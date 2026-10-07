import { fail } from '@sveltejs/kit';
import {
  leerCuadrillas,
  crearCuadrilla,
  editarCuadrilla,
  leerJornadaDeCuadrillas,
  leerHistorialDeCuadrillas,
  armarJornada,
  leerZonas,
  crearZona,
  mapearZona,
  leerLocalidades
} from '$lib/server/v2/cuadrillas.js';
import { leerPersonas, leerUbicaciones } from '$lib/server/v2/inventario.js';

/**
 * Cuadrillas — Supervisor NOC.
 *
 * Tercera vista del mismo módulo, no una pantalla suelta: cuelga de
 * /supervisor-noc para que se alcance con las pastillas de arriba, igual que
 * Programación.
 *
 * ABRE EN UN DÍA, SIEMPRE. «La jornada» sin fecha no significa nada —es el
 * mismo criterio que el backend ya impone en programación— así que sin
 * `?dia=` se usa hoy en vez de mostrar «todo».
 */

/** Hoy en formato YYYY-MM-DD, en la zona del servidor. */
function hoy() {
  return new Date().toISOString().slice(0, 10);
}

/** @type {import('./$types').PageServerLoad} */
export async function load({ url, cookies, locals, fetch }) {
  const dia = (url.searchParams.get('dia') ?? '').trim() || hoy();
  const verBajas = url.searchParams.get('bajas') === '1';

  // EL HISTORIAL SE PIDE, NO VIENE SIEMPRE. Es otra pregunta que «armar
  // mañana», y traerlo en cada visita costaría una consulta de hasta tres
  // meses para una pantalla que la mayoría de las veces se abre a asignar.
  const verQuien = (url.searchParams.get('quien') ?? '').trim();
  const verCual = (url.searchParams.get('cual') ?? '').trim();
  const desde = (url.searchParams.get('desde') ?? '').trim();
  const hasta = (url.searchParams.get('hasta') ?? '').trim();
  const hayHistorial = Boolean((verQuien || verCual) && desde && hasta);

  // Las cuatro juntas: sin personas no se puede armar una cuadrilla, sin
  // vehículos no se le puede asignar uno, y sin la jornada no se sabe qué
  // hace hoy. Pedirlas en serie sumaría tres esperas que no hacen falta.
  const [cuadrillas, jornada, personas, ubicaciones, historial, zonas, locs] =
    await Promise.all([
      leerCuadrillas({ cookies }, verBajas),
      leerJornadaDeCuadrillas({ cookies }, dia),
      leerPersonas({ cookies }),
      leerUbicaciones({ cookies }),
      hayHistorial
        ? leerHistorialDeCuadrillas({ cookies }, {
            desde,
            hasta,
            cuadrilla: verCual,
            profile: verQuien
          })
        : Promise.resolve({ jornadas: [], error: false, motivo: '' }),
      leerZonas({ cookies }),
      // Las localidades viven en el MOTOR, no acá: las arma
      // `localidades.py::sincronizar()` recorriendo el catálogo del
      // proveedor, y su documentación dice que «nunca la escribe una
      // persona». Se ofrecen para elegir, no para teclear.
      leerLocalidades(locals, fetch)
    ]);

  const vehiculos = (ubicaciones.ubicaciones ?? []).filter(
    (u) => u.tipo === 'vehiculo'
  );

  return {
    dia,
    verBajas,
    cuadrillas: cuadrillas.cuadrillas,
    jornadas: jornada.jornadas,
    zonas: zonas.zonas,
    localidades: locs.localidades,
    localidadesActualizadoEn: locs.actualizado_en,
    localidadesError: locs.error,
    historial: {
      pedido: hayHistorial,
      desde,
      hasta,
      quien: verQuien,
      cual: verCual,
      jornadas: historial.jornadas,
      error: historial.error,
      motivo: historial.motivo
    },
    personas: personas.personas,
    vehiculos,
    // NO SE INVENTA UN CERO CUANDO LA LECTURA FALLÓ. Una empresa sin
    // cuadrillas y una consulta que no respondió se dibujan distinto.
    error: cuadrillas.error || jornada.error || personas.error
  };
}

/** Traduce lo que devuelve el backend a una frase, sin inventar una. */
function mensajeDe(e) {
  return (
    e?.body?.detail ||
    e?.detail ||
    e?.message ||
    'No se pudo completar la operación.'
  );
}

