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
from typing import Annotated, Any, ClassVar, Literal

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
    # Tratamiento al que se NORMALIZA el texto que sale hacia el cliente, ya
    # redactado (nucleo/modelo/tuteo.py). Vacio = no se toca nada.
    #
    # No es lo mismo que pedirselo al modelo por 'instrucciones_adicionales':
    # eso es guia y se desobedece. Esto corre despues, sobre el texto final.
    # Se agrego el 15/08/2026 despues de cuatro intentos de resolverlo por
    # prompt, con todas las fuentes de contexto ya medidas en cero formas de
    # voseo y el modelo produciendolo igual, de forma intermitente.
    #
    # Es configuracion y no una constante del motor porque el tratamiento
    # varia por empresa: un ISP rioplatense va a querer justo lo contrario.
    normalizar_tratamiento: str | None = None

    @field_validator("normalizar_tratamiento")
    @classmethod
    def _tratamiento_implementado(cls, v):
        # Rechaza cualquier valor sin normalizador real detras: un tenant que
        # declara 'usted' y no obtiene nada es peor que un error al cargar,
        # porque se descubre en produccion leyendo una conversacion.
        from nucleo.modelo.tuteo import NORMALIZADORES
        if v not in (None, "") and v not in NORMALIZADORES:
            raise ValueError(
                f"'{v}' no tiene normalizador implementado. Disponibles: "
                f"{', '.join(sorted(NORMALIZADORES))} (ver nucleo/modelo/tuteo.py)")
        return v or None


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
    # Solo tiene efecto con orientado_a='cliente_final'. Por defecto True:
    # preserva el comportamiento de siempre (todo cliente_final es un
    # desconocido hasta que se verifica). False es para un cliente_final
    # que TODAVIA NO ES CLIENTE -- ej. un prospecto pidiendo contratar un
    # servicio nuevo -- donde no hay nada que verificar contra WispHub: no
    # esta en esa base de datos y nunca lo va a estar hasta que se de de
    # alta. Agregado 19/08/2026 porque el bloque "VERIFICACION PRIMERO,
    # SIEMPRE" (nucleo/recuperacion/prompt.py) era incondicional para
    # cualquier cliente_final -- un rol de ventas para prospectos quedaba
    # atrapado pidiendo una cedula que no tiene sentido pedir.
    exige_verificacion: bool = True
    # Solo tiene efecto con exige_verificacion=False. Distingue POR QUE este
    # rol no verifica, algo que 'exige_verificacion' por si solo no alcanza
    # a decir: 'ventas' no verifica porque su interlocutor tipicamente NO ES
    # cliente todavia; un ROUTER puro (agregado 19/08/2026) no verifica
    # porque esa responsabilidad se movio al especialista al que deriva --
    # el suyo SI suele ser cliente, solo que la identidad se confirma
    # rio abajo, no aca. Cambia unicamente el texto del prompt (que le
    # explica al modelo POR QUE no le pide cedula); el gate de ejecucion
    # ya funciona igual con solo 'exige_verificacion=False' en los dos
    # casos.
    deriva_verificacion: bool = False
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

    @model_validator(mode="after")
    def _coherencia(self) -> "Rol":
        if self.exige_verificacion and self.deriva_verificacion:
            raise ValueError(
                f"rol '{self.area or self.cargo or ''}': 'deriva_verificacion' "
                f"solo tiene sentido junto con exige_verificacion=False -- "
                f"con exige_verificacion=True el rol verifica el mismo, no "
                f"tiene a quien delegarselo.")
        return self


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
    # NO es lo mismo que 'requiere_confirmacion' -- ese campo lo exige el
    # validador de TODA escritura (mas abajo), asi que hoy lo declaran
    # herramientas deliberadamente autonomas (registrar_pago, activar_catv...)
    # solo para pasar la validacion, sin que nada las frene en tiempo de
    # ejecucion -- ver el comentario "no reactivar el gate sin discutirlo"
    # en tenants/rapilink.config.yaml. Reusar ese campo para un gate real
    # las hubiera roto a todas de un dia para el otro.
    #
    # 'aprobacion_humana' es el gate real, opt-in, agregado el 18/08/2026
    # con un caso concreto (crear/responder/actualizar tickets de WispHub):
    # el motor NO ejecuta la escritura, la guarda en
    # asistente.acciones_propuestas y le dice al modelo que quedo
    # pendiente. Solo se ejecuta de verdad cuando alguien la aprueba desde
    # /configuracion (ver nucleo/canales/api.py). Empieza en False para
    # todo lo existente -- no cambia el comportamiento de ninguna
    # herramienta que no la declare explicitamente.
    aprobacion_humana: bool = False
    # Solo tiene efecto con aprobacion_humana=True. Texto con marcadores
    # '{clave}' que se rellenan con los argumentos YA resueltos (los mismos
    # que se le mandarian a la API) -- para que quien aprueba lea "Crear
    # ticket 'No Tiene Internet' para el servicio 1234" en vez del JSON
    # crudo. Si no se declara, o si falta algun marcador en los argumentos
    # resueltos, se usa un resumen generico -- nunca falla el turno por
    # esto.
    plantilla_resumen: str | None = None
    # {origen: destino} -- despues de resolver los argumentos, copia el
    # valor de 'origen' a 'destino'. Existe por un patron real de WispHub:
    # crear/editar un ticket exige mandar 'asunto' Y 'asuntos_default' (o
    # 'asunto_default' al editar) con el MISMO valor -- pedirle al modelo
    # que mande el mismo dato dos veces es pedirle que se equivoque dos
    # veces. El codigo lo duplica, el modelo elige una sola vez.
    espejar_campos: dict[str, str] = Field(default_factory=dict)
    # Claves de 'filtros_verificados' que el modelo tiene que completar SI o
    # SI -- van al 'required' del schema de function-calling que recibe el
    # modelo (antes, hardcodeado a [] para toda herramienta, sin excepcion:
    # ver motor.py). Nace de un hallazgo en vivo (19/08/2026): la
    # documentacion oficial de 'POST /api/tickets/' no marcaba 'tecnico' como
    # obligatorio, y WispHub lo rechazo con 400 ("Este campo es requerido")
    # recien al intentar crear un ticket real -- el mismo patron de "la doc
    # es una hipotesis" que ya costo tiempo con los filtros de lectura. Un
    # campo con valor fijo conocido (ej. 'estado' de un ticket nuevo) va en
    # 'argumentos_fijos' en vez de aca -- 'requeridos' es solo para lo que
    # el modelo tiene que decidir.
    requeridos: list[str] = Field(default_factory=list)
    # Argumento_de_la_llamada -> atributo de la sesion verificada. El modelo
    # NUNCA propone estos valores (aunque los pida en el mensaje): el motor
    # los sobrescribe siempre con lo que haya en la sesion. Existe para que
    # un cliente_final no pueda pedir, via inyeccion de prompt, el servicio
    # de otro id_cliente -- la identidad la resuelve la verificacion, no el
    # modelo. Ej.: {'id_servicio': 'id_cliente'}.
    inyectar_sesion: dict[str, str] = Field(default_factory=dict)
    # Claves de 'inyectar_sesion' SIN LAS CUALES la llamada no puede salir.
    #
    # La inyeccion OMITE un valor vacio en vez de mandarlo nulo, por una razon
    # buena y verificada: WispHub responde 400 a {"interfaz": null} pero acepta
    # que el campo no venga. Para un campo opcional como 'interfaz_lan' eso es
    # exactamente lo correcto.
    #
    # Para un campo de IDENTIDAD es lo contrario, y ahi la misma regla abre un
    # agujero: omitir 'id_servicio' no consulta "el servicio de nadie", consulta
    # SIN FILTRO -- y una consulta sin filtro devuelve el universo entero con
    # cara de respuesta exitosa. Medido el 27/08/2026 en produccion: un numero
    # de WhatsApp que no es cliente de nadie disparo 'consultar_mi_servicio' con
    # la sesion sin verificar y trajo 300 filas de 7.356 clientes, con
    # 'exito: True' en la traza y sin una sola senal de que algo anduviera mal.
    #
    # Las herramientas cuyo campo va en la RUTA ('/clientes/{id_servicio}/ping/')
    # ya fallaban cerradas por la guarda de 'endpoint sin resolver' de
    # nucleo/herramientas/http.py. Pero eso es un accidente afortunado de como
    # quedo escrito el endpoint, no una decision: la misma herramienta con el
    # id como parametro de consulta no tenia ninguna proteccion. Esto lo vuelve
    # explicito, y deja de depender de donde caiga el dato en la URL.
    inyectados_obligatorios: list[str] = Field(default_factory=list)
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
    # Tipo 'interno', igual que confirma_identidad: no llama a ninguna API,
    # el motor filtra TenantConfig.planes_venta por la localidad que
    # propone el modelo (via 'filtros_verificados', igual que cualquier
    # filtro comun -- no hace falta una excepcion nueva a "sin argumentos
    # libres", solo lee un valor ya acotado por esa lista). Ver
    # nucleo/modelo/motor.py::_ejecutar_consulta_planes_venta.
    consulta_planes_venta: bool = False
    # Marca esta herramienta (tipicamente 'agregado' sobre 'clientes', ej.
    # contar_clientes) como la FUENTE del sync de localidades -> zona real
    # (ver LocalidadZona mas abajo). El motor nunca la corre durante una
    # conversacion -- solo nucleo/herramientas/localidades.py::sincronizar(),
    # bajo demanda desde /configuracion/localidades/sincronizar. Reusa
    # base_url/endpoint/auth_ref que la herramienta ya declara, sin duplicar
    # esa config para un job aparte.
    sincroniza_localidades: bool = False
    # Las dos que mantienen al dia el ticket del sistema operativo del ISP: una
    # copia ahi lo que se le respondio al cliente, la otra lo cierra. Ver
    # nucleo/seguimiento/operativo.py.
    #
    # Son DOS herramientas y no una con un parametro, porque el codigo de
    # estado ('en progreso', 'cerrado') es del proveedor y va en
    # 'argumentos_fijos' de cada una -- el motor no puede conocer esos numeros.
    responde_ticket_operativo: bool = False
    cierra_ticket_operativo: bool = False
    # La que cierra el caso en el CRM. Misma idea: el motor no sabe con que
    # palabra cierra un caso cada CRM ('Closed' aqui), eso va en la config.
    cierra_caso: bool = False
    # Nombres de campo en la respuesta cruda del proveedor -- configurables
    # por tenant para no hardcodear el vocabulario de un proveedor puntual
    # (WispHub llama 'localidad' y 'zona') en nucleo/. 'campo_zona_sync'
    # espera un objeto anidado {id, nombre}, igual forma que 'zona'/'router'
    # de WispHub.
    campo_localidad_sync: str = "localidad"
    campo_zona_sync: str = "zona"
    # Excepcion CUARTA a "el modelo nunca propone argumentos libres" (las
    # otras tres: campo_busqueda de verifica_identidad, 'confirma' de
    # confirma_identidad, 'area' acotada de deriva_rol). Esta SI necesita ser
    # libre: el asistente de configuracion guiada (CLAUDE.md, "la proxima
    # empresa que se conecte no deberia necesitar una sesion de codigo")
    # existe justamente para que un ADMIN describa una API que nucleo/ no
    # conoce todavia. La seguridad no viene de restringir el argumento sino
    # de tres capas alrededor: nucleo/herramientas/sondeo.py bloquea SSRF
    # (nunca una IP privada/interna), la clave de auth se referencia por
    # NOMBRE (auth_ref) y se resuelve server-side -- nunca pasa por el
    # modelo -- y nada de lo sondeado se activa sin aprobacion humana (ver
    # propone_herramienta).
    sondea_api: bool = False
    # Quinta excepcion: guarda el borrador de Herramienta que arma el ADMIN
    # despues de sondear, en asistente.herramientas_propuestas -- 'pendiente'
    # hasta que alguien lo apruebe desde /configuracion-guiada. El modelo
    # nunca escribe directo al catalogo real, aunque sea el mismo ADMIN
    # quien esta charlando -- ver nucleo/canales/api.py, aprobar_propuesta().
    propone_herramienta: bool = False
    # NO es una excepcion a "el modelo nunca propone argumentos libres" --
    # toma CERO argumentos del modelo, solo 'sn_onu' via inyectar_sesion,
    # igual que consultar_senal_ont. Encadena dos llamadas a SmartOLT
    # (resolver OLT/board/port de la ONU, despues consultar incidentes
    # activos de esa OLT) y calcula el veredicto en codigo -- PRD SS12.5, el
    # modelo nunca compara board/port a mano. Ver
    # nucleo/herramientas/incidentes.py y la skill smartolt-api (seccion
    # get_outage_pons) para el porque y la verificacion en vivo.
    detecta_incidente: bool = False
    # Tipo 'interno' tambien: resume el historial de caidas del enlace en un
    # veredicto ya calculado en vez de entregar la lista cruda de eventos.
    # Ver nucleo/herramientas/estabilidad.py.
    resume_estabilidad: bool = False
    # Tipo 'interno' tambien: valida un pedido de cambio de red inalambrica
    # (nombre y/o clave) ANTES de que salga hacia una persona, y deja en la
    # traza que se pidio -- de ahi sale el asunto con el que entra el ticket.
    # No cambia nada en ningun equipo. Ver nucleo/herramientas/wifi.py.
    valida_pedido_wifi: bool = False

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
    # El NOMBRE de una variable de 'variables_tenant' cuyo valor se le entrega
    # al modelo SOLO si esta herramienta se ejecuto y no fallo.
    #
    # Existe para un caso concreto: hay datos que el asistente puede dar, pero
    # NO antes de haber dejado registro de algo. El primero fue el link del
    # formulario de contratacion -- estaba en el prompt del rol de ventas, asi
    # que el modelo lo repartia a quien quisiera y la solicitud no quedaba
    # anotada en ningun lado. Un prospecto que no llenaba el formulario no
    # habia existido nunca, y nadie podia llamarlo.
    #
    # Pedirselo al prompt ("registra antes de dar el link") no alcanza: el
    # prompt es guia, nunca la garantia (PRD 7.4). Sacando el dato del prompt
    # y devolviendolo aca, el modelo NO PUEDE entregarlo sin haber ejecutado la
    # herramienta, porque no lo tiene. Es la misma idea que 'auth_ref': el
    # valor no vive donde el modelo lo ve.
    #
    # Generico a proposito -- guarda el NOMBRE de la variable, no el dato. El
    # nucleo no sabe que existe un formulario ni una empresa que lo use.
    entrega_variable: str | None = None
    # Si OTRO servicio del despliegue puede pedirle al motor que ejecute esta
    # herramienta, via POST /interno/herramienta/<nombre>.
    #
    # Existe porque la credencial de WispHub vive SOLO en el motor, y el
    # backend del CRM tambien necesita crear un ticket ahi (al enviarse una
    # solicitud de contratacion). La alternativa era copiar la clave al
    # backend: dos servicios con la misma credencial es lo que despues se
    # desincroniza sin que nadie sepa cual es la buena.
    #
    # Por defecto FALSO, y esa es la parte importante: la ruta interna no
    # expone "cualquier herramienta", expone las que alguien declaro una por
    # una. Sin esto, quien tuviera el token de servicio podria ejecutar
    # 'reiniciar_ont' o 'registrar_pago' sobre el cliente que quisiera.
    invocable_por_servicio: bool = False
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
    # Igual que 'argumentos_fijos', pero el valor sale de 'variables_tenant':
    # {argumento_de_la_llamada: NOMBRE_DE_LA_VARIABLE}.
    #
    # Existe por la regla que este proyecto ya aprendio a golpes: un dato que
    # VARIA POR EMPRESA no puede quedar fijo en el YAML. El caso que lo trajo
    # es el id del cliente ficticio "INSTALACIONES NUEVAS" de WispHub (3545 en
    # Rapilink), del que cuelgan los tickets de instalacion -- WispHub exige un
    # cliente para crear un ticket y un prospecto todavia no lo es. Cada ISP va
    # a tener el suyo, con otro numero, y el dia que lo cambien no deberian
    # necesitar a un desarrollador: se edita en /configuracion/variables.
    #
    # Mismo espiritu que 'auth_ref' (secretos) y 'base_url_ref' (dominios):
    # la config guarda el NOMBRE, nunca el dato.
    argumentos_desde_variables: dict[str, str] = Field(default_factory=dict)
    # Cuales de esos fijos puede decidir el CODIGO en el momento (nunca el
    # modelo: esto no viaja por tool-calling).
    #
    # Existe por un caso concreto: el tecnico al que se le asigna un ticket
    # estaba fijo, asi que TODOS los tickets de todos los casos caian sobre la
    # misma persona. El valor de la config pasa a ser el respaldo -- lo que se
    # usa si el codigo no pudo resolver a nadie -- en vez de la unica opcion.
    #
    # Sin esto, la unica salida era declarar una herramienta casi identica por
    # cada variante, que es como ya terminamos con cuatro que solo se
    # diferencian en el asunto.
    argumentos_sobrescribibles: list[str] = Field(default_factory=list)
    # A que argumento se le pega, al final, el nombre de quien lo escribio.
    #
    # Va en CODIGO y no en el texto que redacta el modelo por lo de siempre
    # (PRD 7.4): si el modelo escribe la firma, puede poner otro nombre o
    # saltearla, y una atribucion equivocada en algo que queda registrado es
    # peor que no firmar. Aca se pega siempre, con el nombre real de quien
    # tenia la sesion.
    #
    # Solo se firma si hay un colaborador identificado: un cliente final no
    # firma nada.
    firmar_campo: str = ""
    # Como argumentos_fijos, pero calculados en el momento de la llamada en
    # vez de un valor congelado en el YAML -- ej. 'fecha_inicio' tiene que
    # ser AHORA, no la fecha en que se escribio la config. Clave: nombre del
    # argumento. Valor: dias desde hoy (0 = ahora mismo, N = ahora + N dias).
    # El modelo nunca decide una fecha (son notoriamente malos calculando
    # fechas): el codigo hace la cuenta, el modelo ni la ve.
    fechas_automaticas: dict[str, int] = Field(default_factory=dict)
    # 'fechas_automaticas' calcula la fecha, esto decide como se escribe.
    # Default = el formato que ya exigia WispHub en tickets (DD\MM\AAAA
    # HH:MM). Un mismo proveedor puede pedir OTRO formato en otro endpoint
    # -- confirmado 19/08/2026: 'registrar-pago' exige 'fecha_pago' en
    # 'YYYY-MM-DD HH:mm', no el formato de tickets. Un campo por
    # HERRAMIENTA alcanza (no por fecha individual): cada endpoint tiene
    # una sola convención para todas las fechas que calcula.
    formato_fechas_automaticas: str = "%d/%m/%Y %H:%M"
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
    # Prohibe ejecutar esta herramienta en el MISMO turno en que el rol la
    # recibio por derivacion, SI la puerta declaro que el cliente no dijo
    # que servicio se le cayo ('servicio: no_lo_dijo').
    #
    # Para que sirve: la derivacion pasa el caso con el mensaje de entrada
    # tal como llego a la puerta, que suele ser ambiguo ("me quede sin
    # servicio" no dice si es internet o television). El especialista mide,
    # se convence, y ACTUA sobre el equipo en ese mismo turno. Si el
    # servicio que fallaba era el otro, ya le interrumpio el que si le
    # andaba. Visto en vivo el 15/08/2026: "ME QUEDE SIN SERVICIO" ->
    # reinicio remoto de la ONT -> "PERO ES CON LA TELEVISION".
    #
    # La primera version bloqueaba SIEMPRE en el turno de la derivacion, sin
    # mirar el reporte. Funcionaba, pero le hacia preguntar "¿me confirmas
    # que es el internet?" a alguien que acababa de escribir "no tengo
    # internet" -- se lee como que no leyo. Por eso la condicion mira lo que
    # la puerta declaro y no cuantos turnos pasaron.
    #
    # Solo para acciones que INTERRUMPEN el servicio. No se pone en
    # 'activar_catv', que habilita algo apagado y no le quita nada a nadie.
    # Tampoco hace falta en las de solo lectura: medir es gratis y sirve
    # para cualquiera de los dos caminos.
    # SOLO para herramientas 'deriva_rol'. Servicios que la puerta puede
    # declarar como "esto es lo que reporto el cliente" al derivar. El motor
    # le suma siempre 'no_lo_dijo' como opcion, que es la que importa: es la
    # que frena las acciones marcadas con 'exige_turno_propio'.
    #
    # Es config del tenant y no una lista fija porque los servicios varian
    # por empresa -- un ISP que solo vende internet no tiene nada que
    # desambiguar, y otro puede vender telefonia ademas.
    # Si esta herramienta FALLA, la conversacion escala con este motivo, en
    # codigo y sin preguntarle a nadie. El motivo tiene que estar declarado
    # en 'escalamiento.activar_si'.
    #
    # Existe porque el escalamiento normal lo decide un segundo modelo
    # ('escalamiento.evaluar') y en los casos limite es INTERMITENTE: medido
    # el 18/08/2026, el mismo historial con la misma config devolvio
    # escalar=true y escalar=false en llamadas seguidas. Mientras tanto el
    # agente ya le habia dicho al cliente que un colaborador iba a seguir su
    # caso -- asi que la mitad de las veces se le prometia una persona que
    # nunca llegaba.
    #
    # Que una herramienta fallo no es un juicio, es un hecho que el motor ya
    # tiene. Cuando de ese hecho se sigue "aca el asistente no puede seguir
    # solo", conviene que lo decida el codigo y no un modelo. Mismo criterio
    # que 'exige_turno_propio' y que el normalizador de tratamiento.
    escalar_si_falla: str | None = None
    # El espejo del anterior: escala cuando la herramienta SALE BIEN.
    #
    # Suena al reves hasta que existe una herramienta cuyo exito ES el pedido
    # de una persona: 'registrar un pedido que el asistente no puede ejecutar'
    # termina bien y JUSTO POR ESO tiene que llegarle a alguien. Sin esto, el
    # asistente le dice al cliente que un colaborador lo va a aplicar y no hay
    # ningun colaborador enterado -- medido el 25/08/2026 sobre 12
    # conversaciones reales: las 12 con escalada=False y sin ticket.
    #
    # Va aca y no en 'escalamiento.activar_si' a secas por dos motivos. Uno:
    # que la herramienta corrio bien es un HECHO, no una interpretacion, y no
    # hay por que pedirle al modelo que lo juzgue (PRD 7.4). Dos: 'activar_si'
    # gobierna TODAS las conversaciones, y un motivo suelto ahi se puede
    # elegir en cualquiera -- declarado por herramienta, solo alcanza a quien
    # lo pide.
    escalar_al_completar: str | None = None
    # De QUE campo de la respuesta sale el resumen del caso cuando esta
    # herramienta fuerza la escalada.
    #
    # Sin esto, el caso llegaba a la bandeja con una frase sobre la mecanica
    # ("escalo porque tal herramienta se completo") y el pedido de verdad
    # quedaba mas abajo, adentro de la traza. Quien abre el caso tiene que
    # leer QUE HAY QUE HACER en el primer renglon.
    #
    # Se declara por empresa y no se cablea el nombre del campo en el codigo:
    # la herramienta que toma un pedido la define cada ISP, y el campo donde
    # deja el texto tambien.
    resumen_desde: str = ""
    servicios_reportables: list[str] = Field(default_factory=list)
    exige_turno_propio: bool = False
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

        if self.aprobacion_humana and self.solo_lectura:
            raise ValueError(
                f"'{self.nombre}': aprobacion_humana solo tiene sentido en una "
                f"escritura -- una consulta de solo lectura no necesita cola de "
                f"aprobacion.")

        sobrantes_inyectados = set(self.inyectados_obligatorios) - set(self.inyectar_sesion)
        if sobrantes_inyectados:
            raise ValueError(
                f"'{self.nombre}': 'inyectados_obligatorios' nombra "
                f"{sorted(sobrantes_inyectados)}, que no esta en "
                f"'inyectar_sesion' -- solo se puede exigir un campo que el "
                f"motor inyecte desde la sesion.")

        sobrantes_requeridos = set(self.requeridos) - set(self.filtros_verificados)
        if sobrantes_requeridos:
            raise ValueError(
                f"'{self.nombre}': 'requeridos' nombra {sorted(sobrantes_requeridos)}, "
                f"que no esta en 'filtros_verificados' -- el modelo no tiene "
                f"forma de completar un campo que no existe como argumento.")

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


