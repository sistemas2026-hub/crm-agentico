# -*- coding: utf-8 -*-
"""
Abre cada pantalla de la aplicacion, con sesion real, y comprueba que RENDERICE.

    py -3.13 cli/abrir_pantallas.py
    py -3.13 cli/abrir_pantallas.py --rutas conectores,consumo

POR QUE EXISTE
--------------
'pnpm check' pasa en verde con una pantalla que no monta. Es un chequeo de
TIPOS: no ejecuta nada.

El 06/09/2026 la pantalla de Habilidades se desplego y no abria -- una funcion
llamada desde la plantilla escribia estado, y Svelte 5 corta eso con
'state_unsafe_mutation'. No falla el componente: no monta la pagina entera. El
usuario vio la URL correcta con el contenido de otra pantalla.

Ese mismo dia salio que la bandeja de Instalaciones existia desde hacia cuatro
dias SIN UN SOLO ENLACE hacia ella. Y que la pantalla de Consumo devolvia 500
por un objeto que Flask no sabia serializar.

Tres pantallas dadas por terminadas, tres formas distintas de no funcionar, y
ninguna la habria detectado un test de tipos ni una prueba de endpoints. Lo
unico que las detecta es ABRIRLAS.

QUE COMPRUEBA, Y QUE NO
-----------------------
Comprueba que la ruta exista, que el porton de sesion la deje pasar, que el
servidor la renderice sin reventar, y que tenga un titulo -- una pagina en
blanco con HTTP 200 no esta bien.

NO comprueba la hidratacion en el navegador. Un error que solo ocurre del lado
del cliente puede pasar esto igual. Para eso hace falta un navegador de verdad,
y esto no lo reemplaza: reduce el hueco, no lo cierra.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Toda pantalla propia de este producto -- las que agregamos sobre el CRM
# vendorizado. Si se crea una nueva y no se agrega aca, no la mira nadie.
RUTAS = [
    "conectores", "habilidades", "consumo", "instalaciones",
    "agentes", "manual", "conversaciones", "asistente",
    "configuracion-guiada", "simulador-whatsapp",
    "settings/instalaciones", "settings/planes-venta", "settings/organization",
]

# Lo que de verdad indica una pagina rota. Deliberadamente estrecho: una
# version anterior buscaba '500' suelto y marcaba en rojo un HTML sano de
# 325 KB, que es la forma mas rapida de que el aviso se ignore.
SINTOMAS = ("Internal Error", "<h1>500", "Cannot read propert",
            "is not a function", "state_unsafe_mutation")


def _docker(servicio: str, comando: list[str], entorno=None) -> str:
    base = ["docker", "compose", "exec", "-T"]
    for k, v in (entorno or {}).items():
        base += ["-e", f"{k}={v}"]
    r = subprocess.run(base + [servicio] + comando, cwd=RAIZ,
                       capture_output=True, text=True, timeout=180)
    return r.stdout


def sesion_admin() -> tuple[str, str]:
    """Un JWT real de administrador. Sin sesion todas las rutas dan 307."""
    salida = _docker("backend", ["python", "manage.py", "devlogin",
                                 "admin@rapilinksas.co", "--org", "Rapilink"])
    import re
    tok = re.search(r"jwt_access=([^;]+)", salida)
    org = re.search(r"org=([0-9a-f-]{36})", salida)
    if not tok or not org:
        raise SystemExit(
            "No se pudo conseguir una sesion de administrador.\n"
            "Comprobar que el contenedor 'backend' este arriba y que exista "
            "admin@rapilinksas.co en la organizacion Rapilink.")
    return tok.group(1), org.group(1)


def abrir(rutas: list[str]) -> int:
    tok, org = sesion_admin()
    guion = """
const cookie = `jwt_access=${process.env.TOK}; org=${process.env.ORG}`;
const rutas = JSON.parse(process.env.RUTAS);
const sintomas = JSON.parse(process.env.SINTOMAS);
(async () => {
  const salida = [];
  for (const r of rutas) {
    try {
      const resp = await fetch('http://localhost:5173/' + r,
                               { headers: { cookie }, redirect: 'manual' });
      const html = resp.status === 200 ? await resp.text() : '';
      const roto = sintomas.find((s) => html.includes(s)) || null;
      const m = html.match(/<h1[^>]*>([^<]{2,80})/);
      salida.push({ ruta: r, estado: resp.status, roto,
                    titulo: m ? m[1].trim() : null,
                    destino: resp.headers.get('location') });
    } catch (e) { salida.push({ ruta: r, estado: 0, error: e.message }); }
  }
  console.log('###' + JSON.stringify(salida));
})();
"""
    crudo = _docker("frontend", ["node", "-e", guion], {
        "TOK": tok, "ORG": org,
        "RUTAS": json.dumps(rutas), "SINTOMAS": json.dumps(SINTOMAS)})
    marca = crudo.find("###")
    if marca < 0:
        raise SystemExit(f"El frontend no respondio como se esperaba:\n{crudo[-600:]}")
    resultados = json.loads(crudo[marca + 3:].strip())

    fallos = 0
    for r in resultados:
        if r["estado"] == 200 and not r.get("roto") and r.get("titulo"):
            print(f"  ok     /{r['ruta']:26s} {r['titulo']}")
            continue
        fallos += 1
        if r["estado"] == 200 and r.get("roto"):
            detalle = f"renderizo CON ERROR: {r['roto']}"
        elif r["estado"] == 200:
            print(f"  AVISO  /{r['ruta']:26s} 200 pero sin titulo -- ¿pagina vacia?")
            continue
        elif r["estado"] in (301, 302, 307, 308):
            detalle = f"redirige a {r.get('destino')} (¿sesion o permisos?)"
        elif r["estado"] == 404:
            detalle = "404 -- la ruta no existe (o el contenedor no la tomo: reinicialo)"
        else:
            detalle = r.get("error") or f"HTTP {r['estado']}"
        print(f"  FALLA  /{r['ruta']:26s} {detalle}")
    return fallos


if __name__ == "__main__":
    rutas = RUTAS
    if "--rutas" in sys.argv:
        rutas = sys.argv[sys.argv.index("--rutas") + 1].split(",")
    print(f"Abriendo {len(rutas)} pantalla(s) con sesion de administrador.\n")
    fallos = abrir(rutas)
    print()
    if fallos:
        print(f"[FALLA] {fallos} pantalla(s) no abren bien.")
        raise SystemExit(1)
    print("[OK] Todas las pantallas abren y renderizan.")
