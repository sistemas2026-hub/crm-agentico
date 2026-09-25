<script>
  /**
   * Los tres huecos de la cola: no se pudo cargar, todavía no hay nada, y no
   * quedó nada después de filtrar.
   *
   * NO DECIDE CUÁL SE MUESTRA. Las tres condiciones siguen en `+layout.svelte`
   * -- `data.error`, `conversaciones.length === 0`, `visibles.length === 0` --
   * y este componente recibe la que corresponde ya resuelta. Es a propósito:
   * saber si el `load` falló, si la bandeja está vacía o si los filtros no
   * dejaron nada es conocimiento de quien tiene la lista, y las tres
   * respuestas se parecen lo suficiente como para que fusionarlas sea
   * tentador. NO SON LO MISMO:
   *
   *   error              algo se rompió; quien atiende no sabe qué hay
   *   sin-datos          la bandeja está vacía de verdad
   *   sin-coincidencias  hay conversaciones, pero los filtros las escondieron
   *
   * La tercera es la única en la que la salida es "cambiá el filtro", y por
   * eso tiene texto distinto según haya o no una búsqueda escrita.
   *
   * No hay estado de carga acá, y no hay que inventarlo: la cola llega desde
   * el `load` del servidor, ya cargada.
   */
  import EmptyState from '$lib/v2/components/EmptyState.svelte';
  import { MessagesSquare, TriangleAlert, Search } from '@lucide/svelte';

  let { variante, error = '', busqueda = '' } = $props();
</script>

{#if variante === 'error'}
  <div class="hueco">
    <EmptyState title="No se pudo cargar la bandeja" body={error}>
      {#snippet icon()}<TriangleAlert size={21} />{/snippet}
    </EmptyState>
  </div>
{:else if variante === 'sin-datos'}
  <div class="hueco">
    <EmptyState
      title="Todavía no hay conversaciones"
      body="Acá van a aparecer los chats de WhatsApp con tus clientes."
    >
      {#snippet icon()}<MessagesSquare size={21} />{/snippet}
    </EmptyState>
  </div>
{:else if variante === 'sin-coincidencias'}
  <div class="hueco">
    <EmptyState
      title="Nada acá"
      body={busqueda
        ? `Ninguna coincide con «${busqueda}».`
        : 'No hay conversaciones en este estado.'}
    >
      {#snippet icon()}<Search size={20} />{/snippet}
    </EmptyState>
  </div>
{/if}

<style>
  .hueco {
    padding: 18px 10px;
  }
</style>
