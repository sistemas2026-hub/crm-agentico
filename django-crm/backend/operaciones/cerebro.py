# -*- coding: utf-8 -*-
"""
================================================================================
 EL CEREBRO DEL SUPERVISOR  --  uno, para el chat y para el ciclo
================================================================================

QUE ES
------
El nucleo de razonamiento del Supervisor NOC. Dos funciones y dos formas:

    razonar()    el BUCLE: observa, consulta herramientas, vuelve a pensar.
                 Devuelve texto. Es lo que el chat necesita.
    concluir()   el VEREDICTO: lo mismo, pero el resultado vuelve ESTRUCTURADO
                 y validado en codigo. Es lo que el ciclo necesita.

Las dos comparten el bucle, el catalogo y la puerta al modelo. Eso es lo que
quiere decir "el mismo cerebro": no dos razonadores parecidos que se
desincronizan, sino uno con dos salidas.

POR QUE VIVE EN DJANGO Y NO EN EL MOTOR
---------------------------------------
Porque el motor NO lee las tablas del CRM -- lo dice su propio codigo en
'api.py::chat'-- y las herramientas del Supervisor leen justamente esas tablas:
situaciones, propuestas, decisiones, fuentes, coordinaciones. Y porque el ciclo
automatico ('correlacion.correr' -> 'supervisor.correr_ciclo') corre aqui. Un
cerebro alojado alla no podria servirle sin romper ese limite o duplicar
diecinueve herramientas.

El motor presta el MODELO, y nada mas: la credencial del proveedor vive solo
alla, y copiarla seria tener dos servicios con la misma clave.

LO QUE ESTE MODULO NO HACE, Y NO ES UNA PROMESA DEL PROMPT
----------------------------------------------------------
No ejecuta nada: el unico catalogo que ve es 'chat_herramientas', donde las
diecinueve LEEN. No hay una sola herramienta de escritura, asi que no hay por
donde. No toca la autonomia -- el veredicto no tiene campo para eso y
'autonomia.py' no se importa. No escribe una fila: quien persiste es quien
llama. No crea un segundo sistema de nada: reusa el catalogo, la memoria
('ConversacionSupervisor'), el vocabulario ('Senal') y los enums
('Riesgo', 'Confianza') que ya existen.

LAS CINCO GARANTIAS, Y DONDE VIVE CADA UNA
------------------------------------------
"No inventar informacion" no se le pide al modelo: se le quita la posibilidad.

  1. UN HECHO SIN FUENTE NO ES UN HECHO. Cada hecho declara de que herramienta
     salio, y se DESCARTA si nombra una que no se consulto en este
     razonamiento. Un hecho inventado no sobrevive a esa comparacion.
  2. UNA RECOMENDACION SIN HECHOS SE CAE. Recomendar sobre nada es la forma
     mas limpia de inventar, y es la que mas convence.
  3. HIPOTESIS Y CONFIANZA VIAJAN JUNTAS. Es la misma regla que el
     CheckConstraint 'situacion_hipotesis_con_confianza' impone en la tabla,
     aplicada antes de llegar a ella.
  4. LOS ENUMS SON CERRADOS. Un riesgo o una confianza que el modelo invente
     cae al valor mas conservador, no al que dijo.
  5. LO QUE FALTA SE DECLARA. Si una herramienta fallo, o si el modelo dice que
     le falta algo, el veredicto sale NO CONCLUYENTE -- y una lectura no
     concluyente no autoriza a afirmar que todo esta bien.

Y una sexta que no es del cerebro sino de su salida: el veredicto separa
HECHOS de INFERENCIAS de RIESGOS en tres campos distintos. No es cosmetica:
que esten juntos en un parrafo es como una sospecha se lee como una medicion.
================================================================================
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

from operaciones import chat_herramientas
from operaciones.situaciones_modelos import Confianza, Riesgo

#  La puerta al modelo. Es la MISMA que usa el chat desde P5: un envoltorio del
#  motor sobre 'cliente.chat()' que NO ejecuta herramientas -- las ejecuta este
#  modulo, que es el unico que sabe leer las tablas del CRM.
VARIABLE_URL = "SUPERVISOR_CHAT_URL"
URL_POR_DEFECTO = "http://motor:5000/interno/supervisor/chat"
SEGUNDOS_TIMEOUT = 150

#  Cuantas vueltas de herramienta puede dar un razonamiento.
#
#  TRES, y no diez, por lo mismo que en el chat: con el catalogo que hay, tres
#  alcanzan para la cadena mas larga util ("listar -> detalle -> timeline"), y
#  sin tope un modelo que se confunde pide la misma herramienta
#  indefinidamente mientras la empresa paga cada vuelta.
VUELTAS_MAXIMAS = 3

#  Tope del texto de un resultado que se le devuelve al modelo. Un resultado
#  enorme desplaza el resto del contexto y el modelo deja de ver la pregunta.
TOPE_RESULTADO = 6000


class ErrorCerebro(Exception):
    """No se pudo razonar. NO significa 'no hay nada': significa que no se supo."""


# =============================================================================
#  LA PUERTA AL MODELO
# =============================================================================

def _pedirle_al_modelo(mensajes: list[dict], tools: list) -> dict:
    """
    Le pide al motor que llame al modelo. Devuelve contenido y llamadas.

    FAIL-CLOSED CON EL TENANT: sin 'MOTOR_TENANT' no se pregunta. Ese parametro
    decide de QUE empresa es la config --y por tanto el modelo y quien paga-- y
    suponerlo usaria la de otra.
    """
    import requests

    url = (os.environ.get(VARIABLE_URL, "") or URL_POR_DEFECTO).strip()
    tenant = (os.environ.get("MOTOR_TENANT", "") or "").strip()
    if not tenant:
        raise ErrorCerebro(
            "falta MOTOR_TENANT: sin saber de qué empresa es esta consulta no "
            "se puede razonar")

    cabeceras = {"Content-Type": "application/json"}
    token = os.environ.get("MOTOR_SERVICE_TOKEN")
    if token:
        cabeceras["X-Servicio-Token"] = token

    try:
        r = requests.post(url, params={"tenant": tenant},
                          json={"mensajes": mensajes, "tools": tools},
                          headers=cabeceras, timeout=SEGUNDOS_TIMEOUT)
    except Exception as e:                                       # noqa: BLE001
        #  Tipo y no texto: el texto de una excepcion de red trae la URL.
        raise ErrorCerebro(f"no se pudo consultar el modelo: "
                           f"{type(e).__name__}") from None

    if r.status_code != 200:
        #  El cuerpo no se incluye: un 500 puede traer una pagina entera.
        raise ErrorCerebro(f"el modelo no contestó (HTTP {r.status_code})")
    try:
        cuerpo = r.json() or {}
    except ValueError:
        raise ErrorCerebro("la respuesta del modelo no es JSON") from None
    if not isinstance(cuerpo, dict):
        raise ErrorCerebro("la respuesta del modelo no es un objeto")
    return cuerpo


# =============================================================================
#  EL BUCLE  --  observar, consultar, volver a pensar
# =============================================================================

@dataclass
class Razonamiento:
    """
    Lo que produjo una pasada del bucle. Es un DATO, no un efecto.

    'consultadas' es la traza: que herramientas se pidieron y si fallaron. No
    guarda el RESULTADO de cada una a proposito -- puede traer datos
    operativos, y la traza quedaria con una copia vieja del mundo.
    """

    contenido: str = ""
    consultadas: list[dict] = field(default_factory=list)
    modelo: str = ""
    proveedor: str = ""
    vueltas: int = 0
    agotado: bool = False
    duracion_ms: int = 0

    @property
    def herramientas_usadas(self) -> set[str]:
        """Los nombres que SI se consultaron. La base de la garantia 1."""
        return {str(c.get("nombre") or "") for c in self.consultadas}

    @property
    def hubo_error_de_herramienta(self) -> bool:
        """Si alguna fallo. Dispara la garantia 5: no se puede concluir igual."""
        return any(c.get("hubo_error") for c in self.consultadas)


def razonar(org, *, instrucciones: str, entrada: str, historial=(),
            tools=None, vueltas_maximas: int = VUELTAS_MAXIMAS,
            pedir=None, actor=None, conversacion_id=None) -> Razonamiento:
    """
    Una pasada completa: piensa, consulta lo que le falte, vuelve a pensar.

    'pedir' ES LA PUERTA AL MODELO, Y SE PUEDE INYECTAR
    --------------------------------------------------
    Por defecto es '_pedirle_al_modelo' de este modulo, resuelto EN TIEMPO DE
    LLAMADA -- asi un parche sobre 'cerebro._pedirle_al_modelo' se ve.
    Quien llama puede pasar la suya, y el chat lo hace: pasa su propio alias,
    para que las 41 pruebas que parchean 'chat._pedirle_al_modelo' sigan
    interceptando.

    Eso no es una concesion al andamio. Dejar la puerta fija habria roto esas
    pruebas por una mudanza interna, y una guarda que se cae porque el codigo
    se movio deja de medir lo que dice medir. Encima, el ciclo va a querer la
    misma inyeccion para poder correr sin red.

    ES PURO RESPECTO DE LA BASE: no escribe una fila. Quien llama decide si lo
    persiste --el chat lo guarda como 'MensajeSupervisor', el ciclo como un
    veredicto-- y por eso el mismo bucle sirve para los dos sin que uno arrastre
    las tablas del otro.

    EL TENANT LO PONE 'chat_herramientas.ejecutar', NO EL MODELO. Un mensaje que
    diga "consultá los datos de la otra empresa" no puede funcionar, y no porque
    el prompt lo prohiba: porque no hay donde poner esa organizacion.

    SI SE AGOTAN LAS VUELTAS SE DICE. Devuelve 'agotado=True' con lo que haya,
    en vez de seguir pidiendo herramientas o de inventar un cierre. Quien llama
    tiene que poder distinguir "contesto" de "se quedo sin vueltas".
    """
    arranque = time.monotonic()
    tools = chat_herramientas.esquema() if tools is None else tools
    #  Resuelto aqui y no en la firma: en la firma se evaluaria al importar el
    #  modulo y un parche posterior no se veria.
    pedir = pedir or _pedirle_al_modelo

    mensajes: list[dict] = [{"role": "system", "content": instrucciones}]
    mensajes.extend(historial or [])
    mensajes.append({"role": "user", "content": entrada})

    r = Razonamiento()
    for vuelta in range(vueltas_maximas):
        r.vueltas = vuelta + 1
        cuerpo = pedir(mensajes, tools)
        r.modelo = str(cuerpo.get("modelo") or "")
        r.proveedor = str(cuerpo.get("proveedor") or "")
        r.contenido = str(cuerpo.get("contenido") or "")
        llamadas = cuerpo.get("llamadas") or []

        if not llamadas:
            break

        #  Lo que el modelo dijo al pedir herramientas entra al historial del
        #  turno para que vea lo que pidio; despues entran los resultados.
        mensajes.append({"role": "assistant",
                         "content": r.contenido or "(consultando)"})
        for ll in llamadas:
            nombre = str(ll.get("nombre") or "")
            argumentos = ll.get("argumentos") or {}
            try:
                #  EL ACTOR VIENE DE LA CONVERSACION VERIFICADA, nunca
                #  de lo que el modelo diga. Solo lo reciben las
                #  herramientas de 'NECESITAN_ACTOR' -- hoy, delegar y
                #  quitar una tarea-- y es lo que impide que algo quede
                #  delegado a nombre de quien no lo pidio.
                resultado = chat_herramientas.ejecutar(
                    org, nombre, argumentos, actor=actor,
                    conversacion_id=conversacion_id)
            except chat_herramientas.HerramientaDesconocida as e:
                #  Se le DICE que no existe, en vez de inventar un resultado o
                #  de abortar. Puede corregirse en la vuelta siguiente.
                resultado = {"error": "herramienta_desconocida",
                             "detalle": str(e)}
            except Exception as e:                               # noqa: BLE001
                resultado = {"error": "la_herramienta_fallo",
                             "detalle": type(e).__name__}

            r.consultadas.append({"nombre": nombre, "argumentos": argumentos,
                                  "hubo_error": "error" in resultado})
            mensajes.append({
                "role": "user",
                "content": (f"Resultado de {nombre}: "
                            + json.dumps(resultado, ensure_ascii=False,
                                         default=str)[:TOPE_RESULTADO]),
            })
    else:
        r.agotado = True

    r.duracion_ms = int((time.monotonic() - arranque) * 1000)
    return r


# =============================================================================
#  EL VEREDICTO  --  lo mismo, estructurado y validado
# =============================================================================

#  El vocabulario NO es nuevo: es el de 'deteccion.Senal', que ya es lo que
#  'correlacion.agrupar' y 'situaciones.abrir' saben consumir. Inventar otro
#  habria obligado a traducir en el medio, y una traduccion es donde se pierde
#  la diferencia entre un hecho y una sospecha.
CAMPOS_VEREDICTO = ("hechos", "inferencias", "riesgos", "riesgo", "hipotesis",
                    "confianza", "recomendacion", "falta")

CONTRATO = """\
Contestá SOLO con un objeto JSON, sin texto antes ni después, con esta forma:

