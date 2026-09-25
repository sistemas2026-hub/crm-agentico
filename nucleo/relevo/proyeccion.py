# -*- coding: utf-8 -*-
"""
Que necesita cada conversacion, y por que aparece donde aparece. B3.5 (D18).

POR QUE EXISTE (SPEC/CONTRATO_RELEVO_IA_HUMANO.md, §4.5, D18)
-------------------------------------------------------------
"Recomendado" se calculaba en la pantalla con un puntaje: dias esperando, mas
30 si el cliente insistio, mas 2 si el motivo era urgente. Dos problemas, y el
segundo es el que duele:

  1. La regla vivia en Svelte. Cada lector que quisiera la misma cola tenia
     que reimplementarla, y nadie podia probarla sin un navegador.
  2. Ordenaba por ANTIGUEDAD. Una escalada nueva sin dueno entraba al fondo,
     detras de decenas de conversaciones viejas que llevaban dias ahi. Es
     exactamente D18: lo urgente enterrado bajo lo viejo.

Esto lo reemplaza por BANDAS explicitas, calculadas sobre la verdad durable.
No hay puntaje: una fila esta en la banda 2 porque nadie la tomo, no porque
sumo 87 puntos. La pantalla muestra el motivo en palabras.

    banda 1  el cliente escribio y espera a una persona
    banda 2  en manos de personas y SIN dueno (la escalada nueva)
    banda 3  hace falta que una persona revise algo (hoy: la evaluacion que
             quedo en NO_DETERMINADO, T19)
    banda 4  trabajo interno pendiente (pendiente_interno_desde)
    banda 5  en curso con dueno, sin nada nuevo del cliente
    banda 6  legado sin reconciliar: se revisa en G8, no se mezcla con la cola

Dentro de una banda ordena 'esperando_desde', el mas viejo primero: sin eso,
una banda con trafico dejaria a alguien esperando para siempre.

LO QUE NO HACE
--------------
- No escribe nada. Es lectura: las transiciones ya dejaron la verdad.
- No adopta legado. Una conversacion en relevo_version 0 se MUESTRA como
  revision; ordenarla o filtrarla no la convierte (G8 es explicito).
- No mira el CRM. Quien tiene la conversacion lo dice Dexter (D28): el dueno
  del ticket puede estar desalineado y no es autoridad.
- No usa 'atendida_manual': es historico ("se resolvio por otro medio"), no
  dice que hace falta ahora.
- No ordena eventos por 'creado_en' (D27): el orden causal es datos.version.
"""

from __future__ import annotations

from datetime import datetime

from nucleo.relevo import control as regla_control

# Quien tiene que mover la conversacion. 'revision' no es una persona de turno:
# es "esto quedo de antes y alguien tiene que decidir que hacer con ello".
HUMANO, IA, INTERNO, NADIE, REVISION = "humano", "ia", "interno", "nadie", "revision"

# (banda, nombre corto). La banda es para ordenar; el nombre, para explicar.
CLIENTE_ESPERA = (1, "cliente_espera")
SIN_ASIGNAR = (2, "sin_asignar")
REVISAR_EVALUACION = (3, "revisar_evaluacion")
INTERNO_PENDIENTE = (4, "interno_pendiente")
EN_CURSO = (5, "en_curso")
LEGADO = (6, "legado")
FUERA_DE_COLA = (None, "fuera_de_cola")


def _hora(valor) -> datetime | None:
    return valor if isinstance(valor, datetime) else None


def _mas_nuevo(a, b) -> bool:
    """a es estrictamente posterior a b. Si b no existe, alcanza con que a si."""
    a, b = _hora(a), _hora(b)
    if a is None:
        return False
    return b is None or a > b


