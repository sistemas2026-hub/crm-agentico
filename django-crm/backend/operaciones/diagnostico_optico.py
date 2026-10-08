# -*- coding: utf-8 -*-
"""
===============================================================================
 EL DIAGNOSTICO OPTICO DE UN CASO DESINCRONIZADO  --  escrito, no ejecutado
===============================================================================

QUE HACE
--------
Toma las señales de casos cerrados en el proveedor y abiertos en el CRM, le
pregunta a SmartOLT por el equipo de cada cliente, y deja el resultado ESCRITO
en la señal: como evidencia que una persona lee, y como datos que el codigo de
mas adelante puede usar.

NO CIERRA NADA. El cierre es otra fase, otro techo de autonomia y otra puerta.
Lo que esta fase produce es la razon por la cual un cierre seria seguro --o no
lo seria-- y la deja por escrito antes de que nadie decida.

LA REGLA, Y DE QUIEN ES
-----------------------
La definio el usuario el 07/10/2026, y se implementa en CODIGO porque es una
decision, no una redaccion:

    equipo caido por falta de energia  -> el cierre es seguro
    equipo en linea con señal buena    -> el cierre es seguro
    señal debil, o caida por fibra     -> NO: esto lo mira una persona
    cualquier otra cosa                -> NO: no se afirma nada

'sin_energia' es la casa del cliente; 'fibra' es un corte en la NAP, y eso es
nuestro. Son opuestas, y tratarlas igual seria cerrarle el caso a gente que
sigue sin servicio. Esa distincion es la unica razon por la que este modulo
existe: sin ella, "el ticket esta cerrado alla" alcanzaba para cerrar aca.

POR QUE NO VA DENTRO DEL DETECTOR
---------------------------------
'supervisor.detectar' corre DIECIOCHO detectores y promete no tener efectos.
Meter una llamada a un proveedor ahi adentro le habria costado, con los 19
casos medidos en produccion, unos 190 segundos --'get_onu_full_status_info'
tarda ~10 s, medido 9,9 s en la skill-- a una funcion que hoy tarda
milisegundos y que se dispara desde un boton con una persona esperando.

Esa es la misma forma del incidente del 06/10/2026, cuando encender el cerebro
dejo el ciclo colgado: llamadas sin tope dentro de una peticion sincrona.

EL PRESUPUESTO ES DOBLE, Y POR ESO MISMO
----------------------------------------
Un tope de CANTIDAD solo no alcanza: tres llamadas que tardan 30 s cada una
cuelgan el ciclo igual que treinta. Un tope de RELOJ solo tampoco: se gasta
entero en una llamada que no vuelve. Se reusa 'supervisor.presupuesto', que ya
tiene las dos cosas y ya esta probado, en vez de escribir un mecanismo nuevo
con la misma forma.

Lo que NO se diagnostico por falta de presupuesto queda dicho: "no se
diagnostico" con su motivo. Nunca se parece a "esta sano" -- es la misma regla
que el resto del Supervisor aplica con DESCONOCIDO, y la razon por la que el
ejecutor del motor devuelve 'desconocido' con 'motivo' en vez de levantar.
"""
from __future__ import annotations

from django.utils import timezone

from operaciones import supervisor as sup
from operaciones.models import PropuestaSupervisor

#  Cuantos equipos se diagnostican por corrida, y cuanto reloj se les presta.
#
#  TRES Y SESENTA, y los dos numeros salen de una medicion, no de un gusto: son
#  19 los casos desincronizados en produccion (07/10/2026) y cada diagnostico
#  paga ~10 s de 'get_onu_full_status_info' MAS la llamada que resuelve el
#  equipo. Tres por ciclo son ~60 s en el peor caso, que es lo que tolera un
#  boton; los 19 se cubren en siete ciclos, y un caso cerrado afuera no se
#  vuelve urgente por esperar un ciclo mas.
#
#  Subirlos es una decision de operacion con una medicion detras, no un ajuste:
#  el costo no es la cuota de SmartOLT --1.000/hora, holgadisimo-- sino el
#  tiempo que una persona espera mirando la pantalla.
TOPE_DIAGNOSTICOS_POR_CICLO = 3
SEGUNDOS_MAXIMOS_DE_DIAGNOSTICO = 60

