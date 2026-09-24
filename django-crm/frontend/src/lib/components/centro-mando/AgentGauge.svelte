<script>
  /**
   * El anillo de carga: cuanto lleva este agente respecto al mas cargado de
   * la pantalla. La referencia comun es lo que hace que el anillo signifique
   * algo -- "16 conversaciones" suelto no dice nada; contra un maximo de 31,
   * dice la mitad.
   *
   * Dentro va la cifra cruda, porque la proporcion es para el ojo y el numero
   * es para decidir.
   */
  import { colorDe } from '$lib/centro-mando/estados.js';
  import { proporcionCarga, arcoAnillo } from '$lib/centro-mando/telemetria.js';

  /** @type {{ agente: any, referencia: number, radio?: number }} */
  let { agente, referencia, radio = 24 } = $props();

  const proporcion = $derived(proporcionCarga(agente.conversaciones, referencia));
  const arco = $derived(arcoAnillo(proporcion, radio));
  const lado = $derived((radio + 5) * 2);
</script>

<svg class="anillo" width={lado} height={lado} viewBox="0 0 {lado} {lado}" style="--c:{colorDe(agente.estado)}">
  <circle class="pista" cx={lado / 2} cy={lado / 2} r={radio} />
  {#if proporcion > 0}
    <circle
      class="carga"
      cx={lado / 2}
      cy={lado / 2}
      r={radio}
      stroke-dasharray="{arco.pintado} {arco.resto}"
      transform="rotate(-90 {lado / 2} {lado / 2})"
    />
  {/if}
  <text class="cifra" x={lado / 2} y={lado / 2 + 1}>{agente.conversaciones ?? 0}</text>
  <text class="et" x={lado / 2} y={lado / 2 + 12}>conv</text>
</svg>

<style>
  .anillo { flex-shrink: 0; }
  .pista { fill: none; stroke: #e2e8f0; stroke-width: 5; }
  .carga { fill: none; stroke: var(--c); stroke-width: 5; stroke-linecap: round; transition: stroke-dasharray .5s ease; }
  .cifra { fill: #0f172a; font-family: ui-monospace, monospace; font-size: 15px; font-weight: 700; text-anchor: middle; }
  .et { fill: #475569; font-size: 7.5px; letter-spacing: .1em; text-anchor: middle; text-transform: uppercase; }
</style>
