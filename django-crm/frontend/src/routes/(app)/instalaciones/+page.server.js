/**
 * La bandeja de solicitudes de instalación.
 *
 * Acá alguien decide si el servicio puede llegar a esa dirección. Aprobar
 * mueve el ticket de WispHub al equipo que instala; rechazar exige un motivo,
 * porque el cliente va a preguntar y alguien va a tener que contestarle.
 */
import { fail } from '@sveltejs/kit';
import { crearEnElIsp, decidir, leerBandeja, reintentar, resolverAlta } from '$lib/server/v2/solicitudes.js';
import { aprobarInstalacion, leerPorActivar, prepararContratoProveedor, subirFotosDelTrabajo } from '$lib/server/v2/instalaciones-por-activar.js';
import { devolverAlTecnico } from '$lib/server/v2/revision-del-cierre.js';
import { mensajeDeError } from '$lib/server/v2/mensaje-de-error.js';

/** @type {import('./$types').PageServerLoad} */
export async function load({ cookies, url }) {
  //  LA PESTAÑA «POR ACTIVAR» (26/11/2026): las instalaciones que finalizó el
  //  técnico y esperan a una persona. Ver campo/instalacion.py.
  if (url.searchParams.get('vista') === 'por_activar') {
    const { instalaciones, trabadas, error } = await leerPorActivar(cookies);
    return { vista: 'por_activar', instalaciones, trabadas, error, solicitudes: [], estado: '', automatica: false, sinPermiso: false };
  }
  const estado = url.searchParams.get('estado') ?? '';
  // Las aprobadas por Dexter (pre-factibilidad) son su propia pestaña.
  const automatica = url.searchParams.get('automatica') === '1';
  const { solicitudes, error, sinPermiso } = await leerBandeja(cookies, estado, { automatica });
  // 'sinPermiso' VIAJA HASTA LA PÁGINA (12/11/2026): sin él, un 403 se veía
  // como "No hay solicitudes esperando" y nadie sabía por qué.
  return { solicitudes, error, estado, automatica, sinPermiso: Boolean(sinPermiso) };
}

