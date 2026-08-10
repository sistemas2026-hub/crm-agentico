<script>
  /**
   * Your own account.
   *
   * The fields that are NOT editable here are the interesting ones. Role is
   * shown and cannot be changed from this page. The API refuses to let anyone
   * change their own role (ProfileSelfUpdateSerializer names only name and
   * phone), and an input that always fails is worse than no input. Same for the
   * organisation: which org you are in decides which rows you can see at all,
   * and it comes from the JWT, not from a form.
   *
   * Two things you CAN do: edit your name and phone (PATCH /profile/), and
   * switch org, a real action that re-issues the token rather than editing a
   * field, so it goes through its own action and the copy says so.
   */
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import Avatar from '$lib/v2/components/Avatar.svelte';
  import { relativeDays, shortDate, count } from '$lib/v2/format.js';
  import { ROLE_LABEL, ROLE_TONE } from '$lib/v2/enums.js';
  import { KeyRound, Lock, ArrowLeftRight } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let p = $derived(data.profile);
  let name = $derived(`${p.user_details.first_name} ${p.user_details.last_name}`.trim());

  // Editing name + phone. The backend stores one `name` on User, so the form
  // offers a single full-name field rather than the split the header renders.
  let editing = $state(false);
  let editName = $state('');
  let editPhone = $state('');

  function openEdit() {
    editName = name;
    editPhone = p.phone || '';
    editing = true;
  }

  const onEdit = (/** @type {any} */ { formData }) => {
    // Only send the field the person actually changed. The PATCH treats an
    // absent field as "leave it alone", so an untouched phone is not
    // re-validated, which matters because some seeded numbers carry an
    // extension the validator rejects, and re-sending one would block a plain
    // name change. Same rule the leads form uses for its owner select.
    if ((formData.get('name') ?? '') === name) formData.delete('name');
    if ((formData.get('phone') ?? '') === (p.phone || '')) formData.delete('phone');

    return async (/** @type {any} */ { result, update }) => {
      if (result.type === 'success') {
        editing = false;
        await update(); // reloads the profile with the saved values
      } else {
        await update({ reset: false }); // keep what they typed, show the message
      }
    };
  };

  // `form` is shared by both actions; the switch action tags its failures.
  let editError = $derived(form?.scope === 'switch' ? '' : (form?.message ?? ''));
  let switchError = $derived(form?.scope === 'switch' ? (form?.message ?? '') : '');
</script>

