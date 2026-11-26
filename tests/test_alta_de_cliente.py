# -*- coding: utf-8 -*-
"""Un cliente se crea UNA vez, por la puerta humana, y solo si se pudo comprobar.

LO QUE ESTE ARCHIVO DEFIENDE  --  25/11/2026

* **Crear no es idempotente, y hay dos defensas.** La clave: el mismo pedido
  no sale dos veces, y uno que fallo NO se vuelve a ejecutar. El efecto: si la
  llamada salio y la respuesta se perdio, se encuentra al cliente por su IP y
  NO se crea otro. Se mide contando los clientes del proveedor, no un codigo.
* **«No se» no es «fallo».** Un corte, un 5xx o una ficha que no se reconoce
  NUNCA vuelven como FALLO: quien lee «fallo» anula el contrato y firma otro,
  y con el primer cliente quiza creado eso es crear dos (auditoria de
  frontera, el mismo dia). FALLO es solo cuando el proveedor DIJO que no.
* **Nada se crea si no se pudo comprobar.** IP de otro cliente, IP fuera de
  los rangos de la zona, plan que no esta, interruptor detenido o ilegible,
  lectura que falla o que contesta algo raro: CERO escrituras al proveedor.
* **Lo que confirma es la lectura, no el mensaje.**
* **Los nombres de los campos salen de la configuracion**, y lo que no se
  nombra ahi no viaja.
* **El secreto de la empresa viaja en la llamada y no queda en ningun lado.**
* **Las herramientas del alta no son de ningun agente ni de la ruta generica.**

No habla con ningun proveedor: el de aca es de mentira y tiene memoria.

    python tests/test_alta_de_cliente.py
"""
from __future__ import annotations

import contextlib
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.config import schema                                   # noqa: E402
from nucleo.persistencia import db as persistencia                 # noqa: E402
from nucleo.seguimiento import alta_de_cliente as alta             # noqa: E402
from nucleo.seguridad import frontera                              # noqa: E402

TENANT = "tenant-de-prueba"
ORIGEN = "alta_de_contrato:11111111-2222-3333-4444-555555555555:1"
ORIGEN_2 = "alta_de_contrato:11111111-2222-3333-4444-555555555555:2"
CREAR = "crear_cliente_del_contrato"
CLAVE = f"{ORIGEN}|{CREAR}"
ZONA = 20049
IP = "172.16.9.37"

_fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(("  OK   " if condicion else "  FALLA ") + que)
    if not condicion:
        _fallos.append(que)


def seccion(titulo: str) -> None:
    print("\n" + titulo)
    print("-" * len(titulo))


# --------------------------------------------------------------------------- #
#  La configuracion de una empresa cualquiera. Los nombres de los campos son
#  los de SU proveedor: el modulo no los conoce.
# --------------------------------------------------------------------------- #
PARAMETROS = schema.ParametrosDeAlta(
    zona="id_zona",
    campos={"nombre_en_router": "usuario_rb", "ip": "ip", "plan": "plan_internet",
            "nombre": "nombre", "apellido": "apellidos", "documento": "cedula",
            "correo": "email", "telefono": "telefono", "direccion": "direccion",
            "barrio": "localidad", "coordenadas": "coordenadas", "nota": "comentarios"},
    campo_tarea="task_id",
    secretos={"password_router_wifi": "CLAVE_ROUTER_WIFI"})


class HerrCrear:
    nombre = CREAR
    crea_cliente = True
    parametros_de_alta = PARAMETROS
    argumentos_fijos = {"usuario_router_wifi": "admin"}


class HerrBuscar:
    nombre = "buscar_cliente_por_ip"
    busca_cliente_por_ip = True
    argumentos_fijos: dict = {}
    parametros_de_busqueda_por_ip = schema.ParametrosDeBusquedaPorIp(
        ip="ip", campo_id="id_servicio", campo_nombre_en_router="servicio",
        campo_documento="cedula")


class HerrTarea:
    nombre = "leer_tarea"
    lee_tarea = True
    parametros_de_tarea = schema.ParametrosDeTarea(
        identificador="task_id", campo_estado="status",
        estados_terminada=["SUCCESS"], estados_fallida=["FAILURE"])


class HerrPlanes:
    nombre = "listar_planes"
    sincroniza_precio_plan = "listado"


class Pool:
    def __init__(self, zona_id, prefijos):
        self.zona_id, self.prefijos = zona_id, prefijos


class Config:
    variables_tenant: dict = {}

    def __init__(self, herramientas=None, pools=None):
        self.herramientas = ([HerrCrear(), HerrBuscar(), HerrTarea(), HerrPlanes()]
                             if herramientas is None else herramientas)
        #  DOS ZONAS, a proposito: con una sola, ignorar la zona al buscar el
        #  rango pasaria sin que nadie lo note.
        self.pools_de_ip = ([Pool(ZONA, ["172.16.9."]), Pool(777, ["10.77.0."])]
                            if pools is None else pools)


class Veredicto:
    def __init__(self, permitido=True):
        self.permitido = permitido
        self.estado = "activo" if permitido else "detenido"
        self.motivo = "" if permitido else "lo bajo Fulano por el incidente 42"


class Registro:
    """El registro de operaciones, con las reglas de la tabla real: la huella
    se compara PRIMERO, lo exitoso se repite, lo fallido no se reintenta salvo
    que se pida -- y el alta no lo pide nunca."""

    def __init__(self):
        self.filas: dict[str, dict] = {}
        self.pidieron_reintentar: list[bool] = []

    def reclamar(self, tenant, clave, herramienta, argumentos_hash, origen,
                 segundos_vencida, reintentar_fallida=False):
        self.pidieron_reintentar.append(bool(reintentar_fallida))
        fila = self.filas.get(clave)
        if fila is None:
            self.filas[clave] = {"intentos": 1, "estado": "ejecutando",
                                 "respuesta": None, "huella": argumentos_hash}
            return {"decision": "ejecutar", "fila": self.filas[clave]}
        if fila.get("huella") not in (None, argumentos_hash):
            return {"decision": "rechazada", "fila": fila,
                    "codigo": "CLAVE_REUTILIZADA"}
        if fila["estado"] == "exitosa":
            return {"decision": "repetida", "fila": fila}
        if fila["estado"] == "fallida":
            if not reintentar_fallida:
                return {"decision": "fallida", "fila": fila}
            fila["estado"] = "ejecutando"
            fila["intentos"] += 1
            return {"decision": "ejecutar", "fila": fila, "reintento": True}
        return {"decision": "en_curso", "fila": fila}

    def finalizar(self, tenant, clave, estado, respuesta=None, error=None):
        fila = self.filas.setdefault(clave, {"intentos": 1})
        fila["estado"] = estado
        fila["respuesta"] = respuesta


