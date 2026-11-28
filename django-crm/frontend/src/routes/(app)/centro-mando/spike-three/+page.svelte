<script>
  /**
   * EL PROTOTIPO DE THREE.JS, PARA COMPARAR. No reemplaza a `/centro-mando`.
   *
   * Existe porque el 01/11/2026 el diseño de PixiJS no se aprobó por una razón
   * concreta y medida —el edificio es una franja de 88 × 18 unidades, esbeltez
   * 4,85— y porque la causa de esa franja no es el dibujo sino la estrategia
   * de oclusión. Esta pantalla pone la misma empresa, con los mismos datos, en
   * una planta compacta de 40 × 38, esbeltez 1,05.
   *
   * La decisión de motor NO está tomada. Esto es la evidencia para tomarla.
   */
  import { onDestroy } from 'svelte';
  import { pisosDe, salasDe } from '$lib/centro-mando/departamentos.js';
  import { montarThree } from '$lib/centro-mando/three/escena-three.js';
  import { edificioCompacto } from '$lib/centro-mando/three/distribucion.js';

  let { data } = $props();

  const SALAS = salasDe(data.organizacion);
  const PISOS = pisosDe(data.organizacion, SALAS);

  let escena = $state(null);
  let soloNivel = $state(null);
  let modo = $state('corte');
  let seleccionada = $state(null);
  let metricas = $state({ fps: 0, fpsMinimo: 0, objetos: 0, motor: '—', llamadas: 0, triangulos: 0 });
  let reloj;

  const huella = $derived(edificioCompacto(PISOS).huella);
  const esbeltez = $derived(
    huella.fondo > 0 ? (huella.ancho / huella.fondo).toFixed(2) : '—'
  );
  const sala = $derived(seleccionada ? SALAS.find((s) => s.id === seleccionada) : null);

  /**
   * Montar con una ACCIÓN y no con un `$effect` sobre `bind:this`.
   *
   * Con el efecto, la primera carga dejaba el lienzo vacío: el efecto corría
   * antes de que `bind:this` tuviera el nodo y no volvía a correr hasta que
   * cambiaba otra cosa. Se veía como una pantalla negra sin un solo error en
   * la consola, que es la peor forma de fallar. Una acción corre EXACTAMENTE
   * cuando el nodo existe, y ese es todo el motivo.
   */
  function montar(nodo) {
    escena = montarThree(nodo, {
      pisos: PISOS,
      soloNivel: null,
      modo: 'corte',
      alSeleccionar: (id) => (seleccionada = id)
    });
    reloj = setInterval(() => {
      if (escena) metricas = escena.metricas();
    }, 500);
    return {
      destroy() {
        clearInterval(reloj);
        escena?.destruir();
        escena = null;
      }
    };
  }

  $effect(() => {
    escena?.aplicar({ soloNivel, modo });
  });

  onDestroy(() => {
    clearInterval(reloj);
    escena?.destruir();
  });
</script>

<svelte:head><title>Spike Three.js · El edificio compacto</title></svelte:head>

