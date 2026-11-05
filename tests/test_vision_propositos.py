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

# =============================================================================
print("\n-- F: el detector del CRM y la instruccion no se contradicen --")
# =============================================================================
#  EL DEFECTO QUE ESTO CIERRA, medido en produccion el 04/11/2026 (OT 100):
#  **4 de 4 fotos pedian una mirada**, y asi iba a ser en todas las ordenes.
#  El detector buscaba "borros", "no se ve", "no se puede", "tapad", "fuera
#  de cuadro"... y la instruccion le PIDE al modelo que diga exactamente eso:
#  «si algo esta borroso, oscuro, tapado o fuera de cuadro, decilo, y deci
#  que no se puede determinar por eso». Se le pedian las frases y despues se
#  usaban como alarma.
#
#  El costo no fue el ruido: el veredicto quedaba en REVISAR, el cierre
#  autonomo exige CERRAR, y ninguna orden con fotos se cerraba sola. Y un
#  aviso que aparece siempre deja de avisar.
#
#  Es un contrato entre DOS SERVICIOS --el motor no importa de Django ni al
#  reves-- asi que se lee el archivo del otro lado. Una guarda estatica es lo
#  unico posible aca, y es mucho mas que nada.
TAREAS = (RAIZ / "django-crm" / "backend" / "campo" / "tasks.py").read_text(
    encoding="utf-8")

#  Se lee con `ast` y no partiendo texto: cortar por comas y comillas
#  devolvia pedazos pegados --'suelto", "sueltos", ...'-- y la prueba
#  afirmaba sobre basura. Leer mal el archivo del otro servicio es
#  exactamente como una guarda de contrato se vuelve decorativa.
import ast as _ast                                               # noqa: E402

_arbol = _ast.parse(TAREAS)
PALABRAS = next(
    [e.value for e in n.value.elts]
    for n in _ast.walk(_arbol)
    if isinstance(n, _ast.Assign)
    and any(getattr(t, "id", "") == "PALABRAS_QUE_PIDEN_MIRAR" for t in n.targets)
)

comprobar("F1. el CRM declara palabras de respaldo", len(PALABRAS) >= 5,
          str(PALABRAS))

#  LA AFIRMACION QUE IMPORTA, y su alcance exacto: ninguna palabra del
#  respaldo puede estar en la parte de la instruccion que le pide al modelo
#  que DESCRIBA, porque entonces la escribe siempre y el respaldo se dispara
#  siempre. Eso es lo que paso.
#
#  La ultima regla --la que define la marca-- queda FUERA de la comprobacion
#  a proposito, y conviene decir por que en vez de ampliar la lista hasta que
#  pase: esa regla nombra defectos ("un cable suelto", "un equipo sin fijar")
#  como EJEMPLOS de cuando poner "ATENCION: si", no como algo que el modelo
#  tenga que escribir en su parrafo. Y cuando esa regla se cumple, el
#  respaldo ni corre: manda la marca.
#
#  Riesgo que queda, y se escribe en vez de taparse: si el modelo IGNORA la
#  regla de la marca y ademas repite sus ejemplos ("no veo ningun cable
#  suelto"), el respaldo se equivoca. Es menos probable que lo anterior --que
#  fallaba SIEMPRE-- y el costo sigue siendo una mirada de mas, nunca un
#  cierre frenado por el codigo.
#  SE BUSCA LA REGLA, Y SI NO ESTA LA PRUEBA FALLA EN VEZ DE REVENTAR.
#  La primera version cortaba con `.index("11. termin")`: al cambiar la
#  redaccion de esa regla, la prueba lanzaba ValueError en vez de decir que
#  la regla se habia perdido. Mata la mutacion igual, pero quien lee el rojo
#  no entiende por que -- medido el 05/11/2026 mutandola.
_bajo = vision.INSTRUCCION_EVIDENCIA.lower()
_corte = _bajo.find("11. ")
comprobar("F2a. la regla de la marca esta donde se la espera", _corte != -1,
          "no hay regla 11: ¿se renombro o se perdio?")
_descriptivas = _bajo[:_corte] if _corte != -1 else _bajo
chocan = [p for p in PALABRAS if p in _descriptivas]
comprobar("F2. ninguna palabra del respaldo la pide la parte descriptiva",
          not chocan, str(chocan))

#  Y las que se sacaron no pueden volver.
for vieja in ("no se ve", "no se puede", "borros", "oscur", "tapad",
              "fuera de cuadro"):
    comprobar(f"F3. '{vieja}' ya no esta en el detector", vieja not in PALABRAS)

#  El contrato de la marca: la cadena esta escrita en los dos lados.
comprobar("F4. la instruccion pide la marca",
          "ATENCION: si" in vision.INSTRUCCION_EVIDENCIA
          and "ATENCION: no" in vision.INSTRUCCION_EVIDENCIA)
#  Y la PIDE, no la sugiere. Volverla opcional ("podés terminar con...")
#  dejaba el respaldo gobernando en silencio, y la guarda pasaba igual:
#  medido mutandola el 05/11/2026.
#  LA PIDE, no la sugiere. Volverla opcional dejaba el respaldo gobernando
#  en silencio y la guarda pasaba igual: medido mutandola el 05/11/2026.
comprobar("F4b. y la pide, no la sugiere",
          "Terminá con una ultima linea" in vision.INSTRUCCION_EVIDENCIA,
          vision.INSTRUCCION_EVIDENCIA[_corte:_corte + 70] if _corte != -1 else "")
comprobar("F4c. y no la deja a eleccion del modelo",
          not any(p in _bajo for p in ("opcional", "si querés", "si queres",
                                       "podés terminar", "podes terminar")))
comprobar("F5. y el CRM lee esa misma marca",
          'MARCA_ATENCION = "' + vision.MARCA_ATENCION.lower() + ':"' in TAREAS,
          vision.MARCA_ATENCION)

#  Solo la de evidencia la pide: las otras dos no tienen quien la lea.
comprobar("F6. la del cliente no pide la marca",
          vision.MARCA_ATENCION not in vision.INSTRUCCION)
comprobar("F7. la del asistente tampoco",
          vision.MARCA_ATENCION not in vision.INSTRUCCION_ASISTENTE)

print("\n" + "=" * 72)
if fallos:
    print(f" {len(fallos)} FALLAS:")
    for f in fallos:
        print(f"   - {f}")
    sys.exit(1)
print(" TODO EN VERDE")
sys.exit(0)
