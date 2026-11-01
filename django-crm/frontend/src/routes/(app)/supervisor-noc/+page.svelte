<script>
  import { onDestroy } from 'svelte';
  import PestanasNoc from '$lib/supervisor/PestanasNoc.svelte';

  import { resultadoDelCierre } from '$lib/v2/resultado-del-cierre.js';
  //  La burbuja del chat del Supervisor ya no se monta aca: vive en
  //  +layout.svelte (21/10/2026), para que salga en todas las pestañas.
  import { deserialize, enhance } from '$app/forms';
  import { invalidateAll } from '$app/navigation';
  import {
    AUSENTE,
    nombreHumano,
    quePasa,
    prioridadHumana,
    identificacion,
    comparacionFuentes,
    analisisSeparado,
    siAcepto,
    comunDeEvidencia,
    fuentesDeEvidencia,
    baseDePrioridad,
    contrasteDeEstados,
    haceCuanto,
    expiraEn,
    antiguedadDelCaso,
    lecturaExterna,
    CONTEXTO_AUSENTE,
    pasosDelCiclo,
    comparacionAporta,
    filasComparables,
    filasDeAceptar,
    loteDeSeleccion
  } from '$lib/v2/supervisor-noc-detalle.js';
  import {
    kpisDelTablero,
    hallazgosPorTipo,
    estadoDeCasos,
    ordenesDeTrabajo,
    cargaPorTecnico,
    ticketsPorOrigen,
    bandejaDeRevision,
    baseDeLaBandeja,
    conteoPorBandeja,
    rotuloDeHallazgo,
    paginacion,
    ticketsDe,
    origenDe,
    actividadReciente,
    celdaDeSla,
    BLOQUES_SIN_DATO
  } from '$lib/v2/supervisor-noc-tablero.js';
  import {
    agruparPorPlazo,
    cuentaPorPlazo,
    textoDePlazo,
    titularDelTablero
  } from '$lib/v2/supervisor-noc-plazo.js';
  import {
    tarjetasDeSolo,
    resumenAutonomiaGanada,
    nombreDeAccion
  } from '$lib/v2/supervisor-noc-autonomia.js';
  import { efectosDeAceptar, celdaDistinta } from '$lib/v2/supervisor-noc-ficha.js';
  import './supervisor-noc.css';
  //  El diseño del 01/11/2026 vive en su propia hoja y bajo '.snv': esta hoja
  //  de arriba la comparten nueve pantallas, y lo de esta no debe tocarlas.
  import './supervisor-noc-v2.css';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  // ---------------------------------------------------------------------
  //  ESTADO LOCAL
  //  Nada de esto decide permisos ni protege nada: el backend es la
  //  autoridad y vuelve a comprobarlo en cada llamada. Aca solo vive lo que
  //  la pantalla necesita para no parpadear.
  // ---------------------------------------------------------------------
  //  ===================================================================
  //   EL ALCANCE DEL SUPERVISOR  --  nivel e interruptor, desde la pantalla
  //  ===================================================================
  //  Hasta el 08/10/2026 esto solo se podia tocar desde una consola del
  //  servidor. Era deliberado y tenia sentido mientras el Supervisor solo
  //  observaba; dejo de tenerlo el dia que pudo cerrar casos solo. Un freno que
  //  nadie puede tocar desde la pantalla no es un freno, y el momento en que
  //  hace falta es justo cuando nadie quiere estar buscando como abrir una
  //  terminal.
  let modalAlcance = $state(false);
  let alcance = $state(/** @type {any} */ (null));
  let alcanceCargando = $state(false);
  let alcanceError = $state('');
  let alcanceGuardando = $state(false);
  let nivelElegido = $state(/** @type {number | null} */ (null));
  let motivoAlcance = $state('');
  let criteriosAlcance = $state('');
  let motivoFreno = $state('');

  /**
   * Lee el alcance. La usa el modal al abrirse y, desde el 01/11/2026, la
   * pantalla al cargar: «Qué hace el Supervisor solo» muestra las tareas
   * delegadas sin tener que abrir nada. Una sola lectura para los dos.
   */
  async function leerAlcance() {
    alcanceError = '';
    try {
      const r = await fetch('/api/supervisor-noc/autonomia');
      const d = await r.json();
      if (!r.ok) {
        alcanceError = d?.error ?? 'No se pudo leer el alcance.';
      } else {
        alcance = d;
        nivelElegido = d.configurado;
      }
    } catch (/** @type {any} */ e) {
      alcanceError = `No se pudo leer el alcance: ${e?.message ?? e}`;
    }
  }

  async function abrirAlcance() {
    modalAlcance = true;
    alcanceCargando = true;
    try {
      await leerAlcance();
    } finally {
      alcanceCargando = false;
    }
  }

  //  Se vuelve a leer cada vez que corre la carga del servidor --al decidir,
  //  al correr un ciclo--: lo delegado puede haber cambiado desde Ajustes o
  //  desde el chat.
  $effect(() => {
    if (data.puedeVer) leerAlcance();
  });

  const tarjetas = $derived(tarjetasDeSolo(alcance));

  async function guardarNivel() {
    alcanceGuardando = true;
    alcanceError = '';
    try {
      const r = await fetch('/api/supervisor-noc/autonomia', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          nivel: nivelElegido,
          motivo: motivoAlcance,
          criterios: criteriosAlcance
        })
      });
      const d = await r.json();
      if (!r.ok) {
        //  El mensaje del backend se muestra TAL CUAL: ya dice cual de los
        //  tres requisitos falta. Reescribirlo aca serian dos textos que se
        //  separan el dia que uno cambie.
        alcanceError = d?.error ?? 'No se pudo cambiar el nivel.';
      } else {
        alcance = { ...alcance, ...d };
        motivoAlcance = '';
        criteriosAlcance = '';
        await invalidateAll();
      }
    } catch (/** @type {any} */ e) {
      alcanceError = `No se pudo cambiar el nivel: ${e?.message ?? e}`;
    } finally {
      alcanceGuardando = false;
    }
  }

  /** @param {boolean} detener */
  async function moverFreno(detener) {
    alcanceGuardando = true;
    alcanceError = '';
    try {
      const r = await fetch('/api/supervisor-noc/autonomia', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ detener, motivo: motivoFreno })
      });
      const d = await r.json();
      if (!r.ok) {
        alcanceError = d?.error ?? 'No se pudo mover el interruptor.';
      } else {
        alcance = { ...alcance, ...d };
        motivoFreno = '';
        await invalidateAll();
      }
    } catch (/** @type {any} */ e) {
      alcanceError = `No se pudo mover el interruptor: ${e?.message ?? e}`;
    } finally {
      alcanceGuardando = false;
    }
  }

  let modalCiclo = $state(false);
  let corriendo = $state(false);
  let asistenteCorriendo = $state(/** @type {string | null} */ (null));
  let filtro = $state(/** @type {string | null} */ (null));

  // Los filtros de la bandeja. Se aplican en el navegador: el GET ya trajo el
  // conjunto entero (el backend corta en 200 y hoy hay 93), asi que una
  // vuelta al servidor por pastilla seria reordenar datos que ya estan en
  // pantalla.
  //
  // Abre en 'pendientes' y no en 'todas' a proposito: la bandeja se llama
  // asi porque lo que muestra es lo que espera una decision. Lo ya decidido
  // esta a una pastilla de distancia, no escondido.
  let filtroEstado = $state('pendientes');
  let filtroNivel = $state(/** @type {string | null} */ (null));
  let filtroPropuesta = $state('');

  // El buscador. Mira cliente, caso/OT, asunto y tecnico -- lo que la tabla
  // muestra. Buscar tambien en la evidencia haria aparecer filas por un texto
  // que no esta a la vista, y quien busca no entenderia por que salieron.
  let busqueda = $state('');

  // La pagina pedida. `paginacion` la recorta a lo que existe: al filtrar, la
  // 7 puede dejar de haber, y quedarse ahi mostraria una tabla vacia sin
  // decir por que.
  let nPagina = $state(1);

  /** Cuantas filas por pagina. */
  const POR_PAGINA = 10;

  //  EL ORDEN DE LA BANDEJA  --  01/11/2026. Por plazo (agrupada) es lo que
  //  abre; por prioridad es el orden de siempre, sin grupos.
  let ordenar = $state(/** @type {'plazo' | 'prioridad'} */ ('plazo'));
  //  Lo que la persona plegó o desplegó a mano. Lo que no tocó sigue la regla
  //  de 'estaPlegado'.
  let plegadoManual = $state(/** @type {Record<string, boolean>} */ ({}));

  const NIVELES_VISIBLES = ['Alta', 'Media', 'Baja'];

  /**
   * El KPI de pendientes lleva a la bandeja Y la deja filtrada en pendientes.
   * Sin lo segundo, el numero del KPI y el de la tabla se contradicen cuando
   * alguien habia dejado el filtro en 'todas'.
   */
  function irAPendientes() {
    filtroEstado = 'pendientes';
    filtroNivel = null;
    filtroPropuesta = '';
    verDesincronizados = 'ocultar';
    filtro = null;
    busqueda = '';
  }

  /** Si hay algo que limpiar. El estado abre en 'pendientes', que es el
      valor por defecto y no cuenta como filtro puesto. */
  const hayFiltros = $derived(
    Boolean(filtro || filtroNivel || filtroPropuesta || busqueda.trim()) ||
      filtroEstado !== 'pendientes'
  );

  function limpiarFiltros() {
    filtro = null;
    filtroNivel = null;
    filtroPropuesta = '';
    filtroEstado = 'pendientes';
    busqueda = '';
  }

  let revisando = $state(/** @type {string | null} */ (null));
  let comentario = $state('');

  // El panel lateral. `detalle` se pide por id y trae su propio cargando:
  // antes esto recargaba la pagina entera -- las 92 propuestas, los
  // indicadores y el estado del motor -- para mostrar una ficha.
  let abierta = $state(/** @type {string | null} */ (null));
  let detalle = $state(/** @type {any} */ (null));
  let cargandoDetalle = $state(false);
  let errorDetalle = $state(/** @type {string | null} */ (null));

  /** @type {Record<number, string>} */
  const NIVELES = {
    0: 'Observar',
    1: 'Recomendar',
    2: 'Coordinar',
    3: 'Ejecutar acciones reversibles autorizadas',
    4: 'Acción crítica con autorización humana'
  };

  /** Los estados del modelo. No hay ninguno mas, y 'ejecutada' no existe. */
  const ESTADOS = {
    propuesta: { texto: 'Propuesta', clase: 'snoc-insignia' },
    aceptada: { texto: 'Aceptada', clase: 'snoc-insignia-secundaria-suave' },
    modificada: { texto: 'Modificada', clase: 'snoc-insignia-secundaria-suave' },
    rechazada: { texto: 'Rechazada', clase: 'snoc-insignia-error' },
    cancelada: { texto: 'Cancelada', clase: 'snoc-insignia-variante' },
    expirada: { texto: 'Expirada', clase: 'snoc-insignia-variante' }
  };
  const estadoDe = (/** @type {string} */ e) =>
    ESTADOS[/** @type {keyof typeof ESTADOS} */ (e)] ?? { texto: e, clase: 'snoc-insignia' };

  const PRIORIDAD = { alta: 'snoc-insignia-error-solida', media: 'snoc-insignia-secundaria' };
  const tonoPrioridad = (/** @type {any} */ p) =>
    PRIORIDAD[/** @type {keyof typeof PRIORIDAD} */ (String(p).toLowerCase())] ?? 'snoc-insignia';

  const propuestas = $derived(data.hallazgos?.resultados ?? []);

  // ---------------------------------------------------------------------
  //  EL TABLERO
  //  Las derivaciones viven en $lib/v2/supervisor-noc-tablero.js, probadas
  //  aparte: la regla que mas facil se rompe aqui -- un `?? 0` de mas y un
  //  indicador caido se muestra como "todo en orden" -- no se puede ejercitar
  //  sin montar el componente.
  // ---------------------------------------------------------------------
  const leidas = $derived(data.hallazgos?.error ? null : (data.hallazgos?.resultados ?? null));
  /**
   * LO QUE TODAVIA NO LLEGO  --  09/10/2026
   *
   * Tres de las cinco consultas de la carga viajan como PROMESA: los
   * indicadores, la autonomia y la capacidad. La pantalla se pinta con la
   * bandeja --que es a lo que la persona viene-- y estas entran despues.
   *
   * MEDIDO: '/supervisor-noc/__data.json' tardaba 22 segundos en dos
   * grabaciones distintas, mientras TODAS las demas peticiones de la misma
   * sesion estaban por debajo de 600 ms. Las cuatro consultas rapidas
   * esperaban a la lenta.
   *
   * Arrancan en 'null', que es lo que las funciones de abajo ya trataban como
   * "sin dato" -- por eso el cambio no toca ningun bloque de la pantalla.
   */
  let indicadoresVivos = $state(/** @type {any} */ (null));
  let autonomiaViva = $state(/** @type {any} */ (null));
  let capacidadViva = $state(/** @type {any} */ (null));
  //  01/11/2026: la tarjeta «Autonomía ganada». Viaja como promesa, igual que
  //  las otras tres lentas, y 'null' es "todavía no llegó".
  let ganadaViva = $state(/** @type {any} */ (null));
  const ganada = $derived(resumenAutonomiaGanada(ganadaViva));

  $effect(() => {
    //  Se vuelven a enganchar cuando la carga del servidor corre de nuevo.
    //  'vigente' evita que una respuesta vieja pise una nueva si la persona
    //  recarga antes de que la anterior termine.
    let vigente = true;
    indicadoresVivos = null;
    autonomiaViva = null;
    capacidadViva = null;
    ganadaViva = null;
    Promise.resolve(data.autonomiaGanada).then((v) => { if (vigente) ganadaViva = v ?? { autonomia: null, error: 'Sin respuesta.' }; });
    Promise.resolve(data.indicadores).then((v) => { if (vigente) indicadoresVivos = v; });
    Promise.resolve(data.autonomia).then((v) => { if (vigente) autonomiaViva = v; });
    Promise.resolve(data.capacidad).then((v) => { if (vigente) capacidadViva = v; });
    return () => { vigente = false; };
  });

  //  'esperando' distingue "todavia no llego" de "llego vacio". Sin eso, los
  //  bloques dirian "Sin dato" durante la espera, que es una afirmacion
  //  distinta y falsa.
  const esperandoIndicadores = $derived(indicadoresVivos === null);

  const kpis = $derived(kpisDelTablero(indicadoresVivos?.datos, leidas));
  const barras = $derived(estadoDeCasos(indicadoresVivos?.datos));
  const ordenes = $derived(ordenesDeTrabajo(indicadoresVivos?.datos));
  const tecnicos = $derived(cargaPorTecnico(capacidadViva?.personas));
  const origen = $derived(ticketsPorOrigen(indicadoresVivos?.datos));
  /**
   * LA ACTIVIDAD, EN VIVO  --  08/10/2026
   *
   * El Supervisor ahora actua solo: cada hora revisa, diagnostica y cierra lo
   * que tenga delegado. Un panel que solo se refresca al recargar la pagina
   * esconde justo eso -- lo que hizo cuando nadie estaba mirando.
   *
   * 'eventosVivos' pisa a lo que trajo el servidor mientras el sondeo este
   * andando. Cuando la carga del servidor vuelve a correr --al aceptar una
   * propuesta, al cambiar un filtro-- se suelta, y manda otra vez el load: dos
   * fuentes para lo mismo necesitan una que gane, y la que gana es la que la
   * persona acaba de provocar.
   */
  let eventosVivos = $state(/** @type {any[] | null} */ (null));
  //  Fuera de '$state' a proposito: es memoria del sondeo, no algo que la
  //  pantalla muestre. Si fuera reactiva, cambiarla provocaria el mismo
  //  re-render que esta variable existe para evitar.
  let huellaVista = '';
  let ultimoSondeo = $state(/** @type {Date | null} */ (null));
  let sondeoVivo = $state(false);

  const actividad = $derived(
    actividadReciente(eventosVivos ?? data.actividad?.eventos));

  //  EL FILTRO Y LA PAGINACION DE LA ACTIVIDAD  --  15/10/2026
  //
  //  POR QUE HACE FALTA: el panel trae los ultimos eventos de CUALQUIER tipo,
  //  y cada vuelta del ciclo genera propuestas nuevas. Medido ese dia: de los
  //  ultimos 20 eventos, 13 eran pases a Despacho y 7 propuestas creadas --
  //  pero a medida que el ciclo sigue, los pases se diluyen hasta desaparecer
  //  del panel aunque sigan guardados enteros en la base. Subir el limite no lo
  //  arregla: lo retrasa.
  //
  //  EL FILTRO LO RESUELVE EL BACKEND, no un 'filter' aqui: filtrando sobre los
  //  doce hechos que llegaron, el numero del boton diria cuantos entraron en
  //  esa tanda y no cuantos hay. "Cierres de caso (28)" tiene que ser 28.
  let grupo = $state('');
  //  Lo que se trajo hacia atras con "Ver mas". Vive aparte de lo que trae el
  //  sondeo, y la razon es concreta: el sondeo REEMPLAZA su lista cada diez
  //  segundos, asi que si las paginas viejas vivieran ahi, cargar tres y
  //  esperar diez segundos las borraria.
  let paginasViejas = $state(/** @type {any[]} */ ([]));
  let siguiente = $state(/** @type {string | null} */ (null));
  let cargandoMas = $state(false);
  let porGrupo = $state(/** @type {Record<string, number>} */ (data.actividad?.porGrupo ?? {}));

  //  Los grupos, con el rotulo que lee una persona. Las claves son las del
  //  backend ('auditoria.GRUPOS') y no se traducen aqui de vuelta: lo que viaja
  //  es la clave cruda, para que una redaccion nueva no rompa el filtro.
  const GRUPOS_VISIBLES = [
    { clave: '', rotulo: 'Todo' },
    { clave: 'pasa_a_despacho', rotulo: 'Pasados a Despacho' },
    //  SEPARADO DE 'pasa_a_despacho' DESDE EL 16/10/2026. Las dos cosas
    //  escriben 'PropuestaSupervisor APPROVED'; lo que las distingue es la
    //  tarea que ahora queda en la auditoria. Las filas anteriores a esa fecha
    //  no la traen y caen aca -- en produccion eran 597, y mostrarlas como
    //  pases a Despacho era contar cierres de caso dos veces.
    { clave: 'acepta', rotulo: 'Propuestas aceptadas' },
    { clave: 'cierra_caso', rotulo: 'Cierres de caso' },
    { clave: 'propone', rotulo: 'Propuestas' },
    { clave: 'otros', rotulo: 'Otros' }
  ];

  const actividadVisible = $derived([...actividad.filas, ...paginasViejas]);

  //  La declara el $effect del sondeo; se nombra aqui para que 'elegirGrupo'
  //  pueda llamarla. Svelte 5 permite esto porque el efecto corre al montar,
  //  antes de que haya ningun click.
  let traerActividad = async () => {};

  /** Cambia de grupo: se vuelve a pedir desde arriba, sin las paginas viejas. */
  async function elegirGrupo(nueva) {
    if (nueva === grupo) return;
    grupo = nueva;
    paginasViejas = [];
    siguiente = null;
    //  Se fuerza una lectura ya, sin esperar los diez segundos del sondeo: un
    //  filtro que tarda en responder se siente roto.
    await traerActividad();
  }

  /** Trae la pagina siguiente y la SUMA abajo, sin tocar lo de arriba. */
  async function verMas() {
    if (!siguiente || cargandoMas) return;
    cargandoMas = true;
    try {
      const q = new URLSearchParams({ antes_de: siguiente, limite: '20' });
      if (grupo) q.set('grupo', grupo);
      const r = await fetch(`/supervisor-noc/actividad?${q}`, {
        headers: { accept: 'application/json' }
      });
      if (!r.ok) return;
      const cuerpo = await r.json();
      if (cuerpo?.error) return;
      const llegados = Array.isArray(cuerpo?.eventos) ? cuerpo.eventos : [];
      //  SE DESCARTA LO QUE YA ESTA. El sondeo y esto piden rangos distintos y
      //  pueden solaparse en el borde; sin esto, un hecho saldria dos veces y
      //  la lista {#each} con clave duplicada rompe el render.
      const vistos = new Set(actividadVisible.map((f) => f.id));
      paginasViejas = [
        ...paginasViejas,
        ...actividadReciente(llegados).filas.filter((f) => !vistos.has(f.id))
      ];
      siguiente = cuerpo?.siguiente ?? null;
    } finally {
      cargandoMas = false;
    }
  }

  /**
   * La bandeja: filtrada, ordenada y numerada. La logica vive en
   * $lib/v2/supervisor-noc-tablero.js y esta probada aparte -- el orden y la
   * numeracion tienen casos borde (prioridad ausente, sin fecha de origen)
   * que dentro del .svelte no se pueden ejercitar sin montarlo.
   */
  /**
   * QUE SE VE EN LA BANDEJA  --  13/10/2026
   *
   * 'ocultar' por defecto: esta bandeja es para lo que necesita criterio
   * humano, y un caso que el Supervisor cierra solo no lo necesita. Lo pidio
   * el cliente asi: "pendientes por revision no se hizo para los
   * desincronizados".
   *
   * No desaparecen: el recuadro de Desincronizaciones los trae con 'solo'.
   */
  let verDesincronizados = $state(/** @type {'ocultar'|'solo'} */ ('ocultar'));

  const bandeja = $derived(
    bandejaDeRevision(propuestas, {
      estado: filtroEstado,
      nivel: filtroNivel,
      tipo: filtro,
      conPropuesta: filtroPropuesta,
      texto: busqueda,
      desincronizados: verDesincronizados
    })
  );

  const pag = $derived(paginacion(bandeja.length, nPagina, POR_PAGINA));

  //  EL DONUT Y EL SELECTOR DE TIPO CUENTAN LO QUE LA TABLA LISTA  --  19/10/2026.
  //  Contaban las 200 que llegan --el tope del backend, con decididas, casos
  //  cerrados y desincronizaciones-- al lado de una tabla de 15.
  const enLaBandeja = $derived(baseDeLaBandeja(propuestas, filtroEstado, verDesincronizados));
  const donut = $derived(hallazgosPorTipo(leidas ? enLaBandeja : null));

  //  CUANTOS TICKETS SON  --  19/10/2026. La bandeja lista PROPUESTAS, y un
  //  ticket puede tener dos (caso antiguo + sin diagnostico). Medido en
  //  produccion: 12 filas, 8 tickets. Sin decirlo, el numero no se puede
  //  comparar con los de Despacho ni con la cola de Tickets.
  const sobreLaBandeja = $derived(ticketsDe(bandeja));

  /**
   * Las filas de esta pagina. El N.º que ya traen es la posicion dentro de
   * TODOS los resultados filtrados, no dentro de la pagina: asi el numero de
   * la fila coincide con el "Mostrando 7 a 12" de abajo en vez de reiniciar
   * en 1 cada vez.
   */
  //  ORDENADA POR PLAZO ANTES DE CORTAR LA PAGINA  --  01/11/2026. Agrupar
  //  solo dentro de la pagina dejaria un vencido en la 2 mientras la 1 muestra
  //  casos en plazo. Dentro de cada grupo se respeta el orden de la bandeja.
  const bandejaOrdenada = $derived(
    ordenar === 'plazo' ? agruparPorPlazo(bandeja).flatMap((g) => g.filas) : bandeja
  );
  const pagina = $derived(bandejaOrdenada.slice(pag.desde - 1, pag.hasta));
  const gruposDeLaPagina = $derived(agruparPorPlazo(pagina));
  //  El numero del grupo es el de TODA la bandeja filtrada, no el de la
  //  pagina: «Plazo vencido 9» con 4 filas a la vista dice que hay mas.
  const cuentaDeLaBandeja = $derived(cuentaPorPlazo(bandeja));

  /**
   * Los grupos tranquilos («En plazo», «Sin plazo») abren plegados SOLO si en
   * la pagina hay algo vencido o por vencer: plegarlos siempre dejaria una
   * bandeja sin urgentes toda cerrada, que se lee como vacia.
   */
  function estaPlegado(/** @type {string} */ clave) {
    if (clave in plegadoManual) return plegadoManual[clave];
    const hayUrgentes = gruposDeLaPagina.some((g) => g.clave === 'vencido' || g.clave === 'pronto');
    return hayUrgentes && (clave === 'plazo' || clave === 'sin');
  }

  //  LO QUE DICE LA FRASE DE ARRIBA. Sobre la bandeja de PENDIENTES, sin
  //  filtros y sin desincronizados: la misma lista que cuenta el KPI de
  //  pendientes desde el 19/10. Con la bandeja caida, todo en null.
  const enPendientes = $derived(
    leidas ? bandejaDeRevision(leidas, { estado: 'pendientes', desincronizados: 'ocultar' }) : null
  );
  const plazoPendientes = $derived(cuentaPorPlazo(enPendientes));
  const titular = $derived(
    titularDelTablero({
      pendientes: enPendientes ? enPendientes.length : null,
      vencido: plazoPendientes?.vencido ?? null,
      pronto: plazoPendientes?.pronto ?? null
    })
  );
  const enRiesgo = $derived({
    total: plazoPendientes ? plazoPendientes.vencido + plazoPendientes.pronto : null,
    vencido: plazoPendientes?.vencido ?? 0,
    pronto: plazoPendientes?.pronto ?? 0
  });
  const sobrePendientes = $derived(enPendientes ? ticketsDe(enPendientes) : null);
  //  «Sin técnico» sobre la misma lista: las pendientes sin técnico actual.
  const sinTecnico = $derived(
    enPendientes ? enPendientes.filter((/** @type {any} */ p) => !p.tecnico).length : null
  );
  //  Los signos que vienen del backend, con el rótulo corto del diseño.
  const signosDelBackend = $derived(
    [
      { clave: 'bloqueados', rotulo: 'Bloqueados' },
      { clave: 'sin_programar', rotulo: 'Sin programar' }
    ].map((s) => ({ ...s, n: kpis.find((k) => k.clave === s.clave)?.n ?? null }))
  );
  const desincronizados = $derived(kpis.find((k) => k.clave === 'desinc')?.n ?? null);

  // Cambiar un filtro o buscar vuelve a la primera pagina. Sin esto, filtrar
  // de 121 a 4 resultados estando en la pagina 7 deja la tabla vacia.
  $effect(() => {
    void [filtroEstado, filtroNivel, filtro, filtroPropuesta, busqueda];
    nPagina = 1;
  });

  /**
   * EL SONDEO DEL PANEL DE ACTIVIDAD
   *
   * Cada 10 s se pide SOLO la actividad --'/supervisor-noc/actividad', que lee
   * y nada mas-- en vez de invalidar la pagina entera: el load del servidor
   * son cinco consultas, una de ellas la bandeja completa, y recargarlo para
   * ver si aparecio un renglon ademas te mueve el scroll y los filtros que
   * tenias puestos.
   *
   * SOLO CON LA PESTAÑA VISIBLE. Una de fondo no gasta pedidos, y ademas los
   * navegadores frenan sus timers -- por eso el intervalo no alcanza solo y se
   * escuchan tambien 'visibilitychange' y 'focus', que sondean AL INSTANTE al
   * volver. Las dos señales y no una: hay navegadores donde la primera no
   * dispara de forma confiable segun como se cambie de ventana. Es el mismo
   * patron, y por los mismos motivos medidos, que 'conversaciones/+layout'.
   *
   * UN FALLO NO APAGA EL SONDEO NI BORRA LA TABLA: se deja lo ultimo que se
   * vio y se marca que no esta en vivo. Vaciar el panel porque un pedido no
   * salio diria "no hay actividad", que es una afirmacion distinta y falsa.
   */
  $effect(() => {
    //  La carga del servidor manda: cuando vuelve a correr, se suelta lo del
    //  sondeo para no pisar con datos mas viejos lo que la persona provoco.
    void data.actividad;
    eventosVivos = null;
    huellaVista = '';
  });

  $effect(() => {
    let vigente = true;

    async function sondear() {
      if (document.visibilityState !== 'visible') return;
      await traerActividad();
    }

    //  LA LECTURA, SOLA. Se separa del sondeo para que cambiar de filtro pueda
    //  provocarla sin esperar los diez segundos -- un filtro que tarda en
    //  responder se siente roto -- y para que las dos usen el mismo camino: dos
    //  formas de leer lo mismo es tener dos lugares donde arreglar un error.
    traerActividad = async function () {
      try {
        const q = new URLSearchParams();
        if (grupo) q.set('grupo', grupo);
        const r = await fetch(`/supervisor-noc/actividad${q.size ? `?${q}` : ''}`, {
          headers: { accept: 'application/json' }
        });
        if (!r.ok) throw new Error(String(r.status));
        const cuerpo = await r.json();
        if (!vigente) return;
        //  'error' puesto con 'eventos' vacio NO es un feed vacio. Se respeta
        //  lo ultimo bueno en vez de blanquear la tabla.
        if (cuerpo?.error) {
          sondeoVivo = false;
          return;
        }
        const llegados = Array.isArray(cuerpo?.eventos) ? cuerpo.eventos : [];
        //  LOS CONTEOS VIENEN DEL BACKEND y se guardan siempre, cambie o no la
        //  lista: son de TODO el historial, no de esta tanda, asi que suben
        //  aunque los hechos nuevos no entren en la pagina que se muestra.
        porGrupo = cuerpo?.porGrupo ?? porGrupo;
        //  Solo se toma el cursor cuando NO hay paginas cargadas: si la persona
        //  ya fue hacia atras, el cursor que vale es el de su ultima pagina, no
        //  el de la primera -- pisarlo la haria volver a empezar sola.
        if (paginasViejas.length === 0) siguiente = cuerpo?.siguiente ?? null;

        //  SOLO SE ESCRIBE SI CAMBIO ALGO  --  09/10/2026
        //  ---------------------------------------------
        //  Reemplazar el estado en cada sondeo re-renderiza la pagina entera:
        //  ciento ocho propuestas, los graficos y las tablas. Cada diez
        //  segundos. La plataforma se sentia lenta --"doy un click y al rato
        //  reacciona"-- y era el hilo principal ocupado redibujando algo que
        //  casi nunca cambia: el ciclo corre UNA VEZ POR HORA, asi que de 360
        //  sondeos por hora, 359 traen exactamente lo mismo.
        //
        //  Se comparan los IDS y no los objetos: el backend serializa fechas
        //  y textos que pueden variar en forma sin ser un hecho nuevo, y
        //  comparar JSON completo volveria a disparar el re-render por nada.
        const huella = llegados.map((e) => e?.id).join(',');
        if (huella !== huellaVista) {
          huellaVista = huella;
          eventosVivos = llegados;
        }
        ultimoSondeo = new Date();
        sondeoVivo = true;
      } catch {
        if (vigente) sondeoVivo = false;
      }
    }

    sondear();
    //  TREINTA SEGUNDOS Y NO DIEZ. El ciclo del Supervisor corre una vez por
    //  hora: sondear cada diez segundos pedia 360 veces por hora un dato que
    //  cambia una. Treinta sigue siendo "en vivo" para quien mira --media
    //  vuelta de reloj-- y cuesta un tercio.
    const intervalo = setInterval(sondear, 30000);
    document.addEventListener('visibilitychange', sondear);
    window.addEventListener('focus', sondear);
    return () => {
      vigente = false;
      clearInterval(intervalo);
      document.removeEventListener('visibilitychange', sondear);
      window.removeEventListener('focus', sondear);
    };
  });

  /**
   * Cuantas hay en cada estado, para que la pastilla no mienta.
   *
   * Los tres numeros salen de la MISMA funcion que llena la tabla, y ninguno se
   * calcula por resta. Hasta el 29/09/2026 'decididas' era `total - pendientes`
   * y «Todas» era `total`: dejo de ser cierto cuando «Pendientes» empezo a
   * excluir las propuestas cuyo caso ya cerro -- esas no estan en ninguna de las
   * dos bandejas, asi que la resta las contaba como decididas sin serlo.
   *
   * Que «Todas» sea la suma de las otras dos es ahora una propiedad de como se
   * calcula, no una coincidencia que haya que recordar mantener.
   */
  const conteoPorEstado = $derived.by(() => {
    //  Se cuenta con la MISMA funcion que clasifica, una pasada y sin restas.
    //  Una propuesta que no cae en ninguna bandeja no se cuenta en ninguna --
    //  ni siquiera en «Todas», que es la union de las dos y no el total.
    //  Y con la regla de las desincronizaciones, como la tabla (19/10/2026):
    //  con 'bandejaDe' a secas decia «Pendientes (61)» sobre una tabla de 15.
    return conteoPorBandeja(propuestas, verDesincronizados);
  });

  /**
   * Cuantas hay en cada nivel DENTRO del estado elegido.
   *
   * Cuenta sobre el mismo subconjunto que la tabla muestra, no sobre el total:
   * si la bandeja esta en 'pendientes', una pastilla que diga 'Alta (80)'
   * contando tambien las ya decididas filtra a un numero distinto del que
   * anuncia.
   */
  const conteoPorNivel = $derived.by(() => {
    const base = baseDeLaBandeja(propuestas, filtroEstado, verDesincronizados);
    /** @type {Record<string, number>} */
    const cuenta = {};
    for (const p of base) cuenta[p.nivel.texto] = (cuenta[p.nivel.texto] ?? 0) + 1;
    return cuenta;
  });
  const SIN_DATO = BLOQUES_SIN_DATO;

  /**
   * Cuantas filas se ven antes de tener que desplazar, en las dos tablas.
   *
   * Con las 93 propuestas de hoy las dos tablas median ~9.900px juntas: unas
   * once pantallas solo de tablas, y todo lo de abajo --los tecnicos, las
   * ordenes, la actividad-- quedaba a un viaje de distancia. El numero no
   * esconde nada: la insignia dice cuantas se ven y el pie cuantas quedan.
   *
   * Vive aca y no en el CSS porque los dos textos lo necesitan: un alto fijo
   * en la hoja y un "se ven 5" escrito a mano se desincronizan en cuanto
   * alguien toca uno de los dos.
   */
  const FILAS_A_LA_VISTA = 5;

  /** El icono de cada KPI. Decora; el numero y su rotulo dicen todo lo demas. */
  const ICONO_KPI = {
    hallazgos: 'radar',
    propuestas: 'assignment_turned_in',
    sla: 'schedule',
    sin_programar: 'event_busy',
    bloqueados: 'block',
    desinc: 'sync_problem'
  };

  /**
   * Los tipos de señal presentes, para las pildoras. Se derivan de lo que el
   * backend devolvio: una pildora fija que filtra a cero es peor que no
   * estar. El `tipo_senal` viaja tal cual -- el rotulo es el
   * `tipo_senal_display` que manda el backend, no una traduccion propia.
   */
  const porSenal = $derived.by(() => {
    /** @type {Map<string, {etiqueta: string, n: number}>} */
    const cuenta = new Map();
    for (const p of enLaBandeja) {
      const previo = cuenta.get(p.tipo_senal);
      cuenta.set(p.tipo_senal, { etiqueta: p.tipo_senal_display, n: (previo?.n ?? 0) + 1 });
    }
    return [...cuenta.entries()].sort((a, b) => b[1].n - a[1].n);
  });



  const pendientes = $derived(propuestas.filter((/** @type {any} */ p) => p.estado === 'propuesta'));
  const fueraDeAlcance = $derived(
    propuestas.filter((/** @type {any} */ p) => p.dentro_del_alcance === false).length
  );

  const ultimaPropuesta = $derived(
    propuestas
      .map((/** @type {any} */ p) => p.created_at)
      .filter(Boolean)
      .sort()
      .at(-1) ?? null
  );

  const fecha = (/** @type {string|null} */ iso) =>
    iso
      ? new Date(iso).toLocaleString('es-CO', {
          day: '2-digit',
          month: 'short',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit'
        })
      : '—';
  //  RELOJ DE 24 HORAS, Y NO DE 12  --  15/10/2026
  //
  //  'es-CO' por omision da formato de doce horas, y eso hizo ilegible el panel
  //  de actividad: medianoche salia "12:03 a. m." y mediodia "12:03 p. m.", que
  //  de un vistazo son lo mismo. Se reporto leyendo el final de la lista como
  //  si fuera lo mas reciente -- "las horas estan revueltas"-- cuando el orden
  //  estaba bien y lo ambiguo era el reloj.
  //
  //  En 24 horas, 00:03 y 12:03 no se confunden nunca.
  const hora = (/** @type {string|null} */ iso) =>
    iso
      ? new Date(iso).toLocaleTimeString('es-CO', {
          hour: '2-digit', minute: '2-digit', hour12: false
        })
      : '—';

  /**
   * La hora, con el DIA cuando el hecho no es de hoy.
   *
   * La columna mostraba solo la hora, y con doscientos cincuenta y ocho hechos
   * de varios dias eso no alcanza para ubicar ninguno: dos renglones seguidos
   * pueden decir 11:10 y ser de dias distintos. El dia solo aparece cuando hace
   * falta -- repetir "15 oct" en cada fila de hoy es ruido.
   */
  const cuando = (/** @type {string|null} */ iso) => {
    if (!iso) return '—';
    const d = new Date(iso);
    const hoy = new Date();
    const mismoDia =
      d.getFullYear() === hoy.getFullYear() &&
      d.getMonth() === hoy.getMonth() &&
      d.getDate() === hoy.getDate();
    return mismoDia
      ? hora(iso)
      : `${d.toLocaleDateString('es-CO', { day: '2-digit', month: 'short' })} ${hora(iso)}`;
  };
  const fechaCorta = (/** @type {string|null} */ iso) =>
    iso
      ? new Date(iso).toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' })
      : '—';

  /** El sobre del indicador dice cuanto confiar en el numero. */
  function leyendaIndicador(/** @type {any} */ d) {
    if (!d || d.estado === 'SIN_DATO') return 'El backend no entregó este indicador';
    if (d.estado === 'VALIDO') return 'Dato completo';
    if (d.estado === 'NO_APLICA') return 'No aplica en el período';
    const pct = d.cobertura != null ? ` (${Math.round(d.cobertura * 100)}% de cobertura)` : '';
    return `Datos insuficientes${pct}`;
  }

  /**
   * Abre el panel lateral y pide la ficha. Una sola peticion por apertura; si
   * falla, el panel lo dice y no deja un cargando colgado.
   *
   * @param {string} id
   */
  //  El contexto de la fila --ticket, zona, tecnico, SLA-- lo resuelve el
  //  backend para el LISTADO (contexto_propuesta.py) y no viaja en el detalle.
  //  Se guarda al abrir en vez de pedirlo otra vez: ya esta en pantalla.
  let contextoFila = $state(/** @type {any} */ (null));

  async function abrirDetalle(id) {
    contextoFila = propuestas.find((/** @type {any} */ p) => p.id === id) ?? null;
    abierta = id;
    detalle = null;
    errorDetalle = null;
    cargandoDetalle = true;
    try {
      const r = await fetch(`/api/supervisor-noc/propuestas/${id}`);
      const cuerpo = await r.json().catch(() => ({}));
      if (!r.ok) {
        errorDetalle = cuerpo?.error ?? 'No fue posible consultar esta propuesta.';
      } else {
        detalle = cuerpo;
      }
    } catch {
      errorDetalle = 'No fue posible consultar esta propuesta: el servicio no respondió.';
    } finally {
      cargandoDetalle = false;
    }
  }

  /** Escape cierra el panel. Con media pantalla, llegar a la X es un viaje. */
  function alTeclado(/** @type {KeyboardEvent} */ e) {
    if (e.key === 'Escape' && abierta) cerrarDetalle();
  }

  function cerrarDetalle() {
    abierta = null;
    detalle = null;
    errorDetalle = null;
  }

  // ---------------------------------------------------------------------
  //  ENVIOS
  //  Todos refrescan desde el backend al terminar (`invalidateAll`). Nunca
  //  se corrige el estado local suponiendo que la operacion salio bien: si
  //  el backend la rechazo, la pantalla tiene que mostrar lo que el backend
  //  dice, no lo que la pantalla esperaba.
  // ---------------------------------------------------------------------
  //  LO QUE EL CICLO CERRO SOLO, para poder verificarlo.
  //
  //  Un conteo --"cerró 3"-- no se puede comprobar: hay que poder abrir esos
  //  tres y leer contra qué se cerraron. Hasta el 08/10/2026 el ciclo corría,
  //  la pantalla se recargaba, y no había forma de saber qué había hecho.
  let cerradosDelCiclo = $state(/** @type {any[]} */ ([]));

  //  Cuanto se espera antes de traer los resultados de un ciclo encolado.
  //  Medido el 13/10/2026: una corrida que lee diez tickets --cada uno con su
  //  consulta al modelo y sus herramientas-- tardo cerca de cuatro minutos. Se
  //  refresca a los dos y despues cada minuto: traer de mas es barato, y la
  //  alternativa --no refrescar-- deja a la persona mirando una bandeja vieja
  //  sin saber que ya hay resultados.
  //  SE ESPERA MAS DE LO QUE DURA EL CICLO, no menos. Medido mirando la
  //  pantalla el 14/10/2026: refrescar MIENTRAS el ciclo corre deja los
  //  recuadros en «Sin dato» --la consulta que los calcula es pesada y expira
  //  compitiendo con la corrida-- asi que el refresco que venia a mostrar los
  //  resultados terminaba BORRANDO los que ya estaban.
  //
  //  Fue la frase del cliente la que lo ubico: "los datos salen al rato y
  //  despues que presiono ejecutar ciclo se van".
  const ESPERA_INICIAL_MS = 240_000;
  const REINTENTO_MS = 120_000;
  const VECES_QUE_SE_REFRESCA = 3;
  let relojesDelCiclo = /** @type {any[]} */ ([]);

  const traerLoDelCiclo = () => {
    for (const t of relojesDelCiclo) clearTimeout(t);
    relojesDelCiclo = [];
    for (let i = 0; i < VECES_QUE_SE_REFRESCA; i++) {
      relojesDelCiclo.push(
        setTimeout(() => invalidateAll(), ESPERA_INICIAL_MS + i * REINTENTO_MS));
    }
  };

  onDestroy(() => {
    for (const t of relojesDelCiclo) clearTimeout(t);
  });

  const alCorrerCiclo = () => {
    corriendo = true;
    return async (/** @type {any} */ { update, result }) => {
      corriendo = false;
      modalCiclo = false;
      const auto = result?.data?.resumen?.cierre_automatico;
      cerradosDelCiclo = Array.isArray(auto?.cerrados_detalle) ? auto.cerrados_detalle : [];
      //  SOLO 'update', y NUNCA las dos  --  14/10/2026
      //  ----------------------------------------------
      //  'update()' ya recarga los datos de la pagina; 'invalidateAll()' los
      //  recargaba OTRA VEZ. Medido en una grabacion del cliente: dos
      //  peticiones a '__data.json' en paralelo, de 20,3 s y 19,9 s, mas la
      //  recarga de la pagina en 18,6 s.
      //
      //  Y ninguna de las dos servia para nada: el ciclo se ENCOLA y tarda
      //  seis minutos, asi que lo que traian era la misma bandeja de antes.
      //  Pedir dos veces lo mismo, para no enterarse de nada, mientras la
      //  persona mira una pantalla que no responde.
      //
      //  Los resultados los trae 'traerLoDelCiclo', que espera a que el ciclo
      //  haya terminado de verdad.
      await update({ reset: false });

      //  EL CICLO SE ENCOLO: lo que acaba de llegar es el acuse, no el
      //  resultado. Sin esto la bandeja se queda como estaba y parece que el
      //  ciclo no hizo nada.
      if (result?.data?.encolado) traerLoDelCiclo();
    };
  };

  const alCorrerAsistente = (/** @type {string} */ dominio) => () => {
    asistenteCorriendo = dominio;
    return async (/** @type {any} */ { update }) => {
      asistenteCorriendo = null;
      //  Sin 'invalidateAll' detras: 'update()' ya recarga, y pedir lo mismo
      //  dos veces cuesta dos consultas de 20 segundos (ver 'alCorrerCiclo').
      await update({ reset: false });
    };
  };


  /** Donde esta la propuesta abierta dentro de la lista visible. */
  const posicion = $derived.by(() => {
    const indice = pagina.findIndex((/** @type {any} */ p) => p.id === abierta);
    return { indice, total: pagina.length };
  });

  /** Salta a la anterior o la siguiente sin cerrar el panel. */
  function irA(/** @type {number} */ paso) {
    const destino = pagina[posicion.indice + paso];
    if (destino) abrirDetalle(destino.id);
  }

  // Las derivaciones de la ficha viven en $lib/v2/supervisor-noc-detalle.js:
  // son reglas de presentacion con casos borde, y probarlas exige poder
  // llamarlas sin montar el componente.
  const comun = $derived(comunDeEvidencia(detalle?.evidencia));
  //  --- la lectura humana del hallazgo ---
  const titulo = $derived(nombreHumano(detalle));
  //  'contraste' va ANTES de 'resumen' y 'aceptar', que lo reciben como
  //  argumento. Estaba declarado despues: Svelte compila cada $derived a un
  //  getter perezoso, asi que en ejecucion funcionaba -- por eso no se veia
  //  nada raro en pantalla -- pero svelte-check lo marcaba como uso antes de
  //  la declaracion, y bastaria que alguien convirtiera uno de los dos en una
  //  llamada directa para que reventara en la zona muerta temporal.
  const contraste = $derived(contrasteDeEstados(detalle?.evidencia));
  const resumen = $derived(quePasa(detalle, contraste));
  const prioridad = $derived(prioridadHumana(detalle));
  const identidad = $derived(identificacion(detalle, contextoFila));
  const comparacion = $derived(comparacionFuentes(detalle, contextoFila));
  //  Solo lo que de verdad compara: una fila con un lado vacio no dice nada y
  //  la columna en blanco se lee como si algo hubiera fallado.
  const comparables = $derived(filasComparables(comparacion));
  const analisis = $derived(analisisSeparado(detalle));
  const aceptar = $derived(siAcepto(detalle, contraste));
  const filasAceptar = $derived(filasDeAceptar(aceptar));
  const fuentes = $derived(fuentesDeEvidencia(detalle?.evidencia));
  const basePrioridad = $derived(baseDePrioridad(detalle?.evidencia));
  const antiguedad = $derived(antiguedadDelCaso(detalle?.evidencia));
  const lectura = $derived(lecturaExterna(detalle?.evidencia));

  /**
   * DECIDIR TARDA, Y HAY QUE DECIRLO  --  09/10/2026
   *
   * Reportado y reproducido: "le doy click en aceptar propuesta y se queda
   * como si no hubiera dado click; ya despues de una espera espabila la
   * pantalla". No era lentitud de la plataforma: aceptar una propuesta de
   * caso desincronizado EJECUTA el cierre --va al motor, que llama a
   * WispHub-- y despues recarga el tablero entero y vuelve a abrir la ficha.
   * Son varios segundos, y durante todos la interfaz no cambiaba en nada.
   *
   * Un boton que no reacciona invita a apretarlo otra vez, y eso manda una
   * segunda decision sobre la misma propuesta. No rompe nada --la segunda
   * encuentra la propuesta ya revisada y la frontera la rechaza-- pero la
   * persona ve un error por haber hecho lo unico razonable.
   *
   * El patron ya existia en esta pantalla para el boton del ciclo
   * ('Analizando…'); esto lo aplica donde faltaba.
   *
   * EL ROTULO SE PONE AL ENVIAR, NO AL HACER CLIC  --  19/10/2026
   * ------------------------------------------------------------
   * Reportado: "le doy aceptar propuesta y se queda asi", con el boton en
   * «Guardando…» para siempre. Desde el 09/10 el rotulo se ponia en el
   * 'onclick', y el 'disabled' de los tres botones depende de el. Svelte
   * aplica el cambio en un microtask que corre ANTES de que el navegador envie
   * el formulario, y un boton de envio deshabilitado no envia nada: la
   * decision nunca salia, y nada soltaba el rotulo porque el 'finally' de
   * abajo solo corre si hubo envio.
   *
   * MEDIDO con un clic real (Chrome sin interfaz, DevTools Protocol) sobre un
   * componente Svelte 5 con el mismo patron: el clic quedaba en 'click' sin
   * 'submit'. Marcando el rotulo al enviar, 'click' y 'submit'.
   *
   * Ahora lo pone 'enhance', que corre cuando el formulario YA salio y sabe
   * que boton se apreto ('submitter'). El rotulo viaja en 'data-espera' de
   * cada boton. El doble clic sigue cubierto: el segundo encuentra los tres
   * botones deshabilitados.
   */
  let decidiendo = $state('');

  const alDecidir = (/** @type {any} */ { submitter }) => {
    decidiendo = submitter?.dataset?.espera || 'Guardando…';
    return async (/** @type {any} */ { update }) => {
      revisando = null;
      comentario = '';
      //  CUAL ERA LA SIGUIENTE, antes de que la lista se recalcule. Despues de
      //  decidir, la propuesta actual sale de la bandeja de pendientes y los
      //  indices se corren: preguntarlo despues devolveria otra.
      const siguiente = pagina[posicion.indice + 1]?.id ?? null;
      try {
        await update({ reset: false });

        //  SE AVANZA PRIMERO Y SE REFRESCA DESPUES  --  09/10/2026
        //  ------------------------------------------------------
        //  Reportado: "demora mucho cerrando un caso y no deja adelantar otro".
        //  Eran DOS esperas encadenadas: el cierre contra WispHub --que es
        //  inevitable-- y despues recargar el tablero entero y volver a abrir
        //  LA MISMA ficha, que es justo la que la persona ya termino de mirar.
        //
        //  Ahora se salta a la siguiente apenas el cierre volvio, y el tablero
        //  se refresca por detras SIN ESPERARLO. Lo unico que queda viejo por
        //  unos segundos son los contadores de arriba; la ficha que se esta
        //  mirando es la que se acaba de pedir, asi que esta fresca.
        if (siguiente) {
          await abrirDetalle(siguiente);
        } else if (abierta) {
          //  Era la ultima: se queda, con su estado ya actualizado.
          await abrirDetalle(abierta);
        }

        //  SIN 'await' a proposito. Si se espera, se vuelve a pagar la recarga
        //  completa --cinco consultas, ciento ocho propuestas-- antes de que la
        //  persona pueda hacer nada.
        invalidateAll();
      } finally {
        //  SIEMPRE se suelta, aunque algo falle: un boton que queda
        //  deshabilitado para siempre despues de un error de red obliga a
        //  recargar la pagina para volver a intentar.
        decidiendo = '';
      }
    };
  };

  // =====================================================================
  //  ACEPTAR VARIAS PROPUESTAS DE UNA VEZ
  // =====================================================================
  //  POR QUE DE A UNA Y NO EN UN SOLO PEDIDO
  //  ---------------------------------------
  //  Aceptar EJECUTA el cierre: va al motor y vuelve al backend. Son varios
  //  segundos cada una. Mandar veinte en un solo pedido daria un minuto largo
  //  sin señal de vida, y si se corta a la mitad nadie sabria cuales se
  //  cerraron.
  //
  //  De a una, en orden, se ve el avance ("8 de 20"), se puede detener, y
  //  cada una usa EXACTAMENTE el mismo camino que el boton de siempre: la
  //  accion '?/revisar', con su rol, su frontera y su validacion con el caso
  //  bloqueado. No se abre ninguna puerta nueva en el servidor -- y eso es
  //  deliberado: una accion masiva propia seria una segunda forma de cerrar
  //  casos, con sus propios permisos que mantener en sincronia.

  /** Los ids tildados. Objeto y no Set: '$state' lo hace reactivo al vuelo. */
  let seleccion = $state(/** @type {Record<string, boolean>} */ ({}));

  const seleccionadas = $derived(
    Object.keys(seleccion).filter((id) => seleccion[id]));

  //  SOLO LAS PENDIENTES se pueden tildar: una ya decidida no se vuelve a
  //  decidir, y ofrecerla seria prometer algo que el backend rechaza.
  const seleccionables = $derived(pagina.filter((/** @type {any} */ p) => p.revision.pendiente));
  //  Qué promete el botón, calculado sobre lo que está tildado AHORA.
  const lote = $derived(loteDeSeleccion(pagina, seleccionadas));

  const todasTildadas = $derived(
    seleccionables.length > 0 &&
    seleccionables.every((/** @type {any} */ p) => seleccion[p.id]));

  function tildarTodas() {
    const poner = !todasTildadas;
    for (const p of seleccionables) seleccion[p.id] = poner;
  }

  function limpiarSeleccion() {
    seleccion = {};
  }

  //  EL AVANCE, para que la espera no sea un hueco.
  let enLote = $state(false);
  let loteHechas = $state(0);
  let loteTotal = $state(0);
  let loteDetener = $state(false);
  let loteResultado = $state(/** @type {null | {ok: number, fallaron: number, detalle: string[]}} */ (null));

  async function aceptarSeleccionadas() {
    const ids = seleccionadas.slice();
    if (ids.length === 0 || enLote) return;

    enLote = true;
    loteDetener = false;
    loteHechas = 0;
    loteTotal = ids.length;
    loteResultado = null;
    let ok = 0;
    const fallos = [];

    try {
      for (const id of ids) {
        //  SE CONSULTA ANTES DE CADA UNA, no una vez al principio: si la
        //  persona aprieta "Detener", se detiene en la siguiente en vez de
        //  terminar las veinte.
        if (loteDetener) break;

        const cuerpo = new FormData();
        cuerpo.set('id', id);
        cuerpo.set('decision', 'aceptada');
        cuerpo.set('comentario', '');

        try {
          const r = await fetch('?/revisar', { method: 'POST', body: cuerpo });
          const res = deserialize(await r.text());
          if (res.type === 'success') {
            ok += 1;
            //  Se destilda la que SI salio. Las que fallaron quedan tildadas,
            //  asi que reintentar es volver a apretar el boton.
            seleccion[id] = false;
          } else {
            const d = /** @type {any} */ (res).data;
            fallos.push(`${id.slice(0, 8)}: ${d?.error ?? 'no se pudo'}`);
          }
        } catch (/** @type {any} */ e) {
          fallos.push(`${id.slice(0, 8)}: ${e?.message ?? 'error de red'}`);
        }
        loteHechas += 1;
      }
    } finally {
      enLote = false;
      loteResultado = { ok, fallaron: fallos.length, detalle: fallos.slice(0, 5) };
      //  UNA SOLA RECARGA AL FINAL. Recargar despues de cada cierre serian
      //  veinte recargas del tablero entero mientras la persona espera.
      await invalidateAll();
      if (abierta) await abrirDetalle(abierta);
    }
  }
