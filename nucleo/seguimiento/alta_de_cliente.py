# -*- coding: utf-8 -*-
"""Crear en el ISP al cliente de un contrato firmado en su casa.

POR QUE EXISTE  --  25/11/2026.

Hasta hoy el tecnico firmaba el contrato en la app y despues alguien tecleaba
al cliente en el panel del proveedor: nombre, documento, plan, direccion, IP.
El usuario, planeando el formato de instalacion: *«que el tecnico solo valide y
confirme y asi se genere»*. Todo lo que ese formulario pide ya esta en el
contrato firmado.

POR QUE NO ES UNA HERRAMIENTA DEL MODELO. Los datos de un alta son los de una
persona --documento, domicilio-- y los pone un contrato que esa persona firmo,
no una conversacion. Esto lo llama el backend cuando un tecnico identificado
confirma, y entra por `frontera.humana()` con el contrato como evidencia; nunca
por `/interno/herramienta/`, que es la puerta AUTONOMA --la del sistema
decidiendo solo--. El esquema rechaza que la herramienta este en el catalogo de
un rol o que sea invocable por un servicio.

CREAR NO ES IDEMPOTENTE, Y POR ESO HAY DOS DEFENSAS, NO UNA.

  1. LA CLAVE. Una por pedido: el mismo pedido no sale dos veces, ni por un
     doble toque ni por un reintento de red. Una operacion que quedo fallida
     NUNCA se vuelve a ejecutar aca: si una persona decide insistir, es otro
     pedido, con otro numero, y lo decide quien llama.
  2. EL EFECTO. Lo que ninguna clave resuelve (CLAUDE.md 12): si la llamada
     salio y la respuesta se perdio, nadie sabe si el proveedor la aplico. Por
     eso SIEMPRE se empieza preguntando que cliente tiene esa IP. Si ya la
     tiene uno con el mismo nombre en el router, es el nuestro: se adopta, no
     se crea otro.

«NO SE» NO ES «FALLO»  --  auditoria de frontera, el mismo dia.
La primera version devolvia FALLO cuando la llamada salia y volvia con un error
ambiguo --un corte, un 5xx-- y tambien cuando la IP quedaba tomada por una
ficha que no se reconocia. Quien lo leia hacia lo razonable: anular el contrato
y firmar otro. Y eso, con el primer cliente quiza ya creado, es crear DOS. Asi
que ahora hay tres cosas distintas, y no se mezclan:

  * FALLO          el proveedor DIJO que no: rechazo el pedido, o dio el
                   trabajo por fallido, y la IP sigue libre. No hay cliente.
  * EN_CURSO       se pidio, o no se sabe si llego, y el cliente todavia no
                   aparece. Se sigue mirando. Nadie sabe todavia.
  * NO_RECONOCIDO  despues de pedir, la IP quedo tomada por un cliente que no
                   se pudo reconocer como este. Casi seguro es el nuestro,
                   guardado distinto de como se mando; pero «casi seguro» no
                   alcanza para escribir su numero en un contrato. Lo mira una
                   persona.

LO QUE CONFIRMA ES LA LECTURA, NUNCA EL MENSAJE. El proveedor de la primera
empresa contesta «recibido» con el id de una tarea, y ya esta medido que una
tarea puede decir que termino bien con un error adentro. Creado significa que
al preguntar por la IP aparece el cliente.

TRES COMPROBACIONES ANTES DE ESCRIBIR, las tres en el ultimo metro:

  * la IP es de los rangos que la empresa declaro para ESA zona;
  * la IP no la tiene ningun cliente (lectura viva, no una copia de ayer);
  * el plan existe en el catalogo del proveedor (de ahi sale su id).

Si alguna no se puede hacer --o contesta algo que no se entiende--, NO SE CREA.
No poder preguntar no es permiso.

LO QUE ESTO NO PUEDE PROMETER. Que la IP sea usable: libre significa «no la
tiene un cliente», y una antena no es un cliente. Y que el cuerpo sea el que el
proveedor espera mas alla de los tres campos medidos: eso lo dice la primera
alta de verdad, no una prueba.

PRIVACIDAD. Nada de lo que viaja aca --nombre, documento, domicilio, la clave
del equipo-- se escribe en un log ni en el registro de operaciones: lo que
queda es que se pidio, con que tarea, y como termino. Los motivos que salen de
aca son texto fijo: nunca el de una excepcion, nunca el del proveedor.
"""
from __future__ import annotations

import ipaddress
import re
import time
import unicodedata
from dataclasses import dataclass, field

from nucleo.observabilidad.registro import registrar

#: Como puede terminar. El backend los traduce a una respuesta HTTP.
CREADO = "creado"                       # se creo en esta pasada, y se leyo
YA_ESTABA = "ya_estaba"                 # esa IP ya la tiene ESTE cliente
EN_CURSO = "en_curso"                   # se pidio y todavia no aparece
NO_RECONOCIDO = "no_reconocido"         # la IP quedo tomada y no se sabe por quien
FALLO = "fallo"                         # el proveedor dijo que no: no hay cliente
IP_OCUPADA = "ip_ocupada"               # ANTES de pedir: esa IP la tiene otro
IP_FUERA_DEL_RANGO = "ip_fuera_del_rango"
PLAN_DESCONOCIDO = "plan_desconocido"
DATOS_INVALIDOS = "datos_invalidos"
SIN_HERRAMIENTA = "sin_herramienta"
BLOQUEADO = "bloqueado"                 # el sistema decidio no escribir
#  LA ACTIVACION (26/11/2026): una INSTALACION que una persona valido pasa a
#  ser cliente.
ACTIVADO = "activado"                   # se activo en esta pasada, y se leyo
#  COMPLETAR (26/11/2026): el costo y el serial, en el cliente ya activado.
COMPLETADO = "completado"               # se escribio y se leyo igual
NADA_QUE_COMPLETAR = "nada_que_completar"
NO_ENCONTRADA = "no_encontrada"         # no hay una instalacion de este contrato
NO_SE_PUDO_COMPROBAR = "no_se_pudo_comprobar"

#: Cuanto se espera, despues de pedir, a que el cliente aparezca. La app no
#: espera esto: el backend lo llama en segundo plano.
ESPERA_S = 25
INTERVALO_S = 3

#: Seis decimales son ~11 cm: de sobra para una casa.
_DECIMALES = 6

#: Tope del texto de cada dato. Lo que llega ya viene acotado por el contrato;
#: esto es el ultimo metro.
_LARGO = 200

#: La forma del id de un trabajo en segundo plano. Va a parar a la RUTA de una
#: lectura: lo que no tenga esta forma no se usa.
_ID_DE_TAREA = re.compile(r"^[A-Za-z0-9_-]{1,80}$")


