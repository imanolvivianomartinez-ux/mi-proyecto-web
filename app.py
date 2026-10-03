import os
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
from datetime import datetime

app = Flask(__name__)
app.secret_key = "COPA_MUNDIAL_2026_CLAVE"

URI = "mongodb+srv://vimi090703hmcvrma5_db_user:qgb4fQjc7xIyy0UB@cluster0.nwwzftq.mongodb.net/"
client = MongoClient(URI)
db = client["Copamundial2026"]
usuarios, partidos, equipos, apuestas, noticias, clasificados, eliminados = (
    db[n] for n in ("usuarios", "partidos", "equipos", "apuestas", "noticias", "clasificados", "eliminados")
)
administradores = db["Administrador"]
jugadores = db["jugadores"]


# ---------- UTILIDADES ----------

def buscar(col, id):
    try:
        return col.find_one({"_id": ObjectId(id)})
    except Exception:
        return None


def listar(col, campo, orden=1):
    return list(col.find().sort(campo, orden))


def convertir_id(documentos):
    """Convierte el _id de ObjectId a texto para poder usarlo en url_for()."""
    for documento in documentos:
        documento["_id"] = str(documento["_id"])
    return documentos


def solo_admin(f):
    @wraps(f)
    def envoltura(*args, **kwargs):
        if session.get("rol") != "admin":
            flash("Acceso solo para administradores.", "danger")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return envoltura


def autenticar(coleccion, rol):
    """Valida correo y contraseña en la colección indicada."""
    u = coleccion.find_one({"correo": request.form.get("correo", "").strip().lower()})
    if not u or not check_password_hash(u["password"], request.form.get("password", "")):
        flash("Correo o contraseña incorrectos.", "danger")
        return None
    session.update(usuario_id=str(u["_id"]), nombre=u["nombre"], correo=u["correo"], rol=rol)
    flash(f"Bienvenido, {u['nombre']}.", "success")
    return u


# ---------- LOGIN OBLIGATORIO ----------

PUBLICAS = {"login", "registro", "admin_login", "static"}


@app.before_request
def exigir_sesion():
    if request.endpoint and request.endpoint not in PUBLICAS and "usuario_id" not in session:
        flash("Inicia sesión para ver esta página.", "warning")
        return redirect(url_for("admin_login" if request.endpoint == "admin_panel" else "login"))


# ---------- INICIO ----------

@app.route("/")
def index():
    return render_template(
        "index.html",
        partidos=list(partidos.find().sort("fecha", 1).limit(6)),
        noticias=list(noticias.find().sort("fecha", -1).limit(6)),
    )


# ---------- ACCESO ----------

