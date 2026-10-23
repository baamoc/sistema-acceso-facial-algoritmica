"""Único dueño de cv2.VideoCapture y de los cuadros compartidos de la cámara."""
import threading, time
import cv2

class CameraService:
    def __init__(self, index=0):
        self.index, self.cap = index, None
        self.raw_frame = None
        self.display_frame = None
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
            self._handle_frame(frame)

    def _handle_frame(self, frame):
        """Conserva una copia cruda y procesa otra exclusivamente para visualización."""
        raw_frame = frame.copy()
        display_frame = raw_frame.copy()
        if self.processor:
            try:
                display_frame = self.processor(display_frame)
            except Exception as exc:
                self.error = f'Error facial: {exc}'
        with self.lock:
            self.raw_frame = raw_frame
            self.display_frame = display_frame.copy()

    def get_raw_frame(self):
        """Cuadro original, sin rectángulos ni overlays, para alta o recaptura."""
        with self.lock:
            return None if self.raw_frame is None else self.raw_frame.copy()

    def get_display_frame(self):
        """Cuadro procesado para el streaming MJPEG público."""
        with self.lock:
            return None if self.display_frame is None else self.display_frame.copy()

    def mjpeg(self):
        while True:
            frame = self.get_display_frame()
            if frame is None:
                time.sleep(.08); continue
            ok, jpg = cv2.imencode('.jpg', frame)
            if ok: yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpg.tobytes() + b'\r\n'
            time.sleep(.03)

    def stop(self):
        self.running = False
        if self.cap: self.cap.release(); self.cap = None
