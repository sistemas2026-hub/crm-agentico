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
 * NO HAY CLIENTE HTTP PROPIO. Todo pasa por `apiRequest` ($lib/api-helpers.js),
 * el mismo que usa el resto del CRM: resuelve la URL base privada, adjunta el
 * JWT de la cookie y normaliza el error.
 *
 * LO QUE ESTA CAPA NO HACE
 * No calcula ningun indicador. Cada cifra la calculo operaciones/indicadores.py
 * y viaja con su 'estado' (VALIDO / DATOS_INSUFICIENTES / NO_APLICA) y su
 * cobertura -- volver a derivarla aca crearia una segunda verdad sobre el mismo
 * numero. Tampoco ejecuta nada: no hay una sola llamada a WispHub, SmartOLT,
 * acciones_propuestas ni ejecucion_autonoma en todo el modulo.
 */
import { env } from '$env/dynamic/private';
import { apiRequest } from '$lib/api-helpers.js';
import { headersMotor } from './motor-headers.js';
import { tenantDeLaSesion } from './tenant.js';

/**
 * Un fallo, traducido a algo que una persona pueda leer.
 *
 * El codigo viaja aparte del texto porque la pantalla decide distinto segun
 * cual sea: un 403 no es una falla que haya que reintentar, es el permiso
 * funcionando. Nunca se devuelve el error crudo: un stack trace en pantalla
 * no le sirve a nadie que este mirando propuestas.
 *
 * @param {any} err
 * @param {string} que  que se estaba consultando, para el texto
 */
export function traducirError(err, que) {
  const status = err?.status ?? null;
  if (status === 401) {
    return { codigo: 'NO_AUTENTICADO', status, mensaje: 'Tu sesión expiró. Volvé a iniciar sesión.' };
  }
  if (status === 403) {
    return {
      codigo: 'SIN_PERMISO',
      status,
      mensaje: `Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede ver ${que}.`
    };
  }
  if (status === 404) {
    return { codigo: 'NO_ENCONTRADA', status, mensaje: 'No existe, o no pertenece a tu organización.' };
  }
  if (status === 409) {
    return { codigo: 'YA_REVISADA', status, mensaje: 'Esa propuesta ya fue revisada por alguien más.' };
  }
  if (typeof status === 'number' && status >= 500) {
    return {
      codigo: 'ERROR_SERVIDOR',
      status,
      mensaje: `No fue posible consultar ${que}: el servidor respondió con un error.`
    };
  }
  // Sin status es red: el backend no respondio, o la conexion se corto.
  return {
    codigo: status ? 'ERROR' : 'SIN_RESPUESTA',
    status,
    mensaje: status
      ? `No fue posible consultar ${que}.`
      : `No fue posible consultar ${que}: el servicio no respondió.`
  };
}

/**
 * Los indicadores operativos completos. Es un GET y no corre el ciclo: pedir
 * un numero no debe producir trabajo (operaciones/views.py::IndicadoresView).
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string | number} [dias]
 */
export async function leerIndicadores({ cookies }, dias) {
  const query = dias ? `?dias=${encodeURIComponent(String(dias))}` : '';
  try {
    return {
      datos: await apiRequest(`/operaciones/indicadores/${query}`, {}, { cookies }),
      error: null
    };
  } catch (/** @type {any} */ err) {
    return { datos: null, error: traducirError(err, 'los indicadores operativos') };
  }
}

