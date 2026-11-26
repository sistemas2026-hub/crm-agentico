"""Una ONU se autoriza UNA vez, por la puerta humana, y solo si espera.

LO QUE ESTE ARCHIVO DEFIENDE  --  26/11/2026

* **Solo se escribe si el proveedor la lista esperando autorizacion.** El
  equipo central, la placa y el puerto salen de ESA fila, no de lo que mande el
  telefono. Una ONU que no espera, una ya autorizada, una lectura que falla o
  que contesta algo raro: CERO escrituras.
* **El interruptor se lee pegado a la escritura**, y detenido o ilegible no
  deja salir nada.
* **La escritura sale con un permiso HUMANO**, con la clave fija del pedido y
  sin reintentar lo que fallo.
* **«No se» no es «fallo».** Un corte o un 5xx al autorizar no vuelven como
  FALLO: se confirma leyendo, y si no aparece queda EN CURSO. FALLO es solo un
  4xx del proveedor.
* **Los nombres de los campos salen de la configuracion**; un dato vacio no
  viaja; el nombre va sin tildes ni signos que el proveedor rechace.
* **Las herramientas de la ONU no son de ningun agente ni de la ruta generica.**

No habla con ningun proveedor: el de aca es de mentira y tiene memoria.

    python tests/test_activar_onu.py
"""
from __future__ import annotations

import contextlib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.config import schema                                   # noqa: E402
from nucleo.persistencia import db as persistencia                 # noqa: E402
from nucleo.seguimiento import activar_onu as onu                  # noqa: E402
from nucleo.seguridad import frontera                              # noqa: E402

TENANT = "tenant-de-prueba"
ORIGEN = "activar_onu:11111111-2222-3333-4444-555555555555:1"
AUTORIZAR = "autorizar_onu"
SERIAL = "FHTT12345678"

_fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(("  OK   " if condicion else "  FALLA ") + que)
    if not condicion:
        _fallos.append(que)


def seccion(titulo: str) -> None:
    print("\n" + titulo)
    print("-" * len(titulo))


PARAMETROS = schema.ParametrosDeOnu(
    campos={"olt": "olt_id", "tipo_pon": "pon_type", "serial": "sn", "placa": "board",
            "puerto": "port", "tipo": "onu_type", "zona": "zone", "vlan": "vlan",
            "nombre": "name"},
    fila={"olt": "olt_id", "tipo_pon": "pon_type", "serial": "sn", "placa": "board",
          "puerto": "port", "tipo": "onu_type_name"},
    serial_en_la_lectura="sn")


class HerrBuscar:
    nombre = "buscar_onu"
    busca_onu_sin_autorizar = True
    argumentos_fijos: dict = {}


class HerrAutorizar:
    nombre = AUTORIZAR
    autoriza_onu = True
    parametros_de_onu = PARAMETROS
    argumentos_fijos: dict = {}


class HerrLeer:
    nombre = "leer_onu"
    lee_onu = True
    argumentos_fijos: dict = {}


class HerrZonas:
    nombre = "zonas"
    lista_zonas_de_red = True
    argumentos_fijos: dict = {}


class Config:
    variables_tenant: dict = {}

    def __init__(self, herramientas=None):
        self.herramientas = (herramientas if herramientas is not None
                             else [HerrBuscar(), HerrAutorizar(), HerrLeer(), HerrZonas()])


class Veredicto:
    def __init__(self, permitido=True):
        self.permitido = permitido
        self.estado = "activo" if permitido else "detenido"
        self.motivo = "" if permitido else "lo bajo alguien"


class Registro:
    """El registro de operaciones, con sus reglas: lo exitoso se repite, lo
    fallido no se reintenta salvo que se pida (y esto no lo pide nunca)."""

    def __init__(self):
        self.filas: dict[str, dict] = {}
        self.pidieron_reintentar: list[bool] = []

    def reclamar(self, tenant, clave, herramienta, argumentos_hash, origen,
                 segundos_vencida, reintentar_fallida=False):
        self.pidieron_reintentar.append(bool(reintentar_fallida))
        fila = self.filas.get(clave)
        if fila is None:
            self.filas[clave] = {"estado": "ejecutando", "huella": argumentos_hash}
            return {"decision": "ejecutar", "fila": self.filas[clave]}
        if fila["estado"] == "exitosa":
            return {"decision": "repetida", "fila": fila}
        if fila["estado"] == "fallida":
            return {"decision": "fallida", "fila": fila}
        return {"decision": "en_curso", "fila": fila}

    def finalizar(self, tenant, clave, estado, respuesta=None, error=None):
        self.filas.setdefault(clave, {})["estado"] = estado


