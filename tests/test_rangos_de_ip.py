# -*- coding: utf-8 -*-
"""Los rangos de IP de cada servidor: se guardan limpios, se sugieren y se leen.

LO QUE ESTE ARCHIVO DEFIENDE  --  25/11/2026

* **Lo que se guarda es un /24 de verdad.** «172.16.9», «172.16.9.» y
  «172.16.9.0/24» quedan iguales; lo que no es un /24, o es de uso reservado
  (169.254, 127, 0, multicast), se rechaza y NO se guarda nada.
* **La sugerencia sale de los clientes de ESA zona**, con un minimo: un
  prefijo con un par de equipos mal cargados no es un pool.
* **La lectura cuenta por zona sin guardar nada del cliente**, y la ruta que
  la dispara la guarda.
* **La pantalla recibe conteos, nunca direcciones.**

No habla con ningun proveedor.

    MOTOR_SERVICE_TOKEN= python tests/test_rangos_de_ip.py
"""
from __future__ import annotations

import contextlib
import io
import os
import sys
import types
from pathlib import Path

os.environ["MOTOR_SERVICE_TOKEN"] = ""

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                     # noqa: E402
from nucleo.config import editor                                   # noqa: E402
from nucleo.config.schema import PoolDeIp                          # noqa: E402
from nucleo.herramientas import ocupacion_ip as oip                # noqa: E402

TENANT = "empresa-de-prueba"
cliente = api.app.test_client()
_fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(("  OK   " if condicion else "  FALLA ") + que)
    if not condicion:
        _fallos.append(que)


def seccion(titulo: str) -> None:
    print("\n" + titulo)
    print("-" * len(titulo))


@contextlib.contextmanager
def silencio():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        yield


# ---------------------------------------------------------------------------
seccion("1. el prefijo se escribe de varias formas y se guarda de una")
for crudo, esperado in (("172.16.9", "172.16.9."), ("172.16.9.", "172.16.9."),
                        ("172.16.9.0/24", "172.16.9."), ("172.16.9.0", "172.16.9."),
                        (" 10.0.1 ", "10.0.1."), ("010.000.001", "10.0.1."),
                        ("172.16", ""), ("172.16.9.5", ""), ("172.16.9.0/16", ""),
                        ("256.1.1", ""), ("abc", ""), ("", ""), (None, "")):
    afirmar(oip.normalizar_prefijo(crudo) == esperado,
            f"{crudo!r} -> {esperado!r} ({oip.normalizar_prefijo(crudo)!r})")

# ---------------------------------------------------------------------------
seccion("2. lo que se guarda: limpio, o nada")
limpios = editor.rangos_validos([
    {"zona_id": 20049, "zona_nombre": " CORTE 30 ", "prefijos": ["172.16.9", "172.16.9.", "172.16.10.0/24"]},
    {"zona_id": 32278, "prefijos": []}])
afirmar(limpios == [{"zona_id": 20049, "zona_nombre": "CORTE 30", "prefijos": ["172.16.9.", "172.16.10."]},
                    {"zona_id": 32278, "zona_nombre": "", "prefijos": []}],
        f"normalizados y sin repetidos; una zona sin rangos es valida: {limpios}")
afirmar(all(PoolDeIp(**p) for p in limpios), "y lo que sale lo acepta el esquema")

for malo, que in (
        ([{"zona_id": 1, "prefijos": ["169.254.1."]}], "link-local"),
        ([{"zona_id": 1, "prefijos": ["127.0.0."]}], "loopback"),
        ([{"zona_id": 1, "prefijos": ["0.1.2."]}], "la red cero"),
        ([{"zona_id": 1, "prefijos": ["224.0.0."]}], "multicast"),
        ([{"zona_id": 1, "prefijos": ["172.16"]}], "algo que no es un /24"),
        ([{"zona_id": 1, "prefijos": "172.16.9."}], "prefijos que no son lista"),
        ([{"zona_id": 1, "prefijos": ["1.1.1."] * 65}], "demasiados prefijos"),
        ([{"zona_id": True, "prefijos": []}], "zona booleana"),
        ([{"zona_id": 0, "prefijos": []}], "zona cero"),
        ([{"zona_id": "20049", "prefijos": []}], "zona como texto"),
        ([{"zona_id": 1, "prefijos": []}, {"zona_id": 1, "prefijos": []}], "zona repetida"),
        (["no soy un objeto"], "un servidor que no es un objeto"),
        ("nada", "una lista que no es lista")):
    try:
        editor.rangos_validos(malo)
        afirmar(False, f"se rechaza: {que}")
    except editor.ErrorEdicion as e:
        afirmar(True, f"se rechaza: {que} ({e})")

