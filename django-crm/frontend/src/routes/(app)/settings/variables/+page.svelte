<script>
  /**
   * Variables de la empresa (12/11/2026).
   *
   * Datos que cambian de un ISP a otro y no son secretos: el subdominio de una
   * API, un ID de cuenta, un link. Las herramientas los nombran (por ejemplo
   * `base_url_ref`) y el motor los resuelve al llamar. Hasta hoy solo se podían
   * cargar los de SmartOLT y Pagos, cada uno en su pantalla; uno nuevo —el que
   * pide un conector recién aplicado— necesitaba una sesión de código
   * (CLAUDE.md §3.3).
   *
   * Cada fila dice qué herramienta la usa: quitar una que está en uso lo
   * rechaza el motor, y la pantalla lo avisa antes. Las que una herramienta
   * pide y no están se muestran arriba, listas para cargar.
   */
  import { enhance } from '$app/forms';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import { ChevronLeft, KeyRound } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let d = $derived(data.datos);
  let filas = $derived(Object.entries(d?.variables ?? {}).sort(([a], [b]) => a.localeCompare(b)));
  let faltan = $derived(Object.entries(d?.faltan ?? {}));
  /** La que se está editando (nombre), o null. */
  let editando = $state(/** @type {string | null} */ (null));
</script>

<PageHeader title="Variables de la empresa">
  {#snippet crumb()}
    <a href="/settings" class="volver"><ChevronLeft size={13} />Configuración</a>
  {/snippet}
  {#snippet sub()}
    Datos de la empresa que usan las herramientas y no son secretos: subdominios, IDs de cuenta,
    links. Las claves van en <a href="/settings/credenciales">Credenciales</a>, cifradas.
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <div class="v2-pad" style="padding-top:16px;padding-bottom:32px;max-width:860px;display:grid;gap:16px">
    {#if !d}
      <p class="v2-card aviso">No se pudo leer la configuración del asistente. Probá recargar en un rato.</p>
    {:else}
      {#if form?.error}<p class="v2-card aviso">{form.error}</p>{/if}

      {#if faltan.length}
        <div class="v2-card bloque">
          <div class="v2-label">Faltan</div>
          <p class="v2-sub ayuda">Una herramienta las pide y no están cargadas: falla la primera vez que se use.</p>
          {#each faltan as [nombre, herramientas] (nombre)}
            <form method="POST" action="?/guardar" use:enhance class="fila">
              <input type="hidden" name="nombre" value={nombre} />
              <span class="v2-num nombre">{nombre}</span>
              <input name="valor" class="v2-input" required placeholder="Valor" />
              <button class="v2-btn v2-btn-primary v2-btn-sm" type="submit">Cargar</button>
              <span class="v2-sub usos">la usa {herramientas.join(', ')}</span>
            </form>
          {/each}
        </div>
      {/if}

      <div class="v2-card bloque">
        <div class="v2-label">Cargadas ({filas.length})</div>
        {#if !filas.length}
          <p class="v2-sub ayuda">Todavía no hay ninguna.</p>
        {/if}
        {#each filas as [nombre, valor] (nombre)}
          <div class="fila">
            <span class="v2-num nombre">{nombre}</span>
            {#if editando === nombre}
              <form method="POST" action="?/guardar" class="edicion"
                    use:enhance={() => async ({ result, update }) => {
                      if (result.type === 'success') editando = null;
                      await update({ reset: false });
                    }}>
                <input type="hidden" name="nombre" value={nombre} />
                <input name="valor" class="v2-input" required {value} />
                <button class="v2-btn v2-btn-primary v2-btn-sm" type="submit">Guardar</button>
                <button class="v2-btn v2-btn-sm" type="button" onclick={() => (editando = null)}>Cancelar</button>
              </form>
            {:else}
              <span class="valor">{valor}</span>
              <button class="v2-btn v2-btn-sm" type="button" onclick={() => (editando = nombre)}>Cambiar</button>
              {#if d.usos[nombre]?.length}
                <span class="v2-sub usos" title="Una herramienta la usa: el motor no deja quitarla">
                  la usa {d.usos[nombre].join(', ')}
                </span>
              {:else}
                <form method="POST" action="?/borrar" use:enhance>
                  <input type="hidden" name="nombre" value={nombre} />
                  <button class="v2-btn v2-btn-sm v2-btn-quiet" type="submit">Quitar</button>
                </form>
              {/if}
            {/if}
          </div>
        {/each}
      </div>

      <form method="POST" action="?/guardar" use:enhance class="v2-card bloque">
        <div class="v2-label">Agregar una</div>
        <div class="fila">
          <input name="nombre" class="v2-input" required placeholder="NOMBRE_EN_MAYUSCULAS"
                 value={form?.nombre ?? data.sugerida ?? ''} />
          <input name="valor" class="v2-input" required placeholder="Valor" />
          <button class="v2-btn v2-btn-primary v2-btn-sm" type="submit">Agregar</button>
        </div>
        <p class="v2-sub ayuda"><KeyRound size={12} /> Si el valor es una clave, un token o una contraseña,
          no va acá: el motor lo rechaza. Cargalo en <a href="/settings/credenciales">Credenciales</a>.</p>
      </form>
    {/if}
  </div>
</div>

<style>
  .volver {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    color: inherit;
    text-decoration: none;
  }
  .aviso {
    padding: 12px 14px;
    margin: 0;
    font-size: 13px;
    color: var(--v2-rust);
  }
  .bloque {
    padding: 14px 18px;
    display: grid;
    gap: 10px;
  }
  .fila,
  .edicion {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    font-size: 13px;
  }
  .nombre {
    min-width: 220px;
    font-size: 12px;
  }
  .valor {
    flex: 1;
    word-break: break-all;
  }
  .usos {
    font-size: 11.5px;
  }
  .ayuda {
    font-size: 12px;
    margin: 0;
  }
</style>
