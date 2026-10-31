<!--
  RESUMEN DEL DÍA (31/10/2026): cuánto de lo publicado se terminó, cuánto
  queda, y el cumplimiento.

  El porcentaje lo calcula el servidor una sola vez
  (`campo/dia_publicado.py::cuentas.cumplimiento`). Dividir acá daría un número
  que ninguna prueba mira y que cada pantalla podría redondear distinto.
-->
<script>
  /** @type {{ cuentas: any }} */
  let { cuentas } = $props();

  let publicadas = $derived(cuentas?.publicadas ?? 0);
  let completadas = $derived(cuentas?.completadas ?? 0);
  let pendientes = $derived(cuentas?.pendientes ?? 0);
  let cumplimiento = $derived(cuentas?.cumplimiento ?? 0);
</script>

<section class="rd" aria-label="Resumen del día">
  <span class="snoc-label">Resumen del día</span>
  <div class="rd-cifras">
    <div><strong>{publicadas}</strong><span>Publicadas</span></div>
    <div><strong class="rd-ok">{completadas}</strong><span>Completadas</span></div>
    <div><strong class="rd-queda">{pendientes}</strong><span>Pendientes</span></div>
  </div>
  <div
    class="rd-barra"
    role="progressbar"
    aria-label="Cumplimiento de la jornada"
    aria-valuenow={cumplimiento}
    aria-valuemin="0"
    aria-valuemax="100"
  >
    <i style={`width:${cumplimiento}%`}></i>
  </div>
  <p class="rd-pie snoc-secundario">
    {#if publicadas}
      {cumplimiento}% de lo publicado está terminado
    {:else}
      Todavía no hay nada publicado para este día.
    {/if}
  </p>
</section>

<style>
  .rd { display: grid; gap: var(--snoc-xs); min-width: 0; }
  .rd-cifras { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--snoc-sm); text-align: center; }
  .rd-cifras strong {
    display: block;
    font-size: 26px;
    line-height: 1.1;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }
  .rd-cifras span { font-size: 12px; color: var(--snoc-on-surface-variant); }
  .rd-ok { color: var(--snoc-primary); }
  .rd-queda { color: #8a5300; }
  .rd-barra {
    height: 8px;
    border-radius: 999px;
    background: var(--snoc-surface-container-high);
    overflow: hidden;
  }
  .rd-barra i { display: block; height: 100%; background: var(--snoc-primary); }
  .rd-pie { margin: 0; font-size: 12px; }
</style>