class ErrorHttp(Exception):
    """Como el de la libreria HTTP: trae la respuesta con su codigo."""

    def __init__(self, codigo):
        super().__init__(f"{codigo} para https://proveedor/api/?cedula=1234500001")
        self.response = type("R", (), {"status_code": codigo})()


class Proveedor:
    """Un proveedor de mentira CON MEMORIA: lo que se crea, despues se
    encuentra al buscar por IP. Sin memoria no se podria probar lo que mas
    importa: que un segundo intento no crea un segundo cliente."""

    def __init__(self, clientes=None, planes=None, aparece_tras=0,
                 rompe: str | None = None, crea=True, tarea="SUCCESS",
                 error_al_crear: BaseException | None = None, crea_igual=True,
                 guarda_como: str | None = None, forma_rara=...,
                 id_de_tarea="tarea-1"):
        self.clientes = list(clientes or [])
        self.planes = planes if planes is not None else [
            {"id": 197389, "nombre": "PLAN FAMILIA"},
            {"id": 197388, "nombre": "PLAN HOGAR"}]
        #: Cuantas busquedas tarda en verse un cliente recien creado.
        self.aparece_tras = aparece_tras
        self.rompe, self.crea, self.tarea = rompe, crea, tarea
        #: Lo que la llamada de crear levanta. `crea_igual` dice si, ademas,
        #: el proveedor aplico el pedido (la respuesta que se pierde).
        self.error_al_crear, self.crea_igual = error_al_crear, crea_igual
        #: El proveedor guarda el nombre en el router distinto de como llego.
        self.guarda_como = guarda_como
        #: Lo que contesta la busqueda por IP cuando contesta algo raro.
        self.forma_rara = forma_rara
        self.id_de_tarea = id_de_tarea
        self.llamadas: list[tuple[str, dict]] = []
        self.orden: list[str] = []            # tambien anota el interruptor
        self.permisos: list = []
        self._en_camino: list[list] = []      # [busquedas que faltan, fila]

    def ejecutar(self, herramienta, argumentos, tenant, variables_tenant=None):
        nombre = herramienta.nombre
        self.llamadas.append((nombre, dict(argumentos)))
        self.orden.append(nombre)
        if self.rompe == nombre:
            raise RuntimeError("el proveedor no contesto")
        if nombre == "listar_planes":
            return {"count": len(self.planes), "results": list(self.planes)}
        if nombre == "leer_tarea":
            return {"status": self.tarea, "result": "texto que no se guarda"}
        if nombre == "buscar_cliente_por_ip":
            if self.forma_rara is not ...:
                return self.forma_rara
            for par in self._en_camino:
                par[0] -= 1
            for par in [p for p in self._en_camino if p[0] < 0]:
                self.clientes.append(par[1])
                self._en_camino.remove(par)
            return {"results": [c for c in self.clientes
                                if c.get("ip") == argumentos.get("ip")]}
        if nombre == CREAR:
            self.permisos.append(frontera.permiso_vigente())
            aplica = self.crea and (self.error_al_crear is None or self.crea_igual)
            if aplica:
                fila = {"id_servicio": 9000 + len(self.clientes) + len(self._en_camino),
                        "ip": argumentos.get("ip"),
                        "servicio": self.guarda_como or argumentos.get("usuario_rb"),
                        "cedula": argumentos.get("cedula")}
                self._en_camino.append([self.aparece_tras, fila])
            if self.error_al_crear is not None:
                raise self.error_al_crear
            #  LA RESPUESTA, CON DE MAS A PROPOSITO: si el modulo guardara el
            #  cuerpo del proveedor, esto quedaria en el registro.
            return {"task_id": self.id_de_tarea, "messages": "recibido",
                    "cedula": "NO-DEBE-QUEDAR", "password_servicio": "NO-DEBE-QUEDAR"}
        raise AssertionError(f"herramienta inesperada: {nombre}")

    def de(self, nombre: str) -> list[dict]:
        return [a for n, a in self.llamadas if n == nombre]

    @property
    def escrituras(self) -> int:
        return len(self.de(CREAR))

    @property
    def nombres(self) -> list[str]:
        return [n for n, _ in self.llamadas]


@contextlib.contextmanager
def escenario(registro, proveedor, permitido=True, interruptor_rompe=False,
              secreto: str | None = "clave-del-equipo"):
    import nucleo.herramientas.http as ejecutor_http
    from nucleo.seguridad import interruptor, secretos

    originales = (persistencia.reclamar_operacion_externa,
                  persistencia.finalizar_operacion_externa,
                  interruptor.veredicto, interruptor.anotar_bloqueo,
                  ejecutor_http.ejecutar, secretos.obtener)
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
    secretos.obtener = lambda tenant, nombre: secreto
    try:
        afirmar(frontera.permiso_vigente() is None,
                "el andamio NO deja ningun permiso abierto")
        yield
    finally:
        (persistencia.reclamar_operacion_externa,
         persistencia.finalizar_operacion_externa,
         interruptor.veredicto, interruptor.anotar_bloqueo,
         ejecutor_http.ejecutar, secretos.obtener) = originales


