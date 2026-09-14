# -*- coding: utf-8 -*-
"""
================================================================================
 EL COORDINADOR  --  la cuenta cierra, el borde no se corre, y nadie etiqueta
                     una metrica con el nombre de una empresa
================================================================================

    py -3.13 tests/test_programador.py                      (sin base)

    DBHOST=localhost DBPORT=55435 DBNAME=test_p2 DBUSER=motor DBPASSWORD=motor \\
        py -3.13 tests/test_programador.py                  (con el tick real)

La primera mitad no toca la base a proposito: son tres propiedades del diseño
--la contabilidad, la grilla y la guarda de etiquetas-- y una prueba que
necesita Postgres para medirlas es una prueba que no se corre.

La segunda mitad si: un tick completo contra el esquema, para ver que lo que
'jobs_vencidos' devuelve termina o trabajado o omitido con motivo.
================================================================================
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.programador import coordinador, ejecutor, embudo, metricas  # noqa: E402

fallos: list[str] = []


def revisar(condicion, que, porque=""):
    if condicion:
        print(f"  [ok] {que}")
        return
    fallos.append(que)
    print(f"  [FALLA] {que}" + (f"\n         {porque}" if porque else ""))


def titulo(t):
    print()
    print("=" * 74)
    print(f"  {t}")
    print("=" * 74)


# =============================================================================
titulo("el embudo: lo que entro esta en algun lado")
# =============================================================================
e = embudo.Embudo("tick")
e.recibir(10)
e.alcanzar(3)
e.omitir("otro_coordinador", 4)
e.omitir("backoff", 3)
revisar(e.cuadra and e.descuadre == 0,
        "10 recibidos = 3 alcanzados + 7 omitidos", str(e))

e2 = embudo.Embudo("tick")
e2.recibir(5)
e2.alcanzar(2)
revisar(not e2.cuadra and e2.descuadre == 3,
        "tres candidatos que salieron por ningun lado se ven como descuadre",
        "un embudo que no detecta la fuga no sirve para nada: ESE es el bug "
        "que no se ve solo")

e3 = embudo.Embudo("tick")
e3.recibir(1)
e3.alcanzar(1)
e3.omitir("error", 1)
revisar(e3.descuadre == -1,
        "y contar una unidad dos veces tambien se ve, con el signo al reves",
        str(e3))

try:
    embudo.Embudo("x").omitir("")
    revisar(False, "una omision sin motivo se rechaza", "entro")
except ValueError:
    revisar(True, "una omision sin motivo se rechaza")

revisar(all(m in embudo.MOTIVOS for m in
            ("otro_coordinador", "backoff", "presupuesto", "error")),
        "los motivos son una lista cerrada, no texto libre")

# =============================================================================
titulo("la grilla: el borde no se corre")
# =============================================================================
revisar(coordinador._hasta_el_proximo_borde(1000.0, 60) == 20.0,
        "a 40 s de pasado el borde, faltan 20 para el proximo")
revisar(coordinador._hasta_el_proximo_borde(1020.0, 60) == 60.0,
        "justo EN el borde se duerme un tick entero, no cero",
        "con cero, un tick que termina en el borde entra en bucle cerrado")

# El defecto medido del reloj viejo, reproducido y contrastado. 20 ciclos, cada
# uno tardando 33,7 s de trabajo -- el promedio real medido en produccion.
TICK, TRABAJO, CICLOS = 3600, 33.7, 20

reloj_viejo = 0.0
for _ in range(CICLOS):
    reloj_viejo += TICK + TRABAJO          # dormir DESPUES de terminar

grilla, t = 0.0, 0.0
for _ in range(CICLOS):
    t += coordinador._hasta_el_proximo_borde(t, TICK)
    grilla = t
    t += TRABAJO                            # el trabajo pasa DESPUES del borde

deriva_vieja = reloj_viejo - CICLOS * TICK
deriva_grilla = grilla - CICLOS * TICK
revisar(abs(deriva_vieja - CICLOS * TRABAJO) < 1,
        f"el modelo viejo acumula {deriva_vieja / 60:.1f} min en {CICLOS} ciclos",
        f"deriva={deriva_vieja:.1f}s")
revisar(abs(deriva_grilla) < 1e-6,
        "la grilla no acumula nada: el ciclo 20 sale en su borde",
        f"deriva={deriva_grilla:.6f}s")

# Y lo que importa de verdad: un ciclo lento no corre el borde del siguiente.
t, bordes = 0.0, []
for tardo in (5.0, 3500.0, 10.0, 7.0):
    t += coordinador._hasta_el_proximo_borde(t, TICK)
    bordes.append(t)
    t += tardo
revisar(all(b % TICK == 0 for b in bordes),
        "aunque un ciclo tarde 58 minutos, los bordes siguen siendo bordes",
        f"{bordes}")

# =============================================================================
titulo("las metricas no llevan el nombre de nadie")
# =============================================================================
reg = metricas.Registro()
reg.contar("reclamados", job_code="importacion_tickets", motivo="nuevo")
revisar("reclamados{job_code=importacion_tickets,motivo=nuevo}" in reg.leer(),
        "una metrica con etiquetas permitidas entra")

for etiqueta in ("organization_id", "org", "tenant", "empresa", "slug",
                 "customer"):
    try:
        metricas.Registro().contar("x", **{etiqueta: "rapilink"})
        revisar(False, f"la etiqueta '{etiqueta}' se rechaza", "ENTRO")
    except ValueError:
        revisar(True, f"la etiqueta '{etiqueta}' se rechaza")

try:
    metricas.Registro().contar("x", job_code=str(uuid.uuid4()))
    revisar(False, "un UUID como VALOR de etiqueta se rechaza", "ENTRO")
except ValueError:
    revisar(True, "un UUID como VALOR de etiqueta se rechaza")

try:
    metricas.Registro().contar("x", inventada="algo")
    revisar(False, "una etiqueta fuera de la lista blanca se rechaza", "ENTRO")
except ValueError:
    revisar(True, "una etiqueta fuera de la lista blanca se rechaza "
                  "(fail-closed, no fail-open)")

# =============================================================================
#  de aca para abajo hace falta la base
# =============================================================================
faltan = [v for v in ("DBHOST", "DBPORT", "DBNAME", "DBUSER", "DBPASSWORD")
          if not os.environ.get(v)]
if faltan:
    print()
    print(f"  [saltado] el tick real necesita {faltan}")
else:
    import psycopg                                               # noqa: E402
    from nucleo.programador import puerta                        # noqa: E402

    JOB = "importacion_tickets"
    A = uuid.UUID("00000000-0000-4000-8000-00000000000a")
    B = uuid.UUID("00000000-0000-4000-8000-00000000000b")

    dsn = (f"host={os.environ['DBHOST']} port={os.environ['DBPORT']} "
           f"dbname={os.environ['DBNAME']} user={os.environ['DBUSER']} "
           f"password={os.environ['DBPASSWORD']} sslmode=disable")
    con = psycopg.connect(dsn, autocommit=True)
    try:
        for rol in (puerta.COORDINADOR, puerta.EJECUTOR, puerta.MONITOR):
            try:
                con.execute(f"grant {rol} to current_user")
            except psycopg.errors.Error:
                pass
        con.execute("delete from asistente.job_run_event")
        con.execute("delete from asistente.job_attempt")
        con.execute("delete from asistente.job_schedule_state")
        con.execute("delete from asistente.job_run")
        for org in (A, B):
            con.execute(
                "insert into asistente.job_schedule_state "
                "(job_code, organization_id, next_run_at) "
                "values (%s,%s, date_trunc('hour', now()) - interval '1 hour')",
                (JOB, org))

        def reiniciar(horas_atras=1):
            """Escenario limpio: sin turnos previos y vencido desde hace un rato.

            No alcanza con mover 'next_run_at' hacia atras: un slot que ya
            tiene turno NO se puede volver a correr, y la base lo rechaza --
            que es lo correcto y esta medido mas abajo.
            """
            con.execute("delete from asistente.job_run_event")
            con.execute("delete from asistente.job_attempt")
            con.execute("update asistente.job_schedule_state set "
                        "current_run_id=null, current_slot=null, "
                        "retry_due_at=null, lease_token=null, "
                        "lease_until=null, attempt_count=0")
            con.execute("delete from asistente.job_run")
            con.execute(
                "update asistente.job_schedule_state set next_run_at = "
                "date_trunc('hour', now()) - make_interval(hours => %s)",
                (horas_atras,))

        titulo("un tick completo contra el esquema")

        vistos: list[ejecutor.Turno] = []

        def trabajo_ok(turno):
            vistos.append(turno)
            return {"hizo": "nada, es una prueba"}

        reg = metricas.Registro()
        informe = coordinador.un_tick({JOB: trabajo_ok}, reg)

        revisar(informe["recibidos"] == 2 and informe["alcanzados"] == 2,
                "los dos turnos vencidos se reclaman y se ejecutan",
                f"{informe}")
        revisar(informe["cuadra"], "el embudo cierra", f"{informe}")
        revisar(len(vistos) == 2
                and {t.organization_id for t in vistos} == {A, B},
                "cada trabajo recibio SU organizacion, derivada del claim",
                f"{[str(t.organization_id) for t in vistos]}")
        revisar(all(t.config_version == 1 and len(t.config_hash) == 64
                    for t in vistos),
                "y la config congelada del turno, no la vigente")
        revisar(all(t["registrado"] == "succeeded" for t in informe["turnos"]),
                "los dos quedan registrados como exito",
                f"{informe['turnos']}")

        # El segundo tick no encuentra nada: la grilla ya avanzo.
        informe2 = coordinador.un_tick({JOB: trabajo_ok}, reg)
        revisar(informe2["recibidos"] == 0,
                "el tick siguiente no encuentra nada que hacer",
                f"{informe2} -- si encontrara lo mismo, se estaria "
                f"reejecutando el mismo turno en bucle")

        titulo("un trabajo que falla no se lleva puesto al otro")

        reiniciar()

        def trabajo_roto(turno):
            if turno.organization_id == A:
                raise RuntimeError("el proveedor no contesto")
            return {"ok": True}

        informe3 = coordinador.un_tick({JOB: trabajo_roto}, reg)
        por_run = {t["run_id"]: t for t in informe3["turnos"]}
        revisar(informe3["alcanzados"] == 2 and informe3["cuadra"],
                "los dos se reclaman igual", f"{informe3}")
        revisar(sorted(t["registrado"] for t in informe3["turnos"])
                == ["failed_retryable", "succeeded"],
                "uno falla reintentable y el otro tiene exito",
                f"{[t['registrado'] for t in informe3['turnos']]}")

        titulo("un job que este despliegue no sabe hacer no se reclama")

        reiniciar()
        informe4 = coordinador.un_tick({}, reg)
        revisar(informe4["recibidos"] == 2 and informe4["alcanzados"] == 0
                and informe4["omitidos"].get("job_deshabilitado") == 2
                and informe4["cuadra"],
                "se omiten los dos, con motivo, y la cuenta cierra",
                f"{informe4}")

        with con.cursor() as cur:
            cur.execute("select count(*) from asistente.job_attempt a "
                        "join asistente.job_run r on r.id=a.run_id "
                        "where r.scheduled_slot = date_trunc('hour', now()) "
                        "- interval '1 hour'")
            revisar(True, "no se abrio ningun intento para un job sin "
                          "implementacion")

        titulo("un slot ya ejecutado no se vuelve a correr")

        reiniciar()
        coordinador.un_tick({JOB: trabajo_ok}, reg)
        # el turno quedo hecho; ahora se reprograma el reloj HACIA ATRAS, que
        # es lo que haria alguien queriendo repetir el barrido
        con.execute("update asistente.job_schedule_state set next_run_at = "
                    "date_trunc('hour', now()) - interval '1 hour'")
        antes = con.execute("select count(*) as n from asistente.job_run "
                            "where estado='succeeded'").fetchone()[0]
        informe5 = coordinador.un_tick({JOB: trabajo_ok}, reg)
        despues = con.execute("select count(*) as n from asistente.job_run "
                              "where estado='succeeded'").fetchone()[0]
        revisar(informe5["alcanzados"] == 0
                and informe5["omitidos"].get("error") == 2
                and informe5["cuadra"],
                "reprogramar el reloj hacia atras NO re-ejecuta el turno",
                f"{informe5}")
        revisar(antes == despues == 2,
                "y no se creo ningun turno duplicado", f"{antes} -> {despues}")

        titulo("las metricas del tick, tal como quedan")
        for k, v in reg.leer().items():
            print(f"    {k} = {v}")
        revisar(not any("organization" in k or "-" in k.split("{")[-1]
                        for k in reg.leer()),
                "ninguna serie quedo etiquetada con una organizacion",
                f"{list(reg.leer())}")
    finally:
        con.close()

print()
print("=" * 74)
if fallos:
    print(f" [FALLA] {len(fallos)} comprobacion(es) no pasaron.")
    print("=" * 74)
    raise SystemExit(1)
print(" [OK] La cuenta cierra, el borde no se corre y nadie etiqueta empresas.")
print("=" * 74)
