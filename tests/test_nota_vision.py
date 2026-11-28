# -*- coding: utf-8 -*-
"""
================================================================================
 LA NOTA DE VISION  --  lo que se puede garantizar, y lo que solo se mide
================================================================================

    py -3.13 tests/test_nota_vision.py                 (sin red: las guardas)
    DEEPSEEK_API_KEY=... py -3.13 tests/test_nota_vision.py --real   (+ medicion)

DOS COSAS DISTINTAS, Y MEZCLARLAS SERIA MENTIR
-----------------------------------------------
Lo que se pide --"que la respuesta al cliente sea corta"-- es CONDUCTA DEL
MODELO, y ninguna prueba sin red puede garantizarla. La nota es una
instruccion: guia, no garantia (PRD 7.4). Nada en el codigo impide que el
modelo conteste largo igual.

Asi que esto esta partido en dos, y cada parte dice lo que es:

  GUARDAS (secciones 1-4, sin red)
      Que la nota se inyecte cuando hay foto y SOLO cuando hay foto.
      Que el analisis siga llegando entero.
      Que el texto y el audio no cambien en nada.
      Esto si se garantiza, y si falla es un defecto.

  MEDICION (seccion 5, con --real)
      Cuanto se acorta la respuesta de verdad. Pide el modelo, cuesta plata,
      varia entre corridas y NO corre en CI. Es un instrumento, no una guarda:
      un numero peor no es necesariamente una regresion, y por eso compara
      con y sin nota EN LA MISMA CORRIDA, que es la unica forma de que la
      comparacion signifique algo.
================================================================================
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.canales import vision as vi
from nucleo.modelo import nota_vision

fallos: list[str] = []


def comprobar(etiqueta: str, condicion: bool, detalle: str = "") -> None:
    if condicion:
        print(f"  [ok]    {etiqueta}")
    else:
        print(f"  [FALLA] {etiqueta}" + (f"  -- {detalle}" if detalle else ""))
        fallos.append(etiqueta)


#  El analisis REAL que DeepSeek devolvio en produccion el 05/10/2026, sacado
#  de asistente.media. Es el caso que motivo todo esto: 525 caracteres que el
#  modelo le copiaba al cliente.
ANALISIS_REAL = (
    "Se ve un equipo blanco con rejillas y dos antenas verticales, montado en "
    "una pared clara. En la parte superior tiene una fila de indicadores LED: "
    "varios estan encendidos en verde y otros apagados; no se distingue si "
    "parpadean y los rotulos no se leen con claridad. Hay cables negros "
    "gruesos que pasan por delante y se cruzan, un cable blanco que baja por "
    "el lateral izquierdo y un conector metalico conectado en la parte "
    "inferior derecha, parcialmente tapado por los cables. No se observan "
    "luces rojas ni naranjas encendidas."
)

r = vi.Resultado(texto=ANALISIS_REAL, estado=vi.PROCESADO)
CON_FOTO = vi.texto_para_el_agente(r, "Mira la luz roja")
CON_FOTO_SIN_PIE = vi.texto_para_el_agente(r)

print(__doc__)

# =============================================================================
print("\n1. LA NOTA APARECE CUANDO HAY FOTO")
# =============================================================================

comprobar("un turno con foto la recibe", nota_vision.turno_con_foto(CON_FOTO))
comprobar("y la nota no viene vacia", len(nota_vision.nota_para(CON_FOTO)) > 200)
comprobar("tambien sin pie del cliente",
          nota_vision.turno_con_foto(CON_FOTO_SIN_PIE))

# =============================================================================
print("\n2. Y NO APARECE EN NINGUN OTRO TURNO")
# =============================================================================

otros = {
    "un mensaje de texto": "Buenas, se me fue el internet desde anoche",
    "una nota de voz": "[Nota de voz del cliente] Hola, se fue el internet.",
    "voz con pie": ("[Nota de voz del cliente] Se fue el internet.\n"
                    "[Texto que escribio junto al audio] urgente"),
    "una foto que NO se pudo mirar": "[El cliente envio una foto]",
    "un video": "[El cliente envio un video]",
    "un documento": "[El cliente envio un documento]",
    "el pie solo, sin analisis": "Mira la luz roja",
    "vacio": "",
}
for etiqueta, texto in otros.items():
    comprobar(f"{etiqueta}: sin nota",
              not nota_vision.turno_con_foto(texto)
              and nota_vision.nota_para(texto) == "", texto[:40])

#  Que alguien escriba el rotulo a mano no deberia pasar, pero si pasa la nota
#  es inofensiva: solo pide no copiar un analisis que no existe.
comprobar("el disparador es el rotulo exacto de vision.py",
          nota_vision.ROTULO_ANALISIS
          == "[Analisis automatico de la foto, no verificado]")
comprobar("y vision.py sigue poniendo ESE rotulo",
          nota_vision.ROTULO_ANALISIS in CON_FOTO)

# =============================================================================
print("\n3. NO SE LE QUITA NADA AL MODELO")
# =============================================================================

#  Es la regla que mas importa del encargo: la nota AGREGA, nunca recorta.
comprobar("el analisis completo sigue en el mensaje del turno",
          ANALISIS_REAL in CON_FOTO)
comprobar("y entero, sin recortar",
          CON_FOTO.count(ANALISIS_REAL) == 1
          and len(ANALISIS_REAL) == 525, str(len(ANALISIS_REAL)))
comprobar("el pie del cliente tampoco se toca",
          "Mira la luz roja" in CON_FOTO)
comprobar("la nota no modifica el mensaje: es un bloque aparte",
          nota_vision.nota_para(CON_FOTO) not in CON_FOTO)

# =============================================================================
print("\n4. LA NOTA DICE LO QUE TIENE QUE DECIR")
# =============================================================================

#  Prueba DEBIL a proposito --que el prompt lo diga no obliga al modelo-- y
#  esta para que nadie borre una de estas reglas sin darse cuenta. Cada una
#  corresponde a un punto del encargo.
n = nota_vision.NOTA
for etiqueta, aguja in (
        ("que es contexto, no un mensaje", "CONTEXTO PARA TI"),
        ("no enumerar lo que hay en la imagen", "No enumeres"),
        ("no copiar frases del analisis", "No copies frases"),
        ("no hablar de modelo ni analisis", "Nunca menciones que hubo un analisis"),
        ("tope de preguntas", "tres como maximo"),
        ("priorizar si hay servicio", "si el servicio esta funcionando"),
        ("parrafos cortos", "parrafos CORTOS"),
        ("no afirmar lo que la foto no demuestra", "No afirmes como un hecho"),
):
    comprobar(f"la nota pide: {etiqueta}", aguja in n)

comprobar("la nota no nombra a ninguna empresa", "rapilink" not in n.lower())

fuente = Path("nucleo/modelo/nota_vision.py").read_text(encoding="utf-8")
comprobar("el modulo no nombra a ninguna empresa",
          "rapilink" not in fuente.lower())

# =============================================================================
print("\n5. DONDE SE INYECTA, DENTRO DEL TURNO")
# =============================================================================

motor_py = Path("nucleo/modelo/motor.py").read_text(encoding="utf-8")
desde = motor_py.index("def responder(")
cuerpo = motor_py[desde:desde + 20000]

comprobar("el motor la inyecta como mensaje de SISTEMA, no de usuario",
          'historial.append({"role": "system", "content": nota_foto})' in cuerpo)
comprobar("y JUSTO ANTES del mensaje del cliente",
          cuerpo.index("nota_vision.nota_para(mensaje)")
          < cuerpo.index('historial.append({"role": "user", "content": mensaje})'))
comprobar("solo se agrega si hay nota (un turno sin foto no cambia)",
          "if nota_foto:" in cuerpo)

#  El camino real: se arma un historial como lo hace el motor y se mira.
historial_con = []
nota = nota_vision.nota_para(CON_FOTO)
if nota:
    historial_con.append({"role": "system", "content": nota})
historial_con.append({"role": "user", "content": CON_FOTO})

historial_sin = []
nota2 = nota_vision.nota_para("Buenas, se me fue el internet")
if nota2:
    historial_sin.append({"role": "system", "content": nota2})
historial_sin.append({"role": "user", "content": "Buenas, se me fue el internet"})

comprobar("con foto: 2 mensajes (nota + cliente)", len(historial_con) == 2)
comprobar("sin foto: 1 mensaje, el del cliente y nada mas",
          len(historial_sin) == 1
          and historial_sin[0]["role"] == "user")

# =============================================================================
#  MEDICION  --  solo con --real. Pide el modelo y cuesta plata.
# =============================================================================

if "--real" not in sys.argv:
    print("\n" + "=" * 70)
    if fallos:
        print(f"FALLARON {len(fallos)}:")
        for f in fallos:
            print(f"  - {f}")
        sys.exit(1)
    print("GUARDAS EN VERDE.")
    print("La MEDICION de cuanto se acorta no corrio: pedir --real para eso.")
    print("=" * 70)
    sys.exit(0)

import os
import re
import time

if not os.environ.get("DEEPSEEK_API_KEY"):
    print("\n[--real] falta DEEPSEEK_API_KEY")
    sys.exit(2)

from nucleo.modelo import cliente

MODELO = "deepseek:deepseek-v4-flash"
SISTEMA = (
    "Eres el asistente de soporte de un proveedor de internet colombiano. "
    "Hablas con el CLIENTE por WhatsApp, de tu, en espanol de Colombia. No "
    "afirmes nada que no sepas con certeza."
)

print("\n" + "=" * 70)
print(" MEDICION  --  la misma foto, con y sin la nota")
print("=" * 70)
print("  (instrumento, no guarda: pide el modelo y varia entre corridas)")


def pedir(con_nota: bool):
    msgs = [{"role": "system", "content": SISTEMA}]
    if con_nota:
        msgs.append({"role": "system", "content": nota_vision.NOTA})
    msgs.append({"role": "user", "content": CON_FOTO})
    t0 = time.monotonic()
    r = cliente.chat(MODELO, msgs, temperatura=0.1, timeout=60.0)
    return (r.contenido or "").strip(), time.monotonic() - t0


largos = {}
for etiqueta, con in (("SIN la nota", False), ("CON la nota", True)):
    texto, seg = pedir(con)
    largos[etiqueta] = len(texto)
    preguntas = texto.count("?")
    parrafos = len([p for p in texto.split("\n\n") if p.strip()])
    print(f"\n--- {etiqueta} ---  {len(texto)} caracteres · "
          f"{preguntas} preguntas · {parrafos} parrafos · {seg:.1f}s")
    print("  " + "\n  ".join(texto.splitlines()))

    if con:
        comprobar("CON la nota: cabe en un vistazo (<600 caracteres)",
                  len(texto) < 600, f"{len(texto)}")
        comprobar("CON la nota: tres preguntas o menos",
                  preguntas <= 3, f"{preguntas}")
        comprobar("CON la nota: no le habla de un analisis ni de un modelo",
                  not re.search(r"an[aá]lisis autom|modelo de|sistema de|procesad",
                                texto, re.I), texto[:100])
        comprobar("CON la nota: sigue preguntando algo", "?" in texto)

        #  NO COPIA EL ANALISIS. Se mide por frases de 6 palabras del
        #  original: una coincidencia asi no es casualidad del idioma.
        palabras = ANALISIS_REAL.split()
        frases = {" ".join(palabras[i:i + 6]).lower().strip(".,;:")
                  for i in range(len(palabras) - 5)}
        plano = " ".join(texto.lower().split())
        copiadas = [f for f in frases if f in plano]
        comprobar("CON la nota: no copia frases del analisis",
                  not copiadas, str(copiadas[:2]))

        #  NO ENUMERA LA FOTO. Son las cosas que el analisis menciona y que al
        #  cliente no le aportan nada: el ya vio su equipo.
        inventario = [p for p in ("antenas", "rejillas", "cables negros",
                                  "conector metalico", "cable blanco",
                                  "pared clara")
                      if p in texto.lower()]
        comprobar("CON la nota: no le enumera lo que hay en la foto",
                  len(inventario) == 0, str(inventario))

print(f"\n  se acorto {largos['SIN la nota'] - largos['CON la nota']} caracteres "
      f"({100 - largos['CON la nota'] * 100 // max(1, largos['SIN la nota'])}% menos)")

# =============================================================================
print("\n" + "=" * 70)
print(" LO QUE NO PUEDE PERDERSE AL ACORTAR")
print("=" * 70)
#  Acortar es facil; acortar SIN tirar el hallazgo es el problema. Si el
#  analisis confirma una luz roja, esa luz tiene que llegarle al cliente,
#  corta o no la respuesta. Una nota que lograra respuestas de dos lineas
#  comiendose esto habria empeorado el sistema, no mejorado.
CRITICO = ("Se ve una ONT con cinco indicadores. POWER esta en verde fijo y "
           "LOS esta en rojo intermitente. Los demas estan apagados. Los "
           "rotulos se leen con claridad.")
mensaje_critico = vi.texto_para_el_agente(
    vi.Resultado(texto=CRITICO, estado=vi.PROCESADO), "que pasa con mi internet")

t0 = time.monotonic()
r = cliente.chat(MODELO,
                 [{"role": "system", "content": SISTEMA},
                  {"role": "system", "content": nota_vision.NOTA},
                  {"role": "user", "content": mensaje_critico}],
                 temperatura=0.1, timeout=60.0)
critico = (r.contenido or "").strip()
print(f"\n--- con una luz LOS roja CONFIRMADA ---  {len(critico)} caracteres · "
      f"{time.monotonic() - t0:.1f}s")
print("  " + "\n  ".join(critico.splitlines()))

#  SE AFIRMA SOBRE EL HALLAZGO, NO SOBRE LA SIGLA.
#
#  La primera version exigia la palabra 'LOS' literal y dio rojo con esta
#  respuesta: "ese equipo esta sin senal de fibra: la luz roja que esta
#  prendiendo y apagando indica que no le esta llegando la conexion". O sea
#  que fallaba por traducir un rotulo tecnico a algo que el cliente entiende
#  -- que es lo que la nota pide y lo que el prompt del tenant pide. Una
#  prueba que castiga lo correcto se termina ignorando.
#
#  Lo que de verdad no puede perderse es el HALLAZGO: que hay una luz roja y
#  que eso apunta a falta de senal. Como se le diga al cliente es del
#  dialecto de la empresa, no de esta prueba.
comprobar("el hallazgo critico llega al cliente: la luz roja",
          re.search(r"\broj", critico, re.I) is not None, critico[:120])
comprobar("y su consecuencia: sin senal / sin servicio",
          re.search(r"se[nñ]al|fibra|sin internet|sin servicio|conexi[oó]n",
                    critico, re.I) is not None, critico[:120])
comprobar("y sigue siendo corta", len(critico) < 700, f"{len(critico)}")
comprobar("no inventa un diagnostico que el analisis no afirma",
          not re.search(r"(est[aá]|esta)\s+(da[nñ]ad|rot|quemad)", critico, re.I),
          critico[:120])

print("\n" + "=" * 70)
if fallos:
    print(f"FALLARON {len(fallos)}:")
    for f in fallos:
        print(f"  - {f}")
    sys.exit(1)
print("TODO EN VERDE  --  guardas y medicion")
print("=" * 70)
