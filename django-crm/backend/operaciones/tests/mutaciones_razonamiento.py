# -*- coding: utf-8 -*-
"""
================================================================================
 MUTACIONES DE LA CONSTANCIA  --  comprobar que las pruebas sirven de verdad
================================================================================

POR QUE ESTE ARCHIVO ESTA EN EL REPOSITORIO Y NO EN UN TEMPORAL
---------------------------------------------------------------
Porque la vez anterior no estuvo. Las tres mutaciones de la Fase 2 del cerebro
se definieron, se corrieron, y su procedimiento quedo en archivos de sesion
fuera del arbol: hoy nadie puede volver a correrlas ni comprobar que mataron lo
que decian matar. La evidencia de que las pruebas sirven dejo de ser
consultable, que es exactamente la clase de hueco que §6 de CLAUDE.md llama
"una prueba que dice que algo EXISTE no prueba que funcione".

QUE HACE
--------
Rompe el codigo a proposito, de a una rotura, y afirma que la prueba señalada
queda EN ROJO. Si una rotura no mata a nadie, esa prueba es decorativa y hay
que reescribirla -- ese es el unico resultado que importa.

RESPALDO POR COPIA, NUNCA CON GIT
---------------------------------
'git checkout --' ya destruyo trabajo una vez en este proyecto. El respaldo se
hace copiando el archivo a un temporal del sistema y restaurandolo desde ahi.

Y CADA MUTACION SE AFIRMA ANTES DE MEDIR
----------------------------------------
Si el texto a reemplazar no aparece --porque el codigo cambio-- el script
LEVANTA en vez de seguir. Medir un archivo intacto y declararlo "mutacion
sobrevivida" es el peor resultado posible: da por buena una prueba que nunca se
ejercito.

COMO SE USA
-----------
    python operaciones/tests/mutaciones_razonamiento.py --listar
    python operaciones/tests/mutaciones_razonamiento.py --respaldar
    python operaciones/tests/mutaciones_razonamiento.py m1_guarda_el_enriquecido
    #  ... correr pytest operaciones/tests/test_razonamiento.py ...
    python operaciones/tests/mutaciones_razonamiento.py --restaurar
    python operaciones/tests/mutaciones_razonamiento.py --comprobar

'--comprobar' afirma que los archivos volvieron identicos al respaldo, por
checksum. Correrlo al final no es opcional: una mutacion que queda puesta es un
defecto introducido a mano.
"""

import ast
import hashlib
import io
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.dirname(os.path.dirname(AQUI))
RESPALDO = os.path.join(AQUI, "_respaldo_mutaciones")

ARCHIVOS = {
    "supervisor": os.path.join(BACKEND, "operaciones", "supervisor.py"),
    "razonamiento": os.path.join(BACKEND, "operaciones", "razonamiento.py"),
}


#  Cada entrada: (archivo, [(texto_viejo, texto_nuevo), ...], prueba_que_debe_morir)
MUTACIONES = {
    #  M1. Guardar el analisis YA ENRIQUECIDO en vez del previo.
    #      Es el fallo que no se nota: la tabla se llena, los tableros
    #      funcionan, y la comparacion da coincidencia del 100% porque compara
    #      el resultado contra si mismo.
    "m1_guarda_el_enriquecido": (
        "supervisor",
        [("""    return Aporte(cerebro.analisis_de_veredicto(veredicto, analisis),
                  veredicto=veredicto, previo=previo, enriquecio=True)""",
          """    _enriquecido = cerebro.analisis_de_veredicto(veredicto, analisis)
    return Aporte(_enriquecido,
                  veredicto=veredicto, previo=dict(_enriquecido),
                  enriquecio=True)""")],
        "test_5_guarda_el_analisis_de_antes_no_el_enriquecido",
    ),

    #  M2. No registrar cuando el veredicto no concluye.
    #      Sesga la medicion hacia arriba: desaparecen justo las veces que el
    #      cerebro se quedo corto y lo dijo.
    "m2_no_registra_lo_no_concluyente": (
        "razonamiento",
        [("""    if veredicto is None:
        return None""",
          """    if veredicto is None or not veredicto.concluyente:
        return None""")],
        "test_3_lo_no_concluyente_tambien_queda",
    ),

    #  M3. 'solo registra' tambien enriquece.
    #      Rompe la etapa de observacion entera: el cerebro influiria en las
    #      propuestas creyendo que solo mira.
    "m3_solo_registra_tambien_enriquece": (
        "supervisor",
        [("""    if not CEREBRO_EN_EL_CICLO:
        #  Solo registra: el analisis sale INTACTO.""",
          """    if False:
        #  Solo registra: el analisis sale INTACTO.""")],
        "test_2_solo_registra_deja_el_analisis_intacto",
    ),

    #  M4. Tirar los descartes antes de guardar.
    #      Se pierde la metrica mas incomoda: cuantas veces el modelo afirmo
    #      algo sin respaldo.
    "m4_tira_los_descartes": (
        "razonamiento",
        [("""            descartes=[_sin_identificadores(str(d))[:TOPE_TEXTO]
                       for d in (veredicto.descartes or [])[:TOPE_LISTA]],""",
          """            descartes=[],""")],
        "test_4_lo_descartado_queda_registrado",
    ),

    #  M5. Dejar el saneo de identificadores sin efecto.
    #      El cinturon de PII deja de cerrar y nada lo dice.
    "m5_no_sanea_identificadores": (
        "razonamiento",
        [("""    for patron, reemplazo in _PATRONES:
        texto = patron.sub(reemplazo, texto)
    return texto""",
          """    return texto""")],
        "test_8_los_identificadores_no_quedan_en_claro",
    ),

    #  M6. Enriquecer sin registrar  --  la cuarta combinacion prohibida.
    "m6_enriquece_sin_registrar": (
        "supervisor",
        [("""    return bool(CEREBRO_REGISTRA or CEREBRO_EN_EL_CICLO)""",
          """    return bool(CEREBRO_REGISTRA)""")],
        "test_7_enriquecer_implica_registrar",
    ),
}