@dataclass
class ResultadoAlta:
    estado: str
    motivo: str = ""
    referencia: str = ""
    #: El id del cliente en el proveedor, cuando se pudo leer.
    id_cliente: str = ""
    #: El id del trabajo en segundo plano, para volver a preguntar por el.
    tarea: str = ""
    #: Cosas que NO impidieron crear y que alguien tiene que saber (un secreto
    #: que no estaba cargado, por ejemplo).
    avisos: list[str] = field(default_factory=list)
    #: EL PEDIDO LLEGO HASTA EL REGISTRO DE OPERACIONES: a partir de ahi puede
    #: haber salido hacia el proveedor. Quien llama lo necesita para no tratar
    #: igual «la IP estaba tomada y nunca pedimos nada» que «la IP esta tomada
    #: y ya habiamos pedido»: en el segundo caso el que la tiene puede ser el
    #: nuestro.
    emitido: bool = False

    @property
    def creado(self) -> bool:
        return self.estado in (CREADO, YA_ESTABA)

    def como_dict(self) -> dict:
        return {"estado": self.estado, "motivo": self.motivo,
                "referencia": self.referencia, "id_cliente": self.id_cliente,
                "tarea": self.tarea, "avisos": list(self.avisos),
                "emitido": self.emitido}


# =============================================================================
#  LO QUE LA EMPRESA DECLARO
# =============================================================================
def _herramientas(config) -> dict:
    """Las del alta, buscadas POR SU MARCA y nunca por su nombre (CLAUDE.md
    3.1): un nombre aca seria el de la herramienta de un proveedor concreto
    metido en el motor."""
    hs = list(config.herramientas or [])
    busca = [h for h in hs if getattr(h, "busca_cliente_por_ip", False)]
    return {
        "crear": next((h for h in hs if getattr(h, "crea_cliente", False)), None),
        #  La lista de CLIENTES; las de instalaciones van aparte (26/11/2026).
        "buscar": next((h for h in busca if not _de_instalaciones(h)), None),
        "buscar_instalaciones": [h for h in busca if _de_instalaciones(h)],
        "activar": next((h for h in hs if getattr(h, "activa_servicio", False)), None),
        "completar": next((h for h in hs if getattr(h, "completa_cliente_activado", False)),
                          None),
        "tarea": next((h for h in hs if getattr(h, "lee_tarea", False)), None),
        "planes": next((h for h in hs
                        if getattr(h, "sincroniza_precio_plan", "") == "listado"), None),
    }


def _de_instalaciones(herr) -> bool:
    pb = getattr(herr, "parametros_de_busqueda_por_ip", None)
    return bool(getattr(pb, "son_instalaciones", False))


class _NoSePudoLeer(Exception):
    """Una lectura del alta fallo, o contesto algo que no se entiende. Lleva el
    TIPO del problema, nunca el texto de un error."""


def _filas(crudo) -> list[dict]:
    """Las filas de un listado del proveedor, o `_NoSePudoLeer`.

    ESTRICTO A PROPOSITO (auditoria de frontera, 25/11/2026). La version
    anterior convertia cualquier cosa rara --un `null`, un numero, una lista
    de textos-- en una lista vacia, y una lista vacia aca significa «esa IP no
    la tiene nadie»: se creaba. Una respuesta que no se entiende no es una
    respuesta vacia.

    Se aceptan dos formas: una lista de objetos, o un objeto con su lista en
    `results`.
    """
    if isinstance(crudo, dict):
        crudo = crudo.get("results")
    if not isinstance(crudo, list) or not all(isinstance(f, dict) for f in crudo):
        raise _NoSePudoLeer("forma inesperada")
    return crudo


def _llano(texto) -> str:
    """Para COMPARAR, nunca para escribir: sin tildes, mayusculas ni signos."""
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    return " ".join(re.sub(r"[^a-z0-9]+", " ", t.lower()).split())


def _digitos(texto) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def _texto(valor) -> str:
    return " ".join(str(valor or "").split())[:_LARGO]


def _id_de_tarea(valor) -> str:
    """El id de la tarea si tiene forma de id; si no, vacio."""
    t = str(valor or "").strip()
    return t if _ID_DE_TAREA.match(t) else ""


# =============================================================================
#  LOS DATOS
# =============================================================================
def _ip(valor) -> str | None:
    try:
        ip = ipaddress.ip_address(str(valor or "").strip())
    except ValueError:
        return None
    if ip.version != 4:
        return None
    #  La red, la puerta de enlace y el broadcast no son de un cliente. La
    #  misma regla con que el contrato valida la que eligio el tecnico; aca es
    #  la que manda, porque corre pegada a la escritura.
    if int(str(ip).rsplit(".", 1)[1]) in (0, 1, 255):
        return None
    return str(ip)


def _punto(coordenadas) -> str:
    """`lat,lng` con coma y sin espacio, o vacio si no es un punto del planeta."""
    if not isinstance(coordenadas, dict):
        return ""
    try:
        lat, lng = float(coordenadas.get("lat")), float(coordenadas.get("lng"))
    except (TypeError, ValueError):
        return ""
    if lat != lat or lng != lng or abs(lat) > 90 or abs(lng) > 180:
        return ""
    if lat == 0.0 and lng == 0.0:
        return ""                       # un formulario a medio llenar, no una casa
    return f"{lat:.{_DECIMALES}f},{lng:.{_DECIMALES}f}"


def leer_datos(datos, parametros) -> tuple[dict | None, str]:
    """Los datos del alta, limpios, o `(None, por que no)`.

    FAIL-CLOSED: lo que no se reconoce no se arregla. Esto no interpreta un
    dato ajeno: lo ESCRIBE como la ficha de una persona en otro sistema.
    """
    if not isinstance(datos, dict):
        return None, "los datos del alta tienen que ser un objeto"
    try:
        zona = int(datos.get("zona"))
    except (TypeError, ValueError):
        zona = 0
    if isinstance(datos.get("zona"), bool) or zona <= 0:
        return None, "falta la zona del alta"
    ip = _ip(datos.get("ip"))
    if ip is None:
        return None, "el contrato no trae una direccion IP que se pueda asignar"
    plan = _texto(datos.get("plan"))
    if not plan:
        return None, "el contrato no trae el plan"
    cliente = datos.get("cliente") if isinstance(datos.get("cliente"), dict) else {}
    limpio = {c: _texto(cliente.get(c)) for c in
              ("nombre", "apellido", "documento", "correo", "telefono",
               "direccion", "barrio")}
    #  EL DOCUMENTO VIAJA COMO LO DEJO EL CONTRATO, que ya lo limpio sabiendo
    #  de que tipo es. Sacarle aca las letras convertiria un pasaporte en el
    #  documento de otra persona.
    if not limpio["nombre"]:
        return None, "el contrato no trae el nombre del cliente"
    try:
        nombre_en_router = _texto(parametros.nombre_en_router.format(
            nombre=limpio["nombre"], apellido=limpio["apellido"],
            documento=limpio["documento"]))
    except (KeyError, IndexError, ValueError):
        return None, "la regla del nombre en el router esta mal declarada"
    if not nombre_en_router:
        return None, "no se pudo armar el nombre del cliente en el router"
    #  LO QUE COBRO EL TECNICO Y LA ONU QUE INSTALO (26/11/2026). Opcionales:
    #  sin ellos el alta sale igual. Un costo que no es un numero no se arregla.
    costo = datos.get("costo_instalacion")
    if costo in (None, ""):
        costo = None
    elif isinstance(costo, bool) or not isinstance(costo, (int, float, str)):
        return None, "el costo de instalacion no es un numero"
    else:
        try:
            costo = float(str(costo).strip())
        except ValueError:
            return None, "el costo de instalacion no es un numero"
        if not costo >= 0 or costo != costo or costo > 1e9:
            return None, "el costo de instalacion no es un numero valido"
        costo = int(costo) if costo == int(costo) else round(costo, 2)
    serial = re.sub(r"[^A-Za-z0-9]", "", str(datos.get("serial_onu") or "")).upper()[:32]
    return {"zona": zona, "ip": ip, "plan": plan, **limpio,
            "nombre_en_router": nombre_en_router,
            "coordenadas": _punto(datos.get("coordenadas")),
            "nota": _texto(datos.get("nota")),
            "costo_instalacion": costo, "serial_onu": serial}, ""


