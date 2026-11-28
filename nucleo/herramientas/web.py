"""
EL PANEL WEB DE UN PROVEEDOR, CUANDO SU API NO ALCANZA  --  26/11/2026.

El error que lo origino: la API del primer proveedor no tiene contratos,
firmas ni archivos de un cliente (58 rutas medidas), y el usuario decidio que
el cliente firme el contrato DEL PROVEEDOR, el que vive en su panel web. Para
eso alguien tiene que entrar al panel, guardar el contrato con los documentos
y sacar el enlace de firma. Este modulo es ese alguien.

QUE SABE Y QUE NO
-----------------
Sabe lo que es un panel web: entrar con un formulario, abrir una pagina,
reenviar un formulario y leer un dato. NO sabe de ningun proveedor: las rutas,
los nombres de los campos y los NOMBRES de los secretos vienen de la
configuracion (`SesionWeb`, `PasoWeb`, `CapturaWeb` en nucleo/config/schema.py).

LAS TRES REGLAS
---------------
1. **El mismo ultimo metro que una llamada a la API.** Antes de la primera
   peticion pasa por `http._exigir_frontera`: una herramienta que escribe sale
   solo con un permiso vigente de la frontera, y con la guarda de pruebas
   (`SIN_EFECTOS_EXTERNOS`) no sale afuera. No hay un camino nuevo que escriba
   sin ese control.
2. **Un formulario se reenvia TAL COMO VIENE.** Se toman todos sus campos con
   el valor que traen, y solo se cambia lo que la configuracion nombra. Un
   panel que reescribe el registro entero con lo que recibe vaciaria lo que no
   se mando -- en el contrato medido, el texto completo del contrato.
3. **Lo que se lee de la pagina no se escribe en ningun lado.** El panel
   muestra todo (documento, domicilio, contrato). De una pagina solo sale lo
   que una `CapturaWeb` nombra, y el registro lleva etapas y codigos, nunca
   contenido. Una captura `solo_si_tiene` devuelve si/no, nunca el valor.

`ErrorWeb.envio` dice si el formulario YA SALIO cuando algo fallo: en ese caso
nadie sabe si el proveedor lo aplico, y quien llama tiene que mirar antes de
repetir -- la misma regla que el alta (CLAUDE.md §12, «una mutacion externa se
ejecuta una vez»).

SE ENTRA UNA VEZ Y LA SESION SE REUSA  --  medido el 26/11/2026
---------------------------------------------------------------
El primer proveedor contesto **HTTP 429 a la quinta entrada en menos de una
hora** (las cuatro anteriores, de la medicion, habian entrado bien). Entrar en
cada llamada no sirve: mirar si un contrato ya se firmo cada pocos segundos
agotaria el cupo en minutos, y el usuario bloqueado es EL DE LA EMPRESA --el
mismo con que la oficina trabaja en el panel--. Por eso:

* la sesion abierta queda en memoria del proceso, por empresa y credencial, y
  la siguiente llamada la reusa; si el panel la cerro, se vuelve a entrar UNA
  vez, y solo si el formulario todavia no salio;
* una entrada que falla (clave mala, o el panel frenando) deja una ESPERA: en
  ese rato no se vuelve a intentar --ni se toca el panel--, para no
  convertir un rechazo en un bloqueo. Cambiar la credencial la levanta.
"""
from __future__ import annotations

import base64
import hashlib
import re
import threading
import time
from html.parser import HTMLParser
from urllib.parse import quote, urljoin, urlsplit

import requests

from nucleo.herramientas import http as ejecutor_http
from nucleo.observabilidad.registro import registrar

