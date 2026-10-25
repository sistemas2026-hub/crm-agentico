# -*- coding: utf-8 -*-
"""
================================================================================
 LOS NIVELES DE RESPUESTA  --  plazo y prioridad por ASUNTO  (24/10/2026)
================================================================================

Propuesta del usuario del 24/10/2026, con la habilidad H-21 autorizada ese dia
(«autorizo la h-21»). Ficha y decisiones: SPEC/objetivos/
supervisor-arma-la-jornada.md, seccion «Niveles de respuesta y H-21».

EL PROBLEMA
-----------
El plazo era de la PLANTILLA entera (`WorkType.plazo_dias`), y en una plantilla
hay asuntos muy distintos: «No Tiene Internet» y «Cambio De Domicilio»
compartian tiempo. Ponerle plazo y prioridad a cada uno de los ~50 asuntos es
trabajo que nadie iba a mantener.

LO QUE HAY DESDE HOY
--------------------
    NIVELES       tres por empresa (Urgente, Normal, Programable), cada uno
                  con su plazo en dias y su prioridad inicial. Se definen una
                  vez; cambiar un numero cambia todos los asuntos de ese nivel.
    EL ASUNTO     queda en UN nivel, con QUIEN lo decidio (el Supervisor o una
                  persona) y POR QUE. Lo que decide una persona, el Supervisor
                  no lo vuelve a tocar: lo garantiza el `UPDATE` de abajo, no
                  una costumbre.
    LA LECTURA    `nivel_del_asunto(org, asunto)`: lo que necesita quien crea
                  una orden.

LO QUE NO CAMBIA
----------------
La plantilla sigue decidiendo la labor y el formulario del tecnico; un asunto
sigue en una sola plantilla; las ordenes ya creadas no cambian. Y nadie lee
esto todavia para crear una orden: la fase 2.3 (el Supervisor crea las ordenes)
es la que lo va a usar.

SON TRES, Y SON ESTOS TRES (decision N1)
----------------------------------------
Se editan nombre, plazo y prioridad; no se agregan ni se quitan. La habilidad
H-21 ubica cada asunto en uno de los tres por el grupo de sus tickets, y un
cuarto nivel no tendria grupo que lo llene. El CODIGO no cambia nunca: es lo
que queda guardado en cada asunto; el NOMBRE si, que es lo que se ve.

SIN FILAS, LOS DE FABRICA, SIN ESCRIBIR (como `campo.labores`)
--------------------------------------------------------------
Leer no tiene por que crear nada. Una empresa sin filas lee los de fabrica, y
recien cuando alguien guarda los niveles se escriben los tres.

POR EMPRESA EN EL CODIGO, NO EN RLS
-----------------------------------
Como el resto de `campo` (`campo_labor` incluida): toda consulta filtra por
`org`. Las tablas no estan en `common.rls.ORG_SCOPED_TABLES`.
================================================================================
"""

from __future__ import annotations

from django.db import DatabaseError, IntegrityError, models, transaction
from django.utils import timezone

from common.base import BaseModel
from common.models import Org, Profile

URGENTE = "urgente"
NORMAL = "normal"
PROGRAMABLE = "programable"

#: (codigo, nombre, plazo en dias, prioridad inicial). Los numeros son los de
#: la propuesta del 24/10/2026; cada empresa los cambia una vez.
NIVELES_DE_FABRICA = (
    (URGENTE, "Urgente", 0, "alta"),
    (NORMAL, "Normal", 2, "media"),
    (PROGRAMABLE, "Programable", 5, "baja"),
)
CODIGOS = tuple(c for c, *_ in NIVELES_DE_FABRICA)

#: El mismo tope que el plazo de una plantilla (`plantillas.MAX_PLAZO_DIAS`):
#: un trabajo a mas de dos meses no se despacha, se agenda aparte.
MAX_PLAZO_DIAS = 60
MAX_NOMBRE = 40

#: Quien decidio el nivel de un asunto.
POR_SUPERVISOR = "supervisor"
POR_PERSONA = "persona"


class ErrorNivel(ValueError):
    """Lo que se quiso guardar no se puede. El mensaje es para quien edita."""

    def __init__(self, codigo: str, mensaje: str):
        super().__init__(mensaje)
        self.codigo = codigo
        self.mensaje = mensaje


