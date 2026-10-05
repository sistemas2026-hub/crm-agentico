# -*- coding: utf-8 -*-
"""
================================================================================
 LAS HERRAMIENTAS DEL SUPERVISOR  --  solo lectura, y el tenant no es negociable
================================================================================

QUE SON
-------
Las consultas que el Supervisor puede hacerle a sus propios datos durante una
conversacion. Devuelven datos ESTRUCTURADOS; interpretarlos es del modelo.

LAS TRES REGLAS, Y LAS TRES ESTAN EN CODIGO
-------------------------------------------
  1. TODAS son de LECTURA. Ninguna escribe, ninguna cambia un estado, ninguna
     llama a un sistema externo. No es una convencion: el despachador rechaza un
     nombre que no este en este mapa, asi que no hay forma de alcanzar otra cosa.

  2. EL TENANT LO PONE EL DESPACHADOR, NO EL MODELO. Ninguna herramienta acepta
     'org' como argumento. Si lo aceptara, bastaria con que el modelo lo
     inventara --o con que alguien se lo dictara en un mensaje-- para leer los
     datos de otra empresa. El modelo no puede nombrar una organizacion porque no
     hay donde ponerla.

  3. NINGUNA RECIBE SQL, ni un filtro libre, ni un nombre de campo. Los
     argumentos son identificadores y numeros acotados. Un parametro de texto
     libre que llegue a una consulta es la puerta por la que se cuela todo lo
     demas.

QUE DEVUELVEN, Y QUE NO
-----------------------
Conteos, estados, fechas, codigos y topologia. NO devuelven nombres de clientes,
telefonos, cedulas, direcciones ni coordenadas: lo que sale de aqui entra al
prompt de un modelo de un tercero, y la autorizacion de tratamiento que lo
permite nombra al proveedor del modelo -- no autoriza mandarle de mas.

El nombre del caso tampoco viaja: es texto libre de un operador y ya se midio que
136 de 300 descripciones traian un documento embebido.
================================================================================
"""

from __future__ import annotations

from django.utils import timezone

from operaciones import autonomia as gob_autonomia
#  P6: se importan LAS DOS FUNCIONES DE LECTURA, no el modulo. 'coordinacion'
#  tambien tiene 'solicitar_actividad', que ESCRIBE; importar el modulo entero
#  dejaria esa escritura alcanzable por un nombre ligado dentro de este archivo,
#  y la guarda de P5 ('test_20_NINGUNA_herramienta_escribe') dejaria de medir lo
#  que dice medir. Con el import puntual, aqui no hay forma de llegar a ella.
from operaciones.coordinacion import (panorama_m03,
                                      pendientes_de_la_situacion)
from operaciones.fuentes_modelos import EstadoLectura, Fuente, FuenteEstado
from operaciones.gobierno_modelos import DecisionSupervisor
from operaciones.models import PropuestaSupervisor
from operaciones.situaciones_modelos import (SituacionOperativa, TipoAfectado,
                                             TipoEvento)

S = SituacionOperativa
P = PropuestaSupervisor

#  Cuanto puede pedir una herramienta de una sola vez. Un tope y no un parametro
#  libre: sin el, "listame las situaciones" con un limite de 10.000 meteria la
#  base entera en el prompt y la pagaria la empresa.
TOPE = 25


class HerramientaDesconocida(Exception):
    """El modelo pidio una herramienta que no existe. No se adivina cual quiso."""


# =============================================================================
#  SITUACIONES
# =============================================================================

def listar_situaciones(org, *, estado="", limite=TOPE) -> dict:
    """Las situaciones, lo mas reciente primero. Por defecto solo las vivas."""
    qs = S.objects.filter(org=org)
    if estado:
        if estado == "vivas":
            qs = qs.filter(estado__in=S.VIVAS)
        else:
            qs = qs.filter(estado=str(estado))
    else:
        qs = qs.filter(estado__in=S.VIVAS)

    filas = []
    for s in qs.order_by("-detectada_en")[:_acotar(limite)]:
        filas.append({
            "codigo": s.codigo, "titulo": s.titulo, "estado": s.estado,
            "riesgo": s.riesgo, "tipo": s.tipo,
            "afectados": s.afectados_contados,
            "detectada_en": s.detectada_en.isoformat(),
            "senal_vista_en": (s.senal_vista_en.isoformat()
                               if s.senal_vista_en else None),
            "proxima_revision_en": (s.proxima_revision_en.isoformat()
                                    if s.proxima_revision_en else None),
        })
    return {"situaciones": filas, "cuantas": len(filas),
            "hay_mas": qs.count() > len(filas)}


