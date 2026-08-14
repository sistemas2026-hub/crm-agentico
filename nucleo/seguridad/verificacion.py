# -*- coding: utf-8 -*-
"""
================================================================================
 VERIFICACION DE IDENTIDAD  -  para roles que hablan con un desconocido
================================================================================

Por que existe
--------------
'identificar_area()' (soporte_wisphub.py) confia en quien abre la consola:
sirve para un colaborador interno, nunca para un canal como WhatsApp, donde
quien escribe es un desconocido hasta que se demuestre lo contrario. Ese es
el rol de este modulo: no existia ningun codigo que lo hiciera, solo el
contrato declarado en 'Autenticacion'/'Seguridad.requiere_verificacion'
(nucleo/config/schema.py) sin nada que lo ejecutara.

El numero del canal sirve como factor de POSESION (ver el docstring de
'Autenticacion' en schema.py: 98.7% de cobertura medida sobre la base de
Rapilink). La cedula identifica pero NO autentica -- es publica.

Simplificacion deliberada de esta primera version
---------------------------------------------------
El schema declara 'requiere_verificacion' por RECURSO ("saldo", "factura",
...), pero no existe todavia un mapeo de que herramienta toca que recurso.
Mientras ese mapeo no exista, esta version exige el NIVEL MAXIMO declarado en
'requiere_verificacion' para CUALQUIER herramienta del rol -- sobre-exige en
vez de arriesgar sub-exigir. Cuando haya mas de una herramienta con
sensibilidad distinta, hay que reemplazar esto por un mapeo explicito
herramienta->recurso en la config.
================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Sesion:
    """Estado de verificacion de UNA conversacion (vive en memoria del canal;
    no se persiste -- ver PRD RNF-01 sobre que datos de WispHub no se guardan)."""
    identificador_canal: str          # ej. numero de whatsapp, tal cual llega
    verificado: bool = False
    nivel: int = 0
    id_cliente: str | None = None
    # El nombre que confirmo el cliente en _ejecutar_confirmacion. A
    # diferencia de 'nombre_pendiente' (que se limpia al cerrar el segundo
    # paso), este sobrevive: es lo que nucleo/canales/api.py persiste en
    # asistente.conversations para que /conversaciones muestre un nombre en
    # vez del identificador crudo del canal.
    nombre: str | None = None
    # Capturada al verificar (nunca la propone el modelo): la necesita
    # ping_cliente para el parametro 'interfaz' de WispHub. Puede quedar
    # vacia -- normal en clientes nuevos, ver nucleo/herramientas/http.py.
    interfaz_lan: str | None = None
    candidatos: list[str] = field(default_factory=list)  # si el numero es ambiguo

    # Verificacion en DOS pasos: encontrar un cliente por cedula no alcanza
    # para marcar 'verificado' -- primero hay que confirmar con la persona
    # que el nombre que figura es el suyo (nucleo/modelo/motor.py:
    # _ejecutar_confirmacion, la unica funcion que lee estos 'pendiente' y
    # los promueve a los de arriba). Mientras esten seteados, la sesion
    # sigue sin verificar y ninguna otra herramienta se desbloquea.
    id_cliente_pendiente: str | None = None
    nombre_pendiente: str | None = None
    interfaz_lan_pendiente: str | None = None

    # Rol al que se derivo la conversacion en ESTE turno (ver
    # nucleo/modelo/motor.py::_ejecutar_derivacion). None la mayoria de las
    # veces -- solo se pone cuando el modelo llamo una herramienta
    # 'deriva_rol' este turno. Quien llama a motor.responder() (hoy,
    # nucleo/canales/api.py::atender_turno) lo lee DESPUES de la llamada
    # para persistir 'rol_efectivo' con el nuevo rol, y lo mantiene vivo
    # para los turnos siguientes de esta misma sesion en memoria.
    rol_siguiente: str | None = None


def nivel_requerido(rol_cfg, seguridad_cfg) -> int:
    """
    Nivel de verificacion que exige este rol antes de ejecutar CUALQUIERA de
    sus herramientas.

    Ver la nota de simplificacion arriba: no hay mapeo herramienta->recurso
    todavia, asi que se aproxima cruzando los NOMBRES de
    'seguridad.requiere_verificacion' contra los campos que el rol realmente
    expone en 'campos_permitidos'. Tomar el maximo GLOBAL del tenant estaria
    mal: incluiria recursos de otros roles (ej. 'registrar_pago' es de
    Facturacion, no de un rol de autoservicio) y exigiria un nivel que este
    rol no tiene forma de alcanzar.
    """
    if not rol_cfg.puede_consultar:
        return 0
    campos_del_rol = {c for lista in rol_cfg.campos_permitidos.values() for c in lista}
    niveles = [n for recurso, n in seguridad_cfg.requiere_verificacion.items()
              if recurso in campos_del_rol]
    return max(niveles, default=0)


def es_factor_de_posesion(identificador: str) -> bool:
    """
    El numero de telefono sirve como factor de POSESION (98.7% de cobertura
    medida sobre la base de Rapilink, ver el docstring de arriba) porque casi
    nadie mas tiene ese aparato. Un identificador que NO es un telefono --
    como el BSUID que manda WhatsApp cuando el cliente oculto su numero
    detras de un username de la plataforma -- no tiene esa propiedad:
    cualquiera que escriba desde esa cuenta pasaria la barra igual.

    Por eso NO cuenta como verificacion por si sola: nucleo/modelo/motor.py
    exige nivel 1 ANTES de cualquier herramienta cuando esto da False, aunque
    ninguno de los recursos que toque ese turno este marcado como sensible en
    'seguridad.requiere_verificacion'. Mismo heuristico que
    nucleo/canales/whatsapp.py::_destinatario() para distinguir un telefono
    real de un BSUID.
    """
    return bool(identificador) and identificador.isdigit()


def resolver_candidato(sesion: Sesion, id_cliente_elegido: str) -> Sesion:
    """Cuando hubo ambiguedad, el cliente confirma cual de los candidatos es
    -- nunca el modelo eligiendo por su cuenta."""
    if id_cliente_elegido not in sesion.candidatos:
        return sesion
    sesion.verificado = True
    sesion.nivel = 1
    sesion.id_cliente = id_cliente_elegido
    sesion.candidatos = []
    return sesion