def datos(**cambios) -> dict:
    d = {"zona": ZONA, "ip": IP, "plan": "PLAN FAMILIA",
         "cliente": {"nombre": "LAURA MARCELA", "apellido": "PINEDA ORTEGA",
                     "documento": "1234500001", "correo": "laura.pineda@example.com",
                     "telefono": "3005550101",
                     "direccion": "CRA 3B # 54-20 VILLA DEL SOL", "barrio": "VILLA DEL SOL"},
         "coordenadas": {"lat": 10.8982702, "lng": -74.8017717},
         "nota": "Contrato C-2026-000011"}
    d.update(cambios)
    return d


def crear(config=None, origen=ORIGEN, actor="Dilan Moreno", espera_s=0.2, **cambios):
    return alta.crear(config or Config(), TENANT, actor=actor, origen=origen,
                      datos=datos(**cambios), espera_s=espera_s, intervalo_s=0)


NOMBRE_EN_ROUTER = "LAURA MARCELA PINEDA ORTEGA"

# ---------------------------------------------------------------------------
seccion("1. se crea, UNA vez, por la puerta humana, y se confirma leyendo")
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor):
    r = crear()
afirmar(r.estado == alta.CREADO, f"queda creado (estado={r.estado}, motivo={r.motivo})")
afirmar(r.id_cliente == "9000", f"y trae el id que el proveedor le dio: {r.id_cliente!r}")
afirmar(proveedor.escrituras == 1, f"UNA sola escritura: {proveedor.escrituras}")
afirmar(proveedor.orden[:4] == ["buscar_cliente_por_ip", "listar_planes",
                                "(interruptor)", CREAR],
        "pregunta quien tiene la IP, despues el plan, y el INTERRUPTOR se lee "
        f"PEGADO a la escritura, no al principio: {proveedor.orden[:4]}")
afirmar(proveedor.orden[4] == "buscar_cliente_por_ip",
        "y despues de crear VUELVE A LEER: eso es lo que confirma")
p = proveedor.permisos[0] if proveedor.permisos else None
afirmar(p is not None and p.clase == "humana" and p.actor == "Dilan Moreno"
        and p.evidencia == ORIGEN,
        "la escritura salio con un permiso HUMANO: quien fue y con que contrato")
afirmar(list(registro.filas) == [CLAVE], f"una sola clave, la del pedido: {list(registro.filas)}")
afirmar(registro.pidieron_reintentar == [False],
        "y NUNCA se le pide al registro reejecutar algo que fallo")
afirmar(r.emitido is True, "el resultado dice que el pedido llego a emitirse")

# ---------------------------------------------------------------------------
seccion("2. el cuerpo lleva los nombres que el proveedor DECLARA")
cuerpo = proveedor.de(CREAR)[0]
afirmar(cuerpo.get("id_zona") == ZONA, "la zona, en el parametro de la URL")
afirmar(cuerpo.get("usuario_rb") == NOMBRE_EN_ROUTER,
        f"el nombre en el router es el nombre completo: {cuerpo.get('usuario_rb')!r}")
afirmar(cuerpo.get("plan_internet") == 197389,
        f"el plan viaja como SU ID del catalogo, no como texto: {cuerpo.get('plan_internet')!r}")
afirmar(cuerpo.get("ip") == IP and cuerpo.get("cedula") == "1234500001"
        and cuerpo.get("apellidos") == "PINEDA ORTEGA"
        and cuerpo.get("localidad") == "VILLA DEL SOL"
        and cuerpo.get("email") == "laura.pineda@example.com",
        "los datos del cliente, cada uno en su campo")
afirmar(cuerpo.get("coordenadas") == "10.898270,-74.801772",
        f"las coordenadas, lat,lng con coma y sin espacio: {cuerpo.get('coordenadas')!r}")
afirmar(cuerpo.get("usuario_router_wifi") == "admin",
        "lo que la empresa dejo fijo en su herramienta, viaja")
afirmar("plan" not in cuerpo and "nombre_en_router" not in cuerpo and "zona" not in cuerpo,
        "y los nombres de la PLATAFORMA no se cuelan al proveedor")

# ---------------------------------------------------------------------------
seccion("3. el secreto de la empresa viaja en la llamada y no queda en ningun lado")
afirmar(cuerpo.get("password_router_wifi") == "clave-del-equipo",
        "la clave del equipo va en el cuerpo que recibe el proveedor")
guardado = repr(registro.filas)
afirmar("clave-del-equipo" not in guardado, "y NO esta en el registro de operaciones")
afirmar("NO-DEBE-QUEDAR" not in guardado and "1234500001" not in guardado,
        "ni la respuesta del proveedor ni el documento quedan guardados: solo un acuse")
afirmar(registro.filas[CLAVE]["respuesta"] == {"pedido": True, "tarea": "tarea-1"},
        f"lo que queda es que se pidio y con que tarea: {registro.filas[CLAVE]['respuesta']}")
afirmar(r.avisos == [], "con el secreto cargado no hay nada que avisar")
afirmar("clave-del-equipo" not in repr(r.como_dict()), "ni viaja en el resultado")

registro2, proveedor2 = Registro(), Proveedor()
with escenario(registro2, proveedor2, secreto=None):
    r2 = crear()
cuerpo2 = proveedor2.de(CREAR)[0]
afirmar(r2.estado == alta.CREADO and "password_router_wifi" not in cuerpo2,
        "SIN el secreto cargado se crea igual y el campo NO viaja (ni vacio)")
afirmar(len(r2.avisos) == 1 and "CLAVE_ROUTER_WIFI" in r2.avisos[0],
        f"y el resultado lo DICE: {r2.avisos}")
afirmar(registro.filas[CLAVE]["huella"] == registro2.filas[CLAVE]["huella"],
        "la huella de la operacion es la MISMA con y sin secreto: no entra en ella")

# ---------------------------------------------------------------------------
seccion("4. LA RESPUESTA SE PERDIO: no es un fallo, y no se crea otro cliente")
registro, proveedor = Registro(), Proveedor(error_al_crear=RuntimeError("se corto"))
with escenario(registro, proveedor):
    primero = crear()
    segundo = crear()
