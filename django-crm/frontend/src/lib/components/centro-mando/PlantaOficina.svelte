<script>
  /**
   * La planta de la oficina: un puesto por agente, en rejilla isometrica.
   *
   * Es la segunda vista del centro de mando. La primera --el anillo de
   * discos-- sigue existiendo y no se toco: esta convive con ella, no la
   * reemplaza. El anillo esta medido en produccion desde el 24/09/2026 y
   * tirarlo para estrenar esto seria cambiar algo que funciona por algo que
   * todavia nadie miro en la operacion real.
   *
   * QUE APORTA SOBRE EL ANILLO
   * Hace visible la ESTRUCTURA del tenant, que el anillo no muestra: quien
   * atiende al cliente, quien trabaja para adentro, y por donde entran las
   * conversaciones (el `rol_de_entrada`). Todo eso ya viajaba en el panorama
   * y no se pintaba en ningun lado.
   *
   * LO QUE NO SE MUESTRA, A PROPOSITO
   * Nada del contenido de una conversacion: ni un mensaje, ni un nombre de
   * cliente, ni un numero (PRD RNF-01, y el docstring de
   * panorama_centro_mando: "tampoco viaja nada del cliente"). Un puesto dice
   * "consultar_olt · 342 ms" o "4 esperan a una persona"; nunca a quien.
   */
  import { untrack } from 'svelte';
  import PuestoAgente from './PuestoAgente.svelte';
  import { ESTADOS, normalizar } from '$lib/centro-mando/estados.js';
  import { rejillaPlanta, ordenDePintado, zonaDe, ZONAS, cambios } from '$lib/centro-mando/planta.js';

  /** @type {{ panorama: any, alSeleccionar?: (a:any)=>void }} */
  let { panorama, alSeleccionar = () => {} } = $props();

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

  const zonasPresentes = $derived(
    [...new Set(agentes.map((a) => zonaDe(a, entrada)))].sort((a, b) => ZONAS[a].orden - ZONAS[b].orden)
  );
</script>

<div class="planta" bind:this={envoltura}>
  <svg role="img" aria-label="Planta de la oficina: un puesto por cada agente"
    viewBox="0 0 {Math.max(1, caja.ancho)} {Math.max(1, caja.alto)}">
    <g transform="translate({encuadre.dx}, {encuadre.dy}) scale({encuadre.esc})">
      {#each pintado as i (agentes[i]?.nombre ?? i)}
        {#if agentes[i] && rej.celdas[i]}
          <g transform="translate({rej.celdas[i].x}, {rej.celdas[i].y})">
            <PuestoAgente
              agente={agentes[i]}
              numero={i + 1}
              lado={LADO}
              {entrada}
              ejes={rej.ejes}
              cambio={delta[agentes[i].nombre]}
              {ahora}
              {alSeleccionar}
            />
          </g>
        {/if}
      {/each}
    </g>
  </svg>

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
  svg { display: block; width: 100%; flex: 1; min-height: 0; }

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
