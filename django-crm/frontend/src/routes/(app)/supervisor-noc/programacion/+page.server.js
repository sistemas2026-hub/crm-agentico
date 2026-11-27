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
import { moverOrden } from '$lib/server/v2/mover-orden.js';
import { destrabarOrden } from '$lib/server/v2/destrabar-orden.js';
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
import { cuerpoDeContrato, guardarContrato, leerContrato } from '$lib/server/v2/contrato.js';
import { cuerpoDeRangos, guardarRangos, leerOcupacion, leerRangos } from '$lib/server/v2/rangos-de-ip.js';
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
export async function load({ url, cookies, locals, fetch }) {
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
  //  LOS SEIS A LA VEZ (21/11/2026). La marca de agua y el contrato se pedían
  //  después, uno detrás del otro: la pantalla esperaba dos viajes más al
  //  backend, en fila, antes de dibujar nada. El usuario: «cuando se recarga
  //  demora en salir». Ninguno depende de otro.
  //  Y LOS RANGOS DE IP (25/11/2026), del motor y no del backend: viven en la
  //  configuración del asistente. Van en la misma tanda y no tocan al
  //  proveedor: leen lo guardado.
  const [dp, mat, conf, seg, marca, contrato, rangos] = await Promise.all([
    leerDiaPublicado({ cookies }, dia),
    leerMaterialDelDia({ cookies }, dia),
    leerConfiguracionDeMaterial({ cookies }),
    leerConfiguracionDeSeguimiento({ cookies }),
    leerMarcaDeAgua({ cookies }),
    leerContrato({ cookies }),
    leerRangos(locals, fetch)
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
    marcaDeAgua: marca.configuracion,
    //  Los servidores, el NIT y las condiciones del contrato (13/11/2026).
    contrato: contrato.configuracion,
    //  De qué rangos saca IP cada servidor (25/11/2026). `null` = el motor
    //  no contestó, y la pantalla lo dice.
    rangos,
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

  //  LOS RANGOS DE IP DE CADA SERVIDOR (25/11/2026). Se leen los guardados
  //  antes de escribir para no borrar los de una zona que la pantalla no
  //  muestra (ver `cuerpoDeRangos`).
  rangos: async ({ request, locals, fetch }) => {
    const rol = /** @type {any} */ (locals).profile?.role ?? null;
    if (!ROLES_GESTION.has(rol)) return fail(403, { de: 'rangos', error: 'Esto es para quien gestiona.' });
    try {
      const actuales = await leerRangos(locals, fetch);
      if (!actuales) return fail(400, { de: 'rangos', error: 'El asistente no contestó: no se guardó nada.' });
      const f = await request.formData();
      //  UN FORMULARIO VACÍO NO BORRA LOS RANGOS (26/11/2026): la misma trampa
      //  que se llevó la configuración del contrato. Si TODOS los servidores
      //  del formulario llegan sin rangos y antes alguno tenía, no se guarda.
      const zonas = new Set([...f.keys()]
        .filter((k) => /^rango_zona_\d+$/.test(k))
        .map((k) => String(f.get(k) ?? '').trim()));
      const escritos = cuerpoDeRangos(f, []).filter((p) => p.prefijos.length).length;
      const tenian = (actuales.pools ?? []).filter((/** @type {any} */ p) =>
        zonas.has(String(p.zona_id)) && (p.prefijos ?? []).length).length;
      if (zonas.size && !escritos && tenian) {
        return fail(400, {
          de: 'rangos',
          error: 'No se guardó nada: el formulario llegó sin ningún rango y había rangos cargados (así se habrían borrado). Recarga la página e intenta de nuevo.'
        });
      }
      //  CADA CUÁNTAS HORAS SE LEEN SOLAS LAS IP TOMADAS (27/11/2026). Solo si
      //  el campo vino (la pantalla lo muestra cuando la empresa puede leer):
      //  si no, no se toca. Un número entero de 0 a 168; otra cosa no se manda.
      const crudo = f.get('ocupacion_cada_horas');
      /** @type {number | undefined} */
      let cadaHoras;
      if (crudo != null) {
        const texto = String(crudo).trim();
        if (!/^\d{1,3}$/.test(texto) || Number(texto) > 168) {
          return fail(400, {
            de: 'rangos',
            error: 'Cada cuántas horas se leen solas las IP es un número de 0 a 168 (0 = solo con el botón).'
          });
        }
        cadaHoras = Number(texto);
      }
      //  La casilla de las IP mal escritas viaja SIEMPRE como sí o no: una
      //  casilla sin marcar no llega en el formulario, y sin esto no se podría
      //  apagar.
      const r = await guardarRangos(locals, fetch, cuerpoDeRangos(f, actuales.pools ?? []),
        f.get('contar_ip_mal_escritas') != null, cadaHoras);
      const conRango = (r?.pools ?? []).filter((/** @type {any} */ p) => (p.prefijos ?? []).length).length;
      const hecho = conRango
        ? `Guardado. ${conRango} servidor${conRango === 1 ? '' : 'es'} con rangos.`
        : 'Guardado, pero ningún servidor tiene rangos: el técnico no verá IP libres y el alta no podrá crear clientes.';
      return { de: 'rangos', hecho };
    } catch (e) {
      return fail(400, { de: 'rangos', error: mensajeDeError(e) });
    }
  },

  //  Vuelve a leer del proveedor qué direcciones están tomadas. Tarda.
  leerOcupacion: async ({ locals, fetch }) => {
    const rol = /** @type {any} */ (locals).profile?.role ?? null;
    if (!ROLES_GESTION.has(rol)) return fail(403, { de: 'rangos', error: 'Esto es para quien gestiona.' });
    try {
      const r = await leerOcupacion(locals, fetch);
      const hecho = r?.completa
        ? `Leídos ${r.leidos ?? 0} clientes: ${r.direcciones_tomadas ?? 0} direcciones tomadas.`
        : 'La lectura quedó incompleta: hasta que se complete, al técnico no se le ofrecen IP.';
      return { de: 'rangos', hecho };
    } catch (e) {
      return fail(400, { de: 'rangos', error: mensajeDeError(e) });
    }
  },

  //  EL CONTRATO DE INSTALACIÓN (13/11/2026): entre qué servidores elige el
  //  técnico, el NIT y el texto de las condiciones que va en el PDF.
  contrato: async ({ request, cookies, locals }) => {
    const rol = /** @type {any} */ (locals).profile?.role ?? null;
    if (!ROLES_GESTION.has(rol)) return fail(403, { de: 'contrato', error: 'Esto es para quien gestiona.' });
    try {
      const cuerpo = cuerpoDeContrato(await request.formData());
      //  UN FORMULARIO VACÍO NO BORRA LA CONFIGURACIÓN (26/11/2026). Este
      //  formulario guarda TODO junto (servidores, NIT, condiciones, reglas).
      //  Ese día la pantalla vació sus casillas después de un guardado bueno y
      //  el siguiente guardado borró los servidores, las VLAN y las reglas de
      //  la empresa. Llegar sin ningún servidor cuando hay servidores cargados
      //  es eso, no una decisión: no se guarda nada.
      if (!cuerpo.servidores.length) {
        const actual = await leerContrato({ cookies });
        if (actual.error) {
          return fail(400, { de: 'contrato', error: 'No se pudo comprobar lo que hay guardado: no se guardó nada.' });
        }
        const n = actual.configuracion?.servidores?.length ?? 0;
        if (n > 0) {
          return fail(400, {
            de: 'contrato',
            error: `No se guardó nada: el formulario llegó sin ningún servidor y hay ${n} cargado${n === 1 ? '' : 's'} (así se habrían borrado). Recarga la página e intenta de nuevo.`
          });
        }
      }
      const r = await guardarContrato({ cookies }, cuerpo);
      const n = r?.servidores?.length ?? 0;
      //  Dice lo que quedó: sin servidores, el técnico no puede firmar.
      const hecho = n === 0
        ? 'Guardado, pero sin servidores: el técnico no podrá crear contratos hasta cargar al menos uno.'
        : `Guardado. El técnico elige entre ${n} servidor${n === 1 ? '' : 'es'}.`
          + (r?.texto_condiciones ? '' : ' Falta el texto de las condiciones: el PDF lo dirá.')
          //  Que quede dicho al guardar: es el interruptor que crea clientes
          //  en el sistema del proveedor (25/11/2026).
          + (r?.crear_en_el_isp ? ' Al firmar, el cliente se crea en el proveedor.' : '');
      return { de: 'contrato', hecho };
    } catch (e) {
      return fail(400, { de: 'contrato', error: mensajeDeError(e) });
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
  },

  //  MOVER LA ORDEN A OTRO TÉCNICO  --  14/11/2026
  //
  //  Hasta hoy no había forma de hacerlo desde ninguna pantalla: el técnico
  //  que se enfermaba a media jornada se llevaba sus órdenes con él. El
  //  backend lo resolvía entero y nadie lo llamaba (ver `mover-orden.js`).
  //
  //  EL MOTIVO ES OBLIGATORIO EN LAS DOS CAPAS: acá y en el serializer
  //  (`allow_blank=False`). El evento `reasignacion` lo guarda, y es lo único
  //  que después explica por qué un trabajo cambió de manos; un campo
  //  opcional se deja vacío siempre. Mismo criterio que la devolución.
  //
  //  Y VIAJA SIN LIMPIAR DESDE ACÁ, a propósito: el identificador que alguien
  //  escriba ahí lo borra `mover_la_orden` antes de guardar nada
  //  (`campo/services/despacho.py`). Hacerlo también en esta capa daría dos
  //  lugares donde la regla puede divergir, y el único que de verdad protege
  //  es el que está pegado a la escritura.
  //
  //  NO SE VALIDA QUE EL DESTINO SALGA HOY: eso lo decide la pantalla, que
  //  solo ofrece a quienes salen. Repetir la regla acá la pondría en dos
  //  lugares que pueden divergir, y el backend ya rechaza lo que de verdad
  //  no se puede —otra empresa, una orden cerrada o cancelada—.
  mover: async ({ request, cookies, locals }) => {
    const rol = /** @type {any} */ (locals).profile?.role ?? null;
    if (!ROLES_GESTION.has(rol)) return fail(403, { de: 'mover', error: 'Esto es para quien gestiona.' });
    const f = await request.formData();
    const orden = String(f.get('orden') ?? '');
    const profile = String(f.get('profile') ?? '').trim();
    const motivo = String(f.get('motivo') ?? '').trim();
    if (!orden) return fail(400, { de: 'mover', error: 'Falta la orden.' });
    if (!profile) return fail(400, { de: 'mover', orden, error: 'Elegí a quién se la pasás.' });
    if (!motivo) return fail(400, { de: 'mover', orden, error: 'Decí por qué se mueve.' });
    try {
      const r = await moverOrden({ cookies }, { orden, profile, motivo });
      //  NO SE AFIRMA EL AVISO, SE PREGUNTA (14/11/2026). `avisar_asignacion`
      //  sale solo si la persona es nueva en la orden
      //  (`campo/services/despacho.py:229`, decisión propia con su prueba).
      //  Devolverle la orden a quien la tenía antes, o dársela a quien ya
      //  figuraba de ayudante, no manda nada — y la pantalla lo decía igual.
      if (r?.resultado === 'sin_cambios') {
        return { de: 'mover', orden, hecho: 'Esa persona ya la tenía. No se cambió nada.' };
      }
      return { de: 'mover', orden, hecho: r?.aviso
        ? 'Movida. Le llegó el aviso al teléfono.'
        : 'Movida. No le llega aviso: ya figuraba en esta orden.' };
    } catch (e) {
      return fail(400, { de: 'mover', orden, error: mensajeDeError(e, 'No se pudo mover.') });
    }
  },

  //  DEVOLVER AL TÉCNICO UNA ORDEN QUE ÉL DETUVO  --  20/11/2026, OT #328
  //
  //  El técnico reportó un bloqueo y la orden quedó sin salida: la app no
  //  ofrece nada sobre una orden detenida (a propósito: se destraba desde la
  //  oficina), «Devolver» solo existe para lo ya completado, y el único botón
  //  que la destrababa estaba en otra pantalla. El backend lo resolvía entero
  //  (`campo/services/bloqueos.py::resolver`) y desde acá nadie lo llamaba.
  //
  //  LA ACLARACIÓN ES OBLIGATORIA Y LA ESCRIBE UNA PERSONA: es lo que el
  //  técnico lee en el aviso, y lo único que después explica por qué una
  //  orden parada volvió a andar. El servicio también la exige.
  //
  //  VUELVE AL ESTADO DESDE EL QUE SE BLOQUEÓ, que guardó la fila del bloqueo
  //  al abrirse. Acá no se elige destino: el técnico retoma donde estaba.
  destrabar: async ({ request, cookies, locals }) => {
    const rol = /** @type {any} */ (locals).profile?.role ?? null;
    if (!ROLES_GESTION.has(rol)) return fail(403, { de: 'destrabar', error: 'Esto es para quien gestiona.' });
    const f = await request.formData();
    const orden = String(f.get('orden') ?? '');
    const aclaracion = String(f.get('aclaracion') ?? '').trim();
    if (!orden) return fail(400, { de: 'destrabar', error: 'Falta la orden.' });
    if (!aclaracion) {
      return fail(400, { de: 'destrabar', orden, error: 'Escribí la aclaración: es lo que el técnico va a leer.' });
    }
    try {
      const r = await destrabarOrden({ cookies }, { orden, aclaracion });
      //  NO SE AFIRMA EL AVISO, SE PREGUNTA: una orden sin nadie asignado se
      //  destraba igual y no le llega a nadie.
      return { de: 'destrabar', orden, hecho: r?.aviso
        ? 'Devuelta al técnico. Le llega el aviso con tu aclaración.'
        : 'Ya no está detenida. No salió aviso: no tiene a nadie asignado.' };
    } catch (e) {
      return fail(400, { de: 'destrabar', orden, error: mensajeDeError(e, 'No se pudo devolver.') });
    }
  }
};
