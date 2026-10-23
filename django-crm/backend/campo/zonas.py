# -*- coding: utf-8 -*-
"""
================================================================================
 ZONAS OPERATIVAS  --  las que Rapilink usa para repartir, no las del proveedor
================================================================================

POR QUE UN CATALOGO PROPIO Y NO EL CAMPO DEL PROVEEDOR
------------------------------------------------------
"Zona" significa tres cosas distintas en este sistema, y dos no sirven para
repartir trabajo:

  zona (WispHub)        zona de CORTE DE FACTURACION. Medido el 10/09/2026:
                        {'id': 20049, 'nombre': 'CORTE 30 - SERVIDOR 1'}.
                        Agrupar por esto repartiria por dia de cobro.
  zone_name (SmartOLT)  la zona de la OLT. Es topologia de red: dos casas de
                        la misma cuadra pueden colgar de OLT distintas.
  localidad (WispHub)   el barrio ('MARTHA GISELA'). Es lo geografico real,
                        pero son decenas y nadie reparte cuadrillas por barrio.

Una zona operativa es como la empresa divide su territorio --Norte, Sur,
Soledad-- y es una decision suya, no un dato del proveedor. Por eso se declara
acá y los barrios se mapean a ella.

POR QUE EL MAPEO ES UNA TABLA Y NO UN CAMPO
-------------------------------------------
Un barrio pertenece a una zona, pero el nombre del barrio llega como texto del
proveedor y viene escrito de varias formas. Guardar "las localidades de la zona
Norte" como una lista dentro de la zona obligaria a editarla entera para
agregar un barrio, y no dejaria lugar donde anotar las variantes. Con una fila
por alias, agregar 'MARTA GISELA' --sin h, como a veces llega-- es una fila
mas y no toca nada de lo que ya funciona.
"""

from __future__ import annotations

from django.db import models

from common.base import BaseModel
from common.models import Org


class ZonaOperativa(BaseModel):
    """Como la empresa divide su territorio para repartir trabajo."""

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="zonas_operativas"
    )
    nombre = models.CharField(max_length=120)

    #: Una zona NO se borra: se da de baja. Las jornadas viejas la referencian
    #: y son las que explican por que una cuadrilla fue a donde fue.
    activa = models.BooleanField(default=True)
    notas = models.TextField(blank=True, default="")

    class Meta:
        db_table = "campo_zona_operativa"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "nombre"], name="unique_zona_nombre_por_org"
            )
        ]

    def __str__(self) -> str:
        return self.nombre


class AliasDeZona(BaseModel):
    """Un nombre de barrio que cae en esta zona.

    SE GUARDA NORMALIZADO --mayusculas y sin espacios de sobra-- porque el
    texto llega del proveedor y la misma localidad viene escrita de varias
    formas. Comparar sin normalizar haria que 'martha gisela' y 'MARTHA GISELA'
    fueran dos barrios distintos, y uno de los dos quedaria sin zona.

    UN ALIAS PERTENECE A UNA SOLA ZONA. Si el mismo barrio estuviera en dos,
    una orden de ahi podria ir a cualquiera de las dos cuadrillas y el reparto
    dejaria de ser reproducible.
    """

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="alias_de_zona"
    )
    zona = models.ForeignKey(
        ZonaOperativa, on_delete=models.CASCADE, related_name="alias"
    )
    #: El texto tal como llega en la orden, normalizado.
    localidad = models.CharField(max_length=128, db_index=True)

    class Meta:
        db_table = "campo_alias_de_zona"
        ordering = ["localidad"]
        constraints = [
            models.UniqueConstraint(
                fields=["org", "localidad"],
                name="unique_localidad_en_una_sola_zona",
            )
        ]

    def save(self, *args, **kwargs):
        self.localidad = normalizar_localidad(self.localidad)
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.localidad} → {self.zona.nombre}"


def normalizar_localidad(texto: str) -> str:
    """Mayusculas y sin espacios de sobra, que es como se compara.

    No se quitan tildes a proposito: 'BOGOTÁ' y 'BOGOTA' son dos textos que un
    operador puede querer mapear a zonas distintas, y decidirlo por el
    sistema esconderia el caso en vez de resolverlo. Si hacen falta las dos
    formas, son dos alias.
    """
    return " ".join((texto or "").upper().split())


def zona_de(org, localidad: str):
    """La zona operativa de un barrio, o `None` si nadie la mapeo.

    `None` NO es un error ni un dato faltante: es una localidad que todavia
    no se asigno a ninguna zona, y la pantalla tiene que poder decirlo. Una
    orden sin zona no se puede repartir por zona, y callarlo la dejaria
    invisible en vez de pendiente.
    """
    texto = normalizar_localidad(localidad)
    if not texto:
        return None
    alias = (
        AliasDeZona.objects
        .filter(org=org, localidad=texto, zona__activa=True)
        .select_related("zona")
        .first()
    )
    return alias.zona if alias else None


#: Que tan parecido tiene que ser un barrio para SUGERIRLO. 0.85 deja pasar una
#: letra cambiada, faltante o de mas en nombres de barrio tipicos («CACARMOA»
#: contra «CACARAMOA») y no junta barrios distintos de nombre corto.
PARECIDO_MINIMO = 0.85


def parecidas(org, texto: str, n: int = 3) -> list[dict]:
    """Barrios YA MAPEADOS que se parecen a `texto`, para SUGERIR. Nunca corrige.

    13/10/2026: un barrio escrito con una letra de mas o de menos no coincide
    con ningun alias y la orden queda en `sin_zona`. Corregirlo solo seria
    peor: dos barrios reales pueden diferir en una letra («SAN JOSE» y «SAN
    JOSUE») y la orden se iria callada a la cuadrilla equivocada -- que es
    peor que `sin_zona`, donde al menos se ve. Esto devuelve candidatos; decide
    una persona.

    Si `texto` YA esta mapeado no hay nada que sugerir: devuelve [].
    Las tildes NO se igualan, por la misma razon que `normalizar_localidad`.
    """
    import difflib

    buscado = normalizar_localidad(texto)
    if not buscado:
        return []
    mapeados = {
        a.localidad: a.zona
        for a in AliasDeZona.objects.filter(org=org, zona__activa=True)
        .select_related("zona")
    }
    if buscado in mapeados:
        return []
    cercanos = difflib.get_close_matches(buscado, list(mapeados), n=n,
                                         cutoff=PARECIDO_MINIMO)
    return [{"localidad": c, "zona_id": str(mapeados[c].id),
             "zona": mapeados[c].nombre} for c in cercanos]
