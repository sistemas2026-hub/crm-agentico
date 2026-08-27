# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DE IDENTIDAD INYECTADA  --  sin filtro no sale la consulta
================================================================================

El bug, medido en produccion el 27/08/2026
------------------------------------------
Un numero de WhatsApp que no es cliente de nadie escribio "hola para cambiar el
wifi". Al PRIMER mensaje, con la sesion sin verificar, el motor llamo de verdad
a WispHub y trajo 300 filas de un universo de 7.356 clientes. La traza decia
'exito: True'. No hubo error, ni aviso, ni forma de notarlo mirando la bandeja.

La causa son dos piezas correctas por separado:

  1. El gate de identidad no exigia nada: el numero de WhatsApp cuenta como
     factor de posesion, asi que 'nivel_exigido' quedaba en 0.
  2. 'inyectar_sesion' OMITE un valor vacio en vez de mandarlo nulo. Esa regla
     es correcta y esta verificada -- WispHub responde 400 a {"interfaz": null}
     pero acepta que el campo no venga.

Juntas abren el agujero: omitir 'id_servicio' no consulta "el servicio de
nadie", consulta SIN FILTRO. Y una consulta sin filtro contra /api/clientes/
devuelve a todo el mundo con cara de respuesta exitosa -- exactamente la
trampa que la skill de WispHub advierte, solo que aca le paso al motor.

Lo que se fija aca
------------------
1. Un campo declarado en 'inyectados_obligatorios' que la sesion no tiene
   IMPIDE la llamada. Es lo unico que importa: sin esto vuelve la fuga.
2. Con la sesion completa, la llamada sale normal.
3. La excepcion se levanta desde _resolver_argumentos, que es por donde pasan
   los TRES caminos que arman argumentos (el modelo, una accion aprobada, y la
   ruta interna de servicio). Protegerlo en uno solo dejaria los otros dos
   abiertos.
4. Un campo NO declarado obligatorio sigue omitiendose en silencio: eso es lo
   correcto para 'interfaz_lan', y romperlo dejaria sin diagnostico a los
   clientes que lo tienen vacio -- que es normal, no un dato faltante.
5. La config no deja declarar obligatorio algo que no se inyecta.
6. Toda herramienta del tenant que inyecte identidad la declara obligatoria.
   Esta es la que avisa cuando alguien agrega una herramienta nueva y se
   olvida.

Sin base, sin red y sin modelo.

    py -3.13 tests/test_identidad_obligatoria.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.config.schema import Herramienta, TenantConfig, cargar_config   # noqa: E402
from nucleo.modelo import motor                                             # noqa: E402
from nucleo.modelo.motor import FaltaIdentidadEnSesion                      # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(("  [OK]   " if condicion else "  [FALLA] ") + que)
    if not condicion:
        fallos.append(que)


class SesionFalsa:
    def __init__(self, **campos):
        self.__dict__.update(campos)


def _herramienta(**extra) -> Herramienta:
    base = dict(nombre="consultar_algo", tipo="http", roles_permitidos=["x"],
                base_url="http://x", endpoint="/api/clientes/",
                inyectar_sesion={"id_servicio": "id_cliente"})
    base.update(extra)
    return Herramienta(**base)


print("=" * 70)
print(" GUARDA DE IDENTIDAD INYECTADA")
print("=" * 70)

# ---------------------------------------------------------------------- 1 --
print("\n[1] Sin el campo de identidad, la llamada NO se arma  <- el bug")
h = _herramienta(inyectados_obligatorios=["id_servicio"])
try:
    motor._resolver_argumentos(h, SesionFalsa(id_cliente=None), {})
    comprobar(False, "deberia haber impedido la llamada")
except FaltaIdentidadEnSesion as e:
    comprobar("id_servicio" in e.faltantes, "se levanta FaltaIdentidadEnSesion")
    comprobar(e.herramienta == "consultar_algo", "el error dice que herramienta fue")

# El caso exacto de produccion: sesion sin verificar, atributo ausente.
try:
    motor._resolver_argumentos(h, SesionFalsa(identificador_canal="573015581421"), {})
    comprobar(False, "una sesion sin id_cliente deberia frenar")
except FaltaIdentidadEnSesion:
    comprobar(True, "una sesion sin verificar (el caso real) tambien frena")

# Y el modelo no puede sortearlo proponiendo el valor el mismo: la inyeccion
# pisa siempre lo que venga del modelo.
try:
    motor._resolver_argumentos(h, SesionFalsa(id_cliente=""),
                               {"id_servicio": "9999"})
    comprobar(False, "el modelo no deberia poder completar la identidad")
except FaltaIdentidadEnSesion:
    comprobar(True, "el modelo NO puede completar la identidad por su cuenta")

# ---------------------------------------------------------------------- 2 --
print("\n[2] Con la sesion completa, la llamada sale normal")
args = motor._resolver_argumentos(h, SesionFalsa(id_cliente="12345"), {})
comprobar(args.get("id_servicio") == "12345", "el id de la sesion viaja igual que antes")

# ---------------------------------------------------------------------- 4 --
print("\n[4] Un campo NO declarado obligatorio se sigue omitiendo")
opcional = _herramienta(inyectar_sesion={"interfaz": "interfaz_lan"})
args = motor._resolver_argumentos(opcional, SesionFalsa(interfaz_lan=""), {})
comprobar("interfaz" not in args,
          "'interfaz_lan' vacio se omite (WispHub rechaza el nulo, no el ausente)")

# ---------------------------------------------------------------------- 5 --
print("\n[5] La config no deja declarar obligatorio algo que no se inyecta")
try:
    _herramienta(inyectados_obligatorios=["campo_inventado"])
    comprobar(False, "deberia rechazar un obligatorio que no se inyecta")
except ValueError as e:
    comprobar("campo_inventado" in str(e), "se rechaza y NOMBRA el campo")

# ---------------------------------------------------------------------- 6 --
print("\n[6] La config real: ninguna herramienta de identidad quedo sin declarar")
cfg = cargar_config("tenants/rapilink.config.yaml")
# Atributos de sesion que identifican a UN cliente. Si se agrega otro, va aca:
# esta lista es lo que hace que la guarda avise sola.
IDENTIFICAN = {"id_cliente", "sn_onu", "identificador_canal"}
sin_declarar = [
    h.nombre for h in cfg.herramientas
    if any(atr in IDENTIFICAN for atr in (h.inyectar_sesion or {}).values())
    and not h.inyectados_obligatorios
]
comprobar(not sin_declarar,
          f"toda herramienta que inyecta identidad la exige "
          f"(sin declarar: {sin_declarar})")

print("\n" + "=" * 70)
if fallos:
    print(f" {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    raise SystemExit(1)
print(" Todo en orden: sin identidad no sale la consulta.")
print("=" * 70)