def proyectar(fila) -> dict:
    """
    La proyeccion de UNA conversacion. 'fila' es lo que devuelve
    db.ultima_actividad(): columnas durables mas 'ultima_atencion_humana' y
    'evaluacion_revisada'.

    Devuelve:
      necesita_accion_de  humano | ia | interno | nadie | revision
      banda               1..6, o None si no compite por un lugar en la cola
      banda_nombre        el nombre corto de la banda
      motivo_cola         por que esta ahi, en palabras, para la pantalla
      esperando_desde     desde cuando existe ESA necesidad (None si no se
                          puede saber: no se inventa)
      es_legado           relevo_version = 0
      canal_operativo     lo decide quien llama (canal.REALES), no esta regla
    """
    estado = fila.get("estado")
    gobernada = (fila.get("relevo_version") or 0) > 0
    control = regla_control.control_efectivo(fila)
    asignada = fila.get("asignada_a_nombre") or (None if gobernada else fila.get("tomada_por"))
    revision_pendiente = (fila.get("estado_escalada") == "NO_DETERMINADO"
                          and not fila.get("evaluacion_revisada"))

    def salida(necesita, banda, motivo, desde):
        return {"necesita_accion_de": necesita, "banda": banda[0], "banda_nombre": banda[1],
                "motivo_cola": motivo, "esperando_desde": _hora(desde),
                "es_legado": not gobernada, "asignada_a": asignada}

    if estado != "abierta":
        return salida(NADIE, FUERA_DE_COLA, "Cerrada", None)

    if control == HUMANO:
        # Legado: no entra a la cola moderna ni se adopta por mirarla (G8).
        if not gobernada:
            return salida(REVISION, LEGADO, "Legado: requiere revisión",
                          fila.get("escalada_en") or fila.get("actualizado_en"))
        # El cliente volvio a escribir DESPUES de la ultima vez que le
        # respondio una persona. Es lo unico con alguien esperando del otro
        # lado ahora mismo, asi que va primero aunque sea lo mas nuevo.
        referencia = _hora(fila.get("ultima_atencion_humana")) or _hora(fila.get("escalada_en"))
        if _mas_nuevo(fila.get("ultimo_mensaje_cliente"), referencia):
            return salida(HUMANO, CLIENTE_ESPERA,
                          f"Cliente respondió — espera a {asignada}" if asignada
                          else "Cliente respondió — sin asignar",
                          fila.get("ultimo_mensaje_cliente"))
        if not asignada:
            motivo = ("Intervenida, sin asignar" if fila.get("control_motivo") == "intervencion"
                      else "Escalada, sin asignar")
            return salida(HUMANO, SIN_ASIGNAR, motivo,
                          fila.get("escalada_en") or fila.get("actualizado_en"))
        if revision_pendiente:
            return salida(HUMANO, REVISAR_EVALUACION, "Falta revisar la evaluación",
                          fila.get("escalada_en") or fila.get("actualizado_en"))
        if fila.get("pendiente_interno_desde"):
            return salida(INTERNO, INTERNO_PENDIENTE, "Pendiente interno",
                          fila.get("pendiente_interno_desde"))
        return salida(HUMANO, EN_CURSO, f"En atención: {asignada}",
                      fila.get("asignada_en") or fila.get("escalada_en"))

    # La atiende la IA. No compite en la cola operativa, salvo que haya quedado
    # una evaluacion sin decidir: eso lo resuelve una persona (T19).
    if revision_pendiente:
        return salida(HUMANO, REVISAR_EVALUACION, "Falta revisar la evaluación",
                      fila.get("escalada_en") or fila.get("actualizado_en"))
    return salida(IA, FUERA_DE_COLA, "La atiende la IA", None)


def orden_de_cola(proyeccion) -> tuple:
    """
    La clave de orden de 'Recomendado': primero la banda, y dentro de ella el
    que lleva mas tiempo esperando. Sin 'esperando_desde' se va al final de su
    banda -- no se inventa una antiguedad para poder ordenarlo.
    """
    banda = proyeccion.get("banda")
    desde = proyeccion.get("esperando_desde")
    return (banda if banda is not None else 99,
            0 if desde is not None else 1,
            desde.timestamp() if desde is not None else 0.0)
