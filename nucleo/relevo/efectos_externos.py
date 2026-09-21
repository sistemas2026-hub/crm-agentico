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

  crear_ticket  implementado desde Q2.1, y con una regla propia: A LO SUMO UN
                POST POR INTENCION. WispHub no acepta clave de idempotencia y
                no deja buscar por nada util (Q2), pero SI se puede embeber una
                referencia propia en 'descripcion' --sobrevive exacta, viene en
                el listado-- y recuperarla barriendo una ventana. Asi que la
                politica es asimetrica: adoptar si, recrear nunca.

  cerrar_caso   implementado (B6). LEE PRIMERO y solo escribe si sigue
                abierto. Medido contra el CRM real
                (cases/tests/test_cierre_idempotente.py): un PATCH ciego sobre
                un caso ya cerrado responde 200 y REESCRIBE 'closed_on' con la
                fecha del reintento, asi que el caso pasa a decir que se cerro
                un dia en el que no se cerro. No falla nada; solo se corre la
                fecha, y con ella toda metrica de tiempo de resolucion.

  cerrar_ticket implementado, por PUT y nunca por '/respuesta/'. Esa via
                publica un comentario en cada intento; el PUT con solo
                'estado' no publica nada y no vacia ningun otro campo
                (verificado sobre un ticket real, 21/09/2026). Lee primero:
                un PUT repetido sobre uno ya cerrado le mueve 'fecha_fin'.
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


#: Lo que el CRM considera terminado. Uno solo de estos ya significa que el
#: caso no esta en la cola de nadie: no hace falta --ni conviene-- volver a
#: escribirlo. Es la misma lista que usa la lectura de escalamiento.py; vive
#: alla porque alla nacio, y se importa para no tener dos verdades.
def _estados_cerrados():
    from nucleo.seguimiento.escalamiento import ESTADOS_CERRADOS
    return ESTADOS_CERRADOS


def _estado_de(respuesta) -> str | None:
    """El 'status' del caso, venga envuelto o no. None si no se entiende."""
    if not isinstance(respuesta, dict):
        return None
    caso = respuesta.get("cases_obj", respuesta)
    if not isinstance(caso, dict):
        return None
    estado = caso.get("status")
    return str(estado) if estado else None


def cerrar_caso(config, tenant: str, datos: dict, referencia: str | None,
                *, leer_caso, cerrar) -> ResultadoEfecto:
    """
    Cierra el caso del CRM, o adopta el cierre que ya estaba.

    LEE PRIMERO, Y NO ES UNA PRECAUCION ABSTRACTA. Medido contra el CRM real
    (django-crm/backend/cases/tests/test_cierre_idempotente.py): un PATCH sobre
    un caso YA cerrado responde 200 y reescribe 'closed_on' con la fecha que
    lleve el pedido. Un reintento tres dias despues no falla: deja el caso
    diciendo que se cerro un dia en el que no se cerro, y toda metrica de
    tiempo de resolucion construida sobre esa columna se corre con el.

    Asi que el orden es el mismo que en crear_caso y por el mismo motivo: si
    ya esta cerrado, se ADOPTA y no se escribe nada.

    UN RECHAZO PUEDE SER LEGITIMO. El CRM puede exigir una aprobacion antes de
    cerrar (ApprovalRule 'pre_close') y responder 400. Eso no es una falla que
    se resuelva insistiendo: necesita que una persona apruebe. Cae en
    'permanente' por la clase de error, que es donde tiene que quedar --
    visible, sin reintentos, esperando a alguien.

    CERRADO NO ES PARA SIEMPRE. Un caso cerrado se puede reabrir (probado). Por
    eso esto devuelve 'exito' sobre lo que HIZO, no sobre lo que es cierto
    ahora: la cola registra actos, no estados del mundo.
    """
    caso_id = (datos or {}).get("caso_id") or referencia
    if not caso_id:
        return ResultadoEfecto("permanente", codigo="sin_caso")

    # 1. ¿Ya esta cerrado? Si no se puede leer, NO se escribe a ciegas: el
    #    precio de escribir sin saber es mover la fecha de cierre de un caso
    #    que ya estaba bien.
    try:
        estado = _estado_de(leer_caso(str(caso_id)))
    except Exception as e:
        clase, codigo = _clase_de_error(e)
        return ResultadoEfecto("transitorio" if clase != "permanente" else clase,
                               codigo=codigo)
    if estado is None:
        # Respondio algo que no se entiende. Tampoco se escribe.
        return ResultadoEfecto("transitorio", codigo="estado_ilegible")
    if estado in _estados_cerrados():
        registrar("reconciliador", "el caso ya estaba cerrado: no se reescribe",
                  tenant=tenant)
        return ResultadoEfecto("exito", referencia=str(caso_id))

    # 2. Sigue abierto: cerrarlo.
    try:
        cerrar(str(caso_id))
    except Exception as e:
        clase, codigo = _clase_de_error(e)
        return ResultadoEfecto(clase, codigo=codigo)

    # 3. RELEER SIEMPRE. El codigo de estado dice que el pedido se acepto, no
    #    que el caso quedo cerrado -- misma disciplina que asignar_caso (D28).
    try:
        estado = _estado_de(leer_caso(str(caso_id)))
    except Exception:
        estado = None
    if estado is None:
        return ResultadoEfecto("incierto", codigo="sin_confirmacion")
    if estado not in _estados_cerrados():
        # Acepto y no cerro. Insistir daria lo mismo.
        return ResultadoEfecto("permanente", codigo="no_quedo_cerrado")
    return ResultadoEfecto("exito", referencia=str(caso_id))


