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

# =============================================================================
#  TIMEOUTS  --  ninguna llamada al modelo puede colgarse para siempre
# =============================================================================
#  Hasta el 21/08/2026 NINGUNA llamada llevaba timeout: se usaba el default del
#  SDK de cada proveedor, que son varios minutos o directamente ninguno. Eso
#  produjo un fallo real y desconcertante en produccion -- el cliente veia
#  "fetch failed" en mitad de una conversacion que HABIA funcionado: la
#  respuesta ya estaba calculada y guardada en la base, pero atender_turno()
#  (nucleo/canales/api.py) todavia no habia devuelto el HTTP porque seguia
#  esperando una SEGUNDA llamada al modelo -- la evaluacion de escalamiento --
#  que no es parte de la respuesta del cliente. El proxy corto la conexion
#  antes de que esa segunda llamada terminara.
#
#  Por eso hay dos valores y no uno:
#
#    POR_DEFECTO   la llamada que genera la respuesta que el cliente espera.
#                  Generoso: cortarla es dejarlo sin respuesta.
#    SECUNDARIO    trabajo que NO forma parte de esa respuesta (evaluar si
#                  corresponde escalar, verificar agendamiento, auditar).
#                  Corto a proposito: si tarda, se abandona y se reintenta en
#                  el turno siguiente -- cuesta mucho menos que hacer esperar
#                  a alguien por algo que no pidio.
TIMEOUT_POR_DEFECTO = 90.0
TIMEOUT_SECUNDARIO = 20.0


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
        # Un cliente por timeout distinto: el timeout de Ollama se fija al
        # CONSTRUIR el cliente (va al httpx de abajo), no por llamada como en
        # los otros dos proveedores. Se cachean para no abrir un pool de
        # conexiones nuevo en cada turno.
        self._clientes: dict[float, Any] = {}

    def _cliente(self, timeout: float):
        if timeout not in self._clientes:
            self._clientes[timeout] = self._ollama.Client(timeout=timeout)
        return self._clientes[timeout]

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
             tools: list | None = None, temperatura: float = 0.1,
             timeout: float = TIMEOUT_POR_DEFECTO) -> Respuesta:
        t0 = time.monotonic()
        r = self._cliente(timeout).chat(
            model=modelo, messages=self._adaptar(mensajes),
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
             tools: list | None = None, temperatura: float = 0.1,
             timeout: float = TIMEOUT_POR_DEFECTO) -> Respuesta:
        t0 = time.monotonic()
        r = self._cli.chat.completions.create(
            model=modelo, messages=self._adaptar(mensajes),
            tools=tools or None, temperature=temperatura, timeout=timeout)
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


