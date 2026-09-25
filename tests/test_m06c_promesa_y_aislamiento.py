# -*- coding: utf-8 -*-
"""
================================================================================
 M06-C  --  la aprobacion ATADA de agregar_promesa_pago, y el sello (sin base)
================================================================================

Pruebas 6-15 del bloque, mas los bypass de M06-A/B aplicados a la promesa y la
parte estatica de la RLS. Codigo real (frontera, ejecutor HTTP, motor); base y
red sustituidas con el entorno de tests/test_m06a_gate_critico.py, que se
importa. La parte que necesita PostgreSQL (RLS de verdad, sello escrito por la
base, trigger) esta en tests/test_m06c_postgres.py.

Datos inventados: factura 999001, dominio .invalid. Ningun cliente real.
================================================================================
"""

from __future__ import annotations

import pathlib
import re
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from tests import test_m06a_gate_critico as g                      # noqa: E402
from nucleo.herramientas import http as ejecutor_http             # noqa: E402
from nucleo.modelo import motor                                    # noqa: E402
from nucleo.seguridad import aprobacion as aprobaciones            # noqa: E402
from nucleo.seguridad import autorizacion, frontera, interruptor   # noqa: E402
from nucleo.seguridad import techo as techos                       # noqa: E402

FALLOS: list[str] = []
P = "agregar_promesa_pago"
CONFIG, H, TENANT, SESION = g.CONFIG, g.H, g.TENANT, g.SESION


def afirmar(condicion: bool, que: str, detalle: str = "") -> None:
    if condicion:
        print(f"  [ok]    {que}")
    else:
        FALLOS.append(que)
        print(f"  [FALLA] {que}")
        if detalle:
            print(f"          {detalle}")


def seccion(t: str) -> None:
    print()
    print("-" * 78)
    print(f"  {t}")
    print("-" * 78)


def ejecutar(fila, entorno_kw=None, tenant=TENANT):
    with g.Entorno(**(entorno_kw or {})) as e:
        res, cod, _ = motor.ejecutar_accion_irreversible(CONFIG, fila, tenant)
    return res, cod, e


