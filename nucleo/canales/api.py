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

import os
from pathlib import Path
import threading
import time

from flask import Flask, jsonify, request

from nucleo.canales import media, whatsapp
from nucleo.config import editor, fuente
from nucleo.config.fusion import fusionar_roles, modelo_fusionado
from nucleo.herramientas import http as ejecutor_http
from nucleo.herramientas import localidades as sincronizador_localidades
from nucleo.ingesta import corpus as ingesta
from nucleo.ingesta.docx import procesar
from nucleo.modelo import motor
from nucleo.persistencia import db as persistencia
from nucleo.recuperacion.busqueda import recuperar
from nucleo.recuperacion.prompt import piezas_del_system
from nucleo.seguimiento import agendamiento
from nucleo.seguimiento import operativo
from nucleo.seguimiento.forzado import (con_las_manos_vacias,
                                        escalada_forzada,
                                        motivos_por_hecho)
from nucleo.seguimiento import escalamiento
from nucleo.seguimiento import resumen
from nucleo.seguimiento import supervisor
from nucleo.seguridad import secretos
from nucleo.seguridad.verificacion import Sesion

app = Flask(__name__)

_configs: dict = {}    # tenant -> TenantConfig, cacheado por proceso
_servidas: dict = {}   # tenant -> (config_version servida, monotonic de la ultima comprobacion)
_sesiones: dict = {}   # (tenant, id_sesion) -> {"sesion": Sesion, "historial": [...]}

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
            print(f"[config] {tenant}: no se pudo comprobar la version "
                  f"({type(e).__name__}); se sigue con v{version}")
            _servidas[tenant] = (version, ahora)
            return servida
        if en_base == version:
            _servidas[tenant] = (version, ahora)
            return servida
        print(f"[config] {tenant}: la base tiene v{en_base} y este proceso "
              f"servia v{version} -- recargando")
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
    print("[auth] MOTOR_SERVICE_TOKEN activo: /chat, /agentes y el resto de "
         "rutas internas exigen el token de servicio.")
