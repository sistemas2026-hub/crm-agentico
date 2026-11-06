# -*- coding: utf-8 -*-
"""
================================================================================
 VALIDADA LA ORDEN, EL TICKET DEL ISP SE CIERRA  --  el lado del CRM
================================================================================

Decision del usuario del 13/10/2026: lo que el tecnico registra quedaba solo en
Dexter; validada la orden, el ticket del ISP se CIERRA. La mitad del motor
(puerta humana, kill switch, una vez por orden) la prueba
tests/test_cierre_por_validacion.py. Aca, que el CRM:

  A  al APROBAR por el endpoint real pide el cierre, con el ticket de la orden,
     el nombre de quien valido y un resumen de lo hecho SIN datos personales
  B  al DEVOLVER para corregir no pide nada: lo que vuelve no esta terminado
  C  no lo pide dos veces para la misma orden
  D  sin ticket del ISP, no pide nada
  E  si el motor no cierra o no responde, la validacion queda igual y lo anota
  F  se apaga con la bandera

Solo se sustituye la llamada HTTP al motor: todo lo demas es el camino real.

    pytest campo/tests/test_cierre_ticket_al_validar.py
================================================================================
"""

from unittest import mock

import pytest

from campo.models import (AsignacionTrabajo, EventoTrabajo, OrdenTrabajo,
                          WorkType, WorkTypeVersion)
from campo.services import cierre_en_isp
from campo.services.transiciones import completar_campo

pytestmark = pytest.mark.django_db


class _Respuesta:
    def __init__(self, status=200, cuerpo=None):
        self.status_code = status
        self._cuerpo = cuerpo if cuerpo is not None else {"cerrado": True,
                                                          "referencia": "x"}
        self.content = b"{}"

    def json(self):
        return self._cuerpo


@pytest.fixture(autouse=True)
def _entorno(monkeypatch):
    monkeypatch.setattr("operaciones.areas_del_tenant.tenant_de_organizacion", lambda org_id: "tenant-de-prueba")
    monkeypatch.delenv(cierre_en_isp.BANDERA, raising=False)


@pytest.fixture
def orden(org_a, user_profile):
    wt = WorkType.objects.create(org=org_a, codigo="correctivo_fibra",
                                 nombre="Correctivo de fibra", labor="correctivo")
    version = WorkTypeVersion.objects.create(
        work_type=wt, version=1, schema_version=1,
        estado=WorkTypeVersion.PUBLICADA,
        esquema={"pasos": [], "evidencias": [
            {"id": "foto_final", "titulo": "Foto final", "tipo": "foto",
             "obligatorio": False}], "campos": [
            {"id": "que_hizo", "titulo": "Que hizo", "tipo": "texto",
             "reglas": {"required": False}},
            {"id": "potencia", "titulo": "Potencia al salir", "tipo": "decimal",
             "unidad": "dBm", "reglas": {"required": False}},
        ]})
    o = OrdenTrabajo.objects.create(
        org=org_a, numero=7001, tipo_trabajo_version=version,
        cliente_nombre="Cliente Prueba", estado_operativo=OrdenTrabajo.EN_SITIO,
        contexto={"ticket": "94721"},
        datos={"que_hizo": "cambio de conector, el cliente 3001234567 confirmo",
               "potencia": "-19.5"})
    AsignacionTrabajo.objects.create(orden=o, profile=user_profile,
                                     rol="tecnico", es_principal=True)
    completar_campo(o, profile=user_profile)
    o.refresh_from_db()
    return o


def _validar(cliente, orden, decision="aprobar"):
    cuerpo = {"decision": decision, "observacion": ""}
    if decision != "aprobar":
        cuerpo["requisitos_a_corregir"] = ["foto_final"]
    return cliente.post(f"/api/campo/trabajos/{orden.id}/validar/", cuerpo,
                        format="json")


