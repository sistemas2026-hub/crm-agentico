# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DE TIMEOUTS  --  ninguna llamada al modelo se cuelga para siempre
================================================================================

Por que existe
--------------
Bug real de produccion (21/08/2026). Un cliente conversando por el simulador
recibio "fetch failed" en mitad de una venta que venia funcionando bien. La
traza en base mostro algo desconcertante: la respuesta del asistente SI se
habia calculado y SI estaba guardada -- lo que nunca llego fue el HTTP de
vuelta al navegador.

La causa: atender_turno() (nucleo/canales/api.py) calcula la respuesta, la
persiste, y DESPUES -- todavia dentro del mismo request, antes de devolver
nada -- hace una SEGUNDA llamada al modelo para evaluar si corresponde
escalar. Ninguna llamada al modelo llevaba timeout: se usaba el default del
SDK de cada proveedor (minutos, o ninguno). Con el proveedor lento, el proxy
corto la conexion antes de que esa segunda llamada terminara, y el cliente
se quedo sin una respuesta que ya existia.

Lo que se fija aca
------------------
1. La funcion generica 'cliente.chat()' tiene un timeout por defecto ACOTADO
   -- que exista el parametro no alcanza, tiene que tener un valor sensato.
2. Los TRES llamadores secundarios (evaluar escalamiento, verificar
   agendamiento, auditar con el supervisor) piden TIMEOUT_SECUNDARIO y no el
   generoso por defecto. Son trabajo que el cliente NO esta esperando: si
   tardan, se abandonan y se reintentan en el turno siguiente. Este es el
   punto que de verdad cierra el bug, y por eso se verifica llamandolos de
   verdad (con el modelo interceptado) en vez de leer el codigo fuente.
3. Cada proveedor acepta 'timeout'. Sin esto, agregar un proveedor nuevo sin
   soporte de timeout reintroduce el bug en silencio para quien lo use.

No toca la red: 'cliente.chat' se sustituye por un espia que registra con que
timeout lo llamaron y devuelve una respuesta vacia.

Uso
---
    py -3.13 tests/test_timeouts_modelo.py
================================================================================
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config          # noqa: E402
from nucleo.modelo import cliente                # noqa: E402
from nucleo.seguimiento import agendamiento      # noqa: E402
from nucleo.seguimiento import escalamiento      # noqa: E402
from nucleo.seguimiento import supervisor        # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


class EspiaChat:
    """Sustituye a cliente.chat y registra con que timeout lo llamaron."""

    def __init__(self) -> None:
        self.timeout = None
        self.llamado = False

    def __call__(self, referencia_modelo, mensajes, tools=None,
                 temperatura=0.1, timeout=None):
        self.llamado = True
        self.timeout = timeout
        return cliente.Respuesta(contenido="", llamadas=[])


def con_espia(modulo, funcion, *args, **kwargs) -> EspiaChat:
    """Corre 'funcion' con el cliente del modelo interceptado en 'modulo'."""
    espia = EspiaChat()
    original = modulo.cliente.chat
    modulo.cliente.chat = espia
    try:
        funcion(*args, **kwargs)
    except Exception as e:
        # El llamador puede fallar despues de la llamada (la respuesta vacia
        # del espia no trae la funcion que espera) -- da igual: lo que se
        # mide es con que timeout se hizo la llamada, no que termine bien.
        print(f"         (siguio de largo tras la llamada: {type(e).__name__})")
    finally:
        modulo.cliente.chat = original
    return espia


print("=" * 70)
print(" TIMEOUTS DEL MODELO  --  nada se cuelga esperando al proveedor")
print("=" * 70)

# --- 1. el default generico esta acotado y es sensato --------------------
print("\ncliente.chat: timeout por defecto")

firma = inspect.signature(cliente.chat)
por_defecto = firma.parameters["timeout"].default
comprobar("timeout" in firma.parameters, "'chat()' acepta 'timeout'")
comprobar(isinstance(por_defecto, (int, float)) and por_defecto > 0,
          f"tiene un valor por defecto acotado ({por_defecto}s)")
comprobar(por_defecto <= 180,
          f"ese valor no es eterno ({por_defecto}s <= 180s)")
comprobar(0 < cliente.TIMEOUT_SECUNDARIO < por_defecto,
          f"TIMEOUT_SECUNDARIO ({cliente.TIMEOUT_SECUNDARIO}s) es MAS CORTO "
          f"que el de la respuesta al cliente ({por_defecto}s)")

# --- 2. cada proveedor lo acepta -----------------------------------------
print("\nproveedores: todos aceptan 'timeout'")

for nombre, spec in cliente.PROVEEDORES.items():
    clase = spec["clase"]
    parametros = inspect.signature(clase.chat).parameters
    comprobar("timeout" in parametros,
              f"'{nombre}' ({clase.__name__}) acepta 'timeout'")

# --- 3. el trabajo secundario no hace esperar al cliente ------------------
#  Es el punto que cierra el bug: estas tres llamadas ocurren DESPUES de que
#  la respuesta del cliente ya se calculo y guardo, pero ANTES de devolverle
#  el HTTP.
print("\ntrabajo secundario: pide TIMEOUT_SECUNDARIO, no el generoso")

config = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
historial = [
    {"role": "user", "content": "hola"},
    {"role": "assistant", "content": "hola, en que te ayudo?"},
]

espia = con_espia(escalamiento, escalamiento.evaluar,
                  config, "cliente_final", historial)
comprobar(espia.llamado, "escalamiento.evaluar() llama al modelo")
comprobar(espia.timeout == cliente.TIMEOUT_SECUNDARIO,
          f"escalamiento.evaluar() pide TIMEOUT_SECUNDARIO "
          f"(pidio {espia.timeout})")

# agendamiento.verificar() consulta el manual por RAG antes de llamar al
# modelo, y sin eso corta antes de llegar. Se sustituye la recuperacion por
# un fragmento de mentira -- lo que se mide es el timeout de la llamada, no
# de donde salio el manual.
class _FragmentoFalso:
    codigo, titulo, version = "X-00", "manual de prueba", "01"
    contenido = "paso 1: confirmar el equipo."

    def citar(self):
        return self.contenido


_recuperar_original = agendamiento.busqueda.recuperar
agendamiento.busqueda.recuperar = lambda *a, **k: ([_FragmentoFalso()], 1.0)
try:
    espia = con_espia(agendamiento, agendamiento.verificar,
                      config, "rapilink", "soporte_tecnico_cliente", historial)
finally:
    agendamiento.busqueda.recuperar = _recuperar_original

comprobar(espia.llamado, "agendamiento.verificar() llama al modelo")
comprobar(espia.timeout == cliente.TIMEOUT_SECUNDARIO,
          f"agendamiento.verificar() pide TIMEOUT_SECUNDARIO "
          f"(pidio {espia.timeout})")

espia = con_espia(supervisor, supervisor.revisar,
                  config, "cliente_final", "rapilink", "conv-de-prueba", historial)
if espia.llamado:
    comprobar(espia.timeout == cliente.TIMEOUT_SECUNDARIO,
              f"supervisor.revisar() pide TIMEOUT_SECUNDARIO "
              f"(pidio {espia.timeout})")
else:
    print("  [--]   supervisor.revisar() no llego al modelo sin base; "
          "no se puede medir aca")

print("\n" + "=" * 70)
if fallos:
    print(f" {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    raise SystemExit(1)
print(" Todo en orden: ninguna llamada al modelo puede colgarse.")
print("=" * 70)
