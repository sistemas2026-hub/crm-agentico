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
from nucleo.config.editor import (ErrorEdicion, _mutar_ajustes_bandeja,  # noqa: E402
                                  _mutar_borrar,
                                  _mutar_crear, _mutar_editar,
                                  _mutar_marcas_precio,
                                  _mutar_persona, _mutar_rol_de_entrada,
                                  _mutar_rotulos_bandeja,
                                  _mutar_respuestas_rapidas,
                                  _mutar_casos_manual, _fundir_rotulos_de_casos,
                                  claves_sin_rotulo,
                                  _validar,
                                  _validar_nombre_rol,
                                  catalogo_herramientas,
                                  guardar_ajustes_bandeja)

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
        # Tampoco un rol al que alguna herramienta 'deriva_rol' apunte
        # (areas_destino): esta prueba edita 'orientado_a' a colaborador de
        # forma generica, y un rol que sigue siendo blanco de una derivacion
        # tiene que seguir orientado a cliente_final (ver la coherencia
        # global en schema.py) -- no es el caso que esta prueba mide.
        derivables = {n for h in doc["herramientas"] if h.get("deriva_rol")
                     for n in h.get("areas_destino", [])}
        # Ni el rol que atiende los canales publicos: pasarlo a colaborador
        # dejaria a quien escribe por WhatsApp atendido por un rol interno,
        # que no verifica identidad y puede consultar a cualquier cliente.
        # El esquema lo rechaza (schema.py), y con razon -- no es lo que esta
        # prueba mide, igual que 'exclusivas' y 'derivables'.
        entrada = {doc.get("rol_de_entrada")} - {None}
        return [n for n in doc["roles"]
               if n not in exclusivas and n not in derivables
               and n not in entrada and n != excepto]

    libres = sin_exclusivas()
    if libres:
        return libres[0]

    derivables = {n for h in doc["herramientas"] if h.get("deriva_rol")
                 for n in h.get("areas_destino", [])}
    vetados = derivables | ({doc.get("rol_de_entrada")} - {None})
    candidato = next((n for n in doc["roles"] if n != excepto and n not in vetados),
                     next(n for n in doc["roles"] if n != excepto))
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


def prueba_catalogo_dice_lo_que_hace_cada_una() -> None:
    #  02/11/2026: el formulario de agentes agrupa las herramientas por lo que
    #  HACEN y aparta las que dispara el sistema, para que quien crea un
    #  agente no le de una herramienta "NO la llames tu" sin saberlo.
    print("\ncatalogo: que hace cada herramienta")
    config = _validar(TENANT, documento_base())
    por_nombre = {h["nombre"]: h for h in catalogo_herramientas(config)}
    claves = {"escribe", "pide_aprobacion", "critica", "deriva", "de_sistema"}
    comprobar(all(claves <= set(h) for h in por_nombre.values()),
              "cada entrada dice si escribe, pide aprobacion, es critica, deriva o es del sistema")
    lectura = next(h for h in config.herramientas if h.solo_lectura and not h.deriva_rol)
    comprobar(por_nombre[lectura.nombre]["escribe"] is False, "una consulta no escribe")
    deriva = next((h for h in config.herramientas if h.deriva_rol), None)
    if deriva is not None:
        comprobar(por_nombre[deriva.nombre]["deriva"] is True, "la de derivar dice que deriva")
    aprobacion = next((h for h in config.herramientas if h.aprobacion_humana), None)
    if aprobacion is not None:
        comprobar(por_nombre[aprobacion.nombre]["pide_aprobacion"] is True
                  and por_nombre[aprobacion.nombre]["critica"] == aprobacion.critica,
                  "la que pide aprobacion lo dice, y si es critica")
    servicio = next((h for h in config.herramientas if h.invocable_por_servicio), None)
    if servicio is not None:
        comprobar(por_nombre[servicio.nombre]["de_sistema"] is True,
                  "la que invoca un servicio es del sistema")


