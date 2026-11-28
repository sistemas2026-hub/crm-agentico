<script>
  import '../../../app.css';
  import '$lib/v2/styles/v2.css';
  import { Building2, LogOut, ChevronRight } from '@lucide/svelte';
  import { enhance } from '$app/forms';

  let { data = { orgs: [] } } = $props();
  let orgs = $derived(data?.orgs ?? []);

  let loading = $state(false);
  let selectedOrgId = $state(null);

  const ROLE_LABELS = { admin: 'administrador', user: 'miembro' };
  const roleLabel = (role) => ROLE_LABELS[role?.toLowerCase()] || 'miembro';
</script>

<svelte:head>
  <title>Elegir organización · Dexter</title>
</svelte:head>

<div class="v2-root v2-auth">
  <div class="v2-auth-box">
    <a href="/" class="v2-auth-brand">
      <span class="v2-mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.3" stroke-linecap="round"><path d="M5 12a7 7 0 0 1 14 0M8.5 12a3.5 3.5 0 0 1 7 0M12 13v7" /></svg></span>
      <b>Dexter</b>
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
            <!-- A donde volver despues de elegir. Sin esto la accion no tiene
                 forma de saberlo: recibe el POST del formulario, no la query
                 de esta pagina. -->
            {#if data.volverA}
              <input type="hidden" name="redirect" value={data.volverA} />
            {/if}
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

        <!-- Sin "Crear nueva organizacion": a una cuenta comun el backend se
             lo niega (ver el estado vacio de abajo). La plataforma da de alta
             un ISP desde /org/new. -->
      {:else}
        <!-- Antes ofrecia "Crear organizacion" a cualquiera que llegara aca. Desde
             el 23/10/2026 crear una es tarea de la plataforma (el backend lo
             niega a una cuenta comun: PERMITIR_AUTORREGISTRO), asi que el
             camino real de alguien sin empresa es que lo sumen. -->
        <div class="v2-state" style="padding:22px 0 8px">
          <div class="v2-state-icon"><Building2 size={22} /></div>
          <h3>Tu cuenta todavía no está en ninguna empresa</h3>
          <p>Pedile a un administrador de tu empresa que te sume desde Equipo y accesos.</p>
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