class ErrorHttp(Exception):
    def __init__(self, codigo, cuerpo=...):
        super().__init__(f"{codigo}")

        def _json(_self):
            if cuerpo is ...:
                raise ValueError("sin cuerpo JSON")
            return cuerpo

        self.response = type("R", (), {"status_code": codigo, "json": _json})()


class Proveedor:
    """Con memoria: la ONU que se autoriza deja de esperar y pasa a leerse."""

    def __init__(self, esperando=True, autorizada=False, aparece_tras=0,
                 error_al_autorizar: BaseException | None = None, aplica_igual=True,
                 rompe: str | None = None, forma_rara=..., dos_iguales=False):
        self.esperando = [{"olt_id": "3", "pon_type": "gpon", "sn": SERIAL, "board": "3",
                           "port": "6", "onu_type_name": "FD714GS1-R850"}] if esperando else []
        if dos_iguales:
            self.esperando.append(dict(self.esperando[0]))
        #: Otra ONU cuyo serial CONTIENE al nuestro: el filtro es «contiene».
        self.esperando.append({"olt_id": "4", "pon_type": "gpon", "sn": SERIAL + "99",
                               "board": "0", "port": "1", "onu_type_name": "X"})
        self.autorizadas = {SERIAL} if autorizada else set()
        self.aparece_tras, self.error_al_autorizar = aparece_tras, error_al_autorizar
        self.aplica_igual, self.rompe, self.forma_rara = aplica_igual, rompe, forma_rara
        self.llamadas: list[tuple[str, dict]] = []
        self.orden: list[str] = []
        self.permisos: list = []
        self._lecturas_tras = None

    def ejecutar(self, herramienta, argumentos, tenant, variables_tenant=None):
        nombre = herramienta.nombre
        self.llamadas.append((nombre, dict(argumentos)))
        self.orden.append(nombre)
        if self.rompe == nombre:
            raise RuntimeError("el proveedor no contesto")
        if nombre == "buscar_onu":
            if self.forma_rara is not ...:
                return self.forma_rara
            return [f for f in self.esperando if argumentos.get("sn", "") in f["sn"]]
        if nombre == "leer_onu":
            if self._lecturas_tras is not None:
                self._lecturas_tras -= 1
                if self._lecturas_tras < 0:
                    self.autorizadas.add(SERIAL)
                    self._lecturas_tras = None
            if argumentos.get("sn") in self.autorizadas:
                return {"sn": argumentos["sn"], "status": "Online", "name": "NO-DEBE-QUEDAR"}
            raise ErrorHttp(400)
        if nombre == "zonas":
            return [{"id": 1, "name": "VILLA ADELA 2"}, {"id": 2, "name": "SAN VICENTE"}]
        if nombre == AUTORIZAR:
            self.permisos.append(frontera.permiso_vigente())
            if self.error_al_autorizar is None or self.aplica_igual:
                self.esperando = [f for f in self.esperando if f["sn"] != SERIAL]
                if self.aparece_tras:
                    self._lecturas_tras = self.aparece_tras
                else:
                    self.autorizadas.add(SERIAL)
            if self.error_al_autorizar is not None:
                raise self.error_al_autorizar
            return {"status": True, "response": "ONU authorized", "name": "NO-DEBE-QUEDAR"}
        raise AssertionError(f"herramienta inesperada: {nombre}")

    @property
    def escrituras(self) -> int:
        return len([1 for n, _ in self.llamadas if n == AUTORIZAR])

    def de(self, nombre):
        return [a for n, a in self.llamadas if n == nombre]


