# -*- coding: utf-8 -*-
"""
================================================================================
 El catalogo de desenlaces  --  que le paso al cliente, en un vocabulario comun
================================================================================

Contrato §3.5. Un desenlace no es "quien cerro" (eso es 'cerrada_por_tipo') ni
"como salio" (eso es el estado): es QUE LE PASABA AL CLIENTE, dicho en un
vocabulario que se pueda contar.

DOS NIVELES, Y LA RAZON DE QUE SEAN DOS
---------------------------------------
  base      doce codigos en CODIGO, iguales para todo ISP. Cada uno es tambien
            su propia categoria. Esto es plataforma: nucleo/ no conoce a nadie.
  propios   cada empresa agrega los suyos desde la interfaz, y CADA UNO declara
            a que categoria base pertenece (I16). 'fibra_poste_17' es util para
            el jefe de red de esa empresa; para la plataforma es
            'red_distribucion', y asi las metricas siguen sumando entre
            empresas que llaman distinto a lo mismo.

La base funciona SIN escribir config (§3.5). Eso no es una comodidad: escribir
'tenant_config' de Rapilink hoy partiria la medicion de razonamiento ON vs OFF
(Q3). Una empresa que no configura nada tiene los doce codigos y puede cerrar.

LO QUE UNA EMPRESA NO PUEDE HACER
---------------------------------
  redefinir un codigo base    'facturacion' significa lo mismo en todas partes.
                              Un propio con el mismo codigo lo haria ambiguo en
                              cualquier metrica cruzada.
  dejar el catalogo vacio     ocultar los doce sin agregar ninguno deja a sus
                              operadores sin forma de cerrar a mano, y un
                              cierre manual EXIGE codigo (T17). Se rechaza al
                              cargar la config, no al intentar cerrar de noche.

OCULTAR NO ES BORRAR
--------------------
Un codigo oculto desaparece de lo que un operador puede ELEGIR. No invalida lo
ya cerrado con el --el pasado no se reescribe-- y no impide que la plataforma
lo escriba sola: el cierre por plazo (T16) usa 'sin_respuesta_cliente' y no es
una eleccion de nadie, asi que ocultarlo no lo desactiva.
"""

from __future__ import annotations

#: Los doce de plataforma. Cada codigo ES su propia categoria base (§3.5).
#: El orden es el de la pantalla: primero donde estuvo la falla, de la casa del
#: cliente hacia la red y despues la configuracion, que no esta en ningun tramo
#: fisico; despues lo que no era una falla de la red.
#:
#: Los nombres llevan tildes desde el 10/11/2026: son lo que lee el operador.
#: Lo que se guarda y se cuenta es el CODIGO, asi que corregir un nombre no
#: toca ninguna fila ni ninguna metrica.
BASE: dict[str, str] = {
    "equipo_cliente": "Equipo del cliente",
    "wifi_cliente": "WiFi del cliente",
    "fibra_acometida": "Fibra o acometida",
    "red_distribucion": "Red de distribución",
    "red_central": "Red central",
    "configuracion": "Configuración",
    "facturacion": "Facturación",
    "solicitud_comercial": "Solicitud comercial",
    "resuelto_por_cliente": "Lo resolvió el cliente",
    "sin_respuesta_cliente": "El cliente no respondió",
    "falso_positivo_ia": "Falso positivo de la IA",
    "otro": "Otro",
}

#: Las categorias que son una FALLA, en algun tramo del servicio. La pantalla
#: las agrupa aparte (10/11/2026): con los doce en una sola grilla el operador
#: no veia que la lista tiene dos preguntas distintas -- donde fallo, o que
#: necesitaba si no era una falla --, y la grilla los leia mezclados.
#: Un codigo propio cae en el grupo de su categoria base (I16).
FALLAS = frozenset({
    "equipo_cliente", "wifi_cliente", "fibra_acometida",
    "red_distribucion", "red_central", "configuracion",
})

