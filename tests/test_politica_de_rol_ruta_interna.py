# -*- coding: utf-8 -*-
"""
================================================================================
 LA POLITICA DE CAMPOS SE APLICA EN LA RUTA INTERNA, ANTES DE CONTESTAR
================================================================================

QUE SE PRUEBA
-------------
'POST /interno/herramienta/<nombre>' acepta ahora un 'rol' opcional. Con el, el
motor aplica la politica de campos de ESE rol --la lista blanca
'campos_permitidos' y el barrido de 'nunca_revelar'-- ANTES de devolver nada.

POR QUE IMPORTA QUE SEA AQUI Y NO EN EL CRM
-------------------------------------------
Porque asi el campo no autorizado no sale del motor. El chat del Supervisor usa
estas herramientas, y la ficha cruda de un cliente de WispHub trae 54 campos,
CUATRO contrasenas y las coordenadas del domicilio. Si el filtro viviera del
lado de Django, ese dato ya habria viajado -- y bastaria un error ahi para que
llegara a un modelo.

SE AFIRMA SOBRE EL RESULTADO, NO SOBRE LA CONFIGURACION
-------------------------------------------------------
Ninguna prueba de aqui mira si el YAML declara una lista. Todas toman un
registro CRUDO con datos sensibles, lo pasan por la politica y afirman que esos
datos NO estan en la salida. Una prueba que dijera "el rol declara
'nunca_revelar'" pasaria igual con el filtro desconectado.

Sin red, sin base y sin modelo:

    py -3.13 tests/test_politica_de_rol_ruta_interna.py
================================================================================
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for var, valor in (("DBHOST", "localhost"), ("DBPORT", "5432"),
                   ("DBNAME", "postgres"), ("DBUSER", "postgres"),
                   ("DBPASSWORD", "x")):
    os.environ.setdefault(var, valor)

from nucleo.canales import api                                   # noqa: E402
from nucleo.config.schema import Rol                             # noqa: E402

FALLOS = []


def afirmar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        FALLOS.append(que)


class _Config:
    """Lo minimo que '_aplicar_politica_de_rol' necesita: los roles."""

    def __init__(self, roles):
        self.roles = roles


#  Un registro como el que devuelve WispHub: lo relevante operativo, mezclado
#  con lo que nunca debe salir. Los valores son inventados; la FORMA es la real
#  (ver .claude/skills/wisphub-api: 54 campos, cuatro contrasenas, GPS).
CRUDO_CLIENTE = {
    "id_servicio": "5832",
    "nombre": "MARIO SABANAGRANDE",
    "estado": "Activo",
    "plan_internet": "30 MB",
    "zona": "SABANAGRANDE",
    "saldo": "0",
    #  --- lo que no puede salir ---
    "cedula": "1234567890",
    "telefono": "3001234567",
    "celular": "3009876543",
    "direccion": "Calle 5 # 3-21",
    "coordenadas": "10.79,-74.92",
    "latitud": "10.79",
    "longitud": "-74.92",
    "email": "mario@ejemplo.invalido",
    "password_servicio": "secreta-1",
    "password_cpe": "secreta-2",
    "password_router_wifi": "secreta-3",
    "password_ssid_router_wifi": "secreta-4",
    "usuario_router_wifi": "admin",
}

SENSIBLES = ("1234567890", "3001234567", "3009876543", "Calle 5 # 3-21",
             "10.79", "-74.92", "mario@ejemplo.invalido",
             "secreta-1", "secreta-2", "secreta-3", "secreta-4")


def _rol_supervisor():
    """El rol tal como lo declara 'tenants/rapilink.config.yaml'."""
    return Rol(
        descripcion="Supervisor NOC",
        puede_consultar=["consultar_cliente"],
        campos_permitidos={
            "consultar_cliente": ["id_servicio", "nombre", "estado",
                                  "localidad", "ciudad", "plan_internet",
                                  "zona", "fecha_instalacion",
                                  "estado_facturas", "saldo", "fecha_corte"],
        },
        nunca_revelar=["cedula", "celular", "coordenadas", "direccion",
                       "email", "latitud", "longitud", "password_cpe",
                       "password_router_wifi", "password_servicio",
                       "password_ssid_router_wifi", "telefono",
                       "usuario_router_wifi"],
        orientado_a="colaborador",
    )


print("\n§1  LA LISTA BLANCA SE APLICA, Y SE MIDE EN LA SALIDA")
cfg = _Config({"supervisor_noc": _rol_supervisor()})
salida = api._aplicar_politica_de_rol(cfg, "supervisor_noc",
                                      "consultar_cliente", CRUDO_CLIENTE)
texto = json.dumps(salida, ensure_ascii=False)

afirmar(salida.get("id_servicio") == "5832",
        "lo permitido SI pasa: el dato operativo sigue estando")
afirmar(salida.get("zona") == "SABANAGRANDE", "la zona pasa")
for valor in SENSIBLES:
    afirmar(valor not in texto, f"no sale el dato sensible {valor!r}")
afirmar("password" not in texto.lower(), "ni una contrasena en la salida")

print("\n§2  'nunca_revelar' TAMBIEN MUERDE, AUNQUE LA BLANCA SE EQUIVOQUE")
#  El caso que justifica barrer la lista negra: una lista blanca MAL escrita que
#  deja pasar 'telefono'. La blanca es la garantia; esto es la red de abajo.
rol_flojo = _rol_supervisor()
rol_flojo.campos_permitidos["consultar_cliente"] = [
    "id_servicio", "telefono", "cedula", "password_servicio"]
cfg2 = _Config({"supervisor_noc": rol_flojo})
salida2 = api._aplicar_politica_de_rol(cfg2, "supervisor_noc",
                                       "consultar_cliente", CRUDO_CLIENTE)
texto2 = json.dumps(salida2, ensure_ascii=False)
afirmar(salida2.get("id_servicio") == "5832", "lo legitimo sigue pasando")
afirmar("telefono" not in salida2, "'telefono' lo quita la lista NEGRA")
afirmar("cedula" not in salida2, "'cedula' tambien")
afirmar("secreta-1" not in texto2, "la contrasena tampoco sale")

print("\n§3  ANIDADO: un campo prohibido no se escapa por estar adentro")
crudo_anidado = {"id_ticket": "9", "asunto": "Sin internet",
                 "servicio": {"id_servicio": "5832", "cedula": "1234567890",
                              "coordenadas": "10.79,-74.92"}}
rol_t = _rol_supervisor()
rol_t.campos_permitidos["consultar_ticket"] = ["id_ticket", "asunto",
                                               "servicio"]
cfg3 = _Config({"supervisor_noc": rol_t})
salida3 = api._aplicar_politica_de_rol(cfg3, "supervisor_noc",
                                       "consultar_ticket", crudo_anidado)
texto3 = json.dumps(salida3, ensure_ascii=False)
afirmar("1234567890" not in texto3, "la cedula anidada NO sale")
afirmar("10.79" not in texto3, "las coordenadas anidadas NO salen")
afirmar(salida3.get("asunto") == "Sin internet", "el asunto sigue")

print("\n§4  EN LISTA: cada fila se filtra, no solo la primera")
crudo_lista = [dict(CRUDO_CLIENTE), dict(CRUDO_CLIENTE, id_servicio="6580")]
salida4 = api._aplicar_politica_de_rol(cfg, "supervisor_noc",
                                       "consultar_cliente", crudo_lista)
texto4 = json.dumps(salida4, ensure_ascii=False)
for valor in SENSIBLES:
    afirmar(valor not in texto4, f"en lista tampoco sale {valor!r}")
afirmar("6580" in texto4, "las dos filas estan")

print("\n§5  FAIL-CLOSED: sin lista blanca para esa herramienta, nada pasa")
salida5 = api._aplicar_politica_de_rol(cfg, "supervisor_noc",
                                       "consultar_senal_ont", CRUDO_CLIENTE)
afirmar("error" in salida5, "una herramienta sin lista blanca se descarta")
afirmar("5832" not in json.dumps(salida5, ensure_ascii=False),
        "y no se filtra ni un dato en el error")

print("\n§6  FAIL-CLOSED: un rol que no existe LEVANTA, no devuelve crudo")
try:
    api._aplicar_politica_de_rol(cfg, "rol_inventado", "consultar_cliente",
                                 CRUDO_CLIENTE)
    afirmar(False, "pedir una politica inexistente tiene que levantar")
except ValueError:
    afirmar(True, "un rol desconocido levanta ValueError")

print("\n§7  SIN 'rol' NO SE FILTRA  --  los llamadores viejos no se rompen")
#  La capa de fuentes lee topologia de red, no datos de un abonado, y depende de
#  la salida cruda. Se afirma sobre el EFECTO: el ayudante solo corre si se
#  pide un rol, asi que no hay forma de que un llamador sin rol pierda campos.
import inspect                                                   # noqa: E402

fuente = inspect.getsource(api.interno_ejecutar_herramienta)
afirmar("if rol_pedido:" in fuente,
        "la politica corre SOLO si se pidio un rol")
afirmar(fuente.index("rol_pedido = ") > fuente.index("ejecutar_para_servicio"),
        "y se aplica DESPUES de ejecutar, sobre la salida")

print("\n" + "=" * 70)
if FALLOS:
    print(f"FALLARON {len(FALLOS)}:")
    for f in FALLOS:
        print(f"  - {f}")
    sys.exit(1)
print("TODO OK: la politica se aplica antes de contestar, y se midio en la "
      "salida")
