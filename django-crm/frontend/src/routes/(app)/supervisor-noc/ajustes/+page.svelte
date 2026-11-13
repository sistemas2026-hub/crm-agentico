<script>
  /**
   * Ajustes del Supervisor (27/10/2026).
   *
   * Cada tarea que se le puede delegar, con qué hace, qué no hace, el nivel
   * que exige, si está delegada (quién, cuándo y por qué) y un interruptor
   * para delegarla o quitarla. Escribe por las mismas funciones que el chat
   * (`td.delegar` / `td.quitar`): esto es otra cara, no otra regla.
   *
   * EL MOTIVO ES OBLIGATORIO en las dos direcciones, como en el freno de mano:
   * una línea, no un informe. Es lo que contesta, meses después, por qué el
   * Supervisor hizo (o dejó de hacer) algo.
   */
  import { enhance } from '$app/forms';
  import PestanasNoc from '$lib/supervisor/PestanasNoc.svelte';
  import '../supervisor-noc.css';
  import {
    comoLlego,
    loQueLeFalta,
    separarPorCritica,
    tonoDeLaTarea
  } from '$lib/supervisor/ajustes.js';

  let { data, form } = $props();

  const ajustes = $derived(/** @type {any} */ (data.ajustes));
  const tareas = $derived(/** @type {any[]} */ (ajustes?.tareas ?? []));
  const nivel = $derived(Number(ajustes?.nivel_efectivo ?? 0));
  //  12/11/2026: lo no crítico nace delegado y lo crítico espera a una
  //  persona (PRD §2). La pantalla los muestra separados, con el porqué.
  const grupos = $derived(separarPorCritica(tareas));
  const esperan = $derived(/** @type {any[]} */ (ajustes?.espera_a_una_persona ?? []));

  /** La que se está mandando, para no dejar apretar dos veces. */
  let enviando = $state(/** @type {string | null} */ (null));

  /** @param {string} clave */
  const alCambiar = (clave) => {
    enviando = clave;
    return async (/** @type {any} */ { update }) => {
      await update();
      enviando = null;
    };
  };

  const PUNTO = {
    apagada: 'snoc-punto-tenue',
    andando: 'snoc-punto-secundario',
    trabada: 'snoc-punto-error'
  };

  /** En el reloj de la empresa (la zona viene del servidor). @param {string | null} iso */
  const fecha = (iso) =>
    iso
      ? new Date(iso).toLocaleString('es-CO', {
          day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit',
          timeZone: data.zona || 'UTC'
        })
      : '';
</script>

<svelte:head>
  <title>Ajustes del Supervisor · Supervisor NOC</title>
  <!-- Las fuentes se sirven desde la plataforma (static/fuentes/fuentes.css,
       cargado en app.html) desde el 12/11/2026: Google no se entera de
       cada pantalla que se abre. -->
</svelte:head>