# ---------------------------------------------------------------------------
seccion("3. la sugerencia: los prefijos de ESA zona, con un minimo")
s = oip.sugeridos_por_zona({
    "20049": {"172.16.9.": 211, "172.16.10.": 120, "172.16.99.": 3, "169.254.7.": 40,
              "168.0.9.": 58},
    "20053": {"172.16.9.": 42},
    "32278": {"10.0.0.": 1}})
afirmar(s.get("20049") == [{"prefijo": "172.16.9.", "clientes": 211, "privado": True},
                           {"prefijo": "172.16.10.", "clientes": 120, "privado": True},
                           {"prefijo": "168.0.9.", "clientes": 58, "privado": False}],
        f"de mas a menos usado, sin el de 3 clientes ni el link-local: {s.get('20049')}")
afirmar([x["privado"] for x in s["20049"]] == [True, True, False],
        "y cada uno dice si es de red privada: el que no lo es, lo decide una persona")
afirmar(s.get("20053") == [{"prefijo": "172.16.9.", "clientes": 42, "privado": True}],
        "dos zonas del mismo servidor pueden sugerir el mismo prefijo")
afirmar("32278" not in s, "una zona sin prefijos con suficientes clientes no sugiere nada")
afirmar(oip.sugeridos_por_zona({}) == {} and oip.sugeridos_por_zona(None) == {},
        "sin lectura no hay sugerencia")

# ---------------------------------------------------------------------------
seccion("4. la lectura cuenta por zona, y la zona viene como objeto o como id")


class _Respuesta:
    def __init__(self, cuerpo):
        self._cuerpo = cuerpo

    def raise_for_status(self):
        pass

    def json(self):
        return self._cuerpo


filas = ([{"ip": f"172.16.9.{n}", "zona": {"id": 20049, "nombre": "CORTE 30"},
           "nombre": "PERSONA", "cedula": "1234500001"} for n in range(2, 14)]
         + [{"ip": "172.16.9.100", "zona": 20053}, {"ip": "172.16.9.101", "zona": "20053"},
            {"ip": "172.16.9.102", "zona": "CORTE 15"},          # un nombre suelto no
            {"ip": "172.16.9.103", "zona": None},
            {"ip": "10.0.0.5", "zona": {"id": 20049}},
            {"ip": "", "zona": {"id": 20049}}])
herr = types.SimpleNamespace(nombre="listar_clientes", tipo="http", campo_ip_sync="ip",
                             campo_zona_sync="zona")
viejos = (oip.requests.get, oip.headers_de, oip.url_de)
oip.requests.get = lambda *a, **k: _Respuesta({"count": len(filas), "results": filas})
oip.headers_de = lambda h, t: {}
oip.url_de = lambda h, variables_tenant=None: "https://isp/clientes"
try:
    r = oip.sincronizar(herr, tenant=TENANT)
finally:
    oip.requests.get, oip.headers_de, oip.url_de = viejos
afirmar(r["por_zona"] == {"20049": {"10.0.0.": 1, "172.16.9.": 12},
                          "20053": {"172.16.9.": 2}},
        f"cuenta por zona; un nombre suelto o una zona vacia no se adivinan: {r['por_zona']}")
afirmar(r["ocupacion"]["172.16.9."] == list(range(2, 14)) + [100, 101, 102, 103],
        "y la ocupacion sigue siendo GLOBAL por prefijo, sin importar la zona")
afirmar("PERSONA" not in repr(r) and "1234500001" not in repr(r),
        "nada del cliente sale de la lectura")

sin_campo = types.SimpleNamespace(nombre="x", tipo="http", campo_ip_sync="ip", campo_zona_sync="")
oip.requests.get = lambda *a, **k: _Respuesta({"count": len(filas), "results": filas})
oip.headers_de = lambda h, t: {}
oip.url_de = lambda h, variables_tenant=None: "https://isp/clientes"
try:
    r2 = oip.sincronizar(sin_campo, tenant=TENANT)
