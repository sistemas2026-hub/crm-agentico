<script>
  /**
   * The addresses that turn email into tickets.
   *
   * Two things this page is careful about:
   *
   * 1. NO SECRETS. InboundMailbox carries a per-address signing secret and a
   *    provider topic id. The signing secret is what proves a delivery really
   *    came from the provider. Anything holding it can forge tickets into this
   *    org, or read the ones it forges. It is not fetched, not rendered, and
   *    not masked-but-present in the DOM, on this page or on the create/edit
   *    form below: there is no field for it, not even a disabled one, because
   *    the server always generates a stronger secret than a pasted one and an
   *    empty field posted on an edit would blank the org's live credential.
   *    Rotation and a one-time reveal on create are a deliberate, separate
   *    feature, not built here; see the card at the foot of the page.
   * 2. An inactive mailbox does not bounce. The address keeps accepting mail
   *    and the webhook stops creating cases, so the sender gets silence rather
   *    than a delivery failure. That is a materially different thing from
   *    "off", and a grey pill saying "Off" does not say it.
   */
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import SettingsFormPanel from '$lib/v2/components/SettingsFormPanel.svelte';
  import ConfirmAction from '$lib/v2/components/ConfirmAction.svelte';
  import { count, relativeDays } from '$lib/v2/format.js';
  import {
    MAILBOX_PROVIDER_LABEL,
    PRIORITY_TONE,
    CASE_PRIORITY_LABEL,
    CASE_TYPE_LABEL
  } from '$lib/v2/enums.js';
  import { missingOption, inactiveOptionLabel } from '$lib/v2/pickers.js';
  import { Plus, MailWarning, KeyRound } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  // cases.InboundMailbox.PROVIDER_CHOICES is MAILBOX_PROVIDER_LABEL's key
  // order. PRIORITY_CHOICE and CASE_TYPE mirror ticket-approvals' own local
  // copies: value and label are the same string for both, and no shared map
  // exists to derive them from.
  const PROVIDERS = ['ses', 'mailgun', 'postmark', 'imap'];
  const PRIORITIES = ['Low', 'Normal', 'High', 'Urgent'];
  const CASE_TYPES = ['Question', 'Incident', 'Problem'];

  let totals = $derived(data.totals);
  let mailboxes = $derived(data.mailboxes);
  let silent = $derived(mailboxes.filter((m) => !m.is_active));

  // `null` when the panel is closed, `'new'` when adding, or the mailbox
  // object when editing that row. One panel, two modes, so two rows can
  // never be open for edit at once.
  let editing = $state(/** @type {any} */ (null));

  function openCreate() {
    editing = 'new';
  }

  function openEdit(m) {
    editing = m;
  }

  // The stored default assignee when the picker cannot offer it, because the
  // profile has been deactivated since it was chosen. `getOrgPeopleAndTeams`
  // returns active profiles only, `InboundMailbox.default_assignee` keeps
  // whoever was set. A select with no matching option submits nothing, which
  // `readValues` reads as `''` and `buildBody` sends as `null`, so an edit
  // made to change the address or the provider would also quietly move this
  // mailbox back to Unassigned.
  let missingAssignee = $derived(
    editing && editing !== 'new' ? missingOption(data.people, editing.default_assignee) : null
  );
</script>

