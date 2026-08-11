<script>
  /**
   * Bandeja de conversaciones.
   *
   * POR QUE UNA LISTA Y NO UNA TABLA
   * Una tabla ordena columnas comparables -- montos, fechas, estados. Una
   * bandeja se recorre distinto: lo que se busca es "cual de estas me
   * necesita", y eso se decide con quien escribio, que dijo y hace cuanto.
   * Por eso cada fila lleva el ultimo mensaje: sin el, veinte filas se ven
   * identicas y hay que abrirlas una por una para saber de que van.
   *
   * COMO SE LEE  (la regla de v2.css: ember marca lo que te necesita o
   * aquello sobre lo que podes actuar, nunca cromo)
   *   Sin atender   escalada y NADIE del equipo escribio todavia. Es el unico
   *                 estado que pide algo, y el unico con ember.
   *   En curso      escalada y ya contestada por una persona. Sigue abierta
   *                 pero no espera a nadie -> clay, quieto.
   *   Asistente     el bot la esta resolviendo solo -> slate, lo mas quieto.
   *
   * Las pestanas, el buscador y el filtro trabajan sobre lo ya cargado: la
   * bandeja entra en una pagina y filtrar del lado del cliente es instantaneo,
   * sin un viaje de red por cada clic.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import EmptyState from '$lib/v2/components/EmptyState.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';
  import { relativeTime, shortAge } from '$lib/v2/format.js';
  import { MessagesSquare, TriangleAlert, Search, X } from '@lucide/svelte';

  /** @type {{ data: any }} */
  let { data } = $props();

  let conversaciones = $derived(data.conversaciones ?? []);

  const CANAL_LABEL = { whatsapp: 'WhatsApp', 'whatsapp-simulado': 'Simulador' };
  const canalLabel = (/** @type {string} */ c) => CANAL_LABEL[c] ?? c;

  // Un color por etiqueta, no toda la taxonomia hardcodeada -- si el tenant
  // agrega una categoria nueva en conversaciones.etiquetas, cae en 'ink' en
  // vez de romper.
  const ETIQUETA_TONE = {
    soporte_tecnico: 'clay',
    facturacion: 'moss',
    comercial: 'slate',
    queja: 'rust'
  };
  const etiquetaTone = (/** @type {string} */ e) => ETIQUETA_TONE[e] ?? 'ink';
  const etiquetaLabel = (/** @type {string} */ e) => (e ? e.replaceAll('_', ' ') : '');

  /** Escalada y sin que nadie del equipo haya escrito: pide algo. */
  const pendiente = (/** @type {any} */ c) => c.escalada_a_humano && !c.atendida;

  const AUTOR = { user: 'Cliente', assistant: 'Asistente', humano: 'Vos', tool: 'Herramienta' };

  let filtro = $state('todas');
  let busqueda = $state('');

  let pendientes = $derived(conversaciones.filter(pendiente).length);
  let escaladas = $derived(conversaciones.filter((c) => c.escalada_a_humano).length);

  let pestanas = $derived([
    { id: 'todas', label: 'Todas', n: conversaciones.length },
    { id: 'pendientes', label: 'Sin atender', n: pendientes, urge: true },
    { id: 'escaladas', label: 'Escaladas', n: escaladas },
    { id: 'bot', label: 'Asistente', n: conversaciones.length - escaladas }
  ]);

  let visibles = $derived.by(() => {
    let lista = conversaciones;
    if (filtro === 'pendientes') lista = lista.filter(pendiente);
    else if (filtro === 'escaladas') lista = lista.filter((c) => c.escalada_a_humano);
    else if (filtro === 'bot') lista = lista.filter((c) => !c.escalada_a_humano);

    const q = busqueda.trim().toLowerCase();
    if (!q) return lista;
    return lista.filter((c) =>
      [c.usuario_externo, c.ultimo_mensaje, c.etiqueta, c.motivo_escalamiento]
        .filter(Boolean)
        .some((campo) => String(campo).toLowerCase().includes(q))
    );
  });
</script>

