# -*- coding: utf-8 -*-
"""
================================================================================
 POSPONER UNA ESCALADA: la decision entera, probada donde vive
================================================================================
    py -3.13 tests/test_escalada_del_rol_de_entrada.py

QUE DEFIENDE
------------
`nucleo/seguimiento/forzado.py::por_que_posponer` decide si una escalada que el
evaluador pidio se difiere un turno, y con que nota. `nucleo/canales/api.py`
solo aplica lo que devuelve. Esta prueba importa ESA funcion --no una copia--
y ademas comprueba que `_atender_turno` no tenga logica paralela.

DE DONDE SALE, en tres pasos del 25/09/2026
-------------------------------------------
1. Se midio que el rol de entrada de rapilink declara UNA herramienta en
   'puede_consultar', y es la de derivar. Con la condicion de entonces
   --"no ejecuto ninguna herramienta -> se pospone"-- su escalada se
   posponia SIEMPRE: si no deriva no hay mensaje 'tool', y si deriva ya no
   esta ahi. Y la nota le pedia identificar al cliente y avanzar con un
   procedimiento, dos cosas que no puede hacer.

2. El primer arreglo (A) fue no posponer para ese rol: escalar en el acto.
   Tres lentes lo auditaron y una llego a lo mismo que la reconsideracion
   propia: anulaba lo que el tenant declaro en 'intentar_resolver_antes' y le
   quitaba al router la vuelta en la que podia derivar. Y otra PROBO que la
   prueba de entonces no veia el enganche: puso el api.py anterior y siguio
   16/16 en verde.

3. Esto es B: se pospone UNA vez con una nota que le pide lo unico que puede
   --derivar, nombrando la herramienta de su catalogo--, y si tampoco deriva,
   la siguiente escala. La decision se saco a una funcion pura para que esta
   prueba y el codigo que corre sean el mismo objeto.

POR QUE NO LLAMA AL MODELO NI A LA BASE
---------------------------------------
La decision es determinista. Lo que si necesita al sistema real --que el
router derive con esa nota-- se mide con cli/bateria_flujos.py, que pasa por
atender_turno. Medir aca contra DeepSeek mediria dos cosas a la vez.

LO QUE LA PRUEBA 6 AFIRMA, Y LO QUE NO
--------------------------------------
Que `_atender_turno` llama a `por_que_posponer` y NO recompone la decision con
`con_las_manos_vacias` ni `merece_un_intento` por su cuenta. Es una afirmacion
sobre ausencia de logica paralela --el hueco que el auditor demostro--, no
sobre el efecto en un turno completo. Eso ultimo lo cubre la bateria.
================================================================================
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.seguimiento.forzado import (            # noqa: E402
    por_que_posponer, puede_intentar_algo, con_las_manos_vacias,
    NOTA_MANOS_VACIAS, NOTA_INTENTAR_PRIMERO)

RAZONES = ("derivar_primero", "manos_vacias", "intentar_resolver_antes")

fallos = []


def afirmar(condicion: bool, que: str) -> None:
    print(f"  {'ok  ' if condicion else 'ROJO'}  {que}")
    if not condicion:
        fallos.append(que)


class _H:
    def __init__(self, nombre, deriva_rol=False, verifica_identidad=False):
        self.nombre = nombre
        self.deriva_rol = deriva_rol
        self.verifica_identidad = verifica_identidad


class _Rol:
    def __init__(self, puede_consultar):
        self.puede_consultar = list(puede_consultar)


class _Esc:
    def __init__(self, intentar):
        self.intentar_resolver_antes = list(intentar or [])


class _Cfg:
    def __init__(self, roles, herramientas, intentar=None):
        self.roles = roles
        self.herramientas = herramientas
        self.escalamiento = _Esc(intentar)


SIN_TOOL = [{"role": "user", "content": "quiero cancelar"},
            {"role": "assistant", "content": "Entiendo. Para ayudarte necesito saber..."}]
CON_TOOL = SIN_TOOL + [{"role": "tool", "content": '{"saldo": 0}'}]

# El rol de entrada de rapilink, tal como esta en la config: solo deriva.
ROUTER = _Cfg({"cliente_final": _Rol(["derivar_a_area"])},
              [_H("derivar_a_area", deriva_rol=True)],
              intentar=["frustracion_detectada"])
# Un ejecutor: tiene con que intentar algo antes de molestar a una persona.
EJECUTOR = _Cfg({"soporte": _Rol(["consultar_cliente", "reiniciar_ont", "derivar_a_area"])},
                [_H("consultar_cliente"), _H("reiniciar_ont"), _H("derivar_a_area", deriva_rol=True)],
                intentar=["frustracion_detectada"])


def decide(cfg, rol, historial, *, forzado=False, ya_intento=False, motivo="informacion_a_confirmar"):
    return por_que_posponer(cfg, cfg.roles.get(rol) if rol else None, historial,
                            forzado=forzado, ya_intento=ya_intento, motivo=motivo)


def prueba_1_la_funcion_de_la_traza_esta_bien():
    afirmar(con_las_manos_vacias(SIN_TOOL) is True,
            "sin turnos 'tool', la traza esta vacia -- el hecho es correcto")
    afirmar(con_las_manos_vacias(CON_TOOL) is False,
            "con un turno 'tool' real, ya no estan vacias")
    bloqueada = SIN_TOOL + [{"role": "tool", "content": '{"error": "IDENTIDAD_NO_VERIFICADA"}'}]
    afirmar(con_las_manos_vacias(bloqueada) is True,
            "una llamada que el motor BLOQUEO no cuenta como ejecutada")


def prueba_2_el_rol_que_solo_deriva_recibe_la_nota_que_puede_cumplir():
    razon, nota = decide(ROUTER, "cliente_final", SIN_TOOL)
    afirmar(razon == "derivar_primero",
            f"el rol que solo deriva se pospone UNA vez con razon 'derivar_primero' (dio {razon!r})")
    afirmar("derivar_a_area" in nota,
            "la nota nombra la herramienta de derivacion DE SU CATALOGO")
    prohibidas = [p for p in ("herramientas", "identifica", "procedimiento", "cedula")
                  if p in nota.lower()]
    afirmar(not prohibidas,
            f"la nota NO le pide lo que no puede: sin {['herramientas','identifica','procedimiento','cedula']}"
            + (f" -- aparecio {prohibidas}" if prohibidas else ""))
    afirmar(razon in RAZONES, "y es una de las tres razones que el log distingue por campo")
    razon2, _ = decide(ROUTER, "cliente_final", SIN_TOOL, ya_intento=True)
    afirmar(razon2 is None, "una sola vez: con ya_intento, la siguiente escala")
    razon3, _ = decide(ROUTER, "cliente_final", SIN_TOOL, forzado=True)
    afirmar(razon3 is None, "una escalada forzada por un hecho nunca se pospone")
    razon4, _ = decide(ROUTER, "cliente_final", SIN_TOOL, motivo="frustracion_detectada")
    afirmar(razon4 == "derivar_primero",
            "con un motivo de 'intentar_resolver_antes' el tenant sigue teniendo su vuelta, "
            "y la nota es la que ese rol puede cumplir")


def prueba_3_el_ejecutor_conserva_sus_dos_razones():
    razon, nota = decide(EJECUTOR, "soporte", SIN_TOOL)
    afirmar(razon == "manos_vacias" and nota == NOTA_MANOS_VACIAS,
            "con la traza vacia sigue posponiendo, con la nota de siempre -- no se rompe lo que funciona")
    razon, _ = decide(EJECUTOR, "soporte", CON_TOOL)
    afirmar(razon is None, "si ya consulto algo y el motivo no esta en la lista del tenant, no se pospone")
    razon, nota = decide(EJECUTOR, "soporte", CON_TOOL, motivo="frustracion_detectada")
    afirmar(razon == "intentar_resolver_antes" and nota == NOTA_INTENTAR_PRIMERO,
            "un motivo de 'intentar_resolver_antes' pospone una vuelta, con su nota")
    razon, _ = decide(EJECUTOR, "soporte", CON_TOOL, motivo="frustracion_detectada", forzado=True)
    afirmar(razon is None,
            "y forzado corta TAMBIEN esa rama (antes del 25/09 solo cortaba la primera)")
    razon, _ = decide(EJECUTOR, "soporte", SIN_TOOL, ya_intento=True)
    afirmar(razon is None, "una sola vuelta extra por conversacion")


def prueba_4_no_depende_de_ningun_nombre_de_rol():
    for nombre in ("ventas_entrada", "cobranzas_whatsapp", "recepcion_l0"):
        cfg = _Cfg({nombre: _Rol(["pasar_al_area"])}, [_H("pasar_al_area", deriva_rol=True)])
        razon, nota = decide(cfg, nombre, SIN_TOOL)
        afirmar(razon == "derivar_primero" and "pasar_al_area" in nota,
                f"'{nombre}' que solo deriva -> derivar_primero, nombrando SU herramienta")
    cfg = _Cfg({"recepcion_l0": _Rol(["ver_factura", "pasar_al_area"])},
               [_H("ver_factura"), _H("pasar_al_area", deriva_rol=True)])
    razon, _ = decide(cfg, "recepcion_l0", SIN_TOOL)
    afirmar(razon == "manos_vacias", "'recepcion_l0' CON una ejecutable -> manos_vacias, como un ejecutor")


def prueba_5_sin_nada_que_dar_y_falla_cerrado():
    razon, _ = decide(_Cfg({}, []), None, SIN_TOOL)
    afirmar(razon == "manos_vacias",
            "sin cfg_rol (config ilegible) se comporta como antes: manos vacias (FALLA CERRADO)")
    afirmar(puede_intentar_algo(_Cfg({}, []), None) is True, "  ... porque puede_intentar_algo no afirma nada")
    cfg = _Cfg({"charla": _Rol([])}, [_H("consultar_documentacion")])
    razon, _ = decide(cfg, "charla", SIN_TOOL)
    afirmar(razon is None,
            "un rol legible que ni ejecuta ni deriva -> no hay nada que darle: no se pospone")
    cfg2 = _Cfg({"raro": _Rol(["no_existe_en_el_catalogo"])}, [])
    razon, _ = decide(cfg2, "raro", SIN_TOOL)
    afirmar(razon is None, "declara solo nombres fuera del catalogo -> tampoco")


def prueba_6_el_enganche_no_tiene_logica_paralela():
    """
    Afirma sobre AUSENCIA de logica paralela, no sobre el efecto: si alguien
    vuelve a escribir un 'if con_las_manos_vacias(...)' en _atender_turno, la
    decision deja de ser la que esta prueba importa, y eso es exactamente lo
    que el auditor demostro el 25/09 con el api.py anterior en verde.
    """
    try:
        from nucleo.canales import api
    except Exception as e:                                          # noqa: BLE001
        # NO SE PUDO CORRER no es lo mismo que PASO (D1). Saltearse con exit 0
        # dejaba la unica afirmacion sobre el enganche desactivada en silencio.
        print(f"  (NO SE PUDO CORRER: no se importa api -- {type(e).__name__})")
        afirmar(False, "la guarda del enganche no pudo correr (no es un exito)")
        return
    turno = inspect.getsource(api._atender_turno)
    aplica = inspect.getsource(api._aplicar_posposicion)
    fuente = turno + aplica
    afirmar("_aplicar_posposicion(" in turno,
            "_atender_turno aplica la posposicion por la funcion que la prueba mide")
    afirmar("por_que_posponer(" in aplica and "por_que_posponer(" not in turno,
            "y la decision se pide UNA vez, en _aplicar_posposicion")
    afirmar("con_las_manos_vacias(" not in fuente,
            "y NO decide con con_las_manos_vacias por su cuenta")
    afirmar("merece_un_intento(" not in fuente,
            "ni con merece_un_intento por su cuenta")
    afirmar('"se pospone una vuelta antes de escalar"' in aplica and "razon=razon" in aplica,
            "el log lleva un evento FIJO y la razon como campo (registro.py exige texto constante)")
    # Esta ultima SI es una afirmacion sobre el texto, y es a proposito: que
    # el sitio de llamada pase el rol DEL TURNO y no otro no se puede medir
    # sin conducir _atender_turno entero con base. Era la quinta mutacion del
    # auditor y la unica que prueba_7 no alcanza.
    afirmar("_aplicar_posposicion(config, rol_cfg, estado" in turno,
            "y le pasa el rol del turno, no cualquier rol de la config")
    afirmar("puede_intentar_algo(config, rol_cfg)" in turno,
            "el agendamiento automatico sigue exigiendo que el rol tenga con que (api.py, tras el evaluador)")



def prueba_7_el_ciclo_de_dos_vueltas_se_cumple_de_verdad():
    """
    EL EFECTO, no el texto del fuente. El 26/09/2026 el auditor mostro que
    cinco mutaciones distintas de api.py --dos de ellas posposicion infinita--
    dejaban prueba_6 en verde. Esto las mata: se corre el mecanismo real dos
    veces sobre el mismo estado de sesion y se afirma que la segunda escala.
    """
    try:
        from nucleo.canales import api
    except Exception as e:                                          # noqa: BLE001
        print(f"  (NO SE PUDO CORRER: no se importa api -- {type(e).__name__})")
        afirmar(False, "la prueba del efecto no pudo correr (no es un exito)")
        return

    rol_cfg = ROUTER.roles["cliente_final"]
    estado = {"historial": list(SIN_TOOL), "intento_antes_de_escalar": False,
              "nota_pendiente": None, "conversacion_id": None}

    # Vuelta 1: se pospone, con la nota que ese rol SI puede cumplir.
    primera = api._aplicar_posposicion(ROUTER, rol_cfg, estado, forzado=False,
                                       motivo="solicitud_explicita")
    afirmar(primera is True, "vuelta 1: la escalada se pospone")
    afirmar(estado["intento_antes_de_escalar"] is True,
            "y la vuelta queda CONSUMIDA en el estado de la sesion")
    nota = estado["nota_pendiente"] or ""
    afirmar("derivar_a_area" in nota,
            "la nota nombra la herramienta que el rol tiene, sacada del catalogo")

    # Vuelta 2: sobre el MISMO estado, ya no se pospone -- escala.
    segunda = api._aplicar_posposicion(ROUTER, rol_cfg, estado, forzado=False,
                                       motivo="solicitud_explicita")
    afirmar(segunda is False,
            "vuelta 2: sobre el mismo estado NO se pospone -- la escalada sale")

    # Una escalada forzada por una herramienta no se pospone nunca, ni la
    # primera vez: ya tiene un hecho detras.
    estado_f = {"historial": list(SIN_TOOL), "intento_antes_de_escalar": False,
                "nota_pendiente": None, "conversacion_id": None}
    afirmar(api._aplicar_posposicion(ROUTER, rol_cfg, estado_f, forzado=True,
                                     motivo="solicitud_explicita") is False,
            "y una escalada forzada no se pospone ni en la primera vuelta")
    afirmar(estado_f["nota_pendiente"] is None,
            "ni le deja una nota al modelo")

    # Un ejecutor sin nada en la traza tambien recibe una vuelta, y una sola:
    # la funcion no es un caso especial del rol de entrada.
    estado_e = {"historial": list(SIN_TOOL), "intento_antes_de_escalar": False,
                "nota_pendiente": None, "conversacion_id": None}
    rol_e = EJECUTOR.roles["soporte"]
    afirmar(api._aplicar_posposicion(EJECUTOR, rol_e, estado_e, forzado=False,
                                     motivo="informacion_a_confirmar") is True,
            "un ejecutor con la traza vacia tambien recibe su vuelta")
    afirmar(api._aplicar_posposicion(EJECUTOR, rol_e, estado_e, forzado=False,
                                     motivo="informacion_a_confirmar") is False,
            "y tampoco recibe dos")


def main() -> int:
    print(__doc__.split("=" * 80)[1].strip())
    print()
    for prueba in (prueba_1_la_funcion_de_la_traza_esta_bien,
                   prueba_2_el_rol_que_solo_deriva_recibe_la_nota_que_puede_cumplir,
                   prueba_3_el_ejecutor_conserva_sus_dos_razones,
                   prueba_4_no_depende_de_ningun_nombre_de_rol,
                   prueba_5_sin_nada_que_dar_y_falla_cerrado,
                   prueba_6_el_enganche_no_tiene_logica_paralela,
                   prueba_7_el_ciclo_de_dos_vueltas_se_cumple_de_verdad):
        print(f"\n{prueba.__name__}")
        prueba()
    print()
    if fallos:
        print(f"{len(fallos)} en rojo:")
        for f in fallos:
            print(f"  - {f}")
        return 1
    print("Todo en orden: la decision de posponer vive en una sola funcion, el rol que solo",
          "deriva recibe una nota que puede cumplir, y el enganche no la recompone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
