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
   *
   * RECHAZAR, CON MOTIVO OBLIGATORIO (12/11/2026). Hasta hoy el panel solo
   * aprobaba, y la evidencia de autonomía ganada nunca recibía un «no»
   * (auditoría del menú §4, ítem 2). «Rechazar» abre un campo de motivo; sin
   * texto el botón de confirmar no se habilita. Que el motivo exista lo exige
   * también el servidor (`api/conversaciones/[id]/acciones/[accion]/rechazar`):
   * esta pantalla solo evita el viaje inútil.
   */
  import { CircleCheck, CircleX, Clock, CircleHelp, TriangleAlert } from '@lucide/svelte';
  import { lineasDeAcciones } from '$lib/conversaciones/acciones.js';

  let {
    acciones = [], aprobando = null, onAprobar = undefined,
    /** Id de la acción que se está rechazando, o null. */
    rechazando = null,
    /** (id, motivo) => Promise<string>: '' si salió bien, o el aviso para mostrar. */
    onRechazar = undefined
  } = $props();

  /** La acción cuyo formulario de rechazo está abierto. Una sola a la vez. */
  let rechazoAbierto = $state(/** @type {string|null} */ (null));
  let motivo = $state('');
  let avisoRechazo = $state('');

  function abrirRechazo(/** @type {string} */ id) {
    rechazoAbierto = id;
    motivo = '';
    avisoRechazo = '';
  }

  async function confirmarRechazo(/** @type {string} */ id) {
    const texto = motivo.trim();
    if (!texto || !onRechazar) return;
    avisoRechazo = (await onRechazar(id, texto)) || '';
    if (!avisoRechazo) rechazoAbierto = null;
  }

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

        {#if linea.puedeRechazarse && onRechazar}
          {#if rechazoAbierto === linea.id}
            <form class="rechazo" onsubmit={(e) => { e.preventDefault(); confirmarRechazo(linea.id); }}>
              <label class="panel-nota" for="motivo-{linea.id}">Por qué no se hace</label>
              <textarea
                id="motivo-{linea.id}"
                rows="2"
                maxlength="500"
                bind:value={motivo}
                placeholder="Ej.: el cliente ya pagó por otro medio"
              ></textarea>
              {#if avisoRechazo}<p class="panel-nota aviso-rechazo" role="status">{avisoRechazo}</p>{/if}
              <div class="rechazo-botones">
                <button
                  type="submit"
                  class="v2-btn"
                  disabled={!motivo.trim() || rechazando === linea.id}
                >
                  {rechazando === linea.id ? 'Rechazando…' : 'Confirmar rechazo'}
                </button>
                <button type="button" class="v2-btn v2-btn-quiet" onclick={() => (rechazoAbierto = null)}>
                  Cancelar
                </button>
              </div>
            </form>
          {:else}
            <button type="button" class="v2-btn v2-btn-quiet rechazar" onclick={() => abrirRechazo(linea.id)}>
              Rechazar
            </button>
          {/if}
        {/if}
      </div>
    {/each}
  </section>
{/if}

<style>
  .panel {
    padding: 0.75rem 0;
    border-bottom: 1px solid var(--bandeja-borde);
  }
  .accion {
    padding: 0.5rem 0;
  }
  .accion + .accion {
    border-top: 1px dashed var(--bandeja-borde);
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
  .aprobar,
  .rechazar {
    margin-top: 0.5rem;
  }
  .rechazo {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    margin-top: 0.5rem;
  }
  .rechazo textarea {
    width: 100%;
    font: inherit;
    resize: vertical;
  }
  .rechazo-botones {
    display: flex;
    gap: 0.5rem;
  }
  .aviso-rechazo {
    color: var(--bandeja-aviso);
  }
  .tono-ok .cabecera {
    color: var(--bandeja-ok);
  }
  .tono-error .cabecera {
    color: var(--bandeja-error);
  }
  .tono-aviso .cabecera {
    color: var(--bandeja-aviso);
  }
</style>
