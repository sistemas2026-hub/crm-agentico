# -*- coding: utf-8 -*-
"""
================================================================================
 EDITOR DE ROLES  -  crear/editar/borrar agentes desde la interfaz
================================================================================

`schema.py` valida; este modulo ESCRIBE. Separado a proposito: `cargar_config`
no necesita saber nada de edicion, y este archivo no necesita saber nada de
como se sirve por HTTP (eso vive en canales/api.py).

Alcance original (ver plan aprobado): solo se crean/editan/borran ROLES.
Crear una herramienta nueva -- conectar una API nueva, decidir sus filtros
verificados, su whitelist de campos -- era trabajo de codigo, a proposito:
esa superficie es sensible en seguridad y no encajaba en "editar desde una
pantalla SIN verificacion".

Extension (agosto 2026, ver aprobar_herramienta_propuesta mas abajo): el
asistente de configuracion guiada SI puede agregar una herramienta nueva
desde una pantalla -- pero no relaja la razon original, la resuelve de otra
forma. La preocupacion nunca fue "una pantalla", fue "sin verificar contra
la API real y sin que un humano lo revise". Esa doble garantia sigue
intacta: nada llega aca sin haber pasado por nucleo/herramientas/sondeo.py
(metodo del valor imposible, no promesas) Y sin que un ADMIN humano apruebe
el borrador exacto -- nunca el modelo escribe directo al catalogo real.

Escribe en la base, no en el YAML
---------------------------------
Antes este modulo reescribia `tenants/<slug>.config.yaml` con ruamel.yaml para
preservar sus comentarios. En el servidor eso no sirve para nada: esa carpeta
viaja DENTRO de la imagen del contenedor, y el motor ya no la lee -- lee
`asistente.tenant_config` (ver nucleo/config/fuente.py). Un editor que escribia
ahi guardaba sin error en un archivo desechable que nadie iba a consultar: el
cambio se veia en pantalla, no tenia efecto, y desaparecia en el siguiente
despliegue.

Asi que se escribe donde se lee. La fuente de verdad es una sola.

  asistente.tenant_config.config (JSONB)   lo que este modulo escribe
  tenants/<slug>.config.yaml               semilla de alta, ya no se toca

⚠️  El YAML del repositorio NO se entera de lo que se edita aqui. Es
deliberado -- no hay disco donde escribirlo que sobreviva al despliegue -- pero
tiene una consecuencia: volver a correr `cli/cargar_config.py` sobre ese YAML
PISA lo que el cliente haya cambiado desde la interfaz. Ese comando es para
dar de alta un tenant o para aplicar un cambio de esquema, no rutina.

Leer, mutar y escribir en UNA transaccion
-----------------------------------------
`_editar()` toma la fila con `for update` y no la suelta hasta guardar. Sin
eso, dos administradores guardando a la vez se pisan: los dos leen la misma
configuracion, cada uno le agrega SU rol, y el segundo en escribir borra el
rol del primero -- sin error y sin rastro, porque cada uno escribe un
documento completo y valido.

Validar antes de escribir
--------------------------
El documento se muta en memoria y ESE resultado pasa por el mismo camino que
`cargar_config` (barrido de secretos + `TenantConfig(**...)`). Solo si valida
se escribe. Si no valida se lanza `ErrorEdicion` con TODOS los problemas
juntos, y como la excepcion sale de la transaccion, la base queda intacta.

Lo que se guarda es el volcado del modelo ya validado, no el diccionario
crudo: la misma forma canonica que escribe `cli/cargar_config.py`, para que
comparar ambas versiones siga siendo posible.
================================================================================
"""

from __future__ import annotations

import copy
import json
import os
import re
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from .schema import RE_NOMBRE_REF, TenantConfig, _barrer_secretos

_RE_NOMBRE_ROL = re.compile(r"^[a-z][a-z0-9_]{1,29}$")

# Las claves de primer nivel que ALGUNA funcion de este modulo escribe, o sea
# lo que una persona puede cambiar desde la interfaz sin tocar el YAML.
#
# Vive aca y no en cli/cargar_config.py a proposito: esa lista existe para
# que cargar el archivo encima de la base no borre en silencio lo que alguien
# edito desde una pantalla, y estaba escrita a mano en el CLI con un
# comentario que pedia acordarse de actualizarla. No se actualizo: cuando se
# agregaron 'planes_venta', 'localidades', 'variables_tenant' y
# 'manual.casos' quedaron fuera, y la guarda daba por bueno un cambio que
# habria borrado 6 planes curados y 128 localidades sincronizadas sin decir
# una palabra (medido el 23/08/2026, antes de que alguien lo pisara).
#
# Poniendola junto a los mutadores, quien agregue uno la ve. Es el mismo
# criterio que TenantConfig.SINCRONIZADOS: la declaracion vive donde esta el
# codigo que la vuelve necesaria.
SECCIONES_EDITABLES = (
    "roles",              # _mutar_crear / _mutar_editar / _mutar_borrar
    "canales",            # _mutar_canal_whatsapp
    "identidad",          # _mutar_identidad_descripcion
    "persona",            # _mutar_persona
    "herramientas",       # _mutar_plazo_visita_tecnica, _mutar_agregar_herramienta
    "planes_venta",       # _mutar_planes_venta
    "localidades",        # _mutar_localidades
    "variables_tenant",   # _mutar_variable_tenant / _mutar_borrar_variable_tenant
    "manual",             # _mutar_casos_manual
    # 'llm' por _mutar_tarifa y _mutar_saldo_proveedor; 'limites' por
    # _mutar_tope_gasto. Faltaban, y paso exactamente lo que este comentario
    # anunciaba: el 05/09/2026 una carga del YAML borro la tarifa de DeepSeek
    # y el endpoint de saldo -- configuracion que solo existe en la base, que
    # costo medir contra la facturacion real, y que nadie escribio en el
    # archivo porque no se edita ahi.
    #
    # Sin la seccion en esta lista, el cargador ni siquiera avisa: no sabe que
    # ahi hay algo que solo la interfaz escribe.
    "llm",                # _mutar_tarifa / _mutar_saldo_proveedor
    "limites",            # _mutar_tope_gasto
)


