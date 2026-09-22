/**
 * Programación — Supervisor NOC IA: los datos de /supervisor-noc/programacion.
 *
 * Server-only, y hermano de `supervisor-noc.js`: reusa su `traducirError` en
 * vez de repetir la traduccion de status, y pasa por el mismo `apiRequest`.
 * No hay un segundo cliente HTTP.
 *
 * LO QUE ESTA CAPA NO HACE
 * No calcula capacidad. 'operaciones/capacidad.py' la deriva cuando se
 * pregunta -- a proposito, porque un numero guardado queda viejo en cuanto
 * cambia cualquiera de las cinco cosas de las que depende -- y viene con su
 * riesgo y sus 'faltantes'. Rederivarla aca seria una segunda verdad.
 *
 * Y no ejecuta nada: ni WispHub, ni SmartOLT, ni despacho. Las dos escrituras
 * que expone (secuenciar y publicar) mueven ORDEN PROPUESTO y ESTADO DE PLAN,
 * nunca una orden ni una asignacion.
 */
import { apiRequest } from '$lib/api-helpers.js';
import { traducirError } from './supervisor-noc.js';

/**
 * La jornada de un dia: sus lineas en orden reproducible, mas el resumen que
 * cuenta los empates en vez de resolverlos.
 *
 * EXIGE UN DIA. El backend responde 400 FALTA_FILTRO sin 'dia' ni 'plan', con
 * un motivo que vale la pena respetar: "sin filtro, 'la jornada' no significa
 * nada". Por eso la pantalla abre con una fecha, nunca con "todo".
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string} dia  YYYY-MM-DD
 */
export async function leerJornada({ cookies }, dia) {
  try {
    const d = await apiRequest(
      `/operaciones/programacion/jornada/?dia=${encodeURIComponent(dia)}`,
      {},
      { cookies }
    );
    return {
      count: d?.count ?? 0,
      lineas: d?.resultados ?? [],
      resumen: d?.resumen ?? null,
      filtro: d?.filtro ?? null,
      error: null
    };
  } catch (/** @type {any} */ err) {
    return { count: null, lineas: [], resumen: null, filtro: null, error: traducirError(err, 'la jornada') };
  }
}

/**
 * La capacidad operacional del dia, POR PERSONA.
 *
 * NO HAY CUADRILLAS CON NOMBRE en el backend, y no es un olvido:
 * 'capacidad.py' lo dice ("no existe una regla empresarial de productividad
 * de cuadrillas, y no se inventa una aqui"). Lo que existe es
 * 'campo.AsignacionTrabajo', que ata PERSONAS a una orden. Asi que esta
 * funcion devuelve personas, y la pantalla muestra personas.
 *
 * Cada una trae su jornada, su disponibilidad, la carga comprometida, lo que
 * le queda, su 'riesgo' y los 'faltantes' -- si falta la duracion de alguna
 * orden, el riesgo responde INDETERMINADO en vez de "sin sobrecarga". Un dato
 * que falta no vale cero.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string} dia  YYYY-MM-DD
 */
export async function leerCapacidad({ cookies }, dia) {
  try {
    const d = await apiRequest(
      `/operaciones/capacidad/jornada/?dia=${encodeURIComponent(dia)}`,
      {},
      { cookies }
    );
    return {
      jornada: d?.jornada ?? null,
      personas: d?.resultados ?? d?.personas_detalle ?? [],
      total_personas: d?.personas ?? null,
      error: null
    };
  } catch (/** @type {any} */ err) {
    return { jornada: null, personas: [], total_personas: null, error: traducirError(err, 'la capacidad de la jornada') };
  }
}

/**
 * Las propuestas del Supervisor que hablan de programacion.
 *
 * Son las mismas propuestas de la otra pantalla, acotadas a las señales del
 * dominio: el backend no tiene un endpoint "recomendaciones de programacion",
 * y fabricar uno duplicaria la cola que ya existe.
 */
export const SENALES_PROGRAMACION = [
  'orden_sin_programar',
  'programacion_sin_publicar',
  'orden_con_riesgo_operacional',
  'orden_sla_vencido',
  'orden_sla_por_vencer',
  'dato_incompleto'
];

/**
 * Reordena la jornada entera en UNA transaccion.
 *
 * NO REPROGRAMA: no toca 'programada_para', ni el dia, ni el plan, ni la
 * asignacion. Solo el orden propuesto (operaciones/views.py).
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {Record<string, any>} cuerpo
 */
