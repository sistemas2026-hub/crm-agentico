<script>
  /**
   * Personal access tokens: the org-wide oversight view.
   *
   * THE ONE RULE THIS PAGE EXISTS TO KEEP
   * A token value is shown once, in the response to the request that created
   * it, and never again. The server stores a SHA-256 hash plus a 13-character
   * prefix, so there is nothing to re-display even if someone asks. Every row
   * here shows the prefix and stops. The one-time reveal below is the only
   * place a full value ever appears, and it is gone on the next reload.
   *
   * WHO SEES THIS
   * This lists every token across the org, so it is admin-only: `/api/org/tokens/`
   * returns 403 to a member and the page renders "Admins only" rather than a
   * broken table. Managing your own tokens is a separate, self-scoped surface.
   *
   * "OWNER DEACTIVATED" IS A DORMANT ROW, NOT A LIVE ONE
   * The mock this page replaced claimed such a token "keeps working with the
   * role they had". It does not: deactivating an account sets profile.is_active
   * false, and that is exactly the flag the token authenticator checks, so the
   * token is refused at login today. It is worth revoking anyway. It would come
   * back if the account were reactivated, which is why it is surfaced in clay
   * (a loose end) rather than rust (a live breach).
   *
   * SCOPES ARE NOW REAL, AND THIS COMMENT USED TO SAY THE OPPOSITE
   * It read: "the model stores scopes for forward-compatibility but nothing
   * enforces them ... a UI that draws a tidy list of scopes would describe a
   * boundary that does not exist." That was true and worth saying. It stopped
   * being true when `common/scopes.py` landed and the middleware began
   * refusing out-of-scope requests before the view runs.
   *
   * So the form offers the choice, and the table names it per row. Two options,
   * not thirty: the backend grammar is `<resource>:<action>` and supports
   * `leads:read`, but a radio pair is the honest shape for a question most
   * people answer once, and "may this token change anything?" is the part that
   * matters. Anyone who wants finer scopes creates the token through the API.
   *
   * An empty scope list still means unrestricted, which is what every token
   * issued before enforcement carries. That is why the table says "Everything
   * <name> can" for those rows rather than pretending they are limited.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';
  import StatCard from '$lib/v2/components/StatCard.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import NextAction from '$lib/v2/components/NextAction.svelte';
  import { count, relativeDays, shortDate, daysSince } from '$lib/v2/format.js';
  import { ROLE_LABEL } from '$lib/v2/enums.js';
  import { enhance } from '$app/forms';
  import { Plus, ShieldAlert, Copy, Check } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let totals = $derived(data.totals);

  let creating = $state(false);
  let busy = $state(false);
  let copied = $state(false);

  /** A submit handler that flips `busy` while the action runs. */
  const working = () => {
    busy = true;
    return async (/** @type {any} */ { update }) => {
      await update();
      busy = false;
    };
  };

  /** Create both submits and, on success, closes its own form. */
  const createSubmit = () => {
    busy = true;
    return async (/** @type {any} */ { update, result }) => {
      await update();
      busy = false;
      if (result?.type === 'success' && result?.data?.created) creating = false;
    };
  };

  /** @param {string} value */
  async function copyToken(value) {
    try {
      await navigator.clipboard.writeText(value);
      copied = true;
      setTimeout(() => (copied = false), 1600);
    } catch {
      // Clipboard blocked (no https / no permission). The value is on screen to
      // select by hand, nothing else to do, and no error worth alarming over.
    }
  }

  /**
   * Revoked and expired are different reasons for the same outcome, so they
   * read differently but tone the same. Neither is a live credential.
   *
   * @param {any} t
   * @returns {{ label: string, tone: 'ink'|'slate'|'clay'|'rust'|'moss' }}
   */
  function statusOf(t) {
    if (t.revoked_at) return { label: 'Revocado', tone: 'slate' };
    if (!t.is_live) return { label: 'Vencido', tone: 'slate' };
    return { label: 'Activo', tone: 'moss' };
  }

  /** Never used, or not for a long time. Either way it is a key under a mat. */
  function staleness(t) {
    if (!t.is_live) return null;
    if (!t.last_used_at) return 'nunca usado';
    const n = daysSince(t.last_used_at) ?? 0;
    return n > 90 ? `sin usar hace ${n} días` : null;
  }
</script>

