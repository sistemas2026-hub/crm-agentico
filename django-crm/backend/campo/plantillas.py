# -*- coding: utf-8 -*-
"""
================================================================================
 LAS PLANTILLAS DE TRABAJO, SIN ESCRIBIR JSON
================================================================================

Una plantilla dice QUE hace el tecnico y COMO lo registra: los datos que anota,
las fotos que tiene que sacar y en que pasos. Hasta el 13/10/2026 solo se podian
crear de dos formas, y las dos son de desarrollador: el admin de Django, con el
esquema escrito a mano en JSON, o un comando semilla. Cada empresa trabaja
distinto, asi que eso dejaba a cada ISP nuevo esperando una sesion de codigo
para algo que es suyo (CLAUDE.md §3.3).

QUE RESUELVE ESTE MODULO
------------------------
    CATALOGO_BASE      plantillas de partida que trae la plataforma
    componer()         definicion guiada -> esquema del contrato 1
    leer_definicion()  esquema -> definicion guiada, o por que no se puede
    crear() / publicar()

Quien edita nunca ve el JSON: elige de una lista CERRADA de tipos y el esquema
lo arma `componer()`.

POR QUE LA LISTA DE TIPOS ES CERRADA, Y POR QUE ES ESTA
-------------------------------------------------------
NO es porque el backend interprete los campos: medido el 13/10/2026, no
interpreta NINGUN id concreto del esquema -- `serial_ont` o `potencia_rx` no
significan nada fuera de la plantilla, el serial que vuelve al ISP sale del
inventario y la señal sale del contexto de la orden.

Es por el CONTRATO CON LA APLICACION. Ese mismo dia se midio que la app y el
backend entienden distinto varias cosas que el validador acepta, y en todas el
sintoma es el peor posible: la orden queda CERRADA en el telefono y trabada en
el servidor, sin que nadie lo vea.

    booleano obligatorio   la app lo da por completo sin tocarlo; el backend
                           dice CAMPO_FALTANTE
    min/max en texto       la app compara el numero; el backend, el largo
    entero                 la app pone teclado de texto y no valida
    regex                  la app lo ignora
    fecha/foto/documento   como CAMPO, la app los dibuja como texto libre
    firma                  la app guarda dos datos que ninguna plantilla
                           declara y el backend rechaza el envio entero

Por eso aca solo entra lo que los dos lados hacen IGUAL: texto, numero con
rango, seleccion y fotos. El checklist se arma como seleccion «Hecho / No
aplica», no como booleano, justamente por la primera linea. Cuando la app se
alinee, la lista se amplia aca y en ningun otro lado.

LO QUE NO HACE
--------------
No toca versiones existentes. Cada cambio publica una version NUEVA y las
ordenes ya creadas conservan la suya (`OrdenTrabajo.tipo_trabajo_version` es
PROTECT). Una plantilla armada a mano con algo de la lista de arriba se puede
seguir usando, pero el editor no la abre: decir por que es mejor que
reescribirla perdiendo lo que tenia.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata

from django.core.exceptions import ValidationError
from django.db import transaction

from campo.models import WorkType, WorkTypeVersion
from campo.services.validador import validar_esquema_plantilla


class ErrorPlantilla(ValueError):
    """La definicion no se puede publicar. El mensaje es para quien edita."""

    def __init__(self, codigo: str, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


# ---------------------------------------------------------------------------
#  Lo que el editor ofrece
# ---------------------------------------------------------------------------

TEXTO = "texto"
NUMERO = "numero"
SELECCION = "seleccion"
CHECKLIST = "checklist"

TIPOS = (
    (TEXTO, "Texto", "Una nota corta: un serial, una observacion."),
    (NUMERO, "Numero", "Una medida, con unidad y rango opcional."),
    (SELECCION, "Opciones", "Elegir una de varias respuestas."),
    (CHECKLIST, "Verificacion", "Algo que el tecnico confirma: Hecho o No aplica."),
)
TIPOS_VALIDOS = {t[0] for t in TIPOS}

#: El checklist viaja como seleccion: es lo unico que la app y el backend
#: validan igual (ver la cabecera). Estas son sus dos respuestas.
OPCIONES_CHECKLIST = ["Hecho", "No aplica"]

#: Topes para que una plantilla siga siendo algo que se llena en una casa.
MAX_CAMPOS = 40
MAX_EVIDENCIAS = 20
MAX_OPCIONES = 20
MAX_TITULO = 120
MAX_TEXTO_LARGO = 400

CLAVES_RAIZ_CONOCIDAS = {"pasos", "campos", "evidencias", "seguimiento",
                         "duracion_estimada_minutos"}

#: Fotos por reporte (inicio, avance, bloqueo, cierre). Pocas: se sacan con
#: el trabajo andando, no son el checklist.
MAX_FOTOS_POR_REPORTE = 5


# ---------------------------------------------------------------------------
#  El catalogo de partida
# ---------------------------------------------------------------------------

def _c(titulo, tipo=TEXTO, *, obligatorio=True, paso="", **extra):
    return {"titulo": titulo, "tipo": tipo, "obligatorio": obligatorio,
            "paso": paso, **extra}


def _f(titulo, *, obligatorio=True, paso="", instrucciones=""):
    return {"titulo": titulo, "obligatorio": obligatorio, "paso": paso,
            "instrucciones": instrucciones}


_POTENCIA = dict(unidad="dBm", min=-28.0, max=-8.0,
                 ayuda="Rango esperado entre -28 y -8 dBm.")

#: Plantillas de PARTIDA. No son las de ninguna empresa: cada una se adopta,
#: se le cambia lo que haga falta y se publica como propia. Por eso viven en
#: codigo -- son de la plataforma, como el validador -- y lo que la empresa
#: decide queda en SU WorkType.
#:
#: Que tipos hay salio de MEDIR 5.298 tickets reales de un ISP de fibra
#: (14/08-13/10/2026, detalle en SPEC/objetivos/plantillas-de-trabajo.md). Las
#: dos plantillas semilla que existian -- instalacion y correctivo -- no
#: cubrian el SEGUNDO trabajo mas frecuente en una casa: retirar equipos.
#:
#: `visitas_medidas` es el numero que justifica que cada una este aca. Es de
#: UNA empresa y no decide nada para las demas: ordena el catalogo, no lo
#: recorta (CLAUDE.md §3.3).
CATALOGO_BASE: list[dict] = [
    {
        "codigo": "correctivo_fibra",
        "nombre": "Correctivo de fibra",
        "labor": "correctivo",
        "descripcion": "Sin servicio, intermitente, lento, fibra partida o "
                       "cable caido. Mide antes y despues.",
        "visitas_medidas": "~690 tickets en dos meses",
        "definicion": {
            "duracion_estimada_minutos": 60,
            "campos": [
                _c("Potencia al llegar", NUMERO, obligatorio=False,
                   paso="Diagnostico", unidad="dBm",
                   ayuda="Vacio si no hay señal."),
                _c("Que encontro", SELECCION, paso="Diagnostico", opciones=[
                    "Fibra partida o cortada", "Conector o empalme dañado",
                    "Equipo dañado", "Configuracion del equipo",
                    "Falla en la red o el sector", "Problema dentro de la casa",
                    "No se encontro falla"]),
                _c("Que hizo", paso="Solucion"),
                _c("Potencia al salir", NUMERO, paso="Solucion", **_POTENCIA),
                _c("Servicio probado con el cliente", CHECKLIST, paso="Solucion"),
            ],
            "evidencias": [
                _f("Medicion al llegar", paso="Diagnostico",
                   instrucciones="Pantalla del medidor con la lectura legible."),
                _f("Daño encontrado", obligatorio=False, paso="Diagnostico"),
                _f("Medicion al salir", paso="Solucion",
                   instrucciones="Pantalla del medidor con la lectura legible."),
            ],
        },
    },
    {
        "codigo": "retiro_equipos",
        "nombre": "Retiro de equipos",
        "labor": "trabajos",
        "descripcion": "Recoger equipos por retiro o cancelacion del servicio.",
        "visitas_medidas": "~380 tickets en dos meses",
        "definicion": {
            "duracion_estimada_minutos": 30,
            "campos": [
                _c("Que equipos recogio",
                   ayuda="Por ejemplo: ONU, router, decodificador, fuente."),
                _c("Serial de la ONU recogida", obligatorio=False),
                _c("Estado de lo recogido", SELECCION, opciones=[
                    "Completo y en buen estado", "Completo con daños",
                    "Incompleto", "El cliente no lo entrego"]),
                _c("Retiro la acometida", SELECCION, obligatorio=False,
                   opciones=["Si", "No", "No aplica"]),
            ],
            "evidencias": [
                _f("Equipos recogidos",
                   instrucciones="Todos juntos, con el serial visible si se puede."),
                _f("Constancia de entrega", obligatorio=False),
            ],
        },
    },
    {
        "codigo": "instalacion_fibra",
        "nombre": "Instalacion de fibra",
        "labor": "instalacion",
        "descripcion": "Servicio nuevo: equipo, señal y entrega al cliente.",
        "visitas_medidas": "~220 tickets en dos meses",
        "definicion": {
            "duracion_estimada_minutos": 120,
            "campos": [
                _c("Serial de la ONU", paso="Equipo",
                   ayuda="El de la etiqueta del equipo instalado."),
                _c("Metros de fibra usados", NUMERO, obligatorio=False,
                   paso="Equipo", unidad="m", min=0, max=2000),
                _c("Potencia en la roseta", NUMERO, paso="Señal", **_POTENCIA),
                _c("Red WiFi configurada y probada", CHECKLIST, paso="Entrega"),
                _c("Cliente informado de como pedir soporte", CHECKLIST,
                   paso="Entrega"),
            ],
            "evidencias": [
                _f("ONU instalada", paso="Equipo",
                   instrucciones="Que se vea la fijacion, la roseta y el latiguillo."),
                _f("Medicion de potencia", paso="Señal",
                   instrucciones="Pantalla del medidor con la lectura legible."),
                _f("Caja o punto de conexion", obligatorio=False, paso="Señal"),
                _f("Fachada", obligatorio=False, paso="Entrega",
                   instrucciones="Con la nomenclatura visible."),
            ],
        },
    },
    {
        "codigo": "servicio_tv",
        "nombre": "Television",
        "labor": "correctivo",
        "descripcion": "Falla de señal de TV, punto adicional o TDT.",
        "visitas_medidas": "~76 tickets en dos meses",
        "definicion": {
            "duracion_estimada_minutos": 60,
            "campos": [
                _c("Que se hizo", SELECCION, opciones=[
                    "Reparacion de señal", "Punto adicional",
                    "Instalacion TDT o antena", "Cambio de decodificador"]),
                _c("Nivel de señal", NUMERO, obligatorio=False, unidad="dBmV"),
                _c("Puntos de TV funcionando", NUMERO, min=0, max=20),
                _c("Canales verificados con el cliente", CHECKLIST),
            ],
            "evidencias": [
                _f("Trabajo terminado"),
                _f("Medicion de señal", obligatorio=False),
            ],
        },
    },
    {
        "codigo": "traslado_servicio",
        "nombre": "Traslado de servicio",
        "labor": "instalacion",
        "descripcion": "El cliente se muda: el servicio se instala en la nueva "
                       "direccion.",
        "visitas_medidas": "~76 tickets en dos meses",
        "definicion": {
            "duracion_estimada_minutos": 120,
            "campos": [
                _c("Nueva direccion confirmada con el cliente", CHECKLIST,
                   paso="Nueva direccion"),
                _c("Serial de la ONU", paso="Nueva direccion"),
                _c("Metros de fibra usados", NUMERO, obligatorio=False,
                   paso="Nueva direccion", unidad="m", min=0, max=2000),
                _c("Potencia en la roseta", NUMERO, paso="Nueva direccion",
                   **_POTENCIA),
                _c("Servicio probado con el cliente", CHECKLIST,
                   paso="Nueva direccion"),
            ],
            "evidencias": [
                _f("ONU instalada en la nueva direccion", paso="Nueva direccion"),
                _f("Medicion de potencia", paso="Nueva direccion",
                   instrucciones="Pantalla del medidor con la lectura legible."),
                _f("Fachada nueva", obligatorio=False, paso="Nueva direccion"),
            ],
        },
    },
    {
        "codigo": "cambio_equipo",
        "nombre": "Cambio o reubicacion de equipo",
        "labor": "correctivo",
        "descripcion": "Cambiar o mover el router o la ONU.",
        "visitas_medidas": "~30 tickets en dos meses",
        "definicion": {
            "duracion_estimada_minutos": 45,
            "campos": [
                _c("Que se cambio", SELECCION, opciones=[
                    "Router WiFi", "ONU", "ONU y router",
                    "Reubicacion de la ONU", "Reubicacion del router"]),
                _c("Motivo", SELECCION, opciones=[
                    "Dañado", "Lento u obsoleto", "Pedido del cliente",
                    "Mejorar la cobertura"]),
                _c("Serial del equipo nuevo", obligatorio=False),
                _c("Serial del equipo retirado", obligatorio=False),
                _c("Potencia final", NUMERO, obligatorio=False, **_POTENCIA),
                _c("Servicio probado con el cliente", CHECKLIST),
            ],
            "evidencias": [
                _f("Equipo instalado"),
                _f("Equipo retirado", obligatorio=False),
            ],
        },
    },
    {
        "codigo": "trabajo_general",
        "nombre": "Trabajo general",
        "labor": "trabajos",
        "descripcion": "Para lo que no encaja en las demas: una camara, un "
                       "cableado interno, una revision.",
        "visitas_medidas": "asuntos sueltos",
        "definicion": {
            "duracion_estimada_minutos": 60,
            "campos": [
                _c("Que se hizo"),
                _c("Resultado", SELECCION, opciones=[
                    "Resuelto", "Resuelto en parte", "No se pudo resolver"]),
                _c("Observaciones", obligatorio=False),
            ],
            "evidencias": [_f("Trabajo terminado")],
        },
    },
]


def base_por_codigo(codigo: str) -> dict | None:
    return next((b for b in CATALOGO_BASE if b["codigo"] == codigo), None)


# ---------------------------------------------------------------------------
#  Definicion guiada <-> esquema
# ---------------------------------------------------------------------------

def _slug(texto: str) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode(
        "ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9]+", "_", t).strip("_")
    return (t or "campo")[:48]


_ID_VALIDO = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _texto(valor, campo: str, *, obligatorio=True, largo=MAX_TITULO) -> str:
    t = " ".join(str(valor or "").split())
    if obligatorio and not t:
        raise ErrorPlantilla("FALTA_TITULO", f"Falta {campo}.")
    if len(t) > largo:
        raise ErrorPlantilla("TEXTO_LARGO",
                             f"{campo.capitalize()} pasa de {largo} letras.")
    return t


def _numero(valor, campo: str):
    if valor in (None, ""):
        return None
    if isinstance(valor, bool):
        raise ErrorPlantilla("NUMERO_INVALIDO", f"{campo} no es un numero.")
    try:
        return float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        raise ErrorPlantilla("NUMERO_INVALIDO", f"{campo} no es un numero.")


class _Ids:
    """Ids estables y unicos.

    Un id que ya existia se CONSERVA aunque cambie el titulo: los datos que la
    app guarda van indexados por id, y renombrar «Potencia» a «Potencia RX» no
    puede convertir lo anotado ayer en un dato huerfano.
    """

    def __init__(self):
        self.usados: set[str] = set()

    def dar(self, propuesto, titulo) -> str:
        base = propuesto if (isinstance(propuesto, str)
                             and _ID_VALIDO.match(propuesto)) else _slug(titulo)
        if not base[0].isalpha():
            base = f"c_{base}"
        candidato, n = base, 2
        while candidato in self.usados:
            candidato, n = f"{base}_{n}", n + 1
        self.usados.add(candidato)
        return candidato


def componer(definicion: dict) -> dict:
    """La definicion que manda el editor, convertida al esquema del contrato 1.

    Todo lo que entra se valida aca, con mensajes para quien edita; y lo que
    sale se valida OTRA VEZ con el validador de siempre, el mismo que protege
    al admin. Son dos guardas que no confian una en la otra.
    """
    if not isinstance(definicion, dict):
        raise ErrorPlantilla("DEFINICION_INVALIDA", "La plantilla llego vacia.")

    campos_in = definicion.get("campos") or []
    evid_in = definicion.get("evidencias") or []
    if not isinstance(campos_in, list) or not isinstance(evid_in, list):
        raise ErrorPlantilla("DEFINICION_INVALIDA",
                             "Los datos y las fotos tienen que ser listas.")
    if len(campos_in) > MAX_CAMPOS:
        raise ErrorPlantilla("DEMASIADOS", f"Mas de {MAX_CAMPOS} datos.")
    if len(evid_in) > MAX_EVIDENCIAS:
        raise ErrorPlantilla("DEMASIADOS", f"Mas de {MAX_EVIDENCIAS} fotos.")
    if not campos_in and not evid_in:
        #  Una orden sin nada que registrar se cierra con un toque, y eso es
        #  justo lo que la plantilla existe para evitar.
        raise ErrorPlantilla("PLANTILLA_VACIA",
                             "La plantilla no pide ningun dato ni foto.")

    pasos: list[dict] = []
    ids_paso: dict[str, str] = {}

    def paso_de(titulo) -> str:
        t = _texto(titulo, "el nombre del paso", obligatorio=False)
        if not t:
            return ""
        clave = t.lower()
        if clave not in ids_paso:
            ids_paso[clave] = f"paso_{len(pasos) + 1}"
            pasos.append({"id": ids_paso[clave], "titulo": t})
        return ids_paso[clave]

    ids = _Ids()
    campos = []
    for i, c in enumerate(campos_in, 1):
        if not isinstance(c, dict):
            raise ErrorPlantilla("DEFINICION_INVALIDA", f"El dato {i} no se entiende.")
        titulo = _texto(c.get("titulo"), f"el nombre del dato {i}")
        tipo = c.get("tipo") or TEXTO
        if tipo not in TIPOS_VALIDOS:
            raise ErrorPlantilla("TIPO_NO_PERMITIDO",
                                 f"«{titulo}»: el tipo '{tipo}' no esta disponible.")
        obligatorio = bool(c.get("obligatorio", True))
        salida = {"id": ids.dar(c.get("id"), titulo), "titulo": titulo}
        reglas = {"required": obligatorio}

        if tipo == TEXTO:
            salida["tipo"] = "texto"
        elif tipo == NUMERO:
            salida["tipo"] = "decimal"
            mn = _numero(c.get("min"), f"El minimo de «{titulo}»")
            mx = _numero(c.get("max"), f"El maximo de «{titulo}»")
            if mn is not None and mx is not None and mn > mx:
                raise ErrorPlantilla("RANGO_INVERTIDO",
                                     f"«{titulo}»: el minimo es mayor que el maximo.")
            if mn is not None:
                reglas["min"] = mn
            if mx is not None:
                reglas["max"] = mx
            unidad = _texto(c.get("unidad"), "la unidad", obligatorio=False, largo=16)
            if unidad:
                salida["unidad"] = unidad
        elif tipo == SELECCION:
            salida["tipo"] = "seleccion"
            opciones = []
            for o in c.get("opciones") or []:
                o = _texto(o, "una opcion", obligatorio=False)
                if o and o not in opciones:
                    opciones.append(o)
            # «OTRO» CON TEXTO (18/10/2026): la opción la agrega la plataforma,
            # siempre al final y con este nombre exacto, porque la app y el
            # servidor la reconocen por él. Si quien edita la escribió a mano
            # en la lista, no queda dos veces.
            # Sin la casilla, un «Otro» escrito a mano queda como una opción
            # más: hay empresas que lo usan así, sin texto.
            permite_otro = bool(c.get("permite_otro"))
            if permite_otro:
                opciones = [o for o in opciones if o != "Otro"] + ["Otro"]
                salida["permite_otro"] = True
            if len(opciones) < 2:
                raise ErrorPlantilla("FALTAN_OPCIONES",
                                     f"«{titulo}» necesita al menos dos opciones.")
            if len(opciones) > MAX_OPCIONES:
                raise ErrorPlantilla("DEMASIADOS",
                                     f"«{titulo}» tiene mas de {MAX_OPCIONES} opciones.")
            reglas["options"] = opciones
        else:  # CHECKLIST
            salida["tipo"] = "seleccion"
            salida["presentacion"] = CHECKLIST
            reglas["options"] = list(OPCIONES_CHECKLIST)

        salida["reglas"] = reglas
        ayuda = _texto(c.get("ayuda"), "la ayuda", obligatorio=False,
                       largo=MAX_TEXTO_LARGO)
        if ayuda:
            salida["ayuda"] = ayuda
        paso = paso_de(c.get("paso"))
        if paso:
            salida["paso"] = paso
        campos.append(salida)

    evidencias = []
    for i, e in enumerate(evid_in, 1):
        if not isinstance(e, dict):
            raise ErrorPlantilla("DEFINICION_INVALIDA", f"La foto {i} no se entiende.")
        titulo = _texto(e.get("titulo"), f"el nombre de la foto {i}")
        salida = {"id": ids.dar(e.get("id"), titulo), "titulo": titulo,
                  "tipo": "foto", "obligatorio": bool(e.get("obligatorio", True))}
        instrucciones = _texto(e.get("instrucciones"), "las instrucciones",
                               obligatorio=False, largo=MAX_TEXTO_LARGO)
        if instrucciones:
            salida["instrucciones"] = instrucciones
        paso = paso_de(e.get("paso"))
        if paso:
            salida["paso"] = paso
        evidencias.append(salida)

    esquema = {"pasos": pasos, "campos": campos, "evidencias": evidencias}

    #  LAS FOTOS DE CADA REPORTE (15/10/2026). Van en `seguimiento.<momento>.
    #  evidencias`, que es donde las lee `seguimiento_campo.formulario_de`.
    #  Se escriben las de los cuatro momentos, AUNQUE ESTEN VACIAS: una lista
    #  vacia es «este reporte no pide foto», y sin escribirla volveria a valer
    #  la foto por defecto -- lo que el editor mostro no seria lo que la app
    #  pide. Sin la clave en la definicion, no se toca nada.
    fotos_rep = definicion.get("fotos_de_reportes")
    if fotos_rep is not None:
        from campo.services.seguimiento_campo import MOMENTOS
        if not isinstance(fotos_rep, dict):
            raise ErrorPlantilla("DEFINICION_INVALIDA",
                                 "Las fotos de los reportes no se entienden.")
        raros = set(fotos_rep) - set(MOMENTOS)
        if raros:
            raise ErrorPlantilla("DEFINICION_INVALIDA",
                                 f"No existe el reporte '{sorted(raros)[0]}'.")
        seguimiento = {}
        for momento in MOMENTOS:
            lista = fotos_rep.get(momento) or []
            if not isinstance(lista, list):
                raise ErrorPlantilla("DEFINICION_INVALIDA",
                                     "Las fotos de un reporte tienen que ser una lista.")
            if len(lista) > MAX_FOTOS_POR_REPORTE:
                raise ErrorPlantilla(
                    "DEMASIADOS",
                    f"Mas de {MAX_FOTOS_POR_REPORTE} fotos en el reporte de {momento}.")
            salida_m = []
            for i, e in enumerate(lista, 1):
                if not isinstance(e, dict):
                    raise ErrorPlantilla("DEFINICION_INVALIDA",
                                         f"La foto {i} del reporte de {momento} no se entiende.")
                titulo = _texto(e.get("titulo"),
                                f"el nombre de la foto {i} del reporte de {momento}")
                #  Siempre opcional: una foto que falta no retiene un reporte
                #  (la app lo guarda igual), asi que «obligatoria» prometeria
                #  algo que nadie hace cumplir.
                salida_m.append({"id": ids.dar(e.get("id"), titulo),
                                 "titulo": titulo, "tipo": "foto",
                                 "obligatorio": False})
            seguimiento[momento] = {"evidencias": salida_m}
        esquema["seguimiento"] = seguimiento

    duracion = definicion.get("duracion_estimada_minutos")
    if duracion not in (None, ""):
        if isinstance(duracion, bool):
            raise ErrorPlantilla("DURACION_INVALIDA", "La duracion no es un numero.")
        try:
            duracion = int(duracion)
        except (TypeError, ValueError):
            raise ErrorPlantilla("DURACION_INVALIDA", "La duracion no es un numero.")
        if not 1 <= duracion <= 24 * 60:
            raise ErrorPlantilla("DURACION_INVALIDA",
                                 "La duracion va de 1 minuto a 24 horas.")
        esquema["duracion_estimada_minutos"] = duracion

    #  La segunda guarda: la misma que protege al admin.
    try:
        validar_esquema_plantilla(esquema)
    except ValidationError as e:
        raise ErrorPlantilla("ESQUEMA_INVALIDO", "; ".join(e.messages))
    return esquema


def leer_definicion(esquema: dict) -> tuple[dict | None, list[str]]:
    """El esquema de una version, como lo edita la pantalla.

    Devuelve `(definicion, [])` si el editor lo puede abrir, o
    `(None, motivos)` si tiene algo que el editor no maneja. No se adapta en
    silencio: convertir un booleano en checklist, o tirar un regex, cambiaria
    lo que la plantilla pide sin que nadie lo decida.
    """
    esquema = esquema if isinstance(esquema, dict) else {}
    motivos: list[str] = []

    sobrantes = set(esquema) - CLAVES_RAIZ_CONOCIDAS
    if sobrantes:
        motivos.append("tiene secciones que el editor no maneja: "
                       + ", ".join(sorted(sobrantes)))

    titulos_paso = {p.get("id"): p.get("titulo", "")
                    for p in esquema.get("pasos") or [] if isinstance(p, dict)}

    campos = []
    for c in esquema.get("campos") or []:
        if not isinstance(c, dict):
            motivos.append("tiene un dato que no se entiende")
            continue
        titulo = c.get("titulo") or c.get("etiqueta") or c.get("id") or ""
        reglas = c.get("reglas") or {}
        tipo = c.get("tipo")
        obligatorio = bool(reglas.get("required", c.get("obligatorio", False)))
        fila = {"id": c.get("id"), "titulo": titulo, "obligatorio": obligatorio,
                "ayuda": c.get("ayuda", ""),
                "paso": titulos_paso.get(c.get("paso"), "")}
        if "regex" in reglas:
            motivos.append(f"«{titulo}» valida con un patron (regex) que la app ignora")
        if tipo == "texto":
            if "min" in reglas or "max" in reglas:
                motivos.append(f"«{titulo}» tiene minimo o maximo en un texto, "
                               "y la app y el servidor lo entienden distinto")
            fila["tipo"] = TEXTO
        elif tipo == "decimal":
            fila.update(tipo=NUMERO, min=reglas.get("min"), max=reglas.get("max"),
                        unidad=c.get("unidad", ""))
        elif tipo == "seleccion":
            opciones = list(reglas.get("options") or c.get("opciones") or [])
            if c.get("presentacion") == CHECKLIST:
                fila["tipo"] = CHECKLIST
            else:
                permite_otro = bool(c.get("permite_otro"))
                fila.update(tipo=SELECCION, permite_otro=permite_otro,
                            opciones=[o for o in opciones
                                      if not (permite_otro and o == "Otro")])
        else:
            motivos.append(f"«{titulo}» es de tipo '{tipo}', que el editor no ofrece")
        campos.append(fila)

    evidencias = []
    for e in esquema.get("evidencias") or []:
        if not isinstance(e, dict):
            motivos.append("tiene una foto que no se entiende")
            continue
        titulo = e.get("titulo") or e.get("descripcion") or e.get("id") or ""
        if (e.get("tipo") or "foto") != "foto":
            motivos.append(f"«{titulo}» pide un(a) {e.get('tipo')}, que el editor no ofrece")
        evidencias.append({"id": e.get("id"), "titulo": titulo,
                           "obligatorio": bool(e.get("obligatorio", False)),
                           "instrucciones": e.get("instrucciones", ""),
                           "paso": titulos_paso.get(e.get("paso"), "")})

    #  Las fotos de cada reporte. Un momento sin declarar se muestra con la
    #  foto por defecto, que es la que la app ofrece: el editor ensena lo que
    #  pasa, no lo que esta escrito.
    from campo.services.seguimiento_campo import MINIMO_EVIDENCIAS, MOMENTOS
    seguimiento = esquema.get("seguimiento") or {}
    fotos_de_reportes = {}
    if not isinstance(seguimiento, dict):
        motivos.append("tiene un seguimiento que no se entiende")
        seguimiento = {}
    for raro in sorted(set(seguimiento) - set(MOMENTOS)):
        motivos.append(f"declara un reporte '{raro}' que no existe")
    for momento in MOMENTOS:
        declarado = seguimiento.get(momento) or {}
        if not isinstance(declarado, dict):
            motivos.append(f"el reporte de {momento} no se entiende")
            continue
        if declarado.get("campos"):
            motivos.append(f"el reporte de {momento} pide datos propios, "
                           "que el editor no maneja")
        lista = declarado.get("evidencias")
        if not isinstance(lista, list):
            lista = MINIMO_EVIDENCIAS.get(momento, [])
        fotos_de_reportes[momento] = [
            {"id": e.get("id"),
             "titulo": e.get("titulo") or e.get("id") or ""}
            for e in lista if isinstance(e, dict)]

    if motivos:
        return None, motivos
    definicion = {"campos": campos, "evidencias": evidencias,
                  "fotos_de_reportes": fotos_de_reportes}
    if esquema.get("duracion_estimada_minutos"):
        definicion["duracion_estimada_minutos"] = esquema["duracion_estimada_minutos"]
    return definicion, []


def definicion_de_base(base: dict) -> dict:
    """Copia de la definicion de una plantilla del catalogo, lista para editar."""
    d = json.loads(json.dumps(base["definicion"]))
    #  Con las fotos de los reportes ya puestas, las mismas que tendria sin
    #  declararlas: quien adopta ve lo que la app va a pedir.
    if "fotos_de_reportes" not in d:
        d["fotos_de_reportes"] = leer_definicion({})[0]["fotos_de_reportes"]
    return d


# ---------------------------------------------------------------------------
#  Escribir
# ---------------------------------------------------------------------------

def _hash(esquema: dict) -> str:
    #  El mismo que sella `WorkTypeVersion.save()`, para comparar sin escribir.
    return hashlib.sha256(json.dumps(esquema, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def ultima_publicada(tipo: WorkType) -> WorkTypeVersion | None:
    return (tipo.versions.filter(estado=WorkTypeVersion.PUBLICADA)
            .order_by("-version").first())


def _labor(labor, org) -> str:
    from campo.labores import labor_valida
    labor = (labor or "").strip()
    if labor and not labor_valida(org, labor):
        raise ErrorPlantilla("LABOR_INVALIDA", f"'{labor}' no es una labor.")
    return labor


# =============================================================================
#  ASUNTOS Y PLAZO  --  19/10/2026
# =============================================================================
#  Lo que Despacho necesita para llenar el formulario solo. Ver el comentario
#  de los campos en 'campo/models.py::WorkType'.

#: Cuantos asuntos puede atender una plantilla. Mas que esto no es una lista de
#: asuntos, es haber pegado otra cosa.
MAX_ASUNTOS = 40
#: El plazo mas largo que se acepta. Un trabajo a mas de dos meses no se
#: despacha: se agenda aparte.
MAX_PLAZO_DIAS = 60


def normalizar_asunto(texto) -> str:
    """El asunto sin mayusculas, tildes ni espacios de mas: «Cambio De
    Domicilio» y «cambio de  domicilio» son el mismo."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFKD", str(texto or ""))
        if not unicodedata.combining(c))
    return " ".join(sin_tildes.lower().split())


