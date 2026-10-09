# -*- coding: utf-8 -*-
"""
Guardas de common/credenciales.py  --  Etapa B.4.

Todo lo de este archivo corre SIN base de datos y SIN Django configurado: la
logica de entorno es aritmetica de cadenas sobre un dict, a proposito. Las
comprobaciones que si necesitan la base estan en test_credenciales_postgres.py.

Cada prueba afirma sobre el EFECTO (¿aborta o no? ¿que codigo?), nunca sobre
que exista una funcion o una constante: una prueba que solo comprueba que el
mecanismo esta presente sobrevive intacta a una inversion de la conducta.
"""

import pytest

from common import credenciales as cr

# El sufijo real del pooler en produccion. Se usa tal cual en varias pruebas
# porque el recorte del sufijo es justo donde una guarda ingenua se rompe.
TENANT = ".05b5a4b4-3b9a-4901-86f2-f3ed8f8ac0a1"


def codigos(problemas):
    return sorted({p.codigo for p in problemas})


def graves(problemas):
    return [p for p in problemas if p.gravedad == cr.ERROR]


# =============================================================================
#  El recorte del sufijo de Supavisor
# =============================================================================

@pytest.mark.parametrize("entrada,esperado", [
    ("crm_user", "crm_user"),
    ("crm_user" + TENANT, "crm_user"),
    ("postgres" + TENANT, "postgres"),
    ("motor_user" + TENANT, "motor_user"),
    ("  crm_user  ", "crm_user"),
    ("", ""),
    (None, ""),
])
def test_rol_base_recorta_el_sufijo_del_pooler(entrada, esperado):
    assert cr.rol_base(entrada) == esperado


def test_sin_recortar_el_sufijo_la_guarda_no_veria_nada():
    """
    La prueba que justifica que rol_base() exista.

    En produccion DBUSER es 'crm_user.05b5a4b4-...', no 'crm_user'. Una guarda
    que comparara la cadena completa contra 'crm_user' no coincidiria nunca y
    quedaria en verde sin haber comprobado nada.
    """
    entorno = {"DBUSER": "crm_migrator" + TENANT}
    problemas = cr.revisar_entorno(entorno, cr.PROPOSITO_TRAFICO)
    assert "B" in codigos(problemas), (
        "con el sufijo del pooler puesto, la guarda tiene que seguir "
        "reconociendo el rol")
    assert entorno["DBUSER"] != cr.ROL_MIGRACIONES, (
        "si estas dos cadenas fueran iguales, esta prueba no probaria nada")


# =============================================================================
#  A  --  migrar con el usuario de trafico
# =============================================================================

def test_migrar_como_crm_user_avisa_pero_no_aborta():
    """
    NO aborta, y es deliberado: el compose de desarrollo migra como crm_user y
    funciona, porque alli crm_user es dueno de todo el esquema
    (docker/postgres/init-rls-user.sql le da ALL sobre 'public').

    Decidir esto por el NOMBRE del rol habria roto el entorno de desarrollo de
    todo el mundo. Lo que decide es la propiedad, y eso se mide contra la base.
    """
    problemas = cr.revisar_entorno(
        {"DBUSER": "crm_user"}, cr.PROPOSITO_MIGRACIONES)
    assert "A" in codigos(problemas)
    assert not cr.hay_que_abortar(problemas)


def test_migrator_sin_contrasena_aborta():
    problemas = cr.revisar_entorno(
        {"DBUSER": "postgres", "MIGRATOR_DBUSER": "crm_migrator"},
        cr.PROPOSITO_MIGRACIONES)
    assert cr.hay_que_abortar(problemas)


def test_migrator_apuntando_al_rol_equivocado_aborta():
    for equivocado in ("crm_user", "postgres", "motor_user"):
        problemas = cr.revisar_entorno(
            {"DBUSER": "postgres", "MIGRATOR_DBUSER": equivocado + TENANT,
             "MIGRATOR_DBPASSWORD": "x"},
            cr.PROPOSITO_MIGRACIONES)
        assert cr.hay_que_abortar(problemas), (
            f"MIGRATOR_DBUSER={equivocado} tiene que abortar")


# =============================================================================
#  B  --  la credencial de migraciones sirviendo trafico
# =============================================================================

def test_trafico_con_crm_migrator_aborta():
    problemas = cr.revisar_entorno(
        {"DBUSER": "crm_migrator" + TENANT}, cr.PROPOSITO_TRAFICO)
    assert "B" in codigos(problemas)
    assert cr.hay_que_abortar(problemas), (
        "crm_migrator actua como crm_owner: servir peticiones con el es "
        "servirlas como DUENO de las tablas, y un dueno se saltea su propia "
        "politica salvo que este FORCE")


# =============================================================================
#  C  --  trafico con el rol de emergencia
# =============================================================================

def test_trafico_con_postgres_avisa_pero_no_aborta():
    """
    Es el estado REAL de produccion (medido en B.2: DBUSER=postgres al
    11/09/2026). Volverlo fatal haria que este mismo codigo impidiera arrancar
    el backend en el instante en que se desplegara.
    """
    problemas = cr.revisar_entorno(
        {"DBUSER": "postgres" + TENANT}, cr.PROPOSITO_TRAFICO)
    assert "C" in codigos(problemas)
    assert not cr.hay_que_abortar(problemas)


