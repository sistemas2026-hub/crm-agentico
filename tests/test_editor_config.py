# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DEL EDITOR DE ROLES  --  nucleo/config/editor.py
================================================================================

Por que existe
--------------
El editor escribe la configuracion que decide QUE VE cada agente. Un rol
guardado con la lista blanca de campos vacia, o un borrado que deja una
herramienta apuntando a un rol que ya no existe, no revienta al guardar:
revienta despues, en la primera consulta real, con el motor negandose a cargar
la configuracion del tenant entero. Con el cliente adelante.

Lo que se prueba aqui son las MUTACIONES sobre el documento, que es donde vive
esa logica. No hace falta base de datos: `_editar()` solo agrega la
transaccion, la lectura con 'for update' y el volcado -- y esa parte se
verifica desplegada, no en un test que tendria que inventarse un Postgres.

Cada caso termina pasando el documento por el MISMO validador que usa el motor
al cargar (`_validar`), porque un documento que muta bien pero no valida no
sirve de nada.

Uso
---
    py -3.13 tests/test_editor_config.py
================================================================================
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.config import cargar_config                              # noqa: E402
from nucleo.config.editor import (ErrorEdicion, _mutar_borrar,       # noqa: E402
                                  _mutar_crear, _mutar_editar,
                                  _mutar_persona, _validar,
                                  _validar_nombre_rol,
                                  catalogo_herramientas)

TENANT = "prueba"      # el nucleo no nombra clientes: solo rotula los errores

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    print(f"  {'[ok]  ' if condicion else '[FALLA]'} {que}")
    if not condicion:
        fallos.append(que)


def lanza(que: str, fn) -> None:
    """La mitad de esta guarda es que ciertas cosas NO se puedan guardar."""
    try:
        fn()
    except ErrorEdicion:
        print(f"  [ok]   {que}")
        return
    except Exception as e:
        print(f"  [FALLA] {que} -- lanzo {type(e).__name__}, no ErrorEdicion")
        fallos.append(que)
        return
    print(f"  [FALLA] {que} -- no lanzo nada")
    fallos.append(que)


def documento_base() -> dict:
    """
    Un documento con la misma forma que el JSONB de asistente.tenant_config:
    el volcado canonico del modelo, que es lo que escriben tanto
    cli/cargar_config.py como el editor.

    Sale del primer tenants/*.config.yaml que haya. No se nombra ninguno --
    ver tests/test_nucleo_sin_tenants.py.
    """
    yamls = [p for p in sorted((RAIZ / "tenants").glob("*.config.yaml"))
             if not p.name.startswith("tenant.config.example")]
    if not yamls:
        raise SystemExit("No hay ningun tenants/*.config.yaml con que probar.")
    return cargar_config(yamls[0]).model_dump(mode="json")


def _herramienta_consultable(doc: dict) -> dict:
    """Una herramienta http normal (ni de verificacion ni batch), que es la
    que exige lista blanca de campos."""
    return next(h for h in doc["herramientas"]
                if h["tipo"] == "http" and not h["verifica_identidad"])


# =============================================================================

def prueba_crear() -> None:
    print("\ncrear_rol")
    doc = documento_base()
    herr = _herramienta_consultable(doc)

    _mutar_crear(doc, "auditor_nuevo", area="Control", cargo="Auditor",
                 descripcion="Revisa cuentas.", orientado_a="colaborador",
                 herramientas=[{"nombre": herr["nombre"],
                                "campos_permitidos": ["id_servicio"]}])
    config = _validar(TENANT, doc)

    comprobar("auditor_nuevo" in config.roles, "el rol queda en la configuracion")
    comprobar(config.roles["auditor_nuevo"].area == "Control", "guarda el area")
    comprobar(config.roles["auditor_nuevo"].puede_consultar == [herr["nombre"]],
              "guarda la herramienta seleccionada")
    comprobar(config.roles["auditor_nuevo"].campos_permitidos[herr["nombre"]]
              == ["id_servicio"], "guarda la lista blanca de campos")

    despues = next(h for h in config.herramientas if h.nombre == herr["nombre"])
    comprobar("auditor_nuevo" in despues.roles_permitidos,
              "la herramienta declara al rol nuevo en roles_permitidos")

    lanza("un nombre repetido se rechaza",
          lambda: _mutar_crear(doc, "auditor_nuevo", None, None, "x",
                               "colaborador", []))
    for malo in ("Auditor", "1auditor", "auditor-nuevo", "a", "con espacio"):
        lanza(f"el nombre invalido '{malo}' se rechaza",
              lambda m=malo: _validar_nombre_rol(m))


