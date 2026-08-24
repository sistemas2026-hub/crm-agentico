# -*- coding: utf-8 -*-
"""
================================================================================
 VALIDACION DE UN NOMBRE DE RED Y UNA CLAVE  --  antes de molestar a una persona
================================================================================

El asistente no cambia el WiFi: recoge el pedido y lo pasa a alguien que lo
ejecuta. Esto valida lo que el cliente escribio ANTES de que ese pedido salga,
para que nadie tome un trabajo que el equipo despues no va a aceptar.

POR QUE EN CODIGO Y NO EN EL PROMPT
-----------------------------------
El prompt es guia, nunca la garantia (PRD 7.4). Un largo maximo pedido por
prompt se cumple casi siempre, y "casi siempre" aca significa que cada tanto
sale un pedido imposible, alguien lo toma, lo intenta, falla y hay que volver
a escribirle al cliente. Un limite en codigo no tiene 'casi'.

LO QUE ESTO **NO** HACE
-----------------------
No decide si el pedido es legitimo ni si quien escribe es el titular. Eso lo
resuelve el humano que recibe el caso, contrastando contra el equipo lo que el
cliente dijo que tiene hoy. Aca solo se mira la FORMA del valor nuevo.

Tampoco reemplaza al criterio del tenant: los limites de WPA son del estandar
y viven aca, pero que caracteres desaconsejar depende del equipo que ese ISP
haya instalado -- eso viaja por configuracion.
"""

from __future__ import annotations

# --- limites del estandar, no de una empresa ---------------------------------
# WPA/WPA2/WPA3-Personal: la clave es de 8 a 63 caracteres ASCII imprimibles, o
# exactamente 64 hexadecimales (esa forma es la PSK ya derivada, no una frase).
# 802.11 define el SSID como 32 OCTETOS -- ver la nota de _largo_en_octetos.
CLAVE_MIN = 8
CLAVE_MAX = 63
CLAVE_HEX = 64
SSID_MAX_OCTETOS = 32

_HEX = set("0123456789abcdefABCDEF")


def _largo_en_octetos(texto: str) -> int:
    """
    El limite del SSID es de OCTETOS, no de letras.

    Importa de verdad en espanol: 'Casa Peña' son 9 caracteres pero 10 octetos
    en UTF-8, porque la 'ñ' ocupa dos. Contar letras deja pasar nombres que el
    equipo despues recorta o rechaza, y el sintoma le llega al cliente como
    'mi red se llama distinto de lo que pedi'.
    """
    return len(texto.encode("utf-8"))


def _tiene_control(texto: str) -> bool:
    """Caracteres de control (tabulacion, saltos, nulos): invisibles y rompen."""
    return any(ord(c) < 32 or ord(c) == 127 for c in texto)


def validar_ssid(nombre: str, desaconsejados: str = "") -> list[str]:
    """
    Los problemas de un nombre de red, en frases que se le pueden leer al
    cliente tal cual. Lista vacia = se puede pedir el cambio.

    'desaconsejados' son los caracteres que el equipo de ESE ISP maneja mal;
    llega de la configuracion del tenant porque depende de la marca de ONT
    instalada, no del estandar. Se reportan como problema y no como consejo:
    un pedido que el equipo no va a aceptar no es mejor por haber avisado.
    """
    problemas = []
    if nombre is None:
        nombre = ""

    if not nombre.strip():
        problemas.append("El nombre de la red no puede quedar vacio.")
        return problemas

    if nombre != nombre.strip():
        # Se revisa ANTES del largo: un espacio al final es invisible en el
        # chat y explica por si solo un nombre que 'se ve igual' y no funciona.
        problemas.append(
            "El nombre no puede empezar ni terminar con un espacio.")

    octetos = _largo_en_octetos(nombre)
    if octetos > SSID_MAX_OCTETOS:
        detalle = (f" (ocupa {octetos}; algunas letras como la ñ o las tildes "
                   f"cuentan doble)") if octetos != len(nombre) else ""
        problemas.append(
            f"El nombre puede tener hasta {SSID_MAX_OCTETOS} caracteres{detalle}.")

    if _tiene_control(nombre):
        problemas.append("El nombre no puede llevar saltos de linea ni tabulaciones.")

    # Fuera de ASCII: ñ, tildes, emojis. Se rechaza, no se aconseja.
    #
    # El limite de 802.11 es de octetos y por ahi entrarian, pero en la
    # practica los equipos de un ISP no las manejan bien -- y el sintoma no es
    # un error al guardar sino una red que el cliente no encuentra, o que
    # aparece con el nombre cambiado. Eso llega como "me dejaste sin internet"
    # una semana despues, sin forma de relacionarlo con el cambio.
    fuera = sorted({c for c in nombre if ord(c) > 126})
    if fuera:
        problemas.append(
            "El nombre no puede llevar ñ, tildes ni emojis: usa solo letras "
            "sin tilde, numeros y espacios.")

    presentes = sorted({c for c in nombre if c in (desaconsejados or "")})
    if presentes:
        problemas.append(
            "El nombre no puede llevar estos caracteres, porque hay equipos "
            "que despues no ven la red: " + " ".join(presentes) + ".")

    return problemas


