from functools import wraps
from pathlib import Path
from datetime import datetime

import cv2, numpy as np

from flask import (
    Blueprint, current_app, flash, redirect,
    render_template, request, session, url_for
)

from werkzeug.security import check_password_hash, generate_password_hash
from models.database import get_db


# Todas las rutas de este archivo empiezan con /admin.
bp = Blueprint('admin', __name__, url_prefix='/admin')


@bp.before_request
def suspend_access_recording():
    # Mientras estamos en administración no registramos accesos de la cámara.
    current_app.extensions['access'].set_recording_enabled(False)


def login_required(fn):
    # Protege las rutas administrativas: si no hay sesión, manda al login.
    @wraps(fn)
    def wrapped(*a, **kw):
        if not session.get('admin_id'):
            return redirect(url_for('admin.login'))

        return fn(*a, **kw)

    return wrapped


def client_count(client_id):
    # Cuenta únicamente los accesos permitidos de un cliente.
    return get_db().execute(
        """
        SELECT COUNT(*)
        FROM accesos
        WHERE cliente_id=?
        AND resultado='ACCESO PERMITIDO'
        """,
        (client_id,)
    ).fetchone()[0]


def validity(c):
    # Usa AccessService para saber si el cliente está vigente.
    result, reason = current_app.extensions['access'].evaluate(c)

    return 'Vigente' if result == 'ACCESO PERMITIDO' else reason


@bp.route('/login', methods=['GET', 'POST'])
def login():
    # Busca al administrador y verifica su contraseña mediante el hash.
    if request.method == 'POST':
        row = get_db().execute(
            'SELECT * FROM administradores WHERE usuario=?',
            (request.form['usuario'],)
        ).fetchone()

        if (
            row
            and row['activo']
            and check_password_hash(
                row['password_hash'],
                request.form['password']
            )
        ):
            session['admin_id'] = row['id']
            return redirect(url_for('admin.dashboard'))

        flash('Usuario o contraseña incorrectos.', 'error')

    return render_template('login.html')


@bp.get('/logout')
def logout():
    # Cierra la sesión administrativa.
    session.clear()
    return redirect(url_for('public.index'))


@bp.get('/')
@login_required
def dashboard():
    # Muestra los clientes y permite buscarlos por nombre o CI.
    q = request.args.get('q', '').strip()
    db = get_db()

    sql = 'SELECT * FROM clientes'
    args = []

    if q:
        sql += ' WHERE nombre_completo LIKE ? OR ci LIKE ?'
        args = [f'%{q}%', f'%{q}%']

    clients = db.execute(
        sql + ' ORDER BY id DESC',
        args
    ).fetchall()

    return render_template(
        'admin.html',
        clients=clients,
        q=q,
        count=client_count,
        validity=validity
    )


def capture_embedding():
    # Toma el frame limpio, exige un solo rostro y genera su embedding.
    camera = current_app.extensions['camera']
    face = current_app.extensions['face']

    frame = camera.get_raw_frame()

    if frame is None:
        raise ValueError('La cámara aún no entregó una imagen.')

    if not face.ready:
        raise ValueError(
            face.error or 'Modelos faciales no listos.'
        )

    faces = face.detect(frame)

    # Para registrar correctamente debe aparecer exactamente una persona.
    if len(faces) != 1:
        raise ValueError(
            'Debe haber exactamente un rostro visible para registrar.'
        )

    detected = faces[0]

    # SFace convierte el rostro detectado en su vector numérico.
    emb = face.embedding(frame, detected)

    # Recorta la cara para guardar también una foto de referencia.
    x, y, w, h = map(int, detected[:4])
    h0, w0 = frame.shape[:2]

    x = max(x, 0)
    y = max(y, 0)

    crop = frame[
        y:min(y + h, h0),
        x:min(x + w, w0)
    ]

    if crop.size == 0:
        raise ValueError('No se pudo recortar el rostro.')

    return emb, crop


