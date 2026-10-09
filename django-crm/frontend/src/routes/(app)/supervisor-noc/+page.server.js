import { fail } from '@sveltejs/kit';
import {
  leerIndicadores,
  listarPropuestas,
  leerAutonomia,
  leerActividad,
  correrCiclo,
  correrAsistente,
  revisarPropuesta,
  cancelarPropuesta,
  resumenOperativo,
  traducirError
} from '$lib/server/v2/supervisor-noc.js';
import { leerCapacidad } from '$lib/server/v2/programacion-noc.js';

/**
 * POR QUE ESTA RUTA VIVE EN (app)
 * -------------------------------
 * Primero se monto en (no-layout), para que la pantalla conservara la barra
 * lateral y la cabecera que traia su diseno. El efecto fue el que
 * Sidebar.svelte ya dejo escrito sobre /instalaciones: una pantalla sin
 * entrada en el menu no esta terminada, esta escondida.
 *
 * El gate de ROL va aca ademas del que aplica el backend: dos capas, igual
 * que el resto del CRM. Ocultar un boton no es una barrera -- la barrera es
 * 'EsJefeDeOperaciones' en cada vista de operaciones, y sigue estando.
 *
 * LO QUE ESTA PANTALLA NO PUEDE HACER, POR DISENO
 * Ejecutar una herramienta o aplicar una propuesta por su cuenta. No hay
 * accion para eso: no es que esten ocultas, es que no existen en este archivo.
 *
 * LO QUE SI PUEDE DESDE EL 08/10/2026, y por que cambio
 * ----------------------------------------------------
 * Ver y cambiar el ALCANCE del Supervisor --su nivel y el interruptor general--
 * desde '/api/supervisor-noc/autonomia'. Hasta ese dia estaba escrito aqui que
 * no podia, y era correcto: el Supervisor solo observaba.
 *
 * Dejo de serlo el dia que pudo cerrar casos solo. Un freno que nadie puede
 * tocar desde la pantalla no es un freno, y el momento en que hace falta es
 * justo cuando nadie quiere estar buscando como abrir una terminal en un
 * servidor. La decision se reabrio con ese motivo, no por comodidad.
 *
 * Las puertas siguen donde estaban: subir el nivel exige persona, motivo y
 * criterios medidos, y eso lo impone 'autonomia.cambiar' mas una restriccion
 * de base. La pantalla le pone cara humana a esa regla; no la reemplaza.
 */

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @type {import('./$types').PageServerLoad} */
export async function load({ cookies, locals, url, fetch }) {
  const rol = /** @type {any} */ (locals).profile?.role ?? null;
  const puedeVer = ROLES_GESTION.has(rol);

  // Sin rol de gestion no se pide nada: el backend responderia 403 a cada
  // llamada y la pantalla mostraria cinco errores en vez de un motivo.
  if (!puedeVer) {
    return {
      puedeVer: false,
      rol,
      org: locals.org?.name ?? null,
      usuario: locals.user?.email ?? null
    };
  }

  const dias = url.searchParams.get('dias');

  // Las propuestas se traen ENTERAS y una sola vez. El filtro por tipo de
  // señal se aplica despues, en el navegador: el backend ya devuelve el
  // conjunto completo (corta en 200 y hoy hay 92), asi que pedirle una
  // consulta por cada pildora seria una vuelta al servidor para reordenar
  // datos que ya estan en pantalla.
  // La capacidad EXIGE un dia (el backend responde 400 sin el), asi que el
  // tablero abre con hoy. Es una lectura mas, no una pantalla nueva: el
  // bloque de tecnicos necesita quien trabaja hoy y cuanto tiene encima.
  const hoy = new Date().toISOString().slice(0, 10);

  //  LA PANTALLA NO ESPERA A LA CONSULTA MAS LENTA  --  09/10/2026
  //  --------------------------------------------------------------
  //  MEDIDO en dos grabaciones distintas: '/supervisor-noc/__data.json'
  //  tardaba 22.044 ms y 22.214 ms. En las mismas sesiones, TODAS las demas
  //  peticiones --incluido '/centro-mando', que devuelve 70 KB-- estaban por
  //  debajo de 600 ms. O sea que no era la red, ni el frontend, ni la base en
  //  general: era UNA de las cinco consultas de aqui, y las otras cuatro
  //  esperaban por ella.
  //
  //  Esperarlas a las cinco significa que la pantalla tarda lo que tarde la
  //  peor. Y la peor candidata es 'leerAutonomia', que le pregunta AL MOTOR y
  //  no tiene tiempo limite: si el motor esta ocupado --el ciclo diagnostica
  //  hasta quince equipos de ~10 s cada uno-- esta espera no termina.
  //
  //  Ahora se espera SOLO lo que hace falta para que la pantalla sirva:
  //
  //    propuestas   la bandeja. Es a lo que la persona viene.
  //    actividad    medida en 208 ms, y es barata.
  //
  //  Lo demas --los ocho bloques de indicadores, la autonomia y la
  //  capacidad-- viaja como PROMESA. SvelteKit la transmite cuando resuelve,
  //  y la pantalla ya se pinto. Los bloques que las usan muestran mientras
  //  tanto su estado de carga, que ya existia para cuando un dato no llega.
  //
  //  NO SE PIERDE NINGUN DATO: llegan todos, solo que despues. Y si uno falla,
  //  falla solo: hoy un fallo de la autonomia se llevaba la pantalla entera.
  const [todas, actividad] = await Promise.all([
    listarPropuestas({ cookies }),
    leerActividad({ cookies })
  ]);

  //  SIN 'await'. Cada una lleva su propio '.catch' porque una promesa
  //  rechazada que nadie atrapa tumba la respuesta entera -- y el contrato de
  //  estas tres funciones es devolver su error adentro, no levantarlo.
  const indicadores = leerIndicadores({ cookies }, dias ?? undefined)
    .catch((e) => ({ datos: null, error: { mensaje: String(e?.message ?? e) } }));
  const autonomia = leerAutonomia(locals, fetch)
    .catch((e) => ({ estado: null, permitido: null, historial: [],
                     motivo: `No se pudo consultar el motor: ${e?.message ?? e}` }));
  const capacidad = leerCapacidad({ cookies }, hoy)
    .catch((e) => ({ personas: [], error: { mensaje: String(e?.message ?? e) } }));

  return {
    puedeVer: true,
    rol,
    org: locals.org?.name ?? null,
    usuario: locals.user?.email ?? null,
    //  LAS TRES LENTAS VIAJAN COMO PROMESA, y la pagina las espera adentro.
    //  'indicadores' se resuelve a la forma que la pantalla ya esperaba
    //  --{datos, error, resumen}-- para que el componente no tenga que saber
    //  que antes venia resuelta.
    indicadores: indicadores.then((i) => ({
      datos: i?.datos ?? null,
      error: i?.error ?? null,
      resumen: resumenOperativo(i?.datos)
    })),
    hallazgos: todas,
    autonomia,
    dia: hoy,
    capacidad,
    actividad
  };
}