#: El prefijo de la referencia que Dexter embebe en la descripcion del ticket.
#: Medido el 21/09/2026 contra la API real: 'descripcion' sobrevive EXACTA
#: --184 caracteres enviados, 184 devueltos, cadena identica-- viene completa
#: en el listado y no la envuelve en HTML. Es lo que hace posible recuperar un
#: ticket cuyo id se perdio. Ver SPEC/auditorias/B4-Q2-WISPHUB.md.
PREFIJO_REFERENCIA = "DEXTER_REF:"

#: La ETIQUETA que devuelve el GET, no el codigo que toma el PUT. WispHub
#: escribe por numero (4) y lee por texto ('Cerrado') -- verificado sobre un
#: ticket real. Misma deuda que en promesas.py: es vocabulario del proveedor
#: viviendo en nucleo/, y con otro sistema de tickets hay que moverlo a config.
ESTADO_TICKET_CERRADO = "Cerrado"

#: Cuantos dias hacia atras se busca la referencia. La ventana tiene que
#: incluir el instante del intento original; el reconciliador reintenta
#: durante horas, asi que siete dias sobra. El tope duro de la API es 2 meses
#: (medido), y el volumen real son ~17 tickets por dia: recorrerla es barato.
VENTANA_BUSQUEDA_DIAS = 7


def referencia_de(clave_idempotencia: str) -> str:
    """
    La referencia estable de una intencion.

    Sale de 'sincronizaciones_externas.clave_idempotencia', que §3.6 deriva de
    (conversacion, tipo, evento que la origino) y es unica por organizacion.
    NO del conversation_id: una misma conversacion puede generar mas de un
    ticket legitimo --dos fallas, dos visitas-- y esa clave los confundiria,
    haciendo que el segundo adopte el primero y nunca se cree.

    Determinista: la misma intencion da siempre la misma referencia, que es lo
    que permite que un reintento la reuse en vez de inventar otra.
    """
    import hashlib

    crudo = str(clave_idempotencia or "").encode()
    return PREFIJO_REFERENCIA + hashlib.sha256(crudo).hexdigest()[:32]


