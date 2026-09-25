# -*- coding: utf-8 -*-
"""
================================================================================
 UN ROL QUE SOLO DERIVA NO PUEDE ESCALAR  --  prueba de la condicion, sin modelo
================================================================================
    py -3.13 tests/test_escalada_del_rol_de_entrada.py

QUE DEFIENDE
------------
`nucleo/seguimiento/forzado.py::con_las_manos_vacias` devuelve True cuando el
asistente no ejecuto NINGUNA herramienta en toda la conversacion. Es un hecho de
la traza --los mensajes de rol 'tool'-- y esta bien calculado.

El problema no es esa funcion: es como la usa `nucleo/canales/api.py:2252`.

    if (not forzado and not estado["intento_antes_de_escalar"]
            and con_las_manos_vacias(estado["historial"])):
        posponer = True        # la escalada NO ocurre: se difiere un turno

Cruzado con la configuracion real (medido el 25/09/2026 sobre los ocho roles de
rapilink, y coincide con la base):

    soporte                    28 declara   28 ejecutables
    cliente_final               1            0      <-- el rol de entrada
    facturacion_cliente         7            6
    ...

El rol de entrada declara UNA herramienta y es `derivar_a_area`. Entonces:

    si NO deriva  ->  ningun mensaje 'tool'  ->  manos vacias  ->  se POSPONE
    si SI deriva  ->  ya salio del router, y el area toma el caso

No puede escalar en su primer intento NUNCA. Y no es un caso raro: es su estado
permanente. Para ese rol "manos vacias" no significa "no intento lo que sabe
hacer" -- significa "no tiene manos".

La nota que se le inyecta lo confirma sola:

    "Primero intenta lo tuyo: identifica al cliente si hace falta y avanza con
     el procedimiento que corresponda."

El router no puede identificar --ninguna herramienta suya declara
`verifica_identidad`, que es la primera condicion de
`debe_reencauzar_a_derivacion`-- y no tiene procedimiento. Se le pide lo que no
esta en su capacidad: el mismo error que el reencauzamiento corrigio en agosto,
en otra guarda.

POR QUE ESTA PRUEBA NO LLAMA AL MODELO NI A LA BASE
---------------------------------------------------
La condicion es determinista. Medir esto contra DeepSeek mediria dos cosas a la
vez --la condicion y la varianza del modelo-- y este laboratorio ya sabe como
termina eso: el 25/09 la misma celda dio 5/6 y 2/6 en dos tandas.

Lo que si necesita al sistema real --que la conversacion termine con dueño-- no
vive aca.

LO QUE ESTA PRUEBA NO AFIRMA
----------------------------
Que corregir esto elimine el limbo. Arregla el camino del escalamiento cuando el
evaluador YA decidio que hace falta una persona. Un turno donde el evaluador no
pide nada y el router tampoco deriva sigue sin cobertura.
================================================================================
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

fallos = []


def afirmar(condicion: bool, que: str) -> None:
    print(f"  {'ok  ' if condicion else 'ROJO'}  {que}")
    if not condicion:
        fallos.append(que)


class _H:
    """Una herramienta del catalogo, con lo poco que mira la condicion."""

    def __init__(self, nombre, deriva_rol=False, verifica_identidad=False):
        self.nombre = nombre
        self.deriva_rol = deriva_rol
        self.verifica_identidad = verifica_identidad


class _Rol:
    def __init__(self, puede_consultar):
        self.puede_consultar = list(puede_consultar)


class _Cfg:
    def __init__(self, roles, herramientas):
        self.roles = roles
        self.herramientas = herramientas


# ══════════════════════════════════════════════════════════════════════════
#  LA CONDICION, COMO FUNCION DE REFERENCIA
#
#  Vive aca y NO en nucleo/ a proposito: no hay decision de implementarla
#  todavia, y este repositorio ya conoce el costo del codigo sin llamador.
#  Cuando se decida, va en api.py:2252 al lado de con_las_manos_vacias.
# ══════════════════════════════════════════════════════════════════════════
def tenia_algo_que_intentar(config, cfg_rol) -> bool:
    """
    El rol declara al menos una herramienta que NO es de derivacion?

    Es la pieza que le falta a la condicion de api.py:2252. Posponer una
    escalada solo tiene sentido si habia algo que intentar primero; para un rol
    que solo deriva, esperar un turno mas no produce ninguna informacion nueva
    -- y esa es exactamente la leccion del 09/09/2026 que ya esta escrita en el
    bloque de reencauzamiento.

    Sale de `puede_consultar`, igual que el resto de las decisiones de este
    bloque (ver SPEC/objetivos/contexto-por-capacidad-del-turno.md, B1). NO de
    `roles_permitidos` y NO del nombre del rol: un tenant nuevo con otro rol de
    entrada queda cubierto sin tocar codigo (CLAUDE.md 3.3).

    FALLA CERRADO: sin config legible devuelve True, que deja el
    comportamiento actual intacto.
    """
    if cfg_rol is None:
        return True
    catalogo = {h.nombre: h for h in (getattr(config, "herramientas", None) or [])}
    suyas = [catalogo[n] for n in (getattr(cfg_rol, "puede_consultar", None) or [])
             if n in catalogo]
    if not suyas:
        return True
    return any(not getattr(h, "deriva_rol", False) for h in suyas)


def _pospone_hoy(historial) -> bool:
    """La condicion tal como esta HOY en api.py:2252, sin el resto del `if`."""
    from nucleo.seguimiento.forzado import con_las_manos_vacias
    return con_las_manos_vacias(historial)


def _pospone_corregido(config, cfg_rol, historial) -> bool:
    """La condicion con la pieza que falta."""
    from nucleo.seguimiento.forzado import con_las_manos_vacias
    return tenia_algo_que_intentar(config, cfg_rol) and con_las_manos_vacias(historial)


SIN_TOOL = [{"role": "user", "content": "quiero cancelar"},
            {"role": "assistant", "content": "Entiendo. Para ayudarte necesito saber..."}]


def prueba_1_la_funcion_de_la_traza_esta_bien():
    """
    con_las_manos_vacias no es el defecto. Se afirma para que quede claro que
    la correccion NO va ahi -- tocarla romperia a los roles ejecutores, que es
    para quienes fue escrita.
    """
    from nucleo.seguimiento.forzado import con_las_manos_vacias
    afirmar(con_las_manos_vacias(SIN_TOOL) is True,
            "sin turnos 'tool', la traza esta vacia -- el hecho es correcto")
    con_tool = SIN_TOOL + [{"role": "tool", "content": '{"saldo": 0}'}]
    afirmar(con_las_manos_vacias(con_tool) is False,
            "con un turno 'tool' real, ya no estan vacias")
    bloqueada = SIN_TOOL + [{"role": "tool",
                             "content": '{"error": "IDENTIDAD_NO_VERIFICADA"}'}]
    afirmar(con_las_manos_vacias(bloqueada) is True,
            "una llamada que el motor BLOQUEO no cuenta como ejecutada")


def prueba_2_el_rol_de_entrada_queda_bloqueado_hoy():
    cfg = _Cfg({"cliente_final": _Rol(["derivar_a_area"])},
               [_H("derivar_a_area", deriva_rol=True)])
    rol = cfg.roles["cliente_final"]
    afirmar(_pospone_hoy(SIN_TOOL) is True,
            "HOY: el rol que solo deriva pospone la escalada -- y es su estado permanente")
    afirmar(tenia_algo_que_intentar(cfg, rol) is False,
            "no tenia nada que intentar: su unica herramienta lo saca del rol")
    afirmar(_pospone_corregido(cfg, rol, SIN_TOOL) is False,
            "CORREGIDO: ya no pospone, porque esperar un turno no le da nada nuevo")


def prueba_3_el_ejecutor_sigue_posponiendo():
    """
    La razon de ser de la guarda: un caso que llega a la bandeja con la traza
    vacia le pide a una persona que empiece de cero. Eso NO se toca.
    """
    cfg = _Cfg({"soporte_tecnico_cliente": _Rol(["consultar_cliente",
                                                 "reiniciar_ont", "derivar_a_area"])},
               [_H("consultar_cliente"), _H("reiniciar_ont"),
                _H("derivar_a_area", deriva_rol=True)])
    rol = cfg.roles["soporte_tecnico_cliente"]
    afirmar(tenia_algo_que_intentar(cfg, rol) is True,
            "un rol con herramientas de datos SI tenia algo que intentar")
    afirmar(_pospone_corregido(cfg, rol, SIN_TOOL) is True,
            "y sigue posponiendo con la traza vacia -- no se rompe lo que funciona")
    con_tool = SIN_TOOL + [{"role": "tool", "content": '{"plan": "x"}'}]
    afirmar(_pospone_corregido(cfg, rol, con_tool) is False,
            "si ya consulto algo, tampoco se pospone -- como hoy")


def prueba_4_no_depende_de_ningun_nombre_de_rol():
    """
    CLAUDE.md 3.3: un tenant nuevo con otro rol de entrada queda cubierto sin
    tocar codigo. Se prueba con nombres que no existen en ninguna config.
    """
    for nombre in ("ventas_entrada", "cobranzas_whatsapp", "recepcion_l0"):
        cfg = _Cfg({nombre: _Rol(["pasar_al_area"])},
                   [_H("pasar_al_area", deriva_rol=True)])
        afirmar(_pospone_corregido(cfg, cfg.roles[nombre], SIN_TOOL) is False,
                f"'{nombre}' que solo deriva -> no pospone (el nombre no entra)")
    cfg = _Cfg({"recepcion_l0": _Rol(["ver_factura", "pasar_al_area"])},
               [_H("ver_factura"), _H("pasar_al_area", deriva_rol=True)])
    afirmar(_pospone_corregido(cfg, cfg.roles["recepcion_l0"], SIN_TOOL) is True,
            "'recepcion_l0' CON una ejecutable -> sigue posponiendo")


def prueba_5_falla_cerrado():
    """
    Ante la duda, el comportamiento de hoy. Los dos errores no son
    comparables: no posponer de mas manda un caso flaco a la bandeja; posponer
    de mas deja a alguien sin dueño.
    """
    afirmar(tenia_algo_que_intentar(_Cfg({}, []), None) is True,
            "sin cfg_rol -> se comporta como hoy (FALLA CERRADO)")
    cfg = _Cfg({"raro": _Rol([])}, [_H("derivar_a_area", deriva_rol=True)])
    afirmar(tenia_algo_que_intentar(cfg, cfg.roles["raro"]) is True,
            "un rol sin herramientas declaradas -> se comporta como hoy")
    cfg2 = _Cfg({"raro": _Rol(["no_existe_en_el_catalogo"])}, [])
    afirmar(tenia_algo_que_intentar(cfg2, cfg2.roles["raro"]) is True,
            "declara algo que no esta en el catalogo -> se comporta como hoy")


def main() -> int:
    print(__doc__.split("=" * 80)[1].strip())
    print()
    for prueba in (prueba_1_la_funcion_de_la_traza_esta_bien,
                   prueba_2_el_rol_de_entrada_queda_bloqueado_hoy,
                   prueba_3_el_ejecutor_sigue_posponiendo,
                   prueba_4_no_depende_de_ningun_nombre_de_rol,
                   prueba_5_falla_cerrado):
        print(f"\n{prueba.__name__}")
        prueba()
    print()
    if fallos:
        print(f"{len(fallos)} en rojo:")
        for f in fallos:
            print(f"  - {f}")
        return 1
    print("Todo en orden: posponer una escalada solo tiene sentido cuando el rol",
          "tenia algo que intentar, y eso sale de `puede_consultar`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
