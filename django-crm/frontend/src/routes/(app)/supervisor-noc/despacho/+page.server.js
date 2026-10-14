import { fail } from '@sveltejs/kit';
import { proponerReparto, leerPersonasDeCampo, leerZonasConocidas } from '$lib/server/v2/cuadrillas.js';
import {
  leerPlantillasDeTrabajo,
  leerCasosDespachables,
  despacharACampo
} from '$lib/server/v2/despacho.js';
import { correrCiclo } from '$lib/server/v2/supervisor-noc.js';

/** El mismo conjunto que `campo/permissions.py::ROLES_GESTION` y que la
 *  pantalla de Pendientes. Inventar uno propio acá los separaría en silencio
 *  el día que alguno cambie. */
const ROLES_GESTION = new Set(['ADMIN', 'SUPERVISOR', 'OPERACIONES']);

/**
 * CUÁNTOS TÉCNICOS VAN A CADA COSA  --  13/10/2026
 *
 * El reparto ya decide a quién le toca qué. Lo que faltaba era poder verlo
 * antes de autorizar: cuántas cuadrillas salen a correctivos y cuántas a
 * instalaciones, y cuánto trabajo no entró en ninguna.
 *
 * SE CUENTA ACÁ Y NO EN EL BACKEND a propósito: es una lectura de la misma
 * propuesta que ya viaja, no un dato nuevo. Pedirle al backend que además
 * cuente sería una segunda versión del mismo número, y el día que difieran
 * nadie sabría cuál mirar.
 */
function conteosDel(propuesta) {
  if (!propuesta) return null;
  const porLabor = {};
  let ordenes = 0;
  const cuadrillasPorLabor = {};

  for (const a of propuesta.asignaciones ?? []) {
    for (const o of a.ordenes ?? []) {
      const labor = o?.labor || 'sin clasificar';
      porLabor[labor] = (porLabor[labor] ?? 0) + 1;
      ordenes += 1;
      (cuadrillasPorLabor[labor] ??= new Set()).add(a?.cuadrilla?.id ?? a?.cuadrilla);
    }
  }

  return {
    ordenes,
    cuadrillas: (propuesta.asignaciones ?? []).length,
    porLabor: Object.entries(porLabor)
      .map(([labor, n]) => ({
        labor,
        ordenes: n,
        cuadrillas: cuadrillasPorLabor[labor]?.size ?? 0
      }))
      .sort((a, b) => b.ordenes - a.ordenes),
    //  LO QUE NO ENTRÓ, nombrado por su motivo. Un total que no cuadra con la
    //  suma es exactamente lo que una persona tiene que ver antes de aprobar.
    sinZona: (propuesta.sin_zona ?? []).length,
    sinCuadrilla: (propuesta.sin_cuadrilla ?? []).length,
    sobrantes: (propuesta.sobrantes ?? []).length,
    sinClasificar: (propuesta.sin_clasificar ?? []).length,
    //  Asignadas a mano por una persona: el reparto no las toca.
    aMano: (propuesta.a_mano ?? []).length
  };
}

/**
 * Despacho a campo — Supervisor NOC.
 *
 * La pantalla que faltaba. `POST /campo/trabajos/crear/` existía y **nadie lo
 * llamaba**: las órdenes solo se podían crear por API directa, así que el ciclo
 * de la madrugada no tenía qué repartir y la clasificación no tenía dónde
 * ejercitarse.
 *
 * LA FICHA SE PIDE, NO VIENE SIEMPRE. Traer la evidencia de cada caso es una
 * llamada al motor por caso —que a su vez habla con WispHub y SmartOLT— y abrir
 * la lista no puede costar veinticinco viajes de red. Se piden con `?ficha=1`,
 * cuando quien mira ya decidió que va a despachar.
 */

/** @type {import('./$types').PageServerLoad} */
export async function load({ url, cookies }) {
  const conFicha = url.searchParams.get('ficha') === '1';

  //  El día del reparto. Hoy por defecto: es el que una persona mira cuando
  //  abre la pantalla, y pedir una fecha antes de mostrar nada sería un paso
  //  que casi siempre termina en el mismo valor.
  const dia = url.searchParams.get('dia') || new Date().toISOString().slice(0, 10);

  const [plantillas, casos, reparto, personas, barrios] = await Promise.all([
    leerPlantillasDeTrabajo({ cookies }),
    leerCasosDespachables({ cookies }, conFicha),
    proponerReparto({ cookies }, dia),
    leerPersonasDeCampo({ cookies }),
    leerZonasConocidas({ cookies })
  ]);

  return {
    conFicha,
    dia,
    //  LA PROPUESTA DEL REPARTO, tal como la calcula el motor que ya existe.
    //  No se recalcula aquí ni se reordena: el criterio --lo que vence
    //  primero, después lo más viejo, respetando las zonas de cada cuadrilla--
    //  vive en 'campo/reparto.py' y una segunda copia se desincronizaría.
    reparto: reparto.propuesta,
    repartoError: reparto.error ? (reparto.motivo || 'No se pudo calcular la propuesta.') : null,
    conteos: conteosDel(reparto.propuesta),
    plantillas: plantillas.plantillas,
    labores: plantillas.labores,
    plantillasSinClasificar: plantillas.sinClasificar,
    casos: casos.casos,
    tope: casos.tope,
    sinAprobados: casos.sinAprobados,
    //  Los barrios ya mapeados, para ofrecerlos mientras se escribe.
    barriosConocidos: barrios.localidades,
    //  A quien se le puede asignar A MANO: solo quien tiene cuenta, porque es
    //  quien recibe la orden en un telefono. Un auxiliar sin celular integra
    //  la cuadrilla pero no puede ser el responsable de una orden.
    tecnicos: (personas.personas ?? [])
      .filter((p) => p.activa && p.tiene_cuenta && p.profile)
      .map((p) => ({ profile: p.profile, nombre: p.nombre })),
    // NO SE INVENTA UNA LISTA VACÍA CUANDO LA LECTURA FALLÓ. Una empresa sin
    // casos abiertos y una consulta que no respondió se dibujan distinto.
    error: plantillas.error || casos.error
  };
}

