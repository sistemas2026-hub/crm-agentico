<script>
  import { invalidateAll } from '$app/navigation';
  import { toast } from 'svelte-sonner';
  import { Loader2, Search, ChevronLeft, ChevronRight, AlertTriangle } from '@lucide/svelte';
  import { Button } from '$lib/components/ui/button/index.js';
  import * as Dialog from '$lib/components/ui/dialog/index.js';
  import {
    agrupar,
    avisosDelAgente,
    resumenDe,
    sugerirIdentificador,
    PLANTILLA_INSTRUCCIONES
  } from '$lib/agentes/formulario.js';

  /**
   * Crear o editar un agente, en cuatro pasos (02/11/2026).
   *
   * El usuario: "que la persona que cree un agente se le haga facil... la
   * grilla de herramientas, el prompt, mas entendible". Antes era una sola
   * pantalla con las 84 herramientas en lista, cada una con su instruccion
   * entera para el modelo, y faltaban dos cosas sin las que un agente de
   * clientes no sirve: que temas atiende y conectarlo al router (vivian en
   * /agentes/flujo). Ahora:
   *
   *   1. Quien es       a quien atiende, como se llama
   *   2. Que hace       instrucciones con guia, temas, router, verificacion
   *   3. Que puede usar herramientas por lo que hacen, con buscador
   *   4. Revisar        resumen y avisos ANTES de guardar
   *
   * La logica vive en $lib/agentes/formulario.js (probada aparte). En
   * 'editar', el identificador queda de solo lectura: renombrar un rol toca
   * referencias que esta pantalla no ve (para renombrar: borrar y crear).
   *
   * Los datos que ve de cada herramienta arrancan TODOS destildados salvo los
   * ya guardados -- fail-closed: se eligen a proposito.
   *
   * @type {{
   *   open: boolean,
   *   onOpenChange?: (v: boolean) => void,
   *   modo: 'crear' | 'editar',
   *   agente?: any,
   *   catalogo: any[],
   *   autonomia?: any,
   *   motivos?: Array<{ clave: string, rotulo: string }>,
   *   onSaved?: () => void | Promise<void>
   * }}
   */
  let { open = $bindable(false), onOpenChange, modo, agente, catalogo, autonomia = null,
        motivos = [], onSaved } = $props();

  const PASOS = ['Quién es', 'Qué hace', 'Qué puede usar', 'Revisar'];
  let paso = $state(0);

  let nombre = $state('');
  let nombreTocado = $state(false);
  let area = $state('');
  let cargo = $state('');
  let descripcion = $state('');
  let orientadoA = $state('colaborador');
  let atiende = $state('');
  let conectar = $state(false);
  let exigeVerificacion = $state(true);
  let nuncaRevelar = $state('');
  /** Los motivos por los que pasa a una persona. Ninguno = todos los de la empresa. */
  /** @type {Set<string>} */
  let motivosElegidos = $state(new Set());
  let busqueda = $state('');
  /** @type {Record<string, boolean>} */
  let seleccion = $state({});
  /** @type {Record<string, Set<string>>} */
  let camposElegidos = $state({});
  /** @type {Record<string, string>} */
  let campoNuevo = $state({});
  let submitting = $state(false);

  $effect(() => {
    if (!open) return;
    const esEditar = modo === 'editar' && agente;
    paso = 0;
    busqueda = '';
    nombre = esEditar ? agente.nombre : '';
    nombreTocado = !!esEditar;
    area = esEditar ? agente.area || '' : '';
    cargo = esEditar ? agente.cargo || '' : '';
    descripcion = esEditar ? agente.descripcion || '' : '';
    orientadoA = esEditar ? agente.orientado_a : 'colaborador';
    atiende = esEditar ? agente.atiende || '' : '';
    conectar = esEditar ? !!agente.en_el_router : true;
    exigeVerificacion = esEditar ? agente.exige_verificacion !== false : true;
    nuncaRevelar = esEditar ? (agente.nunca_revelar || []).join('\n') : '';
    motivosElegidos = new Set(esEditar ? agente.motivos_escalada || [] : []);
    /** @type {Record<string, boolean>} */
    const nuevaSeleccion = {};
    /** @type {Record<string, Set<string>>} */
    const nuevosCampos = {};
    for (const h of esEditar ? agente.herramientas : []) {
      nuevaSeleccion[h.nombre] = true;
      nuevosCampos[h.nombre] = new Set(h.campos_permitidos || []);
    }
    seleccion = nuevaSeleccion;
    camposElegidos = nuevosCampos;
    campoNuevo = {};
  });

  //  El identificador se sugiere del cargo mientras nadie lo escriba a mano.
  $effect(() => {
    if (modo === 'crear' && !nombreTocado) nombre = sugerirIdentificador(cargo || area);
  });

  const deCliente = $derived(orientadoA === 'cliente_final');
  const derivacion = $derived((catalogo ?? []).find((/** @type {any} */ h) => h.deriva));
  //  Un agente de clientes SIEMPRE tiene la de derivar (el motor se la agrega:
  //  nucleo/config/editor.py::_con_derivacion_si_atiende_clientes).
  $effect(() => {
    if (deCliente && derivacion && !seleccion[derivacion.nombre]) {
      seleccion = { ...seleccion, [derivacion.nombre]: true };
    }
  });

  const grupos = $derived(agrupar(catalogo, busqueda));
  const elegidas = $derived((catalogo ?? []).filter((/** @type {any} */ h) => seleccion[h.nombre]));
  /** @type {Record<string, any>} */
  const autonomiaDe = $derived(
    Object.fromEntries((autonomia?.acciones ?? []).map((/** @type {any} */ a) => [a.accion, a]))
  );
  // Las que el agente YA tenia atendiendo clientes sin verificar: el motor
  // las respeta (editor.py::_comprobar_sin_verificar), y el aviso tambien.
  const previasSinVerificar = $derived(
    modo === 'editar' && agente?.orientado_a === 'cliente_final' && agente?.exige_verificacion === false
      ? new Set((agente.herramientas ?? []).map((/** @type {any} */ h) => h.nombre))
      : new Set()
  );
  const avisos = $derived(
    avisosDelAgente({ orientadoA, descripcion, atiende, conectar, seleccion,
                      campos: camposElegidos, catalogo, exigeVerificacion, previasSinVerificar })
  );
  const bloqueado = $derived(avisos.some((a) => a.bloquea));

  const nombreValido = $derived(/^[a-z][a-z0-9_]{1,29}$/.test(nombre));
  const puedeGuardar = $derived(nombreValido && descripcion.trim().length > 0 && !submitting && !bloqueado);

  function toggleHerramienta(/** @type {string} */ n) {
    if (deCliente && derivacion?.nombre === n) return;
    seleccion = { ...seleccion, [n]: !seleccion[n] };
    if (seleccion[n] && !camposElegidos[n]) camposElegidos = { ...camposElegidos, [n]: new Set() };
  }

  function toggleCampo(/** @type {string} */ n, /** @type {string} */ campo) {
    const actuales = new Set(camposElegidos[n] || []);
    if (actuales.has(campo)) actuales.delete(campo);
    else actuales.add(campo);
    camposElegidos = { ...camposElegidos, [n]: actuales };
  }

  function todosLosCampos(/** @type {any} */ h, /** @type {boolean} */ todos) {
    camposElegidos = { ...camposElegidos, [h.nombre]: new Set(todos ? h.campos_conocidos : []) };
  }

  function agregarCampoLibre(/** @type {string} */ n) {
    const valor = (campoNuevo[n] || '').trim();
    if (!valor) return;
    const actuales = new Set(camposElegidos[n] || []);
    actuales.add(valor);
    camposElegidos = { ...camposElegidos, [n]: actuales };
    campoNuevo = { ...campoNuevo, [n]: '' };
  }

  function usarGuia() {
    if (descripcion.trim() && !confirm('Ya hay texto. ¿Lo reemplazo por la guía?')) return;
    descripcion = PLANTILLA_INSTRUCCIONES;
  }

  async function guardar() {
    if (!puedeGuardar) return;
    submitting = true;
    try {
      const herramientas = Object.keys(seleccion)
        .filter((n) => seleccion[n])
        .map((n) => ({ nombre: n, campos_permitidos: Array.from(camposElegidos[n] || []) }));
      const cuerpo = {
        nombre,
        area: area.trim() || null,
        cargo: cargo.trim() || null,
        descripcion: descripcion.trim(),
        orientado_a: orientadoA,
        herramientas,
        nunca_revelar: nuncaRevelar.split('\n').map((t) => t.trim()).filter(Boolean),
        //  En el orden de la empresa. Vacio = puede pasar por cualquiera.
        motivos_escalada: motivos.map((m) => m.clave).filter((c) => motivosElegidos.has(c)),
        //  Solo tienen sentido en un agente de clientes; para uno interno no
        //  viajan y el motor deja lo que habia.
        ...(deCliente
          ? { atiende: atiende.trim(), conectar_al_router: conectar, exige_verificacion: exigeVerificacion }
          : {})
      };
      const url = modo === 'crear' ? '/api/agentes' : `/api/agentes/${encodeURIComponent(nombre)}`;
      const res = await fetch(url, {
        method: modo === 'crear' ? 'POST' : 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(cuerpo)
      });
      if (!res.ok) {
        const e = await res.json().catch(() => ({}));
        toast.error(e?.error || 'No se pudo guardar el agente');
        return;
      }
      toast.success(modo === 'crear' ? 'Agente creado.' : 'Agente actualizado.');
      open = false;
      await onSaved?.();
      await invalidateAll();
    } finally {
      submitting = false;
    }
  }

  const campo = 'w-full rounded-md border border-[var(--border-default)] bg-[var(--surface-default)] p-2 text-sm';