def detalle_situacion(org, *, codigo) -> dict:
    """
    Una situacion con su hipotesis Y SU CONFIANZA. Las dos juntas, siempre.

    Mandar la hipotesis sin la confianza al prompt seria entregarle al modelo una
    sospecha con forma de hecho -- exactamente lo que la base impide a nivel de
    fila y lo que aqui se respeta a nivel de contexto.
    """
    s = _situacion(org, codigo)
    if s is None:
        return {"error": "no_encontrada", "codigo": str(codigo)}
    return {
        "codigo": s.codigo, "titulo": s.titulo, "descripcion": s.descripcion,
        "estado": s.estado, "riesgo": s.riesgo, "tipo": s.tipo,
        "afectados": s.afectados_contados,
        "detectada_en": s.detectada_en.isoformat(),
        "actualizada_en": s.actualizada_en.isoformat(),
        "senal_vista_en": (s.senal_vista_en.isoformat()
                           if s.senal_vista_en else None),
        "proxima_revision_en": (s.proxima_revision_en.isoformat()
                                if s.proxima_revision_en else None),
        "hipotesis": s.hipotesis,
        "confianza": s.confianza,
        "recomendacion": s.recomendacion,
        "fuente_origen": s.fuente_origen,
        #  La evidencia son HECHOS con su procedencia. Van, porque es lo que
        #  sostiene cualquier afirmacion del Supervisor.
        "evidencia": list(s.evidencia or [])[:10],
        "verificacion": s.verificacion,
        "verificada_en": (s.verificada_en.isoformat()
                          if s.verificada_en else None),
        #  Lo que FALTA. Es tan parte del detalle como lo que hay: sin esto el
        #  modelo no tiene con que contestar "¿que informacion te falta?".
        "falta": _que_falta(s),
    }


def _que_falta(s) -> list[str]:
    """
    Que no se sabe de esta situacion. Derivado, nunca inventado.

    Existe para que "no tengo suficiente informacion" sea una respuesta con
    contenido en vez de una excusa: dice QUE falta y por que importa.
    """
    faltan = []
    if not s.hipotesis:
        faltan.append("no hay una hipotesis: la concentracion observada no "
                      "alcanza para proponer una causa")
    if s.senal_vista_en is None:
        faltan.append("no hay ninguna lectura concluyente registrada")
    sin_identificar = s.afectados.filter(
        tipo=TipoAfectado.DATOS_INSUFICIENTES, recuperado_en__isnull=True)
    for af in sin_identificar:
        porque = (af.datos or {}).get("porque", "")
        faltan.append(f"{(af.datos or {}).get('cuantas', '?')} equipos "
                      f"afectados sin identificar" +
                      (f": {porque}" if porque else ""))
    if not s.afectados.filter(tipo=TipoAfectado.CASO).exists():
        faltan.append("ningun caso de cliente asociado todavia: nadie lo "
                      "reporto, o no hay con que ligarlo")
    if not s.verificacion:
        faltan.append("no hay verificacion registrada, asi que no se puede "
                      "cerrar")
    return faltan


def timeline_situacion(org, *, codigo, limite=TOPE) -> dict:
    """El historial, en orden. Es append-only: lo que esta, paso."""
    s = _situacion(org, codigo)
    if s is None:
        return {"error": "no_encontrada", "codigo": str(codigo)}
    eventos = []
    for e in s.eventos.order_by("-ocurrido_en", "-registrado_en")[:_acotar(limite)]:
        eventos.append({"tipo": e.tipo, "resumen": e.resumen,
                        "ocurrido_en": e.ocurrido_en.isoformat(),
                        "datos": e.datos or {},
                        #  Nulo = lo hizo el Supervisor. Es la marca de la IA, el
                        #  mismo criterio que 'operaciones/auditoria.py'.
                        "por_una_persona": e.actor_id is not None})
    return {"codigo": s.codigo, "eventos": list(reversed(eventos)),
            "cuantos": len(eventos)}