class AreaDeTrabajo(Base):
    """
    Donde trabaja una persona del equipo, y que agentes le corresponden por
    defecto.

    Es un PUNTO DE PARTIDA, no una restriccion: al dar de alta a alguien se
    eligen sus agentes a partir del area y despues se editan. Alguien de
    soporte que ademas atiende facturas termina con los dos, y eso tiene que
    poder expresarse.

    Se declara por empresa y no en la pantalla: las areas de un ISP no son las
    del siguiente, y hacerlas fijas en el frontend obliga a una sesion de
    codigo por cada alta de tenant.
    """
    # Nombre interno, estable. Es lo que se guarda por persona, asi que
    # cambiarlo deja huerfanas a las que ya lo tenian.
    nombre: str
    # Como se lee en pantalla.
    etiqueta: str
    # Agentes que precarga. Puede ser mas de uno, y puede estar vacio: un area
    # que todavia no tiene agente propio se puede declarar igual para poder
    # organizar a la gente, aunque no le de capacidades.
    agentes: list[str] = Field(default_factory=list)
    # Como se distingue el area de un vistazo en una pantalla.
    #
    # Van aca y no en el frontend por el mismo motivo que 'etiqueta': las
    # areas de un ISP no son las del siguiente. Una tabla de colores escrita
    # en la pantalla obligaria a tocar codigo para cada empresa nueva --
    # justo lo que 'nombre'/'etiqueta' ya existen para evitar.
    #
    # Los DOS son opcionales, y a proposito: sin ellos la pantalla deriva un
    # color estable del nombre y dibuja las iniciales. Un area recien
    # declarada se ve distinta de las demas sin que nadie elija nada; quien
    # quiera elegir, elige.
    #
    # 'icono' nombra un dibujo de un catalogo generico que conoce la pantalla
    # (llave, factura, edificio, red...), NUNCA un dibujo "de soporte de
    # Rapilink": el vocabulario es del producto, la eleccion es de la empresa.
    icono: str = ""
    color: str = ""

    @field_validator("color")
    @classmethod
    def _color_hex(cls, v: str) -> str:
        """
        Se acepta solo '#rrggbb'. No es purismo: el valor entra directo a un
        'style' de la pantalla, y aceptar cualquier texto seria dejar que la
        config escriba CSS arbitrario en la interfaz de todos.
        """
        if v and not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            raise ValueError(
                f"areas: color '{v}' invalido -- se espera '#rrggbb' (ej. '#2f6fed')")
        return v