class NivelDeRespuesta(BaseModel):
    """Un nivel de respuesta de la empresa: cuanto se tarda y con que
    prioridad arranca una orden de un asunto de este nivel."""

    org = models.ForeignKey(Org, on_delete=models.CASCADE,
                            related_name="niveles_de_respuesta")
    codigo = models.CharField(max_length=20)
    nombre = models.CharField(max_length=MAX_NOMBRE)
    plazo_dias = models.PositiveSmallIntegerField()
    prioridad = models.CharField(max_length=10)

    class Meta:
        db_table = "campo_nivel_de_respuesta"
        constraints = [
            models.UniqueConstraint(fields=["org", "codigo"],
                                    name="unique_nivel_codigo_por_org"),
        ]

    def __str__(self) -> str:
        return f"{self.nombre} ({self.codigo})"


class NivelDeAsunto(BaseModel):
    """En que nivel esta un asunto de la empresa, quien lo decidio y por que.

    UNA fila por asunto (`unique(org, normalizado)`): si hubiera dos, el mismo
    ticket podria nacer con dos plazos.
    """

    org = models.ForeignKey(Org, on_delete=models.CASCADE,
                            related_name="niveles_de_asunto")
    #: Como se ve: el primero que se vio, tal como venia.
    asunto = models.CharField(max_length=255)
    #: Como se compara: `campo.plantillas.normalizar_asunto`, el mismo de las
    #: plantillas y de las labores. Lo calcula `save()`.
    normalizado = models.CharField(max_length=255, db_index=True)
    nivel = models.CharField(max_length=20)
    por = models.CharField(max_length=12)
    #: Por que, en palabras: «4 de 5 tickets fueron falla de servicio».
    motivo = models.CharField(max_length=255, blank=True, default="")
    #: El Supervisor lo puso en Normal porque todavia no tiene datos.
    provisional = models.BooleanField(default=False)
    #: Con cuantos tickets leidos decidio el Supervisor. 0 si fue una persona.
    tickets = models.PositiveIntegerField(default=0)
    decidido_por = models.ForeignKey(Profile, on_delete=models.SET_NULL,
                                     null=True, blank=True,
                                     related_name="niveles_de_asunto_decididos")
    decidido_por_nombre = models.CharField(max_length=120, blank=True, default="")
    decidido_en = models.DateTimeField()

    class Meta:
        db_table = "campo_nivel_de_asunto"
        ordering = ["asunto"]
        constraints = [
            models.UniqueConstraint(fields=["org", "normalizado"],
                                    name="unique_nivel_por_asunto"),
        ]

    def save(self, *args, **kwargs):
        from campo.plantillas import normalizar_asunto
        self.normalizado = normalizar_asunto(self.asunto)
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.asunto} → {self.nivel} ({self.por})"


# =============================================================================
#  LOS NIVELES
# =============================================================================

def _de_fabrica() -> list[dict]:
    return [{"codigo": c, "nombre": n, "plazo_dias": d, "prioridad": p}
            for c, n, d, p in NIVELES_DE_FABRICA]


def niveles_de(org) -> list[dict]:
    """Los tres niveles de la empresa, en el orden de fabrica:
    [{codigo, nombre, plazo_dias, prioridad}].

    SIN FILAS devuelve los de fabrica, sin escribir. LA TABLA PUEDE NO EXISTIR
    TODAVIA (el mismo motivo que `campo.labores._filas`: el worker puede correr
    antes que `migrate`): se trata igual que «sin filas», con un savepoint que
    deja usable la transaccion de quien llama.
    """
    try:
        with transaction.atomic():
            filas = {f.codigo: f for f in NivelDeRespuesta.objects.filter(org=org)}
    except DatabaseError:
        filas = {}
    salida = []
    for base in _de_fabrica():
        f = filas.get(base["codigo"])
        salida.append(base if f is None else {
            "codigo": f.codigo, "nombre": f.nombre,
            "plazo_dias": f.plazo_dias, "prioridad": f.prioridad})
    return salida


