# -*- coding: utf-8 -*-
"""
================================================================================
 CONSTANCIA DEL RAZONAMIENTO  --  lo que el cerebro concluyo, y contra que
================================================================================

QUE HUECO CIERRA
----------------
'cerebro.concluir()' produce un Veredicto completo -- hechos con su fuente,
inferencias, riesgos, hipotesis con su confianza, recomendacion, que le falta,
y los DESCARTES que 'validar()' le quito por no tener respaldo. De todo eso,
hasta ahora, sobrevivia unicamente el texto aplanado que 'analisis_de_veredicto'
dejaba en 'motivo' e 'impacto'.

Consecuencia medida: con el cerebro encendido NO se podia responder "¿que
concluyo el cerebro, que concluyo el analisis deterministico, y cual acerto?".
La conclusion original se perdia en el momento de escribirla, y esa comparacion
ES la etapa de observacion del plan.

POR QUE UNA TABLA NUEVA Y NO UN CAMPO EN LA PROPUESTA
-----------------------------------------------------
Porque un campo nuevo en 'PropuestaSupervisor' obligaria a agregarlo a
'supervisor.CAMPOS_QUE_ESCRIBE_EL_SUPERVISOR', que NO es una comodidad: es la
garantia de gobernanza que 'test_m09f' vigila, y la que mantiene fuera a
'observaciones' y 'responsable_sugerido' desde M09-C. Ampliar esa lista para
guardar un registro seria pagar con gobernanza algo que una tabla aparte da
gratis.

Efecto lateral buscado: la reversa es trivial. Esta tabla no la lee ninguna
otra parte del sistema, asi que apagar el registro la deja inerte, y borrarla
solo pierde datos nuevos. Con un campo en la propuesta, revertir habria
significado tocar una tabla que esta en produccion con datos reales.

LOS DOS CAMPOS QUE SON EL DISENO, Y NO UN EXTRA
-----------------------------------------------
    analisis_deterministico   lo que la regla concluyo ANTES de que el cerebro
                              opinara. Sin el estado previo no hay comparacion
                              posible: se estaria comparando el resultado
                              contra si mismo, que da coincidencia siempre.
    descartes                 lo que 'validar()' elimino por no tener fuente.
                              Convierte en NUMERO algo que hoy no se mide:
                              cuantas veces el modelo afirmo sin respaldo.

APPEND-ONLY, Y COMO SE SOSTIENE
-------------------------------
Una fila se escribe una vez y no se vuelve a tocar. No hay ruta de
actualizacion: 'razonamiento.registrar()' es el unico escritor y solo hace
'create'. No hay serializer, no hay vista, no hay endpoint de edicion. La
garantia es que nada mas la escribe, no un trigger -- igual que
'DecisionSupervisor', que ya funciona asi.

EL INDICE POR ORG SE DECLARA A MANO, Y ESO TIENE MOTIVO
-------------------------------------------------------
'BaseModel' no trae indice por org (eso es 'BaseOrgModel', que ningun modelo
del Supervisor usa). Y aunque lo trajera, Django NO fusiona las clases Meta: un
subclase que declara su propia Meta reemplaza la del padre y pierde los
'indexes' sin que nada avise. Ya paso con 'orders.Order' y
'orders.OrderLineItem', y la evidencia es una migracion real en el arbol
(orders/0003) que BORRO los dos indices porque 'makemigrations' leyo
correctamente que ya no estaban. 'test_org_index_coverage' existe por eso.
Aqui se declara explicito, igual que 'MensajeSupervisor'.
"""

from django.db import models

from common.base import BaseModel
from common.models import Org
from operaciones.situaciones_modelos import Confianza, Riesgo


