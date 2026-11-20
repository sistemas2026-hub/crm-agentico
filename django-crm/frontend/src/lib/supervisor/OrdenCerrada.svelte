<!--
  UNA ORDEN CERRADA, en la pestaña Cerradas de Programación (30/10/2026). El
  usuario: «¿a dónde van los tickets cuando ya se cierran?». Con la forma de
  `campo/ordenes_cerradas.py`: quién la cerró, el ticket del ISP, los tiempos,
  qué hizo el técnico, lo que revisó el Supervisor al aprobar y SU historial
  —solo lo de esta orden: el material del día es de la cuadrilla—.
-->
<script>
  import ProgresoDeLaOrden from './ProgresoDeLaOrden.svelte';
  import { textoDeQuien, textoDelTicket, textoDeTiempos } from './dia-publicado.js';

  /** @type {{ orden: any }} */
  let { orden } = $props();

  const marca = /** @type {Record<string, string>} */ ({ true: '✔', false: '✖', null: '?' });
  const hora = $derived((orden.cerrada_en ?? '').slice(11, 16));
  const tiempos = $derived(textoDeTiempos(orden.tiempos));
</script>

<article class="oc" aria-label={`Orden ${orden.numero}, cerrada`}>
  <header class="oc-cabeza">
    <span class="oc-numero">OT {orden.numero}</span>
    {#if orden.cuadrilla}<span class="oc-cuadrilla">{orden.cuadrilla}</span>{/if}
    <span class="oc-hora">Cerrada {hora}</span>
  </header>
  <p class="oc-asunto">{orden.asunto || orden.tipo}</p>
  <div class="oc-quien">
    <span>{orden.cliente || 'Sin cliente'}{#if orden.direccion} · {orden.direccion}{/if}</span>
    {#if orden.barrio}<span class="snoc-secundario">{orden.barrio}</span>{/if}
  </div>

  <ProgresoDeLaOrden estado="cerrada" />

  <dl class="oc-datos">
    <dt>Quién la cerró</dt><dd>{textoDeQuien(orden.quien)}</dd>
    <dt>Ticket del ISP</dt><dd class:oc-mal={orden.ticket?.estado === 'no_cerrado'}>{textoDelTicket(orden.ticket)}</dd>
    {#if tiempos}<dt>Tiempos</dt><dd>{tiempos}</dd>{/if}
  </dl>

  {#if orden.solucion}<p class="oc-solucion">Qué hizo: «{orden.solucion}»</p>{/if}

  {#if orden.revision}
    <div class="oc-revision">
      <p><strong>Lo que revisó el Supervisor:</strong> {orden.revision.texto}</p>
      <ul>
        {#each orden.revision.puntos ?? [] as p (p.clave)}
          <li class="oc-punto-{String(p.ok)}"><span aria-hidden="true">{marca[String(p.ok)]}</span> {p.texto}</li>
        {/each}
      </ul>
    </div>
  {:else}
    <p class="oc-sin-foto snoc-secundario">Se cerró antes de que se guardara lo que revisaba el Supervisor.</p>
  {/if}

  {#if orden.historial?.length}
    <details class="oc-historial">
      <summary>Historial de la OT ({orden.historial.length})</summary>
      <ol>
        {#each orden.historial as h, i (i)}
          <li class="oc-de-{h.de}"><time>{h.cuando}</time> <span>{h.texto}</span></li>
        {/each}
      </ol>
    </details>
  {/if}
</article>

<style>
  .oc {
    display: grid;
    gap: 8px;
    padding: 12px 14px;
    background: var(--snoc-surface-container-lowest);
    border: 1px solid var(--snoc-outline-variant);
    border-radius: var(--snoc-r-xl);
    min-width: 0;
  }
  .oc-cabeza { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; font-size: 12px; }
  .oc-numero { font-family: 'JetBrains Mono', ui-monospace, monospace; font-weight: 600; color: var(--snoc-on-surface-variant); }
  .oc-cuadrilla {
    padding: 0 8px;
    border-radius: 999px;
    background: var(--snoc-surface-container);
    font-weight: 600;
    color: var(--snoc-on-surface-variant);
  }
  .oc-hora { margin-left: auto; color: var(--snoc-secondary); }
  .oc-asunto { margin: 0; font-size: 15px; line-height: 20px; font-weight: 600; color: var(--snoc-on-surface); overflow-wrap: anywhere; }
  .oc-quien { display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px; font-size: 13px; color: var(--snoc-on-surface-variant); }
  .oc-datos { margin: 0; display: grid; grid-template-columns: max-content 1fr; gap: 4px 12px; font-size: 13px; }
  .oc-datos dt { color: var(--snoc-secondary); }
  .oc-datos dd { margin: 0; font-weight: 600; overflow-wrap: anywhere; }
  .oc-mal { color: var(--snoc-error); }
  .oc-solucion { margin: 0; font-size: 13px; font-style: italic; color: var(--snoc-on-surface-variant); overflow-wrap: anywhere; }
  .oc-revision { display: grid; gap: 4px; padding: 8px 10px; border-radius: var(--snoc-r-xl); background: var(--snoc-surface-container-low); font-size: 13px; }
  .oc-revision p { margin: 0; }
  .oc-revision ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 2px; font-size: 12px; }
  .oc-punto-false { color: var(--snoc-error); font-weight: 600; }
  .oc-punto-null { color: #8a5300; }
  .oc-sin-foto { margin: 0; font-size: 12px; }
  .oc-historial { border-top: 1px solid var(--snoc-surface-container-high); padding-top: 8px; }
  .oc-historial summary { cursor: pointer; font-size: 13px; font-weight: 600; color: var(--snoc-on-surface-variant); }
  .oc-historial ol { list-style: none; margin: 8px 0 0; padding: 0; display: grid; gap: 4px; }
  .oc-historial li { display: grid; grid-template-columns: 88px 1fr; gap: 8px; font-size: 12px; }
  .oc-historial time { color: var(--snoc-secondary); font-variant-numeric: tabular-nums; }
  .oc-de-supervisor span { color: var(--snoc-primary); }
  .oc-de-alerta span { color: var(--snoc-error); font-weight: 600; }
</style>