def _asuntos(valor, tipo: WorkType) -> list[str]:
    """La lista de asuntos, limpia. Acepta una lista o un texto, uno por linea.

    Dos plantillas de la misma empresa NO comparten asunto: Despacho no podria
    saber cual proponer, y elegir una por un orden que nadie ve es adivinar.
    """
    if isinstance(valor, str):
        valor = valor.splitlines()
    if not isinstance(valor, (list, tuple)):
        raise ErrorPlantilla("ASUNTOS_INVALIDOS",
                             "Los asuntos van uno por linea.")
    limpios, vistos = [], set()
    for a in valor:
        t = _texto(a, "un asunto", obligatorio=False)
        clave = normalizar_asunto(t)
        if not clave or clave in vistos:
            continue
        vistos.add(clave)
        limpios.append(t)
    if len(limpios) > MAX_ASUNTOS:
        raise ErrorPlantilla("ASUNTOS_DEMASIADOS",
                             f"Pasan de {MAX_ASUNTOS} asuntos.")
    otros = (WorkType.objects.filter(org_id=tipo.org_id)
             .exclude(pk=tipo.pk).only("nombre", "asuntos"))
    for otro in otros:
        repetidos = vistos & {normalizar_asunto(x) for x in (otro.asuntos or [])}
        if repetidos:
            raise ErrorPlantilla(
                "ASUNTO_REPETIDO",
                f"«{sorted(repetidos)[0]}» ya lo atiende la plantilla "
                f"«{otro.nombre}». Un asunto va en una sola.")
    return limpios


