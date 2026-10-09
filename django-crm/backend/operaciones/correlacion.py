# -*- coding: utf-8 -*-
"""
================================================================================
 CORRELACION  --  juntar lo que va junto, sin afirmar que uno causa al otro
================================================================================

QUE HACE
--------
Toma las señales de 'deteccion.py' y decide, para cada una: abrir una situacion
nueva, o actualizar la que ya la describe. Despues asocia los tickets que
aparezcan, y pasa a verificacion las situaciones cuya señal dejo de verse.

LA DISTINCION QUE ORDENA TODO EL MODULO
---------------------------------------
Dos eventos cercanos en el tiempo NO son causa y efecto. Esto puede afirmar que
dos cosas COINCIDEN --comparten puerto, OLT o ventana-- y no puede afirmar que
una explique a la otra. Por eso 'situaciones.relacionar' exige un actor humano
para los tipos que afirman causa, y aqui solo se usan los automaticos.

LA FUERZA DE CADA DIMENSION, Y DE DONDE SALE
--------------------------------------------
    PON + ventana    FUERTE.  Comparten el mismo puerto optico: physicamente
                     cuelgan del mismo splitter y de la misma fibra. Si doce
                     caen juntos, la coincidencia es dificil de explicar por azar.
    OLT + ventana    INTERMEDIA. Comparten el equipo de cabecera. Dos PONs
                     distintos de la misma OLT pueden caer por una causa comun
                     --la OLT, su energia, su uplink-- o por dos causas
                     independientes.
    ZONA + ventana   DEBIL. Comparten geografia y nada mas. Un corte de luz
                     barrial y dos averias sueltas se ven igual desde aqui.

Esa jerarquia no es estetica: decide QUE se agrupa en una situacion (solo la
fuerte) y que se registra como RELACION entre situaciones (las otras dos). Meter
todo en una sola situacion porque comparten zona produciria una situacion enorme
que no dice nada.

LA DEDUPLICACION NO ES 'BUSCAR ANTES DE INSERTAR'
-------------------------------------------------
Se busca primero, si -- pero lo que de verdad la garantiza es el indice unico
PARCIAL de la base sobre (org, huella) limitado a los estados vivos. Entre el
'select' y el 'insert' hay una ventana, y dos ciclos del scheduler pueden caer
justo ahi. Cuando pasa, el segundo recibe IntegrityError y vuelve a buscar: la
situacion que encuentra es la que creo el otro. Hay una prueba con dos hilos de
verdad contra Postgres que lo afirma.

LO QUE NO HACE
--------------
No crea tickets, no cierra casos, no toca 'Case.status', no crea propuestas, no
ejecuta nada afuera y no eleva autonomia. Asociar un ticket a una situacion
escribe UNA fila en 'operaciones_situacion_afectado' y nada mas.
================================================================================
"""

from __future__ import annotations

from django.db import IntegrityError, transaction
from django.utils import timezone

from operaciones import situaciones as svc
from operaciones.deteccion import Senal
from operaciones.situaciones_modelos import (SituacionAfectado,
                                             SituacionOperativa,
                                             SituacionRelacion, TipoAfectado,
                                             TipoEvento, TipoRelacion)

S = SituacionOperativa

#  Cuanto tiempo puede pasar sin ver la señal antes de empezar a verificar. NO es
#  un cierre: es el momento de ir a comprobar. Cuarenta minutos y no cinco porque
#  la fuente mas rapida se consulta cada cinco y su dato puede venir con 2 a 5
#  minutos de retraso -- un umbral corto convertiria cualquier hueco de lectura en
#  "se resolvio".
MINUTOS_SIN_SENAL_PARA_VERIFICAR = 40

#  La ventana en la que dos señales se consideran del mismo momento, para
#  relacionar situaciones por OLT o por zona.
MINUTOS_VENTANA_CORRELACION = 30


def _huella_de(tipo_situacion, dimension, clave) -> str:
    """La misma funcion que 'Senal.huella', para poder buscar sin una señal."""
    return f"{tipo_situacion}|{dimension}:{clave}"


