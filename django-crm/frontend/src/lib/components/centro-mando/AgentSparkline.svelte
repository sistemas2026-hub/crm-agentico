<script>
  /**
   * La actividad del agente en la ultima media hora, en 15 cubos de dos
   * minutos. Responde lo que el total no responde: si viene subiendo, si cayo
   * en seco o si lleva rato quieto. Un agente con diez llamadas hace veinte
   * minutos y otro con diez en el ultimo minuto traen el mismo total.
   */
  import { colorDe } from '$lib/centro-mando/estados.js';
  import { rutaSparkline, rutaArea, hayActividad } from '$lib/centro-mando/telemetria.js';

  /** @type {{ agente: any, ancho?: number, alto?: number }} */
  let { agente, ancho = 190, alto = 26 } = $props();

  const serie = $derived(agente.serie || []);
  const vivo = $derived(hayActividad(serie));
</script>

<div class="spark" style="--c:{colorDe(agente.estado)}">
  {#if vivo}
    <svg width="100%" height={alto} viewBox="0 0 {ancho} {alto}" preserveAspectRatio="none">
      <path class="area" d={rutaArea(serie, ancho, alto)} />
      <path class="linea" d={rutaSparkline(serie, ancho, alto)} />
    </svg>
  {:else}
    <div class="plano"></div>
  {/if}
  <span class="pie">últimos 30 min</span>
</div>

<style>
  .spark { display: flex; flex-direction: column; gap: 2px; }
  svg { display: block; overflow: visible; }
  .linea { fill: none; stroke: var(--c); stroke-width: 1.6; vector-effect: non-scaling-stroke; }
  .area { fill: var(--c); opacity: .14; }
  /* Sin actividad se dibuja la linea base, no un hueco: un espacio vacio
     parece un fallo de carga; una raya plana dice "no paso nada". */
  .plano { height: 26px; border-bottom: 1px dashed #cbd5e1; }
  .pie { font-family: ui-monospace, monospace; font-size: 8px; letter-spacing: .08em; color: #64748b; text-transform: uppercase; }
</style>