<PageHeader title="Conversaciones">
  {#snippet sub()}
    {#if pendientes > 0}
      <span class="v2-num">{pendientes}</span>
      {pendientes === 1 ? 'espera' : 'esperan'} a una persona · <span class="v2-num"
        >{conversaciones.length}</span
      > en total
    {:else}
      <span class="v2-num">{conversaciones.length}</span>
      {conversaciones.length === 1 ? 'conversación' : 'conversaciones'}, ninguna esperando
    {/if}
  {/snippet}
</PageHeader>

{#if !data.error && conversaciones.length > 0}
  <!-- Pestanas de estado. Nunca ember en la activa: "donde estoy" no es una
       accion. El contador de "Sin atender" si lo lleva, porque ese numero es
       trabajo sin tomar. -->
  <nav class="tabs" aria-label="Filtrar por estado">
    {#each pestanas as t (t.id)}
      <button
        type="button"
        class="tab"
        aria-current={filtro === t.id ? 'true' : undefined}
        onclick={() => (filtro = t.id)}
      >
        {t.label}
        <span class="tab-n v2-num" class:urge={t.urge && t.n > 0}>{t.n}</span>
      </button>
    {/each}

    <label class="buscar">
      <Search size={14} />
      <input
        type="text"
        bind:value={busqueda}
        placeholder="Buscar por cliente, mensaje o etiqueta…"
        aria-label="Buscar conversaciones"
      />
      {#if busqueda}
        <button type="button" class="limpiar" onclick={() => (busqueda = '')} aria-label="Limpiar">
          <X size={13} />
        </button>
      {/if}
    </label>
  </nav>
{/if}

<div class="v2-scroll">
  {#if data.error}
    <div class="v2-pad">
      <EmptyState title="No se pudo cargar la bandeja" body={data.error}>
        {#snippet icon()}<TriangleAlert size={21} />{/snippet}
      </EmptyState>
    </div>
  {:else if conversaciones.length === 0}
    <EmptyState
      title="Todavía no hay conversaciones"
      body="Acá van a aparecer los chats de WhatsApp con tus clientes. Mientras tanto, probá el Simulador de WhatsApp para ver cómo se vería uno."
    >
      {#snippet icon()}<MessagesSquare size={21} />{/snippet}
    </EmptyState>
  {:else if visibles.length === 0}
    <div class="v2-pad">
      <EmptyState
        title="Nada que mostrar acá"
        body={busqueda
          ? `Ninguna conversación coincide con «${busqueda}».`
          : 'No hay conversaciones en este estado.'}
      >
        {#snippet icon()}<Search size={20} />{/snippet}
      </EmptyState>
    </div>
  {:else}
    <div class="lista v2-pad">
      {#each visibles as c (c.id)}
        <a class="fila" class:pide={pendiente(c)} href="/conversaciones/{c.id}">
          <Avatar name={c.usuario_externo || '?'} size={34} />

          <div class="cuerpo">
            <div class="alta">
              <span class="quien">{c.usuario_externo || 'Sin identificar'}</span>
              <span class="cuando v2-num">{shortAge(c.actualizado_en)}</span>
            </div>

            <p class="avance">
              {#if c.ultimo_rol && c.ultimo_rol !== 'user'}
                <span class="avance-quien">{AUTOR[c.ultimo_rol] ?? c.ultimo_rol}:</span>
              {/if}
              {c.ultimo_mensaje || 'Sin mensajes todavía'}
            </p>

            <div class="baja">
              {#if pendiente(c)}
                <span class="marca" title={c.motivo_escalamiento || 'Escalada a un humano'}>
                  Sin atender
                </span>
              {:else if c.escalada_a_humano}
                <Pill tone="clay" dot>En curso</Pill>
              {:else}
                <Pill tone="slate" dot>Asistente</Pill>
              {/if}

              {#if c.etiqueta}
                <Pill tone={etiquetaTone(c.etiqueta)}>{etiquetaLabel(c.etiqueta)}</Pill>
              {/if}

              <span class="canal">{canalLabel(c.canal)}</span>
            </div>
          </div>
        </a>
      {/each}
    </div>

    <p class="v2-sub v2-pad" style="font-size:12px;padding-bottom:24px">
      Mostrando <span class="v2-num">{visibles.length}</span>
      de <span class="v2-num">{conversaciones.length}</span> ·
      última actividad {relativeTime(conversaciones[0].actualizado_en)}
    </p>
  {/if}
</div>

<style>
  /* ── pestañas + buscador ────────────────────────────────────────────── */
  .tabs {
    display: flex;
    align-items: center;
    gap: 2px;
    padding: 10px var(--v2-pad) 0;
    border-bottom: 1px solid var(--v2-line);
    flex: none;
    flex-wrap: wrap;
  }
  .tab {
    display: inline-flex;
    align-items: center;
    gap: 7px;
    padding: 8px 11px 9px;
    background: none;
    border: 0;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    font: inherit;
    font-size: 12.5px;
    font-weight: 550;
    color: var(--v2-slate);
    cursor: pointer;
    white-space: nowrap;
  }
  .tab:hover {
    color: var(--v2-ink);
  }
  /* Activa = peso y tinta. Ember marca lo que hay que hacer, no donde estás. */
  .tab[aria-current='true'] {
    color: var(--v2-ink);
    font-weight: 640;
    border-bottom-color: var(--v2-ink);
  }
  .tab-n {
    font-size: 10.5px;
    font-weight: 650;
    color: var(--v2-slate);
    background: var(--v2-hover);
    border-radius: 20px;
    padding: 1px 6px;
  }
  /* El único número que sí es ember: trabajo que nadie tomó. */
  .tab-n.urge {
    color: #fff;
    background: var(--v2-ember);
  }
  :global(.dark) .tab-n.urge {
    color: #1c1917;
  }
  .buscar {
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 0 0 6px auto;
    padding: 5px 9px;
    border: 1px solid var(--v2-line);
    border-radius: 8px;
    background: var(--v2-card);
    color: var(--v2-slate);
    min-width: 240px;
  }
  .buscar:focus-within {
    border-color: var(--v2-slate);
  }
  .buscar input {
    flex: 1;
    min-width: 0;
    border: 0;
    background: none;
    color: var(--v2-ink);
    font: inherit;
    font-size: 12.5px;
    outline: none;
  }
  .limpiar {
    border: 0;
    background: none;
    color: var(--v2-slate);
    cursor: pointer;
    display: grid;
    place-items: center;
    padding: 0;
  }
  .limpiar:hover {
    color: var(--v2-ink);
  }

  /* ── filas ──────────────────────────────────────────────────────────── */
  .lista {
    padding-top: 12px;
    padding-bottom: 4px;
    max-width: 900px;
  }
  .fila {
    display: flex;
    gap: 12px;
    padding: 12px 13px;
    margin-bottom: 7px;
    border: 1px solid var(--v2-line);
    border-radius: var(--v2-radius);
    background: var(--v2-card);
    color: inherit;
    text-decoration: none;
  }
  .fila:hover {
    border-color: var(--v2-slate);
  }
  /* Lo único que pide algo lleva ember, y como fondo + borde completo (el
     patrón de .v2-next), nunca como franja lateral. */
  .fila.pide {
    background: var(--v2-ember-soft);
    border-color: var(--v2-ember-line);
  }
  .cuerpo {
    flex: 1;
    min-width: 0;
  }
  .alta {
    display: flex;
    align-items: baseline;
    gap: 8px;
  }
  .quien {
    font-weight: 620;
    font-size: 13.6px;
    letter-spacing: -0.01em;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .cuando {
    margin-left: auto;
    flex: none;
    font-size: 11px;
    color: var(--v2-slate);
  }
  .avance {
    margin: 3px 0 8px;
    font-size: 12.5px;
    color: var(--v2-slate);
    line-height: 1.45;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .avance-quien {
    font-weight: 600;
    color: var(--v2-ink);
    opacity: 0.65;
  }
  .baja {
    display: flex;
    align-items: center;
    gap: 7px;
    flex-wrap: wrap;
  }
  .canal {
    font-size: 11px;
    color: var(--v2-slate);
    margin-left: auto;
    white-space: nowrap;
  }
  /* No es un Pill: Pill.svelte excluye ember a propósito porque ember no es
     "un estado en el que un registro está". Acá no describe un estado, marca
     trabajo sin tomar -- el mismo sentido que la tira .v2-next. */
  .marca {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 11.4px;
    font-weight: 650;
    color: var(--v2-ember);
    white-space: nowrap;
  }
  .marca::before {
    content: '';
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--v2-ember);
    flex: none;
  }

  @media (max-width: 768px) {
    .buscar {
      width: 100%;
      margin-left: 0;
    }
  }
</style>
