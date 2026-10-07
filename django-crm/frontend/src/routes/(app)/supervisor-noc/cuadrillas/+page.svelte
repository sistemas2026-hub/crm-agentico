<script>
  /**
   * Cuadrillas — Supervisor NOC.
   *
   * DOS PREGUNTAS, DOS MITADES
   *   Arriba   el día: qué labor tiene cada cuadrilla y quién la integra HOY.
   *   Abajo    quiénes son: nombre, líder y vehículo. Cambia casi nunca.
   *
   * Esa es la razón de que sean dos tablas en el backend y de que acá estén
   * separadas: armar el día no es editar la cuadrilla. La cuadrilla sigue
   * siendo la misma; lo que cambia es su labor y su gente.
   *
   * POR QUÉ SE MANDA LA JORNADA ENTERA
   * El backend es idempotente por cuadrilla y fecha: reescribe todo con lo que
   * llega. Mandar sólo lo que cambió obligaría a decidir acá qué es un cambio,
   * que es justo lo que la idempotencia evita.
   */
  import { enhance } from '$app/forms';
  import '../supervisor-noc.css';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  const LABORES = [
    { id: 'instalacion', texto: 'Instalación' },
    { id: 'correctivo', texto: 'Correctivo' },
    { id: 'trabajos', texto: 'Trabajos' }
  ];

  const ROLES = [
    { id: 'tecnico_lider', texto: 'Técnico líder' },
    { id: 'tecnico', texto: 'Técnico' },
    { id: 'ayudante', texto: 'Ayudante' },
    { id: 'chofer', texto: 'Chofer' }
  ];

  /** Qué cuadrilla se está armando. `null` = ninguna. */
  let armando = $state(/** @type {any} */ (null));
  let labor = $state('instalacion');
  let lider = $state('');
  /** @type {{ profile: string, rol: string }[]} */
  let integrantes = $state([]);

  /** La ficha de cuadrilla abierta. `null` = ninguna. */
  let editando = $state(/** @type {any} */ (null));

  /** Las zonas que cubre la cuadrilla que se está armando. */
  let zonasDelDia = $state(/** @type {string[]} */ ([]));

  /** La zona cuyo mapeo de barrios está abierto. `null` = ninguno. */
  let mapeando = $state(/** @type {any} */ (null));
  let barriosElegidos = $state(/** @type {string[]} */ ([]));
  let buscaBarrio = $state('');

  /** En qué OTRA zona está cada barrio, para no ofrecerlo dos veces. */
  let barrioTomado = $derived.by(() => {
    /** @type {Record<string, string>} */
    const m = {};
    for (const z of data.zonas ?? []) {
      if (mapeando && z.id === mapeando.id) continue;
      for (const l of z.localidades ?? []) m[l] = z.nombre;
    }
    return m;
  });

  /** Los barrios que se ofrecen: los sincronizados, filtrados por el buscador. */
  let barriosOfrecidos = $derived(
    (data.localidades ?? [])
      .filter((l) =>
        !buscaBarrio ||
        String(l.localidad).toUpperCase().includes(buscaBarrio.toUpperCase())
      )
      // Los de más clientes primero: una zona se arma por peso, no por orden
      // alfabético.
      .slice()
      .sort((a, b) => (b.n_clientes ?? 0) - (a.n_clientes ?? 0))
  );

  function abrirMapeo(z) {
    mapeando = z;
    barriosElegidos = [...(z.localidades ?? [])];
    buscaBarrio = '';
  }

  function alternarBarrio(nombre) {
    barriosElegidos = barriosElegidos.includes(nombre)
      ? barriosElegidos.filter((x) => x !== nombre)
      : [...barriosElegidos, nombre];
  }

  /** La jornada ya armada de una cuadrilla, si la tiene. */
  function jornadaDe(cuadrillaId) {
    return (data.jornadas ?? []).find((j) => j.cuadrilla?.id === cuadrillaId) ?? null;
  }

  /**
   * Quién está ya en OTRA cuadrilla ese día.
   *
   * Se calcula acá para no ofrecer a alguien que el servidor va a rechazar:
   * la regla vive en el backend —y sigue viviendo ahí— pero mostrarla antes
   * evita el viaje de ida y vuelta para enterarse.
   */
  function tomadaPorOtra(profileId, cuadrillaId) {
    for (const j of data.jornadas ?? []) {
      if (j.cuadrilla?.id === cuadrillaId) continue;
      if ((j.integrantes ?? []).some((i) => i.id === profileId)) {
        return j.cuadrilla?.nombre ?? 'otra cuadrilla';
      }
    }
    return '';
  }

  function armar(c) {
    const ya = jornadaDe(c.id);
    armando = c;
    labor = ya?.labor ?? 'instalacion';
    lider = ya?.lider?.id ?? c.lider?.id ?? '';
    zonasDelDia = ya ? (ya.zonas ?? []).map((z) => z.id) : [];
    integrantes = ya
      ? ya.integrantes.map((i) => ({ profile: i.id, rol: i.rol }))
      : [];
    if (integrantes.length === 0) agregarIntegrante();
  }

  function agregarIntegrante() {
    integrantes = [...integrantes, { profile: '', rol: 'tecnico' }];
  }

  function quitarIntegrante(i) {
    integrantes = integrantes.filter((_, n) => n !== i);
    if (integrantes.length === 0) agregarIntegrante();
  }

  function abrirFicha(c) {
    editando = c
      ? { ...c, lider_id: c.lider?.id ?? '', vehiculo_id: c.vehiculo?.id ?? '' }
      : { id: '', nombre: '', lider_id: '', vehiculo_id: '', notas: '' };
  }

  /** Cuántas personas trabajan hoy, sin contar a nadie dos veces. */
  let gentePorJornada = $derived(
    new Set(
      (data.jornadas ?? []).flatMap((j) => (j.integrantes ?? []).map((i) => i.id))
    ).size
  );