def prueba_agente_completo_desde_la_pantalla() -> None:
    #  02/11/2026: crear un agente de clientes y que le lleguen conversaciones
    #  era DOS pantallas -- el formulario y el flujo de derivacion --, y con
    #  la segunda olvidada el agente quedaba creado e invisible. Y la
    #  verificacion de identidad y lo que nunca revela solo se podian
    #  cambiar en el archivo.
    print("\nun agente completo desde el formulario")
    doc = documento_base()
    deriva = next((h for h in doc["herramientas"] if h.get("deriva_rol")), None)
    if deriva is None:
        print("  (sin herramienta de derivacion en este tenant: se saltea)")
        return
    _mutar_crear(doc, "atencion_nueva", area="Atencion", cargo="Agente",
                 descripcion="Atiende consultas de saldo.", orientado_a="cliente_final",
                 herramientas=[],
                 extras={"atiende": "  saldo, facturas y fechas de corte  ",
                         "conectar_al_router": True, "exige_verificacion": False,
                         "nunca_revelar": [" el costo del plan ", "", "el costo del plan"]})
    config = _validar(TENANT, doc)
    rol = config.roles["atencion_nueva"]
    comprobar(rol.atiende == "saldo, facturas y fechas de corte", "guarda que temas atiende, sin espacios")
    comprobar(rol.exige_verificacion is False, "guarda si verifica identidad")
    comprobar(rol.nunca_revelar == ["el costo del plan"], "lo que nunca revela, limpio y sin repetir")
    destinos = next(h for h in config.herramientas if h.deriva_rol).areas_destino
    comprobar("atencion_nueva" in destinos, "queda conectado al router: el router le puede derivar")
    comprobar(deriva["nombre"] in rol.puede_consultar,
              "un agente de clientes recibe sola la herramienta de derivar: nunca queda encerrado")

    doc2 = documento_base()
    lanza("conectar al router un agente interno se rechaza",
          lambda: _mutar_crear(doc2, "interno_nuevo", None, None, "x", "colaborador", [],
                               extras={"conectar_al_router": True}))

    #  Editar SIN extras no toca lo que ya tenia: el formulario viejo, o una
    #  edicion que no los manda, no los borra.
    _mutar_editar(doc, "atencion_nueva", area="Atencion", cargo="Agente",
                  descripcion="Atiende consultas de saldo y pagos.",
                  orientado_a="cliente_final", herramientas=[])
    config = _validar(TENANT, doc)
    rol = config.roles["atencion_nueva"]
    comprobar(rol.atiende == "saldo, facturas y fechas de corte" and rol.exige_verificacion is False
              and rol.nunca_revelar == ["el costo del plan"]
              and "atencion_nueva" in next(h for h in config.herramientas if h.deriva_rol).areas_destino,
              "editar sin esos datos no borra lo que ya tenia")

    _mutar_editar(doc, "atencion_nueva", area="Atencion", cargo="Agente",
                  descripcion="Atiende consultas de saldo y pagos.",
                  orientado_a="cliente_final", herramientas=[],
                  extras={"conectar_al_router": False})
    config = _validar(TENANT, doc)
    comprobar("atencion_nueva" not in next(h for h in config.herramientas if h.deriva_rol).areas_destino,
              "desconectar lo saca del router")


# =============================================================================
#  LA BANDA 'SIN GESTION' NO SE PUEDE GUARDAR DE FORMA QUE NO HAGA NADA
# =============================================================================
#
# Tres silencios, los tres hallados el 26/09/2026 al auditar la rama de
# integracion antes de integrarla, y los tres del mismo tipo: la
# configuracion aceptaba un estado en el que la guarda quedaba apagada sin
# que nadie se enterara. Lo que se afirma aca es el EFECTO --que el
# documento no queda en ese estado-- y no que exista una validacion.


