"""
'manage_rls' no puede afirmar que RLS se aplica cuando no se aplica.

    pytest common/tests/test_manage_rls_no_miente.py --no-cov -v

POR QUE EXISTE
--------------
El comando preguntaba 'pg_user.usesuper' y nada mas. 'rolsuper' y
'rolbypassrls' son atributos DISTINTOS y cualquiera de los dos evade RLS;
'pg_user' no expone el segundo.

En Supabase el rol 'postgres' tiene rolsuper=false y rolbypassrls=true. Sobre
ese rol el comando respondia:

    Database user postgres is not a superuser - RLS will be enforced

Una afirmacion de seguridad FALSA, con el aislamiento desactivado, dicha por la
propia herramienta de verificacion. Esta escrito en DESPLIEGUE.md que paso, y
ahi mismo se afirmaba que '--verify-user' si preguntaba lo correcto -- tambien
falso: preguntaba exactamente lo mismo.

Medido en el PostgreSQL efimero sobre un rol NOSUPERUSER BYPASSRLS:

    SELECT usename, usesuper FROM pg_user  -> crm_bypass | f     ("seguro")
    SELECT rolsuper, rolbypassrls          -> f | t              (evade RLS)

LOS CUATRO ESCENARIOS
---------------------
    rol normal            pasa
    rol SUPERUSER         falla
    rol BYPASSRLS         falla   <- el que el codigo viejo no veia
    rol inexistente       falla   <- indeterminado es fallo, no permiso
"""

import pytest

pytestmark = pytest.mark.django_db


class CursorFalso:
    """Responde las dos consultas de 'inspeccionar_rol' y nada mas."""

    def __init__(self, usuario, fila_rol):
        self.usuario = usuario
        self.fila_rol = fila_rol
        self._ultima = None

    def execute(self, sql, params=None):
        self._ultima = "roles" if "pg_roles" in sql else "usuario"

    def fetchone(self):
        if self._ultima == "usuario":
            return (self.usuario, self.usuario)
        return self.fila_rol


def _inspeccionar(usuario, fila_rol):
    from common.management.commands.manage_rls import inspeccionar_rol

    return inspeccionar_rol(CursorFalso(usuario, fila_rol))


# --- los cuatro escenarios ---------------------------------------------------

def test_un_rol_normal_pasa():
    datos, problemas = _inspeccionar("crm_user", ("crm_user", False, False, True))
    assert problemas == [], f"un rol sujeto a RLS no deberia dar problemas: {problemas}"
    assert datos["rol"] == "crm_user"
    assert datos["rolsuper"] is False
    assert datos["rolbypassrls"] is False


def test_un_superusuario_falla():
    _, problemas = _inspeccionar("postgres", ("postgres", True, False, True))
    assert problemas, "un SUPERUSER evade RLS y tiene que dar problema"
    assert any("SUPERUSER" in p for p in problemas)


def test_un_rol_con_bypassrls_que_NO_es_superusuario_falla():
    """EL CASO QUE EL CODIGO VIEJO NO VEIA.

    'pg_user.usesuper' devuelve false para este rol, asi que el comando
    respondia "not a superuser - RLS will be enforced" con el aislamiento
    desactivado. Es exactamente la forma del rol 'postgres' de Supabase.
    """
    _, problemas = _inspeccionar("crm_bypass", ("crm_bypass", False, True, True))
    assert problemas, (
        "un rol con BYPASSRLS evade RLS aunque no sea superusuario: es el caso "
        "que 'pg_user.usesuper' no puede ver")
    assert any("BYPASSRLS" in p for p in problemas)


def test_un_rol_inexistente_falla_en_vez_de_pasar():
    """Indeterminado es un fallo, no un permiso.

    La unica respuesta peor que "no aisla" es "no se sabe, pasa igual".
    """
    datos, problemas = _inspeccionar("fantasma", None)
    assert problemas, "no poder comprobar tiene que ser un problema"
    assert any("no se pudo hacer" in p or "no se encontro" in p for p in problemas)
    assert "rolsuper" not in datos, "no se inventan atributos de un rol que no existe"


# --- lo que el informe muestra ----------------------------------------------

def test_informa_current_user_y_session_user():
    datos, _ = _inspeccionar("crm_user", ("crm_user", False, False, True))
    assert datos["current_user"] == "crm_user"
    assert datos["session_user"] == "crm_user"


def test_no_se_consulta_pg_user_en_ningun_lado():
    """La fuente equivocada no puede volver por otra puerta.

    'pg_user' es una vista de compatibilidad que NO expone 'rolbypassrls'.
    Cualquier comprobacion de seguridad que la use vuelve a tener el defecto.
    """
    from pathlib import Path

    fuente = Path(
        "common/management/commands/manage_rls.py").read_text(encoding="utf-8")
    # Se busca el SQL, no la palabra: el docstring de 'inspeccionar_rol'
    # NOMBRA pg_user justamente para explicar por que no se usa.
    import re

    consultas = re.findall(r"from\s+pg_user", fuente, re.I)
    assert not consultas, (
        f"vuelve a consultarse pg_user en SQL ({len(consultas)} vez/veces): esa "
        f"vista no expone 'rolbypassrls', asi que cualquier comprobacion de "
        f"seguridad que la use vuelve a tener el defecto original")

    assert "pg_roles" in fuente, "la comprobacion tiene que salir de pg_roles"


def test_el_comando_puede_terminar_distinto_de_cero():
    """Un comando de seguridad que informa un problema y sale 0 no sirve.

    Nadie lo pone en un pipeline; y si alguien lo pone, no protege nada.
    """
    from pathlib import Path

    fuente = Path(
        "common/management/commands/manage_rls.py").read_text(encoding="utf-8")
    assert "CommandError" in fuente
    assert fuente.count("raise CommandError") >= 2, (
        "tanto --status como --verify-user tienen que poder fallar")
