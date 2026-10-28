# -*- coding: utf-8 -*-
"""
================================================================================
 MENSAJES AUTOMATICOS: QUE MOMENTOS HAY Y QUE DATOS OFRECE CADA UNO (28/10/2026)
================================================================================

La plantilla en Meta lleva {{1}}, {{2}}...; QUE va en cada numero lo decide la
empresa, eligiendo de esta lista -- como en el CRM que se reemplaza, donde cada
aviso tenia su plantilla y sus "opciones" en orden.

Esto es el CATALOGO, y es del motor: los momentos que Dexter sabe disparar y
los datos que tiene a mano en cada uno. Es igual para toda empresa. Lo que
varia --que plantilla, que datos, si esta encendido-- vive en la config del
tenant ('mensajes_automaticos'), y se valida contra esto.

Un dato que no existe en un momento NO se ofrece en ese momento: "total a
pagar" al cerrar un ticket se llenaria vacio, y Meta rechaza un valor vacio.
================================================================================
"""

from __future__ import annotations

#: dato -> (como se llama en la pantalla, un ejemplo para la vista previa)
CAMPOS: dict[str, tuple[str, str]] = {
    "cliente_nombre": ("Nombre del cliente", "Juan"),
    "cliente_apellidos": ("Apellidos del cliente", "Pérez Gómez"),
    "cliente_nombre_completo": ("Nombre completo del cliente", "Juan Pérez Gómez"),
    "cliente_direccion": ("Dirección del cliente", "Calle 10 # 5-20"),
    "empresa": ("Nombre de la empresa", "Tu empresa"),
    "servicio": ("Número de servicio", "5832"),
    "plan": ("Plan contratado", "Fibra 100 Mb"),
    "ticket_numero": ("Número de ticket", "95001"),
    "ticket_asunto": ("Asunto del ticket", "No tiene internet"),
    "responsable": ("Quien atiende el caso", "Ana"),
    "tecnico_nombre": ("Nombre del técnico", "Luis"),
    "fecha": ("Fecha de hoy", "28/10/2026"),
    "fecha_visita": ("Fecha de la visita", "30/10/2026"),
    "factura_numero": ("Número de factura", "F-10234"),
    "total": ("Total a pagar", "$ 85.000"),
    "fecha_corte": ("Fecha de corte", "05/11/2026"),
    "fecha_pago": ("Fecha del pago", "28/10/2026"),
    "fecha_promesa": ("Fecha prometida de pago", "02/11/2026"),
    "enlace_factura": ("Enlace a la factura", "https://…/factura"),
    "motivo_rechazo": ("Por qué se rechazó el pago", "el comprobante no se lee"),
    "escrito": ("Lo escribe quien envía", "ya revisamos tu equipo"),
}

_CLIENTE = ["cliente_nombre", "cliente_apellidos", "cliente_nombre_completo", "empresa", "fecha"]

