# -*- coding: utf-8 -*-
"""
================================================================================
 UN CLIENTE VERIFICADO QUE PREGUNTA DONDE PAGAR RECIBE LA RESPUESTA, DEBA O NO
================================================================================

Por que existe
--------------
07/11/2026, conversacion real: una clienta verificada, sin facturas pendientes, pregunto
«donde puedo pagar para una proxima» y el asistente contesto que ese dato no le llego.
Era cierto: el link y los medios de pago solo viajaban DENTRO de la cuenta, y solo con
una deuda. Un cliente al dia tiene el mismo derecho a saber como pagar, y el dato no es
de nadie: es igual para todos. Lo que importa es QUIEN pregunta, no que deba algo.

Esta herramienta no llama a ningun proveedor: lee las dos variables que la empresa carga
en Configuracion -> Pagos. Por eso responde aunque el sistema de facturas este caido.

Que se afirma (el EFECTO)
-------------------------
  1. El esquema solo la deja como herramienta de un cliente verificado (id de la sesion).
  2. En el catalogo real la tiene `facturacion_cliente`, y su lista blanca deja pasar
     lo que el modelo necesita para contestar.
  3. Por el camino real del motor: verificado, recibe link y medios SIN que haya deuda;
     sin verificar, la llamada no sale; sin nada cargado, lo dice (no inventa).
  4. No sale a la red: ni una llamada a un proveedor.

Uso:  py -3.13 tests/test_medios_de_pago_consulta.py
================================================================================
"""
import copy
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for var, valor in (("DBHOST", "localhost"), ("DBPORT", "5432"), ("DBNAME", "postgres"),
                   ("DBUSER", "postgres"), ("DBPASSWORD", "x")):
    os.environ.setdefault(var, valor)

import yaml                                                          # noqa: E402

from nucleo.config.schema import Herramienta, TenantConfig           # noqa: E402
from nucleo.herramientas import cuenta as C                          # noqa: E402
from nucleo.modelo import motor                                      # noqa: E402
from nucleo.seguridad import listas_blancas                          # noqa: E402

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
NOMBRE = "consultar_medios_de_pago"
HERR = next(h for h in CONFIG.herramientas if h.nombre == NOMBRE)

LINK = "https://pagos.ejemplo.co/rapilink"
MEDIOS = json.dumps([{"nombre": "Efecty", "instruccion": "Convenio 12345. Di tu cedula en caja."}])
CARGADO = {"LINK_DE_PAGO": LINK, "MEDIOS_DE_PAGO": MEDIOS}
VERIFICADO = SimpleNamespace(id_cliente="5832")
SIN_VERIFICAR = SimpleNamespace(id_cliente=None)

print("=" * 72)
print(" LOS MEDIOS DE PAGO, PARA UN CLIENTE VERIFICADO")
print("=" * 72)

print("\n§1  EL ESQUEMA SOLO LA DEJA PARA UN CLIENTE VERIFICADO")
base = HERR.model_dump()
afirmar(not rechaza(lambda: Herramienta(**base)), "la herramienta real de Rapilink es valida")
afirmar(rechaza(lambda: Herramienta(**{**base, "inyectar_sesion": {}, "inyectados_obligatorios": []})),
        "sin el id de la sesion se rechaza: cualquiera la podria llamar sin identificarse")
afirmar(rechaza(lambda: Herramienta(**{**base, "invocable_por_servicio": True})),
        "invocable por un servicio se rechaza (esa ruta no tiene a quien verificar)")
afirmar(rechaza(lambda: Herramienta(**{**base, "cuenta": {}})),
        "sin nombrar ninguna variable se rechaza: no entregaria nada")
afirmar(rechaza(lambda: Herramienta(**{**base, "tipo": "http", "base_url": "https://x.co", "endpoint": "/",
                                       "metodo": "GET"})),
        "como herramienta http se rechaza: no sale a ningun proveedor")
afirmar(rechaza(lambda: Herramienta(**{**base, "calcula_estado_de_cuenta": True})),
        "mezclada con el estado de cuenta se rechaza: son dos cosas distintas")

print("\n§2  EN EL CATALOGO REAL")
con_ella = sorted(n for n, r in CONFIG.roles.items()
                  if NOMBRE in [h.nombre for h in motor.herramientas_del_rol(CONFIG, r)])
afirmar(con_ella == ["facturacion_cliente"], f"la tiene facturacion_cliente y nadie mas ({con_ella})")
rol = CONFIG.roles["facturacion_cliente"]
respuesta = {"disponible": True, "hay_medios_de_pago": True, "link_de_pago": LINK,
             "otros_medios_de_pago": ["Efecty: Convenio 12345. Di tu cedula en caja."]}
