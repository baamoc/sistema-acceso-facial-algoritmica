"""Prototipo académico de detección de señales visibles de fatiga."""

import math
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from statistics import median

# MediaPipe importa matplotlib. Esta carpeta temporal evita avisos de permisos.
os.environ.setdefault("MPLCONFIGDIR", str(Path(os.environ.get("TEMP", ".")) / "fatigue-matplotlib"))

import cv2
import mediapipe as mp
from flask import Flask, Response, jsonify, render_template


# CONFIGURACIÓN ---------------------------------------------------------------
# Son valores iniciales de calibración, no constantes científicas universales.
INDICE_CAMARA = 0
PUERTO_APLICACION = 5001
SEGUNDOS_CALIBRACION = 3.5
MUESTRAS_MINIMAS_CALIBRACION = 15

SEGUNDOS_OJOS_CERRADOS = 4.0
PROPORCION_OJO_CERRADO = 0.65

SEGUNDOS_MIN_BOSTEZO = 1.0
BOSTEZOS_PARA_ALERTA = 3
APERTURA_MINIMA_BOCA = 0.20
MULTIPLICADOR_CALIBRACION_BOCA = 2.5
PROPORCION_CIERRE_BOCA = 0.70

DELTA_CAIDA_CABEZA = 0.055
DELTA_RECUPERACION_CABEZA = 0.025
SEGUNDOS_ESPERA_CABECEO = 1.5
CABECEOS_PARA_ALERTA = 3

MAXIMO_EVENTOS = 50
RUTA_MODELO = Path(__file__).parent / "models" / "face_landmarker.task"


# Puntos de MediaPipe usados para ojos, boca y posición de la cabeza.
OJO_IZQUIERDO = (33, 160, 158, 133, 153, 144)
OJO_DERECHO = (362, 385, 387, 263, 373, 380)
BOCA = (61, 291, 13, 14, 82, 87, 312, 317)
PUNTOS_CABEZA = (10, 1, 152, 33, 133, 362, 263)
PUNTOS_DIBUJO = sorted(set(OJO_IZQUIERDO + OJO_DERECHO + BOCA + PUNTOS_CABEZA))


def distancia(a, b):
    """Distancia entre dos puntos normalizados del rostro."""
    return math.hypot(a.x - b.x, a.y - b.y)


def calcular_proporcion_ojo(landmarks, eye):
    """Apertura vertical del ojo dividida entre su ancho (EAR)."""
    p1, p2, p3, p4, p5, p6 = (landmarks[i] for i in eye)
    vertical = distancia(p2, p6) + distancia(p3, p5)
    horizontal = 2.0 * distancia(p1, p4)
    return vertical / horizontal if horizontal else 0.0


def calcular_ear(landmarks):
    """Promedio de apertura de ambos ojos."""
    left = calcular_proporcion_ojo(landmarks, OJO_IZQUIERDO)
    right = calcular_proporcion_ojo(landmarks, OJO_DERECHO)
    return (left + right) / 2.0


def calcular_mar(landmarks):
    """Apertura vertical promedio de la boca dividida entre su ancho."""
    left, right, top1, bottom1, top2, bottom2, top3, bottom3 = (
        landmarks[i] for i in BOCA
    )
    width = distancia(left, right)
    vertical = (
        distancia(top1, bottom1)
        + distancia(top2, bottom2)
        + distancia(top3, bottom3)
    ) / 3.0
    return vertical / width if width else 0.0


def calcular_posicion_cabeza(landmarks):
    """Posición vertical de la nariz, normalizada por la altura del rostro."""
    forehead = landmarks[10]
    nose = landmarks[1]
    chin = landmarks[152]
    eye_indices = (33, 133, 362, 263)
    eye_y = sum(landmarks[i].y for i in eye_indices) / len(eye_indices)
    face_height = distancia(forehead, chin)
    return (nose.y - eye_y) / face_height if face_height else 0.0


