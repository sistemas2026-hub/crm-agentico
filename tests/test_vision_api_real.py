# -*- coding: utf-8 -*-
"""
================================================================================
 VISION CONTRA LA API DE VERDAD  --  foto -> analisis -> respuesta al cliente
================================================================================

    DEEPSEEK_API_KEY=... py -3.13 tests/test_vision_api_real.py
    (opcional)           py -3.13 tests/test_vision_api_real.py <ruta de foto>

POR QUE EXISTE
--------------
tests/test_vision_imagen.py sustituye el cliente del modelo, asi que puede
estar entero en verde con una llamada que la API rechaza. Lo que no se mide
no se sabe: en este repo la documentacion de un tercero es una hipotesis.

Esta prueba recorre la cadena COMPLETA con la implementacion real:

    imagen -> comprimir_imagen() -> DeepSeek vision -> texto rotulado
           -> DeepSeek conversacional -> lo que leeria el cliente

El segundo tramo importa tanto como el primero. Que el modelo describa bien
una foto no sirve de nada si despues, al conversar, convierte "la luz LOS
esta roja" en "su equipo esta danado". Eso solo se ve haciendo las dos
llamadas.

NO MANDA LA FOTO DE NADIE
-------------------------
Por omision usa tests/imagen_ont_sintetica.py: una ONT DIBUJADA aca mismo,
sin cara, sin direccion, sin documento y con una etiqueta inventada. Con un
argumento se le puede pasar una foto real de equipo, y ahi quien la pasa es
responsable de que no tenga datos de nadie.

LO QUE NO IMPRIME
-----------------
Ni la clave, ni cabeceras, ni base64, ni la imagen. El texto del analisis y
la respuesta SI se imprimen: son justamente lo que se viene a mirar, y salen
de una foto dibujada.

CUESTA PLATA
------------
Dos llamadas por corrida. No corre en CI y no corre sin la clave: sin ella
termina en verde habiendo comprobado lo unico que puede sin red -- que faltar
el modelo NO rompe el turno.
================================================================================
"""

import os
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.canales import media, vision as vi

MODELO = "deepseek:deepseek-v4-flash"

fallos: list[str] = []


def comprobar(etiqueta: str, condicion: bool, detalle: str = "") -> None:
    if condicion:
        print(f"  [ok]    {etiqueta}")
    else:
        print(f"  [FALLA] {etiqueta}" + (f"  -- {detalle}" if detalle else ""))
        fallos.append(etiqueta)


print(__doc__)

# =============================================================================
#  Sin clave no hay nada que medir contra la API, pero SI hay algo que medir:
#  que el turno no se rompe.
# =============================================================================

if not os.environ.get("DEEPSEEK_API_KEY"):
    print("\n[sin DEEPSEEK_API_KEY]  No se llama a la API.")
    print("Se comprueba lo unico que se puede sin ella: que el flujo degrada.\n")
    r = vi.analizar(bytes([0xFF, 0xD8, 0xFF]) + b"\x00" * 100, "")
    comprobar("sin modelo, el estado es error", r.estado == vi.ERROR)
    comprobar("sin modelo, NO se produce texto para el agente",
              vi.texto_para_el_agente(r) == "")
    comprobar("sin modelo, no queda un analisis a medias", not r.ok)
    print("\n" + "=" * 70)
    if fallos:
        print(f"FALLARON {len(fallos)}")
        sys.exit(1)
    print("VERDE (parcial) -- la API real NO se verifico: falta DEEPSEEK_API_KEY")
    print("=" * 70)
    sys.exit(0)

# =============================================================================
#  La imagen.
# =============================================================================

ruta = sys.argv[1] if len(sys.argv) > 1 else ""
if ruta:
    origen = Path(ruta)
    if not origen.exists():
        print(f"[error] no existe: {origen}")
        sys.exit(2)
    crudo = origen.read_bytes()
    print(f"\n  imagen: {origen.name} ({len(crudo) // 1024} KB) "
          f"-- la paso quien corre la prueba")
else:
    from tests.imagen_ont_sintetica import construir
    crudo = construir()
    print(f"\n  imagen: ONT sintetica dibujada aca ({len(crudo) // 1024} KB)")

#  SE ENVIA LO QUE SE GUARDA. Pasa por la misma compresion de produccion:
#  medir con el original mediria un camino que no existe.
listo, mime = media.preparar(crudo, "image", "image/jpeg")
print(f"  tras comprimir_imagen(): {len(listo) // 1024} KB  {mime}")

PIE = "Mira como esta mi modem, la lucecita roja"
print(f"  pie del cliente: \"{PIE}\"")

# =============================================================================
print("\n1. LA LLAMADA DE VISION")
# =============================================================================

t0 = time.monotonic()
r = vi.analizar(listo, MODELO, PIE)
visto_en = time.monotonic() - t0

print(f"  modelo   {MODELO}")
print(f"  tiempo   {visto_en:.1f} s")
print(f"  tokens   {r.tokens or 'no informados'}")
print(f"  estado   {r.estado}")
if r.error:
    print(f"  error    {r.error}")

comprobar("la API acepto la imagen", r.estado != vi.ERROR, r.error)
if r.estado == vi.ERROR:
    print("\n" + "=" * 70)
    print("EL PROVEEDOR RECHAZO LA IMAGEN. No se improvisa otra arquitectura:")
    print("se lee que parte rechazo y se hace el cambio minimo.")
    print("=" * 70)
    sys.exit(1)

