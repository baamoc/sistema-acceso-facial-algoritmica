from datetime import date, datetime
import threading, time, cv2, numpy as np


class AccessService:
    def __init__(self, app, face, absence_seconds):
        # Prepara el servicio de acceso, el estado actual y el control de presencia.
        self.app = app
        self.face = face
        self.absence_seconds = absence_seconds

        self.recording_enabled = False
        self.encounter_active = False
        self.no_face_since = None

        self._presence_lock = threading.RLock()

        self.status = {
            'result': 'ESPERANDO ROSTRO',
            'name': '—',
            'ci': '—',
            'expiry': '—',
            'accesses': 0,
            'reason': 'Acerque su rostro a la cámara.'
        }

        self.frame_no = 0

    def evaluate(self, client):
        # Decide si el cliente puede entrar según estado y fechas de vigencia.
        today = date.today().isoformat()

        if not client['activo']:
            return 'ACCESO DENEGADO', 'Cliente inactivo'

        if today < client['fecha_inicio']:
            return 'ACCESO DENEGADO', 'Todavía no vigente'

        if client['fecha_fin'] and today > client['fecha_fin']:
            return 'ACCESO DENEGADO', 'Vigencia vencida'

        return (
            'ACCESO PERMITIDO',
            'Vigencia indefinida'
            if not client['fecha_fin']
            else 'Vigencia activa'
        )

    def _clients(self):
        # Obtiene todos los clientes registrados para comparar sus rostros.
        from models.database import get_db

        return get_db().execute(
            'SELECT * FROM clientes'
        ).fetchall()

    def _record_encounter(self, client, result, reason):
        # Guarda un intento de acceso en el historial de SQLite.
        from models.database import get_db

        local_time = datetime.now().astimezone().isoformat(
            timespec='seconds'
        )

        db = get_db()

        db.execute(
            '''
            INSERT INTO accesos(
                cliente_id,
                fecha_hora,
                resultado,
                motivo
            )
            VALUES (?,?,?,?)
            ''',
            (
                client['id'],
                local_time,
                result,
                reason
            )
        )

        db.commit()

    def set_recording_enabled(self, enabled):
        # Activa el registro de accesos solamente cuando estamos en la vista pública.
        with self._presence_lock:
            enabled = bool(enabled)

            if enabled and not self.recording_enabled:
                self.encounter_active = False
                self.no_face_since = None

            self.recording_enabled = enabled

    def observe_face_presence(self, has_faces, now=None):
        # Considera una nueva entrada solo después de una ausencia real del rostro.
        now = time.monotonic() if now is None else now

        with self._presence_lock:
            if has_faces:
                self.no_face_since = None

            elif self.no_face_since is None:
                self.no_face_since = now

            elif now - self.no_face_since >= self.absence_seconds:
                self.encounter_active = False

    def handle_recognized(self, client):
        # Evalúa al cliente y registra como máximo un acceso por presencia física.
        result, reason = self.evaluate(client)

        with self._presence_lock:
            if self.recording_enabled and not self.encounter_active:
                self._record_encounter(
                    client,
                    result,
                    reason
                )

                self.encounter_active = True

        return result, reason

    def process(self, frame):
        # Procesa el frame: detecta, reconoce, compara y decide el acceso.
        self.frame_no += 1

        if not self.face.ready:
            self.status = {
                'result': 'ESPERANDO ROSTRO',
                'name': '—',
                'ci': '—',
                'expiry': '—',
                'accesses': 0,
                'reason': self.face.error or 'Cargando modelos faciales'
            }

            return frame

        # Procesa reconocimiento cada 4 frames para reducir carga.
        if self.frame_no % 4:
            return frame

        # YuNet detecta si existe algún rostro.
        faces = self.face.detect(frame)

        self.observe_face_presence(bool(faces))

        if not faces:
            self.status = {
                'result': 'ESPERANDO ROSTRO',
                'name': '—',
                'ci': '—',
                'expiry': '—',
                'accesses': 0,
                'reason': 'Acerque su rostro a la cámara.'
            }

            return frame

        # Si hay varios rostros, toma el más grande y genera su embedding.
        face = max(
            faces,
            key=lambda f: f[2] * f[3]
        )

        emb = self.face.embedding(
            frame,
            face
        )

        with self.app.app_context():
            clients = self._clients()

            best = None
            score = -1

            # Compara el rostro actual contra todos los embeddings guardados.
            for c in clients:
                stored = np.frombuffer(
                    c['face_embedding'],
                    dtype=np.float32
                )

                s = self.face.cosine(
                    emb,
                    stored
                )

                if s > score:
                    best, score = c, s

            x, y, w, h = map(
                int,
                face[:4]
            )

            color = (0, 180, 255)

            # Si no supera el umbral, se considera DESCONOCIDO.
            if not best or score < self.face.cos_threshold:
                self.status = {
                    'result': 'DESCONOCIDO',
                    'name': 'DESCONOCIDO',
                    'ci': '—',
                    'expiry': '—',
                    'accesses': 0,
                    'reason': f'Similitud insuficiente ({score:.3f})'
                }

            else:
                # Si reconoce al cliente, evalúa vigencia y registra el acceso.
                result, reason = self.handle_recognized(best)

                db_accesses = self.app.extensions['db_count'](
                    best['id']
                )

                self.status = {
                    'result': result,
                    'name': best['nombre_completo'],
                    'ci': best['ci'],
                    'expiry': best['fecha_fin'] or 'Indefinido',
                    'accesses': db_accesses,
                    'reason': reason
                }

                color = (
                    (30, 180, 30)
                    if result == 'ACCESO PERMITIDO'
                    else (20, 30, 230)
                )

            # Dibuja el rectángulo alrededor del rostro.
            cv2.rectangle(
                frame,
                (x, y),
                (x + w, y + h),
                color,
                2
            )

        return frame