def _plazo(valor) -> int | None:
    if valor in (None, ""):
        return None
    try:
        n = int(valor)
    except (TypeError, ValueError):
        raise ErrorPlantilla("PLAZO_INVALIDO", "El plazo va en dias, un numero.")
    if n < 0 or n > MAX_PLAZO_DIAS:
        raise ErrorPlantilla("PLAZO_INVALIDO",
                             f"El plazo va de 0 a {MAX_PLAZO_DIAS} dias.")
    return n


def plantilla_para_asunto(versiones, asunto):
    """De las plantillas que Despacho ofrece, la que atiende este asunto.
    None si ninguna lo declara. Se usa SOLO desde `plantilla_del_caso`."""
    clave = normalizar_asunto(asunto)
    if not clave:
        return None
    for v in versiones:
        if clave in {normalizar_asunto(x) for x in (v.work_type.asuntos or [])}:
            return v
    return None


def plantillas_que_se_ofrecen(org) -> list:
    """Las plantillas que Despacho ofrece: publicadas, de tipos activos, y UNA
    por tipo -- la version publicada mas alta.

    Ofrecer todas las versiones publicadas de un mismo tipo obligaria a quien
    despacha a elegir entre dos cosas que para el son la misma, y la vieja solo
    sirve para auditar lo ya despachado. Vive aca y no en la vista desde el
    21/10/2026: la usa tambien el Supervisor, que no importa vistas.
    """
    qs = (
        WorkTypeVersion.objects
        .filter(work_type__org=org, work_type__activo=True,
                estado=WorkTypeVersion.PUBLICADA)
        .select_related("work_type")
        .order_by("work_type__codigo", "-version")
    )
    vistas, salida = set(), []
    for v in qs:
        if v.work_type_id in vistas:
            continue
        vistas.add(v.work_type_id)
        salida.append(v)
    return salida