def afectados_situacion(org, *, codigo) -> dict:
    """Que esta afectado, por tipo. Incluye lo que se recupero."""
    s = _situacion(org, codigo)
    if s is None:
        return {"error": "no_encontrada", "codigo": str(codigo)}
    por_tipo: dict = {}
    for af in s.afectados.all():
        fila = por_tipo.setdefault(af.tipo, {"vigentes": 0, "recuperados": 0,
                                             "identificadores": []})
        if af.recuperado_en is None:
            fila["vigentes"] += 1
            #  Los identificadores de TOPOLOGIA viajan (un PON, una OLT); los de
            #  cliente NO. Un id de caso no dice quien es nadie, pero el nombre
            #  si, y por eso aqui solo hay ids.
            if af.tipo in (TipoAfectado.PON, TipoAfectado.OLT,
                           TipoAfectado.ZONA) and len(fila["identificadores"]) < 10:
                fila["identificadores"].append(af.identificador)
        else:
            fila["recuperados"] += 1
    return {"codigo": s.codigo, "por_tipo": por_tipo}


def casos_de_situacion(org, *, codigo) -> dict:
    """
    Los casos asociados, con su SLA y su tecnico. SIN nombres de cliente.

    Un ticket NO es el origen de la situacion: puede haber cero, y eso es valido.
    El conteo en cero se devuelve explicito para que el modelo no lo lea como
    "no averiguamos".
    """
    from cases.models import Case

    s = _situacion(org, codigo)
    if s is None:
        return {"error": "no_encontrada", "codigo": str(codigo)}

    ids = list(s.afectados.filter(tipo=TipoAfectado.CASO,
                                  recuperado_en__isnull=True)
               .values_list("identificador", flat=True)[:TOPE])
    if not ids:
        return {"codigo": s.codigo, "casos": [], "cuantos": 0,
                "nota": "ningun caso asociado: la situacion se detecto sin que "
                        "nadie la reportara, o no hay dato que ligue un caso"}

    filas = []
    for c in Case.objects.filter(org=org, id__in=ids):
        filas.append({
            #  El id, no el nombre: 'name' es texto libre de un operador.
            "id": str(c.id), "estado": c.status, "prioridad": c.priority,
            "creado_en": c.created_at.isoformat(),
            "dias_abierto": (timezone.now() - c.created_at).days,
            "estado_en_el_proveedor": getattr(c, "external_status", "") or "",
            #  Cuantas personas tiene asignadas, no quienes: un nombre es un dato
            #  de una persona y no hace falta para razonar sobre el caso.
            "tiene_asignado": c.assigned_to.exists(),
            "sla_resolucion_incumplido": bool(
                getattr(c, "is_sla_resolution_breached", False)),
        })
    return {"codigo": s.codigo, "casos": filas, "cuantos": len(filas)}


def relaciones_situacion(org, *, codigo) -> dict:
    """Con que otras situaciones se relaciona, y por que."""
    s = _situacion(org, codigo)
    if s is None:
        return {"error": "no_encontrada", "codigo": str(codigo)}
    salida = []
    for r in s.relaciones_salientes.select_related("destino")[:TOPE]:
        salida.append({"tipo": r.tipo, "con": r.destino.codigo,
                       "motivo": r.motivo,
                       "la_puso_una_persona": r.actor_id is not None})
    for r in s.relaciones_entrantes.select_related("origen")[:TOPE]:
        salida.append({"tipo": r.tipo, "con": r.origen.codigo,
                       "motivo": r.motivo,
                       "la_puso_una_persona": r.actor_id is not None})
    return {"codigo": s.codigo, "relaciones": salida}


# =============================================================================
#  FUENTES
# =============================================================================