@contextlib.contextmanager
def escenario(registro, proveedor, permitido=True, interruptor_rompe=False):
    import nucleo.herramientas.http as ejecutor_http
    from nucleo.seguridad import interruptor

    originales = (persistencia.reclamar_operacion_externa,
                  persistencia.finalizar_operacion_externa,
                  interruptor.veredicto, interruptor.anotar_bloqueo, ejecutor_http.ejecutar)
    persistencia.reclamar_operacion_externa = registro.reclamar
    persistencia.finalizar_operacion_externa = registro.finalizar

    def _veredicto(t):
        proveedor.orden.append("(interruptor)")
        if interruptor_rompe:
            raise RuntimeError("la base no responde")
        return Veredicto(permitido)

    interruptor.veredicto = _veredicto
    interruptor.anotar_bloqueo = lambda *a, **k: None
    ejecutor_http.ejecutar = proveedor.ejecutar
    try:
        yield
    finally:
        (persistencia.reclamar_operacion_externa, persistencia.finalizar_operacion_externa,
         interruptor.veredicto, interruptor.anotar_bloqueo, ejecutor_http.ejecutar) = originales


def activar(config=None, origen=ORIGEN, **datos):
    d = {"serial": SERIAL.lower() + " ", "zona": "VILLA ADELA 2", "vlan": "300",
         "nombre": "José Peña-Ortíz, Jr."}
    d.update(datos)
    return onu.activar(config or Config(), TENANT, actor="Dilan Moreno", origen=origen,
                       datos=d, espera_s=0.2, intervalo_s=0)


seccion("1. se autoriza UNA vez, por la puerta humana, con el lugar de la FILA")
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor):
    r = activar()
afirmar(r.estado == onu.ACTIVADA, f"queda activada (estado={r.estado}, motivo={r.motivo})")
afirmar((r.olt, r.placa, r.puerto) == ("3", "3", "6"), "y dice donde: OLT 3, placa 3, puerto 6")
afirmar(proveedor.escrituras == 1, f"UNA sola escritura: {proveedor.escrituras}")
afirmar(proveedor.orden[:4] == ["leer_onu", "buscar_onu", "(interruptor)", AUTORIZAR],
        f"lee si ya estaba, busca si espera, y el interruptor PEGADO a la escritura: {proveedor.orden[:4]}")
afirmar(proveedor.orden[4] == "leer_onu", "y despues VUELVE A LEER: eso confirma")
p = proveedor.permisos[0] if proveedor.permisos else None
afirmar(p is not None and p.clase == "humana" and p.actor == "Dilan Moreno" and p.evidencia == ORIGEN,
        "salio con un permiso HUMANO: quien y con que pedido")
afirmar(list(registro.filas) == [f"{ORIGEN}|{AUTORIZAR}"], "una sola clave, la del pedido")
afirmar(registro.pidieron_reintentar == [False], "y nunca se pide reejecutar lo que fallo")
cuerpo = proveedor.de(AUTORIZAR)[0]
afirmar(cuerpo == {"olt_id": "3", "pon_type": "gpon", "sn": SERIAL, "board": "3", "port": "6",
                   "onu_type": "FD714GS1-R850", "zone": "VILLA ADELA 2", "vlan": 300,
                   "name": "JOSE PENA-ORTIZ JR."},
        f"el cuerpo con los nombres de la config, el lugar de la fila y el nombre limpio: {cuerpo}")

#  EL MODO (26/11/2026): el proveedor lo exige aunque su documentacion lo da
#  por opcional. Es de la empresa, en `argumentos_fijos` de la herramienta.
con_modo = HerrAutorizar()
con_modo.argumentos_fijos = {"onu_mode": "Routing"}
proveedor = Proveedor()
with escenario(Registro(), proveedor):
    r = onu.activar(Config([HerrBuscar(), con_modo, HerrLeer(), HerrZonas()]), TENANT,
                    actor="Dilan Moreno", origen=ORIGEN,
                    datos={"serial": SERIAL, "zona": "VILLA ADELA 2", "vlan": 300,
                           "nombre": "Jose"}, espera_s=5, intervalo_s=0)
cuerpo = proveedor.de(AUTORIZAR)[0] if proveedor.de(AUTORIZAR) else {}
afirmar(r.estado == onu.ACTIVADA and cuerpo.get("onu_mode") == "Routing",
        f"lo fijo de la empresa viaja en el pedido: {cuerpo.get('onu_mode')!r} ({r.estado})")

