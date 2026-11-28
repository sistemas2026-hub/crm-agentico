# -*- coding: utf-8 -*-
"""
================================================================================
 ¿LO QUE EL TECNICO HIZO EXPLICA EL TICKET QUE ORIGINO LA ORDEN?  --  12/11/2026
================================================================================
El usuario:

    «debe haber relacion entre el asunto, la descripcion del ticket y la
     respuesta del tecnico. No puede haber una respuesta correcta en un
     asunto que ni por ahi iba al caso.»

EL CASO REAL QUE ESTO EXISTE PARA ATRAPAR
------------------------------------------
Primera orden que se miro con el cotejo en pantalla, el 12/11/2026:

  se pidio:  «El cliente pide el cambio de router wifi como gestion
              comercial/tecnica, NO POR UNA FALLA: el equipo esta EN LINEA y
              con SENAL BUENA.»
  que hizo:  «Potencia al llegar: -50.0 dBm. Que encontro: FIBRA PARTIDA
              antes del conector.»

Las dos cosas no pueden ser ciertas a la vez, y los OCHO puntos de
`revision_del_cierre` estaban en verde: la orden se podia cerrar.

LO QUE ESTE MODULO NO HACE, Y ES LA PARTE IMPORTANTE
-----------------------------------------------------
**No decide.** Devuelve `si`, `no` o `no_se_sabe` y un motivo corto. Quien
convierte eso en un punto de la revision es el CRM, y ahi vale `True` o
`None`, NUNCA `False` -- la decision del 31/10/2026
(`campo/inspeccion_visual.py:24-36`): la IA puede pedir atencion, no puede
negar el cierre del trabajo de un tecnico. Un `None` produce `REVISAR`, y una
orden en `REVISAR` no cierra sola. Eso es «no puede pasar» sin reprobar a
nadie.

**No acusa.** Que dos textos se contradigan no prueba que alguien mintio: el
diagnostico pudo quedar viejo, el cliente pudo tener dos problemas, la fibra
pudo partirse entre el diagnostico y la visita. La instruccion se lo dice al
modelo con todas las letras, porque sin eso contesta como fiscal.

**No completa.** Si falta uno de los dos lados, no hay cotejo: `no_se_sabe`
sin llamar a nadie. Pedirle al modelo que opine sobre un texto vacio es pedir
que invente.

POR QUE EL MOTOR Y NO EL CRM
-----------------------------
Mismo reparto que `vision`: la credencial del proveedor vive SOLO aca. El CRM
manda dos textos y recibe un veredicto; no sabe a quien se le pregunto.

FAIL-CLOSED EN LA DIRECCION QUE IMPORTA
----------------------------------------
Cuando algo sale mal --el proveedor no contesta, la respuesta no se entiende,
el tope de gasto esta alcanzado-- se devuelve `no_se_sabe`, nunca `si`. Un
error no puede producir un «esto cuadra»: el costo de frenar una orden que
estaba bien es que alguien la mire; el de dejar pasar una que no, es un
cliente sin servicio y un ticket cerrado.
================================================================================
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

from nucleo.modelo import cliente as cliente_modelo
from nucleo.observabilidad.registro import registrar
from nucleo.seguridad.redaccion import redactar

#: Los tres veredictos. `NO_SE_SABE` es el unico que se devuelve ante un
#: error: ver el encabezado.
CUADRA = "si"
NO_CUADRA = "no"
NO_SE_SABE = "no_se_sabe"

#: La bandera de consentimiento de ESTA empresa, en su `TenantConfig`. Es
#: propia y no la de vision: mandar el texto de un reporte no es el mismo
#: permiso que mandar la foto de una casa, y juntarlos haria que encender uno
#: encienda el otro sin que nadie lo decida.
BANDERA = "cotejo_reporte_campo"

#: Trabajo secundario: nadie espera esta respuesta del otro lado de un chat.
#: Ver `cliente.TIMEOUT_SECUNDARIO` y el bloque TIMEOUTS de ese archivo.
TIMEOUT = cliente_modelo.TIMEOUT_SECUNDARIO

#: Lo que se manda de cada lado. No es por costo: un texto largo diluye la
#: pregunta, y los dos lados reales caben de sobra (el mas largo medido el
#: 12/11/2026 tiene 430 caracteres).
TOPE_POR_LADO = 1500

#: Y lo que se acepta de vuelta como motivo. El veredicto es una palabra; el
#: motivo es una frase para que una persona entienda sin volver a leer todo.
TOPE_MOTIVO = 300

INSTRUCCION = (
    "Sos un supervisor de operaciones de un proveedor de internet por fibra "
    "optica (FTTH). Te doy dos textos sobre UNA misma orden de trabajo: lo "
    "que se pidio --el ticket y lo que el analista dejo escrito-- y lo que el "
    "tecnico reporto al terminar.\n"
    "\n"
    "Tu unica pregunta es: ¿lo que el tecnico reporta PUEDE SER una respuesta "
    "a lo que se pidio?\n"
    "\n"
    "1. Contesta SOLO con dos lineas, en este orden y nada mas:\n"
    "   CUADRA: si | no | no se sabe\n"
    "   POR QUE: <una frase, maximo 30 palabras>\n"
    "2. 'no' es para una CONTRADICCION entre los dos textos, no para un "
    "reporte incompleto ni para uno escrito con pocas palabras. Ejemplo de "
    "contradiccion: el ticket dice que el equipo estaba EN LINEA y con senal "
    "buena, y el tecnico reporta una FIBRA PARTIDA y -50 dBm al llegar; un "
    "equipo con la fibra partida no esta en linea.\n"
    "3. 'si' incluye el caso en que el tecnico encontro algo DISTINTO de lo "
    "que se sospechaba pero compatible con el sintoma. Que el analista "
    "dijera 'parece la configuracion' y fuera un conector sucio no es una "
    "contradiccion: es un diagnostico que se afino en el sitio, y eso es "
    "lo normal.\n"
    "4. 'no se sabe' cuando alguno de los dos textos no alcanza para "
    "decidirlo. Es la respuesta correcta muchas veces; no la evites.\n"
    "5. NO ACUSES A NADIE. No digas que el tecnico mintio, se equivoco o "
    "hizo mal el trabajo. Aunque los dos textos se contradigan, puede que el "
    "diagnostico haya quedado viejo, que el cliente tuviera dos problemas, o "
    "que la falla apareciera entre el diagnostico y la visita. Nombra la "
    "contradiccion; no la resuelvas.\n"
    "6. No propongas que se devuelva la orden ni que se apruebe: eso lo "
    "decide una persona.\n"
    "7. No transcribas nombres, documentos, telefonos ni direcciones que "
    "aparezcan en los textos.\n"
    "8. En 'POR QUE', cita lo concreto de CADA lado que te hizo decidir. "
    "'No coinciden' no le sirve a nadie; 'el ticket dice que el equipo "
    "estaba en linea y el reporte describe una fibra partida' si.\n"
)

#: `CUADRA: si`, con o sin acentos, mayusculas o guiones bajos.
_LINEA_CUADRA = re.compile(r"^\s*CUADRA\s*:\s*(.+?)\s*$",
                           re.IGNORECASE | re.MULTILINE)
_LINEA_PORQUE = re.compile(r"^\s*POR\s*_?\s*QUE\s*:\s*(.+?)\s*$",
                           re.IGNORECASE | re.MULTILINE)


@dataclass
class Resultado:
    """Que salio. `veredicto` es siempre uno de los tres."""
    veredicto: str = NO_SE_SABE
    motivo: str = ""
    error: str = ""
    segundos: float = 0.0
    tokens: int = 0

    @property
    def contradice(self) -> bool:
        return self.veredicto == NO_CUADRA


def _normalizar(crudo: str) -> str:
    """La palabra del modelo a uno de los tres veredictos.

    Fail-closed: lo que no se entiende es `no_se_sabe`, nunca `si`. Un
    proveedor que contesta 'Si, cuadra perfectamente' no puede producir un
    'si' por accidente ni un 'no' por contener la letra n.
    """
    t = (crudo or "").strip().lower()
    t = t.replace("í", "i").replace("á", "a").replace("é", "e")
    #  Primero lo mas especifico: 'no se sabe' contiene 'no'.
    if t.startswith("no se sabe") or t.startswith("no_se_sabe"):
        return NO_SE_SABE
    if t.startswith("si"):
        return CUADRA
    if t.startswith("no"):
        return NO_CUADRA
    return NO_SE_SABE


def _recortar(texto: str, tope: int) -> str:
    limpio = " ".join(str(texto or "").split())
    return limpio[:tope]


def leer(respuesta: str) -> tuple[str, str]:
    """El veredicto y el motivo de lo que contesto el modelo.

    Si la linea `CUADRA:` no esta, es `no_se_sabe`: una respuesta que no
    sigue el formato no se interpreta a ojo. Es la misma regla que
    `vision`: el modelo habla con el codigo por lineas marca, y lo que no
    viene en una linea marca no es un veredicto.
    """
    m = _LINEA_CUADRA.search(respuesta or "")
    if m is None:
        return NO_SE_SABE, ""
    p = _LINEA_PORQUE.search(respuesta or "")
    return _normalizar(m.group(1)), _recortar(p.group(1) if p else "",
                                              TOPE_MOTIVO)


def cotejar(se_pidio: str, que_hizo: str, modelo: str) -> Resultado:
    """Compara los dos lados. No escribe, no decide, no acusa.

    SIN UNO DE LOS DOS LADOS NO SE LLAMA A NADIE. Un texto vacio no produce
    una comparacion: produce `no_se_sabe`, gratis y al instante. Pedirle al
    modelo que opine sobre la nada es pedirle que invente, y ademas se
    pagaria por eso -- en produccion hay ordenes sin reporte escrito.
    """
    izq, der = _recortar(se_pidio, TOPE_POR_LADO), _recortar(que_hizo,
                                                             TOPE_POR_LADO)
    if not izq or not der:
        return Resultado(veredicto=NO_SE_SABE,
                         motivo=("falta lo que se pidio" if not izq
                                 else "el tecnico no escribio que hizo"))

    mensajes = [
        {"role": "system", "content": INSTRUCCION},
        {"role": "user", "content": (f"LO QUE SE PIDIO:\n{izq}\n\n"
                                     f"LO QUE EL TECNICO REPORTO:\n{der}")},
    ]
    arranque = time.monotonic()
    try:
        r = cliente_modelo.chat(modelo, mensajes, temperatura=0.0,
                                timeout=TIMEOUT)
    except Exception as e:                                       # noqa: BLE001
        #  El tipo, nunca `str(e)`: el mensaje de un proveedor puede traer de
        #  vuelta lo que se le mando.
        registrar("cotejo", "el proveedor no contesto", error=e)
        return Resultado(veredicto=NO_SE_SABE, error=type(e).__name__,
                         segundos=round(time.monotonic() - arranque, 2))

    #  `contenido`, no `texto`: es el nombre del campo en `cliente.Respuesta`.
    veredicto, motivo = leer(getattr(r, "contenido", "") or "")
    #  LA REDACCION TAMBIEN A LA SALIDA. El motivo lo escribe el modelo
    #  citando los dos textos, y esos textos son de personas: aunque la
    #  instruccion prohibe transcribir datos, el prompt es guia y el codigo
    #  es la garantia (PRD 7.4).
    return Resultado(veredicto=veredicto, motivo=redactar(motivo),
                     segundos=round(time.monotonic() - arranque, 2),
                     tokens=int(getattr(r, "tokens_entrada", 0) or 0)
                     + int(getattr(r, "tokens_salida", 0) or 0))
