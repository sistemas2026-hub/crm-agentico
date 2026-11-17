# -*- coding: utf-8 -*-
"""
================================================================================
 EL INSTRUMENTO TIENE QUE CONTAR LO MISMO QUE EL CAMINO QUE MIDE  --  17/11/2026
================================================================================
`que_foto_frena` existe para decidir si vale construir el arreglo de la foto
del daño. Esa decisión se toma mirando su número, así que un instrumento que
cuenta mal es peor que no medir: produce una decisión con la confianza de un
dato.

LA PRIMERA VERSION DE ESTAS GUARDAS ESTABA EN VERDE Y NO PROTEGIA NADA
-----------------------------------------------------------------------
Las cuatro pasaban, y las cuatro mutaciones que las contradicen SOBREVIVIERON
(medido el 17/11/2026, con un control que confirmó que el archivo mutado sí
se estaba leyendo). Los tres motivos, que son tres formas distintas de
escribir una prueba que no mide:

  a) `"0%" in "100%"` ES VERDADERO. Dos guardas comparaban la tasa por
     subcadena y pasaban con cualquier número terminado en 0. Ahora se compara
     la columna exacta.

  b) EL CASO NO LLEGABA AL CODIGO. La guarda del «no prometer un cierre»
     usaba una orden sin reporte, que da veredicto NO_CERRAR y sale del
     comando antes de la línea que la guarda creía medir. Ahora deja la orden
     en REVISAR con DOS interrogantes, que es el caso real.

  c) LA MUTACION ERA INOCUA EN ESE CASO. Contar todas las filas no infla nada
     cuando el intento fallido es el PRIMERO: los fallidos no cuentan como
     miradas de todos modos. El caso que distingue es el inverso --la buena
     primero y el reintento fallido después-- y es el que estaba faltando.

QUE AFIRMAN AHORA
------------------
El EFECTO sobre los dos números que deciden: la tasa impresa y cuántas
órdenes dice que se destrabarían.
================================================================================
"""
from __future__ import annotations

import io

import pytest
from django.core.management import call_command

pytestmark = pytest.mark.django_db

ESQUEMA = {
    "pasos": [],
    "campos": [
        {"id": "potencia_al_llegar", "tipo": "decimal",
         "titulo": "Medición al llegar", "reglas": {"min": -60, "max": -8}},
        {"id": "potencia_al_salir", "tipo": "decimal",
         "titulo": "Medición al salir", "reglas": {"min": -60, "max": -8}},
    ],
    "evidencias": [
        {"id": "dano_encontrado", "tipo": "foto",
         "titulo": "Daño encontrado", "obligatorio": True},
        {"id": "trabajo_terminado", "tipo": "foto",
         "titulo": "Trabajo terminado", "obligatorio": True},
    ],
}

#: CADA MARCA EN SU RENGLON, COMO LAS ESCRIBE EL MODELO. Las reglas 11, 12 y
#: 13 de `nucleo/canales/vision.py` piden «una última línea, sola», y
#: `es_de_catalogo` busca la marca AL PRINCIPIO DE UNA LINEA, a propósito
#: (nota del 09/11/2026: la palabra «catálogo» aparece en la prosa de estas
#: mismas fotos). La primera versión de este fixture las ponía todas en un
#: renglón: `ATENCION` se detectaba igual --usa `rfind` sobre todo el texto--
#: y `CATALOGO` no, así que la guarda del catálogo medía otra cosa.
VIO_EL_DANO = ("Conector coaxial metálico unido a un cable negro; la funda "
               "presenta un desgarro.\nCATALOGO: no\nMUESTRA: si\nATENCION: si")
TODO_BIEN = ("Caja de empalme cerrada y fijada a la pared.\n"
             "CATALOGO: no\nMUESTRA: si\nATENCION: no")
ES_DE_CATALOGO = ("Router sobre fondo blanco, sin nada alrededor.\n"
                  "CATALOGO: si\nMUESTRA: si\nATENCION: si")
NO_SE_PUDO = "no se pudo hablar con el motor (ReadTimeout)"