<div class="snoc">
  <div class="v2-scroll">
    <div class="snoc-lienzo">
    <!-- ============ CABECERA ============ -->
    <section class="snoc-panel" style="gap:var(--snoc-md);">
      <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-md);">
        <div class="snoc-pila-xs">
          <h1 class="snoc-h1">AJUSTES DEL SUPERVISOR</h1>
          <p class="snoc-body snoc-secundario">
            Lo que no es crítico, el Supervisor lo hace solo desde el primer día. Acá se
            <strong>quita</strong>: cada tarea tiene su interruptor, y queda registrado quién y
            por qué. Lo crítico —lo que mueve dinero, corta un servicio o le llega a muchos
            clientes a la vez— espera siempre a una persona.
          </p>
        </div>
        <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap;">
          <PestanasNoc activa="ajustes" />
        </div>
      </div>
      <!-- El error de UNA tarea se muestra en su fila; acá solo el que no
           tiene fila. -->
      {#if form?.error && !form?.clave}
        <p class="snoc-aviso snoc-error-txt" role="alert">{form.error}</p>
      {/if}
      {#if form?.hecho}
        <p class="snoc-aviso" role="status">{form.hecho}</p>
      {/if}
    </section>

    {#if !data.puedeVer}
      <section class="snoc-panel">
        <p class="snoc-aviso">
          Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede ver y cambiar las tareas del
          Supervisor.
        </p>
      </section>
    {:else if data.error}
      <section class="snoc-panel">
        <p class="snoc-aviso snoc-error-txt">{data.error}</p>
      </section>
    {:else}
      <!-- ============ EL NIVEL, PARA LEER LO DE ABAJO ============ -->
      <section class="snoc-panel" style="gap:var(--snoc-xs);">
        <p class="snoc-body" style="margin:0;">
          Nivel de autonomía que aplica hoy: <strong>{nivel}</strong>
          {#if ajustes.nivel_por_omision}
            <span class="snoc-secundario">(el de fábrica: nadie lo cambió)</span>
          {:else if Number(ajustes.nivel_configurado ?? 0) < 3}
            · <strong class="snoc-error-txt">una persona lo dejó en {ajustes.nivel_configurado}: con
              menos de 3 ninguna tarea actúa sola</strong>
          {/if}
          <!-- EL MOTIVO DEL BACKEND, no una frase fija: con el motor caído
               el interruptor tampoco permite, y decir «freno de mano» culparía
               a la causa equivocada (auditor independiente, 27/10/2026). -->
          {#if !ajustes.interruptor_permite}
            · <strong class="snoc-error-txt">
              {ajustes.motivo || 'el freno de mano está puesto'}
            </strong>
          {/if}
        </p>
        <p class="snoc-body-sm snoc-secundario" style="margin:0;">
          Para pararlo todo de un paso está el freno de mano; el nivel y el freno se cambian en
          <a href="/supervisor-noc">Pendientes por revisión</a> → botón «Autonomía». Quitar una
          tarea no quita lo que el código comprueba antes de cada acción.
        </p>
      </section>

      <!-- ============ LO QUE HACE SOLO ============ -->
      <h2 class="snoc-h3" style="margin:var(--snoc-sm) 0 0;">Lo hace solo</h2>
      <section class="snoc-pila" style="gap:var(--snoc-sm);">
        {#each grupos.solas as t (t.clave)}
          {@const tono = tonoDeLaTarea(t, nivel)}
          {@const faltan = loQueLeFalta(t, nivel)}
          <article class="snoc-panel" style="gap:var(--snoc-xs);" aria-labelledby="tarea-{t.clave}">
            <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm); align-items:flex-start;">
              <div class="snoc-pila-xs" style="min-width:0; flex:1 1 320px;">
                <div class="snoc-fila" style="gap:var(--snoc-xs); align-items:baseline;">
                  <span class="snoc-punto {PUNTO[tono]}" aria-hidden="true"></span>
                  <h2 class="snoc-h3" id="tarea-{t.clave}">{t.nombre}</h2>
                  {#if t.delegada}
                    <span class="snoc-insignia snoc-insignia-secundaria-suave">Lo hace solo</span>
                  {:else}
                    <span class="snoc-insignia snoc-insignia-neutra">Quitada</span>
                  {/if}
                </div>

                <p class="snoc-body-sm snoc-secundario" style="margin:0;">
                  {comoLlego(t)}
                  {#if t.delegada && !t.por_omision && t.delegada_en} el {fecha(t.delegada_en)}{/if}
                  {#if !t.delegada && t.quitada_en} el {fecha(t.quitada_en)}{/if}
                  {#if t.delegada && t.con_estas_palabras}· «{t.con_estas_palabras}»{/if}
                  {#if !t.delegada && t.motivo_al_quitar}· «{t.motivo_al_quitar}»{/if}
                </p>

                <p class="snoc-body-sm" style="margin:0;"><strong>Qué hace.</strong> {t.que_hace}</p>
                <p class="snoc-body-sm snoc-secundario" style="margin:0;">
                  <strong>Qué no hace.</strong> {t.que_no_hace}
                </p>

                {#each faltan as f, i (i)}
                  <p class="snoc-body-sm {t.delegada ? 'snoc-error-txt' : 'snoc-tenue'}" style="margin:0;">
                    {t.delegada ? 'No va a actuar: ' : 'Para que actúe: '}{f}
                  </p>
                {/each}
              </div>

              <!-- EL INTERRUPTOR. Viaja el estado que se quiere, no «invertir»:
                   con la pantalla vieja, el backend contesta 409 y no pisa a
                   quien la cambió antes. -->
              <form
                method="POST"
                action="?/cambiar"
                use:enhance={() => alCambiar(t.clave)}
                class="snoc-pila-xs"
                style="flex:0 1 280px; gap:var(--snoc-xs);"
              >
                <input type="hidden" name="clave" value={t.clave} />
                <input type="hidden" name="delegar" value={t.delegada ? 'no' : 'si'} />
                <label class="snoc-campo-grupo">
                  <span class="snoc-label">Motivo (queda registrado)</span>
                  <input
                    class="snoc-campo"
                    name="motivo"
                    required
                    maxlength="500"
                    placeholder={t.delegada ? 'Por qué la quitás' : 'Por qué la volvés a delegar'}
                    disabled={enviando === t.clave}
                  />
                </label>
                <button
                  type="submit"
                  role="switch"
                  aria-checked={t.delegada}
                  aria-label="{t.delegada ? 'Quitar' : 'Delegar'}: {t.nombre}"
                  class="snoc-btn {t.delegada ? 'snoc-btn-error' : 'snoc-btn-primario'}"
                  disabled={enviando === t.clave}
                >
                  {#if enviando === t.clave}
                    Guardando…
                  {:else}
                    {t.delegada ? 'Quitar la tarea' : 'Volver a delegarla'}
                  {/if}
                </button>
                {#if form?.error && form?.clave === t.clave}
                  <p class="snoc-body-sm snoc-error-txt" role="alert" style="margin:0;">{form.error}</p>
                {/if}
              </form>
            </div>
          </article>
        {/each}
      </section>

      <!-- ============ LO QUE ESPERA A UNA PERSONA ============
           Lo crítico (PRD §2) no se delega desde acá: lo frena su propio
           circuito en el código, y la pantalla dice por qué. -->
      <h2 class="snoc-h3" style="margin:var(--snoc-sm) 0 0;">Espera a una persona</h2>
      <section class="snoc-pila" style="gap:var(--snoc-sm);">
        {#each grupos.criticas as t (t.clave)}
          <article class="snoc-panel" style="gap:var(--snoc-xs);">
            <h3 class="snoc-h3">{t.nombre}</h3>
            <p class="snoc-body-sm" style="margin:0;"><strong>Qué hace.</strong> {t.que_hace}</p>
            <p class="snoc-body-sm snoc-secundario" style="margin:0;">
              <strong>Por qué espera a una persona.</strong> Es crítica: la aprueba una persona cada vez.
            </p>
          </article>
        {/each}
        {#each esperan as c (c.clave)}
          <article class="snoc-panel" style="gap:var(--snoc-xs);">
            <h3 class="snoc-h3">{c.nombre}</h3>
            <p class="snoc-body-sm" style="margin:0;"><strong>Qué hace.</strong> {c.que_hace}</p>
            <p class="snoc-body-sm snoc-secundario" style="margin:0;">
              <strong>Por qué espera a una persona.</strong> {c.por_que_critica}
            </p>
          </article>
        {:else}
          {#if !grupos.criticas.length}
            <p class="snoc-body-sm snoc-secundario">Nada: todo lo que el Supervisor sabe hacer lo hace solo.</p>
          {/if}
        {/each}
      </section>
    {/if}
    </div>
  </div>
</div>
