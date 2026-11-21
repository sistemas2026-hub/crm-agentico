<!--
  NIVEL DE AUTONOMÍA Y FRENO DE MANO  --  21/11/2026.

  Lo que era el modal «Alcance del Supervisor NOC IA» de Pendientes, ahora en
  un componente: Ajustes lo muestra en la página y Pendientes en su panel
  lateral. EL FRENO VA PRIMERO a propósito: quien llega con apuro llega para
  parar, no para ampliar. Tirar el freno no baja el nivel.

  `mostrarTareas` agrega «Qué le pidieron que haga» (solo lectura): en
  Ajustes sobra, porque la página entera es esa lista con sus interruptores.
-->
<script>
  import { avisar } from './avisos.svelte.js';

  /**
   * @type {{
   *   alcance: import('./alcance.svelte.js').Alcance,
   *   mostrarTareas?: boolean,
   *   fecha?: (iso: string | null) => string
   * }}
   */
  let { alcance, mostrarTareas = false, fecha = (iso) => iso ?? '' } = $props();

  const a = $derived(alcance.estado);

  /** @param {boolean} detener */
  async function freno(detener) {
    if (await alcance.moverFreno(detener)) {
      avisar(detener ? 'Freno puesto: ninguna acción automática corre.' : 'Freno levantado: el Supervisor vuelve a actuar.');
    }
  }

  async function nivel() {
    if (await alcance.guardarNivel()) avisar('Nivel de autonomía cambiado.');
  }
</script>

