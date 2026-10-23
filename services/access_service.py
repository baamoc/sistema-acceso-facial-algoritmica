from datetime import date, datetime
import threading, time, cv2, numpy as np

class AccessService:
    def __init__(self, app, face, absence_seconds):
        self.app=app; self.face=face; self.absence_seconds=absence_seconds; self.presence={}
        self.recording_enabled=False; self._presence_lock=threading.RLock()
        self.status={'result':'ESPERANDO ROSTRO','name':'—','ci':'—','expiry':'—','accesses':0,'reason':'Acerque su rostro a la cámara.'}
        self.frame_no=0
    def evaluate(self, client):
        today=date.today().isoformat()
        if not client['activo']: return 'ACCESO DENEGADO', 'Cliente inactivo'
        if today < client['fecha_inicio']: return 'ACCESO DENEGADO', 'Todavía no vigente'
        if client['fecha_fin'] and today > client['fecha_fin']: return 'ACCESO DENEGADO', 'Vigencia vencida'
        return 'ACCESO PERMITIDO', 'Vigencia indefinida' if not client['fecha_fin'] else 'Vigencia activa'
    def _clients(self):
        from models.database import get_db
        return get_db().execute('SELECT * FROM clientes').fetchall()
    def _record_encounter(self, client, result, reason):
        from models.database import get_db
        local_time=datetime.now().astimezone().isoformat(timespec='seconds')
        db=get_db(); db.execute('INSERT INTO accesos(cliente_id,fecha_hora,resultado,motivo) VALUES (?,?,?,?)',(client['id'],local_time,result,reason)); db.commit()
    def set_recording_enabled(self, enabled):
        """Activa el historial sólo en vista pública y reinicia la presencia al volver."""
        with self._presence_lock:
            enabled=bool(enabled)
            if enabled and not self.recording_enabled:
                self.presence.clear()
            self.recording_enabled=enabled
    def handle_recognized(self, client, now=None):
        """Actualiza presencia y registra sólo el primer cuadro de cada encuentro."""
        result,reason=self.evaluate(client); now=time.monotonic() if now is None else now
        with self._presence_lock:
            if self.recording_enabled:
                if now-self.presence.get(client['id'], float('-inf')) > self.absence_seconds:
                    self._record_encounter(client,result,reason)
                self.presence[client['id']]=now
        return result,reason
    def process(self, frame):
        self.frame_no+=1
        if not self.face.ready: self.status={'result':'ESPERANDO ROSTRO','name':'—','ci':'—','expiry':'—','accesses':0,'reason':self.face.error or 'Cargando modelos faciales'}; return frame
        if self.frame_no % 4: return frame
        faces=self.face.detect(frame)
        if not faces:
            self.status={'result':'ESPERANDO ROSTRO','name':'—','ci':'—','expiry':'—','accesses':0,'reason':'Acerque su rostro a la cámara.'}; return frame
        face=max(faces,key=lambda f:f[2]*f[3]); emb=self.face.embedding(frame,face)
        with self.app.app_context():
            clients=self._clients(); best=None; score=-1
            for c in clients:
                stored=np.frombuffer(c['face_embedding'],dtype=np.float32)
                s=self.face.cosine(emb,stored)
                if s>score: best,score=c,s
            x,y,w,h=map(int,face[:4]); color=(0,180,255)
            if not best or score < self.face.cos_threshold:
                self.status={'result':'DESCONOCIDO','name':'DESCONOCIDO','ci':'—','expiry':'—','accesses':0,'reason':f'Similitud insuficiente ({score:.3f})'}
            else:
                result,reason=self.handle_recognized(best)
                db_accesses=self.app.extensions['db_count'](best['id'])
                self.status={'result':result,'name':best['nombre_completo'],'ci':best['ci'],'expiry':best['fecha_fin'] or 'Indefinido','accesses':db_accesses,'reason':reason}
                color=(30,180,30) if result=='ACCESO PERMITIDO' else (20,30,230)
            cv2.rectangle(frame,(x,y),(x+w,y+h),color,2)
        return frame