def _validar(cambio: dict) -> dict:
    codigo = str((cambio or {}).get("codigo") or "")
    if codigo not in CODIGOS:
        raise ErrorNivel("NIVEL_INVALIDO", f"«{codigo}» no es un nivel.")
    limpio = {}
    if "nombre" in cambio:
        nombre = " ".join(str(cambio.get("nombre") or "").split())
        if not nombre:
            raise ErrorNivel("NOMBRE_VACIO", "Cada nivel necesita un nombre.")
        if len(nombre) > MAX_NOMBRE:
            raise ErrorNivel("NOMBRE_LARGO",
                             f"El nombre va hasta {MAX_NOMBRE} letras.")
        limpio["nombre"] = nombre
    if "plazo_dias" in cambio:
        try:
            dias = int(cambio.get("plazo_dias"))
        except (TypeError, ValueError):
            raise ErrorNivel("PLAZO_INVALIDO", "El plazo va en días, un número.")
        if isinstance(cambio.get("plazo_dias"), bool) or dias < 0 or dias > MAX_PLAZO_DIAS:
            raise ErrorNivel("PLAZO_INVALIDO",
                             f"El plazo va de 0 a {MAX_PLAZO_DIAS} días.")
        limpio["plazo_dias"] = dias
    if "prioridad" in cambio:
        #  Las de la orden, no una copia: si la orden ganara una prioridad,
        #  un nivel podria usarla sin tocar esto.
        from campo.models import OrdenTrabajo
        prioridad = str(cambio.get("prioridad") or "")
        if prioridad not in {p for p, _ in OrdenTrabajo.PRIORIDADES}:
            raise ErrorNivel("PRIORIDAD_INVALIDA",
                             "La prioridad es alta, media o baja.")
        limpio["prioridad"] = prioridad
    return {"codigo": codigo, **limpio}


def guardar_niveles(org, cambios) -> list[dict]:
    """Guarda lo que cambio de los niveles y devuelve los tres como quedaron.

    `cambios` = [{codigo, nombre?, plazo_dias?, prioridad?}]. TODO o NADA: si
    uno no es valido no se guarda ninguno, para que la pantalla no quede
    mostrando una mitad. La primera vez escribe los tres (con los de fabrica
    en lo que no vino), asi la empresa deja de depender del codigo.
    """
    if not isinstance(cambios, (list, tuple)):
        raise ErrorNivel("NIVELES_INVALIDOS", "Los niveles van en una lista.")
    validos = [_validar(c) for c in cambios]
    if len({v["codigo"] for v in validos}) != len(validos):
        raise ErrorNivel("NIVEL_REPETIDO", "Un nivel vino dos veces.")
    por_codigo = {v["codigo"]: v for v in validos}
    with transaction.atomic():
        actuales = {f.codigo: f for f in
                    NivelDeRespuesta.objects.select_for_update().filter(org=org)}
        for base in _de_fabrica():
            nuevo = {**base, **{k: v for k, v in
                                por_codigo.get(base["codigo"], {}).items()
                                if k != "codigo"}}
            fila = actuales.get(base["codigo"])
            if fila is None:
                NivelDeRespuesta.objects.create(org=org, **nuevo)
                continue
            campos = [k for k in ("nombre", "plazo_dias", "prioridad")
                      if k in por_codigo.get(base["codigo"], {})
                      and getattr(fila, k) != nuevo[k]]
            for k in campos:
                setattr(fila, k, nuevo[k])
            if campos:
                fila.save(update_fields=[*campos, "updated_at"])
    return niveles_de(org)


# =============================================================================
#  EL ASUNTO DE UN TICKET
# =============================================================================
#  WispHub guarda el asunto como «Asunto - Cliente» (VERIFICADO, skill
#  wisphub-api: «al categorizar hay que cortar en ' - '»), el escalamiento arma
#  el caso como «Asunto · Cliente · #id», y `Case.name` corta en 64. Tal cual,
#  cada cliente seria un asunto distinto con un ticket -- la regla de H-21 no
#  decidiria nunca -- y el nombre del cliente llegaria al chat que lee el
#  modelo (auditor independiente, 25/10/2026, con sonda).

#: Lo que separa el asunto de lo que se le pego detras.
SEPARADORES = (" - ", " · ")
#: El largo de `Case.name`: un nombre de este largo puede venir cortado.
LARGO_DEL_CASO = 64


def asuntos_de_las_plantillas(org) -> dict:
    """{normalizado: como lo escribio quien armo la plantilla}, de las
    plantillas ACTIVAS de la empresa: las que Despacho puede elegir."""
    from campo.models import WorkType
    from campo.plantillas import normalizar_asunto

    salida = {}
    for lista in (WorkType.objects.filter(org=org, activo=True)
                  .values_list("asuntos", flat=True)):
        for a in (lista or []):
            clave = normalizar_asunto(a)
            if clave:
                salida.setdefault(clave, " ".join(str(a).split()))
    return salida


