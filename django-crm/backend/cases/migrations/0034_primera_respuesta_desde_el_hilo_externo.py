# -*- coding: utf-8 -*-
"""
La primera respuesta de los casos que ya tienen hilo del proveedor.

QUE HACE
--------
Desde el 25/10/2026 una respuesta en el ticket de WispHub cuenta como
respuesta del equipo (cases/signals.py::respuesta_externa_es_primera_respuesta).
La senal cuida lo que llega de aca en adelante; esto aplica la MISMA regla a
las respuestas que ya estaban guardadas, que son la mayoria: la importacion
venia trayendo el hilo desde el 10/09/2026 y nada lo contaba, asi que un
ticket trabajado en WispHub figuraba aca "sin primera respuesta" para siempre.

LA REGLA, COPIADA DE 'sellar_primera_respuesta' Y NO IMPORTADA
-------------------------------------------------------------
Una migracion corre con los modelos historicos y no debe depender de codigo
que puede cambiar despues; por eso la regla se repite aca, entera:

  - solo respuestas con usuario del proveedor y con fecha;
  - la mas temprana de cada caso;
  - nunca antes de que el caso exista aca (un caso importado nace con la hora
    de la importacion: si ya estaba respondido, su primera respuesta es su
    nacimiento);
  - solo si mejora lo que hay: vacio, o un sello posterior.

VUELTA ATRAS: no hace nada, y a proposito. Lo que escribe son hechos -- que
alguien respondio y cuando --, no una preferencia; y lo que habia antes era
un vacio que no se puede distinguir de "nadie respondio". Deshacer no
recuperaria nada y borraria sellos que la senal haya puesto despues.
"""

from django.db import migrations
from django.db.models import Min, Q


def adelante(apps, schema_editor):
    Case = apps.get_model("cases", "Case")
    RespuestaExterna = apps.get_model("cases", "RespuestaExterna")

    primeras = (
        RespuestaExterna.objects
        .exclude(autor_usuario="")
        .exclude(creada_en_proveedor__isnull=True)
        .values("case_id")
        .annotate(primera=Min("creada_en_proveedor"))
    )
    sellados = sin_cambio = 0
    for fila in primeras:
        caso = Case.objects.filter(pk=fila["case_id"]).values(
            "created_at", "first_response_at").first()
        if caso is None:
            continue
        momento = fila["primera"]
        if caso["created_at"] and momento < caso["created_at"]:
            momento = caso["created_at"]
        hechos = Case.objects.filter(pk=fila["case_id"]).filter(
            Q(first_response_at__isnull=True) | Q(first_response_at__gt=momento)
        ).update(first_response_at=momento)
        if hechos:
            sellados += 1
        else:
            sin_cambio += 1
    print(f"  [primera respuesta] casos con hilo externo: {sellados + sin_cambio}"
          f" | sellados: {sellados} | ya tenian una anterior: {sin_cambio}")


class Migration(migrations.Migration):

    dependencies = [
        ("cases", "0033_area_del_caso"),
    ]

    operations = [
        migrations.RunPython(adelante, migrations.RunPython.noop),
    ]
