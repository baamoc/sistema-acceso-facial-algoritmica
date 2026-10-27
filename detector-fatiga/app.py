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
CAMERA_INDEX = 0
APP_PORT = 5001
CALIBRATION_SECONDS = 3.5
MIN_CALIBRATION_SAMPLES = 15

EYE_CLOSED_SECONDS = 4.0
EYE_CLOSED_RATIO = 0.65

YAWN_MIN_SECONDS = 1.0
YAWNS_FOR_ALERT = 3
MOUTH_OPEN_MIN = 0.20
MOUTH_CALIBRATION_MULTIPLIER = 2.5
MOUTH_CLOSE_RATIO = 0.70

HEAD_DROP_DELTA = 0.055
HEAD_RECOVERY_DELTA = 0.025
HEAD_NOD_COOLDOWN = 1.5
HEAD_NODS_FOR_ALERT = 3

MAX_EVENTS = 50
MODEL_PATH = Path(__file__).parent / "models" / "face_landmarker.task"


# Puntos de MediaPipe usados para ojos, boca y posición de la cabeza.
LEFT_EYE = (33, 160, 158, 133, 153, 144)
RIGHT_EYE = (362, 385, 387, 263, 373, 380)
MOUTH = (61, 291, 13, 14, 82, 87, 312, 317)
HEAD_POINTS = (10, 1, 152, 33, 133, 362, 263)
DRAW_POINTS = sorted(set(LEFT_EYE + RIGHT_EYE + MOUTH + HEAD_POINTS))


def distance(a, b):
    """Distancia entre dos puntos normalizados del rostro."""
    return math.hypot(a.x - b.x, a.y - b.y)


def calculate_eye_ratio(landmarks, eye):
    """Apertura vertical del ojo dividida entre su ancho (EAR)."""
    p1, p2, p3, p4, p5, p6 = (landmarks[i] for i in eye)
    vertical = distance(p2, p6) + distance(p3, p5)
    horizontal = 2.0 * distance(p1, p4)
    return vertical / horizontal if horizontal else 0.0


def calculate_ear(landmarks):
    """Promedio de apertura de ambos ojos."""
    left = calculate_eye_ratio(landmarks, LEFT_EYE)
    right = calculate_eye_ratio(landmarks, RIGHT_EYE)
    return (left + right) / 2.0


def calculate_mar(landmarks):
    """Apertura vertical promedio de la boca dividida entre su ancho."""
    left, right, top1, bottom1, top2, bottom2, top3, bottom3 = (
        landmarks[i] for i in MOUTH
    )
    width = distance(left, right)
    vertical = (
        distance(top1, bottom1)
        + distance(top2, bottom2)
        + distance(top3, bottom3)
    ) / 3.0
    return vertical / width if width else 0.0


def calculate_head_position(landmarks):
    """Posición vertical de la nariz, normalizada por la altura del rostro."""
    forehead = landmarks[10]
    nose = landmarks[1]
    chin = landmarks[152]
    eye_indices = (33, 133, 362, 263)
    eye_y = sum(landmarks[i].y for i in eye_indices) / len(eye_indices)
    face_height = distance(forehead, chin)
    return (nose.y - eye_y) / face_height if face_height else 0.0


