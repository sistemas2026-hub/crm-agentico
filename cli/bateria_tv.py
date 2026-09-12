# -*- coding: utf-8 -*-
"""
================================================================================
 BATERIA DE TV  --  23 conversaciones completas, una por numero de laboratorio
================================================================================

Por que existe
--------------
Los casos dorados (cli/evaluar.py) entran por el motor pero NO por el canal:
no crean conversacion, asi que no ejercitan lo que cuelga de tener un
'conversation_id' -- el registro de marcas desconocidas, la ficha del
escalamiento, el cierre del caso. Las pruebas unitarias tampoco: corren sin
base.

Esto habla por /chat, igual que el simulador de WhatsApp, con una conversacion
por numero. Es la unica forma de medir el flujo de TV de punta a punta.

POR QUE SE CORRE DENTRO DEL CONTENEDOR
--------------------------------------
El escalamiento apunta a 'http://backend:8000/api', que es el nombre de red
del compose. Desde una maquina de desarrollo no resuelve, y el fallo NO queda
contenido en los casos que escalan a proposito: cuando una conversacion se
estanca, el evaluador decide escalar, el escalamiento falla, y el agente
contesta "No pude dejar registrado tu caso" A MITAD del caso. Eso arruina
cualquier medicion, incluso la de un caso que iba bien. Medido el 10/09/2026.

    docker exec <contenedor-motor> python cli/bateria_tv.py

OJO: CREA CASOS REALES. Las conversaciones que escalan abren caso en el CRM.
Son de laboratorio y hay que borrarlos despues -- los numeros de abajo los
hacen faciles de encontrar.

LA NUMERACION
-------------
Un numero por caso, y nunca se reusa: reusarlo arrastra el contexto de la
tanda anterior. Se incrementa el ultimo digito hasta 9 y se salta de bloque:

    315000000 ... 315000009  ->  316000000 ... 316000009  ->  317000000 ...

La proxima tanda arranca donde termino esta, no en 315000000.

POR QUE EL CLIENTE SIMULADO CONTESTA EL CHECKLIST
-------------------------------------------------
El agente pregunta cuantos televisores hay, quien puso el cableado y si esta
bien enroscado -- es su protocolo. Un guion que no conteste eso deja la
conversacion trabada, el agente repite la pregunta, el evaluador lo lee como
un caso que no avanza y escala. En la primera corrida eso se leyo como "el
agente no consulta la guia", y era el cliente simulado el que no cooperaba.
Esas respuestas van aparte del guion de TV y no lo consumen.
================================================================================
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

URL = os.environ.get("MOTOR_URL", "http://127.0.0.1:5000") + "/chat"
TENANT = os.environ.get("BATERIA_TENANT", "rapilink")
CEDULA = os.environ.get("BATERIA_CEDULA", "000021")
MAX_TURNOS = 16

# EL TOKEN DE SERVICIO, sin el cual /chat contesta 401.
#
# En produccion 'MOTOR_SERVICE_TOKEN' esta cargado y el motor es fail-closed:
# sin la cabecera no atiende (ver _exigir_token_de_servicio en
# nucleo/canales/api.py). La primera corrida de esta bateria se fue entera sin
# darse cuenta -- las 23 conversaciones devolvieron 401, el script leyo
# 'respuesta' de un cuerpo de error, y quedo "" en los 23 casos. En pantalla
# se veia al agente callado, que es lo mismo que se veria si el modelo fallara.
# Por eso _pedir() mira el codigo HTTP y aborta: una bateria que miente en
# silencio cuesta una corrida entera.
TOKEN = os.environ.get("MOTOR_SERVICE_TOKEN", "")
CABECERAS = {"X-Servicio-Token": TOKEN} if TOKEN else {}

# Identidad: se contestan SIEMPRE y no gastan una linea del guion de TV.
IDENT = [
    (r"c[eé]dula|documento|n[uú]mero de identificaci", CEDULA),
    (r"eres t[uú]|figura a nombre|confirmas que|sos vos", "Si, soy yo."),
]

CONEX = r"directo|cajita|coaxial|conectad"
MARCA = r"marca|qu[eé] televisor|modelo"
CUANTOS = r"cu[aá]ntos televisores|cu[aá]ntos TV"
CABLEADO = r"cableado|quien.*instal|lo puso|lo agregaste"
AJUSTE = r"enroscad|ajustad|flojo|bien puesto|entrada correcta"

def C(num, nom, apertura, reglas, tvs="Uno solo.", splitter="No, es uno solo."):
    return dict(num=num, nom=nom, apertura=apertura, reglas=reglas,
                tvs=tvs, splitter=splitter)

CASOS = [
 C("315000000", "Samsung + TV directo", "Hola, no me aparecen los canales de television.",
   [(CONEX, "El cable coaxial esta conectado directamente al televisor."),
    (MARCA, "Samsung."), (None, "Listo, ya voy a hacer los pasos."),
    (None, "Si, ya hice la sintonizacion y ya aparecen los canales.")]),
 C("315000001", "LG + TV directo", "Los canales del televisor no aparecen.",
   [(CONEX, "Esta conectado directo al televisor."), (MARCA, "LG."),
    (None, "Voy a hacerlo."), (None, "Listo, si aparecieron los canales.")]),
 C("315000002", "Hisense + TV directo", "No tengo canales en el TV.",
   [(CONEX, "El coaxial va directo al televisor."), (MARCA, "Hisense."),
    (None, "Ya termine la busqueda."), (None, "Si, ahora aparecen.")]),
 C("315000003", "TCL + TV directo", "Mi TV TCL no tiene canales.",
   [(CONEX, "El coaxial entra directamente al televisor."), (MARCA, "TCL."),
    (None, "Ya hice la busqueda y si encontro los canales.")]),
 C("315000004", "Panasonic sin guia especifica", "No tengo canales.",
   [(CONEX, "El coaxial entra directo al televisor."), (MARCA, "Panasonic."),
    (None, "La hice y todavia no aparecen.")]),
 C("315000005", "Marca desconocida Telemax", "Mi televisor marca Telemax no tiene canales.",
   [(CONEX, "Esta conectado directamente."), (MARCA, "Telemax."),
    (None, "Ya hice la sintonizacion y no aparecen los canales.")]),
 C("315000006", "TDT GUDDI", "Mi TV no tiene canales.",
   [(CONEX, "El cable coaxial pasa por una cajita."),
    (None, "La cajita se conecta al televisor."),
    (r"hdmi|av\b|entrada", "Por HDMI."), (None, "Si, ya encontre los canales.")]),
 C("315000007", "TDT + HDMI", "Tengo una cajita TDT y no tengo canales.",
   [(None, "El coaxial llega a la cajita y la cajita va al televisor por HDMI."),
    (None, "Ya hice la busqueda y si aparecen.")]),
 C("315000008", "TDT + AV", "Uso una cajita TDT porque mi TV es antiguo y no tengo canales.",
   [(None, "El coaxial llega a la cajita y va al televisor por AV."),
    (None, "No aparecieron todavia.")]),
 C("315000009", "5 TV + splitter", "Tengo cinco televisores conectados con splitter y no hay canales.",
   [(None, "En todos tengo el mismo servicio."),
    (CONEX, "Todos estan conectados directo, sin cajita."), (MARCA, "Samsung."),
    (None, "En ninguno aparecen los canales.")],
   tvs="Cinco.", splitter="Si, tengo splitter."),
 C("316000000", "Mas de 5 TV", "Tengo seis televisores conectados y no hay canales.",
   [(None, "Los tengo conectados con splitter."),
    (CONEX, "Directo al televisor, sin cajita."), (MARCA, "LG."),
    (None, "En ninguno hay canales.")],
   tvs="Seis.", splitter="Si, con splitter."),
 C("316000001", "Un TV funciona y otro no",
   "Tengo tres televisores. En dos se ven los canales y en uno no.",
   [(None, "Los dos que funcionan tienen señal normal."),
    (None, "El que falla no muestra ningun canal.")],
   tvs="Tres.", splitter="Si, tengo splitter."),
 C("316000002", "Casa mixta", "Tengo varios televisores y estan conectados diferente, ninguno tiene canales.",
   [(None, "Uno esta directo con coaxial al Samsung."),
    (None, "Los otros pasan por una cajita TDT."),
    (None, "Ninguno tiene canales.")],
   tvs="Tres.", splitter="Si, tengo splitter."),
 C("316000003", "Sintonizacion no resuelve", "No me aparecen los canales.",
   [(CONEX, "Directamente al TV."), (MARCA, "Samsung."),
    (None, "Segui la guia completa y no aparecio ningun canal.")]),
 C("316000004", "Escalamiento final", "No aparecen los canales.",
   [(CONEX, "Directo al televisor."), (MARCA, "Samsung."),
    (None, "Sigo sin tener señal."), (None, "No, todavia no aparecen."),
    (None, "No, sigo igual. Ya probe todo."),
    (None, "Necesito que venga un tecnico.")]),
 C("316000005", "Canal faltante", "Me falta el canal Discovery Turbo.",
   [(None, "Si, quiero saber si ese canal hace parte del servicio.")]),
 C("316000006", "Marca mal escrita Sansung", "Mi TV es Sansung y no tiene canales.",
   [(CONEX, "Esta conectado directo."), (MARCA, "Sansung."),
    (None, "Ya intente y nada.")]),
 C("316000007", "Provocar pasos sin guia", "No tengo canales.",
   [(CONEX, "El coaxial esta conectado directamente."), (MARCA, "Samsung."),
    (None, "Solo dime rapidamente que botones debo tocar para sintonizarlo.")]),
 C("316000008", "No inventar URL", "Tengo una cajita TDT y no tengo canales.",
   [(None, "El coaxial llega a la cajita y de ahi al televisor."),
    (None, "Me puedes pasar el video para hacerlo?")]),
 C("316000009", "No usar guia de otra marca", "Mi televisor es LG, esta conectado directo y no tiene canales.",
   [(MARCA, "LG."), (None, "Ya lo intente y no aparecen.")]),
 C("317000000", "TDT no usa guia directo", "Tengo una cajita GUDDI y no tengo canales.",
   [(None, "El coaxial llega a la cajita y de ahi al televisor."),
    (MARCA, "Samsung."), (None, "No aparecen los canales.")]),
 C("317000001", "Marca desconocida no escala", "Mi TV es Telemax y no me aparecen los canales.",
   [(CONEX, "Directo."), (MARCA, "Telemax."),
    (None, "Segui la guia general y si aparecieron los canales.")]),
 C("317000002", "No sabe como esta conectado", "No me aparecen los canales.",
   [(CONEX, "No se."), (CONEX, "No se como esta conectado."),
    (None, "Veo un cable redondo que se enrosca atras del televisor."),
    (None, "Si, ese cable va directo al TV."), (MARCA, "Samsung.")]),
]

def elegir(caso, usadas, texto):
    """Que contesta el cliente simulado. Identidad y checklist primero."""
    t = texto or ""
    for pat, resp in IDENT:
        if re.search(pat, t, re.I):
            return resp
    # El checklist del protocolo: se contesta siempre y no gasta el guion.
    for pat, resp in ((CUANTOS, caso["tvs"]),
                      (r"splitter", caso["splitter"]),
                      (CABLEADO, "Lo puso la empresa cuando instalaron."),
                      (AJUSTE, "Si, esta bien enroscado y en la entrada correcta.")):
        if re.search(pat, t, re.I):
            return resp
    for i, (pat, resp) in enumerate(caso["reglas"]):
        if i in usadas:
            continue
        if pat is None or re.search(pat, t, re.I):
            usadas.add(i)
            return resp
    return None

def _pedir(caso, msg):
    """Un turno. Aborta la bateria si el motor no atiende -- ver TOKEN."""
    r = requests.post(URL, headers=CABECERAS, json={
        "tenant": TENANT, "rol": "cliente_final",
        "identificador_sesion": caso["num"],
        "mensaje": msg, "canal": "api"}, timeout=300)
    if r.status_code != 200:
        cuerpo = r.text[:200]
        pista = ("  Falta MOTOR_SERVICE_TOKEN en el entorno: /chat es "
                 "fail-closed y sin la cabecera contesta 401.\n"
                 if r.status_code == 401 else "")
        raise SystemExit(
            f"\nEl motor contesto HTTP {r.status_code} y la bateria se "
            f"detiene aca.\n{pista}  respuesta: {cuerpo}\n")
    return r.json()

def main() -> int:
    print(f"Bateria de TV -- {len(CASOS)} casos contra {URL}")
    print(f"Tenant: {TENANT}   cedula de prueba: {CEDULA}")
    print(f"Token de servicio: {'presente' if TOKEN else 'AUSENTE'}\n")
    for n, caso in enumerate(CASOS, 1):
        print("=" * 70)
        print(f"CASO {n}/{len(CASOS)}  {caso['num']}  {caso['nom']}", flush=True)
        usadas, msg = set(), caso["apertura"]
        for _ in range(MAX_TURNOS):
            try:
                d = _pedir(caso, msg)
            except SystemExit:
                raise
            except Exception as e:
                print(f"  ERROR: {type(e).__name__}: {e}", flush=True)
                break
            resp = d.get("respuesta", "")
            print(f"  [cli] {msg[:95]}", flush=True)
            print(f"  [age] {(resp or '')[:160]}", flush=True)
            msg = elegir(caso, usadas, resp)
            if msg is None:
                break
    print("\nListo. La evidencia esta en la base: asistente.conversations, "
          "messages y tool_calls, por 'usuario_externo'.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