def test_a_aprobar_pide_el_cierre_con_ticket_quien_y_resumen_tapado(
        admin_client, orden, admin_user):
    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        r = _validar(admin_client, orden)
    assert r.status_code == 200, r.content
    assert r.json()["ticket_isp"]["estado"] == "cerrado"

    post.assert_called_once()
    url = post.call_args.args[0]
    cuerpo = post.call_args.kwargs["json"]
    assert url.endswith(f"/interno/orden/{orden.id}/cerrar-ticket")
    assert cuerpo["ticket"] == "94721"
    assert cuerpo["actor"]                                   # quien valido
    assert set(cuerpo) == {"ticket", "texto", "actor"}       # ni un campo mas
    #  El ticket del cliente NUNCA recibe el correo del colaborador.
    assert admin_user.email not in str(cuerpo)
    assert "@" not in cuerpo["actor"]
    texto = cuerpo["texto"]
    #  DESDE EL 06/11/2026 EL CIERRE ESCRIBE CORTO, no el reporte entero.
    #
    #  Antes esta prueba exigia «OT #7001», la potencia y el texto libre del
    #  tecnico, porque el cierre era la UNICA escritura que llegaba al ticket.
    #  Ahora el tecnico manda su reporte al completar
    #  (`nota_al_isp.anotar_reporte_del_tecnico`), asi que repetirlo dejaba el
    #  mismo texto dos veces en el mismo ticket.
    #
    #  «SE VALIDA TICKET» es la frase que el supervisor escribe hoy a mano --
    #  el usuario mostro un ticket real. La linea de revision es lo unico que
    #  un cierre automatico agrega sobre uno humano: que se miro.
    assert texto.startswith("SE VALIDA TICKET"), texto
    assert "Revision:" in texto and "checklist" in texto
    #  Y lo que NO puede volver: el reporte duplicado.
    assert "Potencia al salir" not in texto, texto
    assert "cambio de conector" not in texto, texto
    #  El telefono que el tecnico escribio en el texto libre nunca llega al
    #  ticket -- ahora porque ese texto no viaja, antes porque iba tapado. Se
    #  afirma igual: el dia que el cierre vuelva a llevar texto del tecnico,
    #  esto tiene que seguir siendo cierto.
    assert "3001234567" not in texto
    assert EventoTrabajo.objects.filter(
        orden=orden, tipo=cierre_en_isp.EVENTO_CERRADO).count() == 1


def test_b_devolver_para_corregir_anota_pero_no_cierra(admin_client, orden):
    """La devolucion SI le escribe al ISP desde el 06/11/2026 -- pero no cierra.

    Antes esta prueba se llamaba `..._no_pide_nada` y afirmaba
    `post.assert_not_called()`. Era cierto y era el defecto: el usuario pidio
    que el ticket del ISP se entere cuando el trabajo vuelve a campo, porque
    hasta entonces quedaba igual que antes de la devolucion y nadie sabia por
    que. Ver `campo/services/nota_al_isp.py`.

    Lo que esta prueba sigue cuidando es la parte que NO cambio: que la
    devolucion no pida un CIERRE. Una nota y un cierre salen por exenciones
    distintas, con niveles distintos, y confundirlos cerraria el ticket de un
    trabajo que todavia hay que rehacer.
    """
    with mock.patch("requests.post", return_value=_Respuesta(
            200, {"anotada": True, "codigo": "anotada"})) as post:
        r = _validar(admin_client, orden, decision="requerir_correccion")
    #  200: la devolucion SI ocurrio. Sin esto un 400 haria pasar la prueba
    #  sin haber probado nada.
    assert r.status_code == 200, r.content

    post.assert_called_once()
    url = post.call_args.args[0]
    cuerpo = post.call_args.kwargs["json"]
    #  LA RUTA ES LA DE ANOTAR, NUNCA LA DE CERRAR.
    assert url.endswith(f"/interno/orden/{orden.id}/anotar-en-el-ticket")
    assert "cerrar" not in url
    assert cuerpo["momento"] == "devuelta_al_tecnico"
    assert cuerpo["ticket"] == "94721"
    #  La vuelta entra en la clave idempotente: sin ella, el segundo reporte
    #  del tecnico se descartaria como si fuera un reintento.
    assert isinstance(cuerpo["vuelta"], int)
    #  Y el ticket del cliente nunca recibe el correo de nadie.
    assert "@" not in str(cuerpo)


def test_formato_como_lo_escribe_un_tecnico_a_mano(orden):
    """El texto tiene la forma del ticket real, no una propia.

    EL FORMATO LO FIJO EL USUARIO MOSTRANDO UN TICKET  --  06/11/2026
    -----------------------------------------------------------------
    Hasta ese dia esto escribia «- Titulo: valor» con guiones. Se parecia al
    formato que usan y no era el mismo, y lo lee gente que ya tiene el ojo
    hecho al de abajo:

        Observaciones: se realiza instalacion...
        Niveles de potencia: -21-26 dbm
        MATERIAL Y CANTIDAD
        ONU CATV
        1

    Esta guarda afirma la FORMA, que es lo que se rompe sin que nadie lo note:
    alguien vuelve a poner un guion, o cambia el orden, y el ticket sigue
    saliendo -- solo que ilegible para quien lo lee todos los dias.
    """
    texto = cierre_en_isp.resumen_de(orden, "", encabezado="Reporte de campo")

    assert texto.startswith("Reporte de campo")
    #  «Titulo: valor», SIN guion delante. Es la diferencia que motivo el
    #  cambio, asi que se afirma en los dos sentidos.
    assert "Potencia al salir: -19.5 dBm" in texto
    assert "- Potencia al salir" not in texto
    assert "Que hizo: cambio de conector" in texto
    #  Y lo que nunca puede aparecer: el telefono que el tecnico escribio
    #  dentro del texto libre.
    assert "3001234567" not in texto