class ErrorEdicion(ValueError):
    pass


# =============================================================================
#  VALIDACION Y ESCRITURA
# =============================================================================

def commits_sin_empujar() -> int:
    """Cuantos commits locales todavia no estan en el remoto.

    Es la comprobacion mas barata que detecta el orden invertido entre codigo
    y configuracion (ver el bloque que la usa). No mira QUE campos trae la
    config: mira si este codigo ya llego a donde va a leerla.

    Devuelve 0 ante cualquier duda -- sin git, sin remoto configurado, o con
    el comando fallando. Una guarda de conveniencia no puede ser la razon por
    la que no se pueda cargar una configuracion; la que si aborta de verdad es
    la de perdidas, que compara contra la base.
    """
    import subprocess
    try:
        salida = subprocess.run(
            ["git", "rev-list", "--count", "@{u}..HEAD"],
            cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=10)
    except Exception:                                    # noqa: BLE001
        return 0
    if salida.returncode != 0:
        return 0
    try:
        return int((salida.stdout or "0").strip())
    except ValueError:
        return 0


def commits_atrasados() -> int | None:
    """Cuantos commits del remoto todavia no estan en esta copia local.

    Caso simetrico e inverso a commits_sin_empujar(): ese detecta codigo local
    que la config podria usar antes de que llegue a produccion; este detecta
    lo contrario -- una copia VIEJA escribiendo una config que ya no coincide
    con el schema que el motor desplegado usa hoy.

    Encontrado en la auditoria de Fase #20.1-20.3 (04-05/09/2026): asi
    volvieron 'llm.tarifas' / 'limites.mensaje_al_alcanzar_tope' / 'llm.saldo'
    a produccion -- campos que un schema mas viejo ya no reconoce, escritos
    por una copia atrasada que todavia los validaba como buenos contra SU
    propio 'schema.py'.

    A diferencia de commits_sin_empujar() -- que degrada a 0 (permite) ante
    cualquier duda porque la guarda de perdidas de cada puerta la respalda
    igual -- esta NO tiene ningun respaldo equivalente: nada mas sabe si un
    campo sigue siendo valido para el schema desplegado. Por eso, si no se
    puede determinar el estado real (sin git, sin upstream configurado, el
    comando falla), devuelve None -- y None se trata como bloqueo, nunca
    como 'esta alineado'.
    """
    import subprocess
    try:
        salida = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..@{u}"],
            cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=10)
    except Exception:                                    # noqa: BLE001
        return None
    if salida.returncode != 0:
        return None
    try:
        return int((salida.stdout or "").strip())
    except ValueError:
        return None


def problemas_de_alineacion_git() -> list[str]:
    """
    Problemas de alineacion entre esta copia y el remoto, en las DOS
    direcciones -- lista vacia si esta alineada.

    Centraliza la deteccion (Fase #20.6.4) para que cargar_config.py y
    _editar() -- las dos puertas que escriben tenant_config -- compartan UNA
    sola implementacion en vez de dos copias que hay que acordarse de
    mantener iguales. No decide COMO reportar el problema ni si bloquea: eso
    lo arma cada puerta con su propia excepcion, porque una corre como CLI
    (SystemExit tiene sentido ahi) y la otra corre dentro del proceso
    servido, donde SystemExit lo tumbaria entero.
    """
    adelante = commits_sin_empujar()
    atras = commits_atrasados()

    problemas: list[str] = []
    if adelante:
        problemas.append(
            f"esta copia tiene {adelante} commit(s) locales que todavia no "
            f"llegaron al remoto -- si esta config usa un campo del esquema "
            f"que solo existe en esos commits, el motor desplegado no va a "
            f"poder leerla.")
    if atras is None:
        problemas.append(
            "no se pudo determinar si esta copia esta al dia con el remoto "
            "(sin git, sin upstream configurado, o el comando fallo) -- ante "
            "la duda, no se procede.")
    elif atras:
        problemas.append(
            f"esta copia esta {atras} commit(s) atras del remoto -- si un "
            f"commit mas reciente cambio el esquema (por ejemplo, quito un "
            f"campo que esta copia todavia declara valido), escribir esta "
            f"config puede reintroducir en produccion algo que el codigo "
            f"desplegado ya no reconoce.")
    return problemas


def _validar(tenant: str, crudo: dict) -> TenantConfig:
    """Mismo camino que cargar_config(), pero sobre el documento en memoria."""
    secretos = _barrer_secretos(crudo)
    if secretos:
        raise ErrorEdicion(
            f"{tenant}: hay valores con pinta de credencial:\n  - "
            + "\n  - ".join(secretos))

    try:
        return TenantConfig(**crudo)
    except ValidationError as e:
        lineas = [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}"
                  for err in e.errors()]
        raise ErrorEdicion(
            f"{tenant}: {len(lineas)} problema(s) de configuracion:\n  - "
            + "\n  - ".join(lineas)) from None