<div class="pantalla">
  <header>
    <div class="titulo">
      <h1>Prototipo Three.js <span class="marca">comparación, no reemplazo</span></h1>
      <p>
        {SALAS.filter((s) => s.tipo === 'departamento').length} departamentos ·
        {PISOS.length} piso(s) · huella {huella.ancho} × {huella.fondo} ·
        esbeltez {esbeltez}
        <a href="/centro-mando">ver la oficina en PixiJS</a>
      </p>
    </div>
    <div class="mandos">
      <button class:activo={soloNivel === null} onclick={() => (soloNivel = null)}>
        El edificio
      </button>
      {#each PISOS as p (p.nivel)}
        <button class:activo={soloNivel === p.nivel} onclick={() => (soloNivel = p.nivel)}>
          P{p.nivel}
        </button>
      {/each}
      <span class="separador"></span>
      <button class:activo={modo === 'corte'} onclick={() => (modo = 'corte')}>Corte</button>
      <button class:activo={modo === 'seccion'} onclick={() => (modo = 'seccion')}>Sección</button>
      <button class:activo={modo === 'rayosX'} onclick={() => (modo = 'rayosX')}>Rayos X</button>
      <button onclick={() => escena?.encuadrar()}>Encuadrar</button>
      <span class="telemetria">
        {metricas.fps} fps · mín {metricas.fpsMinimo} · {metricas.objetos} obj ·
        {metricas.llamadas} llamadas · {metricas.triangulos} tri · {metricas.motor}
      </span>
    </div>
  </header>

  {#if SALAS.length === 0}
    <p class="vacio">
      {data.error ?? 'Esta empresa todavía no declaró su estructura.'}
      Esta pantalla no inventa un edificio.
    </p>
  {:else}
    <div class="lienzo" use:montar></div>
  {/if}

  {#if sala}
    <aside>
      <h2>{sala.rotulo}</h2>
      <p>{sala.tipo} · piso {sala.piso} · {sala.planta.puestos.length} puestos</p>
      <ul>
        {#each sala.planta.puestos as p (p.id)}
          <li class:ocupado={p.agente || p.persona}>
            {p.nombre}
            {#if p.agente}<em>agente</em>{:else if p.persona}<em>equipo</em>{/if}
          </li>
        {/each}
      </ul>
      <button onclick={() => (seleccionada = null)}>Cerrar</button>
    </aside>
  {/if}
</div>

<style>
  .pantalla { position: relative; display: flex; flex-direction: column; height: 100%; background: #070b1c; color: #e8e7f5; }
  header { padding: 0.9rem 1.2rem 0.6rem; border-bottom: 1px solid #1d2142; }
  h1 { margin: 0; font-size: 1.05rem; font-weight: 700; }
  .marca { font-size: 0.7rem; font-weight: 500; color: #8f8bc6; border: 1px solid #332f5e; border-radius: 999px; padding: 0.1rem 0.5rem; margin-left: 0.5rem; }
  .titulo p { margin: 0.25rem 0 0; font-size: 0.78rem; color: #9a95c0; }
  .titulo a { color: #6fa8ff; margin-left: 0.6rem; }
  .mandos { display: flex; flex-wrap: wrap; align-items: center; gap: 0.4rem; margin-top: 0.7rem; }
  .mandos button { background: #141833; color: #d7d4ee; border: 1px solid #2b2f58; border-radius: 7px; padding: 0.3rem 0.7rem; font-size: 0.78rem; cursor: pointer; }
  .mandos button.activo { background: #2a3270; border-color: #4a55b0; }
  .separador { width: 1px; height: 18px; background: #2b2f58; margin: 0 0.3rem; }
  .telemetria { margin-left: auto; font-size: 0.72rem; color: #7d78a8; font-variant-numeric: tabular-nums; }
  .lienzo { flex: 1; min-height: 0; }
  .vacio { margin: 3rem; color: #9a95c0; }
  aside { position: absolute; right: 1rem; bottom: 1rem; width: 15rem; background: #0e1230ee; border: 1px solid #2b2f58; border-radius: 10px; padding: 0.8rem 0.9rem; }
  aside h2 { margin: 0 0 0.2rem; font-size: 0.9rem; }
  aside p { margin: 0 0 0.5rem; font-size: 0.72rem; color: #9a95c0; }
  aside ul { list-style: none; margin: 0 0 0.6rem; padding: 0; font-size: 0.75rem; }
  aside li { color: #6f6a94; padding: 0.1rem 0; }
  aside li.ocupado { color: #d7d4ee; }
  aside em { font-style: normal; font-size: 0.66rem; color: #6fa8ff; margin-left: 0.3rem; }
  aside button { background: #141833; color: #d7d4ee; border: 1px solid #2b2f58; border-radius: 7px; padding: 0.25rem 0.6rem; font-size: 0.75rem; cursor: pointer; }
</style>
