# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA -- la escalada que NO decide el modelo
================================================================================

    py -3.13 tests/test_escalada_forzada.py

POR QUE EXISTE, Y POR QUE NO ES UN CASO DORADO
----------------------------------------------
El corredor de casos dorados llama a `motor.responder()` un turno a la vez, y
la escalada vive en `api.py::chat()`. Cero menciones de escalamiento en
`cli/evaluar.py` -- o sea que NINGUN caso dorado puede afirmar "y termino en
un ticket".

Ese hueco dejo pasar un bug real (25/08/2026): el flujo de cambio de WiFi
recogia el pedido del cliente, lo validaba, lo confirmaba... y moria en la
conversacion. Medido sobre 12 conversaciones: las 12 con escalada=False y sin
ticket, mientras el asistente le decia al cliente que "un colaborador humano
lo aplica". Los 5 casos dorados de WiFi estaban en verde todo ese tiempo,
afirmando cosas que eran ciertas.

Un conjunto de pruebas que no puede detectar el fallo que mas importa es el
que peor engaña, porque da confianza. Esto lo cubre, y sin llamar al modelo:
la decision es deterministica -- depende de la traza y de la config, nada mas.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.seguimiento.forzado import (con_las_manos_vacias,
                                        escalada_forzada,
                                        motivos_por_hecho,
                                        CODIGOS_CONDICION_DE_NEGOCIO,
                                        CODIGOS_MOTOR_GUARD)  # noqa: E402
from nucleo.config.schema import Herramienta  # noqa: E402

_fallas = []


def afirmar(condicion, que):
    print(("  [ok]   " if condicion else "  [FALLA] ") + que)
    if not condicion:
        _fallas.append(que)


class ConfigFalsa:
    """Lo unico que mira la funcion es el catalogo de herramientas."""

    def __init__(self, herramientas):
        self.herramientas = herramientas


def herr(nombre, **kw):
    return Herramienta(nombre=nombre, tipo="interno",
                       roles_permitidos=["soporte"], **kw)


PEDIDO = herr("registrar_pedido", escalar_al_completar="pedido_para_ejecutar")
FRAGIL = herr("consultar_algo", escalar_si_falla="sin_datos_para_diagnosticar")
COMUN = herr("consultar_otra_cosa")
CFG = ConfigFalsa([PEDIDO, FRAGIL, COMUN])

print("=" * 70)
print(" ESCALADA FORZADA POR UNA HERRAMIENTA")
print("=" * 70)

print("\nel exito de una herramienta puede exigir una persona")
motivo, _ = escalada_forzada(CFG, [{"herramienta": "registrar_pedido"}])
afirmar(motivo == "pedido_para_ejecutar",
        "una herramienta con 'escalar_al_completar' que sale bien fuerza la escalada")

motivo, _ = escalada_forzada(CFG, [{"herramienta": "consultar_otra_cosa"}])
afirmar(motivo is None,
        "una que NO lo declara y sale bien no escala")

print("\nel fallo sigue funcionando como antes")
motivo, _ = escalada_forzada(CFG, [{"herramienta": "consultar_algo",
                                    "codigo_error": "HTTP_500"}])
afirmar(motivo == "sin_datos_para_diagnosticar",
        "una herramienta con 'escalar_si_falla' que falla fuerza la escalada")

motivo, _ = escalada_forzada(CFG, [{"herramienta": "consultar_algo"}])
afirmar(motivo is None,
        "esa MISMA herramienta, cuando sale bien, no escala")

# El caso al reves importa: una herramienta que declara 'escalar_al_completar'
# y FALLA no cumplio su proposito -- no hay ningun pedido tomado que entregar.
motivo, _ = escalada_forzada(CFG, [{"herramienta": "registrar_pedido",
                                    "codigo_error": "HTTP_500"}])
afirmar(motivo is None,
        "una con 'escalar_al_completar' que FALLA no escala: no tomo ningun pedido")

print("\nnada raro rompe la decision")
afirmar(escalada_forzada(CFG, [])[0] is None, "una traza vacia no escala")
afirmar(escalada_forzada(CFG, None)[0] is None, "una traza None no explota")
afirmar(escalada_forzada(CFG, [{"herramienta": "no_existe"}])[0] is None,
        "una herramienta que no esta en el catalogo se ignora")