def _editar(tenant: str, mutar: Callable[[dict], None]) -> TenantConfig:
    """
    Lee la configuracion vigente, le aplica 'mutar', valida el resultado y lo
    guarda -- todo dentro de la misma transaccion, con la fila bloqueada.

    Cualquier excepcion (la que lance 'mutar' o la de validacion) sale de la
    transaccion sin escribir: nucleo/persistencia/db.py hace rollback.
    """
    from nucleo.persistencia.db import sesion     # perezoso: evita ciclo

    # MISMA TRAMPA QUE cargar_config.py, POR LA OTRA PUERTA.
    #
    # Escribir configuracion con campos que el codigo desplegado no conoce deja
    # a produccion con una config que su propio motor rechaza (los modelos
    # declaran extra="forbid": un campo desconocido no se ignora, tumba el
    # archivo entero) y el asistente deja de atender.
    #
    # La guarda de cargar_config.py cubria el camino del YAML. Este es el otro:
    # correr el editor desde una copia local -- una prueba, un script -- contra
    # la base de PRODUCCION. Paso dos veces el mismo dia, la segunda por aca.
    #
    # En produccion esto no dispara nunca: el editor corre dentro del codigo ya
    # desplegado, y ahi no hay repositorio git, asi que la comprobacion
    # devuelve 0/None y no molesta. Solo aparece donde existe el desfase.
    #
    # Fase #20.6.4: ademas del caso de arriba (copia ADELANTADA), cubre el
    # simetrico -- copia ATRASADA -- via problemas_de_alineacion_git(), que
    # tambien usa cargar_config.py. Una sola implementacion para las dos
    # puertas.
    if not os.environ.get("PERMITIR_CONFIG_SIN_DESPLEGAR"):
        problemas = problemas_de_alineacion_git()
        if problemas:
            raise ErrorEdicion(
                "esta copia no esta alineada con el remoto:\n  - "
                + "\n  - ".join(problemas) +
                "\n\nPrimero sincronizar el codigo (git pull / git push segun "
                "corresponda), despues editar. Si sabes que esta edicion no "
                "se ve afectada: PERMITIR_CONFIG_SIN_DESPLEGAR=1")

    with sesion(tenant) as (cur, org):
        cur.execute("""select config, config_version
                       from asistente.tenant_config
                       where organization_id = %s
                       for update""", (org,))
        fila = cur.fetchone()
        if not fila or not fila["config"]:
            raise ErrorEdicion(
                f"'{tenant}' no tiene configuracion cargada en la base, asi que "
                f"no hay nada que editar. Cargarla primero con: "
                f"py -3.13 cli/cargar_config.py tenants/{tenant}.config.yaml")

        # Copia independiente a proposito: 'mutar' cambia dicts anidados en el
        # lugar (ej. _mutar_editar hace rol["descripcion"] = ...). Sin copiar,
        # 'doc' y 'fila["config"]' son el MISMO objeto, así que mutar 'doc'
        # tambien corrompe el "antes" que se usa mas abajo para detectar
        # cambios -- el resultado quedaba comparado contra si mismo y
        # 'datos == fila["config"]' daba True siempre, así que ninguna edicion
        # a un rol EXISTENTE llegaba a guardarse (crear_rol no lo sufria por
        # casualidad: el rol nuevo no traia los campos con default que Pydantic
        # agrega al validar, y esa diferencia de claves bastaba para que el
        # 'if' de abajo diera False).
        doc = copy.deepcopy(fila["config"])
        mutar(doc)
        config = _validar(tenant, doc)
        datos = config.model_dump(mode="json")

        # Igual que cli/cargar_config.py: si el contenido no cambio, no se sube
        # la version. Asi 'config_version' cuenta cambios reales y no clics en
        # el boton de guardar.
        if datos == fila["config"]:
            print(f"[config] {tenant}: sin cambios (v{fila['config_version']})")
            return config

        cur.execute("""update asistente.tenant_config
                       set config = %s,
                           config_version = config_version + 1,
                           actualizado_en = now()
                       where organization_id = %s
                       returning config_version""",
                    (json.dumps(datos), org))
        version = cur.fetchone()["config_version"]

    print(f"[config] {tenant}: v{version} guardada desde el editor")
    return config


def _validar_nombre_rol(nombre: str) -> None:
    if not _RE_NOMBRE_ROL.match(nombre):
        raise ErrorEdicion(
            f"'{nombre}': el nombre debe ser minuscula, empezar con letra y "
            f"usar solo letras/numeros/guion bajo (2-30 caracteres)")


# =============================================================================
#  CATALOGO  -  lo que la UI necesita para armar el formulario
# =============================================================================

def catalogo_herramientas(config: TenantConfig) -> list[dict]:
    """
    Por herramienta: de que tipo es, si es de verificacion (sin whitelist de
    campos), y que campos ya declaro CUALQUIER rol existente para ella -- no
    hay catalogo de campos de las APIs externas en ningun lado del sistema,
    asi que lo unico confiable para ofrecer como checklist es lo que ya paso
    por un humano que leyo la respuesta real.
    """
    conocidos: dict[str, set[str]] = {}
    for rol in config.roles.values():
        for herr, campos in rol.campos_permitidos.items():
            conocidos.setdefault(herr, set()).update(campos)

    return [
        {
            "nombre": h.nombre,
            "descripcion": h.descripcion.strip(),
            "tipo": h.tipo,
            "verifica_identidad": h.verifica_identidad,
            "campos_conocidos": sorted(conocidos.get(h.nombre, set())),
        }
        for h in config.herramientas
    ]


# =============================================================================
#  MUTACIONES  -  sobre el documento, sin saber de donde salio
# =============================================================================
#  Separadas de la transaccion a proposito: son funciones puras sobre un dict
#  y se pueden probar sin base de datos (tests/test_editor_config.py).

