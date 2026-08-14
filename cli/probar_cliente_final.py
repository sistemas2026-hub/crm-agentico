# -*- coding: utf-8 -*-
"""
================================================================================
 PRUEBA EN CONSOLA DEL ROL cliente_final
================================================================================

Simula un remitente de WhatsApp ANTES de tocar el webhook real -- misma
disciplina de "empezar chico, en consola, con datos simulados primero" que
ya se uso para Soporte. Valida de punta a punta: verificacion de identidad,
filtro de campos (nunca password_*, ip, mac_cpe...) y redaccion final.

Uso
---
    py -3.13 cli/probar_cliente_final.py
================================================================================
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# La consola de Windows (cp1252) no imprime bien acentos/emojis -- forzar UTF-8.
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv(override=True)

from nucleo.config import cargar_config
from nucleo.modelo import motor
from nucleo.seguridad.verificacion import Sesion

RUTA_CONFIG = "tenants/rapilink.config.yaml"

# Directorio de prueba en modo SIMULADO: telefono (formato de
# Autenticacion.patron_extraccion, 10 digitos empezando en 3) -> candidatos.
_DIRECTORIO_SIMULADO = {
    "3001234567": [{"id_cliente": "4521"}],
}

USAR_WISPHUB_REAL = os.environ.get("WISPHUB_MODO_REAL", "false").strip().lower() == "true"
WISPHUB_BASE_URL = os.environ.get("WISPHUB_BASE_URL", "https://api.wisphub.io").rstrip("/")


def _buscar_clientes_por_telefono(telefono: str) -> list[dict]:
    if not USAR_WISPHUB_REAL:
        return _DIRECTORIO_SIMULADO.get(telefono, [])

    # 'telefono' (exacto) NO sirve: el campo guarda varios numeros separados
    # por coma y el match es contra la cadena completa. 'telefono__contains'
    # SI esta verificado (metodo del valor imposible, agosto 2026 -- ver
    # .claude/skills/wisphub-api/SKILL.md).
    r = requests.get(
        WISPHUB_BASE_URL + "/api/clientes/",
        headers={"Authorization": f"Api-Key {os.environ.get('WISPHUB_API_KEY', '')}"},
        params={"telefono__contains": telefono, "limit": 5}, timeout=15)
    r.raise_for_status()
    resultados = r.json().get("results", [])
    # Defensa: confirmar que el numero de verdad aparece en el campo antes de
    # confiar en el resultado, en vez de asumir que el filtro hizo su trabajo.
    return [{"id_cliente": str(c["id_servicio"])} for c in resultados
            if telefono in (c.get("telefono") or "")]


if __name__ == "__main__":
    config = cargar_config(RUTA_CONFIG)

    print("=" * 72)
    print(f"  Prueba cliente_final -- "
          f"{config.identidad.nombre_comercial or config.identidad.nombre_legal}")
    print(f"  Modo: {'WISPHUB REAL' if USAR_WISPHUB_REAL else 'SIMULADO (sin tocar la API)'}")
    print("=" * 72)

    telefono = input(
        "\nNumero de WhatsApp que simula escribir [3001234567, "
        "no registrado: probar con otro cualquiera]: "
    ).strip() or "3001234567"

    # La sesion arranca SIN verificar, igual que en produccion. Antes esto
    # llamaba a verificar_por_telefono() para resolver la identidad contra el
    # numero: esa funcion se elimino en agosto de 2026 porque nunca tuvo un
    # llamador real en el motor -- describia un diseño que no era el que
    # corria-- y porque Meta dejo de mandar el telefono en muchas entregas
    # (manda un BSUID, que no identifica a nadie contra la base del ISP).
    #
    # La identidad hoy la resuelve el MODELO pidiendo la cedula y confirmando
    # el nombre (motor.py::_ejecutar_verificacion / _ejecutar_confirmacion).
    # Esta prueba ahora ejercita ese camino de verdad, que es el que importa.
    sesion = Sesion(identificador_canal=telefono)
    print("  [sin verificar: el asistente deberia pedirte la cedula antes de "
          "mostrar cualquier dato de la cuenta]")

    historial: list[dict] = []
    print("\nEscribi como si fueras el cliente. 'salir' para terminar.\n")
    while True:
        try:
            mensaje = input("cliente > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if mensaje.lower() in ("salir", "exit", "quit"):
            break
        if not mensaje:
            continue

        respuesta = motor.responder(config, "cliente_final", mensaje, historial, sesion)
        print(f"\nasistente > {respuesta}\n")
