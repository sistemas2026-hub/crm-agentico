# -*- coding: utf-8 -*-
"""
================================================================================
 SEGUIMIENTO  --  una situacion no termina porque termino un ciclo
================================================================================

QUE HACE
--------
Mira cada situacion abierta y dice en que va: si esta igual, si empeora, si
mejora, si no hay con que decidir, o si hace falta una persona. Anota el veredicto
en el timeline y fija cuando conviene volver a mirarla.

POR QUE ES UN MODULO APARTE DE 'correlacion.py'
----------------------------------------------
Porque son dos preguntas distintas. La correlacion pregunta "¿esta señal es de una
situacion que ya existe?"; el seguimiento pregunta "¿esta situacion como va?". La
primera mira UNA señal del ciclo actual; la segunda mira la HISTORIA de la
situacion y puede concluir sin ninguna señal nueva -- que es justamente el caso
que importa: una situacion de la que hace rato no se sabe nada.

Separarlas tambien permite saber donde esta un error: si una situacion quedo mal
agrupada o si quedo mal evaluada.

LO QUE NO HACE
--------------
No cierra. No ejecuta nada. No crea propuestas, no escribe actividades de M02, no
reprograma, no manda mensajes y no eleva autonomia. Produce un VEREDICTO y lo
escribe en la situacion y su timeline. Decidir que hacer con eso es de una
persona, o de una propuesta que una persona revisa.

Y no inventa una causa. 'SIN_EVIDENCIA' es una salida de primera clase: el
Supervisor tiene que poder decir "no tengo suficiente informacion" en vez de
elegir la explicacion mas probable y presentarla con el mismo tono que un hecho.
================================================================================
"""

from __future__ import annotations

from django.utils import timezone

from operaciones import situaciones as svc
from operaciones.situaciones_modelos import (Riesgo, SituacionAfectado,
                                             SituacionOperativa, TipoAfectado,
                                             TipoEvento)

S = SituacionOperativa

#  Cada cuanto conviene volver a mirar, segun el veredicto. Son minutos, y la
#  diferencia tiene motivo: una que empeora se mira seguido; una estable no gana
#  nada con que se la revise cada cinco minutos.
PROXIMA_REVISION = {
    "empeora": 5,
    "requiere_humano": 10,
    "estable": 20,
    "mejora": 15,
    "sin_evidencia": 15,
    "puede_resolverse": 30,
}

#  Cuanto tiene que crecer el numero de afectados para decir que EMPEORA. Uno
#  solo ya cuenta: en una caida optica, un afectado mas es un abonado mas sin
#  servicio. El umbral existe para no llamar "empeora" a un cambio de cero.
CRECIMIENTO_PARA_EMPEORA = 1

#  Cuantos ciclos seguidos sin informacion concluyente hacen falta antes de pedir
#  una persona. Dos y no uno: un ciclo sin dato puede ser un hueco de lectura, y
#  la capa de fuentes ya distingue eso. Dos seguidos es un patron.
CICLOS_SIN_EVIDENCIA_PARA_ESCALAR = 2

#  Desde que riesgo una situacion pide una persona por si sola, sin importar como
#  evolucione. Un critico que "esta estable" sigue siendo un critico.
RIESGO_QUE_PIDE_HUMANO = (Riesgo.CRITICO,)


class Veredicto:
    """
    Como va una situacion. Siete salidas, y ninguna es "se resolvio".

    Cerrar NO esta aqui a proposito: 'PUEDE_RESOLVERSE' dice que estan dadas las
    condiciones para ir a verificar, no que se resolvio. La diferencia es la que
    sostiene todo el bloque anterior -- una señal que desaparece tiene dos
    explicaciones, y solo una persona que comprueba puede elegir cual.
    """

    ESTABLE = "estable"
    EMPEORA = "empeora"
    MEJORA = "mejora"
    SIN_EVIDENCIA = "sin_evidencia"
    REQUIERE_HUMANO = "requiere_humano"
    PUEDE_RESOLVERSE = "puede_resolverse"

    TODOS = (ESTABLE, EMPEORA, MEJORA, SIN_EVIDENCIA, REQUIERE_HUMANO,
             PUEDE_RESOLVERSE)
    #  Los que NO autorizan a concluir nada sobre el mundo.
    NO_CONCLUYENTES = (SIN_EVIDENCIA,)


