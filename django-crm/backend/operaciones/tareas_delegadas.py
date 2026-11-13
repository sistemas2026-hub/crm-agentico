# -*- coding: utf-8 -*-
"""
===============================================================================
 LO QUE UNA PERSONA LE DELEGO AL SUPERVISOR, UNA SOLA VEZ
===============================================================================

QUE RESUELVE
------------
Que alguien le diga al Supervisor, hablando normal: "todo ticket cerrado en
WispHub y abierto en Dexter, diagnosticalo y si esta todo bien cerralo" -- y a
partir de ahi lo haga siempre, sin que nadie tenga que volver a apretar nada.

EL CATALOGO ES CERRADO, Y ESA ES TODA LA DECISION
--------------------------------------------------
Habia dos formas de construir esto.

La primera: que el modelo interprete la frase y de ahi salga la accion. Mas
flexible, y con la garantia en el texto -- si alguien escribe "cerra los que
esten cerrados en WispHub" sin la parte del diagnostico, el Supervisor cerraria
casos sin mirar el equipo. Lo que hoy protege a un cliente dejaria de ser
codigo y pasaria a ser como estaba redactada una frase.

La segunda, que es esta: el modelo ENTIENDE la frase y ACTIVA una tarea que el
codigo ya sabe hacer. La persona habla igual de natural; lo que el chat decide
es cual de las tareas del catalogo encender, no que hace esa tarea. Si le piden
algo que no esta en la lista, lo dice en vez de improvisarlo.

Es la misma regla que sostiene el resto del proyecto: "el modelo compone, el
codigo calcula", y "seguridad en codigo, nunca solo en el prompt".

LO NO CRITICO NACE DELEGADO  --  12/11/2026
------------------------------------------
Hasta hoy este encabezado decia que la tarea y el nivel "exigen una persona"
los dos, y las diez tareas nacian apagadas en una empresa nueva: el Supervisor
pedia permiso para pasar un caso a Despacho, armar la jornada o cargar el
material. Era la regla de antes del 02/11/2026. Ese dia el dueno del producto
la invirtio (PRD §1, §2 y §8.18): autonomo por defecto, y una persona solo en
lo CRITICO -- lo que mueve dinero, deja a un cliente sin servicio de forma que
no vuelve sola, afecta a muchos clientes a la vez, borra o expone datos, o
compromete a la empresa con un tercero. La auditoria del menu del 12/11/2026
(SPEC/AUDITORIA_MENU_2026-11-12.md, Supervisor NOC) encontro que el Supervisor
seguia del lado viejo: era la bandeja de aprobaciones mas grande del producto,
para trabajo que PRD §2 declara no critico.

Desde hoy cada tarea DECLARA si es critica (campo 'critica', explicito y con
su porque al lado; no se deduce de otra cosa y, si falta, cuenta como critica)
y eso decide su estado cuando nadie dijo nada:

    SIN FILA          no critica -> delegada.    critica -> NO delegada.
    FILA ENCENDIDA    delegada (la delego una persona).
    FILA APAGADA      NO delegada, SIEMPRE: una persona la quito, con su
                      nombre y su motivo, y ningun defecto la vuelve a prender.

Asi «Ajustes del Supervisor» pasa a ser el lugar donde se QUITA autonomia, no
donde se enciende. El nivel de la empresa acompana: sin fila nace en 3
('autonomia.nivel_configurado'), una fila que una persona escribio se respeta,
y el 4 sigue siendo "siempre una persona". Una critica exige el 4, asi que por
este camino no sale sola nunca: queda como propuesta.

LA PERSONA SALE, LA GARANTIA NO. Nada de esto toca lo que cada tarea comprueba
en codigo antes de actuar (las cinco reglas del paso, el diagnostico optico del
cierre, el tope de cada cuadrilla, la bodega que alcanza, las compuertas del
motor). Y el interruptor de autonomia del motor sigue frenando todo de un paso
y fallando cerrado: apagado o ilegible, el nivel efectivo cae a 1 y ninguna
tarea actua ('autonomia.nivel_efectivo').
"""
from __future__ import annotations

from django.utils import timezone

