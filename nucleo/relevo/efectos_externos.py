# -*- coding: utf-8 -*-
"""
================================================================================
 Los ejecutores reales de la cola de B4
================================================================================

El reconciliador (T20) decide QUE hacer con un desenlace; esto es lo que habla
con el sistema externo y produce ese desenlace. Estan separados a proposito:
la regla de si algo se reintenta no debe depender de con quien se habla, y asi
se puede probar sin red.

QUE HAY Y QUE NO
----------------
  crear_caso    implementado. Su idempotencia esta demostrada del lado de
                afuera: el nombre del caso lleva el conversation_id, es unico
                por organizacion, y un repetido responde 400 -- asi que ante un
                reintento se busca y se adopta el que ya existe.

  crear_ticket  NO implementado, y no por falta de tiempo. La API de WispHub no
                acepta clave de idempotencia, no deja buscar el ticket despues,
                reescribe el asunto y recorta el historico (gate Q2,
                SPEC/auditorias/B4-Q2-WISPHUB.md). Sin forma de preguntar "¿esto
                ya se hizo?", un reintento es una apuesta -- y perderla manda
                dos visitas tecnicas al mismo cliente.

                No se escribe ni detras de una bandera: una bandera es una
                invitacion a encenderla.

  cerrar_*      sin productor todavia. Ver el estado en DEXTER_ESTADO_ACTUAL.
"""

from __future__ import annotations

from nucleo.observabilidad.registro import registrar
from nucleo.relevo import asignados_crm
from nucleo.relevo.reconciliador import ResultadoEfecto

#: Lo que el CRM responde cuando el nombre ya existe. Es la senal de que el
#: caso se creo antes -- no un error del pedido.
HTTP_NOMBRE_REPETIDO = 400


def _clase_de_error(e: Exception) -> tuple[str, str | None]:
    """
    De una excepcion al vocabulario de la cola. Solo el codigo, nunca el cuerpo.

    Por defecto INCIERTO y no 'transitorio': si no se puede demostrar que el
    pedido no llego, la respuesta honesta es que no se sabe. Es la misma
    asimetria que el resto del sistema -- decir "no salio" sin evidencia es
    afirmar algo que puede ser falso, y aca eso significa duplicar un efecto.
    """
    estado = getattr(e, "http_status", None) or getattr(e, "codigo_http", None)
    if estado is None:
        return "incierto", "sin_respuesta"
    if estado == HTTP_NOMBRE_REPETIDO:
        return "permanente", str(estado)
    if 400 <= estado < 500 and estado not in (408, 429):
        # El pedido estaba mal. Repetirlo daria el mismo error.
        return "permanente", str(estado)
    return "transitorio", str(estado)


def crear_caso(config, tenant: str, datos: dict, referencia: str | None,
               *, crear, buscar_por_nombre) -> ResultadoEfecto:
    """
    Crea el caso en el CRM, o adopta el que ya existe.

    `crear` y `buscar_por_nombre` se inyectan: este modulo no conoce el cliente
    HTTP ni el catalogo del tenant, y asi la regla de adopcion se puede probar
    sin red.

    EL ORDEN IMPORTA y es lo unico delicado: se BUSCA PRIMERO. Un reintento
    llega aca justamente porque el intento anterior no se pudo confirmar, asi
    que empezar creando seria crear el segundo caso de la misma conversacion.
    """
    nombre = (datos or {}).get("nombre_caso")
    if not nombre:
        # Sin el nombre canonico no hay idempotencia posible: ni se busca ni se
        # crea. Permanente, porque reintentarlo daria lo mismo.
        return ResultadoEfecto("permanente", codigo="sin_nombre_de_caso")

    # 1. ¿Ya existe? El nombre lleva el conversation_id y es unico por
    #    organizacion, asi que esto no puede traer el caso de otra conversacion.
    try:
        existente = buscar_por_nombre(nombre)
    except Exception as e:
        clase, codigo = _clase_de_error(e)
        # No poder BUSCAR no es lo mismo que no poder crear: no se intenta
        # crear a ciegas. Se vuelve a intentar entero mas tarde.
        return ResultadoEfecto("transitorio" if clase != "permanente" else clase,
                               codigo=codigo)
    if existente:
        registrar("reconciliador", "el caso ya existia: se adopta en vez de crear otro",
                  tenant=tenant)
        return ResultadoEfecto("exito", referencia=str(existente))

    # 2. No existe: crear.
    try:
        caso_id = crear(nombre, datos or {})
    except Exception as e:
        clase, codigo = _clase_de_error(e)
        if codigo == str(HTTP_NOMBRE_REPETIDO):
            # Carrera: alguien lo creo entre la busqueda y esto. Que el nombre
            # sea unico convierte la colision en la respuesta correcta.
            try:
                otro = buscar_por_nombre(nombre)
            except Exception:
                otro = None
            if otro:
                return ResultadoEfecto("exito", referencia=str(otro))
            return ResultadoEfecto("incierto", codigo=codigo)
        return ResultadoEfecto(clase, codigo=codigo)

    if not caso_id:
        # El CRM acepto y no devolvio id. El caso pudo quedar creado: NO se
        # crea otro. El proximo ciclo lo busca por nombre y lo adopta.
        return ResultadoEfecto("incierto", codigo="sin_id")
    return ResultadoEfecto("exito", referencia=str(caso_id))