def crear_ticket(config, tenant: str, datos: dict, referencia: str | None,
                 *, crear, buscar_por_referencia) -> ResultadoEfecto:
    """
    Crea el ticket, o adopta el que ya exista con la misma referencia.

    A LO SUMO UN POST POR INTENCION, y de ahi sale todo lo demas. WispHub no
    acepta clave de idempotencia y no deja buscar un ticket por nada util
    (gate Q2), asi que dos POST con la misma intencion son dos tickets y dos
    visitas tecnicas al mismo cliente. Lo que SI se puede es embeber una
    referencia propia en 'descripcion' y buscarla despues (Q2.1).

    EL ORDEN, y es lo unico delicado:

        buscar -> si aparece, adoptar -> si no, crear UNA vez -> si el
        resultado queda incierto, buscar otra vez

    Se busca ANTES incluso en el primer intento. Cuesta un GET de mas y cubre
    el caso que no se puede distinguir desde aca: que un intento anterior haya
    creado el ticket y muerto antes de anotarlo.

    Y si la BUSQUEDA falla, no se crea a ciegas. Es la misma decision que
    crear_caso: no poder preguntar no autoriza a escribir.
    """
    ref = (datos or {}).get("referencia")
    if not ref or not str(ref).startswith(PREFIJO_REFERENCIA):
        # Sin referencia no hay idempotencia posible: ni se busca ni se crea.
        # Permanente, porque reintentarlo daria lo mismo.
        return ResultadoEfecto("permanente", codigo="sin_referencia")

    def buscar():
        """(encontrados, resultado_de_error). Solo uno de los dos."""
        try:
            return buscar_por_referencia(ref), None
        except Exception as e:
            clase, codigo = _clase_de_error(e)
            return None, ResultadoEfecto(
                "transitorio" if clase != "permanente" else clase, codigo=codigo)

    def resolver(encontrados, codigo_si_ninguno):
        """De lo encontrado al desenlace. >1 nunca se resuelve solo."""
        if len(encontrados) == 1:
            registrar("reconciliador", "ticket adoptado por referencia",
                      tenant=tenant)
            return ResultadoEfecto("exito", referencia=str(encontrados[0]))
        if len(encontrados) > 1:
            # Dos tickets con la misma referencia: ya hay un duplicado. Elegir
            # uno seria tapar el problema, y crear otro lo empeoraria.
            return ResultadoEfecto("incierto", codigo="varias_coincidencias")
        return ResultadoEfecto("incierto", codigo=codigo_si_ninguno)

    # 1. ¿ya existe?
    encontrados, fallo = buscar()
    if fallo is not None:
        return fallo
    if encontrados:
        return resolver(encontrados, "")

    # 2. No existe: crear. UNA vez.
    try:
        id_ticket = crear(ref, datos or {})
    except Exception as e:
        clase, codigo = _clase_de_error(e)
        if clase != "incierto":
            # Se sabe que no se hizo. Que lo resuelva la cola.
            return ResultadoEfecto(clase, codigo=codigo)
        # Incierto: el pedido PUDO haber llegado. NO se crea otro -- se busca.
        encontrados, fallo = buscar()
        if fallo is not None:
            return ResultadoEfecto("incierto", codigo=codigo)
        return resolver(encontrados, codigo or "incierto")

    if not id_ticket:
        # Acepto y no devolvio id. El ticket pudo quedar creado: NO se crea
        # otro, se busca.
        encontrados, fallo = buscar()
        if fallo is not None:
            return ResultadoEfecto("incierto", codigo="sin_id")
        return resolver(encontrados, "sin_id")
    return ResultadoEfecto("exito", referencia=str(id_ticket))


