<script>
  /**
   * What gates a ticket close, and who can clear it.
   *
   * The queue at /v2/tickets/approvals answers "what is waiting on me". This
   * answers "what will be gated next time, and by whom", the same rows, a
   * different question, which is why it is a settings page and not a tab.
   *
   * One configuration state the model permits and the form does not warn
   * about, shown here: approver_role MANAGER with no named approvers.
   * Profile.role is only ADMIN or USER, so the rule matches nobody and the
   * cases it gates can never be closed by anyone.
   *
   * Separation of duties, an admin clearing their own requested close, is
   * NOT a gap to warn about: `ApprovalApproveView` rejects an approval whose
   * requester is the approver, unconditionally (no admin exception), so the API
   * enforces it however a rule is configured. An earlier version of this page
   * flagged "any admin, including the requester" as a hole; the view has since
   * closed it, so the warning is gone.
   */
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import SettingsFormPanel from '$lib/v2/components/SettingsFormPanel.svelte';
  import ConfirmAction from '$lib/v2/components/ConfirmAction.svelte';
  import { count } from '$lib/v2/format.js';
  import { ROLE_LABEL, CASE_PRIORITY_LABEL, CASE_TYPE_LABEL } from '$lib/v2/enums.js';
  import { missingOptions, inactiveOptionLabel } from '$lib/v2/pickers.js';
  import { Plus, TriangleAlert, ChevronRight } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  // cases.approvals: PRIORITY_CHOICE and CASE_TYPE. Not in `$lib/v2/enums.js`
  // because there is no shared label map to derive from: value and label are
  // the same string for both, and no other v2 page reads either list.
  const MATCH_PRIORITIES = ['Low', 'Normal', 'High', 'Urgent'];
  const MATCH_CASE_TYPES = ['Question', 'Incident', 'Problem'];

  // `ROLE_LABEL` covers `Profile.role` (ADMIN/USER), not the approver-role
  // vocabulary this form offers (ADMIN/MANAGER). MANAGER is not a real
  // `Profile.role` value (see the module docstring), so it has no entry in
  // that map and would render as `undefined`. Labelled here instead.
  function approverRoleLabel(role) {
    return role === 'MANAGER' ? 'Gerente' : (ROLE_LABEL[role] ?? role);
  }

  // `null` when the panel is closed, `'new'` when adding, or the rule object
  // when editing that row. One panel, two modes, so two rows can never be
  // open for edit at once.
  let editing = $state(/** @type {any} */ (null));

  function openCreate() {
    editing = 'new';
  }

  function openEdit(r) {
    editing = r;
  }

  let totals = $derived(data.totals);
  let rules = $derived(data.rules);

  // Named approvers the picker cannot offer, because the profile has been
  // deactivated since it was named. Without an option of their own the
  // multi-select submits nothing for them and an unrelated edit drops them,
  // which can widen a rule to "any admin" or, on a MANAGER rule, leave it
  // clearable by nobody.
  let missingApprovers = $derived(
    editing && editing !== 'new' ? missingOptions(data.people, editing.approvers) : []
  );

  /** MANAGER matches no Profile.role, so an empty approvers list means nobody. */
  const clearableByNobody = (r) =>
    r.is_active && r.approver_role === 'MANAGER' && !r.approvers.length;

  /** What the rule matches, as the sentence a person would say. */
  function matches(r) {
    const parts = [
      r.match_priority ? `prioridad ${CASE_PRIORITY_LABEL[r.match_priority] ?? r.match_priority}` : null,
      r.match_case_type ? (CASE_TYPE_LABEL[r.match_case_type] ?? r.match_case_type).toLowerCase() : null,
      r.match_team ? `equipo ${r.match_team.name}` : null
    ].filter(Boolean);
    return parts.length ? parts.join(' · ') : 'Todo ticket';
  }
</script>

