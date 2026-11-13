import { fail } from '@sveltejs/kit';

import { leerDiaPublicado } from '$lib/server/v2/dia-publicado.js';
import { hoyDeLaEmpresa } from '$lib/server/v2/hoy-de-la-empresa.js';
import {
  guardarConfiguracionDeMaterial,
  leerConfiguracionDeMaterial,
  leerMaterialDelDia
} from '$lib/server/v2/material-del-dia.js';
import { mensajeDeError } from '$lib/server/v2/mensaje-de-error.js';
import { aprobarYCerrar, cerrarAprobada, devolverAlTecnico } from '$lib/server/v2/revision-del-cierre.js';
import { leerCerradas } from '$lib/server/v2/cerradas.js';
import { rangoDeCerradas } from '$lib/supervisor/dia-publicado.js';
import {
  cuerpoDeSeguimiento,
  guardarConfiguracionDeSeguimiento,
  leerConfiguracionDeSeguimiento
} from '$lib/server/v2/configuracion-de-seguimiento.js';
import {
  cuerpoDeMarcaDeAgua,
  guardarMarcaDeAgua,
  leerMarcaDeAgua
} from '$lib/server/v2/marca-de-agua.js';
import { cuerpoDeConfiguracion } from '$lib/supervisor/material-del-dia.js';

