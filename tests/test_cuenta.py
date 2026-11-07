# -*- coding: utf-8 -*-
"""
================================================================================
 EL ESTADO DE CUENTA: CUANTO DEBE QUIEN ESTA EN LA CONVERSACION
================================================================================

    py -3.13 tests/test_cuenta.py

Nacio de una conversacion real (07/11/2026): un cliente con una factura
pendiente y el servicio suspendido recibio "tu saldo es 0.00 y tienes una
factura pendiente". La ficha trae un 'saldo' que no es lo que debe, y el
agente de cobro no tenia como obtener el monto.

LO QUE SE AFIRMA, por efecto y recorriendo la cadena real
(ficha -> usuario -> facturas -> suma), con el proveedor simulado:

  1. La cadena: el monto es la SUMA de las facturas pendientes, y se calcula en
     codigo. Un saldo 0.00 en la ficha NO produce un 0.00 en la respuesta.
  2. El modelo no pasa identificador: solo se usa el id_servicio de la sesion,
     y el USUARIO que va al filtro de facturas sale de la ficha de ESE cliente.
  3. FALLA CERRADO, las cuatro formas en que un filtro sin efecto devolveria el
     universo con cara de exito:
        - sin id_servicio de sesion: no se consulta nada;
        - la ficha sin usuario: el filtro iria vacio;
        - la ficha de otro (el proveedor ignoro el filtro): no se elige una;
        - mas facturas de las que una persona puede deber, o una a nombre de
          otro: no se suma.
  4. 'no se pudo' no es 'no debe nada': son dos respuestas distintas.
  5. La respuesta no lleva el usuario ni ids de factura.
  6. Los DOS despachos del motor llegan al ejecutor (medido por efecto).
================================================================================
"""
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for var, valor in (("DBHOST", "localhost"), ("DBPORT", "5432"), ("DBNAME", "postgres"),
                   ("DBUSER", "postgres"), ("DBPASSWORD", "x")):
    os.environ.setdefault(var, valor)

from nucleo.config.schema import Herramienta                        # noqa: E402
from nucleo.herramientas import cuenta as C                          # noqa: E402
from nucleo.modelo import motor                                      # noqa: E402

FALLOS = []


def afirmar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        FALLOS.append(que)


HOY = date(2026, 11, 7)
CUENTA = {"usuario": "usuario", "filtro": "cliente", "total": "total",
          "saldo": "saldo", "vencimiento": "fecha_vencimiento"}

FICHA = Herramienta(nombre="consultar_mi_servicio", descripcion="Ficha.", tipo="http",
                    solo_lectura=True, roles_permitidos=["facturacion_cliente"],
                    base_url="https://proveedor.example", endpoint="/api/clientes/",
                    metodo="GET", auth_ref="PROVEEDOR_API_KEY")
FACTURAS = Herramienta(
    nombre="consultar_facturas", descripcion="Facturas.", tipo="http",
    solo_lectura=True, roles_permitidos=["facturacion"],
    base_url="https://proveedor.example", endpoint="/api/facturas/", metodo="GET",
    auth_ref="PROVEEDOR_API_KEY",
    filtros_verificados={
        "cliente": {"param": "cliente", "tipo": "texto"},
        "estado": {"param": "estado", "tipo": "enum",
                   "valores": {"pendiente": 1, "pagada": 2}}})
CUENTA_H = Herramienta(
    nombre="consultar_mi_cuenta", descripcion="Estado de cuenta.", tipo="interno",
    solo_lectura=True, roles_permitidos=["facturacion_cliente"],
    calcula_estado_de_cuenta=True, resolver_cliente_con="consultar_mi_servicio",
    facturas_con="consultar_facturas", cuenta=CUENTA,
    inyectar_sesion={"id_servicio": "id_cliente"}, inyectados_obligatorios=["id_servicio"])
CATALOGO = [FICHA, FACTURAS, CUENTA_H]


