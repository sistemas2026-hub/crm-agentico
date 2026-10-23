# -*- coding: utf-8 -*-
"""
================================================================================
 CREDENCIALES  --  quien atiende trafico y quien migra no son el mismo
================================================================================

Por que existe
--------------
'docker/backend/entrypoint.sh' corria 'migrate --noinput' con las MISMAS
credenciales con las que gunicorn sirve las peticiones. Mientras esas
credenciales fueron las de 'postgres' no se noto: postgres es dueno de las 129
tablas y puede con todo. El dia que el CRM se corte a 'crm_user' -que no es
dueno de ninguna- la primera migracion que necesite 'ALTER TABLE ... ENABLE ROW
LEVEL SECURITY' falla con 'must be owner of table'. Medido contra PostgreSQL 17
en la Etapa B.3.

La separacion es entonces: 'crm_user' sirve, 'crm_migrator' migra actuando como
'crm_owner', y el motor sigue con lo suyo. Este modulo es la guarda que impide
usar una donde va la otra.

Por que en codigo y no solo en el compose
-----------------------------------------
El 18/08/2026 'backend', 'celery-*' y 'motor' compartian una sola variable
'${DBUSER}'. Al cortarla a crm_user, el motor -que necesita el esquema
'asistente', donde crm_user no tiene ningun privilegio- dejo de poder guardar
conversaciones EN SILENCIO: varias de sus escrituras atrapan la excepcion y solo
la logean, a proposito, para no tumbarle la respuesta a un cliente. El sintoma
no fue un error: fue un hueco de datos que nadie vio hasta el dia siguiente.

Una variable mal puesta que rompe en silencio no se arregla documentandola. Se
arregla con una comprobacion que falle fuerte y temprano.

Este modulo NO importa Django ni abre ninguna conexion
------------------------------------------------------
Las comprobaciones de entorno (A-E) son aritmetica de cadenas sobre un dict, asi
que se pueden probar sin base y sin Django. Las que si necesitan la base (F-G)
reciben un cursor ya abierto. Esa separacion es deliberada: una guarda que solo
se puede probar levantando media plataforma es una guarda que no se prueba.
================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass

# --- Los roles, y para que sirve cada uno -----------------------------------
# Los nombres son los de la Etapa B.3. 'crm_owner' no aparece aca porque NO es
# una credencial: no tiene LOGIN y nadie se conecta con el.
ROL_TRAFICO = "crm_user"
ROL_MIGRACIONES = "crm_migrator"
ROL_MOTOR = "motor_user"
ROL_EMERGENCIA = "postgres"
# El rol dueno. Se nombra aca porque la guarda necesita compararlo, pero NO es
# una credencial: no tiene LOGIN y no aparece en ninguna variable de entorno.
ROL_DUENO = "crm_owner"

# Roles que NO deben aparecer nunca del lado del motor. Es el incidente del
# 18/08 escrito como dato: ninguno de los dos tiene privilegios sobre
# 'asistente', asi que el motor quedaria mudo.
ROLES_DEL_CRM = frozenset({ROL_TRAFICO, ROL_MIGRACIONES})

PROPOSITO_TRAFICO = "trafico"
PROPOSITO_MIGRACIONES = "migraciones"
PROPOSITOS = (PROPOSITO_TRAFICO, PROPOSITO_MIGRACIONES)

# Gravedad. La distincion importa y no es cosmetica:
#   ERROR  corta el arranque. Se reserva para lo que YA esta roto o va a romper
#          de una forma que no deja rastro.
#   AVISO  no corta. Se usa para lo que hoy es cierto en produccion y no se
#          puede volver fatal sin tumbar el despliegue en el mismo instante en
#          que este codigo llegue al servidor.
ERROR = "ERROR"
AVISO = "AVISO"

# Con esto en '1', los AVISO pasan a ERROR. Es el interruptor que se enciende
# DESPUES de completar la transicion, no antes: encenderlo hoy -con
# DBUSER=postgres en produccion- impediria arrancar el backend.
VAR_ESTRICTO = "CRM_CREDENCIALES_ESTRICTO"


@dataclass(frozen=True)
class Problema:
    codigo: str          # 'A'..'G', para poder referirse a uno sin ambiguedad
    gravedad: str        # ERROR | AVISO
    mensaje: str
    remedio: str

    def __str__(self) -> str:
        return f"[{self.gravedad} {self.codigo}] {self.mensaje}\n    -> {self.remedio}"


def rol_base(dbuser: str | None) -> str:
    """
    El nombre del rol, sin el sufijo del tenant que exige Supavisor.

    En produccion DBUSER no es 'postgres' sino
    'postgres.05b5a4b4-3b9a-4901-86f2-f3ed8f8ac0a1' -- el pooler lo pide asi
    (ver .env). Una comparacion directa contra 'crm_user' no coincidiria NUNCA,
    y la guarda quedaria en verde sin comprobar nada. Este recorte es la
    diferencia entre una guarda y un adorno.
    """
    if not dbuser:
        return ""
    return dbuser.split(".", 1)[0].strip()


def _estricto(entorno: dict) -> bool:
    return str(entorno.get(VAR_ESTRICTO, "")).strip().lower() in ("1", "true", "si", "yes")


def _grave(entorno: dict, base: str) -> str:
    """AVISO, salvo que el modo estricto este encendido."""
    return ERROR if _estricto(entorno) else base


def revisar_entorno(entorno: dict, proposito: str) -> list[Problema]:
    """
    Las comprobaciones que no necesitan base de datos.

    'proposito' dice para que se va a usar esta conexion. La MISMA variable
    puede estar bien para una cosa y mal para la otra, y sin ese dato la guarda
    no puede decidir nada.
    """
    if proposito not in PROPOSITOS:
        raise ValueError(f"proposito desconocido: {proposito!r}; usar {PROPOSITOS}")

    problemas: list[Problema] = []
    dbuser = entorno.get("DBUSER")
    migrator = entorno.get("MIGRATOR_DBUSER")
    motor = entorno.get("MOTOR_DBUSER")

    actual = rol_base(dbuser)
    base_migrator = rol_base(migrator)
    base_motor = rol_base(motor)

    # --- A) se va a migrar con el usuario de trafico -------------------------
    # NO se decide por el nombre, y la primera version de esta guarda si lo
    # hacia. Migrar como 'crm_user' es PERFECTAMENTE VALIDO cuando crm_user es
    # dueno de las tablas -- que es exactamente el caso del compose de
    # desarrollo: 'docker/postgres/init-rls-user.sql' le da ALL sobre 'public'
    # y crm_user crea, y por lo tanto posee, todo el esquema. Volverlo fatal
    # aqui habria roto el entorno de desarrollo de todo el mundo.
    #
    # Lo que decide no es como se llama el rol: es si puede actuar como el
    # dueno de lo que va a alterar. Eso no se sabe sin preguntarle a la base, y
    # esta en revisar_base(). Aqui solo queda el AVISO.
    if proposito == PROPOSITO_MIGRACIONES and actual == ROL_TRAFICO:
        problemas.append(Problema(
            "A", AVISO,
            f"Se va a ejecutar 'migrate' con {dbuser!r}, que es el rol de "
            f"trafico.",
            "Es correcto si ese rol es dueno de las tablas (asi funciona el "
            "compose de desarrollo). Es un fallo en produccion, donde las 129 "
            "tablas son de otro rol. Se comprueba de verdad con --con-base."))

    # --- B) el proceso normal esta usando la credencial de migraciones -------
    if proposito == PROPOSITO_TRAFICO and actual == ROL_MIGRACIONES:
        problemas.append(Problema(
            "B", ERROR,
            f"El proceso de trafico esta conectando como {dbuser!r}, que es la "
            f"credencial de MIGRACIONES.",
            "crm_migrator actua como crm_owner, o sea como DUENO de las tablas. "
            "Un dueno se saltea su propia politica RLS salvo que este FORCE: "
            "servir peticiones con el es perder el aislamiento por organizacion. "
            "Poner DBUSER=crm_user."))

    # --- C) trafico con el usuario de emergencia -----------------------------
    # AVISO y no ERROR a proposito: hoy produccion corre asi (medido en la
    # Etapa B.2, DBUSER=postgres al 11/09/2026). Volverlo fatal haria que este
    # mismo codigo impidiera arrancar el backend al desplegarse. Se vuelve
    # fatal con CRM_CREDENCIALES_ESTRICTO=1, despues de la transicion.
    if proposito == PROPOSITO_TRAFICO and actual == ROL_EMERGENCIA:
        problemas.append(Problema(
            "C", _grave(entorno, AVISO),
            f"El trafico normal conecta como {dbuser!r}. Ese rol tiene "
            f"BYPASSRLS: las politicas de aislamiento NO se evaluan.",
            "Es el estado conocido hoy, no una novedad. Se cierra pasando "
            "DBUSER a crm_user una vez resuelta la propiedad de las tablas. "
            "'manage_rls --status' NO detecta esto: mira 'usesuper' y en "
            "Supabase postgres tiene rolsuper=false con rolbypassrls=true."))

    # --- D y E) el motor apuntando a una credencial del CRM -----------------
    # Esto es, literalmente, el incidente del 18/08/2026.
    if motor and base_motor in ROLES_DEL_CRM:
        problemas.append(Problema(
            "D" if base_motor == ROL_TRAFICO else "E", ERROR,
            f"MOTOR_DBUSER apunta a {motor!r}, que es una credencial del CRM.",
            "Ninguno de los dos roles del CRM tiene privilegios sobre el "
            "esquema 'asistente'. El motor no fallaria ruidosamente: varias de "
            "sus escrituras atrapan la excepcion y solo la logean, asi que "
            "perderia mensajes y conversaciones EN SILENCIO. Paso de verdad el "
            "18/08/2026. MOTOR_DBUSER va a motor_user."))

    # --- el caso que de verdad ocurrio: una sola variable para los dos -------
    if motor and dbuser and motor == dbuser:
        problemas.append(Problema(
            "D", ERROR,
            "MOTOR_DBUSER y DBUSER son EXACTAMENTE la misma credencial.",
            "Es la configuracion que causo el incidente del 18/08/2026: al "
            "cortar el CRM, el motor se fue con el. Tienen que ser dos."))

    # --- coherencia de la credencial de migraciones -------------------------
    if migrator and base_migrator in (ROL_TRAFICO, ROL_MOTOR, ROL_EMERGENCIA):
        problemas.append(Problema(
            "B", ERROR,
            f"MIGRATOR_DBUSER apunta a {migrator!r}, que no es la credencial de "
            f"migraciones.",
            "Si se define MIGRATOR_DBUSER, tiene que ser crm_migrator. Para "
            "seguir migrando con postgres, dejarla SIN definir: el entrypoint "
            "cae al comportamiento de siempre."))

    if migrator and not entorno.get("MIGRATOR_DBPASSWORD"):
        problemas.append(Problema(
            "A", ERROR,
            "MIGRATOR_DBUSER esta definida pero MIGRATOR_DBPASSWORD no.",
            "Van juntas. Con una sola, el entrypoint intentaria migrar con una "
            "contrasena vacia y el fallo apuntaria a la causa equivocada."))

    return problemas


def revisar_base(cursor, proposito: str) -> list[Problema]:
    """
    Las comprobaciones que SI necesitan la base. Recibe un cursor ya abierto.

    Se limitan a lo que la Etapa B.4 tiene autorizado mirar: quien soy y que
    alcanzo. No inspecciona ni modifica RLS, ni propiedad, ni las 11 tablas
    pendientes.
    """
    problemas: list[Problema] = []

    cursor.execute("select current_user, session_user")
    efectivo, sesion = cursor.fetchone()

    # --- A de verdad) ¿puede este rol alterar lo que hay? -------------------
    # La comprobacion que importa, y la unica que se puede hacer sin adivinar:
    # contar las tablas cuyo dueno este rol NO puede ejercer. Postgres consulta
    # exactamente eso ('pg_has_role') al procesar un ALTER TABLE.
    #
    # Es indiferente a como se llame el rol, asi que vale igual para crm_user
    # duenno en desarrollo, para postgres en produccion y para crm_migrator
    # actuando como crm_owner. Un nombre no prueba nada; esto si.
    if proposito == PROPOSITO_MIGRACIONES:
        cursor.execute("""
            select count(*) from pg_class c
            join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public' and c.relkind = 'r'
              and not pg_has_role(current_user, c.relowner, 'USAGE')
        """)
        ajenas = cursor.fetchone()[0]
        if ajenas:
            problemas.append(Problema(
                "A", ERROR,
                f"El rol efectivo {efectivo!r} no puede actuar como dueno de "
                f"{ajenas} tabla(s) de 'public'.",
                "Cualquier migracion que toque una de ellas fallara con 'must "
                "be owner of table' -- a mitad de camino, no al arrancar. "
                "Migrar con una credencial que pueda ejercer ese rol "
                "(MIGRATOR_DBUSER), o transferir la propiedad primero."))

    # El rol EFECTIVO puede no ser el de la sesion: crm_migrator arranca con
    # 'set role = crm_owner'. Comprobar solo la variable de entorno dejaria eso
    # sin ver, y es justo la pieza que hace que la propiedad no derive.
    if proposito == PROPOSITO_MIGRACIONES and rol_base(sesion) == ROL_MIGRACIONES:
        if efectivo != ROL_DUENO:
            problemas.append(Problema(
                "A", ERROR,
                f"crm_migrator inicio sesion pero su rol efectivo es "
                f"{efectivo!r}, no {ROL_DUENO!r}.",
                f"Falta 'ALTER ROLE {ROL_MIGRACIONES} IN DATABASE <base> SET "
                f"role = {ROL_DUENO}'. Sin eso, cada tabla que cree una "
                f"migracion queda de {ROL_MIGRACIONES} -un rol CON login- y la "
                f"separacion se deshace sola, migracion a migracion."))

    # --- F) crm_user alcanzando el esquema del motor ------------------------
    # has_schema_privilege() lanza excepcion si el rol o el esquema no existen,
    # y ninguno de los dos tiene por que existir en un entorno de pruebas. Se
    # comprueba que existan ANTES de preguntar: una guarda que revienta cuando
    # no aplica es una guarda que alguien termina desactivando.
    if _existe_rol(cursor, ROL_TRAFICO) and _existe_esquema(cursor, "asistente"):
        cursor.execute(
            "select has_schema_privilege(%s, 'asistente', 'usage')", (ROL_TRAFICO,))
        fila = cursor.fetchone()
        if fila and fila[0]:
            problemas.append(Problema(
                "F", ERROR,
                f"{ROL_TRAFICO!r} tiene USAGE sobre el esquema 'asistente'.",
                "La frontera entre el CRM y el motor es que ninguno alcanza el "
                "esquema del otro. Revocar: REVOKE USAGE ON SCHEMA asistente "
                "FROM crm_user."))

    # --- G) motor_user administrando el esquema del CRM ---------------------
    if _existe_rol(cursor, ROL_MOTOR):
        cursor.execute("""
            select count(*) from pg_class c
            join pg_namespace n on n.oid = c.relnamespace
            where n.nspname = 'public' and c.relkind = 'r'
              and pg_get_userbyid(c.relowner) = %s
        """, (ROL_MOTOR,))
        fila = cursor.fetchone()
        if fila and fila[0]:
            problemas.append(Problema(
                "G", ERROR,
                f"{ROL_MOTOR!r} es dueno de {fila[0]} tabla(s) de 'public'.",
                "El motor no administra el esquema del CRM. Transferir esas "
                "tablas al rol dueno del CRM."))

    return problemas


def _existe_rol(cursor, nombre: str) -> bool:
    cursor.execute("select 1 from pg_roles where rolname = %s", (nombre,))
    return cursor.fetchone() is not None


def _existe_esquema(cursor, nombre: str) -> bool:
    cursor.execute("select 1 from pg_namespace where nspname = %s", (nombre,))
    return cursor.fetchone() is not None


def hay_que_abortar(problemas) -> bool:
    return any(p.gravedad == ERROR for p in problemas)


def formatear(problemas, proposito: str) -> str:
    """El texto que ve quien mira los logs a las 3 de la manana."""
    if not problemas:
        return f"credenciales ({proposito}): sin problemas."
    lineas = [f"credenciales ({proposito}): {len(problemas)} problema(s)", ""]
    for p in problemas:
        lineas.append(str(p))
        lineas.append("")
    return "\n".join(lineas)