def _orden(org, numero, *, dano=VIO_EL_DANO, terminado=TODO_BIEN,
           fallo_antes_del_dano=False, fallo_despues_del_dano=False,
           confirmo_sin_material=True):
    """Una orden terminada en campo, con sus dos fotos y su reporte.

    `terminado=""` deja esa foto sin mirar (un intento fallido y nada más).
    `confirmo_sin_material=False` deja el punto del material en «?», que es
    como se arma una orden en REVISAR por DOS motivos a la vez.
    """
    from campo.analisis_de_evidencia import AnalisisDeEvidencia
    from campo.models import (EventoTrabajo, EvidenciaTrabajo, OrdenTrabajo,
                              WorkType, WorkTypeVersion)
    from campo.tasks import _pide_atencion

    wt = WorkType.objects.create(org=org, codigo=f"qf{numero}",
                                 nombre="Soporte", labor="correctivo")
    v = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA, esquema=ESQUEMA)
    respuestas = {"potencia_al_llegar": "-50.0", "potencia_al_salir": "-21.0",
                  "solucion": "se corta y se prepara el conector",
                  "servicio_validado": "Hecho"}
    orden = OrdenTrabajo.objects.create(
        org=org, numero=numero, tipo_trabajo_version=v,
        cliente_nombre="MARIO SABANAGRANDE",
        estado_operativo=OrdenTrabajo.COMPLETADA_CAMPO,
        estado_validacion=OrdenTrabajo.PENDIENTE,
        origen_sistema="manual", contexto={"ticket": f"9{numero}"},
        datos=dict(respuestas), vuelta=1)

    def _fallo(ev):
        AnalisisDeEvidencia.objects.create(
            org=org, evidencia=ev, vuelta=1,
            origen=AnalisisDeEvidencia.IA, texto="", motivo=NO_SE_PUDO)

    def _foto(requisito, texto, *, antes=False, despues=False):
        ev = EvidenciaTrabajo.objects.create(
            org=org, orden_trabajo=orden, requisito_id=requisito, vuelta=1,
            sha256=f"{requisito}{numero}".ljust(64, "x")[:64],
            storage_key=f"k/{requisito}{numero}", nombre_original="m.jpg",
            mime_type="image/jpeg", bytes=1,
            estado_archivo=EvidenciaTrabajo.RECIBIDO)
        if antes:
            _fallo(ev)
        if texto:
            #  `pide_atencion` LO ESCRIBE EL CODIGO, no se deduce del texto
            #  al leer. Se copia el único camino que escribe esa fila de
            #  verdad (`campo/tasks.py:597`); la primera versión de este
            #  fixture la dejaba en False y las guardas fallaban por eso.
            AnalisisDeEvidencia.objects.create(
                org=org, evidencia=ev, vuelta=1,
                origen=AnalisisDeEvidencia.IA, texto=texto,
                pide_atencion=_pide_atencion(texto))
        else:
            _fallo(ev)
        if despues:
            _fallo(ev)
        return ev

    _foto("dano_encontrado", dano,
          antes=fallo_antes_del_dano, despues=fallo_despues_del_dano)
    _foto("trabajo_terminado", terminado)

    datos = {"vuelta": 1, "respuestas": respuestas}
    if confirmo_sin_material:
        datos["sin_material_confirmado"] = True
    EventoTrabajo.objects.create(org=org, orden=orden, tipo="cierre_campo",
                                 datos=datos)
    return orden


def _correr(org) -> str:
    salida = io.StringIO()
    call_command("que_foto_frena", org=str(org.id), stdout=salida)
    return salida.getvalue()


def _tasa_de(salida: str, titulo: str):
    """La tasa impresa para ese requisito, o None si no está en la tabla.

    SE COMPARA LA COLUMNA, NO POR SUBCADENA. `"0%" in "100%"` es verdadero,
    y dos guardas de la primera versión pasaban por eso con el número
    invertido.
    """
    for linea in salida.splitlines():
        if titulo in linea and linea.rstrip().endswith("%"):
            return linea.split()[-1]
    return None


# ---------------------------------------------------------------------------
#  1) LA TASA NOMBRA LA FOTO QUE LEVANTA ATENCION, Y NO LA OTRA
# ---------------------------------------------------------------------------

