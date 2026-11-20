/**
 * DEVOLVER AL TÉCNICO UNA ORDEN QUE ÉL DETUVO  --  20/11/2026, OT #328
 *
 * El técnico reportó un bloqueo y la orden quedó sin salida: la app no ofrece
 * nada sobre una orden detenida (a propósito: se destraba desde la oficina) y
 * desde Programación nadie llamaba al endpoint que la saca. El backend lo
 * resuelve entero (`campo/services/bloqueos.py::resolver`): valida el retorno
 * contra la máquina de transiciones, deja el hecho en la bitácora y le avisa
 * a quien estaba esperando.
 *
 * POR QUÉ UN MÓDULO PROPIO Y NO `programacion-noc.js::resolverBloqueo`, que
 * llama al mismo endpoint: ese módulo importa `$env/dynamic/private` por
 * otras funciones suyas, y arrastrarlo a esta página rompía su prueba
 * (medido el 20/11/2026: `Cannot find module '$env/dynamic/private'`). Mismo
 * criterio que `mover-orden.js`: lo mínimo que la acción necesita.
 *
 * SIN `volver_a`: el estado al que vuelve lo guardó la fila del bloqueo al
 * abrirse. Desde acá no se elige destino.
 *
 * SIN `Idempotency-Key`: la garantía está en el servicio. Un segundo clic
 * encuentra el bloqueo ya resuelto y recibe 409, sin segundo evento ni
 * segundo aviso (la clave del aviso es el id del bloqueo).
 */
import { apiRequest } from '$lib/api-helpers.js';

/**
 * @param {{ cookies: any }} ctx
 * @param {{ orden: string, aclaracion: string }} d
 * @returns {Promise<{aviso?: boolean, estado_operativo?: string}>}
 */
export async function destrabarOrden(ctx, { orden, aclaracion }) {
  const id = encodeURIComponent(orden);
  return await apiRequest(`/campo/trabajos/${id}/bloqueo/resolver/`, {
    method: 'POST',
    // `coordinacion`: quien gestiona desde la oficina. Sale de
    // `BloqueoDeTrabajo.QUIENES`; un rol inventado el servicio lo rechaza.
    body: { que_se_hizo: aclaracion, resuelto_por_rol: 'coordinacion' }
  }, ctx);
}
