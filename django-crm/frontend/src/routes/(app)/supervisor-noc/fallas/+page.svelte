<script>
  /**
   * Fallas de red (30/10/2026, PRD §8.17, Ola 2).
   *
   * Las caídas de PON vivas y, para cada una, avisarle a sus clientes por
   * WhatsApp antes de que escriban. Dos pasos: «Preparar el aviso» muestra a
   * cuántos y quiénes quedan afuera; «Avisar a N clientes» manda, por lotes.
   * La lista la arma el motor: solo los equipos que se cayeron JUNTOS, de
   * clientes activos. Un corte de energía no se avisa.
   *
   * Mientras un envío está en curso la pantalla se actualiza sola.
   */
  import { enhance } from '$app/forms';
  import { invalidateAll } from '$app/navigation';
  import PestanasNoc from '$lib/supervisor/PestanasNoc.svelte';
  import '../supervisor-noc.css';
  import { avance, motivosLegibles, NO_LISTO, POR_QUE_NO } from '$lib/supervisor/fallas.js';

  let { data, form } = $props();

  const fallas = $derived(/** @type {any[]} */ (data.fallas ?? []));
  const enCurso = $derived(fallas.some((f) => f.aviso?.estado === 'en_curso'));

  /** La que se está mandando, para no dejar apretar dos veces. */
  let enviando = $state(/** @type {string | null} */ (null));

  /** @param {string} id */
  const alEnviar = (id) => {
    enviando = id;
    return async (/** @type {any} */ { update }) => {
      await update({ reset: false });
      enviando = null;
    };
  };

  $effect(() => {
    if (!enCurso) return;
    const t = setInterval(() => invalidateAll(), 20000);
    return () => clearInterval(t);
  });

  const ESTADO = { en_curso: 'Enviando', terminado: 'Terminado', detenido: 'Detenido' };

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
  <title>Fallas de red · Supervisor NOC</title>
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
      <section class="snoc-panel" style="gap:var(--snoc-md);">
        <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-md);">
          <div class="snoc-pila-xs">
            <h1 class="snoc-h1">FALLAS DE RED</h1>
            <p class="snoc-body snoc-secundario">
              Las caídas de un puerto PON que están activas. Avisarle a sus clientes antes de que
              escriban evita que todos pregunten a la vez; lo aprueba una persona y sale por WhatsApp,
              por tandas.
            </p>
          </div>
          <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap;">
            <PestanasNoc activa="fallas" />
          </div>
        </div>
        {#if form?.error && !form?.situacion}
          <p class="snoc-aviso snoc-error-txt" role="alert">{form.error}</p>
        {/if}
      </section>

      {#if !data.puedeVer}
        <section class="snoc-panel">
          <p class="snoc-aviso">
            Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede ver las fallas de red y avisar
            a los clientes.
          </p>
        </section>
      {:else if data.error}
        <section class="snoc-panel">
          <p class="snoc-aviso snoc-error-txt">{data.error}</p>
        </section>
      {:else if !fallas.length}
        <section class="snoc-panel">
          <p class="snoc-aviso">No hay caídas de PON activas.</p>
        </section>
      {:else}
        <section class="snoc-pila" style="gap:var(--snoc-sm);">
          {#each fallas as f (f.id)}
            {@const mia = form?.situacion === f.id}
            {@const previa = mia ? form?.preparada : null}
            <article class="snoc-panel" style="gap:var(--snoc-xs);" aria-labelledby="falla-{f.id}">
              <div class="snoc-fila" style="gap:var(--snoc-xs); align-items:baseline; flex-wrap:wrap;">
                <span class="snoc-punto snoc-punto-error" aria-hidden="true"></span>
                <h2 class="snoc-h3" id="falla-{f.id}">{f.codigo} · {f.titulo}</h2>
                <span class="snoc-insignia snoc-insignia-neutra">PON {f.puerto}</span>
                {#if f.caja}<span class="snoc-insignia snoc-insignia-neutra">{f.caja}</span>{/if}
                {#if f.aviso}
                  <span class="snoc-insignia snoc-insignia-secundaria-suave">
                    Aviso: {ESTADO[/** @type {keyof typeof ESTADO} */ (f.aviso.estado)] ?? f.aviso.estado}
                  </span>
                {/if}
              </div>
              <p class="snoc-body-sm snoc-secundario" style="margin:0;">
                {f.equipos ?? '—'} equipos afectados según SmartOLT · detectada el {fecha(f.detectada_en)}
              </p>

              {#if f.aviso}
                {@const pct = avance(f.aviso)}
                <div class="snoc-pila-xs">
                  <p class="snoc-body-sm" style="margin:0;">
                    <strong>{f.aviso.enviados}</strong> avisados de {f.aviso.clientes} aprobados
                    {#if f.aviso.descartados}· {f.aviso.descartados} ya habían vuelto{/if}
                    {#if f.aviso.pendientes}· faltan {f.aviso.pendientes}{/if}
                  </p>
                  <div
                    role="progressbar"
                    aria-label="Avance del aviso"
                    aria-valuenow={pct}
                    aria-valuemin="0"
                    aria-valuemax="100"
                    style="height:6px; border-radius:3px; background:var(--snoc-borde, #e5e7eb); overflow:hidden;"
                  >
                    <div style="height:100%; width:{pct}%; background:var(--snoc-secundario, #2563eb);"></div>
                  </div>
                  {#each motivosLegibles(f.aviso.motivos) as m, i (i)}
                    <p class="snoc-body-sm snoc-tenue" style="margin:0;">No salió: {m}</p>
                  {/each}
                  <p class="snoc-body-sm snoc-tenue" style="margin:0;">
                    Aprobado por {f.aviso.aprobado_por || 'una persona'} el {fecha(f.aviso.aprobado_en)}
                  </p>
                </div>
              {:else if f.por_que_no}
                <p class="snoc-body-sm snoc-tenue" style="margin:0;">
                  {POR_QUE_NO[f.por_que_no] ?? f.por_que_no}
                </p>
              {:else if previa}
                <div class="snoc-pila-xs" role="status">
                  {#if previa.cargando}
                    <p class="snoc-body-sm" style="margin:0;">
                      Dexter está armando la lista de clientes del ISP. Probá de nuevo en un momento.
                    </p>
                  {:else}
                    <p class="snoc-body-sm" style="margin:0;">
                      Se les avisaría a <strong>{previa.clientes}</strong> clientes que se cayeron juntos.
                      {#if previa.sin_cliente || previa.fuera_de_estado}
                        Quedan afuera {previa.sin_cliente} equipos sin cliente y {previa.fuera_de_estado}
                        de clientes que no están activos.
                      {/if}
                    </p>
                    {#if previa.modo_prueba}
                      <p class="snoc-body-sm snoc-tenue" style="margin:0;">
                        El aviso está en modo prueba: solo les llega a los números de prueba.
                      </p>
                    {/if}
                    {#if previa.no_listo}
                      <p class="snoc-body-sm snoc-error-txt" style="margin:0;">
                        {NO_LISTO[previa.no_listo] ?? previa.no_listo} Se cambia en Ajustes → WhatsApp →
                        Mensajes automáticos.
                      </p>
                    {:else if previa.clientes}
                      <form method="POST" action="?/aprobar" use:enhance={() => alEnviar(f.id)}>
                        <input type="hidden" name="situacion" value={f.id} />
                        <button class="snoc-btn snoc-btn-primario" disabled={enviando === f.id}>
                          {enviando === f.id ? 'Aprobando…' : `Avisar a ${previa.clientes} clientes`}
                        </button>
                      </form>
                    {/if}
                  {/if}
                </div>
              {:else}
                <form method="POST" action="?/preparar" use:enhance={() => alEnviar(f.id)}>
                  <input type="hidden" name="situacion" value={f.id} />
                  <button class="snoc-btn" disabled={enviando === f.id}>
                    {enviando === f.id ? 'Preparando…' : 'Preparar el aviso a los clientes'}
                  </button>
                </form>
              {/if}

              {#if mia && form?.error}
                <p class="snoc-body-sm snoc-error-txt" role="alert" style="margin:0;">{form.error}</p>
              {/if}
            </article>
          {/each}
        </section>
      {/if}
    </div>
  </div>
</div>
