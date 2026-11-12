# -*- coding: utf-8 -*-
"""
================================================================================
 EL SUPERVISOR REVISA EL CIERRE DEL TECNICO  --  30/10/2026
================================================================================

SPEC/objetivos/revision-del-cierre.md. El usuario: «al momento que el tecnico
envia el reporte final, el supervisor debe revisar si quedo bien y indicar si
lo cierra o no y por que».

INDICA; Y SI SE LE DELEGA, CIERRA POR SU PUERTA
-----------------------------------------------
Esto devuelve un veredicto con sus motivos y no escribe nada. Lo usan dos:
una persona, que lo confirma con un toque en Programacion (y entonces el ticket
del ISP se cierra por la puerta HUMANA del motor); y el Supervisor, si se le
delego la tarea (`campo/cierre_por_el_supervisor.py`), que cierra solo lo que
esto marca «Se puede cerrar» por la puerta AUTONOMA, con sus compuertas. Un
Supervisor por la puerta humana seria una IA usando una puerta que no es la
suya (CLAUDE.md §4).

EN CODIGO, PUNTO POR PUNTO
--------------------------
Cada punto responde si (True), no (False) o no se sabe (None), con su texto:

    checklist     los datos y las fotos obligatorias (`verificar_checklist_completo`)
    reporte       que el tecnico mando el cierre de ESTA vuelta
    servicio      si el tecnico AFIRMO que el servicio quedo funcionando
    medicion      la señal despues del arreglo: si el Supervisor ya la
                  midio, en rango o no; si la orden la espera y todavia no
                  llego, «no se sabe» (auditoria, 30/10/2026: la ausencia no
                  puede contar como aprobacion)
    material      si registro lo que gasto, o confirmo que no gasto nada

El veredicto: algun «no» -> NO SE CIERRA; algun «no se sabe» -> REVISAR; todo
«si» -> SE PUEDE CERRAR. Un punto que no aplica (una plantilla sin la pregunta
del servicio, una orden que no es de falla) no se cuenta.

SE CALCULA, NO SE GUARDA
------------------------
Como `services/salud_seguimiento.py`: la medicion llega hasta una hora despues
del cierre, y un veredicto guardado diria «revisar» cuando ya se sabe.
================================================================================
"""
from __future__ import annotations

CERRAR = "se_puede_cerrar"
REVISAR = "revisar"
NO_CERRAR = "no_cerrar"

TEXTOS = {
    CERRAR: "Se puede cerrar",
    REVISAR: "Revisalo antes de cerrar",
    NO_CERRAR: "No se cierra",
}


def aplica(orden) -> bool:
    """Lo terminado en campo que todavia nadie valido."""
    from campo.models import OrdenTrabajo

    return (orden.estado_operativo == OrdenTrabajo.COMPLETADA_CAMPO
            and orden.estado_validacion in (OrdenTrabajo.PENDIENTE,
                                            OrdenTrabajo.REQUIERE_REVISION))


#: No se pudo saber que ordenes necesitan la medicion: toda medicion que falta
#: es «no se sabe». Distinto de no haberlo preguntado (None).
NO_SE_SABE = "no_se_sabe"


def pendientes_de_medir(org, ahora=None) -> set | None:
    """Los ids de las ordenes terminadas sin validar que NECESITAN la medicion
    despues del arreglo: las de una FALLA DE SERVICIO (el mismo criterio que
    `operaciones/verificacion_de_arreglos.candidatas`), SIN su ventana de 48 h
    ni su «ya no se reintenta» (auditoria de frontera, 30/10/2026: pasada la
    ventana, una falla nunca medida volvia a contar como «no aplica»). None si
    no se pudo saber, y entonces quien cierra solo no cierra nada."""
    from campo.models import OrdenTrabajo
    from operaciones import paso_a_despacho as pad

    try:
        por_caso = {str(caso): str(orden_id) for orden_id, caso in (
            OrdenTrabajo.objects.filter(
                org=org, origen_sistema="crm",
                estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
                estado_validacion__in=(OrdenTrabajo.PENDIENTE,
                                       OrdenTrabajo.REQUIERE_REVISION))
            .values_list("id", "origen_ref"))}
        if not por_caso:
            return set()
        salida = set()
        for p in pad.propuestas_que_llevan_a_despacho(org).filter(
                origen_id__in=list(por_caso)):
            lectura = pad._ultima_lectura_con_grupo(p) or {}
            if (lectura.get("grupo") == pad.FALLA_DE_SERVICIO
                    and lectura.get("accion_autorizada") != pad.SI):
                salida.add(por_caso[str(p.origen_id)])
        return salida
    except Exception:                                            # noqa: BLE001
        return None


def revisar(orden, *, pendientes=None) -> dict | None:
    """El veredicto de UNA orden, o None si no hay nada que revisar.
    `pendientes`: los de `pendientes_de_medir`; sin ellos, una orden sin
    medicion se lee como una que no la necesita."""
    if not aplica(orden):
        return None
    cierre = _cierre_de_esta_vuelta(orden)
    puntos = [p for p in (_checklist(orden), _reporte(cierre), _servicio(cierre),
                          _medicion(orden, pendientes), _material(orden, cierre),
                          _fotos(orden), _potencia(orden, cierre),
                          _en_rango(orden, cierre))
              if p is not None]
    if any(p["ok"] is False for p in puntos):
        veredicto = NO_CERRAR
    elif any(p["ok"] is None for p in puntos):
        veredicto = REVISAR
    else:
        veredicto = CERRAR
    esquema = getattr(orden.tipo_trabajo_version, "esquema", None) or {}
    return {
        "veredicto": veredicto,
        "texto": TEXTOS[veredicto],
        "puntos": puntos,
        #  Lo que una devolucion puede pedir rehacer (`requerir_correccion`
        #  exige nombrarlo), y lo que el checklist ya marca como faltante.
        #
        #  DESDE EL 06/11/2026 CADA UNA DICE QUE DEBIA MOSTRAR Y QUE LLEGO.
        #  El usuario: «el supervisor debe revisar si las fotos coinciden con
        #  lo pedido; si piden foto del router y manda el TV no debe pasar».
        #  Tenia razon y el hueco era de informacion, no de poder: el boton
        #  «Devolver al tecnico» ya existia, pero esta lista mandaba solo el
        #  id y el titulo --sin las instrucciones y sin la imagen--, asi que
        #  no habia con que comparar. Decir «el checklist esta completo» es
        #  contar fotos, no mirarlas.
        "evidencias": _evidencias_para_revisar(orden, esquema),
        "sugeridas": _que_rehacer(puntos, esquema, orden),
        "solucion": _solucion(cierre),
        #  EL OTRO LADO DE LA COMPARACION (12/11/2026). Hasta hoy esto
        #  devolvia lo que el tecnico hizo y nada de lo que se le pidio: no
        #  habia con que compararlo. Ver `el_ticket`.
        "el_ticket": el_ticket(orden),
        "lo_que_el_tecnico_escribio": _lo_que_escribio_el_tecnico(orden,
                                                                 cierre),
    }


def _fotos_que_muestran_otra_cosa(orden) -> list[str]:
    """Los requisitos cuya foto llego pero muestra algo DISTINTO.

    SOLO `MUESTRA: no`, NUNCA «no se sabe»  --  08/11/2026
    ------------------------------------------------------
    El usuario mando a proposito una foto equivocada --un teclado de laptop
    donde se pedia el conector-- y el Supervisor la marco bien, pero no la
    devolvio sola: hubo que apretar el boton. «Deberia mandar automatico el
    Supervisor».

    ESTO REVIERTE EN PARTE UNA DECISION REGISTRADA, y por eso se acota tanto.
    El 31/10/2026 se escribio que «una opinion no verificada de un modelo no
    puede frenar el trabajo de un tecnico», y `_fotos` sigue sin poder decir
    que no. Lo que cambia es mas angosto: cuando el modelo afirma que la foto
    muestra OTRA COSA --la marca `MUESTRA: no`, no «no se sabe»-- esa foto se
    nombra como algo a rehacer.

    LA DIFERENCIA ENTRE LAS DOS MARCAS ES LA QUE SOSTIENE ESTO. «no se sabe»
    es borrosa, tapada, un primer plano del que no se deduce que equipo es:
    ahi el modelo no sabe, y mandar al tecnico de vuelta por eso seria
    hacerlo viajar por una foto que no se pudo leer. «no» es otra cosa: se
    pidio el router y hay un televisor. Esa es verificable mirando, y es la
    que el usuario eligio.

    Decision del usuario del 08/11/2026, tomada con las dos opciones y su
    costo a la vista.
    """
    try:
        from campo.models import AnalisisDeEvidencia
        from campo.tasks import muestra_lo_pedido
    except Exception:                                            # noqa: BLE001
        return []
    #  La ultima por requisito, con la vuelta pesando primero: lo mismo que
    #  en `_evidencias_para_revisar`, y por el mismo caso de la foto
    #  reintentada.
    ultimo = {}
    try:
        for a in (AnalisisDeEvidencia.objects
                  .filter(org=orden.org, evidencia__orden_trabajo=orden)
                  .select_related("evidencia")
                  .order_by("evidencia__vuelta", "created_at")):
            ultimo[a.evidencia.requisito_id] = a
    except Exception:                                            # noqa: BLE001
        return []
    return sorted(r for r, a in ultimo.items()
                  if muestra_lo_pedido(a.texto or "") is False)


