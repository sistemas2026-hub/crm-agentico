# -*- coding: utf-8 -*-
"""
Los movimientos que ya estaban en la base no tenian direccion, y sin direccion
no restan de ninguna parte.

POR QUE ESTA MIGRACION EXISTE
-----------------------------
Hasta el 28/09/2026 `registrar_movimiento` --el camino de la app del tecnico--
guardaba el movimiento sin `ubicacion_origen` ni `ubicacion_destino`. El arreglo
hace que los nuevos si la lleven, y con eso `saldo_de` pasa a ser
`existencia(custodia)`: un solo libro.

Pero eso deja un hueco hacia atras: un consumo viejo sin direccion no resta de
ninguna ubicacion, asi que DEJARIA DE CONTAR. Antes contaba --`saldo_de` sumaba
por tipo-- y despues del arreglo no contaria en ninguna cuenta. Eso seria perder
informacion en silencio, que es peor que el defecto original.

QUE SE RELLENA, Y QUE NO SE TOCA
--------------------------------
    CONSUMO      origen = custodia de su `profile`     el material salio de las
                                                       manos de esa persona, y
                                                       eso lo dice la propia fila
    DEVOLUCION   origen = custodia de su `profile`     idem. A que bodega llego
                                                       no se sabe, y eso queda en
                                                       null a proposito: nadie
                                                       firmo esa recepcion
    AJUSTE       NO SE TOCA                            la direccion de un ajuste
                                                       viejo no esta en la fila.
                                                       Su cantidad es positiva y
                                                       `saldo_de` la sumaba, pero
                                                       eso era una convencion, no
                                                       un dato. Suponerla seria
                                                       inventar en que sentido
                                                       ajusto alguien hace meses

No se rellena NADA que exija interpretar. El `profile` esta en la fila: derivar
su custodia es determinista, no una suposicion. La direccion de un ajuste no
esta, y por eso se deja -- y esas filas quedan visibles para
`test_ningun_movimiento_queda_sin_direccion`, que las nombraria si un escritor
nuevo volviera a producirlas.

Solo toca filas donde LAS DOS ubicaciones son nulas: una fila que ya tiene
direccion es un movimiento del inventario y se respeta como esta.
"""

from django.db import migrations


def rellenar(Movimiento, Ubicacion) -> dict:
    """La logica, aparte de la migracion para poder probarla con datos de verdad.

    Devuelve un recuento por tipo. Es idempotente: una fila que ya tiene
    direccion no entra en el filtro, asi que correrla dos veces no cambia nada.
    """
    TECNICO = "tecnico"
    A_RELLENAR = ("consumo", "devolucion")

    huerfanos = Movimiento.objects.filter(
        ubicacion_origen__isnull=True,
        ubicacion_destino__isnull=True,
        tipo__in=A_RELLENAR,
        profile__isnull=False,
    ).select_related("profile")

    #: (org_id, profile_id) -> ubicacion, para no consultar una vez por fila.
    custodias: dict = {}
    recuento = {"consumo": 0, "devolucion": 0, "custodias_creadas": 0}

    for mov in huerfanos.iterator(chunk_size=500):
        clave = (mov.org_id, mov.profile_id)
        ubicacion = custodias.get(clave)
        if ubicacion is None:
            ubicacion = Ubicacion.objects.filter(
                org_id=mov.org_id, tipo=TECNICO, profile_id=mov.profile_id
            ).first()
            if ubicacion is None:
                ubicacion = Ubicacion.objects.create(
                    org_id=mov.org_id,
                    tipo=TECNICO,
                    profile_id=mov.profile_id,
                    # El nombre bonito lo pone `ubicacion_de_tecnico` cuando hay
                    # despacho; aca no hay `User` a mano y una migracion no debe
                    # depender de la forma de otro modelo.
                    nombre=f"Custodia de {mov.profile_id}",
                )
                recuento["custodias_creadas"] += 1
            custodias[clave] = ubicacion

        mov.ubicacion_origen = ubicacion
        mov.save(update_fields=["ubicacion_origen"])
        recuento[mov.tipo] = recuento.get(mov.tipo, 0) + 1

    return recuento


def adelante(apps, schema_editor):
    Movimiento = apps.get_model("campo", "MovimientoDeMaterial")
    Ubicacion = apps.get_model("campo", "UbicacionInventario")
    recuento = rellenar(Movimiento, Ubicacion)
    if any(recuento.values()):
        print(f"  [inventario] direcciones rellenadas: {recuento}")


def atras(apps, schema_editor):
    """No se deshace, y eso se declara.

    Poner las ubicaciones en null otra vez no distinguiria las filas que esta
    migracion toco de las que ya venian con direccion, asi que borraria datos
    buenos. Una migracion de datos que no puede revertirse con precision no
    finge que puede.
    """
    pass


class Migration(migrations.Migration):

    dependencies = [("campo", "0010_inventario_fase2_y_3")]

    operations = [migrations.RunPython(adelante, atras)]