def estado_fuentes(org) -> dict:
    """
    Como esta cada fuente, con su frescura y si se puede concluir.

    ES LA HERRAMIENTA QUE IMPIDE LA PEOR RESPUESTA POSIBLE. Sin esto, el
    Supervisor podria decir "no hay afectaciones" cuando la verdad es que SmartOLT
    no contesta. 'concluyente' viaja para cada fuente justamente para que esa
    frase no se pueda construir.
    """
    filas = []
    for f in FuenteEstado.objects.filter(org=org).order_by("fuente"):
        filas.append({
            "fuente": f.fuente, "activa": f.activa, "estado": f.estado,
            "frescura": f.frescura, "registros": f.registros,
            "concluyente": f.concluyente,
            "dato_en": f.dato_en.isoformat() if f.dato_en else None,
            "ultima_consulta": (f.ultima_consulta_fin.isoformat()
                                if f.ultima_consulta_fin else None),
            "motivo_no_disponible": f.motivo_no_disponible,
            #  El mensaje tecnico NO viaja al prompt: puede traer una URL, y una
            #  URL de SmartOLT lleva el identificador del equipo de un cliente.
            "hubo_error": bool(f.error_tecnico),
            "fallos_consecutivos": f.fallos_consecutivos,
        })
    no_concluyentes = [f["fuente"] for f in filas if not f["concluyente"]]
    return {"fuentes": filas,
            "sin_informacion_util": no_concluyentes,
            "aviso": ("de estas fuentes no se puede concluir nada: un cero aqui "
                      "no significa que la operacion este sana"
                      if no_concluyentes else "")}


# =============================================================================
#  PROPUESTAS Y DECISIONES
# =============================================================================

def propuestas_pendientes(org, *, limite=TOPE) -> dict:
    """Lo que el Supervisor recomendo y nadie decidio todavia."""
    qs = P.objects.filter(org=org, estado=P.PROPUESTA).order_by("-prioridad")
    filas = [{
        "id": str(p.id), "accion": p.accion_propuesta, "motivo": p.motivo,
        "prioridad": p.prioridad, "impacto": p.impacto,
        "tipo_senal": p.tipo_senal,
        "nivel_requerido": p.nivel_autonomia_requerido,
        "origen": f"{p.origen_tipo}:{p.origen_id}",
        "expira_en": p.expira_en.isoformat() if p.expira_en else None,
    } for p in qs[:_acotar(limite)]]
    return {"propuestas": filas, "cuantas": len(filas)}


def decisiones_recientes(org, *, limite=TOPE) -> dict:
    """
    Que decidio una persona, y QUE RESULTADO tuvo.

    El resultado viaja porque es lo que separa medir acierto de medir obediencia.
    'pendiente' y 'no_se_puede_saber' se devuelven tal cual: convertirlos en
    "funciono" seria inventar un desenlace.
    """
    qs = (DecisionSupervisor.objects.filter(org=org)
          .select_related("situacion").order_by("-decidida_en"))
    filas = [{
        "recomendacion": d.recomendacion, "decision": d.tipo,
        "decidida_en": d.decidida_en.isoformat(),
        "motivo": d.motivo,
        "resultado": d.resultado,
        "hubo_correccion": bool(d.correccion),
        "situacion": d.situacion.codigo if d.situacion_id else None,
        #  Si la decidio una persona o expiro sola.
        "la_tomo_una_persona": d.actor_id is not None,
    } for d in qs[:_acotar(limite)]]
    return {"decisiones": filas, "cuantas": len(filas)}


# =============================================================================
#  LIMITES
# =============================================================================

