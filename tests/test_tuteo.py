# -*- coding: utf-8 -*-
"""
Guarda del normalizador de tratamiento (nucleo/modelo/tuteo.py).

Lo que de verdad importa aca no son los casos que convierte, sino los que
NO debe tocar: convertir 'el equipo hace ruido' en 'el equipo haz ruido'
seria peor que dejar pasar un 'hace' con acento.
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from nucleo.modelo.tuteo import a_tuteo

CONVIERTE = [
    # frases reales que el modelo produjo en pruebas en vivo (15/08/2026)
    ("¿Sos vos?", "¿Eres tú?"),
    ("¿Me pasás tu número de cédula?", "¿Me pasas tu número de cédula?"),
    ("necesito verificar que sos el titular", "necesito verificar que eres el titular"),
    ("¿cuántos televisores tenés conectados?", "¿cuántos televisores tienes conectados?"),
    ("revisá que el cable esté bien ajustado", "revisa que el cable esté bien ajustado"),
    ("En el otro TV hacé lo mismo: buscá el botón Menú, entrá a Ajustes y elegí ANTENA.",
     "En el otro TV haz lo mismo: busca el botón Menú, entra a Ajustes y elige ANTENA."),
    ("Listo, contame si te salieron los canales.", "Listo, cuentame si te salieron los canales."),
    ("si usás un decodificador TDT", "si usas un decodificador TDT"),
    ("Dale, te espero acá.", "Dale, te espero acá."),          # 'dale' se respeta
    ("hablamos con vos mañana", "hablamos contigo mañana"),
    ("esto es para vos", "esto es para ti"),
    ("Podés reiniciarlo vos mismo", "Puedes reiniciarlo tú mismo"),
    ("SOS el titular", "ERES el titular"),
]

# El corazon de la guarda: palabras correctas que comparten forma con una de
# voseo salvo por la tilde, o que simplemente se le parecen.
NO_TOCA = [
    "el equipo hace ruido desde ayer",
    "la marca del router es Huawei",
    "busca en el menú de tu televisor",       # imperativo tuteo, ya correcto
    "revisa el cable",                        # idem
    "mira la luz roja",                       # idem
    "ya pasas el límite de televisores",      # tuteo ya correcto
    "además el interés es quincenal",
    "quizás después el país lo permita",
    "el técnico entra a las 8 y sale a las 5",
    "dale la clave al cliente",
    "la llama de la vela",
    "toma nota de esto",
    "espera en línea",
    "no conocemos ese modelo",
    "vos" .upper() + "OTRO",                  # dentro de otra palabra, no toca
]

fallos = 0
for entrada, esperado in CONVIERTE:
    obtenido = a_tuteo(entrada)
    if obtenido != esperado:
        print(f"  [FALLA] {entrada!r}\n     esperado: {esperado!r}\n     obtenido: {obtenido!r}")
        fallos += 1

for frase in NO_TOCA:
    obtenido = a_tuteo(frase)
    if obtenido != frase:
        print(f"  [FALSO POSITIVO] {frase!r} -> {obtenido!r}")
        fallos += 1

# Idempotencia: aplicarlo dos veces no puede seguir cambiando el texto.
for entrada, _ in CONVIERTE:
    una = a_tuteo(entrada)
    if a_tuteo(una) != una:
        print(f"  [NO IDEMPOTENTE] {entrada!r} -> {una!r} -> {a_tuteo(una)!r}")
        fallos += 1

if fallos:
    print(f"\n[FALLO] {fallos} problema(s) en el normalizador de tratamiento.")
    sys.exit(1)
print(f"[OK] Tratamiento normalizado: {len(CONVIERTE)} conversiones, "
      f"{len(NO_TOCA)} frases intactas, idempotente.")
