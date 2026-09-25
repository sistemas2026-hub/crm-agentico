<script>
  /**
   * La planta de la oficina: un puesto por agente, en rejilla isometrica.
   *
   * Es la UNICA vista del centro de mando desde el 24/09/2026. Nacio como la
   * segunda --convivia con un anillo de discos-- y ese anillo se retiro el
   * mismo dia, por decision de producto, cuando esta llevaba tres
   * despliegues verificados con datos reales.
   *
   * QUE MUESTRA QUE EL ANILLO NO MOSTRABA
   * La ESTRUCTURA del tenant: quien atiende al cliente, quien trabaja para
   * adentro, y por donde entran las conversaciones (el `rol_de_entrada`).
   * Todo eso ya viajaba en el panorama y no se pintaba en ningun lado.
   *
   * LO QUE NO SE MUESTRA, A PROPOSITO
   * Nada del contenido de una conversacion: ni un mensaje, ni un nombre de
   * cliente, ni un numero (PRD RNF-01, y el docstring de
   * panorama_centro_mando: "tampoco viaja nada del cliente"). Un puesto dice
   * "consultar_olt · 342 ms" o "4 esperan a una persona"; nunca a quien.
   */
  import { untrack } from 'svelte';
  import PuestoAgente from './PuestoAgente.svelte';
  import SistemasExternos from './SistemasExternos.svelte';
  import ActividadViva from './ActividadViva.svelte';
  import { ESTADOS, normalizar } from '$lib/centro-mando/estados.js';
  import { rejillaPlanta, ordenDePintado, zonaDe, ZONAS, cambios } from '$lib/centro-mando/planta.js';

  /** @type {{ panorama: any, ms?: (v:any)=>string, alSeleccionar?: (a:any)=>void }} */
  let {
    panorama,
    ms = (v) => (v == null ? '—' : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${v} ms`),
    alSeleccionar = () => {}
  } = $props();

  let caja = $state({ ancho: 0, alto: 0 });
  let envoltura = $state(/** @type {HTMLDivElement|null} */ (null));

  const entrada = $derived(panorama?.rol_de_entrada || null);

  /* Orden de lectura: primero la ZONA, y dentro de cada una lo que exige
     atencion. Agrupar por zona hace visible la estructura del tenant. */
  const agentes = $derived(
    [...(panorama?.agentes || [])].sort((a, b) =>
      ZONAS[zonaDe(a, entrada)].orden - ZONAS[zonaDe(b, entrada)].orden ||
      ESTADOS[normalizar(a.estado)].orden - ESTADOS[normalizar(b.estado)].orden ||
      (b.conversaciones || 0) - (a.conversaciones || 0) ||
      String(a.nombre).localeCompare(String(b.nombre))
    )
  );

  /* QUE CAMBIO ENTRE DOS FOTOS.
     Los datos llegan por sondeo cada 12 s, asi que no hay tiempo real que
     animar: lo unico honesto es la diferencia entre dos lecturas. Se guarda
     la anterior con untrack para que recalcular los cambios no dispare otra
     vuelta del efecto. */
  let anteriores = $state(/** @type {any[]} */ ([]));
  let delta = $state(/** @type {Record<string, any>} */ ({}));
  $effect(() => {
    const ahora = panorama?.agentes || [];
    const previos = untrack(() => anteriores);
    delta = cambios(previos, ahora);
    anteriores = ahora;
  });

  /* El sello de frescura: cuantos segundos hace que se leyo la operacion.
     Es lo menos vistoso de esta pantalla y lo mas importante -- deja dicho
     que lo que se ve es una FOTO cada 12 segundos y no un flujo continuo.
     Sin el, una planta que se mueve sugiere continuidad que no existe. */
  let ahora = $state(new Date());
  $effect(() => {
    const t = setInterval(() => (ahora = new Date()), 1000);
    return () => clearInterval(t);
  });
  const segundosDesdeLaLectura = $derived.by(() => {
    if (!panorama?.generado_en) return null;
    return Math.max(0, Math.round((ahora.getTime() - new Date(panorama.generado_en).getTime()) / 1000));
  });

  const LADO = 100, SEP = 30;
  /* Arriba: el rotulo cuelga de la pared y la chapa de "esperan" sobresale
     otro tanto. Abajo: el halo de foco, 4 unidades por fuera del puesto. Un
     margen corto no se ve con ocho agentes y desborda con diez. */
  const MARGEN_SUP = LADO * 0.88, MARGEN_INF = LADO * 0.18, MARGEN_LAT = 24;

  const rej = $derived(
    rejillaPlanta(agentes.length, {
      ancho: Math.max(120, caja.ancho - MARGEN_LAT * 2),
      alto: Math.max(120, caja.alto),
      lado: LADO, separacion: SEP,
      holguraAlto: (MARGEN_SUP + MARGEN_INF) / LADO
    })
  );

  const encuadre = $derived.by(() => {
    const esc = rej.escala;
    const anchoTotal = rej.ancho * esc;
    const altoTotal = (rej.alto + MARGEN_SUP + MARGEN_INF) * esc;
    return {
      dx: (caja.ancho - anchoTotal) / 2,
      dy: (caja.alto - altoTotal) / 2 + MARGEN_SUP * esc,
      esc
    };
  });

  /* En isometrica lo que esta mas adelante se pinta DESPUES, o los tabiques
     del puesto de atras tapan el escritorio del de adelante. */
  const pintado = $derived(ordenDePintado(rej.celdas));

  $effect(() => {
    if (!envoltura) return;
    const ro = new ResizeObserver(([e]) => {
      caja = { ancho: e.contentRect.width, alto: e.contentRect.height };
    });
    ro.observe(envoltura);
    return () => ro.disconnect();
  });

  /* Donde esta cada puesto, por nombre. Lo necesita la capa de actividad:
     un puesto se dibuja a si mismo y no sabe donde estan los demas, asi que
     lo que va DE un sitio A otro no lo puede dibujar el. El punto es el
     centro del piso del modulo, no su esquina. */
  const posiciones = $derived.by(() => {
    /** @type {Record<string, {x:number,y:number}>} */
    const m = {};
    rej.celdas.forEach((c, i) => {
      const a = agentes[i];
      if (a) m[a.nombre] = { x: c.x, y: c.y + LADO * rej.ejes.ey };
    });
    return m;
  });

  const zonasPresentes = $derived(
    [...new Set(agentes.map((a) => zonaDe(a, entrada)))].sort((a, b) => ZONAS[a].orden - ZONAS[b].orden)
  );

  /* ------------------------------------------------------------ LA CAMARA
     Rueda para acercar, arrastrar para mover, "Ajustar" para volver.

     Vive APARTE del encuadre automatico, y esa separacion es lo que hace que
     funcione: el encaje se recalcula solo con cada foto --cuantas columnas,
     que escala, donde centrar-- y la camara se aplica ENCIMA. Asi la planta
     se repinta cada 12 segundos con datos nuevos sin devolverle la vista a su
     sitio: quien se acerco a un puesto sigue mirando ese puesto. */
  let vista = $state({ k: 1, x: 0, y: 0 });
  const MIN_K = 0.6, MAX_K = 5;
  const enSuSitio = $derived(vista.k === 1 && vista.x === 0 && vista.y === 0);

  function acercar(factor, cx, cy) {
    const k = Math.max(MIN_K, Math.min(MAX_K, vista.k * factor));
    if (k === vista.k) return;
    /* El punto bajo el cursor se queda quieto: es lo que hace que acercar se
       sienta como acercarse a un sitio y no como que la escena se escape. */
    const r = k / vista.k;
    vista = { k, x: cx - (cx - vista.x) * r, y: cy - (cy - vista.y) * r };
  }

  function alaRueda(ev) {
    ev.preventDefault();
    const c = envoltura.getBoundingClientRect();
    acercar(ev.deltaY < 0 ? 1.12 : 1 / 1.12, ev.clientX - c.x, ev.clientY - c.y);
  }

  let arrastre = $state(/** @type {any} */ (null));
  const UMBRAL = 4;

  function alBajar(ev) {
    if (ev.button !== 0) return;
    /* NO se captura el puntero aqui, y ese detalle es el que rompio abrir la
       ficha de un agente (24/09/2026, visto en produccion).
       Con `setPointerCapture` activa, el elemento capturador se queda con
       todos los eventos de puntero Y con el `click` que sale del par
       pointerdown/pointerup: el evento se dispara en el DIV del lienzo y no
       en el <g> del puesto, asi que el `onclick` del puesto no corria nunca.
       Pulsar un agente dejaba de mostrar su ficha, sin ningun error.
       Se captura mas abajo, solo cuando el gesto resulta ser un arrastre de
       verdad. Un clic limpio no captura nada y llega a su destino. */
    arrastre = { x: ev.clientX, y: ev.clientY, vx: vista.x, vy: vista.y, movido: 0, capturado: false };
  }

  function alMover(ev) {
    if (!arrastre) return;
    const dx = ev.clientX - arrastre.x, dy = ev.clientY - arrastre.y;
    arrastre.movido = Math.max(arrastre.movido, Math.abs(dx) + Math.abs(dy));
    if (arrastre.movido < UMBRAL) return;   // todavia puede ser un clic
    /* Ya es un arrastre: ahora si conviene capturar, para que siga
       funcionando aunque el cursor se salga del lienzo. */
    if (!arrastre.capturado) {
      arrastre.capturado = true;
      try { ev.currentTarget.setPointerCapture(ev.pointerId); } catch { /* sin captura */ }
    }
    vista = { ...vista, x: arrastre.vx + dx, y: arrastre.vy + dy };
  }

  /* Un gesto de menos de 4 px cuenta como clic. Sin este umbral, abrir la
     ficha de un puesto se vuelve imposible: el dedo siempre mueve algo.
     Se mira `ultimoGesto` y no `arrastre`, porque para cuando llega el
     `click` el `pointerup` ya limpio el arrastre -- leerlo ahi daba siempre
     null y el umbral no filtraba nada. */
  let ultimoGesto = $state(0);
  function alSoltarGesto() {
    ultimoGesto = arrastre ? arrastre.movido : 0;
    arrastre = null;
  }

  function seleccionar(a) {
    if (ultimoGesto >= UMBRAL) return;
    alSeleccionar(a);
  }

  function ajustar() { vista = { k: 1, x: 0, y: 0 }; }
  function botonZoom(f) {
    const c = envoltura?.getBoundingClientRect();
    if (c) acercar(f, c.width / 2, c.height / 2);
  }

  /* ----------------------------------------------------------- LOS FILTROS
     Lo primero que se pide en una operacion real: "mostrame solo los que
     tienen errores". Atenua en vez de esconder -- la planta no cambia de
     forma al filtrar, asi que no hay que volver a ubicarse cada vez. */
  let filtro = $state('todos');
  const FILTROS = {
    todos: { rotulo: 'Todos', test: () => true },
    llaman: {
      rotulo: 'Esperan a alguien',
      test: (a) => (a.esperando_humano || 0) + (a.esperando_aprobacion || 0) > 0
    },
    error: { rotulo: 'Con errores', test: (a) => normalizar(a.estado) === 'error' },
    trabajan: { rotulo: 'Trabajando', test: (a) => normalizar(a.estado) === 'working' },
    libres: { rotulo: 'Disponibles', test: (a) => normalizar(a.estado) === 'idle' }
  };
  const cuentas = $derived(
    Object.fromEntries(Object.entries(FILTROS).map(([k, f]) => [k, agentes.filter(f.test).length]))
  );
  const pasa = (a) => (FILTROS[filtro] || FILTROS.todos).test(a);
</script>

<div class="planta">
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div
    class="lienzo"
    class:arrastrando={!!arrastre}
    bind:this={envoltura}
    onwheel={alaRueda}
    onpointerdown={alBajar}
    onpointermove={alMover}
    onpointerup={alSoltarGesto}
    onpointercancel={alSoltarGesto}
    ondblclick={ajustar}
  >
    <svg role="img" aria-label="Planta de la oficina: un puesto por cada agente"
      viewBox="0 0 {Math.max(1, caja.ancho)} {Math.max(1, caja.alto)}">
      <!-- Dos transformaciones compuestas: primero la de la camara, despues
           la del encaje automatico. El orden importa -- al reves, mover la
           vista escalaria tambien el desplazamiento. -->
      <g transform="translate({vista.x}, {vista.y}) scale({vista.k}) translate({encuadre.dx}, {encuadre.dy}) scale({encuadre.esc})">
        {#each pintado as i (agentes[i]?.nombre ?? i)}
          {#if agentes[i] && rej.celdas[i]}
            <g class="celda" class:apagado={!pasa(agentes[i])}
               transform="translate({rej.celdas[i].x}, {rej.celdas[i].y})">
              <PuestoAgente
                agente={agentes[i]}
                numero={i + 1}
                lado={LADO}
                {entrada}
                ejes={rej.ejes}
                cambio={delta[agentes[i].nombre]}
                {ahora}
                alSeleccionar={seleccionar}
              />
            </g>
          {/if}
        {/each}
        <ActividadViva eventos={panorama?.eventos || []} {posiciones} lado={LADO} />
      </g>
    </svg>

    <div class="camara">
      <button onclick={() => botonZoom(1 / 1.3)} title="Alejar" aria-label="Alejar">−</button>
      <button onclick={() => botonZoom(1.3)} title="Acercar" aria-label="Acercar">+</button>
      <button onclick={ajustar} disabled={enSuSitio} title="Volver al encuadre automático">Ajustar</button>
    </div>
  </div>

  <div class="filtros">
    {#each Object.entries(FILTROS) as [k, f] (k)}
      <button class:activo={filtro === k} disabled={cuentas[k] === 0 && k !== 'todos'}
        onclick={() => (filtro = k)}>
        {f.rotulo}<span class="n">{cuentas[k]}</span>
      </button>
    {/each}
  </div>

  <SistemasExternos servicios={panorama?.servicios || []} {ms} />

  <div class="pieplanta">
    {#if !entrada}
      <!-- Se dice que falta en vez de adivinarlo: deducir la puerta de
           entrada del "primer rol orientado al cliente" es el error que dejo
           a un suscriptor sin internet hablando con el agente comercial. -->
      <span class="falta" title="El motor no envió rol_de_entrada para este tenant">
        Sin recepción declarada
      </span>
    {/if}
    {#each zonasPresentes as z (z)}
      <span class="zona"><i style="background:{ZONAS[z].color}"></i>{ZONAS[z].rotulo}</span>
    {/each}
    <span class="crece"></span>
    {#if segundosDesdeLaLectura != null}
      <span class="frescura" title="Los datos llegan por sondeo: lo que se ve es una lectura, no un flujo continuo">
        leído hace {segundosDesdeLaLectura}s
      </span>
    {/if}
  </div>
</div>

<style>
  .planta { position: relative; width: 100%; height: 100%; min-height: 320px; display: flex; flex-direction: column; }
  /* El lienzo se arrastra: el cursor lo anuncia antes de que nadie lo
     intente. `touch-action:none` es lo que deja que el gesto lo maneje la
     pantalla en vez del navegador. */
  .lienzo { position: relative; flex: 1; min-height: 0; cursor: grab; touch-action: none; overflow: hidden; }
  .lienzo.arrastrando { cursor: grabbing; }
  svg { display: block; width: 100%; height: 100%; }

  /* El filtro ATENUA en vez de esconder: la planta no cambia de forma, asi
     que no hay que volver a ubicarse en cada filtro. */
  .celda { transition: opacity .2s ease; }
  .celda.apagado { opacity: .14; pointer-events: none; }

  .camara { position: absolute; right: 8px; bottom: 8px; display: flex; gap: 4px; }
  .camara button {
    font: inherit; font-size: 11px; font-weight: 700; line-height: 1;
    padding: 5px 9px; border: 1px solid #c9d1dc; border-radius: 5px;
    background: rgb(255 255 255 / 92%); color: #475569; cursor: pointer;
  }
  .camara button:hover:not(:disabled) { background: #f1f5f9; color: #0f172a; }
  .camara button:disabled { opacity: .4; cursor: default; }

  .filtros { flex: 0 0 auto; display: flex; gap: 5px; flex-wrap: wrap; padding: 6px 0 0; }
  .filtros button {
    font: inherit; font-size: 10.5px; font-weight: 700; letter-spacing: .03em;
    padding: 4px 10px; border: 1px solid #c9d1dc; border-radius: 5px;
    background: #fff; color: #475569; cursor: pointer;
  }
  .filtros button:hover:not(:disabled) { background: #f1f5f9; }
  .filtros button.activo { background: #0f172a; border-color: #0f172a; color: #fff; }
  .filtros button:disabled { opacity: .4; cursor: default; }
  .filtros .n { font-family: ui-monospace, monospace; opacity: .75; margin-left: 5px; }

  @media (prefers-reduced-motion: reduce) { .celda { transition: none; } }

  .pieplanta {
    flex: 0 0 auto; display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
    padding: 6px 4px 0;
  }
  .zona, .frescura, .falta {
    display: flex; align-items: center; gap: 5px;
    font-size: 9px; letter-spacing: .06em; text-transform: uppercase; font-weight: 600;
    color: #475569;
  }
  .zona i { width: 9px; height: 9px; border-radius: 2px; }
  .crece { flex: 1; }
  .frescura { font-family: ui-monospace, monospace; color: #94A3B8; letter-spacing: .04em; }
  .falta {
    color: #92400E; background: #FEF3C7; border: 1px solid #FCD34D;
    border-radius: 4px; padding: 2px 7px;
  }
</style>
