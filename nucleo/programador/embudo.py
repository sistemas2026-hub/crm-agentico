# -*- coding: utf-8 -*-
"""
================================================================================
 EL EMBUDO  --  todo lo que entro tiene que estar en algun lado
================================================================================

Por que existe
--------------
Un barrido que informa "reclamados: 3" no dice nada. La pregunta operativa no
es cuantos se hicieron: es por que NO se hicieron los otros. Y esa pregunta,
en el reloj viejo, no tenia respuesta -- se veia "ciclo fin, 1 tenant" y nada
mas, asi que cuatro horas sin ningun barrido eran indistinguibles de cuatro
horas en las que no habia nada que barrer.

Un embudo obliga a cerrar la cuenta:

    recibidos = (suma de omitidos, por motivo) + alcanzados

Si esa identidad no se cumple, hay unidades que entraron al barrido y no
figuran en ninguna salida. Eso NO es un detalle de logueo: es que el
coordinador perdio candidatos sin saberlo, que es exactamente la forma que
tiene este tipo de bug de no verse.

Por que no lanza excepcion cuando no cuadra
-------------------------------------------
Porque el barrido no puede morirse por un error de contabilidad. La leccion
del reloj viejo es que una excepcion que mata el bucle deja de hacer TODO,
para siempre, y nadie se entera. El descuadre se informa, se cuenta y se
grita en el log; el trabajo sigue.
================================================================================
"""

from __future__ import annotations

from collections import Counter


class Embudo:
    """
    La contabilidad de una etapa del barrido.

    Cada unidad entra una vez con 'recibir' y sale UNA sola vez: o por
    'omitir(motivo)' o por 'alcanzar'. No hay una tercera salida y no hay
    salida doble -- si aparece, la identidad deja de cerrar y eso es el punto.
    """

    def __init__(self, etapa: str):
        self.etapa = etapa
        self.recibidos = 0
        self.alcanzados = 0
        self.omitidos: Counter[str] = Counter()

    def recibir(self, n: int = 1) -> None:
        if n < 0:
            raise ValueError("recibir no acepta negativos")
        self.recibidos += n

    def omitir(self, motivo: str, n: int = 1) -> None:
        """
        Una unidad que entro y no se va a trabajar, con el motivo.

        El motivo es obligatorio y es una etiqueta corta y CERRADA (ver
        MOTIVOS): un motivo libre termina siendo un mensaje distinto por
        situacion y la agregacion deja de servir.
        """
        if not motivo:
            raise ValueError("una omision sin motivo no es una omision")
        self.omitidos[motivo] += n

    def alcanzar(self, n: int = 1) -> None:
        self.alcanzados += n

    # -- lectura --------------------------------------------------------------

    @property
    def salidas(self) -> int:
        return self.alcanzados + sum(self.omitidos.values())

    @property
    def descuadre(self) -> int:
        """Positivo: entraron mas de los que salieron. Negativo: al reves."""
        return self.recibidos - self.salidas

    @property
    def cuadra(self) -> bool:
        return self.descuadre == 0

    def informe(self) -> dict:
        return {
            "etapa": self.etapa,
            "recibidos": self.recibidos,
            "alcanzados": self.alcanzados,
            "omitidos": dict(sorted(self.omitidos.items())),
            "cuadra": self.cuadra,
            "descuadre": self.descuadre,
        }

    def __str__(self) -> str:
        detalle = " ".join(f"{m}={n}" for m, n in sorted(self.omitidos.items()))
        cola = "" if self.cuadra else f"  [DESCUADRE {self.descuadre:+d}]"
        return (f"{self.etapa}: recibidos={self.recibidos} "
                f"alcanzados={self.alcanzados}"
                + (f" omitidos[{detalle}]" if detalle else "")
                + cola)


# Los motivos por los que un candidato no se trabaja. Cerrados a proposito:
# el embudo sirve para agregar, y una etiqueta libre por situacion no agrega.
MOTIVOS = (
    "otro_coordinador",     # la fila estaba tomada, o la carrera se perdio
    "lease_vivo",           # alguien lo esta ejecutando ahora mismo
    "lectura_vieja",        # el slot que traia el candidato ya no es el vigente
    "backoff",              # esta esperando su reintento
    "job_deshabilitado",    # el catalogo lo tiene apagado
    "sin_config",           # la organizacion no tiene config congelable
    "presupuesto",          # se acabo el tiempo del tick
    "tope_de_tick",         # se alcanzo max_claims_por_tick
    "error",                # el claim fallo por algo no previsto
)