def prueba_banda_sin_gestion() -> None:
    print()
    print("banda_sin_gestion: no se puede apagar sin decirlo")

    # --- 1. un umbral sin rol de entrada se guardaria sin efecto ------------
    doc = documento_base()
    doc.pop("rol_de_entrada", None)
    lanza("sin rol de entrada, el umbral no se guarda",
          lambda: _mutar_ajustes_bandeja(doc, 30, None, 24))
    comprobar(doc.get("sin_gestion_horas") is None,
              "y el umbral sigue apagado, no a medio escribir")

    # --- 2. la banda no puede aparecer despues de que el barrido cierre ----
    doc = documento_base()
    doc["rol_de_entrada"] = _rol_de_cliente_cualquiera(doc)
    doc.setdefault("limites", {})["horas_inactividad_cierra"] = 24
    doc["cierre_inactivas_ia"] = {"habilitado": True,
                                  "rollout_cutoff": "2026-09-22T15:58:07Z"}
    lanza("con el barrido en 24 h, un umbral de 72 no se guarda",
          lambda: _mutar_ajustes_bandeja(doc, 30, None, 72))
    comprobar(doc.get("sin_gestion_horas") is None,
              "y la ventana en que nadie la cierra ni la ve no existe")

    _mutar_ajustes_bandeja(doc, 30, None, 24)
    comprobar(doc.get("sin_gestion_horas") == 24,
              "el umbral igual al del barrido si se guarda (no hay ventana)")

    # Con el barrido apagado no hay ventana que proteger, y el umbral es
    # libre: la validacion acota lo que hace daño, no lo que se le parece.
    doc2 = documento_base()
    doc2["rol_de_entrada"] = _rol_de_cliente_cualquiera(doc2)
    doc2.setdefault("limites", {})["horas_inactividad_cierra"] = 24
    doc2["cierre_inactivas_ia"] = {"habilitado": False}
    _mutar_ajustes_bandeja(doc2, 30, None, 720)
    comprobar(doc2.get("sin_gestion_horas") == 720,
              "con el barrido apagado, 720 h se guarda igual")

    # --- 3. vaciar el rol de entrada apagaria la banda por la otra puerta --
    doc3 = documento_base()
    doc3["rol_de_entrada"] = _rol_de_cliente_cualquiera(doc3)
    _mutar_ajustes_bandeja(doc3, 30, None, 24)
    antes = doc3["rol_de_entrada"]
    lanza("con la banda encendida, el rol de entrada no se puede vaciar",
          lambda: _mutar_rol_de_entrada(doc3, None))
    comprobar(doc3.get("rol_de_entrada") == antes,
              "y el rol sigue puesto: la banda no se apaga de rebote")

    _mutar_ajustes_bandeja(doc3, 30, None, None)
    comprobar(doc3.get("sin_gestion_horas") is None,
              "vaciar el umbral SI apaga la banda (es la puerta correcta)")
    _mutar_rol_de_entrada(doc3, None)
    comprobar(doc3.get("rol_de_entrada") is None,
              "y recien entonces el rol se puede vaciar")

    # --- 4. el cuarto parametro es obligatorio ----------------------------
    # Un llamador con la firma vieja borraria el umbral --y con el, la
    # excepcion del barrido-- sin decir nada. Se afirma el efecto: la
    # llamada no llega a la base.
    try:
        guardar_ajustes_bandeja(TENANT, 30, None)      # type: ignore[call-arg]
    except TypeError:
        comprobar(True, "la firma vieja de tres argumentos ya no compila")
    except Exception as e:
        comprobar(False, f"la firma vieja lanzo {type(e).__name__}, no TypeError")
    else:
        comprobar(False, "la firma vieja de tres argumentos todavia se acepta")

    # --- 5. y la carga del YAML no lo puede pisar sin frenar --------------
    # SECCIONES_EDITABLES es la lista que cli/cargar_config.py mira antes de
    # sobrescribir la base con el archivo. Sin el umbral ahi, el comando que
    # CLAUDE.md 8 manda correr tras cada pull apagaba la banda -- y con ella
    # la excepcion del barrido -- sin avisar. Mismo patron que guias_tv.
    from nucleo.config import editor as _ed
    comprobar("sin_gestion_horas" in _ed.SECCIONES_EDITABLES,
              "el umbral esta protegido de la carga del YAML (SECCIONES_EDITABLES)")

    # Y lo mutado sigue siendo una configuracion valida.
    doc4 = documento_base()
    doc4["rol_de_entrada"] = _rol_de_cliente_cualquiera(doc4)
    _mutar_ajustes_bandeja(doc4, 30, None, 12)
    config = _validar(TENANT, doc4)
    comprobar(config.sin_gestion_horas == 12,
              "y el documento pasa por el validador del motor con el umbral puesto")