def mis_limites(org) -> dict:
    """
    Hasta donde puede llegar el Supervisor AHORA, y por que.

    Se la da al modelo para que pueda contestar honestamente "no puedo hacer eso":
    si no conociera su propio nivel, tendria que adivinar -- y adivinar hacia
    arriba es prometer algo que la frontera despues rechaza, que es la peor forma
    de equivocarse.

    LO QUE ESTA HERRAMIENTA NO HACE: cambiar nada. Es una lectura. Subir el nivel
    exige una persona, y eso lo impone 'autonomia.cambiar' y una restriccion de la
    base -- no el prompt.
    """
    estado = gob_autonomia.nivel_efectivo(org)
    return {
        "nivel_configurado": estado["configurado"],
        "nivel_efectivo": estado["efectivo"],
        "recortado": estado["recortado"],
        "motivo_del_recorte": estado["motivo"],
        "interruptor_de_autonomia_permite_ejecutar":
            estado["interruptor_permite"],
        "puede_ejecutar_acciones": estado["efectivo"] >= 3,
        "nota": ("en esta etapa el Supervisor observa y recomienda. No tiene "
                 "ningun camino de ejecucion: no reinicia equipos, no cierra "
                 "casos, no crea ni reasigna tickets y no cambia la "
                 "programacion."),
    }


# =============================================================================
#  EL MAPA  --  literal y cerrado
# =============================================================================
#  Igual que el registro de trabajos del scheduler: un diccionario literal que se
#  lee de un vistazo para auditar QUE puede consultar el Supervisor. No hay
#  registro dinamico y no hay 'getattr' sobre un nombre que venga del modelo.
# =============================================================================
#  M02 / M03  --  lo que P6 sumo. TODO LECTURA.
# =============================================================================

def coordinaciones_de_situacion(org, *, codigo: str) -> dict:
    """
    Que trabajo se pidio a partir de esta situacion, y en que estado esta.

    Contesta "¿que evidencia falta?" con contenido en vez de con una excusa: una
    solicitud abierta es evidencia que todavia no llego.

    'completadas_sin_validar' viaja APARTE a proposito. Una actividad terminada
    cuya validacion nadie aprobo NO es una actividad resuelta, y presentarlas
    juntas afirmaria que el problema se atendio.
    """
    s = _situacion(org, codigo)
    salida = pendientes_de_la_situacion(s)
    salida["codigo"] = s.codigo
    return salida


def pendientes_criticos(org, *, limite=TOPE) -> dict:
    """
    Los pendientes de M02 que necesitan a alguien: vencidos, sin responsable,
    bloqueados o esperando una dependencia.

    NO DEVUELVE NOMBRES de colaboradores, y no es un olvido: la autorizacion de
    tratamiento que ampara mandar datos a un proveedor externo se razono para
    datos de CLIENTE (PRD RNF-01), y un colaborador tambien es un titular. Se
    devuelve el id del responsable y el conteo por responsable; resolver el
    nombre es de la pantalla, que no sale del servidor.
    """
    from operaciones import actividades as m02
    from operaciones.models import ActividadOperativa as _A

    qs = m02.pendientes_relevantes(org, solo_abiertas=True)
    filas, por_responsable = [], {}
    for a in qs[:_acotar(limite)]:
        clase = m02.clasificar_vencimiento(a)
        critico = (clase in (m02.VENCIDA, m02.VENCE_PRONTO)
                   or a.responsable_id is None
                   or a.estado_operativo == _A.BLOQUEADA
                   or bool(a.depende_de_id and a.bloqueada_por_dependencia))
        if not critico:
            continue
        clave = str(a.responsable_id) if a.responsable_id else "(sin responsable)"
        por_responsable[clave] = por_responsable.get(clave, 0) + 1
        filas.append({
            "id": str(a.id), "tipo": a.tipo, "titulo": a.titulo,
            "estado": a.estado_operativo, "vencimiento": clase,
            "responsable_id": str(a.responsable_id) if a.responsable_id else "",
            "sin_responsable": a.responsable_id is None,
            "bloqueada": a.estado_operativo == _A.BLOQUEADA,
            "motivo_bloqueo": a.motivo_bloqueo,
            "esperando_dependencia": bool(a.depende_de_id
                                          and a.bloqueada_por_dependencia),
        })
    return {"pendientes": filas, "cuantos": len(filas),
            "por_responsable": por_responsable,
            "nota": "sin nombres de colaborador a proposito; el id sirve para "
                    "que la pantalla lo resuelva"}


