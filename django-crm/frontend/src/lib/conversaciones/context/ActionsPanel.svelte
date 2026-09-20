<script>
  /**
   * Las acciones que la IA propuso en esta conversación, y cómo terminaron (B5).
   *
   * POR QUÉ NO ALCANZABA CON LO DE ANTES: una acción terminaba en «aprobada»
   * y nada más. Eso es lo que alguien decidió, no lo que pasó — el efecto
   * podía haber fallado y la pantalla decía exactamente lo mismo. Ahora hay
   * cuatro finales y cada uno pide algo distinto de quien lo lee.
   *
   * EL BOTÓN DE APROBAR SÓLO APARECE DONDE EL BACKEND LO ACEPTARÍA: pendiente
   * y en plazo. Una vencida ofrecería una aprobación que termina en 409, y un
   * botón que falla enseña a desconfiar del resto.
   *
   * SIN BOTÓN DE REINTENTAR sobre una `desconocida`, igual que en el panel de
   * sincronización: nadie puede saber si ya se hizo, y un botón invita al
   * gesto exacto que manda dos visitas técnicas al mismo cliente.
   */
  import { CircleCheck, CircleX, Clock, CircleHelp, TriangleAlert } from '@lucide/svelte';
  import { lineasDeAcciones } from '$lib/conversaciones/acciones.js';

  let { acciones = [], aprobando = null, onAprobar = undefined } = $props();

  const lineas = $derived(lineasDeAcciones(acciones));

  const ICONO = {
    ok: CircleCheck,
    error: CircleX,
    aviso: TriangleAlert,
    neutro: Clock
  };
</script>

{#if lineas.length}
  <section class="panel">
    <h3 class="panel-titulo">Acciones</h3>

    {#each lineas as linea (linea.id)}
      <div class="accion tono-{linea.tono}">
        <div class="cabecera">
          {#if ICONO[linea.tono]}
            {@const Icono = ICONO[linea.tono] ?? CircleHelp}
            <Icono size={14} />
          {/if}
          <span class="titulo">{linea.titulo}</span>
        </div>

        {#if linea.resumen}
          <p class="panel-dato resumen">{linea.resumen}</p>
        {/if}
        <p class="panel-nota">{linea.detalle}</p>

        {#if linea.puedeAprobarse && onAprobar}
          <button
            type="button"
            class="v2-btn aprobar"
            disabled={aprobando === linea.id}
            onclick={() => onAprobar(linea.id)}
          >
            {aprobando === linea.id ? 'Aprobando…' : 'Aprobar y ejecutar'}
          </button>
        {/if}
      </div>
    {/each}
  </section>
{/if}

<style>
  .panel {
    padding: 0.75rem 0;
    border-bottom: 1px solid var(--v2-borde, #e2e2e2);
  }
  .accion {
    padding: 0.5rem 0;
  }
  .accion + .accion {
    border-top: 1px dashed var(--v2-borde, #e2e2e2);
  }
  .cabecera {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }
  .titulo {
    font-weight: 600;
  }
  .resumen {
    margin: 0.25rem 0 0;
  }
  .aprobar {
    margin-top: 0.5rem;
  }
  .tono-ok .cabecera {
    color: var(--v2-ok, #17803d);
  }
  .tono-error .cabecera {
    color: var(--v2-error, #b42318);
  }
  .tono-aviso .cabecera {
    color: var(--v2-aviso, #b54708);
  }
</style>