def _tres_octetos(prefijo) -> str:
    """El /24 de un prefijo declarado, como `a.b.c`, o vacio si no es uno.

    ESTRICTO (auditoria de frontera, 25/11/2026). Se comparaba con
    `startswith`, y un prefijo escrito sin su punto final --`172.16.9`--
    aceptaba tambien `172.16.90.x` a `172.16.99.x`; uno vacio aceptaba todo.
    """
    partes = str(prefijo or "").strip().rstrip(".").split(".")
    if len(partes) != 3 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in partes):
        return ""
    return ".".join(str(int(p)) for p in partes)


def _en_el_rango(config, zona: int, ip: str) -> str:
    """Vacio si esa IP es de los rangos de esa zona; si no, por que no."""
    pool = next((p for p in (getattr(config, "pools_de_ip", None) or [])
                 if int(getattr(p, "zona_id", -1)) == zona), None)
    prefijos = {_tres_octetos(p) for p in (getattr(pool, "prefijos", None) or [])} - {""}
    if not prefijos:
        return "esta zona no tiene rangos de IP declarados"
    if ip.rsplit(".", 1)[0] not in prefijos:
        return "esa IP no es de los rangos declarados para esta zona"
    return ""


def _es_el_nuestro(fila: dict, pb, d: dict) -> bool:
    """Si el cliente que ya tiene esa IP es el de ESTE contrato.

    Manda el nombre en el router: es lo que esta medido que se lee igual que
    se escribio. El documento no esta medido que el proveedor lo guarde tal
    cual, asi que no se exige que coincida -- pero si viene en los dos lados y
    es OTRO, es otra persona, y eso veta.
    """
    campo_nombre = getattr(pb, "campo_nombre_en_router", "") or ""
    campo_doc = getattr(pb, "campo_documento", "") or ""
    leido = _llano(fila.get(campo_nombre)) if campo_nombre else ""
    doc_leido = _digitos(fila.get(campo_doc)) if campo_doc else ""
    doc = _digitos(d.get("documento"))
    if doc and doc_leido and doc != doc_leido:
        return False
    if campo_nombre:
        return bool(leido) and leido == _llano(d["nombre_en_router"])
    #  Sin como leer el nombre, solo el documento puede reconocerlo.
    return bool(doc) and doc == doc_leido


# =============================================================================
#  LAS LECTURAS
# =============================================================================
def _filas_de(herr, comun, config, tenant: str, ip: str) -> list[dict]:
    """Las filas de UNA lista del proveedor con esa IP, con los campos con que
    se reconoce a un cliente renombrados como los de la lista `comun` (la de
    clientes): una lista de instalaciones puede llamarlos distinto."""
    from nucleo.herramientas import http as ejecutor_http

    pb = herr.parametros_de_busqueda_por_ip
    args = dict(getattr(herr, "argumentos_fijos", None) or {})
    args[pb.ip] = ip
    try:
        crudo = ejecutor_http.ejecutar(herr, args, tenant,
                                       variables_tenant=config.variables_tenant)
    except Exception as e:                                   # noqa: BLE001
        raise _NoSePudoLeer(type(e).__name__) from None
    filas = _filas(crudo)
    if comun is None or comun is pb:
        return filas
    pares = [(getattr(pb, c, ""), getattr(comun, c, ""))
             for c in ("campo_id", "campo_nombre_en_router", "campo_documento")]
    return [{**f, **{destino: f.get(origen) for origen, destino in pares
                     if origen and destino and origen != destino}} for f in filas]


def _quien_tiene(h: dict, config, tenant: str, ip: str) -> list[dict]:
    """Quien tiene esa IP en el proveedor: un cliente O una instalacion
    (26/11/2026: una instalacion recien creada no sale en la lista de
    clientes, y su IP esta tan tomada como la de un cliente)."""
    comun = h["buscar"].parametros_de_busqueda_por_ip
    filas = _filas_de(h["buscar"], comun, config, tenant, ip)
    for otra in h.get("buscar_instalaciones") or []:
        filas += _filas_de(otra, comun, config, tenant, ip)
    return filas


def ip_libre_en_el_proveedor(config, tenant: str, ip: str) -> bool:
    """Si NINGUN cliente del proveedor tiene esa IP, preguntado AHORA.

    LA FOTO DE OCUPACION ENVEJECE  --  26/11/2026, la primera prueba real del
    alta. Al firmar, el contrato tomo la primera IP libre segun la foto de la
    noche anterior; la oficina se la habia dado a un cliente nuevo esa misma
    tarde, y el alta la freno («esa IP ya la tiene otro cliente»). La defensa
    funciono, pero el contrato ya estaba firmado con esa IP. Por eso quien
    asigna la IP pregunta aca antes, con la misma herramienta y la misma
    lectura que usa el alta.

    Lanza `_NoSePudoLeer` si no se pudo preguntar: «no se» no es «libre».
    """
    h = _herramientas(config)
    if h["buscar"] is None:
        raise _NoSePudoLeer("SinHerramienta")
    return not _quien_tiene(h, config, tenant, ip)


def _id_del_plan(h: dict, config, tenant: str, plan: str, pa) -> tuple[object, str]:
    """`(id, "")`, o `(None, por que no)`. Igualdad de nombre, no parecido: a
    esta altura el nombre ya es el del catalogo de la empresa."""
    from nucleo.herramientas import http as ejecutor_http

    herr = h["planes"]
    if herr is None:
        return None, "la empresa no declara de donde se lee su catalogo de planes"
    try:
        crudo = ejecutor_http.ejecutar(herr, {}, tenant,
                                       variables_tenant=config.variables_tenant)
    except Exception as e:                                   # noqa: BLE001
        raise _NoSePudoLeer(type(e).__name__) from None
    buscado = _llano(plan)
    ids = [f.get(pa.campo_id_del_plan) for f in _filas(crudo)
           if _llano(f.get(pa.campo_nombre_del_plan)) == buscado
           and f.get(pa.campo_id_del_plan) not in (None, "")]
    if len(ids) == 1:
        return ids[0], ""
    if not ids:
        return None, "ese plan no esta en el catalogo del proveedor"
    return None, "hay mas de un plan con ese nombre en el catalogo del proveedor"