def prueba_fail_closed() -> None:
    """
    Una herramienta que consulta datos y no trae lista blanca no devuelve nada
    (fail-closed, PRD 7.4). El validador tiene que negarse a guardar eso, no
    dejar un agente mudo que parece bien configurado.
    """
    print("\nfail-closed: herramienta sin campos_permitidos")
    doc = documento_base()
    herr = _herramienta_consultable(doc)

    _mutar_crear(doc, "rol_sin_campos", None, None, "Sin lista blanca.",
                 "colaborador", [{"nombre": herr["nombre"], "campos_permitidos": []}])
    lanza("el validador rechaza el rol sin lista blanca",
          lambda: _validar(TENANT, doc))


def _rol_sin_exclusivas(doc: dict, excepto: str | None = None) -> str:
    """
    Un rol al que se le puedan quitar herramientas sin dejar ninguna huerfana
    -- o sea, que no sea el unico que usa alguna. Ese otro caso se prueba
    aparte, en prueba_herramienta_huerfana().

    Puede que NINGUN rol del tenant cumpla eso: paso el 11/08/2026 al quitarse
    el rol 'tecnica', que dejo a los cuatro restantes como unicos dueños de
    alguna herramienta. Antes eso reventaba con un StopIteration a mitad de la
    corrida, que no dice nada de lo que se estaba probando.

    En ese caso se fabrica la condicion en el documento de trabajo (que es una
    copia y no toca la configuracion real): se le presta una herramienta
    exclusiva a otro rol para que deje de serlo. La prueba sigue midiendo lo
    mismo -- editar un rol sin dejar herramientas huerfanas -- en vez de
    depender de que el tenant tenga por casualidad un rol que sirva.
    """
    def sin_exclusivas() -> list[str]:
        exclusivas = {h["roles_permitidos"][0] for h in doc["herramientas"]
                      if len(h["roles_permitidos"]) == 1}
        return [n for n in doc["roles"] if n not in exclusivas and n != excepto]

    libres = sin_exclusivas()
    if libres:
        return libres[0]

    candidato = next(n for n in doc["roles"] if n != excepto)
    for h in doc["herramientas"]:
        if h["roles_permitidos"] == [candidato]:
            otro = next(n for n in doc["roles"] if n != candidato)
            h["roles_permitidos"] = [candidato, otro]
    return candidato


def prueba_editar() -> None:
    print("\neditar_rol")
    doc = documento_base()
    nombre = _rol_sin_exclusivas(doc)
    antes = copy.deepcopy(doc["roles"][nombre])
    herr = _herramienta_consultable(doc)

    _mutar_editar(doc, nombre, area="Nueva", cargo="Cargo nuevo",
                  descripcion="Descripcion nueva.", orientado_a="colaborador",
                  herramientas=[{"nombre": herr["nombre"],
                                 "campos_permitidos": ["id_servicio", "estado"]}])
    config = _validar(TENANT, doc)
    rol = config.roles[nombre]

    comprobar(rol.descripcion == "Descripcion nueva.", "cambia la descripcion")
    comprobar(rol.area == "Nueva" and rol.cargo == "Cargo nuevo",
              "cambia area y cargo")
    comprobar(rol.puede_consultar == [herr["nombre"]],
              "reemplaza la lista de herramientas, no la suma")
    comprobar(set(rol.campos_permitidos) == {herr["nombre"]},
              "descarta los campos de las herramientas que se quitaron")
    comprobar(rol.nunca_revelar == antes.get("nunca_revelar", []),
              "no pisa los campos que el formulario no toca (nunca_revelar)")

    quitadas = [h for h in config.herramientas
                if h.nombre != herr["nombre"] and h.nombre in antes["puede_consultar"]]
    comprobar(bool(quitadas) and all(nombre not in h.roles_permitidos
                                     for h in quitadas),
              f"las {len(quitadas)} herramientas que se le quitaron dejan de "
              f"declararlo en roles_permitidos")

    lanza("editar un rol inexistente se rechaza",
          lambda: _mutar_editar(doc, "no_existe", None, None, "x",
                                "colaborador", []))