def evaluar(situacion, *, ahora=None) -> dict:
    """
    El veredicto de UNA situacion, con el porque. No escribe nada.

    Se separa de 'seguir()' para poder probar el razonamiento sin tocar la base, y
    --mas importante-- para que el veredicto sea reproducible: con la misma
    situacion y el mismo 'ahora' devuelve lo mismo.

    EL ORDEN DE LAS PREGUNTAS ES LA REGLA
    -------------------------------------
    Primero lo que pide una persona, despues lo que no se sabe, y solo al final la
    evolucion. Al reves, una situacion critica de la que no hay datos saldria
    clasificada como "sin evidencia" y nadie la miraria.
    """
    ahora = ahora or timezone.now()

    vivos = SituacionAfectado.objects.filter(
        situacion=situacion, recuperado_en__isnull=True)
    afectados_ahora = vivos.count()
    #  El conteo del PON es el numero que de verdad describe la afectacion: los
    #  afectados de tipo 'caso' o 'datos_insuficientes' no son abonados caidos.
    pon = vivos.filter(tipo=TipoAfectado.PON).first()
    abonados_afectados = int((pon.datos or {}).get("afectados") or 0) if pon else 0

    #  Cuantos ciclos seguidos la fuente no concluyo. Se cuenta sobre el timeline,
    #  que es el unico registro que no se reescribe.
    recientes = list(situacion.eventos.order_by("-ocurrido_en",
                                                "-registrado_en")[:6])
    sin_datos_seguidos = 0
    for e in recientes:
        if e.tipo == TipoEvento.INCONCLUSA:
            sin_datos_seguidos += 1
        elif e.tipo in (TipoEvento.ACTUALIZADA, TipoEvento.DETECTADA):
            break

    #  Cuanto crecio o bajo respecto de la ultima medicion registrada.
    anterior = _abonados_del_evento_anterior(situacion)
    delta = (abonados_afectados - anterior) if anterior is not None else None

    #  --- 1. ¿pide una persona? ------------------------------------------
    if situacion.riesgo in RIESGO_QUE_PIDE_HUMANO:
        return _salida(Veredicto.REQUIERE_HUMANO,
                       f"el riesgo es '{situacion.riesgo}': una afectacion de "
                       f"este tamaño necesita que alguien la mire, sin importar "
                       f"como evolucione",
                       afectados_ahora, abonados_afectados, delta, ahora)
    if sin_datos_seguidos >= CICLOS_SIN_EVIDENCIA_PARA_ESCALAR:
        return _salida(Veredicto.REQUIERE_HUMANO,
                       f"{sin_datos_seguidos} ciclos seguidos sin informacion "
                       f"concluyente de la fuente: no se puede decir si sigue "
                       f"pasando ni si se resolvio",
                       afectados_ahora, abonados_afectados, delta, ahora)

    #  --- 2. ¿se sabe algo? ----------------------------------------------
    if sin_datos_seguidos:
        return _salida(Veredicto.SIN_EVIDENCIA,
                       "el ultimo ciclo no trajo informacion concluyente; no se "
                       "concluye nada todavia",
                       afectados_ahora, abonados_afectados, delta, ahora)
    if situacion.senal_vista_en is None:
        return _salida(Veredicto.SIN_EVIDENCIA,
                       "no hay ninguna lectura concluyente registrada",
                       afectados_ahora, abonados_afectados, delta, ahora)

    #  --- 3. ¿como evoluciona? -------------------------------------------
    if abonados_afectados == 0:
        #  No queda nadie afectado. Son las CONDICIONES para ir a verificar, no
        #  una resolucion: cerrar exige que alguien compruebe.
        return _salida(Veredicto.PUEDE_RESOLVERSE,
                       "ya no hay abonados afectados en la lectura; hace falta "
                       "comprobar si se resolvio antes de cerrar",
                       afectados_ahora, abonados_afectados, delta, ahora)
    if delta is not None and delta >= CRECIMIENTO_PARA_EMPEORA:
        return _salida(Veredicto.EMPEORA,
                       f"los afectados pasaron de {anterior} a "
                       f"{abonados_afectados}",
                       afectados_ahora, abonados_afectados, delta, ahora)
    if delta is not None and delta < 0:
        return _salida(Veredicto.MEJORA,
                       f"los afectados bajaron de {anterior} a "
                       f"{abonados_afectados}",
                       afectados_ahora, abonados_afectados, delta, ahora)
    return _salida(Veredicto.ESTABLE,
                   f"sigue con {abonados_afectados} afectados, sin cambio",
                   afectados_ahora, abonados_afectados, delta, ahora)


