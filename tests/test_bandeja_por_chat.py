# -*- coding: utf-8 -*-
"""
================================================================================
 LA BANDEJA POR CHAT  --  la regla de agrupar, sin base
================================================================================

    py -3.13 tests/test_bandeja_por_chat.py

POR QUE EXISTE  --  21/10/2026
------------------------------
Reportado: "cuando uno escribe desde el mismo numero de telefono se crea una
nueva conversacion como si fuera otro numero nuevo". La bandeja pasa a
mostrar un CHAT por numero (contrato §4.5, C19; SPEC/objetivos/
bandeja-como-whatsapp.md). Esto prueba la regla pura
(proyeccion.agrupar_por_numero) con filas armadas a mano; lo que hace la ruta
con filas reales lo prueba tests/test_bandeja_por_chat_base.py.

QUE SE AFIRMA, SOBRE EL EFECTO
------------------------------
Que conversacion representa al chat, en que banda cae, que ninguna abierta
queda escondida, y que no se mezclan canales, simulacion ni numeros vacios.
Cada regla tiene un caso donde la alternativa equivocada daria otro
resultado: un representante elegido por 'actualizado_en' cae en una fila
distinta, no en la misma.
================================================================================
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.relevo import proyeccion                              # noqa: E402

fallos: list[str] = []
AHORA = datetime(2026, 10, 21, 15, 0, tzinfo=timezone.utc)


def comprobar(etiqueta: str, condicion: bool, detalle: str = "") -> None:
    print(f"  [{'ok' if condicion else 'FALLA'}]    {etiqueta}" + ("" if condicion else f"  -- {detalle}"))
    if not condicion:
        fallos.append(etiqueta)


def fila(id_, *, numero="573000000001", canal="whatsapp", estado="abierta", banda=None,
         desde=None, actualizado=0, ultimo=None, operativa=True, **extra):
    """Una fila de conversacion ya proyectada, con lo minimo que la regla mira."""
    return {**extra, "id": id_, "canal": canal, "usuario_externo": numero, "estado": estado,
            "banda": banda, "esperando_desde": desde,
            "necesita_accion_de": "humano" if banda else ("nadie" if estado != "abierta" else "ia"),
            "banda_nombre": f"b{banda}" if banda else None,
            "motivo_cola": f"motivo de {id_}",
            "actualizado_en": AHORA - timedelta(minutes=actualizado),
            "ultimo_mensaje": f"msg {id_}" if ultimo is not None else None,
            "ultimo_rol": "user" if ultimo is not None else None,
            "ultimo_mensaje_en": AHORA - timedelta(minutes=ultimo) if ultimo is not None else None,
            "canal_operativo": operativa}


def nacimientos(**dias_atras):
    return {k: AHORA - timedelta(days=v) for k, v in dias_atras.items()}


def agrupar(filas, creado):
    salida = proyeccion.agrupar_por_numero(filas, creado)
    salida.sort(key=proyeccion.orden_de_cola)
    return salida


print("\n== 1. Un numero con dos cerradas y dos abiertas: un solo chat")
filas = [
    fila("t17", estado="cerrada", actualizado=5, ultimo=900),          # la cerro una persona
    fila("t18", estado="cerrada", actualizado=1, ultimo=700),          # T18: actualizado_en RECIENTE
    fila("vieja", banda=2, desde=AHORA - timedelta(hours=5), actualizado=300, ultimo=400,
         escalada_a_humano=True, motivo_escalamiento="frustracion_detectada",
         escalada_en=AHORA - timedelta(hours=5), nombre_cliente="Cliente Viejo"),
    fila("nueva", banda=None, actualizado=600, ultimo=3,                # la atiende la IA
         escalada_a_humano=False, motivo_escalamiento=None, escalada_en=None),
]
creado = nacimientos(t17=10, t18=6, vieja=3, nueva=1)
chats = agrupar(filas, creado)
comprobar("las cuatro conversaciones quedan en UNA fila", len(chats) == 1, str(len(chats)))
c = chats[0]
comprobar("representa la abierta mas reciente por creado_en ('nueva')", c["id"] == "nueva", c["id"])
comprobar("la banda es la de la abierta MAS URGENTE (la escalada vieja, banda 2)",
          c["banda"] == 2 and c["urgente_id"] == "vieja", f"{c['banda']} {c.get('urgente_id')}")
comprobar("y la espera es la de esa escalada", c["esperando_desde"] == AHORA - timedelta(hours=5))
comprobar("ninguna abierta queda escondida: la que no es la urgente viaja en 'abiertas'",
          [a["id"] for a in c["abiertas"]] == ["nueva"], str([a["id"] for a in c["abiertas"]]))
# Auditor independiente, 21/10/2026: con solo la banda copiada, la fila decia
# "Por atender" y a la vez escalada=False, sin motivo y con la espera de la IA.
comprobar("la fila describe ENTERA a la urgente: escalada, motivo y desde cuando",
          c["escalada_a_humano"] is True and c["motivo_escalamiento"] == "frustracion_detectada"
          and c["escalada_en"] == AHORA - timedelta(hours=5),
          f"{c.get('escalada_a_humano')} {c.get('motivo_escalamiento')} {c.get('escalada_en')}")
comprobar("se busca por el nombre que dio antes, sin pintarlo de otra conversacion",
          "Cliente Viejo" in c["buscable"] and "frustracion_detectada" in c["buscable"],
          str(c.get("buscable")))
comprobar("'ids' trae las cuatro, de la mas vieja a la mas nueva",
          c["ids"] == ["t17", "t18", "vieja", "nueva"], str(c["ids"]))
comprobar("'tramos' cuenta las cuatro", c["tramos"] == 4)
comprobar("el ultimo mensaje es el mas reciente de TODO el chat", c["ultimo_mensaje"] == "msg nueva")

print("\n== 1b. La escalada vieja ya la tomo alguien: el chat no queda 'Por atender'")
# Copiar campo por campo mezclaba la escalada de una con el 'tomada_por' de la
# otra: un chat que ya tiene quien lo atienda se pintaba sin dueno.
filas = [fila("tomada", banda=3, desde=AHORA - timedelta(hours=2), escalada_a_humano=True,
              tomada_por="Ana", asignada_a_usuario_id="u-ana"),
         fila("ia2", escalada_a_humano=False, tomada_por=None, asignada_a_usuario_id=None)]
c = agrupar(filas, nacimientos(tomada=2, ia2=1))[0]
comprobar("la fila lleva la escalada Y quien la tomo, de la misma conversacion",
          c["urgente_id"] == "tomada" and c["escalada_a_humano"] is True
          and c["tomada_por"] == "Ana" and c["asignada_a_usuario_id"] == "u-ana",
          f"{c.get('urgente_id')} {c.get('tomada_por')} {c.get('asignada_a_usuario_id')}")
comprobar("y el enlace sigue yendo a la actual (D2)", c["id"] == "ia2", c["id"])

print("\n== 2. El representante NO se elige por actualizado_en")
filas = [fila("a", actualizado=1), fila("b", actualizado=500)]   # 'a' tocada hace 1 min
creado = nacimientos(a=5, b=1)                                     # pero 'b' nacio despues
c = agrupar(filas, creado)[0]
comprobar("con dos abiertas, gana la que NACIO despues aunque la otra se haya movido ultima",
          c["id"] == "b", c["id"])

print("\n== 3. Sin ninguna abierta: la ultima por creado_en, fuera de la cola")
filas = [fila("x", estado="cerrada", actualizado=1), fila("y", estado="cerrada", actualizado=90)]
c = agrupar(filas, nacimientos(x=9, y=2))[0]
comprobar("representa la ultima en nacer", c["id"] == "y", c["id"])
comprobar("y no compite en la cola", c["banda"] is None and c["abiertas"] == [])

print("\n== 4. No se mezcla lo que no es el mismo chat")
filas = [fila("w1", canal="whatsapp"), fila("w2", canal="telegram")]
comprobar("el mismo numero en dos canales son dos chats",
          len(agrupar(filas, nacimientos(w1=2, w2=1))) == 2)
filas = [fila("n1", numero="573000000001"), fila("n2", numero="573000000002")]
comprobar("dos numeros son dos chats", len(agrupar(filas, nacimientos(n1=2, n2=1))) == 2)
filas = [fila("s1", canal="whatsapp-simulado", operativa=False),
         fila("s2", canal="whatsapp-simulado", operativa=False)]
comprobar("la simulacion no agrupa (los numeros de bateria se reutilizan)",
          len(agrupar(filas, nacimientos(s1=2, s2=1))) == 2)
filas = [fila("v1", numero=""), fila("v2", numero=None)]
comprobar("un numero vacio no es un chat: no se agrupa con nada",
          len(agrupar(filas, nacimientos(v1=2, v2=1))) == 2)
suelta = agrupar([fila("solo")], nacimientos(solo=1))[0]
comprobar("una fila sola tiene la misma forma (ids, tramos, abiertas)",
          suelta["ids"] == ["solo"] and suelta["tramos"] == 1 and suelta["abiertas"] == [])

print("\n== 5. El orden de la cola usa la banda del chat")
filas = [fila("ia", numero="573000000009", actualizado=1, ultimo=1),
         fila("esc", numero="573000000008", banda=2, desde=AHORA - timedelta(minutes=10))]
orden = [c["id"] for c in agrupar(filas, nacimientos(ia=1, esc=2))]
comprobar("el chat con una escalada va antes que el que atiende la IA", orden == ["esc", "ia"], str(orden))

print()
if fallos:
    print(f"[FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    raise SystemExit(1)
print("[OK] La bandeja agrupa por chat sin esconder ninguna conversacion abierta.")
