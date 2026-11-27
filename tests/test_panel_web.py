# -*- coding: utf-8 -*-
"""El panel web de un proveedor, cuando su API no alcanza (26/11/2026).

LO QUE ESTE ARCHIVO DEFIENDE

* **Entra como un navegador.** Toma el campo oculto de seguridad del
  formulario de entrada --venga con comillas simples o dobles--, manda los
  campos fijos, y si el panel vuelve a pedir la clave, falla diciendo que no
  acepto el usuario. El mensaje nunca lleva el usuario ni la clave.
* **Un formulario se reenvia TAL COMO VIENE.** Cada campo vuelve con su valor
  --el texto largo con sus saltos de linea y sus acentos, la opcion elegida,
  la casilla marcada--, la casilla sin marcar no viaja, solo cambia lo que la
  configuracion nombra, y los archivos salen todos bajo el mismo campo.
* **Lee solo lo que se le pide.** La direccion a la que redirigio, el atributo
  de un elemento, y de la firma solo si esta o no: nunca su contenido.
* **El mismo ultimo metro que la API.** Una herramienta que escribe no sale
  sin permiso de la frontera, ni afuera con la guarda de pruebas encendida:
  en los dos casos, CERO peticiones al panel.
* **Entra UNA vez y reusa la sesion** (el panel real frena la entrada a la
  quinta en una hora): si el panel la cerro, vuelve a entrar una sola vez y
  solo si el formulario no salio; tras un freno o una clave mala, ESPERA sin
  tocar el panel, y cambiar la credencial levanta la espera.
* **Reenviar no borra una firma**: lo que el formulario trae vuelve igual.
* **Lo que el panel dijo, tapado**: si rechaza el formulario y lo escribe en
  la pagina, el error trae ese aviso con numeros largos y correos tapados; un
  archivo por debajo del minimo del panel se frena ANTES de enviar.
* **«Ya salio» se distingue.** Si el formulario se envio y el panel contesto
  mal, el error lo dice (`envio`), porque nadie sabe si lo aplico.
* **El esquema lo comprueba al cargar.** Huecos que nadie llena, archivos que
  no llegan, una web en el catalogo de un rol: fallan al guardar la config.

El panel de aca es de mentira, corre en esta maquina y tiene memoria.

    python tests/test_panel_web.py
"""
from __future__ import annotations

import base64
import os
import sys
import threading
from email.parser import BytesParser
from email.policy import default as politica
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from contextlib import redirect_stdout
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.config import schema                                   # noqa: E402
from nucleo.herramientas import http as ejecutor_http              # noqa: E402
from nucleo.herramientas import web                                # noqa: E402
from nucleo.seguridad import frontera, secretos                    # noqa: E402

TENANT = "tenant-de-prueba"
USUARIO = "operador@empresa-de-prueba"
CLAVE = "clave-del-panel-NO-DEBE-SALIR"
TOKEN = "Tk9fREVCRV9RVUVEQVI.eyJzdWIiOiJwcnVlYmEifQ.ZmlybWE"
CONTENIDO = "<p>Contrato de servicio</p>\n<p>Se&ntilde;or: Laura &amp; familia</p>\n\nlinea final"

_fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(("  OK   " if condicion else "  FALLA ") + que)
    if not condicion:
        _fallos.append(que)


def seccion(titulo: str) -> None:
    print("\n" + titulo)
    print("-" * len(titulo))


# --------------------------------------------------------------------------- #
#  EL PANEL DE MENTIRA
# --------------------------------------------------------------------------- #

class Panel:
    def __init__(self):
        self.peticiones: list[tuple[str, str]] = []
        self.envios: list[dict] = []
        self.contratos: dict[str, int] = {}
        self.firmado = False
        self.rechaza_formulario = False     # re-muestra el formulario, sin redirigir
        self.error_al_guardar = None        # codigo HTTP al guardar
        self.sesiones: set[str] = set()
        self.entradas = 0                   # entradas ACEPTADAS
        self.limita_entrada = False         # contesta 429 a la entrada
        self.sigue_pidiendo_entrada = False  # nunca deja pasar, aunque entre
        self.cierra_al_guardar = False      # guarda y cierra la sesion

    def cerrar_sesiones(self):
        self.sesiones.clear()

    @property
    def intentos_de_entrada(self) -> int:
        return sum(1 for m, r in self.peticiones if m == "POST" and r == "/cuenta/entrar/")


PANEL = Panel()
CSRF = "secreto-csrf-de-la-cookie-123"


def _pagina_entrada() -> str:
    return ("<html><body><form class='x' method='POST' action='/cuenta/entrar/'>"
            f"<input type='hidden' name='csrfmiddlewaretoken' value='{CSRF}' />"
            "<input type=\"text\" name=\"login\" id=\"id_login\" />"
            "<input type=\"password\" name=\"password\" />"
            "<input type=\"hidden\" name=\"token_device\" />"
            "<input id='id_remember' name='remember' type='checkbox' value='1' checked>"
            "<button type='submit'>Entrar</button></form></body></html>")