def _salida(veredicto, porque, afectados, abonados, delta, ahora) -> dict:
    return {
        "veredicto": veredicto,
        "porque": porque,
        "afectados_registrados": afectados,
        "abonados_afectados": abonados,
        "delta": delta,
        "concluyente": veredicto not in Veredicto.NO_CONCLUYENTES,
        "proxima_revision_en": ahora + timezone.timedelta(
            minutes=PROXIMA_REVISION.get(veredicto, 20)),
    }


def _abonados_del_evento_anterior(situacion):
    """
    Cuantos abonados decia la medicion ANTERIOR. None si no hay con que comparar.

    Sale del timeline y no de una columna: una columna 'afectados_anteriores'
    habria que mantenerla en cada escritura, y el timeline ya lo tiene porque
    'actualizar' anota el hecho de cada ciclo. Se busca el penultimo evento de
    medicion -- el ultimo describe el estado de AHORA.
    """
    import re

    mediciones = list(situacion.eventos.filter(
        tipo__in=(TipoEvento.DETECTADA, TipoEvento.ACTUALIZADA)
    ).order_by("-ocurrido_en", "-registrado_en")[:2])
    if len(mediciones) < 2:
        return None
    #  El resumen es el HECHO, con la forma "N ONT afectadas en el PON x/y/z".
    m = re.match(r"\s*(\d+)\s+ONT", mediciones[1].resumen or "")
    return int(m.group(1)) if m else None


