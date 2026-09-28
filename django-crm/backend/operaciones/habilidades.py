# -*- coding: utf-8 -*-
"""
================================================================================
 HABILIDADES OPERATIVAS  --  la ficha de lo que el Supervisor ya sabe hacer
================================================================================

QUE ES ESTE ARCHIVO, Y QUE NO ES
--------------------------------
Es el REGISTRO LITERAL de las 14 habilidades operativas de M09. No agrega
ninguna capacidad: cada ficha DESCRIBE una funcion que ya existe y ya corre en
'supervisor.py'. Si una ficha y el codigo dijeran cosas distintas, el que manda
es el codigo y la diferencia se reporta -- nunca al reves.

POR QUE EN CODIGO Y NO EN UNA TABLA  --  decision D-1
-----------------------------------------------------
El paso D-1 lo midio y lo cerro: una habilidad del Motor
('asistente.habilidades') es un DATO -- texto que se inyecta en el prompt de un
modelo. Una habilidad de M09 es CODIGO -- una funcion determinista que consulta
y emite una señal. Coinciden en 3 de 12 caracteristicas, y las tres son
propiedades transversales del sistema (tenant, no-ejecucion, auditoria), no del
concepto.

Guardar la definicion de un detector en una fila crearia DOS definiciones -- la
fila y la funcion -- que divergirian en el primer cambio. Es exactamente el
error que 'nucleo/programador/registro.py' ya rechazo por escrito:

    "un 'job_code' que llega de una fila de la base terminando en una busqueda
     que resuelve a un callable convierte al catalogo --un dato-- en codigo
     ejecutable. El catalogo lo edita un operador; el codigo lo revisa alguien."

Por eso: diccionario literal, congelado al importar. Sin 'importlib', sin
registro dinamico, sin nombre que venga de afuera. Lo mismo que el registro de
trabajos, por el mismo motivo.

LA CONSECUENCIA BUSCADA
-----------------------
Cambiar una habilidad exige un despliegue y pasa por revision de codigo y por
las pruebas que ya existen. Una fila editable no tendria ninguna de las dos
cosas. La "desventaja" es la garantia.

UNA HABILIDAD NO CONCEDE NADA
-----------------------------
Una ficha documenta que datos se consultan y que analisis se hace. NO concede
permisos, NO eleva autonomia y NO habilita ninguna herramienta. Las 14 declaran
'herramientas_escritura' vacio, y hay una prueba que lo exige: la separacion
habilidad / herramienta / autorizacion / ejecucion sigue viviendo donde vivia
--la frontera externa y el interruptor-- y este archivo no la toca.

QUE SE PUEDE RESPONDER GRACIAS A ESTO
-------------------------------------
    referencia()  ->  "habilidad:H-01@1"
    huella()      ->  sha256 del contenido literal, reproducible

Con la referencia guardada en 'PropuestaSupervisor.conocimiento_version', una
propuesta de hace seis meses sigue diciendo con que definicion se emitio, aunque
la habilidad ya vaya por la v3.
================================================================================
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from types import MappingProxyType

# --- estados de una ficha -----------------------------------------------------
#  'vigente'  la habilidad opera hoy: hay un detector corriendo.
#  'bloqueada' la ficha existe y el detector tambien, pero le falta una decision
#              externa para poder confiar en su resultado. Ver H-05 / D-4.
VIGENTE = "vigente"
BLOQUEADA = "bloqueada"

DOMINIO = "dominio"
TRANSVERSAL = "transversal"


@dataclass(frozen=True)
class Habilidad:
    """
    La ficha de una capacidad que M09 ya tiene.

    Todo son tuplas y no listas a proposito: una ficha no se edita en caliente.
    'frozen=True' lo hace cumplir en Python; el diccionario de abajo va envuelto
    en MappingProxyType para que tampoco se pueda agregar ni quitar una entrada.
    """

    id: str
    nombre: str
    tipo: str                     # DOMINIO | TRANSVERSAL
    version: int
    vigente_desde: str            # AAAA-MM-DD
    estado: str                   # VIGENTE | BLOQUEADA

    proposito: str
    responsabilidad: str
    alcance: str

    # Lo que la habilidad NO resuelve. Va en la ficha porque el limite es parte
    # de la definicion: una habilidad sin borde se usa para cualquier cosa.
    fuera_de_alcance: tuple[str, ...] = ()
    activacion: tuple[str, ...] = ()
    entradas: tuple[str, ...] = ()
    datos: tuple[str, ...] = ()
    reglas: tuple[str, ...] = ()
    procedimiento: tuple[str, ...] = ()

    # Vacio = NO existe documento de conocimiento todavia. No se inventa uno.
    conocimiento: tuple[str, ...] = ()

    herramientas_lectura: tuple[str, ...] = ()
    # SIEMPRE vacio en esta etapa. Hay una prueba que lo exige.
    herramientas_escritura: tuple[str, ...] = ()

    salida: str = ""
    evidencia: tuple[str, ...] = ()
    incertidumbre: tuple[str, ...] = ()
    escalamiento: tuple[str, ...] = ()
    nivel: int = 1                # 0 observar · 1 recomendar. Nada mas.
    metricas: tuple[str, ...] = ()

    # El enganche con el codigo real. 'detector' es la funcion de supervisor.py;
    # vacio en las transversales, que no son detectores.
    detector: str = ""
    senal: str = ""
    huella_condicion: str = ""

    # ---------------------------------------------------------------- refs ---
    def referencia(self) -> str:
        """
        Lo que se guarda en 'PropuestaSupervisor.conocimiento_version'.

        El prefijo 'habilidad:' no es decoracion: el campo se llama
        'conocimiento_version' y lo que aca se guarda es la version de la
        HABILIDAD, no la de un documento de conocimiento. Sin el prefijo, quien
        lea la fila dentro de un año creeria que existe un conocimiento
        versionado que hoy no existe. Ver el docstring de 'referencia_de'.
        """
        return f"habilidad:{self.id}@{self.version}"

    def huella(self) -> str:
        """
        sha256 del contenido literal de la ficha. Reproducible.

        Sirve para demostrar 'esta era exactamente la definicion cuando se
        genero aquella propuesta'. Se calcula sobre una serializacion canonica
        --campos ordenados, separadores fijos, UTF-8-- para que dos corridas del
        mismo contenido den el mismo valor en cualquier maquina.
        """
        return hashlib.sha256(self.canonico().encode("utf-8")).hexdigest()

    def canonico(self) -> str:
        """La serializacion que se hashea. Explicita, para poder auditarla."""
        partes = []
        for clave in sorted(asdict(self)):
            valor = getattr(self, clave)
            if isinstance(valor, tuple):
                texto = "|".join(valor)
            else:
                texto = str(valor)
            partes.append(f"{clave}={texto}")
        return "\n".join(partes)


# =============================================================================
#  LAS 14 FICHAS
# =============================================================================
#  Diez de dominio (una por detector de supervisor.py) y cuatro transversales
#  (una por funcion compartida). No hay ninguna mas y no hay ninguna menos: son
#  exactamente las capacidades que M09 ya tiene.

_FICHAS: tuple[Habilidad, ...] = (

    # ---------------------------------------------------------------- M01 ---
    Habilidad(
        id="H-01",
        nombre="Detectar caso abierto sin resolución registrada",
        tipo=DOMINIO, version=1, vigente_desde="2026-09-17", estado=VIGENTE,
        proposito=(
            "Señalar casos que llevan más tiempo abierto del esperado sin que "
            "el sistema tenga registro de su resolución."),
        responsabilidad=(
            "Afirmar únicamente lo que el dato sostiene: que no hay registro de "
            "cierre. Nunca que nadie lo atendió."),
        alcance="Casos del CRM con 'resolved_at' nulo.",
        fuera_de_alcance=(
            "No juzga la calidad de la atención.",
            "No determina incumplimiento de SLA: 'first_response_at' está "
            "poblado en 4 de 165 casos y M09-C prohíbe usarlo para eso.",
            "No nombra responsables.",
        ),
        activacion=("El caso sigue abierto y su antigüedad supera la ventana.",),
        entradas=("org", "ahora"),
        datos=("case.id", "case.name", "case.created_at", "case.status",
               "case.priority", "case.resolved_at"),
        reglas=(
            "Ventana: DIAS_CASO_ANTIGUO = 7.",
            "La huella es 'abierto_sin_resolucion': la magnitud (los días) NO "
            "entra, porque avanza sola y una propuesta rechazada volvería "
            "mañana con otra huella.",
        ),
        procedimiento=(
            "1. Tomar los casos con resolved_at nulo y created_at anterior al corte.",
            "2. Calcular los días transcurridos.",
            "3. Emitir una señal por caso, citando fecha y estado reales.",
        ),
        conocimiento=(),          # el umbral de 7 días no está documentado
        herramientas_lectura=("ORM: cases.Case",),
        herramientas_escritura=(),
        salida="list[Senal] con tipo 'caso_abierto_antiguo'.",
        evidencia=(
            "observado: fecha de apertura y días transcurridos",
            "observado: estado actual del caso",
            "calculado: componentes de la prioridad",
        ),
        incertidumbre=(
            "Un caso puede haber sido atendido por un canal que el CRM no "
            "registra: la ausencia de cierre NO prueba ausencia de atención.",
            "La antigüedad no distingue un caso complejo de uno olvidado.",
        ),
        escalamiento=(
            "Al Supervisor: siempre; la habilidad no emite propuestas.",
            "A humano: la revisión humana es el único camino (M09-F).",
        ),
        nivel=1,
        metricas=(
            "Falsos negativos: cruce SQL independiente contra el conteo emitido. "
            "Medido en M09-E: 37 = 37.",
            "Exactitud de la evidencia: cada fecha, estado y conteo citado debe "
            "coincidir con la base. Medido: 52 de 52 sin problemas.",
        ),
        detector="_casos_abiertos_antiguos",
        senal="caso_abierto_antiguo",
        huella_condicion="abierto_sin_resolucion",
    ),

    # ---------------------------------------------------------------- M10 ---
    Habilidad(
        id="H-02",
        nombre="Evaluar completitud de datos de una orden",
        tipo=DOMINIO, version=1, vigente_desde="2026-09-17", estado=VIGENTE,
        proposito=(
            "Señalar que a un objeto concreto le falta un campo concreto que se "
            "puede nombrar."),
        responsabilidad=(
            "No ser un comodín. Solo se emite cuando hay un objeto y un campo "
            "identificables; nunca como 'faltan datos' en abstracto."),
        alcance="Órdenes de trabajo con programación publicada.",
        fuera_de_alcance=(
            "No completa el dato.",
            "No infiere cuál debería ser el valor faltante.",
        ),
        activacion=("Existe una programación publicada y la orden no refleja el dato.",),
        entradas=("org", "ahora"),
        datos=("campo_orden_trabajo.programada_para",
               "ProgramacionOrden.estado", "ProgramacionSemanal.estado"),
        reglas=(
            "Es la única señal de NIVEL 0: informa, no recomienda una acción "
            "sobre el mundo.",
            "Huella fija 'campo:programada_para': identifica el campo, no su valor.",
        ),
        procedimiento=(
            "1. Buscar órdenes con programación vigente publicada.",
            "2. Comprobar si el dato correspondiente está presente en la orden.",
            "3. Si falta, nombrar el campo exacto en la evidencia.",
        ),
        conocimiento=(),
        herramientas_lectura=("ORM: campo.OrdenTrabajo", "ORM: operaciones.ProgramacionOrden"),
        herramientas_escritura=(),
        salida="list[Senal] con tipo 'dato_incompleto'.",
        evidencia=("observado: el campo faltante, nombrado",
                   "observado: el plan que sí lo tiene"),
        incertidumbre=(
            "Un campo vacío puede ser un dato que todavía no corresponde cargar, "
            "no un olvido.",
        ),
        escalamiento=("Al Supervisor: siempre.",),
        nivel=0,
        metricas=("Proporción de señales donde el campo nombrado existe y está "
                  "efectivamente vacío.",),
        detector="_ordenes_desincronizadas",
        senal="dato_incompleto",
        huella_condicion="campo:programada_para",
    ),

    # ---------------------------------------------------------------- M03 ---
    Habilidad(
        id="H-03",
        nombre="Determinar si una orden de trabajo tiene programación vigente",
        tipo=DOMINIO, version=1, vigente_desde="2026-09-17", estado=VIGENTE,
        proposito="Señalar órdenes que nadie planificó y que todavía no empezaron.",
        responsabilidad=(
            "No confundir 'sin fecha' con 'sin programar'. Es la corrección que "
            "M09-D introdujo y M09-E validó."),
        alcance="Órdenes de trabajo activas.",
        fuera_de_alcance=(
            "No propone fecha.",
            "No asigna técnico.",
            "No programa: M03 es el dueño del efecto.",
        ),
        activacion=("La orden no empezó y no tiene ninguna ProgramacionOrden "
                    "en estado planificada o confirmada.",),
        entradas=("org", "ahora"),
        datos=("campo_orden_trabajo.estado_operativo",
               "campo_orden_trabajo.programada_para",
               "campo_orden_trabajo.iniciada_en",
               "ProgramacionOrden.estado"),
        reglas=(
            "'programada_para IS NULL' NO implica sin programar. Medido en "
            "M09-E: las 3 OT reales tienen ese campo nulo y ya estaban en campo "
            "o terminadas; la condición vieja habría dado 3 falsos positivos.",
            "Huella 'estado:<estado_operativo>': si el estado cambia, es otra "
            "condición.",
        ),
        procedimiento=(
            "1. Leer el estado operativo de la orden.",
            "2. Si ya está en campo, completada, cancelada o en corrección: "
            "NO hay señal.",
            "3. Buscar una ProgramacionOrden en planificada o confirmada.",
            "4. Si existe: NO hay señal.",
            "5. Si no existe: emitir señal citando el estado y la ausencia.",
        ),
        conocimiento=(),          # estados que implican trabajo iniciado: sin documentar
        herramientas_lectura=("ORM: campo.OrdenTrabajo", "ORM: operaciones.ProgramacionOrden"),
        herramientas_escritura=(),
        salida="list[Senal] con tipo 'orden_sin_programar'.",
        evidencia=("observado: estado operativo de la orden",
                   "faltante: ausencia de programación vigente, declarada como ausencia"),
        incertidumbre=(
            "Una orden puede estar planificada fuera del sistema y no constar.",
            "La ausencia de ProgramacionOrden no distingue 'nadie la planificó' "
            "de 'se planificó y no se registró'.",
        ),
        escalamiento=(
            "Al Supervisor: siempre.",
            "A humano: si la orden ya está en campo sin ningún plan registrado.",
        ),
        nivel=1,
        metricas=("Falsos positivos sobre órdenes ya iniciadas. Medido en "
                  "M09-E: la condición corregida suprimió 3 de 3.",),
        detector="_ordenes_sin_programar",
        senal="orden_sin_programar",
        huella_condicion="estado:<estado_operativo>",
    ),

    Habilidad(
        id="H-04",
        nombre="Detectar plan semanal sin publicar con la semana en curso",
        tipo=DOMINIO, version=1, vigente_desde="2026-09-17", estado=VIGENTE,
        proposito=("Señalar que una semana ya empezó y su programación sigue en "
                   "borrador."),
        responsabilidad=(
            "Describir el estado del plan. No afirmar que alguien omitió publicarlo."),
        alcance="Programaciones semanales en borrador.",
        fuera_de_alcance=("No publica el plan.", "No nombra a quién debía publicarlo."),
        activacion=("La semana de inicio ya comenzó y el plan sigue en borrador.",),
        entradas=("org", "ahora"),
        datos=("ProgramacionSemanal.estado", "ProgramacionSemanal.semana_inicio",
               "ProgramacionSemanal.publicada_en"),
        reglas=(
            "Un plan de una semana futura en borrador NO es una señal: todavía "
            "hay tiempo.",
            "Huella 'semana:<semana_inicio>': una semana distinta es otra condición.",
        ),
        procedimiento=(
            "1. Tomar las programaciones en borrador.",
            "2. Descartar las de semanas que todavía no empezaron.",
            "3. Emitir señal citando el estado y el 'publicada_en' vacío.",
        ),
        conocimiento=(),          # criterio de publicación semanal: sin documentar
        herramientas_lectura=("ORM: operaciones.ProgramacionSemanal",),
        herramientas_escritura=(),
        salida="list[Senal] con tipo 'programacion_sin_publicar'.",
        evidencia=("observado: estado del plan",
                   "faltante: 'publicada_en' vacío, declarado como ausencia"),
        incertidumbre=(
            "Un plan puede estar acordado verbalmente y ejecutándose sin figurar "
            "publicado.",
        ),
        escalamiento=("Al Supervisor: siempre.",),
        nivel=1,
        metricas=("Falsos positivos sobre semanas futuras. Medido en M09-E: 0 "
                  "en 4 escenarios.",),
        detector="_programaciones_sin_publicar",
        senal="programacion_sin_publicar",
        huella_condicion="semana:<semana_inicio>",
    ),

    Habilidad(
        id="H-05",
        nombre="Estimar riesgo operacional de una orden por capacidad",
        tipo=DOMINIO, version=1, vigente_desde="2026-09-17", estado=BLOQUEADA,
        proposito=("Señalar órdenes comprometidas para un día en que la "
                   "capacidad disponible no alcanza."),
        responsabilidad=(
            "No emitir mientras no exista una definición medible de capacidad "
            "operativa. La ficha existe; la habilidad está BLOQUEADA."),
        alcance="Órdenes con fecha programada y ausencias registradas.",
        fuera_de_alcance=(
            "No reprograma.",
            "No decide a quién mover.",
            "No estima capacidad: la capacidad debe venir definida, no inferida.",
        ),
        activacion=("BLOQUEADA — ver reglas.",),
        entradas=("org", "ahora"),
        datos=("campo_orden_trabajo.programada_para",
               "operaciones_disponibilidad (DisponibilidadTecnico)"),
        reglas=(
            "BLOQUEADA POR D-4: no existe una definición medible de capacidad "
            "operativa, y M09-J decidió no inventarla.",
            "Medido en M09-E: 'operaciones_disponibilidad' tiene 0 filas, así "
            "que la habilidad se clasificó NO VALIDABLE POR FALTA DE DATOS.",
            "El detector '_ordenes_en_riesgo' EXISTE y corre; lo que falta es el "
            "conocimiento para confiar en su resultado.",
        ),
        procedimiento=("PENDIENTE — D-4. No se documenta un procedimiento que "
                       "dependería de una definición que no existe.",),
        conocimiento=("PENDIENTE — D-4: definición de capacidad operativa.",),
        herramientas_lectura=("ORM: campo.OrdenTrabajo",
                              "ORM: operaciones.DisponibilidadTecnico"),
        herramientas_escritura=(),
        salida="list[Senal] con tipo 'orden_con_riesgo_operacional'.",
        evidencia=("PENDIENTE — D-4",),
        incertidumbre=(
            "Sin definición de capacidad, cualquier umbral sería arbitrario y "
            "la señal no sería defendible ante quien la reciba.",
            "Con 0 filas de disponibilidad, la ausencia de señal no significa "
            "ausencia de riesgo.",
        ),
        escalamiento=("BLOQUEADA: no emite.",),
        nivel=1,
        metricas=("PENDIENTE — D-4",),
        detector="_ordenes_en_riesgo",
        senal="orden_con_riesgo_operacional",
        huella_condicion="prog:<fecha>|aus:<ausencia_id>",
    ),

    # ---------------------------------------------------------------- M02 ---
    Habilidad(
        id="H-06",
        nombre="Detectar actividad vencida sin cierre",
        tipo=DOMINIO, version=1, vigente_desde="2026-09-17", estado=VIGENTE,
        proposito="Señalar actividades cuyo vencimiento pasó y siguen sin cerrar.",
        responsabilidad=(
            "Decir que venció. NO decir que alguien incumplió: una demora puede "
            "ser un bloqueo, un material, una dependencia o un cambio de "
            "prioridad."),
        alcance="ActividadOperativa no finalizada con 'vence_en' pasado.",
        fuera_de_alcance=("No cierra la actividad.",
                          "No atribuye la demora a una persona."),
        activacion=("'vence_en' es anterior a ahora y el estado no es final.",),
        entradas=("org", "ahora"),
        datos=("ActividadOperativa.vence_en", "ActividadOperativa.estado_operativo"),
        reglas=("Huella 'vence:<fecha>': si la fecha comprometida cambia, es "
                "otra condición y vuelve a proponerse.",),
        procedimiento=(
            "1. Tomar actividades con vence_en anterior a ahora.",
            "2. Excluir las que están en un estado final.",
            "3. Emitir señal citando la fecha real de vencimiento.",
        ),
        conocimiento=(),
        herramientas_lectura=("ORM: operaciones.ActividadOperativa",),
        herramientas_escritura=(),
        salida="list[Senal] con tipo 'actividad_vencida'.",
        evidencia=("observado: fecha de vencimiento real",
                   "observado: estado operativo actual"),
        incertidumbre=(
            "La fecha de vencimiento pudo fijarse con información que ya cambió.",
            "Vencida no implica desatendida.",
        ),
        escalamiento=("Al Supervisor: siempre.",),
        nivel=1,
        metricas=("Ausencia de atribución de culpa: el texto no debe contener "
                  "ninguno de los 13 patrones verificados en M09-E.",),
        detector="_actividades_vencidas",
        senal="actividad_vencida",
        huella_condicion="vence:<fecha ISO>",
    ),

    Habilidad(
        id="H-07",
        nombre="Detectar actividad sin responsable asignado",
        tipo=DOMINIO, version=1, vigente_desde="2026-09-17", estado=VIGENTE,
        proposito="Señalar actividades que nadie tiene asignadas.",
        responsabilidad=(
            "Declarar una ausencia. NO proponer a quién asignarla: M09-C prohíbe "
            "que el Supervisor nombre personas, y por eso "
            "'responsable_sugerido' lo llena un humano al modificar (M09-F)."),
        alcance="ActividadOperativa sin responsable.",
        fuera_de_alcance=("No asigna.", "No sugiere responsable."),
        activacion=("La actividad no tiene responsable y no está en estado final.",),
        entradas=("org", "ahora"),
        datos=("ActividadOperativa.responsable", "ActividadOperativa.estado_operativo"),
        reglas=("Huella fija 'sin_responsable': la condición es binaria.",),
        procedimiento=(
            "1. Tomar actividades sin responsable.",
            "2. Excluir estados finales.",
            "3. Emitir señal declarando la ausencia como ausencia.",
        ),
        conocimiento=(),
        herramientas_lectura=("ORM: operaciones.ActividadOperativa",),
        herramientas_escritura=(),
        salida="list[Senal] con tipo 'actividad_sin_responsable'.",
        evidencia=("faltante: responsable ausente, declarado como ausencia",),
        incertidumbre=(
            "Puede haber un responsable acordado que no se cargó.",
            "La ausencia del campo no prueba que nadie se esté ocupando.",
        ),
        escalamiento=("Al Supervisor: siempre.",),
        nivel=1,
        metricas=("Ninguna propuesta debe nombrar a una persona como "
                  "responsable. Medido en M09-E.",),
        detector="_actividades_sin_responsable",
        senal="actividad_sin_responsable",
        huella_condicion="sin_responsable",
    ),

    Habilidad(
        id="H-08",
        nombre="Detectar actividad bloqueada y citar su causa registrada",
        tipo=DOMINIO, version=1, vigente_desde="2026-09-17", estado=VIGENTE,
        proposito="Señalar actividades detenidas, citando el motivo que alguien registró.",
        responsabilidad=(
            "Usar el motivo REGISTRADO, nunca uno deducido. La lista de causas "
            "es cerrada (NovedadOperativa.TIPOS) y no incluye "
            "'incumplimiento_de_persona'."),
        alcance="ActividadOperativa bloqueada.",
        fuera_de_alcance=("No desbloquea.", "No interpreta la causa.",
                          "No propone una causa distinta de la registrada."),
        activacion=("La actividad está bloqueada.",),
        entradas=("org", "ahora"),
        datos=("ActividadOperativa.estado_operativo",
               "ActividadOperativa.motivo_bloqueo", "NovedadOperativa.TIPOS"),
        reglas=("Huella 'bloqueo:<motivo[:48]>': si el motivo cambia, es otro "
                "bloqueo y vuelve a proponerse.",),
        procedimiento=(
            "1. Tomar actividades bloqueadas.",
            "2. Leer el motivo registrado.",
            "3. Emitir señal citando ese motivo textualmente.",
        ),
        conocimiento=("NovedadOperativa.TIPOS (catálogo cerrado de causas)",),
        herramientas_lectura=("ORM: operaciones.ActividadOperativa",
                              "ORM: operaciones.NovedadOperativa"),
        herramientas_escritura=(),
        salida="list[Senal] con tipo 'actividad_bloqueada'.",
        evidencia=("humana: el motivo de bloqueo tal como lo registró una persona",),
        incertidumbre=(
            "El motivo registrado puede estar desactualizado.",
            "Un bloqueo sin motivo cargado no permite afirmar la causa: se "
            "declara la ausencia, no se infiere.",
        ),
        escalamiento=(
            "Al Supervisor: siempre.",
            "A humano: si el bloqueo persiste más de un ciclo sin novedad.",
        ),
        nivel=1,
        metricas=("El motivo citado debe coincidir textualmente con el "
                  "registrado. Medido en M09-E.",),
        detector="_actividades_bloqueadas",
        senal="actividad_bloqueada",
        huella_condicion="bloqueo:<motivo[:48]>",
    ),

    Habilidad(
        id="H-09",
        nombre="Detectar compromiso próximo a vencer",
        tipo=DOMINIO, version=1, vigente_desde="2026-09-17", estado=VIGENTE,
        proposito="Avisar antes, no después: compromisos dentro de la ventana de aviso.",
        responsabilidad="Citar la fecha comprometida real, no una estimación.",
        alcance="ActividadOperativa con compromiso dentro de la ventana.",
        fuera_de_alcance=("No reprograma el compromiso.",
                          "No negocia con el cliente."),
        activacion=("El compromiso vence dentro de HORAS_COMPROMISO_POR_VENCER.",),
        entradas=("org", "ahora"),
        datos=("ActividadOperativa.vence_en", "ActividadOperativa.estado_operativo"),
        reglas=(
            "Ventana: HORAS_COMPROMISO_POR_VENCER = 24.",
            "Huella 'vence:<fecha>', igual que H-06: si la fecha cambia, es otro "
            "compromiso.",
        ),
        procedimiento=(
            "1. Tomar compromisos que vencen dentro de la ventana.",
            "2. Excluir estados finales.",
            "3. Emitir señal citando la fecha comprometida.",
        ),
        conocimiento=(),
        herramientas_lectura=("ORM: operaciones.ActividadOperativa",),
        herramientas_escritura=(),
        salida="list[Senal] con tipo 'compromiso_por_vencer'.",
        evidencia=("observado: fecha comprometida real",),
        incertidumbre=(
            "Un compromiso puede haberse cumplido y no estar registrado todavía.",
            "La ventana de 24 h es una convención, no una medición.",
        ),
        escalamiento=("Al Supervisor: siempre.",),
        nivel=1,
        metricas=("La fecha citada debe coincidir con la registrada. Medido en M09-E.",),
        detector="_compromisos_por_vencer",
        senal="compromiso_por_vencer",
        huella_condicion="vence:<fecha ISO>",
    ),

    Habilidad(
        id="H-10",
        nombre="Detectar dependencia pendiente que detiene una cadena",
        tipo=DOMINIO, version=1, vigente_desde="2026-09-17", estado=VIGENTE,
        proposito="Señalar actividades que esperan por otra que no avanzó.",
        responsabilidad="Nombrar la actividad previa concreta, no 'una dependencia'.",
        alcance="ActividadOperativa con dependencia no resuelta.",
        fuera_de_alcance=("No resuelve la dependencia.",
                          "No reordena la cadena."),
        activacion=("La actividad depende de otra que no está en estado final.",),
        entradas=("org", "ahora"),
        datos=("ActividadOperativa.depende_de", "ActividadOperativa.estado_operativo"),
        reglas=("Huella 'depende:<id de la previa>': si cambia la previa, es "
                "otra condición.",),
        procedimiento=(
            "1. Tomar actividades con dependencia declarada.",
            "2. Comprobar el estado de la actividad previa.",
            "3. Si la previa no terminó, emitir señal nombrándola.",
        ),
        conocimiento=(),
        herramientas_lectura=("ORM: operaciones.ActividadOperativa",),
        herramientas_escritura=(),
        salida="list[Senal] con tipo 'dependencia_pendiente'.",
        evidencia=("observado: identidad y estado de la actividad previa",),
        incertidumbre=(
            "La dependencia declarada puede haber dejado de ser real.",
            "Una cadena larga puede tener la causa varios pasos atrás: esta "
            "habilidad nombra la previa inmediata, no la causa raíz.",
        ),
        escalamiento=("Al Supervisor: siempre.",),
        nivel=1,
        metricas=("La actividad previa citada debe existir y estar sin "
                  "terminar. Medido en M09-E.",),
        detector="_dependencias_pendientes",
        senal="dependencia_pendiente",
        huella_condicion="depende:<id previa>",
    ),

    # -------------------------------------------------------- TRANSVERSALES ---
    #  No son detectores: son las cuatro funciones que TODAS las de dominio
    #  usan. Estan aca porque duplicarlas produciria dos verdades sobre el mismo
    #  hecho -- y eso ya paso en este proyecto con otras listas.

    Habilidad(
        id="H-C1",
        nombre="Calcular y explicar la prioridad",
        tipo=TRANSVERSAL, version=1, vigente_desde="2026-09-17", estado=VIGENTE,
        proposito="Ordenar la cola con un número que se pueda explicar.",
        responsabilidad=(
            "Que cada componente que suma o resta quede escrito en la "
            "evidencia. El modelo no calcula: el código calcula (PRD §12.5)."),
        alcance="Todas las señales.",
        fuera_de_alcance=("No pondera personas.", "No produce un ranking de nadie."),
        activacion=("Siempre que se registra una propuesta.",),
        entradas=("base: int", "componentes: dict[str, int]"),
        datos=(),
        reglas=(
            "Una sola fórmula para toda la cola: dos fórmulas serían dos colas.",
            "Los componentes viajan como evidencia, con fuente "
            "'calculo_prioridad'.",
        ),
        procedimiento=("1. Partir de la base de la señal.",
                       "2. Sumar cada componente con nombre.",
                       "3. Devolver el total y la lista de componentes."),
        conocimiento=(),
        herramientas_lectura=(),
        herramientas_escritura=(),
        salida="tuple[int, list[str]]",
        evidencia=("calculado: la lista de componentes, con su nombre y su aporte",),
        incertidumbre=("La prioridad ordena; no mide urgencia real para el cliente.",),
        escalamiento=("No aplica: no emite señales.",),
        nivel=0,
        metricas=("Toda propuesta debe traer el cálculo. Medido en M09-E: 52 de 52.",),
        detector="",
        senal="",
    ),

    Habilidad(
        id="H-C2",
        nombre="Construir evidencia trazable",
        tipo=TRANSVERSAL, version=1, vigente_desde="2026-09-17", estado=VIGENTE,
        proposito="Que toda afirmación pueda contrastarse contra la base.",
        responsabilidad=(
            "Cuatro claves siempre: fuente, id, dato y hora de LECTURA. "
            "'observado_en' es cuándo se leyó, no cuándo ocurrió el hecho."),
        alcance="Todas las señales.",
        fuera_de_alcance=("No interpreta el dato.", "No lo resume."),
        activacion=("Siempre que se construye una observación.",),
        entradas=("fuente: str", "identificador", "dato: str", "observado_en"),
        datos=(),
        reglas=(
            "Sin evidencia no hay propuesta: lo garantiza el CheckConstraint "
            "'propuesta_exige_evidencia', no la buena voluntad del llamador.",
            "Un formato único: dos formatos harían la auditoría ilegible.",
        ),
        procedimiento=("1. Nombrar la fuente.", "2. Citar el identificador.",
                       "3. Copiar el dato tal cual.", "4. Sellar la hora de lectura."),
        conocimiento=(),
        herramientas_lectura=(),
        herramientas_escritura=(),
        salida="dict con fuente, id, dato, observado_en",
        evidencia=("la evidencia misma",),
        incertidumbre=(
            "La hora de lectura permite saber si la propuesta se tomó con "
            "información fresca o vieja; no garantiza que siga siendo cierta.",
        ),
        escalamiento=("No aplica.",),
        nivel=0,
        metricas=("Ninguna observación sin las cuatro claves. Medido en M09-E: 0 fallos.",),
        detector="",
        senal="",
    ),

    Habilidad(
        id="H-C3",
        nombre="Calcular la huella de la condición",
        tipo=TRANSVERSAL, version=1, vigente_desde="2026-09-17", estado=VIGENTE,
        proposito="Distinguir 'el mismo hecho otra vez' de 'un hecho nuevo'.",
        responsabilidad=(
            "Llevar solo lo que, si cambia, convierte la situación en otra. "
            "NUNCA una magnitud que avanza sola."),
        alcance="Todas las señales.",
        fuera_de_alcance=("No decide si se propone: eso lo decide el estado.",),
        activacion=("Siempre que se construye una señal.",),
        entradas=("los datos que identifican la condición",),
        datos=(),
        reglas=(
            "Si la huella incluyera la magnitud (los días que lleva abierto un "
            "caso), una propuesta rechazada volvería mañana con otra huella. Es "
            "el defecto que M09-D cerró.",
            "Bloquean: propuesta, aceptada, modificada, rechazada. "
            "NO bloquean: expirada ni cancelada — nadie las miró, volver a "
            "preguntar es lo correcto.",
        ),
        procedimiento=("1. Tomar los rasgos estables de la condición.",
                       "2. Excluir toda magnitud que avance sola.",
                       "3. Componer una cadena estable."),
        conocimiento=(),
        herramientas_lectura=(),
        herramientas_escritura=(),
        salida="str",
        evidencia=("la huella, guardada en 'huella_condicion'",),
        incertidumbre=(
            "Una huella demasiado estable oculta un cambio real; una demasiado "
            "sensible repite la pregunta. El equilibrio es una decisión, no una "
            "medición.",
        ),
        escalamiento=("No aplica.",),
        nivel=0,
        metricas=("Rechazada + misma evidencia → 0 nuevas. Condición nueva → "
                  "exactamente 1. Medido en M09-E y M09-F.",),
        detector="",
        senal="",
    ),

    Habilidad(
        id="H-C4",
        nombre="Redactar sin atribuir culpa",
        tipo=TRANSVERSAL, version=1, vigente_desde="2026-09-17", estado=VIGENTE,
        proposito="Describir una condición sin convertir una ausencia en una acusación.",
        responsabilidad=(
            "Una demora puede ser un bloqueo, un material, una dependencia, una "
            "ausencia, un cambio de prioridad o un dato mal cargado. "
            "'incumplimiento_de_persona' no está en la lista de causas y no debe "
            "aparecer en ningún texto."),
        alcance="El texto de toda propuesta.",
        fuera_de_alcance=("No suaviza un hecho cierto.",
                          "No omite el problema para evitar incomodar."),
        activacion=("Siempre que se redacta un motivo o un impacto.",),
        entradas=("el hecho observado",),
        datos=(),
        reglas=(
            "Una ausencia de dato se declara como ausencia, nunca como causa: "
            "'no hay registro de cierre' no es 'nadie lo atendió'.",
            "Donde corresponde, el texto declara explícitamente lo que NO se "
            "afirma.",
        ),
        procedimiento=("1. Describir la condición observada.",
                       "2. Declarar qué NO se afirma.",
                       "3. Revisar que no aparezca ninguna atribución personal."),
        conocimiento=("PENDIENTE — D-3: guía de redacción sin atribución de culpa.",),
        herramientas_lectura=(),
        herramientas_escritura=(),
        salida="texto",
        evidencia=("el texto de la propuesta",),
        incertidumbre=(
            "La lista de 13 patrones prohibidos es una guarda, no una garantía: "
            "se puede atribuir culpa sin usar ninguna de esas palabras.",
        ),
        escalamiento=("No aplica.",),
        nivel=0,
        metricas=("0 propuestas con patrones de atribución. Medido en M09-E: "
                  "52 de 52 limpias.",),
        detector="",
        senal="",
    ),

    # -------------------------------------------------------------- M04-A ---
    #  Las dos hablan de TIEMPO OPERATIVO de una orden, no del SLA de un caso:
    #  'cases.Case' tiene su propio SLA, su pausa y su politica. Estas dos no
    #  lo tocan ni lo leen.
    Habilidad(
        id="H-11",
        nombre="Detectar orden con plazo operativo vencido",
        tipo=DOMINIO, version=1, vigente_desde="2026-09-20", estado=VIGENTE,
        proposito="Señalar órdenes cuyo plazo derivado del tipo de trabajo ya pasó.",
        responsabilidad=(
            "Decir que el plazo pasó. NO decir que alguien incumplió ni que la "
            "orden esté desatendida: el plazo mide tiempo, no conducta."),
        alcance="OrdenTrabajo no terminada, con duración declarada por su tipo.",
        fuera_de_alcance=(
            "No reprograma ni cierra la orden.",
            "No atribuye el atraso a una persona.",
            "No opina sobre el SLA de un caso: es otro sistema.",
        ),
        activacion=("operaciones.sla.plazo_de devuelve VENCIDA.",),
        entradas=("org", "ahora"),
        datos=("campo.OrdenTrabajo.created_at", "campo.OrdenTrabajo.estado_operativo",
               "WorkTypeVersion.esquema.duracion_estimada_minutos",
               "business_hours.BusinessCalendar"),
        reglas=(
            "El plazo se ancla en 'created_at': reprogramar NO lo extiende y "
            "cambiar el plan NO lo reinicia.",
            "Huella 'sla_vencido': los minutos de atraso crecen solos y no "
            "entran en la huella, o cada ciclo sería otra condición.",
            "Sin duración válida no hay señal: SIN_PLAZO no es cero.",
        ),
        procedimiento=(
            "1. Tomar órdenes no terminadas de la organización.",
            "2. Pedir el plazo a operaciones.sla (única fuente del cálculo).",
            "3. Emitir solo si el estado es VENCIDA.",
        ),
        conocimiento=(),
        herramientas_lectura=("ORM: campo.OrdenTrabajo", "operaciones.sla"),
        herramientas_escritura=(),
        salida="list[Senal] con tipo 'orden_sla_vencido'.",
        evidencia=("observado: número y estado de la orden",
                   "observado: plazo declarado por el tipo de trabajo",
                   "observado: ancla, límite y calendario usado",
                   "observado: minutos de atraso"),
        incertidumbre=(
            "El plazo se cuenta desde la creación, no desde el inicio real del "
            "trabajo: mide espera, no esfuerzo.",
            "Vencida no implica desatendida: la causa, si existe, está en las "
            "novedades de la orden.",
        ),
        escalamiento=("Al Supervisor: siempre.",),
        nivel=1,
        metricas=("Ausencia de atribución de culpa en el texto de la propuesta.",),
        detector="_ordenes_con_sla_vencido",
        senal="orden_sla_vencido",
        huella_condicion="sla_vencido",
    ),

    Habilidad(
        id="H-12",
        nombre="Detectar orden con plazo operativo por vencer",
        tipo=DOMINIO, version=1, vigente_desde="2026-09-20", estado=VIGENTE,
        proposito="Avisar antes del límite, con antelación proporcional al plazo.",
        responsabilidad=(
            "Decir cuánto falta y con qué ventana se avisó. NO afirmar que la "
            "orden vaya a incumplirse."),
        alcance="OrdenTrabajo no terminada, con duración declarada, dentro de la ventana.",
        fuera_de_alcance=("No reprograma.", "No predice el desenlace."),
        activacion=("operaciones.sla.plazo_de devuelve VENCE_PRONTO.",),
        entradas=("org", "ahora"),
        datos=("campo.OrdenTrabajo.created_at",
               "WorkTypeVersion.esquema.duracion_estimada_minutos",
               "business_hours.BusinessCalendar"),
        reglas=(
            "Ventana = min(24 h, 20% del plazo). Un umbral fijo no sirve: con "
            "24 h, un trabajo de 2 h nacería ya avisado.",
            "Huella 'sla_por_vencer': los minutos restantes bajan solos.",
        ),
        procedimiento=(
            "1. Tomar órdenes no terminadas de la organización.",
            "2. Pedir el plazo a operaciones.sla.",
            "3. Emitir solo si el estado es VENCE_PRONTO.",
        ),
        conocimiento=(),
        herramientas_lectura=("ORM: campo.OrdenTrabajo", "operaciones.sla"),
        herramientas_escritura=(),
        salida="list[Senal] con tipo 'orden_sla_por_vencer'.",
        evidencia=("observado: número y estado de la orden",
                   "observado: plazo, ancla, límite y calendario",
                   "observado: minutos restantes y ventana aplicada"),
        incertidumbre=(
            "Que falte poco no implica que vaya a vencerse.",
            "La ventana es de tiempo de reloj; el plazo respeta el calendario.",
        ),
        escalamiento=("Al Supervisor: siempre.",),
        nivel=1,
        metricas=("La ventana citada en la evidencia coincide con la calculada.",),
        detector="_ordenes_con_sla_por_vencer",
        senal="orden_sla_por_vencer",
        huella_condicion="sla_por_vencer",
    ),


    # -------------------------------------------------------------- M05-A ---
    Habilidad(
        id="H-13",
        nombre="Detectar incidencia operativa sin resolver",
        tipo=DOMINIO, version=1, vigente_desde="2026-09-20", estado=VIGENTE,
        proposito="Señalar causas operativas que siguen abiertas o en gestión.",
        responsabilidad=(
            "Decir que la incidencia sigue sin resolverse. NO decir que alguien "
            "la desatendió, ni deducir que se resolvió porque la actividad "
            "dejó de estar bloqueada."),
        alcance="NovedadOperativa con estado ABIERTA o EN_GESTION.",
        fuera_de_alcance=(
            "No resuelve la incidencia.",
            "No cambia su estado.",
            "No desbloquea, no reasigna, no escala.",
        ),
        activacion=("La columna 'estado' vale 'abierta' o 'en_gestion'.",),
        entradas=("org", "ahora"),
        datos=("operaciones.NovedadOperativa.estado",
               "operaciones.NovedadOperativa.impacto",
               "operaciones.NovedadOperativa.created_at"),
        reglas=(
            "El estado se LEE de la columna. Desbloquear una actividad no "
            "resuelve la incidencia: son dos hechos distintos.",
            "Huella 'estado:<estado>': la antigüedad crece sola y no entra, o "
            "cada ciclo sería otra condición. Pasar de abierta a en gestión sí "
            "es otra situación.",
            "Las RESUELTA se ignoran.",
        ),
        procedimiento=(
            "1. Tomar las novedades con estado abierta o en gestión.",
            "2. Armar su ficha con operaciones.incidencias.",
            "3. Emitir señal citando estado, impacto, antigüedad y vínculos.",
        ),
        conocimiento=(),
        herramientas_lectura=("ORM: operaciones.NovedadOperativa",
                              "operaciones.incidencias", "operaciones.novedades"),
        herramientas_escritura=(),
        salida="list[Senal] con tipo 'incidencia_sin_resolver'.",
        evidencia=("observado: tipo y estado de la incidencia",
                   "observado: fecha de registro y antigüedad",
                   "observado: impacto declarado, o su ausencia",
                   "observado: orden y actividad relacionadas",
                   "observado: quién la registró",
                   "observado: contexto observable alrededor",
                   "observado: qué datos no se declararon"),
        incertidumbre=(
            "El contexto observable no dice si la causa se atendió: solo la "
            "resolución explícita lo dice.",
            "Una incidencia sin impacto declarado no es una incidencia leve.",
        ),
        escalamiento=("Al Supervisor: siempre.",),
        nivel=1,
        metricas=("El texto no atribuye la demora a ninguna persona.",),
        detector="_incidencias_sin_resolver",
        senal="incidencia_sin_resolver",
        huella_condicion="estado:<estado>",
    ),


    # -------------------------------------------------------------- M05-B ---
    Habilidad(
        id="H-14",
        nombre="Detectar escalamiento sin destinatario registrado",
        tipo=DOMINIO, version=1, vigente_desde="2026-09-21", estado=VIGENTE,
        proposito="Señalar actividades escaladas a las que les falta destinatario o nivel.",
        responsabilidad=(
            "Decir que el dato falta. NO decir a quién escalarla: no existe una "
            "política operativa que lo determine, y elegir sin ella sería "
            "inventar la decisión."),
        alcance="ActividadOperativa en estado 'escalada' sin 'escalado_a' o sin nivel.",
        fuera_de_alcance=(
            "No escala.",
            "No elige destinatario.",
            "No decide que una actividad 'necesita escalamiento': eso no es "
            "observable con los datos de hoy.",
        ),
        activacion=("estado_operativo='escalada' y falta escalado_a o nivel.",),
        entradas=("org", "ahora"),
        datos=("operaciones.ActividadOperativa.estado_operativo",
               "operaciones.ActividadOperativa.escalado_a",
               "operaciones.ActividadOperativa.nivel_escalamiento"),
        reglas=(
            "Antigüedad, atraso e impacto NO son criterio de escalamiento: un "
            "compromiso viejo puede estar atendido y uno crítico puede no "
            "necesitar a nadie más.",
            "Huella 'faltan:<campos>': lo que identifica la situación es QUÉ "
            "falta, no cuánto lleva así.",
            "El nivel describe ruta de gestión; el impacto de la incidencia es "
            "otro eje y vive en NovedadOperativa.",
        ),
        procedimiento=(
            "1. Tomar actividades en estado escalada.",
            "2. Filtrar las que no tienen destinatario o no tienen nivel.",
            "3. Emitir señal nombrando exactamente qué campo falta.",
        ),
        conocimiento=(),
        herramientas_lectura=("ORM: operaciones.ActividadOperativa",),
        herramientas_escritura=(),
        salida="list[Senal] con tipo 'escalamiento_sin_destinatario'.",
        evidencia=("observado: título y estado de la actividad",
                   "observado: destinatario, o su ausencia",
                   "observado: nivel, o su ausencia",
                   "observado: fecha de escalamiento, o su ausencia"),
        incertidumbre=(
            "Puede tratarse de una actividad escalada antes de que el sistema "
            "registrara destinatario, no de un descuido de nadie.",
        ),
        escalamiento=("Al Supervisor: siempre.",),
        nivel=1,
        metricas=("La propuesta NO nombra a ninguna persona como destinatario.",),
        detector="_escalamientos_sin_destinatario",
        senal="escalamiento_sin_destinatario",
        huella_condicion="faltan:<campos>",
    ),

)


# =============================================================================
#  EL REGISTRO  --  congelado al importar
# =============================================================================
#  MappingProxyType y no un dict: un dict se puede modificar en caliente desde
#  cualquier modulo que lo importe, y entonces "la definicion de la habilidad"
#  dejaria de ser una sola cosa. Con esto, intentar agregar o quitar una entrada
#  levanta TypeError.

HABILIDADES = MappingProxyType({h.id: h for h in _FICHAS})

#  Los IDs, en el orden declarado. Util para recorrer sin depender del orden de
#  un diccionario.
IDS = tuple(h.id for h in _FICHAS)

#  El indice inverso: de que detector de supervisor.py sale cada habilidad.
#  Solo las de dominio: las transversales no son detectores.
POR_DETECTOR = MappingProxyType(
    {h.detector: h.id for h in _FICHAS if h.detector})

#  De que tipo de señal sale cada habilidad. Es el enganche que usa
#  'referencia_de' para poder estampar la version en la propuesta.
POR_SENAL = MappingProxyType({h.senal: h.id for h in _FICHAS if h.senal})


# =============================================================================
#  CONOCIMIENTO  --  paso D-3
# =============================================================================
#  Los documentos de conocimiento que gobiernan la DETECCION de cada habilidad.
#  Viven en 'directivas/' y su fuente es documental, no ejecutable: explican
#  como interpretar una habilidad, nunca la modifican.
#
#  POR QUE UN MAPA APARTE Y NO UN CAMPO DE LA FICHA
#  ------------------------------------------------
#  Agregar la referencia dentro de 'Habilidad' cambiaria el contenido literal de
#  las 14 fichas y por lo tanto sus huellas, que M09-K ya dejo registradas. El
#  §17 de D-3 es explicito: si el conocimiento obliga a tocar una habilidad, se
#  registra el gap y NO se toca. Este mapa es aditivo: ninguna ficha cambia, y
#  las 14 huellas de M09-K siguen siendo validas.
#
#  SOLO LO QUE EXISTE
#  ------------------
#  Una habilidad sin documento NO aparece aca. No hay entrada vacia ni
#  marcador: la ausencia es el dato. Nueve de las catorce no tienen documento
#  porque esos documentos todavia no se escribieron.
#
#  K-04 (redaccion sin atribucion de culpa) gobierna el TEXTO de todas las
#  propuestas, pero se referencia desde H-C4 -- que no emite señales, asi que no
#  aparece en ninguna propuesta. Es deliberado: repetirlo en las diez señales
#  seria relleno, y la referencia sirve para decir que conocimiento gobierno LA
#  DETECCION, no la redaccion. Ver D-3_CONOCIMIENTO_OPERATIVO.md.
CONOCIMIENTO = MappingProxyType({
    "H-01": (("K-01", 1), ("K-05", 1)),
    "H-02": (("K-03", 1),),
    "H-03": (("K-03", 1),),
    "H-C4": (("K-04", 1),),
})


def conocimiento_de(id_habilidad: str) -> str:
    """
    'K-01@1,K-05@1' -- o "" si esa habilidad no tiene documento.

    Vacio NO es un error: significa que el conocimiento de esa habilidad
    todavia no se escribio. Decirlo con una cadena vacia es mas honesto que
    inventar un identificador.
    """
    docs = CONOCIMIENTO.get(id_habilidad, ())
    return ",".join(f"{doc}@{ver}" for doc, ver in docs)


def referencia_de(tipo_senal: str) -> str:
    """
    La referencia que se guarda en 'PropuestaSupervisor.conocimiento_version'.

    QUE REPRESENTA, EXACTAMENTE
    ---------------------------
        "habilidad:H-01@1 conocimiento:K-01@1,K-05@1"
         └ version de la habilidad    └ documentos que gobiernan su deteccion

    Los dos prefijos estan a proposito. El campo se llama
    'conocimiento_version', y hasta D-3 no habia ningun documento versionado: el
    prefijo 'habilidad:' existia para que nadie leyera la version de la
    habilidad como si fuera una version de conocimiento.

    Ahora que D-3 escribio documentos reales, se agrega la segunda mitad -- pero
    SOLO donde el documento existe. Una habilidad sin documento sigue
    devolviendo unicamente 'habilidad:H-XX@N', sin la palabra 'conocimiento'.
    Nueve de las catorce estan en ese caso, y el silencio es el dato.

    ESTABILIDAD HACIA ATRAS
    -----------------------
    Una propuesta emitida antes de D-3 guarda 'habilidad:H-01@1'. Una emitida
    despues guarda 'habilidad:H-01@1 conocimiento:K-01@1,K-05@1'. Las dos siguen
    significando exactamente lo que decian el dia que se escribieron: la
    primera mitad no cambio, y la segunda se agrego sin reescribir ninguna fila.

    Devuelve "" si la señal no tiene ficha: preferible un campo vacio a una
    referencia inventada.
    """
    id_habilidad = POR_SENAL.get(tipo_senal)
    if not id_habilidad:
        return ""
    referencia = HABILIDADES[id_habilidad].referencia()
    docs = conocimiento_de(id_habilidad)
    return f"{referencia} conocimiento:{docs}" if docs else referencia
