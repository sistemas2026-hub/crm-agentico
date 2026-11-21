# -*- coding: utf-8 -*-
"""
================================================================================
 DE DONDE SALIO UNA IMAGEN DE GALERIA, Y DE CUANDO ES  --  21/11/2026
================================================================================
EL PEDIDO
---------
    «cuando el verifica una imagen mira la hora y el origen?»
    «se puede poner que revise eso de la fecha en que es el capture y si es de
     internet o capture del telefono»

La respuesta a la primera era que no. De una imagen elegida de la galeria se
sabia UNA cosa --que venia de la galeria-- y la hora que viajaba era la del
momento en que el tecnico la ELIGIO, no la de la imagen. Una captura de hoy y
una imagen bajada de una tienda llegaban con la misma cara, y lo unico que las
separaba era la opinion de un modelo («es una imagen de producto»), que el
mismo dia se vio fallar en las dos direcciones.

QUE HACE ESTO
-------------
Lee lo que la app declara de la imagen (`metadatos_captura`, ver
`apps/tecnicos-mobile/lib/features/ejecucion/origen_de_la_imagen.dart`) y dice,
SIN MODELO, dos cosas:

  1. QUE CLASE DE IMAGEN ES
       captura de ESTE telefono   mide exactamente lo que su pantalla
       captura de pantalla        solo lo dice el nombre del archivo
       foto guardada              trae adentro la marca de una camara
       origen desconocido         ninguna de las tres

  2. DE CUANDO ES, contra el dia en que se adjunto.

LO QUE NO AFIRMA, Y POR QUE
---------------------------
**Que una imagen «es de internet».** No hay forma de probarlo: solo se puede
decir lo que NO es. Por eso se llama «origen desconocido» y no otra cosa.

**Nada que devuelva una orden.** Todo esto lo declara el telefono, que el
tecnico controla: el reloj se cambia, el archivo se renombra. Sirve para ver
un descuido, no para probar un engaño. Asi que solo puede DEJAR EN DUDA --una
persona mira--, nunca frenar ni devolver. Es CLAUDE.md §10: se escala al
humano cuando la garantia no se puede dar en codigo.

SOLO LA EVIDENCIA POSITIVA LEVANTA UNA DUDA
-------------------------------------------
«No se pudo saber de cuando es» NO es una duda. La forma en que cada marca de
telefono nombra una captura no esta medida en campo, y tratar lo que no se
pudo leer como sospechoso marcaria todas las capturas de una marca que nombra
distinto. Levantan duda dos hechos, los dos afirmativos:

    la fecha SE LEYO y es de otro dia
    la app MIRO y la imagen no es captura ni foto de camara

EL DICT ES `DictField` SIN VALIDAR
----------------------------------
`metadatos_captura` llega del telefono tal cual (`campo/serializers.py`), asi
que aca cada valor se comprueba por tipo: un `"1080"`, un `True` donde va un
numero o un `1` donde va un booleano no cuentan. Lo que no pasa la
comprobacion es «no se sabe», nunca «si».

SIN LA VERSION, NO SE OPINA. Una app vieja manda `de_galeria` y nada mas: ahi
no es que la imagen sea de origen desconocido, es que nadie miro. Sin
`origen_version` se devuelve «elegida de la galeria» y ninguna duda.
================================================================================
"""
from __future__ import annotations

from datetime import date, datetime

CAPTURA_DE_ESTE_TELEFONO = "captura_de_este_telefono"
CAPTURA = "captura"
FOTO_GUARDADA = "foto_guardada"
DESCONOCIDO = "desconocido"
SIN_DATOS = "sin_datos"

#: Lo que se le dice a quien revisa, por clase de imagen.
TEXTOS = {
    CAPTURA_DE_ESTE_TELEFONO: "Captura de pantalla de este teléfono",
    CAPTURA: "Captura de pantalla",
    FOTO_GUARDADA: "Foto guardada en el teléfono",
    DESCONOCIDO: ("No es una captura de este teléfono ni una foto de su "
                  "cámara: no se sabe de dónde salió"),
    SIN_DATOS: "Elegida de la galería",
}


def _entero(valor):
    """Un entero positivo de verdad. `True` es un `int` en Python: se excluye
    a mano, porque un booleano donde va un ancho no es un ancho."""
    if isinstance(valor, bool) or not isinstance(valor, int):
        return None
    return valor if 0 < valor < 100_000 else None


