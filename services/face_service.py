"""YuNet detecta y alinea; SFace transforma un rostro en un embedding numérico."""
from pathlib import Path
from urllib.request import urlretrieve
import threading
import cv2, numpy as np

MODELS = {
    'face_detection_yunet_2023mar.onnx': 'https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx',
    'face_recognition_sface_2021dec.onnx': 'https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx',
}


class FaceService:
    def __init__(self, model_dir, detection_threshold, cosine_threshold):
        # Carga los modelos YuNet y SFace y configura sus umbrales.
        self.model_dir = Path(model_dir)
        self.det_threshold = detection_threshold
        self.cos_threshold = cosine_threshold
        self.detector = self.recognizer = None
        self.error = None

        # Evita usar los modelos faciales simultáneamente desde distintos hilos.
        self._inference_lock = threading.RLock()

        try:
            self.model_dir.mkdir(exist_ok=True)
            paths = []

            for name, url in MODELS.items():
                path = self.model_dir / name

                # Descarga el modelo solamente si todavía no existe.
                if not path.exists():
                    urlretrieve(url, path)

                paths.append(str(path))

            # YuNet detecta rostros y SFace genera sus características numéricas.
            self.detector = cv2.FaceDetectorYN.create(
                paths[0], '', (320, 320), self.det_threshold, .3, 5000
            )
            self.recognizer = cv2.FaceRecognizerSF.create(paths[1], '')

        except Exception as exc:
            self.error = f'Modelos faciales no disponibles: {exc}'

    @property
    def ready(self):
        # Indica si ambos modelos fueron cargados correctamente.
        return self.detector is not None and self.recognizer is not None

    def detect(self, frame):
        # YuNet busca los rostros presentes en el frame.
        if not self.ready:
            return []

        with self._inference_lock:
            h, w = frame.shape[:2]
            self.detector.setInputSize((w, h))
            _, faces = self.detector.detect(frame)

        return [] if faces is None else list(faces)

    def embedding(self, frame, face):
        # SFace alinea el rostro y lo convierte en un vector numérico.
        with self._inference_lock:
            aligned = self.recognizer.alignCrop(frame, face)
            return self.recognizer.feature(aligned).flatten().astype(np.float32)

    @staticmethod
    def cosine(a, b):
        # Calcula qué tan parecidos son dos embeddings faciales.
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        return float(np.dot(a, b) / denom) if denom else -1.0