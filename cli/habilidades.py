# -*- coding: utf-8 -*-
"""
Que le falta saber hacer a cada agente -- y, si se pide, redactarlo.

    py -3.13 cli/habilidades.py rapilink                # solo detectar
    py -3.13 cli/habilidades.py rapilink --proponer     # detectar y redactar
    py -3.13 cli/habilidades.py rapilink --dias 60
    py -3.13 cli/habilidades.py rapilink --listar

Detectar es SQL puro: no llama al modelo, no escribe nada, y se puede correr
todas las veces que uno quiera. Redactar (--proponer) cuesta una llamada al
modelo por patron y deja borradores en estado 'propuesta'.

NADA queda activo por correr esto. Una habilidad entra al prompt de un agente
solo cuando un humano la aprueba desde /habilidades -- ver el porque en
nucleo/habilidades/analista.py.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv                                    # noqa: E402
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from nucleo.config import fuente                                  # noqa: E402
from nucleo.habilidades import analista                           # noqa: E402
from nucleo.persistencia.db import sesion                         # noqa: E402

ROTULO_SENAL = {
    "escalada_repetida": "escalo al humano por el mismo motivo",
    "sin_procedimiento": "el agente admitio no tener el procedimiento",
    "habilidad_insuficiente": "cargo la habilidad y escalo igual",
}


def listar(tenant: str) -> None:
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select h.codigo, h.nombre, h.estado, h.origen, h.roles_permitidos,
                      (select count(*) from asistente.habilidad_usos u
                        where u.habilidad_id = h.id) as usos
                 from asistente.habilidades h
                where h.organization_id = %s
                order by (h.estado = 'propuesta') desc, h.codigo""", (org,))
        filas = [dict(f) for f in cur.fetchall()]
    if not filas:
        print("No hay ninguna habilidad cargada todavia.")
        return
    print(f"{len(filas)} habilidades\n")
    for f in filas:
        roles = ", ".join(f["roles_permitidos"] or []) or "SIN ROL (no la ve nadie)"
        print(f"  [{f['estado']:9s}] {f['codigo']:22s} {f['usos']:4d} usos  {roles}")
        print(f"              {f['nombre'][:78]}  (origen: {f['origen']})")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("tenant")
    p.add_argument("--dias", type=int, default=analista.DIAS_POR_DEFECTO)
    p.add_argument("--minimo", type=int, default=analista.MINIMO_CASOS,
                   help="cuantos casos hacen falta para hablar de un patron")
    p.add_argument("--proponer", action="store_true",
                   help="ademas de detectar, redacta un borrador por patron")
    p.add_argument("--listar", action="store_true",
                   help="muestra las habilidades ya cargadas y sale")
    args = p.parse_args()

    if args.listar:
        listar(args.tenant)
        return 0

    print(f"Mirando los ultimos {args.dias} dias de {args.tenant}, "
          f"con un piso de {args.minimo} casos por patron.\n")

    patrones = analista.detectar(args.tenant, dias=args.dias, minimo=args.minimo)
    if not patrones:
        print("Ningun patron alcanza el piso. Puede ser que los agentes esten "
              "resolviendo bien, o que no haya suficiente historial todavia.")
        return 0

    print(f"HUECOS DETECTADOS: {len(patrones)}\n")
    for pat in patrones:
        print(f"  {pat.rol:26s} {pat.n_casos:3d} casos  "
              f"{ROTULO_SENAL.get(pat.senal, pat.senal)}")
        print(f"  {'':26s}          {pat.motivo[:70]}")
        for muestra in pat.muestras[:2]:
            print(f"  {'':26s}          \"{muestra[:66]}\"")
        print()

    if not args.proponer:
        print("Para redactar un borrador de cada uno: agregar --proponer")
        return 0

    print("Redactando (una llamada al modelo por patron)...\n")
    config = fuente.cargar(args.tenant)
    for r in analista.proponer(config, args.tenant, dias=args.dias,
                               minimo=args.minimo):
        if r["propuesta"]:
            print(f"  propuesta {r['propuesta']:24s} {r['rol']:22s} {r['nombre']}")
        else:
            # Un patron que no se pudo redactar suele significar que al rol le
            # falta una HERRAMIENTA, no un procedimiento: el modelo tiene la
            # instruccion de no inventar herramientas que el rol no tiene.
            print(f"  SIN BORRADOR             {r['rol']:22s} {r['motivo'][:40]}")

    print("\nNinguna quedo activa. Revisalas y aprobalas en /habilidades.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
