<script>
  /**
   * Raising a ticket.
   *
   * Deliberately short. A ticket that has just been raised has no history, no
   * closing date and nothing linked to it, so the only questions are what
   * happened, how bad it is, and who it is for.
   *
   * `?account=<id>` preselects the company, so "raise a ticket for this
   * account" arrives with the account already chosen.
   */
  import { tick, untrack } from 'svelte';
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import { ChevronRight, FileText, Paperclip, TriangleAlert, X } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form: result } = $props();

  // `untrack` so a re-render after a failed save does not throw away what the
  // person typed; `result.values` is the server's echo of the same fields.
  let form = $state(
    untrack(() => ({
      name: '',
      status: data.defaults.status,
      priority: data.defaults.priority,
      case_type: data.defaults.case_type,
      description: '',
      account: data.defaults.account ?? '',
      assigned_to: '',
      ...(result?.values ?? {})
    }))
  );
  /*
   * TAMBIEN EN WISPHUB (26/10/2026). Solo aparece si la empresa tiene asuntos
   * habilitados. El numero de servicio se confirma con "Verificar" -- muestra
   * el titular -- antes de abrir un ticket que le va a caer a un tecnico.
   */
  /*
   * 27/10/2026: la casilla viene MARCADA -- lo normal es que un ticket del
   * ISP viva tambien en WispHub. Y el asunto se elige SIEMPRE de la lista de
   * WispHub, con la casilla o sin ella: decision del usuario, para que Dexter
   * no tenga asuntos distintos a los del ISP. Texto libre solo si la empresa
   * no tiene asuntos habilitados (o el motor no los mando).
   */
  let enWispHub = $state(
    untrack(() => (result?.values ? result.values.en_wisphub === true : true))
  );
  /*
   * 28/10/2026: el cliente se BUSCA por número de servicio, cédula o nombre
   * -- quien atiende una llamada casi nunca tiene el número. Lo que viaja en
   * el formulario sigue siendo el número de servicio del que se eligió.
   */
  let servicio = $state(untrack(() => result?.values?.servicio ?? ''));
  let clienteNombre = $state(untrack(() => result?.values?.cliente_nombre ?? ''));
  let busqueda = $state('');
  /** @type {any} */
  let hallazgo = $state(null);
  let buscando = $state(false);
  /** @type {ReturnType<typeof setTimeout> | undefined} */
  let reintento;
  let usaWispHub = $derived((data.asuntosWispHub?.length ?? 0) > 0);
  const AREAS = /** @type {Record<string, string>} */ ({
    soporte_tecnico: 'Soporte técnico',
    cartera: 'Cartera'
  });
  //  Los frecuentes por área, y después todo el catálogo de WispHub.
  let asuntosPorGrupo = $derived.by(() => {
    /** @type {Record<string, string[]>} */
    const g = {};
    /** @type {string[]} */
    const resto = [];
    for (const a of data.asuntosWispHub ?? []) {
      if (a.frecuente === false) resto.push(a.asunto);
      else (g[a.area || ''] ??= []).push(a.asunto);
    }
    const grupos = Object.entries(g).map(
      ([area, lista]) => /** @type {[string, string[]]} */ ([AREAS[area] ?? (area || 'Otros'), lista])
    );
    if (resto.length) grupos.push(['Todos los asuntos de WispHub', resto]);
    return grupos;
  });
  //  EL ADJUNTO (28/10/2026): una zona con ícono en lugar del control nativo
  //  del navegador. El archivo sigue viajando en el mismo <input name="attachment">.
  const ADJUNTO_MAX = 25 * 1024 * 1024;
  /** @type {{nombre: string, tamano: number} | null} */
  let archivo = $state(null);
  /** @type {HTMLInputElement | null} */
  let entradaArchivo = $state(null);
  let arrastrando = $state(false);
  const peso = (/** @type {number} */ n) =>
    n < 1024 * 1024 ? `${Math.max(1, Math.round(n / 1024))} KB` : `${(n / 1024 / 1024).toFixed(1)} MB`;
  function alElegir(/** @type {Event} */ e) {
    const f = /** @type {HTMLInputElement} */ (e.currentTarget).files?.[0];
    archivo = f ? { nombre: f.name, tamano: f.size } : null;
  }
  function quitarArchivo() {
    if (entradaArchivo) entradaArchivo.value = '';
    archivo = null;
  }
  function soltar(/** @type {DragEvent} */ e) {
    e.preventDefault();
    arrastrando = false;
    const lista = e.dataTransfer?.files;
    if (!lista?.length || !entradaArchivo) return;
    entradaArchivo.files = lista;
    archivo = { nombre: lista[0].name, tamano: lista[0].size };
  }
  //  Elegir el asunto propone su prioridad (la de WispHub para ese asunto);
  //  la persona la puede cambiar, y la que quede es la que llega allá.
  function proponerPrioridad() {
    const a = (data.asuntosWispHub ?? []).find((/** @type {any} */ x) => x.asunto === form.name);
    if (a?.prioridad && data.priorities.some((/** @type {any} */ p) => p.value === a.prioridad)) {
      form.priority = a.prioridad;
    }
  }
  async function buscar(intento = 0) {
    clearTimeout(reintento);
    buscando = true;
    try {
      //  En el cuerpo, no en la URL: es la cédula o el nombre de una persona.
      const r = await fetch('/tickets/new/cliente', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ q: busqueda.trim() })
      });
      hallazgo = await r.json();
      //  La primera búsqueda por nombre arma la lista de clientes del lado del
      //  motor (cerca de un minuto): se reintenta sola, hasta dos minutos.
      if (hallazgo?.ok && hallazgo.cargando && intento < 24) {
        reintento = setTimeout(() => buscar(intento + 1), 5000);
      }
    } catch {
      hallazgo = { ok: false, motivo: 'No se pudo buscar ahora. Probá de nuevo.' };
    } finally {
      buscando = false;
    }
  }
  function elegir(/** @type {any} */ c) {
    servicio = c.servicio;
    clienteNombre = c.nombre;
    hallazgo = null;
  }
  function cambiar() {
    servicio = '';
    clienteNombre = '';
  }

  let touched = $state(/** @type {Record<string, boolean>} */ ({}));
  let submitted = $state(false);

  let errors = $derived.by(() => {
    /** @type {Record<string, string>} */
    const e = {};
    const name = form.name.trim();
    if (!name) e.name = usaWispHub ? 'Elegí el asunto de la lista.' : 'Un ticket necesita un asunto.';
    // `Case.name` is max_length=64, short for a subject line, but it is the
    // column, and a 65th character is a 400 from the serializer.
    else if (name.length > 64)
      e.name = `El asunto tiene un máximo de 64 caracteres (esto tiene ${name.length}).`;
    return e;
  });

  let valid = $derived(Object.keys(errors).length === 0);
  const show = (/** @type {string} */ field) => (touched[field] || submitted) && errors[field];

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

