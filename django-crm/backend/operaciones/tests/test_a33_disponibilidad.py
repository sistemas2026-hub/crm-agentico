# -*- coding: utf-8 -*-
"""
================================================================================
 A-3.3  --  la via operativa de disponibilidad
================================================================================

Lo que estas pruebas afirman NO es que exista una vista: es que la vista se
comporta como debe cuando alguien intenta usarla mal.

Las tres que mas importan, y por que:

  1. UN PERFIL DE OTRA ORGANIZACION NO SE PUEDE USAR. Es el control de
     aislamiento en la escritura, y es el que un CRUD generico se saltea sin que
     nadie lo note: el 'profile' llega como id en el cuerpo, y si se confia en
     el, cualquiera registra ausencias de tecnicos ajenos.

  2. LA ORGANIZACION NO SE PUEDE ELEGIR. Aunque el cliente mande 'org' en el
     payload, la fila queda en request.org. A-3.1 midio que la fuente confiable
     es el JWT revalidado, no el cuerpo.

  3. NO SE BORRA. Una ausencia declarada pudo haber movido trabajo.

Y una que afirma una AUSENCIA de capacidad: el Supervisor NOC IA no tiene
ninguna herramienta que escriba esta tabla.
================================================================================
"""

import uuid
from datetime import date, time, timedelta

import pytest
from django.utils import timezone

from conftest import rls_org
from operaciones.models import DisponibilidadTecnico

RUTA = "/api/operaciones/disponibilidad/"


# =============================================================================
#  utilidades
# =============================================================================

def _perfil(org, correo, rol):
    from common.models import Profile, User
    u = User.objects.create_user(email=correo, password="clave-de-prueba-1")
    return Profile.objects.create(user=u, org=org, role=rol, is_active=True)


def _cliente(org, rol, correo):
    """Un cliente autenticado con el rol pedido, y su perfil."""
    from conftest import _make_authenticated_client
    p = _perfil(org, correo, rol)
    return _make_authenticated_client(p.user, org, p), p


def _cuerpo(profile, **extra):
    datos = {
        "profile": str(profile.id),
        "fecha": str(date.today() + timedelta(days=1)),
        "hora_inicio": "08:00",
        "hora_fin": "12:00",
        "disponible": True,
    }
    datos.update(extra)
    return datos


# =============================================================================
#  1-2.  REGISTRAR
# =============================================================================

def test_el_supervisor_registra_una_franja_disponible(org_a):
    cli, _ = _cliente(org_a, "SUPERVISOR", "sup.reg@prueba.local")
    tecnico = _perfil(org_a, "tec1@prueba.local", "USER")

    r = cli.post(RUTA, _cuerpo(tecnico), format="json")

    assert r.status_code == 201, r.content
    franja = DisponibilidadTecnico.objects.get(id=r.json()["disponibilidad"]["id"])
    assert franja.profile_id == tecnico.id
    assert franja.org_id == org_a.id
    assert franja.disponible is True


def test_una_ausencia_con_motivo_se_registra(org_a):
    cli, _ = _cliente(org_a, "SUPERVISOR", "sup.aus@prueba.local")
    tecnico = _perfil(org_a, "tec2@prueba.local", "USER")

    r = cli.post(RUTA, _cuerpo(tecnico, disponible=False,
                               motivo="incapacidad médica"), format="json")

    assert r.status_code == 201, r.content
    franja = DisponibilidadTecnico.objects.get(id=r.json()["disponibilidad"]["id"])
    assert franja.disponible is False
    assert franja.motivo == "incapacidad médica"
    #  La respuesta dice el hecho como lo dice la operación, no solo el booleano.
    assert r.json()["disponibilidad"]["es_ausencia"] is True


def test_la_respuesta_aclara_que_no_reprograma(org_a):
    """
    El aviso no es decoración.

    Quien registra una ausencia podría suponer que el sistema movió el trabajo.
    No lo movió: M03 es el dueño de ese efecto.
    """
    cli, _ = _cliente(org_a, "SUPERVISOR", "sup.aviso@prueba.local")
    tecnico = _perfil(org_a, "tec.aviso@prueba.local", "USER")
    r = cli.post(RUTA, _cuerpo(tecnico), format="json")
    assert "NO reprograma ni reasigna" in r.json()["aviso"]