class Proveedor:
    """Un proveedor simulado que RECUERDA lo que se le pidio."""

    def __init__(self, ficha, facturas):
        self.ficha, self.facturas, self.pedidos = ficha, facturas, []

    def __call__(self, herramienta, argumentos, tenant=None, variables_tenant=None):
        self.pedidos.append((herramienta.nombre, dict(argumentos)))
        return self.ficha if herramienta.nombre == "consultar_mi_servicio" else self.facturas


def correr(proveedor, id_servicio="5832"):
    real = C.ejecutor_http.ejecutar
    C.ejecutor_http.ejecutar = proveedor
    try:
        return C.estado_de_cuenta(CUENTA_H, {"id_servicio": id_servicio}, "t", {},
                                  catalogo=CATALOGO, hoy=HOY)
    finally:
        C.ejecutor_http.ejecutar = real


def ficha(**campos):
    return {"results": [{"id_servicio": "5832", "usuario": "ana-perez@isp",
                         "saldo": "0.00", **campos}]}


def factura(total, saldo="0.00", vence="2026-12-06", dueno=None):
    f = {"id_factura": 900, "estado": "pendiente", "total": total, "saldo": saldo,
         "fecha_vencimiento": vence}
    if dueno:
        f["cliente"] = dueno
    return f


print("=" * 72)
print(" EL ESTADO DE CUENTA")
print("=" * 72)

print("\n§1  LA CADENA: la suma, no el saldo de la ficha")
p = Proveedor(ficha(), {"results": [factura("60000.00"), factura("50000.00", vence="2026-10-01")]})
r = correr(p)
afirmar(r.get("disponible") is True and r["monto_pendiente"] == "110000.00",
        f"dos facturas de 60.000 y 50.000 suman 110.000 aunque la ficha diga saldo 0.00 ({r})")
afirmar(r["facturas_pendientes"] == 2, "cuenta las facturas")
afirmar(r["vencimiento_mas_antiguo"] == "2026-10-01", "la mas antigua es la de octubre")
afirmar(r["facturas_vencidas"] == 1, "una ya vencio a hoy (7/11), la de diciembre no")
afirmar(C.monto_de({"total": "60000.00", "saldo": "15000.00"}, "total", "saldo") == C.Decimal("15000.00"),
        "una factura con saldo parcial cuenta su saldo, no su total")

print("\n§2  EL MODELO NO PASA IDENTIFICADOR")
afirmar(p.pedidos[0] == ("consultar_mi_servicio", {"id_servicio": "5832"}),
        "la ficha se pide con el id de la SESION")
afirmar(p.pedidos[1] == ("consultar_facturas", {"cliente": "ana-perez@isp", "estado": 1}),
        "las facturas se piden con el usuario de ESA ficha y 'pendiente' sale de la config (1)")

print("\n§3  FALLA CERRADO")
p = Proveedor(ficha(), {"results": []})
r = correr(p, id_servicio="")
afirmar(r["disponible"] is False and not p.pedidos, "sin id de sesion no se consulta NADA")

p = Proveedor(ficha(usuario=""), {"results": [factura("1.00")]})
r = correr(p)
afirmar(r["disponible"] is False and len(p.pedidos) == 1,
        "ficha sin usuario: no se piden facturas (el filtro vacio es el universo)")

p = Proveedor({"results": [{"id_servicio": "111", "usuario": "otro@isp"},
                           {"id_servicio": "222", "usuario": "otro2@isp"}]}, {"results": []})
r = correr(p)
afirmar(r["disponible"] is False and len(p.pedidos) == 1,
        "el proveedor ignoro el filtro de la ficha y devolvio otros: no se elige 'la primera'")

p = Proveedor(ficha(), {"results": [factura("1000.00") for _ in range(C.MAXIMO_PENDIENTES_DE_UNA_PERSONA + 1)]})
r = correr(p)
afirmar(r["disponible"] is False and "monto_pendiente" not in r,
        "mas facturas pendientes de las que una persona puede deber: no se suma el universo")