#  ===========================================================================
#   EL CATALOGO
#  ===========================================================================
#  Cada entrada es una tarea que el CODIGO ya sabe hacer, con su clave estable,
#  como nombrarla a una persona, y que exige para funcionar.
#
#  AGREGAR UNA TAREA AQUI NO LA CONSTRUYE. La entrada declara algo que ya
#  existe y esta probado; si no existe, lo que corresponde es construirlo
#  primero. Una clave sin implementacion seria una promesa que el chat podria
#  aceptar y el ciclo no cumpliria.
CERRAR_DESINCRONIZADOS = "cerrar_desincronizados_con_diagnostico"
CICLO_AUTOMATICO = "revisar_solo_con_cada_actualizacion"
PASAR_A_DESPACHO = "pasar_a_despacho_segun_las_reglas"
ARMAR_LA_JORNADA = "armar_la_jornada_del_dia"
CREAR_LAS_ORDENES = "crear_las_ordenes_de_despacho"
#  Fase 3.1 (27/10/2026): publicar el reparto del dia. Ver
#  operaciones/publicacion_del_reparto.py.
PUBLICAR_EL_REPARTO = "publicar_el_reparto_del_dia"
#  Fase 3 del material del dia (28/10/2026): cargarle a cada cuadrilla su kit.
#  Ver operaciones/carga_del_material.py.
CARGAR_EL_MATERIAL = "cargar_el_material_del_dia"
#  La misma clave que 'paso_a_despacho.TAREA_CORRECCIONES': se escribe en los dos
#  lados para no importar aquel modulo desde aca, y una prueba las ata.
PASAR_CON_LAS_CORRECCIONES = "pasar_a_despacho_con_las_correcciones"
#  H-21 (24/10/2026, autorizada por el usuario): ubicar cada asunto en su nivel
#  de respuesta. Ver operaciones/nivel_de_los_asuntos.py.
UBICAR_LOS_ASUNTOS = "ubicar_los_asuntos_en_su_nivel"
#  30/10/2026, SPEC/objetivos/revision-del-cierre.md: aprobar y cerrar lo que la
#  revision del cierre dio por bueno. Ver campo/cierre_por_el_supervisor.py.
CERRAR_LO_REVISADO = "aprobar_y_cerrar_lo_que_dio_por_bueno"

