import { error } from '@sveltejs/kit';
import {
  leerHiloDeOrden,
  conversacionDelCaso,
  ROLES_GESTION
} from '$lib/server/v2/hilo-del-cliente.js';
import {
  leerSeguimientoDeOrden,
  leerMaterialesDeOrden
} from '$lib/server/v2/programacion-noc.js';

/**
 * LA PÁGINA DE UNA ORDEN DE CAMPO (12/11/2026, auditoría del menú §2
 * «Inventario» y §4 ítem 6).
 *
 * No existía: «OT-188» era texto en el inventario, en el Supervisor y en el
 * ticket, y no había adónde ir. Vive en `/ordenes/[id]` y no dentro de
 * `/supervisor-noc`: la enlazan el ticket, el inventario y la ficha del
 * cliente, que no son pantallas del Supervisor.
 *
 * EL GATE: el mismo conjunto que protege las órdenes en las rutas web que ya
 * existían (`api/supervisor-noc/ordenes/[id]`, `campo/permissions.py::
 * ROLES_GESTION`). El backend vuelve a decidir por su cuenta
 * (`_obtener_orden_o_404`: otra empresa o un técnico no asignado, 404): esto no
 * reemplaza ese control, evita pedir lo que se va a negar.
 *
 * La bitácora y el material salen de las MISMAS lecturas que usa Programación;
 * el hilo (ticket, servicio, quién va, evidencias), de `campo/trabajos/<id>/
 * hilo/`. Ninguna trae el teléfono ni el GPS del cliente.
 */

/** @type {import('./$types').PageServerLoad} */
export async function load({ params, cookies, locals, fetch }) {
  if (!ROLES_GESTION.has(/** @type {any} */ (locals)?.profile?.role)) {
    error(403, 'Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede abrir una orden.');
  }
  const ctx = { cookies };
  const [hilo, seguimiento, materiales] = await Promise.all([
    leerHiloDeOrden(ctx, params.id),
    leerSeguimientoDeOrden(ctx, params.id),
    leerMaterialesDeOrden(ctx, params.id)
  ]);
  if (hilo.error) {
    error(hilo.error.status === 404 ? 404 : hilo.error.status ?? 502, hilo.error.mensaje);
  }
  return {
    orden: hilo.datos,
    seguimiento: seguimiento.datos,
    errorSeguimiento: seguimiento.error?.mensaje ?? null,
    materiales: materiales.datos,
    errorMateriales: materiales.error?.mensaje ?? null,
    // Va sin await: la conversación es un enlace más, no detiene la página.
    conversacion: conversacionDelCaso(locals, fetch, hilo.datos?.caso?.id ?? null)
  };
}