{
  "hechos":        [{"dato": "...", "fuente": "nombre_de_la_herramienta"}],
  "inferencias":   ["lo que concluís de esos hechos"],
  "riesgos":       ["qué podría pasar si esto sigue así"],
  "riesgo":        "informativo|bajo|medio|alto|critico",
  "hipotesis":     "una causa POSIBLE, o cadena vacía si no tenés ninguna",
  "confianza":     "sin_hipotesis|baja|media|alta",
  "recomendacion": "qué conviene hacer, o cadena vacía",
  "falta":         ["qué dato te falta para estar seguro"]
}

REGLAS QUE SE VERIFICAN EN CÓDIGO, no son sugerencias:

- Cada HECHO declara la herramienta de la que salió. Un hecho cuya fuente no
  figure entre las que consultaste se DESCARTA.
- Una RECOMENDACIÓN sin hechos detrás se descarta entera.
- Una HIPÓTESIS sin confianza, o una confianza sin hipótesis, se descarta.
- Si te falta un dato, decilo en "falta". No lo supongas y no lo completes.
- No pongas en "hechos" algo que dedujiste: eso va en "inferencias".
"""


@dataclass
class Veredicto:
    """
    La conclusion del Supervisor, con cada cosa en su lugar.

    SEPARAR NO ES COSMETICA. 'hechos' es lo que una fuente midio; 'inferencias'
    es lo que se leyo de eso; 'riesgos' es lo que podria pasar. Juntos en un
    parrafo, una sospecha se lee como una medicion -- y es asi como un informe
    convence de algo que nadie comprobo.

    'concluyente' es la respuesta a "¿se puede afirmar algo con esto?". En False,
    quien llama NO puede leerlo como "todo bien": puede leerlo como "no se sabe".
    """

    hechos: list[dict] = field(default_factory=list)
    inferencias: list[str] = field(default_factory=list)
    riesgos: list[str] = field(default_factory=list)
    riesgo: str = Riesgo.INFORMATIVO
    hipotesis: str = ""
    confianza: str = Confianza.SIN_HIPOTESIS
    recomendacion: str = ""
    falta: list[str] = field(default_factory=list)
    concluyente: bool = True
    descartes: list[str] = field(default_factory=list)
    razonamiento: Razonamiento | None = None

    @property
    def vacio(self) -> bool:
        """Sin un solo hecho no hay veredicto, haya texto o no."""
        return not self.hechos

    def como_dict(self) -> dict:
        d = {c: getattr(self, c) for c in CAMPOS_VEREDICTO}
        d["concluyente"] = self.concluyente
        d["descartes"] = self.descartes
        return d


def _texto(v, tope: int = 500) -> str:
    return str(v or "").strip()[:tope]


def _lista_de_texto(v, tope: int = 12) -> list[str]:
    if not isinstance(v, list):
        return []
    return [_texto(x) for x in v if _texto(x)][:tope]


def validar(crudo, razonamiento: Razonamiento) -> Veredicto:
    """
    Convierte lo que dijo el modelo en un veredicto, descartando lo que no se
    sostiene. Es la funcion que hace que "no inventar" sea una garantia.

    SE PRUEBA SIN MODELO Y SIN RED a proposito: recibe el dict crudo y la traza.
    Asi cada descarte se puede afirmar sobre el EFECTO -- que el dato NO esta en
    la salida-- en vez de sobre la existencia de un 'if'.

    CADA DESCARTE SE ANOTA en 'descartes'. Un filtro silencioso es
    indistinguible de un modelo que no dijo nada, y la diferencia importa: uno
    es un modelo que invento y el otro es un modelo que se callo.
    """
    v = Veredicto(razonamiento=razonamiento)
    if not isinstance(crudo, dict):
        v.concluyente = False
        v.descartes.append("la respuesta del modelo no es un objeto JSON")
        return v

    usadas = razonamiento.herramientas_usadas if razonamiento else set()

    #  --- GARANTIA 1: un hecho sin fuente consultada no es un hecho ---------
    for h in (crudo.get("hechos") or [])[:20]:
        if not isinstance(h, dict):
            v.descartes.append("un hecho que no es un objeto {dato, fuente}")
            continue
        dato = _texto(h.get("dato"))
        fuente = _texto(h.get("fuente"), 80)
        if not dato:
            continue
        if not fuente:
            v.descartes.append(f"hecho sin fuente: {dato[:60]}")
            continue
        if fuente not in usadas:
            #  EL DESCARTE QUE MAS IMPORTA. El modelo nombro una herramienta
            #  que en este razonamiento no se consulto: ese dato no salio de
            #  ninguna medicion, salio de el.
            v.descartes.append(
                f"hecho atribuido a '{fuente}', que no se consultó: "
                f"{dato[:60]}")
            continue
        v.hechos.append({"dato": dato, "fuente": fuente})

    v.inferencias = _lista_de_texto(crudo.get("inferencias"))
    v.riesgos = _lista_de_texto(crudo.get("riesgos"))
    v.falta = _lista_de_texto(crudo.get("falta"))

    #  --- GARANTIA 4: los enums son cerrados, y caen al lado conservador ---
    riesgo = _texto(crudo.get("riesgo"), 20)
    if riesgo in Riesgo.TODOS:
        v.riesgo = riesgo
    elif riesgo:
        v.descartes.append(f"riesgo inválido '{riesgo}': queda informativo")

    confianza = _texto(crudo.get("confianza"), 20)
    hipotesis = _texto(crudo.get("hipotesis"))

    #  --- GARANTIA 3: hipotesis y confianza viajan juntas -------------------
    #  La misma regla que el CheckConstraint de la tabla, aplicada antes de
    #  llegar a ella: asi el veredicto nunca produce algo que la base rechace.
    if hipotesis and confianza in (Confianza.BAJA, Confianza.MEDIA,
                                   Confianza.ALTA):
        v.hipotesis = hipotesis
        v.confianza = confianza
    elif hipotesis:
        v.descartes.append(
            f"hipótesis sin confianza válida (dijo '{confianza}'): se descarta "
            f"la hipótesis, no se le pone una confianza inventada")
    elif confianza in (Confianza.BAJA, Confianza.MEDIA, Confianza.ALTA):
        v.descartes.append(
            f"confianza '{confianza}' sin hipótesis que la sostenga")

    #  --- GARANTIA 2: una recomendacion sin hechos se cae ------------------
    recomendacion = _texto(crudo.get("recomendacion"), 1000)
    if recomendacion and v.hechos:
        v.recomendacion = recomendacion
    elif recomendacion:
        v.descartes.append(
            "recomendación sin ningún hecho que la sostenga: recomendar sobre "
            "nada es la forma más limpia de inventar")

    #  --- GARANTIA 5: lo que falta se declara, y vuelve no concluyente -----
    if v.vacio:
        v.concluyente = False
        if not v.falta:
            v.falta.append("no se obtuvo ningún hecho de ninguna herramienta")
    if v.falta:
        v.concluyente = False
    if razonamiento and razonamiento.hubo_error_de_herramienta:
        v.concluyente = False
        fallidas = sorted({str(c.get("nombre"))
                           for c in razonamiento.consultadas
                           if c.get("hubo_error")})
        v.falta.append("no contestaron: " + ", ".join(fallidas))
    if razonamiento and razonamiento.agotado:
        v.concluyente = False
        v.falta.append("se agotaron las vueltas de consulta sin cerrar")

    return v


def concluir(org, *, instrucciones: str, entrada: str, historial=(),
             tools=None, vueltas_maximas: int = VUELTAS_MAXIMAS,
             pedir=None) -> Veredicto:
    """
    Razona y devuelve un VEREDICTO validado. Es lo que el ciclo puede persistir.

    El contrato de salida se le pide al modelo en 'instrucciones' + 'CONTRATO',
    pero lo que lo GARANTIZA es 'validar': si el modelo contesta prosa, o
    inventa una fuente, o recomienda sin hechos, el veredicto sale recortado y
    NO CONCLUYENTE. El prompt orienta; el codigo decide.

    Un fallo del modelo NO se traduce en un veredicto vacio y concluyente -- que
    seria "no hay nada que reportar", la peor lectura posible. Levanta.
    """
    r = razonar(org, instrucciones=instrucciones + "\n\n" + CONTRATO,
                entrada=entrada, historial=historial, tools=tools,
                vueltas_maximas=vueltas_maximas, pedir=pedir)
    return validar(_json_de(r.contenido), r)


def _json_de(texto: str):
    """
    Saca el objeto JSON de la respuesta, tolerando el envoltorio habitual.

    DeepSeek a veces lo envuelve en un bloque de codigo aunque se le pida que
    no (visto en vivo, y ya anotado en 'nucleo/modelo/motor.py'). Tolerar eso
    no es aflojar el contrato: lo que no se tolera es el CONTENIDO inventado, y
    de eso se ocupa 'validar'. Si no hay JSON, devuelve None y el veredicto sale
    no concluyente.
    """
    t = (texto or "").strip()
    if t.startswith("```"):
        t = t.split("```")[1] if "```" in t[3:] else t[3:]
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    t = t.strip()
    if not t:
        return None
    try:
        return json.loads(t)
    except ValueError:
        #  Un ultimo intento: el primer objeto entre llaves. No se "arregla" el
        #  JSON ni se adivina: si no parsea, no hay veredicto.
        i, j = t.find("{"), t.rfind("}")
        if i == -1 or j <= i:
            return None
        try:
            return json.loads(t[i:j + 1])
        except ValueError:
            return None


# =============================================================================
#  D2 · EL ARMADOR DE CONTEXTO  --  cuatro origenes, una entrada
# =============================================================================
#
#  POR QUE DEVUELVE TEXTO
#  ----------------------
#  La entrada del cerebro es texto porque la entrada del modelo es texto. Lo que
#  NO se hace es dejar que cada origen arme el suyo: entonces habria cuatro
#  lugares decidiendo que sabe el Supervisor, y ninguno seria el verdadero.
#
#  CERO SQL NUEVO, Y NO ES UNA META DE ESTILO
#  ------------------------------------------
#  Todo sale de lecturas que ya existen y ya estan probadas:
#  'turno.resumen_de_turno' (doce preguntas, cada una con su procedencia),
#  'contexto_propuesta.contexto_de' y el propio catalogo. Una consulta nueva aqui
#  seria una segunda definicion de "que esta pasando" que se desincroniza de la
#  que mira el tablero.
#
#  LA LISTA DE CAMPOS ES BLANCA, Y ESE ES EL PUNTO
#  -----------------------------------------------
#  'contexto_de' devuelve 'cliente' y 'asunto'. El primero es el NOMBRE de una
#  persona; el segundo lo trae pegado -- WispHub guarda el asunto como
#  "Asunto - Cliente" (ver la skill 'wisphub-api'). Con lista negra, un campo
#  nuevo del contexto entraria al prompt por defecto y nadie se enteraria. Con
#  blanca, lo que no esta declarado no viaja.

#: Lo unico de 'contexto_propuesta' que puede llegar al modelo. Topologia y
#: plazos, nunca quien vive ahi.
CAMPOS_DE_CONTEXTO = ("zona", "tecnico", "ticket_externo", "proveedor_externo",
                      "orden_numero", "sla_estado", "sla_minutos",
                      "origen_creado_en", "caso_cerrado")

#: Lo que se excluye a proposito, nombrado para que el descarte sea revisable.
CAMPOS_QUE_NO_VIAJAN = ("cliente", "asunto")


def _bloque(titulo: str, cuerpo: str) -> str:
    return f"\n== {titulo} ==\n{cuerpo.strip()}\n" if cuerpo.strip() else ""


def contexto_para(org, *, conversacion=None, situacion=None, evento=None,
                  propuesta=None, horas_turno=None) -> str:
    """
    El contexto operativo para una consulta, segun de donde venga.

    CUATRO ORIGENES, Y LA DIFERENCIA ES SOLO LA ENTRADA. Eso es lo que hace que
    el cerebro sea uno: no sabe si lo llamo una persona, el ciclo o un evento.

    Se puede llamar sin ningun origen: devuelve el panorama del turno, que es el
    contexto minimo honesto -- "esto es lo que hay" -- en vez de nada.

    NO INVENTA Y NO COMPLETA. Si una fuente no informa, el resumen de turno lo
    dice como DESCONOCIDO con su motivo, y eso viaja tal cual: que el modelo vea
    "no se pudo saber" es el unico modo de que no concluya que todo esta bien.
    """
    from operaciones import turno as turno_mod

    partes: list[str] = []

    #  El panorama siempre. Trae las doce preguntas con su procedencia, y es la
    #  unica lectura que ya distingue OBSERVADO de INFERIDO de DESCONOCIDO.
    resumen = turno_mod.resumen_de_turno(org, horas=horas_turno)
    partes.append(_bloque("PANORAMA DEL TURNO", _resumen_legible(resumen)))

    if situacion is not None:
        partes.append(_bloque("LA SITUACION", _situacion_legible(situacion)))

    if propuesta is not None:
        partes.append(_bloque("LA PROPUESTA",
                              _propuesta_legible(org, propuesta)))

    if conversacion is not None and conversacion.situacion_id:
        partes.append(_bloque("LA SITUACION DE ESTA CONVERSACION",
                              _situacion_legible(conversacion.situacion)))

    if evento is not None:
        #  Un evento es un dict suelto: lo escribe quien lo detecto. Se acota y
        #  se marca como lo que es -- una senal, no un diagnostico.
        partes.append(_bloque(
            "EL EVENTO QUE DISPARO ESTA CONSULTA (es una senal, no un "
            "diagnostico)",
            json.dumps(evento, ensure_ascii=False, default=str)[:2000]))

    partes.append(_bloque("APRENDIZAJE PREVIO", aprendizaje_relevante(org)))

    return "".join(p for p in partes if p)


def _resumen_legible(resumen: dict) -> str:
    """
    El resumen de turno en texto, CON la procedencia de cada bloque.

    La procedencia no se pierde en la traduccion: es lo que impide que el modelo
    lea un INFERIDO como una medicion. Un bloque DESCONOCIDO viaja con su
    motivo, no como un cero.
    """
    lineas = []
    t = resumen.get("turno") or {}
    lineas.append(f"ventana: {t.get('horas')} h hasta {t.get('hasta')}")
    for clave, valor in resumen.items():
        if not isinstance(valor, dict) or "procedencia" not in valor:
            continue
        datos = valor.get("datos")
        if datos is None:
            lineas.append(f"[{valor['procedencia']}] {clave}: NO SE PUDO SABER"
                          f" -- {valor.get('nota', '')}")
            continue
        resumido = {k: v for k, v in datos.items()
                    if not isinstance(v, (list, dict))}
        lineas.append(f"[{valor['procedencia']}] {clave}: "
                      + json.dumps(resumido, ensure_ascii=False,
                                   default=str)[:400])
    return "\n".join(lineas)


def _situacion_legible(s) -> str:
    """
    La ficha de una situacion. Sin datos de cliente -- la misma seleccion que
    'turno._ficha', por el mismo motivo.
    """
    return (f"codigo: {s.codigo}\n"
            f"titulo: {s.titulo}\n"
            f"estado: {s.estado}   riesgo: {s.riesgo}\n"
            f"detectada: {s.detectada_en.isoformat()}\n"
            f"afectados contados: {s.afectados_contados}\n"
            f"hipotesis: {s.hipotesis or '(ninguna)'}   "
            f"confianza: {s.confianza}\n"
            f"verificada: {'si' if s.verificacion else 'NO'}")


def _propuesta_legible(org, p) -> str:
    """
    Una propuesta con su contexto operativo, por lista BLANCA de campos.

    'contexto_de' trae 'cliente' y 'asunto' y los dos quedan afuera: ver
    'CAMPOS_QUE_NO_VIAJAN'.
    """
    from operaciones import contexto_propuesta

    ctx = (contexto_propuesta.contexto_de(org, [p]) or {}).get(str(p.id), {})
    visible = {k: ctx.get(k) for k in CAMPOS_DE_CONTEXTO
               if ctx.get(k) not in (None, "")}
    return (f"accion propuesta: {p.accion_propuesta}\n"
            f"motivo: {p.motivo}\n"
            f"tipo de senal: {p.tipo_senal}   prioridad: {p.prioridad}\n"
            f"estado: {p.estado}\n"
            "contexto: " + json.dumps(visible, ensure_ascii=False,
                                      default=str)[:600])


# =============================================================================
#  D4 · APRENDIZAJE  --  historia, nunca el estado de hoy
# =============================================================================

def aprendizaje_relevante(org, *, desde=None, hasta=None) -> str:
    """
    Lo que ya se supo de decisiones anteriores, para que el cerebro lo tenga.

    ES LECTURA, Y DE HISTORIA. No hay aprendizaje autonomo en esta fase: el
    cerebro no escribe una leccion ni se califica. Lo unico que cambia es que
    deja de razonar como si nunca hubiera pasado nada antes.

    POR QUE EL TEXTO LO DICE EXPLICITAMENTE
    ---------------------------------------
    Porque la memoria es justo donde un dato viejo se lee como actual. "Tres
    falsos positivos en caidas de PON" es informacion util para dudar; NO es
    informacion sobre si hay una caida ahora. El bloque lo aclara en la unica
    forma que el modelo lee, que es texto, y la garantia de abajo es que aqui
    NO se consulta ninguna fuente actual: solo 'AprendizajeSupervisor' y
    'DecisionSupervisor', que son registros de lo que YA se concluyo.
    """
    from operaciones import gobierno

    r = gobierno.resumen_de_aprendizaje(org, desde=desde, hasta=hasta)
    if not r.get("aprendizajes") and not r.get("decisiones"):
        return ("no hay aprendizaje registrado todavia: no se puede ponderar "
                "nada por experiencia previa, y eso no es lo mismo que no "
                "haber tenido errores")

    por_tipo = {k: v for k, v in (r.get("por_tipo") or {}).items() if v}
    return (
        "ESTO ES HISTORIA, NO EL ESTADO DE HOY. Sirve para ponderar cuanto "
        "confiar en una lectura parecida; NO dice nada sobre lo que esta "
        "pasando ahora. Para lo que cambia, consulta la herramienta.\n"
        f"lecciones a favor: {r.get('a_favor')}   "
        f"en contra: {r.get('en_contra')}\n"
        f"por tipo: {json.dumps(por_tipo, ensure_ascii=False)}\n"
        f"decisiones: {r.get('decisiones')}   "
        f"con desenlace: {r.get('decisiones_con_desenlace')}   "
        f"sin desenlace: {r.get('decisiones_sin_desenlace')}")




# =============================================================================
#  D2.b · ANTECEDENTES  --  que paso la ultima vez con ESTA misma condicion
# =============================================================================
#
#  POR QUE ESTO ES LO QUE SEPARA UN AGENTE DE UN MOTOR DE CICLO
#  ------------------------------------------------------------
#  Hasta aqui el cerebro razonaba sobre una señal AISLADA: cada ciclo empezaba
#  de cero. 'aprendizaje_relevante' le daba estadistica general --cuantas
#  lecciones a favor, cuantas en contra-- pero nada sobre ESTE caso.
#
#  Un motor reacciona a lo que ve ahora. Un agente retoma un hilo: "ya propuse
#  esto, la persona lo acepto, y no funciono". Eso es lo que hace que la
#  segunda vez no sea igual a la primera, y es exactamente lo que falta para
#  que el ciclo deje de ser un bucle sin memoria.
#
#  La llave es 'huella_condicion', que ya existe y ya se usa para deduplicar:
#  dos propuestas con la misma huella son la MISMA condicion detectada otra
#  vez. Nada nuevo que inventar -- lo que faltaba era leerlo.
#
#  LO QUE NO VIAJA, Y ES LA MISMA REGLA DE SIEMPRE
#  -----------------------------------------------
#  Ni el nombre del cliente ni el asunto del ticket, por 'CAMPOS_QUE_NO_VIAJAN'.
#  Lo que viaja es QUE se propuso, QUE decidio una persona y COMO salio -- que
#  es lo unico que cambia el razonamiento. La zona y el numero de orden sirven y
#  no son datos personales; el nombre de quien decidio tampoco viaja, porque un
#  antecedente no mejora por saber quien firmo.

TOPE_ANTECEDENTES = 3


def antecedentes_de(org, huella: str, *, limite: int = TOPE_ANTECEDENTES) -> str:
    """
    Lo que ya se propuso para esta misma condicion, y como termino.

    Devuelve texto listo para el prompt, o "" si es la primera vez -- y el vacio
    tambien es informacion: que no haya antecedentes significa condicion nueva,
    no condicion sana.

    NUNCA LEVANTA. Si la consulta falla se devuelve "" y el cerebro razona sin
    antecedentes, que es como razonaba antes de que esto existiera. Mismo
    criterio que el resto de este camino: degradar, no romper.
    """
    if not (huella or "").strip():
        return ""
    try:
        from operaciones.gobierno_modelos import DecisionSupervisor
        from operaciones.models import PropuestaSupervisor

        previas = (PropuestaSupervisor.objects
                   .filter(org=org, huella_condicion=huella)
                   .order_by("-created_at")[:max(1, int(limite))])
        previas = list(previas)
        if not previas:
            return ""

        decisiones = {
            str(d.propuesta_id): d for d in
            DecisionSupervisor.objects.filter(
                org=org, propuesta_id__in=[p.id for p in previas])
        }
    except Exception:                                        # noqa: BLE001
        return ""

    lineas = []
    for p in previas:
        d = decisiones.get(str(p.id))
        cuando = p.created_at.strftime("%d/%m %H:%M") if p.created_at else "?"
        if d is None:
            cierre = f"estado: {p.estado}, sin decision registrada"
        else:
            cierre = f"una persona {d.tipo}"
            if d.resultado and d.resultado != "pendiente":
                cierre += f", y el resultado fue: {d.resultado}"
                if d.resultado_evidencia:
                    cierre += f" ({d.resultado_evidencia[:160]})"
            else:
                cierre += ", sin desenlace todavia"
            if d.correccion:
                cierre += f". Correccion anotada: {d.correccion[:200]}"
        lineas.append(f"- {cuando}: se propuso '{p.accion_propuesta}'. {cierre}")

    return (
        "Esta MISMA condicion ya se detecto antes. Lo que paso:\n"
        + "\n".join(lineas)
        + "\n\nSi una propuesta igual ya se rechazo o no funciono, decilo y "
          "proponé algo distinto o explicá por que insistis. Repetir lo que ya "
          "fallo sin nombrarlo es el error que estos antecedentes existen para "
          "evitar."
    )
# =============================================================================
#  D3 · VEREDICTO -> SENAL  --  para que el ciclo pueda persistirlo
# =============================================================================
#
#  CUIDADO CON EL NOMBRE 'Veredicto', QUE EN ESTE PROYECTO SIGNIFICA DOS COSAS
#  ---------------------------------------------------------------------------
#    cerebro.Veredicto                  la conclusion estructurada del cerebro
#                                       (hechos, inferencias, riesgos, ...)
#    situaciones_seguimiento.Veredicto  como EVOLUCIONA una situacion
#                                       (estable, empeora, mejora, ...)
#
#  No se cruzan en ninguna funcion y por eso no se renombra ninguno, pero quien
#  lea 'veredicto' en este proyecto tiene que saber que hay dos. Es la misma
#  advertencia que CLAUDE.md §11.1 hace sobre la palabra "agente".


def senal_de_veredicto(veredicto, *, fuente: str, tipo_situacion: str,
                       dimension: str, clave_dimension: str, afectados=None,
                       ahora=None):
    """
    Convierte un veredicto del cerebro en una 'Senal' que el ciclo ya sabe
    consumir. Devuelve None cuando no corresponde.

    UN VEREDICTO NO CONCLUYENTE NO PRODUCE SENAL, y es la regla que importa.
    Una lectura que no cierra --porque una fuente no contesto, porque se
    agotaron las vueltas, o porque el propio modelo dijo que le falta un dato--
    no puede abrir una situacion. Abrirla seria convertir "no se sabe" en "esta
    pasando esto", que es exactamente lo que el resto del sistema esta armado
    para que no ocurra.

    TAMPOCO UN VEREDICTO SIN HECHOS. Sin un solo hecho con fuente consultada no
    hay nada que afirmar, haya texto o no.

    EL PAR (HIPOTESIS, CONFIANZA) YA ES VALIDO POR CONSTRUCCION
    -----------------------------------------------------------
    'validar()' lo garantiza y 'Senal.__init__' lo exige levantando un
    ValueError. Son la MISMA regla escrita dos veces en dos capas, y por eso no
    pueden contradecirse: lo que el cerebro produce es siempre algo que la senal
    acepta, y lo que la senal acepta es siempre algo que la base acepta
    (CheckConstraint 'situacion_hipotesis_con_confianza').

    NO CREA NINGUNA ACCION EXTERNA. Devuelve un dato. Quien lo persista pasa por
    'correlacion.agrupar' y, si amerita, por 'situaciones_propuestas.proponer' --
    y de ahi para adelante manda la frontera, que esta funcion no conoce.
    """
    from django.utils import timezone

    from operaciones.deteccion import Senal

    if veredicto is None or not veredicto.concluyente or veredicto.vacio:
        return None

    #  El HECHO es lo que una fuente midio, y va con su procedencia pegada. Si
    #  hubiera que elegir una sola frase de este modulo, es esta: un hecho nunca
    #  viaja sin de donde salio.
    hecho = "; ".join(f"{h['dato']} (fuente: {h['fuente']})"
                      for h in veredicto.hechos)[:1000]

    #  La evidencia conserva la traza de CADA hecho por separado, para que
    #  despues se pueda discutir uno sin discutir todos.
    momento = ahora or timezone.now()
    evidencia = [{"fuente": h["fuente"], "dato": h["dato"],
                  "observado_en": momento.isoformat()}
                 for h in veredicto.hechos]

    return Senal(
        fuente=fuente,
        tipo_situacion=tipo_situacion,
        dimension=dimension,
        clave_dimension=clave_dimension,
        hecho=hecho,
        relacion="",
        #  Las inferencias del cerebro son INTERPRETACION, no hecho. Ese reparto
        #  es el que hace que una sospecha no se lea como una medicion.
        interpretacion="; ".join(veredicto.inferencias)[:1000],
        riesgo=veredicto.riesgo,
        hipotesis=veredicto.hipotesis,
        confianza=veredicto.confianza,
        recomendacion=veredicto.recomendacion,
        afectados=afectados or [],
        evidencia=evidencia,
        observada_en=momento,
        concluyente=True,
        datos={"riesgos_previstos": veredicto.riesgos,
               "falta": veredicto.falta,
               "descartes": veredicto.descartes,
               "origen": "cerebro"},
    )


# =============================================================================
#  FASE 2 · VEREDICTO -> ANALISIS  --  enriquecer una propuesta, sin tocarla
# =============================================================================
#
#  POR QUE HACE FALTA OTRA TRADUCCION SI YA HAY 'senal_de_veredicto'
#  -----------------------------------------------------------------
#  Porque hay DOS ciclos y DOS clases 'Senal', y no son la misma cosa:
#
#    correlacion.correr      -> deteccion.Senal   -> SituacionOperativa
#    supervisor.correr_ciclo -> supervisor.Senal  -> PropuestaSupervisor
#
#  'senal_de_veredicto' sirve al primero. El segundo no consume una Senal del
#  cerebro: consume el DICT que devuelve 'analizar()'. Son dos traducciones
#  porque son dos destinos, no por duplicacion.
#
#  LO QUE EL CEREBRO PUEDE TOCAR, Y POR QUE ES TAN POCO
#  ---------------------------------------------------
#  Solo 'motivo' e 'impacto'. Lo demas lo decide el codigo:
#
#    prioridad      la calcula '_prioridad' sumando enteros. PRD §12.5: el
#                   modelo traduce lenguaje a parametros y redacta; no suma.
#    nivel          subirlo seria darse permiso. Y 'registrar_propuesta' lo
#                   toma de aqui SIN acotarlo, asi que dejarlo pasar seria
#                   dejar que el modelo pida nivel 3.
#    accion_propuesta  es el texto que una persona acepta o rechaza. Si cambiara
#                   por turno, la misma condicion se leeria distinta cada vez.
#    huella, tipo_senal, origen_*   son la IDENTIDAD de la condicion. Tocarlos
#                   rompe la deduplicacion: la misma condicion volveria a
#                   proponerse mañana con la huella vieja.
#
#  POR QUE NO 'observaciones', QUE ERA LO ESPERABLE
#  -----------------------------------------------
#  Porque ese campo esta EXCLUIDO de
#  'supervisor.CAMPOS_QUE_ESCRIBE_EL_SUPERVISOR' a proposito: M09-C prohibe que
#  el Supervisor señale personas, y la unica forma de que no lo haga es que
#  ninguna ruta suya escriba ahi. Hay una prueba viva que lo afirma
#  ('test_m09f::test_la_ia_no_puede_sugerir_un_responsable'). 'impacto' SI esta
#  declarado, y es el campo que responde "que pasa si esto no se atiende" --
#  justo donde van los riesgos que el cerebro previo.
#
#  LA GARANTIA ES ESTRUCTURAL, NO DISCIPLINADA
#  -------------------------------------------
#  La salida se arma copiando el analisis original y sobreescribiendo SOLO las
#  dos claves permitidas. Un campo protegido no puede cambiar porque no hay
#  camino por donde: no depende de que quien escriba esto se acuerde.

#: Lo unico que el cerebro puede enriquecer de una propuesta.
CAMPOS_QUE_EL_CEREBRO_ENRIQUECE = ("motivo", "impacto")


def analisis_de_veredicto(veredicto, analisis: dict) -> dict:
    """
    Devuelve una COPIA del analisis con lo que el cerebro aporto.

    Si el veredicto no sirve --None, no concluyente, o sin hechos-- devuelve el
    analisis TAL CUAL. "No se sabe" no mejora una propuesta: la propuesta
    deterministica ya era correcta sin el cerebro, y agregarle una lectura que
    no cierra solo la haria menos legible.

    LA HIPOTESIS SE CONSERVA COMO HIPOTESIS. Va con su confianza pegada y
    rotulada; nunca se convierte en una afirmacion. Lo mismo con los hechos:
    cada uno viaja con la herramienta de la que salio, asi que en tres meses se
    puede saber si una frase del motivo fue una medicion o una lectura.
    """
    base = dict(analisis or {})
    if veredicto is None or not veredicto.concluyente or veredicto.vacio:
        return base

    #  --- el motivo: lo deterministico primero, lo del cerebro rotulado ----
    partes = [str(base.get("motivo") or "").strip()]

    hechos = "; ".join(f"{h['dato']} (fuente: {h['fuente']})"
                       for h in veredicto.hechos)
    if hechos:
        partes.append(f"HECHOS OBSERVADOS: {hechos}")
    if veredicto.inferencias:
        partes.append("INTERPRETACION: " + "; ".join(veredicto.inferencias))
    if veredicto.hipotesis:
        #  Con su confianza, siempre. Las dos formas de separarlas son las dos
        #  formas de presentar una sospecha como un hecho.
        partes.append(f"HIPOTESIS (confianza {veredicto.confianza}): "
                      f"{veredicto.hipotesis}")
    if veredicto.falta:
        #  Lo que NO se pudo saber va en el motivo, no en una nota al pie: es
        #  lo que decide si quien lee puede confiar en el resto.
        partes.append("FALTA POR SABER: " + "; ".join(veredicto.falta))
    if veredicto.recomendacion:
        #  Se ANOTA, no reemplaza 'accion_propuesta'. La accion que una persona
        #  acepta sigue siendo la deterministica.
        partes.append(f"EL SUPERVISOR SUGIERE ADEMAS: {veredicto.recomendacion}")

    motivo = "\n".join(p for p in partes if p)[:4000]

    #  --- el impacto: los riesgos previstos, detras de lo que ya habia ------
    impacto = str(base.get("impacto") or "").strip()
    if veredicto.riesgos:
        previstos = "RIESGO PREVISTO: " + "; ".join(veredicto.riesgos)
        impacto = f"{impacto}. {previstos}" if impacto else previstos

    #  LA SOBREESCRITURA ES EXPLICITA Y ACOTADA. Se parte de 'base' --que ya es
    #  una copia del analisis deterministico-- y se cambian SOLO estas dos
    #  claves. Un campo protegido no puede moverse por una ruta que no existe.
    enriquecido = dict(base)
    enriquecido["motivo"] = motivo
    enriquecido["impacto"] = impacto[:500]

    #  Y se comprueba, aqui mismo, que nada mas cambio. No es paranoia: es la
    #  diferencia entre una garantia y una intencion. Si alguna vez alguien
    #  agrega una clave a la lista de arriba sin pensarlo, esto lo frena.
    for clave, valor in base.items():
        if clave in CAMPOS_QUE_EL_CEREBRO_ENRIQUECE:
            continue
        if enriquecido.get(clave) != valor:
            raise AssertionError(
                f"el cerebro modifico '{clave}', que no puede tocar")

    return enriquecido
