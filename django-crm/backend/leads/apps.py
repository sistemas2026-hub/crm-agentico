from django.apps import AppConfig


class LeadsConfig(AppConfig):
    name = "leads"

    def ready(self):
        # El origen WhatsApp del prospecto que registra el asistente
        # (12/11/2026): ver leads/senales.py. Referencia perezosa al modelo:
        # 'leads' no importa 'solicitudes' al arrancar.
        from django.db.models.signals import post_save

        from leads.senales import origen_del_asistente

        post_save.connect(origen_del_asistente, sender="solicitudes.SolicitudServicio",
                          dispatch_uid="leads.origen_del_asistente")
