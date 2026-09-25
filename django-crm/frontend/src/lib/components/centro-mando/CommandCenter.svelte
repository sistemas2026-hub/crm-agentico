<script>
  /**
   * El centro de mando entero. Recibe un panorama y lo pinta; no sabe de
   * donde vino --eso es cosa del AgentEventService-- ni calcula nada que el
   * motor no haya contado.
   *
   * LA PLANTA ES LA UNICA VISTA DESDE EL 24/09/2026
   * Hubo una segunda, un anillo de discos con vias entre ellos, que estuvo en
   * produccion desde esa mañana. Se retiro el mismo dia, por decision de
   * producto, cuando la planta llevaba tres despliegues verificados con datos
   * reales. No fue un capricho de limpieza: dos vistas de lo mismo son dos
   * cosas que mantener, dos que probar y dos que envejecen, y la planta dice
   * todo lo que decia el anillo mas la estructura del tenant --quien atiende
   * al cliente, quien trabaja para adentro, por donde entran las
   * conversaciones-- que el anillo no mostraba.
   *
   * Lo que se fue con el: AgentStation.svelte, OrchestratorNode.svelte y
   * lib/centro-mando/disposicion.js con sus pruebas. Vivian solo para el
   * anillo y quedaban sin un solo consumidor. Estan en la historia de git
   * (hasta `2f14565`) si alguna vez hay que mirar como se resolvia colocar
   * piezas sobre una elipse: ese archivo tenia cuatro lecciones medidas y
   * ninguna se perdio, solo dejo de estar en la rama.
   *
   * LO QUE NO SE FUE, y por que: AgentDetail y sus piezas --Gauge, Sparkline,
   * Status, telemetria.js-- no eran del anillo. Son la ficha que se abre al
   * pulsar un puesto, y la planta la usa igual.
   */
  import { untrack } from 'svelte';
  import PlantaOficina from './PlantaOficina.svelte';
  import AgentDetail from './AgentDetail.svelte';
  import MetricsPanel from './MetricsPanel.svelte';
  import EventTimeline from './EventTimeline.svelte';
  import ExternalToolNode from './ExternalToolNode.svelte';
  import { cargaMaxima } from '$lib/centro-mando/telemetria.js';

  /** @type {{ panorama: any, sello?: string|null }} */
  let { panorama, sello = null } = $props();

  let seleccionado = $state(/** @type {any} */ (null));

  const totales = $derived(panorama?.totales || {});
  const servicios = $derived(panorama?.servicios || []);
  const eventos = $derived(panorama?.eventos || []);
  const agentes = $derived(panorama?.agentes || []);
  const referencia = $derived(cargaMaxima(panorama?.agentes || []));

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
  //
  // La dependencia es el panorama, y SOLO el panorama: este efecto escribe
  // `seleccionado`, asi que leerlo fuera de untrack lo vuelve dependiente de su
  // propia escritura. Eso reventaba con effect_update_depth_exceeded al abrir
  // la ficha, y a partir de ahi Svelte deja de re-ejecutar efectos.
  $effect(() => {
    const lista = panorama?.agentes || [];
    untrack(() => {
      if (!seleccionado) return;
      const fresco = lista.find((a) => a.nombre === seleccionado.nombre);
      if (fresco && fresco !== seleccionado) seleccionado = fresco;
    });
  });

  /**
   * El alto de la sala: lo que queda de ventana desde donde empieza. Medido,
   * no una constante restada a 100vh -- el encabezado de la pagina cambia de
   * alto con el ancho, y un numero fijo deja franja blanca en unas ventanas y
   * scroll en otras.
   */
  function estirar(/** @type {HTMLElement} */ nodo) {
    const ajustar = () => {
      const arriba = nodo.getBoundingClientRect().top + window.scrollY;
      nodo.style.height = `${Math.max(560, window.innerHeight - arriba - 14)}px`;
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
    <div class="mapa">
      <PlantaOficina {panorama} alSeleccionar={(x) => (seleccionado = x)} />
    </div>

    <div class="lateral">
      <EventTimeline {eventos} {hora} {ms} sello={hora(sello || panorama.generado_en)} />
      {#if servicios.length}
        <div class="servicios">
          <span class="et">Servicios usados hoy</span>
          {#each servicios as s (s.herramienta)}
            <ExternalToolNode servicio={s} {ms} />
          {/each}
        </div>
      {/if}
    </div>
  </div>
</div>

{#if seleccionado}
  <AgentDetail
    agente={seleccionado}
    ventana={panorama.ventana_min}
    {referencia}
    {hora}
    {ms}
    alCerrar={() => (seleccionado = null)}
  />
{/if}

<style>
  .sala {
    background: #fff;
    background-image: radial-gradient(ellipse at 50% 40%, rgba(14,116,144,.06), transparent 62%);
    color: #0f172a; border: 1px solid #e2e8f0; border-radius: 14px;
    overflow: hidden; display: flex; flex-direction: column;
    min-height: 560px;
  }

  .identidad {
    display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
    padding: 9px 16px; border-bottom: 1px solid #e2e8f0; font-size: 11px;
  }
  .marca { font-weight: 700; letter-spacing: .16em; color: #0f172a; display: flex; align-items: center; gap: 8px; }
  .marca b { font-weight: 500; letter-spacing: .18em; color: #475569; }
  .marca i { width: 7px; height: 7px; border-radius: 50%; background: #0e7490; }
  .tenant { font-family: ui-monospace, monospace; letter-spacing: .08em; padding: 3px 9px; border: 1px solid #e2e8f0; border-radius: 6px; text-transform: uppercase; }
  .sep { flex: 1; }
  .dato { font-family: ui-monospace, monospace; font-size: 10.5px; }
  .dato.rojo { color: #b91c1c; }
  .reloj { font-family: ui-monospace, monospace; font-size: 11px; color: #0f172a; }
  .reloj em { color: #64748b; font-style: normal; }

  .cuerpo { flex: 1; display: flex; min-height: 0; }
  /* La planta trae su propio lienzo, su encaje y sus mandos: aqui solo se le
     da el sitio. */
  .mapa { flex: 1; min-width: 0; min-height: 0; display: flex; padding: 0 10px 8px; }

  .lateral { flex: 0 0 319px; display: flex; flex-direction: column; min-height: 0; border-left: 1px solid #e2e8f0; }
  .lateral :global(.eventos) { flex: 1; min-height: 0; border-left: 0; }
  .servicios { display: flex; flex-wrap: wrap; align-content: start; gap: 8px; padding: 10px 14px; border-top: 1px solid #e2e8f0; background: #f8fafc; max-height: 132px; overflow-y: auto; }
  .servicios .et { font-size: 10px; letter-spacing: .12em; text-transform: uppercase; color: #475569; margin-right: 4px; }

  @media (max-width: 1100px) {
    .cuerpo { flex-direction: column; }
    .lateral { flex: 0 0 auto; border-left: 0; border-top: 1px solid #e2e8f0; max-height: 300px; }
  }
</style>