seccion("2. lo que NO escribe")
for titulo, prov, esperado in (
        ("ya autorizada", Proveedor(autorizada=True), onu.YA_ESTABA),
        ("no esta esperando", Proveedor(esperando=False), onu.NO_ESPERA),
        ("la busqueda no contesta", Proveedor(rompe="buscar_onu"), onu.NO_SE_PUDO_COMPROBAR),
        ("la lectura no contesta", Proveedor(rompe="leer_onu"), onu.NO_SE_PUDO_COMPROBAR),
        ("la busqueda contesta algo raro", Proveedor(forma_rara={"a": 1, "b": 2}), onu.NO_SE_PUDO_COMPROBAR),
        ("dos ONU esperando con el MISMO serial", Proveedor(dos_iguales=True), onu.NO_SE_PUDO_COMPROBAR)):
    with escenario(Registro(), prov):
        r = activar()
    afirmar(r.estado == esperado and prov.escrituras == 0,
            f"{titulo}: {r.estado} y CERO escrituras ({prov.escrituras})")
for titulo, kw in (("interruptor detenido", {"permitido": False}),
                   ("interruptor ilegible", {"interruptor_rompe": True})):
    prov = Proveedor()
    with escenario(Registro(), prov, **kw):
        r = activar()
    afirmar(r.estado == onu.BLOQUEADO and prov.escrituras == 0, f"{titulo}: bloqueado, CERO escrituras")
for titulo, kw in (("serial sin forma", {"serial": "ab"}), ("VLAN con letras", {"vlan": "trescientos"}),
                   ("VLAN fuera de rango", {"vlan": 5000})):
    prov = Proveedor()
    with escenario(Registro(), prov):
        r = activar(**kw)
    afirmar(r.estado == onu.DATOS_INVALIDOS and prov.escrituras == 0 and not prov.llamadas,
            f"{titulo}: datos invalidos, sin preguntar nada")
prov = Proveedor()
with escenario(Registro(), prov):
    r = activar(config=Config([HerrBuscar(), HerrLeer()]))
afirmar(r.estado == onu.SIN_HERRAMIENTA and not prov.llamadas, "sin la herramienta que autoriza: no hace nada")

seccion("3. «no se» no es «fallo»")
prov = Proveedor(error_al_autorizar=RuntimeError("corte"), aplica_igual=True)
with escenario(Registro(), prov):
    r = activar()
afirmar(r.estado == onu.ACTIVADA, f"se corto pero la ONU quedo: la lectura lo dice ({r.estado})")
prov = Proveedor(error_al_autorizar=ErrorHttp(502), aplica_igual=False)
with escenario(Registro(), prov):
    r = activar()
afirmar(r.estado == onu.EN_CURSO and r.estado != onu.FALLO,
        f"un 5xx sin ONU autorizada queda EN CURSO, NO fallo ({r.estado})")
prov = Proveedor(error_al_autorizar=ErrorHttp(400), aplica_igual=False)
with escenario(Registro(), prov):
    r = activar()
afirmar(r.estado == onu.FALLO, f"un 4xx es el proveedor diciendo que no: FALLO ({r.estado})")
afirmar(r.motivo == "el proveedor rechazo la autorizacion",
        f"sin cuerpo, el motivo de siempre ({r.motivo!r})")
#  EL MOTIVO DEL PROVEEDOR (26/11/2026): la primera prueba real volvio 400 dos
#  veces y no quedo por que.
prov = Proveedor(error_al_autorizar=ErrorHttp(400, {"status": False,
                 "error": "  The   ONU mode field is required. " + "x" * 300}), aplica_igual=False)
with escenario(Registro(), prov):
    r = activar()
afirmar(r.estado == onu.FALLO and "The ONU mode field is required." in r.motivo,
        f"el rechazo dice POR QUE, en una linea ({r.motivo!r})")
afirmar(len(r.motivo) <= len("el proveedor rechazo la autorizacion: ") + 160,
        f"y corto ({len(r.motivo)})")
