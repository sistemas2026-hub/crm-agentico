# -*- coding: utf-8 -*-
"""
===============================================================================
 AJUSTES DEL SUPERVISOR: EL CLIC CAMBIA LO QUE EL SUPERVISOR HACE
===============================================================================

POR QUE EXISTE ESTA PRUEBA  --  27/10/2026
------------------------------------------
«Ajustes del Supervisor» deja delegar o quitar cada tarea del catalogo desde
una pantalla, sin hablarle al chat. Lo que importa no es que la pantalla
exista sino el EFECTO del clic, medido donde lo lee el Supervisor:

    td.esta_delegada            lo que pregunta el ciclo antes de actuar
    chat_herramientas.tareas_activas
                                lo que ve el modelo del chat cuando le
                                preguntan que esta haciendo

Y que el clic deja escrito quien y por que, que es lo unico que contesta,
meses despues, por que el Supervisor hizo (o dejo de hacer) algo.

NO SE AFIRMA sobre textos: el catalogo es redaccion. Se afirman estados, el
actor y el motivo guardados, y los codigos de respuesta.
"""
import json

import pytest
from rest_framework.test import APIClient

from common.models import Org, Profile, User
from common.serializer import OrgAwareRefreshToken
from operaciones import autonomia, chat_herramientas, tareas_delegadas as td
from operaciones.tareas_modelos import TareaDelegada

URL = "/api/operaciones/supervisor/ajustes/"


def _persona(org, correo, nombre, rol):
    usuario = User.objects.create_user(email=correo, password="x12345678",
                                       name=nombre)
    perfil = Profile.objects.create(org=org, user=usuario, role=rol,
                                    is_active=True)
    return usuario, perfil


@pytest.fixture
def empresa(db, monkeypatch):
    #  El interruptor se le pregunta al MOTOR por HTTP y aca no hay motor.
    monkeypatch.setattr(autonomia, "_interruptor_de", lambda org: (True, ""))
    org = Org.objects.create(name="Org con ajustes")
    usuario, perfil = _persona(org, "jefa@ajustes.test", "Jefa Ajustes", "ADMIN")
    return org, usuario, perfil


def _cli(org, usuario, perfil):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=(
        "Bearer " + str(OrgAwareRefreshToken.for_user_and_org(
            usuario, org, perfil).access_token)))
    return c


def _post(cli, clave, delegar, motivo="porque se midio"):
    return cli.post(URL, {"clave": clave, "delegar": delegar, "motivo": motivo},
                    format="json")


def _el_chat_la_ve(org, clave) -> bool:
    return clave in {d["clave"] for d in
                     chat_herramientas.tareas_activas(org)["delegadas"]}


def _fila(cli, clave):
    """La fila de esa tarea en la lista que pinta la pantalla (un GET aparte:
    el POST devuelve solo el resultado)."""
    r = cli.get(URL)
    assert r.status_code == 200, r.content
    return {t["clave"]: t for t in r.json()["tareas"]}[clave]


@pytest.mark.django_db
def test_delegar_con_un_clic_la_deja_delegada_para_el_supervisor(empresa):
    org, usuario, perfil = empresa
    assert not td.esta_delegada(org, td.ARMAR_LA_JORNADA)

    cli = _cli(org, usuario, perfil)
    r = _post(cli, td.ARMAR_LA_JORNADA, True, "ya la miramos una semana en sombra")
    assert r.status_code == 200, r.content
    assert r.json() == {"clave": td.ARMAR_LA_JORNADA, "delegada": True}

    #  EL EFECTO, donde lo lee el Supervisor: el ciclo y el chat.
    assert td.esta_delegada(org, td.ARMAR_LA_JORNADA)
    assert _el_chat_la_ve(org, td.ARMAR_LA_JORNADA)
    #  Y quien y por que, guardados.
    f = TareaDelegada.objects.get(org=org, clave=td.ARMAR_LA_JORNADA)
    assert f.delegada_por_id == perfil.id
    assert f.pedido_textual == "ya la miramos una semana en sombra"
    #  La pantalla que vuelve la muestra encendida y con nombre.
    fila = _fila(cli, td.ARMAR_LA_JORNADA)
    assert fila["delegada"] is True
    assert fila["delegada_por"] == "Jefa Ajustes"
    assert fila["con_estas_palabras"] == "ya la miramos una semana en sombra"


