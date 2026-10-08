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
  1. TODAS son de LECTURA MENOS DOS, y las dos se nombran: 'delegar_tarea' y
     'quitar_tarea' escriben una fila de 'TareaDelegada'. Ninguna otra escribe,
     ninguna cambia el estado de un caso ni de una orden, y ninguna llama a un
     sistema externo. No es una convencion: el despachador rechaza un nombre
     que no este en este mapa, asi que no hay forma de alcanzar otra cosa.

     LAS DOS QUE ESCRIBEN NO DECIDEN QUE SE HACE, solo si una tarea del
     CATALOGO esta encendida. El catalogo vive en 'tareas_delegadas.py' y es
     cerrado: el modelo elige de esa lista y no puede agregarle nada. Una clave
     que no este ahi se rechaza con un error legible, y una que quedo en la
     base pero ya no esta en el catalogo no habilita nada.

     Y NINGUNA DE LAS DOS AMPLIA EL ALCANCE. Delegar una tarea no sube el nivel
     de autonomia -- eso sigue exigiendo una persona en otra pantalla, con
     motivo y criterios medidos. Delegar con el nivel bajo no hace nada, y la
     respuesta lo dice con todas las letras.

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


# =============================================================================
#  EL RELEVO DE TURNO  --  P11
# =============================================================================

def resumen_de_turno(org, *, horas=None) -> dict:
    """
    Las doce preguntas que alguien se hace al tomar el turno.

    Vive en 'operaciones.turno' y aqui solo se expone: el modelo no arma el
    resumen, lo LEE. Cada bloque viaja con su procedencia, y la procedencia es
    parte del dato -- leer un INFERIDO como OBSERVADO es justo el error que la
    descripcion de esta herramienta existe para que el modelo no cometa.
    """
    from operaciones import turno

    return turno.resumen_de_turno(org, horas=_acotar_horas(horas))


def evaluacion_shadow(org) -> dict:
    """
    Que habria hecho el Supervisor y que paso de verdad, lado a lado.

    Los numeros salen de 'indicadores.indicadores_evaluacion': no hay una
    segunda formula. Y vienen en su sobre, asi que un indicador puede decir
    NO_APLICA o DATOS_INSUFICIENTES -- que NO es un cero.
    """
    from operaciones import turno

    return turno.evaluacion_shadow(org)


def _acotar_horas(horas) -> int:
    """
    Entre 1 y 72 horas. Sin tope, un "resumen de turno" de un año entero seria
    una consulta de tabla completa pedida desde un mensaje de chat.
    """
    from operaciones import turno

    try:
        n = int(horas)
    except (TypeError, ValueError):
        return turno.HORAS_TURNO
    return max(1, min(n, 72))


# =============================================================================
#  LAS HERRAMIENTAS TECNICAS  --  WispHub, por el motor, con politica de campos
# =============================================================================
#
#  DE DONDE SALEN
#  --------------
#  El rol 'supervisor_noc' de 'tenant_config' declaro diez herramientas tecnicas
#  con su lista blanca de campos por herramienta. Ese trabajo se conserva: lo
#  que cambia es QUIEN las llama. No se vuelven a escribir aqui --serian dos
#  catalogos de lo mismo-- sino que se piden por el camino que ya existe,
#  'POST /interno/herramienta/<nombre>' del motor, que es el unico que tiene la
#  credencial de WispHub.
#
#  CUATRO DE LAS DIEZ, Y EL MOTIVO ES UNA GARANTIA, NO UN LIMITE TECNICO
#  ---------------------------------------------------------------------
#  Las seis de ONT/red ('consultar_estado_ont', 'consultar_senal_ont',
#  'consultar_estabilidad_enlace', 'diagnosticar_falla_ont',
#  'consultar_estado_catv', 'consultar_incidente_red') declaran
#  'inyectados_obligatorios: [sn_onu]': su identificador sale de la SESION
#  VERIFICADA, nunca de un argumento del modelo. Y la ruta interna pasa
#  'sesion=None' a proposito. El motor explica por que, en
#  'nucleo/modelo/motor.py:503':
#
#      "el id sale de la sesion verificada, nunca de un argumento del modelo.
#       Si no, bastaria que el modelo consultara a otro cliente --por inyeccion
#       de prompt o por un rol interno que si puede hacerlo-- para que la sesion
#       se quedara con el serial ajeno y el siguiente reinicio remoto cayera
#       sobre la casa equivocada."
#
#  "un rol interno que si puede hacerlo" es EXACTAMENTE lo que seria el
#  Supervisor si se le dejara pasar el serial. Asi que esas seis no se cablean,
#  y no por falta de ganas: hacerlo exige una decision sobre como se acredita un
#  destinatario sin sesion, y esa decision no esta tomada.
#
#  LA POLITICA SE APLICA EN EL MOTOR, ANTES DE CONTESTAR
#  ----------------------------------------------------
#  Se pasa 'rol=supervisor_noc' y el motor corre su propio
#  'listas_blancas.filtrar_campos' --fail-closed, con notacion con punto y las
#  tres formas de respuesta-- mas el barrido de 'nunca_revelar'. El campo no
#  autorizado NO sale del motor: no llega aqui y mucho menos al modelo. Copiar
#  ese filtro a Django habria dejado dos implementaciones de la misma garantia.