def _comprobar_nadie_se_queda_sin_roles(doc: dict) -> None:
    """
    Una herramienta cuyo ultimo rol se va queda sin nadie que pueda usarla, y
    el esquema la rechaza (roles_permitidos exige al menos uno).

    Se avisa aca y no se deja llegar al validador porque ahi el error sale como
    'herramientas.8.roles_permitidos: List should have at least 1 item': indica
    una posicion en una lista que el administrador no ve y no dice que hacer.
    El caso llega solo -- desmarcar en un rol la unica herramienta que ese rol
    tenia en exclusiva -- y desde el formulario parece un cambio inocente.
    """
    huerfanas = [h.get("nombre") for h in doc.get("herramientas", [])
                 if not h.get("roles_permitidos")]
    if huerfanas:
        raise ErrorEdicion(
            f"{', '.join(huerfanas)}: se quedaria(n) sin ningun rol que "
            f"pueda(n) usarla(s), y una herramienta que nadie puede consultar "
            f"no se puede guardar. Asignala a otro rol antes de quitarsela a "
            f"este.")


def _aplicar_herramientas(doc: dict, nombre_rol: str, herramientas: list[dict],
                          campos_permitidos_out: dict, anterior: set[str] | None = None) -> None:
    """
    Muta 'herramientas' del documento: agrega nombre_rol a roles_permitidos de
    cada herramienta seleccionada (si no estaba), y lo quita de las que ya no
    estan seleccionadas. Documental/defensa en profundidad -- el motor autoriza
    por Rol.puede_consultar, no por esto -- pero dejarlo desactualizado seria
    mentir en la config.

    'anterior' es el 'puede_consultar' del rol ANTES de esta edicion. Solo se
    le quita 'nombre_rol' a una herramienta si de verdad estaba ahi -- nunca
    por una herramienta que el rol nunca ofrecio en su catalogo, aunque
    'roles_permitidos' la apunte a este rol por otro motivo. Caso real: las
    herramientas de uso interno de escalamiento (nucleo/seguimiento/
    escalamiento.py, ej. 'crear_caso_soporte') no las llama ningun modelo, asi
    que ningun rol las tiene en 'puede_consultar' -- pero el esquema exige
    'roles_permitidos' con al menos un elemento, asi que quedan apuntando a un
    rol cualquiera (ej. 'administracion') solo para cumplir esa cota minima.
    Sin este chequeo, CUALQUIER guardado de ese rol las desvinculaba (no
    estaban entre las seleccionadas del formulario, que ni las ofrece) y el
    validador rechazaba el guardado entero por dejarlas huerfanas.
    """
    anterior = anterior or set()
    seleccionadas = {h["nombre"] for h in herramientas}
    for herr in doc.get("herramientas", []):
        nombre_herr = herr.get("nombre")
        permitidos = herr.setdefault("roles_permitidos", [])
        ya_esta = nombre_rol in permitidos
        if nombre_herr in seleccionadas and not ya_esta:
            permitidos.append(nombre_rol)
        elif nombre_herr not in seleccionadas and ya_esta and nombre_herr in anterior:
            permitidos.remove(nombre_rol)

    for h in herramientas:
        campos = h.get("campos_permitidos") or []
        if campos:
            campos_permitidos_out[h["nombre"]] = list(campos)


def _mutar_crear(doc: dict, nombre: str, area: str | None, cargo: str | None,
                 descripcion: str, orientado_a: str, herramientas: list[dict]) -> None:
    if nombre in doc.get("roles", {}):
        raise ErrorEdicion(f"ya existe un rol llamado '{nombre}'")

    campos_permitidos: dict = {}
    _aplicar_herramientas(doc, nombre, herramientas, campos_permitidos)

    nuevo_rol = {
        "descripcion": descripcion,
        "orientado_a": orientado_a,
        "puede_consultar": [h["nombre"] for h in herramientas],
        "campos_permitidos": campos_permitidos,
    }
    if area:
        nuevo_rol["area"] = area
    if cargo:
        nuevo_rol["cargo"] = cargo
    doc.setdefault("roles", {})[nombre] = nuevo_rol
    _comprobar_nadie_se_queda_sin_roles(doc)


def _mutar_editar(doc: dict, nombre: str, area: str | None, cargo: str | None,
                  descripcion: str, orientado_a: str, herramientas: list[dict]) -> None:
    if nombre not in doc.get("roles", {}):
        raise ErrorEdicion(f"el rol '{nombre}' no existe")

    anterior = set(doc["roles"][nombre].get("puede_consultar") or [])
    campos_permitidos: dict = {}
    _aplicar_herramientas(doc, nombre, herramientas, campos_permitidos, anterior)

    rol = doc["roles"][nombre]
    rol["descripcion"] = descripcion
    rol["area"] = area
    rol["cargo"] = cargo
    rol["orientado_a"] = orientado_a
    rol["puede_consultar"] = [h["nombre"] for h in herramientas]
    rol["campos_permitidos"] = campos_permitidos
    _comprobar_nadie_se_queda_sin_roles(doc)


def _mutar_persona(doc: dict, nombre_asistente: str, tono: str,
                   longitud_respuesta: str, instrucciones_adicionales: str) -> None:
    """
    Como se presenta y como escribe el asistente.

    No toca permisos: ni que herramientas hay, ni que campos devuelve cada
    una. Por eso es lo primero que se puede dejar en manos del cliente sin
    revisar nada -- lo peor que puede hacer aca es que su asistente hable
    raro, no que muestre un dato que no debia.
    """
    doc.setdefault("persona", {}).update({
        "nombre_asistente": nombre_asistente,
        "tono": tono,
        "longitud_respuesta": longitud_respuesta,
        "instrucciones_adicionales": instrucciones_adicionales,
    })


NOMBRE_HERRAMIENTA_VISITA_TECNICA = "agendar_visita_tecnica"


