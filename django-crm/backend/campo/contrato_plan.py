# -*- coding: utf-8 -*-
"""
================================================================================
 QUE PLAN ES, Y EN QUE SERVIDORES VA  --  25/11/2026
================================================================================
Decision del usuario: el plan del contrato *«se compara con el plan que aparece
en la descripcion del ticket»*, y el corte *«se lo pregunta el tecnico al
cliente y lo deja seleccionado en la app»*. Plan + corte dicen el servidor.

EL TICKET NO TRAE EL NOMBRE DEL CATALOGO
----------------------------------------
Trae lo que eligio el cliente en el formulario, con su precio: «FAMILIA 200MB -
$89.900». En el proveedor ese plan se llama «PLAN FAMILIA». Compararlos por
igualdad no encuentra nada; compararlos «a ojo» con un modelo seria pedirle que
decida que se le va a cobrar a un cliente. Lo hace el codigo (CLAUDE.md 4, «el
modelo compone, el codigo calcula»), con una regla que se puede leer:

    un plan del catalogo es EL del texto si todas las palabras que lo
    DISTINGUEN de los demas planes estan en el texto.

«FAMILIA» distingue a PLAN FAMILIA; «200MB» y «SV» distinguen a PLAN FIBRA
OPTICA 200MB SV. El texto de arriba trae FAMILIA y 200MB: el primero se cumple
entero, el segundo no (falta SV). Gana uno solo.

SI NO ES UNO SOLO, NO ADIVINA
-----------------------------
Ninguno o varios devuelven None, y la pantalla le muestra al tecnico la lista
para que elija. Un plan elegido por aproximacion es un cliente pagando otra
cosa que la que contrato.

CONTRA QUE CATALOGO
-------------------
Contra los planes que la empresa VENDE (`planes_venta` de su configuracion, en
el motor), no contra el catalogo tecnico del proveedor: ese trae decenas de
variantes viejas y de promocion, y `planes_venta` es ademas el unico lugar que
dice en que zonas va cada plan.

EL CORTE NO ES UN CAMPO: ES EL SERVIDOR
---------------------------------------
En el proveedor el dia de corte de la factura es la zona («CORTE 15 - SERVIDOR
1», «CORTE 30 - SERVIDOR 1»). Entonces al tecnico se le muestran solo los
servidores DE ESE PLAN, y elegir el corte es elegir entre ellos. Lo que el
ticket diga del corte es una SUGERENCIA: se le pregunta al cliente.

Si el motor no contesta, no hay catalogo y nada de esto se aplica: el contrato
se firma con el plan tal como esta escrito. No poder preguntar no puede dejar
a un tecnico sin firmar en la casa del cliente; la comprobacion que no se puede
saltear va en el alta, que es donde esta el efecto.
================================================================================
"""
from __future__ import annotations

import logging
import os
import re
import unicodedata

import requests

logger = logging.getLogger(__name__)

#: Igual que el resto de las llamadas al motor desde el backend.
ESPERA_MAXIMA = 10

#: Cuanto se recuerda el catalogo. Cambia cuando alguien edita los planes de
#: venta, no en cada contrato: cinco minutos alcanzan para no preguntar dos
#: veces en la misma firma, y para que un cambio se vea casi enseguida.
VIGENCIA_S = 300

#: Palabras que estan en el nombre de cualquier plan y no nombran a ninguno.
_RELLENO = frozenset({"plan", "de", "del", "el", "la", "internet", "con"})


def _motor():
    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    cabeceras = {}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token
    return base, cabeceras