#: El rol de 'tenant_config' cuya politica de campos se aplica. Es el unico uso
#: que le queda a ese rol: NO es el anfitrion de la conversacion.
ROL_POLITICA = "supervisor_noc"


def _del_motor(nombre: str, argumentos: dict | None = None) -> dict:
    """
    Llama una herramienta tecnica del catalogo del tenant, con politica aplicada.

    UN SOLO LUGAR PASA EL ROL, y es para que no se pueda olvidar: una
    herramienta tecnica nueva que se agregue abajo la hereda sola. Si cada
    funcion lo pasara por su cuenta, la que se olvidara devolveria la ficha
    cruda y nadie lo notaria hasta leer una cedula en una respuesta.
    """
    from operaciones.fuentes_adaptadores import (MotorNoDisponible,
                                                 _NoDeclarada,
                                                 _pedirle_al_motor)

    try:
        salida = _pedirle_al_motor(nombre, argumentos or {}, rol=ROL_POLITICA)
    except _NoDeclarada as e:
        #  No esta declarada para un servicio, o falta la politica. Es una
        #  respuesta legible, no una excepcion que tumbe el turno: el modelo
        #  tiene que poder decir "esto no lo puedo consultar" en vez de callarse.
        return {"error": "HERRAMIENTA_NO_DISPONIBLE", "detalle": str(e)}
    except MotorNoDisponible as e:
        return {"error": "MOTOR_NO_DISPONIBLE", "detalle": str(e)}

    if salida is None:
        return {"error": "SIN_RESULTADO",
                "detalle": "el motor contesto sin resultado"}
    #  'filtrar_campos' puede devolver {"error": "...Resultado descartado."}
    #  cuando el rol no tiene lista blanca para esa herramienta. Se deja pasar
    #  tal cual: es la respuesta correcta y el modelo tiene que verla.
    return salida if isinstance(salida, dict) else {"resultado": salida}


def consultar_ticket(org, *, limite=TOPE) -> dict:
    """
    Los tickets de WispHub, con los campos que la politica permite.

    NO acepta un id: esta herramienta del catalogo no declara
    'filtros_verificados', asi que el motor ignora cualquier argumento que se le
    proponga (fail-closed). Devuelve la lista que WispHub recorta por su cuenta.
    """
    return _del_motor("consultar_ticket")


def consultar_tickets_de_cliente(org) -> dict:
    """
    La otra vista de los tickets, con su propia lista blanca -- mas corta.

    La API de WispHub NO filtra por cliente (ocho nombres de parametro probados,
    todos ignorados: ver la skill 'wisphub-api'), asi que esto no devuelve "los
    de un cliente": devuelve la lista, y cruzarla es trabajo de quien lee.
    """
    return _del_motor("consultar_tickets_de_cliente")


def consultar_tecnicos(org) -> dict:
    """El personal de WispHub: id, usuario y nombre. Nada mas."""
    return _del_motor("consultar_tecnicos")


