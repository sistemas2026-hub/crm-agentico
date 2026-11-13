<!--
  EL CUADRO DE UNA CUADRILLA. Salió de `SeguimientoDeCuadrillas.svelte` el
  07/11/2026 para que cada cuadro tenga SU PROPIO recorrido: el usuario pidió
  «una flecha con el nombre de con qué sigue después de este ticket, y al
  presionarla que muestre la tarjeta de la siguiente, hasta mostrar todos».

  Un `$state` por cuadro, y no uno en el padre, porque recorrer la Cuadrilla #3
  no tiene por qué mover la #1. El padre lo llama con `(c.jornada)` como clave,
  así que el recorrido sobrevive a las recargas de Programación —cada 15 s— en
  vez de volver al principio mientras alguien lo está leyendo.

  Lo que se recorre son las órdenes del día de ESA cuadrilla, en el orden de la
  app. La decisión de cuál se muestra vive en `recorrido-de-la-cuadrilla.js`;
  acá solo se dibuja.
-->
<script>
  import ProgresoDeLaOrden from './ProgresoDeLaOrden.svelte';
  import { textoDeNovedad } from './dia-publicado.js';
  import { nombreDeLaOrden, recorrido, tituloDel } from './recorrido-de-la-cuadrilla.js';

  /** @type {{ cuadrilla: any }} */
  let { cuadrilla } = $props();

  /**
   * El NÚMERO de la OT que se eligió mirar, o `null` para seguir lo que la
   * cuadrilla hace ahora. Un número y no un índice: ver el comentario de
   * `recorrido-de-la-cuadrilla.js`.
   * @type {number|null}
   */
  let viendo = $state(null);

  const r = $derived(cuadrilla.resumen_del_dia ?? { hechas: 0, total: 0 });
  const vigentes = $derived((cuadrilla.novedades ?? []).filter((/** @type {any} */ n) => n.vigente));
  const paso = $derived(recorrido(cuadrilla.ordenes, r.en_curso?.numero ?? null, viendo));
  const o = $derived(paso.orden);
  const asunto = $derived((paso.enElFoco ? r.en_curso?.asunto : null) || o?.asunto);
  const donde = $derived([o?.direccion, o?.barrio].filter(Boolean).join(' · '));
</script>

