# -*- coding: utf-8 -*-
"""
================================================================================
 EL ANTI-REBOTE SOBREVIVE A UN REINICIO
================================================================================

Por que existe
--------------
Una conversacion que ya paso por un area no puede volver a ser derivada ahi.
Sin eso, soporte manda el caso a facturacion, facturacion se lo devuelve a
soporte, y el cliente no recibe una sola respuesta -- visto el 21/08/2026 con
un cliente suspendido que quedo girando entre las dos areas.

Ese freno vivia SOLO en memoria del proceso. Cualquier reinicio del motor lo
borraba, y no es hipotetico: el 07/09/2026 un despliegue a mitad de una
conversacion real dejo al asistente hablando de internet cuando el cliente
venia hablando de television. La misma clase de perdida se llevaba el
anti-rebote, sin que nada lo denunciara -- la conversacion simplemente
empezaba a rebotar de nuevo.

Ademas, hasta ahora NINGUNA prueba ejercitaba el anti-rebote: ni un test ni un
caso dorado mencionaban 'areas_visitadas' ni 'AREA_YA_INTERVINO'. Esta es la
primera.

Lo que se fija aca
------------------
1. Derivar marca las DOS areas: de donde sale y a donde va.
2. Derivar de vuelta a un area que ya intervino se rechaza con
   'AREA_YA_INTERVINO' -- fail-closed: el camino es escalar, no rebotar.
3. No se duplican areas, ni derivando dos veces ni al rehidratar.
4. Lo que se persiste es exactamente lo que declara
   Sesion.CAMPOS_ROUTING_PERSISTIBLES, y nada mas.
5. Despues de un reinicio (sesion nueva + lo que habia en la base) el bloqueo
   SIGUE en pie.
6. El estado de routing se restaura AUNQUE la conversacion no este verificada
   -- es el caso principal, porque el router deriva antes de que nadie
   verifique (PRD 8.9).
7. La lista rehidratada es una COPIA: dos sesiones no comparten el objeto.
8. Persiste por CONVERSACION, no por caso: una conversacion nueva arranca
   limpia (MASTER SPEC 3).
9. Las DOS puertas conviven en la misma columna sin pisarse, y cada una con
   su semantica: la identidad tecnica del cliente se REEMPLAZA, el routing se
   CONSERVA. Sale de una revision del propio cambio -- ver la seccion 9.

Se corre sin base y sin red: se ejercita la funcion real de derivacion sobre
una herramienta doble, y la persistencia se simula con el mismo diccionario
que la base devuelve en 'datos_sesion'.

    py -3.13 tests/test_anti_rebote_persistente.py
================================================================================
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.modelo.motor import _ejecutar_derivacion          # noqa: E402
from nucleo.seguridad.verificacion import (Sesion,             # noqa: E402
                                           rehidratar_routing,
                                           routing_a_persistir)

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    if condicion:
        print(f"  [OK]   {que}")
    else:
        print(f"  [FALLA] {que}")
        fallos.append(que)


class _HerramientaDoble:
    """Lo minimo que mira _ejecutar_derivacion: a que areas puede derivar."""
    def __init__(self, areas):
        self.areas_destino = list(areas)


def _sesion(**kw) -> Sesion:
    return Sesion(identificador_canal="573000000000", **kw)


# Estas dos NO reimplementan nada: llaman a las mismas funciones que llama
# nucleo/canales/api.py. Hasta el 26/09/2026 esta prueba copiaba los dos bucles
# --api.py los tenia inline y no se puede importar sin credenciales de base-- y
# por eso pasaba igual sin importar lo que api.py hiciera de verdad. Las
# funciones se mudaron a verificacion.py, que no importa nada del nucleo.
def _persistir(sesion: Sesion) -> dict:
    """Lo que nucleo/canales/api.py manda a guardar_estado_routing()."""
    return routing_a_persistir(sesion)


def _rehidratar(datos_sesion: dict) -> Sesion:
    """Un proceso NUEVO: sesion en blanco mas lo que habia en la base."""
    return rehidratar_routing(_sesion(), datos_sesion)


DERIVA = _HerramientaDoble(["facturacion_cliente", "soporte_tecnico_cliente"])

print("=" * 70)
print(" EL ANTI-REBOTE SOBREVIVE A UN REINICIO")
print("=" * 70)

# ---------------------------------------------------------------------- 1 --
print("\n[1] Derivar marca las dos areas: de donde sale y a donde va")
s = _sesion()
salida = _ejecutar_derivacion(DERIVA, s, {"area": "facturacion_cliente"},
                              "soporte_tecnico_cliente")
comprobar(salida.get("error") is None, "la primera derivacion no se rechaza")
comprobar(s.rol_siguiente == "facturacion_cliente",
          "queda anotado el rol al que sigue la conversacion")
comprobar(sorted(s.areas_visitadas) == ["facturacion_cliente", "soporte_tecnico_cliente"],
          "se marcan las DOS areas, no solo el destino")

# ---------------------------------------------------------------------- 2 --
print("\n[2] Devolverla al area que ya intervino se rechaza (fail-closed)")
vuelta = _ejecutar_derivacion(DERIVA, s, {"area": "soporte_tecnico_cliente"},
                              "facturacion_cliente")
comprobar(vuelta.get("error") == "AREA_YA_INTERVINO",
          "el rebote se rechaza con AREA_YA_INTERVINO")
comprobar("escalar" in (vuelta.get("instruccion_interna") or "").lower()
          or "persona" in (vuelta.get("instruccion_interna") or "").lower(),
          "la instruccion ofrece la salida correcta: resolver o pasar a una persona")

# ---------------------------------------------------------------------- 3 --
print("\n[3] No se duplican areas")
antes = list(s.areas_visitadas)
_ejecutar_derivacion(DERIVA, s, {"area": "facturacion_cliente"},
                     "soporte_tecnico_cliente")
comprobar(sorted(s.areas_visitadas) == sorted(antes),
          "derivar de nuevo a un area ya marcada no la agrega dos veces")
comprobar(len(s.areas_visitadas) == len(set(s.areas_visitadas)),
          "la lista no tiene repetidos")

# ---------------------------------------------------------------------- 4 --
print("\n[4] Se persiste exactamente lo declarado, y nada mas")
s.sn_onu = "HWTCAF721761"          # dato del cliente: NO es estado de routing
guardado = _persistir(s)
comprobar(set(guardado) == {"areas_visitadas"},
          "solo viaja 'areas_visitadas' -- no se cuela ningun dato del cliente")
comprobar(guardado["areas_visitadas"] == s.areas_visitadas,
          "viaja la lista tal cual")
comprobar(_persistir(_sesion()) == {},
          "una sesion sin derivaciones no escribe nada (no toca la fila)")

# ---------------------------------------------------------------------- 5 --
print("\n[5] Tras el reinicio, el bloqueo SIGUE en pie")
revivida = _rehidratar(guardado)
comprobar(sorted(revivida.areas_visitadas)
          == ["facturacion_cliente", "soporte_tecnico_cliente"],
          "el proceso nuevo arranca con las areas que ya habian intervenido")
tras_reinicio = _ejecutar_derivacion(DERIVA, revivida,
                                     {"area": "soporte_tecnico_cliente"},
                                     "facturacion_cliente")
comprobar(tras_reinicio.get("error") == "AREA_YA_INTERVINO",
          "el rebote se sigue rechazando despues del reinicio -- ESTE es el bug")

# ---------------------------------------------------------------------- 6 --
print("\n[6] Se restaura aunque la conversacion NO este verificada")
comprobar(revivida.verificado is False and revivida.id_cliente is None,
          "la sesion rehidratada no tiene identidad resuelta")
comprobar(revivida.areas_visitadas != [],
          "y aun asi conserva el anti-rebote -- es el caso principal, porque "
          "el router deriva antes de que nadie verifique")

# ---------------------------------------------------------------------- 7 --
print("\n[7] La lista rehidratada es una copia, no el objeto de la base")
otra = _rehidratar(guardado)
otra.areas_visitadas.append("ventas")
comprobar("ventas" not in guardado["areas_visitadas"],
          "mutar la sesion no altera lo que vino de la base")
comprobar("ventas" not in revivida.areas_visitadas,
          "ni contamina a otra sesion rehidratada de los mismos datos")

# ---------------------------------------------------------------------- 8 --
print("\n[8] Persiste por CONVERSACION: una nueva arranca limpia")
nueva_conversacion = _rehidratar({})      # otra conversacion: sin datos_sesion
comprobar(nueva_conversacion.areas_visitadas == [],
          "sin estado previo, el anti-rebote arranca vacio")
limpia = _ejecutar_derivacion(DERIVA, nueva_conversacion,
                              {"area": "soporte_tecnico_cliente"},
                              "facturacion_cliente")
comprobar(limpia.get("error") is None,
          "y el area que habia intervenido en la conversacion ANTERIOR puede "
          "volver a atender -- no persiste por caso (MASTER SPEC 3)")

# ---------------------------------------------------------------------- 9 --
print("\n[9] Las dos puertas conviven: identidad se REEMPLAZA, routing se CONSERVA")
# 'datos_sesion' lo escriben dos funciones distintas de db.py sobre la misma
# columna JSONB, fusionando con '||'. Fusionar era necesario --con reemplazo,
# la primera verificacion posterior a una derivacion borraba el anti-rebote--
# pero abre un riesgo simetrico: una clave OMITIDA ya no se borra, conserva el
# valor anterior.
#
# El caso real: se verifica al cliente A (que tiene sn_onu), y mas tarde, en la
# MISMA conversacion, una segunda verificacion resuelve al cliente B, que no lo
# tiene -- pasa con el ~32% de los activos. Si el payload omitiera los None, el
# serial de A quedaria pegado a la identidad de B, y las herramientas que
# identifican la ONU por ese serial diagnosticarian el equipo de otra persona
# sin que nada avise. Por eso api.py manda TODOS los campos de identidad,
# incluidos los None.
#
# 'jsonb || jsonb' es, para claves de primer nivel, {**viejo, **nuevo}.


def _payload_identidad(sesion):
    """Lo que api.py::atender_turno le pasa a identificar_cliente(): todos los
    campos de identidad, con None incluido."""
    return {c: getattr(sesion, c, None) for c in Sesion.CAMPOS_PERSISTIBLES}


def _fusion(previo, nuevo):
    return {**previo, **nuevo}


# Cliente A: verificado, con serial, y con una derivacion ya hecha.
a = _sesion()
a.areas_visitadas = ["soporte_tecnico_cliente", "facturacion_cliente"]
a.id_cliente, a.nombre = "6580", "CLIENTE A"
a.sn_onu, a.interfaz_lan = "HWTC-AAAA-1111", "ether2"
fila = _fusion({}, _persistir(a))                    # la puerta del routing
fila = _fusion(fila, _payload_identidad(a))          # la puerta de la identidad
comprobar(fila.get("sn_onu") == "HWTC-AAAA-1111" and fila.get("areas_visitadas"),
          "conviven en la misma fila: serial de A y sus areas visitadas")

# Segunda verificacion en la MISMA conversacion: cliente B, sin sn_onu.
a.id_cliente, a.nombre = "7777", "CLIENTE B"
a.sn_onu, a.interfaz_lan = None, None
fila = _fusion(fila, _payload_identidad(a))

comprobar(fila.get("sn_onu") is None,
          "el serial del cliente A NO sobrevive al cambio de identidad")
comprobar(fila.get("interfaz_lan") is None,
          "tampoco la interfaz de A")
comprobar(fila.get("areas_visitadas") == ["soporte_tecnico_cliente",
                                          "facturacion_cliente"],
          "y el anti-rebote queda INTACTO -- es de la conversacion, no del cliente")

# Y al rehidratar, ni el serial nulo se restaura ni el routing se pierde.
revivida_b = _sesion()
for campo, valor in fila.items():
    if campo in Sesion.CAMPOS_PERSISTIBLES and valor:
        setattr(revivida_b, campo, valor)
rehidratar_routing(revivida_b, fila)
comprobar(revivida_b.sn_onu is None,
          "tras el reinicio la sesion NO arranca con el serial de otro cliente")
comprobar(len(revivida_b.areas_visitadas) == 2,
          "y si arranca con el anti-rebote completo")

# =============================================================================
#  Y LA VUELTA EXTRA ANTES DE ESCALAR TAMBIEN SOBREVIVE (26/09/2026)
# =============================================================================
#
# Vivia solo en memoria del proceso. Con --workers 1 y autodeploy, cada
# despliegue vaciaba esa memoria y le regalaba una posposicion mas a cada
# conversacion en curso -- al cliente le llega como una espera que ya habia
# pasado. Se persiste por la misma puerta que el anti-rebote, y por eso hacen
# falta dos afirmaciones: que viaja, y que un bool no rompe una hidratacion
# que antes asumia que todo lo persistido era una lista.
print()
print("--- la vuelta antes de escalar sobrevive al reinicio ---")

s_v = _sesion()
comprobar(_persistir(s_v) == {},
          "una sesion sin nada no escribe nada (el turno normal no paga escritura)")

s_v.intento_antes_de_escalar = True
guardado_v = _persistir(s_v)
comprobar(guardado_v.get("intento_antes_de_escalar") is True,
          "consumida la vuelta, viaja a la base")
comprobar(_rehidratar(guardado_v).intento_antes_de_escalar is True,
          "y un proceso NUEVO arranca sabiendo que ya se pospuso una vez")

# El bool y la lista conviven: esto es lo que el list(valor) de antes rompia.
s_v2 = _sesion()
s_v2.areas_visitadas.extend(["facturacion", "soporte_tecnico_cliente"])
s_v2.intento_antes_de_escalar = True
revivida_v = _rehidratar(_persistir(s_v2))
comprobar(revivida_v.intento_antes_de_escalar is True
          and revivida_v.areas_visitadas == ["facturacion", "soporte_tecnico_cliente"],
          "el bool y la lista sobreviven juntos: la hidratacion dejo de asumir listas")
comprobar(revivida_v.areas_visitadas is not s_v2.areas_visitadas,
          "y la lista sigue siendo una COPIA, no el mismo objeto")

# Sin consumir la vuelta no se escribe la clave: False no es un dato que valga
# guardar, y asi el turno que no pospone no toca la base.
s_v3 = _sesion()
s_v3.areas_visitadas.append("ventas")
comprobar("intento_antes_de_escalar" not in _persistir(s_v3),
          "sin posponer, la clave no se escribe")
comprobar(_rehidratar({"areas_visitadas": ["ventas"]}).intento_antes_de_escalar is False,
          "y una fila vieja sin la clave rehidrata en False, no revienta")

# Y LA PUERTA DEL ROUTING NO ES UNA PUERTA DE IDENTIDAD. Esto no es conducta,
# es seguridad: 'datos_sesion' es una columna de la base, y rehidratar recorre
# lo que venga en ella. Si un dia trajera 'id_cliente', 'sn_onu' o 'verificado'
# --por una escritura vieja, por otra puerta, o por un error-- no puede fijarlos:
# la identidad se verifica en el turno, no se restaura de una fila. Hoy se
# cumple porque CAMPOS_ROUTING_PERSISTIBLES no los incluye; queda afirmado para
# que siga cumpliendose cuando alguien agregue el campo siguiente.
intruso = _rehidratar({"id_cliente": "999", "sn_onu": "ABC123",
                       "interfaz_lan": "eth0", "verificado": True, "nivel": 9,
                       "areas_visitadas": ["ventas"]})
comprobar(intruso.id_cliente is None and intruso.sn_onu is None
          and intruso.interfaz_lan is None,
          "una fila con identidad NO la restaura por la puerta del routing")
comprobar(intruso.verificado is False and intruso.nivel == 0,
          "ni deja a la sesion verificada: eso se gana en el turno, no se lee")
comprobar(intruso.areas_visitadas == ["ventas"],
          "y lo que si esta declarado entra igual")


print("\n" + "=" * 70)
if fallos:
    print(f" {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    raise SystemExit(1)
print(" Todo en orden: el anti-rebote sobrevive al reinicio, sigue por")
print(" conversacion, y no arrastra la identidad tecnica de otro cliente.")
print("=" * 70)
