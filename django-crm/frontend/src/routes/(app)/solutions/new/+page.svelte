<script>
  /**
   * New knowledge-base article.
   *
   * ── TWO SWITCHES, NOT ONE ────────────────────────────────────────────────
   * `cases.Solution` carries `status` (draft → reviewed → approved) AND a
   * separate `is_published` boolean, and they answer different questions:
   * status is "has a human checked this", published is "can a customer read
   * it". The list page exists partly to surface the row where they disagree,
   * approved and still invisible.
   *
   * ── WHERE THE MOCK WAS WRONG ─────────────────────────────────────────────
   * This form used to offer both switches freely and told the writer that a
   * published draft was "allowed, and sometimes right, but it is a choice,
   * not an accident". It was neither: `Solution.publish()` has always refused
   * it, and the serializer now refuses it on every path in. The old page could
   * say that because it never submitted anything.
   *
   * What is true is narrower and more useful, so the form says that instead:
   * publishing needs an approval, approving is somebody else's job, and a
   * writer's article starts as a draft. The publish switch only appears for
   * an admin. For anyone else it would be a control that answers 403.
   *
   * ── WHAT THIS FORM DOES NOT SET ──────────────────────────────────────────
   * `org` and `created_by` are server-derived; `case_count` is an aggregate
   * over the Case M2M and belongs to the database. None of the three appear
   * here, and the API rejects all three from the request body.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import { SOLUTION_STATUS, SOLUTION_STATUS_LABEL } from '$lib/v2/enums.js';
  import { enhance } from '$app/forms';
  import { untrack } from 'svelte';
  import { ChevronLeft, Eye, EyeOff } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  // `untrack` so a revalidation cannot overwrite what somebody has typed.
  // These are read once, on purpose. `update({ reset: false })` below is what
  // keeps a rejected save's words in the boxes.
  let title = $state(untrack(() => form?.values?.title ?? ''));
  let description = $state(untrack(() => form?.values?.description ?? ''));
  let status = $state(untrack(() => form?.values?.status ?? 'draft'));
  let isPublished = $state(untrack(() => Boolean(form?.values?.is_published)));
  let saving = $state(false);

  /**
   * Statuses this writer may actually set. `approved` is an admin act. See
   * `cases/kb_access.py`, so for everybody else it is not in the list rather
   * than in the list and rejected.
   */
  let statuses = $derived(
    data.canRelease ? SOLUTION_STATUS : SOLUTION_STATUS.filter((s) => s !== 'approved')
  );

  let ready = $derived(title.trim().length > 3 && description.trim().length > 20);

  /**
   * The combination, in words. Three reachable states, and each one means
   * something different to a customer, which is why the two flags cannot be
   * collapsed into a single "publish" toggle.
   */
  let consequence = $derived.by(() => {
    if (isPublished && status === 'approved')
      return { tone: 'moss', text: 'Los clientes pueden leer esto, y alguien ya lo revisó.' };
    if (isPublished)
      return {
        tone: 'clay',
        text: 'Esto se va a rechazar: un artículo tiene que estar aprobado antes de poder publicarse. Poné el estado en Aprobado, o dejalo interno por ahora.'
      };
    if (status === 'approved')
      return {
        tone: 'clay',
        text: 'Revisado, pero nadie fuera del equipo puede verlo. No va a llegar a la base de conocimiento del cliente hasta que se publique.'
      };
    return {
      tone: 'slate',
      text: 'Solo interno. Los agentes pueden adjuntarlo a tickets; los clientes no pueden encontrarlo.'
    };
  });
</script>

