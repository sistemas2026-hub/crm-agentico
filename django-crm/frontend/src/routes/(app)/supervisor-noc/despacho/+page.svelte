<script>
  /**
   * Despacho a campo.
   *
   * Lo que faltaba para que el circuito cierre: ticket → caso → DESPACHO →
   * reparto de la madrugada → cuadrilla. `trabajos/crear/` existía y nadie lo
   * llamaba.
   *
   * La sugerencia viene del Supervisor y NO decide: muestra qué labor sostiene
   * la evidencia y por qué, y quien despacha acepta o cambia.
   *
   * REDISEÑO DEL 21/11/2026 (maqueta aprobada):
   *   - Lo principal primero: los casos para despachar son la primera pestaña;
   *     simular, lo que crearía el Supervisor y la jornada van en las otras.
   *     Antes tres paneles de diagnóstico tapaban la tarea.
   *   - «Despachar» abre un panel al costado, en cinco pasos (qué, cuándo,
   *     dónde, quién, para el técnico). Antes el formulario aparecía al fondo
   *     de la página, debajo de la tabla, sin moverse hasta él.
   *   - La sugerencia del Supervisor y la orden que ya existe van en columnas
   *     propias, con color, en vez de apiladas en la celda del asunto.
   *   - La jornada se puede mirar de otro día (`?dia=`), con su rótulo.
   *   - Los resultados salen en un aviso a la vista.
   */
  import { enhance } from '$app/forms';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { untrack } from 'svelte';
  import { paginacion } from '$lib/v2/supervisor-noc-tablero.js';
  import { fechaSugerida } from '$lib/v2/despacho-sugerencias.js';
  import { textoDeLosTotales, totalesDeLoQueCrearia } from '$lib/supervisor/lo-que-crearia.js';
  import '../supervisor-noc.css';
  import Pestanas from '$lib/supervisor/ui/Pestanas.svelte';
  import PanelLateral from '$lib/supervisor/ui/PanelLateral.svelte';
  import { avisar } from '$lib/supervisor/ui/avisos.svelte.js';

  let { data, form } = $props();

  /** @type {string} */
  let pestana = $state(untrack(() => page.url.searchParams.get('pestana') ?? 'casos'));

  let buscando = $state(false);
  /** El resultado de «Buscar casos que necesiten visita», en un aviso. */
  const alBuscar = () => {
    buscando = true;
    return async (/** @type {any} */ { result, update }) => {
      await update();
      buscando = false;
      if (result?.type === 'success') avisar(result.data?.hecho ?? 'El Supervisor revisó la operación.');
      else if (result?.type === 'failure') avisar(result.data?.error ?? 'No se pudo.', { tono: 'error' });
    };
  };

  let creandoOrden = $state(false);
  /** Crear la orden: si sale bien, se cierra el panel y se avisa. */
  const alDespachar = () => {
    creandoOrden = true;
    return async (/** @type {any} */ { result, update }) => {
      await update({ reset: false });
      creandoOrden = false;
      if (result?.type === 'success') {
        despachando = null;
        avisar(result.data?.hecho ?? 'Orden creada.', { enlace: { texto: 'Ver en Programación', href: '/supervisor-noc/programacion' } });
      } else if (result?.type === 'failure') {
        avisar(result.data?.error ?? 'No se pudo crear la orden.', { tono: 'error' });
      }
    };
  };

  // ---------------------------------------------------------------------
  //  FILTRAR, CONTAR Y PAGINAR LOS CASOS  --  18/10/2026
  //  Lo hace el backend: llegan de a `tope`, y filtrar o contar en el
  //  navegador solo vería esos. Acá vive lo que se escribe y a qué URL ir.
  // ---------------------------------------------------------------------

  /** Lo que se está escribiendo. La URL manda; esto es solo el campo. El
   *  valor inicial se lee una vez a propósito: después lo sigue el efecto. */
  let busqueda = $state(untrack(() => data.filtro?.q ?? ''));
  /** @type {HTMLInputElement | undefined} */
  let campoBusqueda = $state();
  /** @type {HTMLDivElement | undefined} */
  let lista = $state();

  //  Si la URL cambia por otro lado (Limpiar, atrás del navegador), el campo
  //  la sigue. Mientras se escribe NO: la respuesta de lo que se tipeó hace
  //  medio segundo pisaría la letra que se acaba de agregar.
  $effect(() => {
    const q = data.filtro?.q ?? '';
    if (document.activeElement !== campoBusqueda) busqueda = q;
  });

  //  Página nueva, lista desde arriba: el contenedor se desplaza por su
  //  cuenta y conservaría la posición de la página anterior.
  $effect(() => {
    void data.pagina;
    if (lista) lista.scrollTop = 0;
  });

  const hayFiltro = $derived(Boolean(data.filtro?.q || data.filtro?.asunto));

  const pag = $derived(paginacion(data.total ?? 0, data.pagina ?? 1, data.tope || 25));

  /**
   * La URL de la lista con lo que cambia. Conserva lo demás (`ficha`, `dia`)
   * y vuelve a la página 1 salvo que se pida otra: filtrar estando en la 3
   * puede dejar esa página sin filas.
   * @param {{ q?: string, asunto?: string, pagina?: number, ficha?: boolean, conTecnico?: boolean, dia?: string }} cambio
   */
  function enlace(cambio) {
    const p = new URLSearchParams(page.url.searchParams);
    const fijar = (/** @type {string} */ k, /** @type {string} */ v) =>
      v ? p.set(k, v) : p.delete(k);
    if ('q' in cambio) fijar('q', (cambio.q ?? '').trim());
    if ('asunto' in cambio) fijar('asunto', cambio.asunto ?? '');
    if ('ficha' in cambio) fijar('ficha', cambio.ficha ? '1' : '');
    if ('conTecnico' in cambio) fijar('con_tecnico', cambio.conTecnico ? '1' : '');
    if ('dia' in cambio) fijar('dia', cambio.dia ?? '');
    fijar('pagina', cambio.pagina && cambio.pagina > 1 ? String(cambio.pagina) : '');
    const s = p.toString();
    return s ? `?${s}` : page.url.pathname;
  }

  /** @param {Parameters<typeof enlace>[0]} cambio */
  function filtrar(cambio) {
    goto(enlace(cambio), { keepFocus: true, noScroll: true, replaceState: true });
  }

  /** @type {ReturnType<typeof setTimeout> | undefined} */
  let espera;
  /** Busca cuando se deja de escribir, no en cada letra. */
  function alEscribir() {
    clearTimeout(espera);
    espera = setTimeout(() => filtrar({ q: busqueda }), 350);
  }

  /** El caso abierto en el panel. `null` = ninguno. */
  let despachando = $state(/** @type {any} */ (null));
  let plantillaElegida = $state('');

  /**
   * Las fotos que va a pedir la plantilla elegida.
   *
   * EL PEDIDO (06/11/2026): «el supervisor debe saber qué fotos pedir». La
   * línea de abajo decía desde siempre «define qué anota y qué fotos saca el
   * técnico» -- y no las nombraba, así que para saber cuáles había que abrir
   * Plantillas en otra pestaña.
   *
   * VAN CON SU TÍTULO Y SI SON OBLIGATORIAS, no como un número: «3 fotos» no
   * deja ver que una es la medición de potencia que este trabajo no necesita,
   * y ese es el caso que lo originó. Con los títulos a la vista, quien
   * despacha se da cuenta ahí mismo de que eligió la plantilla equivocada.
   */
  const fotosDeLaPlantilla = $derived(
    (data.plantillas ?? []).find((/** @type {any} */ p) => p.id === plantillaElegida)
      ?.fotos ?? []
  );

  /**
   * LAS DEL BACKEND, NO OTRAS (19/10/2026). Decía «normal / Alta / Urgente», y
   * la orden solo acepta alta, media y baja (campo/serializers.py): elegir
   * «Urgente» hacía fallar el despacho entero con un 400.
   */
  const PRIORIDADES = [
    { id: 'alta', texto: 'Alta' },
    { id: 'media', texto: 'Media' },
    { id: 'baja', texto: 'Baja' }
  ];

  /**
   * QUÉ CREARÍA EL SUPERVISOR  --  23/10/2026 (Fase 2.3, entrega 1).
   *
   * Antes de que el Supervisor cree órdenes solo, se ve qué crearía con esta
   * cola y por qué no las otras. Se pide al tocar el botón, no al abrir: la
   * pantalla no tiene por qué pagarla cada vez.
   */
  let ordenesPrevia = $state(/** @type {any} */ (null));
  let cargandoOrdenes = $state(false);
  let errorOrdenes = $state('');
  async function verOrdenesPrevia() {
    cargandoOrdenes = true;
    errorOrdenes = '';
    try {
      const r = await fetch('/supervisor-noc/despacho/vista-previa');
      const d = await r.json();
      if (!r.ok) throw new Error(d?.error || 'No se pudo calcular.');
      ordenesPrevia = d;
    } catch (/** @type {any} */ e) {
      ordenesPrevia = null;
      errorOrdenes = e?.message || 'No se pudo calcular.';
    } finally {
      cargandoOrdenes = false;
    }
  }
  /** @param {string} id */
  const textoDePrioridad = (id) => PRIORIDADES.find((p) => p.id === id)?.texto ?? id;

  /**
   * SIMULAR EL DÍA  --  24/10/2026.
   *
   * El ensayo entero: las cuadrillas que armaría, las órdenes que crearía y cómo
   * las repartiría entre ellas, sin guardar nada. Pedido del usuario: ver la
   * carga de cada cuadrilla y si la labor cuadra antes de dejarlo hacerlo solo.
   */
  let simulacion = $state(/** @type {any} */ (null));
  let simulando = $state(false);
  let errorSimulacion = $state('');
  //  El día con que abre la página; después lo cambia quien simula.
  let diaSimulado = $state(untrack(() => data.dia));
  async function simularElDia() {
    simulando = true;
    errorSimulacion = '';
    try {
      const r = await fetch(`/supervisor-noc/despacho/simulacion?fecha=${encodeURIComponent(diaSimulado)}`);
      const d = await r.json();
      if (!r.ok) throw new Error(d?.error || 'No se pudo simular.');
      simulacion = d;
    } catch (/** @type {any} */ e) {
      simulacion = null;
      errorSimulacion = e?.message || 'No se pudo simular.';
    } finally {
      simulando = false;
    }
  }
  /** Lo que quedó afuera, con el título que dice por qué y cómo se arregla. */
  const FUERA = [
    ['sin_cuadrilla', 'Sin cuadrilla de su labor ese día'],
    ['sobrantes', 'No entraron por el tope de la cuadrilla'],
    ['sin_zona', 'Sin zona: su barrio no está en ninguna'],
    ['sin_clasificar', 'Su plantilla no tiene labor'],
    ['otro_dia', 'Programadas para otro día']
  ];
  let prioridadElegida = $state('media');

  /**
   * DE DÓNDE SALIÓ CADA VALOR PROPUESTO (19/10/2026). Plantilla, fecha y
   * prioridad vienen elegidas según lo que vio el Supervisor; quien despacha
   * tiene que poder ver por qué, para confirmarlas o cambiarlas. Vacío = no se
   * propuso nada y el campo se llena a mano.
   */
  let propuesto = $state({ plantilla: '', fecha: '', prioridad: '' });
  /** Por qué no viene ninguna plantilla elegida (21/10/2026): lo dice el backend. */
  let sinPlantillaPorque = $state('');
  /** Si la persona eligió la fecha a mano, cambiar la plantilla no la pisa. */
  let fechaTocada = $state(false);

  /**
   * Qué plantillas coinciden con la labor sugerida.
   *
   * Se marcan, no se filtran: la sugerencia puede estar equivocada y esconder
   * el resto obligaría a cerrar el panel para corregirla.
   */
  function sugeridas(labor) {
    if (!labor) return [];
    return (data.plantillas ?? []).filter((p) => p.labor === labor);
  }

  /** Mientras se trae la ficha del caso abierto. */
  let cargandoFicha = $state(false);

  /** El barrio del formulario y el día: con eso se sabe a qué zona va. */
  let barrio = $state('');
  let fecha = $state('');
  /** Lo que dice el backend: la zona, qué cuadrillas la cubren ese día. */
  let cobertura = $state(/** @type {any} */ (null));
  let jornadaElegida = $state('');
  let tecnicoElegido = $state('');

  /** La labor de la plantilla elegida: decide qué cuadrilla puede tomarla. */
  const laborElegida = $derived(
    (data.plantillas ?? []).find((p) => p.id === plantillaElegida)?.labor ?? ''
  );

  /**
   * A QUÉ ZONA VA Y QUIÉN LA CUBRE (13/10/2026). El supervisor tiene que verlo
   * al despachar, no enterarse en el reparto. La regla es la del reparto, en el
   * backend: barrio -> zona -> las cuadrillas de ese día con esa labor.
   * Si el barrio no está en ninguna zona, trae los parecidos para sugerir.
   */
  async function revisarCobertura() {
    const q = barrio.trim();
    const pedido = `${q}|${fecha}|${laborElegida}`;
    if (!q) { cobertura = null; jornadaElegida = ''; return; }
    try {
      const p = new URLSearchParams({ barrio: q, fecha, labor: laborElegida });
      const r = await fetch(`/supervisor-noc/despacho/cobertura?${p}`);
      //  Si mientras tanto cambió el barrio, la plantilla o el día, esta
      //  respuesta ya no corresponde.
      if (!r.ok || pedido !== `${barrio.trim()}|${fecha}|${laborElegida}`) return;
      cobertura = await r.json();
      //  Viene elegida SOLO si hay UNA cuadrilla de esa zona con esa labor:
      //  entre dos, la diferencia la sabe quien despacha.
      const sirven = (cobertura.jornadas ?? []).filter((j) => j.coincide_labor);
      jornadaElegida = sirven.length === 1 ? sirven[0].jornada : '';
      tecnicoElegido = '';
    } catch {
      cobertura = null;
    }
  }

  /** La cuadrilla elegida, para ofrecer su gente. */
  const jornada = $derived(
    (cobertura?.jornadas ?? []).find((j) => j.jornada === jornadaElegida) ?? null
  );

  /** @param {string | undefined} labor */
  function preelegir(labor) {
    const coinciden = sugeridas(labor);
    //  Si hay UNA sola de esa labor, viene elegida. Con dos o más no se elige
    //  por el usuario: entre dos plantillas de la misma labor la diferencia la
    //  sabe él, no nosotros. (Desde el 19/10 primero se mira el ASUNTO del
    //  ticket, que sí distingue entre plantillas de la misma labor.)
    if (coinciden.length === 1) {
      plantillaElegida = coinciden[0].id;
      propuesto.plantilla = 'por la labor que sugiere el Supervisor';
    }
  }

  /**
   * «Para cuándo» = creación del ticket + plazo de la plantilla elegida (si ya
   * pasó, hoy). Se recalcula al cambiar la plantilla, salvo que la persona
   * haya puesto la fecha a mano.
   */
  function proponerFecha() {
    if (fechaTocada || !despachando) return;
    const plazo = (data.plantillas ?? []).find((p) => p.id === plantillaElegida)?.plazo_dias;
    const sugerida = fechaSugerida(despachando.creado, plazo);
    fecha = sugerida;
    propuesto.fecha = sugerida
      ? `creación del ticket + ${plazo} ${plazo === 1 ? 'día' : 'días'} de plazo de la plantilla`
      : '';
  }

  function alCambiarPlantilla() {
    propuesto.plantilla = '';
    proponerFecha();
    revisarCobertura();
  }

  /**
   * Abre el caso y TRAE SU FICHA (13/10/2026): el barrio del ISP, la lectura
   * del Supervisor y la descripción del ticket tapada. Antes había que
   * escribir a mano lo que el sistema ya sabía, o apretar «Traer el
   * diagnóstico» para los veinticinco casos. Si la ficha no llega, el
   * formulario queda como antes y se llena a mano.
   */
  async function abrir(caso) {
    despachando = caso;
    barrio = caso?.localidad || '';
    cobertura = null;
    jornadaElegida = '';
    tecnicoElegido = '';
    plantillaElegida = '';
    fecha = '';
    fechaTocada = false;
    prioridadElegida = 'media';
    propuesto = { plantilla: '', fecha: '', prioridad: '' };
    sinPlantillaPorque = '';
    preelegir(caso?.sugerencia?.labor);
    cargandoFicha = true;
    try {
      const r = await fetch(`/supervisor-noc/despacho/ficha/${encodeURIComponent(caso.id)}`);
      //  Si mientras tanto se abrió OTRO caso, esta ficha ya no le corresponde.
      if (!r.ok || despachando?.id !== caso.id) return;
      const ficha = await r.json();
      despachando = {
        ...despachando,
        localidad: ficha.localidad || despachando.localidad || '',
        sugerencia: despachando.sugerencia ?? ficha.sugerencia ?? null,
        lectura: ficha.lectura ?? null,
        descripcion: ficha.descripcion ?? '',
        creado: ficha.creado ?? despachando.creado ?? null
      };
      //  LA PLANTILLA LA DECIDE EL BACKEND (21/10/2026), con UNA regla
      //  (`plantilla_del_caso`): la misma que usa el Supervisor cuando crea la
      //  orden solo. Lo de arriba (`preelegir` al abrir) es solo para no
      //  esperar la ficha; si la regla dice otra cosa, gana la regla.
      const sugerida = ficha.plantilla_sugerida;
      if (sugerida && (data.plantillas ?? []).some((p) => p.id === sugerida)) {
        plantillaElegida = sugerida;
        propuesto.plantilla = ficha.plantilla_por === 'asunto'
          ? `por el asunto «${despachando.nombre}»`
          : 'por la labor: es la única plantilla de esa labor';
      } else if (propuesto.plantilla) {
        //  La que se eligió al abrir no es la de la regla: se suelta.
        plantillaElegida = '';
        propuesto.plantilla = '';
      }
      sinPlantillaPorque = sugerida ? '' : (ficha.plantilla_motivo ?? '');
      //  LA PRIORIDAD, con la MISMA regla que usa el Supervisor cuando crea la
      //  orden solo: el nivel del asunto, su plazo y la caída del equipo
      //  (26/10/2026) y, sin nivel, el plazo de la plantilla sugerida o la
      //  espera del ticket (23/10/2026). La calcula el backend.
      if (['alta', 'media', 'baja'].includes(ficha.prioridad_sugerida)) {
        prioridadElegida = ficha.prioridad_sugerida;
        propuesto.prioridad = 'con la misma regla con la que el Supervisor crea la orden';
      }
      proponerFecha();
      if (!barrio && despachando.localidad) barrio = despachando.localidad;
      revisarCobertura();
    } catch {
      //  Sin ficha se despacha igual, escribiendo lo que falte.
    } finally {
      if (despachando?.id === caso.id) cargandoFicha = false;
    }
  }

  /**
   * Lo que el Supervisor leyó del reclamo y recomienda, como punto de partida
   * de «Qué hay que hacer». Es una LECTURA: viene escrita para que la persona
   * la confirme o la corrija, no como un dato.
   * @param {any} lectura
   */
  function textoDeLectura(lectura) {
    if (!lectura) return '';
    const partes = [];
    if (lectura.hipotesis) partes.push(`Según el Supervisor: ${lectura.hipotesis}`);
    if (lectura.recomendacion) partes.push(`Recomienda: ${lectura.recomendacion}`);
    //  El mismo tope que el backend (2000). Un texto mas largo volveria como
    //  error al crear la orden.
    return partes.join('. ').slice(0, 2000);
  }

  const nombreDeLabor = (id) =>
    (data.labores ?? []).find((l) => l.id === id)?.texto ?? id;
