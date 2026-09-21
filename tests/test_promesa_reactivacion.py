# -*- coding: utf-8 -*-
"""
================================================================================
 Promesa de pago CON reactivacion  --  la politica decide, no el modelo
================================================================================

    py -3.13 tests/test_promesa_reactivacion.py

Sin red y sin base: la politica es una funcion pura y por eso se puede probar
entera. Lo que toca WispHub se prueba aparte, con dobles.

LO QUE SE AFIRMA
  1. cada guarda, por separado, y que el MOTIVO que sale sea el correcto --
     no alcanza con "no elegible": quien lo lea tiene que saber por que;
  2. que "no se pudo leer" NUNCA caiga del lado de "elegible";
  3. que el modelo no pueda elegir entre promesa simple y reactivacion;
  4. que el resumen que ve quien aprueba nombre LOS DOS efectos;
  5. que un 2xx de WispHub no se confunda con "el servicio esta activo".
================================================================================
"""

from __future__ import annotations

import sys
from datetime import date
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

from nucleo.config.schema import PromesasPago, TenantConfig       # noqa: E402
from nucleo.facturacion import promesas                           # noqa: E402

HOY = date(2026, 9, 21)
POLITICA = PromesasPago(dias_maximos_promesa=15, monto_maximo_promesa=200000,
                        dias_entre_promesas=30)


def hechos(**cambios):
    """Un caso que SI es elegible. Cada prueba rompe una cosa."""
    base = {
        "cliente": {"estado": "Suspendido"},
        "facturas": [{"id_factura": 147121, "estado": "Pendiente de Pago",
                      "fecha_vencimiento": "2026-09-10", "total": 69900.0}],
        "fecha_limite": "2026-10-01",
        "promesa_previa": None,
    }
    base.update(cambios)
    return base


def ver(**cambios):
    return promesas.evaluar(hechos(**cambios), POLITICA, hoy=HOY)


# =============================================================================
titulo("1. el caso que SI procede")
# =============================================================================
v = ver()
revisar(v.elegible and v.resultado == promesas.ELEGIBLE,
        f"suspendido + una factura vencida + plazo y monto en regla ({v.resultado})")
revisar(v.datos.get("id_factura") == 147121 and v.datos.get("dias_de_plazo") == 10,
        f"y deja los datos de la decision ({v.datos})",
        "Sin ellos, quien apruebe no sabe sobre que factura ni por cuantos dias.")


# =============================================================================
titulo("2. cada guarda, con su motivo")
# =============================================================================
CASOS = [
    ("activo -> no hay nada que reactivar", "no_esta_suspendido",
     {"cliente": {"estado": "Activo"}}),
    ("cancelado tampoco", "no_esta_suspendido",
     {"cliente": {"estado": "Cancelado"}}),
    ("sin facturas pendientes", "sin_factura_pendiente",
     {"facturas": [{"id_factura": 1, "estado": "Pagada",
                    "fecha_vencimiento": "2026-08-10", "total": 10.0}]}),
    ("dos pendientes = deuda acumulada", "varias_pendientes",
     {"facturas": [
         {"id_factura": 1, "estado": "Pendiente de Pago",
          "fecha_vencimiento": "2026-08-10", "total": 69900.0},
         {"id_factura": 2, "estado": "Pendiente de Pago",
          "fecha_vencimiento": "2026-09-10", "total": 69900.0}]}),
    ("la factura todavia no vencio", "factura_no_vencida",
     {"facturas": [{"id_factura": 1, "estado": "Pendiente de Pago",
                    "fecha_vencimiento": "2026-09-30", "total": 69900.0}]}),
    ("pide mas plazo del permitido", "plazo_excedido",
     {"fecha_limite": "2026-11-30"}),
    ("la fecha que pide ya paso", "fecha_limite_pasada",
     {"fecha_limite": "2026-09-01"}),
    ("el monto supera el tope", "monto_excedido",
     {"facturas": [{"id_factura": 1, "estado": "Pendiente de Pago",
                    "fecha_vencimiento": "2026-09-10", "total": 500000.0}]}),
    ("ya le registramos una promesa hace poco", "promesa_reciente",
     {"promesa_previa": "2026-09-10"}),
]
for etiqueta, motivo, cambios in CASOS:
    v = ver(**cambios)
    revisar(v.resultado == promesas.NO_ELEGIBLE and v.motivo == motivo,
            f"{etiqueta} -> {v.resultado}/{v.motivo}")
    revisar(bool(v.detalle),
            f"   y lo explica en castellano ({v.detalle[:60]!r})",
            "Un codigo sin explicacion obliga a quien lo lee a abrir el codigo.")

