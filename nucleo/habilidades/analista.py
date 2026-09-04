# -*- coding: utf-8 -*-
"""
================================================================================
 ANALISTA DE HABILIDADES  --  detecta que procedimiento le falta a un agente
================================================================================

El problema que resuelve
------------------------
Escribir habilidades a mano tiene un techo obvio: alguien tiene que darse
cuenta de que hacen falta. Y no se da cuenta -- porque el sintoma no se ve
leyendo una conversacion suelta. Una conversacion que termina en un humano se
lee como "bueno, se escalo". Treinta conversaciones que terminan en un humano
por el MISMO motivo, en el MISMO rol, son un procedimiento faltante, y eso solo
se ve contando.

Es la misma leccion que ya esta escrita en CLAUDE.md sobre los casos dorados:
tres bugs estuvieron rotos horas y ninguno se veia leyendo la respuesta. Este
modulo aplica esa leccion a otra cosa -- lo que el agente NO sabe hacer.

De donde sale la evidencia -- de la operacion real, nunca de un supuesto
--------------------------------------------------------------------------
Tres senales, en orden de fuerza:

1. ESCALADAS REPETIDAS POR EL MISMO MOTIVO en el mismo rol. Es la mas fuerte:
   son casos donde el agente explicitamente no pudo, y quedo registrado por que.

2. EL AGENTE DIJO QUE NO TIENE EL PROCEDIMIENTO. El prompt le ordena decirlo
   con esas palabras cuando no tiene una guia cargada (ver "No inventar" en
   nucleo/recuperacion/prompt.py) en vez de improvisar. Esa orden convirtio
   una falla silenciosa en una frase buscable -- y esto la busca.

3. HABILIDAD CARGADA Y LA CONVERSACION IGUAL ESCALO. No falta un procedimiento:
   el que hay esta mal escrito. Sale de asistente.habilidad_usos cruzado contra
   las escaladas. Propone una VERSION nueva, no una habilidad nueva.

Lo que NO hace, a proposito
---------------------------
No activa nada. Toda propuesta nace con estado='propuesta' y no entra al prompt
de ningun agente hasta que un humano la apruebe. No es prudencia decorativa: un
procedimiento aprobado es lo que el agente va a seguir "al pie de la letra",
asi que aprobarlo automaticamente seria dejar que el sistema se escriba a si
mismo las reglas que despues obedece.

Tampoco propone sin un piso de casos (MINIMO_CASOS). Con dos conversaciones no
hay patron, hay dos conversaciones -- y una propuesta por cada cosa que pasa
dos veces convierte la cola de revision en ruido, que es la forma mas rapida de
que nadie la mire.

Y cada propuesta guarda su evidencia: cuantos casos, de que rol, con que
motivo, y los identificadores de las conversaciones. Sin eso, "el sistema
sugiere esta habilidad" es un oraculo; con eso, quien aprueba puede ir a leer
los casos que la motivaron y decidir con datos.

Este modulo es generico: ningun rol, motivo ni empresa aparece aca. Todo sale
de la base del tenant.
================================================================================
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field

from nucleo.modelo import cliente
from nucleo.persistencia.db import sesion

# Por debajo de esto no hay patron, hay casualidad. Es el numero que separa
# "esto pasa" de "esto paso": con 2 casos cualquier conversacion rara genera
# una propuesta, y una cola de revision llena de ruido no la lee nadie.
MINIMO_CASOS = 3

# Cuanto historial mirar. Un procedimiento que hizo falta hace medio año puede
# haber dejado de hacer falta -- cambio el proceso, se agrego una herramienta.
DIAS_POR_DEFECTO = 30

# Tope de conversaciones que se le muestran al modelo por cada patron. El
# analisis no necesita leerlas todas: necesita ver de que se trata. Y un
# modelo saturado de texto deja de seguir instrucciones (PRD seccion 12.5,
# confirmacion empirica de la regla 2).
MUESTRAS_POR_PATRON = 5

# Mas generoso que cliente.TIMEOUT_SECUNDARIO (20 s) a proposito: esto no corre
# dentro de un turno, nadie esta esperando la respuesta del otro lado. Redactar
# un procedimiento entero son bastantes mas tokens que resumir una conversacion.
TIMEOUT_REDACCION = 90.0

# Las frases con que el prompt le ordena al agente admitir que no sabe. Son la
# senal (2). Se buscan como texto porque es exactamente el texto que el prompt
# manda decir -- ver "No inventar" en nucleo/recuperacion/prompt.py. Si ese
# bloque cambia de redaccion, esta lista tiene que cambiar con el.
FRASES_SIN_PROCEDIMIENTO = (
    "no tengo el procedimiento",
    "no tengo un procedimiento",
    "no cuento con el procedimiento",
)


@dataclass
class Patron:
    """Un hueco detectado: mismo rol, misma causa, varias veces."""
    rol: str
    senal: str                  # escalada_repetida | sin_procedimiento | habilidad_insuficiente
    motivo: str
    n_casos: int
    conversaciones: list[str] = field(default_factory=list)
    muestras: list[str] = field(default_factory=list)
    # Solo en 'habilidad_insuficiente': que procedimiento no alcanzo.
    codigo_habilidad: str | None = None


def _filas(cur) -> list[dict]:
    return [dict(f) for f in cur.fetchall()]


def detectar(tenant: str, dias: int = DIAS_POR_DEFECTO,
             minimo: int = MINIMO_CASOS) -> list[Patron]:
    """Los huecos que la operacion real muestra, sin llamar a ningun modelo.

    Separado de proponer() a proposito: detectar es SQL puro y determinista, y
    se puede mirar solo, sin gastar una llamada al modelo ni escribir nada.
    Es lo que permite responder "¿que le falta a este agente?" y decidir
    despues si vale la pena redactar algo.
    """
    patrones: list[Patron] = []
    with sesion(tenant) as (cur, org):
        # (1) Escaladas repetidas por el mismo motivo, en el mismo rol.
        cur.execute(
            """select rol_efectivo as rol, motivo_escalamiento as motivo,
                      count(*) as n, array_agg(id::text) as ids
                 from asistente.conversations
                where organization_id = %s
                  and escalada_a_humano
                  and motivo_escalamiento is not null
                  and rol_efectivo is not null
                  and creado_en > now() - make_interval(days => %s)
                group by rol_efectivo, motivo_escalamiento
               having count(*) >= %s
                order by count(*) desc""",
            (org, dias, minimo))
        for f in _filas(cur):
            patrones.append(Patron(rol=f["rol"], senal="escalada_repetida",
                                   motivo=f["motivo"], n_casos=f["n"],
                                   conversaciones=list(f["ids"] or [])))

        # (2) El agente admitio no tener el procedimiento. Una fila por
        # conversacion; se agrupan por rol, porque el "motivo" aca no es una
        # etiqueta sino lo que la persona vino a pedir -- eso lo resume el
        # modelo despues, mirando las muestras.
        like = " or ".join(["lower(m.contenido) like %s"] * len(FRASES_SIN_PROCEDIMIENTO))
        cur.execute(
            f"""select c.rol_efectivo as rol, count(distinct c.id) as n,
                       array_agg(distinct c.id::text) as ids
                  from asistente.messages m
                  join asistente.conversations c on c.id = m.conversation_id
                 where m.organization_id = %s and m.rol = 'assistant'
                   and c.rol_efectivo is not null
                   and m.creado_en > now() - make_interval(days => %s)
                   and ({like})
                 group by c.rol_efectivo
                having count(distinct c.id) >= %s""",
            (org, dias, *[f"%{f}%" for f in FRASES_SIN_PROCEDIMIENTO], minimo))
        for f in _filas(cur):
            patrones.append(Patron(
                rol=f["rol"], senal="sin_procedimiento",
                motivo="el agente dijo no tener el procedimiento",
                n_casos=f["n"], conversaciones=list(f["ids"] or [])))

        # (3) Se cargo una habilidad y la conversacion escalo igual. No falta
        # un procedimiento: el que hay no alcanza.
        cur.execute(
            """select u.rol, h.codigo, count(distinct c.id) as n,
                      array_agg(distinct c.id::text) as ids
                 from asistente.habilidad_usos u
                 join asistente.habilidades h on h.id = u.habilidad_id
                 join asistente.conversations c on c.id = u.conversation_id
                where u.organization_id = %s and c.escalada_a_humano
                  and u.creado_en > now() - make_interval(days => %s)
                group by u.rol, h.codigo
               having count(distinct c.id) >= %s""",
            (org, dias, minimo))
        for f in _filas(cur):
            patrones.append(Patron(
                rol=f["rol"], senal="habilidad_insuficiente",
                motivo=f"se cargo {f['codigo']} y aun asi escalo",
                n_casos=f["n"], conversaciones=list(f["ids"] or []),
                codigo_habilidad=f["codigo"]))

        # Muestras de conversacion para los patrones encontrados. Solo lo que
        # escribio la PERSONA: alcanza para entender que vino a pedir, y evita
        # que el modelo redacte el procedimiento copiando lo que el agente ya
        # contesto mal -- que es justamente el caso que se esta corrigiendo.
        for p in patrones:
            if not p.conversaciones:
                continue
            cur.execute(
                """select contenido from asistente.messages
                    where organization_id = %s and rol = 'user'
                      and conversation_id = any(%s::uuid[])
                      and contenido is not null and length(contenido) > 10
                    order by creado_en limit %s""",
                (org, p.conversaciones[:MUESTRAS_POR_PATRON],
                 MUESTRAS_POR_PATRON))
            p.muestras = [f["contenido"][:400] for f in _filas(cur)]
    return patrones


PROMPT_REDACCION = """\
Sos un analista de procesos de un proveedor de internet. Se detecto que un \
agente de atencion no supo resolver un tipo de caso, y hay que escribirle el \
procedimiento.