def _mutar_plazo_visita_tecnica(doc: dict, dias: int) -> None:
    """
    Cuantos dias de plazo tiene un ticket de visita tecnica antes de su
    fecha_final (ver 'fechas_automaticas' en schema.py y motor.py, que hace
    la cuenta real en el momento de la llamada). Editable sin tocar codigo
    ni pedirmelo: mismo criterio de riesgo bajo que _mutar_persona -- no
    toca permisos, solo cuanto tiempo se promete para resolver el caso.
    """
    for h in doc.get("herramientas", []):
        if h.get("nombre") == NOMBRE_HERRAMIENTA_VISITA_TECNICA:
            h.setdefault("fechas_automaticas", {})["fecha_final"] = dias
            return
    raise ErrorEdicion(
        f"la herramienta '{NOMBRE_HERRAMIENTA_VISITA_TECNICA}' no existe en "
        f"el catalogo -- no hay donde guardar el plazo.")


def _mutar_identidad_descripcion(doc: dict, descripcion: str) -> None:
    """
    Que servicios y planes ofrece la empresa, en prosa -- se inyecta SIEMPRE
    en el prompt de cualquier rol (ver nucleo/recuperacion/prompt.py), a
    diferencia del corpus (RAG, solo si la pregunta matchea). No toca
    permisos ni roles, mismo criterio de riesgo bajo que _mutar_persona.
    """
    doc.setdefault("identidad", {})["descripcion"] = descripcion


def _mutar_flujo_derivacion(doc: dict, destinos: list[str], atiende: dict) -> None:
    """
    Que agentes son destino del router, y que atiende cada uno.

    Es lo que hace editable el diagrama de /agentes/flujo: 'destinos' va a
    'areas_destino' de la herramienta que declara 'deriva_rol', y 'atiende'
    a cada rol. El prompt del router NO se toca -- su tabla de enrutamiento
    se genera desde esto (nucleo/recuperacion/prompt.py::_tabla_de_derivacion).

    Se valida contra el documento, no contra el modelo ya cargado: un destino
    que no existe como rol, o que apunta al propio router, dejaria el
    diagrama mostrando una flecha que el motor nunca podria seguir.
    """
    roles = doc.get("roles") or {}
    herramientas = doc.get("herramientas") or []

    deriva = next((h for h in herramientas if h.get("deriva_rol")), None)
    if deriva is None:
        raise ErrorEdicion(
            "este tenant no tiene ninguna herramienta de derivacion "
            "(deriva_rol), asi que no hay flujo que editar todavia.")

    # Un destino tiene que existir y atender al CLIENTE: derivar una
    # conversacion de WhatsApp a un rol interno (soporte, administracion)
    # pondria a un agente que habla en tercera persona del cliente a
    # hablarle DE FRENTE a ese cliente.
    #
    # No se rechaza que un destino tenga a su vez la herramienta de derivar:
    # los especialistas la tienen a proposito, para pasarse una conversacion
    # entre ellos cuando el router se equivoco de area. La auto-derivacion
    # (derivar a donde ya se esta) la resuelve el motor en ejecucion --
    # nucleo/modelo/motor.py::_ejecutar_derivacion la detecta y no hace nada.
    for destino in destinos:
        if destino not in roles:
            raise ErrorEdicion(f"'{destino}' no es un agente de este tenant.")
        if (roles[destino].get("orientado_a") or "colaborador") != "cliente_final":
            raise ErrorEdicion(
                f"'{destino}' es un agente interno (habla con un colaborador, "
                f"no con el cliente): no puede recibir una conversacion "
                f"derivada desde WhatsApp.")

    deriva["areas_destino"] = list(dict.fromkeys(destinos))

    for nombre_rol, texto in (atiende or {}).items():
        if nombre_rol not in roles:
            raise ErrorEdicion(f"'{nombre_rol}' no es un agente de este tenant.")
        roles[nombre_rol]["atiende"] = (texto or "").strip()


def _mutar_casos_manual(doc: dict, casos: list[str]) -> None:
    """
    La lista de tipos de caso con que se clasifica cada conversacion
    ('manual.casos': internet_lento, sin_senal_tv, consulta_saldo, ...). El
    modelo elige uno por turno, acotado por enum -- ver
    nucleo/seguimiento/escalamiento.py -- y queda guardado en la
    conversacion (supabase/202608180923_caso_conversacion.sql).

    Editable desde la interfaz a proposito: que casos atiende una empresa es
    dato del negocio, cambia con el uso, y pedir una sesion de desarrollo
    para agregar "instalacion_nueva" a una lista es exactamente lo que este
    editor existe para evitar.

    Riesgo bajo pero NO nulo, y por eso las dos guardas de abajo: la lista es
    el enum que ve el modelo, y hay otras partes de la config que apuntan a
    un caso por nombre. Borrar el caso equivocado no rompe nada de forma
    visible -- deja de dispararse un automatismo y nadie se entera.
    """
    casos_limpios: list[str] = []
    for caso in casos:
        caso = (caso or "").strip()
        if not caso:
            continue
        if not _RE_NOMBRE_ROL.match(caso):
            raise ErrorEdicion(
                f"'{caso}': el nombre del caso debe ser minuscula, empezar "
                f"con letra y usar solo letras/numeros/guion bajo (2-30 "
                f"caracteres). Ej: 'instalacion_nueva'.")
        if caso in casos_limpios:
            raise ErrorEdicion(f"'{caso}' esta repetido en la lista.")
        casos_limpios.append(caso)

    if not casos_limpios:
        raise ErrorEdicion(
            "la lista de casos no puede quedar vacia: es el enum con el que "
            "el asistente clasifica cada conversacion.")

    # 'otro' es la salida segura del enum: sin ella, una conversacion que no
    # encaja en ningun caso obliga al modelo a elegir uno que no corresponde,
    # y la clasificacion pasa de "no se sabe" a "dice algo falso".
    if "otro" not in casos_limpios:
        raise ErrorEdicion(
            "la lista tiene que incluir 'otro': es la opcion que usa el "
            "asistente cuando ninguna de las demas encaja. Sin ella se ve "
            "obligado a elegir mal.")

    # Un caso que otra parte de la config referencia por nombre no se puede
    # borrar desde aca. Hoy solo el agendamiento automatico
    # ('escalamiento.agendamiento_automatico': sin_senal_tv -> agendar la
    # visita), y su sintoma al borrarlo seria silencioso: el piloto deja de
    # dispararse, sin error, sin log, y las visitas vuelven a depender de que
    # alguien las cree a mano.
    referenciados = set((doc.get("escalamiento") or {})
                        .get("agendamiento_automatico") or {})
    huerfanos = sorted(referenciados - set(casos_limpios))
    if huerfanos:
        raise ErrorEdicion(
            f"no se puede quitar {', '.join(huerfanos)}: el agendamiento "
            f"automatico depende de ese caso. Primero hay que desactivarlo "
            f"en la configuracion del escalamiento.")

    doc.setdefault("manual", {})["casos"] = casos_limpios