def panorama_programacion(org, *, dia=None) -> dict:
    """
    La jornada de M03: cuanto hay programado, la capacidad y que esta en riesgo
    de plazo.

    El veredicto de capacidad viaja TAL CUAL lo da 'capacidad.py', incluido
    'CAPACIDAD_NO_DETERMINABLE'. "No se puede determinar" NO es "no hay
    sobrecarga", y colapsar los dos es el error que la capa de fuentes existe
    para no repetir. Igual con 'ordenes_sin_plazo_medible', que se cuenta aparte
    de las que estan a tiempo.
    """
    from datetime import date as _date

    d = None
    if dia:
        try:
            d = _date.fromisoformat(str(dia)[:10])
        except ValueError:
            return {"error": "la fecha tiene que ser AAAA-MM-DD",
                    "recibido": str(dia)[:20]}
    return panorama_m03(org, dia=d)


HERRAMIENTAS = {
    "listar_situaciones": listar_situaciones,
    "detalle_situacion": detalle_situacion,
    "timeline_situacion": timeline_situacion,
    "afectados_situacion": afectados_situacion,
    "casos_de_situacion": casos_de_situacion,
    "relaciones_situacion": relaciones_situacion,
    "estado_fuentes": estado_fuentes,
    "propuestas_pendientes": propuestas_pendientes,
    "decisiones_recientes": decisiones_recientes,
    "mis_limites": mis_limites,
    #  P6
    "coordinaciones_de_situacion": coordinaciones_de_situacion,
    "pendientes_criticos": pendientes_criticos,
    "panorama_programacion": panorama_programacion,
}

#  Los argumentos que CADA herramienta acepta. Es una lista blanca: un argumento
#  que el modelo invente se descarta en vez de llegar a la funcion. Sin esto, un
#  'org' inventado o un 'limite' de un millon entrarian por kwargs.
ARGUMENTOS = {
    "listar_situaciones": {"estado", "limite"},
    "detalle_situacion": {"codigo"},
    "timeline_situacion": {"codigo", "limite"},
    "afectados_situacion": {"codigo"},
    "casos_de_situacion": {"codigo"},
    "relaciones_situacion": {"codigo"},
    "estado_fuentes": set(),
    "propuestas_pendientes": {"limite"},
    "decisiones_recientes": {"limite"},
    "mis_limites": set(),
    #  P6. 'panorama_programacion' acepta 'dia' y nada mas: ni un rango, ni un
    #  responsable -- un rango abierto dejaria al modelo pedir la programacion
    #  de un año entero y pagarla la empresa.
    "coordinaciones_de_situacion": {"codigo"},
    "pendientes_criticos": {"limite"},
    "panorama_programacion": {"dia"},
}


def ejecutar(org, nombre: str, argumentos: dict) -> dict:
    """
    Corre una herramienta. El tenant lo pone ESTA funcion, no el modelo.

    Los argumentos se FILTRAN contra la lista blanca antes de llegar a la
    funcion. Es fail-closed: lo que no esta declarado no pasa, asi que un
    argumento inventado --o dictado en un mensaje-- se descarta en silencio en vez
    de convertirse en un parametro de consulta.
    """
    fn = HERRAMIENTAS.get(str(nombre))
    if fn is None:
        raise HerramientaDesconocida(
            f"'{nombre}' no es una herramienta del Supervisor. Las que hay: "
            f"{', '.join(sorted(HERRAMIENTAS))}")

    permitidos = ARGUMENTOS.get(str(nombre), set())
    limpios = {k: v for k, v in (argumentos or {}).items() if k in permitidos}
    return fn(org, **limpios)


def _situacion(org, codigo):
    """
    Una situacion de ESTA organizacion, por su codigo legible.

    El filtro por 'org' esta aqui y no en quien llama a proposito: es el unico
    lugar por el que todas las herramientas de situacion resuelven un codigo, asi
    que una herramienta nueva que se olvide del tenant no puede existir.
    """
    return S.objects.filter(org=org, codigo=str(codigo).strip()).first()


def _acotar(limite) -> int:
    try:
        n = int(limite)
    except (TypeError, ValueError):
        return TOPE
    return max(1, min(n, TOPE))


# =============================================================================
#  EL ESQUEMA QUE VE EL MODELO
# =============================================================================

