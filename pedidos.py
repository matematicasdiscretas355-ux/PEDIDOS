"""Blueprint independiente para el módulo de Gestión de Pedidos."""

from datetime import datetime
from pathlib import Path
import sqlite3

from flask import Blueprint, current_app, redirect, render_template, request, url_for


pedidos_bp = Blueprint(
    "gestion_pedidos",
    __name__,
    url_prefix="/pedidos",
    template_folder="templates",
    static_folder="static",
    static_url_path="/pedidos/static",
)

ESTADOS_PEDIDO = ("Pendiente", "Asignado", "Entregado")


def inicializar_base_pedidos(app):
    """Crea la tabla del módulo en la base indicada por PEDIDOS_DB_PATH."""
    Path(app.config["PEDIDOS_DB_PATH"]).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(app.config["PEDIDOS_DB_PATH"]) as conexion:
        conexion.execute(
            """
            CREATE TABLE IF NOT EXISTS pedidos (
                id_pedido TEXT PRIMARY KEY,
                cliente TEXT NOT NULL,
                factura TEXT NOT NULL,
                peso REAL NOT NULL CHECK (peso > 0),
                volumen REAL NOT NULL CHECK (volumen > 0),
                zona_destino TEXT NOT NULL,
                fecha_ingreso TEXT NOT NULL,
                usuario_ingreso TEXT NOT NULL,
                fecha_actualizacion TEXT,
                usuario_actualizacion TEXT,
                estado TEXT NOT NULL DEFAULT 'Pendiente'
                    CHECK (estado IN ('Pendiente', 'Asignado', 'Entregado', 'Anulado'))
            )
            """
        )


def _conectar_pedidos():
    conexion = sqlite3.connect(current_app.config["PEDIDOS_DB_PATH"])
    conexion.row_factory = sqlite3.Row
    return conexion


def _ahora():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _listar_pedidos():
    conexion = _conectar_pedidos()
    try:
        return conexion.execute(
            "SELECT * FROM pedidos ORDER BY fecha_ingreso DESC, id_pedido"
        ).fetchall()
    finally:
        conexion.close()


def _pagina_pedidos(mensaje=None, tipo_mensaje="info", valores=None, error=None):
    return render_template(
        "pedidos.html",
        pedidos=_listar_pedidos(),
        estados=ESTADOS_PEDIDO,
        mensaje=mensaje,
        tipo_mensaje=tipo_mensaje,
        valores=valores or {},
        error=error,
    )


def _leer_datos_pedido(formulario):
    datos = {
        "id_pedido": formulario.get("id_pedido", "").strip(),
        "cliente": formulario.get("cliente", "").strip(),
        "factura": formulario.get("factura", "").strip(),
        "zona_destino": formulario.get("zona_destino", "").strip(),
        "usuario": formulario.get("usuario", "").strip(),
    }
    try:
        datos["peso"] = float(formulario.get("peso", ""))
        datos["volumen"] = float(formulario.get("volumen", ""))
    except ValueError:
        return datos, "Peso y volumen deben ser números."
    if not all(datos[campo] for campo in (
        "id_pedido", "cliente", "factura", "zona_destino", "usuario"
    )):
        return datos, "Completa todos los campos."
    if datos["peso"] <= 0 or datos["volumen"] <= 0:
        return datos, "Peso y volumen deben ser mayores que cero."
    return datos, None


@pedidos_bp.route("/", methods=["GET", "POST"], endpoint="listar")
def listar_pedidos():
    if request.method == "POST":
        datos, error = _leer_datos_pedido(request.form)
        if error:
            return _pagina_pedidos(
                "No se pudo registrar el pedido.", "error", request.form, error
            )
        conexion = _conectar_pedidos()
        try:
            conexion.execute(
                """
                INSERT INTO pedidos
                    (id_pedido, cliente, factura, peso, volumen, zona_destino,
                     fecha_ingreso, usuario_ingreso, estado)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pendiente')
                """,
                (
                    datos["id_pedido"], datos["cliente"], datos["factura"],
                    datos["peso"], datos["volumen"], datos["zona_destino"],
                    _ahora(), datos["usuario"],
                ),
            )
            conexion.commit()
        except sqlite3.IntegrityError as error_db:
            conexion.rollback()
            if "UNIQUE constraint failed" in str(error_db):
                mensaje = "Ya existe un pedido con ese ID."
            else:
                mensaje = "La base de datos rechazó los datos ingresados."
            return _pagina_pedidos(mensaje, "error", request.form)
        finally:
            conexion.close()
        return redirect(url_for("gestion_pedidos.listar", mensaje="Pedido registrado."))

    return _pagina_pedidos(
        mensaje=request.args.get("mensaje"),
        tipo_mensaje="success" if request.args.get("mensaje") else "info",
    )