#: evento -> lo que la pantalla y el motor necesitan saber de el.
#:   grupo         para agrupar en la pantalla
#:   destinatario  'cliente' | 'tecnico'
#:   disparo       'dexter' (ocurre en Dexter) | 'diario' (tarea diaria contra
#:                 el sistema del ISP) | 'manual' (lo manda una persona)
EVENTOS: dict[str, dict] = {
    "ticket_creado_cliente": {
        "grupo": "Tickets", "etiqueta": "Ticket creado",
        "descripcion": "Al cliente, cuando se le abre un ticket.",
        "destinatario": "cliente", "disparo": "dexter",
        "campos": _CLIENTE + ["servicio", "ticket_numero", "ticket_asunto"]},
    "ticket_cerrado_cliente": {
        "grupo": "Tickets", "etiqueta": "Ticket cerrado",
        "descripcion": "Al cliente, cuando su caso se cierra.",
        "destinatario": "cliente", "disparo": "dexter",
        "campos": _CLIENTE + ["servicio", "ticket_numero", "ticket_asunto", "responsable"]},
    "ticket_creado_tecnico": {
        "grupo": "Tickets", "etiqueta": "Trabajo asignado al técnico",
        "descripcion": "Al técnico, cuando se le asigna una orden. Usa el celular de su perfil.",
        "destinatario": "tecnico", "disparo": "dexter",
        "campos": ["tecnico_nombre", "cliente_nombre", "cliente_apellidos", "cliente_nombre_completo",
                   "cliente_direccion", "servicio", "ticket_numero", "ticket_asunto",
                   "fecha_visita", "empresa", "fecha"]},
    "seguimiento_ticket": {
        "grupo": "Tickets", "etiqueta": "Seguimiento desde el ticket",
        "descripcion": "La que se manda a mano desde un ticket cuando pasaron más de 24 h.",
        "destinatario": "cliente", "disparo": "manual",
        "campos": _CLIENTE + ["servicio", "ticket_numero", "ticket_asunto", "responsable", "escrito"]},
    "encuesta_cierre": {
        "grupo": "Tickets", "etiqueta": "Encuesta de satisfacción",
        "descripcion": "Al cliente, 30 minutos después de cerrar un caso que vino de un chat.",
        "destinatario": "cliente", "disparo": "dexter",
        "campos": _CLIENTE + ["ticket_numero", "responsable"]},
    "recordatorio_pago": {
        "grupo": "Pagos", "etiqueta": "Recordatorio de pago",
        "descripcion": "Al cliente, antes de la fecha de corte de su factura.",
        "destinatario": "cliente", "disparo": "diario",
        "campos": _CLIENTE + ["servicio", "factura_numero", "total", "fecha_corte", "enlace_factura"]},
    "confirmacion_pago": {
        "grupo": "Pagos", "etiqueta": "Confirmación de pago",
        "descripcion": "Al cliente, cuando se registra su pago.",
        "destinatario": "cliente", "disparo": "dexter",
        "campos": _CLIENTE + ["servicio", "factura_numero", "total", "fecha_pago"]},
    "rechazo_pago": {
        "grupo": "Pagos", "etiqueta": "Rechazo de pago",
        "descripcion": "Al cliente, cuando un comprobante que mandó no se puede aceptar.",
        "destinatario": "cliente", "disparo": "dexter",
        "campos": _CLIENTE + ["servicio", "factura_numero", "motivo_rechazo"]},
    "promesa_pago": {
        "grupo": "Pagos", "etiqueta": "Promesa de pago",
        "descripcion": "Al cliente, cuando queda registrada su promesa de pago.",
        "destinatario": "cliente", "disparo": "dexter",
        "campos": _CLIENTE + ["servicio", "fecha_promesa", "total"]},
    "suspension": {
        "grupo": "Servicio", "etiqueta": "Suspensión del servicio",
        "descripcion": "Al cliente, cuando su servicio pasa a suspendido.",
        "destinatario": "cliente", "disparo": "diario",
        "campos": _CLIENTE + ["servicio", "total", "fecha_corte"]},
    "bienvenida": {
        "grupo": "Servicio", "etiqueta": "Bienvenida",
        "descripcion": "Al cliente, cuando queda activo su servicio nuevo.",
        "destinatario": "cliente", "disparo": "dexter",
        "campos": _CLIENTE + ["servicio", "plan"]},
}

#: Si un dato llega vacio, que se manda en su lugar (Meta rechaza un valor
#: vacio). Cada empresa puede cambiarlos en 'respaldos_mensajes'.
#: Los momentos cuyo DISPARADOR ya esta construido. Los demas se pueden dejar
#: configurados desde la pantalla, que dice que todavia no se mandan: un aviso
#: encendido que nunca sale es peor que uno que dice "todavia no".
LISTOS: frozenset[str] = frozenset({"seguimiento_ticket", "encuesta_cierre"})

RESPALDOS_POR_DEFECTO: dict[str, str] = {
    "cliente_nombre": "cliente",
    "cliente_nombre_completo": "cliente",
    "tecnico_nombre": "técnico",
}