#  Los veredictos de ESTA fase. No son el cierre: son la razon por la que un
#  cierre seria seguro, que es lo que se escribe.
CIERRE_SEGURO = "cierre_seguro"
REVISAR_PERSONA = "revisar_persona"
SIN_DIAGNOSTICO = "sin_diagnostico"

#  Los valores que devuelve el ejecutor del motor
#  ('nucleo/herramientas/diagnostico_servicio.py'). Se nombran aca para que un
#  cambio alla rompa una prueba en vez de volver silenciosamente todo
#  'sin_diagnostico' -- que es el modo de falla peligroso: parece prudencia.
EN_LINEA = "en_linea"
CAIDO = "caido"
SENAL_BUENA = "buena"
SENAL_DEBIL = "debil"
CAUSA_SIN_ENERGIA = "sin_energia"
CAUSA_FIBRA = "fibra"


def presupuesto(ahora=None) -> dict:
    """El presupuesto de esta fase. Mismo mecanismo que el del cerebro."""
    return sup.presupuesto(tope=TOPE_DIAGNOSTICOS_POR_CICLO,
                           segundos=SEGUNDOS_MAXIMOS_DE_DIAGNOSTICO,
                           ahora=ahora)


def clasificar(diagnostico: dict) -> tuple[str, str]:
    """
    (veredicto, porque) a partir de un diagnostico. EL CODIGO DECIDE, no el
    modelo.

    Devuelve siempre un porque redactado para que lo lea una persona: quien
    acepta la propuesta cambia el estado de un caso, y tiene que poder ver
    contra que. El texto no es decorativo -- es lo que queda escrito cuando
    alguien pregunte, semanas despues, por que se cerro.

    FAIL-CLOSED EN LA FORMA QUE IMPORTA: cualquier cosa que no sea una de las
    dos condiciones seguras cae en 'revisar_persona' o 'sin_diagnostico'.
    Nunca al reves. Un diagnostico que no se entiende no es un diagnostico
    bueno.
    """
    if not isinstance(diagnostico, dict) or diagnostico.get("error"):
        motivo = ""
        if isinstance(diagnostico, dict):
            motivo = str(diagnostico.get("detalle") or
                         diagnostico.get("error") or "")
        return SIN_DIAGNOSTICO, (
            "no se pudo diagnosticar el equipo"
            + (f": {motivo}" if motivo else "")
            + ". Eso no dice que este sano ni caido: dice que no hay dato.")

    estado = str(diagnostico.get("estado") or "")
    senal = str(diagnostico.get("senal") or "")
    causa = str(diagnostico.get("causa_caida") or "")
    dbm = diagnostico.get("senal_dbm")

    #  SIN EQUIPO REGISTRADO: su propio motivo, no "no se pudo".
    #
    #  Medido el 07/10/2026: de 19 casos desincronizados, DOS no tienen serial
    #  de ONU cargado en WispHub. Eso no es una falla de nadie ni algo que se
    #  reintente -- es un dato que el ISP no cargo, y la skill lo tiene medido
    #  a escala: 1.299 de 4.163 clientes activos estan igual.
    #
    #  Se dice con todas las letras porque es ACCIONABLE de una forma distinta:
    #  "no se pudo diagnosticar" invita a reintentar, y "este servicio no tiene
    #  equipo registrado" le dice a quien lee que el dato falta en WispHub y
    #  que decida sin el. Lo pidio el usuario con esas palabras.
    if diagnostico.get("equipo_registrado") is False:
        return SIN_DIAGNOSTICO, (
            "este servicio no tiene equipo registrado en WispHub, asi que no "
            "hay con que consultar la ONU: no se puede verificar su estado "
            "optico. No es que el equipo este mal -- es que falta el dato para "
            "preguntar.")

    if estado not in (EN_LINEA, CAIDO):
        return SIN_DIAGNOSTICO, (
            f"el estado del equipo volvio como '{estado or 'vacio'}'"
            + (f" ({diagnostico.get('motivo')})" if diagnostico.get("motivo")
               else "")
            + ". Sin estado no se afirma nada.")

    #  CAIDO POR FALTA DE ENERGIA  --  la casa del cliente, no la red.
    if estado == CAIDO and causa == CAUSA_SIN_ENERGIA:
        return CIERRE_SEGURO, (
            "el equipo esta caido y el proveedor reporto falta de energia "
            "(dying-gasp): es un corte de luz en el domicilio, no una falla "
            "de la red. El ticket ya esta cerrado en el proveedor, asi que "
            "cerrarlo aca alinea el estado, no resuelve nada por nadie.")

    #  CAIDO POR FIBRA  --  esto es nuestro, y no se cierra.
    if estado == CAIDO and causa == CAUSA_FIBRA:
        return REVISAR_PERSONA, (
            "el equipo esta caido por perdida de señal optica (LOS/LOF): esa "
            "falla es de la red, no del cliente. No se propone cerrar aunque "
            "el proveedor ya lo haya cerrado.")

    if estado == CAIDO:
        return REVISAR_PERSONA, (
            f"el equipo esta caido y la causa que reporto el proveedor "
            f"({causa or 'ninguna'}) no es una de las dos que este codigo sabe "
            f"distinguir. No se decide por descarte.")

    #  EN LINEA  --  solo la señal buena habilita el cierre.
    #
    #  El dBm se nombra cuando esta, y se omite cuando no: "señal buena" sin el
    #  numero sigue siendo cierto, pero con el numero quien lee puede
    #  comprobarlo por su cuenta en vez de creerle a esta clasificacion. Es la
    #  misma razon por la que la evidencia de un caso nombra su fuente.
    nivel = f" ({dbm} dBm)" if dbm is not None else ""

    if senal == SENAL_BUENA:
        return CIERRE_SEGURO, (
            f"el equipo esta en linea y la señal de bajada es buena{nivel}, "
            f"dentro del rango que la guia considera sano. El ticket ya esta "
            f"cerrado en el proveedor y el equipo responde bien, asi que "
            f"cerrarlo aca alinea el estado.")

    if senal == SENAL_DEBIL:
        return REVISAR_PERSONA, (
            f"el equipo esta en linea pero la señal de bajada es debil"
            f"{nivel}. Puede volver a fallar, asi que lo mira una persona.")

    return SIN_DIAGNOSTICO, (
        "el equipo esta en linea pero no hubo lectura de señal, asi que no se "
        "puede decir si va a aguantar. No se propone cerrar sin ese dato.")