@pedidos_bp.route("/<string:id_pedido>/editar", methods=["POST"], endpoint="editar")
def editar_pedido(id_pedido):
    datos, error = _leer_datos_pedido(request.form)
    if error:
        return redirect(url_for(
            "gestion_pedidos.listar",
            mensaje=f"No se guardaron los cambios: {error}",
        ))
    conexion = _conectar_pedidos()
    try:
        resultado = conexion.execute(
            """
            UPDATE pedidos
            SET cliente = ?, factura = ?, peso = ?, volumen = ?,
                zona_destino = ?, fecha_actualizacion = ?,
                usuario_actualizacion = ?
            WHERE id_pedido = ? AND estado = 'Pendiente'
            """,
            (
                datos["cliente"], datos["factura"], datos["peso"],
                datos["volumen"], datos["zona_destino"], _ahora(),
                datos["usuario"], id_pedido,
            ),
        )
        conexion.commit()
        mensaje = "Pedido actualizado." if resultado.rowcount else (
            "No se encontró un pedido pendiente con ese ID."
        )
    finally:
        conexion.close()
    return redirect(url_for("gestion_pedidos.listar", mensaje=mensaje))


@pedidos_bp.route("/<string:id_pedido>/estado", methods=["POST"], endpoint="cambiar_estado")
def cambiar_estado_pedido(id_pedido):
    estado = request.form.get("estado", "").strip()
    usuario = request.form.get("usuario_actualizacion", "").strip()
    if estado not in ESTADOS_PEDIDO or not usuario:
        return redirect(url_for(
            "gestion_pedidos.listar",
            mensaje="Selecciona un estado válido e indica quién hizo el cambio.",
        ))
    conexion = _conectar_pedidos()
    try:
        resultado = conexion.execute(
            """
            UPDATE pedidos
            SET estado = ?, fecha_actualizacion = ?, usuario_actualizacion = ?
            WHERE id_pedido = ? AND estado != 'Anulado'
            """,
            (estado, _ahora(), usuario, id_pedido),
        )
        conexion.commit()
        mensaje = "Estado actualizado." if resultado.rowcount else (
            "No se encontró el pedido o ya está anulado."
        )
    finally:
        conexion.close()
    return redirect(url_for("gestion_pedidos.listar", mensaje=mensaje))


@pedidos_bp.route("/<string:id_pedido>/anular", methods=["POST"], endpoint="anular")
def anular_pedido(id_pedido):
    usuario = request.form.get("usuario_actualizacion", "").strip()
    if not usuario:
        return redirect(url_for(
            "gestion_pedidos.listar",
            mensaje="Escribe el nombre del empleado que anula el pedido.",
        ))
    conexion = _conectar_pedidos()
    try:
        resultado = conexion.execute(
            """
            UPDATE pedidos
            SET estado = 'Anulado', fecha_actualizacion = ?,
                usuario_actualizacion = ?
            WHERE id_pedido = ? AND estado = 'Pendiente'
            """,
            (_ahora(), usuario, id_pedido),
        )
        conexion.commit()
        mensaje = "Pedido anulado; se conserva en el historial." if resultado.rowcount else (
            "Solo se pueden anular pedidos pendientes."
        )
    finally:
        conexion.close()
    return redirect(url_for("gestion_pedidos.listar", mensaje=mensaje))


@pedidos_bp.route("/<string:id_pedido>/eliminar", methods=["POST"], endpoint="eliminar")
def eliminar_pedido(id_pedido):
    conexion = _conectar_pedidos()
    try:
        resultado = conexion.execute(
            "DELETE FROM pedidos WHERE id_pedido = ? AND estado = 'Pendiente'",
            (id_pedido,),
        )
        conexion.commit()
        mensaje = "Pedido eliminado." if resultado.rowcount else (
            "Solo se pueden eliminar pedidos pendientes."
        )
    finally:
        conexion.close()
    return redirect(url_for("gestion_pedidos.listar", mensaje=mensaje))