def _fecha(valor):
    """`2026-11-21T09:23:01` o `2026-11-21`, sin zona. `(dia, tiene_hora)` o
    `None`. Estricto: es lo que la app escribe, y nada mas."""
    if not isinstance(valor, str):
        return None
    texto = valor.strip()
    for forma, con_hora in (("%Y-%m-%dT%H:%M:%S", True), ("%Y-%m-%d", False)):
        try:
            leida = datetime.strptime(texto, forma)
        except ValueError:
            continue
        if not 2000 <= leida.year <= 2099:
            return None
        return leida, con_hora
    return None


def _dia_en_que_se_adjunto(evidencia, zona) -> date | None:
    """El dia, en la hora de la empresa, en que el tecnico eligio la imagen.

    `capturada_en_cliente` primero: es el reloj del TELEFONO, el mismo que
    escribio la fecha en el nombre de la captura. Comparar dos lecturas del
    mismo reloj no depende de que ese reloj este en hora.
    """
    cuando = (getattr(evidencia, "capturada_en_cliente", None)
              or getattr(evidencia, "recibida_en_servidor", None))
    if cuando is None:
        return None
    try:
        return cuando.astimezone(zona).date() if zona else cuando.date()
    except Exception:                                            # noqa: BLE001
        return None


def leer(evidencia, zona=None) -> dict | None:
    """Que es esta imagen y de cuando, o `None` si no vino de la galeria.

    Devuelve `{"tipo", "texto", "duda", "fecha", "del_dia"}`. `texto` es la
    frase completa para quien revisa; `duda` es si una persona tiene que
    mirarla por esto.
    """
    metadatos = getattr(evidencia, "metadatos_captura", None)
    if not isinstance(metadatos, dict) or metadatos.get("de_galeria") is not True:
        return None

    if _entero(metadatos.get("origen_version")) is None:
        return {"tipo": SIN_DATOS, "texto": TEXTOS[SIN_DATOS], "duda": False,
                "fecha": None, "del_dia": None}

    ancho = _entero(metadatos.get("imagen_ancho"))
    alto = _entero(metadatos.get("imagen_alto"))
    p_ancho = _entero(metadatos.get("pantalla_ancho"))
    p_alto = _entero(metadatos.get("pantalla_alto"))
    medidas = None not in (ancho, alto, p_ancho, p_alto)
    #  De pie o acostada: una captura con el telefono girado mide lo mismo
    #  con los lados cambiados.
    mide_la_pantalla = medidas and {(ancho, alto)} <= {(p_ancho, p_alto),
                                                      (p_alto, p_ancho)}

    if mide_la_pantalla:
        tipo, leida = CAPTURA_DE_ESTE_TELEFONO, _fecha(
            metadatos.get("fecha_segun_nombre"))
    elif metadatos.get("nombre_dice_captura") is True:
        tipo, leida = CAPTURA, _fecha(metadatos.get("fecha_segun_nombre"))
    elif metadatos.get("exif_camara") is True:
        tipo, leida = FOTO_GUARDADA, _fecha(metadatos.get("exif_fecha"))
    else:
        tipo, leida = DESCONOCIDO, None

    adjuntada = _dia_en_que_se_adjunto(evidencia, zona)
    del_dia = None
    if leida is not None and adjuntada is not None:
        del_dia = leida[0].date() == adjuntada

    texto = TEXTOS[tipo]
    if tipo == DESCONOCIDO:
        #  Los numeros a la vista: si la comparacion falla en un telefono que
        #  mide distinto, esto es lo unico que deja verlo desde la oficina.
        if medidas:
            texto += (f" (la imagen mide {ancho}×{alto} y la pantalla "
                      f"{p_ancho}×{p_alto})")
    elif leida is None:
        texto += " · el archivo no dice de cuándo es"
    else:
        cuando = leida[0].strftime("%d/%m %H:%M" if leida[1] else "%d/%m")
        if del_dia is True:
            texto += f" · del {cuando}, el mismo día en que se adjuntó"
        elif del_dia is False:
            texto += (f" · es del {cuando} y se adjuntó el "
                      f"{adjuntada.strftime('%d/%m')}")
        else:
            texto += f" · del {cuando}"

    return {
        "tipo": tipo,
        "texto": texto,
        "duda": tipo == DESCONOCIDO or del_dia is False,
        "fecha": leida[0].isoformat() if leida else None,
        "del_dia": del_dia,
    }