# =============================================================================
#  3-4.  LO QUE LA BASE YA EXIGIA, DICHO A TIEMPO
# =============================================================================

def test_una_ausencia_sin_motivo_se_rechaza(org_a):
    """
    'ausencia_exige_motivo' ya vive en la base. Aquí se comprueba que además
    llega como un 400 legible, no como un IntegrityError.
    """
    cli, _ = _cliente(org_a, "SUPERVISOR", "sup.sinmotivo@prueba.local")
    tecnico = _perfil(org_a, "tec3@prueba.local", "USER")

    r = cli.post(RUTA, _cuerpo(tecnico, disponible=False, motivo=""),
                 format="json")

    assert r.status_code == 400
    assert "motivo" in r.json()
    assert DisponibilidadTecnico.objects.count() == 0


def test_una_franja_invertida_se_rechaza(org_a):
    cli, _ = _cliente(org_a, "SUPERVISOR", "sup.franja@prueba.local")
    tecnico = _perfil(org_a, "tec4@prueba.local", "USER")

    r = cli.post(RUTA, _cuerpo(tecnico, hora_inicio="14:00", hora_fin="09:00"),
                 format="json")

    assert r.status_code == 400
    assert "hora_fin" in r.json()
    assert DisponibilidadTecnico.objects.count() == 0


def test_un_motivo_de_solo_espacios_no_cuenta_como_motivo(org_a):
    cli, _ = _cliente(org_a, "SUPERVISOR", "sup.espacios@prueba.local")
    tecnico = _perfil(org_a, "tec5@prueba.local", "USER")
    r = cli.post(RUTA, _cuerpo(tecnico, disponible=False, motivo="    "),
                 format="json")
    assert r.status_code == 400
    assert DisponibilidadTecnico.objects.count() == 0


# =============================================================================
#  5-6.  ORGANIZACION Y AISLAMIENTO
# =============================================================================

def test_la_organizacion_no_la_elige_el_cliente(org_a, org_b):
    """
    Aunque el payload traiga 'org', la fila queda en la del token.

    A-3.1 midió que la fuente confiable es el JWT revalidado contra Profile:
    *"This prevents org spoofing attacks"*. El serializador no declara 'org', así
    que lo que mande el cliente no tiene por dónde entrar.
    """
    cli, _ = _cliente(org_a, "SUPERVISOR", "sup.org@prueba.local")
    tecnico = _perfil(org_a, "tec6@prueba.local", "USER")

    cuerpo = _cuerpo(tecnico)
    cuerpo["org"] = str(org_b.id)
    cuerpo["organization_id"] = str(org_b.id)

    r = cli.post(RUTA, cuerpo, format="json")

    assert r.status_code == 201
    franja = DisponibilidadTecnico.objects.get(id=r.json()["disponibilidad"]["id"])
    assert franja.org_id == org_a.id, "el cliente eligió su organización"


def test_no_se_puede_registrar_una_ausencia_de_un_tecnico_ajeno(org_a, org_b):
    """
    El control de aislamiento en la ESCRITURA.

    'profile' llega como id en el cuerpo. Si se confiara en él, un supervisor
    podría declarar ausente a un técnico de otra empresa.
    """
    with rls_org(org_b):
        ajeno = _perfil(org_b, "tec.ajeno@prueba.local", "USER")

    cli, _ = _cliente(org_a, "SUPERVISOR", "sup.ajeno@prueba.local")
    r = cli.post(RUTA, _cuerpo(ajeno), format="json")

    assert r.status_code == 400
    assert "no existe en esta organización" in r.json()["error"]
    assert DisponibilidadTecnico.objects.filter(profile=ajeno).count() == 0


def test_la_consulta_solo_trae_lo_propio(org_a, org_b):
    cli, _ = _cliente(org_a, "SUPERVISOR", "sup.lista@prueba.local")
    mio = _perfil(org_a, "tec.mio@prueba.local", "USER")
    cli.post(RUTA, _cuerpo(mio), format="json")

    with rls_org(org_b):
        ajeno = _perfil(org_b, "tec.b@prueba.local", "USER")
        DisponibilidadTecnico.objects.create(
            org=org_b, profile=ajeno, fecha=date.today(),
            hora_inicio=time(8), hora_fin=time(12), disponible=True)

    r = cli.get(RUTA)

    assert r.status_code == 200
    assert r.json()["count"] == 1
    ids = {x["profile"] for x in r.json()["resultados"]}
    assert str(ajeno.id) not in ids