def test_la_tasa_senala_la_foto_del_dano_y_no_la_otra(org_a):
    """El caso que motivó el comando: de dos fotos miradas, la del daño
    levanta atención y la del trabajo terminado no."""
    _orden(org_a, 8801)

    salida = _correr(org_a)

    assert _tasa_de(salida, "Daño encontrado") == "100%", salida
    assert _tasa_de(salida, "Trabajo terminado") == "0%", salida


# ---------------------------------------------------------------------------
#  2) LAS DOS MITADES DEL REINTENTO  (el bug de la OT #200, en el instrumento)
# ---------------------------------------------------------------------------

def test_una_foto_releida_cuenta_con_la_ultima_mirada(org_a):
    """Primero falló, después se leyó bien: cuenta como mirada, con atención.
    Un instrumento que arrastrara el fallo diría que no se pudo mirar."""
    _orden(org_a, 8802, fallo_antes_del_dano=True)

    assert _tasa_de(_correr(org_a), "Daño encontrado") == "100%"


def test_un_reintento_fallido_borra_la_mirada_buena_anterior(org_a):
    """La otra mitad, y la que mata la mutación: se leyó bien y DESPUES el
    reintento falló. El punto real se queda con la última --no se pudo
    mirar-- así que esa foto no es una mirada ni una atención.

    Si el instrumento contara todas las filas, la foto aparecería con 100%
    de atención donde la pantalla dice «no se pudieron mirar», y el número
    con el que se decide estaría inflado por casos que el arreglo propuesto
    ni siquiera toca.
    """
    _orden(org_a, 8803, fallo_despues_del_dano=True)

    assert _tasa_de(_correr(org_a), "Daño encontrado") is None, _correr(org_a)


# ---------------------------------------------------------------------------
#  3) UNA FOTO DE CATALOGO NO ES ATENCION
# ---------------------------------------------------------------------------

def test_una_imagen_de_catalogo_no_cuenta_como_atencion(org_a):
    """El punto real las separa desde el 09/11. Si el instrumento las
    sumara, contaría como «la foto del daño frena» un caso que en la pantalla
    dice otra cosa, y el arreglo propuesto no lo tocaría."""
    _orden(org_a, 8804, dano=ES_DE_CATALOGO)

    assert _tasa_de(_correr(org_a), "Daño encontrado") == "0%"


# ---------------------------------------------------------------------------
#  4) EL IMPACTO NO PROMETE UN CIERRE QUE NO VA A PASAR
# ---------------------------------------------------------------------------

def test_la_orden_del_caso_se_cuenta_como_destrabable(org_a):
    """El control positivo: sin esto, una guarda que exige «no se cuenta»
    pasaría también con un comando que no cuenta nunca nada."""
    _orden(org_a, 8805)

    salida = _correr(org_a)

    assert "se cerrarían solas" in salida, salida
    assert "#8805" in salida, salida


def test_una_orden_frenada_tambien_por_otro_punto_no_se_promete(org_a):
    """La foto del daño está en atención Y el material quedó en «?». La orden
    sigue frenada aunque la foto deje de frenar, así que contarla sería
    inflar el número con órdenes que no se van a cerrar."""
    _orden(org_a, 8806, confirmo_sin_material=False)

    salida = _correr(org_a)

    assert "se cerrarían solas" not in salida, salida
    assert "quedan frenadas por otro punto" in salida, salida


# ---------------------------------------------------------------------------
#  5) UNA FOTO QUE NO SE PUDO MIRAR NO ES UNA FOTO QUE FRENA
# ---------------------------------------------------------------------------

def test_si_ademas_hay_una_foto_sin_mirar_no_se_promete_el_cierre(org_a):
    """La del daño pide atención, pero la otra no se pudo mirar. Sacar la
    atención no destraba la orden: el punto sigue en «?» por la que falta.

    Es el ruido conocido del motor --3 ReadTimeout en 16 análisis-- y
    confundirlo con el problema estructural es justo lo que este comando
    existe para evitar.
    """
    _orden(org_a, 8807, terminado="")

    salida = _correr(org_a)

    assert "se cerrarían solas" not in salida, salida
    assert "por otra cosa" in salida, salida
