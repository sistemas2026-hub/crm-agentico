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
        "sugeridas": next((p["faltan"] for p in puntos if p["clave"] == "checklist"), []),
        "solucion": _solucion(cierre),
    }


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

    SOLO LA VUELTA QUE CORRE. Una orden devuelta y rehecha tiene fotos nuevas;
    las de la vuelta anterior no dicen nada de esta. Mismo criterio que
    `EvidenciaTrabajo.vuelta` y que `_fotos()`.
    """
    from campo.models import AnalisisDeEvidencia, EvidenciaTrabajo
    from campo.tasks import muestra_lo_pedido

    vuelta = getattr(orden, "vuelta", 1) or 1
    #  La ULTIMA por requisito: si el tecnico la rehizo, manda la de ahora.
    llegaron = {}
    for ev in EvidenciaTrabajo.objects.filter(
            org=orden.org, orden_trabajo=orden,
            vuelta=vuelta).order_by("recibida_en_servidor"):
        llegaron[ev.requisito_id] = ev

    #  Lo que la IA vio, por evidencia. Una sola consulta, no una por foto.
    visto = {}
    for a in AnalisisDeEvidencia.objects.filter(
            org=orden.org, evidencia__orden_trabajo=orden,
            vuelta=vuelta).order_by("created_at"):
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
        dudas, vistos = [], 0
        for campo, requisito, cuando in pares:
            escrito = _a_numero(respuestas.get(campo))
            de_la_foto = PF.uno_solo(_texto_de_la_foto(orden, requisito))
            if escrito is None or de_la_foto is None:
                continue
            vistos += 1
            ok, por_que = PF.comparar(de_la_foto, escrito)
            if ok is False:
                dudas.append(f"{cuando}, {por_que}")
        if not vistos:
            return None
        if dudas:
            return _punto("potencia", None,
                          "La foto y el reporte no dicen lo mismo: "
                          + "; ".join(dudas) + ".")
        return _punto("potencia", True,
                      "La potencia que muestra la foto coincide con la que "
                      "reporto el tecnico.")
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

    De la vuelta actual y no de cualquiera: una foto de la vuelta 1 ya fue
    devuelta, y comparar contra ella diria que el tecnico se contradice
    cuando lo que hizo fue corregir.
    """
    from campo.models import AnalisisDeEvidencia

    a = (AnalisisDeEvidencia.objects
         #  'org' ADEMAS del camino por la orden: es la misma consulta que
         #  hace inspeccion_visual.punto_de_la_revision, y el filtro de tenant
         #  va explicito aunque la orden ya lo acote (CLAUDE.md 4: olvidar
         #  fijar el tenant devuelve cero filas, no todas).
         .filter(org=orden.org, evidencia__orden_trabajo=orden,
                 evidencia__requisito_id=requisito_id,
                 vuelta=orden.vuelta)
         .order_by("-created_at").first())
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