afirmar(primero.estado == alta.CREADO and primero.id_cliente == "9000",
        f"se corto la respuesta, se MIRA, y el cliente esta: {primero.estado} {primero.id_cliente!r}")
afirmar(segundo.estado == alta.YA_ESTABA and segundo.id_cliente == "9000",
        f"y un segundo intento lo adopta: {segundo.estado}")
afirmar(proveedor.escrituras == 1 and len(proveedor.clientes) == 1,
        f"UNA escritura y UN cliente: {proveedor.escrituras} / {len(proveedor.clientes)}")

registro, proveedor = Registro(), Proveedor(error_al_crear=RuntimeError("se corto"),
                                            aparece_tras=50)
with escenario(registro, proveedor):
    primero = crear(espera_s=0)
    segundo = crear(espera_s=0)
    proveedor._en_camino[0][0] = 0          # el proveedor termina de crearlo
    despues = alta.comprobar(Config(), TENANT, datos=datos())
afirmar(primero.estado == alta.EN_CURSO,
        f"se corto y TODAVIA no aparece: EN CURSO, NO fallo ({primero.estado})")
afirmar(primero.estado != alta.FALLO and segundo.estado != alta.FALLO,
        "EL CONTROL: ninguno de los dos dice FALLO -- quien lee «fallo» anula y firma otro")
afirmar(segundo.estado == alta.EN_CURSO and proveedor.escrituras == 1,
        f"el mismo pedido otra vez NO sale de nuevo: {segundo.estado}, {proveedor.escrituras} escritura")
afirmar(despues.estado == alta.CREADO and len(proveedor.clientes) == 1,
        f"y cuando aparece, se da por creado. UN cliente: {despues.estado} / {len(proveedor.clientes)}")

# ---------------------------------------------------------------------------
seccion("5. repetir el mismo pedido ya creado no escribe nada")
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor):
    crear()
    otra = crear()
afirmar(otra.estado == alta.YA_ESTABA, f"dice que ya estaba: {otra.estado}")
afirmar(proveedor.escrituras == 1, f"UNA escritura en total: {proveedor.escrituras}")

# ---------------------------------------------------------------------------
seccion("6. ANTES de pedir, la IP la tiene OTRO cliente: no se crea")
ajeno = {"id_servicio": 4711, "ip": IP, "servicio": "OTRA PERSONA DISTINTA", "cedula": "999"}
registro, proveedor = Registro(), Proveedor(clientes=[ajeno])
with escenario(registro, proveedor):
    r = crear()
afirmar(r.estado == alta.IP_OCUPADA, f"ip ocupada: {r.estado}")
afirmar(proveedor.escrituras == 0 and registro.filas == {},
        "CERO escrituras, y ni siquiera se reclamo la operacion")
afirmar(r.id_cliente == "" and r.emitido is False,
        "no devuelve el id de un cliente ajeno, y dice que NO se emitio nada")

mismo_nombre_otro_doc = {"id_servicio": 4712, "ip": IP, "servicio": NOMBRE_EN_ROUTER,
                         "cedula": "8888888"}
registro, proveedor = Registro(), Proveedor(clientes=[mismo_nombre_otro_doc])
with escenario(registro, proveedor):
    r = crear()
afirmar(r.estado == alta.IP_OCUPADA and proveedor.escrituras == 0,
        f"el MISMO nombre con OTRO documento es otra persona: {r.estado}")

sin_doc = {"id_servicio": 4713, "ip": IP, "servicio": "laura marcela  pineda ortega", "cedula": ""}
registro, proveedor = Registro(), Proveedor(clientes=[sin_doc])
with escenario(registro, proveedor):
    r = crear()
afirmar(r.estado == alta.YA_ESTABA and r.id_cliente == "4713",
        f"el mismo nombre escrito distinto y sin documento ES el nuestro: {r.estado}")

# ---------------------------------------------------------------------------
seccion("7. si no se puede comprobar, o la respuesta no se entiende, no se crea")
registro, proveedor = Registro(), Proveedor(rompe="buscar_cliente_por_ip")
with escenario(registro, proveedor):
    r = crear()
afirmar(r.estado == alta.NO_SE_PUDO_COMPROBAR and proveedor.escrituras == 0,
        f"sin poder preguntar quien tiene la IP: {r.estado}, {proveedor.escrituras} escrituras")
afirmar("no contesto" not in r.motivo, "y el motivo lleva el TIPO del error, no su texto")

for rara, que in ((None, "null"), (5, "un numero"), (["x", "y"], "una lista de textos"),
                  ({"count": 3}, "un objeto sin la lista"), ("hola", "un texto"),
                  ({"results": "muchos"}, "una lista que no es lista")):
    registro, proveedor = Registro(), Proveedor(forma_rara=rara)
    with escenario(registro, proveedor):
        r = crear()
    afirmar(r.estado == alta.NO_SE_PUDO_COMPROBAR and proveedor.escrituras == 0,
            f"la busqueda contesta {que}: NO se lee como «nadie la tiene» ({r.estado})")
registro, proveedor = Registro(), Proveedor(forma_rara={"results": []})
with escenario(registro, proveedor):
    r = crear(espera_s=0)
afirmar(proveedor.escrituras == 1,
        "EL CONTROL: una lista vacia de verdad SI es «nadie la tiene», y se crea")

registro, proveedor = Registro(), Proveedor(rompe="listar_planes")
with escenario(registro, proveedor):
    r = crear()
afirmar(r.estado == alta.NO_SE_PUDO_COMPROBAR and proveedor.escrituras == 0,
        f"sin poder leer el catalogo de planes: {r.estado}")

# ---------------------------------------------------------------------------
seccion("8. un plan que el proveedor no tiene, o que tiene dos veces")
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor):
    r = crear(plan="PLAN QUE NO EXISTE")
