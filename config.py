from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent  # Carpeta raíz del proyecto


class Config:
    SECRET_KEY = os.environ.get(
        "SECRET_KEY",
        "cambie-esta-clave-para-produccion-local"
    )  # Clave usada por Flask para proteger sesiones

    DATABASE = ROOT / "data" / "access.db"       # Base de datos SQLite
    FACE_DIR = ROOT / "faces"                    # Fotos de rostros registrados
    MODEL_DIR = ROOT / "face_models"             # Modelos YuNet y SFace

    DETECTION_THRESHOLD = float(
        os.environ.get("DETECTION_THRESHOLD", "0.8")
    )  # Umbral de YuNet para detectar una cara

    COSINE_THRESHOLD = float(
        os.environ.get("COSINE_THRESHOLD", "0.363")
    )  # Umbral para reconocer si es la misma persona

    ABSENCE_SECONDS = float(
        os.environ.get("ABSENCE_SECONDS", "4")
    )  # Segundos sin rostro para permitir un nuevo acceso

    CAMERA_INDEX = int(
        os.environ.get("CAMERA_INDEX", "0")
    )  # Cámara utilizada; 0 normalmente es la principal

    FIRST_ADMIN_USER = os.environ.get(
        "FIRST_ADMIN_USER"
    )  # Usuario del primer administrador

    FIRST_ADMIN_PASSWORD = os.environ.get(
        "FIRST_ADMIN_PASSWORD"
    )  # Contraseña inicial del administrador