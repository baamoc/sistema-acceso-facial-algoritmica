# Checklist verificable de rúbrica

| Requisito | Estado | Implementación / cómo probar |
|---|---|---|
| ABM clientes | PASS EJECUTADO (alta física) / IMPLEMENTADO PERO NO EJECUTADO (edición y baja) | El alta con cámara fue comprobada físicamente. Edición y activar/desactivar permanecen pendientes de recorrido manual. |
| Datos, CI único, foto y embedding | PASS EJECUTADO (alta física) | El alta comprobada guardó CI, fotografía y embedding mediante `routes/admin.py`. |
| Vista cliente sin controles administrativos | PASS EJECUTADO | `GET /` respondió 200 mediante cliente Flask; `templates/public.html` sólo muestra enlace Administrador. |
| Video en tiempo real | PASS EJECUTADO antes de esta corrección | Webcam y video público fueron comprobados físicamente. No se declara una nueva validación física posterior. |
| Reconocimiento y vigencia | PASS EJECUTADO antes de esta corrección / PENDIENTE REVALIDACIÓN FÍSICA | Se comprobó reconocimiento físico, CI, vigencia indefinida y acceso permitido. Las reglas de vigencia también tienen prueba SQLite. Falta revalidar físicamente el modo de registro corregido. |
| Login con hash | PASS EJECUTADO | `GET /admin/login` respondió 200; clave errónea se rechaza y clave válida redirige 302. |
| Clientes, fechas, estado, conteo e historial | IMPLEMENTADO PERO NO EJECUTADO | Panel e historial en plantillas administrativas; consultas a SQLite. |
| Una sola cámara | PASS EJECUTADO antes de esta corrección | Sólo `services/camera_service.py` contiene `cv2.VideoCapture`; alta usa `get_raw_frame()` y MJPEG usa `get_display_frame()`. Webcam compartida comprobada físicamente. |
| No contar por frame ni en administración | PASS EJECUTADO automatizado / PENDIENTE REVALIDACIÓN FÍSICA | SQLite real: administración no registra; público registra el primero; presencia continua no duplica; ausencia y retorno generan el siguiente. |
| Persistencia tras reiniciar | IMPLEMENTADO PERO NO EJECUTADO | `data/access.db` no se recrea si existe; tablas `IF NOT EXISTS`. |
| Cliente vigente / vencido / futuro / indefinido / inactivo | PASS EJECUTADO | Prueba SQLite real de las cinco condiciones. |
| Rostro desconocido / registro y reconocimiento físico | PASS EJECUTADO antes de esta corrección / PENDIENTE REVALIDACIÓN FÍSICA | Desconocido, alta y reconocimiento fueron comprobados físicamente. Falta repetir el flujo después de suspender eventos en administración. |

Evidencia automatizada actual: `python -m py_compile ...` y `python -m pytest -q` (8 passed). Antes de esta corrección ya existían 7 pruebas PASS. La suite verifica además separación `raw_frame`/`display_frame`, CI público, exclusión mutua de YuNet/SFace, aislamiento de credenciales, modos público/administrativo, cooldown y hora local con zona. No se declara PASS de la validación física posterior a esta corrección.
