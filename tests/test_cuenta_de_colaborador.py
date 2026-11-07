# -*- coding: utf-8 -*-
"""
================================================================================
 LA CUENTA DE UN CLIENTE, PARA QUIEN LO ATIENDE
================================================================================

Por que existe
--------------
`consultar_mi_cuenta` entrega lo que debe quien esta verificado en la conversacion, y
el id sale de la SESION: el modelo no lo toca, porque con un id que escribe el modelo
una inyeccion de prompt pide la cuenta de otro cliente. Un colaborador (facturacion,
soporte) es otra cosa: atiende a un cliente y dice cual. Sin esta herramienta ve las
facturas pero no la suma (la haria el modelo, de cabeza) y la ficha le sigue diciendo
"saldo 0.00" a quien debe.

Es la MISMA proteccion puesta al reves, asi que la regla que importa es que NINGUN rol
de cliente pueda tenerla: el esquema lo impide, y esta prueba lo mide contra el
catalogo real de Rapilink, no contra uno armado a mano.

Que se afirma (el EFECTO)
-------------------------
  1. El esquema rechaza cargarla donde un cliente podria pasar un id.
  2. En el catalogo real la tienen exactamente `facturacion` y `soporte`.
  3. De punta a punta, con el catalogo real: el id que dice el colaborador llega al
     proveedor, la suma sale hecha, y un id mal formado no sale.
  4. Las fichas internas ya no dicen un saldo que vale siempre 0.00.

Uso:  py -3.13 tests/test_cuenta_de_colaborador.py
================================================================================
"""
import copy
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for var, valor in (("DBHOST", "localhost"), ("DBPORT", "5432"), ("DBNAME", "postgres"),
                   ("DBUSER", "postgres"), ("DBPASSWORD", "x")):
    os.environ.setdefault(var, valor)

import yaml                                                          # noqa: E402

from nucleo.config.schema import Herramienta, TenantConfig           # noqa: E402
from nucleo.herramientas import cuenta as C                          # noqa: E402
from nucleo.modelo import motor                                      # noqa: E402

FALLOS = []


def afirmar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        FALLOS.append(que)


def rechaza(fabrica):
    try:
        fabrica()
        return False
    except Exception:                                                # noqa: BLE001
        return True


RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
with open(os.path.join(RAIZ, "tenants", "rapilink.config.yaml"), encoding="utf-8") as f:
    DOC = yaml.safe_load(f)
CONFIG = TenantConfig.model_validate(DOC)
NOMBRE = "consultar_cuenta_de_cliente"
HERR = next(h for h in CONFIG.herramientas if h.nombre == NOMBRE)
HOY = date(2026, 11, 7)

print("=" * 72)
print(" LA CUENTA DE UN CLIENTE, PARA QUIEN LO ATIENDE")
print("=" * 72)

print("\n§1  EL ESQUEMA NO LA DEJA DONDE UN CLIENTE PODRIA PASAR UN ID")
base = HERR.model_dump()
afirmar(not rechaza(lambda: Herramienta(**base)), "la herramienta real de Rapilink es valida")
afirmar(rechaza(lambda: Herramienta(**{**base, "inyectar_sesion": {"id_servicio": "id_cliente"}})),
        "con el id inyectado de la sesion se rechaza (seria la version de clientes)")
afirmar(rechaza(lambda: Herramienta(**{**base, "filtros_verificados": {}, "requeridos": []})),
        "sin el id como argumento verificado se rechaza")
afirmar(rechaza(lambda: Herramienta(**{**base, "requeridos": []})),
        "con el id opcional se rechaza: sin el, la cuenta saldria de ningun cliente")
afirmar(rechaza(lambda: Herramienta(**{**base, "invocable_por_servicio": True})),
        "invocable por un servicio se rechaza (esa ruta no tiene a quien verificar)")
afirmar(rechaza(lambda: Herramienta(**{**base, "calcula_estado_de_cuenta": False})),
        "la marca de colaborador sin ser un estado de cuenta se rechaza")

para_cliente = copy.deepcopy(DOC)
para_cliente["roles"]["facturacion_cliente"]["puede_consultar"].append(NOMBRE)
para_cliente["roles"]["facturacion_cliente"]["campos_permitidos"][NOMBRE] = ["monto_pendiente"]
afirmar(rechaza(lambda: TenantConfig.model_validate(para_cliente)),
        "darsela a un rol de CLIENTE (puede_consultar) se rechaza al cargar la config")
nombrada = copy.deepcopy(DOC)
for h in nombrada["herramientas"]:
    if h["nombre"] == NOMBRE:
        h["roles_permitidos"] = ["facturacion", "facturacion_cliente"]
afirmar(rechaza(lambda: TenantConfig.model_validate(nombrada)),
        "nombrar a un rol de cliente en 'roles_permitidos' de la herramienta tambien se rechaza")