#: Los que no se pueden cerrar sin nota. 'otro' no dice nada por si solo: la
#: columna existe para contar que paso, y un 'otro' sin una linea que lo
#: explique es un cierre que no cuenta nada (10/11/2026). Un propio con
#: categoria 'otro' no entra: ya tiene un nombre que dice que es.
EXIGEN_NOTA = frozenset({"otro"})

#: El que escribe el barrido por plazo (T16). No es una eleccion: es lo que
#: significa que el cliente dejara de contestar.
POR_PLAZO = "sin_respuesta_cliente"

MAX_NOTA = 500


def es_base(codigo: str) -> bool:
    return codigo in BASE


class ErrorCatalogo(ValueError):
    """La extension de una empresa no se puede cargar."""


def _propios_de(config) -> list:
    bloque = getattr(config, "desenlaces", None) if config is not None else None
    return list(getattr(bloque, "propios", []) or []) if bloque else []


def _ocultos_de(config) -> set[str]:
    bloque = getattr(config, "desenlaces", None) if config is not None else None
    return set(getattr(bloque, "ocultos", []) or []) if bloque else set()


def problemas(propios, ocultos) -> list[str]:
    """
    Lo que impide cargar esta extension. Devuelve textos, no levanta: quien
    llama decide si eso es un error de config (lo es) o un aviso.

    Falla cerrado a proposito: una categoria_base invalida no se corrige
    'cayendo a otro'. Si se permitiera, las metricas de plataforma tendrian una
    bolsa de 'otro' que en realidad son fallas de red mal declaradas, y nadie
    lo notaria nunca -- justo lo contrario de para que existe la categoria.
    """
    fallos: list[str] = []
    vistos: set[str] = set()
    for d in propios:
        codigo = (getattr(d, "codigo", "") or "").strip()
        categoria = (getattr(d, "categoria_base", "") or "").strip()
        if not codigo:
            fallos.append("un desenlace propio sin 'codigo'")
            continue
        if es_base(codigo):
            fallos.append(
                f"'{codigo}' es un codigo base y no se puede redefinir: "
                f"significa lo mismo en todas las empresas (§3.5)")
        if codigo in vistos:
            fallos.append(f"'{codigo}' esta declarado dos veces")
        vistos.add(codigo)
        if not categoria:
            fallos.append(
                f"'{codigo}' no declara 'categoria_base'. Es obligatoria (I16): "
                f"sin ella ese cierre no entra a ninguna metrica de plataforma")
        elif not es_base(categoria):
            fallos.append(
                f"'{codigo}' dice pertenecer a '{categoria}', que no es una "
                f"categoria base. Son {sorted(BASE)}")

    for codigo in ocultos:
        if not es_base(codigo):
            fallos.append(
                f"'{codigo}' esta en 'ocultos' y no es un codigo base. Un "
                f"propio se quita sacandolo de la lista, no ocultandolo")

    elegibles = [c for c in BASE if c not in set(ocultos)] + sorted(vistos)
    if not elegibles:
        fallos.append(
            "el catalogo queda vacio: los operadores no podrian cerrar a mano, "
            "y un cierre manual exige un codigo (T17)")
    return fallos


def catalogo(config=None) -> list[dict]:
    """
    Lo que un operador puede ELEGIR, en orden de pantalla: primero los de
    plataforma que la empresa no oculto, despues los suyos.

    Cada entrada dice de donde viene. La pantalla no tiene por que mostrarlo,
    pero quien depura por que un codigo aparece o no, si.

    'grupo', 'categoria_nombre' y 'exige_nota' (10/11/2026) son para que la
    pantalla agrupe, nombre la categoria de un propio y pida la nota sin
    llevar su propia copia de esas reglas: la que valida al cerrar es esta.
    """
    ocultos = _ocultos_de(config)
    salida = [_entrada(c, n, c, "plataforma")
              for c, n in BASE.items() if c not in ocultos]
    for d in _propios_de(config):
        codigo = (getattr(d, "codigo", "") or "").strip()
        if not codigo or es_base(codigo):
            continue
        salida.append(_entrada(
            codigo,
            (getattr(d, "nombre", "") or "").strip() or codigo,
            (getattr(d, "categoria_base", "") or "").strip(),
            "tenant"))
    return salida


