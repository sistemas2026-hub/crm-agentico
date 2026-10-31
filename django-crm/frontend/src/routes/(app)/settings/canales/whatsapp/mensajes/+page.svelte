<script>
  /**
   * Mensajes automáticos (28/10/2026).
   *
   * Cada momento en que Dexter le escribe a alguien por WhatsApp con una
   * plantilla aprobada, y qué dato va en cada {{1}}, {{2}}… Reemplaza la
   * pantalla de avisos del CRM anterior. Los momentos y los datos que ofrece
   * cada uno los define el motor; cada empresa elige plantilla, datos y si está
   * encendido.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import { ChevronLeft } from '@lucide/svelte';
  import Momento from './Momento.svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let m = $derived(data.mensajes);
  let grupos = $derived.by(() => {
    /** @type {Record<string, any[]>} */
    const g = {};
    for (const e of m?.eventos ?? []) (g[e.grupo] ??= []).push(e);
    return Object.entries(g);
  });
</script>

<PageHeader title="Mensajes automáticos">
  {#snippet crumb()}
    <a href="/settings/canales/whatsapp" class="volver"><ChevronLeft size={13} />WhatsApp</a>
  {/snippet}
  {#snippet sub()}
    Qué plantilla se manda en cada momento, y qué dato va en cada lugar de la plantilla.
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <div class="v2-pad" style="padding-top:16px;padding-bottom:32px;max-width:860px">
    {#if !m}
      <p class="v2-card aviso">No se pudo leer la configuración. Probá recargar en un rato.</p>
    {:else}
      {#if m.error_meta}
        <p class="v2-card aviso">
          {m.error_meta} Se ve lo configurado, pero no se pueden elegir plantillas hasta que Meta conteste.
        </p>
      {/if}
      <p class="v2-sub intro">
        Las plantillas se crean en <a href="/settings/canales/whatsapp/plantillas">Plantillas</a> y Meta las
        aprueba. Acá se elige, para cada momento, cuál se manda y qué dato del sistema llena cada
        {'{{1}}'}, {'{{2}}'}… Todos empiezan apagados.
      </p>
      {#each grupos as [grupo, eventos] (grupo)}
        <div class="v2-label" style="margin:22px 0 10px">{grupo}</div>
        <div class="lista">
          {#each eventos as e (e.clave)}
            <Momento evento={e} campos={m.campos} plantillas={m.plantillas} canEdit={data.can_edit} {form}
              encuesta={m.encuesta} />
          {/each}
        </div>
      {/each}
    {/if}
  </div>
</div>

<style>
  .volver {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    color: inherit;
    text-decoration: none;
  }
  .volver:hover {
    color: var(--v2-ink);
    text-decoration: underline;
  }
  .aviso {
    padding: 12px 14px;
    margin: 0 0 14px;
    font-size: 13px;
    color: var(--v2-rust);
  }
  .intro {
    margin: 0;
    font-size: 13px;
    line-height: 1.5;
  }
  .lista {
    display: grid;
    gap: 12px;
  }
</style>
