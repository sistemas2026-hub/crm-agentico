# -*- coding: utf-8 -*-
"""¿El PUT de coordenadas contesta 200 o 202?  --  medicion, 10/11/2026

POR QUE HAY QUE MEDIRLO ANTES DE ACTIVAR EL BOTON. El spec de WispHub dice que
`PUT /api/clientes/{id}/` puede contestar «200 con el cliente, O 202 con
task_id», y no dice cuando cada una. Un 202 pasa `raise_for_status()` sin
ruido: el sistema marcaria la operacion como exitosa, le diria al tecnico
«Ubicacion guardada» y nadie habria comprobado que se aplico. Peor: la fila de
idempotencia queda `exitosa` para siempre, asi que no habria forma de volver a
intentarlo.

QUE HACE ESTE SCRIPT
  1. Lee la coordenada actual del servicio de prueba.
  2. Escribe la MISMA coordenada con el ultimo decimal movido.
  3. Imprime el CODIGO HTTP y las CLAVES de la respuesta -- nunca los valores.
  4. Vuelve a leer para confirmar que se aplico.
  5. Deja la coordenada como estaba.

PRIVACIDAD: no imprime ninguna coordenada ni ningun valor de la ficha. Solo el
codigo de estado, los nombres de los campos que vuelven, y si el valor cambio.

SOLO TOCA EL SERVICIO DE PRUEBA. Si cambias ese numero, estas escribiendo
sobre el domicilio de un cliente real.
"""
import sys

SERVICIO_DE_PRUEBA = "5832"      # Mario Sabanagrande, el cliente de pruebas

sys.path.insert(0, "/app")       # ajustar si se corre fuera del contenedor

import requests                                                  # noqa: E402
from nucleo.seguridad import secretos                            # noqa: E402

BASE = "https://api.wisphub.io"
RUTA = f"{BASE}/api/clientes/{SERVICIO_DE_PRUEBA}/"


def main():
    clave = secretos.obtener("rapilink", "WISPHUB_API_KEY")
    if not clave:
        print("no se pudo resolver WISPHUB_API_KEY para rapilink")
        return 1
    cab = {"Authorization": f"Api-Key {clave}"}

    #  1 . como esta ahora
    r = requests.get(RUTA, headers=cab, timeout=30)
    if r.status_code != 200:
        print(f"la lectura previa fallo: {r.status_code}")
        return 1
    antes = (r.json() or {}).get("coordenadas") or ""
    print(f"1. lectura previa      -> 200, el campo "
          f"{'TIENE valor' if antes.strip() else 'esta VACIO'}")

    #  2 . el valor de prueba: el mismo con el ultimo decimal movido. Si no
    #     hay valor previo, no se inventa uno -- se corta.
    if not antes.strip() or "," not in antes:
        print("   el servicio de prueba no tiene una coordenada legible.")
        print("   Sin un valor previo este script no escribe nada: inventar")
        print("   una coordenada es poner la casa en otro lado.")
        return 1
    lat, lon = antes.split(",", 1)
    nuevo = f"{lat.strip()},{lon.strip()[:-1]}{'1' if lon.strip()[-1] != '1' else '2'}"

    #  3 . LA MEDICION
    w = requests.put(RUTA, headers=cab, json={"coordenadas": nuevo}, timeout=30)
    cuerpo = {}
    try:
        cuerpo = w.json() or {}
    except Exception:                                            # noqa: BLE001
        pass
    print(f"2. el PUT contesto     -> {w.status_code}")
    print(f"   claves de la respuesta ({len(cuerpo)}): "
          f"{sorted(cuerpo)[:40] if isinstance(cuerpo, dict) else type(cuerpo).__name__}")
    if w.status_code == 202 or "task_id" in cuerpo:
        print()
        print("   *** 202 / task_id: ES ASINCRONO. El boton NO se puede")
        print("   activar asi: diria 'guardada' sin que se haya aplicado.")
    elif w.status_code == 200:
        print("   200 sincrono: el boton puede confiar en el codigo.")

    #  4 . se aplico?
    r2 = requests.get(RUTA, headers=cab, timeout=30)
    despues = (r2.json() or {}).get("coordenadas") or ""
    print(f"3. relectura           -> {r2.status_code}, "
          f"el valor {'CAMBIO' if despues != antes else 'NO cambio'}")

    #  5 . dejarlo como estaba
    v = requests.put(RUTA, headers=cab, json={"coordenadas": antes}, timeout=30)
    r3 = requests.get(RUTA, headers=cab, timeout=30)
    vuelto = (r3.json() or {}).get("coordenadas") or ""
    print(f"4. restaurado          -> {v.status_code}, "
          f"{'quedo como estaba' if vuelto == antes else '*** NO SE RESTAURO ***'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
