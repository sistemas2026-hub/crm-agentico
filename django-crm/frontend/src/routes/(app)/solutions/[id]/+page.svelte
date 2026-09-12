<script>
  /**
   * An article, and where it is in the workflow.
   *
   * Two changes from the mock, both because the real model says so:
   *
   * 1. The crumb printed `solution.id`. That is a UUID, 36 characters of
   *    nothing, in the position where a reader looks for what they are
   *    reading. The status goes there instead.
   * 2. "Related articles" is gone. The mock listed three under that heading
   *    with no stated relation, and nothing in the schema computes one. What
   *    the database does hold is the **tickets this article is filed
   *    against**, which is the same rail pointing the other way: the ticket
   *    page already links here.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import NextAction from '$lib/v2/components/NextAction.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import { relativeDays, longDate } from '$lib/v2/format.js';
  import {
    SOLUTION_STATUS_LABEL,
    SOLUTION_STATUS_TONE,
    PRIORITY_TONE,
    CASE_PRIORITY_LABEL,
    CASE_STATUS_TONE,
    CASE_STATUS_LABEL
  } from '$lib/v2/enums.js';
  import { enhance } from '$app/forms';
  import { ChevronRight, Eye, EyeOff } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let { article, tickets, hidden_ticket_count, canRelease } = $derived(data);

  /**
   * What is standing between this article and a customer, said as the next
   * single step rather than as a description of the state.
   *
   * The action is dropped for anyone who cannot take it. The API answers 403
   *, but the sentence stays, because "an admin has to approve this" is the
   * useful half and the half a writer needs to know.
   */
  let gate = $derived.by(() => {
    if (article.is_published) return null;
    if (article.status === 'approved') {
      return {
        // Without the button, "publishing is the last step" leaves a reader
        // hunting for a control that is not theirs. Naming who does it is the
        // whole value of the sentence for everybody else.
        text: canRelease
          ? 'Aprobado, pero los clientes todavía no pueden verlo. Publicarlo es el último paso.'
          : 'Aprobado, pero los clientes todavía no pueden verlo. Un administrador tiene que publicarlo.',
        action: canRelease ? 'Publicar' : null,
        form: 'setPublished',
        value: 'true'
      };
    }
    if (article.status === 'reviewed') {
      return {
        text: canRelease
          ? 'Alguien ya lo revisó. Aprobarlo es lo que permite que se publique.'
          : 'Esperando a que un administrador lo apruebe. Hasta entonces se mantiene interno.',
        action: canRelease ? 'Aprobar' : null,
        form: 'setStatus',
        value: 'approved'
      };
    }
    return {
      text: 'Esto es un borrador. Envialo a revisión cuando la respuesta esté lista: alguien más que vos tiene que aprobarlo antes de que los clientes lo vean.',
      action: 'Enviar a revisión',
      form: 'setStatus',
      value: 'reviewed'
    };
  });
</script>