def save_client(client_id=None):
    # Guarda un cliente nuevo o modifica uno existente.
    f = request.form

    name = f.get('nombre_completo', '').strip()
    ci = f.get('ci', '').strip()
    start = f.get('fecha_inicio')
    end = f.get('fecha_fin') or None

    if not name or not ci or not start:
        raise ValueError(
            'Nombre, CI y fecha de inicio son obligatorios.'
        )

    # Valida las fechas de vigencia.
    try:
        datetime.strptime(start, '%Y-%m-%d')

        if end and end < start:
            raise ValueError(
                'La fecha final no puede ser anterior al inicio.'
            )

    except ValueError as e:
        raise ValueError(str(e))

    db = get_db()

    # Si client_id existe estamos editando; si no, estamos creando.
    old = (
        db.execute(
            'SELECT * FROM clientes WHERE id=?',
            (client_id,)
        ).fetchone()
        if client_id
        else None
    )

    emb = None
    photo = None

    # Si el administrador pidió capturar, obtiene nuevo rostro y embedding.
    if f.get('capturar') == '1':
        emb, photo = capture_embedding()

    # Un cliente nuevo obligatoriamente necesita un rostro.
    if not old and emb is None:
        raise ValueError(
            'Para un alta debe capturar el rostro con la cámara.'
        )

    if old:
        # Modificación: conserva la cara anterior si no se recapturó.
        photo_path = old['foto_path']
        embedding = old['face_embedding']

        if emb is not None:
            photo_path = f'cliente_{client_id}.jpg'

            cv2.imwrite(
                str(
                    Path(current_app.config['FACE_DIR'])
                    / photo_path
                ),
                photo
            )

            embedding = emb.tobytes()

        db.execute(
            """
            UPDATE clientes
            SET nombre_completo=?, ci=?, fecha_inicio=?,
                fecha_fin=?, activo=?, foto_path=?,
                face_embedding=?
            WHERE id=?
            """,
            (
                name,
                ci,
                start,
                end,
                1 if f.get('activo') else 0,
                photo_path,
                embedding,
                client_id
            )
        )

    else:
        # Alta: guarda los datos y el embedding del nuevo cliente.
        cur = db.execute(
            """
            INSERT INTO clientes(
                nombre_completo, ci, fecha_inicio,
                fecha_fin, activo, foto_path,
                face_embedding
            )
            VALUES(?,?,?,?,?,?,?)
            """,
            (
                name,
                ci,
                start,
                end,
                1 if f.get('activo') else 0,
                'pendiente.jpg',
                emb.tobytes()
            )
        )

        client_id = cur.lastrowid
        photo_path = f'cliente_{client_id}.jpg'

        cv2.imwrite(
            str(
                Path(current_app.config['FACE_DIR'])
                / photo_path
            ),
            photo
        )

        db.execute(
            'UPDATE clientes SET foto_path=? WHERE id=?',
            (photo_path, client_id)
        )

    db.commit()


@bp.post('/clients')
@login_required
def create_client():
    # Crea un nuevo cliente.
    try:
        save_client()
        flash('Cliente registrado correctamente.', 'ok')

    except Exception as exc:
        get_db().rollback()
        flash(str(exc), 'error')

    return redirect(url_for('admin.dashboard'))


@bp.post('/clients/<int:client_id>')
@login_required
def edit_client(client_id):
    # Modifica un cliente existente.
    try:
        save_client(client_id)
        flash('Cliente actualizado.', 'ok')

    except Exception as exc:
        get_db().rollback()
        flash(str(exc), 'error')

    return redirect(url_for('admin.dashboard'))


@bp.post('/clients/<int:client_id>/toggle')
@login_required
def toggle(client_id):
    # Activa o desactiva al cliente sin eliminarlo físicamente.
    db = get_db()

    db.execute(
        """
        UPDATE clientes
        SET activo=CASE activo
            WHEN 1 THEN 0
            ELSE 1
        END
        WHERE id=?
        """,
        (client_id,)
    )

    db.commit()

    flash('Estado del cliente actualizado.', 'ok')

    return redirect(url_for('admin.dashboard'))


@bp.get('/clients/<int:client_id>/history')
@login_required
def history(client_id):
    # Muestra el historial de accesos de un cliente.
    db = get_db()

    client = db.execute(
        'SELECT * FROM clientes WHERE id=?',
        (client_id,)
    ).fetchone()

    if not client:
        return ('Cliente no encontrado', 404)

    events = db.execute(
        """
        SELECT *
        FROM accesos
        WHERE cliente_id=?
        ORDER BY id DESC
        """,
        (client_id,)
    ).fetchall()

    return render_template(
        'history.html',
        client=client,
        events=events,
        count=client_count(client_id)
    )