# =============================================================================
#  AGRUPAR  --  una señal a su situacion
# =============================================================================

def agrupar(org, senal: Senal, *, ahora=None, snapshot_id=None) -> dict:
    """
    Abre o actualiza. Devuelve {'situacion', 'creada', 'resultado'}.

    POR QUE 'select_for_update' Y NO SOLO UN 'get'
    ---------------------------------------------
    Porque actualizar una situacion lee y escribe la misma fila (afectados,
    riesgo, evidencia). Dos ciclos sin bloqueo producen la actualizacion perdida
    clasica: los dos leen 12 afectados, los dos escriben 13, y el total queda en
    13 cuando deberian ser 14. Con el bloqueo, el segundo espera y lee lo que el
    primero dejo.
    """
    ahora = ahora or timezone.now()

    #  Una señal que no describe una topologia --la marca de fuente inconclusa--
    #  no abre nada: solo anota en las situaciones vivas que este ciclo no trajo
    #  informacion util.
    if senal.dimension == "fuente":
        return {"situacion": None, "creada": False,
                "resultado": _anotar_inconclusa_en_vivas(org, senal, ahora)}

    huella = senal.huella

    with transaction.atomic():
        viva = (S.objects.select_for_update()
                .filter(org=org, huella=huella, estado__in=S.VIVAS)
                .first())
        if viva is not None:
            resultado = svc.actualizar(viva, senal, ahora=ahora)
            return {"situacion": viva, "creada": False, "resultado": resultado}

    try:
        situacion = svc.abrir(org, senal, ahora=ahora, snapshot_id=snapshot_id)
        return {"situacion": situacion, "creada": True, "resultado": None}
    except IntegrityError:
        #  OTRO CICLO GANO LA CARRERA entre el select y el insert. El indice
        #  unico parcial lo impidio, que es exactamente para lo que esta. Se
        #  vuelve a buscar y se actualiza la que el otro creo: el resultado final
        #  es el mismo que si hubieran llegado en orden.
        with transaction.atomic():
            viva = (S.objects.select_for_update()
                    .filter(org=org, huella=huella, estado__in=S.VIVAS)
                    .first())
            if viva is None:
                #  No deberia pasar: si el insert fallo por la huella, la fila
                #  existe. Si llega aqui es otro IntegrityError --el consecutivo,
                #  por ejemplo-- y hay que dejarlo salir en vez de taparlo.
                raise
            resultado = svc.actualizar(viva, senal, ahora=ahora)
            return {"situacion": viva, "creada": False, "resultado": resultado}


def _anotar_inconclusa_en_vivas(org, senal, ahora) -> dict:
    """
    Una fuente que no concluye se anota en las situaciones vivas de ESA fuente.

    Lo que esto IMPIDE es el error que el bloque nombra con nombre propio: tomar
    un vacio de SmartOLT dentro de su ventana de agregacion como "la red se
    recupero". Las situaciones siguen vivas, su 'senal_vista_en' no avanza, y el
    timeline queda diciendo que ese ciclo no trajo informacion.
    """
    vivas = list(S.objects.filter(org=org, estado__in=S.VIVAS,
                                  fuente_origen=senal.fuente))
    for situacion in vivas:
        svc.anotar_inconclusa(situacion, senal, ahora=ahora)
    return {"anotadas": len(vivas)}


# =============================================================================
#  RELACIONAR  --  lo intermedio y lo debil no se funden, se relacionan
# =============================================================================