class FatigueDetector:
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
            if not MODEL_PATH.exists():
                raise FileNotFoundError(f"No se encontró el modelo: {MODEL_PATH}")
            options = mp.tasks.vision.FaceLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(MODEL_PATH)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self.landmarker = mp.tasks.vision.FaceLandmarker.create_from_options(options)

    def start_camera(self):
        """Abre una sola webcam y comienza el procesamiento en segundo plano."""
        if self.running:
            return
        self.camera = cv2.VideoCapture(CAMERA_INDEX)
        if not self.camera.isOpened():
            self.camera_error = f"No se pudo abrir la cámara {CAMERA_INDEX}."
            self.camera.release()
            self.camera = None
            return
        self.running = True
        threading.Thread(target=self._camera_loop, daemon=True).start()

    def stop_camera(self):
        self.running = False
        if self.camera:
            self.camera.release()
            self.camera = None
        if self.landmarker:
            self.landmarker.close()

    def _camera_loop(self):
        while self.running and self.camera:
            ok, frame = self.camera.read()
            if not ok:
                self.camera_error = "No se pudo leer la cámara."
                time.sleep(0.1)
                continue

            try:
                frame = self.process_frame(frame)
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

    def process_frame(self, frame):
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
            self._handle_missing_face()
            cv2.putText(frame, "ROSTRO NO DETECTADO", (20, 35),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
            return frame

        landmarks = result.face_landmarks[0]
        ear = calculate_ear(landmarks)
        mar = calculate_mar(landmarks)
        head_position = calculate_head_position(landmarks)

        if not self.calibration_finished:
            self._calibrate(ear, mar, head_position, now)
        else:
            self.update_rules(ear, mar, head_position, now)

        self._draw_landmarks(frame, landmarks)
        label = "CALIBRANDO" if not self.calibration_finished else "MONITOREANDO"
        cv2.putText(frame, label, (20, 35), cv2.FONT_HERSHEY_SIMPLEX,
                    0.8, (0, 220, 255) if not self.calibration_finished else (0, 220, 0), 2)
        return frame

    def _calibrate(self, ear, mar, head_position, now):
        """Toma medianas de ojos abiertos, boca cerrada y cabeza neutral."""
        if self.calibration_started_at is None:
            self.calibration_started_at = now

        self.eye_samples.append(ear)
        self.mouth_samples.append(mar)
        self.head_samples.append(head_position)
        elapsed = now - self.calibration_started_at

        if elapsed >= CALIBRATION_SECONDS and len(self.eye_samples) >= MIN_CALIBRATION_SAMPLES:
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

    def update_rules(self, ear, mar, head_position, now=None):
        """Aplica las tres reglas temporales usando métricas ya calculadas."""
        now = time.monotonic() if now is None else now
        eye_threshold = self.neutral_eye * EYE_CLOSED_RATIO
        mouth_open = max(MOUTH_OPEN_MIN, self.neutral_mouth * MOUTH_CALIBRATION_MULTIPLIER)
        mouth_closed = mouth_open * MOUTH_CLOSE_RATIO

        # 1. Ojos cerrados: un solo evento por cada cierre continuo.
        if ear < eye_threshold:
            if self.eyes_closed_since is None:
                self.eyes_closed_since = now
            eye_duration = now - self.eyes_closed_since
            if eye_duration >= EYE_CLOSED_SECONDS and not self.eye_event_sent:
                self.register_event("Ojos cerrados", f"{eye_duration:.1f} s")
                self.eye_event_sent = True
        else:
            self.eyes_closed_since = None
            self.eye_event_sent = False
            eye_duration = 0.0

        # 2. Bostezo: se cuenta al mantener la boca abierta y se rearma al cerrar.
        if mar > mouth_open:
            if self.yawn_started_at is None:
                self.yawn_started_at = now
            if now - self.yawn_started_at >= YAWN_MIN_SECONDS and not self.yawn_counted:
                self.yawn_count += 1
                self.register_event("Bostezo", str(self.yawn_count))
                self.yawn_counted = True
        elif mar < mouth_closed:
            self.yawn_started_at = None
            self.yawn_counted = False

        # 3. Cabeceo: caída respecto al neutral seguida de una recuperación.
        drop_limit = self.neutral_head + HEAD_DROP_DELTA
        recovery_limit = self.neutral_head + HEAD_RECOVERY_DELTA
        if not self.head_is_down and head_position > drop_limit:
            if now - self.last_head_nod_at >= HEAD_NOD_COOLDOWN:
                self.head_is_down = True
        elif self.head_is_down and head_position < recovery_limit:
            self.head_nod_count += 1
            self.last_head_nod_at = now
            self.head_is_down = False
            self.register_event("Cabeceo", str(self.head_nod_count))

        state, alert = "NORMAL", "Sin alerta"
        if self.yawn_count >= YAWNS_FOR_ALERT:
            state, alert = "CANSANCIO", "ALERTA DE CANSANCIO"
        if self.eye_event_sent:
            state, alert = "SUEÑO", "ALERTA DE SUEÑO"
        if self.head_nod_count >= HEAD_NODS_FOR_ALERT:
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

    def register_event(self, event_type, value):
        """Añade un evento en memoria; no guarda imágenes ni video."""
        event = {
            "type": event_type,
            "time": datetime.now().strftime("%H:%M:%S"),
            "value": value,
        }
        with self.lock:
            self.events.insert(0, event)
            del self.events[MAX_EVENTS:]

    def _handle_missing_face(self):
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
    def _draw_landmarks(frame, landmarks):
        height, width = frame.shape[:2]
        for index in DRAW_POINTS:
            point = landmarks[index]
            x, y = int(point.x * width), int(point.y * height)
            cv2.circle(frame, (x, y), 2, (0, 255, 255), -1)

    def stream(self):
        """Entrega el último cuadro como video MJPEG al navegador."""
        while True:
            with self.lock:
                jpeg = self.latest_jpeg
            if jpeg is None:
                time.sleep(0.05)
                continue
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            time.sleep(0.03)

    def public_status(self):
        with self.lock:
            return self.status.copy() | {
                "events": list(self.events),
                "camera_error": self.camera_error,
            }


app = Flask(__name__)
detector = FatigueDetector()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/video_feed")
def video_feed():
    return Response(detector.stream(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.get("/status")
def status():
    return jsonify(detector.public_status())


def run_self_test():
    """Prueba corta de las reglas temporales sin webcam."""
    test = FatigueDetector(load_model=False)
    test.calibration_finished = True
    test.neutral_eye, test.neutral_mouth, test.neutral_head = 0.30, 0.03, 0.25

    test.update_rules(0.10, 0.03, 0.25, 0.0)
    test.update_rules(0.10, 0.03, 0.25, 3.9)
    assert not test.events
    test.update_rules(0.10, 0.03, 0.25, 4.1)
    test.update_rules(0.10, 0.03, 0.25, 8.0)
    assert [e["type"] for e in test.events].count("Ojos cerrados") == 1
    test.update_rules(0.30, 0.03, 0.25, 8.1)
    test.update_rules(0.10, 0.03, 0.25, 9.0)
    test.update_rules(0.10, 0.03, 0.25, 13.1)
    assert [e["type"] for e in test.events].count("Ojos cerrados") == 2

    test.update_rules(0.30, 0.30, 0.25, 20.0)
    test.update_rules(0.30, 0.30, 0.25, 21.1)
    test.update_rules(0.30, 0.30, 0.25, 22.0)
    assert test.yawn_count == 1
    test.update_rules(0.30, 0.03, 0.25, 22.1)
    test.update_rules(0.30, 0.30, 0.25, 23.0)
    test.update_rules(0.30, 0.30, 0.25, 24.1)
    assert test.yawn_count == 2
    test.update_rules(0.30, 0.03, 0.25, 24.2)
    test.update_rules(0.30, 0.30, 0.25, 25.0)
    test.update_rules(0.30, 0.30, 0.25, 26.1)
    assert test.yawn_count == 3
    assert test.status['state'] == 'CANSANCIO'

    test.update_rules(0.10, 0.03, 0.25, 27.0)
    test.update_rules(0.10, 0.03, 0.25, 31.1)
    assert test.status['state'] == 'SUEÑO'
    test.update_rules(0.30, 0.03, 0.25, 31.2)

    test.update_rules(0.30, 0.03, 0.32, 32.0)
    test.update_rules(0.30, 0.03, 0.33, 32.2)
    assert test.head_nod_count == 0
    test.update_rules(0.30, 0.03, 0.25, 32.5)
    assert test.head_nod_count == 1
    test.update_rules(0.30, 0.03, 0.32, 34.1)
    test.update_rules(0.30, 0.03, 0.25, 34.5)
    test.update_rules(0.30, 0.03, 0.32, 36.1)
    test.update_rules(0.30, 0.03, 0.25, 36.5)
    assert test.head_nod_count == 3
    assert test.status['state'] == 'ALERTA'

    test.update_rules(0.10, 0.03, 0.25, 37.0)
    test.update_rules(0.10, 0.03, 0.25, 41.1)
    assert test.status['state'] == 'ALERTA'
    print("Pruebas de reglas: OK")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        run_self_test()
    else:
        detector.start_camera()
        print(f"Abra http://127.0.0.1:{APP_PORT}")
        try:
            app.run(host="127.0.0.1", port=APP_PORT, threaded=True, debug=False)
        finally:
            detector.stop_camera()
