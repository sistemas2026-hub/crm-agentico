<script>
  /**
   * El orquestador: quien recibe lo que entra y lo reparte. No es un agente
   * mas -- no tiene conversaciones propias -- asi que se muestra aparte, como
   * cabecera de la sala, con lo que esta moviendo ahora mismo.
   *
   * En la Fase 2 este mismo componente es el nodo central del mapa y de el
   * salen las FlowLine hacia cada estacion. Por eso recibe ya el reparto por
   * estado: es lo que decidira el color y el grosor de cada flujo.
   */
  import { ESTADOS, normalizar } from '$lib/centro-mando/estados.js';

  /** @type {{ totales: any, reparto: Record<string, number> }} */
  let { totales, reparto } = $props();

  // Solo los estados presentes, en el orden de urgencia de la tabla.
  const presentes = $derived(
    Object.entries(reparto)
      .map(([estado, n]) => ({ estado: normalizar(estado), n }))
      .sort((a, b) => ESTADOS[a.estado].orden - ESTADOS[b.estado].orden)
  );
</script>

<div class="orquestador">
  <div class="nucleo">
    <span class="rot">Orquestador</span>
    <span class="n">{totales.conversaciones_activas ?? 0}</span>
    <span class="sub">en curso</span>
  </div>
  <div class="reparto">
    {#each presentes as p}
      <span class="tramo" style="--c:{ESTADOS[p.estado].color}">
        <i></i>{p.n} {ESTADOS[p.estado].rotulo.toLowerCase()}
      </span>
    {/each}
  </div>
  {#if totales.esperando_humano}
    <span class="humano">{totales.esperando_humano} esperan a una persona</span>
  {/if}
</div>

<style>
  .orquestador {
    display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
    padding: 10px 14px; border: 1px solid rgba(0,229,255,.22); border-radius: 12px;
    background: linear-gradient(90deg, rgba(0,229,255,.08), transparent 60%);
  }
  .nucleo { display: flex; align-items: baseline; gap: 8px; }
  .rot { font-family: ui-monospace, monospace; font-size: 9.5px; letter-spacing: .18em; text-transform: uppercase; color: #00e5ff; }
  .n { font-family: ui-monospace, monospace; font-size: 24px; font-weight: 700; color: #e6f1ff; line-height: 1; }
  .sub { font-size: 10px; letter-spacing: .1em; text-transform: uppercase; color: #8aa2c0; }
  .reparto { display: flex; gap: 12px; flex-wrap: wrap; }
  .tramo { font-family: ui-monospace, monospace; font-size: 10.5px; color: var(--c); display: inline-flex; align-items: center; gap: 6px; }
  .tramo i { width: 7px; height: 7px; border-radius: 50%; background: var(--c); box-shadow: 0 0 7px var(--c); }
  .humano { margin-left: auto; font-family: ui-monospace, monospace; font-size: 10.5px; color: #f59e0b; }
</style>