afirmar(r.estado == alta.PLAN_DESCONOCIDO and proveedor.escrituras == 0,
        f"no esta en el catalogo: {r.estado}")
registro, proveedor = Registro(), Proveedor(planes=[{"id": 1, "nombre": "PLAN FAMILIA"},
                                                    {"id": 2, "nombre": "Plan Familia"}])
with escenario(registro, proveedor):
    r = crear()
afirmar(r.estado == alta.PLAN_DESCONOCIDO and proveedor.escrituras == 0,
        f"dos planes con el mismo nombre no se eligen a ojo: {r.estado}")

# ---------------------------------------------------------------------------
seccion("9. la IP tiene que ser de los rangos de ESA zona")


def fuera(que, **kw):
    registro, proveedor = Registro(), Proveedor()
    with escenario(registro, proveedor):
        r = crear(**kw)
    afirmar(r.estado == alta.IP_FUERA_DEL_RANGO and proveedor.llamadas == [],
            f"{que}: {r.estado}, y no se le pregunto NADA al proveedor")
    return r


fuera("otra red", ip="10.20.30.40")
fuera("el rango de OTRA zona no sirve para esta", ip="10.77.0.9")
#  Y al reves, que es lo que caza «tomar el primer rango sin mirar la zona»:
#  la IP es del rango de la PRIMERA zona y el contrato es de la segunda.
fuera("ni el de la primera zona sirve para la segunda", zona=777)
r = fuera("una zona sin rangos declarados", config=Config(pools=[]))
afirmar("rangos" in r.motivo, f"y dice por que: {r.motivo!r}")
fuera("un prefijo escrito sin su punto NO acepta la red de al lado",
      config=Config(pools=[Pool(ZONA, ["172.16.9"])]), ip="172.16.90.5")
fuera("un prefijo VACIO no acepta todo", config=Config(pools=[Pool(ZONA, [""])]))
fuera("un prefijo que no es un /24 no acepta nada",
      config=Config(pools=[Pool(ZONA, ["172.16."])]))
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor):
    r = crear(config=Config(pools=[Pool(ZONA, ["172.16.9"])]))
afirmar(r.estado == alta.CREADO,
        f"EL CONTROL: ese mismo prefijo sin punto SI acepta su propia red ({r.estado})")

#  LA IP QUE PODRIA SER LA DE UN CLIENTE MAL ESCRITO (25/11/2026): el proveedor
#  la da por libre --tiene escrita otra--, asi que la lectura viva no la frena.
mal_escrito = Config()
mal_escrito.contar_ip_mal_escritas = True
mal_escrito.ocupacion_ip = {"168.16.9.": [37]}
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor):
    r = crear(config=mal_escrito)
afirmar(r.estado == alta.IP_OCUPADA and "mal" in r.motivo and proveedor.llamadas == [],
        f"con la empresa prudente, la IP de un posible mal escrito no se usa: {r.estado}")
mal_escrito.contar_ip_mal_escritas = False
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor):
    r = crear(config=mal_escrito, origen=ORIGEN + "-apagada")
afirmar(r.estado == alta.CREADO, f"EL CONTROL: apagada, se crea como siempre ({r.estado})")

# ---------------------------------------------------------------------------
seccion("10. el interruptor: detenido o ilegible, no se crea")
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor, permitido=False):
    r = crear()
afirmar(r.estado == alta.BLOQUEADO and proveedor.escrituras == 0,
        f"detenido: {r.estado}, {proveedor.escrituras} escrituras")
afirmar("Fulano" not in r.motivo and "incidente" not in r.motivo,
        f"y lo que escribio quien lo bajo NO viaja a la pantalla del tecnico: {r.motivo!r}")
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor, interruptor_rompe=True):
    r = crear()
afirmar(r.estado == alta.BLOQUEADO and proveedor.escrituras == 0,
        f"no se pudo leer: {r.estado}, {proveedor.escrituras} escrituras (falla CERRADO)")
afirmar(registro.filas == {}, "y no quedo ninguna operacion reclamada")
afirmar("la base no responde" not in r.motivo, "sin el texto del error")

# ---------------------------------------------------------------------------
seccion("11. datos que no sirven: ni una llamada")
for cambio, que in (({"ip": ""}, "sin IP"), ({"ip": "172.16.9.1"}, "la puerta de enlace"),
                    ({"ip": "172.16.9.255"}, "el broadcast"), ({"ip": "::1"}, "IPv6"),
                    ({"zona": 0}, "sin zona"), ({"zona": True}, "zona booleana"),
                    ({"plan": " "}, "sin plan"),
                    ({"cliente": {"nombre": "", "apellido": "X"}}, "sin nombre")):
    registro, proveedor = Registro(), Proveedor()
    with escenario(registro, proveedor):
        r = crear(**cambio)
    afirmar(r.estado == alta.DATOS_INVALIDOS and proveedor.llamadas == [],
            f"{que}: {r.estado}, {len(proveedor.llamadas)} llamadas")

# ---------------------------------------------------------------------------
seccion("12. un dato vacio NO viaja")
registro, proveedor = Registro(), Proveedor()
cliente = dict(datos()["cliente"], correo="", telefono="")
with escenario(registro, proveedor):
    r = crear(cliente=cliente, coordenadas={"lat": 0, "lng": 0}, nota="")
cuerpo = proveedor.de(CREAR)[0]
afirmar(r.estado == alta.CREADO, f"se crea igual: {r.estado}")
afirmar(not ({"email", "telefono", "coordenadas", "comentarios"} & set(cuerpo)),
        f"correo, telefono, coordenadas 0,0 y nota vacios: la clave no esta -> {sorted(cuerpo)}")
afirmar(None not in cuerpo.values() and "" not in cuerpo.values(),
        "y ningun campo viaja nulo ni vacio")

