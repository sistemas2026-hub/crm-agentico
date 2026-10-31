# -*- coding: utf-8 -*-
"""
================================================================================
 A QUIEN SE LE ESCRIBE UN AVISO PROACTIVO  --  30/10/2026
================================================================================

Un aviso proactivo (PRD §8.17, Ola 2) le escribe a un cliente que NO esta
chateando. Hay dos fuentes de su numero, y se usan en este orden:

  1. LA CONVERSACION del caso: 'usuario_externo' es el numero con el que el
     cliente le escribe a la empresa de verdad, ya en la forma de WhatsApp.
  2. EL SISTEMA DEL ISP: el campo de telefono, CRUDO. Sin indicativo, y con
     varios numeros en uno solo en el 55% de los casos. Se extraen los moviles
     con el patron que ya declara la empresa (autenticacion.patron_extraccion,
     el mismo que usa la verificacion de identidad) y se les pone SU indicativo
     (autenticacion.indicativo_pais). Con varios, gana el que ya le escribio a
     la empresa por WhatsApp; si ninguno, el primero, que en el ISP es el
     principal.

SIN INDICATIVO NO SE ADIVINA. Es dato de la empresa (un ISP de otro pais tiene
otro), y sin el no hay forma de llegar a la forma de WhatsApp: el aviso no sale.

LA FORMA IMPORTA MAS QUE EL NUMERO. Lo que sale es solo digitos, indicativo
incluido -- la misma forma que 'usuario_externo'. La baja (Ley 1581) compara
por igualdad contra esa forma (db.esta_de_baja): un '+57 300...' o un
'3001234567' la saltarian, y le llegaria el aviso a quien pidio no recibirlo.
================================================================================
"""

from __future__ import annotations

import re
from typing import Callable


def numeros_whatsapp(config, telefono_crudo: str | None) -> list[str]:
    """Los moviles del campo crudo en forma de WhatsApp, sin repetir y en orden."""
    aut = getattr(config, "autenticacion", None)
    indicativo = "".join(ch for ch in str(getattr(aut, "indicativo_pais", "") or "") if ch.isdigit())
    patron = getattr(aut, "patron_extraccion", None)
    if not indicativo or not patron or not telefono_crudo:
        return []
    vistos: list[str] = []

    def sumar(local: str) -> None:
        numero = indicativo + local
        if numero not in vistos:
            vistos.append(numero)

    #  Trozo por trozo, en el orden en que la persona los escribio. Primero el
    #  patron sobre el texto tal cual (asi dos moviles separados por un espacio
    #  siguen siendo dos); si no encuentra nada, el trozo limpio a digitos (un
    #  movil escrito "300 123 4567" o "+57 312-455-8901"), con el indicativo
    #  sacado si ya venia puesto.
    for trozo in re.split(r"[,;/|]+|\s+(?:y|o)\s+", str(telefono_crudo)):
        encontrados = re.findall(patron, trozo)
        if not encontrados:
            digitos = "".join(ch for ch in trozo if ch.isdigit())
            sin_pais = digitos[len(indicativo):] if digitos.startswith(indicativo) else None
            for candidato in (digitos, sin_pais):
                if candidato and re.fullmatch(patron, candidato):
                    encontrados = [candidato]
                    break
        for local in encontrados:
            sumar(local)
    return vistos


def elegir(config, *, conversacion: str | None, telefono_crudo: str | None,
           ya_escribio: Callable[[str], bool]) -> tuple[str | None, str]:
    """
    (numero, de donde salio) o (None, por que no hay).

    'ya_escribio(numero)' dice si ese numero tiene alguna conversacion con la
    empresa; lo inyecta quien llama, para que esto no toque la base.
    """
    #  Solo si ES un numero. Un identificador de WhatsApp sin telefono (BSUID,
    #  'CO.1360...') no se convierte en numero quitandole las letras: eso
    #  inventa un destino y saltea la baja, que se guardo con el identificador
    #  entero (medido por el auditor de frontera, 30/10/2026). Se cae al ISP.
    propio = str(conversacion or "").strip().lstrip("+")
    if propio.isdigit():
        return propio, "conversacion"
    aut = getattr(config, "autenticacion", None)
    if not str(getattr(aut, "indicativo_pais", "") or "").strip():
        return None, "sin_indicativo"
    candidatos = numeros_whatsapp(config, telefono_crudo)
    if not candidatos:
        return None, "sin_movil"
    for numero in candidatos:
        if ya_escribio(numero):
            return numero, "conocido"
    return candidatos[0], "primero_del_isp"
