<!--
  LAS NOVEDADES DE UNA CUADRILLA en su tarjeta de Programación (30/10/2026).
  El usuario: «¿cómo el técnico reporta alguna novedad sin tener que escribir
  en el ticket, por ejemplo se pinchó la llanta?», y que el seguimiento de las
  cuadrillas se vea en Programación. SPEC/objetivos/novedad-de-cuadrilla.md.

  La vigente, arriba y en rojo; si es del resto del día, dice que sus órdenes
  sin empezar pasan a otra. Las que ya terminaron hoy, en una línea gris: «hubo».
-->
<script>
  import { textoDeNovedad } from './dia-publicado.js';

  /** @type {{ novedades: any[] }} */
  let { novedades = [] } = $props();

  const vigentes = $derived(novedades.filter((n) => n.vigente));
  const pasadas = $derived(novedades.filter((n) => !n.vigente));
</script>

{#each vigentes as n (n.id)}
  <div class="nc nc-vigente" role="status">
    <strong>{n.tipo_texto}</strong>
    <span>{textoDeNovedad(n)}</span>
    {#if n.afecta === 'resto_del_dia'}
      <span class="nc-efecto">Sus órdenes sin empezar pasan a otra cuadrilla.</span>
    {/if}
    {#if n.texto}<span class="nc-texto">«{n.texto}»</span>{/if}
    {#if n.quien}<span class="nc-quien">Avisó {n.quien}</span>{/if}
  </div>
{/each}
{#if pasadas.length}
  <p class="nc-pasadas">
    Hoy hubo: {pasadas.map((n) => `${n.tipo_texto.toLowerCase()} (${textoDeNovedad(n)})`).join(' · ')}
  </p>
{/if}

<style>
  .nc {
    display: grid;
    gap: 2px;
    padding: 8px 10px;
    border-radius: var(--snoc-r-xl);
    font-size: 13px;
    line-height: 18px;
  }
  .nc-vigente {
    background: var(--snoc-error-container);
    color: var(--snoc-on-error-container);
    border-left: 3px solid var(--snoc-error);
  }
  .nc-efecto { font-weight: 600; }
  .nc-texto { font-style: italic; overflow-wrap: anywhere; }
  .nc-quien { font-size: 12px; opacity: 0.85; }
  .nc-pasadas {
    margin: 0;
    font-size: 12px;
    color: var(--snoc-secondary);
  }
</style>
