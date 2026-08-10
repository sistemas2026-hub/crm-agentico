<script>
  import '../../../app.css';
  import '$lib/v2/styles/v2.css';
  import imgLogo from '$lib/assets/images/logo.png';
  import { Building2, LogOut, Plus, ChevronRight } from '@lucide/svelte';
  import { enhance } from '$app/forms';

  let { data = { orgs: [] } } = $props();
  let orgs = $derived(data?.orgs ?? []);

  let loading = $state(false);
  let selectedOrgId = $state(null);

  const ROLE_LABELS = { admin: 'administrador', user: 'miembro' };
  const roleLabel = (role) => ROLE_LABELS[role?.toLowerCase()] || 'miembro';
</script>

<svelte:head>
  <title>Elegir organización · BottleCRM</title>
</svelte:head>

<div class="v2-root v2-auth">
  <div class="v2-auth-box">
    <a href="/" class="v2-auth-brand">
      <img src={imgLogo} alt="" />
      <b>BottleCRM</b>
    </a>

    <div class="v2-auth-card">
      <div class="v2-auth-head">
        <h1>Elegí una organización</h1>
        <p>
          {orgs.length
            ? 'Elegí el espacio de trabajo que querés abrir.'
            : 'Creá tu primer espacio de trabajo para empezar.'}
        </p>
      </div>

      {#if orgs.length > 0}
        {#each orgs as org (org.id)}
          <form
            method="POST"
            action="?/selectOrg"
            use:enhance={() => {
              loading = true;
              selectedOrgId = org.id;
              return async ({ update }) => {
                await update();
                loading = false;
                selectedOrgId = null;
              };
            }}
          >
            <input type="hidden" name="org_id" value={org.id} />
            <input type="hidden" name="org_name" value={org.name} />
            <button type="submit" class="v2-auth-org" disabled={loading}>
              <span class="v2-mark" style="width:30px;height:30px;border-radius:8px;font-size:13px">
                {org.name?.slice(0, 1)?.toUpperCase() || '?'}
              </span>
              <span class="v2-auth-org-body">
                <b>{org.name}</b>
                <span class="v2-sub" style="display:block;text-transform:capitalize">
                  {roleLabel(org.role)}
                </span>
              </span>
              {#if loading && selectedOrgId === org.id}
                <span class="v2-spin"></span>
              {:else}
                <ChevronRight />
              {/if}
            </button>
          </form>
        {/each}

        <a href="/org/new" class="v2-auth-add">
          <Plus />
          Crear nueva organización
        </a>
      {:else}
        <div class="v2-state" style="padding:22px 0 8px">
          <div class="v2-state-icon"><Building2 size={22} /></div>
          <h3>Todavía no hay organizaciones</h3>
          <p>Creá tu primer espacio de trabajo para empezar a usar BottleCRM.</p>
          <a href="/org/new" class="v2-btn v2-btn-primary">
            <Plus size={15} />
            Crear organización
          </a>
        </div>
      {/if}
    </div>

    <div class="v2-auth-foot">
      <a href="/logout" style="display:inline-flex;align-items:center;gap:5px">
        <LogOut size={13} /> Cerrar sesión
      </a>
    </div>
  </div>
</div>
