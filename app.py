import os
import certifi
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
from datetime import datetime

app = Flask(__name__)
app.secret_key = "COPA_MUNDIAL_2026_CLAVE"

URI = "mongodb+srv://vimi090703hmcvrma5_db_user:qgb4fQjc7xIyy0UB@cluster0.nwwzftq.mongodb.net/"

ca = certifi.where()
client = MongoClient(URI, tlsCAFile=ca)

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
               ("usuarios", "Administrador", "partidos", "equipos", "jugadores", "noticias", "apuestas")}
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
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)