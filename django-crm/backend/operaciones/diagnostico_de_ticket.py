# -*- coding: utf-8 -*-
"""
===============================================================================
 EL SUPERVISOR LEE UN TICKET ABIERTO Y DICE QUE LE PASA AL CLIENTE
===============================================================================

QUE RESUELVE
------------
Hasta hoy el Supervisor solo miraba lo que podia MEDIR: un plazo vencido, un
equipo caido, un estado que no coincide. Los tickets abiertos con un tecnico
encima pasaban sin que nadie los leyera, y lo unico que decia que les pasaba
era una frase escrita a mano por quien tomo el reclamo.

Ahora los lee. Y entrega dos cosas, cada una de SU fuente:

    QUE LE PASA     lo dice el modelo, leyendo la descripcion. Es una
                    HIPOTESIS, con su confianza y con lo que le falta.
    A QUIEN VA      lo dice el codigo, con el clasificador que ya existia
                    ('clasificacion_de_trabajo'), que marca si la labor salio
                    de una MEDICION o del texto.

ESA SEPARACION NO ES ESTILO, ES LA REGLA DEL PROYECTO. Un diagnostico que sale
del texto no puede mandar una cuadrilla a manejar hasta una casa -- lo dice el
detector 'CASO_REQUIERE_VISITA' con esas palabras. Lo que el texto produce es
una lectura para que una persona la autorice; lo que la medicion produce puede
seguir su camino sin que nadie opine.

LO QUE SE LE MANDA AL MODELO, Y LO QUE NO
-----------------------------------------
Se le manda la descripcion TAPADA: sin documento, sin telefono, sin correo.
Esta medido que 136 de cada 300 tickets traen una cedula escrita a mano ahi
adentro, y la lista blanca de campos no sirve contra eso -- controla que
campos pasan, no que contiene cada campo.

Y NO SE LE MANDA EL NOMBRE DEL CLIENTE. Ni en el prompt ni en el contexto: un
nombre dentro de una frase no se puede tapar con un patron, asi que lo unico
que se puede hacer es no agregarlo. Ver 'lectura_de_ticket.py'.

NADA DE ESTO LE QUITA INFORMACION A NADIE. El ticket completo se sigue viendo
en Dexter, en WispHub y en la app del tecnico. Lo unico que cambia es lo que
viaja hacia afuera.

UN TOPE POR CORRIDA, Y POR QUE
------------------------------
Cada diagnostico es una consulta al modelo mas las herramientas que consulte.
Leer doscientos tickets en una vuelta dejaria al resto del ciclo esperando. El
tope corta; lo que no entro se lee en la vuelta siguiente, que es dentro de
una hora.

NO LEVANTA POR UN TICKET. Uno que falla se anota y se sigue: el ciclo tiene
otras cosas que hacer, y perder las diecinueve restantes por la numero uno
seria el peor reparto posible.
"""
from __future__ import annotations

import logging

from django.utils import timezone

from operaciones import atascos, lectura_de_ticket
from operaciones import supervisor as sup
from operaciones.models import PropuestaSupervisor

logger = logging.getLogger(__name__)

#:  Con que empieza la observacion que guarda lo leido. Esta en una constante
#:  porque la escribe '_anotar' y la reconoce 'el_juicio_ignora_la_lectura':
#:  dos sitios con la misma cadena escrita a mano se separan sin avisar.
ETIQUETA_LECTURA = "lectura del reclamo: "

#:  La fuente con la que queda marcada la evidencia del diagnostico, para que
#:  quien la lea sepa de donde salio sin tener que interpretar la frase.
FUENTE = "diagnostico_del_ticket"

#:  Lo que el Supervisor tiene que producir. Se le dice en segunda persona y
#:  en español porque es lo que ya hace el resto del sistema, y porque la
#:  frase que escriba la va a leer una persona de operaciones, no un ingeniero.
INSTRUCCIONES = """\
Sos el Supervisor NOC IA de un proveedor de internet.

Te paso la descripción de un ticket de soporte que sigue ABIERTO y que ya
tiene un técnico asignado. Tu trabajo es decir QUÉ LE ESTÁ PASANDO AL CLIENTE,
para que una persona de operaciones decida qué hacer.

Consultá las herramientas antes de afirmar nada del equipo: el estado de la
ONU, la señal, el ping. Un hecho que no salga de una herramienta no es un
hecho y se descarta.

La descripción viene con los datos personales tapados (███). Eso es normal y
no es un dato faltante: no lo reportes como tal y no pidas el documento ni el
teléfono, no los vas a recibir.

EL GRUPO NO DEPENDE DE LA HIPÓTESIS, y son dos preguntas distintas:

    LA HIPÓTESIS   qué le está pasando al equipo. Necesita medirlo. Si no
                   podés leer el equipo, no la tenés, y está bien decirlo.
    EL GRUPO       qué está PIDIENDO el reclamo. Sale del TEXTO solo, y lo
                   podés contestar siempre que el texto diga qué se pide.

Un ticket que dice "No tiene internet, LOS en rojo" es 'falla_de_servicio'
aunque no hayas podido consultar ni una herramienta. Uno que dice "Instalación
TDT" es 'trabajo_pedido' aunque el equipo sea inalcanzable. Uno que dice
"Intervención de la CTO 11-43" es 'obra_de_red' igual.

Que no se haya podido leer el equipo NO es motivo para dejar el grupo vacío.
El único motivo es que el texto no diga qué se pide.

Lo que se espera de vos:
- Una HIPÓTESIS de qué le pasa, con su confianza. Si el texto no alcanza para
  tener una, decilo y no inventes. Eso no te exime del grupo.
- Una RECOMENDACIÓN concreta: QUÉ hay que hacer y A QUIÉN le toca. No "revisar
  el ticket" ni "decidir qué hacer" -- eso no le dice nada a quien lo lee. Si
  el reclamo es de pago, decí que va a cartera y qué hay que confirmar; si es
  una falla de señal, decí que va a correctivo; si el equipo está sano y el
  reclamo es técnico, decí que hay que llamar al cliente y qué preguntarle.
- Lo que te FALTA para estar seguro, nombrado.
- El RIESGO de que esto siga así.

Tu recomendación es una PROPUESTA, no una orden: una persona la autoriza antes
de que pase nada. Por eso podés decir a qué área va y qué hay que hacer -- lo
que no podés es darlo por hecho, ni escribir como si ya estuviera resuelto.
"""