def test_un_supervisor_de_otra_organizacion_no_ve_lo_nuestro(org_a, org_b):
    cli_a, _ = _cliente(org_a, "SUPERVISOR", "sup.a@prueba.local")
    tec = _perfil(org_a, "tec.solo.a@prueba.local", "USER")
    cli_a.post(RUTA, _cuerpo(tec), format="json")

    with rls_org(org_b):
        cli_b, _ = _cliente(org_b, "SUPERVISOR", "sup.b@prueba.local")

    r = cli_b.get(RUTA)
    assert r.status_code == 200
    assert r.json()["count"] == 0


# =============================================================================
#  7.  PERMISOS
# =============================================================================

@pytest.mark.parametrize("rol,puede", [
    ("SUPERVISOR", True),       # el responsable, según la decisión de negocio
    ("OPERACIONES", True),      # el Jefe de Operaciones: excepciones
    ("ADMIN", True),            # cubre por arriba, como en todo el módulo
    ("USER", False),            # el técnico informa la novedad; no la registra
])
def test_quien_puede_registrar(org_a, rol, puede):
    cli, _ = _cliente(org_a, rol, f"reg.{rol.lower()}@prueba.local")
    tecnico = _perfil(org_a, f"tec.{rol.lower()}@prueba.local", "USER")

    r = cli.post(RUTA, _cuerpo(tecnico), format="json")

    assert (r.status_code == 201) is puede, f"{rol} -> {r.status_code}"
    assert (DisponibilidadTecnico.objects.count() == 1) is puede


@pytest.mark.parametrize("rol,puede", [
    ("SUPERVISOR", True), ("OPERACIONES", True), ("ADMIN", True),
    ("USER", False),
])
def test_quien_puede_consultar(org_a, rol, puede):
    cli, _ = _cliente(org_a, rol, f"con.{rol.lower()}@prueba.local")
    r = cli.get(RUTA)
    assert (r.status_code == 200) is puede


def test_sin_sesion_no_se_puede_nada(org_a, unauthenticated_client):
    tecnico = _perfil(org_a, "tec.sinsesion@prueba.local", "USER")
    assert unauthenticated_client.get(RUTA).status_code in (401, 403)
    assert unauthenticated_client.post(
        RUTA, _cuerpo(tecnico), format="json").status_code in (401, 403)
    assert DisponibilidadTecnico.objects.count() == 0


# =============================================================================
#  8.  EL SUPERVISOR NOC IA NO ESCRIBE
# =============================================================================

def test_el_supervisor_noc_ia_no_tiene_ninguna_herramienta_que_escriba():
    """
    Se afirma sobre el EFECTO, no sobre una intención.

    Ninguna habilidad declara escritura, y ninguna cita la disponibilidad como
    herramienta de escritura. Si mañana alguien agregara una, esto falla.
    """
    from operaciones import habilidades

    for h in habilidades.HABILIDADES.values():
        assert h.herramientas_escritura == (), \
            f"{h.id} declara escritura: {h.herramientas_escritura}"


def test_el_modulo_del_supervisor_no_escribe_disponibilidad():
    """
    La garantía no es una regla escrita: es una ausencia de código.

    'supervisor.py' lee DisponibilidadTecnico en _ordenes_en_riesgo y en ningún
    lado la crea, actualiza ni borra.
    """
    import inspect

    from operaciones import supervisor

    fuente = inspect.getsource(supervisor)
    for escritura in ("DisponibilidadTecnico.objects.create",
                      "DisponibilidadTecnico.objects.update",
                      "DisponibilidadTecnico.objects.delete",
                      "DisponibilidadTecnico.objects.bulk_create"):
        assert escritura not in fuente, f"supervisor.py hace {escritura}"


# =============================================================================
#  9-10.  CONSULTA Y AUDITORIA
# =============================================================================