def _fotos_de_catalogo(orden) -> list[str]:
    """Los requisitos cuya foto es material de producto, no del trabajo.

    EL CASO, MEDIDO  --  09/11/2026
    --------------------------------
    El usuario subio como evidencia la foto de catalogo de un medidor Rouhan
    --el equipo recortado sobre fondo blanco, de una tienda-- en las dos
    mediciones de una orden. El modelo lo vio y lo escribio las dos veces:
    «Equipo sobre fondo blanco, sin entorno de instalacion; imagen de
    catalogo».

    Y la orden paso igual. `MUESTRA` decia `si` --el medidor SE VE, y eso era
    lo que se pedia-- y `ATENCION: si` por si solo no devuelve nada desde la
    decision del 06/11: «4 de 4 fotos piden una mirada» sobre fotos oscuras
    de un trabajo bien hecho, y devolver por eso haria rehacer lo que no esta
    mal.

    POR QUE ESTA SI DEVUELVE, Y «ATENCION» NO. Son dos afirmaciones de
    distinto peso. «Pide una mirada» es un juicio difuso sobre la calidad de
    una foto. «Es material de producto» es un hecho sobre su ORIGEN: esa
    imagen no se tomo en la casa del cliente, asi que no es evidencia de
    nada, por nitida que sea. Es el mismo criterio con el que `MUESTRA: no`
    devuelve: lo verificable mirando.

    Y SE REPITE. La misma marca salio en las dos fotos de la prueba, en dos
    analisis independientes.

    Sin marca, no devuelve: ver `es_de_catalogo`.
    """
    try:
        from campo.models import AnalisisDeEvidencia
        from campo.tasks import es_de_catalogo
    except Exception:                                            # noqa: BLE001
        return []
    ultimo = {}
    try:
        for a in (AnalisisDeEvidencia.objects
                  .filter(org=orden.org, evidencia__orden_trabajo=orden)
                  .select_related("evidencia")
                  .order_by("evidencia__vuelta", "created_at")):
            ultimo[a.evidencia.requisito_id] = a
    except Exception:                                            # noqa: BLE001
        return []
    return sorted(r for r, a in ultimo.items()
                  if es_de_catalogo(a.texto or "") is True)


def _que_rehacer(puntos, esquema, orden=None) -> list[str]:
    """Los requisitos que una devolucion puede pedir que se rehagan.

    POR QUE EL RANGO ENTRA ACA  --  07/11/2026
    -------------------------------------------
    Hasta hoy esta lista era solo lo que el checklist marca como faltante, y
    una medida fuera de rango no frenaba ni devolvia: quedaba esperando a una
    persona. El usuario pidio que se devuelva.

    Y ESO EXIGIA NOMBRAR QUE REHACER, no saltear la regla que lo impedia.
    `atender_la_que_no_cierra` no devuelve lo que falla «sin un requisito
    concreto», y tiene su motivo medido: cuando el punto que falla es
    «servicio», el tecnico puede necesitar material, un tercero o que alguien
    decida, y mandarselo de vuelta es devolverle un problema que no es suyo.

    El rango SI tiene algo concreto que pedir --volver a medir y mandar la
    foto de la pantalla-- asi que deja de ser ese caso en vez de esquivarlo.

    SOLO SI LA PLANTILLA LO DECLARA. Pedir un requisito que el formulario no
    tiene le deja al tecnico una devolucion que no puede cumplir, y lo
    dejaria dando vueltas. Sin esa foto declarada, la orden sigue esperando a
    una persona, que es lo que hacia hasta hoy.
    """
    faltan = next((p["faltan"] for p in puntos if p["clave"] == "checklist"), [])
    salida = [str(x).strip() for x in (faltan or []) if str(x).strip()]
    fuera_de_rango = any(p.get("clave") == "rango" and p.get("ok") is False
                         for p in puntos)
    if fuera_de_rango:
        declarada = any(isinstance(e, dict) and e.get("id") == REQUISITO_AL_SALIR
                        for e in (esquema or {}).get("evidencias") or [])
        if declarada and REQUISITO_AL_SALIR not in salida:
            salida.append(REQUISITO_AL_SALIR)

    #  Y LA MEDICION CUYO NUMERO NO CUADRA CON LA FOTO  --  09/11/2026
    #
    #  El usuario, probando con una orden nueva: «escribi unos niveles
    #  diferentes en la foto y vio el error pero no la devolvio». Y era
    #  cierto las dos veces: el punto `potencia` lo decia con los dos numeros
    #  en la mano, y esta lista no tenia nada que pedir, asi que
    #  `atender_la_que_no_cierra` salia por su `if not requisitos`.
    #
    #  EL PUNTO SIGUE VALIENDO None, NUNCA False, y eso no cambia: la regla
    #  del 31/10 --una lectura que un modelo hizo de una pantalla
    #  fotografiada no frena a un tecnico-- es sobre el VEREDICTO. Esto es
    #  otra cosa: nombrar algo concreto que rehacer. Es exactamente el mismo
    #  camino que ya recorren las fotos con «MUESTRA: no», cuyo punto
    #  tampoco puede decir que no y aun asi se piden.
    #
    #  LO QUE PROTEGE DE UNA MALA LECTURA DEL MODELO, y por eso alcanza:
    #  `_lectura_creible` descarta lo que el tecnico no habria podido
    #  escribir --el «-2.10» que en realidad era «-21.0» sale por ahi-- y
    #  `PF.comparar` perdona hasta 3 dBm. Lo que queda es una pantalla que se
    #  leyo bien y un numero que no salio de ella.
    declaradas = {e.get("id") for e in (esquema or {}).get("evidencias") or []
                  if isinstance(e, dict) and e.get("id")}
    for p in puntos:
        if p.get("clave") != "potencia":
            continue
        for requisito in p.get("rehacer") or []:
            #  SOLO SI LA PLANTILLA LA DECLARA, igual que el rango y las
            #  fotos de abajo: una devolucion que pide algo que el formulario
            #  no tiene deja al tecnico dando vueltas sin poder cumplirla.
            if requisito in declaradas and requisito not in salida:
                salida.append(requisito)

    #  Y LAS FOTOS QUE MUESTRAN OTRA COSA. Ver `_fotos_que_muestran_otra_cosa`
    #  para por que solo esas y no las que el modelo no supo leer.
    if orden is not None:
        for requisito in _fotos_que_muestran_otra_cosa(orden):
            #  Solo lo que la plantilla declara: pedir rehacer algo que el
            #  formulario no tiene deja al tecnico sin poder cumplirlo. Mismo
            #  criterio que con la foto de la medicion.
            if requisito in declaradas and requisito not in salida:
                salida.append(requisito)

        #  Y LAS QUE SON MATERIAL DE PRODUCTO. Ver `_fotos_de_catalogo`: no es
        #  un juicio sobre la calidad de la foto sino sobre su ORIGEN. Una
        #  imagen bajada de una tienda no es evidencia de nada.
        for requisito in _fotos_de_catalogo(orden):
            if requisito in declaradas and requisito not in salida:
                salida.append(requisito)
    return salida