afirmar(not rechaza(lambda: TenantConfig.model_validate(DOC)), "y la config real sigue siendo valida")

print("\n§2  EN EL CATALOGO REAL LA TIENEN SOLO LOS COLABORADORES QUE LA NECESITAN")
con_ella = sorted(n for n, r in CONFIG.roles.items()
                  if NOMBRE in [h.nombre for h in motor.herramientas_del_rol(CONFIG, r)])
afirmar(con_ella == ["facturacion", "soporte"], f"la tienen exactamente facturacion y soporte ({con_ella})")
clientes = [n for n, r in CONFIG.roles.items() if r.orientado_a != "colaborador"]
afirmar(clientes and not [n for n in clientes if n in con_ella],
        f"ningun rol orientado a cliente la tiene ({clientes})")
vista_cliente = next(h for h in CONFIG.herramientas if h.nombre == "consultar_mi_cuenta")
afirmar("id_servicio" in vista_cliente.inyectados_obligatorios and not vista_cliente.cuenta_de_colaborador,
        "la version de clientes sigue exigiendo el id de la sesion")

print("\n§3  DE PUNTA A PUNTA, CON EL CATALOGO REAL")
FICHA = {"results": [{"id_servicio": "5832", "usuario": "ana-perez@isp", "saldo": "0.00"}]}
FACT = {"results": [
    {"id_factura": 1, "estado": "Pendiente de Pago", "total": "69900.00", "saldo": "0.00", "fecha_vencimiento": "2026-11-08"},
    {"id_factura": 2, "estado": "Pendiente de Pago", "total": "30000.00", "saldo": "0.00", "fecha_vencimiento": "2026-12-08"}]}
pedidos = []


def proveedor(herramienta, argumentos, tenant=None, variables_tenant=None):
    pedidos.append((herramienta.nombre, dict(argumentos)))
    return FICHA if herramienta.nombre == "consultar_mi_servicio" else FACT


real = C.ejecutor_http.ejecutar
C.ejecutor_http.ejecutar = proveedor
try:
    r = C.estado_de_cuenta(HERR, {"id_servicio": "5832"}, "t", {}, catalogo=CONFIG.herramientas, hoy=HOY)
finally:
    C.ejecutor_http.ejecutar = real
afirmar(r.get("disponible") is True and r.get("monto_pendiente") == "99900.00" and r.get("facturas_pendientes") == 2,
        f"la suma sale hecha (69.900 + 30.000 = 99.900) y no la hace el modelo ({r})")
afirmar(("consultar_mi_servicio", {"id_servicio": "5832"}) in pedidos,
        "el id que dijo el colaborador es el que se le pregunta al proveedor")
afirmar("link_de_pago" not in r and "otros_medios_de_pago" not in r,
        "no lleva link ni medios de pago: eso se le ofrece al cliente, no a quien lo atiende")

argumentos = motor._resolver_argumentos(HERR, None, {"id_servicio": "5832"}, None, {})
afirmar(argumentos.get("id_servicio") == "5832", f"el id del modelo pasa el filtro verificado ({argumentos})")
# El filtro NO valida el formato del id (medido): lo que protege es que el ejecutor solo
# acepta la ficha cuyo id_servicio es IDENTICO al pedido. Un id raro no coincide con
# ninguna, aunque el proveedor ignore el filtro y devuelva una ficha ajena.
C.ejecutor_http.ejecutar = proveedor
try:
    raro = C.estado_de_cuenta(HERR, {"id_servicio": "5832 OR 1=1"}, "t", {},
                              catalogo=CONFIG.herramientas, hoy=HOY)
finally:
    C.ejecutor_http.ejecutar = real
afirmar(raro.get("disponible") is False and "monto_pendiente" not in raro,
        "un id raro NO produce una cuenta, aunque el proveedor devuelva la ficha de otro")
afirmar(rechaza(lambda: motor._resolver_argumentos(HERR, None, {}, None, {})) or
        not motor._resolver_argumentos(HERR, None, {}, None, {}).get("id_servicio"),
        "sin id no hay argumento: la ficha sin filtro seria el universo")
sin_id = C.estado_de_cuenta(HERR, {}, "t", {}, catalogo=CONFIG.herramientas, hoy=HOY)
afirmar(sin_id.get("disponible") is False, "y el ejecutor, sin id, dice 'no disponible' en vez de consultar todo")

CENTINELA = {"__centinela__": "llego"}
original = motor.ejecutor_cuenta.estado_de_cuenta
motor.ejecutor_cuenta.estado_de_cuenta = lambda *a, **k: CENTINELA
try:
    por_modelo = motor._despacho_de_herramienta(HERR, {"id_servicio": "5832"}, "t", {})
finally:
    motor.ejecutor_cuenta.estado_de_cuenta = original
