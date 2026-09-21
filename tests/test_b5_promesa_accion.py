# -*- coding: utf-8 -*-
"""
================================================================================
 B5 -- 'agregar_promesa_pago' NO puede reactivar el servicio
================================================================================

    py -3.13 tests/test_b5_promesa_accion.py

Sin red, sin base. Lee el catalogo del tenant y resuelve los argumentos con el
MOTOR REAL, para afirmar sobre lo que la llamada recibiria -- no sobre lo que
el YAML parece decir.

POR QUE EXISTE
--------------
La API de WispHub acepta dos acciones en una promesa de pago:

    0  Registrar Promesa de Pago
    1  Registrar Promesa de Pago Y ACTIVAR SERVICIO

Hasta el 21/09/2026 'accion' estaba en 'requeridos' y en
'filtros_verificados': la elegia el MODELO. Y el panel de aprobacion muestra
unicamente 'resumen' (acciones.js), cuya plantilla decia "Promesa de pago de
la factura N para el D" -- sin nombrar la reactivacion. Es decir: una persona
podia autorizar que se le reconectara el internet a un cliente suspendido sin
que nada se lo dijera.

Reconectar es una decision comercial, no una de redaccion.

LO QUE SE AFIRMA
----------------
  1. el valor que RECIBE la llamada es 0, mande lo que mande el modelo;
  2. el modelo ni siquiera ve el parametro;
  3. el resumen que lee quien aprueba nombra el efecto y niega el otro;
  4. ninguna otra herramienta del catalogo puede mandar accion=1.
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}", flush=True)
    if not condicion:
        fallos.append(que)
        if porque:
            print(f"          {porque}", flush=True)


def titulo(t):
    print(f"\n{'=' * 76}\n  {t}\n{'=' * 76}", flush=True)


import yaml                                                       # noqa: E402

from nucleo.config.schema import TenantConfig                     # noqa: E402
from nucleo.modelo import motor                                   # noqa: E402

RUTA = RAIZ / "tenants" / "rapilink.config.yaml"
config = TenantConfig.model_validate(yaml.safe_load(RUTA.read_text(encoding="utf-8")))
PROMESA = next((h for h in config.herramientas
                if h.nombre == "agregar_promesa_pago"), None)

if PROMESA is None:
    print("  [FALLA] no existe 'agregar_promesa_pago' en el catalogo")
    raise SystemExit(1)

ACTIVA_SERVICIO = 1
SOLO_REGISTRA = 0


# =============================================================================
titulo("1. el valor que recibe la LLAMADA, no el que manda el modelo")
# =============================================================================
# _resolver_argumentos es el que arma los argumentos reales. Se lo llama con
# lo PEOR que el modelo podria proponer.
def resolver(propuesta: dict) -> dict:
    return motor._resolver_argumentos(PROMESA, None, propuesta)


for etiqueta, propuesta in (
        ("el modelo no manda accion", {"id_factura": "8231", "fecha_limite": "2026-10-01"}),
        ("el modelo manda la que activa",
         {"id_factura": "8231", "fecha_limite": "2026-10-01",
          "accion": "registrar_promesa_y_activar_servicio"}),
        ("el modelo manda el numero crudo",
         {"id_factura": "8231", "fecha_limite": "2026-10-01", "accion": 1}),
        ("el modelo manda '1' como texto",
         {"id_factura": "8231", "fecha_limite": "2026-10-01", "accion": "1"}),
        ("el modelo inventa un valor",
         {"id_factura": "8231", "fecha_limite": "2026-10-01", "accion": "reconectar_ya"}),
):
    args = resolver(propuesta)
    recibido = args.get("accion")
    revisar(recibido == SOLO_REGISTRA,
            f"{etiqueta} -> la llamada recibe accion={recibido!r}",
            "Los fijos pisan lo del modelo (motor.py: argumentos.update"
            "(herramienta.argumentos_fijos)). Si esto falla, el modelo decide "
            "si se reconecta a un cliente.")
    revisar(recibido != ACTIVA_SERVICIO,
            f"   y NUNCA {ACTIVA_SERVICIO} ({etiqueta})")

# Y los otros argumentos siguen llegando: fijar uno no puede romper el resto.
args = resolver({"id_factura": "8231", "fecha_limite": "2026-10-01",
                 "comentarios": "acordado por telefono"})
revisar(args.get("id_factura") == "8231" and args.get("fecha_limite") == "2026-10-01",
        "los argumentos que SI decide el modelo siguen llegando")
revisar(args.get("comentarios") == "acordado por telefono",
        "y el texto libre tambien")


# =============================================================================
titulo("2. el modelo ni siquiera ve el parametro")
# =============================================================================
# No alcanza con ignorar el valor: si el modelo viera la opcion
# 'registrar_promesa_y_activar_servicio' en su esquema, podria PROMETERLE al
# cliente que lo reconectan aunque la llamada saliera con 0. Mentirle al
# cliente es peor que mandar el valor equivocado.
revisar("accion" not in PROMESA.filtros_verificados,
        "'accion' no esta en 'filtros_verificados'")
revisar("accion" not in PROMESA.requeridos,
        "ni en 'requeridos'",
        "schema.py ya lo dice: un campo con valor fijo conocido va en "
        "'argumentos_fijos'; 'requeridos' es solo para lo que el modelo decide.")
revisar(PROMESA.argumentos_fijos.get("accion") == SOLO_REGISTRA,
        f"y esta fija en {SOLO_REGISTRA} ({PROMESA.argumentos_fijos.get('accion')!r})")
revisar("accion" not in PROMESA.argumentos_sobrescribibles,
        "tampoco la puede cambiar un llamador interno",
        "'sobrescribibles' es la otra puerta: no llega del modelo, pero si de "
        "codigo propio. Se cierra igual.")

esquema = str(PROMESA.filtros_verificados)
revisar("activar_servicio" not in esquema,
        "y la palabra 'activar_servicio' no aparece en lo que ve el modelo")


# =============================================================================
titulo("3. el resumen que lee quien aprueba")
# =============================================================================
# El panel de aprobacion muestra UNICAMENTE 'resumen'. Si el resumen calla un
# efecto, ese efecto se aprueba a ciegas.
resumen = PROMESA.plantilla_resumen or ""
revisar(bool(resumen), "la herramienta declara un resumen")
bajo = resumen.lower()
revisar("promesa de pago" in bajo,
        f"nombra lo que hace ({resumen!r})")
revisar("no reactiva" in bajo or "no activa" in bajo,
        "y NIEGA explicitamente la reactivacion",
        "Quien aprueba solo ve esta linea. Que no diga 'reactiva' no alcanza: "
        "tiene que decir que NO lo hace, porque la duda es razonable cuando se "
        "trata de un cliente suspendido.")

fuente_panel = (RAIZ / "django-crm" / "frontend" / "src" / "lib" /
                "conversaciones" / "acciones.js").read_text(encoding="utf-8")
revisar("resumen" in fuente_panel and "argumentos" not in fuente_panel,
        "el panel sigue mostrando solo el resumen (por eso el resumen importa)",
        "Si algun dia el panel mostrara los argumentos, esta prueba hay que "
        "repensarla -- no borrarla.")


# =============================================================================
titulo("4. ninguna OTRA herramienta puede activar el servicio asi")
# =============================================================================
culpables = []
for h in config.herramientas:
    if "promesa-pago" not in (h.endpoint or ""):
        continue
    if h.argumentos_fijos.get("accion") == ACTIVA_SERVICIO:
        culpables.append((h.nombre, "lo tiene fijo en 1"))
    if "accion" in h.filtros_verificados:
        culpables.append((h.nombre, "deja que el modelo elija 'accion'"))
revisar(not culpables,
        f"ninguna herramienta de promesa deja elegir 'accion' ({culpables})",
        "Si mañana se agrega la de activar servicio, va con su propio resumen "
        "y su propia aprobacion -- y esta prueba tiene que actualizarse a "
        "mano, que es justamente el punto.")

print()
if fallos:
    print(f"  {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"    - {f}")
    sys.exit(1)
print("  [OK] La promesa de pago registra una promesa. Nada mas.")
