# -*- coding: utf-8 -*-
"""
================================================================================
 VERIFICACIONES VENCIDAS  --  el reloj cierra las que el cliente no vuelve a abrir
================================================================================

QUE PROBLEMA RESUELVE (10/11/2026)
----------------------------------
Despues de una accion con efecto (hoy, reiniciar el equipo) queda una
verificacion pendiente: a los N segundos se mide si el efecto aparecio. Esa
medicion corria SOLO al empezar el turno siguiente del cliente
(api._resolver_verificacion_pendiente). Si el cliente no volvia a escribir --
que es justo el caso feliz: el reinicio anduvo y no necesita nada mas--:

  - la conversacion no se cerraba nunca sola: el cierre automatico se niega
    mientras haya una verificacion pendiente (transiciones.cerrar,
    'verificacion_pendiente');
  - la herramienta PERDIA la autonomia ganada: con 3 verificaciones sin
    resolver de mas de una hora, el codigo la degrada (api.py,
    MAXIMO_SIN_RESOLVER). El exito castigado como un fallo;
  - el panel las contaba como pendientes para siempre.

COMO
----
La misma medicion y la misma evaluacion que el turno --motor.medir_para_
verificar y verificacion_accion.evaluar--, con la sesion rearmada de lo que la
conversacion guardo (la identidad verificada y los identificadores tecnicos,
Sesion.CAMPOS_PERSISTIBLES). No hay una segunda regla: solo un segundo momento.

  CONFIRMADA                  se guarda, y la conversacion ya puede cerrarse.
  NO_CONFIRMADA/NO_VERIFICABLE se guarda, la herramienta pierde la autonomia
                              ganada (condicion 4, PRD §2) y, si declara
                              'escalar_si_no_confirma', la conversacion pasa a
                              una persona: el efecto no aparecio y el cliente no
                              volvio a decir nada. Escalar es solo estado
                              (transiciones.escalar): no crea casos ni tickets.
  PENDIENTE (otro intento)    sube el contador; el proximo ciclo vuelve a medir.

QUE NO HACE
-----------
No le escribe al cliente. Una verificacion no tiene un texto que mandarle
fuera de su turno, y lo que dice cada estado (preguntar si le volvio el
servicio) es para cuando el cliente esta en la conversacion.

MARGEN
------
Solo toma las vencidas hace mas de MARGEN_SEGUNDOS: si el cliente escribe,
su turno la resuelve primero, con la nota al modelo. El reloj se queda con las
que nadie iba a resolver.
================================================================================
"""

from __future__ import annotations

from nucleo.observabilidad.registro import id_interno, registrar
from nucleo.persistencia import db as persistencia
from nucleo.seguimiento import verificacion_accion

#: Cuanto despues del plazo las toma el reloj. Quince minutos: el cliente que
#: va a volver a escribir suele hacerlo antes. El reloj pasa cada hora
#: (operativo.INTERVALO_BARRIDO_SEGUNDOS), asi que en el peor caso una
#: verificacion se resuelve ~1 h 15 min despues del plazo; antes, nunca.
MARGEN_SEGUNDOS = 900

#: Cuantas por pasada y por empresa. Cada una son unas pocas llamadas al
#: proveedor; con un tope, una cola grande se reparte en varios ciclos en vez
#: de gastar el cupo de la hora de golpe.
LIMITE_POR_PASADA = 20

TERMINAN_MAL = (verificacion_accion.NO_CONFIRMADA, verificacion_accion.NO_VERIFICABLE)


def sesion_desde_guardado(fila: dict):
    """La sesion de la conversacion, rearmada como la rearma el turno al
    retomarla (api._estado_inicial): identidad y campos tecnicos persistidos."""
    from nucleo.seguridad.verificacion import Sesion

    sesion = Sesion(identificador_canal=f"reloj:{fila['conversation_id']}")
    if fila.get("id_cliente"):
        sesion.verificado = True
        sesion.nivel = max(sesion.nivel, 1)
        sesion.id_cliente = fila["id_cliente"]
        sesion.nombre = fila.get("nombre_cliente")
        for campo, valor in (fila.get("datos_sesion") or {}).items():
            if campo in Sesion.CAMPOS_PERSISTIBLES and valor:
                setattr(sesion, campo, valor)
    return sesion


def barrer(config, tenant: str, *, simular: bool = False,
           limite: int = LIMITE_POR_PASADA) -> dict:
    """Mide y resuelve las verificaciones vencidas de una empresa."""
    from nucleo.modelo import motor
    from nucleo.persistencia import autonomia_ganada as registro_autonomia
    from nucleo.relevo import transiciones

    vencidas = persistencia.verificaciones_vencidas(tenant, MARGEN_SEGUNDOS, limite)
    informe = {"vencidas": len(vencidas), "confirmadas": 0, "no_confirmadas": 0,
               "siguen_pendientes": 0, "escaladas": 0}
    if simular:
        informe["haria"] = f"medir {len(vencidas)} verificacion(es) vencidas"
        return informe

    por_nombre = {h.nombre: h for h in config.herramientas}
    for fila in vencidas:
        herramienta = por_nombre.get(fila["herramienta"])
        intentos = int(fila["intentos"]) + 1
        if herramienta is None or not herramienta.verificacion:
            # Mismo criterio que el turno: sin criterio no se mide, y dejarla
            # pendiente trabaria el cierre para siempre.
            persistencia.resolver_verificacion(
                tenant, fila["id"], verificacion_accion.NO_VERIFICABLE,
                "la herramienta ya no declara como comprobarse", None, intentos - 1)
            informe["no_confirmadas"] += 1
            continue

        medicion = motor.medir_para_verificar(
            config, herramienta.verificacion, sesion_desde_guardado(fila),
            config.identidad.slug, config.variables_tenant)
        resultado, por_que = verificacion_accion.evaluar(
            herramienta.verificacion.comprobaciones, fila["medicion_previa"] or {},
            medicion, intentos, int(fila["max_intentos"]))
        persistencia.resolver_verificacion(
            tenant, fila["id"], resultado, por_que, medicion, intentos)
        registrar("verificacion", "accion comprobada por el reloj",
                  herramienta=fila["herramienta"], resultado=resultado,
                  intento=intentos, verificacion_id=str(fila["id"]))

        if resultado == verificacion_accion.CONFIRMADA:
            informe["confirmadas"] += 1
        elif resultado in TERMINAN_MAL:
            informe["no_confirmadas"] += 1
            try:
                registro_autonomia.degradar(
                    tenant, fila["herramienta"], "una verificacion no confirmo el efecto",
                    {"verificacion": str(fila["id"])})
            except (Exception, SystemExit) as e:                # noqa: BLE001
                registrar("autonomia_ganada", "no se pudo degradar la autonomia",
                          tenant=tenant, herramienta=fila["herramienta"], error=e)
            motivo = herramienta.verificacion.escalar_si_no_confirma
            if motivo and fila.get("estado") != "cerrada":
                r = transiciones.escalar(tenant, str(fila["conversation_id"]), motivo=motivo)
                if getattr(r, "aplicada", False):
                    informe["escaladas"] += 1
                    registrar("verificacion", "conversacion escalada por una accion sin efecto",
                              conversation_id=id_interno(fila["conversation_id"]))
        else:
            informe["siguen_pendientes"] += 1
    return informe
