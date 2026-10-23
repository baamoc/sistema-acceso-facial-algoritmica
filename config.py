from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "cambie-esta-clave-para-produccion-local")
    DATABASE = ROOT / "data" / "access.db"
    FACE_DIR = ROOT / "faces"
    MODEL_DIR = ROOT / "face_models"
    DETECTION_THRESHOLD = float(os.environ.get("DETECTION_THRESHOLD", "0.8"))
    COSINE_THRESHOLD = float(os.environ.get("COSINE_THRESHOLD", "0.363"))
    ABSENCE_SECONDS = float(os.environ.get("ABSENCE_SECONDS", "4"))
    CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "0"))
    FIRST_ADMIN_USER = os.environ.get("FIRST_ADMIN_USER")
    FIRST_ADMIN_PASSWORD = os.environ.get("FIRST_ADMIN_PASSWORD")
