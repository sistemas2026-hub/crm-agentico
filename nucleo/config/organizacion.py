# -*- coding: utf-8 -*-
"""
================================================================================
 LA ORGANIZACION QUE SIRVE EL MOTOR, Y DE DONDE SALE
================================================================================

Una empresa declara su organizacion en 'TenantConfig.organizacion'. Cuando no
la declara, el motor sirve la ESTRUCTURA POR DEFECTO DEL PRODUCTO -- y lo dice,
en el mismo documento, con 'origen'.

POR QUE HAY UN DEFECTO, Y POR QUE NO ES EL ERROR QUE VENIMOS DE CORREGIR
-------------------------------------------------------------------------
El error medido el 30/10/2026 fue DEDUCIR la organizacion de los agentes: la
pantalla agrupaba el campo 'area' de los roles y presentaba el resultado como
el organigrama. Eso inventaba empleados y borraba los departamentos que no
tienen ninguno.

Esto es otra cosa. Es una estructura explicita, generica para cualquier ISP,
que se sirve ETIQUETADA como no declarada. La diferencia operativa es que la
pantalla puede decirlo, y la empresa puede reemplazarla entera sin tocar
codigo. Un defecto silencioso si seria el mismo error por la puerta de atras:
nadie podria distinguir "la empresa decidio esto" de "nadie lo decidio".

NADA DE AQUI NOMBRA A UNA EMPRESA
---------------------------------
Son los departamentos de un proveedor de internet cualquiera, no los de un
cliente concreto: 'nucleo/' es el motor y no conoce clientes (CLAUDE.md 3.1).
La guarda 'tests/test_nucleo_sin_tenants.py' lo vigila.

Y la cantidad no es un limite. Tres pisos y ocho departamentos es lo que trae
una empresa que no eligio nada; un ISP de cuatro departamentos en una planta y
uno de quince en cinco niveles se expresan con el mismo modelo.

QUE NO DECIDE ESTE ARCHIVO
--------------------------
Como se ve una sala. 'plantilla' nombra una sala de un catalogo generico que
conoce la PANTALLA -- cuanto mide, donde van los muebles, donde los
escritorios. Mismo reparto que 'AreaDeTrabajo.icono'. El motor no tiene ese
catalogo y por eso no valida que el nombre exista: lo que si valida es todo lo
que, mal escrito, haria que la pantalla afirmara algo falso.
"""
from __future__ import annotations

from nucleo.config.schema import (Departamento, EspacioDeTrabajo, Ocupacion,
                                  Organizacion, Piso, TenantConfig)

#  Los acentos NO se eligieron a ojo. La escena los usa para teñir la sala
#  entera, y un acento rojizo haria que una sala tranquila se leyera como una
#  sala en alarma. Los once estan a mas de 160 de distancia (suma de los tres
#  canales) del rojo de alarma y a mas de 70 entre si; el par mas cercano es
#  77. La pantalla tiene la guarda que lo mide.
ORGANIZACION_POR_DEFECTO = Organizacion(
    pisos=[
        Piso(nivel=3, rotulo="Tecnología y dirección"),
        Piso(nivel=2, rotulo="Operación y clientes"),
        Piso(nivel=1, rotulo="Administración"),
    ],
    departamentos=[
        Departamento(
            id="operativo",
            rotulo="NOC y Redes",
            direccion="Dirección de Operaciones",
            piso=3,
            plantilla="operaciones",
            #  Las TRES escrituras hacen falta y no es redundancia: hay dos
            #  vocabularios de area que no coinciden. La configuracion declara
            #  'operativo' y el rol que de verdad existe escribe
            #  'Operaciones'. Con solo el identificador, esta sala salia vacia
            #  en produccion -- medido el 30/10/2026 contra el YAML del
            #  tenant, no deducido.
            areas=["operativo", "Operaciones", "NOC y Redes"],
            ocupaciones=[Ocupacion(puesto="principal", agente="supervisor_noc")],
            acento="#4f46e5",
        ),
        Departamento(
            id="campo",
            rotulo="Operaciones de Campo",
            direccion="Dirección de Operaciones",
            piso=2,
            plantilla="tecnica",
            areas=["campo", "Operaciones de Campo", "Campo"],
            #  SIN NINGUNA OCUPACION, y es el caso que mas importa de los
            #  ocho: un departamento existe porque la empresa lo tiene, no
            #  porque haya un agente que lo represente. Deducido de los
            #  agentes, este departamento no existiria.
            ocupaciones=[],
            acento="#4d9e2a",
        ),
        Departamento(
            id="atencion_cliente",
            rotulo="Atención al Cliente",
            direccion="Dirección de Servicio",
            piso=2,
            plantilla="atencion",
            #  DOS ETIQUETAS DE ROL, UN DEPARTAMENTO. 'Soporte Técnico' y
            #  'Atención al Cliente' son dos areas en el vocabulario de los
            #  roles y una sola puerta de servicio en la empresa. Antes eran
            #  dos salas, y eso era una consecuencia de deducir la estructura
            #  de los agentes.
            areas=["atencion_cliente", "Atención al Cliente",
                   "soporte_tecnico", "Soporte Técnico"],
            capacidades=["soporte"],
            ocupaciones=[
                Ocupacion(puesto="principal", agente="cliente_final"),
                Ocupacion(puesto="p1", agente="soporte_tecnico_cliente",
                          nombre="Diagnóstico"),
            ],
            acento="#0ea5a4",
        ),
        Departamento(
            id="comercial",
            rotulo="Comercial y Marketing",
            direccion="Dirección Comercial",
            piso=2,
            plantilla="comercial",
            areas=["ventas", "Ventas", "comercial", "Comercial y Marketing"],
            ocupaciones=[Ocupacion(puesto="principal", agente="ventas")],
            acento="#b8860b",
        ),
        Departamento(
            id="cartera",
            rotulo="Finanzas y Cartera",
            direccion="Dirección Financiera",
            piso=1,
            plantilla="expedientes",
            areas=["cartera", "Cartera", "Facturación", "Finanzas y Cartera"],
            capacidades=["facturacion"],
            ocupaciones=[Ocupacion(puesto="principal", agente="facturacion_cliente",
                                   nombre="Cobranza")],
            acento="#a855f7",
        ),
        Departamento(
            id="administracion",
            rotulo="Administración",
            direccion="Dirección General",
            piso=1,
            plantilla="reuniones",
            areas=["administracion", "Administración"],
            capacidades=["administracion"],
            ocupaciones=[Ocupacion(puesto="principal", agente="configuracion_guiada")],
            acento="#2563eb",
        ),
        Departamento(
            id="recursos_humanos",
            rotulo="Recursos Humanos",
            direccion="Dirección General",
            piso=1,
            plantilla="expedientes",
            areas=["recursos_humanos", "Recursos Humanos", "Talento Humano"],
            ocupaciones=[],
            acento="#be185d",
        ),
        Departamento(
            id="auditoria",
            rotulo="Auditoría y Cumplimiento",
            direccion="Dirección General",
            piso=1,
            plantilla="expedientes",
            areas=["auditoria", "Auditoría y Cumplimiento", "Cumplimiento"],
            ocupaciones=[],
            acento="#6b21a8",
        ),
    ],
    #  Espacios, no departamentos: no agrupan areas ni agentes. Una recepcion
    #  es parte del edificio y de ninguna manera una parte de la organizacion
    #  a la que se le puedan asignar responsabilidades.
    espacios=[
        EspacioDeTrabajo(id="direccion", rotulo="Dirección", piso=3,
                         plantilla="reuniones", acento="#64748b"),
        EspacioDeTrabajo(id="sala_reuniones", rotulo="Sala de Reuniones", piso=3,
                         plantilla="reuniones", acento="#0f766e"),
        EspacioDeTrabajo(id="recepcion", rotulo="Recepción", piso=1,
                         plantilla="atencion", acento="#92400e"),
    ],
)