def _evidencias_para_revisar(orden, esquema) -> list[dict]:
    """Cada requisito de la plantilla con lo que pedia y lo que llego.

    QUE SE MANDA Y POR QUE:

    - `instrucciones`: lo que esa foto TENIA que mostrar, escrito por la
      empresa en la plantilla. Sin esto el supervisor compara contra un
      titulo de tres palabras y no puede saber si «Medicion al llegar» es el
      medidor o el televisor.
    - `evidencia_id`: con que ver la imagen. La ruta ya existe
      (`campo/evidencias/<id>/archivo/`), y esta lista no la arma: manda el
      id y quien dibuja decide si la pide. Una respuesta de revision no
      carga megabytes de fotos.
    - `analisis`: lo que la IA vio, si lo vio. Va como TEXTO y como
      `pide_atencion`, nunca como un veredicto: la IA puede pedir atencion y
      nunca negar un cierre (ver el encabezado de `inspeccion_visual.py`,
      decidido el 31/10/2026).

    LAS QUE FALTAN TAMBIEN SALEN, con `evidencia_id` en None. Una foto que no
    llego es justamente la que hay que mirar, y si desapareciera de la lista
    el supervisor veria menos filas sin notar cual.

    LA ULTIMA DE CADA REQUISITO, VENGA DE LA VUELTA QUE VENGA  --  08/11/2026
    ------------------------------------------------------------------------
    Decia «solo la vuelta que corre» y era una tercera regla, distinta de la
    que usa el checklist. El usuario lo vio probando una devolucion: se le
    pidieron al tecnico DOS fotos, las rehizo, y la revision mostro las otras
    dos --las que nadie le pidio tocar-- como «No llego», mientras arriba
    decia «El checklist esta completo: datos y fotos».

    La regla buena ya existia en `services/validador.py`: un requisito que NO
    se pidio rehacer se satisface con la evidencia de CUALQUIER vuelta, y uno
    que SI se pidio exige una nueva. Aca se copia la primera mitad -- mostrar
    la ultima que llego-- y la segunda la sigue haciendo cumplir el checklist,
    que es quien dice «hace falta evidencia nueva, de esta vuelta».

    Asi que un tecnico que no rehizo lo que le pidieron no pasa igual: lo
    frena el punto del checklist, no una foto que desaparece de la lista.
    """
    from campo.models import AnalisisDeEvidencia, EvidenciaTrabajo
    from campo.tasks import muestra_lo_pedido

    #  LA VUELTA PESA PRIMERO, Y DESPUES LA FECHA  --  08/11/2026
    #
    #  Lo caza `test_f8_una_foto_VIEJA_que_llega_tarde_no_gana`, que existe
    #  desde el 06/11 por un caso real: la app ENCOLA las fotos y reintenta,
    #  asi que una de la vuelta 1 que se reintento puede entrar al servidor
    #  DESPUES de la de la vuelta 2. Ordenar solo por `recibida_en_servidor`
    #  la dejaria ultima, y es justo la que el supervisor ya rechazo.
    #
    #  Con `vuelta` adelante se cumplen las dos cosas a la vez: la rehecha
    #  gana siempre --aunque haya llegado antes-- y la que nadie pidio
    #  rehacer sigue siendo la evidencia de su requisito.
    llegaron = {}
    for ev in EvidenciaTrabajo.objects.filter(
            org=orden.org,
            orden_trabajo=orden).order_by("vuelta", "recibida_en_servidor"):
        llegaron[ev.requisito_id] = ev

    #  Lo que la IA vio, por evidencia. Una sola consulta, no una por foto.
    #  SIN FILTRAR POR VUELTA tampoco: si la foto que se muestra es de la
    #  vuelta anterior, su analisis tambien lo es, y filtrarlo la dejaria sin
    #  lo que la IA vio -- que es justo la mitad util de esta lista.
    visto = {}
    for a in AnalisisDeEvidencia.objects.filter(
            org=orden.org,
            evidencia__orden_trabajo=orden).order_by("created_at"):
        #  La ULTIMA gana: una correccion de una persona es una fila nueva y
        #  posterior, y es la que vale.
        visto[str(a.evidencia_id)] = a

    salida = []
    for e in esquema.get("evidencias", []):
        if not e.get("id"):
            continue
        ev = llegaron.get(e["id"])
        a = visto.get(str(ev.id)) if ev else None
        salida.append({
            "id": e["id"],
            "titulo": e.get("titulo") or e["id"],
            #  Lo que tenia que mostrar. Es la mitad de la comparacion.
            "instrucciones": str(e.get("instrucciones") or ""),
            "obligatoria": e.get("obligatorio", True),
            #  Y la otra mitad: con que ver lo que llego.
            "evidencia_id": str(ev.id) if ev else None,
            "analisis": (a.texto or "") if a else "",
            "pide_atencion": bool(a.pide_atencion) if a else False,
            #  SI LA FOTO ES LO QUE SE PIDIO (06/11/2026): True / False /
            #  None, y `None` significa "no se sabe", no "esta bien". Se
            #  calcula del texto y NO se persiste: `AnalisisDeEvidencia` es
            #  append-only y volver a leer el mismo texto con el criterio de
            #  hoy es lo correcto -- mismo motivo por el que
            #  `revision_del_cierre` no persiste su veredicto.
            "muestra_lo_pedido": muestra_lo_pedido(a.texto) if a else None,
        })
    return salida


#: La foto de la revision al aprobar (`guardar_foto`).
FOTO = "revision_al_aprobar"


def guardar_foto(orden, revision, profile=None) -> None:
    """Deja en la bitacora de la orden lo que decia la revision al aprobarla
    (30/10/2026, la pestaña Cerradas): despues de aprobada ya no se revisa, y
    recalcularla diria otra cosa. Sin revision (una orden que no la tenia),
    no se guarda nada."""
    from campo.models import EventoTrabajo

    if not revision:
        return
    EventoTrabajo.objects.create(
        org=orden.org, orden=orden, tipo=FOTO, profile=profile,
        datos={"veredicto": revision["veredicto"], "texto": revision["texto"],
               "puntos": [{"clave": p["clave"], "ok": p["ok"], "texto": p["texto"]}
                          for p in revision["puntos"]],
               "solucion": revision.get("solucion", "")})


def _punto(clave, ok, texto, **extra) -> dict:
    return {"clave": clave, "ok": ok, "texto": texto, **extra}


def _fotos(orden):
    """Lo que la IA vio en las fotos de evidencia  --  31/10/2026.

    EL SEXTO PUNTO, Y EL UNICO QUE NO PUEDE DECIR QUE NO. Vale `True` o
    `None`, nunca `False`, y eso no es una omision: la linea de mas abajo
    convierte cualquier `False` en NO_CERRAR, y ese veredicto ademas alimenta
    el cierre autonomo del Supervisor. Una opinion no verificada de un modelo
    no puede frenar el trabajo de un tecnico.

    `None` ya significa REVISAR --"miralo vos"--, que es todo el alcance que
    corresponde: la IA pide atencion, nunca niega un cierre (CLAUDE.md §4).
    Si esta empresa no lo tiene encendido, el punto NO APARECE y la revision
    queda exactamente como antes. Ver `campo/inspeccion_visual.py`.

    NO TUMBA LA REVISION: un fallo aca devuelve None, no una excepcion. La
    revision del cierre ya corre en produccion y decide si una orden se
    cierra; algo que se agrega no puede romper lo que ya funcionaba.
    """
    try:
        from campo.inspeccion_visual import punto_de_la_revision

        p = punto_de_la_revision(orden)
    except Exception:                                            # noqa: BLE001
        return None
    #  LA GUARDA, en el consumidor y no solo en quien lo produce: si alguna
    #  vez alguien devolviera False desde alla, acá no pasa igual.
    if p is None or p.get("ok") is False:
        return None
    return p


#:  COMO SE LLAMAN LOS CAMPOS DE POTENCIA EN LA PLANTILLA.
#:
#:  EN UN SOLO LUGAR, y no repartidos por tres funciones: el dia que una
#:  empresa los llame distinto, cambiarlos en dos de los tres sitios deja un
#:  punto que calla sin decir por que.
CAMPO_AL_LLEGAR = "potencia_al_llegar"
CAMPO_AL_SALIR = "potencia_al_salir"

#:  La foto que respalda la medida al salir: la pantalla del medidor.
#:  Es lo que se le pide rehacer cuando esa medida quedo fuera de rango
#:  y ninguna lectura del equipo la contradice.
REQUISITO_AL_SALIR = "medicion_al_salir"


def _potencia_de_la_foto_al_salir(orden):
    """El dBm que el modelo leyo en la foto del medidor AL SALIR, o `None`.

    La tercera lectura. El usuario la pidio junto con la del equipo --«y
    tambien debe comparar la foto del ticket»-- y es la que desempata: si la
    foto marca lo mismo que el equipo, lo que sobra es el numero escrito; si
    marca lo mismo que el escrito, lo que hay que mirar es el equipo.

    `None` cuando no hay foto analizada, o cuando el modelo leyo mas de un
    nivel en ella: elegir uno seria inventar la mitad del dato
    (`potencia_de_la_foto.uno_solo`).
    """
    try:
        from campo import potencia_de_la_foto as PF

        return PF.uno_solo(_texto_de_la_foto(orden, "medicion_al_salir"))
    except Exception:                                            # noqa: BLE001
        return None


