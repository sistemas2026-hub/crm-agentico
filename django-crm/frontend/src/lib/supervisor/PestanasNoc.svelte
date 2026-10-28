<script>
  /**
   * Las pestañas de Supervisor NOC. La lista vive en `pestanas.js`: una sola,
   * para que ninguna pantalla vuelva a tener la suya. Pone solo los enlaces:
   * el contenedor lo pone cada pantalla, que lo acomoda en su encabezado.
   */
  import { PESTANAS_NOC } from './pestanas.js';

  /** @type {{ activa?: string }} */
  let { activa = '' } = $props();
</script>

{#each PESTANAS_NOC as p (p.id)}
  <a
    class="snoc-pildora"
    class:snoc-pildora-activa={p.id === activa}
    aria-current={p.id === activa ? 'page' : undefined}
    href={p.href}>{p.texto}</a
  >
{/each}