export async function secuenciarJornada({ cookies }, cuerpo) {
  return apiRequest(
    '/operaciones/programacion/jornada/secuenciar/',
    { method: 'POST', body: cuerpo },
    { cookies }
  );
}

/**
 * Publica un plan semanal: borrador -> publicada, y nada mas. No ejecuta la
 * programacion ni toca ninguna orden.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string} programacionId
 */
export async function publicarProgramacion({ cookies }, programacionId) {
  return apiRequest(
    `/operaciones/programacion/${programacionId}/publicar/`,
    { method: 'POST', body: {} },
    { cookies }
  );
}

/**
 * Los cuatro numeros de la cabecera, derivados de lo que ya llego.
 *
 * SIN INVENTAR NINGUNO. Cada uno sale de contar las lineas que el backend
 * devolvio, o se declara ausente. El porcentaje de capacidad es el unico que
 * no se cuenta aca: lo trae 'capacidad.py' por persona, y si alguna tiene
 * riesgo INDETERMINADO el promedio se marca parcial en vez de presentarse
 * como si fuera de todos.
 *
 * @param {{ lineas: any[], count: number|null, error: any }} jornada
 * @param {{ personas: any[], error: any }} capacidad
 */
export function resumenProgramacion(jornada, capacidad) {
  /** Un sobre que declara ausencia. Igual que en supervisor-noc.js. */
  const sinDato = (/** @type {string} */ motivo) => ({
    estado: 'SIN_DATO',
    valor: null,
    motivo
  });
  const valido = (/** @type {number} */ v) => ({ estado: 'VALIDO', valor: v, motivo: '' });

  const hayJornada = !jornada.error && Array.isArray(jornada.lineas);
  const lineas = hayJornada ? jornada.lineas : [];

  // 'secuencia = 0' significa SIN SECUENCIAR (decision E-2 del backend), no
  // "primera". Contarla como orden ya secuenciada seria leer al reves el
  // unico campo que esa decision fijo.
  const sinSecuenciar = lineas.filter((/** @type {any} */ l) => (l.secuencia ?? 0) === 0).length;
  const bloqueadas = lineas.filter((/** @type {any} */ l) => l.estado === 'bloqueada').length;

  const personas = capacidad.error ? [] : capacidad.personas;
  const conRiesgo = personas.filter(
    (/** @type {any} */ p) => p?.riesgo?.estado === 'SOBRECARGA' || p?.riesgo === 'SOBRECARGA'
  ).length;

  // El % de ocupacion: carga conocida sobre jornada, promediado entre las
  // personas que tienen los dos datos. Si a alguna le faltan duraciones, el
  // promedio se declara parcial -- no se imputa nada.
  let ocupacion = sinDato('El backend no entregó la capacidad de la jornada.');
  if (!capacidad.error && personas.length) {
    const utiles = personas.filter(
      (/** @type {any} */ p) => p?.jornada?.minutos > 0 && p?.carga?.minutos_conocidos != null
    );
    if (utiles.length) {
      const pct =
        utiles.reduce(
          (/** @type {number} */ t, /** @type {any} */ p) =>
            t + p.carga.minutos_conocidos / p.jornada.minutos,
          0
        ) / utiles.length;
      const completos = utiles.every((/** @type {any} */ p) => (p.faltantes ?? []).length === 0);
      ocupacion = {
        estado: completos ? 'VALIDO' : 'DATOS_INSUFICIENTES',
        valor: Math.round(pct * 100),
        motivo: completos
          ? ''
          : 'Alguna orden no declara duración: el porcentaje se calculó sobre lo conocido.'
      };
    }
  }

  return [
    {
      clave: 'ordenes',
      titulo: 'Órdenes en la jornada',
      dato: hayJornada ? valido(jornada.count ?? lineas.length) : sinDato('No se pudo leer la jornada.')
    },
    {
      clave: 'sin_secuenciar',
      titulo: 'Sin secuenciar',
      dato: hayJornada ? valido(sinSecuenciar) : sinDato('No se pudo leer la jornada.')
    },
    { clave: 'ocupacion', titulo: 'Ocupación media', dato: ocupacion, sufijo: '%' },
    {
      clave: 'bloqueadas',
      titulo: 'Bloqueadas',
      dato: hayJornada ? valido(bloqueadas) : sinDato('No se pudo leer la jornada.')
    },
    {
      clave: 'sobrecarga',
      titulo: 'Personas en sobrecarga',
      dato: capacidad.error ? sinDato('No se pudo leer la capacidad.') : valido(conRiesgo)
    }
  ];
}
