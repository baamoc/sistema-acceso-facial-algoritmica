import atexit
from flask import Flask
from config import Config
from models.database import init_db, get_db
from services.camera_service import CameraService
from services.face_service import FaceService
from services.access_service import AccessService

def create_app(test_config=None, start_camera=True):
 app=Flask(__name__); app.config.from_object(Config)
 if test_config: app.config.update(test_config)
 app.config['FACE_DIR'].mkdir(exist_ok=True); app.config['MODEL_DIR'].mkdir(exist_ok=True)
 init_db(app)
 face=app.config.get('FACE_SERVICE') or FaceService(app.config['MODEL_DIR'],app.config['DETECTION_THRESHOLD'],app.config['COSINE_THRESHOLD'])
 access=AccessService(app,face,app.config['ABSENCE_SECONDS'])
 camera=CameraService(app.config['CAMERA_INDEX']); camera.processor=access.process
 app.extensions.update(camera=camera,face=face,access=access)
 app.extensions['db_count']=lambda cid: get_db().execute("SELECT COUNT(*) FROM accesos WHERE cliente_id=? AND resultado='ACCESO PERMITIDO'",(cid,)).fetchone()[0]
 if start_camera: camera.start(); atexit.register(camera.stop)
 from routes.public import bp as public_bp
 from routes.admin import bp as admin_bp
 app.register_blueprint(public_bp); app.register_blueprint(admin_bp)
 return app

if __name__=='__main__':
 app=create_app()
 print('Abra http://127.0.0.1:5000  |  Para crear el primer admin: configure FIRST_ADMIN_USER y FIRST_ADMIN_PASSWORD antes del primer inicio.')
 app.run(host='127.0.0.1',port=5000,debug=False,threaded=True)