def _estado_de_la_tarea(h: dict, config, tenant: str, tarea: str) -> str:
    """`terminada`, `fallida`, o vacio si no se sabe (todavia, o no se puede)."""
    from nucleo.herramientas import http as ejecutor_http

    herr = h["tarea"]
    tarea = _id_de_tarea(tarea)
    if herr is None or not tarea:
        return ""
    pt = herr.parametros_de_tarea
    try:
        crudo = ejecutor_http.ejecutar(herr, {pt.identificador: tarea}, tenant,
                                       variables_tenant=config.variables_tenant)
    except Exception as e:                                   # noqa: BLE001
        registrar("alta_cliente", "no se pudo leer la tarea del alta", error=e)
        return ""
    return _clasificar(pt, crudo)[0]


def _clasificar(pt, crudo) -> tuple[str, str]:
    """`(terminada|fallida|"", mensaje tapado)` de lo que devolvio la tarea.

    EL ESTADO SE LEE DONDE VIENE (27/11/2026). Medido ese dia: el primer
    proveedor lo anida (`{"task": {"status": ..., "result": ...}}`) y la
    configuracion lo buscaba arriba: nunca se veia, y el alta solo se enteraba
    leyendo despues al cliente. Se acepta un nivel ("task.status").
    """
    from nucleo.herramientas.http import _leer_anidado

    if not isinstance(crudo, dict):
        return "", ""
    estado = str(_leer_anidado(crudo, pt.campo_estado) or "")
    mensaje = ""
    if getattr(pt, "campo_resultado", ""):
        valor = _leer_anidado(crudo, pt.campo_resultado)
        if isinstance(valor, str):
            mensaje = valor
        elif isinstance(valor, dict):
            #  Un resultado en bloque: sus textos, sin suponer como se llaman.
            mensaje = " · ".join(str(v) for v in valor.values() if isinstance(v, str))
        #  Lo que dice el proveedor, tapado: numeros largos y correos fuera.
        mensaje = re.sub(r"[\w.+-]+@[\w.-]+", "<correo>", mensaje)
        mensaje = re.sub(r"\d{6,}", "<n>", mensaje)[:160]
    if estado in (pt.estados_fallida or []):
        return "fallida", mensaje
    if estado in (pt.estados_terminada or []):
        return "terminada", mensaje
    return "", mensaje


def _leer_tarea(h: dict, config, tenant: str, tarea: str) -> tuple[str, str]:
    """`(estado, mensaje)` de una tarea, o ("", "") si no se pudo leer."""
    from nucleo.herramientas import http as ejecutor_http

    herr = h["tarea"]
    tarea = _id_de_tarea(tarea)
    if herr is None or not tarea:
        return "", ""
    pt = herr.parametros_de_tarea
    try:
        crudo = ejecutor_http.ejecutar(herr, {pt.identificador: tarea}, tenant,
                                       variables_tenant=config.variables_tenant)
    except Exception as e:                                   # noqa: BLE001
        registrar("activar_cliente", "no se pudo leer la tarea", error=e)
        return "", ""
    return _clasificar(pt, crudo)


def _mirar(h: dict, config, tenant: str, d: dict, tarea: str) -> ResultadoAlta | None:
    """UNA mirada DESPUES de haber pedido: el resultado si ya se sabe, o
    `None` si hay que seguir esperando.

    Solo se llama cuando el pedido pudo haber salido. Por eso una IP tomada
    por una ficha que no se reconoce NO es «ocupada por otro»: es
    NO_RECONOCIDO. Antes de pedir estaba libre.
    """
    pb = h["buscar"].parametros_de_busqueda_por_ip
    try:
        filas = _quien_tiene(h, config, tenant, d["ip"])
    except _NoSePudoLeer:
        return None                    # no saber no es que no este: se sigue
    nuestro = next((f for f in filas if _es_el_nuestro(f, pb, d)), None)
    if nuestro is not None:
        return ResultadoAlta(CREADO, id_cliente=str(nuestro.get(pb.campo_id) or ""),
                             tarea=tarea)
    if filas:
        return ResultadoAlta(
            NO_RECONOCIDO,
            "despues de pedir, la IP quedo tomada por un cliente que no se "
            "pudo reconocer como el de este contrato", tarea=tarea)

    #  LA IP SIGUE LIBRE. Solo el proveedor puede decir que no va a aparecer.
    estado = _estado_de_la_tarea(h, config, tenant, tarea)
    if estado == "":
        return None
    #  DIJO ALGO, Y HAY QUE VOLVER A MIRAR ANTES DE CREERLE: la lectura de
    #  arriba pudo ser de un instante antes de que terminara.
    try:
        filas = _quien_tiene(h, config, tenant, d["ip"])
    except _NoSePudoLeer:
        return None
    nuestro = next((f for f in filas if _es_el_nuestro(f, pb, d)), None)
    if nuestro is not None:
        return ResultadoAlta(CREADO, tarea=tarea,
                             id_cliente=str(nuestro.get(pb.campo_id) or ""))
    if filas:
        return ResultadoAlta(
            NO_RECONOCIDO,
            "despues de pedir, la IP quedo tomada por un cliente que no se "
            "pudo reconocer como el de este contrato", tarea=tarea)
    if estado == "fallida":
        return ResultadoAlta(FALLO, "el proveedor no pudo crear al cliente",
                             tarea=tarea)
    return ResultadoAlta(
        FALLO, "el proveedor dio el trabajo por terminado y el cliente no existe",
        tarea=tarea)


def comprobar(config, tenant: str, *, datos, tarea: str = "") -> ResultadoAlta:
    """Como quedo un alta que ya se pidio. NO crea nada: solo lee.

    Es lo que el backend llama para un contrato que quedo «en curso». Devuelve
    CREADO, NO_RECONOCIDO, FALLO o EN_CURSO.
    """
    h = _herramientas(config)
    if h["crear"] is None or h["buscar"] is None:
        return ResultadoAlta(SIN_HERRAMIENTA,
                             "la empresa no declara como se crea ni como se busca un cliente")
    d, motivo = leer_datos(datos, h["crear"].parametros_de_alta)
    if d is None:
        return ResultadoAlta(DATOS_INVALIDOS, motivo)
    tarea = _id_de_tarea(tarea)
    visto = _mirar(h, config, tenant, d, tarea) or ResultadoAlta(
        EN_CURSO, "se pidio y el cliente todavia no aparece", tarea=tarea)
    visto.emitido = True
    return visto


