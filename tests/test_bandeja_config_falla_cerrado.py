# -*- coding: utf-8 -*-
"""
================================================================================
 LA BANDA NO SE APAGA POR NO PODER COMPROBAR SI ESTA ENCENDIDA
================================================================================

    py -3.13 tests/test_bandeja_config_falla_cerrado.py

Corre sin base y sin red: se sustituye '_config_de' y el editor por nombre, y la
peticion se hace con el cliente de prueba de Flask.

POR QUE EXISTE  (hallado el 27/09/2026 por la cuarta auditoria)
---------------------------------------------------------------
'PUT /configuracion/bandeja' exige la clave 'sin_gestion_horas' cuando hay una
banda encendida, porque omitirla apagaria una guarda que protege conversaciones
de clientes reales. La exigencia se relajo a proposito para sobrevivir la ventana
del despliegue: si NO hay nada guardado, omitir la clave no apaga nada.

El problema era como se respondia esa pregunta:

    try:
        ya_guardado = getattr(_config_de(tenant), "sin_gestion_horas", None)
    except Exception:
        ya_guardado = None        # <-- "no hay nada que perder"

Si leer la config fallaba, la respuesta era "no hay nada que perder" y la
omision se aceptaba: **la banda quedaba apagada por no poder confirmar que
estaba encendida.** La unica compuerta del endpoint decidia en un 'except', que
es justo el patron que CLAUDE.md 5 prohibe -- y por el que el interruptor de
autonomia vive fuera de 'tenant_config'.

Ahora falla CERRADO: si no se puede comprobar, no se acepta la omision, y se
dice con un codigo propio para que el frontend pueda distinguirlo de "falta el
campo".

Y la prueba afirma las tres ramas, porque arreglar solo la del medio dejaria
roto el motivo por el que la exigencia se relajo.
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                      # noqa: E402

fallos: list[str] = []
afirmaciones = 0


def comprobar(condicion: bool, que: str) -> None:
    global afirmaciones
    afirmaciones += 1
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


class ConfigFalsa:
    """
    Doble de TenantConfig con lo que ESTE endpoint lee, incluido el metodo que
    devuelve el umbral efectivo: el endpoint lo llama al responder, y un doble
    sin el da 500 y esconde el resultado que la prueba mide.
    """

    def __init__(self, horas, sla=15, umbral=-25.0, tope=24):
        self.sin_gestion_horas = horas
        self.sla_toma_minutos = sla
        self.umbral_rx_dbm = umbral
        self._tope = tope

    def sin_gestion_horas_efectivas(self):
        if self.sin_gestion_horas is None:
            return None
        return min(self.sin_gestion_horas, self._tope)


def pedir(cuerpo: dict, config_de):
    """
    Hace el PUT de verdad contra la ruta, con el mundo exterior sustituido.

    Devuelve (codigo, json). El editor se sustituye por uno que anota: asi se
    puede afirmar TAMBIEN que un rechazo no escribio nada.
    """
    escrituras: list[tuple] = []

    def _guardar(tenant, sla, umbral, horas):
        escrituras.append((tenant, sla, umbral, horas))
        return ConfigFalsa(horas)

    real_config_de = api._config_de
    real_guardar = api.editor.guardar_ajustes_bandeja
    try:
        api._config_de = config_de
        api.editor.guardar_ajustes_bandeja = _guardar
        with api.app.test_client() as cliente:
            r = cliente.put("/configuracion/bandeja", json=cuerpo)
            return r.status_code, (r.get_json() or {}), escrituras
    finally:
        api._config_de = real_config_de
        api.editor.guardar_ajustes_bandeja = real_guardar


def _revienta(_tenant):
    raise RuntimeError("la base no responde")


print()
print("=" * 78)
print("  LA BANDA NO SE APAGA POR NO PODER COMPROBAR SI ESTA ENCENDIDA")
print("=" * 78)
print()

BASE = {"tenant": "rapilink", "sla_toma_minutos": 15, "umbral_rx_dbm": -25}

# ---------------------------------------------------------------------------
#  1. LA RAMA QUE ESTABA MAL: no se puede comprobar -> NO se acepta
# ---------------------------------------------------------------------------
codigo, cuerpo, escrituras = pedir(dict(BASE), _revienta)
comprobar(codigo >= 400,
          f"si no se puede comprobar la banda, la omision se RECHAZA "
          f"(devolvio {codigo})")
comprobar(not escrituras,
          f"y no escribe nada (escribio {len(escrituras)} veces)")
comprobar(cuerpo.get("codigo") == "no_se_pudo_comprobar",
          f"con un codigo propio, distinguible de 'falta el campo' "
          f"(devolvio {cuerpo.get('codigo')!r})")

# ---------------------------------------------------------------------------
#  2. La rama que ya estaba bien: hay banda encendida -> 400
# ---------------------------------------------------------------------------
codigo, cuerpo, escrituras = pedir(dict(BASE), lambda _t: ConfigFalsa(48))
comprobar(codigo == 400,
          f"con la banda encendida, omitir la clave sigue dando 400 "
          f"(devolvio {codigo})")
comprobar(not escrituras, "y tampoco escribe")

# ---------------------------------------------------------------------------
#  3. La rama por la que la exigencia se relajo: sin banda -> SI se puede
#     guardar aunque falte la clave. Es la ventana del despliegue.
# ---------------------------------------------------------------------------
codigo, cuerpo, escrituras = pedir(dict(BASE), lambda _t: ConfigFalsa(None))
comprobar(codigo < 400,
          f"sin banda guardada, el formulario viejo SIGUE pudiendo guardar "
          f"(devolvio {codigo})")
comprobar(len(escrituras) == 1,
          f"y esa si escribe, una vez (escribio {len(escrituras)})")
if escrituras:
    comprobar(escrituras[0][3] is None,
              f"con la banda en None, que es lo que 'ausente' significa cuando "
              f"no habia nada (escribio {escrituras[0]})")

# ---------------------------------------------------------------------------
#  4. Y con la clave explicita en null, se apaga a pedido incluso con banda
# ---------------------------------------------------------------------------
codigo, cuerpo, escrituras = pedir({**BASE, "sin_gestion_horas": None},
                                   lambda _t: ConfigFalsa(48))
comprobar(codigo < 400,
          f"apagar la banda A PEDIDO, mandando null, si se puede "
          f"(devolvio {codigo})")
comprobar(len(escrituras) == 1 and escrituras[0][3] is None,
          f"y se apaga de verdad (escribio {escrituras})")

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
print("[OK] No poder comprobar no es lo mismo que no haber nada: la banda no se")
print("     apaga en silencio, y la ventana del despliegue sigue funcionando.")
print("=" * 78)
print()
