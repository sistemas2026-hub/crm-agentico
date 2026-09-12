import logging
from datetime import timedelta

from botocore.exceptions import ClientError
from celery import shared_task
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage
from django.core.validators import validate_email
from django.db import connection
from django.template.loader import render_to_string
from django.utils import timezone

from common.links import frontend_url
from common.models import (
    MagicLinkToken,
    Notification,
    Org,
    Profile,
    Teams,
    User,
)

logger = logging.getLogger(__name__)


def set_rls_context(org_id):
    """
    Set RLS context for Celery tasks that query org-scoped tables.

    Celery workers don't go through Django middleware, so RLS context
    must be set explicitly before querying org-scoped data.

    Args:
        org_id: Organization UUID (string or UUID object)
    """
    # SQLite (test backend) has no set_config(). RLS is a Postgres feature.
    if connection.vendor != "postgresql":
        return
    if org_id:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT set_config('app.current_org', %s, false)", [str(org_id)]
            )


def clear_rls_context():
    """Drop the RLS context a task set, mirroring the middleware's reset.

    `app.current_org` is set at SESSION scope, so it outlives the statement and
    the transaction. A task that walks several orgs and then returns leaves the
    last one's id on the connection, and on a pooled connection that is the next
    borrower's tenant context. Always paired with `set_rls_context` in a
    ``finally``.
    """
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.current_org', '', false)")