def enriquecer(org, senales, *, ahora=None, presupuesto_=None,
               diagnosticar=None) -> dict:
    """
    Le agrega el diagnostico optico a las señales de casos desincronizados.

    Muta las señales --'Senal' es mutable y su 'evidencia' y 'datos' son del
    llamador-- y devuelve CONTEOS para el informe del ciclo.

    'diagnosticar' SE INYECTA, igual que 'proponer' e 'interpretar' en el
    seguimiento: este modulo decide QUE significa un diagnostico, y no tiene
    por que saber que del otro lado hay un motor por HTTP. Tambien es lo que
    permite probar la clasificacion sin red.
    """
    ahora = ahora or timezone.now()
    p = presupuesto_ if presupuesto_ is not None else presupuesto(ahora=ahora)

    if diagnosticar is None:
        from operaciones import chat_herramientas

        def diagnosticar(org_, id_servicio):
            return chat_herramientas.diagnosticar_servicio(
                org_, id_servicio=id_servicio)

    informe = {"diagnosticados": 0, "cierre_seguro": 0, "revisar_persona": 0,
               "sin_diagnostico": 0, "sin_llave": 0, "sin_presupuesto": 0,
               "errores": 0}

    for senal in senales:
        if senal.tipo != PropuestaSupervisor.CASO_DESINCRONIZADO:
            continue

        id_servicio = str(senal.datos.get("id_servicio") or "").strip()
        if not id_servicio:
            informe["sin_llave"] += 1
            _anotar(senal, SIN_DIAGNOSTICO,
                    "el caso no tiene el id de servicio del proveedor, asi que "
                    "no se puede preguntar por el equipo. No se diagnostico.",
                    None, ahora)
            continue

        if not sup._hay_presupuesto(p):
            informe["sin_presupuesto"] += 1
            _anotar(senal, SIN_DIAGNOSTICO,
                    "no se diagnostico en esta corrida: se agoto el "
                    "presupuesto de diagnosticos del ciclo. Se intenta en el "
                    "siguiente; esto NO dice nada del estado del equipo.",
                    None, ahora)
            continue

        sup._gastar(p)
        try:
            diagnostico = diagnosticar(org, id_servicio)
        except Exception as e:                                   # noqa: BLE001
            #  El tipo y no el texto: el texto de una excepcion de red trae la
            #  URL, y la URL de SmartOLT lleva el identificador del equipo de
            #  un cliente. Misma regla que 'fuentes_adaptadores._pedirle_al_motor'.
            informe["errores"] += 1
            _anotar(senal, SIN_DIAGNOSTICO,
                    f"no se pudo preguntar por el equipo "
                    f"({type(e).__name__}). No se diagnostico.", None, ahora)
            continue

        informe["diagnosticados"] += 1
        veredicto, porque = clasificar(diagnostico)
        informe[veredicto] = informe.get(veredicto, 0) + 1
        _anotar(senal, veredicto, porque, diagnostico, ahora)

    return informe