def test_la_consulta_filtra_por_fecha_y_por_ausencia(org_a):
    cli, _ = _cliente(org_a, "SUPERVISOR", "sup.filtros@prueba.local")
    tecnico = _perfil(org_a, "tec.filtros@prueba.local", "USER")
    manana = date.today() + timedelta(days=1)
    pasado = date.today() + timedelta(days=2)

    cli.post(RUTA, _cuerpo(tecnico, fecha=str(manana)), format="json")
    cli.post(RUTA, _cuerpo(tecnico, fecha=str(pasado), disponible=False,
                           motivo="vacaciones"), format="json")

    assert cli.get(RUTA).json()["count"] == 2
    assert cli.get(f"{RUTA}?fecha={manana}").json()["count"] == 1
    assert cli.get(f"{RUTA}?ausencias=1").json()["count"] == 1
    assert cli.get(f"{RUTA}?profile={tecnico.id}").json()["count"] == 2


def test_queda_registrado_quien_lo_cargo_y_cuando(org_a):
    """
    La auditoría que SÍ existe hoy.

    'BaseModel.save()' escribe created_by desde crum con el usuario de la
    petición. No se acepta por payload: firmar como otro no puede ser un campo
    de entrada.
    """
    cli, supervisor_profile = _cliente(org_a, "SUPERVISOR",
                                       "sup.audit@prueba.local")
    tecnico = _perfil(org_a, "tec.audit@prueba.local", "USER")

    r = cli.post(RUTA, _cuerpo(tecnico), format="json")
    franja = DisponibilidadTecnico.objects.get(id=r.json()["disponibilidad"]["id"])

    assert franja.created_by_id == supervisor_profile.user_id
    assert franja.created_at is not None


def test_no_se_puede_firmar_como_otro(org_a):
    cli, supervisor_profile = _cliente(org_a, "SUPERVISOR",
                                       "sup.firma@prueba.local")
    tecnico = _perfil(org_a, "tec.firma@prueba.local", "USER")
    otro = _perfil(org_a, "otro@prueba.local", "ADMIN")

    cuerpo = _cuerpo(tecnico)
    cuerpo["created_by"] = str(otro.user_id)

    r = cli.post(RUTA, cuerpo, format="json")
    franja = DisponibilidadTecnico.objects.get(id=r.json()["disponibilidad"]["id"])
    assert franja.created_by_id == supervisor_profile.user_id


# =============================================================================
#  11-12.  LO QUE NO SE IMPLEMENTO, Y ES DELIBERADO
# =============================================================================

def test_no_se_borra_una_ausencia(org_a):
    """
    Una ausencia declarada pudo haber movido trabajo.

    Borrar la fila hace desaparecer la causa de una decisión que sí se tomó, y
    deja una reprogramación sin explicación.
    """
    cli, _ = _cliente(org_a, "SUPERVISOR", "sup.borrar@prueba.local")
    tecnico = _perfil(org_a, "tec.borrar@prueba.local", "USER")
    cli.post(RUTA, _cuerpo(tecnico, disponible=False, motivo="permiso"),
             format="json")

    r = cli.delete(RUTA)

    assert r.status_code == 405
    assert r.json()["pendiente"] == "POLITICA DE CORRECCION"
    assert DisponibilidadTecnico.objects.count() == 1


def test_no_existe_ruta_de_correccion(org_a):
    """
    La política de corrección no está definida (A-3 §7), así que esta etapa
    implementa únicamente registro seguro. PUT y PATCH no están.
    """
    cli, _ = _cliente(org_a, "SUPERVISOR", "sup.put@prueba.local")
    tecnico = _perfil(org_a, "tec.put@prueba.local", "USER")
    cli.post(RUTA, _cuerpo(tecnico), format="json")

    assert cli.put(RUTA, {}, format="json").status_code == 405
    assert cli.patch(RUTA, {}, format="json").status_code == 405


def test_la_ruta_es_una_sola_y_no_es_un_crud(org_a):
    from operaciones import urls as rutas
    nombres = {p.name for p in rutas.urlpatterns}
    assert "disponibilidad" in nombres
    #  Sin rutas de detalle: no hay /disponibilidad/<id>/ que editar o borrar.
    assert not any(n and n.startswith("disponibilidad-") for n in nombres)