# =============================================================================
#  LA PLANTILLA DE UN CASO  --  21/10/2026
# =============================================================================
#  UNA sola regla, en codigo, para Despacho y para el Supervisor cuando cree la
#  orden solo (ficha labores-propias-por-empresa, D9-D10; ficha
#  supervisor-arma-la-jornada, Fase 2). Hasta hoy Despacho decidia en dos
#  lugares: el backend por el asunto y la pantalla por la labor. Dos reglas que
#  pueden contestar distinto no son una regla.
#
#  EL ORDEN ES EL DE D3 (medido > asunto > grupo):
#
#    1  el asunto del ticket lo atiende una plantilla  -> esa, salvo que la
#       labor del caso este MEDIDA (cliente nuevo, corte de red) y sea otra:
#       lo medido no lo pisa un texto
#    2  si no, la labor del caso tiene UNA sola plantilla -> esa
#    3  si no hay una sola respuesta -> ninguna, con el motivo. Elegir una por
#       un orden que nadie ve es adivinar, y el Supervisor no despacha a
#       adivinanzas
#
#  Los motivos son codigos cerrados para el log (sin texto del ticket) y una
#  frase para la pantalla.

SIN_LABOR = "SIN_LABOR"
LABOR_SIN_PLANTILLA = "LABOR_SIN_PLANTILLA"
VARIAS_SIN_ASUNTO = "VARIAS_SIN_ASUNTO"


