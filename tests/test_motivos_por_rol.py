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
# El ejemplo era 'solicitud_explicita' y dejo de servir el 02/09/2026: ese
# motivo ya no lo elige el evaluador, lo decide el codigo (ver [7]). Se cambia
# por otro que SI se juzga leyendo la conversacion -- lo que este punto fija
# es el filtro por rol, no cual motivo se usa de ejemplo.
acotado = escalamiento._motivos_a_juicio(cfg, RolFalso(["duda_de_identidad"]))
comprobar(acotado == ["duda_de_identidad"], "el menu queda con lo declarado y nada mas")
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

# --- 7 ---------------------------------------------------------------------
print("\n[7] 'pidio una persona' salio del menu del evaluador")
# Desde el 02/09/2026 lo decide el codigo leyendo los mensajes del cliente
# (forzado.decidir_pedido_humano). Dejarselo tambien al evaluador es pedir dos
# veredictos para la misma pregunta, y el segundo tiene un costo: si lo elige
# mal, el candado de api.py cancela la escalada entera -- y si en el fondo
# queria escalar por OTRA razon, esa razon se pierde con el motivo.
PEDIR_HUMANO = cfg.escalamiento.motivo_pide_humano
comprobar(bool(PEDIR_HUMANO), "el tenant declara cual es ese motivo")
comprobar(PEDIR_HUMANO in cfg.escalamiento.activar_si,
          "sigue siendo un motivo valido del negocio: lo que cambia es quien "
          "lo elige, no que exista")
comprobar(PEDIR_HUMANO not in escalamiento._motivos_a_juicio(cfg),
          f"'{PEDIR_HUMANO}' NO esta en el menu del evaluador")
comprobar(PEDIR_HUMANO not in escalamiento._motivos_a_juicio(
              cfg, RolFalso([PEDIR_HUMANO])),
          "y no vuelve ni declarandolo en el rol, igual que los de hecho")
comprobar(PEDIR_HUMANO in forzado.motivos_que_no_elige_el_modelo(cfg),
          "el motor lo cuenta entre los que no elige el modelo")
comprobar(PEDIR_HUMANO not in forzado.motivos_por_hecho(cfg),
          "pero NO entre los de hecho: esos salen de la traza de herramientas, "
          "y api.py saca de ahi el resumen del caso -- pedir una persona no "
          "deja ninguna traza de herramienta")

# Lo que se saca es UNO. El evaluador tiene que conservar todo lo demas, o
# esto habria cambiado por que escala, no quien lo decide.
menu = escalamiento._motivos_a_juicio(cfg)
print("     menu del evaluador:", menu)
for otro in ("frustracion_detectada", "tres_fallos_seguidos",
             "duda_de_identidad", "sin_datos_para_diagnosticar",
             "visita_tecnica_requerida"):
    if otro in cfg.escalamiento.activar_si:
        comprobar(otro in menu, f"'{otro}' sigue disponible")
comprobar(set(cfg.escalamiento.activar_si) - set(menu)
          == forzado.motivos_que_no_elige_el_modelo(cfg),
          "no se perdio ningun otro motivo por el camino")

# Y el esquema que ve el modelo sigue siendo valido: un enum vacio o con algo
# que no es del negocio rompe la llamada entera, y ahi no escala nadie.
esquema = escalamiento._esquema_evaluacion(cfg, cfg.roles["cliente_final"])
opciones = esquema["function"]["parameters"]["properties"]["motivo"]["enum"]
comprobar(PEDIR_HUMANO not in opciones,
          "el esquema REAL que viaja al modelo tampoco lo ofrece")
comprobar(bool(opciones), "el enum no queda vacio")
comprobar(all(o in cfg.escalamiento.activar_si for o in opciones),
          "y todo lo que ofrece existe en activar_si")
comprobar(PEDIR_HUMANO not in str(esquema["function"]["parameters"]["properties"]["motivo"]
                                  ["description"]),
          "ni lo nombra en la descripcion, que seria ofrecerlo por la ventana")

# EL BORDE QUE JUSTIFICA MANTENER EL CANDADO DE api.py: un tenant cuyo unico
# motivo sea este se quedaria con el enum vacio, y un esquema invalido no deja
# escalar por NADA. Ahi el motivo vuelve al menu a proposito -- vale mas un
# evaluador impreciso que un evaluador roto-- y el candado es lo unico que
# sigue exigiendo evidencia.
solo_uno = cfg.model_copy(deep=True)
solo_uno.escalamiento.activar_si = [PEDIR_HUMANO]
comprobar(escalamiento._motivos_a_juicio(solo_uno) == [],
          "ahi el evaluador se queda sin nada que juzgar")
esquema_borde = escalamiento._esquema_evaluacion(solo_uno)
comprobar(esquema_borde["function"]["parameters"]["properties"]["motivo"]["enum"] == [PEDIR_HUMANO],
          "y el motivo vuelve al enum para no romper el esquema  <- por esto "
          "el candado de api.py sigue haciendo falta")

# La otra razon, y la mas fuerte: el enum es un PEDIDO al proveedor, no una
# garantia nuestra. evaluar() devuelve llamada.argumentos tal cual, sin
# comparar el motivo contra activar_si -- si el modelo contesta algo que no
# estaba en la lista, entra igual. El candado es lo que lo detiene.
import inspect                                                     # noqa: E402

fuente_evaluar = inspect.getsource(escalamiento.evaluar)
comprobar("return llamada.argumentos" in fuente_evaluar
          and "activar_si" not in fuente_evaluar.split("for llamada")[-1],
          "evaluar() no valida el motivo devuelto contra activar_si: el "
          "candado no es redundante")

print("\n" + "=" * 70)
if fallos:
    print(f" {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    raise SystemExit(1)
print(" Todo en orden: cada rol escala por motivos que existen en su mundo.")
print("=" * 70)
