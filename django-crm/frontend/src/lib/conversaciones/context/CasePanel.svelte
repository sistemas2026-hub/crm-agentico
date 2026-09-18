<script>
  /**
   * El caso del CRM detrás de esta conversación: su etiqueta, a quién está
   * asignado EL TICKET y el enlace para abrirlo.
   *
   * OJO CON EL DUEÑO (D28). El "Asignado a" de acá es el dueño del ticket del
   * CRM, que puede no coincidir con quién atiende la conversación en Dexter --
   * eso último es la asignación durable y vive en HandoffControls. Son dos
   * cosas distintas a propósito y no se reconcilian todavía: la fuente de
   * verdad del relevo es Dexter. No usar este valor para decidir Tomar,
   * Soltar, Reasignar ni nada de la cola.
   */
  import { ChevronDown, ArrowRight } from '@lucide/svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';
  import { enhance } from '$app/forms';

  let {
    caso, conversacion, owners = [], ownerActual,
    asignadoA = $bindable(''),
    listaAbierta = $bindable(false),
    formularioAsignar = $bindable()
  } = $props();

  const ETIQUETA_TONE = { soporte_tecnico: 'clay', facturacion: 'moss', comercial: 'slate', queja: 'rust' };
  const etiquetaTone = (e) => ETIQUETA_TONE[e] ?? 'ink';
  const etiquetaLabel = (e) => (e ? e.replaceAll('_', ' ') : '');
</script>

  {#if caso}
  <div class="caso-panel">
  <div class="caso-campo">
    <span class="v2-sub">Etiqueta</span>
    {#if conversacion.etiqueta}
      <Pill tone={etiquetaTone(conversacion.etiqueta)}>{etiquetaLabel(conversacion.etiqueta)}</Pill>
    {:else}
      <span class="v2-muted">Sin clasificar</span>
    {/if}
  </div>

  <div class="caso-campo">
    <span class="v2-sub">Asignado a</span>
    <form
      method="POST"
      action="?/asignar"
      bind:this={formularioAsignar}
      use:enhance={() => ({ update }) => update({ reset: false })}
    >
      <input type="hidden" name="caso_id" value={caso.id} />
      <input type="hidden" name="assigned_to" value={asignadoA} />
      <div class="asignado-picker">
        <button
          type="button"
          class="v2-btn asignado-trigger"
          onclick={() => (listaAbierta = !listaAbierta)}
        >
          {#if ownerActual}
            <Avatar name={ownerActual.name} size={18} />
            <span>{ownerActual.name}</span>
          {:else}
            <span class="v2-muted">Sin asignar</span>
          {/if}
          <ChevronDown size={14} style="margin-left:auto;opacity:0.6" />
        </button>
        {#if listaAbierta}
          <!-- Fondo invisible: cerrar al hacer clic afuera, patron estandar
               sin depender de ninguna libreria de popover. -->
          <button
            type="button"
            class="asignado-fondo"
            aria-label="Cerrar"
            onclick={() => (listaAbierta = false)}
          ></button>
          <ul class="asignado-content">
            <li>
              <button
                type="button"
                class="asignado-item"
                onclick={() => {
                  asignadoA = '';
                  listaAbierta = false;
                  formularioAsignar.requestSubmit();
                }}
              >
                <span class="v2-muted">Sin asignar</span>
              </button>
            </li>
            {#each owners as o (o.id)}
              <li>
                <button
                  type="button"
                  class="asignado-item"
                  onclick={() => {
                    asignadoA = o.id;
                    listaAbierta = false;
                    formularioAsignar.requestSubmit();
                  }}
                >
                  <Avatar name={o.name} size={18} />
                  <span>{o.name}</span>
                </button>
              </li>
            {/each}
          </ul>
        {/if}
      </div>
    </form>
  </div>

  <a class="v2-btn v2-btn-sm caso-link" href="/tickets/{caso.id}">
    Ver ticket completo <ArrowRight size={14} />
  </a>
  </div>
  {/if}

<style>


  /* En la columna angosta los campos del ticket se apilan; en fila no
     entraban ni el nombre del responsable. */
  .caso-panel {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--v2-line-soft);
  }

  .caso-campo {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 5px;
  }

  .caso-campo > .v2-sub {
    font-size: 11.5px;
    white-space: nowrap;
  }

  .caso-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    align-self: flex-start;
  }

  .asignado-picker {
    position: relative;
  }

  .asignado-trigger {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
  }

  /* Fondo invisible a pantalla completa: clic afuera cierra la lista. Es el
     patron sin dependencias -- ver por que se saco bits-ui mas arriba. */
  .asignado-fondo {
    position: fixed;
    inset: 0;
    z-index: 40;
    background: transparent;
    border: none;
    cursor: default;
    padding: 0;
  }

  .asignado-content {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    background: var(--v2-surface, #fff);
    border: 1px solid var(--v2-border, #e5e5e5);
    border-radius: 10px;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
    padding: 6px;
    min-width: 200px;
    z-index: 50;
    list-style: none;
    margin: 0;
  }

  .asignado-item {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
    padding: 7px 10px;
    border-radius: 7px;
    font-size: 13.5px;
    cursor: pointer;
    background: none;
    border: none;
    text-align: left;
    color: inherit;
    font-family: inherit;
  }

  .asignado-item:hover,
  .asignado-item:focus-visible {
    background: var(--v2-surface-2, #f1f1f1);
    outline: none;
  }
</style>
