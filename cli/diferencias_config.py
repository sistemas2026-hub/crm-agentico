# -*- coding: utf-8 -*-
"""
================================================================================
 QUE DICE EL REPO Y QUE DICE LA BASE  -  las dos configs, lado a lado
================================================================================

Por que existe
--------------
Entre el 08 y el 09/09/2026 se arreglaron 19 cosas. Al clasificarlas una por
una, CUATRO no eran bugs de logica: eran la misma falla repetida -- el repo
declaraba algo que produccion no tenia.

  - 'auth_ref: BOTTLECRM_API_TOKEN' en buscar_solicitud    -> 403 en vivo
  - 'invocable_por_servicio' en cerrar_ticket_operativo    -> 403 en vivo
  - herramientas de la oferta escritas y nunca aplicadas   -> el agente
    improvisaba lo que la empresa vende

Ninguna prueba las podia ver, y no por falta de cobertura: las 47 pruebas
unitarias leen el YAML del disco, y produccion lee 'asistente.tenant_config'.
Se verificaba el sistema como esta ESCRITO, nunca el sistema como esta
DESPLEGADO. Las cuatro las encontro el usuario abriendo el simulador, una
simulacion perdida cada una.

Esto compara las dos y tarda segundos.

QUIEN MANDA EN CADA SECCION  -- por que el informe no dice "esto esta mal"
--------------------------------------------------------------------------
No hay una respuesta unica, y fingir que la hay daria un informe que nadie
lee. El YAML es la SEMILLA (cli/cargar_config.py) y la base es la fuente de
verdad una vez cargada: el cliente crea agentes, sube la parrilla y ajusta la
tarifa desde la interfaz, y nada de eso vuelve al archivo salvo que alguien
corra '--exportar'. Una diferencia ahi es el funcionamiento normal.

Por eso lo que se reporta es la DIRECCION de la diferencia, que si tiene una
lectura clara:

  [!] el repo lo declara y la base no dice lo mismo
      Es la direccion peligrosa, y la de las cuatro fallas de arriba: alguien
      escribio el cambio, lo commiteo, y produccion nunca se entero. Tambien
      cae aca lo que se edito desde la interfaz encima de un valor que el
      YAML trae -- que no es un bug, pero conviene ver, porque la proxima
      carga del archivo lo pisa (paso el 05/09/2026 con la tarifa).

  [i] solo la base lo tiene
      El caso normal de una seccion que se llena desde la pantalla: la
      parrilla de canales, las localidades, los planes. El YAML las trae
      vacias A PROPOSITO.

POR QUE SE RECORREN LAS DOS A LA VEZ, Y NO UNA Y DESPUES LA OTRA
----------------------------------------------------------------
La primera version aplanaba cada config por separado a rutas con puntos y
comparaba las dos tablas. Se rompio en el primer uso: 'localidades' esta
VACIA en el YAML y tiene 980 entradas en la base, asi que de un lado la ruta
quedaba como 'localidades' (una hoja) y del otro como 'localidades[Baranoa]'
(980 hojas). Las rutas no se cruzaban con nada y el informe declaraba una
diferencia inventada -- "repo: [] / base: <no existe>"-- sobre una seccion
que esta exactamente como debe estar.

Recorrer los dos arboles a la vez elimina esa clase entera de falso positivo:
en cada nodo se sabe que forma tiene CADA lado, y una lista se empareja por
el 'nombre' de sus elementos --no por su posicion, que cambia al reordenar el
YAML y no significa nada.

Las dos configuraciones se validan con TenantConfig antes de comparar, asi
que los valores por defecto quedan expandidos en las dos y no aparecen como
diferencias. Ese fue el otro ruido, el que hizo inservible la primera version
de cli/activar_oferta.py.

Salida
------
Termina en 1 si hay algo en la direccion peligrosa -- para poder encadenarlo
despues de aplicar config, o en un despliegue, sin leer la salida a ojo.

Uso
---
    py -3.13 cli/diferencias_config.py rapilink
    py -3.13 cli/diferencias_config.py rapilink --todo     # sin resumir
    py -3.13 cli/diferencias_config.py rapilink --json dif.json
================================================================================
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
# override=False por el mismo motivo que en cli/evaluar.py: un .env viejo
# horneado en una imagen no puede mandar mas que el entorno del despliegue.
# Aca importa el doble -- con la precedencia al reves, esta herramienta
# compararia el repo contra la base EQUIVOCADA y diria "todo en orden".
load_dotenv(RAIZ / ".env", override=False)

from nucleo.config import cargar_config                      # noqa: E402
from nucleo.config import fuente                             # noqa: E402
from nucleo.config.schema import TenantConfig                # noqa: E402


# 'version' es el numero de config_version, que sube en cada carga: siempre
# difiere y nunca significa nada. Compararlo seria una linea de ruido fija.
IGNORADAS = {"version"}

# Un campo SINCRONIZADO es propiedad de la base en las dos direcciones: el
# exportador no lo baja al archivo y el archivo no puede pisarlo (ver
# TenantConfig.SINCRONIZADOS). Que difiera no es una noticia -- es la
# definicion del campo.
#
# Se resume en una linea en vez de saltearse del todo, porque el numero SI
# dice algo: "parrilla_canales: 100 en la base" es como se ve de un vistazo
# que la parrilla sigue cargada. Listarlas una por una eran 228 filas que
# enterraban las tres que habia que mirar.
PROPIAS_DE_LA_BASE = set(TenantConfig.SINCRONIZADOS)

# Mas alla de esto, una seccion se resume en vez de listarse entera. Son las
# que se cargan desde la pantalla (980 localidades, 100 canales): imprimirlas
# item por item entierra las tres lineas que importan.
TOPE_DETALLE = 8

# Distingue "este campo no existe de ese lado" de "existe y vale None". No es
# lo mismo y el informe lo dice distinto.
AUSENTE = object()


def _vacio(valor: Any) -> bool:
    return valor is None or valor == "" or valor == [] or valor == {}


def _unir(ruta: str, clave: str) -> str:
    return f"{ruta}.{clave}" if ruta else clave


def _es_lista_de_objetos(valor: Any) -> bool:
    return isinstance(valor, list) and any(isinstance(v, dict) for v in valor)


def _clave_de(item: Any, i: int) -> str:
    """
    Como se identifica un elemento de una lista al emparejar los dos lados.

    Por 'nombre' cuando lo tiene -- herramientas, canales, planes-- y por
    posicion solo como ultimo recurso. Con posicion sola, mover una
    herramienta dentro del YAML aparece como doscientas diferencias que hay
    que leer enteras para descubrir que no cambio nada.
    """
    if isinstance(item, dict):
        for campo in ("nombre", "slug", "id", "clave"):
            if campo in item and isinstance(item[campo], str):
                return item[campo]
    return f"#{i}"


def _recorrer(repo: Any, base: Any, ruta: str, dif: dict) -> None:
    """Los dos arboles a la vez, anotando cada diferencia con su direccion."""
    if repo is AUSENTE:
        dif["solo_en_base"].append(
            {"ruta": ruta, "repo": "<no existe>", "base": base})
        return
    if base is AUSENTE:
        # Un campo que el repo declara y la base ni siquiera tiene: es la
        # forma mas pura de la falla que motivo esta herramienta.
        dif["repo_no_aplicado"].append(
            {"ruta": ruta, "repo": repo, "base": "<no existe>"})
        return

    if isinstance(repo, dict) and isinstance(base, dict):
        for k, v in repo.items():
            _recorrer(v, base.get(k, AUSENTE), _unir(ruta, k), dif)
        for k, v in base.items():
            if k not in repo:
                _recorrer(AUSENTE, v, _unir(ruta, k), dif)
        return

    if isinstance(repo, list) and isinstance(base, list):
        if _es_lista_de_objetos(repo) or _es_lista_de_objetos(base):
            ir = {_clave_de(v, i): v for i, v in enumerate(repo)}
            ib = {_clave_de(v, i): v for i, v in enumerate(base)}
            for k, v in ir.items():
                _recorrer(v, ib.get(k, AUSENTE), f"{ruta}[{k}]", dif)
            for k, v in ib.items():
                if k not in ir:
                    _recorrer(AUSENTE, v, f"{ruta}[{k}]", dif)
            return

        # Lista de valores simples (roles permitidos, campos, localidades).
        # Se compara como una sola hoja, pero se reporta QUE elemento cambio:
        # "15 vs 15 elementos" no le sirve a nadie.
        if repo != base:
            faltan = [x for x in repo if x not in base]
            sobran = [x for x in base if x not in repo]
            fila = {"ruta": ruta, "repo": repo, "base": base,
                    "faltan": faltan, "sobran": sobran}
            dif["repo_no_aplicado" if faltan else "solo_en_base"].append(fila)
        return

    if repo != base:
        # Un valor vacio en el repo frente a uno lleno en la base NO es que
        # falte aplicar algo: es una seccion que se llena desde la pantalla.
        destino = "solo_en_base" if _vacio(repo) else "repo_no_aplicado"
        dif[destino].append({"ruta": ruta, "repo": repo, "base": base})


def _resumen_sincronizado(clave: str, valor) -> dict:
    cuantos = len(valor) if isinstance(valor, (list, dict)) else None
    return {"ruta": clave, "repo": "<no baja al archivo>",
            "base": f"{cuantos} en la base" if cuantos is not None else valor,
            "sincronizado": True}


def comparar(repo: dict, base: dict) -> dict[str, list[dict]]:
    dif: dict[str, list[dict]] = {"repo_no_aplicado": [], "solo_en_base": []}

    # Los sincronizados van en un paso PROPIO, antes de los dos recorridos y
    # no dentro de ellos. Puestos como una excepcion en cada bucle
    # desaparecian: existen de los dos lados --vacios en el archivo, llenos en
    # la base-- asi que el recorrido del repo los saltaba por sincronizados y
    # el de la base los saltaba por 'ya estaba en el repo'. Cada bucle daba
    # por hecho que el otro los reportaba y no los reportaba ninguno.
    for clave in sorted(PROPIAS_DE_LA_BASE):
        valor = base.get(clave)
        if not _vacio(valor):
            dif["solo_en_base"].append(_resumen_sincronizado(clave, valor))

    for k, v in repo.items():
        if k in IGNORADAS or k in PROPIAS_DE_LA_BASE:
            continue
        _recorrer(v, base.get(k, AUSENTE), k, dif)
    for k, v in base.items():
        if k in IGNORADAS or k in PROPIAS_DE_LA_BASE or k in repo:
            continue
        _recorrer(AUSENTE, v, k, dif)
    return dif


def _seccion(ruta: str) -> str:
    """La seccion de primer nivel de una ruta, para agrupar el informe."""
    return ruta.split(".")[0].split("[")[0]


def _resumir(valor: Any) -> str:
    if isinstance(valor, list) and len(valor) > TOPE_DETALLE:
        return f"<{len(valor)} elemento(s)>"
    texto = valor if isinstance(valor, str) else json.dumps(valor, ensure_ascii=False)
    return texto if len(texto) <= 120 else texto[:117] + "..."


def _imprimir(titulo: str, nota: str, filas: list[dict], todo: bool) -> None:
    print(f"\n{titulo}  ({len(filas)})")
    print(f"  {nota}")
    if not filas:
        print("  -- nada")
        return

    por_seccion: dict[str, list[dict]] = {}
    for f in filas:
        por_seccion.setdefault(_seccion(f["ruta"]), []).append(f)

    for seccion, items in sorted(por_seccion.items()):
        if not todo and len(items) > TOPE_DETALLE:
            print(f"\n  {seccion}: {len(items)} diferencias (--todo para verlas)")
            continue
        print(f"\n  {seccion}")
        for f in items:
            print(f"    {f['ruta']}")
            if f.get("faltan") or f.get("sobran"):
                if f.get("faltan"):
                    print(f"        solo en el repo: {_resumir(f['faltan'])}")
                if f.get("sobran"):
                    print(f"        solo en la base: {_resumir(f['sobran'])}")
            elif "faltan" in f:
                # Los mismos elementos en otro orden. Se dice, en vez de
                # imprimir "<15 elemento(s)>" de los dos lados y dejar que
                # alguien pierda diez minutos buscando la diferencia.
                print(f"        mismos {len(f['repo'])} elementos, distinto "
                      f"orden -- sin efecto")
            else:
                print(f"        repo: {_resumir(f['repo'])}")
                print(f"        base: {_resumir(f['base'])}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tenant")
    ap.add_argument("--todo", action="store_true",
                    help="No resume las secciones con muchas diferencias")
    ap.add_argument("--json", help="Guarda el informe completo en este archivo")
    args = ap.parse_args()

    ruta_yaml = RAIZ / "tenants" / f"{args.tenant}.config.yaml"
    if not ruta_yaml.exists():
        raise SystemExit(f"No existe {ruta_yaml}")

    config_repo = cargar_config(ruta_yaml)

    try:
        resultado = fuente.desde_base(args.tenant)
    except fuente.ErrorConfig as e:
        # La base tiene una config que ya no valida contra el schema actual.
        # Es peor que cualquier diferencia y hay que decirlo asi: el motor no
        # puede levantar con eso.
        raise SystemExit(f"[!] La config EN LA BASE no valida:\n{e}")
    except Exception as e:
        raise SystemExit(f"No se pudo leer la base: {type(e).__name__}: {e}")

    if resultado is None:
        raise SystemExit(
            f"'{args.tenant}' no esta en asistente.tenant_config. "
            f"Nunca se cargo: py -3.13 cli/cargar_config.py {args.tenant}")

    config_base, version = resultado

    dif = comparar(config_repo.model_dump(mode="json"),
                   config_base.model_dump(mode="json"))

    print("=" * 72)
    print(f"  CONFIG DE {args.tenant}  --  tenants/{args.tenant}.config.yaml "
          f"vs base (v{version})")
    print("=" * 72)

    _imprimir("[!] EL REPO LO DECLARA Y LA BASE NO DICE LO MISMO",
              "La direccion peligrosa: se escribio, se commiteo, y produccion "
              "no se entero.",
              dif["repo_no_aplicado"], args.todo)

    _imprimir("[i] SOLO LA BASE LO TIENE",
              "Normal en lo que se edita desde la interfaz -- el YAML es "
              "semilla, no fuente de verdad.",
              dif["solo_en_base"], args.todo)

    if args.json:
        Path(args.json).write_text(
            json.dumps({"tenant": args.tenant, "version_base": version, **dif},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nInforme: {args.json}")

    pendientes = len(dif["repo_no_aplicado"])
    print()
    if pendientes:
        print(f"[FALLA] {pendientes} diferencia(s) que el repo declara y la base "
              f"no tiene. Si son cambios que faltan aplicar, se aplican; si son "
              f"ediciones de la interfaz, el YAML esta viejo "
              f"(cli/cargar_config.py {args.tenant} --exportar).")
        raise SystemExit(1)
    print("[OK] La base tiene todo lo que el repo declara.")


if __name__ == "__main__":
    main()
