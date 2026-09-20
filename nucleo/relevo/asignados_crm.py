# -*- coding: utf-8 -*-
"""
================================================================================
 Quien figura atendiendo el caso en el CRM  (contrato D28)
================================================================================

Dexter decide quien atiende una conversacion. El CRM muestra un CONJUNTO de
personas asociadas al caso -- `Case.assigned_to` es ManyToMany, no un dueño
unico-- y esas dos cosas pueden divergir: el proxy sincroniza al TOMAR y nunca
mas, asi que una reasignacion deja el caso con el operador anterior, y soltar no
lo toca.

LO QUE ESTE MODULO DECIDE, Y LO QUE NO
--------------------------------------
Decide una sola cosa: si el operador que Dexter tiene a cargo esta o no en el
conjunto del CRM. Nada mas.

NO decide quien atiende --eso ya esta decidido, y el CRM no puede cambiarlo--,
y sobre todo NO decide que sobra. Los demas asignados se PRESERVAN y se
muestran como colaboradores. Podrian ser un segundo tecnico que un supervisor
sumo esta manana, y el CRM no guarda quien creo cada relacion: no hay forma de
distinguir eso de una asignacion automatica que quedo vieja. Borrar sobre una
suposicion destruye trabajo que no se recupera.

LA IDENTIDAD SE COMPARA POR ID, NUNCA POR NOMBRE
------------------------------------------------
Dexter guarda `asignada_a_usuario_id`, que es el User.id de Django. El CRM
devuelve, por cada perfil, `id` (el Profile.id, que es lo que hay que mandar
para asignar) y `user_details.id` (el User.id). Se cruza por ese User.id.

Dos personas pueden llamarse igual, y una se escribe distinto en cada sistema.
Un nombre que coincide no prueba que sea la misma persona, y actuar sobre esa
coincidencia asigna un caso a quien no es.
"""

from __future__ import annotations


def _user_id_de(perfil: dict) -> str:
    detalles = (perfil or {}).get("user_details") or {}
    return str(detalles.get("id") or "")


def perfil_de_usuario(perfiles: list[dict], usuario_id: str) -> dict | None:
    """
    El perfil del CRM que corresponde a este usuario de Dexter, o None.

    None significa "no se puede demostrar quien es en el CRM", y eso NO es un
    error a reportar ruidosamente: un operador puede no tener perfil en esa
    organizacion, y eso es una situacion real, no una falla. Lo que no se hace
    es adivinar por nombre.
    """
    if not usuario_id:
        return None
    objetivo = str(usuario_id)
    for perfil in perfiles or []:
        if _user_id_de(perfil) == objetivo:
            return perfil
    return None


def diferencia(asignados_crm: list[dict], usuario_id: str | None,
               perfiles: list[dict] | None = None) -> dict:
    """
    Como esta el caso frente a lo que Dexter sabe.

    Devuelve:
        a_cargo_en_dexter   el perfil del CRM del operador, si se pudo resolver
        falta_agregar       True si hay operador y su perfil NO esta en el caso
        colaboradores       los demas asignados. SE CONSERVAN.
        sin_perfil          True si hay operador y no se pudo resolver su perfil

    Cuando Dexter no tiene operador --la IA lleva la conversacion-- no falta
    nada que agregar: lo que haya en el CRM queda como colaboradores. Soltar no
    limpia el caso, a proposito.
    """
    asignados = list(asignados_crm or [])
    catalogo = perfiles if perfiles is not None else asignados

    if not usuario_id:
        return {"a_cargo_en_dexter": None, "falta_agregar": False,
                "colaboradores": asignados, "sin_perfil": False}

    # Se busca primero entre los asignados: si ya esta en el caso, no hace
    # falta el catalogo entero ni una llamada mas para confirmarlo.
    perfil = perfil_de_usuario(asignados, usuario_id) or \
        perfil_de_usuario(catalogo, usuario_id)
    if perfil is None:
        return {"a_cargo_en_dexter": None, "falta_agregar": False,
                "colaboradores": asignados, "sin_perfil": True}

    esta = any(_user_id_de(a) == str(usuario_id) for a in asignados)
    colaboradores = [a for a in asignados if _user_id_de(a) != str(usuario_id)]
    return {"a_cargo_en_dexter": perfil, "falta_agregar": not esta,
            "colaboradores": colaboradores, "sin_perfil": False}


def clave_de_asignacion(conversation_id: str, caso_id: str, quien: str) -> str:
    """
    La clave de idempotencia del efecto.

    Lleva A QUIEN se asigna, no solo la conversacion: reasignar a otra persona
    es otro efecto, y tiene que poder encolarse aunque el anterior ya se haya
    hecho. Sin eso, la segunda asignacion se descartaria como repetida y el CRM
    quedaria mostrando al operador anterior -- que es exactamente el defecto que
    D28 describe.

    'quien' es el identificador DURABLE de Dexter (el User.id), no el
    Profile.id del CRM. No es una preferencia: resolver el perfil exige
    preguntarle al CRM, y la clave se arma dentro de la transaccion que cambia
    la asignacion -- meter una llamada HTTP ahi es exactamente lo que X23
    prohibe. Dentro de una organizacion la correspondencia es uno a uno, asi
    que discrimina igual: dos operadores distintos dan dos claves distintas.
    """
    return f"asignar_caso:{conversation_id}:{caso_id}:{quien}"