{#if alcance.cargando}
  <p class="snoc-body snoc-secundario" style="margin:0;">Leyendo el estado…</p>
{:else if a}
  <div class="ayf">
    <dl class="ayf-estado">
      <div><dt>Nivel autorizado</dt><dd>{a.configurado}</dd></div>
      <div>
        <dt>Nivel que aplica</dt>
        <dd>{a.efectivo}{#if a.recortado}<span class="snoc-error-txt"> (recortado)</span>{/if}</dd>
      </div>
      <div>
        <dt>Interruptor</dt>
        <dd class={a.interruptor_permite ? '' : 'snoc-error-txt'}>
          {a.interruptor_permite ? 'permite actuar' : 'NO permite actuar'}
        </dd>
      </div>
      {#if a.delegaciones}
        <div>
          <dt>Tareas delegadas</dt>
          <dd>{a.delegaciones.filter((/** @type {any} */ d) => d.delegada).length} de {a.delegaciones.length}</dd>
        </div>
      {/if}
    </dl>
    {#if a.motivo}<p class="snoc-body-sm snoc-secundario" style="margin:0;">{a.motivo}</p>{/if}

    <section class="snoc-recuadro {alcance.frenado ? 'snoc-recuadro-error' : ''} ayf-bloque" aria-labelledby="ayf-freno">
      <div class="snoc-fila-sep">
        <h3 class="snoc-h4" id="ayf-freno">Freno de mano</h3>
        <span class="snoc-insignia {alcance.frenado ? 'snoc-insignia-error' : 'snoc-insignia-ok'}">
          {alcance.frenado ? 'Puesto' : 'Libre'}
        </span>
      </div>
      <p class="snoc-body-sm" style="margin:0;">
        Detiene <strong>todas</strong> las acciones automáticas de inmediato. No cambia el nivel: cuando
        lo reactivés, el alcance vuelve a ser el que era.
      </p>
      <label class="snoc-campo-grupo">
        <span class="snoc-label">Motivo (obligatorio)</span>
        <input class="snoc-campo" type="text" bind:value={alcance.motivoFreno} placeholder="ej: algo raro en la bandeja" disabled={alcance.guardando} />
      </label>
      <div>
        {#if a.interruptor_permite}
          <button class="snoc-btn snoc-btn-error" type="button" disabled={alcance.guardando || !alcance.motivoFreno.trim()} onclick={() => freno(true)}>
            Detener las acciones automáticas
          </button>
        {:else}
          <button class="snoc-btn snoc-btn-primario" type="button" disabled={alcance.guardando || !alcance.motivoFreno.trim()} onclick={() => freno(false)}>
            Reactivar
          </button>
        {/if}
      </div>
    </section>

    <section class="ayf-bloque" aria-labelledby="ayf-nivel">
      <h3 class="snoc-h4" id="ayf-nivel">Qué puede hacer sin preguntar</h3>
      <select class="snoc-select" bind:value={alcance.nivelElegido} disabled={alcance.guardando} aria-label="Nivel de autonomía">
        {#each a.niveles ?? [] as n (n.nivel)}
          <option value={n.nivel}>{n.etiqueta}</option>
        {/each}
      </select>
      <label class="snoc-campo-grupo">
        <span class="snoc-label">Motivo del cambio (obligatorio)</span>
        <input class="snoc-campo" type="text" bind:value={alcance.motivoNivel} disabled={alcance.guardando} />
      </label>
      <label class="snoc-campo-grupo">
        <span class="snoc-label">Qué mediste para decidirlo (obligatorio)</span>
        <input class="snoc-campo" type="text" bind:value={alcance.criterios} disabled={alcance.guardando} />
      </label>
      <p class="snoc-body-sm snoc-secundario" style="margin:0;">
        Los criterios no son burocracia: sin saber qué se midió, esta decisión se vuelve a discutir cada
        vez que alguien la mire.
      </p>
      <div>
        <button class="snoc-btn snoc-btn-primario" type="button" disabled={alcance.guardando || alcance.nivelElegido === a.configurado} onclick={nivel}>
          {alcance.guardando ? 'Guardando…' : 'Cambiar el nivel'}
        </button>
      </div>
    </section>

    {#if mostrarTareas}
      <section class="ayf-bloque" aria-labelledby="ayf-tareas">
        <h3 class="snoc-h4" id="ayf-tareas">Qué le pidieron que haga</h3>
        {#each a.delegaciones ?? [] as d (d.clave)}
          {@const anda = d.delegada && d.nivel_alcanza && d.la_despierta_algo?.si}
          <div class="ayf-tarea">
            <div class="snoc-fila">
              <span class="snoc-punto {!d.delegada ? 'snoc-punto-tenue' : anda ? 'ayf-punto-ok' : 'snoc-punto-error'}" aria-hidden="true"></span>
              <strong class="snoc-body-sm">{d.nombre}</strong>
            </div>
            {#if !d.delegada}
              <span class="snoc-body-sm snoc-secundario">
                No delegada. Se enciende en <a href="/supervisor-noc/ajustes">Ajustes</a>, o pidiéndosela al Supervisor en el chat.
              </span>
            {:else}
              <span class="snoc-body-sm snoc-secundario">
                Delegada el {fecha(d.delegada_en)}{#if d.con_estas_palabras} · «{d.con_estas_palabras}»{/if}
              </span>
              {#if !d.nivel_alcanza}
                <span class="snoc-body-sm snoc-error-txt">No va a actuar: necesita nivel {d.exige_nivel} y el que aplica hoy es {a.efectivo}.</span>
              {/if}
              {#if d.la_despierta_algo && !d.la_despierta_algo.si}
                <span class="snoc-body-sm snoc-error-txt">{d.la_despierta_algo.por_que}</span>
              {/if}
            {/if}
            <span class="snoc-body-sm snoc-secundario">{d.que_hace}</span>
          </div>
        {:else}
          <p class="snoc-body-sm snoc-secundario" style="margin:0;">El backend no devolvió el catálogo de tareas.</p>
        {/each}
      </section>
    {/if}
  </div>
{/if}

{#if alcance.error}
  <p class="snoc-recuadro snoc-recuadro-error" role="alert">{alcance.error}</p>
{/if}

<style>
  .ayf { display: flex; flex-direction: column; gap: 14px; }
  .ayf-estado { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px 16px; margin: 0; font-size: 13px; }
  .ayf-estado dt { color: var(--v2-slate); font-size: 12px; }
  .ayf-estado dd { margin: 0; font-weight: 700; }
  .ayf-bloque { display: flex; flex-direction: column; gap: 8px; }
  .ayf-tarea { display: grid; gap: 2px; padding: 8px 0; border-top: 1px solid var(--v2-line-soft); }
  .ayf-punto-ok { background: var(--v2-sola-fuerte); }
</style>