finally:
    oip.requests.get, oip.headers_de, oip.url_de = viejos
afirmar(r2["por_zona"] == {} and r2["ocupacion"] == r["ocupacion"],
        "sin campo de zona declarado no cuenta por zona, y la ocupacion es la misma")

# ---------------------------------------------------------------------------
seccion("5. el sincronizar por HTTP guarda tambien el conteo por zona")
llamadas = {}


def _guardar(tenant, ocupacion, completa, por_zona=None):
    llamadas["guardado"] = (ocupacion, completa, por_zona)
    return types.SimpleNamespace(ocupacion_ip=ocupacion, ocupacion_ip_completa=completa,
                                 ocupacion_ip_actualizado_en="2026-11-25T12:00:00+00:00")


cfg = types.SimpleNamespace(herramientas=[types.SimpleNamespace(
    nombre="listar_clientes", tipo="http", campo_ip_sync="ip", sincroniza_ocupacion_ip=True)],
    variables_tenant={})
viejos2 = (api._config_de, oip.sincronizar, editor.guardar_ocupacion_ip, api.olvidar_config)
api._config_de = lambda t: cfg
oip.sincronizar = lambda h, tenant=None, variables=None, **k: {
    "ocupacion": {"172.16.9.": [2]}, "por_zona": {"20049": {"172.16.9.": 1}},
    "leidos": 1, "sin_ip": 0, "ilegibles": [], "completo": True}
editor.guardar_ocupacion_ip = _guardar
api.olvidar_config = lambda t: None
try:
    with silencio():
        rr = cliente.post("/configuracion/ocupacion-ip/sincronizar", json={"tenant": TENANT})
finally:
    api._config_de, oip.sincronizar, editor.guardar_ocupacion_ip, api.olvidar_config = viejos2
afirmar(rr.status_code == 200 and llamadas.get("guardado") == (
            {"172.16.9.": [2]}, True, {"20049": {"172.16.9.": 1}}),
        f"guarda ocupacion, marca y conteo por zona: {rr.status_code} {llamadas}")

# ---------------------------------------------------------------------------
seccion("6. GET: lo que ve la pantalla son conteos, nunca direcciones")
cfg = types.SimpleNamespace(
    pools_de_ip=[PoolDeIp(zona_id=20049, zona_nombre="CORTE 30", prefijos=["172.16.9."])],
    ocupacion_ip={"172.16.9.": list(range(2, 243)), "172.16.10.": [2, 3],
                  "10.9.9.": [5]},
    ocupacion_ip_por_zona={"20049": {"172.16.9.": 241, "172.16.10.": 12},
                           "32278": {"10.9.9.": 1}},
    ocupacion_ip_completa=True, ocupacion_ip_actualizado_en="2026-11-25T12:00:00+00:00",
    herramientas=[types.SimpleNamespace(nombre="x", sincroniza_ocupacion_ip=True)])
api._config_de = lambda t: cfg
try:
    with silencio():
        g = cliente.get(f"/configuracion/rangos-de-ip?tenant={TENANT}")
finally:
    api._config_de = viejos2[0]
d = g.get_json() or {}
afirmar(g.status_code == 200, f"200: {g.status_code}")
afirmar(d.get("pools") == [{"zona_id": 20049, "zona_nombre": "CORTE 30", "prefijos": ["172.16.9."]}],
        f"los rangos guardados: {d.get('pools')}")
afirmar(d.get("sugeridos") == {"20049": [{"prefijo": "172.16.9.", "clientes": 241, "privado": True},
                                         {"prefijo": "172.16.10.", "clientes": 12, "privado": True}]},
        f"los sugeridos: {d.get('sugeridos')}")
afirmar(d.get("uso") == {"172.16.9.": {"tomadas": 241, "libres": 12},
                         "172.16.10.": {"tomadas": 2, "libres": 251}},
        f"el uso de cada prefijo a la vista, en conteos: {d.get('uso')}")
afirmar("10.9.9." not in (d.get("uso") or {}),
        "un prefijo que no esta guardado ni sugerido no se muestra")
afirmar(d.get("ocupacion") == {"actualizado_en": "2026-11-25T12:00:00+00:00",
                               "completa": True, "leida": True, "se_puede_leer": True,
                               "cada_horas": 0},
        f"y de cuando es la lectura: {d.get('ocupacion')}")
