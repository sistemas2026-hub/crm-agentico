import { fail } from '@sveltejs/kit';
import {
  guardarAjustesBandeja,
  leerAjustesBandeja,
  guardarRotulosBandeja,
  leerRotulosBandeja,
  guardarReincidencia
} from '$lib/server/v2/bandeja-config.js';

/** Prefijo de los campos del formulario de rótulos: `rotulo:<clave>`. */
const PREFIJO_ROTULO = 'rotulo:';

/** @type {import('./$types').PageServerLoad} */
export async function load({ fetch, locals }) {
  const [ajustes, rotulos] = await Promise.all([
    leerAjustesBandeja(locals, fetch),
    leerRotulosBandeja(locals, fetch)
  ]);
  return {
    ajustes,
    rotulos,
    // El motor no tiene identidad propia: quien decide si esto se puede
    // editar es el CRM, mismo criterio que /settings/asistente. Esto es la
    // afordancia (esconder el boton); la accion vuelve a comprobarlo, porque
    // ocultar un boton no es un control de acceso.
    can_edit: locals.profile?.role === 'ADMIN'
  };
}

/**
 * Los dos limites se repiten aca a proposito, aunque el motor tambien los
 * valide (`nucleo/config/editor.py`). No es duplicacion ociosa: sin esto, un
 * "-999" viaja hasta el motor y vuelve con un mensaje escrito para un
 * desarrollador. La autoridad sigue siendo el motor -- si alguna vez cambia el
 * rango, aca solo se afloja un mensaje, no se rompe un guardado.
 */
const SLA_MAXIMO = 1440; // 24 h
const UMBRAL_MINIMO = -40;
const UMBRAL_MAXIMO = 0;

/** @type {import('./$types').Actions} */
export const actions = {
  async update({ fetch, request, locals }) {
    if (locals.profile?.role !== 'ADMIN') {
      return fail(403, {
        update: { error: 'Solo un administrador puede cambiar los ajustes de la Bandeja.' }
      });
    }

    const form = await request.formData();
    const slaCrudo = form.get('sla_toma_minutos')?.toString().trim() ?? '';
    const umbralCrudo = form.get('umbral_rx_dbm')?.toString().trim() ?? '';
    const sinGestionCrudo = form.get('sin_gestion_horas')?.toString().trim() ?? '';

    // Vacio NO es un error: es como se dice "sin definir". Se traduce al valor
    // que el motor entiende como tal (0 para el plazo) en vez de rechazarlo.
    const sla = slaCrudo === '' ? 0 : Number(slaCrudo);
    if (!Number.isInteger(sla) || sla < 0 || sla > SLA_MAXIMO) {
      return fail(400, {
        update: {
          error: `El plazo tiene que ser un número entero de minutos, entre 0 y ${SLA_MAXIMO}. Dejalo vacío o en 0 para no fijar ninguno.`
        }
      });
    }

    let umbral = null;
    if (umbralCrudo !== '') {
      umbral = Number(umbralCrudo);
      if (!Number.isFinite(umbral) || umbral < UMBRAL_MINIMO || umbral > UMBRAL_MAXIMO) {
        return fail(400, {
          update: {
            error: `El umbral óptico tiene que estar entre ${UMBRAL_MINIMO} y ${UMBRAL_MAXIMO} dBm. La potencia recibida es negativa: un valor positivo no existe en una red GPON.`
          }
        });
      }
    }

    // Guarda anti-limbo: vacio = null = la banda "sin resolucion registrada"
    // no existe. El rango fino lo valida el motor (1..720 h); aca solo se
    // exige que sea un entero, para que el mensaje del motor llegue tal cual.
    let sinGestion = null;
    if (sinGestionCrudo !== '') {
      sinGestion = Number(sinGestionCrudo);
      if (!Number.isInteger(sinGestion) || sinGestion < 1) {
        return fail(400, {
          update: {
            error: 'Las horas sin resolución tienen que ser un número entero, 1 o más. Dejalo vacío para no encender la banda.'
          }
        });
      }
    }

    try {
      await guardarAjustesBandeja(locals, fetch, {
        sla_toma_minutos: sla,
        umbral_rx_dbm: umbral,
        sin_gestion_horas: sinGestion
      });
    } catch (/** @type {any} */ err) {
      // El texto viene del validador del motor y nombra el campo y el motivo.
      // Se pasa tal cual: es la diferencia entre "no se pudo guardar" y
      // "el umbral tiene que estar entre -40 y 0".
      return fail(400, {
        update: { error: err?.message || 'No se pudieron guardar los ajustes de la Bandeja.' }
      });
    }

    // Sin redirect: `load` se vuelve a correr despues de la accion y los
    // valores nuevos aparecen donde el usuario ya esta mirando.
    return { updated: true };
  },

  /* Los rótulos de motivos, etiquetas y casos. El formulario manda un campo
     por clave; vacío = sin rótulo, y el motor lo descarta. Cuál clave existe
     lo valida el motor contra la configuración de la empresa. */
  async rotulos({ fetch, request, locals }) {
    if (locals.profile?.role !== 'ADMIN') {
      return fail(403, {
        rotulos: { error: 'Solo un administrador puede cambiar los rótulos de la Bandeja.' }
      });
    }
    const form = await request.formData();
    /** @type {Record<string, string>} */
    const rotulos = {};
    for (const [nombre, valor] of form.entries()) {
      if (!nombre.startsWith(PREFIJO_ROTULO)) continue;
      const texto = valor.toString().trim();
      if (texto) rotulos[nombre.slice(PREFIJO_ROTULO.length)] = texto;
    }
    try {
      await guardarRotulosBandeja(locals, fetch, rotulos);
    } catch (/** @type {any} */ err) {
      return fail(400, {
        rotulos: { error: err?.message || 'No se pudieron guardar los rótulos.' }
      });
    }
    return { rotulosGuardados: true };
  },

  /* Cuántos días mira el aviso de reincidencia (29/10/2026). 0 lo apaga. */
  async reincidencia({ fetch, request, locals }) {
    if (locals.profile?.role !== 'ADMIN') {
      return fail(403, {
        reincidencia: { error: 'Solo un administrador puede cambiar este ajuste.' }
      });
    }
    const form = await request.formData();
    const dias = Number(form.get('reincidencia_dias')?.toString().trim() || '0');
    if (!Number.isInteger(dias) || dias < 0 || dias > 365) {
      return fail(400, {
        reincidencia: { error: 'Los días tienen que ser un número entero entre 0 y 365. 0 apaga el aviso.' }
      });
    }
    try {
      await guardarReincidencia(locals, fetch, dias);
    } catch (/** @type {any} */ err) {
      return fail(400, { reincidencia: { error: err?.message || 'No se pudo guardar.' } });
    }
    return { reincidenciaGuardada: true };
  }
};