p = Proveedor(ficha(), {"results": [factura("1000.00", dueno="ana-perez@isp"),
                                    factura("2000.00", dueno="otro@isp")]})
r = correr(p)
afirmar(r["disponible"] is False and "monto_pendiente" not in r,
        "una factura a nombre de otro cliente: no se suma")

p = Proveedor(ficha(), {"results": [factura("1000.00"), {"id_factura": 2, "total": None, "saldo": ""}]})
r = correr(p)
afirmar(r["disponible"] is False, "una factura sin monto no es una factura de cero")

print("\n§4  'NO SE PUDO' NO ES 'NO DEBE NADA'")
p = Proveedor(ficha(), {"results": []})
r = correr(p)
afirmar(r["disponible"] is True and r["facturas_pendientes"] == 0 and r["monto_pendiente"] == "0.00",
        "sin facturas pendientes: disponible, cero facturas, 0.00")


def _revienta(*a, **k):
    raise RuntimeError("proveedor caido")


real = C.ejecutor_http.ejecutar
C.ejecutor_http.ejecutar = _revienta
try:
    r = C.estado_de_cuenta(CUENTA_H, {"id_servicio": "5832"}, "t", {}, catalogo=CATALOGO, hoy=HOY)
finally:
    C.ejecutor_http.ejecutar = real
afirmar(r["disponible"] is False and "monto_pendiente" not in r,
        "con el proveedor caido NO hay cifra: 'no disponible' con motivo")

p = Proveedor(ficha(), {"results": [factura("5.00")], "next": "https://x/?page=2"})
afirmar(correr(p).get("completo") is False, "si hay otra pagina, no afirma que el total este completo")

print("\n§5  LO QUE NO SALE")
p = Proveedor(ficha(), {"results": [factura("60000.00")]})
r = correr(p)
salida = repr(r)
afirmar("ana-perez" not in salida and "900" not in salida,
        f"ni el usuario ni el id de una factura viajan al modelo ({sorted(r)})")

print("\n§6  EL DESPACHO DEL MODELO LLEGA AL EJECUTOR, Y UN SERVICIO NO PUEDE PEDIRLA")
CENTINELA = {"__centinela__": "llego"}


def falso(herramienta, argumentos, tenant=None, variables_tenant=None, **k):
    return CENTINELA


class _Id:
    slug = "t_prueba"


class _Cfg:
    identidad = _Id()
    variables_tenant = {}
    roles = {}


original = motor.ejecutor_cuenta.estado_de_cuenta
motor.ejecutor_cuenta.estado_de_cuenta = falso
try:
    por_modelo = motor._despacho_de_herramienta(CUENTA_H, {"id_servicio": "5832"}, "t_prueba", {})
finally:
    motor.ejecutor_cuenta.estado_de_cuenta = original
afirmar(por_modelo is CENTINELA, "el despacho del modelo llega al ejecutor")
try:
    motor.ejecutar_para_servicio(_Cfg(), CUENTA_H, {"id_servicio": "5832"})
    rechazo = None
except ValueError as e:
    rechazo = str(e)
afirmar(rechazo is not None and "invocable_por_servicio" in rechazo,
        "un servicio (sin sesion) NO puede pedir la cuenta de un cliente")

print("\n§7  EL SCHEMA NO DEJA ARMARLA SIN LA INYECCION DE SESION")
try:
    Herramienta(nombre="x", descripcion="x", tipo="interno", solo_lectura=True,
                roles_permitidos=["facturacion_cliente"], calcula_estado_de_cuenta=True,
                resolver_cliente_con="a", facturas_con="b", cuenta=CUENTA)
    rechazada = False
except Exception:                                                    # noqa: BLE001
    rechazada = True
afirmar(rechazada, "sin 'id_servicio' inyectado de la sesion, la configuracion se rechaza")

print()
if FALLOS:
    print(f"  {len(FALLOS)} FALLA(S):")
    for f in FALLOS:
        print(f"   - {f}")
    sys.exit(1)
print("  Todo en orden.")