CATALOGO = {
    CERRAR_DESINCRONIZADOS: {
        "nombre": "Cerrar los casos ya cerrados en WispHub, con diagnóstico",
        #  NO CRITICA (PRD §2): cerrar un ticket esta en la lista de lo que el
        #  agente hace solo. Y este ni siquiera sale de Dexter: el caso ya esta
        #  cerrado en el sistema del ISP, y solo se cierra si el diagnostico
        #  del equipo lo habilita.
        "critica": False,
        "que_hace": (
            "Por cada caso que figura cerrado en WispHub y abierto en Dexter, "
            "le pregunta a SmartOLT por el equipo del cliente. Lo cierra solo "
            "si el equipo está en línea con señal buena, o caído por falta de "
            "energía en el domicilio. Si la señal está débil o la caída es por "
            "fibra, lo deja para que lo mire una persona."),
        "que_no_hace": (
            "No toca WispHub, no reabre nada, y no cierra ningún caso cuyo "
            "equipo no haya podido diagnosticar."),
        "exige_nivel": 3,
        "necesita_que_mire": True,
    },
    PASAR_A_DESPACHO: {
        "nombre": "Pasar casos a Despacho solo, según las cinco reglas",
        #  NO CRITICA (PRD §2 la nombra: "pasar un caso a Despacho"). No
        #  mueve dinero ni toca el servicio: deja el caso en una cola interna,
        #  y las cinco reglas se comprueban en codigo antes.
        "critica": False,
        "que_hace": (
            "Después de leer un ticket, lo deja en la cola de Despacho sin "
            "esperar que alguien acepte la propuesta, cuando una de las cinco "
            "reglas lo habilita. Si el cliente reporta una falla, exige que la "
            "medición del equipo la confirme. Si pide un trabajo en su casa, o "
            "si es una obra de red, el equipo sano es lo normal y pasa igual, "
            "pero solo con una lectura del reclamo de confianza alta."),
        "que_no_hace": (
            "NO crea la orden de trabajo, no elige la plantilla y no asigna "
            "técnico ni fecha: eso lo sigue haciendo quien despacha. Y nunca "
            "pasa solo un reclamo que ninguna herramienta puede comprobar "
            "—una página bloqueada—, ni algo que no sea de un cliente ni de la "
            "red: esos los mira una persona siempre."),
        #  PROPIA, y no la del cierre: habilitar una cosa no puede habilitar la
        #  otra de rebote. Son dos efectos distintos y cada uno se pide aparte.
        "exige_nivel": 3,
        "necesita_que_mire": True,
    },
    ARMAR_LA_JORNADA: {
        "nombre": "Armar la jornada del día de cada cuadrilla",
        #  NO CRITICA (PRD §2: "armar la jornada"). Interna, y una persona la
        #  corrige con un clic en Cuadrillas.
        "critica": False,
        "que_hace": (
            "En cada vuelta arma la jornada de hoy de cada cuadrilla activa "
            "que todavía no la tenga: su pareja de siempre, sus zonas "
            "habituales y la labor de la mayoría de los casos de Despacho de "
            "esas zonas. Mientras una jornada que armó él no tenga órdenes, "
            "le cambia la labor si entran casos de otra."),
        "que_no_hace": (
            "No toca una jornada que armó o corrigió una persona, no arma una "
            "cuadrilla sin zonas habituales ni una cuyo líder está ausente, y "
            "no crea órdenes ni las reparte: al técnico no le llega nada "
            "hasta que alguien publica el reparto."),
        #  PROPIA, como la del paso a Despacho: habilitar una no habilita la
        #  otra. Nivel 3 y no 4: armar una jornada no sale de la plataforma ni
        #  le promete nada a un cliente, y una persona la corrige con un clic.
        "exige_nivel": 3,
        "necesita_que_mire": True,
    },
    CREAR_LAS_ORDENES: {
        "nombre": "Crear las órdenes de los casos de Despacho",
        #  NO CRITICA (PRD §2: "crear y repartir órdenes"). La orden no le
        #  llega a nadie hasta que se publica, y una persona la cancela.
        "critica": False,
        "que_hace": (
            "En cada vuelta crea la orden de trabajo de cada caso de la cola "
            "de Despacho que todavía no la tiene, como si alguien apretara "
            "«Despachar»: la plantilla por el asunto, la prioridad por el "
            "plazo y la espera, el día por la hora de corte, y los datos del "
            "cliente de su ficha. Un corte de red lleva una sola orden por "
            "puerto. Hasta 8 por vuelta."),
        "que_no_hace": (
            "No asigna técnico ni publica: la orden queda esperando el "
            "reparto. No crea la de un caso sin barrio, con un barrio sin "
            "zona, sin plantilla o sin ficha del cliente, ni la de uno que ya "
            "tuvo una orden: esos los mira una persona. La instalación de un "
            "cliente nuevo sale sin dirección ni teléfono, para llamar al "
            "cliente."),
        #  PROPIA, como las otras: habilitar armar la jornada no habilita
        #  crear ordenes. Nivel 3: la orden no sale de la plataforma ni le
        #  llega a nadie hasta que se publica, y una persona la cancela.
        "exige_nivel": 3,
        "necesita_que_mire": True,
    },
    PUBLICAR_EL_REPARTO: {
        "nombre": "Publicar el reparto del día",
        #  NO CRITICA (PRD §2: "crear y repartir órdenes", "recordarle al
        #  técnico"). Le llega trabajo a un tecnico de la empresa, no a un
        #  cliente ni a un tercero, y se deshace moviendo la orden.
        "critica": False,
        "que_hace": (
            "En cada vuelta, desde dos horas antes de que abran las cuadrillas "
            "hasta el cierre, asigna a las cuadrillas del día las órdenes que "
            "no tienen a nadie y las que tiene alguien que hoy no trabaja, "
            "con la regla de reparto del botón «Publicar» y contando lo que "
            "cada cuadrilla ya tiene hoy para no pasar su tope. A cada técnico "
            "le avisa al teléfono una vez por vuelta, con cuántas visitas le "
            "tocaron."),
        "que_no_hace": (
            "No mueve una orden que ya tiene a alguien que hoy trabaja: ni lo "
            "que publicó una persona, ni lo que asignó el mismo Supervisor, ni "
            "lo que un técnico empezó. No publica en un día que las cuadrillas "
            "no trabajan, ni a una cuadrilla sin nadie con cuenta o con alguien "
            "que declaró ausencia. Lo que no entra por el tope queda sin "
            "asignar, para mañana."),
        #  PROPIA, como las otras: crear las ordenes no habilita publicarlas.
        #  Nivel 3, justificado por escrito (27/10/2026): es la primera que
        #  hace que el trabajo LE LLEGUE a alguien sin que una persona lo mire
        #  --la visita en su lista y un aviso al telefono--, y eso lo decidio
        #  el usuario el 17/10. Lo acota: una persona lo deshace moviendo la
        #  orden en Cuadrillas, desde la apertura nada publicado se mueve solo,
        #  y lo que un tecnico empezo o una persona asigno no se toca nunca.
        "exige_nivel": 3,
        "necesita_que_mire": True,
    },
    CARGAR_EL_MATERIAL: {
        "nombre": "Cargar el material del día",
        #  NO CRITICA (PRD §2: "cargar el material"). Mueve material de la
        #  bodega de la empresa a la custodia de su propio tecnico: no es
        #  dinero que sale ni una compra a un tercero, y el tecnico confirma
        #  o marca la diferencia al recibir.
        "critica": False,
        "que_hace": (
            "Una vez por día y por cuadrilla, después de publicar el reparto, "
            "le carga a su líder el kit de su labor desde su bodega: lo que le "
            "falta para completarlo. Si en la bodega no alcanza, reparte lo que "
            "hay según el trabajo publicado de cada cuadrilla. Las ONT y demás "
            "equipos con serie no los despacha: los deja reservados a nombre del "
            "líder hasta que los escanee al recibirlos."),
        "que_no_hace": (
            "No carga dos veces en el mismo día a la misma cuadrilla, ni carga "
            "material que la bodega no tiene. No elige la serie de un equipo. "
            "No recarga lo que se publica después durante el día: eso se pide "
            "desde la app. No reemplaza que el técnico confirme lo que recibió."),
        #  PROPIA y nivel 3, como publicar el reparto (28/10/2026): mueve
        #  material de una bodega a la custodia de una persona sin que nadie lo
        #  mire. Lo acota: una sola vez por dia y cuadrilla (el acta tiene clave
        #  fija), nunca mas de lo que la bodega tiene libre, y el tecnico
        #  confirma o marca la diferencia al recibir.
        "exige_nivel": 3,
        "necesita_que_mire": True,
    },
    PASAR_CON_LAS_CORRECCIONES: {
        "nombre": "Pasar a Despacho también con las correcciones del usuario",
        #  NO CRITICA: suma reglas al paso a Despacho, que no lo es, y no
        #  encaja en ninguno de los cinco casos de PRD §2. PRD §8.18 no la
        #  nombra en su lista; se clasifico con la definicion, no con la lista.
        "critica": False,
        "que_hace": (
            "Suma al paso a Despacho las correcciones del 18/10/2026: una "
            "falla con un trabajo ya autorizado por la empresa pasa como "
            "trabajo pedido; un equipo que figura sin energía pasa como falla "
            "de fibra si el ticket dice que eso ya se descartó; y una falla "
            "con la señal en rango pasa si una medición del Supervisor de las "
            "últimas 24 horas la vio fuera de rango. Mientras no se delega, "
            "el Supervisor solo cuenta cuáles pasarían y lo escribe en cada "
            "propuesta. Antes de delegarla conviene mirar eso: el motivo de "
            "cada propuesta y la columna «con correcciones» del informe de "
            "pendientes."),
        "que_no_hace": (
            "No pasa nada por sí sola: hace falta también la tarea de pasar "
            "casos a Despacho, y el nivel de la empresa. No crea órdenes ni "
            "asigna técnicos, y no cambia el grupo que leyó el modelo."),
        #  PROPIA, y no la del paso: encender las correcciones es una decision
        #  aparte. Desde el 12/11/2026 nace delegada (esta_delegada: sin fila,
        #  una no critica esta delegada): pasar un caso a Despacho no es ninguno
        #  de los cinco criticos (PRD §2). Lo que la frena es el nivel 3 de la
        #  empresa; y mientras no actua, el Supervisor sigue contando en sombra
        #  cuales pasarian.
        "exige_nivel": 3,
        "necesita_que_mire": True,
        #  Y NO ANDA SOLA: suma reglas al paso, que es otra tarea. 'delegar_tarea'
        #  lo dice si falta (auditor de frontera, 19/10/2026: contestaba "ya
        #  puede actuar" sin el paso delegado).
        "requiere": (PASAR_A_DESPACHO,),
    },
    UBICAR_LOS_ASUNTOS: {
        "nombre": "Ubicar cada asunto en su nivel de respuesta",
        #  NO CRITICA (PRD §8.18: "ubicar los asuntos"). Clasificacion
        #  interna que una persona corrige con un clic.
        "critica": False,
        "que_hace": (
            "En cada vuelta pone cada asunto en Urgente, Normal o Programable "
            "según lo que midió en sus tickets: si la mayoría fueron falla de "
            "servicio, Urgente; obra de red, Normal; trabajo pedido, "
            "Programable. Con menos de 3 tickets lo deja en Normal por ahora. "
            "Lo cuenta en el chat, con el porqué. Mientras no se delega, solo "
            "cuenta cuántos ubicaría y lo deja en el registro."),
        "que_no_hace": (
            "No toca un asunto que ubicó una persona, no cambia los niveles "
            "(plazo y prioridad los pone la empresa en Plantillas) y no "
            "cambia órdenes ya creadas."),
        #  PROPIA, como el armado y el paso: habilitar una no habilita la otra.
        #  Nivel 3: escribe una clasificacion interna que una persona corrige
        #  con un clic; no sale de la plataforma ni le promete nada a nadie.
        "exige_nivel": 3,
        "necesita_que_mire": True,
    },
    CERRAR_LO_REVISADO: {
        "nombre": "Aprobar y cerrar las órdenes terminadas que dé por buenas",
        #  NO CRITICA (PRD §2: "cerrar tickets"; un ticket se reabre). Sale
        #  del sistema --cierra el ticket en el ISP-- y por eso pasa ademas por
        #  las compuertas del motor (interruptor, techo y autorizacion de la
        #  herramienta), que siguen igual.
        "critica": False,
        "que_hace": (
            "Apenas el técnico manda su reporte revisa esa orden, y además "
            "repasa todas una vez por hora: el checklist, el reporte de "
            "cierre, si el técnico afirmó que el servicio quedó funcionando, "
            "la señal después del arreglo y el material. Las que da por buenas "
            "las cierra en el sistema del ISP —queda allá el resumen de lo que "
            "se hizo, firmado por el Supervisor— y, solo si allá quedaron "
            "cerradas, las aprueba y las cierra en Dexter."),
        "que_no_hace": (
            "No toca las que dejan dudas ni las que no están bien: esas las "
            "mira una persona. Tampoco una orden que ya fue devuelta al "
            "técnico, ni una de falla cuya medición todavía no llegó. Si el "
            "ISP le avisa al cliente que su ticket se cerró, ese aviso no dice "
            "quién lo cerró. Y si el motor no lo deja —el interruptor, el "
            "techo o la autorización de la herramienta— no cierra nada y la "
            "tarjeta dice qué lo frenó."),
        #  PROPIA, como las otras. Nivel 3 y no 4: lo que se cierra es lo que
        #  la revision dio por bueno en codigo, y el ticket pasa ademas por las
        #  compuertas del motor. Con el interruptor detenido no cierra nada.
        "exige_nivel": 3,
        "necesita_que_mire": True,
    },
    CICLO_AUTOMATICO: {
        "nombre": "Revisar solo, una vez por hora",
        #  NO CRITICA (PRD §8.18: "revisar solo cada hora"). Mirar no es
        #  ejecutar; sin esta, ninguna de las otras corre sola.
        "critica": False,
        "que_hace": (
            "Una vez por hora el Supervisor revisa la operación por su "
            "cuenta: detecta lo que cambió, deja las propuestas que "
            "correspondan, y ejecuta las tareas que ya estén delegadas. Sin "
            "que nadie apriete nada. Cada hora y no más seguido porque los "
            "tickets del proveedor también llegan cada hora: mirar más "
            "seguido sería preguntar cuatro veces por el mismo dato."),
        "que_no_hace": (
            "No habilita ninguna acción por sí misma. Solo hace que el "
            "Supervisor mire cada tanto en vez de esperar a que alguien lo "
            "despierte: lo que puede hacer al mirar sigue siendo lo que esté "
            "delegado aparte, con su propio nivel de autonomía."),
        #  NO EXIGE NIVEL, y la diferencia importa: mirar no es ejecutar. Si
        #  no hay ninguna tarea de accion delegada, esto solo produce
        #  propuestas para que las lea una persona -- que es lo que el
        #  Supervisor ya hacia cuando alguien apretaba el boton.
        "exige_nivel": 0,
        #  ES LA QUE PROVEE EL MIRAR, no una que lo necesite. Sin esta fila
        #  ninguna de las otras corre sola: ver 'algo_la_va_a_correr'.
        "necesita_que_mire": False,
    },
}