class IdentidadExterna(Base):
    """
    Como se identifica a un colaborador en el sistema donde de verdad se
    trabaja la orden -- para poder asignarle el trabajo a nombre suyo y no de
    un usuario fijo escrito en la config.

    Todo lo especifico del proveedor vive ACA, en el tenant: que herramienta
    lista a la gente y en que campos viene su id y su nombre. El nucleo
    ejecuta lo que se le declare y no sabe de quien se trata.
    """
    # Nombre interno del sistema. Es la llave con la que se guarda cada
    # identidad, asi que cambiarlo despues deja huerfanas las ya guardadas.
    sistema: str
    # Como se llama en pantalla ("Usuario en WispHub").
    etiqueta: str
    # Herramienta del catalogo que devuelve la gente asignable.
    herramienta_listado: str
    # En que campos de esa respuesta viene el id y el nombre de cada persona.
    campo_identificador: str = "id"
    campo_nombre: str = "nombre"


class TicketEscalado(Base):
    """
    Que ticket operativo se crea cuando un caso se pasa a una persona.

    Distinto del agendamiento automatico, y la diferencia es el proposito:
    'agendamiento_automatico' decide SI corresponde despachar un tecnico, y
    por eso pasa por un verificador contra el manual. Esto no decide nada --
    el caso YA se escalo-- solo deja el trabajo anotado donde la operacion
    lo ve, con un tecnico asignado, en vez de que viva solo en la bandeja
    interna del asistente.

    'condiciones' elige el ticket segun lo que la traza ya probo, porque el
    ASUNTO es lo que le dice al tecnico de que se trata antes de abrir nada:
    una lentitud sin causa identificada y una con la optica fuera de rango
    son dos trabajos distintos y en el catalogo del ISP suelen ser dos
    asuntos distintos. Sin condiciones, es el caso por defecto -- va ultimo.
    """
    herramienta: str
    condiciones: list[Precondicion] = Field(default_factory=list)
    # A que area del equipo le corresponde este trabajo. Con eso el codigo
    # resuelve a nombre de QUIEN se abre el ticket, en vez de dejarlo en el
    # tecnico fijo de la herramienta -- que hacia que todos los tickets de
    # todos los casos cayeran sobre la misma persona.
    #
    # Vacio = se usa el fijo. Es el respaldo, no un error: un caso que no
    # corresponde a ningun area declarada tiene que poder abrir ticket igual.
    area: str = ""
    # Con que asunto y prioridad entra. Vacios = los de la herramienta.
    #
    # Estan ACA y no en una herramienta por variante porque la variante la
    # decide la traza: dos entradas del mismo caso, con condiciones distintas,
    # abren tickets distintos. Declarar una herramienta casi identica por cada
    # combinacion es como se llega a nueve que solo se diferencian en dos
    # cadenas.
    #
    # El asunto tiene que existir en el catalogo del proveedor: verificado el
    # 22/08/2026, WispHub RECHAZA con 400 uno que no este en su lista.
    asunto: str = ""
    prioridad: str = ""