class ClienteAnthropic:
    """
    API de Anthropic (Claude). No habla el formato de OpenAI -- el prompt de
    sistema va aparte de 'messages', y las llamadas/resultados de herramienta
    son bloques de contenido ('tool_use'/'tool_result') en vez de la lista
    'tool_calls' suelta que usan Ollama y los proveedores compatibles con
    OpenAI. Por eso es una clase propia y no una entrada mas de
    ClienteCompatibleOpenAI: traduce el formato canonico aca adentro para que
    el resto del sistema (motor.py, escalamiento.py, supervisor.py) siga
    viendo la misma forma sin importar el proveedor.
    """

    def __init__(self, api_key_ref: str, nombre: str = "anthropic"):
        import anthropic                                 # import perezoso
        clave = os.environ.get(api_key_ref)
        if not clave:
            raise SystemExit(
                f"Falta la variable {api_key_ref} en el entorno.\n"
                f"La configuracion guarda el NOMBRE del secreto, no su valor: "
                f"agregalo al .env como  {api_key_ref}=...")
        self.nombre = nombre
        self._cli = anthropic.Anthropic(api_key=clave)

    @staticmethod
    def _adaptar(mensajes: list[dict]) -> tuple[str, list[dict]]:
        """
        Separa los mensajes 'system' (Anthropic los quiere aparte, no en
        'messages') y convierte los turnos 'tool' en bloques 'tool_result'
        dentro de un turno 'user' -- varios bloques juntos si se llamaron
        varias herramientas en el mismo turno, porque Anthropic rechaza
        'tool_result' sueltos en turnos 'user' separados.
        """
        sistema = []
        salida: list[dict] = []
        for m in mensajes:
            rol = m.get("role")
            if rol == "system":
                if (m.get("content") or "").strip():
                    sistema.append(m["content"])
                continue
            if rol == "tool":
                bloque = {"type": "tool_result", "tool_use_id": m["tool_call_id"],
                          "content": m.get("content") or ""}
                previo = salida[-1] if salida else None
                if (previo and previo["role"] == "user"
                        and isinstance(previo["content"], list) and previo["content"]
                        and previo["content"][0].get("type") == "tool_result"):
                    previo["content"].append(bloque)
                else:
                    salida.append({"role": "user", "content": [bloque]})
                continue
            if rol == "assistant" and m.get("tool_calls"):
                contenido: list[dict] = []
                if (m.get("content") or "").strip():
                    contenido.append({"type": "text", "text": m["content"]})
                for tc in m["tool_calls"]:
                    contenido.append({
                        "type": "tool_use", "id": tc["id"],
                        "name": tc["function"]["name"],
                        # Canonico: 'arguments' ya es un dict (ver Llamada.argumentos
                        # en motor.py); a diferencia de OpenAI, Anthropic lo quiere
                        # como objeto, no como texto JSON -- no hace falta convertir.
                        "input": tc["function"].get("arguments") or {},
                    })
                salida.append({"role": "assistant", "content": contenido})
                continue
            salida.append({"role": rol, "content": m.get("content") or ""})
        return "\n\n".join(sistema), salida

    @staticmethod
    def _herramientas(tools: list[dict]) -> list[dict]:
        """El catalogo interno describe herramientas en formato OpenAI
        ({'type': 'function', 'function': {...}}); Anthropic las quiere
        planas ({'name', 'description', 'input_schema'})."""
        return [{"name": t["function"]["name"],
                 "description": t["function"].get("description", ""),
                 "input_schema": t["function"].get(
                     "parameters", {"type": "object", "properties": {}})}
                for t in tools]

    def chat(self, modelo: str, mensajes: list[dict],
             tools: list | None = None, temperatura: float = 0.1,
             timeout: float = TIMEOUT_POR_DEFECTO) -> Respuesta:
        sistema, adaptados = self._adaptar(mensajes)
        argumentos: dict[str, Any] = {
            "model": modelo, "max_tokens": 8000, "messages": adaptados,
            "timeout": timeout}
        if sistema:
            argumentos["system"] = sistema
        if tools:
            argumentos["tools"] = self._herramientas(tools)
        # 'temperatura' no se reenvia: los modelos Opus 5+ la rechazan (400)
        # y esto es para el rol supervisor, que no necesita ajustarla -- solo
        # se acepta el parametro para que 'chat()' tenga la misma firma que
        # los demas proveedores.

        t0 = time.monotonic()
        r = self._cli.messages.create(**argumentos)
        transcurrido = time.monotonic() - t0

        texto = []
        llamadas = []
        for bloque in r.content:
            if bloque.type == "text":
                texto.append(bloque.text)
            elif bloque.type == "tool_use":
                llamadas.append(Llamada(bloque.name, bloque.input))

        return Respuesta(
            contenido="".join(texto),
            llamadas=llamadas,
            tokens_entrada=r.usage.input_tokens,
            tokens_salida=r.usage.output_tokens,
            # Claude no expone el pensamiento por API (se resume u omite);
            # no hay caracteres que comparar con el 'thinking' de Ollama.
            razonamiento_chars=0,
            segundos=transcurrido, modelo=modelo, proveedor=self.nombre)


# =============================================================================
#  CATALOGO
# =============================================================================
#  Solo endpoints publicos y nombres de variable. Ningun secreto.

PROVEEDORES: dict[str, dict[str, Any]] = {
    "ollama":    {"clase": ClienteOllama},
    "deepseek":  {"clase": ClienteCompatibleOpenAI,
                  "base_url": "https://api.deepseek.com",
                  "api_key_ref": "DEEPSEEK_API_KEY"},
    "qwen":      {"clase": ClienteCompatibleOpenAI,
                  "base_url": "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
                  "api_key_ref": "DASHSCOPE_API_KEY"},
    "glm":       {"clase": ClienteCompatibleOpenAI,
                  "base_url": "https://open.bigmodel.cn/api/paas/v4",
                  "api_key_ref": "GLM_API_KEY"},
    "kimi":      {"clase": ClienteCompatibleOpenAI,
                  "base_url": "https://api.moonshot.cn/v1",
                  "api_key_ref": "MOONSHOT_API_KEY"},
    "anthropic": {"clase": ClienteAnthropic,
                  "api_key_ref": "ANTHROPIC_API_KEY"},
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
         tools: list | None = None, temperatura: float = 0.1,
         timeout: float = TIMEOUT_POR_DEFECTO) -> Respuesta:
    """
    'timeout' en segundos, SIEMPRE acotado -- ver el bloque TIMEOUTS arriba.
    Quien haga trabajo secundario (que no sea la respuesta que el cliente
    esta esperando) deberia pasar TIMEOUT_SECUNDARIO.
    """
    proveedor, modelo = resolver(referencia_modelo)
    return obtener(proveedor).chat(modelo, mensajes, tools, temperatura, timeout)
