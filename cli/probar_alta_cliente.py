# -*- coding: utf-8 -*-
"""
================================================================================
 CREAR UN CLIENTE DE PRUEBA, Y MEDIR QUE PASA DESPUES
================================================================================
**ESTO ESCRIBE EN LA PLATAFORMA DEL ISP.** Sin `--aplicar` no manda nada: lee
los catalogos y muestra el cuerpo exacto que enviaria.

POR QUE EXISTE  --  14/11/2026
------------------------------
El alta de un cliente desde la app esta frenada por UNA pregunta que nadie
midio: **¿crear un cliente con `plan_internet` genera una factura?**

No es curiosidad. Decide por que puerta de la frontera sale la capacidad:

  * si NO genera factura  -> el efecto es un registro externo que otra
    operacion deshace (el borrado esta medido end-to-end), o sea R2, y sale
    por `frontera.humana()` -- la misma puerta que la coordenada.
  * si SI genera factura  -> el efecto «altera la CUENTA del cliente», o sea
    R4: irreversible, y entonces exige `frontera.critica()` con una aprobacion
    humana persistida y atada a los argumentos. Otro diseno.

Y hay una segunda pregunta igual de necesaria: **que trae el `result` de la
tarea**. La skill tiene medido que «una tarea asincrona puede decir SUCCESS y
traer un error de texto como resultado», y que al borrar hizo falta un `GET`
aparte porque «no basta con el mensaje de la tarea». Para crear, nadie sabe
como averiguar el `id_servicio` del cliente nuevo -- y sin eso no se puede
confirmar nada.

LO QUE MIDE, EN ORDEN
---------------------
  1. POST agregar-cliente        -> 202 + task_id (se imprime el task_id: es
                                    la unica forma de preguntar despues)
  2. GET /api/tasks/<task_id>/   -> que estado, y QUE trae el `result`
  3. GET /api/clientes/?...      -> leer el cliente de vuelta, que es la unica
                                    confirmacion que vale
  4. facturas y saldo            -> LA PREGUNTA: aparecio una factura?

LO QUE NO HACE
--------------
No adivina nada. La zona, el plan y la IP se pasan a mano: una zona que no
corresponde a la red de la IP puede hacer fallar el alta, y eso no se sabe sin
conocer la topologia (medido, ver la skill).

Y NO BORRA SOLO. Al final imprime el comando para retirarlo, pero retirarlo es
una decision de una persona.

Uso
---
    py -3.13 cli/probar_alta_cliente.py                      # los catalogos
    py -3.13 cli/probar_alta_cliente.py --zona 7 --plan 12 --ip 172.16.23.40
    py -3.13 cli/probar_alta_cliente.py --zona 7 ... --aplicar   # ESCRIBE
    py -3.13 cli/probar_alta_cliente.py --limpiar 9876           # BORRA
================================================================================
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv                                    # noqa: E402

load_dotenv(RAIZ / ".env", override=False)

#: El host REAL, no el de la documentacion. El `servers:` del spec dice
#: `api.wisphub.net` y esta mal: medido, produccion es `api.wisphub.io`.
BASE = os.environ.get("WISPHUB_BASE_URL", "https://api.wisphub.io").rstrip("/")
CLAVE = os.environ.get("WISPHUB_API_KEY")
if not CLAVE:
    raise SystemExit("Falta WISPHUB_API_KEY en el entorno")
HEADERS = {"Authorization": f"Api-Key {CLAVE}", "Content-Type": "application/json"}
ESPERA = 30

#: Quien es el cliente de prueba. Se nombra asi para que cualquiera que lo vea
#: en la plataforma sepa que no es una persona, y para poder encontrarlo.
NOMBRE = "ZZZ PRUEBA DEXTER"
APELLIDOS = "NO ES UN CLIENTE"
#: Un documento que no puede ser de nadie: ceros. Nunca uno que parezca real.
CEDULA = "000000000"


def _get(ruta: str, **params):
    r = requests.get(f"{BASE}{ruta}", headers=HEADERS, params=params or None,
                     timeout=ESPERA)
    return r


def catalogos() -> None:
    print(f"Leyendo catalogos de {BASE}  (solo lectura)\n")
    for ruta, titulo in (("/api/zonas/", "ZONAS  (el id va en la URL del alta)"),
                         ("/api/plan-internet/", "PLANES")):
        r = _get(ruta, limit=200)
        if not r.ok:
            print(f"  {titulo}: HTTP {r.status_code}")
            continue
        filas = (r.json() or {}).get("results") or []
        print(f"  {titulo}  ({len(filas)})")
        for f in filas[:60]:
            print(f"      {str(f.get('id')):>6}  {f.get('nombre', '')}")
        print()


def cuerpo_de(plan: int, ip: str, usuario_rb: str) -> dict:
    """Los campos que se mandan, y NADA mas.

    LAS CINCO CONTRASENAS NO VAN, ni vacias ni llenas. La skill: «una
    herramienta de crear cliente debe fijar estos campos en codigo, nunca
    dejar que el modelo los complete». Lo mismo vale para una persona
    apurada: lo que no se manda, el proveedor lo genera.

    `coordenadas` tampoco: es el domicilio de alguien y esta prueba no lo
    necesita.
    """
    return {
        "usuario_rb": usuario_rb,
        "ip": ip,
        "plan_internet": plan,
        "nombre": NOMBRE,
        "apellidos": APELLIDOS,
        "cedula": CEDULA,
        "direccion": "SIN DIRECCION - PRUEBA TECNICA",
        "comentarios": ("Creado por cli/probar_alta_cliente.py para medir si "
                        "el alta genera factura. Retirar al terminar."),
    }


def mirar_la_tarea(task_id: str) -> dict:
    """Que dice la tarea, y QUE TRAE ADENTRO.

    El estado NO alcanza: esta medido que puede decir SUCCESS y traer un error
    de texto en el `result`. Por eso se imprime el result entero.
    """
    for intento in range(12):
        time.sleep(1.5)
        r = _get(f"/api/tasks/{task_id}/")
        if not r.ok:
            print(f"    intento {intento + 1}: HTTP {r.status_code}")
            continue
        cuerpo = r.json() or {}
        tarea = cuerpo.get("task", cuerpo) if isinstance(cuerpo, dict) else {}
        estado = tarea.get("status")
        print(f"    intento {intento + 1}: status={estado}")
        if estado in ("SUCCESS", "FAILURE", "REVOKED"):
            print(f"\n    EL RESULT ENTERO (es lo que nadie habia medido):")
            print(f"      {json.dumps(tarea.get('result'), ensure_ascii=False)[:1200]}")
            return tarea
    print("    la tarea no termino en 18s")
    return {}


def buscar_el_cliente(usuario_rb: str) -> dict:
    """Leerlo de vuelta: la unica confirmacion que vale.

    OJO CON EL CAMPO. Lo que se manda como `usuario_rb` vuelve en `servicio`,
    no en `usuario_rb` (medido en produccion). Una busqueda ingenua por
    `usuario_rb` no lo encontraria nunca, y reportaria fallo sobre un alta que
    funciono.
    """
    r = _get("/api/clientes/", limit=300, ordering="-id_servicio")
    if not r.ok:
        print(f"    no se pudo listar: HTTP {r.status_code}")
        return {}
    for fila in (r.json() or {}).get("results") or []:
        if (str(fila.get("servicio") or "").strip() == usuario_rb
                or str(fila.get("usuario_rb") or "").strip() == usuario_rb
                or NOMBRE in str(fila.get("nombre") or "")):
            return fila
    return {}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--zona", type=int, help="id de zona (va en la URL)")
    p.add_argument("--plan", type=int, help="id del plan de internet")
    p.add_argument("--ip", help="la IP para el cliente nuevo")
    p.add_argument("--usuario-rb", default="", help="por defecto, uno con la hora")
    p.add_argument("--aplicar", action="store_true",
                   help="ESCRIBE: crea el cliente de verdad")
    p.add_argument("--limpiar", type=int,
                   help="BORRA el cliente con ese id_servicio")
    args = p.parse_args()

    if args.limpiar:
        print(f"Retirando el servicio {args.limpiar} de {BASE}")
        #  El borrado REAL vive en un sub-recurso, no en DELETE sobre el
        #  recurso: ese da HTTP 500. Medido end-to-end.
        r = requests.delete(f"{BASE}/api/clientes/{args.limpiar}/perfil/",
                            headers=HEADERS, timeout=ESPERA)
        print(f"  HTTP {r.status_code}  {r.text[:300]}")
        if r.status_code in (200, 202):
            tid = (r.json() or {}).get("task_id")
            if tid:
                mirar_la_tarea(str(tid))
            print("\n  Y COMPROBALO APARTE: el mensaje de la tarea no basta.")
            print(f"    py -3.13 {Path(__file__).name} --ver {args.limpiar}")
        return

    if not (args.zona and args.plan and args.ip):
        catalogos()
        print("Para seguir hace falta elegir, a mano:")
        print("    --zona <id>   --plan <id>   --ip <una libre de esa zona>")
        print("\nLa zona TIENE que corresponder a la red de la IP: no hay forma")
        print("de saberlo sin conocer la topologia, y si no coincide el alta")
        print("puede fallar.")
        return

    usuario_rb = args.usuario_rb or f"prueba-dexter-{int(time.time())}"
    cuerpo = cuerpo_de(args.plan, args.ip, usuario_rb)
    url = f"{BASE}/api/clientes/agregar-cliente/{args.zona}/"

    print("=" * 74)
    print("  LO QUE SE VA A MANDAR")
    print("=" * 74)
    print(f"  POST {url}")
    print(json.dumps(cuerpo, indent=2, ensure_ascii=False))
    print()
    print("  NO van las cinco contrasenas ni las coordenadas: lo que no se")
    print("  manda, el proveedor lo genera. Y nada de esto es una persona.")

    if not args.aplicar:
        print("\n  SIMULACRO: no se mando nada. Con --aplicar se crea de verdad.")
        return

    print("\n" + "=" * 74)
    print("  1 · EL POST")
    print("=" * 74)
    r = requests.post(url, headers=HEADERS, json=cuerpo, timeout=ESPERA)
    print(f"  HTTP {r.status_code}")
    print(f"  {r.text[:600]}")
    if r.status_code not in (200, 201, 202):
        print("\n  No se creo nada. Fin.")
        return

    task_id = str((r.json() or {}).get("task_id") or "")
    print(f"\n  task_id: {task_id or '(no vino)'}")
    print("  GUARDALO: sin el no hay forma de preguntarle despues al proveedor.")

    if task_id:
        print("\n" + "=" * 74)
        print("  2 · LA TAREA")
        print("=" * 74)
        mirar_la_tarea(task_id)

    print("\n" + "=" * 74)
    print("  3 · LEERLO DE VUELTA  (la unica confirmacion que vale)")
    print("=" * 74)
    time.sleep(2)
    cliente = buscar_el_cliente(usuario_rb)
    if not cliente:
        print("  NO SE ENCONTRO. O no se creo, o se busca por el campo")
        print("  equivocado. Las dos cosas hay que mirarlas a mano.")
        return
    id_servicio = cliente.get("id_servicio")
    print(f"  id_servicio ...... {id_servicio}")
    print(f"  servicio ......... {cliente.get('servicio')}")
    print(f"  usuario .......... {cliente.get('usuario')}")
    print(f"  usuario_rb ....... {cliente.get('usuario_rb')}")
    print(f"  ip ............... {cliente.get('ip')}")
    print(f"  estado ........... {cliente.get('estado')}")
    print(f"  interfaz_lan ..... {cliente.get('interfaz_lan')!r}  (vacio es normal)")

    print("\n" + "=" * 74)
    print("  4 · LA PREGUNTA: ¿APARECIO UNA FACTURA?")
    print("=" * 74)
    print(f"  estado_facturas .. {cliente.get('estado_facturas')}")
    print(f"  saldo ............ {cliente.get('saldo')}")
    print(f"  fecha_corte ...... {cliente.get('fecha_corte')}")
    usuario = str(cliente.get("usuario") or "").strip()
    if usuario:
        f = _get("/api/facturas/", cliente=usuario, limit=5)
        if f.ok:
            cuerpo_f = f.json() or {}
            print(f"  facturas del cliente ... count={cuerpo_f.get('count')}")
            for fac in (cuerpo_f.get("results") or [])[:3]:
                print(f"      folio={fac.get('folio')} estado={fac.get('estado')} "
                      f"total={fac.get('total')} emision={fac.get('fecha_emision')}")
        else:
            print(f"  no se pudieron leer las facturas: HTTP {f.status_code}")

    print("\n" + "=" * 74)
    print("  SI GENERO FACTURA -> el alta altera la CUENTA del cliente: es R4,")
    print("  irreversible, y exige frontera.critica() con aprobacion humana.")
    print("  SI NO -> es R2 y sale por frontera.humana(), como la coordenada.")
    print()
    print(f"  PARA RETIRARLO:  py -3.13 {Path(__file__).name} --limpiar {id_servicio}")
    print("=" * 74)


if __name__ == "__main__":
    main()