def prueba_herramienta_huerfana() -> None:
    """
    Quitarle a un rol la unica herramienta que solo el usaba la deja sin nadie
    que pueda consultarla. Desde el formulario parece un cambio inocente, y sin
    este control el error que ve el administrador es
    'herramientas.8.roles_permitidos: List should have at least 1 item'.
    """
    print("\nherramienta que se quedaria sin ningun rol")
    doc = documento_base()
    exclusiva = next((h for h in doc["herramientas"]
                      if len(h["roles_permitidos"]) == 1), None)
    if not exclusiva:
        print("  (ningun tenant de prueba tiene una herramienta exclusiva)")
        return
    dueno = exclusiva["roles_permitidos"][0]

    lanza(f"editar '{dueno}' quitandole '{exclusiva['nombre']}' se rechaza",
          lambda: _mutar_editar(doc, dueno, None, None, "x", "colaborador", []))
    lanza(f"borrar '{dueno}', unico rol de '{exclusiva['nombre']}', se rechaza",
          lambda: _mutar_borrar(documento_base(), dueno))


def prueba_borrar() -> None:
    print("\nborrar_rol")
    doc = documento_base()

    # El destino de escalamiento no se puede borrar: dejaria al asistente sin
    # a quien derivar, y el validador lo rechazaria despues igual.
    destino = (doc.get("escalamiento") or {}).get("destino_rol")
    if destino:
        lanza(f"no se borra '{destino}', que es el destino de escalamiento",
              lambda: _mutar_borrar(doc, destino))

    borrable = _rol_sin_exclusivas(doc, excepto=destino)
    usaban = [h["nombre"] for h in doc["herramientas"]
              if borrable in h["roles_permitidos"]]

    _mutar_borrar(doc, borrable)
    config = _validar(TENANT, doc)

    comprobar(borrable not in config.roles, "el rol desaparece")
    comprobar(all(borrable not in h.roles_permitidos for h in config.herramientas),
              f"ninguna de las {len(usaban)} herramientas lo sigue nombrando")
    comprobar(f"rol:{borrable}" not in config.llm.overrides,
              "se limpia su override de modelo (llm.overrides)")

    lanza("borrar un rol inexistente se rechaza",
          lambda: _mutar_borrar(doc, "no_existe"))


def prueba_persona() -> None:
    """
    La personalidad es lo unico que el cliente edita sin tocar permisos, asi
    que lo que hay que comprobar es justamente eso: que no los toque. Y que el
    tope de las instrucciones exista, porque ese texto viaja en cada turno y
    pasarse degrada las respuestas sin dar ningun error.
    """
    print("\nguardar_persona")
    doc = documento_base()
    permisos_antes = {n: (r["puede_consultar"], r["campos_permitidos"])
                      for n, r in doc["roles"].items()}

    _mutar_persona(doc, "Dexter", "formal", "media", "Nunca prometas plazos.")
    config = _validar(TENANT, doc)

    comprobar(config.persona.nombre_asistente == "Dexter", "cambia el nombre")
    comprobar(config.persona.tono == "formal", "cambia el tono")
    comprobar(config.persona.longitud_respuesta == "media", "cambia el largo")
    comprobar(config.persona.instrucciones_adicionales == "Nunca prometas plazos.",
              "guarda las instrucciones adicionales")
    comprobar(
        {n: (r.puede_consultar, r.campos_permitidos)
         for n, r in config.roles.items()} == permisos_antes,
        "no toca ni un permiso de ningun rol")

    lanza("un tono que no existe se rechaza",
          lambda: _validar(TENANT, _con_persona(documento_base(), tono="simpatico")))
    lanza("un largo que no existe se rechaza",
          lambda: _validar(TENANT, _con_persona(documento_base(),
                                                longitud_respuesta="cortita")))
    lanza("un nombre vacio se rechaza",
          lambda: _validar(TENANT, _con_persona(documento_base(), nombre="")))
    # Texto realista, con espacios: una cadena de 2.000 'x' la frenaria antes
    # el barrido de secretos (la confundiria con base64) y la prueba pasaria
    # por el motivo equivocado.
    largo = ("Responde siempre citando el documento de origen. " * 60)
    comprobar(_validar(TENANT, _con_persona(documento_base(),
                                            instrucciones=largo[:2000])) is not None,
              "2.000 caracteres justos si entran")
    lanza("instrucciones de mas de 2.000 caracteres se rechazan",
          lambda: _validar(TENANT, _con_persona(documento_base(),
                                                instrucciones=largo[:2001])))

    # El barrido de secretos alcanza a este campo, y es lo que se quiere: es
    # una caja de texto libre en una pantalla de cliente, o sea el lugar mas
    # probable donde alguien pegue una clave "para que el asistente la use".
    lanza("una clave pegada en las instrucciones se rechaza",
          lambda: _validar(TENANT, _con_persona(
              documento_base(),
              instrucciones="sk-proj-A1b2C3d4E5f6G7h8I9j0K1l2M3n4")))


