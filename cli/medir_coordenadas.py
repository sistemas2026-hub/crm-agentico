# -*- coding: utf-8 -*-
"""
Que forma tiene el campo 'coordenadas' de WispHub, y cuantos lo tienen. SOLO LECTURA.

    py -3.13 cli/medir_coordenadas.py rapilink 5832
    py -3.13 cli/medir_coordenadas.py rapilink --todos

NUNCA IMPRIME UNA COORDENADA, y no es pudor: una coordenada ES EL DOMICILIO DE
UNA PERSONA, y esto se corre en una terminal cuya salida termina pegada en una
conversacion. Lo que imprime es la FORMA --cada digito reemplazado por 'D',
cada letra por 'a'-- mas los conteos. Con eso alcanza para escribir el parseo
y no alcanza para saber donde vive nadie.

QUE PREGUNTA CONTESTA, Y POR QUE NO SE PUEDE CONTESTAR LEYENDO LA DOCUMENTACION
-------------------------------------------------------------------------------
El mapa del Supervisor tiene que dibujar a donde va cada cuadrilla. La orden de
trabajo guarda dos numeros ('gps_lat', 'gps_lng', FloatField); WispHub guarda
UN campo de texto. Alguien tiene que partirlo, y partirlo mal NO DA ERROR: da
una casa equivocada, con un pin que se lee como un hecho.

El spec oficial de WispHub, leido el 05/11/2026, declara exactamente esto:

    coordenadas:
      title: Coordenadas
      type: string

Sin 'format', sin 'example', sin 'pattern', sin 'nullable'. Su unico ejemplo es
el literal "String". O sea: la documentacion CONFIRMA que no documenta el
formato. No hay de donde deducirlo -- solo medirlo. Es la regla de CLAUDE.md
§4 aplicada tal cual: la documentacion de una API externa es una hipotesis.

Los cuatro modos de fallar que esto descarta, todos reales:

    "10.9185,-74.7668"    lat primero          -> el pin cae en la casa
    "-74.7668,10.9185"    lng primero          -> el pin cae en el mar
    "10,9185, -74,7668"   coma decimal         -> cuatro pedazos, basura
    "0,0"                 el "vacio" de WispHub-> el Golfo de Guinea, y es una
                                                  coordenada VALIDA: una guarda
                                                  que pregunte "esta vacio?" la
                                                  deja pasar

Y la segunda pregunta, que decide si el trabajo sirve hoy o dentro de un ano:
CUANTOS clientes lo tienen cargado, partido por estado. Un activo sin
coordenadas es carga pendiente; uno retirado no importa.

POR QUE NO MANEJA LA CREDENCIAL
-------------------------------
Pide por 'nucleo.herramientas.http', con la herramienta 'consultar_cliente' tal
como esta declarada en la config del tenant. La clave se resuelve donde ya
vive --'auth_ref'-- y este archivo no la lee, no la recibe y no la imprime. El
subdominio tambien sale de la config, asi que otro ISP con otro dominio se mide
con el mismo comando. Mismo criterio que 'cli/medir_serial_onu.py'.

POR QUE ES UN SCRIPT Y NO UN COMANDO PEGADO EN LA TERMINAL
----------------------------------------------------------
Porque la terminal web del servidor trunca los comandos largos -- ya paso dos
veces, una dejando la shell esperando una comilla. Un script se corre con una
linea corta, queda versionado y lo vuelve a correr cualquiera.
"""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

#  EL .env, COMO TODOS SUS HERMANOS  --  12/11/2026.
#
#  Este script no lo cargaba, y entonces no podia correrse desde una maquina
#  de desarrollo: `fuente.cargar()` pide las cinco variables de conexion y sin
#  ellas muere con "No hay datos de conexion en el entorno" -- un mensaje que
#  suena a que falta configuracion del servidor y lo que faltaba era esta
#  linea. Medido hoy al intentar usarlo para mirar los servicios 5345 y 5394.
#
#  override=False: el entorno explicito gana, el archivo solo rellena.
from dotenv import find_dotenv, load_dotenv                # noqa: E402