def diagnosticar_servicio(org, *, id_servicio) -> dict:
    """
    El estado optico del equipo de un servicio. Por id de servicio, no por serial.

    POR QUE ESTA Y NO LAS SEIS DE ONU
    ---------------------------------
    Las seis exigen 'sn_onu' INYECTADO desde la sesion verificada, para que el
    modelo no elija de que equipo pregunta. El Supervisor entra por
    la ruta interna de herramientas del motor, que pasa 'sesion=None'
    a proposito: no tiene
    sesion, asi que esas seis son inalcanzables para el -- estan autorizadas
    para su rol, con su lista blanca lista, y no se pueden llamar.

    Esta recibe 'id_servicio' --argumento legitimo, declarado y verificado, que
    el Supervisor conoce de los afectados de una situacion-- y el motor resuelve
    el equipo adentro. EL SERIAL NO VUELVE en la respuesta, y esa ausencia es el
    diseño: si saliera, bastaria una conversacion para cosecharlos.

    QUE DEVUELVE, Y LA DISTINCION QUE IMPORTA
    -----------------------------------------
        estado           en_linea | caido | desconocido
        causa_caida      sin_energia | fibra | otra   (solo si esta caido)
        senal_dbm        la de bajada en dBm, que es la que recibe el equipo
        senal            buena | debil | sin_dato -- la CALCULA el codigo contra
                         el rango de la guia, no la juzga el modelo
        estado_config    el 'Match state' de la OLT. NO habla de la señal: dice
                         si la configuracion del equipo coincide con su perfil

    'sin_energia' es la casa del cliente --se fue la luz, o lo desenchufaron--.
    'fibra' es un corte o una falla en la NAP, y eso es NUESTRO. Son opuestas:
    tratarlas igual seria cerrar casos de gente que sigue sin servicio.

    'desconocido' SIEMPRE trae su 'motivo', y no se lee como sano.
    """
    ident = str(id_servicio or "").strip()
    if not ident:
        return {"error": "FALTA_ID_SERVICIO",
                "detalle": "hace falta el id del servicio"}
    return _del_motor("diagnosticar_servicio", {"id_servicio": ident})


def consultar_cliente(org, *, id_servicio) -> dict:
    """
    La ficha de un servicio, filtrada.

    'id_servicio' SI es un argumento legitimo del modelo: esta declarado en
    'filtros_verificados' de la herramienta y el Supervisor lo conoce de los
    afectados de una situacion. La ficha cruda trae 54 campos --cuatro
    contrasenas y el GPS del domicilio-- y lo que vuelve es lo que la politica
    de 'supervisor_noc' deja pasar.
    """
    ident = str(id_servicio or "").strip()
    if not ident:
        return {"error": "FALTA_ID_SERVICIO",
                "detalle": "hace falta el id del servicio"}
    return _del_motor("consultar_cliente", {"id_servicio": ident})


# ===========================================================================
#  LO QUE UNA PERSONA LE DELEGA AL SUPERVISOR
# ===========================================================================
#  EL CATALOGO ES CERRADO, y esa es toda la decision de seguridad de este
#  bloque. El modelo ENTIENDE la frase --"cerra los que ya esten cerrados en
#  WispHub si el equipo esta bien"-- y elige una tarea de una lista que el
#  codigo ya sabe hacer. No construye la tarea.
#
#  La alternativa era que de la frase saliera la accion. Mas flexible, y con la
#  garantia en el texto: alguien escribe la misma orden sin la parte del
#  diagnostico y el Supervisor cerraria casos sin mirar el equipo. Lo que
#  protege a un cliente dejaria de ser codigo y pasaria a ser como estaba
#  redactada una frase.

def tareas_disponibles(org) -> dict:
    """
    Que tareas se le pueden delegar al Supervisor, y que hace cada una.

    Trae tambien 'que_no_hace' de cada una: el modelo tiene que poder decir que
    NO va a pasar, y sin esa frase lo completaria por su cuenta.
    """
    from operaciones import tareas_delegadas as td

    return {"tareas": td.catalogo_legible()}


def tareas_activas(org) -> dict:
    """Lo que esta delegado hoy, con cuando se delego y con que palabras."""
    from operaciones import tareas_delegadas as td

    return {"delegadas": td.delegadas(org)}


