# -*- coding: utf-8 -*-
"""
================================================================================
 VALIDACION DE tenant.config.yaml
 Entregable 2 de 9. Agosto 2026.
================================================================================

Por que existe este archivo
---------------------------
La restriccion arquitectonica dice que dar de alta un ISP nuevo es escribir un
YAML, sin tocar codigo. Eso convierte al YAML en la superficie donde ocurren
los errores: un rol mal escrito, un filtro que la API no soporta, una clave
pegada por descuido. Sin validacion, esos errores se descubren en produccion
con un cliente adelante.

Este modulo los caza al cargar, no al ejecutar.

Las tres validaciones que no son de tipos
-----------------------------------------
1. NINGUN SECRETO. Los campos '*_ref' deben ser NOMBRES de variable de entorno
   o de Vault, no valores. Ademas se barre el archivo entero buscando cosas con
   pinta de credencial.

2. FILTROS VERIFICADOS vs IGNORADOS. La API de WispHub ignora filtros en
   SILENCIO: pides ?zona=3 y te devuelve los 7.272 clientes como si fuera la
   respuesta filtrada. No da error. Por eso el catalogo separa los que pasaron
   la prueba del valor imposible de los que se sabe que la API ignora, y este
   modulo verifica que un filtro no este en las dos listas y que no se pueda
   agrupar por algo que no esta verificado.

   Un filtro ignorado no se "intenta igual": se rechaza con el motivo. Un total
   preciso que responde otra pregunta es peor que un error.

3. COHERENCIA DE ROLES. Una herramienta no puede permitir un rol que no existe,
   y un rol no puede declarar campos de una herramienta que no puede usar.

Uso
---
    from nucleo.config import cargar_config
    cfg = cargar_config("tenants/<slug>.config.yaml")

    # o por linea de comandos, para validar todos los tenants:
    py -3.13 nucleo/config/schema.py
================================================================================
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import (BaseModel, ConfigDict, Field, ValidationError,
                      field_validator, model_validator)


# =============================================================================
#  DETECCION DE SECRETOS
# =============================================================================
# Un '*_ref' es el NOMBRE de donde vive el secreto, nunca el secreto.
RE_NOMBRE_REF = re.compile(r"^[A-Z][A-Z0-9_]{2,}$")

# Heuristicas de credencial pegada por error. No pretenden ser exhaustivas:
# atrapan el descuido tipico, que es copiar la clave en vez de su nombre.
PATRONES_SECRETO = [
    (re.compile(r"^sk-[A-Za-z0-9_\-]{16,}$"), "clave estilo OpenAI"),
    (re.compile(r"^ey[A-Za-z0-9_\-]{20,}\."), "JSON Web Token"),
    (re.compile(r"^[A-Za-z0-9+/]{40,}={0,2}$"), "cadena base64 larga"),
    (re.compile(r"^[a-f0-9]{32,}$", re.I), "hash o clave hexadecimal"),
]


def _sin_tildes(texto: str) -> str:
    """Minusculas y sin tildes, para comparar texto que escribio una persona.
    'Television' y 'TELEVISIÓN' tienen que dar lo mismo -- ver
    Precondicion.contiene."""
    normal = unicodedata.normalize("NFD", texto.lower())
    return "".join(c for c in normal if unicodedata.category(c) != "Mn")


def _parece_secreto(valor: str) -> str | None:
    for patron, descripcion in PATRONES_SECRETO:
        if patron.match(valor):
            return descripcion
    return None


class Base(BaseModel):
    # Campo desconocido = error. Si alguien escribe 'tono_respuesta' en vez de
    # 'tono', tiene que enterarse al cargar y no cuando el asistente conteste
    # con el tono por defecto sin avisar a nadie.
    model_config = ConfigDict(extra="forbid")


# =============================================================================
#  IDENTIDAD Y PRESENTACION
# =============================================================================

class Identidad(Base):
    slug: Annotated[str, Field(pattern=r"^[a-z][a-z0-9\-]{1,30}$")]
    nombre_legal: str
    nombre_comercial: str | None = None
    sector: str = "isp"
    zona_horaria: str = "America/Bogota"
    idioma: str = "es"
    # Que servicios ofrece la empresa y sus planes en general (ej. "internet
    # solo, o combo internet+TV") -- se inyecta SIEMPRE en el prompt de
    # cualquier rol (nucleo/recuperacion/prompt.py), a diferencia del corpus
    # (RAG, se recupera solo si la pregunta matchea). Existe porque un
    # cliente pregunto por TV y el agente, sin saber que la empresa SI la
    # vende en combo, no supo si inventar o negar el servicio -- esto le da
    # el contexto de base que necesita para no adivinar ninguna de las dos.
    descripcion: str = Field(default="", max_length=2000)


class Marca(Base):
    logo_url: str | None = None
    color_primario: str | None = None
    firma_mensajes: str | None = None


class Persona(Base):
    """
    Como se presenta y como escribe el asistente. Es lo unico de la
    configuracion que el cliente edita sin que cambie QUE puede ver nadie:
    'instrucciones_adicionales' entra al prompt, y el prompt es guia, no
    garantia -- el filtro de campos y la confirmacion de acciones sensibles
    viven en codigo y no se pueden aflojar desde aca (PRD 7.4).
    """
    nombre_asistente: str = Field(min_length=1, max_length=60)
    tono: Literal["formal", "cercano", "tecnico"] = "cercano"
    longitud_respuesta: Literal["breve", "media", "extensa"] = "breve"
    # El tope existe porque este texto viaja en CADA turno, delante de la
    # pregunta. Sin limite, un pegado largo desde una pantalla de edicion se
    # come el contexto del modelo y degrada las respuestas sin dar ningun
    # error: se nota como "el asistente empeoro", que es lo que nadie sabe
    # diagnosticar. 2.000 caracteres son ~10x lo que usa un tenant real.
    instrucciones_adicionales: str = Field(default="", max_length=2000)


class TerminoGlosario(Base):
    """
    Normaliza el vocabulario del sector para la expansion de consulta.

    Sirve para que "no le llega internet" recupere fragmentos que hablan de
    "perdida de senal optica". Sin esto, el usuario y el manual usan idiomas
    distintos y la busqueda no cruza.
    """
    termino_canonico: str
    sinonimos: list[str] = Field(min_length=1)


# =============================================================================
#  ROLES  -  lista blanca, nunca lista negra
# =============================================================================

class Rol(Base):
    """
    Que puede hacer y VER un rol.

    'campos_permitidos' es lista BLANCA por herramienta: un campo sin entrada
    explicita no se entrega. Es deliberado y no es lo mismo que enumerar los
    prohibidos: el registro de cliente de WispHub trae 54 campos, entre ellos
    cuatro de contrasena y las coordenadas GPS del domicilio. Con lista negra,
    un campo nuevo que agregue el proveedor queda expuesto por defecto; con
    lista blanca, queda bloqueado por defecto.
    """
    descripcion: str = ""
    puede_consultar: list[str] = Field(default_factory=list)
    campos_permitidos: dict[str, list[str]] = Field(default_factory=dict)
    # Documental y de defensa en profundidad. NO sustituye a la lista blanca:
    # lo que protege de verdad es 'campos_permitidos'.
    nunca_revelar: list[str] = Field(default_factory=list)
    # A quien le habla este rol. Cambia el prompt de raiz: un colaborador
    # habla de "el cliente" en tercera persona y no requiere verificar
    # identidad (ya esta autorizado por trabajar ahi); un cliente_final habla
    # en segunda persona de SU PROPIO servicio y es un desconocido hasta que
    # se verifique (nucleo/seguridad/verificacion.py). No es un 'if' por rol
    # en el motor: es este campo el que decide.
    orientado_a: Literal["colaborador", "cliente_final"] = "colaborador"
    # Solo organizativas -- para mostrar el agente ordenado en un diagrama
    # (que area, que cargo). NO cambian que puede hacer o ver el rol; eso lo
    # sigue decidiendo unicamente 'puede_consultar'/'campos_permitidos'.
    area: str | None = None
    cargo: str | None = None
    # QUE TEMAS ATIENDE, en palabras del cliente ("saldo, facturas, fechas de
    # corte"). Lo lee el ROUTER para decidir a quien derivar: se arma su tabla
    # de enrutamiento juntando el 'atiende' de cada destino
    # (nucleo/recuperacion/prompt.py), en vez de tenerlo escrito a mano en su
    # prompt. Asi, conectar un agente nuevo al router es completar este campo
    # desde la pantalla -- no editar el texto de otro agente.
    #
    # Vacio = el router no sabe cuando mandarle nada, aunque este declarado
    # como destino. Es lo que hace que la pantalla pueda avisar "este agente
    # esta conectado pero nunca le va a llegar una conversacion".
    atiende: str = Field(default="", max_length=400)


# =============================================================================
#  SEGURIDAD
# =============================================================================

class Seguridad(Base):
    """
    Reglas duras. Se inyectan en el prompt Y se validan en codigo (§8).

    El sistema queda expuesto a usuarios finales por WhatsApp, asi que hay que
    asumir intentos de inyeccion de prompt. La seguridad real esta en la
    validacion de permisos en codigo y en el alcance limitado de cada
    herramienta; las reglas del prompt son una capa adicional, nunca la unica.
    """
    reglas_absolutas: list[str] = Field(default_factory=list)
    # Nivel de verificacion exigido por recurso (ver 'autenticacion').
    #   0 = ninguno   1 = posesion del canal   2 = reto adicional   3 = humano
    requiere_verificacion: dict[str, Literal[0, 1, 2, 3]] = Field(default_factory=dict)


class Autenticacion(Base):
    """
    Como se identifica a quien escribe.

    Medido en la base de Rapilink (600 clientes): 98.7% tienen al menos un
    movil registrado, 50% tienen dos, y solo el 0.4% de los numeros apunta a
    mas de un cliente. Por eso el numero del canal sirve como factor de
    POSESION.

    La cedula NO sirve para autenticar: identifica pero no autentica, porque es
    publica — esta en la factura, el contrato y el documento. Cualquiera que
    conozca la cedula de un vecino podria pedir su saldo.
    """
    campo_identidad: str = "telefono"
    # El campo 'telefono' de WispHub guarda varios numeros en uno solo en el
    # 55% de los casos ("3001234567, 3109876543"). Hay que extraerlos todos:
    # leerlo como valor unico baja la cobertura de 98.7% a 43%.
    patron_extraccion: str = r"(?<!\d)3\d{9}(?!\d)"
    # Cuando el numero no coincide (celular nuevo). Ninguno debe ser publico.
    retos_nivel_2: list[str] = Field(default_factory=list)
    # Un numero que apunta a varios clientes no es fallo de autenticacion:
    # es que hay que preguntar cual servicio.
    desambiguar_si_multiple: bool = True
    ofrecer_actualizar_numero: bool = True


# =============================================================================
#  CORPUS  (ingesta y RAG)
# =============================================================================

class TipoDocumento(Base):
    tipo: str
    estrategia_chunking: Literal["por_seccion", "por_parrafo", "fijo"] = "por_seccion"
    # Una tabla partida a la mitad pierde todo su sentido: una que mapea
    # servidores a VLAN y segmentos IP es inutil si se corta.
    preservar_tablas: bool = True
    tamano_objetivo_tokens: int = Field(default=500, ge=100, le=2000)
    metadatos_dominio: list[str] = Field(default_factory=list)


class PerfilDocumento(Base):
    """
    Como esta ARMADA la documentacion de esta empresa. No de que trata.

    Cada organizacion maqueta distinto, y no es un detalle cosmetico: define
    donde empieza una seccion y que bloque es contenido. Solo en el corpus de
    referencia conviven tres plantillas — una marca las secciones con estilos
    de Word, otra las mete dentro de tablas de una celda, y una tercera usa
    estilo de titulo para los items de una lista.

    Sin este perfil, el criterio de la primera empresa se aplicaria a los
    documentos de la segunda, y sus procesos se mezclarian en el corpus.
    """
    marcas_callout: list[str] = Field(default_factory=lambda: [
        "⚠", "📝", "❗", "ℹ", "✅", "🔴", "atencion", "nota", "importante",
        "advertencia", "precaucion", "recuerde", "ojo"])
    encabezados_pie: list[str] = Field(default_factory=lambda: [
        "registro de cambio", "aprobacion", "elaborado", "revisado por",
        "aprobado por", "control de cambios"])
    campos_metadatos: list[str] = Field(
        default_factory=lambda: ["codigo", "version", "fecha"])
    # Una tabla de una celda con '1 OBJETIVO' abre seccion.
    titulo_un_nivel_en_tabla: bool = True
    # Sin estilo de titulo, solo cuenta la numeracion multinivel ('1.1'). Es lo
    # que separa un titulo de un paso de lista numerada.
    exigir_multinivel_sin_estilo: bool = True
    max_largo_titulo: int = Field(default=120, ge=20, le=400)
    # 'seccion_vacia' no viene por defecto: en el corpus de referencia dio 26
    # falsos positivos y 0 aciertos. Un detector que grita en falso deja de
    # leerse, y entonces tampoco sirve para los casos en que acierta.
    defectos_a_reportar: list[Literal[
        "numeracion_duplicada", "referencia_rota", "seccion_vacia"]] = Field(
        default_factory=lambda: ["numeracion_duplicada", "referencia_rota"])
    # Deja constancia de las imagenes en el fragmento. No las lee: evita que su
    # contenido desaparezca EN SILENCIO.
    anotar_imagenes: bool = True


class Corpus(Base):
    tipos_documento: list[TipoDocumento] = Field(default_factory=list)
    reportar_defectos: bool = True
    perfil_documento: PerfilDocumento = Field(default_factory=PerfilDocumento)
    # Documentos que NO deben vectorizarse. Patrones tipo glob sobre el nombre
    # del archivo. El caso tipico es un documento con credenciales: si entra al
    # corpus, el asistente puede recuperarlo y mostrarselo a quien pregunte.
    excluir: list[str] = Field(default_factory=list)
    # Versiones superadas. Se cargan igual pero marcadas 'obsoleto', asi que no
    # se recuperan en las busquedas y a la vez queda registro de que existieron.
    # Sin esto, el asistente recupera la version vieja tanto como la vigente y
    # no tiene forma de saber cual manda.
    obsoletos: list[str] = Field(default_factory=list)
    # RESPALDO de 'roles' para los documentos que todavia no declaran la
    # columna en su tabla de metadatos. Patron glob -> lista de roles.
    #
    # Lo que manda siempre es el documento: si el .docx trae 'roles', ese gana
    # y esto ni se mira. La razon de que exista es operativa -- de los 19
    # documentos de Rapilink, 12 tienen tabla de metadatos sin columna de
    # roles y 7 no tienen tabla, asi que hoy una recarga los dejaria a todos
    # sin roles, o sea invisibles para el asistente, hasta rellenarlos a mano
    # en la base.
    #
    # Agregarles la columna a los 19 no es solo un dato: a los 7 sin tabla les
    # cambiaria el codigo y la version (procesar() los deduce del nombre de
    # archivo cuando no hay tabla), y con eso su identidad en el corpus.
    # Cuando la empresa actualice sus plantillas, este respaldo deja de
    # usarse solo, sin tocar codigo.
    roles_por_defecto: dict[str, list[str]] = Field(default_factory=dict)


class RAG(Base):
    modelo_embeddings: str
    # 1024 = bge-m3, y coincide con vector(1024) del esquema SQL.
    # Cambiar esto obliga a re-vectorizar TODO el corpus y a migrar la columna.
    dimensiones: Literal[384, 768, 1024, 1536] = 1024
    top_k: int = Field(default=8, ge=1, le=50)
    umbral_similitud: float = Field(default=0.35, ge=0.0, le=1.0)
    busqueda_hibrida: bool = True
    rrf_k: int = 60
    reranking_activo: bool = False
    expandir_con_glosario: bool = True
    # Si nada supera el umbral NO se llama al modelo: se responde esto y se
    # registra en unanswered_queries. Llamar al modelo sin contexto es pedirle
    # que invente.
    mensaje_sin_resultados: str


# =============================================================================
#  MODELOS
# =============================================================================

class LLM(Base):
    """
    Un modelo por defecto, con sustituciones por canal o por rol.

    Las sustituciones existen por una tension medida: el modelo elegido tarda
    42.6 s por turno, y un tecnico en campo esperando 40 s por WhatsApp
    probablemente abandone. Que la estructura lo contemple desde el diseno
    cuesta cero; agregarlo despues obliga a tocar el motor.
    """
    # NO SE USA. Se conserva para que las configuraciones ya guardadas en la
    # base sigan cargando (Base tiene extra='forbid': quitarlo haria fallar la
    # validacion de cualquier config que todavia lo traiga). Quien decide el
    # proveedor es el PREFIJO de cada referencia de modelo --
    # 'deepseek:deepseek-v4-flash' -> deepseek, ver cliente.py::resolver-- y
    # esta lista ni siquiera incluye a deepseek, asi que nunca pudo expresar
    # lo que de verdad se estaba usando. No lo pongas en un tenant nuevo.
    proveedor: Literal["ollama", "openai", "anthropic"] = "ollama"
    modelo_por_defecto: str
    # El modelo que ELIGE herramienta y el que REDACTA pueden ser distintos.
    # Medido: phi4-mini acierta 100% repitiendo un dato y 12.5% eligiendo
    # herramienta. Son habilidades distintas y conviene medirlas por separado.
    modelo_seleccion: str | None = None
    modelo_redaccion: str | None = None
    modelo_informes: str | None = None
    overrides: dict[str, str] = Field(default_factory=dict)  # 'canal:whatsapp' -> modelo
    temperatura: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=64)
    # Un bucle de agente puede multiplicar la factura de la noche a la manana,
    # y aqui cada iteracion cuesta un turno completo, no milisegundos.
    limite_iteraciones_agente: int = Field(default=4, ge=1, le=10)
    descartar_thinking: bool = True


# =============================================================================
#  HERRAMIENTAS
# =============================================================================

class FiltroVerificado(Base):
    """
    Un filtro que PASO la prueba del valor imposible.

    Metodo: se consulta con un valor que no puede existir y se compara el total
    contra la consulta sin filtro. Si son iguales, la API esta ignorando el
    parametro y NO puede entrar aqui.
    """
    param: str
    tipo: Literal["enum", "id", "texto"] = "enum"
    # int para APIs con codigo numerico (WispHub: estado=1/2/3); str para
    # APIs que ya reciben el valor en texto (BottleCRM: status=Assigned).
    valores: dict[str, int | str] | None = None
    verificado_el: date | None = None

    @model_validator(mode="after")
    def _enum_necesita_valores(self):
        if self.tipo == "enum" and not self.valores:
            raise ValueError(f"el filtro '{self.param}' es enum y no declara 'valores'")
        return self


class Periodo(Base):
    campos: dict[str, str]
    por_defecto: str
    sufijos: tuple[str, str] = ("_0", "_1")
    max_meses: int = Field(ge=1, le=12)
    nota_defecto: str = ""
    advertencia_defecto: str = ""

    @model_validator(mode="after")
    def _defecto_existe(self):
        if self.por_defecto not in self.campos:
            raise ValueError(
                f"periodo.por_defecto '{self.por_defecto}' no esta en campos "
                f"({', '.join(self.campos)})")
        return self


class RangoVeredicto(Base):
    """
    Un tramo de un umbral: [desde, hasta] (ambos inclusive; None = sin tope
    de ese lado) -> la etiqueta que le corresponde. El PRIMER rango que
    matchea gana, en el orden declarado -- no se valida que los rangos no se
    superpongan, el orden es la desambiguacion.
    """
    desde: float | None = None
    hasta: float | None = None
    etiqueta: str

    @model_validator(mode="after")
    def _algun_limite(self):
        if self.desde is None and self.hasta is None:
            raise ValueError(
                "un RangoVeredicto necesita al menos 'desde' o 'hasta' -- "
                "sin ninguno de los dos matchea cualquier valor y no sirve "
                "como umbral")
        return self


class Precondicion(Base):
    """
    Una condicion que otra herramienta ya tiene que haber cumplido, EN ESTA
    CONVERSACION, antes de que el motor deje ejecutar la que la declara.

    Nace de un pedido puntual del cliente sobre el reinicio de la ONT: no un
    paso de aprobacion humana, sino una precondicion en codigo -- "reiniciar
    solo si ya se diagnostico que la senal esta bien y el ping responde".
    Fail-closed: sin una llamada previa que matchee, no se ejecuta. Generico
    a proposito -- 'campo'/'valor' son el nombre y valor que ESA herramienta
    devuelve (ej. 'onu_signal_1490_veredicto'/'aceptable'), nucleo/ no sabe
    que significan.
    """
    herramienta: str
    campo: str
    valor: Any = None
    # Varios valores aceptables, cuando el dato REAL no es un unico valor
    # estable. Medido el 15/08/2026: 'ping-exitoso' de WispHub devolvio
    # '1 de 3', '2 de 3' y '3 de 3' en tres corridas seguidas contra el MISMO
    # equipo sano. Con 'valor: "3 de 3"' la precondicion solo se cumplia
    # cuando el ping salia perfecto -- una de cada tres veces-- y el cliente
    # con la conexion inestable (justo el que se queja) casi nunca llegaba al
    # reinicio remoto. Lo que hay que exigir es que el equipo CONTESTE, no
    # que conteste perfecto.
    valores: list[Any] | None = None
    # Un texto que tiene que ESTAR CONTENIDO en el valor leido, cuando lo que
    # hay que exigir no es un valor cerrado sino un rasgo de un texto libre.
    # Medido el 15/08/2026: la unica forma de saber si un plan incluye
    # television es que su descripcion lo diga, y esas descripciones son
    # libres ("PLAN HOGAR FO (100MB + TV)", "SERVICIO DE INTERNET + TV"...).
    # Enumerarlas con 'valores' seria una lista que se desactualiza con el
    # primer plan nuevo, y quedarse sin el guard significa encenderle un
    # servicio pago a quien no lo paga: de 8 clientes con CATV apagada, 4 la
    # tenian apagada CON RAZON.
    #
    # Sin distinguir mayusculas ni tildes -- lo escribe una persona en el
    # panel del proveedor, no un sistema.
    contiene: str | None = None

    @model_validator(mode="after")
    def _uno_solo(self):
        declarados = sum(x is not None for x in (self.valor, self.valores, self.contiene))
        if declarados != 1:
            raise ValueError(
                f"la precondicion sobre '{self.herramienta}.{self.campo}' tiene "
                f"que declarar EXACTAMENTE uno de 'valor' (uno solo), "
                f"'valores' (varios aceptables) o 'contiene' (un texto dentro "
                f"del valor leido) -- declaro {declarados}")
        return self

    def acepta(self, leido) -> bool:
        """Si el valor leido de la respuesta cumple esta condicion."""
        if self.contiene is not None:
            # Fail-closed ante un dato que no es texto: un numero o un None no
            # 'contiene' nada, y darlo por bueno seria saltearse el guard.
            if not isinstance(leido, str):
                return False
            return _sin_tildes(self.contiene) in _sin_tildes(leido)
        if self.valores is not None:
            return leido in self.valores
        return leido == self.valor


class Herramienta(Base):
    nombre: str
    # 'interno': no llama a ninguna API -- el motor la resuelve el mismo
    # (hoy, solo confirma_identidad). Sin endpoint/base_url a proposito, ver
    # el validador mas abajo.
    tipo: Literal["http", "agregado", "sql", "webhook", "batch", "interno"]
    descripcion: str = ""
    solo_lectura: bool = True
    roles_permitidos: list[str] = Field(min_length=1)
    requiere_confirmacion: bool = False
    # Argumento_de_la_llamada -> atributo de la sesion verificada. El modelo
    # NUNCA propone estos valores (aunque los pida en el mensaje): el motor
    # los sobrescribe siempre con lo que haya en la sesion. Existe para que
    # un cliente_final no pueda pedir, via inyeccion de prompt, el servicio
    # de otro id_cliente -- la identidad la resuelve la verificacion, no el
    # modelo. Ej.: {'id_servicio': 'id_cliente'}.
    inyectar_sesion: dict[str, str] = Field(default_factory=dict)
    # Marca esta herramienta como un METODO DE VERIFICACION DE IDENTIDAD, no
    # una consulta de datos. Cambia el comportamiento del motor:
    #   - se ofrece SIEMPRE, aunque la sesion no este verificada todavia (es
    #     justamente como se verifica) -- nunca pasa por el filtro de nivel.
    #   - el modelo SI propone el argumento en 'campo_busqueda' (viene del
    #     cliente, ej. su cedula) -- es la unica excepcion a que el modelo
    #     nunca proponga identificadores.
    #   - la respuesta NO se filtra ni se muestra como dato: el motor la usa
    #     para decidir verificado/ambiguo/no-encontrado y arma el mensaje el
    #     mismo, nunca deja pasar el registro crudo hacia el modelo.
    verifica_identidad: bool = False
    # Campo de la API por el que se busca (ej. 'cedula'). Requerido si
    # verifica_identidad=True.
    campo_busqueda: str | None = None
    # Segunda etapa de verificacion: cierra (o descarta) lo que
    # verifica_identidad dejo pendiente -- ver Sesion.id_cliente_pendiente.
    # No llama a ninguna API (tipo 'interno'): el motor solo lee el
    # 'confirma' (bool) que propone el modelo -- la unica otra excepcion,
    # junto con campo_busqueda, a que el modelo nunca proponga datos de
    # identidad, porque este SI es un booleano sobre lo que el CLIENTE
    # respondio, no un identificador.
    confirma_identidad: bool = False
    # Tipo 'interno', igual que confirma_identidad: no llama a ninguna API,
    # el motor solo cambia que ROL atiende el resto de la conversacion. El
    # modelo SI propone 'area' -- es la unica info que aporta, y esta
    # acotada por el enum de 'areas_destino', nunca libre. Ver
    # nucleo/modelo/motor.py::_ejecutar_derivacion.
    deriva_rol: bool = False
    # Nombres de rol (del mismo tenant, orientado_a=cliente_final) a los que
    # esta herramienta puede derivar. Requerido si deriva_rol=True -- sin
    # esto no hay que ofrecerle al modelo, no hay forma de armar el enum del
    # esquema ni de validar la derivacion en codigo.
    areas_destino: list[str] = Field(default_factory=list)

    # --- http / agregado ---
    # No es secreto (no dispara el barrido de _barrer_secretos): es dato de
    # tenant igual que 'endpoint', solo que compartido por varias
    # herramientas del mismo proveedor. Literal en el YAML -- sirve para una
    # API cuyo dominio es el MISMO para cualquier empresa (WispHub, BottleCRM
    # self-hosted). Para una API donde el dominio VARIA por empresa (ej.
    # SmartOLT: '{subdominio}.smartolt.com', uno distinto por ISP), usar
    # 'base_url_ref' en su lugar -- este software es SaaS multi-tenant, y un
    # dato asi no puede quedar fijo en un archivo que solo un desarrollador
    # edita: la proxima empresa que se conecte tiene que poder cargarlo desde
    # la pantalla de ajustes, no pedir una sesion de codigo.
    base_url: str | None = None
    # El NOMBRE de una variable en TenantConfig.variables_tenant -- mismo
    # patron que 'auth_ref' apunta a un secreto, pero esto NO es secreto
    # (dominio, subdominio, ID de cuenta): se guarda en texto plano en la
    # config del tenant, editable desde /configuracion/variables. Si se
    # declara, el ejecutor resuelve el 'base_url' real desde ahi en el
    # momento de la llamada -- 'base_url' arriba queda sin usar.
    base_url_ref: str | None = None
    endpoint: str | None = None
    metodo: Literal["GET", "POST", "PUT", "PATCH"] = "GET"
    auth_ref: str | None = None
    # El esquema del header Authorization varia por proveedor (WispHub usa
    # 'Api-Key', no el 'Bearer' habitual) -- es dato del tenant, no del motor.
    auth_esquema: str = "Bearer"
    # El NOMBRE del header tambien varia -- SmartOLT no usa 'Authorization' en
    # absoluto, exige 'X-Token' sin esquema (auth_esquema: "" en ese caso).
    # Verificado en vivo agosto 2026, ver .claude/skills/smartolt-api.
    auth_header: str = "Authorization"
    # Algunas APIs envuelven la respuesta en una clave en vez de devolver el
    # dato directo (ej. {"cases_obj": {...}} o {"cases": [...], "cases_count": N}
    # en vez de {"results": [...], "count": N}). Si se declara, el ejecutor
    # extrae esa clave antes de pasar el dato al filtro de campos -- generico,
    # no sabe que proveedor la necesita.
    extraer_de: str | None = None
    # Campos de la respuesta que son TEXTO LIBRE, no un valor estructurado --
    # un operador humano pudo haber escrito cualquier cosa ahi, incluida PII
    # (PRD.md 7.4, "Limite conocido: los campos de texto libre"). La lista
    # blanca decide que campos pasan, no que contienen; estos nombres pasan
    # ademas por nucleo/seguridad/redaccion.py antes de llegar al modelo,
    # sin importar que rol pregunte -- es una propiedad del CAMPO, no del rol.
    campos_texto_libre: list[str] = Field(default_factory=list)
    # La API responde 202 + {"task_id": ...} y hay que consultar el resultado
    # aparte (ej. WispHub en ping_cliente, verificado en vivo agosto 2026) --
    # ver nucleo/herramientas/http.py:ejecutar_asincrono().
    asincrona: bool = False
    # PRD 12.5 "el modelo compone, el codigo calcula": para una herramienta
    # que devuelve un numero contra el que hay un umbral normado (ej. dBm de
    # senal optica contra G-GO-04), el ejecutor computa la etiqueta en
    # Python y la agrega como '{campo}_veredicto' -- el modelo nunca
    # interpreta el numero crudo. Los rangos (y sus valores) son dato de
    # tenant, no del motor: nucleo/ no sabe que es un dBm ni cuales son los
    # limites de Rapilink.
    veredictos: dict[str, list[RangoVeredicto]] = Field(default_factory=dict)
    # Como 'veredictos', pero para un valor de TEXTO exacto en vez de un
    # rango numerico (ej. SmartOLT 'Last down cause': "dying-gasp" -> "sin
    # energia en el domicilio"). El campo puede usar notacion con punto de
    # UN nivel ("ONU details.Last down cause") para leer y escribir dentro
    # de un objeto anidado -- mismo formato que Rol.campos_permitidos
    # (nucleo/seguridad/listas_blancas.py), asi la etiqueta calculada queda
    # en el mismo lugar que la lista blanca ya sabe filtrar. Un valor sin
    # entrada en el mapeo se deja sin interpretar -- no inventa una
    # etiqueta para una causa que no se documento todavia.
    mapeos: dict[str, dict[str, str]] = Field(default_factory=dict)
    # Ver Precondicion. TODAS tienen que cumplirse (AND), con la llamada MAS
    # RECIENTE de cada herramienta requerida -- una que cumplio hace varios
    # mensajes pero ya no representa el estado actual no cuenta.
    exige_previas: list[Precondicion] = Field(default_factory=list)
    # Texto que el motor inyecta como mensaje 'system' apenas 'exige_previas'
    # queda satisfecha (y esta herramienta todavia no se llamo en la
    # conversacion) -- SOLO si 'exige_previas' esta declarado, no tiene
    # sentido sin precondicion que "recien se cumpla".
    #
    # Existe porque un texto en el prompt del rol o en la propia descripcion
    # de la herramienta NO alcanza (probado en vivo, agosto 2026, con
    # reiniciar_ont): el modelo que decide que herramienta llamar solo ve esas
    # instrucciones ANTES de pedir los datos que activan la precondicion, y
    # el modelo que redacta la respuesta final no puede llamar herramientas
    # (tools=None). Sin este mensaje, nadie le da al modelo una SEGUNDA
    # oportunidad de decision justo cuando el dato que la habilita ya esta
    # disponible -- se queda con el plan que armo antes de tener el dato.
    sugerir_cuando_disponible: str | None = None
    # Tope de veces que esta herramienta puede ejecutarse en UNA conversacion
    # (None = sin tope). Pensado para 'reiniciar_ont': un cliente que insiste
    # ("reiniciá otra vez") no puede hacer que el modelo corte el servicio
    # repetidamente en el mismo intercambio. No es un cooldown por tiempo
    # (el historial de la conversacion no guarda timestamps por mensaje) --
    # es un tope duro por conversacion, mas simple y igual de efectivo para
    # el caso que motiva esto.
    limite_por_conversacion: int | None = Field(default=None, ge=1)
    # Algunas APIs exigen multipart/form-data en vez de JSON -- verificado en
    # vivo con WispHub POST /tickets/ (agosto 2026): JSON da 500 (opaco,
    # sin motivo), form-urlencoded da 415, y solo multipart funciona. No es
    # negociable por el cliente HTTP: hay que armar el body distinto.
    multipart: bool = False
    # Valores constantes que el motor manda SIEMPRE con la llamada, nunca
    # visibles para el modelo (a diferencia de filtros_verificados, que el
    # modelo si propone). Ej.: ping_cliente necesita 'pings'/'arp_ping' fijos
    # -- no son un dato de negocio que el modelo deba decidir cada vez.
    argumentos_fijos: dict[str, Any] = Field(default_factory=dict)
    # Como argumentos_fijos, pero calculados en el momento de la llamada en
    # vez de un valor congelado en el YAML -- ej. 'fecha_inicio' tiene que
    # ser AHORA, no la fecha en que se escribio la config. Clave: nombre del
    # argumento. Valor: dias desde hoy (0 = ahora mismo, N = ahora + N dias).
    # El modelo nunca decide una fecha (son notoriamente malos calculando
    # fechas): el codigo hace la cuenta, el modelo ni la ve.
    fechas_automaticas: dict[str, int] = Field(default_factory=dict)
    # Cachea la respuesta en asistente.herramientas_cache -- evita pegarle a
    # la API en cada consulta. Pensado para catalogos estables (un plan, una
    # zona), NUNCA para datos que cambian por cliente (saldo, estado): la
    # clave de cache no distingue "hace 2 segundos" de "hace 2 meses" salvo
    # que se declare cache_vigencia_dias. Ver nucleo/modelo/motor.py.
    # Argumento -> nombre de una transformacion conocida por el ejecutor
    # (nucleo/herramientas/http.py:_TRANSFORMACIONES). Si la llamada FALLA, se
    # reintenta UNA vez con ese argumento convertido. Existe porque una misma
    # cosa puede tener dos escrituras equivalentes y la API aceptar solo una,
    # distinta segun el registro -- verificado en vivo (agosto 2026): de 4.966
    # ONUs de Rapilink, 68 solo responden con el serial en su forma
    # hexadecimal, y para las otras 4.898 la valida es la corta. No se puede
    # elegir una sola de antemano, y adivinar mal deja al cliente sin
    # diagnostico con un error que no dice nada.
    #
    # El nucleo aporta el mecanismo y las transformaciones con nombre; QUE
    # herramienta lo necesita lo declara el tenant.
    reintentar_identificador_como: dict[str, str] = Field(default_factory=dict)
    cache: bool = False
    # Dias antes de refrescar una entrada. None = no vence (se asume estable
    # hasta que alguien fuerce un refresco borrando la fila en la base).
    cache_vigencia_dias: int | None = None

    # --- agregado ---
    entidad: str | None = None
    etiqueta: str | None = None
    filtros_verificados: dict[str, FiltroVerificado] = Field(default_factory=dict)
    # Filtros que la API ANUNCIA pero IGNORA. No se intentan: se rechazan con
    # este texto como motivo. Intentarlos devolveria el universo entero
    # disfrazado de respuesta exacta.
    filtros_ignorados_por_api: dict[str, str] = Field(default_factory=dict)
    agrupar_por: list[str] = Field(default_factory=list)
    periodo: Periodo | None = None
    tope_grupos: int = Field(default=12, ge=1, le=50)
    # Solo para tipo 'agregado'. Si es True, el modelo recibe un argumento
    # extra ('formato': texto|excel) y puede pedir el resultado como archivo
    # descargable en vez de solo redactarlo. El archivo lo arma
    # nucleo/herramientas/informes.py -- una hoja con 'interpretacion' y el
    # desglose, nunca datos que el agregado no calculo ya. El modelo nunca ve
    # el archivo en si, solo su identificador (ver motor.py, medios_pendientes).
    exportable: bool = False

    @field_validator("auth_ref", "base_url_ref")
    @classmethod
    def _ref_es_nombre_no_valor(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not RE_NOMBRE_REF.match(v):
            raise ValueError(
                f"'{v}' parece un VALOR. Debe ser el NOMBRE de la variable de "
                f"entorno, del secreto, o de la variable de tenant, en "
                f"MAYUSCULAS (ej. WISPHUB_API_KEY, SMARTOLT_SUBDOMINIO). "
                f"Ningun valor real vive en este archivo.")
        return v

    @model_validator(mode="after")
    def _coherencia(self):
        if self.tipo in ("http", "agregado") and not self.endpoint:
            raise ValueError(f"'{self.nombre}': tipo {self.tipo} exige 'endpoint'")

        if self.tipo in ("http", "agregado") and not (self.base_url or self.base_url_ref):
            raise ValueError(
                f"'{self.nombre}': tipo {self.tipo} exige 'base_url' (fijo, "
                f"igual para cualquier empresa) o 'base_url_ref' (varia por "
                f"empresa, ej. un subdominio -- ver el comentario del campo "
                f"en schema.py)")

        if self.base_url and self.base_url_ref:
            raise ValueError(
                f"'{self.nombre}': declara 'base_url' Y 'base_url_ref' -- "
                f"decidi cual, el segundo pisaria al primero en tiempo de "
                f"ejecucion y dejaria el otro como codigo muerto que confunde.")

        if self.verifica_identidad and not self.campo_busqueda:
            raise ValueError(
                f"'{self.nombre}': verifica_identidad exige 'campo_busqueda'")

        if self.deriva_rol and not self.areas_destino:
            raise ValueError(
                f"'{self.nombre}': deriva_rol exige 'areas_destino' (al menos un rol)")

        if self.cache and self.tipo != "http":
            raise ValueError(
                f"'{self.nombre}': cache=true solo tiene sentido para tipo "
                f"'http' -- 'agregado' agrega sobre todo el universo cada "
                f"vez, cachear un conteo mentiria apenas cambia un registro")

        if self.cache and self.inyectar_sesion:
            raise ValueError(
                f"'{self.nombre}': cache=true no puede combinarse con "
                f"inyectar_sesion. 'inyectar_sesion' es la marca de que la "
                f"respuesta depende de QUE cliente pregunta (su propio "
                f"servicio, su propio saldo) -- guardar eso en la cache "
                f"persistiria datos de cliente crudos, algo que este "
                f"proyecto nunca hace (ver el docstring de nucleo/"
                f"persistencia/db.py). 'cache' es solo para catalogos "
                f"iguales para cualquiera que pregunte (un plan, una zona).")

        if not self.solo_lectura and not self.requiere_confirmacion:
            raise ValueError(
                f"'{self.nombre}' escribe y no exige confirmacion. Toda accion "
                f"de escritura requiere confirmacion humana explicita.")

        if self.tipo == "agregado":
            if not self.entidad:
                raise ValueError(f"'{self.nombre}': tipo agregado exige 'entidad'")

            # Un filtro no puede estar verificado E ignorado a la vez.
            choque = set(self.filtros_verificados) & set(self.filtros_ignorados_por_api)
            if choque:
                raise ValueError(
                    f"'{self.nombre}': {sorted(choque)} aparece(n) como "
                    f"verificado Y como ignorado por la API. Decide cual.")

            # Agrupar por un campo cuesta UNA llamada por valor. Si el campo no
            # esta verificado, cada llamada devolveria el universo entero y el
            # desglose seria basura con aspecto de dato.
            especiales = {"zona"}      # se resuelven contra un catalogo aparte
            for campo in self.agrupar_por:
                if campo not in self.filtros_verificados and campo not in especiales:
                    raise ValueError(
                        f"'{self.nombre}': agrupar_por '{campo}' no esta en "
                        f"filtros_verificados. Agrupar por un filtro que la API "
                        f"ignora produce un desglose sin sentido.")
        return self


# =============================================================================
#  CANALES, ESCALAMIENTO, LIMITES
# =============================================================================

class CanalWhatsApp(Base):
    """
    Canal de WhatsApp Business (Cloud API de Meta).

    Los campos '*_ref' guardan el NOMBRE de la credencial, nunca su valor --
    misma regla que 'auth_ref' en Herramienta. Se resuelven contra los secretos
    de la empresa y despues contra el entorno (nucleo/seguridad/secretos.py),
    que es lo que permite que cada ISP cargue los suyos desde la plataforma.

    Cual es cual, porque los nombres de Meta se confunden:
      phone_number_id   el ID del numero EMISOR. No es el telefono.
      waba_id           la cuenta de WhatsApp Business. Hace falta para
                        plantillas, no para conversar.
      token             token permanente de un System User. El de prueba de la
                        consola dura 24 h y deja de servir sin aviso.
      app_secret        firma cada webhook entrante (X-Hub-Signature-256). Sin
                        el no hay forma de saber si quien golpea es Meta.
      verify_token      cadena que elige la empresa; Meta la devuelve una sola
                        vez, en el handshake de alta del webhook.
    """
    activo: bool = False
    phone_number_id_ref: str | None = None
    token_ref: str | None = None
    waba_id_ref: str | None = None
    app_secret_ref: str | None = None
    verify_token_ref: str | None = None

    # Se fija a proposito: que Meta publique una version nueva no puede cambiar
    # el comportamiento del canal sin que alguien lo decida.
    version_api: str = "v23.0"

    # Solo para mostrarlo en los ajustes ("estas atendiendo desde el 300...").
    # No participa de ninguna llamada: el emisor lo determina phone_number_id.
    numero_visible: str | None = None

    # Por defecto vacio, y entonces manda la constante del modulo del canal.
    # Existe para el dia que un tenant entre por un BSP (Twilio, 360dialog) en
    # vez de por Meta directo: ahi cambia el host, no el resto.
    api_base: str | None = None

    # clave interna -> nombre aprobado en Meta. La indireccion existe para que
    # el codigo diga 'aviso_mora' y cada empresa lo mapee al nombre que
    # registro; el texto lo aprueba Meta y cambiarlo exige volver a su revision.
    plantillas: dict[str, str] = Field(default_factory=dict)

    # Lo que un cliente escribe para dejar de recibir avisos. Se compara contra
    # el mensaje completo en minusculas y sin espacios -- no "contiene", porque
    # "no me llega nada, doy de baja el servicio?" no es una solicitud de baja
    # del canal.
    palabras_baja: list[str] = Field(
        default_factory=lambda: ["baja", "stop", "no molestar", "cancelar avisos"])
    palabras_alta: list[str] = Field(
        default_factory=lambda: ["alta", "start", "reactivar avisos"])
    respuesta_baja: str = (
        "Listo, no te vamos a escribir mas por este medio. "
        "Si necesitas algo, escribinos cuando quieras y te atendemos.")
    respuesta_alta: str = "Listo, vas a volver a recibir nuestros avisos."

    @field_validator("phone_number_id_ref", "token_ref", "waba_id_ref",
                     "app_secret_ref", "verify_token_ref")
    @classmethod
    def _ref_es_nombre(cls, v: str | None) -> str | None:
        if v is not None and not RE_NOMBRE_REF.match(v):
            raise ValueError(f"'{v}' debe ser el NOMBRE del secreto, no su valor")
        return v

    @model_validator(mode="after")
    def _activo_exige_lo_indispensable(self):
        """
        Un canal marcado activo sin sus referencias no falla al arrancar: falla
        en el primer mensaje de un cliente real, que es el peor momento
        posible. Se rechaza al validar la configuracion.

        'waba_id_ref' NO entra: solo hace falta para plantillas, y se puede
        conversar sin ellas. Los otros tres son indispensables -- sin
        app_secret no hay forma de verificar que quien golpea el webhook es
        Meta, y aceptar sin verificar seria confiar en el prompt de la red.
        """
        if not self.activo:
            return self
        faltan = [nombre for nombre, valor in {
            "phone_number_id_ref": self.phone_number_id_ref,
            "token_ref": self.token_ref,
            "app_secret_ref": self.app_secret_ref,
            "verify_token_ref": self.verify_token_ref,
        }.items() if not valor]
        if faltan:
            raise ValueError(
                f"canales.whatsapp esta 'activo' pero no declara: "
                f"{', '.join(faltan)}. Son los nombres de los secretos, no sus "
                f"valores; los valores se cargan aparte.")
        return self


class Canales(Base):
    whatsapp: CanalWhatsApp = Field(default_factory=CanalWhatsApp)
    web: dict[str, Any] = Field(default_factory=lambda: {"activo": True})


class Escalamiento(Base):
    activar_si: list[str] = Field(default_factory=list)
    destino_rol: str | None = None
    mensaje: str = ""
    # Un escape a humano SIEMPRE disponible, no solo por deteccion automatica.
    siempre_disponible: bool = True
    # Caso de 'manual.casos' -> nombre de Herramienta a ejecutar en CODIGO
    # (nunca via tool-calling del modelo) cuando el verificador de
    # nucleo/seguimiento/agendamiento.py confirma que el checklist de ese
    # caso quedo completo. Vacio por defecto: ningun tenant ni ningun caso
    # agenda solo sin declararlo a proposito aca.
    agendamiento_automatico: dict[str, str] = Field(default_factory=dict)
    # Motivos de 'activar_si' que NO escalan la primera vez que aparecen: el
    # asistente se queda una vuelta mas e intenta resolver. Si el motivo
    # vuelve a aparecer, escala sin discutir.
    #
    # Nace de un caso real (15/08/2026): un cliente escribio "el internet no
    # sirve para una verga" en su primer reclamo, el modelo lo leyo como
    # 'frustracion_detectada' y la conversacion se fue a un humano antes de
    # que se intentara ningun diagnostico. En un ISP eso es casi todo el que
    # se queda sin servicio -- el asistente pasaba de atender a filtrar
    # llamadas.
    #
    # Que quede por tenant y por motivo, y no fijo en el codigo, es
    # deliberado: otro ISP puede querer que un insulto pase a una persona de
    # inmediato, y esa es una decision suya. Un motivo que no este aca escala
    # como siempre, a la primera -- entre ellos 'solicitud_explicita', que es
    # el cliente PIDIENDO un humano y nunca debe hacerse esperar.
    intentar_resolver_antes: list[str] = Field(default_factory=list)


class Limites(Base):
    max_conversaciones_dia: int | None = None
    max_costo_usd_mes: float | None = None
    alerta_al_porcentaje: int = Field(default=80, ge=1, le=100)
    retencion_conversaciones_dias: int = Field(default=365, ge=1)
    # Separada de la de arriba y mucho mas corta, a proposito: una conversacion
    # escrita es barata de guardar y util para depurar; una foto pesa y puede
    # mostrar la casa, la cedula o una cara. La foto sirve para resolver el
    # caso, y un caso vive dias. Ver supabase/09_multimedia.sql.
    retencion_multimedia_dias: int = Field(default=30, ge=1)


class Conversaciones(Base):
    """
    Configuracion de la bandeja de conversaciones con clientes finales.

    'etiquetas' es la taxonomia fija que el modelo puede elegir al escalar
    una conversacion a un humano (nucleo/seguimiento/escalamiento.py) -- vía
    tool-calling forzado, igual que cualquier otra herramienta, así que
    nunca inventa una categoria fuera de esta lista.
    """
    etiquetas: list[str] = Field(default_factory=list)


class Manual(Base):
    """
    Casos/procesos fijos para clasificar ejemplos marcados como buenos
    (ver asistente.ejemplos_validados). Fuente de verdad de la taxonomia que
    arma el manual de procedimientos a partir de conversaciones reales, en
    vez de escribirlo a ciegas -- via tool-calling forzado en el frontend,
    igual que 'conversaciones.etiquetas' para escalamiento: nunca se marca
    con un caso fuera de esta lista.
    """
    casos: list[str] = Field(default_factory=list)


class Evaluacion(Base):
    """
    Criterio de aceptacion para produccion.

    Dos umbrales, no uno. Medido en este proyecto: gemma3:4b "respondia bien"
    pero ignoraba el dato de la herramienta e inventaba cliente, plan y factura.
    Un sistema con 92% de acierto que inventa el 3% restante es peligroso; uno
    con 88% que dice "no se" el 12% es utilizable. El promedio no distingue,
    por eso la invencion se mide aparte y su tope es CERO.
    """
    minimo_acierto_pct: float = Field(default=90.0, ge=0, le=100)
    maximo_invenciones: int = Field(default=0, ge=0, le=0)
    minimo_casos: int = Field(default=50, ge=1)


# =============================================================================
#  RAIZ
# =============================================================================

class TenantConfig(Base):
    version: int = 1
    identidad: Identidad
    marca: Marca = Field(default_factory=Marca)
    persona: Persona
    glosario: list[TerminoGlosario] = Field(default_factory=list)
    roles: dict[str, Rol]
    seguridad: Seguridad = Field(default_factory=Seguridad)
    autenticacion: Autenticacion = Field(default_factory=Autenticacion)
    corpus: Corpus = Field(default_factory=Corpus)
    rag: RAG
    llm: LLM
    herramientas: list[Herramienta] = Field(default_factory=list)
    # Valores por empresa que NO son secretos pero SI varian por tenant (un
    # subdominio, un ID de cuenta) -- referenciados por 'Herramienta.
    # base_url_ref'. Se guardan en texto plano ACA (a diferencia de los
    # secretos, que van cifrados en asistente.tenant_secrets) porque no hace
    # falta cifrarlos, y separarlos de 'base_url' (fijo) es lo que permite que
    # una empresa nueva cargue el suyo desde /configuracion/variables sin que
    # nadie edite el YAML a mano -- este software conecta muchas empresas, no
    # una sola, y esa es la diferencia entre un dato de PLATAFORMA (nucleo/,
    # igual para todas) y uno de EMPRESA (aca, distinto por tenant).
    variables_tenant: dict[str, str] = Field(default_factory=dict)
    canales: Canales = Field(default_factory=Canales)
    escalamiento: Escalamiento = Field(default_factory=Escalamiento)
    conversaciones: Conversaciones = Field(default_factory=Conversaciones)
    limites: Limites = Field(default_factory=Limites)
    evaluacion: Evaluacion = Field(default_factory=Evaluacion)
    manual: Manual = Field(default_factory=Manual)

    @model_validator(mode="after")
    def _coherencia_global(self):
        nombres_rol = set(self.roles)
        nombres_herr = {h.nombre for h in self.herramientas}

        # Mismo patron para un rol creado por la UI de edicion o a mano en el
        # YAML: el nombre es una clave que despues viaja como slug (URL de la
        # API, identificador_sesion, 'rol:<nombre>' en llm.overrides).
        for nombre_rol in nombres_rol:
            if not re.match(r"^[a-z][a-z0-9_]{1,29}$", nombre_rol):
                raise ValueError(
                    f"rol '{nombre_rol}': el nombre debe ser minuscula, "
                    f"empezar con letra y usar solo letras/numeros/guion bajo "
                    f"(2-30 caracteres)")

        # Una herramienta no puede permitir un rol inexistente.
        for h in self.herramientas:
            desconocidos = set(h.roles_permitidos) - nombres_rol
            if desconocidos:
                raise ValueError(
                    f"herramienta '{h.nombre}' permite rol(es) inexistente(s): "
                    f"{sorted(desconocidos)}. Roles definidos: {sorted(nombres_rol)}")

            # Derivar a un rol inexistente, o a uno orientado a colaborador,
            # es el agujero de seguridad que este mecanismo existe para
            # evitar: un rol interno no verifica identidad y puede consultar
            # a cualquier cliente (ver nucleo/modelo/motor.py, nivel_exigido
            # se salta por completo si orientado_a != 'cliente_final'). Se
            # verifica aca, no solo en tiempo de ejecucion, para que un YAML
            # mal escrito no se cargue nunca.
            if h.deriva_rol:
                desconocidos = set(h.areas_destino) - nombres_rol
                if desconocidos:
                    raise ValueError(
                        f"herramienta '{h.nombre}' deriva a rol(es) "
                        f"inexistente(s): {sorted(desconocidos)}")
                internos = [n for n in h.areas_destino
                           if self.roles[n].orientado_a != "cliente_final"]
                if internos:
                    raise ValueError(
                        f"herramienta '{h.nombre}' deriva a rol(es) orientados "
                        f"a colaborador: {sorted(internos)}. Un rol interno no "
                        f"verifica identidad -- derivar ahi expondria datos de "
                        f"cualquier cliente a un desconocido.")

        for nombre_rol, rol in self.roles.items():
            # Un rol no puede usar una herramienta que no existe.
            faltantes = set(rol.puede_consultar) - nombres_herr
            if faltantes:
                raise ValueError(
                    f"rol '{nombre_rol}' declara herramienta(s) inexistente(s): "
                    f"{sorted(faltantes)}")

            # FAIL-CLOSED: una herramienta permitida sin lista blanca de campos
            # no devolveria nada. Mejor avisarlo al cargar que descubrirlo con
            # un asesor esperando una respuesta vacia.
            for herr in rol.puede_consultar:
                obj = next((h for h in self.herramientas if h.nombre == herr), None)
                # Una herramienta de verificacion nunca deja pasar su
                # respuesta cruda hacia el modelo (el motor la interpreta el
                # mismo) -- no necesita lista blanca de campos.
                if obj and obj.tipo in ("http", "agregado", "sql") and not obj.verifica_identidad:
                    if herr not in rol.campos_permitidos:
                        raise ValueError(
                            f"rol '{nombre_rol}' puede usar '{herr}' pero no "
                            f"declara 'campos_permitidos[{herr}]'. Sin lista "
                            f"blanca la herramienta no devuelve nada "
                            f"(fail-closed): declarala aunque sea completa.")

            # Los campos declarados deben ser de herramientas que el rol tiene.
            sobrantes = set(rol.campos_permitidos) - set(rol.puede_consultar)
            if sobrantes:
                raise ValueError(
                    f"rol '{nombre_rol}' declara campos de {sorted(sobrantes)}, "
                    f"herramienta(s) que no puede consultar")

        # El destino del escalamiento tiene que existir.
        destino = self.escalamiento.destino_rol
        if destino and destino not in nombres_rol:
            raise ValueError(
                f"escalamiento.destino_rol '{destino}' no es un rol definido")

        # Cada caso de agendamiento automatico tiene que ser un caso real del
        # manual, y la herramienta que ejecuta tiene que existir -- fail
        # closed al cargar, no en el primer turno que lo dispare de verdad.
        casos_manual = set(self.manual.casos)
        for caso, nombre_herr in self.escalamiento.agendamiento_automatico.items():
            if caso not in casos_manual:
                raise ValueError(
                    f"escalamiento.agendamiento_automatico['{caso}'] no es un "
                    f"caso de 'manual.casos' ({sorted(casos_manual)})")
            if nombre_herr not in nombres_herr:
                raise ValueError(
                    f"escalamiento.agendamiento_automatico['{caso}'] apunta a "
                    f"la herramienta inexistente '{nombre_herr}'")

        # Las sustituciones de modelo deben apuntar a canales o roles reales --
        # con una excepcion: 'rol:supervisor' es una clave VIRTUAL que usa
        # nucleo/seguimiento/supervisor.py para poder redirigir la revision
        # automatica de conversaciones a un modelo distinto (uno mas
        # deliberado, ya que no tiene la urgencia de latencia de responderle
        # a un cliente en vivo) sin que "supervisor" tenga que existir como
        # rol conversacional de verdad en 'roles'.
        for clave in self.llm.overrides:
            if ":" not in clave:
                raise ValueError(
                    f"llm.overrides['{clave}'] debe tener la forma "
                    f"'canal:whatsapp' o 'rol:tecnico'")
            ambito, valor = clave.split(":", 1)
            if ambito == "rol" and valor not in nombres_rol and valor != "supervisor":
                raise ValueError(f"llm.overrides: rol '{valor}' no existe")
            if ambito not in ("rol", "canal"):
                raise ValueError(
                    f"llm.overrides['{clave}']: ambito debe ser 'rol' o 'canal'")
        return self


# =============================================================================
#  CARGA
# =============================================================================

def _barrer_secretos(nodo: Any, ruta: str = "") -> list[str]:
    """Recorre el arbol buscando valores con pinta de credencial."""
    hallazgos: list[str] = []
    if isinstance(nodo, dict):
        for k, v in nodo.items():
            hallazgos += _barrer_secretos(v, f"{ruta}.{k}" if ruta else str(k))
    elif isinstance(nodo, list):
        for i, v in enumerate(nodo):
            hallazgos += _barrer_secretos(v, f"{ruta}[{i}]")
    elif isinstance(nodo, str):
        que = _parece_secreto(nodo)
        if que:
            hallazgos.append(f"{ruta}: {que}")
    return hallazgos


def cargar_config(ruta: str | Path) -> TenantConfig:
    """
    Lee y valida un tenant.config.yaml. Lanza ValueError con TODOS los
    problemas juntos, no solo el primero: corregirlos de a uno es tedioso.
    """
    ruta = Path(ruta)
    crudo = yaml.safe_load(ruta.read_text(encoding="utf-8")) or {}

    secretos = _barrer_secretos(crudo)
    if secretos:
        raise ValueError(
            f"{ruta.name}: hay valores con pinta de credencial. Ningun secreto "
            f"vive en este archivo, solo referencias por nombre:\n  - "
            + "\n  - ".join(secretos))

    try:
        return TenantConfig(**crudo)
    except ValidationError as e:
        lineas = [f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}"
                  for err in e.errors()]
        raise ValueError(
            f"{ruta.name}: {len(lineas)} problema(s) de configuracion:\n  - "
            + "\n  - ".join(lineas)) from None


if __name__ == "__main__":
    import sys
    # Sin argumentos, valida TODOS los tenants. No se nombra ninguno: el nucleo
    # no conoce clientes (ver nucleo/__init__.py y la guarda en tests/).
    objetivos = sys.argv[1:] or sorted(
        str(p) for p in Path(__file__).resolve().parents[2].glob("tenants/*.yaml"))
    if not objetivos:
        raise SystemExit("No hay ningun tenants/*.yaml que validar.")
    for archivo in objetivos:
        try:
            cfg = cargar_config(archivo)
        except ValueError as e:
            print(f"[FALLA] {e}\n")
            continue
        print(f"[OK] {archivo}")
        print(f"      tenant      : {cfg.identidad.slug} ({cfg.identidad.nombre_legal})")
        print(f"      roles       : {', '.join(cfg.roles)}")
        print(f"      herramientas: {len(cfg.herramientas)}")
        print(f"      modelo      : {cfg.llm.modelo_por_defecto}")
        print(f"      embeddings  : {cfg.rag.modelo_embeddings} "
              f"({cfg.rag.dimensiones} dim)\n")
