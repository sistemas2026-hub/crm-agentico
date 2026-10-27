import { fail } from '@sveltejs/kit';
import { reparteTickets } from '$lib/v2/roles.js';
import { listTickets, tomarTicket, OPEN_STATUSES, FILTER_FIELDS } from '$lib/server/v2/tickets.js';
import { readFilters, buildFilterQuery } from '$lib/server/v2/filter-params.js';
import { getOrgPeopleAndTeams, resolveMe } from '$lib/server/v2/org-people.js';
import { getTags } from '$lib/server/v2/tags.js';
import { leerAreas } from '$lib/server/v2/areas.js';
import { areaDelCaso, resumenPorArea, responsablesSinArea, responsablesDeArea, SIN_AREA,
         TODAS_LAS_AREAS }
  from '$lib/v2/tickets-resumen.js';
import { calcularPaginacion, numerosDePagina, enlaceAPagina }
  from '$lib/v2/paginacion.js';

/**
 * Only filters the API actually applies are forwarded. A parameter that
 * changes the URL and nothing else teaches people the filter bar is decorative.
 *
 * The queue defaults to open tickets. `status` is repeatable and the API
 * switches to `status__in` when more than one arrives, so "open" is three
 * values rather than a fourth definition of the word.
 *
 * The pickers are fetched here rather than inside `listTickets` because
 * `getSettingsHub` calls read functions for their totals alone, and a picker
 * fetch folded into one costs a redundant request on every hub load.
 *
 * @type {import('./$types').PageServerLoad}
 */