#  DOS BUSQUEDAS, Y LA SEGUNDA NO ES REDUNDANTE. `load_dotenv()` pelado busca
#  desde la carpeta DEL SCRIPT hacia arriba; con el script en un worktree y el
#  `.env` en la copia principal, no lo encuentra nunca y el mensaje que sale
#  --"No hay datos de conexion"-- apunta al entorno y no a la ruta. Medido el
#  12/11/2026. `usecwd=True` busca desde donde esta parado quien lo corre.
load_dotenv(override=False)
load_dotenv(find_dotenv(usecwd=True), override=False)

from nucleo.config import fuente as fuente_config          # noqa: E402
from nucleo.herramientas import http as ejecutor_http      # noqa: E402

#: De a cuantos se pagina. WispHub acepta 'limit'/'offset'; 100 es el tamano
#: que ya usan los otros recorridos del repo sin que el proveedor se queje.
POR_PAGINA = 100

#: Los "vacios" que hay que tratar como ausencia aunque no sean cadena vacia.
#: '0,0' esta aca por el motivo del encabezado: es valido y no es la casa.
VACIOS = ("", "none", "null", "0,0", "0.0,0.0", "-", "n/a")


def forma_de(valor) -> str:
    """La silueta del valor, sin el valor.

    Digitos a 'D' y letras a 'a'. Lo que queda --comas, puntos, espacios,
    signos, parentesis-- es exactamente lo que hace falta para escribir el
    parseo, y no permite reconstruir ninguna coordenada.
    """
    if valor is None:
        return "<null JSON>"
    if not isinstance(valor, str):
        return f"<{type(valor).__name__}>"
    if valor == "":
        return "<cadena vacia>"
    #  UNA SOLA PASADA, y no dos sustituciones encadenadas. Encadenadas tenian
    #  un error que esta medido: digitos -> 'D' y despues letras -> 'a' volvia
    #  a pisar las 'D' recien puestas, y '10.9185' salia como 'aa.aaaa'. La
    #  silueta mentia justo sobre lo que esta funcion existe para mostrar.
    return re.sub(r"[0-9A-Za-z]",
                  lambda m: "D" if m.group().isdigit() else "a", valor)


def esta_cargada(valor) -> bool:
    return isinstance(valor, str) and valor.strip().lower() not in VACIOS


def numeros_de(valor):
    """Los dos componentes, si se pueden sacar. Solo para medir rangos.

    NO es el parseo definitivo --ese se escribe DESPUES, con lo que esto
    mida-- y a proposito no corrige nada: si hay tres numeros o ninguno, lo
    dice devolviendo None en vez de quedarse con los dos primeros.
    """
    hallados = re.findall(r"-?\d+(?:\.\d+)?", valor or "")
    if len(hallados) != 2:
        return None
    try:
        return float(hallados[0]), float(hallados[1])
    except ValueError:
        return None


def _filas(herramienta, argumentos, tenant, variables):
    crudo = ejecutor_http.ejecutar(herramienta, argumentos, tenant=tenant,
                                   variables_tenant=variables)
    if isinstance(crudo, dict):
        if isinstance(crudo.get("results"), list):
            return crudo["results"], crudo.get("count")
        return [crudo], 1
    if isinstance(crudo, list):
        return crudo, len(crudo)
    return [], 0


def _informar(formas, por_estado, pares, revisados):
    print(f"\n  REVISADOS: {revisados}")

    print("\n  FORMAS DISTINTAS  (D = un digito, a = una letra)")
    if not formas:
        print("    (ninguna)")
    for silueta, n in formas.most_common(25):
        print(f"    {n:>6}  {silueta!r}")

    if por_estado:
        print("\n  COBERTURA POR ESTADO")
        for estado, c in sorted(por_estado.items()):
            total = c["total"]
            print(f"    {estado:<18} total {total:>5}   con coordenadas "
                  f"{c['cargada']:>5}   ({100 * c['cargada'] / max(total, 1):.1f}%)")

    if not pares:
        print("\n  Sin ningun valor de dos componentes: no hay rangos que medir.")
        return

    primeros = [a for a, _, _ in pares]
    segundos = [b for _, b, _ in pares]
    print("\n  RANGO DE CADA COMPONENTE  (asi se sabe el ORDEN sin asumirlo)")
    print(f"    primer  componente: min {min(primeros):>10.4f}   max {max(primeros):>10.4f}")
    print(f"    segundo componente: min {min(segundos):>10.4f}   max {max(segundos):>10.4f}")
    print("    Barranquilla y Soledad son ~10.9 N y ~-74.8 W.")
    print("    Si el PRIMERO es positivo ~10 y el SEGUNDO negativo ~-74 -> 'lat,lng'.")
    print("    Al reves -> 'lng,lat', y partirlo mal manda al tecnico al mar.")

    print("\n  DECIMALES del primer componente:",
          ", ".join(f"{d}:{n}" for d, n in
                    Counter(d for _, _, d in pares).most_common()))