/** @type {import('./$types').Actions} */
export const actions = {
  //  APROBAR UNA INSTALACIÓN = ACTIVARLA en el proveedor (26/11/2026). El
  //  servidor decide si se puede; acá solo se pide y se dice qué contestó.
  async aprobarInstalacion({ request, cookies }) {
    const form = await request.formData();
    const orden = form.get('orden')?.toString() ?? '';
    if (!orden) return fail(400, { error: 'Falta la orden.', de: 'instalacion' });
    try {
      await aprobarInstalacion(cookies, orden);
      return { de: 'instalacion', orden, hecho: 'Aprobada. Se está activando en el proveedor: al quedar activa, al técnico le llega que valide el servicio y la entregue.' };
    } catch (e) {
      const err = /** @type {any} */ (e);
      return fail(err?.status === 409 ? 409 : 400, { de: 'instalacion', orden, error: mensajeDeError(err) });
    }
  },

  //  EL CONTRATO DEL PROVEEDOR (26/11/2026): pedir otra vez que se prepare.
  async prepararContratoProveedor({ request, cookies }) {
    const form = await request.formData();
    const contrato = form.get('contrato')?.toString() ?? '';
    const orden = form.get('orden')?.toString() ?? '';
    if (!contrato) return fail(400, { de: 'instalacion', orden, error: 'Falta el contrato.' });
    try {
      await prepararContratoProveedor(cookies, contrato);
      return { de: 'instalacion', orden, hecho: 'Pedido. El contrato del proveedor se está preparando otra vez.' };
    } catch (e) {
      const err = /** @type {any} */ (e);
      return fail(err?.status === 409 ? 409 : 400, { de: 'instalacion', orden, error: mensajeDeError(err) });
    }
  },

  //  LAS FOTOS DEL TRABAJO (26/11/2026): volver a subirlas a los archivos del
  //  cliente cuando no quedaron.
  async subirFotosDelTrabajo({ request, cookies }) {
    const form = await request.formData();
    const contrato = form.get('contrato')?.toString() ?? '';
    const orden = form.get('orden')?.toString() ?? '';
    if (!contrato) return fail(400, { de: 'instalacion', orden, error: 'Falta el contrato.' });
    try {
      await subirFotosDelTrabajo(cookies, contrato);
      return { de: 'instalacion', orden, hecho: 'Pedido. Las fotos del trabajo se están subiendo otra vez.' };
    } catch (e) {
      const err = /** @type {any} */ (e);
      return fail([403, 409].includes(err?.status) ? err.status : 400,
        { de: 'instalacion', orden, error: mensajeDeError(err) });
    }
  },

  //  DEVOLVERLA AL TÉCNICO: lo mismo que en Programación (la vuelta es la
  //  clave de idempotencia).
  async devolverInstalacion({ request, cookies }) {
    const form = await request.formData();
    const orden = form.get('orden')?.toString() ?? '';
    const vuelta = form.get('vuelta')?.toString() ?? '1';
    const requisitos = form.getAll('requisito').map(String).filter(Boolean);
    const observacion = form.get('observacion')?.toString()?.trim() ?? '';
    if (!orden) return fail(400, { de: 'instalacion', error: 'Falta la orden.' });
    if (!requisitos.length) return fail(400, { de: 'instalacion', orden, error: 'Marca qué foto tiene que volver a tomar.' });
    if (!observacion) return fail(400, { de: 'instalacion', orden, error: 'Escribe por qué la devuelves: es lo que lee el técnico.' });
    try {
      await devolverAlTecnico({ cookies }, { orden, vuelta, requisitos, observacion });
      return { de: 'instalacion', orden, hecho: 'Devuelta al técnico, con lo que tiene que rehacer.' };
    } catch (e) {
      return fail(400, { de: 'instalacion', orden, error: mensajeDeError(e) });
    }
  },

  async decidir({ request, cookies }) {
    const form = await request.formData();
    const id = form.get('id')?.toString();
    const aprueba = form.get('aprueba')?.toString() === 'true';
    const nota = form.get('nota')?.toString()?.trim() ?? '';

    if (!id) return fail(400, { error: 'Falta la solicitud.' });
    if (!aprueba && !nota) {
      return fail(400, { error: 'Para rechazar hace falta anotar el motivo.', id });
    }
    try {
      const r = await decidir(cookies, id, aprueba, nota);
      // El fallo de la reasignación NO invalida la decisión: se muestra para
      // que alguien lo reintente, pero la solicitud ya quedó resuelta.
      // 'aviso' y 'pendientes' (12/11/2026): al rechazar, si el WhatsApp al
      // cliente no salió la pantalla tiene que decir por qué.
      return {
        decidido: true,
        id,
        estado: r.estado,
        fallo: r.fallo || '',
        aviso: r.aviso_cliente ?? null,
        pendientes: r.pendientes ?? []
      };
    } catch (/** @type {any} */ err) {
      return fail(err?.status === 403 ? 403 : 400, {
        error: err?.message || 'No se pudo guardar la decisión.',
        id
      });
    }
  },

  async reintentar({ request, cookies }) {
    const form = await request.formData();
    const id = form.get('id')?.toString();
    if (!id) return fail(400, { error: 'Falta la solicitud.' });
    try {
      const r = await reintentar(cookies, id);
      return {
        reintentado: true,
        id,
        pendientes: r.pendientes ?? [],
        aviso: r.aviso_cliente ?? null,
        fallo: r.fallo || ''
      };
    } catch (/** @type {any} */ err) {
      return fail(err?.status === 403 ? 403 : 400, {
        error: err?.message || 'No se pudo reintentar.',
        id
      });
    }
  },

  //  EL CLIENTE NO QUEDÓ CREADO EN EL PROVEEDOR, y una persona pide que se
  //  intente otra vez (25/11/2026). El backend no lo crea en esta llamada: lo
  //  encola, y la fila dice cómo va al recargar.
  async crearEnElIsp({ request, cookies }) {
    const form = await request.formData();
    const id = form.get('id')?.toString();
    const contrato = form.get('contrato')?.toString();
    if (!contrato) return fail(400, { error: 'Falta el contrato.', id });
    try {
      const r = await crearEnElIsp(cookies, contrato);
      return { altaPedida: true, id, alta: r?.contrato?.alta ?? null, estado: r?.contrato?.estado ?? '' };
    } catch (/** @type {any} */ err) {
      return fail(err?.status === 403 ? 403 : 400, {
        error: err?.message || 'No se pudo pedir que se cree al cliente.',
        id
      });
    }
  },

  //  NADIE SABE SI EL CLIENTE QUEDÓ CREADO, y gestión lo dice después de mirar
  //  en el proveedor (25/11/2026). `quedo` llega como 'si' o 'no' del botón
  //  que se tocó: cualquier otra cosa no se manda, para que un formulario a
  //  medias no se lea como «no quedó».
  async resolverAlta({ request, cookies }) {
    const form = await request.formData();
    const id = form.get('id')?.toString();
    const contrato = form.get('contrato')?.toString();
    const quedo = form.get('quedo')?.toString();
    const numero = (form.get('id_cliente')?.toString() ?? '').trim();
    if (!contrato) return fail(400, { error: 'Falta el contrato.', id });
    if (quedo !== 'si' && quedo !== 'no') return fail(400, { error: 'Di si el cliente quedó creado o no.', id });
    if (quedo === 'si' && !numero) {
      return fail(400, { error: 'Escribe el número del cliente tal como aparece en el proveedor.', id });
    }
    try {
      const r = await resolverAlta(cookies, contrato, quedo === 'si', numero);
      return { altaResuelta: true, id, estado: r?.contrato?.estado ?? '' };
    } catch (/** @type {any} */ err) {
      return fail(err?.status === 403 ? 403 : 400, {
        error: err?.message || 'No se pudo guardar la revisión.',
        id
      });
    }
  }
};
