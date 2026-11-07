# -*- coding: utf-8 -*-
"""
================================================================================
 QUE SE VE EN LA FOTO QUE SUBIO EL TECNICO  --  31/10/2026
================================================================================

Pedido del usuario: que las fotos de evidencia se analicen con IA para ver si
la instalacion quedo bien, y que el supervisor pueda revisarlo.

ESTA ES LA ETAPA 1, Y SU ALCANCE ES DELIBERADO
-----------------------------------------------
Se analiza UNA foto cuando el tecnico la confirma, contra lo que su plantilla
ya declara que esa foto tiene que mostrar, y el resultado aparece como un
punto mas en la revision del cierre que ya existe.

Lo que NO hace, y no es que falte: no extrae estructura del texto (el
proveedor no puede devolver JSON -- medido el 02/10/2026, ver
`nucleo/canales/vision.py:22-33`), no arma dataset de entrenamiento, y no
tiene pantalla propia. Esas etapas se deciden con el numero que esta produce:
cuantas veces el analisis coincide con lo que el supervisor habria dicho.

LA DECISION QUE MANDA SOBRE TODO LO DEMAS
------------------------------------------
**El punto de IA NUNCA puede valer False.** Solo `True` o `None`.

`revision_del_cierre.py` convierte cualquier punto en `False` en el veredicto
NO_CERRAR, y ese veredicto ademas alimenta el cierre autonomo del Supervisor.
Si la IA pudiera decir que no, una opinion no verificada de un modelo
bloquearia el trabajo de un tecnico y frenaria un cierre que nadie reviso.

`None` ya significa REVISAR --"miralo vos"--, que es exactamente el alcance
que corresponde: la IA puede pedir atencion, nunca negar un cierre. Es
"crecer en alcance, no en autonomia" (CLAUDE.md §4) aplicado al caso.

Decidido el 31/10/2026 con esa recomendacion escrita, antes de la primera
linea de codigo, porque despues habria sido una correccion y no una decision.

DE DONDE SALE QUE TIENE QUE MOSTRAR CADA FOTO
----------------------------------------------
De `evidencias[].instrucciones` del esquema de la plantilla
(`campo/plantillas.py:507`): un texto libre, por requisito, por empresa, que
una persona escribe en español desde `/supervisor-noc/plantillas`. Ya existia.
No se invento ningun catalogo de prompts ni ninguna superficie de config
nueva: lo que varia por empresa ya estaba modelado como configuracion.

QUE PASA CON LOS FORMATOS QUE EL ANALIZADOR NO MIRA
----------------------------------------------------
El storage de campo acepta JPEG, PNG, WebP, HEIC y PDF
(`campo/services/storage.py:25-27`); `vision.es_imagen()` solo JPEG y PNG. Una
foto de iPhone (HEIC) se sube bien y el analizador la rechaza. **No se
convierte a ciegas** --mismo criterio que `vision.py:232-238`-- y tampoco se
trata como un fallo: se anota el motivo y el punto queda en `None`. Que
aparezca cuantas veces pasa es parte de lo que la etapa 1 viene a medir.

NO ESCRIBE NADA. Igual que `revision_del_cierre.py`: lee, decide y devuelve.
Quien persiste es `campo/tasks.py`.
================================================================================
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

#: Lo que el CRM le manda al motor y lo que entiende de vuelta.
ESTADO_OK = "procesado"
ESTADO_APAGADO = "apagado"

#: EL MOTIVO QUE NO SE GUARDA. Cuando la empresa no tiene esto habilitado no
#: pasa nada y no queda nada: ni fila, ni punto en la revision, ni foto que
#: haya salido del CRM. Es una cadena y no un booleano porque quien decide no
#: escribir es la tarea, y tiene que poder distinguir ESTE motivo de un fallo
#: de verdad -- un fallo si se guarda, para que se vea.
#:
#: Lo encontro el revisor de PII (31/10/2026): la primera version escribia
#: fila igual, y con eso `punto_de_la_revision` veia "ninguna se pudo mirar",
#: devolvia el punto en "no se sabe" y el veredicto pasaba a REVISAR. Con la
#: funcion APAGADA --que es el default y lo que va a produccion-- eso habria
#: frenado el cierre autonomo del Supervisor en toda orden con evidencia.
MOTIVO_APAGADO = "esta empresa no tiene habilitado que se miren las fotos"

#: Los formatos que el analizador del motor mira hoy. Se comprueba de ESTE
#: lado para no pagar un viaje HTTP por una foto que va a rechazar igual, y
#: para que el motivo que se guarda diga "HEIC" y no "no es JPEG ni PNG".
FIRMA_JPEG = bytes([0xFF, 0xD8, 0xFF])
FIRMA_PNG = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])

#: Tope del analizador (`nucleo/canales/vision.py::MAX_BYTES`). El storage de
#: campo admite 25 MB, asi que una evidencia valida puede pasarse. Se mide
#: aca, con su motivo, en vez de descubrirlo como un error del proveedor.
MAX_BYTES = 8 * 1024 * 1024

#: Cuanto se espera al motor. Mas que el timeout de vision (30 s) para que el
#: que corte sea el de alla y su motivo sea el de alla.
TIMEOUT_SEGUNDOS = 45


def formato_legible(contenido: bytes) -> str:
    """Como nombrar el formato en el motivo. No adivina: mira la firma."""
    if not contenido:
        return "vacio"
    if contenido[:3] == FIRMA_JPEG:
        return "JPEG"
    if contenido[:8] == FIRMA_PNG:
        return "PNG"
    if contenido[4:12] == b"ftypheic" or contenido[4:12] == b"ftypheix":
        return "HEIC"
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "WebP"
    if contenido[:4] == b"%PDF":
        return "PDF"
    return "desconocido"


def se_puede_mirar(contenido: bytes) -> str:
    """"" si se puede analizar, o el motivo por el que no. Falla cerrado."""
    if not contenido:
        return "el archivo llego vacio"
    if len(contenido) > MAX_BYTES:
        return (f"pesa {len(contenido) // 1024} KB y el analizador acepta "
                f"hasta {MAX_BYTES // 1024} KB")
    formato = formato_legible(contenido)
    if formato not in ("JPEG", "PNG"):
        return f"el analizador solo mira JPEG y PNG, y esto es {formato}"
    return ""


def que_tenia_que_mostrar(evidencia, instrucciones_propias: str = "") -> str:
    """El texto que la plantilla declara para ESTE requisito, o "".

    Sale de `evidencias[].instrucciones` del esquema de la version del tipo de
    trabajo. Si la plantilla no lo declara se manda el titulo, que al menos
    dice de que es la foto; si no hay ni eso, se manda vacio y el analizador
    describe lo que ve sin saber que se le pedia.
    """
    version = getattr(evidencia.orden_trabajo, "tipo_trabajo_version", None)
    esquema = (getattr(version, "esquema", None) or {}) if version else {}
    for e in esquema.get("evidencias") or []:
        if not isinstance(e, dict) or e.get("id") != evidencia.requisito_id:
            continue
        #  `instrucciones_propias` SOLO reemplaza el texto de la plantilla,
        #  nunca el envoltorio  --  06/11/2026
        #
        #  Existe para poder PROBAR una redaccion antes de guardarla. Y entra
        #  aca, y no en quien llama, porque el prefijo "Esta foto tenia que
        #  mostrar: <titulo>." es portante: las reglas 7 y 12 de
        #  `INSTRUCCION_EVIDENCIA` disparan solo "si te dijeron que tenia que
        #  mostrar", y la linea MUESTRA: es una de ellas.
        #
        #  La primera version del comando de prueba reemplazaba el pie
        #  COMPLETO. Probaba un prompt sin prefijo y guardaba uno con prefijo:
        #  podia decir que un texto funciona y que al guardarlo cambiara el
        #  veredicto. Un instrumento que mide otro camino que el que corre.
        instrucciones = (instrucciones_propias.strip()
                         or str(e.get("instrucciones") or "").strip())
        titulo = str(e.get("titulo") or "").strip()
        if instrucciones:
            return (f"Esta foto tenia que mostrar: {titulo or evidencia.requisito_id}. "
                    f"{instrucciones}")
        if titulo:
            return f"Esta foto tenia que mostrar: {titulo}."
        break
    return ""


def _motor() -> tuple[str, dict]:
    """La base del motor y las cabeceras. Un solo sitio que lo arma."""
    base = (os.environ.get("MOTOR_URL", "") or "http://motor:5000").rstrip("/")
    cabeceras = {}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token
    return base, cabeceras


def _esta_habilitado(tenant: str) -> bool:
    """Si ESTA empresa tiene habilitado que se miren sus fotos de evidencia.

    FALLA CERRADO en todos los frentes: si el motor no contesta, contesta
    cualquier otra cosa, o la respuesta no se entiende, la foto no sale. Eso
    es lo contrario de como falla la mayoria de las consultas de este
    proyecto, y es a proposito: esto no es un dato de servicio, es el
    consentimiento de una empresa para mandarle fotos de la casa de sus
    clientes a un tercero. No poder comprobarlo no es permiso.
    """
    import requests

    base, cabeceras = _motor()
    try:
        r = requests.get(f"{base}/interno/vision/evidencias-habilitada",
                         params={"tenant": tenant}, headers=cabeceras,
                         timeout=10)
        if r.status_code != 200:
            return False
        return bool((r.json() or {}).get("habilitada") is True)
    except Exception as e:                                       # noqa: BLE001
        logger.warning("inspeccion visual: no se pudo comprobar el "
                       "interruptor (%s)", type(e).__name__)
        return False


def _bytes_de(evidencia) -> bytes | None:
    """El binario de la evidencia, o None si no se pudo leer.

    Pasa por `CampoStorage.ruta_absoluta`, que es quien tapa el path
    traversal: la key sale de la base, pero leerla por otro camino seria
    saltearse la unica defensa que hay si alguna fila quedara con '../..'.
    """
    from campo.services.storage import CampoStorage

    try:
        ruta = CampoStorage.ruta_absoluta(evidencia.storage_key)
        if not ruta or not os.path.exists(ruta):
            return None
        with open(ruta, "rb") as f:
            return f.read()
    except Exception as e:                                       # noqa: BLE001
        logger.warning("inspeccion visual: no se pudo leer el archivo (%s)",
                       type(e).__name__)
        return None


def analizar(evidencia) -> dict:
    """Mira UNA evidencia. Devuelve que paso; no escribe.

    `{"estado", "texto", "motivo", "modelo", "segundos", "tokens"}`.

    NUNCA LEVANTA: el archivo del tecnico ya esta guardado (un hecho) y el
    analisis es otro. Que el segundo falle no puede convertir la subida en un
    500 -- mismo criterio que `cierre_en_isp.cerrar_ticket_al_validar`.
    """
    #  LA EMPRESA SALE DE LA ORDEN, NUNCA DEL ENTORNO (revisor de PII,
    #  31/10/2026). La primera version leia `MOTOR_TENANT`, que es UNA por
    #  instalacion: con dos empresas en la misma, la foto tomada dentro de la
    #  casa de un cliente de la B se habria mandado al proveedor porque la A
    #  tiene el interruptor encendido, y la factura habria caido en la A. El
    #  interruptor que este modulo justifica con "no es el mismo
    #  consentimiento" se habria evaluado contra el consentimiento de otra
    #  empresa. Hay una guarda que lo caza:
    #  `common/tests/test_motor_tenant_falla_cerrado.py`.
    from operaciones.areas_del_tenant import tenant_de

    tenant = tenant_de(evidencia.org)
    if not tenant:
        return _no("no se sabe a que empresa del motor pertenece esta orden: "
                   "no se le manda la foto a nadie")

    #  EL CONSENTIMIENTO SE PREGUNTA ANTES DE MOVER LOS BYTES (H1). La ruta
    #  de analisis tambien lo comprueba --ahi vive el control-- pero para
    #  entonces la foto ya salio del servicio que es su dueño. Preguntar
    #  primero cuesta un GET sin cuerpo.
    if not _esta_habilitado(tenant):
        return _no(MOTIVO_APAGADO)

    contenido = _bytes_de(evidencia)
    if contenido is None:
        return _no("no se pudo leer el archivo de la evidencia")

    motivo = se_puede_mirar(contenido)
    if motivo:
        return _no(motivo)

    import requests

    base, cabeceras = _motor()
    try:
        r = requests.post(
            f"{base}/interno/vision/analizar-evidencia",
            params={"tenant": tenant},
            files={"imagen": ("evidencia.jpg", contenido, "image/jpeg")},
            data={"pie": que_tenia_que_mostrar(evidencia)},
            headers=cabeceras, timeout=TIMEOUT_SEGUNDOS)
        cuerpo = r.json() if r.content else {}
        if not isinstance(cuerpo, dict):
            cuerpo = {}
    except Exception as e:                                       # noqa: BLE001
        logger.warning("inspeccion visual: no se pudo hablar con el motor (%s)",
                       type(e).__name__)
        return _no(f"no se pudo hablar con el motor ({type(e).__name__})")

    if r.status_code != 200:
        return _no(f"el motor contesto HTTP {r.status_code}")
    estado = str(cuerpo.get("estado") or "")
    if estado == ESTADO_APAGADO:
        return _no(str(cuerpo.get("motivo") or "el analisis esta apagado"))
    if estado != ESTADO_OK or not str(cuerpo.get("texto") or "").strip():
        return _no(str(cuerpo.get("error") or "el analizador no devolvio texto"))

    return {"estado": ESTADO_OK, "texto": str(cuerpo["texto"]).strip(),
            "motivo": "", "modelo": str(cuerpo.get("modelo") or ""),
            "segundos": cuerpo.get("segundos") or 0,
            "tokens": cuerpo.get("tokens") or 0}


def _no(motivo: str) -> dict:
    return {"estado": "", "texto": "", "motivo": motivo, "modelo": "",
            "segundos": 0, "tokens": 0}


# =============================================================================
#  EL PUNTO QUE VE EL SUPERVISOR
# =============================================================================

#: La clave del punto en `revision_del_cierre.revisar()`.
CLAVE = "fotos"


def punto_de_la_revision(orden):
    """El sexto punto, o None si no aplica.

    NUNCA DEVUELVE `ok=False`, y esa es la garantia entera de este modulo --
    ver el encabezado. Las tres salidas:

        None   esta empresa no lo tiene encendido, o no hay ninguna foto
               analizada: el punto no aparece y la revision queda como antes.
        True   se miraron todas las fotos y ninguna pidio atencion.
        None (punto)  hay algo que una persona tiene que mirar. El texto dice
               que, y el veredicto de la revision pasa a REVISAR.

    Que "no se pudo mirar" y "mirala" den los dos `None` es a proposito: las
    dos cosas significan lo mismo para quien decide --que el codigo no puede
    afirmar que esta bien-- y distinguirlas en el veredicto invitaria a que
    una de las dos empiece a contar como aprobacion.
    """
    from campo.models import AnalisisDeEvidencia

    analisis = list(AnalisisDeEvidencia.objects.filter(
        org=orden.org, evidencia__orden_trabajo=orden,
        vuelta=orden.vuelta).order_by("created_at"))
    if not analisis:
        return None

    mirados = [a for a in analisis if a.texto]
    sin_mirar = [a for a in analisis if not a.texto]
    if not mirados:
        #  Ninguna se pudo mirar. Se dice, y queda en "no se sabe": callarlo
        #  dejaria al supervisor creyendo que la IA las aprobo.
        return {"clave": CLAVE, "ok": None,
                "texto": (f"No se pudo mirar ninguna de las {len(sin_mirar)} "
                          f"fotos: {sin_mirar[0].motivo}")}

    con_atencion = [a for a in mirados if a.pide_atencion]
    if con_atencion or sin_mirar:
        partes = []
        if con_atencion:
            partes.append(f"{len(con_atencion)} de {len(mirados)} fotos piden "
                          f"una mirada")
        if sin_mirar:
            partes.append(f"{len(sin_mirar)} no se pudieron mirar")
        return {"clave": CLAVE, "ok": None,
                "texto": "Revisá las fotos: " + " y ".join(partes) + "."}

    return {"clave": CLAVE, "ok": True,
            "texto": f"Se miraron las {len(mirados)} fotos y nada llamó la atención."}
