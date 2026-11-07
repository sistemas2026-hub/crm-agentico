# -*- coding: utf-8 -*-
"""
Los canales por los que entra un turno, y la UNICA forma de nombrarlos.

POR QUE ESTO ES UN MODULO
-------------------------
El canal decide dos cosas que no pueden depender de como lo escribio cada
llamador:

  1. Que sesion en memoria se usa. La clave de 'api._sesiones' era
     (tenant, identificador), sin canal. El simulador usa el telefono como
     identificador -- el mismo que usa el webhook real--, asi que una prueba
     con el numero de un cliente y la conversacion real de ese cliente
     compartian historial, rol activo y estado de escalada en el proceso.

  2. Si /chat puede atender el turno. /chat nunca envia nada a Meta: lo que
     entra por ahi con canal 'whatsapp' queda guardado como un mensaje del
     cliente que el cliente no escribio, y mueve la ventana de 24 h, el
     contador de insistencias y el cierre por plazo. Paso desde la bandeja:
     un operador escribia en una conversacion real no escalada y el texto
     entraba como 'rol = user' (SPEC/CONTRATO_RELEVO_IA_HUMANO.md, D3).

Si cada ruta normalizara a su manera, "WhatsApp" o "whatsapp " esquivarian el
rechazo, y un alias nuevo ("simulado") recrearia la colision de sesiones que
esto viene a cerrar. Por eso hay una sola funcion y se prueba sola
(tests/test_chat_canal.py).

ALIAS
-----
No hay ninguno: al 16/09/2026 los cuatro valores de abajo son los unicos que
escribe algun llamador (inventario de la fase B1). Si alguna vez hace falta
uno, se agrega en _ALIAS y no en la ruta que lo necesita.
"""

from __future__ import annotations

# Entra solo por el webhook firmado de Meta (api.py, _procesar_mensaje_whatsapp),
# que llama a atender_turno() directo y nunca pasa por /chat.
WHATSAPP = "whatsapp"

# Canales que /chat SI atiende. Todos representan a alguien que escribe desde
# dentro de la plataforma, no a un cliente real por un medio externo.
WHATSAPP_SIMULADO = "whatsapp-simulado"   # simulador y bandeja sobre hilos simulados
API = "api"                               # asistente interno de colaboradores, baterias, smoke
CONFIGURACION_GUIADA = "configuracion-guiada"

CONOCIDOS = frozenset({WHATSAPP, WHATSAPP_SIMULADO, API, CONFIGURACION_GUIADA})

# Los que tienen un medio externo detras. /chat los rechaza: el unico camino
# autenticado para un mensaje de ese cliente es su webhook.
REALES = frozenset({WHATSAPP})

ATENDIBLES_POR_CHAT = CONOCIDOS - REALES

_ALIAS: dict[str, str] = {}


class CanalInvalido(ValueError):
    """El valor no corresponde a ningun canal conocido."""


def normalizar_canal(valor: object) -> str:
    """
    El nombre canonico de un canal, o CanalInvalido.

    Ignora mayusculas y espacios alrededor -- lo unico que puede variar sin
    cambiar el significado--, resuelve alias y RECHAZA lo desconocido. Nunca
    cae en un valor por defecto: un canal que no se reconoce no se atiende
    como si fuera otro.
    """
    if not isinstance(valor, str):
        raise CanalInvalido(f"canal no es texto: {type(valor).__name__}")
    limpio = valor.strip().lower()
    limpio = _ALIAS.get(limpio, limpio)
    if limpio not in CONOCIDOS:
        raise CanalInvalido(f"canal desconocido: {valor!r}")
    return limpio


def clave_sesion(tenant: str, canal: str, identificador: str) -> tuple[str, str, str]:
    """
    La clave de 'api._sesiones'. El canal va normalizado y en el medio: el
    mismo telefono por WhatsApp real y por el simulador son dos sesiones.
    """
    return (tenant, normalizar_canal(canal), identificador)


def clave_sesion_de_fila(tenant: str, canal: object,
                         identificador: str) -> tuple[str, str, str] | None:
    """
    La misma clave, para un canal que viene de una fila de la base y no de
    un llamador. Devuelve None en vez de fallar si el canal no se reconoce.

    Lo usan las rutas que LIMPIAN o completan una sesion despues de haber
    escrito (responder, resolver, borrar): ahi un canal historico raro no
    puede convertir en 500 una operacion que ya quedo guardada. Y None es
    exacto, no una aproximacion: una sesion solo se crea con un canal que
    paso normalizar_canal(), asi que con uno desconocido no hay ninguna que
    tocar.
    """
    try:
        return clave_sesion(tenant, canal, identificador)  # type: ignore[arg-type]
    except CanalInvalido:
        return None