def esquema() -> list[dict]:
    """
    Las herramientas en el formato de 'tools' que entiende el cliente.

    Las descripciones dicen QUE devuelve cada una y, donde importa, que NO
    devuelve: el modelo no puede pedir un nombre de cliente si la descripcion
    dice que no viene.
    """
    def h(nombre, descripcion, propiedades=None, requeridos=None):
        return {"type": "function", "function": {
            "name": nombre, "description": descripcion,
            "parameters": {"type": "object",
                           "properties": propiedades or {},
                           "required": requeridos or []}}}

    codigo = {"codigo": {"type": "string",
                         "description": "El código de la situación, por ejemplo "
                                        "'S-001'."}}
    limite = {"limite": {"type": "integer",
                         "description": f"Cuántos traer, máximo {TOPE}."}}

    return [
        h("listar_situaciones",
          "Las situaciones operativas. Sin argumentos devuelve las VIVAS. "
          "Devuelve código, título, estado, riesgo y cuántos afectados.",
          {**limite, "estado": {"type": "string",
                                "description": "'vivas' (por defecto) o un "
                                               "estado concreto."}}),
        h("detalle_situacion",
          "Una situación completa: estado, riesgo, hipótesis CON su nivel de "
          "confianza, evidencia, verificación y QUÉ INFORMACIÓN FALTA.",
          codigo, ["codigo"]),
        h("timeline_situacion",
          "El historial de una situación en orden. Es append-only: lo que "
          "aparece, pasó.", {**codigo, **limite}, ["codigo"]),
        h("afectados_situacion",
          "Qué está afectado, por tipo (PON, OLT, caso...), cuántos vigentes y "
          "cuántos ya se recuperaron.", codigo, ["codigo"]),
        h("casos_de_situacion",
          "Los casos de cliente asociados, con estado, antigüedad y SLA. NO "
          "devuelve nombres ni datos de contacto. Pueden ser CERO: una "
          "situación puede existir sin que nadie la haya reportado.",
          codigo, ["codigo"]),
        h("relaciones_situacion",
          "Con qué otras situaciones se relaciona y por qué, y si la relación la "
          "puso una persona o la correlación automática.", codigo, ["codigo"]),
        h("estado_fuentes",
          "Cómo está cada fuente: activa, estado de la última consulta, frescura "
          "del dato y si de ella se puede CONCLUIR algo. Consultala antes de "
          "afirmar que no hay afectaciones."),
        h("propuestas_pendientes",
          "Las recomendaciones que el Supervisor dejó y nadie decidió todavía.",
          limite),
        h("decisiones_recientes",
          "Qué decidió una persona sobre recomendaciones anteriores y qué "
          "resultado tuvo.", limite),
        h("mis_limites",
          "El nivel de autonomía configurado y el efectivo, con el motivo de "
          "cualquier recorte. Consultala antes de decir que puedes hacer algo."),

        #  --- P6: M02 y M03. Las tres son de LECTURA. --------------------
        h("coordinaciones_de_situacion",
          "Qué trabajo se PIDIÓ a partir de una situación y en qué estado está. "
          "Devuelve las completadas-sin-validar APARTE: terminada no es validada. "
          "Úsala para contestar qué evidencia falta.", codigo, ["codigo"]),
        h("pendientes_criticos",
          "Los pendientes que necesitan a alguien: vencidos, sin responsable, "
          "bloqueados o esperando una dependencia, con el conteo por responsable. "
          "NO devuelve nombres de colaborador, solo su id: no los pidas ni los "
          "inventes.", limite),
        h("panorama_programacion",
          "La jornada: cuántas órdenes hay programadas, el veredicto de capacidad "
          "y cuáles están en riesgo de plazo. OJO: el veredicto puede ser "
          "'CAPACIDAD_NO_DETERMINABLE', que NO significa que no haya "
          "sobrecarga; y las órdenes sin plazo medible se cuentan aparte de las "
          "que están a tiempo. No las sumes.",
          {"dia": {"type": "string",
                   "description": "Día en AAAA-MM-DD. Por defecto, hoy."}}),
    ]
