# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DE COBERTURA  --  un cliente suelto no es cobertura, y un typo no es
                          "no tenemos servicio"
================================================================================

Los dos errores posibles al contestar "¿llegan a mi barrio?" no cuestan igual:

  * Decir que NO cuando SI hay: se pierde la venta, y se le dice algo falso a
    alguien que iba a contratar. No hay segunda oportunidad.
  * Decir que SI cuando NO hay: se le prometen planes y precios de otro lado, y
    alguien lo descubre cuando va a instalar.

El catalogo de localidades se arma recorriendo los CLIENTES de WispHub, asi que
dice "donde hay clientes", no "donde hay cobertura". De ahi salen los dos
casos que se fijan aca, los dos medidos el 28/08/2026.

CASO 1 -- un cliente suelto no alcanza
Un prospecto pregunto por "barrio centro". El catalogo dijo que si, con UN
unico cliente: JORGE FLOREZ, id 6185, del CENTRO de SABANAGRANDE. Si el
prospecto era de Soledad, se le ofrecieron los planes de fibra de otro
municipio.

'ciudad' no sirve para desambiguar: es texto libre y esta escrita de quince
formas para el mismo lugar (SOELDAD, SOLEDAF, SOLEDED, SOLEDDAD, y en un
registro hasta un correo electronico). La ZONA si -- son 5 nodos reales de un
catalogo cerrado. Por eso la salida ahora dice en cual cayo, para que el
asistente lo confirme antes de prometer nada.

CASO 2 -- "no esta" casi nunca significa "no hay cobertura"
Casi siempre significa que se escribio distinto. El catalogo trae los typos de
WispHub tal cual: 'VILLA SOL', 'VILLASOL' y 'VILL SOL' son el mismo barrio en
tres entradas. Antes, cualquiera de esos terminaba molestando a una persona.

    py -3.13 tests/test_cobertura_ventas.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.config.schema import (                 # noqa: E402
    LocalidadZona, PlanVenta, ZonaConteo, cargar_config)
from nucleo.modelo import motor                     # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(("  [OK]   " if condicion else "  [FALLA] ") + que)
    if not condicion:
        fallos.append(que)


cfg = cargar_config("tenants/rapilink.config.yaml")

# El catalogo de localidades NO esta en el YAML: es dato sincronizado y vive
# solo en la base (TenantConfig.SINCRONIZADOS). Se arma aca uno chico y
# deliberado, con los tres casos que importan -- asi la guarda corre sin base
# y no depende de que hoy Rapilink tenga tal o cual barrio cargado.
SABANA = ZonaConteo(zona_id=32278, zona_nombre="SERVIDOR SABANAGRANDE", n_clientes=1)
CORTE15 = ZonaConteo(zona_id=20053, zona_nombre="CORTE 15 - SERVIDOR 1", n_clientes=60)
cfg.localidades = [
    # El caso real: un barrio de nombre generico con UN solo cliente, que
    # resulto estar en otro municipio.
    LocalidadZona(localidad="CENTRO", zonas=[SABANA], n_clientes=1),
    # Evidencia de sobra: no hay que molestar a nadie confirmando.
    LocalidadZona(localidad="ZARABANDA", zonas=[CORTE15], n_clientes=60),
    # Los typos del propio WispHub, que llegan al catalogo tal cual.
    LocalidadZona(localidad="VILLA SOL", zonas=[CORTE15], n_clientes=40),
    LocalidadZona(localidad="VILLASOL", zonas=[CORTE15], n_clientes=3),
    LocalidadZona(localidad="DOÑA MANUELA", zonas=[CORTE15], n_clientes=84),
]
cfg.planes_venta = [PlanVenta(nombre_wisphub="PLAN FAMILIA", zonas=[20053]),
                    PlanVenta(nombre_wisphub="PLAN FIBRA", zonas=[32278])]


def cobertura(localidad):
    return motor._ejecutar_consulta_planes_venta(cfg, {"localidad": localidad})


print("=" * 70)
print(" GUARDA DE COBERTURA")
print("=" * 70)

# ---------------------------------------------------------------------- 1 --
print("\n[1] La salida dice en QUE ZONA cayo")
r = cobertura("zarabanda")
comprobar(r["cobertura"] is True, "una localidad conocida da cobertura")
comprobar(bool(r.get("zonas")), "y dice a que zona(s) pertenece")
comprobar(all(isinstance(z, str) and z for z in r["zonas"]),
          "con el NOMBRE del nodo, no su id (el modelo se lo lee al cliente)")

# ---------------------------------------------------------------------- 2 --
print("\n[2] Con muy pocos clientes, pide confirmar el municipio  <- el bug")
r = cobertura("centro")
comprobar(r.get("confirmar_zona") is True,
          "'CENTRO' (1 cliente) pide confirmar la zona antes de dar precios")
comprobar("zona" in (r.get("advertencia") or "").lower(),
          "y el aviso le dice al modelo QUE confirmar")
# Lo que NO puede pasar: convertirlo en "no hay cobertura". Ese es el error
# caro -- perder una venta diciendole algo falso a quien iba a contratar.
comprobar(r["cobertura"] is True,
          "pero NO se convierte en 'no hay cobertura' (ese es el error caro)")

print("\n[2b] Con evidencia suficiente NO molesta con la confirmacion")
r = cobertura("doña manuela")
comprobar(not r.get("confirmar_zona"),
          "'DOÑA MANUELA' (84 clientes) responde directo, sin preguntar de mas")

# ---------------------------------------------------------------------- 3 --
print("\n[3] Un nombre escrito distinto ofrece parecidos, no un traspaso")
# 'vila sol' no esta en el catalogo, pero VILLA SOL y VILLASOL si.
r = cobertura("vila sol")
comprobar(r["cobertura"] is False, "'vila sol' no matchea exacto")
comprobar(bool(r.get("similares")), f"pero ofrece parecidos: {r.get('similares')}")
comprobar("similares" in (r.get("advertencia") or "").lower(),
          "y el aviso le dice al modelo que se los pregunte")

print("\n[3b] Sin ningun parecido, recien ahi se confirma con una persona")
r = cobertura("qwerty zxcvbn 12345")
comprobar(r["cobertura"] is False and not r.get("similares"),
          "un nombre sin relacion no inventa sugerencias")
comprobar("no digas que no hay cobertura" in (r.get("advertencia") or "").lower(),
          "y sigue prohibiendo negar la cobertura")

# ---------------------------------------------------------------------- 4 --
print("\n[4] Nada de esto llama a la red")
# _ejecutar_consulta_planes_venta lee config, que ya esta en memoria del turno.
# Si algun dia alguien le agrega una llamada, este caso lo caza: se corre sin
# credenciales y sin salida a internet.
import os                                            # noqa: E402

sin_red = {k: v for k, v in os.environ.items() if "API_KEY" not in k}
guardado, os.environ = os.environ, sin_red
try:
    r = cobertura("zarabanda")
    comprobar(r["cobertura"] is True, "responde igual sin ninguna credencial cargada")
finally:
    os.environ = guardado

print("\n" + "=" * 70)
if fallos:
    print(f" {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    raise SystemExit(1)
print(" Todo en orden: ni se niega cobertura por un typo, ni se promete por un cliente.")
print("=" * 70)