<PageHeader title={article.title} record>
  {#snippet crumb()}
    <a href="/solutions">Base de conocimiento</a>
    <ChevronRight size={12} />
    <span>{SOLUTION_STATUS_LABEL[article.status]}</span>
  {/snippet}
  {#snippet sub()}
    {[
      article.author || 'Autor desconocido',
      `editado ${relativeDays(article.updated_at)}`,
      article.use_count
        ? `usado en ${article.use_count} ticket${article.use_count === 1 ? '' : 's'}`
        : 'todavía no vinculado a un ticket'
    ].join(' · ')}
  {/snippet}
  {#snippet actions()}
    <a class="v2-btn" href="/solutions/{article.id}/edit">Editar</a>
    {#if article.is_published && canRelease}
      <form method="POST" action="?/setPublished" use:enhance>
        <input type="hidden" name="published" value="false" />
        <button class="v2-btn" type="submit">Despublicar</button>
      </form>
    {/if}
  {/snippet}
</PageHeader>

<div style="display:flex;flex:1;min-height:0;overflow:hidden">
  <div class="v2-main">
    <div class="v2-scroll">
      <div class="v2-pad" style="padding-top:16px;padding-bottom:32px">
        {#if form?.error}
          <p style="color:var(--v2-rust);font-size:12.5px;margin:0 0 14px">{form.error}</p>
        {/if}

        {#if gate}
          <div style="margin-bottom:20px">
            {#if gate.action}
              <!-- NextAction renders a plain `<button>` with no `type` when it
                   has no `href`, so inside a form it submits. That is the
                   whole mechanism: the component did not need a new prop, and
                   the one place it was a dead button is now the one place it
                   does something. -->
              <form method="POST" action="?/{gate.form}" use:enhance>
                <input
                  type="hidden"
                  name={gate.form === 'setPublished' ? 'published' : 'status'}
                  value={gate.value}
                />
                <NextAction label="Todavía no es visible" text={gate.text} action={gate.action} />
              </form>
            {:else}
              <NextAction label="Todavía no es visible" text={gate.text} />
            {/if}
          </div>
        {/if}

        <article
          class="v2-card"
          style="padding:18px 20px;max-width:70ch;font-size:14px;line-height:1.65;white-space:pre-wrap"
        >
          {article.description}
        </article>

        <!-- The tickets this article was filed against. Real rows, and the
             other direction of the link the ticket page already draws. -->
        <div class="v2-label" style="margin:26px 0 10px">
          {tickets.length || hidden_ticket_count ? 'Usado en' : 'Todavía sin usar'}
        </div>
        {#if tickets.length}
          <div class="v2-card" style="overflow:hidden;max-width:70ch">
            {#each tickets as t (t.id)}
              <a
                href="/tickets/{t.id}"
                style="display:flex;gap:12px;align-items:center;padding:11px 15px;border-bottom:1px solid var(--v2-line-soft);color:inherit;text-decoration:none"
              >
                <span style="flex:1;font-size:13px;min-width:0">{t.name}</span>
                <Pill tone={CASE_STATUS_TONE[t.status]}>{CASE_STATUS_LABEL[t.status] ?? t.status}</Pill>
                <Pill tone={PRIORITY_TONE[t.priority]}>{CASE_PRIORITY_LABEL[t.priority] ?? t.priority}</Pill>
              </a>
            {/each}
          </div>
        {:else if !hidden_ticket_count}
          <p class="v2-sub" style="font-size:12.5px;max-width:70ch">
            Nadie adjuntó esto a un ticket. O dejaron de hacer la pregunta, o el artículo es difícil
            de encontrar mientras alguien está escribiendo una respuesta.
          </p>
        {/if}

        {#if hidden_ticket_count}
          <!-- The API filters this rail to tickets the reader may open, while
               the count stays the article's real usage. Saying so is better
               than a number that quietly means something different per
               reader. -->
          <p class="v2-sub" style="font-size:12px;margin-top:10px;max-width:70ch">
            {hidden_ticket_count}
            {hidden_ticket_count === 1 ? 'otro ticket usa' : 'otros tickets usan'} este artículo y
            {hidden_ticket_count === 1 ? 'no es tuyo' : 'no son tuyos'} para abrir.
          </p>
        {/if}
      </div>
    </div>
  </div>

  <aside class="v2-rail">
    <div class="v2-label v2-rail-head">Artículo</div>
    <dl class="v2-kv">
      <dt>Estado</dt>
      <dd>
        <Pill tone={SOLUTION_STATUS_TONE[article.status]}>
          {SOLUTION_STATUS_LABEL[article.status]}
        </Pill>
      </dd>
      <dt>Visibilidad</dt>
      <dd>
        {#if article.is_published}
          <span style="display:inline-flex;gap:5px;align-items:center">
            <Eye size={13} />Publicado
          </span>
        {:else}
          <span
            style="display:inline-flex;gap:5px;align-items:center"
            style:color={article.awaiting_release ? 'var(--v2-clay)' : 'inherit'}
          >
            <EyeOff size={13} />Solo interno
          </span>
        {/if}
      </dd>
      <dt>Autor</dt>
      <dd>{article.author || '—'}</dd>
      <dt>Usado en</dt>
      <dd class="v2-num">{article.use_count} tickets</dd>
      <dt>Escrito</dt>
      <dd>{longDate(article.created_at)}</dd>
      <dt>Editado</dt>
      <dd>{longDate(article.updated_at)}</dd>
    </dl>

    <div class="v2-label v2-rail-head">Cómo se usa esto</div>
    <div class="v2-card" style="padding:11px 12px;font-size:12px;line-height:1.55">
      Los artículos publicados se ofrecen en la pantalla del ticket mientras alguien está
      escribiendo una respuesta. Un artículo que nadie vinculó a un ticket suele ser uno que
      responde una pregunta que nadie hizo.
    </div>
  </aside>
</div>
