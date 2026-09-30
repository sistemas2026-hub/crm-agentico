# -*- coding: utf-8 -*-
"""
El historial que ve el modelo, armado por UNA sola regla.

POR QUE EXISTE (SPEC/CONTRATO_RELEVO_IA_HUMANO.md, D8, D12, §10)
----------------------------------------------------------------
Habia dos caminos que armaban el historial y no decian lo mismo:

  en vivo       nucleo/canales/api.py agregaba "(Ana) ya quedo" cuando una
                persona respondia.
  reconstruido  tras un reinicio (el autodeploy lo hace varias veces por dia),
                db.historial_para_el_modelo leia 'rol, contenido' y devolvia
                "ya quedo" a secas: la IA tomaba como propio lo que habia
                prometido una persona.

Y el resumen de una conversacion vencida recibia TODAS las filas, notas
internas incluidas, como si fueran del asistente.

Este modulo es la regla unica. Los dos caminos la usan, y para las mismas filas
producen lo mismo (tests/test_historial_unico.py).

QUE NO HACE
-----------
No modifica nada guardado. La firma de una persona se arma EN MEMORIA al
construir el contexto; la fila conserva sus bytes. Tampoco marca cada mensaje
de legado: si hay mensajes del lado del asistente cuya procedencia no se puede
saber, se agrega UN bloque por historial, no un prefijo por mensaje.

LA SEMANTICA DE CADA FILA
-------------------------
  rol        origen           al modelo                          ambiguo
  user       cliente | NULL   user, intacto                      no
  assistant  ia | sistema     assistant, intacto                 no
  assistant  humano           assistant, "(Nombre, del equipo) " no
  humano     NULL (legado)    assistant, "(del equipo) "         no  -- se sabe que fue una
                                                                     persona; falta el nombre
  assistant  NULL (legado)    assistant, intacto                 SI  -- pudo ser la IA o una
                                                                     persona: activa el bloque
  nota       cualquiera       NUNCA

  Y una respuesta de la IA DESCARTADA (estado_entrega = 'descartado', D24) no
  entra nunca: se calculo, no se le envio al cliente, y el modelo no puede
  recordar como dicho algo que el cliente no leyo.
"""

from __future__ import annotations

BLOQUE_LEGADO = (
    "CONTEXTO HISTORICO LEGADO\n"
    "Parte del historial anterior al corte no tiene procedencia registrada.\n"
    "Los mensajes del lado del asistente sin procedencia pueden haber sido\n"
    "escritos por la IA o por una persona del equipo.\n"
    "No atribuyas su autoria con certeza."
)

# Una respuesta de la IA que se calculo y no salio: una persona tomo el control
# mientras el modelo pensaba (D24). Queda en la base para auditoria, fuera del
# contexto del modelo.
DESCARTADO = "descartado"

# Los roles que pueden llegar al modelo. 'nota' queda afuera por definicion:
# es lo que el equipo se escribe entre si.
ROLES_DEL_MODELO = ("user", "assistant", "humano")


def firma_humana(autor_nombre: str | None) -> str:
    """Como se presenta al modelo lo que escribio una persona. Nombre si se
    sabe; si no (el legado 'humano'), solo que fue del equipo."""
    nombre = (autor_nombre or "").strip()
    return f"({nombre}, del equipo) " if nombre else "(del equipo) "


def es_ambigua(rol: str, origen: str | None) -> bool:
    """Una fila del lado del asistente sin procedencia: pudo ser la IA o una
    persona. Solo estas activan el bloque de legado."""
    return rol == "assistant" and origen is None


def entrada(rol: str, origen: str | None, contenido: str | None,
            autor_nombre: str | None = None) -> dict | None:
    """
    La entrada de historial para UNA fila, o None si no va al modelo.

    La usa el camino en vivo cuando algo se agrega a la sesion, y la
    reconstruccion para cada fila leida: por eso coinciden.
    """
    texto = contenido or ""
    if rol == "nota":
        return None
    if rol == "user":
        return {"role": "user", "content": texto}
    if rol == "humano":
        return {"role": "assistant", "content": firma_humana(None) + texto}
    if rol == "assistant":
        if origen == "humano":
            return {"role": "assistant", "content": firma_humana(autor_nombre) + texto}
        return {"role": "assistant", "content": texto}
    return None


def construir(filas) -> list[dict]:
    """
    El historial para el modelo a partir de filas de asistente.messages, en
    orden. Cada fila es un mapeo con 'rol', 'contenido' y, si existen,
    'origen' y 'autor_nombre'.

    Si ALGUNA fila de las que entran es ambigua, antes del historial va el
    bloque de legado, una sola vez. Si no hay ninguna, no va.
    """
    salida: list[dict] = []
    ambiguo = False
    for f in filas:
        if f.get("estado_entrega") == DESCARTADO:
            continue
        rol, origen = f.get("rol"), f.get("origen")
        e = entrada(rol, origen, f.get("contenido"), f.get("autor_nombre"))
        if e is None:
            continue
        ambiguo = ambiguo or es_ambigua(rol, origen)
        salida.append(e)
    if ambiguo:
        salida.insert(0, {"role": "system", "content": BLOQUE_LEGADO})
    return salida
