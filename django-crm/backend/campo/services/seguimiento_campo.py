# -*- coding: utf-8 -*-
"""La bitacora de una intervencion: INICIO, AVANCE, BLOQUEO y CIERRE.

QUE ES ESTO Y QUE NO ES
-----------------------
El comunicado de operaciones exige que todo trabajo reporte esos cuatro momentos.
Hasta ahora eso se escribia en Google Chat, donde no se puede buscar, no queda
atado al ticket y cada persona lo redacta distinto.

Esto lo convierte en HECHOS del sistema, y para eso no hace falta una tabla
nueva: `EventoTrabajo` ya es una bitacora append-only por orden desde el
principio, con nueve tipos escribiendose. Se le agregan cuatro.

LAS TRES DECISIONES QUE GOBIERNAN ESTE ARCHIVO
----------------------------------------------
Estan escritas en `SPEC/objetivos/seguimiento-campo-por-ticket.md` y no se
reinterpretan aca:

1. **No hay tercer eje de estado.** Registrar un `bloqueo_campo` NO mueve
   `estado_operativo`. La maquina de estados sigue siendo la de
   `services/transiciones.py`, que NIEGA los saltos invalidos; un estado derivado
   de "el ultimo evento" tirarria esa garantia. Que `bloqueada` sea un estado
   operativo es la fase siguiente, con sus transiciones declaradas.

2. **Los campos los declara el tipo de trabajo, no este archivo.** Ni un
   `nivel_1550`, ni un `PLC`, ni un `puerto`. Otro ISP mide otra ventana y nombra
   distinto sus elementos: con campos fijos, el segundo ISP necesitaria un commit
   para dar de alta un tipo de trabajo. El esquema vive en
   `WorkTypeVersion.esquema["seguimiento"][<momento>]`.

3. **Una declaracion humana se guarda como tal.** "Servicio validado OK" no es
   una conclusion del sistema: es alguien afirmandolo. Un campo marcado
   `declaracion: true` se guarda con QUIEN lo afirmo y CUANDO. Es el mismo
   criterio que `ACCION_CONFIRMADA`: que el equipo responda no dice que la casa
   tenga internet.

POR QUE CADA EVENTO GUARDA SU PROPIO ESQUEMA
--------------------------------------------
Un `avance_campo` de hoy se va a leer en tres años, cuando el tipo de trabajo ya
cambio de version cinco veces. Si la lectura fuera contra el esquema VIGENTE, el
mismo evento diria otra cosa --o dejaria de decir nada-- sin que nadie lo toque.

Asi que el evento guarda `definicion`: los campos tal como estaban cuando se
capturo. La lectura usa ese snapshot y no consulta `WorkTypeVersion`. Es la unica
forma de que la historia sea historia.

EL HUECO DEL VALIDADOR, Y POR QUE SE TAPA ACA
---------------------------------------------
`validar_campos_tecnicos` solo revisa las claves que LLEGAN: un obligatorio
ausente del diccionario no se recorre, y pasa. Eso es correcto para el flujo del
telefono, que guarda avances parciales de un formulario a medio llenar. Pero un
reporte de seguimiento no es parcial --se manda cuando se manda-- asi que los
obligatorios ausentes se exigen aca, y hay una prueba que lo afirma.
"""

from __future__ import annotations

from django.utils import timezone

from campo.models import EventoTrabajo
from campo.services.validador import validar_campos_tecnicos


