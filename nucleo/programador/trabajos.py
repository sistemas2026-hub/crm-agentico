# -*- coding: utf-8 -*-
"""
================================================================================
 LOS TRABAJOS  --  lo que el scheduler sabe hacer, uno por funcion
================================================================================

QUE ES ESTE ARCHIVO
-------------------
Las implementaciones que 'registro.py' mapea. El registro es un diccionario
literal y congelado; aca viven las funciones que ese mapa nombra. La separacion
es a proposito: el mapa se lee de un vistazo para auditar QUE puede correr este
despliegue, y el detalle de COMO vive aparte.

Un trabajo recibe un 'Turno' --derivado de la base, no del coordinador-- y
devuelve un diccionario con lo que hizo. Si falla, levanta.

IMPORTAR ESTE MODULO NO HACE NADA
---------------------------------
Ni conexiones, ni hilos, ni lecturas de entorno al importar. Lo exige
'tests/test_p2_inerte.py', que comprueba que importar el paquete entero no
arranca nada, y lo exige el sentido comun: un import con efectos convierte
cualquier herramienta de inspeccion en un disparador.
================================================================================
"""

from __future__ import annotations

import os

from nucleo.observabilidad.registro import registrar

#: A donde se le pregunta al Supervisor. Vive en el entorno y no en el catalogo
#: del tenant porque es topologia de despliegue --cual backend-- y no una regla
#: de negocio de una empresa. Mismo criterio que 'MOTOR_URL' del lado del CRM.
VARIABLE_URL = "SUPERVISOR_LATIDO_URL"
URL_POR_DEFECTO = "http://backend:8000/api/operaciones/supervisor/latido/"

#: La credencial con la que el motor ya habla con el CRM. NO se crea una nueva:
#: este latido es una lectura mas por el mismo canal, y un token por trabajo
#: seria un secreto mas que rotar sin ninguna frontera nueva que lo justifique.
VARIABLE_TOKEN = "BOTTLECRM_API_TOKEN"

#: Cuanto se espera. Corto a proposito: 'detectar()' son consultas de lectura y
#: si tarda mas que esto el problema es el backend, no el latido. Un timeout
#: largo convierte un backend lento en un turno que ocupa su lease entero.
SEGUNDOS_TIMEOUT = 20


class LatidoFallido(Exception):
    """El Supervisor no contesto, o contesto algo que no se puede interpretar."""


