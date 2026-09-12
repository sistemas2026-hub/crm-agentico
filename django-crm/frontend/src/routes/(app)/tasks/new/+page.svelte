<script>
  /**
   * A new task.
   *
   * "Attached to" is one question, not four. The model allows exactly one
   * parent and now enforces it on every path, so a form with four separate
   * pickers would let somebody fill two and learn about the rule from a 400.
   * Pick the kind, then pick the record.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import { enhance } from '$app/forms';
  import { untrack } from 'svelte';
  import { ChevronRight } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  const KINDS = [
    { key: '', label: 'Nada' },
    { key: 'account', label: 'Una cuenta' },
    { key: 'opportunity', label: 'Una negociación' },
    { key: 'case', label: 'Un ticket' },
    { key: 'lead', label: 'Un prospecto' }
  ];

  let values = $derived(form?.values ?? {});
  let kind = $state(untrack(() => form?.values?.parent_kind ?? ''));
  let options = $derived(kind ? (data.parents[kind] ?? []) : []);
</script>

<PageHeader title="Nueva tarea" record center width="62ch">
  {#snippet crumb()}
    <a href="/tasks">Tareas</a>
    <ChevronRight size={12} />
    <span>Nueva</span>
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <form
    method="POST"
    action="?/create"
    use:enhance
    class="v2-pad"
    style="padding-top:18px;padding-bottom:36px;max-width:62ch;margin-left:auto;margin-right:auto"
  >
    {#if form?.error}
      <p style="color:var(--v2-rust);font-size:12.5px;margin:0 0 14px" role="alert">{form.error}</p>
    {/if}

    <label class="v2-field">
      <span class="v2-label">Tarea</span>
      <input
        class="v2-input"
        name="title"
        required
        maxlength="200"
        value={values.title ?? ''}
        placeholder="Enviar el anexo de seguridad a Northwind"
      />
    </label>

    <div style="display:flex;gap:12px;flex-wrap:wrap">
      <label class="v2-field" style="flex:1;min-width:150px">
        <span class="v2-label">Prioridad</span>
        <select class="v2-input" name="priority" value={values.priority ?? 'Medium'}>
          <option value="Low">Baja</option>
          <option value="Medium">Media</option>
          <option value="High">Alta</option>
        </select>
      </label>
      <label class="v2-field" style="flex:1;min-width:150px">
        <span class="v2-label">Estado</span>
        <select class="v2-input" name="status" value={values.status ?? 'New'}>
          <option value="New">Nueva</option>
          <option value="In Progress">En progreso</option>
          <option value="Completed">Completada</option>
        </select>
      </label>
      <label class="v2-field" style="flex:1;min-width:150px">
        <span class="v2-label">Vence</span>
        <input class="v2-input" type="date" name="due_date" value={values.due_date ?? ''} />
      </label>
    </div>
    <p class="v2-sub" style="font-size:11.5px;margin:-6px 0 16px">
      Una tarea sin fecha límite nunca se vence y nunca aparece en "vencen esta semana". Es una
      elección real, no un olvido.
    </p>

    <label class="v2-field">
      <span class="v2-label">Vinculada a</span>
      <select class="v2-input" name="parent_kind" bind:value={kind}>
        {#each KINDS as k (k.key)}
          <option value={k.key}>{k.label}</option>
        {/each}
      </select>
    </label>

    {#if kind}
      <label class="v2-field">
        <span class="v2-label">Cuál</span>
        <select class="v2-input" name="parent_{kind}" required>
          <option value="">Elegir…</option>
          {#each options as option (option.id)}
            <option value={option.id} selected={values[kind] === option.id}>{option.name}</option>
          {/each}
        </select>
        {#if options.length === 0}
          <span class="v2-sub" style="font-size:11.5px"
            >Nada para elegir. O no hay ninguno, o esa lista no cargó.</span
          >
        {/if}
      </label>
    {/if}

    <label class="v2-field">
      <span class="v2-label">Asignar a</span>
      <select
        class="v2-input"
        name="assigned_to"
        multiple
        size={Math.min(data.owners.length || 1, 5)}
      >
        {#each data.owners as person (person.id)}
          <option value={person.id}>{person.name}</option>
        {/each}
      </select>
      <span class="v2-sub" style="font-size:11.5px">
        Opcional, y se permite más de uno. Dejalo vacío y la tarea queda libre para que alguien la
        tome.
      </span>
    </label>

    <label class="v2-field">
      <span class="v2-label">Nota</span>
      <textarea
        class="v2-input"
        name="description"
        rows="4"
        placeholder="Contexto que necesitaría cualquiera que la tome."
        >{values.description ?? ''}</textarea
      >
    </label>

    <div style="display:flex;gap:9px;margin-top:6px">
      <button class="v2-btn v2-btn-primary" type="submit">Crear tarea</button>
      <a class="v2-btn" href="/tasks">Cancelar</a>
    </div>
  </form>
</div>
