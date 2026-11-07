# Traductor web de texto

Aplicación académica que captura texto visible en la pantalla, lo reconoce mediante OCR, lo traduce al idioma seleccionado y permite escucharlo desde el navegador.

## Flujo

```text
CAPTURA
   ↓
Pillow / ImageGrab
   ↓
Tesseract OCR
   ↓
TEXTO ORIGINAL
   ↓
IDIOMA DESTINO
   ↓
deep-translator
   ↓
TEXTO TRADUCIDO
   ↓
gTTS
   ↓
AUDIO DEL NAVEGADOR
```

## Instalación

Requiere Python 3.13, Tesseract 5.4 y los datos OCR `spa` y `eng`. Desde esta carpeta:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Tesseract puede instalarse en Windows con:

```powershell
winget install --id UB-Mannheim.TesseractOCR --exact
```

Preparar los datos OCR de inglés y español:

```powershell
$datosOcr = "$env:LOCALAPPDATA\Tesseract-OCR\tessdata"
New-Item -ItemType Directory -Force $datosOcr
Copy-Item "C:\Program Files\Tesseract-OCR\tessdata\eng.traineddata" $datosOcr
Invoke-WebRequest "https://github.com/tesseract-ocr/tessdata_fast/raw/refs/heads/main/spa.traineddata" -OutFile "$datosOcr\spa.traineddata"
```

Las rutas de Tesseract y sus idiomas están declaradas juntas al inicio de `app.py`.

## Ejecución

```powershell
.\.venv\Scripts\python.exe app.py
```

Abrir: <http://127.0.0.1:5002>

## Librerías

- **Flask:** muestra la página y atiende los botones.
- **Pillow / ImageGrab:** captura las pantallas visibles.
- **Tesseract y pytesseract:** convierten las letras de la captura en texto digital.
- **deep-translator:** traduce el texto mediante GoogleTranslator.
- **gTTS:** genera el MP3 con la voz del idioma elegido.
- **Navegador:** recibe y reproduce el MP3.

La palabra `Palysound` del requisito se interpretó como `playsound`. playsound fue validado con Python 3.13, pero no se utiliza en esta versión web porque reproduciría el audio en el servidor. gTTS genera la voz y el navegador la reproduce donde corresponde.

## Limitaciones

- Al pulsar **CAPTURAR TEXTO**, hay dos segundos para cambiar a la ventana que contiene el texto.
- El OCR funciona mejor con texto grande, nítido y con buen contraste.
- La captura toma todas las pantallas y no permite seleccionar una región en esta V1.
- La traducción y la voz requieren Internet y dependen de servicios externos.
- Google puede limitar temporalmente las solicitudes de traducción.
- Debe ejecutarse localmente en un equipo Windows con escritorio visible.

## Guía para defender el proyecto

Este es un traductor web sencillo desarrollado con Flask. Cuando el usuario pulsa **CAPTURAR TEXTO**, tiene dos segundos para mostrar otra ventana. Pillow toma una captura de la pantalla y pytesseract la envía a Tesseract. Tesseract realiza OCR, que significa reconocimiento óptico de caracteres: convierte las letras de una imagen en texto digital y el resultado aparece en **TEXTO ORIGINAL**.

Después se elige uno de los 23 idiomas y se pulsa **TRADUCIR**. deep-translator detecta el idioma original, solicita la traducción y Flask vuelve a mostrar la misma página con el resultado debajo, en **TEXTO TRADUCIDO**.

Finalmente, **ESCUCHAR** envía exactamente ese resultado a la ruta de audio. gTTS genera un MP3 en memoria y Flask lo devuelve al navegador, que lo reproduce. No usamos base de datos, usuarios ni una API propia separada. Cada botón representa directamente una etapa del flujo y, si un servicio falla, se muestra un mensaje sin cerrar la aplicación.
