# -*- coding: utf-8 -*-
"""El contrato del proveedor: prepararlo, pedir el enlace, saber si se firmo.

LO QUE ESTE ARCHIVO DEFIENDE  --  26/11/2026

* **Se prepara UNA vez, por la puerta humana, y solo si la instalacion es de
  ESE contrato.** Con ese numero, esa IP y el nombre del cliente; de esa fila
  sale el usuario para el enlace. Si no esta, no es suya o no trae el usuario:
  CERO escrituras.
* **El interruptor, pegado a la escritura**: detenido o ilegible, no sale.
* **El mismo pedido no sale dos veces**: repetido, devuelve el numero de
  contrato de la primera vez sin tocar el panel; uno que fallo no se reejecuta.
* **«No se» no es «fallo»**: salio y no se sabe → `no_se_sabe`; el panel dijo
  que no (con su aviso) o nada salio → `fallo`.
* **Los documentos se validan antes** y la huella del pedido no carga el
  contenido entero.
* **El enlace no queda en el registro**; la firma vuelve como si/no.
* **Las rutas**: contrato angosto, `origen` armado por el motor, codigos.

No habla con ningun proveedor.

    python tests/test_contrato_del_proveedor.py
"""
from __future__ import annotations

import base64
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
from nucleo.herramientas import web                                # noqa: E402
from nucleo.persistencia import db as persistencia                 # noqa: E402
from nucleo.seguimiento import alta_de_cliente as alta             # noqa: E402
from nucleo.seguimiento import contrato_del_proveedor as cp        # noqa: E402
from nucleo.seguridad import frontera, interruptor                 # noqa: E402

TENANT = "tenant-de-prueba"
ORIGEN = "contrato_del_proveedor:c-1:1"
IP = "172.16.9.37"
ENLACE = "http://portal.example/login-panel/AAAA.BBBB.CCCC/"

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


class HerrInst:
    nombre = "buscar_instalacion"
    busca_cliente_por_ip = True
    argumentos_fijos: dict = {}
    parametros_de_busqueda_por_ip = schema.ParametrosDeBusquedaPorIp(
        ip="ip", campo_id="id_servicio", campo_nombre_en_router="servicio",
        campo_documento="cedula", son_instalaciones=True, campo_usuario="usuario")


class HerrPreparar:
    nombre = "preparar_contrato"
    prepara_contrato_del_proveedor = True
    solo_lectura = False


class HerrEnlace:
    nombre = "enlace_de_firma"
    da_enlace_de_firma = True


class HerrFirma:
    nombre = "firma_del_contrato"
    lee_firma_del_contrato = True


class Config:
    variables_tenant: dict = {}
    pools_de_ip: list = []

    def __init__(self, herramientas=None):
        self.herramientas = ([HerrCrear(), HerrBuscar(), HerrInst(), HerrPreparar(),
                              HerrEnlace(), HerrFirma()] if herramientas is None
                             else herramientas)


DATOS = {"zona": 20049, "ip": IP, "plan": "PLAN FAMILIA",
         "cliente": {"nombre": "LAURA MARCELA", "apellido": "PINEDA ORTEGA",
                     "documento": "1234500001"}}
NOMBRE_EN_ROUTER = alta.leer_datos(DATOS, PARAMETROS)[0]["nombre_en_router"]
DOCS = [{"nombre": "cedula_por_delante-1.jpg", "tipo": "image/jpeg",
         "titulo": "Cédula por delante", "base64": base64.b64encode(b"A" * 3000).decode()},
        {"nombre": "recibo-1.jpg", "tipo": "image/jpeg", "titulo": "Recibo",
         "base64": base64.b64encode(b"B" * 3000).decode()}]


class Veredicto:
    def __init__(self, permitido=True):
        self.permitido = permitido
        self.estado = "activo" if permitido else "detenido"
        self.motivo = ""


