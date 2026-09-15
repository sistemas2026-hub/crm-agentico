# -*- coding: utf-8 -*-
"""
================================================================================
 HABILIDADES  --  procedimientos que un agente carga cuando le hacen falta
================================================================================

Que resuelve, y por que no alcanzaba con el corpus
--------------------------------------------------
El corpus (nucleo/recuperacion/) es REFERENCIA: se fragmenta, se vectoriza y se
recupera por parecido con la pregunta. Contesta "que dice la guia sobre esto".

Una habilidad es PROCEDIMIENTO: "cuando pase X, hace estos pasos". Y hay dos
razones concretas por las que no puede vivir en el corpus:

1. UN PROCEDIMIENTO PARTIDO DEJA DE SER UN PROCEDIMIENTO. La recuperacion trae
   los top-k fragmentos mas parecidos. Si el paso 4 de 6 no entra en el top-k,
   el agente hace 1, 2, 3, 5, 6 y nadie se entera -- ni el, ni quien lee la
   respuesta. Una habilidad llega entera o no llega.

2. SE ACTIVA POR SITUACION, NO POR PARECIDO. Lo que dispara una habilidad no
   suele parecerse al texto de la habilidad. "Se me cayo el internet" no tiene
   ni una palabra en comun con "antes de agendar una visita, descarta que la
   caida sea compartida con vecinos del mismo puerto" -- y es exactamente ahi
   donde hace falta. El disparador lo escribe una persona ('cuando_usarla'),
   no lo calcula un coseno.

Como se activa -- divulgacion progresiva
----------------------------------------
    prompt (siempre)   ->  INDICE: codigo + cuando_usarla, una linea c/u
    cargar_habilidad() ->  CUERPO: los pasos completos, solo si la pide

El indice es barato y va en todos los turnos; el cuerpo se paga solo cuando de
verdad se usa. Es el mismo patron con el que se cargan las skills de un agente
de codigo, y por el mismo motivo: el modelo no puede elegir lo que no sabe que
existe, pero tampoco puede cargar con todo en cada turno.

Esto NO es mas autonomia (PRD seccion 2)
----------------------------------------
Una habilidad no ejecuta nada: es texto que entra al prompt. Las garantias
siguen intactas y donde estaban -- listas blancas de campos, precondiciones en
codigo, aprobacion humana de escrituras. Lo que crece es el ALCANCE (cuanto
sabe hacer bien), nunca la confianza en lo que el modelo decide por su cuenta.

Falla cerrado, en dos capas -- igual que las herramientas
--------------------------------------------------------
El indice de un rol solo trae SUS habilidades (la lista blanca de
'roles_permitidos'), y cargar_habilidad vuelve a comprobar el permiso al
resolver el codigo. No alcanza con no mostrarla: el modelo puede nombrar un
codigo que vio en otra conversacion, o inventarlo. Mismo criterio que
PRD 8.1: "una herramienta que no esta en el area no se le muestra al modelo Y
se rechaza si igual la invoca; ambas condiciones se verifican".

Este modulo es generico: no conoce ninguna empresa ni ningun rol concreto.
Los codigos, los disparadores y los pasos son datos del tenant, en la base.
================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass

from nucleo.persistencia.db import sesion


@dataclass(frozen=True)
class Habilidad:
    codigo: str
    nombre: str
    cuando_usarla: str
    pasos: str


@dataclass(frozen=True)
class EntradaIndice:
    """Lo que el agente ve SIN cargar la habilidad: para decidir si la pide."""
    codigo: str
    nombre: str
    cuando_usarla: str


def indice_de(tenant: str, rol: str) -> list[EntradaIndice]:
    """El indice de habilidades vigentes que este rol puede cargar.

    Solo 'vigente': una propuesta sin aprobar no existe para el agente. Es la
    diferencia entre proponer un procedimiento y ponerlo a operar.

    Se ordena por codigo y no por fecha para que el prompt sea ESTABLE entre
    turnos: un prompt que cambia de orden solo invalida la cache del proveedor
    y hace que dos turnos identicos no sean comparables al depurar.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select codigo, nombre, cuando_usarla
                 from asistente.habilidades
                where organization_id = %s and estado = 'vigente'
                  and roles_permitidos is not null
                  and %s = any(roles_permitidos)
                order by codigo""",
            (org, rol))
        filas = cur.fetchall()
    return [EntradaIndice(codigo=f["codigo"], nombre=f["nombre"],
                          cuando_usarla=f["cuando_usarla"]) for f in filas]


def cargar(tenant: str, rol: str, codigo: str) -> Habilidad | None:
    """Los pasos completos de una habilidad, si ESE rol puede cargarla.

    El filtro por rol se repite aca a proposito, aunque el indice ya lo
    aplique: el codigo llega en un argumento que produce el modelo, y un
    modelo puede nombrar uno que vio en otra conversacion o directamente
    inventarlo. Devuelve None tanto para "no existe" como para "no es tuya" --
    quien llama no necesita distinguirlas, y decirle al modelo cual de las dos
    es le contaria que existe una habilidad que no puede ver.
    """
    with sesion(tenant) as (cur, org):
        cur.execute(
            """select codigo, nombre, cuando_usarla, pasos
                 from asistente.habilidades
                where organization_id = %s and estado = 'vigente'
                  and codigo = %s
                  and roles_permitidos is not null
                  and %s = any(roles_permitidos)""",
            (org, codigo, rol))
        fila = cur.fetchone()
    if not fila:
        return None
    return Habilidad(codigo=fila["codigo"], nombre=fila["nombre"],
                     cuando_usarla=fila["cuando_usarla"], pasos=fila["pasos"])


def registrar_uso(tenant: str, codigo: str, rol: str,
                  conversation_id: str | None = None) -> None:
    """Deja constancia de que se cargo. Nunca frena el turno si falla.

    Sin este registro no se puede distinguir una habilidad que nadie usa
    (ruido en el indice de todos los turnos, hay que retirarla) de una que se
    carga siempre y aun asi la conversacion termina en un humano (esta mal
    escrita, hay que reescribirla). Las dos se ven igual desde afuera.

    Es observabilidad, no parte de la respuesta: si la insercion falla, el
    cliente no tiene por que perder su turno por eso.
    """
    try:
        with sesion(tenant) as (cur, org):
            cur.execute(
                """insert into asistente.habilidad_usos
                       (organization_id, habilidad_id, conversation_id, rol)
                   select %s, id, %s, %s from asistente.habilidades
                    where organization_id = %s and codigo = %s
                      and estado = 'vigente' limit 1""",
                (org, conversation_id, rol, org, codigo))
    except Exception as fallo:            # noqa: BLE001 -- ver docstring
        print(f"[habilidades] no se pudo registrar el uso de {codigo}: {fallo!r}")


def bloque_de_indice(entradas: list[EntradaIndice]) -> str:
    """El indice, como texto para el prompt.

    Dice explicitamente que los pasos NO estan aca. Sin esa aclaracion el
    modelo lee el disparador, cree que ya sabe el procedimiento y contesta con
    lo que improvise -- que es exactamente el problema que las habilidades
    vienen a resolver, reproducido un nivel mas arriba.
    """
    if not entradas:
        return ""
    lineas = [f"- {e.codigo}: {e.nombre}. Usala cuando {e.cuando_usarla}"
              for e in entradas]
    return (
        "PROCEDIMIENTOS DISPONIBLES\n"
        "Estos son procedimientos de la empresa que puedes cargar. Aca solo "
        "esta CUANDO usar cada uno -- los pasos NO estan en esta lista.\n"
        + "\n".join(lineas) + "\n"
        "Si la situacion coincide con alguno, cargalo con cargar_habilidad "
        "ANTES de contestar, y despues segui sus pasos al pie de la letra. No "
        "adivines los pasos a partir del nombre: para eso hay que cargarla.")