/**
 * Traduce lo que devuelve el backend a una frase, sin inventar una.
 *
 * El error de `apiRequest` trae `status` y `body`, no `data`: leyendo `e.data`
 * la frase del backend nunca llegaba y se veía «HTTP 500: Internal Server
 * Error» crudo (13/10/2026).
 */
function mensajeDe(e) {
  const detalle = e?.body?.detalle || e?.message;
  return typeof detalle === 'string' && detalle.trim()
    ? detalle.trim()
    : 'No se pudo despachar.';
}

/** @type {import('./$types').Actions} */
export const actions = {
  /**
   * Hace que el Supervisor mire AHORA.
   *
   * El ciclo corre solo una vez por hora, pero SOLO si la empresa le delegó
   * «Revisar solo, una vez por hora». Sin esa delegación el Supervisor espera
   * a que alguien lo despierte — y sin propuestas aceptadas, esta pantalla
   * queda vacía sin que nada explique por qué.
   *
   * Esto lo despierta. No ejecuta nada: `correr_ciclo` solo escribe filas de
   * `PropuestaSupervisor`, que una persona después acepta o rechaza.
   */
  ciclo: async ({ cookies, locals }) => {
    if (!ROLES_GESTION.has(/** @type {any} */ (locals).profile?.role)) {
      return fail(403, {
        error: 'Solo el Jefe de Operaciones puede hacer que el Supervisor mire.'
      });
    }
    try {
      const r = await correrCiclo({ cookies });
      const nuevas = r?.resumen?.propuestas_nuevas ?? r?.resumen?.nuevas ?? null;
      return {
        hecho: nuevas === null
          ? 'El Supervisor revisó la operación. Mirá Pendientes por revisión.'
          : `El Supervisor dejó ${nuevas} ${nuevas === 1 ? 'propuesta' : 'propuestas'}. ` +
            'Las que aceptes aparecen acá.'
      };
    } catch (e) {
      return fail(502, { error: mensajeDe(e) });
    }
  },

  /**
   * Manda el caso a campo.
   *
   * La plantilla la elige quien despacha: la sugerencia viene marcada pero no
   * decide. Es el mismo corte que el resto del Supervisor NOC — observa,
   * analiza, propone.
   */
  despachar: async ({ request, cookies }) => {
    const f = await request.formData();
    const caseId = String(f.get('case_id') ?? '').trim();
    const plantilla = String(f.get('work_type_version_id') ?? '').trim();
    if (!plantilla) return fail(400, { error: 'Elegí con qué plantilla va.' });

    //  LA CLAVE DE IDEMPOTENCIA LA ARMA EL SERVIDOR, no el navegador: una
    //  clave nueva por intento es un identificador único, no una clave
    //  idempotente, y un doble clic crearía dos órdenes. Con el caso y la
    //  plantilla, el mismo despacho repetido es la misma clave; una segunda
    //  visita deliberada lleva otra plantilla, u otra fecha.
    const programada = String(f.get('programada_para') ?? '').trim();
    const clave = `despacho:${caseId || 'manual'}:${plantilla}:${programada}`;

    try {
      const r = await despacharACampo({ cookies }, {
        work_type_version_id: plantilla,
        case_id: caseId || undefined,
        cliente_nombre: String(f.get('cliente_nombre') ?? '').trim(),
        cliente_telefono: String(f.get('cliente_telefono') ?? '').trim(),
        cliente_direccion: String(f.get('cliente_direccion') ?? '').trim(),
        cliente_detalle_acceso: String(f.get('detalle_acceso') ?? '').trim(),
        //  DE DÓNDE ES EL TRABAJO. Sin esto la orden nace sin zona y el
        //  reparto la deja en `sin_zona` para siempre: nunca llega a una
        //  cuadrilla, y el síntoma —«no se asignó»— no señala acá.
        zona: String(f.get('zona') ?? '').trim() || undefined,
        prioridad: String(f.get('prioridad') ?? '').trim() || undefined,
        resumen: String(f.get('resumen') ?? '').trim() || undefined,
        programada_para: programada || undefined,
        //  ASIGNAR A MANO (opcional). Vacío = la reparte el sistema. Con valor,
        //  el reparto la respeta y no la mueve (campo/reparto.py).
        tecnico_profile_id: String(f.get('tecnico_profile_id') ?? '').trim() || undefined
      }, clave);

      const numero = r?.orden?.numero;
      const quien = r?.orden?.tecnico_principal?.nombre;
      return {
        hecho: (numero ? `Orden #${numero} despachada` : 'Orden despachada') +
          (quien
            ? `, asignada a ${quien}. El reparto no la va a mover.`
            : '. Queda SIN ASIGNAR hasta que se publique el reparto.'),
        numero
      };
    } catch (e) {
      return fail(e?.status && e.status < 500 ? e.status : 502, { error: mensajeDe(e) });
    }
  }
};
