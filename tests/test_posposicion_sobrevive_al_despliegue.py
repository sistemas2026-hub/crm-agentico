# -*- coding: utf-8 -*-
"""
================================================================================
 LA VUELTA EXTRA SE ESCRIBE EN EL TURNO QUE LA DECIDE
================================================================================

    py -3.13 tests/test_posposicion_sobrevive_al_despliegue.py

Corre sin base, sin credenciales y sin red.

EL DEFECTO QUE CIERRA  (hallado el 27/09/2026 por la cuarta auditoria)
----------------------------------------------------------------------
El mecanismo de persistir la posposicion existia y sus dos mitades estaban
probadas EN AISLAMIENTO ('tests/test_anti_rebote_persistente.py' invoca
'routing_a_persistir' y 'rehidratar_routing'). Lo que nadie afirmaba era el
ENGANCHE con el turno, y el enganche estaba al reves:

    api._atender_turno():
      ~2039   se guardaba el estado de routing       <-- ANTES
      ~2346   se decide posponer y se pone el flag   <-- DESPUES

Asi que el flag puesto en el turno N se escribia en el turno N+1, que es justo
el turno en que se consume. Un despliegue entre los dos seguia regalandole una
vuelta extra a cada conversacion en curso -- el defecto que el commit decia
haber cerrado.

El auditor lo midio borrando las dos mitades del enganche: trece pruebas
quedaron en verde.

POR QUE NO SE PRUEBA A NIVEL DE TURNO
-------------------------------------
Se intento y no vale la pena: '_atender_turno' toca la base por media docena de
caminos antes de llegar a la decision, y sustituirlos de a uno da una prueba
fragil que mide el arnes mas que el codigo. Ademas la capa de conexion lanza
'SystemExit' (deuda D11 de CLAUDE.md), que un 'except Exception' no atrapa, asi
que el arnes moria sin reportar nada.

Se prueba en tres piezas, y las tres afirman sobre el EFECTO:

  1. el ORDEN del enganche, medido sobre el arbol sintactico de api.py -- que es
     exactamente lo que estaba mal;
  2. que la decision DEJA el flag en la sesion y que el paquete a persistir lo
     lleva -- mata la mutacion de borrar esa linea;
  3. que el escritor ESCRIBE, una sola vez, con el dato adentro, y que NO
     escribe cuando no hay nada que guardar.

El efecto punta a punta contra PostgreSQL lo cubre
'tests/test_relevo_transiciones_base.py'.
================================================================================
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.canales import api                                      # noqa: E402
from nucleo.config import cargar_config                             # noqa: E402
from nucleo.seguridad import verificacion                           # noqa: E402

fallos: list[str] = []
afirmaciones = 0


def comprobar(condicion: bool, que: str) -> None:
    global afirmaciones
    afirmaciones += 1
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")

#  El rol de entrada declara una sola herramienta, la de derivar. Es el que
#  posponia SIEMPRE y el que este bloque vino a arreglar.
ROL_ENTRADA = "cliente_final"
ROL_CFG = CONFIG.roles.get(ROL_ENTRADA)

print()
print("=" * 78)
print("  LA VUELTA EXTRA SE ESCRIBE EN EL TURNO QUE LA DECIDE")
print("=" * 78)
print()

# ---------------------------------------------------------------------------
#  1. EL ORDEN del enganche, que es lo que estaba mal
# ---------------------------------------------------------------------------
#  Por AST y no por grep: un grep lee tambien los docstrings, y con ese error
#  este repositorio ya se dio un falso negativo el 26/09/2026.

_FUENTE = (RAIZ / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8")
_ARBOL = ast.parse(_FUENTE)


def _lineas_de_llamada(nombre: str) -> list[int]:
    """Donde se LLAMA a esa funcion. Solo llamadas, nunca prosa."""
    return sorted(n.lineno for n in ast.walk(_ARBOL)
                  if isinstance(n, ast.Call)
                  and isinstance(n.func, ast.Name)
                  and n.func.id == nombre)


def _dentro_de(nombre_funcion: str) -> tuple[int, int]:
    for n in ast.walk(_ARBOL):
        if isinstance(n, ast.FunctionDef) and n.name == nombre_funcion:
            return n.lineno, (n.end_lineno or n.lineno)
    return (0, 0)


_desde, _hasta = _dentro_de("_atender_turno")
comprobar(_desde > 0, "se encontro _atender_turno en el arbol de api.py")

_decision = [l for l in _lineas_de_llamada("_aplicar_posposicion")
             if _desde <= l <= _hasta]
_guardado = [l for l in _lineas_de_llamada("_persistir_routing")
             if _desde <= l <= _hasta]

comprobar(len(_decision) == 1,
          f"hay UN sitio que decide posponer dentro del turno (hay {len(_decision)})")
#  DOS sitios a proposito: uno despues de la derivacion y otro despues de la
#  decision de posponer, los dos por el mismo escritor, que no repite una
#  escritura identica. Lo que importa no es cuantos son: es que haya uno DESPUES
#  de la decision, que es lo que faltaba.
comprobar(len(_guardado) >= 1,
          f"hay al menos un sitio que persiste el routing dentro del turno "
          f"(hay {len(_guardado)})")

#  LA AFIRMACION QUE FALTABA. Si alguien vuelve a apoyarse solo en el bloque de
#  persistencia de arriba, o mueve el guardado antes de la decision, esto se
#  pone rojo.
if _decision and _guardado:
    comprobar(max(_guardado) > _decision[0],
              f"el routing se persiste DESPUES de decidir posponer "
              f"(decide en {_decision[0]}, guarda en {sorted(_guardado)})")
else:
    comprobar(False, "falta uno de los dos sitios: no se puede medir el orden")


#  Y QUE SEA ALCANZABLE, no solo que este despues.
#
#  La quinta auditoria midio que la afirmacion de orden, sola, es ciega: meter la
#  llamada dentro de 'if False:' o de una rama que nunca se cumple la dejaba
#  VERDE. Afirmar que una linea existe y esta en cierto lugar no prueba que
#  corra -- es literalmente lo que CLAUDE.md 6 llama "una prueba que dice que
#  algo EXISTE no prueba que funcione".
#
#  Lo que se afirma acá es estructural y fuerte: el guardado de despues de la
#  decision vive DENTRO DEL MISMO BLOQUE que el 'posponer = True', o sea en la
#  rama que solo se alcanza cuando de verdad se pospuso.
def _llama_a(nodo, nombre: str) -> bool:
    return any(isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
               and c.func.id == nombre
               for c in ast.walk(nodo))


def _bloque_de_la_posposicion():
    """
    El `if` MAS INTERNO que decide posponer, o sea el que tiene la llamada en su
    propio test: `if _aplicar_posposicion(...):`.

    La primera version recorria con ast.walk y devolvia el primer `if` cuyo
    CUERPO contuviera la llamada, que en un archivo de 9.000 lineas es un `if`
    de tres niveles mas arriba. Afirmaba algo cierto pero mucho mas debil.
    """
    candidatos = [n for n in ast.walk(_ARBOL)
                  if isinstance(n, ast.If) and _llama_a(n.test, "_aplicar_posposicion")]
    return candidatos[0] if len(candidatos) == 1 else None


def _sentencias_alcanzables(cuerpo):
    """
    Las sentencias del cuerpo, descendiendo por el control de flujo pero SIN
    entrar en una rama estaticamente muerta.

    Existe porque la afirmacion de orden, sola, dejaba pasar `if False:`
    alrededor de la llamada -- medido por la quinta auditoria y confirmado acá:
    la primera version de esta comprobacion tambien lo dejaba pasar, porque
    ast.walk entra igual en el cuerpo de un `if` constante-falso.
    """
    for sentencia in cuerpo:
        if isinstance(sentencia, ast.If):
            constante = (sentencia.test.value
                         if isinstance(sentencia.test, ast.Constant) else None)
            if constante is None or bool(constante):
                yield from _sentencias_alcanzables(sentencia.body)
            if not (isinstance(sentencia.test, ast.Constant)
                    and bool(sentencia.test.value)):
                yield from _sentencias_alcanzables(sentencia.orelse)
            continue
        if isinstance(sentencia, (ast.For, ast.While, ast.With, ast.Try)):
            yield from _sentencias_alcanzables(getattr(sentencia, "body", []))
            for rama in ("orelse", "finalbody"):
                yield from _sentencias_alcanzables(getattr(sentencia, rama, []))
            for manejador in getattr(sentencia, "handlers", []):
                yield from _sentencias_alcanzables(manejador.body)
            continue
        yield sentencia


_bloque = _bloque_de_la_posposicion()
comprobar(_bloque is not None,
          "se encontro EL bloque que decide posponer, y es uno solo")

if _bloque is not None:
    _guarda_dentro = [
        c.lineno
        for sentencia in _sentencias_alcanzables(_bloque.body)
        for c in ast.walk(sentencia)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
        and c.func.id == "_persistir_routing"]
    comprobar(len(_guarda_dentro) == 1,
              f"el guardado vive dentro del bloque que pospone Y ES ALCANZABLE, "
              f"asi que corre cuando se pospuso de verdad "
              f"(encontrados: {_guarda_dentro})")

# ---------------------------------------------------------------------------
#  2. EL EFECTO de la decision: deja el flag donde se persiste
# ---------------------------------------------------------------------------


class SesionFalsa:
    """Lo minimo que la posposicion toca, con los nombres reales del modelo."""

    def __init__(self):
        self.areas_visitadas = []
        self.intento_antes_de_escalar = False


_sesion = SesionFalsa()
_estado = {"historial": [{"role": "user", "content": "no tengo internet"}],
           "intento_antes_de_escalar": False, "sesion": _sesion,
           "conversacion_id": "conv-posp", "nota_pendiente": None}

_pospuso = api._aplicar_posposicion(CONFIG, ROL_CFG, _estado,
                                    forzado=False,
                                    motivo="sin_datos_para_diagnosticar")

comprobar(_pospuso is True, "el rol de entrada pospone su primera escalada")
comprobar(_estado["intento_antes_de_escalar"] is True,
          "y el estado del turno queda marcado")
comprobar(_sesion.intento_antes_de_escalar is True,
          "Y LA SESION TAMBIEN, que es la mitad que se persiste")
comprobar(bool(_estado.get("nota_pendiente")),
          "queda la nota que el rol de entrada SI puede cumplir")

#  Lo que de verdad importa: que eso salga en el paquete que se escribe.
_paquete = verificacion.routing_a_persistir(_sesion)
comprobar(_paquete.get("intento_antes_de_escalar") is True,
          f"el paquete a persistir lleva la vuelta usada (paquete: {_paquete})")

#  Y la segunda vez NO se pospone: si se pospusiera siempre, el cliente nunca
#  llegaria a una persona. Es el defecto original de este bloque.
_estado2 = {"historial": [{"role": "user", "content": "sigue igual"}],
            "intento_antes_de_escalar": True, "sesion": _sesion,
            "conversacion_id": "conv-posp", "nota_pendiente": None}
comprobar(api._aplicar_posposicion(CONFIG, ROL_CFG, _estado2, forzado=False,
                                   motivo="sin_datos_para_diagnosticar") is False,
          "con la vuelta ya usada NO se pospone otra vez")

# ---------------------------------------------------------------------------
#  3. EL EFECTO del escritor
# ---------------------------------------------------------------------------
_escrituras: list[tuple] = []
_real = getattr(api.persistencia, "guardar_estado_routing", None)
comprobar(_real is not None, "persistencia declara guardar_estado_routing")

api.persistencia.guardar_estado_routing = (
    lambda tenant, cid, datos: _escrituras.append((tenant, cid, dict(datos))))
try:
    api._persistir_routing("rapilink", "conv-posp", {"sesion": _sesion})
    comprobar(len(_escrituras) == 1,
              f"persistir la posposicion hace UNA escritura "
              f"(hizo {len(_escrituras)})")
    if _escrituras:
        _tn, _cid, _datos = _escrituras[0]
        comprobar(_tn == "rapilink" and _cid == "conv-posp",
                  "contra el tenant y la conversacion correctos")
        comprobar(_datos.get("intento_antes_de_escalar") is True,
                  f"con la vuelta usada adentro (escrito: {_datos})")

    #  UNA ESCRITURA POR CAMBIO, no una por sitio de llamada. Es el defecto que
    #  midio la quinta auditoria: el turno que pospone DESPUES de derivar pasaba
    #  por los dos sitios y hacia dos idas a la base, la segunda un
    #  superconjunto de la primera.
    _escrituras.clear()
    _sesion_derivo = SesionFalsa()
    _sesion_derivo.areas_visitadas = ["soporte_tecnico_cliente"]
    _estado_dos = {"sesion": _sesion_derivo}

    #  1) el sitio de la derivacion escribe las areas
    api._persistir_routing("rapilink", "conv-dos", _estado_dos)
    comprobar(len(_escrituras) == 1,
              f"la derivacion escribe una vez (escribio {len(_escrituras)})")

    #  2) el mismo escritor otra vez, sin que nada cambie: NO repite
    api._persistir_routing("rapilink", "conv-dos", _estado_dos)
    comprobar(len(_escrituras) == 1,
              f"llamarlo de nuevo sin cambios NO repite la escritura "
              f"(van {len(_escrituras)})")

    #  3) ahora se pospone: el paquete cambia, asi que SI escribe una vez mas
    _sesion_derivo.intento_antes_de_escalar = True
    api._persistir_routing("rapilink", "conv-dos", _estado_dos)
    comprobar(len(_escrituras) == 2,
              f"cuando el paquete CAMBIA si escribe (van {len(_escrituras)})")
    if len(_escrituras) == 2:
        comprobar(_escrituras[1][2].get("intento_antes_de_escalar") is True
                  and "areas_visitadas" in _escrituras[1][2],
                  f"y la segunda lleva las dos cosas "
                  f"(escribio {_escrituras[1][2]})")

    #  El turno que NO pospone no paga una escritura extra: es la propiedad que
    #  el bloque de persistencia de arriba cuidaba y que no hay que perder.
    _escrituras.clear()
    api._persistir_routing("rapilink", "conv-posp", {"sesion": None})
    api._persistir_routing("rapilink", "", {"sesion": _sesion})
    comprobar(not _escrituras, "sin sesion o sin conversacion no escribe nada")

    #  Y un fallo de la base NO tumba el turno: quien espera una respuesta no
    #  paga el costo de nuestro registro.
    #
    #  SE PRUEBAN LAS DOS FAMILIAS, y la segunda es la que importa: la capa de
    #  conexion lanza SystemExit, que NO hereda de Exception. La primera
    #  version de esta prueba inyectaba solo un RuntimeError y quedaba VERDE
    #  con el 'except Exception' que dejaba escapar la que de verdad ocurre.
    #  Lo midio la quinta auditoria (27/09/2026): verde por la familia
    #  equivocada.
    for tipo, construir in (("Exception", lambda: RuntimeError("la base se cayo")),
                            ("SystemExit", lambda: SystemExit(
                                "No hay datos de conexion en el entorno."))):
        def _revienta(*_a, **_k):
            raise construir()

        api.persistencia.guardar_estado_routing = _revienta
        try:
            api._persistir_routing("rapilink", "conv-posp",
                                       {"sesion": _sesion})
            comprobar(True, f"un fallo de la familia {tipo} NO rompe el turno")
        except BaseException as e:                             # noqa: BLE001
            comprobar(False,
                      f"un fallo de la familia {tipo} rompio el turno: "
                      f"{type(e).__name__}")
finally:
    if _real is not None:
        api.persistencia.guardar_estado_routing = _real

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
print("[OK] La vuelta extra se escribe en el turno que la decide, asi que un")
print("     despliegue no se la regala de nuevo a una conversacion en curso.")
print("=" * 78)
print()
