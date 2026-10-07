/**
 * Cuadrillas — quiénes son, y qué hacen cada día.
 *
 * Server-only, por el mismo `apiRequest` que el resto del módulo. No hay un
 * segundo cliente HTTP.
 *
 * DOS PREGUNTAS DISTINTAS, DOS FUNCIONES
 *   `leerCuadrillas`  quiénes son   — cambia casi nunca
 *   `leerJornadaDeCuadrillas`  qué hacen HOY — cambia cada mañana
 *
 * Mezclarlas haría que armar el día pareciera editar la cuadrilla, y es justo
 * lo contrario: la cuadrilla sigue siendo la misma, lo que cambia es su labor
 * y quién la integra.
 */
import { apiRequest } from '$lib/api-helpers.js';

/**
 * Las cuadrillas de la empresa.
 *
 * El error viaja declarado y no como lista vacía: una empresa sin cuadrillas
 * todavía y una lectura que falló se dibujan distinto.
 *
 * @param {{ cookies: any }} ctx
 * @param {boolean} todas  incluir las dadas de baja
 */
export async function leerCuadrillas(ctx, todas = false) {
  try {
    const d = await apiRequest(
      `/campo/cuadrillas/${todas ? '?todas=1' : ''}`, {}, ctx
    );
    return { cuadrillas: d?.cuadrillas ?? [], error: false };
  } catch {
    return { cuadrillas: [], error: true };
  }
}

/** @param {{ cookies: any }} ctx @param {Record<string, any>} cuerpo */
export async function crearCuadrilla(ctx, cuerpo) {
  return apiRequest('/campo/cuadrillas/', { method: 'POST', body: cuerpo }, ctx);
}

/** @param {{ cookies: any }} ctx @param {string} id @param {Record<string, any>} cuerpo */
export async function editarCuadrilla(ctx, id, cuerpo) {
  return apiRequest(`/campo/cuadrillas/${id}/`, { method: 'PATCH', body: cuerpo }, ctx);
}

/**
 * Lo que cada cuadrilla hace ESE día.
 *
 * Exige la fecha: «la jornada» sin día no significa nada, igual que en
 * programación. Por eso la pantalla abre con una fecha y nunca con «todo».
 *
 * @param {{ cookies: any }} ctx
 * @param {string} dia  YYYY-MM-DD
 */
export async function leerJornadaDeCuadrillas(ctx, dia) {
  try {
    const d = await apiRequest(
      `/campo/cuadrillas/jornada/?fecha=${encodeURIComponent(dia)}`, {}, ctx
    );
    return { jornadas: d?.jornadas ?? [], error: false };
  } catch {
    return { jornadas: [], error: true };
  }
}

/**
 * El historial: qué hizo cada cuadrilla —o cada persona— entre dos fechas.
 *
 * Contesta otra pregunta que `leerJornadaDeCuadrillas`, que devuelve un día
 * para armar mañana. Esto contesta «quién estuvo con quién, y qué día»: el
 * dato siempre estuvo completo y lo que faltaba era poder leerlo junto en vez
 * de ir cambiando la fecha de a un día.
 *
 * `cuadrilla` y `profile` son opcionales y se excluyen en la pantalla, no acá:
 * el backend acepta los dos a la vez y devuelve la intersección, que es un
 * resultado válido aunque la pantalla no lo ofrezca.
 *
 * @param {{ cookies: any }} ctx
 * @param {{ desde: string, hasta: string, cuadrilla?: string, profile?: string }} filtros
 */
export async function leerHistorialDeCuadrillas(ctx, filtros) {
  const q = new URLSearchParams({ desde: filtros.desde, hasta: filtros.hasta });
  if (filtros.cuadrilla) q.set('cuadrilla', filtros.cuadrilla);
  if (filtros.profile) q.set('profile', filtros.profile);
  try {
    const d = await apiRequest(`/campo/cuadrillas/jornada/?${q}`, {}, ctx);
    return { jornadas: d?.jornadas ?? [], error: false, motivo: '' };
  } catch (e) {
    // El motivo viaja: un rango demasiado largo se arregla acortándolo, y sin
    // el mensaje la pantalla solo podría decir «no se pudo».
    return {
      jornadas: [],
      error: true,
      motivo: e?.body?.detail || e?.detail || ''
    };
  }
}

/**
 * Arma (o reescribe) el día de una cuadrilla.
 *
 * Es idempotente por cuadrilla y fecha: mandarlo dos veces deja lo mismo que
 * mandarlo una. Armar el día se corrige varias veces antes de que empiece.
 *
 * @param {{ cookies: any }} ctx
 * @param {Record<string, any>} cuerpo
 */
