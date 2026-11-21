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
   *
   * REDISEÑO DEL 21/11/2026 (maqueta aprobada):
   *   - El nivel y el freno se cambian ACÁ también (antes había que ir a
   *     Pendientes → «Autonomía»): mismo componente, AutonomiaYFreno.
   *   - Cada tarea es una fila con su interruptor; el motivo se pide al
   *     tocarlo, no en diez cajas siempre abiertas.
   *   - Filtro por estado: andando, trabadas (delegadas que no van a actuar)
   *     y quitadas. El título «Lo hace solo» ya no agrupa a las quitadas.
   *   - «Qué hace / Qué no hace» queda plegado.
   */
  import { enhance } from '$app/forms';
  import { onMount } from 'svelte';
  import '../supervisor-noc.css';
  import PanelLateral from '$lib/supervisor/ui/PanelLateral.svelte';
  import AutonomiaYFreno from '$lib/supervisor/ui/AutonomiaYFreno.svelte';
  import { Alcance } from '$lib/supervisor/ui/alcance.svelte.js';
  import { avisar } from '$lib/supervisor/ui/avisos.svelte.js';
  import { comoLlego, loQueLeFalta, separarPorCritica, tonoDeLaTarea } from '$lib/supervisor/ajustes.js';

  let { data, form } = $props();

  const ajustes = $derived(/** @type {any} */ (data.ajustes));
  const tareas = $derived(/** @type {any[]} */ (ajustes?.tareas ?? []));
  const nivel = $derived(Number(ajustes?.nivel_efectivo ?? 0));
  //  12/11/2026: lo no crítico nace delegado y lo crítico espera a una
  //  persona (PRD §2). La pantalla los muestra separados, con el porqué.
  const grupos = $derived(separarPorCritica(tareas));
  const esperan = $derived(/** @type {any[]} */ (ajustes?.espera_a_una_persona ?? []));

  /** @type {'todas' | 'andando' | 'trabada' | 'apagada'} */
  let filtro = $state('todas');
  const cuentas = $derived({
    todas: grupos.solas.length,
    andando: grupos.solas.filter((t) => tonoDeLaTarea(t, nivel) === 'andando').length,
    trabada: grupos.solas.filter((t) => tonoDeLaTarea(t, nivel) === 'trabada').length,
    apagada: grupos.solas.filter((t) => tonoDeLaTarea(t, nivel) === 'apagada').length
  });
  const visibles = $derived(grupos.solas.filter((t) => filtro === 'todas' || tonoDeLaTarea(t, nivel) === filtro));

  /** La tarea a la que se le está pidiendo el motivo. */
  let pidiendo = $state(/** @type {string | null} */ (null));
  /** La que se está mandando, para no dejar apretar dos veces. */
  let enviando = $state(/** @type {string | null} */ (null));

  /** @param {string} clave */
  const alCambiar = (clave) => {
    enviando = clave;
    return async (/** @type {any} */ { result, update }) => {
      await update();
      enviando = null;
      if (result?.type === 'success') {
        pidiendo = null;
        avisar(result.data?.hecho ?? 'Listo.');
      }
    };
  };

  //  El nivel y el freno, con la misma lógica que Pendientes.
  const alcance = new Alcance();
  let panelAlcance = $state(false);
  onMount(() => {
    if (data.puedeVer) alcance.leer();
  });

  const ESTADO = {
    andando: { texto: 'Andando', clase: 'snoc-insignia-ok' },
    trabada: { texto: 'Trabada', clase: 'snoc-insignia-error' },
    apagada: { texto: 'Quitada', clase: '' }
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
</svelte:head>

<div class="snoc">
  <div class="v2-scroll">
    <div class="snoc-lienzo">
      <header class="snoc-encabezado">
        <div class="snoc-encabezado-texto">
          <h1 class="snoc-h1">Ajustes del Supervisor</h1>
          <p class="snoc-bajada">
            Lo que no es crítico, el Supervisor lo hace solo desde el primer día. Acá se
            <strong>quita</strong>: cada tarea tiene su interruptor, y queda registrado quién y por qué.
            Lo crítico —lo que mueve dinero, corta un servicio o le llega a muchos clientes a la vez—
            espera siempre a una persona.
          </p>
        </div>
      </header>

      <!-- El error de UNA tarea se muestra en su fila; acá solo el que no tiene fila. -->
      {#if form?.error && !form?.clave}
        <p class="snoc-recuadro snoc-recuadro-error" role="alert">{form.error}</p>
      {/if}

      {#if !data.puedeVer}
        <p class="snoc-recuadro">
          Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede ver y cambiar las tareas del Supervisor.
        </p>
      {:else if data.error}
        <p class="snoc-recuadro snoc-recuadro-error">{data.error}</p>
      {:else}
        <!-- ============ EL NIVEL Y EL FRENO ============ -->
        <div class="aj-dos">
          <section class="snoc-panel" aria-labelledby="aj-nivel">
            <div class="snoc-tarjeta-cabeza">
              <h2 class="snoc-h2" id="aj-nivel">Nivel de autonomía que aplica hoy</h2>
            </div>
            <div class="snoc-fila" style="gap:14px;">
              <span class="aj-nivel">{nivel}</span>
              <div class="snoc-pila-xs">
                {#if ajustes.nivel_por_omision}
                  <span class="snoc-body-sm snoc-secundario">El de fábrica: nadie lo cambió.</span>
                {:else if Number(ajustes.nivel_configurado ?? 0) < 3}
                  <strong class="snoc-body-sm snoc-error-txt">
                    Una persona lo dejó en {ajustes.nivel_configurado}: con menos de 3 ninguna tarea actúa sola.
                  </strong>
                {/if}
                <span class="snoc-body-sm snoc-secundario">
                  Quitar una tarea no quita lo que el código comprueba antes de cada acción.
                </span>
              </div>
            </div>
            <div><button type="button" class="snoc-btn" onclick={() => (panelAlcance = true)}>Cambiar el nivel…</button></div>
          </section>

          <section class="snoc-panel {ajustes.interruptor_permite ? '' : 'aj-frenado'}" aria-labelledby="aj-freno">
            <div class="snoc-tarjeta-cabeza">
              <h2 class="snoc-h2" id="aj-freno">Freno de mano</h2>
              <span class="snoc-insignia {ajustes.interruptor_permite ? 'snoc-insignia-ok' : 'snoc-insignia-error'}">
                {ajustes.interruptor_permite ? 'Libre' : 'Puesto'}
              </span>
            </div>
            <p class="snoc-body-sm" style="margin:0;">
              Para todo de un paso: ninguna acción automática corre mientras esté puesto. Lo que propone
              sigue llegando a Pendientes.
            </p>
            <!-- EL MOTIVO DEL BACKEND, no una frase fija: con el motor caído el
                 interruptor tampoco permite, y decir «freno de mano» culparía
                 a la causa equivocada (auditor independiente, 27/10/2026). -->
            {#if !ajustes.interruptor_permite}
              <p class="snoc-recuadro snoc-recuadro-error">{ajustes.motivo || 'El freno de mano está puesto.'}</p>
            {/if}
            <div>
              <button
                type="button"
                class="snoc-btn {ajustes.interruptor_permite ? 'snoc-btn-error' : 'snoc-btn-primario'}"
                onclick={() => (panelAlcance = true)}
              >
                {ajustes.interruptor_permite ? 'Poner el freno…' : 'Ver por qué y levantarlo…'}
              </button>
            </div>
          </section>
        </div>

        <!-- ============ LO QUE HACE SOLO ============ -->
        <section class="snoc-panel" style="padding:0; gap:0;" aria-labelledby="aj-solas">
          <div class="snoc-tarjeta-cabeza aj-cabeza">
            <div class="snoc-fila">
              <h2 class="snoc-h2" id="aj-solas">Lo que hace solo</h2>
              <span class="snoc-cuenta">{grupos.solas.length}</span>
            </div>
            <div class="snoc-segmentado" role="group" aria-label="Qué tareas ver">
              {#each [['todas', 'Todas'], ['andando', 'Andando'], ['trabada', 'Trabadas'], ['apagada', 'Quitadas']] as [clave, texto] (clave)}
                <button type="button" aria-pressed={filtro === clave} onclick={() => (filtro = /** @type {any} */ (clave))}>
                  {texto} <span class="snoc-cuenta">{cuentas[/** @type {keyof typeof cuentas} */ (clave)]}</span>
                </button>
              {/each}
            </div>
          </div>

          {#each visibles as t (t.clave)}
            {@const tono = tonoDeLaTarea(t, nivel)}
            {@const faltan = loQueLeFalta(t, nivel)}
            <article class="aj-tarea" aria-labelledby="tarea-{t.clave}">
              <div class="snoc-fila-sep" style="align-items:flex-start; flex-wrap:wrap;">
                <div class="snoc-pila-xs" style="min-width:0; flex:1 1 320px;">
                  <div class="snoc-fila" style="flex-wrap:wrap;">
                    <h3 class="snoc-h4" id="tarea-{t.clave}">{t.nombre}</h3>
                    <span class="snoc-insignia {ESTADO[tono].clase}">{ESTADO[tono].texto}</span>
                  </div>
                  <p class="snoc-body-sm snoc-secundario" style="margin:0;">
                    {comoLlego(t)}
                    {#if t.delegada && !t.por_omision && t.delegada_en} el {fecha(t.delegada_en)}{/if}
                    {#if !t.delegada && t.quitada_en} el {fecha(t.quitada_en)}{/if}
                    {#if t.delegada && t.con_estas_palabras}· «{t.con_estas_palabras}»{/if}
                    {#if !t.delegada && t.motivo_al_quitar}· «{t.motivo_al_quitar}»{/if}
                  </p>
                  {#each faltan as f, i (i)}
                    <p class="snoc-body-sm {t.delegada ? 'snoc-error-txt' : 'snoc-secundario'}" style="margin:0;">
                      {t.delegada ? 'No va a actuar: ' : 'Para que actúe: '}{f}
                    </p>
                  {/each}
                </div>
                <!-- EL INTERRUPTOR. Tocarlo pide el motivo; viaja el estado que
                     se quiere, no «invertir»: si alguien la cambió mientras
                     tanto, el backend contesta 409 y no pisa su registro. -->
                <div class="snoc-fila">
                  <span class="snoc-body-sm snoc-secundario">{t.delegada ? 'La hace sola' : 'Quitada'}</span>
                  <button
                    type="button"
                    role="switch"
                    class="aj-sw"
                    class:aj-sw-on={t.delegada}
                    aria-checked={t.delegada}
                    aria-label="{t.delegada ? 'Quitar' : 'Delegar'}: {t.nombre}"
                    aria-expanded={pidiendo === t.clave}
                    onclick={() => (pidiendo = pidiendo === t.clave ? null : t.clave)}
                  ></button>
                </div>
              </div>

              {#if pidiendo === t.clave}
                <form
                  method="POST"
                  action="?/cambiar"
                  use:enhance={() => alCambiar(t.clave)}
                  class="snoc-recuadro aj-motivo"
                >
                  <input type="hidden" name="clave" value={t.clave} />
                  <input type="hidden" name="delegar" value={t.delegada ? 'no' : 'si'} />
                  <label class="snoc-campo-grupo" style="flex:1 1 280px;">
                    <span class="snoc-label">Motivo (queda registrado)</span>
                    <!-- svelte-ignore a11y_autofocus -->
                    <input
                      class="snoc-campo"
                      name="motivo"
                      required
                      maxlength="500"
                      autofocus
                      placeholder={t.delegada ? 'Por qué la quitás' : 'Por qué la volvés a delegar'}
                      disabled={enviando === t.clave}
                    />
                  </label>
                  <div class="snoc-fila" style="align-self:flex-end;">
                    <button type="button" class="snoc-btn" onclick={() => (pidiendo = null)} disabled={enviando === t.clave}>Cancelar</button>
                    <button
                      type="submit"
                      class="snoc-btn {t.delegada ? 'snoc-btn-error' : 'snoc-btn-primario'}"
                      disabled={enviando === t.clave}
                    >
                      {enviando === t.clave ? 'Guardando…' : t.delegada ? 'Quitar la tarea' : 'Volver a delegarla'}
                    </button>
                  </div>
                  {#if form?.error && form?.clave === t.clave}
                    <p class="snoc-body-sm snoc-error-txt" role="alert" style="margin:0; flex-basis:100%;">{form.error}</p>
                  {/if}
                </form>
              {:else if form?.error && form?.clave === t.clave}
                <p class="snoc-recuadro snoc-recuadro-error" role="alert">{form.error}</p>
              {/if}

              <details class="aj-detalle">
                <summary>Qué hace y qué no hace</summary>
                <p class="snoc-body-sm" style="margin:0;"><strong>Qué hace.</strong> {t.que_hace}</p>
                <p class="snoc-body-sm snoc-secundario" style="margin:0;"><strong>Qué no hace.</strong> {t.que_no_hace}</p>
              </details>
            </article>
          {:else}
            <p class="snoc-body-sm snoc-secundario" style="margin:0; padding:16px 18px;">Ninguna tarea en esta vista.</p>
          {/each}
        </section>

        <!-- ============ LO QUE ESPERA A UNA PERSONA ============
             Lo crítico (PRD §2) no se delega desde acá: lo frena su propio
             circuito en el código, y la pantalla dice por qué. -->
        <section class="snoc-panel" aria-labelledby="aj-criticas">
          <div class="snoc-tarjeta-cabeza">
            <h2 class="snoc-h2" id="aj-criticas">Espera a una persona</h2>
            <span class="snoc-insignia">Solo lectura</span>
          </div>
          {#each grupos.criticas as t (t.clave)}
            <article class="aj-critica">
              <span class="snoc-insignia snoc-insignia-error">Crítica</span>
              <div class="snoc-pila-xs">
                <h3 class="snoc-h4">{t.nombre}</h3>
                <p class="snoc-body-sm" style="margin:0;"><strong>Qué hace.</strong> {t.que_hace}</p>
                <p class="snoc-body-sm snoc-secundario" style="margin:0;">
                  <strong>Por qué espera a una persona.</strong> Es crítica: la aprueba una persona cada vez.
                </p>
              </div>
            </article>
          {/each}
          {#each esperan as c (c.clave)}
            <article class="aj-critica">
              <span class="snoc-insignia snoc-insignia-error">Crítica</span>
              <div class="snoc-pila-xs">
                <h3 class="snoc-h4">{c.nombre}</h3>
                <p class="snoc-body-sm" style="margin:0;"><strong>Qué hace.</strong> {c.que_hace}</p>
                <p class="snoc-body-sm snoc-secundario" style="margin:0;">
                  <strong>Por qué espera a una persona.</strong> {c.por_que_critica}
                </p>
              </div>
            </article>
          {:else}
            {#if !grupos.criticas.length}
              <p class="snoc-body-sm snoc-secundario" style="margin:0;">Nada: todo lo que el Supervisor sabe hacer lo hace solo.</p>
            {/if}
          {/each}
        </section>
      {/if}
    </div>
  </div>
</div>

<PanelLateral
  abierto={panelAlcance}
  antetitulo="Alcance del Supervisor NOC IA"
  titulo="Autonomía y freno de mano"
  alCerrar={() => (panelAlcance = false)}
>
  <AutonomiaYFreno {alcance} {fecha} />
</PanelLateral>

<style>
  .aj-dos { display: grid; gap: 16px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 380px), 1fr)); }
  .aj-nivel { font-size: 34px; line-height: 1; font-weight: 700; color: var(--v2-ember-text); }
  .aj-frenado { border-color: var(--v2-critica-line); }
  .aj-cabeza { padding: 14px 18px; border-bottom: 1px solid var(--v2-line-soft); }
  .aj-tarea { display: flex; flex-direction: column; gap: 8px; padding: 14px 18px; border-bottom: 1px solid var(--v2-line-soft); }
  .aj-tarea:last-child { border-bottom: 0; }
  .aj-motivo { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; }
  .aj-detalle summary { cursor: pointer; font-size: 12.5px; font-weight: 600; color: var(--v2-ember-text); }
  .aj-detalle[open] { display: grid; gap: 6px; }
  .aj-critica { display: flex; gap: 12px; align-items: flex-start; padding-top: 10px; border-top: 1px solid var(--v2-line-soft); }
  .aj-sw {
    width: 40px; height: 24px; border-radius: 999px; border: 0; cursor: pointer; flex: none;
    background: var(--v2-line-strong); position: relative;
  }
  .aj-sw::after {
    content: ''; position: absolute; top: 3px; left: 3px; width: 18px; height: 18px; border-radius: 999px;
    background: #fff; box-shadow: 0 1px 2px rgba(0, 0, 0, 0.25); transition: left 0.15s;
  }
  .aj-sw-on { background: var(--v2-sola-fuerte); }
  .aj-sw-on::after { left: 19px; }
  .aj-sw:focus-visible { outline: 2px solid var(--v2-ember); outline-offset: 2px; }
  @media (prefers-reduced-motion: reduce) { .aj-sw::after { transition: none; } }
</style>