# ---------------------------------------------------------------------------
seccion("13. se pidio y tarda: queda EN CURSO, y despues se comprueba sin escribir")
registro, proveedor = Registro(), Proveedor(aparece_tras=50, tarea="STARTED")
with escenario(registro, proveedor):
    r = crear(espera_s=0)
    afirmar(r.estado == alta.EN_CURSO and r.tarea == "tarea-1",
            f"en curso, con su tarea para volver a preguntar: {r.estado} {r.tarea!r}")
    antes = proveedor.escrituras
    c = alta.comprobar(Config(), TENANT, datos=datos(), tarea=r.tarea)
    afirmar(c.estado == alta.EN_CURSO, f"comprobar dice que sigue en curso: {c.estado}")
    proveedor._en_camino[0][0] = 0          # el proveedor termina
    c = alta.comprobar(Config(), TENANT, datos=datos(), tarea=r.tarea)
    afirmar(c.estado == alta.CREADO and c.id_cliente == "9000",
            f"y cuando aparece, comprobar lo da por creado: {c.estado} {c.id_cliente!r}")
    afirmar(proveedor.escrituras == antes == 1, "comprobar NO escribe: sigue habiendo una")

#  Para comprobar alcanza con lo minimo: donde buscar y como reconocerlo.
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor):
    crear()
    minimo = {"zona": ZONA, "ip": IP, "plan": "PLAN FAMILIA",
              "cliente": {"nombre": "LAURA MARCELA", "apellido": "PINEDA ORTEGA",
                          "documento": "1234500001"}}
    c = alta.comprobar(Config(), TENANT, datos=minimo)
afirmar(c.estado == alta.CREADO,
        f"comprobar reconoce al cliente sin correo, telefono ni domicilio: {c.estado}")

# ---------------------------------------------------------------------------
seccion("14. FALLO es solo cuando el proveedor DIJO que no")
registro, proveedor = Registro(), Proveedor(crea=False, tarea="SUCCESS")
with escenario(registro, proveedor):
    r = crear()
afirmar(r.estado == alta.FALLO and "no existe" in r.motivo,
        f"la tarea «termino bien» y la IP sigue LIBRE: no hay cliente ({r.estado})")
registro, proveedor = Registro(), Proveedor(crea=False, tarea="FAILURE")
with escenario(registro, proveedor):
    r = crear()
afirmar(r.estado == alta.FALLO, f"una tarea fallida con la IP libre, tambien: {r.estado}")
registro, proveedor = Registro(), Proveedor(aparece_tras=1, tarea="SUCCESS")
with escenario(registro, proveedor):
    r = crear()
afirmar(r.estado == alta.CREADO,
        f"EL CONTROL: si termino y el cliente aparece al volver a mirar, esta creado: {r.estado}")

for codigo, que in ((400, "un 400"), (422, "un 422"), (409, "un 409")):
    registro, proveedor = Registro(), Proveedor(error_al_crear=ErrorHttp(codigo),
                                                crea_igual=False)
    with escenario(registro, proveedor):
        r = crear()
    afirmar(r.estado == alta.FALLO and "rechazo" in r.motivo,
            f"{que} es el proveedor rechazando el pedido: FALLO ({r.estado})")
    afirmar("cedula" not in r.motivo and "1234500001" not in r.motivo,
            "y el motivo no arrastra el texto del error, que trae la URL")

for error, que in ((ErrorHttp(500), "un 500"), (ErrorHttp(502), "un 502"),
                   (ErrorHttp(408), "un 408"), (TimeoutError("tardo"), "un corte"),
                   (ValueError("no es JSON"), "una respuesta que no se pudo leer")):
    registro, proveedor = Registro(), Proveedor(error_al_crear=error, crea_igual=False)
    with escenario(registro, proveedor):
        r = crear(espera_s=0)
    afirmar(r.estado == alta.EN_CURSO,
            f"{que} NO dice si lo aplico: EN CURSO, nunca FALLO ({r.estado})")

# ---------------------------------------------------------------------------
seccion("15. la IP quedo tomada por una ficha que NO se reconoce: no es un fallo")
registro, proveedor = Registro(), Proveedor(guarda_como="L M PINEDA O", tarea="SUCCESS")
with escenario(registro, proveedor):
    r = crear()
    c = alta.comprobar(Config(), TENANT, datos=datos(), tarea="tarea-1")
afirmar(r.estado == alta.NO_RECONOCIDO,
        f"el proveedor guardo el nombre distinto: NO_RECONOCIDO, no FALLO ({r.estado})")
afirmar(r.id_cliente == "", "y NO se escribe el numero de una ficha que no se reconocio")
afirmar(c.estado == alta.NO_RECONOCIDO, f"comprobar dice lo mismo: {c.estado}")
afirmar(proveedor.escrituras == 1, "una sola escritura")

# ---------------------------------------------------------------------------
seccion("16. lo que fallo NO se vuelve a ejecutar; insistir es OTRO pedido")
registro, proveedor = Registro(), Proveedor(error_al_crear=ErrorHttp(400), crea_igual=False)
with escenario(registro, proveedor):
    r1 = crear()
    proveedor.error_al_crear = None
    r2 = crear(espera_s=0)
    sin_pedido_nuevo = proveedor.escrituras
    r3 = crear(origen=ORIGEN_2)
afirmar(r1.estado == alta.FALLO, f"el primero: el proveedor lo rechazo ({r1.estado})")
afirmar(sin_pedido_nuevo == 1,
        f"el MISMO pedido otra vez no sale: sigue habiendo {sin_pedido_nuevo} escritura")
afirmar(r2.estado != alta.CREADO, f"y no inventa un cliente: {r2.estado}")
afirmar(not any(registro.pidieron_reintentar), "nunca se pidio reejecutar lo fallido")
afirmar(r3.estado == alta.CREADO and proveedor.escrituras == 2,
        f"un pedido NUEVO --otro numero-- si sale: {r3.estado}, {proveedor.escrituras} escrituras")
afirmar(len(registro.filas) == 2, "y es otra clave")