def plantilla_del_caso(org, *, labor: str = "", asunto: str = "",
                       labor_medida: bool = False, ofrecidas=None) -> dict:
    """Con que plantilla sale un caso.

    Devuelve {"version", "por", "motivo", "detalle"}: `version` es la
    WorkTypeVersion o None; `por` es "asunto" o "labor" (como se eligio);
    `motivo` el codigo de por que no hay ninguna; `detalle` la frase.

    `ofrecidas` deja pasar la lista ya leida: el Supervisor decide muchos casos
    por vuelta y no tiene por que leerla una vez por caso.
    """
    from campo.labores import nombres_de_labor

    ofrecidas = plantillas_que_se_ofrecen(org) if ofrecidas is None else ofrecidas
    labor = (labor or "").strip()

    por_asunto = plantilla_para_asunto(ofrecidas, asunto)
    if por_asunto is not None and not (
            labor_medida and labor and por_asunto.work_type.labor != labor):
        return {"version": por_asunto, "por": "asunto", "motivo": "",
                "detalle": ""}

    if not labor:
        return {"version": None, "por": "", "motivo": SIN_LABOR,
                "detalle": "El Supervisor no sabe la labor de este caso y "
                           "ninguna plantilla tiene su asunto."}

    de_la_labor = [v for v in ofrecidas if v.work_type.labor == labor]
    nombre = nombres_de_labor(org).get(labor, labor)
    if len(de_la_labor) == 1:
        return {"version": de_la_labor[0], "por": "labor", "motivo": "",
                "detalle": ""}
    if not de_la_labor:
        return {"version": None, "por": "", "motivo": LABOR_SIN_PLANTILLA,
                "detalle": f"La labor «{nombre}» no tiene ninguna plantilla "
                           "activa."}
    return {"version": None, "por": "", "motivo": VARIAS_SIN_ASUNTO,
            "detalle": f"La labor «{nombre}» tiene {len(de_la_labor)} "
                       "plantillas y ninguna tiene este asunto: cargalo en la "
                       "que corresponda, en Plantillas."}