@pytest.mark.django_db
def test_quitar_con_un_clic_la_apaga_y_deja_quien_y_por_que(empresa):
    org, usuario, perfil = empresa
    td.delegar(org, td.CREAR_LAS_ORDENES, actor=perfil, pedido_textual="dale")
    assert td.esta_delegada(org, td.CREAR_LAS_ORDENES)

    otra_u, otra = _persona(org, "ops@ajustes.test", "Otra Persona", "OPERACIONES")
    cli = _cli(org, otra_u, otra)
    r = _post(cli, td.CREAR_LAS_ORDENES, False,
              "crea ordenes de casos que ya se resolvieron")
    assert r.status_code == 200, r.content

    assert not td.esta_delegada(org, td.CREAR_LAS_ORDENES)
    assert not _el_chat_la_ve(org, td.CREAR_LAS_ORDENES)
    f = TareaDelegada.objects.get(org=org, clave=td.CREAR_LAS_ORDENES)
    assert f.quitada_por_id == otra.id
    assert f.motivo_al_quitar == "crea ordenes de casos que ya se resolvieron"
    fila = _fila(cli, td.CREAR_LAS_ORDENES)
    assert fila["delegada"] is False
    assert fila["quitada_por"] == "Otra Persona"
    assert fila["motivo_al_quitar"] == "crea ordenes de casos que ya se resolvieron"

    #  Encendida de nuevo, el motivo de cuando se apagó ya no describe nada.
    r = _post(_cli(org, usuario, perfil), td.CREAR_LAS_ORDENES, True, "ya se arreglo")
    assert r.status_code == 200, r.content
    fila = _fila(cli, td.CREAR_LAS_ORDENES)
    assert fila["quitada_por"] == "" and fila["motivo_al_quitar"] == ""
    assert fila["delegada_por"] == "Jefa Ajustes"


@pytest.mark.django_db
def test_sin_motivo_no_cambia_nada(empresa):
    org, usuario, perfil = empresa
    cli = _cli(org, usuario, perfil)

    r = _post(cli, td.ARMAR_LA_JORNADA, True, "   ")
    assert r.status_code == 400
    assert not td.esta_delegada(org, td.ARMAR_LA_JORNADA)

    td.delegar(org, td.CREAR_LAS_ORDENES, actor=perfil, pedido_textual="dale")
    r = _post(cli, td.CREAR_LAS_ORDENES, False, "")
    assert r.status_code == 400
    assert td.esta_delegada(org, td.CREAR_LAS_ORDENES)


@pytest.mark.django_db
def test_la_cadena_false_no_enciende_una_tarea(empresa):
    org, usuario, perfil = empresa
    r = _post(_cli(org, usuario, perfil), td.ARMAR_LA_JORNADA, "false")
    assert r.status_code == 400
    assert not TareaDelegada.objects.filter(org=org).exists()


@pytest.mark.django_db
def test_una_clave_fuera_del_catalogo_no_crea_nada(empresa):
    org, usuario, perfil = empresa
    r = _post(_cli(org, usuario, perfil), "borrar_todo", True)
    assert r.status_code == 400
    assert not TareaDelegada.objects.filter(org=org).exists()


@pytest.mark.django_db
def test_una_pantalla_vieja_no_pisa_quien_la_delego(empresa):
    org, usuario, perfil = empresa
    td.delegar(org, td.ARMAR_LA_JORNADA, actor=perfil, pedido_textual="primera")

    otra_u, otra = _persona(org, "ops2@ajustes.test", "Otra", "OPERACIONES")
    r = _post(_cli(org, otra_u, otra), td.ARMAR_LA_JORNADA, True, "segunda")
    assert r.status_code == 409
    f = TareaDelegada.objects.get(org=org, clave=td.ARMAR_LA_JORNADA)
    assert f.delegada_por_id == perfil.id
    assert f.pedido_textual == "primera"

    #  Y al reves: quitar una que ya estaba quitada no cambia quien la quito.
    td.quitar(org, td.ARMAR_LA_JORNADA, actor=perfil, motivo="la primera vez")
    r = _post(_cli(org, otra_u, otra), td.ARMAR_LA_JORNADA, False, "otra vez")
    assert r.status_code == 409
    f.refresh_from_db()
    assert f.quitada_por_id == perfil.id
    assert f.motivo_al_quitar == "la primera vez"


