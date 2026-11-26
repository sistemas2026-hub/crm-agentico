# -*- coding: utf-8 -*-
"""
EL EQUIPO DE UN CLIENTE SIN SERIAL, BUSCADO POR LA MAC DE SU ROUTER (26/11/2026).

    py -3.13 tests/test_onu_por_mac.py

Dos partes:

  A. el buscador (nucleo/herramientas/onu_por_mac.py), sin red ni reloj real:
     lo que devuelve cada respuesta de la OLT, que respeta el cupo del
     proveedor (una cada 10 s, 100 por hora, un 429) y cuanto vale lo guardado;
  B. el contexto tecnico (nucleo/canales/api.py::contexto_tecnico) pasando por
     el codigo real y sustituyendo solo la salida a la red: un servicio sin
     serial pide la busqueda y no espera; cuando la OLT contesto, el equipo se
     mide con ese serial y queda marcado de donde salio; un serial cargado en
     el ISP no se busca por MAC.
"""
import os
import sys
from pathlib import Path
from types import SimpleNamespace

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
for var, valor in (("DBHOST", "localhost"), ("DBPORT", "5432"), ("DBNAME", "postgres"),
                   ("DBUSER", "postgres"), ("DBPASSWORD", "x")):
    os.environ.setdefault(var, valor)

import requests  # noqa: E402

from nucleo.herramientas import onu_por_mac as m  # noqa: E402

FALLOS = []


def afirmar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        FALLOS.append(que)


class Reloj:
    def __init__(self):
        self.t = 1000.0
        self.dormido = []

    def __call__(self):
        return self.t

    def dormir(self, s):
        self.dormido.append(s)
        self.t += s


def nuevo():
    r = Reloj()
    return m.Buscador(reloj=r, dormir=r.dormir), r


def respuestas(*cuerpos):
    """Una funcion 'consultar' que devuelve estos cuerpos en orden y anota."""
    llamadas = []
    pendientes = list(cuerpos)

    def consultar(mac, olt):
        llamadas.append((mac, olt))
        r = pendientes.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    return consultar, llamadas


def http_error(codigo, retry_after=None):
    r = requests.Response()
    r.status_code = codigo
    if retry_after is not None:
        r.headers["Retry-After"] = str(retry_after)
    return requests.HTTPError(f"{codigo}", response=r)


UNA = {"verified": True, "matches": [{"sn": "hwtca6fb5263", "olt_id": "3"}]}
CERO = {"verified": True, "matches": []}
DOS = {"verified": True, "matches": [{"sn": "A"}, {"sn": "B"}]}
MAC = "aa:bb:cc:dd:ee:ff"

# ==========================================================================
print("\nA1. la MAC se normaliza como la pide la OLT")
afirmar(m.mac_normalizada("AA-BB-CC-DD-EE-FF") == MAC, "con guiones y en mayusculas")
afirmar(m.mac_normalizada(" aabb.ccdd.eeff ") == MAC, "con puntos y espacios")
afirmar(m.mac_normalizada("aa:bb:cc") == "", "incompleta: vacia, no se adivina")
afirmar(m.mac_normalizada(None) == "", "sin MAC: vacia")

print("\nA2. una coincidencia da el serial; la primera vez esta pendiente")
b, r = nuevo()
afirmar(b.resultado("t", MAC) == ("", m.PENDIENTE), "antes de buscar: pendiente")
consultar, llamadas = respuestas(UNA)
afirmar(b.pedir("t", MAC, ["3", "4"], consultar), "se encola")
afirmar(not b.pedir("t", MAC, ["3", "4"], consultar), "pedirla dos veces no la encola dos veces")
b.procesar_uno()
afirmar(b.resultado("t", MAC) == ("HWTCA6FB5263", m.UNA), "el serial, en mayusculas")
afirmar(llamadas == [(MAC, "3")], "con una coincidencia en la primera OLT no pregunta la segunda")
afirmar(not b.pedir("t", MAC, ["3"], consultar), "con un resultado vigente no se vuelve a pedir")
afirmar(b.resultado("otra", MAC) == ("", m.PENDIENTE), "otra empresa no hereda el resultado")