export async function load({ cookies, url, locals, fetch }) {
  const params = buildFilterQuery(FILTER_FIELDS, readFilters(url, 'tickets'));

  const search = url.searchParams.get('search');
  if (search) params.set('search', search);
  //  PAGINACION  --  07/10/2026
  //
  //  Hasta hoy la cola traia 25 filas y no habia forma de ver el resto: el pie
  //  decia "Mostrando 25 de 47" y ahi terminaba. Con 47 abiertos en Cartera,
  //  22 tickets eran invisibles para quien tiene que trabajarlos, y el numero
  //  solo crece.
  //
  //  Se hace con enlaces y 'offset' en la URL, sin estado en el navegador: una
  //  pagina concreta se puede compartir, recargar y volver atras, y funciona
  //  igual si el JS no cargo.
  const TAMANO = 25;
  const limit = url.searchParams.get('limit');
  const porPagina = Math.min(Math.max(Number(limit) || TAMANO, 1), 200);
  params.set('limit', String(porPagina));
  //  Un 'offset' negativo o no numerico se trata como 0 en vez de rechazarse:
  //  un enlace viejo o manoseado lleva al principio de la cola, no a un error.
  const desde = Math.max(Number(url.searchParams.get('offset')) || 0, 0);
  if (desde) params.set('offset', String(desde));

  const status = url.searchParams.get('status') ?? '';
  const showAll = url.searchParams.get('all') === '1';
  if (status) {
    params.set('status', status);
  } else if (!showAll) {
    for (const open of OPEN_STATUSES) params.append('status', open);
  }

  //  LAS AREAS Y LA GENTE SE RESUELVEN ANTES QUE LOS TICKETS  --  07/10/2026
  //
  //  Antes esto pedia la pagina de tickets aca, en paralelo, y recien despues
  //  miraba las areas. El filtro de area terminaba aplicandose en el navegador
  //  sobre las 25 filas que ya habian llegado, y si ninguna era del area
  //  elegida la tabla salia VACIA con la cabecera diciendo 91. Medido en
  //  produccion ese dia: 138 abiertos, las 25 mas recientes TODAS de cartera,
  //  asi que Soporte Tecnico mostraba cero teniendo 91.
  //
  //  Cuesta una ronda mas (areas -> tickets en vez de todo junto) y a cambio
  //  la pagina que llega ya es la del area. Subir el limite no servia: con
  //  mil tickets el problema vuelve, solo mas tarde.
  const [{ areas, areaPorPersona }, orgPeople, tagList] = await Promise.all([
    // Las areas del equipo y el mapa persona -> area del asistente. Desde el
    // 16/10/2026 el area de un caso es la ESCRITA en el caso ('Case.area');
    // el mapa decide solo para los casos que todavia no la tienen, y dice de
    // que area es quien mira (ver areaDelCaso). Si el asistente no responde,
    // 'areas' y el mapa quedan vacios: las tarjetas salen igual, con el
    // nombre interno de cada area escrita en los casos, y los casos sin area
    // escrita caen a "Sin área asignada". Ver los tickets no puede depender
    // de que el motor este arriba. Ver leerAreas().
    leerAreas(locals, fetch),
    getOrgPeopleAndTeams(cookies),
    // getTags has no fallback of its own: on /settings/tags a failed fetch is
    // meant to surface as an error. Here the tag list is just one picker in
    // the filter bar, so the degradation belongs to this caller, not to the
    // shared function. Losing the picker should cost the Tag dropdown, not
    // the whole queue.
    getTags({ cookies }).catch(() => ({ tags: [] }))
  ]);

  // ---- AREAS -------------------------------------------------------------
  // Un caso sin area escrita y sin asignar aparece como "Sin área asignada"
  // -- que es exactamente lo que hay que ver, porque un caso sin dueño y sin
  // area es un caso que nadie esta mirando. Uno sin asignar pero CON area
  // escrita cuenta en su area, como "sin asignar" de esa cola.

  // Se resuelve UNA vez y se reusa: 'Mis asignados' y el 'meId' que baja a la
  // barra de filtros tienen que ser la misma persona, o el corte y el filtro
  // dirian cosas distintas de la misma pantalla.
  const meId = resolveMe(orgPeople.people, /** @type {any} */ (locals).user?.email);

  // ---- QUE AREAS PUEDE VER QUIEN MIRA -------------------------------------
  // Un colaborador ve SU area y nada mas; quien administra ve todas, porque
  // es quien tiene que saber donde esta la carga y que area esta trancada.
  //
  // Fail-closed a proposito: si no se sabe el area de la persona -- todavia no
  // se la asignaron, o el asistente no respondio y no hay con que resolverla
  // -- no ve NINGUNA cola. Al reves (mostrar todo mientras no se sepa) el
  // hueco se abre justo en el caso que esto existe para cerrar.
  //  "Quien reparte" y no solo ADMIN desde el 23/10/2026: SUPERVISOR y
  //  OPERACIONES ven la cola entera y asignan, como en campo (lib/v2/roles.js,
  //  espejo de cases/access.py::reparte_tickets).
  const reparte = reparteTickets(/** @type {any} */ (locals).profile?.role);
  const miArea = meId ? areaPorPersona[meId] : '';
  const soloMiArea = !reparte;
  const sinAreaPropia = soloMiArea && !miArea;

  let areaElegida = url.searchParams.get('area') ?? '';
  if (soloMiArea) {
    // No alcanza con no dibujar la tarjeta: sin esto, escribir
    // '?area=cartera' en la barra de direcciones abria esa cola igual. Se
    // corrige el parametro en vez de rechazarlo -- un enlace viejo o
    // compartido lleva a la propia cola, no a una pantalla de error.
    //
    // Un area vacia se DEJA vacia: la pantalla arranca igual que para
    // cualquiera, mostrando la tarjeta del area propia. Forzarla aca saltaba
    // directo a la cola, que es una pantalla distinta de la que ve el resto
    // del equipo y hace que "¿cuantos tickets tiene mi area?" deje de tener
    // una respuesta de un vistazo.
    if (sinAreaPropia) areaElegida = '';
    else if (areaElegida && areaElegida !== miArea) areaElegida = miArea;
  }

  //  LA PANTALLA ABRE EN LA COLA, NO EN LAS TARJETAS  --  23/10/2026
  //
  //  Hasta hoy, sin area en la URL se mostraban tarjetas por area y hacia
  //  falta un clic mas para ver un solo ticket. Desde el rediseño de Tickets
  //  abre directo en la cola: quien administra, en "Todas las áreas"; un
  //  colaborador, en la suya. El "¿cuántos tiene cada area?" no se pierde:
  //  viaja como el numero de cada opcion del selector de area (`areasSelector`
  //  abajo). Quien no tiene area propia sigue sin cola -- fail-closed, igual
  //  que antes --.
  if (!areaElegida && !sinAreaPropia) areaElegida = soloMiArea ? miArea : TODAS_LAS_AREAS;

  //  LA VISTA Y EL ORDEN SE LOS PIDE AL SERVIDOR  --  23/10/2026
  //
  //  "Mis asignados" y "Sin asignar" se filtraban aca, sobre las 25 filas que
  //  ya habian llegado: la pestaña decia un numero y la tabla mostraba otro, y
  //  la paginacion contaba la cola entera. Ahora viajan como `vista` y el API
  //  toma a la persona de la SESION (nunca de un parametro).
  //  El orden por defecto es "vence primero": los que todavia no tienen
  //  primera respuesta, el que vence antes arriba. Con 735 abiertos y el orden
  //  por fecha, los vencidos quedaban repartidos en 24 paginas.
  const vista = url.searchParams.get('vista') ?? 'todos';
  if (vista === 'mios' || vista === 'sin_asignar') params.set('vista', vista);
  const orden = url.searchParams.get('orden') === 'recientes' ? 'recientes' : 'vence';
  params.set('ordering', orden === 'vence' ? 'vence' : '-created_at');

  //  EL FILTRO DE AREA VIAJA AL SERVIDOR  --  07/10/2026, reescrito el 16/10/2026
  //
  //  Sin esto la tabla mostraba las 25 filas mas recientes de TODA la cola y
  //  despues descartaba en el navegador las que no eran del area: con 138
  //  abiertos y las 25 primeras todas de cartera, Soporte Tecnico salia vacio
  //  con la cabecera diciendo 91.
  //
  //  Hasta el 16/10 "filtrar por area" era mandar 'assigned_to' con la gente
  //  del area, porque el area se deducia de la persona. Eso escondia en "Sin
  //  área asignada" un ticket de soporte asignado a alguien sin area, y
  //  mostraba como Soporte Tecnico un ticket de ventas asignado a un tecnico.
  //  Hoy el caso trae su area escrita y el API filtra por ella ('area'); la
  //  gente del area viaja aparte ('area_responsables') SOLO para los casos
  //  que todavia no la tienen escrita -- la mitad vieja, ver areaDelCaso().
  //
  //  Ya no hay que cuidar el filtro de responsable de la barra: 'area' y
  //  'assigned_to' son parametros distintos y el API los cruza, asi que
  //  elegir una persona dentro de un area muestra sus tickets DE ESA AREA,
  //  que es lo que el filtro visible dice.
  //
  //  "Sin área asignada" no se puede pedir al servidor: esa cola se sigue
  //  recortando aca abajo, sobre la pagina que llego. Limite conocido.
  const areaEfectiva = soloMiArea ? miArea : areaElegida;
  //  "Todas las áreas" no le pide area al servidor: es la cola sin ese filtro.
  //  Un colaborador no llega aca con ella -- el bloque de arriba ya la cambio
  //  por la suya.
  if (areaEfectiva && areaEfectiva !== SIN_AREA && areaEfectiva !== TODAS_LAS_AREAS) {
    params.set('area', areaEfectiva);
    for (const persona of responsablesDeArea(areaEfectiva, areaPorPersona)) {
      params.append('area_responsables', persona);
    }
    //  LO QUE TENGO ASIGNADO LO VEO SIEMPRE  --  20/10/2026, decidido por el
    //  usuario. Con el area escrita en cada caso, un ticket de otra area
    //  asignado a esta persona salia de su lista. El API toma a la persona de
    //  la sesion; aca solo se pide.
    if (soloMiArea) params.set('incluir_mios', '1');
  }

  //  EL SELECTOR DE AREA LLEVA EL NUMERO DE CADA UNA  --  23/10/2026
  //
  //  Reemplaza a las tarjetas del inicio. Esos numeros salen de la cola SIN
  //  filtro de area; dentro de un area concreta la respuesta principal ya
  //  viene recortada (las demas darian cero), asi que quien administra pide
  //  aparte el desglose de toda la cola: `limit=1`, solo los conteos. Va
  //  PRIMERO a proposito, en paralelo: la llamada principal sigue siendo la
  //  ultima. Un colaborador no lo necesita -- ve una sola area --.
  const dentroDeUnArea = Boolean(areaEfectiva) && areaEfectiva !== TODAS_LAS_AREAS
    && areaEfectiva !== SIN_AREA;
  const paramsGlobal = new URLSearchParams(params);
  for (const clave of ['area', 'area_responsables', 'incluir_mios', 'vista', 'offset']) {
    paramsGlobal.delete(clave);
  }
  paramsGlobal.set('limit', '1');
  const [global, { results, totals, openByAssignee }] = await Promise.all([
    !soloMiArea && dentroDeUnArea
      ? listTickets({ cookies }, paramsGlobal).catch(() => null)
      : Promise.resolve(null),
    listTickets({ cookies }, params)
  ]);

  /**
   * El area de un caso: la escrita en el caso, y si no la tiene, la de su
   * responsable (areaDelCaso, la misma regla que usan las tarjetas y el
   * detalle).
   *
   * Se lee 'assignee_id', NO 'assigned_to': las filas que llegan hasta aca ya
   * pasaron por el modelador de tickets.js, que colapsa la lista de asignados
   * en 'assignee' / 'assignee_id' / 'assignee_count' y NO deja pasar el campo
   * crudo. Leer 'assigned_to' aca daba undefined en todas las filas, o sea
   * TODOS los tickets en "Sin área asignada" -- un tablero que se ve plausible
   * y esta enteramente mal.
   */
  const areaDe = (/** @type {any} */ t) => areaDelCaso(t.area, t.assignee_id, areaPorPersona);

  const conArea = results.map((/** @type {any} */ t) => ({ ...t, area: areaDe(t) }));

  //  EL RESUMEN SALE DEL BACKEND, NO DE LAS FILAS VISIBLES  --  06/10/2026
  //
  //  'openByAssignee' lo calcula la API sobre TODOS los abiertos, en una
  //  consulta agregada. Antes esto se contaba sobre las filas de la pagina y
  //  la cabecera decia 47 mientras las areas sumaban 25.
  //
  //  OJO: cuando hay un area elegida, esta consulta YA viene filtrada por esa
  //  area (y por sus responsables, para los casos sin area escrita), asi que
  //  'openByAssignee' trae solo esa area y las demas dan
  //  cero. No es un problema donde se usa: la pantalla de TARJETAS (las que
  //  comparan areas entre si) es la que NO tiene area elegida, y ahi no hay
  //  filtro. Dentro de un area solo se lee su propio total, que si es el
  //  completo. Si algun dia hiciera falta comparar areas desde adentro, el
  //  desglose tendria que pedirse aparte, sin el filtro.
  const resumen = resumenPorArea(openByAssignee, areas, areaPorPersona);
  //  Responsables sin area configurada con tickets abiertos SIN area escrita:
  //  esos tickets caen en "Sin área asignada" y conviene decirlo, en vez de
  //  que la cola del equipo parezca mas corta de lo que es. Los que ya traen
  //  area escrita cuentan en su tarjeta y no se avisan.
  const sinAreaConfigurada = responsablesSinArea(openByAssignee, areaPorPersona);

  // El universo de tickets se recorta ANTES de armar la respuesta, no solo al
  // dibujar: 'data' viaja serializado dentro del HTML, asi que un ticket de
  // otra area que no se renderiza igual habria viajado hasta el navegador.
  //  Cualquiera de sus asignaciones, no solo la primera: 'assignee_id' es el
  //  primer responsable, y un caso con dos se perdia si la persona era el
  //  segundo (20/10/2026). Sin la lista --una fila vieja-- vale el primero.
  const mios = (/** @type {any} */ t) =>
    Boolean(meId) && (t.assignee_ids ?? (t.assignee_id ? [t.assignee_id] : [])).includes(meId);
  const universo = sinAreaPropia
    ? []
    : soloMiArea
      ? conArea.filter((/** @type {any} */ t) => t.area === miArea || mios(t))
      : conArea;

  const deLaArea = areaElegida && areaElegida !== TODAS_LAS_AREAS
    ? universo.filter((/** @type {any} */ t) => t.area === areaElegida || (soloMiArea && mios(t)))
    : universo;
  //  Cuantos de la lista son de otra area y estan porque son suyos: la
  //  pantalla lo dice, para que la lista no parezca contradecir a la tarjeta.
  const deOtrasAreas = soloMiArea
    ? deLaArea.filter((/** @type {any} */ t) => t.area !== miArea).length
    : 0;

  // Los dos cortes de la sub-navegacion. Los cuenta el API sobre la cola del
  // area ya elegida y ANTES de la vista, asi cada pestaña dice cuantos va a
  // mostrar al pulsarla (`totals.mine` / `totals.unassigned`). Si el API no
  // los manda --una version vieja-- se vuelve a la cuenta sobre la pagina, que
  // es lo que habia, en vez de mostrar un cero inventado.
  const sinAsignar = (/** @type {any} */ t) => !t.assignee_count;
  const delServidor = totals.mine !== null && totals.unassigned !== null;
  const conteosVista = delServidor
    ? { mios: totals.mine, sin_asignar: totals.unassigned }
    : { mios: deLaArea.filter(mios).length, sin_asignar: deLaArea.filter(sinAsignar).length };

  const visibles = delServidor
    ? deLaArea
    : vista === 'mios' ? deLaArea.filter(mios)
    : vista === 'sin_asignar' ? deLaArea.filter(sinAsignar)
    : deLaArea;

  //  'resumen' es null cuando el backend no mando el desglose -- una version
  //  vieja, o una respuesta que fallo. Se propaga como null hasta el return y
  //  NO se colapsa en []: una lista vacia diria "ninguna area tiene tickets",
  //  que es justo la afirmacion que no se puede hacer. La pantalla decide si
  //  muestra ceros o un aviso, con 'resumenDisponible'.
  const areasVisibles = sinAreaPropia || resumen === null
    ? []
    : soloMiArea
      ? resumen.filter((/** @type {any} */ a) => a.nombre === miArea)
      : resumen;

  //  LA TARJETA "TODAS LAS ÁREAS"  --  19/10/2026. Solo para quien administra,
  //  y con los totales del SERVIDOR sobre la cola sin filtro de area. No se
  //  suman las tarjetas: un ticket con dos responsables aparece en las dos, y
  //  la suma diria mas tickets de los que hay. 'sin_asignar' si se suma: un
  //  ticket sin responsable cae en una sola fila del desglose.
  //  Dentro de un area concreta 'totals' ya viene filtrado por ella: esos
  //  numeros no son los de todas, y no se mandan.
  const todasLasAreas = soloMiArea || (areaElegida && areaElegida !== TODAS_LAS_AREAS)
    ? null
    : {
        nombre: TODAS_LAS_AREAS,
        etiqueta: 'Todas las áreas',
        total: totals.open,
        urgentes: totals.urgent,
        sin_respuesta: totals.awaiting_reply,
        sin_asignar: (resumen ?? []).reduce(
          (n, /** @type {any} */ a) => n + (a.sin_asignar ?? 0), 0)
      };

  //  Los enlaces se arman contra el total que da el SERVIDOR, no contra
  //  cuantas filas quedaron visibles: una pagina recortada no significa que
  //  sea la ultima.
  const base = calcularPaginacion(url, totals.count, desde, porPagina);
  //  Los numeros se arman aca y viajan listos: la pantalla solo los dibuja.
  //  Sin la barra numerada, llegar al final de una cola de 24 paginas son 23
  //  clics en "Siguiente".
  const paginacion = {
    ...base,
    numeros: numerosDePagina(base.pagina, base.paginas).map((n) =>
      n === null ? null : { n, url: enlaceAPagina(url, n, porPagina), actual: n === base.pagina })
  };

  //  Las opciones del selector: "Todas las áreas" (solo quien administra) y
  //  cada area con su numero de abiertos, sobre la cola entera. Un colaborador
  //  ve solo la suya, sin selector. `total` null = no se pudo contar.
  const desgloseGlobal = global ? global.openByAssignee : openByAssignee;
  const totalGlobal = global ? global.totals.open : totals.open;
  const resumenGlobal = global ? resumenPorArea(desgloseGlobal, areas, areaPorPersona) : resumen;
  const selectorAreas = soloMiArea
    ? []
    : [
        { nombre: TODAS_LAS_AREAS, etiqueta: 'Todas las áreas', total: totalGlobal },
        ...(resumenGlobal ?? []).map((/** @type {any} */ a) => ({
          nombre: a.nombre, etiqueta: a.etiqueta, total: a.total
        }))
      ];

  //  LAS TARJETAS VUELVEN  --  27/10/2026, pedido del usuario: «no están
  //  saliendo las tarjetas como antes: administración, soporte, operativo,
  //  cartera, ventas». Las del 19/10 (total, urgentes, sin respuesta, sin
  //  asignar), ahora ARRIBA de la cola en vez de en una pantalla aparte: un
  //  clic abre esa área, y la elegida queda marcada.
  //  Los numeros son de la cola ENTERA (`global` cuando hay un area elegida,
  //  igual que el selector): dentro de un area, la consulta principal ya
  //  viene recortada y las demas tarjetas darian cero. Un colaborador ve la
  //  de su area y nada mas, como antes.
  const totalesGlobales = global ? global.totals : totals;
  const tarjetas = soloMiArea
    ? areasVisibles
    : [
        {
          nombre: TODAS_LAS_AREAS,
          etiqueta: 'Todas las áreas',
          todas: true,
          total: totalesGlobales.open,
          urgentes: totalesGlobales.urgent,
          sin_respuesta: totalesGlobales.awaiting_reply,
          sin_asignar: (resumenGlobal ?? []).reduce(
            (n, /** @type {any} */ a) => n + (a.sin_asignar ?? 0), 0)
        },
        ...(resumenGlobal ?? [])
      ];

  return {
    areas: areasVisibles,
    selectorAreas,
    tarjetas,
    orden,
    reparte,
    paginacion,
    //  false = el desglose no llego, asi que 'areas' esta vacio porque no se
    //  pudo contar, no porque no haya tickets. Son dos pantallas distintas.
    resumenDisponible: resumen !== null,
    //  Responsables con tickets abiertos y sin area configurada: sus tickets
    //  no aparecen en ninguna columna del equipo.
    sinAreaConfigurada,
    areaElegida,
    // Distingue "esta persona no tiene area" de "no se pudieron leer las
    // areas". Las dos dejan 'areas' vacio y piden pantallas opuestas: la
    // primera NO debe caer a la cola sin agrupar (seria mostrarle todo justo
    // a quien no puede ver nada), la segunda si.
    sinAreaPropia,
    soloMiArea,
    sinArea: SIN_AREA,
    todas: TODAS_LAS_AREAS,
    todasLasAreas,
    conteosVista,
    deOtrasAreas,
    vista,
    tickets: visibles,
    totals,
    showAll,
    status,
    search: params.get('search') ?? '',
    priority: params.get('priority') ?? '',
    people: orgPeople.people,
    tags: tagList.tags ?? [],
    meId
  };
}