/**
 * Las propuestas de la organizacion, las mas urgentes primero. El backend ya
 * ordena y corta en 200.
 *
 * `count` vuelve null cuando la consulta fallo: un 0 diria que no hay
 * propuestas, que es una afirmacion distinta de "no se pudo saber".
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
    return {
      count: null,
      resultados: [],
      error: traducirError(err, 'las propuestas del Supervisor NOC IA')
    };
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
    // El 404 tambien cubre "es de otra organizacion" a proposito
    // (operaciones/permissions.py::misma_organizacion): un 403 confirmaria
    // que el id existe.
    return { datos: null, error: traducirError(err, 'esta propuesta') };
  }
}

/**
 * Corre una pasada de deteccion. Solo lee y propone: la respuesta trae
 * `acciones_ejecutadas: 0` y `shadow_mode`, y no hay ningun camino que los
 * mueva en esta etapa (operaciones/supervisor.py).
 *
 * UNA sola llamada, sin reintentos. Un ciclo repetido no corrompe nada -- la
 * deduplicacion lo cubre -- pero gasta una pasada entera de deteccion y parte
 * el resumen que el Jefe de Operaciones acaba de leer.
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
 * ACEPTAR NO EJECUTA NADA. Verificado sobre el contrato real: la respuesta
 * trae `ejecutada: false` y un aviso que lo dice con todas las letras. Se
 * repite aca porque es la clase de garantia que una capa intermedia erosiona
 * sin querer.
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
 * La condicion desaparecio antes de que nadie la revisara.
 *
 * Es otra ruta que 'revisar' porque no es una opinion sobre el fondo: nadie
 * dijo si la recomendacion era buena. Por eso no deja revisor y por eso el
 * motivo es obligatorio (operaciones/views.py::CancelarPropuestaView).
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {string} id
 * @param {string} motivo
 */
export async function cancelarPropuesta({ cookies }, id, motivo) {
  return apiRequest(
    `/operaciones/propuestas/${id}/cancelar/`,
    { method: 'POST', body: { motivo } },
    { cookies }
  );
}

/**
 * Los ultimos hechos del modulo, para el feed del tablero.
 *
 * Es el unico bloque de esa pantalla que no existia en ninguna forma: el
 * historial responde "que le paso a ESTA propuesta" y no habia manera de
 * preguntar "que paso, en general". El backend ya acota a las entidades del
 * modulo, asi que aca no se vuelve a filtrar.
 *
 * @param {{ cookies: import('@sveltejs/kit').Cookies }} event
 * @param {number} [limite]
 */
export async function leerActividad({ cookies }, limite = 12) {
  try {
    const d = await apiRequest(
      `/operaciones/actividad-supervisor/?limite=${limite}`,
      {},
      { cookies }
    );
    return { eventos: d?.resultados ?? [], error: null };
  } catch (/** @type {any} */ err) {
    // 'eventos' vacio con 'error' puesto NO es lo mismo que un feed vacio: la
    // pantalla mira el error primero, y solo dice "sin actividad" cuando la
    // lectura salio bien y no habia nada.
    return { eventos: [], error: traducirError(err, 'la actividad reciente') };
  }
}

/**
 * El interruptor de autonomia del motor.
 *
 * FALLA DECLARANDO, NO ASUMIENDO. Si el motor no responde, la pantalla no
 * puede decir "autonomia detenida" -- eso seria exactamente la falla ABIERTA
 * que 'nucleo/seguridad/interruptor.py' existe para evitar, servida como si
 * fuera una garantia. Devuelve estado null y el motivo.
 *
 * Es de LECTURA y punto: esta pantalla no expone ninguna forma de mover el
 * interruptor ni el techo. Eso es gobierno, y vive en `cli/autonomia.py`.
 *
 * @param {App.Locals} locals
 * @param {typeof globalThis.fetch} fetch
 */
