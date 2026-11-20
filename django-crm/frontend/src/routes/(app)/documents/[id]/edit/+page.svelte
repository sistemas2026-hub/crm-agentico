<script>
  import { untrack, tick } from 'svelte';
  import { SvelteSet } from 'svelte/reactivity';
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import NextAction from '$lib/v2/components/NextAction.svelte';
  import { TriangleAlert, Users, Lock } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form: result } = $props();

  /**
   * Rename, archive, and re-share, the mutations that used to be reachable by
   * anyone a document was shared with. The page is only ever drawn for a writer
   * (owner or admin); the PUT enforces the same, so this is the UX side of the
   * `_may_write` fix.
   *
   * The file itself is not replaced here. Swapping the bytes behind a title is
   * a new upload, kept apart so a rename cannot quietly change what the document
   * *is*. VALIDATION IS A UX HINT: the serializer requires a title and rejects a
   * duplicate within the org regardless of what this page allows.
   */
  // Seed once from the loaded document, or from a rejected submit's echoed
  // values. Read inside untrack so this captures the initial state without
  // subscribing the form fields to later `data` changes (there are none, an
  // edit page loads one document).
  const init = untrack(() => {
    const prev = result?.values ?? {};
    const doc = data.document ?? {};
    return {
      title: prev.title ?? doc.title ?? '',
      status: prev.status ?? doc.status ?? 'active',
      shared_to: (prev.shared_to ?? doc.shared_to ?? []).map(String),
      teams: (prev.teams ?? doc.teams ?? []).map(String)
    };
  });

  let title = $state(init.title);
  let status = $state(init.status);
  // SvelteSet is reactive on mutation, so the checkboxes and the reach line
  // update on `.add()`/`.delete()` without reassigning the whole set.
  let sharedTo = new SvelteSet(init.shared_to);
  let sharedTeams = new SvelteSet(init.teams);

  let touched = $state(/** @type {Record<string, boolean>} */ ({}));
  let submitted = $state(false);
  let confirmingDelete = $state(false);

  let errors = $derived.by(() => {
    /** @type {Record<string, string>} */
    const e = {};
    if (!title.trim()) e.title = 'Un documento necesita un título.';
    return e;
  });

  let valid = $derived(Object.keys(errors).length === 0);
  const show = (field) => (touched[field] || submitted) && errors[field];

  let reach = $derived(sharedTo.size + sharedTeams.size);

  function toggle(/** @type {SvelteSet<string>} */ set, /** @type {string} */ id) {
    if (set.has(id)) set.delete(id);
    else set.add(id);
  }

  /** @type {import('./$types').SubmitFunction} */
  const check = async ({ cancel }) => {
    submitted = true;
    if (!valid) {
      cancel();
      await tick();
      /** @type {HTMLElement | null} */
      const first = document.querySelector('[aria-invalid="true"]');
      first?.focus();
    }
  };
</script>

