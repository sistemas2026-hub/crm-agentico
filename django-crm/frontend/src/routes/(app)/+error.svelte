<script>
  import { page } from '$app/state';
  import EmptyState from '$lib/v2/components/EmptyState.svelte';
  import { FileQuestion, Lock, TriangleAlert } from '@lucide/svelte';

  /**
   * Every failed load in /v2 lands here. Three cases, three different things
   * to do next, which is the point: "Something went wrong" tells you nothing
   * and leaves you on a dead page.
   *
   * 403 deliberately does not say whether the record exists. Confirming that
   * an id is real to somebody who cannot open it is an information leak, so
   * the copy talks about access, never about the record.
   */
  let status = $derived(page.status);

  let shape = $derived(
    status === 404
      ? {
          icon: FileQuestion,
          title: 'Ese registro no está acá',
          body:
            page.error?.message ||
            'Puede que se haya borrado, o que pertenezca a un equipo del que no formás parte.'
        }
      : status === 403
        ? {
            icon: Lock,
            title: 'No tenés acceso a esto',
            body: 'Pedile a un administrador de tu organización que te dé acceso, o volvé a Hoy.'
          }
        : {
            icon: TriangleAlert,
            title: 'Eso no cargó',
            body:
              page.error?.message ||
              'El servidor no respondió. No hiciste nada que causara esto, y no se guardó ni se perdió nada.'
          }
  );
</script>

<div class="v2-scroll">
  <EmptyState title={shape.title} body={shape.body}>
    {#snippet icon()}
      <shape.icon size={21} />
    {/snippet}
    {#snippet actions()}
      {#if status >= 500}
        <button class="v2-btn v2-btn-primary" onclick={() => location.reload()}>Reintentar</button>
      {/if}
      <a class="v2-btn" href="/">Volver a Hoy</a>
    {/snippet}
  </EmptyState>

  <p class="v2-sub" style="text-align:center;font-size:11.5px">
    <span class="v2-num">{status}</span>
    · {page.url.pathname}
  </p>
</div>
