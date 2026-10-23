# -*- coding: utf-8 -*-
"""
Quien controla una conversacion HOY, durante la transicion al modelo nuevo.

UNA sola funcion para todas las guardas (B3.3: /mensajes, /humano/media,
/plantilla y las que vengan). Si cada ruta derivara el control a su manera,
el dia del corte habria que cambiar tres lugares y bastaria olvidar uno.

Por que no alcanza con la columna 'control'
-------------------------------------------
B3.1 la creo con default 'ia' y SIN backfill: una conversacion escalada antes
del corte tiene control = 'ia' aunque este esperando a una persona. Una guarda
que leyera solo la columna bloquearia a los operadores justo en esas
conversaciones, hasta que G8 las reconcilie.

La regla
--------
  relevo_version > 0   la conversacion ya entro al modelo nuevo: manda
                       'control'. Una vez adentro no vuelve a legado.
  relevo_version = 0   legado: la misma regla que hoy decide la pausa al
                       reconstruir una sesion (api.py, _sesion_nueva):
                       humano si escalada_a_humano Y necesita_atencion_humana.

Cuando G8 reconcilie todas las conversaciones de legado, la segunda rama deja
de tener filas y se retira.
"""

from __future__ import annotations

IA = "ia"
HUMANO = "humano"


def control_efectivo(fila) -> str:
    """'ia' o 'humano' para una fila de asistente.conversations (un mapeo con
    relevo_version, control, escalada_a_humano y necesita_atencion_humana)."""
    version = fila.get("relevo_version") or 0
    if version > 0:
        return HUMANO if fila.get("control") == HUMANO else IA
    if fila.get("escalada_a_humano") and fila.get("necesita_atencion_humana"):
        return HUMANO
    return IA