class Registro:
    def __init__(self):
        self.filas: dict[str, dict] = {}

    def reclamar(self, tenant, clave, herramienta, argumentos_hash, origen,
                 segundos_vencida, reintentar_fallida=False):
        fila = self.filas.get(clave)
        if fila is None:
            self.filas[clave] = {"intentos": 1, "estado": "ejecutando", "respuesta": None,
                                 "huella": argumentos_hash}
            return {"decision": "ejecutar", "fila": self.filas[clave]}
        if fila.get("huella") not in (None, argumentos_hash):
            return {"decision": "rechazada", "fila": fila, "codigo": "CLAVE_REUTILIZADA"}
        if fila["estado"] == "exitosa":
            return {"decision": "repetida", "fila": fila}
        if fila["estado"] == "fallida":
            return {"decision": "fallida", "fila": fila}
        return {"decision": "en_curso", "fila": fila}

    def finalizar(self, tenant, clave, estado, respuesta=None, error=None):
        fila = self.filas.setdefault(clave, {"intentos": 1})
        fila["estado"] = estado
        fila["respuesta"] = respuesta


class Proveedor:
    """Las lecturas por IP (clientes e instalaciones) y el panel web."""

    def __init__(self, instalaciones=None, rompe_lectura=False, error_web=None,
                 contrato_id="4928", firmado=False, enlace=ENLACE):
        self.instalaciones = list(instalaciones if instalaciones is not None else [
            {"id_servicio": 8039, "ip": IP, "servicio": NOMBRE_EN_ROUTER,
             "cedula": "1234500001", "usuario": "laura-pineda@empresa"}])
        self.rompe_lectura = rompe_lectura
        self.error_web = error_web
        self.contrato_id, self.firmado, self.enlace = contrato_id, firmado, enlace
        self.lecturas: list[str] = []
        self.web: list[tuple[str, dict, object]] = []

    def ejecutar_http(self, herramienta, argumentos, tenant, variables_tenant=None):
        self.lecturas.append(herramienta.nombre)
        if self.rompe_lectura:
            raise RuntimeError("el proveedor no contesto")
        if herramienta.nombre == "buscar_instalacion":
            return {"results": [f for f in self.instalaciones if f["ip"] == argumentos["ip"]]}
        return {"results": []}

    def ejecutar_web(self, herramienta, argumentos, tenant, variables_tenant=None):
        self.web.append((herramienta.nombre, dict(argumentos), frontera.permiso_vigente()))
        if self.error_web is not None:
            raise self.error_web
        if herramienta.nombre == "preparar_contrato":
            return {"contrato_id": self.contrato_id}
        if herramienta.nombre == "enlace_de_firma":
            return {"enlace": self.enlace}
        return {"firmado": self.firmado}


@contextlib.contextmanager
def escenario(registro, proveedor, permitido=True, interruptor_rompe=False):
    originales = (persistencia.reclamar_operacion_externa,
                  persistencia.finalizar_operacion_externa,
                  interruptor.veredicto, interruptor.anotar_bloqueo,
                  ejecutor_http.ejecutar, web.ejecutar)
    persistencia.reclamar_operacion_externa = registro.reclamar
    persistencia.finalizar_operacion_externa = registro.finalizar

    def _veredicto(t):
        if interruptor_rompe:
            raise RuntimeError("la base no responde")
        return Veredicto(permitido)

    interruptor.veredicto = _veredicto
    interruptor.anotar_bloqueo = lambda *a, **k: None
    ejecutor_http.ejecutar = proveedor.ejecutar_http
    web.ejecutar = proveedor.ejecutar_web
    try:
        yield
    finally:
        (persistencia.reclamar_operacion_externa,
         persistencia.finalizar_operacion_externa,
         interruptor.veredicto, interruptor.anotar_bloqueo,
         ejecutor_http.ejecutar, web.ejecutar) = originales