# Justo en el limite: 15 dias exactos SI entra, 16 no.
revisar(ver(fecha_limite="2026-10-06").elegible,
        "el plazo maximo exacto (15 dias) entra")
revisar(ver(fecha_limite="2026-10-07").motivo == "plazo_excedido",
        "y uno mas, no")
# Una promesa vieja no estorba.
revisar(ver(promesa_previa="2026-07-01").elegible,
        "una promesa de hace 82 dias no bloquea (el minimo es 30)")


# =============================================================================
titulo("3. lo que NO se pudo leer nunca cae del lado del 'si'")
# =============================================================================
NO_SE_PUDO = [
    ("el cliente no se pudo leer", "sin_cliente", {"cliente": None}),
    ("vino vacio: tampoco se pudo leer", "sin_cliente", {"cliente": {}}),
    # Distinto del anterior: el cliente SI vino, pero sin el campo que decide.
    # Merece su propio motivo -- "no encontre al cliente" y "lo encontre y no
    # trae estado" mandan a mirar lugares distintos.
    ("vino, pero sin el campo 'estado'", "sin_estado",
     {"cliente": {"id_servicio": 6555, "nombre": "PRUEBA TEMPORAL"}}),
    ("las facturas no se pudieron leer", "sin_facturas", {"facturas": None}),
    ("la fecha limite no se entiende", "sin_fecha_limite",
     {"fecha_limite": "el proximo martes"}),
    ("la factura no trae vencimiento legible", "sin_vencimiento",
     {"facturas": [{"id_factura": 1, "estado": "Pendiente de Pago",
                    "fecha_vencimiento": "", "total": 69900.0}]}),
    ("el total no es un numero", "sin_monto",
     {"facturas": [{"id_factura": 1, "estado": "Pendiente de Pago",
                    "fecha_vencimiento": "2026-09-10", "total": "n/d"}]}),
]
for etiqueta, motivo, cambios in NO_SE_PUDO:
    v = ver(**cambios)
    revisar(v.resultado == promesas.NO_SE_PUDO and v.motivo == motivo,
            f"{etiqueta} -> {v.resultado}/{v.motivo}")
    revisar(not v.elegible, f"   y NO es elegible ({etiqueta})")

# El caso fino: no es lo mismo "consulte y no hay" que "no pude consultar".
sin_historial = hechos()
del sin_historial["promesa_previa"]
v = promesas.evaluar(sin_historial, POLITICA, hoy=HOY)
revisar(v.resultado == promesas.NO_SE_PUDO and v.motivo == "sin_historial",
        f"historial AUSENTE -> no_se_pudo ({v.motivo})",
        "None dice 'consulte y no hay'; ausente dice 'no pude consultar'. Si "
        "se trataran igual, un fallo de la base pareceria un cliente limpio.")
revisar(ver(promesa_previa=None).elegible,
        "y con historial en None (consultado, sin promesas) si procede")


# =============================================================================
titulo("4. el catalogo: dos acciones, y el modelo no elige entre ellas")
# =============================================================================
config = TenantConfig.model_validate(
    yaml.safe_load((RAIZ / "tenants" / "rapilink.config.yaml").read_text(encoding="utf-8")))
por_nombre = {h.nombre: h for h in config.herramientas}

simple = por_nombre.get("agregar_promesa_pago")
doble = por_nombre.get("registrar_promesa_y_reactivar")
revisar(simple is not None and doble is not None,
        "existen las DOS herramientas, separadas")

