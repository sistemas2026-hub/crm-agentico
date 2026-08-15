# -*- coding: utf-8 -*-
"""
================================================================================
 CORRER LOS CASOS DORADOS CONTRA EL MOTOR REAL
================================================================================

Por que existe
--------------
Hasta ahora, "¿este cambio mejoro o empeoro al agente?" se contestaba
abriendo el simulador y leyendo una conversacion. Eso no escala y no detecta
regresiones: el 14/08/2026 tres bugs estuvieron rotos horas -- una herramienta
que devolvia un ERROR donde debia haber un dato, un veredicto que no se
calculaba, y una precondicion imposible de cumplir. Ninguno se veia leyendo la
respuesta; los tres se ven en la traza de herramientas.

Por eso este corredor afirma sobre la TRAZA (que herramientas se llamaron, a
que area se derivo, si hubo errores) y no sobre la redaccion. Un test que
exija una frase exacta falla por motivos que no importan, y un test que falla
seguido deja de leerse.

Que NO cubre
------------
La calidad de la redaccion, el tono, y si la respuesta le sirve a la persona.
Eso se sigue evaluando a mano, marcando buenos ejemplos en /conversaciones y
en el simulador (ver /manual). Este corredor dice que el agente hizo lo
correcto, no que lo dijo bien.

Llama a las APIs de verdad y al modelo: tarda (~20-60s por caso) y cuesta.
Es la prueba de antes de dar por bueno un cambio, no algo para correr en cada
guardado.

Uso
---
    py -3.13 cli/evaluar.py rapilink
    py -3.13 cli/evaluar.py rapilink --caso "reinicio"    # solo los que matcheen
    py -3.13 cli/evaluar.py rapilink --json informe.json
================================================================================
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import yaml
from dotenv import load_dotenv
load_dotenv(RAIZ / ".env", override=True)

from nucleo.config import cargar_config                      # noqa: E402
from nucleo.modelo import motor                              # noqa: E402
from nucleo.seguridad.verificacion import Sesion             # noqa: E402


def _sin_tildes_minusc(texto: str) -> str:
    """Para comparar 'responde_sin' sin que una tilde o una mayuscula deje
    pasar lo que se queria prohibir ('Desenchufá' vs 'desenchuf')."""
    import unicodedata
    t = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def correr_caso(config, caso: dict, defaults: dict, prohibido: list[str]) -> dict:
    """Un caso: arma la sesion, manda los mensajes y junta la traza."""
    datos_sesion = {**defaults, **(caso.get("sesion") or {})}
    # 'Sesion' no acepta claves que no conoce -- se filtran para que el YAML
    # pueda traer campos de documentacion sin romper el corredor.
    campos = set(Sesion.__dataclass_fields__)
    sesion = Sesion(**{k: v for k, v in datos_sesion.items() if k in campos})

    historial: list[dict] = []
    usadas: list[str] = []
    errores: list[str] = []
    respuesta = ""

    for mensaje in caso["mensajes"]:
        respuesta, registro = motor.responder(
            config, caso["rol"], mensaje, historial, sesion)
        for r in registro:
            usadas.append(r["herramienta"])
            if r.get("codigo_error"):
                errores.append(f"{r['herramienta']}: {r['codigo_error']}")

    fallas: list[str] = []
    espera = caso.get("espera") or {}
    rol_cfg = config.roles.get(caso["rol"])
    respuesta_norm = _sin_tildes_minusc(respuesta)

    esperado = espera.get("deriva_a")
    if esperado and sesion.rol_siguiente != esperado:
        fallas.append(f"deriva_a: esperaba '{esperado}', "
                     f"quedo en '{sesion.rol_siguiente}'")

    for herr in espera.get("usa") or []:
        if herr not in usadas:
            fallas.append(f"usa: nunca llamo '{herr}'")

    # OJO con 'no_usa': la traza es del TURNO COMPLETO, y si hubo derivacion
    # incluye lo que llamo el especialista despues del handoff. Sirve para
    # "esta herramienta no se ejecuto en todo el turno" (ej. no se reinicio
    # nada), NO para "este rol no la tiene" -- para eso esta 'catalogo_sin',
    # que mira la configuracion y no la corrida. Confundirlos hace que el
    # caso falle por lo que hizo OTRO agente, que es como se escribio mal la
    # primera version de estos casos.
    for herr in espera.get("no_usa") or []:
        if herr in usadas:
            fallas.append(f"no_usa: llamo '{herr}' y no debia")

    # Afirmacion sobre la CONFIGURACION, no sobre la corrida: que este rol no
    # tenga tal herramienta en su catalogo. No cuesta ninguna llamada y es la
    # forma correcta de fijar una decision de diseño (el router enruta, no
    # diagnostica) para que no se deshaga sin que nadie lo note.
    if rol_cfg is not None:
        for herr in espera.get("catalogo_sin") or []:
            if herr in rol_cfg.puede_consultar:
                fallas.append(f"catalogo_sin: el rol '{caso['rol']}' TIENE "
                             f"'{herr}' en su catalogo y no deberia")
        for herr in espera.get("catalogo_con") or []:
            if herr not in rol_cfg.puede_consultar:
                fallas.append(f"catalogo_con: al rol '{caso['rol']}' le falta "
                             f"'{herr}' en su catalogo")

    for herr in espera.get("usa_una_sola_vez") or []:
        veces = usadas.count(herr)
        if veces == 0:
            fallas.append(f"usa_una_sola_vez: nunca llamo '{herr}'")
        elif veces > 1:
            fallas.append(f"usa_una_sola_vez: llamo '{herr}' {veces} veces")

    if espera.get("sin_errores") and errores:
        fallas.append(f"sin_errores: {'; '.join(errores)[:150]}")

    for prohibida in espera.get("responde_sin") or []:
        if _sin_tildes_minusc(prohibida) in respuesta_norm:
            fallas.append(f"responde_sin: la respuesta dice '{prohibida}'")

    # 'responde_con' se usa con cuidado y solo para DATOS, nunca para
    # redaccion: exigir que aparezca el nombre del cliente es legitimo (o lo
    # sabe o no lo sabe); exigir una frase de cortesia seria un test que
    # falla porque el modelo dijo lo mismo con otras palabras.
    for requerida in espera.get("responde_con") or []:
        if _sin_tildes_minusc(requerida) not in respuesta_norm:
            fallas.append(f"responde_con: la respuesta NO dice '{requerida}'")

    # Las prohibiciones globales solo aplican a lo que ve un CLIENTE: un rol
    # interno SI puede ver un dBm o un serial, es su trabajo.
    if rol_cfg is not None and rol_cfg.orientado_a == "cliente_final":
        for prohibida in prohibido:
            if _sin_tildes_minusc(prohibida) in respuesta_norm:
                fallas.append(f"PII/jerga: la respuesta dice '{prohibida}'")

    return {
        "nombre": caso["nombre"],
        "ok": not fallas,
        "fallas": fallas,
        "herramientas": usadas,
        "deriva_a": sesion.rol_siguiente,
        "respuesta": respuesta,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tenant")
    ap.add_argument("--caso", help="Corre solo los casos cuyo nombre contenga esto")
    ap.add_argument("--json", help="Guarda el informe completo en este archivo")
    args = ap.parse_args()

    ruta_casos = RAIZ / "evaluacion" / f"{args.tenant}.casos.yaml"
    if not ruta_casos.exists():
        raise SystemExit(f"No hay casos para '{args.tenant}': falta {ruta_casos}")

    doc = yaml.safe_load(ruta_casos.read_text(encoding="utf-8")) or {}
    casos = doc.get("casos") or []
    if args.caso:
        casos = [c for c in casos if args.caso.lower() in c["nombre"].lower()]
    if not casos:
        raise SystemExit("Ningun caso para correr.")

    config = cargar_config(RAIZ / "tenants" / f"{args.tenant}.config.yaml")

    print("=" * 72)
    print(f"  Casos dorados de {args.tenant} -- {len(casos)} caso(s)")
    print(f"  Contra el motor REAL: llama a las APIs y al modelo, tarda.")
    print("=" * 72, flush=True)

    resultados = []
    t_total = time.monotonic()
    for i, caso in enumerate(casos, 1):
        t0 = time.monotonic()
        try:
            r = correr_caso(config, caso, doc.get("sesion_por_defecto") or {},
                           doc.get("prohibido_a_cliente_final") or [])
        except Exception as e:
            # Un caso que revienta es una falla del caso, no del corredor: se
            # anota y se sigue, para no perder los 40 que vienen despues.
            r = {"nombre": caso["nombre"], "ok": False,
                 "fallas": [f"reviento: {type(e).__name__}: {e}"],
                 "herramientas": [], "deriva_a": None, "respuesta": ""}
        r["segundos"] = round(time.monotonic() - t0, 1)
        resultados.append(r)

        marca = "[ok]  " if r["ok"] else "[FALLA]"
        print(f"{marca} {i}/{len(casos)} {r['nombre']}  ({r['segundos']}s)", flush=True)
        for f in r["fallas"]:
            print(f"         -> {f}", flush=True)

    ok = sum(1 for r in resultados if r["ok"])
    pct = 100.0 * ok / len(resultados)
    minimo = config.evaluacion.minimo_acierto_pct

    print()
    print("=" * 72)
    print(f"  {ok}/{len(resultados)} casos OK ({pct:.0f}%)  --  minimo exigido: {minimo:.0f}%")
    print(f"  {round(time.monotonic() - t_total)}s en total")
    if len(resultados) < config.evaluacion.minimo_casos:
        print(f"  AVISO: el set tiene {len(resultados)} casos y la config pide al "
              f"menos {config.evaluacion.minimo_casos} para dar por buena una "
              f"corrida. Sirve igual para detectar regresiones, pero todavia "
              f"no es un criterio de aceptacion.")
    print("=" * 72)

    if args.json:
        Path(args.json).write_text(
            json.dumps(resultados, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Informe: {args.json}")

    sys.exit(0 if pct >= minimo else 1)


if __name__ == "__main__":
    main()
