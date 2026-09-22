/**
 * Supervisor NOC IA: los datos que alimentan /supervisor-noc.
 *
 * Server-only. Dos origenes distintos, y la distincion importa:
 *
 *   - django-crm (`/api/operaciones/...`) -- las propuestas, los indicadores
 *     y el ciclo de deteccion. Todo con el JWT del colaborador, asi que el
 *     403 de 'EsJefeDeOperaciones' llega hasta esta capa y se declara.
 *   - el motor (`PRIVATE_ASISTENTE_URL`) -- el interruptor de autonomia, que
 *     NO vive en django-crm ni en tenant_config (ver CLAUDE.md: esa ruta falla
 *     ABIERTA). Se lee aparte, y si no se puede leer se dice, nunca se asume
 *     que esta detenida.
 *
 * LO QUE ESTA CAPA NO HACE
 * No calcula ningun indicador. Cada numero que la pantalla muestra lo calculo
 * el backend y viaja con su 'estado' (VALIDO / DATOS_INSUFICIENTES /
 * NO_APLICA) y su cobertura -- volver a derivarlo aca crearia una segunda
 * verdad sobre la misma cifra, que es justo lo que operaciones/indicadores.py
 * evita al no guardar KPIs.
 */
import { env } from '$env/dynamic/private';
import { apiRequest } from '$lib/api-helpers.js';
import { headersMotor } from './motor-headers.js';

/** Un sobre de indicador vacio pero valido, para que la pantalla nunca reviente. */
const SIN_DATO = {
  estado: 'NO_APLICA',
  valor: null,
  unidad: 'conteo',
  cobertura: null,
  motivo: 'El backend no devolvio este indicador.'
};

/**
 * El indicador que vive en `ruta` dentro del arbol de `/indicadores/`, o un
 * sobre NO_APLICA. Nunca inventa un 0: la ausencia de un numero y un cero son
 * cosas distintas, y el backend ya lo distingue.
 *
 * @param {any} arbol
 * @param {string[]} ruta
 */
function indicador(arbol, ruta) {
  let nodo = arbol;
  for (const paso of ruta) {
    if (nodo == null || typeof nodo !== 'object') return SIN_DATO;
    nodo = nodo[paso];
  }
  return nodo && typeof nodo === 'object' && 'estado' in nodo ? nodo : SIN_DATO;
}

/**
 * Los indicadores operativos completos. Es un GET y no corre el ciclo: pedir
 * un numero no debe producir trabajo (operaciones/views.py::IndicadoresView).
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string | number} [dias]
 */
export async function leerIndicadores({ cookies }, dias) {
  const query = dias ? `?dias=${encodeURIComponent(dias)}` : '';
  try {
    return { datos: await apiRequest(`/operaciones/indicadores/${query}`, {}, { cookies }), error: null };
  } catch (/** @type {any} */ err) {
    // El 403 no es una falla: es el permiso funcionando. Se distingue para
    // que la pantalla diga "no tenes permiso" en vez de "algo se rompio".
    return { datos: null, error: err?.status === 403 ? 'SIN_PERMISO' : 'ERROR' };
  }
}

/**
 * Las propuestas de la organizacion, las mas urgentes primero. El backend ya
 * ordena y corta en 200.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {{ estado?: string, tipo_senal?: string }} [filtros]
 */
export async function listarPropuestas({ cookies }, filtros = {}) {
  const params = new URLSearchParams();
  if (filtros.estado) params.set('estado', filtros.estado);
  if (filtros.tipo_senal) params.set('tipo_senal', filtros.tipo_senal);
  const query = params.toString() ? `?${params}` : '';
  try {
    const datos = await apiRequest(`/operaciones/propuestas/${query}`, {}, { cookies });
    return { count: datos?.count ?? 0, resultados: datos?.resultados ?? [], error: null };
  } catch (/** @type {any} */ err) {
    return { count: 0, resultados: [], error: err?.status === 403 ? 'SIN_PERMISO' : 'ERROR' };
  }
}

/**
 * Una propuesta con su evidencia completa y su historial de auditoria.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string} id
 */
export async function leerPropuesta({ cookies }, id) {
  try {
    return { datos: await apiRequest(`/operaciones/propuestas/${id}/`, {}, { cookies }), error: null };
  } catch (/** @type {any} */ err) {
    // 404 tambien cubre "es de otra organizacion" a proposito
    // (operaciones/permissions.py::misma_organizacion): un 403 confirmaria
    // que el id existe.
    return { datos: null, error: err?.status === 404 ? 'NO_ENCONTRADA' : 'ERROR' };
  }
}

/**
 * Corre una pasada de deteccion. Solo lee y propone: la respuesta trae
 * `acciones_ejecutadas: 0` y `shadow_mode`, y no hay ningun camino que los
 * mueva en esta etapa (operaciones/supervisor.py).
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 */
export async function correrCiclo({ cookies }) {
  return apiRequest('/operaciones/supervisor/ciclo/', { method: 'POST', body: {} }, { cookies });
}