def preparar(config=None, origen=ORIGEN, id_servicio=8039, archivos=DOCS, datos=DATOS):
    with redirect_stdout(StringIO()):
        return cp.preparar(config or Config(), TENANT, actor="Dilan Moreno", origen=origen,
                           datos=datos, id_servicio=id_servicio, archivos=archivos)


# --------------------------------------------------------------------------- #
seccion("1. se prepara UNA vez, por la puerta humana, con el usuario de SU instalacion")
reg, prov = Registro(), Proveedor()
with escenario(reg, prov):
    r = preparar()
    afirmar(r.estado == cp.PREPARADO and r.contrato_id == "4928"
            and r.usuario == "laura-pineda@empresa", f"preparado, con contrato y usuario ({r})")
    afirmar(len(prov.web) == 1, "una sola escritura en el panel")
    nombre, args, permiso = prov.web[0]
    afirmar(permiso is not None and permiso.clase == "humana" and permiso.actor == "Dilan Moreno"
            and permiso.origen == ORIGEN, "sale con el permiso HUMANO de quien confirmo")
    afirmar(args.get("id_servicio") == 8039 and [a["titulo"] for a in args["archivos"]] ==
            ["Cédula por delante", "Recibo"], "viajan el numero y los documentos con su titulo")
    afirmar("buscar_instalacion" in prov.lecturas, "antes de escribir, leyo la instalacion")
    huella = next(iter(reg.filas.values()))["huella"]
    afirmar(DOCS[0]["base64"] not in str(huella), "la huella del pedido no carga el contenido")
    r2 = preparar()
    afirmar(r2.estado == cp.PREPARADO and r2.contrato_id == "4928" and len(prov.web) == 1,
            "el MISMO pedido otra vez: devuelve el contrato de la primera vez sin tocar el panel")

# --------------------------------------------------------------------------- #
seccion("2. si la instalacion no esta, no es suya o no trae el usuario: CERO escrituras")
casos = [
    ("otro numero", Proveedor(), dict(id_servicio=9999), cp.NO_ENCONTRADA),
    ("otro cliente en esa IP", Proveedor(instalaciones=[
        {"id_servicio": 8039, "ip": IP, "servicio": "OTRA PERSONA", "cedula": "999",
         "usuario": "otra@empresa"}]), {}, cp.NO_ENCONTRADA),
    ("sin usuario", Proveedor(instalaciones=[
        {"id_servicio": 8039, "ip": IP, "servicio": NOMBRE_EN_ROUTER,
         "cedula": "1234500001", "usuario": ""}]), {}, cp.SIN_USUARIO),
    ("la lectura falla", Proveedor(rompe_lectura=True), {}, cp.NO_SE_PUDO_COMPROBAR),
]
for que, prov, kw, esperado in casos:
    with escenario(Registro(), prov):
        r = preparar(**kw)
    afirmar(r.estado == esperado and prov.web == [], f"{que}: {esperado}, sin escribir ({r.estado})")

# --------------------------------------------------------------------------- #
seccion("3. el interruptor, pegado a la escritura")
for que, kw in (("detenido", dict(permitido=False)), ("ilegible", dict(interruptor_rompe=True))):
    prov = Proveedor()
    with escenario(Registro(), prov, **kw):
        r = preparar()
    afirmar(r.estado == cp.BLOQUEADO and prov.web == [], f"interruptor {que}: no sale")

# --------------------------------------------------------------------------- #
seccion("4. «no se» no es «fallo», y lo que fallo no se reejecuta")
reg, prov = Registro(), Proveedor(error_web=web.ErrorWeb("paso 2", "no redirigio", envio=True))
with escenario(reg, prov):
    r = preparar()
    afirmar(r.estado == cp.NO_SE_SABE and r.emitido, f"salio y no se sabe: no_se_sabe ({r.estado})")
    prov.error_web = None
    r2 = preparar()
    afirmar(r2.estado == cp.BLOQUEADO and len(prov.web) == 1,
            "el mismo pedido NO se vuelve a mandar despues de un «no se»")
