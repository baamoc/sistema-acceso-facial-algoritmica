import sqlite3
from flask import current_app, g
from werkzeug.security import generate_password_hash


# Estructura de las tres tablas principales del sistema.
SCHEMA = '''
CREATE TABLE IF NOT EXISTS administradores (
 id INTEGER PRIMARY KEY AUTOINCREMENT, usuario TEXT NOT NULL UNIQUE,
 password_hash TEXT NOT NULL, activo INTEGER NOT NULL DEFAULT 1,
 fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS clientes (
 id INTEGER PRIMARY KEY AUTOINCREMENT, nombre_completo TEXT NOT NULL, ci TEXT NOT NULL UNIQUE,
 fecha_inicio TEXT NOT NULL, fecha_fin TEXT, activo INTEGER NOT NULL DEFAULT 1,
 foto_path TEXT, face_embedding BLOB NOT NULL, fecha_registro TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS accesos (
 id INTEGER PRIMARY KEY AUTOINCREMENT, cliente_id INTEGER NOT NULL,
 fecha_hora TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, resultado TEXT NOT NULL, motivo TEXT NOT NULL,
 FOREIGN KEY(cliente_id) REFERENCES clientes(id)
);

CREATE INDEX IF NOT EXISTS idx_accesos_cliente ON accesos(cliente_id);
'''


def get_db():
    # Abre la conexión SQLite y la reutiliza durante la petición actual.
    if 'db' not in g:
        db = sqlite3.connect(current_app.config['DATABASE'])
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys = ON')
        g.db = db

    return g.db


def close_db(_=None):
    # Cierra la conexión a la base de datos cuando termina la petición.
    db = g.pop('db', None)

    if db:
        db.close()


def init_db(app):
    # Crea la base y las tablas si todavía no existen.
    app.config['DATABASE'].parent.mkdir(exist_ok=True)

    app.teardown_appcontext(close_db)

    with app.app_context():
        db = get_db()
        db.executescript(SCHEMA)
        db.commit()

        # Crea el primer administrador si fue configurado y aún no existe ninguno.
        u = app.config.get('FIRST_ADMIN_USER')
        p = app.config.get('FIRST_ADMIN_PASSWORD')

        if u and p and not db.execute(
            'SELECT 1 FROM administradores LIMIT 1'
        ).fetchone():

            # La contraseña se guarda como hash, no como texto plano.
            db.execute(
                'INSERT INTO administradores(usuario,password_hash) VALUES (?,?)',
                (u, generate_password_hash(p))
            )

            db.commit()