def relacionar_por_topologia(org, *, ahora=None) -> int:
    """
    Relaciona situaciones vivas que comparten OLT dentro de la ventana.

    POR QUE RELACIONAR Y NO FUNDIR
    ------------------------------
    Dos PONs de la misma OLT caidos a la vez pueden ser una falla de la OLT o dos
    averias independientes. Fundirlos en una sola situacion afirmaria la primera
    explicacion; dejarlos sueltos esconderia que estan juntos. Una RELACION
    'coincide' dice lo que se midio --comparten OLT y ventana-- sin decidir cual
    de las dos explicaciones es.

    Solo se usa 'coincide', que es automatico. 'explica' necesita una persona.
    """
    ahora = ahora or timezone.now()
    desde = ahora - timezone.timedelta(minutes=MINUTOS_VENTANA_CORRELACION)

    #  Las situaciones de PON vivas, con su OLT sacada de la fila de afectado de
    #  tipo OLT -- que 'deteccion' ya registro. No se vuelve a parsear la clave:
    #  el dato ya esta normalizado en la base.
    por_olt: dict[str, list] = {}
    vivas = (S.objects.filter(org=org, tipo=S.AFECTACION_PON,
                              estado__in=S.VIVAS,
                              actualizada_en__gte=desde)
             .prefetch_related("afectados"))
    for situacion in vivas:
        for af in situacion.afectados.all():
            if af.tipo == TipoAfectado.OLT and af.recuperado_en is None:
                por_olt.setdefault(af.identificador, []).append(situacion)

    creadas = 0
    for olt, grupo in sorted(por_olt.items()):
        if len(grupo) < 2:
            continue
        #  Se relacionan en orden estable para que la relacion no dependa de en
        #  que orden las devolvio la base.
        grupo = sorted(grupo, key=lambda s: (s.detectada_en, str(s.pk)))
        primera = grupo[0]
        for otra in grupo[1:]:
            #  Se pregunta ANTES si ya existia, porque 'relacionar' devuelve la
            #  fila y no dice si la creo. Sin esto el conteo sumaba uno en cada
            #  ciclo aunque la relacion fuera la misma de siempre -- y un numero
            #  que crece sin que pase nada es peor que no tenerlo.
            ya_estaba = SituacionRelacion.objects.filter(
                origen=primera, destino=otra,
                tipo=TipoRelacion.COINCIDE).exists()
            try:
                svc.relacionar(
                    primera, otra, TipoRelacion.COINCIDE,
                    f"comparten la OLT {olt} dentro de una ventana de "
                    f"{MINUTOS_VENTANA_CORRELACION} minutos", ahora=ahora)
            except svc.ErrorSituacion:
                #  Una relacion que no se puede crear no rompe el ciclo: se sigue
                #  con las demas.
                continue
            if not ya_estaba:
                creadas += 1
    return creadas


# =============================================================================
#  TICKETS  --  llegan DESPUES, como evidencia
# =============================================================================

def asociar_tickets(org, *, ahora=None, ventana_minutos=None) -> dict:
    """
    Asocia casos abiertos a la situacion que los explica, si hay evidencia.

    QUE CUENTA COMO EVIDENCIA DE RELACION
    -------------------------------------
    Que el caso apunte a un recurso que la situacion YA tiene registrado como
    afectado. Hoy eso significa el PON: si el caso trae el PON del cliente, y ese
    PON esta afectado en una situacion viva, hay relacion.

    LO QUE NO SE HACE, Y ES LA DECISION MAS IMPORTANTE DE ESTA FUNCION
    ------------------------------------------------------------------
    NO se asocia un caso por estar cerca en el tiempo. Un caso abierto a las 02:20
    puede no tener nada que ver con la caida del PON 3/1/4: puede ser una consulta
    de facturacion. Asociarlo porque coincide la hora inflaria la situacion con
    casos ajenos y haria que el conteo de afectados mienta.

    Por eso un caso SIN el dato que lo ligue a la topologia NO se asocia, y eso se
    registra como insuficiencia en vez de resolverse con una suposicion.

    Y NO SE TOCA EL CASO. Ni 'status', ni asignacion, ni nada: la unica escritura
    es una fila de afectado en la situacion.
    """
    from cases.models import Case

    ahora = ahora or timezone.now()
    ventana = ventana_minutos or (MINUTOS_VENTANA_CORRELACION * 4)
    desde = ahora - timezone.timedelta(minutes=ventana)

    #  Que PON esta afectado en que situacion viva. Una sola consulta.
    pon_a_situacion: dict[str, SituacionOperativa] = {}
    for af in (SituacionAfectado.objects
               .filter(org=org, tipo=TipoAfectado.PON, recuperado_en__isnull=True,
                       situacion__estado__in=S.VIVAS)
               .select_related("situacion")):
        pon_a_situacion.setdefault(af.identificador, af.situacion)

    if not pon_a_situacion:
        return {"asociados": 0, "sin_datos": 0, "revisados": 0}

    asociados, sin_datos, revisados = 0, 0, 0
    casos = Case.objects.filter(org=org, resolved_at__isnull=True,
                                created_at__gte=desde)
    for caso in casos:
        revisados += 1
        pon = _pon_del_caso(caso)
        if not pon:
            #  No hay con que ligarlo. Se cuenta como insuficiencia y NO se
            #  asocia: una suposicion aqui mete casos ajenos en la situacion.
            sin_datos += 1
            continue
        situacion = pon_a_situacion.get(pon)
        if situacion is None:
            continue

        antes = SituacionAfectado.objects.filter(
            situacion=situacion, tipo=TipoAfectado.CASO,
            identificador=str(caso.id)).exists()
        svc.agregar_afectados(
            situacion,
            [{"tipo": TipoAfectado.CASO, "identificador": str(caso.id),
              #  La etiqueta NO lleva el nombre del cliente ni el titulo del
              #  caso: es texto que puede traer PII, y esto termina en una tabla
              #  que se lee desde un tablero.
              "etiqueta": "", "datos": {"pon": pon}}],
            ahora=ahora, fuente="dexter")
        if not antes:
            svc.anotar(situacion, TipoEvento.TICKET_ASOCIADO,
                       f"caso asociado por coincidir el PON {pon}",
                       datos={"caso_id": str(caso.id), "pon": pon},
                       ocurrido_en=ahora)
            asociados += 1

    return {"asociados": asociados, "sin_datos": sin_datos,
            "revisados": revisados}


