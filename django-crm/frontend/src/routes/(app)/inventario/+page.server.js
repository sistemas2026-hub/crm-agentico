import { fail } from '@sveltejs/kit';
import {
  leerExistencias,
  leerCatalogo,
  leerUbicaciones,
  leerSerie,
  leerPersonas,
  registrarEntrada,
  despachar,
  recibirDevolucion,
} from '$lib/server/v2/inventario.js';

/**
 * El inventario de la empresa.
 *
 * LAS TRES LECTURAS VAN EN PARALELO porque ninguna depende de la otra, y la
 * pantalla no sirve con dos de tres: sin catálogo no se puede despachar, sin
 * ubicaciones no se sabe de dónde, sin existencias no se sabe cuánto hay.
 *
 * Y NINGUNA INVENTA UN CERO: cada lectura devuelve `error` aparte de su forma
 * vacía. Una bodega que dice «0 conectores» porque la API falló manda a un
 * técnico a la calle sin material, y eso no se distingue de una bodega vacía si
 * la pantalla no lo dice.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ locals, url, cookies }) {
  // `apiRequest` lee el token de aca. `locals` no tiene cookies en un load.
  const ctx = { cookies };
  const serie = (url.searchParams.get('serie') ?? '').trim();

  const [existencias, catalogo, ubicaciones, personas] = await Promise.all([
    leerExistencias(ctx),
    leerCatalogo(ctx),
    leerUbicaciones(ctx),
    leerPersonas(ctx),
  ]);

  const consulta = serie ? await leerSerie(ctx, serie) : null;

  return {
    existencias: existencias.ubicaciones,
    materiales: catalogo.materiales,
    ubicaciones: ubicaciones.ubicaciones,
    personas: personas.personas,
    serieConsultada: serie,
    consulta,
    // Un solo lugar decide si la pantalla puede confiar en lo que muestra.
    noSePudoLeer:
      existencias.error || catalogo.error || ubicaciones.error || personas.error,
  };
}

/**
 * Las tres acciones que mueven material. Cada una devuelve el mensaje del
 * backend tal cual: el 409 del despacho imposible dice DÓNDE está el aparato, y
 * reescribirlo con un «no se pudo» perdería justo el dato que resuelve el caso.
 *
 * @type {import('./$types').Actions}
 */
export const actions = {
  entrada: async ({ request, cookies }) => {
    const f = await request.formData();
    try {
      await registrarEntrada({ cookies }, {
        material: f.get('material'),
        cantidad: f.get('cantidad'),
        serie: f.get('serie') ?? '',
        ubicacion_destino: f.get('ubicacion_destino'),
        origen_ref: f.get('origen_ref') ?? '',
      });
      return { hecho: 'La entrada quedó registrada.' };
    } catch (e) {
      return fail(400, { error: mensajeDe(e) });
    }
  },

  despacho: async ({ request, cookies }) => {
    const f = await request.formData();
    const lineas = [{
      material: f.get('material'),
      cantidad: f.get('cantidad'),
      serie: f.get('serie') ?? '',
    }];
    try {
      const r = await despachar({ cookies }, {
        ubicacion_origen: f.get('ubicacion_origen'),
        profile_destino: f.get('profile_destino'),
        acta: f.get('acta') ?? '',
        lineas,
      });
      return { hecho: `Despachado. Acta: ${r?.acta || r?.entrega}` };
    } catch (e) {
      return fail(409, { error: mensajeDe(e) });
    }
  },

  devolucion: async ({ request, cookies }) => {
    const f = await request.formData();
    try {
      const esperado = (f.get('esperado') ?? '').toString().trim();
      const r = await recibirDevolucion({ cookies }, {
        profile_origen: f.get('profile_origen'),
        ubicacion_destino: f.get('ubicacion_destino'),
        notas: f.get('notas') ?? '',
        lineas: [{
          material: f.get('material'),
          cantidad: f.get('cantidad'),
          serie: f.get('serie') ?? '',
          // Solo viaja si quien recibe lo declaró. Sin esto el backend NO
          // adivina un faltante: devolver parte de lo que se tiene es legítimo.
          ...(esperado ? { esperado } : {}),
        }],
      });
      const abiertas = r?.incidencias ?? [];
      if (abiertas.length) {
        // La diferencia se DICE. Un 201 silencioso sobre una devolución que no
        // cuadra es esconder justo lo que hay que mirar.
        return {
          hecho: 'La devolución quedó registrada.',
          incidencias: abiertas,
        };
      }
      return { hecho: 'La devolución quedó registrada.' };
    } catch (e) {
      return fail(409, { error: mensajeDe(e) });
    }
  },
};

/**
 * El texto que el backend mandó, no una reescritura.
 *
 * `apiRequest` mete el cuerpo del error en el mensaje cuando puede; si no,
 * queda el genérico. Preferir el del backend importa porque ahí está el dato
 * útil: «la serie X figura en la Custodia de Juan» resuelve el caso, y
 * «no se pudo despachar» obliga a investigar de cero.
 *
 * @param {any} e
 */
function mensajeDe(e) {
  const crudo = String(e?.body?.detail ?? e?.message ?? e ?? '');
  const limpio = crudo.replace(/^Error \d+:\s*/, '').trim();
  return limpio || 'No se pudo completar la operación.';
}