class Escalamiento(Base):
    activar_si: list[str] = Field(default_factory=list)
    destino_rol: str | None = None
    mensaje: str = ""
    # El mensaje CAMBIA segun por que se escala, porque no todos los motivos
    # son una queja. El generico esta escrito para alguien molesto ("entiendo
    # tu molestia") y suena mal cuando el cliente pidio un tramite y todo
    # salio bien: se lo vio en produccion el 28/08/2026 con un cambio de clave
    # de WiFi, donde el cliente no se habia quejado de nada.
    #
    # Clave = motivo de 'activar_si'. Un motivo sin entrada usa el generico,
    # asi que agregar uno nuevo nunca deja al cliente sin respuesta.
    mensajes_por_motivo: dict[str, str] = Field(default_factory=dict)
    # Y que decirle cuando el traspaso NO se pudo registrar en ningun lado.
    # Los de arriba anuncian algo que ya paso; este anuncia que no paso, y por
    # eso no puede ser el mismo texto con otro tono: los otros cierran el
    # tema, este tiene que pedirle al cliente que vuelva a escribir, porque
    # el reintento necesita un mensaje suyo.
    mensaje_si_falla: str = ""
    # Horas sin que el cliente conteste antes de cerrar el caso solo. 0 = nunca
    # se cierra por tiempo, que es el valor por defecto: un caso que se cierra
    # sin que nadie lo decida es peor que uno viejo abierto, y ninguna empresa
    # deberia estrenar ese comportamiento sin pedirlo.
    #
    # Se cuenta desde el ULTIMO mensaje del cliente. Si escribe despues de que
    # se cerro, el asistente lo atiende normal y abre lo que haga falta -- no
    # se pierde nada, se cierra lo que quedo esperando.
    cerrar_sin_respuesta_horas: int = 0
    # Que se deja escrito en el ticket del sistema del ISP al cerrarlo asi. Sin
    # una linea que diga por que, quien lo audite tiene que reconstruirlo desde
    # el chat -- justo lo que ese registro existe para evitar.
    texto_cierre_sin_respuesta: str = ""
    # Y lo que se deja escrito cuando el que cierra es el propio cliente
    # diciendo que ya quedo resuelto.
    texto_cierre_confirmado: str = ""
    # Y lo que se le dice AL CLIENTE en ese ultimo mensaje. Distinto del de
    # arriba: aquel lo lee quien audita el ticket, este lo lee el cliente.
    mensaje_cierre_cliente: str = ""
    # Un escape a humano SIEMPRE disponible, no solo por deteccion automatica.
    siempre_disponible: bool = True
    # Caso de 'manual.casos' -> nombre de Herramienta a ejecutar en CODIGO
    # (nunca via tool-calling del modelo) cuando el verificador de
    # nucleo/seguimiento/agendamiento.py confirma que el checklist de ese
    # caso quedo completo. Vacio por defecto: ningun tenant ni ningun caso
    # agenda solo sin declararlo a proposito aca.
    agendamiento_automatico: dict[str, str] = Field(default_factory=dict)
    # Caso de 'manual.casos' -> que ticket operativo se crea al escalar. Se
    # evalua en orden y gana el PRIMERO cuyas condiciones cumpla la traza;
    # una entrada sin condiciones es el caso por defecto. Ver TicketEscalado.
    ticket_al_escalar: dict[str, list[TicketEscalado]] = Field(default_factory=dict)
    # Caso de 'manual.casos' -> area del equipo que ATIENDE la conversacion.
    #
    # Distinto del area del ticket, aunque casi siempre coincidan: una cosa es
    # quien sigue hablando con el cliente y otra quien hace el trabajo. Pueden
    # ser areas distintas y el modelo tiene que poder decirlo.
    #
    # Sin esto el caso se crea SIN asignar, y ahi no queda "visible para
    # todos": el CRM muestra a quien no es administrador solo lo suyo, asi que
    # un caso sin dueño es un caso que el equipo NO VE. Medido el 23/08/2026
    # sobre la instancia real: 54 casos escalados, y las dos personas del
    # equipo veian cero.
    area_por_caso: dict[str, str] = Field(default_factory=dict)
    # Estados en los que un caso ya NO ocupa a nadie. Todo lo demas cuenta
    # como carga: lo que la persona ya empezo y lo que tiene esperando.
    #
    # Contar solo lo empezado dejaba invisible la cola de alguien: quien tiene
    # ocho casos sin abrir figuraba tan libre como quien no tiene ninguno, y
    # se le seguian dando mas.
    #
    # Se declara por empresa porque son las palabras del CRM de cada una, no
    # del motor.
    estados_cerrados: list[str] = Field(default_factory=list)
    # Caso de 'manual.casos' -> condiciones sobre la TRAZA que, si se
    # cumplen, bastan para agendar SIN pasar por el verificador del manual.
    #
    # Existe porque el verificador contrasta contra el procedimiento que el
    # RAG recupere, y ese procedimiento esta escrito para una persona que
    # atiende, no para un agente que ya midio la OLT. Visto el 21/08/2026:
    # una falla sin señal optica quedaba sin agendar porque el checklist
    # recuperado (el de WiFi, traido por parecido) exigia "¿que mensaje
    # aparece en el dispositivo?" -- una pregunta imposible de contestar
    # cuando no hay ninguna conexion de la cual leer un mensaje.
    #
    # Solo para ramas donde la evidencia YA es dura y viene de la red, no
    # del relato del cliente. Cada condicion usa la misma forma que
    # 'Herramienta.exige_previas' y se evalua contra el historial: si
    # CUALQUIERA se cumple, se agenda. Vacio = todo pasa por el verificador,
    # que es el comportamiento de siempre.
    evidencia_suficiente: dict[str, list[Precondicion]] = Field(default_factory=dict)
    # El reverso: condiciones de la traza con las que agendar seria un ERROR,
    # aunque el checklist este completo. Existe por la caida compartida --
    # desde la ONU de un cliente se ve IGUAL que su propia fibra cortada, que
    # es justo la evidencia que agenda sola. Sin esto, treinta reportes de la
    # misma caida despachan treinta tecnicos. Ver
    # nucleo/seguimiento/agendamiento.py:veto_de_agendamiento.
    no_agendar_si: dict[str, list[Precondicion]] = Field(default_factory=dict)
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
    # Horas sin un solo mensaje despues de las cuales la conversacion se cierra
    # sola y el proximo mensaje abre una nueva. None = no se cierra por tiempo
    # (el comportamiento viejo).
    #
    # Existe porque sin esto una conversacion no se cierra nunca salvo que el
    # evaluador la marque resuelta o la cierre una persona: medido el
    # 18/08/2026, una acumulo 67 mensajes a lo largo de 180 horas, mezclando
    # tres problemas distintos. Con ese contexto el modelo vuelve a preguntar
    # lo ya contestado y, peor, repite mediciones viejas como si fueran de
    # ahora.
    #
    # Lo que se sabia del cliente NO se pierde al cerrar: se guarda un resumen
    # (ver nucleo/seguimiento/resumen.py) que se le entrega al modelo cuando
    # esa persona vuelve a escribir.
    horas_inactividad_cierra: int | None = Field(default=None, ge=1)
    # Separada de la de arriba y mucho mas corta, a proposito: una conversacion
    # escrita es barata de guardar y util para depurar; una foto pesa y puede
    # mostrar la casa, la cedula o una cara. La foto sirve para resolver el
    # caso, y un caso vive dias. Ver supabase/202608121842_multimedia.sql.
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
    # Lo que se le pregunta al cliente ANTES de cerrar su conversacion.
    #
    # Ninguna conversacion se cierra por lo que el modelo interprete de un
    # "ok" o un "gracias": se le pregunta, y se cierra con lo que conteste. El
    # 28/08/2026 se cerro un caso --chat, ticket y todo-- porque el cliente
    # contesto "ok" a un aviso del asistente, con el trabajo sin hacer.
    #
    # Vacio = se cierra sin preguntar (comportamiento viejo). Se declara por
    # empresa porque es texto que lee un cliente, y el tono es de cada una.
    pregunta_antes_de_cerrar: str = ""


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