def latido_supervisor(turno) -> dict:
    """
    Despierta al Supervisor y guarda QUE VIO. No le pide que haga nada.

    POR QUE ESTE ES EL PRIMER TRABAJO, Y NO LA IMPORTACION
    -----------------------------------------------------
    Porque demuestra el circuito entero --tick, reclamo, ejecucion, HTTP,
    respuesta, 'job_run'-- sin producir UN SOLO efecto: el endpoint del otro
    lado solo llama a 'supervisor.detectar()', que es lectura. Si el circuito
    estuviera mal cableado, lo peor que pasa es que no se lea nada.

    LO QUE DEVUELVE NO LLEVA DATOS DE CLIENTE  --  Y A DONDE VA DE VERDAD
    ---------------------------------------------------------------------
    Conteos por tipo de senal y nada mas. El endpoint ya filtra; aca se vuelve a
    acotar en vez de reenviar lo que venga, porque una respuesta que crezca del
    otro lado no tiene por que viajar entera.

    DONDE TERMINA ESTO, MEDIDO EL 02/10/2026: no en la base. 'job_run' no tiene
    columna de salida y los eventos del turno guardan solo metadatos del
    scheduler ('intento', 'fencing', 'worker'); 'puerta.finalizar' pasa un
    desenlace y un codigo de error, nada mas. Lo que se devuelve va al informe EN
    MEMORIA del tick ('ejecutor.py': resultado["trabajo"]) y lo que queda escrito
    es la linea de log de abajo.

    O sea: la base prueba QUE el latido corrio y que salio bien; CUANTAS senales
    vio vive en el log. Si hiciera falta que fuera durable, es una decision de
    diseno --una columna, o un evento del turno-- y no se toma desde aca.
    'tests/test_latido_extremo_a_extremo.py' afirma las dos direcciones, asi que
    el dia que alguien agregue ese 'output' la prueba lo obliga a revisar que se
    persiste.

    EL TENANT VIAJA Y SE COMPRUEBA DEL OTRO LADO
    --------------------------------------------
    'turno.organization_id' sale de la base, no del coordinador. Se manda como
    parametro y el backend lo compara contra la organizacion de la credencial:
    si no coinciden contesta 409 y no lee nada. Un turno de una empresa no puede
    leer la de al lado ni con el token equivocado.
    """
    import requests  # dentro: importar este modulo no debe traer la red

    url = (os.environ.get(VARIABLE_URL, "") or URL_POR_DEFECTO).strip()
    token = (os.environ.get(VARIABLE_TOKEN, "") or "").strip()
    if not token:
        #  Sin credencial no se intenta. Es un fallo del turno, no un exito
        #  vacio: "no se pudo preguntar" no es "no hay senales".
        raise LatidoFallido(
            f"falta {VARIABLE_TOKEN}: sin credencial no se le puede preguntar "
            f"al Supervisor, y un latido sin respuesta no es un latido en cero")

    try:
        r = requests.get(
            url,
            params={"organization_id": str(turno.organization_id)},
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/json"},
            timeout=SEGUNDOS_TIMEOUT)
    except Exception as e:                                       # noqa: BLE001
        #  Tipo y no texto: el texto de una excepcion de red trae la URL, y la
        #  URL puede traer el id de la organizacion. Misma regla que
        #  'nucleo/observabilidad' y que 'campo/services/lazo_isp.py'.
        registrar("programador", "el latido del Supervisor no salio",
                  job=turno.job_code, error=e)
        raise LatidoFallido(f"no se pudo preguntar: {type(e).__name__}") from None

    if r.status_code != 200:
        #  El cuerpo NO se incluye: un 500 de Django puede traer una pagina
        #  entera, y esto termina en una fila de 'job_run'.
        raise LatidoFallido(f"el Supervisor contesto HTTP {r.status_code}")

    try:
        cuerpo = r.json()
    except ValueError:
        raise LatidoFallido("la respuesta no es JSON") from None
    if not isinstance(cuerpo, dict):
        raise LatidoFallido("la respuesta no es un objeto JSON")

    #  Se vuelve a acotar aca: lo que se guarda son conteos, nunca la evidencia.
    vigentes = cuerpo.get("senales_vigentes")
    por_tipo = cuerpo.get("senales_por_tipo") or {}
    if not isinstance(vigentes, int) or not isinstance(por_tipo, dict):
        raise LatidoFallido("la respuesta no trae los conteos esperados")

    registrar("programador", "latido del Supervisor",
              job=turno.job_code, senales=vigentes)

    return {
        "senales_vigentes": vigentes,
        "senales_por_tipo": {str(k): int(v) for k, v in por_tipo.items()},
        "leido_en": str(cuerpo.get("leido_en") or ""),
        #  Se copia del backend en vez de afirmarlo aca: que no se escribio es
        #  una propiedad de lo que corrio del otro lado, no de este archivo.
        "escrituras": int(cuerpo.get("escrituras", 0)),
    }


#: A donde se le pide el sondeo de fuentes. Misma clase de dato que
#: VARIABLE_URL: topologia de despliegue, no regla de negocio de una empresa.
VARIABLE_URL_SONDEO = "SUPERVISOR_SONDEO_URL"
URL_SONDEO_POR_DEFECTO = "http://backend:8000/api/operaciones/supervisor/sondeo/"

#: Mas largo que el del latido, y con motivo: este turno consulta SEIS fuentes
#: y dos de ellas salen a un tercero por HTTP. Sigue siendo un tope: si tarda
#: mas que esto, el problema esta del otro lado y el turno tiene que soltar su
#: lease en vez de ocuparlo entero.
SEGUNDOS_TIMEOUT_SONDEO = 90


class SondeoFallido(Exception):
    """No se pudo pedir el sondeo, o la respuesta no se puede interpretar."""


