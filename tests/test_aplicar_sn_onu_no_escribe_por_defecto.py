# -*- coding: utf-8 -*-
"""
================================================================================
 EL CLI QUE ESCRIBE EN WISPHUB NO ESCRIBE SI NADIE LO PIDIO
================================================================================

    py -3.13 tests/test_aplicar_sn_onu_no_escribe_por_defecto.py

Corre sin base, sin credenciales y SIN RED: 'requests' se sustituye por un doble
que anota cada llamada y falla la prueba si alguna sale de verdad.

POR QUE EXISTE  (hallado el 27/09/2026 por la cuarta auditoria)
---------------------------------------------------------------
'cli/aplicar_sn_onu.py' hace 'requests.patch' sobre la ficha del cliente en
WispHub de PRODUCCION -- y sobre 'sn_onu', que es el identificador con el que
SmartOLT encuentra despues la ONU. NO es una herramienta del catalogo: es
requests directo, asi que no lo ve el interruptor de autonomia, ni el techo, ni
queda en 'operaciones_externas', ni lo miran las guardas de M06, que solo
recorren 'CONFIG.herramientas'.

Hasta el 26/09/2026 escribia POR DEFECTO, con solo pasarle el CSV. Se mitigo
exigiendo '--aplicar'. Y la cuarta auditoria midio que esa mitigacion **no tenia
ninguna guarda**: borrando 'or not args.aplicar' el CLI volvia a escribir por
defecto y doce pruebas quedaban en verde.

Asi que hoy lo unico que separa un CSV de una escritura masiva contra fichas de
clientes reales es un default en el fuente que nada vigila. Esta prueba lo
vigila.

QUE AFIRMA, Y QUE NO
--------------------
Afirma el EFECTO: cuantas llamadas de escritura SALEN, no que la bandera exista.
Una prueba que dijera "hay un argumento --aplicar" seguiria en verde con el
default invertido.

NO cierra el hueco de fondo -- que este comando no pase por la frontera -- y no
pretende hacerlo: eso es una decision de producto, abierta en
SPEC/objetivos/puerta-humana-y-los-ocho-pasos.md. Esto protege la mitigacion que
existe.
================================================================================
"""

from __future__ import annotations

import csv as csv_mod
import importlib
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

fallos: list[str] = []
afirmaciones = 0


def comprobar(condicion: bool, que: str) -> None:
    global afirmaciones
    afirmaciones += 1
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


#  Se importa DESPUES de fijar el sys.path, y sin credenciales: el modulo lee
#  WISPHUB_API_KEY con un default vacio, asi que importarlo no exige nada.
aplicar = importlib.import_module("cli.aplicar_sn_onu")


class RequestsFalso:
    """
    Doble de 'requests' que anota y nunca sale a la red.

    Cada metodo devuelve una respuesta plausible para que el CLI siga su camino
    -- si devolviera basura, el CLI podria cortar antes de intentar escribir y
    la prueba quedaria verde por el motivo equivocado.
    """

    def __init__(self):
        self.gets: list[str] = []
        self.patches: list[tuple[str, dict]] = []

    class _Resp:
        def __init__(self, cuerpo, codigo=200):
            self._cuerpo = cuerpo
            self.status_code = codigo
            self.text = "ok"

        def json(self):
            return self._cuerpo

        def raise_for_status(self):
            return None

    def get(self, url, **kw):
        self.gets.append(url)
        #  El cliente existe y NO tiene serial: es el caso que habilita escribir.
        return self._Resp({"results": [{"id_servicio": "111", "sn_onu": "",
                                        "nombre": "CLIENTE DE PRUEBA"}]})

    def patch(self, url, **kw):
        self.patches.append((url, dict(kw.get("json") or {})))
        return self._Resp({}, 200)

    #  Si el CLI intentara cualquier otro verbo, que se vea.
    def post(self, *a, **kw):
        self.patches.append(("POST INESPERADO", {}))
        return self._Resp({}, 200)

    def put(self, *a, **kw):
        self.patches.append(("PUT INESPERADO", {}))
        return self._Resp({}, 200)


def _csv_de_laboratorio(carpeta: Path) -> Path:
    """Dos filas de alta confianza. Ningun dato de una persona real."""
    ruta = carpeta / "candidatos.csv"
    with ruta.open("w", encoding="utf-8", newline="") as f:
        w = csv_mod.DictWriter(f, fieldnames=[
            "id_servicio", "nombre_wisphub", "sn_onu_candidato", "confianza"])
        w.writeheader()
        w.writerow({"id_servicio": "111", "nombre_wisphub": "CLIENTE DE PRUEBA",
                    "sn_onu_candidato": "ZTEGLAB000001", "confianza": "alta_confianza"})
        w.writerow({"id_servicio": "222", "nombre_wisphub": "OTRO DE PRUEBA",
                    "sn_onu_candidato": "ZTEGLAB000002", "confianza": "alta_confianza"})
    return ruta


