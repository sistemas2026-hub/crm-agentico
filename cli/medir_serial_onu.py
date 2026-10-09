# -*- coding: utf-8 -*-
"""
Por que el diagnostico optico de un servicio no se puede hacer. SOLO LECTURA.

    py -3.13 cli/medir_serial_onu.py rapilink 535 4045 7755
    py -3.13 cli/medir_serial_onu.py rapilink 535 --con-diagnostico

NUNCA IMPRIME EL SERIAL, y no es pudor: el serial habilita reiniciar el equipo
de un cliente, y esto se corre en una terminal cuya salida termina pegada en
una conversacion. Lo que imprime es la FORMA --cuantos caracteres, si es
alfanumerico, si trae guion o espacio, las cuatro letras del fabricante-- que
es exactamente lo que hace falta para distinguir las dos causas posibles de un
HTTP 400 y nada mas que eso.

QUE PREGUNTA CONTESTA
---------------------
El 07/10/2026 la primera propuesta con diagnostico dijo: "el estado del equipo
volvio como 'desconocido' (el proveedor optico contesto 400)". Segun la skill
de SmartOLT, 400 en ese endpoint es "Invalid parameters" -- el identificador no
le sirve. Hay dos causas, y la diferencia decide si hay algo que arreglar:

  formato      el serial viaja con guion, espacio o con un largo distinto de 12
               -> se normaliza antes de llamar, y es una linea
  no existe    el equipo ya no esta dado de alta en SmartOLT (ONU vieja o
               cambiada) -> no hay nada que arreglar: lo correcto es que la
               propuesta diga que no pudo diagnosticar, como ya hace

Tambien existe el caso 'sin_onu': 1.299 de 4.163 clientes activos no tienen
'sn_onu' cargado en WispHub (medido, ver la skill). Ese no da 400 -- el
ejecutor lo contesta sin llamar al proveedor.

POR QUE ES UN SCRIPT Y NO UN COMANDO PEGADO EN LA TERMINAL
----------------------------------------------------------
Porque la terminal web del servidor trunca los comandos largos: dos intentos
quedaron cortados a la mitad, uno de ellos dejando la shell esperando una
comilla. Un script en el repositorio se corre con una linea corta, queda
versionado y lo puede volver a correr cualquiera.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from nucleo.config import fuente as fuente_config          # noqa: E402
from nucleo.herramientas import http as ejecutor_http      # noqa: E402

#  Lo que la skill de SmartOLT documenta como formato valido, verificado en
#  vivo el 14/08/2026: 12 caracteres, sin guiones (CDTC505AEAFF).
LARGO_ESPERADO = 12


def _ficha(herramienta, id_servicio, tenant, variables):
    crudo = ejecutor_http.ejecutar(
        herramienta, {"id_servicio": id_servicio},
        tenant=tenant, variables_tenant=variables)
    if isinstance(crudo, dict) and isinstance(crudo.get("results"), list):
        return (crudo["results"] or [{}])[0] or {}
    return crudo if isinstance(crudo, dict) else {}


def main() -> int:
    argumentos = [a for a in sys.argv[1:] if not a.startswith("--")]
    con_diagnostico = "--con-diagnostico" in sys.argv

    if len(argumentos) < 2:
        print(__doc__)
        return 2

    tenant, ids = argumentos[0], argumentos[1:]
    config = fuente_config.cargar(tenant)

    cliente = next((h for h in config.herramientas
                    if h.nombre == "consultar_cliente"), None)
    if cliente is None:
        print("  'consultar_cliente' no esta en el catalogo de este tenant.")
        return 1

    diag = next((h for h in config.herramientas
                 if getattr(h, "diagnostica_servicio", False)), None)
    if con_diagnostico and diag is None:
        print("  no hay ninguna herramienta de diagnostico en el catalogo.")
        return 1

    print(f"\n  TENANT: {tenant}   servicios a revisar: {len(ids)}")
    print(f"  Formato que espera SmartOLT: {LARGO_ESPERADO} caracteres, "
          f"sin guiones ni espacios.")
    if con_diagnostico:
        print("  Con --con-diagnostico: ~10 s por servicio. Paciencia.")
    print()

    resumen = {"sin_onu": 0, "formato_raro": 0, "formato_ok": 0, "error": 0}

    for id_servicio in ids:
        try:
            serial = str(_ficha(cliente, id_servicio, tenant,
                                config.variables_tenant).get("sn_onu")
                         or "").strip()
        except Exception as e:                               # noqa: BLE001
            #  El tipo y no el texto: el texto de una excepcion de red trae la
            #  URL, y la URL lleva el identificador del servicio.
            resumen["error"] += 1
            print(f"  {id_servicio:>6}  no se pudo consultar la ficha "
                  f"({type(e).__name__})")
            continue

        if not serial:
            resumen["sin_onu"] += 1
            print(f"  {id_servicio:>6}  SIN EQUIPO REGISTRADO en WispHub "
                  f"(sn_onu vacio) -- este caso no da 400, se contesta sin "
                  f"llamar al proveedor")
            continue

        raro = (len(serial) != LARGO_ESPERADO or not serial.isalnum())
        resumen["formato_raro" if raro else "formato_ok"] += 1
        print(f"  {id_servicio:>6}  largo={len(serial):<3} "
              f"alfanumerico={str(serial.isalnum()):<5} "
              f"guion={str('-' in serial):<5} "
              f"espacio={str(' ' in serial):<5} "
              f"fabricante={serial[:4]}"
              + ("   <<< FORMATO FUERA DE LO ESPERADO" if raro else ""))

        if con_diagnostico:
            from nucleo.herramientas import diagnostico_servicio as dx

            salida = dx.diagnosticar(diag, {"id_servicio": id_servicio},
                                     tenant=tenant,
                                     variables_tenant=config.variables_tenant,
                                     catalogo=config.herramientas)
            #  'salida' no trae el serial: el ejecutor no lo devuelve.
            print(f"          -> estado={salida.get('estado')} "
                  f"senal={salida.get('senal')} "
                  f"causa={salida.get('causa_caida') or '-'} "
                  f"motivo={salida.get('motivo') or '-'}")

    print(f"\n  RESUMEN")
    print(f"    sin equipo registrado .......... {resumen['sin_onu']}")
    print(f"    formato esperado ............... {resumen['formato_ok']}")
    print(f"    formato RARO (explicaria el 400) {resumen['formato_raro']}")
    print(f"    no se pudo consultar ........... {resumen['error']}")
    print()
    if resumen["formato_raro"]:
        print("    Hay seriales con formato raro: eso SI se arregla "
              "normalizando antes de llamar.")
    elif resumen["formato_ok"] and not con_diagnostico:
        print("    Todos con el formato esperado. Si igual dan 400, el equipo "
              "no esta dado de alta en SmartOLT.")
        print("    Para confirmarlo, repetir con --con-diagnostico sobre UNO "
              "solo (tarda ~10 s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