/**
 * Una pasada de uno de los dos asistentes operativos. ESCRIBE propuestas en la
 * misma cola y nada mas: no programa, no asigna y no llama a ningun sistema
 * externo (operaciones/views.py::AsistenteView).
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string} dominio  'programacion' | 'compromiso'
 */
export async function correrAsistente({ cookies }, dominio) {
  return apiRequest('/operaciones/asistentes/', { method: 'POST', body: { dominio } }, { cookies });
}

/**
 * La decision del Jefe de Operaciones sobre una propuesta.
 *
 * ACEPTAR NO EJECUTA NADA, y esta dicho aca ademas de en el backend porque es
 * la clase de garantia que una capa intermedia puede erosionar sin querer.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string} id
 * @param {{ decision: string, comentario?: string, cambios?: Record<string, any> }} revision
 */
export async function revisarPropuesta({ cookies }, id, revision) {
  return apiRequest(
    `/operaciones/propuestas/${id}/revisar/`,
    { method: 'POST', body: revision },
    { cookies }
  );
}

/**
 * El interruptor de autonomia del motor.
 *
 * FALLA DECLARANDO, NO ASUMIENDO. Si el motor no responde, la pantalla no
 * puede decir "autonomia detenida" -- eso seria exactamente la falla ABIERTA
 * que 'nucleo/seguridad/interruptor.py' existe para evitar, servida como si
 * fuera una garantia. Devuelve estado null y el motivo.
 */
export async function leerAutonomia() {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  const tenant = env.PRIVATE_ASISTENTE_TENANT;
  if (!baseUrl || !tenant) {
    return { estado: null, permitido: null, motivo: 'El motor no esta configurado en este entorno.', historial: [] };
  }
  try {
    const r = await fetch(`${baseUrl}/autonomia?tenant=${encodeURIComponent(tenant)}`, {
      headers: headersMotor()
    });
    if (!r.ok) {
      return { estado: null, permitido: null, motivo: `El motor respondio ${r.status}.`, historial: [] };
    }
    const d = await r.json();
    return {
      estado: d.estado ?? null,
      permitido: d.permitido ?? null,
      motivo: d.motivo ?? '',
      actor: d.actor ?? null,
      historial: Array.isArray(d.historial) ? d.historial : []
    };
  } catch (/** @type {any} */ err) {
    return { estado: null, permitido: null, motivo: `No se pudo consultar el motor: ${err?.message ?? err}`, historial: [] };
  }
}

/**
 * Los cinco numeros del Resumen operativo, cada uno con su sobre intacto.
 *
 * NO HAY COMPARACION CONTRA AYER. La maqueta mostraba "+3 vs. ayer" en cada
 * tarjeta; el backend no guarda serie historica de senales (no hay tabla de
 * KPI, a proposito), asi que ese delta no se puede calcular sin inventarlo.
 * En su lugar viaja el 'estado' del indicador, que es un dato real y sirve
 * para lo mismo: decirle al jefe cuanto confiar en el numero.
 *
 * @param {any} indicadores  el arbol completo de /indicadores/
 */
export function resumenOperativo(indicadores) {
  const sup = ['supervisor'];
  const porTipo = (tipo) => indicador(indicadores, [...sup, 'senales_por_tipo', tipo]);

  // 'senales_por_tipo' solo trae las que tienen al menos una ocurrencia
  // (operaciones/indicadores.py arma el dict desde 'vivas'), asi que una
  // ausencia aca es un cero real y no un dato faltante.
  const cero = { ...SIN_DATO, estado: 'VALIDO', valor: 0, cobertura: 1 };
  const oCero = (n) => (n === SIN_DATO ? cero : n);

  const sumar = (...nodos) => {
    const vivos = nodos.map(oCero);
    return {
      estado: vivos.every((n) => n.estado === 'VALIDO') ? 'VALIDO' : 'DATOS_INSUFICIENTES',
      valor: vivos.reduce((t, n) => t + (n.valor ?? 0), 0),
      unidad: 'conteo',
      cobertura: 1,
      motivo: ''
    };
  };

  return [
    {
      titulo: 'Requieren atención',
      etiqueta: 'Atención requerida',
      tono: 'error',
      dato: indicador(indicadores, [...sup, 'senales_vigentes'])
    },
    {
      titulo: 'Próximos vencimientos',
      etiqueta: 'Riesgo SLA',
      tono: 'neutro',
      dato: sumar(porTipo('orden_sla_por_vencer'), porTipo('compromiso_por_vencer'))
    },
    {
      titulo: 'Bloqueos',
      etiqueta: 'Bloqueadas',
      tono: 'variante',
      dato: oCero(porTipo('actividad_bloqueada'))
    },
    {
      titulo: 'Incidencias abiertas',
      etiqueta: 'En curso',
      tono: 'error',
      dato: oCero(porTipo('incidencia_sin_resolver'))
    },
    {
      titulo: 'OT sin programar',
      etiqueta: 'Pendiente cuadrilla',
      tono: 'secundario',
      dato: oCero(porTipo('orden_sin_programar'))
    }
  ];
}