def main() -> int:
    argumentos = [a for a in sys.argv[1:] if not a.startswith("--")]
    todos = "--todos" in sys.argv

    if not argumentos or (len(argumentos) < 2 and not todos):
        print(__doc__)
        return 2

    tenant = argumentos[0]
    ids = argumentos[1:]
    config = fuente_config.cargar(tenant)

    herramienta = next((h for h in config.herramientas
                        if h.nombre == "consultar_cliente"), None)
    if herramienta is None:
        print("  'consultar_cliente' no esta en el catalogo de este tenant.")
        return 1

    print(f"\n  TENANT: {tenant}")
    print("  Esto NO imprime ninguna coordenada: solo su forma y los conteos.")

    formas = Counter()
    por_estado = {}
    pares = []
    revisados = 0
    #  Por si el campo ni siquiera viene en la respuesta de la lista: es
    #  distinto de venir vacio, y la diferencia decide donde hay que pedirlo.
    sin_la_clave = 0

    def _mirar(fila):
        nonlocal revisados, sin_la_clave
        revisados += 1
        presente = "coordenadas" in fila
        if not presente:
            sin_la_clave += 1
        valor = fila.get("coordenadas") if presente else "<clave ausente>"
        formas[forma_de(valor) if presente else "<clave ausente>"] += 1

        estado = fila.get("estado")
        clave = str(estado if not isinstance(estado, dict)
                    else estado.get("nombre") or estado.get("id"))
        cuenta = por_estado.setdefault(clave, Counter())
        cuenta["total"] += 1
        cuenta["cargada" if esta_cargada(valor) else "sin_cargar"] += 1

        if esta_cargada(valor):
            par = numeros_de(valor)
            if par is not None:
                entero, _, resto = str(valor).strip().partition(",")
                decimales = len(entero.split(".")[1]) if "." in entero else 0
                pares.append((par[0], par[1], decimales))

    try:
        if todos:
            print("  Recorriendo TODOS los clientes. Puede tardar unos minutos.\n")
            offset, total = 0, None
            while True:
                filas, count = _filas(herramienta,
                                      {"limit": POR_PAGINA, "offset": offset},
                                      tenant, config.variables_tenant)
                if total is None and count is not None:
                    total = count
                    print(f"  count que reporta el proveedor: {total}")
                if not filas:
                    break
                for fila in filas:
                    if isinstance(fila, dict):
                        _mirar(fila)
                offset += POR_PAGINA
                print(f"    ... {revisados}", file=sys.stderr)
                if total is not None and offset >= total:
                    break
        else:
            for id_servicio in ids:
                filas, _ = _filas(herramienta, {"id_servicio": str(id_servicio)},
                                  tenant, config.variables_tenant)
                if not filas:
                    print(f"    {id_servicio:>8}  sin resultados")
                    continue
                fila = filas[0] if isinstance(filas[0], dict) else {}
                _mirar(fila)
                valor = fila.get("coordenadas", "<clave ausente>")
                print(f"    {id_servicio:>8}  forma {forma_de(valor)!r}"
                      f"   cargada: {'si' if esta_cargada(valor) else 'NO'}")
    except Exception as e:                                   # noqa: BLE001
        #  El TIPO y no el texto: el texto de una excepcion de red trae la
        #  URL, y la URL de esta consulta lleva el identificador del servicio.
        print(f"\n  no se pudo consultar ({type(e).__name__}). "
              f"Revisados antes de fallar: {revisados}")
        if revisados:
            _informar(formas, por_estado, pares, revisados)
        return 1

    if sin_la_clave:
        print(f"\n  OJO: en {sin_la_clave} fila(s) la clave 'coordenadas' NO "
              f"viene en la respuesta de la lista.\n       Eso NO es 'esta "
              f"vacia': significa que hay que pedirla en el detalle.")

    _informar(formas, por_estado, pares, revisados)
    print("\n  Pegale esta salida entera a quien va a escribir el parseo.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