#:  LAS CORRECCIONES DEL USUARIO A LA LECTURA  --  18/10/2026. Van SOLO con la
#:  tarea 'paso_a_despacho.TAREA_CORRECCIONES' delegada ('instrucciones_para'):
#:  le cambian al modelo la forma de leer, y una lectura que mueve el grupo de
#:  una falla a un trabajo pasa por la Fase 4 sin aparecer en la sombra
#:  (auditor de frontera, 19/10/2026). Sin la tarea, las dos claves nuevas se
#:  piden igual --son las que la sombra necesita--, pero estas lineas no.
INSTRUCCIONES_DE_LAS_CORRECCIONES = """
Tres cosas que corrigió la empresa sobre lecturas anteriores:
- Un trabajo en la casa de un cliente que YA tiene el servicio (cambio de
  equipo o de router, cambio de plan, traslado) no es una instalación: la
  instalación es solo para un cliente nuevo.
- Si el ticket trae un cambio YA AUTORIZADO por la empresa (por
  fidelización, por cambio de plan), no lo objetes: medí el equipo y contá lo
  que dé, pero esa decisión ya está tomada.
- Si el ticket dice que el cliente ya probó otro tomacorriente, o que el
  equipo está encendido con LOS en rojo, la falta de energía está descartada
  aunque el equipo figure sin energía: buscá la causa en la fibra.
"""


#:  Con que instrucciones se hizo una lectura: queda en la pieza
#:  ('instrucciones'), y es lo que permite releer al delegar la tarea lo que se
#:  leyo en sombra (auditor independiente, 19/10/2026).
CON_LAS_CORRECCIONES = "correcciones"
SIN_LAS_CORRECCIONES = "base"


def instrucciones_para(org, con_las_correcciones=None) -> str:
    """Las instrucciones de la lectura para esta empresa: las de siempre, mas
    las correcciones del usuario si la tarea esta delegada. Falla cerrado: sin
    poder comprobarlo, las de siempre."""
    if con_las_correcciones is None:
        con_las_correcciones = sup._con_las_correcciones(org)
    if con_las_correcciones:
        return INSTRUCCIONES + INSTRUCCIONES_DE_LAS_CORRECCIONES
    return INSTRUCCIONES


#:  LA VERSION DE LA LECTURA  --  18/10/2026. Sube cuando cambia lo que se le
#:  pide al modelo de una forma que cambia lo que el paso puede decidir. La 2
#:  trae las claves 'accion_autorizada' y 'energia_descartada'
#:  ('paso_a_despacho.CAMPO_PARA_EL_MODELO'), que se piden siempre. Una
#:  lectura sin la clave es de la version 1.
VERSION_DE_LA_LECTURA = 2

#:  Cuantas lecturas MAS se le pagan a una propuesta para ponerla en la version
#:  nueva, por encima de 'MAXIMAS_RELECTURAS'. Dos: una con las claves nuevas,
#:  apenas se despliega, y otra con las instrucciones de las correcciones el
#:  dia que se delegue la tarea. Si el modelo contesta, el criterio se apaga;
#:  si no contesta, el tope corta como en las otras relecturas.
RELECTURAS_POR_VERSION = 2


def _caso_de(senal):
    from cases.models import Case

    return (Case.objects
            .filter(id=senal.origen_id)
            .only("id", "description", "external_service_id",
                  "external_ticket_id")
            .first())


def _labor_de(org, senal, texto_tapado):
    """
    A quien le corresponde, segun el clasificador que YA existe.

    Devuelve el veredicto completo --no solo la labor-- porque trae
    'verificada', que es lo que distingue "lo dice una medicion" de "lo dice
    el texto". Esa diferencia decide si el caso puede seguir camino solo o si
    necesita que una persona lo mire.
    """
    from operaciones import clasificacion_de_trabajo as clf

    from campo.services.despacho import contexto_del_caso

    try:
        contexto = contexto_del_caso(str(senal.origen_id))
    except Exception:                                            # noqa: BLE001
        #  Sin contexto no se abandona: el clasificador tambien sabe leer el
        #  texto, y marca esa labor como NO verificada. Perder la medicion
        #  degrada el resultado; no lo anula.
        contexto = None
    if not isinstance(contexto, dict):
        contexto = {}

    try:
        #  EL CLIENTE DE INSTALACIONES DEL PROVEEDOR  --  18/10/2026,
        #  correccion 1 del usuario: instalacion es solo para un cliente nuevo.
        #  Es el discriminador medido (220 de 220) que ya usan la pantalla de
        #  Despacho y 'supervisor.analizar'; sin el, un trabajo pedido salia
        #  'instalacion' por el texto aunque el cliente ya existiera.
        return clf.clasificar(
            contexto, texto=texto_tapado,
            marcadores={"id_servicio_instalaciones":
                        contexto.get("id_servicio_instalaciones")})
    except Exception as e:                                       # noqa: BLE001
        logger.info("Supervisor: no se pudo clasificar la labor (%s)",
                    type(e).__name__)
        return {}


