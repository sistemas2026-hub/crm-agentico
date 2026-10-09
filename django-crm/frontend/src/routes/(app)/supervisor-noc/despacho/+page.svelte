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

  function abrir(caso) {
    despachando = caso;
    const coinciden = sugeridas(caso?.sugerencia?.labor);
    //  Si hay UNA sola de esa labor, viene elegida. Con dos o más no se elige
    //  por el usuario: entre dos plantillas de la misma labor la diferencia la
    //  sabe él, no nosotros.
    plantillaElegida = coinciden.length === 1 ? coinciden[0].id : '';
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

      <section class="snoc-panel" style="gap:var(--snoc-sm);">
        <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
          <div class="snoc-pila-xs">
            <h2 class="snoc-h2">Casos abiertos</h2>
            <p class="snoc-body-sm snoc-secundario">
              Los últimos {data.tope}. Que un caso merezca visita no lo decide el sistema:
              depende de si ya se intentó por teléfono, si el cliente está, si hay repuesto.
            </p>
          </div>
          {#if !data.conFicha}
            <!-- La ficha cuesta una llamada al motor POR CASO, que a su vez
                 habla con WispHub y SmartOLT. Se pide, no viene sola. -->
            <a class="snoc-btn" href="?ficha=1">Traer el diagnóstico de cada uno</a>
          {/if}
        </div>

        {#if (data.casos ?? []).length === 0}
          <p class="snoc-body-sm snoc-secundario">
            No hay casos abiertos. Nada que despachar.
          </p>
        {:else}
          <div class="snoc-pila-xs">
            {#each data.casos as c (c.id)}
              <div class="snoc-tarjeta snoc-fila-sep"
                   style="flex-wrap:wrap; gap:var(--snoc-xs);">
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
                    <span class="snoc-tag">Ya tiene la orden #{c.orden_activa} abierta</span>
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
                    bind:value={plantillaElegida} required>
              <option value="">— elegí una —</option>
              {#each data.plantillas as p (p.id)}
                <option value={p.id}>
                  {p.nombre}{p.labor ? ` · ${nombreDeLabor(p.labor)}` : ' · sin labor'}
                  {p.labor && p.labor === despachando.sugerencia?.labor ? ' ← sugerida' : ''}
                </option>
              {/each}
            </select>
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
              <input class="snoc-campo" type="date" name="programada_para" />
            </label>
          </div>

          <label class="snoc-campo-grupo">
            <span class="snoc-label">Cómo se entra al inmueble</span>
            <input class="snoc-campo" name="detalle_acceso"
                   placeholder="Apto 302, portería pide cédula" />
          </label>
          <!-- Con la dirección sola el técnico llega al edificio, no al
               apartamento. -->

          <label class="snoc-campo-grupo">
            <span class="snoc-label">Qué hay que hacer</span>
            <input class="snoc-campo" name="resumen"
                   placeholder="Lo que el técnico no puede deducir" />
          </label>

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