#  EL PILOTO EN SOMBRA DEL CIERRE AUTOMATICO
#  ==========================================
#  ESTE MODULO NO CIERRA NINGUN CASO, Y NO HAY BANDERA QUE LO HAGA CERRAR.
#
#  La primera version de este bloque declaraba 'CIERRE_AUTOMATICO = False' y
#  decia "en True, cierra". Era falso: el codigo que cierra no estaba escrito.
#  Una bandera que promete una conducta inexistente es peor que no tenerla --
#  la proxima sesion la enciende, no pasa nada, y se va a buscar el error a
#  otro lado. Es la misma familia que "codigo construido no es codigo que
#  corre", y por eso se saco en vez de dejarla "para despues".
#
#  Lo que SI hace: medir. Marca cada propuesta con si el sistema la habria
#  cerrado solo y por que, corriendo las condiciones REALES del cierre. Ese
#  registro es lo que produce el dato que el propio codigo exige para el paso
#  siguiente: 'autonomia.cambiar()' pide criterios MEDIDOS, no una intuicion.
#
#  Para que el cierre ocurra de verdad faltan tres cosas, y ninguna es esta:
#    1. el codigo que llame a 'cierre_de_caso.cerrar' desde el ciclo
#    2. un actor de sistema ('ACTOR_AUTOMATICO') que la auditoria acepte
#    3. el techo de autonomia de la empresa en NIVEL_EJECUTAR_REVERSIBLE,
#       que hoy esta en NIVEL_RECOMENDAR (models.py, NIVEL_MAXIMO_ETAPA)
EN_SOMBRA = True

#  Quien figura en la auditoria cuando cierra el sistema. Decision del usuario
#  el 07/10/2026 sobre la alternativa de usar su propio usuario: si lo
#  automatico y lo humano quedan con el mismo nombre, el dia que algo salga mal
#  no hay forma de separarlos, que es justo cuando hace falta.
ACTOR_AUTOMATICO = "Supervisor NOC IA"

#  El nivel que una propuesta tiene que pedir para que el ciclo la ejecute.
#  Cerrar un caso en el CRM es reversible --se reabre-- y por eso es 3 y no 4:
#  el 4 es "siempre lo aprueba una persona" y 'autonomia.puede' lo niega
#  siempre, por configuracion que tenga la empresa.
NIVEL_PARA_CERRAR = PropuestaSupervisor.NIVEL_EJECUTAR_REVERSIBLE