#  LO QUE EL SUPERVISOR DEJA SIEMPRE PARA UNA PERSONA  --  12/11/2026
#  -------------------------------------------------------------------
#  No son tareas de este catalogo: su circuito vive en otro lado y ya exige a
#  la persona en codigo. Se declaran aca SOLO para que «Ajustes del
#  Supervisor» pueda decir, al lado de lo que hace solo, que espera a alguien y
#  por que es critico (PRD §2). No habilitan ni frenan nada: lo que lo frena
#  es la funcion que se nombra en 'garantia', y una prueba la ata
#  ('test_lo_critico_espera_a_una_persona').
LO_QUE_ESPERA_A_UNA_PERSONA = (
    {
        "clave": "avisar_la_caida_de_red",
        "nombre": "Avisar a los clientes de una caída de red",
        "que_hace": (
            "Cuando se cae un puerto de fibra, prepara el aviso por WhatsApp y "
            "cuenta a cuántos clientes les llegaría. No sale hasta que una "
            "persona lo aprueba en Supervisor NOC → Fallas."),
        "por_que_critica": (
            "Le llega a muchos clientes a la vez (PRD §2, caso 3): un aviso "
            "equivocado lo reciben todos los de ese puerto, y no se retira."),
        "garantia": "operaciones.aviso_de_caida.aprobar",
    },
)


