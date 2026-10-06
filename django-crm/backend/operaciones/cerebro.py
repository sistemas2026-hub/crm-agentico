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
            tools=None, vueltas_maximas: int = VUELTAS_MAXIMAS) -> Razonamiento:
    """
    Una pasada completa: piensa, consulta lo que le falte, vuelve a pensar.

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

    mensajes: list[dict] = [{"role": "system", "content": instrucciones}]
    mensajes.extend(historial or [])
    mensajes.append({"role": "user", "content": entrada})

    r = Razonamiento()
    for vuelta in range(vueltas_maximas):
        r.vueltas = vuelta + 1
        cuerpo = _pedirle_al_modelo(mensajes, tools)
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
                resultado = chat_herramientas.ejecutar(org, nombre, argumentos)
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
             tools=None, vueltas_maximas: int = VUELTAS_MAXIMAS) -> Veredicto:
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
                vueltas_maximas=vueltas_maximas)
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
