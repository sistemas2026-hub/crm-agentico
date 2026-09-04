# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DE LA GUARDA  --  lo que 'cargar_config' frena y lo que deja pasar
================================================================================

Por que existe
--------------
'cli/cargar_config.py' compara el YAML contra la config viva en base antes de
pisarla, porque la interfaz tambien escribe ahi y eso no esta en git. Es la
unica red entre "cargo mi archivo" y "borre el trabajo de otro".

Esa red se equivoco en las DOS direcciones, y las dos veces costo:

 - Se quedo CORTA (23/08/2026): una seccion que el archivo dejaba vacia entera
   no producia ninguna hoja que comparar, asi que 6 planes de venta curados a
   mano y 128 localidades sincronizadas no aparecian en el reporte. La guarda
   daba el visto bueno para borrarlos.

 - Se paso de LARGA (24/08/2026): comparaba las listas por POSICION, asi que
   insertar una herramienta al principio de 'puede_consultar' corria todos los
   indices y reportaba cada posicion siguiente como si hubiera cambiado. De 31
   avisos, 15 eran ese artefacto y ninguno era una perdida. Una guarda que
   grita de mas se vuelve el paso que todo el mundo saltea con --forzar, que
   es peor que no tenerla: la falsa alarma no es un detalle cosmetico.

Lo que se fija aca
------------------
1. Una lista de permisos se compara por CONTENIDO. Reordenar no es un cambio.
2. Si el archivo SUMA a una lista, no se reporta: agregar no es perder.
3. Si el archivo QUITA de una lista, se reporta -- y nombra que se pierde.
4. Una seccion que el archivo vacia entera se reporta (el caso invisible).
5. Un campo SINCRONIZADO no se reporta NI se pisa: es propiedad de la base.
6. Un valor distinto en una hoja suelta se sigue reportando (el bug original
   de 'canales.whatsapp.activo', que dejo el webhook devolviendo 401 a Meta).

Se corre sin base y sin red: son funciones puras sobre dos diccionarios.

    py -3.13 tests/test_guarda_cargar_config.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cli.cargar_config import _lo_que_pisaria           # noqa: E402
from nucleo.config.schema import TenantConfig           # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    if condicion:
        print(f"  [OK]   {que}")
    else:
        print(f"  [FALLA] {que}")
        fallos.append(que)


def _rol(**campos) -> dict:
    return {"roles": {"soporte": campos}}


print("=" * 70)
print(" GUARDA DE cargar_config._lo_que_pisaria")
print("=" * 70)

# ---------------------------------------------------------------- 1 y 2 ----
print("\n[1] Una lista de permisos se compara por contenido, no por posicion")

base = _rol(puede_consultar=["consultar_factura", "reiniciar_ont"])
igual_desordenado = _rol(puede_consultar=["reiniciar_ont", "consultar_factura"])
comprobar(_lo_que_pisaria(base, igual_desordenado) == [],
          "reordenar una lista NO se reporta")

# El caso exacto que produjo los 15 falsos positivos: un inserto al principio.
suma_al_principio = _rol(
    puede_consultar=["activar_catv", "consultar_factura", "reiniciar_ont"])
comprobar(_lo_que_pisaria(base, suma_al_principio) == [],
          "el archivo que SUMA al principio de la lista NO se reporta")

# ---------------------------------------------------------------------- 3 --
print("\n[3] Quitar de una lista SI se reporta, y nombra lo que se pierde")

quita = _rol(puede_consultar=["consultar_factura"])
salida = _lo_que_pisaria(base, quita)
comprobar(len(salida) == 1, "quitar una herramienta produce exactamente 1 aviso")
comprobar(bool(salida) and "reiniciar_ont" in salida[0],
          "el aviso NOMBRA la herramienta que se pierde")
comprobar(bool(salida) and "consultar_factura" not in salida[0],
          "el aviso NO nombra lo que se conserva (ese era el ruido)")

# ---------------------------------------------------------------------- 4 --
print("\n[4] Una seccion que el archivo vacia entera se reporta")

con_planes = {"roles": {}, "planes_venta": [{"nombre_wisphub": "PLAN HOGAR"}]}
sin_planes = {"roles": {}, "planes_venta": []}
salida = _lo_que_pisaria(con_planes, sin_planes)
comprobar(len(salida) == 1 and "planes_venta" in salida[0],
          "6 planes -> lista vacia se reporta (el caso que era invisible)")
comprobar(bool(salida) and "BORRARIA" in salida[0],
          "el aviso dice BORRARIA, no PISARIA: la diferencia importa al leerlo")

# ---------------------------------------------------------------------- 5 --
print("\n[5] Un campo SINCRONIZADO es propiedad de la base, no del archivo")

comprobar("localidades" in TenantConfig.SINCRONIZADOS,
          "'localidades' sigue declarado como sincronizado")

con_localidades = {"roles": {}, "localidades": [{"localidad": "DONA MANUELA"}]}
sin_localidades = {"roles": {}, "localidades": []}
comprobar(_lo_que_pisaria(con_localidades, sin_localidades) == [],
          "un campo sincronizado que el archivo no trae NO se reporta")

# Que no se reporte solo sirve si ademas no se pisa. 'cargar()' restaura el
# valor de la base sobre 'datos' antes de escribir; se comprueba la regla que
# usa, no la funcion entera (necesitaria una base).
datos_del_archivo = {"localidades": [], "roles": {}}
en_base = {"localidades": [{"localidad": "DONA MANUELA"}], "roles": {}}
for campo in TenantConfig.SINCRONIZADOS:
    if campo in en_base:
        datos_del_archivo[campo] = en_base[campo]
comprobar(datos_del_archivo["localidades"] == en_base["localidades"],
          "y lo que se escribe conserva el valor de la base, no el del archivo")

# ---------------------------------------------------------------------- 6 --
print("\n[6] El bug original: una hoja suelta con otro valor")

activo = {"roles": {}, "canales": {"whatsapp": {"activo": True}}}
apagado = {"roles": {}, "canales": {"whatsapp": {"activo": False}}}
salida = _lo_que_pisaria(activo, apagado)
comprobar(len(salida) == 1 and "activo" in salida[0],
          "true -> false en un booleano se sigue reportando")

print("\n[+] Un rol entero que el archivo no trae")
salida = _lo_que_pisaria({"roles": {"ventas": {}}}, {"roles": {}})
comprobar(len(salida) == 1 and "ventas" in salida[0],
          "un rol que solo existe en la base se reporta")

print("\n" + "=" * 70)
if fallos:
    print(f" {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    raise SystemExit(1)
print(" Todo en orden: la guarda frena las perdidas y no grita por lo demas.")
print("=" * 70)