def test_el_modo_estricto_convierte_ese_aviso_en_error():
    problemas = cr.revisar_entorno(
        {"DBUSER": "postgres" + TENANT, cr.VAR_ESTRICTO: "1"},
        cr.PROPOSITO_TRAFICO)
    assert cr.hay_que_abortar(problemas), (
        "el interruptor existe para encenderlo DESPUES de la transicion")


@pytest.mark.parametrize("valor", ["0", "", "no", "false", None])
def test_el_modo_estricto_esta_apagado_por_defecto(valor):
    entorno = {"DBUSER": "postgres"}
    if valor is not None:
        entorno[cr.VAR_ESTRICTO] = valor
    assert not cr.hay_que_abortar(
        cr.revisar_entorno(entorno, cr.PROPOSITO_TRAFICO))


# =============================================================================
#  D y E  --  el incidente del 18/08/2026
# =============================================================================

@pytest.mark.parametrize("rol_crm", ["crm_user", "crm_migrator"])
def test_el_motor_apuntando_a_una_credencial_del_crm_aborta(rol_crm):
    """
    Esto paso de verdad: 'backend', 'celery-*' y 'motor' compartian ${DBUSER}.
    Al cortarlo a crm_user, el motor perdio 'asistente' y dejo de guardar
    mensajes EN SILENCIO, porque atrapa la excepcion y solo la logea.
    """
    problemas = cr.revisar_entorno(
        {"DBUSER": "postgres" + TENANT,
         "MOTOR_DBUSER": rol_crm + TENANT},
        cr.PROPOSITO_TRAFICO)
    assert codigos(problemas) and cr.hay_que_abortar(problemas)
    assert any(p.codigo in ("D", "E") for p in graves(problemas))


def test_una_sola_variable_para_el_motor_y_el_crm_aborta():
    """La forma EXACTA que tenia la configuracion el 18/08."""
    compartida = "postgres" + TENANT
    problemas = cr.revisar_entorno(
        {"DBUSER": compartida, "MOTOR_DBUSER": compartida},
        cr.PROPOSITO_TRAFICO)
    assert cr.hay_que_abortar(problemas)


def test_el_motor_con_su_propio_rol_no_se_queja():
    problemas = cr.revisar_entorno(
        {"DBUSER": "crm_user" + TENANT,
         "MOTOR_DBUSER": "motor_user" + TENANT},
        cr.PROPOSITO_TRAFICO)
    assert not problemas, f"no deberia haber ningun problema: {problemas}"


# =============================================================================
#  La configuracion objetivo, y la de hoy
# =============================================================================

def test_la_configuracion_objetivo_de_b3_pasa_limpia():
    entorno = {
        "DBUSER": "crm_user" + TENANT,
        "MIGRATOR_DBUSER": "crm_migrator" + TENANT,
        "MIGRATOR_DBPASSWORD": "x",
        "MOTOR_DBUSER": "motor_user" + TENANT,
    }
    assert cr.revisar_entorno(entorno, cr.PROPOSITO_TRAFICO) == []
    problemas = cr.revisar_entorno(entorno, cr.PROPOSITO_MIGRACIONES)
    assert not cr.hay_que_abortar(problemas)


def test_la_configuracion_de_hoy_arranca_igual():
    """
    Lo que esta desplegado ahora mismo. Esta prueba es la que garantiza que
    desplegar B.4 no tumba nada: sin MIGRATOR_* definidas y con DBUSER=postgres,
    el arranque sigue.
    """
    entorno = {
        "DBUSER": "postgres" + TENANT,
        "MOTOR_DBUSER": "motor_user" + TENANT,
    }
    assert not cr.hay_que_abortar(cr.revisar_entorno(entorno, cr.PROPOSITO_TRAFICO))
    assert not cr.hay_que_abortar(cr.revisar_entorno(entorno, cr.PROPOSITO_MIGRACIONES))


def test_la_configuracion_de_desarrollo_arranca_igual():
    """docker-compose.yml: DBUSER=crm_user, sin MIGRATOR_*, sin MOTOR_DBUSER."""
    entorno = {"DBUSER": "crm_user"}
    assert not cr.hay_que_abortar(cr.revisar_entorno(entorno, cr.PROPOSITO_TRAFICO))
    assert not cr.hay_que_abortar(cr.revisar_entorno(entorno, cr.PROPOSITO_MIGRACIONES))


def test_un_proposito_inventado_es_un_error_de_programacion():
    with pytest.raises(ValueError):
        cr.revisar_entorno({"DBUSER": "crm_user"}, "cualquier_cosa")


def test_cada_problema_dice_que_hacer():
    """
    Un mensaje sin remedio obliga a quien lo lee a las 3 de la manana a
    reconstruir el razonamiento entero.
    """
    problemas = cr.revisar_entorno(
        {"DBUSER": "crm_migrator", "MOTOR_DBUSER": "crm_user"},
        cr.PROPOSITO_TRAFICO)
    assert problemas
    for p in problemas:
        assert p.remedio.strip(), f"{p.codigo} no dice como arreglarlo"
        assert p.gravedad in (cr.ERROR, cr.AVISO)