# =============================================================================
#  EL CATALOGO
# =============================================================================
def catalogo_de(org) -> list[dict] | None:
    """Los planes que la empresa vende: `[{"nombre": str, "zonas": [int]}]`.

    None cuando NO SE PUDO SABER (sin empresa en el motor, el motor no
    contesta). Una lista vacia es otra cosa: la empresa no cargo ninguno.
    Nunca levanta.
    """
    from django.core.cache import cache

    from operaciones.areas_del_tenant import tenant_de

    tenant = tenant_de(org)
    if not tenant:
        return None
    clave = f"contrato:planes_de_venta:{tenant}"
    try:
        guardado = cache.get(clave)
        if guardado is not None:
            return guardado
    except Exception:                                        # noqa: BLE001
        pass

    base, cabeceras = _motor()
    try:
        r = requests.get(f"{base}/configuracion/planes-venta", headers=cabeceras,
                         params={"tenant": tenant}, timeout=ESPERA_MAXIMA)
    except Exception as e:                                   # noqa: BLE001
        #  Por TIPO y no `str(e)`: el texto de un error de red trae la URL.
        logger.info("Contrato: no se pudo leer el catalogo de planes (%s)",
                    type(e).__name__)
        return None
    if not r.ok:
        logger.info("Contrato: el motor respondio %s al catalogo de planes",
                    r.status_code)
        return None
    try:
        crudo = (r.json() or {}).get("planes_venta") or []
    except ValueError:
        return None

    planes, vistos = [], set()
    for p in crudo:
        if not isinstance(p, dict):
            continue
        nombre = str(p.get("nombre_wisphub") or p.get("nombre") or "").strip()
        if not nombre or nombre in vistos:
            continue
        vistos.add(nombre)
        zonas = [z for z in (p.get("zonas") or [])
                 if isinstance(z, int) and not isinstance(z, bool)]
        planes.append({"nombre": nombre, "zonas": zonas})
    try:
        cache.set(clave, planes, VIGENCIA_S)
    except Exception:                                        # noqa: BLE001
        pass
    return planes


# =============================================================================
#  RECONOCER EL PLAN
# =============================================================================
def _palabras(texto) -> list[str]:
    """Las palabras que NOMBRAN un plan, sin lo que no lo distingue.

    * sin tildes ni mayusculas;
    * sin el precio («$89.900» no es parte del nombre);
    * la velocidad siempre igual: «200 megas», «200 Mb» y «200M» son «200mb».
    """
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).lower()
    t = re.sub(r"\$\s*[\d.,]+", " ", t)
    t = re.sub(r"(\d+)\s*(?:mbps|megas|mega|mb|m)(?![a-z0-9])", r"\1mb", t)
    return [p for p in re.split(r"[^a-z0-9]+", t) if p and p not in _RELLENO]


def reconocer(texto, catalogo) -> dict | None:
    """El plan del catalogo que ese texto nombra, o None si no nombra UNO SOLO."""
    buscadas = set(_palabras(texto))
    if not buscadas or not catalogo:
        return None
    por_plan = [(p, set(_palabras(p.get("nombre")))) for p in catalogo
                if isinstance(p, dict)]
    por_plan = [(p, w) for p, w in por_plan if w]

    #  1. El mismo nombre, palabra por palabra (lo que manda un formulario que
    #     ofrece el catalogo tal cual).
    iguales = [p for p, w in por_plan if w == buscadas]
    if len(iguales) == 1:
        return iguales[0]

    #  2. Por lo que lo distingue de los demas.
    candidatos = []
    for plan, suyas in por_plan:
        ajenas = set()
        for otro, otras in por_plan:
            if otro is not plan:
                ajenas |= otras
        #  Un plan sin ninguna palabra propia («PLAN HOGAR» al lado de «PLAN
        #  HOGAR PROMO») se exige entero.
        exigidas = (suyas - ajenas) or suyas
        if exigidas <= buscadas:
            candidatos.append((len(suyas & buscadas), plan))
    if not candidatos:
        return None
    #  Entre varios, el que mas palabras suyas encuentra: «HOGAR PROMO» es el
    #  de promocion y no el plano. Un empate no se desempata.
    mejor = max(n for n, _ in candidatos)
    ganadores = [p for n, p in candidatos if n == mejor]
    return ganadores[0] if len(ganadores) == 1 else None