afirmar("172.16.9.5" not in repr(d) and "[2, 3" not in repr(d),
        "ninguna direccion suelta ni lista de octetos sale hacia la pantalla")

# ---------------------------------------------------------------------------
seccion("7. PUT: guarda limpio, y rechaza sin guardar")
guardados = []


def _guardar_rangos(tenant, pools, prudente=None, cada_horas=None):
    guardados.append(editor.rangos_validos(pools))
    return types.SimpleNamespace(pools_de_ip=[PoolDeIp(**p) for p in guardados[-1]],
                                 contar_ip_mal_escritas=bool(prudente),
                                 ocupacion_ip_cada_horas=cada_horas or 0)


viejos3 = (editor.guardar_rangos_de_ip, api.olvidar_config)
editor.guardar_rangos_de_ip = _guardar_rangos
api.olvidar_config = lambda t: guardados.append("olvido")
try:
    with silencio():
        ok = cliente.put("/configuracion/rangos-de-ip", json={
            "tenant": TENANT, "pools": [{"zona_id": 20049, "prefijos": ["172.16.9"]}]})
        malo = cliente.put("/configuracion/rangos-de-ip", json={
            "tenant": TENANT, "pools": [{"zona_id": 20049, "prefijos": ["169.254.1"]}]})
        sin_tenant = cliente.put("/configuracion/rangos-de-ip", json={"pools": []})
finally:
    editor.guardar_rangos_de_ip, api.olvidar_config = viejos3
afirmar(ok.status_code == 200 and (ok.get_json() or {}).get("pools") ==
        [{"zona_id": 20049, "zona_nombre": "", "prefijos": ["172.16.9."]}],
        f"guarda normalizado: {ok.status_code} {ok.get_json()}")
afirmar("olvido" in guardados, "y olvida la config en memoria, para que la lean las demas rutas")
afirmar(malo.status_code == 400 and "reservado" in (malo.get_json() or {}).get("error", ""),
        f"un rango reservado: 400 con el porque ({malo.status_code})")
afirmar(sin_tenant.status_code == 400, f"sin tenant: {sin_tenant.status_code}")

# ---------------------------------------------------------------------------
seccion("8. las IP mal escritas: la direccion que podria ser la de ellas no se ofrece")
ocupacion = {"172.16.4.": [2, 3], "168.16.4.": [25, 40], "168.0.4.": [77],
             "100.0.9.": [9], "172.16.9.": [2], "10.0.4.": [50]}
sombra = oip.sombra_de_mal_escritas(ocupacion)
afirmar(sombra == {"4": {25, 40, 77}, "9": {9}},
        f"por tercer numero, solo de las que NO son de red privada: {sombra}")
afirmar(oip.tomadas_en("172.16.4.", ocupacion, sombra) == {2, 3, 25, 40, 77},
        "las del rango mas las que podrian ser de un mal escrito")
afirmar(oip.tomadas_en("172.16.4.", ocupacion) == {2, 3},
        "EL CONTROL: sin la sombra, solo las del rango")
afirmar(oip.tomadas_en("10.0.4.", ocupacion, sombra) == {50, 25, 40, 77},
        "vale para cualquier rango con ese tercer numero, no para uno en particular")

cfg = types.SimpleNamespace(
    pools_de_ip=[PoolDeIp(zona_id=1, zona_nombre="S", prefijos=["172.16.4."])],
    ocupacion_ip=ocupacion, ocupacion_ip_completa=True,
    ocupacion_ip_actualizado_en="2026-11-25T12:00:00+00:00",
    ocupacion_ip_por_zona={}, contar_ip_mal_escritas=True,
    herramientas=[])
api._config_de = lambda t: cfg
try:
    with silencio():
        r_on = cliente.get(f"/interno/red/ips-libres?tenant={TENANT}&zona=1&cuantas=200")
        g_on = cliente.get(f"/configuracion/rangos-de-ip?tenant={TENANT}")
    cfg.contar_ip_mal_escritas = False
    with silencio():
        r_off = cliente.get(f"/interno/red/ips-libres?tenant={TENANT}&zona=1&cuantas=200")
        g_off = cliente.get(f"/configuracion/rangos-de-ip?tenant={TENANT}")
finally:
    api._config_de = viejos2[0]