prov = Proveedor(error_web=web.ErrorWeb("paso 2", "no redirigio", envio=True,
                                        avisos=["El archivo es muy pequeño."]))
with escenario(Registro(), prov):
    r = preparar()
afirmar(r.estado == cp.FALLO and r.avisos == ["El archivo es muy pequeño."],
        "el panel dijo que no (con su aviso): fallo, con el aviso")
prov = Proveedor(error_web=web.ErrorWeb("entrada", "el panel freno", http_status=429))
with escenario(Registro(), prov):
    r = preparar()
afirmar(r.estado == cp.FALLO, "nada llego a salir (entrada frenada): fallo")
prov = Proveedor(error_web=ejecutor_http.ErrorHerramientaHttp("guarda de pruebas"))
with escenario(Registro(), prov):
    r = preparar()
afirmar(r.estado == cp.BLOQUEADO and not r.emitido, "la guarda lo freno: bloqueado, no salio")
prov = Proveedor(contrato_id="")
with escenario(Registro(), prov):
    r = preparar()
afirmar(r.estado == cp.NO_SE_SABE, "guardo y no devolvio el numero: no_se_sabe")

# --------------------------------------------------------------------------- #
seccion("5. los datos se validan ANTES de leer o escribir")
for que, kw in (("documento no base64", dict(archivos=[{"nombre": "x", "base64": "@@@"}])),
                ("demasiados documentos", dict(archivos=DOCS * 6)),
                ("sin numero", dict(id_servicio="")),
                ("datos incompletos", dict(datos={"ip": IP}))):
    prov = Proveedor()
    with escenario(Registro(), prov):
        r = preparar(**kw)
    afirmar(r.estado == cp.DATOS_INVALIDOS and prov.lecturas == [] and prov.web == [],
            f"{que}: datos_invalidos, sin tocar el proveedor")
prov = Proveedor()
with escenario(Registro(), prov):
    r = preparar(config=Config([HerrCrear(), HerrBuscar(), HerrInst()]))
afirmar(r.estado == cp.SIN_HERRAMIENTA, "sin la herramienta del contrato: sin_herramienta")

# --------------------------------------------------------------------------- #
seccion("6. el enlace no queda en el registro; la firma es si/no")
prov = Proveedor()
salida = StringIO()
with escenario(Registro(), prov), redirect_stdout(salida):
    r = cp.enlace(Config(), TENANT, usuario="laura-pineda@empresa", id_servicio="8039")
afirmar(r.estado == cp.LISTO and r.enlace == ENLACE, "devuelve el enlace")
afirmar(prov.web[0][1] == {"usuario": "laura-pineda@empresa", "id_servicio": 8039},
        "lo pide con el usuario y el numero")
afirmar("AAAA" not in salida.getvalue(), "el enlace NO aparece en el registro")
with escenario(Registro(), Proveedor(enlace="javascript:alert(1)")), redirect_stdout(StringIO()):
    r = cp.enlace(Config(), TENANT, usuario="u@e", id_servicio=1)
afirmar(r.estado == cp.NO_SE_PUDO_COMPROBAR and not r.enlace, "algo que no es un enlace web: no sale")
with escenario(Registro(), Proveedor()), redirect_stdout(StringIO()):
    r = cp.enlace(Config(), TENANT, usuario="", id_servicio=1)
afirmar(r.estado == cp.DATOS_INVALIDOS, "sin usuario: datos_invalidos")
for valor in (True, False):
    with escenario(Registro(), Proveedor(firmado=valor)), redirect_stdout(StringIO()):
        r = cp.firmado(Config(), TENANT, contrato_id="4928")
    afirmar(r.estado == cp.LISTO and r.firmado is valor, f"firmado = {valor}")
with escenario(Registro(), Proveedor(error_web=web.ErrorWeb("entrada", "freno", http_status=429))), \
        redirect_stdout(StringIO()):
    r = cp.firmado(Config(), TENANT, contrato_id="4928")