@app.route("/registro", methods=["GET", "POST"])
def registro():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        correo = request.form.get("correo", "").strip().lower()
        password = request.form.get("password", "")
        if not nombre or not correo or not password:
            flash("Todos los campos son obligatorios.", "danger")
            return redirect(url_for("registro"))
        if usuarios.find_one({"correo": correo}):
            flash("Este correo ya está registrado.", "danger")
            return redirect(url_for("registro"))
        usuarios.insert_one({
            "nombre": nombre, "correo": correo, "rol": "usuario",
            "password": generate_password_hash(password), "fecha_registro": datetime.now(),
        })
        flash("Cuenta creada correctamente. Ahora puedes iniciar sesión.", "success")
        return redirect(url_for("login"))
    return render_template("registro.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST" and autenticar(usuarios, "usuario"):
        return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST" and autenticar(administradores, "admin"):
        return redirect(url_for("admin_panel"))
    return render_template("admin_login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Has cerrado sesión.", "success")
    return redirect(url_for("login"))


# ---------- ADMINISTRADOR ----------

@app.route("/admin")
@solo_admin
def admin_panel():
    conteos = {n: db[n].count_documents({}) for n in
               ("usuarios", "Administrador", "partidos", "equipos", "jugadores",
                "clasificados", "eliminados", "noticias", "apuestas")}
    return render_template("admin.html", conteos=conteos)


@app.route("/estado-db")
@solo_admin
def estado_db():
    try:
        client.admin.command("ping")
        return "<h1>MongoDB conectado correctamente</h1><p>Base de datos:</p><strong>Copamundial2026</strong>"
    except Exception as error:
        return f"<h1>Error de conexión con MongoDB</h1><p>{error}</p>"


# ---------- PARTIDOS ----------

@app.route("/partidos")
def partidos_page():
    return render_template("partidos.html", partidos=listar(partidos, "fecha"))


@app.route("/partido/<id>")
def partido_detalle(id):
    partido = buscar(partidos, id)
    if not partido:
        flash("El partido no existe.", "danger")
        return redirect(url_for("partidos_page"))
    return render_template("partido_detalle.html", partido=partido)


# ---------- EQUIPOS ----------

@app.route("/equipos")
def equipos_page():
    return render_template("equipos.html", equipos=listar(equipos, "nombre"))


@app.route("/equipo/<id>")
def equipo_detalle(id):
    equipo = buscar(equipos, id)
    if not equipo:
        flash("El equipo no existe.", "danger")
        return redirect(url_for("equipos_page"))
    return render_template("equipo_detalle.html", equipo=equipo)


# ---------- GRUPOS ----------

@app.route("/grupos")
def grupos_page():
    grupos = {}
    for e in listar(equipos, "nombre"):
        grupos.setdefault(e.get("grupo") or "Sin grupo", []).append(e)
    return render_template("grupos.html", grupos=dict(sorted(grupos.items())))


# ---------- JUGADORES ----------

@app.route("/jugadores")
def jugadores_page():
    lista = list(jugadores.find().sort([("pais", 1), ("dorsal", 1)]))
    agrupados = {}
    for j in lista:
        agrupados.setdefault(j.get("pais") or "Sin país", []).append(j)
    equipos_por_nombre = {e["nombre"]: e for e in equipos.find()}
    return render_template("jugadores.html", jugadores=dict(sorted(agrupados.items())),
                            equipos_por_nombre=equipos_por_nombre)


# ---------- CLASIFICADOS Y ELIMINADOS ----------

@app.route("/clasificados")
def clasificados_page():
    lista = list(clasificados.find().sort([("puntos", -1), ("diferencia", -1)]))
    return render_template("clasificados.html", equipos=lista)


@app.route("/eliminados")
def eliminados_page():
    return render_template("eliminados.html", eliminados=listar(eliminados, "fecha", -1))


# ---------- FRAGMENTOS EN VIVO (consultados por clasificados.html y eliminados.html) ----------

@app.route("/clasificados/fragmento")
def clasificados_fragmento():
    lista = list(clasificados.find().sort([("puntos", -1), ("diferencia", -1)]))
    return render_template("_clasificados_filas.html", equipos=lista)


@app.route("/eliminados/fragmento")
def eliminados_fragmento():
    return render_template("_eliminados_tarjetas.html", eliminados=listar(eliminados, "fecha", -1))


# ---------- ADMINISTRAR CLASIFICADOS (solo administrador) ----------

@app.route("/admin/clasificados", methods=["GET", "POST"])
@solo_admin
def admin_clasificados_page():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        if not nombre:
            flash("Selecciona un equipo.", "danger")
            return redirect(url_for("admin_clasificados_page"))
        if clasificados.find_one({"nombre": nombre}):
            flash("Ese equipo ya está en la tabla de clasificados.", "danger")
            return redirect(url_for("admin_clasificados_page"))

        gf = int(request.form.get("goles_favor", 0) or 0)
        gc = int(request.form.get("goles_contra", 0) or 0)
        clasificados.insert_one({
            "nombre": nombre,
            "pj": int(request.form.get("pj", 0) or 0),
            "pg": int(request.form.get("pg", 0) or 0),
            "pe": int(request.form.get("pe", 0) or 0),
            "pp": int(request.form.get("pp", 0) or 0),
            "goles_favor": gf,
            "goles_contra": gc,
            "diferencia": gf - gc,
            "puntos": int(request.form.get("puntos", 0) or 0),
        })
        flash("Equipo agregado a la tabla de clasificados.", "success")
        return redirect(url_for("admin_clasificados_page"))

    lista = list(clasificados.find().sort([("puntos", -1), ("diferencia", -1)]))
    nombres_usados = {d["nombre"] for d in clasificados.find({}, {"nombre": 1})}
    disponibles = list(equipos.find({"nombre": {"$nin": list(nombres_usados)}}).sort("nombre", 1))
    return render_template("admin_clasificados.html", equipos=convertir_id(lista),
                            equipos_disponibles=disponibles)


@app.route("/admin/clasificados/editar/<id>", methods=["GET", "POST"])
@solo_admin
def admin_clasificados_editar(id):
    equipo = buscar(clasificados, id)
    if not equipo:
        flash("Ese registro no existe.", "danger")
        return redirect(url_for("admin_clasificados_page"))

    if request.method == "POST":
        gf = int(request.form.get("goles_favor", 0) or 0)
        gc = int(request.form.get("goles_contra", 0) or 0)
        clasificados.update_one({"_id": equipo["_id"]}, {"$set": {
            "nombre": request.form.get("nombre", "").strip(),
            "pj": int(request.form.get("pj", 0) or 0),
            "pg": int(request.form.get("pg", 0) or 0),
            "pe": int(request.form.get("pe", 0) or 0),
            "pp": int(request.form.get("pp", 0) or 0),
            "goles_favor": gf,
            "goles_contra": gc,
            "diferencia": gf - gc,
            "puntos": int(request.form.get("puntos", 0) or 0),
        }})
        flash("Cambios guardados.", "success")
        return redirect(url_for("admin_clasificados_page"))

    equipo["_id"] = str(equipo["_id"])
    return render_template("admin_clasificados_editar.html", equipo=equipo)


@app.route("/admin/clasificados/eliminar/<id>", methods=["POST"])
@solo_admin
def admin_clasificados_eliminar(id):
    equipo = buscar(clasificados, id)
    if equipo:
        clasificados.delete_one({"_id": equipo["_id"]})
        flash("Equipo eliminado de la tabla.", "success")
    return redirect(url_for("admin_clasificados_page"))


# ---------- ADMINISTRAR ELIMINADOS (solo administrador) ----------

@app.route("/admin/eliminados", methods=["GET", "POST"])
@solo_admin
def admin_eliminados_page():
    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        if not nombre:
            flash("Selecciona un equipo.", "danger")
            return redirect(url_for("admin_eliminados_page"))
        if eliminados.find_one({"nombre": nombre}):
            flash("Ese equipo ya está marcado como eliminado.", "danger")
            return redirect(url_for("admin_eliminados_page"))

        eliminados.insert_one({
            "nombre": nombre,
            "fase": request.form.get("fase", "").strip(),
            "motivo": request.form.get("motivo", "").strip(),
            "fecha": request.form.get("fecha", "").strip(),
        })
        flash("Equipo eliminado agregado.", "success")
        return redirect(url_for("admin_eliminados_page"))

    lista = listar(eliminados, "fecha", -1)
    nombres_usados = {d["nombre"] for d in eliminados.find({}, {"nombre": 1})}
    disponibles = list(equipos.find({"nombre": {"$nin": list(nombres_usados)}}).sort("nombre", 1))
    return render_template("admin_eliminados.html", eliminados=convertir_id(lista),
                            equipos_disponibles=disponibles)


@app.route("/admin/eliminados/editar/<id>", methods=["GET", "POST"])
@solo_admin
def admin_eliminados_editar(id):
    equipo = buscar(eliminados, id)
    if not equipo:
        flash("Ese registro no existe.", "danger")
        return redirect(url_for("admin_eliminados_page"))

    if request.method == "POST":
        eliminados.update_one({"_id": equipo["_id"]}, {"$set": {
            "nombre": request.form.get("nombre", "").strip(),
            "fase": request.form.get("fase", "").strip(),
            "motivo": request.form.get("motivo", "").strip(),
            "fecha": request.form.get("fecha", "").strip(),
        }})
        flash("Cambios guardados.", "success")
        return redirect(url_for("admin_eliminados_page"))

    equipo["_id"] = str(equipo["_id"])
    return render_template("admin_eliminados_editar.html", equipo=equipo)


@app.route("/admin/eliminados/eliminar/<id>", methods=["POST"])
@solo_admin
def admin_eliminados_eliminar(id):
    equipo = buscar(eliminados, id)
    if equipo:
        eliminados.delete_one({"_id": equipo["_id"]})
        flash("Registro eliminado.", "success")
    return redirect(url_for("admin_eliminados_page"))


# ---------- ADMINISTRAR ADMINISTRADORES (solo administrador; invisible para usuarios) ----------

@app.route("/admin/administradores", methods=["GET", "POST"])
@solo_admin
def admin_administradores_page():
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        if administradores.find_one({"correo": correo}):
            flash("Ya existe un administrador con ese correo.", "danger")
            return redirect(url_for("admin_administradores_page"))
        administradores.insert_one({
            "nombre": request.form.get("nombre", "").strip(),
            "correo": correo,
            "rol": "admin",
            "password": generate_password_hash(request.form.get("password", "")),
            "fecha_registro": datetime.now(),
        })
        flash("Administrador creado correctamente.", "success")
        return redirect(url_for("admin_administradores_page"))

    lista = list(administradores.find().sort("nombre", 1))
    return render_template("admin_administradores.html", administradores=lista)


# ---------- NOTICIAS ----------

@app.route("/noticias")
def noticias_page():
    return render_template("noticias.html", noticias=listar(noticias, "fecha", -1))


@app.route("/noticia/<id>")
def noticia_detalle(id):
    noticia = buscar(noticias, id)
    if not noticia:
        flash("La noticia no existe.", "danger")
        return redirect(url_for("noticias_page"))
    return render_template("noticia_detalle.html", noticia=noticia)


# ---------- APUESTAS ----------

@app.route("/apuestas", methods=["GET", "POST"])
def apuestas_page():
    if request.method == "POST":
        partido_id = request.form.get("partido_id")
        pronostico = request.form.get("pronostico")
        if not partido_id or not pronostico:
            flash("Selecciona un partido y un pronóstico.", "danger")
            return redirect(url_for("apuestas_page"))
        partido = buscar(partidos, partido_id)
        if not partido:
            flash("El partido seleccionado no existe.", "danger")
            return redirect(url_for("apuestas_page"))
        apuestas.insert_one({
            "usuario_id": session["usuario_id"],
            "partido_id": partido["_id"],
            "partido": partido.get("equipo_local", "Equipo") + " vs " + partido.get("equipo_visitante", "Equipo"),
            "pronostico": pronostico,
            "fecha": datetime.now(),
        })
        flash("Tu pronóstico fue guardado correctamente.", "success")
        return redirect(url_for("apuestas_page"))

    mias = list(apuestas.find({"usuario_id": session["usuario_id"]}).sort("fecha", -1))
    return render_template("apuestas.html", partidos=listar(partidos, "fecha"), apuestas=mias)


@app.route("/mis-apuestas")
def mis_apuestas():
    mias = list(apuestas.find({"usuario_id": session["usuario_id"]}).sort("fecha", -1))
    return render_template("apuestas.html", apuestas=mias, partidos=[])


# ---------- ERROR 404 ----------

@app.errorhandler(404)
def pagina_no_encontrada(error):
    return '<h1 style="text-align:center;margin-top:100px;">404</h1><p style="text-align:center;">Página no encontrada.</p>', 404


# ---------- CREAR ADMINISTRADOR ----------

def crear_admin():
    """Crea la cuenta de administrador en la colección Administrador la primera vez."""
    correo = os.environ.get("ADMIN_CORREO", "admin@copamundial.com")
    if not administradores.find_one({"correo": correo}):
        administradores.insert_one({
            "nombre": "Administrador", "correo": correo, "rol": "admin",
            "password": generate_password_hash(os.environ.get("ADMIN_PASSWORD", "Admin2026!")),
            "fecha_registro": datetime.now(),
        })


crear_admin()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)