def _pon_del_caso(caso) -> str:
    """
    El PON del cliente de ese caso, si el dato existe. Cadena vacia si no.

    NO RECONSTRUYE cliente -> ONT -> OLT -> PON: esa relacion la esta corrigiendo
    otro colaborador y rehacerla aqui produciria una segunda version que se
    desincroniza. Lo unico que hace esta funcion es LEER el dato si ya esta
    normalizado en el caso, por el camino que el propio modelo ofrece.

    Hoy busca en 'custom_fields' --donde la importacion deja los datos del
    proveedor que no tienen columna propia-- y en nada mas. Si manana la relacion
    corregida expone el PON en un campo propio, se agrega aqui UNA linea; lo que
    no se hace es inferirlo.
    """
    campos = getattr(caso, "custom_fields", None)
    if isinstance(campos, dict):
        for clave in ("pon", "PON", "pon_puerto", "puerto_pon"):
            valor = campos.get(clave)
            if valor:
                return str(valor).strip()
    return ""


# =============================================================================
#  LA SEÑAL QUE DEJA DE VERSE
# =============================================================================

def revisar_sin_senal(org, *, ahora=None, minutos=None) -> dict:
    """
    Las situaciones cuya señal no se ve hace rato pasan a EN_VERIFICACION.

    NO LAS CIERRA, Y ES EL PUNTO
    ----------------------------
    Que una señal desaparezca tiene dos explicaciones: el problema se resolvio, o
    la fuente dejo de verlo. Cerrar aqui elegiria la primera sin haberla
    comprobado. Lo que se hace es mover a verificacion y anotar que la señal no
    se ve -- cerrar exige que alguien registre QUE comprobo, y la base lo obliga.

    Tampoco se tocan las situaciones cuya ultima lectura fue INCONCLUSA: para esas
    'senal_vista_en' no avanzo justamente porque no habia informacion, y tratarlas
    como "sin señal" castigaria a la situacion por un problema de la fuente.
    """
    ahora = ahora or timezone.now()
    limite = ahora - timezone.timedelta(
        minutes=minutos or MINUTOS_SIN_SENAL_PARA_VERIFICAR)

    movidas = 0
    candidatas = S.objects.filter(
        org=org, estado__in=(S.DETECTADA, S.INVESTIGANDO, S.CONFIRMADA,
                             S.EN_ATENCION),
        senal_vista_en__lt=limite)
    for situacion in candidatas:
        svc.anotar(situacion, TipoEvento.SENAL_AUSENTE,
                   f"la señal no se ve desde {situacion.senal_vista_en:%H:%M}",
                   datos={"desde": situacion.senal_vista_en.isoformat()},
                   ocurrido_en=ahora)
        svc.cambiar_estado(
            situacion, S.EN_VERIFICACION,
            motivo=("la señal dejo de verse; hay que comprobar si se resolvio o "
                    "si la fuente dejo de informarla"),
            ahora=ahora)
        movidas += 1
    return {"a_verificacion": movidas}


