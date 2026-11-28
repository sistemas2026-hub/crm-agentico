# -*- coding: utf-8 -*-
"""
================================================================================
 ENCENDER (O APAGAR) QUE SE MIREN LAS FOTOS DE UN CAMINO  --  02/11/2026
================================================================================

QUE HACE
--------
Pone en `true` (o en `false`) el interruptor de UN proposito de vision en la
configuracion de un tenant. Los propositos los declara el codigo, en
`nucleo/canales/vision.py::PROPOSITOS`, y este script los lee de ahi: no
tiene su propia lista que se pueda quedar vieja.

    whatsapp_cliente     la foto que un cliente DECIDE mandar por WhatsApp
    evidencia_campo      la que un tecnico toma DENTRO de la casa del cliente
    asistente_interno    la que un colaborador adjunta en el chat interno

TRES INTERRUPTORES Y NO UNO, Y POR ESO ESTE SCRIPT PIDE CUAL
------------------------------------------------------------
No es el mismo consentimiento. Una empresa puede autorizar que su asistente
mire las fotos que le mandan sus clientes y no las que su tecnico toma dentro
de una vivienda, o al reves. Encender uno NO enciende los otros, y este
comando no tiene una opcion para "todos" a proposito: cada uno es una
decision, y se toma de a una.

POR QUE UN SCRIPT Y NO 'cli/cargar_config.py'
---------------------------------------------
Cargar el YAML entero pisa lo que la base tenga y el archivo no traiga --un
agente creado desde la interfaz, una variable editada en vivo--. Esto toca UNA
clave (CLAUDE.md §8).

EL CODIGO VA PRIMERO
--------------------
`vision_asistente_interno` es un campo NUEVO. Los modelos usan extra="forbid":
escribir esta config contra una base cuyo motor todavia no conoce el campo
deja a ese motor rechazando su propia configuracion entera, y el asistente
deja de atender. Por eso se corre DESPUES de desplegar y DESDE el entorno
desplegado.

    python cli/encender_vision.py rapilink asistente_interno
    python cli/encender_vision.py rapilink asistente_interno --aplicar
    python cli/encender_vision.py rapilink asistente_interno --apagar --aplicar

SIN --aplicar NO ESCRIBE NADA.

DONDE SE CORRE: en el contenedor del MOTOR, que es el unico que tiene las
credenciales de la base de produccion. Ahi el ejecutable es `python`, no
`py -3.13` (ese es el lanzador de Windows).

OJO CON EL DIFF (deuda D7): 'editor._editar' reescribe los defaults ausentes,
asi que la version nueva puede diferir en muchas hojas que nadie toco. Lo que
importa es que la clave de abajo quede como se pidio.
================================================================================
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nucleo.canales import vision                                 # noqa: E402
from nucleo.config import editor                                  # noqa: E402


def _uso() -> int:
    print(__doc__)
    print("  propositos disponibles:")
    for nombre in vision.PROPOSITOS:
        print(f"    {nombre:22} -> {vision.bandera_de(nombre)}")
    return 2


OPCIONES = ("--aplicar", "--apagar")


def leer_argumentos(argv: list[str]) -> dict:
    """Lo que se pidio, o el motivo por el que no se entiende.

    APARTE DE `main` para poder probarlo: `main` no se puede llamar sin una
    base, y la decision de si esto ESCRIBE y de si enciende o apaga se toma
    aca. Una prueba que solo comprobara que la cadena "--apagar" aparece en
    el archivo pasaria con el parseo roto -- se midio, el 02/11/2026.

    Devuelve `{"error": ...}` o `{"tenant", "proposito", "aplicar", "valor"}`.
    """
    sueltos = [a for a in argv if not a.startswith("--")]
    opciones = {a for a in argv if a.startswith("--")}
    desconocidas = sorted(opciones - set(OPCIONES))
    if desconocidas:
        return {"error": f"opciones desconocidas: {desconocidas}"}
    if len(sueltos) != 2:
        return {"error": "hacen falta el tenant y el proposito"}
    return {
        "tenant": sueltos[0],
        "proposito": sueltos[1],
        #  SIN --aplicar NO SE ESCRIBE. El default es mirar, no actuar.
        "aplicar": "--aplicar" in opciones,
        #  --apagar invierte. Que se pueda apagar importa: es la unica forma
        #  de cortar esto sin un deploy.
        "valor": "--apagar" not in opciones,
    }


def main() -> int:
    pedido = leer_argumentos(sys.argv[1:])
    if pedido.get("error"):
        print(f"[FALLA] {pedido['error']}\n")
        return _uso()

    tenant = pedido["tenant"]
    proposito = pedido["proposito"]
    aplicar = pedido["aplicar"]
    valor = pedido["valor"]

    campo = vision.bandera_de(proposito)
    if not campo:
        #  Falla CERRADO: un proposito que el codigo no declara no tiene
        #  interruptor, y escribir un campo inventado haria que la config no
        #  cargue mas (extra="forbid").
        print(f"[FALLA] '{proposito}' no es un proposito declarado.\n")
        return _uso()

    from nucleo.config import fuente

    try:
        vigente = fuente.cargar(tenant)
    except Exception as e:                                        # noqa: BLE001
        print(f"[FALLA] no se pudo leer la config de '{tenant}': {type(e).__name__}")
        return 1

    antes = getattr(vigente, campo, None)
    if antes is None:
        #  El campo no existe en el schema que ESTE proceso conoce: el motor
        #  desplegado es mas viejo que el codigo que declara el proposito.
        #  Escribirlo igual dejaria la config sin cargar.
        print(f"[FALLA] el motor de este entorno no conoce '{campo}'. "
              f"Desplegar el codigo primero.")
        return 1

    print(f"  tenant     : {tenant}")
    print(f"  proposito  : {proposito}")
    print(f"  interruptor: {campo}")
    print(f"  ANTES      : {antes}")
    print(f"  DESPUES    : {valor}")

    if antes == valor:
        print("\n  Ya estaba asi: no hay nada que escribir.")
        return 0
    if not aplicar:
        print("\n  SIMULACRO: no se escribio nada. Con --aplicar se escribe.")
        return 0

    def _mutar(doc: dict) -> None:
        doc[campo] = valor

    try:
        nueva = editor._editar(tenant, _mutar)
    except Exception as e:                                        # noqa: BLE001
        print(f"\n[FALLA] el editor no escribio: {type(e).__name__}: {e}")
        return 1

    #  SE AFIRMA SOBRE LO QUE QUEDO, releido del objeto validado -- no sobre
    #  que la llamada no haya levantado.
    quedo = getattr(nueva, campo, None)
    ok = quedo is valor
    print(f"\n  quedo: {campo}={quedo}")
    print("  [OK] escrito." if ok else "  [FALLA] no quedo como se pidio.")

    #  LOS OTROS NO SE TOCARON. Es la garantia entera de los tres
    #  interruptores separados, y se comprueba en vez de prometerse.
    for otro in vision.PROPOSITOS:
        if otro == proposito:
            continue
        campo_otro = vision.bandera_de(otro)
        print(f"  sin tocar: {campo_otro}={getattr(nueva, campo_otro, None)}")

    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
