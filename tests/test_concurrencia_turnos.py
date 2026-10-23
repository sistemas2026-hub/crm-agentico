# -*- coding: utf-8 -*-
"""
EL ORDEN POR CONVERSACION Y EL CUPO POR EMPRESA.

Dos problemas distintos que el motor no tenia resueltos, y que esta prueba
mide por su EFECTO -- no comprobando que exista un lock, que es la clase de
prueba que este proyecto ya descubrio que no sirve: un mecanismo puede estar
y no hacer nada.

  1. ORDEN. El webhook lanza un hilo por mensaje. Dos mensajes del MISMO
     cliente con medio segundo de diferencia se atendian en paralelo, y el
     segundo podia contestarse antes que el primero: el cliente escribe "no
     tengo internet" y despues "ya volvio", y recibe el diagnostico DESPUES
     de la confirmacion. Se afirma que dos turnos de la misma conversacion
     nunca se solapan, corriendolos de verdad en hilos.

  2. CUPO. Los datos de cada empresa estaban aislados; la capacidad no. Se
     afirma que con el tope puesto nunca hay mas de N turnos de esa empresa a
     la vez, y que OTRA empresa no queda esperando por eso.

    py -3.13 tests/test_concurrencia_turnos.py
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for var, valor in (("DBHOST", "localhost"), ("DBPORT", "5432"), ("DBNAME", "postgres"),
                   ("DBUSER", "postgres"), ("DBPASSWORD", "x")):
    os.environ.setdefault(var, valor)

from nucleo.canales import api  # noqa: E402

FALLOS = []


def afirmar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        FALLOS.append(que)


def correr(hilos):
    for h in hilos:
        h.start()
    for h in hilos:
        h.join(timeout=20)
    return not any(h.is_alive() for h in hilos)


# ── 1. dos turnos de la misma conversacion no se solapan ────────────────────
print("\n--- orden por conversacion ---")

CLAVE = ("t1", "whatsapp", "573000000001")
dentro = []
solapados = []
candado = threading.Lock()


def turno(etiqueta, clave=CLAVE, maximo=None, espera=0.05):
    with api._turno_en_orden("t1", clave, maximo):
        with candado:
            dentro.append(etiqueta)
            if len(dentro) > 1:
                solapados.append(tuple(dentro))
        time.sleep(espera)
        with candado:
            dentro.remove(etiqueta)


ok = correr([threading.Thread(target=turno, args=(f"m{i}",)) for i in range(6)])
afirmar(ok, "los seis turnos terminaron")
afirmar(not solapados,
        f"nunca hubo dos turnos a la vez en la misma conversacion "
        f"(solapes: {solapados[:2]})")

# ── 2. conversaciones DISTINTAS no se estorban ──────────────────────────────
print("\n--- y conversaciones distintas siguen en paralelo ---")

a_la_vez = []
maximo_visto = [0]


def turno_suelto(i):
    clave = ("t1", "whatsapp", f"57300000{i:04d}")
    with api._turno_en_orden("t1", clave, None):
        with candado:
            a_la_vez.append(i)
            maximo_visto[0] = max(maximo_visto[0], len(a_la_vez))
        time.sleep(0.15)
        with candado:
            a_la_vez.remove(i)


correr([threading.Thread(target=turno_suelto, args=(i,)) for i in range(5)])
afirmar(maximo_visto[0] > 1,
        f"el lock es POR conversacion, no global: hubo {maximo_visto[0]} a la vez")

# ── 3. el cupo por empresa ──────────────────────────────────────────────────
print("\n--- cupo por empresa ---")

TOPE = 3
vivos = []
pico = [0]


def turno_tenant(tenant, i, tope):
    clave = (tenant, "whatsapp", f"5730000{i:05d}")
    with api._turno_en_orden(tenant, clave, tope):
        with candado:
            vivos.append((tenant, i))
            de_este = sum(1 for t, _ in vivos if t == tenant)
            pico[0] = max(pico[0], de_este)
        time.sleep(0.12)
        with candado:
            vivos.remove((tenant, i))


correr([threading.Thread(target=turno_tenant, args=("empresa-a", i, TOPE))
        for i in range(9)])
afirmar(pico[0] <= TOPE,
        f"nunca mas de {TOPE} turnos simultaneos de esa empresa (pico: {pico[0]})")
afirmar(pico[0] == TOPE,
        f"y se usa el cupo entero, no menos (pico: {pico[0]})")

# ── 4. una empresa saturada no frena a la otra ──────────────────────────────
print("\n--- una empresa saturada NO frena a la otra ---")

pico[0] = 0
vivos.clear()
empezo_b = threading.Event()


def turno_b():
    clave = ("empresa-b", "whatsapp", "573000009999")
    with api._turno_en_orden("empresa-b", clave, 1):
        empezo_b.set()


hilos = [threading.Thread(target=turno_tenant, args=("empresa-a", i, 1))
         for i in range(6)]
hilos.append(threading.Thread(target=turno_b))
for h in hilos:
    h.start()
# B tiene su propio cupo: no espera a que A drene sus seis.
arranco = empezo_b.wait(timeout=0.3)
for h in hilos:
    h.join(timeout=20)
afirmar(arranco,
        "la empresa B arranco sin esperar a que A --saturada-- terminara")

# ── 5. no quedan locks colgados ─────────────────────────────────────────────
print("\n--- sin fugas ---")
afirmar(not api._locks_conversacion,
        f"el diccionario de locks quedo vacio (quedaron: {len(api._locks_conversacion)}); "
        f"sin esto crece un lock por cada conversacion que existio, para siempre")

# ── 6. sin tope configurado, nada cambia ────────────────────────────────────
print("\n--- sin tope, el comportamiento de siempre ---")
pico[0] = 0
vivos.clear()
correr([threading.Thread(target=turno_tenant, args=("empresa-c", i, None))
        for i in range(5)])
afirmar(pico[0] > 1,
        f"con max_turnos_simultaneos = None no hay cupo que espere "
        f"(pico: {pico[0]})")

print()
if FALLOS:
    print(f"[FALLA] {len(FALLOS)} comprobacion(es)")
    sys.exit(1)
print("[OK] Los turnos van en orden por conversacion y dentro del cupo de su empresa.")