</script>

<svelte:head>
  <title>Cuadrillas · Supervisor NOC</title>
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
          <h1 class="snoc-h1">CUADRILLAS</h1>
          <p class="snoc-body snoc-secundario">
            Quiénes son, y qué hace cada una el día que elijas. La cuadrilla sigue siendo la
            misma mañana; lo que cambia es su labor y su gente.
          </p>
        </div>
        <div class="snoc-fila" style="gap:var(--snoc-sm);">
          <a class="snoc-pildora" href="/supervisor-noc">Pendientes por revisión</a>
          <a class="snoc-pildora" href="/supervisor-noc/programacion">Programación</a>
          <a class="snoc-pildora snoc-pildora-activa" href="/supervisor-noc/cuadrillas">
            Cuadrillas
          </a>
        </div>
      </div>

      {#if data.error}
        <p class="snoc-aviso snoc-error-txt">
          No se pudieron leer todos los datos. Lo que falta no está vacío: no se sabe.
        </p>
      {/if}
      {#if form?.error}
        <p class="snoc-aviso snoc-error-txt">{form.error}</p>
      {/if}
      {#if form?.hecho}
        <p class="snoc-aviso">{form.hecho}</p>
      {/if}
    </section>

    <!-- ============ EL DÍA ============ -->
    <section class="snoc-panel" style="gap:var(--snoc-sm);">
      <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
        <div class="snoc-pila-xs">
          <h2 class="snoc-h2">El día</h2>
          <p class="snoc-body-sm snoc-secundario">
            {gentePorJornada}
            {gentePorJornada === 1 ? 'persona' : 'personas'} con trabajo asignado.
          </p>
        </div>
        <!-- La fecha va en la URL: así un día se puede compartir por enlace. -->
        <form method="GET" class="snoc-fila" style="gap:var(--snoc-xs);">
          <input class="snoc-campo" type="date" name="dia" value={data.dia} />
          <button class="snoc-btn" type="submit">Ver ese día</button>
        </form>
      </div>

      {#if (data.cuadrillas ?? []).length === 0}
        <p class="snoc-body snoc-secundario">
          Todavía no hay ninguna cuadrilla. Hasta que exista una no se le puede asignar
          trabajo a nadie: el reparto elige de acá.
        </p>
      {:else}
        <table class="snoc-tabla">
          <thead>
            <tr>
              <th>Cuadrilla</th>
              <th>Labor de hoy</th>
              <th>Quiénes</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {#each data.cuadrillas as c (c.id)}
              {@const j = jornadaDe(c.id)}
              <tr>
                <td>
                  <strong>{c.nombre}</strong>
                  {#if c.lider}
                    <span class="snoc-body-sm snoc-secundario" style="display:block;">
                      Líder: {c.lider.nombre}
                    </span>
                  {/if}
                  {#if c.vehiculo}
                    <span class="snoc-body-sm snoc-secundario" style="display:block;">
                      {c.vehiculo.nombre}
                    </span>
                  {/if}
                </td>
                <td>
                  {#if j}
                    <span class="snoc-insignia snoc-insignia-primaria">{j.labor_nombre}</span>
                    {#if j.zonas?.length}
                      {#each j.zonas as z (z.id)}
                        <span class="snoc-tag">{z.nombre}</span>
                      {/each}
                    {:else}
                      <span class="snoc-sin-dato" style="display:block;">sin zona</span>
                    {/if}
                  {:else}
                    <!-- SIN JORNADA NO ES «NO TRABAJA»: es que nadie se lo asignó
                         todavía. Decirlo distinto que «descansa» importa a las 6 am. -->
                    <span class="snoc-sin-dato">Sin armar</span>
                  {/if}
                </td>
                <td>
                  {#if j && j.integrantes.length}
                    {#each j.integrantes as i (i.id)}
                      <span class="snoc-tag">{i.nombre} · {i.rol.replace('_', ' ')}</span>
                    {/each}
                  {:else}
                    <span class="snoc-sin-dato">—</span>
                  {/if}
                </td>
                <td class="snoc-derecha">
                  <button class="snoc-pildora" type="button" onclick={() => armar(c)}>
                    {j ? 'Cambiar el día' : 'Armar el día'}
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </section>

    <!-- ============ ARMAR EL DÍA DE UNA CUADRILLA ============ -->
    {#if armando}
      <section class="snoc-panel" style="gap:var(--snoc-sm);">
        <h2 class="snoc-h2">{armando.nombre} · {data.dia}</h2>

        <form method="POST" action="?/jornada" use:enhance={() => {
          return async ({ result, update }) => {
            await update();
            if (result.type === 'success') armando = null;
          };
        }} class="snoc-pila">
          <input type="hidden" name="cuadrilla" value={armando.id} />
          <input type="hidden" name="fecha" value={data.dia} />

          <div class="snoc-fila" style="gap:var(--snoc-md); flex-wrap:wrap;">
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Labor</span>
              <select class="snoc-select" name="labor" bind:value={labor}>
                {#each LABORES as l (l.id)}
                  <option value={l.id}>{l.texto}</option>
                {/each}
              </select>
            </label>

            <label class="snoc-campo-grupo">
              <span class="snoc-label">Líder de hoy</span>
              <select class="snoc-select" name="lider" bind:value={lider}>
                <option value="">— el de la cuadrilla —</option>
                {#each data.personas as p (p.id)}
                  <option value={p.id}>{p.nombre}</option>
                {/each}
              </select>
            </label>
          </div>

          <div class="snoc-pila-xs">
            <span class="snoc-label">Zonas que cubre hoy</span>
            {#if (data.zonas ?? []).length === 0}
              <p class="snoc-body-sm snoc-secundario">
                Todavía no hay zonas. Se arman más abajo; sin ellas la cuadrilla queda sin
                zona, que no es lo mismo que cubrir todas.
              </p>
            {:else}
              <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
                {#each data.zonas as z (z.id)}
                  <label class="snoc-pildora" style="cursor:pointer;">
                    <input
                      type="checkbox"
                      name="zona"
                      value={z.id}
                      checked={zonasDelDia.includes(z.id)}
                      onchange={(e) => {
                        zonasDelDia = e.currentTarget.checked
                          ? [...zonasDelDia, z.id]
                          : zonasDelDia.filter((x) => x !== z.id);
                      }}
                    />
                    {z.nombre}
                  </label>
                {/each}
              </div>
              {#if zonasDelDia.length === 0}
                <!-- Vacío NO es «cubre todas», y hay que decirlo: con zona dura
                     una cuadrilla sin zona no recibe trabajo por zona. -->
                <p class="snoc-body-sm snoc-secundario">
                  Sin zona asignada. No significa que cubra todas: significa que no va a
                  recibir trabajo por zona.
                </p>
              {/if}
            {/if}
          </div>

          <p class="snoc-body-sm snoc-secundario">
            El líder del día puede no ser el de la cuadrilla: si está de vacaciones, alguien
            la lleva igual, y quién respondía ese día no puede depender de quién la lidera
            hoy.
          </p>

          <div class="snoc-pila-xs">
            <span class="snoc-label">Quiénes van</span>
            {#each integrantes as ig, i (i)}
              {@const ocupada = ig.profile ? tomadaPorOtra(ig.profile, armando.id) : ''}
              <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
                <select class="snoc-select" name="integrante_profile" bind:value={ig.profile}>
                  <option value="">— elegí a alguien —</option>
                  {#each data.personas as p (p.id)}
                    <option value={p.id}>{p.nombre}</option>
                  {/each}
                </select>
                <select class="snoc-select" name="integrante_rol" bind:value={ig.rol}>
                  {#each ROLES as r (r.id)}
                    <option value={r.id}>{r.texto}</option>
                  {/each}
                </select>
                <button class="snoc-pildora" type="button" onclick={() => quitarIntegrante(i)}>
                  Quitar
                </button>
                {#if ocupada}
                  <!-- Se avisa ANTES de enviar. La regla vive en el backend y
                       sigue viviendo ahí; esto evita el viaje para enterarse. -->
                  <span class="snoc-error-txt snoc-body-sm">
                    Ya está en {ocupada} hoy
                  </span>
                {/if}
              </div>
            {/each}
            <button class="snoc-pildora" type="button" onclick={agregarIntegrante}>
              Agregar a alguien
            </button>
          </div>

          <div class="snoc-fila" style="gap:var(--snoc-sm);">
            <button class="snoc-btn snoc-btn-primario" type="submit">Guardar el día</button>
            <button class="snoc-pildora" type="button" onclick={() => (armando = null)}>
              Cancelar
            </button>
          </div>
        </form>
      </section>
    {/if}

    <!-- ============ LAS ZONAS ============ -->
    <section class="snoc-panel" style="gap:var(--snoc-sm);">
      <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
        <div class="snoc-pila-xs">
          <h2 class="snoc-h2">Zonas operativas</h2>
          <p class="snoc-body-sm snoc-secundario">
            Cómo divide la empresa su territorio. No son las zonas del proveedor —ésas son
            de corte de facturación— y por eso se declaran acá.
          </p>
        </div>
        <form method="POST" action="?/zona" use:enhance class="snoc-fila"
              style="gap:var(--snoc-xs);">
          <input class="snoc-campo" name="nombre" required placeholder="Norte" />
          <button class="snoc-btn" type="submit">Crear zona</button>
        </form>
      </div>

      {#if (data.zonas ?? []).length === 0}
        <p class="snoc-body snoc-secundario">
          Todavía no hay ninguna. Sin zonas, una cuadrilla no puede recibir trabajo por
          zona.
        </p>
      {:else}
        <table class="snoc-tabla">
          <thead>
            <tr>
              <th>Zona</th>
              <th>Barrios</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {#each data.zonas as z (z.id)}
              <tr>
                <td><strong>{z.nombre}</strong></td>
                <td>
                  {#if z.localidades?.length}
                    {#each z.localidades as l (l)}
                      <span class="snoc-tag">{l}</span>
                    {/each}
                  {:else}
                    <span class="snoc-sin-dato">sin barrios asignados</span>
                  {/if}
                </td>
                <td class="snoc-derecha">
                  <button class="snoc-pildora" type="button" onclick={() => abrirMapeo(z)}>
                    Elegir barrios
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}

      {#if mapeando}
        <div class="snoc-pila" style="gap:var(--snoc-sm);">
          <h3 class="snoc-h2">Barrios de {mapeando.nombre}</h3>
          <!--
            LOS BARRIOS SE ELIGEN, NO SE ESCRIBEN. La lista la arma el motor
            recorriendo el catálogo del proveedor —«nunca la escribe una
            persona»— y ya resolvió las variantes: un intento de «mejorar» el
            nombre colapsando SOLEDAD ATLANTICO devolvió SOLEDA, un typo de
            tres clientes. Teclearlos acá repetiría ese error.
          -->
          {#if data.localidadesError}
            <p class="snoc-aviso snoc-error-txt">
              No se pudieron leer las localidades. Sin ellas no se puede mapear: no están
              vacías, no se saben.
            </p>
          {:else}
            <p class="snoc-body-sm snoc-secundario">
              {data.localidades.length} barrios sincronizados, con sus clientes.
              {#if data.localidadesActualizadoEn}
                Última sincronización: {data.localidadesActualizadoEn}.
              {/if}
              Se actualizan desde Configuración · Planes de venta.
            </p>

            <form method="POST" action="?/mapeo" use:enhance={() => {
              return async ({ result, update }) => {
                await update();
                if (result.type === 'success') mapeando = null;
              };
            }} class="snoc-pila" style="gap:var(--snoc-sm);">
              <input type="hidden" name="zona_id" value={mapeando.id} />

              <input
                class="snoc-campo"
                bind:value={buscaBarrio}
                placeholder="Buscar un barrio…"
              />

              <div style="max-height:320px; overflow:auto;" class="snoc-pila-xs">
                {#each barriosOfrecidos as l (l.localidad)}
                  {@const tomado = barrioTomado[l.localidad]}
                  <label
                    class="snoc-fila"
                    style="gap:var(--snoc-xs); cursor:{tomado ? 'not-allowed' : 'pointer'};"
                  >
                    <input
                      type="checkbox"
                      name="localidad"
                      value={l.localidad}
                      checked={barriosElegidos.includes(l.localidad)}
                      disabled={Boolean(tomado)}
                      onchange={() => alternarBarrio(l.localidad)}
                    />
                    <span class={tomado ? 'snoc-secundario' : ''}>{l.localidad}</span>
                    <span class="snoc-body-sm snoc-secundario">
                      {l.n_clientes}
                      {l.n_clientes === 1 ? 'cliente' : 'clientes'}
                    </span>
                    {#if tomado}
                      <!-- Se dice EN CUÁL está: el servidor lo rechazaría igual,
                           pero sin el nombre hay que salir a buscarlo. -->
                      <span class="snoc-body-sm snoc-secundario">· ya está en {tomado}</span>
                    {/if}
                  </label>
                {:else}
                  <p class="snoc-body-sm snoc-secundario">
                    Ningún barrio coincide con la búsqueda.
                  </p>
                {/each}
              </div>

              <div class="snoc-fila" style="gap:var(--snoc-sm);">
                <button class="snoc-btn snoc-btn-primario" type="submit">
                  Guardar {barriosElegidos.length}
                  {barriosElegidos.length === 1 ? 'barrio' : 'barrios'}
                </button>
                <button class="snoc-pildora" type="button" onclick={() => (mapeando = null)}>
                  Cancelar
                </button>
              </div>
            </form>
          {/if}
        </div>
      {/if}
    </section>

    <!-- ============ EL HISTORIAL ============ -->
    <section class="snoc-panel" style="gap:var(--snoc-sm);">
      <div class="snoc-pila-xs">
        <h2 class="snoc-h2">Quién estuvo con quién</h2>
        <p class="snoc-body-sm snoc-secundario">
          El dato siempre estuvo completo —una fila por persona y por día—; esto lo lee
          junto en vez de ir cambiando la fecha de a uno.
        </p>
      </div>

      <!-- Va por GET: así un historial se comparte por enlace, igual que el día. -->
      <form method="GET" class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
        <input type="hidden" name="dia" value={data.dia} />
        <label class="snoc-campo-grupo">
          <span class="snoc-label">Desde</span>
          <input class="snoc-campo" type="date" name="desde" value={data.historial.desde} />
        </label>
        <label class="snoc-campo-grupo">
          <span class="snoc-label">Hasta</span>
          <input class="snoc-campo" type="date" name="hasta" value={data.historial.hasta} />
        </label>
        <label class="snoc-campo-grupo">
          <span class="snoc-label">De una cuadrilla</span>
          <select class="snoc-select" name="cual" value={data.historial.cual}>
            <option value="">— todas —</option>
            {#each data.cuadrillas as c (c.id)}
              <option value={c.id}>{c.nombre}</option>
            {/each}
          </select>
        </label>
        <label class="snoc-campo-grupo">
          <span class="snoc-label">O de una persona</span>
          <select class="snoc-select" name="quien" value={data.historial.quien}>
            <option value="">— nadie en particular —</option>
            {#each data.personas as p (p.id)}
              <option value={p.id}>{p.nombre}</option>
            {/each}
          </select>
        </label>
        <button class="snoc-btn" type="submit">Ver</button>
      </form>

      {#if data.historial.error}
        <p class="snoc-aviso snoc-error-txt">
          {data.historial.motivo || 'No se pudo leer el historial.'}
        </p>
      {:else if !data.historial.pedido}
        <p class="snoc-body-sm snoc-secundario">
          Elegí un rango y una cuadrilla o una persona. No se trae solo: es una consulta de
          hasta tres meses y esta pantalla se abre casi siempre para asignar, no para mirar
          atrás.
        </p>
      {:else if data.historial.jornadas.length === 0}
        <p class="snoc-body-sm snoc-secundario">
          No hay ninguna jornada en ese rango. Que no haya no es lo mismo que no haber
          podido leerlas: esto es una respuesta, no un error.
        </p>
      {:else}
        <table class="snoc-tabla">
          <thead>
            <tr>
              <th>Día</th>
              <th>Cuadrilla</th>
              <th>Labor</th>
              <th>Quiénes</th>
            </tr>
          </thead>
          <tbody>
            {#each data.historial.jornadas as j (j.id)}
              <tr>
                <td class="snoc-mono">{j.fecha}</td>
                <td>{j.cuadrilla?.nombre ?? '—'}</td>
                <td>
                  <span class="snoc-insignia snoc-insignia-neutra">{j.labor_nombre}</span>
                </td>
                <td>
                  {#each j.integrantes as i (i.id)}
                    <!-- La persona consultada se destaca: en una fila de cinco,
                         encontrarla a ojo es justo lo que uno vino a evitar. -->
                    <span
                      class="snoc-tag"
                      class:snoc-insignia-primaria={i.id === data.historial.quien}
                    >
                      {i.nombre} · {i.rol.replace('_', ' ')}
                    </span>
                  {:else}
                    <span class="snoc-sin-dato">—</span>
                  {/each}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </section>

    <!-- ============ QUIÉNES SON ============ -->
    <section class="snoc-panel" style="gap:var(--snoc-sm);">
      <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
        <div class="snoc-pila-xs">
          <h2 class="snoc-h2">Las cuadrillas</h2>
          <p class="snoc-body-sm snoc-secundario">
            Una cuadrilla no se borra: se da de baja. Sus jornadas la referencian y son las
            que explican quién hizo qué.
          </p>
        </div>
        <div class="snoc-fila" style="gap:var(--snoc-xs);">
          <a
            class="snoc-pildora"
            href="?dia={data.dia}&bajas={data.verBajas ? '0' : '1'}"
          >
            {data.verBajas ? 'Ocultar las dadas de baja' : 'Ver las dadas de baja'}
          </a>
          <button class="snoc-pildora" type="button" onclick={() => abrirFicha(null)}>
            Cuadrilla nueva
          </button>
        </div>
      </div>

      {#if editando}
        <form method="POST" action="?/cuadrilla" use:enhance={() => {
          return async ({ result, update }) => {
            await update();
            if (result.type === 'success') editando = null;
          };
        }} class="snoc-pila">
          <input type="hidden" name="cuadrilla_id" value={editando.id} />
          <div class="snoc-fila" style="gap:var(--snoc-md); flex-wrap:wrap;">
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Nombre</span>
              <input
                class="snoc-campo"
                name="nombre"
                required
                bind:value={editando.nombre}
                placeholder="Cuadrilla 1"
              />
            </label>
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Líder</span>
              <select class="snoc-select" name="lider" bind:value={editando.lider_id}>
                <option value="">— sin líder —</option>
                {#each data.personas as p (p.id)}
                  <option value={p.id}>{p.nombre}</option>
                {/each}
              </select>
            </label>
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Vehículo</span>
              <select class="snoc-select" name="vehiculo" bind:value={editando.vehiculo_id}>
                <option value="">— sin vehículo —</option>
                {#each data.vehiculos as v (v.id)}
                  <option value={v.id}>{v.nombre}</option>
                {/each}
              </select>
            </label>
          </div>
          <p class="snoc-body-sm snoc-secundario">
            El vehículo es una ubicación de inventario: en una cuadrilla el material vive en
            la camioneta y no en la mochila de una persona, y eso cambia a quién se le pide
            cuenta.
          </p>
          <div class="snoc-fila" style="gap:var(--snoc-sm);">
            <button class="snoc-btn snoc-btn-primario" type="submit">Guardar</button>
            <button class="snoc-pildora" type="button" onclick={() => (editando = null)}>
              Cancelar
            </button>
          </div>
        </form>
      {/if}

      {#if (data.cuadrillas ?? []).length === 0}
        <p class="snoc-body snoc-secundario">Todavía no hay ninguna.</p>
      {:else}
        <table class="snoc-tabla">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Líder</th>
              <th>Vehículo</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {#each data.cuadrillas as c (c.id)}
              <tr>
                <td>
                  <strong>{c.nombre}</strong>
                  {#if !c.activa}
                    <span class="snoc-insignia snoc-insignia-neutra">Dada de baja</span>
                  {/if}
                </td>
                <td>{c.lider?.nombre ?? '—'}</td>
                <td>{c.vehiculo?.nombre ?? '—'}</td>
                <td class="snoc-derecha">
                  <div class="snoc-fila" style="gap:var(--snoc-xs); justify-content:flex-end;">
                    <button class="snoc-pildora" type="button" onclick={() => abrirFicha(c)}>
                      Editar
                    </button>
                    <form method="POST" action="?/baja" use:enhance>
                      <input type="hidden" name="cuadrilla_id" value={c.id} />
                      <input type="hidden" name="activa" value={c.activa ? '0' : '1'} />
                      <button class="snoc-pildora" type="submit">
                        {c.activa ? 'Dar de baja' : 'Reactivar'}
                      </button>
                    </form>
                  </div>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </section>
  </div>
</div>
