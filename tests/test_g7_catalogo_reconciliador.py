# -*- coding: utf-8 -*-
"""
================================================================================
 G7 pre-deploy -- el catalogo tiene con que reconciliar  (B4, D28)
================================================================================

    py -3.13 tests/test_g7_catalogo_reconciliador.py

Corre SIN RED, SIN BASE y SIN EJECUTAR NINGUN EFECTO. Lee el YAML del tenant y
comprueba que el reconciliador encontraria lo que necesita.

POR QUE ESTE ARCHIVO EXISTE
---------------------------
G7 pedia "declarar busca_caso en el catalogo del tenant". Eso era IMPOSIBLE
hasta el 20/09/2026: 'Herramienta' usa extra="forbid", asi que un YAML con esa
bandera hacia fallar la carga entera -- y el codigo de B4 la leia con
getattr(..., False), que devuelve False en silencio. La capacidad se
consultaba, no se podia declarar, y nadie se enteraba.

Un gate que depende de que alguien recuerde declarar cuatro banderas en un YAML
de 6000 lineas necesita una prueba, no una nota.

LO QUE NO HACE, Y ES EL PUNTO
-----------------------------
No llama a nadie. No hay red, no hay token, no se resuelve un secreto. Se
comprueba lo que el catalogo DECLARA, que es justo lo que el gate pide antes de
encender nada.
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}", flush=True)
    if not condicion:
        fallos.append(que)
        if porque:
            print(f"          {porque}", flush=True)


def titulo(t):
    print(f"\n{'=' * 76}\n  {t}\n{'=' * 76}", flush=True)


import yaml                                                       # noqa: E402

from nucleo.config.schema import TenantConfig                     # noqa: E402

TENANT = "rapilink"

# Se valida el YAML del REPO, no lo que haya en una base: este gate comprueba
# lo que se va a desplegar. La fuente de verdad en produccion es
# asistente.tenant_config, y comparar las dos es trabajo de
# cli/diferencias_config.py despues de aplicar.
RUTA_YAML = RAIZ / "tenants" / f"{TENANT}.config.yaml"

# =============================================================================
titulo("1. la config carga entera, con las banderas nuevas")
# =============================================================================
try:
    crudo = yaml.safe_load(RUTA_YAML.read_text(encoding="utf-8"))
    config = TenantConfig.model_validate(crudo)
    revisar(True, "el YAML del tenant valida contra el schema, entero")
except Exception as e:
    revisar(False, "el YAML del tenant valida contra el schema", str(e)[:300])
    print("\n[FALLA] sin config no se puede comprobar nada mas.")
    raise SystemExit(1)

por_bandera = {}
for bandera in ("busca_caso", "asigna_caso", "lee_asignados", "lee_perfiles"):
    encontradas = [h for h in config.herramientas if getattr(h, bandera, False)]
    por_bandera[bandera] = encontradas
    revisar(len(encontradas) == 1,
            f"'{bandera}' la declara exactamente una herramienta "
            f"({[h.nombre for h in encontradas]})",
            "Dos herramientas con la misma bandera hacen que cual gana dependa "
            "del orden del YAML.")

# =============================================================================
titulo("2. asigna_caso usa el endpoint ADITIVO, y solo ese")
# =============================================================================
asignar = por_bandera["asigna_caso"][0] if por_bandera["asigna_caso"] else None
if asignar is None:
    revisar(False, "hay una herramienta para asignar el caso")
else:
    revisar(asignar.endpoint.rstrip("/").endswith("/assignees"),
            f"apunta a /assignees/ ({asignar.endpoint})",
            "Es el unico endpoint que agrega sin reemplazar el conjunto.")
    revisar((asignar.metodo or "").upper() == "POST",
            f"por POST ({asignar.metodo})")

    # Lo prohibido, dicho por su nombre: los tres reemplazan el conjunto.
    ruta = (asignar.endpoint or "").lower()
    for prohibido in ("bulk/update", "bulk_update"):
        revisar(prohibido not in ruta,
                f"NO usa '{prohibido}'",
                "Reemplaza el conjunto: borraria a los colaboradores.")
    revisar((asignar.metodo or "").upper() != "PUT",
            "NO usa PUT",
            "El PUT del detalle ademas vacia contacts, teams y tags.")
    revisar(asignar.solo_lectura is False and asignar.requiere_confirmacion is True,
            "es una escritura y exige confirmacion, como toda escritura")

# =============================================================================
titulo("3. las dos lecturas son de solo lectura de verdad")
# =============================================================================
for bandera in ("lee_asignados", "lee_perfiles"):
    herr = por_bandera[bandera][0] if por_bandera[bandera] else None
    if herr is None:
        revisar(False, f"hay una herramienta con '{bandera}'")
        continue
    revisar(herr.solo_lectura is True,
            f"'{herr.nombre}' es solo_lectura")
    revisar((herr.metodo or "GET").upper() == "GET",
            f"y consulta por GET ({herr.metodo})")

# La de perfiles tiene que apuntar a donde estan los perfiles CON su user_id:
# es lo unico que permite cruzar identidad por id y no por nombre.
perfiles = por_bandera["lee_perfiles"][0] if por_bandera["lee_perfiles"] else None
if perfiles is not None:
    revisar("users" in (perfiles.endpoint or "").lower(),
            f"la de perfiles apunta al listado de usuarios ({perfiles.endpoint})")

# =============================================================================
titulo("4. el reconciliador encuentra sus ejecutores")
# =============================================================================
# Se arma el ejecutor REAL con esta config y se comprueba que reconoce los
# tipos. Nada se ejecuta: las funciones inyectadas no se llaman porque solo se
# consulta si existen.
from nucleo.relevo import efectos_externos                        # noqa: E402
from nucleo.seguimiento import escalamiento                       # noqa: E402

tiene_crear = any(h.nombre == escalamiento.NOMBRE_HERRAMIENTA_CASO_CREAR
                  for h in config.herramientas)
revisar(tiene_crear,
        f"existe la herramienta de crear caso "
        f"('{escalamiento.NOMBRE_HERRAMIENTA_CASO_CREAR}')",
        "Sin ella el worker ni siquiera procesa el tenant.")

puede_asignar = all(por_bandera[b] for b in
                    ("asigna_caso", "lee_asignados", "lee_perfiles"))
revisar(puede_asignar,
        "estan las TRES capacidades que D28 exige",
        "Falla cerrado: sin cualquiera, asignar_caso queda 'permanente'.")

llamadas = []


def _espia(*a, **k):
    llamadas.append(a)
    raise AssertionError("no se puede llamar a un sistema externo en esta prueba")


ejecutar = efectos_externos.ejecutor(
    config, TENANT, crear=_espia, buscar_por_nombre=_espia,
    agregar_asignado=_espia, leer_asignados=_espia, leer_perfiles=_espia)

# Un tipo sin datos NO llega a llamar a nadie: se rechaza antes, y eso es lo
# que permite comprobar el cableado sin tocar nada de afuera.
for tipo, codigo_esperado in (("crear_caso", "sin_nombre_de_caso"),
                              ("asignar_caso", "sin_caso_o_perfil")):
    r = ejecutar(tipo, {}, None)
    revisar(r.clase == "permanente" and r.codigo == codigo_esperado,
            f"'{tipo}' tiene ejecutor y valida antes de llamar "
            f"({r.clase}/{r.codigo})")

r = ejecutar("crear_ticket", {}, None)
revisar(r.clase == "permanente" and "sin_ejecutor" in (r.codigo or ""),
        f"'crear_ticket' sigue SIN ejecutor, por el gate Q2 ({r.codigo})",
        "Es lo correcto: WispHub no permite demostrar que el ticket no existe.")

revisar(llamadas == [],
        "NINGUN sistema externo se llamo durante esta prueba",
        f"Se llamo {len(llamadas)} vez/veces.")

# =============================================================================
titulo("5. el worker sigue apagado")
# =============================================================================
import os                                                         # noqa: E402

from nucleo.relevo import reconciliador                           # noqa: E402
from nucleo.relevo import worker_reconciliador as worker          # noqa: E402

anterior = os.environ.pop("RECONCILIADOR_HABILITADO", None)
try:
    revisar(worker.encendido() is False,
            "sin la variable de entorno, el worker esta APAGADO")
    # '1 ' NO esta en esta lista a proposito: encendido() hace strip(), y un
    # espacio de mas al copiar una variable de entorno es un descuido, no la
    # intencion de dejarlo apagado. Se comprueba abajo, explicitamente.
    for valor in ("0", "", "true", "si", "yes", "01", "2", "-1"):
        os.environ["RECONCILIADOR_HABILITADO"] = valor
        revisar(worker.encendido() is False,
                f"'{valor}' NO enciende el worker",
                "Solo el '1' exacto: cualquier otra cosa es un descuido.")
    os.environ["RECONCILIADOR_HABILITADO"] = "1"
    revisar(worker.encendido() is True, "'1' si lo enciende")
    os.environ["RECONCILIADOR_HABILITADO"] = " 1 "
    revisar(worker.encendido() is True, "y tolera espacios alrededor del 1")
finally:
    os.environ.pop("RECONCILIADOR_HABILITADO", None)
    if anterior is not None:
        os.environ["RECONCILIADOR_HABILITADO"] = anterior

revisar(worker.INTERVALO_SEGUNDOS == 300,
        f"la cadencia es de 300 s ({worker.INTERVALO_SEGUNDOS})",
        "§3.6 pide de 1 a 5 min; el reloj general (~60 min) no alcanza.")
revisar(reconciliador.CADENCIA_SEGUNDOS == worker.INTERVALO_SEGUNDOS,
        "y sale de un solo lugar, no de dos numeros que pueden separarse")

# El interruptor es PROPIO: encender el reloj general no puede encender esto.
codigo_worker = (RAIZ / "nucleo" / "relevo" / "worker_reconciliador.py").read_text(
    encoding="utf-8")
revisar("RELOJ_HABILITADO" not in codigo_worker,
        "el worker no mira la variable del reloj general",
        "Encender uno no puede encender el otro por descuido: este toca "
        "sistemas externos.")

# Apagado, un '--once' no procesa nada.
os.environ.pop("RECONCILIADOR_HABILITADO", None)
llamadas_vuelta = []
original = worker.una_vuelta
worker.una_vuelta = lambda **k: llamadas_vuelta.append(k) or {}
try:
    codigo_salida = worker.main(["--once"])
    revisar(codigo_salida == 0 and llamadas_vuelta == [],
            "apagado, '--once' termina sin procesar nada",
            f"salida={codigo_salida}, vueltas={len(llamadas_vuelta)}")
finally:
    worker.una_vuelta = original
    if anterior is not None:
        os.environ["RECONCILIADOR_HABILITADO"] = anterior

print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] El catalogo tiene con que reconciliar, y el worker sigue apagado.")
