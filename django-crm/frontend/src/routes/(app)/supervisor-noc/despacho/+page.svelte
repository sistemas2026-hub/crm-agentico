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
   */
  import { enhance } from '$app/forms';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { untrack } from 'svelte';
  import { paginacion } from '$lib/v2/supervisor-noc-tablero.js';
  import { fechaSugerida } from '$lib/v2/despacho-sugerencias.js';
  import '../supervisor-noc.css';

  let { data, form } = $props();

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
   * @param {{ q?: string, asunto?: string, pagina?: number, ficha?: boolean }} cambio
   */
  function enlace(cambio) {
    const p = new URLSearchParams(page.url.searchParams);
    const fijar = (/** @type {string} */ k, /** @type {string} */ v) =>
      v ? p.set(k, v) : p.delete(k);
    if ('q' in cambio) fijar('q', (cambio.q ?? '').trim());
    if ('asunto' in cambio) fijar('asunto', cambio.asunto ?? '');
    if ('ficha' in cambio) fijar('ficha', cambio.ficha ? '1' : '');
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
      //  orden solo (23/10/2026): el plazo de la plantilla sugerida y, si no
      //  tiene, la espera del ticket. La calcula el backend.
      if (['alta', 'media', 'baja'].includes(ficha.prioridad_sugerida)) {
        prioridadElegida = ficha.prioridad_sugerida;
        propuesto.prioridad = 'por el plazo de la plantilla y lo que lleva esperando el ticket';
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
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="" />
  <link
    href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;700&family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap"
    rel="stylesheet"
  />
</svelte:head>

<div class="snoc">
  <!-- v2-scroll: el UNICO contenedor que se desplaza. El marco de (app) es
       `overflow:hidden`; sin esto lo que no entra en la ventana queda
       recortado y no hay forma de llegar (ver supervisor-noc/+page.svelte). -->
  <div class="v2-scroll">
    <div class="snoc-lienzo">
    <!-- ============ CABECERA ============ -->
    <section class="snoc-panel" style="gap:var(--snoc-md);">
      <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-md);">
        <div class="snoc-pila-xs">
          <h1 class="snoc-h1">DESPACHO A CAMPO</h1>
          <p class="snoc-body snoc-secundario">
            Qué casos van a una visita, y con qué plantilla. Lo que se despacha acá es lo
            que el ciclo de la madrugada reparte entre las cuadrillas.
          </p>
        </div>
        <div class="snoc-fila" style="gap:var(--snoc-sm);">
          <a class="snoc-pildora" href="/supervisor-noc">Pendientes por revisión</a>
          <a class="snoc-pildora" href="/supervisor-noc/programacion">Programación</a>
          <a class="snoc-pildora" href="/supervisor-noc/cuadrillas">Cuadrillas</a>
          <a class="snoc-pildora snoc-pildora-activa" href="/supervisor-noc/despacho">
            Despacho
          </a>
          <a class="snoc-pildora" href="/supervisor-noc/plantillas">Plantillas</a>
        </div>
      </div>
    </section>

    {#if data.error}
      <section class="snoc-panel">
        <p class="snoc-aviso snoc-error-txt">
          No se pudieron leer los casos ni las plantillas. Si otras pantallas tampoco
          cargan, es el backend.
        </p>
      </section>
    {:else}
      {#if data.plantillasSinClasificar}
        <!-- Sin labor, el ciclo de la madrugada no las reparte. Se avisa acá
             —donde se despacha— y no solo en la pantalla de configuración. -->
        <section class="snoc-panel">
          <p class="snoc-aviso">
            {data.plantillasSinClasificar}
            {data.plantillasSinClasificar === 1 ? 'plantilla' : 'plantillas'} sin labor.
            Las órdenes que salgan con ellas no entran al reparto automático; se clasifican
            en <a href="/supervisor-noc/cuadrillas">Cuadrillas</a>.
          </p>
        </section>
      {/if}

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
            <input id="dia-simulado" class="snoc-campo" type="date" bind:value={diaSimulado}
                   aria-label="Día a simular" />
            <button class="snoc-btn" type="button" onclick={simularElDia} disabled={simulando}>
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
                <div class="snoc-tarjeta snoc-pila-xs" style="min-width:0;">
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
          <button class="snoc-btn" type="button" onclick={verOrdenesPrevia} disabled={cargandoOrdenes}>
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
          {#if ordenesPrevia.crear.length}
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
                      <td>{textoDePrioridad(f.prioridad)}</td>
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
          <a class="snoc-btn" href="/supervisor-noc/cuadrillas?dia={data.dia}&reparto=1">
            Ver el detalle y publicar
          </a>
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
            <ul class="snoc-lote-fallos">
              {#if data.conteos.sinZona}
                <li>{data.conteos.sinZona} sin zona mapeada — se arregla en Cuadrillas.</li>
              {/if}
              {#if data.conteos.sinCuadrilla}
                <li>{data.conteos.sinCuadrilla} en zonas que hoy no cubre nadie.</li>
              {/if}
              {#if data.conteos.sobrantes}
                <li>{data.conteos.sobrantes} no entraron por el tope por cuadrilla.</li>
              {/if}
              {#if data.conteos.sinClasificar}
                <li>{data.conteos.sinClasificar} sin tipo de trabajo declarado.</li>
              {/if}
            </ul>
          {/if}
        {/if}
      </section>

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
            <!-- EL SUPERVISOR MIRA UNA VEZ POR HORA, pero solo si la empresa le
                 delegó «Revisar solo». Sin esa delegación espera a que alguien
                 lo despierte, y esta pantalla queda vacía sin que nada lo
                 explique. Esto lo despierta: no ejecuta nada, solo deja
                 propuestas para que una persona las lea. -->
            <form method="POST" action="?/ciclo" use:enhance>
              <button class="snoc-btn" type="submit">
                Buscar casos que necesiten visita
              </button>
            </form>
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

                        {#if c.orden_activa}
                          <!-- No bloquea: una segunda visita al mismo caso es
                               legítima. Pero tiene que verse ANTES. -->
                          <span class="snoc-tag">Ya tiene la orden #{c.orden_activa} abierta ·
                            {c.orden_activa_tecnico ? `asignada a ${c.orden_activa_tecnico}` : 'SIN ASIGNAR'}</span>
                        {/if}

                        {#if c.sugerencia}
                          <p class="snoc-body-sm" style="margin:2px 0 0">
                            {#if c.sugerencia.labor === 'no_requiere_visita'}
                              <strong>No requiere visita.</strong>
                            {:else if c.sugerencia.labor}
                              <strong>{nombreDeLabor(c.sugerencia.labor)}</strong>
                              {#if !c.sugerencia.verificada}
                                <span class="snoc-tag">sin verificar</span>
                              {/if}
                            {:else}
                              <strong>Sin concluir.</strong>
                            {/if}
                            <span class="snoc-secundario">{c.sugerencia.porque}</span>
                          </p>
                        {/if}
                      </div>
                    </td>
                    <td class="snoc-mono" style="white-space:nowrap;">
                      {#if c.ticket}#{c.ticket}{:else}<span class="snoc-tenue">—</span>{/if}
                    </td>
                    <td class="snoc-body-sm">
                      {#if c.cliente}{c.cliente}{:else}<span class="snoc-tenue">Sin nombre</span>{/if}
                    </td>
                    <td style="text-align:right;">
                      <button class="snoc-btn" type="button" onclick={() => abrir(c)}>
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
    {/if}

    {#if despachando}
      <section class="snoc-panel" style="gap:var(--snoc-sm);">
        <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
          <h2 class="snoc-h2">{despachando.nombre}</h2>
          <button class="snoc-pildora" type="button" onclick={() => (despachando = null)}>
            Cerrar
          </button>
        </div>

        {#if despachando.sugerencia?.porque}
          <p class="snoc-aviso">
            {#if despachando.sugerencia.labor === 'no_requiere_visita'}
              <strong>La evidencia dice que no hace falta ir.</strong>
            {:else if despachando.sugerencia.labor}
              <strong>Sugerido: {nombreDeLabor(despachando.sugerencia.labor)}.</strong>
            {/if}
            {despachando.sugerencia.porque}
          </p>
        {/if}

        <form method="POST" action="?/despachar" use:enhance class="snoc-pila-xs">
          <input type="hidden" name="case_id" value={despachando.id} />

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
          </label>

          <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap;">
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
            <div class="snoc-tarjeta snoc-pila-xs">
              {#if cobertura.motivo === 'sin_zona'}
                <span class="snoc-body-sm"><strong>Este barrio no está en ninguna zona.</strong>
                  La orden se crea, pero no se reparte hasta que alguien lo agregue a una
                  zona en Cuadrillas.</span>
                {#if cobertura.parecidas?.length}
                  <span class="snoc-body-sm">¿Quisiste decir
                    {#each cobertura.parecidas as p, i (p.localidad)}
                      {i ? ' o ' : ''}<button type="button" class="snoc-btn"
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
          {#if cobertura?.jornadas?.length}
            <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap;">
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
              <p class="snoc-aviso snoc-error-txt">
                {jornada.aviso ?? `${jornada.cuadrilla}: nadie la vería en un teléfono.`}
              </p>
            {/if}
          {/if}

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
            <details class="snoc-tarjeta" open>
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
            <p class="snoc-aviso snoc-body-sm">
              <strong>Pasó solo a Despacho:</strong> {despachando.lectura.por_que_paso}
            </p>
          {/if}
          <!-- EL CORTE DE RED (19/10/2026), lo haya pasado el Supervisor o una
               persona: varios casos del mismo puerto son un solo trabajo. -->
          {#if despachando.lectura?.corte_de_red}
            <p class="snoc-aviso snoc-body-sm">
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

          <div>
            <button class="snoc-btn" type="submit">Crear la orden</button>
          </div>
        </form>

        {#if form?.error}
          <p class="snoc-aviso snoc-error-txt">{form.error}</p>
        {/if}
        {#if form?.hecho}
          <p class="snoc-aviso">{form.hecho}</p>
        {/if}
      </section>
    {/if}
    </div>
  </div>
</div>