class FuenteRazonamiento:
    """
    De donde salio la llamada al cerebro.

    No es cosmetico: el mismo cerebro se invoca desde el ciclo automatico y
    desde el chat, y una medicion que los mezcle no significa nada -- el chat
    razona sobre lo que una persona pregunto, el ciclo sobre lo que un detector
    encontro. Son poblaciones distintas.
    """

    CICLO = "ciclo"
    CHAT = "chat"
    SEGUIMIENTO = "seguimiento"
    TODAS = (CICLO, CHAT, SEGUIMIENTO)
    ETIQUETAS = tuple((f, f.capitalize()) for f in TODAS)


class RazonamientoSupervisor(BaseModel):
    """
    Un razonamiento del cerebro, tal como quedo, y el estado previo.

    SE REGISTRA TAMBIEN CUANDO NO CONCLUYE
    --------------------------------------
    Un veredicto no concluyente es EL dato interesante, no un caso a descartar:
    es la medida de cuantas veces el cerebro se quedo corto y lo dijo en vez de
    inventar. Filtrarlo al guardar dejaria la medicion sesgada hacia arriba,
    que es justo la direccion equivocada para una decision de autonomia.
    """

    org = models.ForeignKey(
        Org, on_delete=models.CASCADE, related_name="razonamientos_ia"
    )

    #  A QUE APUNTA  --  los dos opcionales, pero no los dos vacios (ver el
    #  CheckConstraint de abajo). Misma regla que 'registrar_aprendizaje' ya
    #  aplica sobre las lecciones: un registro huerfano no lo vuelve a
    #  encontrar nadie.
    propuesta = models.ForeignKey(
        "operaciones.PropuestaSupervisor",
        on_delete=models.CASCADE,
        related_name="razonamientos",
        null=True,
        blank=True,
        help_text="La propuesta sobre la que razono, si hubo una.",
    )
    situacion = models.ForeignKey(
        "operaciones.SituacionOperativa",
        on_delete=models.SET_NULL,
        related_name="razonamientos",
        null=True,
        blank=True,
        help_text="La situacion analizada, si el razonamiento salio de una.",
    )
    fuente = models.CharField(
        max_length=16,
        choices=FuenteRazonamiento.ETIQUETAS,
        default=FuenteRazonamiento.CICLO,
    )

    #  LO QUE CONCLUYO
    concluyente = models.BooleanField(
        default=True,
        help_text="False cuando faltaba informacion, fallo una herramienta o "
                  "se agotaron las vueltas.",
    )
    hechos = models.JSONField(
        default=list, blank=True,
        help_text="Cada hecho con su fuente. Los que no tenian fuente "
                  "verificada ya fueron descartados antes de llegar aqui.",
    )
    inferencias = models.JSONField(default=list, blank=True)
    riesgos = models.JSONField(default=list, blank=True)
    riesgo = models.CharField(
        max_length=16, choices=Riesgo.ETIQUETAS, default=Riesgo.INFORMATIVO
    )
    hipotesis = models.TextField(blank=True, default="")
    confianza = models.CharField(
        max_length=16,
        choices=Confianza.ETIQUETAS,
        default=Confianza.SIN_HIPOTESIS,
    )
    recomendacion = models.TextField(blank=True, default="")
    falta = models.JSONField(
        default=list, blank=True,
        help_text="Lo que el cerebro declaro que no pudo averiguar.",
    )

    #  LO QUE SE LE QUITO  --  la medicion de cuanto intenta afirmar sin base
    descartes = models.JSONField(
        default=list, blank=True,
        help_text="Lo que 'cerebro.validar()' elimino por no tener respaldo.",
    )

    #  CON QUE LO HIZO
    herramientas = models.JSONField(
        default=list, blank=True,
        help_text="Nombres de las herramientas realmente consultadas.",
    )
    vueltas = models.PositiveSmallIntegerField(default=0)
    agotado = models.BooleanField(
        default=False, help_text="Se quedo sin vueltas antes de cerrar."
    )
    modelo = models.CharField(max_length=120, blank=True, default="")
    proveedor = models.CharField(max_length=60, blank=True, default="")
    duracion_ms = models.PositiveIntegerField(default=0)

    #  CONTRA QUE SE COMPARA  --  el estado PREVIO al enriquecimiento
    analisis_deterministico = models.JSONField(
        default=dict, blank=True,
        help_text="El analisis de la regla ANTES de que el cerebro lo tocara. "
                  "Si aqui quedara el analisis ya enriquecido, la comparacion "
                  "seria contra si misma y daria coincidencia siempre.",
    )
    enriquecio = models.BooleanField(
        default=False,
        help_text="True solo si el veredicto llego a modificar el analisis. "
                  "En 'solo registra' es siempre False.",
    )

    registrado_en = models.DateTimeField()

    class Meta:
        db_table = "operaciones_razonamiento_supervisor"
        ordering = ["-registrado_en", "-created_at"]
        indexes = [
            #  Declarado a mano a proposito -- ver el encabezado del archivo.
            models.Index(fields=["org", "-registrado_en"]),
            models.Index(fields=["propuesta", "-registrado_en"]),
            models.Index(fields=["org", "fuente", "-registrado_en"]),
        ]
        constraints = [
            #  Espeja la garantia 3 de 'cerebro.validar()': hipotesis y
            #  confianza viajan juntas. La regla ya vive en el codigo; que
            #  tambien viva en la base es a proposito -- un escritor futuro que
            #  no pase por 'validar()' choca con la restriccion en vez de
            #  dejar una hipotesis sin ponderar.
            models.CheckConstraint(
                condition=(
                    models.Q(hipotesis="", confianza=Confianza.SIN_HIPOTESIS)
                    | (~models.Q(hipotesis="")
                       & ~models.Q(confianza=Confianza.SIN_HIPOTESIS))
                ),
                name="razonamiento_hipotesis_con_confianza",
            ),
            #  Un razonamiento huerfano no lo encuentra nadie.
            models.CheckConstraint(
                condition=(
                    models.Q(propuesta__isnull=False)
                    | models.Q(situacion__isnull=False)
                ),
                name="razonamiento_apunta_a_algo",
            ),
        ]
        verbose_name = "razonamiento del cerebro"
        verbose_name_plural = "razonamientos del cerebro"

    def __str__(self):
        estado = "concluyente" if self.concluyente else "sin concluir"
        return f"{self.fuente} · {self.riesgo} · {estado}"

    @property
    def comparable(self) -> bool:
        """Si hay estado previo guardado contra el cual comparar."""
        return bool(self.analisis_deterministico)

    @property
    def aporto_algo(self) -> bool:
        """
        Si el cerebro agrego informacion que la regla no tenia.

        NO DICE QUIEN ACERTO, Y NO PUEDE DECIRLO. Quien acerto sale de lo que
        una persona decidio y de lo que despues ocurrio -- eso vive en
        'DecisionSupervisor' y en 'AprendizajeSupervisor', no aqui. Una
        propiedad que prometiera "coincide con la regla" estaria comparando dos
        redacciones libres, y el modelo dice lo mismo de diez formas: eso da
        ruido, no medicion.

        Lo que SI es comparable, porque la regla no lo produce en absoluto:
            un riesgo por encima de 'informativo'   la regla no estima riesgo
            una hipotesis con su confianza          la regla no hipotetiza
            datos declarados como faltantes         la regla no sabe que no sabe

        Tres aportes de tipo distinto, los tres verificables sin interpretar
        texto.
        """
        return bool(
            self.riesgo != Riesgo.INFORMATIVO
            or self.hipotesis
            or self.falta
        )

    @property
    def intento_afirmar_sin_base(self) -> bool:
        """
        Si 'validar()' tuvo que quitarle algo por no tener fuente.

        Es la contracara de 'aporto_algo' y la metrica mas incomoda de las dos:
        cuenta las veces que el modelo afirmo algo que ninguna herramienta
        respaldaba. Un numero que suba aca es motivo para NO subir autonomia.
        """
        return bool(self.descartes)