def _entrada(codigo: str, nombre: str, categoria: str, origen: str) -> dict:
    return {"codigo": codigo, "nombre": nombre, "categoria_base": categoria,
            "categoria_nombre": BASE.get(categoria, ""),
            "grupo": grupo_de(categoria),
            "exige_nota": exige_nota(codigo),
            "origen": origen}


def grupo_de(categoria: str) -> str:
    """'falla' o 'otra_cosa': a cual de las dos preguntas responde."""
    return "falla" if categoria in FALLAS else "otra_cosa"


def exige_nota(codigo: str) -> bool:
    return (codigo or "").strip() in EXIGEN_NOTA


def validar_nota(codigo: str, nota: str | None) -> None:
    """
    ValueError si este codigo no se puede cerrar con esta nota.

    Va en el motor y no solo en la pantalla: la pantalla es una de las
    puertas (tambien estan el CLI de G8 y completar un desenlace despues), y
    una regla que vive en una sola puerta es una sugerencia.
    """
    if exige_nota(codigo) and not (nota or "").strip():
        raise ValueError(
            "con 'Otro' la nota es obligatoria: sin ella el cierre no dice "
            "que paso")


def categoria_de(codigo: str, config=None) -> str | None:
    """
    La categoria base de un codigo, o None si no se puede resolver.

    None NO es 'otro'. Un codigo que no esta en ningun catalogo es un dato que
    no se entiende, y tratarlo como 'otro' seria inventar una respuesta: se
    rechaza al cerrar, que es cuando todavia hay una persona delante para
    elegir bien.

    Resuelve sobre TODOS los base, ocultos incluidos: ocultar saca el codigo de
    lo que se puede elegir, no de lo que significa. La plataforma sigue
    escribiendo 'sin_respuesta_cliente' por plazo aunque la empresa lo haya
    ocultado de la lista.
    """
    codigo = (codigo or "").strip()
    if not codigo:
        return None
    if es_base(codigo):
        return codigo
    for d in _propios_de(config):
        if (getattr(d, "codigo", "") or "").strip() == codigo:
            categoria = (getattr(d, "categoria_base", "") or "").strip()
            return categoria if es_base(categoria) else None
    return None


def resolver_para_cerrar(codigo: str, config=None, *,
                         por_persona: bool = True) -> tuple[str, str]:
    """
    (codigo, categoria_base) listos para escribir, o ValueError.

    Es el unico punto por el que un desenlace entra a la base. No adivina, no
    normaliza mayusculas ni parecidos: un codigo que no esta en el catalogo de
    esta empresa se rechaza. Aceptar uno desconocido "por si acaso" llenaria la
    columna de erratas que despues nadie puede agrupar.

    'por_persona' distingue quien elige, y no es lo mismo:

      True   lo elige un operador -> tiene que estar VISIBLE. Ocultar existe
             para que una empresa saque de la lista lo que no usa; si igual se
             pudiera elegir, ocultar no significaria nada.
      False  lo escribe la plataforma (hoy solo el cierre por plazo) -> basta
             con que el codigo exista. Ahi no hay ninguna eleccion que ocultar,
             y negarse dejaria a T16 sin poder cerrar nada en una empresa que
             oculto ese codigo de su lista.
    """
    codigo = (codigo or "").strip()
    if not codigo:
        raise ValueError("falta el codigo de desenlace")
    if por_persona:
        if codigo not in {d["codigo"] for d in catalogo(config)}:
            raise ValueError(f"'{codigo}' no esta en el catalogo de desenlaces")
    elif not es_base(codigo) and codigo not in {
            (getattr(d, "codigo", "") or "").strip() for d in _propios_de(config)}:
        raise ValueError(f"'{codigo}' no esta en el catalogo de desenlaces")
    categoria = categoria_de(codigo, config)
    if categoria is None:
        raise ValueError(f"'{codigo}' no tiene categoria base valida (I16)")
    return codigo, categoria
