# -*- coding: utf-8 -*-
"""El costo de instalacion y el serial, en el cliente recien activado (26/11/2026).

LO QUE ESTE ARCHIVO DEFIENDE

* **Una vez, por la puerta humana de quien aprobo, y solo si ya es CLIENTE con
  ese numero y de ESTE contrato.** Si no esta, no es suyo, o la lectura falla:
  CERO escrituras.
* **Lo que confirma es la lectura**: escrito y leido igual → completado; si
  no se lee, «en curso», nunca «hecho».
* **Si ya tiene esos valores, no escribe.** Sin costo ni serial, no hay nada
  que hacer.
* **El interruptor, pegado a la escritura.**
* **Solo esos dos valores**, con el nombre del proveedor que dice la
  configuracion; un costo que no es numero no viaja.
* **La ruta**: contrato angosto y origen del motor.

    python tests/test_completar_cliente.py
"""
from __future__ import annotations

import contextlib
import os
import sys
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

os.environ["MOTOR_SERVICE_TOKEN"] = ""
RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.config import schema                                   # noqa: E402
from nucleo.herramientas import http as ejecutor_http              # noqa: E402
from nucleo.persistencia import db as persistencia                 # noqa: E402
from nucleo.seguimiento import alta_de_cliente as alta             # noqa: E402
from nucleo.seguridad import frontera, interruptor                 # noqa: E402

TENANT = "tenant-de-prueba"
ORIGEN = "completar_cliente:c-1:1"
IP = "172.16.9.37"
_fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(("  OK   " if condicion else "  FALLA ") + que)
    if not condicion:
        _fallos.append(que)


def seccion(titulo: str) -> None:
    print("\n" + titulo)
    print("-" * len(titulo))


PARAMETROS = schema.ParametrosDeAlta(
    zona="id_zona",
    campos={"nombre_en_router": "usuario_rb", "ip": "ip", "plan": "plan_internet",
            "nombre": "nombre", "apellido": "apellidos", "documento": "cedula"})


class HerrCrear:
    nombre = "crear_cliente"
    crea_cliente = True
    parametros_de_alta = PARAMETROS


class HerrBuscar:
    nombre = "buscar_cliente"
    busca_cliente_por_ip = True
    argumentos_fijos: dict = {}
    parametros_de_busqueda_por_ip = schema.ParametrosDeBusquedaPorIp(
        ip="ip", campo_id="id_servicio", campo_nombre_en_router="servicio",
        campo_documento="cedula")


class HerrCompletar:
    nombre = "completar_cliente"
    completa_cliente_activado = True
    solo_lectura = False
    argumentos_fijos: dict = {}
    parametros_de_completar = schema.ParametrosDeCompletar(
        campo_servicio="id_servicio",
        campos={"costo_instalacion": "costo_instalacion", "serial_onu": "sn_onu"})


class Config:
    variables_tenant: dict = {}
    pools_de_ip: list = []

    def __init__(self, herramientas=None):
        self.herramientas = herramientas if herramientas is not None else [
            HerrCrear(), HerrBuscar(), HerrCompletar()]


DATOS = {"zona": 20049, "ip": IP, "plan": "PLAN FAMILIA",
         "cliente": {"nombre": "LAURA MARCELA", "apellido": "PINEDA ORTEGA",
                     "documento": "1234500001"}}
NOMBRE = alta.leer_datos(DATOS, PARAMETROS)[0]["nombre_en_router"]


class Veredicto:
    def __init__(self, permitido=True):
        self.permitido, self.estado, self.motivo = permitido, "activo" if permitido else "detenido", ""