def evaluar_cierre_automatico(org, senales, *, ahora=None) -> dict:
    """
    Si cada caso con 'cierre_seguro' CERRARIA hoy. En sombra no cierra.

    Corre las condiciones REALES ('cierre_de_caso.condiciones_del_caso'), las
    mismas doce que corren antes de un cierre de verdad. No las imita: una
    sombra que midiera otra cosa que la ejecucion no serviria para decidir si
    encenderla, que es su unico proposito.

    Lo que deja escrito en la señal:
        cierre_automatico   'cerraria' | 'no_cerraria' | 'no_aplica'
        cierre_automatico_porque   el motivo, en el idioma de quien lee

    NO CIERRA, y no hay forma de que cierre: el codigo que ejecuta un cierre
    desde el ciclo todavia no existe. Ver la nota de 'EN_SOMBRA' arriba para
    las tres cosas que faltan.
    """
    from cases.models import Case
    from operaciones import cierre_de_caso

    ahora = ahora or timezone.now()
    informe = {"cerraria": 0, "no_cerraria": 0, "no_aplica": 0,
               "cerrados": 0, "motivos": {}}

    for senal in senales:
        if senal.tipo != PropuestaSupervisor.CASO_DESINCRONIZADO:
            continue
        if senal.datos.get("diagnostico_veredicto") != CIERRE_SEGURO:
            #  Sin un diagnostico que lo habilite no se evalua siquiera. El
            #  'no_aplica' se escribe igual: el silencio en una señal que no
            #  se miro es indistinguible del silencio en una que si.
            informe["no_aplica"] += 1
            senal.datos["cierre_automatico"] = "no_aplica"
            senal.datos["cierre_automatico_porque"] = (
                "el diagnostico no habilita un cierre automatico")
            continue

        caso = Case.objects.filter(id=senal.origen_id, org=org).first()
        if caso is None:
            informe["no_cerraria"] += 1
            senal.datos["cierre_automatico"] = "no_cerraria"
            senal.datos["cierre_automatico_porque"] = "el caso ya no existe"
            continue

        #  Se construye una propuesta EN MEMORIA, sin guardar: las condiciones
        #  miran la organizacion y el origen, y eso ya se sabe sin ir a la
        #  base. Guardar una propuesta falsa para poder validarla seria dejar
        #  basura en una tabla que es registro de decisiones.
        fantasma = PropuestaSupervisor(
            org=org, tipo_senal=senal.tipo, origen_tipo=senal.origen_tipo,
            origen_id=senal.origen_id,
            estado=PropuestaSupervisor.ACEPTADA)
        try:
            cierre_de_caso.condiciones_del_caso(fantasma, caso, ahora=ahora)
        except cierre_de_caso.NoSeCerro as no:
            informe["no_cerraria"] += 1
            informe["motivos"][no.motivo] = informe["motivos"].get(no.motivo, 0) + 1
            senal.datos["cierre_automatico"] = "no_cerraria"
            senal.datos["cierre_automatico_porque"] = (
                f"no cerraria: {no.detalle or no.motivo}")
            continue

        informe["cerraria"] += 1
        senal.datos["cierre_automatico"] = "cerraria"
        senal.datos["cierre_automatico_porque"] = (
            "el diagnostico habilita el cierre y las condiciones del caso se "
            "siguen cumpliendo"
            + (". No se cerro: el cierre automatico esta en modo sombra, asi "
               "que esto es lo que el sistema HABRIA hecho." if EN_SOMBRA
               else ""))
        senal.evidencia.append(sup._observacion(
            "cierre automatico", senal.origen_id,
            senal.datos["cierre_automatico_porque"], ahora))

    return informe


def propuesta_pendiente_de(org, senal):
    """
    La propuesta VIVA y sin decidir de esta señal, o None.

    Solo 'PROPUESTA': una aceptada, rechazada o modificada ya recibio su
    decision humana, y volver sobre ella seria pisar lo que alguien dijo.
    """
    return PropuestaSupervisor.objects.filter(
        org=org, tipo_senal=senal.tipo, origen_tipo=senal.origen_tipo,
        origen_id=senal.origen_id, huella_condicion=senal.huella,
        estado=PropuestaSupervisor.PROPUESTA,
    ).order_by("-created_at").first()


def le_falta_diagnostico(propuesta) -> bool:
    """
    Si esta propuesta se emitio ANTES de que existiera el diagnostico optico.

    Se mira la evidencia --que es lo que de verdad tiene o no tiene-- y no una
    marca aparte: una bandera podria quedar puesta sin que la evidencia este, y
    entonces diria que ya se diagnostico un caso del que no se sabe nada.
    """
    for pieza in (propuesta.evidencia or []):
        if isinstance(pieza, dict) and pieza.get("fuente") == "diagnostico":
            return False
    return True