def _lo_que_el_tecnico_PODRIA_escribir(orden, campo_id):
    """`(piso, techo)` de ese campo segun la plantilla, o `None`.

    NO ES EL RANGO SANO: es `min`/`max`, lo que el formulario acepta. Rapilink
    declaro -60 a -8. Sirve para otra cosa y por eso se lee aparte.
    """
    esquema = getattr(orden.tipo_trabajo_version, "esquema", None) or {}
    campo = next((c for c in (esquema.get("campos") or [])
                  if isinstance(c, dict) and c.get("id") == campo_id), None)
    reglas = (campo or {}).get("reglas") or {}
    mn, mx = _a_numero(reglas.get("min")), _a_numero(reglas.get("max"))
    if mn is None or mx is None:
        #  SI ESTE CAMPO NO LOS DECLARA, SIRVEN LOS DEL OTRO  --  08/11/2026
        #
        #  Medido en produccion: `potencia_al_llegar` no declara limites --su
        #  regla es solo `required: False`, porque al llegar puede no haber
        #  señal-- asi que el filtro no filtraba nada ahi y el punto salto con
        #  «la foto marca -5.0 dBm y el reporte dice -50.0: 45.0 de
        #  diferencia». El arreglo cubria al salir y no al llegar.
        #
        #  Los dos campos son LA MISMA MEDICION: el mismo instrumento sobre el
        #  mismo equipo, en dos momentos. Si la empresa declaro que al salir se
        #  escribe entre -60 y -8, una lectura de -5 en la foto de llegada
        #  tampoco puede ser de esa pantalla. No se inventa un rango: se usa el
        #  que la empresa ya declaro para la otra mitad de la misma medicion.
        otro = CAMPO_AL_SALIR if campo_id == CAMPO_AL_LLEGAR else CAMPO_AL_LLEGAR
        if campo_id in (CAMPO_AL_LLEGAR, CAMPO_AL_SALIR):
            gemelo = next((c for c in (esquema.get("campos") or [])
                           if isinstance(c, dict) and c.get("id") == otro), None)
            r2 = (gemelo or {}).get("reglas") or {}
            mn, mx = _a_numero(r2.get("min")), _a_numero(r2.get("max"))
        if mn is None or mx is None:
            return None
    return min(mn, mx), max(mn, mx)


#: Que campo del formulario verifica cada foto de medicion. El mapeo ya
#: estaba repartido en `_potencia` y en el diagnostico; se nombra una vez.
FOTO_DEL_CAMPO = {"medicion_al_llegar": CAMPO_AL_LLEGAR,
                  "medicion_al_salir": CAMPO_AL_SALIR}


def limites_de_la_foto(orden, requisito_id: str):
    """`(piso, techo)` que la empresa declaro para la medicion de ESA foto, o
    `None` si esa foto no es de medicion o la plantilla no los declara.

    PARA QUE SE EXPONE  --  11/11/2026, OT #201
    --------------------------------------------
    Hasta hoy este rango servia solo para DESCARTAR, despues de que el modelo
    leyera. `inspeccion_visual` lo usa ahora ANTES, en el pie de la foto: ver
    `que_tenia_que_mostrar`.
    """
    campo_id = FOTO_DEL_CAMPO.get(requisito_id)
    if not campo_id:
        return None
    return _lo_que_el_tecnico_PODRIA_escribir(orden, campo_id)


def _lectura_creible(valor, limites):
    """Si ese numero puede ser la medicion que se pidio.

    EL MODELO LE CORRE LA COMA  --  08/11/2026
    -------------------------------------------
    Medido en tres ordenes seguidas (186, 198 y 204): la pantalla del medidor
    dice -21.0 dBm y el analisis leyo -2.10 dBm, las dos veces, en los dos
    momentos. El usuario lo confirmo mirando la foto. El tecnico escribe bien;
    lo que falla es la lectura.

    Y el punto que compara las dos cosas saltaba en TODAS las ordenes. Un «?»
    que aparece siempre enseña a ignorarlo, que es exactamente lo que el
    encabezado de `_potencia` dice que hay que evitar.

    EL LIMITE SALE DE LA PLANTILLA, no de una constante nueva. La empresa ya
    declaro que acepta de -60 a -8 en ese campo: un -2.10 esta fuera de lo que
    un tecnico siquiera PODRIA escribir, asi que no es la medicion de esa
    pantalla y no sirve para compararla. Varia por empresa y por tipo de
    trabajo, y ya esta donde tiene que estar (CLAUDE.md §3.3).

    SIN LIMITES DECLARADOS NO SE FILTRA NADA: se prefiere una comparacion de
    mas a decidir por una empresa que no dijo nada.
    """
    if valor is None or limites is None:
        return valor is not None
    piso, techo = limites
    return piso <= valor <= techo


def _lecturas_de_la_foto(orden, requisito_id: str) -> list[str]:
    """TODOS los textos que la IA escribio sobre esa foto, del mas viejo al
    mas nuevo. Solo los que dicen algo: una fila sin texto es un intento que
    fallo, no una lectura.

    POR QUE HACEN FALTA TODAS, Y NO LA ULTIMA  --  11/11/2026
    ---------------------------------------------------------
    `_texto_de_la_foto` devuelve una --la ultima-- y para DESCRIBIR alcanza.
    Para sacar un NUMERO no: dos lecturas que dan el mismo numero son una
    lectura confirmada, y dos que dan numeros distintos no son ninguna. Ese
    es el unico control que existe sobre lo que el modelo lee de una
    pantalla, porque no hay segundo instrumento con que comparar.

    DE UNA SOLA EVIDENCIA, la mas reciente de ese requisito. Las lecturas de
    la foto que el tecnico rehizo no se mezclan con las de la que reemplazo:
    son dos pantallas distintas y coincidir entre ellas no probaria nada.
    """
    from campo.models import AnalisisDeEvidencia

    ultima = (AnalisisDeEvidencia.objects
              .filter(org=orden.org, evidencia__orden_trabajo=orden,
                      evidencia__requisito_id=requisito_id)
              #  La vuelta primero, por lo mismo que `_texto_de_la_foto`.
              .order_by("-vuelta", "-created_at").first())
    if ultima is None:
        return []
    textos = (AnalisisDeEvidencia.objects
              .filter(org=orden.org, evidencia_id=ultima.evidencia_id)
              .order_by("created_at").values_list("texto", flat=True))
    return [t for t in textos if (t or "").strip()]


def _numero_de_la_foto(textos, limites):
    """`(valor, discordaron)`: el dBm que esa foto muestra, o `None`.

    LA DOBLE LECTURA  --  11/11/2026, pedido del usuario
    -----------------------------------------------------
    El usuario, despues de ver la OT #200 cerrar con la medicion de salida
    sin verificar: «o si mejor ese datos llene la app con la lectura que toma
    de la foto». La precondicion de eso --y el problema de fondo de los
    cinco bugs de esta semana-- es que la lectura del modelo no es confiable:
    le corre el punto decimal y lee «-2.10» donde la pantalla dice «-21.0».
    Medido 3 de cada 7 veces el 10/11, y otra vez el 11/11 en la misma foto.

    Una lectura sola no tiene con que validarse. Dos si:

      · un solo valor creible  ->  ese es el numero
      · dos valores creibles distintos  ->  NO HAY numero (`discordaron`)
      · ninguno creible  ->  no hay numero, y no es discordancia: es el
        descarte que ya existia (ver `_lectura_creible`)

    POR QUE NO SE PROMEDIA NI SE ELIGE UNA. Promediar «-2.10» con «-21.0» da
    un numero que ninguna pantalla mostro, y elegir la que convenga es
    inventar la mitad del juicio -- el mismo motivo por el que `PF.uno_solo`
    no elige entre dos lecturas de un mismo texto.

    UNA SOLA LECTURA CREIBLE SIGUE VALIENDO, y es deliberado: el tecnico ya
    escribio su propio numero, asi que cuando los dos coinciden hay dos
    fuentes independientes de acuerdo y no hace falta pagar una tercera. La
    segunda lectura se pide donde hace falta --ver `mediciones_para_releer`--
    y no en toda foto, que duplicaria el costo del analisis entero para
    confirmar lo que ya estaba confirmado.
    """
    from campo import potencia_de_la_foto as PF

    creibles = []
    for t in textos:
        v = PF.uno_solo(t)
        if v is None or not _lectura_creible(v, limites):
            continue
        if v not in creibles:
            creibles.append(v)
    if len(creibles) == 1:
        return creibles[0], False
    return None, len(creibles) > 1