afirmar(r.estado == cp.NO_SE_PUDO_COMPROBAR and r.firmado is None,
        "si no se pudo leer, no dice ni si ni no")

# --------------------------------------------------------------------------- #
seccion("7. las rutas: contrato angosto, origen del motor, codigos")
from nucleo.canales import api                                       # noqa: E402

cliente = api.app.test_client()
vistos: list[dict] = []
viejos = (api._config_de, cp.preparar, cp.enlace, cp.firmado)
api._config_de = lambda t: object()


def _preparar(config, tenant, **kw):
    vistos.append(kw)
    return cp.ResultadoContrato(cp.PREPARADO, contrato_id="4928", usuario="u@e")


cp.preparar = _preparar
cp.enlace = lambda config, tenant, **kw: cp.ResultadoContrato(cp.LISTO, enlace=ENLACE)
cp.firmado = lambda config, tenant, **kw: cp.ResultadoContrato(cp.LISTO, firmado=True)
try:
    base = "/interno/contrato/c-9/"
    cuerpo = {"actor": "Dilan Moreno", "datos": DATOS, "intento": 2, "id_servicio": 8039,
              "archivos": DOCS}
    r = cliente.post(base + "preparar-contrato-proveedor?tenant=t", json=cuerpo)
    afirmar(r.status_code == 200 and r.get_json()["contrato_id"] == "4928", "preparar: 200")
    afirmar(vistos and vistos[-1]["origen"] == "contrato_del_proveedor:c-9:2",
            "el origen lo arma el motor con el contrato y el numero de pedido")
    r = cliente.post(base + "preparar-contrato-proveedor?tenant=t",
                     json={**cuerpo, "origen": "otro"})
    afirmar(r.status_code == 400, "no acepta un origen de afuera")
    r = cliente.post(base + "preparar-contrato-proveedor?tenant=t", json={**cuerpo, "actor": ""})
    afirmar(r.status_code == 400, "sin actor: 400")
    r = cliente.post(base + "preparar-contrato-proveedor?tenant=t", json={**cuerpo, "intento": 0})
    afirmar(r.status_code == 400, "intento fuera de rango: 400")
    r = cliente.post(base + "preparar-contrato-proveedor", json=cuerpo)
    afirmar(r.status_code == 400, "sin tenant: 400")
    r = cliente.post(base + "enlace-de-firma?tenant=t", json={"usuario": "u@e", "id_servicio": 1})
    afirmar(r.status_code == 200 and r.get_json().get("enlace") == ENLACE, "enlace: 200")
    r = cliente.post(base + "firma-en-el-proveedor?tenant=t", json={"contrato_id": "4928"})
    afirmar(r.status_code == 200 and r.get_json().get("firmado") is True, "firma: 200, si/no")
    r = cliente.post(base + "firma-en-el-proveedor?tenant=t", json={"contrato_id": "1", "x": 1})
    afirmar(r.status_code == 400, "un campo de mas: 400")
    cp.preparar = lambda config, tenant, **kw: cp.ResultadoContrato(cp.NO_SE_SABE)
    r = cliente.post(base + "preparar-contrato-proveedor?tenant=t", json=cuerpo)
    afirmar(r.status_code == 202, "no se sabe: 202")
    cp.preparar = lambda config, tenant, **kw: cp.ResultadoContrato(cp.NO_ENCONTRADA)
    r = cliente.post(base + "preparar-contrato-proveedor?tenant=t", json=cuerpo)
    afirmar(r.status_code == 409, "no encontrada: 409")
finally:
    api._config_de, cp.preparar, cp.enlace, cp.firmado = viejos

# ---------------------------------------------------------------------------
print()
if _fallos:
    print(f"FALLARON {len(_fallos)}:")
    for f in _fallos:
        print("  -", f)
    sys.exit(1)
print("TODO OK")