/**
 * NINGUNA DE ESTAS ACCIONES EJECUTA NADA CONTRA UN SISTEMA EXTERNO.
 *
 * 'ciclo' y 'asistente' escriben filas de PropuestaSupervisor y sus renglones
 * de auditoria. 'revisar' y 'cancelar' mueven el estado de una propuesta.
 * Aceptar significa "el Jefe de Operaciones esta de acuerdo", nunca "se hizo":
 * el contrato del backend devuelve `ejecutada: false` en las dos, y el estado
 * 'ejecutada' no existe en el modelo.
 *
 * @type {import('./$types').Actions}
 */
export const actions = {
  async ciclo({ cookies, locals }) {
    if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
      return fail(403, { error: 'Solo el Jefe de Operaciones puede correr el ciclo.' });
    }
    try {
      const r = await correrCiclo({ cookies });
      return {
        ok: true,
        tipo: 'ciclo',
        resumen: r?.resumen ?? null,
        shadow_mode: r?.shadow_mode ?? null,
        acciones_ejecutadas: r?.acciones_ejecutadas ?? 0
      };
    } catch (/** @type {any} */ err) {
      const e = traducirError(err, 'el ciclo de análisis');
      return fail(e.status ?? 502, { error: e.mensaje });
    }
  },

  async asistente({ cookies, locals, request }) {
    if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
      return fail(403, { error: 'Solo el Jefe de Operaciones puede correr un asistente.' });
    }
    const datos = await request.formData();
    const dominio = String(datos.get('dominio') ?? '');
    try {
      const r = await correrAsistente({ cookies }, dominio);
      return { ok: true, tipo: 'asistente', dominio, asistente: r };
    } catch (/** @type {any} */ err) {
      const e = traducirError(err, 'el asistente de ' + dominio);
      return fail(e.status ?? 502, { error: e.mensaje });
    }
  },

  async revisar({ cookies, locals, request }) {
    if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
      return fail(403, { error: 'Solo el Jefe de Operaciones puede revisar una propuesta.' });
    }
    const datos = await request.formData();
    const id = String(datos.get('id') ?? '');
    const decision = String(datos.get('decision') ?? '');
    const comentario = String(datos.get('comentario') ?? '');

    // La misma regla que RevisionSerializer.validate, adelantada para que el
    // motivo se pida en la pantalla y no vuelva como un 400 sin contexto. El
    // backend la sigue aplicando: esta copia es comodidad, no la garantia.
    if ((decision === 'rechazada' || decision === 'modificada') && !comentario.trim()) {
      return fail(400, { error: 'Rechazar o modificar exige decir por qué.', id });
    }

    try {
      const r = await revisarPropuesta({ cookies }, id, { decision, comentario });
      return {
        ok: true,
        tipo: 'revision',
        id,
        decision,
        // Viajan tal cual los devuelve el backend. 'ejecutada' conserva su
        // significado -- si una accion salio de verdad -- y ahora puede ser
        // true: el cierre de un caso desincronizado es la unica que ejecuta.
        //
        // 'motivo' es una CLAVE, no prosa: la pantalla distingue "el sistema
        // esta detenido" de "el caso cambio" sin interpretar un texto.
        ejecutada: r?.ejecutada ?? false,
        motivo: r?.motivo ?? "",
        detalle: r?.detalle ?? "",
        aviso: r?.aviso ?? null
      };
    } catch (/** @type {any} */ err) {
      const e = traducirError(err, 'la revisión');
      return fail(e.status ?? 502, { error: e.mensaje, id });
    }
  },

  async cancelar({ cookies, locals, request }) {
    if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
      return fail(403, { error: 'Solo el Jefe de Operaciones puede cancelar una propuesta.' });
    }
    const datos = await request.formData();
    const id = String(datos.get('id') ?? '');
    const motivo = String(datos.get('motivo') ?? '');

    // Obligatorio en el backend (CancelacionSerializer) y con razon: cancelar
    // sin decir por que deja una auditoria que no explica nada.
    if (!motivo.trim()) {
      return fail(400, { error: 'Cancelar exige decir por qué la condición ya no aplica.', id });
    }

    try {
      const r = await cancelarPropuesta({ cookies }, id, motivo);
      return { ok: true, tipo: 'cancelacion', id, ejecutada: r?.ejecutada ?? false };
    } catch (/** @type {any} */ err) {
      const e = traducirError(err, 'la cancelación');
      return fail(e.status ?? 502, { error: e.mensaje, id });
    }
  }
};
