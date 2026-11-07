"""Traductor web sencillo con captura de pantalla, OCR, traducción y voz."""

import os
import time
from io import BytesIO
from pathlib import Path

import pytesseract
from deep_translator import GoogleTranslator
from flask import Flask, jsonify, render_template, request, send_file
from gtts import gTTS
from PIL import ImageGrab


# CONFIGURACIÓN
PUERTO_APLICACION = 5002
SEGUNDOS_ANTES_CAPTURA = 2
IDIOMAS_OCR = "spa+eng"
RUTA_TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
RUTA_DATOS_TESSERACT = Path(os.environ.get("LOCALAPPDATA", "")) / "Tesseract-OCR" / "tessdata"

# Un solo diccionario alimenta el ComboBox, la traducción y la voz.
IDIOMAS = {
    "Español": "es",
    "Inglés": "en",
    "Portugués": "pt",
    "Francés": "fr",
    "Italiano": "it",
    "Alemán": "de",
    "Japonés": "ja",
    "Coreano": "ko",
    "Chino": "zh-CN",
    "Ruso": "ru",
    "Árabe": "ar",
    "Hindi": "hi",
    "Holandés": "nl",
    "Sueco": "sv",
    "Polaco": "pl",
    "Turco": "tr",
    "Griego": "el",
    "Checo": "cs",
    "Rumano": "ro",
    "Indonesio": "id",
    "Ucraniano": "uk",
    "Vietnamita": "vi",
    "Danés": "da",
}


app = Flask(__name__)

# pytesseract queda configurado una sola vez al iniciar el programa.
pytesseract.pytesseract.tesseract_cmd = str(RUTA_TESSERACT)
os.environ["TESSDATA_PREFIX"] = str(RUTA_DATOS_TESSERACT)


@app.get("/")
def inicio():
    """Muestra la página principal vacía."""
    return render_template(
        "index.html",
        idiomas=IDIOMAS,
        texto_original="",
        texto_traducido="",
        idioma_destino="Inglés",
        mensaje="Listo para capturar texto.",
    )


@app.post("/capturar")
def capturar_texto():
    """Espera dos segundos, captura la pantalla y aplica OCR."""
    idioma_destino = request.form.get("idioma_destino", "Inglés")
    if idioma_destino not in IDIOMAS:
        idioma_destino = "Inglés"

    try:
        time.sleep(SEGUNDOS_ANTES_CAPTURA)
        captura = ImageGrab.grab(all_screens=True)
        texto_original = pytesseract.image_to_string(captura, lang=IDIOMAS_OCR).strip()
        mensaje = "Texto capturado correctamente."
        if not texto_original:
            mensaje = "No se encontró texto en la captura."
    except Exception as error:
        print(f"Error de OCR: {error}")
        texto_original = ""
        mensaje = "No se pudo reconocer texto."

    return render_template(
        "index.html",
        idiomas=IDIOMAS,
        texto_original=texto_original,
        texto_traducido="",
        idioma_destino=idioma_destino,
        mensaje=mensaje,
    )


@app.post("/traducir")
def traducir_texto():
    """Traduce el texto original al idioma elegido."""
    texto_original = request.form.get("texto_original", "").strip()
    idioma_destino = request.form.get("idioma_destino", "Inglés")
    texto_traducido = ""

    if idioma_destino not in IDIOMAS:
        idioma_destino = "Inglés"

    if not texto_original:
        mensaje = "No hay texto para traducir."
    else:
        try:
            codigo_idioma = IDIOMAS[idioma_destino]
            texto_traducido = GoogleTranslator(
                source="auto",
                target=codigo_idioma,
            ).translate(texto_original)
            mensaje = f"Texto traducido a {idioma_destino}."
        except Exception as error:
            print(f"Error de traducción: {error}")
            mensaje = "No se pudo realizar la traducción. Revise su conexión."

    return render_template(
        "index.html",
        idiomas=IDIOMAS,
        texto_original=texto_original,
        texto_traducido=texto_traducido,
        idioma_destino=idioma_destino,
        mensaje=mensaje,
    )


@app.post("/escuchar")
def generar_audio():
    """Convierte exactamente el texto traducido en un MP3 para el navegador."""
    texto_traducido = request.form.get("texto_traducido", "").strip()
    idioma_destino = request.form.get("idioma_destino", "Español")

    if not texto_traducido:
        return jsonify(error="No hay texto traducido para escuchar."), 400
    if idioma_destino not in IDIOMAS:
        return jsonify(error="El idioma seleccionado no es válido."), 400

    try:
        audio = BytesIO()
        gTTS(text=texto_traducido, lang=IDIOMAS[idioma_destino]).write_to_fp(audio)
        audio.seek(0)
        return send_file(
            audio,
            mimetype="audio/mpeg",
            download_name="traduccion.mp3",
        )
    except Exception as error:
        print(f"Error de audio: {error}")
        return jsonify(error="No se pudo generar el audio. Revise su conexión."), 503


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=PUERTO_APLICACION, debug=False)
