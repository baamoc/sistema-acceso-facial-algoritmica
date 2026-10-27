# Sistema de detección de fatiga

Prototipo académico que usa una webcam para observar tres señales asociadas con
fatiga: ojos cerrados, apertura prolongada de la boca y cabeceos. Flask muestra
el video, las métricas, contadores, alertas y un historial guardado solamente en
memoria.

El sistema no “sabe” si una persona está dormida. Detecta señales visibles y las
combina mediante reglas temporales. No es un sistema certificado para seguridad
vehicular.

## Instalación

Requiere Python 3.13 y una webcam. En PowerShell, desde esta carpeta:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

El archivo oficial `models/face_landmarker.task` debe existir antes de iniciar.

## Ejecución

```powershell
.\.venv\Scripts\python.exe app.py
```

Abra `http://127.0.0.1:5001`. Durante los primeros 3.5 segundos con el rostro
visible, mire al frente con los ojos abiertos y la boca cerrada.

La prueba corta de las reglas no necesita webcam:

```powershell
.\.venv\Scripts\python.exe app.py --self-test
```

## Cómo funciona

**Ojos:** se calcula EAR, la apertura vertical del ojo dividida entre su ancho.
Un valor bajo durante 4 segundos genera un solo evento y `ALERTA DE SUEÑO`.
Abrir los ojos rearma la detección.

**Bostezo:** se calcula MAR, la apertura vertical de la boca dividida entre su
ancho. Una apertura grande durante 1 segundo cuenta un bostezo. La boca debe
cerrarse antes de contar otro. Tres bostezos generan `ALERTA DE CANSANCIO`.

**Cabeceo:** se mide la posición vertical de la nariz respecto a los ojos y se
normaliza con la altura del rostro. Una caída respecto a la posición calibrada,
seguida de una recuperación, cuenta un cabeceo. Tres generan
`ALERTA: DETENER EL VEHÍCULO`.

## Parámetros principales

Las constantes están al inicio de `app.py`. Las más importantes son:

- `EYE_CLOSED_SECONDS`: tiempo para alerta de ojos cerrados.
- `EYE_CLOSED_RATIO`: proporción del EAR calibrado considerada cierre.
- `YAWN_MIN_SECONDS`: duración mínima de apertura de boca.
- `YAWNS_FOR_ALERT`: bostezos necesarios para alerta.
- `HEAD_DROP_DELTA`: caída necesaria para iniciar un cabeceo.
- `HEAD_NOD_COOLDOWN`: pausa entre cabeceos.
- `HEAD_NODS_FOR_ALERT`: cabeceos necesarios para alerta.

Estos valores son parámetros de calibración y pueden requerir ajustes según la
cámara, iluminación, distancia y persona.

## Limitaciones

- Gafas, poca luz, oclusiones y movimientos fuera de cámara reducen la precisión.
- Hablar con la boca muy abierta puede parecer un bostezo.
- La medida sencilla de cabeza puede reaccionar a movimientos corporales amplios.
- No detecta intención, cansancio interno ni sueño de forma clínica.
- El historial desaparece al cerrar el programa y no se guardan imágenes.

## GUÍA PARA DEFENDER EL PROYECTO

“La cámara entrega imágenes a OpenCV. MediaPipe localiza puntos del rostro, pero
no reconoce a la persona. Con esos puntos calculamos tres medidas sencillas: la
apertura de los ojos respecto a su ancho, la apertura de la boca respecto a su
ancho y la posición vertical normalizada de la nariz. Al iniciar tomamos medianas
durante 3.5 segundos para conocer el rostro en posición normal. Después comparamos
cada medida con umbrales configurables. También usamos tiempo y estados para no
contar cada cuadro: un cierre continuo produce un solo evento, un bostezo debe
durar un segundo y cerrar antes del siguiente, y un cabeceo requiere caída y
recuperación. Flask muestra el video y consulta el estado del mismo programa para
actualizar contadores, alertas e historial. Todo se procesa localmente y los
eventos viven únicamente en memoria. Es un prototipo académico de señales de
fatiga, no un dispositivo certificado de seguridad.”
