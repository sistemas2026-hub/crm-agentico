<script>
  import { invalidateAll } from '$app/navigation';
  import { toast } from 'svelte-sonner';
  import { Loader2 } from '@lucide/svelte';
  import { Button } from '$lib/components/ui/button/index.js';
  import * as Dialog from '$lib/components/ui/dialog/index.js';

  /**
   * Crear o editar un agente (un rol de tenants/*.yaml). Un solo componente
   * para los dos modos -- en 'editar', `nombre` queda de solo lectura:
   * renombrar un rol obliga a tocar roles_permitidos de cada herramienta,
   * llm.overrides, escalamiento.destino_rol y sesiones ya abiertas, fuera de
   * alcance de esta pantalla (para renombrar: borrar y crear de nuevo).
   *
   * Los checkboxes de campo por herramienta arrancan TODOS destildados salvo
   * los que ya estaban guardados (modo editar) -- fail-closed: el admin
   * elige a propósito, nunca se preseleccionan "todos los campos conocidos".
   *
   * @type {{
   *   open: boolean,
   *   onOpenChange?: (v: boolean) => void,
   *   modo: 'crear' | 'editar',
   *   agente?: any,
   *   catalogo: Array<{nombre: string, descripcion: string, tipo: string,
   *     verifica_identidad: boolean, campos_conocidos: string[]}>,
   *   onSaved?: () => void | Promise<void>
   * }}
   */
  let { open = $bindable(false), onOpenChange, modo, agente, catalogo, onSaved } = $props();

  let nombre = $state('');
  let area = $state('');
  let cargo = $state('');
  let descripcion = $state('');
  let orientadoA = $state('colaborador');
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
    nombre = esEditar ? agente.nombre : '';
    area = esEditar ? agente.area || '' : '';
    cargo = esEditar ? agente.cargo || '' : '';
    descripcion = esEditar ? agente.descripcion || '' : '';
    orientadoA = esEditar ? agente.orientado_a : 'colaborador';

    /** @type {Record<string, boolean>} */
    const nuevaSeleccion = {};
    /** @type {Record<string, Set<string>>} */
    const nuevosCampos = {};
    const herramientasDelAgente = esEditar ? agente.herramientas : [];
    for (const h of herramientasDelAgente) {
      nuevaSeleccion[h.nombre] = true;
      nuevosCampos[h.nombre] = new Set(h.campos_permitidos || []);
    }
    seleccion = nuevaSeleccion;
    camposElegidos = nuevosCampos;
    campoNuevo = {};
  });

  function toggleHerramienta(/** @type {string} */ nombreHerr) {
    seleccion = { ...seleccion, [nombreHerr]: !seleccion[nombreHerr] };
    if (seleccion[nombreHerr] && !camposElegidos[nombreHerr]) {
      camposElegidos = { ...camposElegidos, [nombreHerr]: new Set() };
    }
  }

  function toggleCampo(/** @type {string} */ nombreHerr, /** @type {string} */ campo) {
    const actuales = new Set(camposElegidos[nombreHerr] || []);
    if (actuales.has(campo)) actuales.delete(campo);
    else actuales.add(campo);
    camposElegidos = { ...camposElegidos, [nombreHerr]: actuales };
  }

  function agregarCampoLibre(/** @type {string} */ nombreHerr) {
    const valor = (campoNuevo[nombreHerr] || '').trim();
    if (!valor) return;
    const actuales = new Set(camposElegidos[nombreHerr] || []);
    actuales.add(valor);
    camposElegidos = { ...camposElegidos, [nombreHerr]: actuales };
    campoNuevo = { ...campoNuevo, [nombreHerr]: '' };
  }

  const nombreValido = $derived(/^[a-z][a-z0-9_]{1,29}$/.test(nombre));
  const puedeGuardar = $derived(
    nombreValido && descripcion.trim().length > 0 && !submitting
  );

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
        herramientas
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
</script>