def es_critica(clave: str) -> bool:
    """
    Si esta tarea es critica segun su ficha. FALLA CERRADO: una clave que no
    esta en el catalogo, o una ficha sin el campo, cuenta como critica -- lo
    que no se declara se trata como critico, igual que 'critica' en el
    catalogo de herramientas del motor (PRD §2, «Cómo se declara»).
    """
    ficha = CATALOGO.get(clave)
    if ficha is None:
        return True
    return ficha.get("critica", True) is not False


def catalogo_legible() -> list[dict]:
    """El catálogo con su clave, para que el chat lo muestre y lo nombre."""
    return [{"clave": c, **datos} for c, datos in CATALOGO.items()]


def esta_delegada(org, clave: str) -> bool:
    """
    Si esta tarea esta delegada y vigente para esta empresa.

    LA FILA MANDA; SIN FILA, LA FICHA  --  12/11/2026. Una fila (encendida o
    apagada) es lo que decidio una persona y se respeta siempre. Sin fila, una
    no critica esta delegada y una critica no: es "autonomo por defecto, una
    persona solo en lo critico" (PRD §2). Antes, sin fila era siempre False, y
    las diez tareas nacian apagadas.

    FALLA CERRADO: una clave que no esta en el catalogo devuelve False, no
    levanta. El ciclo pregunta esto antes de actuar, y una excepcion ahi
    tumbaria una corrida entera por una clave vieja en la base.
    """
    from operaciones.tareas_modelos import TareaDelegada

    if clave not in CATALOGO:
        return False
    activa = (TareaDelegada.objects.filter(org=org, clave=clave)
              .values_list("activa", flat=True).first())
    if activa is not None:
        return bool(activa)
    return not es_critica(clave)


