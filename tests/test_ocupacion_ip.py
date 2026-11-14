# -*- coding: utf-8 -*-
"""
================================================================================
 QUE IP SE LE PUEDEN OFRECER AL TECNICO  --  14/11/2026
================================================================================
Afirma sobre el EFECTO: que la ruta devuelva CERO cuando no se puede saber, y
que devuelva las de verdad cuando si. No sobre que el campo exista.

LO QUE MAS VALE DE ESTE ARCHIVO es el bloque B: las cuatro formas de no saber.
Una direccion ofrecida a partir de un dato que falta es como dos clientes
terminan con la misma IP, y ninguna de las cuatro da error por su cuenta.

No llama a ninguna API: reemplaza la lectura.
================================================================================
"""
from __future__ import annotations

import contextlib
import io
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.canales import api                                    # noqa: E402
from nucleo.config.schema import PoolDeIp                         # noqa: E402
from nucleo.herramientas import ocupacion_ip as oip               # noqa: E402

TENANT = "empresa-de-prueba"
cliente = api.app.test_client()
fallos: list[str] = []


def revisar(cond, que, detalle=""):
    print(f"  [{'ok' if cond else 'FALLA'}] {que}")
    if not cond:
        if detalle:
            print(f"         {detalle[:300]}")
        fallos.append(que)


@contextlib.contextmanager
def config_de(cfg):
    viejo = api._config_de
    api._config_de = lambda t: cfg
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            yield
    finally:
        api._config_de = viejo


def _config(**extra):
    base = dict(pools_de_ip=[], ocupacion_ip={}, ocupacion_ip_completa=False,
                ocupacion_ip_actualizado_en=None,
                identidad=types.SimpleNamespace(slug=TENANT))
    base.update(extra)
    return types.SimpleNamespace(**base)


def pedir(cfg, zona=7, cuantas=None):
    with config_de(cfg):
        url = f"/interno/red/ips-libres?tenant={TENANT}&zona={zona}"
        if cuantas:
            url += f"&cuantas={cuantas}"
        r = cliente.get(url)
    return r.status_code, (r.get_json(silent=True) or {})


#  Un pool con el .1, el .5 y el .9 tomados.
POOL = [PoolDeIp(zona_id=7, zona_nombre="ZONA SIETE", prefijos=["172.16.9."])]
SANA = _config(pools_de_ip=POOL, ocupacion_ip={"172.16.9.": [1, 5, 9]},
               ocupacion_ip_completa=True,
               ocupacion_ip_actualizado_en="2026-11-14T10:00:00+00:00")


print("=" * 78)
print(" QUE IP SE LE PUEDEN OFRECER AL TECNICO")
print("=" * 78)

# =========================================================================== #
print("\nA. LA CUENTA")
# =========================================================================== #
revisar(oip.prefijo_de("172.16.9.37") == "172.16.9.", "el /24 de una IP")
for basura in ("", "  ", "no-es-una-ip", "172.16.9", "172.16.9.1.5",
               "999.1.1.1", "::1", "172.16.9.1/24"):
    revisar(oip.prefijo_de(basura) == "", f"{basura!r} no tiene /24")

libres = oip.libres_de("172.16.9.", [1, 5, 9])
revisar("172.16.9.0" not in libres, "la RED (.0) no se ofrece")
revisar("172.16.9.255" not in libres, "el BROADCAST (.255) no se ofrece")
revisar("172.16.9.1" not in libres,
        "la PUERTA DE ENLACE (.1) no se ofrece, aunque estuviera libre")
revisar("172.16.9.5" not in libres and "172.16.9.9" not in libres,
        "las ocupadas no se ofrecen")
revisar(libres[0] == "172.16.9.2", "la primera ofrecida es la .2", str(libres[:3]))
revisar(len(libres) == 251, "quedan 251: 254 menos .1, .5 y .9", str(len(libres)))
revisar(len(oip.libres_de("172.16.9.", [1, 5, 9], 4)) == 4, "'cuantas' recorta")

#  EL .1 SE EXCLUYE AUNQUE NADIE LO TENGA. Es la medicion del 14/11: libre en
#  83 de 86 pools, uno de ellos con 240 de 254 ocupadas.
revisar("172.16.9.1" not in oip.libres_de("172.16.9.", []),
        "EL CONTROL: con el pool VACIO, el .1 sigue sin ofrecerse")

#  Un /24 lleno no ofrece nada, y eso no es un error.
revisar(oip.libres_de("172.16.9.", list(range(0, 256))) == [],
        "un /24 lleno devuelve lista vacia")