print("\nprioridad dentro de una misma traza")
motivo, _ = escalada_forzada(CFG, [{"herramienta": "consultar_otra_cosa"},
                                   {"herramienta": "registrar_pedido"}])
afirmar(motivo == "pedido_para_ejecutar",
        "se mira toda la traza, no solo la primera llamada")

print()
print("el motivo por hecho no entra en el menu del evaluador")
# El evaluador lee la conversacion y elige un motivo de una lista. Un motivo
# que significa "una herramienta ya registro el pedido" no se puede juzgar
# leyendo: si esta en la lista, lo elige apenas la conversacion SUENA a un
# pedido -- y como la escalada reemplaza la respuesta, corta el turno en el
# que el asistente estaba pidiendo la confirmacion. Visto el 28/08/2026.
afirmar(motivos_por_hecho(CFG) == {"pedido_para_ejecutar"},
        "se reconoce cual motivo lo decide un hecho y no un juicio")
afirmar("sin_datos_para_diagnosticar" not in motivos_por_hecho(CFG),
        "'escalar_si_falla' NO cuenta: un fallo si se puede juzgar leyendo")
afirmar(motivos_por_hecho(ConfigFalsa([])) == set(),
        "un tenant sin herramientas no deja al evaluador sin motivos")

print()
print("no se escala sin haber intentado nada")
# El modelo puede decidir escalar en el primer mensaje. Si no corrio ni una
# herramienta, el caso llega a la bandeja con la traza vacia: sin identidad,
# sin pedido y sin ticket. Paso dos veces el 28/08/2026, la segunda DESPUES de
# pedirselo por prompt -- por eso esto es codigo.
afirmar(con_las_manos_vacias([]),
        "una conversacion sin nada ejecutado esta con las manos vacias")
afirmar(con_las_manos_vacias([{"role": "user", "content": "hola"},
                              {"role": "assistant", "content": "hola"}]),
        "hablar no es hacer: solo mensajes sigue siendo manos vacias")
afirmar(not con_las_manos_vacias([{"role": "user", "content": "hola"},
                                  {"role": "tool", "name": "consultar_algo",
                                   "content": "{}"}]),
        "con una herramienta ejecutada, ya no")
afirmar(not con_las_manos_vacias([{"role": "tool", "name": "x", "content": ""}]),
        "cuenta la llamada aunque haya devuelto vacio: se intento igual")
afirmar(con_las_manos_vacias(None),
        "un historial None no explota")

print()
print("=" * 70)
print(" GUARDIAS DEL MOTOR -- no son la herramienta fallando")
print("=" * 70)
# Fase #2, paso 2. Encontrado en la auditoria (02/09/2026): 'reiniciar_ont'
# declara 'escalar_si_falla' Y 'exige_previas' a la vez, y el modelo SI
# intenta llamarla antes de tiempo en la practica (motor.py lo documenta:
# "un texto en el prompt no alcanzo"). Sin este filtro, esa guardia --el
# motor funcionando exactamente como debe-- forzaba una escalada.

print("\n[1] error real HTTP_500 + escalar_si_falla -> mantiene el escalamiento")
motivo, _ = escalada_forzada(CFG, [{"herramienta": "consultar_algo",
                                    "codigo_error": "HTTP_500"}])
afirmar(motivo == "sin_datos_para_diagnosticar",
        "un codigo_error que NO es guardia del motor sigue forzando la escalada")

print("\n[2-6] las cinco guardias del motor -- ninguna escala")
FRAGIL_NOMBRE = "consultar_algo"
for codigo in sorted(CODIGOS_MOTOR_GUARD):
    motivo, _ = escalada_forzada(CFG, [{"herramienta": FRAGIL_NOMBRE,
                                        "codigo_error": codigo}])
    afirmar(motivo is None,
            f"'{codigo}' en una herramienta con escalar_si_falla NO escala")