export async function leerAutonomia(locals, fetch) {
  const baseUrl = env.PRIVATE_ASISTENTE_URL;
  // Se comprueba la URL ANTES de resolver la empresa: sin motor al que
  // preguntarle, preguntar de qué empresa son los datos es una llamada de más.
  const tenant = baseUrl ? await tenantDeLaSesion(locals, fetch) : null;
  if (!baseUrl || !tenant) {
    return {
      estado: null,
      permitido: null,
      motivo: 'El motor no está configurado en este entorno.',
      historial: []
    };
  }
  try {
    const r = await fetch(`${baseUrl}/autonomia?tenant=${encodeURIComponent(tenant)}`, {
      headers: headersMotor()
    });
    if (!r.ok) {
      return { estado: null, permitido: null, motivo: `El motor respondió ${r.status}.`, historial: [] };
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
    return {
      estado: null,
      permitido: null,
      motivo: `No se pudo consultar el motor: ${err?.message ?? err}`,
      historial: []
    };
  }
}

/** Un sobre que declara la AUSENCIA del dato. No es un cero. */
const SIN_DATO = Object.freeze({
  estado: 'SIN_DATO',
  valor: null,
  unidad: 'conteo',
  cobertura: null,
  motivo: 'El backend no devolvió este indicador.'
});

/**
 * El indicador que vive en `ruta` dentro del arbol de `/indicadores/`, o el
 * sobre SIN_DATO.
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
 * Los cinco numeros del Resumen operativo, cada uno con su sobre intacto.
 *
 * CERO Y "SIN DATOS" NO SON LO MISMO, y esta funcion existe sobre todo para
 * no confundirlos. 'senales_por_tipo' solo trae las señales con al menos una
 * ocurrencia (operaciones/indicadores.py lo arma desde 'vivas'), asi que:
 *
 *   - si el arbol de indicadores LLEGO y el tipo no figura -> es un CERO real;
 *   - si el arbol no llego -> no se sabe, y la tarjeta dice "Sin datos".
 *
 * La diferencia la decide si llego el arbol, no la ausencia de la clave. Una
 * version anterior devolvia 0 en los dos casos, que es afirmar "no hay
 * ninguna incidencia abierta" cuando lo cierto era "no se pudo preguntar".
 *
 * NO HAY COMPARACION CONTRA AYER. El backend no guarda serie historica de
 * señales (no hay tabla de KPI, a proposito), asi que ese delta no se puede
 * calcular sin inventarlo.
 *
 * @param {any} indicadores  el arbol completo de /indicadores/, o null
 */
export function resumenOperativo(indicadores) {
  const hayArbol = !!(indicadores && typeof indicadores === 'object' && indicadores.supervisor);
  const sup = ['supervisor'];

  /** Un tipo de señal: cero real si el arbol llego, ausencia si no. */
  const porTipo = (/** @type {string} */ tipo) => {
    if (!hayArbol) return SIN_DATO;
    const n = indicador(indicadores, [...sup, 'senales_por_tipo', tipo]);
    if (n !== SIN_DATO) return n;
    return { estado: 'VALIDO', valor: 0, unidad: 'conteo', cobertura: 1, motivo: '' };
  };

  /** Suma de varios tipos. Si falta cualquiera, el total es desconocido. */
  const sumar = (/** @type {any[]} */ ...nodos) => {
    if (nodos.some((n) => n === SIN_DATO || n.valor == null)) return SIN_DATO;
    return {
      estado: nodos.every((n) => n.estado === 'VALIDO') ? 'VALIDO' : 'DATOS_INSUFICIENTES',
      valor: nodos.reduce((t, n) => t + (n.valor ?? 0), 0),
      unidad: 'conteo',
      cobertura: 1,
      motivo: ''
    };
  };

  return [
    {
      clave: 'atencion',
      titulo: 'Requieren atención',
      etiqueta: 'Atención requerida',
      tono: 'error',
      dato: hayArbol ? indicador(indicadores, [...sup, 'senales_vigentes']) : SIN_DATO
    },
    {
      clave: 'vencimientos',
      titulo: 'Próximos vencimientos',
      etiqueta: 'Riesgo SLA',
      tono: 'neutro',
      dato: sumar(porTipo('orden_sla_por_vencer'), porTipo('compromiso_por_vencer'))
    },
    {
      clave: 'bloqueos',
      titulo: 'Bloqueos',
      etiqueta: 'Bloqueadas',
      tono: 'variante',
      dato: porTipo('actividad_bloqueada')
    },
    {
      clave: 'incidencias',
      titulo: 'Incidencias abiertas',
      etiqueta: 'En curso',
      tono: 'error',
      dato: porTipo('incidencia_sin_resolver')
    },
    {
      clave: 'sin_programar',
      titulo: 'OT sin programar',
      etiqueta: 'Pendiente cuadrilla',
      tono: 'secundario',
      dato: porTipo('orden_sin_programar')
    }
  ];
}
