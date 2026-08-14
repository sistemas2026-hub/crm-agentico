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
import threading

from flask import Flask, jsonify, request

from nucleo.canales import media, whatsapp
from nucleo.config import editor, fuente
from nucleo.config.fusion import fusionar_roles, modelo_fusionado
from nucleo.ingesta import corpus as ingesta
from nucleo.ingesta.docx import procesar
from nucleo.modelo import motor
from nucleo.persistencia import db as persistencia
from nucleo.recuperacion.busqueda import recuperar
from nucleo.recuperacion.prompt import piezas_del_system
from nucleo.seguimiento import escalamiento
from nucleo.seguimiento import supervisor
from nucleo.seguridad import secretos
from nucleo.seguridad.verificacion import Sesion

app = Flask(__name__)

_configs: dict = {}    # tenant -> TenantConfig, cacheado por proceso
_sesiones: dict = {}   # (tenant, id_sesion) -> {"sesion": Sesion, "historial": [...]}


def _config_de(tenant: str):
    # La base manda; el YAML es semilla y respaldo. Ver nucleo/config/fuente.py.
    # Es la misma fila que escribe el editor (nucleo/config/editor.py), asi que
    # leer y guardar apuntan al mismo lugar -- por eso alcanza con vaciar este
    # cache para que un cambio de la interfaz se vea en el turno siguiente.
    if tenant not in _configs:
        _configs[tenant] = fuente.cargar(tenant)
    return _configs[tenant]


def olvidar_config(tenant: str) -> None:
    """Descarta la copia cacheada para que el proximo turno relea de la base.
    Se llama tras cada guardado del editor: sin esto, un cambio hecho desde la
    interfaz no se veria hasta reiniciar el proceso.

    Se descarta en vez de reemplazarse por lo que devolvio el editor, aunque
    sea el mismo objeto: asi lo que se sirve es siempre lo que quedo ESCRITO,
    y un guardado que no llego a la base se nota en el siguiente turno en vez
    de quedar tapado por una copia en memoria que dice lo contrario."""
    _configs.pop(tenant, None)


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
            }
            for h in herramientas
        ],
    }


def atender_turno(config, tenant: str, rol: str, id_sesion: str,
                  mensaje: str, canal: str) -> dict:
    """
    Un turno completo de conversacion: pausa por escalamiento, modelo,
    persistencia y evaluacion de escalamiento.

    Se extrajo de /chat sin cambiarle el comportamiento para que el webhook de
    WhatsApp (mas abajo) haga lo MISMO en vez de una copia parecida. Un canal
    con su propia version de esta logica se desincroniza: es exactamente como
    aparecio el bot que seguia contestando despues de escalar.

    Devuelve {'respuesta', 'verificado', 'pausada'}. Levanta motor.ErrorMotor
    si el rol o el mensaje no son atendibles -- quien llama decide si eso es un
    400 (HTTP) o una linea de registro (webhook, donde no hay a quien
    devolverle un error).
    """
    clave = (tenant, id_sesion)
    if clave not in _sesiones:
        _sesiones[clave] = {"sesion": Sesion(identificador_canal=id_sesion),
                            "historial": [], "escalada": False, "caso_id": None}
    estado = _sesiones[clave]

    # --- si ya se escalo, el bot NO contesta ---------------------------------
    # Va antes de motor.responder() a proposito. Marcar la conversacion como
    # escalada y despues dejar que el modelo siga respondiendo deja al cliente
    # hablando con un bot justo despues de que se le dijo que lo iba a atender
    # una persona. Se verifica contra el CRM en vez de confiar en la marca:
    # cuando el humano cierra el caso, el asistente retoma solo.
    if estado["escalada"]:
        if escalamiento.caso_sigue_abierto(config, estado["caso_id"]):
            respuesta = (config.escalamiento.mensaje or "").strip() or \
                "Tu caso ya esta con un companero del equipo."
            estado["historial"].append({"role": "user", "content": mensaje})
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

    respuesta, registro_herramientas = motor.responder(
        config, rol, mensaje, estado["historial"], estado["sesion"])

    conversation_id = None
    mensaje_id = None
    mensaje_usuario_id = None
    try:
        # El id del turno del CLIENTE se conserva: es a esa burbuja a la que
        # hay que colgarle la foto que mando, para que aparezca en el hilo
        # donde la mando y no en una lista aparte al final.
        _, mensaje_usuario_id = persistencia.registrar_mensaje(
            tenant, canal, id_sesion, rol, "user", mensaje)
        conversation_id, mensaje_id = persistencia.registrar_mensaje(
            tenant, canal, id_sesion, rol, "assistant", respuesta)
        for llamada in registro_herramientas:
            persistencia.registrar_llamada_herramienta(tenant, conversation_id, rol, llamada)
        # Recien aca existe conversation_id (ver el docstring de
        # motor.responder): antes de esto no habia donde persistir a quien
        # verifico _ejecutar_confirmacion. Se repite cada turno una vez
        # verificado -- es un UPDATE idempotente, mas simple que rastrear si
        # ya se guardo antes.
        if estado["sesion"] is not None and estado["sesion"].verificado and estado["sesion"].id_cliente:
            try:
                persistencia.identificar_cliente(
                    tenant, conversation_id,
                    estado["sesion"].id_cliente, estado["sesion"].nombre)
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
    if (conversation_id and rol_cfg and rol_cfg.orientado_a == "cliente_final"
            and not estado["escalada"]):
        try:
            evaluacion = escalamiento.evaluar(config, rol, estado["historial"])
        except Exception as e:
            print(f"[escalamiento] fallo al evaluar: {type(e).__name__}: {e}")
            evaluacion = None
        if evaluacion and evaluacion.get("escalar"):
            escalamiento.escalar(
                config, tenant, id_sesion, conversation_id, estado["historial"],
                evaluacion.get("motivo", ""), evaluacion.get("etiqueta", ""),
                resumen=evaluacion.get("resumen", ""),
                necesita_humano=evaluacion.get("necesita_humano", True))
            estado["escalada"] = True
            # El caso queda guardado para poder consultarlo despues: es lo que
            # permite que la pausa de arriba sepa cuando el humano lo cerro y
            # el asistente pueda retomar solo.
            try:
                estado["caso_id"] = persistencia.caso_de_conversacion(tenant, conversation_id)
            except Exception as e:
                print(f"[escalamiento] no se pudo leer el caso de la conversacion: {e}")
            respuesta = f"{respuesta}\n\n{config.escalamiento.mensaje}".strip()
        elif evaluacion and evaluacion.get("resuelta"):
            # No escalada Y el cliente confirmo que ya quedo resuelto: cierra
            # la conversacion en la bandeja (ver cerrar_conversacion en
            # persistencia). El propio saludo de despedida del modelo ya
            # cumple el rol de "mensaje de cierre" -- no hace falta agregar
            # otro, sonaria repetido.
            try:
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
                  agentes tiene asignados (supabase/15_agentes_por_colaborador)
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
            return jsonify({"error": "Todavia no tenes ningun agente asignado. "
                                     "Pedile a un administrador que te asigne "
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
        salida = atender_turno(config, tenant, rol, id_sesion, mensaje, canal)
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
    })