/** @type {import('./$types').Actions} */
export const actions = {
  //  "ASIGNARME" DESDE LA COLA  --  23/10/2026
  //
  //  Solo para quien reparte (ADMIN, SUPERVISOR, OPERACIONES): el backend no
  //  le deja a un colaborador comun ver ni escribir un caso que no es suyo
  //  (cases/access.py), asi que el boton solo aparece para esos roles. Aca se vuelve a mirar el rol -- la pantalla no es
  //  la que decide --, y la persona sale de la SESION, nunca del formulario.
  //  TOMAR, NO EDITAR (24/10/2026). Asignarme llama a '/tomar/', que decide
  //  el backend: quien reparte toma cualquier ticket sin responsable, un
  //  colaborador solo los de su area. Ya no se mira el rol aca -- la regla es
  //  una sola y vive en cases/access.py::puede_tomar -- y ya no es un PATCH:
  //  aquel reemplazaba el conjunto de responsables, y dos que apretaban a la
  //  vez quedaban con el ultimo. '/tomar/' bloquea la fila y al segundo le
  //  contesta 409.
  asignarme: async ({ request, cookies }) => {
    const id = String((await request.formData()).get('id') ?? '');
    if (!id) return fail(400, { error: 'Falta el ticket.' });
    try {
      await tomarTicket({ cookies }, id);
    } catch (e) {
      const estado = /** @type {any} */ (e)?.status;
      if (estado === 409) {
        return fail(409, { error: 'Otra persona tomó este ticket primero.' });
      }
      if (estado === 403) {
        return fail(403, { error: 'Este ticket no es de tu área.' });
      }
      return fail(400, { error: 'No se pudo asignar el ticket.' });
    }
    return { asignado: id };
  }
};
