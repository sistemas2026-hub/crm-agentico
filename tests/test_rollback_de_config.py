# -*- coding: utf-8 -*-
"""
================================================================================
 APAGAR UN CAMPO NUEVO NO BORRA SU CLAVE, Y ESO DECIDE SI EL ROLLBACK SIRVE
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

Esta prueba no afirma que el rollback funcione: afirma **lo que de verdad pasa**,
para que el dia que alguien arregle D7 --o rompa este comportamiento de otra forma--
se ponga roja y el documento se actualice con ella.

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
print("  APAGAR UN CAMPO NUEVO NO BORRA SU CLAVE")
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

    #  3. PERO lo que se PERSISTE es el volcado del modelo, y ahi vuelve en None.
    #     Esta es la afirmacion que corrige el documento. Si algun dia deja de ser
    #     cierta, esto se pone rojo y hay que actualizar DESPLIEGUE.md 7.
    _datos = editor._validar(_ruta.stem.replace(".config", ""),
                             copy.deepcopy(_doc)).model_dump(mode="json")
    comprobar(CAMPO in _datos and _datos[CAMPO] is None,
              f"{_ruta.name}: lo que se PERSISTE trae {CAMPO} en None "
              f"(presente: {CAMPO in _datos}, valor: {_datos.get(CAMPO)!r})")

    if CAMPO in _datos:
        avisos.append(
            f"{_ruta.name}: apagar la banda deja '{CAMPO}' persistido en None, "
            f"asi que una imagen que no declare ese campo NO puede cargar esta "
            f"config. El rollback exige borrar la clave. Ver DESPLIEGUE.md 7.")

#  4. Y la propiedad general que lo explica: 'extra=forbid' rechaza por PRESENCIA.
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
    print("  Si fallo la afirmacion 3, el comportamiento CAMBIO: puede que")
    print("  alguien haya arreglado D7. Es una buena noticia, pero hay que")
    print("  actualizar DESPLIEGUE.md 7, que hoy dice que el rollback exige")
    print("  borrar la clave por SQL.")
    print("=" * 78)
    print()
    sys.exit(1)
print()
print("[OK] Medido: apagar el campo NO habilita el rollback de imagen.")
if avisos:
    print()
    print("  LO QUE ESTO SIGNIFICA PARA UN INCIDENTE:")
    for a in avisos:
        print(f"    - {a}")
print("=" * 78)
print()