# ---------------------------------------------------------------------------
seccion("17. la CLAVE, por su efecto: repetida, en curso y con otros argumentos")
registro, proveedor = Registro(), Proveedor(aparece_tras=50, tarea="STARTED")
registro.filas[CLAVE] = {"intentos": 1, "estado": "exitosa", "huella": None,
                         "respuesta": {"pedido": True, "tarea": "tarea-9"}}
with escenario(registro, proveedor):
    r = crear(espera_s=0)
afirmar(proveedor.escrituras == 0 and r.estado == alta.EN_CURSO and r.tarea == "tarea-9",
        f"ya se habia pedido con exito: NO sale otra vez, se mira con SU tarea ({r.estado}, {r.tarea!r})")

registro, proveedor = Registro(), Proveedor()
registro.filas[CLAVE] = {"intentos": 1, "estado": "ejecutando", "huella": None,
                         "respuesta": None}
with escenario(registro, proveedor):
    r = crear(espera_s=0)
afirmar(proveedor.escrituras == 0 and r.estado == alta.EN_CURSO,
        f"otro proceso lo esta pidiendo AHORA: no sale dos veces ({r.estado})")

registro, proveedor = Registro(), Proveedor()
registro.filas[CLAVE] = {"intentos": 1, "estado": "fallida", "huella": "la-de-otros-datos",
                         "respuesta": None}
with escenario(registro, proveedor):
    r = crear()
afirmar(proveedor.escrituras == 0 and r.estado == alta.BLOQUEADO,
        f"la misma clave con OTROS argumentos no sale: {r.estado}")

# ---------------------------------------------------------------------------
seccion("18. el ejecutor se niega antes de la red: bloqueado, no fallo")
import nucleo.herramientas.http as _http                            # noqa: E402

registro = Registro()
proveedor = Proveedor(error_al_crear=_http.ErrorHerramientaHttp(
    "'crear' no salio: falta la credencial SECRETO_DEL_PROVEEDOR"), crea_igual=False)
with escenario(registro, proveedor):
    r = crear()
afirmar(r.estado == alta.BLOQUEADO,
        f"la guarda de un entorno que no escribe afuera, o una credencial que falta: {r.estado}")
afirmar("SECRETO_DEL_PROVEEDOR" not in r.motivo and "credencial" not in r.motivo,
        f"y el texto del error no llega a la pantalla: {r.motivo!r}")
afirmar(len(proveedor.clientes) == 0, "en el proveedor no hay ningun cliente")

# ---------------------------------------------------------------------------
seccion("19. el id de la tarea va a parar a una RUTA: si no tiene forma de id, no se usa")
registro, proveedor = Registro(), Proveedor(aparece_tras=50, id_de_tarea="../clientes/1/perfil")
with escenario(registro, proveedor):
    r = crear(espera_s=0)
    alta.comprobar(Config(), TENANT, datos=datos(), tarea="../clientes/1/perfil")
afirmar(r.tarea == "" and registro.filas[CLAVE]["respuesta"]["tarea"] == "",
        f"no se guarda ni se devuelve: {r.tarea!r}")
afirmar(proveedor.de("leer_tarea") == [], "y no se le pide al proveedor esa ruta")

# ---------------------------------------------------------------------------
seccion("20. sin las herramientas declaradas no hay alta")
registro, proveedor = Registro(), Proveedor()
with escenario(registro, proveedor):
    r = crear(config=Config(herramientas=[HerrBuscar(), HerrPlanes()]))
    afirmar(r.estado == alta.SIN_HERRAMIENTA and proveedor.llamadas == [],
            f"sin la que crea: {r.estado}")
    r = crear(config=Config(herramientas=[HerrCrear(), HerrPlanes()]))
    afirmar(r.estado == alta.SIN_HERRAMIENTA and proveedor.llamadas == [],
            f"sin la que busca por IP TAMPOCO: no habria como comprobar ni confirmar ({r.estado})")
    r = crear(config=Config(herramientas=[HerrCrear(), HerrBuscar()]))
    afirmar(r.estado == alta.PLAN_DESCONOCIDO and proveedor.escrituras == 0,
            f"sin de donde leer los planes no se crea: {r.estado}")
    r = crear(config=Config(herramientas=[HerrCrear(), HerrBuscar(), HerrPlanes()]),
              origen=ORIGEN + "-sin-tarea")
    afirmar(r.estado == alta.CREADO,
            f"sin la que lee tareas SI: lo que confirma es la lectura por IP ({r.estado})")

# ---------------------------------------------------------------------------
seccion("21. la configuracion mal declarada se rechaza al cargar")


def rechaza(que: str, **kw) -> None:
    base = dict(zona="id_zona", campos={"nombre_en_router": "usuario_rb", "ip": "ip",
                                        "plan": "plan_internet"})
    base.update(kw)
    try:
        schema.ParametrosDeAlta(**base)
    except Exception:                                            # noqa: BLE001
        afirmar(True, f"se rechaza: {que}")
    else:
        afirmar(False, f"se rechaza: {que}")


rechaza("un dato que la plataforma no conoce (una contrasena, por ejemplo)",
        campos={"nombre_en_router": "usuario_rb", "ip": "ip", "plan": "plan_internet",
                "password_servicio": "password_servicio"})
rechaza("sin decir como se llama la IP", campos={"nombre_en_router": "usuario_rb",
                                                 "plan": "plan_internet"})
rechaza("dos datos al mismo campo", campos={"nombre_en_router": "usuario_rb", "ip": "ip",
                                            "plan": "plan_internet", "nombre": "usuario_rb"})
rechaza("un campo que es dato Y secreto", secretos={"ip": "ALGO"})
rechaza("un secreto sin nombre", secretos={"password_router_wifi": ""})
rechaza("un nombre en el router armado con un dato que no existe",
        nombre_en_router="{nombre} {telefono}")
rechaza("un nombre en el router fijo, igual para todos", nombre_en_router="cliente")
rechaza("sin zona", zona=" ")
try:
    schema.ParametrosDeAlta(zona="id_zona", nombre_en_router="{documento}",
                            campos={"nombre_en_router": "usuario_rb", "ip": "ip",
                                    "plan": "plan_internet"})
    afirmar(True, "EL CONTROL: otra costumbre valida (el documento) SI se acepta")