def _mutar_variable_tenant(doc: dict, nombre: str, valor: str) -> None:
    """
    Guarda un valor NO secreto que varia por empresa (ej. el subdominio de
    SmartOLT) -- ver TenantConfig.variables_tenant en schema.py. Genero a
    proposito: este archivo no sabe que integraciones existen, solo que
    'nombre' tiene que matchear el patron de referencia (RE_NOMBRE_REF,
    revalidado por Pydantic al final de _editar) para poder ser referenciado
    desde 'Herramienta.base_url_ref'.
    """
    doc.setdefault("variables_tenant", {})[nombre] = valor


def _mutar_borrar_variable_tenant(doc: dict, nombre: str) -> None:
    (doc.get("variables_tenant") or {}).pop(nombre, None)


def _mutar_canal_whatsapp(doc: dict, activo: bool, numero_visible: str | None) -> None:
    """
    Prender/apagar el canal y el numero que se muestra en la pantalla de
    ajustes ("estas atendiendo desde el 300...").

    NO toca los '*_ref' (phone_number_id_ref, token_ref, etc): esos son los
    NOMBRES de los secretos y ya vienen declarados desde el alta del tenant,
    siguiendo la convencion de la plataforma (WHATSAPP_PHONE_NUMBER_ID...).
    Lo que carga el cliente desde la interfaz son los VALORES, que van
    aparte, cifrados, en asistente.tenant_secrets -- nunca en este documento
    (ver nucleo/seguridad/secretos.py).

    Pydantic exige que los cuatro refs indispensables esten DECLARADOS para
    poner 'activo: true' (CanalWhatsApp._activo_exige_lo_indispensable), pero
    eso no confirma que haya un VALOR cargado para cada uno -- ese chequeo es
    de la pantalla, no de este documento, porque este documento nunca ve
    valores de secretos.
    """
    doc.setdefault("canales", {}).setdefault("whatsapp", {})
    doc["canales"]["whatsapp"]["activo"] = activo
    doc["canales"]["whatsapp"]["numero_visible"] = numero_visible or None


def _mutar_borrar(doc: dict, nombre: str) -> None:
    if nombre not in doc.get("roles", {}):
        raise ErrorEdicion(f"el rol '{nombre}' no existe")

    destino_escalamiento = (doc.get("escalamiento") or {}).get("destino_rol")
    if destino_escalamiento == nombre:
        raise ErrorEdicion(
            f"'{nombre}' es el destino de escalamiento (escalamiento.destino_rol). "
            f"Cambia ese destino antes de borrar el rol.")

    del doc["roles"][nombre]

    for herr in doc.get("herramientas", []):
        permitidos = herr.get("roles_permitidos", [])
        if nombre in permitidos:
            permitidos.remove(nombre)

    overrides = (doc.get("llm") or {}).get("overrides")
    if overrides:
        for clave in [c for c in overrides if c == f"rol:{nombre}"]:
            del overrides[clave]

    # Y de las areas que lo precargaban. Sin esto, borrar un agente desde la
    # pantalla dejaba un area apuntando a un rol que ya no existe: el
    # validador rechazaba la config entera con "precarga el agente inexistente
    # 'x'", o sea el borrado fallaba por una referencia que el propio borrado
    # tenia que limpiar. Un area que se queda sin agentes es valida (ver
    # AreaDeTrabajo): sigue sirviendo para organizar gente aunque no le de
    # capacidades, asi que se vacia, no se borra.
    for area in doc.get("areas", []):
        agentes = area.get("agentes", [])
        if nombre in agentes:
            agentes.remove(nombre)

    _comprobar_nadie_se_queda_sin_roles(doc)


# =============================================================================
#  CREAR / EDITAR / BORRAR
# =============================================================================

def crear_rol(tenant: str, nombre: str, area: str | None, cargo: str | None,
              descripcion: str, orientado_a: str,
              herramientas: list[dict]) -> TenantConfig:
    _validar_nombre_rol(nombre)
    return _editar(tenant, lambda doc: _mutar_crear(
        doc, nombre, area, cargo, descripcion, orientado_a, herramientas))


def editar_rol(tenant: str, nombre: str, area: str | None, cargo: str | None,
               descripcion: str, orientado_a: str,
               herramientas: list[dict]) -> TenantConfig:
    return _editar(tenant, lambda doc: _mutar_editar(
        doc, nombre, area, cargo, descripcion, orientado_a, herramientas))