def organizacion_de(config: TenantConfig) -> dict:
    """
    La organizacion de una empresa, lista para servir, CON SU PROCEDENCIA.

    'origen' no es decorativo y es la mitad del valor de esta funcion:

        declarada     la empresa la escribio. Es su organigrama.
        por_defecto   no la escribio. Es la estructura generica del producto,
                      y quien la muestre tiene que poder decirlo.

    Sin ese campo, las dos se ven igual en la pantalla y una empresa creeria
    que configuro algo que no configuro -- el dia que reorganice de verdad, no
    entenderia por que "ya estaba bien".
    """
    declarada = config.organizacion.declarada()
    org = config.organizacion if declarada else ORGANIZACION_POR_DEFECTO
    return {
        "origen": "declarada" if declarada else "por_defecto",
        **org.model_dump(mode="json"),
    }


#  ──────────────────────────────────────────────────────────────────────────
#  EL CATALOGO DE SALAS
#
#  Son NOMBRES y cuantos puestos tiene cada una. La geometria -cuanto mide la
#  sala, donde va cada escritorio- vive en el frontend, en
#  `lib/centro-mando/plantillas.js`, y es correcto que viva ahi: describir una
#  sala isometrica son cuarenta numeros y el motor no dibuja. Mismo reparto que
#  `AreaDeTrabajo.icono`.
#
#  Vive aqui y no en `canales/api.py` porque api.py ya tiene 9.000 lineas y
#  porque este dato lo necesitan dos cosas: la API que lo sirve al formulario y
#  el exportador que escribe el fixture del frontend. Importarlo desde api.py
#  levantaria la aplicacion Flask entera para leer una lista.
#
#  LOS TAMANOS. Una empresa no elige un numero de puestos -un numero puede
#  contradecir al dibujo, y entonces o el numero miente o el dibujo miente-:
#  elige una sala que YA tiene esa cantidad de escritorios. Por eso el catalogo
#  trae cada sala en tres tamanos y el nombre dice cual es: `tecnica_6` es la
#  sala tecnica de seis puestos.
#
#  La lista se escribe a mano aqui y se GENERA en el frontend. Que no se
#  separen lo vigila `tests/test_organizacion_config.py` contra el fixture que
#  escribe `cli/exportar_organizacion.py`, en las dos direcciones.
#  ──────────────────────────────────────────────────────────────────────────

#  Cuantos puestos de mas tiene cada tamano. Tiene que ser el mismo `TAMANOS`
#  que el de `plantillas.js`.
TAMANOS_DE_SALA = (3, 6)

_SALAS_BASE = (
    ("operaciones", "Centro de operaciones", 4),
    ("atencion", "Sala de atencion", 4),
    ("tecnica", "Sala tecnica", 3),
    ("expedientes", "Sala de expedientes", 4),
    ("comercial", "Sala comercial", 4),
    ("reuniones", "Sala de reuniones", 2),
)


def _catalogo() -> list[dict]:
    salida: list[dict] = []
    for nombre, rotulo, puestos in _SALAS_BASE:
        salida.append({"nombre": nombre, "rotulo": rotulo, "puestos": puestos})
        for extra in TAMANOS_DE_SALA:
            total = puestos + extra
            salida.append({"nombre": f"{nombre}_{total}",
                           "rotulo": f"{rotulo} - {total} puestos",
                           "puestos": total})
    return salida


PLANTILLAS_DE_SALA = _catalogo()