# =========================================================================== #
print("\nB. LAS CUATRO FORMAS DE NO SABER  --  todas devuelven CERO")
# =========================================================================== #
casos = [
    ("la ocupacion no se sincronizo nunca",
     _config(pools_de_ip=POOL, ocupacion_ip={}, ocupacion_ip_completa=True),
     "no se ha sincronizado nunca"),
    ("la ultima lectura quedo incompleta",
     _config(pools_de_ip=POOL, ocupacion_ip={"172.16.9.": [5]},
             ocupacion_ip_completa=False),
     "incompleta"),
    ("la zona no tiene pool declarado",
     _config(pools_de_ip=[], ocupacion_ip={"172.16.9.": [5]},
             ocupacion_ip_completa=True),
     "no tiene pool declarado"),
    ("el pool no tiene ningun prefijo",
     _config(pools_de_ip=[PoolDeIp(zona_id=7, prefijos=[])],
             ocupacion_ip={"172.16.9.": [5]}, ocupacion_ip_completa=True),
     "ningun prefijo"),
]
for etiqueta, cfg, trozo in casos:
    codigo, datos = pedir(cfg)
    revisar(codigo == 200 and datos.get("libres") == []
            and trozo in str(datos.get("motivo", "")),
            f"{etiqueta} -> cero, y lo dice", f"{codigo} {datos}")

#  Y si la config no se puede leer: tampoco inventa.
viejo = api._config_de
api._config_de = lambda t: (_ for _ in ()).throw(RuntimeError("sin base"))
try:
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        r = cliente.get(f"/interno/red/ips-libres?tenant={TENANT}&zona=7")
    datos = r.get_json(silent=True) or {}
    revisar(r.status_code == 200 and datos.get("libres") == [],
            "sin poder leer la config -> cero", f"{r.status_code} {datos}")
finally:
    api._config_de = viejo

# =========================================================================== #
print("\nC. CUANDO SI SE PUEDE")
# =========================================================================== #
codigo, datos = pedir(SANA, cuantas=5)
revisar(codigo == 200, "responde 200", str(codigo))
revisar(datos.get("libres") == ["172.16.9.2", "172.16.9.3", "172.16.9.4",
                                "172.16.9.6", "172.16.9.7"],
        "devuelve las libres en orden, salteando las tomadas",
        str(datos.get("libres")))
revisar(datos.get("zona_nombre") == "ZONA SIETE", "nombra la zona")
revisar(datos.get("actualizado_en") == "2026-11-14T10:00:00+00:00",
        "dice de cuando es el dato: una lista vieja se tiene que poder ver")
revisar("equipos de red" in str(datos.get("advertencia", "")),
        "LA ADVERTENCIA VIAJA EN LA RESPUESTA, no se queda en el docstring",
        str(datos.get("advertencia")))

#  Pedir otra zona no devuelve el pool de la primera.
codigo, datos = pedir(SANA, zona=99)
revisar(datos.get("libres") == [], "otra zona no hereda el pool",
        str(datos))

#  Varios prefijos: se recorren en el orden declarado.
dos = _config(
    pools_de_ip=[PoolDeIp(zona_id=7, prefijos=["172.16.9.", "172.16.10."])],
    ocupacion_ip={"172.16.9.": list(range(0, 256)), "172.16.10.": [2, 3]},
    ocupacion_ip_completa=True)
codigo, datos = pedir(dos, cuantas=3)
revisar(datos.get("libres") == ["172.16.10.4", "172.16.10.5", "172.16.10.6"],
        "con el primer prefijo lleno, pasa al siguiente",
        str(datos.get("libres")))

#  Un prefijo SIN entrada en la ocupacion: no se asume vacio ni se revienta.
#  Esta es la unica forma de "no saber" que NO se puede distinguir de "nadie la
#  tiene", y por eso el pool se declara: un prefijo que la empresa no puso no
#  llega hasta aca.
sin_dato = _config(
    pools_de_ip=[PoolDeIp(zona_id=7, prefijos=["10.9.9."])],
    ocupacion_ip={"172.16.9.": [5]}, ocupacion_ip_completa=True)
codigo, datos = pedir(sin_dato, cuantas=2)
revisar(datos.get("libres") == ["10.9.9.2", "10.9.9.3"],
        "un prefijo declarado sin ocupacion leida se trata como vacio",
        str(datos.get("libres")))

# =========================================================================== #
print("\nD. LA LECTURA DEL PROVEEDOR")
# =========================================================================== #
herr = types.SimpleNamespace(nombre="listar_clientes", tipo="http",
                             campo_ip_sync="ip")