def borrar_rol(tenant: str, nombre: str) -> TenantConfig:
    return _editar(tenant, lambda doc: _mutar_borrar(doc, nombre))


def guardar_persona(tenant: str, nombre_asistente: str, tono: str,
                    longitud_respuesta: str,
                    instrucciones_adicionales: str) -> TenantConfig:
    return _editar(tenant, lambda doc: _mutar_persona(
        doc, nombre_asistente, tono, longitud_respuesta,
        instrucciones_adicionales))


def guardar_identidad_descripcion(tenant: str, descripcion: str) -> TenantConfig:
    return _editar(tenant, lambda doc: _mutar_identidad_descripcion(doc, descripcion))


def guardar_plazo_visita_tecnica(tenant: str, dias: int) -> TenantConfig:
    if dias < 1 or dias > 30:
        raise ErrorEdicion("el plazo tiene que ser entre 1 y 30 dias.")
    return _editar(tenant, lambda doc: _mutar_plazo_visita_tecnica(doc, dias))


def guardar_canal_whatsapp(tenant: str, activo: bool,
                           numero_visible: str | None) -> TenantConfig:
    return _editar(tenant, lambda doc: _mutar_canal_whatsapp(doc, activo, numero_visible))


def guardar_flujo_derivacion(tenant: str, destinos: list[str],
                             atiende: dict) -> TenantConfig:
    return _editar(tenant, lambda doc: _mutar_flujo_derivacion(doc, destinos, atiende))


def guardar_casos_manual(tenant: str, casos: list[str]) -> TenantConfig:
    return _editar(tenant, lambda doc: _mutar_casos_manual(doc, casos))


def guardar_variable_tenant(tenant: str, nombre: str, valor: str) -> TenantConfig:
    if not RE_NOMBRE_REF.match(nombre):
        raise ErrorEdicion(
            f"'{nombre}': el nombre de la variable debe ser MAYUSCULAS, "
            f"empezar con letra y usar solo letras/numeros/guion bajo "
            f"(ej. SMARTOLT_SUBDOMINIO) -- es como se referencia despues "
            f"desde 'base_url_ref' en el catalogo de herramientas.")
    if not valor or not valor.strip():
        raise ErrorEdicion("falta el valor.")
    return _editar(tenant, lambda doc: _mutar_variable_tenant(doc, nombre, valor.strip()))


def borrar_variable_tenant(tenant: str, nombre: str) -> TenantConfig:
    return _editar(tenant, lambda doc: _mutar_borrar_variable_tenant(doc, nombre))


def _mutar_planes_venta(doc: dict, planes: list[dict]) -> None:
    """
    Reemplaza ENTERA la lista curada de planes que 'ventas' ofrece a un
    prospecto nuevo -- ver PlanVenta/TenantConfig.planes_venta en
    schema.py. Reemplazo completo y no un merge incremental a proposito:
    la pantalla manda el estado completo de los checkboxes en cada
    guardado (que planes quedaron tildados, con que localidades cada
    uno), asi que "lo que llega" ya ES la lista final -- un merge
    complicaria sin necesidad la logica de "destildar uno para sacarlo".
    """
    doc["planes_venta"] = planes


def guardar_planes_venta(tenant: str, planes: list[dict]) -> TenantConfig:
    for p in planes:
        if not (p.get("nombre_wisphub") or "").strip():
            raise ErrorEdicion("Cada plan necesita 'nombre_wisphub'.")
    return _editar(tenant, lambda doc: _mutar_planes_venta(doc, planes))


def _mutar_localidades(doc: dict, localidades: list[dict]) -> None:
    """
    Reemplaza ENTERO el catalogo localidad -> zona(s) -- ver
    TenantConfig.localidades/LocalidadZona en schema.py. Igual criterio
    que _mutar_planes_venta: lo produce nucleo/herramientas/localidades.py
    de punta a punta en cada sincronizacion, nunca un merge incremental.
    """
    from datetime import datetime, timezone
    doc["localidades"] = localidades
    doc["localidades_actualizado_en"] = datetime.now(timezone.utc).isoformat()


def guardar_localidades(tenant: str, localidades: list[dict]) -> TenantConfig:
    return _editar(tenant, lambda doc: _mutar_localidades(doc, localidades))


def aprobar_herramienta_propuesta(tenant: str, herramienta_propuesta: dict) -> TenantConfig:
    """
    Agrega al catalogo real una herramienta que vino de una propuesta ya
    aprobada por un ADMIN humano (ver nucleo/canales/api.py::
    aprobar_propuesta, el unico llamador -- nunca se invoca directo desde
    una conversacion). Ver el docstring de este archivo para por que esto
    no relaja la regla original de "crear una herramienta es trabajo de
    codigo": llega aca ya sondeada de verdad y ya aprobada por una persona.

    Rechaza si ya existe una herramienta con ese nombre -- una coincidencia
    de nombre en el borrador no debe pisar algo real. La validacion de
    FORMA (que 'herramienta_propuesta' tenga los campos correctos para su
    'tipo', que 'roles_permitidos' apunte a roles que existen) la hace
    _editar() al final, contra el mismo esquema que valida todo lo demas --
    si el borrador esta mal armado, el error sale aca y la propuesta queda
    aprobada pero sin poder escribirse (ver el llamador: no marca 'aprobada'
    hasta que esto no lance).
    """
    nombre = herramienta_propuesta.get("nombre")
    if not nombre:
        raise ErrorEdicion("El borrador no tiene 'nombre'.")
    return _editar(tenant, lambda doc: _mutar_agregar_herramienta(doc, herramienta_propuesta))


