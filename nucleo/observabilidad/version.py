# -*- coding: utf-8 -*-
"""
================================================================================
 QUE CODIGO ESTA CORRIENDO  --  una huella del contenido, no una etiqueta
================================================================================

    py -3.13 -m nucleo.observabilidad.version      imprime la huella de ESTE arbol
    curl https://<motor>/salud                     imprime la del que esta vivo

Si los dos numeros coinciden, el codigo de este arbol es el que esta corriendo.
Si no coinciden, no lo es. No hay un tercer resultado.

POR QUE EXISTE  --  12/11/2026
------------------------------
`/salud` devolvia `{"estado": "ok"}`. Eso dice que el proceso respira y NO dice
que version respira, que es la unica pregunta que alguien se hace despues de un
despliegue. El dia que se busco confirmar un deploy no habia con que: la
respuesta de un motor con el codigo nuevo y la de uno con el viejo eran
identicas, byte a byte.

Es la familia de CLAUDE.md §6 --"codigo construido no es codigo que corre"--
aplicada al propio sistema: el reloj de tareas colgaba de un bloque `__main__`
que gunicorn nunca ejecuta y nadie se entero porque no habia forma de
preguntarle al proceso vivo que tenia adentro.

POR QUE EL CONTENIDO Y NO EL HASH DEL COMMIT
--------------------------------------------
Lo intuitivo seria inyectar el commit en el build. No se puede y no se quiere:

  * NO SE PUEDE. `.dockerignore` excluye `.git` (linea 1), asi que dentro del
    build no hay repositorio al que preguntarle nada. Quedaria depender de que
    la plataforma de despliegue pase un `ARG`, y una etiqueta que la plataforma
    puede olvidar de pasar es una etiqueta que algun dia va a mentir sin que se
    note -- exactamente el modo de falla que esto viene a cerrar.
  * NO SE QUIERE. CLAUDE.md §11 ya lo decidio para la pregunta gemela: "para
    afirmar que algo esta desplegado se compara el CONTENIDO, no el hash".
    Ese dia `merge-base --is-ancestor` conto como ausente un commit rebaseado
    que estaba presente, y el archivo de estado termino afirmando lo contrario
    de la realidad dos veces en el mismo dia, una en cada direccion.

Una huella del contenido no tiene ese problema: un commit rebaseado, un
cherry-pick o un merge dan la misma huella si el codigo es el mismo, que es lo
que de verdad se quiere saber.

QUE ENTRA EN LA HUELLA, Y QUE NO
--------------------------------
Solo `nucleo/`: el motor. No `tests/`, no `cli/`, no `tenants/` --esa es
configuracion y vive en la base, no en la imagen-- y no `django-crm/`, que es
otro servicio con su propio despliegue. Cambiar una prueba no cambia lo que el
motor hace, y una huella que se mueve por eso avisaria de cambios que no son.

LOS SALTOS DE LINEA SE NORMALIZAN, y no es cosmetica
----------------------------------------------------
Este repositorio se trabaja en Windows: el arbol local tiene CRLF y la imagen
se construye desde git, que entrega LF. Sin normalizar, la huella local y la
desplegada NUNCA coincidirian -- y la herramienta diria "no esta desplegado"
sobre el mismo codigo, siempre. Seria peor que no tenerla: un instrumento que
da siempre el mismo resultado no se nota roto, se nota aburrido.

LO QUE ESTO NO PROMETE
----------------------
Que el proceso vivo sea el que contesto. Si hay mas de una replica con
versiones distintas, cada peticion puede caer en una u otra y esta respuesta
habla de la que atendio. Hoy el motor corre con --workers 1 y una sola
instancia (D4), asi que la pregunta no se plantea; el dia que se plantee, esto
hay que leerlo de nuevo.
================================================================================
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

#: La raiz del motor: el paquete que contiene a este archivo.
_NUCLEO = Path(__file__).resolve().parent.parent

#: Cuantos caracteres se publican. Doce de sha256 alcanzan de sobra para
#: distinguir dos despliegues --es lo mismo que usa git para un hash corto-- y
#: entran de un vistazo en una terminal.
_LARGO = 12

_huella: str | None = None


def _archivos() -> list[Path]:
    """Los .py del motor, en orden estable.

    ORDENADOS A PROPOSITO: `rglob` no promete un orden, y un orden distinto
    daria una huella distinta sobre el mismo codigo. Es el tipo de defecto que
    aparece recien al cambiar de sistema de archivos.

    SOLO `*.py`, Y ESO YA DEJA AFUERA `__pycache__`: lo que hay ahi son `.pyc`,
    que cambian por CORRER el codigo y no por cambiarlo. Una huella que se
    moviera con eso dependeria de si alguien importo un modulo, no de que
    version es.

    Aca hubo un filtro explicito de `__pycache__` y se saco el 12/11/2026: una
    pasada de mutacion mostro que no filtraba nada --ningun `.pyc` entra por un
    glob de `*.py`-- y su prueba pasaba sin tocarlo. Un mecanismo que no hace
    nada es peor que no tenerlo: se lee como una garantia.
    """
    return sorted(_NUCLEO.rglob("*.py"))


def huella() -> str:
    """La huella del codigo del motor que este proceso tiene cargado.

    Se calcula UNA VEZ y se recuerda: el codigo de un proceso no cambia
    mientras el proceso vive, y recalcularla en cada `/salud` seria leer cien
    archivos por cada chequeo de un balanceador.
    """
    global _huella
    if _huella is not None:
        return _huella

    acumulador = hashlib.sha256()
    for archivo in _archivos():
        #  LA RUTA TAMBIEN ENTRA: sin ella, mover el contenido de un archivo a
        #  otro daria la misma huella, y eso es un cambio del motor.
        relativa = archivo.relative_to(_NUCLEO).as_posix()
        acumulador.update(relativa.encode("utf-8"))
        acumulador.update(b"\0")
        try:
            crudo = archivo.read_bytes()
        except OSError:
            #  Un archivo ilegible no tumba `/salud`. Se marca su ausencia en
            #  la huella --asi el numero cambia y se nota-- y sigue.
            acumulador.update(b"<ilegible>\0")
            continue
        #  CRLF -> LF: ver el encabezado. Sin esto, local y desplegado nunca
        #  coinciden y la herramienta miente siempre en la misma direccion.
        acumulador.update(crudo.replace(b"\r\n", b"\n"))
        acumulador.update(b"\0")

    _huella = acumulador.hexdigest()[:_LARGO]
    return _huella


def cuantos_archivos() -> int:
    """Sobre cuantos archivos se calculo. Para que un 0 se vea."""
    return len(_archivos())


if __name__ == "__main__":
    print(huella())
    print(f"  ({cuantos_archivos()} archivos de {_NUCLEO.name}/)",
          file=sys.stderr)
