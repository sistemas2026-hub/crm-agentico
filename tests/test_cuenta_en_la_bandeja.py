# -*- coding: utf-8 -*-
"""
================================================================================
 GET /conversaciones/<id>/cuenta  --  lo que debe el cliente, en la Bandeja
================================================================================

10/11/2026. La pestaña Cliente mostraba el 'saldo' de la ficha del ISP, que NO
es lo que se debe (07/11/2026: saldo 0.00 con una factura pendiente). Esta ruta
le da a quien atiende el MISMO calculo que usa el agente de cobro.

Se afirma sobre el EFECTO, recorriendo el calculo real (cuenta.estado_de_cuenta)
y sustituyendo solo las dos llamadas al proveedor:

  - el cliente sale de la identidad de la conversacion, nunca del pedido;
  - la cifra es la suma de los totales de SUS facturas pendientes;
  - si el proveedor devuelve facturas de otro, no hay cifra (y se dice por que);
  - sin cliente identificado, sin herramienta o sin conexion: 'disponible'
    false con un motivo que la pantalla sabe leer, nunca un 500;
  - se prefiere la herramienta del cliente a la del colaborador.

Sin base ni red.

    py -3.13 tests/test_cuenta_en_la_bandeja.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                              # noqa: E402
from nucleo.herramientas import http as ejecutor_http       # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}" + (f" ({detalle})" if not condicion else ""))
    if not condicion:
        fallos.append(que)


CUENTA = {"usuario": "usuario", "filtro": "cliente", "total": "total", "saldo": "saldo",
          "vencimiento": "fecha_vencimiento", "link_de_pago": "LINK_DE_PAGO"}


def herramienta_cuenta(nombre, colaborador=False):
    return SimpleNamespace(nombre=nombre, tipo="interno", calcula_estado_de_cuenta=True,
                           cuenta_de_colaborador=colaborador,
                           resolver_cliente_con="ficha", facturas_con="facturas",
                           cuenta=CUENTA)


FICHA = SimpleNamespace(nombre="ficha", tipo="http", calcula_estado_de_cuenta=False)
FACTURAS = SimpleNamespace(
    nombre="facturas", tipo="http", calcula_estado_de_cuenta=False,
    filtros_verificados={"estado": SimpleNamespace(valores={"pendiente": "1"})})

estado = {"herramientas": [FICHA, FACTURAS, herramienta_cuenta("cuenta_cliente")],
          "id_cliente": "1234", "facturas": [], "falla": None}
pedidos: list[tuple[str, dict]] = []


def falso_ejecutar(herramienta, argumentos, tenant=None, variables_tenant=None, **kw):
    pedidos.append((herramienta.nombre, dict(argumentos)))
    if estado["falla"]:
        raise estado["falla"]
    if herramienta.nombre == "ficha":
        return {"results": [{"id_servicio": argumentos.get("id_servicio"), "usuario": "ana@isp"}]}
    return {"results": estado["facturas"], "next": None}


api._config_de = lambda tenant: SimpleNamespace(
    herramientas=estado["herramientas"],
    variables_tenant={"LINK_DE_PAGO": "https://pagos.ejemplo.test/x"},
    identidad=SimpleNamespace(zona_horaria="America/Bogota"))
api.persistencia.identidad_de_conversacion = (
    lambda tenant, cid: {"id_cliente": estado["id_cliente"]} if cid != "no-existe" else None)
ejecutor_http.ejecutar = falso_ejecutar
api._TOKEN_SERVICIO = None
http = api.app.test_client()


def pedir(cid="c-1", extra=""):
    pedidos.clear()
    return http.get(f"/conversaciones/{cid}/cuenta?tenant=empresa{extra}")


print("\nla cuenta del cliente de la conversacion")
estado["facturas"] = [
    {"cliente": {"usuario": "ana@isp"}, "total": "50000.00", "saldo": "0", "fecha_vencimiento": "2020-01-05"},
    {"cliente": {"usuario": "ana@isp"}, "total": "45000.00", "saldo": "0", "fecha_vencimiento": "2099-01-05"},
]
r = pedir(extra="&id_servicio=9999")
cuerpo = r.get_json()
comprobar(r.status_code == 200 and cuerpo.get("disponible") is True, "contesta con la cuenta", str(cuerpo))
comprobar(cuerpo.get("facturas_pendientes") == 2 and cuerpo.get("monto_pendiente") == "95000.00",
          "suma los totales de sus facturas pendientes, en el codigo", str(cuerpo))
comprobar(cuerpo.get("facturas_vencidas") == 1 and cuerpo.get("vencimiento_mas_antiguo") == "2020-01-05",
          "cuenta las vencidas y dice la mas antigua", str(cuerpo))
comprobar(cuerpo.get("link_de_pago") == "https://pagos.ejemplo.test/x",
          "y trae el link de pago de la empresa, porque hay deuda", str(cuerpo))
comprobar(pedidos and pedidos[0] == ("ficha", {"id_servicio": "1234"}),
          "el cliente sale de la conversacion, no de un parametro del pedido", str(pedidos))
comprobar(any(n == "facturas" and a.get("cliente") == "ana@isp" and a.get("estado") == "1"
              for n, a in pedidos),
          "y las facturas se piden por SU usuario y solo las pendientes", str(pedidos))

print("\nfalla cerrado")
estado["facturas"] = [{"cliente": {"usuario": "otro@isp"}, "total": "10.00", "saldo": "0",
                       "fecha_vencimiento": "2020-01-01"}]
cuerpo = pedir().get_json()
comprobar(cuerpo.get("disponible") is False and cuerpo.get("motivo") == "no_calculable"
          and "monto_pendiente" not in cuerpo,
          "con facturas de otro cliente no hay cifra", str(cuerpo))
comprobar("otro cliente" in (cuerpo.get("detalle") or ""), "y dice por que", str(cuerpo))

estado["facturas"] = []
cuerpo = pedir().get_json()
comprobar(cuerpo.get("disponible") is True and cuerpo.get("facturas_pendientes") == 0
          and "link_de_pago" not in cuerpo,
          "al dia es 'cero pendientes', distinto de 'no se pudo', y sin link", str(cuerpo))

estado["id_cliente"] = ""
r = pedir()
comprobar(r.status_code == 200 and r.get_json() == {"disponible": False, "motivo": "sin_identificar"}
          and not pedidos,
          "sin cliente identificado no se consulta nada", r.get_data(as_text=True)[:200])
estado["id_cliente"] = "1234"

estado["falla"] = ConnectionError("caido")
r = pedir()
comprobar(r.status_code == 200 and r.get_json().get("disponible") is False,
          "con el proveedor caido: no disponible, no un 500", r.get_data(as_text=True)[:200])
estado["falla"] = None

guardadas = estado["herramientas"]
estado["herramientas"] = [FICHA, FACTURAS]
comprobar(pedir().get_json() == {"disponible": False, "motivo": "sin_herramienta"},
          "una empresa sin la herramienta de cuenta: no disponible, con el motivo")
estado["herramientas"] = guardadas

comprobar(pedir("no-existe").status_code == 404, "una conversacion que no existe: 404")
comprobar(http.get("/conversaciones/c-1/cuenta").status_code == 400, "sin tenant: 400")

print("\ncual herramienta")
usadas: list[str] = []
original = api.ejecutor_cuenta.estado_de_cuenta
api.ejecutor_cuenta.estado_de_cuenta = (
    lambda h, *a, **k: usadas.append(h.nombre) or {"disponible": True, "facturas_pendientes": 0})
estado["herramientas"] = [FICHA, FACTURAS, herramienta_cuenta("de_colaborador", colaborador=True),
                          herramienta_cuenta("del_cliente")]
pedir()
comprobar(usadas == ["del_cliente"], "se prefiere la del cliente a la del colaborador", str(usadas))
api.ejecutor_cuenta.estado_de_cuenta = original

print()
if fallos:
    print(f"[FALLA] {len(fallos)} caso(s)")
    sys.exit(1)
print("[OK] La Bandeja ve la misma cuenta que el agente, y no la de otro.")
