<!--
  «CÓMO FUNCIONA»  --  21/11/2026 (rediseño del Supervisor NOC).

  Los párrafos largos que había en casi cada bloque (unos 25 en Cuadrillas)
  quedan plegados acá: el texto sigue, pero no empuja lo que se usa.
-->
<script>
  /** @type {{ titulo?: string, abierto?: boolean, children: import('svelte').Snippet }} */
  let { titulo = 'Cómo funciona', abierto = false, children } = $props();
</script>

<details class="cf" open={abierto}>
  <summary>{titulo}</summary>
  <div class="cf-texto">{@render children()}</div>
</details>

<style>
  .cf { border: 1px solid var(--v2-fam-cliente-line); background: var(--v2-fam-cliente-soft); border-radius: 12px; }
  .cf summary {
    cursor: pointer; padding: 9px 14px; font-size: 13px; font-weight: 600; color: var(--v2-fam-cliente);
    list-style: none; display: flex; align-items: center; gap: 8px;
  }
  .cf summary::-webkit-details-marker { display: none; }
  .cf summary::before { content: 'ⓘ'; }
  .cf summary:focus-visible { outline: 2px solid var(--v2-ember); outline-offset: 2px; border-radius: 12px; }
  .cf-texto { padding: 0 14px 12px; font-size: 13px; line-height: 19px; color: var(--v2-ink); display: grid; gap: 6px; }
</style>
