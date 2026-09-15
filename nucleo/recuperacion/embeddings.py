# -*- coding: utf-8 -*-
"""
================================================================================
 EMBEDDINGS  --  un solo lugar para vectorizar
================================================================================
Antes cada llamador (nucleo/recuperacion/busqueda.py, nucleo/ingesta/corpus.py,
cli/cargar_corpus.py) tenia su PROPIA copia de "como se llama al modelo de
embeddings", las tres contra Ollama local. Tres copias es tres lugares para
olvidarse de actualizar el dia que cambia el proveedor -- que es exactamente
lo que paso hoy: el VPS no tiene recursos de sobra para correr un modelo local
ademas de todo lo demas (el CRM, el motor, dos Supabase, Traefik), asi que se
pasa a una API.

MODELO Y DIMENSION
-------------------
text-embedding-3-large, ACORTADO a 1024 dimensiones con el parametro
'dimensions' de la API de OpenAI -- verificado contra la documentacion oficial
(agosto 2026): se puede recortar el vector sin que pierda sus propiedades
(Matryoshka); un 'large' recortado a 256 ya supera al modelo viejo
'ada-002' en 1536.

Se elige 1024 y no el nativo 3072 A PROPOSITO: la columna
asistente.document_chunks.embedding es vector(1024) desde que se creo
pensando en bge-m3. Acortar evita una migracion de esquema, encima de la
re-vectorizacion del corpus que el cambio de proveedor ya exige (ver
busqueda.py: "vectores de modelos distintos no son comparables, y la busqueda
no falla -- devuelve fragmentos peores, en silencio").

'large' y no 'small': el corpus es chico (106 fragmentos) -- la diferencia de
costo entre los dos es centavos al mes, no hay motivo para resignar calidad de
recuperacion por un ahorro que no se nota.

CLAVE
-----
OPENAI_API_KEY es de PLATAFORMA, no por tenant -- mismo criterio que
DEEPSEEK_API_KEY/ANTHROPIC_API_KEY en nucleo/modelo/cliente.py (a diferencia
de WISPHUB_API_KEY o los secretos de WhatsApp, que si son por tenant y pasan
por nucleo/seguridad/secretos.py). Se lee del entorno, nunca de la config ni
de la base.
================================================================================
"""

from __future__ import annotations

import os

MODELO = "text-embedding-3-large"
DIMENSIONES = 1024


def vectorizar(texto: str) -> list[float]:
    """Un texto -> un vector de DIMENSIONES numeros, via la API de OpenAI."""
    from openai import OpenAI                            # import perezoso

    clave = os.environ.get("OPENAI_API_KEY")
    if not clave:
        raise RuntimeError(
            "Falta OPENAI_API_KEY en el entorno -- agregalo al .env "
            "(o a las variables de Dokploy en produccion, servicio 'motor').")

    cliente = OpenAI(api_key=clave)
    try:
        r = cliente.embeddings.create(model=MODELO, input=texto, dimensions=DIMENSIONES)
    except Exception as e:
        raise RuntimeError(f"OpenAI rechazo el embedding ({MODELO}): {e}") from e
    return r.data[0].embedding