def mediciones_para_releer(orden, cierre=None) -> list[str]:
    """Los requisitos de foto de medicion cuya lectura conviene volver a
    pedirle al modelo. Solo lee; quien la vuelve a mirar es
    `campo.tasks.mirar_las_que_faltan`, que es quien puede escribir.

    CUANDO SE GASTA UNA SEGUNDA LECTURA: cuando la primera va a tener
    consecuencia y no se sostiene sola.

      · no se leyo ningun numero  ->  eso DEVUELVE la orden (`ilegibles`), y
        mandar a un tecnico de vuelta por un fallo de lectura del modelo es
        el viaje mas caro que este sistema puede causar
      · el numero no es creible, o las lecturas discordaron  ->  la medicion
        queda sin verificar, que es como cerro la OT #200
      · el numero no coincide con lo escrito  ->  eso tambien DEVUELVE la
        orden, y conviene estar seguro antes

    Y CUANDO NO: cuando el numero creible coincide con el del tecnico. Ahi ya
    hay dos fuentes independientes de acuerdo --su medidor y la foto-- y una
    tercera lectura no agrega nada que no se sepa.

    SIN NUMERO ESCRITO TAMBIEN SE RELEE si la foto no deja leer nada: la
    devolucion por foto ilegible no depende de que el tecnico haya escrito.

    EL TOPE DE INTENTOS NO VIVE ACA. Lo aplica `mirar_las_que_faltan` con
    `INTENTOS_POR_FOTO`, contando filas: una foto que el modelo lee mal tres
    veces deja de releerse y espera a una persona.
    """
    from campo import potencia_de_la_foto as PF

    if cierre is None:
        cierre = _cierre_de_esta_vuelta(orden)
    if cierre is None:
        return []
    respuestas = _lo_que_escribio_el_tecnico(orden, cierre)
    declaradas = {e.get("id") for e in
                  ((getattr(orden.tipo_trabajo_version, "esquema", None)
                    or {}).get("evidencias") or [])
                  if isinstance(e, dict) and e.get("id")}
    #  LOS CAMPOS QUE LA PLANTILLA DECLARA, no solo las fotos  --  11/11
    #
    #  SIN CAMPO DE POTENCIA NO SE RELEE NADA, y lo encontro una guarda
    #  ajena: `test_las_fotos_se_miran_antes_de_decidir` arma su orden con
    #  `"campos": []` --declara las tres fotos y ningun campo-- y sus siete
    #  casos se pusieron en rojo porque esta funcion pedia releer las dos
    #  fotos de medicion en cada pasada. Eran guardas de COSTO: «no se le
    #  paga dos veces al modelo».
    #
    #  Y tenian razon. Una segunda lectura solo sirve si hay con que
    #  CONTRASTARLA: el numero que el tecnico escribio. Donde la plantilla
    #  no tiene ese campo, el formulario nunca va a traerlo, y releer la
    #  foto hasta agotar el tope no puede cambiar nada -- es gasto puro, en
    #  toda orden abierta de esa plantilla y en cada pasada del ciclo.
    campos_declarados = {c.get("id") for c in
                         ((getattr(orden.tipo_trabajo_version, "esquema", None)
                           or {}).get("campos") or [])
                         if isinstance(c, dict) and c.get("id")}
    salida = []
    for campo, requisito, _cuando in ((CAMPO_AL_LLEGAR, "medicion_al_llegar",
                                       "al llegar"),
                                      (CAMPO_AL_SALIR, "medicion_al_salir",
                                       "al salir")):
        if requisito not in declaradas or campo not in campos_declarados:
            continue
        textos = _lecturas_de_la_foto(orden, requisito)
        if not textos:
            #  Nadie la miro todavia. La mira `mirar_las_que_faltan` por su
            #  camino de siempre; releer no es lo que falta aca.
            continue
        #  SI EL MODELO YA SE REPITIO, NO SE RELEE MAS  --  11/11, OT #201
        #
        #  Esa foto se miro CUATRO veces y las cuatro leyeron «-2.10». El
        #  tope de 3 existe para un fallo transitorio de red; esto es otra
        #  cosa: el modelo es CONSISTENTE leyendo mal, y una lectura mas no
        #  va a decir algo distinto. Dos lecturas iguales ya contestaron la
        #  pregunta que la tercera venia a hacer.
        crudos = [v for v in (PF.uno_solo(t) for t in textos) if v is not None]
        if len(crudos) >= 2 and crudos[-1] == crudos[-2]:
            continue
        limites = _lo_que_el_tecnico_PODRIA_escribir(orden, campo)
        valor, _discordaron = _numero_de_la_foto(textos, limites)
        if valor is None:
            salida.append(requisito)
            continue
        escrito = _a_numero(respuestas.get(campo))
        if escrito is None:
            continue
        if PF.comparar(valor, escrito)[0] is False:
            salida.append(requisito)
    return salida


def _pieza_de_medicion(orden):
    """Lo que el Supervisor midio CONTRA EL EQUIPO para esta orden, o `None`.

    Se extrajo de `_medicion` el 07/11/2026 porque ahora la necesitan dos
    puntos: el que la reporta y el del rango, que desde hoy le cede la
    palabra. Una sola consulta escrita una sola vez.
    """
    from operaciones.models import PropuestaSupervisor
    from operaciones.verificacion_de_arreglos import FUENTE

    propuesta = (PropuestaSupervisor.objects
                 .filter(org=orden.org,
                         evidencia__contains=[{"fuente": FUENTE,
                                               "orden": str(orden.id)}])
                 .order_by("-updated_at").first())
    if propuesta is None:
        return None
    return next((p for p in reversed(propuesta.evidencia or [])
                 if isinstance(p, dict) and p.get("fuente") == FUENTE
                 and p.get("orden") == str(orden.id)), None)


def _lo_que_escribio_el_tecnico(orden, cierre) -> dict:
    """El formulario del trabajo, de donde de verdad vive.

    DOS LUGARES, Y NO ES CAPRICHO  --  07/11/2026
    ----------------------------------------------
    Los campos que el tecnico llena --«Potencia al salir», «Que encontro»--
    se guardan en `OrdenTrabajo.datos`, validados contra el esquema. El
    evento de cierre lleva en `datos["respuestas"]` lo que se mando EN ESE
    MOMENTO: `solucion`, `servicio_validado`. Son dos cosas distintas y
    hasta hoy este archivo leia solo la segunda.

    MEDIDO EN LA OT #185 (07/11/2026, produccion). El tecnico escribio -35.0
    dBm al salir, la nota del ticket lo mostraba --`cierre_en_isp.resumen_de`
    lee `orden.datos`-- y el punto del rango no aparecia:

        respuestas pot: {}
        punto rango   : None
        punto potencia: None

    Las 37 guardas de ese bloque estaban en verde porque el andamiaje ponia
    la potencia en `cierre.datos["respuestas"]`. La prueba confirmaba la
    suposicion de quien la escribio, no la forma del dato real. Por eso la
    guarda nueva arma la orden como produccion la tiene: el evento SIN
    potencia y `orden.datos` CON ella.

    GANA `orden.datos`, que es el formulario de registro --el mismo que el
    ticket del ISP imprime--; el evento queda de respaldo para lo que solo
    vive ahi.
    """
    salida = {}
    if cierre is not None:
        salida.update((cierre.datos or {}).get("respuestas") or {})
    for clave, valor in (getattr(orden, "datos", None) or {}).items():
        if valor not in (None, ""):
            salida[clave] = valor
    return salida