def _rol_de_cliente_cualquiera(doc: dict) -> str:
    """El nucleo no nombra roles de ningun cliente: se toma el primero que
    atienda a cliente_final, que es lo que el esquema exige del rol de
    entrada."""
    for nombre, rol in doc["roles"].items():
        if rol.get("orientado_a") == "cliente_final":
            return nombre
    raise SystemExit("ningun rol orientado a cliente_final con que probar")


# =============================================================================
#  DE DONDE SALIO LA CONFIG, Y EL UMBRAL CON EL QUE LA BANDA SE CALCULA
# =============================================================================
#
# Las dos cosas las agrego b3ce928 y ninguna tenia prueba: el auditor del
# delta mostro que borrar el marcado o invertir su default dejaba todo en
# verde con la proteccion apagada -- o, al reves, con el barrido apagado para
# siempre y sin que nadie se enterara.


def prueba_origen_de_la_config() -> None:
    print()
    print("origen_de_la_config: 'apagado' y 'no pude leer' no son lo mismo")
    from nucleo.config import fuente
    from nucleo.config.schema import cargar_config as leer_yaml

    yamls = [p for p in sorted((RAIZ / "tenants").glob("*.config.yaml"))
             if not p.name.startswith("tenant.config.example")]
    ruta = yamls[0]
    nombre = ruta.name.replace(".config.yaml", "")

    # 1. Leer un archivo marca 'yaml', y se marca en el lector: asi vale por
    #    los usos de cli/, no solo por el camino del reloj.
    comprobar(leer_yaml(ruta)._origen == "yaml",
              "leer un YAML marca la config como venida de un archivo")

    # 2. El default es 'base', y tiene que serlo: un documento que sale de la
    #    tabla es la fuente de verdad.
    comprobar(_validar(TENANT, documento_base())._origen == "base",
              "y una config armada desde el documento de la base queda en 'base'")

    # 3. El camino real: fuente.cargar cae al YAML cuando la base no tiene la
    #    fila, y lo que devuelve queda marcado.
    original = fuente.desde_base
    try:
        fuente.desde_base = lambda t: None
        comprobar(fuente.cargar(nombre, RAIZ)._origen == "yaml",
                  "y fuente.cargar, al caer a la semilla, devuelve una config marcada")
    finally:
        fuente.desde_base = original

    # 4. Y no al reves: lo que la base sirve no se marca como degradado.
    desde_la_base = _validar(TENANT, documento_base())
    try:
        fuente.desde_base = lambda t: (desde_la_base, 7)
        comprobar(fuente.cargar(nombre, RAIZ)._origen == "base",
                  "y lo que la base si sirve NO queda marcado como degradado")
    finally:
        fuente.desde_base = original


def prueba_umbral_efectivo_de_la_banda() -> None:
    print()
    print("umbral_efectivo: la banda nunca aparece despues del cierre")
    doc = documento_base()
    doc["sin_gestion_horas"] = 72                       # entra por el YAML,
    doc.setdefault("limites", {})["horas_inactividad_cierra"] = 24   # sin pasar
    doc["cierre_inactivas_ia"] = {"habilitado": True,   # por el editor
                                  "rollout_cutoff": "2026-09-22T15:58:07Z"}
    config = _validar(TENANT, doc)
    comprobar(config.sin_gestion_horas == 72,
              "el esquema acepta el par incoherente (no vuelve incargable la config)")
    comprobar(config.sin_gestion_horas_efectivas() == 24,
              "pero el umbral EFECTIVO se acota al del cierre: no hay ventana invisible")

    doc["cierre_inactivas_ia"] = {"habilitado": False}
    comprobar(_validar(TENANT, doc).sin_gestion_horas_efectivas() == 72,
              "con el barrido apagado no hay nada que acotar y vale el numero pedido")

    doc["cierre_inactivas_ia"] = {"habilitado": True,
                                  "rollout_cutoff": "2026-09-22T15:58:07Z"}
    doc["sin_gestion_horas"] = 6
    comprobar(_validar(TENANT, doc).sin_gestion_horas_efectivas() == 6,
              "y un umbral anterior al cierre se respeta tal cual")

    doc["sin_gestion_horas"] = None
    comprobar(_validar(TENANT, doc).sin_gestion_horas_efectivas() is None,
              "sin umbral no hay banda, y acotar nada sigue siendo nada")