# =============================================================================
#  EL CICLO COMPLETO
# =============================================================================

def correr(org, *, ahora=None) -> dict:
    """
    Fuente -> señal -> deteccion -> correlacion -> situacion. Una pasada.

    No duerme, no cicla y no se agenda: la llama el mismo turno del scheduler que
    el sondeo, inmediatamente despues. Por eso una situacion siempre se construye
    sobre la captura mas reciente.

    El informe que devuelve son CONTEOS: lo lee el motor y termina en su log.
    """
    from operaciones import deteccion

    ahora = ahora or timezone.now()
    senales = deteccion.detectar(org, ahora=ahora)

    informe = {"senales": len(senales), "creadas": 0, "actualizadas": 0,
               "inconclusas": 0, "por_tipo": {}}

    for senal in senales:
        if senal.dimension == "fuente":
            informe["inconclusas"] += 1
            agrupar(org, senal, ahora=ahora)
            continue
        salida = agrupar(org, senal, ahora=ahora)
        if salida["creada"]:
            informe["creadas"] += 1
        else:
            informe["actualizadas"] += 1
        clave = senal.tipo_situacion
        informe["por_tipo"][clave] = informe["por_tipo"].get(clave, 0) + 1

    informe["relaciones"] = relacionar_por_topologia(org, ahora=ahora)
    informe["tickets"] = asociar_tickets(org, ahora=ahora)
    informe.update(revisar_sin_senal(org, ahora=ahora))

    #  EL SEGUIMIENTO, EN EL MISMO TURNO. Una situacion no termina porque termino
    #  un ciclo: aqui se evalua como va cada una de las abiertas y, si amerita, se
    #  deja una recomendacion para que la lea una persona.
    #
    #  El proponedor se le PASA al seguimiento en vez de que lo importe: el
    #  seguimiento produce veredictos y no tiene por que conocer las propuestas.
    #  El interprete se pasa por el mismo motivo que el proponedor: el
    #  seguimiento produce veredictos y no tiene por que conocer el cerebro. Con
    #  las banderas apagadas 'interpretar_seguimiento' devuelve la salida tal
    #  cual, y esto es exactamente el seguimiento de antes.
    from operaciones import (situaciones_propuestas, situaciones_seguimiento,
                             supervisor as sup)

    #  EL PRESUPUESTO, o esto se cuelga. El seguimiento NO deduplica: corre
    #  sobre CADA situacion abierta en cada corrida. Sin tope, con el cerebro
    #  encendido, son tantas llamadas al modelo como situaciones vivas haya --
    #  y esto se dispara desde un boton, con una persona esperando.
    #
    #  Se crea aqui y no dentro de 'interpretar_seguimiento' porque un
    #  presupuesto por llamada no acota nada: tiene que ser uno para toda la
    #  corrida.
    presupuesto = sup.presupuesto(ahora=ahora)

    def interpretar(situacion, salida, *, ahora=None):
        return sup.interpretar_seguimiento(
            situacion, salida, ahora=ahora, presupuesto=presupuesto)

    informe["seguimiento"] = situaciones_seguimiento.seguir(
        org, ahora=ahora, proponer=situaciones_propuestas.proponer,
        interpretar=interpretar)
    informe["razonamientos"] = presupuesto["usados"]
    informe["razonamientos_omitidos"] = presupuesto["omitidos"]

    informe["vivas"] = S.objects.filter(org=org, estado__in=S.VIVAS).count()
    return informe
