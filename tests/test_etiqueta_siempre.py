# -*- coding: utf-8 -*-
"""
================================================================================
 LA CLASIFICACION SE GUARDA AUNQUE LA CONVERSACION NO ESCALE
================================================================================

Por que existe
--------------
El evaluador devuelve 'etiqueta' en CADA turno -- es campo obligatorio de su
esquema, no opcional. Pero hasta el 15/09/2026 solo se persistia dentro de
marcar_escalada(), o sea unicamente cuando la conversacion pasaba a un humano.
Una que el asistente resolvia solo calculaba su etiqueta y la tiraba.

Medido sobre produccion ese dia, filtrando nuestro propio trafico de prueba:

    178 conversaciones reales
     62 sin etiquetar  (34.8%)
     52 en 'otro'      (29.2%)
    ---
    64% del trafico real sin una clasificacion util

Y 'caso_manual', que sale de la MISMA llamada al evaluador, si estaba en casi
todas -- porque para ese campo el agujero ya se habia encontrado y tapado
(ver el comentario de marcar_caso en db.py, y
supabase/202608180923_caso_conversacion.sql). Era el mismo bug, un campo mas
tarde.

Importa para algo concreto: un supervisor de operaciones no puede priorizar
lo que no sabe nombrar. Con dos de cada tres conversaciones sin nombre, no
hay tablero que sirva.

Lo que se fija
--------------
1. UN TURNO QUE NO ESCALA TAMBIEN GUARDA LA ETIQUETA. Es la regresion exacta:
   antes solo se guardaba por el camino de escalada.

2. SE GUARDA AUNQUE NO HAYA 'caso_manual'. Son dos campos distintos del mismo
   veredicto y uno puede venir sin el otro; atar la etiqueta a que exista un
   caso reintroduciria el agujero a medias.

3. UN TURNO MUDO NO BORRA LO QUE YA HABIA. Si el evaluador no clasifico nada,
   no se llama a la persistencia -- perder una clasificacion buena por un
   turno sin veredicto seria peor que no tenerla.

4. NO SE AFIRMA QUE EXISTA LA COLUMNA NI QUE EL SQL DIGA 'coalesce'. Se
   afirma el EFECTO: con que valores se llama a la persistencia en cada caso.
   Una prueba que mirara el SQL sobreviviria a que api.py dejara de pasar la
   etiqueta.

Corre SIN BASE DE DATOS y sin red: se sustituye todo lo que toca Postgres.

Uso
---
    py -3.13 tests/test_etiqueta_siempre.py
================================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config                              # noqa: E402
from nucleo.canales import api                                       # noqa: E402
from nucleo.persistencia import db as p                              # noqa: E402
from nucleo.seguimiento import escalamiento as esc                   # noqa: E402
from nucleo.modelo import motor as mot                               # noqa: E402

CONFIG = cargar_config(RAIZ / "tenants" / "rapilink.config.yaml")

fallos: list[str] = []


def afirmar(condicion: bool, que: str) -> None:
    if not condicion:
        fallos.append(que)


def comprobar(seccion: str) -> None:
    print(f"\n--- {seccion} ---")


def un_turno(veredicto: dict) -> list[tuple]:
    """Corre un turno con ese veredicto del evaluador y devuelve las llamadas
    a marcar_caso que hizo (tenant, conversation_id, caso, etiqueta)."""
    llamadas: list[tuple] = []

    postizos = {
        p: {"estado_de_conversacion_abierta": lambda *a, **k: None,
            "atendida_por_humano": lambda *a, **k: False,
            "registrar_mensaje": lambda *a, **k: ("conv-1", "msg-1"),
            "conversacion_vencida": lambda *a, **k: False,
            "identificar_cliente": lambda *a, **k: None,
            "resumen_anterior": lambda *a, **k: None,
            "historial_para_el_modelo": lambda *a, **k: [],
            "registrar_turno": lambda *a, **k: None,
            "actualizar_contenido_mensaje": lambda *a, **k: None,
            "caso_de_conversacion": lambda *a, **k: None,
            "ticket_operativo_de": lambda *a, **k: None,
            "cerrar_conversacion": lambda *a, **k: None,
            "guardar_resumen": lambda *a, **k: None,
            "marcar_caso": lambda *a: llamadas.append(a),
            "marcar_escalada": lambda *a, **k: None,
            "completar_medicion": lambda *a, **k: None,
            "guardar_estado_routing": lambda *a, **k: None,
            "registrar_marca_tv_desconocida": lambda *a, **k: None},
        esc: {"evaluar": lambda *a, **k: dict(veredicto),
              "escalar": lambda *a, **k: True,
              "caso_sigue_abierto": lambda *a, **k: False},
        mot: {"responder": lambda *a, **k: ("respuesta del bot", [], [])},
        api: {"_resolver_verificacion_pendiente": lambda *a, **k: None,
              "_hay_verificacion_pendiente": lambda *a, **k: False},
        api.consumo: {"estado_del_gasto": lambda *a, **k:
                      {"accion": "seguir", "gastado": 0, "tope": 0,
                       "porcentaje": 0.0}},
    }
    orig = {(m, n): getattr(m, n) for m, d in postizos.items() for n in d
            if hasattr(m, n)}
    for m, d in postizos.items():
        for n, f in d.items():
            if hasattr(m, n):
                setattr(m, n, f)
    api._sesiones.clear()
    try:
        api.atender_turno(CONFIG, "rapilink", "cliente_final",
                          "573000000000", "hola, no me anda el wifi", "api")
    finally:
        for (m, n), f in orig.items():
            setattr(m, n, f)
    return llamadas


def etiqueta_guardada(llamadas: list[tuple]) -> str | None:
    """La etiqueta con la que se llamo a marcar_caso, si se llamo."""
    for a in llamadas:
        if len(a) >= 4:
            return a[3]
    return None if not llamadas else ""


# ---------------------------------------------------------------------------
comprobar("1. un turno que NO escala guarda la etiqueta")

llamadas = un_turno({"escalar": False, "resuelta": False,
                     "etiqueta": "soporte_tecnico", "caso_manual": "cambio_wifi"})
afirmar(bool(llamadas),
        "no se persistio nada: un turno sin escalada vuelve a tirar la "
        "clasificacion, que es exactamente el bug del 15/09/2026")
afirmar(etiqueta_guardada(llamadas) == "soporte_tecnico",
        f"la etiqueta no llego a la persistencia (llego {etiqueta_guardada(llamadas)!r})")
print(f"  marcar_caso recibio: {llamadas[0][2:] if llamadas else '(nada)'}")

# ---------------------------------------------------------------------------
comprobar("2. se guarda aunque no haya caso_manual")

llamadas = un_turno({"escalar": False, "resuelta": False,
                     "etiqueta": "facturacion", "caso_manual": ""})
afirmar(bool(llamadas),
        "sin 'caso_manual' no se guarda nada -- la etiqueta quedaria atada a "
        "que exista un caso, que es el mismo agujero a medias")
afirmar(etiqueta_guardada(llamadas) == "facturacion",
        "la etiqueta sola no se persiste")

# ---------------------------------------------------------------------------
comprobar("3. un turno mudo no toca la persistencia")

llamadas = un_turno({"escalar": False, "resuelta": False,
                     "etiqueta": "", "caso_manual": ""})
afirmar(not llamadas,
        "con el evaluador sin clasificar igual se llama a la persistencia: "
        "un turno mudo podria borrar una clasificacion buena")

# ---------------------------------------------------------------------------
comprobar("4. el camino de escalada sigue funcionando")

llamadas = un_turno({"escalar": True, "resuelta": False, "necesita_humano": True,
                     "etiqueta": "queja", "caso_manual": "reclamo_formal",
                     "motivo": "frustracion_detectada", "resumen": "x"})
afirmar(etiqueta_guardada(llamadas) == "queja",
        "al escalar dejo de guardarse por este camino -- el arreglo no puede "
        "romper el que ya andaba")

# ---------------------------------------------------------------------------
print()
if fallos:
    print(f"[FALLA] {len(fallos)} problema(s):")
    for f in fallos:
        print(f"  - {f}")
    raise SystemExit(1)

print("[OK] La clasificacion se guarda escale o no, y un turno mudo no la borra.")