# --- lo que se le dice al cliente ANTES de que escriba -----------------------
# Pedir el dato y despues rechazarlo es una vuelta de mas; estas frases se
# mandan al pedirlo. Viven aca y no en el prompt para que digan exactamente lo
# mismo que valida el codigo: si el limite cambia, cambian las dos juntas.

def recomendaciones_nombre() -> list[str]:
    return [
        f"Hasta {SSID_MAX_OCTETOS} caracteres.",
        "Sin ñ, sin tildes y sin emojis.",
        "Sin espacios al principio ni al final.",
    ]


def recomendaciones_clave() -> list[str]:
    return [
        f"Entre {CLAVE_MIN} y {CLAVE_MAX} caracteres.",
        "Combina mayuscula, minuscula, numero y un simbolo -- por ejemplo, "
        "algo con la forma de 'Mm12$'.",
        "Sin ñ, sin tildes y sin emojis.",
        "Sin espacios al principio ni al final.",
    ]


def validar_clave(clave: str, desaconsejados: str = "") -> list[str]:
    """
    Los problemas de una clave. Lista vacia = se puede pedir el cambio.

    Una clave de 64 caracteres hexadecimales es valida y NO se mide contra el
    maximo de 63: esa forma no es una frase sino la PSK ya derivada, y el
    estandar la acepta. Sin esta excepcion, quien pega una PSK real se la
    rechaza por larga.
    """
    problemas = []
    if clave is None:
        clave = ""

    if len(clave) == CLAVE_HEX and all(c in _HEX for c in clave):
        return problemas

    if len(clave) < CLAVE_MIN:
        problemas.append(f"La clave tiene que tener al menos {CLAVE_MIN} caracteres.")
    elif len(clave) > CLAVE_MAX:
        problemas.append(f"La clave puede tener hasta {CLAVE_MAX} caracteres.")

    if clave and clave != clave.strip():
        problemas.append("La clave no puede empezar ni terminar con un espacio.")

    if _tiene_control(clave):
        problemas.append("La clave no puede llevar saltos de linea ni tabulaciones.")

    # El estandar pide ASCII imprimible para la frase de 8-63. Una 'ñ' o un
    # emoji entran en el celular pero muchos equipos los guardan distinto, y el
    # cliente queda sin poder conectarse a su propia red.
    fuera = sorted({c for c in clave if ord(c) < 32 or ord(c) > 126})
    if fuera:
        problemas.append(
            "La clave solo puede llevar letras sin tilde, numeros y simbolos "
            "comunes: no acepta emojis, tildes ni la ñ.")

    presentes = sorted({c for c in clave if c in (desaconsejados or "")})
    if presentes:
        problemas.append(
            "La clave no puede llevar estos caracteres por el equipo instalado: "
            + " ".join(presentes) + ".")

    return problemas


def clave_es_debil(clave: str) -> bool:
    """
    Si la clave es de las que se prueban primero.

    Se devuelve aparte de validar_clave() a proposito: esto AVISA, no rechaza.
    Es la red del propio cliente y la decision es suya; un asistente que se
    niega genera una discusion que no puede ganar, y el cliente igual se la
    dice al tecnico por telefono. Avisar cambia decisiones; bloquear solo
    mueve la conversacion a otro canal.
    """
    if not clave:
        return False
    plana = clave.lower()
    if plana in _DEBILES:
        return True
    # Todo el mismo caracter, o digitos consecutivos: 11111111, 12345678.
    cuerpo = clave.strip()
    if len(set(cuerpo)) == 1:
        return True
    if cuerpo.isdigit() and len(cuerpo) > 3:
        seguidos = all(int(cuerpo[i + 1]) - int(cuerpo[i]) == 1
                       for i in range(len(cuerpo) - 1))
        if seguidos:
            return True
    return False


_DEBILES = {
    "12345678", "123456789", "1234567890", "password", "contrasena",
    "contraseña", "qwertyui", "11111111", "00000000", "abcd1234",
    "internet", "administrador", "wifi1234", "clave123",
}


