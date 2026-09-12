# -*- coding: utf-8 -*-
"""
================================================================================
 RECUPERACION  --  busca en el corpus del tenant lo que responde la pregunta
================================================================================

Cierra el circuito del RAG. Hasta ahora el corpus se vectorizaba y se cargaba
(cli/cargar_corpus.py) y ahi se quedaba: motor.responder() solo usaba
construir_system(), asi que preguntar un procedimiento devolvia lo que el
modelo improvisara del prompt, no lo que dice la guia.

Como funciona
-------------
La pregunta se vectoriza con el MISMO modelo con que se vectorizo el corpus
(nucleo/recuperacion/embeddings.py -- un solo proveedor de plataforma, no por
tenant). No es un detalle: vectores de modelos distintos no son comparables, y
la busqueda no falla -- devuelve fragmentos peores, en silencio.

Se usa asistente.match_chunks, la vectorial pura, y no match_chunks_hibrido
aunque el YAML traiga busqueda_hibrida. Motivo: la hibrida devuelve un puntaje
RRF, que ordena pero no mide parecido, y no se puede comparar contra
umbral_similitud. Como el umbral es lo que decide "aca no hay nada que
responda esto", perderlo seria perder la garantia de RF-07. La hibrida queda
para cuando mejore el ORDEN de resultados que ya pasaron el umbral.

Aislamiento
-----------
Se apoya en persistencia.sesion(), que baja a app_backend y fija el tenant, asi
que las politicas de RLS aplican. match_chunks ademas filtra por
organization_id explicitamente: dos capas, como el resto del proyecto.
================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass

from nucleo.persistencia.db import sesion
from nucleo.recuperacion.embeddings import vectorizar


@dataclass(frozen=True)
class Fragmento:
    codigo: str
    titulo: str
    version: str
    contenido: str
    similitud: float

    def citar(self) -> str:
        """Como se le presenta al modelo: con su procedencia, para que pueda
        decir de donde salio en vez de afirmarlo como conocimiento propio."""
        version = f" v{self.version}" if self.version else ""
        return f"[{self.codigo}{version} — {self.titulo}]\n{self.contenido}"


def contar_elegibles(tenant: str, rol: str) -> int:
    """
    Cuantos fragmentos vigentes puede VER este rol, sin mirar similitud.

    Es la unica forma de distinguir dos fallos que se ven idénticos desde
    afuera y se arreglan en lugares opuestos:

      0   a este rol no se le asigno ningun documento. Es configuracion
          (se arregla en /manual), no recuperacion -- tocar el umbral o el
          modelo de embeddings no cambiaria nada.
      >0  habia documentos visibles y ninguno supero el umbral. Recien aca
          tiene sentido hablar de calibracion o de vocabulario.

    Confundirlos costo tiempo real (agosto 2026): 103 preguntas distintas
    quedaron registradas como 'sin respuesta' con similitud NULL, y se
    leyeron como un problema semantico cuando ningun documento tenia
    asignados los roles de cara al cliente.

    Se llama SOLO cuando la busqueda no devolvio nada -- ver recuperar().
    En el camino normal no se paga esta consulta.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select count(*) as n
                 from asistente.document_chunks c
                 join asistente.documents d on d.id = c.document_id
                where c.organization_id = %s and c.vigente
                  and d.estado = 'vigente'
                  and d.roles_permitidos is not null
                  and %s = any(d.roles_permitidos)""",
            (org, rol))
        fila = cur.fetchone()
    return int(fila["n"] if isinstance(fila, dict) else fila[0])


def documentos_visibles(tenant: str, rol: str) -> set[str]:
    """
    Los CODIGOS de documento que este rol puede recuperar.

    Complementa contar_elegibles(): ese dice cuantos fragmentos ve en total,
    este dice cuales documentos. Hace falta para distinguir con precision dos
    fallos que se parecen -- "el rol no ve NINGUN documento" y "el rol ve
    documentos pero no el que responde esta pregunta". Los dos se arreglan
    asignando roles en /manual, pero saber cual de los dos es evita revisar
    el corpus entero cuando el hueco es de un solo documento.

    Diagnostico, no camino caliente: lo usa cli/evaluar_rag.py, no el motor.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select distinct d.codigo
                 from asistente.documents d
                 join asistente.document_chunks c
                   on c.document_id = d.id and c.vigente
                where d.organization_id = %s and d.estado = 'vigente'
                  and d.roles_permitidos is not null
                  and %s = any(d.roles_permitidos)""",
            (org, rol))
        filas = cur.fetchall()
    return {(f["codigo"] if isinstance(f, dict) else f[0]) or "" for f in filas}


def recuperar_candidatos(config, tenant: str, rol: str,
                         pregunta: str) -> list[Fragmento]:
    """
    El top_k COMPLETO, ya ordenado, SIN aplicar el umbral.

    Es lo que recupera() usa por dentro. Se expone aparte porque sin ver lo
    que quedo DEBAJO del umbral no se pueden distinguir dos fallos que desde
    afuera son identicos:

      el fragmento correcto no entro al top_k    -> problema de busqueda
      entro, pero por debajo del umbral          -> problema de calibracion

    El primero no lo arregla mover un numero; el segundo si. Lo usa
    cli/evaluar_rag.py para clasificar cada fallo; el motor sigue llamando a
    recuperar(), que aplica el umbral como siempre.
    """
    vector = vectorizar(pregunta)

    with sesion(tenant) as (cur, org):
        cur.execute(
            """select codigo, titulo, version, contenido, similitud
               from asistente.match_chunks(
                 p_org => %s, p_query_embedding => %s::vector,
                 p_match_count => %s, p_umbral => 0.0, p_rol => %s)""",
            (org, str(vector), config.rag.top_k, rol))
        filas = cur.fetchall()

    return [
        Fragmento(codigo=f["codigo"] or "", titulo=f["titulo"] or "",
                  version=f["version"] or "", contenido=f["contenido"] or "",
                  similitud=float(f["similitud"]))
        for f in filas
    ]


def recuperar(config, tenant: str, rol: str,
              pregunta: str) -> tuple[list[Fragmento], float | None]:
    """
    Devuelve (fragmentos que superan el umbral, mejor similitud vista).

    La consulta se hace SIN umbral y el filtro se aplica aca. Cuesta lo mismo
    -el orden y el limite los pone igual la base- y a cambio queda el dato de
    cuanto se acerco lo mejor que habia. Sin eso, "no encontre nada" es una
    respuesta sin diagnostico: no se distingue un tema que no esta documentado
    de un umbral mal calibrado.

    'rol' filtra por documents.roles_permitidos (ver
    supabase/202608111433_documentos_roles.sql): un documento sin roles asignados no lo
    recupera NADIE, fail-closed -- no es opcional, cada rol solo ve el corpus
    que alguien le asigno a proposito.

    Lista vacia = el corpus no cubre eso (o no hay nada asignado a este rol
    todavia). Es informacion, no un fallo: quien llama decide que hacer con
    ese silencio.

    OJO con lo que significa superar el umbral: es PARECIDO SEMANTICO, no
    "aca esta la respuesta". Medido el 21/08/2026: "cuanto cuesta el plan mas
    caro" saca 0.488 contra un documento que no trae un solo precio a
    proposito. El umbral es un filtro de pertinencia, no una garantia de
    respaldo -- quien redacta la respuesta tiene que poder abstenerse igual.
    """
    candidatos = recuperar_candidatos(config, tenant, rol, pregunta)
    if not candidatos:
        return [], None

    mejor = max(f.similitud for f in candidatos)
    fragmentos = [f for f in candidatos
                  if f.similitud >= config.rag.umbral_similitud]
    return fragmentos, mejor


def registrar_sin_resultados(tenant: str, pregunta: str, rol: str,
                             mejor_similitud: float | None = None) -> None:
    """
    Una pregunta que el corpus no cubre es la mejor pista de que documentacion
    falta. Se guarda la PREGUNTA, nunca la respuesta ni datos de cliente.

    'mejor_similitud' es cuanto se acerco lo mas parecido que habia. Distingue
    "no hay nada de este tema" (0.1) de "hay algo casi util y el umbral esta
    demasiado alto" (0.34 con umbral 0.35), que son dos problemas distintos:
    uno se arregla escribiendo documentacion y el otro ajustando un numero.

    Ademas se cuenta cuantos fragmentos podia VER este rol (ver
    contar_elegibles): un cero ahi significa que el fallo no fue de
    recuperacion sino de permisos, y ninguna cantidad de calibracion lo
    arreglaria. Es la distincion que faltaba cuando 103 preguntas quedaron
    registradas con similitud NULL y se leyeron como un problema semantico.

    Nunca interrumpe la atencion: si esto falla, el usuario igual recibe su
    respuesta. Un registro para mejorar el corpus no puede dejar sin servicio a
    quien esta preguntando.
    """
    try:
        elegibles = contar_elegibles(tenant, rol)
    except Exception as e:
        print(f"[recuperacion] no se pudo contar fragmentos elegibles: {e}")
        elegibles = None

    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """insert into asistente.unanswered_queries
                     (organization_id, pregunta, rol_solicitante,
                      mejor_similitud, chunks_elegibles)
                   values (%s, %s, %s, %s, %s)""",
                (org, pregunta[:2000], rol, mejor_similitud, elegibles))
    except Exception as e:
        print(f"[recuperacion] no se pudo registrar la pregunta sin respuesta: {e}")


def bloque_de_contexto(fragmentos: list[Fragmento], citar_fuente: bool = True) -> str:
    """
    El texto que se le inyecta al modelo. Lleva instruccion explicita de no
    rellenar huecos: el prompt es guia y no garantia (PRD 7.4), pero cuesta
    poco y ayuda.

    Presenta lo recuperado como "lo mas parecido que hay", NO como la
    respuesta. La diferencia no es de estilo: superar 'umbral_similitud' es
    parecido semantico y nada mas. Con el encabezado anterior ("DOCUMENTACION
    RECUPERADA PARA ESTA PREGUNTA" + "Responde usando esta documentacion") se
    le afirmaba al modelo algo que en varios casos medidos era falso, y encima
    se le pedia que lo usara.

    'citar_fuente' separa dos publicos que necesitan lo opuesto: un
    colaborador (soporte, facturacion) SI quiere saber "esto sale de
    G-GO-06 v01" para poder verificarlo o citarlo el mismo. Un cliente_final
    no -- nombrar el codigo/version de un documento interno en medio de la
    charla suena a bot leyendo un manual, justo lo que rompe la idea de que
    hable como una persona del equipo (ver conversaciones con clientes:
    "la guia que uso para esto es MANUAL-001 v01" no es como habla alguien
    real). El motor decide esto por rol_cfg.orientado_a, nunca lo pide el
    modelo.
    """
    cuerpo = "\n\n".join(f.citar() for f in fragmentos)
    instruccion = (
        "Si responde, usala y menciona de que guia sale. "
        if citar_fuente else
        "Si responde, usala con naturalidad, como lo diria una persona del "
        "equipo. NUNCA menciones el nombre, codigo o version del documento "
        "interno de donde sale esto -- el cliente no tiene que notar que "
        "estas citando una guia. "
    )
    return (
        # El encabezado NO afirma que esto responda la pregunta, porque muchas
        # veces no lo hace. Lo que se recupero es lo mas PARECIDO que habia, y
        # parecido no es lo mismo que respuesta: medido el 21/08/2026, "cuanto
        # cuesta el plan mas caro" trajo a 0.488 un documento que no tiene un
        # solo precio, y "cual es el saldo de la cedula X" trajo el instructivo
        # de tickets a 0.411. El encabezado anterior decia "DOCUMENTACION
        # RECUPERADA PARA ESTA PREGUNTA" y arrancaba con "Responde usando esta
        # documentacion" -- o sea, le afirmaba al modelo algo falso y le pedia
        # que lo usara.
        #
        # No se puede filtrar por score: los falsos positivos (0.367 a 0.488)
        # se superponen con las consultas legitimas (0.426 a 0.440). Un umbral
        # que corte los unos corta las otras. Por eso la decision se le deja al
        # modelo, que a diferencia del umbral SI puede leer el fragmento y ver
        # si contiene lo que se pregunto.
        "LO MAS PARECIDO QUE HAY EN LA DOCUMENTACION INTERNA (puede no "
        "responder la pregunta):\n\n"
        f"{cuerpo}\n\n"
        "Primero fijate si esto de verdad responde lo que te preguntaron. "
        f"{instruccion}"
        "Si NO responde, ignoralo y segui como si no lo hubieras recibido: "
        "usa tus herramientas si el dato es de un sistema (un saldo, un "
        "precio, el estado de un equipo, cuantos clientes hay), o deci que "
        "no lo tenes. Nunca estires un fragmento parecido para que parezca "
        "una respuesta, ni cites una guia que en realidad no dice lo que "
        "estas afirmando.\n\n"
        "Si responde solo en parte, di que parte falta en vez de "
        "completarla por tu cuenta.\n\n"
        "Esta busqueda se repite en CADA mensaje del cliente, asi que puede "
        "traer un fragmento distinto al de un turno anterior -- eso no "
        "significa que el caso cambio. Si ya venias siguiendo algo mas "
        "especifico en esta conversacion (ej. un canal puntual, un TV en "
        "particular, una validacion ya hecha), usa esto para COMPLEMENTAR "
        "ese caso, no para abandonarlo ni reiniciar la conversacion de cero "
        "con preguntas que ya se respondieron. Y si lo que cuenta el "
        "cliente ahora es mas amplio que el caso original (ej. paso de 'un "
        "canal' a 'ningun canal'), decilo EXPLICITAMENTE conectando con lo "
        "anterior antes de las preguntas nuevas (ej. 'ahi cambia el "
        "panorama del canal de La Estrella que me contabas, esto ya es mas "
        "general') -- nunca respondas como si el mensaje anterior no "
        "hubiera existido."
    )
