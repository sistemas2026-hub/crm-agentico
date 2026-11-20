# -*- coding: utf-8 -*-
"""
================================================================================
 DONDE ES UNA OBRA DE RED  --  25/10/2026
================================================================================

Pedido del usuario: que el Supervisor identifique solo de que zona es cada
ticket, «sin que uno tenga que estar mostrando». La simulacion del dia mostro
el caso que lo motivo: «Intervencio Santa Sofia Niveles Altos» se le daba a una
cuadrilla de Soledad, y Santa Sofia es de Sabanagrande. Una obra de red se abre
con la cuenta de la oficina, asi que el «barrio del cliente» es OFICINA o
ATLANTICO: el de la oficina, no el del trabajo.

LA REGLA (la segunda version: la auditoria del 25/10 midio que la primera
mandaba clientes y cortes de red a la zona equivocada)
---------------------------------------------------------------------------
    una OBRA DE RED (la lectura del Supervisor la puso en `obra_de_red`, y no
    es el ticket de un cliente dentro de un corte de red):
        el barrio cargado que NOMBRA el ticket, sin contar el de la cuenta
        con que se abrio (la oficina). Si no nombra ninguno, o nombra barrios
        de dos zonas, NO SE SABE DONDE ES: la ubica una persona. Antes caia a
        la zona de la oficina, sin ninguna señal.
    TODO LO DEMAS (un cliente en su casa, tambien el de un corte de red):
        el barrio del cliente, como siempre. El texto de un cliente no se
        lee: «se acerco a la oficina» o «desde el 20 de julio» lo mandaban a
        otra zona (auditoria, medido).

«Un barrio cargado» es uno que la empresa YA cargo en Zonas operativas: no se
inventa ninguno ni se adivina por parecido. Codigo y no el modelo (CLAUDE.md
§4): comparar un nombre contra una lista es calcular, no componer.

Para buscar, el texto y el barrio se comparan sin tildes ni signos («Viña» y
«VINA», «Santa Sofía,» y «SANTA SOFIA»); lo que se devuelve es el barrio tal
como esta cargado, que es lo que el reparto mapea a una zona.
"""

from __future__ import annotations

import re
import unicodedata

_NO_ALFANUMERICO = re.compile(r"[^0-9A-Z]+")

DEL_CLIENTE = "cliente"
DEL_TICKET = "ticket"


def _comparable(texto: str) -> str:
    """Mayusculas, sin tildes y con un espacio entre palabras, con un espacio
    a cada lado: asi «SANTA SOFIA» no se encuentra dentro de «SANTA SOFIAS»."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFKD", (texto or "").upper())
        if not unicodedata.combining(c))
    return " " + " ".join(_NO_ALFANUMERICO.sub(" ", sin_tildes).split()) + " "


def preparar(zona_de_barrio: dict) -> list:
    """De {barrio cargado: zona} a la lista con que se busca en un texto, del
    nombre mas largo al mas corto («VILLA MARIA» antes que «MARIA»). Se arma
    una vez por vuelta, no una por caso."""
    lista = [(_comparable(b), b, z) for b, z in zona_de_barrio.items()
             if _comparable(b).strip()]
    return sorted(lista, key=lambda x: -len(x[0]))


def barrio_en_el_texto(texto: str, buscables: list, *, sin=()) -> str:
    """El barrio cargado que nombra el texto, o "" si no nombra ninguno o
    nombra barrios de dos zonas distintas. `sin`: barrios que no cuentan (el
    de la cuenta con que se abrio una obra: la oficina)."""
    if not buscables:
        return ""
    t = _comparable(texto)
    encontrados = []
    for patron, b, z in buscables:           # del mas largo al mas corto
        if patron in t:
            if b not in sin:
                encontrados.append((b, z))
            #  Lo encontrado se CONSUME, con un separador que no es letra:
            #  «VILLA MARIA» no deja una «MARIA» suelta que haga parecer
            #  ambiguo el texto, y sacar «SANTA SOFIA» de «DE LA SANTA SOFIA
            #  PAZ» no inventa un «LA PAZ» (auditoria, 25/10/2026).
            t = t.replace(patron, " | ")
    if not encontrados:
        return ""
    if len({z for _b, z in encontrados}) > 1:
        return ""
    return encontrados[0][0]


def barrio_del_caso(barrio_del_cliente: str, texto: str, *, es_obra: bool,
                    buscables: list) -> tuple[str, str]:
    """(barrio, de donde salio) para un caso de Despacho. Ver la regla arriba.

    `barrio_del_cliente` ya normalizado (`normalizar_localidad`); "" si no se
    sabe. De donde: `DEL_CLIENTE`, `DEL_TICKET` o "" si no hay barrio. Una
    obra sin barrio en el ticket devuelve ("", ""): no se sabe donde es.
    """
    if es_obra:
        #  PRIMERO OTRO BARRIO QUE EL DE LA CUENTA: «Intervencion Santa Sofia;
        #  el material se recoge en la oficina» es de Santa Sofia.
        del_ticket = barrio_en_el_texto(texto, buscables,
                                        sin={barrio_del_cliente})
        if del_ticket:
            return del_ticket, DEL_TICKET
        #  Si el ticket nombra SOLO el de la cuenta, lo confirma: «Caja de
        #  SOLEDAD CENTRO» abierta con una cuenta de SOLEDAD CENTRO.
        if barrio_del_cliente and (
                barrio_en_el_texto(texto, buscables) == barrio_del_cliente):
            return barrio_del_cliente, DEL_TICKET
        return "", ""
    return (barrio_del_cliente, DEL_CLIENTE) if barrio_del_cliente else ("", "")


def es_obra_de_red(lectura: dict, *, es_corte: bool) -> bool:
    """Si el caso es una obra de red: la lectura del Supervisor lo puso en
    `obra_de_red` --o en `ni_cliente_ni_red`, que en el informe de Despacho
    del 25/10/2026 eran obras abiertas con la cuenta de la oficina-- y no es
    el ticket de un cliente dentro de un corte (ese es de un cliente en su
    casa, aunque su labor sea la de la obra)."""
    from operaciones import paso_a_despacho as pad

    return (not es_corte
            and str((lectura or {}).get("grupo") or "")
            in (pad.OBRA_DE_RED, pad.NI_CLIENTE_NI_RED))