def asunto_del_ticket(texto, plantillas: dict) -> tuple[str, str]:
    """(clave normalizada, como se ve) del asunto de un ticket o de un caso.

    En este orden: el asunto de una plantilla que coincide entero; el de una
    plantilla seguido de un separador (el mas largo, para que «Cambio De Plan»
    no se coma a «Cambio De Plan - Upgrade» si la plantilla dice el segundo);
    lo que hay antes del primer separador; y, si el texto tiene el largo de
    `Case.name`, el UNICO asunto de plantilla que empieza con el. Si nada de
    eso aplica, el texto entero.
    """
    from campo.plantillas import normalizar_asunto

    visto = " ".join(str(texto or "").split())
    clave = normalizar_asunto(visto)
    if not clave:
        return "", ""
    if clave in plantillas:
        return clave, plantillas[clave]
    #  Los separadores ya estan en minusculas y sin tildes: se comparan contra
    #  la clave normalizada tal cual.
    con_cola = [p for p in plantillas
                if any(clave.startswith(p + s) for s in SEPARADORES)]
    if con_cola:
        p = max(con_cola, key=len)
        return p, plantillas[p]
    for s in SEPARADORES:
        if s in visto:
            cabeza = visto.split(s, 1)[0].strip()
            c = normalizar_asunto(cabeza)
            if c:
                return (c, plantillas[c]) if c in plantillas else (c, cabeza)
    if len(visto) >= LARGO_DEL_CASO:
        cortadas = [p for p in plantillas if p.startswith(clave)]
        if len(cortadas) == 1:
            return cortadas[0], plantillas[cortadas[0]]
    return clave, visto


# =============================================================================
#  EL NIVEL DE CADA ASUNTO
# =============================================================================

def nivel_del_asunto(org, asunto) -> dict | None:
    """El nivel de este asunto, listo para crear una orden:

        {"nivel": codigo, "plazo_dias": int, "prioridad": "alta|media|baja",
         "por": "supervisor" | "persona"}

    `asunto` puede ser el nombre del caso tal como viene («Asunto - Cliente»):
    se corta igual que lo cuenta H-21 (`asunto_del_ticket`).

    None si el asunto viene vacio, si la empresa todavia no lo ubico, o si lo
    que hay es un Normal PROVISIONAL del Supervisor (menos de 3 tickets
    leidos): eso no es una decision medida, y quien llama sigue con lo que ya
    tenia -- el plazo de la plantilla --. Aca no se inventa (auditor
    independiente, 25/10/2026: un plazo de 7 dias que puso la empresa quedaba
    tapado por 2 dias decididos con 0 tickets).
    `nivel` es el CODIGO (urgente, normal, programable): no cambia nunca. El
    nombre que se muestra sale de `niveles_de`.
    """
    try:
        with transaction.atomic():
            clave, _ = asunto_del_ticket(asunto, asuntos_de_las_plantillas(org))
            if not clave:
                return None
            fila = (NivelDeAsunto.objects.filter(org=org, normalizado=clave)
                    .values("nivel", "por", "provisional").first())
    except DatabaseError:
        return None
    if fila is None or (fila["por"] == POR_SUPERVISOR and fila["provisional"]):
        return None
    nivel = next((n for n in niveles_de(org) if n["codigo"] == fila["nivel"]), None)
    if nivel is None:
        return None
    return {"nivel": nivel["codigo"], "plazo_dias": nivel["plazo_dias"],
            "prioridad": nivel["prioridad"], "por": fila["por"]}


def asuntos_con_nivel(org) -> list[dict]:
    """Los asuntos de la empresa con su nivel, para la pantalla.

    Tambien los de las plantillas activas que todavia NO tienen nivel (con
    `nivel` None): sin el Supervisor ubicandolos, una persona tiene que poder
    ponerlos ella, y no se puede elegir lo que no aparece.
    """
    filas = [{
        "asunto": f.asunto,
        "nivel": f.nivel,
        "por": f.por,
        "motivo": f.motivo,
        "provisional": f.provisional,
        "tickets": f.tickets,
        "decidido_por": f.decidido_por_nombre,
        "decidido_en": f.decidido_en.isoformat() if f.decidido_en else None,
    } for f in NivelDeAsunto.objects.filter(org=org).order_by("asunto")]
    con_nivel = set(NivelDeAsunto.objects.filter(org=org)
                    .values_list("normalizado", flat=True))
    sin_nivel = [{"asunto": visto, "nivel": None, "por": None, "motivo": "",
                  "provisional": False, "tickets": 0, "decidido_por": "",
                  "decidido_en": None}
                 for clave, visto in asuntos_de_las_plantillas(org).items()
                 if clave not in con_nivel]
    return sorted(filas + sin_nivel, key=lambda a: a["asunto"].lower())