# =============================================================================
#  EJECUTOR  --  lo que corre cuando el modelo llama a la herramienta
# =============================================================================

def procesar(herramienta, argumentos: dict, tenant: str = "",
             variables_tenant: dict | None = None) -> dict:
    """
    Toma el pedido de cambio de WiFi, lo valida y devuelve la traza.

    NO cambia nada en ningun equipo, y el nombre de la herramienta que la
    invoca tampoco lo sugiere ('registrar_pedido_wifi'): el modelo lee ese
    nombre para decidir que hace, y uno que dijera 'cambiar' lo invita a
    contestarle al cliente que ya esta hecho.

    Lo que devuelve alimenta dos cosas distintas:
      - al modelo, para que le diga al cliente que corregir;
      - a 'escalamiento.ticket_al_escalar', que elige el asunto de WispHub
        mirando 'cambia_nombre' / 'cambia_clave' / 'red_oculta' en la traza.
    """
    desaconsejados = (variables_tenant or {}).get("WIFI_CARACTERES_DESACONSEJADOS", "")

    nombre = (argumentos.get("nombre_nuevo") or "").strip("\r\n")
    clave = argumentos.get("clave_nueva") or ""
    # Llega como texto ('si'/'no') porque el esquema de argumentos del motor
    # solo maneja cadenas; se traduce aca a un booleano, que es lo que leen
    # las condiciones de 'ticket_al_escalar'. Ausente = el cliente no dijo
    # nada de ocultarla, que NO es lo mismo que pedir que sea visible.
    crudo = argumentos.get("red_oculta")
    ocultar = None if crudo in (None, "") else str(crudo).strip().lower() in ("si", "true", "1")

    cambia_nombre = bool(nombre)
    cambia_clave = bool(clave)

    problemas = []
    if cambia_nombre:
        problemas += validar_ssid(nombre, desaconsejados)
    if cambia_clave:
        problemas += validar_clave(clave, desaconsejados)

    if not (cambia_nombre or cambia_clave or ocultar is not None):
        problemas.append(
            "No se entendio que hay que cambiar: el nombre de la red, la "
            "clave, o si la red queda oculta.")

    # PRIMER campo a proposito, y no por estetica: la traza que va al ticket
    # recorta cada linea de herramienta a 160 caracteres (ver
    # escalamiento.py::_que_se_probo). Como el JSON conserva el orden, lo
    # que va primero es lo unico que se garantiza que sobreviva -- y esto es
    # lo que quien tome el caso necesita leer de un vistazo. Con los valores
    # ENTRE COMILLAS, para que un espacio al final se vea.
    # Cada parte es una frase COMPLETA, no un fragmento con prefijo comun:
    # "cambiar" no encabeza bien un pedido de ocultar la red.
    partes = []
    if cambia_nombre:
        partes.append(f'cambiar el nombre a "{nombre}"')
    if cambia_clave:
        partes.append(f'cambiar la clave a "{clave}"')
    if ocultar is True:
        partes.append("dejar la red OCULTA")
    elif ocultar is False:
        partes.append("volver la red VISIBLE")
    frase = ", ".join(partes)

    return {
        "pedido": (frase[0].upper() + frase[1:]) if frase else "sin datos",
        "pedido_valido": not problemas,
        # Frases listas para leerle al cliente. Van en plural aunque haya una
        # sola: se le dicen TODAS juntas, no de a una por turno -- corregir un
        # problema para que aparezca el siguiente es la forma mas rapida de
        # que alguien abandone a mitad de camino.
        "problemas": problemas,
        "cambia_nombre": cambia_nombre,
        "cambia_clave": cambia_clave,
        # None cuando el cliente no dijo nada de ocultarla: distinto de False,
        # que es "pidio que vuelva a ser visible".
        "red_oculta": ocultar,
        "nombre_nuevo": nombre,
        # Se avisa, no se rechaza (ver clave_es_debil).
        "clave_debil": cambia_clave and clave_es_debil(clave),
        # Lo que el cliente afirma tener HOY. Va a la traza sin comprobar: el
        # asistente no puede leer la clave actual del equipo, asi que esto es
        # una AFIRMACION que valida la persona que tome el caso. El ticket
        # tiene que decirlo con esas palabras, o quien lo lea va a creer que
        # salio del sistema.
        "nombre_actual_segun_cliente": argumentos.get("nombre_actual") or "",
        "clave_actual_segun_cliente": argumentos.get("clave_actual") or "",
    }
