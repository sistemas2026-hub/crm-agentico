from django.apps import AppConfig


class CasesConfig(AppConfig):
    name = "cases"

    def ready(self):
        import cases.signals  # noqa: F401  # pylint: disable=unused-import

        # La Base de conocimiento entra al corpus del asistente (12/11/2026).
        # Importarlo aca registra sus señales y sus tareas de Celery.
        import cases.kb_asistente  # noqa: F401  # pylint: disable=unused-import