<PageHeader title="Reglas de aprobación">
  {#snippet crumb()}<SettingsCrumb />{/snippet}
  {#snippet sub()}
    <span class="v2-num">{count(totals.active)}</span> activas ·
    <span class="v2-num">{count(totals.pending)}</span> aprobaciones esperando por ellas ahora mismo
  {/snippet}
  {#snippet actions()}
    {#if data.can_edit && !editing}
      <button class="v2-btn v2-btn-primary" onclick={openCreate}><Plus />Nueva regla</button>
    {/if}
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <div class="v2-pad" style="padding-top:18px;padding-bottom:32px">
    {#if editing}
      <SettingsFormPanel
        title={editing === 'new' ? 'Nueva regla' : `Editar ${editing.name}`}
        action={editing === 'new' ? '?/create' : '?/update'}
        error={editing === 'new' ? form?.create?.error : form?.update?.error}
        submitLabel={editing === 'new' ? 'Agregar regla' : 'Guardar regla'}
        oncancel={() => (editing = null)}
        ondone={() => (editing = null)}
      >
        {#snippet fields()}
          {#if editing !== 'new'}
            <input type="hidden" name="id" value={editing.id} />
          {/if}

          <div class="v2-field">
            <label for="a-name">Nombre</label>
            <input
              id="a-name"
              class="v2-input"
              name="name"
              maxlength="128"
              required
              value={editing === 'new' ? '' : editing.name}
            />
          </div>

          <div class="v2-field">
            <label for="a-role">Rol del aprobador</label>
            <select id="a-role" class="v2-input" name="approver_role">
              {#each ['ADMIN', 'MANAGER'] as role (role)}
                <option
                  value={role}
                  selected={editing === 'new' ? role === 'ADMIN' : editing.approver_role === role}
                >
                  {approverRoleLabel(role)}
                </option>
              {/each}
            </select>
          </div>

          <div class="v2-field v2-sfp-wide">
            <label for="a-approvers">Aprobadores nombrados</label>
            <select
              id="a-approvers"
              class="v2-input"
              name="approver_ids"
              multiple
              style="height:96px"
            >
              <!-- A named approver whose profile is no longer active is not in
                   `data.people`, so it gets an option of its own here. Without
                   one the browser submits nothing for it and saving an
                   unrelated field would drop the approver silently. -->
              {#each missingApprovers as a (a.id)}
                <option value={a.id} selected>{inactiveOptionLabel(a.email)}</option>
              {/each}
              {#each data.people as p (p.id)}
                <option
                  value={p.id}
                  selected={editing !== 'new' && editing.approvers.some((a) => a.id === p.id)}
                >
                  {p.name}
                </option>
              {/each}
            </select>
            <p class="v2-hint">
              Los aprobadores nombrados se suman al rol de arriba. Dejá esto vacío y cualquiera con
              ese rol puede destrabar la aprobación.
            </p>
            {#if missingApprovers.length}
              <p class="v2-hint">
                {missingApprovers.length === 1
                  ? 'Un aprobador ya no está activo.'
                  : `${missingApprovers.length} aprobadores ya no están activos.`}
                Se mantienen nombrados hasta que los desmarques, y no pueden destrabar una aprobación
                mientras su cuenta esté apagada.
              </p>
            {/if}
          </div>

          <div class="v2-field">
            <label for="a-priority">Prioridad</label>
            <select id="a-priority" class="v2-input" name="match_priority">
              <option value="" selected={editing === 'new' || !editing.match_priority}>Cualquiera</option>
              {#each MATCH_PRIORITIES as p (p)}
                <option value={p} selected={editing !== 'new' && editing.match_priority === p}>
                  {CASE_PRIORITY_LABEL[p] ?? p}
                </option>
              {/each}
            </select>
          </div>

          <div class="v2-field">
            <label for="a-type">Tipo de ticket</label>
            <select id="a-type" class="v2-input" name="match_case_type">
              <option value="" selected={editing === 'new' || !editing.match_case_type}>
                Cualquiera
              </option>
              {#each MATCH_CASE_TYPES as t (t)}
                <option value={t} selected={editing !== 'new' && editing.match_case_type === t}>
                  {CASE_TYPE_LABEL[t] ?? t}
                </option>
              {/each}
            </select>
          </div>

          <div class="v2-field">
            <label for="a-team">Equipo</label>
            <select id="a-team" class="v2-input" name="match_team_id">
              <option value="" selected={editing === 'new' || !editing.match_team}>Cualquier equipo</option>
              {#each data.teams as t (t.id)}
                <option value={t.id} selected={editing !== 'new' && editing.match_team?.id === t.id}>
                  {t.name}
                </option>
              {/each}
            </select>
            {#if !data.teams.length}
              <p class="v2-hint">Todavía no hay equipos en esta organización.</p>
            {/if}
          </div>

          {#if editing === 'new'}
            <div class="v2-field">
              <label for="a-active">Activa</label>
              <label style="display:flex;gap:8px;align-items:center;font-weight:400">
                <input id="a-active" type="checkbox" name="is_active" value="true" checked />
                Empieza a bloquear los cierres de tickets que coincidan apenas se guarde.
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
    {#if form?.remove?.turned_off}
      <!-- What actually happened, not what the button said. The backend
           soft-disables a rule that has approval history rather than
           destroying it, so the row is still in the list below, off, and
           saying nothing here would read as a delete that failed silently. -->
      <div class="v2-rule-flag" style="margin-bottom:12px">
        <TriangleAlert size={14} style="color:var(--v2-clay);flex:none" />
        <span>
          Esa regla tenía historial de aprobaciones, así que se apagó en vez de eliminarse. Las
          aprobaciones que ya bloqueó tienen que seguir apuntando a ella. Sigue en la lista de abajo,
          marcada Apagada, y no bloquea nada.
        </span>
      </div>
    {/if}

    <div class="v2-label" style="margin-bottom:10px">Reglas</div>
    <div style="display:flex;flex-direction:column;gap:9px">
      {#each rules as r (r.id)}
        <div class="v2-card" style="padding:14px 16px;opacity:{r.is_active ? 1 : 0.62}">
          <div style="display:flex;gap:11px;align-items:flex-start">
            <div style="flex:1;min-width:0">
              <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
                <b style="font-size:13.5px">{r.name}</b>
                {#if !r.is_active}<Pill tone="slate">Apagada</Pill>{/if}
                {#if clearableByNobody(r)}<Pill tone="rust">Nadie puede destrabarla</Pill>{/if}
              </div>

              <div class="v2-sub" style="font-size:12.5px;margin-top:5px;white-space:normal">
                <b style="font-weight:600;color:var(--v2-ink)">Bloquea</b>
                {matches(r)}
                <b style="font-weight:600;color:var(--v2-ink)">→</b>
                se destraba con
                {#if r.approvers.length}
                  {r.approvers.map((a) => a.email).join(' o ')}
                {:else}
                  cualquier {approverRoleLabel(r.approver_role).toLowerCase()}
                {/if}
              </div>

              {#if clearableByNobody(r)}
                <div class="v2-rule-flag">
                  <TriangleAlert size={14} style="color:var(--v2-rust);flex:none" />
                  <span>
                    Esta organización tiene administradores y miembros. No existe el rol de gerente.
                    Sin aprobadores nombrados, el primer ticket que bloquee esto no lo puede cerrar
                    nadie. Nombrá aprobadores, o cambiala a administrador.
                  </span>
                </div>
              {/if}
            </div>

            <div style="flex:none;text-align:right">
              {#if r.pending_count}
                <a
                  href="/tickets/approvals"
                  class="v2-sub"
                  style="font-size:12px;display:inline-flex;align-items:center;gap:2px"
                >
                  <span class="v2-num">{count(r.pending_count)}</span> esperando
                  <ChevronRight size={13} />
                </a>
              {/if}
            </div>

            {#if data.can_edit}
              <div style="display:flex;gap:6px;align-items:center;flex:none">
                <button class="v2-btn v2-btn-sm" type="button" onclick={() => openEdit(r)}>
                  Editar
                </button>
                {#if r.is_active}
                  <ConfirmAction
                    action="?/deactivate"
                    label="Apagar"
                    confirmLabel="Apagar"
                    explain="Deja de bloquear cierres de tickets nuevos. Se mantiene en la lista, apagada, hasta que se vuelva a encender."
                    hidden={{ id: r.id }}
                  />
                {:else}
                  <form method="POST" action="?/activate" use:enhance>
                    <input type="hidden" name="id" value={r.id} />
                    <button class="v2-btn v2-btn-sm" type="submit">Encender</button>
                  </form>
                {/if}
                <!-- Not "deleted permanently". The backend destroys a rule
                     only when it has never been used; one with any approval
                     history, in any state, is turned off instead, because the
                     approval rows have to keep pointing at it. `pending_count`
                     cannot predict which happens: it counts only the pending
                     state, and the backend's check counts every state. So the
                     line names both outcomes, and the page reports which one
                     actually happened afterwards. -->
                <ConfirmAction
                  action="?/remove"
                  label="Eliminar"
                  confirmLabel="Eliminar"
                  explain={r.pending_count > 0
                    ? `${r.pending_count} aprobaciones están esperando por esta regla. Una regla que alguna vez bloqueó un cierre se apaga en vez de eliminarse, porque el registro tiene que conservarse.`
                    : 'Una regla que nunca bloqueó un cierre se elimina para siempre. Una con historial de aprobaciones se apaga en cambio, porque el registro tiene que conservarse.'}
                  hidden={{ id: r.id }}
                />
              </div>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  </div>
</div>

<style>
  .v2-rule-flag {
    display: flex;
    gap: 7px;
    align-items: flex-start;
    margin-top: 9px;
    font-size: 12px;
    color: var(--v2-slate);
    line-height: 1.45;
  }
</style>
