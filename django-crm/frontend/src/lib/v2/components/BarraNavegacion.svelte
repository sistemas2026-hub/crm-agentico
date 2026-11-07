<script>
  /**
   * La franja de arriba mientras se carga la pagina siguiente.
   *
   * SvelteKit no cambia de pantalla hasta que la carga de la nueva termina, y
   * hasta el 01/11/2026 nada lo mostraba: un clic que tardaba varios segundos
   * se veia igual que uno que no hizo nada. "La ventana configuracion demora
   * para abrir o en ocasiones no abre", dijo el usuario.
   *
   * Aparece recien a los 150 ms, para que una navegacion rapida no parpadee.
   */
  import { navigating } from '$app/state';

  const RETARDO_MS = 150;

  let visible = $state(false);
  $effect(() => {
    if (!navigating.to) {
      visible = false;
      return;
    }
    const reloj = setTimeout(() => (visible = true), RETARDO_MS);
    return () => clearTimeout(reloj);
  });
</script>

{#if visible}
  <div class="barra-navegacion" role="progressbar" aria-label="Cargando la página"></div>
{/if}

<style>
  .barra-navegacion {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    z-index: 1000;
    overflow: hidden;
    background: var(--v2-ember-soft);
    pointer-events: none;
  }

  .barra-navegacion::after {
    content: '';
    position: absolute;
    inset: 0;
    width: 40%;
    background: var(--v2-ember);
    animation: barra-navegacion 1.1s ease-in-out infinite;
  }

  @keyframes barra-navegacion {
    from {
      transform: translateX(-100%);
    }
    to {
      transform: translateX(250%);
    }
  }

  /* Sin movimiento: la franja entera, quieta, sigue diciendo "cargando". */
  @media (prefers-reduced-motion: reduce) {
    .barra-navegacion::after {
      animation: none;
      width: 100%;
      opacity: 0.6;
    }
  }
</style>
