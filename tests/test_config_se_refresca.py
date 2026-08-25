# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DE REFRESCO DE CONFIG  --  el motor no sirve una version vieja en
                                   silencio
================================================================================

Por que existe
--------------
El motor cachea la configuracion del tenant por proceso. Ese cache se vaciaba
SOLO cuando guardaba la interfaz, porque 'olvidar_config' se llama desde los
endpoints del propio proceso.

Pero la interfaz no es la unica que escribe en 'asistente.tenant_config':
'cli/cargar_config.py' y el editor invocado desde un script escriben la misma
fila desde OTRO proceso, y muchas veces desde otra maquina. Ese otro proceso no
tiene forma de avisarle al motor. Resultado: el motor seguia contestando con la
configuracion vieja -- sin error, sin aviso, y sin manera de notarlo salvo
reiniciando.

Paso de verdad el 25/08/2026, dos veces el mismo dia: se cargo un cambio por
script, se probo contra el motor, no aparecia, y se probo otra vez contra un
proceso que no podia haberlo tomado. El sintoma no apunta a la causa: parece
que el cambio no se guardo, cuando en la base estaba perfectamente escrito.

Lo que se fija aca
------------------
1. Arranque en frio: se lee la config Y se anota que version se esta sirviendo.
2. Dentro del intervalo NO se le pregunta nada a la base (si cada turno pagara
   una consulta, esto seria latencia en el camino caliente y alguien lo sacaria).
3. Pasado el intervalo, si la version no cambio, se comprueba pero NO se recarga
   ni se revalida la config entera.
4. Pasado el intervalo, si la version cambio, se recarga. Este es el bug.
5. Si la base no responde a la comprobacion, se sigue sirviendo lo que hay: un
   turno que funciona con una config de hace un minuto es mejor que un turno
   fallido.
6. 'olvidar_config' sigue forzando la relectura inmediata (interfaz).

Se corre sin base y sin red: se sustituyen 'fuente.cargar' y
'fuente.version_en_base' por espias.

    py -3.13 tests/test_config_se_refresca.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.canales import api                      # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    if condicion:
        print(f"  [OK]   {que}")
    else:
        print(f"  [FALLA] {que}")
        fallos.append(que)


class Base:
    """Una base de mentira que cuenta cuantas veces la consultaron."""

    def __init__(self, version=1):
        self.version = version
        self.cargas = 0          # veces que se bajo y valido la config entera
        self.consultas = 0       # veces que se pregunto solo la version
        self.caida = False

    def cargar(self, tenant, raiz="."):
        if self.caida:
            raise RuntimeError("base caida")
        self.cargas += 1
        return f"config-v{self.version}"

    def version_en_base(self, tenant):
        if self.caida:
            raise RuntimeError("base caida")
        self.consultas += 1
        return self.version


def preparar(version=1):
    base = Base(version)
    api._configs.clear()
    api._servidas.clear()
    api.fuente.cargar = base.cargar
    api.fuente.version_en_base = base.version_en_base
    return base


def envejecer(tenant="t"):
    """Simula que la ultima comprobacion fue hace mucho."""
    version, _ = api._servidas[tenant]
    api._servidas[tenant] = (version, 0.0)


print("=" * 70)
print(" GUARDA DE REFRESCO DE CONFIG")
print("=" * 70)

# ---------------------------------------------------------------------- 1 --
print("\n[1] Arranque en frio")
base = preparar(version=66)
comprobar(api._config_de("t") == "config-v66", "la primera llamada trae la config")
comprobar(base.cargas == 1, "se bajo la config una sola vez")
comprobar(api._servidas["t"][0] == 66, "queda anotada la version que se sirve")

# ---------------------------------------------------------------------- 2 --
print("\n[2] Dentro del intervalo no se consulta la base")
antes = base.consultas
api._config_de("t")
api._config_de("t")
api._config_de("t")
comprobar(base.consultas == antes,
          "tres turnos seguidos no agregan ninguna consulta")
comprobar(base.cargas == 1, "y no se vuelve a bajar la config")

# ---------------------------------------------------------------------- 3 --
print("\n[3] Pasado el intervalo, misma version: se comprueba y nada mas")
envejecer()
antes_consultas, antes_cargas = base.consultas, base.cargas
comprobar(api._config_de("t") == "config-v66", "se sigue sirviendo lo mismo")
comprobar(base.consultas == antes_consultas + 1, "se pregunto la version (1 consulta)")
comprobar(base.cargas == antes_cargas,
          "pero NO se volvio a bajar ni revalidar la config entera")

# ---------------------------------------------------------------------- 4 --
print("\n[4] Pasado el intervalo, otra version: se recarga (el bug)")
base.version = 67
envejecer()
comprobar(api._config_de("t") == "config-v67",
          "un cambio escrito por OTRO proceso se toma solo")
comprobar(base.cargas == 2, "y se bajo la config de nuevo, una vez")

# ---------------------------------------------------------------------- 5 --
print("\n[5] Si la base no responde, se sigue sirviendo lo que hay")
envejecer()
base.caida = True
try:
    servido = api._config_de("t")
    comprobar(servido == "config-v67",
              "la comprobacion fallida no rompe el turno ni vacia el cache")
except Exception as e:
    comprobar(False, f"no debia propagar la excepcion (propago {type(e).__name__})")
base.caida = False

# ---------------------------------------------------------------------- 6 --
print("\n[6] La interfaz sigue viendose al instante")
base.version = 68
api.olvidar_config("t")
comprobar("t" not in api._servidas, "olvidar_config tambien borra la version anotada")
comprobar(api._config_de("t") == "config-v68",
          "el turno siguiente a un guardado de la interfaz relee ya mismo")

print("\n" + "=" * 70)
if fallos:
    print(f" {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    raise SystemExit(1)
print(" Todo en orden: una carga por script ya no queda invisible para el motor.")
print("=" * 70)
