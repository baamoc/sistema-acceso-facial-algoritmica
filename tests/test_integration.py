import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
import numpy as np
from werkzeug.security import generate_password_hash
from app import create_app
from models.database import close_db, get_db
from services.camera_service import CameraService
from services.face_service import FaceService

class NoFace:
 ready=False; error='Prueba sin modelos'

class RecognizesFace:
 ready=True; error=None; cos_threshold=.363
 def detect(self, frame): return [np.array([0,0,3,3,0,0,0,0,0,0,0,0,0,0,0], dtype=np.float32)]
 def embedding(self, frame, face): return np.array([1,0], dtype=np.float32)
 @staticmethod
 def cosine(a,b): return float(np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b)))

def build(face=None):
 folder=tempfile.TemporaryDirectory(); root=Path(folder.name)
 app=create_app({'TESTING':True,'DATABASE':root/'real.sqlite','FACE_DIR':root/'faces','MODEL_DIR':root/'models','FACE_SERVICE':face or NoFace(),'ABSENCE_SECONDS':4,'FIRST_ADMIN_USER':None,'FIRST_ADMIN_PASSWORD':None},start_camera=False)
 return app,folder
def insert(app,name,ci,start='2020-01-01',end=None,active=1):
 with app.app_context():
  db=get_db(); cur=db.execute('INSERT INTO clientes(nombre_completo,ci,fecha_inicio,fecha_fin,activo,face_embedding) VALUES(?,?,?,?,?,?)',(name,ci,start,end,active,np.array([1,0],np.float32).tobytes())); db.commit(); return cur.lastrowid
def test_validity_rules_use_real_sqlite():
 app,tmp=build()
 try:
  ids=[insert(app,'Vigente','1'),insert(app,'Futuro','2','2999-01-01'),insert(app,'Vencido','3','2020-01-01','2020-01-02'),insert(app,'Inactivo','4',active=0),insert(app,'Indefinido','5')]
  with app.app_context():
   rows=get_db().execute('SELECT * FROM clientes ORDER BY id').fetchall(); service=app.extensions['access']
   assert [service.evaluate(x)[0] for x in rows]==['ACCESO PERMITIDO','ACCESO DENEGADO','ACCESO DENEGADO','ACCESO DENEGADO','ACCESO PERMITIDO']
 finally:
  with app.app_context(): close_db()
  tmp.cleanup()
def test_access_events_only_record_in_public_mode_with_presence_cooldown():
 app,tmp=build()
 try:
  cid=insert(app,'Ana','9')
  with app.app_context():
   client=get_db().execute('SELECT * FROM clientes WHERE id=?',(cid,)).fetchone(); s=app.extensions['access']
   s.observe_face_presence(True,10); s.handle_recognized(client)
   assert get_db().execute('SELECT COUNT(*) FROM accesos WHERE cliente_id=?',(cid,)).fetchone()[0]==0
   s.set_recording_enabled(True); s.observe_face_presence(True,11); s.handle_recognized(client)
   assert get_db().execute('SELECT COUNT(*) FROM accesos WHERE cliente_id=?',(cid,)).fetchone()[0]==1
   s.handle_recognized(client); s.handle_recognized(client)
   assert get_db().execute('SELECT COUNT(*) FROM accesos WHERE cliente_id=?',(cid,)).fetchone()[0]==1
   s.observe_face_presence(True,20); s.handle_recognized(client)
   assert get_db().execute('SELECT COUNT(*) FROM accesos WHERE cliente_id=?',(cid,)).fetchone()[0]==1
   s.observe_face_presence(False,30); s.observe_face_presence(False,33.9); s.observe_face_presence(True,34); s.handle_recognized(client)
   assert get_db().execute('SELECT COUNT(*) FROM accesos WHERE cliente_id=?',(cid,)).fetchone()[0]==1
   s.observe_face_presence(False,40); s.observe_face_presence(False,44); s.observe_face_presence(True,45); s.handle_recognized(client)
   events=get_db().execute('SELECT fecha_hora FROM accesos WHERE cliente_id=? ORDER BY id',(cid,)).fetchall()
   assert len(events)==2
   assert all(datetime.fromisoformat(event['fecha_hora']).utcoffset() is not None for event in events)
 finally:
  with app.app_context(): close_db()
  tmp.cleanup()
