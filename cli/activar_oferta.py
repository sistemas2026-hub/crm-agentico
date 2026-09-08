# -*- coding: utf-8 -*-
"""
================================================================================
 ACTIVAR LA OFERTA (servicios ofrecidos + parrilla de canales) EN UN TENANT
================================================================================

Por que existe, y por que NO se usa cargar_config.py
-----------------------------------------------------
Las dos herramientas nuevas ('consultar_servicios_ofrecidos' y
'consultar_parrilla_canales') tienen que llegar al catalogo del tenant en la
BASE. La via obvia seria recargar el YAML entero, y esta medido que eso hoy
seria destructivo -- diagnostico del 08/09/2026 contra produccion v120:

  llm.razonamiento          base='disabled'   archivo=None
      Produccion corre con el razonamiento APAGADO: es el brazo OFF de la
      medicion ON/OFF en curso. El YAML no lo declara, asi que una carga lo
      dejaria en None (= encendido). No parte la medicion en un tercer grupo:
      le da vuelta la variable que se esta midiendo.

  derivar_a_area.roles_permitidos
      base=[cliente_final, facturacion_cliente, soporte_tecnico_cliente, ventas]
      archivo=[cliente_final, facturacion_cliente, soporte_tecnico_cliente]
      Alguien agrego 'ventas' desde la interfaz y el YAML nunca se entero. Una
      carga se lo lleva, y ventas deja de poder derivar.

Este script hace lo MINIMO, en UNA sola transaccion (una sola version nueva de
config, no tres), y no toca ninguna de esas dos cosas.

Que hace exactamente
--------------------
  1. agrega las dos herramientas al catalogo
  2. le da acceso a 'ventas' (puede_consultar + campos_permitidos)
  3. suma 'ventas' a consultar_plan_tv.roles_permitidos
  4. siembra 'servicios_ofrecidos'
  5. reemplaza los prompts de 'cliente_final' y 'ventas' por los del YAML

La parrilla de canales NO se toca: se sube por Excel desde
/settings/oferta, que es su via propia.

Es idempotente: si una herramienta ya esta, la deja como esta y sigue.

AVISO
-----
Escribe la configuracion del tenant en la BASE, y eso crea una version nueva.
Mientras corra la ventana de medicion ON/OFF, esa version parte la comparacion
-- es inevitable para cualquier cambio de config, pero conviene saberlo antes
de correrlo, no despues.

Uso
---
    py -3.13 cli/activar_oferta.py rapilink            # muestra que haria
    py -3.13 cli/activar_oferta.py rapilink --aplicar  # lo escribe
================================================================================
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
load_dotenv(RAIZ / ".env", override=False)

from nucleo.config import editor, fuente                      # noqa: E402
from nucleo.config.schema import TenantConfig                 # noqa: E402

HERRAMIENTAS_NUEVAS = ("consultar_servicios_ofrecidos", "consultar_parrilla_canales")
ROLES_CON_PROMPT_NUEVO = ("cliente_final", "ventas")


def _del_archivo(slug: str) -> dict:
    ruta = RAIZ / "tenants" / f"{slug}.config.yaml"
    if not ruta.exists():
        raise SystemExit(f"No existe {ruta}")
    return yaml.safe_load(io.open(ruta, encoding="utf-8"))


def _mutar(doc: dict, archivo: dict, informe: list[str]) -> None:
    """Toca SOLO lo que necesita la oferta. Todo lo demas del documento queda
    exactamente como estaba en la base."""

    # 1. Las dos herramientas nuevas.
    existentes = {h.get("nombre") for h in doc.get("herramientas", [])}
    por_nombre = {h["nombre"]: h for h in archivo["herramientas"]}
    for nombre in HERRAMIENTAS_NUEVAS:
        if nombre in existentes:
            informe.append(f"  = {nombre}: ya estaba en el catalogo, no se toca")
            continue
        doc.setdefault("herramientas", []).append(por_nombre[nombre])
        informe.append(f"  + {nombre}: se agrega al catalogo")

    # 2. 'ventas' suma acceso a las nuevas y a las dos que necesita para saber
    #    si el plan de un cliente incluye TV. Se agrega lo que falte, no se
    #    reemplaza la lista: en la base puede haber algo que el YAML no tenga
    #    -- es exactamente lo que paso con derivar_a_area.roles_permitidos.
    ventas = doc.get("roles", {}).get("ventas")
    if ventas is None:
        raise editor.ErrorEdicion("este tenant no tiene rol 'ventas'.")
    quiere = archivo["roles"]["ventas"]["puede_consultar"]
    tiene = ventas.setdefault("puede_consultar", [])
    for h in quiere:
        if h not in tiene:
            tiene.append(h)
            informe.append(f"  + ventas.puede_consultar: {h}")
    for campo, permitidos in archivo["roles"]["ventas"].get("campos_permitidos", {}).items():
        if campo not in ventas.setdefault("campos_permitidos", {}):
            ventas["campos_permitidos"][campo] = permitidos
            informe.append(f"  + ventas.campos_permitidos: {campo} -> {permitidos}")

    # 3. consultar_plan_tv tiene que admitir a ventas.
    for h in doc.get("herramientas", []):
        if h.get("nombre") == "consultar_plan_tv":
            roles = h.setdefault("roles_permitidos", [])
            if "ventas" not in roles:
                roles.append("ventas")
                informe.append("  + consultar_plan_tv.roles_permitidos: ventas")

    # 4. Los servicios que vende la empresa. Solo si no hay nada cargado: si
    #    alguien ya los edito desde la pantalla, su version manda sobre la
    #    semilla del archivo.
    if not doc.get("servicios_ofrecidos"):
        doc["servicios_ofrecidos"] = archivo.get("servicios_ofrecidos", [])
        informe.append(f"  + servicios_ofrecidos: {len(doc['servicios_ofrecidos'])} sembrados")
    else:
        informe.append("  = servicios_ofrecidos: ya habia cargados, no se pisan")

    # 5. Los prompts corregidos (derivar aunque creas que el servicio no
    #    existe; usar las herramientas antes de afirmar el catalogo).
    for rol in ROLES_CON_PROMPT_NUEVO:
        nueva = archivo["roles"][rol]["descripcion"]
        if doc["roles"][rol].get("descripcion") != nueva:
            doc["roles"][rol]["descripcion"] = nueva
            informe.append(f"  ~ roles.{rol}.descripcion: se actualiza")

    # La parrilla NO se siembra: se sube por Excel desde /settings/oferta.
    # Escribir [] aca seria pisar lo que alguien pudo haber subido ya.


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    aplicar = "--aplicar" in sys.argv[1:]
    if len(args) != 1:
        raise SystemExit(__doc__.split("Uso\n---")[1].strip())
    slug = args[0]

    archivo = _del_archivo(slug)
    actual = fuente.desde_base(slug)
    if actual is None:
        raise SystemExit(f"No hay configuracion en la base para '{slug}'.")
    cfg, version = actual
    print(f"\n  Tenant '{slug}', configuracion vigente: v{version}\n")

    # Ensayo en seco: se muta una COPIA y se valida, sin tocar la base.
    import copy, json
    doc = json.loads(cfg.model_dump_json())
    informe: list[str] = []
    _mutar(doc, archivo, informe)
    TenantConfig(**doc)          # si el resultado no valida, revienta aca

    if not informe:
        print("  Nada que hacer: ya estaba todo aplicado.\n")
        return

    print("  Cambios que se aplicarian:")
    for linea in informe:
        print(linea)

    # Lo que NO se toca, dicho explicito: es la razon de que este script exista.
    print("\n  Sin tocar (a proposito):")
    print(f"    llm.razonamiento            = {cfg.llm.razonamiento!r}   <- el brazo de la medicion")
    deriva = next((h for h in cfg.herramientas if h.nombre == 'derivar_a_area'), None)
    if deriva:
        print(f"    derivar_a_area.roles_permitidos = {deriva.roles_permitidos}")
    print(f"    parrilla_canales            = {len(cfg.parrilla_canales)} canales (se sube por Excel)")
    print(f"    localidades                 = {len(cfg.localidades)} (propiedad de la base)")

    if not aplicar:
        print("\n  ENSAYO. No se escribio nada.")
        print(f"  Para aplicarlo:  py -3.13 cli/activar_oferta.py {slug} --aplicar\n")
        return

    print("\n  Aplicando...")
    nueva = editor._editar(slug, lambda d: _mutar(d, archivo, []))
    print(f"  Listo. El motor recomprueba la version cada 15s y recarga solo.")
    print(f"  Herramientas en el catalogo: {len(nueva.herramientas)}")
    print(f"  Servicios ofrecidos: {len(nueva.servicios_ofrecidos)}\n")


if __name__ == "__main__":
    main()
