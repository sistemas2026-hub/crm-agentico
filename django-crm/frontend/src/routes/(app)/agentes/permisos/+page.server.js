import { error } from '@sveltejs/kit';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { leerAutonomiaGanada } from '$lib/server/v2/capacidad.js';
import { destino } from '$lib/server/v2/agentes.js';

/**
 * QUIEN PUEDE QUE  --  13/11/2026
 *
 * Una fila por accion que cambia algo, una columna por agente. Responde
 * "¿quien puede reiniciar una ONT, y lo hace solo?" sin abrir agente por
 * agente. Solo lectura; la autonomia se cambia en la pagina de cada agente.
 *
 * NOTA: es una ruta estatica bajo /agentes, asi que le gana a /agentes/[nombre]:
 * un agente que se llamara 'permisos' no tendria pagina. El editor no lo
 * impide hoy; ningun tenant lo usa.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ locals, fetch }) {
  const cfg = await destino(locals, fetch);
  if (!cfg) error(500, 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT).');
  const [resp, ganada] = await Promise.all([
    fetch(`${cfg.baseUrl}/agentes?tenant=${encodeURIComponent(cfg.tenant)}`, { headers: headersMotor() }).catch(() => null),
    leerAutonomiaGanada(locals, fetch).catch(() => ({ autonomia: null, error: 'No se pudo leer lo que hace solo cada agente.' }))
  ]);
  if (!resp?.ok) error(502, 'No se pudo leer la lista de agentes del asistente.');
  const datos = await resp.json();
  return { agentes: datos.agentes ?? [], autonomia: ganada?.autonomia ?? null, errorAutonomia: ganada?.error ?? null };
}