</script>

<Dialog.Root bind:open onOpenChange={(v) => onOpenChange?.(v)}>
  <Dialog.Content class="sm:max-w-4xl">
    <Dialog.Header>
      <Dialog.Title>{modo === 'crear' ? 'Nuevo agente' : `Editar ${agente?.nombre ?? ''}`}</Dialog.Title>
      <Dialog.Description>
        Un agente es un rol: a quién atiende, qué hace, qué herramientas usa y qué datos ve. Para
        conectar una API nueva está <a href="/configuracion-guiada" class="underline">Configuración guiada</a>.
      </Dialog.Description>
    </Dialog.Header>

    <!-- Los pasos, clickeables: en editar se salta directo al que importa. -->
    <ol class="flex flex-wrap gap-2 text-xs">
      {#each PASOS as titulo, i (titulo)}
        <li>
          <button
            type="button"
            class="rounded-full border px-3 py-1 {i === paso
              ? 'border-[var(--v2-ember)] text-[var(--v2-ember)] font-semibold'
              : 'border-[var(--border-default)] text-[var(--text-secondary)]'}"
            onclick={() => (paso = i)}
          >
            {i + 1}. {titulo}
          </button>
        </li>
      {/each}
    </ol>

    <div class="max-h-[60vh] min-h-[22rem] overflow-y-auto pr-1">
      {#if paso === 0}
        <div class="space-y-4">
          <fieldset class="space-y-2">
            <legend class="text-sm font-medium">¿A quién atiende?</legend>
            <div class="grid gap-2 sm:grid-cols-2">
              {#each [
                { v: 'cliente_final', t: 'A los clientes', d: 'Por WhatsApp. El router le pasa las conversaciones de los temas que atiende.' },
                { v: 'colaborador', t: 'Al equipo', d: 'Uso interno: compañeros que le preguntan desde Dexter.' }
              ] as op (op.v)}
                <label
                  class="flex cursor-pointer gap-2 rounded-md border p-3 text-sm {orientadoA === op.v
                    ? 'border-[var(--v2-ember)]'
                    : 'border-[var(--border-default)]'}"
                >
                  <input type="radio" name="orientado" value={op.v} bind:group={orientadoA} class="mt-1" />
                  <span><span class="font-medium">{op.t}</span><br /><span class="text-xs text-[var(--text-secondary)]">{op.d}</span></span>
                </label>
              {/each}
            </div>
          </fieldset>
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="space-y-1 text-sm">
              <span class="font-medium">Cargo</span>
              <input type="text" bind:value={cargo} placeholder="ej. Agente de Facturación" class={campo} />
            </label>
            <label class="space-y-1 text-sm">
              <span class="font-medium">Área</span>
              <input type="text" bind:value={area} placeholder="ej. Atención al Cliente" class={campo} />
            </label>
          </div>
          <label class="block space-y-1 text-sm">
            <span class="font-medium">Identificador <span class="text-destructive">*</span></span>
            <input
              type="text"
              bind:value={nombre}
              oninput={() => (nombreTocado = true)}
              disabled={modo === 'editar'}
              placeholder="se arma solo con el cargo"
              class="{campo} font-mono disabled:opacity-60"
            />
            <span class="text-xs text-[var(--text-secondary)]">
              {#if nombre && !nombreValido}
                <span class="text-destructive">Minúsculas, empieza con letra, solo letras, números y _ (2 a 30).</span>
              {:else}
                Es el nombre interno del agente. Se sugiere solo; no se puede cambiar después.
              {/if}
            </span>
          </label>
        </div>
      {:else if paso === 1}
        <div class="space-y-4">
          <label class="block space-y-1 text-sm">
            <span class="flex items-center justify-between">
              <span class="font-medium">Instrucciones <span class="text-destructive">*</span></span>
              <button type="button" class="text-xs underline" onclick={usarGuia}>Usar la guía</button>
            </span>
            <span class="block text-xs text-[var(--text-secondary)]">
              Se le entregan al modelo en cada conversación, tal cual. Lo que más importa es lo que
              <em>no</em> debe hacer.
            </span>
            <textarea
              bind:value={descripcion}
              placeholder={PLANTILLA_INSTRUCCIONES}
              class="{campo} min-h-[14rem] resize-y p-3 text-[13px] leading-[1.6]"
            ></textarea>
            <span class="text-xs text-[var(--text-secondary)]">{descripcion.length} caracteres</span>
          </label>

          {#if deCliente}
            <div class="space-y-2 rounded-md border border-[var(--border-default)] p-3">
              <label class="flex items-start gap-2 text-sm">
                <input type="checkbox" bind:checked={conectar} class="mt-1" />
                <span><span class="font-medium">Que el router le pase conversaciones</span><br />
                  <span class="text-xs text-[var(--text-secondary)]">Sin esto, el agente existe pero nunca le llega nada.</span></span>
              </label>
              <label class="block space-y-1 text-sm">
                <span class="font-medium">Qué temas atiende</span>
                <span class="block text-xs text-[var(--text-secondary)]">
                  En palabras del cliente. Con esto el router decide cuándo mandarle una conversación.
                </span>
                <textarea bind:value={atiende} maxlength="400" placeholder="ej. saldo, facturas, fechas de corte, pagos" class="{campo} min-h-[4rem]"></textarea>
              </label>
              <label class="flex items-start gap-2 text-sm">
                <input type="checkbox" bind:checked={exigeVerificacion} class="mt-1" />
                <span><span class="font-medium">Verifica la identidad antes de mostrar datos</span><br />
                  <span class="text-xs text-[var(--text-secondary)]">Desmarcalo solo si atiende a quien todavía no es cliente (por ejemplo, ventas).</span></span>
              </label>
            </div>
          {/if}

          {#if motivos.length}
            <fieldset class="space-y-1.5 rounded-md border border-[var(--border-default)] p-3 text-sm">
              <legend class="px-1 font-medium">Cuándo pasa a una persona</legend>
              <p class="text-xs text-[var(--text-secondary)]">
                {motivosElegidos.size
                  ? `Solo por estos ${motivosElegidos.size} motivos.`
                  : 'Sin ninguno marcado puede pasar por cualquiera de los motivos de la empresa.'}
              </p>
              <div class="grid gap-x-4 gap-y-1 sm:grid-cols-2">
                {#each motivos as m (m.clave)}
                  <label class="flex items-center gap-2 text-xs">
                    <input type="checkbox" checked={motivosElegidos.has(m.clave)}
                           onchange={() => {
                             const s = new Set(motivosElegidos);
                             if (s.has(m.clave)) s.delete(m.clave); else s.add(m.clave);
                             motivosElegidos = s;
                           }} />
                    {m.rotulo}
                  </label>
                {/each}
              </div>
            </fieldset>
          {/if}

          <label class="block space-y-1 text-sm">
            <span class="font-medium">Lo que nunca debe revelar</span>
            <span class="block text-xs text-[var(--text-secondary)]">Uno por línea. Opcional.</span>
            <textarea bind:value={nuncaRevelar} placeholder="ej. el costo interno de un plan" class="{campo} min-h-[4rem]"></textarea>
          </label>
        </div>
      {:else if paso === 2}
        <div class="space-y-3">
          <label class="flex items-center gap-2 rounded-md border border-[var(--border-default)] px-2">
            <Search size={14} class="text-[var(--text-secondary)]" />
            <input type="search" bind:value={busqueda} placeholder="Buscar una herramienta (saldo, ticket, reinicio…)"
                   class="w-full bg-transparent py-2 text-sm outline-none" />
          </label>
          <p class="text-xs text-[var(--text-secondary)]">{elegidas.length} elegidas</p>

          {#each grupos as g (g.clave)}
            <section class="space-y-1.5">
              <h3 class="text-sm font-semibold">
                {g.titulo} <span class="font-normal text-[var(--text-secondary)]">· {g.ayuda}</span>
              </h3>
              {#each g.items as h (h.nombre)}
                {@const bloqueada = deCliente && derivacion?.nombre === h.nombre}
                <div class="rounded-md border border-[var(--border-default)] p-2 {seleccion[h.nombre] ? 'bg-[var(--surface-subtle,transparent)]' : ''}">
                  <label class="flex items-start gap-2 text-sm">
                    <input type="checkbox" checked={!!seleccion[h.nombre]} disabled={bloqueada}
                           onchange={() => toggleHerramienta(h.nombre)} class="mt-1" />
                    <span class="min-w-0 flex-1">
                      <span class="font-mono text-[13px]">{h.nombre}</span>
                      {#if h.escribe && !h.de_sistema}<span class="ml-1 rounded-full border px-1.5 text-[10px]">cambia algo real</span>{/if}
                      {#if h.pide_aprobacion && !h.de_sistema}
                        <span class="ml-1 rounded-full border px-1.5 text-[10px]">{h.critica ? 'crítica · pide aprobación' : 'no crítica'}</span>
                      {/if}
                      <span class="block text-xs text-[var(--text-secondary)]">
                        {bloqueada ? 'Un agente de clientes siempre la tiene, para no dejar a nadie encerrado.' : resumenDe(h.descripcion)}
                      </span>
                    </span>
                  </label>

                  {#if seleccion[h.nombre] && h.pide_aprobacion && modo === 'editar' && autonomiaDe[h.nombre]}
                    {@const enEste = autonomiaDe[h.nombre].por_agente?.[nombre]}
                    <p class="ml-6 mt-1 text-xs text-[var(--text-secondary)]">
                      {enEste?.autonoma ? 'Este agente la hace solo.' : 'Este agente pide aprobación.'}
                      Se cambia en la tarjeta del agente, debajo de la acción.
                    </p>
                  {/if}

                  {#if seleccion[h.nombre] && !h.escribe && !h.deriva && !h.verifica_identidad && !h.de_sistema}
                    <details class="ml-6 mt-1" open={!(camposElegidos[h.nombre]?.size)}>
                      <summary class="cursor-pointer text-xs">
                        Qué datos ve de la respuesta ({camposElegidos[h.nombre]?.size ?? 0})
                      </summary>
                      <div class="mt-1.5 space-y-1.5">
                        <div class="flex gap-3 text-xs">
                          <button type="button" class="underline" onclick={() => todosLosCampos(h, true)}>Todos</button>
                          <button type="button" class="underline" onclick={() => todosLosCampos(h, false)}>Ninguno</button>
                        </div>
                        <div class="flex flex-wrap gap-x-3 gap-y-1">
                          {#each [...new Set([...(h.campos_conocidos ?? []), ...(camposElegidos[h.nombre] ?? [])])] as c (c)}
                            <label class="flex items-center gap-1 font-mono text-xs">
                              <input type="checkbox" checked={camposElegidos[h.nombre]?.has(c) ?? false}
                                     onchange={() => toggleCampo(h.nombre, c)} />
                              {c}
                            </label>
                          {/each}
                        </div>
                        <div class="flex gap-1.5">
                          <input type="text" bind:value={campoNuevo[h.nombre]} placeholder="agregar otro dato…"
                                 onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); agregarCampoLibre(h.nombre); } }}
                                 class="rounded-md border border-[var(--border-default)] bg-[var(--surface-default)] px-2 py-1 text-xs" />
                          <Button type="button" variant="outline" class="h-auto py-1 text-xs" onclick={() => agregarCampoLibre(h.nombre)}>Agregar</Button>
                        </div>
                      </div>
                    </details>
                  {/if}

                  <details class="ml-6 mt-1">
                    <summary class="cursor-pointer text-[11px] text-[var(--text-secondary)]">Ver la instrucción completa para el modelo</summary>
                    <p class="mt-1 whitespace-pre-line text-[11px] text-[var(--text-secondary)]">{h.descripcion}</p>
                  </details>
                </div>
              {/each}
            </section>
          {:else}
            <p class="text-sm text-[var(--text-secondary)]">Ninguna herramienta coincide con «{busqueda}».</p>
          {/each}
        </div>
      {:else}
        <div class="space-y-4 text-sm">
          <dl class="grid grid-cols-[10rem_1fr] gap-x-3 gap-y-1.5">
            <dt class="text-[var(--text-secondary)]">Atiende a</dt><dd>{deCliente ? 'Los clientes, por WhatsApp' : 'El equipo (uso interno)'}</dd>
            <dt class="text-[var(--text-secondary)]">Nombre</dt><dd>{cargo || '—'}{area ? ` · ${area}` : ''} <span class="font-mono text-xs">({nombre || 'sin identificador'})</span></dd>
            {#if deCliente}
              <dt class="text-[var(--text-secondary)]">Router</dt><dd>{conectar ? `Le pasa: ${atiende.trim() || '(sin temas)'}` : 'No le pasa conversaciones'}</dd>
              <dt class="text-[var(--text-secondary)]">Identidad</dt><dd>{exigeVerificacion ? 'La verifica antes de mostrar datos' : 'No la verifica'}</dd>
            {/if}
            <dt class="text-[var(--text-secondary)]">Pasa a una persona</dt>
            <dd>{motivosElegidos.size
              ? motivos.filter((m) => motivosElegidos.has(m.clave)).map((m) => m.rotulo).join(', ')
              : 'Por cualquier motivo de la empresa'}</dd>
            <dt class="text-[var(--text-secondary)]">Herramientas</dt>
            <dd>{elegidas.length ? elegidas.map((/** @type {any} */ h) => h.nombre).join(', ') : 'Ninguna'}</dd>
          </dl>

          {#if avisos.length}
            <div class="space-y-1.5 rounded-md border border-[var(--v2-clay)] p-3">
              <p class="flex items-center gap-1.5 font-medium"><AlertTriangle size={14} /> Antes de guardar</p>
              {#each avisos as a (a.clave)}<p class="text-xs">{a.texto}</p>{/each}
            </div>
          {:else}
            <p class="text-xs text-[var(--text-secondary)]">Sin avisos: el agente queda listo para trabajar.</p>
          {/if}
        </div>
      {/if}
    </div>

    <Dialog.Footer class="gap-2">
      <Button type="button" variant="outline" onclick={() => (open = false)} disabled={submitting}>Cancelar</Button>
      {#if paso > 0}
        <Button type="button" variant="outline" onclick={() => (paso -= 1)}><ChevronLeft size={14} /> Anterior</Button>
      {/if}
      {#if paso < PASOS.length - 1}
        <Button type="button" onclick={() => (paso += 1)}>Siguiente <ChevronRight size={14} /></Button>
      {:else}
        <Button type="button" disabled={!puedeGuardar} onclick={guardar}>
          {#if submitting}<Loader2 class="mr-1 h-3.5 w-3.5 animate-spin" />{/if}
          {modo === 'crear' ? 'Crear agente' : 'Guardar cambios'}
        </Button>
      {/if}
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