<Dialog.Root bind:open onOpenChange={(v) => onOpenChange?.(v)}>
  <Dialog.Content class="sm:max-w-2xl">
    <Dialog.Header>
      <Dialog.Title>{modo === 'crear' ? 'Nuevo agente' : `Editar ${agente?.nombre ?? ''}`}</Dialog.Title>
      <Dialog.Description>
        Un agente es un rol: a quién le habla, qué herramientas puede usar y qué campos ve de cada
        una. Crear una herramienta nueva (conectar una API) sigue siendo trabajo de código.
      </Dialog.Description>
    </Dialog.Header>

    <div class="space-y-3 max-h-[60vh] overflow-y-auto pr-1">
      <div class="grid grid-cols-2 gap-2">
        <label class="space-y-1 text-sm">
          <span class="font-medium">Nombre (identificador) <span class="text-red-600">*</span></span>
          <input
            type="text"
            bind:value={nombre}
            disabled={modo === 'editar'}
            placeholder="ej. ventas"
            class="w-full rounded-md border border-[var(--border-default)] bg-[var(--surface-default)] p-2 text-sm disabled:opacity-60"
          />
          {#if nombre && !nombreValido}
            <span class="text-xs text-red-600">Minúscula, empieza con letra, solo letras/números/_</span>
          {/if}
        </label>
        <label class="space-y-1 text-sm">
          <span class="font-medium">Habla con</span>
          <select
            bind:value={orientadoA}
            class="w-full rounded-md border border-[var(--border-default)] bg-[var(--surface-default)] p-2 text-sm"
          >
            <option value="colaborador">Un colaborador (uso interno)</option>
            <option value="cliente_final">El cliente final (verificación de identidad)</option>
          </select>
        </label>
      </div>

      <div class="grid grid-cols-2 gap-2">
        <label class="space-y-1 text-sm">
          <span class="font-medium">Área</span>
          <input
            type="text"
            bind:value={area}
            placeholder="ej. Atención al Cliente"
            class="w-full rounded-md border border-[var(--border-default)] bg-[var(--surface-default)] p-2 text-sm"
          />
        </label>
        <label class="space-y-1 text-sm">
          <span class="font-medium">Cargo</span>
          <input
            type="text"
            bind:value={cargo}
            placeholder="ej. Agente de Ventas"
            class="w-full rounded-md border border-[var(--border-default)] bg-[var(--surface-default)] p-2 text-sm"
          />
        </label>
      </div>

      <label class="space-y-1 text-sm">
        <span class="font-medium">Descripción / instrucciones <span class="text-red-600">*</span></span>
        <textarea
          bind:value={descripcion}
          rows="3"
          placeholder="Qué hace este agente, con quién habla, qué NO debe hacer."
          class="w-full rounded-md border border-[var(--border-default)] bg-[var(--surface-default)] p-2 text-sm"
        ></textarea>
      </label>

      <div class="space-y-2">
        <span class="text-sm font-medium">Herramientas que puede usar</span>
        {#each catalogo as herr (herr.nombre)}
          <div class="rounded-md border border-[var(--border-default)] p-2">
            <label class="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={!!seleccion[herr.nombre]}
                onchange={() => toggleHerramienta(herr.nombre)}
                class="mt-0.5"
              />
              <span>
                <span class="font-medium">{herr.nombre}</span>
                <span class="text-xs text-[var(--text-secondary)]"> · {herr.tipo}</span>
                {#if herr.descripcion}
                  <div class="text-xs text-[var(--text-secondary)]">{herr.descripcion}</div>
                {/if}
              </span>
            </label>

            {#if seleccion[herr.nombre] && !herr.verifica_identidad}
              <div class="mt-2 ml-6 space-y-1.5">
                <span class="text-xs text-[var(--text-secondary)]">
                  Campos que puede ver de esta herramienta (nada por defecto):
                </span>
                <div class="flex flex-wrap gap-x-3 gap-y-1">
                  {#each herr.campos_conocidos as campo (campo)}
                    <label class="flex items-center gap-1 text-xs">
                      <input
                        type="checkbox"
                        checked={camposElegidos[herr.nombre]?.has(campo) ?? false}
                        onchange={() => toggleCampo(herr.nombre, campo)}
                      />
                      {campo}
                    </label>
                  {/each}
                  {#each Array.from(camposElegidos[herr.nombre] || []).filter((c) => !herr.campos_conocidos.includes(c)) as campo (campo)}
                    <label class="flex items-center gap-1 text-xs">
                      <input
                        type="checkbox"
                        checked={true}
                        onchange={() => toggleCampo(herr.nombre, campo)}
                      />
                      {campo}
                    </label>
                  {/each}
                </div>
                <div class="flex gap-1.5">
                  <input
                    type="text"
                    bind:value={campoNuevo[herr.nombre]}
                    placeholder="agregar otro campo…"
                    onkeydown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault();
                        agregarCampoLibre(herr.nombre);
                      }
                    }}
                    class="rounded-md border border-[var(--border-default)] bg-[var(--surface-default)] px-2 py-1 text-xs"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    class="h-auto py-1 text-xs"
                    onclick={() => agregarCampoLibre(herr.nombre)}
                  >
                    Agregar
                  </Button>
                </div>
              </div>
            {/if}
          </div>
        {/each}
      </div>
    </div>

    <Dialog.Footer>
      <Button type="button" variant="outline" onclick={() => (open = false)} disabled={submitting}>
        Cancelar
      </Button>
      <Button type="button" disabled={!puedeGuardar} onclick={guardar}>
        {#if submitting}<Loader2 class="mr-1 h-3.5 w-3.5 animate-spin" />{/if}
        {modo === 'crear' ? 'Crear agente' : 'Guardar cambios'}
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
