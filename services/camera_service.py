"""Único dueño de cv2.VideoCapture: todos los endpoints reutilizan latest_frame."""
import threading, time
import cv2

class CameraService:
    def __init__(self, index=0):
        self.index, self.cap, self.frame = index, None, None
        self.lock = threading.Lock(); self.running = False; self.processor = None; self.error = None

    def start(self):
        if self.running: return
        self.cap = cv2.VideoCapture(self.index)
        if not self.cap.isOpened():
            self.error = f"No se pudo abrir la cámara {self.index}"; self.cap.release(); self.cap = None; return
        self.running = True
        threading.Thread(target=self._loop, daemon=True, name='single-camera').start()

    def _loop(self):
        while self.running and self.cap:
            ok, frame = self.cap.read()
            if not ok: self.error = 'No se pudo leer un cuadro de cámara'; time.sleep(.1); continue
            if self.processor:
                try: frame = self.processor(frame)
                except Exception as exc: self.error = f'Error facial: {exc}'
            with self.lock: self.frame = frame.copy()

    def get_frame(self):
        with self.lock: return None if self.frame is None else self.frame.copy()

    def mjpeg(self):
        while True:
            frame = self.get_frame()
            if frame is None:
                time.sleep(.08); continue
            ok, jpg = cv2.imencode('.jpg', frame)
            if ok: yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpg.tobytes() + b'\r\n'
            time.sleep(.03)

    def stop(self):
        self.running = False
        if self.cap: self.cap.release(); self.cap = None