print("\nA3. ninguna, varias y una OLT que no miro")
for cuerpos, esperado, que in (
        ((CERO, CERO), m.NINGUNA, "ninguna OLT la tiene: 'ninguna'"),
        ((DOS,), m.VARIAS, "dos ONU detras de la misma MAC: no se elige"),
        (({"verified": False, "matches": []},), m.SIN_RESPUESTA,
         "sin 'verified', cero coincidencias no prueba nada"),
        ((requests.ConnectionError("sin ruta"),), m.SIN_RESPUESTA, "un fallo de red"),
):
    b, r = nuevo()
    consultar, _ = respuestas(*cuerpos)
    b.pedir("t", MAC, ["3", "4"], consultar)
    b.procesar_uno()
    afirmar(b.resultado("t", MAC) == ("", esperado), que)

print("\nA4. el cupo del proveedor: una cada 10 s")
b, r = nuevo()
consultar, llamadas = respuestas(CERO, CERO)
b.pedir("t", MAC, ["3", "4"], consultar)
b.procesar_uno()
afirmar(len(llamadas) == 2 and r.dormido == [m.SEGUNDOS_ENTRE_LLAMADAS],
        "entre la OLT 3 y la 4 espera 11 s")

print("\nA5. el cupo del proveedor: 100 por hora")
b, r = nuevo()
for i in range(m.MAXIMO_POR_HORA):
    consultar, _ = respuestas(CERO)
    b.pedir("t", f"mac{i}", ["3"], consultar)
    b.procesar_uno()
antes = r.t
consultar, _ = respuestas(CERO)
b.pedir("t", "otra", ["3"], consultar)
b.procesar_uno()
afirmar(r.t - antes > 2000, "pasado el tope de la hora, espera a que se libere uno")

print("\nA6. un 429 frena a la empresa lo que pida el proveedor")
b, r = nuevo()
consultar, _ = respuestas(http_error(429, retry_after=300))
b.pedir("t", MAC, ["3"], consultar)
b.procesar_uno()
afirmar(b.resultado("t", MAC) == ("", m.SIN_RESPUESTA), "el 429 queda como sin respuesta")
consultar, _ = respuestas(UNA)
b.pedir("t", "otra", ["3"], consultar)
b.procesar_uno()
afirmar(r.dormido and r.dormido[-1] >= 299, "la consulta siguiente espera el Retry-After")

print("\nA7. cuanto vale lo guardado")
b, r = nuevo()
consultar, _ = respuestas(CERO)
b.pedir("t", MAC, ["3"], consultar)
b.procesar_uno()
r.t += m.SEGUNDOS_SIN_RESULTADO + 1
afirmar(b.resultado("t", MAC) == ("", m.PENDIENTE),
        "'ninguna' se vence a las tres horas: el equipo pudo estar apagado")
consultar, _ = respuestas(UNA)
b.pedir("t", MAC, ["3"], consultar)
b.procesar_uno()
r.t += m.SEGUNDOS_SIN_RESULTADO + 1
afirmar(b.resultado("t", MAC)[1] == m.UNA, "lo encontrado sigue valiendo pasadas tres horas")
r.t += m.SEGUNDOS_ENCONTRADA
afirmar(b.resultado("t", MAC)[1] == m.PENDIENTE, "y se vence al dia")

# ==========================================================================
#  B. el contexto tecnico
# ==========================================================================
from nucleo.canales import api  # noqa: E402

print("\nB. el contexto tecnico de un servicio sin serial")

config = SimpleNamespace(
    herramientas=[SimpleNamespace(nombre=n, auth_ref="SMARTOLT", auth_header="X-Token")
                  for n in api._HERRAMIENTAS_EQUIPO],
    variables_tenant={"SMARTOLT_SUBDOMINIO": "https://olt.example"}, zona_horaria="")
