# -*- coding: utf-8 -*-
"""
===============================================================================
 EL CICLO DEL SUPERVISOR, CORRIENDO SOLO  --  cada hora, sin que nadie mire
===============================================================================

QUE CIERRA
----------
El Supervisor ya sabe diagnosticar un caso desincronizado y cerrarlo. Lo que
faltaba era que lo hiciera sin que una persona apretara "Ejecutar ciclo":
mientras eso dependiera del boton, un caso que apareciera un sabado a la noche
esperaba al lunes.

POR QUE AQUI Y NO EN EL RELOJ DEL MOTOR  --  medido el 08/10/2026
------------------------------------------------------------------
Primero se construyo del otro lado: un trabajo en 'nucleo/programador' que le
pegara por HTTP a una ruta propia del CRM. Ese camino quedo completo y NUNCA
SE PUDO ENCENDER, por una razon que no es de codigo:

    el reloj reclama turnos en 'asistente.job_catalogo', y para tocar esa
    tabla hace falta el rol 'scheduler_coordinator'. Ese rol existe desde
    202609141200 y no esta concedido a nadie. Conceder un rol exige la opcion
    ADMIN sobre el, y NINGUNA credencial de los tres contenedores la tiene:

        motor / motor-reloj   motor_user     -> permission denied
        backend / celery      crm_migrator   -> "Only roles with the ADMIN
                                                 option on role
                                                 'scheduler_coordinator' may
                                                 grant this role"

    La credencial que creo esos roles --la que es dueña del esquema
    'asistente'-- no esta en ningun contenedor, y conseguirla es un gesto de
    infraestructura, no de despliegue.

Pero el ciclo no necesitaba nada de eso. Es codigo del CRM, sobre tablas del
CRM, y 'crm_user' --con el que corre este worker-- ya puede todo lo que hace
falta. El trabajo del motor y su ruta se BORRARON ese mismo dia: un camino que
nadie usa y nadie corre se pudre en silencio, y la ruta ademas pedia solo
'IsAuthenticated' --mas flojo que el 'EsJefeDeOperaciones' del boton-- para
hacer exactamente lo mismo. El CRM ademas YA TIENE un reloj andando: 'celery-beat', con 12 tareas
programadas desde antes, una de ellas cada 5 minutos. Pasar por el motor para
volver a entrar al CRM era un rodeo que ademas pedia un permiso nuevo.

La leccion, que vale mas que el arreglo: el permiso que no se consigue suele
ser la señal de que la pieza esta del lado equivocado de la frontera.

LAS TRES PUERTAS SIGUEN INTACTAS, y esto no abre ninguna
--------------------------------------------------------
Que el ciclo corra solo no le agrega una sola facultad. Para que un caso se
cierre siguen teniendo que estar las tres:

    1. la tarea delegada por una persona desde el chat
    2. el nivel de autonomia de la empresa en 3, puesto con motivo
    3. el diagnostico optico de ESE caso, favorable

Esta tarea es la primera puerta aplicada a si misma: recorre UNICAMENTE las
empresas que delegaron 'CICLO_AUTOMATICO'. Sin esa fila no mira nada. Y aunque
corra, si 'CERRAR_DESINCRONIZADOS' no esta delegada, el ciclo deja propuestas
para que las lea una persona y no cierra nada -- que es lo que el Supervisor
hacia cuando alguien apretaba el boton.

LA TRAMPA DEL RLS, que en este archivo esta resuelta por medicion
-----------------------------------------------------------------
Un worker de Celery NO pasa por el middleware que fija 'app.current_org'. Una
tabla con RLS forzada consultada sin ese contexto devuelve CERO FILAS SIN
NINGUN ERROR: no falla, no hace nada, y no lo registra. Es exactamente como
'purge_read_notifications' borro cero filas todas las noches durante meses
(ver 'common/tasks.py'), y es la primera cosa que habia que medir aqui.

Medido el 08/10/2026 contra 'common/rls/__init__.py::ORG_SCOPED_TABLES', que
es la lista de la que salen las politicas --no las migraciones, que solo las
aplican-- sobre sus 65 tablas:

    organization                        SIN politica
    operaciones_tarea_delegada          SIN politica
    case                                CON politica
    operaciones_propuesta_supervisor    CON politica

De ahi sale la forma de esta tarea, y no es estetica:

    el descubrimiento de empresas lee 'TareaDelegada' y 'Org', que NO tienen
    politica, asi que se pueden consultar antes de fijar contexto -- es lo
    unico que se puede hacer sin contexto, y por eso es lo primero. Si 'Org'
    la tuviera, el bucle no veria ni una empresa;

    el ciclo de cada empresa toca 'PropuestaSupervisor' y 'Case', que SI la
    tienen, asi que va despues de 'set_rls_context(org.id)' y nunca antes.

Invertir ese orden no daria error: daria cero casos para siempre.

AL FINAL SE LIMPIA EL CONTEXTO. 'app.current_org' se fija a nivel de SESION,
sobrevive a la transaccion, y la conexion del worker se reusa para la tarea
siguiente. Dejar la ultima empresa puesta significaria que la proxima tarea que
caiga en esa conexion --cualquiera de las otras 12-- arranca creyendo que es de
esa empresa. Mismo cierre que hace 'scan_for_breached_cases'.
"""
from __future__ import annotations