{#if data.forbidden}
  <PageHeader title="Tokens de API">
    {#snippet crumb()}<SettingsCrumb />{/snippet}
  </PageHeader>
  <div class="v2-pad" style="padding-top:40px">
    <NextAction
      label="Solo administradores"
      text="Revisar todos los tokens de la organización está limitado a administradores, porque un token se autentica como su dueño. Pedile a un administrador si hace falta emitir o revocar uno."
    />
  </div>
{:else}
  <PageHeader title="Tokens de API">
    {#snippet crumb()}<SettingsCrumb />{/snippet}
    {#snippet sub()}
      <span class="v2-num">{count(totals.live)}</span> activos de
      <span class="v2-num">{count(totals.count)}</span> emitidos en total
    {/snippet}
    {#snippet actions()}
      <button class="v2-btn v2-btn-primary" onclick={() => (creating = !creating)}>
        <Plus />Nuevo token
      </button>
    {/snippet}
  </PageHeader>

  <div class="v2-pad" style="padding-top:16px;flex:none">
    <div class="v2-stats">
      <StatCard label="Tokens activos" value={count(totals.live)} tone="ink" />
      <StatCard
        label="Dueño desactivado"
        value={count(totals.orphaned)}
        tone={totals.orphaned ? 'clay' : 'slate'}
        detail={totals.orphaned ? 'Rechazado al iniciar sesión, no revocado' : 'Ninguno'}
      />
      <StatCard
        label="Sin usar hace 90+ días"
        value={count(totals.unused_90d)}
        tone={totals.unused_90d ? 'clay' : 'slate'}
      />
      <StatCard label="Emitidos en total" value={count(totals.count)} tone="slate" />
    </div>
  </div>

  <div class="v2-scroll">
    <div class="v2-pad" style="padding-bottom:32px">
      {#if form?.created?.token}
        <!-- The one and only time this value is shown. On the next reload it is
             gone; the list will have the prefix and nothing more. -->
        <div
          class="v2-card"
          style="padding:15px 16px;margin-bottom:18px;border-color:color-mix(in srgb, var(--v2-moss) 40%, var(--v2-line))"
        >
          <div style="font-weight:650;font-size:13px">
            “{form.created.name}” creado, copialo ahora
          </div>
          <p class="v2-sub" style="font-size:12px;margin:4px 0 10px">
            Esta es la única vez que se muestra el token completo. Guardalo en un lugar seguro; no
            se puede volver a recuperar.
          </p>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <code
              class="v2-num"
              style="flex:1;min-width:220px;background:var(--v2-bg-sunk);border:1px solid var(--v2-line);border-radius:var(--v2-radius);padding:9px 11px;font-size:12.5px;word-break:break-all"
            >
              {form.created.token}
            </code>
            <button class="v2-btn v2-btn-sm" onclick={() => copyToken(form.created.token)}>
              {#if copied}<Check size={13} />Copiado{:else}<Copy size={13} />Copiar{/if}
            </button>
          </div>
        </div>
      {/if}

      {#if form?.revokedOrphaned}
        <p
          class="v2-sub"
          style="color:var(--v2-moss);font-size:12.5px;margin:0 0 16px;font-weight:550"
        >
          Se {form.revokedOrphaned === 1 ? 'revocó' : 'revocaron'} {form.revokedOrphaned}
          {form.revokedOrphaned === 1 ? 'token' : 'tokens'} de cuentas desactivadas.
        </p>
      {:else if form?.error}
        <div style="margin-bottom:16px">
          <NextAction label="Eso no funcionó" text={form.error} tone="rust" />
        </div>
      {/if}

      {#if creating}
        <form
          method="POST"
          action="?/create"
          use:enhance={createSubmit}
          class="v2-card"
          style="padding:14px 15px;margin-bottom:18px;display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap"
        >
          <div style="flex:1;min-width:220px">
            <label class="v2-label" for="token-name" style="display:block;margin-bottom:4px">
              ¿Para qué es este token?
            </label>
            <input
              id="token-name"
              name="name"
              required
              maxlength="255"
              class="v2-input"
              style="width:100%"
              placeholder="ej. Exportación nocturna"
            />
          </div>
          <div>
            <label class="v2-label" for="token-access" style="display:block;margin-bottom:4px">
              Acceso
            </label>
            <select id="token-access" name="access" class="v2-input" style="width:180px">
              <option value="read" selected>Solo lectura</option>
              <option value="full">Todo lo que puede hacer el dueño</option>
            </select>
          </div>
          <div>
            <label class="v2-label" for="token-expiry" style="display:block;margin-bottom:4px">
              Vence
            </label>
            <select id="token-expiry" name="expiry" class="v2-input" style="width:150px">
              <option value="90" selected>En 90 días</option>
              <option value="30">En 30 días</option>
              <option value="365">En 1 año</option>
              <option value="never">Nunca</option>
            </select>
          </div>
          <button class="v2-btn v2-btn-primary" disabled={busy}>Crear token</button>
          <button type="button" class="v2-btn" disabled={busy} onclick={() => (creating = false)}>
            Cancelar
          </button>
          {#if form?.create?.error}
            <p
              class="v2-sub"
              style="color:var(--v2-rust);font-size:12px;flex-basis:100%;margin:2px 0 0"
            >
              {form.create.error}
            </p>
          {/if}
        </form>
      {/if}

      {#if totals.orphaned}
        <div style="margin-bottom:18px">
          <NextAction
            label="Cabo suelto"
            text={`${totals.orphaned} ${totals.orphaned === 1 ? 'token activo pertenece' : 'tokens activos pertenecen'} a una cuenta desactivada. Desactivarla ya los frena al iniciar sesión, pero no están revocados. Si se reactiva la cuenta, volverían a funcionar.`}
          />
          <form
            method="POST"
            action="?/revokeOrphaned"
            use:enhance={working}
            style="margin-top:10px"
          >
            <button class="v2-btn v2-btn-primary" disabled={busy}>
              Revocar{totals.orphaned === 1 ? 'lo' : 'los todos'}
            </button>
          </form>
        </div>
      {/if}

      <div class="v2-table-wrap">
        <table class="v2-table">
          <thead>
            <tr>
              <th>Token</th>
              <th>Dueño</th>
              <th data-m="hide">Puede hacer</th>
              <th data-m="hide">Último uso</th>
              <th data-m="hide">Vence</th>
              <th class="v2-r">Estado</th>
            </tr>
          </thead>
          <tbody>
            {#each data.tokens as t (t.id)}
              {@const s = statusOf(t)}
              {@const stale = staleness(t)}
              {@const owner = t.owner ?? {}}
              <tr style={t.is_live ? '' : 'opacity:.55'}>
                <td>
                  <span class="v2-table-primary">{t.name}</span>
                  <!-- The prefix, and only the prefix. There is no full value to
                       show: the server keeps a hash. -->
                  <span class="v2-table-secondary v2-num" style="display:block">
                    {t.token_prefix}…
                  </span>
                </td>
                <td data-m="meta">
                  {owner.name}
                  <span class="v2-table-secondary" style="display:block">
                    {ROLE_LABEL[owner.role] ?? owner.role}{owner.is_active === false
                      ? ' · deactivated'
                      : ''}
                  </span>
                </td>
                <td data-m="hide">
                  <span class="v2-sub" style="font-size:12px">
                    {#if (t.scopes ?? []).length === 0}
                      Todo lo que puede {(owner.name ?? '').split(' ')[0]}
                    {:else if (t.scopes ?? []).every((/** @type {string} */ s) => s.endsWith(':read'))}
                      Solo lectura
                    {:else}
                      {(t.scopes ?? []).join(', ')}
                    {/if}
                  </span>
                </td>
                <td data-m="hide">
                  {#if t.last_used_at}
                    {relativeDays(t.last_used_at)}
                  {:else}
                    <span class="v2-muted">nunca</span>
                  {/if}
                  {#if stale}
                    <span
                      class="v2-table-secondary"
                      style="display:block;color:var(--v2-clay);font-weight:600"
                    >
                      {stale}
                    </span>
                  {/if}
                </td>
                <td data-m="hide">
                  {#if t.expires_at}
                    {shortDate(t.expires_at)}
                  {:else}
                    <span class="v2-sub">nunca vence</span>
                  {/if}
                </td>
                <td class="v2-r">
                  <span style="display:inline-flex;gap:7px;align-items:center">
                    <Pill tone={s.tone}>{s.label}</Pill>
                    {#if t.is_live}
                      <form method="POST" action="?/revoke" use:enhance={working}>
                        <input type="hidden" name="id" value={t.id} />
                        <button class="v2-btn v2-btn-sm" disabled={busy}>Revocar</button>
                      </form>
                    {/if}
                  </span>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>

      <div
        style="display:flex;gap:10px;align-items:flex-start;margin-top:20px;padding:14px 16px;border:1px solid var(--v2-line);border-radius:var(--v2-radius)"
      >
        <ShieldAlert size={16} style="color:var(--v2-clay);flex:none;margin-top:1px" />
        <div>
          <div style="font-weight:600;font-size:13px">Un token es la cuenta entera</div>
          <p class="v2-sub" style="font-size:12px;margin:4px 0 0">
            Un token se autentica como su dueño y hereda su rol y su organización. No hay un
            permiso más acotado para darle. Emití uno por integración para que una sola revocación
            frene una sola cosa, ponele vencimiento, y revocá cualquiera del que no puedas nombrar
            un uso. El valor se muestra una vez cuando se crea el token y no se puede recuperar
            después.
          </p>
        </div>
      </div>
    </div>
  </div>
{/if}
