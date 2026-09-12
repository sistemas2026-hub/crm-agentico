"""
Los numeradores visibles: quien es unico donde, y quien se rompe bajo RLS.

    DBNAME=crm_db DBUSER=crm_user ... \
      pytest invoices/tests/test_numeradores_y_rls.py --ds=crm.test_settings_postgres

POR QUE EXISTE
--------------
Escribiendo las pruebas de aislamiento aparecio esto: 'Estimate.estimate_number'
es 'unique=True' GLOBAL, no por organizacion, y 'generate_estimate_number()'
calcula el siguiente consultando los Estimate que PUEDE VER. Bajo RLS no ve los
de otras empresas, asi que dos organizaciones que crean un presupuesto el mismo
dia generan ambas 'EST-AAAAMMDD-0001' y la segunda choca.

No es deuda de pruebas: un tenant puede impedirle a otro crear un presupuesto.

EL BARRIDO
----------
Se reviso todo el backend buscando el patron --numero visible con constraint
global mas generador que consulta filas filtradas-- y son exactamente dos:

  modelo    campo             constraint   algoritmo              RLS   carrera
  Invoice   invoice_number    GLOBAL       Max(Substr)+1 + FU     SI    parcial
  Estimate  estimate_number   GLOBAL       Max(Substr)+1 + FU     SI    parcial
  Product   sku               (sku, org)   manual                 no    no
  Order     order_number      ninguna      no se genera           no    no
  Payment   reference_number  ninguna      lo escribe una persona no    no
  OrdenTrabajo numero         (org, numero) Max+1 por org + reintento no  cubierto

"FU" es 'select_for_update()'. No cubre la carrera del primer numero del dia:
bloquea las filas que el SELECT devuelve, y cuando todavia no hay ninguna con
ese prefijo no hay nada que bloquear. Es la misma leccion que ya costo una vez
en 'campo/services/despacho.py', donde se resolvio dejando chocar la constraint
y reintentando.

'OrdenTrabajo' es el unico de los tres generados que esta bien: constraint por
organizacion y reintento probado contra PostgreSQL.
"""

import threading

import pytest
from django.db import connection, transaction
from django.utils import timezone

from common.models import Org
from invoices.models import Estimate, Invoice

pytestmark = [pytest.mark.postgres_only, pytest.mark.django_db(transaction=True)]


def _contexto(valor):
    with connection.cursor() as cur:
        cur.execute("SELECT set_config('app.current_org', %s, false)", [valor])


def _exigir_rol_que_respeta_rls():
    import os

    if connection.vendor != "postgresql":
        motivo = "la base no es PostgreSQL"
    else:
        with connection.cursor() as cur:
            cur.execute("SELECT rolname, rolsuper, rolbypassrls FROM pg_roles "
                        "WHERE rolname = current_user")
            nombre, superusuario, evade = cur.fetchone()
        if not (superusuario or evade):
            return
        motivo = (f"el rol '{nombre}' evade RLS (rolsuper={superusuario}, "
                  f"rolbypassrls={evade})")

    if os.environ.get("RLS_GATE", "") not in ("", "0", "false"):
        pytest.fail(f"RLS_GATE=1: {motivo}")
    pytest.skip(f"{motivo} (con RLS_GATE=1 esto seria un fallo)")


# --- el barrido, como guarda ------------------------------------------------

def test_solo_dos_numeradores_tienen_constraint_global():
    """Si aparece un tercero, esta prueba lo nombra.

    El patron peligroso es: numero VISIBLE + 'unique=True' global + generador
    que consulta filas que RLS filtra. Un numerador nuevo que lo repita tiene
    el mismo defecto desde el primer dia, y sin esta guarda nadie lo vería
    hasta que dos empresas chocaran en produccion.
    """
    from django.apps import apps

    CONOCIDOS = {("invoices", "Invoice", "invoice_number"),
                 ("invoices", "Estimate", "estimate_number")}

    globales = set()
    for modelo in apps.get_models():
        for campo in modelo._meta.local_fields:
            if not getattr(campo, "unique", False) or campo.primary_key:
                continue
            nombre = campo.name.lower()
            if not any(p in nombre for p in ("number", "numero", "consecutiv",
                                             "correlativ", "folio")):
                continue
            globales.add((modelo._meta.app_label, modelo.__name__, campo.name))

    nuevos = globales - CONOCIDOS
    assert not nuevos, (
        f"numerador(es) con constraint GLOBAL que no estaban en el barrido: "
        f"{sorted(nuevos)}. Si genera su valor consultando filas que RLS "
        f"filtra, tiene el mismo defecto: dos empresas generan el mismo numero "
        f"y la segunda choca. Ver el encabezado de este archivo.")

    faltan = CONOCIDOS - globales
    assert not faltan, (
        f"{sorted(faltan)} ya no tiene constraint global: si se arreglo, "
        f"actualizar este barrido y quitar los xfail de abajo")


