# -*- coding: utf-8 -*-
"""
================================================================================
 EL DIAGNOSTICO OPTICO SALE POR LOS DOS DESPACHOS, Y NUNCA DEVUELVE EL SERIAL
================================================================================

QUE SE PRUEBA
-------------
Tres cosas, y cada una tiene su cicatriz:

  1. Que 'motor.ejecutar_para_servicio' LLEGUE al ejecutor de diagnostico.
     Hay DOS despachos en nucleo/modelo/motor.py --'_despacho_de_herramienta',
     que es el del modelo, y 'ejecutar_para_servicio', que es el de un servicio
     interno-- y el 07/10/2026 la herramienta estaba cableada solo en el
     primero. El sintoma no señalaba la causa: la herramienta existia, estaba
     autorizada por rol, tenia 'invocable_por_servicio: true' en la base, y el
     chat del Supervisor recibia HTTP 502. Ese 502 era el 'except Exception' de
     la ruta interna atrapando el ValueError "solo 'http'" del final de
     'ejecutar_para_servicio'.

  2. Que el SERIAL de la ONU no salga nunca en el resultado. El serial habilita
     reiniciar el equipo. Que el modelo pueda leerlo es la mitad de un camino
     de inyeccion -- la otra mitad seria una herramienta de reinicio que acepte
     el serial como argumento del modelo.

  3. Que la señal se clasifique EN CODIGO, no la interprete el modelo, y que
     la clasificacion no se mezcle con 'Match state'. Un campo unico llamado
     'senal_texto' decia 'mismatch' con -20.55 dBm, que es una señal BUENA:
     'Match state' habla de la config aplicada en la OLT, no del nivel optico.

COMO SE AFIRMA, Y POR QUE ASI
-----------------------------
La §1 se mide POR EFECTO: se reemplaza el ejecutor por un centinela y se
afirma que la salida ES el centinela. Una prueba que dijera "la rama esta
escrita" --buscando el texto en el fuente-- pasaria en verde con el ejecutor
desconectado, y encima se dispararia con un docstring que mencione el flag.
Esa trampa ya costo tiempo cinco veces en este repositorio.

Sin red, sin base y sin modelo:

    py -3.13 tests/test_diagnostico_servicio.py
================================================================================
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for var, valor in (("DBHOST", "localhost"), ("DBPORT", "5432"),
                   ("DBNAME", "postgres"), ("DBUSER", "postgres"),
                   ("DBPASSWORD", "x")):
    os.environ.setdefault(var, valor)

from nucleo.config.schema import Herramienta                      # noqa: E402
from nucleo.herramientas import diagnostico_servicio as diag     # noqa: E402
from nucleo.modelo import motor                                  # noqa: E402

FALLOS = []


def afirmar(condicion, que):
    print(f"  [{'ok' if condicion else 'FALLA'}] {que}")
    if not condicion:
        FALLOS.append(que)


class _Identidad:
    slug = "tenant_de_prueba"


class _Config:
    """Lo minimo que 'ejecutar_para_servicio' lee de una config."""

    identidad = _Identidad()
    variables_tenant = {"SMARTOLT_SUBDOMINIO": "ejemplo"}
    roles = {}


def _herramienta(**cambios):
    """La herramienta REAL del schema, no un doble artesanal.

    La primera version de esta prueba imitaba a mano los atributos que el
    despacho mira y fallaba por los que no adivino ('argumentos_fijos'). Una
    instancia del schema los trae todos con su default -- y si manana el
    despacho mira un campo nuevo, esta prueba no se cae por eso.
    """
    datos = {"nombre": "diagnosticar_servicio",
             "descripcion": "Diagnostico optico de un servicio.",
             "tipo": "interno",
             "diagnostica_servicio": True,
             "resolver_equipo_con": "consultar_cliente",
             "invocable_por_servicio": True,
             "roles_permitidos": ["supervisor_noc"],
             "solo_lectura": True}
    datos.update(cambios)
    return Herramienta(**datos)


print("=" * 70)
print(" EL DIAGNOSTICO OPTICO: LOS DOS DESPACHOS, EL SERIAL Y LA SEÑAL")
print("=" * 70)

print("\n§1  LA RUTA DE UN SERVICIO LLEGA AL EJECUTOR  --  medido por efecto")

CENTINELA = {"__centinela__": "llego al ejecutor de diagnostico"}
_visto = {}


def _falso_diagnosticar(herramienta, argumentos, tenant=None,
                        variables_tenant=None, catalogo=None):
    _visto["tenant"] = tenant
    _visto["argumentos"] = dict(argumentos or {})
    return CENTINELA


_original = motor.ejecutor_diagnostico.diagnosticar
motor.ejecutor_diagnostico.diagnosticar = _falso_diagnosticar
try:
    salida = motor.ejecutar_para_servicio(
        _Config(), _herramienta(), {"id_servicio": 5832})
    error = None
except Exception as e:                                           # noqa: BLE001
    salida, error = None, e
finally:
    motor.ejecutor_diagnostico.diagnosticar = _original

afirmar(error is None,
        f"'ejecutar_para_servicio' no lanza"
        + (f" (lanzo {type(error).__name__}: {error})" if error else ""))
afirmar(salida is CENTINELA,
        "y la salida ES la del ejecutor de diagnostico, no otra cosa")
#  El slug importa: el ejecutor lo usa para resolver la credencial del tenant.
#  Si llegara vacio, la llamada saldria sin clave y el sintoma seria un 403 de
#  SmartOLT, que señala al proveedor y no a esto.
afirmar(_visto.get("tenant") == "tenant_de_prueba",
        "y el ejecutor recibe el slug del tenant, no una cadena vacia")

print("\n§2  LA MUTACION QUE ESTA PRUEBA TIENE QUE MATAR")
#  Lo que fallo en produccion fue EXACTAMENTE esto: sin la rama, el final de
#  'ejecutar_para_servicio' lanza ValueError y la ruta interna lo convierte en
#  502. Se reproduce apagando el flag, que es la forma de llegar al final de la
#  funcion sin tocar el fuente.
try:
    motor.ejecutar_para_servicio(
        _Config(), _herramienta(diagnostica_servicio=False),
        {"id_servicio": 5832})
    cayo = None
except Exception as e:                                           # noqa: BLE001
    cayo = e

afirmar(isinstance(cayo, ValueError) and "solo 'http'" in str(cayo),
        "sin rama que la atienda, una 'interno' muere con ValueError -- que es "
        "el 502 que se vio")

print("\n§3  LAS CLAVES QUE EL EJECUTOR PROMETE  --  el serial no esta entre ellas")
#  '_sin_resolver' es el unico camino de salida que no habla con el proveedor,
#  asi que sirve para leer la FORMA del resultado sin red.
forma = diag._sin_resolver("motivo de prueba", 5832)
afirmar(isinstance(forma, dict), "'_sin_resolver' devuelve un dict")
prohibidas = {"sn", "SN", "sn_onu", "serial", "equipo", "Description",
              "nombre", "ip", "IPv4 address", "mac"}
afirmar(not (set(forma) & prohibidas),
        f"ninguna clave del resultado es el serial ni PII: {sorted(forma)}")
afirmar("equipo_registrado" in forma,
        "y si dice SI HAY equipo registrado, que es el dato util sin el serial")

print("\n§4  LA SEÑAL SE CLASIFICA EN CODIGO, Y NO ES 'Match state'")
afirmar(diag._clasificar_senal(-20.55) == "buena",
        "-20.55 dBm es buena (el caso real que un campo unico llamaba "
        "'mismatch')")
afirmar(diag._clasificar_senal(-27.0) == "debil",
        f"-27.0 dBm es debil (fuera del piso {diag.SENAL_MINIMA_DBM})")
afirmar(diag._clasificar_senal(None) == "sin_dato",
        "sin lectura NO se inventa una clasificacion")
afirmar(diag._clasificar_senal(-8.0) == "buena"
        and diag._clasificar_senal(-25.0) == "buena",
        "los bordes del rango documentado (-25 a -8) cuentan como buenos")
#  Y el campo de config va aparte, para que no se lean como lo mismo.
afirmar("senal" in forma and "estado_config" in forma,
        "'senal' y 'estado_config' son campos DISTINTOS del resultado")

print("\n§5  LA CAUSA DE CAIDA SE TRADUCE A ALGO QUE DECIDE UNA ACCION")
#  'dying-gasp' y 'LOSi' llevan a conversaciones distintas: una es un corte de
#  luz en la casa, la otra es fibra. Si el modelo tuviera que interpretar el
#  texto crudo del proveedor, eso seria el prompt haciendo de garantia.
afirmar(diag._clasificar_causa("dying-gasp") == diag.SIN_ENERGIA,
        "'dying-gasp' es sin energia (corte de luz del cliente)")
afirmar(diag._clasificar_causa("ONT LOSi/LOBi alarm") == diag.FIBRA,
        "'LOSi/LOBi' es fibra")
afirmar(diag._clasificar_causa("ONT LOFi alarm") == diag.FIBRA,
        "'LOFi' tambien es fibra, no otra categoria")
#  '' y 'otra' NO son lo mismo, y la diferencia decide una conversacion:
#  vacio es "el proveedor no reporto ninguna caida" (tipico de un equipo en
#  linea), 'otra' es "reporto una causa que este codigo no sabe traducir". Si
#  las dos cayeran en el mismo cajon, un equipo sano se leeria como un equipo
#  con una falla sin clasificar.
afirmar(diag._clasificar_causa("") == "",
        "sin causa reportada el campo queda VACIO, no 'otra'")
afirmar(diag._clasificar_causa("algo que el proveedor no documento")
        == diag.OTRA,
        "una causa nueva del proveedor cae en 'otra', no en la ultima probada")

print("\n§6  NINGUNA 'interno' INVOCABLE POR SERVICIO MUERE CON \"solo 'http'\"")
#  LA GUARDA QUE PREVIENE LA TERCERA, y la razon de que exista: al arreglar el
#  diagnostico se midio el catalogo entero por este mismo criterio y aparecio un
#  SEGUNDO hueco identico ('consultar_caidas_pon_flota'), declarada invocable
#  por un servicio y sin rama que la atienda. No se habia visto porque hoy nadie
#  la pide -- estaba cableada para fallar el dia que se active, y el sintoma
#  habria sido un 502 que no señala a esto.
#
#  SE MIDE POR EFECTO, NO POR AST. La primera version de esta medicion leia QUE
#  atributos de 'herramienta' toca cada despacho, y daba un falso OK para una
#  herramienta que no enciende ningun flag conocido: el conjunto vacio satisface
#  cualquier condicion. Llamar y ver si muere no tiene ese agujero.
#
#  Se recorren TODOS los tenants del repositorio y no se nombra ninguno: el
#  nucleo no conoce un cliente, y una prueba del nucleo tampoco deberia.
import glob                                                      # noqa: E402

import yaml                                                      # noqa: E402

from nucleo.config.schema import TenantConfig                    # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
semillas = sorted(glob.glob(os.path.join(RAIZ, "tenants", "*.config.yaml")))
afirmar(bool(semillas), f"hay semillas de tenant para revisar ({len(semillas)})")

huecos = []
revisadas = 0
for ruta in semillas:
    with io.open(ruta, encoding="utf-8") as fh:
        cfg = TenantConfig(**yaml.safe_load(fh))
    for h in cfg.herramientas:
        if h.tipo != "interno" or not h.invocable_por_servicio:
            continue
        revisadas += 1
        try:
            motor.ejecutar_para_servicio(cfg, h, {})
        except ValueError as e:
            if "solo 'http'" in str(e):
                huecos.append(f"{os.path.basename(ruta)}:{h.nombre}")
        except Exception:                                        # noqa: BLE001
            #  Cualquier otra excepcion significa que el despacho SI la atendio
            #  y fallo mas adentro (sin red, sin credencial). Eso no es lo que
            #  se mide aqui.
            pass

afirmar(revisadas > 0,
        f"se llamo a cada 'interno' invocable por servicio ({revisadas})")
afirmar(not huecos,
        f"ninguna muere en el despacho de servicio (huecos: {huecos})")

print("\n" + "=" * 70)
if FALLOS:
    print(f"FALLARON {len(FALLOS)}:")
    for f in FALLOS:
        print(f"  - {f}")
    sys.exit(1)
print("TODO OK: el diagnostico sale por los dos despachos, sin el serial, y la "
      "señal la clasifica el codigo")