afirmar(CODIGOS_MOTOR_GUARD == {"PRECONDICION_NO_CUMPLIDA", "LIMITE_DE_CONVERSACION",
                                "FALTA_HABLAR_CON_EL_CLIENTE", "IDENTIDAD_NO_RESUELTA",
                                "HERRAMIENTA_DESCONOCIDA"},
        "la clasificacion tiene exactamente los 5 codigos de la auditoria -- "
        "ni uno de mas, ni uno de menos")

print("\n[7] EL CASO CRITICO -- bloqueo prematuro y despues exito, en la MISMA traza")
# Reproduce 'reiniciar_ont' de verdad: mismo nombre, mismo 'escalar_si_falla'
# ('sin_datos_para_diagnosticar', ver tenants/rapilink.config.yaml), para que
# esta prueba sea al mismo tiempo la regresion del caso real y no solo un
# ejemplo generico.
REINICIAR_ONT = herr("reiniciar_ont", solo_lectura=False, requiere_confirmacion=True,
                     escalar_si_falla="sin_datos_para_diagnosticar")
CFG_REINICIO = ConfigFalsa([REINICIAR_ONT])

motivo, _ = escalada_forzada(CFG_REINICIO, [
    {"herramienta": "reiniciar_ont", "codigo_error": "PRECONDICION_NO_CUMPLIDA"},
    {"herramienta": "reiniciar_ont"},
])
afirmar(motivo is None,
        "el intento prematuro (rechazado por la precondicion, correctamente) "
        "NO escala cuando el MISMO turno reintento y reinicio de verdad -- "
        "el bug que motivo la auditoria de Fase #2")

# El orden inverso tiene que dar lo mismo: la guardia no es un fallo, asi que
# no importa si aparece antes o despues del exito en la traza.
motivo, _ = escalada_forzada(CFG_REINICIO, [
    {"herramienta": "reiniciar_ont"},
    {"herramienta": "reiniciar_ont", "codigo_error": "PRECONDICION_NO_CUMPLIDA"},
])
afirmar(motivo is None,
        "y tampoco importa el orden: un exito seguido de la guardia sigue sin escalar")

# Si el rechazo es la UNICA entrada del turno (el modelo lo intento, la
# precondicion lo freno, y no volvio a intentarlo) -- sigue sin escalar. Es
# 'FALTA_HABLAR_CON_EL_CLIENTE' y 'LIMITE_DE_CONVERSACION' en la practica: no
# hay reintento posible dentro del mismo turno.
motivo, _ = escalada_forzada(CFG_REINICIO, [
    {"herramienta": "reiniciar_ont", "codigo_error": "PRECONDICION_NO_CUMPLIDA"},
])
afirmar(motivo is None,
        "y aunque no haya un segundo intento en el turno, la guardia sola "
        "tampoco escala -- nunca fue un fallo de la herramienta")

# Contraprueba: SIN el filtro esto habria dado 'sin_datos_para_diagnosticar'.
# Se deja explicito para que quede claro que esta prueba SI distingue algo,
# no que 'motivo is None' salga por cualquier otro motivo.
afirmar("PRECONDICION_NO_CUMPLIDA" in CODIGOS_MOTOR_GUARD,
        "la razon de que no escale es la clasificacion, no una casualidad")

print("\n[8] codigo_error real, pero la herramienta NO declara escalar_si_falla")
motivo, _ = escalada_forzada(CFG, [{"herramienta": "consultar_otra_cosa",
                                    "codigo_error": "ConnectionError: fallo la red"}])
afirmar(motivo is None,
        "sin escalar_si_falla declarado, ni un error real fuerza nada -- "
        "comportamiento de siempre, sin cambios")

print("\n[9] resultado negativo de negocio, SIN codigo_error -> no escala")
# '0 de 3', 'Offline', 'Disabled': la herramienta corrio bien y el DATO es
# negativo. Eso no es un error de ejecucion -- 'codigo_error' queda vacio, y
# la traza no distingue "salio 0 de 3" de "salio 3 de 3": ambas son exito
# desde el punto de vista de la herramienta.
motivo, _ = escalada_forzada(CFG, [{"herramienta": "consultar_algo",
                                    "resultado": "0 de 3"}])
afirmar(motivo is None,
        "un resultado negativo valido, sin codigo_error, no activa "
        "escalar_si_falla -- la herramienta funciono")