afirmar(por_modelo is CENTINELA, "el despacho del modelo llega al ejecutor de la cuenta")


class _Id:
    slug = "t_prueba"


class _Cfg:
    identidad = _Id()
    variables_tenant = {}
    roles = {}


try:
    motor.ejecutar_para_servicio(_Cfg(), HERR, {"id_servicio": "5832"})
    rechazo = None
except ValueError as e:
    rechazo = str(e)
afirmar(rechazo is not None and "invocable_por_servicio" in rechazo,
        "un servicio (sin sesion ni persona) NO puede pedir la cuenta de un cliente")

print("\n§4  LAS FICHAS INTERNAS YA NO DICEN UN SALDO QUE VALE SIEMPRE 0.00")
con_saldo = [(n, t) for n, r in CONFIG.roles.items() for t, campos in r.campos_permitidos.items()
             if t.startswith("consultar_cliente") and "saldo" in campos]
afirmar(not con_saldo, f"ninguna ficha de cliente lleva 'saldo' en ningun rol ({con_saldo})")
fact = CONFIG.roles["facturacion"]
afirmar("consultar_cuenta_de_cliente" in fact.descripcion and "SIEMPRE" in fact.descripcion,
        "y el agente de facturacion sabe de donde sale lo que se debe")
afirmar("saldo" not in (fact.campos_permitidos.get("consultar_cuenta_de_cliente") or []),
        "la herramienta no devuelve un campo 'saldo' que se pudiera leer como deuda")

print("\n§5  EL SCRIPT QUE LO APLICA A LA BASE (sin tocar la base: sobre la config de ANTES)")
from cli import aplicar_cuenta_de_colaborador as A                  # noqa: E402

antes = copy.deepcopy(DOC)
antes["herramientas"] = [h for h in antes["herramientas"] if h["nombre"] != NOMBRE]
for rol_n in A.ROLES_CON_LA_HERRAMIENTA:
    antes["roles"][rol_n]["puede_consultar"].remove(NOMBRE)
    del antes["roles"][rol_n]["campos_permitidos"][NOMBRE]
for rol_n in A.ROLES_CON_FICHA:
    for ficha in A.FICHAS:
        lista = antes["roles"][rol_n]["campos_permitidos"].get(ficha)
        if lista is not None:
            lista.append("saldo")
antes["roles"]["facturacion"]["descripcion"] = A.PROMPT_DE_ANTES
# Lo que la base tiene y el repo no tiene que sobrevivir (no se pisa con la lista del repo).
antes["roles"]["soporte"]["campos_permitidos"]["consultar_cliente"].append("campo_solo_de_la_base")
herr, campos, prompt = A.semilla("rapilink")
avisos = []
A.mutar(antes, herr, campos, prompt, avisos)
despues = TenantConfig.model_validate(antes)
afirmar(NOMBRE in [h.nombre for h in despues.herramientas], "agrega la herramienta y la config resultante VALIDA")
afirmar(sorted(n for n, r in despues.roles.items() if NOMBRE in r.puede_consultar) == ["facturacion", "soporte"],
        "se la da exactamente a facturacion y soporte")
afirmar(not [(n, t) for n, r in despues.roles.items() for t, c in r.campos_permitidos.items()
             if t.startswith("consultar_cliente") and "saldo" in c],
        "ninguna ficha de cliente queda con 'saldo'")
afirmar("campo_solo_de_la_base" in despues.roles["soporte"].campos_permitidos["consultar_cliente"],
        "conserva lo que la base tenia y el repo no")
afirmar(NOMBRE in despues.roles["facturacion"].descripcion, "el prompt de facturacion sabe de donde sale lo que se debe")
antes2 = copy.deepcopy(antes)
avisos2 = []
A.mutar(antes2, herr, campos, prompt, avisos2)
afirmar(antes2 == antes, "una segunda pasada no cambia nada (idempotente)")

editado = copy.deepcopy(DOC)
editado["herramientas"] = [h for h in editado["herramientas"] if h["nombre"] != NOMBRE]
editado["roles"]["facturacion"]["descripcion"] = "Un prompt que alguien edito desde /agentes."
for rol_n in A.ROLES_CON_LA_HERRAMIENTA:
    editado["roles"][rol_n]["puede_consultar"].remove(NOMBRE)
copia = copy.deepcopy(editado)
try:
    A.mutar(editado, herr, campos, prompt, [])
    aborto = False
except SystemExit:
    aborto = True
afirmar(aborto and editado == copia,
        "si el prompt ya no es el esperado, ABORTA sin escribir nada (ni la herramienta ni los permisos)")

print()
if FALLOS:
    print(f"  {len(FALLOS)} FALLA(S):")
    for f in FALLOS:
        print(f"   - {f}")
    sys.exit(1)
print("  Todo en orden.")