def prueba_marcas_de_precio() -> None:
    """
    De que herramienta sale el listado de planes y de cual el precio.

    Lo que esta guarda protege no es que el campo se escriba: es que no
    queden DOS herramientas marcadas con el mismo papel. Si quedaran dos
    'listado', cual gana la decide el orden de la lista en el JSONB, y un
    cambio de configuracion pasaria a depender de donde quedo una fila.
    """
    print("\nmarcas de precio")
    doc = documento_base()
    nombres = [h["nombre"] for h in doc["herramientas"]]
    if len(nombres) < 3:
        comprobar(False, "hacen falta 3 herramientas para probar esto")
        return
    a, b, c = nombres[0], nombres[1], nombres[2]

    _mutar_marcas_precio(doc, a, b)
    por_nombre = {h["nombre"]: h for h in doc["herramientas"]}
    comprobar(por_nombre[a].get("sincroniza_precio_plan") == "listado",
              "la herramienta elegida para el listado queda marcada 'listado'")
    comprobar(por_nombre[b].get("sincroniza_precio_plan") == "detalle",
              "la elegida para el detalle queda marcada 'detalle'")
    comprobar(
        sum(1 for h in doc["herramientas"]
            if h.get("sincroniza_precio_plan")) == 2,
        "quedan exactamente DOS herramientas marcadas, no mas")

    # El EFECTO que importa: elegir otra deja de marcar la anterior.
    _mutar_marcas_precio(doc, c, b)
    por_nombre = {h["nombre"]: h for h in doc["herramientas"]}
    comprobar(not por_nombre[a].get("sincroniza_precio_plan"),
              "cambiar de herramienta DESMARCA la que estaba antes")
    comprobar(por_nombre[c].get("sincroniza_precio_plan") == "listado",
              "y marca la nueva")
    comprobar(
        sum(1 for h in doc["herramientas"]
            if h.get("sincroniza_precio_plan") == "listado") == 1,
        "nunca hay dos 'listado' a la vez")

    # El documento resultante tiene que seguir validando contra el mismo
    # esquema con que el motor carga la configuracion -- una mutacion que
    # muta bien y no valida no sirve.
    cfg = _validar(TENANT, copy.deepcopy(doc))
    comprobar(
        next((h.nombre for h in cfg.herramientas
              if h.sincroniza_precio_plan == "listado"), None) == c,
        "el motor lee la marca del documento validado")
    comprobar(
        next((h.nombre for h in cfg.herramientas
              if h.sincroniza_precio_plan == "detalle"), None) == b,
        "y lee tambien la del detalle")

    lanza("una herramienta que no existe no se puede marcar",
          lambda: _mutar_marcas_precio(documento_base(), "no_existe_jamas", b))
    lanza("ni como detalle",
          lambda: _mutar_marcas_precio(documento_base(), a, "no_existe_jamas"))
    lanza("la misma herramienta para los dos pasos se rechaza",
          lambda: _mutar_marcas_precio(documento_base(), a, a))

    sin_herramientas = documento_base()
    sin_herramientas["herramientas"] = []
    lanza("un catalogo vacio se rechaza en vez de guardar marcas que no apuntan a nada",
          lambda: _mutar_marcas_precio(sin_herramientas, a, b))