def _sin_labor_sin_asuntos(labor: str, asuntos: list) -> None:
    """D7 de labores propias (20/10/2026): una plantilla sin labor no tiene
    asuntos. Sin labor la orden no le llega a ninguna cuadrilla, y un asunto
    que la elige mandaria trabajo a un lugar que no reparte."""
    if asuntos and not labor:
        raise ErrorPlantilla(
            "ASUNTOS_SIN_LABOR",
            "Elegi la labor antes de ponerle asuntos: sin labor, la orden no "
            "le llega a ninguna cuadrilla.")


def crear(org, *, base: str = "", nombre: str = "", labor: str = "",
          definicion: dict | None = None, asuntos=None,
          plazo_dias=None) -> tuple[WorkType, WorkTypeVersion]:
    """Una plantilla nueva para la empresa, desde el catalogo o desde cero.

    Desde el catalogo toma su codigo: dos empresas pueden adoptar la misma
    base sin pisarse, porque el codigo es unico POR EMPRESA.

    CON SUS ASUNTOS Y SU PLAZO DESDE EL ALTA (21/10/2026), pedido del usuario:
    «un boton que permita crear y editar las plantillas y agregar los asuntos
    de esa plantilla». Hasta hoy se creaba sin asuntos y habia que abrirla y
    publicarla para cargarlos. Se validan DENTRO de la transaccion: un asunto
    que ya es de otra plantilla no deja una plantilla creada a medias.
    """
    if base:
        b = base_por_codigo(base)
        if b is None:
            raise ErrorPlantilla("BASE_INEXISTENTE", "Esa plantilla de partida no existe.")
        codigo = b["codigo"]
        nombre = _texto(nombre or b["nombre"], "el nombre")
        labor = _labor(labor or b["labor"], org)
        definicion = definicion or definicion_de_base(b)
    else:
        nombre = _texto(nombre, "el nombre")
        codigo = _slug(nombre)
        labor = _labor(labor, org)
        if definicion is None:
            raise ErrorPlantilla("PLANTILLA_VACIA",
                                 "La plantilla no pide ningun dato ni foto.")

    esquema = componer(definicion)
    with transaction.atomic():
        if WorkType.objects.filter(org=org, codigo=codigo).exists():
            raise ErrorPlantilla(
                "YA_EXISTE",
                f"La empresa ya tiene una plantilla con el codigo '{codigo}'. "
                "Editala en vez de crear otra.")
        tipo = WorkType.objects.create(org=org, codigo=codigo, nombre=nombre,
                                       labor=labor, activo=True)
        if asuntos is not None or plazo_dias not in (None, ""):
            tipo.asuntos = _asuntos(asuntos or [], tipo)
            _sin_labor_sin_asuntos(tipo.labor, tipo.asuntos)
            tipo.plazo_dias = _plazo(plazo_dias)
            tipo.save(update_fields=["asuntos", "plazo_dias"])
        version = WorkTypeVersion.objects.create(
            work_type=tipo, version=1, schema_version=1,
            estado=WorkTypeVersion.PUBLICADA, esquema=esquema)
    return tipo, version


