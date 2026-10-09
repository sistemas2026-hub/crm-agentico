<script>
  /**
   * El chip de estado. Un solo lugar decide como se ve cada estado, asi que
   * agregar el noveno es tocar la tabla de estados, no buscar chips por la
   * pantalla.
   */
  import { rotuloDe, colorDe, pulsaEn } from '$lib/centro-mando/estados.js';

  /** @type {{ estado: string, compacto?: boolean }} */
  let { estado, compacto = false } = $props();
</script>

<span class="chip" class:compacto style="--c:{colorDe(estado)}">
  <i class:vivo={pulsaEn(estado)}></i>{rotuloDe(estado)}
</span>

<style>
  .chip {
    font-family: ui-monospace, monospace; font-size: 8.5px; letter-spacing: .08em;
    font-weight: 700; padding: 2px 6px; border-radius: 5px; white-space: nowrap;
    color: var(--c); border: 1px solid var(--c);
    background: color-mix(in srgb, var(--c) 14%, transparent);
    display: inline-flex; align-items: center; gap: 5px; flex-shrink: 0;
  }
  .chip.compacto { font-size: 8px; padding: 1px 5px; }
  i { width: 6px; height: 6px; border-radius: 50%; background: var(--c); display: inline-block; }
  i.vivo { animation: latir 1.6s infinite; }
  @keyframes latir { 0%, 100% { opacity: 1 } 50% { opacity: .45 } }
  @media (prefers-reduced-motion: reduce) { i.vivo { animation: none } }
</style>