def delegar_tarea(org, *, clave="", pedido="", actor=None) -> dict:
    """
    Deja delegada una tarea del catalogo. La pide una PERSONA, por el chat.

    'actor' NO es un argumento del modelo: lo pone 'ejecutar' desde la
    conversacion verificada (ver 'NECESITAN_ACTOR'). Si viajara como parametro,
    alguien podria dictarlo en un mensaje y la tarea quedaria a nombre de quien
    no la pidio.

    DELEGAR NO AMPLIA EL ALCANCE. La respuesta dice si ademas falta subir el
    nivel de autonomia, porque delegar con el nivel bajo no hace nada y el
    silencio ahi seria el peor resultado: la persona se va creyendo que quedo
    andando.
    """
    from operaciones import autonomia
    from operaciones import tareas_delegadas as td

    try:
        fila = td.delegar(org, str(clave).strip(), actor=actor,
                          pedido_textual=str(pedido or ""))
    except td.ErrorTarea as e:
        return {"error": "no_se_pudo_delegar", "detalle": str(e)}

    ficha = td.CATALOGO.get(fila.clave, {})
    nivel_que_exige = int(ficha.get("exige_nivel") or 0)
    veredicto = autonomia.puede(org, nivel_que_exige) if nivel_que_exige else {
        "puede": True, "motivo": ""}

    return {
        "delegada": fila.clave,
        "nombre": ficha.get("nombre", fila.clave),
        "ya_puede_actuar": bool(veredicto.get("puede")),
        #  Lo que FALTA, dicho sin rodeos. Una tarea delegada que no puede
        #  actuar no es una tarea delegada a medias: es una que no hace nada.
        "que_falta": ("" if veredicto.get("puede") else
                      f"la tarea quedó delegada, pero todavía no puede actuar: "
                      f"{veredicto.get('motivo')}. Se habilita subiendo el "
                      f"nivel de autonomía desde la pantalla del Supervisor, "
                      f"y eso lo hace una persona."),
    }


def quitar_tarea(org, *, clave="", actor=None) -> dict:
    """Deja de delegar una tarea. Queda el registro de que existio."""
    from operaciones import tareas_delegadas as td

    try:
        fila = td.quitar(org, str(clave).strip(), actor=actor)
    except td.ErrorTarea as e:
        return {"error": "no_se_pudo_quitar", "detalle": str(e)}
    return {"quitada": fila.clave,
            "detalle": "el Supervisor deja de hacerla desde el próximo ciclo"}


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
    #  P9 (08/10/2026). Lo que una persona le delega al Supervisor.
    "tareas_disponibles": tareas_disponibles,
    "tareas_activas": tareas_activas,
    "delegar_tarea": delegar_tarea,
    "quitar_tarea": quitar_tarea,
    #  P6
    "coordinaciones_de_situacion": coordinaciones_de_situacion,
    "pendientes_criticos": pendientes_criticos,
    "panorama_programacion": panorama_programacion,
    #  P11
    "resumen_de_turno": resumen_de_turno,
    "evaluacion_shadow": evaluacion_shadow,
    #  Tecnicas, por el motor, con la politica de 'supervisor_noc' aplicada
    #  antes de contestar.
    "consultar_ticket": consultar_ticket,
    "consultar_tickets_de_cliente": consultar_tickets_de_cliente,
    "consultar_tecnicos": consultar_tecnicos,
    "consultar_cliente": consultar_cliente,
    "diagnosticar_servicio": diagnosticar_servicio,
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
    "tareas_disponibles": set(),
    "tareas_activas": set(),
    #  'actor' NO esta aqui a proposito: no es un argumento del modelo.
    "delegar_tarea": {"clave", "pedido"},
    "quitar_tarea": {"clave"},
    #  P6. 'panorama_programacion' acepta 'dia' y nada mas: ni un rango, ni un
    #  responsable -- un rango abierto dejaria al modelo pedir la programacion
    #  de un año entero y pagarla la empresa.
    "coordinaciones_de_situacion": {"codigo"},
    "pendientes_criticos": {"limite"},
    "panorama_programacion": {"dia"},
    #  P11. 'resumen_de_turno' acepta 'horas' y nada mas --acotado a 72 en
    #  '_acotar_horas'--; 'evaluacion_shadow' no acepta ninguno: su periodo lo
    #  fija el indicador, no el modelo.
    "resumen_de_turno": {"horas"},
    "evaluacion_shadow": set(),
    #  Tecnicas. 'consultar_cliente' acepta 'id_servicio' porque la herramienta
    #  del catalogo lo declara en 'filtros_verificados'; las otras tres no
    #  aceptan ninguno, y el motor ignoraria igual lo que se le propusiera.
    "consultar_ticket": {"limite"},
    "consultar_tickets_de_cliente": set(),
    "consultar_tecnicos": set(),
    "consultar_cliente": {"id_servicio"},
    "diagnosticar_servicio": {"id_servicio"},
}


