# -*- coding: utf-8 -*-
"""
Convierte las herramientas de un tenant en un CONECTOR reutilizable.

    py -3.13 cli/extraer_conector.py rapilink wisphub api.wisphub.io

El tercer argumento es la marca que identifica al sistema dentro de la
'base_url' de cada herramienta.

POR QUE SE EXTRAE Y NO SE ESCRIBE
---------------------------------
Las 29 herramientas de WispHub que tiene Rapilink no se inventaron: cada
'filtros_verificados' paso por el metodo del valor imposible contra la API
real, y cada 'filtros_ignorados_por_api' documenta un filtro que la API acepta
y despues ignora en silencio. Eso costo semanas de sondeo.

Escribir el conector a mano seria volver a escribir todo eso de memoria, con la
garantia de perder detalles. Se extrae de lo que YA funciona en produccion.

QUE SE PARAMETRIZA
------------------
  base_url        -> base_url_ref, una variable que la empresa carga
  roles           -> areas genericas, que el administrador mapea a SUS roles
  campos_permitidos -> viajan con la herramienta, por area

Lo demas viaja tal cual: endpoint, filtros verificados, filtros ignorados,
veredictos, mapeos, precondiciones. Es el conocimiento de la API, y no cambia
de una empresa a otra.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import yaml                                                    # noqa: E402
from dotenv import load_dotenv                                 # noqa: E402

load_dotenv(RAIZ / ".env", override=False)


def extraer(slug: str, id_conector: str, marca: str) -> dict:
    doc = yaml.safe_load((RAIZ / "tenants" / f"{slug}.config.yaml")
                         .read_text(encoding="utf-8"))
    roles = doc.get("roles") or {}

    # Que herramientas son de este sistema. Se mira base_url y base_url_ref:
    # una empresa puede tenerlo fijo y otra por variable, y las dos formas
    # apuntan al mismo sistema.
    def es_de_este_sistema(h):
        rastro = f"{h.get('base_url', '')} {h.get('base_url_ref', '')}".lower()
        return marca.lower() in rastro

    herramientas = [h for h in (doc.get("herramientas") or []) if es_de_este_sistema(h)]
    if not herramientas:
        raise SystemExit(f"Ninguna herramienta de '{slug}' apunta a '{marca}'.")

    # Las areas salen de los roles que de verdad usan estas herramientas, no de
    # una lista imaginada. Un area sin herramientas no le sirve a nadie.
    nombres = {h["nombre"] for h in herramientas}
    areas = {}
    for nombre_rol, rol in roles.items():
        usadas = [n for n in (rol.get("puede_consultar") or []) if n in nombres]
        if usadas:
            areas[nombre_rol] = {
                "descripcion": (rol.get("descripcion") or "").strip().split("\n")[0][:160],
                "orientado_a": rol.get("orientado_a", "colaborador"),
            }

    salida = []
    for h in herramientas:
        nuevo = {k: v for k, v in h.items()
                 if k not in ("roles_permitidos", "base_url", "base_url_ref")}
        # La URL pasa a ser una variable que cada empresa carga: dos ISP con
        # el mismo proveedor pueden tener subdominios distintos.
        nuevo["base_url_ref"] = f"{id_conector.upper()}_BASE_URL"
        nuevo["areas"] = sorted(a for a in areas if h["nombre"] in
                                (roles[a].get("puede_consultar") or []))
        # La lista blanca de campos es la parte sensible: dice que ve cada area
        # de un registro que trae 54 campos, cuatro de ellos contraseñas. Viaja
        # con la herramienta o el conector entrega acceso sin limites.
        campos = {a: roles[a]["campos_permitidos"][h["nombre"]]
                  for a in nuevo["areas"]
                  if (roles[a].get("campos_permitidos") or {}).get(h["nombre"])}
        if campos:
            nuevo["campos_por_area"] = campos
        salida.append(nuevo)

    secretos = sorted({h["auth_ref"] for h in herramientas if h.get("auth_ref")})
    return {
        "id": id_conector,
        "nombre": id_conector.title(),
        "descripcion": f"Herramientas verificadas contra {marca}.",
        "extraido_de": slug,
        "variables": [{
            "nombre": f"{id_conector.upper()}_BASE_URL",
            "etiqueta": "URL base de la API",
            "ejemplo": next((h.get("base_url") for h in herramientas
                             if h.get("base_url")), f"https://{marca}"),
        }],
        "secretos": [{"nombre": s, "etiqueta": f"Credencial de {id_conector.title()}"}
                     for s in secretos],
        "areas": areas,
        "herramientas": salida,
    }


if __name__ == "__main__":
    if len(sys.argv) < 4:
        raise SystemExit("Uso: py -3.13 cli/extraer_conector.py <slug> <id> <marca>")
    slug, id_conector, marca = sys.argv[1], sys.argv[2], sys.argv[3]
    conector = extraer(slug, id_conector, marca)

    destino = RAIZ / "conectores" / f"{id_conector}.yaml"
    destino.parent.mkdir(exist_ok=True)
    destino.write_text(
        yaml.dump(conector, allow_unicode=True, sort_keys=False, width=100),
        encoding="utf-8")

    print(f"  {destino.relative_to(RAIZ)}")
    print(f"    {len(conector['herramientas'])} herramientas")
    print(f"    areas: {', '.join(conector['areas'])}")
    print(f"    secretos que pide: {[s['nombre'] for s in conector['secretos']]}")
