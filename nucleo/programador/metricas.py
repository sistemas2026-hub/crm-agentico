# -*- coding: utf-8 -*-
"""
================================================================================
 METRICAS  --  y la etiqueta que no se puede poner
================================================================================

Por que existe
--------------
Una metrica con etiqueta 'organization_id' es un dato de cliente. No se siente
como tal cuando se escribe --es "solo un UUID en un contador"-- pero termina en
un dashboard compartido, en un sistema de alertas y en la retencion de un
proveedor de observabilidad, todos fuera del perimetro que alguien reviso.

Y con cardinalidad por tenant tampoco escala: cada empresa nueva multiplica las
series por el numero de jobs y estados.

Asi que la guarda es de codigo y es fail-closed: 'contar' RECHAZA cualquier
etiqueta que identifique a una empresa. No avisa, no la borra en silencio --
levanta ValueError, que es lo que hace que se corrija al escribirla y no seis
meses despues.

Que si se puede etiquetar: 'job_code', 'motivo', 'outcome', 'resultado'. Son de
cardinalidad acotada por el catalogo y no dicen de quien es la fila.

Que no es esto
--------------
No es un cliente de Prometheus ni pretende serlo. Es un registro en memoria que
el coordinador vuelca al log al cerrar cada tick. Cuando haya un exportador de
verdad, esta guarda es la que tiene que sobrevivir; el almacenamiento es lo de
menos.
================================================================================
"""

from __future__ import annotations

import re
from collections import Counter

# Cualquier etiqueta cuyo NOMBRE contenga alguno de estos. Se mira el nombre,
# no el valor: un UUID de empresa escondido en una etiqueta llamada 'x' no lo
# atrapa esto -- para eso esta la lista blanca de abajo, que es la que manda.
_PROHIBIDAS = ("organization", "org", "tenant", "empresa", "company",
               "cliente", "customer", "slug", "account")

# Lista blanca. Fail-closed: lo que no este aca, no entra.
PERMITIDAS = frozenset({"job_code", "motivo", "outcome", "resultado", "etapa"})

_VALOR = re.compile(r"^[a-z0-9_]{1,40}$")

# Un UUID como VALOR de etiqueta es casi siempre un identificador de fila o de
# empresa disfrazado. Se rechaza tambien.
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
                   r"[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


class Registro:
    """Contadores en memoria, con la guarda de etiquetas puesta."""

    def __init__(self):
        self._c: Counter[tuple] = Counter()

    def contar(self, nombre: str, valor: int = 1, **etiquetas: str) -> None:
        for k, v in etiquetas.items():
            _validar(k, v)
        clave = (nombre,) + tuple(sorted(etiquetas.items()))
        self._c[clave] += valor

    def leer(self) -> dict:
        salida = {}
        for clave, n in sorted(self._c.items(), key=lambda p: str(p[0])):
            nombre, etiquetas = clave[0], dict(clave[1:])
            etq = ",".join(f"{k}={v}" for k, v in sorted(etiquetas.items()))
            salida[f"{nombre}{{{etq}}}" if etq else nombre] = n
        return salida

    def __str__(self) -> str:
        return " ".join(f"{k}={v}" for k, v in self.leer().items())


def _validar(nombre: str, valor) -> None:
    n = str(nombre).lower()
    if n not in PERMITIDAS:
        motivo = ("identifica a una empresa"
                  if any(p in n for p in _PROHIBIDAS)
                  else "no esta en la lista blanca")
        raise ValueError(
            f"etiqueta '{nombre}' rechazada: {motivo}. "
            f"Permitidas: {sorted(PERMITIDAS)}. "
            f"Una metrica etiquetada por empresa es un dato de cliente en un "
            f"dashboard, y ademas multiplica las series por cada tenant nuevo.")
    v = str(valor)
    if _UUID.match(v):
        raise ValueError(
            f"la etiqueta '{nombre}' trae un UUID ('{v[:8]}...'): un "
            f"identificador de fila o de empresa disfrazado de dimension.")
    if not _VALOR.match(v):
        raise ValueError(
            f"valor de etiqueta invalido para '{nombre}': '{v}'. "
            f"Se admiten hasta 40 caracteres de [a-z0-9_].")