libres_on = set((r_on.get_json() or {}).get("libres") or [])
libres_off = set((r_off.get_json() or {}).get("libres") or [])
afirmar("172.16.4.25" not in libres_on and "172.16.4.77" not in libres_on,
        "ENCENDIDA: no se ofrece la que podria ser de un cliente mal escrito")
afirmar({"172.16.4.25", "172.16.4.40", "172.16.4.77"} <= libres_off,
        "APAGADA: esas mismas se ofrecen como siempre")
afirmar((g_on.get_json() or {}).get("mal_escritas") == 4,
        f"la pantalla sabe cuantas hay: {(g_on.get_json() or {}).get('mal_escritas')}")
afirmar((g_on.get_json() or {})["uso"]["172.16.4."]["libres"] == 248
        and (g_off.get_json() or {})["uso"]["172.16.4."]["libres"] == 251,
        "y el conteo de libres de la pantalla dice lo mismo que la app")

guardados.clear()
editor.guardar_rangos_de_ip = lambda t, pools, prudente=None, cada_horas=None: (
    guardados.append(prudente) or types.SimpleNamespace(pools_de_ip=[],
                                                        contar_ip_mal_escritas=bool(prudente),
                                                        ocupacion_ip_cada_horas=0))
api.olvidar_config = lambda t: None
try:
    with silencio():
        si = cliente.put("/configuracion/rangos-de-ip",
                         json={"tenant": TENANT, "pools": [], "contar_ip_mal_escritas": True})
        raro = cliente.put("/configuracion/rangos-de-ip",
                           json={"tenant": TENANT, "pools": [], "contar_ip_mal_escritas": "si"})
finally:
    editor.guardar_rangos_de_ip, api.olvidar_config = viejos3
afirmar(si.status_code == 200 and guardados == [True], f"se guarda el si: {guardados}")
afirmar(raro.status_code == 400, f"un si que no es un si se rechaza: {raro.status_code}")

# ---------------------------------------------------------------------------
seccion("8b. la ocupacion se lee SOLA cada N horas: lo decide la empresa (27/11/2026)")
#  GET: la tarea de la plataforma pregunta aca cada cuanto.
cfg.ocupacion_ip_cada_horas = 1
api._config_de = lambda t: cfg
try:
    with silencio():
        g1 = cliente.get(f"/configuracion/rangos-de-ip?tenant={TENANT}")
finally:
    api._config_de = viejos2[0]
afirmar((g1.get_json() or {}).get("ocupacion", {}).get("cada_horas") == 1,
        f"el GET dice cada cuantas horas: {(g1.get_json() or {}).get('ocupacion')}")
#  PUT: viaja tal cual hasta el editor, y vuelve en la respuesta.
llegadas = []
editor.guardar_rangos_de_ip = lambda t, pools, prudente=None, cada_horas=None: (
    llegadas.append(cada_horas) or types.SimpleNamespace(pools_de_ip=[], contar_ip_mal_escritas=False,
                                                         ocupacion_ip_cada_horas=cada_horas or 0))
api.olvidar_config = lambda t: None
try:
    with silencio():
        con = cliente.put("/configuracion/rangos-de-ip",
                          json={"tenant": TENANT, "pools": [], "ocupacion_cada_horas": 1})
        sin = cliente.put("/configuracion/rangos-de-ip", json={"tenant": TENANT, "pools": []})
finally:
    editor.guardar_rangos_de_ip, api.olvidar_config = viejos3
afirmar(con.status_code == 200 and (con.get_json() or {}).get("ocupacion_cada_horas") == 1,
        f"se guarda y vuelve: {con.status_code} {con.get_json()}")
afirmar(llegadas == [1, None], f"sin el campo no se toca (None): {llegadas}")
#  El EDITOR rechaza lo que no es un numero de horas, SIN escribir.
escrituras = []
viejo_editar = editor._editar
editor._editar = lambda t, mutar: escrituras.append(t)
try:
    for malo in (-1, 169, True, "1", 1.5):
        try:
            editor.guardar_rangos_de_ip(TENANT, [], None, malo)
            afirmar(False, f"{malo!r} se rechaza")
        except editor.ErrorEdicion as e:
            afirmar("0 = solo con el botón" in str(e), f"{malo!r}: se rechaza con el porque")
    editor.guardar_rangos_de_ip(TENANT, [], None, 168)
    editor.guardar_rangos_de_ip(TENANT, [], None, 0)