def empresas_con_la_tarea(clave: str) -> list:
    """
    Los id de las empresas para las que esta tarea esta delegada.

    La usa el ciclo horario para saber a quien recorrer, ANTES de fijar el
    contexto de RLS: 'TareaDelegada' y 'Org' no tienen politica (medido el
    08/10/2026, ver 'tasks.py'), asi que se pueden leer sin empresa puesta.

    SIN FILA, SOLO LAS EMPRESAS QUE SON UN ISP DEL MOTOR. Una no critica nace
    delegada, pero "toda organizacion activa del CRM" no es "toda empresa": una
    organizacion sin tenant en el motor no tiene tickets ni equipos que mirar,
    y recorrerla seria pagar un ciclo por nada. 'tenant_de' sin respuesta es
    '' y la deja afuera -- falla cerrado, como en el resto del backend.
    """
    from common.models import Org

    from operaciones.tareas_modelos import TareaDelegada

    if clave not in CATALOGO:
        return []
    filas = dict(TareaDelegada.objects.filter(clave=clave)
                 .values_list("org_id", "activa"))
    ids = [org_id for org_id, activa in filas.items() if activa]
    if es_critica(clave):
        return ids
    from operaciones import areas_del_tenant

    for org_id in (Org.objects.filter(is_active=True)
                   .exclude(id__in=list(filas))
                   .values_list("id", flat=True)):
        try:
            if areas_del_tenant.tenant_de(org_id):
                ids.append(org_id)
        except Exception:                                        # noqa: BLE001
            #  No saber de que empresa es = no recorrerla. Sin el texto del
            #  error: puede traer la URL del motor.
            continue
    return ids


def algo_la_va_a_correr(org, clave: str) -> dict:
    """
    Si esta tarea delegada va a correr sola, o solo cuando alguien la despierte.

    LA SEGUNDA PRECONDICION, Y ESTABA EN SILENCIO  --  15/10/2026
    -------------------------------------------------------------
    Una tarea de accion necesita DOS cosas para andar sola, no una:

        EL NIVEL   cuanto puede hacer el Supervisor por su cuenta.
        EL MIRAR   que algo lo despierte. Lo da 'CICLO_AUTOMATICO'; sin esa
                   fila el Supervisor solo corre cuando una persona aprieta
                   el boton de la pantalla.

    'delegar_tarea' ya avisaba de la primera y callaba la segunda. Medido ese
    dia en el entorno local: 'pasar_a_despacho_segun_las_reglas' delegada y
    activa, el nivel en 3, y el ciclo horario devolviendo 'empresas: 0' en las
    cinco corridas de 16:07 a 21:11 UTC con el mensaje "ningun ciclo delegado,
    no se recorre nada". El panel se quedo clavado en el ultimo hecho de las
    11:10 y nada en la pantalla ni en el chat decia por que.

    Es el mismo razonamiento que el docstring de 'delegar_tarea' ya escribia
    para el nivel --"el silencio ahi seria el peor resultado: la persona se va
    creyendo que quedo andando"-- aplicado a la precondicion que faltaba.

    POR QUE NO SE ARREGLA ENSANCHANDO LA PUERTA DEL CICLO. La tentacion es que
    'tasks.py' admita tambien a quien delego solo la accion. Seria exactamente
    lo que este catalogo prohibe dos lineas mas arriba: "habilitar una cosa no
    puede habilitar la otra de rebote". Delegar que pase casos a Despacho no
    autoriza al Supervisor a despertarse cada hora -- eso es 'CICLO_AUTOMATICO'
    y se pide aparte. Lo que faltaba no era permiso: era decirlo.

    FALLA DICIENDO QUE NO, no al reves: una clave fuera del catalogo devuelve
    'si=False'. Esta funcion la lee el chat para avisar, y un falso "ya quedo
    andando" es el resultado que esto existe para evitar.
    """
    ficha = CATALOGO.get(clave)
    if ficha is None:
        return {"si": False, "por_que": "esa tarea no está en el catálogo"}
    if not ficha.get("necesita_que_mire"):
        #  La tarea se corre a si misma -- es el caso de 'CICLO_AUTOMATICO'.
        return {"si": True, "por_que": ""}
    if esta_delegada(org, CICLO_AUTOMATICO):
        return {"si": True, "por_que": ""}
    return {
        "si": False,
        "por_que": (
            "nada la va a correr sola: el Supervisor solo revisa por su "
            "cuenta si está delegada «"
            + CATALOGO[CICLO_AUTOMATICO]["nombre"]
            + "». Hasta entonces esta tarea corre únicamente cuando una "
              "persona aprieta el botón de revisar en la pantalla"),
    }