class ZonaConteo(Base):
    """Una zona real del proveedor (nodo de red -- router/servidor) con
    cuantos clientes tiene DENTRO de una localidad puntual. Ver
    LocalidadZona: una misma localidad puede repartirse en mas de una
    zona, asi que esto vive en una lista, no en un campo suelto."""
    zona_id: int
    zona_nombre: str
    n_clientes: int


class LocalidadZona(Base):
    """
    Una localidad observada en el proveedor, con la(s) zona(s) real(es)
    donde tiene clientes -- nunca la escribe una persona, solo la llena
    nucleo/herramientas/localidades.py::sincronizar() recorriendo el
    catalogo completo de clientes. Reemplaza el chequeo de cobertura en
    vivo que 'ventas' hacia con contar_clientes en cada turno (agregaba
    1-2s de latencia por mensaje -- ver incidente 20/08/2026, "doña
    manuela") y le da a PlanVenta.zonas algo real contra que comparar en
    vez de texto libre por localidad.

    Una misma localidad puede caer en mas de una zona real (verificado:
    "DOÑA MANUELA" tiene clientes en dos routers distintos) -- por eso
    'zonas' es una lista, nunca una zona dominante unica.
    """
    localidad: str                     # nombre a mostrar (variante mas comun)
    zonas: list[ZonaConteo] = Field(default_factory=list)
    n_clientes: int = 0                # total, suma de zonas[].n_clientes