<PageHeader title="Nuevo artículo" center width="760px">
  {#snippet crumb()}
    <a href="/solutions"><ChevronLeft size={13} />Base de conocimiento</a>
  {/snippet}
  {#snippet sub()}
    Escribí la respuesta una sola vez, adjuntala a cada ticket que la pida
  {/snippet}
  {#snippet actions()}
    <a class="v2-btn" href="/solutions">Cancelar</a>
    <button
      class="v2-btn v2-btn-primary"
      type="submit"
      form="article-form"
      disabled={!ready || saving}
    >
      {saving ? 'Guardando…' : 'Guardar artículo'}
    </button>
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <form
    id="article-form"
    method="POST"
    action="?/create"
    use:enhance={() => {
      saving = true;
      return async ({ update }) => {
        saving = false;
        // `reset: false` so a rejected save comes back with the words still
        // in the textarea. Retyping an article because the title was three
        // characters long is not a thing to ask of anybody.
        await update({ reset: false });
      };
    }}
  >
    <div
      class="v2-pad"
      style="padding-top:18px;padding-bottom:32px;max-width:760px;margin-left:auto;margin-right:auto"
    >
      {#if form?.error}
        <p style="color:var(--v2-rust);font-size:12.5px;margin:0 0 14px">{form.error}</p>
      {/if}

      <div class="v2-card" style="padding:18px 20px">
        <label class="f">
          <span>Título</span>
          <input
            name="title"
            bind:value={title}
            placeholder="Solucionar un loop de inicio de sesión SSO tras un cambio del proveedor de identidad"
          />
          <!-- The title is what an agent scans in a list of forty under time
               pressure, so the guidance is about scanning, not SEO. -->
          <em>Contá el síntoma como lo reportaría un cliente, no la solución.</em>
        </label>

        <label class="f" style="margin-top:18px">
          <span>Respuesta</span>
          <textarea
            name="description"
            rows="9"
            bind:value={description}
            placeholder="Qué está pasando, por qué, y los pasos que lo resuelven."></textarea>
          <em>
            {#if description.trim().length && description.trim().length <= 20}
              Unas palabras más: este es el texto que un agente le va a pegar a un cliente.
            {:else}
              Esto se pega en las respuestas tal cual, así que escribilo para que lo lea la persona
              con el problema.
            {/if}
          </em>
        </label>
      </div>

      <div class="v2-card" style="padding:18px 20px;margin-top:14px">
        <div class="v2-label" style="margin-bottom:4px">Revisión y visibilidad</div>
        <p class="lead">
          Son dos datos separados sobre el artículo y este formulario los mantiene separados.
        </p>

        <div class="switches">
          <label class="f" style="max-width:220px">
            <span>Estado de revisión</span>
            <select name="status" bind:value={status}>
              {#each statuses as s (s)}
                <option value={s}>{SOLUTION_STATUS_LABEL[s]}</option>
              {/each}
            </select>
            {#if !data.canRelease}
              <em>Aprobar es decisión de un administrador. Es lo que permite que un artículo llegue a los clientes.</em>
            {/if}
          </label>

          {#if data.canRelease}
            <div class="pub">
              <span class="pub-label">Visibilidad para el cliente</span>
              <div class="seg">
                <button type="button" class:on={!isPublished} onclick={() => (isPublished = false)}>
                  <EyeOff size={13} />Interno
                </button>
                <button type="button" class:on={isPublished} onclick={() => (isPublished = true)}>
                  <Eye size={13} />Publicado
                </button>
              </div>
              <!-- A segmented control cannot post a value on its own. The
                   checkbox is what the form actually submits. -->
              <input type="checkbox" name="is_published" checked={isPublished} hidden />
            </div>
          {/if}
        </div>

        <p class="consequence" data-tone={consequence.tone}>{consequence.text}</p>
      </div>
    </div>
  </form>
</div>

<style>
  .f {
    display: block;
  }
  .f > span {
    display: block;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--v2-slate);
    margin-bottom: 5px;
  }
  .f em {
    display: block;
    margin-top: 5px;
    font-style: normal;
    font-size: 11.5px;
    color: var(--v2-slate);
    line-height: 1.5;
  }
  input,
  select,
  textarea {
    width: 100%;
    padding: 8px 10px;
    font: inherit;
    font-size: 13.5px;
    color: var(--v2-ink);
    background: var(--v2-card);
    border: 1px solid var(--v2-line);
    border-radius: 6px;
  }
  textarea {
    resize: vertical;
    line-height: 1.6;
  }
  input:focus,
  select:focus,
  textarea:focus {
    outline: 2px solid var(--v2-ember);
    outline-offset: -1px;
  }

  .lead {
    margin: 0 0 14px;
    font-size: 12.5px;
    color: var(--v2-slate);
    line-height: 1.5;
  }
  .switches {
    display: flex;
    gap: 26px;
    flex-wrap: wrap;
    align-items: flex-start;
  }
  .pub-label {
    display: block;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--v2-slate);
    margin-bottom: 5px;
  }
  .seg {
    display: flex;
    border: 1px solid var(--v2-line);
    border-radius: 6px;
    overflow: hidden;
  }
  .seg button {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 7px 12px;
    font: inherit;
    font-size: 12.5px;
    color: var(--v2-slate);
    background: var(--v2-card);
    border: 0;
    cursor: pointer;
  }
  .seg button + button {
    border-left: 1px solid var(--v2-line);
  }
  .seg button.on {
    color: var(--v2-ink);
    background: var(--v2-hover);
    font-weight: 600;
  }

  .consequence {
    margin: 16px 0 0;
    padding-top: 13px;
    border-top: 1px solid var(--v2-line);
    font-size: 12.5px;
    line-height: 1.55;
    color: var(--v2-slate);
  }
  .consequence[data-tone='clay'] {
    color: var(--v2-clay);
  }
  .consequence[data-tone='moss'] {
    color: var(--v2-moss);
  }
</style>
