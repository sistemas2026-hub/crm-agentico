# -*- coding: utf-8 -*-
"""
================================================================================
 ¿LO QUE EL TECNICO HIZO EXPLICA EL TICKET?  --  LADO DEL CRM, 12/11/2026
================================================================================
El usuario:

    «debe haber relacion entre el asunto, la descripcion del ticket y la
     respuesta del tecnico. No puede haber una respuesta correcta en un
     asunto que ni por ahi iba al caso.»

Aca vive la tabla y la llamada; la decision de QUE significa cada veredicto
vive en `nucleo/canales/cotejo.py` (el motor), y como entra a la revision,
en `campo/revision_del_cierre.py`.

POR QUE SE GUARDA Y NO SE CALCULA AL MIRAR  --  LA RAZON ES UN NUMERO
----------------------------------------------------------------------
Programacion se refresca sola cada **15 segundos** (`+page.svelte:90`), y
cada refresco llama a `revisar()` para CADA orden terminada sin validar. Con
el cotejo dentro de `revisar()`:

    1 orden × 4 refrescos/min × 8 horas = 1.920 llamadas al modelo por dia

por orden, y multiplicado por cada supervisor con la pantalla abierta. Seria
una factura disparada por un camino que nadie mira, que es textualmente lo
que le paso a `vision` y por lo que su endpoint consulta el tope de gasto
(auditoria del arquitecto, 31/10/2026).

Asi que se calcula UNA vez --cuando el tecnico manda su reporte-- y
`revisar()` LEE lo guardado. Es el mismo reparto que las fotos:
`AnalisisDeEvidencia` + `tasks.mirar_las_que_faltan`.

UNA FILA POR INTENTO, NUNCA UN UPDATE
--------------------------------------
Por el mismo motivo que `AnalisisDeEvidencia`: un cotejo cuesta dinero, no es
recalculable --volver a correrlo da otro texto-- y si alguna vez una persona
corrige el veredicto, esa correccion tiene que ser una fila nueva. Sin el par
(lo que dijo la IA, lo que dijo la persona) no hay con que medir si acierta.

LO QUE ESTO NO DECIDE
----------------------
Nada. Guarda `si`, `no` o `no_se_sabe`. Quien lo convierte en un punto de la
revision es `revision_del_cierre`, y ahi vale `True` o `None`, **nunca
`False`** -- la decision del 31/10/2026 (`campo/inspeccion_visual.py:24-36`):
la IA puede pedir atencion, no puede negar el cierre del trabajo de un
tecnico. Un `None` produce `REVISAR`, y una orden en `REVISAR` no cierra
sola.
================================================================================
"""
from __future__ import annotations

import logging
import os

from django.db import models

from common.base import BaseModel

logger = logging.getLogger(__name__)

#: Los mismos tres del motor. No se importan de alla: este proceso no puede
#: importar `nucleo/`, y duplicar tres cadenas es mas barato que un acople
#: entre dos servicios que se despliegan por separado.
CUADRA = "si"
NO_CUADRA = "no"
NO_SE_SABE = "no_se_sabe"

VEREDICTOS = ((CUADRA, "cuadra"), (NO_CUADRA, "no cuadra"),
              (NO_SE_SABE, "no se sabe"))

IA = "ia"
PERSONA = "persona"
ORIGENES = ((IA, "IA"), (PERSONA, "persona"))