# =============================================================================
#  CREAR
# =============================================================================
def _lo_rechazo(e: BaseException) -> bool:
    """Si ese error es el proveedor DICIENDO QUE NO al pedido.

    Un 4xx es una respuesta: leyo el pedido y lo rechazo, no hay cliente. Todo
    lo demas --un corte, un 5xx, una respuesta que no se pudo leer-- no dice
    si lo aplico o no. El 408 tampoco: es el servidor cansado de esperar.
    """
    codigo = getattr(getattr(e, "response", None), "status_code", None)
    return isinstance(codigo, int) and 400 <= codigo < 500 and codigo != 408


def crear(config, tenant: str, *, actor: str, origen: str, datos,
          espera_s: float = ESPERA_S,
          intervalo_s: float = INTERVALO_S) -> ResultadoAlta:
    """Crea al cliente en el proveedor, una sola vez, y confirma leyendolo.

    `origen` identifica EL PEDIDO --el contrato y su numero-- y es la base de
    la clave idempotente. Lo arma la ruta, no quien llama.

    NO HAY «REINTENTAR». Una operacion que quedo fallida no se vuelve a
    ejecutar por este camino: repetir una creacion es crear dos. Si una
    persona decide insistir, quien llama abre un pedido NUEVO --otro numero--,
    y este pedido nuevo empieza, como todos, mirando quien tiene la IP.
    """
    from nucleo.herramientas import http as ejecutor_http
    from nucleo.seguridad import frontera, idempotencia, interruptor, secretos

    h = _herramientas(config)
    if h["crear"] is None:
        return ResultadoAlta(SIN_HERRAMIENTA,
                             "la empresa no declara ninguna herramienta que cree un cliente")
    if h["buscar"] is None:
        #  SIN PODER LEER NO SE CREA: no habria como saber si la IP esta
        #  tomada, ni como confirmar despues que el cliente quedo.
        return ResultadoAlta(SIN_HERRAMIENTA,
                             "la empresa no declara como se busca un cliente por su IP")
    herr = h["crear"]
    pa = herr.parametros_de_alta
    pb = h["buscar"].parametros_de_busqueda_por_ip

    d, motivo = leer_datos(datos, pa)
    if d is None:
        registrar("alta_cliente", "los datos del alta no sirven: no se crea")
        return ResultadoAlta(DATOS_INVALIDOS, motivo, referencia=origen)

    fuera = _en_el_rango(config, d["zona"], d["ip"])
    if fuera:
        return ResultadoAlta(IP_FUERA_DEL_RANGO, fuera, referencia=origen)

    #  LA IP PODRIA SER LA DE UN CLIENTE CON LA SUYA MAL ESCRITA (25/11/2026).
    #  El proveedor no lo sabe --tiene escrita otra direccion--, asi que la
    #  lectura viva de abajo la daria por libre. Si la empresa lo encendio, se
    #  frena aca, con la ultima lectura de la ocupacion.
    if getattr(config, "contar_ip_mal_escritas", False):
        from nucleo.herramientas.ocupacion_ip import sombra_de_mal_escritas

        prefijo, ultimo = d["ip"].rsplit(".", 1)
        sombra = sombra_de_mal_escritas(getattr(config, "ocupacion_ip", None) or {})
        if int(ultimo) in sombra.get(prefijo.split(".")[2], set()):
            return ResultadoAlta(
                IP_OCUPADA, "esa IP podria ser la de un cliente que tiene su IP mal "
                            "escrita en el proveedor", referencia=origen)

    #  1. ¿QUIEN TIENE ESA IP?  --  antes que nada, y es la segunda defensa.
    try:
        filas = _quien_tiene(h, config, tenant, d["ip"])
    except _NoSePudoLeer as e:
        registrar("alta_cliente", "no se pudo preguntar quien tiene la IP: no se crea")
        return ResultadoAlta(NO_SE_PUDO_COMPROBAR,
                             f"no se pudo comprobar si la IP esta libre ({e})",
                             referencia=origen)
    nuestro = next((f for f in filas if _es_el_nuestro(f, pb, d)), None)
    if nuestro is not None:
        return ResultadoAlta(YA_ESTABA, "esa IP ya la tiene este cliente",
                             referencia=origen,
                             id_cliente=str(nuestro.get(pb.campo_id) or ""))
    if filas:
        return ResultadoAlta(IP_OCUPADA, "esa IP ya la tiene otro cliente",
                             referencia=origen)

    #  2. EL PLAN, en el catalogo vivo del proveedor.
    try:
        plan_id, motivo = _id_del_plan(h, config, tenant, d["plan"], pa)
    except _NoSePudoLeer as e:
        return ResultadoAlta(NO_SE_PUDO_COMPROBAR,
                             f"no se pudo leer el catalogo de planes ({e})",
                             referencia=origen)
    if plan_id is None:
        return ResultadoAlta(PLAN_DESCONOCIDO, motivo, referencia=origen)

    #  3. EL INTERRUPTOR, sin cache y pegado a la escritura (CLAUDE.md 8). La
    #     puerta humana no lo consulta: se consulta aca. Falla cerrado.
    try:
        veredicto = interruptor.veredicto(tenant)
    except Exception as e:                                   # noqa: BLE001
        registrar("alta_cliente", "no se pudo leer el interruptor: NO se crea",
                  error=e)
        return ResultadoAlta(BLOQUEADO, "no se pudo comprobar el interruptor",
                             referencia=origen)
    if not veredicto.permitido:
        #  EL PORQUE QUE ESCRIBIO QUIEN LO BAJO queda en la auditoria, no en
        #  la respuesta: esto lo lee un tecnico en la calle.
        interruptor.anotar_bloqueo(tenant, actor=actor, recurso="alta_de_cliente",
                                   motivo=f"{veredicto.estado}: {veredicto.motivo}")
        return ResultadoAlta(BLOQUEADO, "el interruptor de la empresa esta detenido",
                             referencia=origen)

    #  4. EL CUERPO, con los nombres que ESTE proveedor declara. Un dato vacio
    #     NO viaja: una clave con valor nulo no es lo mismo que una ausente, y
    #     ya costo un diagnostico.
    valores = {**d, "plan": plan_id}
    args = dict(getattr(herr, "argumentos_fijos", None) or {})
    args[pa.zona] = d["zona"]
    for dato, campo in pa.campos.items():
        if valores.get(dato) not in (None, ""):
            args[campo] = valores[dato]

    #  LOS SECRETOS DE LA EMPRESA VAN APARTE: no entran en la huella de la
    #  operacion ni en nada que se guarde. Se suman al cuerpo dentro de
    #  `_hacer`, que es lo unico que los ve.
    reservado: dict = {}
    avisos: list[str] = []
    for campo, nombre in (pa.secretos or {}).items():
        try:
            valor = secretos.obtener(tenant, nombre)
        except Exception as e:                               # noqa: BLE001
            registrar("alta_cliente", "no se pudo leer un secreto del alta",
                      error=e)
            valor = None
        if valor:
            reservado[campo] = valor
        else:
            avisos.append(f"no se mando '{campo}': el secreto '{nombre}' no esta "
                          f"cargado en las credenciales de la empresa")

    def _fin(estado: str, motivo: str = "", **mas) -> ResultadoAlta:
        """Un resultado de DESPUES de haber llegado al registro de operaciones."""
        return ResultadoAlta(estado, motivo, referencia=origen, avisos=avisos,
                             emitido=True, **mas)

    def _hacer():
        crudo = ejecutor_http.ejecutar(herr, {**args, **reservado}, tenant,
                                       variables_tenant=config.variables_tenant)
        #  SE GUARDA UN ACUSE, NO EL CUERPO DEL PROVEEDOR. Lo que devuelve
        #  esto queda en el registro de operaciones tal cual, y la respuesta
        #  de un alta puede traer la ficha de una persona.
        tarea = ""
        if pa.campo_tarea and isinstance(crudo, dict):
            tarea = _id_de_tarea(crudo.get(pa.campo_tarea))
        return {"pedido": True, "tarea": tarea}

    tarea = ""
    try:
        with frontera.humana(tenant, herr.nombre, actor=actor,
                             evidencia=origen, origen=origen):
            #  CLAVE FIJA POR PEDIDO, sin la huella de los argumentos. Aca es
            #  lo correcto: el contrato no cambia, y si los argumentos de un
            #  mismo pedido cambiaran, eso NO es otra operacion -- es un
            #  motivo para no salir.
            #
            #  Y SIN `reintentar_fallida`: lo que fallo no se repite aca.
            res = idempotencia.ejecutar(tenant, herr.nombre, args, origen, _hacer,
                                        clave=f"{origen}|{herr.nombre}")
    except ejecutor_http.ErrorHerramientaHttp as e:
        #  EL EJECUTOR SE NEGO ANTES DE LA RED: la guarda de un entorno que no
        #  escribe afuera, una credencial que falta, una ruta sin armar. Nada
        #  salio. El texto es fijo: el del error nombra piezas de la
        #  configuracion y no es para una pantalla.
        registrar("alta_cliente", "el ejecutor no dejo salir el alta", error=e)
        return _fin(BLOQUEADO, "el alta no salio: el ejecutor la freno antes "
                               "de llegar al proveedor")
    except frontera.AccionExternaNoAutorizada as e:
        registrar("alta_cliente", "la frontera no autorizo el alta", error=e)
        return _fin(BLOQUEADO, "la frontera no autorizo el alta")
    except Exception as e:                                   # noqa: BLE001
        registrar("alta_cliente", "el pedido del alta volvio con error", error=e)
        if _lo_rechazo(e):
            #  EL PROVEEDOR LEYO EL PEDIDO Y DIJO QUE NO. No hay cliente.
            return _fin(FALLO, "el proveedor rechazo el pedido")
        #  SALIO Y NO SE SABE SI LLEGO. No es un fallo: se mira, igual que si
        #  hubiera contestado bien. Si el cliente no aparece queda EN CURSO,
        #  y lo decide quien llama --nunca «fallo, proba de nuevo»--.
        res = None

    if res is not None:
        if isinstance(res.respuesta, dict):
            tarea = _id_de_tarea(res.respuesta.get("tarea"))
        if not res.ejecutada and res.decision not in ("repetida", "en_curso", "fallida"):
            #  El registro no dejo: la clave se uso con otros argumentos, o
            #  contesto algo que no se entiende. Nada salio en ESTA pasada.
            return _fin(BLOQUEADO, "el registro de operaciones no dejo salir "
                                   "este pedido")
        #  `repetida`, `en_curso` y `fallida` son las tres formas de «este
        #  pedido ya se habia mandado»: no se manda otra vez, se mira.

    #  5. CONFIRMAR LEYENDO. Hasta `espera_s`; si no aparece, queda en curso y
    #     `comprobar` lo vuelve a mirar despues.
    limite = time.monotonic() + max(0.0, float(espera_s))
    sin_reconocer = None
    while True:
        visto = _mirar(h, config, tenant, d, tarea)
        if visto is not None and visto.estado != NO_RECONOCIDO:
            visto.referencia, visto.avisos, visto.emitido = origen, avisos, True
            if visto.estado == CREADO:
                registrar("alta_cliente", "el cliente quedo creado en el proveedor")
            return visto
        #  UNA FICHA SIN RECONOCER PUEDE SER LA NUESTRA A MEDIO ARMAR: el
        #  proveedor crea en segundo plano. Se sigue mirando hasta el limite,
        #  y recien ahi se dice que no se reconocio.
        sin_reconocer = visto or sin_reconocer
        if time.monotonic() >= limite:
            if sin_reconocer is not None:
                sin_reconocer.referencia, sin_reconocer.avisos = origen, avisos
                sin_reconocer.emitido = True
                return sin_reconocer
            return _fin(EN_CURSO, "se pidio y el cliente todavia no aparece",
                        tarea=tarea)
        time.sleep(max(0.0, float(intervalo_s)))


