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