import logging

from celery import shared_task

from common.models import Org
from common.tasks import clear_rls_context, set_rls_context

logger = logging.getLogger(__name__)


@shared_task
def ciclo_del_supervisor():
    """
    Una pasada del Supervisor por cada empresa que lo haya delegado.

    NO LEVANTA por una empresa: un fallo en la primera no puede dejar sin
    revisar a las demas. Cada una se registra y se sigue -- un ciclo que se
    cae entero porque SmartOLT no contesto para un cliente seria la clase de
    fallo que nadie nota hasta que alguien pregunta por que no se cerro nada.

    Devuelve el conteo Y POR QUE NO CERRO, que no es lo mismo. "Corrio y
    cerro 0" tiene dos lecturas incompatibles --no habia nada que cerrar, o
    habia y no pudo-- y un numero solo no las distingue. Medido el 08/10/2026:
    la primera corrida real en produccion devolvio 'cerrados: 0' y no hubo
    forma de saber cual de las dos era sin abrir otra consulta.

    Dos mapas, porque son dos cosas distintas y conviene no fundirlas:

        no_evaluados_por   el diagnostico no habilito siquiera evaluar el
                           cierre -- señal debil, caida por fibra, equipo sin
                           registrar en SmartOLT. Viene de 'motivos'.
        no_cerrados_por    el cierre SE INTENTO y no salio -- una de las tres
                           puertas, o la validacion con la fila bloqueada.
                           Viene de 'motivos_de_no_cierre'.

    Los dos son claves tecnicas y conteos, nunca casos: sin un solo dato de
    cliente, porque esto va a un log y al resultado en Redis.
    """
    from operaciones import supervisor, tareas_delegadas as td
    from operaciones.tareas_modelos import TareaDelegada

    #  LA PUERTA, y es la primera consulta a proposito: 'TareaDelegada' no
    #  tiene politica de RLS (medido, ver el encabezado), asi que es lo unico
    #  que se puede leer antes de fijar contexto. Las empresas que no delegaron
    #  el ciclo no entran: no se las recorre y se decide despues, no se las
    #  recorre.
    org_ids = (TareaDelegada.objects
               .filter(clave=td.CICLO_AUTOMATICO, activa=True)
               .values_list("org_id", flat=True)
               .distinct())
    org_ids = list(org_ids)
    if not org_ids:
        #  Se registra, y la frase importa: "nadie lo delego" no es lo mismo
        #  que "no habia nada que hacer". La primera se arregla desde el chat.
        logger.info("Supervisor: ningun ciclo delegado, no se recorre nada")
        #  MISMA FORMA que la salida normal, con los mapas vacios. Una salida
        #  que a veces trae dos claves y a veces cuatro obliga a quien la lee
        #  a adivinar cual recibio.
        return {"empresas": 0, "cerrados": 0,
                "no_evaluados_por": {}, "no_cerrados_por": {}}

    empresas = 0
    cerrados = 0
    #  SE SUMAN ENTRE EMPRESAS. Un motivo es una clave tecnica compartida
    #  ('NO_DELEGADO', 'NIVEL_INSUFICIENTE', ...), no algo de una empresa, asi
    #  que el total agregado sigue siendo legible y no nombra a nadie.
    no_evaluados: dict[str, int] = {}
    no_cerrados: dict[str, int] = {}
    #  EL 'finally' NO ES PRECAUCION DE ADORNO: lo pide el docstring de
    #  'clear_rls_context' con esas palabras --"always paired with
    #  set_rls_context in a finally"-- y el hueco que cierra es estrecho pero
    #  real. El 'try' de cada empresa atrapa lo que falle DENTRO del ciclo;
    #  lo que se escape de aqui --la propia iteracion del queryset, un
    #  SoftTimeLimit, un apagado del worker-- se iria con la ultima empresa
    #  todavia puesta en 'app.current_org'. Y esa variable es de SESION: la
    #  conexion vuelve al pool con ella, y la proxima tarea que la tome
    #  --cualquiera de las otras 12-- arranca creyendo que es de esa empresa.
    try:
        for org in Org.objects.filter(id__in=org_ids):
            #  EL CONTEXTO, antes de tocar 'Case' o 'PropuestaSupervisor'. Sin
            #  esto la RLS devuelve cero filas y el ciclo informaria "sin
            #  casos" siendo que no pudo verlos.
            set_rls_context(org.id)
            try:
                #  DESATENDIDO: nadie esta esperando esta corrida, asi que el
                #  tope corto de diagnosticos --pensado para que un boton
                #  conteste rapido-- no tiene sentido aqui. Medido el
                #  08/10/2026: con el tope atendido, 12 casos por corrida
                #  quedaban sin preguntarle al proveedor y la cola de 90
                #  tardaba 30 horas. No cambia NINGUNA puerta del cierre.
                resumen = supervisor.correr_ciclo(org, desatendido=True)
            except Exception:
                #  'exception' y no 'error': hace falta el traceback para saber
                #  donde fue, y el org id alcanza para ubicar la empresa sin
                #  nombrarla.
                logger.exception(
                    "Supervisor: el ciclo fallo para org=%s", org.id)
                continue
            empresas += 1
            auto = resumen.get("cierre_automatico") or {}
            n = auto.get("cerrados", 0)
            cerrados += n
            for mapa, destino in ((auto.get("motivos"), no_evaluados),
                                  (auto.get("motivos_de_no_cierre"),
                                   no_cerrados)):
                for motivo, veces in (mapa or {}).items():
                    destino[motivo] = destino.get(motivo, 0) + veces
            #  CONTEOS Y NUNCA CASOS. Que se cerro y por que ya quedo escrito
            #  en la propuesta y en su auditoria, que es donde una persona lo
            #  va a buscar; repetirlo aqui pondria el detalle de un cliente en
            #  el log del worker, que no es un lugar con control de acceso.
            logger.info(
                "Supervisor: ciclo corrido org=%s senales=%s propuestas=%s "
                "cerrados=%s no_evaluados=%s no_cerrados=%s",
                org.id, resumen.get("senales", 0),
                resumen.get("propuestas", 0), n,
                auto.get("motivos") or {},
                auto.get("motivos_de_no_cierre") or {})
    finally:
        clear_rls_context()
    return {"empresas": empresas, "cerrados": cerrados,
            "no_evaluados_por": no_evaluados,
            "no_cerrados_por": no_cerrados}


