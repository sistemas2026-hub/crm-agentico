import { error, fail } from '@sveltejs/kit';
import { headersMotor } from '$lib/server/v2/motor-headers.js';
import { leerAutonomiaGanada } from '$lib/server/v2/capacidad.js';
import { accionesDeAutonomia } from '$lib/server/v2/acciones-autonomia.js';
import {
  destino, leerBitacora, leerDesempeno, leerHistorial, leerHuecosPorRol, pausarAgente, restaurarAgente
} from '$lib/server/v2/agentes.js';

/**
 * LA PAGINA DE UN AGENTE  --  13/11/2026
 *
 * Todo lo que la tarjeta de /agentes amontonaba (herramientas, lo que recibe,
 * autonomia) mas lo que no tenia: como le va, que cambio en el mundo real,
 * sus versiones, y pausarlo. Cada lectura es independiente y NUNCA tumba la
 * pagina: si la bitacora no responde, se dice eso y lo demas se ve igual.
 * La unica que si manda es la del agente: sin el no hay pagina (404).
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ params, locals, fetch }) {
  const nombre = params.nombre;
  const cfg = await destino(locals, fetch);
  if (!cfg) error(500, 'Asistente no configurado (falta PRIVATE_ASISTENTE_URL/TENANT).');

  const q = `tenant=${encodeURIComponent(cfg.tenant)}`;
  const [respAgentes, catalogo, ganada, desempeno, bitacora, historial, huecosPorRol] = await Promise.all([
    fetch(`${cfg.baseUrl}/agentes?${q}`, { headers: headersMotor() }).catch(() => null),
    fetch(`${cfg.baseUrl}/agentes/catalogo?${q}`, { headers: headersMotor() })
      .then((r) => (r.ok ? r.json() : null)).catch(() => null),
    leerAutonomiaGanada(locals, fetch).catch(() => ({ autonomia: null, error: 'No se pudo leer lo que hace solo cada agente.' })),
    leerDesempeno(cfg, fetch, 30),
    leerBitacora(cfg, fetch, nombre, 30),
    leerHistorial(cfg, fetch, nombre),
    leerHuecosPorRol(cfg, fetch, 14)
  ]);

  if (!respAgentes?.ok) error(502, 'No se pudo leer la lista de agentes del asistente.');
  const datos = await respAgentes.json();
  const agente = (datos.agentes ?? []).find((/** @type {any} */ a) => a.nombre === nombre);
  if (!agente) error(404, 'Ese agente no existe.');

  return {
    agente,
    catalogo: catalogo?.herramientas ?? [],
    motivosEscalada: catalogo?.motivos_escalada ?? [],
    // Las respuestas del motor ENTERAS y sin renombrar (CLAUDE.md §6).
    autonomia: ganada?.autonomia ?? null,
    errorAutonomia: ganada?.error ?? null,
    desempeno: desempeno ? (desempeno.agentes?.[nombre] ?? { sin_conversaciones: true }) : null,
    dias: desempeno?.dias ?? 30,
    bitacora: bitacora ? bitacora.acciones ?? [] : null,
    historial: historial ? historial.cambios ?? [] : null,
    huecos: huecosPorRol[nombre] ?? [],
    esAdmin: locals.profile?.role === 'ADMIN'
  };
}

/** @param {any} locals */
const soloAdmin = (locals) => locals.profile?.role === 'ADMIN';

/** @type {import('./$types').Actions} */
export const actions = {
  ...accionesDeAutonomia,

  async pausar({ params, locals, fetch }) {
    if (!soloAdmin(locals)) return fail(403, { pausa: { error: 'Solo un administrador puede pausar un agente.' } });
    const r = await pausarAgente(await destino(locals, fetch), fetch, params.nombre, true);
    if (!r.ok) return fail(r.status === 400 ? 400 : 502, { pausa: { error: r.error } });
    return { pausa: { ok: 'pausado' } };
  },

  async reanudar({ params, locals, fetch }) {
    if (!soloAdmin(locals)) return fail(403, { pausa: { error: 'Solo un administrador puede reanudar un agente.' } });
    const r = await pausarAgente(await destino(locals, fetch), fetch, params.nombre, false);
    if (!r.ok) return fail(r.status === 400 ? 400 : 502, { pausa: { error: r.error } });
    return { pausa: { ok: 'reanudado' } };
  },

  async restaurar({ params, locals, fetch, request }) {
    if (!soloAdmin(locals)) return fail(403, { restaurar: { error: 'Solo un administrador puede restaurar una versión.' } });
    const form = await request.formData();
    const version = Number(form.get('version'));
    if (!Number.isInteger(version) || version < 1) return fail(400, { restaurar: { error: 'Esa versión no se reconoce.' } });
    if (form.get('confirmo') !== 'si') return fail(400, { restaurar: { version, error: 'Confirmá que querés volver a esa versión.' } });
    const r = await restaurarAgente(await destino(locals, fetch), fetch, params.nombre, version);
    if (!r.ok) return fail(r.status === 404 || r.status === 400 ? r.status : 502, { restaurar: { version, error: r.error } });
    return { restaurar: { version, ok: true } };
  }
};
