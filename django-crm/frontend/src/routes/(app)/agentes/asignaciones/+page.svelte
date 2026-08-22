<script>
  /**
   * Quien puede usar cada agente. Una fila por persona del equipo, una
   * columna por agente interno.
   *
   * Se guarda por persona (no un "Guardar" global): cada fila es una decision
   * independiente, y un boton unico obligaria a revisar todo el tablero antes
   * de confirmar un solo cambio.
   *
   * Sin ningun agente marcado, esa persona no accede al asistente -- se lo
   * dice el propio motor con un 403, no se falla en silencio ni se cae a un
   * agente por defecto.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import { Button } from '$lib/components/ui/button/index.js';
  import { Loader2 } from '@lucide/svelte';
  import { toast } from 'svelte-sonner';

  /** @type {{ data: any }} */
  let { data } = $props();

  const esAdmin = $derived(data.role === 'ADMIN');

  // Copia local mutable: marcar y guardar actualiza la pantalla al toque, sin
  // recargar. Mismo patron que /manual y /conversaciones.
  /** @type {Record<string, string[]>} */
  let asignaciones = $state({ ...(data.asignaciones ?? {}) });
  /** @type {Record<string, boolean>} */
  let guardando = $state({});

  // A nombre de quien se le asigna el trabajo en el sistema operativo. Se
  // edita en la MISMA fila que los agentes y se guarda con el mismo boton:
  // las dos cosas responden a la misma pregunta -- que hace esta persona y
  // donde. Separarlas en dos pantallas fue lo que dejo gente creada a medias.
  /** @type {Record<string, string>} */
  let externos = $state(
    Object.fromEntries(
      Object.entries(data.identidades ?? {}).map(([id, v]) => [
        id,
        /** @type {any} */ (v)?.identificador ?? ''
      ])
    )
  );

  const nombreExterno = (/** @type {string} */ id) =>
    data.candidatos_externos?.find((/** @type {any} */ c) => c.identificador === externos[id])
      ?.nombre_visible ?? '';

  const tiene = (/** @type {string} */ id, /** @type {string} */ agente) =>
    (asignaciones[id] ?? []).includes(agente);

  function alternar(/** @type {string} */ id, /** @type {string} */ agente) {
    const actuales = asignaciones[id] ?? [];
    asignaciones = {
      ...asignaciones,
      [id]: actuales.includes(agente)
        ? actuales.filter((a) => a !== agente)
        : [...actuales, agente]
    };
  }

  async function guardar(/** @type {any} */ persona) {
    guardando = { ...guardando, [persona.id]: true };
    try {
      const resp = await fetch(`/api/agentes/asignaciones/${persona.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          roles: asignaciones[persona.id] ?? [],
          identidad_externa: {
            identificador: externos[persona.id] ?? '',
            nombre_visible: nombreExterno(persona.id)
          }
        })
      });
      const datos = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        toast.error(datos?.error || 'No se pudieron guardar los agentes');
        return;
      }
      asignaciones = { ...asignaciones, [persona.id]: datos.roles ?? [] };
      const n = (datos.roles ?? []).length;
      toast.success(
        n === 0
          ? `${persona.name} ya no accede al asistente.`
          : `${persona.name}: ${n} agente${n === 1 ? '' : 's'}.`
      );
    } finally {
      guardando = { ...guardando, [persona.id]: false };
    }
  }
</script>

<PageHeader title="Quién usa cada agente">
  {#snippet sub()}
    Cada persona pregunta en un solo lugar y el asistente usa las herramientas de todos los agentes
    que tenga asignados. Sin ninguno marcado, no accede.
  {/snippet}
  {#snippet actions()}
    <a class="v2-btn v2-btn-sm" href="/agentes">Ver agentes</a>
  {/snippet}
</PageHeader>

{#if data.error}
  <p class="aviso-error v2-pad">⚠️ {data.error}</p>
{:else if !esAdmin}
  <p class="v2-sub v2-pad">Solo un administrador puede asignar agentes.</p>
{:else if data.personas.length === 0}
  <p class="v2-sub v2-pad">No hay personas activas en esta organización.</p>
{:else}
  <div class="v2-scroll">
    <div class="v2-pad tabla-envoltorio">
      <table class="tabla">
        <thead>
          <tr>
            <th class="col-persona">Persona</th>
            {#each data.agentes as agente (agente)}
              <th class="col-agente">{agente}</th>
            {/each}
            {#if data.candidatos_externos?.length}
              <th class="col-externo">{data.sistema_externo || 'Usuario externo'}</th>
            {/if}
            <th></th>
          </tr>
        </thead>
        <tbody>
          {#each data.personas as persona (persona.id)}
            <tr>
              <td class="col-persona">
                <span class="nombre">{persona.name}</span>
                {#if persona.email}<span class="v2-muted correo">{persona.email}</span>{/if}
              </td>
              {#each data.agentes as agente (agente)}
                <td class="col-agente">
                  <input
                    type="checkbox"
                    checked={tiene(persona.id, agente)}
                    onchange={() => alternar(persona.id, agente)}
                    aria-label="{agente} para {persona.name}"
                  />
                </td>
              {/each}
              {#if data.candidatos_externos?.length}
                <td class="col-externo">
                  <select
                    class="v2-input select-externo"
                    bind:value={externos[persona.id]}
                    aria-label="Usuario externo de {persona.name}"
                  >
                    <option value="">Sin vincular</option>
                    {#each data.candidatos_externos as c (c.identificador)}
                      <option value={c.identificador}>{c.nombre_visible}</option>
                    {/each}
                  </select>
                </td>
              {/if}
              <td>
                <Button
                  type="button"
                  variant="outline"
                  class="h-auto py-1 text-xs"
                  disabled={guardando[persona.id]}
                  onclick={() => guardar(persona)}
                >
                  {#if guardando[persona.id]}<Loader2 class="mr-1 h-3 w-3 animate-spin" />{/if}
                  Guardar
                </Button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  </div>
{/if}

<style>
  .col-externo {
    white-space: nowrap;
  }
  .select-externo {
    width: 180px;
    font-size: 12.5px;
    padding: 3px 6px;
  }
  .aviso-error {
    color: var(--v2-rust);
    font-size: 14px;
  }
  .tabla-envoltorio {
    padding-top: 12px;
    padding-bottom: 32px;
  }
  .tabla {
    border-collapse: collapse;
    font-size: 13px;
    min-width: 480px;
  }
  .tabla th {
    text-align: left;
    font-weight: 600;
    font-size: 11.5px;
    text-transform: uppercase;
    letter-spacing: 0.02em;
    color: var(--v2-slate);
    padding: 0 14px 8px 0;
    border-bottom: 1px solid var(--v2-line);
  }
  .tabla td {
    padding: 10px 14px 10px 0;
    border-bottom: 1px solid var(--v2-line);
    vertical-align: middle;
  }
  .col-agente {
    text-align: center;
    padding-right: 14px;
  }
  .col-persona {
    min-width: 210px;
  }
  .nombre {
    display: block;
  }
  .correo {
    font-size: 11.5px;
  }
</style>
