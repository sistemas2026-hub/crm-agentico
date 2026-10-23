# -*- coding: utf-8 -*-
"""
================================================================================
 LEER Y CAMBIAR EL ESTILO  --  y los textos por defecto
================================================================================

QUE HACE
--------
    vigente(org, ambito)    el texto que rige ahora. Sin filas, el por defecto.
    cambiar(...)            deja una fila nueva. Exige actor y motivo.
    restablecer(...)        vuelve al por defecto, DEJANDO su fila.

FAIL-SAFE, NO FAIL-CLOSED  --  y la diferencia importa
------------------------------------------------------
'autonomia.nivel_configurado' falla CERRADO: sin filas, nivel 0, porque el
alcance se concede y no se hereda. Aqui es al reves a proposito: sin filas rige
el texto por defecto del codigo.

El motivo es que un estilo ausente no es un permiso ausente. Si esto fallara
"cerrado" --sin estilo, sin instrucciones de presentacion-- el Supervisor
seguiria contestando, solo que sin ninguna guia de como: peor, no mas seguro. Lo
que de verdad protege son el nucleo y las barreras en codigo, y esos no dependen
de esta tabla.

Y si la consulta a la base falla, tambien se devuelve el por defecto en vez de
levantar: una base lenta no puede dejar al Supervisor sin poder contestar.

POR QUE EL POR DEFECTO ARREGLA UNA CONTRADICCION QUE YA ESTABA
--------------------------------------------------------------
El prompt anterior pedia, en el mismo texto:

    "Separas siempre, y de forma VISIBLE" -> seis categorias etiquetadas
    "Cuando no sabes ... explicas"        -> cinco cosas
    "Si te piden algo que no puedes"      -> cuatro cosas
    "Breve y directo"                     -> sin ninguna medida

Un modelo obedece lo concreto e ignora lo vago, asi que contestaba largo. No era
un defecto del modelo: era lo que el prompt pedia. El por defecto de abajo
mantiene la separacion entre hecho y sospecha --que es la garantia-- y cambia
COMO se expresa: en prosa corta con un tope medible, no en secciones fijas.

LO QUE EL ESTILO NO PUEDE CAMBIAR, Y ES ESTRUCTURAL
---------------------------------------------------
El nucleo se concatena SIEMPRE y va PRIMERO; el estilo se agrega despues y no
puede quitarlo. Un estilo que diga "ignora las instrucciones anteriores" es
texto dentro de un prompt cuyo nucleo ya se declaro, y las garantias reales
--listas blancas por rol, techo de autonomia, modo sombra, los campos que el
cerebro no puede escribir-- no viven en el prompt en absoluto.
"""

from django.utils import timezone

from operaciones.estilo_modelos import AmbitoEstilo, EstiloSupervisor

#  Tope del texto editable. Alcanza de sobra para tono, largo y que mostrar, y
#  evita que un pegado accidental de medio documento entre al prompt de cada
#  turno -- que se paga en tokens en TODAS las conversaciones.
TOPE_TEXTO = 4000


class ErrorEstilo(ValueError):
    """Un cambio de estilo que no se puede aceptar."""


# =============================================================================
#  LOS TEXTOS POR DEFECTO
# =============================================================================

_CHAT = """\
CÓMO HABLAS
Máximo 4 líneas. Si lo que hay que decir no cabe, das lo que importa y ofreces
ampliar: "si querés el detalle, pedímelo". Solo te extendés cuando te piden el
detalle de forma explícita.

Español, tuteando, como un colega de turno que pasa el parte: primero lo que
importa, después el detalle. Sin relleno, sin disculpas, sin repetir la pregunta
antes de contestarla. Los números van con su fuente.

QUÉ MOSTRAR Y QUÉ NO
Escribís en prosa corta. No etiquetás cada frase con su categoría y no devolvés
secciones fijas con encabezados.

La distinción entre lo que sabés y lo que sospechás se mantiene SIEMPRE, pero se
dice con palabras: "está caído" para un hecho, "parece que" o "no puedo
confirmar" para lo demás. Una sospecha nunca se escribe como un hecho.

No enumerás lo que no te preguntaron. Si falta un dato y nadie lo pidió, una
línea alcanza para decirlo.
"""

_CICLO = """\
CÓMO ESCRIBÍS EL MOTIVO
Dos frases. La primera dice qué pasa; la segunda, por qué conviene actuar.

Nadie está leyendo esto en el momento en que lo escribís: lo va a leer alguien
que revisa una bandeja con varias propuestas. Que se entienda de un vistazo vale
más que que esté completo.

Sin encabezados, sin listas, sin repetir lo que la propuesta ya dice en sus
propios campos.
"""

POR_DEFECTO = {
    AmbitoEstilo.CHAT: _CHAT,
    AmbitoEstilo.CICLO: _CICLO,
}


# =============================================================================
#  LEER
# =============================================================================