@pytest.mark.django_db
def test_quien_no_gestiona_no_ve_ni_cambia(empresa):
    org, _, _ = empresa
    u, p = _persona(org, "tec@ajustes.test", "Tecnico", "USER")
    cli = _cli(org, u, p)

    assert cli.get(URL).status_code == 403
    r = _post(cli, td.ARMAR_LA_JORNADA, True)
    assert r.status_code == 403
    assert not td.esta_delegada(org, td.ARMAR_LA_JORNADA)


@pytest.mark.django_db
def test_delegar_en_una_empresa_no_toca_la_otra(empresa):
    org, usuario, perfil = empresa
    otra_org = Org.objects.create(name="Otra empresa")

    r = _post(_cli(org, usuario, perfil), td.ARMAR_LA_JORNADA, True)
    assert r.status_code == 200
    assert td.esta_delegada(org, td.ARMAR_LA_JORNADA)
    assert not td.esta_delegada(otra_org, td.ARMAR_LA_JORNADA)


@pytest.mark.django_db
def test_la_lista_trae_el_catalogo_entero_y_lo_que_falta(empresa):
    org, usuario, perfil = empresa
    cli = _cli(org, usuario, perfil)

    r = cli.get(URL)
    assert r.status_code == 200, r.content
    tareas = {t["clave"]: t for t in r.json()["tareas"]}
    assert set(tareas) == set(td.CATALOGO)

    #  Las correcciones se apoyan en el paso: la pantalla lo dice ANTES del
    #  clic, y cambia cuando el paso se delega.
    req = tareas[td.PASAR_CON_LAS_CORRECCIONES]["requiere"]
    assert [x["clave"] for x in req] == [td.PASAR_A_DESPACHO]
    assert req[0]["delegada"] is False

    _post(cli, td.PASAR_A_DESPACHO, True)
    req = _fila(cli, td.PASAR_CON_LAS_CORRECCIONES)["requiere"]
    assert req[0]["delegada"] is True

    #  Delegar el ciclo desde la pantalla es lo que hace que el resto corra
    #  solo: la misma lectura que usa el chat para avisarlo.
    assert not td.algo_la_va_a_correr(org, td.ARMAR_LA_JORNADA)["si"]
    _post(cli, td.CICLO_AUTOMATICO, True)
    assert td.algo_la_va_a_correr(org, td.ARMAR_LA_JORNADA)["si"]
    fila = _fila(cli, td.ARMAR_LA_JORNADA)
    assert fila["la_despierta_algo"]["si"] is True


@pytest.mark.django_db
def test_la_respuesta_no_lleva_correos(empresa):
    org, usuario, perfil = empresa
    cli = _cli(org, usuario, perfil)
    _post(cli, td.ARMAR_LA_JORNADA, True)
    _post(cli, td.ARMAR_LA_JORNADA, False)
    crudo = json.dumps(cli.get(URL).json())
    assert "@" not in crudo


@pytest.mark.django_db
def test_quitar_por_el_chat_no_deja_a_la_vista_el_motivo_viejo(empresa):
    org, usuario, perfil = empresa
    td.delegar(org, td.ARMAR_LA_JORNADA, actor=perfil)
    td.quitar(org, td.ARMAR_LA_JORNADA, actor=perfil, motivo="motivo viejo")
    td.delegar(org, td.ARMAR_LA_JORNADA, actor=perfil)

    chat_herramientas.quitar_tarea(org, clave=td.ARMAR_LA_JORNADA, actor=perfil)
    f = TareaDelegada.objects.get(org=org, clave=td.ARMAR_LA_JORNADA)
    assert not f.activa
    assert f.motivo_al_quitar == ""


@pytest.mark.django_db
def test_un_motivo_demasiado_largo_se_rechaza_y_no_se_corta_en_silencio(empresa):
    org, usuario, perfil = empresa
    r = _post(_cli(org, usuario, perfil), td.ARMAR_LA_JORNADA, True, "x" * 501)
    assert r.status_code == 400
    assert not TareaDelegada.objects.filter(org=org).exists()


@pytest.mark.django_db
def test_quitar_una_que_nunca_se_delego_dice_que_ya_estaba_asi(empresa):
    org, usuario, perfil = empresa
    r = _post(_cli(org, usuario, perfil), td.ARMAR_LA_JORNADA, False)
    assert r.status_code == 409
    assert not TareaDelegada.objects.filter(org=org).exists()