</script>

<svelte:head>
  <title>Despacho a campo · Supervisor NOC</title>
  <!-- Las fuentes se sirven desde la plataforma (static/fuentes/fuentes.css,
       cargado en app.html) desde el 12/11/2026: Google no se entera de
       cada pantalla que se abre. -->
</svelte:head>

<div class="snoc">
  <!-- v2-scroll: el UNICO contenedor que se desplaza. El marco de (app) es
       `overflow:hidden`; sin esto lo que no entra en la ventana queda
       recortado y no hay forma de llegar (ver supervisor-noc/+page.svelte). -->
  <div class="v2-scroll">
    <div class="snoc-lienzo">
    <header class="snoc-encabezado">
      <div class="snoc-encabezado-texto">
        <h1 class="snoc-h1">Despacho a campo</h1>
        <p class="snoc-bajada">
          Qué casos van a una visita, y con qué plantilla. Lo que se despacha acá es lo que el ciclo
          de la madrugada reparte entre las cuadrillas.
        </p>
      </div>
      {#if !data.error}
        <!-- EL SUPERVISOR MIRA UNA VEZ POR HORA, pero solo si la empresa le
             delegó «Revisar solo». Sin esa delegación espera a que alguien lo
             despierte, y esta pantalla queda vacía sin que nada lo explique.
             Esto lo despierta: no ejecuta nada, solo deja propuestas para que
             una persona las lea. -->
        <form class="snoc-encabezado-acciones" method="POST" action="?/ciclo" use:enhance={alBuscar}>
          <button class="snoc-btn snoc-btn-primario" type="submit" disabled={buscando}>
            {buscando ? 'Buscando…' : 'Buscar casos que necesiten visita'}
          </button>
        </form>
      {/if}
    </header>
    {#if form?.de === 'ciclo'}
      <p class="snoc-recuadro {form.error ? 'snoc-recuadro-error' : 'snoc-recuadro-ok'}" role="status">
        {form.error ?? form.hecho}
      </p>
    {/if}

    {#if data.error}
      <p class="snoc-recuadro snoc-recuadro-error">
        No se pudieron leer los casos ni las plantillas. Si otras pantallas tampoco cargan, es el backend.
      </p>
    {:else}
      {#if data.plantillasSinClasificar}
        <!-- Sin labor, el ciclo de la madrugada no las reparte. Se avisa acá
             —donde se despacha— y no solo en la pantalla de configuración. -->
        <p class="snoc-recuadro snoc-recuadro-alerta">
          <strong>{data.plantillasSinClasificar}
          {data.plantillasSinClasificar === 1 ? 'plantilla' : 'plantillas'} sin labor.</strong>
          Las órdenes que salgan con ellas no entran al reparto automático; se clasifican en
          <a href="/supervisor-noc/cuadrillas">Cuadrillas</a>.
        </p>
      {/if}

      <Pestanas
        bind:activa={pestana}
        etiqueta="Secciones de Despacho"
        pestanas={[
          { id: 'casos', texto: 'Casos para despachar', n: data.sinAprobados ? null : data.totalSinFiltro },
          { id: 'simular', texto: 'Simular el día' },
          { id: 'crearia', texto: 'Lo que crearía el Supervisor' },
          { id: 'jornada', texto: 'Cómo quedaría la jornada' }
        ]}
      />

      {#if pestana === 'casos'}
      <section class="snoc-panel" style="gap:var(--snoc-sm);">
        <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
          <div class="snoc-pila-xs">
            <h2 class="snoc-h2">
              Casos abiertos
              {#if !data.sinAprobados}
                <!-- EL NÚMERO ES EL DE TODA LA COLA, no el de la página. Con
                     filtro dice los dos: «3 de 41». -->
                <span class="snoc-chip-conteo">
                  {#if hayFiltro}{data.total} de {data.totalSinFiltro}{:else}{data.total}{/if}
                </span>
              {/if}
            </h2>
            <p class="snoc-body-sm snoc-secundario">
              Solo los que ya aprobaste en <a href="/supervisor-noc">Pendientes por
              revisión</a>. Nada sale a campo sin pasar por ahí.
            </p>
            <!-- LO QUE YA TIENE TÉCNICO ESTÁ EN PROGRAMACIÓN (28/10/2026):
                 Despacho es lo que falta. Se cuenta, y se puede volver a ver
                 acá para una segunda visita al mismo caso. -->
            {#if data.conTecnico}
              <p class="snoc-body-sm snoc-secundario">
                {#if data.mostrandoConTecnico}
                  Se ven también {data.conTecnico}
                  {data.conTecnico === 1 ? 'caso que ya tiene técnico' : 'casos que ya tienen técnico'}.
                  <a href={enlace({ conTecnico: false })}>Ocultarlos</a>
                {:else}
                  {data.conTecnico}
                  {data.conTecnico === 1 ? 'caso ya tiene técnico' : 'casos ya tienen técnico'}: están en
                  <a href="/supervisor-noc/programacion">Programación</a>.
                  <a href={enlace({ conTecnico: true })}>Mostrarlos acá</a> (para una segunda visita).
                {/if}
              </p>
            {/if}
          </div>
          <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap;">
            {#if !data.conFicha && (data.casos ?? []).length}
              <!-- La ficha cuesta una llamada al motor POR CASO, que a su vez
                   habla con WispHub y SmartOLT. Se pide, no viene sola, y
                   solo para la página que se está mirando. -->
              <a class="snoc-btn" href={enlace({ ficha: true, pagina: data.pagina })}>
                Traer el diagnóstico de esta página
              </a>
            {/if}
          </div>
        </div>

        {#if !data.sinAprobados && data.totalSinFiltro > 0}
          <!-- EL FILTRO. Busca en lo que se ve en la fila --asunto, cliente,
               N.º de ticket o de servicio-- y nada más: buscar en la
               descripción haría salir casos por un texto que no está a la
               vista. Los asuntos son los de TODA la cola, con cuántos hay. -->
          <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap;">
            <label class="snoc-buscador">
              <span class="snoc-icono snoc-tenue" style="font-size:18px;" aria-hidden="true">search</span>
              <input
                type="search"
                class="snoc-buscador-campo"
                placeholder="Buscar asunto, cliente o N.º de ticket…"
                aria-label="Buscar en los casos abiertos"
                maxlength="100"
                bind:this={campoBusqueda}
                bind:value={busqueda}
                oninput={alEscribir}
                onkeydown={(e) => {
                  if (e.key === 'Enter') { clearTimeout(espera); filtrar({ q: busqueda }); }
                }}
              />
            </label>
            <select
              class="snoc-select"
              aria-label="Filtrar por asunto"
              value={data.filtro?.asunto ?? ''}
              onchange={(e) => filtrar({ asunto: e.currentTarget.value })}
            >
              <option value="">Todos los asuntos ({data.totalSinFiltro})</option>
              {#each data.asuntos ?? [] as a (a.asunto)}
                <option value={a.asunto}>{a.asunto} ({a.n})</option>
              {/each}
            </select>
            {#if hayFiltro}
              <button
                class="snoc-pildora"
                type="button"
                onclick={() => { busqueda = ''; clearTimeout(espera); filtrar({ q: '', asunto: '' }); }}
              >
                Limpiar filtro
              </button>
            {/if}
          </div>
        {/if}

        {#if (data.casos ?? []).length === 0 && hayFiltro}
          <p class="snoc-body-sm snoc-secundario">
            Ningún caso coincide con el filtro. El N.º de ticket se busca completo.
          </p>
        {:else if (data.casos ?? []).length === 0}
          <!-- VACÍO NO ES UN ERROR, y las dos razones de estar vacío se
               dibujan distinto: una dice qué hacer, la otra que algo falló. -->
          {#if data.sinAprobados}
            <p class="snoc-body-sm snoc-secundario">
              Todavía no aprobaste ningún caso para visita. El Supervisor propone los que
              su diagnóstico sostiene —equipo caído por fibra, señal débil, varios del
              mismo puerto— y aparecen en
              <a href="/supervisor-noc">Pendientes por revisión</a>. Lo que aceptes ahí
              llega acá.
            </p>
            <p class="snoc-body-sm snoc-secundario">
              Con <strong>Buscar casos que necesiten visita</strong> lo hacés mirar ahora,
              sin esperar a su ronda de cada hora.
            </p>
          {:else}
            <p class="snoc-body-sm snoc-secundario">
              No hay casos abiertos entre los aprobados. Nada que despachar.
            </p>
          {/if}
        {:else}
          <!-- LA LISTA SE DESPLAZA POR SU CUENTA (18/10/2026): con la página
               entera desplazándose, despachar el caso 20 dejaba la jornada y
               el filtro a una pantalla de distancia. La cabecera queda fija. -->
          <div class="snoc-tabla-caja snoc-despacho-lista" bind:this={lista}>
            <table class="snoc-tabla">
              <thead>
                <tr>
                  <th scope="col">Asunto</th>
                  <th scope="col">N.º ticket</th>
                  <th scope="col">Cliente</th>
                  <th scope="col">Qué sugiere el Supervisor</th>
                  <th scope="col">Orden existente</th>
                  <th scope="col"><span class="snoc-solo-lector">Acción</span></th>
                </tr>
              </thead>
              <tbody>
                {#each data.casos as c (c.id)}
                  <tr class={despachando?.id === c.id ? 'snoc-fila-elegida' : ''}>
                    <td>
                      <div class="snoc-pila-xs" style="min-width:0;">
                        <span class="snoc-body">{c.nombre}</span>
                        <span class="snoc-body-sm snoc-secundario">
                          {c.estado}{c.prioridad ? ` · ${c.prioridad}` : ''}
                          {#if c.servicio}· servicio {c.servicio}{/if}
                        </span>

                      </div>
                    </td>
                    <td class="snoc-mono" style="white-space:nowrap;">
                      {#if c.ticket}#{c.ticket}{:else}<span class="snoc-tenue">—</span>{/if}
                    </td>
                    <td class="snoc-body-sm">
                      {#if c.cliente}{c.cliente}{:else}<span class="snoc-tenue">Sin nombre</span>{/if}
                    </td>
                    <td class="snoc-body-sm" style="max-width:280px;">
                      {#if c.sugerencia}
                        {#if c.sugerencia.labor === 'no_requiere_visita'}
                          <span class="snoc-insignia snoc-insignia-ok">No requiere visita</span>
                        {:else if c.sugerencia.labor}
                          <span class="snoc-insignia snoc-insignia-secundaria-suave">
                            {nombreDeLabor(c.sugerencia.labor)}{c.sugerencia.verificada ? '' : ' · sin verificar'}
                          </span>
                        {:else}
                          <span class="snoc-insignia">Sin concluir</span>
                        {/if}
                        <div class="snoc-secundario" style="margin-top:3px;">{c.sugerencia.porque}</div>
                      {:else}
                        <span class="snoc-tenue">—</span>
                      {/if}
                    </td>
                    <td class="snoc-body-sm">
                      <!-- No bloquea: una segunda visita al mismo caso es
                           legítima. Pero tiene que verse ANTES. -->
                      {#if c.orden_activa}
                        <span class="snoc-insignia {c.orden_activa_tecnico ? 'snoc-insignia-ok' : 'snoc-insignia-alerta'}">
                          #{c.orden_activa} · {c.orden_activa_tecnico ? `asignada a ${c.orden_activa_tecnico}` : 'sin asignar'}
                        </span>
                      {:else}
                        <span class="snoc-tenue">—</span>
                      {/if}
                    </td>
                    <td style="text-align:right;">
                      <button class="snoc-btn snoc-btn-primario" type="button" onclick={() => abrir(c)}>
                        Despachar
                      </button>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>

          <!-- PAGINACIÓN. Son enlaces y no botones: la página vive en la URL,
               así que se puede copiar y volver atrás. -->
          <div class="snoc-paginacion">
            <span class="snoc-mono-sm snoc-tenue">
              Mostrando {pag.desde} a {pag.hasta} de {pag.total} caso{pag.total === 1 ? '' : 's'}
            </span>
            {#if pag.paginas > 1}
              <nav class="snoc-paginacion-botones" aria-label="Páginas de casos">
                {#if pag.actual > 1}
                  <a class="snoc-pildora" href={enlace({ pagina: pag.actual - 1 })}
                     data-sveltekit-noscroll>Anterior</a>
                {:else}
                  <span class="snoc-pildora snoc-pildora-apagada" aria-disabled="true">Anterior</span>
                {/if}
                {#each pag.ventana as n, i (i)}
                  {#if n === null}
                    <span class="snoc-paginacion-hueco" aria-hidden="true">…</span>
                  {:else}
                    <a
                      class="snoc-pildora {n === pag.actual ? 'snoc-pildora-activa' : ''}"
                      href={enlace({ pagina: n })}
                      data-sveltekit-noscroll
                      aria-current={n === pag.actual ? 'page' : undefined}
                      aria-label="Página {n}"
                    >{n}</a>
                  {/if}
                {/each}
                {#if pag.actual < pag.paginas}
                  <a class="snoc-pildora" href={enlace({ pagina: pag.actual + 1 })}
                     data-sveltekit-noscroll>Siguiente</a>
                {:else}
                  <span class="snoc-pildora snoc-pildora-apagada" aria-disabled="true">Siguiente</span>
                {/if}
              </nav>
            {/if}
          </div>
        {/if}
      </section>
      {:else if pestana === 'simular'}
      <!-- SIMULAR EL DÍA (24/10/2026): ver `simularElDia`. -->
      <section class="snoc-panel" style="gap:var(--snoc-sm);">
        <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
          <div class="snoc-pila-xs" style="min-width:0;">
            <h2 class="snoc-h2">Simular el día</h2>
            <p class="snoc-body-sm snoc-secundario">
              Las cuadrillas que armaría el Supervisor, las órdenes que crearía y a quién se
              las daría. <strong>No guarda nada.</strong>
            </p>
          </div>
          <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
            <label class="snoc-fila snoc-body-sm" for="dia-simulado"><span class="snoc-secundario">Día a simular</span></label>
            <input id="dia-simulado" class="snoc-campo" style="width:auto;" type="date" bind:value={diaSimulado} />
            <button class="snoc-btn snoc-btn-primario" type="button" onclick={simularElDia} disabled={simulando}>
              {simulando ? 'Simulando…' : 'Simular el día'}
            </button>
          </div>
        </div>
        {#if errorSimulacion}
          <p class="snoc-aviso snoc-error-txt">{errorSimulacion}</p>
        {/if}
        {#if simulacion}
          {#if !simulacion.trabaja}
            <!-- Un día que no se trabaja igual muestra lo armado a mano: publicar
                 le da trabajo (auditoría del 24/10/2026). -->
            <p class="snoc-aviso">
              {simulacion.porque}
              {#if simulacion.cuadrillas.length}Se muestra solo lo que ya estaba armado para ese día.{/if}
            </p>
          {/if}
          {#if simulacion.trabaja || simulacion.cuadrillas.length}
            {#if simulacion.sin_crear_porque}
              <p class="snoc-aviso">{simulacion.sin_crear_porque}</p>
            {/if}
            <p class="snoc-body-sm">
              Repartiría {simulacion.cuentas.repartidas}:
              {simulacion.cuentas.repartidas_nuevas} nuevas y {simulacion.cuentas.repartidas_existentes} que ya esperaban
              · {simulacion.cuentas.afuera} quedan afuera
              · no crearía {simulacion.cuentas.no_se_crearian}
              {#if simulacion.cuentas.nuevas_para_otro_dia}· {simulacion.cuentas.nuevas_para_otro_dia} salen otro día{/if}
              {#if simulacion.cuentas.a_mano || simulacion.cuentas.empezadas}
                · no se mueven: {simulacion.cuentas.a_mano} asignadas a mano y {simulacion.cuentas.empezadas} ya empezadas
              {/if}
            </p>
            <div style="display:grid; grid-template-columns:repeat(auto-fit, minmax(min(100%, 300px), 1fr)); gap:var(--snoc-sm);">
              {#each simulacion.cuadrillas as c (c.cuadrilla)}
                <div class="snoc-tarjeta snoc-pila-xs" style="min-width:0; justify-content:flex-start;">
                  <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-xs);">
                    <strong>{c.cuadrilla}</strong>
                    <span class="snoc-mono">
                      {c.carga} de {c.tope}{#if c.carga >= c.tope} · llena{:else if c.carga === 0} · sin trabajo{/if}
                    </span>
                    {#if c.ya_tiene}
                      <!-- Lo asignado a mano o ya empezado no cuenta para el tope
                           (el reparto no lo mueve), pero es trabajo de esa gente. -->
                      <span class="snoc-body-sm snoc-secundario">
                        además ya {c.ya_tiene === 1 ? 'tiene 1 orden' : `tiene ${c.ya_tiene} órdenes`} a mano o empezadas
                      </span>
                    {/if}
                  </div>
                  <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
                    {#if c.labor}<span class="snoc-tag">{c.labor}</span>{/if}
                    {#if c.apoyo}<span class="snoc-tag">Apoyo: {c.apoyo}</span>{/if}
                    {#each c.zonas as z (z)}<span class="snoc-body-sm snoc-secundario">{z}</span>{/each}
                  </div>
                  <p class="snoc-body-sm snoc-secundario">
                    {c.lider || 'Sin líder'}{#if c.gente.length} · {c.gente.map((/** @type {any} */ g) => g.nombre).join(', ')}{/if}
                    <br />{c.que_haria}
                  </p>
                  {#each c.ordenes as o, i (i)}
                    <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap; border-top:1px solid var(--snoc-outline-variant); padding-top:var(--snoc-xs);">
                      <span class="snoc-mono">#{o.ticket || o.orden}</span>
                      <span style="min-width:0;">{o.asunto || o.plantilla}</span>
                      <span class="snoc-body-sm">{textoDePrioridad(o.prioridad)}</span>
                      <span class="snoc-body-sm snoc-secundario">
                        {o.barrio || ''}{o.barrio_de === 'ticket' ? ' · según el ticket' : ''}{o.llamar_al_cliente ? ' · llamar al cliente' : ''}{o.nueva ? ' · nueva' : ''}
                      </span>
                    </div>
                  {/each}
                </div>
              {/each}
            </div>
            {#each FUERA as [clave, titulo] (clave)}
              {#if simulacion.fuera[clave]?.length}
                <span class="snoc-label">{titulo} ({simulacion.fuera[clave].length})</span>
                {#each simulacion.fuera[clave] as o, i (i)}
                  <p class="snoc-body-sm">
                    <span class="snoc-mono">#{o.ticket || o.orden}</span> {o.asunto || o.plantilla}
                    · {textoDePrioridad(o.prioridad)}
                    {#if clave === 'sin_cuadrilla'}· nadie de «{o.labor}» cubre {o.zona || o.barrio}{:else if o.barrio}· {o.barrio}{/if}
                  </p>
                {/each}
              {/if}
            {/each}
            {#if simulacion.no_salen.length}
              <span class="snoc-label">No salen ({simulacion.no_salen.length})</span>
              {#each simulacion.no_salen as n (n.cuadrilla)}
                <p class="snoc-body-sm">{n.cuadrilla}: {n.porque}</p>
              {/each}
            {/if}
          {/if}
        {/if}
      </section>

      {:else if pestana === 'crearia'}
      <!-- LO QUE CREARÍA EL SUPERVISOR (23/10/2026): ver `verOrdenesPrevia`. -->
      <section class="snoc-panel" style="gap:var(--snoc-sm);">
        <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
          <div class="snoc-pila-xs">
            <h2 class="snoc-h2">Lo que crearía el Supervisor</h2>
            <p class="snoc-body-sm snoc-secundario">
              Las órdenes que crearía ahora con esta cola, y por qué no las otras.
              <strong>No crea nada.</strong>
            </p>
          </div>
          <button class="snoc-btn snoc-btn-primario" type="button" onclick={verOrdenesPrevia} disabled={cargandoOrdenes}>
            {cargandoOrdenes ? 'Calculando…' : 'Ver qué crearía el Supervisor'}
          </button>
        </div>
        {#if errorOrdenes}
          <p class="snoc-aviso snoc-error-txt">{errorOrdenes}</p>
        {/if}
        {#if ordenesPrevia}
          {#if ordenesPrevia.porque}
            <p class="snoc-aviso">{ordenesPrevia.porque}</p>
          {/if}
          <p class="snoc-body-sm">
            Crearía {ordenesPrevia.crear.length} · no crearía {ordenesPrevia.no_se_crea.length}
            {#if ordenesPrevia.atadas.length}· atadas a un corte de red {ordenesPrevia.atadas.length}{/if}
            {#if ordenesPrevia.hora_de_corte}· hora de corte {ordenesPrevia.hora_de_corte}{/if}
          </p>
          <!-- Los totales (27/10/2026): lo que daba el comando `informe_de_despacho`,
               para verificarlo desde acá sin contar filas. -->
          {#if ordenesPrevia.crear.length}
            {#each textoDeLosTotales(totalesDeLoQueCrearia(ordenesPrevia.crear)) as linea (linea)}
              <p class="snoc-body-sm snoc-secundario">{linea}</p>
            {/each}
            <div style="overflow-x:auto;">
              <table class="snoc-tabla">
                <thead>
                  <tr>
                    <th>Ticket</th><th>Asunto</th><th>Plantilla</th><th>Prioridad</th>
                    <th>Para</th><th>Dónde</th>
                  </tr>
                </thead>
                <tbody>
                  {#each ordenesPrevia.crear as f (f.caso)}
                    <tr>
                      <td class="snoc-mono">#{f.ticket}</td>
                      <td>{f.asunto}</td>
                      <td>
                        {f.plantilla}
                        <span class="snoc-body-sm snoc-secundario">
                          · {f.por === 'asunto' ? 'por el asunto' : 'por la labor'}
                        </span>
                      </td>
                      <td>
                        {textoDePrioridad(f.prioridad)}
                        <!-- El nivel del asunto (26/10/2026): de ahí arranca la prioridad. -->
                        {#if f.nivel}<span class="snoc-body-sm snoc-secundario">· {f.nivel_nombre || f.nivel}</span>{/if}
                        {#if f.equipo_caido}<span class="snoc-body-sm snoc-secundario">· equipo caído</span>{/if}
                      </td>
                      <td>{f.para || '—'}</td>
                      <td>
                        <!-- «Según el ticket» (25/10/2026): el Supervisor sacó el barrio
                             del texto del ticket, no de la ficha del cliente. -->
                        {f.barrio ? `${f.barrio} (${f.zona})` : ''}
                        {#if f.barrio_de === 'ticket'}· según el ticket{/if}
                        {#if f.llamar_al_cliente}{f.barrio ? '· llamar al cliente' : 'Llamar al cliente para ubicarlo'}{/if}
                        {#if f.corte_de_red}· corte de red{/if}
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}
          {#if ordenesPrevia.no_se_crea.length}
            <span class="snoc-label">No las crearía ({ordenesPrevia.no_se_crea.length})</span>
            <div style="overflow-x:auto;">
              <table class="snoc-tabla">
                <thead><tr><th>Ticket</th><th>Asunto</th><th>Por qué</th></tr></thead>
                <tbody>
                  {#each ordenesPrevia.no_se_crea as f (f.caso)}
                    <tr>
                      <td class="snoc-mono">#{f.ticket}</td>
                      <td>{f.asunto}</td>
                      <td>{f.detalle}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}
          {#if ordenesPrevia.atadas.length}
            <span class="snoc-label">
              Atadas a un corte de red ({ordenesPrevia.atadas.length}): van con la orden de otro
              caso del mismo puerto
            </span>
            {#each ordenesPrevia.atadas as f (f.caso)}
              <p class="snoc-body-sm">
                <span class="snoc-mono">#{f.ticket}</span> {f.asunto} → con el
                <span class="snoc-mono">#{f.a_ticket}</span>
              </p>
            {/each}
          {/if}
        {/if}
      </section>

      {:else}
      <!--
        COMO QUEDARIA LA JORNADA  --  13/10/2026
        ========================================
        El reparto ya existia y nadie lo veia desde aca. Ordena por lo que ya
        VENCIO, despues por la prioridad y lo que vence antes (23/10/2026), y
        respeta las zonas de cada cuadrilla. No publica nada: lo que se ve es una propuesta, y una
        persona decide.

        LO QUE NO ENTRO SE MUESTRA JUNTO A LO QUE SI, y no escondido: una
        jornada que reparte veinte ordenes y deja ocho afuera sin decirlo
        parece completa. El motivo de cada grupo es distinto y lleva a
        acciones distintas -- una zona sin mapear se arregla en Cuadrillas, un
        sobrante se arregla subiendo el tope o agregando gente.
      -->
      <section class="snoc-panel" style="gap:var(--snoc-sm);">
        <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
          <div class="snoc-pila-xs">
            <h2 class="snoc-h2">Cómo quedaría la jornada</h2>
            <p class="snoc-body-sm snoc-secundario">
              Del {data.dia}. Primero lo vencido, después la prioridad y lo que
              vence antes, respetando las zonas de cada cuadrilla.
              <strong>Es una propuesta: no se publica sola.</strong>
            </p>
          </div>
          <div class="snoc-fila" style="flex-wrap:wrap;">
            <label class="snoc-fila snoc-body-sm">
              <span class="snoc-secundario">Día</span>
              <input class="snoc-campo" type="date" value={data.dia}
                     onchange={(e) => goto(enlace({ dia: e.currentTarget.value }), { keepFocus: true, noScroll: true })} />
            </label>
            <a class="snoc-btn snoc-btn-primario" href="/supervisor-noc/cuadrillas?dia={data.dia}&reparto=1">
              Ver el detalle y publicar
            </a>
          </div>
        </div>

        {#if data.repartoError}
          <div class="snoc-hueco">
            <span class="snoc-hueco-rotulo">Sin dato</span>
            <p class="snoc-hueco-motivo">{data.repartoError}</p>
          </div>
        {:else if !data.conteos || data.conteos.ordenes === 0}
          <p class="snoc-body-sm snoc-secundario">
            No hay órdenes para repartir en este día. Se crean desde acá
            abajo, despachando un caso aprobado.
          </p>
        {:else}
          <div class="snoc-fila" style="flex-wrap:wrap; gap:var(--snoc-sm);">
            {#each data.conteos.porLabor as l (l.labor)}
              <div class="snoc-kpi" style="min-width:9rem;">
                <span class="snoc-kpi-n">{l.cuadrillas}</span>
                <span class="snoc-kpi-titulo">
                  <!-- `nombreDeLabor`, no el id crudo: el resto de la
                       pantalla ya lo traduce (lineas 255, 292, 308) y aca
                       decia 'correctivo' donde todo lo demas dice
                       'Correctivo'. -->
                  {l.cuadrillas === 1 ? 'cuadrilla' : 'cuadrillas'} a {nombreDeLabor(l.labor)}
                </span>
                <span class="snoc-kpi-sub">
                  {l.ordenes} {l.ordenes === 1 ? 'orden' : 'órdenes'}
                </span>
              </div>
            {/each}
          </div>

          {#if data.conteos.aMano}
            <p class="snoc-body-sm snoc-secundario">
              {data.conteos.aMano} {data.conteos.aMano === 1 ? 'orden asignada' : 'órdenes asignadas'}
              a mano: el reparto no las mueve.
            </p>
          {/if}
          {#if data.conteos.otroDia}
            <!-- 23/10/2026: el reparto ya no reparte hoy lo programado para
                 otro día. No es una falla: salen el día que les toca. -->
            <p class="snoc-body-sm snoc-secundario">
              {data.conteos.otroDia}
              {data.conteos.otroDia === 1 ? 'programada para otro día: sale' : 'programadas para otro día: salen'}
              en el reparto de ese día.
            </p>
          {/if}
          {#if data.conteos.empezadas}
            <p class="snoc-body-sm snoc-secundario">
              {data.conteos.empezadas}
              {data.conteos.empezadas === 1
                ? 'ya empezada sigue con quien la tiene: el reparto no la mueve.'
                : 'ya empezadas siguen con quien las tiene: el reparto no las mueve.'}
            </p>
          {/if}
          {#if data.conteos.sinZona || data.conteos.sinCuadrilla || data.conteos.sobrantes || data.conteos.sinClasificar}
            <div class="dp-fallos">
              {#if data.conteos.sinZona}
                <p class="snoc-recuadro snoc-recuadro-error"><strong>{data.conteos.sinZona}</strong> sin zona mapeada — <a href="/supervisor-noc/cuadrillas?pestana=zonas">se arregla en Cuadrillas</a>.</p>
              {/if}
              {#if data.conteos.sinCuadrilla}
                <p class="snoc-recuadro snoc-recuadro-error"><strong>{data.conteos.sinCuadrilla}</strong> en zonas que hoy no cubre nadie.</p>
              {/if}
              {#if data.conteos.sobrantes}
                <p class="snoc-recuadro snoc-recuadro-alerta"><strong>{data.conteos.sobrantes}</strong> no entraron por el tope por cuadrilla.</p>
              {/if}
              {#if data.conteos.sinClasificar}
                <p class="snoc-recuadro"><strong>{data.conteos.sinClasificar}</strong> sin tipo de trabajo declarado.</p>
              {/if}
            </div>
          {/if}
        {/if}
      </section>

      {/if}
    {/if}

    </div>
  </div>
</div>

<PanelLateral
  abierto={!!despachando}
  ancho="ancho"
  antetitulo={despachando?.ticket ? `Despachar · #${despachando.ticket}` : 'Despachar'}
  titulo={despachando ? `${despachando.nombre}${despachando.cliente ? ' · ' + despachando.cliente : ''}` : ''}
  alCerrar={() => (despachando = null)}
>
  {#if despachando}

        {#if despachando.sugerencia?.porque}
          <p class="snoc-recuadro {despachando.sugerencia.labor === 'no_requiere_visita' ? 'snoc-recuadro-alerta' : 'snoc-recuadro-ok'}">
            {#if despachando.sugerencia.labor === 'no_requiere_visita'}
              <strong>La evidencia dice que no hace falta ir.</strong>
            {:else if despachando.sugerencia.labor}
              <strong>Sugerido: {nombreDeLabor(despachando.sugerencia.labor)}.</strong>
            {/if}
            {despachando.sugerencia.porque}
          </p>
        {/if}

        <form id="dp-despachar" method="POST" action="?/despachar" use:enhance={alDespachar} class="dp-pasos">
          <input type="hidden" name="case_id" value={despachando.id} />

          <span class="dp-paso">1 · Qué y con qué plantilla</span>
          <label class="snoc-campo-grupo">
            <span class="snoc-label">Con qué plantilla va</span>
            <select class="snoc-select" name="work_type_version_id"
                    bind:value={plantillaElegida} onchange={alCambiarPlantilla} required>
              <option value="">— elegí una —</option>
              {#each data.plantillas as p (p.id)}
                <option value={p.id}>
                  {p.nombre}{p.labor ? ` · ${nombreDeLabor(p.labor)}` : ' · sin labor'}
                  {p.labor && p.labor === despachando.sugerencia?.labor ? ' ← sugerida' : ''}
                </option>
              {/each}
            </select>
            <!-- Sin esta línea la pregunta no se entendía (13/10/2026: «¿por
                 qué me pregunta con qué plantilla va?»). La plantilla define
                 el formulario que llena el técnico Y qué cuadrilla la recibe. -->
            {#if propuesto.plantilla}
              <span class="snoc-body-sm snoc-primario">Propuesta {propuesto.plantilla}.</span>
            {:else if sinPlantillaPorque && !plantillaElegida}
              <span class="snoc-body-sm snoc-secundario">Sin plantilla propuesta: {sinPlantillaPorque}</span>
            {/if}
            <span class="snoc-body-sm snoc-secundario">
              Define qué anota y qué fotos saca el técnico, y por su labor, qué cuadrilla
              la recibe.
              {#if !plantillaElegida && !cargandoFicha}
                Viene elegida sola cuando el asunto del ticket está declarado en una
                plantilla, o cuando el diagnóstico sugiere una labor con una sola plantilla.
              {/if}
              Se crean y se editan en <a href="/supervisor-noc/plantillas">Plantillas</a>.
            </span>

            <!-- QUÉ FOTOS VA A PEDIR, con nombre (06/11/2026). Es lo que
                 convierte «elegir plantilla» en «indicarle al técnico qué
                 fotos tomar», que es lo que se pidió. Y es el lugar barato
                 para notar el error: si acá aparece «Medición al llegar» en
                 un cambio de contraseña del wifi, la plantilla está mal
                 elegida -- y todavía no salió nadie a la calle. -->
            {#if fotosDeLaPlantilla.length}
              <ul class="dp-fotos">
                <li class="dp-fotos-titulo">Le va a pedir estas fotos:</li>
                {#each fotosDeLaPlantilla as f (f.titulo)}
                  <li>
                    {f.titulo}{f.obligatoria ? '' : ' (opcional)'}
                  </li>
                {/each}
              </ul>
            {:else if plantillaElegida}
              <!-- Decirlo es parte de lo mismo: «no pide ninguna» es una
                   respuesta, y el silencio se lee como que no cargó. -->
              <span class="snoc-body-sm snoc-secundario">
                Esta plantilla no pide ninguna foto.
              </span>
            {/if}
          </label>

          <span class="dp-paso">2 · Cuándo</span>
          <div class="dp-par">
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Prioridad</span>
              <select class="snoc-select" name="prioridad" bind:value={prioridadElegida}
                      onchange={() => (propuesto.prioridad = '')}>
                {#each PRIORIDADES as p (p.id)}<option value={p.id}>{p.texto}</option>{/each}
              </select>
            </label>
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Para cuándo</span>
              <input class="snoc-campo" type="date" name="programada_para"
                     bind:value={fecha}
                     onchange={() => { fechaTocada = true; propuesto.fecha = ''; revisarCobertura(); }} />
            </label>
          </div>
          {#if propuesto.prioridad || propuesto.fecha}
            <!-- DE DÓNDE SALEN (19/10/2026): son propuestas, y quien despacha
                 tiene que poder ver por qué para confirmarlas o cambiarlas. -->
            <span class="snoc-body-sm snoc-primario">
              {#if propuesto.prioridad}Prioridad propuesta: {propuesto.prioridad}.{/if}
              {#if propuesto.fecha}Fecha propuesta: {propuesto.fecha}.{/if}
            </span>
          {/if}

          <!-- EL BARRIO DECIDE LA ZONA, Y LA ZONA DECIDE LA CUADRILLA. Viene
               de la ficha del cliente en el ISP; si hay que escribirlo, se
               elige de los barrios que ya están en alguna zona. -->
          <span class="dp-paso">3 · Dónde</span>
          <label class="snoc-campo-grupo">
            <span class="snoc-label">Barrio</span>
            <input class="snoc-campo" name="zona" required maxlength="128"
                   bind:value={barrio} list="barrios-conocidos" autocomplete="off"
                   onchange={revisarCobertura}
                   placeholder="Empezá a escribir y elegí de la lista" />
            <datalist id="barrios-conocidos">
              {#each data.barriosConocidos ?? [] as b (b.localidad)}
                <option value={b.localidad}>{b.zona}</option>
              {/each}
            </datalist>
          </label>

          <!-- ZONA Y CUADRILLA (13/10/2026). Lo que el supervisor tiene que
               tener claro al despachar: a qué zona va este trabajo y qué
               cuadrilla la cubre ese día con esta labor. Misma regla que el
               reparto, calculada en el backend. -->
          {#if cobertura}
            <div class="snoc-recuadro {cobertura.motivo === 'cubierta' ? 'snoc-recuadro-ok' : 'snoc-recuadro-alerta'} snoc-pila-xs">
              {#if cobertura.motivo === 'sin_zona'}
                <span class="snoc-body-sm"><strong>Este barrio no está en ninguna zona.</strong>
                  La orden se crea, pero no se reparte hasta que alguien lo agregue a una
                  zona en Cuadrillas.</span>
                {#if cobertura.parecidas?.length}
                  <span class="snoc-body-sm">¿Quisiste decir
                    {#each cobertura.parecidas as p, i (p.localidad)}
                      {i ? ' o ' : ''}<button type="button" class="snoc-pildora"
                        onclick={() => { barrio = p.localidad; revisarCobertura(); }}>
                        {p.localidad}</button> <span class="snoc-secundario">({p.zona})</span>
                    {/each}?</span>
                {/if}
              {:else if cobertura.zona}
                <span class="snoc-body">Zona: <strong>{cobertura.zona.nombre}</strong>
                  <span class="snoc-secundario">· {cobertura.fecha}</span></span>
                {#if cobertura.motivo === 'cubierta'}
                  <span class="snoc-body-sm snoc-secundario">
                    La cubre{(cobertura.jornadas.filter((j) => j.coincide_labor).length > 1) ? 'n' : ''}:
                    {cobertura.jornadas.filter((j) => j.coincide_labor).map((j) => j.cuadrilla).join(', ')}
                  </span>
                {:else if cobertura.motivo === 'otra_labor'}
                  <span class="snoc-body-sm"><strong>Ese día la cubre
                    {cobertura.jornadas.map((j) => `${j.cuadrilla} (${nombreDeLabor(j.labor)})`).join(', ')},
                    pero no en {laborElegida ? nombreDeLabor(laborElegida) : 'esta labor'}.</strong>
                    El reparto no se la va a dar: o se cambia la labor de esa jornada en
                    Cuadrillas, o se asigna a mano.</span>
                {:else}
                  <span class="snoc-body-sm"><strong>Ese día ninguna cuadrilla cubre
                    {cobertura.zona.nombre}.</strong>
                    {#if cobertura.habituales?.length}
                      La trabaja{cobertura.habituales.length > 1 ? 'n' : ''} habitualmente
                      {cobertura.habituales.map((c) => c.cuadrilla).join(', ')}: hay que armarle
                      la jornada en Cuadrillas.
                    {:else}
                      Ninguna cuadrilla la tiene entre sus zonas.
                    {/if}
                  </span>
                {/if}
              {/if}
            </div>
          {/if}

          <!-- A QUÉ CUADRILLA (opcional). Vacío = la reparte el sistema. Con
               una cuadrilla, le llega a su líder (el único con celular) como al
               publicar el reparto, y el reparto la respeta después. Se ofrecen las que
               cubren esa zona ese día; un técnico puntual, dentro de ella. -->
          <span class="dp-paso">4 · Quién</span>
          {#if !cobertura?.jornadas?.length}
            <p class="snoc-body-sm snoc-secundario" style="margin:0;">
              Sin cuadrilla para elegir: la orden queda para que la reparta el sistema.
            </p>
          {/if}
          {#if cobertura?.jornadas?.length}
            <div class="dp-par">
              <label class="snoc-campo-grupo">
                <span class="snoc-label">Cuadrilla</span>
                <select class="snoc-select" name="jornada_id" bind:value={jornadaElegida}
                        onchange={() => (tecnicoElegido = '')}>
                  <option value="">— que la reparta el sistema —</option>
                  {#each cobertura.jornadas as j (j.jornada)}
                    <option value={j.jornada}>
                      {j.cuadrilla} · {nombreDeLabor(j.labor)}{j.coincide_labor ? '' : ' (otra labor)'}
                    </option>
                  {/each}
                </select>
              </label>
              <!-- Elegir técnico solo tiene sentido si hay MÁS DE UNO con cuenta:
                   en la cuadrilla normal (un líder con celular y un auxiliar
                   sin él) la recibe el líder y no hay nada que elegir. -->
              {#if jornada && jornada.con_cuenta.length > 1}
                <label class="snoc-campo-grupo">
                  <span class="snoc-label">Técnico (opcional)</span>
                  <select class="snoc-select" name="tecnico_profile_id" bind:value={tecnicoElegido}>
                    <option value="">— toda la cuadrilla —</option>
                    {#each jornada.con_cuenta as t (t.profile)}
                      <option value={t.profile}>{t.nombre}</option>
                    {/each}
                  </select>
                </label>
              {/if}
            </div>
            {#if jornada && jornada.con_cuenta.length}
              <p class="snoc-body-sm snoc-secundario">
                La recibe: <strong>{jornada.con_cuenta.map((t) => t.nombre).join(', ')}</strong>
                {#if jornada.van_con_el?.length}
                  · va con: {jornada.van_con_el.join(', ')}
                {/if}
              </p>
            {:else if jornada}
              <p class="snoc-recuadro snoc-recuadro-error">
                {jornada.aviso ?? `${jornada.cuadrilla}: nadie la vería en un teléfono.`}
              </p>
            {/if}
          {/if}

          <span class="dp-paso">5 · Para el técnico</span>
          <label class="snoc-campo-grupo">
            <span class="snoc-label">Cómo se entra al inmueble (opcional)</span>
            <input class="snoc-campo" name="detalle_acceso" maxlength="255"
                   placeholder="Apto 302, portería pide cédula" />
          </label>
          <!-- Con la dirección sola el técnico llega al edificio, no al
               apartamento. NO se llena solo: suele estar escrito a mano en el
               ticket, y sacarlo de ahí sería que un modelo adivine en un campo
               que el técnico lee como dato. Se muestra el ticket para copiarlo. -->
          {#if despachando.descripcion}
            <details class="snoc-recuadro" open>
              <summary class="snoc-body-sm"><strong>Lo que dice el ticket</strong>
                <span class="snoc-secundario">· datos personales tapados</span></summary>
              <p class="snoc-body-sm" style="white-space:pre-wrap; margin-top:var(--snoc-xs);">
                {despachando.descripcion}
              </p>
            </details>
          {/if}

          <!-- POR QUÉ PASÓ SOLO (17/10/2026). Si el Supervisor lo pasó sin que
               nadie lo mirara, quien despacha tiene que saber con qué dato:
               una caída por LOS puede ser un equipo desenchufado, y "no se
               pudo medir" no confirma nada. Se confirma con el cliente antes
               de mandar a alguien. Vacío si lo aceptó una persona. -->
          {#if despachando.lectura?.por_que_paso}
            <p class="snoc-recuadro">
              <strong>Pasó solo a Despacho:</strong> {despachando.lectura.por_que_paso}
            </p>
          {/if}
          <!-- EL CORTE DE RED (19/10/2026), lo haya pasado el Supervisor o una
               persona: varios casos del mismo puerto son un solo trabajo. -->
          {#if despachando.lectura?.corte_de_red}
            <p class="snoc-recuadro snoc-recuadro-alerta">
              <strong>Corte de red:</strong> {despachando.lectura.corte_de_red}
            </p>
          {/if}

          <label class="snoc-campo-grupo">
            <span class="snoc-label">Qué hay que hacer</span>
            {#key despachando.lectura}
              <textarea class="snoc-campo" name="resumen" rows="3" maxlength="2000"
                        placeholder="Lo que el técnico no puede deducir">{textoDeLectura(despachando.lectura)}</textarea>
            {/key}
            {#if despachando.lectura?.hipotesis || despachando.lectura?.recomendacion}
              <span class="snoc-body-sm snoc-secundario">
                Viene de la lectura del Supervisor que se aceptó: confirmala o corregila.
              </span>
            {/if}
          </label>
          {#if cargandoFicha}
            <p class="snoc-body-sm snoc-secundario">Trayendo la ficha del caso…</p>
          {/if}

        </form>

        {#if form?.error && form?.de !== 'ciclo'}
          <p class="snoc-recuadro snoc-recuadro-error" role="alert">{form.error}</p>
        {/if}
  {/if}
  {#snippet pie()}
    <div class="snoc-fila-sep" style="flex-wrap:wrap;">
      <span class="snoc-body-sm snoc-secundario">Si el caso ya tenía una orden abierta, se avisa al crearla.</span>
      <div class="snoc-fila">
        <button class="snoc-btn" type="button" onclick={() => (despachando = null)}>Cerrar</button>
        <button class="snoc-btn snoc-btn-primario" type="submit" form="dp-despachar" disabled={creandoOrden}>
          {creandoOrden ? 'Creando…' : 'Crear la orden'}
        </button>
      </div>
    </div>
  {/snippet}
</PanelLateral>

<style>
  /*  LAS FOTOS QUE PIDE LA PLANTILLA (06/11/2026): una lista corta, legible
      de un vistazo. Si hace falta leerla con cuidado, ya es tarde: el momento
      de notar que la plantilla está mal elegida es ANTES de despachar. */
  .dp-fotos {
    list-style: none;
    margin: var(--snoc-xs) 0 0;
    padding: 0 0 0 var(--snoc-sm);
    font-size: 12px;
    color: var(--snoc-on-surface-variant, #666);
    display: grid;
    gap: 1px;
    border-left: 2px solid var(--snoc-outline-variant, #ddd);
  }
  .dp-fotos-titulo { font-weight: 600; }
  .dp-pasos { display: flex; flex-direction: column; gap: 10px; }
  .dp-paso {
    font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; font-weight: 700;
    color: var(--v2-ember-text); margin-top: 8px; padding-top: 10px; border-top: 1px solid var(--v2-line-soft);
  }
  .dp-paso:first-of-type { margin-top: 0; padding-top: 0; border-top: 0; }
  .dp-par { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr)); }
  .dp-fallos { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 220px), 1fr)); }
</style>