#  LAS QUE NECESITAN SABER QUIEN LAS PIDIO (08/10/2026).
#
#  Casi ninguna: la enorme mayoria de las herramientas del chat solo leen, y a
#  una lectura no le importa quien pregunta mas alla del tenant. Delegar una
#  tarea SI es distinto -- deja algo encendido que va a actuar despues, cuando
#  esa persona no este mirando-- asi que tiene que quedar a nombre de alguien.
#
#  EL ACTOR NO VIAJA COMO ARGUMENTO DEL MODELO, y por eso esta en un conjunto
#  aparte y no en 'ARGUMENTOS'. Sale de la conversacion verificada; si fuera un
#  parametro mas, el modelo podria proponerlo --o alguien dictarselo en un
#  mensaje-- y la tarea quedaria delegada a nombre de quien no la pidio. Es la
#  misma regla que 'inyectar_sesion' aplica en el motor.
NECESITAN_ACTOR = {"delegar_tarea", "quitar_tarea"}


def ejecutar(org, nombre: str, argumentos: dict, *, actor=None) -> dict:
    """
    Corre una herramienta. El tenant lo pone ESTA funcion, no el modelo.

    Los argumentos se FILTRAN contra la lista blanca antes de llegar a la
    funcion. Es fail-closed: lo que no esta declarado no pasa, asi que un
    argumento inventado --o dictado en un mensaje-- se descarta en silencio en vez
    de convertirse en un parametro de consulta.

    'actor' lo pone quien llama desde la conversacion verificada, nunca el
    modelo, y solo llega a las herramientas de 'NECESITAN_ACTOR'.
    """
    fn = HERRAMIENTAS.get(str(nombre))
    if fn is None:
        raise HerramientaDesconocida(
            f"'{nombre}' no es una herramienta del Supervisor. Las que hay: "
            f"{', '.join(sorted(HERRAMIENTAS))}")

    permitidos = ARGUMENTOS.get(str(nombre), set())
    limpios = {k: v for k, v in (argumentos or {}).items() if k in permitidos}
    if str(nombre) in NECESITAN_ACTOR:
        limpios["actor"] = actor
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

        #  --- P9: lo que una persona delega. EL CATALOGO ES CERRADO. ------
        #  Las descripciones le dicen al modelo que NO puede inventar una
        #  tarea. Es lo unico que lo separa de intentar construir lo que le
        #  pidan: si no dijeran que la lista manda, trataria de cumplir
        #  cualquier frase con las herramientas que tenga a mano.
        h("tareas_disponibles",
          "Las tareas que se le pueden delegar al Supervisor, con qué hace y "
          "qué NO hace cada una. La lista es cerrada: NO existe forma de "
          "delegar algo que no esté acá. Consultala SIEMPRE antes de aceptar "
          "un encargo, y si lo que te piden no está, decilo en vez de "
          "intentar armarlo con otras herramientas."),
        h("tareas_activas",
          "Lo que ya está delegado hoy, con cuándo se delegó y con qué "
          "palabras se pidió."),
        h("delegar_tarea",
          "Deja delegada UNA tarea del catálogo, para que el Supervisor la "
          "haga siempre sin que nadie vuelva a pedirla. 'clave' tiene que ser "
          "una de 'tareas_disponibles', exacta. En 'pedido' va la frase con la "
          "que te lo pidieron, tal cual, para que quede registrada. La "
          "respuesta puede decir que la tarea todavía NO puede actuar porque "
          "falta subir el nivel de autonomía: si lo dice, repetilo, porque "
          "delegar sin ese nivel no hace nada.",
          {"clave": {"type": "string"}, "pedido": {"type": "string"}},
          ["clave"]),
        h("quitar_tarea",
          "Deja de delegar una tarea. El Supervisor deja de hacerla desde el "
          "próximo ciclo.",
          {"clave": {"type": "string"}}, ["clave"]),

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

        #  --- P11: el relevo de turno. Las dos son de LECTURA. -----------
        h("resumen_de_turno",
          "El relevo de turno: qué ocurrió, qué sigue abierto, qué empeoró, qué "
          "se resolvió, qué sigue SIN VERIFICAR, qué tickets aparecieron, qué "
          "SLA están en riesgo, qué evidencias y recomendaciones quedaron "
          "pendientes, qué requiere a una persona, qué fuentes fallaron y qué "
          "pasó de noche. CADA bloque trae su PROCEDENCIA (OBSERVADO, INFERIDO, "
          "RECOMENDADO, CONFIRMADO, DESCONOCIDO): respetala al contestar y NUNCA "
          "presentes un INFERIDO como un hecho. Un bloque DESCONOCIDO significa "
          "que no se pudo saber, NO que no haya nada.",
          {"horas": {"type": "integer",
                     "description": "Cuántas horas atrás mirar; 12 por defecto, "
                                    "72 como máximo."}}),
        h("evaluacion_shadow",
          "Qué habría hecho el Supervisor y qué pasó de verdad. Separa lo "
          "OBSERVADO de lo INFERIDO, lo RECOMENDADO y lo CONFIRMADO. OJO: "
          "'aceptada' NO es 'correcta' --el acierto sale solo de lo CONFIRMADO, "
          "que exige evidencia-- y un indicador puede venir en NO_APLICA o "
          "DATOS_INSUFICIENTES, que NO es un cero: no lo reportes como tal."),

        #  --- Tecnicas: WispHub por el motor. Las cuatro LEEN. -----------
        h("consultar_tecnicos",
          "El personal técnico de WispHub: id, usuario y nombre. Úsala para "
          "resolver a quién se refiere un nombre antes de nombrarlo -- NUNCA "
          "inventes un id ni un técnico."),
        h("consultar_ticket",
          "Los tickets de WispHub con sus campos operativos: asunto, estado, "
          "prioridad, técnico, fechas y la zona del servicio. NO devuelve "
          "cédula, teléfono, dirección ni coordenadas. OJO: no acepta un id "
          "ni un filtro -- devuelve la lista que el proveedor recorta, así que "
          "no cuentes sobre ella como si fuera el total.", limite),
        h("consultar_tickets_de_cliente",
          "La vista corta de los tickets: id, asunto, estado, prioridad, "
          "técnico y fecha. OJO: a pesar del nombre NO filtra por cliente -- la "
          "API de WispHub ignora ese filtro (ocho parámetros probados). "
          "Devuelve la lista; cruzarla es tu trabajo, y si no podés, decilo."),
        h("consultar_cliente",
          "La ficha operativa de UN servicio por su id: estado, plan, zona, "
          "localidad, fecha de instalación, estado de facturas y saldo. NO "
          "devuelve nombre de contacto, cédula, teléfono, dirección, "
          "coordenadas ni contraseñas: no los pidas ni los supongas. El "
          "'id_servicio' lo sacás de los afectados de una situación.",
          {"id_servicio": {"type": "string",
                           "description": "El id del servicio en WispHub."}},
          ["id_servicio"]),

        h("diagnosticar_servicio",
          "El estado ÓPTICO del equipo de un servicio: si está en línea o "
          "caído, su señal de bajada y, si está caído, POR QUÉ. "
          "La señal viene DOS veces: 'senal_dbm' es el número y 'senal' es su "
          "clasificación ('buena', 'debil' o 'sin_dato'), que YA viene "
          "calculada -- no la recalcules ni compares dBm vos. "
          "'estado_config' NO habla de la señal: es si la configuración del "
          "equipo coincide con su perfil en la OLT. Un 'mismatch' ahí con señal "
          "buena no es un problema de señal; no los mezcles. "
          "La causa es lo que cambia la decisión y no se puede ignorar: "
          "'sin_energia' es la casa del cliente --se fue la luz o lo "
          "desenchufaron--, 'fibra' es un corte o una falla en la NAP y eso "
          "SÍ es de la red. Son opuestas; no las trates igual. "
          "Si 'equipo_registrado' es false, ese servicio no tiene equipo "
          "cargado en el proveedor y no se puede afirmar NADA sobre él -- eso "
          "no es 'está sano'. Si 'estado' es 'desconocido', viene con su "
          "'motivo' y tampoco se lee como sano. "
          "NO devuelve el serial del equipo: no lo pidas ni lo supongas. "
          "El 'id_servicio' lo sacás de los afectados de una situación.",
          {"id_servicio": {"type": "string",
                           "description": "El id del servicio en WispHub."}},
          ["id_servicio"]),
    ]
