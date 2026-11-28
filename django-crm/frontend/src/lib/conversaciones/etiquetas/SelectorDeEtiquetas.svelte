<script>
  /**
   * Las etiquetas del equipo de ESTE chat, y cómo cambiarlas (11/11/2026).
   *
   * Vive en la cabecera de la conversación, debajo de los identificadores: es
   * un dato del chat --«Cliente VIP» se mira antes de contestar--, no del
   * caso, así que no va escondido en una pestaña. Las elegidas se ven siempre
   * como chips; el botón abre la lista del catálogo con una casilla por
   * etiqueta. Cada casilla guarda en el acto, como en WhatsApp: no hay un
   * «Guardar» que olvidar.
   *
   * Es presentación: la página hace el pedido (PUT /api/conversaciones/<id>/
   * etiquetas) y le devuelve acá `guardando` y `error`. Sin catálogo no se
   * dibuja nada: la empresa no definió etiquetas y no hay nada que ofrecer.
   */
  import { Tag } from '@lucide/svelte';
  import EtiquetaChip from './EtiquetaChip.svelte';
  import { etiquetasDeFila } from '$lib/conversaciones/etiquetas.js';

  let {
    /** [{ clave, nombre, color }] de la empresa. */
    catalogo = [],
    /** Las claves que tiene el chat. */
    asignadas = [],
    guardando = false,
    error = '',
    /** Recibe el conjunto ENTERO nuevo, en el orden del catálogo. */
    onCambiar
  } = $props();

  let abierto = $state(false);
  /** @type {HTMLElement | null} */
  let raiz = $state(null);
  // `$props.id()` y no un aleatorio: el id es el mismo en el servidor y en el
  // navegador, así la hidratación no ve dos `aria-controls` distintos.
  const uid = $props.id();
  const idMenu = `etq-menu-${uid}`;

  const elegidas = $derived(etiquetasDeFila(asignadas, catalogo));

  /** @param {string} clave */
  function alternar(clave) {
    const actuales = new Set(asignadas ?? []);
    if (actuales.has(clave)) actuales.delete(clave);
    else actuales.add(clave);
    onCambiar?.(catalogo.map((/** @type {any} */ e) => e.clave).filter((c) => actuales.has(c)));
  }

  /* Se cierra al tocar afuera o con Escape, como cualquier menú. Solo
     escucha mientras está abierto. */
  $effect(() => {
    if (!abierto) return;
    /** @param {MouseEvent} ev */
    const afuera = (ev) => {
      if (raiz && !raiz.contains(/** @type {Node} */ (ev.target))) abierto = false;
    };
    /** @param {KeyboardEvent} ev */
    const escape = (ev) => {
      if (ev.key === 'Escape') abierto = false;
    };
    document.addEventListener('mousedown', afuera);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('mousedown', afuera);
      document.removeEventListener('keydown', escape);
    };
  });
</script>

{#if catalogo.length}
  <div class="etiquetas" bind:this={raiz}>
    {#each elegidas as e (e.clave)}
      <EtiquetaChip nombre={e.nombre} color={e.color} />
    {/each}
    <button
      type="button"
      class="etq-boton"
      aria-expanded={abierto}
      aria-controls={idMenu}
      onclick={() => (abierto = !abierto)}
    >
      <Tag size={12} aria-hidden="true" />
      {elegidas.length ? 'Etiquetas' : 'Etiquetar'}
    </button>
    {#if abierto}
      <div class="menu" id={idMenu} role="group" aria-label="Etiquetas de este chat">
        {#each catalogo as e (e.clave)}
          <label class="opcion">
            <input
              type="checkbox"
              checked={(asignadas ?? []).includes(e.clave)}
              disabled={guardando}
              onchange={() => alternar(e.clave)}
            />
            <EtiquetaChip nombre={e.nombre} color={e.color} />
          </label>
        {/each}
        <p class="pie">Son del chat: un cliente que vuelve las conserva.</p>
      </div>
    {/if}
    {#if error}
      <span class="error" role="alert">{error}</span>
    {/if}
  </div>
{/if}

<style>
  .etiquetas {
    position: relative;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 4px 6px;
    margin-top: 6px;
  }

  /* Discreto: un dato más de la cabecera, no una acción principal. */
  .etq-boton {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    min-height: 22px;
    padding: 0 6px;
    border: 1px dashed var(--bandeja-borde-fuerte, #cbd5e1);
    border-radius: var(--bandeja-radio-sm, 4px);
    background: transparent;
    color: var(--bandeja-texto-2, #64748b);
    font-family: var(--bandeja-sans, inherit);
    font-size: 12px;
    cursor: pointer;
  }

  .etq-boton:hover,
  .etq-boton[aria-expanded='true'] {
    border-style: solid;
    color: var(--bandeja-texto, #0f172a);
  }

  .etq-boton:focus-visible {
    outline: 2px solid var(--bandeja-accion, #1e3a8a);
    outline-offset: 1px;
  }

  /* Una lista que flota debajo del botón, separada por su filete: sin sombra,
     como el resto de la Bandeja. */
  .menu {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    z-index: 20;
    min-width: 14rem;
    max-height: 18rem;
    overflow-y: auto;
    padding: 6px;
    border: 1px solid var(--bandeja-borde-fuerte, #cbd5e1);
    border-radius: var(--bandeja-radio, 6px);
    background: var(--bandeja-superficie, #fff);
  }

  .opcion {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px;
    border-radius: var(--bandeja-radio-sm, 4px);
    cursor: pointer;
  }

  .opcion:hover {
    background: var(--bandeja-superficie-suave, #f1f5f9);
  }

  .pie {
    margin: 6px 4px 2px;
    padding-top: 6px;
    border-top: 1px solid var(--bandeja-borde, #e2e8f0);
    font-size: 11.5px;
    color: var(--bandeja-texto-2, #64748b);
  }

  .error {
    font-size: 12px;
    color: var(--bandeja-error, #dc2626);
  }
</style>