def diagnosticar(org, senales, *, ahora=None, tope=None, concluir=None,
                 propuestas=None) -> dict:
    """
    Lee los tickets y deja el diagnostico en la evidencia de cada señal.

    MUTA LAS SEÑALES, igual que 'diagnostico_optico.enriquecer': 'evidencia' y
    'datos' son del llamador, y devolver copias obligaria a que el ciclo las
    volviera a juntar.

    'concluir' SE INYECTA, por lo mismo que 'diagnosticar' en el modulo
    optico: este archivo decide QUE significa un diagnostico, no como se le
    habla a un modelo. Y una prueba puede ejercitar la regla sin red.

    'propuestas' ({origen_id: PropuestaSupervisor}) es para DEJAR RASTRO de
    cada lectura: que herramientas pidio el modelo, cuantas vueltas dio, si se
    quedo sin ellas. Sin eso no se puede contestar la pregunta que el 13/10/2026
    nadie pudo contestar -- "¿MIDE el equipo, o solo lee el texto?" -- porque
    'asistente.tool_calls' NO ve este camino: una medicion real hecha ese dia
    desde el chat del Supervisor no quedo ahi, y con ese registro se afirmo
    "nunca se llamo", que era falso.

    Es opcional y no cambia el diagnostico: una señal sin propuesta todavia se
    lee igual, solo que esa lectura no deja fila. En el ciclo real casi todas
    la tienen -- se registran antes de leer.
    """
    ahora = ahora or timezone.now()
    tope = sup.TOPE_TICKETS_POR_CORRIDA if tope is None else tope
    #  Una vez por corrida, como la tarea en el paso: ver
    #  'INSTRUCCIONES_DE_LAS_CORRECCIONES'. Y queda en cada lectura.
    con_las_correcciones = bool(sup._con_las_correcciones(org))

    if concluir is None:
        from operaciones import cerebro

        instrucciones = instrucciones_para(
            org, con_las_correcciones=con_las_correcciones)

        def concluir(org_, entrada):
            from operaciones import paso_a_despacho as pad
            #  SIN 'tools': 'razonar' usa 'chat_herramientas.esquema()' por
            #  defecto, que es el catalogo de solo lectura del Supervisor.
            #  Pasarle una lista propia seria una segunda version del catalogo
            #  que mantener en sincronia con la primera.
            #  'cierre': si el modelo agota sus vueltas consultando, se le
            #  pide que cierre con lo que tiene. Medido el 16/10/2026: 9 de 64
            #  lecturas gastaban sus tres relecturas sin llegar a contestar.
            return cerebro.concluir(
                org_, instrucciones=instrucciones, entrada=entrada,
                campos_extra=pad.CAMPO_PARA_EL_MODELO, cierre=True)

    informe = {"leidos": 0, "con_hipotesis": 0, "sin_hipotesis": 0,
               "sin_texto": 0, "errores": 0, "fuera_de_tope": 0,
               #  El modelo contesto algo que no es un objeto: no se anota
               #  como lectura (ver abajo).
               "respuestas_rotas": 0,
               #  CUANTAS DE LAS LEIDAS MIDIERON EL EQUIPO. Va en el informe
               #  del ciclo --no solo en la tabla-- para que el numero este a
               #  la vista en cada corrida y no haya que ir a buscarlo.
               "midieron": 0, "sin_medir": 0}

    for senal in senales:
        if senal.tipo != PropuestaSupervisor.TICKET_SIN_DIAGNOSTICO:
            continue

        if informe["leidos"] >= tope:
            #  NO SE ANOTA NADA en la señal. Anotar "no se leyo por el tope"
            #  la daria por atendida, y entonces no volveria a entrar NUNCA --
            #  es el mismo error que el modulo optico ya pago y dejo escrito.
            informe["fuera_de_tope"] += 1
            continue

        caso = _caso_de(senal)
        if caso is None:
            informe["errores"] += 1
            continue

        tapado = lectura_de_ticket.tapar(caso.description or "")
        if not tapado:
            informe["sin_texto"] += 1
            continue

        informe["leidos"] += 1
        try:
            v = concluir(org, _entrada(caso, tapado, senal))
        except Exception as e:                                   # noqa: BLE001
            #  El tipo y no el texto: el mensaje de un error del modelo puede
            #  traer de vuelta el prompt, y el prompt lleva la descripcion.
            informe["errores"] += 1
            senal.evidencia.append(sup._observacion(
                FUENTE, senal.origen_id,
                f"no se pudo diagnosticar en esta corrida "
                f"({type(e).__name__}). Se reintenta en la siguiente.", ahora))
            atascos.anotar(org, atascos.FASE_LECTURA, "ia_error", senal.origen_id,
                           type(e).__name__, ahora=ahora)
            continue

        #  EL ATASCO DE LA IA (29/10/2026, 'operaciones/atascos.py'): una
        #  respuesta rota, se cuide o no una lectura anterior, o una lectura
        #  sin hipotesis. El id del caso y un texto fijo: nunca lo que leyo.
        rota = _respuesta_rota(getattr(v, "descartes", None))
        if rota:
            atascos.anotar(org, atascos.FASE_LECTURA, "ia_respuesta_rota", senal.origen_id,
                           atascos.TIPOS["ia_respuesta_rota"][1], ahora=ahora)
        elif not getattr(v, "hipotesis", ""):
            atascos.anotar(org, atascos.FASE_LECTURA, "ia_sin_hipotesis", senal.origen_id,
                           atascos.TIPOS["ia_sin_hipotesis"][1], ahora=ahora)

        if (rota
                and _tiene_un_grupo((propuestas or {}).get(str(senal.origen_id)))):
            #  UNA RESPUESTA ROTA NO PISA UNA LECTURA BUENA  --  19/10/2026. El
            #  modelo no llego a contestar con un objeto, y anotarla como
            #  lectura dejaba un grupo VACIO encima del que la propuesta ya
            #  tenia: la relectura por version del 19/10 lo hizo con el 95531,
            #  que era una falla en rango y quedo "sin grupo". Se deja el rastro
            #  --la fila cuenta para el tope absoluto de relecturas-- y la
            #  lectura anterior sigue valiendo.
            #
            #  SOLO SI HAY UNA LECTURA QUE CUIDAR (auditor independiente, mismo
            #  dia): en un ticket que nunca se leyo, no anotar nada dejaba
            #  'le_falta_lectura' en verdadero para siempre --esa pregunta no
            #  tiene tope-- y se releia cada hora. Sin lectura buena se anota
            #  como antes, con el grupo vacio, y entra el tope de
            #  'le_falta_el_grupo'.
            informe["respuestas_rotas"] += 1
            _dejar_rastro(org, v, senal, propuestas, ahora, informe)
            continue

        labor = _labor_de(org, senal, tapado)
        _anotar(senal, v, labor, ahora,
                con_las_correcciones=con_las_correcciones)
        _dejar_rastro(org, v, senal, propuestas, ahora, informe)
        if getattr(v, "hipotesis", ""):
            informe["con_hipotesis"] += 1
        else:
            informe["sin_hipotesis"] += 1

    return informe


