/**
 * Deshacer un hecho del Supervisor desde Actividad  --  12/11/2026.
 *
 * Lo no crítico ya no pide permiso antes (operaciones/tareas_delegadas.py);
 * esto es la otra mitad: revertir después, con nombre y motivo.
 *
 * UNA RUTA PROPIA y no una acción de la página por lo mismo que la lectura de
 * la actividad: una acción vuelve a correr el load entero (cinco consultas)
 * y la persona perdería el scroll y los filtros del panel.
 *
 * EL PERMISO LO DECIDE DJANGO ('EsJefeDeOperaciones'), y qué se puede deshacer
 * también ('operaciones/deshacer.py'): acá no se valida nada que allá no se
 * valide. Lo único que se hace es no mandar un motivo vacío, para no gastar
 * un viaje en algo que el backend va a rechazar.
 */
import { json } from '@sveltejs/kit';

import { deshacerHecho } from '$lib/server/v2/supervisor-noc.js';
import { mensajeDeError } from '$lib/server/v2/mensaje-de-error.js';

export async function POST({ cookies, params, request }) {
  /** @type {any} */
  let cuerpo = {};
  try {
    cuerpo = await request.json();
  } catch {
    return json({ ok: false, error: 'El pedido no se pudo leer.' }, { status: 400 });
  }
  const motivo = String(cuerpo?.motivo ?? '').trim();
  if (!motivo) {
    return json(
      { ok: false, error: 'Escribí el motivo: queda registrado con tu nombre.' },
      { status: 400 }
    );
  }
  try {
    const r = await deshacerHecho({ cookies }, params.id, motivo);
    return json({ ok: true, ...(r ?? {}) });
  } catch (e) {
    return json(
      { ok: false, error: mensajeDeError(e, 'No se pudo deshacer.') },
      { status: /** @type {any} */ (e)?.status ?? 502 }
    );
  }
}