def _pagina_contrato(n: int, error: str = "") -> str:
    firma = "data:image/png;base64,QUJDREVGRw==" if PANEL.firmado else ""
    aviso = f"<ul class='errorlist nonfield'><li>{error}</li></ul>" if error else ""
    return (
        "<html><body>" + aviso +
        "<form id='otro' method='POST' action='/contacto/'><input name='x' value='1'></form>"
        "<form id='generarContrato' method='post' action='' enctype='multipart/form-data'>"
        f"<input type='hidden' name='csrfmiddlewaretoken' value='otro-token-{n}' />"
        "<input type='text' name='contrato-fecha_inicio' value='26/11/2026' />"
        "<textarea name='contrato-contenido' class='ck'>\n" + CONTENIDO + "</textarea>"
        "<button type='button' class='btn'>Limpiar Firma</button>"
        "<textarea name='contrato-firma'>\n" + firma + "</textarea>"
        "<select name='contrato-plan'><option value='a'>A</option>"
        "<option value='b' selected>B</option></select>"
        "<input type='checkbox' name='contrato-acepta' checked>"
        "<input type='checkbox' name='form-0-visible'>"
        "<input type='file' name='archivo' multiple>"
        "<input type='hidden' name='form-TOTAL_FORMS' value='1' />"
        "<input type='hidden' name='form-INITIAL_FORMS' value='0' />"
        "<input type='hidden' name='form-MAX_NUM_FORMS' value='3' />"
        "<input type='file' name='form-0-archivo'>"
        "<input type='text' name='form-0-titulo' value=''>"
        "<textarea name='form-0-descripcion'>\n</textarea>"
        "<button type='submit' name='guardar_contrato' class='btn'>Guardar</button>"
        "<button type='submit' name='guardar_contrato_pdf'>Guardar y PDF</button>"
        "</form></body></html>")


class Manejador(BaseHTTPRequestHandler):
    def log_message(self, *a):            # silencio
        pass

    def _cookies(self) -> dict:
        crudo = self.headers.get("Cookie") or ""
        return dict(p.strip().split("=", 1) for p in crudo.split(";") if "=" in p)

    def _responder(self, codigo=200, cuerpo="", ubicacion=None, cookies=()):
        self.send_response(codigo)
        if ubicacion:
            self.send_header("Location", ubicacion)
        for c in cookies:
            self.send_header("Set-Cookie", c)
        datos = cuerpo.encode("utf-8")
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(datos)))
        self.end_headers()
        self.wfile.write(datos)

    def _dentro(self) -> bool:
        return (self._cookies().get("sesion") in PANEL.sesiones
                and not PANEL.sigue_pidiendo_entrada)

    def do_GET(self):
        ruta = urlsplit(self.path).path
        PANEL.peticiones.append(("GET", ruta))
        if ruta == "/cuenta/entrar/":
            return self._responder(200, _pagina_entrada(), cookies=[f"csrftoken={CSRF}; Path=/"])
        if ruta == "/panel/" and self._cookies().get("sesion") in PANEL.sesiones:
            return self._responder(200, "<html>panel</html>")   # la entrada SI aterriza
        if not self._dentro():
            return self._responder(302, "", "/cuenta/entrar/")
        partes = ruta.strip("/").split("/")
        if ruta.startswith("/instalaciones/agregar-contrato/"):
            servicio = partes[2]
            n = PANEL.contratos.setdefault(servicio, 4900 + len(PANEL.contratos))
            return self._responder(302, "", f"/instalaciones/editar-contrato/{n}/")
        if ruta.startswith("/instalaciones/editar-contrato/"):
            return self._responder(200, _pagina_contrato(int(partes[2])))
        if ruta.startswith("/clientes/generar-link/"):
            usuario, servicio = partes[2], partes[3]
            return self._responder(200, (
                "<html><a class='btn' id='copiar' data-x='1'>Copiar link</a>"
                f"<a class='btn' href='http://portal.example/login-panel/{TOKEN}/' "
                f"id='auto-login' data-u='{usuario}' data-s='{servicio}'>Ir al link</a></html>"))
        return self._responder(404, "no esta")

    def do_POST(self):
        ruta = urlsplit(self.path).path
        PANEL.peticiones.append(("POST", ruta))
        largo = int(self.headers.get("Content-Length") or 0)
        cuerpo = self.rfile.read(largo)
        tipo = self.headers.get("Content-Type") or ""
        if ruta == "/cuenta/entrar/":
            datos = dict(parse_qsl(cuerpo.decode("utf-8"), keep_blank_values=True))
            if (self._cookies().get("csrftoken") != CSRF
                    or datos.get("csrfmiddlewaretoken") != CSRF
                    or not self.headers.get("Referer")):
                return self._responder(403, "CSRF")
            if PANEL.limita_entrada:
                return self._responder(429, "Too Many Requests")
            PANEL.envios.append({"_entrada": sorted(datos)})
            if datos.get("login") == USUARIO and datos.get("password") == CLAVE:
                PANEL.entradas += 1
                sesion = f"ses-{PANEL.entradas}"
                PANEL.sesiones.add(sesion)
                return self._responder(302, "", "/panel/", cookies=[f"sesion={sesion}; Path=/"])
            return self._responder(200, _pagina_entrada())
        if not self._dentro():
            return self._responder(302, "", "/cuenta/entrar/")
        if ruta.startswith("/instalaciones/editar-contrato/"):
            msg = BytesParser(policy=politica).parsebytes(
                b"Content-Type: " + tipo.encode() + b"\r\n\r\n" + cuerpo)
            campos, archivos = [], []
            for parte in msg.iter_parts():
                nombre = parte.get_param("name", header="content-disposition")
                archivo = parte.get_filename()
                if archivo is not None:
                    archivos.append((nombre, archivo, parte.get_content_type(),
                                     parte.get_payload(decode=True)))
                else:
                    campos.append((nombre, parte.get_payload(decode=True).decode("utf-8")))
            PANEL.envios.append({"campos": campos, "archivos": archivos,
                                 "multipart": tipo.startswith("multipart/form-data"),
                                 "referer": self.headers.get("Referer") or ""})
            if PANEL.cierra_al_guardar:
                PANEL.cerrar_sesiones()
            if PANEL.error_al_guardar:
                return self._responder(PANEL.error_al_guardar, "error")
            if PANEL.rechaza_formulario:
                return self._responder(200, _pagina_contrato(
                    int(ruta.strip("/").split("/")[2]),
                    error="El archivo 1234567 de ana.ruiz@correo.com es muy pequeño. Mínimo 1.0 KB."))
            return self._responder(302, "", ruta)
        return self._responder(404, "no esta")


