# Sistema web de acceso por reconocimiento facial

Aplicación local para el segundo parcial de Algorítmica Avanzada. Una sola aplicación Flask ofrece la pantalla pública y el área administrativa, usando **una única cámara** compartida.

## Instalación y arranque

Requiere Python 3.10+ y una webcam. En PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:FIRST_ADMIN_USER="admin"
$env:FIRST_ADMIN_PASSWORD="cambie-esta-clave"
python app.py
```

Abra `http://127.0.0.1:5000`. Las variables `FIRST_ADMIN_*` sólo crean el primer administrador cuando la base no tiene ninguno; luego pueden quitarse. Las contraseñas se guardan como hash de Werkzeug, nunca en texto plano. Si se desea otra clave de sesión, defina `SECRET_KEY`.

Al primer inicio `FaceService` descarga en `face_models/` los modelos ONNX oficiales de OpenCV Zoo. La descarga requiere conexión; se reutilizan luego localmente. No se versionan ni modelos, ni fotografías, ni la base SQLite.

## Uso

La página inicial es exclusivamente pública: video, resultado, nombre, CI, vigencia y número de accesos. El único enlace es **Administrador**. Después de autenticarse, complete el formulario de alta mientras hay exactamente un rostro frente a la cámara y pulse “Capturar rostro y registrar”. La edición permite recapturar opcionalmente. Desactivar hace baja lógica: conserva cliente e historial.

## Arquitectura

- `services/camera_service.py`: único propietario de `cv2.VideoCapture(0)`. Conserva `raw_frame` sin overlays para alta/recaptura y `display_frame` procesado para el streaming público; nunca abre una segunda cámara.
- `services/face_service.py`: YuNet detecta rostro y sus puntos; SFace alinea y transforma el rostro en un **embedding**, un vector numérico que resume rasgos faciales. Un `RLock` serializa la inferencia sobre ambos modelos entre el hilo de cámara y las peticiones administrativas.
- `services/access_service.py`: compara el embedding actual con los almacenados usando similitud coseno, aplica vigencia y registra historial.
- `models/database.py`: SQLite y sus tres tablas: `administradores`, `clientes`, `accesos`.
- `routes/`: rutas pública y administrativa separadas.

El umbral de detección es `0.8` y el de similitud coseno `0.363`, configurables con `DETECTION_THRESHOLD` y `COSINE_THRESHOLD`. Una similitud igual o mayor al umbral identifica al cliente. Son valores iniciales; iluminación, cámara y población pueden exigir calibración.

## Vigencia y contador

La fecha local (`date.today()`) se compara como sigue: inactivo siempre deniega; antes de `fecha_inicio` deniega; después de `fecha_fin` deniega; `fecha_fin` vacío significa indefinido y permite desde el inicio. Cada resultado explica el motivo.

El sistema no cuenta cuadros ni usa la última identificación como prueba de salida. Después del primer reconocimiento el encuentro queda activo aunque SFace pierda temporalmente la identidad o baje la similitud. YuNet debe observar **cero rostros de forma continua** durante `ABSENCE_SECONDS` (por defecto 4 s) para cerrar el encuentro y permitir otro acceso. Si YuNet sigue viendo una cara, o vuelve a verla antes del plazo, no se rearma el contador. El total mostrado cuenta sólo eventos permitidos, y el historial conserva permitidos y denegados.

El registro de eventos se habilita al abrir la vista pública y se suspende al entrar en cualquier ruta administrativa. La cámara y el reconocimiento siguen compartidos y activos para permitir capturas. Al volver a la vista pública se limpia la presencia, de modo que el siguiente reconocimiento inicia un intento nuevo. Cada evento guarda `fecha_hora` con la hora local del sistema y su desplazamiento UTC en formato ISO 8601; así el historial conserva una referencia temporal inequívoca.

## Pruebas

Instale las dependencias de desarrollo y ejecute pytest:

```powershell
pip install -r requirements-dev.txt
python -m pytest -q
```

Las pruebas usan archivos SQLite reales temporales y comprueban vigencia, hash/login, modos público/administrativo, presencia, hora local, separación entre cuadros crudo/visual, CI público y serialización concurrente de YuNet/SFace. La demostración posterior a cambios de cámara o registro debe repetirse con webcam física.

## Limitaciones conocidas

Es una solución local académica: no implementa detección anti-suplantación, cifrado de embeddings, múltiples cámaras ni tolerancia a mala iluminación. La identificación compara linealmente todos los clientes, apropiada para una lista pequeña.