def correr(argumentos: list[str]) -> RequestsFalso:
    """Corre main() con 'requests' sustituido y devuelve lo que se llamo."""
    doble = RequestsFalso()
    real_requests = aplicar.requests
    real_argv = sys.argv
    real_sleep = aplicar.time.sleep
    try:
        aplicar.requests = doble
        aplicar.time.sleep = lambda *_a, **_k: None
        sys.argv = ["aplicar_sn_onu.py", *argumentos]
        try:
            aplicar.main()
        except SystemExit:
            #  El CLI puede salir por su cuenta; lo que se mide es lo que
            #  alcanzo a llamar antes.
            pass
    finally:
        aplicar.requests = real_requests
        aplicar.time.sleep = real_sleep
        sys.argv = real_argv
    return doble


print()
print("=" * 78)
print("  EL CLI QUE ESCRIBE EN WISPHUB NO ESCRIBE SI NADIE LO PIDIO")
print("=" * 78)
print()

with tempfile.TemporaryDirectory() as tmp:
    carpeta = Path(tmp)
    csv = _csv_de_laboratorio(carpeta)
    doc = carpeta / "pendientes.md"

    # -----------------------------------------------------------------------
    #  1. SIN --aplicar: cero escrituras. Es LA afirmacion.
    # -----------------------------------------------------------------------
    d1 = correr(["--csv", str(csv), "--pendientes-doc", str(doc)])
    comprobar(d1.patches == [],
              f"sin --aplicar NO sale ni una escritura (salieron {len(d1.patches)})")

    # -----------------------------------------------------------------------
    #  2. Y tampoco lecturas: el default no habla con WispHub en absoluto.
    # -----------------------------------------------------------------------
    comprobar(d1.gets == [],
              f"sin --aplicar tampoco lee de WispHub (leyo {len(d1.gets)})")

    # -----------------------------------------------------------------------
    #  3. CON --aplicar: SI escribe. Sin esto la prueba pasaria en verde con el
    #     CLI roto, que es el falso positivo clasico de una guarda negativa.
    # -----------------------------------------------------------------------
    d2 = correr(["--csv", str(csv), "--aplicar",
                 "--pendientes-doc", str(doc)])
    comprobar(len(d2.patches) >= 1,
              f"con --aplicar SI escribe, asi que la afirmacion de arriba no es "
              f"vacia (escribio {len(d2.patches)})")
    if d2.patches:
        url, cuerpo = d2.patches[0]
        comprobar("/api/clientes/" in url and "sn_onu" in cuerpo,
                  f"y lo que escribe es el serial en la ficha del cliente "
                  f"(cuerpo: {cuerpo})")
        comprobar(not any(u.startswith(("POST", "PUT")) for u, _ in d2.patches),
                  "y no usa ningun otro verbo")

    # -----------------------------------------------------------------------
    #  4. --dry-run sigue sin escribir aunque venga con --aplicar: el que pide
    #     simular gana. Un comando viejo no puede escribir por sorpresa.
    # -----------------------------------------------------------------------
    d3 = correr(["--csv", str(csv), "--aplicar", "--dry-run",
                 "--pendientes-doc", str(doc)])
    comprobar(d3.patches == [],
              f"--dry-run le gana a --aplicar (salieron {len(d3.patches)})")

    # -----------------------------------------------------------------------
    #  5. --piloto acota: no escribe las dos filas, escribe una.
    # -----------------------------------------------------------------------
    d4 = correr(["--csv", str(csv), "--aplicar", "--piloto", "1",
                 "--pendientes-doc", str(doc)])
    comprobar(len(d4.patches) == 1,
              f"--piloto 1 escribe UNA sola ficha (escribio {len(d4.patches)})")

print()
print("=" * 78)
print(f"  afirmaciones  {afirmaciones}")
print(f"  fallos        {len(fallos)}")
if fallos:
    print()
    print(f"[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    print("=" * 78)
    print()
    sys.exit(1)
print()
print("[OK] Escribir en la ficha de un cliente exige pedirlo, y esta prueba lo")
print("     mide por efecto: cuenta las escrituras que SALEN.")
print("=" * 78)
print()