print()
print("=" * 70)
print(" FASE #2 PASO 3 -- 'ping_cliente' activada, y SOLO ella")
print("=" * 70)
# Contra la config REAL del tenant, no un doble -- es la unica forma de
# probar que lo que se activo es lo de PRODUCCION y no una recreacion
# parecida. cargar_config valida el YAML solo (sin red, sin base, sin
# modelo), mismo patron que ya usan test_solicitud_explicita.py y
# test_motivos_por_rol.py.
from nucleo.config.schema import cargar_config                     # noqa: E402

CFG_REAL = cargar_config("tenants/rapilink.config.yaml")
PING = next(h for h in CFG_REAL.herramientas if h.nombre == "ping_cliente")

print("\n[A] error REAL de ejecucion -> escala")
for codigo in ("ConnectionError: HTTPSConnectionPool(...)",
              "ReadTimeout: HTTPSConnectionPool(...)",
              "HTTPError: 500 Server Error"):
    motivo, por_que = escalada_forzada(CFG_REAL, [
        {"herramienta": "ping_cliente", "codigo_error": codigo}])
    afirmar(motivo == "sin_datos_para_diagnosticar",
            f"'{codigo.split(':')[0]}' en ping_cliente fuerza la escalada")
    afirmar("ping_cliente" in por_que, "y el motivo nombra la herramienta")

print("\n[B] resultado negativo VALIDO ('0 de 3', sin codigo_error) -> NO escala")
motivo, _ = escalada_forzada(CFG_REAL, [
    {"herramienta": "ping_cliente", "resultado": {"ping-exitoso": "0 de 3"}}])
afirmar(motivo is None,
        "'0 de 3' es un dato negativo, no un fallo -- la llamada funciono, "
        "sigue siendo el modelo quien lo lee (PRD 12.5)")

print("\n[C] guardias del motor en ping_cliente -> ninguna escala")
for codigo in ("PRECONDICION_NO_CUMPLIDA", "LIMITE_DE_CONVERSACION",
              "FALTA_HABLAR_CON_EL_CLIENTE", "IDENTIDAD_NO_RESUELTA"):
    motivo, _ = escalada_forzada(CFG_REAL, [
        {"herramienta": "ping_cliente", "codigo_error": codigo}])
    afirmar(motivo is None, f"'{codigo}' en ping_cliente NO escala")

print("\n[D] exito ('3 de 3', sin codigo_error) -> NO escala")
motivo, _ = escalada_forzada(CFG_REAL, [
    {"herramienta": "ping_cliente", "resultado": {"ping-exitoso": "3 de 3"}}])
afirmar(motivo is None, "un ping exitoso no activa nada")

print("\n[E] caso mixto -- prematuro y despues exitoso, en la MISMA traza")
motivo, _ = escalada_forzada(CFG_REAL, [
    {"herramienta": "ping_cliente", "codigo_error": "PRECONDICION_NO_CUMPLIDA"},
    {"herramienta": "ping_cliente"},
])
afirmar(motivo is None,
        "el bloqueo del motor no contamina un reintento exitoso en el mismo turno")

print("\n[F] otra herramienta sin escalar_si_falla, con error real -> sigue sin escalar")
motivo, _ = escalada_forzada(CFG_REAL, [
    {"herramienta": "consultar_mi_servicio", "codigo_error": "ConnectionError: ..."}])
afirmar(motivo is None,
        "consultar_mi_servicio no fue activada en este paso -- un error real "
        "suyo no fuerza nada, comportamiento sin cambios")

print("\n[G] solo se activo lo que se pidio, ni una herramienta de mas")
con_escalar_si_falla = {h.nombre for h in CFG_REAL.herramientas if h.escalar_si_falla}
afirmar(con_escalar_si_falla == {"ping_cliente", "reiniciar_ont", "consultar_estado_catv"},
        f"exactamente estas tres tienen escalar_si_falla, ni una mas: "
        f"{sorted(con_escalar_si_falla)}")
NO_ACTIVAR = ("consultar_senal_ont", "consultar_estado_ont", "cambiar_tipo_onu",
             "activar_catv", "verificar_identidad_por_cedula",
             "consultar_mi_servicio", "registrar_solicitud_servicio",
             "consultar_incidente_red")