def asignar_caso(config, tenant: str, datos: dict, referencia: str | None,
                 *, agregar_asignado, leer_asignados,
                 leer_perfiles=None) -> ResultadoEfecto:
    """
    Pone al operador de Dexter en el conjunto de asignados del caso (D28).

    ES ADITIVO. No manda el conjunto entero: los demas asignados del CRM se
    quedan donde estan. Podrian ser un segundo tecnico que un supervisor sumo
    hoy, y el CRM no guarda quien creo cada relacion -- reemplazar el conjunto
    borraria ese trabajo sin dejar rastro.

    SE RELEE DESPUES DE ESCRIBIR, y esto no es prolijidad: el endpoint de
    asignacion masiva del CRM responde 200 y deja el caso SIN NADIE cuando el
    perfil no resuelve dentro de la organizacion. Un codigo de estado no prueba
    el efecto. Si la relectura no confirma que el perfil quedo, el resultado es
    INCIERTO -- nunca 'exito'.
    """
    caso_id = (datos or {}).get("caso_id")
    perfil_id = (datos or {}).get("perfil_id")
    usuario_id = (datos or {}).get("usuario_id")

    if not perfil_id and usuario_id:
        # La intencion viaja con el usuario DURABLE de Dexter, no con el perfil
        # del CRM: resolverlo exige preguntar, y eso no puede pasar dentro de
        # la transaccion que cambia la asignacion (X23). Se traduce aca, que ya
        # esta fuera.
        if leer_perfiles is None:
            return ResultadoEfecto("permanente", codigo="sin_catalogo_de_perfiles")
        try:
            perfiles = leer_perfiles()
        except Exception as e:
            clase, codigo = _clase_de_error(e)
            # No se pudo preguntar quien es. No se escribio nada, asi que esto
            # se reintenta entero: 'transitorio', no 'incierto'.
            return ResultadoEfecto("transitorio" if clase != "permanente" else clase,
                                   codigo=codigo)
        perfil = asignados_crm.perfil_de_usuario(perfiles, str(usuario_id))
        if perfil is None:
            # El operador no tiene perfil en esta organizacion del CRM. No es
            # una falla a reintentar --reintentar no lo va a crear-- y no se
            # fuerza contra nadie: queda visible.
            return ResultadoEfecto("permanente", codigo="operador_sin_perfil_en_crm")
        perfil_id = perfil.get("id")

    if not caso_id or not perfil_id:
        return ResultadoEfecto("permanente", codigo="sin_caso_o_perfil")

    try:
        agregar_asignado(caso_id, perfil_id)
    except Exception as e:
        clase, codigo = _clase_de_error(e)
        if clase == "permanente":
            return ResultadoEfecto("permanente", codigo=codigo)
        # Transitorio o incierto: el pedido pudo haber llegado. NO se decide
        # todavia -- se comprueba abajo, que es lo unico que puede resolverlo.
        # Reintentar tampoco duplicaria nada (agregar es idempotente), pero
        # confirmar es mejor que suponer.
        try:
            if perfil_id in _ids_asignados(leer_asignados(caso_id)):
                return ResultadoEfecto("exito", referencia=str(perfil_id))
        except Exception:
            pass
        return ResultadoEfecto(clase, codigo=codigo)

    # Escribio sin error. Igual se comprueba: el 200 no es la evidencia.
    try:
        asignados = _ids_asignados(leer_asignados(caso_id))
    except Exception as e:
        _, codigo = _clase_de_error(e)
        # El efecto muy probablemente ocurrio, pero no se puede demostrar.
        # 'incierto' y no 'exito': afirmar que el caso quedo asignado sin
        # haberlo visto es exactamente lo que X22 prohibe.
        registrar("reconciliador", "se asigno el caso y no se pudo confirmar",
                  tenant=tenant)
        return ResultadoEfecto("incierto", codigo=f"sin_confirmacion:{codigo}")

    if str(perfil_id) in asignados:
        return ResultadoEfecto("exito", referencia=str(perfil_id))
    # Se escribio, no hubo error, y el perfil NO esta. Es el caso del 200 que
    # no hizo nada: no se reintenta a ciegas, queda para una persona.
    return ResultadoEfecto("incierto", codigo="asignado_no_confirmado")


def _ids_asignados(respuesta) -> set[str]:
    """Los Profile.id que el CRM dice que tiene el caso ahora."""
    if isinstance(respuesta, dict):
        respuesta = respuesta.get("assigned_to") or []
    return {str(p.get("id")) for p in respuesta or [] if isinstance(p, dict)}


def ejecutor(config, tenant: str, *, crear, buscar_por_nombre,
             agregar_asignado=None, leer_asignados=None, leer_perfiles=None):
    """
    El `ejecutar` que espera el reconciliador, ya atado a este tenant.

    Un tipo sin ejecutor devuelve 'permanente' y NO 'incierto': que no este
    implementado no es una duda sobre si el efecto ocurrio -- no ocurrio, y no
    va a ocurrir solo. Queda visible como fallida_definitiva, que es lo que
    corresponde a algo que necesita que alguien escriba codigo.
    """
    def _ejecutar(tipo: str, datos: dict, referencia: str | None) -> ResultadoEfecto:
        if tipo == "crear_caso":
            return crear_caso(config, tenant, datos, referencia,
                              crear=crear, buscar_por_nombre=buscar_por_nombre)
        if tipo == "asignar_caso":
            if agregar_asignado is None or leer_asignados is None:
                # Sin las dos, no hay forma de escribir Y comprobar. Falta una
                # capacidad del tenant, no un dato del efecto: permanente y
                # visible, nunca 'incierto' -- no hay ninguna duda sobre si
                # ocurrio.
                return ResultadoEfecto("permanente", codigo="sin_ejecutor:asignar_caso")
            return asignar_caso(config, tenant, datos, referencia,
                                agregar_asignado=agregar_asignado,
                                leer_asignados=leer_asignados,
                                leer_perfiles=leer_perfiles)
        return ResultadoEfecto("permanente", codigo=f"sin_ejecutor:{tipo}")
    return _ejecutar