/**
 * Programación — lo que quedó publicado un día (28/10/2026).
 *
 * Pedido del usuario: «cuando el supervisor publique, salga en Programación lo
 * que publicó», con esta pantalla después de Despacho. Despacho es lo que
 * FALTA; esto es lo que QUEDÓ: por cuadrilla, cada orden con quién la asignó
 * (el Supervisor o una persona) y a qué hora, y si al técnico le llegó el
 * aviso.
 *
 * Y EL MATERIAL DEL DÍA (28/10/2026, SPEC/objetivos/material-del-dia.md): qué
 * kit le tocaría a cada cuadrilla, de qué bodega, y qué falta. Fase 1: solo
 * propone; lo único que se escribe desde acá es la configuración (qué kit
 * lleva cada labor y de qué bodega carga cada cuadrilla).
 *
 * La pantalla de antes —los planes semanales— vive en
 * /supervisor-noc/planes-semanales, enlazada desde acá.
 *
 * Solo quien gestiona: muestra el trabajo de todas las cuadrillas y el nombre
 * de cada técnico (el backend lo exige igual).
 */

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/** @type {import('./$types').PageServerLoad} */
export async function load({ url, cookies, locals }) {
  const rol = /** @type {any} */ (locals).profile?.role ?? null;
  if (!ROLES_GESTION.has(rol)) {
    return {
      puedeVer: false, dia: '', hoy: '', publicado: null, error: false,
      material: null, errorMaterial: false, configuracion: null, seguimiento: null,
      vista: 'hoy', rango: 'hoy', cerradas: null, errorCerradas: false
    };
  }

  //  Hoy en el reloj de la EMPRESA, no en el del servidor (UTC).
  const pedido = (url.searchParams.get('dia') ?? '').trim();
  //  EL HOY DE LA EMPRESA SE CALCULA UNA VEZ Y VIAJA (01/11/2026). La pantalla
  //  necesita saber si lo que mira es HOY --el mapa solo tiene sentido para
  //  hoy-- y no puede deducirlo: el navegador del supervisor puede estar en
  //  otra zona, y fijar una en el codigo rompe la regla de que lo que varia
  //  por empresa es configuracion (CLAUDE.md §3.3). Antes el mapa comparaba
  //  contra «America/Bogota» escrito a mano y no aparecia nunca si los dos
  //  relojes no coincidian.
  const hoy = await hoyDeLaEmpresa(locals, cookies);
  const dia = /^\d{4}-\d{2}-\d{2}$/.test(pedido) ? pedido : hoy;

  //  LA PESTAÑA CERRADAS (30/10/2026): lo que ya se cerró, en el rango que
  //  se elija, contado desde el día que se mira.
  if (url.searchParams.get('vista') === 'cerradas') {
    const pedidoRango = url.searchParams.get('rango') ?? 'hoy';
    const rango = ['hoy', 'ayer', '7d'].includes(pedidoRango) ? pedidoRango : 'hoy';
    const { desde, hasta } = rangoDeCerradas(rango, dia);
    const c = await leerCerradas({ cookies }, desde, hasta);
    return {
      puedeVer: true, dia, vista: 'cerradas', rango,
      cerradas: c.cerradas, errorCerradas: c.error,
      publicado: null, error: false, material: null, errorMaterial: false,
      configuracion: null, seguimiento: null
    };
  }
  const [dp, mat, conf, seg] = await Promise.all([
    leerDiaPublicado({ cookies }, dia),
    leerMaterialDelDia({ cookies }, dia),
    leerConfiguracionDeMaterial({ cookies }),
    leerConfiguracionDeSeguimiento({ cookies })
  ]);
  return {
    puedeVer: true,
    dia,
    hoy,
    publicado: dp.publicado,
    error: dp.error,
    material: mat.material,
    errorMaterial: mat.error,
    configuracion: conf.configuracion,
    //  Lo que el Supervisor hace solo (30/10/2026): recordar y cerrar.
    seguimiento: seg.configuracion,
    //  Qué dice la marca de agua de las fotos de campo (12/11/2026).
    marcaDeAgua: (await leerMarcaDeAgua({ cookies })).configuracion,
    vista: 'hoy', rango: 'hoy', cerradas: null, errorCerradas: false
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  material: async ({ request, cookies, locals }) => {
    const rol = /** @type {any} */ (locals).profile?.role ?? null;
    if (!ROLES_GESTION.has(rol)) return fail(403, { error: 'Esto es para quien gestiona.' });
    try {
      await guardarConfiguracionDeMaterial({ cookies }, cuerpoDeConfiguracion(await request.formData()));
      return { hecho: 'Quedó guardado de dónde y qué carga cada cuadrilla.' };
    } catch (e) {
      return fail(400, { error: mensajeDeError(e) });
    }
  },

  //  LA MARCA DE AGUA DE LAS FOTOS (12/11/2026). El logo y el nombre salen
  //  del perfil de la empresa; acá solo se decide qué se estampa y cómo.
  marcaDeAgua: async ({ request, cookies, locals }) => {
    const rol = /** @type {any} */ (locals).profile?.role ?? null;
    if (!ROLES_GESTION.has(rol)) return fail(403, { de: 'marcaDeAgua', error: 'Esto es para quien gestiona.' });
    try {
      const r = await guardarMarcaDeAgua({ cookies }, cuerpoDeMarcaDeAgua(await request.formData()));
      //  EL MENSAJE DICE EL ESTADO QUE QUEDÓ, no «guardado» a secas: la
      //  diferencia entre prendida y apagada es la que importa, y la persona
      //  acaba de tocar varias casillas.
      if (!r?.activa) return { de: 'marcaDeAgua', hecho: 'Guardado. Las fotos salen sin marca.' };
      //  Y AVISA EL CASO QUE DEJA UNA MARCA SIN LOGO: prender «el logo» sin
      //  haberlo cargado produce una marca a la que le falta justo lo que la
      //  persona creía estar poniendo, y nada se lo diría.
      const falta = r?.mostrar_logo && !r?.logo_cargado
        ? ' Falta cargar el logo en el perfil de la empresa: por ahora sale sin logo.'
        : '';
      return { de: 'marcaDeAgua', hecho: `Guardado. Las fotos nuevas salen con marca.${falta}` };
    } catch (e) {
      return fail(400, { de: 'marcaDeAgua', error: mensajeDeError(e) });
    }
  },

  //  LO QUE EL SUPERVISOR HACE SOLO (30/10/2026): recordarle al técnico. Que
  //  cierre solo se le delega desde su chat, no desde acá.
  seguimiento: async ({ request, cookies, locals }) => {
    const rol = /** @type {any} */ (locals).profile?.role ?? null;
    if (!ROLES_GESTION.has(rol)) return fail(403, { de: 'seguimiento', error: 'Esto es para quien gestiona.' });
    try {
      const r = await guardarConfiguracionDeSeguimiento({ cookies }, cuerpoDeSeguimiento(await request.formData()));
      //  EL MENSAJE DICE LA CADENCIA, NO SOLO QUE GUARDÓ (11/11/2026): el
      //  campo de minutos no se manda cuando quedó vacío, así que «guardado»
      //  sin el número dejaría al usuario sin saber con qué valor quedó.
      const cada = Number(r?.repetir_recordatorio_cada_minutos ?? 0);
      const insiste = Number.isFinite(cada) && cada > 0
        ? ` Vuelve a avisarle cada ${cada} minutos hasta que reporte.`
        : ' Avisa una sola vez por atraso.';
      return {
        de: 'seguimiento',
        hecho: r?.recordar_al_tecnico
          ? `Guardado. El Supervisor le recuerda al técnico la orden sin reporte.${insiste}`
          : 'Guardado. El Supervisor ya no le recuerda al técnico.'
      };
    } catch (e) {
      return fail(400, { de: 'seguimiento', error: mensajeDeError(e) });
    }
  },

  //  LA REVISIÓN DEL CIERRE (30/10/2026, SPEC/objetivos/revision-del-cierre.md):
  //  el Supervisor indica, y esto es la persona confirmándolo.
  aprobar: async ({ request, cookies, locals }) => {
    const rol = /** @type {any} */ (locals).profile?.role ?? null;
    if (!ROLES_GESTION.has(rol)) return fail(403, { de: 'revision', error: 'Esto es para quien gestiona.' });
    const f = await request.formData();
    const orden = String(f.get('orden') ?? '');
    if (!orden) return fail(400, { de: 'revision', error: 'Falta la orden.' });
    try {
      const r = await aprobarYCerrar({ cookies }, {
        orden,
        vuelta: String(f.get('vuelta') ?? '1'),
        observacion: `Aprobada en Programación. El Supervisor dijo: ${String(f.get('veredicto') ?? '')}`
      });
      //  El ticket del ISP puede no cerrarse sin que la aprobación deje de
      //  ser cierta (`campo/services/cierre_en_isp.py`): se dice.
      return { de: 'revision', hecho: r.ticketIsp?.estado === 'no_cerrado'
        ? 'Aprobada y cerrada en Dexter. El ticket del ISP no se pudo cerrar: quedó anotado en la orden.'
        : 'Aprobada y cerrada.' };
    } catch (e) {
      return fail(400, { de: 'revision', error: mensajeDeError(e, 'No se pudo aprobar.') });
    }
  },

  //  APROBADA Y SIN CERRAR (30/10/2026): solo falta cerrarla.
  cerrar: async ({ request, cookies, locals }) => {
    const rol = /** @type {any} */ (locals).profile?.role ?? null;
    if (!ROLES_GESTION.has(rol)) return fail(403, { de: 'revision', error: 'Esto es para quien gestiona.' });
    const f = await request.formData();
    const orden = String(f.get('orden') ?? '');
    if (!orden) return fail(400, { de: 'revision', error: 'Falta la orden.' });
    try {
      await cerrarAprobada({ cookies }, { orden, vuelta: String(f.get('vuelta') ?? '1') });
      return { de: 'revision', hecho: 'Cerrada. Ya está en Cerradas.' };
    } catch (e) {
      return fail(400, { de: 'revision', error: mensajeDeError(e, 'No se pudo cerrar.') });
    }
  },

  devolver: async ({ request, cookies, locals }) => {
    const rol = /** @type {any} */ (locals).profile?.role ?? null;
    if (!ROLES_GESTION.has(rol)) return fail(403, { de: 'revision', error: 'Esto es para quien gestiona.' });
    const f = await request.formData();
    const orden = String(f.get('orden') ?? '');
    const requisitos = f.getAll('requisito').map(String).filter(Boolean);
    const observacion = String(f.get('observacion') ?? '').trim();
    if (!orden) return fail(400, { de: 'revision', error: 'Falta la orden.' });
    if (!requisitos.length) return fail(400, { de: 'revision', error: 'Marcá qué tiene que rehacer.' });
    if (!observacion) return fail(400, { de: 'revision', error: 'Decí por qué se devuelve.' });
    try {
      await devolverAlTecnico({ cookies }, {
        orden, vuelta: String(f.get('vuelta') ?? '1'), requisitos, observacion
      });
      return { de: 'revision', hecho: 'Devuelta al técnico. Le llega el aviso con lo que tiene que rehacer.' };
    } catch (e) {
      return fail(400, { de: 'revision', error: mensajeDeError(e, 'No se pudo devolver.') });
    }
  }
};