# -----------------------------------------------------------------------------
#  QUE AGENTES PUEDE USAR CADA COLABORADOR
# -----------------------------------------------------------------------------
#  Solo agentes INTERNOS: el de cliente final no se le asigna a un empleado.
#  Ese atiende a un desconocido y verifica identidad; los internos dan por
#  hecho que quien escribe ya esta autorizado y pueden consultar a CUALQUIER
#  cliente. Mezclarlos seria abrirle a una persona datos de terceros por la
#  puerta de al lado -- por eso se filtra aca y se vuelve a validar al guardar.

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

    return jsonify({"asignaciones": asignaciones,
                    "agentes": _agentes_internos(config)})


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

    return jsonify({"profile_id": profile_id, "roles": guardados})


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
    if not tenant or not contenido:
        return jsonify({"error": "Faltan campos: tenant, mensaje"}), 400

    try:
        destino = persistencia.agregar_mensaje_humano(tenant, id_conversacion, contenido)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"[conversaciones] fallo al guardar respuesta humana: {type(e).__name__}: {e}")
        return jsonify({"error": "No se pudo guardar la respuesta."}), 500

    if destino is None:
        return jsonify({"error": f"La conversacion '{id_conversacion}' no existe."}), 404

    salida = {"ok": True, "entregado": False}

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
                    forzar=forzar)
    except ValueError as e:
        return jsonify({"error": f"El documento declara {e}"}), 400
    except Exception as e:
        print(f"[corpus] fallo la ingesta de '{nombre}': {type(e).__name__}: {e}")
        return jsonify({"error": f"No se pudo procesar el documento: {e}"}), 500

    return jsonify(resultado), 201


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
                "Contame en palabras qué necesitás y te ayudo.")
            return

        salida = atender_turno(config, tenant, rol, de, texto, "whatsapp")

        # El adjunto se guarda DESPUES del turno, con la conversacion ya
        # creada: es lo que le da el conversation_id al que colgarlo. Va
        # aparte del turno y en su propio try porque una foto que no se pudo
        # bajar no puede dejar al cliente sin respuesta.
        _guardar_adjunto(config, tenant, entrante, salida.get("conversacion_id"),
                         salida.get("mensaje_usuario_id"))

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
        # dos veces. Ver supabase/08_webhook_eventos.sql.
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


if __name__ == "__main__":
    puerto = int(os.environ.get("PUERTO_API", "5000"))
    app.run(host="0.0.0.0", port=puerto)
