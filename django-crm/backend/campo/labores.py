# -*- coding: utf-8 -*-
"""
================================================================================
 LAS LABORES DE CADA EMPRESA  --  20/10/2026
================================================================================

Pedido del usuario: «que se pueda crear labor y al momento de crearla uno le
asigna los asuntos que cubre esa labor». Ficha y decisiones:
SPEC/objetivos/labores-propias-por-empresa.md (D1-D8).

QUE ES UNA LABOR
----------------
Lo que una cuadrilla sale a hacer un dia (cada cuadrilla, UNA por dia), y por
lo tanto que trabajo le llega. Hasta hoy eran tres fijas en el codigo
--instalacion, correctivo, trabajos-- repetidas en cuatro tuplas. Desde aca son
filas por empresa: las tres de siempre se SIEMBRAN con el mismo codigo, asi que
nada de lo guardado (WorkType.labor, JornadaDeCuadrilla.labor,
Cuadrilla.labor_habitual, labor_por_grupo) cambia de valor ni se migra.

EL CODIGO NO CAMBIA NUNCA despues de creada: queda escrito en el historial de
jornadas. El NOMBRE si (es lo que se ve).

LAS DE FABRICA (D5) se renombran y llevan asuntos, pero no se dan de baja: el
clasificador medido del Supervisor y la tabla de fabrica emiten sus codigos.

LOS ASUNTOS (D2, D6): la labor manda. Un asunto de WispHub va en UNA sola labor
de la empresa --lo garantiza la base, no un bucle-- y se compara normalizado
con `campo.plantillas.normalizar_asunto`, el mismo de las plantillas.

FASE 1: esto existe y se lee, pero la conducta no cambia: las tres de siempre,
con los mismos codigos y los nombres que la empresa ya les habia puesto.
================================================================================
"""

from __future__ import annotations

from django.db import DatabaseError, IntegrityError, models, transaction

from common.base import BaseModel
from common.models import Org

#: Las tres de siempre. Su codigo es el que ya esta guardado en todas partes;
#: el nombre es el de fabrica, que cada empresa puede cambiar.
LABORES_DE_FABRICA = (
    ("instalacion", "Instalacion"),
    ("correctivo", "Correctivo"),
    ("trabajos", "Trabajos"),
)
NOMBRE_DE_FABRICA = dict(LABORES_DE_FABRICA)
#: El orden en que se muestran: las de fabrica primero, en este orden.
_ORDEN_DE_FABRICA = {c: i for i, (c, _) in enumerate(LABORES_DE_FABRICA)}

#: Largo maximo del codigo: entra en las columnas que ya lo guardan
#: (`max_length=20` en WorkType, JornadaDeCuadrilla y Cuadrilla).
MAX_CODIGO = 20
#: Largo maximo del nombre (el mismo que ya validaba `nombres_de_labor`).
MAX_NOMBRE = 40


class Labor(BaseModel):
    """Una labor de la empresa."""

    org = models.ForeignKey(Org, on_delete=models.CASCADE, related_name="labores")
    codigo = models.CharField(max_length=MAX_CODIGO)
    nombre = models.CharField(max_length=MAX_NOMBRE)
    activa = models.BooleanField(default=True)
    #: Una de las tres sembradas (D5): se renombra, no se da de baja.
    de_fabrica = models.BooleanField(default=False)
    #: El kit que lleva una cuadrilla que sale con esta labor (28/10/2026,
    #: SPEC/objetivos/material-del-dia.md). Vacio = esta labor no carga.
    plantilla_de_kit = models.ForeignKey(
        "campo.PlantillaDeKit",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="labores",
    )

    class Meta:
        db_table = "campo_labor"
        ordering = ["nombre"]
        constraints = [
            models.UniqueConstraint(fields=["org", "codigo"],
                                    name="unique_labor_codigo_por_org"),
        ]

    def __str__(self) -> str:
        return f"{self.nombre} ({self.codigo})"


class AsuntoDeLabor(BaseModel):
    """Un asunto de ticket del proveedor que cubre esta labor.

    UN ASUNTO PERTENECE A UNA SOLA LABOR DE LA EMPRESA: si estuviera en dos,
    el mismo ticket podria ir a dos cuadrillas distintas y el reparto dejaria
    de ser reproducible. Lo garantiza la base (`unique(org, normalizado)`),
    no un bucle en Python que dos guardados a la vez podrian saltear.
    """

    org = models.ForeignKey(Org, on_delete=models.CASCADE,
                            related_name="asuntos_de_labor")
    labor = models.ForeignKey(Labor, on_delete=models.CASCADE,
                              related_name="asuntos")
    #: Como lo escribio la persona, para mostrarlo.
    asunto = models.CharField(max_length=255)
    #: Como se compara. Lo calcula `save()`.
    normalizado = models.CharField(max_length=255, db_index=True)

    class Meta:
        db_table = "campo_asunto_de_labor"
        ordering = ["asunto"]
        constraints = [
            models.UniqueConstraint(fields=["org", "normalizado"],
                                    name="unique_asunto_en_una_sola_labor"),
        ]

    def save(self, *args, **kwargs):
        from campo.plantillas import normalizar_asunto
        self.normalizado = normalizar_asunto(self.asunto)
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.asunto} → {self.labor.codigo}"


# =============================================================================
#  LO QUE LEE EL RESTO DEL SISTEMA
# =============================================================================

def _orden(codigo: str, nombre: str):
    return (_ORDEN_DE_FABRICA.get(codigo, len(_ORDEN_DE_FABRICA)), nombre.lower())