TIMEOUT_SEGUNDOS = 30
#: Tope de lo que viaja en archivos en UNA llamada. Un panel web no es un
#: deposito, y el puente entre servicios trae los archivos en base64.
LIMITE_DE_ARCHIVOS_BYTES = 25 * 1024 * 1024
#: Un navegador comun: hay paneles que no atienden a un cliente sin nombre.
#: No lleva nada de la empresa ni de quien lo usa.
AGENTE = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
#: Tras una entrada fallida, cuanto se espera antes de volver a intentar.
ESPERA_TRAS_FRENO_S = 15 * 60          # el panel freno por demasiados intentos
ESPERA_TRAS_RECHAZO_S = 5 * 60         # el panel no acepto usuario y clave
#: Cuanto se espera la sesion del panel si otra llamada la esta usando
#: (auditoria de frontera, 27/11/2026): sin tope, la espera podia pasar el
#: vencimiento del registro de operaciones y el pedido salir DOS veces.
ESPERA_DEL_CANDADO_S = 120
_HUECO = re.compile(r"\{(\w+)\}")
_SIN_VALOR = ("submit", "button", "image", "reset", "file")


class ErrorWeb(Exception):
    """Algo del panel no salio. El mensaje nunca lleva contenido de la pagina
    ni secretos: la etapa, que paso y el codigo HTTP."""

    def __init__(self, etapa: str, motivo: str, *, http_status: int | None = None,
                 envio: bool = False, avisos: list[str] | None = None):
        self.etapa = etapa
        self.motivo = motivo
        self.http_status = http_status
        #: El formulario ya habia salido: no se sabe si el proveedor lo aplico.
        self.envio = envio
        #: Lo que el panel escribio como error de formulario, tapado (ver _avisos).
        self.avisos = list(avisos or [])
        codigo = f" (HTTP {http_status})" if http_status else ""
        dijo = f" -- el panel dijo: {' | '.join(self.avisos)}" if self.avisos else ""
        super().__init__(f"{etapa}: {motivo}{codigo}{dijo}")


# ---------------------------------------------------------------------------
#  LEER UNA PAGINA
# ---------------------------------------------------------------------------

class _Formulario:
    def __init__(self, atributos: dict):
        self.accion = atributos.get("action") or ""
        self.metodo = (atributos.get("method") or "get").lower()
        self.enctype = (atributos.get("enctype") or "").lower()
        self.campos: list[tuple[str, str]] = []      # en orden, como los manda un navegador
        self.botones: dict[str, str] = {}
        self.de_archivo: set[str] = set()
        self.nombres: set[str] = set()


