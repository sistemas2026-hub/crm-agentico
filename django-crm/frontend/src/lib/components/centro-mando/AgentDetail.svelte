<script>
  /**
   * La ficha de un agente. Muestra los HECHOS que el motor midio -- ni uno
   * calculado aqui -- y dos salidas: a su configuracion y a la bandeja.
   */
  import { Button } from '$lib/components/ui/button/index.js';
  import { Users } from '@lucide/svelte';
  import AgentStatus from './AgentStatus.svelte';
  import AgentGauge from './AgentGauge.svelte';
  import AgentSparkline from './AgentSparkline.svelte';
  import { colorDe, ESTADOS, normalizar } from '$lib/centro-mando/estados.js';

  /** @type {{ agente: any, ventana: number, referencia?: number, hora: (v: any) => string,
   *           ms: (v: any) => string, alCerrar: () => void }} */
  let { agente, ventana, referencia = 0, hora, ms, alCerrar } = $props();

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
  function caraDe(/** @type {any} */ a) {
    const texto = `${a.nombre} ${a.area || ''} ${a.cargo || ''}`.toLowerCase();
    const hallada = PISTAS_CARA.find(([patron]) => patron.test(texto));
    return `/centro-mando/avatares/${hallada ? hallada[1] : 'router'}.webp`;
  }

  const cifras = $derived([
    [agente.conversaciones, 'Activas (24 h)', false],
    [agente.abiertas_total, 'Abiertas sin cerrar', false],
    [agente.esperando_humano, 'Esperan persona', false],
    [agente.esperando_cliente, 'Esperan al cliente', false],
    [agente.llamadas_ventana, `Herramientas (${ventana} min)`, false],
    [agente.fallos_ventana, 'Fallos recientes', agente.fallos_ventana > 0]
  ]);
</script>

<button class="telon" onclick={alCerrar} aria-label="Cerrar detalle"></button>
<aside class="detalle" style="--c:{colorDe(agente.estado)}">
  <header>
    <img class="retrato" src={caraDe(agente)} alt="" />
    <div>
      <h2>{agente.nombre.replaceAll('_', ' ')}</h2>
      <p>{agente.cargo || ''}{agente.area ? ` · ${agente.area}` : ''}</p>
      <AgentStatus estado={agente.estado} />
    </div>
    <button class="cerrar" onclick={alCerrar} aria-label="Cerrar">✕</button>
  </header>

  <div class="rejilla-cifras">
    {#each cifras as [valor, rotulo, rojo]}
      <div class:rojo><b>{valor ?? 0}</b><span>{rotulo}</span></div>
    {/each}
  </div>

  <div class="bloque">
    <h3>Ahora mismo</h3>
    <p>{agente.haciendo || 'Sin actividad.'}</p>
    <p class="pista">{ESTADOS[normalizar(agente.estado)].descripcion}</p>
  </div>

  <!-- Los dos instrumentos viven aqui y no en el disco del mapa: en el anillo
       compiten con los otros siete nodos y no se leen; en la ficha, que se
       abre para UN agente, responden lo que el total no responde -- cuanto
       lleva respecto al mas cargado, y si viene subiendo o cayo en seco. -->
  <div class="bloque instrumentos">
    <AgentGauge {agente} {referencia} />
    <AgentSparkline {agente} />
  </div>

  <div class="bloque">
    <h3>Descripción</h3>
    <p>{agente.descripcion || 'Sin descripción configurada.'}</p>
  </div>

  <div class="bloque">
    <h3>Última señal</h3>
    <p>
      {#if agente.ultima_herramienta}
        Última herramienta: <code>{agente.ultima_herramienta}</code><br />
      {/if}
      Última actividad: {hora(agente.ultima_actividad)}
      {#if agente.ultima_actividad}<span class="tz"> (Bogotá)</span>{/if}
      {#if agente.duracion_media_ms}<br />Duración media: {ms(agente.duracion_media_ms)}{/if}
    </p>
  </div>

  <footer>
    <Button href="/agentes" variant="outline" size="sm">Ver configuración</Button>
    <Button href="/conversaciones" size="sm">
      <Users class="mr-2 size-4" />Abrir bandeja
    </Button>
  </footer>
</aside>

<style>
  .telon { position: fixed; inset: 0; background: rgba(15,23,42,.45); backdrop-filter: blur(3px); border: 0; z-index: 40; }
  .detalle {
    position: fixed; top: 0; right: 0; height: 100%; width: 440px; z-index: 41;
    background: #ffffff; color: #0f172a; border-left: 1px solid var(--c);
    box-shadow: -18px 0 46px rgba(15,23,42,.18); display: flex; flex-direction: column; overflow-y: auto;
  }
  header { display: flex; gap: 14px; align-items: center; padding: 18px 16px; border-bottom: 1px solid #e2e8f0; position: relative; }
  .retrato { width: 76px; height: 76px; border-radius: 14px; object-fit: cover; border: 2px solid var(--c); flex-shrink: 0; }
  h2 { font-size: 18px; margin: 0 0 3px; text-transform: capitalize; }
  header p { font-size: 11.5px; color: #475569; margin: 0 0 8px; }
  .cerrar { position: absolute; top: 12px; right: 12px; width: 28px; height: 28px; border-radius: 8px; border: 1px solid #e2e8f0; background: #f1f5f9; color: #475569; cursor: pointer; }
  .rejilla-cifras { display: grid; grid-template-columns: repeat(3, 1fr); }
  .rejilla-cifras div { padding: 12px 8px; text-align: center; border-right: 1px solid #e2e8f0; border-bottom: 1px solid #e2e8f0; }
  .rejilla-cifras b { display: block; font-family: ui-monospace, monospace; font-size: 17px; }
  .rejilla-cifras span { font-size: 8.5px; letter-spacing: .08em; color: #475569; text-transform: uppercase; }
  .rejilla-cifras .rojo b { color: #b91c1c; }
  .bloque { padding: 14px 16px; border-bottom: 1px solid #e2e8f0; }
  .bloque h3 { font-family: ui-monospace, monospace; font-size: 10px; letter-spacing: .14em; color: #475569; text-transform: uppercase; margin: 0 0 8px; }
  .bloque p { font-size: 12.5px; line-height: 1.55; margin: 0; color: #334155; }
  .bloque .pista { font-size: 11px; color: #475569; margin-top: 6px; }
  .bloque code { font-family: ui-monospace, monospace; font-size: 11.5px; color: var(--c); }
  .tz { color: #64748b; }
  .instrumentos { display: flex; align-items: center; gap: 14px; }
  .instrumentos :global(.spark) { flex: 1; min-width: 0; }
  footer { margin-top: auto; padding: 14px 16px; display: flex; gap: 10px; }
</style>
