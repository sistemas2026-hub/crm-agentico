<script>
  /**
   * El centro de mando entero. Recibe un panorama y lo pinta; no sabe de
   * donde vino -- eso es cosa del AgentEventService -- ni calcula nada que el
   * motor no haya contado.
   *
   * COMO SE COLOCAN LAS ESTACIONES
   * Hoy, en una rejilla que acomoda el navegador. La Fase 2 puede agregar una
   * vista de mapa: la geometria ya esta resuelta y probada en
   * lib/centro-mando/disposicion.js, y AgentStation acepta que le digan donde
   * ponerse. Lo que no volvera es colocar por coordenadas escritas a mano:
   * con ocho agentes se encimaban, y cuantos hay lo decide cada empresa.
   */
  import AgentStation from './AgentStation.svelte';
  import AgentDetail from './AgentDetail.svelte';
  import MetricsPanel from './MetricsPanel.svelte';
  import EventTimeline from './EventTimeline.svelte';
  import ExternalToolNode from './ExternalToolNode.svelte';
  import OrchestratorNode from './OrchestratorNode.svelte';
  import { ordenar, repartoPorEstado } from '$lib/centro-mando/estados.js';

  /** @type {{ panorama: any, sello?: string|null }} */
  let { panorama, sello = null } = $props();

  let seleccionado = $state(/** @type {any} */ (null));

  const totales = $derived(panorama?.totales || {});
  const servicios = $derived(panorama?.servicios || []);
  const eventos = $derived(panorama?.eventos || []);
  const agentes = $derived(ordenar(panorama?.agentes || []));
  const reparto = $derived(repartoPorEstado(panorama?.agentes || []));

  const hora = (/** @type {string|null} */ iso) =>
    iso
      ? new Date(iso).toLocaleTimeString('es-CO', {
          hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'America/Bogota'
        })
      : '—';

  const ms = (/** @type {number|null} */ v) =>
    v == null ? '—' : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${v} ms`;

  // El agente abierto se refresca solo cuando llega un panorama nuevo: si no,
  // la ficha se queda con las cifras del momento en que se abrio.
  $effect(() => {
    if (!seleccionado) return;
    const fresco = (panorama?.agentes || []).find((a) => a.nombre === seleccionado.nombre);
    if (fresco && fresco !== seleccionado) seleccionado = fresco;
  });

  /* Alto minimo medido, no una constante restada a 100vh: el encabezado de la
     pagina cambia de alto con el ancho, y un numero fijo deja franja blanca en
     unas ventanas y scroll en otras. */
  function estirar(nodo) {
    const ajustar = () => {
      const arriba = nodo.getBoundingClientRect().top + window.scrollY;
      nodo.style.minHeight = `${Math.max(560, window.innerHeight - arriba - 14)}px`;
    };
    ajustar();
    window.addEventListener('resize', ajustar);
    return { destroy: () => window.removeEventListener('resize', ajustar) };
  }
</script>

<div class="sala" use:estirar>
  <div class="identidad">
    <span class="marca"><i></i>DEXTER <b>· CENTRO DE MANDO</b></span>
    <span class="tenant">{panorama.tenant}</span>
    <span class="sep"></span>
    <span class="dato">{agentes.length} agentes configurados</span>
    {#if totales.abiertas_total}
      <span class="dato">{totales.abiertas_total} abiertas sin cerrar</span>
    {/if}
    {#if totales.fallos_hoy}
      <span class="dato rojo">{totales.fallos_hoy} fallos hoy</span>
    {/if}
    <span class="reloj">{hora(sello || panorama.generado_en)} <em>(Bogotá)</em></span>
  </div>

  <MetricsPanel {totales} {ms} />

  <div class="cuerpo">
    <div class="tablero">
      <OrchestratorNode {totales} {reparto} />

      {#if servicios.length}
        <div class="servicios">
          <span class="et">Servicios usados hoy</span>
          {#each servicios as s (s.herramienta)}
            <ExternalToolNode servicio={s} {ms} />
          {/each}
        </div>
      {/if}

      <div class="rejilla">
        {#each agentes as a (a.nombre)}
          <AgentStation agente={a} {ms} alSeleccionar={(x) => (seleccionado = x)} />
        {/each}
      </div>
    </div>

    <EventTimeline {eventos} {hora} {ms} sello={hora(sello || panorama.generado_en)} />
  </div>
</div>

{#if seleccionado}
  <AgentDetail
    agente={seleccionado}
    ventana={panorama.ventana_min}
    {hora}
    {ms}
    alCerrar={() => (seleccionado = null)}
  />
{/if}

<style>
  .sala {
    background-color: #050b18;
    background-image: radial-gradient(ellipse at 50% 0%, rgba(0,229,255,.16), transparent 60%);
    color: #e6f1ff; border: 1px solid rgba(0,229,255,.14); border-radius: 14px;
    overflow: hidden; display: flex; flex-direction: column;
  }

  .identidad {
    display: flex; align-items: center; gap: 14px; padding: 9px 16px;
    border-bottom: 1px solid rgba(0,229,255,.14); font-size: 11px; color: #8aa2c0;
  }
  .marca { font-weight: 700; letter-spacing: .16em; color: #e6f1ff; display: flex; align-items: center; gap: 8px; }
  .marca b { font-weight: 500; letter-spacing: .18em; color: #8aa2c0; }
  .marca i { width: 7px; height: 7px; border-radius: 50%; background: #00e5ff; box-shadow: 0 0 9px #00e5ff; }
  .tenant { font-family: ui-monospace, monospace; letter-spacing: .08em; padding: 3px 9px; border: 1px solid rgba(0,229,255,.14); border-radius: 6px; text-transform: uppercase; }
  .sep { flex: 1; }
  .dato { font-family: ui-monospace, monospace; font-size: 10.5px; }
  .dato.rojo { color: #ef4444; }
  .reloj { font-family: ui-monospace, monospace; font-size: 11px; color: #e6f1ff; }
  .reloj em { color: #47607f; font-style: normal; }

  .cuerpo { flex: 1; display: flex; min-height: 0; }
  .tablero { flex: 1; min-width: 0; display: flex; flex-direction: column; overflow-y: auto; padding: 14px; gap: 14px; }

  .servicios { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .servicios .et { font-size: 10px; letter-spacing: .12em; text-transform: uppercase; color: #8aa2c0; margin-right: 4px; }

  /* auto-fill: cuantos agentes hay lo decide cada empresa y el ancho cambia
     con el menu lateral. Con columnas fijas, la novena tarjeta rompe la fila. */
  .rejilla { display: grid; grid-template-columns: repeat(auto-fill, minmax(236px, 1fr)); gap: 14px; align-content: start; }
</style>