@pytest.mark.django_db
def test_el_chat_no_borra_quien_la_quito_si_ya_estaba_quitada(empresa):
    """Auditor independiente, 27/10/2026: el chat re-sellaba una ya quitada y
    borraba quién y por qué, sin cambiar nada."""
    org, usuario, perfil = empresa
    td.delegar(org, td.CREAR_LAS_ORDENES, actor=perfil)
    otra_u, otra = _persona(org, "ops4@ajustes.test", "Otra", "OPERACIONES")
    assert _post(_cli(org, otra_u, otra), td.CREAR_LAS_ORDENES, False,
                 "crea ordenes duplicadas").status_code == 200

    r = chat_herramientas.quitar_tarea(org, clave=td.CREAR_LAS_ORDENES, actor=perfil)
    assert r.get("error") == "no_se_pudo_quitar"
    f = TareaDelegada.objects.get(org=org, clave=td.CREAR_LAS_ORDENES)
    assert f.quitada_por_id == otra.id
    assert f.motivo_al_quitar == "crea ordenes duplicadas"


@pytest.mark.django_db
def test_volver_a_delegar_desde_ajustes_no_deja_la_conversacion_de_otro(empresa):
    """Auditor independiente, 27/10/2026: los avisos iban al chat de quien la
    delegó ANTES. La de la misma persona sí se conserva."""
    import uuid

    org, usuario, perfil = empresa
    conversacion = uuid.uuid4()
    td.delegar(org, td.CERRAR_DESINCRONIZADOS, actor=perfil,
               conversacion_id=conversacion)
    td.quitar(org, td.CERRAR_DESINCRONIZADOS, actor=perfil)

    #  La MISMA persona la vuelve a delegar desde la pantalla: su chat sigue.
    assert _post(_cli(org, usuario, perfil), td.CERRAR_DESINCRONIZADOS, True,
                 "otra vez").status_code == 200
    f = TareaDelegada.objects.get(org=org, clave=td.CERRAR_DESINCRONIZADOS)
    assert f.conversacion_id == conversacion

    #  OTRA persona: el chat de la primera ya no es donde avisar.
    td.quitar(org, td.CERRAR_DESINCRONIZADOS, actor=perfil)
    otra_u, otra = _persona(org, "ops5@ajustes.test", "Otra", "OPERACIONES")
    assert _post(_cli(org, otra_u, otra), td.CERRAR_DESINCRONIZADOS, True,
                 "la retomo yo").status_code == 200
    f.refresh_from_db()
    assert f.delegada_por_id == otra.id
    assert f.conversacion_id is None


@pytest.mark.django_db(transaction=True)
def test_dos_personas_que_delegan_a_la_vez_la_primera_vez_no_se_pisan(empresa):
    """
    Dos transacciones de verdad. La primera delega y tarda en confirmar; la
    segunda llega por la pantalla mientras tanto. Sin el bloqueo de la tarea,
    la segunda no ve fila (todavía no hay nada confirmado), y al confirmarse la
    primera la reactiva a su nombre con 200: el registro de la primera
    desaparece (auditor independiente, 27/10/2026). Con el bloqueo espera, ve
    la fila, y contesta 409.
    """
    import threading
    import time

    from django.db import connection, transaction

    org, usuario, perfil = empresa
    otra_u, otra = _persona(org, "ops6@ajustes.test", "Otra", "OPERACIONES")
    listo = threading.Event()
    errores = []

    def primera():
        try:
            with transaction.atomic():
                td.delegar(org, td.ARMAR_LA_JORNADA, actor=perfil,
                           pedido_textual="primera")
                listo.set()
                time.sleep(1.5)
        except Exception as e:                                   # noqa: BLE001
            errores.append(e)
            listo.set()
        finally:
            connection.close()

    hilo = threading.Thread(target=primera)
    hilo.start()
    assert listo.wait(10)
    r = _post(_cli(org, otra_u, otra), td.ARMAR_LA_JORNADA, True, "segunda")
    hilo.join(10)

    assert not errores, errores
    assert r.status_code == 409, r.content
    f = TareaDelegada.objects.get(org=org, clave=td.ARMAR_LA_JORNADA)
    assert f.delegada_por_id == perfil.id
    assert f.pedido_textual == "primera"
