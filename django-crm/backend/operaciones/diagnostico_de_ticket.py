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

from operaciones import lectura_de_ticket
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

Lo que se espera de vos:
- Una HIPÓTESIS de qué le pasa, con su confianza. Si el texto no alcanza para
  tener una, decilo y no inventes.
- Lo que te FALTA para estar seguro, nombrado.
- El RIESGO de que esto siga así.

No propongas mandar una cuadrilla ni cerrar el ticket: eso lo decide una
persona con lo que vos escribas, y proponerlo invitaría a tratarlo como algo
ya resuelto.
"""


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
        return clf.clasificar(contexto, texto=texto_tapado)
    except Exception as e:                                       # noqa: BLE001
        logger.info("Supervisor: no se pudo clasificar la labor (%s)",
                    type(e).__name__)
        return {}


def diagnosticar(org, senales, *, ahora=None, tope=None, concluir=None) -> dict:
    """
    Lee los tickets y deja el diagnostico en la evidencia de cada señal.

    MUTA LAS SEÑALES, igual que 'diagnostico_optico.enriquecer': 'evidencia' y
    'datos' son del llamador, y devolver copias obligaria a que el ciclo las
    volviera a juntar.

    'concluir' SE INYECTA, por lo mismo que 'diagnosticar' en el modulo
    optico: este archivo decide QUE significa un diagnostico, no como se le
    habla a un modelo. Y una prueba puede ejercitar la regla sin red.
    """
    ahora = ahora or timezone.now()
    tope = sup.TOPE_TICKETS_POR_CORRIDA if tope is None else tope

    if concluir is None:
        from operaciones import cerebro

        def concluir(org_, entrada):
            #  SIN 'tools': 'razonar' usa 'chat_herramientas.esquema()' por
            #  defecto, que es el catalogo de solo lectura del Supervisor.
            #  Pasarle una lista propia seria una segunda version del catalogo
            #  que mantener en sincronia con la primera.
            return cerebro.concluir(
                org_, instrucciones=INSTRUCCIONES, entrada=entrada)

    informe = {"leidos": 0, "con_hipotesis": 0, "sin_hipotesis": 0,
               "sin_texto": 0, "errores": 0, "fuera_de_tope": 0}

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
            continue

        labor = _labor_de(org, senal, tapado)
        _anotar(senal, v, labor, ahora)
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


def _anotar(senal, veredicto, labor, ahora) -> None:
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

    if hipotesis:
        senal.evidencia.append(sup._observacion(
            FUENTE, senal.origen_id,
            f"{ETIQUETA_LECTURA}{hipotesis} "
            f"(confianza {confianza or 'sin declarar'})",
            ahora))
    else:
        #  SE ANOTA IGUAL. "Se leyó y no alcanzó" es un resultado, y callarlo
        #  dejaría al ticket con cara de no haber sido mirado nunca.
        senal.evidencia.append(sup._observacion(
            FUENTE, senal.origen_id,
            "se leyó el reclamo y no alcanza para una hipótesis", ahora))

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

    senal.datos["diagnostico_leido"] = True
    senal.datos["diagnostico_hipotesis"] = hipotesis
    senal.datos["diagnostico_confianza"] = confianza
    senal.datos["diagnostico_riesgo"] = riesgo
    senal.datos["labor"] = etiqueta
    senal.datos["labor_verificada"] = bool((labor or {}).get("verificada"))


def le_falta_lectura(propuesta) -> bool:
    """
    Si a esta propuesta todavia no se le leyo el ticket.

    SE MIRA LA EVIDENCIA, que es lo que de verdad tiene o no tiene. Una
    bandera aparte podria quedar puesta sin que la evidencia este, y entonces
    diria que ya se leyo un ticket del que no quedo escrito nada -- el mismo
    criterio que usa 'diagnostico_optico.le_falta_diagnostico'.
    """
    for pieza in (propuesta.evidencia or []):
        if isinstance(pieza, dict) and pieza.get("fuente") == FUENTE:
            return False
    return True


#:  Cuanto de la hipotesis tiene que aparecer en el motivo para dar por hecho
#:  que el juicio la incorporo. No se compara entero: el motivo la envuelve en
#:  una frase y puede recortarla.
TROZO_PARA_RECONOCERLA = 40


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

    SE APAGA SOLA: en cuanto la propuesta se rejuzga, el motivo pasa a contener
    la hipotesis y deja de cumplirse.
    """
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