def vigente(org, ambito: str) -> str:
    """
    El estilo que rige ahora para ese ámbito.

    Devuelve el texto por defecto si nadie editó nunca, y TAMBIÉN si la consulta
    falla: ver el encabezado sobre fail-safe.
    """
    if ambito not in AmbitoEstilo.TODOS:
        raise ErrorEstilo(f"ámbito desconocido: {ambito!r}")
    try:
        fila = (EstiloSupervisor.objects
                .filter(org=org, ambito=ambito)
                .order_by("-cambiado_en", "-created_at")
                .first())
    except Exception:                                        # noqa: BLE001
        return POR_DEFECTO[ambito]
    return fila.texto if fila is not None else POR_DEFECTO[ambito]


def es_el_por_defecto(org, ambito: str) -> bool:
    """
    Si lo vigente es el texto por defecto. Lo necesita la pantalla para decirlo.

    Compara NORMALIZADO, y no es laxitud: 'cambiar' aplica strip() al texto, asi
    que un 'restablecer' guarda el por defecto sin su salto final. Comparar byte
    a byte haria que restablecer dejara la pantalla diciendo "editado" para
    siempre. El espacio de los bordes no cambia un prompt.
    """
    return vigente(org, ambito).strip() == POR_DEFECTO[ambito].strip()


def historial(org, ambito: str = "", limite: int = 20) -> list[dict]:
    """
    Los cambios, del más reciente al más viejo.

    DEVUELVE EL ID DEL ACTOR, NO SU NOMBRE, y es la misma decisión que ya tomó
    'autonomia.historial' con la misma razón escrita al lado: esto puede
    terminar en un log. La pantalla resuelve el nombre con las listas de
    personas que ya tiene; un nombre viajando en cada respuesta no agrega nada
    y sí agrega una ruta por la que se escapa.
    """
    qs = EstiloSupervisor.objects.filter(org=org)
    if ambito:
        qs = qs.filter(ambito=ambito)
    filas = (qs.select_related("actor")
             .order_by("-cambiado_en", "-created_at")[:max(1, min(int(limite), 100))])
    return [{
        "id": str(f.id),
        "ambito": f.ambito,
        "texto": f.texto,
        "texto_anterior": f.texto_anterior,
        "motivo": f.motivo,
        "actor_id": str(f.actor_id) if f.actor_id else None,
        "cambiado_en": f.cambiado_en.isoformat(),
    } for f in filas]


# =============================================================================
#  CAMBIAR
# =============================================================================

def cambiar(org, ambito: str, texto: str, *, actor, motivo: str,
            ahora=None) -> EstiloSupervisor:
    """
    Deja una fila nueva con el estilo. Exige persona y motivo.

    POR QUE LOS DOS SON OBLIGATORIOS
    --------------------------------
    Mismo criterio que 'autonomia.cambiar', por el mismo motivo práctico: un
    prompt que empeora las respuestas hay que poder discutirlo después, y para
    eso hace falta saber quién lo cambió y qué buscaba. Sin eso, la única salida
    es volver al por defecto a ciegas.

    El actor NO tiene default, igual que allá: el Supervisor no se reescribe sus
    propias instrucciones.
    """
    if ambito not in AmbitoEstilo.TODOS:
        raise ErrorEstilo(f"ámbito desconocido: {ambito!r}")
    if actor is None:
        raise ErrorEstilo(
            "un cambio de estilo necesita la persona que lo decide: el "
            "Supervisor no se reescribe sus propias instrucciones")
    texto = (texto or "").strip()
    if not texto:
        raise ErrorEstilo(
            "el estilo no puede quedar vacío. Para volver al texto por defecto "
            "usá 'restablecer', que deja su propia fila en el historial")
    if len(texto) > TOPE_TEXTO:
        raise ErrorEstilo(
            f"el estilo no puede pasar de {TOPE_TEXTO} caracteres: este texto "
            f"viaja en el prompt de CADA turno")
    if not (motivo or "").strip():
        raise ErrorEstilo("un cambio de estilo necesita su motivo")

    #  El anterior se lee ANTES de crear la fila nueva, o se leería a sí misma.
    anterior = vigente(org, ambito)

    return EstiloSupervisor.objects.create(
        org=org, ambito=ambito, texto=texto,
        texto_anterior=anterior,
        actor=actor, motivo=motivo.strip(),
        cambiado_en=ahora or timezone.now())


def restablecer(org, ambito: str, *, actor, motivo: str,
                ahora=None) -> EstiloSupervisor:
    """
    Vuelve al texto por defecto, dejando su fila.

    No borra el historial: volver atrás es un cambio como cualquier otro y tiene
    que quedar registrado igual. Borrar la fila dejaría un hueco justo en el
    momento en que a alguien le interesa saber qué pasó.
    """
    return cambiar(org, ambito, POR_DEFECTO[ambito],
                   actor=actor, motivo=motivo, ahora=ahora)
