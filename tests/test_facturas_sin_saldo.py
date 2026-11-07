# -*- coding: utf-8 -*-
"""
================================================================================
 EL AGENTE DE FACTURACION NO LEE UN 'saldo' DE FACTURA QUE VALE SIEMPRE 0.00
================================================================================

Por que existe
--------------
07/11/2026: el agente de cobro de clientes dijo «saldo 0.00» a una persona con una
factura pendiente de 69.900. El 'saldo' que WispHub devuelve en Rapilink es una
constante (0.00 en todas las facturas medidas), y un 0.00 que el modelo lee es un
«no debe nada» dicho a quien si debe. Ahi se corrigio el agente de clientes; esto
cierra lo mismo para el agente de facturacion INTERNO, que lo veia en cada factura.

Que se afirma (el EFECTO, no la presencia del mecanismo)
--------------------------------------------------------
  1. Lo que el rol 'facturacion' VE de una factura real con saldo no trae 'saldo',
     y si trae lo que si dice cuanto es (total, estado, vencimiento).
  2. El script que lo aplica a la base lo quita de la lista que la base YA tiene,
     una sola vez, sin tocar fichas, 'registrar_pago' ni otros roles.

Que NO se toco, a proposito
---------------------------
  - El 'saldo' de la FICHA del cliente (soporte, facturacion, supervisor_noc):
    decision pendiente aparte.
  - 'total_cobrado' de 'registrar_pago': es la respuesta de un pago real, no un
    campo de la factura.

Uso:  py -3.13 tests/test_facturas_sin_saldo.py
================================================================================
"""
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for var, valor in (("DBHOST", "localhost"), ("DBPORT", "5432"), ("DBNAME", "postgres"),
                   ("DBUSER", "postgres"), ("DBPASSWORD", "x")):
    os.environ.setdefault(var, valor)

import yaml                                                          # noqa: E402

from cli import aplicar_estado_de_cuenta as A                        # noqa: E402
from nucleo.config.schema import TenantConfig                        # noqa: E402
from nucleo.seguridad import listas_blancas                          # noqa: E402

FALLOS = []


def afirmar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        FALLOS.append(que)


RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(RAIZ, "tenants", "rapilink.config.yaml"), encoding="utf-8") as f:
    DOC = yaml.safe_load(f)
CONFIG = TenantConfig.model_validate(DOC)
FACTURACION = CONFIG.roles["facturacion"]

# Lo que WispHub devuelve de una factura PENDIENTE de Rapilink: saldo en 0.00.
FACTURA = {"id_factura": 900, "estado": "Pendiente de Pago", "total": "69900.00", "saldo": "0.00",
           "fecha_emision": "2026-11-01", "fecha_vencimiento": "2026-11-08", "fecha_pago": "2026-11-08",
           "total_cobrado": "69900.00"}
DETALLE = {**FACTURA, "folio": "F-1", "tipo": "Internet", "sub_total": "69900.00", "descuento": "0.00",
           "cliente": {"nombre": "Ana Perez", "cedula": "1", "email": "a@x.co"}, "articulos": []}

print("=" * 72)
print(" FACTURAS SIN 'saldo' PARA EL AGENTE DE FACTURACION")
print("=" * 72)

print("\n§1  LO QUE EL ROL VE DE UNA FACTURA REAL")
vista = listas_blancas.filtrar_campos(FACTURACION, "consultar_facturas", {"results": [FACTURA], "count": 1})
fila = vista["resultados"][0]
afirmar("saldo" not in fila, f"la lista de facturas NO trae 'saldo' ({sorted(fila)})")
afirmar(fila.get("total") == "69900.00" and fila.get("estado") == "Pendiente de Pago"
        and fila.get("fecha_vencimiento") == "2026-11-08",
        "pero si lo que dice cuanto se debe y de cuando: total, estado y vencimiento")
afirmar("total_cobrado" not in fila, "'total_cobrado' tampoco llega por la lista de facturas")
vista = listas_blancas.filtrar_campos(FACTURACION, "consultar_factura_detalle", DETALLE)
afirmar("saldo" not in vista, f"el detalle de una factura NO trae 'saldo' ({sorted(vista)})")
afirmar(vista.get("total") == "69900.00" and vista.get("cliente", {}).get("nombre") == "Ana Perez"
        and "cedula" not in vista.get("cliente", {}),
        "el detalle conserva el total y solo el nombre del cliente (sin cedula ni email)")

print("\n§2  LO QUE NO SE TOCO")
afirmar("saldo" in CONFIG.roles["soporte"].campos_permitidos["consultar_cliente"],
        "la FICHA de soporte sigue igual (decision pendiente aparte)")
afirmar("saldo" in FACTURACION.campos_permitidos["consultar_cliente"],
        "la FICHA de facturacion sigue igual")
afirmar("total_cobrado" in FACTURACION.campos_permitidos["registrar_pago"],
        "'registrar_pago' sigue devolviendo 'total_cobrado': es un pago real, no un campo de factura")

print("\n§3  EL SCRIPT LO APLICA A LA BASE")
# La base de ANTES: las listas con 'saldo' (y una lista que la base tiene distinta de la del repo).
base = copy.deepcopy(DOC)
base["roles"]["facturacion"]["campos_permitidos"]["consultar_facturas"] = [
    "id_factura", "estado", "total", "saldo", "campo_que_solo_tiene_la_base"]
base["roles"]["facturacion"]["campos_permitidos"]["consultar_factura_detalle"] = [
    "id_factura", "saldo", "total"]
base["roles"]["soporte"]["campos_permitidos"]["consultar_facturas"] = ["id_factura", "saldo"]
herr, campos = A.semilla("rapilink")
avisos = []
A.mutar(base, herr, campos, avisos)
cp = base["roles"]["facturacion"]["campos_permitidos"]
afirmar("saldo" not in cp["consultar_facturas"] and "saldo" not in cp["consultar_factura_detalle"],
        "quita 'saldo' de las dos herramientas de facturas")
afirmar("campo_que_solo_tiene_la_base" in cp["consultar_facturas"],
        "conserva lo que la base tenia y el repo no (no la pisa con la lista del repo)")
afirmar("saldo" in base["roles"]["soporte"]["campos_permitidos"]["consultar_facturas"],
        "no toca a otros roles")
afirmar(any("sin 'saldo'" in a for a in avisos), "lo avisa")
avisos2 = []
antes = copy.deepcopy(base)
A.mutar(base, herr, campos, avisos2)
afirmar(base == antes, "una segunda pasada no cambia nada (idempotente)")
afirmar(any("ya sin 'saldo'" in a for a in avisos2), "y dice que ya estaba")

print()
if FALLOS:
    print(f"  {len(FALLOS)} FALLA(S):")
    for f in FALLOS:
        print(f"   - {f}")
    sys.exit(1)
print("  Todo en orden.")
