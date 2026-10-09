# -*- coding: utf-8 -*-
"""
===============================================================================
 LA POLITICA DE AISLAMIENTO TIENE QUE PODER USAR EL INDICE
===============================================================================

QUE PASO, medido el 09/10/2026
------------------------------
La pantalla del Supervisor NOC tardaba 22 SEGUNDOS en cargar. En la misma
sesion, TODAS las demas peticiones tardaban menos de 500 ms -- lo que descarto
la red, el frontend y el sondeo del panel, que eran las sospechas iniciales.

La causa estaba en la politica de RLS: decia `org_id::text = (select ...)`.
Castear la COLUMNA deja inutilizable cualquier indice sobre org_id, asi que
Postgres lee la tabla entera y convierte fila por fila. Y como la politica se
aplica a TODAS las consultas de las 65 tablas con aislamiento, cada una se
volvia un recorrido secuencial.

    org_id::text = text  ->  Parallel Seq Scan   70,4 ms
    org_id = uuid        ->  Index Only Scan      6,7 ms   (200.000 filas)

POR QUE ESTA GUARDA AFIRMA UN PLAN Y NO UN TEXTO
------------------------------------------------
Comprobar que el SQL "no diga ::text" seria afirmar la ausencia de una cadena:
pasaria con cualquier otra forma de romper el indice --una funcion sobre la
columna, un cast distinto, un LOWER()-- y ninguna se veria.

Lo que hay que sostener es el EFECTO: que Postgres pueda llegar por indice. Se
construye una tabla con su indice, se le aplica la politica REAL --la que
genera 'get_enable_policy_sql', no una copia-- y se mira el plan.

Y el aislamiento se comprueba aparte, abajo: una politica rapida que deje ver
filas de otra empresa seria mucho peor que una lenta.
"""
import re
import uuid

import pytest
from django.db import connection

from common.rls import CONTEXT_VARIABLE, get_enable_policy_sql

#  Bastantes filas para que el planificador PREFIERA el indice. Con pocas,
#  recorrer la tabla es legitimamente mas barato y el plan diria 'Seq Scan'
#  por un motivo que no es el que esta prueba vigila.
FILAS = 20000


def _predicado_de_la_politica() -> str:
    """
    La condicion que la politica REAL usa, sacada del SQL que se despliega.

    No se escribe a mano: si alguien cambia la plantilla, esta prueba tiene que
    medir lo nuevo, no una copia que quedo vieja.
    """
    sql = get_enable_policy_sql("x")
    m = re.search(r"USING\s*\(\s*(.+?)\s*\)\s*;", sql, re.S)
    assert m, "no se pudo leer la condicion USING de la politica"
    return m.group(1).strip()


@pytest.mark.django_db(transaction=True)
def test_la_politica_puede_llegar_por_indice():
    if connection.vendor != "postgresql":
        pytest.skip("RLS y planes de consulta son de PostgreSQL")

    de_la_empresa = uuid.uuid4()
    with connection.cursor() as cur:
        cur.execute("""
            create table if not exists t_plan_rls (
                id serial primary key, org_id uuid not null, dato text)
        """)
        cur.execute("truncate t_plan_rls")
        cur.execute("create index if not exists t_plan_rls_org on t_plan_rls (org_id)")
        cur.execute("""
            insert into t_plan_rls (org_id, dato)
            select case when i %% 100 = 0 then %s::uuid else gen_random_uuid() end,
                   'x'
              from generate_series(1, %s) i
        """, [str(de_la_empresa), FILAS])
        cur.execute("analyze t_plan_rls")

        cur.execute("select set_config(%s, %s, false)",
                    [CONTEXT_VARIABLE, str(de_la_empresa)])
        cur.execute(
            f"explain select count(*) from t_plan_rls "
            f"where {_predicado_de_la_politica()}")
        plan = "\n".join(f[0] for f in cur.fetchall())
        cur.execute("drop table t_plan_rls")

    assert "Index" in plan, (
        "la condicion de la politica de aislamiento NO puede usar el indice "
        "sobre org_id, asi que cada consulta de cada tabla con RLS recorre la "
        "tabla entera. Asi se llego a una pantalla de 22 segundos el "
        f"09/10/2026. Plan obtenido:\n{plan}")
    assert "Seq Scan" not in plan, f"recorrido secuencial:\n{plan}"


@pytest.mark.django_db(transaction=True)
def test_la_politica_sigue_aislando():
    """
    RAPIDA NO SIRVE DE NADA SI DEJA VER LO AJENO. Los casos que importan, con
    la politica real aplicada.

    CORRE BAJO UN ROL CREADO AQUI, y no es un detalle de montaje: UN
    SUPERUSUARIO DE POSTGRES SE SALTEA EL RLS SIEMPRE, incluso con 'FORCE ROW
    LEVEL SECURITY'. La primera version de esta prueba corria con el usuario
    de las pruebas --superusuario-- y la empresa A vio LAS TRES filas.

    Fallo por el motivo correcto y por eso se corrige asi en vez de bajar la
    expectativa: una guarda de aislamiento que corre con quien puede
    saltearselo no mide el aislamiento, mide nada, y habria quedado en verde
    para siempre.
    """
    if connection.vendor != "postgresql":
        pytest.skip("RLS es de PostgreSQL")

    a, b = uuid.uuid4(), uuid.uuid4()
    rol = f"rls_prueba_{uuid.uuid4().hex[:8]}"
    with connection.cursor() as cur:
        cur.execute("""
            create table if not exists t_aisla_rls (
                id serial primary key, org_id uuid not null)
        """)
        cur.execute("truncate t_aisla_rls")
        cur.execute("insert into t_aisla_rls (org_id) values (%s),(%s),(%s)",
                    [str(a), str(a), str(b)])
        #  LA POLITICA REAL, la misma que se despliega.
        cur.execute(get_enable_policy_sql("t_aisla_rls"))

        #  UN ROL SIN PRIVILEGIOS ESPECIALES. Nombre unico porque los roles son
        #  del cluster entero y dos corridas en paralelo chocarian.
        cur.execute(f'create role "{rol}"')
        cur.execute(f'grant select on t_aisla_rls to "{rol}"')

        def cuantas(valor):
            cur.execute(f'set role "{rol}"')
            cur.execute("select set_config(%s, %s, false)",
                        [CONTEXT_VARIABLE, valor])
            cur.execute("select count(*) from t_aisla_rls")
            n = cur.fetchone()[0]
            cur.execute("reset role")
            return n

        try:
            de_a, de_b, vacio = cuantas(str(a)), cuantas(str(b)), cuantas("")
        finally:
            #  SIEMPRE: un rol que queda vivo hace fallar la corrida siguiente
            #  con "ya existe", y el mensaje no señalaria aqui.
            cur.execute("reset role")
            cur.execute(f'revoke all on t_aisla_rls from "{rol}"')
            cur.execute("drop table t_aisla_rls")
            cur.execute(f'drop role if exists "{rol}"')

    assert de_a == 2, f"la empresa A tendria que ver 2 y vio {de_a}"
    assert de_b == 1, f"la empresa B tendria que ver 1 y vio {de_b}"
    assert vacio == 0, (
        f"SIN CONTEXTO se vieron {vacio} filas. El aislamiento falla ABIERTO: "
        f"cualquier consulta que olvide fijar la empresa ve todo")