class DetectorFatiga:
    """Guarda la cámara, las métricas y las reglas temporales del sistema."""

    def __init__(self, load_model=True):
        self.lock = threading.Lock()
        self.camera = None
        self.running = False
        self.latest_jpeg = None
        self.camera_error = ""

        self.calibration_started_at = None
        self.calibration_finished = False
        self.eye_samples = []
        self.mouth_samples = []
        self.head_samples = []
        self.neutral_eye = 0.30
        self.neutral_mouth = 0.03
        self.neutral_head = 0.25

        self.eyes_closed_since = None
        self.eye_event_sent = False
        self.yawn_started_at = None
        self.yawn_counted = False
        self.head_is_down = False
        self.last_head_nod_at = -math.inf

        self.yawn_count = 0
        self.head_nod_count = 0
        self.events = []
        self.last_timestamp_ms = 0
        self.landmarker = None

        self.status = {
            "state": "CALIBRANDO",
            "message": "CALIBRANDO — MIRE AL FRENTE",
            "face_detected": False,
            "ear": None,
            "mar": None,
            "head_position": None,
            "eyes_closed_seconds": 0.0,
            "yawns": 0,
            "head_nods": 0,
            "alert": "Mire al frente con ojos abiertos y boca cerrada.",
        }

        if load_model:
            if not RUTA_MODELO.exists():
                raise FileNotFoundError(f"No se encontró el modelo: {RUTA_MODELO}")
            options = mp.tasks.vision.FaceLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(RUTA_MODELO)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self.landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)

    def iniciar_camara(self):
        """Abre una sola webcam y comienza el procesamiento en segundo plano."""
        if self.running:
            return
        self.camera = cv2.VideoCapture(INDICE_CAMARA)
        if not self.camera.isOpened():
            self.camera_error = f"No se pudo abrir la cámara {INDICE_CAMARA}."
            self.camera.release()
            self.camera = None
            return
        self.running = True
        threading.Thread(target=self._bucle_camara, daemon=True).start()

    def detener_camara(self):
        self.running = False
        if self.camera:
            self.camera.release()
            self.camera = None
        if self.landmarker:
            self.landmarker.close()

    def _bucle_camara(self):
        while self.running and self.camera:
            ok, frame = self.camera.read()
            if not ok:
                self.camera_error = "No se pudo leer la cámara."
                time.sleep(0.1)
                continue

            try:
                frame = self.procesar_frame(frame)
                ok, encoded = cv2.imencode(".jpg", frame)
                if ok:
                    with self.lock:
                        self.latest_jpeg = encoded.tobytes()
                        self.camera_error = ""
            except Exception as exc:
                error = f"Error procesando la cámara: {exc}"
                print(error, file=sys.stderr)
                with self.lock:
                    self.camera_error = error
                time.sleep(0.1)

    def procesar_frame(self, frame):
        """Obtiene landmarks, calcula métricas y actualiza las reglas."""
        # El video se muestra como espejo, pero los textos se dibujan después.
        frame = cv2.flip(frame, 1)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        timestamp_ms = max(int(time.monotonic() * 1000), self.last_timestamp_ms + 1)
        self.last_timestamp_ms = timestamp_ms
        result = self.landmarker.detect_for_video(
            mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), timestamp_ms
        )

        now = time.monotonic()
        if not result.face_landmarks:
            self._manejar_rostro_ausente()
            cv2.putText(frame, "ROSTRO NO DETECTADO", (20, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            return frame

        landmarks = result.face_landmarks[0]
        ear = calcular_ear(landmarks)
        mar = calcular_mar(landmarks)
        head_position = calcular_posicion_cabeza(landmarks)

        if not self.calibration_finished:
            self._calibrar(ear, mar, head_position, now)
        else:
            self.actualizar_reglas(ear, mar, head_position, now)

        self._dibujar_puntos(frame, landmarks)
        label = "CALIBRANDO" if not self.calibration_finished else "MONITOREANDO"
        cv2.putText(frame, label, (20, 35), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (0, 220, 255) if not self.calibration_finished else (0, 220, 0), 2)
        return frame

    def _calibrar(self, ear, mar, head_position, now):
        """Toma medianas de ojos abiertos, boca cerrada y cabeza neutral."""
        if self.calibration_started_at is None:
            self.calibration_started_at = now

        self.eye_samples.append(ear)
        self.mouth_samples.append(mar)
        self.head_samples.append(head_position)
        elapsed = now - self.calibration_started_at

        if elapsed >= SEGUNDOS_CALIBRACION and len(self.eye_samples) >= MUESTRAS_MINIMAS_CALIBRACION:
            self.neutral_eye = median(self.eye_samples)
            self.neutral_mouth = median(self.mouth_samples)
            self.neutral_head = median(self.head_samples)
            self.calibration_finished = True

        with self.lock:
            self.status.update(
                state="NORMAL" if self.calibration_finished else "CALIBRANDO",
                message="MONITOREANDO" if self.calibration_finished else "CALIBRANDO — MIRE AL FRENTE",
                face_detected=True,
                ear=round(ear, 3),
                mar=round(mar, 3),
                head_position=round(head_position, 3),
                alert="Sin alerta" if self.calibration_finished else "Mire al frente con ojos abiertos y boca cerrada.",
            )

    def actualizar_reglas(self, ear, mar, head_position, now=None):
        """Aplica las tres reglas temporales usando métricas ya calculadas."""
        now = time.monotonic() if now is None else now
        eye_threshold = self.neutral_eye * PROPORCION_OJO_CERRADO
        mouth_open = max(APERTURA_MINIMA_BOCA, self.neutral_mouth * MULTIPLICADOR_CALIBRACION_BOCA)
        mouth_closed = mouth_open * PROPORCION_CIERRE_BOCA

        # 1. Ojos cerrados: un solo evento por cada cierre continuo.
        if ear < eye_threshold:
            if self.eyes_closed_since is None:
                self.eyes_closed_since = now
            eye_duration = now - self.eyes_closed_since
            if eye_duration >= SEGUNDOS_OJOS_CERRADOS and not self.eye_event_sent:
                self.registrar_evento("Ojos cerrados", f"{eye_duration:.1f} s")
                self.eye_event_sent = True
        else:
            self.eyes_closed_since = None
            self.eye_event_sent = False
            eye_duration = 0.0

        # 2. Bostezo: se cuenta al mantener la boca abierta y se rearma al cerrar.
        if mar > mouth_open:
            if self.yawn_started_at is None:
                self.yawn_started_at = now
            if now - self.yawn_started_at >= SEGUNDOS_MIN_BOSTEZO and not self.yawn_counted:
                self.yawn_count += 1
                self.registrar_evento("Bostezo", str(self.yawn_count))
                self.yawn_counted = True
        elif mar < mouth_closed:
            self.yawn_started_at = None
            self.yawn_counted = False

        # 3. Cabeceo: caída respecto al neutral seguida de una recuperación.
        drop_limit = self.neutral_head + DELTA_CAIDA_CABEZA
        recovery_limit = self.neutral_head + DELTA_RECUPERACION_CABEZA
        if not self.head_is_down and head_position > drop_limit:
            if now - self.last_head_nod_at >= SEGUNDOS_ESPERA_CABECEO:
                self.head_is_down = True
        elif self.head_is_down and head_position < recovery_limit:
            self.head_nod_count += 1
            self.last_head_nod_at = now
            self.head_is_down = False
            self.registrar_evento("Cabeceo", str(self.head_nod_count))

        state, alert = "NORMAL", "Sin alerta"
        if self.yawn_count >= BOSTEZOS_PARA_ALERTA:
            state, alert = "CANSANCIO", "ALERTA DE CANSANCIO"
        if self.eye_event_sent:
            state, alert = "SUEÑO", "ALERTA DE SUEÑO"
        if self.head_nod_count >= CABECEOS_PARA_ALERTA:
            state, alert = "ALERTA", "ALERTA: DETENER EL VEHÍCULO"

        with self.lock:
            self.status.update(
                state=state,
                message="MONITOREANDO",
                face_detected=True,
                ear=round(ear, 3),
                mar=round(mar, 3),
                head_position=round(head_position, 3),
                eyes_closed_seconds=round(eye_duration, 1),
                yawns=self.yawn_count,
                head_nods=self.head_nod_count,
                alert=alert,
            )

    def registrar_evento(self, event_type, value):
        """Añade un evento en memoria; no guarda imágenes ni video."""
        event = {
            "type": event_type,
            "time": datetime.now().strftime("%H:%M:%S"),
            "value": value,
        }
        with self.lock:
            self.events.insert(0, event)
            del self.events[MAXIMO_EVENTOS:]

    def _manejar_rostro_ausente(self):
        """Cancela condiciones incompletas cuando se pierde el rostro."""
        if not self.calibration_finished:
            # La calibración necesita varios segundos continuos con rostro visible.
            self.calibration_started_at = None
            self.eye_samples.clear()
            self.mouth_samples.clear()
            self.head_samples.clear()
        self.eyes_closed_since = None
        self.eye_event_sent = False
        self.yawn_started_at = None
        self.yawn_counted = False
        self.head_is_down = False
        with self.lock:
            self.status.update(
                state="SIN ROSTRO",
                face_detected=False,
                eyes_closed_seconds=0.0,
                message="ROSTRO NO DETECTADO",
                alert="Coloque el rostro frente a la cámara.",
            )

    @staticmethod
    def _dibujar_puntos(frame, landmarks):
        height, width = frame.shape[:2]
        for index in PUNTOS_DIBUJO:
            point = landmarks[index]
            x, y = int(point.x * width), int(point.y * height)
            cv2.circle(frame, (x, y), 2, (0, 255, 255), -1)

    def flujo_video(self):
        """Entrega el último cuadro como video MJPEG al navegador."""
        while True:
            with self.lock:
                jpeg = self.latest_jpeg
            if jpeg is None:
                time.sleep(0.05)
                continue
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            time.sleep(0.03)

    def obtener_estado(self):
        with self.lock:
            return self.status.copy() | {
                "events": list(self.events),
                "camera_error": self.camera_error,
            }


app = Flask(__name__)
detector = DetectorFatiga()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/video_feed")
def video_feed():
    return Response(detector.flujo_video(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.get("/status")
def status():
    return jsonify(detector.obtener_estado())


def ejecutar_autoprueba():
    """Prueba corta de las reglas temporales sin webcam."""
    test = DetectorFatiga(load_model=False)
    test.calibration_finished = True
    test.neutral_eye, test.neutral_mouth, test.neutral_head = 0.30, 0.03, 0.25

    test.actualizar_reglas(0.10, 0.03, 0.25, 0.0)
    test.actualizar_reglas(0.10, 0.03, 0.25, 3.9)
    assert not test.events
    test.actualizar_reglas(0.10, 0.03, 0.25, 4.1)
    test.actualizar_reglas(0.10, 0.03, 0.25, 8.0)
    assert [e["type"] for e in test.events].count("Ojos cerrados") == 1
    test.actualizar_reglas(0.30, 0.03, 0.25, 8.1)
    test.actualizar_reglas(0.10, 0.03, 0.25, 9.0)
    test.actualizar_reglas(0.10, 0.03, 0.25, 13.1)
    assert [e["type"] for e in test.events].count("Ojos cerrados") == 2

    test.actualizar_reglas(0.30, 0.30, 0.25, 20.0)
    test.actualizar_reglas(0.30, 0.30, 0.25, 21.1)
    test.actualizar_reglas(0.30, 0.30, 0.25, 22.0)
    assert test.yawn_count == 1
    test.actualizar_reglas(0.30, 0.03, 0.25, 22.1)
    test.actualizar_reglas(0.30, 0.30, 0.25, 23.0)
    test.actualizar_reglas(0.30, 0.30, 0.25, 24.1)
    assert test.yawn_count == 2
    test.actualizar_reglas(0.30, 0.03, 0.25, 24.2)
    test.actualizar_reglas(0.30, 0.30, 0.25, 25.0)
    test.actualizar_reglas(0.30, 0.30, 0.25, 26.1)
    assert test.yawn_count == 3
    assert test.status['state'] == 'CANSANCIO'

    test.actualizar_reglas(0.10, 0.03, 0.25, 27.0)
    test.actualizar_reglas(0.10, 0.03, 0.25, 31.1)
    assert test.status['state'] == 'SUEÑO'
    test.actualizar_reglas(0.30, 0.03, 0.25, 31.2)

    test.actualizar_reglas(0.30, 0.03, 0.32, 32.0)
    test.actualizar_reglas(0.30, 0.03, 0.33, 32.2)
    assert test.head_nod_count == 0
    test.actualizar_reglas(0.30, 0.03, 0.25, 32.5)
    assert test.head_nod_count == 1
    test.actualizar_reglas(0.30, 0.03, 0.32, 34.1)
    test.actualizar_reglas(0.30, 0.03, 0.25, 34.5)
    test.actualizar_reglas(0.30, 0.03, 0.32, 36.1)
    test.actualizar_reglas(0.30, 0.03, 0.25, 36.5)
    assert test.head_nod_count == 3
    assert test.status['state'] == 'ALERTA'

    test.actualizar_reglas(0.10, 0.03, 0.25, 37.0)
    test.actualizar_reglas(0.10, 0.03, 0.25, 41.1)
    assert test.status['state'] == 'ALERTA'
    print("Pruebas de reglas: OK")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        ejecutar_autoprueba()
    else:
        detector.iniciar_camara()
        print(f"Abra http://127.0.0.1:{PUERTO_APLICACION}")
        try:
            app.run(host="127.0.0.1", port=PUERTO_APLICACION, threaded=True, debug=False)
        finally:
            detector.detener_camara()
