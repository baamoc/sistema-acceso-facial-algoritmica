import tempfile
from pathlib import Path
import numpy as np
from werkzeug.security import generate_password_hash
from app import create_app
from models.database import close_db, get_db

class NoFace:
 ready=False; error='Prueba sin modelos'

def build():
 folder=tempfile.TemporaryDirectory(); root=Path(folder.name)
 app=create_app({'TESTING':True,'DATABASE':root/'real.sqlite','FACE_DIR':root/'faces','MODEL_DIR':root/'models','FACE_SERVICE':NoFace(),'ABSENCE_SECONDS':4},start_camera=False)
 return app,folder
def insert(app,name,ci,start='2020-01-01',end=None,active=1):
 with app.app_context():
  db=get_db(); cur=db.execute('INSERT INTO clientes(nombre_completo,ci,fecha_inicio,fecha_fin,activo,face_embedding) VALUES(?,?,?,?,?,?)',(name,ci,start,end,active,np.array([1,0],np.float32).tobytes())); db.commit(); return cur.lastrowid
def test_validity_rules_use_real_sqlite():
 app,tmp=build()
 try:
  ids=[insert(app,'Vigente','1'),insert(app,'Futuro','2','2999-01-01'),insert(app,'Vencido','3','2020-01-01','2020-01-02'),insert(app,'Inactivo','4',active=0),insert(app,'Indefinido','5')]
  with app.app_context():
   rows=get_db().execute('SELECT * FROM clientes ORDER BY id').fetchall(); service=app.extensions['access']
   assert [service.evaluate(x)[0] for x in rows]==['ACCESO PERMITIDO','ACCESO DENEGADO','ACCESO DENEGADO','ACCESO DENEGADO','ACCESO PERMITIDO']
 finally:
  with app.app_context(): close_db()
  tmp.cleanup()
def test_presence_counts_once_then_again_after_absence_in_real_db():
 app,tmp=build()
 try:
  cid=insert(app,'Ana','9')
  with app.app_context():
   client=get_db().execute('SELECT * FROM clientes WHERE id=?',(cid,)).fetchone(); s=app.extensions['access']
   s.handle_recognized(client,10); s.handle_recognized(client,11); s.handle_recognized(client,13.9); s.handle_recognized(client,18)
   assert get_db().execute('SELECT COUNT(*) FROM accesos WHERE cliente_id=?',(cid,)).fetchone()[0]==2
 finally:
  with app.app_context(): close_db()
  tmp.cleanup()
def test_login_password_hash_and_persistence():
 app,tmp=build()
 try:
  with app.app_context():
   db=get_db(); db.execute('INSERT INTO administradores(usuario,password_hash) VALUES (?,?)',('admin',generate_password_hash('secreta'))); db.commit()
   assert db.execute('SELECT password_hash FROM administradores').fetchone()[0] != 'secreta'
  c=app.test_client(); assert c.post('/admin/login',data={'usuario':'admin','password':'mala'}).status_code==200
  assert c.post('/admin/login',data={'usuario':'admin','password':'secreta'}).status_code==302
 finally:
  with app.app_context(): close_db()
  tmp.cleanup()