export const actions = {
  cuadrilla: async ({ request, cookies }) => {
    const f = await request.formData();
    const id = String(f.get('cuadrilla_id') ?? '').trim();
    const cuerpo = {
      nombre: f.get('nombre'),
      lider: f.get('lider') || null,
      vehiculo: f.get('vehiculo') || null,
      notas: f.get('notas') ?? ''
    };
    try {
      const r = id
        ? await editarCuadrilla({ cookies }, id, cuerpo)
        : await crearCuadrilla({ cookies }, cuerpo);
      return {
        hecho: id
          ? `${r?.nombre} quedó actualizada.`
          : `${r?.nombre} quedó dada de alta.`
      };
    } catch (e) {
      return fail(409, { error: mensajeDe(e) });
    }
  },

  baja: async ({ request, cookies }) => {
    const f = await request.formData();
    const id = String(f.get('cuadrilla_id') ?? '').trim();
    const activa = String(f.get('activa') ?? '') === '1';
    try {
      const r = await editarCuadrilla({ cookies }, id, { activa });
      return {
        hecho: activa
          ? `${r?.nombre} vuelve a estar activa.`
          : `${r?.nombre} quedó dada de baja. Sus jornadas siguen enteras.`
      };
    } catch (e) {
      return fail(409, { error: mensajeDe(e) });
    }
  },

  zona: async ({ request, cookies }) => {
    const f = await request.formData();
    try {
      const r = await crearZona({ cookies }, { nombre: f.get('nombre') });
      return { hecho: `La zona ${r?.nombre} quedó creada.` };
    } catch (e) {
      return fail(409, { error: mensajeDe(e) });
    }
  },

  /**
   * Reemplaza ENTERO el mapeo de una zona.
   *
   * Se manda la lista completa y no un delta: la pantalla tiene el estado
   * entero, y mandar «agregá esta, sacá aquella» obligaría a las dos puntas a
   * estar de acuerdo sobre qué había antes.
   */
  mapeo: async ({ request, cookies }) => {
    const f = await request.formData();
    const id = String(f.get('zona_id') ?? '').trim();
    const localidades = f.getAll('localidad').map((x) => String(x));
    try {
      const r = await mapearZona({ cookies }, id, localidades);
      const n = r?.localidades?.length ?? 0;
      return {
        hecho: `${r?.nombre}: ${n} ${n === 1 ? 'barrio' : 'barrios'}.`
      };
    } catch (e) {
      // 409 es «ese barrio ya está en otra zona», y el mensaje dice en cuál.
      // Se pasa tal cual: sin el nombre hay que salir a buscarlo.
      return fail(409, { error: mensajeDe(e) });
    }
  },

  /**
   * Arma el día de una cuadrilla.
   *
   * Manda la jornada ENTERA —labor e integrantes— porque el backend es
   * idempotente por cuadrilla y fecha: reescribe todo con lo que llega. Mandar
   * solo lo que cambió obligaría a leer el estado previo acá y a decidir qué
   * es un cambio, que es justo lo que la idempotencia evita.
   */
  jornada: async ({ request, cookies }) => {
    const f = await request.formData();

    // Vienen como pares paralelos, igual que las líneas del despacho.
    const perfiles = f.getAll('integrante_profile').map((x) => String(x).trim());
    const roles = f.getAll('integrante_rol').map((x) => String(x).trim());
    const integrantes = perfiles
      .map((profile, i) => ({ profile, rol: roles[i] || 'tecnico' }))
      .filter((x) => x.profile);

    try {
      const r = await armarJornada({ cookies }, {
        cuadrilla: f.get('cuadrilla'),
        fecha: f.get('fecha'),
        labor: f.get('labor'),
        zonas: f.getAll('zona').map((x) => String(x)).filter(Boolean),
        lider: f.get('lider') || null,
        integrantes,
        notas: f.get('notas') ?? ''
      });
      const cuantos = r?.integrantes?.length ?? 0;
      return {
        hecho:
          `${r?.cuadrilla?.nombre}: ${r?.labor_nombre} el ${r?.fecha}, ` +
          `${cuantos} ${cuantos === 1 ? 'persona' : 'personas'}.`
      };
    } catch (e) {
      // 409 es «esa persona ya está en otra cuadrilla hoy», y el mensaje del
      // backend dice en cuál. Se pasa tal cual: reescribirlo acá perdería el
      // nombre, que es lo único que evita salir a buscarla.
      return fail(409, { error: mensajeDe(e) });
    }
  }
};