vista = listas_blancas.filtrar_campos(rol, NOMBRE, respuesta)
afirmar(vista.get("link_de_pago") == LINK and vista.get("otros_medios_de_pago") == respuesta["otros_medios_de_pago"]
        and vista.get("hay_medios_de_pago") is True,
        f"la lista blanca del rol deja pasar link, medios y 'hay_medios_de_pago' ({sorted(vista)})")
afirmar("monto_pendiente" in CONFIG.roles["facturacion_cliente"].campos_permitidos["consultar_mi_cuenta"]
        and "monto_pendiente" not in (rol.campos_permitidos.get(NOMBRE) or []),
        "y no mezcla campos de la cuenta: cada herramienta dice lo suyo")
afirmar("consultar_medios_de_pago" in rol.descripcion and "DONDE" in rol.descripcion,
        "el prompt de cobro dice cuando usarla (pregunta donde o como pagar, deba algo o no)")

print("\n§3  POR EL CAMINO REAL DEL MOTOR")
# Cualquier salida a la red es un fallo: esta herramienta no habla con ningun proveedor.
salidas = []
real = C.ejecutor_http.ejecutar
C.ejecutor_http.ejecutar = lambda *a, **k: salidas.append(a) or {}


def llamar(sesion, variables):
    return motor._ejecutar_tool(HERR, sesion, {}, "t", variables)


try:
    r = llamar(VERIFICADO, CARGADO)
    afirmar(r.get("disponible") is True and r.get("link_de_pago") == LINK
            and r.get("otros_medios_de_pago") == ["Efecty: Convenio 12345. Di tu cedula en caja."]
            and r.get("hay_medios_de_pago") is True,
            f"verificado: recibe el link y los medios SIN que haya deuda de por medio ({r})")
    r = llamar(VERIFICADO, {"LINK_DE_PAGO": LINK})
    afirmar(r.get("link_de_pago") == LINK and "otros_medios_de_pago" not in r and r["hay_medios_de_pago"] is True,
            "si la empresa solo cargo el link, entrega solo el link")
    r = llamar(VERIFICADO, {"MEDIOS_DE_PAGO": MEDIOS})
    afirmar("link_de_pago" not in r and r.get("otros_medios_de_pago") and r["hay_medios_de_pago"] is True,
            "si solo cargo medios, entrega solo los medios")
    r = llamar(VERIFICADO, {})
    afirmar(r.get("disponible") is True and r.get("hay_medios_de_pago") is False
            and "link_de_pago" not in r and "otros_medios_de_pago" not in r,
            "sin nada cargado lo DICE (hay_medios_de_pago=false): una respuesta, no un error, y nada que inventar")
    r = llamar(VERIFICADO, {"LINK_DE_PAGO": "http://inseguro.co", "MEDIOS_DE_PAGO": "no es json"})
    afirmar(r.get("hay_medios_de_pago") is False and "link_de_pago" not in r,
            "un link sin https o un JSON roto NO se le da a un cliente (mismas reglas que la cuenta)")

    for sesion, que in ((SIN_VERIFICAR, "con la sesion sin verificar"), (None, "sin sesion")):
        try:
            llamar(sesion, CARGADO)
            salio = True
        except motor.FaltaIdentidadEnSesion:
            salio = False
        afirmar(not salio, f"{que}, la llamada NO sale: es la herramienta de un cliente verificado")
finally:
    C.ejecutor_http.ejecutar = real

print("\n§4  NO HABLA CON NINGUN PROVEEDOR")
afirmar(not salidas, f"ninguna llamada a un proveedor en todo lo anterior ({len(salidas)})")
afirmar(C.medios_de_pago_de_la_empresa(HERR, {}, "t", CARGADO).get("disponible") is False,
        "el ejecutor, sin id, dice 'no disponible' en vez de entregar")

CENTINELA = {"__centinela__": "llego"}
original = motor.ejecutor_cuenta.medios_de_pago_de_la_empresa
motor.ejecutor_cuenta.medios_de_pago_de_la_empresa = lambda *a, **k: CENTINELA
try:
    por_modelo = motor._despacho_de_herramienta(HERR, {"id_servicio": "5832"}, "t", {})
finally:
    motor.ejecutor_cuenta.medios_de_pago_de_la_empresa = original
afirmar(por_modelo is CENTINELA, "el despacho del modelo llega al ejecutor de los medios")


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
        "un servicio (sin sesion ni persona) NO la puede pedir")

print("\n§5  EL SCRIPT QUE LO APLICA A LA BASE (sin tocar la base: sobre la config de ANTES)")
from cli import aplicar_medios_de_pago_consulta as A                 # noqa: E402

