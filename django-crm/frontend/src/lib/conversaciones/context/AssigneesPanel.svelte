<script>
  /**
   * Quién atiende, y quién figura en el caso del CRM (D28).
   *
   * Son dos cosas distintas: Dexter tiene UNA persona a cargo y manda; el CRM
   * tiene un CONJUNTO, y quien no puso Dexter es colaboración de alguien más.
   * El panel las muestra separadas y no llama «dueño» a ninguna.
   *
   * NO HAY BOTÓN PARA QUITAR A NADIE, y no es un olvido: el CRM no guarda
   * quién creó cada asignación, así que nada distingue una automática vieja de
   * un segundo técnico que un supervisor sumó esta mañana. Un botón invitaría
   * a borrar trabajo que no se recupera.
   */
  import { Users } from '@lucide/svelte';
  import { ETIQUETAS, vistaDeAsignados, explicacion } from '$lib/conversaciones/asignados.js';

  let { asignados = null, aCargoEnDexter = '' } = $props();

  const vista = $derived(vistaDeAsignados(asignados, aCargoEnDexter));
  const nota = $derived(explicacion(vista));
</script>

{#if vista.hayAlgoQueMostrar}
  <section class="panel">
    <h3 class="panel-titulo"><Users size={13} /> {ETIQUETAS.crm}</h3>

    {#if vista.aCargoEnDexter}
      <p class="panel-dato">
        <span class="v2-sub">{ETIQUETAS.dexter}:</span> {vista.aCargoEnDexter}
      </p>
    {/if}

    {#if vista.colaboradores.length}
      <p class="panel-dato">
        <span class="v2-sub">{ETIQUETAS.colaboradores}:</span>
        {vista.colaboradores.join(', ')}
      </p>
    {/if}

    {#if nota}
      <p class="panel-nota">{nota}</p>
    {/if}
  </section>
{/if}

<style>
  .panel {
    padding: 0.75rem 0;
    border-bottom: 1px solid var(--v2-borde, #e2e2e2);
  }
  .panel-titulo {
    display: flex;
    align-items: center;
    gap: 0.35rem;
  }
</style>
