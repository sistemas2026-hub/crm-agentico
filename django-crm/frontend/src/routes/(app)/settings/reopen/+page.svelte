<script>
  /**
   * Whether a customer's reply can bring a closed ticket back.
   *
   * One row per org, four fields. Small enough that v1's form is not wrong,
   * just uninformative. The whole question here is what number to put in the
   * window, and the only thing that answers it is how customers actually
   * behave: the median reply comes back in two days, and four replies last
   * month arrived after the window and reopened nothing.
   *
   * Those four are the cost of the current setting. A settings form that shows
   * the field but not the consequence makes the number a guess forever.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import StatCard from '$lib/v2/components/StatCard.svelte';
  import SettingsFormPanel from '$lib/v2/components/SettingsFormPanel.svelte';
  import { count } from '$lib/v2/format.js';
  import { REOPEN_TO_STATUSES, CASE_STATUS_LABEL } from '$lib/v2/enums.js';
  import { RotateCcw, MailX } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let editing = $state(false);

  let p = $derived(data.policy);
</script>

<PageHeader title="Política de reapertura">
  {#snippet crumb()}<SettingsCrumb />{/snippet}
  {#snippet sub()}
    {p.is_enabled
      ? `Las respuestas dentro de ${p.reopen_window_days} días vuelven a abrir un ticket cerrado`
      : 'Los tickets cerrados se mantienen cerrados'}
  {/snippet}
  {#snippet actions()}
    {#if data.can_edit && !editing}
      <button class="v2-btn v2-btn-primary" onclick={() => (editing = true)}>Editar política</button>
    {/if}
  {/snippet}
</PageHeader>

<div class="v2-pad" style="padding-top:16px;flex:none">
  <div class="v2-stats">
    <StatCard
      label="Reabiertos, 30 días"
      value={count(p.reopened_last_30d)}
      tone="ink"
      detail="Cerrado, y luego llegó una respuesta a tiempo"
    />
    <StatCard
      label="Fuera de plazo"
      value={count(p.replies_after_window_30d)}
      tone={p.replies_after_window_30d > 0 ? 'clay' : 'slate'}
      detail="Respuestas que no reabrieron nada"
    />
    <StatCard
      label="Respuesta mediana"
      value={`${p.median_days_to_reply}d`}
      tone="slate"
      detail="Después de cerrado el ticket"
    />
  </div>
</div>

<div class="v2-scroll">
  <div class="v2-pad" style="padding-bottom:32px">
    {#if editing}
      <SettingsFormPanel
        title="Política de reapertura"
        action="?/update"
        error={form?.update?.error}
        submitLabel="Guardar política"
        oncancel={() => (editing = false)}
        ondone={() => (editing = false)}
      >
        {#snippet fields()}
          <div class="v2-field v2-sfp-wide">
            <label for="f-enabled">Reabrir con la respuesta del cliente</label>
            <label style="display:flex;gap:8px;align-items:center;font-weight:400">
              <input
                id="f-enabled"
                type="checkbox"
                name="is_enabled"
                value="true"
                checked={p.is_enabled}
              />
              Apagado significa que la respuesta se archiva en el ticket cerrado y no pasa nada más.
            </label>
          </div>

          <div class="v2-field">
            <label for="f-window">Plazo, en días</label>
            <input
              id="f-window"
              class="v2-input"
              type="number"
              name="reopen_window_days"
              min="1"
              max="365"
              required
              value={p.reopen_window_days}
            />
            <p class="v2-hint">Se cuenta desde que se cerró el ticket, en días calendario.</p>
          </div>

          <div class="v2-field">
            <label for="f-status">Vuelve como</label>
            <select id="f-status" class="v2-input" name="reopen_to_status">
              {#each REOPEN_TO_STATUSES as status (status)}
                <option value={status} selected={status === p.reopen_to_status}>{CASE_STATUS_LABEL[status] ?? status}</option>
              {/each}
            </select>
            <p class="v2-hint">
              Solo estos tres. Un ticket reabierto en un estado cerrado se volvería a cerrar apenas
              llegue.
            </p>
          </div>

          <div class="v2-field v2-sfp-wide">
            <label for="f-notify">Avisar al responsable</label>
            <label style="display:flex;gap:8px;align-items:center;font-weight:400">
              <input
                id="f-notify"
                type="checkbox"
                name="notify_assigned"
                value="true"
                checked={p.notify_assigned}
              />
              La persona a la que estaba asignado el ticket cuando se cerró.
            </label>
          </div>
        {/snippet}
      </SettingsFormPanel>
    {/if}
    <div class="v2-split">
      <div>
        <div class="v2-label" style="margin-bottom:10px">La regla</div>
        <div class="v2-card" style="overflow:hidden">
          <div class="v2-setting">
            <div class="v2-setting-body">
              <b>Reabrir con la respuesta del cliente</b>
              <span class="v2-sub" style="font-size:11.5px">
                Apagado significa que la respuesta se archiva en el ticket cerrado y no pasa nada
                más.
              </span>
            </div>
            <Pill tone={p.is_enabled ? 'moss' : 'slate'}>{p.is_enabled ? 'Activado' : 'Apagado'}</Pill>
          </div>
          <div class="v2-setting">
            <div class="v2-setting-body">
              <b>Plazo</b>
              <span class="v2-sub" style="font-size:11.5px">
                Se cuenta desde que se cerró el ticket, en días calendario.
              </span>
            </div>
            <span class="v2-num" style="font-size:13px">{p.reopen_window_days} días</span>
          </div>
          <div class="v2-setting">
            <div class="v2-setting-body">
              <b>Vuelve como</b>
              <!-- Must be a non-terminal status: reopening a ticket into a
                   closed status would close it again on arrival. -->
              <span class="v2-sub" style="font-size:11.5px">
                Tiene que ser un estado que cuente como abierto.
              </span>
            </div>
            <Pill tone="ink">{CASE_STATUS_LABEL[p.reopen_to_status] ?? p.reopen_to_status}</Pill>
          </div>
          <div class="v2-setting">
            <div class="v2-setting-body">
              <b>Avisar al responsable</b>
              <span class="v2-sub" style="font-size:11.5px">
                La persona a la que estaba asignado el ticket cuando se cerró.
              </span>
            </div>
            <Pill tone={p.notify_assigned ? 'moss' : 'slate'}>
              {p.notify_assigned ? 'Sí' : 'No'}
            </Pill>
          </div>
        </div>
      </div>

      <div>
        <div class="v2-label" style="margin-bottom:10px">Qué cambia esto</div>
        <div class="v2-card" style="padding:15px 16px">
          <div style="display:flex;gap:10px;align-items:flex-start">
            <RotateCcw size={16} style="color:var(--v2-slate);flex:none;margin-top:2px" />
            <p class="v2-sub" style="font-size:12.5px;margin:0;line-height:1.5">
              Una respuesta dentro del plazo devuelve el ticket a la cola como
              <b style="font-weight:600;color:var(--v2-ink)">{CASE_STATUS_LABEL[p.reopen_to_status] ?? p.reopen_to_status}</b>,
              conservando su historial y su número original. Es el mismo ticket, no uno nuevo, así
              que la primera respuesta y la resolución se siguen midiendo contra la apertura
              original.
            </p>
          </div>
        </div>

        {#if p.replies_after_window_30d > 0}
          <div class="v2-card" style="padding:15px 16px;margin-top:12px">
            <div style="display:flex;gap:10px;align-items:flex-start">
              <MailX size={16} style="color:var(--v2-clay);flex:none;margin-top:2px" />
              <div>
                <div style="font-weight:600;font-size:13px">
                  <span class="v2-num">{count(p.replies_after_window_30d)}</span> respuestas llegaron
                  tarde
                </div>
                <p class="v2-sub" style="font-size:12.5px;margin:5px 0 0;line-height:1.5">
                  Llegaron a tickets cerrados hace más de
                  <span class="v2-num">{p.reopen_window_days}</span> días, así que ningún ticket volvió
                  a abrirse y no se avisó a nadie. Esos clientes todavía están esperando.
                </p>
              </div>
            </div>
          </div>
        {/if}

        <p class="v2-sub" style="font-size:11.5px;margin-top:14px">
          Qué direcciones aceptan respuestas se configura en
          <a href="/settings/inbound-email" style="color:inherit">correo entrante</a>.
        </p>
      </div>
    </div>
  </div>
</div>