servidor = ThreadingHTTPServer(("127.0.0.1", 0), Manejador)
threading.Thread(target=servidor.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{servidor.server_address[1]}"

_secretos_original = secretos.obtener
secretos.obtener = lambda tenant, nombre: {"PANEL_WEB_USUARIO": USUARIO,
                                           "PANEL_WEB_CLAVE": CLAVE}.get(nombre)

SESION_WEB = dict(entrada="/cuenta/entrar/", usuario_ref="PANEL_WEB_USUARIO",
                  clave_ref="PANEL_WEB_CLAVE", campo_usuario="login", campo_clave="password",
                  campo_csrf="csrfmiddlewaretoken",
                  campos_fijos={"token_device": "", "remember": "1"})


def herramienta(**kw):
    base = dict(nombre="preparar_contrato_del_proveedor", tipo="web", solo_lectura=False,
                requiere_confirmacion=True,
                roles_permitidos=["administracion"],
                base_url=BASE, sesion_web=SESION_WEB, argumentos_web=["id_servicio", "archivos"],
                pasos_web=[
                    dict(abrir="/instalaciones/agregar-contrato/{id_servicio}/",
                         capturar={"contrato_id": dict(de="url",
                                                       patron=r"/editar-contrato/(\d+)/")}),
                    dict(formulario="/instalaciones/editar-contrato/{contrato_id}/",
                         id_formulario="generarContrato", valores={"contrato-firma": ""},
                         archivos={"archivo": "archivos"}, boton="guardar_contrato",
                         exito="redirige"),
                ])
    base.update(kw)
    return schema.Herramienta(**base)


ENLACE = schema.Herramienta(
    nombre="enlace_de_firma", tipo="web", solo_lectura=True, base_url=BASE,
    roles_permitidos=["administracion"],
    sesion_web=SESION_WEB, argumentos_web=["usuario", "id_servicio"],
    pasos_web=[dict(abrir="/clientes/generar-link/{usuario}/{id_servicio}/",
                    capturar={"enlace": dict(de="atributo", id="auto-login", atributo="href")})])

FIRMA = schema.Herramienta(
    nombre="firma_del_contrato", tipo="web", solo_lectura=True, base_url=BASE,
    roles_permitidos=["administracion"],
    sesion_web=SESION_WEB, argumentos_web=["contrato_id"],
    pasos_web=[dict(abrir="/instalaciones/editar-contrato/{contrato_id}/",
                    capturar={"firmado": dict(de="campo", nombre="contrato-firma",
                                              solo_si_tiene=True)})])

ARCHIVOS = [
    {"nombre": "cedula.jpg", "base64": base64.b64encode(b"JPG-CEDULA").decode(), "tipo": "image/jpeg"},
    {"nombre": "recibo.pdf", "base64": base64.b64encode(b"PDF-RECIBO").decode(), "tipo": "application/pdf"},
]


def reiniciar():
    PANEL.__init__()
    web._SESIONES.clear()


def con_permiso(h, argumentos):
    with frontera.humana(TENANT, h.nombre, actor="Tecnico de prueba", evidencia="orden-1",
                         origen="contrato:1"):
        return web.ejecutar(h, argumentos, TENANT)


def no_carga(que: str, **kw) -> None:
    try:
        herramienta(**kw)
    except Exception:                                    # noqa: BLE001
        afirmar(True, f"no carga: {que}")
        return
    afirmar(False, f"no carga: {que}")


def falla(fn) -> BaseException | None:
    try:
        fn()
    except BaseException as e:                            # noqa: BLE001
        return e
    return None


os.environ.pop("SIN_EFECTOS_EXTERNOS", None)

# --------------------------------------------------------------------------- #
seccion("1. entra y guarda el contrato TAL COMO VIENE, con los archivos")
reiniciar()
salida = StringIO()
with redirect_stdout(salida):
    leido = con_permiso(herramienta(), {"id_servicio": 8039, "archivos": ARCHIVOS})
afirmar(leido == {"contrato_id": "4900"}, f"lee el numero del contrato de la redireccion ({leido})")
entrada = PANEL.envios[0].get("_entrada")
afirmar(entrada == sorted(["csrfmiddlewaretoken", "login", "password", "token_device", "remember"]),
        f"la entrada manda el campo de seguridad y los fijos ({entrada})")
envio = PANEL.envios[1]
campos = dict(envio["campos"])
afirmar(envio["multipart"], "el formulario sale como multipart")
afirmar(campos.get("contrato-contenido") == "<p>Contrato de servicio</p>\n<p>Señor: Laura & familia</p>\n\nlinea final",
        "el texto del contrato vuelve IGUAL: sin el salto inicial, con acentos y saltos")
afirmar(campos.get("csrfmiddlewaretoken") == "otro-token-4900",
        "devuelve el campo de seguridad DEL FORMULARIO, no el de la entrada")
afirmar(campos.get("contrato-firma") == "", "la firma va vacia, como pide la configuracion")
afirmar(campos.get("contrato-plan") == "b", "la opcion elegida vuelve elegida")
afirmar(campos.get("contrato-acepta") == "on", "la casilla marcada vuelve marcada")
afirmar("form-0-visible" not in campos, "la casilla SIN marcar no viaja")
afirmar(campos.get("contrato-fecha_inicio") == "26/11/2026" and campos.get("form-TOTAL_FORMS") == "1",
        "los demas campos vuelven con su valor")
afirmar("guardar_contrato" in campos and "guardar_contrato_pdf" not in campos,
        "se envia con el boton nombrado, y solo con ese")
afirmar("x" not in campos, "no mezcla campos de otro formulario de la pagina")
afirmar([(a[0], a[1], a[2], a[3]) for a in envio["archivos"]] == [
    ("archivo", "cedula.jpg", "image/jpeg", b"JPG-CEDULA"),
    ("archivo", "recibo.pdf", "application/pdf", b"PDF-RECIBO")],
    "los DOS archivos salen bajo el mismo campo, con nombre y tipo")
afirmar(envio["referer"].endswith("/instalaciones/editar-contrato/4900/"),
        "manda la pagina del formulario como origen")
afirmar(PANEL.entradas == 1, "entro una sola vez")
log = salida.getvalue()
afirmar(CLAVE not in log and USUARIO not in log and "Laura" not in log,
        "el registro no lleva la clave, el usuario ni el contrato")

# --------------------------------------------------------------------------- #
seccion("2. lee el enlace y la firma: solo lo que se pide")
reiniciar()
leido = web.ejecutar(ENLACE, {"usuario": "laura-pineda@empresa", "id_servicio": 8039}, TENANT)
afirmar(leido == {"enlace": f"http://portal.example/login-panel/{TOKEN}/"},
        "devuelve el enlace del atributo, completo")
afirmar(("GET", "/clientes/generar-link/laura-pineda@empresa/8039/") in PANEL.peticiones,
        "la arroba del usuario viaja tal cual en la ruta")
reiniciar()
afirmar(web.ejecutar(FIRMA, {"contrato_id": "4900"}, TENANT) == {"firmado": False},
        "sin firma: firmado = False")
PANEL.firmado = True
leido = web.ejecutar(FIRMA, {"contrato_id": "4900"}, TENANT)
afirmar(leido == {"firmado": True}, "con firma: firmado = True, y NUNCA el contenido de la firma")
afirmar(PANEL.envios == [{"_entrada": PANEL.envios[0]["_entrada"]}] * len(PANEL.envios),
        "una lectura no envia ningun formulario")

# --------------------------------------------------------------------------- #
seccion("3. el mismo ultimo metro que la API: sin permiso o con la guarda, cero peticiones")
reiniciar()
e = falla(lambda: web.ejecutar(herramienta(), {"id_servicio": 8039, "archivos": ARCHIVOS}, TENANT))
afirmar(isinstance(e, frontera.AccionExternaNoAutorizada), f"sin permiso no sale ({type(e).__name__})")
afirmar(PANEL.peticiones == [], "y no toco el panel")
os.environ["SIN_EFECTOS_EXTERNOS"] = "1"
fuera = herramienta(base_url="https://panel.example")
e = falla(lambda: con_permiso(fuera, {"id_servicio": 8039, "archivos": ARCHIVOS}))
afirmar(isinstance(e, ejecutor_http.ErrorHerramientaHttp),
        f"con la guarda de pruebas, una escritura afuera no sale ({type(e).__name__})")
os.environ["EFECTOS_EXTERNOS_PERMITIDOS"] = "otra_herramienta"
e = falla(lambda: con_permiso(fuera, {"id_servicio": 8039, "archivos": ARCHIVOS}))
afirmar(isinstance(e, ejecutor_http.ErrorHerramientaHttp),
        "el permiso de la prueba vigilada es por NOMBRE: otra herramienta no la abre")
os.environ.pop("EFECTOS_EXTERNOS_PERMITIDOS", None)
reiniciar()
leido = web.ejecutar(FIRMA, {"contrato_id": "4900"}, TENANT)
afirmar(leido == {"firmado": False}, "una LECTURA sigue funcionando con la guarda encendida")
os.environ.pop("SIN_EFECTOS_EXTERNOS", None)

# --------------------------------------------------------------------------- #
seccion("4. lo que sale mal se dice, y «ya salio» se distingue")
reiniciar()
mala = schema.Herramienta(**{**ENLACE.model_dump(), "nombre": "enlace_clave_mala"})
secretos.obtener = lambda tenant, nombre: {"PANEL_WEB_USUARIO": USUARIO,
                                           "PANEL_WEB_CLAVE": "otra-clave"}.get(nombre)
salida = StringIO()
with redirect_stdout(salida):
    e = falla(lambda: web.ejecutar(mala, {"usuario": "u@e", "id_servicio": 1}, TENANT))
afirmar(isinstance(e, web.ErrorWeb) and e.etapa == "entrada", f"clave mala: falla en la entrada ({e})")
afirmar("otra-clave" not in str(e) and USUARIO not in str(e) and "otra-clave" not in salida.getvalue(),
        "ni el error ni el registro llevan el usuario o la clave")
secretos.obtener = lambda tenant, nombre: None
e = falla(lambda: web.ejecutar(ENLACE, {"usuario": "u@e", "id_servicio": 1}, TENANT))
afirmar(isinstance(e, web.ErrorWeb) and "PANEL_WEB_USUARIO" in str(e),
        "sin la credencial cargada, dice cual falta")
secretos.obtener = lambda tenant, nombre: {"PANEL_WEB_USUARIO": USUARIO,
                                           "PANEL_WEB_CLAVE": CLAVE}.get(nombre)

reiniciar()
PANEL.rechaza_formulario = True
with redirect_stdout(StringIO()):
    e = falla(lambda: con_permiso(herramienta(), {"id_servicio": 8039, "archivos": ARCHIVOS}))
afirmar(isinstance(e, web.ErrorWeb) and e.envio and "redirigio" in e.motivo,
        "el panel re-muestra el formulario: falla, y dice que YA SALIO")
afirmar(isinstance(e, web.ErrorWeb)
        and e.avisos == ["El archivo <n> de <correo> es muy pequeño. Mínimo 1.0 KB."]
        and "el panel dijo" in str(e),
        f"...y trae lo que el panel escribio, con el numero y el correo tapados ({getattr(e, 'avisos', None)})")
reiniciar()
chico = herramienta(pasos_web=[dict(formulario="/instalaciones/editar-contrato/{id_servicio}/",
                                    id_formulario="generarContrato",
                                    archivos={"archivo": "archivos"}, archivo_minimo_bytes=1024,
                                    boton="guardar_contrato")])
with redirect_stdout(StringIO()):
    e = falla(lambda: con_permiso(chico, {"id_servicio": 4900, "archivos": ARCHIVOS}))
afirmar(isinstance(e, web.ErrorWeb) and not e.envio and "pesa menos" in e.motivo
        and [x for x in PANEL.envios if "campos" in x] == [],
        "un archivo por debajo del minimo del panel frena ANTES de enviar")
grande = [{"nombre": "cedula.jpg", "tipo": "image/jpeg",
           "base64": base64.b64encode(b"J" * 2048).decode()}]
with redirect_stdout(StringIO()):
    e = falla(lambda: con_permiso(chico, {"id_servicio": 4900, "archivos": grande}))
afirmar(e is None and len([x for x in PANEL.envios if "campos" in x]) == 1,
        "con el peso suficiente, sale")
reiniciar()
PANEL.error_al_guardar = 500
with redirect_stdout(StringIO()):
    e = falla(lambda: con_permiso(herramienta(), {"id_servicio": 8039, "archivos": ARCHIVOS}))
afirmar(isinstance(e, web.ErrorWeb) and e.envio and e.http_status == 500,
        "un 500 al guardar: falla con el codigo y «ya salio»")
reiniciar()
with redirect_stdout(StringIO()):
    e = falla(lambda: con_permiso(herramienta(), {"id_servicio": 8039}))
afirmar(e is None and PANEL.envios[-1]["archivos"] == [],
        "sin archivos tambien guarda (y no inventa ninguno)")
reiniciar()
with redirect_stdout(StringIO()):
    e = falla(lambda: con_permiso(herramienta(), {"id_servicio": 8039, "archivos": [{"nombre": "x"}]}))
afirmar(isinstance(e, web.ErrorWeb) and not e.envio and PANEL.envios[1:] == [],
        "un archivo sin contenido frena ANTES de enviar")
reiniciar()
otra = herramienta(pasos_web=[dict(formulario="/instalaciones/editar-contrato/{id_servicio}/",
                                   id_formulario="generarContrato",
                                   valores={"contrato-no-existe": ""})])
with redirect_stdout(StringIO()):
    e = falla(lambda: con_permiso(otra, {"id_servicio": 1}))
afirmar(isinstance(e, web.ErrorWeb) and not e.envio and "no tiene" in e.motivo,
        "cambiar un campo que el formulario no tiene: frena antes de enviar")
reiniciar()
e = falla(lambda: web.ejecutar(ENLACE, {"usuario": "", "id_servicio": 1}, TENANT))
afirmar(isinstance(e, web.ErrorWeb) and "usuario" in str(e), "un hueco vacio no arma una direccion a medias")

# --------------------------------------------------------------------------- #
seccion("5. entra UNA vez y reusa la sesion; tras un freno, espera")
reiniciar()
for _ in range(4):
    web.ejecutar(FIRMA, {"contrato_id": "4900"}, TENANT)
web.ejecutar(ENLACE, {"usuario": "u@e", "id_servicio": 1}, TENANT)
afirmar(PANEL.intentos_de_entrada == 1,
        f"cinco lecturas, de dos herramientas, con UNA sola entrada ({PANEL.intentos_de_entrada})")

PANEL.cerrar_sesiones()
afirmar(web.ejecutar(FIRMA, {"contrato_id": "4900"}, TENANT) == {"firmado": False},
        "si el panel cerro la sesion, vuelve a entrar y la lectura sale")
afirmar(PANEL.intentos_de_entrada == 2, "...con UNA entrada mas")

reiniciar()
PANEL.sigue_pidiendo_entrada = True
with redirect_stdout(StringIO()):
    e = falla(lambda: web.ejecutar(FIRMA, {"contrato_id": "1"}, TENANT))
afirmar(isinstance(e, web.ErrorWeb) and PANEL.intentos_de_entrada == 2,
        f"si sigue pidiendo la entrada, vuelve a entrar UNA vez y falla ({PANEL.intentos_de_entrada})")

reiniciar()
with redirect_stdout(StringIO()):
    con_permiso(herramienta(), {"id_servicio": 8039, "archivos": ARCHIVOS})
    PANEL.cerrar_sesiones()                    # la sesion cae ANTES del segundo pedido
    antes = len(PANEL.envios)
    e = falla(lambda: con_permiso(herramienta(), {"id_servicio": 8040, "archivos": ARCHIVOS}))
afirmar(e is None and len([x for x in PANEL.envios[antes:] if "campos" in x]) == 1
        and PANEL.intentos_de_entrada == 2,
        "con la sesion caida ANTES de enviar: vuelve a entrar y envia UNA vez")

reiniciar()
PANEL.cierra_al_guardar = True                 # guarda, y la redireccion ya pide la entrada
with redirect_stdout(StringIO()):
    e = falla(lambda: con_permiso(herramienta(), {"id_servicio": 8041, "archivos": ARCHIVOS}))
envios = [x for x in PANEL.envios if "campos" in x]
afirmar(isinstance(e, web.ErrorWeb) and e.envio and len(envios) == 1
        and PANEL.intentos_de_entrada == 1,
        f"si la sesion cae DESPUES de enviar, NO reenvia: falla diciendo «ya salio» ({len(envios)})")

reiniciar()
PANEL.limita_entrada = True
with redirect_stdout(StringIO()):
    e = falla(lambda: web.ejecutar(FIRMA, {"contrato_id": "1"}, TENANT))
afirmar(isinstance(e, web.ErrorWeb) and e.http_status == 429 and "demasiados" in e.motivo,
        "un 429 en la entrada se dice como lo que es: el panel freno, no «clave mala»")
PANEL.limita_entrada = False
antes = len(PANEL.peticiones)
with redirect_stdout(StringIO()):
    e = falla(lambda: web.ejecutar(FIRMA, {"contrato_id": "1"}, TENANT))
afirmar(isinstance(e, web.ErrorWeb) and len(PANEL.peticiones) == antes and "min" in str(e),
        "y en la espera NO se vuelve a tocar el panel")
secretos.obtener = lambda tenant, nombre: {"PANEL_WEB_USUARIO": USUARIO,
                                           "PANEL_WEB_CLAVE": CLAVE + "-nueva"}.get(nombre)
with redirect_stdout(StringIO()):
    e = falla(lambda: web.ejecutar(FIRMA, {"contrato_id": "1"}, TENANT))
afirmar(len(PANEL.peticiones) > antes, "cambiar la credencial levanta la espera (vuelve a intentar)")
secretos.obtener = lambda tenant, nombre: {"PANEL_WEB_USUARIO": USUARIO,
                                           "PANEL_WEB_CLAVE": CLAVE}.get(nombre)

reiniciar()
PANEL.firmado = True
sin_tocar = herramienta(pasos_web=[dict(formulario="/instalaciones/editar-contrato/{id_servicio}/",
                                        id_formulario="generarContrato",
                                        archivos={"archivo": "archivos"},
                                        boton="guardar_contrato")])
with redirect_stdout(StringIO()):
    con_permiso(sin_tocar, {"id_servicio": 4900, "archivos": ARCHIVOS})
firma = dict(PANEL.envios[-1]["campos"]).get("contrato-firma")
afirmar(firma == "data:image/png;base64,QUJDREVGRw==",
        "reenviar un contrato YA firmado no borra la firma (vuelve tal como venia)")

# --------------------------------------------------------------------------- #
seccion("6. el bloque de archivos: una fila por archivo, cada una con su titulo")
reiniciar()
con_bloque = herramienta(argumentos_web=["id_servicio", "documentos"], pasos_web=[
    dict(formulario="/instalaciones/editar-contrato/{id_servicio}/",
         id_formulario="generarContrato", boton="guardar_contrato", archivo_minimo_bytes=1024,
         bloque_de_archivos=dict(argumento="documentos", prefijo="form",
                                 campo_archivo="archivo", campo_titulo="titulo"))])
DOCS = [{"nombre": f"doc-{i}.jpg", "tipo": "image/jpeg", "titulo": t,
         "base64": base64.b64encode(bytes([65 + i]) * 2048).decode()}
        for i, t in enumerate(["Cedula frente", "Cedula reverso"])]
DOCS.append({"nombre": "recibo.pdf", "tipo": "application/pdf",
             "base64": base64.b64encode(b"R" * 4096).decode()})
with redirect_stdout(StringIO()):
    e = falla(lambda: con_permiso(con_bloque, {"id_servicio": 4900, "documentos": DOCS}))
envio = PANEL.envios[-1]
c = envio["campos"]
d = dict(c)
afirmar(e is None, f"guarda con el bloque ({e})")
afirmar(d.get("form-TOTAL_FORMS") == "3" and [n for n, _ in c].count("form-TOTAL_FORMS") == 1,
        "el total de filas pasa a 3, una sola vez")
afirmar([(n, v) for n, v in c if n.endswith("-titulo")] == [
    ("form-0-titulo", "Cedula frente"), ("form-1-titulo", "Cedula reverso"),
    ("form-2-titulo", "recibo.pdf")],
    "cada fila con SU titulo, y sin titulo va el nombre del archivo")
afirmar([(a[0], a[1], len(a[3])) for a in envio["archivos"]] == [
    ("form-0-archivo", "doc-0.jpg", 2048), ("form-1-archivo", "doc-1.jpg", 2048),
    ("form-2-archivo", "recibo.pdf", 4096)],
    "cada archivo en SU fila, con su contenido")
afirmar([(n, v) for n, v in c if n.endswith("-descripcion")] == [
    ("form-0-descripcion", ""), ("form-1-descripcion", ""), ("form-2-descripcion", "")],
    "lo demas de la fila sale del molde (descripcion vacia)")
afirmar(not any(n.endswith("-visible") for n, _ in c), "la casilla sin marcar del molde no viaja")
afirmar(d.get("contrato-contenido", "").startswith("<p>Contrato de servicio</p>")
        and d.get("form-INITIAL_FORMS") == "0" and d.get("form-MAX_NUM_FORMS") == "3",
        "el resto del formulario vuelve igual")
reiniciar()
with redirect_stdout(StringIO()):
    e = falla(lambda: con_permiso(con_bloque, {"id_servicio": 4900, "documentos": DOCS * 2}))
afirmar(isinstance(e, web.ErrorWeb) and not e.envio and "mas archivos" in e.motivo,
        "mas archivos de los que el bloque acepta: frena ANTES de enviar")
reiniciar()
chicos = [dict(DOCS[0]), dict(DOCS[1], base64=base64.b64encode(b"x").decode())]
with redirect_stdout(StringIO()):
    e = falla(lambda: con_permiso(con_bloque, {"id_servicio": 4900, "documentos": chicos}))
afirmar(isinstance(e, web.ErrorWeb) and not e.envio and "pesa menos" in e.motivo,
        "un archivo del bloque bajo el minimo: frena ANTES de enviar")
reiniciar()
with redirect_stdout(StringIO()):
    e = falla(lambda: con_permiso(con_bloque, {"id_servicio": 4900, "documentos": []}))
d = dict(PANEL.envios[-1]["campos"])
afirmar(e is None and d.get("form-TOTAL_FORMS") == "1" and d.get("form-0-titulo") == "",
        "sin archivos, el bloque va como vino")
no_carga("un bloque cuyo argumento no llega",
         argumentos_web=["id_servicio"], pasos_web=[
             dict(formulario="/x/{id_servicio}/", id_formulario="f",
                  bloque_de_archivos=dict(argumento="documentos", prefijo="form",
                                          campo_archivo="archivo"))])
no_carga("un bloque en un paso que solo abre",
         pasos_web=[dict(abrir="/x/", bloque_de_archivos=dict(
             argumento="archivos", prefijo="form", campo_archivo="archivo"))])

# --------------------------------------------------------------------------- #
seccion("7. el esquema lo comprueba al cargar")
no_carga("tipo web sin sesion", sesion_web=None)
no_carga("tipo web sin pasos", pasos_web=[])
no_carga("un hueco que nadie llena", argumentos_web=["archivos"])
no_carga("archivos que no llegan", argumentos_web=["id_servicio"])
no_carga("invocable por un servicio", invocable_por_servicio=True)
no_carga("sin base_url", base_url=None)
no_carga("un paso que abre Y reenvia",
         pasos_web=[dict(abrir="/a/", formulario="/b/", id_formulario="f")])
no_carga("formulario sin id", pasos_web=[dict(formulario="/b/")])
no_carga("ruta sin barra inicial", pasos_web=[dict(abrir="a/")])
no_carga("captura de url sin patron",
         pasos_web=[dict(abrir="/a/", capturar={"x": dict(de="url")})])
no_carga("captura con patron que no compila",
         pasos_web=[dict(abrir="/a/", capturar={"x": dict(de="url", patron="(")})])
no_carga("un secreto escrito como valor",
         sesion_web={**SESION_WEB, "clave_ref": "mi clave 123"})
no_carga("una captura que pisa un argumento",
         pasos_web=[dict(abrir="/a/{id_servicio}/",
                         capturar={"id_servicio": dict(de="url", patron="x")})])
try:
    schema.Herramienta(nombre="x", tipo="http", endpoint="/x", base_url=BASE, roles_permitidos=["administracion"],
                       sesion_web=SESION_WEB)
    afirmar(False, "no carga: una sesion web en una herramienta http")
except Exception:                                        # noqa: BLE001
    afirmar(True, "no carga: una sesion web en una herramienta http")

# una herramienta web en el catalogo de un rol: lo rechaza la config entera
from nucleo.config import fuente                                    # noqa: E402
import yaml                                                          # noqa: E402

doc = yaml.safe_load((RAIZ / "tenants" / "rapilink.config.yaml").read_text(encoding="utf-8"))
doc["herramientas"].append(ENLACE.model_dump(exclude_defaults=True))
rol = next(iter(doc["roles"]))
doc["roles"][rol].setdefault("puede_consultar", []).append("enlace_de_firma")
try:
    schema.TenantConfig(**doc)
    afirmar(False, "no carga: una herramienta web en el catalogo de un rol")
except Exception as e:                                   # noqa: BLE001
    afirmar("panel web" in str(e), f"no carga: una herramienta web en el catalogo de un rol")

secretos.obtener = _secretos_original
servidor.shutdown()

# ---------------------------------------------------------------------------
print()
if _fallos:
    print(f"FALLARON {len(_fallos)}:")
    for f in _fallos:
        print("  -", f)
    sys.exit(1)
print("TODO OK")