def _sha(ruta):
    return hashlib.sha256(io.open(ruta, "rb").read()).hexdigest()


def respaldar():
    if not os.path.isdir(RESPALDO):
        os.makedirs(RESPALDO)
    print("respaldo POR COPIA (nunca con git):")
    for clave, ruta in ARCHIVOS.items():
        shutil.copyfile(ruta, os.path.join(RESPALDO, clave + ".py"))
        print("  %-14s %s" % (clave, _sha(ruta)[:16]))


def restaurar():
    for clave, ruta in ARCHIVOS.items():
        copia = os.path.join(RESPALDO, clave + ".py")
        if not os.path.isfile(copia):
            raise SystemExit("no hay respaldo de %s: correr --respaldar primero"
                             % clave)
        shutil.copyfile(copia, ruta)
    print("restaurado: " + "  ".join(
        "%s=%s" % (c, _sha(r)[:12]) for c, r in ARCHIVOS.items()))


def comprobar():
    ok = True
    for clave, ruta in ARCHIVOS.items():
        copia = os.path.join(RESPALDO, clave + ".py")
        igual = os.path.isfile(copia) and _sha(ruta) == _sha(copia)
        ok = ok and igual
        print("  %s %-14s %s" % ("OK  " if igual else "DIST", clave,
                                 _sha(ruta)[:16]))
    print("IDENTICO AL RESPALDO" if ok else ">>> HAY DIFERENCIAS: restaurar")
    return 0 if ok else 1


def listar():
    print("mutaciones disponibles, y la prueba que cada una DEBE matar:\n")
    for clave, (_, _, prueba) in MUTACIONES.items():
        print("  %-36s -> %s" % (clave, prueba))
    print("\nSi una mutacion no deja en rojo su prueba, esa prueba es")
    print("decorativa y hay que reescribirla midiendo el efecto.")


def mutar(clave):
    archivo, cambios, prueba = MUTACIONES[clave]
    restaurar()
    ruta = ARCHIVOS[archivo]
    bruto = io.open(ruta, "rb").read()
    salto = "\r\n" if bruto.count(b"\r\n") else "\n"
    antes = bruto.decode("utf-8").replace("\r\n", "\n")

    texto = antes
    for viejo, nuevo in cambios:
        #  SE AFIRMA, no se asume: si el codigo cambio y el ancla ya no esta,
        #  medir un archivo intacto daria "mutacion sobrevivida" y declararia
        #  buena una prueba que nunca se ejercito.
        if viejo not in texto:
            raise SystemExit(
                "NO se encontro el texto a mutar en %s.\n"
                "El codigo cambio: hay que actualizar la mutacion '%s'.\n"
                "  buscaba: %r" % (archivo, clave, viejo[:70]))
        texto = texto.replace(viejo, nuevo, 1)

    if texto == antes:
        raise SystemExit("la mutacion no cambio el archivo")
    ast.parse(texto)                      # que siga siendo Python valido

    io.open(ruta, "wb").write(texto.replace("\n", salto).encode("utf-8"))
    print("MUTADO %s en %s.py  (AST ok, %s)"
          % (clave, archivo, _sha(ruta)[:12]))
    print("  ahora DEBE quedar en rojo: %s" % prueba)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    orden = sys.argv[1]
    if orden == "--respaldar":
        respaldar()
    elif orden == "--restaurar":
        restaurar()
    elif orden == "--comprobar":
        raise SystemExit(comprobar())
    elif orden == "--listar":
        listar()
    elif orden in MUTACIONES:
        mutar(orden)
    else:
        raise SystemExit("orden desconocida: %s\n%s" % (orden, __doc__))
