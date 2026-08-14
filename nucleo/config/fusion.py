# -*- coding: utf-8 -*-
"""
================================================================================
 FUSION DE ROLES  --  un colaborador con varios agentes asignados
================================================================================

Por que existe
--------------
Hasta ahora un turno se atendia con UN rol y punto. Para un cliente final eso
sigue siendo cierto y es deliberado (ver 'orientado_a' en schema.py). Pero un
colaborador interno no encaja en un solo agente: quien atiende un reclamo
necesita ver el ticket Y la factura, y hasta ahora tenia que elegir a cual de
los dos agentes preguntarle -- de hecho ni siquiera podia elegir, porque la
pantalla estaba fija en uno solo.

Esto arma un rol SINTETICO con la union de los agentes que esa persona tiene
asignados (asistente.tenant_users). No es un agente nuevo que haya que
configurar: se calcula en cada turno a partir de los que ya existen en el YAML.

POR QUE NO HAY UN MODELO ORQUESTADOR
------------------------------------
La alternativa evaluada era un agente 'principal' que clasificara la pregunta
y derivara a un sub-agente. Se descarto por costo: el sub-agente corre su
propio ciclo completo, asi que un turno pasaba de ~2 llamadas al modelo a ~4
--con turnos que ya tardan 4.7-12 s (PRD RNF-04)--. Y no hacia falta: elegir
que herramienta usar para una pregunta es exactamente lo que hace el
tool-calling, que el motor ya tiene. El enrutador es el catalogo, no otro
modelo.

QUE SE UNE Y EN QUE DIRECCION  (no es simetrico)
-------------------------------------------------
  puede_consultar     union      -- suma capacidades
  campos_permitidos   union      -- por herramienta; nunca aparece un campo
                                    que ninguno de sus roles permitia
  nunca_revelar       union      -- suma restricciones (es una lista NEGRA)
  descripcion         concatena  -- cada agente aporta su prosa

'campos_permitidos' se une hacia MAS permisivo y 'nunca_revelar' hacia MAS
restrictivo, y eso es correcto: son listas de signo opuesto. La garantia que
se conserva es la que importa (schema.py:Rol): un campo que NINGUNO de sus
agentes declaro no se entrega, porque la lista blanca sigue siendo blanca --
unir dos listas blancas da otra lista blanca.

FAIL-CLOSED
-----------
Sin agentes asignados no hay rol que fusionar y esto levanta ValueError. No
devuelve un rol vacio: un rol sin herramientas parece que "funciona" y deja al
colaborador hablando con un asistente mudo, sin que nadie entienda por que.
================================================================================
"""

from __future__ import annotations

from nucleo.config.schema import Rol


def fusionar_roles(config, nombres: list[str]) -> tuple[str, Rol]:
    """
    Devuelve (nombre_sintetico, Rol) con la union de los roles pedidos.

    Con un solo nombre devuelve ESE rol tal cual, sin fusionar nada: es el
    caso mas comun y no tiene sentido construirle una copia.

    Solo fusiona roles del mismo 'orientado_a'. Mezclar un agente interno con
    uno de cliente final seria un agujero de seguridad, no una comodidad: los
    internos no verifican identidad (dan por hecho que quien escribe ya es un
    empleado autorizado) y pueden consultar a CUALQUIER cliente. Ver
    nucleo/seguridad/verificacion.py::nivel_requerido.
    """
    if not nombres:
        raise ValueError("No hay ningun agente asignado.")

    desconocidos = [n for n in nombres if n not in config.roles]
    if desconocidos:
        raise ValueError(
            f"agente(s) inexistente(s): {', '.join(sorted(desconocidos))}. "
            f"Agentes del tenant: {', '.join(sorted(config.roles))}")

    if len(nombres) == 1:
        return nombres[0], config.roles[nombres[0]]

    roles = [config.roles[n] for n in nombres]

    audiencias = {r.orientado_a for r in roles}
    if len(audiencias) > 1:
        raise ValueError(
            "No se pueden fusionar agentes que le hablan a audiencias "
            "distintas (colaborador y cliente_final): el de cliente final "
            "verifica identidad y solo ve SU propio servicio, el interno da "
            "por hecho que quien escribe ya esta autorizado y puede consultar "
            "a cualquier cliente.")

    # Orden estable (el de 'nombres', no el de un set) para que el prompt y el
    # catalogo de herramientas no cambien entre turnos: dos prompts distintos
    # para la misma persona harian imposible reproducir un problema.
    herramientas: list[str] = []
    for r in roles:
        for h in r.puede_consultar:
            if h not in herramientas:
                herramientas.append(h)

    campos: dict[str, list[str]] = {}
    for r in roles:
        for herramienta, permitidos in r.campos_permitidos.items():
            acumulado = campos.setdefault(herramienta, [])
            for campo in permitidos:
                if campo not in acumulado:
                    acumulado.append(campo)

    nunca: list[str] = []
    for r in roles:
        for campo in r.nunca_revelar:
            if campo not in nunca:
                nunca.append(campo)

    descripcion = "\n\n".join(
        f"Como {n}: {config.roles[n].descripcion.strip()}"
        for n in nombres if config.roles[n].descripcion.strip())

    sintetico = Rol(
        descripcion=descripcion,
        puede_consultar=herramientas,
        campos_permitidos=campos,
        nunca_revelar=nunca,
        orientado_a=roles[0].orientado_a,
        # 'area'/'cargo' quedan vacios a proposito: son etiquetas
        # organizativas de UN agente (schema.py), y esta persona actua como
        # varios a la vez. Inventarle un area combinada seria un dato falso.
        area=None,
        cargo=None,
    )
    return "+".join(nombres), sintetico


def modelo_fusionado(config, nombres: list[str]) -> str | None:
    """
    Que modelo le corresponde al rol fusionado, o None si ninguno de los que
    lo componen declara override.

    Hace falta porque 'llm.overrides' se indexa por NOMBRE de rol
    ('rol:soporte'), y el rol fusionado tiene un nombre que no figura ahi. Sin
    esto cae en 'modelo_por_defecto' -- y eso rompio de verdad en la primera
    prueba: el default del tenant sigue siendo el modelo local, que desde que
    los embeddings pasaron a la API de OpenAI ya no corre en ningun lado.

    Si los roles que se fusionan declaran modelos DISTINTOS se toma el del
    primero y se avisa por consola. Es una situacion rara y probablemente un
    error de configuracion (todos los agentes internos suelen ir al mismo
    modelo), asi que lo que importa es que no pase en silencio.
    """
    elegidos = [config.llm.overrides.get(f"rol:{n}") for n in nombres]
    declarados = [m for m in elegidos if m]
    if not declarados:
        return None
    if len(set(declarados)) > 1:
        print(f"[agentes] {'+'.join(nombres)} mezcla roles con modelos "
              f"distintos ({', '.join(sorted(set(declarados)))}); se usa "
              f"{declarados[0]}. Revisar llm.overrides del tenant.")
    return declarados[0]