# =============================================================================
#  LA ACTIVACION  --  26/11/2026
# =============================================================================
#  El usuario: «en instalaciones se crea instalacion y despues un encargado
#  valida si todo esta bien y activa, que pasa a cliente». El alta crea la
#  INSTALACION; esto la pasa a cliente, cuando una persona la aprobo en
#  Dexter. Es la escritura que DA SERVICIO, asi que sale por la puerta
#  humana (quien valido), con clave fija por pedido, sin reintentar lo que
#  fallo, y se confirma LEYENDO: aparecer en la lista de clientes.

def _el_numero(valor) -> str:
    s = str(valor if valor is not None else "").strip()
    return s if s.isdigit() else ""


def activar(config, tenant: str, *, actor: str, origen: str, datos, id_servicio,
            espera_s: float = ESPERA_S, intervalo_s: float = INTERVALO_S) -> ResultadoAlta:
    """Pasa a cliente la instalacion de ESTE contrato. Ver el encabezado."""
    from nucleo.herramientas import http as ejecutor_http
    from nucleo.seguridad import frontera, idempotencia, interruptor

    h = _herramientas(config)
    if None in (h["activar"], h["buscar"], h["crear"]) or not h["buscar_instalaciones"]:
        return ResultadoAlta(SIN_HERRAMIENTA, "la empresa no declara como se pasa una "
                                              "instalacion a cliente", referencia=origen)
    numero = _el_numero(id_servicio)
    if not numero:
        return ResultadoAlta(DATOS_INVALIDOS, "falta el numero de servicio de la instalacion",
                             referencia=origen)
    d, por_que = leer_datos(datos, h["crear"].parametros_de_alta)
    if d is None:
        return ResultadoAlta(DATOS_INVALIDOS, por_que, referencia=origen)
    comun = h["buscar"].parametros_de_busqueda_por_ip

    #  1. ¿YA ES CLIENTE? Entonces no hay nada que activar.
    try:
        if any(_el_numero(f.get(comun.campo_id)) == numero
               for f in _filas_de(h["buscar"], comun, config, tenant, d["ip"])):
            return ResultadoAlta(YA_ESTABA, "esa instalacion ya es cliente",
                                 referencia=origen, id_cliente=numero)
        instalaciones = []
        for herr in h["buscar_instalaciones"]:
            instalaciones += _filas_de(herr, comun, config, tenant, d["ip"])
    except _NoSePudoLeer as e:
        return ResultadoAlta(NO_SE_PUDO_COMPROBAR,
                             f"no se pudo leer el proveedor ({e})", referencia=origen)
    #  2. LA INSTALACION TIENE QUE ESTAR, CON ESE NUMERO Y DE ESTE CONTRATO.
    if not any(_el_numero(f.get(comun.campo_id)) == numero and _es_el_nuestro(f, comun, d)
               for f in instalaciones):
        return ResultadoAlta(NO_ENCONTRADA, "no hay en el proveedor una instalacion de "
                                            "este contrato con ese numero", referencia=origen)

    #  3. EL INTERRUPTOR, sin cache y pegado a la escritura.
    try:
        veredicto = interruptor.veredicto(tenant)
    except Exception as e:                                   # noqa: BLE001
        registrar("activar_cliente", "no se pudo leer el interruptor: NO se activa", error=e)
        return ResultadoAlta(BLOQUEADO, "no se pudo comprobar el interruptor", referencia=origen)
    if not veredicto.permitido:
        interruptor.anotar_bloqueo(tenant, actor=actor, recurso="activar_cliente",
                                   motivo=f"{veredicto.estado}: {veredicto.motivo}")
        return ResultadoAlta(BLOQUEADO, "el interruptor de la empresa esta detenido",
                             referencia=origen)

    herr = h["activar"]
    args = dict(getattr(herr, "argumentos_fijos", None) or {})
    args[herr.parametros_de_activacion.campo_servicios] = [int(numero)]

    def _fin(estado: str, motivo: str = "") -> ResultadoAlta:
        return ResultadoAlta(estado, motivo, referencia=origen, id_cliente=numero, emitido=True)

    campo_tarea = getattr(herr.parametros_de_activacion, "campo_tarea", "") or ""

    def _hacer():
        crudo = ejecutor_http.ejecutar(herr, dict(args), tenant,
                                       variables_tenant=config.variables_tenant)
        #  EL ID DE LA TAREA (27/11/2026): con el se sabe si el proveedor dice
        #  que la activacion fallo. Es lo unico de la respuesta que se guarda.
        tarea = _id_de_tarea(crudo.get(campo_tarea)) if campo_tarea and isinstance(crudo, dict) else ""
        return {"pedido": True, "tarea": tarea}

    try:
        with frontera.humana(tenant, herr.nombre, actor=actor, evidencia=origen, origen=origen):
            res = idempotencia.ejecutar(tenant, herr.nombre, args, origen, _hacer,
                                        clave=f"{origen}|{herr.nombre}")
    except ejecutor_http.ErrorHerramientaHttp as e:
        registrar("activar_cliente", "el ejecutor no dejo salir la activacion", error=e)
        return _fin(BLOQUEADO, "la activacion no salio: el ejecutor la freno antes de "
                               "llegar al proveedor")
    except frontera.AccionExternaNoAutorizada as e:
        registrar("activar_cliente", "la frontera no autorizo la activacion", error=e)
        return _fin(BLOQUEADO, "la frontera no autorizo la activacion")
    except Exception as e:                                   # noqa: BLE001
        registrar("activar_cliente", "el pedido de activacion volvio con error", error=e)
        if _lo_rechazo(e):
            return _fin(FALLO, "el proveedor rechazo la activacion")
        res = None                     # salio y no se sabe si llego: se mira
    if res is not None and not res.ejecutada and res.decision not in (
            "repetida", "en_curso", "fallida"):
        return _fin(BLOQUEADO, "el registro de operaciones no dejo salir este pedido")

    #  4. CONFIRMAR LEYENDO: que aparezca en la lista de CLIENTES. Y mientras,
    #  la TAREA del proveedor (27/11/2026): medido ese dia, un «activar» que el
    #  proveedor acepto no paso la instalacion a cliente, y Dexter solo lo supo
    #  a los minutos. Si la tarea dice que fallo, se dice ya, con su mensaje.
    tarea = str(((res.respuesta if res is not None else None) or {}).get("tarea") or "")
    limite = time.monotonic() + max(0.0, float(espera_s))
    while True:
        visto = comprobar_activacion(config, tenant, datos=datos, id_servicio=numero)
        if visto.estado == ACTIVADO:
            registrar("activar_cliente", "la instalacion quedo como cliente")
            return _fin(ACTIVADO)
        if tarea:
            estado_tarea, mensaje = _leer_tarea(h, config, tenant, tarea)
            if estado_tarea == "fallida":
                registrar("activar_cliente", "la tarea del proveedor fallo")
                return _fin(FALLO, "la tarea del proveedor fallo"
                            + (f": {mensaje}" if mensaje else ""))
        if time.monotonic() >= limite:
            r = _fin(EN_CURSO, "se pidio y todavia no aparece como cliente")
            r.tarea = tarea
            return r
        time.sleep(max(0.0, float(intervalo_s)))


