# -*- coding: utf-8 -*-
"""
LOS MODULOS HEREDADOS QUE UNA EMPRESA PUEDE SACAR DEL MENU  --  12/11/2026

Auditoria del menu (SPEC/AUDITORIA_MENU_2026-11-12.md §1.5): un tercio del menu
es herencia de BottleCRM sin alimentacion propia -- Cuentas, Contactos, Base de
conocimiento, Tareas, Metas, Facturas, Registro de horas --. Ninguna la escribe
el motor y varias confunden («¿donde esta la factura del cliente?» -> en
WispHub, no aca).

Que se vea o no es un dato de ESTA empresa, editable desde la interfaz
(CLAUDE.md §3.3): vive en `Org.modulos_ocultos` y lo cambia su ADMIN en
/settings/modulos. Por defecto la lista esta vacia: el dia del despliegue
nadie pierde nada del menu.

OCULTAR NO ES UN PERMISO. La ruta sigue existiendo y sus propias reglas de
acceso siguen valiendo igual: esto solo decide que entradas dibuja el menu. Por
eso no se consulta en ningun permiso ni en ningun queryset.

La lista es cerrada a proposito: una clave desconocida se rechaza al guardar,
asi un error de tipeo no queda guardado como «oculto» sin ocultar nada. El
frontend tiene la misma lista con sus textos (`lib/v2/modulos.js`); la prueba
de cada lado fija las nueve claves.
"""

MODULOS_OCULTABLES = (
    "accounts",
    "contacts",
    "solutions",
    "documents",
    "tasks",
    "pipeline",
    "goals",
    "invoices",
    "timesheet",
)


def normalizar_modulos_ocultos(valor):
    """La lista que se guarda: sin repetidos, en el orden del catalogo.

    Lanza ValueError con un texto para personas si trae algo que no es una
    lista de claves conocidas.
    """
    if valor is None:
        return []
    if not isinstance(valor, (list, tuple)):
        raise ValueError("Tiene que ser una lista de módulos.")
    desconocidos = [v for v in valor if v not in MODULOS_OCULTABLES]
    if desconocidos:
        raise ValueError(
            "Estos módulos no se pueden ocultar: "
            + ", ".join(str(d) for d in desconocidos)
        )
    pedidos = set(valor)
    return [m for m in MODULOS_OCULTABLES if m in pedidos]