</script>

<svelte:window onkeydown={alTeclado} />

<svelte:head>
  <title>Supervisor NOC · {data.org ?? 'Operaciones'}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="" />
  <link
    href="https://fonts.googleapis.com/css2?family=Atkinson+Hyperlegible+Next:wght@400;500;700&family=Barlow+Semi+Condensed:wght@500;600;700&family=JetBrains+Mono:wght@500;700&family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap"
    rel="stylesheet"
  />
</svelte:head>

<div class="snoc snv" class:snv-con-detalle={abierta}>
  <!--
    v2-scroll NO ES DECORACION: es el unico contenedor que hace scroll.

    El shell de (app) es `height:100vh; overflow:hidden` y `.v2-main`
    tambien recorta (lib/v2/styles/v2.css). Sin esta envoltura la pantalla
    se ve entera solo si cabe: todo lo que pasa del alto de la ventana
    queda recortado y no hay forma de llegar a lo de abajo.

    Es el mismo fallo que settings/guias-tv dejo escrito el 10/09/2026, y
    volvio a pasar por la misma razon: la pantalla trae su propio CSS y se
    ve completa sin el mientras el contenido quepa. Los dos modales quedan
    FUERA -- son position:fixed y cubren la ventana, no el contenido
    desplazado.
  -->
  <div class="v2-scroll">
    <div class="snoc-lienzo">
      {#if !data.puedeVer}
        <section class="snoc-panel">
          <div class="snoc-fila">
            <span class="snoc-icono snoc-error-txt" style="font-size:28px;">lock</span>
            <div class="snoc-pila-xs">
              <h1 class="snoc-h2">Supervisor NOC IA</h1>
              <p class="snoc-body snoc-secundario">
                Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede ver y revisar las propuestas. Tu rol es
                <strong class="snoc-mono">{data.rol ?? 'sin rol'}</strong>.
              </p>
            </div>
          </div>
        </section>
      {:else}
        <!-- ============ CABECERA ============ -->
        <header class="snv-cabecera">
          <div class="snv-cabecera-fila">
            <div class="snv-cabecera-izq">
              <h1 class="snv-titulo-pantalla"><span class="snv-rombo" aria-hidden="true"></span>Supervisor NOC</h1>
              <!--
                La respuesta a «¿cómo está la operación?», antes que cualquier
                número. La frase y los grupos de la bandeja cuentan con la MISMA
                función (cuentaPorPlazo), sobre la MISMA lista que «Pendientes».
              -->
              <p class="snv-titular" id="snv-titular">
                {titular.principal}{#if titular.alerta}{' '}<span class="snv-critico">{titular.alerta}</span>{/if}
              </p>
              {#if titular.bajada || (sobrePendientes && sobrePendientes.tickets < sobrePendientes.propuestas)}
                <p class="snv-bajada">
                  {titular.bajada ?? ''}
                  {#if sobrePendientes && sobrePendientes.tickets < sobrePendientes.propuestas}
                    Son {sobrePendientes.propuestas} propuestas sobre {sobrePendientes.tickets}
                    {sobrePendientes.palabra}.
                  {/if}
                </p>
              {/if}
            </div>
            <div class="snv-cabecera-der">
              <span
                class="snv-ultimo"
                title="Derivado de la propuesta más reciente: el backend no registra cuándo corrió el ciclo."
              >
                Última propuesta: {ultimaPropuesta ? haceCuanto(ultimaPropuesta) : 'ninguna todavía'}
              </span>
              <button class="snv-btn snv-btn-pri" type="button" onclick={() => (modalCiclo = true)} disabled={corriendo}>
                <span aria-hidden="true">▶</span>
                {corriendo ? 'Analizando…' : 'Analizar ahora'}
              </button>
            </div>
          </div>
          <div class="snv-pestanas">
            <PestanasNoc activa="pendientes" />
          </div>
        </header>

        {#if indicadoresVivos?.error}
          <div class="snoc-aviso">
            <span class="snoc-icono snoc-error-txt" style="font-size:20px;" aria-hidden="true">error</span>
            <p class="snoc-body" style="margin:0;">{indicadoresVivos.error.mensaje}</p>
          </div>
        {/if}

        <!--
          ============ AHORA MISMO ============
          Cinco signos. El color aparece solo si el número pide atención; un
          cero o un hueco van en gris. «SLA en riesgo» y «Sin técnico» salen de
          la bandeja de pendientes (mismo conteo que los grupos); bloqueados,
          sin programar y desincronizados son los indicadores del backend.
        -->
        <section class="snv-caja snv-ahora" aria-labelledby="snv-ahora-titulo">
          <h2 class="snv-h3" id="snv-ahora-titulo">Ahora mismo</h2>
          <div class="snv-signos" role="group" aria-label="Signos vitales de la operación">
            <a class="snv-signo snv-signo-enlace {enRiesgo.vencido ? 'snv-tono-critico' : enRiesgo.total ? 'snv-tono-alerta' : 'snv-tono-calma'}"
               href="#pendientes" onclick={irAPendientes}>
              <span class="snv-signo-n">{enRiesgo.total ?? 'Sin dato'}</span>
              <span class="snv-signo-rot">SLA en riesgo</span>
              <span class="snv-signo-sub">
                {enRiesgo.total == null ? 'la bandeja no se pudo leer' : `${enRiesgo.vencido} vencidas · ${enRiesgo.pronto} por vencer`}
              </span>
            </a>
            {#each signosDelBackend as k (k.clave)}
              <div class="snv-signo {k.n ? (k.clave === 'bloqueados' ? 'snv-tono-alerta' : '') : 'snv-tono-calma'}">
                <!-- Un hueco, no un cero: el backend no entregó el indicador. -->
                <span class="snv-signo-n">{k.n ?? (esperandoIndicadores ? '…' : 'Sin dato')}</span>
                <span class="snv-signo-rot">{k.rotulo}</span>
              </div>
            {/each}
            <div class="snv-signo {sinTecnico ? '' : 'snv-tono-calma'}">
              <span class="snv-signo-n">{sinTecnico ?? 'Sin dato'}</span>
              <span class="snv-signo-rot">Sin técnico</span>
            </div>
            <!--
              13/10/2026: los desincronizados salieron de la bandeja --los
              cierra el Supervisor solo-- y este signo es SU LUGAR. Es un
              <button>: muestra solo esos casos.
            -->
            <button
              class="snv-signo snv-signo-enlace snv-tono-calma"
              type="button"
              aria-pressed={verDesincronizados === 'solo'}
              title="Ver los casos desincronizados en la bandeja"
              onclick={() => {
                //  EL ORDEN IMPORTA: 'irAPendientes' deja la vista en
                //  'ocultar', asi que el modo se fija DESPUES.
                const prender = verDesincronizados !== 'solo';
                irAPendientes();
                verDesincronizados = prender ? 'solo' : 'ocultar';
                nPagina = 1;
                document.getElementById('pendientes')?.scrollIntoView({ block: 'start' });
              }}
            >
              <span class="snv-signo-n">{desincronizados ?? (esperandoIndicadores ? '…' : 'Sin dato')}</span>
              <span class="snv-signo-rot">Desincronizados</span>
              <span class="snv-signo-sub">
                {verDesincronizados === 'solo' ? 'viéndolos · tocá para volver' : 'los cierra el Supervisor'}
              </span>
            </button>
          </div>
        </section>

          {#if form?.ok && form.tipo === 'ciclo' && form.encolado}
            <!--
              EL CICLO SE ENCOLA Y NO SE ESPERA (13/10/2026). Mostrar aqui el
              resumen con ceros seria PEOR que no mostrar nada: diria "cero
              propuestas nuevas" sobre un ciclo que todavia no empezo, y eso se
              lee como "no encontro nada".
            -->
            <div class="snoc-resultado">
              <span class="snoc-label-sm" style="text-transform:uppercase;">Ciclo en marcha</span>
              <span class="snoc-body-sm">
                El Supervisor está analizando la operación. Lee los tickets uno
                por uno y consulta el equipo de cada cliente, así que tarda unos
                minutos.
              </span>
              <span class="snoc-mono-sm snoc-tenue">
                Podés cerrar esto y seguir trabajando: los resultados aparecen
                en la bandeja cuando termine.
              </span>
            </div>
          {:else if form?.ok && form.tipo === 'ciclo' && form.resumen}
            <div class="snoc-resultado">
              <span class="snoc-label-sm" style="text-transform:uppercase;">Último ciclo</span>
              <div class="snoc-mono-sm snoc-pila-xs">
                <span>Señales detectadas: <strong>{form.resumen?.senales ?? 0}</strong></span>
                <span>Propuestas nuevas: <strong>{form.resumen?.propuestas ?? 0}</strong></span>
                <span>Repetidas: <strong>{form.resumen?.repetidas ?? 0}</strong></span>
                <span>Datos insuficientes: <strong>{form.resumen?.datos_insuficientes ?? 0}</strong></span>
                <span>Expiradas: <strong>{form.resumen?.expiradas ?? 0}</strong></span>
              </div>
              <span class="snoc-mono-sm snoc-tenue">Acciones ejecutadas: {form.acciones_ejecutadas ?? 0}</span>
            </div>
          {/if}

        <!--
          ============ QUÉ HACE EL SUPERVISOR SOLO ============
          01/11/2026. Desde que aprueba y cierra órdenes solo, es lo primero que
          necesita saber quien mira. Las dos tareas que más pesan van en
          tarjeta propia, con el MISMO estado de tres valores que el modal de
          Alcance; la tercera tarjeta es la autonomía ganada, la misma lectura
          que la pantalla de Capacidad. Las demás tareas delegadas se nombran
          abajo: esconderlas sería decir que no corren.
        -->
        <section class="snv-solo" aria-labelledby="snv-solo-titulo">
          <div class="snv-seccion-cab">
            <h2 class="snv-h3" id="snv-solo-titulo">Qué hace el Supervisor solo</h2>
            <button class="snv-enlace" type="button" onclick={abrirAlcance}>Ver reglas de autonomía ↗</button>
          </div>
          {#if tarjetas.frenado}
            <p class="snv-freno">
              <strong>Freno de mano puesto.</strong> Ninguna acción automática corre hasta que alguien lo levante.
              <button class="snv-enlace" type="button" onclick={abrirAlcance}>Ver por qué</button>
            </p>
          {/if}
          <div class="snv-tarjetas">
            {#each [{ t: tarjetas.desincronizados, titulo: 'Cierra casos desincronizados', pie: 'No toca WispHub.' }, { t: tarjetas.ordenes, titulo: 'Aprueba y cierra órdenes de trabajo (OT)', pie: 'Cierra el ticket en WispHub y después la orden en Dexter.' }] as c (c.titulo)}
              <article class="snv-tarjeta">
                <h3 class="snv-tarjeta-titulo">{c.titulo}</h3>
                {#if !alcance}
                  <p class="snv-nota">{alcanceError || 'Leyendo…'}</p>
                {:else if !c.t}
                  <p class="snv-nota">El catálogo de tareas no la trae.</p>
                {:else}
                  <span class="snv-estado snv-estado-{c.t.estado}">
                    <span class="snv-punto" aria-hidden="true"></span>
                    {c.t.estado === 'encendida' ? 'Encendido' : c.t.estado === 'apagada' ? 'Apagado' : 'No actúa'}
                  </span>
                  {#if c.t.estado === 'no_actua'}
                    <p class="snv-tarjeta-txt snv-critico">
                      {c.t.porQue}
                      <button class="snv-enlace" type="button" onclick={abrirAlcance}>Ver por qué</button>
                    </p>
                  {:else if c.t.estado === 'apagada'}
                    <p class="snv-tarjeta-txt">No está delegada. <a class="snv-enlace" href="/supervisor-noc/ajustes">Delegar</a></p>
                  {:else}
                    <p class="snv-tarjeta-txt">{c.pie}</p>
                  {/if}
                {/if}
              </article>
            {/each}
            <article class="snv-tarjeta">
              <h3 class="snv-tarjeta-titulo">Autonomía ganada</h3>
              {#if !ganada.leido}
                <p class="snv-nota">Leyendo…</p>
              {:else if ganada.error}
                <p class="snv-nota">No se pudo leer: {ganada.error}</p>
              {:else}
                {#if ganada.autonomas.length}
                  <p class="snv-tarjeta-linea"><span class="snv-punto snv-punto-vivo" aria-hidden="true"></span>
                    {ganada.autonomas.length} {ganada.autonomas.length === 1 ? 'acción se hace sola' : 'acciones se hacen solas'}:
                    {ganada.autonomas.map(nombreDeAccion).join(', ')}</p>
                {:else}
                  <p class="snv-tarjeta-linea">Ninguna acción se hace sola todavía.</p>
                {/if}
                {#if ganada.elegibles.length}
                  <p class="snv-tarjeta-linea"><span class="snv-punto snv-punto-alerta" aria-hidden="true"></span>
                    {ganada.elegibles.length} con la evidencia para ganarla: {ganada.elegibles.map(nombreDeAccion).join(', ')}</p>
                {/if}
                {#if ganada.degradadas.length}
                  <p class="snv-tarjeta-linea snv-critico"><span class="snv-punto snv-punto-critico" aria-hidden="true"></span>
                    {ganada.degradadas.length} la perdió por un fallo: {ganada.degradadas.map(nombreDeAccion).join(', ')}</p>
                {/if}
                <a class="snv-enlace" href="/capacidad">Ver en Capacidad</a>
              {/if}
            </article>
          </div>
          {#if tarjetas.otras.length}
            <p class="snv-nota snv-otras">
              También tiene delegadas:
              {#each tarjetas.otras as o, i (o.clave)}{i ? ' · ' : ' '}<span class={o.actua ? '' : 'snv-critico'} title={o.porQue ?? o.queHace}>{o.nombre}{o.actua ? '' : ' (no actúa)'}</span>{/each}.
              <a class="snv-enlace" href="/supervisor-noc/ajustes">Delegar o quitar</a>
            </p>
          {/if}
          {#if fueraDeAlcance > 0}
            <p class="snv-nota snv-critico">{fueraDeAlcance} propuestas quedaron por encima de su alcance.</p>
          {/if}
        </section>

        <div class="snv-cuerpo">
          <div class="snv-columna-principal">
            <!--
              ============ PARA DECIDIR ============
              Lo único que pide una decisión de una persona. Agrupada por
              PLAZO, con los grupos tranquilos plegados cuando hay urgentes.
              Dentro de cada grupo se respeta el orden de la bandeja. Decidir
              sigue en «Revisar», junto a la evidencia.
            -->
            <section class="snv-decidir" id="pendientes" aria-labelledby="snv-decidir-titulo">
              <div class="snv-decidir-cab">
                <h2 class="snv-h2" id="snv-decidir-titulo">Para decidir</h2>
                {#if !data.hallazgos.error}
                  <span class="snv-pildora-n" title="Pendientes de decisión">{conteoPorEstado.pendientes ?? 0}</span>
                {/if}
                {#if !data.hallazgos.error && propuestas.length > 0}
                  <div class="snv-segmentado" role="group" aria-label="Estado de la revisión">
                    {#each [{ v: 'pendientes', t: 'Pendientes' }, { v: 'decididas', t: 'Ya decididas' }, { v: '', t: 'Todas' }] as o (o.v)}
                      <button type="button" aria-pressed={filtroEstado === o.v} onclick={() => (filtroEstado = o.v)}>
                        {o.t}<span class="snv-cuenta">{conteoPorEstado[o.v] ?? 0}</span>
                      </button>
                    {/each}
                  </div>
                {/if}
              </div>
              {#if data.hallazgos.error}
                <p class="snv-nota snv-critico">No se pudieron leer las propuestas.</p>
              {:else if sobreLaBandeja.tickets < bandeja.length || data.hallazgos.truncado}
                <p class="snv-nota">
                  {#if sobreLaBandeja.tickets < bandeja.length}
                    {bandeja.length} propuestas sobre {sobreLaBandeja.tickets} {sobreLaBandeja.palabra}.
                  {/if}
                  <!-- EL TOPE SE DICE (19/10/2026): el backend manda 200 y lo que
                       espera decision va primero. -->
                  {#if data.hallazgos.truncado}
                    Se cargaron {propuestas.length} de {data.hallazgos.count}: las que esperan decisión van
                    primero, y «Ya decididas» puede quedar corta.
                  {/if}
                </p>
              {/if}

              {#if !data.hallazgos.error && propuestas.length > 0}
                <!-- Los filtros se aplican en el navegador: el GET ya trajo el
                     conjunto entero. -->
                <div class="snv-filtros">
                  <label class="snv-buscador">
                    <span aria-hidden="true">⌕</span>
                    <input type="search" placeholder="Buscar por cliente, caso, OT o ticket…" bind:value={busqueda}
                           aria-label="Buscar en las propuestas" />
                  </label>
                  <select class="snv-select" aria-label="Filtrar por prioridad" value={filtroNivel ?? ''}
                          onchange={(e) => (filtroNivel = e.currentTarget.value || null)}>
                    <option value="">Prioridad</option>
                    {#each NIVELES_VISIBLES as nv (nv)}
                      <option value={nv} disabled={(conteoPorNivel[nv] ?? 0) === 0}>{nv} ({conteoPorNivel[nv] ?? 0})</option>
                    {/each}
                  </select>
                  <select class="snv-select" aria-label="Filtrar por tipo de hallazgo" value={filtro ?? ''}
                          onchange={(e) => (filtro = e.currentTarget.value || null)}>
                    <option value="">Tipo</option>
                    {#each porSenal as [clave, info] (clave)}
                      <option value={clave}>{rotuloDeHallazgo(clave, info.etiqueta)} ({info.n})</option>
                    {/each}
                  </select>
                  <select class="snv-select" aria-label="Filtrar por si trae acción recomendada" value={filtroPropuesta}
                          onchange={(e) => (filtroPropuesta = e.currentTarget.value)}>
                    <option value="">Con y sin acción</option>
                    <option value="si">Con acción recomendada</option>
                    <option value="no">Sin acción recomendada</option>
                  </select>
                  <select class="snv-select" aria-label="Ordenar la bandeja" bind:value={ordenar}>
                    <option value="plazo">Ordenar: Plazo</option>
                    <option value="prioridad">Ordenar: Prioridad</option>
                  </select>
                  {#if hayFiltros}
                    <button class="snv-enlace" type="button" onclick={limpiarFiltros}>Limpiar filtros</button>
                  {/if}
                </div>
                {#if verDesincronizados === 'solo'}
                  <p class="snv-aviso-filtro">
                    Mostrando solo los casos desincronizados, que el Supervisor cierra solo.
                    <button class="snv-enlace" type="button" onclick={() => (verDesincronizados = 'ocultar')}>
                      Volver a la bandeja
                    </button>
                  </p>
                {/if}
              {/if}

          {#if form?.error}
            <div class="snoc-aviso">
              <span class="snoc-icono snoc-error-txt" style="font-size:18px;">error</span>
              <span class="snoc-body">{form.error}</span>
            </div>
          {:else if form?.ok && form.tipo === 'revision'}
            <!--
              Seis resultados posibles, y dos de ellos se parecen sin ser lo
              mismo: "el interruptor esta detenido" se arregla levantandolo y
              "cambio la condicion" no se arregla. La traduccion vive en
              $lib/v2/resultado-del-cierre.js y esta probada aparte; aca solo se
              muestra, sin rediseniar nada.
            -->
            {@const res = resultadoDelCierre({
              estado: 'aceptada',
              ejecutada: form.ejecutada,
              motivo: form.motivo,
              detalle: form.detalle
            })}
            <div class="snoc-aviso">
              <span
                class="snoc-icono {res.tono === 'ok' ? 'snoc-primario' : 'snoc-error-txt'}"
                style="font-size:18px;"
              >
                {res.tono === 'ok' ? 'check_circle' : 'warning'}
              </span>
              <span class="snoc-body">
                Revisión registrada: <strong>{form.decision}</strong>.
                <strong>{res.titulo}.</strong>
                {res.explicacion}
              </span>
            </div>
          {:else if form?.ok && form.tipo === 'cancelacion'}
            <div class="snoc-aviso">
              <span class="snoc-icono snoc-primario" style="font-size:18px;">check_circle</span>
              <span class="snoc-body">Propuesta cancelada. Ninguna acción se ejecutó.</span>
            </div>
          {/if}

              {#if data.hallazgos.error}
                <div class="snoc-aviso">
                  <span class="snoc-icono snoc-error-txt" style="font-size:18px;" aria-hidden="true">error</span>
                  <span class="snoc-body">{data.hallazgos.error.mensaje}</span>
                </div>
              {:else if propuestas.length === 0}
                <div class="snv-vacio">
                  <strong>Todavía no hay propuestas</strong>
                  Usá «Analizar ahora» para que el Supervisor revise la operación.
                </div>
              {:else if bandeja.length === 0}
                <div class="snv-vacio">
                  {#if busqueda.trim() || filtro || filtroNivel || filtroPropuesta}
                    <strong>Nada coincide</strong>
                    {busqueda.trim()
                      ? `Ninguna propuesta coincide con «${busqueda.trim()}».`
                      : 'Ninguna propuesta con esos filtros.'}
                    <button class="snv-enlace" type="button" onclick={limpiarFiltros}>Limpiar filtros</button>
                  {:else if filtroEstado === 'pendientes'}
                    <strong>Todo al día</strong>
                    No hay propuestas esperando tu decisión.
                  {:else}
                    <strong>Nada en esta lista</strong>
                    <button class="snv-enlace" type="button" onclick={limpiarFiltros}>Volver a pendientes</button>
                  {/if}
                </div>
              {:else}
                <div class="snv-bandeja">
                  <!--
                    LA BARRA DE SELECCION. Tilda SOLO las pendientes de esta
                    pagina: "seleccionar todo" sobre algo que no se ve es la forma
                    mas facil de aceptar algo que nadie miro. Con algo tildado,
                    muestra el lote --que dice que hace segun lo tildado--.
                  -->
                  <div class="snv-barra-sel">
                    {#if seleccionables.length > 0}
                      <input type="checkbox" aria-label="Seleccionar las pendientes de esta página"
                             checked={todasTildadas} disabled={enLote} onchange={tildarTodas} />
                    {/if}
            {#if seleccionadas.length > 0 || enLote || loteResultado}
              <div class="snoc-lote">
                {#if enLote}
                  <span class="snoc-lote-texto">
                    Cerrando <strong>{loteHechas}</strong> de {loteTotal}…
                  </span>
                  <!--
                    DETENER, Y NO CANCELAR: lo ya cerrado no se deshace. La
                    palabra importa -- "cancelar" invitaria a creer que vuelve
                    atras lo que ya salio.
                  -->
                  <button class="snoc-btn" type="button" onclick={() => (loteDetener = true)}>
                    {loteDetener ? 'Deteniendo…' : 'Detener'}
                  </button>
                {:else if loteResultado}
                  <span class="snoc-lote-texto">
                    Se cerraron <strong>{loteResultado.ok}</strong>.
                    {#if loteResultado.fallaron > 0}
                      {loteResultado.fallaron} no se pudieron y siguen tildadas.
                    {/if}
                  </span>
                  <button class="snoc-btn" type="button" onclick={() => (loteResultado = null)}>
                    Entendido
                  </button>
                {:else}
                  <span class="snoc-lote-texto">
                    <strong>{seleccionadas.length}</strong>
                    {seleccionadas.length === 1 ? 'propuesta seleccionada' : 'propuestas seleccionadas'}
                  </span>
                  <button class="snoc-btn" type="button" onclick={limpiarSeleccion}>
                    Limpiar
                  </button>
                  <!--
                    EL ROTULO LO DECIDE LO TILDADO, no el botón. Decía
                    "Aceptar y cerrar" siempre, también sobre seis propuestas
                    que no cierran ninguna: quien lo apretaba se iba creyendo
                    que esos seis casos quedaron resueltos.

                    (El comentario anterior además decía que el cierre es
                    "contra el proveedor", y es al revés: cierra en Dexter y
                    NUNCA toca WispHub.)
                  -->
                  {#if lote.aclaracion}
                    <span class="snoc-mono-sm snoc-tenue">{lote.aclaracion}</span>
                  {/if}
                  <button
                    class="snoc-btn snoc-btn-primario"
                    type="button"
                    onclick={aceptarSeleccionadas}
                  >
                    {lote.etiqueta}
                  </button>
                {/if}
              </div>
              {#if loteResultado && loteResultado.detalle.length > 0}
                <ul class="snoc-lote-fallos">
                  {#each loteResultado.detalle as f}
                    <li>{f}</li>
                  {/each}
                </ul>
              {/if}
            {/if}
                    {#if !(seleccionadas.length > 0 || enLote || loteResultado)}
                      <span class="snv-nota">
                        {seleccionables.length > 0
                          ? `Seleccionar las ${seleccionables.length} pendientes de esta página`
                          : 'Nada para seleccionar en esta página'}
                      </span>
                    {/if}
                  </div>

                  {#snippet fila(/** @type {any} */ p)}
                    {@const pl = textoDePlazo(p.sla_estado, p.sla_minutos)}
                    <div class="snv-fila {abierta === p.id ? 'snv-fila-abierta' : ''} {p.revision.pendiente ? '' : 'snv-fila-decidida'}">
                      <div class="snv-c-check">
                        {#if p.revision.pendiente}
                          <input type="checkbox" aria-label="Seleccionar la propuesta de {p.cliente ?? 'este caso'}"
                                 checked={!!seleccion[p.id]} disabled={enLote}
                                 onchange={() => (seleccion[p.id] = !seleccion[p.id])} />
                        {/if}
                      </div>
                      <div class="snv-c-plazo snv-tono-{pl.tono}" title={pl.detalle || undefined}>{pl.texto}</div>
                      <div class="snv-c-quien">
                        <!-- EL CLIENTE, SIEMPRE EN LA MISMA COLUMNA. Si la fuente
                             no lo trae se dice; no se rellena con el evento. -->
                        {#if p.cliente}
                          <span class="snv-cliente">{p.cliente}</span>
                        {:else}
                          <span class="snv-cliente snoc-celda-ausente">Cliente no disponible</span>
                        {/if}
                        <span class="snv-asunto" title={p.asunto}>{p.asunto || 'Sin asunto en la fuente'}</span>
                        {#if !p.revision.pendiente}
                          <span class="snv-tag snv-tag-decidida" title="Ya pasó por una persona">{p.revision.texto}</span>
                        {/if}
                        {#if (sobreLaBandeja.porOrigen.get(origenDe(p)) ?? 0) > 1}
                          <span class="snv-tag" title="Para que se vea CUAL ticket cuenta dos veces">
                            {sobreLaBandeja.porOrigen.get(origenDe(p))} propuestas de este ticket
                          </span>
                        {/if}
                      </div>
                      <div class="snv-c-prio">
                        <span class="snv-tag {p.nivel.texto === 'Alta' ? 'snv-tag-alta' : ''}"
                              title="Prioridad {p.prioridad} en la escala del Supervisor (0-99, menor es más urgente)">{p.nivel.texto}</span>
                      </div>
                      <div class="snv-c-tipo"><span class="snv-tag">{rotuloDeHallazgo(p.tipo_senal, p.tipo_senal_display)}</span></div>
                      <div class="snv-c-propone" title={p.accion_propuesta || undefined}>
                        {#if p.tienePropuesta}{p.accion_propuesta}{:else}<span class="snv-propone-vacia">Sin acción para recomendar</span>{/if}
                      </div>
                      <div class="snv-c-tecnico">
                        <!-- EL TÉCNICO ACTUAL, no el que la IA sugiere. -->
                        {#if p.tecnico}{p.tecnico}{:else}<span class="snv-sin-tecnico">Sin técnico</span>{/if}
                      </div>
                      <div class="snv-c-ids">
                        <!-- Los dos identificadores: el caso de este lado y el
                             número del proveedor para buscarlo allá. -->
                        {#if p.orden_numero != null}
                          <span>OT-{p.orden_numero}</span>
                        {:else if p.caso_id}
                          <a href="/tickets/{p.caso_id}" title="Abrir el caso en Dexter">Caso {String(p.caso_id).slice(0, 8)}</a>
                        {:else if !p.ticket_externo}
                          <span title={p.origen_id}>{String(p.origen_id).slice(0, 8)}</span>
                        {/if}
                        {#if p.ticket_externo}<span title={p.proveedor_externo ?? undefined}>{p.ticket_externo}</span>{/if}
                      </div>
                      <div class="snv-c-accion">
                        <button class="snv-btn snv-btn-sec {abierta === p.id ? 'snv-btn-activo' : ''}" type="button"
                                onclick={() => abrirDetalle(p.id)}
                                aria-label="Revisar la propuesta de {p.cliente ?? 'este caso'}">Revisar</button>
                      </div>
                    </div>
                  {/snippet}

                  {#if ordenar === 'plazo'}
                    {#each gruposDeLaPagina as g (g.clave)}
                      {@const plegado = estaPlegado(g.clave)}
                      <div class="snv-grupo">
                        <button class="snv-grupo-cab snv-tono-{g.tono}" type="button" aria-expanded={!plegado}
                                onclick={() => (plegadoManual = { ...plegadoManual, [g.clave]: !plegado })}>
                          <span class="snv-chevron" aria-hidden="true">{plegado ? '▸' : '▾'}</span>
                          {g.titulo} ({cuentaDeLaBandeja?.[g.clave] ?? g.filas.length})
                        </button>
                        {#if !plegado}
                          {#each g.filas as p (p.id)}{@render fila(p)}{/each}
                        {/if}
                      </div>
                    {/each}
                  {:else}
                    {#each pagina as p (p.id)}{@render fila(p)}{/each}
                  {/if}
                </div>

                <!-- PAGINACIÓN -->
                <div class="snoc-paginacion">
                  <span class="snv-nota">Mostrando {pag.desde} a {pag.hasta} de {pag.total}</span>
                  {#if pag.paginas > 1}
                    <div class="snoc-paginacion-botones">
                      <button class="snoc-pildora" type="button" onclick={() => (nPagina = pag.actual - 1)} disabled={pag.actual === 1}>Anterior</button>
                      {#each pag.ventana as n, i (i)}
                        {#if n === null}
                          <span class="snoc-paginacion-hueco" aria-hidden="true">…</span>
                        {:else}
                          <button class="snoc-pildora {n === pag.actual ? 'snoc-pildora-activa' : ''}" type="button"
                                  onclick={() => (nPagina = n)} aria-current={n === pag.actual ? 'page' : undefined}
                                  aria-label="Página {n}">{n}</button>
                        {/if}
                      {/each}
                      <button class="snoc-pildora" type="button" onclick={() => (nPagina = pag.actual + 1)} disabled={pag.actual === pag.paginas}>Siguiente</button>
                    </div>
                  {/if}
                </div>
              {/if}
            </section>

            <!-- ============ ACTIVIDAD ============ debajo de la bandeja, a todo el ancho -->
            <section class="snv-caja snv-actividad">
          <!--
            Actividad reciente del Supervisor
            De `common.Activity`, acotada a las entidades de este módulo. Un
            renglón sin usuario lo escribió la IA, y el backend lo marca con
            `es_ia`: no se deduce del texto.
          -->
          <div class="snoc-grafico">
            <h2 class="snoc-grafico-titulo">
              <span class="snoc-icono snoc-primario" style="font-size:15px;">history</span>
              Actividad reciente del Supervisor
              <!--
                SE DICE SI ESTA EN VIVO O NO, y no se asume. Un panel que se
                refresca solo es indistinguible de uno congelado hasta que algo
                cambia -- y si el sondeo se cae, quedaria mostrando datos viejos
                con cara de actuales. El punto verde afirma "esto se esta
                actualizando"; sin el, el rotulo dice la hora de lo ultimo que
                se pudo leer.
              -->
              {#if sondeoVivo}
                <span class="snoc-vivo" title="Se actualiza solo cada 10 segundos{ultimoSondeo ? ` · última lectura ${hora(ultimoSondeo.toISOString())}` : ''}">
                  <span class="snoc-vivo-punto"></span>En vivo
                </span>
              {:else}
                <span class="snoc-vivo snoc-vivo-frio" title="No se pudo leer la actividad en el último intento. Se muestra lo último que llegó.">
                  Sin actualizar
                </span>
              {/if}

              <!--
                EL FILTRO, y dice cuantos hay de cada cosa. Un selector que no
                dice cuanto deja afuera obliga a probarlo para saber si sirve.
              -->
              <span class="snoc-filtro-actividad">
                {#each GRUPOS_VISIBLES as g (g.clave)}
                  <button
                    type="button"
                    class="snoc-filtro-btn {grupo === g.clave ? 'snoc-filtro-btn-activo' : ''}"
                    onclick={() => elegirGrupo(g.clave)}>
                    {g.rotulo}
                    <!--
                      EL NUMERO ES DE TODO EL HISTORIAL, no de lo que se ve: lo
                      cuenta el backend. Un selector que no dice cuantos hay
                      obliga a apretarlo para saber si sirve, y con un panel que
                      se refresca solo eso significa no poder distinguir "no
                      hay" de "todavia no llego".
                    -->
                    {#if porGrupo[g.clave || 'todo'] !== undefined}
                      <span class="snoc-filtro-n">{porGrupo[g.clave || 'todo']}</span>
                    {/if}
                  </button>
                {/each}
              </span>
            </h2>
            {#if data.actividad.error}
              <div class="snoc-hueco">
                <span class="snoc-hueco-rotulo">Sin dato</span>
                <p class="snoc-hueco-motivo">{data.actividad.error.mensaje}</p>
              </div>
            {:else if actividad.disponible && grupo && actividadVisible.length === 0}
              <!--
                "El filtro no deja nada" NO es "no hay actividad": decir lo
                segundo cuando pasa lo primero manda a buscar el problema al
                lado equivocado.
              -->
              <div class="snoc-hueco">
                <span class="snoc-hueco-rotulo">Nada de este tipo todavía</span>
                <p class="snoc-hueco-motivo">
                  Hay actividad en el módulo, pero ninguna de
                  «{GRUPOS_VISIBLES.find((g) => g.clave === grupo)?.rotulo ?? grupo}».
                </p>
              </div>
            {:else if !actividad.disponible}
              <div class="snoc-hueco">
                <span class="snoc-hueco-rotulo">Sin actividad</span>
                <p class="snoc-hueco-motivo">
                  Todavía no hay hechos registrados en este módulo.
                </p>
              </div>
            {:else}
              <div class="snoc-tabla-caja snoc-desplazable">
                <table class="snoc-tabla">
                  <thead>
                    <tr><th>Hora</th><th>Evento</th><th>Detalle</th></tr>
                  </thead>
                  <tbody>
                    {#each actividadVisible as f (f.id)}
                      <tr>
                        <td class="snoc-mono-sm snoc-tenue" title={fecha(f.cuando)}>{cuando(f.cuando)}</td>
                        <td class="snoc-body-sm">
                          {f.evento}
                          {#if f.esIa}
                            <span class="snoc-insignia snoc-insignia-neutra" title="Lo escribió el Supervisor, no una persona">IA</span>
                          {/if}
                        </td>
                        <td class="snoc-body-sm snoc-recorte" title="{f.detalle} · {f.quien}">{f.detalle}</td>
                      </tr>
                    {/each}
                  </tbody>
                </table>

                <!--
                  VER MAS: trae hechos mas viejos y los SUMA abajo, sin tocar lo
                  de arriba. El cursor va por fecha y no por posicion: con el
                  ciclo auditando cada hora entran filas arriba todo el tiempo, y
                  un desplazamiento por numero repetiria lo que ya se mostro.
                -->
                {#if siguiente}
                  <button class="snoc-ver-mas" type="button"
                          onclick={verMas} disabled={cargandoMas}>
                    {cargandoMas ? 'Trayendo…' : 'Ver más atrás'}
                  </button>
                {:else if actividadVisible.length > 0}
                  <p class="snoc-fin-historial">No hay nada más atrás.</p>
                {/if}
              </div>
            {/if}
          </div>
            </section>
          </div>

          <!--
            ============ MIENTRAS TANTO ============
            Con el panel de detalle abierto se oculta: el detalle ocupa su
            lugar y la bandeja conserva su ancho.
          -->
          {#if !abierta}
            <aside class="snv-contexto" aria-label="Lo que pasa alrededor">
              <h2 class="snv-h3">Mientras tanto</h2>
          <div class="snoc-grafico" id="tecnicos">
            <div class="snoc-fila-sep">
              <h2 class="snoc-grafico-titulo">
                <span class="snoc-icono snoc-primario" style="font-size:15px;">engineering</span>
                Técnicos · carga operativa
              </h2>
              <a class="snoc-pildora" href="/supervisor-noc/programacion">Ver todos</a>
            </div>
            {#if capacidadViva?.error}
              <div class="snoc-hueco">
                <span class="snoc-hueco-rotulo">Sin dato</span>
                <p class="snoc-hueco-motivo">{capacidadViva.error.mensaje}</p>
              </div>
            {:else if !tecnicos.disponible}
              <div class="snoc-hueco">
                <span class="snoc-hueco-rotulo">Nadie con jornada</span>
                <p class="snoc-hueco-motivo">
                  Ninguna persona tiene jornada registrada para el {fechaCorta(data.dia)}.
                </p>
              </div>
            {:else}
              <div class="snoc-desplazable">
                {#each tecnicos.filas as t (t.id)}
                  <div class="snoc-tecnico">
                    <div class="snoc-tecnico-cabeza">
                      <span class="snoc-tecnico-nombre">{t.nombre}</span>
                      <span class="snoc-mono-sm {t.tono === 'critico' ? 'snoc-error-txt' : 'snoc-tenue'}">
                        {t.pct == null ? t.estado : `${t.pct}% · ${t.estado}`}
                      </span>
                    </div>
                    <div class="snoc-riel">
                      <div class="snoc-riel-relleno snoc-riel-{t.tono}" style="width:{t.ancho}%;"></div>
                    </div>
                    {#if t.faltantes > 0}
                      <span class="snoc-mono-sm snoc-tenue">
                        {t.faltantes} orden{t.faltantes === 1 ? '' : 'es'} sin duración: la carga real puede ser mayor
                      </span>
                    {/if}
                  </div>
                {/each}
              </div>
            {/if}
          </div>

          <!-- Órdenes de trabajo -->
          <div class="snoc-grafico" id="programacion">
            <div class="snoc-fila-sep">
              <h2 class="snoc-grafico-titulo">
                <span class="snoc-icono snoc-primario" style="font-size:15px;">assignment</span>
                Órdenes de trabajo
              </h2>
              <a class="snoc-pildora" href="/supervisor-noc/programacion">Ver programación</a>
            </div>
            {#if ordenes.disponible}
              <div class="snoc-desplazable">
                {#each ordenes.filas as f (f.clave)}
                  <div class="snoc-fila-orden">
                    <span>{f.texto}</span>
                    <span class="snoc-fila-orden-n {f.tono === 'alerta' ? 'snoc-error-txt' : ''}">{f.n}</span>
                  </div>
                {/each}
              </div>
            {:else}
              <div class="snoc-hueco">
                <span class="snoc-hueco-rotulo">Sin dato</span>
                <p class="snoc-hueco-motivo">Los indicadores de programación no llegaron en esta consulta.</p>
              </div>
            {/if}
          </div>

            </aside>
          {/if}
        </div>

        <!--
          ============ ANÁLISIS ============
          A un clic, no en la primera vista. Barras y no donas: una longitud se
          compara de un vistazo, un ángulo no.
        -->
        <details class="snv-analisis" open={form?.ok && form.tipo === 'asistente'}>
          <summary>
            <span class="snv-chevron" aria-hidden="true">▸</span>
            <span class="snv-h2">Análisis</span>
            <span class="snv-nota">De qué se trata lo pendiente y de dónde viene</span>
          </summary>

          <div class="snv-analisis-rejilla">
            <section>
              <h3 class="snv-h4">
                {filtroEstado === 'pendientes' ? 'Pendientes' : filtroEstado === 'decididas' ? 'Ya decididas' : 'Todas'} por tipo
              </h3>
              {#if donut.disponible}
                {@const max = Math.max(...donut.tramos.map((/** @type {any} */ t) => t.n), 1)}
                {#each donut.tramos as t (t.clave)}
                  <div class="snv-barra-h" title="{t.etiqueta}: {t.n}">
                    <span>{t.etiqueta}</span><span class="snv-barra-n">{t.n}</span>
                    <span class="snv-riel"><i style="width:{(t.n / max) * 100}%"></i></span>
                  </div>
                {/each}
              {:else}
                <p class="snv-nota">
                  {data.hallazgos.error
                    ? data.hallazgos.error.mensaje
                    : propuestas.length > 0
                      ? 'Ninguna propuesta cae en la bandeja elegida.'
                      : 'Sin propuestas todavía.'}
                </p>
              {/if}
            </section>

            <section>
              <h3 class="snv-h4">Casos técnicos por estado</h3>
              {#if barras.disponible}
                {@const max = Math.max(...barras.barras.map((/** @type {any} */ b) => b.n), 1)}
                {#each barras.barras as b (b.estado)}
                  <div class="snv-barra-h" title="{b.estado}: {b.n}">
                    <span>{b.estado}</span><span class="snv-barra-n">{b.n}</span>
                    <span class="snv-riel"><i style="width:{(b.n / max) * 100}%"></i></span>
                  </div>
                {/each}
              {:else}
                <p class="snv-nota">{esperandoIndicadores ? 'Leyendo…' : 'El reparto de casos por estado no llegó en esta consulta.'}</p>
              {/if}
            </section>

            <section>
              <!-- De `casos.por_origen`: 'wisphub' o 'dexter', las dos categorías
                   que el campo distingue; no se derivan otras. -->
              <h3 class="snv-h4">Casos por origen</h3>
              {#if origen.disponible}
                <div class="snv-reparto" role="img" aria-label="Reparto de los {origen.total} casos por sistema de origen">
                  {#each origen.tramos as t (t.clave)}
                    <i style="width:{t.pct}%; background:{t.color};"></i>
                  {/each}
                </div>
                {#each origen.tramos as t (t.clave)}
                  <div class="snv-reparto-fila">
                    <span class="snv-cuadro" style="background:{t.color};"></span>
                    <span>{t.etiqueta}</span>
                    <b>{t.n} · {t.pct} %</b>
                  </div>
                {/each}
              {:else}
                <p class="snv-nota">{esperandoIndicadores ? 'Leyendo…' : 'Ningún caso trae sistema de origen en esta consulta.'}</p>
              {/if}
            </section>
          </div>

          <!-- El mapa no se dibuja vacío: queda dicho en una línea. -->
          <p class="snv-nota">{SIN_DATO.mapa.titulo}: {SIN_DATO.mapa.motivo}</p>

        <!-- ============ ASISTENTES OPERATIVOS ============ -->
        <div class="snoc-panel snv-asistentes" style="gap:var(--snoc-sm);">
          <div class="snoc-fila-sep">
            <div class="snoc-fila">
              <div class="snoc-chip-icono snoc-chip-icono-solido">
                <span class="snoc-icono" style="font-size:18px;">smart_toy</span>
              </div>
              <div class="snoc-pila-xs">
                <h3 class="snoc-h4">Asistentes operativos</h3>
                <span class="snoc-body-sm snoc-secundario">Analizan su dominio y proponen</span>
              </div>
            </div>
          </div>

          <div class="snoc-pila-xs">
            {#each [{ id: 'programacion', rotulo: 'Programación', desc: 'Órdenes sin programar, planes sin publicar, riesgo de plazo' }, { id: 'compromiso', rotulo: 'Compromisos', desc: 'Compromisos por vencer y dependencias pendientes' }] as a (a.id)}
              <form method="POST" action="?/asistente" use:enhance={alCorrerAsistente(a.id)}>
                <input type="hidden" name="dominio" value={a.id} />
                <div class="snoc-caja-asistente">
                  <div class="snoc-fila-sep">
                    <span class="snoc-label">{a.rotulo}</span>
                    <button class="snoc-btn snoc-btn-primario" type="submit" disabled={asistenteCorriendo !== null}>
                      <span class="snoc-icono" style="font-size:14px;">play_arrow</span>
                      {asistenteCorriendo === a.id ? 'Analizando…' : 'Analizar'}
                    </button>
                  </div>
                  <p class="snoc-body-sm snoc-secundario" style="margin:var(--snoc-xs) 0 0;">{a.desc}</p>
                </div>
              </form>
            {/each}
          </div>

          {#if form?.ok && form.tipo === 'asistente'}
            <div class="snoc-resultado">
              <span class="snoc-label-sm" style="text-transform:uppercase;">Resultado · {form.dominio}</span>
              {#each form.asistente?.recomendaciones ?? [] as r, i (i)}
                <div class="snoc-resultado-fila">
                  <span class="snoc-body-sm">{r.recomendacion ?? r.accion_propuesta ?? r.tipo_senal}</span>
                  <span class="snoc-mono-sm snoc-tenue">{r.resultado ?? ''}</span>
                </div>
              {:else}
                <span class="snoc-body-sm snoc-secundario">El asistente no encontró señales de su dominio.</span>
              {/each}
            </div>
          {/if}

          <div class="snoc-fila" style="gap:var(--snoc-xs); padding-top:var(--snoc-xs);">
            <span class="snoc-icono snoc-primario" style="font-size:13px;">gavel</span>
            <span class="snoc-mono-sm snoc-tenue">
              Los asistentes solo leen y proponen. No programan, no asignan y no llaman a ningún sistema externo.
            </span>
          </div>
        </div>
        </details>
      {/if}
    </div>
  </div>

  <!--
    ============ PANEL DE DETALLE ============
    01/11/2026: era un modal centrado de 85vw; el diseño aprobado lo vuelve
    panel lateral para decidir sin perder la bandeja de vista. Lo de adentro
    son las MISMAS derivaciones de siempre ($lib/v2/supervisor-noc-detalle.js),
    ordenadas como se lee una decisión: de quién se trata, qué pasa, con qué
    evidencia, qué propone, y qué pasa --y qué NO pasa-- si se acepta.
  -->
  {#if abierta}
    <div
      class="snv-velo-detalle"
      role="presentation"
      onclick={(e) => {
        if (e.target === e.currentTarget) cerrarDetalle();
      }}
    >
      <div class="snv-detalle" role="dialog" aria-modal="false" aria-labelledby="snv-detalle-titulo">
        <div class="snv-det-cab">
          <h2 class="snv-h3" id="snv-detalle-titulo">Detalle de la propuesta</h2>
          <button class="snv-cerrar" type="button" onclick={cerrarDetalle} aria-label="Cerrar el detalle">×</button>
        </div>
        {#if posicion.total > 1}
          <div class="snv-det-nav">
            <button class="snv-enlace-nav" type="button" onclick={() => irA(-1)}
                    disabled={posicion.indice <= 0 || cargandoDetalle}>‹ Anterior</button>
            <span>{posicion.indice + 1} de {posicion.total}</span>
            <button class="snv-enlace-nav" type="button" onclick={() => irA(1)}
                    disabled={posicion.indice >= posicion.total - 1 || cargandoDetalle}>Siguiente ›</button>
          </div>
        {/if}

        <div class="snv-det-cuerpo">
          {#if cargandoDetalle}
            <p class="snv-nota">Consultando la propuesta…</p>
          {:else if errorDetalle}
            <div class="snoc-aviso">
              <span class="snoc-icono snoc-error-txt" style="font-size:18px;" aria-hidden="true">error</span>
              <span class="snoc-body">{errorDetalle}</span>
            </div>
          {:else if detalle}
            {@const plazoFila = textoDePlazo(contextoFila?.sla_estado, contextoFila?.sla_minutos)}
            {@const efectos = efectosDeAceptar(aceptar)}
            <!-- DE QUIÉN SE TRATA -->
            <div class="snv-det-ficha">
              <span class="snv-det-icono snv-tono-{plazoFila.tono}" aria-hidden="true">!</span>
              <div class="snv-det-quien">
                <strong>Cliente: {contextoFila?.cliente ?? 'no disponible en la fuente'}</strong>
                <span class="snv-det-titulo">{titulo}</span>
                <span class="snv-ids">
                  {#if contextoFila?.orden_numero != null}OT-{contextoFila.orden_numero}{:else if contextoFila?.caso_id}<a href="/tickets/{contextoFila.caso_id}">Caso {String(contextoFila.caso_id).slice(0, 8)}</a>{:else}{String(detalle.origen_id).slice(0, 8)}{/if}{#if contextoFila?.ticket_externo}{' · '}{contextoFila.ticket_externo}{/if}
                </span>
              </div>
              <span class="snv-det-plazo snv-tono-{plazoFila.tono}">{plazoFila.texto}</span>
            </div>
            <p class="snv-det-meta">
              {detalle.tipo_senal_display} · Prioridad {detalle.prioridad}{#if basePrioridad}{' '}({basePrioridad}){/if}
              · Detectado {haceCuanto(detalle.created_at)} · Expira {expiraEn(detalle.expira_en)}
              · {estadoDe(detalle.estado).texto}
            </p>

            <section class="snv-det-sec">
              <h3>Qué está pasando</h3>
              <p>{resumen}</p>
              {#if contraste}
                <p class="snv-det-contraste">
                  En Dexter: <strong>{contraste.crm}</strong> · En WispHub: <strong>{contraste.proveedor}</strong>
                </p>
              {/if}
            </section>

            <section class="snv-det-sec">
              <h3>Evidencia</h3>
              <!-- SOLO SI HAY DOS FUENTES QUE COMPARAR: una tabla con un lado
                   vacío se lee como si algo hubiera fallado. -->
              {#if comparacionAporta(comparacion)}
                <table class="snv-evidencia">
                  <thead><tr><th>Campo</th><th>Dexter</th><th>WispHub</th></tr></thead>
                  <tbody>
                    {#each comparables as f (f.campo)}
                      {@const distinta = celdaDistinta(f)}
                      <tr>
                        <th scope="row">{f.campo}</th>
                        <td class:snv-distinta={distinta} class:snoc-sin-fuente={f.dexter === AUSENTE}>{f.dexter}</td>
                        <td class:snoc-sin-fuente={f.wisphub === AUSENTE}>{f.wisphub}</td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              {/if}
              <!-- Los hechos con su fuente: lo que el Supervisor vio, separado
                   de lo que interpreta. -->
              {#if analisis.hechos.length}
                <ul class="snv-hechos">
                  {#each analisis.hechos as h, i (i)}
                    <li>{h.dato}<span class="snv-nota"> · {h.fuente}</span></li>
                  {/each}
                </ul>
              {:else if !comparacionAporta(comparacion)}
                <p class="snv-nota">{AUSENTE}</p>
              {/if}
              {#if analisis.impacto !== AUSENTE}
                <p><strong>Impacto:</strong> {analisis.impacto}</p>
              {/if}
              {#if analisis.faltantes.length}
                <p class="snv-nota">Falta para estar seguro: {analisis.faltantes.join(' · ')}</p>
              {/if}
            </section>

            <section class="snv-det-sec">
              <h3>Propuesta del Supervisor</h3>
              <p>{detalle.accion_propuesta || 'Lo detectó, pero no trae una acción para recomendar.'}</p>
            </section>

            <section class="snv-det-acepto">
              <h3>Si aceptás</h3>
              <p class="snv-det-sub">Qué va a pasar</p>
              <ul class="snv-lista-si">
                {#each efectos.si as e, i (i)}<li>{e}</li>{/each}
              </ul>
              <p class="snv-det-sub">Qué NO va a pasar</p>
              <ul class="snv-lista-no">
                {#each efectos.no as e, i (i)}<li>{e}</li>{/each}
              </ul>
              {#if aceptar.avisoLectura}
                <!-- 19/10/2026: aceptar pasa a Despacho aunque la lectura diga
                     que no hace falta ir. Se dice acá, junto a la decisión. -->
                <p class="snoc-aviso">
                  <span class="snoc-icono" style="font-size:16px;" aria-hidden="true">warning</span>
                  {aceptar.avisoLectura}
                </p>
              {/if}
            </section>

            <!-- INFORMACIÓN TÉCNICA: todo lo que estaba, a un clic. -->
            <details class="snv-det-tecnica">
              <summary>Información técnica</summary>
            <details class="snoc-detalle-tecnico">
              <summary class="snoc-label-sm">Información técnica de la señal</summary>
            <!-- DOS COLUMNAS: identificación y contexto -->
            <div class="snoc-dos-columnas">
              <section class="snoc-columna">
                <div class="snoc-columna-titulo">
                  <span class="snoc-icono snoc-primario" style="font-size:16px;">fingerprint</span>
                  <span class="snoc-label" style="text-transform:uppercase; letter-spacing:0.06em;">
                    Identificación de la señal
                  </span>
                </div>
                <dl class="snoc-lista-datos">
                  <!-- La clave técnica ya está en «Información técnica», más abajo. -->
                  <div><dt>Detectado</dt><dd class="snoc-mono-sm">{fecha(detalle.created_at)}</dd></div>
                  <div><dt>Fecha de expiración</dt><dd class="snoc-mono-sm">{fecha(detalle.expira_en)}</dd></div>
                  <div><dt>Tipo de origen</dt><dd>{detalle.origen_tipo}</dd></div>
                  <div><dt>Organización</dt><dd>{data.org ?? '—'}</dd></div>
                  <div>
                    <dt>Alcance de la etapa</dt>
                    <dd>{detalle.dentro_del_alcance === false ? 'Fuera del alcance vigente' : 'Dentro del alcance'}</dd>
                  </div>
                </dl>
              </section>

              <section class="snoc-columna">
                <div class="snoc-columna-titulo">
                  <span class="snoc-icono snoc-primario" style="font-size:16px;">dvr</span>
                  <span class="snoc-label" style="text-transform:uppercase; letter-spacing:0.06em;">
                    Contexto operativo
                  </span>
                </div>
                <dl class="snoc-lista-datos">
                  {#if antiguedad}
                    <div>
                      <dt>Antigüedad del caso</dt>
                      <dd>
                        {antiguedad.dias != null ? `${antiguedad.dias} días` : '—'}
                        <span class="snoc-mono-sm snoc-tenue">· desde {antiguedad.desde}</span>
                      </dd>
                    </div>
                  {/if}
                  <div>
                    <dt>Caso / orden relacionada</dt>
                    <dd>
                      <span class="snoc-mono-sm">{String(detalle.origen_id).slice(0, 8)}</span>
                      {#if detalle.origen_tipo === 'case'}
                        <a class="snoc-enlace-externo" href="/tickets/{detalle.origen_id}">
                          Ver en el CRM <span class="snoc-icono" style="font-size:13px;">open_in_new</span>
                        </a>
                      {/if}
                    </dd>
                  </div>
                  <div>
                    <dt>Responsable sugerido</dt>
                    <dd>
                      {detalle.responsable_sugerido_email ?? 'Ninguno'}
                      <span class="snoc-mono-sm snoc-tenue">· sugerido, no asignado</span>
                    </dd>
                  </div>
                  {#if detalle.impacto}
                    <div><dt>Afectación operativa</dt><dd>{detalle.impacto}</dd></div>
                  {/if}
                  {#if lectura}
                    <div><dt>Última verificación externa</dt><dd class="snoc-mono-sm">{lectura}</dd></div>
                  {/if}
                  {#if detalle.conocimiento_version}
                    <div><dt>Versión de conocimiento</dt><dd class="snoc-mono-sm">{detalle.conocimiento_version}</dd></div>
                  {/if}
                </dl>
                <div class="snoc-ausente">
                  <span class="snoc-icono snoc-tenue" style="font-size:14px;">info</span>
                  <span class="snoc-mono-sm snoc-tenue">
                    No llegan en esta respuesta: {CONTEXTO_AUSENTE.join(' · ')}.
                  </span>
                </div>
              </section>
            </div>
            </details>
            <!-- ============ EL REGISTRO DE AUDITORIA ============
                 Para que esta: si manana hay que revisar por que se mando una
                 cuadrilla a una casa, esta tabla dice que sabia el sistema, de
                 donde lo saco y cuando. Es lo unico que lo dice.

                 ESTABA DOS VECES: un desplegable adentro de otro, los dos con
                 el mismo titulo. Para abrirlo habia que hacer dos clics en la
                 misma frase. -->
            <details class="snoc-detalles">
              <summary class="snoc-label-sm">
                Ver análisis técnico completo ({(detalle.evidencia ?? []).length} observaciones registradas)
              </summary>
              <div style="padding-top:var(--snoc-sm);">
                {#if Array.isArray(detalle.evidencia) && detalle.evidencia.length}
                  <div class="snoc-tabla-caja">
                    <table class="snoc-tabla">
                      <thead>
                        <!-- SIN «Referencia»: era el id del caso, el MISMO en
                             las ocho filas, ocupando un tercio del ancho. El
                             id ya esta abajo, en «Información técnica». -->
                        <tr><th>Fuente</th><th>Observación</th><th>Leído</th></tr>
                      </thead>
                      <tbody>
                        {#each detalle.evidencia as e, i (i)}
                          <tr>
                            <td class="snoc-mono-sm">{e.fuente ?? '—'}</td>
                            <td class="snoc-body-sm">{e.dato}</td>
                            <td class="snoc-mono-sm snoc-tenue">{fecha(e.observado_en)}</td>
                          </tr>
                        {/each}
                      </tbody>
                    </table>
                  </div>
                {:else}
                  <span class="snoc-body snoc-secundario">Sin observaciones registradas.</span>
                {/if}
              </div>
            </details>
            <!-- INFORMACIÓN TÉCNICA -->
            <details class="snoc-detalles">
              <summary class="snoc-label-sm">Información técnica</summary>
              <div class="snoc-meta" style="margin-top:var(--snoc-sm);">
                <div style="grid-column:1 / -1;">
                  <span>ID de propuesta:</span><span class="snoc-mono-sm snoc-copiable">{detalle.id}</span>
                </div>
                <div style="grid-column:1 / -1;">
                  <span>ID de origen:</span><span class="snoc-mono-sm snoc-copiable">{detalle.origen_id}</span>
                </div>
                <div><span>Clave técnica:</span><span class="snoc-mono-sm">{detalle.tipo_senal}</span></div>
                <div><span>Actualizada:</span><span class="snoc-mono-sm">{fecha(detalle.updated_at)}</span></div>
              </div>
              <!-- Un objeto VACIO tambien es "truthy": se pintaba un «{}»
                   suelto debajo de los ids, que no es un dato, es basura. -->
              {#if detalle.propuesta_original
                   && Object.keys(detalle.propuesta_original).length > 0}
                <pre class="snoc-pre">{JSON.stringify(detalle.propuesta_original, null, 2)}</pre>
              {/if}
            </details>

            <!--
              EL CICLO, SOLO DONDE ES UN CICLO. Para todo lo que no ejecuta
              nada al aceptar, este bloque pintaba seis etapas y después
              aclaraba que tres «no existen para este tipo de señal». Un
              diagrama que necesita desmentirse a sí mismo no está informando;
              lo que sí hace falta saber --que aceptar registra un acuerdo y
              nada más-- ya lo dice «Si aceptas esta propuesta», justo arriba.
            -->
            {#if aceptar.ejecuta}
            <section class="snoc-ciclo">
              <div class="snoc-fila-sep" style="flex-wrap:wrap;">
                <span class="snoc-label" style="text-transform:uppercase; letter-spacing:0.06em;">
                  Ciclo de ejecución
                </span>
                <span class="snoc-mono-sm snoc-tenue">
                  {aceptar.ejecuta ? 'Revisión humana ➔ Cierre' : 'Revisión humana ➔ Ejecución'}
                </span>
              </div>
              <ol class="snoc-pasos">
                {#each pasosDelCiclo(detalle.estado, detalle.tipo_senal) as p (p.clave)}
                  <li class="snoc-paso {p.estado}">
                    <span class="snoc-paso-punto"></span>
                    <span class="snoc-paso-texto">{p.texto}</span>
                  </li>
                {/each}
              </ol>
              <span class="snoc-mono-sm snoc-tenue">
                {#if aceptar.ejecuta}
                  El cierre se intenta <strong>de inmediato al aceptar</strong>, dentro de la misma petición: no
                  queda encolado. Antes de ejecutarlo el sistema revalida las condiciones, así que
                  «Aprobada» no implica «Cerrada».
                {:else}
                  Las tres últimas etapas <strong>no existen para este tipo de señal</strong>: aceptar registra el
                  acuerdo y nada más. Se muestran para que se vea dónde termina lo que esta pantalla puede hacer.
                {/if}
              </span>
            </section>
            {/if}

            {#if Array.isArray(detalle.historial) && detalle.historial.length}
              <details class="snoc-detalles">
                <summary class="snoc-label-sm">Trazabilidad ({detalle.historial.length})</summary>
                <div class="snoc-pila-xs" style="padding-top:var(--snoc-sm);">
                  {#each detalle.historial as h, i (i)}
                    <div class="snoc-historial">
                      <span class="snoc-body-sm"><strong>{h.accion}</strong> · {h.descripcion}</span>
                      <span class="snoc-mono-sm snoc-tenue">
                        {h.quien === 'Supervisor NOC IA'
                          ? 'Generado por Supervisor NOC IA'
                          : `Ejecutado por usuario: ${h.quien}`} · {fecha(h.cuando)}
                      </span>
                    </div>
                  {/each}
                </div>
              </details>
            {/if}
            </details>
          {/if}
        </div>

        <!-- EL PIE NO SE DESPLAZA: la decisión tiene que estar siempre a mano. -->
        {#if detalle && !cargandoDetalle && !errorDetalle}
          <div class="snv-det-pie">
            {#if detalle.estado === 'propuesta'}
              <label class="snv-det-coment">
                <span>Comentario <span class="snv-nota">(opcional; para rechazar o cancelar conviene decir por qué)</span></span>
                <textarea bind:value={comentario} placeholder="Agregá un comentario…" rows="2"></textarea>
              </label>
              <!--
                Los tres botones se deshabilitan mientras una decision esta en
                curso: las tres actuan sobre la MISMA propuesta. El rotulo de
                espera lo pone 'alDecidir' al ENVIAR, leyendo 'data-espera'; un
                'onclick' deshabilitaria el boton antes de que el formulario salga.
              -->
              <div class="snv-det-botones">
                <form method="POST" action="?/cancelar" use:enhance={alDecidir} style="display:contents;">
                  <input type="hidden" name="id" value={detalle.id} />
                  <input type="hidden" name="motivo" value={comentario} />
                  <button class="snv-enlace snv-det-cancelar" type="submit" disabled={!!decidiendo} data-espera="Cancelando…">
                    {decidiendo === 'Cancelando…' ? 'Cancelando…' : 'Cancelar la propuesta'}
                  </button>
                </form>
                <form method="POST" action="?/revisar" use:enhance={alDecidir} style="display:contents;">
                  <input type="hidden" name="id" value={detalle.id} />
                  <input type="hidden" name="comentario" value={comentario} />
                  <button class="snv-btn snv-btn-sec" name="decision" value="rechazada" type="submit"
                          disabled={!!decidiendo} data-espera="Rechazando…">
                    {decidiendo === 'Rechazando…' ? 'Rechazando…' : 'Rechazar'}
                  </button>
                  <!-- El rótulo dice A DÓNDE VA («Aceptar y pasar a Despacho») y,
                       mientras viaja, lo que de verdad pasa («Cerrando el caso…»).
                       Sale de 'siAcepto', con lo que dice el backend. -->
                  <button class="snv-btn snv-btn-pri" name="decision" value="aceptada" type="submit"
                          disabled={!!decidiendo} data-espera={aceptar.espera}>
                    <span aria-hidden="true">✓</span>
                    {decidiendo && decidiendo === aceptar.espera ? decidiendo : aceptar.rotuloBoton}
                  </button>
                </form>
              </div>
            {:else}
              <div class="snv-det-botones">
                <span class="snv-nota">Ya revisada: <strong>{estadoDe(detalle.estado).texto}</strong></span>
                <button class="snv-btn snv-btn-sec" type="button" onclick={cerrarDetalle}>Cerrar</button>
              </div>
            {/if}
          </div>
        {/if}
      </div>
    </div>
  {/if}

  <!-- ============ MODAL DEL CICLO ============ -->
  <!-- ============ LO QUE EL CICLO CERRO SOLO ============
       Aparece una vez, al terminar el ciclo, y con los casos NOMBRADOS.
       El objetivo es que se puedan abrir y comprobar, no que se confie en
       un numero. -->
  {#if cerradosDelCiclo.length}
    <div
      class="snoc-velo"
      role="presentation"
      onclick={(e) => {
        if (e.target === e.currentTarget) cerradosDelCiclo = [];
      }}
    >
      <div class="snoc-modal" role="dialog" aria-modal="true" aria-labelledby="snoc-cerrados-titulo">
        <div class="snoc-fila snoc-primario">
          <span class="snoc-icono" style="font-size:28px;">task_alt</span>
          <h4 class="snoc-h3" id="snoc-cerrados-titulo">
            El Supervisor cerró {cerradosDelCiclo.length}
            {cerradosDelCiclo.length === 1 ? 'caso' : 'casos'}
          </h4>
        </div>
        <p class="snoc-body-sm snoc-secundario" style="margin:0;">
          Los cerró sin intervención humana porque el diagnóstico del equipo lo habilitó. Abrilos y confirmá
          que el motivo es correcto — si alguno está mal, se puede reabrir.
        </p>
        <div class="snoc-pila-xs">
          {#each cerradosDelCiclo as c (c.caso_id)}
            <div class="snoc-caja-datos" style="display:flex; flex-direction:column; gap:var(--snoc-xs);">
              <a class="snoc-enlace-externo" href="/tickets/{c.caso_id}">
                Caso CS-{String(c.caso_id).slice(0, 8)}
                <span class="snoc-icono" style="font-size:13px;">open_in_new</span>
              </a>
              <span class="snoc-body-sm">{c.porque || 'Sin motivo registrado.'}</span>
            </div>
          {/each}
        </div>
        <div class="snoc-fila" style="justify-content:flex-end; padding-top:var(--snoc-xs);">
          <button class="snoc-btn" type="button" onclick={() => (cerradosDelCiclo = [])}>Entendido</button>
        </div>
      </div>
    </div>
  {/if}

  <!-- ============ EL ALCANCE DEL SUPERVISOR ============
       Dos controles que NO son lo mismo, y la pantalla los separa:
       el NIVEL dice qué clase de cosas puede hacer solo, y el INTERRUPTOR
       es el freno de mano. Tirar el freno no baja el nivel. -->
  {#if modalAlcance}
    <div
      class="snoc-velo"
      role="presentation"
      onclick={(e) => {
        if (e.target === e.currentTarget) modalAlcance = false;
      }}
    >
      <div class="snoc-modal" role="dialog" aria-modal="true" aria-labelledby="snoc-alcance-titulo">
        <div class="snoc-fila snoc-primario">
          <span class="snoc-icono" style="font-size:28px;">tune</span>
          <h4 class="snoc-h3" id="snoc-alcance-titulo">Alcance del Supervisor NOC IA</h4>
        </div>

        {#if alcanceCargando}
          <p class="snoc-body snoc-secundario" style="margin:0;">Leyendo el estado…</p>
        {:else if alcance}
          <!-- QUÉ PUEDE HACER HOY, antes de ofrecer cambiarlo -->
          <div class="snoc-mono-sm snoc-caja-datos">
            <div>• Nivel autorizado: <strong>{alcance.configurado}</strong></div>
            <div>
              • Nivel que de verdad aplica: <strong>{alcance.efectivo}</strong>
              {#if alcance.recortado}<span class="snoc-error-txt"> (recortado)</span>{/if}
            </div>
            <div>
              • Interruptor:
              {#if alcance.interruptor_permite}
                <strong>permite actuar</strong>
              {:else}
                <strong class="snoc-error-txt">NO permite actuar</strong>
              {/if}
            </div>
            {#if alcance.motivo}
              <div class="snoc-tenue">• {alcance.motivo}</div>
            {/if}
            <!-- LA OTRA MITAD DEL ESTADO, y faltaba (21/10/2026). El nivel
                 dice CUANTO puede hacer; esto, QUE le pidieron que haga. Las
                 dos hacen falta: una tarea delegada con el nivel en 1 no
                 cierra nada, y el nivel en 3 sin tareas delegadas tampoco
                 hace nada. El detalle va al final del modal para no empujar
                 el freno de mano hacia abajo. -->
            {#if alcance.delegaciones}
              <div>
                • Tareas delegadas:
                <strong>{alcance.delegaciones.filter((/** @type {any} */ d) => d.delegada).length}</strong>
                de {alcance.delegaciones.length}
              </div>
            {/if}
          </div>

          <!-- EL FRENO VA PRIMERO, y es a propósito: si alguien abre esta
               pantalla con apuro es para parar, no para ampliar. -->
          <section class="snoc-columna" style="gap:var(--snoc-xs);">
            <span class="snoc-label-sm" style="text-transform:uppercase;">Freno de mano</span>
            <p class="snoc-body-sm snoc-secundario" style="margin:0;">
              Detiene <strong>todas</strong> las acciones automáticas de inmediato. No cambia el nivel: cuando
              lo reactivés, el alcance vuelve a ser el que era.
            </p>
            <input
              class="snoc-campo"
              type="text"
              bind:value={motivoFreno}
              placeholder="Motivo (obligatorio) — ej: algo raro en la bandeja"
              disabled={alcanceGuardando}
            />
            <div class="snoc-fila" style="gap:var(--snoc-xs);">
              {#if alcance.interruptor_permite}
                <button
                  class="snoc-btn snoc-btn-error"
                  type="button"
                  disabled={alcanceGuardando || !motivoFreno.trim()}
                  onclick={() => moverFreno(true)}
                >
                  Detener las acciones automáticas
                </button>
              {:else}
                <button
                  class="snoc-btn"
                  type="button"
                  disabled={alcanceGuardando || !motivoFreno.trim()}
                  onclick={() => moverFreno(false)}
                >
                  Reactivar
                </button>
              {/if}
            </div>
          </section>

          <!-- EL NIVEL: ampliar exige demostrar que se midió algo -->
          <section class="snoc-columna" style="gap:var(--snoc-xs);">
            <span class="snoc-label-sm" style="text-transform:uppercase;">Qué puede hacer sin preguntar</span>
            <select class="snoc-select" bind:value={nivelElegido} disabled={alcanceGuardando}>
              {#each alcance.niveles as n (n.nivel)}
                <option value={n.nivel}>{n.etiqueta}</option>
              {/each}
            </select>
            <input
              class="snoc-campo"
              type="text"
              bind:value={motivoAlcance}
              placeholder="Motivo del cambio (obligatorio)"
              disabled={alcanceGuardando}
            />
            <input
              class="snoc-campo"
              type="text"
              bind:value={criteriosAlcance}
              placeholder="Qué mediste para decidirlo (obligatorio)"
              disabled={alcanceGuardando}
            />
            <p class="snoc-body-sm snoc-tenue" style="margin:0;">
              Los criterios no son burocracia: sin saber qué se midió, esta decisión se vuelve a discutir cada
              vez que alguien la mire.
            </p>
            <div class="snoc-fila" style="justify-content:flex-end;">
              <button
                class="snoc-btn snoc-btn-primario"
                type="button"
                disabled={alcanceGuardando || nivelElegido === alcance.configurado}
                onclick={guardarNivel}
              >
                {alcanceGuardando ? 'Guardando…' : 'Cambiar el nivel'}
              </button>
            </div>
          </section>
          <!-- QUÉ LE PIDIERON QUE HAGA  --  21/10/2026
               Hasta hoy esto no se veía en ninguna pantalla: se delegaba
               hablándole al Supervisor en el chat, y para saber si había
               quedado encendido había que volver a preguntarle.
               SOLO LECTURA acá. Desde el 27/10/2026 se delega y se quita
               también en «Ajustes del Supervisor», que escribe por las mismas
               funciones que el chat (`td.delegar` / `td.quitar`): dos caras,
               una sola regla. -->
          <section class="snoc-columna" style="gap:var(--snoc-xs);">
            <span class="snoc-label-sm" style="text-transform:uppercase;">Qué le pidieron que haga</span>
            {#each alcance.delegaciones ?? [] as d (d.clave)}
              <div class="snoc-caja-datos snoc-columna" style="gap:2px;">
                <div class="snoc-fila" style="gap:var(--snoc-xs); align-items:baseline;">
                  <!-- TRES ESTADOS Y NO DOS. "Delegada" y "delegada y
                       funcionando" no son lo mismo: el 15/10 una tarea estuvo
                       delegada, con el nivel en 3, y nada la corrió en cinco
                       vueltas porque faltaba el ciclo horario. Un punto verde
                       ahí habría mentido. -->
                  <span
                    class="snoc-punto {!d.delegada
                      ? 'snoc-punto-tenue'
                      : d.nivel_alcanza && d.la_despierta_algo?.si
                        ? 'snoc-punto-secundario'
                        : 'snoc-punto-error'}"
                  ></span>
                  <strong class="snoc-body-sm">{d.nombre}</strong>
                </div>
                {#if !d.delegada}
                  <div class="snoc-body-sm snoc-tenue">
                    No delegada. Se enciende en <a href="/supervisor-noc/ajustes">Ajustes</a>, o
                    pidiéndosela al Supervisor en el chat.
                  </div>
                {:else}
                  <div class="snoc-body-sm snoc-secundario">
                    Delegada el {fecha(d.delegada_en)}
                  </div>
                  {#if d.con_estas_palabras}
                    <!-- LA FRASE TAL CUAL, que es el único registro de qué
                         creía estar pidiendo quien la delegó. Si la tarea hace
                         algo distinto de lo que esa frase dice, el problema es
                         del catálogo y conviene poder verlo. -->
                    <div class="snoc-body-sm snoc-tenue">«{d.con_estas_palabras}»</div>
                  {/if}
                  {#if !d.nivel_alcanza}
                    <div class="snoc-body-sm snoc-error-txt">
                      No va a actuar: necesita nivel {d.exige_nivel} y el que aplica hoy es
                      {alcance.efectivo}.
                    </div>
                  {/if}
                  {#if d.la_despierta_algo && !d.la_despierta_algo.si}
                    <div class="snoc-body-sm snoc-error-txt">{d.la_despierta_algo.por_que}</div>
                  {/if}
                {/if}
                <div class="snoc-body-sm snoc-tenue">{d.que_hace}</div>
              </div>
            {/each}
            {#if !(alcance.delegaciones ?? []).length}
              <p class="snoc-body-sm snoc-tenue" style="margin:0;">
                El backend no devolvió el catálogo de tareas.
              </p>
            {/if}
          </section>
        {/if}

        {#if alcanceError}
          <p class="snoc-body-sm snoc-error-txt" style="margin:0;">{alcanceError}</p>
        {/if}

        <div class="snoc-fila" style="justify-content:flex-end; padding-top:var(--snoc-xs);">
          <button class="snoc-btn" type="button" onclick={() => (modalAlcance = false)}>Cerrar</button>
        </div>
      </div>
    </div>
  {/if}

  {#if modalCiclo}
    <div
      class="snoc-velo"
      role="presentation"
      onclick={(e) => {
        if (e.target === e.currentTarget) modalCiclo = false;
      }}
    >
      <div class="snoc-modal" role="dialog" aria-modal="true" aria-labelledby="snoc-modal-titulo">
        <div class="snoc-fila snoc-primario">
          <span class="snoc-icono" style="font-size:28px;">lock_clock</span>
          <h4 class="snoc-h3" id="snoc-modal-titulo">Ejecutar ciclo de observación</h4>
        </div>
        <p class="snoc-body snoc-secundario" style="margin:0;">
          El Supervisor analizará nuevamente la operación y podrá generar nuevas propuestas. Además
          <strong style="color:var(--snoc-on-surface);">ejecuta las tareas que tenga delegadas</strong>
          (ver «Qué hace el Supervisor solo»); todo lo demás queda para que lo decida una persona.
        </p>
        <div class="snoc-mono-sm snoc-caja-datos">
          <div>• Escribe propuestas y su auditoría, y lo que hagan sus tareas delegadas</div>
          <div>• Un ciclo a la vez por organización</div>
          <div>• Todo o nada: si falla a la mitad, no quedan propuestas parciales</div>
        </div>
        <form method="POST" action="?/ciclo" use:enhance={alCorrerCiclo}>
          <div class="snoc-fila" style="justify-content:flex-end; padding-top:var(--snoc-xs);">
            <button class="snoc-btn" type="button" onclick={() => (modalCiclo = false)} disabled={corriendo}>
              Cancelar
            </button>
            <button class="snoc-btn snoc-btn-primario" type="submit" disabled={corriendo}>
              {corriendo ? 'Analizando operación…' : 'Ejecutar ciclo'}
            </button>
          </div>
        </form>
      </div>
    </div>
  {/if}
</div>

<!-- La burbuja del Supervisor vive en +layout.svelte desde el 21/10/2026:
     aparece en todas las pestañas y no se corta al cambiar de una a otra.
     'lib/v2/ChatSupervisor.svelte' sigue sin montar a proposito; su destino
     es una decision pendiente, no un olvido. -->
