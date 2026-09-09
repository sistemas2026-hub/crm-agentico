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

POR QUE HAY UN SUBCONJUNTO DE HUMO
-----------------------------------
Los 56 casos tardan ~23 minutos. Eso los saco de circulacion sin que nadie lo
decidiera: entre el 08 y el 09/09/2026 se hicieron diecinueve arreglos y no se
corrieron enteros ni una vez. Cinco de esos diecinueve eran regresiones que un
caso dorado habria cazado -- los casos existian, pasaban, y nadie los miro.

'--humo' corre los marcados 'humo: true' en el archivo de casos: uno por
camino critico, ninguno que reinicie un equipo. Tarda ~3 minutos, que es lo
que cabe despues de CADA cambio. No reemplaza la corrida completa antes de dar
algo por bueno; reemplaza a no correr nada.

Y DE DONDE SALE LA CONFIG
--------------------------
Por defecto, del YAML del repo -- valida lo que uno acaba de escribir, antes
de aplicarlo, sin exigir Postgres. Pero DESPUES de aplicar config a produccion
ese YAML no prueba nada: otras cuatro de esas diecinueve fallas eran cosas que
el repo declaraba y la base no tenia, y este corredor no podia verlas porque
leia el lado donde el dato SI estaba. Para eso esta '--base'.

Uso
---
    py -3.13 cli/evaluar.py rapilink
    py -3.13 cli/evaluar.py rapilink --humo              # ~3 min, camino critico
    py -3.13 cli/evaluar.py rapilink --humo --base       # despues de aplicar config
    py -3.13 cli/evaluar.py rapilink --caso "reinicio"   # solo los que matcheen
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

