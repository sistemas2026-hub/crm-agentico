# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDIA DE SALIDA -- lo que el modelo redacta, antes de que el cliente lo vea
================================================================================

Tercera capa de RNF-02 (seguridad en dos capas, PRD.md). Las dos existentes
protegen la ENTRADA de datos al modelo -- que campos ve (listas blancas en
nucleo/seguridad/listas_blancas.py) y que hace con una accion sensible
(confirmacion humana). Ninguna de las dos mira la SALIDA: el texto en
espanol que el modelo redacta para el cliente pasaba directo, sin chequeo.

Por que hace falta, no es hipotetico: los casos dorados YA declaran
'responde_sin' (evaluacion/*.casos.yaml) para atrapar exactamente este tipo
de fuga -- un codigo de error interno repetido tal cual, una fabricacion
sobre 'como se sabe' la identidad del cliente. Pero esa guarda solo corre en
evaluacion. En produccion, si el modelo comete el mismo desliz manana, nada
lo detiene antes de llegar al cliente.

Patron con precedente en la industria (investigado agosto 2026): Decagon lo
describe como una "capa de supervisor que atrapa errores antes de que el
cliente los vea" -- mismo concepto, misma filosofia de RNF-02.

Deliberadamente NO se reusa 'Rol.nunca_revelar' para este chequeo: esa lista
son NOMBRES DE CAMPO para filtrar datos crudos de API (ver
listas_blancas.py), no frases prohibidas en lenguaje natural. Confirmado
contra tenants/rapilink.config.yaml antes de escribir esto: 'cliente_final'
tiene 'cedula' y 'direccion' en nunca_revelar, y el agente dice "pasame tu
cedula" en cada verificacion -- buscar esa palabra en el texto libre habria
bloqueado el flujo normal de identificacion. Los patrones de aca son solo
codigos internos del motor: tokens que nunca aparecen en espanol legitimo.
================================================================================
"""

from __future__ import annotations

import unicodedata

# Codigos y marcadores internos de nucleo/modelo/motor.py -- universales
# (nunca dependen de un tenant), y el modelo a veces los repite tal cual si
# los ve en el resultado de una herramienta fallida ('salida = {"error": ...,
# "codigo_error": "..."}'). Ninguno de estos strings puede aparecer en una
# respuesta legitima en espanol: si aparece, es una fuga de plomeria interna.
PATRONES_INTERNOS = [
    "IDENTIDAD_NO_VERIFICADA",
    "PRECONDICION_NO_CUMPLIDA",
    "HERRAMIENTA_DESCONOCIDA",
    "instruccion_interna",
]

# Generico a proposito, no es texto de marca de ningun tenant -- es plomeria
# tecnica (como un mensaje de error), no copy de negocio. Si esto se ve en
# produccion con frecuencia, el log de '[salida]' lo va a mostrar: ahi se
# evalua si conviene hacerlo configurable por tenant, no antes.
MENSAJE_FUGA = (
    "Dame un segundo, quiero confirmar ese dato antes de seguir. "
    "¿Me repetis tu consulta?"
)


def _normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFKD", (texto or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def verificar(texto: str) -> tuple[str, str | None]:
    """
    (texto_a_enviar, patron_detectado). Si detecta una fuga, el texto
    original NO se devuelve -- fail-closed, mismo criterio que el filtro de
    campos: ante la duda, se bloquea en vez de dejar pasar.
    """
    normalizado = _normalizar(texto)
    for patron in PATRONES_INTERNOS:
        if _normalizar(patron) in normalizado:
            return MENSAJE_FUGA, patron
    return texto, None
