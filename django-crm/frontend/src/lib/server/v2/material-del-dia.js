/**
 * El material del día (28/10/2026): `campo/material_del_dia.py`, para
 * Programación. SPEC/objetivos/material-del-dia.md.
 */
import { apiRequest } from '$lib/api-helpers.js';

/**
 * La propuesta de un día. Solo lee.
 * @param {{ cookies: any }} ctx
 * @param {string} dia AAAA-MM-DD
 * @returns {Promise<{ material: any, error: boolean }>}
 */
export async function leerMaterialDelDia(ctx, dia) {
  try {
    const d = await apiRequest(`/campo/material-del-dia/?fecha=${encodeURIComponent(dia)}`, {}, ctx);
    return { material: d, error: false };
  } catch {
    return { material: null, error: true };
  }
}

/**
 * Qué kit lleva cada labor y de qué bodega carga cada cuadrilla.
 * @param {{ cookies: any }} ctx
 * @returns {Promise<{ configuracion: any, error: boolean }>}
 */
export async function leerConfiguracionDeMaterial(ctx) {
  try {
    const d = await apiRequest('/campo/material-del-dia/configuracion/', {}, ctx);
    return { configuracion: d, error: false };
  } catch {
    return { configuracion: null, error: true };
  }
}

/**
 * Cambia lo que viene: `{ kits: {labor: id|null}, bodegas: {cuadrilla: id|null} }`.
 * @param {{ cookies: any }} ctx
 * @param {{ kits: Record<string, string|null>, bodegas: Record<string, string|null> }} cuerpo
 */
export async function guardarConfiguracionDeMaterial(ctx, cuerpo) {
  return apiRequest('/campo/material-del-dia/configuracion/', { method: 'PUT', body: cuerpo }, ctx);
}