def _entrada(caso, tapado, senal) -> str:
    """
    Lo que el modelo recibe. SIN nombre de cliente y SIN datos de contacto.

    El id de servicio SI va: es con lo que el modelo consulta el equipo, y sin
    el las herramientas no tienen a que preguntarle. Es un identificador
    interno del proveedor, no un dato de la persona.
    """
    dias = senal.datos.get("dias_abierto", 0)
    return (
        f"Ticket {senal.datos.get('ticket') or 'sin número'} del proveedor, "
        f"abierto hace {dias} días.\n"
        f"Servicio: {senal.datos.get('id_servicio') or 'sin id'}\n\n"
        f"Descripción del reclamo (con datos personales tapados):\n{tapado}"
    )


def _anotar(senal, veredicto, labor, ahora, *,
            con_las_correcciones: bool = False) -> None:
    """
    Deja el diagnostico en la evidencia Y en los datos, como el resto.

    LA EVIDENCIA es lo que ve la persona que decide, con la misma forma que
    las otras observaciones del caso. LOS DATOS son lo que lee el codigo de la
    fase siguiente -- y leer un veredicto parseando el texto de una evidencia
    es el error que este proyecto nombra en varios archivos.
    """
    hipotesis = (getattr(veredicto, "hipotesis", "") or "").strip()
    confianza = (getattr(veredicto, "confianza", "") or "").strip()
    falta = list(getattr(veredicto, "falta", []) or [])
    riesgo = (getattr(veredicto, "riesgo", "") or "").strip()

    #  EL JUICIO VIAJA COMO CLAVES, NO SOLO COMO TEXTO  --  14/10/2026
    #  ---------------------------------------------------------------
    #  La observacion lleva el grupo, la labor y la confianza en claves
    #  propias, ademas de la frase que lee una persona. Es el mismo patron que
    #  'diagnostico_optico' ya usa con 'pieza["veredicto"]'.
    #
    #  POR QUE HACE FALTA: lo que decide el paso a Despacho vive en
    #  'senal.datos', y la señal se muere con el ciclo. Sin esto, un ticket que
    #  no pudo pasar hoy --porque una puerta estaba cerrada-- necesita que el
    #  modelo lo lea OTRA VEZ para poder reintentar, y el tope son diez
    #  lecturas por vuelta. Es la misma forma del bug que tenia atascados a los
    #  desincronizados: un dato que solo existia durante la corrida que lo
    #  produjo.
    #
    #  Y se escribe aunque no haya hipotesis: el grupo no depende de ella.
    def _con_el_juicio(pieza: dict) -> dict:
        pieza["grupo"] = str(
            (getattr(veredicto, "extras", None) or {}).get("grupo") or "")
        pieza["labor"] = (labor or {}).get("labor") or ""
        pieza["labor_verificada"] = bool((labor or {}).get("verificada"))
        pieza["labor_porque"] = str((labor or {}).get("porque") or "")
        pieza["confianza"] = confianza
        pieza["confianza_del_grupo"] = str(
            (getattr(veredicto, "extras", None) or {}).get(
                "confianza_del_grupo") or "")
        #  LAS CORRECCIONES DEL USUARIO  --  18/10/2026. Lo que 'cerebro' ya
        #  dejo pasar por la lista cerrada, o vacio. Las lee 'paso_a_despacho'.
        for clave in ("accion_autorizada", "energia_descartada"):
            pieza[clave] = str(
                (getattr(veredicto, "extras", None) or {}).get(clave) or "")
        pieza["version"] = VERSION_DE_LA_LECTURA
        pieza["instrucciones"] = (CON_LAS_CORRECCIONES if con_las_correcciones
                                  else SIN_LAS_CORRECCIONES)
        return pieza

    if hipotesis:
        senal.evidencia.append(_con_el_juicio(sup._observacion(
            FUENTE, senal.origen_id,
            f"{ETIQUETA_LECTURA}{hipotesis} "
            f"(confianza {confianza or 'sin declarar'})",
            ahora)))
    else:
        #  SE ANOTA IGUAL. "Se leyó y no alcanzó" es un resultado, y callarlo
        #  dejaría al ticket con cara de no haber sido mirado nunca.
        senal.evidencia.append(_con_el_juicio(sup._observacion(
            FUENTE, senal.origen_id,
            "se leyó el reclamo y no alcanza para una hipótesis", ahora)))

    if falta:
        senal.evidencia.append(sup._observacion(
            FUENTE, senal.origen_id,
            "falta para estar seguro: " + "; ".join(str(f) for f in falta[:3]),
            ahora))

    #  LA LABOR, CON SU PROCEDENCIA. 'verificada' distingue "lo dice una
    #  medición del equipo" de "lo dice el texto", y esa diferencia es la que
    #  decide si esto puede seguir camino solo.
    etiqueta = (labor or {}).get("labor") or ""
    if etiqueta:
        verificada = bool((labor or {}).get("verificada"))
        senal.evidencia.append(sup._observacion(
            FUENTE, senal.origen_id,
            f"corresponde a {etiqueta}"
            + (" (lo sostiene una medición del equipo)" if verificada
               else " (surge del texto del reclamo, no de una medición)"),
            ahora))

    #  LA PROPUESTA DEL MODELO, que es lo que la pantalla muestra en grande.
    #
    #  NO VIAJABA hasta el 13/10/2026, y el efecto se vio mirando la pantalla:
    #  "¿Qué propone el Supervisor NOC IA? -- Decidir qué se hace con este
    #  ticket, que sigue abierto". Eso no es una propuesta, es devolverle la
    #  pregunta a quien la hizo. Y el Supervisor ya tenia la respuesta escrita
    #  dos bloques mas abajo: "está frenado en la validación del pago, no en
    #  una falla técnica".
    #
    #  'cerebro.validar' ya la protege: una recomendacion sin NINGUN hecho
    #  obtenido de una herramienta se descarta sola --"recomendar sobre nada es
    #  la forma mas limpia de inventar"--. O sea que para proponer algo hay que
    #  haber ido a buscar informacion primero, que es exactamente la regla que
    #  se quiere.
    senal.datos["accion_sugerida"] = (
        getattr(veredicto, "recomendacion", "") or "").strip()
    senal.datos["diagnostico_leido"] = True
    senal.datos["diagnostico_hipotesis"] = hipotesis
    senal.datos["diagnostico_confianza"] = confianza
    senal.datos["diagnostico_riesgo"] = riesgo
    senal.datos["labor"] = etiqueta
    senal.datos["labor_verificada"] = bool((labor or {}).get("verificada"))
    senal.datos["labor_porque"] = str((labor or {}).get("porque") or "")

    #  EN QUE GRUPO CAE, segun el modelo  --  14/10/2026
    #
    #  Viene de 'veredicto.extras' y no de un campo propio del veredicto
    #  porque el grupo lo conoce ESTE camino, no el cerebro generico. Y pasa
    #  por la lista cerrada de 'paso_a_despacho.GRUPOS': un valor inventado ya
    #  fue descartado en 'cerebro', asi que lo que llega aca esta en la lista
    #  o no esta -- nunca es "el que mas se parecia".
    #
    #  La AUSENCIA es un valor con significado: "el modelo no supo", y manda
    #  el ticket a una persona. No se completa con un default.
    _extras = getattr(veredicto, "extras", None) or {}
    senal.datos["grupo"] = str(_extras.get("grupo") or "")
    #  LA CONFIANZA DEL GRUPO, que NO es 'diagnostico_confianza'. Esa habla de
    #  la hipotesis sobre la causa; esta, de que tan claro esta el pedido. La
    #  medicion que separo las dos esta en 'paso_a_despacho'.
    senal.datos["confianza_del_grupo"] = str(
        _extras.get("confianza_del_grupo") or "")


