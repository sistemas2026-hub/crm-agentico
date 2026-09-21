# -*- coding: utf-8 -*-
"""
================================================================================
 El registro de politicas  --  quien junta los hechos y llama a la regla
================================================================================

'promesas.evaluar()' es una funcion pura: recibe hechos y decide. Aqui vive lo
otro, que es ir a buscar esos hechos.

Estan separados a proposito y no es ceremonia: la REGLA hay que poder probarla
entera sin red, y la RECOLECCION hay que poder cambiarla --otro endpoint, otro
proveedor-- sin tocar la regla.

COMO SABE EL MOTOR QUE LEER
---------------------------
No lo sabe, y no debe. La herramienta lo declara en el catalogo del tenant:

    politica:
      nombre: promesa_reactivacion
      lecturas:
        cliente:  consultar_cliente
        facturas: consultar_facturas

El nucleo busca esos nombres en el catalogo, comprueba que sean de SOLO
LECTURA, y las usa. Si falta una, o no es de lectura, la accion NO se propone
-- misma regla que la revalidacion de §3.7: una comprobacion declarada que no
puede correr nunca autoriza nada.

SI NO SE PUEDE COMPROBAR, NO SE PROPONE
---------------------------------------
Y ojo con la tentacion de "bueno, que lo decida el humano igual". Una
propuesta que llega a la pantalla ya viene con la forma de algo aprobable, y
la persona que la ve no tiene como saber que las comprobaciones no corrieron.
Proponer sin haber verificado es trasladarle a alguien una decision que se le
presenta como verificada.
"""

from __future__ import annotations

from nucleo.facturacion import promesas
from nucleo.observabilidad.registro import registrar


def _politica_promesa_reactivacion(config, tenant, argumentos, lecturas, leer,
                                   historial):
    """Reune los hechos de 'registrar promesa y reactivar' y los evalua."""
    politica = getattr(config, "promesas_pago", None)
    if politica is None or politica.faltan_valores():
        faltan = politica.faltan_valores() if politica else ["todo"]
        # Sin politica cargada no hay con que decidir. No se propone: ofrecer
        # la accion con topes que nadie definio es peor que no ofrecerla.
        return promesas.Veredicto(
            promesas.NO_SE_PUDO, "politica_sin_cargar",
            f"La empresa todavia no definio su politica de promesas "
            f"(falta: {', '.join(faltan)}).")

    # EL MODELO PROPONE CON 'id_factura', no con el cliente. Asi que la cadena
    # empieza por la factura y de ahi se saca a quien pertenece. Lo natural
    # habria sido pedir el id del cliente, pero eso obligaria al modelo a
    # decidir dos cosas en vez de una, y a nosotros a confiar en que las ata
    # bien.
    id_factura = argumentos.get("id_factura")
    if not id_factura:
        return promesas.Veredicto(promesas.NO_SE_PUDO, "sin_id_factura",
                                  "No se sabe sobre que factura es la promesa.")

    hechos: dict = {"fecha_limite": argumentos.get("fecha_limite")}

    # --- 1. la factura, para saber de quien es ------------------------------
    try:
        detalle = leer(lecturas["factura"], {"id_factura": id_factura})
    except Exception as e:
        registrar("promesas", "no se pudo leer la factura", tenant=tenant, error=e)
        detalle = None
    # El objeto 'cliente' de una factura identifica por el slug 'usuario': NO
    # trae 'id_servicio' (medido el 21/09/2026).
    usuario = ((detalle or {}).get("cliente") or {}).get("usuario") if detalle else None
    if not usuario:
        return promesas.Veredicto(promesas.NO_SE_PUDO, "sin_cliente_de_la_factura",
                                  "No se pudo saber de que cliente es la factura.")

    # --- 2. el cliente, por su slug -----------------------------------------
    try:
        respuesta = leer(lecturas["cliente"], {"usuario": usuario})
        filas = (respuesta or {}).get("results") if isinstance(respuesta, dict) else None
        hechos["cliente"] = (filas or [None])[0] if filas is not None else respuesta
    except Exception as e:
        registrar("promesas", "no se pudo leer el cliente", tenant=tenant, error=e)
        hechos["cliente"] = None

    # --- 3. sus facturas pendientes -----------------------------------------
    # Se filtra por 'cliente' (el slug), que es lo que ese listado acepta:
    # 'id_servicio' ahi esta MEDIDO como ignorado (15/09/2026) y devolveria el
    # universo entero, o sea las facturas de todo el mundo.
    try:
        respuesta = leer(lecturas["facturas"], {"cliente": usuario, "estado": 1})
        hechos["facturas"] = ((respuesta or {}).get("results")
                              if isinstance(respuesta, dict) else respuesta)
    except Exception as e:
        registrar("promesas", "no se pudieron leer las facturas",
                  tenant=tenant, error=e)
        hechos["facturas"] = None

    # --- 4. lo que registro Dexter ------------------------------------------
    # Por FACTURA, que es el dato exacto que hay. Cubre "no dos promesas sobre
    # la misma factura"; NO cubre "este cliente promete todos los meses con
    # factura nueva" -- de eso se ocupa, parcialmente, la guarda de una sola
    # factura pendiente. Y nada cubre las promesas cargadas a mano en el panel.
    #
    # La clave AUSENTE significa "no pude consultar" y termina en NO_SE_PUDO.
    # Solo se pone cuando la consulta respondio, aunque responda que no hay.
    if historial is not None:
        try:
            hechos["promesa_previa"] = historial(tenant, str(id_factura))
        except Exception as e:
            registrar("promesas", "no se pudo leer el historial de promesas",
                      tenant=tenant, error=e)

    return promesas.evaluar(hechos, politica)