if doble is not None:
    revisar(doble.argumentos_fijos.get("accion") == 1,
            f"la de reactivar manda accion=1 fija ({doble.argumentos_fijos.get('accion')!r})")
    revisar("accion" not in doble.filtros_verificados
            and "accion" not in doble.requeridos
            and "accion" not in doble.argumentos_sobrescribibles,
            "y el modelo no la ve por ninguna de las tres puertas")
    revisar(doble.aprobacion_humana is True,
            "exige aprobacion humana",
            "Mientras WispHub no permita leer promesas vigentes, la persona que "
            "aprueba es lo unico que cubre ese punto ciego.")
    revisar(doble.roles_permitidos == ["facturacion"],
            f"y es interna, no del cliente final ({doble.roles_permitidos})")
    bajo = (doble.plantilla_resumen or "").lower()
    revisar("promesa" in bajo and ("reactiva" in bajo or "reactivar" in bajo),
            f"su resumen nombra LOS DOS efectos ({doble.plantilla_resumen!r})")

if simple is not None:
    revisar(simple.argumentos_fijos.get("accion") == 0,
            "y la simple sigue en accion=0")
    revisar("no reactiva" in (simple.plantilla_resumen or "").lower(),
            "diciendo que NO reactiva")

# Ninguna de las dos deja el interruptor a la vista.
for h in (simple, doble):
    if h is None:
        continue
    revisar("activar_servicio" not in str(h.filtros_verificados),
            f"'{h.nombre}': el enum 0/1 no aparece en lo que ve el modelo")


# =============================================================================
titulo("5. la politica no se inventa: sin valores, no se ofrece")
# =============================================================================
vacia = PromesasPago()
revisar(sorted(vacia.faltan_valores()) == ["dias_entre_promesas",
                                           "dias_maximos_promesa",
                                           "monto_maximo_promesa"],
        f"una politica vacia declara lo que le falta ({vacia.faltan_valores()})",
        "Cuantos dias de gracia da un ISP es una decision comercial. La "
        "plataforma no la puede tomar por el.")
revisar(config.promesas_pago.faltan_valores(),
        "y Rapilink todavia no la cargo: la accion NO se puede ofrecer aun")
revisar(POLITICA.faltan_valores() == [],
        "con los tres valores puestos, la politica esta completa")
revisar(PromesasPago(dias_maximos_promesa=1, monto_maximo_promesa=0,
                     dias_entre_promesas=0).faltan_valores() == [],
        "monto 0 es 'sin tope', no 'falta'",
        "None es 'nadie lo decidio'; 0 es 'se decidio que no hay tope'.")
revisar(vacia.requiere_aprobacion_humana is True,
        "y la aprobacion humana viene en true por defecto")


# =============================================================================
titulo("6. el resumen de aprobacion")
# =============================================================================
texto = promesas.resumen_de_aprobacion(ver().datos)
bajo = texto.lower()
revisar("promesa" in bajo, f"nombra la promesa ({texto[:50]}...)")
revisar("reactivar" in bajo or "reactiva" in bajo, "y la REACTIVACION")
revisar("suspendido" in bajo,
        "dice que el servicio esta hoy suspendido",
        "Es el hecho que justifica la accion; sin el, quien aprueba no puede "
        "saber si corresponde.")
revisar("vuelve a suspender" in bajo or "suspender" in bajo,
        "y que WispHub lo vuelve a suspender si no paga",
        "Es lo que le pone techo al riesgo. Quien aprueba tiene que saberlo.")
revisar("147121" in texto and "2026-10-01" in texto,
        "con la factura y la fecha concretas, no genericas")


# =============================================================================
titulo("7. aceptado NO es reactivado")
# =============================================================================
# WispHub responde 201 al crear la promesa. Eso dice que ACEPTO el pedido, no
# que el servicio quedo activo. Son tres hechos distintos y el contrato exige
# no mezclarlos.
fuente = (RAIZ / "nucleo" / "facturacion" / "promesas.py").read_text(encoding="utf-8")
codigo = "\n".join(l for l in fuente.splitlines() if not l.strip().startswith("#"))
revisar("requests" not in codigo and "http" not in codigo.lower().replace("https://", ""),
        "la politica no habla con nadie: recibe hechos ya leidos",
        "Asi se puede probar entera sin red, y asi la decision no depende de "
        "que la API conteste rapido.")
revisar("201" not in codigo and "status_code" not in codigo,
        "y no mira codigos de estado HTTP en ningun lado",
        "Confirmar la reactivacion es releer el cliente, no leer un 2xx.")

print()
if fallos:
    print(f"  {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"    - {f}")
    sys.exit(1)
print("  [OK] La politica decide con hechos, y quien aprueba ve los dos efectos.")