def seguir(org, *, ahora=None, proponer=None, interpretar=None) -> dict:
    """
    Evalua todas las situaciones abiertas y deja el veredicto escrito.

    'proponer' se INYECTA en vez de importarse. Dos motivos: este modulo no tiene
    por que conocer las propuestas --su trabajo termina en el veredicto-- y
    separarlo permite probar el seguimiento sin crear ni una propuesta. Quien lo
    pasa es el ciclo.

    'interpretar' se inyecta por lo mismo, y es lo que le da al cerebro su lugar
    aqui. ESTE MODULO SIGUE DECIDIENDO EL VEREDICTO: lo que el cerebro puede
    aportar es el POR QUE, y solo si una bandera lo habilita. Si no se pasa, el
    seguimiento es exactamente el de antes.

    POR QUE IMPORTA QUE SEA AQUI Y NO SOLO EN LA DETECCION
    -----------------------------------------------------
    En el ciclo el cerebro ve una señal recien detectada. Aqui ve una SITUACION
    con su historia -- cuantos afectados tenia, como cambio, cuantas veces se
    reviso. Un sistema que razona sobre señales sueltas reacciona; uno que razona
    sobre como evoluciona algo que ya conocia, sigue un hilo. Esa es la
    diferencia entre un motor de ciclo y un agente, y vive en esta linea.

    Lo llama el mismo turno del scheduler que el sondeo y la correlacion,
    inmediatamente despues: asi el veredicto se calcula sobre la captura mas
    reciente y no sobre la del ciclo anterior.

    UNA SITUACION QUE REVIENTA NO SE LLEVA A LAS DEMAS, por el mismo motivo que en
    el sondeo: diez situaciones sin evaluar por culpa de una, y nada que lo
    explique, es peor que una en rojo.
    """
    ahora = ahora or timezone.now()
    informe = {"evaluadas": 0, "por_veredicto": {}, "errores": 0,
               "piden_humano": 0}

    for situacion in S.objects.filter(org=org, estado__in=S.VIVAS):
        try:
            salida = evaluar(situacion, ahora=ahora)
        except Exception as e:                                   # noqa: BLE001
            informe["errores"] += 1
            svc.anotar(situacion, TipoEvento.EVIDENCIA,
                       f"no se pudo evaluar el seguimiento: {type(e).__name__}",
                       ocurrido_en=ahora)
            continue

        #  EL CEREBRO, ANTES DE ESCRIBIR. Va aqui y no despues porque lo unico
        #  que puede aportar es el 'porque', y el 'porque' es lo que se anota.
        #  Nunca cambia el veredicto, la proxima revision ni los conteos: eso lo
        #  comprueba 'interpretar' en codigo y lo afirma 'test_12b'.
        if interpretar is not None:
            try:
                salida = interpretar(situacion, salida, ahora=ahora) or salida
            except Exception as e:                               # noqa: BLE001
                #  Que el cerebro no pueda interpretar no invalida el veredicto,
                #  que es correcto sin el. Se cuenta aparte para que el fallo se
                #  vea en vez de desaparecer -- mismo criterio que el proponedor.
                informe["errores_interpretacion"] = (
                    informe.get("errores_interpretacion", 0) + 1)
                svc.anotar(situacion, TipoEvento.EVIDENCIA,
                           f"no se pudo interpretar el seguimiento: "
                           f"{type(e).__name__}", ocurrido_en=ahora)

        _escribir(situacion, salida, ahora)
        informe["evaluadas"] += 1
        v = salida["veredicto"]
        informe["por_veredicto"][v] = informe["por_veredicto"].get(v, 0) + 1
        if v == Veredicto.REQUIERE_HUMANO:
            informe["piden_humano"] += 1

        if proponer is not None:
            try:
                if proponer(situacion, salida, ahora=ahora) is not None:
                    informe["propuestas"] = informe.get("propuestas", 0) + 1
            except Exception as e:                               # noqa: BLE001
                #  Que no se pueda dejar una recomendacion no invalida el
                #  veredicto, que ya quedo escrito. Se cuenta aparte para que el
                #  fallo se vea en vez de desaparecer.
                informe["errores_propuesta"] = (
                    informe.get("errores_propuesta", 0) + 1)
                svc.anotar(situacion, TipoEvento.EVIDENCIA,
                           f"no se pudo dejar la recomendacion: "
                           f"{type(e).__name__}", ocurrido_en=ahora)

    return informe


def _escribir(situacion, salida, ahora) -> None:
    """
    Anota el veredicto y mueve el estado SOLO donde la maquina lo permite.

    Las dos transiciones que el seguimiento puede hacer solo:

      detectada -> investigando   la señal se vio otra vez; ya no es un dato
                                  suelto.
      * -> en_verificacion        no quedan afectados. Es ir a COMPROBAR, no
                                  cerrar.

    Cualquier otra la decide una persona. En particular 'requiere_humano' NO
    cambia el estado: marcarlo como 'en_atencion' afirmaria que alguien lo esta
    atendiendo, y lo que pasa es lo contrario -- hace falta que alguien lo haga.
    """
    svc.anotar(situacion, TipoEvento.EVIDENCIA,
               f"seguimiento: {salida['veredicto']} -- {salida['porque']}",
               datos={"veredicto": salida["veredicto"],
                      "abonados_afectados": salida["abonados_afectados"],
                      "delta": salida["delta"],
                      "concluyente": salida["concluyente"]},
               ocurrido_en=ahora)

    situacion.proxima_revision_en = salida["proxima_revision_en"]
    situacion.actualizada_en = ahora
    situacion.save(update_fields=["proxima_revision_en", "actualizada_en"])

    if (salida["veredicto"] == Veredicto.PUEDE_RESOLVERSE
            and situacion.estado != S.EN_VERIFICACION):
        try:
            svc.cambiar_estado(
                situacion, S.EN_VERIFICACION,
                motivo="el seguimiento no encuentra afectados; hay que "
                       "comprobar si se resolvio",
                ahora=ahora)
        except svc.TransicionInvalida:
            #  Desde un estado que no lo permite se deja como esta: el veredicto
            #  ya quedo anotado, y forzar la transicion seria saltearse la
            #  maquina de estados por conveniencia.
            pass