class _Respuesta:
    def __init__(self, cuerpo):
        self._cuerpo = cuerpo

    def raise_for_status(self):
        pass

    def json(self):
        return self._cuerpo


def _con_paginas(paginas):
    """Reemplaza requests.get por una lectura de paginas de mentira."""
    estado = {"i": 0}

    def _get(url, headers=None, params=None, timeout=None):
        i = estado["i"]
        estado["i"] += 1
        return _Respuesta(paginas[i] if i < len(paginas) else
                          {"count": 0, "results": []})
    return _get


def _medir(paginas, **extra):
    viejos = (oip.requests.get, oip.headers_de, oip.url_de)
    oip.requests.get = _con_paginas(paginas)
    oip.headers_de = lambda h, t: {}
    oip.url_de = lambda h, variables_tenant=None: "https://isp/clientes"
    try:
        return oip.sincronizar(herr, tenant=TENANT, **extra)
    finally:
        oip.requests.get, oip.headers_de, oip.url_de = viejos


filas = [{"ip": f"172.16.9.{n}"} for n in range(2, 12)]
filas += [{"ip": ""}, {"ip": "no-es-una-ip"}, {"ip": "10.0.0.4"}]
r = _medir([{"count": len(filas), "results": filas}])
revisar(r["ocupacion"].get("172.16.9.") == list(range(2, 12)),
        "junta los octetos de un prefijo", str(r["ocupacion"]))
revisar(r["ocupacion"].get("10.0.0.") == [4], "y separa los prefijos")
revisar(r["sin_ip"] == 1, "cuenta la fila sin ip", str(r["sin_ip"]))
revisar(r["ilegibles"] == ["no-es-una-ip"], "y nombra la ilegible",
        str(r["ilegibles"]))
revisar(r["leidos"] == len(filas), "cuenta las filas leidas")
revisar(r["completo"] is True, "una sola pagina corta y se da por completa")

#  DOS ZONAS, UN MISMO /24: el defecto del 14/11. La ocupacion es GLOBAL.
mezcla = ([{"ip": f"172.16.9.{n}"} for n in range(2, 44)]
          + [{"ip": f"172.16.9.{n}"} for n in range(44, 100)])
r = _medir([{"count": len(mezcla), "results": mezcla}])
revisar(len(r["ocupacion"]["172.16.9."]) == 98,
        "las dos tandas del MISMO /24 se suman, no se separan por zona",
        str(len(r["ocupacion"]["172.16.9."])))

#  Una lectura cortada NO se da por completa.
pagina_llena = {"count": 100000,
                "results": [{"ip": f"10.0.{p}.1"} for p in range(300)]}
viejo_max = oip.MAX_PAGINAS
oip.MAX_PAGINAS = 2
try:
    r = _medir([pagina_llena, pagina_llena, pagina_llena])
finally:
    oip.MAX_PAGINAS = viejo_max
revisar(r["completo"] is False,
        "LA LECTURA CORTADA NO SE DA POR COMPLETA: lo que falto leer es justo "
        "lo que haria parecer libre una direccion tomada")

#  Sin 'campo_ip_sync' no se lee nada: no se adivina el nombre de la columna.
try:
    oip.sincronizar(types.SimpleNamespace(nombre="x", tipo="http",
                                          campo_ip_sync=""), tenant=TENANT)
    revisar(False, "sin campo_ip_sync tiene que levantar")
except oip.ErrorHerramientaHttp as e:
    revisar("campo_ip_sync" in str(e), "sin campo_ip_sync levanta y lo nombra")

try:
    oip.sincronizar(types.SimpleNamespace(nombre="x", tipo="rag",
                                          campo_ip_sync="ip"), tenant=TENANT)
    revisar(False, "un tipo que no sirve tiene que levantar")
except oip.ErrorHerramientaHttp as e:
    revisar("tipo" in str(e), "un tipo que no sirve levanta y lo dice")

# =========================================================================== #
print("\nE. EL LLAMADOR  --  que la ruta de verdad llame al sincronizador")
# =========================================================================== #
#  CLAUDE.md 6: «codigo construido no es codigo que corre». El reloj de tareas
#  colgaba de un `__main__` que gunicorn nunca ejecuta y la reconciliacion
#  estaba probada y sin llamador. Ninguno dio error, log ni alerta. Aca se
#  afirma que el POST recorre el proveedor Y guarda, no que la funcion exista.
from nucleo.config import editor as _editor                       # noqa: E402

herr_marcada = types.SimpleNamespace(nombre="listar_clientes", tipo="http",
                                     campo_ip_sync="ip",
                                     sincroniza_ocupacion_ip=True)