def _potencia(orden, cierre):
    """La potencia que muestra la FOTO contra la que ESCRIBIO el tecnico.

    POR QUE  --  07/11/2026
    -----------------------
    El usuario, mirando la inspeccion de «Medicion al llegar» en la OT #187:
    el modelo habia leido «la pantalla se lee: 1310 nm, "Lo" y -70.00 dBm» --
    el dato mas importante de esa foto, porque «Lo» es perdida de senal -- y
    ese numero moria en un parrafo. Mientras tanto el tecnico escribe su
    propia lectura en `potencia_al_llegar`, y nadie cruzaba las dos.

    COMO EL PUNTO DE LAS FOTOS, VALE `True` O `None`, NUNCA `False`. Un
    `False` se convierte en NO_CERRAR y ademas alimenta el cierre autonomo
    del Supervisor: una lectura que un modelo hizo de una pantalla
    fotografiada no puede frenar el trabajo de un tecnico. Cuando no
    coinciden, el punto queda en `None` --«miralo vos»-- con los dos numeros
    escritos, que es lo que permite decidir a quien mira.

    NO APARECE cuando no hay con que comparar: una plantilla sin campo de
    potencia, un cierre sin numero, o una foto que el modelo no supo leer. Un
    punto que siempre dice «no se sabe» entrena a ignorarlo.
    """
    try:
        from campo import potencia_de_la_foto as PF

        if cierre is None:
            return None
        respuestas = _lo_que_escribio_el_tecnico(orden, cierre)
        #  LOS DOS MOMENTOS, en el orden en que pasan. El de llegada es el que
        #  el usuario señalo; el de salida es el que dice si el arreglo sirvio,
        #  asi que si estan los dos se miran los dos y gana la peor noticia.
        pares = ((CAMPO_AL_LLEGAR, "medicion_al_llegar", "al llegar"),
                 (CAMPO_AL_SALIR, "medicion_al_salir", "al salir"))
        declaradas = {e.get("id") for e in
                      ((getattr(orden.tipo_trabajo_version, "esquema", None)
                        or {}).get("evidencias") or [])
                      if isinstance(e, dict) and e.get("id")}
        dudas, vistos, rehacer, sin_mirar, ilegibles = [], 0, [], [], []
        sin_analizar, verificadas, discordantes = [], [], []
        for campo, requisito, cuando in pares:
            escrito = _a_numero(respuestas.get(campo))
            #  TODAS LAS LECTURAS DE ESA FOTO, no la ultima  --  11/11/2026
            #
            #  Ver `_numero_de_la_foto`: el numero vale si DOS lecturas lo
            #  dicen, o si una sola lo dice y es creible. Lo que no vale es
            #  una lectura creible contra otra creible distinta, y hasta hoy
            #  este punto no podia ni enterarse: leia una fila.
            lecturas = _lecturas_de_la_foto(orden, requisito)
            texto_foto = lecturas[-1] if lecturas else ""
            limites = _lo_que_el_tecnico_PODRIA_escribir(orden, campo)
            #  LOS NUMEROS CRUDOS, antes de filtrar por creible: distinguen
            #  «la foto no deja leer un dBm» --que devuelve la orden-- de
            #  «se leyo algo que no puede salir de ese medidor», que no.
            crudos = [v for v in (PF.uno_solo(t) for t in lecturas)
                      if v is not None]
            de_la_foto, discordaron = _numero_de_la_foto(lecturas, limites)

            #  LA FOTO QUE TODAVIA NADIE MIRO  --  10/11/2026, OT #200
            #
            #  EL CASO, MEDIDO EN VIVO. El usuario escribio -18.0 al salir y
            #  la pantalla marcaba -21.0. El panel mostro, en la misma
            #  tarjeta: «? Revisá las fotos: 1 no se pudieron mirar» Y
            #  «✓ La potencia que muestra la foto coincide con la que reportó
            #  el tecnico». La que no se pudo mirar era justamente la de
            #  salida: el Supervisor reviso antes de que la cola la
            #  analizara, nadie comparo esos dos numeros, y el punto afirmo
            #  en verde una coincidencia que solo valia para la de llegada.
            #
            #  TRES AUSENCIAS DISTINTAS, Y HASTA HOY SOLO DOS SE DECIAN:
            #    - `ilegibles`  la foto se miro y no se lee ningun numero
            #    - `sin_mirar`  se leyo algo que no puede salir de ese medidor
            #    - esta        no hay analisis todavia: nadie la miro
            #  La tercera salia por el `continue` de abajo sin dejar rastro, y
            #  el texto del punto hablaba de «la potencia» como si fueran una.
            #
            #  NO SE DEVUELVE AL TECNICO, y es deliberado: la foto esta
            #  subida y es obligatoria. Que la cola no la haya mirado todavia
            #  es un problema del sistema, no algo que el pueda rehacer. Por
            #  eso no entra en `rehacer` --`_que_rehacer` nunca la vera-- y
            #  solo cambia lo que se puede SABER. Cuando la cola termine, la
            #  pasada siguiente del ciclo la compara y la orden cierra sola.
            #
            #  EXIGE EL NUMERO ESCRITO: sin el no hay nada que verificar y el
            #  checklist ya reclama la foto por su cuenta.
            if (escrito is not None and not texto_foto.strip()
                    and requisito in declaradas):
                sin_analizar.append(cuando)

            #  UNA FOTO DE MEDICION QUE NO DEJA LEER NINGUN NUMERO NO SIRVE
            #  --  10/11/2026, pregunta del usuario
            #
            #  «y si sale borrosa o movida y no se pueden leer los datos, por
            #  que no la devolveria». El 06/11 se decidio no devolver por una
            #  foto borrosa, y ese motivo sigue en pie para las demas: «4 de 4
            #  fotos piden una mirada» sobre fotos oscuras de un trabajo bien
            #  hecho, y mandar al tecnico de vuelta por una OPINION es caro.
            #
            #  Pero esta foto es otra cosa, y la distincion que faltaba es la
            #  del PROPOSITO. La del daño encontrado, borrosa, igual muestra
            #  algo. La del medidor tiene un solo trabajo: que se lea un
            #  numero. Si no se lee, no sirve para nada -- y eso no es una
            #  opinion del modelo, es que la expresion regular de
            #  `potencia_de_la_foto` no encontro un dBm. La plantilla de la
            #  empresa ya lo declara: «Basta con que el numero se lea».
            #
            #  SOLO SI LA FOTO EXISTE Y SE MIRO. `_texto_de_la_foto` devuelve
            #  "" cuando no hay analisis, y eso es «todavia nadie la miro»,
            #  nunca «no se lee».
            #
            #  TAMBIEN SIN NUMERO ESCRITO, a diferencia de `sin_mirar`: ahi
            #  faltan las dos cosas y la foto sigue siendo obligatoria. Lo que
            #  no se puede es acusar de una DISCREPANCIA que no se midio.
            #  NINGUNA DE LAS LECTURAS DIO UN dBm, no «la ultima no dio»:
            #  con la relectura puesta, una foto puede tener dos textos y
            #  solo el primero traer el numero. Exigir que la ultima lo
            #  tenga devolveria una orden por una foto que SI se leyo.
            if (not crudos and texto_foto.strip()
                    and requisito in declaradas):
                ilegibles.append(cuando)
                if requisito not in rehacer:
                    rehacer.append(requisito)
            #  UNA LECTURA IMPOSIBLE NO SE COMPARA, se descarta. Ver
            #  `_lectura_creible`: no se "corrige" lo que el modelo leyo
            #  --eso seria inventar el dato-- se deja de opinar sobre una
            #  foto cuya lectura no se puede sostener.
            #  LAS DOS LECTURAS NO DIJERON LO MISMO  --  11/11/2026
            #
            #  Las dos son creibles y son numeros distintos: no hay con que
            #  decidir cual salio de esa pantalla. Se dice y no se compara.
            #  NO devuelve la orden --`rehacer` no la toca--: el que leyo
            #  distinto dos veces es el modelo, no el tecnico.
            if discordaron and requisito in declaradas:
                discordantes.append(cuando)
            if not _lectura_creible(de_la_foto, limites):
                #  PERO EL DESCARTE SE DICE  --  09/11/2026, OT #217
                #
                #  Medido dos veces (OT #212 y #217): la pantalla marca
                #  «-21.0» y el modelo lee «-2.10» --le mueve el punto
                #  decimal--. El filtro hace lo correcto y la tira, pero el
                #  punto salia diciendo «la potencia coincide» a secas, sin
                #  que nadie pudiera saber que de las dos mediciones solo se
                #  habia mirado UNA. La de salida pasaba sin verificar y el
                #  texto no lo delataba.
                #
                #  No cambia el veredicto: una foto mal leida no puede frenar
                #  a un tecnico (31/10). Cambia lo que se puede saber.
                #  Y SOLO ESO: si la foto no dejaba leer nada ya se conto
                #  en `ilegibles`, y si las lecturas discordaron ya se conto
                #  arriba. Tres ausencias distintas, una frase cada una.
                if crudos and escrito is not None and not discordaron:
                    sin_mirar.append(cuando)
                de_la_foto = None
            if escrito is None or de_la_foto is None:
                continue
            vistos += 1
            verificadas.append(cuando)
            ok, por_que = PF.comparar(de_la_foto, escrito)
            if ok is False:
                dudas.append(f"{cuando}, {por_que}")
                #  QUE FOTO ES, para que la devolucion pueda nombrarla. Igual
                #  que `checklist` lleva `faltan`: el punto sabe cual de las
                #  dos mediciones no cuadra, y recalcularlo en `_que_rehacer`
                #  seria copiar esta comparacion --con su tolerancia y su
                #  filtro de lecturas imposibles-- en un segundo lugar.
                rehacer.append(requisito)
        #  EL PUNTO APARECE TAMBIEN SIN UNA SOLA COMPARACION cuando hay una
        #  foto ilegible. Antes `vistos == 0` se iba en silencio, y ese era
        #  justo el caso del usuario: las dos fotos sin numero legible, nada
        #  que comparar, y la orden cerrando como si estuviera todo bien.
        if not vistos and not ilegibles:
            return None
        ilegible = ""
        if ilegibles:
            ilegible = ("La foto del medidor " + " ni la de ".join(ilegibles)
                        + " no deja leer ningún número.")
        nota = ""
        if sin_mirar:
            nota = (" La medición " + " ni ".join(sin_mirar)
                    + " no se pudo verificar: lo que se leyó en esa foto no "
                      "puede salir de ese medidor.")
        if sin_analizar:
            nota += (" La medición " + " ni ".join(sin_analizar)
                     + " todavía no se pudo comparar: esa foto no se ha "
                       "revisado.")
        if discordantes:
            nota += (" La medición " + " ni ".join(discordantes)
                     + " no se pudo verificar: la foto se leyó dos veces y "
                       "dio números distintos.")
        if dudas:
            return _punto("potencia", None,
                          "La foto y el reporte no dicen lo mismo: "
                          + "; ".join(dudas) + "." + nota
                          + ((" " + ilegible) if ilegible else ""),
                          rehacer=rehacer)
        if ilegibles:
            return _punto("potencia", None, ilegible + nota, rehacer=rehacer)
        #  NI `True` NI EL TEXTO DE SIEMPRE SI FALTO MIRAR UNA  --  OT #200
        #
        #  «La potencia coincide» con una sola de las dos verificadas es la
        #  afirmacion que el panel mostro en verde mientras la discrepancia
        #  real pasaba sin que nadie la midiera. `None` es «miralo vos», que
        #  es exactamente lo que se sabe.
        #
        #  NO LO FRENA POR UNA OPINION (31/10): aca no hay opinion de un
        #  modelo, hay un dato que falta. Y no traba nada que no estuviera
        #  trabado: el punto de las fotos ya cuenta esa misma foto en «no se
        #  pudieron mirar». La diferencia es que esto no depende de que ese
        #  otro punto siga contandola.
        #  LO QUE SE ARREGLA ES EL TEXTO, NO EL VEREDICTO  --  11/11/2026
        #
        #  La OT #200, releida: el modelo volvio a escribir «-2.10» donde la
        #  pantalla dice «-21.0», la lectura se descarto con razon, y el
        #  punto salio «La potencia que muestra la foto coincide con la que
        #  reporto el tecnico» con la nota pegada atras. Esa frase habla de
        #  «la potencia» como si fueran una sola, y se compararon una de dos.
        #
        #  SE PROBO BAJAR EL VEREDICTO A `None` Y LAS GUARDAS LO FRENARON, y
        #  tenian razon: `test_LA_ORDEN_SIGUE_CERRANDO` (09/11) dice que el
        #  limite es deliberado --«informa, no frena»-- porque con el modelo
        #  moviendo el punto decimal 3 de cada 7 veces, frenar por cada
        #  lectura descartada deja de cerrar casi todas las ordenes. Eso es
        #  peor que el problema. No se reabre sin una medicion que mueva ese
        #  numero, y la de hoy no lo mueve: lo confirma.
        #
        #  Nombrar CUAL coincidio dice la verdad entera sin frenar nada, y
        #  deja el texto bien de los dos lados: la nota ya explica la que no.
        #
        #  QUIEN SI FRENA, cuando corresponde: el punto de las fotos, que
        #  cuenta la que no tiene texto, y el checklist. Una foto sin analisis
        #  ademas se reintenta (`mirar_las_que_faltan`), asi que esa ausencia
        #  es transitoria -- razon de mas para que no frene nada aca.
        if sin_analizar or sin_mirar:
            cuales = (("La medición " + " y la ".join(verificadas)
                       + (" coincide con su foto." if len(verificadas) == 1
                          else " coinciden con su foto."))
                      if verificadas else
                      "Ninguna medición se pudo verificar contra su foto.")
            return _punto("potencia", True if verificadas else None,
                          cuales + nota)
        return _punto("potencia", True,
                      "La potencia que muestra la foto coincide con la que "
                      "reporto el tecnico." + nota)
    except Exception:                                            # noqa: BLE001
        #  NO TUMBA LA REVISION, por lo mismo que `_fotos`: algo que se
        #  agrega no puede romper lo que ya decide si una orden se cierra.
        return None


