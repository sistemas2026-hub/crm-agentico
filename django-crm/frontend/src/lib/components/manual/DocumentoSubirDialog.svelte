<script>
  import { toast } from 'svelte-sonner';
  import { Loader2 } from '@lucide/svelte';
  import { Button } from '$lib/components/ui/button/index.js';
  import * as Dialog from '$lib/components/ui/dialog/index.js';

  /**
   * Sube un .docx al corpus y elige a que roles se le muestra. Multipart,
   * no JSON -- es el unico formulario del proyecto que manda un archivo (ver
   * la nota en /api/corpus/documentos/+server.js). El backend fragmenta y
   * vectoriza en el momento del POST; no hay paso "guardar" aparte.
   *
   * Sin roles marcados el documento queda cargado pero invisible para TODOS
   * los agentes -- fail-closed, mismo criterio que
   * supabase/03_documentos_roles.sql. Se avisa antes de mandarlo, no se
   * bloquea: puede ser intencional (cargarlo y asignarlo despues).
   *
   * @type {{
   *   open: boolean,
   *   onOpenChange?: (v: boolean) => void,
   *   roles: string[],
   *   onSubido?: (documento: any) => void | Promise<void>
   * }}
   */
  let { open = $bindable(false), onOpenChange, roles, onSubido } = $props();

  /** @type {File | null} */
  let archivo = $state(null);
  /** @type {Record<string, boolean>} */
  let rolesElegidos = $state({});
  let submitting = $state(false);

  $effect(() => {
    if (!open) return;
    archivo = null;
    rolesElegidos = {};
  });

  const nombreArchivoValido = $derived(!archivo || archivo.name.toLowerCase().endsWith('.docx'));
  const puedeSubir = $derived(!!archivo && nombreArchivoValido && !submitting);
  const sinRoles = $derived(Object.values(rolesElegidos).every((v) => !v));

  /** @param {Event} e */
  function elegirArchivo(e) {
    const input = /** @type {HTMLInputElement} */ (e.currentTarget);
    archivo = input.files?.[0] ?? null;
  }

  function toggleRol(/** @type {string} */ rol) {
    rolesElegidos = { ...rolesElegidos, [rol]: !rolesElegidos[rol] };
  }

  async function subir() {
    if (!puedeSubir || !archivo) return;
    if (sinRoles) {
      const seguro = confirm(
        'No marcaste ningún rol: el documento va a quedar cargado pero ningún agente lo va a poder ' +
        'recuperar hasta que le asignes roles. ¿Seguir igual?'
      );
      if (!seguro) return;
    }

    submitting = true;
    try {
      const cuerpo = new FormData();
      cuerpo.append('archivo', archivo);
      const elegidos = Object.keys(rolesElegidos).filter((r) => rolesElegidos[r]);
      if (elegidos.length) cuerpo.append('roles', elegidos.join(','));

      const res = await fetch('/api/corpus/documentos', { method: 'POST', body: cuerpo });
      const datos = await res.json().catch(() => ({}));
      if (!res.ok) {
        toast.error(datos?.error || 'No se pudo cargar el documento');
        return;
      }
      toast.success(`"${datos.titulo}" cargado — ${datos.fragmentos} fragmento${datos.fragmentos === 1 ? '' : 's'}.`);
      open = false;
      await onSubido?.(datos);
    } finally {
      submitting = false;
    }
  }
</script>

<Dialog.Root bind:open onOpenChange={(v) => onOpenChange?.(v)}>
  <Dialog.Content class="sm:max-w-lg">
    <Dialog.Header>
      <Dialog.Title>Nuevo documento</Dialog.Title>
      <Dialog.Description>
        Solo .docx. Se fragmenta y vectoriza al instante — queda buscable apenas termina, sin
        pasos aparte.
      </Dialog.Description>
    </Dialog.Header>

    <div class="space-y-3">
      <label class="space-y-1 text-sm">
        <span class="font-medium">Archivo <span class="text-red-600">*</span></span>
        <input
          type="file"
          accept=".docx"
          onchange={elegirArchivo}
          class="w-full rounded-md border border-[var(--border-default)] bg-[var(--surface-default)] p-2 text-sm"
        />
        {#if archivo && !nombreArchivoValido}
          <span class="text-xs text-red-600">Solo se admite .docx.</span>
        {/if}
      </label>

      <div class="space-y-1.5">
        <span class="text-sm font-medium">Quién lo puede consultar</span>
        {#if !roles || roles.length === 0}
          <p class="text-xs text-[var(--text-secondary)]">
            Este tenant no tiene roles configurados todavía (ver Agentes).
          </p>
        {:else}
          <div class="flex flex-wrap gap-x-3 gap-y-1">
            {#each roles as rol (rol)}
              <label class="flex items-center gap-1.5 text-sm">
                <input type="checkbox" checked={!!rolesElegidos[rol]} onchange={() => toggleRol(rol)} />
                {rol}
              </label>
            {/each}
          </div>
        {/if}
        {#if sinRoles}
          <p class="text-xs text-[var(--text-secondary)]">
            Sin roles marcados, nadie lo va a poder consultar hasta que se lo asignes.
          </p>
        {/if}
      </div>
    </div>

    <Dialog.Footer>
      <Button type="button" variant="outline" onclick={() => (open = false)} disabled={submitting}>
        Cancelar
      </Button>
      <Button type="button" disabled={!puedeSubir} onclick={subir}>
        {#if submitting}<Loader2 class="mr-1 h-3.5 w-3.5 animate-spin" />{/if}
        Cargar documento
      </Button>
    </Dialog.Footer>
  </Dialog.Content>
</Dialog.Root>