def completar_propuesta_existente(org, senal, propuesta, *, ahora=None) -> dict:
    """
    Le agrega el diagnostico a una propuesta YA EMITIDA, y la cierra si procede.

    POR QUE HACE FALTA (08/10/2026)
    -------------------------------
    Porque sin esto el cierre automatico no servia para nada en la practica.
    Medido en produccion: 75 casos desincronizados, y los 75 YA tenian
    propuesta. El ciclo las descartaba con 'repetida' antes de mirarlas, asi
    que no habia ni una sola señal nueva sobre la que diagnosticar -- el
    sistema estaba completo, autorizado, y no tenia sobre que actuar.

    La alternativa era cancelar 75 propuestas a mano para que se regeneraran.
    Eso habria resuelto el sintoma de hoy y dejado el mismo problema para
    siempre: una propuesta que queda pendiente dos dias no ganaba diagnostico
    nunca.

    LA EVIDENCIA SE AGREGA, NO SE REESCRIBE. Las siete observaciones originales
    quedan donde estaban y el diagnostico se suma como octava. Una propuesta es
    el registro de lo que se sabia al proponerla; aqui se sabe mas, y eso se
    anota -- no se borra lo anterior.

    EL NIVEL SUBE A 3 SOLO SI EL DIAGNOSTICO LO HABILITA, igual que en una
    propuesta nueva. Sin eso la propuesta pedia nivel 1 --porque nacio sin
    diagnostico-- y la primera puerta del cierre la rechazaria por una razon
    que ya no es cierta.
    """
    ahora = ahora or timezone.now()
    veredicto = senal.datos.get("diagnostico_veredicto")
    if not veredicto:
        return {"intentado": False, "cerrado": False,
                "motivo": "no se diagnostico en esta corrida"}

    campos = ["evidencia", "updated_at"]
    propuesta.evidencia = list(propuesta.evidencia or []) + [
        sup._observacion("diagnostico", senal.origen_id,
                         f"diagnostico del equipo: "
                         f"{senal.datos.get('diagnostico_porque', '')}", ahora)]
    if veredicto == CIERRE_SEGURO:
        propuesta.nivel_autonomia_requerido = NIVEL_PARA_CERRAR
        campos.append("nivel_autonomia_requerido")
    propuesta.updated_at = ahora
    propuesta.save(update_fields=campos)

    return cerrar_si_corresponde(org, propuesta, ahora=ahora)


def cerrar_si_corresponde(org, propuesta, *, ahora=None) -> dict:
    """
    Cierra el caso de una propuesta recien creada, si las DOS puertas lo dejan.

    Devuelve {intentado, cerrado, motivo}. Nunca levanta: un cierre que no
    ocurre es un resultado posible del ciclo, no algo que deba tumbarlo.

    LAS DOS PUERTAS, Y NINGUNA ES LA OTRA
    -------------------------------------
      1. LA PROPUESTA PIDE NIVEL 3. Solo lo pide si su diagnostico optico dio
         'cierre_seguro' -- equipo en linea con señal buena, o caido por falta
         de energia en la casa del cliente. Cualquier otra cosa se queda en
         nivel 1 y ni llega aqui.
      2. LA EMPRESA LO AUTORIZO. 'autonomia.puede(org, 3)' lee el nivel
         configurado para ESTA empresa, que solo sube una persona con nombre,
         motivo y criterios medidos. Con el techo del codigo en 3 y el de la
         empresa en 1 --que es el estado al escribir esto-- no se cierra ni un
         caso.

    Y despues de las dos, 'cierre_de_caso.cerrar' vuelve a validar las once
    condiciones sobre datos releidos con la fila bloqueada. Que el ciclo haya
    decidido cerrarlo hace un segundo no exime de eso: entre el diagnostico y
    el cierre el proveedor pudo reabrir el ticket.

    QUIEN FIGURA EN LA AUDITORIA
    ----------------------------
    Nadie: 'revisado_por' queda en NULL y el resultado dice que lo cerro el
    Supervisor NOC IA. Es como se distingue lo automatico de lo humano cuando
    alguien pregunte, dentro de seis meses, por que se cerro este caso.
    """
    from operaciones import autonomia, cierre_de_caso
    from operaciones import supervisor as sup_mod

    ahora = ahora or timezone.now()

    #  PUERTA 1  --  el diagnostico, via el nivel que la propuesta declara.
    if propuesta.nivel_autonomia_requerido < NIVEL_PARA_CERRAR:
        return {"intentado": False, "cerrado": False,
                "motivo": "el diagnostico no habilita un cierre automatico"}

    #  PUERTA 2  --  lo que la empresa autorizo. Se consulta aunque la puerta 1
    #  haya pasado: pasar una no exime de la siguiente, que es como funciona la
    #  frontera del motor y por el mismo motivo.
    veredicto = autonomia.puede(org, NIVEL_PARA_CERRAR)
    if not veredicto.get("puede"):
        return {"intentado": False, "cerrado": False,
                "motivo": f"la empresa no lo autoriza: "
                          f"{veredicto.get('motivo') or 'sin motivo'}"}

    #  La aceptacion se persiste ANTES de intentar el cierre, igual que en el
    #  camino humano y por la misma razon medida alli: si la llamada al
    #  proveedor falla, la decision igual quedo registrada y auditada. Al reves,
    #  un fallo de red haria rollback de una decision que si se tomo.
    try:
        sup_mod.revisar(
            propuesta, actor=None, automatico=True,
            decision=PropuestaSupervisor.ACEPTADA,
            comentario=(f"Aceptada automaticamente por {ACTOR_AUTOMATICO}: "
                        f"{(propuesta.motivo or '')[:300]}"),
            ahora=ahora)
        propuesta.refresh_from_db()
    except Exception as e:                                       # noqa: BLE001
        #  El tipo y no el texto: lo mismo que el resto del modulo.
        return {"intentado": False, "cerrado": False,
                "motivo": f"no se pudo registrar la aceptacion "
                          f"({type(e).__name__})"}

    try:
        resultado = cierre_de_caso.cerrar(propuesta, actor=None, ahora=ahora)
    except Exception as e:                                       # noqa: BLE001
        #  'cerrar' promete no levantar por un cierre que no ocurrio, pero una
        #  excepcion inesperada aqui no puede tumbar el ciclo entero: quedan
        #  otras señales por procesar y la propuesta YA esta aceptada.
        return {"intentado": True, "cerrado": False,
                "motivo": f"el cierre fallo ({type(e).__name__})"}

    return {"intentado": True,
            "cerrado": bool(resultado.get("cerrado")),
            "motivo": resultado.get("motivo") or "",
            #  QUE CASO FUE, para que quien corrio el ciclo pueda ir a verlo.
            #  Un conteo --"cerro 3"-- no se puede verificar: hay que poder
            #  abrir esos tres y leer contra que se cerraron. Esto es lo que
            #  pidio el usuario al preguntar "¿como voy a saber cuales cerro?",
            #  y la pregunta estaba bien: hasta ese momento no habia forma.
            "caso_id": str(propuesta.origen_id),
            "propuesta_id": str(propuesta.id),
            "porque": porque_del_cierre(propuesta)}


