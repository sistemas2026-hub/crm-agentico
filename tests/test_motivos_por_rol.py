# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DE MOTIVOS POR ROL  --  una venta no escala por un motivo de soporte
================================================================================

El caso, medido en produccion el 28/08/2026
-------------------------------------------
Un prospecto escribio tres mensajes: "hola", "quiero instalar", "barrio
centro". 'consultar_planes_venta' corrio bien y encontro cobertura, asi que la
respuesta de venta ya estaba escrita -- cobertura y planes.

El evaluador de escalada escalo igual, con motivo 'sin_datos_para_diagnosticar':
un motivo de soporte tecnico, en una conversacion donde no habia nada que
diagnosticar. Y como la escalada REEMPLAZA la respuesta (no se le suma), el
cliente nunca leyo sus planes. Leyo "Entiendo tu molestia. Te paso con un
compañero", sin haberse quejado de nada.

Queda la traza completa en la conversacion 8840fc37-1edb-4058-82ae-604e5a30beff.

Por que el prompt no alcanzaba
------------------------------
El evaluador ve el mismo menu de motivos en CADA turno, sin importar quien
esta hablando, y elige uno en cuanto la conversacion se le parece. Pedirle por
prompt que no use motivos ajenos a su rol es guia, no garantia (PRD 7.4).
Sacarselos del menu si lo es: no puede elegir lo que no ve.

Es el mismo criterio que ya aplicaba 'forzado.motivos_por_hecho' -- lo que se
agrega es el otro eje: no solo QUE motivos se pueden juzgar, sino cuales
tienen sentido para QUIEN esta hablando.

Lo que se fija aca
------------------
1. Un rol que declara sus motivos solo ve esos.
2. Un rol que no declara ninguno los ve todos (comportamiento de siempre).
3. El filtro por HECHO sigue aplicando encima del de rol -- son dos razones
   distintas y las dos tienen que valer.
4. Un motivo mal escrito en un rol rechaza la config, en vez de dejarlo con
   menos motivos de los que se creia.
5. En la config real, 'ventas' NO puede elegir motivos de diagnostico.

Sin base, sin red y sin modelo.

    py -3.13 tests/test_motivos_por_rol.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.config.schema import TenantConfig, cargar_config       # noqa: E402
from nucleo.seguimiento import escalamiento                        # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(("  [OK]   " if condicion else "  [FALLA] ") + que)
    if not condicion:
        fallos.append(que)


cfg = cargar_config("tenants/rapilink.config.yaml")

# --- 1 y 2 -----------------------------------------------------------------
print("\n[1] Un rol que declara sus motivos solo ve esos")


class RolFalso:
    def __init__(self, motivos):
        self.motivos_escalada = motivos


todos = escalamiento._motivos_a_juicio(cfg)
acotado = escalamiento._motivos_a_juicio(cfg, RolFalso(["solicitud_explicita"]))
comprobar(acotado == ["solicitud_explicita"], "el menu queda con lo declarado y nada mas")
comprobar(len(acotado) < len(todos), "y es mas chico que el menu completo")

print("\n[2] Un rol que no declara nada los ve todos")
comprobar(escalamiento._motivos_a_juicio(cfg, RolFalso([])) == todos,
          "lista vacia = comportamiento de siempre")
comprobar(escalamiento._motivos_a_juicio(cfg, None) == todos,
          "sin rol tampoco cambia nada")

# --- 3 ---------------------------------------------------------------------
print("\n[3] El filtro por HECHO sigue mandando encima del de rol")
# 'pedido_para_ejecutar' lo dispara una herramienta, no el juicio: aunque un
# rol lo declare, no puede volver al menu.
from nucleo.seguimiento import forzado                             # noqa: E402

por_hecho = forzado.motivos_por_hecho(cfg)
comprobar(bool(por_hecho), "el tenant tiene motivos que decide un hecho")
uno = sorted(por_hecho)[0]
comprobar(uno not in escalamiento._motivos_a_juicio(cfg, RolFalso([uno])),
          f"'{uno}' no vuelve al menu ni declarandolo en el rol")

# --- 4 ---------------------------------------------------------------------
print("\n[4] Un motivo mal escrito rechaza la config")
crudo = cfg.model_dump(mode="json")
crudo["roles"]["ventas"]["motivos_escalada"] = ["motivo_que_no_existe"]
try:
    TenantConfig(**crudo)
    comprobar(False, "deberia rechazar un motivo inexistente")
except ValueError as e:
    comprobar("motivo_que_no_existe" in str(e), "se rechaza y NOMBRA el motivo")

# --- 5 ---------------------------------------------------------------------
print("\n[5] La config real: ventas no puede escalar por diagnostico")
menu_ventas = escalamiento._motivos_a_juicio(cfg, cfg.roles["ventas"])
print("     menu de ventas:", menu_ventas)
for prohibido in ("sin_datos_para_diagnosticar", "visita_tecnica_requerida"):
    comprobar(prohibido not in menu_ventas,
              f"'{prohibido}' NO esta en el menu de ventas  <- el bug")
comprobar(bool(menu_ventas), "pero ventas conserva motivos con los que SI puede escalar")

# El rol que si diagnostica los conserva: el filtro no puede haberse comido lo
# que hace falta donde hace falta.
menu_soporte = escalamiento._motivos_a_juicio(cfg, cfg.roles["soporte_tecnico_cliente"])
comprobar("sin_datos_para_diagnosticar" in menu_soporte,
          "y soporte tecnico SI lo conserva")

print("\n" + "=" * 70)
if fallos:
    print(f" {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    raise SystemExit(1)
print(" Todo en orden: cada rol escala por motivos que existen en su mundo.")
print("=" * 70)

# --- 6 ---------------------------------------------------------------------
print("\n[6] Cada motivo le dice al cliente lo que le corresponde")
# El texto generico habla de una MOLESTIA, y sirve para los motivos que si son
# un problema. Usarlo para los demas desconcierta a quien no se quejo de nada:
# pedir hablar con alguien, o no haber podido confirmar la identidad, no son
# quejas. Se comprueba el TEXTO REAL que recibe el cliente, no la config.
from nucleo.canales.api import _mensaje_de_escalada                # noqa: E402

QUEJA = "molestia"
for motivo in ("solicitud_explicita", "duda_de_identidad",
               "sin_datos_para_diagnosticar", "visita_tecnica_requerida",
               "pedido_para_ejecutar"):
    if motivo not in cfg.escalamiento.activar_si:
        continue
    texto = (_mensaje_de_escalada(cfg, motivo) or "").lower()
    comprobar(bool(texto), f"'{motivo}' tiene un mensaje")
    comprobar(QUEJA not in texto,
              f"'{motivo}' NO le habla de una molestia al cliente")

# Y el generico sigue existiendo para los que SI son una queja: sacarlo
# dejaria sin mensaje a los motivos que de verdad lo necesitan.
comprobar(QUEJA in (_mensaje_de_escalada(cfg, "frustracion_detectada") or "").lower(),
          "pero 'frustracion_detectada' si conserva el texto de la queja")

print("\n" + "=" * 70)
if fallos:
    print(f" {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    raise SystemExit(1)
print(" Todo en orden: cada rol escala por motivos que existen en su mundo.")
print("=" * 70)