def _tiene_un_grupo(propuesta) -> bool:
    """Si la propuesta ya tiene una lectura con el grupo puesto."""
    if propuesta is None:
        return False
    from operaciones import paso_a_despacho as pad

    ultima = pad._ultima_lectura_con_grupo(propuesta)
    return bool(ultima and str(ultima.get("grupo") or "").strip())


def le_falta_lectura(propuesta) -> bool:
    """
    Si a esta propuesta todavia no se le leyo el ticket.

    SE MIRA LA EVIDENCIA, que es lo que de verdad tiene o no tiene. Una
    bandera aparte podria quedar puesta sin que la evidencia este, y entonces
    diria que ya se leyo un ticket del que no quedo escrito nada -- el mismo
    criterio que usa 'diagnostico_optico.le_falta_diagnostico'.

    NO MIRA SI LA LECTURA ESTA COMPLETA, y eso es deliberado. Hay dos
    preguntas parecidas y cada una tiene su funcion, porque mezclarlas borra
    los casos que hay que distinguir:

        le_falta_lectura            no hay NINGUNA evidencia de lectura
        el_juicio_ignora_la_lectura la lectura esta, y el resumen la contradice
        le_falta_el_grupo           la lectura esta, y es de antes de que se
                                    guardara el grupo (14/10/2026)

    La primera version del tercer caso se metio DENTRO de esta funcion y una
    guarda lo encontro: su mensaje decia "el criterio viejo no la ve como
    pendiente, que es justo por lo que hacia falta uno nuevo". Tenia razon.
    """
    for pieza in (propuesta.evidencia or []):
        if isinstance(pieza, dict) and pieza.get("fuente") == FUENTE:
            return False
    return True