except Exception as e:                                           # noqa: BLE001
    afirmar(False, f"EL CONTROL: otra costumbre valida se acepta ({type(e).__name__})")

# ---------------------------------------------------------------------------
seccion("22. las herramientas del alta: ni de la ruta generica, ni de un agente")
ALTA_OK = dict(zona="id_zona", campos={"nombre_en_router": "usuario_rb", "ip": "ip",
                                       "plan": "plan_internet"})
BUSCA_OK = dict(ip="ip", campo_id="id_servicio")
TAREA_OK = dict(identificador="task_id", campo_estado="status", estados_terminada=["SUCCESS"])


def herramienta(**kw):
    base = dict(nombre="la_del_alta", tipo="http", endpoint="/api/x/{id_zona}/",
                base_url="https://api.ejemplo.io", descripcion="x",
                roles_permitidos=["administracion"], metodo="POST",
                solo_lectura=False, requiere_confirmacion=True)
    base.update(kw)
    return schema.Herramienta(**base)


def no_carga(que: str, **kw) -> None:
    try:
        herramienta(**kw)
    except Exception:                                            # noqa: BLE001
        afirmar(True, f"no carga: {que}")
    else:
        afirmar(False, f"no carga: {que}")


try:
    herramienta(crea_cliente=True, parametros_de_alta=ALTA_OK)
    herramienta(nombre="busca", metodo="GET", solo_lectura=True, requiere_confirmacion=False,
                busca_cliente_por_ip=True, parametros_de_busqueda_por_ip=BUSCA_OK)
    herramienta(nombre="tarea", metodo="GET", solo_lectura=True, requiere_confirmacion=False,
                lee_tarea=True, parametros_de_tarea=TAREA_OK)
    afirmar(True, "EL CONTROL: las tres, bien declaradas, cargan")
except Exception as e:                                           # noqa: BLE001
    afirmar(False, f"EL CONTROL: las tres, bien declaradas, cargan ({e})")

no_carga("la que crea, INVOCABLE POR UN SERVICIO (la ruta generica es la puerta autonoma)",
         crea_cliente=True, parametros_de_alta=ALTA_OK, invocable_por_servicio=True)
no_carga("la que busca por IP, invocable por un servicio (devolveria la ficha cruda)",
         metodo="GET", solo_lectura=True, requiere_confirmacion=False,
         busca_cliente_por_ip=True, parametros_de_busqueda_por_ip=BUSCA_OK,
         invocable_por_servicio=True)
no_carga("la que lee tareas, invocable por un servicio",
         metodo="GET", solo_lectura=True, requiere_confirmacion=False,
         lee_tarea=True, parametros_de_tarea=TAREA_OK, invocable_por_servicio=True)
no_carga("la marca de crear sin sus parametros", crea_cliente=True)
no_carga("los parametros de crear sin la marca", parametros_de_alta=ALTA_OK)
no_carga("la que crea, declarada de solo lectura",
         crea_cliente=True, parametros_de_alta=ALTA_OK, solo_lectura=True,
         requiere_confirmacion=False, metodo="GET")
no_carga("la que busca por IP, declarada de escritura",
         busca_cliente_por_ip=True, parametros_de_busqueda_por_ip=BUSCA_OK)

import yaml                                                          # noqa: E402

for marca in ("crea_cliente", "busca_cliente_por_ip", "lee_tarea"):
    doc = yaml.safe_load((RAIZ / "tenants" / "tenant.config.example.yaml").read_text(encoding="utf-8")) \
        if (RAIZ / "tenants" / "tenant.config.example.yaml").exists() else None
    if doc is None:
        afirmar(False, "hay una plantilla de tenant con la que probar el catalogo de un rol")
        break
    try:
        base_ok = schema.TenantConfig(**doc)
    except Exception as e:                                       # noqa: BLE001
        afirmar(False, f"la plantilla de tenant carga ({type(e).__name__})")
        break
    extra = {"crea_cliente": dict(crea_cliente=True, parametros_de_alta=ALTA_OK),
             "busca_cliente_por_ip": dict(metodo="GET", solo_lectura=True,
                                          requiere_confirmacion=False,
                                          busca_cliente_por_ip=True,
                                          parametros_de_busqueda_por_ip=BUSCA_OK),
             "lee_tarea": dict(metodo="GET", solo_lectura=True, requiere_confirmacion=False,
                               lee_tarea=True, parametros_de_tarea=TAREA_OK)}[marca]
    nueva = dict(nombre="la_del_alta", tipo="http", endpoint="/api/x/{id_zona}/",
                 base_url="https://api.ejemplo.io", descripcion="x",
                 roles_permitidos=[next(iter(doc["roles"]))], metodo="POST",
                 solo_lectura=False, requiere_confirmacion=True)
    nueva.update(extra)
    sola = dict(doc, herramientas=list(doc.get("herramientas") or []) + [nueva])
    try:
        schema.TenantConfig(**sola)
        carga_sola = True
    except Exception:                                            # noqa: BLE001
        carga_sola = False
    rol = next(iter(doc["roles"]))
    con_rol = yaml.safe_load(yaml.safe_dump(sola))
    con_rol["roles"][rol].setdefault("puede_consultar", []).append("la_del_alta")
    con_rol["roles"][rol].setdefault("campos_permitidos", {})["la_del_alta"] = ["id"]
    try:
        schema.TenantConfig(**con_rol)
        en_un_rol = True
    except Exception as e:                                       # noqa: BLE001
        en_un_rol = "alta" not in str(e)
    afirmar(carga_sola and not en_un_rol,
            f"'{marca}': carga fuera de todo rol y NO carga en el catalogo de un agente")

# ---------------------------------------------------------------------------
print()
if _fallos:
    print(f"FALLARON {len(_fallos)}:")
    for f in _fallos:
        print("  -", f)
    sys.exit(1)
print("TODO OK")