def comprobar_activacion(config, tenant: str, *, datos, id_servicio) -> ResultadoAlta:
    """Si la instalacion ya es cliente. SOLO LEE."""
    h = _herramientas(config)
    if h["buscar"] is None or h["crear"] is None:
        return ResultadoAlta(SIN_HERRAMIENTA, "la empresa no declara como se lee un cliente")
    numero = _el_numero(id_servicio)
    d, por_que = leer_datos(datos, h["crear"].parametros_de_alta)
    if not numero or d is None:
        return ResultadoAlta(DATOS_INVALIDOS, por_que or "falta el numero de servicio")
    comun = h["buscar"].parametros_de_busqueda_por_ip
    try:
        filas = _filas_de(h["buscar"], comun, config, tenant, d["ip"])
    except _NoSePudoLeer as e:
        return ResultadoAlta(NO_SE_PUDO_COMPROBAR, f"no se pudo leer el proveedor ({e})")
    if any(_el_numero(f.get(comun.campo_id)) == numero for f in filas):
        return ResultadoAlta(ACTIVADO, id_cliente=numero)
    return ResultadoAlta(EN_CURSO, "todavia no aparece como cliente", id_cliente=numero)


# =============================================================================
#  COMPLETAR AL CLIENTE ACTIVADO  --  26/11/2026
# =============================================================================
#  Decision del usuario: el costo de instalacion que cobro el tecnico y el
#  serial de la ONU se escriben CUANDO LA OFICINA APRUEBA y la instalacion pasa
#  a cliente. Medido ese dia: el proveedor no deja editar una instalacion por
#  su API (las instalaciones son otra lista; `GET /api/clientes/<id>/` da 404),
#  y el formulario web de editarla trae ~70 campos, algunos rellenados con
#  valores que el proveedor no tiene guardados: reenviarlo cambiaria datos.
#  Sobre el CLIENTE, el PUT parcial esta medido (aplica y no pisa lo demas).
#
#  Las mismas reglas que activar: puerta HUMANA de quien aprobo, solo si es
#  cliente con ese numero y de ESTE contrato, una vez por pedido, y se confirma
#  LEYENDO que quedaron los valores.
def _costo(valor) -> str | None:
    """El costo como texto con dos decimales, o None si no es un numero >= 0."""
    try:
        n = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return f"{n:.2f}" if n >= 0 else None