class CotejoDelReporte(BaseModel):
    """Si lo que el tecnico reporto explica el ticket. Una fila por intento.

    `vuelta` importa: una orden devuelta y rehecha se coteja DE NUEVO, y el
    cotejo de la vuelta anterior no vale para la nueva -- el tecnico pudo
    escribir otra cosa. Ver `del_cierre_de_esta_vuelta`.
    """

    org = models.ForeignKey("common.Org", on_delete=models.CASCADE,
                            related_name="cotejos_de_reporte")
    orden = models.ForeignKey("campo.OrdenTrabajo", on_delete=models.CASCADE,
                              related_name="cotejos")
    vuelta = models.PositiveIntegerField(default=1)

    origen = models.CharField(max_length=16, choices=ORIGENES, default=IA)
    veredicto = models.CharField(max_length=16, choices=VEREDICTOS,
                                 default=NO_SE_SABE)
    #: Por que. Lo escribe el modelo citando los dos lados, y ya paso por
    #: `redactar()` en el motor antes de volver.
    motivo = models.CharField(max_length=300, blank=True, default="")

    #: Que fallo, POR TIPO. Nunca el mensaje del proveedor: puede traer de
    #: vuelta lo que se le mando.
    error = models.CharField(max_length=80, blank=True, default="")
    segundos = models.FloatField(default=0.0)
    tokens = models.PositiveIntegerField(default=0)

    #: Quien, cuando lo corrige una persona.
    profile = models.ForeignKey("common.Profile", null=True, blank=True,
                                on_delete=models.SET_NULL,
                                related_name="cotejos_corregidos")

    class Meta:
        db_table = "campo_cotejo_del_reporte"
        indexes = [models.Index(fields=["org", "orden", "-created_at"])]

    def __str__(self) -> str:
        return f"cotejo {self.veredicto} de la OT {self.orden_id}"


def del_cierre_de_esta_vuelta(orden):
    """El ultimo cotejo de la vuelta en curso, o None.

    De la VUELTA, no de la orden: una devuelta y rehecha trae otro reporte, y
    el veredicto del anterior diria algo sobre un texto que ya no esta.
    """
    return (CotejoDelReporte.objects
            .filter(org=orden.org, orden=orden,
                    vuelta=getattr(orden, "vuelta", 1))
            .order_by("-created_at").first())


def _motor():
    """La base y las cabeceras, igual que `inspeccion_visual._motor`."""
    base = (os.environ.get("MOTOR_URL") or "http://motor:5000").rstrip("/")
    cabeceras = {}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token
    return base, cabeceras


def _tenant_de(org) -> str:
    #  Mismo origen que `inspeccion_visual`: el slug del tenant sale de
    #  `operaciones`, no se arma aca.
    from operaciones.areas_del_tenant import tenant_de

    return tenant_de(org)