# =============================================================================
#  LO QUE EL TICKET DICE, CUANDO NO HAY SOLICITUD
# =============================================================================
def dato_del_ticket(orden, etiqueta: str) -> str:
    """Lo que la descripcion del ticket trae despues de «Etiqueta:».

    La plataforma escribe el ticket de una instalacion como una linea de
    campos separados por barras (`solicitudes/entrega.py`): «... | Plan: X |
    Corte: Y | ...». Cuando la orden tiene su solicitud esto no se usa: la
    solicitud es el dato, el ticket su copia.
    """
    caso = getattr(orden, "caso", None)
    texto = str(getattr(caso, "description", "") or "")
    m = re.search(rf"(?:^|[|\n\r])\s*{re.escape(etiqueta)}\s*:\s*([^|\n\r]+)", texto, re.I)
    return m.group(1).strip() if m else ""


#: El comienzo de la linea con los datos de una instalacion nueva, como la
#: escriben las personas en el ISP y la plataforma (`solicitudes/entrega.py`).
_INSTALACION_NUEVA = re.compile(r"instalaci[oó]n\s+nueva\s*[-–—:]\s*", re.I)
_ETIQUETADO = re.compile(r"^([^\W\d_][^:]{0,24}?)\s*:\s*(.*)$")


def _sin_tildes(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(ch for ch in t if not unicodedata.combining(ch)).strip().lower()


def _gps_escrito(valor: str) -> dict | None:
    """«10.8820333, -74.7947109» -> {"lat", "lng"}, o None si no es un punto
    creible (fuera de rango, 0,0)."""
    numeros = re.findall(r"-?\d+(?:\.\d+)?", valor or "")
    if len(numeros) != 2:
        return None
    lat, lng = float(numeros[0]), float(numeros[1])
    if not (-90 <= lat <= 90 and -180 <= lng <= 180) or (lat == 0 and lng == 0):
        return None
    return {"lat": lat, "lng": lng}


def _nombre_y_apellido(completo: str) -> tuple[str, str]:
    """Nombres y apellidos de un nombre escrito de corrido. En Colombia los dos
    ULTIMOS son los apellidos cuando hay cuatro o mas palabras; con tres, la
    primera es el nombre. El tecnico lo confirma contra la cedula."""
    palabras = str(completo or "").split()
    if len(palabras) >= 4:
        return " ".join(palabras[:-2]), " ".join(palabras[-2:])
    if len(palabras) == 3:
        return palabras[0], " ".join(palabras[1:])
    if len(palabras) == 2:
        return palabras[0], palabras[1]
    return " ".join(palabras), ""


def cliente_del_ticket(orden) -> dict | None:
    """Los datos del cliente NUEVO escritos en el ticket, o None si no estan.

    POR QUE EXISTE (el usuario, 27/11/2026, primera instalacion vigilada en
    produccion): en el ISP una instalacion nueva NO tiene todavia su cliente.
    El ticket se abre sobre un cliente DE PASO y los datos del cliente de
    verdad van escritos en la descripcion, en una linea con barras:

        Instalacion Nueva - Nombre Apellidos | Tel: ... | correo | direccion,
        barrio | GPS: lat, lng | Doc: CC numero | Plan: ... | Corte: ...

    Sin solicitud ligada, el contrato salia con el nombre, el telefono, la
    direccion y las coordenadas del cliente de paso. Ahora sale con estos.

    Lo que viene con etiqueta se lee por su etiqueta; el correo, por la «@»; el
    primer texto sin etiqueta es la direccion, con el barrio despues de la
    ultima coma. Lo que no se pudo leer queda vacio: el tecnico lo escribe con
    la cedula a la vista. Sin la linea «Instalacion Nueva», None: no se adivina.
    """
    caso = getattr(orden, "caso", None)
    texto = str(getattr(caso, "description", "") or "")
    m = _INSTALACION_NUEVA.search(texto)
    if not m:
        return None
    resto = texto[m.end():].splitlines()
    partes = [p.strip() for p in (resto[0] if resto else "").split("|")]
    nombre, apellido = _nombre_y_apellido(partes[0] if partes else "")
    datos = {"nombre": nombre, "apellido": apellido, "tipo_documento": "CC",
             "numero_documento": "", "telefono": "", "correo": "",
             "direccion": "", "barrio": "", "gps": None}
    for parte in partes[1:]:
        if not parte:
            continue
        e = _ETIQUETADO.match(parte)
        if e:
            etiqueta, valor = _sin_tildes(e.group(1)), e.group(2).strip()
            if etiqueta in ("tel", "telefono", "cel", "celular", "movil"):
                datos["telefono"] = re.sub(r"\D", "", valor)
            elif etiqueta == "gps":
                datos["gps"] = _gps_escrito(valor)
            elif etiqueta in ("doc", "documento", "cedula"):
                d = re.match(r"^([A-Za-z]{1,4})\.?\s*(.+)$", valor)
                if d and re.search(r"\d", d.group(2)):
                    datos["tipo_documento"] = d.group(1).upper()
                    datos["numero_documento"] = d.group(2).strip()
                else:
                    datos["numero_documento"] = valor
            #  Plan, corte y los demas los lee `dato_del_ticket` o no son del cliente.
            continue
        if "@" in parte and " " not in parte and not datos["correo"]:
            datos["correo"] = parte
        elif re.match(r"^(sin\s+gps|solicitud\b)", _sin_tildes(parte)):
            continue
        elif not datos["direccion"]:
            direccion, coma, barrio = parte.rpartition(",")
            datos["direccion"], datos["barrio"] = ((direccion.strip(), barrio.strip())
                                                   if coma else (parte, ""))
    return datos


# =============================================================================
#  LOS SERVIDORES
# =============================================================================
def servidores_del_plan(plan: dict | None, servidores) -> list[dict]:
    """Los servidores de la empresa donde ese plan se puede crear.

    * Sin plan reconocido: todos los de la empresa (no hay con que filtrar).
    * Un plan sin zonas declaradas va en cualquiera: todos.
    * Un plan con zonas: SOLO esos. Si la empresa no cargo ninguno de ellos en
      su contrato la lista sale VACIA, y es a proposito: ofrecerle «los otros»
      es dejar que un cliente quede creado en un servidor donde su plan no va.
      La pantalla dice que falta cargarlos.
    """
    validos = [s for s in (servidores or []) if isinstance(s, dict)]
    zonas = (plan or {}).get("zonas") or []
    if not zonas:
        return validos
    return [s for s in validos if s.get("id_zona") in zonas]


def _fichas(texto) -> set[str]:
    t = unicodedata.normalize("NFKD", str(texto or ""))
    t = "".join(ch for ch in t if not unicodedata.combining(ch)).lower()
    return {p for p in re.split(r"[^a-z0-9]+", t) if p}


def servidor_del_corte(corte, servidores) -> int | None:
    """El servidor cuyo NOMBRE trae lo que el ticket dice del corte, si es uno solo.

    «CORTE 30» esta entero en «CORTE 30 - SERVIDOR 1» y no en «CORTE 15 -
    SERVIDOR 1». No conoce la palabra «corte»: compara lo que haya escrito la
    empresa en sus servidores con lo que haya escrito en su formulario.

    Es una sugerencia para dejar una opcion marcada. Si coinciden varios o
    ninguno, no marca nada.
    """
    buscadas = _fichas(corte)
    if not buscadas:
        return None
    coinciden = [s for s in (servidores or [])
                 if isinstance(s, dict) and buscadas <= _fichas(s.get("nombre"))]
    return coinciden[0].get("id_zona") if len(coinciden) == 1 else None