{#if !data.can_edit}
  <PageHeader title="Gestionar documento">
    {#snippet crumb()}<a href="/documents">Documentos</a> ›{/snippet}
  </PageHeader>
  <div class="v2-pad" style="padding-top:40px">
    <NextAction
      label="Solo el propietario o un administrador"
      text="Cambiar un documento está limitado a quien lo subió y a los administradores. Podés abrir un documento compartido con vos, pero no editarlo."
    />
  </div>
{:else}
  <PageHeader title="Gestionar documento" center>
    {#snippet crumb()}<a href="/documents">Documentos</a> ›{/snippet}
    {#snippet sub()}{data.document.title}{/snippet}
  </PageHeader>

  <div class="v2-scroll v2-pad" style="padding-top:18px">
    <form class="v2-form" method="POST" action="?/save" use:enhance={check} novalidate>
      {#if result?.error}
        <div
          class="v2-next"
          style="background:color-mix(in srgb, var(--v2-rust) 9%, transparent);border-color:color-mix(in srgb, var(--v2-rust) 28%, transparent);margin-bottom:18px"
          role="alert"
        >
          <TriangleAlert size={17} style="color:var(--v2-rust);flex:none" />
          <div class="v2-next-body">
            <div style="font-weight:600">El servidor rechazó este cambio</div>
            <div class="v2-sub" style="margin-top:2px">{result.error}</div>
          </div>
        </div>
      {/if}

      <div class="v2-field">
        <label for="f-title">Título</label>
        <input
          id="f-title"
          name="title"
          class="v2-input"
          bind:value={title}
          onblur={() => (touched.title = true)}
          aria-invalid={show('title') ? 'true' : undefined}
          aria-describedby={show('title') ? 'e-title' : undefined}
        />
        {#if show('title')}<p class="v2-error" id="e-title">{errors.title}</p>{/if}
      </div>

      <div class="v2-field">
        <span class="pseudo-label">Archivo</span>
        <p class="v2-input v2-file-static">{data.document.document_file}</p>
        <p class="v2-hint">El archivo no se reemplaza acá, subí un documento nuevo para cambiarlo.</p>
      </div>

      <div class="v2-field">
        <label for="f-status">Estado</label>
        <select id="f-status" name="status" class="v2-input" bind:value={status}>
          <option value="active">Activo, aparece en la lista</option>
          <option value="inactive">Archivado, se conserva, oculto de la vista predeterminada</option>
        </select>
      </div>

      <fieldset class="v2-field share">
        <legend>Quién puede abrirlo</legend>
        <p class="v2-hint" style="margin-top:0">
          {#if reach === 0}
            <span class="unshared"><Lock size={11} /> Solo el propietario y los administradores.</span>
          {:else}
            Llega a <span class="v2-num">{reach}</span>
            {reach === 1 ? 'persona o equipo' : 'personas y equipos'}, más los administradores.
          {/if}
        </p>

        {#if data.people?.length}
          <div class="share-label">Personas</div>
          <div class="share-grid">
            {#each data.people as p (p.id)}
              <label class="share-opt">
                <input
                  type="checkbox"
                  name="shared_to"
                  value={p.id}
                  checked={sharedTo.has(String(p.id))}
                  onchange={() => toggle(sharedTo, String(p.id))}
                />
                <span>{p.name}</span>
              </label>
            {/each}
          </div>
        {/if}

        {#if data.teams?.length}
          <div class="share-label"><Users size={12} /> Equipos</div>
          <div class="share-grid">
            {#each data.teams as t (t.id)}
              <label class="share-opt">
                <input
                  type="checkbox"
                  name="teams"
                  value={t.id}
                  checked={sharedTeams.has(String(t.id))}
                  onchange={() => toggle(sharedTeams, String(t.id))}
                />
                <span>{t.name}</span>
              </label>
            {/each}
          </div>
        {/if}
      </fieldset>

      <div style="display:flex;gap:8px;align-items:center;margin-top:22px">
        <button class="v2-btn v2-btn-primary" type="submit">Guardar cambios</button>
        <a class="v2-btn" href="/documents">Cancelar</a>
      </div>
    </form>

    <!-- Delete sits apart from the save form and behind an inline confirm, so a
         mis-click cannot destroy a document for everyone, no blocking browser
         dialog, just a second, deliberate button. -->
    <div
      style="margin-top:26px;padding-top:18px;border-top:1px solid var(--v2-line-soft);max-width:640px"
    >
      {#if !confirmingDelete}
        <button
          class="v2-btn"
          type="button"
          style="color:var(--v2-rust)"
          onclick={() => (confirmingDelete = true)}>Eliminar este documento</button
        >
        <p class="v2-sub" style="font-size:12px;margin-top:8px">
          Archivar conserva el documento y su historial; eliminar lo quita para todos los que
          podían abrirlo. Eliminá solo cuando se subió por error.
        </p>
      {:else}
        <form method="POST" action="?/delete" use:enhance>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <span class="v2-sub" style="font-size:13px"
              >¿Eliminar “{data.document.title}” definitivamente?</span
            >
            <button class="v2-btn v2-btn-primary" type="submit" style="background:var(--v2-rust)"
              >Sí, eliminar</button
            >
            <button class="v2-btn" type="button" onclick={() => (confirmingDelete = false)}
              >Conservarlo</button
            >
          </div>
        </form>
      {/if}
    </div>
  </div>
{/if}

<style>
  .share {
    border: 1px solid var(--v2-line-soft);
    border-radius: 8px;
    padding: 14px 16px;
  }
  .share legend {
    font-weight: 600;
    padding: 0 6px;
  }
  .unshared {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--v2-clay);
  }
  .share-label {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 12px;
    font-weight: 600;
    color: var(--v2-slate);
    margin: 12px 0 6px;
  }
  .share-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px 14px;
  }
  @media (max-width: 560px) {
    .share-grid {
      grid-template-columns: 1fr;
    }
  }
  .share-opt {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13.5px;
    cursor: pointer;
  }
  .share-opt input {
    flex: none;
  }
  .v2-file-static {
    font-family: var(--v2-mono);
    font-size: 12px;
    color: var(--v2-slate);
    margin: 0;
  }
  .pseudo-label {
    display: block;
    font-size: 12.5px;
    font-weight: 600;
    margin-bottom: 5px;
  }
</style>