def _con_persona(doc: dict, nombre: str = "Dexter", tono: str = "cercano",
                 longitud_respuesta: str = "breve", instrucciones: str = "") -> dict:
    _mutar_persona(doc, nombre, tono, longitud_respuesta, instrucciones)
    return doc


def prueba_ida_y_vuelta() -> None:
    """
    El otro medio circuito: lo que el editor escribe en la base tiene que poder
    volver al YAML del repositorio (`cli/cargar_config.py --exportar`).

    Se comprueban las tres propiedades de las que depende que ese archivo siga
    sirviendo de respaldo:

      fiel        releerlo reproduce EXACTAMENTE lo que hay en la base
      conservado  no se pierde ni un comentario -- son notas de verificacion
                  en vivo y motivos de exclusion, no adorno
      estable     exportar dos veces da el mismo texto, o cada exportacion
                  ensuciaria el diff y nadie lo miraria
    """
    from io import StringIO

    import yaml
    from cli.cargar_config import _fusionar, _yaml_rt

    print("\nida y vuelta: de la base al YAML (--exportar)")
    yamls = [p for p in sorted((RAIZ / "tenants").glob("*.config.yaml"))
             if not p.name.startswith("tenant.config.example")]
    ruta = yamls[0]
    texto = ruta.read_text(encoding="utf-8")

    # Lo que quedaria en la base despues de crear un agente desde la interfaz.
    doc = documento_base()
    herr = _herramienta_consultable(doc)
    _mutar_crear(doc, "auditor_exportado", "Control", "Auditor",
                 "Creado desde la interfaz.", "colaborador",
                 [{"nombre": herr["nombre"], "campos_permitidos": ["id_servicio"]}])
    cfg = _validar(TENANT, doc)
    completo = cfg.model_dump(mode="json")
    minimo = cfg.model_dump(mode="json", exclude_defaults=True)

    def exportar(fuente: str) -> str:
        nodo = _yaml_rt.load(fuente)
        _fusionar(nodo, completo, minimo)
        buf = StringIO()
        _yaml_rt.dump(nodo, buf)
        return buf.getvalue()

    salida = exportar(texto)
    relectura = _validar(TENANT, yaml.safe_load(salida)).model_dump(mode="json")

    comprobar(relectura == completo,
              "el archivo exportado se relee como lo que hay en la base")
    antes = sum(1 for l in texto.splitlines() if l.strip().startswith("#"))
    despues = sum(1 for l in salida.splitlines() if l.strip().startswith("#"))
    comprobar(antes == despues,
              f"conserva los {antes} comentarios del archivo")
    comprobar("auditor_exportado" in salida,
              "el rol creado desde la interfaz aparece en el archivo")
    comprobar(exportar(salida) == salida,
              "exportar de nuevo no cambia nada (el diff solo muestra lo real)")

    crecimiento = len(salida.splitlines()) - len(texto.splitlines())
    comprobar(crecimiento < 40,
              f"no materializa los valores por defecto (+{crecimiento} lineas, "
              f"no +170)")


def prueba_catalogo() -> None:
    print("\ncatalogo_herramientas")
    config = _validar(TENANT, documento_base())
    catalogo = catalogo_herramientas(config)

    comprobar(len(catalogo) == len(config.herramientas),
              "lista todas las herramientas")
    comprobar(all({"nombre", "tipo", "verifica_identidad", "campos_conocidos"}
                  <= set(h) for h in catalogo),
              "cada entrada trae lo que el formulario necesita")
    verificacion = [h for h in catalogo if h["verifica_identidad"]]
    comprobar(all(not h["campos_conocidos"] for h in verificacion),
              "una herramienta de verificacion no ofrece campos (no los usa)")


if __name__ == "__main__":
    print("=" * 70)
    print(" EDITOR DE ROLES  --  mutaciones sobre el documento de configuracion")
    print("=" * 70)

    prueba_crear()
    prueba_fail_closed()
    prueba_editar()
    prueba_herramienta_huerfana()
    prueba_borrar()
    prueba_persona()
    prueba_ida_y_vuelta()
    prueba_catalogo()

    print("\n" + "=" * 70)
    if fallos:
        print(f" {len(fallos)} FALLA(S):")
        for f in fallos:
            print(f"   - {f}")
        sys.exit(1)
    print(" Todo en orden.")