@shared_task
def send_welcome_email(user_id):
    """Send welcome email to newly created users."""
    user_obj = User.objects.filter(id=user_id).first()
    if not user_obj:
        return

    email = user_obj.email.strip()
    try:
        validate_email(email)
    except ValidationError:
        logger.warning("Welcome email skipped: invalid email for user %s", user_id)
        return

    context = {"url": settings.FRONTEND_URL}
    subject = "Welcome to BottleCRM"
    html_content = render_to_string("welcome_email.html", context=context)

    msg = EmailMessage(
        subject,
        html_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    msg.content_subtype = "html"
    try:
        msg.send()
    except ClientError:
        logger.exception("SES rejected welcome email for user %s", user_id)


@shared_task
def send_magic_link_email(token_id, raw_code=None):
    """Send a magic-link or OTP-code email for passwordless authentication.

    For `delivery == "code"` rows, the caller passes `raw_code` (the plaintext
    OTP), only the hash is stored on the token row, so the plaintext can't be
    recovered from the DB by this task.
    """
    magic_token = MagicLinkToken.objects.filter(id=token_id).first()
    if not magic_token:
        return

    email = magic_token.email.strip()
    try:
        validate_email(email)
    except ValidationError:
        logger.warning(
            "Magic link skipped: invalid email format for token %s", token_id
        )
        return

    if magic_token.delivery == "code":
        if not raw_code:
            logger.warning(
                "Magic link skipped: raw_code missing for code-delivery token %s",
                token_id,
            )
            return
        subject = f"Your BottleCRM sign-in code: {raw_code}"
        html_content = render_to_string(
            "magic_link_code_email.html",
            {"code": raw_code},
        )
    else:
        magic_link_url = (
            f"{settings.FRONTEND_URL}/login/verify?token={magic_token.token}"
        )
        subject = "Your BottleCRM sign-in link"
        html_content = render_to_string(
            "magic_link_email.html",
            {"magic_link_url": magic_link_url},
        )

    msg = EmailMessage(
        subject,
        html_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    msg.content_subtype = "html"
    try:
        msg.send()
    except ClientError:
        logger.exception("SES rejected email for magic link token %s", token_id)


@shared_task
def send_email_user_status(
    user_id,
    status_changed_user="",
):
    """Send Mail To Users Regarding their status i.e active or inactive"""
    user = User.objects.filter(id=user_id).first()
    if user:
        context = {}
        context["message"] = "deactivated"
        context["email"] = user.email
        # The web app's root is the dashboard. There is no `/marketing` route,
        # and `has_marketing_access` is a profile flag rather than a user one,
        # so the branch that appended it could never have been reached from a
        # `User` in the first place.
        context["url"] = frontend_url("/")
        if user.is_active:
            context["message"] = "activated"
        context["status_changed_user"] = status_changed_user
        if context["message"] == "activated":
            subject = "Account Activated "
            html_content = render_to_string(
                "user_status_activate.html", context=context
            )
        else:
            subject = "Account Deactivated "
            html_content = render_to_string(
                "user_status_deactivate.html", context=context
            )
        recipients = []
        recipients.append(user.email)
        if recipients:
            msg = EmailMessage(
                subject,
                html_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipients,
            )
            msg.content_subtype = "html"
            msg.send()


@shared_task
def send_email_user_delete(
    user_email,
    deleted_by="",
):
    """Send Mail To Users When their account is deleted"""
    if user_email:
        context = {}
        context["message"] = "deleted"
        context["deleted_by"] = deleted_by
        context["email"] = user_email
        recipients = []
        recipients.append(user_email)
        subject = "CRM : Your account is Deleted. "
        html_content = render_to_string("user_delete_email.html", context=context)
        if recipients:
            msg = EmailMessage(
                subject,
                html_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=recipients,
            )
            msg.content_subtype = "html"
            msg.send()


@shared_task
def remove_users(removed_users_list, team_id, org_id=None):
    # Set RLS context for org-scoped queries
    set_rls_context(org_id)

    removed_users_list = [i for i in removed_users_list if i.isdigit()]
    users_list = Profile.objects.filter(id__in=removed_users_list)
    if users_list.exists():
        team = Teams.objects.filter(id=team_id).first()
        if team:
            accounts = team.account_teams.all()
            for account in accounts:
                for user in users_list:
                    account.assigned_to.remove(user)

            contacts = team.contact_teams.all()
            for contact in contacts:
                for user in users_list:
                    contact.assigned_to.remove(user)

            leads = team.lead_teams.all()
            for lead in leads:
                for user in users_list:
                    lead.assigned_to.remove(user)

            opportunities = team.oppurtunity_teams.all()
            for opportunity in opportunities:
                for user in users_list:
                    opportunity.assigned_to.remove(user)

            cases = team.cases_teams.all()
            for case in cases:
                for user in users_list:
                    case.assigned_to.remove(user)

            docs = team.document_teams.all()
            for doc in docs:
                for user in users_list:
                    doc.shared_to.remove(user)

            tasks = team.tasks_teams.all()
            for task in tasks:
                for user in users_list:
                    task.assigned_to.remove(user)

            invoices = team.invoices_teams.all()
            for invoice in invoices:
                for user in users_list:
                    invoice.assigned_to.remove(user)


@shared_task
def update_team_users(team_id, org_id=None):
    """this function updates assigned_to field on all models when a team is updated"""
    # Set RLS context for org-scoped queries
    set_rls_context(org_id)

    team = Teams.objects.filter(id=team_id).first()
    if team:
        teams_members = team.users.all()

        accounts = team.account_teams.all()
        for account in accounts:
            account_assigned_to_users = account.assigned_to.all()
            for team_member in teams_members:
                if team_member not in account_assigned_to_users:
                    account.assigned_to.add(team_member)

        contacts = team.contact_teams.all()
        for contact in contacts:
            contact_assigned_to_users = contact.assigned_to.all()
            for team_member in teams_members:
                if team_member not in contact_assigned_to_users:
                    contact.assigned_to.add(team_member)

        leads = team.lead_teams.all()
        for lead in leads:
            lead_assigned_to_users = lead.assigned_to.all()
            for team_member in teams_members:
                if team_member not in lead_assigned_to_users:
                    lead.assigned_to.add(team_member)

        opportunities = team.oppurtunity_teams.all()
        for opportunity in opportunities:
            opportunity_assigned_to_users = opportunity.assigned_to.all()
            for team_member in teams_members:
                if team_member not in opportunity_assigned_to_users:
                    opportunity.assigned_to.add(team_member)

        cases = team.cases_teams.all()
        for case in cases:
            case_assigned_to_users = case.assigned_to.all()
            for team_member in teams_members:
                if team_member not in case_assigned_to_users:
                    case.assigned_to.add(team_member)

        docs = team.document_teams.all()
        for doc in docs:
            doc_assigned_to_users = doc.shared_to.all()
            for team_member in teams_members:
                if team_member not in doc_assigned_to_users:
                    doc.shared_to.add(team_member)

        tasks = team.tasks_teams.all()
        for task in tasks:
            task_assigned_to_users = task.assigned_to.all()
            for team_member in teams_members:
                if team_member not in task_assigned_to_users:
                    task.assigned_to.add(team_member)

        invoices = team.invoices_teams.all()
        for invoice in invoices:
            invoice_assigned_to_users = invoice.assigned_to.all()
            for team_member in teams_members:
                if team_member not in invoice_assigned_to_users:
                    invoice.assigned_to.add(team_member)


# Default cutoff for purging read notifications. Per
# `docs/cases/tier2/in-app-notifications.md` "Storage growth".
NOTIFICATION_PURGE_DAYS = 90


@shared_task
def purge_read_notifications(days=NOTIFICATION_PURGE_DAYS):
    """Delete already-read notifications older than ``days`` days.

    Schedule via celery-beat (recommended cadence: nightly). Walks orgs and sets
    the RLS context for each, because `notification` is org-scoped.

    THIS USED TO DELETE NOTHING IN PRODUCTION. The previous version ran one
    unscoped DELETE and justified it in its own docstring: "RLS does not need a
    per-org context here because the query targets `read_at`, which is intrinsic
    to the row". That is not how RLS works. A policy filters which rows the
    statement can see at all, whatever the WHERE clause names, and the isolation
    policy is `org_id::text = NULLIF(current_setting('app.current_org', true),
    '')`, which matches nothing when the context is empty. A Celery worker runs
    no middleware, so the context was always empty, and under the non-superuser
    role the deployment docs mandate, the nightly DELETE removed zero rows every
    night while logging nothing (it only logs when `deleted` is truthy).

    It passed its tests because `crm.test_settings` is SQLite, which has no RLS
    at all. `set_rls_context` returns early on any non-Postgres vendor, so the
    per-org loop is a no-op there and the tests still describe real behaviour on
    both backends.

    The context is cleared at the end. It is set at SESSION scope, so leaving
    the last org's id on a pooled connection would hand that tenant's context to
    whatever borrows the connection next.
    """
    cutoff = timezone.now() - timedelta(days=days)
    deleted = 0
    try:
        for org_id in Org.objects.values_list("id", flat=True).iterator():
            set_rls_context(org_id)
            removed, _ = Notification.objects.filter(
                read_at__isnull=False, read_at__lt=cutoff
            ).delete()
            deleted += removed
    finally:
        clear_rls_context()
    if deleted:
        logger.info("Purged %s read notifications older than %s days", deleted, days)
    return deleted


@shared_task
def flush_expired_refresh_tokens():
    """Delete refresh-token bookkeeping rows whose tokens have already expired.

    `OrgAwareTokenRefreshView` rotates refresh tokens, so simplejwt writes one
    `OutstandingToken` row per token minted and one `BlacklistedToken` row per
    rotation. An expired token is rejected on its `exp` claim regardless of
    blacklist state, so those rows stop carrying security value once
    `expires_at` passes, and would otherwise grow unbounded, one row per login
    and per refresh. Deleting the outstanding row cascades to its blacklist
    entry.

    Equivalent to simplejwt's `manage.py flushexpiredtokens`; schedule via
    celery-beat (nightly is plenty). Not org-scoped; `expires_at` is intrinsic
    to the row, so no RLS context is needed.

    Returns the number of outstanding-token rows removed.
    """
    from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

    expired = OutstandingToken.objects.filter(expires_at__lte=timezone.now())
    count = expired.count()
    if count:
        expired.delete()
        logger.info("Flushed %s expired refresh token records", count)
    return count


# =============================================================================
#  INGESTA AL CORPUS DEL ASISTENTE
# =============================================================================
#  Un documento entra al RAG solo si alguien marca `usar_en_asistente`. Aqui
#  tambien viven contratos y archivos administrativos, y no tienen por que
#  alimentar al asistente.
#
#  Por que el trabajo lo hace el worker y no el motor solo: el motor no ve el
#  directorio de medios (docker-compose le monta unicamente ./nucleo, ./tenants,
#  ./corpus y ./cli), mientras que backend, worker y beat comparten /app/media.
#  El worker tiene los bytes, asi que los empuja por HTTP. Ademas asi sigue
#  funcionando el dia que el almacenamiento sea S3 en vez de disco local.


def _motor():
    """(url, tenant) del motor, o (None, None) si no esta configurado."""
    import os

    return os.environ.get("ASISTENTE_URL"), os.environ.get("ASISTENTE_TENANT")


@shared_task
def ingerir_documento_en_asistente(document_id, org_id):
    """
    Fragmenta, vectoriza y publica un documento en el corpus del asistente.

    Es asincrona porque no es barata: un documento se parte en 2-12 fragmentos
    y cada uno es una llamada al modelo de embeddings. Dejar eso dentro de la
    peticion colgaria el formulario de subida.
    """
    import requests

    from common.models import Document

    set_rls_context(org_id)

    try:
        doc = Document.objects.get(id=document_id, org_id=org_id)
    except Document.DoesNotExist:
        logger.warning("Ingesta: el documento %s ya no existe", document_id)
        return

    url, tenant = _motor()
    if not url or not tenant:
        # Configuracion faltante, no un fallo del documento: se dice tal cual
        # en vez de dejarlo en "procesando" para siempre.
        doc.estado_ingesta = "error"
        doc.ingesta_detalle = (
            "El asistente no esta configurado: faltan ASISTENTE_URL / "
            "ASISTENTE_TENANT en el entorno del backend."
        )
        doc.ingesta_actualizada_en = timezone.now()
        doc.save(update_fields=["estado_ingesta", "ingesta_detalle",
                                "ingesta_actualizada_en"])
        return

    doc.estado_ingesta = "procesando"
    doc.ingesta_actualizada_en = timezone.now()
    doc.save(update_fields=["estado_ingesta", "ingesta_actualizada_en"])

    try:
        with doc.document_file.open("rb") as f:
            datos = f.read()
        nombre = doc.document_file.name.rsplit("/", 1)[-1]

        r = requests.post(
            f"{url.rstrip('/')}/corpus/documentos",
            files={"archivo": (nombre, datos)},
            data={
                "tenant": tenant,
                # Respaldo: si el .docx trae su propia tabla de roles, esa
                # manda -- el valor viaja con el documento.
                "roles": doc.roles_asistente or "",
                "storage_path": doc.document_file.name,
                # Reingesta explicita: si alguien vuelve a marcar un documento
                # ya cargado, se espera que se rehaga.
                "forzar": "true",
            },
            timeout=900,
        )
        cuerpo = r.json()
        if not r.ok:
            raise RuntimeError(cuerpo.get("error") or f"HTTP {r.status_code}")
    except Exception as e:
        logger.exception("Ingesta: fallo el documento %s", document_id)
        doc.estado_ingesta = "error"
        doc.ingesta_detalle = str(e)[:2000]
        doc.ingesta_actualizada_en = timezone.now()
        doc.save(update_fields=["estado_ingesta", "ingesta_detalle",
                                "ingesta_actualizada_en"])
        return

    defectos = cuerpo.get("defectos") or []
    roles = cuerpo.get("roles_permitidos") or []
    doc.corpus_document_id = cuerpo.get("document_id")
    doc.estado_ingesta = "ok"
    doc.ingesta_fragmentos = cuerpo.get("fragmentos")
    if roles:
        doc.roles_asistente = ", ".join(roles)
    # Los defectos son del documento, no del proceso: sirven para que quien lo
    # subio sepa que partes no se detectaron bien y pueda arreglar el archivo.
    notas = [
        f"{d.get('tipo')}: {d.get('seccion') or ''} {d.get('detalle') or ''}".strip()
        for d in defectos
    ]
    if not roles:
        notas.insert(0, "Sin roles asignados: el asistente todavia no lo va a "
                        "recuperar para nadie.")
    doc.ingesta_detalle = "\n".join(notas)[:2000] or None
    doc.ingesta_actualizada_en = timezone.now()
    doc.save(update_fields=["corpus_document_id", "estado_ingesta",
                            "ingesta_fragmentos", "ingesta_detalle",
                            "roles_asistente", "ingesta_actualizada_en"])
    logger.info("Ingesta: %s -> %s (%s fragmentos, roles=%s)",
                document_id, cuerpo.get("codigo"), cuerpo.get("fragmentos"), roles)


@shared_task
def retirar_documento_del_asistente(corpus_document_id, org_id, document_id=None):
    """
    Saca un documento del corpus cuando se desmarca o se borra.

    No borra: el motor lo pasa a 'obsoleto', que es lo que la busqueda excluye.
    Asi deshacer es posible y se conserva con que version se respondio antes.
    """
    import requests

    from common.models import Document

    set_rls_context(org_id)

    url, tenant = _motor()
    if not url or not tenant:
        logger.warning("Retiro: el asistente no esta configurado")
        return

    try:
        r = requests.post(
            f"{url.rstrip('/')}/corpus/documentos/{corpus_document_id}/retirar",
            json={"tenant": tenant},
            timeout=60,
        )
        r.raise_for_status()
    except Exception:
        logger.exception("Retiro: fallo el documento de corpus %s", corpus_document_id)
        return

    if document_id:
        Document.objects.filter(id=document_id, org_id=org_id).update(
            estado_ingesta="", corpus_document_id=None,
            ingesta_fragmentos=None, ingesta_detalle=None,
            ingesta_actualizada_en=timezone.now(),
        )


@shared_task
def purgar_retencion_asistente():
    """
    Aplica la retencion declarada por el tenant: borra las conversaciones y los
    adjuntos vencidos del asistente.

    POR QUE LLAMA AL MOTOR Y NO BORRA DESDE AQUI
    Es la leccion que dejo escrita purge_read_notifications() unos cientos de
    lineas mas arriba: aquella purga borro CERO filas todas las noches durante
    meses porque un worker de Celery no pasa por el middleware que fija el
    contexto de aislamiento, y la politica filtra contra un valor vacio que no
    coincide con ninguna fila. No fallaba: no hacia nada, y no lo registraba.

    Las tablas del asistente viven en el esquema 'asistente' con esa misma
    clase de politica. Repetir el patron aca seria repetir el error. El motor
    ya abre cada operacion fijando la empresa (nucleo/persistencia/db.py::
    sesion()), asi que se le delega a el y esta ruta no puede quedarse callada
    borrando nada.

    Cadencia sugerida: diaria, de madrugada. No es urgente ni caro -- son dos
    DELETE por empresa.
    """
    import requests

    url, tenant = _motor()
    if not url or not tenant:
        logger.warning("Purga: el asistente no esta configurado")
        return

    try:
        r = requests.post(
            f"{url.rstrip('/')}/mantenimiento/{tenant}/purgar", timeout=120)
        r.raise_for_status()
        datos = r.json()
    except Exception:
        logger.exception("Purga: fallo la purga de retencion del asistente")
        return

    # Se registra SIEMPRE, tambien cuando no borro nada. Una purga silenciosa
    # es indistinguible de una purga rota -- que es exactamente como el fallo
    # de las notificaciones paso meses sin que nadie lo viera.
    logger.info(
        "Purga del asistente: %s archivos (>%s dias), %s conversaciones (>%s dias)",
        datos.get("media_borrada"), datos.get("retencion_multimedia_dias"),
        datos.get("conversaciones_borradas"), datos.get("retencion_conversaciones_dias"))