def delegadas(org) -> list[dict]:
    """
    Las tareas vigentes de esta empresa, con quién y cuándo las delegó.

    INCLUYE LAS QUE NACEN DELEGADAS (12/11/2026), con 'por_omision' en
    verdadero y sin quien ni cuando: nadie las delego, las trae el defecto. Si
    esta lista mostrara solo las filas, el chat diria "no tengo nada delegado"
    mientras el ciclo pasa casos a Despacho -- la peor forma de equivocarse
    para un sistema que tiene que poder decir que hace.
    """
    from operaciones.tareas_modelos import TareaDelegada

    filas = {f.clave: f for f in (TareaDelegada.objects
                                  .filter(org=org)
                                  .select_related("delegada_por"))}
    salida = []
    for f in sorted((f for f in filas.values() if f.activa),
                    key=lambda f: f.delegada_en, reverse=True):
        if f.clave not in CATALOGO:
            continue
        salida.append({
            "clave": f.clave,
            "nombre": CATALOGO[f.clave].get("nombre", f.clave),
            "delegada_en": f.delegada_en.isoformat(),
            #  El ID y nunca el nombre ni el correo: esto puede terminar en un
            #  log.
            "delegada_por": str(f.delegada_por_id or ""),
            "con_estas_palabras": f.pedido_textual,
            "por_omision": False,
        })
    for clave, ficha in CATALOGO.items():
        if clave in filas or es_critica(clave):
            continue
        salida.append({
            "clave": clave,
            "nombre": ficha.get("nombre", clave),
            "delegada_en": None,
            "delegada_por": "",
            "con_estas_palabras": "",
            "por_omision": True,
        })
    return salida


class ErrorTarea(Exception):
    """No se pudo delegar o quitar. El mensaje lo lee una persona."""


def bloquear(org, clave: str) -> None:
    """
    Una sola escritura a la vez sobre ESTA tarea de ESTA empresa  --  27/10/2026.

    Desde «Ajustes del Supervisor» hay dos caminos que escriben (la pantalla y
    el chat), y la pantalla además lee el estado antes de escribir para no
    pisar a nadie. Sin esto, dos personas que delegan por primera vez a la vez
    ven las dos "no hay fila", y la segunda reactiva la de la primera a su
    nombre (auditor independiente, 27/10/2026). Un 'select_for_update' no
    alcanza: la primera vez no hay fila que bloquear.

    'pg_advisory_xact_lock', como 'campo.services.despacho.bloquear_el_caso':
    no necesita fila y se suelta solo al confirmar o deshacer. Exige una
    transaccion abierta: fuera de una se soltaria en el acto. Solo en
    Postgres, como 'common/packs/applier.py': en SQLite (solo pruebas) no
    existe y se saltea en vez de romper.
    """
    from django.db import connection

    if not connection.in_atomic_block:
        raise RuntimeError("bloquear una tarea necesita una transaccion abierta")
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as c:
        c.execute("select pg_advisory_xact_lock(hashtext(%s))",
                  [f"tarea-delegada:{org.id}:{clave}"])


