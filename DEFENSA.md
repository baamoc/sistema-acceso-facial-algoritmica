# Guía para defensa oral

**¿Qué es YuNet?** Es el detector facial ligero de OpenCV. Localiza el rectángulo del rostro y puntos faciales en cada cuadro.

**¿Qué es SFace?** Es el modelo de reconocimiento de OpenCV. Recibe el rostro alineado y genera un vector de características.

**¿Qué es un embedding?** Un arreglo de números que representa rasgos del rostro. No es una foto; se guarda como BLOB `float32` en SQLite para comparar rostros.

**¿Cómo se reconoce una persona?** YuNet detecta, SFace genera embedding y el sistema calcula similitud coseno frente a cada embedding registrado. Si el mayor valor llega a `COSINE_THRESHOLD`, se toma ese cliente.

**¿Qué representa el umbral?** La similitud mínima aceptable. Un valor muy bajo puede confundir personas; uno alto puede rechazar a la misma persona. El valor inicial es 0.363 y es configurable.

**¿Por qué una sola cámara?** `CameraService` es el único que llama `cv2.VideoCapture`. Mantiene el último cuadro para streaming y altas, evitando que dos procesos disputen la webcam.

**¿Cómo se evita contar cada frame?** Se conserva la hora monotónica de la última vez que se vio cada cliente. Un evento se inserta sólo si pasó `ABSENCE_SECONDS` desde esa presencia. El valor inicial es cuatro segundos.

**¿Por qué usar baja lógica?** Desactivar no borra al cliente ni sus registros; permite auditoría y reactivación.

**¿Cómo funcionan fechas?** Se usa la fecha local: antes de inicio deniega, entre inicio y fin permite, después de fin deniega. Un inactivo siempre deniega.

**¿Cómo se representa acceso indefinido?** `fecha_fin` es `NULL`; desde `fecha_inicio` el resultado es permitido y la UI muestra “Indefinido”.

**¿Por qué historial y no sólo contador?** `accesos` guarda cuándo, resultado y motivo. El total permitido se calcula desde esos eventos y el administrador puede auditar denegaciones.

**¿Por qué SQLite?** No necesita servidor externo, persiste en archivo y es suficiente para una aplicación local universitaria.

**¿Por qué Flask?** Es pequeño, claro y permite servir página pública, sesión administrativa, video MJPEG y rutas de datos en una sola aplicación Python.

**¿Dónde se almacenan contraseñas?** En `administradores.password_hash`, generado y verificado por Werkzeug. Nunca se guarda la contraseña original.

**¿Qué ocurre con un rostro desconocido?** La pantalla muestra `DESCONOCIDO`; no se permite ni se vincula un evento a un cliente inexistente.