class Registro:
    def __init__(self):
        self.filas: dict = {}

    def reclamar(self, tenant, clave, herramienta, argumentos_hash, origen, segundos_vencida,
                 reintentar_fallida=False):
        fila = self.filas.get(clave)
        if fila is None:
            self.filas[clave] = {"estado": "ejecutando", "respuesta": None, "huella": argumentos_hash}
            return {"decision": "ejecutar", "fila": self.filas[clave]}
        if fila["estado"] == "exitosa":
            return {"decision": "repetida", "fila": fila}
        return {"decision": "fallida" if fila["estado"] == "fallida" else "en_curso", "fila": fila}

    def finalizar(self, tenant, clave, estado, respuesta=None, error=None):
        self.filas.setdefault(clave, {})["estado"] = estado


class Proveedor:
    def __init__(self, clientes=None, aplica=True, rompe=False):
        self.clientes = clientes if clientes is not None else [
            {"id_servicio": 8039, "ip": IP, "servicio": NOMBRE, "cedula": "1234500001",
             "costo_instalacion": "0.00", "sn_onu": ""}]
        self.aplica, self.rompe = aplica, rompe
        self.escrituras: list[tuple[dict, object]] = []

    def ejecutar(self, herramienta, argumentos, tenant, variables_tenant=None):
        if herramienta.nombre == "buscar_cliente":
            if self.rompe:
                raise RuntimeError("no contesto")
            return {"results": [dict(c) for c in self.clientes if c["ip"] == argumentos["ip"]]}
        if herramienta.nombre == "completar_cliente":
            self.escrituras.append((dict(argumentos), frontera.permiso_vigente()))
            if self.aplica:
                for c in self.clientes:
                    if str(c["id_servicio"]) == str(argumentos["id_servicio"]):
                        c.update({k: v for k, v in argumentos.items() if k != "id_servicio"})
            return {"ok": True}
        raise AssertionError(herramienta.nombre)


@contextlib.contextmanager
def escenario(registro, proveedor, permitido=True):
    viejos = (persistencia.reclamar_operacion_externa, persistencia.finalizar_operacion_externa,
              interruptor.veredicto, interruptor.anotar_bloqueo, ejecutor_http.ejecutar)
    persistencia.reclamar_operacion_externa = registro.reclamar
    persistencia.finalizar_operacion_externa = registro.finalizar
    interruptor.veredicto = lambda t: Veredicto(permitido)
    interruptor.anotar_bloqueo = lambda *a, **k: None
    ejecutor_http.ejecutar = proveedor.ejecutar
    try:
        yield
    finally:
        (persistencia.reclamar_operacion_externa, persistencia.finalizar_operacion_externa,
         interruptor.veredicto, interruptor.anotar_bloqueo, ejecutor_http.ejecutar) = viejos


def completar(valores=None, config=None, id_servicio=8039, origen=ORIGEN):
    with redirect_stdout(StringIO()):
        return alta.completar(config or Config(), TENANT, actor="Encargada Rosa", origen=origen,
                              datos=DATOS, id_servicio=id_servicio,
                              valores=valores if valores is not None else
                              {"costo_instalacion": 50000, "serial_onu": "zte-c1a2b3c4"})


# --------------------------------------------------------------------------- #
seccion("1. una vez, por la puerta humana, y se confirma leyendo")
reg, prov = Registro(), Proveedor()
with escenario(reg, prov):
    r = completar()
    afirmar(r.estado == alta.COMPLETADO, f"completado ({r.estado})")
    args, permiso = prov.escrituras[0]
    afirmar(args == {"id_servicio": "8039", "costo_instalacion": "50000.00", "sn_onu": "ZTE-C1A2B3C4"},
            f"viajan solo esos dos, con el nombre del proveedor ({args})")
    afirmar(permiso is not None and permiso.clase == "humana" and permiso.actor == "Encargada Rosa",
            "sale con el permiso HUMANO de quien aprobo")
    r2 = completar()
    afirmar(r2.estado == alta.YA_ESTABA and len(prov.escrituras) == 1,
            "otra vez: ya tiene los valores, NO vuelve a escribir")