def le_falta_el_grupo(propuesta) -> bool:
    """
    Si la lectura que esta guardada es de ANTES de que se guardara el grupo.

    EL LIMBO QUE CIERRA  --  14/10/2026
    -----------------------------------
    Ese dia la lectura empezo a guardar el GRUPO del ticket, que es lo que el
    paso a Despacho necesita para decidir. Las 80 propuestas que ya existian se
    habian leido antes, asi que tenian la frase y no la clave -- y quedaban con
    las dos puertas cerradas:

        tienen lectura          ->  no eran candidatas a leerse de nuevo
        su lectura no da grupo  ->  el paso no podia decidirlas

    El sintoma seria el de siempre --"ejecute el ciclo y no se movio nada"--
    sin un error en ningun log, y para siempre.

    EL COSTO ES REAL y conviene saberlo: volver a leer cuesta una consulta al
    modelo por ticket, con el tope de 'TOPE_TICKETS_POR_CORRIDA' por vuelta. Se
    paga una vez; de los tickets nuevos en adelante el grupo ya viene.

    LO QUE NO SE HACE, y es deliberado: deducir el grupo del texto de la frase
    vieja. Es texto libre escrito para que lo lea una persona, y clasificar un
    ticket interpretandolo es exactamente lo que este modulo existe para
    evitar. Mejor pagar la relectura que inventar una clasificacion.

    SIN NINGUNA LECTURA devuelve False: ese caso es de 'le_falta_lectura', y
    contestar las dos cosas desde aca es lo que ya salio mal una vez.
    """
    hay_lectura = False
    ultima_con_clave = None
    for pieza in (propuesta.evidencia or []):
        if isinstance(pieza, dict) and pieza.get("fuente") == FUENTE:
            hay_lectura = True
            if "grupo" in pieza:
                #  LA MAS RECIENTE GANA, igual que en 'de_la_propuesta': la
                #  evidencia se acumula y la ultima describe la situacion de
                #  hoy. Antes esto cortaba en la PRIMERA que tuviera la clave.
                ultima_con_clave = pieza

    if ultima_con_clave is not None:
        if str(ultima_con_clave.get("grupo") or "").strip():
            return False
        #  LA CLAVE ESTA PERO VINO VACIA  --  15/10/2026
        #  ---------------------------------------------
        #  Ese dia se midio que 15 de 44 propuestas tenian 'grupo' en blanco y
        #  quedaban en el mismo limbo que este modulo ya habia cerrado una vez,
        #  solo que una capa mas adentro:
        #
        #      la clave esta        ->  no eran candidatas a releerse
        #      su valor esta vacio  ->  el paso las mandaba a una persona
        #
        #  La causa de los 15 no era el texto --decian "No tiene internet, LOS
        #  en rojo"-- sino que el modelo, al no poder leer el equipo
        #  ('onu_no_vinculada'), se callaba tambien el grupo. Corregidas las
        #  instrucciones, releerlas devolvio grupo en 14 de 15.
        #
        #  CON EL TOPE PUESTO, y no es precaucion de adorno: un ticket cuyo
        #  texto de verdad no diga que se pide va a volver vacio siempre, y sin
        #  tope volveria a la cola en cada vuelta para siempre. Es exactamente
        #  el bucle de 43 lecturas sobre 11 propuestas que 'MAXIMAS_RELECTURAS'
        #  ya mide. Despues de tres intentos se deja como esta y la mira una
        #  persona, que es la respuesta correcta para un texto que no dice nada.
        return _cuantas_veces_se_leyo(propuesta) < MAXIMAS_RELECTURAS

    return hay_lectura


def le_falta_la_version(propuesta, *,
                        con_las_correcciones: bool = False) -> bool:
    """
    Si la lectura guardada es de una version anterior y la nueva puede cambiar
    lo que el paso decide.  --  18/10/2026, correcciones del usuario.

    SOLO LAS QUE PUEDEN CAMBIAR. Las claves nuevas deciden sobre una falla que
    la medicion FRENA ('paso_a_despacho.la_medicion_frena'): un trabajo ya
    autorizado, o la energia descartada por el ticket. Releer las demas
    gastaria el tope de la vuelta en tickets que la lectura nueva no mueve.

    CON TOPE: 'RELECTURAS_POR_VERSION' por encima de 'MAXIMAS_RELECTURAS',
    contadas como las demas. Una lectura que contesta trae la version y apaga
    el criterio; una que no contesta, no lo repite para siempre.

    Y CON LA TAREA DELEGADA, tambien la que se leyo sin sus instrucciones
    (auditor independiente, 19/10/2026): desplegado en sombra, estas fallas se
    releen con las claves nuevas pero sin las instrucciones de las
    correcciones, y sin esto ya no se volvian a leer cuando el usuario las
    encendiera.
    """
    from operaciones import paso_a_despacho as pad

    ultima = pad._ultima_lectura_con_grupo(propuesta)
    if ultima is None or ultima.get("grupo") != pad.FALLA_DE_SERVICIO:
        return False
    version = ultima.get("version")
    if (isinstance(version, int) and not isinstance(version, bool)
            and version >= VERSION_DE_LA_LECTURA
            and not (con_las_correcciones
                     and ultima.get("instrucciones") != CON_LAS_CORRECCIONES)):
        return False
    if not pad.la_medicion_frena(pad.ultima_medicion(propuesta)):
        return False
    return (_cuantas_veces_se_leyo(propuesta)
            < MAXIMAS_RELECTURAS + RELECTURAS_POR_VERSION)


def hay_que_releer(propuesta, *, con_las_correcciones: bool = False) -> bool:
    """
    Si a esta propuesta le falta una lectura que el paso necesita: ninguna,
    una sin el grupo, o una de una version que ya no alcanza.

    UN SOLO LUGAR  --  18/10/2026. Los dos sitios del ciclo que eligen que leer
    llamaban a 'le_falta_lectura' y 'le_falta_el_grupo' por separado, con un
    comentario que pedia que un tercer criterio fallara en los dos a la vez.
    El tercero llego, y ahora es una funcion.
    """
    return (le_falta_lectura(propuesta) or le_falta_el_grupo(propuesta)
            or le_falta_la_version(
                propuesta, con_las_correcciones=con_las_correcciones))


#:  Cuanto de la hipotesis tiene que aparecer en el motivo para dar por hecho
#:  que el juicio la incorporo. No se compara entero: el motivo la envuelve en
#:  una frase y puede recortarla.
TROZO_PARA_RECONOCERLA = 40

#:  Cuantas veces se relee una propuesta antes de dejarla como esta. Tres es
#:  suficiente para absorber un fallo puntual --el modelo cortado, una
#:  herramienta caida-- y corta el bucle antes de que cueste.
#:
#:  NO ES UN NUMERO PRUDENTE AL AZAR: medido el 14/10/2026, sin tope fueron 43
#:  lecturas sobre 11 propuestas en una madrugada, cada una con su consulta al
#:  modelo.
MAXIMAS_RELECTURAS = 3


