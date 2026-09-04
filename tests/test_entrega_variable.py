# -*- coding: utf-8 -*-
"""
================================================================================
 GUARDA DE 'entrega_variable'  --  el link no existe si no quedo el registro
================================================================================

Por que existe
--------------
El rol de ventas tenia la URL del formulario de contratacion metida en su
prompt. El modelo la repartia cuando le parecia, y la solicitud no quedaba
anotada en ningun lado: quien no llenaba el formulario -la mayoria- no habia
existido nunca y nadie podia llamarlo. Tampoco se podia responder una pregunta
basica del negocio: cuantos llegan al link contra cuantos lo completan.

Pedirselo al prompt ("registra antes de dar el link") no alcanza. El prompt es
guia, nunca la garantia (PRD 7.4): un modelo que se saltea el paso no deja
ninguna senal, y el fallo se ve recien cuando alguien pregunta por que la lista
de prospectos esta vacia.

La solucion es sacarle el dato al modelo. La URL ya no esta en el prompt: la
DEVUELVE la herramienta que registra la solicitud, y solo si no fallo. El
modelo no puede dar un link que no tiene.

Lo que se fija aca
------------------
1. Si la herramienta sale bien, el valor de la variable llega al modelo.
2. Si la herramienta FALLA, no llega -- ese es el punto entero.
3. Si devuelve un error de negocio (dict con 'error' con contenido), tampoco.
4. Pero {'error': False} es EXITO, no fallo: BottleCRM responde asi cuando todo
   salio bien. Mirar si la clave existe -en vez de su valor- daba "fallo"
   siempre, y el link no se habria entregado nunca. Se rompio asi la primera
   vez que se escribio; por eso tiene caso propio.
5. Una herramienta sin 'entrega_variable' no recibe nada de mas.
6. La config NO valida si la variable no existe en 'variables_tenant': eso
   fallaria en silencio en produccion -- la herramienta se ejecuta, el registro
   queda, y el modelo se queda sin el dato que no puede sacar de ningun lado.

Se corre sin base, sin red y sin modelo: se prueba la regla de decision y el
validador de config, que es donde vive la garantia.

    py -3.13 tests/test_entrega_variable.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.config.schema import TenantConfig, cargar_config    # noqa: E402

fallos: list[str] = []


def comprobar(condicion: bool, que: str) -> None:
    if condicion:
        print(f"  [OK]   {que}")
    else:
        print(f"  [FALLA] {que}")
        fallos.append(que)


# La MISMA condicion que aplica nucleo/modelo/motor.py. Se replica aca en vez
# de invocar el turno entero (que necesitaria base y modelo): lo que se esta
# fijando es la regla de decision, no el andamiaje alrededor.
def entrega(salida, codigo_error, variable="LINK", variables={"LINK": "https://x/y"}):
    if (variable and codigo_error is None
            and not (isinstance(salida, dict) and salida.get("error"))):
        valor = (variables or {}).get(variable)
        if valor and isinstance(salida, dict):
            return dict(salida, **{variable: valor})
    return salida


print("=" * 70)
print(" GUARDA DE entrega_variable")
print("=" * 70)

print("\n[1] Herramienta que sale bien: el dato llega")
r = entrega({"message": "Lead Created Successfully"}, None)
comprobar(r.get("LINK") == "https://x/y", "el valor de la variable llega al modelo")

print("\n[2] Herramienta que falla: el dato NO llega  <- el punto entero")
r = entrega({"error": "No se pudo completar la consulta en este momento."},
            "ConnectionError: timeout")
comprobar("LINK" not in r, "con codigo_error, no se entrega nada")

print("\n[3] Error de negocio sin excepcion: tampoco llega")
r = entrega({"error": "El CRM rechazo la solicitud"}, None)
comprobar("LINK" not in r, "un dict con 'error' con contenido no entrega")

print("\n[4] {'error': False} es EXITO, no fallo")
r = entrega({"error": False, "message": "Lead Created Successfully"}, None)
comprobar(r.get("LINK") == "https://x/y",
          "la respuesta real de BottleCRM SI entrega el dato")

print("\n[5] Herramienta sin entrega_variable: no recibe nada de mas")
r = entrega({"message": "ok"}, None, variable=None)
comprobar(r == {"message": "ok"}, "no se agrega ninguna clave")

print("\n[6] Variable declarada que no existe: la config se niega a cargar")
crudo = cargar_config("tenants/rapilink.config.yaml").model_dump(mode="json")
for h in crudo["herramientas"]:
    if h["nombre"] == "registrar_solicitud_servicio":
        h["entrega_variable"] = "VARIABLE_QUE_NO_EXISTE"
try:
    TenantConfig(**crudo)
    comprobar(False, "una variable inexistente deberia rechazar la config")
except ValueError as e:
    comprobar("VARIABLE_QUE_NO_EXISTE" in str(e),
              "la config se rechaza y el error NOMBRA la variable que falta")

print("\n[7] La config real: el flujo de venta esta completo")
cfg = cargar_config("tenants/rapilink.config.yaml")
herr = next((h for h in cfg.herramientas
             if h.nombre == "registrar_solicitud_servicio"), None)
comprobar(herr is not None, "existe registrar_solicitud_servicio")
# El link YA NO viene de 'entrega_variable'. Desde el 27/08/2026 lo devuelve
# firmado el endpoint que crea el lead y la solicitud, asi que el modelo no
# puede fabricarlo ni adivinarlo -- la misma garantia, sostenida por
# criptografia en vez de por omision. 'entrega_variable' sigue existiendo como
# mecanismo generico (casos 1 a 5), pero esta herramienta ya no lo necesita.
comprobar(bool(herr and not herr.entrega_variable),
          "ya no depende de entrega_variable: el link viene firmado en la respuesta")
comprobar(bool(herr and (herr.endpoint or "").rstrip("/").endswith("/solicitudes")),
          "apunta al endpoint que crea lead y solicitud en una transaccion")
comprobar("link" in (cfg.roles["ventas"].campos_permitidos or {})
          .get("registrar_solicitud_servicio", []),
          "'link' pasa la lista blanca (sin el, el modelo no ve el formulario)")
# 'requiere_confirmacion' se comprueba porque el validador lo exige en toda
# escritura, NO porque frene algo: hoy no lo aplica nadie en tiempo de
# ejecucion (el gate real es 'aprobacion_humana'). Lo que de verdad garantiza
# el flujo es 'entrega_variable', que es lo que fijan los casos 1 a 4.
comprobar(bool(herr and not herr.solo_lectura and herr.requiere_confirmacion),
          "es escritura y declara confirmacion (requisito del validador)")

# Las DOS listas paralelas. 'roles_permitidos' y 'puede_consultar' se declaran
# por separado y el esquema no valida una contra la otra: el 23/08/2026 una
# herramienta quedo sacada de una y no de la otra, y rompio un caso dorado.
comprobar(bool(herr and "ventas" in herr.roles_permitidos),
          "'ventas' esta en roles_permitidos de la herramienta")
comprobar("registrar_solicitud_servicio" in (cfg.roles["ventas"].puede_consultar or []),
          "y TAMBIEN en puede_consultar del rol (son dos listas paralelas)")

# Lo que hace que esto sea una garantia y no una sugerencia.
prompt_ventas = " ".join(str(v) for v in cfg.roles["ventas"].model_dump().values())
comprobar(cfg.variables_tenant.get("VENTAS_FORMULARIO_URL", "@@") not in prompt_ventas,
          "la URL NO esta escrita en el prompt de ventas")
comprobar("{VENTAS_FORMULARIO_URL}" not in prompt_ventas,
          "ni como variable interpolada -- si vuelve al prompt, la guarda cae")

print("\n" + "=" * 70)
if fallos:
    print(f" {len(fallos)} FALLA(S):")
    for f in fallos:
        print(f"   - {f}")
    raise SystemExit(1)
print(" Todo en orden: sin registro no hay link, y el link no vive en el prompt.")
print("=" * 70)