FICHA = {"nombre": "ANA MARIA PEREZ GOMEZ", "mac_cpe": "AA-BB-CC-DD-EE-FF"}
INVENTARIO = [{"sn": "HWTCA6FB5263", "name": "ANA MARIA PEREZ GOMEZ", "olt_id": "3"},
              {"sn": "OTRA", "name": "OTRO CLIENTE", "olt_id": "4"}]

originales = (api._ficha_cliente, api._inventario_onu, api._estado_equipo,
              api.onu_por_mac.buscador)
medidos = []
buscador, reloj = nuevo()
pedidos = []
_pedir = buscador.pedir


def pedir(tenant, mac, olts, consultar):
    pedidos.append((tenant, mac, tuple(olts)))
    return _pedir(tenant, mac, olts, consultar)


buscador.pedir = pedir
ficha_actual = {}
api._ficha_cliente = lambda c, i, t: dict(ficha_actual)
api._inventario_onu = lambda c, t: (api._onus_por_olt.__setitem__(t, (0, INVENTARIO))
                                    or INVENTARIO)
api._estado_equipo = lambda c, sn, t: medidos.append(sn) or {"onu_status": "Online"}
api.onu_por_mac.buscador = lambda: buscador
try:
    ficha_actual = dict(FICHA)
    e1 = api.contexto_tecnico(config, "t", {"id_servicio": "5574"})
    afirmar(e1.get("equipo_no_disponible") == api.SIN_ONU_VINCULADA
            and e1.get("busqueda_por_mac") == "pendiente",
            "la primera vez: sin equipo, con la busqueda pendiente")
    afirmar(pedidos == [("t", "aa:bb:cc:dd:ee:ff", ("3", "4"))],
            "se pidio la busqueda en las OLT que dice el inventario, sin esperarla")
    afirmar(not medidos, "y no se midio nada todavia")
    afirmar("mac_cpe" not in (e1.get("cliente") or {}),
            "la MAC no sale en la tarjeta del cliente")

    #  La OLT contesta (lo que haria el hilo de fondo).
    buscador._cola[0] = buscador._cola[0][:3] + (respuestas(UNA)[0],)
    buscador.procesar_uno()
    e2 = api.contexto_tecnico(config, "t", {"id_servicio": "5574"})
    afirmar(medidos == ["HWTCA6FB5263"], "la lectura siguiente mide el equipo con ese serial")
    afirmar(e2.get("sn_onu") == "HWTCA6FB5263" and e2.get("sn_onu_origen") == "mac",
            "y queda dicho que el serial salio de la MAC, no del ISP")
    afirmar((e2.get("equipo_por_mac") or {}).get("nombre_coincide") is True,
            "el nombre de esa ONU en la OLT coincide con el del cliente")
    afirmar("equipo_no_disponible" not in e2, "ya no dice que falta el equipo")

    ficha_actual = {"nombre": "SIN MAC", "mac_cpe": ""}
    e3 = api.contexto_tecnico(config, "t", {"id_servicio": "9"})
    afirmar(e3.get("busqueda_por_mac") == "sin_mac", "sin MAC en el ISP, se dice")

    medidos.clear()
    pedidos.clear()
    ficha_actual = {"nombre": "CON SERIAL", "sn_onu": "CARGADO1", "mac_cpe": "11:22:33:44:55:66"}
    e4 = api.contexto_tecnico(config, "t", {"id_servicio": "10"})
    afirmar(not pedidos and medidos == ["CARGADO1"] and "sn_onu_origen" not in e4,
            "con serial en el ISP no se busca por MAC: manda el serial cargado")
finally:
    (api._ficha_cliente, api._inventario_onu, api._estado_equipo,
     api.onu_por_mac.buscador) = originales

print()
if FALLOS:
    print(f"[FALLA] {len(FALLOS)} afirmacion(es)")
    sys.exit(1)
print("[OK] Sin serial, el equipo se busca por la MAC del router y se mide con lo encontrado.")
