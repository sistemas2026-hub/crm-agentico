<!-- Los avisos del Supervisor NOC (21/11/2026). Ver avisos.svelte.js. -->
<script>
  import { avisos, quitarAviso } from './avisos.svelte.js';
</script>

<div class="av" aria-live="polite">
  {#each avisos.lista as a (a.id)}
    <div class="av-uno av-{a.tono}" role={a.tono === 'error' ? 'alert' : 'status'}>
      <span>{a.texto}</span>
      {#if a.enlace}<a href={a.enlace.href}>{a.enlace.texto}</a>{/if}
      <button type="button" onclick={() => quitarAviso(a.id)} aria-label="Cerrar aviso">✕</button>
    </div>
  {/each}
</div>

<style>
  .av {
    position: fixed; left: 24px; bottom: 20px; z-index: 90;
    display: flex; flex-direction: column; gap: 8px; max-width: min(520px, calc(100% - 48px));
    pointer-events: none;
  }
  @media (min-width: 768px) { .av { left: calc(var(--v2-sidebar-w, 232px) + 24px); } }
  .av-uno {
    pointer-events: auto;
    display: flex; align-items: center; gap: 12px;
    padding: 11px 14px; border-radius: 12px;
    background: var(--v2-ink); color: var(--v2-paper);
    font-size: 13px; line-height: 18px; box-shadow: var(--v2-shadow-lift);
  }
  .av-error { background: var(--v2-rust); color: #fff; }
  .av-uno a { color: #c7c4ff; font-weight: 700; white-space: nowrap; }
  .av-error a { color: #fff; text-decoration: underline; }
  .av-uno button { background: none; border: 0; color: inherit; font: inherit; cursor: pointer; opacity: 0.8; margin-left: auto; }
  .av-uno button:focus-visible { outline: 2px solid currentColor; outline-offset: 2px; }
</style>
