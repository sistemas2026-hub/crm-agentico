<script>
  /**
   * Traspaso a una persona y cierre por inactividad (12/11/2026).
   *
   * Hasta este día los textos que lee el cliente cuando Dexter lo pasa a
   * alguien del equipo, y el plazo con el que se cierra una conversación muda,
   * solo se cambiaban por YAML: lo que CLAUDE.md §3.3 prohíbe. No son
   * plantillas de Meta (van dentro de la ventana de 24 h), por eso viven en una
   * página hermana de «Mensajes automáticos» y no como un momento más.
   *
   * Cada campo dice CUÁNDO lo lee el cliente: un texto sin su momento es una
   * adivinanza. Las reglas que importan (el general no puede quedar vacío; el
   * de «ya escalada» no puede ser el anuncio; el cierre no puede actuar antes
   * de que la Bandeja muestre la conversación) las valida el motor y su motivo
   * vuelve tal cual.
   */
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import { ChevronLeft } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let t = $derived(data.traspaso);
  /** @param {string} m */
  const rotulo = (m) => data.rotulos?.[m] || m.replaceAll('_', ' ');

  /** @param {string | null} iso */
  function enBogota(iso) {
    if (!iso) return null;
    return new Date(iso).toLocaleString('es-CO', {
      timeZone: 'America/Bogota',
      dateStyle: 'medium',
      timeStyle: 'short'
    });
  }
</script>

