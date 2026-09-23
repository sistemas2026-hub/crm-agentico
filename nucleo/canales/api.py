# -*- coding: utf-8 -*-
"""
================================================================================
 CANAL API  -  el motor alcanzable por HTTP
================================================================================

Envoltorio delgado sobre nucleo/modelo/motor.py: no agrega logica de negocio,
solo expone POST /chat para que cualquier cliente HTTP (una pagina web, un
proxy de otro sistema, mas adelante un webhook real) pueda hablarle al motor
sin importar Python directamente.

Estado de sesion en memoria del proceso -- es el estado "caliente" del turno
(rapido, sin ida y vuelta a disco). La conversacion tambien se persiste
(nucleo/persistencia/db.py) para que un proceso aparte (un scheduler, por
ejemplo) pueda saber cuando fue el ultimo contacto sin depender de que este
proceso siga vivo -- pero si el proceso se reinicia, la sesion "caliente"
(nivel de verificacion, id_cliente ya resuelto) se pierde igual; solo el
historial de mensajes sobrevive.

Simplificacion deliberada de esta version: no hay verificacion automatica por
"posesion del canal" (el numero de telefono) como si tienen los scripts de
cli/ -- ahi es codigo ad-hoc fuera de nucleo/ (no puede vivir aca sin nombrar
un proveedor concreto). Generalizar eso -- una herramienta
'verifica_identidad' que se dispare sola al abrir la sesion, no por el
modelo -- queda pendiente. Por ahora toda sesion nueva arranca sin verificar
y se verifica DURANTE la conversacion, con una herramienta como
'verificar_identidad_por_cedula' si el rol la tiene.
================================================================================
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import contextlib
import threading
import uuid
import time
from datetime import datetime, timezone

import requests
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from nucleo.canales import canal as canales
from nucleo.canales import media, whatsapp
from nucleo.canales.errores import estado_http_de, fallo, mensaje_publico
from nucleo.relevo import desenlaces
from nucleo.relevo import historial as regla_historial
from nucleo.relevo import proyeccion
from nucleo.relevo import revalidacion
from nucleo.relevo import transiciones
from nucleo.relevo import autorizacion as autorizacion_relevo
from nucleo.relevo.control import control_efectivo
from nucleo.conectores import catalogo as conectores
from nucleo.config import editor, fuente
from nucleo.config.fusion import fusionar_roles, modelo_fusionado
from nucleo.habilidades import analista
from nucleo.herramientas import http as ejecutor_http
from nucleo.herramientas import localidades as sincronizador_localidades
from nucleo.ingesta import corpus as ingesta
from nucleo.ingesta.docx import procesar
from nucleo.seguridad import interruptor
from nucleo.seguridad import idempotencia
from nucleo.modelo import motor
from nucleo.observabilidad import consumo
from nucleo.persistencia import db as persistencia
from nucleo.recuperacion.busqueda import recuperar
from nucleo.recuperacion.prompt import piezas_del_system
from nucleo.seguimiento import agendamiento
from nucleo.seguimiento import estado_escalada
from nucleo.seguimiento import operativo
from nucleo.seguimiento import verificacion_accion
from nucleo.seguimiento.forzado import (con_las_manos_vacias,
                                        decidir_pedido_humano_de,
                                        pidio_hablar_con_humano,
                                        decidir_pedido_humano,
                                        escalada_forzada,
                                        motivos_por_hecho,
                                        PIDE_HUMANO, PREGUNTAR, CONFIRMA)
from nucleo.seguimiento import escalamiento
from nucleo.seguimiento import resumen
from nucleo.seguimiento import supervisor
from nucleo.seguridad import secretos
from nucleo.seguridad.verificacion import Sesion
from nucleo.observabilidad.registro import id_interno, ref_proveedor, ref_sesion, registrar

app = Flask(__name__)

_configs: dict = {}    # tenant -> TenantConfig, cacheado por proceso
_servidas: dict = {}   # tenant -> (config_version servida, monotonic de la ultima comprobacion)
_sesiones: dict = {}   # canales.clave_sesion(tenant, canal, id_sesion) -> {"sesion": Sesion, "historial": [...]}

# ════════════════════════════════════════════════════════════════════════════
#  CONTROL DE CONCURRENCIA
#
#  El webhook contesta a Meta al instante y lanza UN HILO POR MENSAJE. Es
#  simple y tiene baja latencia, y con poco volumen alcanza. Lo que no tiene
#  es freno: cincuenta mensajes seguidos son cincuenta hilos, cada uno
#  llamando al modelo, abriendo su conexion y pegandole a los sistemas del
#  ISP. Nada limita eso hoy.
#
#  Dos problemas distintos, y por eso dos mecanismos:
#
#  1. ORDEN. Dos mensajes del MISMO cliente con medio segundo de diferencia
#     se atienden en paralelo, y el segundo puede contestarse antes que el
#     primero -- el cliente escribe "no tengo internet" y despues "ya volvio",
#     y recibe el diagnostico despues de la confirmacion. Eso no es un
#     problema de escala: la escala solo lo vuelve frecuente. El lock por
#     conversacion lo cierra, y va SIEMPRE PUESTO porque es correccion, no
#     capacidad.
#
#  2. AISLAMIENTO. Los datos de cada empresa ya estan aislados
#     (organization_id en cada consulta), pero la CAPACIDAD no: una empresa
#     con un corte masivo llena los hilos y las demas esperan detras. El
#     semaforo por tenant convierte la avalancha de una en una fila de esa
#     una. Nace APAGADO (max_turnos_simultaneos = None): encenderlo introduce
#     espera, y eso se decide por empresa y midiendo, no por defecto.
#
#  LIMITACION EXPLICITA DE ESTA FASE, Y NO ES UN DETALLE
#  -----------------------------------------------------
#  El lock y el semaforo son estructuras EN MEMORIA DE ESTE PROCESO. Hoy
#  alcanzan porque el motor corre con UN worker (gunicorn --workers 1). El dia
#  que haya dos workers, dos contenedores o escalado horizontal dejan de ser
#  globales:
#
#      worker A  ->  lock de la conversacion 123
#      worker B  ->  OTRO lock de la conversacion 123
#      los dos procesan a la vez
#
#  O sea que esto protege lo que hay, no lo que venga. Antes de subir a mas de
#  un worker hay que mover la exclusion a algo compartido -- un lock consultivo
#  de Postgres (pg_advisory_lock) sobre el id de la conversacion es lo mas
#  barato, porque la base ya esta y ya es el punto de serializacion de todo lo
#  demas. Queda dicho aca y no en un documento aparte: quien suba los workers
#  va a leer este archivo, no ese documento.
# ════════════════════════════════════════════════════════════════════════════

# clave de sesion -> [Lock, cuantos lo estan usando]. El contador es para
# poder BORRAR la entrada: sin eso el diccionario crece un lock por cada
# conversacion que existio, para siempre.
_locks_conversacion: dict = {}
_locks_maestro = threading.Lock()

# tenant -> (semaforo, tope con el que se creo). El tope se relee de la config
# en cada turno; si cambia, el semaforo se rehace. Lo que estaba en vuelo con
# el semaforo viejo no se pierde -- lo suelta en el suyo, que deja de usarse.
_semaforos_tenant: dict = {}
_semaforos_maestro = threading.Lock()

# Cuanto espera un turno por su lugar antes de rendirse. Generoso a proposito:
# rendirse deja al cliente sin respuesta, y eso es peor que tardar. El tope
# esta atado al timeout de gunicorn (180 s) -- pasarse de ahi solo cambia
# quien corta la llamada.
SEGUNDOS_ESPERA_TURNO = 150


@contextlib.contextmanager
def _turno_en_orden(tenant: str, clave, maximo):
    """
    El turno corre solo, y dentro del cupo de su empresa.

    ORDEN DE ADQUISICION: primero el lock de la conversacion, despues el
    semaforo del tenant. Al reves, los mensajes apilados de UN cliente
    ocuparian los cupos de toda la empresa mientras esperan su turno entre
    ellos. Siempre en este orden -- dos ordenes distintos es como se arma un
    abrazo mortal.

    Si no consigue lugar a tiempo levanta TimeoutError: quien llama decide.
    No se atiende igual "por si acaso": atender fuera de orden es justo lo que
    esto viene a impedir.
    """
    with _locks_maestro:
        par = _locks_conversacion.setdefault(clave, [threading.Lock(), 0])
        par[1] += 1
    lock = par[0]
    tomado = lock.acquire(timeout=SEGUNDOS_ESPERA_TURNO)
    try:
        if not tomado:
            raise TimeoutError("no se consiguio el turno de la conversacion")
        semaforo = None
        if maximo:
            with _semaforos_maestro:
                actual = _semaforos_tenant.get(tenant)
                if actual is None or actual[1] != maximo:
                    actual = (threading.BoundedSemaphore(maximo), maximo)
                    _semaforos_tenant[tenant] = actual
                semaforo = actual[0]
            if not semaforo.acquire(timeout=SEGUNDOS_ESPERA_TURNO):
                raise TimeoutError("la empresa esta en su tope de turnos simultaneos")
        try:
            yield
        finally:
            if semaforo is not None:
                semaforo.release()
    finally:
        if tomado:
            lock.release()
        with _locks_maestro:
            par[1] -= 1
            if par[1] <= 0:
                _locks_conversacion.pop(clave, None)

# Cuantos mensajes se vuelven a poner en contexto cuando este proceso no tiene
# la conversacion en memoria (un reinicio, un despliegue). Ver
# persistencia.historial_para_el_modelo.
#
# Veinte y no "todos": el historial en RAM crece de a poco durante una sesion
# viva, pero volcar una conversacion de 200 mensajes de golpe seria pagar de
# una vez un prompt que nadie decidio. Y no es config del tenant: es un
# equilibrio entre costo y memoria del MOTOR, igual para toda empresa.
MENSAJES_A_REHIDRATAR = 20

# Cada cuanto se le pregunta a la base si la version cambio. Acota las dos
# cosas que importan: cuanto puede quedarse vieja una config (este intervalo)
# y cuantas consultas agrega (una cada tantos segundos, no una por turno).
SEGUNDOS_ENTRE_COMPROBACIONES = 15.0


def _config_de(tenant: str):
    # La base manda; el YAML es semilla y respaldo. Ver nucleo/config/fuente.py.
    # Es la misma fila que escribe el editor (nucleo/config/editor.py), asi que
    # leer y guardar apuntan al mismo lugar.
    #
    # Ademas de vaciarse cuando guarda la interfaz (olvidar_config), este cache
    # COMPRUEBA la version contra la base cada tantos segundos. Es lo que
    # arregla el caso silencioso: 'cli/cargar_config.py' escribe en la base
    # desde otro proceso -- o desde otra maquina-- y no puede avisarle a este.
    # Sin la comprobacion, el motor seguia sirviendo la config vieja sin error,
    # sin aviso y sin forma de notarlo salvo reiniciando. Paso el 25/08/2026:
    # se probo dos veces contra un motor que no podia haber tomado el cambio.
    ahora = time.monotonic()
    servida = _configs.get(tenant)

    if servida is not None:
        version, comprobada_en = _servidas.get(tenant, (None, 0.0))
        if ahora - comprobada_en < SEGUNDOS_ENTRE_COMPROBACIONES:
            return servida
        try:
            en_base = fuente.version_en_base(tenant)
        except Exception as e:
            # No poder comprobar la version no es motivo para cortar una
            # conversacion: se sigue sirviendo lo que ya hay y se reintenta en
            # el proximo intervalo. Una config de hace un minuto es mucho mejor
            # que un turno fallido.
            registrar("config", "no se pudo comprobar la version; se sigue con la servida",
                      tenant=tenant, version=version, error=e)
            _servidas[tenant] = (version, ahora)
            return servida
        if en_base == version:
            _servidas[tenant] = (version, ahora)
            return servida
        registrar("config", "la base tiene otra version: recargando",
                  tenant=tenant, en_base=en_base, servida=version)
        _configs.pop(tenant, None)

    # Se pregunta la version ANTES de bajar la config, no despues. Si alguien
    # guarda entre las dos consultas, quedar con la version vieja anotada
    # provoca una recarga de mas en el proximo intervalo; al reves quedaria
    # anotada una version mas nueva que la que se sirve, y no se recargaria
    # nunca -- que es justo el bug que esto viene a cerrar.
    try:
        version = fuente.version_en_base(tenant)
    except Exception:
        version = None
    _configs[tenant] = fuente.cargar(tenant)
    _servidas[tenant] = (version, ahora)
    return _configs[tenant]


def _evidencias_de(tenant: str, conversation_id: str | None) -> int:
    """
    Cuantas imagenes mando el cliente en esta conversacion.

    Solo el NUMERO: quien lea el ticket necesita saber que hay fotos para ir a
    buscarlas, no recibirlas ahi. Las imagenes ya se guardan colgadas de la
    conversacion desde antes (ver _guardar_adjunto); esta etapa no las
    interpreta, solo las cuenta.

    Nunca rompe el turno: sin el conteo la ficha sale igual, con una linea
    menos.
    """
    if not conversation_id:
        return 0
    try:
        with persistencia.sesion(tenant) as (cur, _org):
            cur.execute(
                """select count(*) as n from asistente.media
                   where conversation_id = %s and tipo = 'image'""",
                (conversation_id,))
            fila = cur.fetchone()
        return int((fila or {}).get("n") or 0)
    except Exception as e:                            # noqa: BLE001
        registrar("escalamiento", "no se pudieron contar las evidencias", error=e)
        return 0


def _primer_mensaje_del_cliente(historial: list[dict]) -> str:
    """
    Lo primero que escribio el cliente, sin resumir.

    Es el respaldo cuando no hay resumen del evaluador. No es tan bueno como
    una sintesis, pero es de el y es cierto -- que es mas de lo que se puede
    decir de un texto de relleno. Misma eleccion que ya hace la bandeja
    (conversaciones/[id]/+page.svelte::primerPedido); aca se repite para el
    ticket de la operacion, que a diferencia de la pantalla no tiene el
    historial a mano para resolverlo solo.
    """
    for mensaje in historial or []:
        if mensaje.get("role") == "user" and (mensaje.get("content") or "").strip():
            return mensaje["content"].strip()
    return ""


def _mensaje_de_escalada(config, motivo: str | None) -> str:
    """
    Lo que se le dice al cliente al pasarlo a una persona.

    El del motivo si lo hay, y si no el general. No todos los motivos son una
    queja: el texto generico habla de una molestia, y suena mal cuando el
    cliente pidio un tramite y todo salio bien -- visto el 28/08/2026 con un
    cambio de clave de WiFi, donde el cliente no se habia quejado de nada.

    Nunca queda vacio por elegir mal la clave: un motivo sin texto propio cae
    al generico, que siempre existe.
    """
    esc = config.escalamiento
    propio = (esc.mensajes_por_motivo or {}).get(motivo or "", "")
    return (propio or esc.mensaje or "").strip()


def _pregunta_de_cierre(config) -> str:
    """
    Lo que se le pregunta al cliente antes de cerrarle la conversacion.

    Vacio si el tenant no la declaro, y entonces se cierra como antes. No hay
    texto de reserva a proposito: los otros mensajes de reserva existen porque
    quedarse callado seria peor, y aca callarse significa exactamente lo que
    la empresa pidio -- no preguntar.
    """
    return (config.conversaciones.pregunta_antes_de_cerrar or "").strip()


def _pregunta_pide_humano(config) -> str:
    """
    Lo que se le pregunta al cliente cuando SUENA a que querria una persona
    pero no la pidio.

    Vacia si el tenant no la declaro, y entonces no se pregunta nunca: el
    comportamiento de siempre. Ver Escalamiento.pregunta_pide_humano.
    """
    return (config.escalamiento.pregunta_pide_humano or "").strip()


def _decidir_pedido_humano(config, historial):
    """
    (decision, evidencia) de los tres niveles.

    El cuerpo se mudo a nucleo/seguimiento/forzado.py cuando aparecio un
    segundo llamador (cli/evaluar.py): una sola implementacion, o la prueba
    termina midiendo su propia copia. Se deja este nombre porque lo usan
    varios puntos de este archivo.
    """
    return decidir_pedido_humano_de(config, historial)


# Lo que se le dice al modelo segun como haya terminado la comprobacion. El
# estado lo calcula el codigo; esto solo lo traduce a una instruccion, porque
# saber "ACCION_CONFIRMADA" no le dice al modelo que hacer con eso.
#
# El texto de ACCION_CONFIRMADA es el mas importante de los cuatro: confirmar
# que el equipo reinicio NO es confirmar que el cliente tiene internet. Ese
# dato no lo tiene ningun endpoint -- lo tiene el cliente, y hay que
# preguntarselo.
_INSTRUCCION_VERIFICACION = {
    verificacion_accion.CONFIRMADA:
        "El equipo hizo lo que se le pidio y volvio a responder. Eso NO "
        "significa que el cliente ya tenga servicio: preguntale si le volvio, "
        "con esas palabras, y espera su respuesta antes de dar nada por "
        "resuelto.",
    verificacion_accion.NO_CONFIRMADA:
        "Se midio y el efecto no aparecio. NO le digas que quedo resuelto y "
        "NO repitas la accion. El caso pasa a una persona del equipo.",
    verificacion_accion.NO_VERIFICABLE:
        "No se pudo comprobar -- no que haya fallado, sino que no hubo con "
        "que medir. No afirmes que se resolvio ni que no se resolvio; dile al "
        "cliente que estas confirmando y que un compañero sigue el caso.",
    verificacion_accion.PENDIENTE:
        "Todavia no se puede comprobar: hace falta que pase mas tiempo. NO "
        "afirmes que quedo resuelto. Si el cliente pregunta, dile que estas "
        "esperando para confirmar.",
}


def _resolver_verificacion_pendiente(config, tenant: str, estado: dict) -> dict | None:
    """
    Mide y cierra la verificacion que dejo un turno anterior, si ya vencio.

    Devuelve None cuando no hay nada que comprobar. Si hay, devuelve el estado
    calculado, la nota que se le inyecta al modelo, y --cuando corresponda-- el
    motivo con el que hay que escalar.

    Corre al empezar el turno y no al final del anterior por lo unico que
    importa: el equipo necesita minutos para volver, y bloquear el turno
    esperandolo deja al cliente mirando "escribiendo" por algo que no depende
    de nosotros. Cuando vuelve a escribir, el plazo ya paso.
    """
    conversacion = estado.get("conversacion_id")
    if not conversacion:
        return None
    pendiente = persistencia.verificacion_pendiente_de(tenant, conversacion)
    if not pendiente:
        return None

    herramienta = next((h for h in config.herramientas
                        if h.nombre == pendiente["herramienta"]), None)
    if herramienta is None or not herramienta.verificacion:
        # La herramienta dejo de declarar verificacion (cambio de config entre
        # un turno y otro). No se puede medir contra un criterio que ya no
        # existe, y dejarla pendiente para siempre trabaria el cierre.
        persistencia.resolver_verificacion(
            tenant, pendiente["id"], verificacion_accion.NO_VERIFICABLE,
            "la herramienta ya no declara como comprobarse", None,
            pendiente["intentos"])
        return None

    if not pendiente["vencida"]:
        return {"estado": verificacion_accion.PENDIENTE,
                "nota": _nota_verificacion(pendiente["herramienta"],
                                           verificacion_accion.PENDIENTE, "")}

    intentos = int(pendiente["intentos"]) + 1
    medicion_posterior = motor.medir_para_verificar(
        config, herramienta.verificacion, estado["sesion"],
        config.identidad.slug, config.variables_tenant)
    resultado, por_que = verificacion_accion.evaluar(
        herramienta.verificacion.comprobaciones,
        pendiente["medicion_previa"] or {}, medicion_posterior,
        intentos, int(pendiente["max_intentos"]))
    persistencia.resolver_verificacion(
        tenant, pendiente["id"], resultado, por_que, medicion_posterior, intentos)
    # El 'por que' queda en la fila (resolver_verificacion), no en el log: lo
    # arma la medicion de un equipo externo y puede traer sus datos.
    registrar("verificacion", "accion comprobada",
              herramienta=pendiente["herramienta"], resultado=resultado,
              intento=intentos, max_intentos=pendiente["max_intentos"],
              verificacion_id=str(pendiente["id"]))

    salida = {"estado": resultado,
              "nota": _nota_verificacion(pendiente["herramienta"], resultado, por_que)}
    if (resultado in (verificacion_accion.NO_CONFIRMADA,
                      verificacion_accion.NO_VERIFICABLE)
            and herramienta.verificacion.escalar_si_no_confirma):
        salida["motivo_escalada"] = herramienta.verificacion.escalar_si_no_confirma
        salida["por_que"] = f"'{pendiente['herramienta']}' termino en {resultado}: {por_que}"
    return salida


def _cerrar_el_traspaso(config, tenant: str, conversation_id, mensaje_id,
                        respuesta: str, id_sesion: str, *, evaluador_fallo: bool,
                        se_intento: bool, caso_creado: bool,
                        ticket_creado: bool, reservado: bool = False) -> str:
    """
    Decide en que termino el traspaso, lo deja escrito, y --si no quedo
    confirmado-- impide que la respuesta lo prometa.

    Devuelve el texto que de verdad sale al cliente.

    LA GARANTIA, EN UNA LINEA: el texto del tenant solo REEMPLAZA al del
    modelo dentro de la rama de escalada. Cuando esa rama no corre --porque el
    evaluador se cayo-- el modelo queda libre de prometer lo que quiera, y el
    02/09/2026 prometio "tu caso ya quedo en manos de un colaborador humano"
    sin caso, sin ticket y sin escalada. Esto cierra esa puerta desde afuera.

    NO_DETERMINADO no se convierte en escalada: no se toca
    'escalada_a_humano' --eso pausaria al bot y afirmaria un traspaso que no
    ocurrio-- pero la conversacion queda marcada para que una persona la mire,
    que es un registro real y no una promesa.
    """
    estado, por_que = estado_escalada.calcular(
        evaluador_fallo, se_intento, caso_creado, ticket_creado)
    if not estado or not conversation_id:
        return respuesta

    necesita_persona = estado == estado_escalada.NO_DETERMINADO
    persistencia.registrar_estado_escalada(
        tenant, conversation_id, estado, por_que, necesita_atencion=necesita_persona)
    registrar("escalamiento", "traspaso registrado",
              conversation_id=str(conversation_id), estado=estado)

    if estado == estado_escalada.CONFIRMADO:
        return respuesta
    # Con el control humano reservado en la base, prometer una persona es
    # cierto aunque no haya caso ni ticket: la conversacion ya esta en la cola
    # de personas. El estado NO_CONFIRMADO queda anotado igual (el efecto
    # externo fallo), pero la respuesta no se reemplaza.
    if reservado:
        return respuesta

    # No quedo confirmado: la respuesta no puede prometer una persona. Se
    # revisa SOLO en este camino, que es lo que vuelve segura la comparacion
    # por frases -- en un turno normal ni se ejecuta.
    frase = estado_escalada.promete_traspaso(
        respuesta, config.escalamiento.frases_de_traspaso)
    if not frase:
        return respuesta

    registrar("escalamiento", "la respuesta prometia un traspaso sin nada registrado: se reemplaza",
              conversation_id=str(conversation_id),
              mensaje_id=str(mensaje_id) if mensaje_id else None)
    respuesta = _mensaje_si_no_quedo(config)
    if mensaje_id:
        # El mensaje ya se guardo con el texto del modelo: sin esto, la
        # bandeja mostraria la promesa que el cliente nunca recibio.
        try:
            persistencia.actualizar_contenido_mensaje(tenant, mensaje_id, respuesta)
        except Exception as e:
            registrar("persistencia", "no se pudo corregir el mensaje", error=e)
    return respuesta


def _hay_verificacion_pendiente(tenant: str, conversation_id) -> bool:
    """
    Si esta conversacion tiene una accion ejecutada y todavia sin comprobar.

    Ante la duda dice que NO hay: un fallo al leer la base no puede dejar
    conversaciones imposibles de cerrar para siempre. Es la eleccion menos
    mala de las dos -- la otra es un cliente atrapado.
    """
    if not conversation_id:
        return False
    return bool(persistencia.verificacion_pendiente_de(tenant, conversation_id))


def _nota_verificacion(herramienta: str, resultado: str, por_que: str) -> str:
    """El resultado, ya calculado, en la forma en que el modelo lo recibe."""
    detalle = f" ({por_que})" if por_que else ""
    return ("(Nota del sistema, no del cliente) Comprobacion de "
            f"'{herramienta}': {resultado}{detalle}. "
            + _INSTRUCCION_VERIFICACION.get(resultado, ""))


def _mensaje_de_cierre(config) -> str:
    """
    Lo que se le dice al cliente cuando el mismo da el caso por resuelto.

    El de reserva vive aca por lo mismo que el de la escalada fallida: es el
    ultimo mensaje de la conversacion, y quedarse callado por tener un campo
    vacio en la config seria terminar mal un caso que salio bien.
    """
    return ((config.escalamiento.mensaje_cierre_cliente or "").strip()
            or "Listo, cierro tu caso. Si necesitas algo mas, escribime "
               "cuando quieras.")


def _mensaje_si_no_quedo(config) -> str:
    """
    Lo que se le dice al cliente cuando el traspaso NO se pudo registrar.

    Tiene que pedirle que vuelva a escribir, y no es por cortesia: la
    conversacion no quedo marcada, asi que el reintento ocurre en el proximo
    turno -- y el proximo turno empieza con un mensaje suyo. Sin ese mensaje
    no hay reintento y el caso no existe para nadie.

    El texto es del tenant, pero el de reserva vive aca: es justo el momento
    en que algo ya fallo, y quedarse callado por tener un campo vacio en la
    config seria fallar dos veces.
    """
    return ((config.escalamiento.mensaje_si_falla or "").strip()
            or "No pude dejar registrado tu caso en este momento. Escribeme "
               "de nuevo en un par de minutos y lo intento otra vez.")


def olvidar_config(tenant: str) -> None:
    """Descarta la copia cacheada para que el proximo turno relea de la base.
    Se llama tras cada guardado del editor: sin esto, un cambio hecho desde la
    interfaz no se veria hasta reiniciar el proceso.

    Se descarta en vez de reemplazarse por lo que devolvio el editor, aunque
    sea el mismo objeto: asi lo que se sirve es siempre lo que quedo ESCRITO,
    y un guardado que no llego a la base se nota en el siguiente turno en vez
    de quedar tapado por una copia en memoria que dice lo contrario."""
    _configs.pop(tenant, None)
    _servidas.pop(tenant, None)


_TOKEN_SERVICIO = os.environ.get("MOTOR_SERVICE_TOKEN")
if _TOKEN_SERVICIO:
    registrar("auth", "MOTOR_SERVICE_TOKEN activo: /chat, /agentes y el resto de "
                      "rutas internas exigen el token de servicio.")
else:
    registrar("auth", "MOTOR_SERVICE_TOKEN no esta configurado -- las rutas "
                      "internas quedan abiertas a quien alcance el motor por red. Ver "
                      "DESPLIEGUE.md, 'Autenticar /chat y /agentes en el motor'.")

# Rutas que se autentican con OTRO mecanismo (no el token de servicio), asi
# que quedan afuera de la comprobacion de abajo:
#   - el webhook de WhatsApp: Meta lo firma (verify_token en el handshake,
#     X-Hub-Signature-256 en los mensajes), y Meta no puede mandar un header
#     nuestro -- exigirselo lo dejaria afuera a el, no a un atacante.
#   - /salud: lo pega el healthcheck de Dokploy, sin credenciales, y no
#     devuelve nada mas que {"estado": "ok"}.
_RUTAS_SIN_TOKEN = {"/salud"}
_PREFIJOS_SIN_TOKEN = ("/canales/whatsapp/",)


@app.before_request
def _exigir_token_de_servicio():
    """
    Hoy lo unico que separa /chat, /agentes y el resto de internet es el
    'PathPrefix' de una regla de Traefik -- una sola capa, cuando el resto
    del proyecto usa dos por principio (PRD.md 7.4: las reglas duras se
    aplican en codigo, no solo en la configuracion de alrededor). Una regla
    mal escrita al agregar un dominio y cualquiera puede conversar con el
    asistente a costa de la empresa, o leer como esta configurado cada
    agente. Ver DESPLIEGUE.md.

    Si 'MOTOR_SERVICE_TOKEN' no esta configurado, no se bloquea nada -- el
    valor por defecto no puede romper un despliegue que todavia no cargo la
    variable (arranque local, el compose de desarrollo). Una vez cargada,
    es fail-closed: falta o no coincide, 401.
    """
    if not _TOKEN_SERVICIO:
        return None
    if request.path in _RUTAS_SIN_TOKEN or request.path.startswith(_PREFIJOS_SIN_TOKEN):
        return None
    recibido = request.headers.get("X-Servicio-Token", "")
    if recibido != _TOKEN_SERVICIO:
        return jsonify({"error": "Token de servicio invalido o ausente."}), 401
    return None


@app.errorhandler(Exception)
def _error_no_manejado(e):
    """
    Una excepcion que ninguna ruta atrapo. Sin esto Flask la registra con su
    traza completa, y la ultima linea de una traza es str(e): un error de
    PostgreSQL con el valor que fallo, uno de requests con la URL. Ver
    nucleo/observabilidad/registro.py (D20).

    LOS HTTPException NO SON FALLOS DEL MOTOR y conservan su codigo: un 404 de
    ruta inexistente, un 405, o cualquier abort(401/403/409/503) sigue siendo
    ese codigo, nunca un 500. Se responden con un JSON generico (el nombre
    estandar del codigo) en vez de la pagina HTML de werkzeug, que repite la
    'description' de quien hizo abort(); y se conservan sus cabeceras propias
    (Allow en un 405, WWW-Authenticate en un 401). Las redirecciones de ruteo
    (308 por la barra final) pasan tal cual.

    Las rutas que devuelven su error con jsonify(..., 4xx) ni pasan por aca:
    eso es una respuesta, no una excepcion.
    """
    if isinstance(e, HTTPException):
        if e.code is None or e.code < 400:
            return e
        respuesta = jsonify({"error": e.name})
        respuesta.status_code = e.code
        for nombre, valor in e.get_headers():
            if nombre.lower() not in ("content-type", "content-length"):
                respuesta.headers[nombre] = valor
        return respuesta
    registrar("http", "error no manejado", metodo=request.method,
              ruta=request.url_rule.rule if request.url_rule else None, error=e)
    return jsonify({"error": "Error interno del motor."}), 500


def _error_al_guardar(e: Exception):
    """Todo lo que no sea un problema de la configuracion en si (la base
    inalcanzable, el tenant sin cargar) es un fallo del servidor, no del
    formulario: no se devuelve 400 porque no hay nada que el usuario pueda
    corregir escribiendo distinto."""
    return fallo(500, "guardado_fallido", "No se pudo guardar la configuracion en la base.",
                 componente="editor", e=e)


def _agente_supervisor_json(config) -> dict | None:
    """
    El supervisor (nucleo/seguimiento/supervisor.py) no es un Rol real: no
    esta en config.roles, no tiene 'puede_consultar' ni conversa con nadie --
    revisa en segundo plano cada conversacion que se cierra y propone aportes
    al manual. Se arma a mano (no via _agente_json, que asume un Rol de
    verdad) para que la pantalla de Agentes pueda mostrar que existe, sin
    forzarlo al mismo molde de tarjeta editable que un agente conversacional.

    Solo aparece si el manual esta configurado -- mismo guard que
    supervisor.revisar(), que sin 'manual.casos' ni siquiera llama al modelo.
    """
    if not config.manual.casos:
        return None
    return {
        "nombre": "supervisor",
        "descripcion": (
            "Revisa cada conversacion cerrada y propone aportes al manual de "
            "procedimientos. No conversa con nadie ni tiene herramientas: "
            "corre solo, y cada aporte queda pendiente hasta que una persona "
            "lo aprueba o lo descarta desde /manual."),
        "modelo": config.llm.overrides.get("rol:supervisor"),
        "automatico": True,
        "herramientas": [],
    }


def _agente_json(nombre: str, rol, config) -> dict:
    herramientas = motor.herramientas_del_rol(config, rol)
    return {
        "nombre": nombre,
        "descripcion": rol.descripcion.strip(),
        "area": rol.area,
        "cargo": rol.cargo,
        "orientado_a": rol.orientado_a,
        # El system prompt REAL, partido en piezas con su origen. Sin esto,
        # para saber por que un agente contesto algo hay que reconstruirlo de
        # memoria cruzando cuatro secciones de la configuracion -- y el
        # trabajo termina en el prompt aunque la causa este en otro lado (ver
        # 'confirmar_identidad' faltante en la base, agosto 2026).
        "prompt_piezas": piezas_del_system(config, nombre),
        "herramientas": [
            {
                "nombre": h.nombre, "descripcion": h.descripcion.strip(), "tipo": h.tipo,
                "campos_permitidos": rol.campos_permitidos.get(h.nombre, []),
                # Lo que separa mirar de HACER. 'agendar_visita_tecnica' crea
                # una visita real, con costo y logistica; en la tarjeta se veia
                # igual que una consulta porque este dato no viajaba. Es lo
                # primero que hay que ver para revisar que puede hacer un
                # agente, no un detalle.
                "solo_lectura": h.solo_lectura,
                "requiere_confirmacion": h.requiere_confirmacion,
            }
            for h in herramientas
        ],
    }


def _sesion_nueva(tenant: str, id_sesion: str, canal: str,
                  horas_inactividad: int | None = None) -> dict:
    """
    El estado en memoria de una conversacion que el proceso no tenia, LEIDO
    de la base cuando hay una conversacion abierta con esta persona.

    Sin esto, un reinicio del motor equivalia a borrarle la memoria al
    asistente en mitad de una conversacion: la marca de escalamiento se perdia
    y el bot volvia a atender a alguien a quien ya se le habia dicho que lo
    pasaba con una persona, y la verificacion se perdia y habia que pedirle la
    cedula de nuevo.

    Lo que NO se rehidrata es el historial de mensajes: son dos decisiones
    distintas. El escalamiento y la identidad son estado, chico y acotado; el
    historial es contexto que viaja al modelo en cada turno y crece sin techo.
    Restaurarlo se puede hacer, pero cambia el costo de cada llamada y merece
    decidirse aparte.

    Un fallo al leer NO impide atender: se arranca en blanco, que es
    exactamente lo que pasaba antes. Peor que empezar sin memoria es no
    contestarle a un cliente.
    """
    estado = {"sesion": Sesion(identificador_canal=id_sesion),
              "historial": [], "escalada": False, "caso_id": None, "rol_activo": None,
              "repreguntado_agendamiento": False, "nota_pendiente": None,
              # Un agendamiento que quedo a medias, para poder retomarlo en el
              # turno siguiente aunque el modelo no vuelva a pedir escalar.
              "agendamiento_pendiente": None,
              # Distinto de 'escalada': esa se apaga a proposito cuando no hay
              # humano a quien esperar (ver mas abajo), y sin esta bandera esa
              # misma pausa apagada volvia a habilitar la evaluacion en el
              # turno siguiente y se creaba un caso duplicado.
              "ya_escalada": False,
              # Esta conversacion ya tuvo su vuelta extra antes de escalar
              # (ver escalamiento.merece_un_intento). Vive en memoria, como
              # 'repreguntado_agendamiento': si el motor se reinicia se
              # concede un intento mas, que es un costo aceptable frente a
              # una lectura extra a la base en cada turno.
              "intento_antes_de_escalar": False,
              # La conversacion abierta de este usuario, si ya habia una.
              "conversacion_id": None,
              # Por que se escalo, para que el aviso de la pausa siga
              # hablando el mismo idioma que el del traspaso.
              "motivo_escalada": None,
              # Ya se le pregunto al cliente si se puede cerrar. Vive en
              # memoria, como 'intento_antes_de_escalar': si el motor se
              # reinicia se le vuelve a preguntar una vez, que es el error
              # barato de los dos posibles.
              "cierre_propuesto": False}
    try:
        previo = persistencia.estado_de_conversacion_abierta(
            tenant, canal, id_sesion, horas_inactividad)
    except Exception as e:
        registrar("sesion", "no se pudo leer el estado previo",
                  tenant=tenant, canal=canal, sesion=ref_sesion(id_sesion), error=e)
        return estado
    if not previo:
        return estado

    # La pausa solo tiene sentido si hay un HUMANO al que esperar. Una
    # conversacion escalada pero agendada sola (nucleo/seguimiento/
    # agendamiento.py) no tiene caso de BottleCRM abierto que la retome --
    # pausarla la dejaria muda con ese cliente para siempre.
    estado["escalada"] = previo["escalada"] and previo["necesita_atencion_humana"]
    # Sin el 'and': lo que interesa aca no es si el bot esta en pausa, sino si
    # esta conversacion YA tiene un caso creado. Son cosas distintas.
    #
    # Y POR ESO TAMBIEN MIRA 'caso_id', no solo la bandera de escalada.
    #
    # 'escalada_a_humano' dejo de significar "tiene caso" el dia que se pudo
    # devolver una conversacion al asistente: 'devolver_al_asistente' la apaga
    # pero NO cierra el caso, a proposito -- sigue abierto para que cuando el
    # cliente diga que ya quedo se cierren los tres juntos.
    #
    # El camino en memoria ya lo tenia bien: al devolver, api.py apaga la
    # pausa y deja 'ya_escalada' como estaba, con su comentario explicando que
    # es lo que evita un segundo caso. Lo que se perdia era al RECONSTRUIR la
    # sesion desde la base, donde 'ya_escalada' volvia en false. O sea que la
    # proteccion vivia solo en memoria -- y con autodeploy encendido este
    # proceso se reinicia varias veces por dia.
    #
    # La secuencia es corta: escala (caso A abierto) -> una persona responde y
    # devuelve -> el motor se reinicia -> el cliente escribe -> el bot no
    # resuelve y escala -> caso B, con el A todavia abierto. Y escalar() no
    # comprueba nada: siempre crea uno.
    #
    # Cuando el caso se cierra DE VERDAD no hace falta nada de esto: la rama
    # de atender_turno que detecta el cierre pone 'ya_escalada' en false a
    # mano, y ahi un caso nuevo es legitimo y no un duplicado.
    estado["ya_escalada"] = bool(previo["escalada"] or previo["caso_id"])
    estado["caso_id"] = previo["caso_id"]
    # Cual es la conversacion en curso. Hace falta ANTES de que el turno
    # cree la suya: el camino pausado decide si un "ok" del cliente puede
    # cerrar el caso, y para eso tiene que poder preguntar por esta fila.
    estado["conversacion_id"] = previo["conversation_id"]
    estado["motivo_escalada"] = previo["motivo_escalada"]
    # Se guarda tal cual vino de la base, sin validar todavia contra la
    # config (esta funcion no la recibe) -- atender_turno() la revalida
    # antes de usarla, por si el rol cambio o se borro desde entonces.
    estado["rol_activo"] = previo["rol_efectivo"]

    # La identidad se restaura solo mientras la conversacion siga ABIERTA (es
    # la unica que devuelve la consulta): al cerrarse, la siguiente empieza de
    # cero y hay que verificar otra vez. Esa es la frontera -- se continua una
    # conversacion, no se recuerda a una persona para siempre.
    if previo["id_cliente"]:
        estado["sesion"].verificado = True
        estado["sesion"].nivel = max(estado["sesion"].nivel, 1)
        estado["sesion"].id_cliente = previo["id_cliente"]
        estado["sesion"].nombre = previo["nombre_cliente"]
        # Y los identificadores tecnicos que capturo la verificacion (el
        # serial de la ONU, la interfaz). Sin esto la conversacion volvia
        # verificada pero MUDA para cualquier herramienta que los necesite:
        # el cliente recibia un diagnostico a ciegas y nada lo denunciaba
        # -- la guarda fallaba cerrado y el modelo seguia por el camino
        # alternativo. Visto en produccion el 15/08/2026.
        for campo, valor in (previo.get("datos_sesion") or {}).items():
            if campo in Sesion.CAMPOS_PERSISTIBLES and valor:
                setattr(estado["sesion"], campo, valor)

    # El estado de ROUTING se restaura SIEMPRE, tambien sin identidad
    # resuelta -- fuera del 'if' de arriba a proposito. El anti-rebote se
    # llena al derivar, que pasa antes de que nadie verifique nada: dejarlo
    # dentro habria protegido solo a las conversaciones ya verificadas y
    # ninguna otra. Ver Sesion.CAMPOS_ROUTING_PERSISTIBLES.
    #
    # Se copia la lista en vez de asignar la de la base: asignarla dejaria a
    # dos sesiones distintas compartiendo el mismo objeto si alguna vez se
    # rehidratan del mismo diccionario, y esta lista se muta con append.
    for campo, valor in (previo.get("datos_sesion") or {}).items():
        if campo in Sesion.CAMPOS_ROUTING_PERSISTIBLES and valor:
            setattr(estado["sesion"], campo, list(valor))

    visitadas = getattr(estado["sesion"], "areas_visitadas", [])
    registrar("sesion", "se retoma la conversacion abierta",
              conversation_id=str(previo["conversation_id"]),
              escalada=bool(previo["escalada"]),
              verificado=bool(previo["id_cliente"]),
              areas_visitadas=list(visitadas))
    return estado


def _sincronizar_respuesta_en_memoria(historial: list[dict], desde: int,
                                      respuesta: str) -> None:
    """Deja la ULTIMA respuesta del asistente agregada en este turno (a partir
    del indice 'desde') con el texto que de verdad salio. No toca lo anterior
    al turno ni agrega nada si el turno no produjo respuesta."""
    for msg in reversed(historial[desde:]):
        if msg.get("role") == "assistant":
            if msg.get("content") != respuesta:
                msg["content"] = respuesta
            return


# --- D24: el control puede cambiar mientras el modelo piensa -----------------
#
# La compuerta de B3.3b lee el control ANTES de llamar al modelo, y el modelo
# tarda segundos. Si en ese intervalo una persona interviene, la respuesta que
# vuelve se calculo con un control que ya no existe. Por eso el turno guarda que
# autorizo (conversacion y relevo_version) y lo vuelve a comprobar en dos
# puntos, siempre fuera de cualquier transaccion:
#
#   1. al volver del modelo, antes de guardar la respuesta o tocar la memoria;
#   2. justo antes del POST a Meta (whatsapp_webhook).
#
# PUNTO DE NO RETORNO: una intervencion impide todo envio de la IA cuyo POST al
# proveedor todavia no empezo cuando la intervencion queda durable. Un POST que
# ya estaba en vuelo puede completar. No se sostiene una transaccion abierta
# esperando a Meta (P-A); la garantia absoluta pediria una reserva durable de
# salida (outbox), que no es de esta fase.
#
# Contadores por proceso, para que operaciones vea si esto pasa seguido. Los
# logs llevan el id de la conversacion y versiones: nunca el telefono ni el
# contenido.
contadores_relevo = {"control_no_determinado": 0,
                     "respuesta_ia_descartada_por_cambio_de_control": 0,
                     "accion_ia_cancelada_por_cambio_de_control": 0}


def _contar_relevo(evento: str, **campos) -> None:
    contadores_relevo[evento] = contadores_relevo.get(evento, 0) + 1
    # Campos con nombre y no un texto armado: ver nucleo/observabilidad/registro.py (D20).
    registrar("relevo", "contador", contador=evento, **campos)


def _autorizacion_de(control_actual: dict | None) -> dict:
    """Lo que autorizo el turno: la conversacion abierta (None si no habia) y
    su relevo_version (0 si no habia: una conversacion nueva nace en 0)."""
    if control_actual is None:
        return {"conversation_id": None, "relevo_version": 0}
    return {"conversation_id": control_actual["conversation_id"],
            "relevo_version": control_actual["relevo_version"]}


def _turno_sigue_autorizado(tenant: str, canal: str, id_sesion: str,
                            autorizacion: dict, *, exigir_ia: bool) -> bool:
    """
    True solo si la conversacion sigue abierta, es la misma, no cambio de
    relevo_version y (si se pide) su control efectivo sigue siendo 'ia'. Si la
    base no responde, False: falla cerrado.

    'exigir_ia' es False en el segundo punto porque el mismo turno puede haber
    escalado (y entonces el control es humano con la version que ESE turno
    escribio, que ya esta en la autorizacion): lo que se compara es que nadie
    mas haya movido la version.
    """
    try:
        actual = persistencia.control_de_conversacion_abierta(tenant, canal, id_sesion)
    except Exception as e:
        _contar_relevo("control_no_determinado",
                       conversation_id=id_interno(autorizacion.get("conversation_id")),
                       punto="al_revalidar", error=e)
        return False
    return autorizacion_relevo.regla_turno(autorizacion, actual, exigir_ia=exigir_ia)


def _escalada_sigue_vigente(tenant: str, escalada: dict) -> bool:
    """SYNC_ESCALADA (autorizacion.regla_escalada), leido de la base. Si la base
    no responde, False: falla cerrado."""
    try:
        vigencia = persistencia.vigencia_de_escalada(
            tenant, escalada["conversation_id"], escalada["version"],
            autorizacion_relevo.INVALIDAN_ESCALADA)
    except Exception as e:
        _contar_relevo("control_no_determinado",
                       conversation_id=id_interno(escalada.get("conversation_id")),
                       punto="vigencia_de_escalada", error=e)
        return False
    return autorizacion_relevo.regla_escalada(vigencia)


def _efecto_del_turno(tenant: str, canal: str, id_sesion: str, estado: dict, que: str, *,
                      clase: str = autorizacion_relevo.AUTONOMO_IA) -> bool:
    """
    D25: si un efecto que escribe, originado por este turno, todavia puede
    empezar. Se pregunta justo antes de iniciarlo. Las reglas de cada clase
    viven en nucleo/relevo/autorizacion.py; aca solo se lee la base.

    Una denegacion AUTONOMO_IA dura todo el turno: despues de una intervencion
    la IA no vuelve a preguntar ni reintenta. SYNC_ESCALADA no se revoca por
    eso: su obligacion es de la escalada, no de la IA.
    """
    autorizacion = estado["autorizacion_turno"]
    if clase == autorizacion_relevo.SYNC_ESCALADA:
        escalada = estado.get("escalada_del_turno")
        permitido = bool(escalada) and _escalada_sigue_vigente(tenant, escalada)
    elif clase == autorizacion_relevo.AUTOMATICO_EN_PAUSA:
        permitido = _turno_sigue_autorizado(tenant, canal, id_sesion, autorizacion, exigir_ia=False)
    elif autorizacion.get("revocada"):
        permitido = False
    else:
        permitido = _turno_sigue_autorizado(
            tenant, canal, id_sesion, autorizacion,
            exigir_ia=not autorizacion.get("legado_retomado"))
        if not permitido:
            autorizacion["revocada"] = True
    if not permitido:
        _contar_relevo("accion_ia_cancelada_por_cambio_de_control",
                       conversation_id=id_interno(autorizacion.get("conversation_id")),
                       version=autorizacion.get("relevo_version"), efecto=que, clase=clase)
    return permitido


def eventos_identidad_de(llamadas) -> list[dict]:
    """Los eventos del embudo de identidad que dejo el turno, listos para la
    base: lo que motor.evento_identidad clasifico, mas la herramienta. Funcion
    aparte para poder afirmarla sin hilo ni base."""
    return [dict(l["identidad"], herramienta=l.get("herramienta"))
            for l in (llamadas or []) if l and l.get("identidad")]


def _quitar_respuesta_de_memoria(historial: list, desde: int | None = None) -> None:
    """Saca de la memoria lo que produjo el modelo en este turno y deja el
    mensaje del cliente. 'desde' es el largo antes del modelo; sin el, se corta
    despues del ultimo mensaje del cliente."""
    if desde is None:
        ultimos = [i for i, m in enumerate(historial) if m.get("role") == "user"]
        if not ultimos:
            return
        del historial[ultimos[-1] + 1:]
        return
    del historial[desde:]


class _CierreCancelado(Exception):
    """El cierre por confirmacion no empieza: cambio el control (D25)."""


# Lo que un rol que NO puede verificar no tiene por que estar pidiendo. Sin
# tildes y en minuscula, porque asi se compara.
_PIDE_IDENTIDAD = ("cedula", "documento de identidad", "numero de documento",
                   "dni", "numero de identificacion", "tu documento")

# Lo que se le dice al modelo al reencauzarlo. No es un regaño ni una regla
# nueva: es la que YA tiene, repetida en el unico momento en que se puede
# comprobar que no la siguio.
INSTRUCCION_REENCAUZAR = (
    "AVISO INTERNO (no se lo menciones al cliente): en tu respuesta anterior "
    "le pediste un dato de identidad, y vos no verificas identidad ni tenes "
    "herramienta para hacerlo. El dato que te de no lo vas a poder usar. "
    "Llama a derivar_a_area con el area que corresponda: alli SI se verifica "
    "y alli se le va a pedir lo que haga falta. No le anuncies el pase ni le "
    "pidas que espere. "
    "Y si la descripcion de derivar_a_area te pide verificar identidad antes "
    "de derivar: esa condicion es para los roles que SI pueden verificarla. "
    "No es tu caso. Si esperas a verificar, esta conversacion no avanza nunca."
)


def _sin_tildes(texto: str) -> str:
    reemplazos = {"a": "áà", "e": "éè", "i": "íì", "o": "óò", "u": "úùü"}
    salida = texto.lower()
    for llano, acentuadas in reemplazos.items():
        for x in acentuadas:
            salida = salida.replace(x, llano)
    return salida


def _derivo_en_este_turno(config, rol: str, llamadas) -> bool:
    """Se llamo una herramienta que deriva, EN ESTE TURNO.

    No es lo mismo que "ya no pide identidad": una respuesta que deja de
    nombrar la cedula sin derivar tampoco resolvio nada, y contarla como
    derivacion vuelve inutil la medicion que justifica esta guarda.
    """
    cfg_rol = (getattr(config, "roles", None) or {}).get(rol)
    if cfg_rol is None:
        return False
    catalogo = {h.nombre: h for h in getattr(config, "herramientas", []) or []}
    derivadoras = {n for n in (getattr(cfg_rol, "puede_consultar", None) or [])
                   if n in catalogo and getattr(catalogo[n], "deriva_rol", None)}
    return any((l or {}).get("herramienta") in derivadoras for l in (llamadas or []))


def debe_reencauzar_a_derivacion(config, rol: str, respuesta: str, llamadas) -> bool:
    """
    Este turno pidio un dato de identidad SIN poder verificarlo ni haber
    derivado?

    DE DONDE SALE. El 22/09/2026, en produccion, 'cliente_final' le pidio a un
    cliente el nombre y el "DNI" para darse de baja, el cliente los mando, y
    el asistente volvio a pedirlos. Ocho horas dando vueltas, cero
    herramientas. Su instruccion dice tres veces que no verifica y que derive
    a facturacion; ademas 'DNI' no aparece en ninguna parte de esa
    instruccion. El modelo se invento un flujo.

    POR QUE NO ALCANZA EL PROMPT, dicho por el propio PRD (7.4): el prompt es
    guia, nunca la garantia. Ya hay tres frases ahi y no bastaron. Lo que
    puede garantizar algo es el codigo, y este es el unico momento en que se
    puede COMPROBAR que no la siguio: cuando la respuesta ya esta escrita.

    TRES CONDICIONES, Y LAS TRES HACEN FALTA:

      no puede verificar   ninguna herramienta suya declara verifica_identidad.
                           Si puede, pedir la cedula es su trabajo y no hay
                           nada que corregir.
      no derivo            si derivo, quien contesta es el area -- y el area SI
                           debe pedirla. Prohibirselo marcaria como falla el
                           comportamiento correcto (se probo, y fallaba).
      pide identidad       la frase pide el dato. Nombrar la cedula para decir
                           "en facturacion te la van a pedir" no alcanza: eso
                           queda cubierto por la condicion de arriba, porque
                           para decirlo tuvo que derivar.
    """
    cfg_rol = (getattr(config, "roles", None) or {}).get(rol)
    if cfg_rol is None:
        return False
    catalogo = {h.nombre: h for h in getattr(config, "herramientas", []) or []}
    suyas = [catalogo[n] for n in (getattr(cfg_rol, "puede_consultar", None) or [])
             if n in catalogo]
    if any(getattr(h, "verifica_identidad", False) for h in suyas):
        return False
    if not any(getattr(h, "deriva_rol", None) for h in suyas):
        # Sin a donde derivar, reencauzar solo produciria otra vuelta igual.
        return False
    derivadoras = {h.nombre for h in suyas if getattr(h, "deriva_rol", None)}
    if any((l or {}).get("herramienta") in derivadoras for l in (llamadas or [])):
        return False
    texto = _sin_tildes(respuesta or "")
    return any(p in texto for p in _PIDE_IDENTIDAD)


def decision_del_router(rol_evaluado: str, rol_final: str, sesion,
                        cfg_rol, llamadas) -> dict:
    """
    Los campos con los que queda registrado POR QUE este turno derivo, o por
    que no.

    ESTA SEPARADA PARA PODER PROBARLA, y no es un detalle de estilo: el
    corredor de casos dorados (cli/evaluar.py) llama a motor.responder()
    DIRECTO y no pasa por atender_turno, asi que nada de lo que se agregue
    alrededor del modelo lo ven los casos dorados. Una funcion pura si se
    puede probar sin base, sin modelo y sin red.

    SIN PII: numeros y nombres de rol. 'identidad' dice en que estado quedo el
    turno, nunca con que dato se llego a el -- la cedula que el cliente ofrece
    no aparece por ningun lado.
    """
    if sesion is not None and getattr(sesion, "verificado", False):
        identidad = "verificada"
    elif sesion is not None and getattr(sesion, "id_cliente_pendiente", None):
        # Localizada pero SIN confirmar: es el estado intermedio que existe
        # justo para que esta distincion se pueda auditar despues.
        identidad = "candidata"
    else:
        identidad = "sin_verificar"
    return {
        "rol": rol_evaluado,
        "identidad": identidad,
        "herramientas_disponibles": len(getattr(cfg_rol, "puede_consultar", None) or []),
        "herramientas_usadas": len(llamadas or []),
        # Vacio cuando no derivo. Se compara contra el rol EVALUADO, no contra
        # una bandera: si el turno termino en otra area, eso es la derivacion.
        "derivo_a": rol_final if rol_final != rol_evaluado else "",
    }


def atender_turno(config, tenant: str, rol: str, id_sesion: str,
                  mensaje: str, canal: str, profile_id: str | None = None,
                  nombre_colaborador: str = "",
                  evento_id: str | None = None,
                  conversacion_ya_guardada: str | None = None) -> dict:
    """
    Un turno, atendido EN ORDEN y dentro del cupo de su empresa.

    Es un envoltorio fino sobre el turno de verdad (`_atender_turno`), y esta
    separado para no reindentar quinientas lineas -- no para esconder nada.
    Todo lo que decide el turno sigue abajo; lo unico que pasa aca es esperar
    el lugar.

    POR QUE ACA Y NO EN EL WEBHOOK: por esta funcion entran los TRES caminos
    --el webhook de WhatsApp, /chat y la devolucion a la IA-- y el orden hay
    que sostenerlo en los tres. Ponerlo en el webhook dejaria a los otros dos
    sin proteccion y con la sensacion de que la tienen.

    Si no consigue lugar en `SEGUNDOS_ESPERA_TURNO` devuelve 'sin_turno' y NO
    atiende: contestar fuera de orden es lo que esto viene a impedir, y
    contestar tarde de mas es peor que no contestar -- el cliente ya escribio
    otra cosa. Queda en el log, que es donde se ve si el tope quedo corto.
    """
    clave = canales.clave_sesion(tenant, canal, id_sesion)
    maximo = getattr(config.limites, "max_turnos_simultaneos", None)
    try:
        with _turno_en_orden(tenant, clave, maximo):
            return _atender_turno(config, tenant, rol, id_sesion, mensaje, canal,
                                  profile_id, nombre_colaborador, evento_id,
                                  conversacion_ya_guardada)
    except TimeoutError as e:
        registrar("turno", "no se consiguio lugar para atender el turno",
                  tenant=tenant, canal=canal, tope=maximo, error=e)
        return {"respuesta": "", "verificado": False, "pausada": True,
                "sin_turno": True}


def _atender_turno(config, tenant: str, rol: str, id_sesion: str,
                   mensaje: str, canal: str, profile_id: str | None = None,
                   nombre_colaborador: str = "",
                   evento_id: str | None = None,
                   conversacion_ya_guardada: str | None = None) -> dict:
    """
    Un turno completo de conversacion: pausa por escalamiento, modelo,
    persistencia y evaluacion de escalamiento.

    Se extrajo de /chat sin cambiarle el comportamiento para que el webhook de
    WhatsApp (mas abajo) haga lo MISMO en vez de una copia parecida. Un canal
    con su propia version de esta logica se desincroniza: es exactamente como
    aparecio el bot que seguia contestando despues de escalar.

    'profile_id': quien pregunta, cuando /chat lo resolvio (app web). None en
    el webhook de WhatsApp -- ahi no hay un colaborador del CRM de por medio,
    solo se propaga a asistente.tool_calls.profile_id para la auditoria por
    persona (ver supabase/202608180800_tool_calls_profile_id.sql).

    'evento_id': el identificador ESTABLE del mensaje entrante, cuando el canal
    tiene uno. En WhatsApp es el wamid, y es estable porque Meta reentrega el
    mismo mensaje con el mismo id -- por eso sirve como identidad de la
    solicitud para el control de repeticion de operaciones externas (ver
    nucleo/seguridad/idempotencia.py). En /chat no existe: ahi el turno recibe
    un identificador propio y el control protege el reintento DENTRO del turno,
    no la reentrega del turno entero. Eso esta dicho tambien en la migracion,
    y no se disimula: la garantia vale lo que valga este dato.

    Devuelve {'respuesta', 'verificado', 'pausada'}. Levanta motor.ErrorMotor
    si el rol o el mensaje no son atendibles -- quien llama decide si eso es un
    400 (HTTP) o una linea de registro (webhook, donde no hay a quien
    devolverle un error).

    'conversacion_ya_guardada': el id de la conversacion cuando el mensaje
    entrante YA ESTA en la base y este turno no tiene que volver a escribirlo.
    Existe por un solo caso: devolverle la conversacion a la IA cuando el
    cliente escribio mientras la tenia una persona. Ese mensaje se guardo
    cuando llego; atenderlo ahora sin esto lo dibujaria DOS VECES en el hilo.

    Apagado por defecto, y eso es lo que importa: el webhook y /chat no pasan
    nada, asi que su camino no cambia en un solo byte. Los seis lugares donde
    el turno guarda el mensaje del cliente --uno por rama-- pasan por el mismo
    ayudante de abajo, que sin la bandera hace exactamente lo de siempre.

    'canal' se normaliza ANTES de cualquier lectura o escritura: un canal
    desconocido levanta canales.CanalInvalido sin haber tocado la base ni la
    memoria. /chat ya lo valida antes de llamar; esto cubre a cualquier otro
    llamador.
    """

    def _guardar_del_cliente(*extra, **opciones):
        """El mensaje entrante, guardado UNA SOLA VEZ.

        Devuelve (conversation_id, message_id), igual que registrar_mensaje:
        dos ramas usan el primero para cerrar el caso y el camino normal usa
        el segundo para colgarle el adjunto a la burbuja correcta.

        Con 'conversacion_ya_guardada' no escribe nada y devuelve ese id con
        message_id en None -- no hay burbuja nueva a la que colgarle nada,
        porque el mensaje ya estaba.
        """
        if conversacion_ya_guardada:
            return conversacion_ya_guardada, None
        return persistencia.registrar_mensaje(
            tenant, canal, id_sesion, rol, "user", mensaje, *extra,
            origen="cliente", **opciones)

    clave = canales.clave_sesion(tenant, canal, id_sesion)
    canal = clave[1]
    # Antes de nada: si la conversacion anterior de esta persona quedo abierta
    # pero ya paso el plazo de inactividad, se la resume y se la cierra. Asi el
    # turno que sigue empieza limpio en vez de pegarse a un hilo de dias --
    # medido el 18/08/2026, uno llego a 67 mensajes y 180 horas mezclando tres
    # problemas, y el modelo terminaba repitiendo preguntas ya contestadas y
    # citando mediciones de cuatro horas antes como si fueran de ahora.
    # La hora en que ESTE mensaje llego. Se toma antes de todo -- del cierre
    # por inactividad, del modelo, de las herramientas-- porque es lo unico
    # que despues permite saber cuanto espero el cliente. Ver el comentario en
    # persistencia.registrar_mensaje: sin esto los dos mensajes del turno
    # quedaban sellados al terminar, y la base decia 0.1s de espera SIEMPRE.
    llego_en = datetime.now(timezone.utc)

    horas = config.limites.horas_inactividad_cierra
    if horas:
        try:
            vencida = persistencia.conversacion_vencida(tenant, canal, id_sesion, horas)
            if vencida:
                texto = (vencida["resumen_previo"]
                        or resumen.redactar(config, vencida["historial"]) or "")
                persistencia.guardar_resumen(tenant, vencida["conversation_id"], texto)
                # La sesion en memoria tambien se descarta: si no, el turno
                # nuevo arrancaria con el historial viejo igual y el cierre no
                # habria servido de nada.
                _sesiones.pop(clave, None)
                registrar("conversacion", "cerrada por inactividad y resumida",
                          conversation_id=str(vencida["conversation_id"]),
                          horas=horas, caracteres_resumen=len(texto))
        except Exception as e:
            registrar("conversacion", "no se pudo cerrar por inactividad", error=e)

    nueva = clave not in _sesiones
    if nueva:
        _sesiones[clave] = _sesion_nueva(tenant, id_sesion, canal, horas)
    estado = _sesiones[clave]
    # Quien esta escribiendo, para poder firmar a su nombre lo que se escriba
    # en un sistema externo. Se refresca en CADA turno y no solo al abrir la
    # conversacion: la misma sesion puede retomarla otra persona del equipo, y
    # firmar con el nombre de quien la abrio seria atribuirle algo que no
    # escribio.
    if nombre_colaborador:
        estado["sesion"].nombre_colaborador = nombre_colaborador

    # Poner al modelo en contexto cuando este proceso no tiene memoria de esta
    # persona -- porque es la primera vez, o porque el motor se reinicio.
    #
    # SON DOS COSAS DISTINTAS Y VAN EN ESTE ORDEN:
    #
    #   1. el resumen de la conversacion ANTERIOR, ya cerrada (si la hubo)
    #   2. los ultimos mensajes de la conversacion EN CURSO, si sigue abierta
    #
    # Primero lo viejo, despues lo reciente: es el orden en que ocurrio, y es
    # el que evita que el modelo confunda una cosa con la otra. Justamente eso
    # paso el 07/09/2026 -- sin el paso 2, el unico contexto era el resumen de
    # hacia seis horas, y el asistente contesto sobre esa falla en vez de la
    # conversacion de television que tenia nueve minutos.
    if nueva and not estado["historial"]:
        anterior = persistencia.resumen_anterior(tenant, canal, id_sesion)
        if anterior:
            texto_previo, horas_previo = anterior
            estado["historial"].append(
                resumen.como_contexto(texto_previo, horas_previo))

        # El hilo en curso. Solo si hay una conversacion abierta: si no la
        # hay, no hay nada que retomar y el resumen de arriba es todo el
        # contexto que corresponde.
        if estado.get("conversacion_id"):
            retomado = persistencia.historial_para_el_modelo(
                tenant, estado["conversacion_id"], MENSAJES_A_REHIDRATAR)
            if retomado:
                estado["historial"].extend(retomado)
                registrar("sesion", "se retomo el historial: el proceso no lo tenia en memoria",
                          conversation_id=str(estado["conversacion_id"]),
                          mensajes=len(retomado))

    # --- si la conversacion ya se derivo a otra area, seguir ahi -------------
    # Solo aplica cuando el rol que pide el LLAMADOR ya es cliente_final (para
    # WhatsApp, siempre lo mismo hoy): nunca se pisa un rol interno/colaborador
    # con uno derivado. 'rol_activo' se revalida contra la config actual, no
    # se confia ciegamente en lo que quedo grabado -- un rol pudo borrarse o
    # cambiar de 'orientado_a' desde la ultima vez.
    nota_continuidad = None
    rol_pedido = config.roles.get(rol)
    if (rol_pedido is not None and rol_pedido.orientado_a == "cliente_final"
            and estado.get("rol_activo")):
        rol_activo_cfg = config.roles.get(estado["rol_activo"])
        if rol_activo_cfg is not None and rol_activo_cfg.orientado_a == "cliente_final":
            # Si ademas el historial en memoria esta vacio (se perdio en un
            # reinicio -- ver _sesion_nueva(), no rehidrata mensajes), el
            # especialista arranca sin ningun rastro de por que esta
            # atendiendo. Confirmado en vivo (agosto 2026): sin avisarlo,
            # el modelo podia derivar de nuevo a otra area sin motivo real,
            # solo por no saber que ya estaba en la correcta.
            if rol != estado["rol_activo"] and not estado["historial"]:
                nota_continuidad = (
                    "(Nota del sistema, no del cliente) Esta conversacion ya "
                    "fue derivada a tu area en un mensaje anterior que no "
                    "esta disponible en este historial (se perdio por un "
                    "reinicio del sistema, no por el cliente). Atende el "
                    "mensaje que sigue con naturalidad, sin pedirle que "
                    "repita lo que ya conto si no hace falta. NO vuelvas a "
                    "derivar a otra area salvo que el mensaje ACTUAL sea "
                    "claramente de un tema distinto al tuyo.")
            rol = estado["rol_activo"]

    # Desde aca, todo lo que se agregue al historial es de ESTE turno. Lo usa
    # _sincronizar_respuesta_en_memoria() al final para no tocar turnos previos.
    inicio_turno = len(estado["historial"])
    # Si ESTE turno reservo el control humano (escalada). Lo lee el candado del
    # traspaso al final: con la reserva hecha, prometer una persona es cierto.
    reservado_turno = False

    # --- repregunta pendiente del verificador de agendamiento -----------------
    # nucleo/seguimiento/agendamiento.py dejo esto en un turno anterior porque
    # el checklist del manual quedo con UN dato puntual sin confirmar. Se
    # inyecta como nota de sistema para este turno (no via 'nota_continuidad':
    # esta conversacion sigue con su historial intacto, no es el caso de
    # amnesia por reinicio) y se consume una sola vez.
    if estado.get("nota_pendiente"):
        estado["historial"].append({"role": "system", "content": estado["nota_pendiente"]})
        estado["nota_pendiente"] = None

    # --- ¿quedo algo sin comprobar del turno anterior? ----------------------
    # Va antes de TODO lo que puede cortar el turno, incluida la pausa por
    # escalada. Si esperara a la parte donde habla el modelo, una conversacion
    # que paso a una persona no resolveria nunca su comprobacion pendiente --
    # y como esa pendiente traba el cierre, el caso quedaria atascado hasta el
    # barrido por inactividad.
    veredicto_accion = _resolver_verificacion_pendiente(config, tenant, estado)

    # --- QUIEN CONTROLA LA CONVERSACION: LO DICE LA BASE ---------------------
    # B3.3b. Antes lo decidia estado["escalada"], la memoria del proceso: una
    # devolucion, una intervencion o un reinicio en otro lado no se enteraban.
    # Ahora se lee en cada turno con control_efectivo() (nucleo/relevo/control.py),
    # la misma regla que las guardas: legado -> las banderas de siempre;
    # gobernada -> la columna control. La memoria solo refleja lo leido.
    #
    # Si la base no responde, FALLA CERRADO: sin saber quien controla, no se
    # corre el modelo. Un silencio es un problema; que la IA le conteste a un
    # cliente que una persona esta atendiendo es otro peor.
    try:
        control_actual = persistencia.control_de_conversacion_abierta(tenant, canal, id_sesion)
    except Exception as e:
        _contar_relevo("control_no_determinado",
                       conversation_id=id_interno(estado.get("conversacion_id")),
                       punto="antes_del_modelo_no_se_corre", error=e)
        return {"respuesta": "", "verificado": estado["sesion"].verificado,
                "pausada": True, "control_desconocido": True}
    # Lo que autoriza ESTE turno (D24). Se vuelve a comprobar al salir del
    # modelo y antes de enviar.
    estado["autorizacion_turno"] = _autorizacion_de(control_actual)
    estado["escalada_del_turno"] = None
    if control_actual is None:
        estado["escalada"] = False
    else:
        estado["escalada"] = control_actual["control_efectivo"] == "humano"
        if estado["escalada"] and control_actual["control_motivo"] == "intervencion":
            # Una persona tomo la conversacion por su cuenta. La IA no corre y
            # NO se usa nada de la escalada: ni el acuse "ya te estamos
            # atendiendo", ni el cierre por confirmacion, ni el CRM. Quien
            # intervino esta ahi; el mensaje queda guardado para que lo lea.
            estado["historial"].append({"role": "user", "content": mensaje})
            try:
                _guardar_del_cliente()
            except Exception as e:
                registrar("persistencia", "no se pudo guardar el mensaje durante la intervencion",
                          error=e)
            return {"respuesta": "", "verificado": estado["sesion"].verificado, "pausada": True}

    # --- si ya se escalo, el bot NO contesta ---------------------------------
    # Va antes de motor.responder() a proposito. Marcar la conversacion como
    # escalada y despues dejar que el modelo siga respondiendo deja al cliente
    # hablando con un bot justo despues de que se le dijo que lo iba a atender
    # una persona. Se verifica contra el CRM en vez de confiar en la marca:
    # cuando el humano cierra el caso, el asistente retoma solo.
    if estado["escalada"]:
        seguir_en_pausa = escalamiento.caso_sigue_abierto(config, estado["caso_id"])
        if not seguir_en_pausa and estado.get("conversacion_id"):
            # Caso cerrado en el CRM. En una conversacion que ya esta en el
            # modelo nuevo (relevo_version > 0) eso NO la devuelve a la IA:
            # queda un aviso para la persona y la pausa sigue, porque el unico
            # camino de vuelta es devolver_a_ia(). En el legado (version 0)
            # se retoma como siempre, hasta la reconciliacion de G8.
            try:
                if transiciones.caso_externo_cerrado(tenant, estado["conversacion_id"]).gobernada:
                    seguir_en_pausa = True
            except Exception as e:
                registrar("relevo", "no se pudo registrar el cierre externo del caso", error=e)
        if seguir_en_pausa:
            estado["historial"].append({"role": "user", "content": mensaje})
            # ¿El cliente esta diciendo que ya quedo?
            #
            # El bot no contesta mientras hay una persona atendiendo, pero
            # SIGUE leyendo: el "listo, gracias" con el que de verdad termina
            # un caso llega justo aca, y sin esto no tenia ningun efecto -- al
            # cliente le volvia "tu caso ya esta con un compañero", y el caso,
            # el ticket y el chat quedaban abiertos esperando que alguien se
            # acordara de cerrarlos a mano.
            #
            # Y "resuelta" NO alcanza por si sola. El evaluador la pone en true
            # tambien cuando el cliente se despide -- asi esta escrito, y para
            # el flujo normal esta bien: ahi el asistente ya resolvio y el
            # "gracias" cierra. Aca no: el trabajo lo tiene una persona y
            # todavia no lo hizo.
            #
            # Paso el 28/08/2026. El cliente contesto "ok" al aviso del PROPIO
            # asistente ("tu pedido quedo registrado") y se cerro todo -- chat,
            # caso y ticket -- con el cambio de clave sin aplicar y sin que
            # ninguna persona hubiera escrito nunca. Un "ok" a nadie no
            # confirma nada.
            #
            # Asi que se exige el hecho: que alguien del equipo le haya
            # respondido. Recien ahi un "ok" significa "si, ya quedo".
            #
            # Y ESE HECHO SE MIRA PRIMERO, antes de gastar la llamada.
            #
            # El cierre exige las dos cosas -- que el cliente lo confirme Y
            # que una persona le haya escrito-- asi que sin lo segundo el
            # veredicto del modelo no puede cerrar nada por definicion. Se
            # estaba pagando una llamada por cada mensaje de un cliente que
            # espera, para descartar el resultado dos lineas mas abajo.
            # Reordenarlo no cambia nada de lo que ve el cliente: las dos
            # ramas de salida son las mismas y en el mismo orden.
            hubo_humano = persistencia.atendida_por_humano(
                tenant, estado["conversacion_id"])
            cerrado = False
            veredicto = {}
            if hubo_humano:
                try:
                    # Este camino no pasa por motor.responder --el bot esta en
                    # pausa, no compone nada-- asi que abre su PROPIO
                    # acumulador en vez de seguir uno que todavia no existe.
                    # Pero cuenta igual: es una llamada al modelo, y hasta hoy
                    # tampoco se contaba.
                    with consumo.abrir(config):
                        veredicto = escalamiento.evaluar(config, rol, estado["historial"]) or {}
                    # Un "si" explicito cierra por si solo, aunque la pregunta
                    # se le haya hecho dos turnos antes: el cliente contesto lo
                    # que se le pregunto, y volver a preguntarle lo mismo es no
                    # escucharlo. Visto en la prueba: dijo "listo entonces, ya
                    # puedes cerrar" y se le repregunto.
                    cerrado = bool(veredicto.get("resuelta")
                                   or veredicto.get("confirma_cierre"))
                except Exception as e:
                    registrar("escalamiento", "no se pudo evaluar el turno pausado", error=e)
            if cerrado and _hay_verificacion_pendiente(tenant, estado["conversacion_id"]):
                registrar("verificacion", "el cliente da por cerrado, pero hay una accion "
                                          "sin comprobar -- no se cierra",
                          conversation_id=str(estado["conversacion_id"]))
                cerrado = False
            # Y aunque haya respondido una persona: primero se le PREGUNTA.
            # Cerrar con lo que el modelo dedujo de un "ok" ya salio mal una
            # vez; con una pregunta explicita, lo que cierra el caso es la
            # respuesta del cliente y no una interpretacion.
            # Ya se le pregunto: cierra solo si CONTESTO que si. Con
            # 'resuelta' a secas alcanzaba con que la conversacion volviera a
            # parecer terminada, y una pregunta nueva del cliente la cerraba.
            if (estado["cierre_propuesto"] and _pregunta_de_cierre(config)
                    and not veredicto.get("confirma_cierre")):
                cerrado = False
                estado["cierre_propuesto"] = False
            elif (cerrado and _pregunta_de_cierre(config)
                    and not veredicto.get("confirma_cierre")):
                estado["cierre_propuesto"] = True
                cerrado = False
                respuesta = _pregunta_de_cierre(config)
                estado["historial"].append({"role": "assistant", "content": respuesta})
                try:
                    _guardar_del_cliente()
                    persistencia.registrar_mensaje(tenant, canal, id_sesion, rol, "assistant", respuesta,
                                                   origen="sistema")
                except Exception as e:
                    registrar("persistencia", "no se pudo guardar la pregunta de cierre", error=e)
                return {"respuesta": respuesta,
                        "verificado": estado["sesion"].verificado,
                        "pausada": True}
            if not cerrado:
                # Dijo que le falta algo: la proxima vez se le vuelve a
                # preguntar en vez de darlo por cerrado de una.
                estado["cierre_propuesto"] = False

            # D25: el evaluador tardo; si mientras tanto alguien movio el relevo
            # (tomo, solto, intervino), el cierre automatico no empieza. Control
            # humano es lo esperado aca, asi que se compara solo la version.
            if cerrado and not _efecto_del_turno(tenant, canal, id_sesion, estado,
                                                 "cierre_confirmado_en_pausa",
                                                 clase=autorizacion_relevo.AUTOMATICO_EN_PAUSA):
                cerrado = False

            if cerrado:
                respuesta = _mensaje_de_cierre(config)
                try:
                    conv, _ = _guardar_del_cliente()
                    persistencia.registrar_mensaje(
                        tenant, canal, id_sesion, rol, "assistant", respuesta, origen="sistema")
                    hecho = operativo.cerrar_todo(
                        config, tenant,
                        {"id": conv, "caso_id": estado["caso_id"],
                         "ticket_operativo": persistencia.ticket_operativo_de(tenant, conv)},
                        (config.escalamiento.texto_cierre_confirmado or "").strip()
                        or "El cliente confirmo que su caso quedo resuelto.")
                    # La memoria solo se limpia si la base cerro de verdad. Si
                    # la transicion se nego --queda una accion viva o una
                    # verificacion sin resolver-- dejar aca 'escalada = False'
                    # haria justo lo que D9/D10 costaron: que la memoria diga
                    # una cosa y la base otra.
                    if hecho["conversacion"]:
                        estado["escalada"] = False
                        estado["caso_id"] = None
                except Exception as e:
                    registrar("operativo", "no se pudo cerrar tras la confirmacion del cliente", error=e)
                estado["historial"].append({"role": "assistant", "content": respuesta})
                return {"respuesta": respuesta,
                        "verificado": estado["sesion"].verificado,
                        "cerrada": True, "pausada": True}

            # Si YA hay una persona escribiendole, el bot se calla.
            #
            # Repetirle "un compañero lo va a aplicar" a alguien que acaba de
            # leer "ya se realizo su cambio" no es redundante: lo contradice,
            # y el cliente no sabe a cual creerle. Su mensaje queda guardado y
            # la persona lo ve en la bandeja, que es donde esta mirando.
            if hubo_humano:
                try:
                    _guardar_del_cliente()
                except Exception as e:
                    registrar("persistencia", "no se pudo guardar el mensaje del cliente", error=e)
                return {"respuesta": "", "verificado": estado["sesion"].verificado,
                        "pausada": True}

            # EL ANUNCIO NO SE REPITE.
            #
            # Aca el cliente ya fue escalado y vuelve a escribir. Antes se le
            # devolvia el mensaje del motivo -- el mismo "te paso con un
            # compañero" que ya habia leido-- y sonaba a que el pase nunca
            # habia ocurrido. Medido el 08/09/2026: escalada 19:56:30, el
            # cliente contesta "ok" a las 19:56:57 y recibe el anuncio
            # identico, palabra por palabra.
            #
            # Lo que corresponde en este turno es el ESTADO ("ya esta con
            # alguien"), no el anuncio. Configurable por tenant, con un texto
            # interno de respaldo para que nunca quede mudo.
            respuesta = (config.escalamiento.mensaje_ya_escalada or "").strip() or \
                "Tu caso ya esta con un compañero del equipo, que lo va a " \
                "revisar y te escribe por aca."
            estado["historial"].append({"role": "assistant", "content": respuesta})
            try:
                _guardar_del_cliente()
                persistencia.registrar_mensaje(tenant, canal, id_sesion, rol, "assistant", respuesta,
                                               origen="sistema")
            except Exception as e:
                registrar("persistencia", "no se pudo guardar el turno pausado", error=e)
            return {"respuesta": respuesta,
                    "verificado": estado["sesion"].verificado,
                    "pausada": True}
        # El caso se cerro y la conversacion es de legado: el asistente
        # vuelve a atender desde este turno, como hasta hoy.
        estado["escalada"] = False
        estado["caso_id"] = None
        # Y vuelve a poder escalar: el caso anterior ya no esta abierto, asi
        # que un caso nuevo no seria un duplicado sino uno legitimo.
        estado["ya_escalada"] = False
        # Este turno decidio retomar un legado cuyas banderas siguen en la
        # base: al volver del modelo no se exige control 'ia' (seguiria
        # diciendo humano), solo que nadie haya movido la version (D24).
        estado["autorizacion_turno"]["legado_retomado"] = True

    # El resultado ya calculado entra al contexto del modelo ANTES de que
    # redacte: si llegara despues, le contestaria al cliente sin saber si el
    # equipo volvio. Le llega un ESTADO, no dos mediciones para que opine.
    if veredicto_accion:
        estado["historial"].append(
            {"role": "system", "content": veredicto_accion["nota"]})

    # --- tope de gasto de la empresa ----------------------------------------
    # Va aca y no despues: si esperara al final, el turno que descubre el tope
    # ya lo gasto. El control tiene que correr ANTES de la primera llamada al
    # modelo o cuenta un turno tarde, siempre.
    #
    # 'frenar' NO deja al cliente sin respuesta. El tope existe para que no se
    # dispare la factura, no para que alguien con el internet caido se quede
    # hablando solo: se le contesta, se marca la conversacion para que una
    # persona la tome, y no se le pide nada al modelo.
    #
    # Se marca 'necesita_atencion_humana' pero NO 'escalada_a_humano': lo
    # segundo afirma un traspaso con caso y ticket, y aca no hubo ninguno --
    # mismo criterio que NO_DETERMINADO en _cerrar_escalada(). Prometer un
    # traspaso que no ocurrio es peor que no prometerlo.
    gasto = consumo.estado_del_gasto(config, tenant)
    if gasto["accion"] == "avisar":
        registrar("consumo", "gasto del mes cerca del tope", tenant=tenant,
                  gastado_usd=gasto["gastado"], tope_usd=gasto["tope"],
                  porcentaje=round(gasto["porcentaje"] * 100))
    elif gasto["accion"] == "frenar":
        registrar("consumo", "TOPE ALCANZADO: el turno pasa a una persona sin llamar al modelo",
                  tenant=tenant, gastado_usd=gasto["gastado"], tope_usd=gasto["tope"])
        respuesta = (config.limites.mensaje_al_alcanzar_tope or "").strip() or (
            "En este momento no puedo atender por este medio. Un compañero "
            "del equipo va a continuar con esta conversacion.")
        estado["historial"].append({"role": "user", "content": mensaje})
        estado["historial"].append({"role": "assistant", "content": respuesta})
        try:
            conv_id, _ = _guardar_del_cliente()
            persistencia.registrar_mensaje(
                tenant, canal, id_sesion, rol, "assistant", respuesta, origen="sistema")
            if conv_id:
                persistencia.registrar_estado_escalada(
                    tenant, conv_id, estado_escalada.NO_DETERMINADO,
                    "tope de gasto del mes alcanzado", necesita_atencion=True)
        except Exception as e:
            # Igual se le contesta: quedarse callado ademas de sin servicio
            # seria el peor de los dos mundos.
            registrar("consumo", "no se pudo registrar el turno frenado", error=e)
        return {"respuesta": respuesta,
                "verificado": bool(getattr(estado["sesion"], "verificado", False)),
                "pausada": True}

    # El unico lugar que abre el contador de consumo: este es el turno que se
    # atiende de verdad. Los corredores de casos dorados y los bancos de
    # prueba llaman al mismo motor y no lo abren, asi que sus miles de
    # llamadas al modelo no entran en la facturacion de nadie ni disparan el
    # tope de gasto -- ver nucleo/observabilidad/consumo.py.
    # El mensaje de esta respuesta, para poder completarle la medicion al
    # final del turno (ver el cierre de esta funcion). Se declara aca y no
    # dentro del try de persistencia porque ese try se traga sus fallos: si no
    # se pudo guardar, esto queda en None y no se intenta actualizar nada.
    mensaje_id_turno = None

    # La ficha del turno se conserva despues del 'with': trae los tokens y el
    # costo de ESTE turno, y hasta ahora se volcaban solo al agregado diario
    # (asistente.usage_daily). Con el agregado se puede decir cuanto cuesta
    # una llamada en promedio, pero no CUAL turno salio caro ni por que --
    # que es justo lo que hace falta para bajar de los 4-11 segundos que
    # tarda el modelo. Las columnas por mensaje existian y estaban vacias.
    antes_del_modelo = len(estado["historial"])
    # D25: mientras el modelo corre, cada herramienta que escribe le pregunta a
    # este autorizador justo antes de empezar.
    with consumo.abrir(config) as ficha_consumo, autorizacion_relevo.autorizando(
            lambda que: _efecto_del_turno(tenant, canal, id_sesion, estado, que)):
        # Con que rol se EVALUO este turno. Se guarda antes de la derivacion,
        # que mas abajo pisa 'rol' con el area nueva: sin esto, el registro de
        # la decision diria que fue facturacion quien decidio derivar a
        # facturacion.
        rol_evaluado = rol
        # El origen se calcula UNA vez y se guarda: si se reencauza, la
        # segunda vuelta lo reusa con un sufijo. Generarlo de nuevo daria un
        # uuid distinto, y las dos vueltas del mismo turno quedarian sin
        # forma de juntarse al revisar la traza.
        origen_del_turno = (f"evento:{evento_id}" if evento_id
                            else f"turno:{uuid.uuid4()}")
        respuesta, registro_herramientas, medios_pendientes = motor.responder(
            config, rol, mensaje, estado["historial"], estado["sesion"],
            nota_continuidad=nota_continuidad,
            origen=origen_del_turno)

        # ── REENCAUZAR: PIDIO IDENTIDAD SIN PODER VERIFICARLA ───────────────
        #
        # Una sola vez, y en la capa donde sirve. La leccion del 09/09/2026 es
        # que un reintento solo sirve donde puede entrar informacion nueva: la
        # redaccion final corre sin catalogo, asi que pedirle tres veces que
        # reescriba devuelve tres veces la misma frase. Aca se vuelve a entrar
        # al BUCLE DEL AGENTE, que es donde todavia puede llamar
        # derivar_a_area -- y llamarla es justamente lo que le falto.
        #
        # UNA, nunca en bucle: si la segunda tampoco deriva, se manda lo que
        # haya. Una guarda que puede dar vueltas es peor que el problema que
        # arregla, y el cliente esperando no tiene la culpa.
        if debe_reencauzar_a_derivacion(config, rol, respuesta, registro_herramientas):
            registrar("router", "pidio identidad sin poder verificar: se reencauza",
                      rol=rol, herramientas_usadas=len(registro_herramientas or []))
            # La respuesta descartada sale de la memoria: si se queda, el
            # modelo la ve como algo que ya dijo y la sostiene -- que es
            # exactamente como esta conversacion se quedo ocho horas pidiendo
            # lo mismo.
            _quitar_respuesta_de_memoria(estado["historial"], antes_del_modelo)
            # EL AVISO VA AL HISTORIAL, NO POR 'nota_continuidad'.
            #
            # Ese parametro se inyecta UNICAMENTE dentro de 'if not historial'
            # (nucleo/modelo/motor.py): existe para la amnesia por reinicio, y
            # el comentario de mas arriba en este mismo archivo ya lo decia.
            # Con historial --o sea, siempre que haya un turno previo, que es
            # el caso que motivo esta guarda-- la nota se descartaba en
            # silencio y el reintento corria con el MISMO payload que la
            # primera vuelta. Eso convertia la guarda en un turno de modelo
            # regalado: la leccion del 09/09/2026 al reves.
            posicion_aviso = len(estado["historial"])
            estado["historial"].append({"role": "system",
                                        "content": INSTRUCCION_REENCAUZAR})
            respuesta, registro_herramientas, medios_pendientes = motor.responder(
                config, rol, mensaje, estado["historial"], estado["sesion"],
                origen=f"{origen_del_turno}:reencauzado")
            # Era para ESTA vuelta. Si se queda, los turnos siguientes leen
            # "en tu respuesta anterior le pediste un dato de identidad"
            # cuando ya no es cierto.
            if (posicion_aviso < len(estado["historial"])
                    and estado["historial"][posicion_aviso].get("content")
                    == INSTRUCCION_REENCAUZAR):
                estado["historial"].pop(posicion_aviso)
            # 'derivo' se mide por la herramienta que corrio EN ESTE TURNO.
            # Ni por 'sesion.rol_siguiente' --el motor lo deja puesto entre
            # turnos a proposito (motor.py, "NO se limpia aca"), asi que una
            # derivacion vieja diria que si-- ni por la ausencia del sintoma:
            # una respuesta que deja de nombrar la cedula sin derivar tampoco
            # resolvio nada, y contarla como exito arruina la unica medicion
            # que puede decir si esta guarda sirve.
            registrar("router", "resultado del reencauzamiento",
                      rol=rol, herramientas_usadas=len(registro_herramientas or []),
                      derivo=_derivo_en_este_turno(config, rol,
                                                   registro_herramientas))

    # --- D24, punto 1: el control no cambio mientras el modelo pensaba ------
    # Si cambio (una persona intervino, se cerro, otra version), la respuesta
    # se DESCARTA: no se guarda como dicha, no entra a la memoria y no se
    # envia. El consumo del modelo ya ocurrio y queda medido; el texto no se
    # registra en ningun lado. El mensaje del cliente si se guarda: lo escribio
    # y quien tomo la conversacion tiene que leerlo.
    if not _turno_sigue_autorizado(
            tenant, canal, id_sesion, estado["autorizacion_turno"],
            exigir_ia=not estado["autorizacion_turno"].get("legado_retomado")):
        _quitar_respuesta_de_memoria(estado["historial"], antes_del_modelo)
        estado["historial"].append({"role": "user", "content": mensaje})
        if estado["sesion"] is not None:
            estado["sesion"].rol_siguiente = None
        _contar_relevo("respuesta_ia_descartada_por_cambio_de_control",
                       conversation_id=id_interno(estado["autorizacion_turno"].get("conversation_id")),
                       version=estado["autorizacion_turno"].get("relevo_version"),
                       punto="al_volver_del_modelo")
        try:
            _guardar_del_cliente(horas, creado_en=llego_en)
        except Exception as e:
            registrar("persistencia", "no se pudo guardar el mensaje del turno descartado",
                      error=e)
        return {"respuesta": "", "verificado": estado["sesion"].verificado,
                "pausada": True, "descartada": True}

    # --- si este turno derivo a otra area, persistir YA con el rol nuevo -----
    # 'rol_siguiente' lo pone motor._ejecutar_derivacion() cuando el modelo
    # llamo una herramienta 'deriva_rol' este mismo turno. Se consume ahora:
    # el mensaje del asistente en ESTE turno (el aviso breve de "te paso con
    # el area X") ya queda grabado con 'rol_efectivo' = el area nueva, que es
    # lo que _rol_de_cliente()/el bloque de arriba leen para el PROXIMO
    # mensaje de este mismo cliente.
    if estado["sesion"] is not None and estado["sesion"].rol_siguiente:
        rol = estado["sesion"].rol_siguiente
        estado["rol_activo"] = rol
        estado["sesion"].rol_siguiente = None

    # ── POR QUE ESTE TURNO DERIVO, O POR QUE NO ──────────────────────────────
    #
    # Nace de un caso del 22/09/2026 que costo dos horas reconstruir: el router
    # le pidio la cedula a un cliente en vez de derivar, y con lo que quedaba
    # guardado no habia forma de saber POR QUE. La traza tenia lo que se
    # ejecuto --nada-- y el hilo tenia lo que respondio. Faltaba el medio: con
    # que rol se evaluo, si habia identidad, cuantas herramientas tenia a mano
    # y que eligio.
    #
    # Doce corridas contra el motor real no lo reprodujeron. Cuando algo pasa
    # una vez y no se repite, lo unico que queda es que la PROXIMA vez haya
    # dejado rastro.
    #
    # SIN PII, y por eso son numeros y nombres de rol, nunca texto del cliente
    # ni el dato de identidad que ofrecio. 'identidad' dice en que estado
    # quedo, no con que se llego a el.
    try:
        registrar("router", "decision del turno",
                  **decision_del_router(rol_evaluado, rol, estado["sesion"],
                                        config.roles.get(rol_evaluado),
                                        registro_herramientas))
    except Exception:
        # Observabilidad, no funcionalidad: si esto falla, el turno sigue.
        pass

    conversation_id = None
    mensaje_id = None
    mensaje_usuario_id = None
    try:
        # El id del turno del CLIENTE se conserva: es a esa burbuja a la que
        # hay que colgarle la foto que mando, para que aparezca en el hilo
        # donde la mando y no en una lista aparte al final.
        _, mensaje_usuario_id = _guardar_del_cliente(horas, creado_en=llego_en)
        # 'latencia_ms' es lo que el cliente ESPERO: desde que su mensaje
        # llego hasta que la respuesta estuvo lista. La columna existia y
        # nadie la llenaba -- por eso no habia con que responder "¿cuanto
        # tarda?" salvo adivinando.
        conversation_id, mensaje_id = persistencia.registrar_mensaje(
            tenant, canal, id_sesion, rol, "assistant", respuesta, horas,
            # 'ia' aunque una guarda del codigo reescriba despues el texto
            # (actualizar_contenido_mensaje): sigue siendo el turno del
            # asistente, del lado maquina. 'sistema' queda para los textos
            # fijos que salen sin turno del modelo.
            origen="ia",
            latencia_ms=int(
                (datetime.now(timezone.utc) - llego_en).total_seconds() * 1000),
            # De ESTE turno, no del dia. 'n_llamadas' es cuantas veces se
            # hablo con el modelo para producir una sola respuesta: es la otra
            # palanca sobre la latencia, junto con el tamaño del prompt, y no
            # se veia en ningun lado.
            tokens_entrada=ficha_consumo.tokens_entrada,
            tokens_salida=ficha_consumo.tokens_salida,
            costo_usd=ficha_consumo.costo_usd,
            llamadas_modelo=ficha_consumo.n_llamadas,
            modelo=config.llm.modelo_por_defecto)
        mensaje_id_turno = mensaje_id
        if estado["autorizacion_turno"].get("conversation_id") is None and conversation_id:
            estado["autorizacion_turno"]["conversation_id"] = str(conversation_id)
        # La sesion viva se queda con el id. Solo lo tenia cuando venia de una
        # conversacion ANTERIOR: si la creo este mismo proceso, quedaba en
        # None y las reglas que preguntan por esta fila --si ya la atendio una
        # persona, sobre todo-- respondian que no sin poder mirar.
        estado["conversacion_id"] = conversation_id
        # LA TRAZA VA EN UN HILO, Y FUERA DEL CAMINO CRITICO.
        #
        # Eran N inserciones --una por herramienta-- y cada una es una ida a
        # Postgres. Medido contra produccion: 1.054 ms de mediana por viaje.
        # Un diagnostico llama a cinco herramientas, asi que la traza costaba
        # casi seis segundos, y se pagaban ANTES de mandarle la respuesta al
        # cliente, que ya estaba escrita hacia rato.
        #
        # Dos cambios, no uno: ahora es UNA insercion para todas las filas
        # (registrar_llamadas_herramienta), y ademas corre en un hilo aparte.
        #
        # POR QUE SE PUEDE. Nadie lee esta traza durante el turno: es
        # auditoria, la mira una persona despues, en "Ver proceso". Lo que SI
        # tiene que estar guardado antes de responder son los mensajes, y esos
        # siguen siendo sincronos.
        #
        # LO QUE SE ACEPTA A CAMBIO. Si el proceso muere en ese segundo, se
        # pierde la traza de un turno. Se pierde la auditoria de una
        # conversacion, no la conversacion. Al reves --hacer esperar al
        # cliente seis segundos para que la auditoria este a salvo-- es
        # cobrarle al cliente el costo de nuestro registro.
        def _guardar_traza(cid=conversation_id, llamadas=list(registro_herramientas)):
            try:
                persistencia.registrar_llamadas_herramienta(
                    tenant, cid, rol, llamadas, profile_id=profile_id)
                # Fase 1 del ciclo de identidad (23/09/2026): el embudo del
                # turno va en la misma ida de auditoria, despues de responder,
                # y con la misma regla -- perderlo no tumba la atencion.
                eventos = eventos_identidad_de(llamadas)
                if eventos:
                    persistencia.registrar_eventos_identidad(tenant, cid, rol, eventos)
                for llamada in llamadas:
                    # La accion quedo hecha pero sin comprobar: se anota para
                    # medirla en un turno siguiente, cuando pase el plazo.
                    if llamada.get("verificacion_pendiente"):
                        persistencia.guardar_verificacion_pendiente(
                            tenant, cid, llamada["herramienta"],
                            llamada["verificacion_pendiente"])
            except Exception as e:
                registrar("traza", "no se pudo guardar", error=e)

        if registro_herramientas:
            threading.Thread(target=_guardar_traza, daemon=True).start()
        # Mismo motivo que el bucle de arriba: un archivo generado por una
        # herramienta 'agregado' exportable (ver nucleo/herramientas/
        # informes.py) no se pudo guardar dentro de motor.responder() porque
        # todavia no existia conversation_id. El 'media_id' que el modelo ya
        # vio en su turno (crudo['archivo_id']) es el MISMO que se inserta
        # aca -- no hace falta avisarle nada nuevo, solo completar el guardado.
        for medio in medios_pendientes:
            try:
                persistencia.guardar_media(
                    tenant, conversation_id, medio["media_id"], medio["tipo"],
                    medio["contenido"], mime=medio.get("mime"),
                    descripcion=medio.get("descripcion"), mensaje_id=mensaje_id)
            except Exception as e:
                registrar("informes", "no se pudo guardar el archivo generado", error=e)
        # Las marcas de televisor que se nombraron y no tienen guia propia.
        #
        # Mismo motivo que el bucle de arriba: cuando la herramienta resolvio
        # la guia todavia no existia 'conversation_id', y sin el la marca es un
        # nombre suelto -- quien la revise no puede leer que le pasaba a ese
        # cliente ni si la guia general le sirvio.
        #
        # Se drena la lista para que una conversacion larga no vuelva a anotar
        # lo mismo en cada turno. La deduplicacion de verdad la hace el indice
        # unico de la tabla; esto solo evita el viaje.
        if estado["sesion"] is not None and estado["sesion"].marcas_tv_sin_guia:
            for marca in estado["sesion"].marcas_tv_sin_guia:
                persistencia.registrar_marca_tv_desconocida(
                    tenant, conversation_id, marca)
            estado["sesion"].marcas_tv_sin_guia = []
        # Las acciones que el turno dejo propuestas: recien aca existe el
        # conversation_id con el que ligarlas (B5). Hasta este punto no se
        # pueden aprobar --sin conversacion son indistinguibles del legado, que
        # esta bloqueado-- asi que la ventana falla cerrado.
        if estado["sesion"] is not None and estado["sesion"].acciones_por_vincular:
            for pendiente in estado["sesion"].acciones_por_vincular:
                try:
                    herr = next((h for h in config.herramientas
                                 if h.nombre == pendiente["herramienta"]), None)
                    aprob = getattr(herr, "aprobacion", None) if herr else None
                    persistencia.vincular_accion_a_conversacion(
                        tenant, pendiente["accion_id"], conversation_id,
                        aprob.vigencia_minutos if aprob else None)
                except Exception as e:
                    # La accion existe y sigue sin conversacion: no se puede
                    # aprobar, que es el lado seguro. Se registra para que no
                    # quede invisible.
                    registrar("acciones", "no se pudo ligar la accion a su conversacion",
                              tenant=tenant, error=e)
            estado["sesion"].acciones_por_vincular = []
        # Recien aca existe conversation_id (ver el docstring de
        # motor.responder): antes de esto no habia donde persistir a quien
        # verifico _ejecutar_confirmacion. Se repite cada turno una vez
        # verificado -- es un UPDATE idempotente, mas simple que rastrear si
        # ya se guardo antes.
        if estado["sesion"] is not None and estado["sesion"].verificado and estado["sesion"].id_cliente:
            try:
                persistencia.identificar_cliente(
                    tenant, conversation_id,
                    estado["sesion"].id_cliente, estado["sesion"].nombre,
                    # Lo capturado al verificar, para que sobreviva a un
                    # reinicio -- ver Sesion.CAMPOS_PERSISTIBLES.
                    #
                    # Van TODOS los campos, incluidos los que valen None, y no
                    # solo los que traen dato. Desde que 'datos_sesion' se
                    # fusiona en vez de reemplazarse (para no pisar el
                    # anti-rebote), omitir un campo ya no lo borra: deja el
                    # valor ANTERIOR. Y una segunda verificacion en la misma
                    # conversacion puede dejar 'sn_onu' en None -- pasa con el
                    # ~32% de los clientes activos, que no lo tienen cargado.
                    # El resultado seria la identidad de un cliente conviviendo
                    # con el serial de ONU de otro, y las herramientas de
                    # SmartOLT diagnosticando el equipo equivocado sin que nada
                    # avise. Mandando el None explicito, el '||' lo sobrescribe
                    # y la rehidratacion lo ignora por falsy.
                    {c: getattr(estado["sesion"], c, None)
                     for c in Sesion.CAMPOS_PERSISTIBLES})
            except Exception as e:
                registrar("persistencia", "no se pudo guardar la identidad", error=e)

        # El anti-rebote, aparte y SIN exigir identidad verificada: se llena
        # al derivar, y derivar pasa antes de que nadie verifique. Solo se
        # escribe si hay algo que proteger, asi que el turno normal -- el que
        # no deriva -- no paga ninguna escritura extra.
        if estado["sesion"] is not None:
            routing = {c: getattr(estado["sesion"], c, None)
                       for c in Sesion.CAMPOS_ROUTING_PERSISTIBLES
                       if getattr(estado["sesion"], c, None)}
            if routing:
                try:
                    persistencia.guardar_estado_routing(
                        tenant, conversation_id, routing)
                except Exception as e:
                    registrar("persistencia", "no se pudo guardar el routing", error=e)
    except Exception as e:  # nunca se rompe el turno por un fallo de persistencia
        registrar("persistencia", "no se pudo guardar el turno", error=e)

    # Solo conversaciones con un cliente final pueden terminar en un ticket
    # humano -- escalar la sesion de un colaborador no tiene destino. 'ya
    # escalada' vive en memoria del proceso (no en la base) porque evita una
    # lectura extra en cada turno; si el proceso se reinicia, en el peor caso
    # se re-evalua una vez mas, y escalar() es idempotente en la practica
    # (crea un ticket nuevo, pero no revienta nada).
    rol_cfg = config.roles.get(rol)
    cerrada = False
    # Lo que hace falta para saber, al final del turno, si el traspaso ocurrio
    # de verdad. Se declaran aca --y no dentro de la rama de escalada-- porque
    # justamente el caso que hay que cubrir es cuando esa rama NO corre.
    evaluador_fallo = False
    se_intento_escalar = False
    caso_creado = False
    ticket_creado = False
    # Los tres niveles de "quiero una persona" (ver forzado.py). Se declara
    # aca por lo mismo: la rama de abajo no corre para un colaborador interno
    # ni en una conversacion ya escalada, y el final del turno lo lee igual.
    decision_humano, evidencia_humano = None, ""
    preguntar_por_humano = False
    # 'ya_escalada' frena la creacion de un SEGUNDO caso, no la evaluacion
    # entera: una conversacion que volvio de manos de una persona sigue
    # necesitando que alguien note cuando el cliente da el tema por cerrado.
    # Atado a esa bandera, el asistente contestaba con normalidad y no cerraba
    # nunca -- ni el chat, ni el caso, ni el ticket.
    if (conversation_id and rol_cfg and rol_cfg.orientado_a == "cliente_final"
            and not estado["escalada"]):
        try:
            # Dentro del acumulador del turno: esta es una llamada al modelo
            # como cualquier otra, y hasta hoy no se contaba en ningun lado --
            # abrir() envuelve solo motor.responder(), y esto corre despues.
            # El gasto diario y el tope quedaban cortos en una llamada POR
            # TURNO de cliente.
            with consumo.seguir_anotando(ficha_consumo):
                evaluacion = escalamiento.evaluar(config, rol, estado["historial"])
        except Exception as e:
            # NO es lo mismo que 'evaluacion = None' por decision: el
            # evaluador no llego a opinar. Se anota para poder distinguirlo
            # al final del turno -- ver estado_escalada.calcular.
            registrar("escalamiento", "fallo al evaluar", error=e)
            evaluacion = None
            evaluador_fallo = True

        # Escalamiento POR HECHO, no por juicio. Si una herramienta declarada
        # con 'escalar_si_falla' (schema.py) fallo en este turno, la
        # conversacion escala aunque el evaluador haya dicho que no.
        #
        # No es desconfianza del evaluador en general: es que en los casos
        # limite responde distinto a la misma pregunta. Medido el 18/08/2026
        # sobre el mismo historial y la misma config, en llamadas seguidas:
        # escalar=true una vez, false la siguiente. Y para entonces el agente
        # ya le habia dicho al cliente que un colaborador iba a seguir su
        # caso -- o sea que la mitad de las veces le prometia una persona que
        # no llegaba nunca.
        # "El cliente pidio una persona" es un HECHO de la conversacion, no
        # una lectura: o lo dijo o no lo dijo. Si el evaluador elige ese
        # motivo y no hay ni un mensaje SUYO que lo pida, no se acepta.
        #
        # El 02/09/2026 clasifico asi un "hola, cual es mi plan? cedula
        # 000021": el asistente habia derivado a otro agente interno y se lo
        # narro como "te paso con un compañero del equipo", y el evaluador
        # leyo esa frase --suya, no del cliente-- como el pedido. Abrio un
        # caso que nadie pidio.
        #
        # Se descarta el MOTIVO, no se cambia por otro: si el evaluador no
        # supo por que escalaba, el turno sigue normal. Lo que de verdad
        # necesite una persona va a volver por su propio camino -- la
        # escalada forzada por hechos no pasa por aca, y si el cliente lo
        # pide de verdad, lo dice y ahi si hay evidencia.
        motivo_humano = config.escalamiento.motivo_pide_humano
        if (motivo_humano and evaluacion and evaluacion.get("escalar")
                and evaluacion.get("motivo") == motivo_humano
                and config.escalamiento.frases_pide_humano
                and not pidio_hablar_con_humano(
                    estado["historial"], config.escalamiento.frases_pide_humano)):
            registrar("escalamiento", "se descarta el motivo: el cliente nunca pidio una persona",
                      conversation_id=id_interno(estado.get("conversacion_id")),
                      motivo=motivo_humano)
            evaluacion = {**evaluacion, "escalar": False}

        # El otro lado del mismo candado. Descartar el motivo cuando no hay
        # evidencia deja el caso contrario sin resolver: el cliente SI la
        # pide, o dice que si cuando se le pregunta, y todo depende de que el
        # evaluador haya acertado. Es un hecho de la conversacion, asi que se
        # decide leyendola -- ver decidir_pedido_humano en forzado.py.
        decision_humano, evidencia_humano = _decidir_pedido_humano(
            config, estado["historial"])
        if decision_humano:
            # La evidencia es lo que ESCRIBIO el cliente: no va al log.
            registrar("escalamiento", "pedido de una persona",
                      conversation_id=id_interno(estado.get("conversacion_id")),
                      decision=decision_humano)

        # Si esta conversacion YA tuvo su caso, no se abre otro: lo que
        # sigue vivo es la deteccion del cierre. Sin este freno, una vuelta
        # despues de que una persona la atendio podia crear un caso duplicado.
        if estado["ya_escalada"] and evaluacion:
            evaluacion = {**evaluacion, "escalar": False}

        forzado, motivo_forzado = escalada_forzada(config, registro_herramientas)
        # Una accion que se ejecuto y no se pudo confirmar escala por el
        # motivo que declara su propia herramienta, no por lo que el modelo
        # opine del resultado. Va despues de escalada_forzada y solo si esa no
        # encontro nada: una herramienta que fallo AHORA pesa mas que una
        # comprobacion de un turno anterior.
        if not forzado and (veredicto_accion or {}).get("motivo_escalada"):
            forzado = veredicto_accion["motivo_escalada"]
            motivo_forzado = veredicto_accion.get("por_que", "")
        # Y lo mismo cuando el que lo pidio fue el cliente: o lo dijo claro, o
        # se le pregunto y contesto que si. Las dos son cosas que dijo EL, no
        # lecturas de su tono, y por eso no dependen de que el evaluador
        # coincida: el 18/08/2026 se midio que ante el mismo historial
        # responde distinto en llamadas seguidas.
        #
        # Va despues de las herramientas a proposito: una que fallo en este
        # turno describe mejor lo que hay que hacer que "pidio una persona".
        # De cualquiera de las dos formas termina en manos de alguien.
        if not forzado and decision_humano in (PIDE_HUMANO, CONFIRMA):
            forzado = config.escalamiento.motivo_pide_humano
            motivo_forzado = (
                f"el cliente pidio hablar con una persona: "
                f"\"{evidencia_humano[:120]}\"" if decision_humano == PIDE_HUMANO
                else f"se le pregunto si queria una persona y dijo que si: "
                     f"\"{evidencia_humano[:120]}\"")
        if estado["ya_escalada"]:
            forzado, motivo_forzado = None, ""
        if forzado:
            evaluacion = dict(evaluacion or {})
            if not evaluacion.get("escalar"):
                # motivo_forzado cita al cliente: queda en la evaluacion, no en el log.
                registrar("escalamiento", "escalada forzada",
                          conversation_id=id_interno(estado.get("conversacion_id")),
                          motivo=forzado)
            evaluacion["escalar"] = True
            evaluacion["motivo"] = forzado
            evaluacion["necesita_humano"] = True
            # El resumen y la etiqueta los deja el evaluador si los trajo; si
            # no vino nada (fallo entero), se completa lo minimo para que el
            # caso no llegue mudo a la bandeja.
            evaluacion.setdefault("etiqueta", "")
            # El resumen por defecto cuenta lo UNICO que se sabe con
            # certeza: que forzo la escalada. Antes decia siempre que una
            # consulta no habia devuelto datos y que habia que revisar a
            # mano -- escrito para el caso de una herramienta que FALLA, y
            # falso cuando lo que paso fue lo contrario: una herramienta que
            # salio bien y dejo un pedido para aplicar. Visto el 28/08/2026
            # en un cambio de clave de WiFi, con el caso creado y el pedido
            # anotado, mientras el resumen hablaba de un diagnostico fallido.
            #
            # Y si lo que forzo la escalada fue una herramienta que TOMO un
            # pedido, el resumen es el pedido mismo: es lo que hay que hacer,
            # y tiene que estar en el primer renglon del caso y no adentro de
            # la traza. Solo cuando el motivo salio de 'escalar_al_completar':
            # si escalo porque algo FALLO, un pedido tomado en el mismo turno
            # no es lo que hay que resolver.
            pedido = ""
            if forzado in motivos_por_hecho(config):
                pedido = next((l.get("resumen") for l in (registro_herramientas or [])
                               if l.get("resumen")), "")
            # Sin pedido tomado NO se inventa un resumen. Aca iba una frase
            # escrita para quien programo esto ("El evaluador no dejo
            # resumen... escalo porque 'ping_cliente' no pudo ejecutarse"):
            # nombra una pieza interna y una herramienta, dos cosas que no
            # significan nada para quien abre el caso en la bandeja, y se
            # llevaba el primer renglon, que es el mas leido. La bandeja ya
            # resuelve mejor el hueco: muestra el primer mensaje del cliente
            # y lo rotula "lo que escribio, sin resumir", asi que quien lee
            # sabe si tiene una sintesis o una cita. Un resumen vacio deja
            # que ese respaldo aparezca; uno de relleno se lo tapa.
            if pedido:
                evaluacion.setdefault("resumen", f"Pedido del cliente: {pedido}")
        # De que es esta conversacion. Se guarda SIEMPRE que el evaluador
        # haya clasificado, escale o no: el 'caso_manual' ya se calculaba en
        # cada turno pero solo se leia para decidir el agendamiento
        # automatico, y despues se tiraba -- una conversacion que el
        # asistente resolvio solo terminaba en la bandeja sin ninguna
        # etiqueta de que trataba. Ver supabase/202608180923_caso_conversacion.sql.
        # 'etiqueta' va junto con el caso y por el mismo motivo: sale de la
        # misma llamada al evaluador y hasta el 15/09/2026 se persistia SOLO
        # al escalar. Medido: 62 de 178 conversaciones reales sin etiquetar.
        if evaluacion and (evaluacion.get("caso_manual") or evaluacion.get("etiqueta")):
            persistencia.marcar_caso(tenant, conversation_id,
                                     evaluacion.get("caso_manual"),
                                     evaluacion.get("etiqueta") or "")

        # Un agendamiento pospuesto tiene que VOLVER, aunque el modelo no
        # pida escalar de nuevo. Cuando el verificador pide un dato que
        # faltaba, la escalada se pospone un turno (mas abajo) -- y hasta el
        # 21/08/2026 el caso solo regresaba si el modelo, por su cuenta,
        # volvia a decidir escalar. Medido contra la ONU de prueba: en el
        # turno siguiente el modelo pregunto por el tomacorriente en vez de
        # escalar, la verificacion no volvio a correr nunca, y la
        # conversacion quedo colgada -- el agente prometiendole un tecnico al
        # cliente en cada turno, sin un solo ticket detras. Es exactamente la
        # falla con la que se abrio este trabajo.
        if estado.get("agendamiento_pendiente") and not (evaluacion or {}).get("escalar"):
            registrar("agendamiento", "se retoma el caso pospuesto: el modelo no "
                                      "volvio a escalar por su cuenta",
                      conversation_id=id_interno(estado.get("conversacion_id")))
            evaluacion = {**(evaluacion or {}), **estado["agendamiento_pendiente"],
                         "escalar": True}

        if evaluacion and evaluacion.get("escalar"):
            # Se consume aca: si hace falta posponer otra vez, la rama de
            # abajo lo vuelve a guardar. Sin esto, un caso ya resuelto
            # (ticket o humano) seguiria retomandose cada turno.
            estado["agendamiento_pendiente"] = None
            necesita_humano = evaluacion.get("necesita_humano", True)
            nota_ticket = ""
            posponer = False
            # Tiene que existir SIEMPRE, no solo dentro de la rama de
            # agendamiento: mas abajo decide que se le promete al cliente, y
            # esa promesa no puede depender de una variable que a veces no se
            # asigno. Ver el comentario del aviso final.
            id_ticket_auto = None
            # El ticket que deja el trabajo anotado en la operacion. Se
            # cuenta aparte del de visita a proposito -- ver mas abajo.
            id_ticket_operativo = None

            # --- una vuelta mas antes de pasarlo a un humano ----------------
            # Solo para los motivos que el tenant declaro (por defecto,
            # ninguno). Ver escalamiento.merece_un_intento y el campo en
            # nucleo/config/schema.py.
            #
            # La nota le pide al modelo que ACTUE, no que contenga. Es la
            # diferencia que importa con un cliente furioso: "entiendo tu
            # frustracion, lamento las molestias" repetido suena a libreto y
            # lo enfurece mas; "ya vi tu equipo, la señal esta bien, te lo
            # estoy reiniciando" lo calma, porque es lo que vino a buscar.
            # Nadie pasa a un humano sin haber intentado nada.
            #
            # Vale para CUALQUIER motivo que haya elegido el modelo, y por eso
            # esta aparte de 'intentar_resolver_antes': aquello es una lista
            # que el tenant declara motivo por motivo; esto es la regla de
            # abajo de todo, y no depende de acertar que motivo va a elegir.
            #
            # Lo que la hizo falta: a las 14:50 se le agrego al evaluador la
            # instruccion de no leer un tramite como un pedido de hablar con
            # una persona. Funciono en la prueba, y a las 22:01 volvio a pasar
            # exactamente lo mismo -- mismo mensaje, otra conversacion, motivo
            # 'solicitud_explicita', traza vacia. El caso se abrio sin
            # identidad verificada, sin pedido tomado y sin ticket.
            #
            # Una escalada forzada por una herramienta NO pasa por aca: esa ya
            # tiene un hecho detras, que es justo lo que aca falta.
            if (not forzado and not estado["intento_antes_de_escalar"]
                    and con_las_manos_vacias(estado["historial"])):
                estado["intento_antes_de_escalar"] = True
                estado["nota_pendiente"] = (
                    "(Nota del sistema, no del cliente) Ibas a pasar esto a "
                    "una persona sin haber usado ninguna herramienta todavia. "
                    "Primero intenta lo tuyo: identifica al cliente si hace "
                    "falta y avanza con el procedimiento que corresponda. Si "
                    "de verdad hace falta una persona, en el proximo mensaje "
                    "se pasa.")
                posponer = True
                registrar("escalamiento", "se pospone: el asistente todavia no habia hecho nada",
                          conversation_id=id_interno(estado.get("conversacion_id")),
                          motivo=evaluacion.get("motivo"))
            elif escalamiento.merece_un_intento(
                    config, evaluacion.get("motivo", ""),
                    estado["intento_antes_de_escalar"]):
                estado["intento_antes_de_escalar"] = True
                estado["nota_pendiente"] = (
                    "(Nota del sistema, no del cliente) El cliente esta "
                    "molesto. NO lo escales todavia y NO le contestes con "
                    "frases de consuelo ni le pidas que se calme: usa tus "
                    "herramientas ahora, deciles que encontraste y que estas "
                    "haciendo al respecto. Si todavia no lo verificaste, "
                    "pedile la cedula UNA vez y segui de una. Si con eso no "
                    "alcanza, en el proximo mensaje se pasa a un companero.")
                posponer = True
                registrar("escalamiento", "se pospone una vuelta: el asistente lo intenta primero",
                          conversation_id=id_interno(estado.get("conversacion_id")),
                          motivo=evaluacion.get("motivo"))

            # --- verificacion automatica de agendamiento --------------------
            # Solo corre si el tenant declaro ESTE caso puntual en
            # 'escalamiento.agendamiento_automatico' (apagado por defecto,
            # ver nucleo/config/schema.py:Escalamiento). Ver
            # nucleo/seguimiento/agendamiento.py para el detalle.
            caso_manual = evaluacion.get("caso_manual")
            herramienta_auto = (config.escalamiento.agendamiento_automatico.get(caso_manual)
                                if caso_manual else None)
            # Dos motivos distintos para saltear la verificacion, y los dos
            # valen:
            #
            # 'not posponer' -- si ya se pospuso arriba, esta escalada no va a
            # ocurrir en este turno y 'verificar' es otra llamada al modelo.
            #
            # 'not forzado' -- cuando la escalada la fuerza una herramienta que
            # no pudo ejecutarse, no hay nada que verificar ni que repreguntar.
            # El verificador veria el checklist incompleto y pospondria la
            # escalada para pedirle un dato mas al cliente: un dato que no
            # cambia nada, porque lo que falta no lo tiene el cliente sino
            # nuestro sistema. Visto el 18/08/2026 -- la escalada forzada se
            # activaba y quedaba atrapada justo aca, asi que al cliente se le
            # prometia un colaborador que no llegaba nunca.
            # Antes que nada, el veto: hay trazas con las que agendar es un
            # ERROR aunque todo lo demas de al derecho. La caida compartida
            # es la que lo motiva -- desde la ONU de un cliente se ve igual
            # que su fibra cortada, que es la evidencia que agenda sola.
            # Treinta reportes de la misma caida = treinta tecnicos
            # despachados por una falla que no esta en ninguna de las casas.
            veto = (agendamiento.veto_de_agendamiento(config, caso_manual,
                                                      estado["historial"])
                    if herramienta_auto and caso_manual else None)
            if veto:
                registrar("agendamiento", "VETADO: no se agenda visita individual, el caso "
                                          "sigue el camino normal", veto=veto)
                herramienta_auto = None

            if herramienta_auto and not posponer and not forzado:
                # Primero lo barato: si la traza ya prueba por si sola que
                # corresponde visita (evidencia de la RED, no del relato del
                # cliente), se agenda sin consultar el manual -- y sin gastar
                # la llamada al modelo que cuesta el verificador. Ver
                # 'evidencia_suficiente' en schema.py: el checklist que el RAG
                # recupera esta escrito para una persona que atiende, y en
                # estas ramas pide datos que no existen (el 21/08/2026 exigia
                # "¿que mensaje aparece en el dispositivo?" a alguien sin
                # ninguna conexion de la cual leer un mensaje).
                directo = agendamiento.evidencia_ya_alcanza(
                    config, caso_manual, estado["historial"])
                if directo:
                    registrar("agendamiento", "evidencia suficiente: se agenda sin pasar por "
                                              "el checklist del manual", evidencia=directo)
                    veredicto = {"checklist_completo": True,
                                 "corresponde_agendar": True,
                                 # Mismo respaldo que el ticket de la
                                 # operacion: sin resumen, lo que escribio el
                                 # cliente. Un tecnico que recibe la visita
                                 # con la descripcion vacia no sabe a que va.
                                 "descripcion_visita": (
                                     (evaluacion.get("resumen") or "").strip()
                                     or _primer_mensaje_del_cliente(estado["historial"])
                                 )[:400]}
                else:
                    try:
                        veredicto = agendamiento.verificar(config, tenant, rol, estado["historial"])
                    except Exception as e:
                        registrar("agendamiento", "fallo al verificar", error=e)
                        veredicto = None

                # Sin esta linea, un veredicto que dice "no" es invisible: no
                # hay ticket, no hay error, y desde afuera se ve igual que si
                # el agendamiento no estuviera configurado.
                if veredicto:
                    # 'pregunta_faltante' la redacta el modelo sobre la
                    # conversacion: se dice SI falta algo, no que.
                    registrar("agendamiento", "veredicto", caso=caso_manual,
                              checklist_completo=veredicto.get("checklist_completo"),
                              corresponde_agendar=veredicto.get("corresponde_agendar"),
                              falta_dato=bool(veredicto.get("pregunta_faltante")))

                if (veredicto and veredicto.get("checklist_completo") and veredicto.get("corresponde_agendar")
                        and _efecto_del_turno(tenant, canal, id_sesion, estado,
                                              "agendamiento_automatico")):
                    id_ticket_auto = agendamiento.agendar(
                        config, tenant, estado["sesion"], herramienta_auto,
                        veredicto.get("descripcion_visita", ""))
                    if id_ticket_auto:
                        ticket_creado = True
                        # Queda anotado en la conversacion, no solo dentro del
                        # texto del caso: es lo que permite responder y cerrar
                        # ese ticket despues sin parsear un parrafo.
                        persistencia.guardar_ticket_operativo(
                            tenant, conversation_id, id_ticket_auto)
                        necesita_humano = False
                        nota_ticket = (f"\n\nVisita tecnica agendada "
                                       f"automaticamente (ticket #{id_ticket_auto}).")
                elif (veredicto and not veredicto.get("checklist_completo")
                      and veredicto.get("pregunta_faltante")
                      and not estado["repreguntado_agendamiento"]):
                    # Una sola oportunidad de cerrar el hueco antes de
                    # escalar de verdad -- si el cliente no puede
                    # resolverlo, el proximo intento ya no repregunta.
                    estado["repreguntado_agendamiento"] = True
                    # Lo que hace falta para retomarlo solo el turno que
                    # viene. 'repreguntado_agendamiento' ya en True garantiza
                    # que la proxima vuelta NO repregunte de nuevo: o sale
                    # ticket, o sale humano.
                    estado["agendamiento_pendiente"] = {
                        "motivo": evaluacion.get("motivo", ""),
                        "etiqueta": evaluacion.get("etiqueta", ""),
                        "resumen": evaluacion.get("resumen", ""),
                        "caso_manual": caso_manual,
                        "necesita_humano": necesita_humano,
                    }
                    estado["nota_pendiente"] = (
                        "(Nota del sistema, no del cliente) Antes de "
                        "escalar, falta confirmar un dato puntual del "
                        f"procedimiento: {veredicto['pregunta_faltante']} "
                        "Pediselo al cliente en tu proxima respuesta, de "
                        "forma natural.")
                    posponer = True

            if not posponer:
                # RESERVA DEL CONTROL HUMANO, antes de cualquier efecto de la
                # escalada (ticket operativo, caso del CRM). Escritura en
                # paralelo (B3.2): la verdad nueva queda en 'humano' aunque
                # despues fallen el ticket o el CRM, y nunca vuelve sola a la
                # IA. Todavia no decide la pausa -- eso sigue en el legado
                # hasta el corte de control --, por eso un fallo aca se anota
                # y no detiene el turno. Si ya se agendo una visita sola
                # (necesita_humano=False) no hay nada que reservar.
                reservado = False
                escalada_propia = False
                if necesita_humano:
                    try:
                        r_reserva = transiciones.escalar(
                            tenant, conversation_id, motivo=evaluacion.get("motivo", ""),
                            clave=f"escalada:{mensaje_id}" if mensaje_id else None)
                        # Reservado = la base YA dice humano, se haya aplicado
                        # ahora o por un reintento de la misma escalada.
                        reservado = r_reserva.aplicada or r_reserva.motivo in ("reintento", "sin_cambio")
                        # La version que escribio ESTE turno es la esperada al
                        # enviar (D24, punto 2). 'sin_cambio' no la mueve: si
                        # otro ya la paso a humano, el envio tiene que frenar.
                        if r_reserva.aplicada or r_reserva.motivo == "reintento":
                            escalada_propia = True
                            estado["escalada_del_turno"] = {
                                "conversation_id": str(conversation_id),
                                "version": r_reserva.version}
                            estado["autorizacion_turno"] = {
                                "conversation_id": str(conversation_id),
                                "relevo_version": r_reserva.version,
                                "escalada_version": r_reserva.version}
                    except Exception as e:
                        registrar("relevo", "no se pudo reservar el control humano", error=e)
                # El trabajo queda anotado donde la operacion lo ve, con un
                # tecnico asignado -- no solo en la bandeja interna del
                # asistente. Distinto del agendamiento automatico: eso decide
                # SI corresponde un tecnico y pasa por el verificador del
                # manual; esto no decide nada, el caso ya se escalo. Si ya se
                # agendo una visita en este mismo turno no se duplica: ese
                # ticket ya es el trabajo anotado.
                #
                # En variable PROPIA, no en 'id_ticket_auto': ese decide el
                # aviso de "tu visita ya quedo agendada" que se le suma a la
                # respuesta, y un ticket de diagnostico NO es una visita.
                # Reusarlo hacia que el cliente escuchara que iba un tecnico a
                # su casa cuando lo unico que paso fue que el caso quedo
                # anotado -- visto el 21/08/2026 en la primera prueba de este
                # mismo codigo. Con la variable separada, el turno cae en la
                # rama de escalada sin visita, que le dice la verdad: que lo
                # toma una persona.
                entrada_ticket = (
                    agendamiento.ticket_para_escalar(config, caso_manual,
                                                     estado["historial"])
                    if caso_manual and not id_ticket_auto else None)
                nombre_ticket = entrada_ticket.herramienta if entrada_ticket else None
                # D25: el ticket y el caso del CRM son de ESTA escalada si la
                # reserva la escribio este turno; si no, son un efecto autonomo
                # y piden que la IA siga controlando.
                clase_escalada = (autorizacion_relevo.SYNC_ESCALADA if escalada_propia
                                  else autorizacion_relevo.AUTONOMO_IA)
                if nombre_ticket and not _efecto_del_turno(
                        tenant, canal, id_sesion, estado, "ticket_de_escalada",
                        clase=clase_escalada):
                    nombre_ticket = None
                if nombre_ticket:
                    # La sugerencia va PRIMERO en la descripcion, no al
                    # final: un ticket con asunto generico se abre para saber
                    # de que es, y quien lo lee tiene que encontrar eso en la
                    # primera linea. Al pie se lo come el resto del texto.
                    # El ticket de la operacion SI necesita cuerpo -- a
                    # diferencia de la bandeja, que sabe caer al mensaje del
                    # cliente por su cuenta. Cuando no hay resumen se usa lo
                    # mismo que usaria ella: lo que escribio el cliente. Es
                    # de el y es cierto, y sirve mas que un ticket en blanco.
                    descripcion_ticket = (evaluacion.get("resumen", "") or "")
                    if not descripcion_ticket.strip():
                        descripcion_ticket = _primer_mensaje_del_cliente(
                            estado["historial"])

                    # LA FICHA DE TV VA DEBAJO DEL RELATO, no en su lugar.
                    #
                    # El resumen dice que paso; la ficha dice lo que se
                    # confirmo -- marca, conexion, que guia se entrego. Lo
                    # arma el codigo con lo que ya se resolvio, en vez de
                    # confiar en que el modelo lo recuerde bien al redactar
                    # (ver escalamiento.ficha_tv). Vacia si la conversacion
                    # no fue de television.
                    ficha = escalamiento.ficha_tv(
                        estado["sesion"], evaluacion,
                        evidencias=_evidencias_de(tenant, conversation_id))
                    if ficha:
                        descripcion_ticket = (
                            descripcion_ticket.strip() + chr(10) * 2 + ficha)
                    sugerido = (evaluacion.get("asunto_sugerido") or "").strip()
                    if sugerido:
                        descripcion_ticket = (
                            "[Sin clasificar] El asistente sugiere la categoria "
                            + chr(34) + sugerido + chr(34)
                            + " para casos como este." + chr(10) + chr(10)
                            + descripcion_ticket)

                    id_ticket_operativo = agendamiento.agendar(
                        config, tenant, estado["sesion"], nombre_ticket,
                        descripcion_ticket[:400],
                        area=entrada_ticket.area,
                        asunto=entrada_ticket.asunto,
                        prioridad=entrada_ticket.prioridad)
                    if id_ticket_operativo:
                        ticket_creado = True
                        registrar("escalamiento", "ticket operativo creado",
                                  ticket=id_ticket_operativo, herramienta=nombre_ticket,
                                  conversation_id=id_interno(conversation_id))
                        persistencia.guardar_ticket_operativo(
                            tenant, conversation_id, id_ticket_operativo)
                        # Que el numero quede en el caso: quien lo tome en la
                        # bandeja tiene que poder saltar al ticket sin buscarlo.
                        nota_ticket += (chr(10) + chr(10) + "Ticket operativo #"
                                       + str(id_ticket_operativo)
                                       + " (" + nombre_ticket + ").")
                    else:
                        # Que NO haya salido importa: quien lea el caso en la
                        # bandeja tiene que saber que la operacion no lo
                        # recibio, en vez de suponer que si.
                        registrar("escalamiento", "no se pudo crear el ticket operativo",
                                  herramienta=nombre_ticket,
                                  conversation_id=id_interno(conversation_id))

                # Lo que el cliente va a leer en este turno, decidido ANTES
                # de escalar y no despues. Dos motivos, y el segundo es el que
                # obliga:
                #
                # (1) El aviso de visita se decide por el TICKET REAL, no por
                # 'necesita_humano'. El evaluador puede devolver
                # necesita_humano=false por su cuenta (caso registrado para
                # seguimiento, sin urgencia) sin que se haya agendado nada:
                # atado a esa bandera, el cliente escuchaba "tu visita ya
                # quedo agendada" cuando no existia ninguna visita. Visto el
                # 15/08/2026 -- el peor error posible aca es prometerle a
                # alguien un tecnico que no va a ir. Este aviso SI se suma al
                # texto del modelo: el turno cierra con el diagnostico ("esto
                # necesita ir a la casa") y el aviso lo completa.
                #
                # (2) El traspaso a una persona REEMPLAZA la respuesta, no se
                # le suma. Pegarlo al final producia mensajes que se
                # contradicen solos: la escalada se evalua DESPUES de que el
                # modelo contesto, asi que cuando escribio su respuesta
                # todavia no sabia que el turno terminaba en traspaso. Visto
                # en produccion el 15/08/2026 -- al cliente le llego "necesito
                # verificar tu identidad: ¿me pasas tu cedula?" y debajo "Te
                # paso con un companero", y no habia forma de saber si mandar
                # la cedula o esperar. Lo que se descarta no se pierde: si el
                # caso pasa a una persona, la pregunta que el modelo iba a
                # hacer ya no corre. El texto es del tenant, asi que el tono
                # se ajusta en config.escalamiento.mensaje.
                #
                # Y se calcula aca arriba, antes de crear el caso, porque la
                # transcripcion que viaja al caso tiene que llevar ESTE texto
                # y no el borrador que el modelo escribio sin saber que el
                # turno terminaba en traspaso.
                if id_ticket_auto:
                    respuesta_al_cliente = (
                        f"{respuesta}\n\nTu visita tecnica ya quedo agendada, "
                        f"un tecnico te va a contactar para coordinar.").strip()
                else:
                    # El texto depende del MOTIVO: anunciar un pedido que
                    # salio bien no se dice igual que anunciar una queja.
                    respuesta_al_cliente = _mensaje_de_escalada(
                        config, evaluacion.get("motivo")) or respuesta

                se_intento_escalar = True
                caso_creado = _efecto_del_turno(
                    tenant, canal, id_sesion, estado, "caso_de_escalada",
                    clase=clase_escalada) and escalamiento.escalar(
                    config, tenant, id_sesion, conversation_id, estado["historial"],
                    evaluacion.get("motivo", ""), evaluacion.get("etiqueta", ""),
                    resumen=(evaluacion.get("resumen", "") + nota_ticket).strip(),
                    necesita_humano=necesita_humano,
                    no_se_pudo_comprobar=evaluacion.get("no_se_pudo_comprobar", ""),
                    siguiente_paso=evaluacion.get("siguiente_paso", ""),
                    # El mismo asunto con el que entra el ticket, para que
                    # la cola del CRM y la de la operacion se lean igual.
                    # De los DOS caminos que abren ticket, el que haya
                    # corrido: el elegido por la traza al escalar, o el fijo
                    # de la herramienta cuando la visita se agendo sola.
                    asunto=(entrada_ticket.asunto if entrada_ticket
                            else (agendamiento.asunto_fijo_de(config, herramienta_auto)
                                  if id_ticket_auto and herramienta_auto else "")),
                    nombre_cliente=getattr(estado["sesion"], "nombre", "") or "",
                    # Para que el caso muestre la conversacion como la vivio
                    # el cliente, no como la escribio el modelo.
                    respuesta_al_cliente=respuesta_al_cliente,
                    asignar_a=(agendamiento.perfil_del_area(
                        tenant,
                        config.escalamiento.area_por_caso.get(caso_manual, ""),
                        config)
                        if caso_manual else None) or "")
                # QUEDO REGISTRADO EN ALGUN LADO, SI O NO. Una sola variable.
                #
                # Antes esto se calculaba dos veces y para cosas distintas:
                # mas abajo decidia QUE se le dice al cliente, y la pausa
                # decidia por su cuenta mirando solo 'caso_id'. Prometiamos
                # con tres llaves y vigilabamos con una.
                #
                # Con ticket operativo y sin caso del CRM: al cliente se le
                # decia que un compañero lo iba a atender, 'escalada' quedaba
                # en true, 'caso_id' en None, y en el turno siguiente
                # 'caso_sigue_abierto(None)' contestaba false -- el codigo
                # concluia que el caso habia cerrado y el bot volvia a
                # atender a alguien a quien se le prometio una persona. Dos
                # interlocutores para el mismo cliente.
                quedo_registrado = bool(id_ticket_auto or caso_creado
                                        or id_ticket_operativo)

                # La pausa (arriba, "si ya se escalo, el bot NO contesta")
                # solo tiene sentido cuando de verdad hay un humano al que
                # esperar -- si se agendo solo, el bot sigue atendiendo
                # normal desde el proximo mensaje. Y si no quedo registrado
                # en ningun lado, tampoco: ver mas abajo.
                # FAIL-CLOSED (Q5): si la reserva quedo en la base, la pausa es
                # un hecho aunque el ticket y el CRM hayan fallado -- la base
                # ya dice que esta conversacion espera a una persona, y la
                # memoria no puede decir otra cosa. Solo si ni siquiera la
                # reserva se pudo guardar se vuelve a lo de antes.
                estado["escalada"] = necesita_humano and (quedo_registrado or reservado)
                reservado_turno = reservado
                # Y POR QUE se escalo. Lo lee el aviso que recibe el cliente
                # en cada mensaje mientras espera: sin esto se le contestaba
                # con el texto generico ("entiendo tu molestia") aunque
                # hubiera escalado por un tramite, porque el motivo solo
                # estaba en la base y la sesion viva no lo miraba.
                estado["motivo_escalada"] = evaluacion.get("motivo")
                # El caso queda guardado para poder consultarlo despues: es lo
                # que permite que la pausa de arriba sepa cuando el humano lo
                # cerro y el asistente pueda retomar solo.
                try:
                    estado["caso_id"] = persistencia.caso_de_conversacion(tenant, conversation_id)
                except Exception as e:
                    registrar("escalamiento", "no se pudo leer el caso de la conversacion", error=e)

                # UNA PAUSA QUE NO SE VA A DESPAUSAR SOLA: dejarla dicha.
                #
                # Con registro pero sin caso del CRM, la conversacion queda
                # pausada y nadie mira el estado de la otra cola, asi que solo
                # sale por devolucion explicita de una persona. Es el lado
                # correcto para equivocarse, pero si empieza a pasar seguido
                # hay clientes esperando a alguien que quiza no los vea.
                #
                # Hoy es raro -- 2 de 63 escalamientos historicos, los dos del
                # 11/08/2026 y con pinta de prueba-- y por eso NO se construyo
                # un 'ticket_sigue_abierto()': seria otra API que consultar y
                # otro fail-safe que mantener para un caso que no ocurre. Se
                # mide primero. Esta linea es el instrumento: la rama era muda,
                # y sin ella la unica forma de enterarse es que alguien note un
                # cliente callado.
                if necesita_humano and quedo_registrado and not estado["caso_id"]:
                    registrar("escalamiento", "traspaso registrado SIN caso del CRM -- la "
                                              "conversacion queda pausada hasta que una persona "
                                              "la devuelva. Si esto se repite, revisar por que "
                                              "el caso no se crea.",
                              conversation_id=id_interno(conversation_id))

                # Escalo y no quedo registrado en ningun lado: no se le
                # puede decir al cliente que si.
                #
                # Alcanza con que haya quedado en UNO de los tres: el caso lo
                # pone en la cola del CRM y el ticket (automatico u operativo)
                # en la de la operacion. Cualquiera de ellos es una persona
                # que lo va a ver, que es lo que el aviso promete. Si no quedo
                # en ninguna -- el 28/08/2026 el CRM rechazo un caso con un
                # 400 y al cliente se le contesto igual que su pedido habia
                # quedado registrado -- se le dice la verdad y se le pide que
                # escriba de nuevo, que es lo que dispara el reintento.
                #
                # Con la reserva hecha, el pedido de atencion humana SI quedo:
                # se le dice el anuncio normal, que promete una persona y no
                # un numero de caso. Pedirle que escriba de nuevo seria
                # mandarlo a insistirle a un bot que ya no le va a contestar.
                if quedo_registrado or reservado:
                    respuesta = respuesta_al_cliente
                else:
                    respuesta = _mensaje_si_no_quedo(config) or respuesta

                # Y SI NO QUEDO, EL ESTADO TIENE QUE ACOMPAÑAR AL MENSAJE.
                #
                # Le decimos "escribime de nuevo" justamente para que el
                # proximo mensaje reintente. Pero 'escalada' y 'ya_escalada'
                # quedaban en true igual, asi que ese reintento no podia
                # ocurrir: 'ya_escalada' lo bloquea como duplicado, y una
                # pausa fail-closed se lo tragaria. Le pedimos que insista y
                # despues no lo escuchabamos.
                #
                # Sin registro no hay nadie a quien esperar ni caso que
                # consultar: se limpia todo y la conversacion sigue viva.
                estado["ya_escalada"] = quedo_registrado or reservado
                if not quedo_registrado:
                    estado["caso_id"] = None
                # El mensaje del asistente ya se guardo (mas arriba, antes de
                # poder evaluar la escalada -- necesitaba conversation_id).
                # Sin esto el HTTP response trae el aviso pero /conversaciones
                # sigue mostrando el texto de antes.
                if mensaje_id:
                    try:
                        persistencia.actualizar_contenido_mensaje(tenant, mensaje_id, respuesta)
                    except Exception as e:
                        registrar("persistencia", "no se pudo actualizar el aviso de escalada", error=e)
        elif decision_humano == PREGUNTAR:
            # Ni lo pidio ni es una consulta normal: esta diciendo que esto no
            # se le esta resolviendo. No se decide por el --escalar aca abre
            # casos que nadie pidio, y no escalar lo deja golpeando una
            # pared--: se le PREGUNTA, y decide su respuesta.
            #
            # El texto se agrega despues de _cerrar_el_traspaso, al final del
            # turno: esa funcion revisa si la respuesta promete una persona, y
            # la pregunta nombra una. Ver mas abajo.
            preguntar_por_humano = True
            registrar("escalamiento", "se pregunta si quiere una persona",
                      conversation_id=id_interno(conversation_id))
        elif _hay_verificacion_pendiente(tenant, conversation_id):
            # CANDADO. Mientras una accion siga sin comprobarse, esta
            # conversacion no se cierra ni se pregunta si cerrarla: todavia no
            # se sabe si lo que se hizo sirvio. Cerrar aca dejaria al cliente
            # sin servicio y al caso marcado como resuelto.
            #
            # No se queda trabado para siempre: la verificacion se resuelve
            # sola --confirmada, no confirmada o no verificable-- al agotar
            # sus intentos, y una conversacion abandonada la cierra igual el
            # barrido por inactividad.
            registrar("verificacion", "no se cierra, hay una accion sin comprobar",
                      conversation_id=id_interno(conversation_id))
        elif (evaluacion and estado["cierre_propuesto"] and _pregunta_de_cierre(config)
                and not evaluacion.get("confirma_cierre")):
            # Se le pregunto y NO dijo que si: trajo otra cosa. La pregunta
            # queda sin usar y se le vuelve a hacer cuando corresponda -- si
            # no se limpiara, el proximo turno que parezca terminado cerraria
            # sin haberle preguntado por lo nuevo.
            estado["cierre_propuesto"] = False
        elif (evaluacion and evaluacion.get("resuelta")
                and _pregunta_de_cierre(config)
                and not evaluacion.get("confirma_cierre")):
            # Antes de cerrar, se PREGUNTA. Vale para el camino normal igual
            # que para el escalado: "gracias" y "ok" son despedidas, no
            # confirmaciones de que no quedo nada pendiente, y el modelo las
            # lee como lo mismo. Se suma a lo que ya contesto, que suele ser
            # su propio saludo.
            estado["cierre_propuesto"] = True
            respuesta = f"{respuesta}\n\n{_pregunta_de_cierre(config)}".strip()
            if mensaje_id:
                try:
                    persistencia.actualizar_contenido_mensaje(tenant, mensaje_id, respuesta)
                except Exception as e:
                    registrar("persistencia", "no se pudo agregar la pregunta de cierre", error=e)
        elif evaluacion and (evaluacion.get("resuelta")
                             or evaluacion.get("confirma_cierre")):
            # Ya se le pregunto (o el tenant no quiere que se pregunte) y
            # confirmo: cierra la conversacion en la bandeja (ver
            # cerrar_conversacion en persistencia). El propio saludo de
            # despedida del modelo ya cumple el rol de "mensaje de cierre" --
            # no hace falta agregar otro, sonaria repetido.
            # Si detras hay un caso --porque esta conversacion paso por una
            # persona y volvio-- se cierran los tres, no solo el chat. Dejar
            # el caso y el ticket abiertos obligaria a cerrarlos a mano
            # justo cuando el cliente ya dijo que quedo conforme.
            try:
                if not _efecto_del_turno(tenant, canal, id_sesion, estado, "cierre_por_confirmacion"):
                    raise _CierreCancelado()
                caso = estado.get("caso_id") or persistencia.caso_de_conversacion(
                    tenant, conversation_id)
                if caso:
                    hecho = operativo.cerrar_todo(
                        config, tenant,
                        {"id": conversation_id, "caso_id": caso,
                         "ticket_operativo": persistencia.ticket_operativo_de(
                             tenant, conversation_id)},
                        (config.escalamiento.texto_cierre_confirmado or "").strip()
                        or "El cliente confirmo que su caso quedo resuelto.")
                    cerrada = hecho["conversacion"]
                else:
                    # T15a/T15b: lo cierra la confirmacion del cliente. La
                    # transicion mira 'atendida_manual' para saber cual de las
                    # dos es, y deja el desenlace en NULL: que el cliente diga
                    # "ya funciona" no dice si era la ONT, el WiFi o la fibra,
                    # y esa columna existe para contar eso (B6, §3.5).
                    r_cierre = transiciones.cerrar(tenant, conversation_id,
                                                   por="cliente", config=config)
                    cerrada = r_cierre.aplicada or r_cierre.motivo == "ya_cerrada"
                if not cerrada:
                    # Quedo algo vivo (una accion propuesta, una verificacion
                    # sin resolver): no se cierra. Decirle al cliente que su
                    # caso quedo cerrado mientras el sistema sigue esperando
                    # una respuesta de afuera es la clase de mentira chica que
                    # despues nadie puede explicar.
                    registrar("conversaciones", "el cierre por confirmacion no procedio",
                              conversation_id=id_interno(conversation_id))
            except _CierreCancelado:
                pass
            except Exception as e:
                registrar("conversaciones", "no se pudo cerrar la conversacion", error=e)
            # El supervisor audita la conversacion ya cerrada y deja un
            # veredicto PENDIENTE para que una persona lo confirme desde
            # /manual -- nunca publica solo (ver nucleo/seguimiento/
            # supervisor.py). Aparte del cierre: un fallo aca no debe
            # revertir que la conversacion ya quedo cerrada.
            if cerrada:
                try:
                    supervisor.revisar(config, rol, tenant, conversation_id, estado["historial"])
                except Exception as e:
                    registrar("supervisor", "fallo al revisar la conversacion", error=e)

    # --- ¿el traspaso ocurrio de verdad? ------------------------------------
    # Tres situaciones distintas que antes se veian iguales desde afuera, y la
    # unica garantia que importa: no se afirma un traspaso que no quedo
    # registrado. Ver nucleo/seguimiento/estado_escalada.py.
    antes_del_candado = respuesta
    respuesta = _cerrar_el_traspaso(
        config, tenant, conversation_id, mensaje_id, respuesta, id_sesion,
        evaluador_fallo=evaluador_fallo, se_intento=se_intento_escalar,
        caso_creado=caso_creado, ticket_creado=ticket_creado,
        reservado=reservado_turno)

    # --- "¿quieres que te comunique con una persona?" -----------------------
    # Se agrega ACA, con el candado ya corrido: la pregunta nombra a un
    # colaborador humano, que es exactamente lo que ese candado busca en la
    # respuesta para sustituirla. Puesta antes, cualquier turno con el
    # evaluador caido la habria borrado.
    #
    # Y no se agrega si el candado sustituyo la respuesta: ese texto le pide
    # al cliente que vuelva a escribir porque su pedido NO quedo registrado.
    # Preguntarle ahi mismo si quiere una persona dice las dos cosas a la vez.
    if preguntar_por_humano and respuesta == antes_del_candado:
        pregunta = _pregunta_pide_humano(config)
        respuesta = f"{respuesta}\n\n{pregunta}".strip()
        # El historial en memoria tiene que quedar con la pregunta incluida:
        # es de ahi de donde el proximo turno saca si YA se pregunto --el
        # freno del bucle-- y si lo que el cliente acaba de contestar le
        # responde a esto o a otra cosa.
        for msg in reversed(estado["historial"]):
            if msg.get("role") == "assistant":
                msg["content"] = f"{msg.get('content') or ''}\n\n{pregunta}".strip()
                break
        if mensaje_id:
            try:
                persistencia.actualizar_contenido_mensaje(tenant, mensaje_id, respuesta)
            except Exception as e:
                registrar("persistencia", "no se pudo agregar la pregunta por una persona", error=e)

    # El turno entero, ya con lo que gastaron el evaluador de escalamiento y
    # todo lo que corre despues de componer la respuesta.
    #
    # Va aca y no en el insert porque el orden lo impide: la respuesta se
    # guarda en la linea ~1010 y el evaluador corre en la ~1120. Con solo el
    # insert, el registro por mensaje contaba media llamada de las que de
    # verdad hizo el turno -- justo el numero que hace falta para saber por
    # que un turno tardo.
    if mensaje_id_turno:
        persistencia.completar_medicion(
            tenant, mensaje_id_turno,
            tokens_entrada=ficha_consumo.tokens_entrada,
            tokens_salida=ficha_consumo.tokens_salida,
            costo_usd=ficha_consumo.costo_usd,
            llamadas_modelo=ficha_consumo.n_llamadas)

    # QUE AREA QUEDO ATENDIENDO, para quien mire la conversacion desde afuera.
    #
    # 'rol' es el parametro con el que entro el turno y se REASIGNA mas arriba
    # si el turno derivo, asi que aca vale el area que de verdad atendio -- la
    # misma que se persiste en 'rol_efectivo' y que va a recibir el proximo
    # mensaje del cliente.
    #
    # Sale en la respuesta porque sin esto no habia forma de verlo sin abrir
    # la base. Los tres bugs de derivacion del 08 y 09/09/2026 se veian todos
    # aca: uno anunciaba un pase que ya habia ocurrido, y saber que quien
    # escribia era 'ventas' -- no la puerta-- lo hacia obvio de inmediato.
    # LO QUE EL MODELO RECUERDA ES LO QUE EL CLIENTE LEYO.
    #
    # Varias guardas reescriben la respuesta DESPUES de que el motor la agrego
    # al historial (la promesa de traspaso sin registro, el aviso de escalada,
    # la pregunta de cierre) y corregian solo la fila guardada. En vivo el
    # modelo seguia recordando su texto original; tras un reinicio, el
    # reconstruido traia el corregido. Un solo punto al final, para todas.
    _sincronizar_respuesta_en_memoria(estado["historial"], inicio_turno, respuesta)

    rol_cfg_final = config.roles.get(rol)
    return {"respuesta": respuesta, "verificado": estado["sesion"].verificado,
            "cerrada": cerrada, "conversacion_id": conversation_id,
            "mensaje_id": mensaje_id, "mensaje_usuario_id": mensaje_usuario_id,
            "rol_activo": rol,
            "rol_activo_nombre": (getattr(rol_cfg_final, "area", None)
                                  or rol) if rol_cfg_final else rol,
            "pausada": False,
            # Para el punto 2 de D24 (antes del POST a Meta). No sale por /chat.
            "_autorizacion": dict(estado["autorizacion_turno"])}


@app.post("/chat")
def chat():
    """
    Un turno. El agente se puede indicar de DOS formas, y son excluyentes:

      rol         el nombre, tal cual. Lo usa el simulador de WhatsApp, que
                  necesita fijar 'cliente_final' a proposito para probar ese
                  canal, y cualquier llamador interno que ya sepa cual quiere.
      profile_id  el perfil del CRM de quien pregunta. El motor resuelve que
                  agentes tiene asignados (supabase/202608132036_agentes_por_colaborador)
                  y le arma la union: un colaborador con Soporte y Facturacion
                  puede preguntar por el ticket Y la factura en un solo turno,
                  sin elegir a cual agente le habla.
    """
    cuerpo = request.get_json(force=True, silent=True) or {}

    # EL CANAL SE DECIDE PRIMERO, antes de leer config, crear sesion o
    # escribir nada. /chat no envia a ningun medio externo: un turno con canal
    # real que entra por aca guarda como mensaje del cliente algo que el
    # cliente no escribio, y le mueve la ventana de 24 h y el cierre por plazo
    # (SPEC/CONTRATO_RELEVO_IA_HUMANO.md, D3 y X1). El cliente real solo entra
    # por su webhook firmado. Rechazar despues de haber tocado algo no seria
    # fallar cerrado.
    #
    # Sin 'canal' sigue valiendo "api", como siempre (el asistente interno y
    # el smoke de DESPLIEGUE.md no lo mandan). Presente pero desconocido o
    # vacio NO cae en ese default: se rechaza.
    canal_pedido = cuerpo["canal"] if cuerpo.get("canal") is not None else canales.API
    try:
        canal = canales.normalizar_canal(canal_pedido)
    except canales.CanalInvalido:
        return jsonify({"error": "Canal desconocido."}), 400
    if canal in canales.REALES:
        # Sin identificador ni texto en el registro: son datos del cliente.
        registrar("chat", "rechazado un turno con canal real", canal=canal,
                  tenant=cuerpo.get("tenant"))
        return jsonify({"error": f"El canal '{canal}' no se atiende por /chat: "
                                 "sus mensajes solo entran por el webhook del "
                                 "proveedor."}), 403

    tenant = cuerpo.get("tenant")
    rol = cuerpo.get("rol")
    profile_id = cuerpo.get("profile_id")
    id_sesion = cuerpo.get("identificador_sesion")
    mensaje = cuerpo.get("mensaje")
    # Lo manda la plataforma: el motor no lee las tablas del CRM, asi que
    # quien sabe el nombre de quien inicio sesion es la pantalla.
    nombre_colaborador = (cuerpo.get("nombre_colaborador") or "").strip()

    faltantes = [nombre for nombre, valor in
                {"tenant": tenant, "identificador_sesion": id_sesion,
                 "mensaje": mensaje}.items() if not valor]
    if faltantes:
        return jsonify({"error": f"Faltan campos: {', '.join(faltantes)}"}), 400
    if not rol and not profile_id:
        return jsonify({"error": "Falta 'rol' o 'profile_id'."}), 400

    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    if profile_id:
        try:
            asignados = persistencia.agentes_de_colaborador(tenant, profile_id)
        except Exception as e:
            registrar("agentes", "fallo al resolver los del colaborador",
                      profile_id=profile_id, error=e)
            return jsonify({"error": "No se pudieron resolver los agentes."}), 500
        # Fail-closed: sin asignacion no se atiende. Caer a un agente por
        # defecto seria darle a alguien un acceso que nadie le concedio.
        if not asignados:
            return jsonify({"error": "Todavia no tienes ningun agente asignado. "
                                     "Pidele a un administrador que te asigne "
                                     "al menos uno."}), 403
        try:
            rol, rol_fusionado = fusionar_roles(config, asignados)
        except ValueError as e:
            return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
        # Copia por peticion, no se muta el config cacheado: el rol fusionado
        # existe solo para este turno. Si se registrara en el compartido,
        # apareceria como un agente mas en GET /agentes y en el editor.
        #
        # El override de modelo viaja con el: 'llm.overrides' se indexa por
        # nombre de rol, y el fusionado tiene un nombre que no figura ahi.
        # Sin esto cae en 'modelo_por_defecto', que sigue siendo el modelo
        # local -- y ese ya no corre en ningun lado.
        llm = config.llm
        modelo = modelo_fusionado(config, asignados)
        if modelo:
            llm = llm.model_copy(
                update={"overrides": {**llm.overrides, f"rol:{rol}": modelo}})
        config = config.model_copy(
            update={"roles": {**config.roles, rol: rol_fusionado}, "llm": llm})

    try:
        salida = atender_turno(config, tenant, rol, id_sesion, mensaje, canal,
                               profile_id=profile_id,
                               nombre_colaborador=nombre_colaborador)
    except motor.ErrorMotor as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400

    # 'pausada' solo viaja cuando es cierto: es la forma que ya devolvia /chat
    # antes de que existiera el webhook, y el simulador depende de ella.
    if not salida.get("pausada"):
        salida.pop("pausada", None)
    salida.pop("_autorizacion", None)
    return jsonify(salida)


@app.get("/agentes")
def agentes():
    """
    Solo lectura -- para que una pantalla externa (o quien sea) pueda listar
    que agentes existen y que herramientas tiene cada uno, sin necesitar
    abrir el YAML. No expone nada de sesion ni de datos de clientes.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    salida = [_agente_json(nombre, rol, config) for nombre, rol in config.roles.items()]
    supervisor = _agente_supervisor_json(config)
    if supervisor:
        salida.append(supervisor)
    return jsonify({"tenant": tenant, "agentes": salida})


@app.get("/agentes/catalogo")
def agentes_catalogo():
    """
    Que herramientas existen y que campos ya se declararon para cada una en
    algun rol -- lo que necesita el formulario de crear/editar un agente sin
    inventar nombres de campo a ciegas.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    return jsonify({
        "herramientas": editor.catalogo_herramientas(config),
        "roles_existentes": sorted(config.roles),
        # Cuales de esos roles atienden a un CLIENTE FINAL. Lo usa /manual
        # para avisar antes de darle un documento a uno de ellos: el riesgo
        # real del corpus no es que el filtro por rol falle -- esta en SQL y
        # es fail-closed -- sino que alguien tilde el rol equivocado al
        # subir. Los nombres se parecen ('soporte' es el tecnico en campo,
        # 'soporte_tecnico_cliente' atiende por WhatsApp) y el sistema hace
        # exactamente lo que le dijeron, sin error.
        "roles_de_cliente": sorted(
            n for n, r in config.roles.items() if r.orientado_a == "cliente_final"),
    })


# -----------------------------------------------------------------------------
#  QUE AGENTES PUEDE USAR CADA COLABORADOR
# -----------------------------------------------------------------------------
#  Solo agentes INTERNOS: el de cliente final no se le asigna a un empleado.
#  Ese atiende a un desconocido y verifica identidad; los internos dan por
#  hecho que quien escribe ya esta autorizado y pueden consultar a CUALQUIER
#  cliente. Mezclarlos seria abrirle a una persona datos de terceros por la
#  puerta de al lado -- por eso se filtra aca y se vuelve a validar al guardar.

def _candidatos_externos(config, tenant: str) -> list[dict]:
    """
    La gente del sistema externo a la que se le puede asignar trabajo, sacada
    ejecutando la herramienta que el tenant declaro para eso.

    Se ejecuta la herramienta del catalogo en vez de llamar a una API desde
    aca por lo de siempre: el nucleo no conoce ningun proveedor. El tenant
    dice cual es la herramienta y con que campos viene cada persona.

    Devuelve lista vacia ante cualquier fallo -- la pantalla tiene que poder
    dibujarse igual, ofreciendo lo que ya estaba guardado, aunque el sistema
    externo no conteste.
    """
    cfg = config.identidad_externa
    herramienta = next((h for h in config.herramientas
                        if h.nombre == cfg.herramienta_listado), None)
    if herramienta is None:
        registrar("agentes", "la herramienta de listado no esta en el catalogo",
                  herramienta=cfg.herramienta_listado)
        return []
    try:
        crudo = motor._ejecutar_tool(herramienta, None, {}, tenant,
                                     config.variables_tenant)
    except Exception as e:
        registrar("agentes", "no se pudieron listar los candidatos externos", error=e)
        return []

    filas = crudo.get("results") if isinstance(crudo, dict) else crudo
    if not isinstance(filas, list):
        return []
    salida = []
    for f in filas:
        if not isinstance(f, dict):
            continue
        ident = f.get(cfg.campo_identificador)
        nombre = f.get(cfg.campo_nombre)
        if ident:
            salida.append({"identificador": str(ident),
                           "nombre_visible": str(nombre or ident)})
    return sorted(salida, key=lambda x: x["nombre_visible"])


def _agentes_internos(config) -> list[str]:
    return sorted(n for n, r in config.roles.items()
                  if r.orientado_a == "colaborador")


@app.get("/agentes/asignaciones")
def agentes_asignaciones():
    """
    {profile_id: [agente, ...]} de todo el tenant, mas la lista de agentes
    asignables. La pantalla cruza esto contra los usuarios del CRM, que los
    trae de la API de Django -- el motor no lee las tablas del CRM.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    try:
        asignaciones = persistencia.asignaciones_de_agentes(tenant)
    except Exception as e:
        registrar("agentes", "fallo al listar asignaciones", error=e)
        return jsonify({"error": "No se pudieron leer las asignaciones."}), 500

    # Las identidades ya guardadas y los candidatos posibles viajan con las
    # asignaciones: es una sola pantalla, y pedirlos por separado la obligaria
    # a encadenar tres llamadas para dibujar una fila.
    identidades, candidatos = {}, []
    if config.identidad_externa:
        try:
            identidades = persistencia.identidades_externas(
                tenant, config.identidad_externa.sistema)
        except Exception as e:
            registrar("agentes", "fallo al leer identidades externas", error=e)
        candidatos = _candidatos_externos(config, tenant)

    try:
        areas_por_persona = persistencia.areas_de_colaboradores(tenant)
    except Exception as e:
        registrar("agentes", "fallo al leer areas", error=e)
        areas_por_persona = {}

    return jsonify({"asignaciones": asignaciones,
                    "agentes": _agentes_internos(config),
                    # Las areas declaradas por la empresa, con que agentes
                    # precarga cada una: la pantalla no las conoce de antemano.
                    "areas": [{"nombre": a.nombre, "etiqueta": a.etiqueta,
                               "icono": a.icono, "color": a.color,
                               "agentes": list(a.agentes)} for a in config.areas],
                    "areas_por_persona": areas_por_persona,
                    "sistema_externo": (config.identidad_externa.etiqueta
                                        if config.identidad_externa else None),
                    "identidades": identidades,
                    "candidatos_externos": candidatos})


@app.get("/agentes/areas")
def agentes_areas():
    """
    Las areas de la empresa y de quien es cada persona. Nada mas.

    Existe aparte de /agentes/asignaciones porque las pantallas de tickets
    solo necesitan esto, y aquella ademas lee identidades, agentes y sale a
    buscar candidatos al sistema externo -- una llamada HTTP afuera que esas
    pantallas nunca usan y que igual esperaban. Se hacia notar: abrir un
    ticket tardaba segundos con la pantalla quieta, como si el clic no
    hubiera pasado (28/08/2026).

    Solo lecturas locales, sin salir a ningun sistema externo.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    try:
        areas_por_persona = persistencia.areas_de_colaboradores(tenant)
    except Exception as e:
        registrar("agentes", "fallo al leer areas", error=e)
        areas_por_persona = {}

    return jsonify({"areas": [{"nombre": a.nombre, "etiqueta": a.etiqueta,
                               "icono": a.icono, "color": a.color,
                               "agentes": list(a.agentes)} for a in config.areas],
                    "areas_por_persona": areas_por_persona})


@app.put("/agentes/asignaciones/<profile_id>")
def agentes_asignar(profile_id):
    """
    Deja a este colaborador con EXACTAMENTE los agentes de 'roles'. Una lista
    vacia es valida y significa quitarle el acceso: sin agentes, /chat le
    responde 403 en vez de caer a uno por defecto.
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400

    roles = cuerpo.get("roles")
    if not isinstance(roles, list):
        return jsonify({"error": "'roles' tiene que ser una lista."}), 400

    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    permitidos = set(_agentes_internos(config))
    invalidos = [r for r in roles if r not in permitidos]
    if invalidos:
        # Se nombra el motivo probable en vez de solo "invalido": si alguien
        # intenta asignar el agente de cliente final, el error tiene que
        # explicar por que no se puede, no parecer un typo.
        return jsonify({"error": (
            f"No se puede asignar: {', '.join(sorted(invalidos))}. "
            f"Solo agentes internos ({', '.join(sorted(permitidos))}) -- el "
            f"agente que atiende al cliente final no se le asigna a un "
            f"colaborador.")}), 400

    try:
        guardados = persistencia.asignar_agentes(tenant, profile_id, roles)
    except Exception as e:
        registrar("agentes", "fallo al asignar", profile_id=profile_id, error=e)
        return jsonify({"error": "No se pudieron guardar las asignaciones."}), 500

    # Quien es esta persona en el sistema operativo del tenant. Va en el MISMO
    # PUT que los agentes, y no en un endpoint aparte, porque es la misma
    # decision: cuando alguien da de alta a un colaborador define que puede
    # hacer aca y a nombre de quien se le asigna el trabajo alla. Separarlo en
    # dos llamadas es como se llega a personas creadas a medias.
    #
    # Opcional: si el tenant no declaro un sistema externo, no se toca nada.
    # El area se guarda aparte de los agentes a proposito: es lo que alguien
    # DECIDIO, y los agentes son consecuencia de esa decision mas los ajustes
    # que se le hagan despues. Deducir una de la otra hace que alguien cambie
    # de area sola por haber recibido una capacidad extra.
    if "area" in cuerpo:
        try:
            persistencia.guardar_area_colaborador(
                tenant, profile_id, str(cuerpo.get("area") or ""))
        except Exception as e:
            registrar("agentes", "fallo al guardar el area", profile_id=profile_id, error=e)

    sistema = (config.identidad_externa.sistema
               if config.identidad_externa else None)
    if sistema and "identidad_externa" in cuerpo:
        ident = cuerpo.get("identidad_externa") or {}
        try:
            persistencia.guardar_identidad_externa(
                tenant, profile_id, sistema,
                str(ident.get("identificador") or ""),
                str(ident.get("nombre_visible") or ""))
        except Exception as e:
            # No invalida la asignacion de agentes, que ya se guardo: se avisa
            # y se sigue. Devolver error aca dejaria a quien lo llamo sin saber
            # que la mitad SI quedo hecha.
            registrar("agentes", "fallo al guardar la identidad externa",
                      profile_id=profile_id, error=e)
            return jsonify({"profile_id": profile_id, "roles": guardados,
                            "aviso": "Se guardaron los agentes, pero no la "
                                     "identidad en el sistema externo."})

    return jsonify({"profile_id": profile_id, "roles": guardados})


def _flujo_de(config) -> dict:
    """
    El flujo de derivacion de una config ya cargada. Funcion aparte, y no el
    cuerpo del GET, porque el PUT tambien necesita devolverlo despues de
    guardar -- y ahi el tenant viene en el cuerpo, no en la query, asi que
    llamar al handler del GET fallaba con "falta el parametro 'tenant'".
    """
    deriva = next((h for h in config.herramientas if h.deriva_rol), None)
    destinos = list(deriva.areas_destino) if deriva else []

    # Tres conceptos distintos que es facil confundir en uno solo:
    #
    #   puede_derivar  tiene la herramienta en su catalogo. La tienen TODOS
    #                  los agentes de cara al cliente, tambien los
    #                  especialistas -- para pasarse una conversacion entre
    #                  ellos cuando la primera derivacion no fue la correcta.
    #   es_destino     esta en 'areas_destino': puede RECIBIR conversaciones.
    #   es_entrada     de cara al cliente y NO es destino de nadie: es a donde
    #                  cae un mensaje nuevo. Es el unico que la pantalla no
    #                  ofrece como destino (seria un ciclo hacia la puerta).
    #
    # Confundir 'puede_derivar' con 'es_entrada' deja la pantalla sin ningun
    # candidato que ofrecer, porque los tres derivan.
    agentes = []
    for nombre, rol in config.roles.items():
        if rol.orientado_a != "cliente_final":
            continue          # el flujo de derivacion es del lado del cliente
        agentes.append({
            "nombre": nombre,
            "area": rol.area,
            "cargo": rol.cargo,
            "atiende": rol.atiende,
            "puede_derivar": deriva is not None and deriva.nombre in rol.puede_consultar,
            "es_destino": nombre in destinos,
            "es_entrada": nombre not in destinos,
            "n_herramientas": len(rol.puede_consultar),
        })

    return {
        "herramienta_derivacion": deriva.nombre if deriva else None,
        "entradas": [a["nombre"] for a in agentes if a["es_entrada"]],
        "agentes": agentes,
    }


@app.get("/agentes/flujo")
def agentes_flujo():
    """
    El flujo de derivacion tal como esta hoy: quien es la puerta de entrada,
    que agentes son destino y que atiende cada uno. Es lo que dibuja (y ahora
    edita) la pantalla /agentes/flujo.

    Devuelve TODOS los agentes de cara al cliente, no solo los conectados: la
    pantalla necesita poder ofrecer los sueltos para engancharlos.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404
    return jsonify(_flujo_de(config))


@app.put("/agentes/flujo")
def agentes_flujo_guardar():
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400
    destinos = cuerpo.get("destinos")
    if not isinstance(destinos, list):
        return jsonify({"error": "'destinos' tiene que ser una lista de nombres de agente."}), 400

    try:
        config = editor.guardar_flujo_derivacion(
            tenant, destinos, cuerpo.get("atiende") or {})
    except editor.ErrorEdicion as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except Exception as e:
        return _error_al_guardar(e)

    olvidar_config(tenant)
    return jsonify(_flujo_de(config))


@app.post("/agentes")
def agentes_crear():
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    nombre = cuerpo.get("nombre")
    if not tenant or not nombre:
        return jsonify({"error": "Faltan campos: tenant, nombre"}), 400

    try:
        config = editor.crear_rol(
            tenant, nombre,
            area=cuerpo.get("area"), cargo=cuerpo.get("cargo"),
            descripcion=cuerpo.get("descripcion", ""),
            orientado_a=cuerpo.get("orientado_a", "colaborador"),
            herramientas=cuerpo.get("herramientas", []),
        )
    except editor.ErrorEdicion as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except Exception as e:
        return _error_al_guardar(e)

    olvidar_config(tenant)
    return jsonify({"agente": _agente_json(nombre, config.roles[nombre], config)}), 201


@app.put("/agentes/<nombre>")
def agentes_editar(nombre):
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400

    try:
        config = editor.editar_rol(
            tenant, nombre,
            area=cuerpo.get("area"), cargo=cuerpo.get("cargo"),
            descripcion=cuerpo.get("descripcion", ""),
            orientado_a=cuerpo.get("orientado_a", "colaborador"),
            herramientas=cuerpo.get("herramientas", []),
        )
    except editor.ErrorEdicion as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except Exception as e:
        return _error_al_guardar(e)

    olvidar_config(tenant)
    return jsonify({"agente": _agente_json(nombre, config.roles[nombre], config)})


@app.delete("/agentes/<nombre>")
def agentes_borrar(nombre):
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400

    try:
        editor.borrar_rol(tenant, nombre)
    except editor.ErrorEdicion as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except Exception as e:
        return _error_al_guardar(e)

    olvidar_config(tenant)
    return "", 204


# =============================================================================
#  CONFIGURACION  -  lo que el cliente ajusta sin tocar permisos
# =============================================================================
#  Separado de /agentes a proposito. Ahi se decide QUE PUEDE VER cada rol, que
#  es superficie de seguridad; aca se decide como habla el asistente. Mezclar
#  las dos en una pantalla haria que cambiar el tono se sintiera tan riesgoso
#  como abrirle una herramienta nueva a un area.

@app.get("/reportes/escalamiento")
def reporte_escalamiento():
    """
    Version HTTP de cli/reporte_escalamiento.py -- mismo calculo
    (persistencia.tasa_escalamiento), para que /agentes lo muestre sin pasar
    por la terminal. 'dias' default 7, tope 90 (mas alla el query barre
    demasiada tabla para una carga de pantalla interactiva).
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        dias = int(request.args.get("dias", 7))
    except ValueError:
        return jsonify({"error": "'dias' debe ser un numero."}), 400
    dias = max(1, min(dias, 90))

    try:
        r = persistencia.tasa_escalamiento(tenant, dias)
    except Exception as e:
        registrar("reportes", "fallo al calcular escalamiento", error=e)
        return jsonify({"error": "No se pudo calcular el reporte."}), 500

    return jsonify({"dias": dias, **r})


@app.get("/centro-mando")
def centro_mando():
    """
    Que esta haciendo cada agente ahora mismo, para la pantalla /centro-mando.

    La persistencia entrega hechos (cuantas conversaciones, que herramientas,
    cuanto tardaron, cuales fallaron); el ESTADO se decide aqui, que es donde
    se conocen los roles del tenant. La regla, en este orden:

      error       alguna herramienta suya fallo dentro de la ventana
      procesando  llamo alguna herramienta dentro de la ventana
      atendiendo  tiene conversaciones abiertas, sin actividad en la ventana
      disponible  no tiene conversaciones abiertas

    'esperando humano' NO es un estado: es una cifra aparte que viaja siempre
    ('esperando_humano'). Se probo como estado y tapaba lo otro -- un agente
    con una escalada de hace dos horas y tres conversaciones en curso se veia
    detenido, que es justo lo contrario de lo que pasaba. El estado dice que
    hace el agente; la cifra dice que necesita una persona, y la pantalla
    muestra las dos cosas.

    Ninguna de estas cifras es una estimacion del modelo: todas salen de
    contar filas (PRD 12.5, el codigo calcula). Y no viaja contenido de
    conversaciones -- ver panorama_centro_mando() en persistencia.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    try:
        ventana = int(request.args.get("ventana", 10))
    except ValueError:
        return jsonify({"error": "'ventana' debe ser un numero."}), 400
    # Tope de 120: mas alla deja de ser "ahora mismo" y la pantalla miente.
    ventana = max(1, min(ventana, 120))

    try:
        datos = persistencia.panorama_centro_mando(tenant, ventana)
    except Exception as e:
        registrar("centro_mando", "fallo al calcular el panorama", error=e)
        return jsonify({"error": "No se pudo calcular el panorama."}), 500

    def _estado(carga: dict, act: dict) -> str:
        if (act.get("fallos") or 0) > 0:
            return "error"
        if (act.get("llamadas") or 0) > 0:
            return "procesando"
        if (carga.get("conversaciones") or 0) > 0:
            return "atendiendo"
        return "disponible"

    agentes = []
    for nombre, rol in config.roles.items():
        carga = datos["carga"].get(nombre, {})
        act = datos["actividad"].get(nombre, {})
        ultima = carga.get("ultima_actividad") or act.get("ultima_llamada")
        agentes.append({
            "nombre": nombre,
            "descripcion": rol.descripcion.strip(),
            "area": rol.area,
            "cargo": rol.cargo,
            "orientado_a": rol.orientado_a,
            "estado": _estado(carga, act),
            "conversaciones": carga.get("conversaciones") or 0,
            "abiertas_total": carga.get("abiertas_total") or 0,
            "esperando_humano": carga.get("esperando_humano") or 0,
            "recibidas_hoy": carga.get("recibidas_hoy") or 0,
            "llamadas_ventana": act.get("llamadas") or 0,
            "fallos_ventana": act.get("fallos") or 0,
            "duracion_media_ms": act.get("duracion_media_ms"),
            "ultima_herramienta": act.get("ultima_herramienta"),
            "ultima_actividad": ultima.isoformat() if ultima else None,
        })
    agentes.sort(key=lambda a: a["nombre"])

    # Un solo ticker ordenado: la pantalla no tiene por que saber que estos
    # eventos vienen de dos tablas distintas.
    eventos = []
    for e in datos["eventos_herramienta"]:
        ms = e.get("duracion_ms")
        eventos.append({
            "en": e["creado_en"].isoformat(),
            "agente": e["agente"],
            "tipo": "herramienta_fallida" if not e["exito"] else (
                "accion" if e["es_escritura"] else "consulta"),
            "herramienta": e["herramienta"],
            "duracion_ms": ms,
        })
    for e in datos["eventos_escalada"]:
        eventos.append({
            "en": e["creado_en"].isoformat(),
            "agente": e["agente"],
            "tipo": "escalada",
            "motivo": e.get("motivo_escalamiento"),
        })
    eventos.sort(key=lambda x: x["en"], reverse=True)

    t = datos["totales"]
    return jsonify({
        "tenant": tenant,
        "generado_en": datetime.now(timezone.utc).isoformat(),
        "ventana_min": datos["ventana_min"],
        "totales": {
            "conversaciones_activas": t.get("conversaciones_activas") or 0,
            "abiertas_total": t.get("abiertas_total") or 0,
            "esperando_humano": t.get("esperando_humano") or 0,
            "atendidas_hoy": t.get("atendidas_hoy") or 0,
            "herramientas_hoy": t.get("herramientas_hoy") or 0,
            "duracion_media_ms": t.get("duracion_media_ms"),
            "fallos_hoy": t.get("fallos_hoy") or 0,
            "agentes_activos": sum(
                1 for a in agentes if a["estado"] in ("procesando", "atendiendo")),
        },
        "agentes": agentes,
        "eventos": eventos[:20],
    })


@app.get("/configuracion")
def configuracion():
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    return jsonify({
        "persona": config.persona.model_dump(mode="json"),
        # 'descripcion' es lo unico de 'identidad' que se edita desde esta
        # pantalla (que servicios/planes ofrece la empresa, para el prompt);
        # el resto (nombre legal, slug) se define al dar de alta el tenant.
        "identidad": {"descripcion": config.identidad.descripcion,
                      "nombre_comercial": config.identidad.nombre_comercial},
        # Solo existe si la herramienta 'agendar_visita_tecnica' esta en el
        # catalogo -- None en cualquier tenant que no la tenga, para que la
        # pantalla sepa si mostrar el campo o no.
        "plazo_visita_tecnica": next(
            (h.fechas_automaticas.get("fecha_final")
             for h in config.herramientas if h.nombre == "agendar_visita_tecnica"),
            None),
        # Contexto de solo lectura para la pantalla: el modelo y cuantos
        # agentes hay se deciden en otro lado, pero quien ajusta el tono
        # merece verlos sin abrir otra pestana.
        "modelo": config.llm.modelo_por_defecto,
        "roles": sorted(config.roles),
    })


@app.put("/configuracion/persona")
def configuracion_persona():
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400

    try:
        config = editor.guardar_persona(
            tenant,
            nombre_asistente=cuerpo.get("nombre_asistente", ""),
            tono=cuerpo.get("tono", "cercano"),
            longitud_respuesta=cuerpo.get("longitud_respuesta", "breve"),
            instrucciones_adicionales=cuerpo.get("instrucciones_adicionales", ""),
        )
    except editor.ErrorEdicion as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except Exception as e:
        return _error_al_guardar(e)

    olvidar_config(tenant)
    return jsonify({"persona": config.persona.model_dump(mode="json")})


@app.put("/configuracion/identidad")
def configuracion_identidad():
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400

    try:
        config = editor.guardar_identidad_descripcion(
            tenant, descripcion=cuerpo.get("descripcion", ""))
    except editor.ErrorEdicion as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except Exception as e:
        return _error_al_guardar(e)

    olvidar_config(tenant)
    return jsonify({"descripcion": config.identidad.descripcion})


@app.put("/configuracion/plazo-visita-tecnica")
def configuracion_plazo_visita_tecnica():
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400

    try:
        dias = int(cuerpo.get("dias"))
    except (TypeError, ValueError):
        return jsonify({"error": "'dias' tiene que ser un numero entero."}), 400

    try:
        config = editor.guardar_plazo_visita_tecnica(tenant, dias)
    except editor.ErrorEdicion as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except Exception as e:
        return _error_al_guardar(e)

    olvidar_config(tenant)
    herramienta = next(h for h in config.herramientas if h.nombre == "agendar_visita_tecnica")
    return jsonify({"dias": herramienta.fechas_automaticas.get("fecha_final")})


@app.get("/configuracion/bandeja")
def configuracion_bandeja():
    """Los dos ajustes de la Bandeja, para la pantalla de configuracion."""
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404
    return jsonify({
        "sla_toma_minutos": getattr(config, "sla_toma_minutos", 0) or 0,
        "umbral_rx_dbm": getattr(config, "umbral_rx_dbm", None),
    })


@app.put("/configuracion/bandeja")
def configuracion_bandeja_guardar():
    """
    Cambia los dos numeros con los que la Bandeja emite un veredicto.

    Los DOS admiten "sin definir" -- 0 y null-- y eso no es un hueco: es la
    manera de decir que la empresa todavia no lo decidio, y entonces la
    pantalla muestra el dato crudo sin afirmar si esta bien o mal.
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400

    try:
        sla = int(cuerpo.get("sla_toma_minutos") or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "'sla_toma_minutos' tiene que ser un numero entero."}), 400

    crudo = cuerpo.get("umbral_rx_dbm")
    umbral = None
    if crudo not in (None, ""):
        try:
            umbral = float(crudo)
        except (TypeError, ValueError):
            return jsonify({"error": "'umbral_rx_dbm' tiene que ser un numero."}), 400

    try:
        config = editor.guardar_ajustes_bandeja(tenant, sla, umbral)
    except editor.ErrorEdicion as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except Exception as e:
        return _error_al_guardar(e)

    olvidar_config(tenant)
    return jsonify({
        "sla_toma_minutos": getattr(config, "sla_toma_minutos", 0) or 0,
        "umbral_rx_dbm": getattr(config, "umbral_rx_dbm", None),
    })


@app.get("/configuracion/canales")
def configuracion_canales():
    """
    Estado del canal de WhatsApp para la pantalla de ajustes: si esta activo,
    los NOMBRES de los secretos que declara (nunca sus valores -- esos se
    consultan aparte en /secretos) y que plantillas tiene mapeadas.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    w = config.canales.whatsapp
    # SmartOLT no es un 'canal' propiamente (no es un medio de contacto con el
    # cliente), pero vive en el mismo endpoint por lo mismo que ping_cliente
    # vive en el catalogo de WispHub: es la unica integracion externa nueva y
    # no amerita todavia una seccion propia en el schema.
    #
    # 'subdominio' se resuelve desde 'variables_tenant' via 'base_url_ref'
    # (no desde 'base_url' -- este software es SaaS multi-tenant, el dominio
    # varia por empresa y tiene que poder cargarse desde esta pantalla, no
    # quedar fijo en un YAML que solo un desarrollador edita. Ver
    # 'base_url_ref' en nucleo/config/schema.py y PUT /configuracion/variables).
    smartolt_tool = next((h for h in config.herramientas
                         if h.nombre == "consultar_estado_ont"), None)
    return jsonify({"whatsapp": {
        # El slug tal cual se lo paso quien llamo -- es el mismo valor con el
        # que se arma la URL del webhook (/canales/whatsapp/<tenant_slug>), y
        # la pantalla de ajustes lo necesita para armar esa URL sin adivinar.
        "tenant_slug": tenant,
        "activo": w.activo,
        "version_api": w.version_api,
        "numero_visible": w.numero_visible,
        "plantillas": w.plantillas,
        # Los NOMBRES declarados -- la pantalla cruza esto contra /secretos
        # para saber cuales de los cuatro indispensables ya tienen un valor.
        "refs": {
            "phone_number_id": w.phone_number_id_ref,
            "token": w.token_ref,
            "waba_id": w.waba_id_ref,
            "app_secret": w.app_secret_ref,
            "verify_token": w.verify_token_ref,
        },
    }, "smartolt": {
        "instalado": smartolt_tool is not None,
        "subdominio_ref": smartolt_tool.base_url_ref if smartolt_tool else None,
        "subdominio": (config.variables_tenant.get(smartolt_tool.base_url_ref)
                       if smartolt_tool and smartolt_tool.base_url_ref else None),
        "ref_clave": smartolt_tool.auth_ref if smartolt_tool else None,
    }})


@app.put("/configuracion/canales/whatsapp")
def configuracion_canal_whatsapp():
    """
    Prender/apagar el canal y el numero visible. Los valores de las
    credenciales NO pasan por aca -- ver POST /secretos.
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400

    try:
        config = editor.guardar_canal_whatsapp(
            tenant, activo=bool(cuerpo.get("activo", False)),
            numero_visible=cuerpo.get("numero_visible") or None)
    except editor.ErrorEdicion as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except Exception as e:
        return _error_al_guardar(e)

    olvidar_config(tenant)
    w = config.canales.whatsapp
    return jsonify({"activo": w.activo, "numero_visible": w.numero_visible})


@app.get("/configuracion/variables")
def configuracion_variables_listar():
    """
    Las variables del tenant, para que una pantalla pueda MOSTRAR lo que hay
    cargado antes de dejar cambiarlo.

    Habia PUT y DELETE pero no lectura, asi que cualquier pantalla que quisiera
    mostrar el valor actual tenia que adivinarlo o dejar el campo vacio. Se
    noto el 02/09/2026 armando Ajustes -> Instalaciones: los cuatro campos
    salian en blanco aunque estuvieran configurados.

    No son secretos -- eso vive en /secretos, cifrado. Aca hay dominios, ids de
    cuenta y nombres de equipo: datos de la empresa que se editan desde la
    interfaz (ver TenantConfig.variables_tenant en schema.py).
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        config = _config_de(tenant)
    except Exception as e:
        return fallo(500, "config_no_cargada", "No se pudo cargar la configuracion.",
                     componente="configuracion", e=e)
    return jsonify({"variables": dict(config.variables_tenant or {})})


@app.put("/configuracion/variables/<nombre>")
def configuracion_variable_guardar(nombre):
    """
    Guarda un valor NO secreto que varia por empresa (ej. el subdominio de
    SmartOLT) -- ver TenantConfig.variables_tenant en schema.py. Generico a
    proposito: cualquier 'Herramienta.base_url_ref' futuro usa este mismo
    endpoint, este archivo no necesita saber que integracion es cada una.
    Distinto de /secretos: esto se guarda en texto plano en la config del
    tenant (no cifrado) porque no es sensible -- un subdominio no es una
    credencial.
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400
    valor = cuerpo.get("valor")
    if not valor:
        return jsonify({"error": "Falta el campo 'valor'"}), 400

    try:
        config = editor.guardar_variable_tenant(tenant, nombre, valor)
    except editor.ErrorEdicion as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except Exception as e:
        return _error_al_guardar(e)

    olvidar_config(tenant)
    return jsonify({"nombre": nombre, "valor": config.variables_tenant.get(nombre)})


@app.delete("/configuracion/variables/<nombre>")
def configuracion_variable_borrar(nombre):
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400

    try:
        editor.borrar_variable_tenant(tenant, nombre)
    except editor.ErrorEdicion as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except Exception as e:
        return _error_al_guardar(e)

    olvidar_config(tenant)
    return jsonify({"borrado": nombre})


@app.post("/interno/herramienta/<nombre>")
def interno_ejecutar_herramienta(nombre: str):
    """
    Ejecuta una herramienta del catalogo a pedido de OTRO servicio del
    despliegue -- no de un modelo y no de una persona.

    Por que existe: la credencial de WispHub vive solo en el motor. El backend
    del CRM tambien necesita crear un ticket ahi cuando alguien envia una
    solicitud de contratacion, y la alternativa era copiarle la clave. Dos
    servicios con la misma credencial es lo que despues se desincroniza sin
    que nadie sepa cual es la buena.

    Tres capas, y ninguna sobra:

      1. El token de servicio, que ya exige _exigir_token_de_servicio() para
         toda ruta interna.
      2. 'invocable_por_servicio' en la herramienta. Por defecto es False, asi
         que esta ruta no expone "cualquier herramienta" sino las que alguien
         declaro una por una. Sin esto, quien tuviera el token podria
         ejecutar 'reiniciar_ont' sobre el cliente que se le ocurriera.
      3. Sin sesion. Se pasa sesion=None a proposito: ninguna herramienta que
         dependa de una identidad verificada puede funcionar por aca, porque
         del otro lado no hay nadie a quien verificar.

    Los argumentos pasan por el MISMO _resolver_argumentos que usa el modelo
    -- traduccion de filtros verificados fail-closed incluida. Un servicio
    interno no tiene mas permisos que el modelo para inventar parametros.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        config = _config_de(tenant)
    except Exception as e:
        return fallo(500, "config_no_cargada", "No se pudo cargar la configuracion.",
                     componente="interno", e=e)

    herramienta = next((h for h in config.herramientas if h.nombre == nombre), None)
    if herramienta is None:
        return jsonify({"error": f"No existe la herramienta '{nombre}'."}), 404
    if not herramienta.invocable_por_servicio:
        return jsonify({
            "error": f"'{nombre}' no esta declarada como invocable por un "
                     f"servicio. Se declara con 'invocable_por_servicio: true' "
                     f"en la config del tenant."}), 403

    argumentos = request.get_json(silent=True) or {}
    if not isinstance(argumentos, dict):
        return jsonify({"error": "El cuerpo tiene que ser un objeto JSON."}), 400

    # La cabecera es el unico identificador ESTABLE que puede aportar quien
    # llama: si reenvia la misma peticion con la misma clave, la mutacion no
    # sale dos veces (ver nucleo/seguridad/idempotencia.py). Se aceptan los dos
    # nombres por la misma razon que campo/services/idempotencia.py los acepta.
    # Sin cabecera se ejecuta igual, como siempre -- no se rompe a ningun
    # llamador existente -- pero un reenvio no se reconoce.
    clave_idem = (request.headers.get("Idempotency-Key")
                  or request.headers.get("X-Idempotency-Key") or "").strip()
    try:
        salida = motor.ejecutar_para_servicio(
            config, herramienta, argumentos,
            origen=f"idem:{clave_idem}" if clave_idem else None)
    except motor.AutonomiaDetenida as e:
        # 409 y no 500: la peticion estaba bien, el sistema decidio no
        # ejecutarla. Quien llama tiene que poder distinguir "fallo" de "no se
        # hizo a proposito", porque la reaccion correcta no es la misma.
        #  M06-F: el motivo va al log, no a la respuesta (regla de origin,
        #  tests/test_errores_http.py): la respuesta lleva un codigo fijo.
        registrar("interno", "accion bloqueada por el interruptor",
                  herramienta=nombre, error=e)
        return jsonify({"error": "AUTONOMIA_DETENIDA",
                        "detalle": "Las acciones automaticas de esta empresa "
                                   "estan detenidas."}), 409
    except motor.OperacionNoEjecutada as e:
        registrar("interno", "operacion externa no ejecutada",
                  herramienta=nombre, error=e)
        codigo = e.resultado.codigo           # una constante de idempotencia.py
        return jsonify({"error": codigo,
                        "detalle": "La operacion no se ejecuto: el registro de "
                                   "operaciones externas lo impidio."}), 409
    except Exception as e:
        return fallo(502, "herramienta_fallo", "La herramienta no pudo completarse.",
                     componente="interno", e=e, estado_proveedor=estado_http_de(e))

    return jsonify({"resultado": salida})


@app.get("/autonomia")
def autonomia_estado():
    """
    El estado del interruptor de autonomia de una empresa, y su historial.

    Solo lectura, y a proposito NO carga la configuracion del tenant: el
    interruptor tiene que poder consultarse aunque la config este rota, que es
    justo uno de los momentos en que alguien querria tirarlo.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        veredicto = interruptor.veredicto(tenant)
        historial = interruptor.historial(tenant, limite=20)
    except Exception as e:
        return fallo(500, "autonomia_no_legible",
                     "No se pudo leer el interruptor de autonomia.",
                     componente="autonomia", e=e)
    return jsonify({
        "estado": veredicto.estado,
        "permitido": veredicto.permitido,
        "motivo": veredicto.motivo,
        "actor": veredicto.actor,
        "historial": [
            {"estado": h["estado"], "estado_anterior": h["estado_anterior"],
             "actor": h["actor"], "motivo": h["motivo"],
             "creado_en": h["creado_en"].isoformat() if h["creado_en"] else None}
            for h in historial],
    })


@app.post("/autonomia/detener")
def autonomia_detener():
    """
    Tira el interruptor: esta empresa deja de ejecutar acciones autonomas.

    Cuerpo: {"actor": "...", "motivo": "..."}. Los dos obligatorios -- una
    parada de emergencia sin nombre ni razon es la que despues nadie se anima a
    levantar porque no sabe que estaba pasando.

    Quien puede llamarla: esta ruta esta detras de _exigir_token_de_servicio()
    como todas las internas, y del lado de la app web el gate de ADMIN es el
    mismo que ya usan /agentes y /configuracion-guiada. NO es una ruta publica.
    """
    return _mover_autonomia(interruptor.detener)


@app.post("/autonomia/reactivar")
def autonomia_reactivar():
    """Levanta el interruptor. Mismo cuerpo y mismos requisitos que detener."""
    return _mover_autonomia(interruptor.reactivar)


def _mover_autonomia(accion):
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    cuerpo = request.get_json(silent=True) or {}
    try:
        fila = accion(tenant, (cuerpo.get("actor") or "").strip(),
                      (cuerpo.get("motivo") or "").strip())
    except ValueError as e:
        # Falta el actor o el motivo: es un pedido incompleto, no una falla.
        return jsonify({"error": mensaje_publico(
            e, "Hacen falta el actor y el motivo.")}), 400
    except Exception as e:
        return fallo(500, "autonomia_no_movida",
                     "No se pudo cambiar el interruptor de autonomia.",
                     componente="autonomia", e=e)
    return jsonify({
        "estado": fila["estado"], "estado_anterior": fila["estado_anterior"],
        "actor": fila["actor"], "motivo": fila["motivo"],
        "creado_en": fila["creado_en"].isoformat() if fila["creado_en"] else None,
    })


@app.get("/configuracion/planes-venta")
def configuracion_planes_venta_listar():
    """
    Para la pantalla que arma la lista curada de planes que 'ventas' ofrece
    a un prospecto -- ver PlanVenta/TenantConfig.planes_venta en schema.py.

    Trae DOS cosas: la lista curada que ya esta guardada (siempre), y el
    catalogo TECNICO completo de WispHub EN VIVO -- solo si se pide con
    '?catalogo=1'. Nunca cacheado (a diferencia de como usa este mismo
    endpoint el asistente en una conversacion): quien esta configurando
    necesita ver el catalogo mas actual, no uno de hasta 7 dias de
    antiguedad. El llamado a WispHub queda OPCIONAL para que el hub de
    configuracion (que solo necesita el conteo de planes ya curados, para
    mostrar "3 planes ofrecidos" sin abrir la pantalla) no pague ese
    viaje de red en cada carga de /settings.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    catalogo: list[dict] = []
    error_catalogo = None
    if request.args.get("catalogo") == "1":
        herramienta = next((h for h in config.herramientas if h.nombre == "consultar_planes"), None)
        if herramienta is None:
            error_catalogo = "Este agente no tiene 'consultar_planes' en su catalogo."
        else:
            try:
                crudo = ejecutor_http.ejecutar(herramienta, {}, tenant, config.variables_tenant)
                resultados = crudo.get("results", crudo) if isinstance(crudo, dict) else crudo
                catalogo = [{"id": r.get("id"), "nombre": r.get("nombre")}
                           for r in (resultados or []) if isinstance(r, dict)]
            except Exception as e:
                error_catalogo = f"No se pudo consultar el catalogo real: {type(e).__name__}: {e}"

    return jsonify({
        "catalogo": catalogo,
        "error_catalogo": error_catalogo,
        "planes_venta": [p.model_dump(mode="json") for p in config.planes_venta],
        "localidades": [l.model_dump(mode="json") for l in config.localidades],
        "localidades_actualizado_en": config.localidades_actualizado_en,
    })


@app.get("/configuracion/oferta")
def configuracion_oferta_listar():
    """
    Que vende la empresa y que canales trae la TV -- las dos cosas que el
    agente no podia saber y terminaba improvisando (ver ServicioOfrecido en
    schema.py sobre la falla del 08/09/2026).

    Van juntas en un endpoint porque se editan en la misma pantalla y
    ninguna de las dos justifica un viaje propio: las dos salen de config
    que ya esta en memoria, sin red.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    return jsonify({
        "servicios_ofrecidos": [s.model_dump(mode="json")
                                for s in config.servicios_ofrecidos],
        "parrilla_canales": [c.nombre for c in config.parrilla_canales],
    })


@app.get("/configuracion/guias-tv")
def configuracion_guias_tv_listar():
    """
    Las guias de sintonizacion, para administrarlas.

    A DIFERENCIA de lo que ve el agente, esto SI devuelve 'observaciones':
    son notas de quien administra el catalogo ("confirmado con el tecnico",
    "solo modelos posteriores a 2019") y quien edita tiene que verlas. Lo que
    nunca las entrega es la resolucion que consume el modelo -- ver
    _ejecutar_consulta_guia_tv en motor.py.

    Se devuelven TODAS, activas y apagadas: una guia apagada es un borrador o
    una version vieja que alguien quiere poder volver a encender, y una
    pantalla que solo muestra las activas la vuelve invisible.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    return jsonify({
        "guias_tv": [g.model_dump(mode="json") for g in config.guias_tv],
        # Que la pantalla no tenga que conocer las reglas de negocio para
        # dibujar su formulario: los dos valores validos salen de aca.
        "tipos_conexion": ["directo", "tdt"],
    })


@app.post("/configuracion/guias-tv")
def configuracion_guias_tv_guardar():
    """
    Reemplaza el catalogo entero con lo que manda la pantalla.

    Las reglas -- TDT sin marca, una sola activa por marca y conexion, activa
    con instrucciones-- las hace cumplir el SCHEMA al validar, no este
    endpoint. Si alguna no se cumple, _editar hace rollback y el motivo vuelve
    tal cual para mostrarlo en el formulario.
    """
    cuerpo = request.json or {}
    tenant = cuerpo.get("tenant")
    guias = cuerpo.get("guias")
    if not tenant or not isinstance(guias, list):
        return jsonify({"error": "Falta 'tenant' o 'guias'."}), 400
    try:
        config = editor.guardar_guias_tv(tenant, guias)
    except editor.ErrorEdicion as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    return jsonify({"guias_tv": [g.model_dump(mode="json")
                                 for g in config.guias_tv]})


@app.post("/configuracion/servicios")
def configuracion_servicios_guardar():
    tenant = (request.json or {}).get("tenant")
    servicios = (request.json or {}).get("servicios")
    if not tenant or not isinstance(servicios, list):
        return jsonify({"error": "Falta 'tenant' o 'servicios'."}), 400
    try:
        config = editor.guardar_servicios_ofrecidos(tenant, servicios)
    except editor.ErrorEdicion as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    return jsonify({"servicios_ofrecidos": [s.model_dump(mode="json")
                                           for s in config.servicios_ofrecidos]})


@app.post("/configuracion/parrilla")
def configuracion_parrilla_guardar():
    """
    Sube la parrilla desde un Excel de UNA columna. Reemplaza la lista
    entera: la parrilla es lo que dice el archivo que se subio, y mezclarla
    con la anterior deja canales fantasma de una version que nadie recuerda.

    Devuelve los canales cargados Y los descartados por duplicados. Lo
    segundo no es un detalle: sin verlo, quien sube el archivo cree que
    cargo mas de lo que cargo.
    """
    tenant = request.form.get("tenant")
    archivo = request.files.get("archivo")
    if not tenant or archivo is None:
        return jsonify({"error": "Falta 'tenant' o el archivo."}), 400
    try:
        canales, descartados = editor.canales_desde_excel(archivo.read())
        editor.guardar_parrilla_canales(tenant, canales)
    except editor.ErrorEdicion as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    return jsonify({"parrilla_canales": canales, "descartados": descartados,
                    "total": len(canales)})


@app.post("/configuracion/localidades/sincronizar")
def configuracion_localidades_sincronizar():
    """
    Recorre el catalogo de clientes del proveedor entero (paginado, ver
    nucleo/herramientas/localidades.py) y reemplaza TenantConfig.localidades
    -- el catalogo localidad -> zona(s) real(es) que 'ventas' usa para
    resolver cobertura y planes sin pegarle a la API en cada mensaje.

    Puede tardar 60-90s en una base de miles de clientes (paginas
    secuenciales) -- es una accion de administrador bajo demanda desde
    /settings/planes-venta, nunca participa de una conversacion.
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400
    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    herramienta = next((h for h in config.herramientas if h.sincroniza_localidades), None)
    if herramienta is None:
        return jsonify({"error": "Este agente no tiene ninguna herramienta "
                                 "marcada 'sincroniza_localidades'."}), 400

    try:
        localidades = sincronizador_localidades.sincronizar(
            herramienta, tenant, config.variables_tenant)
    except Exception as e:
        # D19: antes devolvia el texto del proveedor tal cual. Queda su codigo
        # HTTP, que es lo que dice si fue una clave, una ruta o una caida.
        return fallo(502, "proveedor_no_sincronizo",
                     "No se pudieron sincronizar las localidades con el proveedor.",
                     componente="localidades", e=e, estado_proveedor=estado_http_de(e))

    try:
        nuevo = editor.guardar_localidades(
            tenant, [l.model_dump(mode="json") for l in localidades])
    except editor.ErrorEdicion as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except Exception as e:
        return _error_al_guardar(e)

    olvidar_config(tenant)
    return jsonify({
        "localidades": [l.model_dump(mode="json") for l in nuevo.localidades],
        "localidades_actualizado_en": nuevo.localidades_actualizado_en,
    })


@app.put("/configuracion/planes-venta")
def configuracion_planes_venta_guardar():
    """Reemplaza entera la lista curada -- ver editor.guardar_planes_venta:
    la pantalla manda el estado completo de los checkboxes en cada
    guardado, asi que no hace falta (ni conviene) un merge incremental."""
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400
    planes = cuerpo.get("planes")
    if planes is None or not isinstance(planes, list):
        return jsonify({"error": "Falta el campo 'planes' (lista)."}), 400

    try:
        config = editor.guardar_planes_venta(tenant, planes)
    except editor.ErrorEdicion as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except Exception as e:
        return _error_al_guardar(e)

    olvidar_config(tenant)
    return jsonify({"planes_venta": [p.model_dump(mode="json") for p in config.planes_venta]})


# =============================================================================
#  SECRETOS  -  credenciales por empresa (WhatsApp, WispHub...), cifradas
# =============================================================================
#  Nunca se devuelve un valor. Ver nucleo/seguridad/secretos.py: la pantalla
#  de ajustes solo necesita saber SI algo esta cargado (pista + fecha), no QUE
#  es. Distinto del resto de este archivo, que sirve datos de negocio: aca lo
#  que se sirve es metadata de una llave, nunca la llave.

@app.get("/secretos")
def secretos_listar():
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        return jsonify({"secretos": secretos.listar(tenant)})
    except secretos.ErrorSecreto as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 500
    except Exception as e:
        registrar("secretos", "fallo al listar", error=e)
        return jsonify({"error": "No se pudieron leer los secretos."}), 500


@app.get("/configuracion/credenciales")
def configuracion_credenciales():
    """
    Que credenciales necesita esta empresa, y cuales ya estan cargadas.

    La lista NO es fija: se arma leyendo los 'auth_ref' que declara el catalogo
    de herramientas del tenant. Por eso sirve para el ISP numero dos sin que
    nadie toque codigo -- si su config declara 'OTRO_PROVEEDOR_API_KEY', la
    pantalla se lo pide sola.

    Existe porque hasta ahora cargar un secreto nuevo obligaba a entrar al
    contenedor: el endpoint '/secretos' siempre fue generico, pero las unicas
    pantallas que lo llamaban estaban cableadas a WhatsApp y a SmartOLT. Dar de
    alta una empresa no puede depender de una sesion de consola.

    Nunca devuelve valores. De cada secreto cargado salen el nombre, para que
    sirve, cuando se cargo y una pista de los ultimos caracteres -- lo que
    'secretos.listar' ya expone.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    # Quien usa cada credencial. Se muestra para que quien la carga entienda
    # que se rompe si falta, en vez de ver una lista de nombres sueltos.
    usos: dict[str, list[str]] = {}
    for h in config.herramientas:
        if h.auth_ref:
            usos.setdefault(h.auth_ref, []).append(h.nombre)
    for atributo in ("token_ref", "verify_token_ref", "app_secret_ref"):
        for h in config.herramientas:
            ref = getattr(h, atributo, None)
            if ref:
                usos.setdefault(ref, []).append(h.nombre)

    try:
        cargados = {s["nombre"]: s for s in secretos.listar(tenant)}
    except Exception as e:
        registrar("credenciales", "no se pudieron leer los secretos", error=e)
        cargados = {}

    # Los declarados por el catalogo, mas los que ya estan cargados aunque
    # ninguna herramienta los pida: un secreto huerfano es informacion util
    # -- puede ser de una integracion que se saco y quedo la credencial viva.
    salida = []
    for nombre in sorted(set(usos) | set(cargados)):
        s = cargados.get(nombre) or {}
        salida.append({
            "nombre": nombre,
            "cargado": nombre in cargados,
            "declarado": nombre in usos,
            "herramientas": sorted(usos.get(nombre, []))[:12],
            "cantidad_herramientas": len(usos.get(nombre, [])),
            "descripcion": s.get("descripcion") or "",
            "pista": s.get("pista") or "",
            "actualizado_en": s.get("actualizado_en").isoformat()
            if s.get("actualizado_en") else None,
        })
    return jsonify({"credenciales": salida})


@app.post("/secretos")
def secretos_guardar():
    """
    Cifra y guarda (o actualiza) un secreto de la empresa.

    'nombre' llega libre y no contra una lista cerrada a proposito: este
    endpoint es generico (sirve para WHATSAPP_* y para cualquier otro
    auth_ref que declare una Herramienta, ej. WISPHUB_API_KEY). Lo que decide
    QUE secretos hacen falta es la configuracion del tenant, no este archivo.
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    nombre = (cuerpo.get("nombre") or "").strip()
    valor = cuerpo.get("valor") or ""
    if not tenant or not nombre:
        return jsonify({"error": "Faltan campos: tenant, nombre"}), 400

    try:
        secretos.guardar(tenant, nombre, valor, cuerpo.get("descripcion"))
    except secretos.ErrorSecreto as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except Exception as e:
        registrar("secretos", "fallo al guardar", nombre=nombre, error=e)
        return jsonify({"error": "No se pudo guardar el secreto."}), 500

    return jsonify({"ok": True})


@app.delete("/secretos/<nombre>")
def secretos_borrar(nombre):
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant") or request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400

    try:
        borrado = secretos.borrar(tenant, nombre)
    except Exception as e:
        registrar("secretos", "fallo al borrar", nombre=nombre, error=e)
        return jsonify({"error": "No se pudo borrar el secreto."}), 500

    return jsonify({"borrado": borrado})


# =============================================================================
#  DIAGNOSTICO DE INTEGRACIONES  -  probar credenciales antes de guardarlas
# =============================================================================

@app.post("/diagnostico/smartolt")
def diagnostico_smartolt():
    """
    Prueba de conectividad de solo lectura contra SmartOLT, con lo que la
    persona acaba de pegar en la pantalla de ajustes -- ANTES de guardarlo
    como secreto/variable, para poder corregir un dato mal pegado sin
    round-trip.

    El endpoint (GET /api/onu/get_all_onus_details) y el header (X-Token,
    no Authorization) quedaron CONFIRMADOS en vivo contra la instancia real
    de Rapilink -- ver .claude/skills/smartolt-api/SKILL.md. No se usa
    'get_olts' para esto pese a ser mas liviano: el proveedor pide
    explicitamente no usarlo como heartbeat/chequeo de conexion (misma
    skill).
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    base_url = (cuerpo.get("base_url") or "").strip().rstrip("/")
    api_key = (cuerpo.get("api_key") or "").strip()
    if not base_url or not api_key:
        return jsonify({"error": "Faltan campos: base_url, api_key"}), 400

    import requests

    try:
        r = requests.get(f"{base_url}/api/onu/get_all_onus_details",
                         headers={"X-Token": api_key}, timeout=10)
    except requests.exceptions.SSLError:
        return jsonify({"ok": False, "detalle": "El dominio no tiene HTTPS valido -- revisa la URL."})
    except requests.exceptions.ConnectionError:
        return jsonify({"ok": False, "detalle": "No se pudo conectar -- revisa el subdominio."})
    except requests.exceptions.Timeout:
        return jsonify({"ok": False, "detalle": "El servidor no respondio a tiempo."})
    except Exception as e:
        registrar("diagnostico", "fallo inesperado al probar la conexion", error=e)
        return jsonify({"ok": False, "codigo": "fallo_inesperado",
                        "detalle": "No se pudo probar la conexion por un error inesperado."})

    if r.status_code == 200:
        try:
            cuerpo_resp = r.json()
        except ValueError:
            return jsonify({"ok": False, "detalle": "Respondio 200 pero sin JSON -- "
                             "revisar si la ruta es la correcta."})
        # SIN 'muestra' con los registros crudos: get_all_onus_details trae
        # nombre y direccion del cliente por ONU (ver tabla de riesgo en la
        # skill smartolt-api) -- un chequeo de conexion no tiene que devolver
        # datos de clientes al navegador. La cantidad alcanza para confirmar
        # que la clave sirve.
        cantidad = len(cuerpo_resp) if isinstance(cuerpo_resp, list) else 1
        return jsonify({"ok": True,
                        "detalle": f"Conexion correcta -- {cantidad} ONU(s) visibles con esta clave."})
    if r.status_code in (401, 403):
        return jsonify({"ok": False, "detalle": f"La API key fue rechazada (HTTP {r.status_code})."})
    if r.status_code == 404:
        return jsonify({"ok": False, "detalle": "HTTP 404 -- el subdominio responde, pero esta ruta "
                         "no existe en esta cuenta (la API real puede diferir de la hipotesis)."})
    # Solo el codigo: el cuerpo es del proveedor y puede traer cualquier cosa.
    return jsonify({"ok": False, "detalle": f"El servidor respondio HTTP {r.status_code}."})


# =============================================================================
#  CONVERSACIONES  -  solo lectura, la bandeja de chats con clientes finales
# =============================================================================

@app.get("/conversaciones")
def conversaciones():
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400

    try:
        salida = persistencia.ultima_actividad(tenant, canal=request.args.get("canal"))
    except RuntimeError as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 404
    except Exception as e:
        registrar("conversaciones", "fallo al listar", error=e)
        return jsonify({"error": "No se pudo leer las conversaciones."}), 500

    # B3.5 (D18): la proyeccion viaja calculada. Que necesita cada
    # conversacion, en que banda de la cola cae, desde cuando espera y por que
    # -- para que la pantalla ordene y lo explique sin reimplementar la regla.
    for fila in salida:
        fila.update(proyeccion.proyectar(fila))
        fila["canal_operativo"] = fila.get("canal") in canales.REALES
    salida.sort(key=proyeccion.orden_de_cola)

    # El plazo de toma viaja con la cola y no por conversacion: es uno solo
    # para toda la empresa, y mandarlo repetido en cada fila seria el mismo
    # numero N veces. 0 = la empresa no definio objetivo, y entonces la
    # pantalla no dibuja cuenta regresiva -- ver TenantConfig.sla_toma_minutos.
    try:
        sla = int(getattr(_config_de(tenant), "sla_toma_minutos", 0) or 0)
    except Exception:
        # No poder leer la config no puede tumbar la cola entera: sin plazo,
        # la Bandeja funciona igual, sólo que sin el reloj.
        sla = 0

    # La salud del canal viaja con la cola por lo mismo que el plazo: es una
    # sola para la empresa. Son los tres numeros crudos -- el veredicto lo
    # arma la pantalla, en un solo lugar y con pruebas.
    canal_whatsapp = persistencia.salud_canal_whatsapp(tenant)

    return jsonify({"tenant": tenant, "conversaciones": salida,
                    "sla_toma_minutos": sla,
                    "canal_whatsapp": canal_whatsapp})


@app.get("/conversaciones/por-caso/<caso_id>")
def conversacion_por_caso(caso_id):
    """
    La conversacion que origino un caso del CRM.

    Solo lectura y solo metadatos -- no devuelve los mensajes: para eso ya
    esta /conversaciones/<id>/mensajes, y quien pregunta por el origen de un
    caso no necesita la transcripcion (la tiene en el propio caso).
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        datos = persistencia.conversacion_de_caso(tenant, caso_id)
    except Exception as e:
        registrar("conversaciones", "fallo al buscar por caso", error=e)
        return jsonify({"error": "No se pudo leer la conversacion."}), 500

    # Los enlaces directos a los sistemas externos, armados ACA y no en la
    # pantalla: el motor es quien conoce los identificadores y los dominios de
    # cada empresa. La pantalla solo los dibuja.
    #
    # Se arman con el IDENTIFICADOR, nunca con el nombre. Las URLs del panel
    # admiten un usuario que contiene el nombre del cliente, y armarlo a mano
    # (pasar "MARIO SABANAGRANDE" a "mario-sabanagrande") abriria la ficha de
    # cualquier homonimo. El identificador es lo unico que no se parece a otro.
    try:
        config = _config_de(tenant)
    except Exception:
        config = None

    # 'servicio' lo manda la pantalla desde 'Case.external_service_id'. El
    # motor no puede leerlo por su cuenta: corre con su propio usuario de base
    # y no ve las tablas del CRM (incidente del 18/08/2026, ver el compose).
    # Que lo mande quien ya tiene el caso en la mano es mas barato que abrir un
    # camino nuevo para volver a pedir algo que ya estaba cargado.
    identidad = identidad_del_contexto(datos, request.args.get("servicio") or "")
    contexto = contexto_tecnico(config, tenant, identidad) if config else {}

    # Dos cosas distintas en dos claves distintas. 'conversacion' es DE DONDE
    # VINO el caso -- canal, etiqueta, motivo de la escalada -- y puede ser
    # None; 'contexto' es QUE HAY DEL OTRO LADO -- cliente, equipo, enlaces --
    # y ahora existe aunque no haya habido ninguna conversacion. Estaban
    # pegadas en un solo objeto porque hasta hoy la segunda solo se podia
    # obtener a traves de la primera.
    if datos is not None:
        datos["enlaces"] = contexto          # compatibilidad
    return jsonify({"conversacion": datos, "contexto": contexto})


IDENTIDAD_CASE = "case"
IDENTIDAD_CONVERSACION = "conversacion"

# Por que puede faltar la tarjeta del equipo. Son dos motivos distintos y la
# pantalla los dice distinto: uno es "todavia no cargaron el serial en el
# sistema del ISP", el otro es "no sabemos de quien es este ticket".
SIN_ONU_VINCULADA = "onu_no_vinculada"
# El serial que tiene el sistema del ISP no existe en el de la OLT. Casi
# siempre significa que le cambiaron el equipo al cliente y actualizaron un
# sistema y no el otro -- confirmado el 10/09/2026 sobre los cuatro casos que
# fallaban: los cuatro clientes estaban en la OLT con OTRO serial, y a dos de
# ellos les habian cambiado la ONU ese mismo dia y el anterior.
SERIAL_DESACTUALIZADO = "serial_desactualizado"

# Cuanto vale el inventario de ONU antes de volver a pedirlo. La consulta trae
# 4.909 equipos en 11,7 MB y tarda 2 s: cara para hacerla al abrir cada ticket,
# barata una vez cada cinco minutos. Solo se paga cuando un serial NO responde,
# que es el 13 % de los casos.
_onus_por_olt: dict = {}
SEGUNDOS_INVENTARIO_ONU = 300.0

# Que porcentaje de las palabras del nombre tiene que coincidir para proponer
# una ONU. No es un numero elegido a ojo: medido contra los cuatro casos
# reales, 0.75 acepta "BRANDON STEVEN PATERNINA POLO" contra la ficha que en la
# OLT dice "PARERNINA" -- un apellido mal tipeado, 3 de 4 palabras -- y rechaza
# "EMERSON STEVEN POLO CARRANZA", que comparte dos palabras y es otra persona.
# Con un umbral mas bajo, la pantalla ofreceria el equipo de un tercero.
UMBRAL_NOMBRE = 0.75


def identidad_del_contexto(conv: dict | None, servicio_case: str) -> dict:
    """
    Con QUE servicio se resuelve el contexto tecnico. Deterministico, sin
    ninguna aproximacion.

    Un caso importado del sistema del ISP trae su propio identificador de
    servicio y no tiene conversacion detras; uno nacido de un chat tiene la
    conversacion y no el identificador. Los dos caminos terminan en el mismo
    numero, asi que la unica pregunta real es cual gana cuando estan los dos.

        A  el del caso    manda. Lo dijo el proveedor sobre ESE ticket.
        B  el del chat    si el caso no trae nada.
        C  los dos y no coinciden -> gana A y se INFORMA la discrepancia.
        D  ninguno        sin contexto. Es lo normal en un ticket cargado a
                          mano, no un error.

    Nunca se elige por nombre, telefono ni parecido. El comentario de
    'conversacion_de_caso' ya explica por que: armar algo con el nombre abre
    la ficha de cualquier homonimo.

    EL SERIAL DE RESPALDO SOLO VALE SI ES DEL MISMO SERVICIO. La conversacion
    guarda un 'sn_onu' que corresponde al cliente que ELLA identifico; si el
    caso apunta a otro servicio, ese serial es el equipo de otra persona.
    Arrastrarlo mostraria niveles opticos ajenos con cara de dato correcto --
    y encima justo en el caso donde ya sabemos que algo no cuadra.
    """
    del_caso = str(servicio_case or "").strip()
    conv = conv or {}
    de_conv = str(conv.get("id_cliente") or "").strip()
    sn_conv = str((conv.get("datos_sesion") or {}).get("sn_onu") or "").strip()

    if del_caso and de_conv and del_caso != de_conv:
        return {"id_servicio": del_caso, "origen": IDENTIDAD_CASE,
                "sn_onu_respaldo": "",
                "conflicto": {"case": del_caso, "conversacion": de_conv}}
    if del_caso:
        return {"id_servicio": del_caso, "origen": IDENTIDAD_CASE,
                "sn_onu_respaldo": sn_conv if del_caso == de_conv else "",
                "conflicto": None}
    if de_conv:
        return {"id_servicio": de_conv, "origen": IDENTIDAD_CONVERSACION,
                "sn_onu_respaldo": sn_conv, "conflicto": None}
    return {"id_servicio": "", "origen": "", "sn_onu_respaldo": "",
            "conflicto": None}


def contexto_tecnico(config, tenant: str, identidad: dict) -> dict:
    """
    Quien es el cliente de un servicio, que equipo tiene y como esta ese
    equipo ahora. Mas los enlaces para ir a verlo sin volver a buscarlo.

    Recibe IDENTIFICADORES, no un caso ni una conversacion. Por eso sirve
    igual al detalle del CRM, a una orden de trabajo y a la API de campo, sin
    que ninguno de los tres le hable al sistema del ISP por su cuenta -- y sin
    que el nucleo tenga que saber que existe un Case, que es la regla que
    tests/test_nucleo_sin_tenants.py hace cumplir.

    EL SERIAL SE RELEE SIEMPRE, no se guarda. Medido el 10/09/2026 sobre 600
    clientes reales: el 80,8 % tiene serial cargado. El 19 % restante casi
    nunca es un servicio sin equipo -- es un serial que todavia nadie cargo
    del otro lado. Guardarlo aca convertiria a Dexter en una segunda fuente de
    verdad de un dato ajeno, con la obligacion de mantener las dos iguales.
    Releerlo no cuesta una llamada extra (la ficha del cliente se pide igual) y
    hace que el dia que alguien lo cargue, la tarjeta aparezca sola.

    Devuelve solo lo que se puede armar de verdad. Que falte algo NO es un
    error: se escala una conversacion justamente cuando el asistente no pudo
    avanzar, y muchas veces eso incluye no haber identificado al cliente.
    Medido sobre 85 conversaciones reales: 45 con cliente identificado y 12 con
    ticket. Que la pantalla diga "no disponible" es el caso NORMAL.
    """
    v = config.variables_tenant or {}
    panel = (v.get("WISPHUB_PANEL_URL") or "").rstrip("/")
    sufijo = v.get("WISPHUB_SUFIJO_USUARIO") or ""
    olt = (v.get("SMARTOLT_SUBDOMINIO") or "").rstrip("/")

    id_cliente = identidad.get("id_servicio") or ""
    enlaces: dict = {}

    if not id_cliente:
        # Sin identificador no hay a quien preguntarle, y no se llama a nadie.
        # La discrepancia, si la hubiera, viaja igual: es lo unico que se sabe.
        if identidad.get("conflicto"):
            enlaces["identidad_en_conflicto"] = identidad["conflicto"]
        return enlaces

    # El 'usuario' del sistema externo NO viene en el detalle del cliente,
    # solo en el LISTADO -- verificado el 25/08/2026: el detalle lo devuelve
    # vacio y el listado lo trae completo. Es el mismo patron que esa API
    # ya mostro otras veces: dos endpoints del mismo proveedor dicen cosas
    # distintas del mismo registro (ver la skill del proveedor en .claude/).
    ficha = _ficha_cliente(config, id_cliente, tenant)
    usuario, ip = ficha.get("usuario"), ficha.get("ip")
    # El serial VIVO del sistema del ISP manda. El de la conversacion es solo
    # respaldo, y llega hasta aca unicamente si corresponde al mismo servicio
    # (ver identidad_del_contexto).
    sn_onu = str(ficha.get("sn_onu") or identidad.get("sn_onu_respaldo") or "").strip()

    if panel and usuario:
        enlaces["wisphub_perfil"] = f"{panel}/clientes/ver/{usuario}/"
        if id_cliente:
            enlaces["wisphub_trafico"] = (
                f"{panel}/trafico/semana/servicio/{usuario}/{id_cliente}/")
            enlaces["wisphub_ping"] = (
                f"{panel}/clientes/ping/{usuario}/{id_cliente}/")
    if ip:
        # El router del cliente, para que entre a su configuracion. Es una IP
        # de la red del ISP: solo llega desde adentro, no desde cualquier lado.
        enlaces["router"] = f"http://{ip}"
        enlaces["ip"] = ip
    if olt and sn_onu:
        enlaces["smartolt_ont"] = f"{olt}/onu/details/{sn_onu}"
        enlaces["sn_onu"] = sn_onu
        # El estado del equipo AHORA, para no tener que salir a mirarlo.
        # Una sola vez al abrir el ticket y sin refresco automatico: quien
        # quiera el dato fresco entra por el enlace, que siempre lo esta.
        enlaces["equipo"] = _estado_equipo(config, sn_onu, tenant)
        if not enlaces["equipo"]:
            # El serial existe en el sistema del ISP y la OLT no lo conoce.
            # Antes esto se mostraba como "no se pudo leer el estado", que
            # mandaba a buscar una falla de red donde habia un dato viejo.
            candidatos = onus_del_cliente(
                _inventario_onu(config, tenant), ficha.get("nombre") or "")
            # Si el candidato es el MISMO serial, entonces no es un serial
            # viejo: la OLT lo conoce y la consulta fallo por otra cosa.
            candidatos = [c for c in candidatos
                          if c["sn"].upper() != sn_onu.upper()]
            if candidatos:
                enlaces["equipo_no_disponible"] = SERIAL_DESACTUALIZADO
                enlaces["equipo_candidatos"] = candidatos
    elif not sn_onu:
        # El servicio esta identificado y el sistema del ISP no tiene serial.
        # No se llama a SmartOLT -- no hay con que -- y se dice POR QUE, que no
        # es lo mismo que una tarjeta vacia. Casi siempre significa que todavia
        # nadie cargo el serial, no que el cliente no tenga equipo: por eso el
        # texto de la pantalla no culpa al asistente.
        enlaces["equipo_no_disponible"] = SIN_ONU_VINCULADA

    # La ficha del cliente va aparte de los enlaces: son datos, no destinos.
    # 'sn_onu' se saca de aca porque ya viaja arriba junto a su enlace;
    # repetirlo en la tarjeta del cliente seria el mismo dato dos veces.
    if ficha:
        enlaces["cliente"] = {k: v for k, v in ficha.items()
                              if k not in ("usuario", "sn_onu")}

    # Con que servicio se resolvio todo esto, y si los dos origenes se
    # contradecian. La discrepancia viaja como DATO y no como log: quien abre
    # el ticket tiene que verla, y un log lo lee solo alguien que ya sospecha.
    enlaces["identidad"] = {"servicio": id_cliente,
                            "origen": identidad.get("origen") or ""}
    if identidad.get("conflicto"):
        enlaces["identidad_en_conflicto"] = identidad["conflicto"]

    return enlaces


def _enlaces_externos(config, conv: dict, tenant: str) -> dict:
    """El contexto tecnico de una conversacion. Envoltura de compatibilidad."""
    return contexto_tecnico(config, tenant, identidad_del_contexto(conv, ""))


# Las herramientas que dan el estado del equipo. Se piden por NOMBRE y no por
# endpoint: son las livianas (2-3 s cada una). Existe una tercera que trae
# ademas la causa de la ultima caida, pero tarda ~10 s y el proveedor pide no
# usarla en consultas repetidas -- diez segundos al abrir cada ticket se
# sienten, y esa causa se puede ver entrando por el enlace.
_HERRAMIENTAS_EQUIPO = ("consultar_estado_ont", "consultar_senal_ont")


def _estado_equipo(config, sn_onu: str, tenant: str) -> dict:
    """
    Estado y niveles opticos del equipo, o {} si no se pudo leer.

    Se consulta cada herramienta por separado y se sigue aunque una falle: que
    no responda la señal no tiene por que ocultar que el equipo esta en linea.
    Y si fallan las dos, la pantalla muestra el enlace igual -- sin refresco
    automatico, una tarjeta vacia no se arregla sola.
    """
    salida = {}
    por_nombre = {h.nombre: h for h in config.herramientas}
    for nombre in _HERRAMIENTAS_EQUIPO:
        herr = por_nombre.get(nombre)
        if herr is None:
            continue
        try:
            datos = ejecutor_http.ejecutar(
                herr, {"sn_onu": sn_onu}, tenant,
                variables_tenant=config.variables_tenant)
            if isinstance(datos, dict):
                salida.update({k: v for k, v in datos.items()
                               if isinstance(v, (str, int, float, bool)) and v != ""})
        except Exception as e:
            registrar("enlaces", "la herramienta de equipo no respondio",
                      herramienta=nombre, error=e)
    return salida


# Lo que la ficha del cliente aporta a la pantalla del ticket. Se nombra aca
# y no se devuelve la fila entera a proposito: ese registro trae 54 campos,
# incluidas CUATRO contraseñas y las coordenadas del domicilio (ver la skill
# del proveedor). Una lista blanca, como en todo el resto del sistema.
# 'cedula' entra por decision explicita del usuario (25/08/2026): es dato
# personal y por eso no estaba, pero quien atiende el ticket la necesita para
# confirmar con quien habla sin salir a buscarla. Va SOLO a la pantalla de un
# colaborador -- nunca a una respuesta al cliente, que sigue gobernada por la
# lista blanca del rol.
# 'sn_onu' entra el 10/09/2026: es el serial del equipo del cliente, y es la
# UNICA forma de llegar a SmartOLT -- sus once herramientas se indexan por el.
# Hasta hoy el dato pasaba por esta funcion y se tiraba, porque el serial se
# sacaba de la sesion de la conversacion; un caso importado no tiene ninguna.
# No es dato personal: identifica un aparato, no a una persona.
#
# 'telefono', 'direccion' y 'localidad' entran el 10/09/2026, por decision
# explicita y con el mismo criterio que 'cedula': son datos personales y por
# eso no estaban, pero quien atiende un ticket de campo tiene que poder llamar
# al cliente y saber a donde ir sin salir a buscarlo en otro sistema. Ademas
# son los que va a necesitar el tecnico offline cuando la orden de trabajo se
# los lleve congelados.
#
# 'localidad' y NO 'zona', que se le parece y no sirve: medido el 10/09/2026,
# 'zona' es {'id': 20049, 'nombre': 'CORTE 30 - SERVIDOR 1'} -- una zona de
# corte de facturacion, ademas anidada-- mientras que 'localidad' trae
# 'MARTHA GISELA', que es el barrio y coincide con la zona que reporta
# SmartOLT. Pedir "la zona" y agregar el campo que se llama asi habria puesto
# en pantalla algo que a un tecnico no le dice nada.
_CAMPOS_FICHA = ("usuario", "ip", "estado", "nombre", "cedula", "sn_onu",
                 "telefono", "direccion", "localidad")


def _inventario_onu(config, tenant: str) -> list:
    """
    Todas las ONU de la OLT, para poder buscar por nombre. Cacheado por proceso.

    Es la unica forma de encontrar el equipo de un cliente cuando el serial que
    tiene el sistema del ISP ya no existe: las once herramientas de la OLT se
    indexan por serial, ninguna busca por cliente.

    Se pide UNA vez cada cinco minutos y solo cuando hace falta. Ponerlo en el
    camino de cada ticket seria 11,7 MB por apertura para una respuesta que casi
    siempre no se necesita.
    """
    ahora = time.monotonic()
    entrada = _onus_por_olt.get(tenant)
    if entrada and (ahora - entrada[0]) < SEGUNDOS_INVENTARIO_ONU:
        return entrada[1]

    herr = next((h for h in config.herramientas
                 if h.nombre in _HERRAMIENTAS_EQUIPO), None)
    v = config.variables_tenant or {}
    base = (v.get("SMARTOLT_SUBDOMINIO") or "").rstrip("/")
    if herr is None or not base:
        return []
    try:
        import requests

        clave = secretos.obtener(tenant, herr.auth_ref)
        if not clave:
            return []
        r = requests.get(f"{base}/api/onu/get_all_onus_details",
                         headers={herr.auth_header: clave},
                         timeout=TIMEOUT_INVENTARIO)
        r.raise_for_status()
        onus = (r.json() or {}).get("onus") or []
    except Exception as e:                                  # noqa: BLE001
        registrar("enlaces", "no se pudo leer el inventario de ONU", error=e)
        return []
    _onus_por_olt[tenant] = (ahora, onus)
    return onus


TIMEOUT_INVENTARIO = 60


def _palabras(nombre: str) -> set:
    """Las palabras con peso de un nombre. Las de tres letras o menos no
    distinguen a nadie ('DE', 'LA', 'DEL')."""
    from unicodedata import category, normalize

    limpio = "".join(c for c in normalize("NFD", str(nombre or "").upper())
                     if category(c) != "Mn")
    return {p for p in limpio.replace(".", " ").split() if len(p) > 3}


def onus_del_cliente(onus: list, nombre: str) -> list:
    """
    Las ONU que podrian ser de este cliente, por parecido de nombre.

    Devuelve CANDIDATAS, nunca una respuesta. Que la pantalla las muestre y
    decida una persona no es prudencia de mas: probado el 10/09/2026, una
    coincidencia laxa propone el equipo de otro cliente que comparte dos
    palabras del nombre, y mostrar su potencia optica como si fuera la del
    titular del ticket es exactamente el error que este proyecto ya decidio no
    cometer con los enlaces armados por nombre.

    Se ordenan por fecha de alta descendente: si al cliente le cambiaron el
    equipo, el nuevo es el de arriba. Pero eso es un orden, no un veredicto.
    """
    buscadas = _palabras(nombre)
    if not buscadas:
        return []
    encontradas = []
    for o in onus:
        tiene = _palabras(o.get("name"))
        if not tiene:
            continue
        comunes = len(buscadas & tiene)
        if comunes / len(buscadas) >= UMBRAL_NOMBRE:
            encontradas.append({
                "sn": str(o.get("sn") or ""),
                "nombre": str(o.get("name") or ""),
                "zona": str(o.get("zone_name") or ""),
                "alta": str(o.get("authorization_date") or "")[:10],
                "estado": str(o.get("status") or ""),
            })
    encontradas.sort(key=lambda c: c["alta"], reverse=True)
    return encontradas[:4]


def _ficha_cliente(config, id_cliente, tenant: str) -> dict:
    """
    Lo que se sabe del cliente en el sistema del ISP: como identificarlo, su
    IP, su plan y si el servicio esta al dia. Diccionario vacio si no se pudo.

    UNA sola llamada, la misma que ya hacia falta para armar los enlaces: esa
    respuesta ya trae el plan y el estado, asi que llenar la ficha entera no
    cuesta ninguna consulta extra.

    Nunca rompe el turno: si la API no responde, la pantalla muestra el ticket
    sin la ficha en vez de no mostrar el ticket.
    """
    if not id_cliente:
        return {}
    try:
        # Se elige por lo que la herramienta SABE HACER, no por su endpoint.
        # Cuatro herramientas del catalogo apuntan a la misma ruta y solo una
        # declara el filtro por identificador de servicio; las otras filtran
        # por cedula o lo inyectan de la sesion, asi que pasarles el id lo
        # descartan y devuelven el primer cliente de la empresa -- otro
        # cliente, con aspecto de respuesta correcta. Elegir "la primera que
        # coincide por endpoint" fallaba justo asi.
        herr = next((h for h in config.herramientas
                     if h.tipo == "http" and "id_servicio" in (h.filtros_verificados or {})),
                    None)
        if herr is None:
            return {}
        datos = ejecutor_http.ejecutar(
            herr, {"id_servicio": str(id_cliente)}, tenant,
            variables_tenant=config.variables_tenant)
        filas = datos.get("results") if isinstance(datos, dict) else None
        fila = (filas or [None])[0]
        if not isinstance(fila, dict):
            return {}
        ficha = {c: fila.get(c) for c in _CAMPOS_FICHA if fila.get(c)}
        # El plan viene anidado ({"id":..., "nombre":...}); se guarda su
        # nombre, que es lo unico que le dice algo a quien lee el ticket.
        plan = fila.get("plan_internet")
        if isinstance(plan, dict) and plan.get("nombre"):
            ficha["plan"] = plan["nombre"]
        return ficha
    except Exception as e:
        registrar("enlaces", "no se pudo leer la ficha del cliente", error=e)
        return {}


@app.get("/conversaciones/<id_conversacion>/mensajes")
def conversaciones_mensajes(id_conversacion):
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400

    try:
        resultado = persistencia.mensajes_de(tenant, id_conversacion)
    except RuntimeError as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 404
    except Exception as e:
        registrar("conversaciones", "fallo al leer mensajes", error=e)
        return jsonify({"error": "No se pudo leer la conversacion."}), 500

    if resultado["conversacion"] is None:
        return jsonify({"error": f"La conversacion '{id_conversacion}' no existe."}), 404

    # La ventana de 24 h SOLO para WhatsApp. El simulador, la API y cualquier
    # canal futuro no tienen esta regla, y heredarla por descuido dejaria al
    # operador sin poder escribir donde nadie se lo impide.
    conv = resultado["conversacion"]
    if conv.get("canal") == "whatsapp":
        conv["ventana_whatsapp"] = whatsapp.estado_de_ventana(
            conv.get("ultimo_mensaje_cliente"))
    # Quien controla HOY, ya calculado: la pantalla no reimplementa la regla.
    conv["control_efectivo"] = control_efectivo(conv)

    # Los identificadores tecnicos del equipo del cliente, FILTRADOS por la
    # misma lista que decide que se persiste al verificar. 'datos_sesion'
    # guarda ademas el estado de anti-rebote (las areas ya visitadas), que es
    # del ROUTING y no del cliente: mandarlo entero seria enviar a la pantalla
    # cosas que no le tocan. Se filtra por Sesion.CAMPOS_PERSISTIBLES y no por
    # una lista escrita aca, para que el motor siga sin conocer el vocabulario
    # del tenant: 'sn_onu' es de un ISP de fibra y el proximo puede capturar
    # otra cosa -- cuando esa lista crezca, esto crece solo.
    sesion_guardada = conv.pop("datos_sesion", None) or {}
    conv["equipo"] = {c: sesion_guardada.get(c) for c in Sesion.CAMPOS_PERSISTIBLES
                      if sesion_guardada.get(c)}

    return jsonify(resultado)


@app.get("/canales/plantillas")
def canales_plantillas():
    """
    Las plantillas que Meta tiene aprobadas para esta empresa, con su texto.

    Se consultan EN VIVO y no se cachean: una plantilla recien aprobada tiene
    que aparecer sin esperar nada, y el caso de uso --alguien mirando una
    conversacion con la ventana cerrada-- ocurre pocas veces por dia.

    Devuelve solo las APPROVED. Ofrecer una en revision seria ofrecer un
    envio que va a fallar.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        config = _config_de(tenant)
        todas = whatsapp.plantillas_aprobadas(config, tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404
    except Exception as e:
        return fallo(502, "plantillas_no_leidas",
                     mensaje_publico(e, "No se pudieron leer las plantillas."),
                     componente="plantillas", e=e)

    aprobadas = [p for p in todas if (p.get("estado") or "").upper() == "APPROVED"]
    return jsonify({"plantillas": aprobadas, "total_en_meta": len(todas)})


def _autor_y_clave(campos) -> tuple[str, str, str | None]:
    """
    (autor_nombre, autor_usuario_id, clave_idempotencia) de un cuerpo JSON o
    de un formulario multipart. Levanta persistencia.AutorInvalido si falta
    el autor: un mensaje de persona sin autor no se guarda (D2). Los arma el
    proxy del frontend con la sesion autenticada, nunca el navegador.
    """
    nombre, usuario = persistencia.validar_autor(
        campos.get("autor"), campos.get("autor_usuario_id"))
    return nombre, usuario, (campos.get("clave_idempotencia") or "").strip() or None


def _exigir_control_humano(tenant: str, id_conversacion: str):
    """
    GUARDA DEL RELEVO (B3.3, contrato X25): nada que escribe una persona le
    llega al cliente mientras la conversacion la atiende la IA. Texto, media y
    plantilla la llaman ANTES de guardar nada y antes de hablar con Meta.

    Devuelve None si se puede seguir, o (respuesta, codigo) para devolver:
      409  la controla la IA -- hay que intervenir primero
      404  no existe o no es de este tenant
      503  no se pudo leer el control: falla cerrado, no se envia a ciegas

    Decide con control_efectivo() (nucleo/relevo/control.py), la misma regla
    para todas las rutas: en una conversacion de legado escalada, que todavia
    tiene control 'ia' por default, cuenta como humana y no se bloquea a quien
    la esta atendiendo. La nota interna NO pasa por aca: no sale del equipo.
    """
    try:
        control = persistencia.control_efectivo_de(tenant, id_conversacion)
    except Exception as e:
        registrar("relevo", "no se pudo leer el control", conversation_id=id_interno(id_conversacion),
                  error=e)
        return jsonify({"error": "No se pudo comprobar quien atiende la conversacion. "
                                 "No se envio nada.", "codigo": "control_desconocido"}), 503
    if control is None:
        return jsonify({"error": f"La conversacion '{id_conversacion}' no existe."}), 404
    if control != "humano":
        return jsonify({"error": "La IA esta atendiendo esta conversacion. Para escribirle "
                                 "al cliente hay que intervenir primero.",
                        "codigo": "control_ia", "control": control}), 409
    return None


def _ya_guardado(destino: dict) -> bool:
    """
    True si 'destino' es un REINTENTO de un mensaje que ya existia (misma
    clave de idempotencia) y NO hay que volver a entregarlo: solo se reenvia
    lo que fallo. Un 'pendiente' sin resultado puede estar en vuelo o haber
    salido sin que se anotara; reenviarlo arriesga un duplicado ante el
    cliente, asi que tampoco se reenvia (SPEC/CONTRATO_RELEVO_IA_HUMANO.md,
    §9.5).
    """
    return bool(destino.get("existente")) and destino.get("estado_entrega") != "fallido"


@app.post("/conversaciones/<id_conversacion>/plantilla")
def conversaciones_enviar_plantilla(id_conversacion):
    """
    Mandar una plantilla aprobada, que es la unica forma de escribirle a
    alguien con la ventana de 24 h cerrada.

    Mismo orden que responder texto: se GUARDA y despues se entrega. Lo que
    se guarda es el texto YA ARMADO con sus variables -- no el nombre de la
    plantilla-- porque el hilo tiene que mostrar lo que el cliente leyo, y
    porque el texto de una plantilla lo puede cambiar Meta despues.

    NO abre la ventana. La ventana la abre el cliente cuando responde, y
    nada mas: esto queda con rol 'assistant' (origen 'humano'), y el calculo
    de la ventana solo cuenta los mensajes del cliente.

    El canal se valida ANTES de guardar (D16): antes la fila quedaba escrita
    y recien despues se respondia 400 porque la conversacion no era de
    WhatsApp.
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    nombre = (cuerpo.get("plantilla") or "").strip()
    variables = [str(v) for v in (cuerpo.get("variables") or [])]
    if not tenant or not nombre:
        return jsonify({"error": "Faltan campos: tenant, plantilla"}), 400
    try:
        autor, autor_id, clave = _autor_y_clave(cuerpo)
    except persistencia.AutorInvalido as e:
        return jsonify({"error": f"Autor invalido: {mensaje_publico(e, 'datos de autor incompletos')}"}), 400
    bloqueo = _exigir_control_humano(tenant, id_conversacion)
    if bloqueo:
        return bloqueo

    try:
        config = _config_de(tenant)
        disponibles = whatsapp.plantillas_aprobadas(config, tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404
    except Exception as e:
        return fallo(502, "plantillas_no_leidas",
                     mensaje_publico(e, "No se pudieron leer las plantillas."),
                     componente="plantillas", e=e)

    # Se vuelve a mirar la lista en vez de confiar en lo que mando la
    # pantalla: entre que se dibujo el selector y que alguien apreto Enviar
    # puede haber pasado cualquier cosa, y el nombre viaja por la red.
    elegida = next((p for p in disponibles
                    if p["nombre"] == nombre
                    and (p.get("estado") or "").upper() == "APPROVED"), None)
    if elegida is None:
        return jsonify({"error": f"'{nombre}' no es una plantilla aprobada de "
                                 f"esta cuenta."}), 400
    # Una plantilla que mezcla {{1}} con {{nombre}} no es un formato de Meta.
    # No se adivina cual de las dos lecturas vale: se rechaza, porque
    # cualquiera de las dos pondria un valor en el lugar de otro.
    if elegida.get("formato_variables") == "mixto":
        return jsonify({"error": f"'{nombre}' mezcla variables numeradas y con "
                                 f"nombre. Hay que corregirla en Meta antes de "
                                 f"poder enviarla."}), 400
    if len(variables) != elegida["variables"]:
        return jsonify({"error": f"'{nombre}' necesita {elegida['variables']} "
                                 f"variable(s) y llegaron {len(variables)}."}), 400

    texto = _armar_plantilla(elegida, variables)

    try:
        destino = persistencia.agregar_mensaje_humano(
            tenant, id_conversacion, texto, autor, autor_usuario_id=autor_id,
            clave_idempotencia=clave, solo_canal=canales.WHATSAPP)
    except persistencia.CanalNoAdmite:
        return jsonify({"error": "Las plantillas son de WhatsApp; esta "
                                 "conversacion es de otro canal."}), 400
    except RuntimeError as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 404
    except Exception as e:
        registrar("plantillas", "fallo al guardar", error=e)
        return jsonify({"error": "No se pudo guardar el mensaje."}), 500
    if destino is None:
        return jsonify({"error": f"La conversacion '{id_conversacion}' no existe."}), 404
    if _ya_guardado(destino):
        return jsonify({"ok": True, "ya_existia": True, "texto": texto,
                        "mensaje_id": destino["mensaje_id"],
                        "estado_entrega": destino["estado_entrega"]}), 200

    salida = {"ok": True, "texto": texto, "mensaje_id": destino["mensaje_id"]}
    salida.update(_entregar_y_registrar(
        tenant, destino["mensaje_id"],
        lambda: whatsapp.enviar_plantilla_aprobada(
            config, tenant, destino["usuario_externo"], nombre, variables,
            elegida.get("idioma") or "es", plantilla=elegida),
        f"plantillas '{nombre}'"))
    return jsonify(salida), 201


def _rellenar(texto: str, huecos: list[str], valores: list[str]) -> str:
    """Cada hueco con su valor, por posicion en la lista de huecos."""
    for hueco, valor in zip(huecos, valores):
        texto = texto.replace("{{" + hueco + "}}", valor)
    return texto


def _armar_plantilla(plantilla: dict, variables: list[str]) -> str:
    """
    El texto final, con los huecos reemplazados -- lo que va a leer el cliente
    y lo que queda en el hilo.

    Reparte la lista plana igual que whatsapp.componentes_de_plantilla:
    primero el encabezado, despues el cuerpo. Y rellena CADA componente con
    los suyos, porque en posicional los dos numeran desde 1 -- el {{1}} del
    cuerpo no es el mismo valor que el {{1}} del encabezado.

    Si este reparto dejara de coincidir con el del envio, el cliente leeria
    una cosa y el hilo guardaria otra.
    """
    del_encabezado = list(plantilla.get("variables_encabezado") or [])
    del_cuerpo = list(plantilla.get("variables_cuerpo") or [])
    corte = len(del_encabezado)
    encabezado = _rellenar(plantilla.get("encabezado") or "",
                           del_encabezado, variables[:corte]).strip()
    cuerpo = _rellenar(plantilla.get("cuerpo") or "", del_cuerpo,
                       variables[corte:corte + len(del_cuerpo)])
    return f"{encabezado}\n\n{cuerpo}".strip() if encabezado else cuerpo


@app.post("/mantenimiento/cerrar-sin-respuesta")
def mantenimiento_cerrar_sin_respuesta():
    """
    Cierra los casos donde el cliente dejo de contestar hace mas del plazo que
    declare el tenant. Sin plazo declarado no hace nada.

    Es un endpoint y no solo un hilo interno para que se pueda correr a mano
    --y sobre todo, para poder VERLO correr-- sin esperar la proxima pasada.
    """
    tenant = request.args.get("tenant") or (
        request.get_json(force=True, silent=True) or {}).get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404
    return jsonify(operativo.cerrar_vencidas(config, tenant))


@app.post("/mantenimiento/cerrar-inactivas-ia")
def mantenimiento_cerrar_inactivas_ia():
    """
    Cierra las conversaciones que atendio SOLO el asistente y quedaron mudas.

    Hermano de '/mantenimiento/cerrar-sin-respuesta', que solo alcanza a las
    ESCALADAS: sin este, una conversacion que la IA resolvio sola no la cierra
    nadie nunca. Medido contra produccion el 22/09/2026: 151 asi, 145 de ellas
    sin un mensaje en mas de una semana.

    'simular=1' lista las que se cerrarian sin tocarlas. Se usa primero,
    siempre: la primera corrida sobre un backlog acumulado es la unica que no
    se puede deshacer mirando despues.
    """
    tenant = request.args.get("tenant") or (
        request.get_json(force=True, silent=True) or {}).get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    simular = request.args.get("simular") in ("1", "true", "si")
    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404
    return jsonify(operativo.cerrar_inactivas_de_ia(config, tenant, simular=simular))


@app.post("/casos/<caso_id>/mensajes")
def caso_responder_humano(caso_id):
    """
    Lo mismo que responder en la conversacion, pero entrando por el CASO.

    Existe porque quien atiende trabaja en la pantalla del ticket y ahi lo que
    se conoce es el caso, no la conversacion. La alternativa era que la
    pantalla resolviera una por la otra antes de cada respuesta, y esa consulta
    sale a los sistemas del ISP a buscar la ficha del cliente y el estado del
    equipo: cuatro segundos de espera para mandar una linea de texto.
    """
    tenant = (request.get_json(force=True, silent=True) or {}).get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400
    try:
        datos = persistencia.conversacion_de_caso(tenant, caso_id)
    except Exception as e:
        registrar("conversaciones", "fallo al resolver el caso", caso_id=caso_id, error=e)
        return jsonify({"error": "No se pudo resolver la conversacion."}), 500
    if not datos:
        # No es un error: un ticket cargado a mano no tiene conversacion
        # detras, y quien responde ahi no le esta hablando a nadie por chat.
        return jsonify({"error": "Este caso no vino de una conversacion.",
                        "sin_conversacion": True}), 404
    return conversaciones_responder_humano(datos["id"])


@app.post("/conversaciones/<id_conversacion>/mensajes")
def conversaciones_responder_humano(id_conversacion):
    """
    Un agente humano responde directo en una conversacion ya escalada -- sin
    pasar por el modelo. Distinto de /chat: eso simula al cliente escribiendo
    y le contesta el bot; esto es la respuesta de la persona que tomo el
    caso, tal cual la tipeo.

    GUARDAR NO ES ENTREGAR
    ----------------------
    Se guarda primero y se entrega despues, y el resultado de la entrega viaja
    en la respuesta ('entregado' / 'aviso'). Una respuesta que se ve en la
    bandeja pero nunca salio es peor que un error visible: el agente cree que
    ya atendio y el cliente sigue esperando. El caso mas comun no es una caida
    sino la ventana de 24 h de WhatsApp -- ver nucleo/canales/whatsapp.py.

    El orden importa: si se enviara primero y guardara despues, un fallo al
    guardar dejaria un mensaje que el cliente recibio y que no figura en
    ningun lado.
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    contenido = cuerpo.get("mensaje")
    # Si con esta respuesta la persona da por terminada su parte. Lo elige
    # ella: acaba de hacer el trabajo y sabe si le quedo algo preguntado al
    # cliente. Ver devolver_al_asistente().
    devolver = bool(cuerpo.get("devolver_al_asistente"))
    if not tenant or not contenido:
        return jsonify({"error": "Faltan campos: tenant, mensaje"}), 400
    # Quien contesta, OBLIGATORIO (D2). Lo manda el proxy porque el motor no
    # lee las tablas del CRM; firma la copia al ticket del ISP (ahi toda
    # respuesta queda a nombre de la cuenta de la API key) y el historial que
    # ve el modelo.
    try:
        autor, autor_id, clave = _autor_y_clave(cuerpo)
    except persistencia.AutorInvalido as e:
        return jsonify({"error": f"Autor invalido: {mensaje_publico(e, 'datos de autor incompletos')}"}), 400
    # T6 sin clave no se puede reintentar sin arriesgar un segundo mensaje al
    # cliente, y el reintento es justo lo que recupera una devolucion cortada a
    # la mitad. Se exige antes de escribir nada, y se dice por que.
    if devolver and not (clave or "").strip():
        return jsonify({"error": "Devolver al asistente requiere clave_idempotencia.",
                        "codigo": "clave_requerida"}), 400
    bloqueo = _exigir_control_humano(tenant, id_conversacion)
    if bloqueo:
        return bloqueo

    try:
        destino = (transiciones.solicitar_devolucion(
            tenant, id_conversacion, contenido, operador_id=autor_id,
            operador_nombre=autor, clave=clave)
                   if devolver else persistencia.agregar_mensaje_humano(
                       tenant, id_conversacion, contenido, autor,
                       autor_usuario_id=autor_id, clave_idempotencia=clave))
    except RuntimeError as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 404
    except Exception as e:
        registrar("conversaciones", "fallo al guardar respuesta humana", error=e)
        return jsonify({"error": "No se pudo guardar la respuesta."}), 500

    if destino is None:
        return jsonify({"error": f"La conversacion '{id_conversacion}' no existe."}), 404
    if _ya_guardado(destino):
        # Reintento de un mensaje que no fallo: ni otra fila, ni otra copia al
        # ticket, ni otra entrada al historial, ni otro envio.
        #
        # El estado de la FILA no alcanza para decidir. Un 'pendiente' puede ser
        # "el proceso se cayo antes de hablar con Meta" o "Meta acepto y el
        # proceso se cayo antes de anotarlo": lo primero no ocurrio, lo segundo
        # si le llego al cliente, y la fila los escribe igual. El desempate esta
        # en whatsapp_salidas, que es lo unico que se reservo ANTES del POST.
        estado_previo = destino["estado_entrega"]
        if estado_previo in ("enviado", "entregado", "leido"):
            # La fila ya lleva el sello durable: Meta acepto y quedo anotado.
            entrega = {"resultado": "aceptado", "aceptado_por_meta": True,
                       "aceptacion_registrada": True}
        else:
            entrega = _salida_previa(tenant, f"humano:{clave}")
        aceptado = entrega["resultado"] == "aceptado" and entrega["aceptacion_registrada"]
        devuelto = False
        if devolver and aceptado:
            r = transiciones.devolver_a_ia(
                tenant, id_conversacion, operador_id=autor_id,
                operador_nombre=autor, clave=f"devolver:{clave}")
            devuelto = r.aplicada or r.motivo == "reintento"
            if devuelto:
                clave_viva = canales.clave_sesion_de_fila(
                    tenant, destino.get("canal"), destino["usuario_externo"])
                if clave_viva in _sesiones:
                    _sesiones[clave_viva]["escalada"] = False
        elif devolver:
            # B1/B2: el primer intento se corto sin dejar rastro. Sin esto la
            # conversacion queda con el control humano correcto pero SIN una
            # sola linea que diga que alguien quiso devolverla y no se pudo --
            # y el operador no tiene como saber que su accion no llego.
            transiciones.registrar_devolucion_fallida(
                tenant, id_conversacion, destino["mensaje_id"],
                operador_id=autor_id, operador_nombre=autor,
                resultado=entrega["resultado"], clave=f"fallo:{clave}")
        return jsonify({"ok": True, "ya_existia": True,
                        "mensaje_id": destino["mensaje_id"],
                        "estado_entrega": estado_previo,
                        "resultado": entrega["resultado"],
                        "aceptado_por_meta": entrega["aceptado_por_meta"],
                        "aceptacion_registrada": entrega["aceptacion_registrada"],
                        "devuelto_al_asistente": devuelto}), 200
    reintento = bool(destino.get("existente"))

    # Lo que escribio la persona entra al HISTORIAL que ve el modelo, marcado
    # como suyo.
    #
    # Sin esto el asistente no se entera de nada: el mensaje se guarda en la
    # base, le llega al cliente, y el modelo sigue la conversacion donde la
    # dejo. Paso el 28/08/2026 -- el colaborador escribio "ya se realizo su
    # cambio de contraseña, confirmeme", el cliente contesto "listo, ya
    # quedaron conectados los celulares", y el asistente le repitio que
    # estaba esperando a un compañero para aplicarlo. Contradijo a su propio
    # equipo delante del cliente.
    #
    # Va con rol 'assistant' porque es el mismo lado del canal --el cliente ve
    # un solo interlocutor-- pero con el nombre adelante, que es lo que le
    # permite al modelo NO confundirlo con algo que dijo el. Y como la
    # transcripcion del caso sale de este mismo historial, en el ticket
    # tambien queda claro quien escribio cada cosa.
    clave_sesion = canales.clave_sesion_de_fila(
        tenant, destino.get("canal"), destino["usuario_externo"])
    if clave_sesion in _sesiones and not reintento:
        # La misma regla que la reconstruccion tras un reinicio: en vivo y
        # reconstruido el modelo ve exactamente lo mismo (D8).
        _sesiones[clave_sesion]["historial"].append(
            regla_historial.entrada("assistant", "humano", contenido, autor))

    salida = {"ok": True, "aceptado_por_meta": False,
              "aceptacion_registrada": False, "resultado": None,
              "devuelto_al_asistente": False}

    # La misma respuesta, copiada al ticket del sistema del ISP. Va aparte de
    # la entrega al cliente y no la condiciona: que la operacion no se entere
    # es un problema, pero uno menor que no contestarle a quien espera.
    if destino.get("ticket_operativo") and not reintento:
        try:
            config = _config_de(tenant)
            salida["copiado_al_ticket"] = operativo.responder(
                config, tenant, destino["ticket_operativo"], contenido, autor)
        except Exception as e:
            registrar("operativo", "no se pudo copiar la respuesta al ticket", error=e)
            salida["copiado_al_ticket"] = False

    if destino["canal"] != "whatsapp":
        # El simulador y la API no tienen a donde entregar: la conversacion se
        # lee desde la misma pantalla. No es un fallo.
        salida["aceptado_por_meta"] = None
        salida["aceptacion_registrada"] = True
        salida["resultado"] = "aceptado"
        if devolver:
            r = transiciones.devolver_a_ia(
                tenant, id_conversacion, operador_id=autor_id,
                operador_nombre=autor, clave=f"devolver:{clave}")
            salida["devuelto_al_asistente"] = r.aplicada or r.motivo == "reintento"
            # La sesion viva tambien: sin esto la base dice 'ia' y la sesion en
            # memoria sigue en pausa, asi que el asistente no reanuda hasta que
            # se reconstruya. Los otros dos caminos de T6 ya lo hacen; este se
            # quedaba afuera.
            if salida["devuelto_al_asistente"] and clave_sesion in _sesiones:
                _sesiones[clave_sesion]["escalada"] = False
        return jsonify(salida), 201

    # 201 aunque la entrega falle: el mensaje SI quedo guardado, y el agente
    # tiene que verlo en el hilo. Lo que no ocurrio es la entrega, y eso se dice
    # con todas las letras (aviso + fila en 'fallido') en vez de devolver un
    # error que sugiera que se perdio todo. El wamid queda sellado en la fila:
    # es la unica clave con la que despues se casan los acuses del webhook.
    salida["mensaje_id"] = destino["mensaje_id"]
    salida.update(_entregar_y_registrar(
        tenant, destino["mensaje_id"],
        lambda: whatsapp.enviar_texto(_config_de(tenant), tenant,
                                      destino["usuario_externo"], contenido),
        f"conversaciones '{id_conversacion}'", clave_salida=f"humano:{clave}",
        conversation_id=id_conversacion))
    if devolver:
        if salida["resultado"] == "aceptado" and salida["aceptacion_registrada"]:
            # T6 paso 4: solo después del commit que guardó el wamid.
            r = transiciones.devolver_a_ia(
                tenant, id_conversacion, operador_id=autor_id,
                operador_nombre=autor, clave=f"devolver:{clave}")
            salida["devuelto_al_asistente"] = r.aplicada or r.motivo == "reintento"
            if salida["devuelto_al_asistente"] and clave_sesion in _sesiones:
                _sesiones[clave_sesion]["escalada"] = False
        else:
            transiciones.registrar_devolucion_fallida(
                tenant, id_conversacion, destino["mensaje_id"],
                operador_id=autor_id, operador_nombre=autor,
                resultado=salida["resultado"], clave=f"fallo:{clave}")
    return jsonify(salida), 201


@app.get("/conversaciones/<id_conversacion>/herramientas")
def conversaciones_herramientas(id_conversacion):
    """
    Que hizo el agente en esta conversacion -- para el panel "Ver proceso"
    de un supervisor. Solo lectura, mismo criterio de auditoria que el
    resto: nombre de la herramienta y resultado, nunca el dato consultado.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400

    try:
        llamadas = persistencia.herramientas_de(tenant, id_conversacion)
    except RuntimeError as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 404
    except Exception as e:
        registrar("conversaciones", "fallo al leer herramientas", error=e)
        return jsonify({"error": "No se pudo leer el registro de herramientas."}), 500

    # El diagnostico se cuenta ACA y no en la pantalla: distinguir un bloqueo
    # de un fallo depende de una columna de la base, y si la pantalla lo
    # dedujera del texto del error habria que mantener esa regla en dos
    # lugares. La pantalla dibuja tres numeros; no decide cual es cual.
    #
    # Tres categorias y no cuatro. 'bloqueada' e 'intento no ejecutado' son la
    # misma cosa vista desde dos lados -- el codigo freno la accion-- y
    # separarlas obligaba a explicar una diferencia que no existe.
    return jsonify({
        "herramientas": llamadas,
        "diagnostico": {
            # Corrio y devolvio datos.
            "normales": sum(1 for l in llamadas if l["exito"]),
            # El CODIGO la freno: identidad sin verificar, precondicion sin
            # cumplir, accion que corta el servicio sin confirmar. NO es un
            # fallo -- es la proteccion funcionando-- y por eso se cuenta
            # aparte y no ensucia la tasa de error.
            "bloqueadas": sum(1 for l in llamadas if l.get("es_bloqueo")),
            # El sistema externo fallo: timeout, credencial, HTTP 400. Aca si
            # hay algo roto, y quien atiende tiene que reportarlo.
            "errores": sum(1 for l in llamadas
                           if not l["exito"] and not l.get("es_bloqueo")),
        },
    })


@app.get("/conversaciones/<id_conversacion>/sincronizaciones")
def conversaciones_sincronizaciones(id_conversacion):
    """
    Que efectos externos de esta conversacion quedaron sin hacer (B4).

    Solo lectura y SIN 'datos_intencion': lo que la pantalla necesita es que
    falto y si alguien tiene que mirarlo, no los parametros con los que se iba
    a hacer. Tampoco sale nunca el cuerpo de la respuesta del sistema externo
    -- de el solo se guarda el codigo (X19).

    Esta ruta NO reintenta nada. El reconciliador (T20) corre aparte con su
    propia cadencia, y lo que quedo 'desconocida' no vuelve a intentarse solo:
    espera a una persona, que es justo lo que este panel deja ver.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400

    try:
        pendientes = persistencia.sincronizaciones_de(tenant, id_conversacion)
    except RuntimeError as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 404
    except Exception as e:
        registrar("reconciliador", "fallo al leer las sincronizaciones",
                  conversation_id=id_interno(id_conversacion), error=e)
        return jsonify({"error": "No se pudo leer el estado de sincronizacion."}), 500

    return jsonify({"sincronizaciones": pendientes})


@app.get("/conversaciones/<id_conversacion>/acciones")
def conversaciones_acciones(id_conversacion):
    """
    Las acciones que la IA propuso en esta conversacion, con su estado REAL (B5).

    Antes de B5 una accion terminaba en 'aprobada' y nada mas -- que es lo que
    alguien decidio, no lo que paso. Ahora el estado dice como termino:
    ejecutada_ok, ejecutada_fallo, vencida o desconocida. Decir 'aprobada' de
    algo que fallo es afirmar un efecto que no ocurrio.

    Solo lectura y SIN 'argumentos': ahi estan los valores reales con los que
    se iba a escribir afuera. Para decidir alcanza el resumen.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400

    try:
        acciones = persistencia.acciones_de_conversacion(tenant, id_conversacion)
    except RuntimeError as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 404
    except Exception as e:
        registrar("acciones", "fallo al leer las acciones de la conversacion",
                  conversation_id=id_interno(id_conversacion), error=e)
        return jsonify({"error": "No se pudieron leer las acciones."}), 500

    return jsonify({"acciones": acciones})


"""
Los campos de la ficha del cliente que la Bandeja puede mostrar.

Es una lista blanca EXPLICITA y no la del rol: 'campos_permitidos' del rol
decide que ve el MODELO, y esto decide que ve una PERSONA autenticada en la
pantalla. Son dos preguntas distintas y mezclarlas haria que ampliar una
ampliara la otra sin que nadie lo decida.

Lo que NO esta, y por que: contrasenas de cualquier tipo, coordenadas y
cualquier campo de red del equipo. La ficha responde "quien es este cliente y
como esta su servicio", no "como entro a su router".
"""
CAMPOS_FICHA_CLIENTE = (
    "id_servicio", "nombre", "cedula", "estado", "telefono", "email",
    "direccion", "localidad", "ciudad", "plan_internet", "zona",
    "fecha_instalacion", "estado_facturas", "saldo", "fecha_corte",
)


@app.get("/conversaciones/<id_conversacion>/cliente")
def conversaciones_cliente(id_conversacion):
    """
    La ficha del cliente, LEIDA EN VIVO del sistema del ISP.

    POR QUE EN VIVO Y NO GUARDADA
    -----------------------------
    El plan, el estado del servicio, el saldo y la fecha de corte cambian sin
    que esta conversacion se entere. Una copia guardada envejece en silencio,
    y en esta pantalla se usa para decidir: decirle a alguien que el cliente
    esta al dia cuando lleva dos meses cortado es peor que no decirle nada.
    Ademas, el PRD prohibe persistir las respuestas crudas de la API externa
    -- traen contrasenas, GPS y documento.

    Por eso esta ruta lee y devuelve, sin escribir una sola fila.

    REUSA LA HERRAMIENTA DEL TENANT, NO UNA URL PROPIA
    --------------------------------------------------
    Llama a 'consultar_cliente' tal como esta declarada en la config de la
    empresa. Eso no es comodidad: es lo que hace que el subdominio, la
    credencial (auth_ref) y el filtro verificado salgan de la configuracion
    del tenant y no de una constante en este archivo. Una empresa nueva se
    conecta editando su config, sin tocar codigo -- que es la regla de
    arquitectura del repo.

    Si la empresa no declara la herramienta, o no tiene cargada la credencial,
    NO es un error del servidor: es que este tenant todavia no tiene conectado
    su sistema. Se contesta 200 con 'disponible: false' y el motivo, y la
    pantalla dibuja un estado vacio honesto en vez de un error rojo.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400

    try:
        identidad = persistencia.identidad_de_conversacion(tenant, id_conversacion)
    except RuntimeError as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 404
    except Exception as e:
        registrar("cliente", "fallo al leer la identidad de la conversacion",
                  conversation_id=id_interno(id_conversacion), error=e)
        return jsonify({"error": "No se pudo leer la conversacion."}), 500

    if not identidad:
        return jsonify({"error": "No existe esa conversacion."}), 404

    id_servicio = (identidad.get("id_cliente") or "").strip()
    if not id_servicio:
        # El asistente todavia no identifico al cliente. No es una falla: una
        # conversacion recien abierta por un numero desconocido esta asi.
        return jsonify({"disponible": False, "motivo": "sin_identificar", "cliente": None})

    config = _config_de(tenant)
    herramienta = next((h for h in config.herramientas if h.nombre == "consultar_cliente"), None)
    if herramienta is None:
        return jsonify({"disponible": False, "motivo": "sin_herramienta", "cliente": None})

    try:
        crudo = ejecutor_http.ejecutar(
            herramienta, {"id_servicio": id_servicio}, tenant=tenant,
            variables_tenant=getattr(config, "variables_tenant", None))
    except Exception as e:
        # Ni el mensaje ni el error llevan datos del cliente: el fallo es de
        # conexion o de credencial, y lo que se pidio fue un identificador.
        registrar("cliente", "no se pudo leer la ficha del cliente",
                  conversation_id=id_interno(id_conversacion), error=e)
        return jsonify({"disponible": False, "motivo": "sin_conexion", "cliente": None})

    # Una coleccion paginada contesta {"results": [...]} aun filtrando por un
    # id que es unico, asi que la ficha viene adentro de una lista de uno. Se
    # acepta tambien una lista desnuda: que forma tiene la respuesta depende
    # del sistema que cada empresa tenga conectado, y este archivo no conoce
    # ninguno en particular.
    # Si no vino ninguna fila, el cliente no existe alla -- que TAMBIEN es una
    # respuesta util y no un error.
    filas = crudo.get("results") if isinstance(crudo, dict) else crudo
    fila = (filas or [None])[0] if isinstance(filas, list) else None
    if not isinstance(fila, dict):
        return jsonify({"disponible": False, "motivo": "no_encontrado", "cliente": None})

    ficha = {}
    for campo in CAMPOS_FICHA_CLIENTE:
        valor = fila.get(campo)
        # Los catalogos del sistema externo suelen venir anidados
        # y lo que se muestra es el nombre; el id no le dice nada a nadie.
        if isinstance(valor, dict):
            valor = valor.get("nombre") or valor.get("id")
        if valor not in (None, ""):
            ficha[campo] = valor

    # Sin 'registrar' de los valores: esta respuesta es la ficha personal de
    # alguien y no entra a ningun log ni a ninguna traza.
    return jsonify({"disponible": True, "motivo": None, "cliente": ficha})


"""
Cuanto vale una lectura optica antes de volver a pedirla.

CINCO MINUTOS, Y EL NUMERO NO ES ARBITRARIO: la consulta profunda tarda ~10
segundos y el proveedor pide expresamente no usarla en polling ni en bulk
(skill 'smartolt-api', verificado el 14/08/2026). Sin cache, cambiar de
pestaña dos veces serian dos consultas; con cinco minutos, una conversacion
que se atiende en una sentada hace UNA.

Es el mismo TTL que ya usa la verificacion de sesion del frontend, por la
misma razon: es el tiempo que alguien tolera ver un dato de hace un rato sin
que deje de ser util.
"""
SEGUNDOS_CACHE_OPTICA = 300

# (tenant, serial) -> (momento, payload). En memoria del proceso y a
# proposito: es una lectura de un sistema externo y el PRD prohibe
# persistirla. Si el motor se reinicia, se vuelve a consultar, que es
# exactamente lo correcto.
_optica: dict[tuple[str, str], tuple[float, dict]] = {}
_optica_lock = threading.Lock()


def _serial_de(identidad: dict) -> str:
    """El serial del equipo, de la sesion de la conversacion."""
    datos = identidad.get("datos_sesion") or {}
    if isinstance(datos, str):
        try:
            datos = json.loads(datos)
        except Exception:
            datos = {}
    return str((datos or {}).get("sn_onu") or "").strip()


# Las rutas EXACTAS de lo que puede salir de la lectura profunda.
#
# POR QUE UNA LISTA BLANCA Y NO UN FILTRO DE LO MALO: la misma respuesta trae
# 'ONU details.Description', que es el NOMBRE COMPLETO del cliente en el
# registro de la ONU. Una lista negra deja pasar lo que el proveedor agregue
# manana; esta nombra lo que sale, campo por campo, y todo lo demas se queda.
#
# Los cinco primeros son (destino, seccion, campo). La MAC y el conteo de
# equipos tienen forma propia --viven bajo indices numericos-- y se resuelven
# aparte, abajo.
CAMPOS_PROFUNDOS = (
    ("temperatura", "Optical status", "Temperature(C)"),
    ("tx", "Optical status", "Tx optical power(dBm)"),
    ("olt_rx", "Optical status", "OLT Rx ONT optical power(dBm)"),
    ("encendido", "ONU details", "ONT online duration"),
    ("perfil", "ONU details", "Line profile name"),
)


def _profundidad_de(completo: dict) -> dict | None:
    """Lo que la pantalla puede mostrar de la lectura profunda, y nada mas.

    Vive aparte del endpoint para poder probarse: las rutas son cadenas, y un
    espacio de mas en "Tx optical power(dBm)" no falla -- devuelve None en
    silencio, que es la clase de error que nadie ve hasta que un operador
    pregunta por que la temperatura siempre esta vacia.
    """
    salida: dict = {}
    for destino, seccion, campo in CAMPOS_PROFUNDOS:
        bloque = completo.get(seccion)
        if not isinstance(bloque, dict):
            continue
        valor = bloque.get(campo)
        if valor not in (None, ""):
            salida[destino] = valor

    # La MAC vive bajo un indice numerico ('1', '2', ...): se toma la de la
    # PRIMERA interfaz WAN y no se concatenan todas -- un equipo con dos WAN
    # tiene dos MAC y elegir una a ojo seria inventar.
    wan = completo.get("ONU WAN Interfaces")
    if isinstance(wan, dict):
        for clave in sorted(k for k in wan if isinstance(wan[k], dict)):
            mac = (wan[clave] or {}).get("MAC address")
            if mac:
                salida["mac"] = mac
                break

    # CUANTOS EQUIPOS SE VEN detras de la ONU. Es un conteo, no una lista: las
    # MAC de los aparatos de una casa son dato personal, y el numero contesta
    # la unica pregunta que la pantalla hace -- si hay algo del otro lado.
    macs = completo.get("MACs on OLT from this ONU")
    if isinstance(macs, dict):
        cuantos = sum(1 for v in macs.values() if isinstance(v, dict))
        if cuantos:
            salida["dispositivos"] = cuantos

    return salida or None


@app.get("/conversaciones/<id_conversacion>/optica")
def conversaciones_optica(id_conversacion):
    """
    Como esta el equipo del cliente AHORA: enlace y potencia optica.

    LAS DOS LIVIANAS, NO LA PROFUNDA. Usa 'consultar_estado_ont' y
    'consultar_senal_ont', que contestan rapido. El diagnostico profundo
    ('diagnosticar_falla_ont') tarda ~10 segundos y el proveedor pide no
    automatizarlo: ese se pide aparte y a proposito, nunca al abrir una
    pantalla.

    NO SE GUARDA. Se cachea en memoria del proceso por
    SEGUNDOS_CACHE_OPTICA y nada mas: el PRD prohibe persistir las
    respuestas crudas del sistema externo. 'forzar=1' salta el cache -- es
    lo que hace el boton "Consultar ahora" cuando alguien quiere el dato
    del segundo, no el de hace cuatro minutos.

    Devuelve SIEMPRE 'leido_en' junto al dato. Una medicion sin su hora es
    una afirmacion sobre el presente que puede tener cinco minutos, y en
    esta pantalla se usa para decidir si mandar un tecnico.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    forzar = request.args.get("forzar") in ("1", "true", "si")
    # LA LECTURA PROFUNDA VA APARTE, Y SOLO CUANDO ALGUIEN LA PIDE.
    # 'get_onu_full_status_info' tarda ~10 s y el proveedor pide no usarla en
    # bucle (skill 'smartolt-api', 14/08/2026). Las dos lecturas livianas
    # --estado y senal-- siguen respondiendo en el acto y son las que se hacen
    # solas; esta la dispara el boton. Mezclarlas haria que abrir una
    # conversacion costara diez segundos.
    profundo = request.args.get("profundo") in ("1", "true", "si")

    try:
        identidad = persistencia.identidad_de_conversacion(tenant, id_conversacion)
    except Exception as e:
        registrar("optica", "fallo al leer la conversacion",
                  conversation_id=id_interno(id_conversacion), error=e)
        return jsonify({"error": "No se pudo leer la conversacion."}), 500
    if not identidad:
        return jsonify({"error": "No existe esa conversacion."}), 404

    serial = _serial_de(identidad)
    if not serial:
        # El asistente todavia no identifico el equipo. No es una falla.
        return jsonify({"disponible": False, "motivo": "sin_equipo", "optica": None})

    clave = (tenant, serial)
    if not forzar:
        with _optica_lock:
            guardado = _optica.get(clave)
        if guardado and (time.monotonic() - guardado[0]) < SEGUNDOS_CACHE_OPTICA:
            return jsonify(guardado[1])

    config = _config_de(tenant)
    por_nombre = {h.nombre: h for h in config.herramientas}
    estado_h = por_nombre.get("consultar_estado_ont")
    senal_h = por_nombre.get("consultar_senal_ont")
    if estado_h is None and senal_h is None:
        return jsonify({"disponible": False, "motivo": "sin_herramienta", "optica": None})

    variables = getattr(config, "variables_tenant", None)

    def _leer(herramienta):
        if herramienta is None:
            return None
        try:
            return ejecutor_http.ejecutar(herramienta, {"sn_onu": serial},
                                          tenant=tenant, variables_tenant=variables)
        except Exception as e:
            # Que una de las dos falle no invalida la otra: una ONU offline
            # no tiene lectura de senal util, y eso no es un error.
            registrar("optica", "no se pudo leer una medicion del equipo",
                      conversation_id=id_interno(id_conversacion),
                      herramienta=herramienta.nombre, error=e)
            return None

    estado = _leer(estado_h)
    senal = _leer(senal_h)
    if estado is None and senal is None:
        return jsonify({"disponible": False, "motivo": "sin_conexion", "optica": None})

    # DONDE esta conectado el equipo. Es una tercera lectura y es opcional a
    # proposito: si la empresa no declara la herramienta, o el sistema no la
    # contesta, la potencia y el estado se muestran igual. La topologia
    # explica una falla; no es lo que hace falta para verla.
    topologia = None
    detalle = _leer(por_nombre.get("consultar_topologia_ont"))
    if isinstance(detalle, dict):
        # LISTA BLANCA, y acá importa especialmente: la respuesta de detalle
        # trae 'name' -- el NOMBRE COMPLETO del cliente en el registro de la
        # ONU. Es el mismo dato personal que ya se cuida en todo lo demas, y
        # por esta puerta no sale: la pantalla ya sabe con quien habla.
        topologia = {}
        # 'onu_type_name' es el MODELO del equipo, y ya venia en esta misma
        # respuesta: medido el 22/09/2026 contra la instancia de Rapilink, 82
        # campos, y ahi estaba. Se habia dado por inexistente leyendo la lista
        # parcial de la skill -- que aclara "60+ campos totales, no todos
        # abajo". Concluir desde una lista parcial es el error que la regla
        # "la documentacion es una hipotesis" existe para evitar.
        for campo in ("olt_name", "olt_id", "board", "port", "onu",
                      "zone_name", "odb_name", "onu_type_name"):
            valor = detalle.get(campo)
            if isinstance(valor, dict):
                valor = valor.get("nombre") or valor.get("name") or valor.get("id")
            if valor not in (None, ""):
                topologia[campo] = valor
        topologia = topologia or None

    # LO QUE SOLO SABE LA LECTURA PROFUNDA: temperatura del modulo optico,
    # potencia de subida medida en la OLT, MAC de la interfaz WAN y el perfil
    # de linea. Medido el 22/09/2026 contra la instancia de Rapilink: los
    # cuatro estan en la respuesta, y ninguno estaba llegando a la pantalla.
    #
    # LISTA BLANCA POR RUTA EXACTA, y aca no es una formalidad: la misma
    # respuesta trae 'ONU details.Description', que es el NOMBRE COMPLETO del
    # cliente. Se nombran los campos que salen, uno por uno; lo que no este en
    # esta tupla no puede salir aunque el proveedor lo agregue manana.
    profundidad = None
    if profundo:
        completo = _leer(por_nombre.get("diagnosticar_falla_ont"))
        if isinstance(completo, dict):
            profundidad = _profundidad_de(completo)

    # El umbral viaja con la medicion: sin el, la pantalla puede mostrar la
    # potencia pero no decir si esta bien o mal. Y decirlo con un numero
    # inventado seria peor que no decirlo -- ver TenantConfig.umbral_rx_dbm.
    umbral = getattr(config, "umbral_rx_dbm", None)

    payload = {
        "disponible": True,
        "motivo": None,
        "leido_en": datetime.now(timezone.utc).isoformat(),
        "umbral_rx_dbm": umbral,
        "optica": {"serial": serial, "estado": estado, "senal": senal,
                   "topologia": topologia, "profundidad": profundidad},
    }

    # UNA LECTURA LIVIANA NO BORRA LA PROFUNDA. Si alguien ya pago los diez
    # segundos y despues se refresca lo barato, la temperatura y la MAC tienen
    # que seguir ahi: se arrastra lo que habia, marcado con SU hora, que es lo
    # que deja ver que es mas vieja que el resto.
    if profundidad is None:
        with _optica_lock:
            previo = _optica.get(clave)
        anterior = ((previo[1].get("optica") or {}) if previo else {}).get("profundidad")
        if anterior:
            payload["optica"]["profundidad"] = anterior
            payload["profundidad_leida_en"] = (previo[1] or {}).get(
                "profundidad_leida_en") or (previo[1] or {}).get("leido_en")
    else:
        payload["profundidad_leida_en"] = payload["leido_en"]
    with _optica_lock:
        _optica[clave] = (time.monotonic(), payload)
    return jsonify(payload)


@app.post("/conversaciones/<id_conversacion>/equipo/reiniciar")
def conversaciones_reiniciar_equipo(id_conversacion):
    """
    Una PERSONA reinicia el equipo del cliente desde la Bandeja.

    POR QUE ESTO NO CONTRADICE LA COLA DE ACCIONES
    ----------------------------------------------
    La cola de acciones propuestas existe para lo que decide el MODELO: el
    asistente no puede cortarle el servicio a nadie por su cuenta, y por eso
    lo que propone espera una aprobacion. Acá el actor es otro -- una persona
    autenticada, con el caso en la mano, que es quien en cualquier NOC aprieta
    ese boton. No se salta la confirmacion del modelo: es una puerta distinta,
    para un actor distinto, y con sus propias condiciones.

    Y ESAS CONDICIONES VIVEN ACA, NO EN EL NAVEGADOR. El dialogo de
    confirmacion de la pantalla es cortesia; si alguien llama a esta ruta
    directo, el dialogo no existe. Lo que de verdad protege es esto:

      400  sin motivo (obligatorio: queda en el expediente)
      403  quien pide no es el dueño de la conversacion ni ADMIN
      404  no existe, o no se sabe cual es el equipo
      409  la lleva la IA, o esta cerrada -- reiniciar no es un gesto que
           corresponda hacer por encima del asistente sin tomarla primero

    El actor y su rol los arma el proxy DESDE LA SESION (el JWT ya verificado
    contra el backend), nunca el navegador -- mismo mecanismo que /reasignar.

    Cuerpo: {tenant, autor, autor_usuario_id, autor_rol, motivo}
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400

    motivo = (cuerpo.get("motivo") or "").strip()
    if not motivo:
        return jsonify({"error": "Hace falta un motivo: queda en el expediente."}), 400

    autor_id = (cuerpo.get("autor_usuario_id") or "").strip()
    autor_nombre = (cuerpo.get("autor") or "").strip()
    es_admin = (cuerpo.get("autor_rol") or "").upper() == "ADMIN"
    if not autor_id:
        return jsonify({"error": "No se sabe quien pide el reinicio."}), 400

    try:
        identidad = persistencia.identidad_de_conversacion(tenant, id_conversacion)
    except Exception as e:
        registrar("equipo", "fallo al leer la conversacion",
                  conversation_id=id_interno(id_conversacion), error=e)
        return jsonify({"error": "No se pudo leer la conversacion."}), 500
    if not identidad:
        return jsonify({"error": "No existe esa conversacion."}), 404

    # La lleva la IA: reiniciar por encima del asistente, sin tomarla, deja al
    # cliente con el servicio cortado y una conversacion que sigue automatica.
    if (identidad.get("control") or "ia") != "humano":
        return jsonify({"error": "Tomá la conversación antes de tocar el equipo."}), 409

    if (identidad.get("estado") or "") == "cerrada":
        return jsonify({"error": "La conversación está cerrada."}), 409

    # Dueño o ADMIN. El mismo criterio que ya usan soltar y reasignar: quien
    # solo esta mirando no actua sobre el equipo de un caso ajeno.
    #
    # EL DUEÑO LO DICE LA BASE, NO EL PEDIDO. La primera version leia
    # 'duenio_usuario_id' del cuerpo, que es exactamente el agujero que este
    # bloque existe para tapar: quien llama la ruta decidiria contra quien se
    # compara. Sale de la fila.
    duenio = str(identidad.get("asignada_a_usuario_id") or "").strip()
    if not es_admin and duenio and duenio != autor_id:
        return jsonify({"error": "La conversación la tiene otra persona."}), 403

    serial = _serial_de(identidad)
    if not serial:
        return jsonify({"error": "No se sabe cuál es el equipo de este cliente."}), 404

    config = _config_de(tenant)
    herramienta = next((h for h in config.herramientas if h.nombre == "reiniciar_ont"), None)
    if herramienta is None:
        return jsonify({"error": "Esta empresa no tiene conectado el reinicio de equipos."}), 409

    # M06-F: EL EFECTO VA POR LA MISMA CADENA QUE CUALQUIER R3.
    #
    # Hasta aca esta ruta llamaba al ejecutor directo. Es una persona la que
    # decide, y eso no cambia: pero un reinicio es irreversible (M06-A) y la
    # frontera solo lo deja salir con una aprobacion atada a la accion exacta.
    # En vez de abrir una segunda puerta, el boton hace lo que haria la cola:
    #
    #   1. deja la propuesta en asistente.acciones_propuestas, ya ligada a esta
    #      conversacion, con la huella de sus argumentos y un origen propio;
    #   2. la aprueba QUIEN APRIETA EL BOTON (su nombre queda en el sello);
    #   3. y sigue los mismos pasos que /acciones/propuestas/<id>/aprobar:
    #      kill switch, techo, etapa, autorizacion, sello, previas frescas,
    #      idempotencia, frontera, efecto, desenlace con su evento.
    #
    # Las cuatro condiciones de arriba -- motivo, control humano, dueño o
    # ADMIN, conversacion abierta -- siguen siendo las de esta ruta; la cadena
    # se suma, no las reemplaza.
    quien = autor_nombre or autor_id
    argumentos = {"sn_onu": serial}
    sesion_min = Sesion(identificador_canal=quien)
    sesion_min.sn_onu = serial
    if identidad.get("id_cliente"):
        sesion_min.id_cliente = identidad.get("id_cliente")
    try:
        accion_id, _ = persistencia.guardar_accion_propuesta(
            tenant, herramienta.nombre, argumentos,
            _resumen_de_reinicio(herramienta, argumentos), "bandeja", quien,
            str(id_conversacion),
            herramienta.aprobacion.vigencia_minutos if herramienta.aprobacion else None,
            hash_argumentos=idempotencia.hash_de(argumentos),
            origen=f"bandeja:{id_conversacion}:{uuid.uuid4()}",
            contexto=motor._contexto_de_revalidacion(config, herramienta,
                                                     sesion_min, None))
    except Exception as e:
        registrar("equipo", "no se pudo dejar el reinicio en la cola",
                  conversation_id=id_interno(id_conversacion), error=e)
        return jsonify({"error": "No se pudo registrar el pedido de reinicio. "
                                 "No se reinicio nada."}), 500

    # El rastro de quien lo hizo y por que. El motivo es obligatorio justamente
    # para que este renglon exista: dentro de un mes, saber por que alguien
    # corto el servicio vale mas que los segundos que costo escribirlo.
    # 'autor_nombre' NO va al log -- solo al expediente.
    registrar("equipo", "reinicio pedido por una persona",
              conversation_id=id_interno(id_conversacion),
              autor_usuario_id=autor_id, con_motivo=bool(motivo),
              accion_id=accion_id)

    salida = _aprobar_y_ejecutar(config, tenant, accion_id, quien)
    respuesta, codigo_http = salida if isinstance(salida, tuple) else (salida, 200)
    cuerpo_respuesta = respuesta.get_json() or {}
    if codigo_http == 200 and cuerpo_respuesta.get("ok"):
        return jsonify({"ok": True, "reiniciado": True, "verificando": True,
                        "autor": autor_nombre, "motivo": motivo,
                        "accion_id": accion_id})
    cuerpo_respuesta.setdefault("error", "No se reinicio el equipo.")
    cuerpo_respuesta["accion_id"] = accion_id
    return jsonify(cuerpo_respuesta), codigo_http


def _resumen_de_reinicio(herramienta, argumentos: dict) -> str:
    """El resumen de la propuesta que deja el boton: el de la plantilla del
    tenant, igual que una propuesta del modelo."""
    if herramienta.plantilla_resumen:
        try:
            return herramienta.plantilla_resumen.format(**argumentos)
        except (KeyError, IndexError):
            pass
    return f"{herramienta.nombre}(sn_onu={argumentos.get('sn_onu')})"


@app.get("/conversaciones/<id_conversacion>/equipo")
def conversaciones_equipo(id_conversacion):
    """
    Que se le hizo al equipo del cliente en esta conversacion, y si funciono.

    Solo lectura y SIN las mediciones crudas: son respuestas del sistema
    externo, y por esta puerta no salen -- mismo criterio que /herramientas,
    que devuelve el resultado de cada llamada y nunca el dato consultado.

    Esta ruta NO ejecuta nada. Reiniciar una ONU corta el servicio de alguien
    y pasa por la cola de acciones propuestas (PRD 7.4, fail-closed en
    codigo); exponer un boton que la ejecute desde aca seria abrir una segunda
    puerta a la misma accion, sin la confirmacion que la primera exige.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400

    try:
        acciones = persistencia.acciones_sobre_el_equipo(tenant, id_conversacion)
    except RuntimeError as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 404
    except Exception as e:
        registrar("verificacion", "fallo al leer las acciones sobre el equipo",
                  conversation_id=id_interno(id_conversacion), error=e)
        return jsonify({"error": "No se pudo leer el registro de acciones."}), 500

    return jsonify({"acciones": acciones})


@app.get("/conversaciones/<id_conversacion>/relevo")
def conversaciones_relevo(id_conversacion):
    """
    Como llego esta conversacion a las manos en las que esta.

    El relevo escribe un evento por transicion desde B3.3, y hasta ahora nadie
    los leia: la pantalla decia QUIEN la lleva, no COMO llego. Una reasignacion
    de supervisor y una devolucion a la IA se veian igual desde afuera -- la
    conversacion aparecia en otras manos y no habia donde mirar por que.

    Solo lectura, mismo criterio de auditoria que /herramientas: lo que sale
    son tipos de transicion, quien actuo y los datos que el propio contrato
    declara para cada tipo (ver ESQUEMAS en nucleo/relevo/transiciones.py).
    Nunca texto del cliente ni respuestas de un sistema externo.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400

    try:
        eventos = persistencia.eventos_de_relevo(tenant, id_conversacion)
    except RuntimeError as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 404
    except Exception as e:
        # Sin el nombre de quien actuo en el log: autor_nombre no va a
        # telemetria (D2), ni siquiera cuando algo falla leyendolo.
        registrar("relevo", "fallo al leer el registro de relevo",
                  conversation_id=id_interno(id_conversacion), error=e)
        return jsonify({"error": "No se pudo leer el registro de relevo."}), 500

    return jsonify({"eventos": eventos})


@app.post("/conversaciones/<id_conversacion>/mensajes/<mensaje_id>/marcar")
def conversaciones_marcar_ejemplo(id_conversacion, mensaje_id):
    """
    Marca una respuesta puntual del agente como buen ejemplo de un caso --
    base del manual de procedimientos (ver /manual mas abajo). Solo marca
    lo BUENO: no hay contraparte de "invalida" ni correccion en el momento
    (decision del cliente, ver el plan de esta funcionalidad).
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    caso = cuerpo.get("caso")
    marcado_por = cuerpo.get("marcado_por")
    if not tenant or not caso:
        return jsonify({"error": "Faltan campos: tenant, caso"}), 400

    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    # Fail-closed, mismo criterio que cualquier enum del proyecto: un caso
    # fuera de tenant_config.manual.casos se rechaza, nunca se guarda tal cual.
    if caso not in config.manual.casos:
        return jsonify({"error": f"'{caso}' no esta en la lista de casos "
                                 f"configurada (manual.casos)."}), 400

    try:
        persistencia.marcar_ejemplo(tenant, id_conversacion, mensaje_id, caso, marcado_por)
    except Exception as e:
        registrar("manual", "fallo al marcar ejemplo", error=e)
        return jsonify({"error": "No se pudo guardar el marcado."}), 500

    return jsonify({"ok": True, "caso": caso}), 201


@app.delete("/conversaciones/<id_conversacion>/mensajes/<mensaje_id>/marcar")
def conversaciones_desmarcar_ejemplo(id_conversacion, mensaje_id):
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400

    try:
        persistencia.desmarcar_ejemplo(tenant, mensaje_id)
    except Exception as e:
        registrar("manual", "fallo al desmarcar ejemplo", error=e)
        return jsonify({"error": "No se pudo deshacer el marcado."}), 500

    return "", 204


@app.post("/sugerencias")
def sugerencias():
    """
    Copiloto documental: que dice la documentacion interna sobre este texto.

    Recupera fragmentos y NO llama al modelo -- no redacta una respuesta, le
    acerca al colaborador lo que ya esta escrito, con su procedencia, y la
    persona decide. Cuesta un embedding y una consulta; el LLM no se toca.

    POST y no GET a proposito: 'texto' suele ser el mensaje del cliente y
    puede traer datos personales. En GET viajaria en la URL y quedaria escrito
    en el log de acceso del servidor, que es justo lo que el resto del sistema
    evita (PRD RNF-01).

    El 'rol' decide que documentos se pueden ver (documents.roles_permitidos).
    Por defecto 'soporte': quien abre esta pantalla esta autenticado en el CRM
    y atiende, no es un cliente. Es un default deliberado -- si esto se
    expusiera a un canal de cliente, habria que mandar el rol siempre.
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    texto = (cuerpo.get("texto") or "").strip()
    rol = cuerpo.get("rol") or "soporte"

    if not tenant or not texto:
        return jsonify({"error": "Faltan campos: tenant, texto"}), 400

    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    if rol not in config.roles:
        return jsonify({"error": f"El rol '{rol}' no existe."}), 400

    try:
        fragmentos, mejor = recuperar(config, tenant, rol, texto)
    except Exception as e:
        # Nunca rompe la pantalla del colaborador: es una ayuda lateral, no el
        # contenido principal. Mismo criterio que el RAG dentro de motor.py.
        registrar("sugerencias", "no se pudo recuperar", error=e)
        return jsonify({"error": "No se pudo consultar la documentacion."}), 502

    return jsonify({
        "sugerencias": [
            {"codigo": f.codigo, "titulo": f.titulo, "version": f.version,
             "contenido": f.contenido, "similitud": round(f.similitud, 3)}
            for f in fragmentos
        ],
        # Cuanto se acerco lo mejor que habia, aunque no pasara el umbral.
        # Distingue "no hay nada de este tema" de "hay algo casi util".
        "mejor_similitud": round(mejor, 3) if mejor is not None else None,
    })


# =============================================================================
#  MANUAL  -  ejemplos marcados, agrupados por caso/proceso
# =============================================================================

@app.get("/manual/casos")
def manual_casos():
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400

    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    return jsonify({"casos": config.manual.casos})


@app.put("/manual/casos")
def manual_casos_guardar():
    """
    Reemplaza la lista completa de tipos de caso, no un caso suelto: asi la
    interfaz manda lo que quedo en pantalla y no hay que resolver ordenes ni
    renombrados con operaciones parciales. El editor valida el conjunto
    entero (ver _mutar_casos_manual) y lo guarda versionado.
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400

    casos = cuerpo.get("casos")
    if not isinstance(casos, list):
        return jsonify({"error": "'casos' tiene que ser una lista."}), 400

    try:
        config = editor.guardar_casos_manual(tenant, casos)
    except editor.ErrorEdicion as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except Exception as e:
        return _error_al_guardar(e)

    return jsonify({"casos": config.manual.casos})


@app.get("/manual/ejemplos")
def manual_ejemplos():
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400

    try:
        ejemplos = persistencia.ejemplos_por_caso(tenant, request.args.get("caso"))
    except Exception as e:
        registrar("manual", "fallo al leer ejemplos", error=e)
        return jsonify({"error": "No se pudieron leer los ejemplos."}), 500

    return jsonify({"ejemplos": ejemplos})


@app.get("/manual/revisiones")
def manual_revisiones():
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400

    try:
        revisiones = persistencia.revisiones_de(tenant, request.args.get("estado"))
    except Exception as e:
        registrar("supervisor", "fallo al leer revisiones", error=e)
        return jsonify({"error": "No se pudieron leer las revisiones."}), 500

    return jsonify({"revisiones": revisiones})


def _actualizar_revision(id_revision, estado_nuevo):
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400

    try:
        existe = persistencia.actualizar_estado_revision(
            tenant, id_revision, estado_nuevo, cuerpo.get("revisado_por"))
    except Exception as e:
        registrar("supervisor", "fallo al actualizar revision", error=e)
        return jsonify({"error": "No se pudo guardar."}), 500

    if not existe:
        return jsonify({"error": f"La revision '{id_revision}' no existe."}), 404
    return jsonify({"ok": True, "estado": estado_nuevo})


@app.post("/manual/revisiones/<id_revision>/aprobar")
def manual_revisiones_aprobar(id_revision):
    return _actualizar_revision(id_revision, "aprobado")


@app.post("/manual/revisiones/<id_revision>/descartar")
def manual_revisiones_descartar(id_revision):
    return _actualizar_revision(id_revision, "descartado")


# =============================================================================
#  CONFIGURACION GUIADA  -  propuestas de herramienta nuevas, pendientes de
#  aprobacion humana. Ver tenants/rapilink.config.yaml, rol
#  'configuracion_guiada', y nucleo/config/editor.py::
#  aprobar_herramienta_propuesta para el porque esto no salta la regla de
#  "crear una herramienta es trabajo de codigo".
# =============================================================================

@app.get("/configuracion/propuestas")
def configuracion_propuestas():
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        propuestas = persistencia.herramientas_propuestas_de(tenant, request.args.get("estado"))
    except Exception as e:
        registrar("configuracion-guiada", "fallo al leer propuestas", error=e)
        return jsonify({"error": "No se pudieron leer las propuestas."}), 500
    return jsonify({"propuestas": propuestas})


@app.post("/configuracion/propuestas/<id_propuesta>/aprobar")
def configuracion_propuesta_aprobar(id_propuesta):
    """
    Escribe la herramienta propuesta al catalogo REAL (editor.py) y recien
    despues marca la propuesta como 'aprobada' -- en ese orden, para que un
    borrador mal armado (le falta un campo, un rol que no existe) quede
    visiblemente sin aprobar en vez de aprobado pero sin efecto.
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'."}), 400

    try:
        propuesta = persistencia.herramienta_propuesta_de(tenant, id_propuesta)
    except Exception as e:
        registrar("configuracion-guiada", "fallo al leer la propuesta", error=e)
        return jsonify({"error": "No se pudo leer la propuesta."}), 500
    if not propuesta:
        return jsonify({"error": f"La propuesta '{id_propuesta}' no existe."}), 404
    if propuesta["estado"] != "pendiente":
        return jsonify({"error": f"Esta propuesta ya esta '{propuesta['estado']}', "
                                 f"no se puede volver a aprobar."}), 400

    try:
        editor.aprobar_herramienta_propuesta(tenant, propuesta["herramienta_propuesta"])
    except editor.ErrorEdicion as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except Exception as e:
        return _error_al_guardar(e)

    olvidar_config(tenant)
    try:
        persistencia.resolver_herramienta_propuesta(
            tenant, id_propuesta, "aprobada", cuerpo.get("revisado_por"))
    except Exception as e:
        # La herramienta YA quedo escrita en el catalogo -- esto solo afecta
        # el rotulo de la propuesta. No se revierte lo ya guardado por esto.
        registrar("configuracion-guiada", "la herramienta se agrego pero no se pudo marcar la propuesta como aprobada", error=e)

    return jsonify({"ok": True, "estado": "aprobada"})


@app.post("/configuracion/propuestas/<id_propuesta>/rechazar")
def configuracion_propuesta_rechazar(id_propuesta):
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'."}), 400

    try:
        existe = persistencia.resolver_herramienta_propuesta(
            tenant, id_propuesta, "rechazada", cuerpo.get("revisado_por"),
            motivo_rechazo=cuerpo.get("motivo"))
    except Exception as e:
        registrar("configuracion-guiada", "fallo al rechazar", error=e)
        return jsonify({"error": "No se pudo guardar."}), 500

    if not existe:
        return jsonify({"error": f"La propuesta '{id_propuesta}' no existe."}), 404
    return jsonify({"ok": True, "estado": "rechazada"})


# =============================================================================
#  CONECTORES  -  conectar un sistema conocido eligiendolo de una lista.
#  Ver nucleo/conectores/catalogo.py.
#
#  'preparar' devuelve lo que VA a pasar sin que pase: cuantas herramientas
#  entran, cuales se saltean, que campos gana cada rol. Aplicar escribe datos
#  de clientes en el catalogo de un tenant -- que se pueda mirar antes no es
#  cortesia, es la unica forma de que la decision sea de una persona.
# =============================================================================

@app.get("/conectores")
def conectores_listar():
    try:
        return jsonify({"conectores": conectores.listar()})
    except Exception as e:
        registrar("conectores", "fallo al listar", error=e)
        return jsonify({"error": "No se pudieron leer los conectores."}), 500


@app.post("/conectores/<id_conector>/preparar")
def conectores_preparar(id_conector):
    """Que pasaria al aplicarlo. NO escribe nada."""
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'."}), 400
    try:
        plan = conectores.preparar(id_conector, cuerpo.get("areas") or {},
                                   _config_de(tenant))
    except conectores.ErrorConector as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404
    except Exception as e:
        registrar("conectores", "fallo al preparar", error=e)
        return jsonify({"error": "No se pudo preparar el conector."}), 500
    return jsonify({
        "conector": plan["conector"],
        # Solo los nombres: quien decide no necesita 25 definiciones completas,
        # necesita saber QUE entra y a quien.
        "nuevas": [{"nombre": h["nombre"], "roles": h["roles_permitidos"],
                    "escritura": not h.get("solo_lectura", True)}
                   for h in plan["nuevas"]],
        "salteadas": plan["salteadas"],
        "campos_por_rol": {r: {n: len(c) for n, c in v.items()}
                           for r, v in plan["campos_por_rol"].items()},
        "variables": plan["variables"],
        "secretos": plan["secretos"],
    })


@app.post("/conectores/<id_conector>/aplicar")
def conectores_aplicar(id_conector):
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'."}), 400
    try:
        plan = conectores.aplicar(tenant, id_conector, cuerpo.get("areas") or {})
    except conectores.ErrorConector as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except editor.ErrorEdicion as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except Exception as e:
        return _error_al_guardar(e)
    olvidar_config(tenant)
    return jsonify({"ok": True,
                    "agregadas": [h["nombre"] for h in plan["nuevas"]],
                    "salteadas": plan["salteadas"],
                    # Lo que TODAVIA falta: sin la credencial cargada, las
                    # herramientas estan en el catalogo y fallan al primer uso.
                    "faltan_secretos": plan["secretos"],
                    "faltan_variables": [v["nombre"] for v in plan["variables"]]})


# =============================================================================
#  CONSUMO  -  cuanto gasta la empresa, y en que punto del tope esta.
#  Ver nucleo/observabilidad/consumo.py.
#
#  EL ESTADO SE DECIDE ACA, NO EN LA PANTALLA. La maqueta original mostraba
#  "sin tope configurado", "0% del tope" y "asistente frenado por alcanzar el
#  tope" al mismo tiempo -- tres cosas que no pueden ser ciertas juntas. Peor:
#  sin tarifa cargada el costo es SIEMPRE cero, asi que el tope no puede
#  alcanzarse nunca y 'frenado' es inalcanzable en ese estado.
#
#  Si cada tarjeta decide sola si mostrarse, tarde o temprano se contradicen.
#  El servidor devuelve UN estado y la pantalla dibuja lo que corresponde.
# =============================================================================

@app.get("/consumo")
def consumo_resumen():
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        dias = max(1, min(int(request.args.get("dias") or 30), 366))
    except ValueError:
        dias = 30

    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    modelo = config.llm.modelo_por_defecto
    tarifas = config.llm.tarifas or {}
    hay_tarifa = modelo in tarifas
    gasto = consumo.estado_del_gasto(config, tenant)

    try:
        with persistencia.sesion(tenant) as (cur, org):
            cur.execute(
                """select dia, n_mensajes, tokens_entrada, tokens_salida, costo_usd
                     from asistente.usage_daily
                    where organization_id = %s
                      and dia > current_date - make_interval(days => %s)
                    order by dia desc""", (org, dias))
            filas = [{"dia": f["dia"].isoformat(), "n_mensajes": f["n_mensajes"],
                      "tokens_entrada": f["tokens_entrada"],
                      "tokens_salida": f["tokens_salida"],
                      "costo_usd": float(f["costo_usd"] or 0)}
                     for f in cur.fetchall()]

            # De OTRAS tablas: usage_daily tiene columnas n_conversaciones y
            # n_tool_calls que nadie escribe y siempre valen 0. No se sirven
            # desde ahi -- una cifra que siempre es cero se lee como "no pasa
            # nada" en vez de "no se mide".
            cur.execute(
                """select count(*) n,
                          percentile_disc(0.95) within group (order by duracion_ms) p95
                     from asistente.tool_calls
                    where organization_id = %s
                      and creado_en > now() - make_interval(days => %s)""",
                (org, dias))
            h = cur.fetchone() or {}
            cur.execute(
                """select count(*) n from asistente.conversations
                    where organization_id = %s
                      and creado_en > now() - make_interval(days => %s)""",
                (org, dias))
            c = cur.fetchone() or {}
    except Exception as e:
        registrar("consumo", "fallo al leer", error=e)
        return jsonify({"error": "No se pudo leer el consumo."}), 500

    return jsonify({
        "dias": dias,
        # 'sin_tarifa' gana sobre todo lo demas: sin ella el costo no existe y
        # cualquier cifra de gasto es ficcion. La pantalla no debe dibujar el
        # eje de costo, el medidor del tope ni el panel de frenado en ese
        # estado -- no porque queden feos, sino porque afirmarian algo falso.
        "estado": ("sin_tarifa" if not hay_tarifa
                   else "sin_tope" if not gasto["tope"]
                   else gasto["accion"]),
        "modelo": modelo,
        "hay_tarifa": hay_tarifa,
        # .model_dump() y no el objeto: desde que 'Tarifa' dejo de ser un
        # diccionario suelto para ganar validacion propia, Flask no la sabe
        # serializar y la ruta devolvia 500. La pantalla mostraba "no se pudo
        # contactar al asistente", que apunta a la red y no al dato.
        "tarifa": tarifas[modelo].model_dump() if hay_tarifa else None,
        "tope": gasto["tope"] or None,
        "gastado": gasto["gastado"],
        "porcentaje": gasto["porcentaje"],
        "mensaje_al_alcanzar_tope": config.limites.mensaje_al_alcanzar_tope or "",
        "dias_detalle": filas,
        "totales": {
            "n_mensajes": sum(f["n_mensajes"] for f in filas),
            "tokens_entrada": sum(f["tokens_entrada"] for f in filas),
            "tokens_salida": sum(f["tokens_salida"] for f in filas),
            "costo_usd": round(sum(f["costo_usd"] for f in filas), 6),
        },
        "herramientas": {"n": h.get("n") or 0, "p95_ms": h.get("p95")},
        "conversaciones": c.get("n") or 0,
    })


@app.put("/consumo/tarifa")
def consumo_guardar_tarifa():
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant, modelo = cuerpo.get("tenant"), cuerpo.get("modelo")
    if not tenant or not modelo:
        return jsonify({"error": "Faltan 'tenant' y 'modelo'."}), 400
    try:
        cache = cuerpo.get("entrada_cache")
        editor.guardar_tarifa(tenant, modelo,
                              float(cuerpo.get("entrada") or 0),
                              float(cuerpo.get("salida") or 0),
                              None if cache in (None, "") else float(cache),
                              descuento_fuera_pico=cuerpo.get("descuento_fuera_pico"),
                              ventanas_pico=cuerpo.get("ventanas_pico"))
    except editor.ErrorEdicion as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except (TypeError, ValueError):
        return jsonify({"error": "Las tarifas tienen que ser numeros."}), 400
    except Exception as e:
        return _error_al_guardar(e)
    olvidar_config(tenant)
    return jsonify({"ok": True})


@app.put("/consumo/tope")
def consumo_guardar_tope():
    """Guarda el tope mensual. Vacio o null lo saca; cero se rechaza."""
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta 'tenant'."}), 400
    crudo = cuerpo.get("tope")
    try:
        tope = None if crudo in (None, "") else float(crudo)
    except (TypeError, ValueError):
        return jsonify({"error": "El tope tiene que ser un numero."}), 400
    try:
        editor.guardar_tope_gasto(tenant, tope, cuerpo.get("mensaje"))
    except editor.ErrorEdicion as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except Exception as e:
        return _error_al_guardar(e)
    olvidar_config(tenant)
    return jsonify({"ok": True})


# =============================================================================
#  HABILIDADES  -  procedimientos que un agente carga cuando le hacen falta.
#  Ver nucleo/habilidades/catalogo.py (que son y por que no son documentos del
#  corpus) y analista.py (como se detecta que falta una).
#
#  Ninguna entra al prompt de ningun agente sin pasar por /aprobar: una
#  habilidad aprobada es lo que el agente va a seguir "al pie de la letra".
#  Mismo criterio que las propuestas de herramienta de aca arriba.
# =============================================================================

@app.get("/habilidades")
def habilidades_listar():
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        with persistencia.sesion(tenant) as (cur, org):
            cur.execute(
                """select h.id::text, h.codigo, h.nombre, h.cuando_usarla,
                          h.pasos, h.roles_permitidos, h.estado, h.origen,
                          h.evidencia, h.motivo_rechazo, h.creada_en,
                          h.aprobada_en, h.aprobada_por,
                          (select count(*) from asistente.habilidad_usos u
                            where u.habilidad_id = h.id) as usos
                     from asistente.habilidades h
                    where h.organization_id = %s
                    order by (h.estado = 'propuesta') desc, h.codigo""",
                (org,))
            filas = [dict(f) for f in cur.fetchall()]
    except Exception as e:
        registrar("habilidades", "fallo al leer", error=e)
        return jsonify({"error": "No se pudieron leer las habilidades."}), 500
    return jsonify({"habilidades": filas})


@app.post("/habilidades")
def habilidades_crear():
    """Crea una habilidad escrita a mano. Nace 'propuesta', igual que las del
    analista -- que la haya escrito una persona no la pone a operar sola."""
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    faltan = [c for c in ("codigo", "nombre", "cuando_usarla", "pasos")
              if not str(cuerpo.get(c) or "").strip()]
    if not tenant or faltan:
        return jsonify({"error": f"Faltan campos: {['tenant'] if not tenant else []}"
                                 f"{faltan}"}), 400
    try:
        with persistencia.sesion(tenant) as (cur, org):
            cur.execute(
                """insert into asistente.habilidades
                       (organization_id, codigo, nombre, cuando_usarla, pasos,
                        roles_permitidos, estado, origen)
                   values (%s, %s, %s, %s, %s, %s, 'propuesta', 'manual')
                   returning id::text""",
                (org, str(cuerpo["codigo"]).strip()[:60],
                 str(cuerpo["nombre"])[:200], str(cuerpo["cuando_usarla"]),
                 str(cuerpo["pasos"]), cuerpo.get("roles_permitidos") or []))
            fila = cur.fetchone()
    except Exception as e:
        registrar("habilidades", "fallo al crear", error=e)
        return jsonify({"error": "No se pudo crear. ¿Ya existe ese codigo?"}), 400
    return jsonify({"ok": True, "id": fila["id"]})


@app.post("/habilidades/<id_habilidad>/aprobar")
def habilidades_aprobar(id_habilidad):
    """Pone la habilidad a operar. Exige roles: sin roles no la ve nadie, y
    aprobar algo que nadie va a cargar es la forma silenciosa de creer que se
    resolvio un hueco que sigue abierto."""
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'."}), 400
    roles = cuerpo.get("roles_permitidos")
    try:
        with persistencia.sesion(tenant) as (cur, org):
            if roles is not None:
                cur.execute("""update asistente.habilidades set roles_permitidos = %s
                                where organization_id = %s and id = %s""",
                            (list(roles), org, id_habilidad))
            cur.execute("""select roles_permitidos from asistente.habilidades
                            where organization_id = %s and id = %s""",
                        (org, id_habilidad))
            fila = cur.fetchone()
            if not fila:
                return jsonify({"error": "Esa habilidad no existe."}), 404
            if not (fila["roles_permitidos"] or []):
                return jsonify({"error": "Asignale al menos un rol antes de "
                                         "aprobarla: sin rol no la ve ningun "
                                         "agente."}), 400
            cur.execute(
                """update asistente.habilidades
                      set estado = 'vigente', aprobada_en = now(),
                          aprobada_por = %s, motivo_rechazo = null
                    where organization_id = %s and id = %s""",
                (cuerpo.get("aprobada_por"), org, id_habilidad))
    except Exception as e:
        registrar("habilidades", "fallo al aprobar", error=e)
        return jsonify({"error": "No se pudo aprobar."}), 500
    return jsonify({"ok": True, "estado": "vigente"})


@app.post("/habilidades/<id_habilidad>/retirar")
def habilidades_retirar(id_habilidad):
    """Saca la habilidad de circulacion sin borrarla: los usos ya registrados
    siguen teniendo a que apuntar, y se puede saber que estuvo vigente."""
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'."}), 400
    try:
        with persistencia.sesion(tenant) as (cur, org):
            cur.execute(
                """update asistente.habilidades
                      set estado = 'obsoleta', motivo_rechazo = %s
                    where organization_id = %s and id = %s
                    returning id""",
                (cuerpo.get("motivo"), org, id_habilidad))
            if not cur.fetchone():
                return jsonify({"error": "Esa habilidad no existe."}), 404
    except Exception as e:
        registrar("habilidades", "fallo al retirar", error=e)
        return jsonify({"error": "No se pudo retirar."}), 500
    return jsonify({"ok": True, "estado": "obsoleta"})


@app.get("/habilidades/huecos")
def habilidades_huecos():
    """Que le falta saber hacer a cada agente, segun la operacion real.

    Solo detecta -- no llama al modelo ni escribe nada. Es la respuesta barata
    a "¿que le falta a este agente?", separada a proposito de proponer(), que
    ademas redacta. Ver nucleo/habilidades/analista.py.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        dias = int(request.args.get("dias") or analista.DIAS_POR_DEFECTO)
        patrones = analista.detectar(tenant, dias=dias)
    except Exception as e:
        registrar("habilidades", "fallo al detectar huecos", error=e)
        return jsonify({"error": "No se pudieron analizar las conversaciones."}), 500
    return jsonify({"dias": dias, "huecos": [
        {"rol": p.rol, "senal": p.senal, "motivo": p.motivo,
         "n_casos": p.n_casos, "codigo_habilidad": p.codigo_habilidad,
         "conversaciones": p.conversaciones[:20]} for p in patrones]})


@app.post("/habilidades/proponer")
def habilidades_proponer():
    """Detecta huecos Y redacta un borrador por cada uno. Todo queda en
    'propuesta'. Puede tardar: es una llamada al modelo por patron."""
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'."}), 400
    try:
        config = _config_de(tenant)
        resultados = analista.proponer(
            config, tenant, dias=int(cuerpo.get("dias") or analista.DIAS_POR_DEFECTO))
    except Exception as e:
        registrar("habilidades", "fallo al proponer", error=e)
        return jsonify({"error": "No se pudieron generar propuestas."}), 500
    return jsonify({"ok": True, "resultados": resultados})


# =============================================================================
#  ACCIONES PROPUESTAS  -  escrituras con aprobacion_humana=True, pendientes
#  hasta que alguien las apruebe o rechace. Ver Herramienta.aprobacion_humana
#  (schema.py) y motor.py::_ejecutar_propuesta_de_accion/
#  ejecutar_accion_aprobada. Genero, no especifico de tickets -- cualquier
#  herramienta de escritura futura que declare aprobacion_humana entra por
#  aca, no hace falta un endpoint nuevo por cada una.
# =============================================================================

@app.get("/acciones/propuestas")
def acciones_propuestas():
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        acciones = persistencia.acciones_propuestas_de(tenant, request.args.get("estado"))
    except Exception as e:
        registrar("acciones", "fallo al leer propuestas", error=e)
        return jsonify({"error": "No se pudieron leer las acciones propuestas."}), 500

    # Que sea de legado lo decide el motor, no la pantalla: es la misma regla
    # que usa la guarda de aprobar, y tenerla en dos lugares es tenerla en
    # ninguno. La lista NO trae 'argumentos' (valores reales sin enmascarar).
    for accion in acciones:
        accion["es_legado"] = persistencia.es_accion_de_legado(accion)
    return jsonify({"acciones": acciones})


#: Lo que se le dice a quien intenta aprobar una accion de legado. Explica el
#: camino, porque un 409 sin salida se lee como una falla del sistema.
MOTIVO_LEGADO = (
    "Esta accion no esta vinculada a ninguna conversacion, asi que no hay "
    "contexto actual contra el cual comprobar que todavia tiene sentido. No se "
    "puede aprobar: si el problema sigue vivo, la conversacion de hoy la vuelve "
    "a proponer; si no, se cancela.")


@app.post("/acciones/propuestas/<id_accion>/aprobar")
def acciones_propuesta_aprobar(id_accion):
    """
    Ejecuta la escritura real contra la API externa y RECIEN DESPUES marca
    la accion como 'aprobada' -- mismo orden que aprobar una herramienta
    propuesta: si la API la rechaza, el resultado (y el error) quedan
    visibles en la misma fila, no se pierde ni se finge que salio bien.

    ⚠️ SALVO QUE SEA DE LEGADO (X24, gate G3). Una accion sin conversacion no
    tiene contra que revalidarse (§3.7) y sus argumentos son los de hace
    semanas: aprobarla ejecutaria a ciegas. Se rechaza con 409 ANTES de tocar
    nada -- ni la API externa, ni el estado de la fila.

    Hoy eso alcanza a las 36 (A5), porque la columna 'conversation_id' todavia
    no existe. Cuando B5 la traiga, la misma guarda deja pasar las que la
    tengan sin que haya que tocarla.
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'."}), 400

    try:
        accion = persistencia.accion_propuesta_de(tenant, id_accion)
    except Exception as e:
        registrar("acciones", "fallo al leer la accion", error=e)
        return jsonify({"error": "No se pudo leer la accion."}), 500
    if not accion:
        return jsonify({"error": f"La accion '{id_accion}' no existe."}), 404

    # ANTES del chequeo de estado y ANTES de leer la config: lo que se prohibe
    # es llegar al ejecutor, y cualquier paso previo que pueda fallar o
    # escribir es un paso de mas en un camino que no deberia existir.
    if persistencia.es_accion_de_legado(accion):
        try:
            persistencia.registrar_aprobacion_rechazada(
                tenant, id_accion, MOTIVO_LEGADO, cuerpo.get("revisado_por"))
        except Exception as e:
            # Que no se pueda dejar constancia no puede convertir un rechazo en
            # una ejecucion: se registra el fallo y se rechaza igual.
            registrar("acciones", "no se pudo registrar el intento de aprobar legado",
                      error=e)
        registrar("acciones", "se rechazo aprobar una accion de legado", tenant=tenant)
        return jsonify({"error": MOTIVO_LEGADO, "codigo": "accion_de_legado",
                        "estado": accion["estado"],
                        "puede_cancelarse": accion["estado"] == "pendiente"}), 409

    if accion["estado"] != "pendiente":
        return jsonify({"error": f"Esta accion ya esta '{accion['estado']}', "
                                 f"no se puede volver a aprobar."}), 400

    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    quien = (cuerpo.get("revisado_por") or "").strip()
    if not quien:
        # Quien aprueba da la cara. El proxy lo saca de la sesion autenticada,
        # nunca del cuerpo que arma el navegador (§3.4) -- este endpoint solo
        # comprueba que llegue.
        return jsonify({"error": "Falta 'revisado_por': una ejecucion aprobada "
                                 "sin responsable no se puede auditar."}), 400

    return _aprobar_y_ejecutar(config, tenant, id_accion, quien)


def _aprobar_y_ejecutar(config, tenant: str, id_accion: str, quien: str):
    """
    Los cuatro pasos de §9.3 sobre una accion ya propuesta: reservar (que es
    aprobar, y para una irreversible escribe el sello), revalidar, ejecutar,
    resolver. Devuelve la respuesta Flask.

    M06-F: vive aparte del endpoint porque hay DOS entradas humanas a la misma
    cadena -- aprobar una propuesta de la cola, y el boton de reinicio de la
    Bandeja -- y las dos tienen que ser exactamente el mismo camino. Una
    segunda copia de estos pasos seria una segunda maquina de aprobacion.
    """
    # ---- PASO 1: reservar. Transaccion corta y condicionada (§9.3) ----------
    try:
        reserva = persistencia.reservar_accion(tenant, id_accion, quien)
    except Exception as e:
        registrar("acciones", "fallo al reservar la accion", error=e)
        return jsonify({"error": "No se pudo tomar la accion."}), 500

    if not reserva["ok"]:
        return jsonify(_NEGATIVAS.get(reserva["motivo"], {
            "error": "No se pudo aprobar esta accion.",
            "codigo": reserva["motivo"]})), _CODIGO_HTTP.get(reserva["motivo"], 409)

    reservada = reserva["accion"]
    conv = str(reservada.get("conversation_id") or "") or None
    herramienta = next((h for h in config.herramientas
                        if h.nombre == reservada["herramienta"]), None)
    if herramienta is None or not herramienta.aprobacion_humana:
        # El catalogo cambio entre proponer y aprobar (§3.7, condicion 3). No
        # se ejecuta, y vuelve a pendiente: puede que alguien este editando el
        # catalogo justo ahora.
        persistencia.liberar_accion(tenant, id_accion, "herramienta_fuera_de_catalogo")
        return jsonify({"error": "La herramienta de esta accion ya no esta "
                                 "disponible para aprobacion.",
                        "codigo": "herramienta_fuera_de_catalogo"}), 409

    # ---- PASO 2: revalidar. FUERA de transaccion (§3.7, X23) ----------------
    veredicto = revalidacion.revalidar(config, tenant, herramienta, reservada)

    if veredicto.desenlace == revalidacion.NO_SE_PUDO:
        # No se pudo comprobar != no se cumple. No se ejecuta nada y la accion
        # vuelve a estar disponible: el operador reintenta cuando la API
        # responda.
        persistencia.liberar_accion(tenant, id_accion, veredicto.codigo)
        return jsonify({"error": "No se pudo comprobar que esta accion siga "
                                 "aplicando. No se ejecuto nada: se puede "
                                 "reintentar.",
                        "codigo": "revalidacion_indeterminada",
                        "detalle": veredicto.codigo, "estado": "pendiente"}), 503

    if veredicto.desenlace == revalidacion.NO_CUMPLE:
        persistencia.vencer_accion(tenant, id_accion, veredicto.codigo, conv)
        return jsonify({"error": veredicto.detalle or "Esta accion ya no aplica.",
                        "codigo": "revalidacion_fallida",
                        "detalle": veredicto.codigo, "estado": "vencida"}), 409

    # ---- PASO 3: ejecutar. FUERA de transaccion -----------------------------
    # M06-F: UNA sola cadena. Una irreversible (R3/R4 y las excepciones de
    # M06-E) sigue el mismo ciclo B5 -- reservar, revalidar, ejecutar,
    # resolver -- y lo unico que cambia es QUIEN ejecuta: la puerta critica de
    # la frontera, que exige la aprobacion atada a la accion exacta. Esa
    # aprobacion es la reserva de arriba: 'reservar_accion' escribio el sello
    # en la misma escritura que paso la fila a 'ejecutando'.
    #
    # Se ejecuta la fila RELEIDA de la base, nunca el cuerpo de este request ni
    # el 'returning' de la reserva: lo que sale es lo que quedo escrito.
    verificacion_pendiente = None
    if getattr(herramienta, "irreversible", False):
        try:
            fila = persistencia.accion_propuesta_de(tenant, id_accion)
        except Exception as e:
            registrar("acciones", "fallo al releer la accion reservada", error=e)
            fila = None
        if not fila or fila.get("estado") != "ejecutando":
            # No se ejecuto nada: vuelve a estar disponible.
            persistencia.liberar_accion(tenant, id_accion, "relectura_fallida")
            return jsonify({"error": "No se pudo releer la accion aprobada. No "
                                     "se ejecuto nada: se puede reintentar.",
                            "codigo": "relectura_fallida", "estado": "pendiente"}), 503
        resultado, codigo_error, verificacion_pendiente =             motor.ejecutar_accion_irreversible(config, fila, tenant)
    else:
        resultado, codigo_error = motor.ejecutar_accion_aprobada(config, reservada)

    # Una guarda del CODIGO freno la accion antes del efecto (kill switch,
    # techo, aprobacion alterada, previas que ya no se cumplen, idempotencia):
    # no salio nada hacia el tercero. No es un fallo del sistema externo y no
    # queda como 'ejecutada_fallo'. Queda 'vencida' con el codigo del bloqueo:
    # la aprobacion era para ESE momento y no se reutiliza sola.
    if codigo_error in motor.CODIGOS_DE_BLOQUEO:
        persistencia.vencer_accion(tenant, id_accion, codigo_error, conv)
        return jsonify({"ok": False, "estado": "vencida", "codigo": codigo_error,
                        "error": (resultado or {}).get("error")
                                 or "Una guarda del sistema freno esta accion.",
                        "resultado": resultado}), 409
    incierto = bool(codigo_error) and _es_incierto(codigo_error)

    # ---- PASO 3b: confirmar el efecto, releyendo ----------------------------
    # Un 2xx dice que el pedido se acepto, no que el efecto ocurrio. Para las
    # herramientas cuya politica sabe como comprobarlo, se vuelve a leer.
    #
    # Y NO se reintenta el POST pase lo que pase: WispHub no permite consultar
    # promesas ni recuperarlas por referencia, asi que un segundo intento no
    # se puede reconciliar con el primero. Maximo un POST por accion aprobada
    # (misma regla que Q2 para crear_ticket).
    confirmado, detalle_confirmacion = _confirmar_efecto(
        config, tenant, herramienta, reservada, codigo_error)

    # ---- PASO 4: el desenlace, con su evento --------------------------------
    try:
        persistencia.resolver_ejecucion_de_accion(
            tenant, id_accion, resultado=resultado, codigo_error=codigo_error,
            incierto=incierto, aprobada_por=quien, conversation_id=conv)
    except Exception as e:
        # El efecto pudo haber ocurrido y no se pudo anotar. Queda
        # 'ejecutando', que es lo correcto: T20 la pasa a 'desconocida' y nadie
        # la reejecuta sola (§9.3 paso 5).
        registrar("acciones", "la accion se ejecuto y no se pudo guardar el desenlace",
                  error=e)

    if verificacion_pendiente and conv and not codigo_error:
        # El efecto salio EN ESTA pasada (reiniciar_ont): se comprueba despues,
        # contra la conversacion de la que salio la propuesta.
        try:
            persistencia.guardar_verificacion_pendiente(
                tenant, conv, herramienta.nombre, verificacion_pendiente)
        except Exception as e:
            registrar("acciones", "no se pudo anotar la verificacion de la accion",
                      error=e)

    if incierto:
        return jsonify({"ok": False, "estado": "desconocida",
                        "error_ejecucion": codigo_error,
                        "mensaje": "No se sabe si la accion llegó a hacerse. NO se "
                                   "reintenta: hay que comprobarlo a mano."}), 502
    if codigo_error:
        return jsonify({"ok": False, "estado": "ejecutada_fallo",
                        "error_ejecucion": codigo_error, "resultado": resultado}), 502

    return jsonify(_salida_ejecutada_ok(resultado, confirmado, detalle_confirmacion))


def _confirmar_efecto(config, tenant, herramienta, reservada, codigo_error):
    """
    Releer para comprobar que el efecto ocurrio. Devuelve (confirmado, detalle).

    Dos casos no se comprueban, y por razones opuestas:
      con codigo_error   el pedido ya fallo o quedo incierto; releer no
                         cambiaria el desenlace y puede confundirlo
      sin politica       la herramienta no declara como comprobarse

    Vive aparte del endpoint porque el 'if' es la guarda: dentro, una mutacion
    que lo apagaba entero dejaba el test verde -- el arbol de sintaxis ve la
    llamada aunque este muerta, y una prueba que mira el archivo no distingue
    codigo alcanzable de codigo presente.
    """
    if codigo_error or getattr(herramienta, "politica", None) is None:
        return None, None
    from nucleo.facturacion import politicas as politicas_facturacion

    confirmado, detalle = politicas_facturacion.confirmar(
        config, tenant, herramienta, reservada.get("argumentos") or {})
    registrar("acciones", "confirmacion del efecto", herramienta=herramienta.nombre,
              confirmado=confirmado, detalle=detalle)
    return confirmado, detalle


def _salida_ejecutada_ok(resultado, confirmado, detalle):
    """
    La respuesta cuando el sistema externo ACEPTO el pedido.

    Son TRES hechos distintos y no se colapsan en uno:

        ok: True          el pedido se acepto. Siempre, si llegamos aca.
        confirmado: True  ademas se releyo y el efecto ESTA
        confirmado: False se releyo y NO esta
        confirmado: None  no se pudo releer -- ni si ni no

    Vive aparte del endpoint para poder ejercitar las cuatro ramas sin montar
    Flask ni una base. Antes estaba dentro, y una mutacion que apagaba la
    confirmacion entera dejaba el test verde: se estaba afirmando sobre el
    TEXTO del archivo en vez de sobre lo que devuelve.
    """
    salida = {"ok": True, "estado": "ejecutada_ok", "resultado": resultado}
    if detalle is None:
        return salida
    salida["confirmado"] = confirmado
    salida["confirmacion"] = detalle
    if confirmado is False:
        salida["mensaje"] = ("El pedido se aceptó pero el efecto NO se pudo "
                             "verificar en el sistema externo. No se reintenta: "
                             "hay que revisarlo a mano.")
    elif confirmado is None:
        salida["mensaje"] = ("El pedido se aceptó y no se pudo comprobar el "
                             "efecto. NO se reintenta.")
    return salida


#: Lo que se le responde a cada negativa de la reserva. Texto propio por motivo:
#: "no se pudo" a secas obliga a adivinar si hay que reintentar, esperar o
#: avisarle a alguien.
_NEGATIVAS = {
    "no_existe": {"error": "Esta accion no existe.", "codigo": "no_existe"},
    "de_legado": {"error": MOTIVO_LEGADO, "codigo": "accion_de_legado"},
    "vencida": {"error": "Esta accion pasó su plazo de vigencia y ya no se "
                         "ejecuta. Si el problema sigue, hay que proponerla de "
                         "nuevo desde la conversación.",
                "codigo": "vencida", "estado": "vencida"},
    "conversacion_cerrada": {"error": "La conversación de esta accion está "
                                      "cerrada.",
                             "codigo": "conversacion_cerrada"},
    "ya_no_pendiente": {"error": "Alguien más ya resolvió esta accion.",
                        "codigo": "ya_no_pendiente"},
}
_CODIGO_HTTP = {"no_existe": 404}

#: Fallos donde NO se puede afirmar que el efecto no ocurrio: el pedido pudo
#: haber viajado antes de cortarse. Mismo criterio que B4 -- unknown != failed,
#: y por eso terminan en 'desconocida' en vez de 'ejecutada_fallo'.
_ERRORES_INCIERTOS = ("Timeout", "ConnectionError", "ChunkedEncoding",
                      "ReadTimeout", "ConnectTimeout", "RemoteDisconnected")


def _es_incierto(codigo_error: str) -> bool:
    return any(marca in (codigo_error or "") for marca in _ERRORES_INCIERTOS)


@app.post("/acciones/propuestas/<id_accion>/rechazar")
def acciones_propuesta_rechazar(id_accion):
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'."}), 400

    try:
        existe = persistencia.resolver_accion_propuesta(
            tenant, id_accion, "rechazada", cuerpo.get("revisado_por"),
            motivo_rechazo=cuerpo.get("motivo"))
    except Exception as e:
        registrar("acciones", "fallo al rechazar", error=e)
        return jsonify({"error": "No se pudo guardar."}), 500

    if not existe:
        # M06-F: rechazar es un compare-and-set sobre 'pendiente'. Antes pisaba
        # cualquier estado -- una accion ya 'ejecutando' (aprobada, con su sello
        # y quiza con el efecto en viaje) podia quedar como 'rechazada' y
        # borrar el rastro de que salio. Si la fila existe, se dice en que
        # estado esta; si no, 404.
        try:
            actual = persistencia.accion_propuesta_de(tenant, id_accion)
        except Exception:
            actual = None
        if actual:
            return jsonify({"error": f"Esta accion ya esta '{actual['estado']}', "
                                     f"no se puede rechazar.",
                            "estado": actual["estado"]}), 409
        return jsonify({"error": f"La accion '{id_accion}' no existe."}), 404
    return jsonify({"ok": True, "estado": "rechazada"})


@app.post("/acciones/propuestas/<id_accion>/cancelar")
def acciones_propuesta_cancelar(id_accion):
    """
    Cancela una accion que quedo obsoleta, con su motivo y su evento (§11.4).

    NO es rechazar. Rechazada es "alguien la evaluo y dijo que no"; cancelada
    es "quedo obsoleta y nadie la va a evaluar". Ninguna de las dos ejecuta
    nada, pero en un registro que existe para auditar la diferencia es el
    registro entero -- y es la que §11.4 pide para las 36.

    El motivo es obligatorio: 36 filas canceladas sin explicacion no le dicen
    nada a quien las mire el mes que viene. Quien cancela tambien da la cara,
    igual que en cualquier otro evento de operador.
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    motivo = (cuerpo.get("motivo") or "").strip()
    quien = (cuerpo.get("cancelada_por") or "").strip()
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'."}), 400
    if not motivo:
        return jsonify({"error": "Falta el campo 'motivo': una cancelacion sin "
                                 "motivo no explica nada."}), 400
    if not quien:
        return jsonify({"error": "Falta el campo 'cancelada_por'."}), 400

    try:
        estado, la_cancele = persistencia.cancelar_accion_propuesta(
            tenant, id_accion, motivo, quien)
    except Exception as e:
        registrar("acciones", "fallo al cancelar", error=e)
        return jsonify({"error": "No se pudo cancelar la accion."}), 500

    if estado is None:
        return jsonify({"error": f"La accion '{id_accion}' no existe."}), 404
    if not la_cancele:
        # Ya la habia resuelto alguien -- incluso si tambien fue cancelando.
        # Se dice cual es su estado en vez de pisarlo: dos operadores mirando
        # la misma lista es lo normal, y el segundo tiene que enterarse de que
        # llego tarde en vez de creer que hizo algo.
        return jsonify({"error": f"Esta accion ya esta '{estado}'.",
                        "estado": estado}), 409
    return jsonify({"ok": True, "estado": "cancelada"})


# =============================================================================
#  CORPUS  -  cargar documentacion sin pasar por la consola, y consultar que
#  hay publicado hoy
# =============================================================================
#  Hasta ahora, meter un documento al corpus exigia un desarrollador con el
#  repo, el .env y Ollama: dejar el .docx en corpus/<slug>/ y correr
#  cli/cargar_corpus.py. Eso contradice la regla de ARQUITECTURA.md ("dar de
#  alta un ISP nuevo = ... cargar sus documentos. Cero cambios en nucleo/"):
#  de los tres pasos, ese era el unico que la empresa no podia hacer sola.
#
#  La escritura es la MISMA que usa el CLI (nucleo/ingesta/corpus.py); lo unico
#  que cambia es de donde viene el archivo y con que rol se escribe. La lectura
#  (GET, mas abajo) es distinta de /manual/*: eso es material crudo todavia sin
#  redactar, esto es lo que ya esta publicado y el motor puede recuperar.

EXTENSIONES_SOPORTADAS = (".docx",)


@app.post("/corpus/documentos")
def corpus_ingerir():
    """
    Recibe un documento y lo deja fragmentado, vectorizado y buscable.

    Multipart (el unico endpoint del motor que recibe un archivo; los demas son
    JSON): 'tenant', 'archivo', y opcionalmente 'roles' (lista separada por
    comas), 'storage_path' y 'forzar'.

    Escribe con sesion(), que baja a 'app_backend' y aplica RLS. El CLI, en
    cambio, se conecta como 'postgres' con BYPASSRLS porque es herramienta de
    operacion -- esa diferencia es deliberada, y por eso el modulo de ingesta
    recibe el cursor en vez de abrirlo.
    """
    import hashlib
    import tempfile
    from pathlib import Path

    tenant = request.form.get("tenant")
    archivo = request.files.get("archivo")
    if not tenant or archivo is None or not archivo.filename:
        return jsonify({"error": "Faltan campos: tenant, archivo"}), 400

    nombre = Path(archivo.filename).name
    if Path(nombre).suffix.lower() not in EXTENSIONES_SOPORTADAS:
        # Explicito y no en silencio: el fragmentador es especifico de Word, y
        # un PDF aceptado "a medias" quedaria como un documento vacio dentro
        # del corpus, que es peor que un rechazo.
        return jsonify({"error": f"Solo se admite {', '.join(EXTENSIONES_SOPORTADAS)}. "
                                 f"'{nombre}' no se puede fragmentar."}), 400

    forzar = str(request.form.get("forzar", "")).lower() in ("1", "true", "si", "on")

    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    try:
        roles = ingesta.roles_validos(config, request.form.get("roles"))
    except ValueError as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400

    datos = archivo.read()
    hash_ = hashlib.sha256(datos).hexdigest()

    try:
        # El temporal CONSERVA EL NOMBRE ORIGINAL. procesar() usa 'ruta.stem'
        # como respaldo del codigo y el titulo cuando el documento no los
        # declara adentro; con un nombre aleatorio, ese documento quedaria
        # registrado con el nombre del temporal y nadie lo notaria.
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / nombre
            ruta.write_bytes(datos)

            perfil, tokens = ingesta.perfil_desde_config(config)
            doc = procesar(ruta, perfil=perfil, max_tokens=tokens)

            # Si el .docx trae su propia tabla de roles, manda esa: el valor
            # viaja con el documento. El del formulario es el respaldo para
            # los que todavia no la tienen.
            roles_doc = ingesta.roles_validos(config, getattr(doc, "roles", None))

            # VECTORIZAR SIN UNA CONEXION TOMADA (22/09/2026, auditoria previa
            # al pool). `ingerir` recibia el cursor y llamaba a OpenAI UNA VEZ
            # POR FRAGMENTO dentro del `with`: un documento largo retenia la
            # conexion minutos. Con un pool eso no agota conexiones nuevas --
            # agota las del pool, y de paso hace esperar a todos los demas.
            #
            # Ahora son tres pasos: una consulta corta para saber si hace
            # falta, los embeddings SIN conexion, y otra consulta corta para
            # escribir. La decision sigue siendo de `ingerir`; esto solo evita
            # gastar embeddings cuando el archivo no cambio.
            with persistencia.sesion(tenant) as (cur, org):
                hace_falta = ingesta.hay_que_vectorizar(
                    cur, org, doc, hash_, forzar=forzar)

            vectores = ([ingesta.vectorizar(f.contextualizar(doc))
                         for f in doc.fragmentos] if hace_falta else [])

            with persistencia.sesion(tenant) as (cur, org):
                resultado = ingesta.ingerir(
                    cur, org, doc, hash_,
                    vectores=vectores,
                    modelo_embeddings=config.rag.modelo_embeddings,
                    roles_permitidos=roles_doc or roles,
                    storage_path=request.form.get("storage_path"),
                    forzar=forzar,
                    # El archivo tal cual se subio: es la evidencia de QUE se
                    # aprueba despues. Los fragmentos son derivados; sin el
                    # original, "Fulano aprobo esto" no se puede verificar.
                    original=datos,
                    nombre_archivo=nombre,
                    mime=archivo.mimetype,
                    perfil_fragmentacion={
                        "max_tokens": tokens,
                        "exigir_multinivel_sin_estilo":
                            perfil.exigir_multinivel_sin_estilo,
                        "titulo_un_nivel_en_tabla": perfil.titulo_un_nivel_en_tabla,
                    },
                    # Lo subido desde la interfaz entra PENDIENTE: se
                    # vectoriza, pero match_chunks no lo recupera hasta que
                    # una persona lo apruebe (ver supabase/202608231328_aprobacion_documentos). Subir un
                    # archivo y publicarlo dejan de ser el mismo acto.
                    #
                    # El CLI mantiene 'vigente' a proposito: exige
                    # credenciales de base y es herramienta de operacion,
                    # como una migracion -- quien lo corre ya decidio.
                    estado="pendiente")
    except ingesta.VersionAprobadaInmutable as e:
        # 409 y no 400: la peticion esta bien formada, lo que pasa es que el
        # recurso esta en un estado que no admite esa operacion. Y no es un
        # fallo que haya que investigar en los logs -- es una regla del
        # producto contandose a quien la choco.
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 409
    except ingesta.RolesInvalidos as e:
        return jsonify({"error": f"El documento declara {mensaje_publico(e, 'roles invalidos')}"}), 400
    except Exception as e:
        return fallo(500, "documento_no_procesado", "No se pudo procesar el documento.",
                     componente="corpus", e=e)

    return jsonify(resultado), 201


@app.post("/corpus/documentos/<id_documento>/aprobar")
def corpus_aprobar(id_documento):
    """
    Habilita un documento pendiente para que el asistente pueda recuperarlo.

    Es la segunda capa que le faltaba al corpus. La primera --y la que de
    verdad garantiza-- es que asistente.match_chunks filtra por
    estado='vigente' en SQL: un documento pendiente es invisible aunque esta
    ruta no existiera. Aca solo se abre la puerta, y queda registrado quien.

    Nace de una medicion concreta (agosto 2026): la unica guia de
    diagnostico del corpus, G-GO-04, tiene 7 de sus 8 fragmentos escritos
    para un tecnico en campo -- abrir conectores de fibra, medir potencia
    optica, reemplazar el cable de acometida. Asignada por error a un rol de
    cara al cliente, eso son instrucciones peligrosas entregadas sin que
    salte ningun error.
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400

    try:
        with persistencia.sesion(tenant) as (cur, org):
            ok = ingesta.aprobar(cur, org, id_documento,
                                 cuerpo.get("aprobado_por"))
    except Exception as e:
        registrar("corpus", "fallo al aprobar", id_documento=id_documento, error=e)
        return jsonify({"error": "No se pudo aprobar el documento."}), 500

    if not ok:
        # Distinto de 404 a proposito: el caso normal no es que el documento
        # no exista sino que ya este aprobado (dos personas mirando la misma
        # pantalla), y eso no es un error que haya que investigar.
        return jsonify({"error": "El documento no existe o no estaba "
                                 "pendiente de aprobacion."}), 409
    return jsonify({"aprobado": True})


@app.post("/corpus/documentos/<id_documento>/retirar")
def corpus_retirar(id_documento):
    """
    Saca un documento del corpus: pasa a 'obsoleto', que es lo que
    match_chunks() excluye. No se borra -- deshacer tiene que ser posible, y
    hay que poder reconstruir con que version se respondio algo.
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400

    try:
        with persistencia.sesion(tenant) as (cur, org):
            ok = ingesta.retirar(cur, org, id_documento)
    except RuntimeError as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 404
    except Exception as e:
        registrar("corpus", "fallo el retiro", id_documento=id_documento, error=e)
        return jsonify({"error": "No se pudo retirar el documento."}), 500

    if not ok:
        return jsonify({"error": f"El documento '{id_documento}' no existe."}), 404
    return jsonify({"retirado": True})


@app.put("/corpus/documentos/<id_documento>/roles")
def corpus_actualizar_roles(id_documento):
    """
    Corrige a quien se le recupera un documento YA cargado, sin re-vectorizar.
    Antes de esto, la unica forma de arreglar un typo en los roles era editar
    el .docx o el YAML del tenant y volver a correr la ingesta completa.
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400

    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    # roles_validos espera texto separado por comas -- reusa la MISMA
    # validacion que la carga (rol desconocido = 400, nunca en silencio).
    try:
        roles = ingesta.roles_validos(config, ",".join(cuerpo.get("roles") or []))
    except ValueError as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400

    try:
        with persistencia.sesion(tenant) as (cur, org):
            ok = ingesta.actualizar_roles(cur, org, id_documento, roles)
    except Exception as e:
        registrar("corpus", "fallo al actualizar roles", id_documento=id_documento, error=e)
        return jsonify({"error": "No se pudieron actualizar los roles."}), 500

    if not ok:
        return jsonify({"error": f"El documento '{id_documento}' no existe."}), 404
    return jsonify({"roles_permitidos": roles})


# =============================================================================
#  WEBHOOK DE WHATSAPP  -  la unica ruta de este servicio expuesta a internet
# =============================================================================
#  El resto del motor NO lleva dominio publico a proposito (ver DESPLIEGUE.md):
#  exponer /chat seria dejar el asistente abierto sin autenticacion. La regla
#  de Traefik tiene que restringirse al prefijo '/canales/whatsapp'.
#
#  Aca la autenticacion es la FIRMA del cuerpo, no un token de sesion: Meta
#  firma cada entrega con el App Secret y sin esa firma no se procesa nada.

def _rol_de_cliente(config) -> str | None:
    """El rol con el que se atiende a quien escribe por un canal publico.

    Lo dice la CONFIGURACION ('rol_de_entrada'), no el orden en que quedaron
    las claves de un diccionario.

    Antes se devolvia el primer rol con orientado_a='cliente_final'. Se
    buscaba por 'orientado_a' y no por nombre por una razon correcta -- el
    nucleo no puede saber como llamo cada empresa a su rol de autoservicio
    (PRD 3 / ARQUITECTURA.md)-- pero eso resuelve QUE roles son candidatos,
    no CUAL de ellos atiende. Rapilink tiene cuatro.

    El 07/09/2026 el primero era 'ventas', que existe para PROSPECTOS
    ("todavia no es cliente de Rapilink", dice su descripcion) y que no tiene
    'derivar_a_area': un suscriptor sin internet escribia y le contestaba el
    agente comercial, sin ninguna forma de pasarlo a soporte. Y el orden
    cambia solo, porque editar la configuracion desde la interfaz reserializa
    el JSON entero.

    Sin 'rol_de_entrada' se conserva el comportamiento viejo para no dejar
    mudo a un tenant ya cargado, pero se AVISA: que la eleccion la haga un
    orden que nadie decidio es exactamente lo que hay que poder ver.
    """
    if config.rol_de_entrada:
        return config.rol_de_entrada

    candidatos = [n for n, r in config.roles.items()
                  if r.orientado_a == "cliente_final"]
    if not candidatos:
        return None
    if len(candidatos) > 1:
        registrar("canal", "sin 'rol_de_entrada' definido y hay varios roles de cliente: "
                           "se atiende con el primero del diccionario, que no es una "
                           "decision de nadie. Definir 'rol_de_entrada'.",
                  candidatos=candidatos, elegido=candidatos[0])
    return candidatos[0]


# Lo que se le dice al MODELO cuando el cliente manda un archivo sin escribir
# nada. Es una descripcion del hecho, no del contenido: nadie miro la foto. Sin
# esto el turno arrancaria con un mensaje vacio y el modelo saludaria como si
# fuera el primer contacto.
_AVISO_ADJUNTO = {
    "image": "[El cliente envio una foto]",
    "audio": "[El cliente envio un audio]",
    "voice": "[El cliente envio una nota de voz]",
    "video": "[El cliente envio un video]",
    "document": "[El cliente envio un documento]",
    "sticker": "[El cliente envio un sticker]",
    "location": "[El cliente compartio su ubicacion]",
}


def _atendio_baja_o_alta(config, tenant: str, de: str, texto: str) -> bool:
    """
    Si el mensaje es una solicitud de baja o alta de avisos, la resuelve y
    devuelve True (el turno termina ahi).

    Se compara el mensaje COMPLETO, no si lo contiene: "no me llega nada, doy
    de baja el servicio?" no es una solicitud de baja del canal, y tratarla
    como tal seria dejar de avisarle justo a quien tiene un problema.
    """
    cfg = getattr(config.canales, "whatsapp", None)
    if not cfg:
        return False

    limpio = (texto or "").strip().lower().rstrip(".!")
    if not limpio:
        return False

    try:
        if limpio in [p.lower() for p in cfg.palabras_baja]:
            persistencia.dar_de_baja(tenant, de, "whatsapp", limpio)
            whatsapp.enviar_texto(config, tenant, de, cfg.respuesta_baja)
            registrar("whatsapp", "baja de avisos", tenant=tenant, remitente=ref_sesion(de))
            return True
        if limpio in [p.lower() for p in cfg.palabras_alta]:
            persistencia.dar_de_alta(tenant, de, "whatsapp")
            whatsapp.enviar_texto(config, tenant, de, cfg.respuesta_alta)
            registrar("whatsapp", "alta de avisos", tenant=tenant, remitente=ref_sesion(de))
            return True
    except Exception as e:
        # Si falla, se deja seguir al modelo: peor que no registrar la baja
        # seria dejar el mensaje sin ninguna respuesta.
        registrar("whatsapp", "fallo al procesar baja/alta de avisos",
                  tenant=tenant, remitente=ref_sesion(de), error=e)
    return False


def _guardar_adjunto(config, tenant: str, entrante: dict,
                     conversacion_id: str | None,
                     mensaje_id: str | None = None) -> None:
    """
    Baja el archivo, lo comprime y lo guarda colgado de la conversacion.

    Nunca levanta: es informacion de apoyo. Si falla, el cliente igual recibe
    su respuesta y el agente ve el mensaje sin la foto -- que es peor que
    tenerla, pero muchisimo mejor que un turno caido.
    """
    media_id = entrante.get("media_id")
    if not media_id or not conversacion_id:
        return
    try:
        crudo, mime = whatsapp.descargar_media(config, tenant, media_id)
        contenido, mime = media.preparar(crudo, entrante.get("tipo", ""), mime)
        persistencia.guardar_media(
            tenant, conversacion_id, media_id, entrante.get("tipo", ""),
            contenido, mime, entrante.get("descripcion") or None, mensaje_id)
        registrar("whatsapp", "adjunto guardado", conversation_id=id_interno(conversacion_id),
                  media=ref_proveedor(media_id), kb_recibidos=len(crudo) // 1024,
                  kb_guardados=len(contenido) // 1024)
    except Exception as e:
        registrar("whatsapp", "no se pudo guardar el adjunto",
                  conversation_id=id_interno(conversacion_id),
                  media=ref_proveedor(media_id), error=e)


def _procesar_mensaje_whatsapp(config, tenant: str, rol: str, entrante: dict) -> None:
    """
    Un mensaje entrante, de punta a punta. Corre FUERA del ciclo de respuesta
    del webhook (ver la nota de ACK abajo), asi que no puede devolver error a
    nadie: todo lo que falle se registra y se corta ahi.
    """
    de = entrante.get("de")
    wamid = entrante.get("wamid")

    # Que llegue un BSUID en vez de un telefono NO impide contestar: el envio
    # lo nombra por el campo 'recipient' en vez de 'to' (ver _destinatario() en
    # nucleo/canales/whatsapp.py). Lo que si queda sin poder hacerse es cruzarlo
    # con la base del ISP, porque un BSUID no es un numero: esa persona va a
    # tener que identificarse con su cedula como cualquier numero desconocido.
    if not entrante.get("telefono"):
        registrar("whatsapp", "remitente sin telefono (BSUID): se contesta igual, pero no se "
                              "puede reconocer al cliente sin que se identifique",
                  tenant=tenant, remitente=ref_sesion(de), wamid=ref_proveedor(wamid))

    try:
        if wamid:
            whatsapp.marcar_leido(config, tenant, wamid)

        # Baja/alta de avisos ANTES del modelo. No es una consulta que haya que
        # interpretar: es un derecho del titular (Ley 1581) y tiene que
        # funcionar aunque el modelo este caido. Ademas, un numero que quiere
        # dejar de recibir y no puede, bloquea -- y los bloqueos le bajan la
        # reputacion al numero de la empresa.
        if _atendio_baja_o_alta(config, tenant, de, entrante.get("texto", "")):
            return

        texto = entrante.get("texto", "")
        descripcion = entrante.get("descripcion", "")
        tipo = entrante.get("tipo", "")

        # Lo que el modelo lee de un adjunto es lo que el cliente ESCRIBIO al
        # mandarlo, mas el hecho de que mando algo. No se le pasa la foto: no
        # hay modelo de vision configurado, e inventar una descripcion seria
        # exactamente lo que el PRD RF-07 prohibe.
        if not texto.strip():
            texto = descripcion.strip() or _AVISO_ADJUNTO.get(tipo, "")

        if not texto:
            whatsapp.enviar_texto(
                config, tenant, de,
                "Recibí tu mensaje, pero no puedo leer ese tipo de archivo. "
                "Cuéntame en palabras qué necesitas y te ayudo.")
            return

        salida = atender_turno(config, tenant, rol, de, texto, "whatsapp",
                               evento_id=wamid)

        # El adjunto se guarda DESPUES del turno, con la conversacion ya
        # creada: es lo que le da el conversation_id al que colgarlo. Va
        # aparte del turno y en su propio try porque una foto que no se pudo
        # bajar no puede dejar al cliente sin respuesta.
        _guardar_adjunto(config, tenant, entrante, salida.get("conversacion_id"),
                         salida.get("mensaje_usuario_id"))

        # Una respuesta VACIA significa "no hay nada que decir", y hay que
        # respetarlo: pasa cuando una persona del equipo esta atendiendo la
        # conversacion y el bot se calla para no contradecirla. Mandarla igual
        # seria un mensaje en blanco al cliente (y un 400 de Meta).
        if (salida.get("respuesta") or "").strip():
            # D24, punto 2: lo ultimo antes del POST. Entre el punto 1 y aca
            # corren el evaluador de escalamiento, el CRM y el adjunto, y
            # tardan. Si una persona intervino en ese intervalo, no se envia.
            if (salida.get("_autorizacion") is not None
                    and not _respuesta_sigue_autorizada(tenant, "whatsapp", de, salida)):
                _descartar_respuesta_guardada(tenant, "whatsapp", de, salida)
                return
            whatsapp.enviar_texto(config, tenant, de, salida["respuesta"])
    except Exception as e:
        registrar("whatsapp", "fallo al atender un mensaje entrante",
                  tenant=tenant, remitente=ref_sesion(de), wamid=ref_proveedor(wamid), error=e)


def _respuesta_sigue_autorizada(tenant: str, canal: str, id_sesion: str, salida: dict) -> bool:
    """
    D24, punto 2. Si el turno escalo, su respuesta es el aviso de ESA escalada
    y sigue la regla SYNC_ESCALADA: que un operador la haya tomado no le quita
    al cliente el aviso de que lo atiende una persona; una devolucion o un
    cierre, si. Si no escalo, la version no puede haber cambiado.
    """
    autorizacion = salida["_autorizacion"]
    if autorizacion.get("escalada_version") is not None:
        return _escalada_sigue_vigente(tenant, {"conversation_id": autorizacion.get("conversation_id"),
                                                "version": autorizacion["escalada_version"]})
    return _turno_sigue_autorizado(tenant, canal, id_sesion, autorizacion, exigir_ia=False)


def _descartar_respuesta_guardada(tenant: str, canal: str, id_sesion: str, salida: dict) -> None:
    """La respuesta ya estaba guardada y no se va a enviar (D24, punto 2): la
    fila queda 'descartado' y sale de la memoria viva."""
    autorizacion = salida.get("_autorizacion") or {}
    _contar_relevo("respuesta_ia_descartada_por_cambio_de_control",
                   conversation_id=id_interno(autorizacion.get("conversation_id")),
                   version=autorizacion.get("relevo_version"), punto="antes_del_envio")
    if salida.get("mensaje_id"):
        try:
            persistencia.descartar_respuesta_ia(tenant, salida["mensaje_id"])
        except Exception as e:
            registrar("relevo", "no se pudo marcar la respuesta descartada", error=e)
    estado = _sesiones.get(canales.clave_sesion(tenant, canal, id_sesion))
    if estado is not None:
        _quitar_respuesta_de_memoria(estado["historial"])


@app.get("/canales/whatsapp/<tenant>")
def whatsapp_handshake(tenant):
    """
    Alta del webhook. Meta llama una sola vez con GET y espera que le devuelvan
    'hub.challenge' TAL CUAL, en texto plano, solo si el verify_token coincide.
    """
    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    recibido = request.args.get("hub.verify_token")
    if not whatsapp.token_de_verificacion_valido(config, tenant, recibido):
        registrar("whatsapp", "handshake rechazado: token invalido", tenant=tenant)
        return jsonify({"error": "verify_token invalido"}), 403

    return request.args.get("hub.challenge", ""), 200, {"Content-Type": "text/plain"}


@app.post("/canales/whatsapp/<tenant>")
def whatsapp_webhook(tenant):
    """
    Mensajes entrantes.

    ACK INMEDIATO, TRABAJO APARTE
    -----------------------------
    Meta espera un 200 en pocos segundos y reintenta si no lo recibe. Un turno
    con DeepSeek tarda 4.7-12 s (PRD 7.1) y el modelo local hasta 42 s: si se
    contesta despues de atender, Meta reintenta y el cliente recibe la misma
    respuesta dos veces. Por eso se responde 200 antes de pensar, y el turno
    corre en un hilo.

    El hilo es suficiente y una cola seria de mas: el trabajo es una llamada
    HTTP con espera, no calculo, y si el proceso se cae en el medio el mensaje
    se pierde -- que es lo mismo que pasaria con una cola sin persistencia. El
    dia que el volumen lo pida, esto es lo que se reemplaza.
    """
    crudo = request.get_data()          # CRUDO: la firma es sobre estos bytes

    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    # --- la firma es la autenticacion de esta ruta, y falla cerrado ----------
    if not whatsapp.firma_valida(config, tenant, crudo,
                                 request.headers.get("X-Hub-Signature-256")):
        registrar("whatsapp", "firma invalida en el webhook", tenant=tenant)
        return jsonify({"error": "firma invalida"}), 401

    cuerpo = request.get_json(force=True, silent=True) or {}

    entrantes = whatsapp.mensajes_entrantes(cuerpo)
    estados = whatsapp.estados_entrantes(cuerpo)
    rol = _rol_de_cliente(config)
    if not rol and entrantes:
        registrar("whatsapp", "no hay ningun rol orientado a cliente_final: no hay con que "
                              "atender mensajes; los statuses se procesan igual", tenant=tenant)
        # La ausencia de rol solo cierra la puerta conversacional. Los acuses
        # ya autenticados son hechos del canal y se conservan abajo.
        entrantes = []

    # Que trajo esta entrega. Sin esto, un webhook que llega y no produce nada
    # es indistinguible de uno que no llego: los dos se ven como un 200 en el
    # registro de acceso. Costo una tarde de depuracion averiguar cual de los
    # dos estaba pasando.
    if not entrantes and not estados:
        campos = []
        for entrada in (cuerpo or {}).get("entry", []) or []:
            for cambio in entrada.get("changes", []) or []:
                campos.append(cambio.get("field"))
                valor = cambio.get("value") or {}
                campos.extend(f"value.{clave}" for clave in sorted(valor))
        # Solo NOMBRES de campos de la estructura de Meta; aun asi pasan por el
        # registro, que redacta cualquier cosa que no tenga forma de nombre.
        registrar("whatsapp", "entrega SIN mensajes ni estados", tenant=tenant,
                  claves=campos or list((cuerpo or {}).keys()))
    else:
        # Se dice de que forma llego el remitente, no solo cuantos mensajes.
        # Un identificador opaco ('CO.1360...') en vez de un telefono rompe la
        # verificacion por posesion del canal SIN dar ningun error: el cliente
        # queda como desconocido y se le pide la cedula aunque escriba desde su
        # propio numero. Es la clase de fallo que hay que poder ver de un
        # vistazo en vez de deducir.
        formas = [("telefono" if (e.get("de") or "").isdigit() else "OPACO")
                  for e in entrantes]
        registrar("whatsapp", "entrega recibida", tenant=tenant, mensajes=len(entrantes),
                  estados=len(estados), remitentes=formas)

        # Si el remitente vino opaco, hace falta saber que SI trajo la entrega
        # para encontrar donde esta el telefono. Se registran las CLAVES de
        # cada nivel, nunca los valores: el contenido es de un cliente.
        if "OPACO" in formas:
            for entrada in (cuerpo or {}).get("entry", []) or []:
                for cambio in entrada.get("changes", []) or []:
                    valor = cambio.get("value") or {}
                    contactos = valor.get("contacts") or []
                    registrar("whatsapp", "remitente opaco: claves de la entrega",
                              tenant=tenant, field=cambio.get("field"),
                              claves_value=sorted(valor), contactos=len(contactos),
                              claves_contacto=sorted(contactos[0]) if contactos else None,
                              claves_metadata=sorted(valor.get("metadata") or {}))

    atendidos = 0
    for entrante in entrantes:
        wamid = entrante.get("wamid")
        de = entrante.get("de")
        if not wamid or not de:
            # Un mensaje sin id o sin remitente no se puede atender NI
            # deduplicar. Antes se descartaba con un 'continue' mudo, y eso
            # dejaba el peor rastro posible: el registro decia "entrega con 1
            # mensaje" y despues no pasaba nada, sin ninguna linea que
            # explicara por que. Se dice que se descarto y con que forma
            # llego -- las CLAVES, nunca el contenido, que es de un cliente.
            registrar("whatsapp", "mensaje descartado: incompleto", tenant=tenant,
                      falta="wamid" if not wamid else "remitente",
                      tipo=entrante.get("tipo"),
                      claves=sorted((entrante.get("crudo") or {}).keys()))
            continue

        # Antes de gastar un turno del modelo: si este wamid ya se atendio, es
        # un reintento de Meta y contestar de nuevo seria cobrar y responder
        # dos veces. Ver supabase/202608121841_webhook_eventos.sql.
        try:
            if persistencia.evento_ya_visto(tenant, wamid):
                continue
        except Exception as e:
            # Sin poder deduplicar se prefiere NO atender: un mensaje perdido
            # se recupera cuando el cliente insiste; uno duplicado ya le llego
            # dos veces y no hay vuelta atras.
            registrar("whatsapp", "no se pudo verificar si es duplicado: se descarta por precaucion",
                      tenant=tenant, wamid=ref_proveedor(wamid), error=e)
            continue

        hilo = threading.Thread(
            target=_procesar_mensaje_whatsapp,
            args=(config, tenant, rol, entrante), daemon=True)
        hilo.start()
        atendidos += 1

    # Los acuses de entrega llegan por este mismo webhook y NO son
    # conversacion: sin separarlos, el bot contestaria a su propio "entregado".
    for estado in estados:
        crudo = estado.get("estado")
        # Metadata solamente. Ni el telefono del cliente (ni siquiera sus
        # ultimos digitos) ni el texto de error de Meta ni el wamid entero van al
        # log -- un log de produccion persiste, y antes se imprimian el telefono
        # completo y el texto de Meta en CADA acuse. El wamid entero vive en la
        # base, que es donde hace falta para casar el acuse; en el log va su
        # huella (ref_proveedor, 'prv-' + 12 hex), que alcanza para ubicar la fila:
        #   select id from asistente.messages
        #    where left(encode(sha256(convert_to(wamid, 'UTF8')), 'hex'), 12) = '<huella sin prv->';
        # (convert_to y no wamid::bytea: el cast interpreta las barras invertidas
        # como escapes, y un wamid con una no se encontraria.)
        huella = ref_proveedor(estado.get("wamid"))
        if crudo == "failed":
            registrar("whatsapp", "acuse", tenant=tenant, estado="failed",
                      codigo=estado.get("codigo"), wamid=huella)
        else:
            # Los acuses buenos tambien se registran. Antes solo se imprimian
            # los fallidos, y eso obligaba a deducir del SILENCIO que un
            # mensaje habia salido bien -- que es justo lo que no se puede
            # distinguir de que el acuse nunca llego. La categoria es lo que
            # factura Meta.
            registrar("whatsapp", "acuse", tenant=tenant, estado=estado.get("estado"),
                      wamid=huella, categoria=estado.get("categoria"))

        # Y ahora, ademas de imprimirlo, se GUARDA contra el mensaje que lo
        # produjo. Hasta hoy esto se leia, se registraba y se tiraba: no habia
        # donde ponerlo, porque 'messages' no guardaba el wamid. La
        # consecuencia era que un mensaje que nunca salio se veia, al recargar
        # la pagina, exactamente igual que uno entregado.
        nuestro = ESTADOS_DE_ENTREGA.get(crudo)
        if not nuestro or not estado.get("wamid"):
            continue
        try:
            persistencia.marcar_entrega(
                tenant, estado["wamid"], nuestro,
                _motivo_de_fallo(estado) if nuestro == "fallido" else None)
        except Exception as e:
            # Un acuse perdido no puede tumbar el webhook: Meta reintenta la
            # entrega entera y volveriamos a procesar los mensajes.
            registrar("whatsapp", "no se pudo anotar el acuse", tenant=tenant,
                      estado=estado.get("estado"), wamid=huella, error=e)

    return jsonify({"recibido": True, "atendidos": atendidos}), 200


@app.get("/corpus/documentos")
def corpus_documentos():
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400

    try:
        documentos = persistencia.documentos_de(tenant)
    except Exception as e:
        registrar("corpus", "fallo al listar documentos", error=e)
        return jsonify({"error": "No se pudieron leer los documentos."}), 500

    return jsonify({"documentos": documentos})


@app.get("/corpus/documentos/<id_documento>/fragmentos")
def corpus_fragmentos(id_documento):
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400

    try:
        fragmentos = persistencia.fragmentos_de(tenant, id_documento)
    except Exception as e:
        registrar("corpus", "fallo al leer fragmentos", error=e)
        return jsonify({"error": "No se pudieron leer los fragmentos."}), 500

    return jsonify({"fragmentos": fragmentos})


@app.post("/avisos/whatsapp/<tenant>")
def whatsapp_avisar(tenant):
    """
    Un aviso PROACTIVO por plantilla: cobro, corte, mantenimiento.

    Es la unica forma de escribirle primero a alguien -- fuera de las 24 h
    desde su ultimo mensaje, WhatsApp solo acepta plantillas aprobadas.

    NO va detras del webhook publico: esto lo llama un proceso interno (una
    tarea programada del CRM cruzando facturas vencidas), por la red interna.
    Si algun dia se expone, necesita autenticacion propia -- la firma de Meta
    no aplica aca porque el que llama no es Meta.

    Cuerpo: {para, plantilla, variables?, idioma?}
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    para = cuerpo.get("para")
    plantilla = cuerpo.get("plantilla")
    if not para or not plantilla:
        return jsonify({"error": "Faltan campos: para, plantilla"}), 400

    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    # La baja se consulta ANTES de armar nada. Escribirle a quien pidio que no
    # le escribamos no es solo un problema legal: los bloqueos que genera le
    # bajan la reputacion al numero y con ella el limite de envio de TODA la
    # empresa. Falla cerrado: si no se puede comprobar, no se manda.
    try:
        if persistencia.esta_de_baja(tenant, para, "whatsapp"):
            return jsonify({"enviado": False, "motivo": "el numero pidio no recibir avisos"}), 200
    except Exception as e:
        registrar("whatsapp", "no se pudo comprobar la baja antes de un aviso",
                  tenant=tenant, destinatario=ref_sesion(para), error=e)
        return jsonify({"error": "No se pudo comprobar si el numero acepta avisos."}), 503

    try:
        wamid = whatsapp.enviar_plantilla(
            config, tenant, para, plantilla,
            cuerpo.get("variables"), cuerpo.get("idioma", "es"))
    except whatsapp.ErrorWhatsApp as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except Exception as e:
        registrar("whatsapp", "fallo el aviso", tenant=tenant, destinatario=ref_sesion(para),
                  plantilla=plantilla, error=e)
        return jsonify({"error": "No se pudo enviar el aviso."}), 502

    return jsonify({"enviado": True, "wamid": wamid}), 200


@app.get("/plantillas/whatsapp/<tenant>")
def whatsapp_plantillas(tenant):
    """
    Que plantillas tiene aprobadas la empresa en Meta, cruzadas con las que
    declara su configuracion.

    Existe porque hoy esas dos listas se mantienen a ciegas: una plantilla
    declarada en el YAML que Meta nunca aprobo falla recien al mandar el primer
    aviso, y a esa altura ya hay un cliente sin enterarse de su corte.
    """
    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    try:
        en_meta = whatsapp.plantillas_aprobadas(config, tenant)
    except whatsapp.ErrorWhatsApp as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400
    except Exception as e:
        registrar("whatsapp", "fallo al leer plantillas", error=e)
        return jsonify({"error": "No se pudieron leer las plantillas."}), 502

    declaradas = config.canales.whatsapp.plantillas
    aprobadas = {p["nombre"] for p in en_meta if p["estado"] == "APPROVED"}
    return jsonify({
        "en_meta": en_meta,
        "declaradas": declaradas,
        # Lo unico que hay que mirar: lo que el codigo puede pedir y Meta no
        # va a aceptar.
        "declaradas_sin_aprobar": sorted(
            clave for clave, nombre in declaradas.items() if nombre not in aprobadas),
    })


@app.post("/conversaciones/<id_conversacion>/conservar")
def conversaciones_conservar(id_conversacion):
    """
    Marca o desmarca una conversacion para que la purga por retencion no la
    borre.

    NO es lo mismo que marcar un ejemplo (ver /mensajes/<id>/marcar): un
    ejemplo dice "esta respuesta del asistente fue buena" y alimenta el manual
    de procedimientos; esto dice "no la borres todavia" -- un reclamo, un
    incidente, algo que puede terminar en disputa, que es justo lo que NO hay
    que copiar como ejemplo.

    Cuerpo: {tenant, conservar: bool, motivo?, por?}
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400

    conservar = bool(cuerpo.get("conservar", True))
    motivo = (cuerpo.get("motivo") or "").strip() or None

    # Al conservar se exige un motivo: dentro de seis meses nadie va a saber
    # si la marca sigue teniendo sentido, y sin eso no hay forma de decidir si
    # se puede soltar. Al desmarcar no hace falta.
    if conservar and not motivo:
        return jsonify({"error": "Hay que decir por que se conserva."}), 400

    try:
        existe = persistencia.marcar_conservar(
            tenant, id_conversacion, conservar, motivo, cuerpo.get("por"))
    except Exception as e:
        registrar("conversaciones", "fallo al marcar conservar", error=e)
        return jsonify({"error": "No se pudo guardar."}), 500

    if not existe:
        return jsonify({"error": f"La conversacion '{id_conversacion}' no existe."}), 404
    return jsonify({"conservar": conservar, "motivo": motivo})


@app.post("/conversaciones/<id_conversacion>/intervenir")
def conversaciones_intervenir(id_conversacion):
    """
    Una persona toma el control de una conversacion que atendia la IA. B3.3b.

    Solo adquiere el control: NO le envia nada al cliente. Responder es otra
    llamada, despues, y pasa por la guarda de control como cualquier respuesta.
    Mezclar las dos cosas meteria el envio a Meta y su incertidumbre (D17)
    dentro de la toma de control.

    No es una escalada: no toca escalada_a_humano ni necesita_atencion_humana,
    asi que no cuenta en la tasa de escalamiento ni dispara nada de ella.

    Cuerpo: {tenant, autor, autor_usuario_id, motivo?, clave_operacion?}
      200  intervenida (o reintento de la misma operacion)
      409  ya no la controla la IA: otra persona intervino o esta escalada
      404  no existe
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400
    try:
        autor, autor_id, _ = _autor_y_clave(cuerpo)
    except persistencia.AutorInvalido as e:
        return jsonify({"error": f"Autor invalido: {mensaje_publico(e, 'datos de autor incompletos')}"}), 400
    try:
        r = transiciones.intervenir(
            tenant, id_conversacion, operador_id=autor_id, operador_nombre=autor,
            motivo_texto=(cuerpo.get("motivo") or "").strip(),
            clave=(cuerpo.get("clave_operacion") or "").strip() or None)
    except Exception as e:
        registrar("relevo", "fallo al intervenir", conversation_id=id_interno(id_conversacion),
                  error=e)
        return jsonify({"error": "No se pudo tomar el control."}), 500
    if r.motivo == "no_existe":
        return jsonify({"error": f"La conversacion '{id_conversacion}' no existe."}), 404
    if r.motivo == "clave_ajena":
        # La clave ya la uso otra operacion u otro operador: no se le responde
        # exito a quien no fue el que intervino.
        return jsonify({"error": "Esa clave de operacion ya pertenece a otra operacion.",
                        "codigo": "clave_de_otra_operacion"}), 409
    if r.aplicada or r.motivo == "reintento":
        return jsonify({"intervenida": True, "relevo_version": r.version,
                        "reintento": r.motivo == "reintento"}), 200
    return jsonify({"error": "Esta conversacion ya no la atiende la IA: otra persona la tomo "
                             "o esta escalada.", "codigo": "no_es_de_la_ia"}), 409


def _atender_pendiente_tras_devolver(tenant: str, pendiente: dict) -> None:
    """
    El mensaje que el cliente mando mientras la conversacion la tenia una
    persona, atendido por la IA justo despues de que se la devuelvan.

    NO VUELVE A GUARDAR EL MENSAJE: ya esta en la base desde que llego, y por
    eso el turno recibe 'conversacion_ya_guardada'. Sin eso el hilo mostraria
    la misma frase del cliente dos veces.

    Corre en su propio hilo y no puede devolverle un error a nadie: lo que
    falle se registra y se corta ahi, igual que el webhook.
    """
    try:
        config = _config_de(tenant)
        salida = atender_turno(
            config, tenant, pendiente["rol"], pendiente["usuario_externo"],
            pendiente["texto"], pendiente["canal"],
            conversacion_ya_guardada=pendiente["conversacion_id"])
        respuesta = (salida.get("respuesta") or "").strip()
        if respuesta and pendiente["canal"] == "whatsapp":
            whatsapp.enviar_texto(config, tenant, pendiente["usuario_externo"], respuesta)
    except Exception as e:
        registrar("relevo", "no se pudo atender el mensaje pendiente tras la devolucion",
                  conversation_id=id_interno(pendiente.get("conversacion_id")), error=e)


@app.post("/conversaciones/<id_conversacion>/devolver")
def conversaciones_devolver(id_conversacion):
    """
    Una persona le devuelve la conversacion a la IA. La inversa de /intervenir.

    POR QUE HACIA FALTA ESTA RUTA, Y NO ESTABA
    ------------------------------------------
    Hasta el 22/09/2026 devolver SOLO existia pegado a un envio: el modo
    "responder y devolver" de la Bandeja manda un mensaje y, si sale, devuelve.
    Quien queria devolver sin decir nada no tenia como -- y en produccion
    alguien apreto el boton esperando exactamente eso, el cliente escribio dos
    veces mas y la IA no contesto porque el control seguia en 'humano'. No
    fallo nada: no habia nada que fallara.

    Devolver sin responder es una intencion legitima y distinta: "ya esta, que
    siga el asistente". Atarla a tener algo que decir obliga a escribir un
    mensaje de relleno, que es peor que no decir nada.

    NO ENVIA NADA AL CLIENTE, por el mismo motivo que /intervenir no envia:
    mezclar el envio a Meta --y su incertidumbre, D17-- dentro de un cambio de
    control hace que un fallo de red deje el control a medias. Son dos cosas y
    se piden por separado.

    Cuerpo: {tenant, autor, autor_usuario_id, clave_operacion?}
      200  devuelta (o reintento de la misma operacion)
      409  no la lleva una persona: ya es de la IA, o esta cerrada
      404  no existe
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400
    try:
        autor, autor_id, _ = _autor_y_clave(cuerpo)
    except persistencia.AutorInvalido as e:
        return jsonify({"error": f"Autor invalido: {mensaje_publico(e, 'datos de autor incompletos')}"}), 400

    try:
        r = transiciones.devolver_a_ia(
            tenant, id_conversacion, operador_id=autor_id, operador_nombre=autor,
            clave=(cuerpo.get("clave_operacion") or "").strip() or None)
    except Exception as e:
        registrar("relevo", "fallo al devolver a la IA",
                  conversation_id=id_interno(id_conversacion), error=e)
        return jsonify({"error": "No se pudo devolver la conversacion."}), 500

    if r.motivo == "no_existe":
        return jsonify({"error": f"La conversacion '{id_conversacion}' no existe."}), 404
    if r.motivo == "clave_ajena":
        return jsonify({"error": "Esa clave de operacion ya pertenece a otra operacion.",
                        "codigo": "clave_de_otra_operacion"}), 409
    if not (r.aplicada or r.motivo == "reintento"):
        return jsonify({"error": "Esta conversacion no la lleva una persona: ya es de la IA "
                                 "o esta cerrada.", "codigo": "no_es_humana"}), 409

    # LA SESION VIVA TAMBIEN TIENE QUE ENTERARSE. El motor guarda en memoria si
    # la conversacion estaba escalada, y con esa bandera puesta el asistente
    # sigue en pausa aunque la base ya diga 'ia'. Es el mismo gesto que hace el
    # envio-con-devolucion; sin el, devolver "funciona" en la pantalla y no en
    # el comportamiento, que es la peor forma de funcionar.
    #
    # SE LEE CON mensajes_de Y NO CON identidad_de_conversacion, y no es un
    # detalle: identidad_de_conversacion NO devuelve 'canal' --su docstring lo
    # dice, "solo identificadores"-- asi que la clave de sesion salia armada
    # con None y no coincidia con ninguna. La bandera quedaba puesta. Ademas
    # hace falta el hilo entero para lo de abajo, asi que es una lectura y no
    # dos.
    pendiente = None
    try:
        hilo = persistencia.mensajes_de(tenant, id_conversacion)
        conv = hilo.get("conversacion") or {}
        if conv:
            clave_viva = canales.clave_sesion_de_fila(
                tenant, conv.get("canal"), conv.get("usuario_externo"))
            if clave_viva in _sesiones:
                _sesiones[clave_viva]["escalada"] = False

        # EL MENSAJE QUE QUEDO SIN CONTESTAR.
        #
        # Si el cliente escribio mientras la conversacion la tenia una persona,
        # ese mensaje no lo contesto nadie: la IA estaba en pausa. Al devolver,
        # sin esto se quedaba sin respuesta PARA SIEMPRE -- la IA solo actua
        # cuando entra un mensaje nuevo, asi que el cliente tenia que insistir
        # para que alguien le hablara. Visto en produccion el 22/09/2026.
        #
        # La condicion es estrecha a proposito: solo si el ULTIMO mensaje del
        # hilo es del cliente. Si despues de el hubo una respuesta --de la
        # persona o del asistente-- ya se le contesto, y volver a hacerlo seria
        # repetirle algo que quiza ya se resolvio por telefono.
        mensajes = hilo.get("mensajes") or []
        ultimo = mensajes[-1] if mensajes else None
        if ultimo and ultimo.get("rol") == "user" and (ultimo.get("contenido") or "").strip():
            pendiente = {"texto": ultimo["contenido"],
                         "canal": conv.get("canal"),
                         "usuario_externo": conv.get("usuario_externo"),
                         "rol": conv.get("rol_efectivo") or "cliente_final",
                         "conversacion_id": id_conversacion}
    except Exception as e:
        # La transicion ya se aplico y es la fuente de verdad. Que no se haya
        # podido limpiar la sesion en memoria --o mirar si quedaba algo sin
        # contestar-- se registra y no se oculta, pero no convierte un exito en
        # un error.
        registrar("relevo", "devuelta pero no se pudo leer el hilo",
                  conversation_id=id_interno(id_conversacion), error=e)

    # FUERA DEL CICLO DE RESPUESTA, como el webhook. Atender un turno llama al
    # modelo y puede tardar segundos: dejar esperando a quien apreto el boton
    # convertiria "devolver" en una operacion lenta, y peor, un timeout del
    # navegador haria parecer que fallo algo que ya se aplico.
    if pendiente:
        threading.Thread(target=_atender_pendiente_tras_devolver,
                         args=(tenant, pendiente), daemon=True).start()

    return jsonify({"devuelta": True, "relevo_version": r.version,
                    "reintento": r.motivo == "reintento",
                    "atiende_pendiente": bool(pendiente)}), 200


@app.post("/conversaciones/<id_conversacion>/atender")
def conversaciones_atender(id_conversacion):
    """
    Alguien se hace cargo del caso. NO lo resuelve.

    ESTA RUTA CAMBIO DE SIGNIFICADO EL 07/09/2026, Y ESE ES EL PUNTO.
    Escribia 'atendida_manual', que quiere decir "resuelto por telefono, en
    persona o por otro canal". Sirve para el boton "Marcar como resuelta"
    --que sigue existiendo, en /resolver-- pero no para "Atender", que es lo
    que se pulsa al ENTRAR a un caso, no al salir.

    La diferencia no era de nombre. 'atendida_manual' habilita dos cierres
    automaticos (ver persistencia): el "ok, gracias" del cliente cierra el
    caso, y el barrido por plazo vencido lo cierra solo. Tomar un caso para
    trabajarlo lo dejaba expuesto a los dos.

    Cuerpo: {tenant, autor, autor_usuario_id, soltar?, clave_operacion?}

    Tomar asigna; soltar quita la asignacion y la conversacion SIGUE esperando
    a una persona (no vuelve a la IA). Ver nucleo/relevo/transiciones.py.
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400
    try:
        autor, autor_id, _ = _autor_y_clave(cuerpo)
    except persistencia.AutorInvalido as e:
        return jsonify({"error": f"Autor invalido: {mensaje_publico(e, 'datos de autor incompletos')}"}), 400

    soltar = bool(cuerpo.get("soltar"))
    clave = (cuerpo.get("clave_operacion") or "").strip() or None
    try:
        hacer = transiciones.soltar if soltar else transiciones.tomar
        r = hacer(tenant, id_conversacion, operador_id=autor_id, operador_nombre=autor, clave=clave)
    except Exception as e:
        registrar("conversaciones", "fallo al tomar el caso", error=e)
        return jsonify({"error": "No se pudo guardar."}), 500

    if r.motivo == "no_existe":
        return jsonify({"error": f"La conversacion '{id_conversacion}' no existe."}), 404
    conflicto = _conflicto_de_asignacion(r)
    if conflicto:
        return conflicto
    # Exito, o nada que hacer porque ya estaba como se pidio (ya era suya, ya
    # estaba libre, el mismo clic reintentado).
    return jsonify({"tomada": not soltar, "por": None if soltar else autor,
                    "aplicada": r.aplicada, "relevo_version": r.version,
                    "reintento": r.motivo == "reintento"})


# Los 409 de la asignacion (B3.4). 'codigo' es lo que lee la pantalla para
# refrescar y decir que paso; 'asignada_a' dice quien gano, cuando lo hay.
_CONFLICTOS_DE_ASIGNACION = {
    "ya_asignada": "Esta conversacion ya la tomo otra persona.",
    "no_es_suya": "Solo quien tiene la conversacion puede soltarla.",
    "control_ia": "Esta conversacion la atiende la IA: para tomarla, usa Intervenir.",
    "no_abierta": "Esta conversacion ya esta cerrada.",
    "clave_ajena": "Esa clave de operacion ya pertenece a otra operacion.",
    "legado_sin_relevo": "Esta conversacion es anterior al relevo: no se puede reasignar hasta adoptarla.",
}


def _conflicto_de_asignacion(r):
    mensaje = _CONFLICTOS_DE_ASIGNACION.get(r.motivo)
    if not mensaje:
        return None
    codigo = "clave_de_otra_operacion" if r.motivo == "clave_ajena" else r.motivo
    return jsonify({"error": mensaje, "codigo": codigo,
                    "asignada_a": (r.datos or {}).get("asignada_a_nombre")}), 409


@app.post("/conversaciones/<id_conversacion>/reasignar")
def conversaciones_reasignar(id_conversacion):
    """
    T4 (B3.4, D4): un ADMIN pasa la conversacion a otra persona, o a si mismo.

    Cuerpo: {tenant, autor, autor_usuario_id, autor_rol, destino_usuario_id,
             destino_nombre, motivo, clave_operacion?}

    El actor, su rol y el destino los arma el proxy DESDE LA SESION (el rol del
    JWT verificado; el destino, contra las personas activas de la
    organizacion), nunca el navegador. Esta ruta queda detras del token de
    servicio (G1), y ademas exige el rol: un pedido sin 'ADMIN' es 403 aunque
    traiga todo lo demas -- no 409, el problema es de autorizacion.

      200  reasignada (o ya era del destino, o reintento de la misma operacion)
      400  sin motivo, o autor/destino invalidos
      403  el actor no es ADMIN
      404  no existe
      409  cerrada, bajo control ia, legado sin adoptar, o clave ajena
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400
    try:
        autor, autor_id, _ = _autor_y_clave(cuerpo)
    except persistencia.AutorInvalido as e:
        return jsonify({"error": f"Autor invalido: {mensaje_publico(e, 'datos de autor incompletos')}"}), 400
    if (cuerpo.get("autor_rol") or "").strip().upper() != "ADMIN":
        return jsonify({"error": "Solo un administrador puede reasignar una conversacion.",
                        "codigo": "no_es_admin"}), 403
    try:
        r = transiciones.reasignar(
            tenant, id_conversacion, admin_id=autor_id, admin_nombre=autor,
            destino_id=cuerpo.get("destino_usuario_id") or "",
            destino_nombre=cuerpo.get("destino_nombre") or "",
            motivo=cuerpo.get("motivo") or "",
            clave=(cuerpo.get("clave_operacion") or "").strip() or None)
    except (persistencia.AutorInvalido, ValueError) as e:
        # 'ValueError' tambien llega desde bibliotecas: mensaje_publico solo
        # deja pasar el texto si la excepcion es de Dexter (D23).
        return jsonify({"error": f"Reasignacion invalida: "
                                 f"{mensaje_publico(e, 'faltan datos de la reasignacion')}",
                        "codigo": "reasignacion_invalida"}), 400
    except Exception as e:
        registrar("conversaciones", "fallo al reasignar", error=e)
        return jsonify({"error": "No se pudo guardar."}), 500
    if r.motivo == "no_existe":
        return jsonify({"error": f"La conversacion '{id_conversacion}' no existe."}), 404
    conflicto = _conflicto_de_asignacion(r)
    if conflicto:
        return conflicto
    return jsonify({"reasignada": True, "aplicada": r.aplicada, "relevo_version": r.version,
                    "asignada_a": (r.datos or {}).get("nuevo_nombre") if r.aplicada else None,
                    "reintento": r.motivo == "reintento"})


@app.post("/conversaciones/<id_conversacion>/humano/media")
def conversaciones_enviar_media(id_conversacion):
    """
    Una persona le manda un archivo al cliente desde la bandeja: una foto de
    como queda el cableado, la factura en PDF, una nota de voz.

    MISMO CRITERIO QUE EL TEXTO: se guarda primero y se entrega despues.
    Un adjunto que se ve en el hilo pero nunca salio es peor que un error
    visible.

    LO QUE ESTA API ACEPTA, Y POR QUE NO MAS
    ---------------------------------------
    image, document y audio. Video y sticker existen en la API de Meta y NO
    estan aca a proposito: no se probaron contra esta cuenta. Declarar un tipo
    sin haberlo probado es exactamente lo que costo tiempo con la API de
    WispHub -- ver la skill 'wisphub-api'.

    Los limites (formato y tamaño) los declara el canal, no esta funcion:
    whatsapp.LIMITES_MEDIA. Se validan ANTES de subir, porque pasarse devuelve
    un error generico DESPUES de haber subido el archivo entero.

    Multipart, no JSON: mandar los bytes en base64 dentro de un JSON los
    infla un tercio y obliga a tener el archivo entero dos veces en memoria.

    Campos: archivo (file), tenant, tipo, pie?, autor?
    """
    subido = request.files.get("archivo")
    tenant = request.form.get("tenant")
    tipo = (request.form.get("tipo") or "").strip()
    pie = (request.form.get("pie") or "").strip()

    if not subido or not tenant or not tipo:
        return jsonify({"error": "Faltan campos: archivo, tenant, tipo"}), 400
    try:
        autor, autor_id, clave = _autor_y_clave(request.form)
    except persistencia.AutorInvalido as e:
        return jsonify({"error": f"Autor invalido: {mensaje_publico(e, 'datos de autor incompletos')}"}), 400
    bloqueo = _exigir_control_humano(tenant, id_conversacion)
    if bloqueo:
        return bloqueo

    contenido = subido.read()
    mime = subido.mimetype or "application/octet-stream"
    nombre = subido.filename or "archivo"

    # Validar antes de tocar la base: si WhatsApp no lo va a aceptar, no se
    # guarda un adjunto que despues no se puede entregar nunca.
    try:
        whatsapp._validar_media(tipo, mime, len(contenido))
    except Exception as e:
        return jsonify({"error": mensaje_publico(e, "No se pudo completar la operacion.")}), 400

    # Lo que ve el hilo. Un adjunto sin texto no puede quedar como una burbuja
    # vacia: se dice que se mando, y el pie va aparte si lo hay.
    etiqueta = whatsapp.LIMITES_MEDIA[tipo]["etiqueta"]
    texto = pie or f"[{etiqueta} enviado: {nombre}]"

    try:
        destino = persistencia.agregar_mensaje_humano(
            tenant, id_conversacion, texto, autor, autor_usuario_id=autor_id,
            clave_idempotencia=clave)
    except Exception as e:
        registrar("media", "fallo al guardar el mensaje", error=e)
        return jsonify({"error": "No se pudo guardar."}), 500
    if destino is None:
        return jsonify({"error": f"La conversacion '{id_conversacion}' no existe."}), 404
    if _ya_guardado(destino):
        return jsonify({"ok": True, "ya_existia": True,
                        "mensaje_id": destino["mensaje_id"],
                        "estado_entrega": destino["estado_entrega"]}), 200

    # Se comprime con el mismo criterio que lo que ENTRA (media.preparar):
    # una foto de 8 MB del celular de un tecnico no tiene por que viajar
    # entera, y ademas asi entra en el tope de 5 MB de WhatsApp.
    guardado, mime_guardado = media.preparar(contenido, tipo, mime)

    salida = {"ok": True, "aceptado_por_meta": False,
              "aceptacion_registrada": False, "resultado": None,
              "mensaje_id": destino["mensaje_id"]}

    if destino["canal"] != "whatsapp":
        salida["aceptado_por_meta"] = None
        salida["aceptacion_registrada"] = True
        salida["resultado"] = "aceptado"
    else:
        salida.update(_entregar_y_registrar(
            tenant, destino["mensaje_id"],
            lambda: whatsapp.enviar_media(
                _config_de(tenant), tenant, destino["usuario_externo"], tipo,
                guardado, mime_guardado, nombre, pie),
            f"media '{id_conversacion}'"))

    # Se guarda pase lo que pase con la entrega: si fallo, quien atiende tiene
    # que poder ver QUE quiso mandar para reintentarlo, no volver a buscar el
    # archivo en su disco.
    #
    # 'media_id' propio y no el de Meta: el de Meta caduca a los 30 dias y no
    # existe si la entrega fallo. Este es la clave estable de nuestro lado.
    try:
        persistencia.guardar_media(
            tenant, id_conversacion, f"salida:{destino['mensaje_id']}", tipo,
            guardado, mime_guardado, nombre, destino["mensaje_id"])
    except Exception as e:
        registrar("media", "no se pudo guardar el adjunto", error=e)

    return jsonify(salida), 201


@app.post("/conversaciones/<id_conversacion>/nota")
def conversaciones_nota(id_conversacion):
    """
    Una nota que el equipo se deja a si mismo. NO se le envia a nadie.

    Esta ruta NO tiene ninguna llamada al canal, y eso es la garantia: no es
    que se decida no enviar, es que no hay con que. La ruta que entrega
    (POST .../humano) es otra funcion, con otro nombre y otro verbo.

    Cuerpo: {tenant, mensaje, autor, autor_usuario_id} -- autor obligatorio.
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    contenido = (cuerpo.get("mensaje") or "").strip()
    if not tenant or not contenido:
        return jsonify({"error": "Faltan campos: tenant, mensaje"}), 400

    try:
        autor, autor_id, _clave = _autor_y_clave(cuerpo)
    except persistencia.AutorInvalido as e:
        return jsonify({"error": f"Autor invalido: {mensaje_publico(e, 'datos de autor incompletos')}"}), 400
    try:
        nota_id = persistencia.agregar_nota_interna(
            tenant, id_conversacion, contenido, autor, autor_usuario_id=autor_id)
    except Exception as e:
        registrar("nota", "fallo al guardar", error=e)
        return jsonify({"error": "No se pudo guardar la nota."}), 500

    if nota_id is None:
        return jsonify({"error": f"La conversacion '{id_conversacion}' no existe."}), 404
    return jsonify({"ok": True, "nota_id": nota_id}), 201


@app.get("/canales/limites-media")
def canales_limites_media():
    """
    Que formatos y tamaños acepta el canal. La pantalla los pide para validar
    ANTES de subir un archivo -- que alguien espere una subida de 40 MB para
    que le digan que no se puede es evitable.

    Sale del canal y no de una constante en el frontend: si Meta cambia un
    tope, se cambia en un solo lugar y la pantalla se entera sola.
    """
    return jsonify({"limites": whatsapp.limites_media()})


# Los nombres de Meta, traducidos UNA vez. La base guarda el nuestro porque es
# lo que se muestra, y tener la traduccion en un solo lugar evita que la
# pantalla tenga que conocer el vocabulario de un proveedor.
ESTADOS_DE_ENTREGA = {
    "sent": "enviado",
    "delivered": "entregado",
    "read": "leido",
    "failed": "fallido",
}

# Lo que Meta manda como texto del error es el MISMO ('Message undeliverable')
# para causas opuestas: un numero que no existe, la ventana de 24 h vencida, o
# alguien que bloqueo a la empresa. Lo que las distingue es el codigo, y quien
# atiende tiene que hacer cosas distintas en cada una -- por eso se guarda ya
# traducido a algo que dice que hacer, y no el texto crudo.
MOTIVOS_DE_FALLO = {
    131047: "Pasaron más de 24 horas desde el último mensaje del cliente: "
            "WhatsApp ya no acepta texto libre, hay que usar una plantilla.",
    131026: "El número no tiene WhatsApp, o no puede recibir mensajes.",
    131049: "Meta no entregó el mensaje para cuidar la experiencia del "
            "usuario (límite de mensajes de marketing).",
    131051: "Ese tipo de mensaje no está permitido para este número.",
    470: "La ventana de servicio se cerró: hay que reabrirla con una "
         "plantilla aprobada.",
}


def _motivo_de_fallo(estado: dict) -> str:
    """El por que de un fallo, en palabras y con su codigo por si hay que
    buscarlo. Se guarda en messages.error_entrega, asi que lo escribe Dexter:
    un codigo desconocido deja solo el codigo, que es la pista que sirve para
    buscar la causa. Lo que dijo Meta no se guarda ni se imprime -- no se
    persisten respuestas de APIs externas, y un log de produccion persiste."""
    codigo = estado.get("codigo")
    return MOTIVOS_DE_FALLO.get(codigo) or f"WhatsApp no lo entregó (código {codigo})."


def _motivo_de_envio(e: Exception) -> str:
    """
    Lo que se guarda y se le muestra al operador cuando un envio falla.

    Nunca str(e) de algo que no escribio Dexter: termina en
    messages.error_entrega y en la pantalla. ErrorWhatsApp si trae un texto
    propio (ver nucleo/canales/whatsapp.py), y un codigo conocido se traduce
    con la misma tabla que los acuses del webhook.
    """
    if isinstance(e, whatsapp.ErrorWhatsApp):
        return MOTIVOS_DE_FALLO.get(e.codigo) or str(e)
    if isinstance(e, requests.RequestException):
        return "No se pudo contactar a WhatsApp. El mensaje no salió."
    return "No se pudo enviar el mensaje por WhatsApp."


def _rechazo_es_definitivo(e: Exception) -> bool:
    """Solo un rechazo inequívoco habilita el aviso de que no salió."""
    if not isinstance(e, whatsapp.ErrorWhatsApp):
        return False
    if e.http_status is None:  # configuración/validación antes del POST
        return True
    return 400 <= e.http_status < 500 and e.http_status not in (408, 429)


def _salida_previa(tenant: str, clave: str) -> dict:
    """
    Que se sabe de una salida que YA fue adquirida con esta clave.

    Es el unico desempate entre "no salio nunca" y "pudo haber salido y no
    sabemos": la fila de messages no distingue los dos casos --en los dos queda
    'pendiente'-- y whatsapp_salidas si. 'adquirido' es el estado de una salida
    que se reservo y nunca se resolvio: el proceso se cayo entre el POST y el
    registro, o esta en vuelo ahora mismo. Los dos son INCIERTO, no fallo: no se
    reenvia nada y tampoco se afirma que no salio.
    """
    previa = persistencia.salida_whatsapp(tenant, clave) or {}
    estado = previa.get("estado")
    resultado = ({"aceptado": "aceptado", "rechazado": "rechazado",
                  "sin_id": "sin_id"}.get(estado, "incierto"))
    return _contrato_entrega(resultado, previa.get("wamid"), estado == "aceptado")


def _contrato_entrega(resultado: str, wamid: str | None, registrado: bool,
                      aviso: str | None = None) -> dict:
    salida = {"resultado": resultado, "aceptado_por_meta": bool(wamid),
              "aceptacion_registrada": bool(wamid) and registrado}
    if aviso:
        salida["aviso"] = aviso
    return salida


def _entregar_y_registrar(tenant: str, mensaje_id: str | None, enviar, etiqueta: str,
                           *, clave_salida: str | None = None,
                           conversation_id: str | None = None) -> dict:
    """
    El UNICO camino por el que una respuesta humana sale por WhatsApp y deja su
    resultado en la fila. Lo usan texto, plantilla y multimedia.

    'enviar' es una funcion sin argumentos que devuelve el wamid. Se separan
    las dos mitades a proposito: antes el registro del exito estaba DENTRO del
    try del envio, y si algo fallaba despues de que Meta aceptara, el except
    marcaba 'fallido' un mensaje que si habia salido -- y la pantalla ofrecia
    reintentarlo.

    Devuelve lo que el endpoint agrega a su respuesta:
      resultado   que paso, sin ambiguedad:
                    'aceptado'               Meta dio wamid y quedo registrado
                    'rechazado'              Meta (o la red) lo rechazo: NO salio
                    'sin_id'                 Meta respondio bien pero sin wamid
                    'aceptado_sin_registro'  Meta dio wamid y la base NO lo guardo
      entregado   True solo si Meta devolvio un wamid.
      registrado  si el resultado quedo escrito en la base.
      aviso       SOLO en 'rechazado': texto saneado para el operador.

    'aceptado_sin_registro' es una ENTREGA INCIERTA, no un fallo. El cliente
    probablemente ya recibio el mensaje; lo que se perdio es la constancia. Por
    eso no lleva aviso: el aviso es lo que hace que la bandeja muestre "No le
    llego al cliente" y ofrezca Reintentar, y reintentar mandaria el mensaje dos
    veces. Tampoco se reenvia nada desde aca, ni ahora ni despues. La fila queda
    como estaba ('pendiente'), que es lo honesto: no se sabe mas que eso.

    Los logs llevan solo metadata: nunca el texto de una excepcion ajena ni lo
    que respondio Meta, porque un log de produccion tambien persiste.
    """
    clave = clave_salida or f"mensaje:{mensaje_id}"
    try:
        adquirida = persistencia.adquirir_salida_whatsapp(
            tenant, clave, proposito=etiqueta, mensaje_id=mensaje_id,
            conversation_id=conversation_id)
    except Exception as e:
        registrar("entrega", "no se pudo adquirir el derecho a enviar", operacion=etiqueta,
                  mensaje=id_interno(mensaje_id), error=e)
        return _contrato_entrega("incierto", None, False)
    if not adquirida:
        return _salida_previa(tenant, clave)

    try:
        wamid = enviar()
    except Exception as e:
        motivo = _motivo_de_envio(e)
        definitivo = _rechazo_es_definitivo(e)
        resultado = "rechazado" if definitivo else "incierto"
        if mensaje_id:
            registrado = persistencia.marcar_envio(
                tenant, mensaje_id, None, motivo if definitivo else None,
                clave_salida=clave, resultado=resultado)
        else:
            registrado = persistencia.resolver_salida_whatsapp(
                tenant, clave, resultado, error=motivo if definitivo else None)
        # error_seguro ya aporta tipo, codigo y http_status del rechazo.
        # El evento es fijo y el desenlace va como campo: un evento armado con
        # una variable no se puede buscar en el log (tests/test_registro_sin_pii).
        registrar("entrega", "el envio no fue aceptado", proveedor="meta",
                  operacion=etiqueta, resultado=resultado,
                  mensaje=id_interno(mensaje_id), registrado=registrado, error=e)
        return _contrato_entrega(resultado, None, registrado,
                                 motivo if definitivo else None)

    if mensaje_id:
        registrado = persistencia.marcar_envio(
            tenant, mensaje_id, wamid, clave_salida=clave,
            resultado="aceptado" if wamid else "sin_id")
    else:
        registrado = persistencia.resolver_salida_whatsapp(
            tenant, clave, "aceptado" if wamid else "sin_id", wamid=wamid)
    if not wamid:
        resultado = "sin_id"
    elif not registrado:
        resultado = "aceptado_sin_registro"
    else:
        resultado = "aceptado"
    if resultado == "aceptado_sin_registro":
        registrar("entrega", "ENTREGA INCIERTA: no reenviar", proveedor="meta",
                  operacion=etiqueta, resultado=resultado, mensaje=id_interno(mensaje_id),
                  registrado=registrado, wamid=ref_proveedor(wamid))
    elif resultado != "aceptado":
        registrar("entrega", "sin identificador", proveedor="meta", operacion=etiqueta,
                  resultado=resultado, mensaje=id_interno(mensaje_id), registrado=registrado)
    return _contrato_entrega(resultado, wamid, registrado)


@app.get("/conversaciones/desenlaces")
def conversaciones_desenlaces():
    """
    El catalogo de cierre de esta empresa: que puede elegir un operador (B6).

    Sale del backend y no de una lista en la pantalla por la misma razon de
    siempre: la lista de la pantalla se copia, se desincroniza y termina
    ofreciendo un codigo que el motor rechaza. Aca el que ofrece y el que
    valida leen lo mismo (nucleo/relevo/desenlaces.py).
    """
    tenant = (request.args.get("tenant") or "").strip()
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'"}), 400
    try:
        config = _config_de(tenant)
    except Exception:
        # Sin config cargada quedan los doce de plataforma, que es justo lo que
        # una empresa sin nada configurado tiene que poder usar (§3.5).
        config = None
    return jsonify({"desenlaces": desenlaces.catalogo(config)})


@app.post("/conversaciones/<id_conversacion>/desenlace")
def conversaciones_completar_desenlace(id_conversacion):
    """
    Ponerle desenlace a una conversacion que se cerro sin uno (B6, §3.5).

    Los cierres por confirmacion del cliente (T15a, T15b) y por inactividad
    (T18) dejan el codigo en NULL a proposito: ahi nadie eligio nada. Esto es
    la otra mitad de esa frase del contrato -- "se completan despues si una
    persona revisa".

    NO reabre la conversacion, NO cambia quien la cerro y NO toca el caso ni
    el ticket de afuera. Solo escribe sobre NULL: si ya tiene desenlace
    responde 409, porque pisar el que puso otra persona seria reescribir el
    pasado en silencio.

    Cuerpo: {tenant, autor, autor_usuario_id, desenlace, nota?, clave_operacion?}
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400
    try:
        autor, autor_id, _ = _autor_y_clave(cuerpo)
    except persistencia.AutorInvalido as e:
        return jsonify({"error": f"Autor invalido: {mensaje_publico(e, 'datos de autor incompletos')}"}), 400

    try:
        r = transiciones.completar_desenlace(
            tenant, id_conversacion,
            desenlace=(cuerpo.get("desenlace") or "").strip(),
            nota=(cuerpo.get("nota") or "").strip() or None,
            operador_id=autor_id, operador_nombre=autor,
            config=_config_de(tenant),
            clave=(cuerpo.get("clave_operacion") or "").strip() or None)
    except ValueError as e:
        return jsonify({"error": mensaje_publico(e, "desenlace invalido")}), 400
    except Exception as e:
        registrar("conversaciones", "fallo al completar el desenlace", error=e)
        return jsonify({"error": "No se pudo guardar."}), 500

    if r.motivo == "no_existe":
        return jsonify({"error": f"La conversacion '{id_conversacion}' no existe."}), 404
    if r.motivo == "no_esta_cerrada":
        return jsonify({"error": "La conversacion sigue abierta: se cierra, no se completa."}), 409
    if r.motivo == "ya_completado":
        # 409 y no 200: el segundo tiene que enterarse de que llego tarde.
        return jsonify({"error": "Esta conversacion ya tiene desenlace."}), 409
    return jsonify({"completado": True, "desenlace": r.datos.get("desenlace"),
                    "categoria": r.datos.get("categoria")})


@app.post("/conversaciones/<id_conversacion>/resolver")
def conversaciones_resolver(id_conversacion):
    """
    El caso termino: cierra la conversacion y la saca de la bandeja.

    No es lo mismo que 'atender' (arriba): esa dice "alguien esta en esto" y
    la conversacion sigue viva. Esta dice "esto ya se resolvio" y la cierra,
    para que el proximo mensaje de esa persona empiece un hilo limpio en vez
    de arrastrar el caso viejo.

    Ademas de la base, descarta la sesion VIVA en memoria. Sin eso el proceso
    seguiria recordando el historial, si ya escalo y el rol activo -- la base
    diria 'cerrada' y el asistente contestaria como si nada hubiera pasado.

    Cuerpo: {tenant, autor, autor_usuario_id, desenlace, nota?,
             clave_operacion?}

    Cerrar NO es devolver a la IA: libera la asignacion y deja la
    conversacion cerrada. Ver nucleo/relevo/transiciones.py.

    'desenlace' es OBLIGATORIO desde B6 (T17, §3.5) y sale del catalogo de
    /conversaciones/desenlaces. No hay valor por defecto a proposito: uno
    --'otro', el mas probable-- convertiria la columna en ruido, y la columna
    existe justo para poder contar en que terminan los casos.
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400
    try:
        autor, autor_id, _ = _autor_y_clave(cuerpo)
    except persistencia.AutorInvalido as e:
        return jsonify({"error": f"Autor invalido: {mensaje_publico(e, 'datos de autor incompletos')}"}), 400

    try:
        r = transiciones.resolver(tenant, id_conversacion, operador_id=autor_id,
                                  operador_nombre=autor,
                                  desenlace=(cuerpo.get("desenlace") or "").strip(),
                                  nota=(cuerpo.get("nota") or "").strip() or None,
                                  config=_config_de(tenant),
                                  clave=(cuerpo.get("clave_operacion") or "").strip() or None)
    except ValueError as e:
        # Desenlace ausente, fuera del catalogo o nota demasiado larga. Es un
        # error del pedido, no una falla: 400 y el motivo, para que la pantalla
        # pueda decirlo en vez de mostrar "no se pudo guardar".
        return jsonify({"error": mensaje_publico(e, "desenlace invalido")}), 400
    except Exception as e:
        registrar("conversaciones", "fallo al resolver", error=e)
        return jsonify({"error": "No se pudo guardar."}), 500

    if r.motivo == "no_existe":
        return jsonify({"error": f"La conversacion '{id_conversacion}' no existe."}), 404

    # La clave de _sesiones lleva el canal: sin el, resolver un hilo del
    # simulador descartaba tambien la sesion real del mismo telefono.
    if r.datos.get("usuario_externo"):
        _sesiones.pop(canales.clave_sesion_de_fila(
            tenant, r.datos.get("canal"), r.datos["usuario_externo"]), None)
    return jsonify({"resuelta": True})


@app.delete("/conversaciones/<id_conversacion>")
def conversaciones_borrar(id_conversacion):
    """
    SOLO PARA PRUEBAS -- borra la conversacion entera (mensajes, tool_calls
    y adjuntos en cascada, ver persistencia.borrar_conversacion) y limpia
    el estado en memoria de esa sesion, para que la proxima vez que ese
    numero le escriba al bot arranque de cero: sin eso, aunque la base
    quede vacia, el proceso seguiria recordando el rol activo, si ya
    escalo, y el historial de la conversacion borrada.

    Pensado para el boton "Reiniciar (prueba)" del entrenamiento por
    WhatsApp real -- sacar este endpoint y el boton cuando termine esa
    etapa.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400

    try:
        borrada = persistencia.borrar_conversacion(tenant, id_conversacion)
    except Exception as e:
        registrar("conversaciones", "fallo al borrar", error=e)
        return jsonify({"error": "No se pudo borrar."}), 500

    if not borrada:
        return jsonify({"error": f"La conversacion '{id_conversacion}' no existe."}), 404

    _sesiones.pop(canales.clave_sesion_de_fila(
        tenant, borrada.get("canal"), borrada["usuario_externo"]), None)
    return "", 204


@app.get("/conversaciones/<id_conversacion>/media")
def conversaciones_media(id_conversacion):
    """Que adjuntos tiene una conversacion, SIN los bytes -- la bandeja pide
    cada archivo aparte por su id."""
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        return jsonify({"media": persistencia.media_de(tenant, id_conversacion)})
    except Exception as e:
        registrar("media", "fallo al listar", error=e)
        return jsonify({"error": "No se pudieron leer los adjuntos."}), 500


@app.get("/media/<id_media>")
def media_archivo(id_media):
    """
    El archivo en si. Sale con los bytes crudos y su mime, para que la interfaz
    lo use directo en un <img> sin pasarlo por base64.

    El aislamiento por empresa lo hace la politica de la base, no un if: pedir
    el id de otra empresa devuelve 404 porque la fila sencillamente no se ve.
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        encontrado = persistencia.media_bytes(tenant, id_media)
    except Exception as e:
        registrar("media", "fallo al leer", id_media=id_interno(id_media), error=e)
        return jsonify({"error": "No se pudo leer el archivo."}), 500

    if not encontrado:
        return jsonify({"error": "No existe."}), 404

    contenido, mime = encontrado
    # Cache larga: el contenido de un id nunca cambia (se inserta una vez y se
    # borra por antiguedad), asi que revalidar seria trafico puro.
    return contenido, 200, {"Content-Type": mime,
                            "Cache-Control": "private, max-age=86400"}


@app.get("/informes/<media_id>")
def informe_archivo(media_id):
    """
    Un archivo GENERADO por el motor (nucleo/herramientas/informes.py), no
    recibido de WhatsApp -- por eso no comparte ruta con /media/<id_media>.

    Esa otra ruta busca por 'id' (la clave primaria de asistente.media,
    generada por Postgres). Esta busca por 'media_id' (el UUID que el codigo
    elige ANTES de insertar la fila, para poder mencionarlo en la respuesta
    del modelo desde motor.responder() -- que corre antes de que 'id' exista.
    Ver persistencia.media_bytes_por_media_id().
    """
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400
    try:
        encontrado = persistencia.media_bytes_por_media_id(tenant, media_id)
    except Exception as e:
        registrar("informes", "fallo al leer", media_id=id_interno(media_id), error=e)
        return jsonify({"error": "No se pudo leer el archivo."}), 500

    if not encontrado:
        return jsonify({"error": "No existe."}), 404

    contenido, mime = encontrado
    return contenido, 200, {"Content-Type": mime,
                            "Cache-Control": "private, max-age=86400"}


@app.post("/mantenimiento/<tenant>/purgar")
def mantenimiento_purgar(tenant):
    """
    Aplica la retencion declarada por la empresa: borra lo vencido.

    Vive en el motor y no en el CRM por una razon concreta, y hay una leccion
    ajena que la respalda: la purga de notificaciones del CRM estuvo borrando
    CERO filas todas las noches durante meses, porque un worker de Celery no
    pasa por el middleware que fija el contexto de aislamiento, y la politica
    filtra contra un valor vacio que no coincide con nada. Nunca fallo; solo no
    hizo nada, y no lo registraba.

    Aca eso no puede pasar: db.sesion() fija la empresa en cada operacion --
    es la misma funcion que usa el resto del motor, no una ruta especial.

    NO va bajo /canales/whatsapp: ese prefijo es el que se expone a internet.
    Esto lo llama una tarea programada por la red interna.
    """
    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    dias_media = config.limites.retencion_multimedia_dias
    dias_conv = config.limites.retencion_conversaciones_dias

    salida = {"retencion_multimedia_dias": dias_media,
              "retencion_conversaciones_dias": dias_conv}
    try:
        # Multimedia primero: tiene el plazo mas corto, y borrarla antes deja
        # menos trabajo en cascada al borrar conversaciones.
        salida["media_borrada"] = persistencia.purgar_media(tenant, dias_media)
        salida["conversaciones_borradas"] = persistencia.purgar_conversaciones(
            tenant, dias_conv)
    except Exception as e:
        registrar("mantenimiento", "fallo la purga", tenant=tenant, error=e)
        return jsonify({"error": "No se pudo completar la purga."}), 500

    registrar("mantenimiento", "purga", tenant=tenant,
              archivos_borrados=salida["media_borrada"], dias_media=dias_media,
              conversaciones_borradas=salida["conversaciones_borradas"], dias_conversaciones=dias_conv)
    return jsonify(salida)


@app.get("/salud")
def salud():
    return jsonify({"estado": "ok"})


if __name__ == "__main__":
    # Solo el servidor. El reloj de tareas periodicas se mudo a su propio
    # proceso -- 'python -m nucleo.reloj', servicio 'motor-reloj' del compose.
    #
    # Aca vivia como un hilo arrancado desde este mismo bloque, y en produccion
    # NUNCA corrio: el compose levanta el motor con gunicorn, que IMPORTA este
    # modulo en vez de ejecutarlo, asi que '__main__' no pasa nunca. Colgar un
    # trabajo periodico del arranque del servidor web lo deja atado a COMO se
    # arranque el servidor web, y eso cambio sin que nadie lo notara.
    puerto = int(os.environ.get("PUERTO_API", "5000"))
    app.run(host="0.0.0.0", port=puerto)
