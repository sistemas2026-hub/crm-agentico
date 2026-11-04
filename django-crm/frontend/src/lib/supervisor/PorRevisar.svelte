<!--
  POR REVISAR (31/10/2026): lo terminado en campo de días anteriores que nadie
  cerró, con la forma de `campo/dia_publicado.py` (`por_revisar`). Antes no
  salía en ningún lado: en producción la OT #4, terminada el 30 y sin aprobar,
  el 31 no estaba ni en Hoy ni en Cerradas (el usuario: «en la supervisor no
  sale el ticket»). Cada una en su tarjeta, con la revisión del Supervisor y
  sus botones; siguen acá hasta que alguien las apruebe y las cierre.
-->
<script>
  import OrdenDelDia from './OrdenDelDia.svelte';

  /** @type {{ ordenes: any[], dia: string }} */
  let { ordenes, dia } = $props();
</script>

{#if ordenes?.length}
  <section class="snoc-panel pr" aria-label="Por revisar">
    <span class="snoc-label">Por revisar, de días anteriores ({ordenes.length})</span>
    <p class="snoc-body-sm snoc-secundario">
      Terminadas en campo y sin cerrar. Siguen acá hasta que alguien las apruebe y las cierre.
    </p>
    <div class="pr-rejilla">
      {#each ordenes as o (o.id)}
        <div class="pr-orden">
          {#if o.terminada_el}<span class="snoc-body-sm snoc-secundario">Terminó el {o.terminada_el}</span>{/if}
          <OrdenDelDia orden={o} {dia} />
        </div>
      {/each}
    </div>
  </section>
{/if}

<style>
  .pr { gap: var(--snoc-sm); }
  .pr-rejilla {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr));
    gap: var(--snoc-sm);
  }
  .pr-orden { display: grid; gap: 4px; min-width: 0; align-content: start; }
</style>