def publicar(tipo: WorkType, definicion: dict, *, nombre: str | None = None,
             labor: str | None = None, asuntos=None,
             plazo_dias=None, con_plazo: bool = False
             ) -> tuple[WorkTypeVersion, bool]:
    """Publica una version NUEVA. Devuelve `(version, cambio)`.

    Si el esquema no cambio no se crea otra version: «v7» igual a «v6» solo
    ensuciaria la historia y haria creer que algo cambio. El nombre y la labor
    son del TIPO, no de la version, asi que se guardan aunque el formulario sea
    el mismo.
    """
    esquema = componer(definicion)
    with transaction.atomic():
        #  Dos personas publicando a la vez se pelearian el mismo numero de
        #  version; el unique lo frenaria con un 500. El bloqueo las ordena.
        tipo = WorkType.objects.select_for_update().get(pk=tipo.pk)
        campos = []
        if nombre is not None:
            tipo.nombre = _texto(nombre, "el nombre")
            campos.append("nombre")
        if labor is not None:
            tipo.labor = _labor(labor, tipo.org_id)
            campos.append("labor")
        #  Asuntos y plazo, del TIPO como la labor (19/10/2026). Viajan solo si
        #  vienen: 'con_plazo' distingue "no lo mande" de "lo borro" (None).
        if asuntos is not None:
            tipo.asuntos = _asuntos(asuntos, tipo)
            campos.append("asuntos")
        if con_plazo:
            tipo.plazo_dias = _plazo(plazo_dias)
            campos.append("plazo_dias")
        if "asuntos" in campos or "labor" in campos:
            _sin_labor_sin_asuntos(tipo.labor, tipo.asuntos)
        if campos:
            tipo.save(update_fields=campos)

        actual = ultima_publicada(tipo)
        if actual is not None and actual.schema_hash == _hash(esquema):
            return actual, False

        siguiente = (tipo.versions.order_by("-version")
                     .values_list("version", flat=True).first() or 0) + 1
        #  Sin `publicada_en`: `save()` sella la fecha Y el hash solo cuando
        #  viene vacia. Pasarla dejaria la version sin hash, y la comparacion
        #  de arriba no volveria a reconocer un «sin cambios».
        version = WorkTypeVersion.objects.create(
            work_type=tipo, version=siguiente, schema_version=1,
            estado=WorkTypeVersion.PUBLICADA, esquema=esquema)
    return version, True
