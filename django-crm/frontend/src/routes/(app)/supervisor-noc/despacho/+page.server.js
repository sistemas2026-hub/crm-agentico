import { fail } from '@sveltejs/kit';
import { proponerReparto, leerZonasConocidas } from '$lib/server/v2/cuadrillas.js';
import {
  leerPlantillasDeTrabajo,
  leerCasosDespachables,
  despacharACampo
} from '$lib/server/v2/despacho.js';
import { correrCiclo } from '$lib/server/v2/supervisor-noc.js';
import { mensajeDeError } from '$lib/server/v2/mensaje-de-error.js';

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
    //  LA LABOR ES DE LA ASIGNACION, NO DE LA ORDEN  --  13/10/2026
    //
    //  Estaba leyendo `o.labor` de cada orden, y `_orden_json`
    //  (`campo/cuadrillas_views.py:1086`) devuelve `id, numero, cliente,
    //  direccion, zona, prioridad` y NADA MAS. O sea: `o.labor` era
    //  `undefined` SIEMPRE, el `||` lo mandaba a 'sin clasificar', y este
    //  panel --que existe justo para ver cuantas cuadrillas van a correctivos
    //  y cuantas a instalaciones-- mostraba una sola fila diciendo
    //  «N cuadrillas a sin clasificar». Con el backend en verde: ninguna
    //  prueba suya podia verlo (CLAUDE.md §6).
    //
    //  La asignacion SI la trae (`"labor": a["jornada"].labor`, linea 952), y
    //  es el lugar correcto: el reparto agrupa por `(zona, labor)`, asi que
    //  todas las ordenes de una asignacion tienen la labor de esa jornada. No
    //  se agrega `labor` a cada orden a proposito -- seria una segunda copia
    //  del mismo dato, y el dia que difieran nadie sabria cual mirar.
    //
    //  El `||` se queda, y ahora SI significa algo: una jornada sin labor
    //  declarada es una anomalia que hay que ver, no un campo que falta.
    const labor = a?.labor || 'sin clasificar';
    for (const _o of a.ordenes ?? []) {
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

  //  EL FILTRO Y LA PÁGINA VIVEN EN LA URL: un enlace copiado abre lo mismo,
  //  y volver atrás después de despachar no pierde dónde se estaba.
  const filtro = {
    q: (url.searchParams.get('q') ?? '').trim(),
    asunto: (url.searchParams.get('asunto') ?? '').trim(),
    pagina: Number.parseInt(url.searchParams.get('pagina') ?? '1', 10) || 1
  };

  const [plantillas, casos, reparto, barrios] = await Promise.all([
    leerPlantillasDeTrabajo({ cookies }),
    leerCasosDespachables({ cookies }, conFicha, filtro),
    proponerReparto({ cookies }, dia),
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
    filtro: { q: filtro.q, asunto: filtro.asunto },
    total: casos.total,
    totalSinFiltro: casos.totalSinFiltro,
    //  La que devolvió el backend, no la pedida: la recorta a lo que existe.
    pagina: casos.pagina,
    paginas: casos.paginas,
    asuntos: casos.asuntos,
    //  Los barrios ya mapeados, para ofrecerlos mientras se escribe.
    barriosConocidos: barrios.localidades,
    // NO SE INVENTA UNA LISTA VACÍA CUANDO LA LECTURA FALLÓ. Una empresa sin
    // casos abiertos y una consulta que no respondió se dibujan distinto.
    error: plantillas.error || casos.error
  };
}

/**
 * Traduce lo que devuelve el backend a una frase, sin inventar una.
 *
 * DOS SESIONES ENCONTRARON ESTO EL MISMO DIA, por caminos independientes, y
 * coincidieron en la causa: el error de `apiRequest` trae `status` y **`body`**,
 * no `data`, asi que leer `e.data.detalle` daba `undefined` siempre y la frase
 * del backend no llegaba nunca.
 *
 * Se conserva la version que delega en `mensaje-de-error.js`, que es la misma
 * correccion mas tres cosas: lee tambien `detail` (DRF) --que es la clave que
 * usan los endpoints que NO son de campo--, deja el codigo (`error`) como
 * ultimo recurso en vez de como primero, y unifica las TRES copias que habia
 * de esta funcion (despacho, cuadrillas, inventario), que leian de tres
 * lugares distintos.
 */
function mensajeDe(e) {
  return mensajeDeError(e, 'No se pudo despachar.');
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
        tecnico_profile_id: String(f.get('tecnico_profile_id') ?? '').trim() || undefined,
        //  LA CUADRILLA DEL DÍA que cubre esa zona (13/10/2026). Le llega a su
        //  gente con cuenta, como al publicar el reparto, y el reparto la respeta.
        jornada_id: String(f.get('jornada_id') ?? '').trim() || undefined
      }, clave);

      const numero = r?.orden?.numero;
      const quien = r?.orden?.tecnico_principal?.nombre;
      const conCuadrilla = Boolean(String(f.get('jornada_id') ?? '').trim());
      //  ESTE CASO YA TENIA UNA ORDEN ABIERTA, y hay que decirlo.
      //
      //  `CrearOrdenView` devuelve `ordenes_activas_del_caso` --las que ya
      //  existian ANTES de esta, calculadas en `despacho_views.py:131`-- y el
      //  comentario del backend nombra textualmente a su consumidor: «Que la
      //  UI pueda avisar "este caso ya tiene una orden activa"». La UI no lo
      //  usaba: confirmaba «Orden #1042 despachada.» y quien despacho se
      //  enteraba de la otra cuando el tecnico llamaba preguntando cual hace.
      //
      //  SE SUMA a lo que ya decia el mensaje --a quien quedo asignada y si el
      //  reparto la va a mover--, no lo reemplaza: son tres hechos distintos y
      //  los tres importan antes de que alguien salga a manejar.
      //
      //  NO se bloquea --una segunda visita al mismo caso es legitima, y el
      //  duplicado accidental lo evita la Idempotency-Key--: se NOMBRA.
      const yaHabia = Array.isArray(r?.ordenes_activas_del_caso)
        ? r.ordenes_activas_del_caso.filter((n) => n !== numero)
        : [];
      return {
        hecho: (numero ? `Orden #${numero} despachada` : 'Orden despachada') +
          (String(f.get('tecnico_profile_id') ?? '').trim() && quien
            ? `, asignada a ${quien}. El reparto no la va a mover.`
            : conCuadrilla
              ? `, asignada a la cuadrilla elegida${quien ? ` (a cargo: ${quien})` : ''}. El reparto no la va a mover.`
              : '. Queda SIN ASIGNAR hasta que se publique el reparto.') +
          (yaHabia.length
            ? ` Atención: este caso ya tenía ` +
              `${yaHabia.length === 1 ? 'una orden abierta' : `${yaHabia.length} órdenes abiertas`}` +
              ` (${yaHabia.map((n) => `#${n}`).join(', ')}).`
            : ''),
        numero
      };
    } catch (e) {
      return fail(e?.status && e.status < 500 ? e.status : 502, { error: mensajeDe(e) });
    }
  }
};