def _mutar_agregar_herramienta(doc: dict, herramienta_propuesta: dict) -> None:
    nombre = herramienta_propuesta["nombre"]
    existentes = {h.get("nombre") for h in doc.get("herramientas", [])}
    if nombre in existentes:
        raise ErrorEdicion(f"ya existe una herramienta llamada '{nombre}' en el catalogo.")
    doc.setdefault("herramientas", []).append(herramienta_propuesta)


def _mutar_tarifa(doc: dict, modelo: str, entrada: float, salida: float,
                  entrada_cache: float | None = None,
                  descuento: float | None = None,
                  ventanas: list | None = None) -> None:
    """Guarda cuanto cuesta un modelo, en USD por MILLON de tokens.

    Por millon porque asi lo publican los proveedores: guardar el numero como
    viene evita el error mas aburrido y mas caro de este dominio, que es un
    factor de mil metido al cargarlo.
    """
    tarifa = {"entrada": float(entrada), "salida": float(salida)}
    # Se omite si no se declara, en vez de copiar 'entrada': ausente significa
    # "cobrar todo como entrada nueva", que es el lado conservador. Guardarlo
    # igual al de entrada seria lo mismo en el calculo pero mentiria en la
    # pantalla -- diria que hay un precio de cache cargado cuando no lo hay.
    if entrada_cache is not None:
        tarifa["entrada_cache"] = float(entrada_cache)
    # El descuento y las ventanas son propiedad del PROVEEDOR y cambian sin
    # avisar (DeepSeek movio las suyas el 23/08/2026). Se conservan si no
    # vienen: cargar una tarifa nueva no deberia borrar el horario que alguien
    # configuro antes -- son dos cosas que se editan por separado.
    previa = ((doc.get("llm") or {}).get("tarifas") or {}).get(modelo) or {}
    if descuento is not None:
        tarifa["descuento_fuera_pico"] = float(descuento)
    elif previa.get("descuento_fuera_pico"):
        tarifa["descuento_fuera_pico"] = previa["descuento_fuera_pico"]
    if ventanas is not None:
        tarifa["ventanas_pico"] = ventanas
    elif previa.get("ventanas_pico"):
        tarifa["ventanas_pico"] = previa["ventanas_pico"]
    doc.setdefault("llm", {}).setdefault("tarifas", {})[modelo] = tarifa


def _mutar_borrar_tarifa(doc: dict, modelo: str) -> None:
    ((doc.get("llm") or {}).get("tarifas") or {}).pop(modelo, None)


def _mutar_tope_gasto(doc: dict, tope: float | None, mensaje: str | None) -> None:
    """El tope mensual de gasto, y que se le dice al cliente si se alcanza.

    None borra el tope. No es lo mismo que cero: cero seria 'frena siempre', y
    alguien que quiere sacar el limite escribiria justamente eso.
    """
    limites = doc.setdefault("limites", {})
    if tope is None:
        limites.pop("max_costo_usd_mes", None)
    else:
        limites["max_costo_usd_mes"] = float(tope)
    if mensaje is not None:
        limites["mensaje_al_alcanzar_tope"] = mensaje.strip()


def guardar_tarifa(tenant: str, modelo: str, entrada: float, salida: float,
                   entrada_cache: float | None = None,
                   descuento_fuera_pico: float | None = None,
                   ventanas_pico: list | None = None) -> TenantConfig:
    if not str(modelo or "").strip():
        raise ErrorEdicion("Falta la referencia del modelo (ej. 'deepseek:deepseek-v4-flash').")
    if entrada < 0 or salida < 0 or (entrada_cache is not None and entrada_cache < 0):
        raise ErrorEdicion("Una tarifa no puede ser negativa.")
    if descuento_fuera_pico is not None and not (0 <= descuento_fuera_pico <= 1):
        raise ErrorEdicion(
            "El descuento fuera de pico va de 0 a 1 (0.5 = mitad de precio).")
    return _editar(tenant, lambda d: _mutar_tarifa(
        d, modelo.strip(), entrada, salida, entrada_cache,
        descuento_fuera_pico, ventanas_pico))


def borrar_tarifa(tenant: str, modelo: str) -> TenantConfig:
    return _editar(tenant, lambda d: _mutar_borrar_tarifa(d, modelo))


def guardar_tope_gasto(tenant: str, tope: float | None,
                       mensaje: str | None = None) -> TenantConfig:
    if tope is not None and tope <= 0:
        raise ErrorEdicion(
            "El tope tiene que ser mayor que cero. Para sacar el limite, "
            "guardalo vacio -- un tope de 0 frenaria el asistente siempre.")
    return _editar(tenant, lambda d: _mutar_tope_gasto(d, tope, mensaje))


def _mutar_saldo_proveedor(doc: dict, url: str, auth_ref: str, campo: str,
                           tolerancia: float | None) -> None:
    """Donde preguntarle al proveedor cuanto saldo queda. Ver SaldoProveedor."""
    s = doc.setdefault("llm", {}).setdefault("saldo", {})
    s["url"] = url.strip()
    s["auth_ref"] = auth_ref.strip()
    s["campo"] = campo.strip()
    if tolerancia is not None:
        s["tolerancia"] = float(tolerancia)


def guardar_saldo_proveedor(tenant: str, url: str, auth_ref: str, campo: str,
                            tolerancia: float | None = None) -> TenantConfig:
    if url and not url.lower().startswith("https://"):
        raise ErrorEdicion(
            "La URL del saldo tiene que ser https: por ahi viaja la clave del "
            "proveedor.")
    return _editar(tenant, lambda d: _mutar_saldo_proveedor(
        d, url, auth_ref, campo, tolerancia))
