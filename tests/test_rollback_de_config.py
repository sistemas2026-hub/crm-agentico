# -*- coding: utf-8 -*-
"""
================================================================================
 APAGAR UN CAMPO NUEVO BORRA SU CLAVE, Y ESO DECIDE SI EL ROLLBACK SIRVE
================================================================================

    py -3.13 tests/test_rollback_de_config.py

Corre sin base, sin credenciales y sin red.

QUE MIDE, Y POR QUE IMPORTA  (hallado el 27/09/2026)
----------------------------------------------------
'DESPLIEGUE.md' 7 decia que para revertir una imagen alcanzaba con apagar el campo
nuevo desde la interfaz. Medido, es falso, y quien lo siguiera durante un incidente
dejaria al tenant SIN ATENDER creyendo que hizo lo correcto:

  1. el mutador hace doc.pop(...), asi que del documento la clave desaparece;
  2. pero editor._editar persiste config.model_dump(mode='json') -- el modelo
     ENTERO -- y eso REINTRODUCE la clave con valor None (deuda D7);
  3. y extra='forbid' rechaza una clave por ESTAR PRESENTE, no por su valor.

ARREGLADO el mismo dia, con 'editor._sin_los_que_se_borraron': el volcado respeta
el borrado de una clave de primer nivel. Alcance minimo a proposito -- solo saca
claves que (a) el mutador dejo fuera y (b) el volcado trae en None. NO arregla D7:
el editor sigue reescribiendo los defaults anidados. Arregla el caso concreto en que
esa reescritura vuelve destructivo un rollback.

Verificado extrayendo el arbol de f90d3ec y cargando las dos versiones del
documento contra SU esquema:

    ANTES del arreglo      la RECHAZA   -> rollback destructivo
    DESPUES del arreglo    LA CARGA     -> rollback seguro

La pregunta correcta nunca fue "la banda esta apagada?" sino "la imagen anterior
puede cargar lo que quedo en la base?".
================================================================================
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.config import editor                                    # noqa: E402
from nucleo.config.schema import cargar_config                      # noqa: E402

fallos: list[str] = []
avisos: list[str] = []
afirmaciones = 0


def comprobar(condicion: bool, que: str) -> None:
    global afirmaciones
    afirmaciones += 1
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


#  El campo que hoy ejercita el caso. Si manana hay otro campo nuevo que solo vive
#  en la base, agregarlo aca es mas barato que volver a descubrir esto en un
#  incidente.
CAMPO = "sin_gestion_horas"

print()
print("=" * 78)
print("  APAGAR UN CAMPO NUEVO BORRA SU CLAVE")
print("=" * 78)
print()

_rutas = sorted((RAIZ / "tenants").glob("*.config.yaml"))
comprobar(bool(_rutas),
          "hay al menos un tenant para medir (si no, esto no midio nada)")

for _ruta in _rutas:
    _cfg = cargar_config(_ruta)
    _doc = _cfg.model_dump(mode="json")
    #  La banda exige rol de entrada, y tiene que ser un rol DE CLIENTE: la
    #  validacion rechaza uno interno, porque quien atiende un canal publico no
    #  puede consultar a cualquier cliente sin verificar identidad. La primera
    #  version de esta prueba tomaba el primer rol del diccionario --'soporte'--
    #  y el validador la paro. Bien parada.
    _de_cliente = next((n for n, r in (_cfg.roles or {}).items()
                        if getattr(r, "orientado_a", "") == "cliente_final"), None)
    if _de_cliente is None:
        comprobar(False, f"{_ruta.name}: no hay ningun rol de cliente; no se "
                         f"puede medir la banda en este tenant")
        continue
    _doc["rol_de_entrada"] = _de_cliente

    #  1. Encendida: la clave esta en el documento.
    editor._mutar_ajustes_bandeja(_doc, 15, -25.0, 20)
    comprobar(_doc.get(CAMPO) == 20,
              f"{_ruta.name}: encendida, el documento trae {CAMPO}")

    #  2. Apagada: el mutador la SACA del documento.
    editor._mutar_ajustes_bandeja(_doc, 15, -25.0, None)
    comprobar(CAMPO not in _doc,
              f"{_ruta.name}: apagada, el mutador saca {CAMPO} del documento")

    #  3. Y LO QUE SE PERSISTE TAMPOCO LA TRAE. Es la afirmacion central.
    #
    #     Hasta el 27/09/2026 si la traia: 'model_dump()' emite todos los campos
    #     del modelo, asi que la clave volvia con valor None y una imagen anterior
    #     que no la declarara no podia cargar la config -- el tenant dejaba de
    #     atender justo durante un rollback. Lo arregla
    #     'editor._sin_los_que_se_borraron'.
    _tenant = _ruta.stem.replace(".config", "")
    _datos = editor._sin_los_que_se_borraron(
        editor._validar(_tenant, copy.deepcopy(_doc)).model_dump(mode="json"),
        _doc)
    comprobar(CAMPO not in _datos,
              f"{_ruta.name}: lo que se PERSISTE tampoco trae {CAMPO} "
              f"(valor: {_datos.get(CAMPO, '(ausente)')!r})")

    #  4. Y sigue siendo una config valida: sacar la clave no rompe nada, porque
    #     el modelo da None por defecto.
    try:
        editor._validar(_tenant, copy.deepcopy(_datos))
        comprobar(True, f"{_ruta.name}: y el documento sin la clave sigue siendo "
                        f"una config valida")
    except Exception as e:                                         # noqa: BLE001
        comprobar(False, f"{_ruta.name}: el documento sin la clave ya no valida: "
                         f"{type(e).__name__}")

    #  5. LA PROPIEDAD QUE DECIDE EL ROLLBACK: no queda en el documento ninguna
    #     clave que una imagen anterior rechazaria. 'extra=forbid' rechaza por
    #     PRESENCIA, asi que basta con que la clave no este.
    _sobran = [k for k in _datos if k == CAMPO]
    comprobar(not _sobran,
              f"{_ruta.name}: no queda ninguna clave que un esquema anterior "
              f"rechazaria por 'extra_forbidden' (sobran: {_sobran})")

    avisos.append(
        f"{_ruta.name}: apagar la banda BORRA la clave, asi que una imagen que "
        f"no declare ese campo puede cargar la config. El rollback es seguro sin "
        f"tocar SQL. Verificado contra el esquema de f90d3ec el 27/09/2026.")

#  EL ENGANCHE, que es lo que faltaba. Las afirmaciones de arriba llaman al
#  ayudante directamente, asi que seguian VERDES con el arreglo desconectado de
#  '_editar' -- medido, y es el mismo error que esta suite documenta: afirmar
#  sobre la pieza y no sobre el camino.
#
#  '_editar' exige base, asi que el enganche se mide sobre el arbol sintactico:
#  la llamada tiene que estar DENTRO de '_editar', DESPUES del volcado, y en una
#  rama alcanzable.
import ast                                                          # noqa: E402

_FUENTE_EDITOR = (RAIZ / "nucleo" / "config" / "editor.py").read_text(encoding="utf-8")
_ARBOL_EDITOR = ast.parse(_FUENTE_EDITOR)

_editar_nodo = next((n for n in ast.walk(_ARBOL_EDITOR)
                     if isinstance(n, ast.FunctionDef) and n.name == "_editar"), None)
comprobar(_editar_nodo is not None, "se encontro _editar en el arbol del editor")

if _editar_nodo is not None:
    def _alcanzables(cuerpo):
        """Sin entrar en ramas estaticamente muertas."""
        for s in cuerpo:
            if isinstance(s, ast.If):
                constante = (s.test.value if isinstance(s.test, ast.Constant)
                             else None)
                if constante is None or bool(constante):
                    yield from _alcanzables(s.body)
                if not (isinstance(s.test, ast.Constant) and bool(s.test.value)):
                    yield from _alcanzables(s.orelse)
                continue
            if isinstance(s, (ast.For, ast.While, ast.With, ast.Try)):
                yield from _alcanzables(getattr(s, "body", []))
                for rama in ("orelse", "finalbody"):
                    yield from _alcanzables(getattr(s, rama, []))
                for h in getattr(s, "handlers", []):
                    yield from _alcanzables(h.body)
                continue
            yield s

    _sentencias = list(_alcanzables(_editar_nodo.body))
    _linea_volcado = [c.lineno for s in _sentencias for c in ast.walk(s)
                      if isinstance(c, ast.Call)
                      and isinstance(c.func, ast.Attribute)
                      and c.func.attr == "model_dump"]
    _linea_arreglo = [c.lineno for s in _sentencias for c in ast.walk(s)
                      if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                      and c.func.id == "_sin_los_que_se_borraron"]

    comprobar(len(_linea_arreglo) == 1,
              f"_editar llama a _sin_los_que_se_borraron, y es alcanzable "
              f"(encontradas: {_linea_arreglo})")
    comprobar(bool(_linea_volcado) and bool(_linea_arreglo)
              and min(_linea_arreglo) > min(_linea_volcado),
              f"y lo llama DESPUES del volcado, que es donde la clave vuelve "
              f"(volcado en {_linea_volcado}, arreglo en {_linea_arreglo})")

#  6. Y la propiedad general que lo explica: 'extra=forbid' rechaza por PRESENCIA.
#     Se mide con un campo inventado, para no depender de que exista una version
#     anterior del esquema en el arbol.
from nucleo.config.schema import TenantConfig                       # noqa: E402

_base = cargar_config(_rutas[0]).model_dump(mode="json") if _rutas else {}
_con_extra = dict(_base)
_con_extra["un_campo_que_ninguna_version_declara"] = None
_rechazado = False
try:
    TenantConfig(**_con_extra)
except Exception as e:                                             # noqa: BLE001
    _rechazado = "extra_forbidden" in str(e)
comprobar(_rechazado,
          "una clave que el esquema no declara se rechaza AUNQUE VALGA None "
          "(es lo que vuelve destructivo el rollback)")

print()
print("=" * 78)
print(f"  afirmaciones  {afirmaciones}")
print(f"  fallos        {len(fallos)}")
if fallos:
    print()
    print(f"[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    print()
    print("  Si fallo la afirmacion 3, el volcado VOLVIO a reintroducir la clave")
    print("  que el mutador borro, y con eso un rollback de imagen vuelve a")
    print("  dejar al tenant sin atender. Ver editor._sin_los_que_se_borraron")
    print("  y DESPLIEGUE.md 7.")
    print("=" * 78)
    print()
    sys.exit(1)
print()
print("[OK] Medido: apagar el campo BORRA su clave, asi que el rollback de")
print("     imagen no queda destructivo.")
if avisos:
    print()
    print("  LO QUE ESTO SIGNIFICA PARA UN INCIDENTE:")
    for a in avisos:
        print(f"    - {a}")
print("=" * 78)
print()
