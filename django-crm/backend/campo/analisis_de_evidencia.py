# -*- coding: utf-8 -*-
"""
================================================================================
 LO QUE LA IA VIO EN UNA FOTO DE EVIDENCIA  --  31/10/2026
================================================================================

Una fila por intento de analisis sobre una evidencia. La lectura y la decision
viven en `campo/inspeccion_visual.py`; esto es solo donde se guarda.

POR QUE UNA TABLA Y NO UNA COLUMNA EN EvidenciaTrabajo
-------------------------------------------------------
Tres motivos, y el tercero es el que decide:

1. `EvidenciaTrabajo.metadatos_captura` esta declarado como metadatos
   TECNICOS del dispositivo (GPS, precision, modelo). Meter ahi el analisis
   sobrecarga un campo documentado para otra cosa.

2. Un analisis cuesta dinero y latencia, y volver a correrlo da OTRO texto.
   No es recalculable, asi que no puede vivir como un derivado --que es
   justamente por que `revision_del_cierre.py:38-41` eligio NO persistir su
   veredicto: ese si se recalcula--.

3. **La correccion de una persona tiene que ser una FILA NUEVA, nunca un
   UPDATE.** Sin el par (lo que dijo la IA, lo que dijo la persona) no hay
   con que medir si acierta, y medir eso es el unico motivo por el que la
   etapa 1 existe. Un UPDATE borraria exactamente el dato que se vino a
   buscar.

LO QUE ESTA TABLA NO ES, TODAVIA
---------------------------------
No es un dataset de entrenamiento, y la diferencia no es de palabras.
Acumular el analisis como registro OPERATIVO --que paso con esta orden-- es
legitimo hoy con la autorizacion vigente. Declararlo dataset para entrenar un
modelo es una FINALIDAD NUEVA sobre fotos de la casa de un cliente, y
CLAUDE.md §5 es textual: cualquier tercero nuevo exige resolver eso antes de
activarse. Cuando esa decision se tome, se escribe aca.

POR QUE GUARDA EL TEXTO Y NO UNA ESTRUCTURA
--------------------------------------------
Porque el proveedor no puede devolver JSON estructurado: medido contra la API
real el 02/10/2026 (`nucleo/canales/vision.py:22-33`), `json_schema` devuelve
HTTP 400 y `json_object` triplico la latencia para devolver listas vacias.
Extraer estructura del texto libre es la etapa 2, y se decide con el numero
que esta etapa produce.

EL CAMPO QUE DECIDE: `pide_atencion`
-------------------------------------
Lo escribe el codigo, no el modelo. Es la unica senal que llega a la revision
del cierre, y aun asi NO PUEDE bloquear nada: el punto que arma
`inspeccion_visual.punto_de_la_revision` vale `True` o `None`, nunca `False`.
Ver el encabezado de ese modulo.
================================================================================
"""
from __future__ import annotations

from django.db import models

from common.base import BaseModel


class AnalisisDeEvidencia(BaseModel):
    """Un intento de mirar una foto de evidencia. Append-only."""

    #: Lo dijo el analizador.
    IA = "ia"
    #: Lo corrigio una persona. Fila NUEVA, nunca un UPDATE de la de la IA.
    PERSONA = "persona"
    ORIGENES = ((IA, "Análisis automático"), (PERSONA, "Corrección de una persona"))

    org = models.ForeignKey("common.Org", on_delete=models.CASCADE,
                            related_name="analisis_de_evidencia")
    evidencia = models.ForeignKey("campo.EvidenciaTrabajo",
                                  on_delete=models.CASCADE,
                                  related_name="analisis")
    #: LA VUELTA SE COPIA, no se deduce de la orden al leer. Una orden
    #: devuelta al tecnico y rehecha tiene otras fotos, y el analisis de la
    #: vuelta anterior no dice nada de esta. Mismo criterio que
    #: `EvidenciaTrabajo.vuelta`: lo pone el servidor.
    vuelta = models.PositiveIntegerField(default=1)

    origen = models.CharField(max_length=16, choices=ORIGENES, default=IA)

    #: Lo que se vio. Vacio = no se pudo mirar, y entonces `motivo` dice por que.
    texto = models.TextField(blank=True, default="")
    #: Por que no se pudo. Texto del sistema, nunca del proveedor.
    motivo = models.CharField(max_length=300, blank=True, default="")

    #: Si esto necesita que una persona lo mire. Lo escribe el CODIGO.
    pide_atencion = models.BooleanField(default=False)

    #: Para poder decir despues con que se saco cada cosa. Sin esto, comparar
    #: dos meses de analisis es comparar cosas distintas sin saberlo.
    modelo = models.CharField(max_length=120, blank=True, default="")
    segundos = models.FloatField(default=0.0)
    tokens = models.PositiveIntegerField(default=0)

    #: Quien corrigio, cuando `origen = persona`.
    profile = models.ForeignKey("common.Profile", null=True, blank=True,
                                on_delete=models.SET_NULL,
                                related_name="correcciones_de_analisis")

    class Meta:
        db_table = "campo_analisis_de_evidencia"
        ordering = ["created_at"]
        indexes = [
            #  La consulta que hace la revision del cierre: todos los
            #  analisis de las fotos de una orden, en una vuelta.
            models.Index(fields=["org", "vuelta"],
                         name="idx_analisis_org_vuelta"),
        ]

    def __str__(self) -> str:
        return f"Análisis {self.origen} de {self.evidencia_id}"