def _serial(valor) -> str:
    return re.sub(r"[^A-Z0-9:-]", "", str(valor or "").upper())[:40]


def _mismo_costo(a, b) -> bool:
    x, y = _costo(a), _costo(b)
    return x is not None and x == y


def completar(config, tenant: str, *, actor: str, origen: str, datos, id_servicio,
              valores) -> ResultadoAlta:
    """Escribe el costo y el serial en el cliente recien activado. Ver arriba."""
    from nucleo.herramientas import http as ejecutor_http
    from nucleo.seguridad import frontera, idempotencia, interruptor

    h = _herramientas(config)
    herr = h["completar"]
    if herr is None or h["buscar"] is None or h["crear"] is None:
        return ResultadoAlta(SIN_HERRAMIENTA, "la empresa no declara como se completa un "
                                              "cliente", referencia=origen)
    numero = _el_numero(id_servicio)
    d, por_que = leer_datos(datos, h["crear"].parametros_de_alta)
    if not numero or d is None:
        return ResultadoAlta(DATOS_INVALIDOS, por_que or "falta el numero de servicio",
                             referencia=origen)
    valores = valores if isinstance(valores, dict) else {}
    pc = herr.parametros_de_completar
    quiero: dict[str, str] = {}
    if valores.get("costo_instalacion") not in (None, "") and "costo_instalacion" in pc.campos:
        costo = _costo(valores["costo_instalacion"])
        if costo is None:
            return ResultadoAlta(DATOS_INVALIDOS, "el costo de instalacion no es un numero",
                                 referencia=origen)
        quiero["costo_instalacion"] = costo
    if valores.get("serial_onu") and "serial_onu" in pc.campos:
        serial = _serial(valores["serial_onu"])
        if not serial:
            return ResultadoAlta(DATOS_INVALIDOS, "el serial de la ONU no es valido",
                                 referencia=origen)
        quiero["serial_onu"] = serial
    if not quiero:
        return ResultadoAlta(NADA_QUE_COMPLETAR, "no hay costo ni serial que escribir",
                             referencia=origen, id_cliente=numero)
    comun = h["buscar"].parametros_de_busqueda_por_ip

    def _fila():
        for f in _filas_de(h["buscar"], comun, config, tenant, d["ip"]):
            if _el_numero(f.get(comun.campo_id)) == numero and _es_el_nuestro(f, comun, d):
                return f
        return None

    def _ya_estan(f) -> bool:
        return all((_mismo_costo(f.get(pc.campos[k]), v) if k == "costo_instalacion"
                    else _serial(f.get(pc.campos[k])) == v) for k, v in quiero.items())

    #  1. TIENE QUE SER CLIENTE, con ese numero y de ESTE contrato.
    try:
        fila = _fila()
    except _NoSePudoLeer as e:
        return ResultadoAlta(NO_SE_PUDO_COMPROBAR, f"no se pudo leer el proveedor ({e})",
                             referencia=origen)
    if fila is None:
        return ResultadoAlta(NO_ENCONTRADA, "no hay en el proveedor un cliente de este contrato "
                                            "con ese numero", referencia=origen)
    if _ya_estan(fila):
        return ResultadoAlta(YA_ESTABA, "el cliente ya tiene esos valores", referencia=origen,
                             id_cliente=numero)

    #  2. EL INTERRUPTOR, sin cache y pegado a la escritura.
    try:
        veredicto = interruptor.veredicto(tenant)
    except Exception as e:                                   # noqa: BLE001
        registrar("completar_cliente", "no se pudo leer el interruptor: NO se escribe", error=e)
        return ResultadoAlta(BLOQUEADO, "no se pudo comprobar el interruptor", referencia=origen)
    if not veredicto.permitido:
        interruptor.anotar_bloqueo(tenant, actor=actor, recurso="completar_cliente",
                                   motivo=f"{veredicto.estado}: {veredicto.motivo}")
        return ResultadoAlta(BLOQUEADO, "el interruptor de la empresa esta detenido",
                             referencia=origen)

    #  3. UNA VEZ, POR LA PUERTA HUMANA.
    args = dict(getattr(herr, "argumentos_fijos", None) or {})
    args[pc.campo_servicio] = numero
    for k, v in quiero.items():
        args[pc.campos[k]] = v

    def _fin(estado: str, motivo: str = "") -> ResultadoAlta:
        return ResultadoAlta(estado, motivo, referencia=origen, id_cliente=numero, emitido=True)

    def _hacer():
        ejecutor_http.ejecutar(herr, dict(args), tenant, variables_tenant=config.variables_tenant)
        return {"pedido": True}

    try:
        with frontera.humana(tenant, herr.nombre, actor=actor, evidencia=origen, origen=origen):
            res = idempotencia.ejecutar(tenant, herr.nombre, args, origen, _hacer,
                                        clave=f"{origen}|{herr.nombre}")
    except ejecutor_http.ErrorHerramientaHttp as e:
        registrar("completar_cliente", "el ejecutor no dejo salir el pedido", error=e)
        return ResultadoAlta(BLOQUEADO, "no salio: el ejecutor lo freno antes de llegar al "
                                        "proveedor", referencia=origen, id_cliente=numero)
    except frontera.AccionExternaNoAutorizada as e:
        registrar("completar_cliente", "la frontera no autorizo el pedido", error=e)
        return ResultadoAlta(BLOQUEADO, "la frontera no autorizo el pedido", referencia=origen,
                             id_cliente=numero)
    except Exception as e:                                   # noqa: BLE001
        registrar("completar_cliente", "el pedido volvio con error", error=e)
        if _lo_rechazo(e):
            return _fin(FALLO, "el proveedor rechazo el pedido")
        res = None                     # salio y no se sabe si llego: se mira
    if res is not None and not res.ejecutada and res.decision not in (
            "repetida", "en_curso", "fallida"):
        return _fin(BLOQUEADO, "el registro de operaciones no dejo salir este pedido")

    #  4. CONFIRMAR LEYENDO que quedaron los valores.
    try:
        fila = _fila()
    except _NoSePudoLeer:
        fila = None
    if fila is not None and _ya_estan(fila):
        registrar("completar_cliente", "el cliente quedo con el costo y el serial")
        return _fin(COMPLETADO)
    return _fin(EN_CURSO, "se pidio y todavia no se leen los valores")
