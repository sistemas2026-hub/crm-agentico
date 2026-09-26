# -*- coding: utf-8 -*-
"""
================================================================================
 LA COLA DE LA BANDEJA  --  lo urgente no queda enterrado bajo lo viejo (D18)
================================================================================

    py -3.13 tests/test_cola_bandeja.py          (sin base)

B3.5 de SPEC/CONTRATO_RELEVO_IA_HUMANO.md. La regla es nucleo/relevo/
proyeccion.py; la parte contra PostgreSQL (la ruta /conversaciones con filas
reales) esta en tests/test_relevo_transiciones_base.py, seccion 14.

  1. Cada situacion durable cae en su banda, con quien tiene que moverla y
     desde cuando espera. Lo que no se puede saber queda en None.
  2. D18: 45 conversaciones de legado viejas y UNA escalada nueva sin dueno.
     La nueva va arriba. Con el orden anterior (antiguedad) quedaba ultima.
  3. Dentro de una misma banda manda la espera mas larga.
  4. El legado se muestra como revision y NO se adopta: sigue en version 0.
================================================================================
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.relevo import proyeccion                                # noqa: E402

fallos: list[str] = []
AHORA = datetime(2026, 9, 18, 15, 0, tzinfo=timezone.utc)


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


def hace(minutos: float) -> datetime:
    return AHORA - timedelta(minutes=minutos)


def fila(**campos):
    """Una conversacion como la devuelve db.ultima_actividad()."""
    base = {"id": campos.pop("id", "c"), "canal": "whatsapp", "estado": "abierta",
            "relevo_version": 1, "control": "humano", "control_motivo": "escalada",
            "escalada_a_humano": True, "necesita_atencion_humana": True,
            "asignada_a_usuario_id": None, "asignada_a_nombre": None, "asignada_en": None,
            "tomada_por": None, "pendiente_interno_desde": None, "estado_escalada": None,
            "evaluacion_revisada": False, "escalada_en": hace(30),
            "ultima_atencion_humana": None, "ultimo_mensaje_cliente": None,
            "actualizado_en": hace(30)}
    base.update(campos)
    return base


print("=" * 74)
print(" LA COLA DE LA BANDEJA (D18)")
print("=" * 74)

# ---------------------------------------------------------------------------
print("\n== 1. cada situacion en su banda ==")
CASOS = [
    ("escalada sin dueno", fila(), 2, "humano", "Escalada, sin asignar", hace(30)),
    ("intervenida sin dueno", fila(control_motivo="intervencion", escalada_a_humano=False,
                                   necesita_atencion_humana=False),
     2, "humano", "Intervenida, sin asignar", hace(30)),
    ("el cliente respondio despues de la ultima persona",
     fila(asignada_a_nombre="Ana Perez", asignada_en=hace(50),
          ultima_atencion_humana=hace(20), ultimo_mensaje_cliente=hace(12)),
     1, "humano", "Cliente respondió — espera a Ana Perez", hace(12)),
    ("el cliente escribio y todavia no le respondio nadie",
     fila(ultimo_mensaje_cliente=hace(5)),
     1, "humano", "Cliente respondió — sin asignar", hace(5)),
    ("ya le respondieron despues de su ultimo mensaje",
     fila(asignada_a_nombre="Ana Perez", asignada_en=hace(50),
          ultimo_mensaje_cliente=hace(20), ultima_atencion_humana=hace(3)),
     5, "humano", "En atención: Ana Perez", hace(50)),
    ("evaluacion sin revisar, con dueno",
     fila(asignada_a_nombre="Ana Perez", asignada_en=hace(40), estado_escalada="NO_DETERMINADO",
          ultima_atencion_humana=hace(10)),
     3, "humano", "Falta revisar la evaluación", hace(30)),
    ("evaluacion sin revisar, y la atiende la IA",
     fila(control="ia", control_motivo=None, escalada_a_humano=False,
          necesita_atencion_humana=False, estado_escalada="NO_DETERMINADO"),
     3, "humano", "Falta revisar la evaluación", hace(30)),
    ("evaluacion YA revisada: vuelve a su banda",
     fila(asignada_a_nombre="Ana Perez", asignada_en=hace(40), estado_escalada="NO_DETERMINADO",
          evaluacion_revisada=True, ultima_atencion_humana=hace(10)),
     5, "humano", "En atención: Ana Perez", hace(40)),
    ("pendiente interno",
     fila(asignada_a_nombre="Ana Perez", asignada_en=hace(60), pendiente_interno_desde=hace(25),
          ultima_atencion_humana=hace(10)),
     4, "interno", "Pendiente interno", hace(25)),
    ("legado escalado: revision, no cola",
     fila(relevo_version=0, control="ia", control_motivo=None, tomada_por=None),
     6, "revision", "Legado: requiere revisión", hace(30)),
    ("la atiende la IA: fuera de la cola",
     fila(control="ia", control_motivo=None, escalada_a_humano=False,
          necesita_atencion_humana=False),
     None, "ia", "La atiende la IA", None),
    ("cerrada: no necesita a nadie",
     fila(estado="cerrada"), None, "nadie", "Cerrada", None),
]
for nombre, f, banda, necesita, motivo, desde in CASOS:
    p = proyeccion.proyectar(f)
    comprobar(p["banda"] == banda and p["necesita_accion_de"] == necesita
              and p["motivo_cola"] == motivo and p["esperando_desde"] == desde,
              f"{nombre}: banda {banda}, {necesita}, «{motivo}» "
              f"(dio banda {p['banda']}, {p['necesita_accion_de']}, «{p["motivo_cola"]}»)")

sin_fecha = proyeccion.proyectar(fila(escalada_en=None, actualizado_en=None))
comprobar(sin_fecha["esperando_desde"] is None and sin_fecha["banda"] == 2,
          "sin fecha de la que derivar la espera: queda en None, no se inventa")

# ---------------------------------------------------------------------------
print("\n== 2. D18: una escalada nueva no queda enterrada bajo el legado ==")
bandeja = [fila(id=f"legado-{i}", relevo_version=0, control="ia", control_motivo=None,
                escalada_en=hace(60 * 24 * (3 + i)), actualizado_en=hace(60 * 24 * (3 + i)))
           for i in range(45)]
nueva = fila(id="escalada-nueva", escalada_en=hace(4), actualizado_en=hace(4))
bandeja.append(nueva)
proyectadas = [{**c, **proyeccion.proyectar(c)} for c in bandeja]
ordenadas = sorted(proyectadas, key=proyeccion.orden_de_cola)
comprobar(ordenadas[0]["id"] == "escalada-nueva",
          f"la escalada de hace 4 minutos queda primera, sobre 45 de legado de dias "
          f"({ordenadas[0]['id']})")
por_antiguedad = sorted(proyectadas, key=lambda c: c["escalada_en"])
comprobar(por_antiguedad[-1]["id"] == "escalada-nueva",
          "y con el orden viejo (antiguedad global) quedaba ULTIMA: eso es D18")
comprobar(all(c["banda"] == 6 for c in ordenadas[1:]),
          "las 45 de legado quedan detras, en la banda de revision")

# ---------------------------------------------------------------------------
print("\n== 3. dentro de una banda, el que mas espera ==")
a = fila(id="A", escalada_en=hace(40), actualizado_en=hace(40))
b = fila(id="B", escalada_en=hace(5), actualizado_en=hace(5))
mezcla = [{**c, **proyeccion.proyectar(c)} for c in (b, a)]
comprobar([c["id"] for c in sorted(mezcla, key=proyeccion.orden_de_cola)] == ["A", "B"],
          "misma banda: 40 minutos esperando va antes que 5")
con_cliente = {**fila(id="C", ultimo_mensaje_cliente=hace(1)),
               **proyeccion.proyectar(fila(id="C", ultimo_mensaje_cliente=hace(1)))}
comprobar(sorted(mezcla + [con_cliente], key=proyeccion.orden_de_cola)[0]["id"] == "C",
          "pero un cliente esperando (banda 1) va antes que cualquier espera de la banda 2")
sin_desde = {**fila(id="D", escalada_en=None, actualizado_en=None),
             **proyeccion.proyectar(fila(id="D", escalada_en=None, actualizado_en=None))}
comprobar(sorted(mezcla + [sin_desde], key=proyeccion.orden_de_cola)[-1]["id"] == "D",
          "el que no tiene desde cuando espera va al final de su banda, no al principio")

# ---------------------------------------------------------------------------
print("\n== 4. el legado se muestra, no se adopta ==")
legado = fila(relevo_version=0, control="ia", control_motivo=None, tomada_por="Ana Perez")
copia = dict(legado)
p = proyeccion.proyectar(legado)
comprobar(p["es_legado"] and p["banda"] == 6 and p["asignada_a"] == "Ana Perez",
          "legado tomado: sigue en revision y se ve quien lo tiene (tomada_por)")
comprobar(legado == copia, "proyectar no modifica la fila: es lectura")
comprobar(all(proyeccion.proyectar(f).get("relevo_version", 0) == 0 for f in [legado]),
          "y no toca relevo_version: adoptar es G8")

# ---------------------------------------------------------------------------
print("\n== 5. sin una accion de resolucion registrada (guarda anti-limbo) ==")
# La fila de un limbo como los cinco medidos en produccion el 25/09/2026: la
# atiende la IA, nunca salio del rol de entrada, sin escalada ni caso ni
# ticket, hubo un pedido (2+ mensajes), lo ultimo visible lo dijo la IA hace
# horas y el cliente no volvio. Todo son columnas que la fila YA trae.


def limbo(**campos):
    base = fila(control="ia", control_motivo=None, escalada_a_humano=False,
                necesita_atencion_humana=False, rol_efectivo="cliente_final",
                caso_id=None, ticket_operativo=None, mensajes_cliente=2,
                ultimo_rol="assistant", ultimo_mensaje_en=hace(60 * 5),
                escalada_en=None, tomada_en=None, ultima_atencion_humana=None)
    base.update(campos)
    return base


BANDA = dict(rol_de_entrada="cliente_final", sin_gestion_horas=2, ahora=AHORA)
p = proyeccion.proyectar(limbo(), **BANDA)
comprobar(p["banda"] == 3 and p["banda_nombre"] == "sin_gestion"
          and p["necesita_accion_de"] == "humano"
          and p["motivo_cola"] == "Sin una acción de resolución registrada"
          and p["esperando_desde"] == hace(60 * 5),
          "un limbo de 5 horas entra a la banda 3 como 'sin_gestion', para una persona, "
          "esperando desde el ultimo mensaje de la IA")
comprobar(proyeccion.proyectar(limbo())["banda"] is None,
          "sin rol_de_entrada ni umbral la banda NO existe (falla cerrado): sigue 'la atiende la IA'")
comprobar(proyeccion.proyectar(limbo(), rol_de_entrada="cliente_final", ahora=AHORA)["banda"] is None,
          "con rol pero sin umbral, tampoco")
comprobar(proyeccion.proyectar(limbo(ultimo_mensaje_en=hace(30)), **BANDA)["banda"] is None,
          "la IA contesto hace 30 minutos: es una conversacion en curso, no un limbo")
comprobar(proyeccion.proyectar(limbo(rol_efectivo="facturacion_cliente"), **BANDA)["banda"] is None,
          "si derivo a un area, hubo una accion de resolucion: no es limbo")
comprobar(proyeccion.proyectar(limbo(mensajes_cliente=1), **BANDA)["banda"] is None,
          "un 'hola' y el saludo de vuelta no es un pedido sin resolver (hace falta 2+)")
comprobar(proyeccion.proyectar(limbo(ultimo_rol="user"), **BANDA)["banda"] is None,
          "si lo ultimo visible es del cliente, es el cliente quien espera: eso es otra banda")
comprobar(proyeccion.proyectar(limbo(caso_id="caso-1"), **BANDA)["banda"] is None,
          "con un caso abierto hay una accion registrada")
comprobar(proyeccion.proyectar(limbo(ticket_operativo="T-1"), **BANDA)["banda"] is None,
          "con un ticket, tambien")
comprobar(proyeccion.proyectar(limbo(ultima_atencion_humana=hace(60 * 5)), **BANDA)["banda"] is None,
          "el ultimo 'assistant' es de una persona (mismo instante que ultima_atencion_humana): no entra")
comprobar(proyeccion.proyectar(limbo(ultima_atencion_humana=hace(60 * 3)), **BANDA)["banda"] is None,
          "una persona la toco DESPUES del ultimo mensaje de la IA: no reentra (sin ping-pong)")
comprobar(proyeccion.proyectar(limbo(tomada_en=hace(60 * 4)), **BANDA)["banda"] is None,
          "ni si alguien la tomo despues")
comprobar(proyeccion.proyectar(limbo(ultima_atencion_humana=hace(60 * 9)), **BANDA)["banda"] == 3,
          "pero si la IA volvio a contestar despues de la persona y el cliente no volvio, entra "
          "con antiguedad nueva")
viejo = {**limbo(id="L"), **proyeccion.proyectar(limbo(id="L"), **BANDA)}
f_rev = fila(id="R", control="ia", control_motivo=None, escalada_a_humano=False,
             necesita_atencion_humana=False, estado_escalada="NO_DETERMINADO",
             escalada_en=hace(10))
rev = {**f_rev, **proyeccion.proyectar(f_rev, **BANDA)}
comprobar([c["id"] for c in sorted([rev, viejo], key=proyeccion.orden_de_cola)] == ["L", "R"],
          "comparte la banda 3 con 'falta revisar', y dentro manda la espera mas larga")
copia = limbo()
proyeccion.proyectar(copia, **BANDA)
comprobar(copia == limbo(), "la banda nueva tampoco escribe: proyectar sigue siendo lectura")

if fallos:
    print(f"\n[FALLA] {len(fallos)} caso(s):")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("\n[OK] La cola pone primero lo que espera a una persona, y dice por que.")
