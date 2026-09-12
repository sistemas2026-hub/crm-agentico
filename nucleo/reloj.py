# -*- coding: utf-8 -*-
"""
================================================================================
 EL RELOJ  --  las tareas periodicas, en su propio proceso
================================================================================

    python -m nucleo.reloj                      corre para siempre
    python -m nucleo.reloj --once               una pasada y termina
    python -m nucleo.reloj --once --dry-run     dice que haria, sin hacerlo

POR QUE ES UN PROCESO Y NO UN HILO
----------------------------------
Esto vivia como 'threading.Thread(...)' dentro del bloque '__main__' de
nucleo/canales/api.py. En produccion el motor NO ejecuta ese bloque: el compose
lo arranca con

    gunicorn nucleo.canales.api:app --workers 1 --threads 8

y gunicorn IMPORTA el modulo, nunca lo corre como '__main__'. El hilo jamas se
creo.

Las fechas cuentan el resto: gunicorn se adopto el 10/08/2026 (b5f4311) y
'cerrar_vencidas' se escribio el 28/08/2026 (b387613), dieciocho dias despues,
contra una topologia que ya habia cambiado. No es que dejara de funcionar --
nunca corrio ni una vez, sin excepcion, sin log y sin sintoma: lo unico que se
veia era que nada se cerraba solo, que es indistinguible de "todavia no vence
ninguna". Se descubrio el 10/09/2026 leyendo la primera linea del log del
contenedor, no el codigo.

Un hilo tampoco era la forma correcta aunque hubiera arrancado: muere con el
worker que lo hospeda (timeout, --max-requests, un reload) y se multiplica en
cuanto alguien sube '--workers' a dos, sin que nada en el codigo lo delate. Un
trabajo periodico necesita un proceso cuyo oficio SEA esperar.

UNA SOLA REPLICA -- CONDICION, NO PREFERENCIA
---------------------------------------------
Los dos trabajos se comportan distinto ante una ejecucion doble simultanea:

  importacion      idempotente por construccion. UNIQUE(org, provider,
                   external_ticket_id) sobre 'cases_case' hace que dos pasadas
                   a la vez converjan al mismo Case; la segunda choca contra la
                   restriccion en vez de duplicar.

  cerrar_vencidas  NO. Auditado el 10/09/2026 leyendo el camino completo:
                   'conversaciones_sin_respuesta' filtra por
                   "estado <> 'cerrada'", asi que en pasadas SUCESIVAS si es
                   idempotente -- una conversacion ya cerrada no vuelve a
                   salir. Pero dos pasadas SIMULTANEAS leen esa lista antes de
                   que ninguna escriba, y las dos siguen hasta 'cerrar_todo',
                   que hace un POST de respuesta al ticket del ISP y una
                   llamada de cierre al CRM. Resultado: el texto de cierre
                   aparece dos veces en el historico del ticket del proveedor.
                   (Al cliente no le llega dos veces: 'cerrar_todo' no manda
                   nada por el canal.)

Por eso 'motor-reloj' corre con UNA replica. No se agrega un lock distribuido:
con una instancia no hace falta, y seria infraestructura para un problema que
hoy no existe. Si alguna vez se escala este servicio, esta nota es la condicion
que hay que resolver ANTES, no despues.

LLEGA INERTE, Y INERTE NO ES MUERTO
-----------------------------------
'RELOJ_HABILITADO' tiene que valer exactamente '1' para que el proceso trabaje.
Con cualquier otro valor -- incluida su ausencia -- arranca, lo dice en el log,
y se queda VIVO sin ejecutar nada.

Vivo y no terminando, que es la parte que importa: el servicio corre con
'restart: unless-stopped', asi que un proceso que imprime "no habilitado" y
sale --aunque salga en 0-- lo reinicia Docker en el acto, y otra vez, y otra.
El modo apagado tiene que ser operacionalmente estable, no un contenedor
rebotando.

Tampoco relee la variable mientras corre. El entorno de un proceso ya arrancado
no cambia solo; cambiarla en Dokploy reinicia el servicio, y ese arranque nuevo
es el que la lee. Un chequeo periodico prometeria una capacidad que no existe.

El interruptor es del DESPLIEGUE, y por eso vive en el entorno del servicio y
no en 'tenant_config': la config del tenant dice QUE hacer y con que reglas; si
este proceso en particular debe estar corriendo es una decision de operacion,
igual para todos los tenants que sirva este despliegue.

LAS CREDENCIALES NO VIAJAN POR EL COMPOSE
-----------------------------------------
'motor' y 'motor-reloj' son contenedores distintos, asi que una credencial
cargada en uno no existe en el otro -- salvo que viaje por algun lado. Viaja
por la BASE: 'secretos.obtener' mira primero 'asistente.tenant_secrets'
(cifrado, por empresa, editable desde la pantalla de credenciales) y solo
despues el entorno. Alcanza entonces con que este proceso tenga
'SECRETOS_CLAVE_MAESTRA', que es la unica que sigue siendo de entorno por
diseño.

Medido el 10/09/2026: 'IMPORTACION_API_TOKEN', 'WISPHUB_API_KEY' y
'BOTTLECRM_API_TOKEN' estan los tres en 'tenant_secrets' de rapilink. Ponerlos
ademas en el entorno de este servicio crearia un segundo lugar de edicion para
el mismo secreto -- y como la base gana, la copia del entorno quedaria vieja
sin que nadie lo note. 'credenciales_resueltas()' responde la pregunta de
verdad ("¿este proceso puede resolverla?") sin exponer ningun valor, y
'--once --dry-run' la reporta por tenant.

QUE HACE Y QUE NO
-----------------
Solo los dos trabajos que ya existian y estaban aprobados: cerrar vencidas e
importar tickets. Esta version no agrega ninguna politica nueva de ciclo de
vida. Un proceso que "corre cosas periodicas" es un cajon comodo, y lo que
entre aca sin discutirse va a correr solo en produccion sin que nadie lo haya
mirado.
================================================================================
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from nucleo.config import fuente
from nucleo.seguimiento import importacion, importacion_io, operativo

# Cuando se intento importar por ultima vez en cada tenant. Vive en memoria a
# proposito: no es un checkpoint de "hasta donde llegue" -- eso no existe, la
# ventana movil de 30 dias lo reemplaza -- sino un regulador de frecuencia.
# Perderlo en un reinicio adelanta como mucho una pasada, y una pasada de mas
# no tiene efecto: el descubrimiento vuelve a encontrar lo mismo y lo marca
# YA_EXISTE.
_ultimo_intento_importacion: dict[str, datetime] = {}


def habilitado() -> bool:
    """
    Si este proceso tiene que trabajar.

    Se lee del entorno, que en un proceso ya arrancado NO cambia solo. Por eso
    el modo daemon la mira una vez, al arrancar, y no la vuelve a consultar en
    cada vuelta: un chequeo periodico de algo que no puede cambiar promete una
    capacidad que no existe -- daria a entender que se puede encender el reloj
    sin redesplegar, y no se puede. Encenderlo es cambiar la variable en
    Dokploy, que reinicia el servicio.

    '--once' si la mira en el momento, y por eso un smoke manual puede correr
    'RELOJ_HABILITADO=1 python -m nucleo.reloj --once --dry-run' dentro del
    contenedor sin tocar lo que Dokploy tiene guardado.
    """
    return os.environ.get("RELOJ_HABILITADO", "0").strip() == "1"


def credenciales_necesarias(config) -> dict[str, list[str]]:
    """
    Que credenciales necesita el reloj en ESTE tenant, y para que herramientas.

    Sale del catalogo del tenant, no de una lista escrita aca: se juntan las
    herramientas que usa el cierre de vencidas (por sus banderas) y las que usa
    la importacion (por su nombre, la lista canonica vive en importacion_io), y
    se agrupa por 'auth_ref'.

    Sirve para responder antes de encender la pregunta que importa: si el
    contenedor del reloj puede resolver lo que va a necesitar. 'motor' y
    'motor-reloj' son contenedores distintos, y que una credencial exista en
    uno no dice nada del otro.
    """
    banderas = ("responde_ticket_operativo", "cierra_ticket_operativo",
                "cierra_caso")
    necesarias: dict[str, list[str]] = {}
    for h in config.herramientas:
        usada = (h.nombre in importacion_io.HERRAMIENTAS
                 or any(getattr(h, b, False) for b in banderas))
        if usada and h.auth_ref:
            necesarias.setdefault(h.auth_ref, []).append(h.nombre)
    return {k: sorted(v) for k, v in sorted(necesarias.items())}


def credenciales_resueltas(config, tenant: str) -> dict[str, bool]:
    """
    Si cada credencial que hace falta se puede resolver DESDE ESTE PROCESO.

    Devuelve solo si/no. El valor no se devuelve, no se loguea y no sale de
    aca: lo unico que se necesita saber es si esta.

    'secretos.obtener' mira primero 'asistente.tenant_secrets' --cifrado, por
    empresa, editable desde la pantalla de credenciales-- y despues el entorno.
    O sea que una credencial cargada por pantalla viaja por la BASE, no por el
    compose: alcanza con que este proceso tenga 'SECRETOS_CLAVE_MAESTRA'.
    """
    from nucleo.seguridad import secretos

    return {ref: bool(secretos.obtener(tenant, ref))
            for ref in credenciales_necesarias(config)}


def tenants_conocidos() -> list[str]:
    """Los tenants que este despliegue sirve, por su archivo semilla."""
    return sorted(p.stem.replace(".config", "")
                  for p in (RAIZ / "tenants").glob("*.config.yaml"))


def _vencimientos(config, tenant: str, seco: bool) -> dict:
    """
    Cierra las conversaciones escaladas donde el cliente dejo de contestar.

    En seco NO se evalua una regla propia: se llama a la MISMA consulta que usa
    'cerrar_vencidas' para elegir a quien cerrar. Dos motores de reglas -- uno
    que decide y otro que explica -- terminan discrepando justo cuando hace
    falta confiar en el segundo.
    """
    horas = config.escalamiento.cerrar_sin_respuesta_horas
    if not horas or horas <= 0:
        return {"plazo_horas": 0, "revisadas": 0, "cerradas": 0,
                "haria": "nada: el tenant no declara plazo"}
    if seco:
        from nucleo.persistencia import db

        candidatas = db.conversaciones_sin_respuesta(tenant, horas)
        return {"plazo_horas": horas, "revisadas": len(candidatas),
                "cerradas": 0, "seco": True,
                "haria": (f"cerrar {len(candidatas)} conversacion(es): ticket "
                          f"del ISP + caso del CRM + conversacion")
                         if candidatas else "nada: no hay vencidas"}
    return {"plazo_horas": horas, **operativo.cerrar_vencidas(config, tenant)}


def _importacion(config, tenant: str, seco: bool, ahora: datetime) -> dict:
    """
    El subsistema de importacion entero: descubrir e importar (B), y despues
    reconciliar los casos que ya existen (C). Las dos las hace 'barrido'.

    'debe_correr' es la compuerta, y vive en el modulo de importacion, no aca:
    con 'cada_horas' en 0 -- el valor por defecto -- devuelve False y no pasa
    NADA. Ni una llamada al proveedor, ni una al CRM, ni una escritura.

    Y NADA quiere decir tambien la reconciliacion. 'cada_horas' manda sobre
    'importacion_tickets' completo, que es la unica semantica explicable en una
    frase; la alternativa dejaba un estado incomodo -- "no importa nada pero
    igual habla con el proveedor cada hora" -- y un segundo interruptor que
    recordar. La razon larga esta en el docstring de 'importacion_io.barrido'.
    """
    cada = config.importacion_tickets.cada_horas
    if not importacion.debe_correr(config.importacion_tickets,
                                   _ultimo_intento_importacion.get(tenant),
                                   ahora):
        return {"le_toca": False, "cada_horas": cada,
                "haria": ("nada: cada_horas=0, la importacion esta apagada"
                          if not cada else
                          f"nada: todavia no se cumplieron las {cada} h")}
    # El sello se pone ANTES de trabajar: si el barrido revienta, el proximo
    # intento igual espera su hora en vez de golpear al proveedor en cada
    # vuelta del bucle.
    _ultimo_intento_importacion[tenant] = ahora
    return {"le_toca": True, "cada_horas": cada,
            "proveedor": config.importacion_tickets.proveedor or "(sin declarar)",
            **importacion_io.barrido(config, tenant, aplicar_cambios=not seco)}


def una_pasada(seco: bool = False) -> list[dict]:
    """
    Una vuelta completa por todos los tenants. Devuelve que paso en cada uno.

    Cada trabajo de cada tenant va en su propio try/except. Son cuatro
    aislamientos distintos y los cuatro hacen falta por separado:

      una config rota          no puede dejar sin atender a los demas tenants
      la importacion rota      no puede dejar sin cerrar las vencidas
      las vencidas rotas       no pueden impedir la importacion
      cualquiera de las dos    no puede matar el proceso

    Una excepcion que mata el reloj deja de hacer TODO, para siempre, y nadie
    se entera hasta que alguien nota que nada se cierra solo -- que es
    exactamente la forma en que este trabajo estuvo muerto un mes entero.

    Se atrapa tambien 'SystemExit', que NO es una 'Exception'. No es paranoia:
    'nucleo/persistencia/conexion.py::dsn' hace 'raise SystemExit' cuando
    faltan los datos de conexion, y hay mas de un sitio asi. En un CLI eso
    esta bien -- el programa termina y lo dice. Aca terminaria el reloj y
    volveriamos al mismo bug de siempre, con la variante de que un tenant mal
    configurado se llevaria puestos a todos los demas. Lo unico que sigue
    subiendo es 'KeyboardInterrupt': parar el proceso tiene que poder pararlo.
    """
    ahora = datetime.now(timezone.utc)
    tenants = tenants_conocidos()
    print(f"[reloj] ciclo inicio {ahora.isoformat(timespec='seconds')}"
          f"{' EN SECO' if seco else ''} -- {len(tenants)} tenant(s): "
          f"{tenants}", flush=True)
    salida = []
    for tenant in tenants:
        r: dict = {"tenant": tenant}
        try:
            config = fuente.cargar(tenant, RAIZ)
        except (Exception, SystemExit) as e:                     # noqa: BLE001
            r["error_config"] = f"{type(e).__name__}: {e}"
            print(f"[reloj] no se pudo leer la config de '{tenant}': "
                  f"{r['error_config']}", flush=True)
            salida.append(r)
            continue

        if seco:
            # La ficha del tenant: lo que hace falta para decidir si encender.
            # Solo en seco -- en una pasada de verdad seria una consulta de
            # credenciales por hora para informar algo que ya se sabe.
            try:
                r["credenciales"] = credenciales_resueltas(config, tenant)
            except (Exception, SystemExit) as e:                 # noqa: BLE001
                r["credenciales"] = {"error": f"{type(e).__name__}: {e}"}

        try:
            r["vencimientos"] = _vencimientos(config, tenant, seco)
        except (Exception, SystemExit) as e:                     # noqa: BLE001
            r["vencimientos"] = {"error": f"{type(e).__name__}: {e}"}
            print(f"[reloj] los vencimientos de '{tenant}' fallaron: "
                  f"{r['vencimientos']['error']}", flush=True)

        try:
            r["importacion"] = _importacion(config, tenant, seco, ahora)
        except (Exception, SystemExit) as e:                     # noqa: BLE001
            r["importacion"] = {"error": f"{type(e).__name__}: {e}"}
            print(f"[reloj] la importacion de '{tenant}' fallo: "
                  f"{r['importacion']['error']}", flush=True)

        print(f"[reloj] {tenant}: {r}", flush=True)
        salida.append(r)
    duro = (datetime.now(timezone.utc) - ahora).total_seconds()
    print(f"[reloj] ciclo fin -- {len(salida)} tenant(s) en {duro:.1f}s"
          + ("" if seco else
             f", proximo en ~{operativo.INTERVALO_BARRIDO_SEGUNDOS // 60} min"),
          flush=True)
    return salida


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    desconocidos = [a for a in argv if a not in ("--once", "--dry-run")]
    if desconocidos:
        print(f"[reloj] no entiendo {desconocidos}.", flush=True)
        return 2
    una_vez = "--once" in argv
    seco = "--dry-run" in argv

    if seco and not una_vez:
        # Un bucle "en seco" para siempre no le sirve a nadie y es una trampa:
        # queda corriendo con toda la pinta de un reloj sin serlo.
        print("[reloj] --dry-run solo tiene sentido junto con --once.",
              flush=True)
        return 2

    minutos = operativo.INTERVALO_BARRIDO_SEGUNDOS // 60
    encendido = habilitado()

    # --once: pasada suelta, a mano. Respeta el interruptor pero lo lee AHORA,
    # asi que un smoke puede hacer 'RELOJ_HABILITADO=1 ... --once --dry-run'
    # dentro del contenedor sin tocar lo que Dokploy tiene guardado.
    if una_vez:
        if not encendido:
            print("[reloj] RELOJ_HABILITADO=0: no se hace nada.", flush=True)
            return 0
        una_pasada(seco=seco)
        return 0

    # De aca para abajo, el daemon.
    print("[reloj] motor-reloj iniciado", flush=True)
    print(f"[reloj] RELOJ_HABILITADO={'1' if encendido else '0'}", flush=True)

    if not encendido:
        # INERTE, PERO VIVO. Con 'restart: unless-stopped', un proceso que
        # imprime y termina --aunque termine en 0-- lo reinicia Docker una y
        # otra vez: seria una ametralladora de contenedores en vez de un
        # servicio apagado.
        #
        # Y no se vuelve a mirar la variable: el entorno de un proceso ya
        # arrancado no cambia solo. Cambiarla en Dokploy reinicia el servicio,
        # y ese arranque nuevo es el que la lee. Un chequeo periodico aca solo
        # prometeria una capacidad que no existe.
        print("[reloj] scheduler inerte: no se ejecuta ningun job. Para "
              "encenderlo, RELOJ_HABILITADO=1 en Dokploy (redespliega el "
              "servicio).", flush=True)
        while True:
            time.sleep(operativo.INTERVALO_BARRIDO_SEGUNDOS)

    print(f"[reloj] scheduler activo: un ciclo cada {minutos} minutos sobre "
          f"{len(tenants_conocidos())} tenant(s).", flush=True)
    while True:
        # Duerme PRIMERO: al desplegar, el proceso no dispara en el segundo
        # cero, cuando quien mira los logs todavia no termino de leer el
        # arranque -- y da margen para apagarlo si arranco por error.
        time.sleep(operativo.INTERVALO_BARRIDO_SEGUNDOS)
        try:
            una_pasada()
        except (Exception, SystemExit) as e:                     # noqa: BLE001
            # La ultima red. Nada puede matar el bucle.
            print(f"[reloj] el ciclo entero fallo: {type(e).__name__}: {e}",
                  flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
