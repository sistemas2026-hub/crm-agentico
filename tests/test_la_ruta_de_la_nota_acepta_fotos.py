# -*- coding: utf-8 -*-
"""
================================================================================
 LA RUTA DE LA NOTA ACEPTA 'fotos'  --  07/11/2026
================================================================================
POR QUE ESTA GUARDA EXISTE, que es lo que vale de ella.

Se construyo la cadena entera para que las fotos del tecnico llegaran al
ticket del ISP: el motor que manda varias partes, los topes, el catalogo, el
lado de campo. Treinta y una guardas, todas en verde, y las mutaciones
muertas.

Y en produccion el reporte de la OT #198 contesto 400, sin una sola foto y
sin el texto tampoco. No fallo ninguna de las piezas probadas: fallo la
LISTA BLANCA del cuerpo en `/interno/orden/<id>/anotar-en-el-ticket`, que
nunca llego a tener 'fotos'. El script que la agregaba hizo el reemplazo en
memoria, se cayo en un `assert` posterior y murio antes de escribir el
archivo. El otro cambio del mismo archivo si quedo, asi que
`anotar(... fotos=...)` existia y el cuerpo no podia llegar.

NINGUNA de las 31 guardas podia verlo: todas entran por debajo de la ruta.
Esta entra POR la ruta, que es el unico lugar donde el defecto vivia.

    la funcion anda  +  la ruta la llama  !=  la ruta deja pasar el dato

QUE AFIRMA
----------
  · que un cuerpo CON 'fotos' no se rechace -- el caso que fallo
  · que uno con una clave inventada SI se rechace: la lista blanca es la
    proteccion, y ensancharla de mas la anula
  · que las fotos lleguen a `anotar` tal como entraron
  · y que el 400 diga POR QUE, porque el rastro de campo lo escribe

Se corre sola: `py -3.13 tests/test_la_ruta_de_la_nota_acepta_fotos.py`
================================================================================
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.canales import api                                  # noqa: E402
from nucleo.seguimiento import nota_en_el_ticket as N           # noqa: E402

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    print(f"  {'OK  ' if condicion else 'FALLA'}  {que}")
    if not condicion:
        fallos.append(que)


RUTA = "/interno/orden/11111111-1111-1111-1111-111111111111/anotar-en-el-ticket"
UNA_FOTO = {"nombre": "dano_encontrado-1.jpg", "tipo": "image/jpeg",
            "base64": "AAAA"}

recibido: dict = {}


def _anotar_falso(config, tenant, **kw):
    recibido.clear()
    recibido.update(kw)
    return N.ResultadoNota(N.ANOTADA, referencia="prueba")


def _config_falsa(_tenant):
    return object()


def llamar(cuerpo):
    """Un POST real contra la ruta, con `anotar` y la config sustituidos.

    Lo que se mide es la RUTA: que deja entrar y que le pasa a `anotar`. Lo
    que `anotar` hace con eso ya tiene sus propias guardas
    (`tests/test_fotos_en_la_nota.py`).
    """
    real_anotar = N.anotar
    real_config = api._config_de
    N.anotar = _anotar_falso
    api._config_de = _config_falsa
    try:
        with api.app.test_request_context():
            pass
        return api.app.test_client().post(
            RUTA, query_string={"tenant": "rapilink"}, json=cuerpo)
    finally:
        N.anotar = real_anotar
        api._config_de = real_config


CUERPO = {"ticket": "97981", "texto": "Reporte de campo", "vuelta": 1,
          "momento": "reporte_del_tecnico", "actor": "Mario Vasquez"}


print("== 1. el caso que fallo en produccion ==")

r = llamar({**CUERPO, "fotos": [UNA_FOTO]})
afirmar(r.status_code != 400,
        "un cuerpo CON 'fotos' NO se rechaza -- la OT #198 contesto 400 "
        f"(aca: {r.status_code})")
afirmar(recibido.get("fotos") == [UNA_FOTO],
        "y las fotos llegan a `anotar` tal como entraron")

r = llamar(CUERPO)
afirmar(r.status_code != 400, "y sin fotos sigue funcionando igual")
afirmar(recibido.get("fotos") in (None, []),
        "sin fotos no se inventa una lista")


print()
print("== 2. la lista blanca sigue siendo blanca ==")

r = llamar({**CUERPO, "ticket-estado": "4"})
afirmar(r.status_code == 400,
        "una clave que la ruta no nombra se rechaza: elegir el estado aca "
        "convertiria una nota en un cierre")
cuerpo = r.get_json() or {}
afirmar("ticket-estado" in str(cuerpo.get("error") or ""),
        "y el 400 DICE cual sobraba -- el rastro de campo escribe ese texto, "
        "y sin el queda un numero sin explicacion (medido en la OT #198)")

r = llamar({**CUERPO, "fotos": [UNA_FOTO], "lo_que_sea": 1})
afirmar(r.status_code == 400,
        "aceptar 'fotos' no abrio la puerta a cualquier otra clave")


print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)
print("[OK] La ruta deja entrar las fotos, y nada mas que lo que nombra.")
