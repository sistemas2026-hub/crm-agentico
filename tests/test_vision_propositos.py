# -*- coding: utf-8 -*-
"""
================================================================================
 TRES PROPOSITOS, TRES CONSENTIMIENTOS  --  02/11/2026
================================================================================

    py -3.13 tests/test_vision_propositos.py

QUE SE CAMBIO
-------------
La misma foto puede llegar por tres caminos, y no los respalda el mismo
consentimiento:

    whatsapp_cliente    la que un cliente DECIDE mandar
    evidencia_campo     la que un tecnico toma DENTRO de la casa del cliente
    asistente_interno   la que un colaborador adjunta en el chat interno

Cada uno tiene su interruptor en la config del tenant y su instruccion. Lo
que se evita con eso: que encender uno encienda los otros, que es lo que
habria pasado con una sola bandera.

QUE SE AFIRMA, Y POR QUE ASI
-----------------------------
Sobre el EFECTO: que cada proposito resuelva SU bandera y SU instruccion, que
un nombre desconocido no habilite nada, y que el rotulo del turno diga de
donde salio la foto. Afirmar que el diccionario PROPOSITOS existe no probaria
nada: un dict que nadie consulta se ve igual de bien en el diff.

NO SE LLAMA A NINGUNA API NI AL MODELO.
================================================================================
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml                                                      # noqa: E402

from nucleo.canales import vision                                # noqa: E402
from nucleo.config.schema import TenantConfig                    # noqa: E402

RAIZ = Path(__file__).resolve().parents[1]

fallos: list[str] = []


def comprobar(etiqueta: str, condicion: bool, detalle: str = "") -> None:
    if condicion:
        print(f"  [ok]    {etiqueta}")
    else:
        print(f"  [FALLA] {etiqueta}" + (f"  -- {detalle}" if detalle else ""))
        fallos.append(etiqueta)


print("=" * 72)
print(" TRES PROPOSITOS, TRES CONSENTIMIENTOS  (sin red, sin modelo)")
print("=" * 72)

# =============================================================================
print("\n-- A: cada proposito tiene SU bandera, y son distintas --")
# =============================================================================
banderas = {p: vision.bandera_de(p) for p in vision.PROPOSITOS}
comprobar("A1. los tres propositos declaran bandera", all(banderas.values()),
          str(banderas))
comprobar("A2. y son TRES distintas, no la misma repetida",
          len(set(banderas.values())) == 3, str(banderas))

#  LA QUE IMPORTA: encender una no enciende las otras. Si alguien volviera a
#  colapsarlas en un solo campo, esto se pone rojo.
comprobar("A3. la del cliente no es la de campo",
          vision.bandera_de("whatsapp_cliente") != vision.bandera_de("evidencia_campo"))
comprobar("A4. la de campo no es la del asistente interno",
          vision.bandera_de("evidencia_campo") != vision.bandera_de("asistente_interno"))

# =============================================================================
print("\n-- B: un proposito que el codigo no conoce no habilita nada --")
# =============================================================================
#  Falla CERRADO: sin bandera, quien llama no tiene que consultar. Devolver
#  una bandera cualquiera habria hecho que un typo encendiera otro camino.
for inventado in ("", "   ", "asistente", "whatsapp", "evidencia", None):
    comprobar(f"B. {inventado!r} no tiene bandera",
              vision.bandera_de(inventado or "") == "")

# =============================================================================
print("\n-- C: cada uno pide algo distinto, y lo desconocido cae en lo mas estricto --")
# =============================================================================
comprobar("C1. campo usa la de evidencia",
          vision.instruccion_de("evidencia_campo") is vision.INSTRUCCION_EVIDENCIA)
comprobar("C2. el asistente usa la suya",
          vision.instruccion_de("asistente_interno") is vision.INSTRUCCION_ASISTENTE)
comprobar("C3. el cliente usa la de siempre",
          vision.instruccion_de("whatsapp_cliente") is vision.INSTRUCCION)
#  Lo desconocido cae en la del CLIENTE, que es la unica que prohibe afirmar
#  que algo esta mal instalado: ante la duda, la mas restrictiva.
comprobar("C4. un proposito desconocido cae en la MAS restrictiva",
          vision.instruccion_de("xxx") is vision.INSTRUCCION)

comprobar("C5. las tres instrucciones son distintas de verdad",
          len({vision.INSTRUCCION, vision.INSTRUCCION_EVIDENCIA,
               vision.INSTRUCCION_ASISTENTE}) == 3)

#  Lo que NINGUNA puede perder, miradas las tres juntas.
for nombre, texto in (("cliente", vision.INSTRUCCION),
                      ("evidencia", vision.INSTRUCCION_EVIDENCIA),
                      ("asistente", vision.INSTRUCCION_ASISTENTE)):
    comprobar(f"C6. la de {nombre} prohibe transcribir documentos",
              "cedulas" in texto)
for nombre, texto in (("evidencia", vision.INSTRUCCION_EVIDENCIA),
                      ("asistente", vision.INSTRUCCION_ASISTENTE)):
    comprobar(f"C7. la de {nombre} sigue sin poder decir que el servicio anda",
              "NO digas si el servicio funciona" in texto)
    comprobar(f"C8. la de {nombre} prohibe inventar una medicion",
              "potencia optica" in texto)
    comprobar(f"C9. la de {nombre} acota la foto fuera de tema",
              "nada mas" in texto)

# =============================================================================
print("\n-- D: el rotulo del turno dice de DONDE salio la foto --")
# =============================================================================
#  Era la constante "[Foto que envio el cliente]" para todos. Con el asistente
#  interno eso pasaba a ser falso --la adjunta un colaborador-- y el modelo no
#  trata igual una foto del cliente que una de la oficina.
r = vision.Resultado(texto="Se ve una ONT con la luz PON fija.",
                     estado=vision.PROCESADO)
rotulos = {p: vision.texto_para_el_agente(r, proposito=p).splitlines()[0]
           for p in vision.PROPOSITOS}
comprobar("D1. los tres rotulos son distintos", len(set(rotulos.values())) == 3,
          str(rotulos))
comprobar("D2. el del cliente dice que la envio el cliente",
          "cliente" in rotulos["whatsapp_cliente"])
comprobar("D3. el del asistente NO dice que la envio el cliente",
          "cliente" not in rotulos["asistente_interno"],
          rotulos["asistente_interno"])
comprobar("D4. sin proposito sigue siendo el del cliente",
          vision.texto_para_el_agente(r).splitlines()[0]
          == rotulos["whatsapp_cliente"])
comprobar("D5. un proposito desconocido no deja el turno sin rotulo",
          vision.texto_para_el_agente(r, proposito="xxx").splitlines()[0]
          == rotulos["whatsapp_cliente"])

#  El analisis sigue rotulado como lectura automatica NO verificada: es lo que
#  impide que el agente lo repita como un hecho comprobado.
for p in vision.PROPOSITOS:
    comprobar(f"D6. {p} marca el analisis como no verificado",
              "[Analisis automatico de la foto, no verificado]"
              in vision.texto_para_el_agente(r, proposito=p))

# =============================================================================
print("\n-- E: el tenant real declara las tres, y nacen apagadas --")
# =============================================================================
config = TenantConfig.model_validate(
    yaml.safe_load((RAIZ / "tenants" / "rapilink.config.yaml").read_text(
        encoding="utf-8")))
for p, bandera in banderas.items():
    comprobar(f"E1. el schema conoce '{bandera}'", hasattr(config, bandera))

#  EL DEFAULT, no el YAML de rapilink --que ya tiene una en true--. Se arma
#  quitandole las tres banderas a la config real: lo que queda es lo que ve
#  una empresa nueva, y las tres tienen que estar apagadas. Encender vision
#  para un camino no puede encenderla para otro.
crudo = yaml.safe_load((RAIZ / "tenants" / "rapilink.config.yaml").read_text(
    encoding="utf-8"))
for bandera in banderas.values():
    crudo.pop(bandera, None)
limpio = TenantConfig.model_validate(crudo)
for p, bandera in banderas.items():
    comprobar(f"E2. '{bandera}' nace apagada", getattr(limpio, bandera) is False)

print("\n" + "=" * 72)
if fallos:
    print(f" {len(fallos)} FALLAS:")
    for f in fallos:
        print(f"   - {f}")
    sys.exit(1)
print(" TODO EN VERDE")
sys.exit(0)