def _nombres_viejos(org) -> dict:
    """Los nombres que la empresa puso el 20/10 en «Nombre de cada labor»,
    antes de que existiera esta tabla. Solo se leen mientras la empresa no
    tiene filas: la siembra los copia y desde ahi manda `Labor.nombre`."""
    from campo.cuadrillas import ConfiguracionDeReparto
    propios = (ConfiguracionDeReparto.objects.filter(org=org)
               .values_list("nombres_de_labor", flat=True).first())
    return propios if isinstance(propios, dict) else {}


def _filas(org):
    """(codigo, nombre, activa) de la empresa, o None si la tabla no existe.

    LA TABLA PUEDE NO EXISTIR TODAVIA (auditor independiente, 20/10/2026): en
    produccion el worker de Celery no espera al backend, y puede correr este
    codigo antes de que `migrate` cree `campo_labor`. Sin esto, el armado de
    la madrugada reventaria con ProgrammingError mientras tanto -- y para
    siempre si `migrate` fallara. Se trata igual que "sin filas": las de
    fabrica. El savepoint deja la transaccion de quien llama usable.
    """
    try:
        with transaction.atomic():
            return list(Labor.objects.filter(org=org)
                        .values_list("codigo", "nombre", "activa"))
    except DatabaseError:
        return None


def labores_de(org, *, incluir_inactivas: bool = False) -> list[dict]:
    """Las labores de esta empresa: [{"id": codigo, "texto": nombre}].

    UNA sola lista para todas las pantallas (Plantillas, Despacho, Cuadrillas):
    si cada una armara la suya, un nombre cambiaria en una y no en las otras.

    SIN FILAS --una empresa creada despues de la siembra, o una base donde la
    siembra no llego-- devuelve las de fabrica, con los nombres viejos si los
    tenia, SIN ESCRIBIR: leer no tiene por que crear nada, y una lista vacia
    haria que toda validacion rechazara y que el ciclo de la madrugada fallara.
    """
    filas = _filas(org)
    if not filas:
        viejos = _nombres_viejos(org)
        return [{"id": c, "texto": str(viejos.get(c) or "").strip() or n}
                for c, n in LABORES_DE_FABRICA]
    return [{"id": c, "texto": n}
            for c, n, activa in sorted(filas, key=lambda f: _orden(f[0], f[1]))
            if activa or incluir_inactivas]


def labor_valida(org, codigo) -> bool:
    """Si `codigo` es una labor ACTIVA de esta empresa.

    La UNICA validacion de labores del sistema: las siete que habia (cinco en
    cuadrillas_views, una en plantillas, una en `labor_de_cada_grupo`) leian
    las tuplas fijas, y una labor creada por la empresa no habria pasado por
    ninguna. Vacio no es una labor: quien acepta «sin labor» lo dice aparte.

    COMPARA EXACTO, sin limpiar espacios: quien llama guarda el valor tal como
    lo paso, y ' correctivo ' validado como 'correctivo' quedaria guardado con
    los espacios y el reparto no lo emparejaria (auditor independiente,
    20/10/2026; origin lo rechazaba, y lo sigue rechazando).
    """
    codigo = codigo if isinstance(codigo, str) else str(codigo or "")
    if not codigo.strip():
        return False
    filas = _filas(org)
    if not filas:
        return codigo in NOMBRE_DE_FABRICA
    return any(c == codigo and activa for c, _, activa in filas)


def nombres_de_labor(org) -> dict:
    """codigo -> nombre, de TODAS (tambien las dadas de baja): una jornada
    vieja tiene que poder seguir mostrando el nombre de su labor."""
    return {l["id"]: l["texto"] for l in labores_de(org, incluir_inactivas=True)}


def sembrar_de_fabrica(org) -> None:
    """Que esta empresa tenga las tres de siempre.

    Toma los nombres que la empresa ya les habia puesto. Idempotente: la que ya
    existe no se toca. La usa quien va a ESCRIBIR una labor; leer no siembra
    (ver `labores_de`).
    """
    #  Una por una con get_or_create, y no "si no hay ninguna, crear las tres":
    #  sobre cero filas un select_for_update no bloquea nada, y dos siembras a
    #  la vez chocarian contra `unique(org, codigo)`. Asi la segunda encuentra
    #  la fila y sigue.
    viejos = _nombres_viejos(org)
    for codigo, nombre in LABORES_DE_FABRICA:
        try:
            with transaction.atomic():
                Labor.objects.get_or_create(
                    org=org, codigo=codigo,
                    defaults={"de_fabrica": True,
                              "nombre": (str(viejos.get(codigo) or "").strip()
                                         or nombre)[:MAX_NOMBRE]})
        except IntegrityError:
            #  Otra siembra la creo entre el get y el create: ya esta.
            pass


def renombrar_de_fabrica(org, codigo: str, nombre: str) -> None:
    """Le cambia el nombre a una de las tres de fabrica. Vacio = el de fabrica.

    Es lo que hacia «Nombre de cada labor» (20/10) sobre la columna
    `nombres_de_labor`; desde la Fase 1 escribe `Labor.nombre`, que es la
    unica fuente del nombre. La columna vieja queda sin escribir hasta que la
    Fase 4 la borre.
    """
    sembrar_de_fabrica(org)
    nombre = " ".join(str(nombre or "").split()) or NOMBRE_DE_FABRICA[codigo]
    Labor.objects.filter(org=org, codigo=codigo).update(nombre=nombre[:MAX_NOMBRE])