por_nombre_real = {h.nombre: h for h in CFG_REAL.herramientas}
for nombre in NO_ACTIVAR:
    afirmar(not por_nombre_real[nombre].escalar_si_falla,
            f"'{nombre}' sigue SIN escalar_si_falla -- no era parte de este paso")
afirmar(PING.escalar_si_falla == "sin_datos_para_diagnosticar",
        "y ping_cliente quedo con el motivo exacto pedido")
# Nada mas de ping_cliente se toco: sigue siendo asincrona, con los mismos
# argumentos fijos y la misma inyeccion de sesion que antes de este paso.
afirmar(PING.asincrona is True and PING.argumentos_fijos == {"pings": 3, "arp_ping": False}
        and PING.inyectar_sesion == {"id_servicio": "id_cliente"},
        "el resto de la declaracion de ping_cliente quedo intacto")

print()
print("=" * 70)
print(" FASE #5.1 -- fallo real superado por un exito posterior de la MISMA herramienta")
print("=" * 70)
# Auditoria de Fase #5 (03/09/2026): 'reiniciar_ont' puede fallar con un
# error REAL (no una guardia del motor) sin gastar su limite_por_conversacion
# -- motor.py::_veces_ejecutada() no cuenta un intento que termino en error.
# Eso deja abierta la puerta a un reintento real, en el MISMO turno, que esta
# vez funciona. Reproducido antes de corregir: escalada_forzada() encontraba
# el ConnectionError y escalaba, sin mirar que la MISMA herramienta, mas
# abajo en la MISMA traza, ya habia reiniciado el equipo de verdad.

print("\n[CASO A] fallo real + exito posterior, MISMA herramienta -> NO escala")
traza_superada = [
    {"herramienta": "reiniciar_ont",
     "codigo_error": "ConnectionError: HTTPSConnectionPool(...): Max retries exceeded"},
    {"herramienta": "reiniciar_ont", "codigo_error": None,
     "verificacion_pendiente": {"espera_segundos": 120, "max_intentos": 3}},
]
copia_para_comparar = [dict(x) for x in traza_superada]
motivo, _ = escalada_forzada(CFG_REAL, traza_superada)
afirmar(motivo is None,
        "el ConnectionError del primer intento queda superado por el exito "
        "real del segundo, en la misma traza -- ya no escala")
afirmar(traza_superada == copia_para_comparar,
        "escalada_forzada() no toca la traza: la ejecucion exitosa (con su "
        "'verificacion_pendiente') sigue intacta para quien la use despues -- "
        "esta funcion solo LEE, nunca filtra ni descarta entradas")

print("\n[CASO B] MOTOR_GUARD + exito posterior -> sigue sin escalar (ya cubierto arriba en [7]/[E])")
motivo, _ = escalada_forzada(CFG_REAL, [
    {"herramienta": "reiniciar_ont", "codigo_error": "PRECONDICION_NO_CUMPLIDA"},
    {"herramienta": "reiniciar_ont", "codigo_error": None}])
afirmar(motivo is None,
        "la correccion de Fase #5.1 no toco el filtro de MOTOR_GUARD: sigue sin escalar")

print("\n[CASO C] fallo real SIN exito posterior -> mantiene el escalamiento")
motivo, por_que = escalada_forzada(CFG_REAL, [
    {"herramienta": "reiniciar_ont",
     "codigo_error": "ConnectionError: HTTPSConnectionPool(...): Max retries exceeded"}])
afirmar(motivo == "sin_datos_para_diagnosticar",
        "sin un reintento exitoso despues, el fallo real sigue forzando la "
        "escalada -- la correccion NO perdona un fallo que quedo sin resolver")
afirmar("reiniciar_ont" in por_que, "y el motivo sigue nombrando la herramienta")

print("\n[CASO D] fallo herramienta A + exito herramienta B (DISTINTAS) -> semantica sin cambios")
motivo, _ = escalada_forzada(CFG_REAL, [
    {"herramienta": "reiniciar_ont",
     "codigo_error": "ConnectionError: HTTPSConnectionPool(...): Max retries exceeded"},
    {"herramienta": "ping_cliente", "codigo_error": None,
     "resultado": {"ping-exitoso": "3 de 3"}},
])
afirmar(motivo == "sin_datos_para_diagnosticar",
        "el exito de 'ping_cliente' NO 'perdona' el fallo real de "
        "'reiniciar_ont' -- son herramientas distintas, la regla nueva solo "
        "aplica cuando es la MISMA herramienta")

