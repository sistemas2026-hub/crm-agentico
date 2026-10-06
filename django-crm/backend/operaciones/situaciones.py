# -*- coding: utf-8 -*-
"""
================================================================================
 SITUACIONES  --  abrir, actualizar, verificar, cerrar. Nada que salga afuera.
================================================================================

QUE HACE
--------
El servicio de 'SituacionOperativa': crear una situacion, agregarle afectados,
anotar su timeline, moverla de estado y cerrarla cuando hay verificacion.

LO QUE NO HACE, Y HAY PRUEBAS QUE LO AFIRMAN CONTANDO FILAS
-----------------------------------------------------------
No reinicia un equipo, no cierra un caso, no toca 'Case.status', no crea
tickets, no reprograma, no manda mensajes, no crea propuestas y no eleva
autonomia. Crear o actualizar una situacion es una operacion INTERNA de
supervision: lo unico que cambia son tablas propias de este modulo.

TRES REGLAS QUE LA BASE HACE CUMPLIR, NO ESTE ARCHIVO
-----------------------------------------------------
  1. Una sola situacion VIVA por huella  -> indice unico PARCIAL.
  2. Un afectado no se cuenta dos veces  -> unico (situacion, tipo, id).
  3. Cerrar exige verificacion            -> CheckConstraint.

Estan en la base a proposito: un 'if' en Python no sobrevive a dos ciclos
concurrentes, y los tres casos que importan son justamente carreras.
================================================================================
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from operaciones.situaciones_modelos import (Confianza, Riesgo,
                                             SituacionAfectado, SituacionEvento,
                                             SituacionOperativa,
                                             SituacionRelacion, TipoAfectado,
                                             TipoEvento, TipoRelacion)

S = SituacionOperativa


class ErrorSituacion(Exception):
    """Algo no se puede hacer con esta situacion."""


class TransicionInvalida(ErrorSituacion):
    """Ese cambio de estado no esta permitido."""


# =============================================================================
#  LA MAQUINA DE ESTADOS
# =============================================================================
#  Literal y revisable de un vistazo, igual que 'actividades.TRANSICIONES'. Lo
#  que NO esta aqui no se puede hacer: es una lista blanca.
TRANSICIONES = {
    S.DETECTADA: {S.INVESTIGANDO, S.CONFIRMADA, S.EN_VERIFICACION, S.DESCARTADA},
    S.INVESTIGANDO: {S.CONFIRMADA, S.EN_ATENCION, S.EN_VERIFICACION,
                     S.DESCARTADA},
    S.CONFIRMADA: {S.EN_ATENCION, S.EN_VERIFICACION, S.DESCARTADA},
    S.EN_ATENCION: {S.EN_VERIFICACION, S.CONFIRMADA, S.DESCARTADA},
    #  Desde verificacion se puede VOLVER: si la señal reaparece, no se resolvio.
    #  Esa vuelta es la que hace que una recaida no quede tapada por un cierre
    #  apresurado.
    S.EN_VERIFICACION: {S.RESUELTA, S.CONFIRMADA, S.EN_ATENCION, S.DESCARTADA},
    #  Resuelta NO es terminal: se cierra, o se reabre si vuelve a pasar.
    S.RESUELTA: {S.CERRADA, S.CONFIRMADA},
    #  Las dos terminales no salen a ningun lado. Reabrir una cerrada seria otra
    #  situacion -- y su huella ya esta libre, asi que se puede crear.
    S.CERRADA: set(),
    S.DESCARTADA: set(),
}

#  Para llegar a RESUELTA hay que haber pasado por verificacion. No es una
#  convencion: es el unico camino que 'TRANSICIONES' deja abierto, y es
#  deliberado -- CLAUDE.md §12 ya dejo escrito que un efecto que ningun endpoint
#  puede confirmar no se declara confirmado.
ESTADOS_QUE_EXIGEN_MOTIVO = (S.DESCARTADA,)


def _exigir_transicion(actual: str, nuevo: str) -> None:
    if actual == nuevo:
        return
    if nuevo not in TRANSICIONES.get(actual, set()):
        raise TransicionInvalida(
            f"Una situacion '{actual}' no puede pasar a '{nuevo}'. "
            f"Permitidas: {sorted(TRANSICIONES.get(actual, set())) or 'ninguna'}.")


# =============================================================================
#  EL TIMELINE
# =============================================================================

def anotar(situacion, tipo: str, resumen: str, *, datos=None, actor=None,
           ocurrido_en=None) -> SituacionEvento:
    """
    Agrega un evento. Es la UNICA forma de escribir en el timeline.

    'ocurrido_en' por defecto es ahora, pero se puede pasar: un ciclo que procesa
    una captura de hace tres minutos deberia fechar el evento cuando paso, no
    cuando lo leimos.
    """
    if tipo not in TipoEvento.TODOS:
        raise ErrorSituacion(f"tipo de evento desconocido: {tipo!r}")
    return SituacionEvento.objects.create(
        situacion=situacion, org=situacion.org, tipo=tipo,
        resumen=resumen[:255], datos=datos or {},
        ocurrido_en=ocurrido_en or timezone.now(), actor=actor)


# =============================================================================
#  ABRIR
# =============================================================================

def _siguiente_codigo(org) -> str:
    """
    'S-001', 'S-002'... por ORGANIZACION.

    Se calcula del maximo existente. Dos creaciones concurrentes pueden calcular
    el mismo numero; de eso se encarga la restriccion unica (org, codigo) y el
    reintento de 'abrir()'. Un contador en una tabla aparte seria otra fila que
    bloquear, y el consecutivo no vale ese costo.
    """
    ultimo = (S.objects.filter(org=org)
              .aggregate(n=Max("codigo")).get("n") or "")
    try:
        numero = int(str(ultimo).split("-")[-1]) + 1
    except (ValueError, IndexError):
        numero = S.objects.filter(org=org).count() + 1
    return f"S-{numero:03d}"


def abrir(org, senal, *, ahora=None, snapshot_id=None) -> SituacionOperativa:
    """
    Crea la situacion que describe esta señal, y anota su deteccion.

    NO comprueba si ya existe: eso es de 'correlacion.agrupar', que es quien
    busca primero. Si dos ciclos llegan juntos, el indice unico parcial hace que
    el segundo reviente con IntegrityError -- y quien llama lo traduce a "ya
    existia", que es la verdad.
    """
    ahora = ahora or timezone.now()
    observada = senal.observada_en or ahora

    with transaction.atomic():
        situacion = S.objects.create(
            org=org,
            codigo=_siguiente_codigo(org),
            tipo=senal.tipo_situacion,
            titulo=_titulo_de(senal),
            descripcion=senal.interpretacion or senal.hecho,
            estado=S.DETECTADA,
            riesgo=senal.riesgo,
            huella=senal.huella,
            detectada_en=ahora,
            actualizada_en=ahora,
            senal_vista_en=observada,
            fuente_origen=senal.fuente,
            snapshot_origen_id=snapshot_id,
            hipotesis=senal.hipotesis,
            confianza=senal.confianza,
            recomendacion=senal.recomendacion,
            evidencia=list(senal.evidencia),
        )
        anotar(situacion, TipoEvento.DETECTADA, senal.hecho,
               datos={"relacion": senal.relacion,
                      "interpretacion": senal.interpretacion,
                      "riesgo": senal.riesgo,
                      "fuente": senal.fuente,
                      "concluyente": senal.concluyente},
               ocurrido_en=observada)
        if senal.hipotesis:
            #  La hipotesis se anota como SU PROPIO evento, con su confianza. Asi
            #  el timeline deja ver cuando se empezo a creer algo, aparte de
            #  cuando se vio el hecho.
            anotar(situacion, TipoEvento.HIPOTESIS, senal.hipotesis,
                   datos={"confianza": senal.confianza}, ocurrido_en=observada)
        if senal.recomendacion:
            anotar(situacion, TipoEvento.RECOMENDACION, senal.recomendacion,
                   ocurrido_en=observada)
        agregar_afectados(situacion, senal.afectados, ahora=ahora,
                          fuente=senal.fuente, anotar_eventos=False)
    return situacion


def _titulo_de(senal) -> str:
    """Un titulo que dice que se cree y no lo afirma como hecho."""
    if senal.dimension == "pon":
        return f"Posible afectación del PON {senal.clave_dimension}"
    if senal.dimension == "olt":
        return f"Posible afectación de la OLT {senal.clave_dimension}"
    if senal.dimension == "zona":
        return f"Posible afectación de la zona {senal.clave_dimension}"
    return senal.hecho[:255]


# =============================================================================
#  AFECTADOS
# =============================================================================

def agregar_afectados(situacion, afectados, *, ahora=None, fuente="",
                      anotar_eventos=True) -> dict:
    """
    Suma o actualiza afectados. Idempotente por (situacion, tipo, identificador).

    LO QUE DEVUELVE, Y POR QUE IMPORTA LA DIFERENCIA
    ------------------------------------------------
    {'nuevos': N, 'vistos': M}: cuantos aparecieron por primera vez y cuantos ya
    estaban y se volvieron a ver. Es lo que permite que el segundo ciclo con 15
    afectados anote "3 nuevos" en vez de "15 afectados" otra vez -- y que el
    conteo no se duplique.
    """
    ahora = ahora or timezone.now()
    nuevos, vistos = 0, 0

    for a in afectados:
        tipo = a.get("tipo")
        if tipo not in TipoAfectado.TODOS:
            raise ErrorSituacion(f"tipo de afectado desconocido: {tipo!r}")
        identificador = str(a.get("identificador") or "")
        if not identificador:
            raise ErrorSituacion(
                "un afectado sin identificador no se puede deduplicar: si no se "
                "sabe que esta afectado, el tipo es 'datos_insuficientes'")

        #  El alta va por '_upsert_afectado', que crea e intenta de nuevo si
        #  otro ciclo gano la carrera. La restriccion unica de la base es la que
        #  decide; aqui no hay un 'select' previo del que depender.
        _, creado = _upsert_afectado(situacion, tipo, identificador, a,
                                     ahora, fuente)
        if creado:
            nuevos += 1
        else:
            vistos += 1

    #  El contador de la situacion se RECALCULA de las filas, no se incrementa:
    #  un incremento sobre un valor leido es la actualizacion perdida clasica
    #  cuando dos ciclos corren juntos.
    situacion.afectados_contados = SituacionAfectado.objects.filter(
        situacion=situacion, recuperado_en__isnull=True).count()
    situacion.save(update_fields=["afectados_contados"])

    if anotar_eventos and nuevos:
        anotar(situacion, TipoEvento.AFECTADO_NUEVO,
               f"{nuevos} afectado(s) nuevo(s)",
               datos={"nuevos": nuevos, "total": situacion.afectados_contados},
               ocurrido_en=ahora)

    return {"nuevos": nuevos, "vistos": vistos,
            "total": situacion.afectados_contados}


def _upsert_afectado(situacion, tipo, identificador, a, ahora, fuente):
    """
    Un afectado, creado o actualizado. Devuelve (fila, creado).

    Se escribe a mano --en vez de 'update_or_create' directo-- para poder fijar
    'detectado_en' SOLO al crear: si se pasara en los defaults, cada ciclo
    reescribiria la fecha de deteccion y la situacion perderia desde cuando esta
    afectado ese recurso.
    """
    defaults = {
        "org": situacion.org,
        "etiqueta": str(a.get("etiqueta") or "")[:120],
        "visto_en": ahora,
        "fuente": fuente or a.get("fuente", ""),
        "datos": a.get("datos") or {},
        "recuperado_en": None,
    }
    try:
        with transaction.atomic():
            fila = SituacionAfectado.objects.create(
                situacion=situacion, tipo=tipo, identificador=identificador,
                detectado_en=ahora, **defaults)
            return fila, True
    except IntegrityError:
        #  Ya existia: otro ciclo lo creo, o es el mismo recurso de una pasada
        #  anterior. Se actualiza lo que cambia y se deja 'detectado_en' quieto.
        SituacionAfectado.objects.filter(
            situacion=situacion, tipo=tipo,
            identificador=identificador).update(**defaults)
        fila = SituacionAfectado.objects.get(
            situacion=situacion, tipo=tipo, identificador=identificador)
        return fila, False


def marcar_recuperados(situacion, identificadores_vigentes, *, tipo,
                       ahora=None) -> int:
    """
    Marca como recuperados los afectados de ese tipo que ya NO aparecen.

    No borra: la fila queda con 'recuperado_en'. Borrarla perderia que estuvo
    afectado, y con eso la posibilidad de contar la evolucion entre ciclos -- que
    es justo lo que el bloque pide poder ver.
    """
    ahora = ahora or timezone.now()
    vigentes = {str(i) for i in identificadores_vigentes}
    pendientes = SituacionAfectado.objects.filter(
        situacion=situacion, tipo=tipo, recuperado_en__isnull=True)
    cuantos = 0
    for fila in pendientes:
        if fila.identificador not in vigentes:
            fila.recuperado_en = ahora
            fila.save(update_fields=["recuperado_en"])
            cuantos += 1
    if cuantos:
        situacion.afectados_contados = SituacionAfectado.objects.filter(
            situacion=situacion, recuperado_en__isnull=True).count()
        situacion.save(update_fields=["afectados_contados"])
        anotar(situacion, TipoEvento.AFECTADO_RECUPERADO,
               f"{cuantos} afectado(s) ya no aparecen",
               datos={"recuperados": cuantos,
                      "quedan": situacion.afectados_contados},
               ocurrido_en=ahora)
    return cuantos


# =============================================================================
#  ACTUALIZAR
# =============================================================================

def actualizar(situacion, senal, *, ahora=None) -> dict:
    """
    Una señal nueva sobre una situacion que YA existe. No crea otra.

    Es el caso del ejemplo: ciclo 1 con 12 afectados, ciclo 2 con 15. La misma
    situacion pasa a 15 y su timeline dice que aparecieron 3.
    """
    ahora = ahora or timezone.now()
    observada = senal.observada_en or ahora
    antes_riesgo = situacion.riesgo

    resultado = agregar_afectados(situacion, senal.afectados, ahora=ahora,
                                 fuente=senal.fuente)

    #  La evidencia se ACUMULA, no se reemplaza: es una lista de observaciones
    #  con su momento, y perder las viejas borraria desde cuando pasa.
    evidencia = list(situacion.evidencia or [])
    for e in senal.evidencia:
        if e not in evidencia:
            evidencia.append(e)
    situacion.evidencia = evidencia[-50:]

    situacion.actualizada_en = ahora
    if senal.concluyente:
        #  'senal_vista_en' solo avanza con una señal CONCLUYENTE: si la fuente
        #  no concluye, decir que la vimos recien haria parecer vigente algo que
        #  no se pudo comprobar.
        situacion.senal_vista_en = observada

    #  El riesgo puede subir o bajar. Se anota cuando cambia, con los dos
    #  valores: un riesgo que cambia sin registro es un numero que nadie puede
    #  discutir despues.
    if senal.riesgo != situacion.riesgo:
        situacion.riesgo = senal.riesgo

    #  La hipotesis se actualiza SOLO si la nueva tiene al menos tanta confianza
    #  como la que habia. Bajar la confianza sin motivo convertiria una
    #  explicacion sostenida en una duda por el ruido de un ciclo.
    if senal.hipotesis and (
            Confianza.TODAS.index(senal.confianza)
            >= Confianza.TODAS.index(situacion.confianza)):
        if senal.hipotesis != situacion.hipotesis:
            situacion.hipotesis = senal.hipotesis
            situacion.confianza = senal.confianza
            anotar(situacion, TipoEvento.HIPOTESIS, senal.hipotesis,
                   datos={"confianza": senal.confianza}, ocurrido_en=observada)

    situacion.save()

    if antes_riesgo != situacion.riesgo:
        anotar(situacion, TipoEvento.CAMBIO_RIESGO,
               f"el riesgo paso de '{antes_riesgo}' a '{situacion.riesgo}'",
               datos={"antes": antes_riesgo, "ahora": situacion.riesgo},
               ocurrido_en=observada)

    anotar(situacion, TipoEvento.ACTUALIZADA, senal.hecho,
           datos={"afectados_nuevos": resultado["nuevos"],
                  "afectados_total": resultado["total"],
                  "concluyente": senal.concluyente},
           ocurrido_en=observada)

    #  Una situacion recien detectada que vuelve a verse pasa a investigando: ya
    #  no es un dato suelto, se repitio.
    if situacion.estado == S.DETECTADA:
        cambiar_estado(situacion, S.INVESTIGANDO,
                       motivo="la señal se repitio en otro ciclo", ahora=ahora)

    return resultado


def anotar_inconclusa(situacion, senal, *, ahora=None) -> None:
    """
    La fuente contesto algo que no concluye. Se registra y NO se interpreta.

    Es lo que impide el error que el bloque nombra: un vacio de SmartOLT dentro de
    su ventana de agregacion NO puede leerse como "la red se recupero". La
    situacion sigue viva, su 'senal_vista_en' NO avanza, y el timeline dice que
    hubo un ciclo sin informacion util.
    """
    ahora = ahora or timezone.now()
    anotar(situacion, TipoEvento.INCONCLUSA,
           "la fuente contesto sin informacion concluyente en este ciclo",
           datos={"fuente": senal.fuente, "motivo": senal.interpretacion},
           ocurrido_en=senal.observada_en or ahora)
    situacion.actualizada_en = ahora
    situacion.save(update_fields=["actualizada_en"])


# =============================================================================
#  ESTADOS
# =============================================================================

def cambiar_estado(situacion, nuevo: str, *, motivo="", actor=None,
                   ahora=None) -> SituacionOperativa:
    """Mueve la situacion de estado, validando la transicion y anotandola."""
    ahora = ahora or timezone.now()
    actual = situacion.estado
    _exigir_transicion(actual, nuevo)
    if actual == nuevo:
        return situacion

    if nuevo in ESTADOS_QUE_EXIGEN_MOTIVO and not (motivo or "").strip():
        raise ErrorSituacion(
            f"pasar a '{nuevo}' exige un motivo: sin el, es indistinguible de "
            f"un borrado silencioso")

    if nuevo == S.DESCARTADA:
        #  La base exige que una descartada tenga descripcion. Se usa el motivo,
        #  que es exactamente el dato que falta.
        situacion.descripcion = motivo.strip()

    situacion.estado = nuevo
    situacion.actualizada_en = ahora
    if nuevo in S.TERMINALES:
        situacion.cerrada_en = ahora
    situacion.save()

    anotar(situacion, TipoEvento.CAMBIO_ESTADO,
           f"de '{actual}' a '{nuevo}'" + (f": {motivo}" if motivo else ""),
           datos={"antes": actual, "ahora": nuevo, "motivo": motivo},
           actor=actor, ocurrido_en=ahora)
    return situacion


def verificar(situacion, que_se_comprobo: str, *, actor=None,
              ahora=None) -> SituacionOperativa:
    """
    Registra QUE se comprobo. Es el requisito para poder resolver y cerrar.

    POR QUE NO ALCANZA CON QUE LA SEÑAL DESAPAREZCA
    ----------------------------------------------
    Porque una señal que desaparece tiene dos explicaciones: el problema se
    resolvio, o la fuente dejo de verlo. Toda la capa de fuentes del bloque
    anterior existe porque esas dos cosas se confundian. Aqui se cierra el
    circulo: para afirmar que se resolvio hay que decir que se comprobo.

    La base lo obliga con un CheckConstraint, asi que ni un camino nuevo de codigo
    puede saltearlo.
    """
    ahora = ahora or timezone.now()
    texto = (que_se_comprobo or "").strip()
    if not texto:
        raise ErrorSituacion(
            "una verificacion sin decir QUE se comprobo no es una verificacion")
    situacion.verificacion = texto
    situacion.verificada_en = ahora
    situacion.actualizada_en = ahora
    situacion.save(update_fields=["verificacion", "verificada_en",
                                  "actualizada_en"])
    anotar(situacion, TipoEvento.VERIFICACION, texto, actor=actor,
           ocurrido_en=ahora)
    return situacion


def cerrar(situacion, *, actor=None, ahora=None) -> SituacionOperativa:
    """
    Cierra la situacion. Exige verificacion registrada.

    Se comprueba ANTES de intentar el save para dar un mensaje util: sin esto el
    CheckConstraint de la base levantaria un IntegrityError que no explica nada a
    quien llamo.
    """
    if not (situacion.verificacion or "").strip() or situacion.verificada_en is None:
        raise ErrorSituacion(
            "no se puede cerrar una situacion sin verificacion: una señal que "
            "desaparece no prueba que el problema se resolvio")
    ahora = ahora or timezone.now()
    if situacion.estado != S.RESUELTA:
        #  El camino es verificacion -> resuelta -> cerrada, y no se saltea.
        _exigir_transicion(situacion.estado, S.RESUELTA)
        cambiar_estado(situacion, S.RESUELTA,
                       motivo="verificado", actor=actor, ahora=ahora)
    cambiar_estado(situacion, S.CERRADA, actor=actor, ahora=ahora)
    anotar(situacion, TipoEvento.CIERRE, "situacion cerrada", actor=actor,
           ocurrido_en=ahora)
    return situacion


# =============================================================================
#  RELACIONES
# =============================================================================

def relacionar(origen, destino, tipo: str, motivo: str, *, actor=None,
               ahora=None) -> SituacionRelacion:
    """
    Relaciona dos situaciones. Los tipos que afirman causa EXIGEN un actor.

    'coincide', 'contiene' y 'contenida_en' los puede poner la correlacion: son
    afirmaciones sobre topologia y tiempo, que es lo que midio. 'explica' y
    'duplicada_de' afirman algo que ninguna cercania temporal demuestra, asi que
    los pone una persona.
    """
    ahora = ahora or timezone.now()
    if tipo not in TipoRelacion.TODOS:
        raise ErrorSituacion(f"tipo de relacion desconocido: {tipo!r}")
    if origen.pk == destino.pk:
        raise ErrorSituacion("una situacion no se relaciona consigo misma")
    if origen.org_id != destino.org_id:
        raise ErrorSituacion(
            "no se relacionan situaciones de organizaciones distintas")
    if tipo not in TipoRelacion.AUTOMATICOS and actor is None:
        raise ErrorSituacion(
            f"la relacion '{tipo}' afirma algo que la correlacion no puede "
            f"medir: dos eventos cercanos no son causa y efecto. La pone una "
            f"persona.")
    if not (motivo or "").strip():
        raise ErrorSituacion("una relacion sin motivo es una afirmacion sin "
                             "respaldo")

    relacion, creada = SituacionRelacion.objects.get_or_create(
        origen=origen, destino=destino, tipo=tipo,
        defaults={"org": origen.org, "motivo": motivo.strip(),
                  "creada_en": ahora, "actor": actor})
    if creada:
        anotar(origen, TipoEvento.RELACION,
               f"{tipo} con {destino.codigo}: {motivo}",
               datos={"destino": destino.codigo, "tipo": tipo}, actor=actor,
               ocurrido_en=ahora)
    return relacion
