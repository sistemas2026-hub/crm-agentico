<script>
  import ChatBurbuja from '$lib/supervisor/ChatBurbuja.svelte';
  import { resultadoDelCierre } from '$lib/v2/resultado-del-cierre.js';
  //  La burbuja del chat del Supervisor. Vive en su propio componente: este
  //  archivo ya tiene 1.900 lineas y es de los que CLAUDE.md marca como
  //  superficie de conflicto alta.
  import { enhance } from '$app/forms';
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
    pasosDelCiclo
  } from '$lib/v2/supervisor-noc-detalle.js';
  import {
    kpisDelTablero,
    hallazgosPorTipo,
    estadoDeCasos,
    ordenesDeTrabajo,
    cargaPorTecnico,
    ticketsPorOrigen,
    bandejaDe,
    bandejaDeRevision,
    rotuloDeHallazgo,
    paginacion,
    actividadReciente,
    celdaDeSla,
    BLOQUES_SIN_DATO
  } from '$lib/v2/supervisor-noc-tablero.js';
  import './supervisor-noc.css';

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

  async function abrirAlcance() {
    modalAlcance = true;
    alcanceError = '';
    alcanceCargando = true;
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
    } finally {
      alcanceCargando = false;
    }
  }

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
  const POR_PAGINA = 6;

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

  $effect(() => {
    //  Se vuelven a enganchar cuando la carga del servidor corre de nuevo.
    //  'vigente' evita que una respuesta vieja pise una nueva si la persona
    //  recarga antes de que la anterior termine.
    let vigente = true;
    indicadoresVivos = null;
    autonomiaViva = null;
    capacidadViva = null;
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
  const donut = $derived(hallazgosPorTipo(leidas));
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

  /**
   * La bandeja: filtrada, ordenada y numerada. La logica vive en
   * $lib/v2/supervisor-noc-tablero.js y esta probada aparte -- el orden y la
   * numeracion tienen casos borde (prioridad ausente, sin fecha de origen)
   * que dentro del .svelte no se pueden ejercitar sin montarlo.
   */
  const bandeja = $derived(
    bandejaDeRevision(propuestas, {
      estado: filtroEstado,
      nivel: filtroNivel,
      tipo: filtro,
      conPropuesta: filtroPropuesta,
      texto: busqueda
    })
  );

  const pag = $derived(paginacion(bandeja.length, nPagina, POR_PAGINA));

  /**
   * Las filas de esta pagina. El N.º que ya traen es la posicion dentro de
   * TODOS los resultados filtrados, no dentro de la pagina: asi el numero de
   * la fila coincide con el "Mostrando 7 a 12" de abajo en vez de reiniciar
   * en 1 cada vez.
   */
  const pagina = $derived(bandeja.slice(pag.desde - 1, pag.hasta));

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
      try {
        const r = await fetch('/supervisor-noc/actividad', {
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
    const cuenta = { pendientes: 0, decididas: 0 };
    for (const p of propuestas) {
      const b = bandejaDe(p);
      if (b) cuenta[b] += 1;
    }
    return { ...cuenta, '': cuenta.pendientes + cuenta.decididas };
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
    const base = bandejaDeRevision(propuestas, { estado: filtroEstado });
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
    for (const p of propuestas) {
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
  const hora = (/** @type {string|null} */ iso) =>
    iso ? new Date(iso).toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' }) : '—';
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

  const alCorrerCiclo = () => {
    corriendo = true;
    return async (/** @type {any} */ { update, result }) => {
      corriendo = false;
      modalCiclo = false;
      const auto = result?.data?.resumen?.cierre_automatico;
      cerradosDelCiclo = Array.isArray(auto?.cerrados_detalle) ? auto.cerrados_detalle : [];
      await update({ reset: false });
      await invalidateAll();
    };
  };

  const alCorrerAsistente = (/** @type {string} */ dominio) => () => {
    asistenteCorriendo = dominio;
    return async (/** @type {any} */ { update }) => {
      asistenteCorriendo = null;
      await update({ reset: false });
      await invalidateAll();
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
  const analisis = $derived(analisisSeparado(detalle));
  const aceptar = $derived(siAcepto(detalle, contraste));
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
   */
  let decidiendo = $state('');

  const alDecidir = () => async (/** @type {any} */ { update }) => {
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

  /** Marca que se empezo, ANTES de que el formulario salga. */
  const alEmpezar = (/** @type {string} */ que) => () => { decidiendo = que; };
</script>

<svelte:window onkeydown={alTeclado} />

<svelte:head>
  <title>Supervisor NOC IA · {data.org ?? 'Operaciones'}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="" />
  <link
    href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;700&family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap"
    rel="stylesheet"
  />
</svelte:head>

<div class="snoc">
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
        <header class="snoc-fila-sep" style="flex-wrap:wrap; padding-bottom:var(--snoc-sm);">
          <div class="snoc-fila">
            <div class="snoc-marca-grande">
              <span class="snoc-icono" style="font-size:28px;">psychology</span>
            </div>
            <div class="snoc-pila-xs">
              <div class="snoc-fila">
                <h1 class="snoc-h1">Supervisor NOC IA</h1>
                <!-- DECIA "Shadow Mode", y dejo de ser cierto el 08/10/2026:
                     hay un caso en que ejecuta. Una etiqueta que miente sobre
                     eso es peor que ninguna -- es la que alguien va a citar el
                     dia que pregunte por que se cerro un caso sin que nadie lo
                     aprobara.
                     No se condiciona a un dato en vivo a proposito: el estado
                     exacto esta a un clic, en el panel de Autonomia, y una
                     insignia que dependiera de tres condiciones diria algo
                     distinto cada vez que una cambie. -->
                <span class="snoc-insignia snoc-insignia-neutra snoc-primario"
                      title="Solo ejecuta el cierre de casos ya cerrados en WispHub, y solo si una persona se lo delegó y el diagnóstico del equipo lo habilita">
                  Observa, propone y cierra sincronizados
                </span>
              </div>
              <p class="snoc-body snoc-secundario">
                Observa la operación, la analiza y propone. La decisión es humana
                <strong>salvo en un caso</strong>: cierra los que ya están cerrados
                en WispHub, si alguien le delegó esa tarea y el diagnóstico del
                equipo lo habilita.
              </p>
            </div>
          </div>

          <div class="snoc-fila" style="gap:var(--snoc-sm);">
            <span
              class="snoc-mono-sm snoc-tenue"
              title="Derivado de la propuesta más reciente: el backend no registra cuándo corrió el ciclo."
            >
              Última propuesta: {ultimaPropuesta ? fecha(ultimaPropuesta) : 'ninguna todavía'}
            </span>
            <button
              class="snoc-btn snoc-btn-primario"
              type="button"
              onclick={() => (modalCiclo = true)}
              disabled={corriendo}
            >
              <span class="snoc-icono" style="font-size:14px;">refresh</span>
              <span>{corriendo ? 'Analizando…' : 'Ejecutar ciclo'}</span>
            </button>
          </div>

          <div class="snoc-envuelve snoc-pestanas" style="width:100%; order:3;">
            <a class="snoc-pildora snoc-pildora-activa" href="/supervisor-noc">Pendientes por revisión</a>
            <a class="snoc-pildora" href="/supervisor-noc/programacion">Programación</a>
          <a class="snoc-pildora" href="/supervisor-noc/cuadrillas">Cuadrillas</a>
          <a class="snoc-pildora" href="/supervisor-noc/despacho">Despacho</a>
          </div>
        </header>

        <!--
          ============ ESTADO DEL MOTOR ============
          Una sola línea. Antes esto eran cuatro tarjetas, un banner y una barra
          de controles diciendo lo mismo: «la IA no ejecuta» aparecía cuatro
          veces antes del primer dato. La garantía nunca fue el mensaje repetido
          -- es que en este archivo no existe ninguna acción que ejecute algo.
        -->
        <section class="snoc-tarjeta" style="padding:var(--snoc-sm) var(--snoc-md);">
          <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
            <div class="snoc-fila" style="gap:var(--snoc-xs);">
              <span class="snoc-icono snoc-primario" style="font-size:18px;">visibility</span>
              <span class="snoc-body-sm">
                Analiza y propone. En <strong>casos desincronizados</strong>, aceptar autoriza un cierre
                controlado en Dexter.
              </span>
            </div>
            <div class="snoc-envuelve">
              <button
                type="button"
                class="snoc-insignia snoc-insignia-neutra"
                style="cursor:pointer; border:0; font:inherit;"
                title="Ver y cambiar cuánto puede hacer solo el Supervisor"
                onclick={abrirAlcance}
              >
                Autonomía:
                <!--
                  TRES ESTADOS, NO DOS. 'autonomiaViva === null' es "todavia
                  no llego" y es distinto de "llego y no se pudo leer":
                  mostrarlos igual le diria a una persona que el motor fallo
                  cuando lo unico que pasa es que la respuesta viene en
                  camino.
                -->
                {#if autonomiaViva === null}
                  <span class="snoc-tenue">leyendo…</span>
                {:else if autonomiaViva.estado == null}
                  <span class="snoc-tenue">no se pudo leer</span>
                {:else}
                  <span
                    class="snoc-punto {autonomiaViva.permitido ? 'snoc-punto-secundario' : 'snoc-punto-error'}"
                  ></span>
                  {autonomiaViva.estado}
                {/if}
                <span class="snoc-icono" style="font-size:14px;">tune</span>
              </button>
              <span class="snoc-insignia snoc-insignia-neutra">Acciones ejecutadas: 0</span>
              {#if fueraDeAlcance > 0}
                <span class="snoc-insignia snoc-insignia-error" title="Por encima del alcance de esta etapa">
                  {fueraDeAlcance} fuera de alcance
                </span>
              {/if}
            </div>
          </div>
        </section>


        <!-- ============ LOS SEIS KPI ============ -->
        {#if indicadoresVivos?.error}
          <div class="snoc-aviso">
            <span class="snoc-icono snoc-error-txt" style="font-size:20px;">error</span>
            <p class="snoc-body" style="margin:0;">{indicadoresVivos.error.mensaje}</p>
          </div>
        {/if}

        <section class="snoc-rejilla snoc-rejilla-2 snoc-rejilla-6">
          {#each kpis as k (k.clave)}
            {#if k.clave === 'propuestas'}
              <!--
                El unico KPI que lleva a algun lado, porque es el unico que
                tiene un destino: la bandeja de arriba. Es un <a> de verdad y
                no un div con onclick -- el teclado llega a uno y no al otro.
              -->
              <a class="snoc-kpi snoc-kpi-enlace snoc-tono-{k.tono}" href="#pendientes" onclick={irAPendientes}>
                <div class="snoc-kpi-icono">
                  <span class="snoc-icono" style="font-size:15px;">{ICONO_KPI[k.clave]}</span>
                </div>
                {#if k.n == null}
                  <span class="snoc-kpi-n snoc-sin-dato" style="font-size:1rem;">Sin dato</span>
                {:else}
                  <span class="snoc-kpi-n">{k.n}</span>
                {/if}
                <span class="snoc-kpi-titulo">{k.titulo}</span>
                <span class="snoc-kpi-sub">{k.sub}</span>
              </a>
            {:else}
              <div class="snoc-kpi snoc-tono-{k.tono}">
                <div class="snoc-kpi-icono">
                  <span class="snoc-icono" style="font-size:15px;">{ICONO_KPI[k.clave]}</span>
                </div>
                {#if k.n == null}
                  <!--
                    Un hueco, no un cero: el backend no entregó el indicador, y
                    escribir «0» aquí afirmaría que no hay ninguno.
                  -->
                  <span class="snoc-kpi-n snoc-sin-dato" style="font-size:1rem;">Sin dato</span>
                {:else}
                  <span class="snoc-kpi-n">{k.n}</span>
                {/if}
                <span class="snoc-kpi-titulo">{k.titulo}</span>
                <span class="snoc-kpi-sub">{k.sub}</span>
              </div>
            {/if}
          {/each}
        </section>

        <!-- ============ LOS CUATRO GRÁFICOS ============ -->
        <section class="snoc-rejilla snoc-rejilla-2 snoc-rejilla-4">
          <!-- 1 · Hallazgos por tipo -->
          <div class="snoc-grafico">
            <h2 class="snoc-grafico-titulo">
              <span class="snoc-icono snoc-primario" style="font-size:15px;">donut_small</span>
              Hallazgos por tipo
            </h2>
            {#if donut.disponible}
              <div class="snoc-grafico-cuerpo">
                <div class="snoc-donut-centro">
                  <svg
                    class="snoc-donut"
                    viewBox="0 0 40 40"
                    width="110"
                    height="110"
                    role="img"
                    aria-label="Reparto de las {donut.total} propuestas por tipo de señal"
                  >
                    {#each donut.tramos as t (t.clave)}
                      <circle
                        cx="20"
                        cy="20"
                        r="15.9155"
                        fill="none"
                        stroke={t.color}
                        stroke-width="5"
                        stroke-dasharray={t.dash}
                        stroke-dashoffset={t.offset}
                      ></circle>
                    {/each}
                  </svg>
                  <span class="snoc-donut-cifra">{donut.total}</span>
                </div>
                <div class="snoc-leyenda">
                  {#each donut.tramos as t (t.clave)}
                    <div class="snoc-leyenda-fila" title="{t.etiqueta}: {t.n}">
                      <span class="snoc-leyenda-punto" style="background:{t.color};"></span>
                      <span class="snoc-leyenda-txt">{t.etiqueta}</span>
                      <span class="snoc-leyenda-n">{t.n}</span>
                    </div>
                  {/each}
                </div>
              </div>
            {:else}
              <div class="snoc-hueco">
                {#if data.hallazgos.error}
                  <span class="snoc-hueco-rotulo">Sin dato</span>
                  <p class="snoc-hueco-motivo">{data.hallazgos.error.mensaje}</p>
                {:else}
                  <span class="snoc-hueco-rotulo">Sin propuestas</span>
                  <p class="snoc-hueco-motivo">
                    Corré un ciclo de análisis para que el Supervisor revise la operación.
                  </p>
                {/if}
              </div>
            {/if}
          </div>

          <!-- 2 · Estado de casos técnicos -->
          <div class="snoc-grafico">
            <h2 class="snoc-grafico-titulo">
              <span class="snoc-icono snoc-primario" style="font-size:15px;">bar_chart</span>
              Estado de casos técnicos
            </h2>
            {#if barras.disponible}
              <div class="snoc-barras">
                {#each barras.barras as b (b.estado)}
                  <div class="snoc-barra-col" title="{b.estado}: {b.n}">
                    <span class="snoc-barra-n">{b.n}</span>
                    <div class="snoc-barra" style="height:{b.alto}%;"></div>
                    <span class="snoc-barra-txt">{b.estado}</span>
                  </div>
                {/each}
              </div>
            {:else}
              <div class="snoc-hueco">
                <span class="snoc-hueco-rotulo">Sin dato</span>
                <p class="snoc-hueco-motivo">El reparto de casos por estado no llegó en esta consulta.</p>
              </div>
            {/if}
          </div>

          <!--
            3 · Tickets por origen
            Sale de `casos.por_origen`, que agrupa por `Case.external_provider`:
            'wisphub' cuando el caso espeja un ticket del proveedor, 'dexter'
            cuando nació en el CRM. Son las dos categorías que el campo
            distingue; no se derivan otras.
          -->
          <div class="snoc-grafico">
            <h2 class="snoc-grafico-titulo">
              <span class="snoc-icono snoc-primario" style="font-size:15px;">hub</span>
              Tickets por origen
            </h2>
            {#if origen.disponible}
              <div class="snoc-grafico-cuerpo">
                <div class="snoc-donut-centro">
                  <svg
                    class="snoc-donut"
                    viewBox="0 0 40 40"
                    width="110"
                    height="110"
                    role="img"
                    aria-label="Reparto de los {origen.total} casos por sistema de origen"
                  >
                    {#each origen.tramos as t (t.clave)}
                      <circle
                        cx="20"
                        cy="20"
                        r="15.9155"
                        fill="none"
                        stroke={t.color}
                        stroke-width="5"
                        stroke-dasharray={t.dash}
                        stroke-dashoffset={t.offset}
                      ></circle>
                    {/each}
                  </svg>
                  <span class="snoc-donut-cifra">{origen.total}</span>
                </div>
                <div class="snoc-leyenda">
                  {#each origen.tramos as t (t.clave)}
                    <div class="snoc-leyenda-fila" title="{t.etiqueta}: {t.n}">
                      <span class="snoc-leyenda-punto" style="background:{t.color};"></span>
                      <span class="snoc-leyenda-txt">{t.etiqueta}</span>
                      <span class="snoc-leyenda-n">{t.n}</span>
                      <span class="snoc-tenue">{t.pct}%</span>
                    </div>
                  {/each}
                </div>
              </div>
            {:else}
              <div class="snoc-hueco">
                <span class="snoc-hueco-rotulo">Sin dato</span>
                <p class="snoc-hueco-motivo">
                  Ningún caso trae sistema de origen en esta consulta.
                </p>
              </div>
            {/if}
          </div>

          <!-- 4 · Mapa de operación · LAS COORDENADAS ESTAN EN LA ORDEN, NO EN LA PROPUESTA -->
          <div class="snoc-grafico">
            <h2 class="snoc-grafico-titulo">
              <span class="snoc-icono snoc-tenue" style="font-size:15px;">map</span>
              {SIN_DATO.mapa.titulo}
            </h2>
            <div class="snoc-hueco">
              <span class="snoc-hueco-rotulo">Falta en el backend</span>
              <p class="snoc-hueco-motivo">{SIN_DATO.mapa.motivo}</p>
            </div>
          </div>
        </section>

        <!--
          ============ PENDIENTES POR REVISIÓN ============
          Va ARRIBA, antes de los indicadores, porque es lo único de esta
          pantalla que pide una decisión de una persona. Un KPI se mira; esto
          se atiende.

          Antes eran DOS tablas con las mismas filas: «Hallazgos recientes»
          aquí y «Pendientes de revisión» al final, y como las 93 propuestas
          estaban en estado `propuesta`, coincidían fila por fila. Leerlas dos
          veces no era redundancia inofensiva -- hacía dudar de si eran dos
          cosas distintas que casualmente coincidían.

          Los botones de decisión no están en la fila: viven en «Ver detalle»,
          junto a la evidencia. Decidir sobre una fila de tabla es decidir sin
          mirar por qué.
        -->
        <section class="snoc-panel" id="pendientes">
          <!-- CABECERA: el título, cuántas esperan y el buscador -->
          <div class="snoc-bandeja-cabecera">
            <div class="snoc-fila" style="gap:var(--snoc-sm);">
              <div class="snoc-chip-icono snoc-chip-icono-solido">
                <span class="snoc-icono" style="font-size:18px;">rule</span>
              </div>
              <div class="snoc-pila-xs">
                <!--
                  Dos lineas y no un titulo largo: la de arriba dice DONDE
                  estas -- el centro entero -- y la de abajo QUE es esta
                  seccion. Fundirlas en «Centro del Supervisor NOC IA -
                  Pendientes por revision» daria un titulo que se lee como un
                  breadcrumb y pesa mas que la tabla que encabeza.
                -->
                <span class="snoc-label-sm snoc-secundario snoc-rotulo-centro">
                  Centro del Supervisor NOC IA
                </span>
                <h2 class="snoc-h3">Pendientes por revisión</h2>
                {#if data.hallazgos.error}
                  <span class="snoc-body-sm snoc-error-txt">No se pudieron leer</span>
                {:else}
                  <span class="snoc-body-sm snoc-secundario">
                    <strong class="snoc-primario">{bandeja.length}</strong>
                    {filtroEstado === 'pendientes' ? 'pendientes de decisión' : 'en la lista'}
                  </span>
                {/if}
              </div>
            </div>

            <label class="snoc-buscador">
              <span class="snoc-icono snoc-tenue" style="font-size:18px;" aria-hidden="true">search</span>
              <input
                type="search"
                class="snoc-buscador-campo"
                placeholder="Buscar cliente, caso, asunto o técnico…"
                bind:value={busqueda}
                aria-label="Buscar en los pendientes por revisión"
              />
            </label>
          </div>

          {#if !data.hallazgos.error && propuestas.length > 0}
            <!-- Los filtros se aplican en el navegador: el GET ya trajo el
                 conjunto entero, así que una vuelta al servidor por pastilla
                 sería reordenar datos que ya están en pantalla. -->
            <!--
              Una sola fila, como la referencia: los dos grupos separados por
              una barra, sin rótulos a la izquierda. Los rótulos
              «REVISIÓN»/«PRIORIDAD» ocupaban tres líneas para decir algo que
              las propias pastillas ya dicen.
            -->
            <div class="snoc-filtros-bandeja">
              {#each [{ v: 'pendientes', t: 'Pendientes' }, { v: 'decididas', t: 'Ya decididas' }, { v: '', t: 'Todas' }] as o (o.v)}
                <button
                  class="snoc-pildora {filtroEstado === o.v ? 'snoc-pildora-activa' : ''}"
                  type="button"
                  onclick={() => (filtroEstado = o.v)}
                >
                  {o.t} ({conteoPorEstado[o.v] ?? 0})
                </button>
              {/each}

              <span class="snoc-separador-filtro" aria-hidden="true">|</span>

              <button
                class="snoc-pildora {filtroNivel ? '' : 'snoc-pildora-activa'}"
                type="button"
                onclick={() => (filtroNivel = null)}
              >
                Todas
              </button>
              {#each NIVELES_VISIBLES as nv (nv)}
                <button
                  class="snoc-pildora {filtroNivel === nv ? 'snoc-pildora-activa' : ''}"
                  type="button"
                  onclick={() => (filtroNivel = nv)}
                  disabled={(conteoPorNivel[nv] ?? 0) === 0}
                  title="Prioridad {nv}"
                >
                  <span class="snoc-punto-nivel snoc-nivel-{nv.toLowerCase()}"></span>
                  {nv} ({conteoPorNivel[nv] ?? 0})
                </button>
              {/each}

              <button
                class="snoc-pildora {filtroPropuesta === 'si' ? 'snoc-pildora-activa' : ''}"
                type="button"
                onclick={() => (filtroPropuesta = filtroPropuesta === 'si' ? '' : 'si')}
                title="Las que traen una acción recomendada escrita"
              >
                Con propuesta
              </button>
              <button
                class="snoc-pildora {filtroPropuesta === 'no' ? 'snoc-pildora-activa' : ''}"
                type="button"
                onclick={() => (filtroPropuesta = filtroPropuesta === 'no' ? '' : 'no')}
                title="Detectadas, sin acción recomendada"
              >
                Sin propuesta
              </button>

              <!--
                El tipo NO está en la referencia, y sí es un filtro que
                funciona. Se queda, como desplegable y al final de la fila:
                quitarlo replicaría la imagen perdiendo una función que ya
                existía.
              -->
              <select
                class="snoc-select"
                aria-label="Filtrar por tipo de hallazgo"
                value={filtro ?? ''}
                onchange={(e) => (filtro = e.currentTarget.value || null)}
              >
                <option value="">Todos los tipos ({propuestas.length})</option>
                {#each porSenal as [clave, info] (clave)}
                  <option value={clave}>{rotuloDeHallazgo(clave, info.etiqueta)} ({info.n})</option>
                {/each}
              </select>

              {#if hayFiltros}
                <button class="snoc-enlace snoc-limpiar" type="button" onclick={limpiarFiltros}>
                  <span class="snoc-icono" style="font-size:14px;" aria-hidden="true">restart_alt</span>
                  Limpiar filtros
                </button>
              {/if}
            </div>
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
              <span class="snoc-icono snoc-error-txt" style="font-size:18px;">error</span>
              <span class="snoc-body">{data.hallazgos.error.mensaje}</span>
            </div>
          {:else if propuestas.length === 0}
            <p class="snoc-body snoc-secundario">
              No hay propuestas registradas. Corré un ciclo de análisis para que el Supervisor revise la operación.
            </p>
          {:else if bandeja.length === 0}
            <p class="snoc-body snoc-secundario">
              {busqueda.trim()
                ? `Ninguna propuesta coincide con «${busqueda.trim()}».`
                : 'Ninguna propuesta con esos filtros.'}
              <button class="snoc-enlace" type="button" onclick={limpiarFiltros}>Limpiar filtros</button>
            </p>
          {:else}
            <div class="snoc-tabla-caja">
              <table class="snoc-tabla snoc-tabla-bandeja">
                <thead>
                  <tr>
                    <th style="width:2.5rem;">N.º</th>
                    <th>Prioridad</th>
                    <th>Cliente</th>
                    <th>Caso / OT</th>
                    <th>Asunto del ticket</th>
                    <th>Técnico actual</th>
                    <th>SLA</th>
                    <th>Antigüedad</th>
                    <th>Propuesta</th>
                    <th class="snoc-derecha">Acción</th>
                  </tr>
                </thead>
                <tbody>
                  {#each pagina as p (p.id)}
                    {@const sla = celdaDeSla(p.sla_estado, p.sla_minutos)}
                    <tr class={abierta === p.id ? 'snoc-fila-activa' : ''}>
                      <!-- La posición dentro de los resultados, no el id: con
                           un filtro puesto, numerar por id dejaría huecos. -->
                      <td class="snoc-mono-sm snoc-tenue">{p.n}</td>
                      <td>
                        <span
                          class="snoc-insignia snoc-pildora-nivel snoc-nivel-{p.nivel.texto.toLowerCase()}"
                          title="Prioridad {p.prioridad} en la escala del Supervisor (0-99, menor es más urgente)"
                        >
                          <span class="snoc-punto-nivel snoc-nivel-{p.nivel.texto.toLowerCase()}"></span>
                          {p.nivel.texto}
                        </span>
                        {#if !p.revision.pendiente}
                          <div>
                            <span class="snoc-insignia snoc-insignia-variante" title="Ya pasó por una persona">
                              {p.revision.texto}
                            </span>
                          </div>
                        {/if}
                      </td>
                      <td class="snoc-body-sm">
                        {#if p.cliente}
                          {p.cliente}
                        {:else}
                          <span class="snoc-celda-ausente">No disponible en la fuente</span>
                        {/if}
                      </td>
                      <!--
                        El numero del proveedor NO alcanza para encontrar el
                        caso aqui: en el CRM un caso no tiene numero visible, se
                        abre por su id. Mostrar solo el de WispHub hacia que una
                        propuesta que dice "cerra el caso" no se pudiera
                        verificar contra el caso del que hablaba.

                        Por eso ahora van los dos: el enlace al caso de este
                        lado, y debajo el numero del proveedor para buscarlo
                        alla. Son dos sistemas y dos identificadores; colapsarlos
                        en uno fue el error.
                      -->
                      <td>
                        {#if p.orden_numero != null}
                          <span class="snoc-id">OT-{p.orden_numero}</span>
                        {:else if p.caso_id}
                          <a class="snoc-id" href="/tickets/{p.caso_id}"
                             title="Abrir el caso en Dexter">
                            Caso {String(p.caso_id).slice(0, 8)}
                          </a>
                          {#if p.ticket_externo}
                            <div class="snoc-mono-sm snoc-tenue">
                              {p.ticket_externo}{#if p.proveedor_externo} · {p.proveedor_externo}{/if}
                            </div>
                          {/if}
                        {:else if p.ticket_externo}
                          <span class="snoc-id">{p.ticket_externo}</span>
                          {#if p.proveedor_externo}
                            <div class="snoc-mono-sm snoc-tenue">{p.proveedor_externo}</div>
                          {/if}
                        {:else}
                          <span class="snoc-mono-sm snoc-tenue" title={p.origen_id}>
                            {String(p.origen_id).slice(0, 8)}
                          </span>
                        {/if}
                      </td>
                      <td class="snoc-body-sm snoc-recorte" title={p.asunto}>
                        {#if p.asunto}
                          {p.asunto}
                        {:else}
                          <span class="snoc-celda-ausente">No disponible en la fuente</span>
                        {/if}
                      </td>
                      <td class="snoc-body-sm">
                        <!--
                          EL TÉCNICO ACTUAL, no el que la IA sugiere. El
                          detalle trae `responsable_sugerido` y ponerlo aquí
                          diría que alguien ya tiene la orden.
                        -->
                        {#if p.tecnico}
                          {p.tecnico}
                        {:else}
                          <span class="snoc-celda-ausente">Sin técnico asignado</span>
                        {/if}
                      </td>
                      <td>
                        <span class="snoc-insignia snoc-sla-{sla.tono}" title={sla.detalle}>{sla.texto}</span>
                      </td>
                      <td class="snoc-mono-sm snoc-tenue">
                        {#if p.edad.texto}
                          {p.edad.texto}
                        {:else}
                          <span class="snoc-celda-ausente">—</span>
                        {/if}
                      </td>
                      <td class="snoc-body-sm snoc-recorte" title={p.accion_propuesta}>
                        {#if p.tienePropuesta}
                          {p.accion_propuesta}
                        {:else}
                          <span class="snoc-celda-ausente">Sin acción recomendada</span>
                        {/if}
                      </td>
                      <td class="snoc-derecha">
                        <button
                          class="snoc-btn {abierta === p.id ? 'snoc-btn-primario' : ''}"
                          type="button"
                          onclick={() => abrirDetalle(p.id)}
                        >
                          <span class="snoc-icono" style="font-size:14px;" aria-hidden="true">visibility</span>
                          Ver detalle
                        </button>
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>

            <!-- PAGINACIÓN -->
            <div class="snoc-paginacion">
              <span class="snoc-mono-sm snoc-tenue">
                Mostrando {pag.desde} a {pag.hasta} de {pag.total} registro{pag.total === 1 ? '' : 's'}
              </span>
              {#if pag.paginas > 1}
                <div class="snoc-paginacion-botones">
                  <button
                    class="snoc-pildora"
                    type="button"
                    onclick={() => (nPagina = pag.actual - 1)}
                    disabled={pag.actual === 1}
                  >
                    Anterior
                  </button>
                  {#each pag.ventana as n, i (i)}
                    {#if n === null}
                      <!-- Un hueco declarado, no un número que falte. -->
                      <span class="snoc-paginacion-hueco" aria-hidden="true">…</span>
                    {:else}
                      <button
                        class="snoc-pildora {n === pag.actual ? 'snoc-pildora-activa' : ''}"
                        type="button"
                        onclick={() => (nPagina = n)}
                        aria-current={n === pag.actual ? 'page' : undefined}
                        aria-label="Página {n}"
                      >
                        {n}
                      </button>
                    {/if}
                  {/each}
                  <button
                    class="snoc-pildora"
                    type="button"
                    onclick={() => (nPagina = pag.actual + 1)}
                    disabled={pag.actual === pag.paginas}
                  >
                    Siguiente
                  </button>
                </div>
              {/if}
            </div>
            <span class="snoc-mono-sm snoc-tenue">
              Se revisa desde «Ver detalle», junto a la evidencia.
            </span>
          {/if}
        </section>

        <!-- ============ LOS TRES BLOQUES DE ABAJO ============ -->
        <section class="snoc-rejilla snoc-rejilla-2 snoc-rejilla-3">
          <!-- Técnicos · carga operativa -->
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
            </h2>
            {#if data.actividad.error}
              <div class="snoc-hueco">
                <span class="snoc-hueco-rotulo">Sin dato</span>
                <p class="snoc-hueco-motivo">{data.actividad.error.mensaje}</p>
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
                    {#each actividad.filas as f (f.id)}
                      <tr>
                        <td class="snoc-mono-sm snoc-tenue" title={fecha(f.cuando)}>{hora(f.cuando)}</td>
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
              </div>
            {/if}
          </div>
        </section>

        <!-- ============ ASISTENTES OPERATIVOS ============ -->
        <div class="snoc-panel" style="gap:var(--snoc-sm);">
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
          {:else if form?.ok && form.tipo === 'ciclo'}
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

          <div class="snoc-fila" style="gap:var(--snoc-xs); padding-top:var(--snoc-xs);">
            <span class="snoc-icono snoc-primario" style="font-size:13px;">gavel</span>
            <span class="snoc-mono-sm snoc-tenue">
              Los asistentes solo leen y proponen. No programan, no asignan y no llaman a ningún sistema externo.
            </span>
          </div>
        </div>
      {/if}
    </div>
  </div>

  <!-- ============ MODAL DE DETALLE DEL HALLAZGO ============ -->
  {#if abierta}
    <div
      class="snoc-velo snoc-velo-centrado"
      role="presentation"
      onclick={(e) => {
        if (e.target === e.currentTarget) cerrarDetalle();
      }}
    >
      <div class="snoc-modal-hallazgo" role="dialog" aria-modal="true" aria-labelledby="snoc-hallazgo-titulo">
        <!-- CABECERA: navegación entre hallazgos -->
        <div class="snoc-modal-cabecera">
          <div class="snoc-fila" style="gap:var(--snoc-xs);">
            {#if posicion.total > 1}
              <button
                class="snoc-btn"
                type="button"
                onclick={() => irA(-1)}
                disabled={posicion.indice <= 0 || cargandoDetalle}
              >
                <span class="snoc-icono" style="font-size:16px;">chevron_left</span> Anterior
              </button>
              <span class="snoc-mono-sm snoc-contador">{posicion.indice + 1} de {posicion.total}</span>
              <button
                class="snoc-btn"
                type="button"
                onclick={() => irA(1)}
                disabled={posicion.indice >= posicion.total - 1 || cargandoDetalle}
              >
                Siguiente <span class="snoc-icono" style="font-size:16px;">chevron_right</span>
              </button>
            {/if}
          </div>
          <div class="snoc-fila" style="gap:var(--snoc-sm);">
            <!--
              La insignia dice lo que aceptar HACE, no en que modo esta el
              producto: para una desincronizacion aceptar autoriza un cierre.
            -->
            <span class="snoc-insignia snoc-insignia-neutra">
              <span class="snoc-punto snoc-punto-primario"></span>
              {aceptar.ejecuta
                ? 'Cierre controlado · requiere tu autorización'
                : 'Observación · sin ejecución'}
            </span>
            <button class="snoc-btn" type="button" onclick={cerrarDetalle} aria-label="Cerrar">
              <span class="snoc-icono" style="font-size:18px;">close</span>
            </button>
          </div>
        </div>

        <div class="snoc-modal-cuerpo">
          {#if cargandoDetalle}
            <div class="snoc-cargando">
              <span class="snoc-icono snoc-girando" style="font-size:22px;">progress_activity</span>
              <span class="snoc-body snoc-secundario">Consultando la propuesta…</span>
            </div>
          {:else if errorDetalle}
            <div class="snoc-aviso">
              <span class="snoc-icono snoc-error-txt" style="font-size:18px;">error</span>
              <span class="snoc-body">{errorDetalle}</span>
            </div>
          {:else if detalle}
            <div class="snoc-fila-sep" style="flex-wrap:wrap;">
              <h3 class="snoc-h2" id="snoc-hallazgo-titulo">{titulo}</h3>
              <span class="snoc-mono-sm snoc-tenue">Leído {haceCuanto(comun?.leido ?? detalle.created_at)}</span>
            </div>

            <!-- LA DISCREPANCIA -->
            <div class="snoc-hallazgo">
              <div class="snoc-fila-sep" style="flex-wrap:wrap;">
                <div class="snoc-fila" style="gap:var(--snoc-xs);">
                  <span class="snoc-icono" style="font-size:18px;">warning</span>
                  <span class="snoc-hallazgo-titulo">{detalle.tipo_senal_display}</span>
                </div>
                <span class="snoc-mono-sm">{detalle.origen_tipo} · {String(detalle.origen_id).slice(0, 8)}</span>
              </div>

              {#if contraste}
                <div class="snoc-mismatch">
                  <div class="snoc-mismatch-lado">
                    <span class="snoc-label-sm" style="text-transform:uppercase;">En el CRM</span>
                    <span class="snoc-h4">{contraste.crm}</span>
                  </div>
                  <span class="snoc-mismatch-vs">≠</span>
                  <div class="snoc-mismatch-lado">
                    <span class="snoc-label-sm" style="text-transform:uppercase;">En el proveedor</span>
                    <span class="snoc-h4">{contraste.proveedor}</span>
                  </div>
                </div>
              {:else}
                <p class="snoc-body" style="margin:0;">{detalle.motivo || 'Sin motivo registrado.'}</p>
              {/if}
            </div>

            <!-- TIRA DE CINCO -->
            <div class="snoc-tira">
              <span class="snoc-tira-item">
                <span class="snoc-label-sm snoc-tenue">Estado</span>
                <span class="snoc-insignia {estadoDe(detalle.estado).clase}">{estadoDe(detalle.estado).texto}</span>
              </span>
              <span class="snoc-tira-item">
                <span class="snoc-label-sm snoc-tenue">Prioridad</span>
                <span class="snoc-mono">
                  {detalle.prioridad}{#if basePrioridad}<span class="snoc-tenue"> · {basePrioridad}</span>{/if}
                </span>
              </span>
              <span class="snoc-tira-item">
                <span class="snoc-label-sm snoc-tenue">Autonomía</span>
                <span class="snoc-mono">
                  {detalle.nivel_autonomia_requerido} · {NIVELES[detalle.nivel_autonomia_requerido] ?? '—'}
                </span>
              </span>
              <span class="snoc-tira-item">
                <span class="snoc-label-sm snoc-tenue">Detección</span>
                <span class="snoc-mono">{haceCuanto(detalle.created_at)}</span>
              </span>
              <span class="snoc-tira-item">
                <span class="snoc-label-sm snoc-tenue">Expira</span>
                <span class="snoc-mono">{expiraEn(detalle.expira_en)}</span>
              </span>
            </div>

            <!-- ============ 1 · IDENTIFICACIÓN ============ -->
            <!--
              Lo primero que la pantalla tiene que contestar es DE QUÉ habla.
              Las cuatro casillas salen del contexto que el backend ya resolvió
              para la fila; las que la fuente no entrega lo dicen con todas las
              letras en vez de quedarse vacías.
            -->
            <dl class="snoc-identidad">
              {#each identidad as casilla (casilla.rotulo)}
                <div>
                  <dt>{casilla.rotulo}</dt>
                  <dd class:snoc-sin-fuente={casilla.valor === AUSENTE}>
                    {#if casilla.href && casilla.valor !== AUSENTE}
                      <a class="snoc-enlace-externo" href={casilla.href}>{casilla.valor}</a>
                    {:else}
                      {casilla.valor}
                    {/if}
                  </dd>
                </div>
              {/each}
            </dl>

            <!-- ============ 2 · ¿QUÉ ESTÁ PASANDO? ============ -->
            <section class="snoc-que-pasa">
              <h4 class="snoc-h4">¿Qué está pasando?</h4>
              <p class="snoc-que-pasa-frase">{resumen}</p>
            </section>

            <!-- ============ 3 · DEXTER vs WISPHUB ============ -->
            <section class="snoc-columna">
              <div class="snoc-columna-titulo">
                <span class="snoc-icono snoc-primario" style="font-size:15px;">compare_arrows</span>
                <span class="snoc-label-sm" style="text-transform:uppercase;">Dexter vs WispHub</span>
              </div>
              <table class="snoc-comparacion">
                <thead>
                  <tr><th>Información</th><th>Dexter</th><th>WispHub</th></tr>
                </thead>
                <tbody>
                  {#each comparacion as fila (fila.campo)}
                    <tr>
                      <th scope="row">{fila.campo}</th>
                      <td class:snoc-sin-fuente={fila.dexter === AUSENTE}>{fila.dexter}</td>
                      <td class:snoc-sin-fuente={fila.wisphub === AUSENTE}>{fila.wisphub}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </section>

            <!-- ============ 4 · ¿QUÉ DETECTÓ EL SUPERVISOR? ============ -->
            <section class="snoc-columna">
              <div class="snoc-columna-titulo">
                <span class="snoc-icono snoc-primario" style="font-size:15px;">radar</span>
                <span class="snoc-label-sm" style="text-transform:uppercase;">¿Qué detectó el Supervisor NOC IA?</span>
              </div>
              <dl class="snoc-dl">
                <div><dt>Hallazgo</dt><dd>{titulo}</dd></div>
                <div><dt>Clave técnica</dt><dd class="snoc-mono-sm">{detalle.tipo_senal}</dd></div>
                <div><dt>Detectado</dt><dd class="snoc-mono-sm">{fecha(detalle.created_at)}</dd></div>
                <div>
                  <dt>Fuente</dt>
                  <dd class="snoc-mono-sm">{detalle.conocimiento_version || AUSENTE}</dd>
                </div>
                {#if antiguedad}
                  <div>
                    <dt>Antigüedad</dt>
                    <dd>{antiguedad.dias != null ? `${antiguedad.dias} días` : `desde ${antiguedad.desde}`}</dd>
                  </div>
                {/if}
              </dl>
              <p class="snoc-body-sm snoc-secundario" style="margin:var(--snoc-xs) 0 0;">
                {detalle.motivo || AUSENTE}
              </p>
            </section>

            <!-- ============ 10 · INFORMACIÓN TÉCNICA (se conserva entera) ============
                 Baja de sitio, no se pierde: primero lo que hace falta para
                 decidir, y el detalle técnico a un clic. -->
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

            <!-- ============ 6 · ANÁLISIS DEL SUPERVISOR ============ -->
            <!--
              Las tres cosas van SEPARADAS y rotuladas. Un lector apurado lee
              la interpretación como si fuera un hecho, y sobre eso decide.
            -->
            <section class="snoc-columna">
              <div class="snoc-columna-titulo">
                <span class="snoc-icono snoc-primario" style="font-size:15px;">psychology</span>
                <span class="snoc-label-sm" style="text-transform:uppercase;">Análisis del Supervisor NOC IA</span>
              </div>

              <p class="snoc-etiqueta-analisis">Hechos observados</p>
              {#if analisis.hechos.length === 0}
                <p class="snoc-sin-fuente snoc-body-sm">{AUSENTE}</p>
              {:else}
                <ul class="snoc-lista-hechos">
                  {#each analisis.hechos as h, i (i)}
                    <li>
                      <span class="snoc-body-sm">{h.dato}</span>
                      <span class="snoc-mono-sm snoc-tenue">{h.fuente}</span>
                    </li>
                  {/each}
                </ul>
              {/if}

              <p class="snoc-etiqueta-analisis">Interpretación del Supervisor</p>
              <p class="snoc-body-sm" class:snoc-sin-fuente={analisis.interpretacion === AUSENTE}>
                {analisis.interpretacion}
              </p>

              <p class="snoc-etiqueta-analisis">Impacto operativo</p>
              <p class="snoc-body-sm" class:snoc-sin-fuente={analisis.impacto === AUSENTE}>
                {analisis.impacto}
              </p>

              {#if analisis.faltantes.length > 0}
                <p class="snoc-etiqueta-analisis">Información que falta</p>
                <ul class="snoc-lista-hechos">
                  {#each analisis.faltantes as f, i (i)}
                    <li><span class="snoc-body-sm">{f}</span></li>
                  {/each}
                </ul>
              {/if}
            </section>

            <!-- ============ 7 · LA PROPUESTA ============ -->
            <section class="snoc-propuesta">
              <h4 class="snoc-h4">¿Qué propone el Supervisor NOC IA?</h4>
              <p class="snoc-propuesta-accion">{detalle.accion_propuesta || AUSENTE}</p>
              <dl class="snoc-dl">
                <div><dt>Confirmación humana</dt><dd>Obligatoria</dd></div>
                <div><dt>Evidencia que la respalda</dt><dd>{analisis.hechos.length} observaciones</dd></div>
              </dl>
            </section>

            <!-- ============ 8 · ¿QUÉ PASA SI ACEPTO? ============ -->
            <!--
              La sección que evita el malentendido más caro de esta pantalla.
              NO dice «resultado: caso cerrado»: aceptar registra un acuerdo y
              no ejecuta nada mientras siga el Shadow Mode. El estado
              «ejecutada» no existe en el modelo.
            -->
            <section class="snoc-si-acepto">
              <h4 class="snoc-h4">Si aceptas esta propuesta</h4>
              <dl class="snoc-dl">
                <div>
                  <dt>Estado actual en Dexter</dt>
                  <dd class:snoc-sin-fuente={aceptar.estadoActual === AUSENTE}>{aceptar.estadoActual}</dd>
                </div>
                <div><dt>Acción propuesta</dt><dd>{aceptar.accion}</dd></div>
                <div>
                  <dt>Origen de la decisión</dt>
                  <dd class:snoc-sin-fuente={aceptar.origenDecision === AUSENTE}>{aceptar.origenDecision}</dd>
                </div>
                <div><dt>Tipo</dt><dd>{aceptar.tipo}</dd></div>
              </dl>
              <p class="snoc-aviso-shadow">
                <span class="snoc-icono" style="font-size:16px;">info</span>
                {aceptar.efecto}
              </p>
            </section>

            <!-- ANÁLISIS TÉCNICO COMPLETO (el que ya existía, desplegable) -->
            <details class="snoc-detalle-tecnico">
              <summary class="snoc-label-sm">Ver análisis técnico completo</summary>
            <!-- EVIDENCIA COMO TABLA -->
            <details class="snoc-detalles">
              <summary class="snoc-label-sm">
                Ver análisis técnico completo ({(detalle.evidencia ?? []).length} observaciones registradas)
              </summary>
              <div style="padding-top:var(--snoc-sm);">
                {#if Array.isArray(detalle.evidencia) && detalle.evidencia.length}
                  <div class="snoc-tabla-caja">
                    <table class="snoc-tabla">
                      <thead>
                        <tr><th>Fuente</th><th>Observación</th><th>Referencia</th><th>Leído</th></tr>
                      </thead>
                      <tbody>
                        {#each detalle.evidencia as e, i (i)}
                          <tr>
                            <td class="snoc-mono-sm">{e.fuente ?? '—'}</td>
                            <td class="snoc-body-sm">{e.dato}</td>
                            <td class="snoc-mono-sm snoc-tenue">{e.id ?? '—'}</td>
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
              {#if detalle.propuesta_original}
                <pre class="snoc-pre">{JSON.stringify(detalle.propuesta_original, null, 2)}</pre>
              {/if}
            </details>

            <!-- CICLO: revisión humana ➔ ejecución -->
            </details>

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
          {/if}
        </div>

        <!-- PIE FIJO: la decisión -->
        {#if detalle && !cargandoDetalle && !errorDetalle}
          <div class="snoc-modal-pie">
            <div class="snoc-fila" style="gap:var(--snoc-xs); min-width:0;">
              <span class="snoc-icono snoc-primario" style="font-size:16px;">verified_user</span>
              <span class="snoc-body-sm snoc-secundario">
                {#if aceptar.ejecuta}
                  La IA observa y propone. <strong>La decisión es tuya</strong>: aceptar autoriza un intento de
                  cierre en Dexter, que el sistema revalida antes de ejecutar.
                {:else}
                  La IA observa y propone. <strong>La decisión es tuya</strong>: aceptar no ejecuta nada.
                {/if}
              </span>
            </div>
            {#if detalle.estado === 'propuesta'}
              <div class="snoc-pie-acciones">
                <input class="snoc-campo" bind:value={comentario} placeholder="Motivo (para rechazar o cancelar)" />
                <!--
                  Los tres botones se deshabilitan mientras una decision esta
                  en curso, no solo el que se apreto: las tres actuan sobre la
                  MISMA propuesta, y mandar "rechazar" mientras "aceptar"
                  viaja es pedir dos cosas contrarias sobre lo mismo.
                -->
                <form method="POST" action="?/cancelar" use:enhance={alDecidir} style="display:contents;">
                  <input type="hidden" name="id" value={detalle.id} />
                  <input type="hidden" name="motivo" value={comentario} />
                  <button class="snoc-btn" type="submit" disabled={!!decidiendo}
                          onclick={alEmpezar('Cancelando…')}>
                    {decidiendo === 'Cancelando…' ? 'Cancelando…' : 'Cancelar'}
                  </button>
                </form>
                <form method="POST" action="?/revisar" use:enhance={alDecidir} style="display:contents;">
                  <input type="hidden" name="id" value={detalle.id} />
                  <input type="hidden" name="comentario" value={comentario} />
                  <button class="snoc-btn snoc-btn-error" name="decision" value="rechazada"
                          type="submit" disabled={!!decidiendo}
                          onclick={alEmpezar('Rechazando…')}>
                    {decidiendo === 'Rechazando…' ? 'Rechazando…' : 'Rechazar'}
                  </button>
                  <!--
                    DICE "Cerrando el caso…" y no "Guardando…": en una
                    desincronizacion, aceptar no guarda una decision, ejecuta
                    un cierre contra el proveedor. El texto de espera tiene
                    que decir lo que de verdad esta pasando, que ademas
                    explica por que tarda.
                  -->
                  <button class="snoc-btn snoc-btn-primario" name="decision" value="aceptada"
                          type="submit" disabled={!!decidiendo}
                          onclick={alEmpezar(aceptar.ejecuta ? 'Cerrando el caso…' : 'Guardando…')}>
                    {decidiendo === 'Cerrando el caso…' || decidiendo === 'Guardando…'
                      ? decidiendo
                      : 'Aceptar propuesta'}
                  </button>
                </form>
              </div>
            {:else}
              <div class="snoc-fila" style="gap:var(--snoc-sm);">
                <span class="snoc-body-sm snoc-secundario">
                  Ya revisada: <strong>{estadoDe(detalle.estado).texto}</strong>
                </span>
                <button class="snoc-btn" type="button" onclick={cerrarDetalle}>Cerrar</button>
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
          El Supervisor NOC IA analizará nuevamente la operación y podrá generar nuevas propuestas. En esta etapa
          <strong style="color:var(--snoc-on-surface);">no ejecutará acciones autónomas</strong>.
        </p>
        <div class="snoc-mono-sm snoc-caja-datos">
          <div>• Lo único que escribe: propuestas y su auditoría</div>
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

<!-- La burbuja del Supervisor. Fuera del contenedor a proposito:
     es fija y pertenece a la pantalla, no a una seccion.

     UNA SOLA, y la eleccion esta medida: dos ramas construyeron un chat del
     Supervisor y esta es la que recupera el hilo al abrir (hace GET al montarse)
     y la que ya estaba desplegada y probada. Lo que cambio en la reconciliacion
     no es la burbuja: es a QUE le habla -- ahora al Supervisor dedicado, con sus
     15 herramientas, en vez del agente generico del tenant.
     'lib/v2/ChatSupervisor.svelte' quedo sin montar a proposito; su destino es
     una decision pendiente, no un olvido. -->
<ChatBurbuja />
