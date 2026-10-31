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
        "descripcion": "Al cliente, un rato después de cerrar un caso que vino de un chat (cuánto, se elige acá).",
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

#: Una plantilla de partida para cada momento (29/10/2026), con QUE dato va en
#: cada {{n}}: el que la crea desde Ajustes -> Plantillas no tiene que adivinar
#: el orden, y al elegirla en Mensajes automaticos los datos ya vienen puestos.
#: Escritas para cualquier empresa (la empresa es un dato, no un texto fijo) y
#: en "usted". Se pueden cambiar antes de mandarlas a Meta; Meta revisa igual.
#: Cada una pasa por armar_plantilla_nueva en tests/test_plantillas_whatsapp.py.
SUGERENCIAS: dict[str, dict] = {
    "ticket_creado_cliente": {
        "nombre": "ticket_creado", "categoria": "UTILITY",
        "cuerpo": "Hola {{1}}, registramos su solicitud con el número {{2}}: {{3}}. "
                  "Le avisaremos por este medio cuando tengamos novedades.",
        "datos": ["cliente_nombre", "ticket_numero", "ticket_asunto"]},
    "ticket_cerrado_cliente": {
        "nombre": "ticket_cerrado", "categoria": "UTILITY",
        "cuerpo": "Hola {{1}}, su caso número {{2}} quedó cerrado. Si el inconveniente "
                  "continúa, responda este mensaje y lo revisamos.",
        "datos": ["cliente_nombre", "ticket_numero"]},
    "ticket_creado_tecnico": {
        "nombre": "orden_asignada_tecnico", "categoria": "UTILITY",
        "cuerpo": "Hola {{1}}, se le asignó un trabajo nuevo. Ticket {{2}}: {{3}}. "
                  "Cliente {{4}}, en {{5}}. Fecha de la visita: {{6}}. "
                  "Encuentra todos los detalles en la aplicación de campo.",
        "datos": ["tecnico_nombre", "ticket_numero", "ticket_asunto",
                  "cliente_nombre_completo", "cliente_direccion", "fecha_visita"]},
    "seguimiento_ticket": {
        "nombre": "seguimiento_caso", "categoria": "UTILITY",
        "cuerpo": "Hola {{1}}, le escribimos por su caso de soporte: {{2}}. "
                  "Si necesita algo más, responda este mensaje.",
        "datos": ["cliente_nombre", "escrito"]},
    "encuesta_cierre": {
        "nombre": "encuesta_satisfaccion", "categoria": "UTILITY",
        "cuerpo": "Hola {{1}}, cerramos su caso de soporte. "
                  "¿Cómo calificaría la atención que recibió?",
        "pie": "Su respuesta nos ayuda a mejorar",
        "botones": ["Excelente", "Buena", "Regular", "Mala"],
        "datos": ["cliente_nombre"]},
    "recordatorio_pago": {
        "nombre": "recordatorio_pago", "categoria": "UTILITY",
        "cuerpo": "Hola {{1}}, le recordamos que su factura {{2}} por {{3}} del servicio {{4}} "
                  "vence el {{5}}. Pagarla a tiempo evita la suspensión del servicio.",
        "datos": ["cliente_nombre", "factura_numero", "total", "servicio", "fecha_corte"]},
    "confirmacion_pago": {
        "nombre": "pago_recibido", "categoria": "UTILITY",
        "cuerpo": "Hola {{1}}, recibimos su pago de {{2}} del {{3}} para el servicio {{4}}. "
                  "Gracias por mantenerse al día.",
        "datos": ["cliente_nombre", "total", "fecha_pago", "servicio"]},
    "rechazo_pago": {
        "nombre": "pago_no_aceptado", "categoria": "UTILITY",
        "cuerpo": "Hola {{1}}, no pudimos aceptar el comprobante de pago que nos envió porque {{2}}. "
                  "Por favor envíenos uno nuevo respondiendo este mensaje.",
        "datos": ["cliente_nombre", "motivo_rechazo"]},
    "promesa_pago": {
        "nombre": "promesa_de_pago", "categoria": "UTILITY",
        "cuerpo": "Hola {{1}}, registramos su compromiso de pagar {{2}} a más tardar el {{3}}. "
                  "Si ya realizó el pago, puede ignorar este mensaje.",
        "datos": ["cliente_nombre", "total", "fecha_promesa"]},
    "suspension": {
        "nombre": "servicio_suspendido", "categoria": "UTILITY",
        "cuerpo": "Hola {{1}}, su servicio {{2}} fue suspendido por un saldo pendiente de {{3}}. "
                  "Si ya pagó, responda este mensaje con el comprobante y lo revisamos.",
        "datos": ["cliente_nombre", "servicio", "total"]},
    "bienvenida": {
        "nombre": "bienvenida_servicio", "categoria": "UTILITY",
        "cuerpo": "Hola {{1}}, bienvenido a {{2}}. Su servicio {{3}} con el plan {{4}} ya está activo. "
                  "Si necesita ayuda, escríbanos por este medio.",
        "datos": ["cliente_nombre", "empresa", "servicio", "plan"]},
}


def sugerencia(evento: str) -> dict | None:
    """La sugerencia del momento lista para el formulario: con un ejemplo por dato."""
    s = SUGERENCIAS.get(evento)
    if s is None:
        return None
    return {"encabezado": "", "pie": "", "botones": [], **s,
            "ejemplos": [CAMPOS[d][1] for d in s["datos"]]}


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
