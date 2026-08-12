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

import re
from dataclasses import dataclass, field


@dataclass
class Sesion:
    """Estado de verificacion de UNA conversacion (vive en memoria del canal;
    no se persiste -- ver PRD RNF-01 sobre que datos de WispHub no se guardan)."""
    identificador_canal: str          # ej. numero de whatsapp, tal cual llega
    verificado: bool = False
    nivel: int = 0
    id_cliente: str | None = None
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


def extraer_identificador(texto: str, patron_extraccion: str) -> str | None:
    """
    Saca el numero de telefono del campo crudo del canal usando el patron del
    tenant (Autenticacion.patron_extraccion). Existe porque el campo
    'telefono' de WispHub guarda mas de un numero junto en la mayoria de los
    casos -- leerlo como valor unico bajaria mucho la cobertura (ver
    docstring de 'Autenticacion' en schema.py).
    """
    m = re.search(patron_extraccion, texto or "")
    return m.group(0) if m else None


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


def verificar_por_telefono(sesion: Sesion, autenticacion_cfg,
                           buscar_clientes_por_telefono, telefono: str) -> Sesion:
    """
    Intenta subir la sesion a nivel 1 cruzando 'telefono' contra los clientes
    que devuelva 'buscar_clientes_por_telefono(telefono)'.

    'buscar_clientes_por_telefono' se inyecta a proposito (no llama a
    WispHub directo desde aca): en modo simulado es un lookup fijo; en modo
    real depende de que exista un filtro por telefono VERIFICADO contra la
    API -- no confirmado todavia (ver skill wisphub-api, metodo del valor
    imposible). Hasta sondearlo, no se asume que funciona.
    """
    candidatos = buscar_clientes_por_telefono(telefono)

    if not candidatos:
        sesion.verificado = False
        sesion.nivel = 0
        return sesion

    if len(candidatos) > 1 and autenticacion_cfg.desambiguar_si_multiple:
        # No es fallo de autenticacion: hay que preguntar cual servicio, y el
        # codigo -no el modelo- decide entre los candidatos reales.
        sesion.verificado = False
        sesion.nivel = 0
        sesion.candidatos = [c["id_cliente"] for c in candidatos]
        return sesion

    sesion.verificado = True
    sesion.nivel = 1
    sesion.id_cliente = candidatos[0]["id_cliente"]
    sesion.candidatos = []
    return sesion


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