finally:
    editor._editar = viejo_editar
afirmar(escrituras == [TENANT, TENANT], f"solo 0..168 llega a escribirse: {escrituras}")
doc = {"pools_de_ip": [], "ocupacion_ip_cada_horas": 6}
editor._mutar_rangos_de_ip(doc, [], None, None)
afirmar(doc["ocupacion_ip_cada_horas"] == 6, "guardar rangos sin el campo NO cambia la frecuencia")
editor._mutar_rangos_de_ip(doc, [], None, 1)
afirmar(doc["ocupacion_ip_cada_horas"] == 1, "con el campo, si")
#  El ESQUEMA: 0 de fabrica (nadie le pega al proveedor sin decidirlo) y con tope.
from nucleo.config import cargar_config  # noqa: E402
from nucleo.config.schema import TenantConfig  # noqa: E402

campo = TenantConfig.model_fields["ocupacion_ip_cada_horas"]
afirmar(campo.default == 0, f"de fabrica, solo con el boton: {campo.default}")
base_cfg = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml").model_dump(mode="json")
for valor, debe in ((1, True), (168, True), (169, False), (-1, False)):
    try:
        TenantConfig.model_validate({**base_cfg, "ocupacion_ip_cada_horas": valor})
        paso = True
    except Exception:                                            # noqa: BLE001
        paso = False
    afirmar(paso is debe, f"el esquema {'acepta' if debe else 'rechaza'} {valor}")

seccion("9. la IP se pregunta EN VIVO antes de ponerla en un contrato (26/11/2026)")
from nucleo.seguimiento import alta_de_cliente as alta              # noqa: E402

viejos9 = (api._config_de, alta._quien_tiene)
api._config_de = lambda t: types.SimpleNamespace(herramientas=[types.SimpleNamespace(
    nombre="buscar", busca_cliente_por_ip=True)], variables_tenant={})
preguntas = []


def _quien(h, config, tenant, ip):
    preguntas.append(ip)
    if ip == "172.16.9.7":
        raise alta._NoSePudoLeer("ConnectionError")
    return [{"id_servicio": 1, "nombre": "NO-DEBE-SALIR"}] if ip == "172.16.9.5" else []


alta._quien_tiene = _quien
try:
    with silencio():
        tomada = cliente.get(f"/interno/red/ip-libre?tenant={TENANT}&ip=172.16.9.5")
        libre = cliente.get(f"/interno/red/ip-libre?tenant={TENANT}&ip=172.16.9.6")
        caida = cliente.get(f"/interno/red/ip-libre?tenant={TENANT}&ip=172.16.9.7")
        mala = cliente.get(f"/interno/red/ip-libre?tenant={TENANT}&ip=172.16.9.300")
        sin = cliente.get("/interno/red/ip-libre?ip=172.16.9.6")
    api._config_de = lambda t: types.SimpleNamespace(herramientas=[], variables_tenant={})
    with silencio():
        sin_herr = cliente.get(f"/interno/red/ip-libre?tenant={TENANT}&ip=172.16.9.6")
finally:
    api._config_de, alta._quien_tiene = viejos9
afirmar(tomada.status_code == 200 and tomada.get_json() == {"libre": False},
        f"la que tiene un cliente: libre=false, y NADA de su ficha ({tomada.get_json()})")
afirmar(libre.get_json() == {"libre": True}, f"la que nadie tiene: libre=true ({libre.get_json()})")
afirmar(caida.status_code == 502, f"si no se pudo preguntar: 502, no «libre» ({caida.status_code})")
afirmar(sin_herr.status_code == 502, f"sin herramienta para preguntar: 502 ({sin_herr.status_code})")
afirmar(mala.status_code == 400 and sin.status_code == 400,
        f"una IP que no es IP, o sin empresa: 400 ({mala.status_code}, {sin.status_code})")
afirmar(preguntas == ["172.16.9.5", "172.16.9.6", "172.16.9.7"],
        f"se pregunta por la IP pedida, una vez: {preguntas}")

# ---------------------------------------------------------------------------
print()
if _fallos:
    print(f"FALLARON {len(_fallos)}:")
    for f in _fallos:
        print("  -", f)
    sys.exit(1)
print("TODO OK")