def _cuantas_veces_se_leyo(propuesta) -> int:
    """
    Cuantas veces se LEYO esta propuesta, se haya guardado o no el resultado.

    SE CUENTAN LOS RAZONAMIENTOS Y NO LA EVIDENCIA, y la diferencia es la que
    hace que el tope sirva: el bucle del 14/10/2026 existia JUSTAMENTE porque
    la lectura no llegaba a la evidencia --43 razonamientos y solo 8 propuestas
    con su pieza--. Un contador que mire la evidencia se queda en cero en ese
    caso y no corta nada. El razonamiento, en cambio, queda siempre.

    UNA RESPUESTA QUE NO SE PUDO LEER NO ES UNA LECTURA  --  16/10/2026. Nueve
    propuestas tenian sus tres relecturas gastadas en respuestas que 'validar'
    descarto enteras ("no es un objeto JSON"): el modelo nunca llego a
    contestar, y el tope las dejaba para siempre sin grupo. Esas no cuentan.
    CON UN TOPE ABSOLUTO del doble, para que un modelo que nunca conteste no
    vuelva al bucle de las 43 lecturas: ahi si se deja como esta.
    """
    try:
        from operaciones.razonamiento_modelos import (FuenteRazonamiento,
                                                      RazonamientoSupervisor)

        descartes = list(RazonamientoSupervisor.objects.filter(
            propuesta=propuesta,
            fuente=FuenteRazonamiento.LECTURA_TICKET,
        ).values_list("descartes", flat=True))
    except Exception:                                        # noqa: BLE001
        #  Sin poder contar se cuenta cero, como antes de esta fase: las
        #  pruebas sin base pasan propuestas falsas. El tope absoluto de arriba
        #  NO alcanza a este camino: con la tabla caida se releeria en cada
        #  vuelta, igual que antes (auditor de frontera, 16/10/2026).
        return 0
    if len(descartes) >= MAXIMAS_RELECTURAS * 2:
        return len(descartes)
    return sum(1 for d in descartes if not _respuesta_rota(d))


def _respuesta_rota(descartes) -> bool:
    """
    Si en esa lectura el modelo no llego a contestar con un objeto: el
    descarte es el de 'cerebro.validar', leido de su constante. Cualquier otro
    descarte es una lectura que si contesto, y cuenta.
    """
    from operaciones import cerebro

    return any(cerebro.DESCARTE_SIN_OBJETO in str(d) for d in (descartes or []))


def el_juicio_ignora_la_lectura(propuesta) -> bool:
    """
    Si esta propuesta ya fue leida pero su resumen no lo dice.

    DE DONDE SALE, Y POR QUE HACE FALTA UN SEGUNDO CRITERIO
    -------------------------------------------------------
    'le_falta_lectura' pregunta si hay evidencia de lectura. Las 52 propuestas
    que estaban vivas el 13/10/2026 SI la tienen -- y su resumen igual decia
    "se leyo el reclamo y no alcanza para una hipotesis", porque se escribio
    antes de leer y hasta ese dia nadie lo volvia a tocar.

    Para esas, 'le_falta_lectura' dice que no falta nada y quedarian con el
    texto viejo para siempre. Este criterio las encuentra.

    SE COMPARAN DOS TEXTOS QUE YA ESTAN, no se parsea un veredicto desde la
    evidencia: eso es justo lo que '_anotar' advierte que no se haga, y por eso
    el veredicto viaja aparte en los datos de la señal. Lo unico que se
    pregunta aca es si el resumen menciona lo que la lectura encontro.

    NO SE APAGA SOLA, Y ESO COSTO UN BUCLE  --  14/10/2026
    -------------------------------------------------------
    Se escribio creyendo que si: "en cuanto la propuesta se rejuzga, el motivo
    pasa a contener la hipotesis y deja de cumplirse". Falso cuando la relectura
    NO encuentra nada -- ahi el motivo no la menciona nunca, y la propuesta
    vuelve a la cola en cada vuelta.

    MEDIDO esa madrugada: 43 lecturas sobre 11 propuestas. Las mismas, cuatro
    veces cada una, con su consulta al modelo y sus herramientas cada vez. Nadie
    lo noto porque el sintoma era "no avanza", no "gasta".

    Por eso el tope: despues de 'MAXIMAS_RELECTURAS' intentos se deja como esta.
    Una propuesta con el resumen viejo es un problema; una que se relee para
    siempre es peor, y ademas desplaza de la cola a los tickets que nadie miro.
    """
    if _cuantas_veces_se_leyo(propuesta) >= MAXIMAS_RELECTURAS:
        return False

    motivo = (getattr(propuesta, "motivo", "") or "")
    for pieza in (propuesta.evidencia or []):
        if not isinstance(pieza, dict) or pieza.get("fuente") != FUENTE:
            continue
        dato = str(pieza.get("dato") or "")
        if not dato.startswith(ETIQUETA_LECTURA):
            #  "falta para estar seguro" y "no alcanza" tambien se anotan con
            #  esta fuente, y no son una hipotesis que el motivo deba citar.
            continue
        hipotesis = dato[len(ETIQUETA_LECTURA):].strip()
        if hipotesis[:TROZO_PARA_RECONOCERLA] not in motivo:
            return True
    return False


