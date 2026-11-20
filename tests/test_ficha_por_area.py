# -*- coding: utf-8 -*-
"""
================================================================================
 LA FICHA DEL CLIENTE SEGUN QUIEN MIRA  --  sin base, por la ruta real
================================================================================

    PYTHONIOENCODING=utf-8 py -3.13 tests/test_ficha_por_area.py

12/11/2026 (auditoria del menu, §1 punto 6). Corre sin base y sin red: se
sustituyen '_config_de', la identidad de la conversacion, la llamada al sistema
del ISP y la lectura de areas. El filtro, el schema y las rutas son los REALES.
La misma cadena contra PostgreSQL esta en tests/test_ficha_por_area_base.py.

Lo que se afirma, sobre el EFECTO (lo que sale por la ruta):
  A. el catalogo cubre todo lo que la Bandeja lee (si no, gestion perderia
     campos sin que nadie lo decida);
  B. el criterio: gestion ve todo; un area que declara ve exactamente eso; sin
     rol, sin area, area sin declarar o area desconocida -> defecto, que NO
     trae cedula, correo ni coordenadas;
  C. el schema rechaza un campo mal escrito;
  D. la ruta /conversaciones/<id>/cliente mantiene su forma y filtra; la base
     que falla (incluido SystemExit, D11) cae al defecto y no tumba el proceso;
  E. /ficha-cliente/visibilidad da el mismo criterio para el ticket.
================================================================================
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                      # noqa: E402
from nucleo.config import cargar_config, editor                     # noqa: E402
from nucleo.config.schema import (CAMPOS_FICHA_DEL_CLIENTE,         # noqa: E402
                                  AreaDeTrabajo)
from nucleo.seguridad import ficha_por_area as F                    # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str, detalle: str = "") -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}"
          + (f"\n          {detalle}" if detalle and not condicion else ""))
    if not condicion:
        fallos.append(que)


def documento() -> dict:
    """El volcado del primer tenants/*.config.yaml. No se nombra ninguno."""
    yamls = [p for p in sorted((RAIZ / "tenants").glob("*.config.yaml"))
             if not p.name.startswith("tenant.config.example")]
    return cargar_config(yamls[0]).model_dump(mode="json")


TENANT = "prueba"
DOC = documento()
#  Dos areas inventadas, sin nombre de ninguna empresa: una que declara su
#  ficha (sin cedula) y otra que no declara nada.
DOC["areas"] = list(DOC.get("areas") or []) + [
    {"nombre": "area_sin_cedula", "etiqueta": "Area A", "agentes": [],
     "ficha_cliente": ["nombre", "estado", "plan_internet", "telefono"]},
    {"nombre": "area_con_cedula", "etiqueta": "Area B", "agentes": [],
     "ficha_cliente": ["nombre", "cedula"]},
    {"nombre": "area_muda", "etiqueta": "Area C", "agentes": []},
]
CONFIG = editor._validar(TENANT, DOC)

FILA_ISP = {
    "id_servicio": 5832, "nombre": "TITULAR PRUEBA", "cedula": "1234567890",
    "estado": "Activo", "telefono": "3001112233", "email": "x@y.z",
    "direccion": "CALLE 1 # 2-3", "localidad": "BARRIO", "ciudad": "CIUDAD",
    "plan_internet": {"id": 7, "nombre": "PLAN 100"}, "zona": {"id": 1, "nombre": "Z1"},
    "fecha_instalacion": "2024-01-01", "estado_facturas": "Al dia", "saldo": "0.00",
    "fecha_corte": "2026-12-05",
    # Lo que la Bandeja nunca entrega, a nadie:
    "password_servicio": "SECRETO", "coordenadas": "4.1,-74.1",
}

areas_por_persona = {"p-sin-cedula": "area_sin_cedula", "p-con-cedula": "area_con_cedula",
                     "p-muda": "area_muda", "p-fantasma": "area_que_ya_no_existe"}
falla_areas: list = []


def _areas(tenant):
    if falla_areas:
        raise falla_areas[0]
    return dict(areas_por_persona)


api._config_de = lambda tenant: CONFIG
api.persistencia.identidad_de_conversacion = lambda tenant, cid: {"id_cliente": "5832"}
api.persistencia.areas_de_colaboradores = _areas
api.ejecutor_http.ejecutar = lambda h, args, tenant=None, variables_tenant=None: {"results": [dict(FILA_ISP)]}

cliente = api.app.test_client()


def ficha(rol=None, perfil=None):
    q = f"/conversaciones/c1/cliente?tenant={TENANT}"
    if rol is not None:
        q += f"&rol={rol}"
    if perfil is not None:
        q += f"&perfil={perfil}"
    r = cliente.get(q)
    return r.status_code, r.get_json()


print("=" * 74)
print(" LA FICHA DEL CLIENTE SEGUN QUIEN MIRA")
print("=" * 74)

print("\n== A. el catalogo ==")
faltan = [c for c in api.CAMPOS_FICHA_CLIENTE if c not in CAMPOS_FICHA_DEL_CLIENTE]
comprobar(not faltan, "todo lo que la Bandeja lee esta en el catalogo", str(faltan))
comprobar({"cedula", "email", "coordenadas"}.isdisjoint(F.DEFECTO_COLABORADOR),
          "el defecto deja afuera cedula, correo y coordenadas")
comprobar({"telefono", "direccion", "estado", "plan_internet", "saldo"} <= F.DEFECTO_COLABORADOR,
          "el defecto conserva telefono, direccion, estado, plan y saldo")

print("\n== B. el criterio (puro) ==")
for rol in ("ADMIN", "SUPERVISOR", "OPERACIONES", "admin"):
    v, c = F.campos_visibles(CONFIG, rol, "area_sin_cedula")
    comprobar(v == frozenset(CAMPOS_FICHA_DEL_CLIENTE) and c == "gestion",
              f"{rol}: la ficha entera, aunque su area diga otra cosa")
v, c = F.campos_visibles(CONFIG, "USER", "area_sin_cedula")
comprobar(v == {"nombre", "estado", "plan_internet", "telefono"} and c == "area",
          "un area que declara ve EXACTAMENTE lo declarado")
for rol, area, que in (("USER", None, "sin area"), (None, None, "sin rol"),
                       ("USER", "area_muda", "area que no declaro"),
                       ("USER", "area_que_ya_no_existe", "area que la config ya no tiene"),
                       ("ADMINISTRADOR", None, "rol desconocido"), ("BODEGA", None, "rol BODEGA")):
    v, c = F.campos_visibles(CONFIG, rol, area)
    comprobar(v == F.DEFECTO_COLABORADOR and c == "defecto", f"{que} -> defecto")
f = F.filtrar_ficha({"cedula": "1", "plan": "P", "plan_id": 7, "ip": "10.0.0.1",
                     "inventado": "x"}, {"plan_internet"})
comprobar(f == {"plan": "P", "plan_id": 7, F.CLAVE_OCULTOS: F.ocultos({"plan_internet"})},
          "filtrar conserva los alias del campo visible y tira lo no clasificado (ip, inventado)", str(f))
comprobar(F.filtrar_ficha("no es un dict", F.DEFECTO_COLABORADOR) == {},
          "una ficha que no es diccionario no pasa tal cual")

print("\n== C. el schema ==")
try:
    AreaDeTrabajo(nombre="x", etiqueta="X", ficha_cliente=["cédula"])
    comprobar(False, "un campo mal escrito se rechaza al cargar")
except ValueError:
    comprobar(True, "un campo mal escrito se rechaza al cargar")
comprobar(AreaDeTrabajo(nombre="x", etiqueta="X").ficha_cliente is None,
          "no declararlo es None (defecto), no 'todo'")
comprobar(AreaDeTrabajo(nombre="x", etiqueta="X", ficha_cliente=[]).ficha_cliente == [],
          "una lista vacia es valida: nada de la ficha")

print("\n== D. la ruta de la Bandeja ==")
s, admin = ficha("ADMIN", "p-sin-cedula")
comprobar(s == 200 and set(admin) == {"disponible", "motivo", "cliente"},
          "la forma de la respuesta no cambia", str(admin))
comprobar(admin["cliente"].get("cedula") == "1234567890" and admin["cliente"][F.CLAVE_OCULTOS] == [],
          "gestion recibe la cedula y nada oculto")
comprobar("password_servicio" not in admin["cliente"] and "coordenadas" not in admin["cliente"],
          "ni gestion recibe lo que la Bandeja no lee del ISP")
s, a = ficha("USER", "p-sin-cedula")
comprobar("cedula" not in a["cliente"] and "direccion" not in a["cliente"],
          "un colaborador de un area sin cedula NO la recibe (ni la direccion que no declaro)")
comprobar(a["cliente"].get("telefono") == "3001112233" and a["cliente"].get("plan_internet") == "PLAN 100",
          "y si recibe lo que su area declara")
comprobar("cedula" in a["cliente"][F.CLAVE_OCULTOS], "y la ficha dice que la cedula esta oculta")
s, b = ficha("USER", "p-con-cedula")
comprobar(b["cliente"].get("cedula") == "1234567890", "un area que declara la cedula la recibe")
for rol, perfil, que in ((None, None, "llamador viejo, sin rol ni perfil"),
                         ("USER", None, "sin perfil"), ("USER", "p-muda", "area sin declarar"),
                         ("USER", "p-fantasma", "area irresoluble"),
                         ("USER", "p-desconocido", "perfil sin area")):
    s, d = ficha(rol, perfil)
    comprobar("cedula" not in d["cliente"] and "email" not in d["cliente"]
              and d["cliente"].get("telefono") == "3001112233",
              f"{que}: defecto (sin cedula ni correo, con telefono)")
falla_areas.append(SystemExit(2))
s, d = ficha("USER", "p-con-cedula")
comprobar(s == 200 and "cedula" not in d["cliente"],
          "la base que lanza SystemExit cae al defecto y no tumba el proceso (D11)")
falla_areas[:] = [RuntimeError("caida")]
s, d = ficha("USER", "p-con-cedula")
comprobar(s == 200 and "cedula" not in d["cliente"], "la base caida cae al defecto")
falla_areas.clear()

print("\n== E. la visibilidad para el ticket ==")
r = cliente.get(f"/ficha-cliente/visibilidad?tenant={TENANT}&rol=USER&perfil=p-sin-cedula").get_json()
comprobar(r["criterio"] == "area" and "cedula" in r["ocultos"] and "plan" in r["campos"],
          "el ticket recibe el mismo criterio, con el alias 'plan' del plan", str(r))
r = cliente.get(f"/ficha-cliente/visibilidad?tenant={TENANT}").get_json()
comprobar(r["criterio"] == "defecto" and "cedula" not in r["campos"], "sin quien mira: defecto")
r = cliente.get(f"/ficha-cliente/visibilidad?tenant={TENANT}&rol=OPERACIONES").get_json()
comprobar(r["criterio"] == "gestion" and r["ocultos"] == [], "gestion: nada oculto")
comprobar(cliente.get("/ficha-cliente/visibilidad").status_code == 400, "sin empresa: 400")

print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] la ficha del cliente se filtra segun quien mira.")