def _en_rango(orden, cierre):
    """La potencia AL SALIR contra el rango que la empresa declaro bueno.

    POR QUE  --  07/11/2026
    -----------------------
    El usuario: «hay que establecer que para que pueda diagnosticar si una
    medida esta buena es entre este rango y cuando el note un rango fuera de
    lo indicado ya diagnostica como malo».

    SOLO AL SALIR, decidido con el usuario el 07/11/2026. Al llegar, una
    senal mala ES la falla que el tecnico vino a arreglar: marcarla no aporta
    nada y pondria un punto en rojo en casi toda orden correctiva, que es la
    forma de que el rojo deje de significar algo. Al salir si importa, porque
    es lo que dice si el arreglo sirvio.

    EL RANGO SALE DE LA PLANTILLA, nunca de una constante: varia por empresa
    (CLAUDE.md §3.3) y por tipo de trabajo. Rapilink declaro -8 a -27 dBm el
    07/11/2026. Si la plantilla no lo declara, el punto NO APARECE -- no se
    inventa un rango por omision, que seria decidir por una empresa que no
    dijo nada.

    ESTE SI PUEDE DECIR QUE NO, a diferencia de `_fotos` y `_potencia`. La
    diferencia es quien lo afirma: aca el dato es el NUMERO QUE ESCRIBIO EL
    TECNICO y el rango lo fijo la empresa; el codigo solo compara. No hay
    ninguna lectura de un modelo en el medio (CLAUDE.md §4: el modelo compone,
    el codigo calcula).
    """
    try:
        if cierre is None:
            return None
        esquema = getattr(orden.tipo_trabajo_version, "esquema", None) or {}
        campo = next((c for c in (esquema.get("campos") or [])
                      if isinstance(c, dict) and c.get("id") == CAMPO_AL_SALIR),
                     None)
        if campo is None:
            return None
        bueno = campo.get("bueno")
        if not isinstance(bueno, dict):
            return None
        mn, mx = _a_numero(bueno.get("min")), _a_numero(bueno.get("max"))
        if mn is None or mx is None:
            return None
        #  EL RANGO VIENE COMO (min, max) Y EN dBm EL "MINIMO" ES EL MAS
        #  NEGATIVO. Se ordena acá y no se confia en como quedo escrito: un
        #  -8 cargado como minimo y un -27 como maximo describe el mismo
        #  rango que al reves, y rechazarlo seria pedirle a quien configura
        #  que adivine la convencion.
        piso, techo = min(mn, mx), max(mn, mx)

        valor = _a_numero(_lo_que_escribio_el_tecnico(orden, cierre)
                          .get(CAMPO_AL_SALIR))
        if valor is None:
            return None

        unidad = campo.get("unidad") or "dBm"
        if piso <= valor <= techo:
            return _punto("rango", True,
                          f"La medida al salir ({valor:g} {unidad}) está "
                          f"dentro de lo que la empresa considera bueno "
                          f"({piso:g} a {techo:g}).")
        #  MANDA EL EQUIPO  --  07/11/2026
        #
        #  El usuario, viendo la OT #185 con -35.0 escrito a mano y la OLT
        #  midiendo -20.65: «no, si esta midiendo bien en la OLT esta bien, y
        #  tambien debe comparar la foto del ticket».
        #
        #  Y tiene razon sobre quien sabe. El numero escrito es la
        #  transcripcion de una persona que mira una pantalla; la lectura del
        #  equipo la da el equipo. Cuando se contradicen, frenar un cierre por
        #  la transcripcion es frenarlo por el eslabon mas debil.
        #
        #  PERO NO SE CALLA. Que no frene no lo vuelve irrelevante: una
        #  diferencia de 15 dBm entre lo escrito y lo medido es un dato malo
        #  en el ticket, y alguien tiene que verlo. Queda en «miralo vos» con
        #  las tres lecturas que haya --equipo, foto y lo escrito-- juntas en
        #  un renglon, que es lo unico que permite decidir cual sobra.
        medida = _pieza_de_medicion(orden)
        del_equipo = (medida or {}).get("senal_dbm")
        if (medida or {}).get("quedo_en_rango") is True:
            lecturas = [f"el equipo mide {del_equipo:g} {unidad}"
                        if isinstance(del_equipo, (int, float))
                        else "el equipo la mide en rango"]
            de_la_foto = _potencia_de_la_foto_al_salir(orden)
            if de_la_foto is not None:
                lecturas.append(f"la foto marca {de_la_foto:g} {unidad}")
            lecturas.append(f"el técnico escribió {valor:g} {unidad}")
            return _punto("rango", None,
                          "El número escrito quedó fuera del rango bueno "
                          f"({piso:g} a {techo:g}), pero no coincide con el "
                          "equipo: " + "; ".join(lecturas) + ".")

        #  SIN LECTURA DEL EQUIPO QUE LA CONTRADIGA, el numero escrito es lo
        #  unico que hay, y dice que la señal quedo mal. Ahi si frena: lo
        #  contrario seria dejar pasar toda medida mala cada vez que la
        #  medicion del equipo no se pudo hacer, que es seguido.
        return _punto("rango", False,
                      f"La medida al salir ({valor:g} {unidad}) quedó fuera "
                      f"del rango bueno ({piso:g} a {techo:g}).")
    except Exception:                                            # noqa: BLE001
        #  No tumba la revision, por lo mismo que los otros puntos nuevos.
        return None