export async function armarJornada(ctx, cuerpo) {
  return apiRequest(
    '/campo/cuadrillas/jornada/', { method: 'POST', body: cuerpo }, ctx
  );
}

/**
 * Las localidades REALES, para mapearlas a zonas sin escribirlas a mano.
 *
 * Vive en el motor —`TenantConfig.localidades`— y no en el CRM, porque la
 * arma `nucleo/herramientas/localidades.py` recorriendo el catálogo completo
 * de clientes del proveedor. Su propia documentación lo dice: «nunca la
 * escribe una persona».
 *
 * POR QUÉ IMPORTA QUE NO SE ESCRIBAN
 * El nombre de un barrio llega del proveedor con variantes, y ese módulo
 * elige la más común. Un intento de «mejorarlo» colapsando `SOLEDAD
 * ATLANTICO` devolvió `SOLEDA` —un typo de tres clientes— y la moda ya los
 * descarta sola: 2.328 `SOLEDAD` contra un puñado de variantes. Ofrecer la
 * lista en vez de un campo de texto es heredar esa lección en vez de
 * repetir el error.
 *
 * Las `zonas` que trae cada localidad son de RED (corte de facturación), no
 * operativas: sirven como referencia al mapear, nunca como la zona de una
 * cuadrilla.
 *
 * @param {any} locals
 * @param {typeof globalThis.fetch} fetch
 * @returns {Promise<{ localidades: any[], actualizado_en: string | null, error: boolean }>}
 */
export async function leerLocalidades(locals, fetch) {
  const { destinoDelAsistente } = await import('./tenant.js');
  const { headersMotor } = await import('./motor-headers.js');
  const cfg = await destinoDelAsistente(locals, fetch);
  if (!cfg) return { localidades: [], actualizado_en: null, error: true };
  try {
    const resp = await fetch(
      `${cfg.baseUrl}/configuracion/planes-venta?tenant=${encodeURIComponent(cfg.tenant)}`,
      { headers: headersMotor() }
    );
    if (!resp.ok) return { localidades: [], actualizado_en: null, error: true };
    const d = await resp.json();
    return {
      localidades: d?.localidades ?? [],
      actualizado_en: d?.localidades_actualizado_en ?? null,
      error: false
    };
  } catch {
    return { localidades: [], actualizado_en: null, error: true };
  }
}

/** @param {{ cookies: any }} ctx */
export async function leerZonas(ctx) {
  try {
    const d = await apiRequest('/campo/zonas/', {}, ctx);
    return { zonas: d?.zonas ?? [], error: false };
  } catch {
    return { zonas: [], error: true };
  }
}

/** @param {{ cookies: any }} ctx @param {Record<string, any>} cuerpo */
export async function crearZona(ctx, cuerpo) {
  return apiRequest('/campo/zonas/', { method: 'POST', body: cuerpo }, ctx);
}

/**
 * Reemplaza ENTERO el mapeo de una zona.
 *
 * Se manda la lista completa de localidades, no un delta: la pantalla tiene
 * el estado entero y mandar «agregá esta, sacá aquella» obligaría a las dos
 * puntas a estar de acuerdo sobre qué había antes.
 *
 * @param {{ cookies: any }} ctx @param {string} id @param {string[]} localidades
 */
export async function mapearZona(ctx, id, localidades) {
  return apiRequest(
    `/campo/zonas/${id}/localidades/`,
    { method: 'PUT', body: { localidades } },
    ctx
  );
}

/**
 * La jornada PROPUESTA de un día. No escribe nada.
 *
 * @param {{ cookies: any }} ctx @param {string} dia
 */
export async function proponerReparto(ctx, dia) {
  try {
    const d = await apiRequest(
      `/campo/cuadrillas/reparto/?fecha=${encodeURIComponent(dia)}`, {}, ctx
    );
    return { propuesta: d, error: false, motivo: '' };
  } catch (e) {
    return {
      propuesta: null,
      error: true,
      motivo: e?.body?.detail || e?.detail || ''
    };
  }
}

/**
 * Publica la propuesta: crea las asignaciones de verdad.
 *
 * Se manda lo que la pantalla MOSTRÓ, no una fecha para recalcular. Entre
 * mirar y publicar pueden entrar órdenes nuevas —a las 3 de la mañana entran
 * tickets igual— y se publicaría algo que nadie revisó.
 *
 * @param {{ cookies: any }} ctx
 * @param {{ jornada: string, ordenes: string[] }[]} asignaciones
 */
export async function publicarReparto(ctx, asignaciones) {
  return apiRequest(
    '/campo/cuadrillas/reparto/',
    { method: 'POST', body: { asignaciones } },
    ctx
  );
}