class PlanVenta(Base):
    """
    Un plan que se OFRECE a un prospecto nuevo -- lista curada por el
    tenant, separada a proposito del catalogo tecnico del proveedor (ej.
    WispHub trae 55 entradas para Rapilink, con variantes duplicadas y
    nombres legacy pensados para facturar clientes existentes, no para
    vender). Agregado 19/08/2026: un prospecto pregunto por "300 megas" y
    el catalogo crudo devolvio TRES resultados distintos con ese numero --
    cual de esos es el que de verdad se vende hoy es una decision humana,
    no algo que el modelo deba adivinar ni algo que deba vivir hardcodeado
    en un YAML que un desarrollador edita.
    """
    nombre_wisphub: str
    # Tiene que coincidir EXACTO con un nombre real del catalogo del
    # proveedor (verificar contra consultar_planes antes de cargar uno
    # nuevo aca -- mismo principio de todo el proyecto: la documentacion,
    # y en este caso el nombre que alguien recuerda, es una hipotesis).
    # IDs de zona real (LocalidadZona.zonas[].zona_id -- el catalogo del
    # proveedor, ej. /api/zonas/ de WispHub). Vacio = se ofrece en
    # CUALQUIER zona con cobertura. Reemplaza 'localidades: list[str]'
    # (texto libre) -- ver incidente 20/08/2026: un barrio real (Doña
    # Manuela) puede caer en mas de una zona, y el texto libre no lo podia
    # representar ni mantenerse sincronizado solo con la realidad.
    zonas: list[int] = Field(default_factory=list)