def cerrar_ticket(config, tenant: str, datos: dict, referencia: str | None,
                  *, leer_ticket, cerrar) -> ResultadoEfecto:
    """
    Cierra el ticket del ISP, o adopta el cierre que ya estaba.

    LEE PRIMERO, por dos razones medidas el 21/09/2026 sobre un ticket de
    prueba real:

      * un PUT repetido sobre un ticket ya cerrado mueve 'fecha_fin' --de
        14:42:10 a 14:42:12-- sin error ninguno. El ticket pasa a decir que se
        cerro en un momento en que no se cerro. Mismo daño que 'closed_on' en
        el CRM.
      * el estado se ESCRIBE por codigo (4) y se LEE por etiqueta ('Cerrado').
        Comparar el numero contra lo que devuelve el GET no funciona nunca.

    NUNCA por '/api/tickets/{id}/respuesta/'. Esa via exige un texto y lo
    PUBLICA en el ticket: cada reintento le deja al cliente otra copia del
    mensaje de cierre. El PUT con solo 'estado' no publica nada -- verificado,
    las respuestas del ticket quedaron en 0 antes y despues.
    """
    id_ticket = (datos or {}).get("ticket") or (datos or {}).get("id_ticket") or referencia
    if not id_ticket:
        return ResultadoEfecto("permanente", codigo="sin_ticket")

    def estado_de(t):
        return str((t or {}).get("estado") or "").strip() if isinstance(t, dict) else ""

    # 1. ¿ya esta cerrado? Si no se puede leer, NO se escribe.
    try:
        actual = estado_de(leer_ticket(str(id_ticket)))
    except Exception as e:
        clase, codigo = _clase_de_error(e)
        return ResultadoEfecto("transitorio" if clase != "permanente" else clase,
                               codigo=codigo)
    if not actual:
        return ResultadoEfecto("transitorio", codigo="estado_ilegible")
    if actual == ESTADO_TICKET_CERRADO:
        registrar("reconciliador", "el ticket ya estaba cerrado: no se reescribe",
                  tenant=tenant)
        return ResultadoEfecto("exito", referencia=str(id_ticket))

    # 2. Sigue abierto: cerrarlo.
    try:
        cerrar(str(id_ticket))
    except Exception as e:
        clase, codigo = _clase_de_error(e)
        return ResultadoEfecto(clase, codigo=codigo)

    # 3. RELEER SIEMPRE. El codigo de estado dice que el pedido se acepto, no
    #    que el ticket quedo cerrado.
    try:
        actual = estado_de(leer_ticket(str(id_ticket)))
    except Exception:
        actual = ""
    if not actual:
        return ResultadoEfecto("incierto", codigo="sin_confirmacion")
    if actual != ESTADO_TICKET_CERRADO:
        return ResultadoEfecto("permanente", codigo="no_quedo_cerrado")
    return ResultadoEfecto("exito", referencia=str(id_ticket))


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
             agregar_asignado=None, leer_asignados=None, leer_perfiles=None,
             leer_caso=None, cerrar_caso_crm=None,
             crear_ticket_isp=None, buscar_ticket_por_referencia=None,
             leer_ticket=None, cerrar_ticket_isp=None):
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
        if tipo == "cerrar_caso":
            if leer_caso is None or cerrar_caso_crm is None:
                # Sin LEER no se escribe: un PATCH a ciegas sobre un caso ya
                # cerrado le corre la fecha de cierre. Falta una capacidad del
                # tenant, no un dato del efecto.
                return ResultadoEfecto("permanente", codigo="sin_ejecutor:cerrar_caso")
            return cerrar_caso(config, tenant, datos, referencia,
                               leer_caso=leer_caso, cerrar=cerrar_caso_crm)
        if tipo == "crear_ticket":
            if crear_ticket_isp is None or buscar_ticket_por_referencia is None:
                # Sin BUSCAR no se crea. Poder escribir sin poder preguntar es
                # exactamente lo que produce dos visitas tecnicas al mismo
                # cliente, que es lo que el gate Q2 existe para impedir.
                return ResultadoEfecto("permanente", codigo="sin_ejecutor:crear_ticket")
            return crear_ticket(config, tenant, datos, referencia,
                                crear=crear_ticket_isp,
                                buscar_por_referencia=buscar_ticket_por_referencia)
        if tipo == "cerrar_ticket":
            if leer_ticket is None or cerrar_ticket_isp is None:
                # Sin LEER no se escribe: un PUT sobre un ticket ya cerrado le
                # corre la fecha de cierre (medido).
                return ResultadoEfecto("permanente", codigo="sin_ejecutor:cerrar_ticket")
            return cerrar_ticket(config, tenant, datos, referencia,
                                 leer_ticket=leer_ticket, cerrar=cerrar_ticket_isp)
        return ResultadoEfecto("permanente", codigo=f"sin_ejecutor:{tipo}")
    return _ejecutar
