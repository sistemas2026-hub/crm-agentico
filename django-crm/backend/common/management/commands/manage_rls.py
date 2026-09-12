"""
Management command to check Row-Level Security (RLS) status.

Usage:
    python manage.py manage_rls --status          # Check RLS status
    python manage.py manage_rls --test            # Test RLS is working
    python manage.py manage_rls --verify-user     # Verify DB user is not superuser

RLS Configuration: See common/rls/__init__.py for centralized policy definitions.
RLS is enabled/disabled via Django migrations, not this command.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from common.rls import RLS_CONFIG, get_check_rls_status_sql, get_set_context_sql


def inspeccionar_rol(cursor):
    """
    Si el rol de esta sesion esta sujeto a RLS. Dos atributos, no uno.

    POR QUE NO ALCANZA 'pg_user.usesuper'
    -------------------------------------
    'rolsuper' y 'rolbypassrls' son atributos DISTINTOS, y cualquiera de los
    dos evade RLS. 'pg_user' no expone el segundo.

    En Supabase el rol 'postgres' tiene rolsuper=false y rolbypassrls=true.
    Este comando miraba solo 'usesuper' y respondia "not a superuser - RLS
    will be enforced": una afirmacion de seguridad FALSA, con el aislamiento
    desactivado, desde la propia herramienta de verificacion. Esta escrito en
    DESPLIEGUE.md que paso.

    Devuelve (datos, problemas). 'problemas' vacio significa sujeto a RLS.
    """
    datos = {}
    problemas = []

    cursor.execute("SELECT current_user, session_user")
    datos["current_user"], datos["session_user"] = cursor.fetchone()

    cursor.execute(
        "SELECT rolname, rolsuper, rolbypassrls, rolcreatedb "
        "FROM pg_roles WHERE rolname = current_user")
    fila = cursor.fetchone()

    if fila is None:
        # No se pudo comprobar. INDETERMINADO es un fallo, no un permiso: la
        # unica respuesta peor que "no aisla" es "no se sabe, pasa igual".
        problemas.append(
            f"no se encontro el rol '{datos['current_user']}' en pg_roles: la "
            f"comprobacion NO se pudo hacer, asi que no se afirma nada")
        return datos, problemas

    datos["rol"], datos["rolsuper"], datos["rolbypassrls"], datos["rolcreatedb"] = fila

    if datos["rolsuper"]:
        problemas.append(
            f"el rol '{datos['rol']}' es SUPERUSER: evade RLS por completo")
    if datos["rolbypassrls"]:
        problemas.append(
            f"el rol '{datos['rol']}' tiene BYPASSRLS: evade RLS aunque no sea "
            f"superusuario -- es el caso que 'pg_user.usesuper' no ve")

    return datos, problemas


class Command(BaseCommand):
    help = "Check Row-Level Security (RLS) status for multi-tenancy"

    # Use centralized RLS configuration
    ORG_SCOPED_TABLES = RLS_CONFIG["tables"]

    def add_arguments(self, parser):
        parser.add_argument(
            "--status", action="store_true", help="Check RLS status for all tables"
        )
        parser.add_argument(
            "--test", action="store_true", help="Test that RLS is working correctly"
        )
        parser.add_argument(
            "--verify-user",
            action="store_true",
            help="Verify database user is not a superuser",
        )

    def handle(self, *args, **options):
        if connection.vendor != "postgresql":
            self.stderr.write(self.style.ERROR("RLS is only supported on PostgreSQL"))
            return

        if options["status"]:
            self.check_status()
        elif options["test"]:
            self.test_rls()
        elif options["verify_user"]:
            self.verify_user()
        else:
            self.check_status()

    def check_status(self):
        """Check RLS status for all org-scoped tables."""
        self.stdout.write(self.style.MIGRATE_HEADING("RLS Status:"))
        self.stdout.write("")

        inseguro = False
        with connection.cursor() as cursor:
            datos, problemas = inspeccionar_rol(cursor)

            self.stdout.write(f"  current_user : {datos.get('current_user')}")
            self.stdout.write(f"  session_user : {datos.get('session_user')}")
            if "rol" in datos:
                self.stdout.write(
                    f"  rol inspeccionado: {datos['rol']} "
                    f"(rolsuper={datos['rolsuper']}, "
                    f"rolbypassrls={datos['rolbypassrls']})")

            if problemas:
                inseguro = True
                for p in problemas:
                    self.stdout.write(self.style.ERROR(f"  RLS NO SE APLICA: {p}"))
            else:
                self.stdout.write(self.style.SUCCESS(
                    f"  El rol '{datos['rol']}' esta sujeto a RLS "
                    f"(rolsuper=False, rolbypassrls=False)"))

            self.stdout.write("")

            enabled_count = 0
            disabled_count = 0

            for table in self.ORG_SCOPED_TABLES:
                cursor.execute(get_check_rls_status_sql(), [table])

                result = cursor.fetchone()
                if result:
                    rls_enabled, rls_forced = result
                    if rls_enabled:
                        status = self.style.SUCCESS("ENABLED")
                        if rls_forced:
                            status += " (forced)"
                        enabled_count += 1
                    else:
                        status = self.style.WARNING("disabled")
                        disabled_count += 1
                else:
                    status = self.style.ERROR("TABLE NOT FOUND")

                self.stdout.write(f"  {table}: {status}")

            self.stdout.write("")
            self.stdout.write(f"  Enabled: {enabled_count}, Disabled: {disabled_count}")

        # Salir distinto de cero. Un comando de seguridad que informa un
        # problema y termina en 0 es un comando que nadie va a poner en un
        # pipeline, y si alguien lo pone, no sirve de nada.
        if inseguro:
            raise CommandError(
                "RLS NO se aplica con este rol: las politicas existen pero el "
                "rol las evade. Ver arriba cual de los dos atributos es.")
        if disabled_count:
            raise CommandError(
                f"{disabled_count} tabla(s) con alcance de organizacion no "
                f"tienen RLS habilitado.")

    def test_rls(self):
        """Test that RLS is working correctly."""
        self.stdout.write(self.style.MIGRATE_HEADING("Testing RLS..."))

        set_context_sql = get_set_context_sql()

        with connection.cursor() as cursor:
            # Find orgs that have leads (need to check each org since RLS is active)
            cursor.execute(
                "SELECT id FROM organization ORDER BY created_at DESC LIMIT 50"
            )
            all_orgs = cursor.fetchall()

            orgs_with_leads = []
            for (org_id,) in all_orgs:
                cursor.execute(set_context_sql, [str(org_id)])
                cursor.execute("SELECT COUNT(*) FROM lead")
                if cursor.fetchone()[0] > 0:
                    orgs_with_leads.append(str(org_id))
                    if len(orgs_with_leads) >= 2:
                        break

            if len(orgs_with_leads) < 1:
                # Fall back to first 2 orgs for testing
                cursor.execute("SELECT id FROM organization LIMIT 2")
                orgs = cursor.fetchall()
                if len(orgs) < 2:
                    self.stdout.write(
                        self.style.WARNING(
                            "Need at least 2 orgs to test RLS. Skipping."
                        )
                    )
                    return
                org_a = str(orgs[0][0])
                org_b = str(orgs[1][0])
            else:
                org_a = orgs_with_leads[0]
                org_b = (
                    orgs_with_leads[1]
                    if len(orgs_with_leads) > 1
                    else str(all_orgs[0][0])
                )

            # Test with org_a context
            cursor.execute(set_context_sql, [org_a])
            cursor.execute("SELECT COUNT(*) FROM lead")
            count_a = cursor.fetchone()[0]

            # Test with org_b context
            cursor.execute(set_context_sql, [org_b])
            cursor.execute("SELECT COUNT(*) FROM lead")
            count_b = cursor.fetchone()[0]

            # Test with no context
            cursor.execute(set_context_sql, [""])
            cursor.execute("SELECT COUNT(*) FROM lead")
            count_none = cursor.fetchone()[0]

            self.stdout.write(f"  Leads with org_a context: {count_a}")
            self.stdout.write(f"  Leads with org_b context: {count_b}")
            self.stdout.write(f"  Leads with no context: {count_none}")

            if count_a == 0 and count_b == 0 and count_none == 0:
                self.stdout.write(
                    self.style.WARNING(
                        "No lead data found. Create leads for different orgs to test RLS isolation."
                    )
                )
            elif count_none == 0 and (count_a > 0 or count_b > 0):
                self.stdout.write(
                    self.style.SUCCESS("RLS is working - no data without context")
                )
            elif count_none > 0:
                self.stdout.write(
                    self.style.WARNING(
                        "RLS may not be fully enabled - data visible without context. "
                        "This is expected if the policy allows empty context."
                    )
                )

    def verify_user(self):
        """Verify the database user is not a superuser."""
        self.stdout.write(self.style.MIGRATE_HEADING("Verifying database user..."))

        with connection.cursor() as cursor:
            # Tenia el MISMO defecto que check_status: 'pg_user.usesuper' no
            # ve BYPASSRLS. DESPLIEGUE.md afirmaba que '--verify-user' si
            # preguntaba lo correcto, y era falso: preguntaba lo mismo.
            datos, problemas = inspeccionar_rol(cursor)

            self.stdout.write(f"  current_user : {datos.get('current_user')}")
            self.stdout.write(f"  session_user : {datos.get('session_user')}")
            self.stdout.write(f"  rolsuper     : {datos.get('rolsuper')}")
            self.stdout.write(f"  rolbypassrls : {datos.get('rolbypassrls')}")
            self.stdout.write(f"  rolcreatedb  : {datos.get('rolcreatedb')}")

            if problemas:
                self.stdout.write("")
                for p in problemas:
                    self.stdout.write(self.style.ERROR(f"  {p}"))
                raise CommandError(
                    "El usuario de base de datos NO esta sujeto a RLS. "
                    "Crear uno de aplicacion: CREATE ROLE crm_app WITH "
                    "LOGIN PASSWORD '...' NOSUPERUSER NOBYPASSRLS;")

            self.stdout.write(
                self.style.SUCCESS(
                    "El usuario de base de datos esta sujeto a RLS"))