@shared_task(name="operaciones.tasks.ciclo_a_pedido")
def ciclo_a_pedido(org_id: str) -> dict:
    """
    El ciclo de UNA empresa, lanzado desde el boton de la pantalla.

    POR QUE EXISTE, Y POR QUE ES OTRA TAREA
    ---------------------------------------
    Hasta el 13/10/2026 el boton corria el ciclo DENTRO de la peticion HTTP y
    esperaba. Eso funcionaba cuando el ciclo no hacia casi nada; ese mismo dia
    paso a LEER tickets --cada lectura es una consulta al modelo mas las
    herramientas que use-- y la corrida se fue a varios minutos.

    MEDIDO esa noche: el ciclo termino a las 23:58:38 y dejo sus cuatro
    lecturas; a las 00:02 el boton seguia diciendo "Analizando operacion...".
    La conexion se habia cortado mucho antes. El trabajo salia bien y la
    pantalla se quedaba girando para siempre -- el peor de los dos mundos,
    porque invita a apretar de nuevo algo que ya esta corriendo.

    NO ES 'ciclo_del_supervisor' CON UN PARAMETRO. Aquella recorre las empresas
    que DELEGARON el ciclo y corre desatendida; esta la pide una persona para
    SU empresa, aunque no haya delegacion. Mezclarlas haria que el boton
    dependiera de una delegacion que no tiene nada que ver.

    NO AFLOJA NINGUNA PUERTA: 'correr_ciclo' solo escribe propuestas y su
    auditoria, igual que antes. Lo unico que cambia es quien espera.
    """
    from operaciones import supervisor

    try:
        org = Org.objects.get(id=org_id)
    except Org.DoesNotExist:
        logger.info("Supervisor: el ciclo a pedido no encontro la empresa")
        return {"corrio": False, "motivo": "empresa inexistente"}

    #  EL CONTEXTO, antes de tocar nada: sin esto la RLS devuelve cero filas y
    #  el ciclo informaria "sin casos" siendo que no pudo verlos. Y el 'finally'
    #  no es de adorno -- la variable es de SESION y la conexion vuelve al pool
    #  con ella puesta.
    set_rls_context(org.id)
    try:
        #  'desatendido=True'  --  corregido el 14/10/2026
        #  ------------------------------------------------
        #  Decia False, razonando que "alguien SI esta esperando en la
        #  pantalla". Es falso desde que esta tarea existe: el boton se
        #  responde en el acto con el acuse y la persona se va a hacer otra
        #  cosa. Nadie espera esta corrida.
        #
        #  Y el tope corto existe SOLO por esa espera: tres diagnosticos
        #  contra quince. MEDIDO: diez propuestas de desincronizados llevaban
        #  un dia sin diagnosticar, y por lo tanto sin poder cerrarse, mientras
        #  cada vuelta a pedido miraba tres equipos y se iba.
        #
        #  NO ES UN PERMISO: las tres puertas del cierre --delegacion, techo de
        #  autonomia y diagnostico del equipo-- siguen exactamente iguales. Lo
        #  unico que cambia es cuantos equipos alcanza a mirar antes de cortar.
        resumen = supervisor.correr_ciclo(org, desatendido=True)
    except Exception:
        logger.exception("Supervisor: el ciclo a pedido fallo para org=%s",
                         org.id)
        return {"corrio": False, "motivo": "el ciclo falló"}
    finally:
        clear_rls_context()

    #  EL RESULTADO, EN EL LOG  --  14/10/2026
    #  ---------------------------------------
    #  Desde que el ciclo se encola, el resumen ya no vuelve a la pantalla:
    #  nadie lo ve. Y la primera corrida asi dejo 38 propuestas creadas y CERO
    #  lecturas, sin ninguna pista de por que -- el unico lugar donde podia
    #  estar la respuesta era un log que no decia nada.
    #
    #  Son numeros, no contenido: cuantas se leyeron, cuantas midieron el
    #  equipo, cuantas fallaron. Ni una descripcion de ticket ni un nombre.
    t = resumen.get("tickets") or {}
    logger.info(
        "Supervisor: ciclo a pedido · propuestas=%s · tickets leidos=%s "
        "midieron=%s sin_medir=%s errores=%s fuera_de_tope=%s · fases_caidas=%s",
        resumen.get("propuestas"), t.get("leidos"), t.get("midieron"),
        t.get("sin_medir"), t.get("errores"), t.get("fuera_de_tope"),
        [f.get("fase") for f in (resumen.get("fases_que_fallaron") or [])])

    return {"corrio": True, "resumen": resumen}