DATOS DEL PATRON
Rol del agente: {rol}
Senal: {senal}
Motivo: {motivo}
Casos en los ultimos {dias} dias: {n_casos}

LO QUE ESCRIBIERON LAS PERSONAS EN ESOS CASOS
{muestras}

HERRAMIENTAS QUE ESE AGENTE TIENE DE VERDAD
{herramientas}

Escribi un procedimiento. Reglas, todas obligatorias:

1. Los pasos solo pueden usar las herramientas de la lista de arriba, por su \
nombre exacto. Si el caso necesita algo que no esta en esa lista, el \
procedimiento tiene que terminar pasando el caso a un colaborador humano -- \
nunca inventes una herramienta.
2. No inventes datos de la empresa: ni precios, ni plazos, ni politicas, ni \
nombres de sistemas que no aparezcan arriba. Si hace falta un dato asi, el \
paso dice que hay que consultarlo, no lo afirma.
3. "cuando_usarla" es la CONDICION OBSERVABLE que dispara el procedimiento, \
escrita para que otro agente decida si aplica sin leer los pasos. Empieza \
directo con la condicion, sin la palabra "cuando".
4. Los pasos son imperativos, numerados, concretos y en orden. Nada de \
consejos generales tipo "se empatico".
5. Todo en español, sin markdown.