# --------------------------------------------------------------------------- #
seccion("2. sin cliente suyo, o sin poder leer: CERO escrituras")
for que, prov, kw, esperado in (
        ("otro numero", Proveedor(), dict(id_servicio=9999), alta.NO_ENCONTRADA),
        ("otro cliente en esa IP", Proveedor(clientes=[
            {"id_servicio": 8039, "ip": IP, "servicio": "OTRA PERSONA", "cedula": "999"}]), {},
         alta.NO_ENCONTRADA),
        ("la lectura falla", Proveedor(rompe=True), {}, alta.NO_SE_PUDO_COMPROBAR)):
    with escenario(Registro(), prov):
        r = completar(**kw)
    afirmar(r.estado == esperado and prov.escrituras == [], f"{que}: {esperado}, sin escribir")

# --------------------------------------------------------------------------- #
seccion("3. lo que confirma es la lectura; el interruptor; los datos")
prov = Proveedor(aplica=False)
with escenario(Registro(), prov):
    r = completar()
afirmar(r.estado == alta.EN_CURSO and len(prov.escrituras) == 1,
        "escribio y no se lee: en curso, nunca «completado»")
prov = Proveedor()
with escenario(Registro(), prov, permitido=False):
    r = completar()
afirmar(r.estado == alta.BLOQUEADO and prov.escrituras == [], "interruptor detenido: no sale")
prov = Proveedor()
with escenario(Registro(), prov):
    r = completar(valores={})
afirmar(r.estado == alta.NADA_QUE_COMPLETAR and prov.escrituras == [], "sin costo ni serial: nada")
with escenario(Registro(), prov):
    r = completar(valores={"costo_instalacion": "cincuenta"})
afirmar(r.estado == alta.DATOS_INVALIDOS and prov.escrituras == [], "un costo que no es numero no viaja")
prov = Proveedor()
with escenario(Registro(), prov):
    r = completar(valores={"serial_onu": "zte-c1a2b3c4"})
afirmar(r.estado == alta.COMPLETADO and "costo_instalacion" not in prov.escrituras[0][0],
        "solo el serial: el costo no viaja")
with escenario(Registro(), Proveedor()):
    r = completar(config=Config([HerrCrear(), HerrBuscar()]))
afirmar(r.estado == alta.SIN_HERRAMIENTA, "sin la herramienta: sin_herramienta")

# --------------------------------------------------------------------------- #
seccion("4. el esquema y la ruta")
try:
    schema.ParametrosDeCompletar(campo_servicio="id_servicio", campos={"plan": "plan_internet"})
    afirmar(False, "no carga: completar otro campo que costo y serial")
except Exception:                                        # noqa: BLE001
    afirmar(True, "no carga: completar otro campo que costo y serial")

from nucleo.canales import api                                       # noqa: E402

cliente = api.app.test_client()
vistos: list = []
viejos = (api._config_de, alta.completar)
api._config_de = lambda t: object()
alta.completar = lambda config, tenant, **kw: vistos.append(kw) or alta.ResultadoAlta(alta.COMPLETADO)
try:
    base = "/interno/contrato/c-9/completar-cliente?tenant=t"
    cuerpo = {"actor": "Encargada Rosa", "datos": DATOS, "intento": 1, "id_servicio": 8039,
              "valores": {"costo_instalacion": 50000, "serial_onu": "X1"}}
    r = cliente.post(base, json=cuerpo)
    afirmar(r.status_code == 200 and vistos[-1]["origen"] == "completar_cliente:c-9:1",
            "200, y el origen lo arma el motor")
    r = cliente.post(base, json={**cuerpo, "valores": {"plan": "OTRO"}})
    afirmar(r.status_code == 400, "otro valor que costo y serial: 400")
    r = cliente.post(base, json={**cuerpo, "actor": ""})
    afirmar(r.status_code == 400, "sin actor: 400")
finally:
    api._config_de, alta.completar = viejos

print()
if _fallos:
    print(f"FALLARON {len(_fallos)}:")
    for f in _fallos:
        print("  -", f)
    sys.exit(1)
print("TODO OK")
