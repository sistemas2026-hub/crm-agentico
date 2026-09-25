# -*- coding: utf-8 -*-
"""
================================================================================
 UNA COPIA MAS VIEJA QUE PRODUCCION NO ESCRIBE LA CONFIG
================================================================================

Por que existe
--------------
Encontrado el 24/09/2026. Una rama de diseno estaba 283 commits atras de la que
despliega, y su 'tenants/rapilink.config.yaml' no tenia NI UNO de los campos de
la frontera de autorizacion: 'irreversible', 'nivel_autonomia',
'exige_declaracion', 'aprobacion'. Cargarlo habria dejado al motor desplegado
ejecutando acciones irreversibles sin la puerta que hoy las frena -- y el dato
viejo ya no estaria para volver.

Las dos guardas que ya existian la dejaban pasar, cada una por su motivo:

  - '_lo_que_pisaria' compara hoja por hoja y se SALTA lo que el archivo no
    trae ("la completa el esquema con su default"). Cuando el esquema ni
    siquiera CONOCE el campo no hay ruta que comparar, y la perdida es muda.
  - 'problemas_de_alineacion_git' medía, en esa copia, contra el remoto de la
    rama actual. La rama tenia upstream y estaba 0 commits atras de EL, asi que
    lo unico que bloqueaba eran 5 commits sin empujar: un push rutinario la
    desarmaba entera.

Lo que se fija aca
------------------
La pregunta correcta no es "que trabajo de otro se pierde" sino "puedo YO
escribir esta tabla", y se contesta antes. Se lee lo que HAY en la base con el
esquema de esta copia: si no valida por campos que el esquema no conoce, la
conclusion es exacta -- produccion tiene capacidades que este codigo no sabe
representar.

No depende de git, ni de ramas, ni de que alguien recuerde una variable de
entorno.

Sin red, sin base y sin modelo:

    py -3.13 tests/test_no_cargar_config_desde_copia_vieja.py
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RAIZ)

for var, valor in (("DBHOST", "localhost"), ("DBPORT", "5432"), ("DBNAME", "postgres"),
                   ("DBUSER", "postgres"), ("DBPASSWORD", "x")):
    os.environ.setdefault(var, valor)

from pathlib import Path                                   # noqa: E402

from cli.cargar_config import copia_mas_vieja_que_la_base  # noqa: E402
from nucleo.config import cargar_config                    # noqa: E402

FALLOS = []


def afirmar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        FALLOS.append(que)


VIGENTE = cargar_config(Path(RAIZ) / "tenants" / "rapilink.config.yaml").model_dump(mode="json")

print("\n--- 1. la config de hoy se puede cargar ---")
# El contrapeso obligatorio: una guarda que bloquea siempre no protege, estorba.
afirmar(copia_mas_vieja_que_la_base(VIGENTE, "rapilink", 154) is None,
        "una base que este esquema SI entiende no se bloquea")

afirmar(copia_mas_vieja_que_la_base(None, "rapilink", 0) is None,
        "un tenant que todavia no tiene config en la base tampoco (alta nueva)")

afirmar(copia_mas_vieja_que_la_base({}, "rapilink", 0) is None,
        "ni una config vacia")

print("\n--- 2. el caso real: la base sabe algo que este codigo no ---")
# Exactamente la forma del incidente: la base trae un campo de herramienta que
# el esquema de esta copia no conoce.
del_futuro = {k: v for k, v in VIGENTE.items()}
del_futuro["herramientas"] = [dict(h) for h in VIGENTE["herramientas"]]
del_futuro["herramientas"][0]["guarda_que_este_codigo_no_conoce"] = True

aviso = copia_mas_vieja_que_la_base(del_futuro, "rapilink", 154)
afirmar(aviso is not None,
        "un campo de herramienta desconocido BLOQUEA la carga")
afirmar(aviso and "mas adelante que este codigo" in aviso,
        "y el aviso dice cual es la relacion, no 'error de validacion'")
afirmar(aviso and "guarda_que_este_codigo_no_conoce" in aviso,
        "y nombra el campo, para que no haya que adivinar que falta bajar")

print("\n--- 3. tambien si lo desconocido esta en la raiz ---")
raiz = dict(VIGENTE)
raiz["seccion_del_futuro"] = {"algo": 1}
afirmar(copia_mas_vieja_que_la_base(raiz, "rapilink", 154) is not None,
        "una seccion entera que el esquema no conoce tambien bloquea")

print("\n--- 4. lo que NO tiene que bloquear ---")
# Una base a la que le FALTA algo que el archivo trae no es este problema: eso
# es una incorporacion normal, y frenarla seria impedir todo cambio.
#
# Se quita una lista sincronizada y no una herramienta: sacar una herramienta
# rompe las referencias que la nombran, y eso SI es un error de configuracion
# legitimo -- no el caso que esta guarda mira.
sin_localidades = dict(VIGENTE)
sin_localidades["localidades"] = []
afirmar(copia_mas_vieja_que_la_base(sin_localidades, "rapilink", 154) is None,
        "que la base tenga MENOS que el archivo no bloquea: eso es agregar")

# Y el contrapeso del contrapeso: una base INVALIDA por un motivo que no es
# "campo desconocido" tambien bloquea, y esta bien que lo haga. Escribir encima
# de una config que ni se puede leer es peor, no mejor.
rota = dict(VIGENTE)
rota["identidad"] = {"slug": "rapilink"}
afirmar(copia_mas_vieja_que_la_base(rota, "rapilink", 154) is not None,
        "una base que no valida por cualquier motivo tampoco se pisa a ciegas")

print()
if FALLOS:
    print(f"[FALLA] {len(FALLOS)} comprobacion(es)")
    sys.exit(1)
print("[OK] Una copia que no entiende la base no la puede escribir.")
