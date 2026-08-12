<script>
  /**
   * La columna del centro cuando todavia no se eligio ninguna conversacion.
   *
   * La lista, las pestanas y el buscador viven en +layout.svelte, que
   * acompaña a esta pantalla y a /conversaciones/<id>. Aca solo queda el
   * hueco del medio.
   */
  import EmptyState from '$lib/v2/components/EmptyState.svelte';
  import { MessagesSquare } from '@lucide/svelte';

  /** @type {{ data: any }} */
  let { data } = $props();

  let conversaciones = $derived(data.conversaciones ?? []);
  let pendientes = $derived(
    conversaciones.filter((/** @type {any} */ c) => c.escalada_a_humano && !c.atendida).length
  );
</script>

<section class="centro">
  {#if conversaciones.length === 0}
    <EmptyState
      title="Todavía no hay conversaciones"
      body="Acá van a aparecer los chats de WhatsApp con tus clientes. Mientras tanto, probá el Simulador de WhatsApp para ver cómo se vería uno."
    >
      {#snippet icon()}<MessagesSquare size={21} />{/snippet}
    </EmptyState>
  {:else}
    <EmptyState
      title="Elegí una conversación"
      body={pendientes > 0
        ? `Hay ${pendientes} esperando a una persona. Están marcadas en la lista de la izquierda.`
        : 'Ninguna está esperando a nadie: el asistente las viene llevando solo.'}
    >
      {#snippet icon()}<MessagesSquare size={21} />{/snippet}
    </EmptyState>
  {/if}
</section>

<style>
  .centro {
    flex: 1;
    min-width: 0;
    display: grid;
    place-items: center;
    overflow-y: auto;
  }

  /* Debajo de 1000px la lista es la pantalla; este hueco no aporta nada. */
  @media (max-width: 1000px) {
    .centro {
      display: none;
    }
  }
</style>