def _a_numero(valor):
    """El decimal que el tecnico escribio, venga como numero o como texto.

    El campo es `decimal` en la plantilla, pero lo que queda guardado en el
    JSON del cierre puede ser `"-21.0"` o `-21.0` segun por donde entro. Leer
    solo uno de los dos formatos es que el punto desaparezca sin motivo
    visible la mitad de las veces.
    """
    if isinstance(valor, bool) or valor is None:
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    try:
        return float(str(valor).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None


def _texto_de_la_foto(orden, requisito_id: str) -> str:
    """Lo que la IA escribio sobre ESA foto, en esta vuelta. `''` si no hay.

    LA ULTIMA, venga de la vuelta que venga -- 08/11/2026, por lo mismo que
    `_evidencias_para_revisar`. Decia «de la vuelta actual», y en una orden
    devuelta eso dejaba sin comparar las mediciones que nadie pidio rehacer:
    el punto desaparecia en silencio justo donde habia mas para mirar.

    Si el tecnico la rehizo, la nueva es la ultima y manda. Si no se la
    pidieron, la que habia sigue siendo la evidencia de esa medicion.
    """
    from campo.models import AnalisisDeEvidencia

    a = (AnalisisDeEvidencia.objects
         #  'org' ADEMAS del camino por la orden: es la misma consulta que
         #  hace inspeccion_visual.punto_de_la_revision, y el filtro de tenant
         #  va explicito aunque la orden ya lo acote (CLAUDE.md 4: olvidar
         #  fijar el tenant devuelve cero filas, no todas).
         .filter(org=orden.org, evidencia__orden_trabajo=orden,
                 evidencia__requisito_id=requisito_id)
         #  La vuelta primero, por lo mismo que en
         #  `_evidencias_para_revisar`: una foto reintentada de la vuelta
         #  anterior puede ser la mas nueva por fecha.
         .order_by("-vuelta", "-created_at").first())
    return (a.texto or "") if a else ""


def _cierre_de_esta_vuelta(orden):
    """El ultimo reporte de cierre DESPUES de la ultima devolucion: el de una
    vuelta anterior ya fue revisado y devuelto."""
    from campo.models import EventoTrabajo

    eventos = EventoTrabajo.objects.filter(org=orden.org, orden=orden)
    devuelta = (eventos.filter(tipo="reapertura_correccion")
                .order_by("-created_at").values_list("created_at", flat=True).first())
    cierres = eventos.filter(tipo="cierre_campo")
    if devuelta is not None:
        cierres = cierres.filter(created_at__gt=devuelta)
    return cierres.order_by("-created_at").first()


def el_ticket(orden) -> dict:
    """Lo que ORIGINO la orden, para poder compararlo con lo que se hizo.

    POR QUE  --  12/11/2026
    -----------------------
    El usuario: «debe haber relacion entre el asunto, la descripcion del
    ticket y la respuesta del tecnico. No puede haber una respuesta correcta
    en un asunto que ni por ahi iba al caso.»

    `revisar()` evaluaba ocho puntos --checklist, reporte, servicio, medicion,
    material, fotos, potencia, rango-- y NINGUNO miraba el ticket. El tecnico
    podia escribir cualquier cosa coherente consigo misma y los ocho daban
    verde, porque no habia contra que compararla.

    ES EL MISMO HUECO DEL 06/11, CON TEXTO EN VEZ DE FOTOS. Ese dia el usuario
    pidio que el supervisor viera si las fotos coinciden con lo pedido, y la
    nota de `revisar()` lo dejo escrito: «el hueco era de informacion, no de
    poder: el boton ya existia, pero esta lista mandaba solo el id y el
    titulo, asi que NO HABIA CON QUE COMPARAR». Esto trae el otro lado.

    DE DONDE SALE CADA COSA, MEDIDO EN PRODUCCION EL 12/11/2026
    -----------------------------------------------------------
    Sobre las ultimas ordenes de Rapilink:

      272 | resumen: 'Enviar a correctivo de planta: el tecnico ya asignado...'
      270 | resumen: 'Enviar a correctivo de red/planta externa: verificar el
                      puerto 3/4/4...'
      264 | resumen: 'Llamar al cliente para ubicarlo: es una instalacion
                      nueva y el ISP no tiene su direccion...'

    `resumen` ES el caso, y esta lleno: lo precarga la lectura del Supervisor
    (ver el comentario del campo en `campo/models.py`). `diagnostico_previo`
    sale VACIO en todas: el campo existe, `crear_orden` lo acepta, y ninguno
    de sus dos llamadores --`despacho_views.py:191` y
    `operaciones/ordenes_de_despacho.py:654`-- se lo pasa. Se lee igual, para
    el dia que alguien lo llene; hoy devuelve "".

    (Las ordenes 1842-1844 de produccion SI lo traen y tienen `resumen`
    vacio. No son otra poblacion: son datos de demostracion que quedaron ahi,
    con su historia escrita en `seed_campo_demo.py`.)

    NO JUZGA NADA. Devuelve los dos lados; quien compara es el punto noveno,
    y por encima de el, una persona.
    """
    version = getattr(orden, "tipo_trabajo_version", None)
    tipo = getattr(version, "work_type", None)
    #  El diagnostico previo es un JSON libre del asistente. Se toma su
    #  'resumen' si lo trae; lo demas son datos sueltos que no se leen como
    #  prosa --y volcarlos enteros meteria claves internas en una pantalla.
    previo = getattr(orden, "diagnostico_previo", None) or {}
    return {
        "asunto": str(getattr(tipo, "nombre", "") or ""),
        "caso": str(getattr(orden, "resumen", "") or "").strip(),
        "diagnostico_previo": str(previo.get("resumen") or "").strip(),
        "origen": " ".join(x for x in (
            str(getattr(orden, "origen_tipo", "") or ""),
            str(getattr(orden, "origen_ref", "") or "")) if x).strip(),
    }


def _solucion(cierre) -> str:
    respuestas = ((cierre.datos or {}).get("respuestas") or {}) if cierre else {}
    return str(respuestas.get("solucion") or "")


def _checklist(orden):
    from campo.services.validador import verificar_checklist_completo

    errores = verificar_checklist_completo(orden)
    if not errores:
        return _punto("checklist", True, "El checklist está completo: datos y fotos.", faltan=[])
    faltan = sorted({e["requisito_id"] for e in errores if e.get("requisito_id")})
    return _punto("checklist", False, "Falta en el checklist: "
                  + "; ".join(e.get("mensaje", "") for e in errores[:3]), faltan=faltan)


def _reporte(cierre):
    if cierre is None:
        return _punto("reporte", False, "No mandó el reporte de cierre.")
    return _punto("reporte", True, "Mandó el reporte de cierre.")


def _servicio(cierre):
    """Lo que el tecnico AFIRMO. Si la plantilla de ese cierre no lo pregunta,
    el punto no aplica."""
    if cierre is None:
        return None
    datos = cierre.datos or {}
    pregunta = any(isinstance(c, dict) and c.get("id") == "servicio_validado"
                   for c in (datos.get("definicion") or []))
    if not pregunta:
        return None
    valor = (datos.get("respuestas") or {}).get("servicio_validado")
    if valor is True:
        return _punto("servicio", True, "El técnico afirma que el servicio quedó funcionando.")
    if valor is False:
        return _punto("servicio", False, "El técnico dice que el servicio NO quedó funcionando.")
    return _punto("servicio", None, "El reporte no dice si el servicio quedó funcionando.")


def _medicion(orden, pendientes=None):
    """La señal despues del arreglo (`operaciones/verificacion_de_arreglos.py`),
    si el Supervisor ya la midio para ESTA orden. Si la espera y no llego,
    «no se sabe». Si no la espera, no aplica.

    EL TEXTO YA NO NOMBRA UNA HORA  --  06/11/2026. Decia «el Supervisor mide
    una vez por hora», y el usuario lo leyo como lo que era: una espera que no
    tenia por que existir. Desde hoy la medicion sale apenas llega el reporte
    (`campo/tasks.py::revisar_el_cierre_ya`), y el ciclo horario quedo de red
    de atras. Si aun asi no se midio, es porque el proveedor no contesto o la
    orden no entra en lo que se mide -- y ninguna de las dos es «esperar»."""
    from operaciones.models import PropuestaSupervisor
    from operaciones.verificacion_de_arreglos import FUENTE

    esperando = _punto("medicion", None,
                       "La señal después del arreglo todavía no se "
                       "pudo medir.")

    propuesta = (PropuestaSupervisor.objects
                 .filter(org=orden.org,
                         evidencia__contains=[{"fuente": FUENTE, "orden": str(orden.id)}])
                 .order_by("-updated_at").first())
    pieza = None if propuesta is None else next(
        (p for p in reversed(propuesta.evidencia or [])
         if isinstance(p, dict) and p.get("fuente") == FUENTE
         and p.get("orden") == str(orden.id)), None)
    if pieza is None:
        if pendientes == NO_SE_SABE:
            return _punto("medicion", None,
                          "No se pudo saber si esta orden espera la medición "
                          "después del arreglo.")
        return esperando if pendientes and str(orden.id) in pendientes else None
    rango = pieza.get("quedo_en_rango")
    if rango is True:
        return _punto("medicion", True, "La señal quedó en rango después del arreglo.")
    if rango is False:
        return _punto("medicion", False, "La señal NO quedó en rango después del arreglo.")
    return _punto("medicion", None, "No se pudo medir la señal después del arreglo.")


def _material(orden, cierre):
    from campo.models import MovimientoDeMaterial

    usados = MovimientoDeMaterial.objects.filter(
        org=orden.org, orden=orden, tipo=MovimientoDeMaterial.CONSUMO).count()
    if usados:
        return _punto("material", True,
                      f"Registró {usados} {'material' if usados == 1 else 'materiales'}.")
    if cierre is not None and (cierre.datos or {}).get("sin_material_confirmado"):
        return _punto("material", True, "Confirmó que no usó material.")
    return _punto("material", None, "No registró material ni confirmó que no usó.")
