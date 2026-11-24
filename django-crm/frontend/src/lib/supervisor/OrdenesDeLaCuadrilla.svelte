<!--
  LAS ÓRDENES DE UNA CUADRILLA, EN FILAS (24/11/2026). Ver filas-de-ordenes.js.

  Una fila de dos renglones por orden que se abre a la tarjeta de siempre
  (`OrdenDelDia.svelte`, sin cambios): todo lo que se podía hacer con una orden
  —moverla, devolverla al técnico, revisar el cierre, cerrarla— sigue ahí, un
  clic más adentro.

  `<details>` NATIVO, como el resto de esta pantalla: sin estado de cliente,
  se dibuja en el servidor y sus pruebas lo pueden leer. La fila recuerda si
  alguien la abrió aunque Programación se refresque cada 15 s, porque `open`
  solo se vuelve a escribir si cambia lo que lo decide.
-->
<script>
  import OrdenDelDia from './OrdenDelDia.svelte';
  import { textoDelVencimiento, tonoDelVencimiento, textoDePrioridad } from './dia-publicado.js';
  import { arrancaAbierta, motivosDeAtencion, partirLasFilas } from './filas-de-ordenes.js';

  /** @type {{ ordenes: any[], dia: string, marca?: string,
   *           aQuienMover?: {profile: string, nombre: string}[], form?: any,
   *           filtro?: string, texto?: string }} */
  let { ordenes, dia, marca = '', aQuienMover = [], form = null, filtro = 'todas', texto = '' } = $props();

  const partes = $derived(partirLasFilas(ordenes, { filtro, texto, dia }));
</script>

