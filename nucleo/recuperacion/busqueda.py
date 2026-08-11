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
(config.rag.modelo_embeddings). No es un detalle: vectores de modelos distintos
no son comparables, y la busqueda no falla -- devuelve fragmentos peores, en
silencio.

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


def vectorizar(pregunta: str, modelo: str) -> list[float]:
    import ollama                                    # import perezoso
    return ollama.embed(model=modelo, input=pregunta)["embeddings"][0]


def recuperar(config, tenant: str, pregunta: str) -> tuple[list[Fragmento], float | None]:
    """
    Devuelve (fragmentos que superan el umbral, mejor similitud vista).

    La consulta se hace SIN umbral y el filtro se aplica aca. Cuesta lo mismo
    -el orden y el limite los pone igual la base- y a cambio queda el dato de
    cuanto se acerco lo mejor que habia. Sin eso, "no encontre nada" es una
    respuesta sin diagnostico: no se distingue un tema que no esta documentado
    de un umbral mal calibrado.

    Lista vacia = el corpus no cubre eso. Es informacion, no un fallo: quien
    llama decide que hacer con ese silencio.
    """
    vector = vectorizar(pregunta, config.rag.modelo_embeddings)

    with sesion(tenant) as (cur, org):
        cur.execute(
            """select codigo, titulo, version, contenido, similitud
               from asistente.match_chunks(%s, %s::vector, %s, 0.0)""",
            (org, str(vector), config.rag.top_k))
        filas = cur.fetchall()

    if not filas:
        return [], None

    mejor = max(float(f["similitud"]) for f in filas)
    fragmentos = [
        Fragmento(codigo=f["codigo"] or "", titulo=f["titulo"] or "",
                  version=f["version"] or "", contenido=f["contenido"] or "",
                  similitud=float(f["similitud"]))
        for f in filas if float(f["similitud"]) >= config.rag.umbral_similitud
    ]
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

    Nunca interrumpe la atencion: si esto falla, el usuario igual recibe su
    respuesta. Un registro para mejorar el corpus no puede dejar sin servicio a
    quien esta preguntando.
    """
    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """insert into asistente.unanswered_queries
                     (organization_id, pregunta, rol_solicitante, mejor_similitud)
                   values (%s, %s, %s, %s)""",
                (org, pregunta[:2000], rol, mejor_similitud))
    except Exception as e:
        print(f"[recuperacion] no se pudo registrar la pregunta sin respuesta: {e}")


def bloque_de_contexto(fragmentos: list[Fragmento]) -> str:
    """
    El texto que se le inyecta al modelo. Lleva instruccion explicita de citar
    y de no rellenar huecos: el prompt es guia y no garantia (PRD 7.4), pero
    cuesta poco y ayuda.
    """
    cuerpo = "\n\n".join(f.citar() for f in fragmentos)
    return (
        "DOCUMENTACION INTERNA RECUPERADA PARA ESTA PREGUNTA:\n\n"
        f"{cuerpo}\n\n"
        "Responde usando esta documentacion y menciona de que guia sale. "
        "Si no alcanza para responder del todo, di que parte falta en vez de "
        "completarla por tu cuenta."
    )
