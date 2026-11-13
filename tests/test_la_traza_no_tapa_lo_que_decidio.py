# -*- coding: utf-8 -*-
"""
================================================================================
 LA TRAZA TAPA LA CÉDULA, NO LA DECISIÓN
================================================================================

Por qué existe
--------------
`_enmascarar` recorta todo valor de más de cuatro caracteres antes de
guardarlo en `asistente.tool_calls.parametros`. Eso protege la cédula y el
id_servicio, que es para lo que está.

Pero también tapaba **lo que el modelo decidió**. Encontrado el 20/10/2026
midiendo la confianza del router: `media` llegaba a la auditoría como
`...edia` y `alta` pasaba entera por tener cuatro letras. O sea que la máscara
**ni siquiera era consistente: dependía del largo de la palabra.**

Un valor de enum es un conjunto cerrado que la empresa escribió en su
catálogo —áreas, niveles de confianza, tipos de servicio—. No sale de la
conversación, así que no puede traer una cédula. Taparlo no protege nada y
cuesta la única cosa que la traza existe para contar.

LAS DOS MITADES
---------------
Esta prueba afirma las dos, y la segunda es la que no se puede aflojar nunca:

    lo que sale de un enum        se guarda entero
    todo lo demás                 se sigue enmascarando

    py -3.13 tests/test_la_traza_no_tapa_lo_que_decidio.py
================================================================================
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.config.schema import cargar_config                   # noqa: E402
from nucleo.modelo import motor                                  # noqa: E402

FALLOS = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  [{'ok' if condicion else 'FALLA'}]   {que}")
    if not condicion:
        FALLOS.append(que)


cfg = cargar_config("tenants/rapilink.config.yaml")
deriva = next(h for h in cfg.herramientas if h.deriva_rol)
area = deriva.areas_destino[0]

print("\n  LO QUE SALE DE UN ENUM SE GUARDA ENTERO")
salida = motor._enmascarar({"area": area, "confianza": "media"}, deriva)
comprobar(salida["area"] == area,
          f"el área se lee completa: {salida['area']!r}")
comprobar(salida["confianza"] == "media",
          f"y la confianza también: {salida['confianza']!r}")

print("\n  TODO LO DEMÁS SE SIGUE ENMASCARANDO  <- esto no se afloja nunca")
#  LA MITAD QUE NO SE PUEDE ROMPER. Una exención mal puesta acá convierte la
#  auditoría en una copia de los datos del cliente -- §5: las respuestas
#  crudas de WispHub traen contraseñas, GPS y cédula.
#
#  SE USA UNA HERRAMIENTA QUE DE VERDAD RECIBE EL DATO, y no la de derivación.
#  La primera versión de esta prueba usaba `deriva`, cuyo esquema solo tiene
#  `area` y `confianza`: eximir TODA clave --la mutación peligrosa-- no cambiaba
#  nada ahí, y la guarda quedaba en verde con el agujero abierto. Medido el
#  20/10/2026 aplicando esa mutación: exit 0. Una guarda que no mata la
#  mutación que le toca no es una guarda.
consulta = next(h for h in cfg.herramientas if h.nombre == "consultar_cliente")
#  EL VALOR TIENE QUE SER LARGO, y la clave tiene que estar EN EL ESQUEMA.
#  `id_servicio` está en el de `consultar_cliente` y no declara enum, así que
#  es exactamente lo que la exención NO debe alcanzar. Con cuatro caracteres
#  («6580») pasaría entero de todas formas y la mutación quedaría viva --
#  medido el 20/10/2026, dos intentos fallidos antes de este.
sensible = motor._enmascarar(
    {"cedula": "1012345678", "id_servicio": "6580123"}, consulta)
comprobar(sensible["id_servicio"] == "...0123",
          f"el id_servicio del esquema se tapa: {sensible['id_servicio']!r}"
          "   <- la mutación que esta prueba mata")
comprobar(sensible["cedula"] == "...5678",
          f"la cédula sigue tapada: {sensible['cedula']!r}")
#  OJO: `6580` tiene CUATRO caracteres, asi que `len(texto) > 4` es falso y
#  pasa ENTERO -- antes de este cambio tambien. Se afirma lo que de verdad
#  pasa, no lo que uno esperaria: una prueba que afirma lo segundo se pone
#  verde el dia que alguien arregle el hueco y roja hoy, sin medir nada.
corto4 = motor._enmascarar({"id_servicio": "6580"}, consulta)
comprobar(corto4["id_servicio"] == "6580",
          f"un id de cuatro digitos pasa entero (hueco preexistente): "
          f"{corto4['id_servicio']!r}")

print("\n  EL HUECO QUE ESO DESTAPA, afirmado para que no se pierda")
#  La mascara es DEPENDIENTE DEL LARGO: protege 'cedula' (10 digitos) y no
#  protege 'id_servicio' (4). No es que falte proteccion, es que es
#  inconsistente -- y una proteccion inconsistente es peor que una ausente,
#  porque se confia en ella.
#
#  NO SE ARREGLA ACA. Cambiar el umbral toca lo que ya hay guardado y es una
#  decision de producto: los ultimos 4 caracteres existen justamente para que
#  un supervisor reconozca "es el mismo cliente de siempre". Un id corto
#  entero da exactamente eso y nada mas. Queda medido.
corto = motor._enmascarar({"loquesea": "6580"}, None)
comprobar(corto["loquesea"] == "6580",
          "cualquier valor de 4 caracteres o menos se guarda entero")

print("\n  SIN LA HERRAMIENTA, SE ENMASCARA TODO  (ningún llamador queda peor)")
viejo = motor._enmascarar({"area": area, "confianza": "media"})
comprobar(viejo["confianza"] == "...edia",
          f"sin herramienta vuelve el comportamiento de antes: {viejo['confianza']!r}")

print("\n  Y UNA HERRAMIENTA SIN ENUMS NO EXIME NADA")
sin_enum = next((h for h in cfg.herramientas
                 if not h.deriva_rol and h.solo_lectura), None)
if sin_enum is not None:
    r = motor._enmascarar({"loquesea": "unvalorlargo"}, sin_enum)
    comprobar(r["loquesea"].startswith("..."),
              "una clave que no está en ningún enum se tapa igual")

print("\n  FAIL-CLOSED: si el esquema no se puede leer, se tapa todo")


class _Rota:
    """Una herramienta cuyo esquema levanta al construirse."""
    def __getattr__(self, _):
        raise RuntimeError("esquema roto")


roto = motor._enmascarar({"confianza": "media"}, _Rota())
comprobar(roto["confianza"] == "...edia",
          "un error leyendo el esquema no exime a nadie")

print("\n" + "=" * 70)
if FALLOS:
    print(f" {len(FALLOS)} afirmacion(es) en rojo:")
    for f in FALLOS:
        print(f"   - {f}")
    sys.exit(1)
print(" La traza tapa la cédula y conserva la decisión.")
print("=" * 70)
