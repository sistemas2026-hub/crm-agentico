# -*- coding: utf-8 -*-
"""
================================================================================
 CUANTO TARDA PROGRAMACION, MEDIDO DONDE CORRE  --  21/11/2026
================================================================================
El usuario: «la pestaña de Supervisor cuando se recarga demora en salir».

El arreglo (`campo/revision_sin_repetir.py`) se midio en una base de pruebas
con ordenes sin fotos: 339 consultas por pedido contra 50. Ese numero es un
piso, no lo que pasa en produccion: alla las ordenes tienen fotos, analisis y
medicion, y la base esta a un salto de red. Este comando mide lo mismo que
pide la pantalla (`dia_publicado.del_dia`), con el atajo apagado y prendido.

    python manage.py medir_programacion
    python manage.py medir_programacion --org <uuid> --fecha 2026-11-21

NO ESCRIBE EN LA BASE. Lo unico que deja es lo que la pantalla ya deja sola:
la revision de cada orden en la cache, por un minuto.

NO IMPRIME NADA DE NINGUN CLIENTE: cuentas y milisegundos. Se puede pegar en
un chat.
================================================================================
"""
import datetime as dt
import os
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from common.models import Org
from common.tasks import set_rls_context


class Command(BaseCommand):
    help = ("Mide cuanto tarda lo que pide la pantalla de Programacion, con y "
            "sin el atajo de la revision. No escribe en la base.")

    def add_arguments(self, parser):
        parser.add_argument("--org", default="",
                            help="UUID de la empresa. Sin esto, la unica que "
                                 "haya; si hay varias, las lista.")
        parser.add_argument("--fecha", default="",
                            help="AAAA-MM-DD. Sin esto, hoy en la zona de la "
                                 "empresa.")

    def _empresa(self, pedido: str):
        if pedido:
            try:
                return Org.objects.get(pk=pedido)
            except (Org.DoesNotExist, ValueError, TypeError) as e:
                raise CommandError(
                    f"No se encontro esa empresa ({type(e).__name__})")
        empresas = list(Org.objects.order_by("created_at")[:50])
        if len(empresas) == 1:
            return empresas[0]
        if not empresas:
            raise CommandError("No hay ninguna empresa.")
        self.stdout.write("Hay varias empresas. Repetilo con --org <uuid>:")
        for e in empresas:
            self.stdout.write(f"  {e.id}  {e.name}")
        raise CommandError("Falta --org.")

    def handle(self, *args, **opciones):
        from django.utils import timezone

        from campo import dia_publicado as D
        from campo import reparto as R
        from campo import revision_del_cierre as RC
        from campo import revision_sin_repetir as RSR

        org = self._empresa((opciones["org"] or "").strip())
        set_rls_context(org.id)

        zona = R._zona_de(org)
        if opciones["fecha"]:
            try:
                fecha = dt.date.fromisoformat(opciones["fecha"])
            except ValueError:
                raise CommandError("La fecha va como AAAA-MM-DD.")
        else:
            fecha = timezone.now().astimezone(zona).date()

        from campo import material_del_dia as MD

        #  Con la vida que este proceso ya tiene puesta; si esta apagado, con
        #  la de fabrica: lo que se quiere ver es el atajo andando.
        vida_puesta = RSR.vida() or RSR.VIDA_POR_DEFECTO

        def medir(prendido: bool, que=None) -> dict:
            antes = os.environ.get(RSR.VARIABLE)
            os.environ[RSR.VARIABLE] = str(vida_puesta) if prendido else "0"
            cuenta = {"revisadas": 0, "ms": 0.0}
            real = RC.revisar

            def contada(orden, **kw):
                t = time.perf_counter()
                try:
                    return real(orden, **kw)
                finally:
                    cuenta["revisadas"] += 1
                    cuenta["ms"] += (time.perf_counter() - t) * 1000

            RC.revisar = contada
            try:
                with CaptureQueriesContext(connection) as consultas:
                    t = time.perf_counter()
                    d = (que or D.del_dia)(org, fecha)
                    total = (time.perf_counter() - t) * 1000
            finally:
                RC.revisar = real
                if antes is None:
                    os.environ.pop(RSR.VARIABLE, None)
                else:
                    os.environ[RSR.VARIABLE] = antes
            if que is not None:
                return {"ms": total, "consultas": len(consultas),
                        "revisadas": cuenta["revisadas"],
                        "ms_revisar": cuenta["ms"]}
            filas = [f for c in d["cuadrillas"] for f in c["ordenes"]]
            filas += d["con_alguien_que_no_sale"]
            return {
                "ms": total, "consultas": len(consultas),
                "revisadas": cuenta["revisadas"], "ms_revisar": cuenta["ms"],
                "del_dia": len(filas), "por_revisar": len(d["por_revisar"]),
                "con_revision": sum(1 for f in [*filas, *d["por_revisar"]]
                                    if f.get("revision") is not None),
            }

        #  El primero no cuenta: carga modulos y abre la conexion.
        medir(False)
        apagado = medir(False)
        prendido_1 = medir(True)
        prendido_2 = medir(True)
        #  El material del dia se pide a la vez que la pantalla al cargarla.
        material = medir(False, MD.calcular)

        w = self.stdout.write
        w(f"Programacion del {fecha.isoformat()} "
          f"({RSR.VARIABLE} en este proceso: {RSR.vida()} s"
          f"{'' if RSR.encendido() else ' = APAGADO'})")
        w(f"  ordenes del dia: {apagado['del_dia']}   "
          f"de dias anteriores por revisar: {apagado['por_revisar']}   "
          f"con revision del cierre: {apagado['con_revision']}")
        w("")
        w("  como                         tarda      consultas   revisadas   "
          "de eso, revisando")
        for nombre, m in (("sin el atajo, cada vez   ", apagado),
                          ("con el atajo, 1er pedido ", prendido_1),
                          ("con el atajo, repetido   ", prendido_2),
                          ("el material del dia      ", material)):
            w(f"  {nombre}   {m['ms']:7.0f} ms   {m['consultas']:6d}      "
              f"{m['revisadas']:4d}        {m['ms_revisar']:7.0f} ms")
        w("")
        if apagado["ms"] > 0:
            w(f"  El pedido repetido tarda el "
              f"{100 * prendido_2['ms'] / apagado['ms']:.0f}% de lo que "
              f"tardaba, con {apagado['consultas'] - prendido_2['consultas']} "
              f"consultas menos.")
        w("  LA RECARGA EN FRIO (nadie miro la pantalla en el ultimo minuto) "
          "cuesta el renglon «sin el atajo» mas el del material, a la vez.")
        if material["revisadas"]:
            w(f"  OJO: el material del dia reviso {material['revisadas']} "
              "ordenes. No tiene que revisar ninguna.")
        if prendido_2["revisadas"]:
            w("  OJO: el pedido repetido volvio a revisar "
              f"{prendido_2['revisadas']} ordenes. Con el atajo andando eso "
              "es 0 salvo que algo haya cambiado entre los dos pedidos; si se "
              "repite, la cache no esta guardando.")
        w("  (El 1er pedido puede salir ya rapido: si alguien tiene la "
          "pantalla abierta, la cache ya esta caliente.)")
