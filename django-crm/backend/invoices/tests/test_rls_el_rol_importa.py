"""
El aislamiento por RLS, y la guarda que faltaba: bajo que ROL se comprueba.

    DBNAME=crm_db DBUSER=crm_user DBPASSWORD=... DBHOST=... \
      pytest invoices/tests/test_rls_el_rol_importa.py --ds=crm.test_settings_postgres

POR QUE EXISTE
--------------
'test_portal_rls.py' fallaba en una auditoria y parecia una fuga de aislamiento:
un Estimate legible con el contexto de organizacion vacio. No lo era. Corria
bajo un rol con 'rolsuper=t, rolbypassrls=t', y un superusuario de PostgreSQL
evade RLS por completo.

El problema no fue el rol: fue que la prueba NO LO DIJO. Fallo con
'assert <Estimate: ...> is None', que se lee como "hay una fuga" cuando lo que
pasa es "esta prueba no puede comprobar nada aqui". Dos lecturas opuestas del
mismo sintoma, y la equivocada cuesta horas.

'crm/test_settings_postgres.py' ya advertia en su docstring que el rol no puede
ser superusuario. Una advertencia en un docstring no es una guarda.

LO QUE SE AGREGA
----------------
1. Una guarda que mira el rol ANTES de afirmar nada, y que separa "no se puede
   comprobar" de "no aisla".
2. Las comprobaciones de aislamiento que la suite no tenia: cruce entre dos
   organizaciones, dentro y fuera de una transaccion, y que devolver la
   conexion no deje el tenant anterior puesto.
"""

import os

import pytest
from django.db import connection, transaction
from django.utils import timezone

from common.models import Org
from common.tasks import set_rls_context
from invoices.models import Estimate

pytestmark = [pytest.mark.postgres_only, pytest.mark.django_db]


def _contexto(valor):
    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.current_org', %s, false)", [valor])