<PageHeader title="Nuevo ticket" center>
  {#snippet crumb()}
    <a href="/tickets">Tickets</a>
    <ChevronRight size={12} />
    <span>Nuevo</span>
  {/snippet}
  {#snippet sub()}
    Qué pasó, qué tan urgente es, y para quién es.
  {/snippet}
</PageHeader>

<div class="v2-scroll v2-pad" style="padding-top:18px">
  <form
    class="v2-form"
    method="POST"
    action="?/create"
    enctype="multipart/form-data"
    use:enhance={check}
    novalidate>
    {#if result?.error}
      <div
        class="v2-next"
        style="background:color-mix(in srgb, var(--v2-rust) 9%, transparent);border-color:color-mix(in srgb, var(--v2-rust) 28%, transparent);margin-bottom:18px"
        role="alert"
      >
        <TriangleAlert size={17} style="color:var(--v2-rust);flex:none" />
        <div class="v2-next-body">
          <div style="font-weight:600">El servidor rechazó este ticket</div>
          <div class="v2-sub" style="margin-top:2px">{result.error}</div>
        </div>
      </div>
    {/if}

    {#if data.asuntosWispHub?.length}
      <fieldset class="wisphub">
        <label class="marca">
          <input
            type="checkbox"
            name="en_wisphub"
            value="1"
            bind:checked={enWispHub} />
          Crear también en WispHub
        </label>
        {#if enWispHub}
          <div class="v2-field">
            <label for="f-cliente">Cliente</label>
            <input type="hidden" name="servicio" value={servicio} />
            <input type="hidden" name="cliente_nombre" value={clienteNombre} />
            {#if servicio}
              <div class="elegido">
                <span><b>{clienteNombre || 'Cliente'}</b> · servicio {servicio}</span>
                <button type="button" class="v2-btn v2-btn-sm" onclick={cambiar}>Cambiar</button>
              </div>
            {:else}
              <div class="servicio">
                <input
                  id="f-cliente"
                  class="v2-input"
                  autocomplete="off"
                  placeholder="Número de servicio, cédula o nombre"
                  bind:value={busqueda}
                  onkeydown={(e) => {
                    if (e.key !== 'Enter') return;
                    e.preventDefault();
                    if (busqueda.trim().length >= 3) buscar();
                  }} />
                <button
                  type="button"
                  class="v2-btn v2-btn-sm"
                  onclick={() => buscar()}
                  disabled={buscando || busqueda.trim().length < 3}>Buscar</button>
              </div>
              {#if hallazgo && !hallazgo.ok}
                <p class="v2-hint aviso">{hallazgo.motivo}</p>
              {:else if hallazgo?.cargando}
                <p class="v2-hint">
                  Cargando la lista de clientes de WispHub: la primera vez tarda cerca de un minuto.
                  La búsqueda sigue sola.
                </p>
              {:else if hallazgo && !hallazgo.resultados.length}
                <p class="v2-hint aviso">No hay ningún cliente con eso.</p>
              {:else if hallazgo}
                <ul class="hallados">
                  {#each hallazgo.resultados as c (c.servicio)}
                    <li>
                      <button type="button" onclick={() => elegir(c)}>
                        <b>{c.nombre}</b>
                        <span>Servicio {c.servicio}{c.estado ? ` · ${c.estado}` : ''}</span>
                      </button>
                    </li>
                  {/each}
                </ul>
                {#if hallazgo.mas}
                  <p class="v2-hint">Hay más: escribí el nombre más completo.</p>
                {/if}
              {/if}
            {/if}
          </div>
          <p class="v2-hint">
            Se abre en WispHub a nombre del responsable del área, con lo que escribas en «Qué
            pasó», y queda atado a este ticket: lo que respondan allá aparece acá.
          </p>
        {/if}
      </fieldset>
    {/if}

    <div class="v2-field">
      <label for="f-name">Asunto</label>
      {#if usaWispHub}
        <select
          id="f-name"
          name="name"
          class="v2-input"
          bind:value={form.name}
          onchange={proponerPrioridad}
          onblur={() => (touched.name = true)}
          aria-invalid={show('name') ? 'true' : undefined}>
          <option value="">Elegí uno</option>
          {#each asuntosPorGrupo as [grupo, lista] (grupo)}
            <optgroup label={grupo}>
              {#each lista as a (a)}
                <option value={a}>{a}</option>
              {/each}
            </optgroup>
          {/each}
        </select>
      {:else}
        <input
          id="f-name"
          name="name"
          class="v2-input"
          bind:value={form.name}
          onblur={() => (touched.name = true)}
          aria-invalid={show('name') ? 'true' : undefined}
        />
      {/if}
      {#if show('name')}
        <p class="v2-error">{errors.name}</p>
      {:else if usaWispHub}
        <p class="v2-hint">Los mismos asuntos de WispHub, aunque el ticket quede solo en Dexter.</p>
      {/if}
    </div>

    <!--
      28/10/2026: sin selector de estado. Un ticket nace «Nuevo», aca y en
      WispHub (que lo crea siempre en 1): ofrecer otro estado al crearlo era
      ofrecer algo que WispHub no iba a reflejar. Se cambia despues, desde el
      ticket.
    -->
    <input type="hidden" name="status" value={form.status} />
    <div class="pair">
      <div class="v2-field">
        <label for="f-priority">Prioridad</label>
        <select id="f-priority" name="priority" class="v2-input" bind:value={form.priority}>
          {#each data.priorities as p (p.value)}
            <option value={p.value}>{p.label}</option>
          {/each}
        </select>
        <p class="v2-hint">
          {enWispHub && usaWispHub
            ? 'La misma llega a WispHub. Define el objetivo de primera respuesta.'
            : 'Define el objetivo de primera respuesta.'}
        </p>
      </div>
      <div class="v2-field">
        <label for="f-type">Tipo</label>
        <select id="f-type" name="case_type" class="v2-input" bind:value={form.case_type}>
          <option value="">Sin definir</option>
          {#each data.caseTypes as t (t.value)}
            <option value={t.value}>{t.label}</option>
          {/each}
        </select>
      </div>
    </div>
    <p class="v2-hint nace">
      El ticket nace como «Nuevo», igual que en WispHub. El estado se cambia después, desde el ticket.
    </p>

    <div class="pair">
      <!-- Igual que «Personas afectadas»: sin cuentas en el CRM solo ofrecía «Sin vincular». -->
      {#if data.accounts?.length}
        <div class="v2-field">
          <label for="f-account">Cuenta</label>
          <select id="f-account" name="account" class="v2-input" bind:value={form.account}>
            <option value="">Sin vincular</option>
            {#each data.accounts as a (a.id)}
              <option value={a.id}>{a.name}</option>
            {/each}
          </select>
          <p class="v2-hint">No se puede cambiar después. La API lo deja de solo lectura tras la creación.</p>
        </div>
      {/if}
      <div class="v2-field">
        <label for="f-owner">Asignado a</label>
        <select id="f-owner" name="assigned_to" class="v2-input" bind:value={form.assigned_to}>
          <option value="">Nadie</option>
          {#each data.owners as o (o.id)}
            <option value={o.id}>{o.name}</option>
          {/each}
        </select>
        <p class="v2-hint">Los tickets sin asignar igual cuentan contra el reloj.</p>
      </div>
    </div>

    <!--
      28/10/2026: solo si el CRM tiene contactos. Son los contactos del CRM
      (no los clientes de WispHub, que se eligen arriba), y en una empresa que
      no los carga la lista salia vacia: un campo que no se podia usar.
    -->
    {#if data.contacts?.length}
      <div class="v2-field">
        <label for="f-contacts">Personas afectadas</label>
        <select id="f-contacts" name="contacts" class="v2-input" multiple size="4">
          {#each data.contacts as c (c.id)}
            <option value={c.id}>{c.name}</option>
          {/each}
        </select>
        <p class="v2-hint">Opcional. Mantené presionado ctrl o cmd para elegir más de uno.</p>
      </div>
    {/if}

    <div class="v2-field">
      <label for="f-desc">Qué pasó</label>
      <textarea
        id="f-desc"
        name="description"
        class="v2-input"
        rows="4"
        bind:value={form.description}></textarea>
    </div>

    <div class="v2-field">
      <label for="f-adjunto">Adjuntar documento</label>
      <!-- El control nativo queda oculto a la vista, no al teclado: se enfoca con Tab y la zona lo muestra. -->
      <input
        id="f-adjunto"
        bind:this={entradaArchivo}
        name="attachment"
        type="file"
        class="oculto"
        onchange={alElegir} />
      {#if archivo}
        <div class="adjunto-elegido" class:excede={archivo.tamano > ADJUNTO_MAX}>
          <FileText size={18} style="flex:none" />
          <div class="adjunto-datos">
            <b>{archivo.nombre}</b>
            <span>
              {peso(archivo.tamano)}{archivo.tamano > ADJUNTO_MAX ? ' · pasa de 25 MB, no se va a poder subir' : ''}
            </span>
          </div>
          <button type="button" class="v2-btn v2-btn-sm" onclick={quitarArchivo} aria-label="Quitar el archivo">
            <X size={14} />
          </button>
        </div>
      {:else}
        <label
          for="f-adjunto"
          class="soltar"
          class:arrastrando
          ondragover={(e) => {
            e.preventDefault();
            arrastrando = true;
          }}
          ondragleave={() => (arrastrando = false)}
          ondrop={soltar}>
          <Paperclip size={18} style="flex:none" />
          <span><b>Elegí un archivo</b> o arrastralo acá</span>
        </label>
      {/if}
      <p class="v2-hint">
        Opcional, hasta 25 MB. Queda en el ticket{enWispHub && usaWispHub ? ' y también va a WispHub' : ''}.
      </p>
    </div>

    <div class="actions">
      <button class="v2-btn v2-btn-primary" type="submit">Crear ticket</button>
      <a class="v2-btn" href="/tickets">Cancelar</a>
    </div>
  </form>
</div>

<style>
  .wisphub {
    margin: 0 0 18px;
    padding: 14px 16px;
    border: 1px solid var(--v2-line);
    border-radius: var(--v2-radius-control);
    background: var(--v2-paper);
    display: grid;
    gap: 12px;
  }
  .marca {
    display: flex;
    align-items: center;
    gap: 8px;
    font-weight: 600;
    font-size: 14px;
  }
  .servicio {
    display: flex;
    gap: 8px;
    max-width: 380px;
  }
  .servicio .v2-input {
    flex: 1;
    min-width: 0;
  }
  .aviso {
    color: var(--v2-clay);
  }
  .elegido {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 14px;
  }
  .hallados {
    list-style: none;
    margin: 6px 0 0;
    padding: 0;
    max-width: 480px;
    border: 1px solid var(--v2-line);
    border-radius: var(--v2-radius-control);
    overflow: hidden;
  }
  .hallados li + li {
    border-top: 1px solid var(--v2-line);
  }
  .hallados button {
    display: flex;
    flex-direction: column;
    gap: 2px;
    width: 100%;
    padding: 8px 12px;
    border: 0;
    background: transparent;
    text-align: left;
    font: inherit;
    font-size: 14px;
    cursor: pointer;
  }
  .hallados button:hover,
  .hallados button:focus-visible {
    background: color-mix(in srgb, var(--v2-ink, currentColor) 6%, transparent);
  }
  .hallados span {
    font-size: 12.5px;
    opacity: 0.75;
  }
  .pair {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
  }
  .nace {
    margin: -4px 0 14px;
  }
  .oculto {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    padding: 0;
    overflow: hidden;
    clip: rect(0 0 0 0);
    border: 0;
  }
  .soltar {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    min-height: 64px;
    padding: 14px 16px;
    border: 1.5px dashed color-mix(in srgb, var(--v2-slate) 45%, transparent);
    border-radius: var(--v2-radius-control);
    background: var(--v2-paper);
    color: var(--v2-slate);
    font-size: 14px;
    font-weight: 400;
    cursor: pointer;
    transition:
      border-color 0.15s,
      background 0.15s;
  }
  .soltar b {
    color: var(--v2-ember-text);
    font-weight: 600;
  }
  .soltar:hover,
  .soltar.arrastrando {
    border-color: var(--v2-ember-line);
    background: var(--v2-ember-soft);
  }
  .oculto:focus-visible + .soltar {
    outline: 2px solid var(--v2-ember);
    outline-offset: 2px;
  }
  .adjunto-elegido {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border: 1px solid var(--v2-line);
    border-radius: var(--v2-radius-control);
    background: var(--v2-card);
  }
  .adjunto-elegido.excede {
    border-color: var(--v2-rust);
  }
  .adjunto-datos {
    display: flex;
    flex-direction: column;
    min-width: 0;
    flex: 1;
    font-size: 14px;
  }
  .adjunto-datos b {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .adjunto-datos span {
    font-size: 12.5px;
    color: var(--v2-slate);
  }
  .excede .adjunto-datos span {
    color: var(--v2-rust);
  }
  .actions {
    display: flex;
    align-items: center;
    gap: 9px;
    margin-top: 22px;
    padding-bottom: 40px;
  }
  @media (max-width: 720px) {
    .pair {
      grid-template-columns: 1fr;
    }
  }
</style>
