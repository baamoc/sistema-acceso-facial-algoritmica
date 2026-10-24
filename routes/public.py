from flask import Blueprint, Response, current_app, jsonify, render_template


# Agrupa las rutas públicas del sistema.
bp = Blueprint('public', __name__)


@bp.get('/')
def index():
    # Activa el registro de accesos al entrar a la vista pública.
    current_app.extensions['access'].set_recording_enabled(True)

    # Muestra la pantalla principal del reconocimiento facial.
    return render_template('public.html')


@bp.get('/video-feed')
def video_feed():
    # Envía al navegador el video MJPEG generado por CameraService.
    return Response(
        current_app.extensions['camera'].mjpeg(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


@bp.get('/api/status')
def status():
    # Devuelve en JSON el resultado actual del reconocimiento y errores de cámara.
    return jsonify(
        current_app.extensions['access'].status
        | {'camera_error': current_app.extensions['camera'].error}
    )