def decidir_por_persona(org, asunto, nivel, *, profile=None, nombre="") -> dict:
    """Una persona pone este asunto en este nivel. Desde aca, el Supervisor
    ya no lo toca (`ubicar_por_el_supervisor` no escribe filas de persona)."""
    from campo.plantillas import normalizar_asunto

    asunto = " ".join(str(asunto or "").split())
    if not normalizar_asunto(asunto):
        raise ErrorNivel("ASUNTO_VACIO", "Falta el asunto.")
    if len(asunto) > 255:
        raise ErrorNivel("ASUNTO_LARGO", "El asunto es demasiado largo.")
    if nivel not in CODIGOS:
        raise ErrorNivel("NIVEL_INVALIDO", f"«{nivel}» no es un nivel.")
    nombre = (nombre or "").strip()[:120]
    ahora = timezone.now()
    valores = {"nivel": nivel, "por": POR_PERSONA,
               "motivo": f"Lo eligió {nombre}" if nombre else "Lo eligió una persona",
               "provisional": False, "tickets": 0, "decidido_por": profile,
               "decidido_por_nombre": nombre, "decidido_en": ahora}
    with transaction.atomic():
        fila = (NivelDeAsunto.objects.select_for_update()
                .filter(org=org, normalizado=normalizar_asunto(asunto)).first())
        creada = False
        if fila is None:
            try:
                with transaction.atomic():
                    fila = NivelDeAsunto(org=org, asunto=asunto, **valores)
                    fila.save()
                creada = True
            except IntegrityError:
                #  EL SUPERVISOR LA CREO EN EL MEDIO (auditor independiente,
                #  25/10/2026, con sonda: daba un 500). La persona gana igual:
                #  se bloquea la fila que ahora existe y se escribe encima.
                fila = (NivelDeAsunto.objects.select_for_update()
                        .get(org=org, normalizado=normalizar_asunto(asunto)))
        if not creada:
            for k, v in valores.items():
                setattr(fila, k, v)
            fila.save(update_fields=[*valores, "updated_at"])
    return {"asunto": fila.asunto, "nivel": fila.nivel, "por": fila.por,
            "motivo": fila.motivo}


#: Lo que devuelve `ubicar_por_el_supervisor`.
NUEVO = "nuevo"
CAMBIO = "cambio"
IGUAL = "igual"
DE_UNA_PERSONA = "de_una_persona"


def ubicar_por_el_supervisor(org, asunto, nivel, *, motivo, tickets: int,
                             provisional: bool) -> str:
    """El Supervisor (H-21) pone este asunto en este nivel, SALVO que ya lo
    haya decidido una persona.

    LA PERSONA GANA EN LA BASE, NO EN UN `if`. La fila de una persona no se
    lee y despues se decide: el `UPDATE` lleva `por='supervisor'` en el filtro,
    asi que una persona que guarda entre la lectura del Supervisor y su
    escritura no pierde lo que eligio -- el `UPDATE` no encuentra fila. Y si la
    fila no existia y la crean los dos a la vez, el indice unico deja una sola.

    Devuelve NUEVO, CAMBIO (cambio de nivel), IGUAL (mismo nivel; el motivo y
    el conteo se actualizan en silencio) o DE_UNA_PERSONA.
    """
    from campo.plantillas import normalizar_asunto

    if nivel not in CODIGOS:
        raise ErrorNivel("NIVEL_INVALIDO", f"«{nivel}» no es un nivel.")
    clave = normalizar_asunto(asunto)
    if not clave:
        raise ErrorNivel("ASUNTO_VACIO", "Falta el asunto.")
    ahora = timezone.now()
    with transaction.atomic():
        actual = (NivelDeAsunto.objects.filter(org=org, normalizado=clave)
                  .values("nivel", "por").first())
        if actual is None:
            try:
                with transaction.atomic():
                    NivelDeAsunto(org=org, asunto=" ".join(str(asunto).split())[:255],
                                  nivel=nivel, por=POR_SUPERVISOR,
                                  motivo=motivo[:255], provisional=provisional,
                                  tickets=tickets, decidido_en=ahora).save()
                return NUEVO
            except IntegrityError:
                #  Alguien la creo entre la lectura y el insert: se relee.
                actual = (NivelDeAsunto.objects.filter(org=org, normalizado=clave)
                          .values("nivel", "por").first())
        if actual is None or actual["por"] != POR_SUPERVISOR:
            return DE_UNA_PERSONA
        tocadas = (NivelDeAsunto.objects
                   .filter(org=org, normalizado=clave, por=POR_SUPERVISOR)
                   .update(nivel=nivel, motivo=motivo[:255],
                           provisional=provisional, tickets=tickets,
                           decidido_en=ahora if actual["nivel"] != nivel
                           else models.F("decidido_en"),
                           updated_at=ahora))
    if not tocadas:
        return DE_UNA_PERSONA
    return CAMBIO if actual["nivel"] != nivel else IGUAL