def prueba_rotulos_bandeja() -> None:
    """
    Como se lee cada motivo, etiqueta y caso en la Bandeja (29/10/2026).

    Lo que se protege: que un rotulo solo se guarde para una clave que la
    empresa tiene de verdad, que el vacio no se guarde como texto, y que el
    documento siga validando -- un mapa que muta bien y no carga no sirve.
    """
    print("\n-- rotulos de la Bandeja --")
    doc = documento_base()
    motivo = (doc.get("escalamiento") or {}).get("activar_si", [None])[0]
    etiqueta = ((doc.get("conversaciones") or {}).get("etiquetas") or [None])[0]
    if not motivo or not etiqueta:
        comprobar(False, "el tenant de prueba necesita al menos un motivo y una etiqueta")
        return

    _mutar_rotulos_bandeja(doc, {motivo: "  Algo   con tilde: acción ", etiqueta: ""})
    rot = doc["conversaciones"].get("rotulos", {})
    comprobar(rot.get(motivo) == "Algo con tilde: acción",
              "el rotulo de un motivo se guarda, con los espacios normalizados")
    comprobar(etiqueta not in rot, "un rotulo vacio no se guarda: es no tenerlo")
    cfg = _validar(TENANT, doc)
    comprobar(cfg.conversaciones.rotulos.get(motivo) == "Algo con tilde: acción",
              "y el documento valida con el mismo validador que usa el motor")

    lanza("una clave que no es motivo, etiqueta ni caso se rechaza",
          lambda: _mutar_rotulos_bandeja(documento_base(), {"no_existe_xyz": "Texto"}))
    lanza("un rotulo de mas de 60 caracteres se rechaza",
          lambda: _mutar_rotulos_bandeja(documento_base(), {motivo: "x" * 61}))

    # Reemplaza el mapa entero: mandarlo vacio borra los que habia.
    _mutar_rotulos_bandeja(doc, {})
    comprobar("rotulos" not in doc["conversaciones"], "un mapa vacio borra los rotulos")

    # Un huerfano que ya estaba en la base no impide cargar la config: el
    # schema no lo rechaza, para no trabar el guardado de quien borro el caso.
    huerfano = documento_base()
    huerfano["conversaciones"]["rotulos"] = {"clave_que_se_borro": "Viejo"}
    try:
        _validar(TENANT, huerfano)
        comprobar(True, "un rotulo huerfano no impide cargar la configuracion")
    except Exception as e:
        comprobar(False, f"un rotulo huerfano no impide cargar la configuracion -- {type(e).__name__}")


def prueba_rotulos_de_casos() -> None:
    """
    Un caso nuevo de /manual nace con su rotulo (29/10/2026): la persona
    escribe «Problema de TV», la clave es 'problema_de_tv', y lo escrito es
    como se lee. Y uno que se borra no deja el suyo colgado.
    """
    print("\n-- rotulos de casos nuevos --")
    doc = documento_base()
    casos = list(doc["manual"]["casos"])
    _mutar_casos_manual(doc, casos + ["problema_de_tv"])
    _fundir_rotulos_de_casos(doc, {"problema_de_tv": "Problema de TV"})
    rot = doc["conversaciones"].get("rotulos") or {}
    comprobar(rot.get("problema_de_tv") == "Problema de TV",
              "el caso nuevo se guarda con lo que la persona escribio")
    cfg = _validar(TENANT, doc)
    comprobar("problema_de_tv" not in claves_sin_rotulo(cfg)["casos"],
              "y ya no figura entre las claves sin rotulo")

    _mutar_casos_manual(doc, casos)
    _fundir_rotulos_de_casos(doc, {})
    comprobar("problema_de_tv" not in (doc["conversaciones"].get("rotulos") or {}),
              "al borrar el caso, su rotulo se va con el")

    lanza("por esta puerta no se rotula algo que no es un caso",
          lambda: _fundir_rotulos_de_casos(documento_base(), {"no_es_caso_xyz": "Algo"}))

    sin = documento_base()
    sin["conversaciones"]["rotulos"] = {}
    faltan = claves_sin_rotulo(_validar(TENANT, sin))
    comprobar(sum(len(v) for v in faltan.values()) > 0,
              "sin rotulos, claves_sin_rotulo las cuenta todas")