def delegar(org, clave: str, *, actor, pedido_textual: str = "",
            conversacion_id=None, ahora=None):
    """
    Deja delegada una tarea del catálogo. Exige persona.

    'pedido_textual' es la frase con la que se pidió, guardada tal cual. No se
    usa para decidir nada -- lo que se ejecuta es la tarea del catálogo-- pero
    es lo que permite, meses después, saber qué creía estar pidiendo quien la
    delegó. Si la tarea hace algo distinto de lo que esa frase dice, el
    problema es del catálogo y conviene poder verlo.
    """
    from django.db import transaction

    from operaciones.tareas_modelos import TareaDelegada

    if clave not in CATALOGO:
        raise ErrorTarea(
            f"'{clave}' no es una tarea que el sistema sepa hacer. Las que hay: "
            f"{', '.join(CATALOGO)}")
    if actor is None:
        raise ErrorTarea(
            "delegar una tarea necesita la persona que la delega: el "
            "Supervisor no puede darse trabajo a sí mismo")
    if es_critica(clave):
        #  12/11/2026. Una critica exige el nivel 4, que nunca alcanza por
        #  configuracion: delegarla dejaria una fila "delegada" que no hace
        #  nada, y la pantalla la pintaria encendida. Se dice antes.
        raise ErrorTarea(
            f"«{CATALOGO[clave].get('nombre', clave)}» es crítica (PRD §2): "
            f"la aprueba una persona cada vez, no se delega")

    ahora = ahora or timezone.now()
    with transaction.atomic():
        bloquear(org, clave)
        fila, creada = TareaDelegada.objects.get_or_create(
            org=org, clave=clave,
            defaults={"activa": True, "delegada_por": actor,
                      "pedido_textual": (pedido_textual or "")[:500],
                      "conversacion_id": conversacion_id,
                      "delegada_en": ahora})
        if not creada:
            #  LA CONVERSACION SE MUEVE A LA ULTIMA, igual que el actor: el
            #  aviso tiene que llegar donde se pidio esta vez, no donde se pidio
            #  hace meses. Si no viene una --se delego desde «Ajustes del
            #  Supervisor»-- se conserva solo si es de la MISMA persona: la de
            #  otro le mandaria a esa persona avisos de algo que delego otra
            #  (auditor independiente, 27/10/2026). Sin conversacion, el aviso
            #  cae a la ultima de quien la delego ('aviso_al_chat').
            if conversacion_id:
                fila.conversacion_id = conversacion_id
            elif fila.delegada_por_id != actor.id:
                fila.conversacion_id = None
            #  Volver a delegar una que ya estaba es REACTIVARLA, y queda a
            #  nombre de quien lo pidió esta vez. Lo contrario --dejar el actor
            #  viejo-- haría que la auditoría culpara a quien la delegó hace
            #  meses.
            fila.activa = True
            fila.delegada_por = actor
            fila.delegada_en = ahora
            if pedido_textual:
                fila.pedido_textual = pedido_textual[:500]
            fila.save(update_fields=["activa", "delegada_por", "delegada_en",
                                     "pedido_textual", "conversacion_id",
                                     "updated_at"])
    return fila


def quitar(org, clave: str, *, actor, motivo: str = "", ahora=None):
    """
    Deja de delegar una tarea. NO la borra: queda el registro de que existió.

    Borrarla haría imposible contestar "¿esto estuvo delegado alguna vez?", que
    es justo la pregunta que alguien va a hacer el día que un caso aparezca
    cerrado y nadie recuerde por qué.

    'motivo' lo trae «Ajustes del Supervisor» (27/10/2026). Se escribe SIEMPRE,
    también vacío: si no, quitarla por el chat dejaría a la vista el motivo de
    la vez anterior, como si fuera de esta.

    UNA YA QUITADA NO SE VUELVE A QUITAR  --  27/10/2026. Antes se re-sellaba:
    pedirle al chat que quite algo que ya estaba quitado borraba quién lo quitó
    y por qué, sin cambiar nada (auditor independiente). Ahora se dice.

    SIN FILA, UNA NO CRITICA SE QUITA CREANDO LA FILA APAGADA  --  12/11/2026.
    Desde que lo no critico nace delegado, "no hay fila" ya no significa "no
    estaba delegada": significa "la trae el defecto". Quitarla tiene que dejar
    una fila apagada con quien y por que, que es lo que el defecto respeta
    para siempre ('esta_delegada').
    """
    from django.db import transaction

    from operaciones.tareas_modelos import TareaDelegada

    if actor is None:
        raise ErrorTarea("quitar una tarea necesita la persona que lo decide")
    if clave not in CATALOGO:
        raise ErrorTarea(f"'{clave}' no es una tarea del catálogo")
    with transaction.atomic():
        bloquear(org, clave)
        fila = TareaDelegada.objects.filter(org=org, clave=clave).first()
        if fila is None and not es_critica(clave):
            return TareaDelegada.objects.create(
                org=org, clave=clave, activa=False, quitada_por=actor,
                quitada_en=ahora or timezone.now(),
                motivo_al_quitar=(motivo or "")[:500])
        if fila is None:
            raise ErrorTarea(f"'{clave}' no estaba delegada")
        if not fila.activa:
            raise ErrorTarea(f"'{clave}' ya no estaba delegada")
        fila.activa = False
        fila.quitada_por = actor
        fila.quitada_en = ahora or timezone.now()
        fila.motivo_al_quitar = (motivo or "")[:500]
        fila.save(update_fields=["activa", "quitada_por", "quitada_en",
                                 "motivo_al_quitar", "updated_at"])
    return fila
