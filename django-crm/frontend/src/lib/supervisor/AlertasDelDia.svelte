<!--
  ALERTAS Y NOVEDADES (31/10/2026). Lo que necesita que alguien haga algo,
  junto y ordenado por gravedad, en vez de repartido por toda la pantalla.

  No pide nada nuevo al servidor: `alertasDelDia` lo arma con lo que la página
  ya cargó, así que no puede decir algo que las tarjetas no digan.

  Sin alertas no se dibuja una caja vacía: se dice que no hay nada que atender,
  que es información.
-->
<script>
  import { alertasDelDia } from './dia-publicado.js';

  /** @type {{ publicado: any, material: any }} */
  let { publicado, material } = $props();

  let alertas = $derived(alertasDelDia(publicado, material));
  let graves = $derived(alertas.filter((a) => a.tono === 'grave').length);
</script>

<section class="ad" aria-label="Alertas y novedades">
  <div class="ad-cab">
    <span class="snoc-label">Alertas y novedades</span>
    {#if graves}<span class="ad-cuenta">{graves}</span>{/if}
  </div>
  {#if !alertas.length}
    <p class="ad-nada snoc-secundario">Nada que atender: ninguna cuadrilla dejó de reportar y no hay novedades.</p>
  {:else}
    <ul class="ad-lista">
      {#each alertas as a (a.clave)}
        <li class="ad-i ad-{a.tono}">
          <span class="ad-punto" aria-hidden="true"></span>
          <span class="ad-texto">{a.texto}</span>
          <span class="ad-donde">{a.donde}</span>
        </li>
      {/each}
    </ul>
  {/if}
</section>

<style>
  .ad { display: grid; gap: var(--snoc-xs); min-width: 0; }
  .ad-cab { display: flex; align-items: center; gap: 8px; }
  .ad-cuenta {
    background: var(--snoc-error);
    color: var(--snoc-on-error, #fff);
    font-size: 11px;
    font-weight: 700;
    padding: 0 7px;
    border-radius: 999px;
    line-height: 18px;
  }
  .ad-nada { margin: 0; font-size: 13px; }
  .ad-lista { list-style: none; margin: 0; padding: 0; display: grid; }
  .ad-i {
    display: grid;
    grid-template-columns: auto 1fr auto;
    align-items: baseline;
    gap: 8px;
    padding: 7px 0;
    font-size: 13px;
    border-top: 1px solid var(--snoc-surface-container-high);
  }
  .ad-i:first-child { border-top: none; }
  .ad-punto { width: 8px; height: 8px; border-radius: 50%; align-self: center; }
  .ad-grave .ad-punto { background: var(--snoc-error); }
  .ad-avisa .ad-punto { background: #8a5300; }
  .ad-dato .ad-punto { background: var(--snoc-secondary); }
  .ad-grave .ad-texto { font-weight: 600; color: var(--snoc-error); }
  .ad-texto { min-width: 0; overflow-wrap: anywhere; }
  .ad-donde { color: var(--snoc-secondary); font-size: 12px; white-space: nowrap; }
</style>