def sincronizar_por_http(cfg, *, sincronizador=None, guardar=None):
    """Hace el POST con el proveedor y el editor reemplazados."""
    llamadas = {}

    def _sinc(h, tenant=None, variables=None, **k):
        llamadas["sincronizador"] = h.nombre
        return (sincronizador or (lambda: {
            "ocupacion": {"172.16.9.": [2, 3]}, "leidos": 2, "sin_ip": 0,
            "ilegibles": [], "completo": True}))()

    def _guardar(tenant, ocupacion, completa):
        llamadas["guardado"] = (ocupacion, completa)
        return types.SimpleNamespace(
            ocupacion_ip=ocupacion, ocupacion_ip_completa=completa,
            ocupacion_ip_actualizado_en="2026-11-14T12:00:00+00:00")

    viejos = (api._config_de, oip.sincronizar, _editor.guardar_ocupacion_ip,
              api.olvidar_config)
    api._config_de = lambda t: cfg
    oip.sincronizar = _sinc
    _editor.guardar_ocupacion_ip = guardar or _guardar
    api.olvidar_config = lambda t: llamadas.setdefault("olvido", True)
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            r = cliente.post("/configuracion/ocupacion-ip/sincronizar",
                             json={"tenant": TENANT})
        return r.status_code, (r.get_json(silent=True) or {}), llamadas
    finally:
        (api._config_de, oip.sincronizar, _editor.guardar_ocupacion_ip,
         api.olvidar_config) = viejos


cfg_ok = _config(herramientas=[herr_marcada], variables_tenant={})
codigo, datos, llamadas = sincronizar_por_http(cfg_ok)
revisar(codigo == 200, "el POST responde 200", f"{codigo} {datos}")
revisar(llamadas.get("sincronizador") == "listar_clientes",
        "LA RUTA LLAMA AL SINCRONIZADOR con la herramienta marcada",
        str(llamadas))
revisar(llamadas.get("guardado") == ({"172.16.9.": [2, 3]}, True),
        "Y GUARDA lo leido, con la marca de completa", str(llamadas))
revisar(llamadas.get("olvido") is True,
        "y olvida la config cacheada: si no, el motor sigue con la vieja")
revisar(datos.get("prefijos") == 1 and datos.get("direcciones_tomadas") == 2,
        "el resumen cuenta prefijos y direcciones", str(datos))

#  Una lectura INCOMPLETA se guarda con su marca, no se tira.
codigo, datos, llamadas = sincronizar_por_http(
    cfg_ok, sincronizador=lambda: {"ocupacion": {"10.0.0.": [2]}, "leidos": 1,
                                   "sin_ip": 0, "ilegibles": [],
                                   "completo": False})
revisar(llamadas.get("guardado") == ({"10.0.0.": [2]}, False),
        "una lectura INCOMPLETA se guarda CON su marca: tirarla dejaria la "
        "anterior pasando por buena", str(llamadas))
revisar(datos.get("completa") is False, "y el resumen lo dice")

#  Sin herramienta marcada no recorre nada.
cfg_sin = _config(herramientas=[types.SimpleNamespace(
    nombre="otra", tipo="http", sincroniza_ocupacion_ip=False)],
    variables_tenant={})
codigo, datos, llamadas = sincronizar_por_http(cfg_sin)
revisar(codigo == 400 and "sincroniza_ocupacion_ip" in str(datos),
        "sin herramienta marcada: 400 y nombra la bandera", f"{codigo} {datos}")
revisar("sincronizador" not in llamadas,
        "y NO le pega al proveedor: no se recorren 7.000 clientes por nada")

#  Si el proveedor falla, no se guarda nada a medias.
def _explota():
    raise RuntimeError("el proveedor se cayo")


codigo, datos, llamadas = sincronizar_por_http(cfg_ok, sincronizador=_explota)
revisar(codigo == 502, "si el proveedor falla: 502", f"{codigo} {datos}")
revisar("guardado" not in llamadas,
        "Y NO SE GUARDA NADA: una ocupacion a medias es peor que la vieja")

codigo, datos, _ = sincronizar_por_http(cfg_ok)
viejo_cfg = api._config_de
buf = io.StringIO()
with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
    r = cliente.post("/configuracion/ocupacion-ip/sincronizar", json={})
revisar(r.status_code == 400, "sin 'tenant': 400", str(r.status_code))

print()
print("=" * 78)
if fallos:
    print(f"  FALLARON {len(fallos)}")
    for f in fallos:
        print(f"    - {f}")
    sys.exit(1)
print("  TODO EN VERDE")
print("=" * 78)
