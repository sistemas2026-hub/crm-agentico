from __future__ import absolute_import, unicode_literals

import os

from celery import Celery, signals
from celery.schedules import crontab

# set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "crm.settings")
# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.dev_settings')
# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.server_settings')

app = Celery("crm")


# =============================================================================
#  UNA CONEXION FRESCA POR TAREA  --  08/10/2026
# =============================================================================
#  LO QUE PASO, medido en produccion. El worker arranco a las 00:06:23 UTC tras
#  un despliegue y a las 00:07:00 --treinta y siete segundos despues-- el ciclo
#  del Supervisor murio en su PRIMERA consulta:
#
#      psycopg.errors.AdminShutdown:
#      terminating connection due to administrator command
#
#  La base estaba sana: 'scan_for_breached_cases' corrio bien tres minutos mas
#  tarde. Lo que estaba muerto era ESA conexion, cortada del lado del servidor
#  durante el reinicio, y el worker se la quedo sin enterarse.
#
#  POR QUE PASA, y por que le pasa a las TRECE tareas y no a una
#  --------------------------------------------------------------
#  Django cierra la conexion al terminar cada peticion HTTP, y con
#  'CONN_MAX_AGE: 0' esa es justo la politica configurada aqui. Pero un worker
#  de Celery NO pasa por el ciclo de peticion: no hay 'request_finished' que
#  dispare el cierre, asi que la misma conexion viaja de una tarea a la
#  siguiente durante horas. Si algo la mata del otro lado --un despliegue, un
#  reinicio de la base, un 'pg_terminate_backend'-- la proxima tarea que la
#  tome revienta. No es un problema del ciclo del Supervisor: fue la primera
#  en tocarla, nada mas.
#
#  'close_old_connections' es exactamente lo que Django hace entre peticiones,
#  y es el remedio documentado para esto. Con 'CONN_MAX_AGE: 0' descarta la
#  conexion siempre, asi que cada tarea abre la suya y ninguna hereda una
#  rota.
#
#  LAS DOS SEÑALES Y NO UNA: 'prerun' resuelve el caso medido --arrancar con
#  una conexion heredada-- y 'postrun' evita dejar abierta la propia al
#  terminar, que es la otra mitad de la misma politica.
#
#  NO REEMPLAZA AL MANEJO DE ERRORES DE CADA TAREA: una conexion puede morir a
#  mitad de camino, y eso lo tiene que atrapar quien hace el trabajo. Esto
#  solo garantiza el punto de partida.
#  EL IMPORT VA ADENTRO, y no arriba: 'crm/__init__.py' importa este modulo al
#  cargar el paquete, o sea en pleno arranque de Django y antes de que las
#  aplicaciones esten listas. Traer 'django.db' en ese momento es el tipo de
#  import circular que funciona en una maquina y falla en otra segun el orden
#  de carga. Adentro corre cuando ya hay tarea, que es cuando hace falta.
@signals.task_prerun.connect
def _conexion_fresca(**_):
    from django.db import close_old_connections

    close_old_connections()


@signals.task_postrun.connect
def _soltar_conexion(**_):
    from django.db import close_old_connections

    close_old_connections()

# Using a string here means the worker don't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()
app.autodiscover_tasks(related_name="celery_tasks")  # tasks app uses celery_tasks.py

# Celery Beat Schedule for recurring tasks
app.conf.beat_schedule = {
    # Generate invoices from recurring invoice templates - daily at midnight
    "generate-recurring-invoices": {
        "task": "invoices.tasks.generate_recurring_invoices",
        "schedule": crontab(hour=0, minute=0),
    },
    # Mark overdue invoices - daily at 1 AM
    "check-overdue-invoices": {
        "task": "invoices.tasks.check_overdue_invoices",
        "schedule": crontab(hour=1, minute=0),
    },
    # Process payment reminders - daily at 9 AM
    "process-payment-reminders": {
        "task": "invoices.tasks.process_payment_reminders",
        "schedule": crontab(hour=9, minute=0),
    },
    # Mark expired estimates - daily at midnight
    "check-expired-estimates": {
        "task": "invoices.tasks.check_expired_estimates",
        "schedule": crontab(hour=0, minute=30),
    },
    # Check for stale/rotten opportunities - daily at 8 AM
    "check-stale-opportunities": {
        "task": "opportunity.tasks.check_stale_opportunities",
        "schedule": crontab(hour=8, minute=0),
    },
    # Check goal milestones and send notifications - daily at 9:15 AM
    "check-goal-milestones": {
        "task": "opportunity.tasks.check_goal_milestones",
        "schedule": crontab(hour=9, minute=15),
    },
    # Scan cases for SLA breach and fire configured escalations - every 5 minutes
    "scan-for-breached-cases": {
        "task": "cases.tasks.scan_for_breached_cases",
        "schedule": crontab(minute="*/5"),
    },
    # Purge already-read in-app notifications older than 90 days - daily at 3 AM
    "purge-read-notifications": {
        "task": "common.tasks.purge_read_notifications",
        "schedule": crontab(hour=3, minute=0),
    },
    # Stop forgotten time-tracking timers older than 12 hours - every 30 minutes
    "auto-stop-stale-timers": {
        "task": "cases.tasks.auto_stop_stale_timers",
        "schedule": crontab(minute="*/30"),
    },
    # Drop rotated/expired refresh token records - daily at 3:30 AM
    "flush-expired-refresh-tokens": {
        "task": "common.tasks.flush_expired_refresh_tokens",
        "schedule": crontab(hour=3, minute=30),
    },
    # Aplica la retencion del asistente: adjuntos vencidos (30 dias) y
    # conversaciones vencidas (365). Hasta ahora esos plazos estaban declarados
    # en la configuracion del tenant y no los ejecutaba nadie. Diaria, 4 AM.
    "purgar-retencion-asistente": {
        "task": "common.tasks.purgar_retencion_asistente",
        "schedule": crontab(hour=4, minute=0),
    },
    # El ciclo del Supervisor NOC: detecta lo que cambio, deja propuestas y
    # cierra lo que este delegado. Cada hora, en el minuto 7.
    #
    # EL MINUTO 7 Y NO EL 0, a proposito: a la hora en punto ya arrancan
    # 'scan-for-breached-cases' (cada 5 min cae en :00) y las cuatro diarias de
    # medianoche. Un ciclo que puede tardar un minuto largo --tres diagnosticos
    # de ~10 s contra SmartOLT, mas los cierres-- compitiendo con la rafaga de
    # :00 en un worker de concurrencia modesta es latencia que no hace falta
    # pagar. Siete minutos de corrimiento no le cambian nada a nadie.
    #
    # CADA HORA Y NO MAS SEGUIDO: el ciclo mira tickets que llegan de WispHub
    # por la sincronizacion, que corre cada 60 minutos. Mirar cada 15 seria
    # preguntarle cuatro veces por el mismo dato -- y cada pasada que encuentra
    # un caso nuevo gasta presupuesto de diagnostico contra un tercero que pide
    # explicitamente no hacer polling.
    #
    # NO HABILITA NADA. Solo corre para las empresas que delegaron el ciclo
    # ('operaciones/tareas_delegadas.py::CICLO_AUTOMATICO'); sin esa fila, la
    # tarea no recorre ninguna. Ver el encabezado de 'operaciones/tasks.py'.
    "ciclo-del-supervisor": {
        "task": "operaciones.tasks.ciclo_del_supervisor",
        "schedule": crontab(minute=7),
    },
}