def test_login_password_hash_and_persistence():
 app,tmp=build()
 try:
  with app.app_context():
   db=get_db(); db.execute('INSERT INTO administradores(usuario,password_hash) VALUES (?,?)',('admin',generate_password_hash('secreta'))); db.commit()
   assert db.execute('SELECT password_hash FROM administradores').fetchone()[0] != 'secreta'
  c=app.test_client(); assert c.post('/admin/login',data={'usuario':'admin','password':'mala'}).status_code==200
  assert c.post('/admin/login',data={'usuario':'admin','password':'secreta'}).status_code==302
 finally:
  with app.app_context(): close_db()
  tmp.cleanup()
def test_build_does_not_inherit_initial_admin_environment(monkeypatch):
 monkeypatch.setenv('FIRST_ADMIN_USER','admin-real')
 monkeypatch.setenv('FIRST_ADMIN_PASSWORD','secreto-real')
 app,tmp=build()
 try:
  with app.app_context():
   assert get_db().execute('SELECT COUNT(*) FROM administradores').fetchone()[0]==0
 finally:
  with app.app_context(): close_db()
  tmp.cleanup()
def test_public_and_admin_routes_toggle_recording_and_reset_presence():
 app,tmp=build()
 try:
  cid=insert(app,'Ruta Pública','77'); service=app.extensions['access']; client=app.test_client()
  with app.app_context():
   recognized=get_db().execute('SELECT * FROM clientes WHERE id=?',(cid,)).fetchone()
   service.handle_recognized(recognized)
   assert get_db().execute('SELECT COUNT(*) FROM accesos').fetchone()[0]==0
  assert service.recording_enabled is False
  assert client.get('/').status_code==200
  assert service.recording_enabled is True
  with app.app_context():
   service.handle_recognized(recognized); service.handle_recognized(recognized)
   assert get_db().execute('SELECT COUNT(*) FROM accesos').fetchone()[0]==1
  assert client.get('/admin/login').status_code==200
  assert service.recording_enabled is False
  with app.app_context():
   service.handle_recognized(recognized)
   assert get_db().execute('SELECT COUNT(*) FROM accesos').fetchone()[0]==1
  assert client.get('/').status_code==200
  assert service.recording_enabled is True
  assert service.encounter_active is False
  assert service.no_face_since is None
  with app.app_context():
   service.handle_recognized(recognized); service.handle_recognized(recognized)
   assert get_db().execute('SELECT COUNT(*) FROM accesos').fetchone()[0]==2
 finally:
  with app.app_context(): close_db()
  tmp.cleanup()
def test_camera_keeps_raw_frame_separate_from_display_frame():
 camera=CameraService()
 camera.processor=lambda frame: frame.__setitem__((0,0), [255,0,0]) or frame
 source=np.zeros((3,3,3), dtype=np.uint8)
 camera._handle_frame(source)
 raw=camera.get_raw_frame(); display=camera.get_display_frame()
 assert np.array_equal(raw, source)
 assert not np.array_equal(raw, display)
 assert np.array_equal(display[0,0], [255,0,0])
def test_recognized_status_exposes_client_ci():
 app,tmp=build(RecognizesFace())
 try:
  insert(app,'Ana Pérez','123456')
  with app.app_context():
   service=app.extensions['access']
   for _ in range(4): service.process(np.zeros((8,8,3), dtype=np.uint8))
   assert service.status['ci']=='123456'
   assert service.status['result']=='ACCESO PERMITIDO'
  response=app.test_client().get('/api/status')
  assert response.get_json()['ci']=='123456'
 finally:
  with app.app_context(): close_db()
  tmp.cleanup()
def test_face_service_serializes_detector_and_recognizer_inference():
 class Probe:
  def __init__(self): self.active=0; self.maximum=0; self.lock=threading.Lock()
  def operation(self, result=None):
   with self.lock:
    self.active+=1; self.maximum=max(self.maximum,self.active)
   time.sleep(.01)
   with self.lock: self.active-=1
   return result
 class Detector:
  def setInputSize(self, size): probe.operation()
  def detect(self, frame): return probe.operation((None, np.zeros((1,15),dtype=np.float32)))
 class Recognizer:
  def alignCrop(self, frame, face): return probe.operation(frame)
  def feature(self, aligned): return probe.operation(np.array([[1,0]],dtype=np.float32))
 probe=Probe(); service=FaceService.__new__(FaceService)
 service.detector=Detector(); service.recognizer=Recognizer(); service._inference_lock=threading.RLock()
 frame=np.zeros((8,8,3),dtype=np.uint8); face=np.zeros(15,dtype=np.float32)
 with ThreadPoolExecutor(max_workers=8) as executor:
  futures=[executor.submit(service.detect,frame) if i%2==0 else executor.submit(service.embedding,frame,face) for i in range(16)]
  for future in futures: future.result()
 assert probe.maximum==1
