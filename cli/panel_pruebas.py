# -*- coding: utf-8 -*-
"""
================================================================================
 PANEL DE PRUEBAS  -  ver el flujo del agente paso a paso, no solo la respuesta
================================================================================

Herramienta de DESARROLLO, no el canal de produccion. nucleo/canales/web
todavia no existe (ver ARQUITECTURA.md) -- esto es para poder elegir que
probar y ver la conversacion completa (verificacion, llamada a herramienta,
dato ya filtrado, redaccion final) sin tener que leerlo en texto plano de la
consola.

Hoy solo cubre el rol 'cliente_final' porque es el unico que ya corre sobre
el motor generico (nucleo/modelo/motor.py). Los demas roles (soporte,
tecnica, facturacion, administracion) todavia viven en soporte_wisphub.py,
que no esta conectado a esto.

Uso
---
    py -3.13 -m streamlit run cli/panel_pruebas.py
================================================================================
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from dotenv import load_dotenv
load_dotenv(override=True)

from nucleo.config import cargar_config
from nucleo.modelo import motor
from nucleo.seguridad.verificacion import Sesion, verificar_por_telefono

RUTA_CONFIG = "tenants/rapilink.config.yaml"
USAR_WISPHUB_REAL = os.environ.get("WISPHUB_MODO_REAL", "false").strip().lower() == "true"
WISPHUB_BASE_URL = os.environ.get("WISPHUB_BASE_URL", "https://api.wisphub.io").rstrip("/")

# Directorio de prueba en modo SIMULADO unicamente.
DIRECTORIO_SIMULADO = {
    "3001234567": [{"id_cliente": "4521"}],
}


def buscar_clientes_por_telefono(telefono: str) -> list[dict]:
    if not USAR_WISPHUB_REAL:
        return DIRECTORIO_SIMULADO.get(telefono, [])

    # 'telefono__contains' verificado (metodo del valor imposible, agosto
    # 2026 -- ver .claude/skills/wisphub-api/SKILL.md). 'telefono' exacto NO
    # sirve: el campo guarda varios numeros separados por coma.
    r = requests.get(
        WISPHUB_BASE_URL + "/api/clientes/",
        headers={"Authorization": f"Api-Key {os.environ.get('WISPHUB_API_KEY', '')}"},
        params={"telefono__contains": telefono, "limit": 5}, timeout=15)
    r.raise_for_status()
    resultados = r.json().get("results", [])
    # Defensa: confirmar que el numero de verdad aparece en el campo, en vez
    # de asumir que el filtro hizo su trabajo.
    return [{"id_cliente": str(c["id_servicio"])} for c in resultados
            if telefono in (c.get("telefono") or "")]


def _ultimo_turno(historial: list[dict]) -> list[dict]:
    """Los mensajes desde el ULTIMO 'user' en adelante -- lo que paso en la
    interaccion mas reciente, para saber que camino iluminar."""
    idx = None
    for i, m in enumerate(historial):
        if m.get("role") == "user":
            idx = i
    return historial[idx:] if idx is not None else []


def _construir_diagrama(rol_cfg, historial: list[dict]) -> str:
    """
    Arma el mapa de herramientas del rol como grafo DOT, con el camino del
    ULTIMO turno resaltado. Las herramientas se leen de 'Rol.puede_consultar'
    -- no hay nada hardcodeado por nombre de herramienta, si se agrega una
    nueva al YAML aparece sola en el mapa.
    """
    ultimo = _ultimo_turno(historial)
    hubo_turno = bool(ultimo)
    bloqueado = any(
        m.get("role") == "tool"
        and json.loads(m["content"]).get("error") == "IDENTIDAD_NO_VERIFICADA"
        for m in ultimo)
    llamadas = {
        m["name"] for m in ultimo
        if m.get("role") == "tool"
        and json.loads(m["content"]).get("error") != "IDENTIDAD_NO_VERIFICADA"}

    ACTIVO = 'color="#2ecc71" penwidth=3'
    INACTIVO = 'color="#666666" penwidth=1'

    def arista(origen: str, destino: str, activo: bool) -> str:
        return f'  "{origen}" -> "{destino}" [{ACTIVO if activo else INACTIVO}];'

    lineas = [
        "digraph flujo {",
        "  rankdir=LR;",
        '  bgcolor="transparent";',
        '  node [shape=box, style="rounded,filled", fontname="Helvetica", '
        'fontcolor="white", color="#666666"];',
        '  "agente" [label="🤖 cliente_final", fillcolor="#2c2c2c"];',
        '  "verificacion" [label="🔒 verificar\\nidentidad", fillcolor="#2c2c2c"];',
        '  "bloqueado" [label="⛔ bloqueado\\n(sin datos)", fillcolor="#5c1a1a"];',
        '  "filtro" [label="🧹 filtro de\\ncampos", fillcolor="#2c2c2c"];',
        '  "respuesta" [label="💬 respuesta", fillcolor="#1a5c2e"];',
    ]
    for h in rol_cfg.puede_consultar:
        lineas.append(f'  "{h}" [label="🔧 {h}", fillcolor="#1a3a5c"];')

    lineas.append(arista("agente", "verificacion", hubo_turno))
    lineas.append(arista("verificacion", "bloqueado", bloqueado))
    for h in rol_cfg.puede_consultar:
        activa = h in llamadas
        lineas.append(arista("verificacion", h, activa))
        lineas.append(arista(h, "filtro", activa))
    lineas.append(arista("filtro", "respuesta", bool(llamadas)))
    lineas.append("}")
    return "\n".join(lineas)


st.set_page_config(page_title="Panel de pruebas - cliente_final", page_icon="🛠️")

config = cargar_config(RUTA_CONFIG)

if USAR_WISPHUB_REAL:
    st.warning("⚠️ WISPHUB_MODO_REAL=true -- esto llama a la API real de "
              "WispHub, no a datos simulados.")
else:
    st.info("Modo simulado: no toca la API real de WispHub.")

st.title("🛠️ Panel de pruebas -- rol cliente_final")
st.caption(f"{config.identidad.nombre_comercial or config.identidad.nombre_legal} "
          f"-- simula un remitente de WhatsApp")

with st.sidebar:
    st.header("Sesion")
    telefono = st.text_input("Numero que simula escribir", value="3001234567")
    st.caption("Registrado en el directorio de prueba: 3001234567 -> "
              "id_cliente 4521. Cualquier otro numero queda sin verificar.")
    if st.button("Reiniciar conversacion", use_container_width=True):
        st.session_state.clear()
        st.rerun()

if "sesion" not in st.session_state or st.session_state.get("telefono_actual") != telefono:
    _sesion = Sesion(identificador_canal=telefono)
    _sesion = verificar_por_telefono(_sesion, config.autenticacion,
                                     buscar_clientes_por_telefono, telefono)
    st.session_state["sesion"] = _sesion
    st.session_state["telefono_actual"] = telefono
    st.session_state["historial"] = []

sesion = st.session_state["sesion"]
historial = st.session_state["historial"]

with st.sidebar:
    if sesion.verificado:
        st.success(f"✅ Verificado -- id_cliente={sesion.id_cliente}")
    elif sesion.candidatos:
        st.warning(f"Numero ambiguo entre: {sesion.candidatos}")
    else:
        st.error("🔒 No verificado (numero no encontrado)")

st.subheader("🗺️ Mapa de herramientas del agente")
rol_cfg = config.roles["cliente_final"]
st.graphviz_chart(_construir_diagrama(rol_cfg, historial), use_container_width=True)
st.caption("🟢 verde = camino que siguio el ULTIMO mensaje. Gris = conexiones "
          "disponibles pero no usadas en este turno.")

st.subheader("Detalle paso a paso")

if not historial:
    st.caption("Escribi un mensaje abajo para empezar. Probá primero SIN "
              "cambiar el numero de la barra lateral (queda sin verificar "
              "salvo que uses 3001234567) para ver el bloqueo de identidad.")

for m in historial:
    rol = m.get("role")

    if rol == "system":
        with st.expander("🧾 system prompt (armado por nucleo/recuperacion/prompt.py)"):
            st.text(m["content"])

    elif rol == "user":
        with st.chat_message("user"):
            st.write(m["content"])

    elif rol == "assistant" and m.get("tool_calls"):
        with st.chat_message("assistant"):
            for tc in m["tool_calls"]:
                fn = tc["function"]
                st.markdown(f"🔧 decide llamar a `{fn['name']}({fn['arguments']})`")

    elif rol == "tool":
        with st.chat_message("assistant"):
            contenido = json.loads(m["content"])
            if contenido.get("error") == "IDENTIDAD_NO_VERIFICADA":
                st.error("🔒 Bloqueado por el motor: identidad no verificada. "
                        "La herramienta NUNCA se ejecuto.")
            elif isinstance(contenido, dict) and "error" in contenido:
                st.warning(f"⚠️ {contenido['error']}")
            else:
                st.markdown(f"✅ `{m['name']}` devolvio (ya filtrado por "
                            f"`nucleo/seguridad/listas_blancas.py`):")
                st.json(contenido)

    elif rol == "assistant":
        with st.chat_message("assistant"):
            st.write(m["content"])

mensaje = st.chat_input("Escribi como si fueras el cliente...")
if mensaje:
    with st.spinner("El agente esta respondiendo..."):
        motor.responder(config, "cliente_final", mensaje, historial, sesion)
    st.rerun()