{#snippet fila(/** @type {any} */ o)}
  {@const motivos = motivosDeAtencion(o)}
  {@const tono = tonoDelVencimiento(o.vence_en, dia)}
  <li>
    <details class="of" class:of-siguiente={o.siguiente} class:of-alerta={motivos.length}
             class:of-terminada={o.estado === 'cerrada' || o.estado === 'cancelada'}
             open={arrancaAbierta(o, form)}>
      <summary class="of-fila" aria-label={`OT ${o.numero}: ${o.asunto || o.tipo || 'sin asunto'}`}>
        <span class="of-lugar" title="Lugar en el orden del día">{o.orden_del_dia ?? '·'}</span>
        <span class="of-cuerpo">
          <span class="of-l1">
            <span class="of-ot">OT {o.numero}</span>
            <span class="of-asunto">{o.asunto || o.tipo || 'Sin asunto'}</span>
          </span>
          <span class="of-l2">
            {#if o.siguiente && marca}<span class="of-marca">{marca}</span>{/if}
            {#each motivos as m (m)}<span class="of-tag">{m}</span>{/each}
            <span class="of-estado">{o.estado_texto}</span>
            {#if o.barrio}<span class="of-barrio">{o.barrio}</span>{/if}
            {#if tono === 'vencida' || tono === 'hoy'}<span class="of-vence of-vence-{tono}">{textoDelVencimiento(o.vence_en, dia)}</span>{/if}
          </span>
        </span>
        {#if o.prioridad}
          <span class="of-prioridad of-prioridad-{o.prioridad}" title={`Prioridad ${textoDePrioridad(o.prioridad).toLowerCase()}`}></span>
        {/if}
      </summary>
      <div class="of-detalle">
        <OrdenDelDia orden={o} {dia} {marca} {aQuienMover} {form} />
      </div>
    </details>
  </li>
{/snippet}

{#if !partes.visibles.length}
  {#if partes.filtrando && partes.total}
    <p class="of-nada">Ninguna de sus {partes.total} órdenes con este filtro.</p>
  {/if}
{:else}
  <ol class="of-lista">
    {#each partes.visibles as o (o.id)}{@render fila(o)}{/each}
  </ol>
  {#if partes.plegadas.length}
    <details class="of-mas">
      <summary>
        Ver las {partes.plegadas.length} restantes{#if partes.atencionPlegada}{' '}<span class="of-mas-alerta">· {partes.atencionPlegada === 1 ? '1 pide atención' : `${partes.atencionPlegada} piden atención`}</span>{/if}
      </summary>
      <ol class="of-lista" start={partes.visibles.length + 1}>
        {#each partes.plegadas as o (o.id)}{@render fila(o)}{/each}
      </ol>
    </details>
  {/if}
{/if}

<style>
  .of-lista { list-style: none; margin: 0; padding: 0; display: grid; gap: 4px; }
  .of {
    border: 1px solid var(--snoc-outline-variant);
    border-radius: 10px;
    background: var(--snoc-surface-container-lowest, #fff);
    min-width: 0;
  }
  .of[open] { border-color: var(--snoc-outline); }
  .of-siguiente { border-color: var(--snoc-primary); box-shadow: inset 3px 0 0 var(--snoc-primary); }
  .of-alerta { box-shadow: inset 3px 0 0 var(--snoc-error); }
  .of-terminada .of-fila { opacity: 0.6; }

  .of-fila {
    display: grid;
    grid-template-columns: 22px minmax(0, 1fr) auto;
    gap: 8px;
    align-items: center;
    padding: 6px 10px 6px 8px;
    cursor: pointer;
    list-style: none;
  }
  .of-fila::-webkit-details-marker { display: none; }
  .of-fila:hover { background: var(--snoc-surface-container); border-radius: 9px; }
  .of-fila:focus-visible { outline: 2px solid var(--snoc-primary); outline-offset: -2px; border-radius: 9px; }

  .of-lugar {
    width: 22px; height: 22px; border-radius: 999px;
    display: grid; place-items: center;
    font-size: 11px; font-weight: 700; font-variant-numeric: tabular-nums;
    background: var(--snoc-surface-container); color: var(--snoc-on-surface-variant);
  }
  .of-siguiente .of-lugar { background: var(--snoc-primary); color: var(--snoc-on-primary, #fff); }

  .of-cuerpo { display: grid; gap: 1px; min-width: 0; }
  .of-l1 { display: flex; gap: 6px; align-items: baseline; min-width: 0; font-size: 13px; line-height: 18px; }
  .of-ot { flex: none; font-family: var(--v2-mono, ui-monospace, monospace); font-size: 12px; color: var(--snoc-on-surface-variant); }
  .of-asunto { min-width: 0; font-weight: 600; color: var(--snoc-on-surface); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

  .of-l2 { display: flex; flex-wrap: wrap; gap: 2px 8px; align-items: center; font-size: 11.5px; line-height: 16px; color: var(--snoc-outline); min-width: 0; }
  .of-barrio { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 100%; }
  .of-marca { font-weight: 700; color: var(--snoc-primary); }
  .of-tag { padding: 0 6px; border-radius: 999px; font-weight: 700; background: var(--snoc-error-container); color: var(--snoc-on-error-container); }
  .of-vence-vencida { color: var(--snoc-error); font-weight: 600; }
  .of-vence-hoy { color: var(--v2-espera, #a15c00); font-weight: 600; }

  .of-prioridad { width: 8px; height: 8px; border-radius: 999px; background: var(--snoc-outline-variant); }
  .of-prioridad-alta { background: var(--snoc-error); }
  .of-prioridad-media { background: var(--v2-espera-fuerte, #d97706); }

  .of-detalle { padding: 0 6px 6px; }
  .of-nada { margin: 0; font-size: 12px; color: var(--snoc-outline); }

  .of-mas > summary {
    cursor: pointer;
    padding: 6px 10px;
    margin-top: 4px;
    border-radius: 10px;
    border: 1px dashed var(--snoc-outline-variant);
    font-size: 12.5px;
    font-weight: 600;
    color: var(--snoc-primary);
  }
  .of-mas > summary:focus-visible { outline: 2px solid var(--snoc-primary); outline-offset: 1px; }
  .of-mas[open] > summary { margin-bottom: 4px; }
  .of-mas-alerta { color: var(--snoc-error); }
</style>