def main() -> int:
    print("=" * 78)
    print("  M06-C  --  agregar_promesa_pago atada + sello de la aprobacion")
    print("=" * 78)

    seccion("La promesa entra a la puerta critica")
    h = H[P]
    afirmar(h.irreversible and h.aprobacion_humana and not h.invocable_por_servicio,
            "agregar_promesa_pago: irreversible, con aprobacion, no invocable por servicio")
    from tests.test_m10a_gobierno_frontera import R4_DINERO
    afirmar(P in R4_DINERO, "sigue siendo R4: la clasificacion no cambio")
    afirmar(h.nivel_autonomia is None and techos.nivel_requerido_de(h) == 2,
            "su nivel de autonomia no cambio (no declarado, exige 2)")

    seccion("6. Sin aprobacion -> bloqueada, cero efecto")
    _, cod, e = ejecutar(g.fila(P, estado="pendiente", revisado_por=None,
                                revisado_en=None))
    afirmar(cod == aprobaciones.NO_APROBADA and e.red.llamadas == [],
            f"pendiente -> {cod}, {len(e.red.llamadas)} llamadas")
    with g.Entorno() as e:
        cod = g.intento_directo(lambda: frontera.critica(
            TENANT, P, argumentos=g.ARGS[P], aprobacion=None).__enter__())
    afirmar(cod == aprobaciones.SIN_APROBACION and e.red.llamadas == [],
            f"sin ninguna fila de aprobacion -> {cod}")

    seccion("7. Aprobacion valida -> supera el gate y sigue")
    _, cod, e = ejecutar(g.fila(P))
    afirmar(cod is None and len(e.red.escrituras) == 1
            and "/api/promesa-pago/" in e.red.escrituras[0][1],
            f"con todo en regla sale UNA vez ({e.red.escrituras})")
    permitida = [b for b in e.bitacora if b.get("decision") == "permitida"
                 and "aprobada por supervisor.prueba" in (b.get("motivo") or "")]
    afirmar(len(permitida) == 1, "la auditoria registra la autorizacion con el aprobador")

    seccion("8. La aprobacion de una herramienta no sirve para la otra")
    aprob_pago = aprobaciones.desde_fila(g.fila("registrar_pago"), TENANT)
    aprob_prom = aprobaciones.desde_fila(g.fila(P), TENANT)
    with g.Entorno() as e:
        c1 = g.intento_directo(lambda: frontera.critica(
            TENANT, P, argumentos=g.ARGS["registrar_pago"],
            aprobacion=aprob_pago).__enter__())
        c2 = g.intento_directo(lambda: frontera.critica(
            TENANT, "registrar_pago", argumentos=g.ARGS[P],
            aprobacion=aprob_prom).__enter__())
    afirmar(c1 == aprobaciones.OTRA_HERRAMIENTA and c2 == aprobaciones.OTRA_HERRAMIENTA
            and e.red.llamadas == [],
            f"aprobacion de registrar_pago usada para la promesa -> {c1}; "
            f"la de la promesa usada para registrar_pago -> {c2}")
    #  La fila de un pago re-etiquetada como promesa (alguien cambia la
    #  herramienta en la fila): la huella no coincide, y si la acomoda, el sello.
    f = g.fila("registrar_pago")
    f.update(herramienta=P, argumentos=dict(g.ARGS[P]),
             hash_argumentos=aprobaciones.hash_de(g.ARGS[P]))
    _, cod, e = ejecutar(f)
    afirmar(cod == aprobaciones.ALTERADA and e.red.llamadas == [],
            f"la fila de un pago reescrita como promesa (args y huella acomodados) "
            f"-> {cod}: el sello la delata")

    seccion("9. Argumentos modificados despues de aprobar")
    otros = dict(g.ARGS[P], fecha_limite="2026-12-31")
    _, cod, e = ejecutar(g.fila(P, argumentos=otros))
    afirmar(cod == aprobaciones.OTROS_ARGUMENTOS and e.red.llamadas == [],
            f"otra fecha limite en la fila -> {cod}")
    _, cod, e = ejecutar(g.fila(P, argumentos=otros,
                                hash_argumentos=aprobaciones.hash_de(otros)))
    afirmar(cod == aprobaciones.ALTERADA and e.red.llamadas == [],
            f"otra fecha Y la huella recalculada (la alteracion 'completa') -> {cod}")
    with g.Entorno() as e:
        with frontera.critica(TENANT, P, argumentos=g.ARGS[P], aprobacion=aprob_prom):
            cod = g.intento_directo(lambda: ejecutor_http.ejecutar(
                H[P], dict(g.ARGS[P], id_factura=999002), TENANT))
    afirmar(cod == frontera.PERMISO_DE_OTRA_ACCION and e.red.llamadas == [],
            f"permiso de la promesa de 999001 usado para 999002 -> {cod}")

    seccion("10. Tenant modificado")
    _, cod, e = ejecutar(g.fila(P), tenant="otra-empresa")
    afirmar(cod in (aprobaciones.ALTERADA, techos.AUSENTE, techos.OTRO_TENANT)
            and e.red.llamadas == [],
            f"la aprobacion de rapilink ejecutada como otra empresa -> {cod}")
    with g.Entorno() as e:
        aprob_otro = aprobaciones.desde_fila(g.fila(P), "otra-empresa")
        cod = g.intento_directo(lambda: frontera.critica(
            TENANT, P, argumentos=g.ARGS[P], aprobacion=aprob_otro).__enter__())
    afirmar(cod == aprobaciones.OTRO_TENANT and e.red.llamadas == [],
            f"una aprobacion leida para otra empresa -> {cod}")
    _, cod, e = ejecutar(g.fila(P, organization_id="00000000-0000-0000-0000-0000000000bb"))
    afirmar(cod == aprobaciones.ALTERADA and e.red.llamadas == [],
            f"la organizacion de la fila cambiada -> {cod}")

    seccion("11. Origen modificado")
    _, cod, e = ejecutar(g.fila(P, origen="evento:otro-mensaje"))
    afirmar(cod == aprobaciones.ALTERADA and e.red.llamadas == [],
            f"otro origen en la fila -> {cod} (antes de M06-C solo se exigia 'no vacio')")

    seccion("El sello, por su cuenta")
    _, cod, e = ejecutar(g.fila(P, sello_aprobacion=None))
    afirmar(cod == aprobaciones.SIN_SELLO and e.red.llamadas == [],
            f"aprobacion sin sello (escrita por fuera de aprobar_accion_propuesta) -> {cod}")
    _, cod, e = ejecutar(g.fila(P, revisado_por="otra.persona"))
    afirmar(cod == aprobaciones.ALTERADA and e.red.llamadas == [],
            f"otro aprobador en la fila -> {cod}")
    _, cod, e = ejecutar(g.fila(P, sello_aprobacion="0" * 64))
    afirmar(cod == aprobaciones.ALTERADA and e.red.llamadas == [],
            f"sello falso -> {cod}")

    seccion("12. Replay -> no duplica")
    with g.Entorno() as e:
        _, c1, _ = motor.ejecutar_accion_irreversible(CONFIG, g.fila(P), TENANT)
        _, c2, _ = motor.ejecutar_accion_irreversible(CONFIG, g.fila(P), TENANT)
    afirmar(c1 is None and c2 is None and len(e.red.escrituras) == 1,
            f"la misma aprobacion dos veces -> {len(e.red.escrituras)} escritura")

    seccion("13-15. Las demas barreras siguen mandando")
    _, cod, e = ejecutar(g.fila(P), {"interruptor_fila": g.DETENIDO})
    afirmar(cod == interruptor.CODIGO_BLOQUEO and e.red.llamadas == [],
            f"13. kill switch detenido -> {cod}")
    _, cod, e = ejecutar(g.fila(P), {"nivel": 1})
    afirmar(cod == techos.INSUFICIENTE and e.red.llamadas == [],
            f"14. techo 1 (autonomia insuficiente) -> {cod}")
    _, cod, e = ejecutar(g.fila(P), {"etapa": False})
    afirmar(cod == "AUTONOMIA_2_NO_ACTIVA" and e.red.llamadas == [],
            f"14. etapa apagada -> {cod}")
    _, cod, e = ejecutar(g.fila(P), {"autorizadas": ()})
    afirmar(cod == autorizacion.SIN_AUTORIZACION and e.red.llamadas == [],
            f"15. sin autorizacion granular -> {cod}")

    seccion("Bypass: ningun camino llega al efecto sin la puerta critica")
    for nombre, fn in (
            ("_ejecutar_tool (conversacion/agente)", lambda: motor._ejecutar_tool(
                h, SESION, dict(g.MODELO[P]), TENANT, CONFIG.variables_tenant,
                origen="evento:bypass")),
            ("ejecutor directo", lambda: ejecutor_http.ejecutar(h, g.ARGS[P], TENANT)),
            ("ruta de servicio", lambda: motor.ejecutar_para_servicio(
                CONFIG, h, dict(g.MODELO[P]), TENANT))):
        with g.Entorno() as e:
            try:
                fn()
                cod = None
            except frontera.AccionExternaNoAutorizada as ex:
                cod = ex.codigo
            except Exception as ex:                              # noqa: BLE001
                cod = type(ex).__name__
        afirmar(cod is not None and e.red.llamadas == [], f"{nombre} -> {cod}")
    for puerta in ("humana", "autonoma"):
        with g.Entorno() as e:
            ctx = (frontera.humana(TENANT, P, actor="alguien", evidencia="x")
                   if puerta == "humana" else frontera.autonoma(TENANT, P, origen="x"))
            with ctx:
                cod = g.intento_directo(lambda: ejecutor_http.ejecutar(h, g.ARGS[P], TENANT))
        afirmar(cod == frontera.IRREVERSIBLE_SIN_APROBACION and e.red.llamadas == [],
                f"frontera.{puerta} + ejecutor -> {cod}")
    with g.Entorno() as e:
        _, cod = motor.ejecutar_accion_aprobada(CONFIG, g.fila(P))
    afirmar(cod == frontera.IRREVERSIBLE_SIN_APROBACION and e.red.llamadas == [],
            f"el ejecutor de aprobaciones COMUN (el que usaba antes) -> {cod}")
    with g.Entorno() as e:
        with frontera.critica(TENANT, P, argumentos=g.ARGS[P], aprobacion=aprob_prom):
            ejecutor_http.ejecutar(h, g.ARGS[P], TENANT)
    afirmar(len(e.red.escrituras) == 1,
            "CONTROL: el mismo ejecutor, por la puerta critica con su aprobacion, sale")

    seccion("La conversacion propone la promesa atada, no la ejecuta")
    from nucleo.modelo.cliente import Llamada, Respuesta
    guion = [Respuesta(llamadas=[Llamada(P, dict(g.MODELO[P]))]),
             Respuesta(contenido="Quedo pendiente de aprobacion.")]
    propuestas = []

    def guardar(tenant, herr, argumentos, resumen, rol, quien, **kw):
        propuestas.append({"herramienta": herr, "argumentos": argumentos, **kw})
        return "prop-promesa", False  # M06-F: firma de B5, (id, ya_existia)

    with g.Entorno() as e:
        sustituir = [(motor.cliente, "chat",
                      lambda *a, **k: guion.pop(0) if guion else Respuesta(contenido="fin")),
                     (motor, "recuperar", lambda *a, **k: ([], 0.0)),
                     (motor.catalogo_habilidades, "indice_de", lambda *a, **k: []),
                     (motor.consumo, "anotar", lambda *a, **k: None),
                     (motor.persistencia, "guardar_accion_propuesta", guardar)]
        orig = [(o, a, getattr(o, a)) for o, a, _ in sustituir]
        for o, a, f_ in sustituir:
            setattr(o, a, f_)
        try:
            motor.responder(CONFIG, "facturacion", "el cliente promete pagar",
                            [], None, origen="evento:wamid-promesa")
        finally:
            for o, a, f_ in orig:
                setattr(o, a, f_)
    p0 = propuestas[0] if propuestas else {}
    afirmar(e.red.llamadas == [] and p0.get("herramienta") == P
            and p0.get("hash_argumentos") == aprobaciones.hash_de(p0.get("argumentos"))
            and p0.get("origen") == "evento:wamid-promesa",
            f"0 llamadas; 1 propuesta con huella y origen del mensaje ({len(e.red.llamadas)} llamadas)")

    seccion("RLS, lo que se ve sin base: la migracion")
    sql = (RAIZ / "supabase" / "202609221020_aislamiento_autonomia.sql").read_text(encoding="utf-8")
    plano = " ".join(sql.lower().split())
    for tabla in ("autorizacion_herramienta", "ejecucion_autonoma"):
        afirmar(f"alter table asistente.{tabla} enable row level security" in plano
                and f"alter table asistente.{tabla} force row level security" in plano,
                f"{tabla}: RLS habilitada y FORZADA")
    politicas = re.findall(r"create policy (\w+) on asistente\.(\w+)(.*?);", plano)
    sin_org = [p[0] for p in politicas if "asistente.org_actual()" not in p[2]]
    afirmar(len(politicas) == 5 and not sin_org,
            f"{len(politicas)} politicas nuevas, todas contra la organizacion activa "
            f"(sin org: {sin_org})")
    afirmar(not re.search(r"grant [^;]*(insert|update|delete)[^;]* on asistente\."
                          r"autorizacion_herramienta[^;]* to app_backend", plano),
            "la migracion no le da escritura de autorizaciones al runtime")
    #  Solo las SENTENCIAS: los comentarios de la migracion nombran BYPASSRLS a
    #  proposito, para documentar quien lo tiene.
    sentencias = " ".join(" ".join(l.split("--", 1)[0] for l in sql.splitlines()).lower().split())
    afirmar("using (true)" not in sentencias and "bypassrls" not in sentencias,
            "ninguna politica es 'using (true)' y ninguna sentencia concede BYPASSRLS")

    print()
    print("=" * 78)
    if FALLOS:
        print(f"  {len(FALLOS)} falla(s):")
        for f in FALLOS:
            print(f"    - {f}")
        print("=" * 78)
        return 1
    print("  [OK] La promesa va atada: sin aprobacion no sale, con aprobacion sigue")
    print("       por las demas barreras, y el sello ata tenant, origen y aprobador.")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
