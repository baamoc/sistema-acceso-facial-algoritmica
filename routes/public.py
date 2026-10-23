from flask import Blueprint, Response, current_app, jsonify, render_template

bp=Blueprint('public',__name__)
@bp.get('/')
def index():
 current_app.extensions['access'].set_recording_enabled(True)
 return render_template('public.html')
@bp.get('/video-feed')
def video_feed(): return Response(current_app.extensions['camera'].mjpeg(), mimetype='multipart/x-mixed-replace; boundary=frame')
@bp.get('/api/status')
def status(): return jsonify(current_app.extensions['access'].status | {'camera_error':current_app.extensions['camera'].error})