def prueba_respuestas_rapidas() -> None:
    """
    Las respuestas rapidas de la Bandeja (11/11/2026): «/atajo» en el
    compositor inserta un texto guardado.

    Lo que se protege: que el atajo se normalice a lo que el compositor
    compara (sin barra, en minusculas), que una fila a medio llenar no se
    pierda en silencio, que no haya dos con el mismo atajo, que el formato y
    el largo los valide el MISMO schema que carga el YAML, y que mandar la
    lista vacia las borre.
    """
    print("\n-- respuestas rapidas de la Bandeja --")
    doc = documento_base()
    _mutar_respuestas_rapidas(doc, [
        {"atajo": " /Saludo ", "texto": "  Hola {nombre}, ¿en qué te ayudo? "},
        {"atajo": "", "texto": ""},          # renglon vacio del formulario
        {"atajo": "reinicio", "texto": "Desconectá el equipo 30 segundos."},
    ])
    rr = doc["conversaciones"].get("respuestas_rapidas", [])
    comprobar([r["atajo"] for r in rr] == ["saludo", "reinicio"],
              "el atajo se guarda sin barra y en minusculas; el renglon vacio se descarta")
    comprobar(rr[0]["texto"] == "Hola {nombre}, ¿en qué te ayudo?",
              "el texto se guarda recortado y con {nombre} intacto")
    cfg = _validar(TENANT, doc)
    comprobar([r.atajo for r in cfg.conversaciones.respuestas_rapidas] == ["saludo", "reinicio"],
              "y el documento valida con el mismo validador que usa el motor")

    lanza("texto sin atajo se rechaza en vez de perderse",
          lambda: _mutar_respuestas_rapidas(documento_base(), [{"atajo": "", "texto": "algo"}]))
    lanza("atajo sin texto se rechaza",
          lambda: _mutar_respuestas_rapidas(documento_base(), [{"atajo": "hola", "texto": " "}]))
    lanza("dos con el mismo atajo se rechazan (aunque difieran en mayusculas o barra)",
          lambda: _mutar_respuestas_rapidas(documento_base(), [
              {"atajo": "hola", "texto": "a"}, {"atajo": "/HOLA", "texto": "b"}]))

    for malo, que in (("con espacio", "un atajo con espacios"),
                      ("atención", "un atajo con tilde"),
                      ("x" * 31, "un atajo de mas de 30 caracteres"),
                      ("-hola", "un atajo que empieza con guion")):
        d = documento_base()
        _mutar_respuestas_rapidas(d, [{"atajo": malo, "texto": "t"}])
        lanza(f"{que} lo rechaza el schema", lambda d=d: _validar(TENANT, d))
    d = documento_base()
    # Texto de verdad y no "x" * 1001: una cadena repetida sin espacios la
    # agarra antes el barrido de credenciales, y la prueba pasaria por el
    # motivo equivocado.
    _mutar_respuestas_rapidas(d, [{"atajo": "largo", "texto": "Hola que tal. " * 80}])
    lanza("un texto de mas de 1000 caracteres lo rechaza el schema", lambda: _validar(TENANT, d))
    d = documento_base()
    _mutar_respuestas_rapidas(d, [{"atajo": f"r{i}", "texto": "t"} for i in range(101)])
    lanza("mas de 100 respuestas las rechaza el schema", lambda: _validar(TENANT, d))

    # Repetidas que entran por el YAML (no por el editor) tambien se rechazan.
    d = documento_base()
    d.setdefault("conversaciones", {})["respuestas_rapidas"] = [
        {"atajo": "hola", "texto": "a"}, {"atajo": "hola", "texto": "b"}]
    lanza("repetidas por el YAML las rechaza el schema", lambda: _validar(TENANT, d))

    _mutar_respuestas_rapidas(doc, [])
    comprobar("respuestas_rapidas" not in doc["conversaciones"],
              "una lista vacia borra las respuestas")
    comprobar(_validar(TENANT, documento_base()).conversaciones.respuestas_rapidas == [],
              "una empresa que nunca las configuro valida con la lista vacia")
    lanza("una fila que no es {atajo, texto} se rechaza",
          lambda: _mutar_respuestas_rapidas(documento_base(), ["solo texto"]))


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
    prueba_catalogo_dice_lo_que_hace_cada_una()
    prueba_agente_completo_desde_la_pantalla()
    prueba_banda_sin_gestion()
    prueba_origen_de_la_config()
    prueba_umbral_efectivo_de_la_banda()
    prueba_marcas_de_precio()
    prueba_rotulos_bandeja()
    prueba_rotulos_de_casos()
    prueba_respuestas_rapidas()

    print("\n" + "=" * 70)
    if fallos:
        print(f" {len(fallos)} FALLA(S):")
        for f in fallos:
            print(f"   - {f}")
        sys.exit(1)
    print(" Todo en orden.")