def guardar_en_propuesta(propuesta, senal, ahora=None) -> None:
    """
    Pasa a la propuesta la evidencia que 'diagnosticar' dejo en la señal.

    SE AGREGA, NO SE REEMPLAZA, y es lo contrario de lo que hace el modulo
    optico. Alla una relectura CORRIGE un diagnostico anterior y dejar los dos
    confundiria sobre cual vale. Aca cada lectura es un momento del ticket, y
    el cliente pidio exactamente eso: "si el supervisor lee el mismo ticket
    mañana y la situacion cambio, agrega uno nuevo dejando ver un flujo del
    seguimiento del ticket".

    Lo que para un diagnostico de equipo seria ruido, para el seguimiento de un
    reclamo es la historia.

    SE INTENTO FILTRAR LAS REPETIDAS Y NO SE PUEDE ASI  --  13/10/2026
    -------------------------------------------------------------------
    Un ticket de reconexion quedo con DOS lecturas de la misma tarde diciendo
    lo mismo con otras palabras ("solicita la reconexion pagando el costo" /
    "solicita la reconexion abonando el costo"), y se probo descartar la
    segunda comparando cuanto se parecian los textos.

    MEDIDO sobre los textos reales, y el resultado cierra esa puerta:

        las dos lecturas REPETIDAS      0.576
        una lectura vs un CAMBIO REAL   0.565
        dos "falta para estar seguro"
          que dicen lo mismo            0.339

    Son el mismo numero. NO existe un umbral que separe "repite" de "paso algo
    nuevo": el que tapara la repeticion taparia tambien la noticia --que el
    cliente pago y el servicio sigue caido--, que es justo lo que el historial
    existe para mostrar. Y dos listas de "lo que falta" que dicen lo mismo se
    parecen MENOS entre si que una lectura y un cambio real.

    Por eso se agrega siempre, como pedia el cliente. La duplicacion que se vio
    venia de una RELECTURA --no de leer dos veces porque si-- y esa se dispara
    una sola vez por propuesta: el criterio que la pide se apaga en cuanto el
    resumen cita la lectura. Lo que quedo duplicado de antes se limpia aparte.
    """
    nuevas = [p for p in (senal.evidencia or [])
              if isinstance(p, dict) and p.get("fuente") == FUENTE]
    if not nuevas:
        return

    propuesta.evidencia = list(propuesta.evidencia or []) + nuevas
    propuesta.updated_at = ahora or timezone.now()
    campos = ["evidencia", "updated_at"]

    #  Y SE REESCRIBE EL JUICIO, que es lo que faltaba  --  13/10/2026
    #  ---------------------------------------------------------------
    #  El ciclo registra la propuesta ANTES de leer el ticket: primero cierra
    #  lo que ya esta resuelto, despues lee lo que sigue abierto. Asi que el
    #  motivo nace escrito sin la lectura, y hasta hoy nadie lo volvia a tocar.
    #
    #  MEDIDO EN PRODUCCION, en la primera propuesta que alguien abrio: el
    #  texto de arriba decia "se leyo el reclamo y no alcanza para una
    #  hipotesis" mientras la evidencia de abajo traia la hipotesis entera
    #  --degradacion del enlace optico, -26.19 dBm--. Las dos cosas en la misma
    #  pantalla, contradiciendose.
    #
    #  Eso es peor que no haber leido: quien lee el resumen y no baja hasta la
    #  evidencia decide sobre lo contrario de lo que el sistema averiguo. Por
    #  eso se vuelve a juzgar con la señal YA enriquecida, en vez de dejar el
    #  texto viejo al lado del dato nuevo.
    from operaciones import supervisor as sup

    try:
        juicio = sup.analizar(senal)
    except Exception as e:                                       # noqa: BLE001
        #  Un juicio que no se pudo rehacer deja el anterior, que es viejo pero
        #  no inventado. La evidencia nueva se guarda igual.
        logger.info("Supervisor: no se pudo rejuzgar el ticket (%s)",
                    type(e).__name__)
        juicio = None

    if juicio:
        propuesta.motivo = juicio["motivo"]
        propuesta.accion_propuesta = juicio["accion_propuesta"]
        propuesta.prioridad = juicio["prioridad"]
        propuesta.impacto = juicio.get("impacto", propuesta.impacto)
        campos += ["motivo", "accion_propuesta", "prioridad", "impacto"]

    propuesta.save(update_fields=campos)


#:  Las herramientas que MIDEN el equipo, y no las que solo lo describen. Es
#:  lista BLANCA a proposito: una herramienta nueva no cuenta como medicion
#:  hasta que alguien decida que lo es. Al reves --lista negra-- cualquier
#:  herramienta agregada despues inflaria el numero sin que nadie lo note.
HERRAMIENTAS_QUE_MIDEN = frozenset({
    "diagnosticar_servicio",      # estado optico + señal + causa de caida
    "ping_cliente",               # responde o no responde
    "consultar_senal_ont",
    "consultar_estado_ont",
    "diagnosticar_falla_ont",
    "consultar_estabilidad_enlace",
})


def midio_el_equipo(herramientas) -> bool:
    """
    Si en esta lectura se fue a BUSCAR el dato en vez de leerlo del texto.

    LA DISTINCION QUE MOTIVO TODO ESTO (13/10/2026): una hipotesis puede
    nombrar '-26.19 dBm' porque lo midio o porque ese numero venia escrito en
    la descripcion del ticket --WispHub embebe un panel con la señal en el
    cuerpo del reclamo--. Las dos frases se leen igual y valen cosas muy
    distintas: la primera es una medicion, la segunda es una cita.
    """
    return bool(HERRAMIENTAS_QUE_MIDEN & set(herramientas or ()))


def _dejar_rastro(org, veredicto, senal, propuestas, ahora, informe) -> None:
    """
    Deja la fila de ESTA lectura: que pidio el modelo y cuanto le costo.

    NO PUEDE TUMBAR EL DIAGNOSTICO. Una bitacora que rompe el trabajo que
    estaba registrando es peor que no tenerla -- mismo criterio que
    'razonamiento.registrar', que ya se traga sus propios errores.
    """
    r = getattr(veredicto, "razonamiento", None)
    usadas = list(getattr(r, "herramientas_usadas", ()) or ()) if r else []

    if midio_el_equipo(usadas):
        informe["midieron"] = informe.get("midieron", 0) + 1
    else:
        informe["sin_medir"] = informe.get("sin_medir", 0) + 1

    propuesta = (propuestas or {}).get(str(senal.origen_id))
    if propuesta is None:
        #  Sin propuesta no hay a que colgar la fila: la base lo rechaza y
        #  'registrar' devuelve None. El contador de arriba ya conto igual.
        return
    try:
        from operaciones import razonamiento
        from operaciones.razonamiento_modelos import FuenteRazonamiento

        razonamiento.registrar(
            org, veredicto,
            fuente=FuenteRazonamiento.LECTURA_TICKET,
            propuesta=propuesta, ahora=ahora)
    except Exception as e:                                   # noqa: BLE001
        logger.info("Supervisor: no se pudo registrar la lectura (%s)",
                    type(e).__name__)
