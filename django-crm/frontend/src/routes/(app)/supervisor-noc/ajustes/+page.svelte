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
  import '../supervisor-noc.css';
  import { loQueLeFalta, tonoDeLaTarea } from '$lib/supervisor/ajustes.js';

  let { data, form } = $props();

  const ajustes = $derived(/** @type {any} */ (data.ajustes));
  const tareas = $derived(/** @type {any[]} */ (ajustes?.tareas ?? []));
  const nivel = $derived(Number(ajustes?.nivel_efectivo ?? 0));

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
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="" />
  <link
    href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;700&family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap"
    rel="stylesheet"
  />
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
            Qué tareas hace solo el Supervisor. Cada una se delega o se quita con su
            interruptor, y queda registrado quién lo hizo y por qué.
          </p>
        </div>
        <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap;">
          <a class="snoc-pildora" href="/supervisor-noc">Pendientes por revisión</a>
          <a class="snoc-pildora" href="/supervisor-noc/programacion">Programación</a>
          <a class="snoc-pildora" href="/supervisor-noc/cuadrillas">Cuadrillas</a>
          <a class="snoc-pildora" href="/supervisor-noc/despacho">Despacho</a>
          <a class="snoc-pildora" href="/supervisor-noc/plantillas">Plantillas</a>
          <a class="snoc-pildora snoc-pildora-activa" href="/supervisor-noc/ajustes">Ajustes</a>
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
          Delegar una tarea no alcanza sola: además la empresa tiene que tener el nivel que esa
          tarea exige. El nivel y el freno se cambian en
          <a href="/supervisor-noc">Pendientes por revisión</a> → botón «Autonomía».
        </p>
      </section>

      <!-- ============ LAS TAREAS ============ -->
      <section class="snoc-pila" style="gap:var(--snoc-sm);">
        {#each tareas as t (t.clave)}
          {@const tono = tonoDeLaTarea(t, nivel)}
          {@const faltan = loQueLeFalta(t, nivel)}
          <article class="snoc-panel" style="gap:var(--snoc-xs);" aria-labelledby="tarea-{t.clave}">
            <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm); align-items:flex-start;">
              <div class="snoc-pila-xs" style="min-width:0; flex:1 1 320px;">
                <div class="snoc-fila" style="gap:var(--snoc-xs); align-items:baseline;">
                  <span class="snoc-punto {PUNTO[tono]}" aria-hidden="true"></span>
                  <h2 class="snoc-h3" id="tarea-{t.clave}">{t.nombre}</h2>
                  {#if t.delegada}
                    <span class="snoc-insignia snoc-insignia-secundaria-suave">Delegada</span>
                  {:else}
                    <span class="snoc-insignia snoc-insignia-neutra">Sin delegar</span>
                  {/if}
                  {#if t.exige_nivel}
                    <span class="snoc-insignia snoc-insignia-variante">Exige nivel {t.exige_nivel}</span>
                  {/if}
                </div>

                {#if t.delegada}
                  <p class="snoc-body-sm snoc-secundario" style="margin:0;">
                    Delegada por <strong>{t.delegada_por || 'una persona'}</strong> el {fecha(t.delegada_en)}
                    {#if t.con_estas_palabras}· «{t.con_estas_palabras}»{/if}
                  </p>
                {:else if t.quitada_por}
                  <p class="snoc-body-sm snoc-secundario" style="margin:0;">
                    Quitada por <strong>{t.quitada_por}</strong> el {fecha(t.quitada_en)}
                    {#if t.motivo_al_quitar}· «{t.motivo_al_quitar}»{/if}
                  </p>
                {/if}

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
                    placeholder={t.delegada ? 'Por qué la quitás' : 'Por qué la delegás'}
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
                    {t.delegada ? 'Quitar la tarea' : 'Delegar la tarea'}
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
    {/if}
    </div>
  </div>
</div>
