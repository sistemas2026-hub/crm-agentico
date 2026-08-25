# -*- coding: utf-8 -*-
"""
================================================================================
 SINCRONIZAR tenant.config.yaml CON LA BASE  (los dos sentidos)
================================================================================

El YAML es la fuente que se versiona en git; la base es de donde LEE el sistema
en ejecucion. Este comando lleva uno al otro.

Se guarda en la base, y no se lee del disco en caliente, por dos razones:
cambiar la configuracion no debe exigir redeploy, y varios procesos (API, worker
de ingesta, cron de informes) tienen que ver exactamente la MISMA version.

Nunca se carga sin validar: un YAML con un rol mal escrito o un filtro que la
API ignora se rechaza aqui, no en produccion con un cliente adelante.

'config_version' sube en cada carga efectiva. Queda en evaluation_runs para
poder decir "esta corrida se hizo con la config v3", y no adivinarlo despues.

POR QUE EL VIAJE DE VUELTA  (--exportar)
----------------------------------------
Los roles ya no se editan solo aca: el cliente crea y modifica sus agentes
desde la interfaz, y eso escribe en la base (nucleo/config/editor.py). El
archivo del repositorio no se entera. Sin un camino de vuelta pasan dos cosas,
las dos malas:

  - cargar el YAML encima BORRA los agentes que creo el cliente, sin aviso;
  - no hay forma de revisar en git que cambio, ni de reconstruir el tenant sin
    devolverlo a como estaba el dia del alta.

'--exportar' baja la configuracion vigente al YAML, y la carga se NIEGA a pisar
roles que solo existen en la base salvo que se le pase '--forzar'. El archivo
deja de ser una foto vieja y vuelve a ser el respaldo legible que dice ser.

Se conservan los comentarios. No es cosmetico: en tenants/ hay 133 lineas de
notas de verificacion en vivo, motivos de cada exclusion y advertencias, que
son informacion de produccion. Por eso la exportacion FUSIONA sobre el archivo
existente con ruamel.yaml en modo round-trip, en vez de volcarlo de cero.

Uso
---
    py -3.13 cli/cargar_config.py tenants/rapilink.config.yaml
    py -3.13 cli/cargar_config.py tenants/rapilink.config.yaml --forzar
    py -3.13 cli/cargar_config.py --todos
    py -3.13 cli/cargar_config.py --exportar rapilink
    py -3.13 cli/cargar_config.py --ver rapilink
================================================================================
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import date, datetime
from io import StringIO
from pathlib import Path

import yaml
from dotenv import load_dotenv
from ruamel.yaml import YAML

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from nucleo.config import TenantConfig, cargar_config   # noqa: E402
from nucleo.config.editor import SECCIONES_EDITABLES    # noqa: E402
from nucleo.persistencia.conexion import dsn            # noqa: E402

# override=False, y NO es un detalle: con True, el .env PISABA las variables
# que ya trae el entorno. Dentro de un contenedor eso significa que un .env
# viejo horneado en la imagen manda mas que la configuracion del despliegue
# -- el 24/08/2026 hizo que toda carga de config corriera contra la base
# local aunque el servicio apuntara a la de produccion, en silencio y
# reportando exito. La precedencia correcta es la de siempre: lo que el
# entorno declara explicitamente gana; el archivo solo rellena lo que falta,
# que es justo lo que hace falta al correrlo a mano en una maquina.
load_dotenv(RAIZ / ".env", override=False)

_yaml_rt = YAML(typ="rt")
_yaml_rt.preserve_quotes = True
_yaml_rt.width = 100
# Mismo estilo que ya usan los archivos escritos a mano: el guion de una lista
# va indentado 2 espacios respecto de su clave padre, no pegado a la izquierda.
_yaml_rt.indent(mapping=2, sequence=4, offset=2)


def _conectar():
    # Se importa aca y no arriba a proposito: 'tests/test_editor_config.py'
    # reusa _fusionar/_yaml_rt de este modulo y se documenta como una guarda
    # que corre SIN BASE. Con el import al tope, una maquina sin el driver
    # instalado no podia correr el test aunque no fuera a conectarse a nada.
    import psycopg
    return psycopg.connect(dsn(), connect_timeout=40)


def _organizacion(cur, slug: str, org_id: str | None = None) -> str:
    """
    Resuelve slug -> organization_id.

    El slug no existe en public.organization: esa tabla es del CRM y solo tiene
    'name'. El vinculo vive en asistente.tenant_config.slug, y esta funcion es
    la que lo establece la primera vez.

    Tres caminos, en orden. El ultimo falla ruidosamente a proposito: vincular
    la configuracion a la empresa equivocada mezcla los datos de dos ISP, y es
    un error que nadie nota hasta que es tarde.
    """
    cur.execute("select organization_id from asistente.tenant_config where slug = %s",
                (slug,))
    fila = cur.fetchone()
    if fila:
        return fila[0]                            # ya vinculado

    if org_id:
        cur.execute("select id from public.organization where id = %s", (org_id,))
        if not cur.fetchone():
            raise SystemExit(f"No existe public.organization con id '{org_id}'.")
        return org_id

    cur.execute("select id, name from public.organization order by created_at")
    orgs = cur.fetchall()
    if len(orgs) == 1:
        org, nombre = orgs[0]
        print(f"    vinculando '{slug}' a la unica organizacion del CRM: {nombre}")
        return org
    if not orgs:
        raise SystemExit(
            f"El CRM no tiene ninguna organizacion todavia.\n"
            f"Crearla primero desde el CRM: el asistente no inventa "
            f"organizaciones, esa tabla la mantiene django-crm.")
    listado = "\n".join(f"      {i}  {n}" for i, n in orgs)
    raise SystemExit(
        f"Hay {len(orgs)} organizaciones en el CRM y '{slug}' no esta vinculado "
        f"a ninguna. Indicar cual:\n\n"
        f"      py -3.13 cli/cargar_config.py tenants/{slug}.config.yaml --org-id <id>\n\n"
        f"{listado}")


# Cada seccion que el editor de la interfaz puede escribir, sacada de las
# funciones _mutar_* de nucleo/config/editor.py. Si se agrega una alla, va
# aca: lo que el editor toca y esta lista no cubre, se pisa en silencio.
#
# 'herramientas' entra por _mutar_plazo_visita_tecnica, que edita
# fechas_automaticas de una herramienta puntual -- no es solo catalogo.
#  Se importa de nucleo/config/editor.py en vez de repetirla aca. Estaba
#  escrita a mano, con un comentario que pedia acordarse de actualizarla cada
#  vez que el editor aprendiera a escribir una seccion nueva -- y no se
#  actualizo: 'planes_venta', 'localidades', 'variables_tenant' y 'manual'
#  quedaron fuera. La guarda daba por bueno un cambio que habria borrado 6
#  planes curados y 128 localidades sincronizadas sin avisar (medido el
#  23/08/2026). Ahora la lista vive junto a los mutadores que la vuelven
#  necesaria, y esto la lee.
SECCIONES_QUE_EDITA_LA_INTERFAZ = SECCIONES_EDITABLES


def _hojas(valor, prefijo=""):
    """
    Aplana a {'a.b.c': valor} para comparar VALOR por VALOR.

    Las LISTAS tambien se recorren, no se tratan como un valor unico: sin eso
    'herramientas' -que es una lista de 19 diccionarios- se reportaba entera
    como una sola diferencia de 41 KB. Un aviso que nadie puede leer empuja a
    usar --forzar sin mirar, que es justo el habito que esta guarda existe
    para evitar.

    Se indexa por 'nombre' cuando el elemento lo trae: reordenar herramientas
    en el YAML no deberia aparecer como que cambiaron todas.
    """
    if isinstance(valor, dict):
        salida = {}
        for clave, sub in valor.items():
            salida.update(_hojas(sub, f"{prefijo}.{clave}" if prefijo else str(clave)))
        return salida
    if isinstance(valor, list):
        # Una lista de VALORES SIMPLES se compara como conjunto, no por
        # posicion. 'puede_consultar' o 'campos_permitidos' son permisos: lo
        # que importa es si una herramienta esta o no esta, no en que lugar
        # de la lista quedo. Indexando por posicion, insertar un elemento al
        # principio corre todos los demas y la guarda reporta cada posicion
        # siguiente como si hubiera cambiado -- 15 avisos falsos de 31 en la
        # comparacion real del 23/08/2026, que es como se deja de leer una
        # guarda. Se ordena para que el conjunto tenga una representacion
        # estable.
        if valor and all(not isinstance(v, (dict, list)) for v in valor):
            return {prefijo: sorted(valor, key=str)}
        salida = {}
        for i, sub in enumerate(valor):
            etiqueta = sub["nombre"] if isinstance(sub, dict) and sub.get("nombre") else i
            salida.update(_hojas(sub, f"{prefijo}[{etiqueta}]"))
        return salida
    return {prefijo: valor}


def _corto(valor, tope: int = 70) -> str:
    """El valor para mostrar en un aviso, acotado. Un prompt de 1.400
    caracteres impreso entero tapa las otras diferencias de la lista."""
    texto = repr(valor)
    return texto if len(texto) <= tope else texto[:tope - 1] + "…"


def _lo_que_pisaria(guardado: dict, nuevo: dict) -> list[str]:
    """
    Que se PERDERIA de la base al cargar 'nuevo' encima.

    Compara VALOR por valor, no presencia de claves. Esa distincion costo una
    caida: al empujar el YAML se comprobo que ninguna clave de la base faltara
    en el archivo -- y ninguna faltaba-- pero 'canales.whatsapp.activo' estaba
    en las dos con valores distintos (true en la base, false en el archivo).
    El canal quedo apagado y el webhook devolvio 401 a Meta hasta que alguien
    lo noto.

    Un valor que esta en el archivo y no en la base es una incorporacion, no
    una perdida, y no se reporta: lo que hay que frenar es borrar el trabajo
    de otro, no agregar el propio.
    """
    lineas: list[str] = []

    roles_g = guardado.get("roles") or {}
    roles_n = nuevo.get("roles") or {}
    for nombre in roles_g:
        if nombre not in roles_n:
            lineas.append(f"el rol '{nombre}' esta en la base y no en el archivo: "
                          f"se BORRARIA")

    for seccion in SECCIONES_QUE_EDITA_LA_INTERFAZ:
        # Un campo sincronizado no se puede perder: 'cargar' le devuelve el
        # valor de la base al archivo antes de escribir (ver alla). Avisar de
        # una perdida imposible es la falsa alarma mas cara de todas, porque
        # aparece en CADA corrida y ensena a saltear el aviso entero.
        if seccion in TenantConfig.SINCRONIZADOS:
            continue

        en_base = guardado.get(seccion)
        en_archivo = nuevo.get(seccion)

        # UNA SECCION QUE SE VACIA ENTERA no la ve la comparacion hoja por
        # hoja de mas abajo: esa recorre las rutas de la base y solo avisa si
        # la MISMA ruta existe en el archivo. Una lista vacia no produce
        # ninguna ruta, asi que 'la base tiene 6 planes y el archivo ninguno'
        # no coincidia con nada y pasaba en silencio.
        #
        # Es el caso mas destructivo de todos y era el unico invisible.
        # Medido el 23/08/2026: la base tenia 6 planes de venta curados y 128
        # localidades sincronizadas que el archivo no trae, y la guarda daba
        # el visto bueno.
        # 'roles' ya lo cubre el bucle de arriba, rol por rol y con nombre
        # propio. Sin esta linea, un archivo sin roles los lista uno por uno
        # Y ADEMAS agrega un "roles: se BORRARIA entero" que dice lo mismo.
        if en_base and not en_archivo and seccion != "roles":
            cuantos = len(en_base) if isinstance(en_base, (list, dict)) else 1
            lineas.append(
                f"{seccion}: la base tiene {cuantos} y el archivo lo deja "
                f"VACIO -- se BORRARIA entero")
            continue

        viejo = _hojas(en_base, seccion)
        nuevo_plano = _hojas(en_archivo, seccion)
        for ruta, valor in viejo.items():
            # Solo lo que ya existe en el archivo con OTRO valor. Una clave que
            # el archivo no trae la completa el esquema con su default, y
            # reportarla seria ruido en cada corrida.
            if ruta not in nuevo_plano or nuevo_plano[ruta] == valor:
                continue

            # En una lista de permisos lo unico que se PIERDE es lo que la base
            # tiene y el archivo no. Si el archivo solo agrega -- el caso normal
            # cuando alguien conecta una herramienta nueva -- no hay nada que
            # frenar, y decir "se PISARIA" ahi es exactamente como se entrena a
            # la gente a correr --forzar sin leer.
            if isinstance(valor, list) and isinstance(nuevo_plano[ruta], list):
                se_pierden = [v for v in valor if v not in nuevo_plano[ruta]]
                if not se_pierden:
                    continue
                lineas.append(f"{ruta}: el archivo NO trae {_corto(se_pierden)} "
                              f"-- se PERDERIA")
                continue

            lineas.append(f"{ruta}: la base dice {_corto(valor)} y el "
                          f"archivo {_corto(nuevo_plano[ruta])} -- se PISARIA")

    ov_g = ((guardado.get("llm") or {}).get("overrides") or {})
    ov_n = ((nuevo.get("llm") or {}).get("overrides") or {})
    for clave, valor in ov_g.items():
        if clave.startswith("rol:") and ov_n.get(clave) != valor:
            lineas.append(f"llm.overrides['{clave}'] = '{valor}' se perderia")

    return lineas


def cargar(ruta: Path, org_id: str | None = None, forzar: bool = False) -> None:
    cfg = cargar_config(ruta)                     # valida o revienta
    slug = cfg.identidad.slug
    datos = cfg.model_dump(mode="json")

    with _conectar() as con, con.cursor() as cur:
        org = _organizacion(cur, slug, org_id)

        # Si el contenido no cambio, no se sube la version: asi 'config_version'
        # cuenta cambios reales y no ejecuciones del comando.
        cur.execute("""select config, config_version from asistente.tenant_config
                       where organization_id = %s""", (org,))
        actual = cur.fetchone()

        # Un campo SINCRONIZADO es propiedad de la base en las DOS direcciones:
        # 'exportar' no lo baja al archivo, y por lo tanto el archivo nunca
        # tiene con que pisarlo. Sin esto, declararlo sincronizado lo dejaba
        # peor que antes: fuera del archivo Y borrado por cualquier carga, que
        # es como se pierden 128 localidades que costaron 25 paginas de API.
        #
        # Se restaura lo que ya hay en la base ANTES de comparar, para que la
        # comparacion de "sin cambios" no dispare por un campo que ni siquiera
        # se va a tocar.
        if actual:
            for campo in TenantConfig.SINCRONIZADOS:
                if campo in (actual[0] or {}):
                    datos[campo] = actual[0][campo]

        if actual and actual[0] == datos:
            print(f"[=] {slug}: sin cambios (v{actual[1]})")
            return

        # El archivo ya no es el unico que escribe roles. Antes de pisar la
        # base hay que saber si lo que hay ahi lo puso una persona desde la
        # interfaz, porque eso no esta en git y no se recupera.
        if actual and not forzar:
            perdidas = _lo_que_pisaria(actual[0], datos)
            if perdidas:
                raise SystemExit(
                    f"'{slug}': la base (v{actual[1]}) tiene roles que este "
                    f"archivo no trae.\n\n  - " + "\n  - ".join(perdidas) +
                    f"\n\nLos roles se editan desde la interfaz y se guardan en "
                    f"la base, no aqui. Bajarlos al archivo primero:\n\n"
                    f"      py -3.13 cli/cargar_config.py --exportar {slug}\n\n"
                    f"o pisarlos a proposito, si es lo que se quiere:\n\n"
                    f"      py -3.13 cli/cargar_config.py {ruta} --forzar")

        if actual:
            cur.execute("""update asistente.tenant_config
                           set config = %s,
                               config_version = config_version + 1,
                               actualizado_en = now()
                           where organization_id = %s
                           returning config_version""",
                        (json.dumps(datos), org))
            version = cur.fetchone()[0]
            print(f"[^] {slug}: actualizada a v{version}")
        else:
            cur.execute("""insert into asistente.tenant_config
                             (organization_id, slug, config, config_version)
                           values (%s, %s, %s, 1)""",
                        (org, slug, json.dumps(datos)))
            print(f"[+] {slug}: cargada v1")
        con.commit()

    print(f"    roles: {', '.join(cfg.roles)}")
    print(f"    herramientas: {len(cfg.herramientas)}   modelo: "
          f"{cfg.llm.modelo_por_defecto}")


# =============================================================================
#  EXPORTAR  -  de la base al archivo, sin perder los comentarios
# =============================================================================

def _nombrados(x) -> bool:
    """Una lista de objetos identificables por 'nombre' (herramientas)."""
    return bool(x) and all(isinstance(i, dict) and "nombre" in i for i in x)


def _como_json(valor):
    """
    El valor del YAML expresado como lo expresa model_dump(mode='json'), para
    poder compararlos.

    Hace falta por las fechas: 'verificado_el: 2026-08-07' se carga como un
    date y la base lo guarda como la cadena '2026-08-07'. Sin esta conversion
    parecen distintos, y cada exportacion reescribiria la fecha entrecomillada
    -- catorce lineas de diff que no cambian nada.
    """
    return valor.isoformat() if isinstance(valor, (date, datetime)) else valor


def _fusionar(destino, completo, minimo):
    """
    Copia lo que dice la base sobre 'destino' (el documento round-trip, con
    sus comentarios), en el sitio.

    Llegan DOS versiones de lo mismo y la diferencia es la que evita que el
    archivo se degrade a cada exportacion:

      completo  el volcado entero, con cada campo del esquema
      minimo    solo lo que difiere de su valor por defecto (exclude_defaults)

    Se BORRA lo que no este en 'completo' (desaparecio de verdad) y se AGREGA
    solo lo que este en 'minimo'. Sin esa distincion, la primera exportacion
    escribiria 170 lineas de 'logo_url:', 'orientado_a: colaborador' y
    'reranking_activo: false' que el archivo omitia a proposito -- fiel, pero
    con el cambio real enterrado en el ruido.

    Lo que decide que comentarios y que estilo sobreviven:

      - Un valor que no cambio devuelve el nodo original, no una copia. Asi los
        bloques '>' y '|' conservan su corte de linea y sus comillas, en vez de
        reescribirse con el ancho de este volcador.
      - Los diccionarios se recorren clave por clave, asi que el comentario
        sobre 'campos_permitidos.consultar_cliente' sigue pegado a esa clave
        aunque cambie la lista de al lado.
      - Las listas de objetos con 'nombre' (herramientas) se emparejan por ese
        nombre y no por posicion.

    Limite conocido: los comentarios DENTRO de una lista se indexan por
    posicion, asi que quitar o agregar un elemento en medio desalinea los que
    vienen despues. No pasa hoy -- desde la interfaz se editan roles, no
    herramientas -- pero si un dia pasa, es lo primero que hay que mirar en el
    diff.
    """
    if not isinstance(completo, (dict, list)) and _como_json(destino) == completo:
        return destino

    # VACIAR EN EL SITIO ROMPE EL ARCHIVO. Si lo que hay en la base es una
    # coleccion vacia y el archivo tenia contenido, no se vacia el nodo
    # original: se devuelve uno nuevo. Vaciar un CommentedMap/CommentedSeq
    # deja sus comentarios sin nada a que colgarse, y ruamel emite YAML
    # invalido -- el valor cae en la columna 0 y la clave siguiente termina
    # pegada en la misma linea.
    #
    # Encontrado el 23/08/2026 con 'areas' e 'identidad_externa': dos campos
    # que estaban en el YAML y todavia no en la base. --exportar quedo
    # inutilizable (fallo cerrado, sin escribir), y sin el no habia camino
    # base -> archivo justo cuando hacia falta para fusionar el trabajo de
    # dos personas.
    #
    # Se pierden los comentarios de ADENTRO del bloque, no el encabezado que
    # cuelga de la clave. Es la unica salida: el bloque ya no tiene contenido
    # al que referirse.
    if isinstance(completo, (dict, list)) and not completo and destino:
        return type(completo)()

    if isinstance(destino, dict) and isinstance(completo, dict):
        minimo = minimo if isinstance(minimo, dict) else {}
        for clave in [k for k in destino if k not in completo]:
            del destino[clave]
        for clave, valor in completo.items():
            if clave in destino:
                # Un bloque con contenido que en la base quedo VACIO o NULO se
                # borra y se vuelve a poner, en vez de asignarle el valor
                # nuevo encima. Los comentarios de ese bloque estan anclados a
                # la clave en el mapa padre: si solo se pisa el valor, quedan
                # colgados de algo que ya no existe y ruamel emite YAML
                # invalido -- la clave siguiente termina pegada en la misma
                # linea. Borrar la clave se lleva esa metadata con ella.
                #
                # Visto el 23/08/2026 con 'identidad_externa', que estaba en
                # el archivo y todavia no en la base.
                if (not valor and isinstance(destino[clave], (dict, list))
                        and destino[clave]):
                    del destino[clave]
                    destino[clave] = valor
                    continue
                fusionado = _fusionar(destino[clave], valor, minimo.get(clave))
                if fusionado is not destino[clave]:
                    destino[clave] = fusionado
            elif clave in minimo:
                destino[clave] = minimo[clave]
        return destino

    if isinstance(destino, list) and isinstance(completo, list):
        if _nombrados(destino) and _nombrados(completo):
            minimos = {i["nombre"]: i for i in (minimo or [])
                       if isinstance(i, dict) and "nombre" in i}
            # Si estan los mismos y en el mismo orden -- el caso normal, porque
            # las herramientas no se editan desde la interfaz -- se entra en
            # cada una sin tocar la lista. Rearmarla desprende los comentarios
            # y las lineas en blanco que separan una herramienta de la
            # siguiente, y eso saldria en el diff de cada exportacion.
            actuales = {i["nombre"]: i for i in destino}
            if [i["nombre"] for i in destino] == [i["nombre"] for i in completo]:
                for nodo, item in zip(destino, completo):
                    _fusionar(nodo, item, minimos.get(item["nombre"]))
                return destino
            destino[:] = [
                _fusionar(actuales[i["nombre"]], i, minimos.get(i["nombre"]))
                if i["nombre"] in actuales
                else minimos.get(i["nombre"], i)
                for i in completo
            ]
            return destino

        if [_como_json(v) for v in destino] == list(completo):
            return destino
        # Listas de objetos SIN 'nombre' -- las precondiciones de
        # 'evidencia_suficiente', por ejemplo. Mientras la cantidad no cambie
        # se entra en cada elemento en vez de reemplazar la lista: el
        # reemplazo descarta los nodos originales, y con ellos CUALQUIER
        # comentario anclado ahi. El que se pierde no es solo el de adentro:
        # ruamel cuelga el encabezado de la seccion siguiente del ultimo nodo
        # del bloque anterior, asi que una lista al final de una seccion se
        # lleva puesto el titulo de la que sigue. Medido: agregar
        # 'evidencia_suficiente' borraba las 7 lineas del encabezado de
        # CONVERSACIONES en cada exportacion.
        if (len(destino) == len(completo)
                and all(isinstance(d, dict) for d in destino)
                and all(isinstance(c, dict) for c in completo)):
            minimos = minimo if isinstance(minimo, list) else []
            for i, (nodo, item) in enumerate(zip(destino, completo)):
                fusionado = _fusionar(nodo, item,
                                      minimos[i] if i < len(minimos) else None)
                if fusionado is not nodo:
                    destino[i] = fusionado
            return destino

        # Se reemplaza el CONTENIDO, no el nodo: asi una lista escrita en linea
        # ([a, b, c]) sigue en linea despues de agregarle un elemento, en vez de
        # estallar en una lista de guiones que reescribe el bloque entero.
        destino[:] = completo
        return destino

    return completo


def _resumen_de_roles(antes: dict, despues: dict) -> list[str]:
    """Que le cambia al archivo. Es lo que hay que mirar en el diff, dicho en
    una linea, para no leer 650 lineas de YAML buscando la diferencia."""
    a, d = (antes.get("roles") or {}), (despues.get("roles") or {})
    lineas = [f"+ rol '{n}' (creado desde la interfaz)" for n in d if n not in a]
    lineas += [f"- rol '{n}' (ya no esta en la base)" for n in a if n not in d]
    lineas += [f"~ rol '{n}' cambio" for n in d if n in a and a[n] != d[n]]
    return lineas or ["(los roles ya coincidian; puede haber cambiado otra cosa)"]


def _escribir_atomico(ruta: Path, texto: str) -> None:
    """Temporal + replace: un fallo a mitad de escritura no deja el YAML
    corrupto, que es el archivo con el que se da de alta el tenant."""
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix=f".{ruta.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(texto)
        os.replace(tmp, ruta)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def exportar(slug: str) -> None:
    with _conectar() as con, con.cursor() as cur:
        cur.execute("""select config, config_version from asistente.tenant_config
                       where slug = %s""", (slug,))
        fila = cur.fetchone()
    if not fila or not fila[0]:
        raise SystemExit(f"'{slug}' no tiene configuracion cargada en la base.")

    guardado, version = fila
    # Se valida ANTES de escribir: si lo que hay en la base no pasa el
    # esquema, el archivo bueno no se sacrifica por copiar uno roto.
    cfg = TenantConfig(**guardado)
    datos = cfg.model_dump(mode="json")
    minimo = cfg.model_dump(mode="json", exclude_defaults=True)

    # Lo SINCRONIZADO no baja al archivo: no es configuracion que alguien
    # escribio, es la salida de un proceso que se reemplaza entera cada vez
    # que corre (ver TenantConfig.SINCRONIZADOS). Hoy 'localidades' son 128
    # localidades con sus zonas y conteos -- volcarlas al YAML meteria
    # cientos de lineas generadas por maquina en un archivo escrito a mano, y
    # cambiarian en cada sincronizacion, enterrando el cambio real en el
    # diff. Viven solo en la base, que es de donde el motor las lee.
    for campo in TenantConfig.SINCRONIZADOS:
        datos.pop(campo, None)
        minimo.pop(campo, None)

    ruta = RAIZ / "tenants" / f"{slug}.config.yaml"
    if ruta.exists():
        anterior = cargar_config(ruta).model_dump(mode="json")
        doc = _yaml_rt.load(ruta.read_text(encoding="utf-8"))
        _fusionar(doc, datos, minimo)
    else:
        anterior, doc = {}, minimo     # tenant nuevo: no hay comentarios que cuidar

    buf = StringIO()
    _yaml_rt.dump(doc, buf)
    texto = buf.getvalue()

    # El archivo tiene que releerse como EXACTAMENTE lo que hay en la base.
    # Una fusion que se coma una clave produciria un YAML valido y distinto, y
    # el error aparecería mucho despues, al reconstruir el tenant desde el.
    try:
        releido = TenantConfig(**(yaml.safe_load(texto) or {})).model_dump(mode="json")
    except Exception as e:
        raise SystemExit(f"{slug}: el archivo fusionado no valida ({e}). No se escribio.")
    # Los sincronizados se excluyeron de 'datos' mas arriba; al releer el
    # archivo vuelven con su valor por defecto, asi que hay que sacarlos de
    # los dos lados o la comparacion falla por un campo que a proposito no
    # se escribio.
    for campo in TenantConfig.SINCRONIZADOS:
        releido.pop(campo, None)
    if releido != datos:
        distintas = sorted(k for k in set(releido) | set(datos)
                           if releido.get(k) != datos.get(k))
        raise SystemExit(
            f"{slug}: la fusion no quedo fiel a la base en {distintas}. "
            f"No se escribio nada.")

    _escribir_atomico(ruta, texto)

    print(f"[v] {slug}: v{version} de la base -> {ruta.relative_to(RAIZ)}")
    for linea in _resumen_de_roles(anterior, datos):
        print(f"    {linea}")
    print(f"    Revisar con: git diff -- {ruta.relative_to(RAIZ).as_posix()}")


def ver(slug: str) -> None:
    with _conectar() as con, con.cursor() as cur:
        cur.execute("""select tc.config_version, tc.plan, tc.activo,
                              tc.actualizado_en, tc.config
                       from asistente.tenant_config tc
                       where tc.slug = %s""", (slug,))
        fila = cur.fetchone()
    if not fila:
        raise SystemExit(f"'{slug}' no tiene configuracion cargada.")
    v, plan, activo, cuando, cfg = fila
    print(f"{slug}  v{v}  plan={plan}  activo={activo}")
    print(f"  actualizada: {cuando:%Y-%m-%d %H:%M}")
    print(f"  asistente  : {cfg['persona']['nombre_asistente']}")
    print(f"  roles      : {', '.join(cfg['roles'])}")
    print(f"  modelo     : {cfg['llm']['modelo_por_defecto']}")
    print(f"  embeddings : {cfg['rag']['modelo_embeddings']} "
          f"({cfg['rag']['dimensiones']} dim)")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__.split("Uso\n---")[1].strip())

    # --org-id <uuid>: vincula un slug nuevo a una organizacion concreta del CRM.
    # Solo hace falta la primera vez, y solo si hay mas de una.
    org_id = None
    if "--org-id" in args:
        i = args.index("--org-id")
        org_id = args[i + 1]
        del args[i:i + 2]

    forzar = "--forzar" in args
    if forzar:
        args.remove("--forzar")

    if args[0] == "--ver":
        ver(args[1])
    elif args[0] == "--exportar":
        exportar(args[1])
    elif args[0] == "--todos":
        for y in sorted((RAIZ / "tenants").glob("*.config.yaml")):
            if y.name.startswith("tenant.config.example"):
                continue                          # la plantilla no es un tenant
            try:
                cargar(y, forzar=forzar)
            except SystemExit as e:
                print(f"[!] {y.name}: {e}")
    else:
        cargar(Path(args[0]), org_id, forzar=forzar)