comprobar("devolvio una descripcion", r.ok and len(r.texto) > 40)
comprobar("el tiempo esta dentro del timeout",
          visto_en < vi.TIMEOUT_SEGUNDOS,
          f"{visto_en:.1f}s de {vi.TIMEOUT_SEGUNDOS}s")

print("\n  LO QUE VIO:")
print("  " + "\n  ".join(r.texto.splitlines()))

# =============================================================================
print("\n2. QUE SE LE PASA AL AGENTE")
# =============================================================================

contexto = vi.texto_para_el_agente(r, PIE)
print("  " + "\n  ".join(contexto.splitlines()))

comprobar("rotulado como foto", contexto.startswith("[Foto que envio el cliente]"))
comprobar("el pie del cliente no se perdio", PIE in contexto)
comprobar("y aparece una sola vez", contexto.count(PIE) == 1)
comprobar("el pie va antes del analisis",
          contexto.index(PIE) < contexto.index("[Analisis automatico"))
comprobar("el analisis se marca como no verificado",
          "no verificado" in contexto)

#  LO QUE NUNCA PUEDE ESTAR.
import base64 as _b64
PREFIJO = _b64.b64encode(listo).decode("ascii")[:40]
comprobar("no hay base64 en el contexto del agente", PREFIJO not in contexto)
comprobar("no hay base64 en lo que se guardaria", PREFIJO not in r.texto)
comprobar("no quedan bytes de imagen en el Resultado",
          not any(isinstance(v, (bytes, bytearray)) for v in vars(r).values()))

#  Si el modelo transcribio algo con forma de documento, la redaccion ya lo
#  tapo: se comprueba sobre el texto que de verdad salio.
sospechosos = re.findall(r"(?<!\d)\d{8,11}(?!\d)", r.texto)
comprobar("no sobrevivio ningun numero con forma de documento",
          not sospechosos, str(sospechosos))

# =============================================================================
print("\n3. EL TURNO CONVERSACIONAL  --  que leeria el cliente")
# =============================================================================

from nucleo.modelo import cliente

SISTEMA = (
    "Eres el asistente de soporte de un proveedor de internet colombiano. "
    "Hablas con el CLIENTE por WhatsApp, de usted, breve y claro. No afirmes "
    "nada que no sepas con certeza. Si hace falta revisar algo que no podes "
    "comprobar, decile que lo vas a escalar. No inventes datos de la cuenta."
)

t0 = time.monotonic()
try:
    resp = cliente.chat(
        MODELO,
        [{"role": "system", "content": SISTEMA},
         {"role": "user", "content": contexto}],
        temperatura=0.1, timeout=60.0)
    contesto_en = time.monotonic() - t0
    respuesta = (resp.contenido or "").strip()
    tokens_turno = (resp.tokens_entrada or 0) + (resp.tokens_salida or 0)
except Exception as e:
    print(f"  [FALLA] el turno conversacional fallo: {type(e).__name__}")
    respuesta, contesto_en, tokens_turno = "", 0.0, 0
    fallos.append("el turno conversacional fallo")

if respuesta:
    print(f"  tiempo   {contesto_en:.1f} s")
    print(f"  tokens   {tokens_turno}")
    print("\n  LO QUE LE LLEGARIA AL CLIENTE:")
    print("  " + "\n  ".join(respuesta.splitlines()))

    comprobar("el agente contesto algo", len(respuesta) > 20)
    comprobar("no le muestra al cliente el rotulo interno",
              "[Analisis automatico" not in respuesta
              and "[Foto que envio" not in respuesta, respuesta[:120])
    comprobar("no le filtra base64", PREFIJO not in respuesta)

    #  LA REGLA QUE MAS IMPORTA. Una foto no muestra un equipo danado: muestra
    #  una luz. Si el agente afirma lo primero, la cadena entera falla aunque
    #  la vision haya sido correcta.
    afirma_dano = re.search(
        r"\b(est[aá] da[nñ]ad[oa]|est[aá] rot[oa]|se da[nñ][oó]|"
        r"equipo da[nñ]ado|fuera de servicio)\b", respuesta, re.I)
    comprobar("NO afirma que el equipo esta danado",
              afirma_dano is None,
              afirma_dano.group(0) if afirma_dano else "")

    comprobar("menciona lo que se vio en la foto",
              re.search(r"\b(luz|led|indicador|roj)", respuesta, re.I)
              is not None, respuesta[:120])

# =============================================================================
print("\n4. RESUMEN DE LA CADENA")
# =============================================================================

print(f"  vision        {visto_en:>6.1f} s   {r.tokens or 0:>6} tokens")
print(f"  conversacion  {contesto_en:>6.1f} s   {tokens_turno:>6} tokens")
print(f"  TOTAL         {visto_en + contesto_en:>6.1f} s   "
      f"{(r.tokens or 0) + tokens_turno:>6} tokens")
print(f"  llamadas a DeepSeek: 2 (una por la foto, una por la respuesta)")

print("\n" + "=" * 70)
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("TODO EN VERDE  --  la cadena completa funciona contra la API real")
print("=" * 70)
