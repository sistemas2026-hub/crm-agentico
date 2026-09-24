<script>
  /**
   * La estacion de un agente: su pod, quien es, que trae entre manos y su
   * carga. Es UN componente reutilizado por todos -- agregar un agente en la
   * configuracion del tenant no crea ningun archivo aqui.
   *
   * La Fase 2 le podra pasar `posicion` para colocarla en un mapa; hoy la
   * coloca la rejilla del contenedor, que es lo que aguanta que cada empresa
   * tenga un numero distinto de agentes.
   */
  import AgentAvatar from './AgentAvatar.svelte';
  import AgentStatus from './AgentStatus.svelte';
  import { colorDe } from '$lib/centro-mando/estados.js';

  /** @type {{ agente: any, alSeleccionar?: (a: any) => void, ms?: (v: any) => string }} */
  let { agente, alSeleccionar = () => {}, ms = (v) => String(v ?? '—') } = $props();
</script>

<button class="estacion" style="--c:{colorDe(agente.estado)}" onclick={() => alSeleccionar(agente)}>
  <AgentAvatar {agente} />
  <div class="ficha">
    <div class="fila1">
      <span class="nombre">{agente.nombre.replaceAll('_', ' ')}</span>
      <AgentStatus estado={agente.estado} />
    </div>
    <div class="cargo">{agente.cargo || agente.area || ''}</div>
    <div class="haciendo">{agente.haciendo || ''}</div>
    <div class="datos">
      <span>Conv <b>{agente.conversaciones}</b></span>
      {#if agente.esperando_humano}<span class="ambar">Humano <b>{agente.esperando_humano}</b></span>{/if}
      {#if agente.esperando_aprobacion}<span class="violeta">Sin comprobar <b>{agente.esperando_aprobacion}</b></span>{/if}
      {#if agente.duracion_media_ms}<span>{ms(agente.duracion_media_ms)}</span>{/if}
    </div>
  </div>
</button>

<style>
  .estacion {
    text-align: left; padding: 0; cursor: pointer; overflow: hidden;
    background: #0f172a; border: 1px solid var(--c); border-radius: 12px;
    transition: transform .15s, box-shadow .15s;
    display: flex; flex-direction: column;
  }
  .estacion:hover { transform: translateY(-2px); box-shadow: 0 0 22px color-mix(in srgb, var(--c) 40%, transparent); }
  .ficha { padding: 10px 12px 12px; display: flex; flex-direction: column; gap: 3px; }
  .fila1 { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
  .nombre { font-size: 12.5px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; line-height: 1.25; color: #e6f1ff; }
  .cargo { font-size: 10.5px; color: #8aa2c0; }
  /* Alto minimo: sin el, una tarjeta con frase corta queda mas baja que su
     vecina y la rejilla se ve desalineada. */
  .haciendo { font-size: 11px; color: var(--c); line-height: 1.35; margin-top: 3px; min-height: 30px; overflow-wrap: anywhere; }
  .datos { display: flex; gap: 10px; flex-wrap: wrap; font-family: ui-monospace, monospace; font-size: 10.5px; color: #8aa2c0; margin-top: 2px; }
  .datos b { color: #e6f1ff; }
  .datos .ambar { color: #f59e0b; }
  .datos .violeta { color: #8b5cf6; }
</style>