class _Pagina(HTMLParser):
    """Lo que hace falta de una pagina: sus formularios con sus campos, el valor
    de cada campo por nombre y los atributos de cada elemento con id."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.formularios: dict[str, _Formulario] = {}
        self.campos: dict[str, str] = {}
        self.por_id: dict[str, dict] = {}
        self._form: _Formulario | None = None
        self._textarea: list | None = None            # [nombre, partes]
        self._select: list | None = None              # [nombre, multiple, opciones]
        self._opcion: list | None = None              # [valor|None, seleccionada, texto]

    # -- utilidades --------------------------------------------------------
    def _anotar(self, nombre: str, valor: str, *, en_el_form: bool = True) -> None:
        self.campos.setdefault(nombre, valor)
        if self._form is not None and en_el_form:
            self._form.campos.append((nombre, valor))

    # -- el recorrido ------------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = {k: (v if v is not None else "") for k, v in attrs}
        if a.get("id"):
            self.por_id.setdefault(a["id"], a)
        if tag == "form":
            self._form = _Formulario(a)
            clave = a.get("id") or f"#{len(self.formularios) + 1}"
            self.formularios.setdefault(clave, self._form)
            return
        nombre = a.get("name") or ""
        if tag == "input":
            tipo = (a.get("type") or "text").lower()
            if nombre and self._form is not None:
                self._form.nombres.add(nombre)
            if tipo in ("submit", "image") and nombre and self._form is not None:
                self._form.botones.setdefault(nombre, a.get("value", ""))
                return
            if tipo == "file":
                if nombre and self._form is not None:
                    self._form.de_archivo.add(nombre)
                return
            if tipo in _SIN_VALOR or not nombre:
                return
            if tipo in ("checkbox", "radio"):
                if "checked" in a:
                    self._anotar(nombre, a.get("value") or "on")
                return
            self._anotar(nombre, a.get("value", ""))
        elif tag == "button":
            tipo = (a.get("type") or "submit").lower()
            if nombre and tipo == "submit" and self._form is not None:
                self._form.botones.setdefault(nombre, a.get("value", ""))
        elif tag == "textarea" and nombre:
            if self._form is not None:
                self._form.nombres.add(nombre)
            self._textarea = [nombre, []]
        elif tag == "select" and nombre:
            if self._form is not None:
                self._form.nombres.add(nombre)
            self._select = [nombre, "multiple" in a, []]
        elif tag == "option" and self._select is not None:
            self._opcion = [a.get("value"), "selected" in a, []]

    def handle_data(self, data):
        if self._textarea is not None:
            self._textarea[1].append(data)
        elif self._opcion is not None:
            self._opcion[2].append(data)

    def _cerrar_opcion(self):
        if self._opcion is not None and self._select is not None:
            valor, sel, texto = self._opcion
            self._select[2].append((valor if valor is not None else "".join(texto).strip(), sel))
        self._opcion = None

    def handle_endtag(self, tag):
        if tag == "textarea" and self._textarea is not None:
            texto = "".join(self._textarea[1])
            #  Un navegador descarta UN salto de linea justo despues de
            #  <textarea>: sin esto, cada reenvio le sumaria uno al texto.
            if texto.startswith("\r\n"):
                texto = texto[2:]
            elif texto.startswith("\n"):
                texto = texto[1:]
            self._anotar(self._textarea[0], texto)
            self._textarea = None
        elif tag == "option":
            self._cerrar_opcion()
        elif tag == "select" and self._select is not None:
            self._cerrar_opcion()
            nombre, multiple, opciones = self._select
            elegidas = [v for v, sel in opciones if sel]
            if not elegidas and opciones and not multiple:
                elegidas = [opciones[0][0]]           # lo que hace un navegador
            for v in elegidas:
                self._anotar(nombre, v)
            self._select = None
        elif tag == "form":
            self._form = None


def _leer(html: str) -> _Pagina:
    p = _Pagina()
    try:
        p.feed(html or "")
        p.close()
    except Exception:                                    # noqa: BLE001
        pass                    # una pagina mal formada: se usa lo que se leyo
    return p


# ---------------------------------------------------------------------------
#  EL RECORRIDO
# ---------------------------------------------------------------------------

def _llenar(plantilla: str, contexto: dict, etapa: str, *, en_ruta: bool) -> str:
    def _uno(m):
        clave = m.group(1)
        valor = contexto.get(clave)
        if valor is None or valor == "" or isinstance(valor, (dict, list)):
            raise ErrorWeb(etapa, f"falta '{clave}' para armar la direccion")
        return quote(str(valor), safe="@-._~") if en_ruta else str(valor)
    return _HUECO.sub(_uno, plantilla or "")


def _ruta_de(url: str) -> str:
    return urlsplit(url).path.rstrip("/") or "/"


class _SesionCerrada(ErrorWeb):
    """El panel volvio a pedir la entrada a mitad de camino."""


def _comprobar(r, etapa: str, entrada: str, *, envio: bool = False) -> None:
    if r.status_code == 429:
        raise ErrorWeb(etapa, "el panel freno por demasiados pedidos seguidos",
                       http_status=429, envio=envio)
    if r.status_code >= 400:
        raise ErrorWeb(etapa, "el panel respondio con error", http_status=r.status_code,
                       envio=envio)
    if _ruta_de(r.url) == _ruta_de(entrada):
        raise _SesionCerrada(etapa, "el panel volvio a pedir la entrada: la sesion no "
                                    "quedo abierta", http_status=r.status_code, envio=envio)


def _credenciales(tenant: str, sw) -> tuple[str, str]:
    from nucleo.seguridad import secretos

    usuario = secretos.obtener(tenant, sw.usuario_ref)
    clave = secretos.obtener(tenant, sw.clave_ref)
    for ref, valor in ((sw.usuario_ref, usuario), (sw.clave_ref, clave)):
        if not valor:
            raise ErrorWeb("entrada", f"falta la credencial '{ref}': cargala en "
                                      f"Configuracion -> Credenciales")
    return usuario, clave


class _Abierta:
    """Una sesion del panel, reusable. La usa una llamada a la vez."""

    def __init__(self, huella: str):
        self.huella = huella
        self.s = requests.Session()
        self.s.headers["User-Agent"] = AGENTE
        self.dentro = False
        self.esperar_hasta = 0.0
        self.motivo_espera = ""
        self.candado = threading.Lock()


_SESIONES: dict[tuple, _Abierta] = {}
_CANDADO = threading.Lock()


def _sesion_de(tenant: str, base: str, sw, usuario: str, clave: str) -> _Abierta:
    clave_sesion = (tenant, base, sw.usuario_ref, sw.clave_ref)
    #  La huella cambia si cambia la credencial: una sesion (o una espera)
    #  de la credencial vieja no sirve para la nueva. No se guarda el valor.
    huella = hashlib.sha256(f"{usuario}\0{clave}".encode("utf-8")).hexdigest()
    with _CANDADO:
        actual = _SESIONES.get(clave_sesion)
        if actual is None or actual.huella != huella:
            if actual is not None:
                actual.s.close()
            actual = _SESIONES[clave_sesion] = _Abierta(huella)
        return actual


def _entrar(s, base: str, sw, usuario: str, clave: str, espera: float) -> None:
    r = s.get(base + sw.entrada, timeout=espera)
    if r.status_code == 429:
        raise ErrorWeb("entrada", "el panel freno la entrada por demasiados intentos "
                                  "seguidos: hay que esperar", http_status=429)
    if r.status_code >= 400:
        raise ErrorWeb("entrada", "la pagina de entrada no abrio", http_status=r.status_code)
    pagina = _leer(r.text)
    form = next((f for f in pagina.formularios.values() if sw.campo_clave in f.nombres), None)
    if form is None:
        raise ErrorWeb("entrada", "la pagina de entrada no trae el formulario con la clave")
    datos = dict(sw.campos_fijos)
    if sw.campo_csrf:
        token = dict(form.campos).get(sw.campo_csrf)
        if not token:
            raise ErrorWeb("entrada", "la pagina de entrada no trae el campo de seguridad")
        datos[sw.campo_csrf] = token
    datos[sw.campo_usuario] = usuario
    datos[sw.campo_clave] = clave
    destino = urljoin(r.url, form.accion) if form.accion else r.url
    r2 = s.post(destino, data=datos, headers={"Referer": r.url}, timeout=espera)
    if r2.status_code == 429:
        raise ErrorWeb("entrada", "el panel freno la entrada por demasiados intentos "
                                  "seguidos: hay que esperar", http_status=429)
    if (r2.status_code >= 400 or _ruta_de(r2.url) == _ruta_de(base + sw.entrada)
            or sw.campo_clave in {n for f in _leer(r2.text).formularios.values()
                                  for n in f.nombres}):
        raise ErrorWeb("entrada", "el panel no acepto el usuario y la clave",
                       http_status=r2.status_code if r2.status_code >= 400 else None)


def _archivos(lista, etapa: str) -> list[tuple[str, bytes, str, str]]:
    """(nombre, contenido, tipo, titulo) de cada archivo de la lista."""
    if lista in (None, "", []):
        return []
    if isinstance(lista, dict):
        lista = [lista]
    if not isinstance(lista, list):
        raise ErrorWeb(etapa, "los archivos no llegaron como una lista")
    salida = []
    for i, a in enumerate(lista, 1):
        if not isinstance(a, dict) or not a.get("base64"):
            raise ErrorWeb(etapa, f"el archivo {i} no trae contenido")
        try:
            contenido = base64.b64decode(a["base64"], validate=True)
        except Exception:                                # noqa: BLE001
            raise ErrorWeb(etapa, f"el archivo {i} no es base64 valido") from None
        nombre = str(a.get("nombre") or f"archivo-{i}")
        salida.append((nombre, contenido, str(a.get("tipo") or "application/octet-stream"),
                       str(a.get("titulo") or nombre)))
    return salida


def _pesa_lo_minimo(paso, contenido: bytes, i: int, argumento: str, etapa: str) -> None:
    #  El panel medido rechaza un archivo de menos de 1 KB, y lo dice DENTRO de
    #  la pagina (26/11/2026). Se frena antes de enviar.
    if len(contenido) < paso.archivo_minimo_bytes:
        raise ErrorWeb(etapa, f"el archivo {i} de '{argumento}' pesa menos de lo que "
                              f"el panel acepta ({paso.archivo_minimo_bytes} bytes)")


def _con_el_bloque(paso, form: _Formulario, campos: list, partes: list, argumentos: dict,
                   etapa: str) -> tuple[list, int]:
    """Agrega una FILA por archivo al bloque repetible. Devuelve (campos, bytes).

    Las filas de la plantilla que ya existian (las 'iniciales') vuelven igual;
    las vacias que la pagina trae para llenar se quitan, y sus otros campos
    sirven de molde para cada fila nueva (descripcion vacia, casilla sin
    marcar...). El total se cuenta de nuevo.

    Los `campos_que_no_van` se quitan del molde SIEMPRE (27/11/2026): asi una
    casilla como «visible para el cliente» sale sin marcar aunque la pagina la
    traiga marcada.
    """
    b = paso.bloque_de_archivos
    lista = _archivos(argumentos.get(b.argumento), etapa)
    if not lista:
        return campos, 0                       # sin archivos, el formulario va como vino
    valores = dict(form.campos)
    total, iniciales, maximo = (f"{b.prefijo}-TOTAL_FORMS", f"{b.prefijo}-INITIAL_FORMS",
                                f"{b.prefijo}-MAX_NUM_FORMS")
    if total not in valores:
        raise ErrorWeb(etapa, f"el formulario no tiene el bloque de archivos '{b.prefijo}'")
    try:
        desde = int(valores.get(iniciales) or 0)
        tope = int(valores.get(maximo) or 1000)
    except ValueError:
        raise ErrorWeb(etapa, "el bloque de archivos trae un conteo que no es un numero") from None
    if f"{b.prefijo}-{desde}-{b.campo_archivo}" not in form.de_archivo:
        raise ErrorWeb(etapa, f"el bloque '{b.prefijo}' no tiene el campo de archivo "
                              f"'{b.campo_archivo}'")
    if desde + len(lista) > tope:
        raise ErrorWeb(etapa, "son mas archivos de los que el bloque acepta")
    fila = re.compile(rf"^{re.escape(b.prefijo)}-(\d+)-(.+)$")
    fuera = set(b.campos_que_no_van or ())
    molde: dict[str, str] = {}
    salida = []
    for c, v in campos:
        m = fila.match(c)
        if m and int(m.group(1)) >= desde:
            if int(m.group(1)) == desde:
                molde.setdefault(m.group(2), v)
            continue
        if c != total:
            salida.append((c, v))
    salida.append((total, str(desde + len(lista))))
    pesan = 0
    for k, (nombre, contenido, tipo, titulo) in enumerate(lista):
        _pesa_lo_minimo(paso, contenido, k + 1, b.argumento, etapa)
        n = desde + k
        for sufijo, v in molde.items():
            if sufijo not in (b.campo_archivo, b.campo_titulo) and sufijo not in fuera:
                salida.append((f"{b.prefijo}-{n}-{sufijo}", v))
        if b.campo_titulo:
            salida.append((f"{b.prefijo}-{n}-{b.campo_titulo}", titulo))
        partes.append((f"{b.prefijo}-{n}-{b.campo_archivo}", (nombre, contenido, tipo)))
        pesan += len(contenido)
    return salida, pesan


def _capturar(paso, url: str, pagina: _Pagina, etapa: str) -> dict:
    salida = {}
    for nombre, c in paso.capturar.items():
        valor = None
        if c.de == "url":
            m = re.search(c.patron, url)
            if m:
                valor = m.group(1) if m.groups() else m.group(0)
        elif c.de == "campo":
            valor = pagina.campos.get(c.nombre)
        else:
            valor = (pagina.por_id.get(c.id) or {}).get(c.atributo)
            if valor and c.atributo.lower() in ("href", "src", "action"):
                valor = urljoin(url, valor)
        if c.solo_si_tiene:
            salida[nombre] = bool(str(valor or "").strip())
            continue
        if (valor is None or str(valor).strip() == "") and c.obligatoria:
            raise ErrorWeb(etapa, f"la pagina no trae '{nombre}'")
        salida[nombre] = valor
    return salida


def ejecutar(herramienta, argumentos: dict, tenant: str,
             variables_tenant: dict | None = None, *, antes_de_salir=None) -> dict:
    """Entra al panel (o reusa la sesion), da los pasos y devuelve lo que las
    capturas leyeron.

    `antes_de_salir`, si viene, se llama YA CON LA SESION TOMADA y antes de la
    primera peticion: quien escribe vuelve a leer ahi el interruptor, que pudo
    cambiar mientras se esperaba la sesion (auditoria de frontera, 27/11/2026).

    Lanza `ejecutor_http.ErrorHerramientaHttp` si el ultimo metro no la deja
    salir (antes de cualquier peticion) y `ErrorWeb` si algo del panel falla.
    """
    sw = getattr(herramienta, "sesion_web", None)
    if getattr(herramienta, "tipo", None) != "web" or sw is None:
        raise ErrorWeb("configuracion", "no es una herramienta del panel web")
    #  UNA «LECTURA» NO ENVIA FORMULARIOS (auditoria de frontera, 27/11/2026):
    #  la frontera solo se exige a lo que escribe, asi que una herramienta de
    #  solo lectura con un paso de formulario mandaria un POST sin control. El
    #  esquema ya la rechaza; esto es el ultimo metro.
    if getattr(herramienta, "solo_lectura", True) and any(
            getattr(p, "formulario", "") for p in herramienta.pasos_web):
        raise ErrorWeb("configuracion", "una herramienta de solo lectura no envia formularios")
    argumentos = dict(argumentos or {})

    #  1. EL ULTIMO METRO, antes de la primera peticion (ver el encabezado).
    ejecutor_http._exigir_frontera(herramienta, tenant, argumentos, variables_tenant)

    base = ejecutor_http.base_url_de(herramienta, variables_tenant).rstrip("/")
    espera = float(getattr(herramienta, "timeout_segundos", None) or TIMEOUT_SEGUNDOS)
    usuario, clave = _credenciales(tenant, sw)
    abierta = _sesion_de(tenant, base, sw, usuario, clave)
    if not abierta.candado.acquire(timeout=ESPERA_DEL_CANDADO_S):
        raise ErrorWeb("sesion", "el panel esta ocupado con otro pedido; nada salio")
    try:
        if antes_de_salir is not None:
            antes_de_salir()
        try:
            for intento in (1, 2):
                if not abierta.dentro:
                    _entrar_o_esperar(abierta, base, sw, usuario, clave, espera)
                try:
                    return _recorrer(herramienta, abierta.s, base, sw, argumentos, espera)
                except _SesionCerrada as e:
                    abierta.dentro = False
                    #  Se vuelve a entrar UNA vez, y solo si nada salio todavia.
                    if e.envio or intento == 2:
                        raise
        except requests.RequestException as e:
            registrar("panel_web", "el panel no contesto", herramienta=herramienta.nombre,
                      error=e)
            raise ErrorWeb("red", "el panel no contesto",
                           envio=getattr(e, "_envio_web", False)) from None
        except ErrorWeb as e:
            registrar("panel_web", "el panel no dejo completar los pasos",
                      herramienta=herramienta.nombre, etapa=e.etapa,
                      http_status=e.http_status, envio=e.envio)
            raise
    finally:
        abierta.candado.release()
    raise ErrorWeb("configuracion", "no se completo ningun intento")    # no se llega


def _entrar_o_esperar(abierta: _Abierta, base: str, sw, usuario: str, clave: str,
                      espera: float) -> None:
    ahora = time.monotonic()
    if ahora < abierta.esperar_hasta:
        minutos = max(1, int((abierta.esperar_hasta - ahora + 59) // 60))
        raise ErrorWeb("entrada", f"{abierta.motivo_espera}; no se vuelve a intentar "
                                  f"por {minutos} min para no bloquear el usuario del panel")
    try:
        _entrar(abierta.s, base, sw, usuario, clave, espera)
    except ErrorWeb as e:
        frenado = e.http_status == 429
        abierta.esperar_hasta = time.monotonic() + (
            ESPERA_TRAS_FRENO_S if frenado else ESPERA_TRAS_RECHAZO_S)
        abierta.motivo_espera = ("la ultima entrada la freno el panel por demasiados "
                                 "intentos" if frenado else "la ultima entrada fallo")
        abierta.s.cookies.clear()
        raise
    abierta.dentro = True
    abierta.esperar_hasta = 0.0


def _recorrer(herramienta, s, base: str, sw, argumentos: dict, espera: float) -> dict:
    contexto = {k: v for k, v in argumentos.items() if not isinstance(v, (dict, list))}
    leido: dict = {}
    envio = False
    for n, paso in enumerate(herramienta.pasos_web, 1):
        etapa = f"paso {n}"
        try:
            if paso.abrir:
                r = s.get(base + _llenar(paso.abrir, contexto, etapa, en_ruta=True),
                          timeout=espera)
                _comprobar(r, etapa, base + sw.entrada, envio=envio)
                nuevo = _capturar(paso, r.url, _leer(r.text), etapa)
            else:
                nuevo = _enviar(paso, s, base, sw, argumentos, contexto, etapa, espera,
                                ya_salio=envio)
                envio = True
        except requests.RequestException as e:
            e._envio_web = envio or getattr(e, "_envio_web", False)
            raise
        except ErrorWeb as e:
            e.envio = e.envio or envio
            raise
        leido.update(nuevo)
        contexto.update({k: v for k, v in nuevo.items() if not isinstance(v, bool)})
    return leido


def _enviar(paso, s, base: str, sw, argumentos: dict, contexto: dict, etapa: str,
            espera: float, *, ya_salio: bool) -> dict:
    r = s.get(base + _llenar(paso.formulario, contexto, etapa, en_ruta=True), timeout=espera)
    _comprobar(r, etapa, base + sw.entrada, envio=ya_salio)
    form = _leer(r.text).formularios.get(paso.id_formulario)
    if form is None:
        raise ErrorWeb(etapa, f"la pagina no trae el formulario '{paso.id_formulario}'")
    if form.metodo != "post":
        raise ErrorWeb(etapa, "el formulario no se envia por POST")
    cambiados = {c: _llenar(v, contexto, etapa, en_ruta=False) for c, v in paso.valores.items()}
    no_estan = sorted(set(cambiados) - form.nombres)
    if no_estan:
        raise ErrorWeb(etapa, f"el formulario no tiene {no_estan}")
    campos = [(c, v) for c, v in form.campos if c not in cambiados]
    campos += list(cambiados.items())
    if paso.boton:
        if paso.boton not in form.botones:
            raise ErrorWeb(etapa, f"el formulario no tiene el boton '{paso.boton}'")
        campos.append((paso.boton, form.botones[paso.boton]))
    partes, total = [], 0
    for campo, argumento in paso.archivos.items():
        if campo not in form.de_archivo:
            raise ErrorWeb(etapa, f"el formulario no tiene el campo de archivo '{campo}'")
        for i, (nombre, contenido, tipo, _titulo) in enumerate(
                _archivos(argumentos.get(argumento), etapa), 1):
            _pesa_lo_minimo(paso, contenido, i, argumento, etapa)
            total += len(contenido)
            partes.append((campo, (nombre, contenido, tipo)))
    if paso.bloque_de_archivos:
        campos, pesan = _con_el_bloque(paso, form, campos, partes, argumentos, etapa)
        total += pesan
    if total > LIMITE_DE_ARCHIVOS_BYTES:
        raise ErrorWeb(etapa, "los archivos pasan el tope de una llamada")
    destino = urljoin(r.url, form.accion) if form.accion else r.url
    cabeceras = {"Referer": r.url}
    try:
        if partes or "multipart" in form.enctype:
            r2 = s.post(destino, files=[(c, (None, v)) for c, v in campos] + partes,
                        headers=cabeceras, timeout=espera)
        else:
            r2 = s.post(destino, data=campos, headers=cabeceras, timeout=espera)
    except requests.RequestException as e:
        #  Salvo que ni siquiera se haya conectado, no se sabe si llego.
        e._envio_web = not isinstance(e, requests.ConnectTimeout)
        raise
    _comprobar(r2, etapa, base + sw.entrada, envio=True)
    if paso.exito == "redirige" and not r2.history:
        avisos = _avisos(r2.text)
        raise ErrorWeb(etapa, "el panel no redirigio despues de guardar: puede haber "
                              "rechazado el formulario", http_status=r2.status_code, envio=True,
                       avisos=avisos)
    return _capturar(paso, r2.url, _leer(r2.text), etapa)


#  LOS AVISOS DEL PANEL CUANDO RECHAZA UN FORMULARIO  --  26/11/2026
#  El primer rechazo medido volvio con HTTP 200 y la razon escrita en la pagina
#  («El tamaño del archivo es muy pequeño...»), en una lista con clase
#  'errorlist'. Sin leerla, el error solo decia «no redirigio». Se toma el texto
#  de los bloques que por convencion marcan un error de formulario --no de un
#  proveedor en particular--, con los numeros largos y los correos tapados, y
#  pocos: es un mensaje para quien lo diagnostica, no una copia de la pagina.
_CLASES_DE_ERROR = re.compile(
    r"<(ul|div|span|p|li)\b[^>]*class=[\"'][^\"']*\b(errorlist|invalid-feedback|alert-danger|"
    r"text-danger)\b[^\"']*[\"'][^>]*>(.*?)</\1>", re.S | re.I)


def _avisos(html: str, cuantos: int = 3) -> list[str]:
    salida: list[str] = []
    for m in _CLASES_DE_ERROR.finditer(html or ""):
        texto = re.sub(r"<[^>]+>", " ", m.group(3))
        texto = re.sub(r"[\w.+-]+@[\w.-]+", "<correo>", texto)
        texto = re.sub(r"\d{5,}", "<n>", texto)
        texto = re.sub(r"\s+", " ", texto).strip()[:160]
        if len(texto) > 2 and texto not in salida:
            salida.append(texto)
        if len(salida) >= cuantos:
            break
    return salida