# Herramientas que ESCRIBEN en un equipo o en un sistema de terceros. Se
# listan por marcador de efecto y no por nombre exacto, para que una
# herramienta nueva de la misma familia quede cubierta desde el dia uno.
#
# tests/test_casos_de_humo.py importa esta lista de aca: si viviera en los
# dos lados, la copia del test se quedaria vieja justo cuando importa.
ESCRIBEN_EN_SISTEMAS = ("reiniciar", "reinicio", "cambiar_", "actualizar_",
                        "crear_ticket", "registrar_pago", "cerrar_ticket",
                        "cancelar_")

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import yaml
from dotenv import load_dotenv
# override=False, y NO es un detalle: con True, el .env PISABA las variables
# que ya trae el entorno. Dentro de un contenedor eso significa que un .env
# viejo horneado en la imagen manda mas que la configuracion del despliegue
# -- el 24/08/2026 hizo que toda carga de config corriera contra la base
# local aunque el servicio apuntara a la de produccion, en silencio y
# reportando exito. La precedencia correcta es la de siempre: lo que el
# entorno declara explicitamente gana; el archivo solo rellena lo que falta,
# que es justo lo que hace falta al correrlo a mano en una maquina.
load_dotenv(RAIZ / ".env", override=False)

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
    # Un caso puede arrancar con el resumen de una conversacion ANTERIOR ya
    # inyectado, que es lo que hace el motor de verdad cuando alguien vuelve a
    # escribir despues de que la suya se cerrara por inactividad
    # (nucleo/canales/api.py). Sin esto no habia forma de probar lo que pasa
    # en ese arranque -- y ahi es donde el 07/09/2026 el asistente le dijo a
    # un cliente real "estuvimos hablando hace un momento" sobre algo de
    # veintiseis dias antes.
    previo = caso.get("conversacion_anterior")
    if previo:
        from nucleo.seguimiento import resumen as _resumen
        historial.append(_resumen.como_contexto(
            previo["resumen"], previo.get("hace_horas")))

    usadas: list[str] = []
    # Las que de verdad CORRIERON: una que el motor freno (precondicion,
    # limite, reporte ambiguo) figura en 'usadas' porque el modelo la
    # intento, pero no le hizo nada a nadie. La distincion importa para
    # 'no_usa', que afirma que algo no le paso al cliente -- ver mas abajo.
    ejecutadas: list[str] = []
    errores: list[str] = []
    respuesta = ""
    # Sigue el mismo patron que nucleo/canales/api.py::atender_turno(): si un
    # mensaje deriva a otro rol (sesion.rol_siguiente), los mensajes
    # SIGUIENTES de este mismo caso tienen que atenderse con el rol nuevo, no
    # con el declarado en el caso. Bug real encontrado el 19/08/2026: sin
    # esto, un caso de varios mensajes que espera una derivacion a mitad de
    # conversacion le seguia mandando los mensajes de despues al rol viejo,
    # y fallaba con HERRAMIENTA_DESCONOCIDA en vez de probar lo que decia
    # probar.
    rol_actual = caso["rol"]

    # El rol se ARRASTRA entre mensajes, igual que en el canal real
    # (nucleo/canales/api.py: atender_turno lee 'sesion.rol_siguiente', lo usa
    # y lo limpia). Sin esto, un caso de varios mensajes corre SIEMPRE con el
    # rol declarado: el turno 1 deriva al especialista y el turno 2 vuelve a
    # empezar como 'cliente_final', que no tiene las herramientas del area.
    #
    # Lo que producia era peor que un fallo claro: el modelo intentaba una
    # herramienta que veia en el historial, el motor la rechazaba con
    # HERRAMIENTA_DESCONOCIDA -- y como 'usadas' cuenta los intentos, la
    # afirmacion 'usa: [reiniciar_ont]' se daba por cumplida igual. El caso
    # pasaba o fallaba segun como el modelo redactara la respuesta, que es
    # justo lo que estos casos NO deben afirmar. Visto el 22/08/2026
    # persiguiendo una regresion que no existia.
    rol_actual = caso["rol"]
    derivado_a = None
    for mensaje in caso["mensajes"]:
        if getattr(sesion, "rol_siguiente", None):
            derivado_a = sesion.rol_siguiente
            rol_actual = derivado_a
            sesion.rol_siguiente = None
        respuesta, registro, _medios = motor.responder(
            config, rol_actual, mensaje, historial, sesion)
        # Las dos ramas arreglaron ESTE mismo bug por separado (el arnes no
        # arrastraba el rol derivado) y llegaron a codigo distinto. Se
        # conserva esta forma porque hace las dos cosas: registra a donde se
        # derivo -- que es lo que afirma 'deriva_a' y la otra version no
        # guardaba -- y el cambio de rol se aplica arriba, al empezar el
        # mensaje siguiente, donde ademas se limpia la bandera. Asignar
        # 'rol_actual' aca tambien funcionaba, pero dejaba 'rol_siguiente'
        # puesta y sin 'derivado_a'.
        if getattr(sesion, "rol_siguiente", None):
            derivado_a = sesion.rol_siguiente
        for r in registro:
            usadas.append(r["herramienta"])
            # Un bloqueo del motor no es ninguna de las dos cosas: ni corrio
            # (por eso no entra en 'ejecutadas', como ya decia el comentario
            # de arriba) ni fallo nada (por eso tampoco es un error). Es la
            # proteccion funcionando. Sin esta rama, un caso con
            # 'sin_errores: true' donde el gate de identidad frena una
            # llamada -- exactamente lo que debe pasar -- fallaba acusando un
            # error que no existio. Se lee 'es_bloqueo', que el motor ya
            # calcula en la traza (motor.py::CODIGOS_DE_BLOQUEO), en vez de
            # repetir aca la lista de codigos: son la misma verdad y ya se
            # separaron una vez, el 08/09/2026.
            if r.get("es_bloqueo"):
                continue
            if r.get("codigo_error"):
                errores.append(f"{r['herramienta']}: {r['codigo_error']}")
            else:
                ejecutadas.append(r["herramienta"])

    fallas: list[str] = []
    espera = caso.get("espera") or {}
    rol_cfg = config.roles.get(caso["rol"])
    respuesta_norm = _sin_tildes_minusc(respuesta)

    # Contra 'derivado_a' y no contra 'sesion.rol_siguiente': ahora el rol se
    # consume al arrancar el turno siguiente, asi que al final de un caso de
    # varios mensajes la sesion ya no lo tiene -- pero la derivacion ocurrio.
    esperado = espera.get("deriva_a")
    if esperado and derivado_a != esperado:
        fallas.append(f"deriva_a: esperaba '{esperado}', "
                     f"quedo en '{derivado_a}'")

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
    # Mira 'ejecutadas', no 'usadas': lo que afirma es que la herramienta no
    # LLEGO A CORRER -- que no se reinicio ningun equipo, que no se creo
    # ningun ticket. Si el modelo la intento y una guarda del motor la freno,
    # el caso pasa, porque para el cliente no paso nada. Contarlo como uso
    # hacia fallar justo a los casos que existen para probar una guarda
    # fail-closed: la guarda funcionaba y el caso decia que no.
    for herr in espera.get("no_usa") or []:
        if herr in ejecutadas:
            fallas.append(f"no_usa: ejecuto '{herr}' y no debia")

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
    ap.add_argument("--humo", action="store_true",
                    help="Solo los casos marcados 'humo: true' (~3 min)")
    ap.add_argument("--base", action="store_true",
                    help="Usa la config DESPLEGADA en vez del YAML del repo")
    ap.add_argument("--json", help="Guarda el informe completo en este archivo")
    args = ap.parse_args()

    ruta_casos = RAIZ / "evaluacion" / f"{args.tenant}.casos.yaml"
    if not ruta_casos.exists():
        raise SystemExit(f"No hay casos para '{args.tenant}': falta {ruta_casos}")

    doc = yaml.safe_load(ruta_casos.read_text(encoding="utf-8")) or {}
    casos = doc.get("casos") or []
    if args.humo:
        casos = [c for c in casos if c.get("humo")]
        if not casos:
            raise SystemExit(
                "Ningun caso marcado 'humo: true'. El subconjunto de humo "
                "existe para poder correr algo despues de CADA cambio: sin "
                "el, la unica opcion son los 56 casos completos y entonces "
                "no se corre ninguno.")
    if args.caso:
        casos = [c for c in casos if args.caso.lower() in c["nombre"].lower()]
    if not casos:
        raise SystemExit("Ningun caso para correr.")

    # De donde sale la config, y por que importa tanto que se pueda elegir.
    #
    # El 09/09/2026, al clasificar diecinueve arreglos de dos dias, cuatro
    # resultaron ser la misma falla: el repo declaraba algo que produccion no
    # tenia (una credencial, una bandera, herramientas enteras). Este corredor
    # no podia verlas -- leia el YAML, donde el dato SI estaba-- y por eso las
    # cuatro las encontro una persona abriendo el simulador.
    #
    # El YAML sigue siendo el default: valida el cambio que uno acaba de
    # escribir ANTES de aplicarlo, y no exige tener Postgres arriba. Pero
    # DESPUES de aplicar config, la unica corrida que prueba algo es --base.
    # Ver tambien cli/diferencias_config.py, que contesta lo mismo en segundos
    # y sin gastar una llamada al modelo.
    if args.base:
        from nucleo.config import fuente
        resultado = fuente.desde_base(args.tenant)
        if resultado is None:
            raise SystemExit(
                f"'{args.tenant}' no esta en asistente.tenant_config.")
        config, version_config = resultado
        origen = f"la base (v{version_config})"
    else:
        config = cargar_config(RAIZ / "tenants" / f"{args.tenant}.config.yaml")
        origen = f"tenants/{args.tenant}.config.yaml (NO es lo desplegado)"

    print("=" * 72)
    print(f"  Casos dorados de {args.tenant} -- {len(casos)} caso(s)"
          + ("  [HUMO]" if args.humo else ""))
    print(f"  Config: {origen}")
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

    # "NO SE PUDO LLEGAR" NO ES "EL CASO FALLA"
    #
    # Las herramientas contra nuestro propio backend apuntan a
    # 'http://backend:8000' -- el nombre de servicio del compose. Es correcto
    # en produccion, donde el motor y el backend comparten la red, e
    # irresoluble desde una maquina de desarrollo.
    #
    # Contarlo como caso fallado deja toda corrida local en rojo permanente, y
    # un chequeo que siempre falla se deja de leer: seria exactamente la
    # enfermedad que el subconjunto de humo vino a curar. Se separa, se dice
    # cuantos son y se dice por que -- sin ocultarlo, que es la otra forma de
    # equivocarse aca.
    def _inalcanzable(r: dict) -> bool:
        f = r.get("fallas") or []
        return bool(f) and all(
            ("ConnectionError" in x or "Max retries exceeded" in x
             or "NameResolutionError" in x) for x in f)

    inalcanzables = [r for r in resultados if not r["ok"] and _inalcanzable(r)]
    corridos = [r for r in resultados if r not in inalcanzables]

    ok = sum(1 for r in resultados if r["ok"])
    pct = 100.0 * ok / len(corridos) if corridos else 0.0
    minimo = config.evaluacion.minimo_acierto_pct

    print()
    print("=" * 72)
    print(f"  {ok}/{len(corridos)} casos OK ({pct:.0f}%)  --  minimo exigido: {minimo:.0f}%")
    print(f"  {round(time.monotonic() - t_total)}s en total")
    if inalcanzables:
        print(f"  {len(inalcanzables)} caso(s) NO se pudieron correr desde aca "
              f"-- el sistema no responde, no es que el caso falle:")
        for r in inalcanzables:
            print(f"    {r['nombre']}")
        print(f"    (las herramientas del backend propio usan el nombre de red "
              f"del compose:")
        print(f"     desde una maquina de desarrollo no resuelve. Corren dentro "
              f"del contenedor.)")

    # ECONOMIA DEL CAMINO -- un caso puede pasar por el camino equivocado.
    #
    # 'ok' dice que la traza cumplio lo que el caso afirmaba. No dice que el
    # agente haya llegado ahi bien. Un caso que exige 'contar_facturas' pasa
    # igual si ademas consulto la documentacion sin necesidad: funcionalmente
    # correcto, arquitectonicamente incorrecto. Y ese camino de mas es el que
    # despues escala -- en latencia, en tokens y en fuentes compitiendo.
    #
    # Se cuentan llamadas por caso y se listan los casos con mas de tres, sin
    # opinar sobre si esta bien: encadenar cuatro herramientas para diagnosticar
    # una falla es correcto, y llamar cuatro para contestar un saldo no. La
    # distincion la hace quien lee, mirando cuales son.
    llamadas = [len(r.get("herramientas") or []) for r in resultados]
    if llamadas:
        total = sum(llamadas)
        print(f"  {total} llamadas a herramienta en {len(resultados)} casos "
              f"({total / len(resultados):.1f} por caso)")
        largos = sorted(((n, r["nombre"], r.get("herramientas") or [])
                         for n, r in zip(llamadas, resultados) if n > 3),
                        reverse=True)[:5]
        for n, nombre, herr in largos:
            print(f"    {n} llamadas  {nombre[:44]}")
            print(f"               {' -> '.join(herr[:6])}")
    # UNA CORRIDA DE HUMO NO PUEDE ESCRIBIR EN NINGUN SISTEMA
    #
    # Se comprueba sobre la traza REAL y no sobre lo que el caso afirma, y esa
    # diferencia no es teorica: el 09/09/2026, en la primera corrida de humo,
    # 'falla de internet va a soporte tecnico' reinicio la ONU de laboratorio
    # de verdad. El caso trae 'sn_onu: ""' justamente para que eso no pase, y
    # el YAML lo documenta ("los casos de enrutamiento no tocan el equipo").
    # Pero el motor REPONE el serial desde 'consultar_mi_servicio' cuando se
    # perdio (nucleo: recuperacion de sesion), asi que la neutralizacion que
    # el caso escribia quedo sin efecto el dia que esa recuperacion entro.
    #
    # Nadie lo noto porque la guarda estatica miraba 'espera.usa' -- lo que el
    # caso DICE que va a pasar-- y ahi 'reiniciar_ont' no figura. Es el mismo
    # error contra el que existe todo este corredor: verificar lo escrito en
    # vez de lo ocurrido.
    if args.humo:
        escrituras = [(r["nombre"], h) for r in resultados
                      for h in (r.get("herramientas") or [])
                      if any(m in h for m in ESCRIBEN_EN_SISTEMAS)]
        if escrituras:
            print()
            print("  [!] UNA CORRIDA DE HUMO ESCRIBIO EN UN SISTEMA REAL:")
            for nombre, herr in escrituras:
                print(f"      {herr}  <-  {nombre}")
            print("      El humo se corre despues de cada cambio: no puede "
                  "reiniciar equipos")
            print("      ni tocar tickets. Sacar 'humo: true' de ese caso, o "
                  "neutralizarlo")
            print("      de verdad (y comprobar en la traza que quedo "
                  "neutralizado).")

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