print("\n[CASO E] consultar_incidente_red expone 'motivo' al rol de cara al cliente")
campos_cliente = CFG_REAL.roles["soporte_tecnico_cliente"].campos_permitidos[
    "consultar_incidente_red"]
afirmar("motivo" in campos_cliente,
        "'soporte_tecnico_cliente' ahora SI puede distinguir 'no se pudo "
        "comprobar' de 'confirmado sin incidente'")
afirmar(set(campos_cliente) == {"es_incidente_de_red", "desde_por_tiempos", "motivo"},
        f"y los campos que ya tenia siguen ahi -- solo se agrego uno: {sorted(campos_cliente)}")
campos_soporte = CFG_REAL.roles["soporte"].campos_permitidos["consultar_incidente_red"]
afirmar(set(campos_soporte) == {"es_incidente_de_red", "tipo_alerta", "clientes_afectados",
                                "porcentaje_afectado", "desde", "zona", "caja", "motivo",
                                "clientes_caidos_a_la_vez", "desde_por_tiempos"},
        "y el rol 'soporte' (que ya tenia 'motivo') no cambio en nada")

print()
print("=" * 70)
print(" FASE #6.1 -- registrar_pedido_wifi: PEDIDO_INVALIDO no escala")
print("=" * 70)
# Reproduce y corrige el defecto de la auditoria de Fase #6/#6.1
# (03/09/2026): un pedido de WiFi invalido (SSID/clave que wifi.py
# rechaza) llegaba a escalar igual que uno valido, porque
# 'registrar_pedido_wifi' nunca lanza una excepcion y 'escalar_al_completar'
# solo mira si hubo codigo_error. La correccion vive en dos archivos:
# motor.py::_codigo_error_de_pedido_wifi() le asigna 'PEDIDO_INVALIDO'
# cuando corresponde, y este archivo prueba que, con ese codigo puesto,
# escalada_forzada() ya NO escala.

print("\n[CASO 1] pedido VALIDO -- comportamiento SIN CAMBIOS: sigue escalando")
motivo, por_que = escalada_forzada(CFG_REAL, [
    {"herramienta": "registrar_pedido_wifi", "codigo_error": None}])
afirmar(motivo == "pedido_para_ejecutar",
        "un pedido valido (codigo_error=None, igual que antes de esta fase) sigue "
        "forzando la escalada -- el flujo que ya funcionaba no se toco")

print("\n[CASO 2] pedido INVALIDO por CONTRASEÑA -- NO escala")
motivo, _ = escalada_forzada(CFG_REAL, [
    {"herramienta": "registrar_pedido_wifi", "codigo_error": "PEDIDO_INVALIDO"}])
afirmar(motivo is None,
        "con PEDIDO_INVALIDO (el codigo que motor.py asigna cuando la clave no "
        "cumple las reglas), escalada_forzada() ya NO escala")

print("\n[CASO 3] pedido INVALIDO por SSID -- mismo codigo, mismo resultado")
# El codigo no distingue SSID de clave (wifi.py ya junta ambos problemas en
# 'problemas'), asi que la traza es identica -- lo que importa es que
# PEDIDO_INVALIDO se comporte igual sin importar CUAL regla violo el pedido.
motivo, _ = escalada_forzada(CFG_REAL, [
    {"herramienta": "registrar_pedido_wifi", "codigo_error": "PEDIDO_INVALIDO"}])
afirmar(motivo is None, "un SSID invalido tampoco escala -- mismo codigo, mismo freno")

print("\n[CASO 4] pedido con VARIOS problemas a la vez -- sigue siendo un solo freno")
motivo, _ = escalada_forzada(CFG_REAL, [
    {"herramienta": "registrar_pedido_wifi", "codigo_error": "PEDIDO_INVALIDO",
     "resumen": ""}])