<PageHeader title="Traspaso a una persona">
  {#snippet crumb()}
    <a href="/settings/canales/whatsapp" class="volver"><ChevronLeft size={13} />WhatsApp</a>
  {/snippet}
  {#snippet sub()}
    Qué le dice Dexter al cliente cuando lo pasa a alguien del equipo, y cuándo se cierra sola una
    conversación que quedó muda.
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <div class="v2-pad" style="padding-top:16px;padding-bottom:32px;max-width:860px">
    {#if !t}
      <p class="v2-card aviso">No se pudo leer la configuración del asistente. Probá recargar en un rato.</p>
    {:else}
      <form method="POST" action="?/textos" use:enhance={() => async ({ update }) => update({ reset: false })}
            class="v2-card bloque">
        <div class="v2-label">Lo que lee el cliente</div>
        <fieldset disabled={!data.can_edit}>
          <label>
            <b>Al pasarlo a una persona</b>
            <span class="v2-sub ayuda">Reemplaza la respuesta de ese turno: es lo único que el cliente lee.
              Lo usa todo motivo que no tenga texto propio abajo.</span>
            <textarea name="mensaje" class="v2-input" rows="2" required maxlength="1000"
                      value={t.textos.mensaje}></textarea>
          </label>

          {#if t.motivos.length}
            <details class="motivos">
              <summary>Texto propio por motivo ({Object.keys(t.textos.mensajes_por_motivo).length} de {t.motivos.length})</summary>
              <p class="v2-sub ayuda">No todos los motivos son una queja: un trámite que salió bien no
                merece «entiendo tu molestia». Vacío = usa el de arriba.</p>
              {#each t.motivos as m (m)}
                <label>
                  <span>{rotulo(m)}</span>
                  <textarea name={`motivo:${m}`} class="v2-input" rows="2" maxlength="1000"
                      value={t.textos.mensajes_por_motivo[m] ?? ''}></textarea>
                </label>
              {/each}
            </details>
          {/if}

          <label>
            <b>Si vuelve a escribir mientras espera</b>
            <span class="v2-sub ayuda">Mientras nadie del equipo escribió todavía. Un solo texto para
              todos los motivos, y no puede ser el anuncio: repetido suena a que el pase nunca ocurrió.
              Vacío = un texto de respaldo del sistema.</span>
            <textarea name="mensaje_ya_escalada" class="v2-input" rows="2" maxlength="1000"
                      value={t.textos.mensaje_ya_escalada}></textarea>
          </label>

          <label>
            <b>Si el traspaso no se pudo registrar</b>
            <span class="v2-sub ayuda">Tiene que pedirle que vuelva a escribir: el reintento ocurre con
              su próximo mensaje. Vacío = un texto de respaldo del sistema.</span>
            <textarea name="mensaje_si_falla" class="v2-input" rows="2" maxlength="1000"
                      value={t.textos.mensaje_si_falla}></textarea>
          </label>

          <label>
            <b>Frases con las que esta empresa promete una persona</b>
            <span class="v2-sub ayuda">Una por línea («un asesor», «te paso con»). Si el traspaso NO
              quedó registrado y la respuesta trae una de estas, se cambia por el texto de arriba: así
              no se promete algo que no pasó. Vacío = no se revisa.</span>
            <textarea name="frases_de_traspaso" class="v2-input" rows="3"
                      value={t.textos.frases_de_traspaso.join('\n')}></textarea>
          </label>
        </fieldset>
        {#if form?.textos?.error}<p class="error">{form.textos.error}</p>{/if}
        {#if form?.textos?.ok}<p class="v2-sub ok">Guardado. El próximo traspaso ya lo usa.</p>{/if}
        {#if data.can_edit}
          <div><button class="v2-btn v2-btn-primary" type="submit">Guardar textos</button></div>
        {:else}
          <p class="v2-sub ayuda">Solo un administrador puede cambiarlos.</p>
        {/if}
      </form>

      <form method="POST" action="?/cierre" use:enhance={() => async ({ update }) => update({ reset: false })}
            class="v2-card bloque">
        <div class="v2-label">Cierre por inactividad</div>
        <fieldset disabled={!data.can_edit}>
          <label>
            <b>Horas sin un mensaje</b>
            <span class="v2-sub ayuda">Pasado este plazo, el próximo mensaje del cliente abre una
              conversación nueva (lo que se sabía de él se resume y no se pierde). Vacío = nunca se
              cierra por tiempo.</span>
            <input name="horas_inactividad_cierra" type="number" min="1" max="720" class="v2-input corto"
                   value={t.cierre.horas_inactividad_cierra ?? ''} />
          </label>
          <label class="interruptor">
            <input type="checkbox" name="habilitado" checked={t.cierre.habilitado} />
            <span><b>Cerrar solas las que atendió solo Dexter</b>
              <span class="v2-sub ayuda">Las cierra el reloj con el desenlace «sin respuesta del cliente».
                {#if t.cierre.rollout_cutoff}
                  Cuenta desde el {enBogota(t.cierre.rollout_cutoff)}; lo anterior es historia y no se toca.
                {:else}
                  Al encenderlo, cuenta desde ese momento; lo anterior no se toca.
                {/if}
              </span></span>
          </label>
          {#if t.sin_gestion_horas}
            <p class="v2-sub ayuda">La Bandeja muestra una conversación «sin resolución registrada» a las
              {t.sin_gestion_horas} h: el cierre no puede actuar antes.</p>
          {/if}
          <details>
            <summary>Lo anterior al corte</summary>
            <label class="interruptor">
              <input type="checkbox" name="backfill_habilitado" checked={t.cierre.backfill_habilitado} />
              <span><b>Autorizar cerrar lo anterior</b>
                <span class="v2-sub ayuda">Solo autoriza: lo ejecuta una persona a mano, de a un lote por
                  vez. El reloj nunca lo toca.</span></span>
            </label>
            <label>
              <span>Conversaciones por lote</span>
              <input name="backfill_lote" type="number" min="1" max="500" class="v2-input corto"
                     value={t.cierre.backfill_lote} />
            </label>
          </details>
        </fieldset>
        {#if form?.cierre?.error}<p class="error">{form.cierre.error}</p>{/if}
        {#if form?.cierre?.ok}<p class="v2-sub ok">Guardado. La próxima pasada del reloj ya lo usa.</p>{/if}
        {#if data.can_edit}
          <div><button class="v2-btn v2-btn-primary" type="submit">Guardar cierre</button></div>
        {/if}
      </form>
    {/if}
  </div>
</div>

<style>
  .volver {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    color: inherit;
    text-decoration: none;
  }
  .aviso {
    padding: 12px 14px;
    font-size: 13px;
    color: var(--v2-rust);
  }
  .bloque {
    padding: 16px 18px;
    margin-bottom: 16px;
    display: grid;
    gap: 12px;
  }
  fieldset {
    border: 0;
    padding: 0;
    margin: 0;
    display: grid;
    gap: 14px;
  }
  label {
    display: grid;
    gap: 4px;
    font-size: 13px;
  }
  .interruptor {
    grid-template-columns: auto 1fr;
    align-items: start;
    gap: 8px;
  }
  .ayuda {
    font-size: 12px;
    line-height: 1.45;
    margin: 0;
  }
  .corto {
    max-width: 140px;
  }
  .motivos,
  details {
    display: grid;
    gap: 10px;
    font-size: 13px;
  }
  summary {
    cursor: pointer;
    font-weight: 600;
  }
  .error {
    margin: 0;
    color: var(--v2-rust);
    font-size: 13px;
  }
  .ok {
    margin: 0;
    font-size: 12.5px;
  }
</style>