def _rol_actual():
    """(nombre, es_superusuario, evade_rls) del rol con el que corre la sesion."""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT r.rolname, r.rolsuper, r.rolbypassrls
            FROM pg_roles r
            WHERE r.rolname = current_user
        """)
        return cur.fetchone()


# DOS MODOS, Y LA DIFERENCIA ES EL PUNTO.
#
#   sin RLS_GATE   suite de desarrollo. Si el rol evade RLS, estas pruebas se
#                  SALTAN diciendo por que. Correr la suite con un superusuario
#                  es legitimo para todo lo demas.
#
#   RLS_GATE=1     compuerta de seguridad. El mismo rol que alla hacia saltar,
#                  aca FALLA.
#
# Una compuerta que se saltea sola no es una compuerta. Si CI arranca un dia
# con un rol privilegiado --que es exactamente lo que acaba de pasar en una
# auditoria-- el aislamiento deja de comprobarse y el job sigue en verde. Es el
# mismo error de esta investigacion un nivel mas arriba: lo que no se dice en
# voz alta se lee como que esta bien.
MODO_COMPUERTA = os.environ.get("RLS_GATE", "") not in ("", "0", "false")


def _sin_rls(motivo: str):
    """Saltar en desarrollo, fallar en la compuerta. Mismo motivo, dos pesos."""
    if MODO_COMPUERTA:
        pytest.fail(
            f"RLS_GATE=1: {motivo}. "
            f"La compuerta de aislamiento no puede saltarse: si no se puede "
            f"comprobar, no esta comprobado.")
    pytest.skip(f"{motivo} (con RLS_GATE=1 esto seria un fallo)")


def _exigir_rol_que_respeta_rls():
    """
    La guarda que faltaba, en sus dos modos.

    Lo que no puede pasar --y pasaba-- es afirmar sobre RLS bajo un rol que lo
    evade y leer el resultado como si significara algo.
    """
    if connection.vendor != "postgresql":
        _sin_rls("la base no es PostgreSQL, y RLS es una funcion de PostgreSQL")
        return

    nombre, superusuario, evade = _rol_actual()
    if superusuario or evade:
        _sin_rls(
            f"el rol '{nombre}' evade RLS (rolsuper={superusuario}, "
            f"rolbypassrls={evade}), asi que estas comprobaciones serian "
            f"vacuamente ciertas o enganosamente falsas. Correr con un rol de "
            f"aplicacion: --ds=crm.test_settings_postgres y DBUSER apuntando a "
            f"un rol NOSUPERUSER NOBYPASSRLS. Ver "
            f"docs/self-hosting/postgresql-and-rls.md")


def _estimate(org, titulo, numero=None):
    """
    Un Estimate de esa organizacion.

    El numero se pasa EXPLICITO a proposito. 'generate_estimate_number()' lo
    calcula consultando los Estimate existentes, y bajo RLS solo ve los de la
    organizacion actual: dos empresas que crean uno el mismo dia generan el
    mismo 'EST-AAAAMMDD-0001' y chocan contra 'estimate_number unique=True',
    que es GLOBAL y no por organizacion.

    Ese choque es un defecto real y preexistente --ver
    'test_DEFECTO_dos_organizaciones_no_pueden_crear_el_mismo_dia' abajo-- y no
    es lo que estas pruebas miden. Dandole el numero, miden aislamiento.
    """
    _contexto(str(org.id))
    try:
        return Estimate.objects.create(
            org=org, title=titulo, currency="USD",
            estimate_number=numero or f"EST-PRUEBA-{titulo.replace(' ', '-')}",
            issue_date=timezone.localdate())
    finally:
        _contexto("")


# --- la guarda misma --------------------------------------------------------

def test_la_suite_sabe_bajo_que_rol_corre():
    """Si esto se salta, NINGUNA afirmacion de aislamiento de abajo vale.

    Existe para que el motivo aparezca en la salida en vez de deducirse de una
    asercion rara. Un 'skip' con explicacion es informacion; un fallo que dice
    'is None' sobre un objeto es una pista falsa.
    """
    if connection.vendor != "postgresql":
        _sin_rls("la base no es PostgreSQL")
        return

    nombre, superusuario, evade = _rol_actual()
    with connection.cursor() as cur:
        cur.execute("SELECT current_database(), inet_server_addr()")
        base, servidor = cur.fetchone()

    # Se imprime el destino y el rol -- nada sensible, ninguna contrasena.
    # Sin esto, una corrida en verde no dice CONTRA QUE corrio, que es
    # justamente lo que hizo falta saber para entender el fallo original.
    print(f"\n  base: {base}   servidor: {servidor}")
    print(f"  rol: {nombre} (rolsuper={superusuario}, rolbypassrls={evade})")
    print(f"  modo compuerta (RLS_GATE): {MODO_COMPUERTA}")
    assert nombre, "no se pudo determinar el rol de la sesion"

    if MODO_COMPUERTA:
        assert not superusuario, (
            f"RLS_GATE=1 y el rol '{nombre}' es SUPERUSER: evade RLS, asi que "
            f"toda afirmacion de aislamiento de esta suite seria vacua")
        assert not evade, (
            f"RLS_GATE=1 y el rol '{nombre}' tiene BYPASSRLS: idem")


# --- el aislamiento que la suite no comprobaba ------------------------------

def test_con_contexto_vacio_no_se_ve_ningun_estimate():
    _exigir_rol_que_respeta_rls()

    org = Org.objects.create(name="RLS Org Sola")
    _estimate(org, "Presupuesto uno")

    _contexto("")
    assert Estimate.objects.count() == 0, (
        "con el contexto de organizacion vacio se estan viendo filas")


def test_una_organizacion_no_ve_las_filas_de_la_otra():
    _exigir_rol_que_respeta_rls()

    a = Org.objects.create(name="RLS Org A")
    b = Org.objects.create(name="RLS Org B")
    _estimate(a, "De la A")
    _estimate(b, "De la B")

    set_rls_context(str(a.id))
    try:
        titulos = set(Estimate.objects.values_list("title", flat=True))
        assert titulos == {"De la A"}, f"la A esta viendo {titulos}"
    finally:
        _contexto("")

    set_rls_context(str(b.id))
    try:
        titulos = set(Estimate.objects.values_list("title", flat=True))
        assert titulos == {"De la B"}, f"la B esta viendo {titulos}"
    finally:
        _contexto("")


def test_el_contexto_no_sobrevive_a_limpiarlo():
    """Lo que le pasa a una conexion cuando vuelve al pool.

    Si el tenant anterior quedara puesto, la siguiente peticion que tome esa
    conexion veria datos de otra empresa sin haber hecho nada mal.
    """
    _exigir_rol_que_respeta_rls()

    a = Org.objects.create(name="RLS Org Pool")
    _estimate(a, "De la A")

    set_rls_context(str(a.id))
    assert Estimate.objects.count() == 1

    # Lo que hace el middleware al terminar la peticion.
    _contexto("")
    assert Estimate.objects.count() == 0, (
        "el contexto sobrevivio a la limpieza: la proxima peticion que tome "
        "esta conexion veria datos ajenos")


def test_el_aislamiento_vale_dentro_de_una_transaccion():
    """Una policy que solo aplica fuera de atomic() no protege casi nada:
    todo el codigo de escritura corre dentro de una transaccion."""
    _exigir_rol_que_respeta_rls()

    a = Org.objects.create(name="RLS Org Tx A")
    b = Org.objects.create(name="RLS Org Tx B")
    _estimate(a, "De la A")
    _estimate(b, "De la B")

    with transaction.atomic():
        set_rls_context(str(a.id))
        try:
            titulos = set(Estimate.objects.values_list("title", flat=True))
            assert titulos == {"De la A"}, (
                f"dentro de atomic() la A ve {titulos}")
        finally:
            _contexto("")

    # Y fuera de la transaccion sigue valiendo.
    _contexto("")
    assert Estimate.objects.count() == 0


def test_la_tabla_tiene_rls_habilitado_y_forzado():
    """'ENABLE' no alcanza: sin 'FORCE', el DUEÑO de la tabla la lee entera.

    El usuario de la aplicacion suele ser el dueño --las migraciones corren con
    el-- asi que sin FORCE la policy no lo alcanzaria justamente a el.
    """
    if connection.vendor != "postgresql":
        _sin_rls("la base no es PostgreSQL")
        return

    tabla = Estimate._meta.db_table
    with connection.cursor() as cur:
        cur.execute("SELECT relrowsecurity, relforcerowsecurity "
                    "FROM pg_class WHERE relname = %s", [tabla])
        fila = cur.fetchone()

    assert fila, f"no se encontro la tabla {tabla}"
    habilitado, forzado = fila
    assert habilitado, f"{tabla} no tiene ROW LEVEL SECURITY habilitado"
    assert forzado, (
        f"{tabla} tiene RLS habilitado pero NO forzado: el dueño de la tabla "
        f"--que es el usuario con el que corren las migraciones-- la lee entera")


# El defecto de 'estimate_number' que aparecio escribiendo estas pruebas vive
# en 'test_numeradores_y_rls.py', junto con el barrido de numeradores y la
# carrera intra-tenant. Aca quedaria suelto.


# --- que la compuerta sea una compuerta -------------------------------------

def test_la_compuerta_falla_en_vez_de_saltarse():
    """RLS_GATE=1 convierte el 'skip' en 'fail'. Sin esto no es una compuerta.

    Se comprueba la FUNCION, no el proceso: '_sin_rls' es el unico punto por el
    que pasan todos los motivos por los que estas pruebas no pueden comprobar
    nada, asi que fijar su conducta fija la de todas.

    La prueba de punta a punta --lanzar pytest con RLS_GATE=1 bajo un rol
    BYPASSRLS y ver el exit distinto de cero-- esta en el comando documentado
    arriba, y su salida va en el reporte. Aca se fija la regla para que un
    cambio futuro no la afloje sin que nadie lo note.
    """
    import importlib

    modulo = importlib.import_module(__name__)

    # Modo desarrollo: salta.
    original = modulo.MODO_COMPUERTA
    try:
        modulo.MODO_COMPUERTA = False
        with pytest.raises(BaseException) as salto:
            modulo._sin_rls("motivo de prueba")
        assert salto.typename == "Skipped", (
            f"en modo desarrollo tendria que saltar, levanto {salto.typename}")

        # Modo compuerta: falla.
        modulo.MODO_COMPUERTA = True
        with pytest.raises(BaseException) as fallo:
            modulo._sin_rls("motivo de prueba")
        assert fallo.typename == "Failed", (
            f"en modo compuerta tendria que FALLAR, levanto {fallo.typename}")
        assert "RLS_GATE=1" in str(fallo.value)
        assert "no esta comprobado" in str(fallo.value)
    finally:
        modulo.MODO_COMPUERTA = original
