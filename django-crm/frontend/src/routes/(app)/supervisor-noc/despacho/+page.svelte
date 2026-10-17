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
  import '../supervisor-noc.css';

  let { data, form } = $props();

  /** El caso abierto en el panel. `null` = ninguno. */
  let despachando = $state(/** @type {any} */ (null));
  let plantillaElegida = $state('');

  const PRIORIDADES = [
    { id: '', texto: '— normal —' },
    { id: 'alta', texto: 'Alta' },
    { id: 'urgente', texto: 'Urgente' }
  ];

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
    //  sabe él, no nosotros.
    if (coinciden.length === 1) plantillaElegida = coinciden[0].id;
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
        descripcion: ficha.descripcion ?? ''
      };
      if (!plantillaElegida) preelegir(despachando.sugerencia?.labor);
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

      <!--
        COMO QUEDARIA LA JORNADA  --  13/10/2026
        ========================================
        El reparto ya existia y nadie lo veia desde aca. Ordena por lo que
        VENCE primero, despues por lo mas viejo, y respeta las zonas de cada
        cuadrilla. No publica nada: lo que se ve es una propuesta, y una
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
              Del {data.dia}. Primero lo que está por vencer, después lo más
              viejo, respetando las zonas de cada cuadrilla.
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
                  {l.cuadrillas === 1 ? 'cuadrilla' : 'cuadrillas'} a {l.labor}
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
            <h2 class="snoc-h2">Casos abiertos</h2>
            <p class="snoc-body-sm snoc-secundario">
              Solo los que ya aprobaste en <a href="/supervisor-noc">Pendientes por
              revisión</a>. Nada sale a campo sin pasar por ahí.
            </p>
          </div>
          <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap;">
            {#if !data.conFicha && (data.casos ?? []).length}
              <!-- La ficha cuesta una llamada al motor POR CASO, que a su vez
                   habla con WispHub y SmartOLT. Se pide, no viene sola. -->
              <a class="snoc-btn" href="?ficha=1">Traer el diagnóstico de cada uno</a>
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

        {#if (data.casos ?? []).length === 0}
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
          <div class="snoc-pila-xs">
            {#each data.casos as c (c.id)}
              <!-- `snoc-tarjeta` YA es flex en columna con space-between, asi
                   que encimarle `snoc-fila-sep` no la pone en fila: la deja en
                   columna separando el contenido del boton al maximo, y la
                   tarjeta crece hasta ocupar media pantalla. La fila va
                   ADENTRO. -->
              <div class="snoc-tarjeta">
                <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
                  <div class="snoc-pila-xs" style="min-width:0; flex:1 1 260px;">
                  <span class="snoc-body">{c.nombre}</span>
                  <span class="snoc-body-sm snoc-secundario">
                    {c.estado}{c.prioridad ? ` · ${c.prioridad}` : ''}
                    {#if c.ticket}· ticket #{c.ticket}{/if}
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

                  <button class="snoc-btn" type="button" onclick={() => abrir(c)}>
                    Despachar
                  </button>
                </div>
              </div>
            {/each}
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
                    bind:value={plantillaElegida} onchange={revisarCobertura} required>
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
            <span class="snoc-body-sm snoc-secundario">
              Define qué anota y qué fotos saca el técnico, y por su labor, qué cuadrilla
              la recibe.
              {#if !despachando.sugerencia && !cargandoFicha}
                Viene elegida sola cuando el diagnóstico sugiere una labor y hay una sola
                plantilla de esa labor.
              {/if}
              Se crean y se editan en <a href="/supervisor-noc/plantillas">Plantillas</a>.
            </span>
          </label>

          <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap;">
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Prioridad</span>
              <select class="snoc-select" name="prioridad">
                {#each PRIORIDADES as p (p.id)}<option value={p.id}>{p.texto}</option>{/each}
              </select>
            </label>
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Para cuándo</span>
              <input class="snoc-campo" type="date" name="programada_para"
                     bind:value={fecha} onchange={revisarCobertura} />
            </label>
          </div>

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