# =============================================================================
#  RAIZ
# =============================================================================

class TenantConfig(Base):
    # Campos que NO son configuracion sino la SALIDA de un proceso: los
    # produce el sistema, no los escribe una persona, y se reemplazan enteros
    # cada vez que ese proceso corre.
    #
    # cli/cargar_config.py los excluye al exportar a YAML. Sin eso, un
    # 'git diff' del archivo mostraria cientos de lineas generadas por
    # maquina cambiando en cada sincronizacion -- hoy 'localidades' son 128
    # localidades con sus zonas y conteos-- y el cambio real quedaria
    # enterrado ahi. Viven solo en la base, que es donde el motor los lee.
    #
    # Vive aca y no en el exportador a proposito: quien agrega un campo
    # sincronizado nuevo lo declara junto al campo, no en un archivo de cli/
    # que no va a recordar tocar.
    SINCRONIZADOS: ClassVar[tuple[str, ...]] = (
        "localidades", "localidades_actualizado_en")

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
    # Lista curada de planes para OFRECER a un prospecto nuevo -- ver
    # PlanVenta arriba sobre por que es distinta del catalogo tecnico del
    # proveedor. Vacio = ningun plan configurado todavia: el rol de ventas
    # tiene que decirlo asi, nunca caer de vuelta al catalogo crudo (eso
    # es exactamente el problema que este campo resuelve).
    planes_venta: list[PlanVenta] = Field(default_factory=list)
    # Catalogo localidad -> zona(s) real(es), sincronizado bajo demanda --
    # ver LocalidadZona arriba y nucleo/herramientas/localidades.py. Nunca
    # se edita a mano: se reemplaza entero cada vez que corre el sync.
    localidades: list[LocalidadZona] = Field(default_factory=list)
    localidades_actualizado_en: str | None = None  # ISO, ultima sincronizacion
    canales: Canales = Field(default_factory=Canales)
    escalamiento: Escalamiento = Field(default_factory=Escalamiento)
    # Opcional: sin esto, el asistente no intenta identificar a nadie en
    # ningun sistema externo y la pantalla no ofrece el campo.
    identidad_externa: IdentidadExterna | None = None
    # Las areas de trabajo del equipo. Vacio = la pantalla no ofrece area.
    areas: list[AreaDeTrabajo] = Field(default_factory=list)
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

        # Una 'entrega_variable' que apunte a una variable inexistente falla
        # SIN error visible: la herramienta se ejecuta, el registro queda, y
        # el modelo se queda sin el dato que tenia que entregar -- y como el
        # dato ya no esta en el prompt, no tiene de donde sacarlo. El cliente
        # ve una respuesta a medias y nadie sabe por que.
        # Mismo motivo, y el mismo fallo silencioso: la llamada sale sin ese
        # argumento y la API la rechaza -- o peor, la acepta con un dato de
        # menos.
        for h in self.herramientas:
            faltan_vars = [v for v in h.argumentos_desde_variables.values()
                           if v not in self.variables_tenant]
            if faltan_vars:
                raise ValueError(
                    f"'{h.nombre}': 'argumentos_desde_variables' nombra "
                    f"{sorted(faltan_vars)}, que no esta en 'variables_tenant'. "
                    f"Declararla ahi (se edita en /configuracion/variables).")

        for h in self.herramientas:
            if h.entrega_variable and h.entrega_variable not in self.variables_tenant:
                raise ValueError(
                    f"'{h.nombre}': 'entrega_variable' nombra "
                    f"'{h.entrega_variable}', que no esta en 'variables_tenant'. "
                    f"Declararla ahi (se edita en /configuracion/variables) o "
                    f"quitar la referencia.")

        # Un 'escalar_si_falla' que apunte a un motivo no declarado no daria
        # ningun error al ejecutarse: escalaria con una razon que el resto
        # del sistema no reconoce y que nadie puede filtrar en la bandeja.
        for motivo in self.escalamiento.mensajes_por_motivo:
            if motivo not in self.escalamiento.activar_si:
                raise ValueError(
                    f"escalamiento.mensajes_por_motivo tiene '{motivo}', que no "
                    f"esta en activar_si -- seria un mensaje que no se muestra "
                    f"nunca, y nadie lo notaria")
        for h in self.herramientas:
            if h.resumen_desde and not (h.escalar_al_completar or h.escalar_si_falla):
                raise ValueError(
                    f"herramientas['{h.nombre}'].resumen_desde dice "
                    f"'{h.resumen_desde}', pero esa herramienta no escala: sin "
                    f"'escalar_al_completar' ni 'escalar_si_falla' ese resumen "
                    f"no lo lee nadie nunca")
            if h.escalar_al_completar and h.escalar_al_completar not in self.escalamiento.activar_si:
                raise ValueError(
                    f"herramientas['{h.nombre}'].escalar_al_completar dice "
                    f"'{h.escalar_al_completar}', que no esta en "
                    f"escalamiento.activar_si -- el motivo tiene que existir "
                    f"o la escalada quedaria sin razon declarada")
            if h.escalar_si_falla and h.escalar_si_falla not in self.escalamiento.activar_si:
                raise ValueError(
                    f"herramienta '{h.nombre}': 'escalar_si_falla' declara el "
                    f"motivo '{h.escalar_si_falla}', que no esta en "
                    f"escalamiento.activar_si "
                    f"({', '.join(self.escalamiento.activar_si) or 'vacio'})")

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

        # Misma exigencia para el atajo por evidencia: un caso mal escrito o
        # una herramienta que ya no existe NO rompe nada en vivo -- cae al
        # verificador del manual, que es el camino de siempre -- y por eso
        # mismo es peligroso: desde afuera se ve identico a "la evidencia no
        # alcanzaba", y nadie se entera de que la condicion nunca se evaluo.
        # Se cae al cargar, no en el turno que la necesitaba.
        for caso, condiciones in self.escalamiento.evidencia_suficiente.items():
            if caso not in casos_manual:
                raise ValueError(
                    f"escalamiento.evidencia_suficiente['{caso}'] no es un "
                    f"caso de 'manual.casos' ({sorted(casos_manual)})")
            if caso not in self.escalamiento.agendamiento_automatico:
                raise ValueError(
                    f"escalamiento.evidencia_suficiente['{caso}'] no sirve de "
                    "nada: ese caso no tiene agendamiento automatico, asi que "
                    "la evidencia nunca se consulta")
            for c in condiciones:
                if c.herramienta not in nombres_herr:
                    raise ValueError(
                        f"escalamiento.evidencia_suficiente['{caso}'] espera la "
                        f"herramienta inexistente '{c.herramienta}'")

        # Los agentes que precarga un area tienen que existir Y ser internos.
        # Un area que apunta a un agente inexistente no falla al usarla: deja
        # a la persona sin capacidades y se ve igual que "todavia no le
        # asignaron nada". Se cae al cargar, que es donde se nota.
        internos = {n for n, r in self.roles.items()
                    if r.orientado_a == "colaborador"}
        vistos = set()
        for area in self.areas:
            if area.nombre in vistos:
                raise ValueError(f"areas: '{area.nombre}' esta declarada dos veces")
            vistos.add(area.nombre)
            for agente in area.agentes:
                if agente not in self.roles:
                    raise ValueError(
                        f"areas['{area.nombre}'] precarga el agente inexistente "
                        f"'{agente}'")
                if agente not in internos:
                    raise ValueError(
                        f"areas['{area.nombre}'] precarga '{agente}', que atiende "
                        f"al cliente final -- a un colaborador solo se le asignan "
                        f"agentes internos ({', '.join(sorted(internos))})")

        # El ticket que se crea al escalar: mismo criterio fail-closed. Un
        # caso mal escrito aca no rompe nada en vivo -- la escalada ocurre
        # igual, solo que sin ticket-- y por eso hay que atajarlo al cargar:
        # desde afuera se ve identico a "todavia no le toca ticket a este
        # caso", y nadie se entera de que la operacion dejo de recibir el
        # trabajo anotado.
        for caso, entradas in self.escalamiento.ticket_al_escalar.items():
            if caso not in casos_manual:
                raise ValueError(
                    f"escalamiento.ticket_al_escalar['{caso}'] no es un caso "
                    f"de 'manual.casos' ({sorted(casos_manual)})")
            for entrada in entradas:
                if entrada.herramienta not in nombres_herr:
                    raise ValueError(
                        f"escalamiento.ticket_al_escalar['{caso}'] apunta a la "
                        f"herramienta inexistente '{entrada.herramienta}'")
                for c in entrada.condiciones:
                    if c.herramienta not in nombres_herr:
                        raise ValueError(
                            f"escalamiento.ticket_al_escalar['{caso}'] espera "
                            f"la herramienta inexistente '{c.herramienta}'")
            # Una entrada CON condiciones despues de una sin ellas no se
            # alcanza nunca: la de por defecto matchea todo. Es un error de
            # orden y se ve solo leyendo el YAML con atencion, que es
            # justamente cuando no se ve.
            for i, entrada in enumerate(entradas[:-1]):
                if not entrada.condiciones:
                    raise ValueError(
                        f"escalamiento.ticket_al_escalar['{caso}']: la entrada "
                        f"{i} no tiene condiciones, asi que gana siempre y las "
                        f"que siguen no se evaluan nunca. El caso por defecto "
                        f"va ultimo.")

        # Mismo control para el veto: si la herramienta que tendria que
        # frenar el agendamiento no existe, el veto no frena nada y no lo
        # dice nadie.
        for caso, condiciones in self.escalamiento.no_agendar_si.items():
            if caso not in casos_manual:
                raise ValueError(
                    f"escalamiento.no_agendar_si['{caso}'] no es un caso de "
                    f"'manual.casos' ({sorted(casos_manual)})")
            if caso not in self.escalamiento.agendamiento_automatico:
                raise ValueError(
                    f"escalamiento.no_agendar_si['{caso}'] no sirve de nada: "
                    "ese caso no agenda solo, asi que no hay nada que vetar")
            for c in condiciones:
                if c.herramienta not in nombres_herr:
                    raise ValueError(
                        f"escalamiento.no_agendar_si['{caso}'] espera la "
                        f"herramienta inexistente '{c.herramienta}'")

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
    # Corriendo como script, la raiz del repo no esta en sys.path y los
    # validadores que importan otros modulos del nucleo (ej. el de
    # 'normalizar_tratamiento', que consulta nucleo/modelo/tuteo.py) fallan
    # con ModuleNotFoundError -- un error que no se parece en nada a "falta
    # una ruta". Se agrega antes de validar nada.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
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