<PageHeader title={name} record>
  {#snippet sub()}
    {ROLE_LABEL[p.role]} · {data.org.name} · ingresó el {shortDate(p.joined_at)}
  {/snippet}
  {#snippet actions()}
    {#if !editing}
      <button class="v2-btn v2-btn-primary" onclick={openEdit}>Editar datos</button>
    {/if}
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <div class="v2-pad" style="padding-top:18px;padding-bottom:32px">
    <div class="v2-split">
      <div>
        <div class="v2-label" style="margin-bottom:10px">Vos</div>

        {#if editing}
          <form
            class="v2-card"
            method="POST"
            action="?/edit"
            use:enhance={onEdit}
            style="padding:17px 18px;margin-bottom:20px"
          >
            <div class="v2-field">
              <label for="f-name">Nombre completo</label>
              <input
                id="f-name"
                name="name"
                class="v2-input"
                bind:value={editName}
                maxlength="255"
              />
            </div>
            <div class="v2-field" style="margin-top:12px">
              <label for="f-phone">Teléfono</label>
              <input
                id="f-phone"
                name="phone"
                class="v2-input"
                bind:value={editPhone}
                placeholder="+44 20 7946 0100"
              />
              <p class="v2-hint">Solo dígitos y separadores. Dejalo en blanco para quitarlo.</p>
            </div>
            {#if editError}
              <p class="v2-error" style="margin-top:10px">{editError}</p>
            {/if}
            <div style="display:flex;gap:8px;margin-top:16px">
              <button class="v2-btn v2-btn-primary" type="submit">Guardar</button>
              <button class="v2-btn" type="button" onclick={() => (editing = false)}>Cancelar</button>
            </div>
          </form>
        {:else}
          <div class="v2-card" style="padding:17px 18px;margin-bottom:20px">
            <div style="display:flex;gap:13px;align-items:center;margin-bottom:16px">
              <Avatar {name} size={46} />
              <div style="min-width:0">
                <div style="font-weight:640;font-size:15px">{name}</div>
                <div class="v2-sub" style="font-size:12.5px">{p.user_details.email}</div>
              </div>
            </div>
            <dl class="v2-kv">
              <dt>Teléfono</dt>
              <dd class="v2-num" style="font-size:12px">{p.phone || '—'}</dd>
              <dt>Equipos</dt>
              <dd>{p.teams.join(', ') || '—'}</dd>
              <dt>Ingresó</dt>
              <dd>{shortDate(p.joined_at)}</dd>
              <dt>Último inicio de sesión</dt>
              <dd>{relativeDays(p.last_login)}</dd>
            </dl>
          </div>
        {/if}

        <div class="v2-label" style="margin-bottom:10px">Organizaciones</div>
        <div class="v2-card" style="overflow:hidden">
          {#each p.orgs as o (o.id)}
            <div class="v2-setting">
              <div class="v2-setting-body">
                <b>{o.name}</b>
                <span class="v2-sub" style="font-size:11.5px">
                  Sos {o.role === 'ADMIN' ? 'administrador' : 'miembro'} acá
                </span>
              </div>
              {#if o.is_current}
                <Pill tone="ink" dot>Actual</Pill>
              {:else}
                <!-- Switching org re-issues the token; it does not edit a field
                     on this page. The action swaps the cookies and reloads. -->
                <form method="POST" action="?/switchOrg" use:enhance class="v2-inline-form">
                  <input type="hidden" name="org_id" value={o.id} />
                  <button class="v2-btn v2-btn-sm" type="submit">
                    <ArrowLeftRight size={12} />Cambiar
                  </button>
                </form>
              {/if}
            </div>
          {/each}
        </div>
        {#if switchError}
          <p class="v2-error" style="margin-top:9px">{switchError}</p>
        {/if}
        <p class="v2-sub" style="font-size:11.5px;margin-top:11px">
          Cambiar de organización te vuelve a iniciar sesión con un token nuevo. La organización en
          la que estás decide qué registros existen para vos, así que no es un filtro que puedas
          activar y desactivar.
        </p>
      </div>

      <div>
        <div class="v2-label" style="margin-bottom:10px">Acceso</div>
        <div class="v2-card" style="overflow:hidden;margin-bottom:20px">
          <div class="v2-setting">
            <div class="v2-setting-body">
              <b>Rol</b>
              <!-- Displayed, never editable from here. -->
              <span class="v2-sub" style="font-size:11.5px">
                Lo define un administrador. No podés cambiar tu propio rol.
              </span>
            </div>
            <Lock size={14} style="color:var(--v2-slate);flex:none" />
            <Pill tone={ROLE_TONE[p.role]}>{ROLE_LABEL[p.role]}</Pill>
          </div>
          <a class="v2-setting" href="/settings/api-tokens">
            <div class="v2-setting-body">
              <b>Tokens de API</b>
              <span class="v2-sub" style="font-size:11.5px">
                Cada uno inicia sesión como vos, con tu rol.
              </span>
            </div>
            <KeyRound size={14} style="color:var(--v2-slate);flex:none" />
            <span class="v2-num" style="font-size:13px;font-weight:600">
              {count(p.active_token_count)}
            </span>
          </a>
          <div class="v2-setting">
            <div class="v2-setting-body">
              <b>Método de inicio de sesión</b>
              <span class="v2-sub" style="font-size:11.5px">
                Google, con {p.user_details.email}. No hay contraseña para cambiar.
              </span>
            </div>
          </div>
        </div>

        <div class="v2-label" style="margin-bottom:10px">Dónde aparece tu trabajo</div>
        <div class="v2-card" style="overflow:hidden">
          <a class="v2-setting" href="/goals">
            <div class="v2-setting-body">
              <b>Metas</b>
              <span class="v2-sub" style="font-size:11.5px">Tu cuota y cómo va el ritmo</span>
            </div>
          </a>
          <a class="v2-setting" href="/timesheet">
            <div class="v2-setting-body">
              <b>Registro de horas</b>
              <span class="v2-sub" style="font-size:11.5px">Horas que registraste esta semana</span>
            </div>
          </a>
          <a class="v2-setting" href="/tasks">
            <div class="v2-setting-body">
              <b>Tareas</b>
              <span class="v2-sub" style="font-size:11.5px">Lo que tenés asignado</span>
            </div>
          </a>
        </div>
      </div>
    </div>
  </div>
</div>

<style>
  /* The Switch button sits in a form so it can POST; keep it laid out exactly
     as the bare button was (the row uses flex; the form must not add a box). */
  .v2-inline-form {
    display: contents;
  }
</style>