def porque_del_cierre(propuesta) -> str:
    """
    La razon escrita del diagnostico, sacada de la evidencia de la propuesta.

    Se lee de la EVIDENCIA y no de un campo aparte: es lo que de verdad quedo
    guardado, y lo que alguien va a leer dentro de seis meses.
    """
    for pieza in reversed(propuesta.evidencia or []):
        if isinstance(pieza, dict) and pieza.get("fuente") == "diagnostico":
            return str(pieza.get("dato") or "")
    return ""


def _anotar(senal, veredicto: str, porque: str, diagnostico, ahora) -> None:
    """
    Deja el veredicto en la señal: en la evidencia Y en los datos.

    EN LOS DOS LADOS A PROPOSITO, porque sirven a lectores distintos. La
    evidencia es lo que ve la persona que decide, en el mismo formato que las
    otras siete observaciones del caso. Los datos son lo que lee el codigo de
    la fase siguiente -- y leer un veredicto parseando el texto de una
    evidencia seria exactamente el error que este proyecto llama "el modelo
    compone, el codigo calcula".

    LO QUE NO SE ESCRIBE: el serial del equipo (el ejecutor del motor no lo
    devuelve) ni el nombre del cliente. Esto termina en una propuesta que
    queda guardada, y una propuesta no es lugar para datos de un abonado.
    """
    senal.evidencia.append(sup._observacion(
        "diagnostico", senal.origen_id, f"diagnostico del equipo: {porque}",
        ahora))

    senal.datos["diagnostico_veredicto"] = veredicto
    senal.datos["diagnostico_porque"] = porque
    if isinstance(diagnostico, dict):
        #  Las cinco claves que sostienen el veredicto, y solo esas. Guardar el
        #  diagnostico entero metería campos que nadie decidio guardar el dia
        #  que el ejecutor devuelva uno nuevo.
        senal.datos["diagnostico"] = {
            k: diagnostico.get(k) for k in
            ("estado", "causa_caida", "senal", "senal_dbm", "estado_config")
            if k in diagnostico
        }
