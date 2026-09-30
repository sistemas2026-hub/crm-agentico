# -*- coding: utf-8 -*-
"""
================================================================================
 COMO SE LLAMA UN CASO EN LA BANDEJA
================================================================================

Modulo propio y sin dependencias, por el mismo motivo que forzado.py:
escalamiento.py arrastra la base de datos, y esto tiene que poder comprobarse
sin levantar nada -- es texto, no I/O.

No es cosmetico. El nombre es lo UNICO que se ve de un caso antes de abrirlo,
tiene que ser unico dentro de la empresa, y el CRM lo rechaza entero si se
pasa de largo. Ver tests/test_nombre_del_caso.py y el bug que lo motivo.
"""

from __future__ import annotations


# El CRM acepta 64 caracteres en el nombre del caso, ni uno mas: responde 400
# con "Ensure this field has no more than 64 characters".
LARGO_NOMBRE_CASO = 64


def nombre_del_caso(asunto: str, cliente: str, conversation_id: str) -> str:
    """
    Como se llama el caso en la bandeja: asunto, cliente e identificador.

    Los tres tramos no caben siempre en 64 caracteres, asi que hay que
    recortar -- y lo que se recorta importa:

      - el ID va ENTERO. Es lo unico que hace unico al nombre (el CRM rechaza
        uno repetido con 400) y lo que permite cruzar el caso con su
        conversacion.
      - el ASUNTO va entero. Sale del catalogo del ISP y es lo que decide a
        quien le toca y con que urgencia.
      - se recorta el NOMBRE DEL CLIENTE, que es lo unico redundante: esta
        completo dentro del caso y en la ficha del cliente.

    Paso el 28/08/2026: un caso llego a 68 caracteres y el CRM lo rechazo. El
    nombre entraba mientras el cliente NO estaba identificado --ahi iba su
    telefono, mas corto-- asi que arreglar la verificacion destapo este limite.
    """
    cola = f" · #{conversation_id[:8]}"
    cabeza = (asunto or "Consulta").strip()
    cliente = (cliente or "").strip()
    espacio = LARGO_NOMBRE_CASO - len(cabeza) - len(cola) - 3   # 3 = ' · '
    if not cliente or espacio < 4:
        # Sin lugar para el cliente, se va: el asunto y el id son los que no
        # se pueden perder. Y si NI ASI entra, se recorta el asunto -- feo,
        # pero un nombre feo es mejor que un caso que no se crea.
        return (cabeza + cola)[:LARGO_NOMBRE_CASO]
    if len(cliente) > espacio:
        cliente = cliente[:espacio - 1].rstrip() + "…"
    return f"{cabeza} · {cliente}{cola}"
