import { listTickets, OPEN_STATUSES, FILTER_FIELDS } from '$lib/server/v2/tickets.js';
import { readFilters, buildFilterQuery } from '$lib/server/v2/filter-params.js';
import { getOrgPeopleAndTeams, resolveMe } from '$lib/server/v2/org-people.js';
import { getTags } from '$lib/server/v2/tags.js';
import { leerAreas } from '$lib/server/v2/areas.js';
import { resumenPorArea, responsablesSinArea, SIN_AREA }
  from '$lib/v2/tickets-resumen.js';

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
  const limit = url.searchParams.get('limit');
  if (limit) params.set('limit', limit);

  const status = url.searchParams.get('status') ?? '';
  const showAll = url.searchParams.get('all') === '1';
  if (status) {
    params.set('status', status);
  } else if (!showAll) {
    for (const open of OPEN_STATUSES) params.append('status', open);
  }

  const [{ results, totals, openByAssignee }, orgPeople, tagList] = await Promise.all([
    listTickets({ cookies }, params),
    getOrgPeopleAndTeams(cookies),
    // getTags has no fallback of its own: on /settings/tags a failed fetch is
    // meant to surface as an error. Here the tag list is just one picker in
    // the filter bar, so the degradation belongs to this caller, not to the
    // shared function. Losing the picker should cost the Tag dropdown, not
    // the whole queue.
    getTags({ cookies }).catch(() => ({ tags: [] }))
  ]);

  // ---- AREAS -------------------------------------------------------------
  // El CRM no tiene campo de area: el area vive en el asistente y es POR
  // PERSONA. Asi que la de un caso se deriva de a quien esta asignado.
  //
  // Consecuencia buscada: un caso sin asignar no tiene area, y aparece como
  // "Sin área asignada" -- que es exactamente lo que hay que ver, porque un
  // caso sin dueño es un caso que nadie esta mirando.
  //
  // Si el asistente no responde, 'areas' queda vacio y la pantalla cae a la
  // lista de siempre: ver los tickets no puede depender de que el motor este
  // arriba. Ver leerAreas().
  const { areas, areaPorPersona } = await leerAreas(locals, fetch);

  /**
   * El area de un caso: la de su responsable.
   *
   * Se lee 'assignee_id', NO 'assigned_to': las filas que llegan hasta aca ya
   * pasaron por el modelador de tickets.js, que colapsa la lista de asignados
   * en 'assignee' / 'assignee_id' / 'assignee_count' y NO deja pasar el campo
   * crudo. Leer 'assigned_to' aca daba undefined en todas las filas, o sea
   * TODOS los tickets en "Sin área asignada" -- un tablero que se ve plausible
   * y esta enteramente mal.
   */
  const areaDe = (/** @type {any} */ t) =>
    (t.assignee_id && areaPorPersona[t.assignee_id]) || SIN_AREA;

  const conArea = results.map((/** @type {any} */ t) => ({ ...t, area: areaDe(t) }));

  //  EL RESUMEN SALE DEL BACKEND, NO DE LAS FILAS VISIBLES  --  06/10/2026
  //
  //  Antes se contaba sobre 'conArea', que son las filas de ESTA pagina (25).
  //  Con 47 abiertos la cabecera decia 47 y las areas sumaban 25, y parecia
  //  que 22 tickets no tenian area: lo que pasaba es que no habian llegado.
  //  'openByAssignee' lo calcula la API sobre TODOS los abiertos, en una
  //  consulta agregada -- la paginacion de 25 no cambia.
  //
  //  'conArea' se conserva porque la TABLA sigue mostrando la pagina y
  //  necesita el area de cada fila; lo que dejo de derivarse de ahi son los
  //  totales.
  const resumen = resumenPorArea(openByAssignee, areas, areaPorPersona);
  //  Responsables con tickets abiertos y sin area configurada: sus tickets
  //  caen en "Sin área asignada" y conviene decirlo, en vez de que la cola
  //  del equipo parezca mas corta de lo que es.
  const sinAreaConfigurada = responsablesSinArea(openByAssignee, areaPorPersona);

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
  const esAdmin = /** @type {any} */ (locals).profile?.role === 'ADMIN';
  const miArea = meId ? areaPorPersona[meId] : '';
  const soloMiArea = !esAdmin;
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

  // El universo de tickets se recorta ANTES de armar la respuesta, no solo al
  // dibujar: 'data' viaja serializado dentro del HTML, asi que un ticket de
  // otra area que no se renderiza igual habria viajado hasta el navegador.
  const mios = (/** @type {any} */ t) => meId && t.assignee_id === meId;
  const universo = sinAreaPropia
    ? []
    : soloMiArea
      ? conArea.filter((/** @type {any} */ t) => t.area === miArea)
      : conArea;

  const deLaArea = areaElegida
    ? universo.filter((/** @type {any} */ t) => t.area === areaElegida)
    : universo;

  // Los dos cortes de la sub-navegacion. Se cuentan sobre la cola del area
  // YA elegida y no sobre todo el CRM: el numero al lado de "Sin asignar"
  // tiene que ser el que se va a ver al pulsarlo.
  const sinAsignar = (/** @type {any} */ t) => !t.assignee_count;
  const conteosVista = {
    mios: deLaArea.filter(mios).length,
    sin_asignar: deLaArea.filter(sinAsignar).length
  };

  const vista = url.searchParams.get('vista') ?? 'todos';
  const visibles =
    vista === 'mios' ? deLaArea.filter(mios)
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

  return {
    areas: areasVisibles,
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
    conteosVista,
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