def cotejar(orden) -> dict:
    """Le pregunta al motor y DEVUELVE lo que dijo. No escribe.

    FALLA AL `no_se_sabe`, SIEMPRE. El motor ya contesta 200 con ese
    veredicto ante cualquier problema suyo --por eso esta ruta no tira 500--,
    y lo que se cubre aca es que el motor no conteste en absoluto. En ningun
    caso se devuelve `si` por un error: el costo de los dos errores no es el
    mismo, y esta escrito en `nucleo/canales/cotejo.py`.
    """
    import requests

    from campo import revision_del_cierre as RC

    tenant = _tenant_de(orden.org)
    if not tenant:
        return {"veredicto": NO_SE_SABE, "apagado": False,
                "motivo": "la empresa no esta en el motor", "error": ""}

    ticket = RC.el_ticket(orden)
    #  LOS DOS LADOS, armados aca y no en el motor: el motor no sabe que es
    #  una orden de trabajo. Lo que se pidio es el asunto mas el caso mas lo
    #  que ya se habia diagnosticado; los tres dicen cosas distintas y
    #  mandarlos sueltos obligaria al modelo a adivinar cual es cual.
    se_pidio = "\n".join(x for x in (
        f"Asunto: {ticket['asunto']}" if ticket["asunto"] else "",
        ticket["caso"],
        (f"Diagnostico previo: {ticket['diagnostico_previo']}"
         if ticket["diagnostico_previo"] else ""),
    ) if x)

    cierre = RC._cierre_de_esta_vuelta(orden)
    escrito = RC._lo_que_escribio_el_tecnico(orden, cierre)
    #  Y del otro lado, TODO lo que el tecnico dejo escrito, no solo
    #  `solucion`: «que encontro» es a veces lo unico que contradice el
    #  ticket, y en el caso del 12/11 era exactamente ahi donde estaba
    #  («fibra partida» contra «el equipo esta en linea»).
    que_hizo = "\n".join(f"{k}: {v}" for k, v in sorted(escrito.items())
                         if isinstance(v, (str, int, float)) and str(v).strip())

    base, cabeceras = _motor()
    try:
        r = requests.post(f"{base}/interno/cotejo/reporte-contra-ticket",
                          params={"tenant": tenant}, headers=cabeceras,
                          json={"se_pidio": se_pidio, "que_hizo": que_hizo},
                          timeout=30)
        if r.status_code != 200:
            return {"veredicto": NO_SE_SABE, "motivo": "", "error":
                    f"HTTP {r.status_code}"}
        d = r.json() or {}
    except Exception as e:                                       # noqa: BLE001
        logger.warning("cotejo: el motor no contesto (%s)", type(e).__name__)
        return {"veredicto": NO_SE_SABE, "motivo": "", "error":
                type(e).__name__}

    #  UN VEREDICTO QUE NO RECONOZCO NO ES UN `si`. El motor es nuestro, pero
    #  este es el borde entre dos servicios que se despliegan por separado:
    #  una version vieja o nueva del otro lado no puede producir un «cuadra»
    #  por accidente.
    veredicto = str(d.get("veredicto") or "")
    if veredicto not in (CUADRA, NO_CUADRA, NO_SE_SABE):
        veredicto = NO_SE_SABE
    return {"veredicto": veredicto,
            "motivo": str(d.get("motivo") or "")[:300],
            #  `apagado` VIAJA, y por defecto es False: si una version vieja
            #  del motor no lo manda, se asume que SI se pregunto -- queda
            #  una fila `no_se_sabe` de mas, que es ruido; asumir lo
            #  contrario esconderia un cotejo que si se hizo.
            "apagado": bool(d.get("apagado")),
            "error": str(d.get("error") or "")[:80],
            "segundos": float(d.get("segundos") or 0),
            "tokens": int(d.get("tokens") or 0)}


def cotejar_y_anotar(orden) -> str:
    """Coteja y deja la fila. Devuelve el veredicto.

    Una fila casi siempre, incluso cuando no se pudo juzgar: sin ella, la
    pantalla no puede distinguir «todavia no se miro» de «se miro y no se
    supo», y esa diferencia es la que le dice a una persona si vale la pena
    esperar.

    APAGADO NO DEJA FILA, Y ES LA EXCEPCION QUE EVITA UN DESASTRE
    --------------------------------------------------------------
    Encontrado antes de desplegar, el 12/11/2026. Esta funcion corre en CADA
    cierre, tenga la empresa el cotejo encendido o no. Con la bandera
    apagada el motor contesta --correctamente-- `no_se_sabe`, y si eso
    dejara una fila, el punto noveno la leeria, valdria None, y el veredicto
    de la orden seria REVISAR.

    O sea: **toda orden de toda empresa que no encendio el cotejo dejaria de
    cerrarse sola**, por una funcion apagada. Lo contrario de lo que esta
    funcion dice hacer.

    «Apagado» no es «no se supo»: es «no se pregunto». No deja rastro, y la
    revision se comporta igual que antes de que esto existiera.
    """
    r = cotejar(orden)
    if r.get("apagado"):
        return r["veredicto"]
    CotejoDelReporte.objects.create(
        org=orden.org, orden=orden, vuelta=getattr(orden, "vuelta", 1),
        origen=IA, veredicto=r["veredicto"], motivo=r.get("motivo", ""),
        error=r.get("error", ""), segundos=r.get("segundos", 0.0),
        tokens=r.get("tokens", 0))
    return r["veredicto"]