<PageHeader title="Correo entrante">
  {#snippet crumb()}<SettingsCrumb />{/snippet}
  {#snippet sub()}
    <span class="v2-num">{count(totals.active)}</span> de
    <span class="v2-num">{count(totals.count)}</span> direcciones creando tickets ·
    <span class="v2-num">{count(totals.cases_last_30d)}</span> en los últimos 30 días
  {/snippet}
  {#snippet actions()}
    {#if data.can_edit && !editing}
      <button class="v2-btn v2-btn-primary" onclick={openCreate}><Plus />Agregar dirección</button>
    {/if}
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <div class="v2-pad" style="padding-top:18px;padding-bottom:32px">
    {#if editing}
      <SettingsFormPanel
        title={editing === 'new' ? 'Nueva dirección' : `Editar ${editing.address}`}
        action={editing === 'new' ? '?/create' : '?/update'}
        error={editing === 'new' ? form?.create?.error : form?.update?.error}
        submitLabel={editing === 'new' ? 'Agregar dirección' : 'Guardar dirección'}
        oncancel={() => (editing = null)}
        ondone={() => (editing = null)}
      >
        {#snippet fields()}
          {#if editing !== 'new'}
            <input type="hidden" name="id" value={editing.id} />
          {/if}

          <div class="v2-field">
            <label for="m-address">Dirección</label>
            <input
              id="m-address"
              class="v2-input"
              type="email"
              name="address"
              required
              value={editing === 'new' ? '' : editing.address}
            />
            {#if editing !== 'new'}
              <p class="v2-hint">El correo a la dirección anterior deja de convertirse en tickets.</p>
            {/if}
          </div>

          <div class="v2-field">
            <label for="m-provider">Proveedor</label>
            <select id="m-provider" class="v2-input" name="provider">
              {#each PROVIDERS as p (p)}
                <option value={p} selected={editing === 'new' ? p === 'ses' : editing.provider === p}>
                  {MAILBOX_PROVIDER_LABEL[p]}
                </option>
              {/each}
            </select>
            <p class="v2-hint">
              El secreto de firma lo genera el servidor y no se muestra acá.
            </p>
          </div>

          <div class="v2-field">
            <label for="m-priority">Se abre con prioridad</label>
            <select id="m-priority" class="v2-input" name="default_priority">
              {#each PRIORITIES as p (p)}
                <option
                  value={p}
                  selected={editing === 'new' ? p === 'Normal' : editing.default_priority === p}
                >
                  {CASE_PRIORITY_LABEL[p] ?? p}
                </option>
              {/each}
            </select>
          </div>

          <div class="v2-field">
            <label for="m-type">Se abre como tipo</label>
            <select id="m-type" class="v2-input" name="default_case_type">
              <option value="" selected={editing === 'new' || !editing.default_case_type}>
                Ninguno
              </option>
              {#each CASE_TYPES as t (t)}
                <option value={t} selected={editing !== 'new' && editing.default_case_type === t}>
                  {CASE_TYPE_LABEL[t] ?? t}
                </option>
              {/each}
            </select>
          </div>

          <div class="v2-field">
            <label for="m-assignee">Responsable por defecto</label>
            <select id="m-assignee" class="v2-input" name="default_assignee_id">
              <option value="" selected={editing === 'new' || !editing.default_assignee}>
                Sin asignar
              </option>
              {#if missingAssignee}
                <option value={missingAssignee.id} selected>
                  {inactiveOptionLabel(missingAssignee.name)}
                </option>
              {/if}
              {#each data.people as p (p.id)}
                <option
                  value={p.id}
                  selected={editing !== 'new' && editing.default_assignee?.id === p.id}
                >
                  {p.name}
                </option>
              {/each}
            </select>
            {#if missingAssignee}
              <p class="v2-hint">
                La cuenta de este responsable ya no está activa. Se mantiene así hasta que lo
                cambies, así que los tickets nuevos de esta dirección le llegan a alguien que no
                puede iniciar sesión.
              </p>
            {/if}
          </div>

          {#if editing === 'new'}
            <div class="v2-field">
              <label for="m-active">Activa</label>
              <label style="display:flex;gap:8px;align-items:center;font-weight:400">
                <input id="m-active" type="checkbox" name="is_active" value="true" checked />
                Empieza a crear tickets a partir del correo a esta dirección apenas se guarde.
              </label>
            </div>
          {/if}
        {/snippet}
      </SettingsFormPanel>
    {/if}

    {#if form?.deactivate?.error}
      <p class="v2-error" style="margin-bottom:12px">{form.deactivate.error}</p>
    {/if}
    {#if form?.activate?.error}
      <p class="v2-error" style="margin-bottom:12px">{form.activate.error}</p>
    {/if}
    {#if form?.remove?.error}
      <p class="v2-error" style="margin-bottom:12px">{form.remove.error}</p>
    {/if}

    {#if silent.length}
      <div class="v2-mbx-banner">
        <MailWarning size={17} style="color:var(--v2-clay);flex:none;margin-top:1px" />
        <div>
          <div style="font-weight:600;font-size:13px">
            {silent.map((m) => m.address).join(', ')}
            {silent.length === 1
              ? 'acepta correo y no crea nada'
              : 'aceptan correo y no crean nada'}
          </div>
          <p class="v2-sub" style="font-size:12px;margin:4px 0 0;line-height:1.5">
            Apagar una dirección deja de abrir tickets. No deja de recibir correo ni lo rebota, así
            que quien escriba ahí no recibe ticket ni error, solo silencio.
          </p>
        </div>
      </div>
    {/if}

    <div class="v2-label" style="margin-bottom:10px">Direcciones</div>
    <div style="display:flex;flex-direction:column;gap:9px">
      {#each mailboxes as m (m.id)}
        <div class="v2-card v2-mbx" style="opacity:{m.is_active ? 1 : 0.68}">
          <div style="flex:1;min-width:0">
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
              <b style="font-size:13.5px">{m.address}</b>
              <Pill tone={m.is_active ? 'moss' : 'clay'}>
                {m.is_active ? 'Crea tickets' : 'No crea nada'}
              </Pill>
            </div>
            <div class="v2-sub" style="font-size:11.5px;margin-top:4px">
              {MAILBOX_PROVIDER_LABEL[m.provider]} ·
              {#if m.cases_last_30d}
                <span class="v2-num">{count(m.cases_last_30d)}</span> tickets en 30 días · último
                correo {relativeDays(m.last_received_at)}
              {:else}
                sin tickets en 30 días · último correo {relativeDays(m.last_received_at)}
              {/if}
            </div>

            <!-- What a ticket from here starts out as. These are the defaults
                 a routing rule then reads, so they are worth stating next to
                 the address rather than behind an edit dialog. -->
            <div class="v2-mbx-defaults">
              <span class="v2-sub">Se abre como</span>
              <Pill tone={PRIORITY_TONE[m.default_priority]}>{CASE_PRIORITY_LABEL[m.default_priority] ?? m.default_priority}</Pill>
              {#if m.default_case_type}
                <Pill tone="slate">{CASE_TYPE_LABEL[m.default_case_type] ?? m.default_case_type}</Pill>
              {/if}
              <span class="v2-sub">
                {m.default_assignee ? `asignado a ${m.default_assignee.name}` : 'después enrutado'}
              </span>
            </div>
          </div>

          {#if data.can_edit}
            <div style="display:flex;gap:6px;align-items:center;flex:none">
              <button class="v2-btn v2-btn-sm" type="button" onclick={() => openEdit(m)}>
                Editar
              </button>
              {#if m.is_active}
                <ConfirmAction
                  action="?/deactivate"
                  label="Apagar"
                  confirmLabel="Apagar"
                  explain="Deja de abrir tickets desde esta dirección. Se mantiene en la lista, apagada, hasta que se vuelva a encender."
                  hidden={{ id: m.id }}
                />
              {:else}
                <form method="POST" action="?/activate" use:enhance>
                  <input type="hidden" name="id" value={m.id} />
                  <button class="v2-btn v2-btn-sm" type="submit">Encender</button>
                </form>
              {/if}
              <ConfirmAction
                action="?/remove"
                label="Eliminar"
                confirmLabel="Eliminar"
                explain="Se elimina de forma permanente. El correo a esta dirección deja de convertirse en tickets, y el secreto de firma se destruye."
                hidden={{ id: m.id }}
              />
            </div>
          {/if}
        </div>
      {/each}
    </div>

    <!--
      The webhook secret is the credential that authenticates deliveries from
      the provider. It is not on this page in any form, not shown, not
      masked, not sitting in the payload behind a click-to-reveal, and there
      is no field for it on the form above either. See api.js for the same
      rule stated at the boundary.
    -->
    <div class="v2-card" style="padding:15px 16px;margin-top:20px">
      <div style="display:flex;gap:10px;align-items:flex-start">
        <KeyRound size={16} style="color:var(--v2-slate);flex:none;margin-top:2px" />
        <div>
          <div style="font-weight:600;font-size:13px">Los secretos del webhook no se muestran acá</div>
          <p class="v2-sub" style="font-size:12.5px;margin:5px 0 0;line-height:1.5">
            Cada dirección tiene un secreto compartido que prueba que una entrega vino realmente del
            proveedor. Cualquiera que lo tenga puede publicar correo en esta organización como si lo
            hubiera enviado un cliente, así que nunca se renderiza en una página. El servidor lo
            genera cuando se agrega una dirección y no es editable acá; rotarlo es una acción aparte
            que esta página todavía no ofrece.
          </p>
        </div>
      </div>
    </div>

    <p class="v2-sub" style="font-size:11.5px;margin-top:14px">
      A dónde va un ticket nuevo una vez creado lo decide el
      <a href="/settings/routing" style="color:inherit">enrutamiento de tickets</a>, no estos valores
      por defecto.
    </p>
  </div>
</div>

<style>
  .v2-mbx {
    display: flex;
    gap: 13px;
    align-items: flex-start;
    padding: 14px 16px;
  }
  .v2-mbx-defaults {
    display: flex;
    gap: 6px;
    align-items: center;
    flex-wrap: wrap;
    margin-top: 9px;
    font-size: 11.5px;
  }
  .v2-mbx-banner {
    display: flex;
    gap: 11px;
    align-items: flex-start;
    padding: 14px 16px;
    margin-bottom: 18px;
    border: 1px solid var(--v2-line);
    border-radius: var(--v2-radius);
    background: var(--v2-card);
  }
</style>
