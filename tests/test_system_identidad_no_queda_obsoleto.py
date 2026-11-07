# -*- coding: utf-8 -*-
"""
================================================================================
 SYSTEM NO ENVEJECE  --  ninguna instruccion vigente afirma un estado vencido
================================================================================

    py -3.13 tests/test_system_identidad_no_queda_obsoleto.py        (sin base, sin red)

Por que existe (25/09/2026)
--------------------------
Un mensaje `system` no es memoria: es una **instruccion vigente**. Si contiene
un estado que puede cambiar, en algun momento se vuelve una mentira activa.

Los mensajes que arma el motor se parten en dos poblaciones con reglas de vida
distintas, y esa mezcla es el defecto:

  * cuatro viven dentro de `if not historial` (nucleo/modelo/motor.py:3144) y se
    escriben UNA sola vez, en el primer turno;
  * el resto se apila turno a turno.

Nada reemplaza a los primeros cuando el estado que describen cambia. Medido:
una conversacion que arranca SIN verificar y se verifica despues arrastra para
siempre el bloque "Este cliente TODAVIA NO esta verificado: no sabes quien es,
no tienes su cuenta ubicada y no conoces su servicio" -- mientras
`sesion.verificado` ya es True.

Dos conversaciones que desde afuera estan las dos verificadas reciben asi
instrucciones OPUESTAS, y desde afuera parecen el mismo caso. Es lo que hacia
inconsistentes las mediciones del router: la etiqueta "identidad verificada"
agrupaba dos poblaciones con contexto contrario.

EL PRECEDENTE, que muestra que el arreglo no necesita arquitectura nueva
----------------------------------------------------------------------
De los avisos que se inyectan, UNO ya se limpia: `INSTRUCCION_REENCAUZAR` se
saca del historial con un `pop` justo despues de su vuelta
(nucleo/canales/api.py:1751), con este motivo escrito al lado:

    "Era para ESTA vuelta. Si se queda, los turnos siguientes leen 'en tu
     respuesta anterior le pediste un dato de identidad' cuando ya no es
     cierto."

Ese comentario describe exactamente el defecto general. El patron correcto ya
existe en el codigo, aplicado a un caso y no a los demas.

Las tres partes
---------------
  1. EL EFECTO, dinamico: se corre el motor con una sesion que se verifica a
     mitad de camino y se exige que NINGUN system vigente diga lo contrario.
  2. EL CONTROL, dinamico: la sesion verificada desde el turno 1 NO debe llevar
     el aviso de "no verificado". Sin esta mitad, la parte 1 podria estar
     pasando por una razon equivocada -- una prueba que solo mira una direccion
     no distingue "el bug no esta" de "el escenario no se armo".
  3. LA REGLA GENERAL, estatica: el inventario de puntos donde se inyecta un
     `system` esta FIJADO. Si aparece uno nuevo, esta prueba falla y obliga a
     declarar si su contenido puede envejecer. Es la parte que evita que el
     defecto vuelva con otro estado -- verificacion, servicio ubicado, gestion
     activa, escalada: el patron es el mismo y la identidad fue solo el primero
     que se encontro.

No usa base ni red: sustituye `cliente.chat`, y neutraliza el indice de
habilidades y el RAG -- que la piden y NO son lo que se mide; su aporte es
identico en los dos escenarios.
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config                      # noqa: E402
from nucleo.modelo import cliente, motor                     # noqa: E402
from nucleo.seguridad.verificacion import Sesion             # noqa: E402

TENANT = "rapilink"
ROL = "cliente_final"

#: El texto que NO puede seguir vivo cuando la sesion ya esta verificada.
AVISO_NO_VERIFICADO = "TODAVIA NO esta verificado"
#: Y el que SI corresponde en ese caso.
AVISO_VERIFICADO = "YA esta verificado"

#: Inventario FIJADO de los puntos que inyectan un `system`. Una linea por
#: punto: (archivo, linea aproximada, que inyecta, puede envejecer).
#:
#: ESTA FIJADO A PROPOSITO. Si el motor gana un punto nuevo, el conteo cambia y
#: esta prueba falla: entonces hay que venir aca, declararlo, y decidir si su
#: contenido afirma un estado que puede cambiar. Ese es el trabajo que el
#: defecto de 2026-09-25 mostro que nadie estaba haciendo.
PUNTOS_ESPERADOS_MOTOR = 11
PUNTOS_ESPERADOS_CANAL = 3

capturas: list[list[dict]] = []


def _chat_falso(referencia, mensajes, tools=None, temperatura=0.1,
                timeout=60.0, razonamiento=None):
    capturas.append([dict(m) for m in mensajes])
    return cliente.Respuesta(contenido="Entiendo, permitame revisar eso.")


def _aislar() -> None:
    """Nada sale a la red ni a la base."""
    motor.cliente.chat = _chat_falso
    motor.catalogo_habilidades.indice_de = lambda *a, **k: []
    motor.recuperar = lambda *a, **k: ([], None)
    motor.registrar_sin_resultados = lambda *a, **k: None


def _systems(mensajes: list[dict]) -> list[str]:
    return [str(m.get("content") or "") for m in mensajes
            if m.get("role") == "system"]


def _conversacion(config, *, verificado_en_turno_1: bool) -> list[str]:
    """
    Reproduce el ciclo real: el turno 1 congela el bloque `if not historial`;
    los turnos siguientes reusan ese mismo historial, como hace el canal.

    Devuelve los `system` del payload del ULTIMO turno -- el que decide.
    """
    capturas.clear()
    sesion = Sesion(identificador_canal="573001112233")
    sesion.verificado = verificado_en_turno_1
    if verificado_en_turno_1:
        sesion.nombre = "Cliente De Prueba"

    historial: list[dict] = []
    motor.responder(config, ROL, "hola, no me anda el internet",
                    historial, sesion)

    # El cliente se verifica a mitad de la conversacion, que es el caso normal:
    # `sesion.verificado` se marca en cualquier turno (nucleo/seguridad/
    # verificacion.py:232 y nucleo/canales/api.py:840).
    if not verificado_en_turno_1:
        sesion.verificado = True
        sesion.nombre = "Cliente De Prueba"

    motor.responder(config, ROL, "sigue igual", historial, sesion)
    motor.responder(config, ROL, "quiero cancelar el servicio",
                    historial, sesion)

    if not capturas:
        raise AssertionError("el motor no llego a llamar al modelo: "
                             "el escenario no se armo y nada de lo que sigue "
                             "prueba algo")
    return _systems(capturas[-1])


def parte_1_el_efecto(config) -> list[str]:
    """Verificada a mitad de camino: ningun system puede decir lo contrario."""
    fallos: list[str] = []
    bloques = _conversacion(config, verificado_en_turno_1=False)

    vivos = [b for b in bloques if AVISO_NO_VERIFICADO in b]
    if vivos:
        fallos.append(
            "la sesion esta verificada y el contexto sigue diciendo que no:\n"
            f"        {' '.join(vivos[0].split())[:160]}...")

    if not any(AVISO_VERIFICADO in b for b in bloques):
        fallos.append("y tampoco hay ningun system que diga el estado real "
                      "(verificado): el modelo no tiene de donde sacarlo")
    return fallos


def parte_2_el_control(config) -> list[str]:
    """Verificada desde el turno 1: el aviso correcto, y solo ese."""
    fallos: list[str] = []
    bloques = _conversacion(config, verificado_en_turno_1=True)

    if any(AVISO_NO_VERIFICADO in b for b in bloques):
        fallos.append("verificada desde el turno 1 y aun asi aparece el aviso "
                      "de NO verificado: el escenario esta mal armado")
    if not any(AVISO_VERIFICADO in b for b in bloques):
        fallos.append("verificada desde el turno 1 y NO aparece el aviso de "
                      "verificado: el escenario esta mal armado, y la parte 1 "
                      "no mide lo que dice medir")
    return fallos


def parte_3_la_regla_general() -> list[str]:
    """El inventario de puntos de inyeccion esta fijado."""
    fallos: list[str] = []
    marca = 'role": "system"'

    for ruta, esperados, nombre in (
            (RAIZ / "nucleo" / "modelo" / "motor.py", PUNTOS_ESPERADOS_MOTOR,
             "motor"),
            (RAIZ / "nucleo" / "canales" / "api.py", PUNTOS_ESPERADOS_CANAL,
             "canal"),
    ):
        hallados = ruta.read_text(encoding="utf-8").count(marca)
        if hallados != esperados:
            fallos.append(
                f"{nombre}: el inventario decia {esperados} puntos que "
                f"inyectan un system y ahora hay {hallados}. No es un error de "
                "conteo: hay que ir a cada punto nuevo y decidir si su "
                f"contenido afirma un estado que puede cambiar. Archivo: "
                f"{ruta.relative_to(RAIZ)}")

    # La limpieza que YA existe no puede perderse: es el patron correcto, y el
    # unico caso donde alguien lo aplico.
    api = (RAIZ / "nucleo" / "canales" / "api.py").read_text(encoding="utf-8")
    if "pop(posicion_aviso)" not in api:
        fallos.append(
            "desaparecio el `pop(posicion_aviso)` de api.py: era la unica "
            "limpieza de un system que ya no es cierto, y el precedente del "
            "arreglo general")
    return fallos


def main() -> int:
    config = cargar_config(RAIZ / "tenants" / f"{TENANT}.config.yaml")
    _aislar()

    partes = (
        ("1 - EL EFECTO    verificada a mitad: nada la contradice",
         lambda: parte_1_el_efecto(config)),
        ("2 - EL CONTROL   verificada desde el turno 1",
         lambda: parte_2_el_control(config)),
        ("3 - LA REGLA     el inventario de puntos esta fijado",
         parte_3_la_regla_general),
    )

    total: list[str] = []
    for titulo, fn in partes:
        try:
            fallos = fn()
        except BaseException as e:            # SystemExit incluido, ver abajo
            print(f"  NO SE PUDO MEDIR  {titulo}")
            print(f"      {type(e).__name__}: {e}")
            total.append(f"{titulo}: no se pudo medir")
            continue
        estado = "OK " if not fallos else "ROJO"
        print(f"  {estado}  {titulo}")
        for f in fallos:
            print(f"      - {f}")
        total.extend(fallos)

    print()
    if total:
        print(f"ROJO: {len(total)} problema(s).")
        print("Un `system` es una instruccion vigente, no memoria. Si afirma un")
        print("estado que puede cambiar, en algun momento miente -- y el modelo")
        print("no tiene forma de saber cual de los dos mundos es el de hoy.")
        return 1
    print("Todo en orden: ninguna instruccion vigente afirma un estado vencido.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