<article class="sc-cuadro" class:sc-alerta={vigentes.length || cuadrilla.sin_reporte}>
  <header class="sc-cabeza">
    <strong>{cuadrilla.cuadrilla}</strong>
    {#if cuadrilla.labor}<span class="sc-labor">{cuadrilla.labor}</span>{/if}
  </header>

  <p class="sc-ahora">{tituloDel(r, paso)}</p>
  {#if asunto}<p class="sc-asunto">{asunto}</p>{/if}
  {#if donde}<p class="sc-donde">{donde}</p>{/if}
  <!-- El progreso de esa orden, como en la app (30/10/2026). -->
  {#if o}<ProgresoDeLaOrden estado={o.estado} compacto />{/if}
  {#if paso.enElFoco && r.en_curso?.minutos != null}
    <p class="sc-reloj" aria-label={`Lleva ${r.en_curso.minutos} minutos`}>⏱ {r.en_curso.minutos} min</p>
  {:else if paso.enElFoco && r.en_curso?.desde}
    <!-- Empezó otro día y nadie la cerró: la fecha, no «21159 min». -->
    <p class="sc-viejo">⏱ Desde el {r.en_curso.desde}, sin cerrar</p>
  {/if}

  <!--
    EL RECORRIDO. Solo aparece si hay más de una orden que recorrer: con una
    sola, una flecha apagada es ruido.
  -->
  {#if paso.total > 1}
    <nav class="sc-paso" aria-label={`Órdenes de ${cuadrilla.cuadrilla}`}>
      <div class="sc-paso-fila">
        <button
          type="button"
          class="sc-atras"
          disabled={!paso.anterior}
          onclick={() => (viendo = paso.anterior?.numero ?? null)}
          aria-label={paso.anterior ? `Ver la anterior: ${nombreDeLaOrden(paso.anterior)}` : 'No hay anterior'}
        >←</button>
        <span class="sc-cuenta">{paso.posicion} de {paso.total}</span>
        {#if !paso.enElFoco}
          <button type="button" class="sc-volver" onclick={() => (viendo = null)}>
            Volver a lo de ahora
          </button>
        {/if}
      </div>

      {#if paso.siguiente}
        <button
          type="button"
          class="sc-sigue"
          onclick={() => (viendo = paso.siguiente.numero)}
          title={nombreDeLaOrden(paso.siguiente)}
        >
          <span class="sc-sigue-nombre">Sigue: {nombreDeLaOrden(paso.siguiente)}</span>
          <span class="sc-sigue-punta" aria-hidden="true">→</span>
        </button>
      {:else}
        <p class="sc-ultima">Es la última orden del día</p>
      {/if}
    </nav>
  {/if}

  <div class="sc-avance">
    <progress max={r.total || 1} value={r.hechas}></progress>
    <span>{`${r.hechas} de ${r.total}${r.salio ? ` · salió ${r.salio}` : ''}`}</span>
  </div>

  {#each vigentes as n (n.id)}
    <p class="sc-aviso">⚠ {n.tipo_texto} · {textoDeNovedad(n)}</p>
  {/each}
  {#if cuadrilla.sin_reporte}
    <p class="sc-aviso">⚠ Sin reporte hace {cuadrilla.sin_reporte.minutos} min · OT #{cuadrilla.sin_reporte.numero}</p>
  {/if}

  {#if cuadrilla.log?.length}
    <details class="sc-log">
      <summary>Seguimiento ({cuadrilla.log.length})</summary>
      <ol>
        {#each cuadrilla.log as e, i (i)}
          <li class="sc-log-{e.de}"><time>{e.hora}</time> <span>{e.texto}</span></li>
        {/each}
      </ol>
    </details>
  {/if}
</article>

<style>
  .sc-cuadro {
    display: grid;
    /*  NADA SE SALE DE LA TARJETA (07/11/2026). El usuario, con el cuadro ya
        visible: «ahora se dañó esta parte de acá». Una columna `auto` --el
        valor por omisión-- tiene como mínimo el ancho de su contenido, y acá
        hay dos hijos con `white-space: nowrap`: el botón «Sigue: OT #6 ·
        Recolección De Equipo» y los cinco rótulos del progreso. Entre los dos
        empujaban la columna más allá del ancho de la tarjeta y el texto se
        derramaba sobre la cuadrilla de al lado. `minmax(0, 1fr)` le saca ese
        piso, y entonces sí funcionan los puntos suspensivos que ya tenían. */
    grid-template-columns: minmax(0, 1fr);
    gap: 4px;
    align-content: start;
    padding: 10px 12px;
    border-radius: var(--snoc-r-xl);
    background: var(--snoc-surface-container-lowest, #fff);
    border: 1px solid var(--snoc-outline-variant);
    font-size: 13px;
    line-height: 18px;
    color: var(--snoc-on-surface-variant);
    min-width: 0;
  }
  .sc-alerta { border-left: 3px solid var(--snoc-error); }
  .sc-cabeza { display: flex; flex-wrap: wrap; gap: 6px; align-items: baseline; }
  .sc-cabeza strong { font-size: 14px; color: var(--snoc-on-surface); }
  .sc-labor {
    padding: 0 8px;
    border-radius: 999px;
    background: var(--snoc-surface-container);
    font-size: 12px;
    font-weight: 600;
  }
  .sc-ahora { margin: 0; font-weight: 700; color: var(--snoc-on-surface); }
  .sc-asunto { margin: 0; overflow-wrap: anywhere; color: var(--snoc-on-surface); }
  .sc-donde { margin: 0; overflow-wrap: anywhere; font-size: 12px; }
  .sc-reloj { margin: 0; font-size: 18px; font-weight: 700; color: var(--snoc-primary); font-variant-numeric: tabular-nums; }
  .sc-viejo { margin: 0; font-weight: 600; color: var(--snoc-error); font-variant-numeric: tabular-nums; }

  .sc-paso { display: grid; gap: 4px; margin-top: 2px; }
  .sc-paso-fila { display: flex; align-items: center; gap: 6px; font-size: 12px; }
  .sc-atras {
    flex: none;
    width: 24px;
    height: 24px;
    border-radius: 8px;
    border: 1px solid var(--snoc-outline-variant);
    background: var(--snoc-surface-container-lowest, #fff);
    color: var(--snoc-on-surface);
    font-size: 13px;
    line-height: 1;
    cursor: pointer;
  }
  .sc-atras:disabled { opacity: 0.35; cursor: default; }
  .sc-cuenta { color: var(--snoc-outline); font-variant-numeric: tabular-nums; }
  .sc-volver {
    margin-left: auto;
    padding: 0;
    border: 0;
    background: none;
    color: var(--snoc-primary);
    font: inherit;
    font-weight: 600;
    text-decoration: underline;
    cursor: pointer;
  }
  .sc-sigue {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 6px 10px;
    border-radius: 10px;
    border: 1px solid var(--snoc-outline-variant);
    background: var(--snoc-surface-container);
    color: var(--snoc-on-surface);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .sc-sigue:hover { border-color: var(--snoc-primary); }
  .sc-sigue-nombre {
    flex: 1 1 auto;
    min-width: 0;
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .sc-sigue-punta { flex: none; color: var(--snoc-primary); font-weight: 700; }
  .sc-ultima { margin: 0; font-size: 12px; color: var(--snoc-outline); }

  .sc-avance { display: grid; gap: 2px; font-size: 12px; }
  .sc-avance progress { width: 100%; height: 6px; accent-color: var(--snoc-primary); }
  .sc-aviso { margin: 0; color: var(--snoc-error); font-weight: 600; }
  .sc-log summary { cursor: pointer; font-weight: 600; color: var(--snoc-secondary); }
  .sc-log ol { list-style: none; margin: 6px 0 0; padding: 0; display: grid; gap: 3px; }
  .sc-log li { display: grid; grid-template-columns: 40px 1fr; gap: 6px; font-size: 12px; }
  .sc-log time { font-variant-numeric: tabular-nums; color: var(--snoc-secondary); }
  .sc-log-supervisor span { color: var(--snoc-primary); }
  .sc-log-alerta span { color: var(--snoc-error); font-weight: 600; }
</style>
