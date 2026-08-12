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

from flask import Flask, jsonify, request

from nucleo.config import editor, fuente
from nucleo.ingesta import corpus as ingesta
from nucleo.ingesta.docx import procesar
from nucleo.modelo import motor
from nucleo.persistencia import db as persistencia
from nucleo.recuperacion.busqueda import recuperar
from nucleo.seguimiento import escalamiento
from nucleo.seguimiento import supervisor
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
        "herramientas": [
            {
                "nombre": h.nombre, "descripcion": h.descripcion.strip(), "tipo": h.tipo,
                "campos_permitidos": rol.campos_permitidos.get(h.nombre, []),
            }
            for h in herramientas
        ],
    }


@app.post("/chat")
def chat():
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    rol = cuerpo.get("rol")
    id_sesion = cuerpo.get("identificador_sesion")
    mensaje = cuerpo.get("mensaje")
    canal = cuerpo.get("canal", "api")

    faltantes = [nombre for nombre, valor in
                {"tenant": tenant, "rol": rol, "identificador_sesion": id_sesion,
                 "mensaje": mensaje}.items() if not valor]
    if faltantes:
        return jsonify({"error": f"Faltan campos: {', '.join(faltantes)}"}), 400

    try:
        config = _config_de(tenant)
    except FileNotFoundError:
        return jsonify({"error": f"El tenant '{tenant}' no existe."}), 404

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
            return jsonify({"respuesta": respuesta,
                            "verificado": estado["sesion"].verificado,
                            "pausada": True})
        # El caso se cerro: el asistente vuelve a atender desde este turno.
        estado["escalada"] = False
        estado["caso_id"] = None

    try:
        respuesta, registro_herramientas = motor.responder(
            config, rol, mensaje, estado["historial"], estado["sesion"])
    except motor.ErrorMotor as e:
        return jsonify({"error": str(e)}), 400

    conversation_id = None
    mensaje_id = None
    try:
        persistencia.registrar_mensaje(tenant, canal, id_sesion, rol, "user", mensaje)
        conversation_id, mensaje_id = persistencia.registrar_mensaje(
            tenant, canal, id_sesion, rol, "assistant", respuesta)
        for llamada in registro_herramientas:
            persistencia.registrar_llamada_herramienta(tenant, conversation_id, rol, llamada)
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
                resumen=evaluacion.get("resumen", ""))
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

    return jsonify({"respuesta": respuesta, "verificado": estado["sesion"].verificado,
                    "cerrada": cerrada, "conversacion_id": conversation_id,
                    "mensaje_id": mensaje_id})


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
    """
    cuerpo = request.get_json(force=True, silent=True) or {}
    tenant = cuerpo.get("tenant")
    contenido = cuerpo.get("mensaje")
    if not tenant or not contenido:
        return jsonify({"error": "Faltan campos: tenant, mensaje"}), 400

    try:
        existe = persistencia.agregar_mensaje_humano(tenant, id_conversacion, contenido)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        print(f"[conversaciones] fallo al guardar respuesta humana: {type(e).__name__}: {e}")
        return jsonify({"error": "No se pudo guardar la respuesta."}), 500

    if not existe:
        return jsonify({"error": f"La conversacion '{id_conversacion}' no existe."}), 404

    return jsonify({"ok": True}), 201


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


@app.get("/salud")
def salud():
    return jsonify({"estado": "ok"})


if __name__ == "__main__":
    puerto = int(os.environ.get("PUERTO_API", "5000"))
    app.run(host="0.0.0.0", port=puerto)