class SeguimientoInvalido(Exception):
    """Lo que se niega antes de escribir en la bitacora."""

    def __init__(self, mensaje, errores=None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        #: Errores por campo, para que la pantalla los pinte donde corresponde en
        #: vez de mostrar un solo texto arriba.
        self.errores = errores or {}


INICIO = "inicio"
AVANCE = "avance"
BLOQUEO = "bloqueo"
CIERRE = "cierre"

#: El momento que se reporta, y el tipo con el que queda en la bitacora. El
#: sufijo `_campo` distingue estos de los nueve que ya existian: `trabajo_iniciado`
#: es una TRANSICION de estado; `inicio_campo` es un REPORTE de la persona.
TIPOS = {
    INICIO: "inicio_campo",
    AVANCE: "avance_campo",
    BLOQUEO: "bloqueo_campo",
    CIERRE: "cierre_campo",
}

MOMENTOS = tuple(TIPOS.keys())

#: De que hechos del sistema se muestra algo mas que el cambio de estado, y QUE
#: exactamente. Es una lista blanca: `datos` es un JSONField y volcarlo completo
#: dejaria pasar lo que cualquier servicio haya guardado ahi.
CAMPOS_EXPUESTOS = {
    "bloqueo_resuelto": (
        "que_se_hizo",
        "resuelto_por_rol",
        "minutos_detenido",
        "volvio_a",
        "requeria_noc",
    ),
    "bloqueo_detuvo_el_trabajo": ("requiere_noc", "estado_operativo_anterior"),
    "bloqueo_libero_el_trabajo": ("volvio_a",),
}


#: Como se lee cada uno en una linea de tiempo.
ETIQUETAS = {
    "inicio_campo": "INICIO",
    "avance_campo": "AVANCE",
    "bloqueo_campo": "BLOQUEO",
    "cierre_campo": "CIERRE DE CAMPO",
    # Los hechos del sistema alrededor de un bloqueo. Se distinguen del REPORTE
    # --`bloqueo_campo`-- a proposito: uno es lo que dijo una persona, los otros
    # son lo que hizo la maquina de estados.
    "bloqueo_detuvo_el_trabajo": "ESTADO → BLOQUEADA",
    "bloqueo_libero_el_trabajo": "ESTADO → en marcha",
    "bloqueo_resuelto": "BLOQUEO RESUELTO",
    # Los que ya se escribian, para que la linea de tiempo sea UNA sola y no dos
    # listas que el lector tiene que cruzar a mano.
    "orden_creada": "Orden creada",
    "asignacion": "Técnico asignado",
    "tecnico_asignado": "Técnico asignado",
    "datos_actualizados": "Datos del trabajo actualizados",
    "evidencia_confirmada": "Evidencia confirmada",
    "correccion_requerida": "El supervisor devolvió el trabajo",
    "consumo": "Material consumido",
    "contexto_refrescado": "Contexto refrescado",
    "trabajo_iniciado": "Trabajo iniciado",
    "case": "Caso",
    "tecnico": "Técnico",
}

#: El minimo que se pide cuando el tipo de trabajo no declara nada para ese
#: momento. Es deliberadamente pobre y generico: una nota en palabras, y en el
#: bloqueo ademas que hace falta del NOC --sin eso un bloqueo no es accionable y
#: vuelve a ser un mensaje de chat--. Cualquier medicion la declara la empresa.
MINIMO = {
    INICIO: [
        {
            "id": "nota",
            "titulo": "Qué se encontró y qué se va a hacer",
            "tipo": "texto",
            "reglas": {"required": True, "min": 3},
        },
    ],
    AVANCE: [
        {
            "id": "nota",
            "titulo": "Qué se hizo y qué sigue",
            "tipo": "texto",
            "reglas": {"required": True, "min": 3},
        },
    ],
    BLOQUEO: [
        {
            "id": "motivo",
            "titulo": "Por qué no se puede seguir",
            "tipo": "texto",
            "reglas": {"required": True, "min": 3},
        },
        {
            "id": "necesita_de_noc",
            "titulo": "Qué se necesita del NOC",
            "tipo": "texto",
            "reglas": {"required": True, "min": 3},
        },
    ],
    CIERRE: [
        {
            "id": "solucion",
            "titulo": "Qué se hizo para resolverlo",
            "tipo": "texto",
            "reglas": {"required": True, "min": 3},
        },
        {
            "id": "servicio_validado",
            "titulo": "¿El servicio quedó funcionando?",
            "tipo": "booleano",
            "reglas": {"required": True},
            # Decision 3: esto lo AFIRMA una persona. El sistema no puede saberlo
            # y no va a decir que lo sabe.
            "declaracion": True,
        },
    ],
}


def _esquema_de(orden) -> dict:
    version = getattr(orden, "tipo_trabajo_version", None)
    return (getattr(version, "esquema", None) or {}) if version else {}


def formulario_de(orden, momento: str) -> dict:
    """Que se le pide a quien reporta ese momento, en este tipo de trabajo.

    La app y la pantalla dibujan ESTO. Ninguna de las dos sabe que campos existen
    hasta preguntar, que es lo que permite que la empresa siguiente traiga los
    suyos sin tocar codigo.
    """
    _exigir_momento(momento)
    version = getattr(orden, "tipo_trabajo_version", None)
    seguimiento = (_esquema_de(orden).get("seguimiento") or {})
    declarado = seguimiento.get(momento) or {}

    campos = declarado.get("campos")
    if not isinstance(campos, list) or not campos:
        campos = MINIMO[momento]
        del_tenant = False
    else:
        del_tenant = True

    return {
        "momento": momento,
        "tipo_evento": TIPOS[momento],
        "campos": campos,
        "evidencias": declarado.get("evidencias") or [],
        #: Que la empresa no haya declarado nada no es un error, pero la pantalla
        #: puede decirlo: "se esta usando el minimo generico".
        "declarado_por_el_tipo_de_trabajo": del_tenant,
        "schema_version": getattr(version, "schema_version", None),
        "version_del_tipo": getattr(version, "version", None),
    }


def registrar(
    orden,
    *,
    profile,
    momento: str,
    respuestas: dict | None = None,
    capturado_en_dispositivo=None,
):
    """Escribe un reporte en la bitacora de la orden. Devuelve el `EventoTrabajo`.

    NO mueve `estado_operativo` -- ver la decision 1 del encabezado.
    """
    _exigir_momento(momento)
    respuestas = dict(respuestas or {})

    formulario = formulario_de(orden, momento)
    definicion = formulario["campos"]
    mapa = {c["id"]: c for c in definicion}

    # 1. Los obligatorios que NO llegaron. El validador no los ve (ver encabezado).
    faltan = {
        cid: "Este campo es requerido."
        for cid, c in mapa.items()
        if (c.get("reglas") or {}).get("required") and cid not in respuestas
    }

    # 2. Lo que si llego, contra tipos y reglas.
    limpios, errores = validar_campos_tecnicos({"campos": definicion}, respuestas)
    errores = {**faltan, **errores}
    if errores:
        raise SeguimientoInvalido(
            "El reporte no se puede guardar todavía: hay campos sin completar o "
            "con un valor que no corresponde.",
            errores=errores,
        )

    # 3. El orden de los hechos. Un cierre sin inicio es un reporte al que le
    #    falta la mitad de la historia, y quien lo lea no va a poder reconstruir
    #    cuanto duro la intervencion.
    if momento == CIERRE and not _hubo(orden, TIPOS[INICIO]):
        raise SeguimientoInvalido(
            "No se puede cerrar una intervención que nunca se inició: registrá "
            "primero el INICIO."
        )
    if momento == INICIO and _hubo(orden, TIPOS[INICIO]):
        raise SeguimientoInvalido(
            "Esta intervención ya tiene un INICIO registrado. Lo que sigue es un "
            "AVANCE."
        )

    ahora = timezone.now()
    version = getattr(orden, "tipo_trabajo_version", None)

    datos = {
        # EL SNAPSHOT. Sin esto, leer este evento dentro de tres años dependeria
        # del esquema vigente entonces.
        "definicion": definicion,
        # QUE FOTO SE PEDIA EN ESTE REPORTE, congelado igual que los campos.
        #
        # No es decoracion: es lo que decide, mas tarde, si una foto que llega
        # pertenece a este evento. Validarlo contra el esquema VIGENTE dejaria
        # que una version nueva del tipo de trabajo volviera invalida una foto
        # que el tecnico saco siguiendo lo que la app le mostro ese dia -- o, al
        # reves, que aceptara una que entonces nadie le pidio.
        #
        # Y sirve para leer: quien abre la bitacora dentro de un año puede ver
        # que aca se pedia una foto y que no esta, en vez de no saber que
        # faltaba.
        "evidencias": formulario["evidencias"],
        "schema_version": getattr(version, "schema_version", None),
        "version_del_tipo": getattr(version, "version", None),
        "schema_hash": getattr(version, "schema_hash", "") or "",
        "respuestas": _serializable(limpios),
        "declaraciones": _declaraciones(mapa, limpios, profile, ahora),
        # La hora que declaro el telefono, distinta de `created_at`, que es
        # cuando el servidor la recibio. Con la app offline las dos se separan, y
        # confundirlas es lo que haria que un tecnico sin señal parezca uno que no
        # reporta. La fase D se apoya en tener las dos.
        "capturado_en_dispositivo": (
            capturado_en_dispositivo.isoformat()
            if hasattr(capturado_en_dispositivo, "isoformat")
            else (capturado_en_dispositivo or None)
        ),
        "recibido_en_servidor": ahora.isoformat(),
    }

    return EventoTrabajo.objects.create(
        org=orden.org, orden=orden, tipo=TIPOS[momento], profile=profile, datos=datos
    )


def _declaraciones(mapa, limpios, profile, ahora) -> dict:
    """Lo que una persona AFIRMA, con su nombre y su hora.

    Decision 3 del encabezado. Se guarda aparte de `respuestas` para que leerlo
    sea imposible de confundir con algo que el sistema midio.
    """
    salida = {}
    for cid, definicion in mapa.items():
        if not definicion.get("declaracion") or cid not in limpios:
            continue
        salida[cid] = {
            "valor": _valor_serializable(limpios[cid]),
            "declarado_por": str(profile.id) if profile else None,
            "declarado_por_nombre": _nombre(profile),
            "declarado_en": ahora.isoformat(),
            #: Se escribe en el dato, no solo en la pantalla: cualquiera puede
            #: cambiar un titulo en el frontend.
            "es_declaracion_humana": True,
        }
    return salida


#: Lo que de una evidencia sale hacia afuera. Lista blanca y no un `values()`:
#: la fila lleva `storage_key` -- la ruta real del archivo en el bucket -- y
#: `metadatos_captura`, que trae el GPS del telefono del tecnico. Ninguna de las
#: dos tiene nada que hacer en una pantalla, y un dia alguien agrega un campo
#: mas sin acordarse de este punto.
CAMPOS_DE_EVIDENCIA = (
    "id",
    "requisito_id",
    "nombre_original",
    "mime_type",
    "bytes",
    "estado_archivo",
)


def _evidencias_de(evento) -> list:
    """Las fotos de un reporte, con lo justo para mostrarlas y pedirlas.

    NO devuelve una URL. La de lectura se emite aparte, firmada y por evidencia
    (`evidencias/<id>/url/`), porque dura poco: meterla en la linea de tiempo la
    volveria un enlace vencido en cuanto alguien deje la pantalla abierta.
    """
    salida = []
    for ev in evento.evidencias.all().order_by("created_at"):
        fila = {c: getattr(ev, c) for c in CAMPOS_DE_EVIDENCIA}
        fila["id"] = str(fila["id"])
        fila["capturada_en_cliente"] = (
            ev.capturada_en_cliente.isoformat() if ev.capturada_en_cliente else None
        )
        fila["recibida_en_servidor"] = (
            ev.recibida_en_servidor.isoformat() if ev.recibida_en_servidor else None
        )
        #: Que la foto este EN el servidor no es lo mismo que que exista una fila
        #: diciendo que alguien la iba a subir. Quien dibuja necesita esa
        #: diferencia para no mostrar un hueco roto.
        fila["disponible"] = ev.estado_archivo in ("recibido", "verificado")
        salida.append(fila)
    return salida


def linea_de_tiempo(orden) -> dict:
    """La intervencion entera, en orden, mezclando los cuatro nuevos y los nueve.

    Dos listas separadas obligarian a quien lee a cruzarlas a mano para saber que
    paso antes: la devolucion del supervisor, o el ultimo avance.
    """
    eventos = list(
        EventoTrabajo.objects.filter(org=orden.org, orden=orden)
        .select_related("profile__user")
        .order_by("created_at")
    )

    tipos_seguimiento = set(TIPOS.values())
    salida = []
    for e in eventos:
        datos = e.datos or {}
        es_seguimiento = e.tipo in tipos_seguimiento
        fila = {
            "id": str(e.id),
            "tipo": e.tipo,
            "etiqueta": ETIQUETAS.get(e.tipo, e.tipo.replace("_", " ")),
            "es_seguimiento": es_seguimiento,
            "quien": _nombre(e.profile),
            "recibido_en": e.created_at.isoformat() if e.created_at else None,
            "capturado_en_dispositivo": datos.get("capturado_en_dispositivo"),
        }
        if es_seguimiento:
            # Se lee con el snapshot del evento, NO con el esquema vigente.
            fila["detalle"] = _leer_con_su_esquema(datos)
            fila["declaraciones"] = datos.get("declaraciones") or {}
            # Las fotos de ESTE reporte, y las que se le pedian. Las dos listas,
            # porque una foto que falta solo se ve comparandolas: sin la segunda,
            # un bloqueo sin foto y un bloqueo al que nunca se le pidio una se
            # leen igual.
            fila["evidencias"] = _evidencias_de(e)
            fila["evidencias_declaradas"] = datos.get("evidencias") or []
        elif e.tipo in CAMPOS_EXPUESTOS:
            # Hechos del sistema que si tienen algo que contar. Se exponen las
            # claves nombradas y NADA MAS: volcar el JSON entero dejaria salir lo
            # que cualquier servicio haya metido ahi, hoy o dentro de un año.
            fila["datos"] = {
                k: datos.get(k) for k in CAMPOS_EXPUESTOS[e.tipo] if k in datos
            }
            fila["estado_anterior"] = datos.get("estado_anterior")
            fila["estado_nuevo"] = datos.get("nuevo_estado") or datos.get("estado_nuevo")
        else:
            # De los otros se muestra el cambio de estado si lo trae; nunca el
            # JSON entero, que puede llevar cualquier cosa.
            #
            # LAS TRES CLAVES, porque el sistema escribe tres nombres distintos y
            # leer uno solo deja la mitad de la bitacora muda:
            #   `nuevo_estado`              -- transiciones.py::_aplicar_transicion
            #   `estado_validacion_nuevo`   -- transiciones.py::_aplicar_validacion
            #   `estado_nuevo`              -- por si alguien lo escribe asi
            # Se descubrio leyendo el codigo: la primera version de esta funcion
            # leia solo `estado_nuevo`, y la prueba pasaba porque CREABA el evento
            # con esa clave en vez de ejecutar una transicion de verdad.
            fila["estado_anterior"] = (
                datos.get("estado_anterior")
                or datos.get("estado_validacion_anterior")
            )
            fila["estado_nuevo"] = (
                datos.get("nuevo_estado")
                or datos.get("estado_nuevo")
                or datos.get("estado_validacion_nuevo")
            )
        salida.append(fila)

    registrados = [e.tipo for e in eventos if e.tipo in tipos_seguimiento]
    return {
        "orden_id": str(orden.id),
        "eventos": salida,
        "ultimo_reporte": _ultimo_reporte(eventos, tipos_seguimiento),
        "momentos_registrados": sorted(set(registrados)),
        "avisos": _avisos(registrados),
    }


def _avisos(registrados: list[str]) -> list[str]:
    """Lo que la bitacora tiene de raro, dicho sin bloquear nada.

    Hay reportes que llegan fuera de orden --un AVANCE antes del INICIO-- porque
    alguien empezo a trabajar y reporto recien a la media hora. NO se rechaza: un
    reporte que se pierde es peor que uno desordenado, y el que reporta no tiene
    por que pelear con el formulario en la calle.

    Pero tampoco se calla, porque quien lea la ficha despues necesita saber que
    falta la mitad de la historia --sin el INICIO no hay con que comparar la
    medicion final, ni desde cuando se cuenta la intervencion--.
    """
    avisos = []
    if TIPOS[AVANCE] in registrados and TIPOS[INICIO] not in registrados:
        avisos.append(
            "Hay avances reportados sin un INICIO: falta la condición inicial "
            "contra la cual comparar, y desde cuándo se cuenta la intervención."
        )
    if TIPOS[INICIO] in registrados and registrados.index(TIPOS[INICIO]) > 0:
        primero = registrados[0]
        if primero != TIPOS[INICIO]:
            avisos.append(
                "El INICIO se registró después de otro reporte. El orden que se "
                "muestra es el real; no se reordena para que parezca prolijo."
            )
    return avisos


def _leer_con_su_esquema(datos: dict) -> list[dict]:
    """Las respuestas con el titulo que tenian cuando se capturaron."""
    definicion = datos.get("definicion") or []
    respuestas = datos.get("respuestas") or {}
    titulos = {c.get("id"): c.get("titulo") or c.get("id") for c in definicion}

    filas = []
    for cid, valor in respuestas.items():
        filas.append(
            {
                "id": cid,
                # Un campo que ya no esta en el esquema de hoy igual se lee: su
                # titulo viajo con el evento.
                "titulo": titulos.get(cid, cid),
                "valor": valor,
                "en_el_esquema_de_entonces": cid in titulos,
            }
        )
    return filas


def _ultimo_reporte(eventos, tipos_seguimiento) -> dict | None:
    """Cuando fue el ultimo reporte. SIN veredicto.

    Devuelve los minutos porque son un dato, no una conclusion: decidir si eso
    esta vencido --y distinguirlo de un telefono sin sincronizar-- es la fase D, y
    adelantarlo aca significaria inventar el semaforo en el lugar equivocado.
    """
    ultimos = [e for e in eventos if e.tipo in tipos_seguimiento]
    if not ultimos:
        return None
    e = ultimos[-1]
    datos = e.datos or {}
    minutos = None
    if e.created_at:
        minutos = int((timezone.now() - e.created_at).total_seconds() // 60)
    return {
        "tipo": e.tipo,
        "etiqueta": ETIQUETAS.get(e.tipo, e.tipo),
        "quien": _nombre(e.profile),
        "recibido_en": e.created_at.isoformat() if e.created_at else None,
        "capturado_en_dispositivo": datos.get("capturado_en_dispositivo"),
        "minutos_desde_que_lo_recibimos": minutos,
    }


def _hubo(orden, tipo: str) -> bool:
    return EventoTrabajo.objects.filter(org=orden.org, orden=orden, tipo=tipo).exists()


def _exigir_momento(momento) -> None:
    if momento not in TIPOS:
        raise SeguimientoInvalido(
            f"'{momento}' no es un momento de seguimiento. Los que hay: "
            + ", ".join(MOMENTOS)
            + "."
        )


def _nombre(profile) -> str | None:
    if profile is None:
        return None
    user = getattr(profile, "user", None)
    return (getattr(user, "name", "") or getattr(user, "email", "") or "").strip() or None


def _valor_serializable(valor):
    """Decimal y date no entran en un JSONField tal cual."""
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    if isinstance(valor, (int, float, bool, str)) or valor is None:
        return valor
    return str(valor)


def _serializable(valores: dict) -> dict:
    return {k: _valor_serializable(v) for k, v in valores.items()}