Responde SOLO un objeto JSON, sin texto alrededor:
{{"nombre": "...", "cuando_usarla": "...", "pasos": "1. ...\\n2. ..."}}
"""


def _codigo_desde(nombre: str) -> str:
    """El codigo se DERIVA del nombre; no se le pide al modelo.

    Se le pedia, y las tres primeras corridas reales devolvieron literal el
    'HAB-XXXX-01' que el ejemplo del prompt usaba como marcador de forma. Un
    modelo copia el ejemplo cuando el campo no le aporta nada -- y tenia razon:
    un identificador no es una decision de redaccion.

    Importa porque el codigo no es decorativo: es lo que el agente escribe
    para pedir el procedimiento y lo que queda en la traza de la conversacion.
    'HAB-XXXX-01' no dice nada; 'HAB-CAMBIO-NOMBRE-WIFI' se entiende leyendolo.
    """
    base = unicodedata.normalize("NFKD", nombre or "")
    base = base.encode("ascii", "ignore").decode("ascii").upper()
    palabras = [p for p in re.split(r"[^A-Z0-9]+", base) if len(p) > 2][:4]
    return ("HAB-" + "-".join(palabras))[:52] if palabras else "HAB-SIN-NOMBRE"


def _extraer_json(texto: str) -> dict | None:
    """El JSON del modelo, tolerando que venga envuelto en explicaciones.

    Un modelo instruido a responder "SOLO JSON" igual antepone una linea de
    cortesia cada tantas corridas. Eso no vale perder el analisis entero.
    """
    if not texto:
        return None
    try:
        return json.loads(texto)
    except (ValueError, TypeError):
        pass
    m = re.search(r"\{.*\}", texto, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except (ValueError, TypeError):
        return None


def redactar(config, patron: Patron, dias: int = DIAS_POR_DEFECTO) -> dict | None:
    """Un borrador de habilidad para un patron. None si no salio utilizable.

    Le pasa al modelo las herramientas REALES del rol. Sin eso redacta pasos
    que mencionan sistemas que el agente no puede tocar -- un procedimiento
    imposible de seguir es peor que ninguno, porque el agente lo intenta y
    falla en la mitad.
    """
    rol_cfg = (config.roles or {}).get(patron.rol)
    if rol_cfg is None:
        return None

    nombres = list(rol_cfg.puede_consultar or [])
    catalogo = {h.nombre: h for h in (config.herramientas or [])}
    herramientas = "\n".join(
        f"- {n}: {getattr(catalogo.get(n), 'descripcion', '') or 'sin descripcion'}"
        for n in nombres) or "(este rol no tiene ninguna herramienta)"

    muestras = "\n".join(f"- {m}" for m in patron.muestras) or "(sin muestras)"
    prompt = PROMPT_REDACCION.format(
        rol=patron.rol, senal=patron.senal, motivo=patron.motivo,
        dias=dias, n_casos=patron.n_casos, muestras=muestras,
        herramientas=herramientas)

    try:
        respuesta = cliente.chat(
            config.llm.modelo_por_defecto, [{"role": "user", "content": prompt}],
            temperatura=0.2, timeout=TIMEOUT_REDACCION)
    except Exception as fallo:      # noqa: BLE001
        print(f"[analista] el modelo no pudo redactar: {fallo!r}")
        return None

    datos = _extraer_json(getattr(respuesta, "contenido", "") or "")
    if not datos:
        print(f"[analista] respuesta no interpretable para {patron.rol}/{patron.senal}")
        return None

    faltan = [c for c in ("nombre", "cuando_usarla", "pasos")
              if not str(datos.get(c) or "").strip()]
    if faltan:
        print(f"[analista] borrador incompleto, falta {faltan}")
        return None
    return datos


def guardar_propuesta(tenant: str, patron: Patron, borrador: dict,
                      dias: int) -> str | None:
    """Guarda el borrador como propuesta. Devuelve el codigo, o None.

    'evidencia' guarda de donde salio -- sin eso quien aprueba tendria que
    creerle al sistema. Con eso puede abrir las conversaciones y decidir.

    El codigo lleva sufijo de version si ya existe uno igual: dos analisis del
    mismo patron en semanas distintas no deben pisarse, porque la propuesta
    vieja puede estar ya revisada.
    """
    evidencia = {
        "senal": patron.senal, "motivo": patron.motivo,
        "n_casos": patron.n_casos, "dias_analizados": dias,
        "conversaciones": patron.conversaciones[:20],
        "habilidad_previa": patron.codigo_habilidad,
    }
    codigo = _codigo_desde(str(borrador["nombre"]))
    with sesion(tenant) as (cur, org):
        # Dos analisis del mismo hueco en semanas distintas no deben pisarse:
        # la propuesta vieja puede estar ya revisada, o incluso vigente.
        cur.execute("""select count(*) as n from asistente.habilidades
                        where organization_id = %s and codigo like %s""",
                    (org, codigo + "%"))
        repetidas = (cur.fetchone() or {}).get("n") or 0
        if repetidas:
            codigo = f"{codigo}-{repetidas + 1}"
        cur.execute(
            """insert into asistente.habilidades
                   (organization_id, codigo, nombre, cuando_usarla, pasos,
                    roles_permitidos, estado, origen, evidencia)
               values (%s, %s, %s, %s, %s, %s, 'propuesta', 'analisis', %s)
               on conflict do nothing
               returning codigo""",
            (org, codigo, str(borrador["nombre"])[:200],
             str(borrador["cuando_usarla"]), str(borrador["pasos"]),
             [patron.rol], json.dumps(evidencia)))
        fila = cur.fetchone()
    return fila["codigo"] if fila else None


def proponer(config, tenant: str, dias: int = DIAS_POR_DEFECTO,
             minimo: int = MINIMO_CASOS) -> list[dict]:
    """El circuito entero: detectar, redactar, guardar como propuesta.

    Nada queda activo. Devuelve un resumen por patron para que quien lo corra
    vea que se detecto y que se llego a redactar -- las dos cosas pueden
    diferir, y esa diferencia es informacion: un patron detectado que no se
    pudo redactar suele significar que al rol le falta una HERRAMIENTA, no un
    procedimiento.
    """
    resultados = []
    for patron in detectar(tenant, dias=dias, minimo=minimo):
        borrador = redactar(config, patron, dias=dias)
        codigo = guardar_propuesta(tenant, patron, borrador, dias) if borrador else None
        resultados.append({
            "rol": patron.rol, "senal": patron.senal, "motivo": patron.motivo,
            "n_casos": patron.n_casos, "propuesta": codigo,
            "nombre": (borrador or {}).get("nombre"),
        })
    return resultados