def sondeo_de_fuentes(turno) -> dict:
    """
    Despierta al Supervisor para que consulte sus fuentes. No interpreta nada.

    QUE HACE ESTE TRABAJO, Y QUE NO
    -------------------------------
    Pide el sondeo y guarda CUANTAS fuentes se consultaron y en que estado quedo
    cada una. No decide si hay un problema, no crea nada y no sabe que es
    SmartOLT: para este modulo las fuentes son nombres que vienen en la
    respuesta. Quien sabe de fuentes es el Supervisor, del otro lado.

    POR QUE NO HAY UN TRABAJO POR FUENTE
    ------------------------------------
    Porque el nombre de un sistema externo no tiene por que estar escrito en el
    motor, que es generico. Un trabajo por fuente obligaria a que el registro de
    'nucleo/programador/' nombrara 'smartolt' y 'wisphub', y a que la frecuencia
    de cada una fuera una fila de catalogo mantenida por quien despliega.

    En su lugar: UN turno, y del otro lado cada fuente tiene su propia
    frecuencia en una fila editable. Asi SmartOLT puede ir cada 5 minutos y M03
    cada hora con un solo temporizador -- el de este scheduler, que sigue siendo
    el unico del sistema.

    UN FALLO ES UN FALLO
    --------------------
    Mismo criterio que el latido: si no se pudo pedir el sondeo, LEVANTA. "No se
    pudo preguntar" no es "ninguna fuente tiene novedades", y el dia que esa
    confusion entre a un tablero, el tablero dira que la red esta sana porque no
    puede verla.
    """
    import requests  # dentro: importar este modulo no debe traer la red

    url = (os.environ.get(VARIABLE_URL_SONDEO, "")
           or URL_SONDEO_POR_DEFECTO).strip()
    token = (os.environ.get(VARIABLE_TOKEN, "") or "").strip()
    if not token:
        raise SondeoFallido(
            f"falta {VARIABLE_TOKEN}: sin credencial no se le puede pedir el "
            f"sondeo, y un sondeo que no salio no es un sondeo en cero")

    try:
        r = requests.post(
            url,
            params={"organization_id": str(turno.organization_id)},
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/json"},
            timeout=SEGUNDOS_TIMEOUT_SONDEO)
    except Exception as e:                                       # noqa: BLE001
        registrar("programador", "el sondeo de fuentes no salio",
                  job=turno.job_code, error=e)
        raise SondeoFallido(f"no se pudo pedir: {type(e).__name__}") from None

    if r.status_code != 200:
        raise SondeoFallido(f"el Supervisor contesto HTTP {r.status_code}")

    try:
        cuerpo = r.json()
    except ValueError:
        raise SondeoFallido("la respuesta no es JSON") from None
    if not isinstance(cuerpo, dict):
        raise SondeoFallido("la respuesta no es un objeto JSON")

    sondeadas = cuerpo.get("sondeadas")
    por_fuente = cuerpo.get("por_fuente")
    if not isinstance(sondeadas, int) or not isinstance(por_fuente, dict):
        raise SondeoFallido("la respuesta no trae los conteos esperados")

    #  Se vuelve a acotar aca: de cada fuente se conserva su ESTADO y su
    #  frescura, no el resumen de datos que el Supervisor ya guardo en su propia
    #  tabla. Reenviarlo lo duplicaria en el log del motor sin que nadie lo use.
    estados = {}
    for nombre, detalle in por_fuente.items():
        if not isinstance(detalle, dict):
            continue
        estados[str(nombre)] = {
            "estado": str(detalle.get("estado") or ""),
            "frescura": str(detalle.get("frescura") or ""),
            "concluyente": bool(detalle.get("concluyente")),
        }

    registrar("programador", "sondeo de fuentes",
              job=turno.job_code, fuentes=sondeadas)

    return {
        "fuentes_sondeadas": sondeadas,
        "estados": estados,
        #  Cuantas NO permiten concluir nada. Es el numero que importa de un
        #  vistazo: si son todas, el Supervisor esta ciego aunque el turno haya
        #  salido bien.
        "no_concluyentes": sum(1 for e in estados.values()
                               if not e["concluyente"]),
    }