for cuerpo, esperado in (({"message": "bad zone"}, "bad zone"),
                         ({"errors": {"vlan": ["invalid"]}}, '{"vlan": ["invalid"]}'),
                         ({"status": False}, ""), (["x"], ""), ("texto", "")):
    afirmar(onu.motivo_del_rechazo(ErrorHttp(400, cuerpo)) == esperado,
            f"motivo de {cuerpo!r} -> {esperado!r}")
prov = Proveedor(aparece_tras=2)
with escenario(Registro(), prov):
    r = onu.activar(Config(), TENANT, actor="x", origen=ORIGEN, datos={"serial": SERIAL},
                    espera_s=5, intervalo_s=0)
afirmar(r.estado == onu.ACTIVADA, f"una que tarda en verse se espera, y se confirma ({r.estado})")

seccion("4. el mismo pedido no sale dos veces")
registro, prov = Registro(), Proveedor(aparece_tras=10**9)
with escenario(registro, prov):
    r1 = activar()
    prov.esperando.insert(0, {"olt_id": "3", "pon_type": "gpon", "sn": SERIAL, "board": "3",
                              "port": "6", "onu_type_name": "FD714GS1-R850"})
    r2 = activar()
afirmar(r1.estado == onu.EN_CURSO and prov.escrituras == 1,
        f"el segundo pedido con la MISMA clave no escribe otra vez ({prov.escrituras} escrituras)")

seccion("5. buscar y comprobar SOLO leen")
prov = Proveedor()
with escenario(Registro(), prov):
    b = onu.buscar(Config(), TENANT, SERIAL)
    z = onu.zonas(Config(), TENANT)
    c = onu.comprobar(Config(), TENANT, SERIAL)
afirmar(b == {"estado": "esperando", "olt": "3", "placa": "3", "puerto": "6", "tipo": "FD714GS1-R850"},
        f"buscar dice donde espera: {b}")
afirmar(z == ["SAN VICENTE", "VILLA ADELA 2"], f"las zonas, ordenadas: {z}")
afirmar(c.estado == onu.EN_CURSO, "comprobar una que no esta autorizada: en curso")
afirmar(prov.escrituras == 0, "y ninguna de las tres escribio")

seccion("6. las herramientas de la ONU no son de ningun agente")
base = {"nombre": "h", "tipo": "http", "descripcion": "d", "roles_permitidos": ["administracion"],
        "base_url": "https://x", "endpoint": "/a", "metodo": "GET", "solo_lectura": True}
for marca, extra in (("busca_onu_sin_autorizar", {}), ("lee_onu", {}), ("lista_zonas_de_red", {}),
                     ("autoriza_onu", {"solo_lectura": False, "metodo": "POST",
                                       "parametros_de_onu": PARAMETROS.model_dump()})):
    try:
        schema.Herramienta.model_validate({**base, **extra, marca: True, "invocable_por_servicio": True})
        invocable = True
    except Exception:                                        # noqa: BLE001
        invocable = False
    afirmar(not invocable, f"'{marca}' NO puede ser invocable por un servicio")
try:
    schema.Herramienta.model_validate({**base, "autoriza_onu": True, "parametros_de_onu": PARAMETROS.model_dump()})
    lectura = True
except Exception:                                            # noqa: BLE001
    lectura = False
afirmar(not lectura, "la que autoriza NO puede declararse de solo lectura")
try:
    schema.Herramienta.model_validate({**base, "solo_lectura": False, "metodo": "POST", "autoriza_onu": True})
    sin_parametros = True
except Exception:                                            # noqa: BLE001
    sin_parametros = False
afirmar(not sin_parametros, "la que autoriza sin sus parametros no carga")
try:
    schema.Herramienta.model_validate({**base, "solo_lectura": False, "metodo": "POST",
                                       "form_urlencoded": True, "multipart": True})
    los_dos = True
except Exception:                                            # noqa: BLE001
    los_dos = False
afirmar(not los_dos, "formulario y multipart a la vez no carga")

# ---------------------------------------------------------------------------
print()
if _fallos:
    print(f"FALLARON {len(_fallos)}:")
    for f in _fallos:
        print("  -", f)
    sys.exit(1)
print("TODO OK")
