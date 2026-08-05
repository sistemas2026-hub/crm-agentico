# -*- coding: utf-8 -*-
"""
================================================================================
 CLIENTE DE MODELO  -  local y API detras de la misma interfaz
================================================================================

Por que existe
--------------
El sistema tiene que poder mandar cada peticion a un modelo distinto SIN que el
motor sepa cual. Dos razones concretas:

  - Reparto por sensibilidad. El corpus documental y los informes no llevan un
    solo dato personal; una consulta de saldo si. Lo primero puede salir a una
    API, lo segundo no. La decision es por ROL y por CANAL, y va en la
    configuracion del tenant.

  - Reparto por latencia. Medido: el modelo local tarda 42.6 s por turno. Para
    un tecnico en un poste esperando por WhatsApp eso puede ser inaceptable, y
    la salida no deberia obligar a tocar codigo.

Que hace y que NO hace
----------------------
Normaliza la respuesta de ambos mundos a una sola forma, para que el banco de
pruebas y el motor no tengan ramas por proveedor. NO decide a donde va cada
peticion: eso lo resuelve la configuracion.

Sobre los secretos
------------------
La configuracion guarda el NOMBRE de la variable de entorno, nunca la clave.
Si el nombre no resuelve, se falla al construir el cliente y no en mitad de una
conversacion con un cliente delante.
================================================================================
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from typing import Any


# =============================================================================
#  RESPUESTA NORMALIZADA
# =============================================================================

@dataclass
class Llamada:
    """Una invocacion de herramienta que propuso el modelo."""
    nombre: str
    argumentos: dict


@dataclass
class Respuesta:
    contenido: str = ""
    llamadas: list[Llamada] = field(default_factory=list)
    # Metricas comparables entre proveedores. 'razonamiento' importa: medido en
    # local, el grueso de la latencia son tokens de razonamiento que se generan
    # y se descartan, y comparar modelos sin verlo lleva a conclusiones al reves.
    tokens_entrada: int = 0
    tokens_salida: int = 0
    razonamiento_chars: int = 0
    segundos: float = 0.0
    modelo: str = ""
    proveedor: str = ""

    @property
    def tok_s(self) -> float:
        return round(self.tokens_salida / self.segundos, 1) if self.segundos else 0.0


# =============================================================================
#  PROVEEDORES
# =============================================================================

# El formato CANONICO del historial es el de OpenAI: 'arguments' como cadena
# JSON, 'id' y 'type' en cada tool_call. Cada cliente lo adapta a lo que exige
# su proveedor.
#
# No es un capricho de estilo: Ollama exige que 'arguments' sea un DICCIONARIO
# y la API de OpenAI exige que sea una CADENA. La misma informacion con tipos
# incompatibles. Si esto no se absorbe aqui, cada llamador termina con una rama
# por proveedor — que es justo lo que esta capa existe para evitar.

def _args_a_dict(valor: Any) -> dict:
    if isinstance(valor, dict):
        return valor
    try:
        return json.loads(valor or "{}")
    except (ValueError, TypeError):
        return {}


def _args_a_texto(valor: Any) -> str:
    if isinstance(valor, str):
        return valor or "{}"
    return json.dumps(valor or {}, ensure_ascii=False)


class ClienteOllama:
    """Modelo local. Sin costo por token y sin que nada salga de la red."""

    nombre = "ollama"

    def __init__(self, **_):
        import ollama                                   # import perezoso
        self._ollama = ollama

    @staticmethod
    def _adaptar(mensajes: list[dict]) -> list[dict]:
        salida = []
        for m in mensajes:
            m = dict(m)
            # 'reasoning_content' es de los modelos de razonamiento por API;
            # Ollama no lo conoce y lo rechaza.
            m.pop("reasoning_content", None)
            if m.get("tool_calls"):
                m["tool_calls"] = [
                    {**tc, "function": {**tc["function"],
                                        "arguments": _args_a_dict(
                                            tc["function"].get("arguments"))}}
                    for tc in m["tool_calls"]]
            salida.append(m)
        return salida

    def chat(self, modelo: str, mensajes: list[dict],
             tools: list | None = None, temperatura: float = 0.1) -> Respuesta:
        t0 = time.monotonic()
        r = self._ollama.chat(model=modelo, messages=self._adaptar(mensajes),
                              tools=tools or None,
                              options={"temperature": temperatura})
        transcurrido = time.monotonic() - t0
        msg = r.get("message", {}) or {}

        llamadas = []
        for tc in (msg.get("tool_calls") or []):
            args = tc["function"]["arguments"]
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except ValueError:
                    args = {}
            llamadas.append(Llamada(tc["function"]["name"], args))

        return Respuesta(
            contenido=msg.get("content") or "",
            llamadas=llamadas,
            tokens_entrada=r.get("prompt_eval_count") or 0,
            tokens_salida=r.get("eval_count") or 0,
            razonamiento_chars=len(msg.get("thinking") or ""),
            segundos=transcurrido, modelo=modelo, proveedor=self.nombre)


class ClienteCompatibleOpenAI:
    """
    Cualquier API con el contrato de OpenAI: DeepSeek, Qwen, GLM, Kimi, Together.

    Se agrupan porque comparten formato: cambiar de uno a otro es cambiar
    'base_url' y el nombre del modelo, sin tocar codigo.
    """

    def __init__(self, base_url: str, api_key_ref: str, nombre: str = "api"):
        from openai import OpenAI                       # import perezoso
        clave = os.environ.get(api_key_ref)
        if not clave:
            raise SystemExit(
                f"Falta la variable {api_key_ref} en el entorno.\n"
                f"La configuracion guarda el NOMBRE del secreto, no su valor: "
                f"agregalo al .env como  {api_key_ref}=...")
        self.nombre = nombre
        self._cli = OpenAI(api_key=clave, base_url=base_url)

    @staticmethod
    def _adaptar(mensajes: list[dict]) -> list[dict]:
        salida = []
        for m in mensajes:
            m = dict(m)
            if m.get("tool_calls"):
                m["tool_calls"] = [
                    {"id": tc.get("id", "call_1"),
                     "type": tc.get("type", "function"),
                     "function": {"name": tc["function"]["name"],
                                  "arguments": _args_a_texto(
                                      tc["function"].get("arguments"))}}
                    for tc in m["tool_calls"]]
                # Los modelos de razonamiento EXIGEN que el razonamiento vuelva
                # en los turnos siguientes; sin el campo responden 400 y la
                # peticion no llega a ejecutarse.
                m.setdefault("reasoning_content", "")
            salida.append(m)
        return salida

    def chat(self, modelo: str, mensajes: list[dict],
             tools: list | None = None, temperatura: float = 0.1) -> Respuesta:
        t0 = time.monotonic()
        r = self._cli.chat.completions.create(
            model=modelo, messages=self._adaptar(mensajes),
            tools=tools or None, temperature=temperatura)
        transcurrido = time.monotonic() - t0
        msg = r.choices[0].message

        llamadas = []
        for tc in (msg.tool_calls or []):
            try:
                args = json.loads(tc.function.arguments or "{}")
            except ValueError:
                args = {}
            llamadas.append(Llamada(tc.function.name, args))

        uso = r.usage
        # Algunos modelos exponen los tokens de razonamiento aparte. Se traducen
        # a caracteres (~4 por token) para poder compararlos con el campo
        # 'thinking' que devuelve Ollama.
        razonamiento = 0
        detalle = getattr(uso, "completion_tokens_details", None)
        if detalle is not None:
            razonamiento = (getattr(detalle, "reasoning_tokens", 0) or 0) * 4

        return Respuesta(
            contenido=msg.content or "",
            llamadas=llamadas,
            tokens_entrada=getattr(uso, "prompt_tokens", 0) or 0,
            tokens_salida=getattr(uso, "completion_tokens", 0) or 0,
            razonamiento_chars=razonamiento,
            segundos=transcurrido, modelo=modelo, proveedor=self.nombre)


# =============================================================================
#  CATALOGO
# =============================================================================
#  Solo endpoints publicos y nombres de variable. Ningun secreto.

PROVEEDORES: dict[str, dict[str, Any]] = {
    "ollama":   {"clase": ClienteOllama},
    "deepseek": {"clase": ClienteCompatibleOpenAI,
                 "base_url": "https://api.deepseek.com",
                 "api_key_ref": "DEEPSEEK_API_KEY"},
    "qwen":     {"clase": ClienteCompatibleOpenAI,
                 "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                 "api_key_ref": "DASHSCOPE_API_KEY"},
    "glm":      {"clase": ClienteCompatibleOpenAI,
                 "base_url": "https://open.bigmodel.cn/api/paas/v4",
                 "api_key_ref": "GLM_API_KEY"},
    "kimi":     {"clase": ClienteCompatibleOpenAI,
                 "base_url": "https://api.moonshot.cn/v1",
                 "api_key_ref": "MOONSHOT_API_KEY"},
}

_cache: dict[str, Any] = {}


def obtener(proveedor: str):
    """Cliente del proveedor. Se cachea: abrir conexion en cada turno es tonto."""
    if proveedor in _cache:
        return _cache[proveedor]
    if proveedor not in PROVEEDORES:
        raise SystemExit(f"Proveedor desconocido: '{proveedor}'. "
                         f"Disponibles: {', '.join(PROVEEDORES)}")
    spec = dict(PROVEEDORES[proveedor])
    clase = spec.pop("clase")
    _cache[proveedor] = clase(nombre=proveedor, **spec) if spec else clase()
    return _cache[proveedor]


def resolver(referencia: str) -> tuple[str, str]:
    """
    'deepseek:deepseek-chat' -> ('deepseek', 'deepseek-chat')
    'qwen3:30b-a3b-q4_K_M'   -> ('ollama',   'qwen3:30b-a3b-q4_K_M')

    Sin prefijo de proveedor conocido se asume local. Es deliberado: si alguien
    escribe mal el nombre, la peticion se queda en casa en vez de irse a
    internet con datos de un cliente.
    """
    if ":" in referencia:
        posible, resto = referencia.split(":", 1)
        if posible in PROVEEDORES and posible != "ollama":
            return posible, resto
    return "ollama", referencia


def chat(referencia_modelo: str, mensajes: list[dict],
         tools: list | None = None, temperatura: float = 0.1) -> Respuesta:
    proveedor, modelo = resolver(referencia_modelo)
    return obtener(proveedor).chat(modelo, mensajes, tools, temperatura)