antes = copy.deepcopy(DOC)
antes["herramientas"] = [h for h in antes["herramientas"] if h["nombre"] != NOMBRE]
antes["roles"]["facturacion_cliente"]["puede_consultar"].remove(NOMBRE)
del antes["roles"]["facturacion_cliente"]["campos_permitidos"][NOMBRE]
prompt_yaml = antes["roles"]["facturacion_cliente"]["descripcion"]
# El prompt de ANTES: sin el agregado (la frase de la que cuelga, sola).
antes["roles"]["facturacion_cliente"]["descripcion"] = prompt_yaml.replace(A.AGREGADO, A.ANCLA)
afirmar(antes["roles"]["facturacion_cliente"]["descripcion"] != prompt_yaml,
        "(el agregado del script es el que esta en el YAML: si no, esto no habria cambiado nada)")
atiende_yaml = antes["roles"]["facturacion_cliente"]["atiende"]
antes["roles"]["facturacion_cliente"]["atiende"] = atiende_yaml.replace(A.ATIENDE_NUEVO, A.ATIENDE_ANCLA)
afirmar(antes["roles"]["facturacion_cliente"]["atiende"] != atiende_yaml,
        "(el agregado al 'atiende' del script es el que esta en el YAML)")
antes["roles"]["soporte"]["campos_permitidos"]["consultar_cliente"].append("campo_solo_de_la_base")

herr, campos = A.semilla("rapilink")
avisos = []
A.mutar(antes, herr, campos, avisos)
despues = TenantConfig.model_validate(antes)
afirmar(NOMBRE in [h.nombre for h in despues.herramientas], "agrega la herramienta y la config resultante VALIDA")
afirmar(sorted(n for n, r in despues.roles.items() if NOMBRE in r.puede_consultar) == ["facturacion_cliente"],
        "se la da solo a facturacion_cliente")
afirmar(" ".join(despues.roles["facturacion_cliente"].descripcion.split()) == " ".join(prompt_yaml.split()),
        "el prompt queda IDENTICO al del YAML (el repo y la base dicen lo mismo)")
afirmar(" ".join(despues.roles["facturacion_cliente"].atiende.split()) == " ".join(atiende_yaml.split())
        and "donde y como pagar" in despues.roles["facturacion_cliente"].atiende,
        "el 'atiende' (lo que lee el router) tambien queda IDENTICO al del YAML")
afirmar("campo_solo_de_la_base" in despues.roles["soporte"].campos_permitidos["consultar_cliente"],
        "no toca lo que la base tenia y el repo no")
antes2 = copy.deepcopy(antes)
avisos2 = []
A.mutar(antes2, herr, campos, avisos2)
afirmar(antes2 == antes and "prompt: ya estaba" in avisos2, "una segunda pasada no cambia nada (idempotente)")

editado = copy.deepcopy(antes)
editado["herramientas"] = [h for h in editado["herramientas"] if h["nombre"] != NOMBRE]
editado["roles"]["facturacion_cliente"]["puede_consultar"].remove(NOMBRE)
editado["roles"]["facturacion_cliente"]["descripcion"] = "Un prompt que alguien edito desde /agentes."
copia = copy.deepcopy(editado)
try:
    A.mutar(editado, herr, campos, [])
    aborto = False
except SystemExit:
    aborto = True
afirmar(aborto and editado == copia,
        "si el prompt ya no tiene la frase de la que cuelga, ABORTA sin escribir nada (ni herramienta ni permisos)")

sin_ancla = copy.deepcopy(antes)
sin_ancla["herramientas"] = [h for h in sin_ancla["herramientas"] if h["nombre"] != NOMBRE]
sin_ancla["roles"]["facturacion_cliente"]["puede_consultar"].remove(NOMBRE)
sin_ancla["roles"]["facturacion_cliente"]["descripcion"] = prompt_yaml.replace(A.AGREGADO, A.ANCLA)
sin_ancla["roles"]["facturacion_cliente"]["atiende"] = "Un 'atiende' que alguien edito desde /agentes/flujo."
copia = copy.deepcopy(sin_ancla)
try:
    A.mutar(sin_ancla, herr, campos, [])
    aborto = False
except SystemExit:
    aborto = True
afirmar(aborto and sin_ancla == copia,
        "si el 'atiende' fue editado, ABORTA sin escribir nada (aunque el prompt si estuviera como esperaba)")

print()
if FALLOS:
    print(f"  {len(FALLOS)} FALLA(S):")
    for f in FALLOS:
        print(f"   - {f}")
    sys.exit(1)
print("  Todo en orden.")