#: Las politicas que la plataforma ofrece, por nombre. El tenant elige cual
#: aplica a cada herramienta; el nucleo nunca elige por el.
REGISTRO = {
    "promesa_reactivacion": _politica_promesa_reactivacion,
}


def evaluar(config, tenant: str, herramienta, argumentos: dict, *,
            leer=None, historial=None):
    """
    ¿Se puede PROPONER esta accion? Devuelve un Veredicto, o None si la
    herramienta no declara politica (que es el caso de casi todas).

    'leer' e 'historial' se inyectan para poder probar la recoleccion sin red
    y sin base.
    """
    declarada = getattr(herramienta, "politica", None)
    if declarada is None:
        return None

    regla = REGISTRO.get(declarada.nombre)
    if regla is None:
        # Declarada y desconocida: no se propone. Que el catalogo nombre una
        # politica que el nucleo no tiene es un error de despliegue, y fallar
        # abierto seria saltearse justo lo que alguien quiso poner.
        return promesas.Veredicto(
            promesas.NO_SE_PUDO, f"politica_desconocida:{declarada.nombre}",
            "La politica declarada no existe en esta version del motor.")

    por_nombre = {h.nombre: h for h in config.herramientas}
    lecturas = {}
    for rol, nombre in (declarada.lecturas or {}).items():
        lectura = por_nombre.get(nombre)
        if lectura is None:
            return promesas.Veredicto(
                promesas.NO_SE_PUDO, f"lectura_ausente:{nombre}",
                f"La politica necesita '{nombre}' y no esta en el catalogo.")
        if not lectura.solo_lectura:
            # Comprobar no puede escribir: correria un efecto antes de decidir
            # si se corre el efecto.
            return promesas.Veredicto(
                promesas.NO_SE_PUDO, f"lectura_no_es_lectura:{nombre}",
                f"'{nombre}' no es de solo lectura.")
        lecturas[rol] = lectura

    if leer is None:
        from nucleo.herramientas import http as herramientas_http

        def leer(h, a):
            return herramientas_http.ejecutar(h, a, tenant, config.variables_tenant)

    try:
        return regla(config, tenant, argumentos, lecturas, leer, historial)
    except Exception as e:
        # Nunca el cuerpo del error: puede traer datos del cliente.
        registrar("promesas", "la politica fallo", tenant=tenant,
                  politica=declarada.nombre, error=e)
        return promesas.Veredicto(promesas.NO_SE_PUDO,
                                  f"politica_fallo:{type(e).__name__}",
                                  "No se pudo evaluar la politica.")