else:
    print("[auth] MOTOR_SERVICE_TOKEN no esta configurado -- las rutas "
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


def _error_al_guardar(e: Exception):
    """Todo lo que no sea un problema de la configuracion en si (la base
    inalcanzable, el tenant sin cargar) es un fallo del servidor, no del
    formulario: no se devuelve 400 porque no hay nada que el usuario pueda
    corregir escribiendo distinto."""
    print(f"[editor] fallo al guardar la configuracion: {type(e).__name__}: {e}")
    return jsonify({"error": f"No se pudo guardar en la base: {type(e).__name__}: {e}"}), 500


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
        print(f"[sesion] no se pudo leer el estado previo de {id_sesion}: "
              f"{type(e).__name__}: {e}")
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
    estado["ya_escalada"] = previo["escalada"]
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

    print(f"[sesion] {id_sesion}: se retoma la conversacion abierta "
          f"(escalada={previo['escalada']}, "
          f"verificado={'si' if previo['id_cliente'] else 'no'})")
    return estado


def atender_turno(config, tenant: str, rol: str, id_sesion: str,
                  mensaje: str, canal: str, profile_id: str | None = None,
                  nombre_colaborador: str = "") -> dict:
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

    Devuelve {'respuesta', 'verificado', 'pausada'}. Levanta motor.ErrorMotor
    si el rol o el mensaje no son atendibles -- quien llama decide si eso es un
    400 (HTTP) o una linea de registro (webhook, donde no hay a quien
    devolverle un error).
    """
    # Antes de nada: si la conversacion anterior de esta persona quedo abierta
    # pero ya paso el plazo de inactividad, se la resume y se la cierra. Asi el
    # turno que sigue empieza limpio en vez de pegarse a un hilo de dias --
    # medido el 18/08/2026, uno llego a 67 mensajes y 180 horas mezclando tres
    # problemas, y el modelo terminaba repitiendo preguntas ya contestadas y
    # citando mediciones de cuatro horas antes como si fueran de ahora.
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
                _sesiones.pop((tenant, id_sesion), None)
                print(f"[conversacion] {id_sesion}: cerrada por {horas}h sin "
                      f"actividad, resumida en {len(texto)} caracteres")
        except Exception as e:
            print(f"[conversacion] no se pudo cerrar por inactividad: "
                  f"{type(e).__name__}: {e}")

    clave = (tenant, id_sesion)
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

    # Al abrir una conversacion nueva, lo que se sabia del cliente entra como
    # contexto -- no el historial entero, solo el resumen de la anterior.
    if nueva and not estado["historial"]:
        anterior = persistencia.resumen_anterior(tenant, canal, id_sesion)
        if anterior:
            estado["historial"].append(resumen.como_contexto(anterior))

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

    # --- repregunta pendiente del verificador de agendamiento -----------------
    # nucleo/seguimiento/agendamiento.py dejo esto en un turno anterior porque
    # el checklist del manual quedo con UN dato puntual sin confirmar. Se
    # inyecta como nota de sistema para este turno (no via 'nota_continuidad':
    # esta conversacion sigue con su historial intacto, no es el caso de
    # amnesia por reinicio) y se consume una sola vez.
    if estado.get("nota_pendiente"):
        estado["historial"].append({"role": "system", "content": estado["nota_pendiente"]})
        estado["nota_pendiente"] = None

    # --- si ya se escalo, el bot NO contesta ---------------------------------
    # Va antes de motor.responder() a proposito. Marcar la conversacion como
    # escalada y despues dejar que el modelo siga respondiendo deja al cliente
    # hablando con un bot justo despues de que se le dijo que lo iba a atender
    # una persona. Se verifica contra el CRM en vez de confiar en la marca:
    # cuando el humano cierra el caso, el asistente retoma solo.
    if estado["escalada"]:
        if escalamiento.caso_sigue_abierto(config, estado["caso_id"]):
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
            cerrado = False
            try:
                veredicto = escalamiento.evaluar(config, rol, estado["historial"]) or {}
                # Un "si" explicito cierra por si solo, aunque la pregunta
                # se le haya hecho dos turnos antes: el cliente contesto lo
                # que se le pregunto, y volver a preguntarle lo mismo es no
                # escucharlo. Visto en la prueba: dijo "listo entonces, ya
                # puedes cerrar" y se le repregunto.
                cerrado = bool(veredicto.get("resuelta")
                               or veredicto.get("confirma_cierre"))
            except Exception as e:
                print(f"[escalamiento] no se pudo evaluar el turno pausado: {e}")
            if cerrado and not persistencia.atendida_por_humano(
                    tenant, estado["conversacion_id"]):
                print(f"[escalamiento] {id_sesion}: el cliente da por cerrado, "
                      "pero nadie del equipo le respondio todavia -- no se cierra")
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
                    persistencia.registrar_mensaje(tenant, canal, id_sesion, rol, "user", mensaje)
                    persistencia.registrar_mensaje(tenant, canal, id_sesion, rol, "assistant", respuesta)
                except Exception as e:
                    print(f"[persistencia] no se pudo guardar la pregunta de cierre: {e}")
                return {"respuesta": respuesta,
                        "verificado": estado["sesion"].verificado,
                        "pausada": True}
            if not cerrado:
                # Dijo que le falta algo: la proxima vez se le vuelve a
                # preguntar en vez de darlo por cerrado de una.
                estado["cierre_propuesto"] = False

            if cerrado:
                respuesta = _mensaje_de_cierre(config)
                try:
                    conv, _ = persistencia.registrar_mensaje(
                        tenant, canal, id_sesion, rol, "user", mensaje)
                    persistencia.registrar_mensaje(
                        tenant, canal, id_sesion, rol, "assistant", respuesta)
                    operativo.cerrar_todo(
                        config, tenant,
                        {"id": conv, "caso_id": estado["caso_id"],
                         "ticket_operativo": persistencia.ticket_operativo_de(tenant, conv)},
                        (config.escalamiento.texto_cierre_confirmado or "").strip()
                        or "El cliente confirmo que su caso quedo resuelto.")
                    estado["escalada"] = False
                    estado["caso_id"] = None
                except Exception as e:
                    print(f"[operativo] no se pudo cerrar tras la confirmacion "
                          f"del cliente: {type(e).__name__}: {e}")
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
            if persistencia.atendida_por_humano(tenant, estado["conversacion_id"]):
                try:
                    persistencia.registrar_mensaje(
                        tenant, canal, id_sesion, rol, "user", mensaje)
                except Exception as e:
                    print(f"[persistencia] no se pudo guardar el mensaje del cliente: {e}")
                return {"respuesta": "", "verificado": estado["sesion"].verificado,
                        "pausada": True}

            respuesta = _mensaje_de_escalada(config, estado.get("motivo_escalada")) or \
                "Tu caso ya esta con un compañero del equipo."
            estado["historial"].append({"role": "assistant", "content": respuesta})
            try:
                persistencia.registrar_mensaje(tenant, canal, id_sesion, rol, "user", mensaje)
                persistencia.registrar_mensaje(tenant, canal, id_sesion, rol, "assistant", respuesta)
            except Exception as e:
                print(f"[persistencia] no se pudo guardar el turno pausado: {e}")
            return {"respuesta": respuesta,
                    "verificado": estado["sesion"].verificado,
                    "pausada": True}
        # El caso se cerro: el asistente vuelve a atender desde este turno.
        estado["escalada"] = False
        estado["caso_id"] = None
        # Y vuelve a poder escalar: el caso anterior ya no esta abierto, asi
        # que un caso nuevo no seria un duplicado sino uno legitimo.
        estado["ya_escalada"] = False

    respuesta, registro_herramientas, medios_pendientes = motor.responder(
        config, rol, mensaje, estado["historial"], estado["sesion"],
        nota_continuidad=nota_continuidad)

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

    conversation_id = None
    mensaje_id = None
    mensaje_usuario_id = None
    try:
        # El id del turno del CLIENTE se conserva: es a esa burbuja a la que
        # hay que colgarle la foto que mando, para que aparezca en el hilo
        # donde la mando y no en una lista aparte al final.
        _, mensaje_usuario_id = persistencia.registrar_mensaje(
            tenant, canal, id_sesion, rol, "user", mensaje, horas)
        conversation_id, mensaje_id = persistencia.registrar_mensaje(
            tenant, canal, id_sesion, rol, "assistant", respuesta, horas)
        # La sesion viva se queda con el id. Solo lo tenia cuando venia de una
        # conversacion ANTERIOR: si la creo este mismo proceso, quedaba en
        # None y las reglas que preguntan por esta fila --si ya la atendio una
        # persona, sobre todo-- respondian que no sin poder mirar.
        estado["conversacion_id"] = conversation_id
        for llamada in registro_herramientas:
            persistencia.registrar_llamada_herramienta(
                tenant, conversation_id, rol, llamada, profile_id=profile_id)
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
                print(f"[informes] no se pudo guardar el archivo generado: {e}")
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
                    {c: getattr(estado["sesion"], c, None)
                     for c in Sesion.CAMPOS_PERSISTIBLES
                     if getattr(estado["sesion"], c, None)})
            except Exception as e:
                print(f"[persistencia] no se pudo guardar la identidad: {e}")
    except Exception as e:  # nunca se rompe el turno por un fallo de persistencia
        print(f"[persistencia] no se pudo guardar el turno: {e}")

    # Solo conversaciones con un cliente final pueden terminar en un ticket
    # humano -- escalar la sesion de un colaborador no tiene destino. 'ya
    # escalada' vive en memoria del proceso (no en la base) porque evita una
    # lectura extra en cada turno; si el proceso se reinicia, en el peor caso
    # se re-evalua una vez mas, y escalar() es idempotente en la practica
    # (crea un ticket nuevo, pero no revienta nada).
    rol_cfg = config.roles.get(rol)
    cerrada = False
    # 'ya_escalada' frena la creacion de un SEGUNDO caso, no la evaluacion
    # entera: una conversacion que volvio de manos de una persona sigue
    # necesitando que alguien note cuando el cliente da el tema por cerrado.
    # Atado a esa bandera, el asistente contestaba con normalidad y no cerraba
    # nunca -- ni el chat, ni el caso, ni el ticket.
    if (conversation_id and rol_cfg and rol_cfg.orientado_a == "cliente_final"
            and not estado["escalada"]):
        try:
            evaluacion = escalamiento.evaluar(config, rol, estado["historial"])
        except Exception as e:
            print(f"[escalamiento] fallo al evaluar: {type(e).__name__}: {e}")
            evaluacion = None

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
        # Si esta conversacion YA tuvo su caso, no se abre otro: lo que
        # sigue vivo es la deteccion del cierre. Sin este freno, una vuelta
        # despues de que una persona la atendio podia crear un caso duplicado.
        if estado["ya_escalada"] and evaluacion:
            evaluacion = {**evaluacion, "escalar": False}

        forzado, motivo_forzado = escalada_forzada(config, registro_herramientas)
        if estado["ya_escalada"]:
            forzado, motivo_forzado = None, ""
        if forzado:
            evaluacion = dict(evaluacion or {})
            if not evaluacion.get("escalar"):
                print(f"[escalamiento] forzado por '{forzado}': {motivo_forzado}")
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
            evaluacion.setdefault(
                "resumen",
                f"Pedido del cliente: {pedido}" if pedido else
                f"El evaluador no dejo resumen. Lo que se sabe: escalo "
                f"porque {motivo_forzado}. El detalle exacto esta abajo, "
                f"en lo que ya se probo.")
        # De que es esta conversacion. Se guarda SIEMPRE que el evaluador
        # haya clasificado, escale o no: el 'caso_manual' ya se calculaba en
        # cada turno pero solo se leia para decidir el agendamiento
        # automatico, y despues se tiraba -- una conversacion que el
        # asistente resolvio solo terminaba en la bandeja sin ninguna
        # etiqueta de que trataba. Ver supabase/202608180923_caso_conversacion.sql.
        if evaluacion and evaluacion.get("caso_manual"):
            persistencia.marcar_caso(tenant, conversation_id,
                                     evaluacion["caso_manual"])

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
            print("[agendamiento] se retoma el caso pospuesto: el modelo no "
                  "volvio a escalar por su cuenta")
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
                print(f"[escalamiento] {id_sesion}: se pospone '"
                      f"{evaluacion.get('motivo')}' -- el asistente todavia no "
                      "habia hecho nada")
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
                print(f"[escalamiento] {id_sesion}: '{evaluacion.get('motivo')}' "
                      "se pospone una vuelta -- el asistente lo intenta primero")

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
                print(f"[agendamiento] VETADO por {veto}: no se agenda visita "
                      "individual, el caso sigue el camino normal")
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
                    print(f"[agendamiento] evidencia suficiente ({directo}): "
                          f"se agenda sin pasar por el checklist del manual")
                    veredicto = {"checklist_completo": True,
                                 "corresponde_agendar": True,
                                 "descripcion_visita": (evaluacion.get("resumen") or "")[:400]}
                else:
                    try:
                        veredicto = agendamiento.verificar(config, tenant, rol, estado["historial"])
                    except Exception as e:
                        print(f"[agendamiento] fallo al verificar: {type(e).__name__}: {e}")
                        veredicto = None

                # Sin esta linea, un veredicto que dice "no" es invisible: no
                # hay ticket, no hay error, y desde afuera se ve igual que si
                # el agendamiento no estuviera configurado.
                if veredicto:
                    print(f"[agendamiento] caso='{caso_manual}' "
                          f"checklist_completo={veredicto.get('checklist_completo')} "
                          f"corresponde_agendar={veredicto.get('corresponde_agendar')} "
                          f"falta={veredicto.get('pregunta_faltante') or '-'}")

                if veredicto and veredicto.get("checklist_completo") and veredicto.get("corresponde_agendar"):
                    id_ticket_auto = agendamiento.agendar(
                        config, tenant, estado["sesion"], herramienta_auto,
                        veredicto.get("descripcion_visita", ""))
                    if id_ticket_auto:
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
                if nombre_ticket:
                    # La sugerencia va PRIMERO en la descripcion, no al
                    # final: un ticket con asunto generico se abre para saber
                    # de que es, y quien lo lee tiene que encontrar eso en la
                    # primera linea. Al pie se lo come el resto del texto.
                    descripcion_ticket = (evaluacion.get("resumen", "") or "")
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
                        print(f"[escalamiento] ticket operativo #{id_ticket_operativo} "
                              f"creado con '{nombre_ticket}'")
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
                        print("[escalamiento] no se pudo crear el ticket "
                              f"operativo con '{nombre_ticket}'")

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

                caso_creado = escalamiento.escalar(
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
                # La pausa (arriba, "si ya se escalo, el bot NO contesta")
                # solo tiene sentido cuando de verdad hay un humano al que
                # esperar -- si se agendo solo, el bot sigue atendiendo
                # normal desde el proximo mensaje.
                estado["escalada"] = necesita_humano
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
                    print(f"[escalamiento] no se pudo leer el caso de la conversacion: {e}")
                # Escalo y no quedo registrado en ningun lado: no se le
                # puede decir al cliente que si.
                #
                # Alcanza con que haya quedado en UNO de los dos: el caso lo
                # pone en la cola del CRM y el ticket operativo en la de la
                # operacion. Cualquiera de los dos es una persona que lo va a
                # ver, que es lo que el aviso promete. Si no quedo en ninguna
                # -- el 28/08/2026 el CRM rechazo un caso con un 400 y al
                # cliente se le contesto igual que su pedido habia quedado
                # registrado -- se le dice la verdad y se le pide que escriba
                # de nuevo, que es lo que dispara el reintento.
                if id_ticket_auto or caso_creado or id_ticket_operativo:
                    respuesta = respuesta_al_cliente
                else:
                    respuesta = _mensaje_si_no_quedo(config) or respuesta
                estado["ya_escalada"] = True
                # El mensaje del asistente ya se guardo (mas arriba, antes de
                # poder evaluar la escalada -- necesitaba conversation_id).
                # Sin esto el HTTP response trae el aviso pero /conversaciones
                # sigue mostrando el texto de antes.
                if mensaje_id:
                    try:
                        persistencia.actualizar_contenido_mensaje(tenant, mensaje_id, respuesta)
                    except Exception as e:
                        print(f"[persistencia] no se pudo actualizar el aviso de escalada: {e}")
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
                    print(f"[persistencia] no se pudo agregar la pregunta de cierre: {e}")
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
                caso = estado.get("caso_id") or persistencia.caso_de_conversacion(
                    tenant, conversation_id)
                if caso:
                    operativo.cerrar_todo(
                        config, tenant,
                        {"id": conversation_id, "caso_id": caso,
                         "ticket_operativo": persistencia.ticket_operativo_de(
                             tenant, conversation_id)},
                        (config.escalamiento.texto_cierre_confirmado or "").strip()
                        or "El cliente confirmo que su caso quedo resuelto.")
                else:
                    persistencia.cerrar_conversacion(tenant, conversation_id)
                cerrada = True
            except Exception as e:
                print(f"[conversaciones] no se pudo cerrar la conversacion: {e}")
            # El supervisor audita la conversacion ya cerrada y deja un
            # veredicto PENDIENTE para que una persona lo confirme desde
            # /manual -- nunca publica solo (ver nucleo/seguimiento/
            # supervisor.py). Aparte del cierre: un fallo aca no debe
            # revertir que la conversacion ya quedo cerrada.
            try:
                supervisor.revisar(config, rol, tenant, conversation_id, estado["historial"])
            except Exception as e:
                print(f"[supervisor] fallo al revisar la conversacion: {e}")

    return {"respuesta": respuesta, "verificado": estado["sesion"].verificado,
            "cerrada": cerrada, "conversacion_id": conversation_id,
            "mensaje_id": mensaje_id, "mensaje_usuario_id": mensaje_usuario_id,
            "pausada": False}


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
    tenant = cuerpo.get("tenant")
    rol = cuerpo.get("rol")
    profile_id = cuerpo.get("profile_id")
    id_sesion = cuerpo.get("identificador_sesion")
    mensaje = cuerpo.get("mensaje")
    canal = cuerpo.get("canal", "api")
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
            print(f"[agentes] fallo al resolver los de '{profile_id}': "
                  f"{type(e).__name__}: {e}")
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
            return jsonify({"error": str(e)}), 400
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
        return jsonify({"error": str(e)}), 400

    # 'pausada' solo viaja cuando es cierto: es la forma que ya devolvia /chat
    # antes de que existiera el webhook, y el simulador depende de ella.
    if not salida.get("pausada"):
        salida.pop("pausada", None)
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
        print(f"[agentes] '{cfg.herramienta_listado}' no esta en el catalogo")
        return []
    try:
        crudo = motor._ejecutar_tool(herramienta, None, {}, tenant,
                                     config.variables_tenant)
    except Exception as e:
        print(f"[agentes] no se pudieron listar los candidatos externos: "
              f"{type(e).__name__}: {e}")
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
        print(f"[agentes] fallo al listar asignaciones: {type(e).__name__}: {e}")
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
            print(f"[agentes] fallo al leer identidades externas: "
                  f"{type(e).__name__}: {e}")
        candidatos = _candidatos_externos(config, tenant)

    try:
        areas_por_persona = persistencia.areas_de_colaboradores(tenant)
    except Exception as e:
        print(f"[agentes] fallo al leer areas: {type(e).__name__}: {e}")
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
        print(f"[agentes] fallo al leer areas: {type(e).__name__}: {e}")
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
        print(f"[agentes] fallo al asignar a '{profile_id}': {type(e).__name__}: {e}")
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
            print(f"[agentes] fallo al guardar el area de '{profile_id}': "
                  f"{type(e).__name__}: {e}")

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
            print(f"[agentes] fallo al guardar la identidad externa de "
                  f"'{profile_id}': {type(e).__name__}: {e}")
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
        return jsonify({"error": str(e)}), 400
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
        return jsonify({"error": str(e)}), 400
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
        return jsonify({"error": str(e)}), 400
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
        return jsonify({"error": str(e)}), 400
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
        print(f"[reportes] fallo al calcular escalamiento: {type(e).__name__}: {e}")
        return jsonify({"error": "No se pudo calcular el reporte."}), 500

    return jsonify({"dias": dias, **r})


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
        return jsonify({"error": str(e)}), 400
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
        return jsonify({"error": str(e)}), 400
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
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return _error_al_guardar(e)

    olvidar_config(tenant)
    herramienta = next(h for h in config.herramientas if h.nombre == "agendar_visita_tecnica")
    return jsonify({"dias": herramienta.fechas_automaticas.get("fecha_final")})


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
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return _error_al_guardar(e)

    olvidar_config(tenant)
    w = config.canales.whatsapp
    return jsonify({"activo": w.activo, "numero_visible": w.numero_visible})


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
        return jsonify({"error": str(e)}), 400
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
        return jsonify({"error": str(e)}), 400
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
        return jsonify({"error": f"No se pudo cargar la config: {e}"}), 500

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

    try:
        salida = motor.ejecutar_para_servicio(config, herramienta, argumentos)
    except Exception as e:
        print(f"[interno] '{nombre}' fallo: {type(e).__name__}: {e}")
        return jsonify({"error": f"{type(e).__name__}: {e}"}), 502

    return jsonify({"resultado": salida})


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
        return jsonify({"error": f"No se pudo sincronizar contra el "
                                 f"proveedor: {type(e).__name__}: {e}"}), 502

    try:
        nuevo = editor.guardar_localidades(
            tenant, [l.model_dump(mode="json") for l in localidades])
    except editor.ErrorEdicion as e:
        return jsonify({"error": str(e)}), 400
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
        return jsonify({"error": str(e)}), 400
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
        return jsonify({"error": str(e)}), 500
    except Exception as e:
        print(f"[secretos] fallo al listar: {type(e).__name__}: {e}")
        return jsonify({"error": "No se pudieron leer los secretos."}), 500


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
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"[secretos] fallo al guardar '{nombre}': {type(e).__name__}: {e}")
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
        print(f"[secretos] fallo al borrar '{nombre}': {type(e).__name__}: {e}")
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
        return jsonify({"ok": False, "detalle": f"{type(e).__name__}: {e}"})

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
    return jsonify({"ok": False, "detalle": f"HTTP {r.status_code}: {r.text[:200]}"})


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
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"[conversaciones] fallo al listar: {type(e).__name__}: {e}")
        return jsonify({"error": "No se pudo leer las conversaciones."}), 500

    return jsonify({"tenant": tenant, "conversaciones": salida})


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
        print(f"[conversaciones] fallo al buscar por caso: {type(e).__name__}: {e}")
        return jsonify({"error": "No se pudo leer la conversacion."}), 500
    if not datos:
        return jsonify({"conversacion": None}), 200

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
    datos["enlaces"] = _enlaces_externos(config, datos, tenant) if config else {}
    return jsonify({"conversacion": datos})


def _enlaces_externos(config, conv: dict, tenant: str) -> dict:
    """
    A donde puede saltar un colaborador desde el ticket, con el cliente ya
    seleccionado.

    Devuelve solo los que se pueden armar de verdad. Un enlace faltante NO es
    un error: se escala una conversacion justamente cuando el asistente no
    pudo avanzar, y muchas veces eso incluye no haber identificado al cliente.
    Medido sobre 85 conversaciones reales: 45 con cliente identificado y 12 con
    ticket, y las que llegan a ticket tienden a ser las otras. Que la pantalla
    diga "no disponible" es el caso NORMAL, no una falla que haya que reportar.
    """
    v = config.variables_tenant or {}
    panel = (v.get("WISPHUB_PANEL_URL") or "").rstrip("/")
    sufijo = v.get("WISPHUB_SUFIJO_USUARIO") or ""
    olt = (v.get("SMARTOLT_SUBDOMINIO") or "").rstrip("/")

    id_cliente = conv.get("id_cliente")
    sesion = conv.get("datos_sesion") or {}
    sn_onu = sesion.get("sn_onu")

    enlaces = {}

    # El 'usuario' del sistema externo NO viene en el detalle del cliente,
    # solo en el LISTADO -- verificado el 25/08/2026: el detalle lo devuelve
    # vacio y el listado lo trae completo. Es el mismo patron que esa API
    # ya mostro otras veces: dos endpoints del mismo proveedor dicen cosas
    # distintas del mismo registro (ver la skill del proveedor en .claude/).
    ficha = _ficha_cliente(config, id_cliente, tenant)
    usuario, ip = ficha.get("usuario"), ficha.get("ip")

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

    # La ficha del cliente va aparte de los enlaces: son datos, no destinos.
    if ficha:
        enlaces["cliente"] = {k: v for k, v in ficha.items() if k != "usuario"}

    return enlaces


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
            print(f"[enlaces] '{nombre}' no respondio: {type(e).__name__}: {e}")
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
_CAMPOS_FICHA = ("usuario", "ip", "estado", "nombre", "cedula")


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
        print(f"[enlaces] no se pudo leer la ficha del cliente: "
              f"{type(e).__name__}: {e}")
        return {}


@app.get("/conversaciones/<id_conversacion>/mensajes")
def conversaciones_mensajes(id_conversacion):
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400

    try:
        resultado = persistencia.mensajes_de(tenant, id_conversacion)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"[conversaciones] fallo al leer mensajes: {type(e).__name__}: {e}")
        return jsonify({"error": "No se pudo leer la conversacion."}), 500

    if resultado["conversacion"] is None:
        return jsonify({"error": f"La conversacion '{id_conversacion}' no existe."}), 404

    return jsonify(resultado)


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
        print(f"[conversaciones] fallo al resolver el caso {caso_id}: "
              f"{type(e).__name__}: {e}")
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
    # Quien contesta. Lo manda la pantalla porque el motor no lee las tablas
    # del CRM, y sirve para firmar la copia que va al ticket del ISP: ahi toda
    # respuesta queda a nombre de la cuenta de la API key, asi que sin esto el
    # historico del ticket dice que contesto el sistema.
    autor = (cuerpo.get("autor") or "").strip()
    # Si con esta respuesta la persona da por terminada su parte. Lo elige
    # ella: acaba de hacer el trabajo y sabe si le quedo algo preguntado al
    # cliente. Ver devolver_al_asistente().
    devolver = bool(cuerpo.get("devolver_al_asistente"))
    if not tenant or not contenido:
        return jsonify({"error": "Faltan campos: tenant, mensaje"}), 400

    try:
        destino = persistencia.agregar_mensaje_humano(
            tenant, id_conversacion, contenido, autor)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"[conversaciones] fallo al guardar respuesta humana: {type(e).__name__}: {e}")
        return jsonify({"error": "No se pudo guardar la respuesta."}), 500

    if destino is None:
        return jsonify({"error": f"La conversacion '{id_conversacion}' no existe."}), 404

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
    clave_sesion = (tenant, destino["usuario_externo"])
    if clave_sesion in _sesiones:
        quien = autor or "Compañero del equipo"
        _sesiones[clave_sesion]["historial"].append(
            {"role": "assistant", "content": f"({quien}) {contenido}"})

    if devolver:
        persistencia.devolver_al_asistente(tenant, id_conversacion)
        # Y la sesion VIVA, no solo la base: la pausa se decide con lo que
        # tiene este proceso en memoria, asi que sin esto el asistente seguia
        # callado hasta el proximo reinicio.
        if clave_sesion in _sesiones:
            _sesiones[clave_sesion]["escalada"] = False
            # 'ya_escalada' se deja como esta: es lo que evita que la misma
            # conversacion abra un segundo caso. Lo que se apaga es la pausa,
            # no la memoria de que esto ya paso por una persona.

    salida = {"ok": True, "entregado": False, "devuelto_al_asistente": devolver}

    # La misma respuesta, copiada al ticket del sistema del ISP. Va aparte de
    # la entrega al cliente y no la condiciona: que la operacion no se entere
    # es un problema, pero uno menor que no contestarle a quien espera.
    if destino.get("ticket_operativo"):
        try:
            config = _config_de(tenant)
            salida["copiado_al_ticket"] = operativo.responder(
                config, tenant, destino["ticket_operativo"], contenido, autor)
        except Exception as e:
            print(f"[operativo] no se pudo copiar la respuesta al ticket: "
                  f"{type(e).__name__}: {e}")
            salida["copiado_al_ticket"] = False

    if destino["canal"] != "whatsapp":
        # El simulador y la API no tienen a donde entregar: la conversacion se
        # lee desde la misma pantalla. No es un fallo.
        salida["entregado"] = None
        return jsonify(salida), 201

    try:
        config = _config_de(tenant)
        whatsapp.enviar_texto(config, tenant, destino["usuario_externo"], contenido)
        salida["entregado"] = True
    except Exception as e:
        # 201 igual: el mensaje SI quedo guardado, y el agente tiene que verlo
        # en el hilo. Lo que no ocurrio es la entrega, y eso se dice con todas
        # las letras en vez de devolver un error que sugiera que se perdio todo.
        print(f"[conversaciones] no se pudo entregar la respuesta humana de "
              f"'{id_conversacion}': {type(e).__name__}: {e}")
        salida["aviso"] = str(e)

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
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"[conversaciones] fallo al leer herramientas: {type(e).__name__}: {e}")
        return jsonify({"error": "No se pudo leer el registro de herramientas."}), 500

    return jsonify({"herramientas": llamadas})


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
        print(f"[manual] fallo al marcar ejemplo: {type(e).__name__}: {e}")
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
        print(f"[manual] fallo al desmarcar ejemplo: {type(e).__name__}: {e}")
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
        print(f"[sugerencias] no se pudo recuperar: {type(e).__name__}: {e}")
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
        return jsonify({"error": str(e)}), 400
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
        print(f"[manual] fallo al leer ejemplos: {type(e).__name__}: {e}")
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
        print(f"[supervisor] fallo al leer revisiones: {type(e).__name__}: {e}")
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
        print(f"[supervisor] fallo al actualizar revision: {type(e).__name__}: {e}")
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
        print(f"[configuracion-guiada] fallo al leer propuestas: {type(e).__name__}: {e}")
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
        print(f"[configuracion-guiada] fallo al leer la propuesta: {type(e).__name__}: {e}")
        return jsonify({"error": "No se pudo leer la propuesta."}), 500
    if not propuesta:
        return jsonify({"error": f"La propuesta '{id_propuesta}' no existe."}), 404
    if propuesta["estado"] != "pendiente":
        return jsonify({"error": f"Esta propuesta ya esta '{propuesta['estado']}', "
                                 f"no se puede volver a aprobar."}), 400

    try:
        editor.aprobar_herramienta_propuesta(tenant, propuesta["herramienta_propuesta"])
    except editor.ErrorEdicion as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        return _error_al_guardar(e)

    olvidar_config(tenant)
    try:
        persistencia.resolver_herramienta_propuesta(
            tenant, id_propuesta, "aprobada", cuerpo.get("revisado_por"))
    except Exception as e:
        # La herramienta YA quedo escrita en el catalogo -- esto solo afecta
        # el rotulo de la propuesta. No se revierte lo ya guardado por esto.
        print(f"[configuracion-guiada] la herramienta se agrego pero no se "
             f"pudo marcar la propuesta como aprobada: {type(e).__name__}: {e}")

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
        print(f"[configuracion-guiada] fallo al rechazar: {type(e).__name__}: {e}")
        return jsonify({"error": "No se pudo guardar."}), 500

    if not existe:
        return jsonify({"error": f"La propuesta '{id_propuesta}' no existe."}), 404
    return jsonify({"ok": True, "estado": "rechazada"})


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
        print(f"[acciones] fallo al leer propuestas: {type(e).__name__}: {e}")
        return jsonify({"error": "No se pudieron leer las acciones propuestas."}), 500
    return jsonify({"acciones": acciones})


@app.post("/acciones/propuestas/<id_accion>/aprobar")
def acciones_propuesta_aprobar(id_accion):
    """
    Ejecuta la escritura real contra la API externa y RECIEN DESPUES marca
    la accion como 'aprobada' -- mismo orden que aprobar una herramienta
    propuesta: si la API la rechaza, el resultado (y el error) quedan
    visibles en la misma fila, no se pierde ni se finge que salio bien.
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'."}), 400

    try:
        accion = persistencia.accion_propuesta_de(tenant, id_accion)
    except Exception as e:
        print(f"[acciones] fallo al leer la accion: {type(e).__name__}: {e}")
        return jsonify({"error": "No se pudo leer la accion."}), 500
    if not accion:
        return jsonify({"error": f"La accion '{id_accion}' no existe."}), 404
    if accion["estado"] != "pendiente":
        return jsonify({"error": f"Esta accion ya esta '{accion['estado']}', "
                                 f"no se puede volver a aprobar."}), 400

    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

    resultado, codigo_error = motor.ejecutar_accion_aprobada(config, accion)

    try:
        persistencia.resolver_accion_propuesta(
            tenant, id_accion, "aprobada", cuerpo.get("revisado_por"),
            resultado_ejecucion=resultado, codigo_error=codigo_error)
    except Exception as e:
        print(f"[acciones] la accion se ejecuto pero no se pudo guardar el "
             f"resultado: {type(e).__name__}: {e}")

    if codigo_error:
        return jsonify({"ok": False, "estado": "aprobada", "error_ejecucion": codigo_error,
                        "resultado": resultado}), 502
    return jsonify({"ok": True, "estado": "aprobada", "resultado": resultado})


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
        print(f"[acciones] fallo al rechazar: {type(e).__name__}: {e}")
        return jsonify({"error": "No se pudo guardar."}), 500

    if not existe:
        return jsonify({"error": f"La accion '{id_accion}' no existe."}), 404
    return jsonify({"ok": True, "estado": "rechazada"})


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
        return jsonify({"error": str(e)}), 400

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

            with persistencia.sesion(tenant) as (cur, org):
                resultado = ingesta.ingerir(
                    cur, org, doc, hash_,
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
        return jsonify({"error": str(e)}), 409
    except ValueError as e:
        return jsonify({"error": f"El documento declara {e}"}), 400
    except Exception as e:
        print(f"[corpus] fallo la ingesta de '{nombre}': {type(e).__name__}: {e}")
        return jsonify({"error": f"No se pudo procesar el documento: {e}"}), 500

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
        print(f"[corpus] fallo al aprobar '{id_documento}': {type(e).__name__}: {e}")
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
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"[corpus] fallo el retiro de '{id_documento}': {type(e).__name__}: {e}")
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
        return jsonify({"error": str(e)}), 400

    try:
        with persistencia.sesion(tenant) as (cur, org):
            ok = ingesta.actualizar_roles(cur, org, id_documento, roles)
    except Exception as e:
        print(f"[corpus] fallo al actualizar roles de '{id_documento}': {type(e).__name__}: {e}")
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

    Se busca por 'orientado_a', no por nombre: el nucleo no puede saber como
    llamo cada empresa a su rol de autoservicio (PRD 3 / ARQUITECTURA.md), y
    fijar 'cliente_final' como literal seria conocimiento de un tenant."""
    for nombre, rol in config.roles.items():
        if rol.orientado_a == "cliente_final":
            return nombre
    return None


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
            print(f"[whatsapp] baja de avisos: {de}")
            return True
        if limpio in [p.lower() for p in cfg.palabras_alta]:
            persistencia.dar_de_alta(tenant, de, "whatsapp")
            whatsapp.enviar_texto(config, tenant, de, cfg.respuesta_alta)
            print(f"[whatsapp] alta de avisos: {de}")
            return True
    except Exception as e:
        # Si falla, se deja seguir al modelo: peor que no registrar la baja
        # seria dejar el mensaje sin ninguna respuesta.
        print(f"[whatsapp] fallo al procesar baja/alta de {de}: "
              f"{type(e).__name__}: {e}")
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
        print(f"[whatsapp] adjunto {media_id} guardado "
              f"({len(crudo) // 1024} KB -> {len(contenido) // 1024} KB)")
    except Exception as e:
        print(f"[whatsapp] no se pudo guardar el adjunto {media_id}: "
              f"{type(e).__name__}: {e}")


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
        print(f"[whatsapp] {de} llega sin telefono (BSUID): se contesta igual, "
              f"pero no se puede reconocer al cliente sin que se identifique.")

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

        salida = atender_turno(config, tenant, rol, de, texto, "whatsapp")

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
            whatsapp.enviar_texto(config, tenant, de, salida["respuesta"])
    except Exception as e:
        print(f"[whatsapp] fallo al atender a {de} ({wamid}): "
              f"{type(e).__name__}: {e}")


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
        print(f"[whatsapp] handshake rechazado para '{tenant}': token invalido")
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
        print(f"[whatsapp] firma invalida en el webhook de '{tenant}'")
        return jsonify({"error": "firma invalida"}), 401

    cuerpo = request.get_json(force=True, silent=True) or {}

    rol = _rol_de_cliente(config)
    if not rol:
        print(f"[whatsapp] '{tenant}' no tiene ningun rol orientado a "
              f"cliente_final: no hay con que atender el mensaje")
        return jsonify({"recibido": True}), 200

    entrantes = whatsapp.mensajes_entrantes(cuerpo)
    estados = whatsapp.estados_entrantes(cuerpo)

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
                campos.append("value:" + ",".join(sorted(valor)))
        print(f"[whatsapp] entrega SIN mensajes ni estados. Contenido: "
              f"{campos or list((cuerpo or {}).keys())}")
    else:
        # Se dice de que forma llego el remitente, no solo cuantos mensajes.
        # Un identificador opaco ('CO.1360...') en vez de un telefono rompe la
        # verificacion por posesion del canal SIN dar ningun error: el cliente
        # queda como desconocido y se le pide la cedula aunque escriba desde su
        # propio numero. Es la clase de fallo que hay que poder ver de un
        # vistazo en vez de deducir.
        formas = [("telefono" if (e.get("de") or "").isdigit() else "OPACO")
                  for e in entrantes]
        print(f"[whatsapp] entrega con {len(entrantes)} mensaje(s) y "
              f"{len(estados)} estado(s). Remitente(s): {formas}")

        # Si el remitente vino opaco, hace falta saber que SI trajo la entrega
        # para encontrar donde esta el telefono. Se registran las CLAVES de
        # cada nivel, nunca los valores: el contenido es de un cliente.
        if "OPACO" in formas:
            for entrada in (cuerpo or {}).get("entry", []) or []:
                for cambio in entrada.get("changes", []) or []:
                    valor = cambio.get("value") or {}
                    contactos = valor.get("contacts") or []
                    print(f"[whatsapp] remitente opaco. field={cambio.get('field')!r} "
                          f"value={sorted(valor)} "
                          f"contacts={len(contactos)} "
                          f"claves_contacto={sorted(contactos[0]) if contactos else '-'} "
                          f"metadata={sorted(valor.get('metadata') or {})}")

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
            print(f"[whatsapp] mensaje descartado: sin "
                  f"{'wamid' if not wamid else 'remitente'}. "
                  f"tipo={entrante.get('tipo')!r} "
                  f"claves={sorted((entrante.get('crudo') or {}).keys())}")
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
            print(f"[whatsapp] no se pudo verificar duplicado de {wamid}, "
                  f"se descarta por precaucion: {type(e).__name__}: {e}")
            continue

        hilo = threading.Thread(
            target=_procesar_mensaje_whatsapp,
            args=(config, tenant, rol, entrante), daemon=True)
        hilo.start()
        atendidos += 1

    # Los acuses de entrega llegan por este mismo webhook y NO son
    # conversacion: sin separarlos, el bot contestaria a su propio "entregado".
    for estado in estados:
        if estado.get("estado") == "failed":
            print(f"[whatsapp] no se pudo entregar a {estado.get('de')}: "
                  f"codigo={estado.get('codigo')} {estado.get('error')} "
                  f"| detalle={estado.get('detalle')}")
            continue
        # Los acuses buenos tambien se registran. Antes solo se imprimian los
        # fallidos, y eso obligaba a deducir del SILENCIO que un mensaje habia
        # salido bien -- que es justo lo que no se puede distinguir de que el
        # acuse nunca llego. La categoria es lo que factura Meta.
        categoria = estado.get("categoria")
        print(f"[whatsapp] {estado.get('estado')} -> {estado.get('de')}"
              + (f" | conversacion={estado.get('conversacion')} ({categoria})"
                 if categoria else ""))

    return jsonify({"recibido": True, "atendidos": atendidos}), 200


@app.get("/corpus/documentos")
def corpus_documentos():
    tenant = request.args.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el parametro 'tenant'."}), 400

    try:
        documentos = persistencia.documentos_de(tenant)
    except Exception as e:
        print(f"[corpus] fallo al listar documentos: {type(e).__name__}: {e}")
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
        print(f"[corpus] fallo al leer fragmentos: {type(e).__name__}: {e}")
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
        print(f"[whatsapp] no se pudo comprobar la baja de {para}: {e}")
        return jsonify({"error": "No se pudo comprobar si el numero acepta avisos."}), 503

    try:
        wamid = whatsapp.enviar_plantilla(
            config, tenant, para, plantilla,
            cuerpo.get("variables"), cuerpo.get("idioma", "es"))
    except whatsapp.ErrorWhatsApp as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"[whatsapp] fallo el aviso a {para}: {type(e).__name__}: {e}")
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
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        print(f"[whatsapp] fallo al leer plantillas: {type(e).__name__}: {e}")
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
        print(f"[conversaciones] fallo al marcar conservar: {type(e).__name__}: {e}")
        return jsonify({"error": "No se pudo guardar."}), 500

    if not existe:
        return jsonify({"error": f"La conversacion '{id_conversacion}' no existe."}), 404
    return jsonify({"conservar": conservar, "motivo": motivo})


@app.post("/conversaciones/<id_conversacion>/atender")
def conversaciones_atender(id_conversacion):
    """
    Marca una conversacion escalada como atendida sin pasar por el chat --
    el colaborador la resolvio por telefono, en persona, o por otro canal, y
    no corresponde (o no hace falta) responderle al cliente por ahi. Ver
    persistencia.marcar_atendida().

    Distinto de responder de verdad (POST /conversaciones/<id>/humano): esa
    via ya deja la conversacion atendida sola, calculada. Esta es la manual,
    para cuando esa via no aplica.

    Cuerpo: {tenant, por?}
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    if not tenant:
        return jsonify({"error": "Falta el campo 'tenant'"}), 400

    try:
        existe = persistencia.marcar_atendida(tenant, id_conversacion, cuerpo.get("por"))
    except Exception as e:
        print(f"[conversaciones] fallo al marcar atendida: {type(e).__name__}: {e}")
        return jsonify({"error": "No se pudo guardar."}), 500

    if not existe:
        return jsonify({"error": f"La conversacion '{id_conversacion}' no existe."}), 404
    return jsonify({"atendida": True})


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
        print(f"[conversaciones] fallo al borrar: {type(e).__name__}: {e}")
        return jsonify({"error": "No se pudo borrar."}), 500

    if not borrada:
        return jsonify({"error": f"La conversacion '{id_conversacion}' no existe."}), 404

    _sesiones.pop((tenant, borrada["usuario_externo"]), None)
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
        print(f"[media] fallo al listar: {type(e).__name__}: {e}")
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
        print(f"[media] fallo al leer {id_media}: {type(e).__name__}: {e}")
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
        print(f"[informes] fallo al leer {media_id}: {type(e).__name__}: {e}")
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
        print(f"[mantenimiento] fallo la purga de '{tenant}': "
              f"{type(e).__name__}: {e}")
        return jsonify({"error": "No se pudo completar la purga."}), 500

    print(f"[mantenimiento] purga de '{tenant}': "
          f"{salida['media_borrada']} archivos (>{dias_media}d), "
          f"{salida['conversaciones_borradas']} conversaciones (>{dias_conv}d)")
    return jsonify(salida)


@app.get("/salud")
def salud():
    return jsonify({"estado": "ok"})


def _reloj_de_vencimientos() -> None:
    """
    Revisa los plazos cada tanto, para siempre.

    Vive dentro del motor y no en un cron aparte por una razon simple: el motor
    ya es el unico proceso que sabe leer la config de un tenant. Un cron
    externo tendria que resolver credenciales, tenants y plazos por su cuenta,
    o llamar a este mismo endpoint -- y entonces es infraestructura de mas para
    hacer lo mismo.

    Arranca solo si hay algun tenant con plazo declarado: sin eso seria un hilo
    despertandose cada hora para no hacer nada.
    """
    while True:
        time.sleep(operativo.INTERVALO_BARRIDO_SEGUNDOS)
        for tenant in _tenants_conocidos():
            try:
                config = _config_de(tenant)
            except Exception as e:
                print(f"[operativo] no se pudo leer la config de '{tenant}': "
                      f"{type(e).__name__}: {e}")
                continue
            if not config.escalamiento.cerrar_sin_respuesta_horas:
                continue
            try:
                operativo.cerrar_vencidas(config, tenant)
            except Exception as e:
                # Un fallo NO puede matar el hilo: si muere, deja de revisar
                # plazos para siempre y nadie se entera hasta que alguien nota
                # que ningun caso se cierra solo.
                print(f"[operativo] el barrido de '{tenant}' fallo: "
                      f"{type(e).__name__}: {e}")


def _tenants_conocidos() -> list[str]:
    """Los tenants que este despliegue sirve, por su archivo semilla."""
    return sorted(p.stem.replace(".config", "")
                  for p in Path("tenants").glob("*.config.yaml"))


if __name__ == "__main__":
    # Arranca SIEMPRE, aunque hoy ningun tenant tenga plazo. Condicionarlo a
    # la config del arranque parecia mas prolijo y era un bug: el plazo se
    # activa guardando la config, que es justo lo que este proceso NO relee al
    # decidir si crear el hilo -- se habria quedado dormido hasta el proximo
    # reinicio, sin que nadie entendiera por que no cerraba nada.
    #
    # No cuesta nada: cada pasada consulta la config ya cacheada y sale por
    # donde entro si no hay plazo declarado.
    threading.Thread(target=_reloj_de_vencimientos, daemon=True).start()
    print("[operativo] reloj de vencimientos activo: revisa los plazos cada "
          f"{operativo.INTERVALO_BARRIDO_SEGUNDOS // 60} minutos.")
    puerto = int(os.environ.get("PUERTO_API", "5000"))
    app.run(host="0.0.0.0", port=puerto)
