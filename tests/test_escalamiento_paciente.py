# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DE LA VUELTA EXTRA ANTES DE ESCALAR
================================================================================

Por que existe
--------------
El 15/08/2026 un cliente escribio "el internet no sirve para una verga" en su
PRIMER reclamo. El modelo lo leyo como 'frustracion_detectada' y la
conversacion se fue a un humano ahi mismo: cero herramientas ejecutadas, caso
abierto en el CRM, y el cliente fuera del asistente antes de que se intentara
ningun diagnostico. En un ISP eso es casi todo el que se queda sin servicio --
el asistente pasaba de atender a filtrar llamadas.

'escalamiento.intentar_resolver_antes' (por tenant, ver
nucleo/config/schema.py) le da a esos motivos UNA vuelta mas. El techo de una
sola vuelta es tan importante como la vuelta misma: sin el, un cliente al que
no se le puede resolver nada queda dando vueltas con el bot para siempre, que
es justo lo que la escalada existe para evitar.

Por que aca y no en evaluacion/rapilink.casos.yaml
--------------------------------------------------
El corredor de casos dorados llama a nucleo/modelo/motor.py::responder, y la
escalada no vive ahi: vive en nucleo/canales/api.py, despues de que el modelo
ya contesto. Cubrirla con un caso dorado exigiria que el corredor atendiera el
turno completo, con base de datos y CRM de por medio. La decision se aislo en
una funcion pura para poder guardarla sin nada de eso.

Uso
---
    py -3.13 tests/test_escalamiento_paciente.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config                        # noqa: E402
from nucleo.config.schema import Escalamiento                   # noqa: E402
from nucleo.seguimiento.escalamiento import merece_un_intento   # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


class _Config:
    """Lo minimo que mira la funcion: su seccion de escalamiento."""
    def __init__(self, **kw):
        self.escalamiento = Escalamiento(**kw)


print("un motivo declarado se pospone una vez, y solo una")
cfg = _Config(activar_si=["frustracion_detectada", "solicitud_explicita"],
              intentar_resolver_antes=["frustracion_detectada"])

comprobar(merece_un_intento(cfg, "frustracion_detectada", False),
         "la primera vez, el asistente se queda e intenta resolverlo")
comprobar(not merece_un_intento(cfg, "frustracion_detectada", True),
         "la segunda vez escala sin discutir (el techo de una sola vuelta)")

print("\nlo que NUNCA se pospone")
comprobar(not merece_un_intento(cfg, "solicitud_explicita", False),
         "quien PIDE un humano no espera una vuelta, por calmado que suene")
comprobar(not merece_un_intento(cfg, "tres_fallos_seguidos", False),
         "un motivo fuera de la lista escala como siempre, a la primera")
comprobar(not merece_un_intento(cfg, "", False),
         "sin motivo no se pospone nada (fail-closed: ante la duda, escala)")

print("\npor defecto no cambia el comportamiento de nadie")
# Un tenant que no declara nada tiene que seguir escalando igual que antes:
# esto se agrego a una configuracion que ya estaba en produccion.
vacia = _Config(activar_si=["frustracion_detectada"])
comprobar(not merece_un_intento(vacia, "frustracion_detectada", False),
         "sin 'intentar_resolver_antes', se escala a la primera como siempre")

print("\nla configuracion real de Rapilink")
real = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")
comprobar("frustracion_detectada" in real.escalamiento.intentar_resolver_antes,
         "la frustracion se intenta resolver antes de escalar")
comprobar("solicitud_explicita" not in real.escalamiento.intentar_resolver_antes,
         "pedir un humano sigue siendo inmediato")
# El mensaje REEMPLAZA la respuesta del asistente (ver api.py), asi que si
# queda vacio el cliente se queda sin nada que leer justo cuando lo pasan a
# una persona.
comprobar(bool((real.escalamiento.mensaje or "").strip()),
         "hay un mensaje de traspaso: es lo unico que el cliente va a leer")
for declarado in real.escalamiento.intentar_resolver_antes:
    comprobar(declarado in real.escalamiento.activar_si,
             f"'{declarado}' es un motivo que de verdad escala (esta en activar_si)")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)

print("\n[OK] La vuelta extra se concede una vez, a quien corresponde.")