afirmar(motivo is None,
        "nombre Y clave invalidos a la vez siguen resolviendo a UN solo "
        "PEDIDO_INVALIDO, y ese solo ya alcanza para no escalar")

print("\n[CASO 5] pedido INVALIDO -- el mensaje de 'quedo registrado' nunca se busca")
# api.py solo entra a buscar 'mensajes_por_motivo[motivo]' cuando 'forzado'
# (el motivo que devuelve escalada_forzada) no es None -- ver
# nucleo/canales/api.py:1061 ('if forzado:'). Con motivo=None no hay 'motivo'
# con que indexar el diccionario, asi que el texto fijo de
# 'pedido_para_ejecutar' ("Listo, tu pedido quedo registrado...") no puede
# llegar a reemplazar la respuesta del modelo.
motivo_invalido, _ = escalada_forzada(CFG_REAL, [
    {"herramienta": "registrar_pedido_wifi", "codigo_error": "PEDIDO_INVALIDO"}])
afirmar(motivo_invalido is None,
        "sin motivo, api.py nunca entra a la rama que reemplaza la respuesta con "
        "el mensaje fijo -- lo que el modelo redacte (mostrando 'problemas') es "
        "lo que de verdad le llega al cliente")

print("\n[CASO 6] pedido VALIDO -- conserva el mensaje real, sin cambios")
motivo_valido, _ = escalada_forzada(CFG_REAL, [
    {"herramienta": "registrar_pedido_wifi", "codigo_error": None}])
mensaje = CFG_REAL.escalamiento.mensajes_por_motivo.get(motivo_valido)
afirmar(motivo_valido == "pedido_para_ejecutar" and mensaje
        and "quedó registrado" in mensaje,
        "un pedido valido SI produce el motivo, y el mensaje fijo de "
        "'pedido_para_ejecutar' sigue siendo exactamente el mismo que antes")

print("\n[CASO 7] idempotencia -- nada de esto se toco")
# escalada_forzada() es una funcion pura: no crea casos, no escribe en la
# base, no toca 'estado[\"ya_escalada\"]' (eso vive en api.py, sin cambios
# en esta fase). Que PEDIDO_INVALIDO no escale significa, ademas, que un
# pedido invalido NUNCA llega a intentar crear un caso -- no hay nada que
# deduplicar porque no se crea nada. Se confirma aca que el mecanismo
# CODIGOS_MOTOR_GUARD -- que SI es la base de la que la idempotencia entre
# turnos ya dependia (Fase #2/#5) -- sigue exactamente igual:
afirmar(CODIGOS_MOTOR_GUARD == {"PRECONDICION_NO_CUMPLIDA", "LIMITE_DE_CONVERSACION",
                                "FALTA_HABLAR_CON_EL_CLIENTE", "IDENTIDAD_NO_RESUELTA",
                                "HERRAMIENTA_DESCONOCIDA"},
        "CODIGOS_MOTOR_GUARD sigue teniendo exactamente los mismos 5 codigos de "
        "siempre -- PEDIDO_INVALIDO NO se mezclo ahi adentro")
afirmar(CODIGOS_CONDICION_DE_NEGOCIO == {"PEDIDO_INVALIDO"},
        "PEDIDO_INVALIDO vive en su propio conjunto, separado de las guardias del motor")

print("\n[extra] PEDIDO_INVALIDO tambien respeta CASO 8 de Fase #5.1: si despues, "
      "en la MISMA traza, el pedido se corrige y sale valido, ESE gana")
motivo, _ = escalada_forzada(CFG_REAL, [
    {"herramienta": "registrar_pedido_wifi", "codigo_error": "PEDIDO_INVALIDO"},
    {"herramienta": "registrar_pedido_wifi", "codigo_error": None},
])
afirmar(motivo == "pedido_para_ejecutar",
        "un primer intento invalido seguido de uno corregido y valido, en el "
        "mismo turno, SI escala -- el freno es solo para el intento que sigue "
        "siendo invalido, no para la conversacion entera")

print("\n" + "=" * 70)
if _fallas:
    print(f" {len(_fallas)} falla(s):")
    for f in _fallas:
        print("   - " + f)
    sys.exit(1)
print(" Todo en orden: lo que obliga a escalar no depende del modelo.")
print("=" * 70)
