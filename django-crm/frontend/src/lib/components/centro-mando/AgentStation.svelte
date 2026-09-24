<script>
  /**
   * La estacion de un agente, como panel de instrumentos.
   *
   * POR QUE YA NO HAY UN RENDER DE PUESTO DETRAS
   * Hasta el 24/09/2026 cada tarjeta llevaba una imagen generada del pod de
   * trabajo. Se veia bien y no decia nada: ocupaba media tarjeta, pesaba 1,6
   * MB entre todas, y cada agente nuevo de cualquier empresa exigia producir
   * su render antes de poder mostrarlo. Ahora ese espacio lo ocupan dos
   * instrumentos que si responden preguntas -- cuanta carga lleva y como
   * viene -- y se dibujan en codigo, asi que un agente nuevo aparece solo.
   *
   * La cara del agente se queda: es la identidad de Dexter, no decorado, y
   * pesa 20 KB.
   */
  import AgentStatus from './AgentStatus.svelte';
  import AgentGauge from './AgentGauge.svelte';
  import AgentSparkline from './AgentSparkline.svelte';
  import { colorDe } from '$lib/centro-mando/estados.js';

  /** @type {{ agente: any, referencia?: number, alSeleccionar?: (a: any) => void, ms?: (v: any) => string }} */
  let { agente, referencia = 0, alSeleccionar = () => {}, ms = (v) => String(v ?? '—') } = $props();

  const PISTAS_CARA = [
    [/vent|comercial/, 'ventas'],
    [/factur|cartera|pago|cobr/, 'facturacion'],
    [/fibra|ftth|red|olt|tecnic/, 'soporte'],
    [/campo|instal|visita/, 'campo'],
    [/supervis|administra|analista/, 'supervisor'],
    [/identidad|verific/, 'identidad'],
    [/dato|analit|informe/, 'datos'],
    [/cliente|recepcion|router|chat|guiad|config/, 'router']
  ];

  const cara = $derived.by(() => {
    const texto = `${agente.nombre} ${agente.area || ''} ${agente.cargo || ''}`.toLowerCase();
    const encontrada = PISTAS_CARA.find(([patron]) => patron.test(texto));
    return `/centro-mando/avatares/${encontrada ? encontrada[1] : 'router'}.webp`;
  });
</script>

<button class="estacion" style="--c:{colorDe(agente.estado)}" onclick={() => alSeleccionar(agente)}>
  <div class="cabecera">
    <img class="cara" src={cara} alt="" />
    <div class="quien">
      <span class="nombre">{agente.nombre.replaceAll('_', ' ')}</span>
      <span class="cargo">{agente.cargo || agente.area || ''}</span>
    </div>
    <AgentStatus estado={agente.estado} />
  </div>

  <div class="instrumentos">
    <AgentGauge {agente} {referencia} />
    <AgentSparkline {agente} />
  </div>

  <div class="haciendo">{agente.haciendo || ''}</div>

  <div class="datos">
    {#if agente.esperando_humano}<span class="ambar">Humano <b>{agente.esperando_humano}</b></span>{/if}
    {#if agente.esperando_aprobacion}<span class="violeta">Sin comprobar <b>{agente.esperando_aprobacion}</b></span>{/if}
    {#if agente.duracion_media_ms}<span>{ms(agente.duracion_media_ms)}</span>{/if}
    {#if agente.fallos_ventana}<span class="rojo">{agente.fallos_ventana} fallos</span>{/if}
    {#if agente.abiertas_total}<span class="tenue">{agente.abiertas_total} sin cerrar</span>{/if}
  </div>
</button>

<style>
  .estacion {
    text-align: left; cursor: pointer; padding: 12px;
    background: #0f172a; border: 1px solid var(--c); border-radius: 12px;
    transition: transform .15s, box-shadow .15s;
    display: flex; flex-direction: column; gap: 10px;
  }
  .estacion:hover { transform: translateY(-2px); box-shadow: 0 0 22px color-mix(in srgb, var(--c) 35%, transparent); }

  .cabecera { display: flex; align-items: center; gap: 10px; }
  .cara {
    width: 34px; height: 34px; border-radius: 50%; object-fit: cover; flex-shrink: 0;
    border: 1.5px solid var(--c); box-shadow: 0 0 10px color-mix(in srgb, var(--c) 55%, transparent);
  }
  .quien { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .nombre { font-size: 12px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; color: #e6f1ff; line-height: 1.2; }
  .cargo { font-size: 10px; color: #8aa2c0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .instrumentos { display: flex; align-items: center; gap: 12px; }
  .instrumentos :global(.spark) { flex: 1; min-width: 0; }

  /* Alto minimo: sin el, una tarjeta con frase corta queda mas baja que su
     vecina y la rejilla se ve desalineada. */
  .haciendo { font-size: 11px; color: var(--c); line-height: 1.35; min-height: 30px; overflow-wrap: anywhere; }

  .datos { display: flex; gap: 10px; flex-wrap: wrap; font-family: ui-monospace, monospace; font-size: 10px; color: #8aa2c0; }
  .datos b { color: #e6f1ff; }
  .datos .ambar { color: #f59e0b; }
  .datos .violeta { color: #8b5cf6; }
  .datos .rojo { color: #ef4444; }
  .datos .tenue { color: #47607f; }
</style>