def test_el_numerador_de_campo_si_esta_por_organizacion():
    """El contraejemplo, para que se vea cual es la forma correcta."""
    from campo.models import OrdenTrabajo

    compuestas = [c for c in OrdenTrabajo._meta.constraints
                  if getattr(c, "fields", None) and "numero" in c.fields]
    assert compuestas, "OrdenTrabajo.numero perdio su constraint"
    assert any("org" in c.fields for c in compuestas), (
        "la unicidad de OrdenTrabajo.numero dejo de llevar 'org' adentro")

    campo_numero = OrdenTrabajo._meta.get_field("numero")
    assert not campo_numero.unique, (
        "OrdenTrabajo.numero se volvio unique GLOBAL: es el defecto que este "
        "archivo documenta, ahora en campo")


# --- el defecto, reproducido -------------------------------------------------

@pytest.mark.xfail(
    strict=True,
    reason="DEFECTO REPRODUCIBLE, preexistente y ajeno a la entrega de campo. "
           "'Estimate.estimate_number' es unique GLOBAL y su generador consulta "
           "filas filtradas por RLS: dos organizaciones que crean un "
           "presupuesto el mismo dia generan ambas 'EST-AAAAMMDD-0001' y la "
           "segunda choca. Un tenant le impide a otro crear un presupuesto. "
           "strict=True a proposito: si esto empieza a pasar, la suite falla "
           "con XPASS y obliga a cerrar la deuda en vez de dejarla abierta.")
def test_DEFECTO_dos_organizaciones_chocan_en_estimate():
    _exigir_rol_que_respeta_rls()

    a = Org.objects.create(name="Num Org A")
    b = Org.objects.create(name="Num Org B")
    for org, titulo in ((a, "De la A"), (b, "De la B")):
        _contexto(str(org.id))
        try:
            Estimate.objects.create(org=org, title=titulo, currency="USD",
                                    issue_date=timezone.localdate())
        finally:
            _contexto("")


@pytest.mark.xfail(
    strict=True,
    reason="Mismo defecto que en Estimate, mismo generador, misma constraint "
           "global. Se prueba aparte porque arreglar uno no arregla el otro.")
def test_DEFECTO_dos_organizaciones_chocan_en_invoice():
    _exigir_rol_que_respeta_rls()

    a = Org.objects.create(name="Num Inv A")
    b = Org.objects.create(name="Num Inv B")
    for org in (a, b):
        _contexto(str(org.id))
        try:
            Invoice.objects.create(org=org, currency="USD",
                                   issue_date=timezone.localdate(),
                                   due_date=timezone.localdate())
        finally:
            _contexto("")


# --- la carrera DENTRO del mismo tenant -------------------------------------

def test_dos_presupuestos_simultaneos_del_MISMO_tenant():
    """Cambiar la constraint a "por organizacion" no arregla esto.

    'select_for_update()' bloquea las filas que el SELECT devuelve. Cuando
    todavia no hay ninguna con el prefijo del dia --el primer presupuesto de la
    mañana-- no hay nada que bloquear, y dos peticiones simultaneas calculan el
    mismo numero.

    Es la misma leccion que ya costo una vez en 'campo/services/despacho.py',
    donde se resolvio dejando chocar la constraint y reintentando. Esta prueba
    mide si el numerador de presupuestos la aprendio.
    """
    _exigir_rol_que_respeta_rls()

    org = Org.objects.create(name="Num Org Carrera")
    errores, numeros = [], []
    barrera = threading.Barrier(2)

    def crear():
        try:
            barrera.wait(timeout=10)
            with transaction.atomic():
                _contexto(str(org.id))
                e = Estimate.objects.create(org=org, title="Simultaneo",
                                            currency="USD",
                                            issue_date=timezone.localdate())
                numeros.append(e.estimate_number)
        except Exception as e:                                   # noqa: BLE001
            errores.append(f"{type(e).__name__}: {e}")
        finally:
            connection.close()

    hilos = [threading.Thread(target=crear) for _ in range(2)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=30)

    # Lo que se afirma es el INVARIANTE, no el mecanismo: o los dos entran con
    # numeros distintos, o uno falla limpio. Lo que no puede pasar es que los
    # dos crean haber entrado con el mismo numero.
    if len(numeros) == 2:
        assert numeros[0] != numeros[1], (
            f"dos presupuestos simultaneos del mismo tenant recibieron el "
            f"MISMO numero: {numeros}")
    else:
        assert errores, "un hilo no creo nada y tampoco fallo"
        print(f"\n  la carrera se resolvio fallando: {errores}")