def test_el_cierre_no_repite_el_reporte_que_ya_escribio_el_tecnico(
        orden, admin_profile):
    """Con revision, el cierre escribe corto; sin ella, el reporte completo.

    Antes el cierre mandaba `resumen_de` entero porque era la UNICA escritura
    que llegaba al ticket. Desde que el tecnico manda su reporte al completar,
    repetirlo deja el mismo texto dos veces en el mismo ticket.

    El caso SIN revision sigue escribiendo el reporte a proposito: una orden
    que se cierre por un camino que no calcula revision no puede quedarse sin
    dejar nada.
    """
    from campo.services.nota_al_isp import texto_de_la_revision

    revision = {"veredicto": "cerrar", "puntos": [
        {"clave": "checklist", "ok": True},
        {"clave": "reporte", "ok": True},
        {"clave": "fotos", "ok": None},
    ]}
    corto = texto_de_la_revision(revision)
    #  La frase que su equipo ya reconoce, no una inventada.
    assert corto.startswith("SE VALIDA TICKET")
    assert "checklist ok" in corto and "fotos sin datos" in corto

    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        cierre_en_isp.cerrar_ticket_al_validar(orden, admin_profile,
                                               extra=corto)
    enviado = post.call_args.kwargs["json"]["texto"]
    assert "SE VALIDA TICKET" in enviado
    #  LA MITAD QUE IMPORTA: no repite lo que el tecnico ya escribio.
    assert "Potencia al salir" not in enviado, enviado
    assert "cambio de conector" not in enviado, enviado


def test_sin_revision_el_cierre_sigue_dejando_el_reporte(orden, admin_profile):
    """Sin `extra`, la conducta de antes: mejor el reporte que nada."""
    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        cierre_en_isp.cerrar_ticket_al_validar(orden, admin_profile)
    enviado = post.call_args.kwargs["json"]["texto"]
    assert "Potencia al salir: -19.5 dBm" in enviado
    assert "SE VALIDA TICKET" not in enviado


def test_c_no_lo_pide_dos_veces_para_la_misma_orden(orden, admin_profile):
    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        primera = cierre_en_isp.cerrar_ticket_al_validar(orden, admin_profile)
        segunda = cierre_en_isp.cerrar_ticket_al_validar(orden, admin_profile)
    assert primera["estado"] == "cerrado"
    assert segunda["estado"] == "ya_cerrado"
    assert post.call_count == 1


def test_d_sin_ticket_del_isp_no_pide_nada(orden, admin_profile):
    orden.contexto = {}
    orden.save(update_fields=["contexto"])
    with mock.patch("requests.post") as post:
        r = cierre_en_isp.cerrar_ticket_al_validar(orden, admin_profile)
    assert r["estado"] == "sin_ticket"
    post.assert_not_called()


@pytest.mark.parametrize("efecto", [
    _Respuesta(409, {"cerrado": False, "codigo": "BLOQUEADO_POR_INTERRUPTOR"}),
    _Respuesta(502, {"cerrado": False, "codigo": "FALLO_AL_CERRAR"}),
    ConnectionError("motor caido"),
])
def test_e_si_el_motor_no_cierra_la_validacion_queda_y_se_anota(
        admin_client, orden, efecto):
    kw = {"side_effect": efecto} if isinstance(efecto, Exception) else {"return_value": efecto}
    with mock.patch("requests.post", **kw):
        r = _validar(admin_client, orden)
    assert r.status_code == 200, r.content
    assert r.json()["ticket_isp"]["estado"] == "no_cerrado"
    orden.refresh_from_db()
    assert orden.estado_validacion == OrdenTrabajo.APROBADO
    assert EventoTrabajo.objects.filter(
        orden=orden, tipo=cierre_en_isp.EVENTO_NO_CERRADO).exists()
    assert not EventoTrabajo.objects.filter(
        orden=orden, tipo=cierre_en_isp.EVENTO_CERRADO).exists()


def test_g_sin_nombre_firma_la_oficina_y_no_el_correo(orden, admin_profile):
    admin_profile.user.name = ""
    admin_profile.user.save(update_fields=["name"])
    with mock.patch("requests.post", return_value=_Respuesta()) as post:
        cierre_en_isp.cerrar_ticket_al_validar(orden, admin_profile)
    cuerpo = post.call_args.kwargs["json"]
    assert cuerpo["actor"] == "Oficina de operaciones"
    assert admin_profile.user.email not in str(cuerpo)


def test_f_se_apaga_con_la_bandera(orden, admin_profile, monkeypatch):
    monkeypatch.setenv(cierre_en_isp.BANDERA, "0")
    with mock.patch("requests.post") as post:
        r = cierre_en_isp.cerrar_ticket_al_validar(orden, admin_profile)
    assert r["estado"] == "apagado"
    post.assert_not_called()
