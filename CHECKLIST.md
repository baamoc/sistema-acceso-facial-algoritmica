# Checklist verificable de rúbrica

| Requisito | Estado | Implementación / cómo probar |
|---|---|---|
| ABM clientes | IMPLEMENTADO PERO NO EJECUTADO | `routes/admin.py`: alta con cámara, edición, activar/desactivar. Requiere recorrido visual con webcam. |
| Datos, CI único, foto y embedding | IMPLEMENTADO PERO NO EJECUTADO | Esquema en `models/database.py`; alta exige captura, guarda JPG y BLOB. |
| Vista cliente sin controles administrativos | PASS EJECUTADO | `GET /` respondió 200 mediante cliente Flask; `templates/public.html` sólo muestra enlace Administrador. |
| Video en tiempo real | PENDIENTE CÁMARA FÍSICA | `/video-feed` entrega MJPEG desde `CameraService`. |
| Reconocimiento y vigencia | PASS EJECUTADO (vigencia) / PENDIENTE CÁMARA FÍSICA (reconocimiento) | La prueba SQLite real cubrió vigente, futuro, vencido, indefinido e inactivo. |
| Login con hash | PASS EJECUTADO | `GET /admin/login` respondió 200; clave errónea se rechaza y clave válida redirige 302. |
| Clientes, fechas, estado, conteo e historial | IMPLEMENTADO PERO NO EJECUTADO | Panel e historial en plantillas administrativas; consultas a SQLite. |
| Una sola cámara | IMPLEMENTADO PERO NO EJECUTADO | Sólo `services/camera_service.py` contiene `cv2.VideoCapture`; alta usa `get_raw_frame()` y MJPEG usa `get_display_frame()`. |
| No contar por frame | PASS EJECUTADO | Prueba SQLite real: presencia continua genera un evento y retorno después de ausencia genera el segundo. |
| Persistencia tras reiniciar | IMPLEMENTADO PERO NO EJECUTADO | `data/access.db` no se recrea si existe; tablas `IF NOT EXISTS`. |
| Cliente vigente / vencido / futuro / indefinido / inactivo | PASS EJECUTADO | Prueba SQLite real de las cinco condiciones. |
| Rostro desconocido / registro y reconocimiento físico | PENDIENTE DE VALIDACIÓN FÍSICA | Requiere webcam y modelos descargados; procedimiento descrito en README. |

Evidencia ejecutada: `python -m py_compile ...` y `python -m pytest -q` (6 passed); cliente interno Flask: página pública 200, login 200, error de contraseña y login correcto 302, estado 200. Las pruebas también verifican separación `raw_frame`/`display_frame`, CI público y exclusión mutua de inferencias YuNet/SFace. La vista pública muestra nombre, CI, vigencia y accesos. La corrección de concurrencia requiere una nueva validación física; no se declara PASS de alta ni reconocimiento con webcam.
