<script>
  /**
   * Qué módulos heredados del CRM ve esta empresa en su menú (12/11/2026).
   *
   * Un tercio del menú venía de BottleCRM y nada de Dexter lo alimenta
   * (auditoría del menú, §1.5). Cada empresa decide si los quiere ver; por
   * defecto se ven todos. Ocultar no es un permiso: la ruta sigue existiendo y
   * esta pantalla lo dice, para que nadie lo use creyendo que cierra algo.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';
  import { enhance } from '$app/forms';
  import { invalidateAll } from '$app/navigation';
  import { MODULOS_OCULTABLES } from '$lib/v2/modulos.js';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let guardando = $state(false);
  /** Marcado = se VE en el menú. Lo que se guarda es lo contrario. */
  let visibles = $state(
    Object.fromEntries(
      MODULOS_OCULTABLES.map((m) => [m.clave, !(data.ocultos ?? []).includes(m.clave)])
    )
  );
  let cuantosOcultos = $derived(Object.values(visibles).filter((v) => !v).length);
</script>

<PageHeader title="Módulos del menú">
  {#snippet crumb()}<SettingsCrumb />{/snippet}
  {#snippet sub()}
    Pantallas heredadas del CRM que esta empresa puede sacar de su menú. Por defecto se ven todas.
  {/snippet}
</PageHeader>

<div class="v2-pad modulos">
  <p class="aviso" role="note">
    <b>Ocultar no quita el acceso.</b> La pantalla sigue existiendo y quien tenga la dirección
    puede abrirla con los mismos permisos de siempre; esto solo decide qué aparece en el menú de
    todas las personas de la empresa.
  </p>

  {#if data.ocultos === null}
    <p class="error" role="alert">
      No se pudo leer qué tiene oculto esta empresa ahora. Para no borrar lo que ya estaba
      guardado, esta pantalla no deja guardar hasta poder leerlo. Probá recargar en un momento.
    </p>
  {:else}
    <form
      method="POST"
      action="?/guardar"
      use:enhance={() => {
        guardando = true;
        return async ({ update }) => {
          await update({ reset: false });
          // El menú lo dibuja el layout: se vuelve a leer para que cambie ya.
          await invalidateAll();
          guardando = false;
        };
      }}
    >
      <ul class="lista">
        {#each MODULOS_OCULTABLES as m (m.clave)}
          <li class="v2-card fila">
            <label>
              <input type="checkbox" bind:checked={visibles[m.clave]} />
              <span class="texto">
                <b>{m.nombre}</b>
                <small>{m.para}</small>
                {#if m.nota}
                  <small class="nota" class:usa={m.dexter === 'usa'}>
                    {m.dexter === 'usa' ? '' : 'Dexter no lo usa. '}{m.nota}
                  </small>
                {/if}
              </span>
              <span class="estado">{visibles[m.clave] ? 'Se ve' : 'Oculto'}</span>
            </label>
            {#if !visibles[m.clave]}
              <input type="hidden" name="oculto" value={m.clave} />
            {/if}
          </li>
        {/each}
      </ul>

      {#if form?.error}<p class="error" role="alert">{form.error}</p>{/if}
      {#if form?.guardado}<p class="ok" role="status">Guardado. El menú ya refleja el cambio.</p>{/if}

      <div class="acciones">
        <span class="v2-sub">
          {cuantosOcultos === 0
            ? 'Se ven todos.'
            : `${cuantosOcultos} ${cuantosOcultos === 1 ? 'oculto' : 'ocultos'}.`}
        </span>
        <button class="v2-btn v2-btn-primary" type="submit" disabled={guardando}>
          {guardando ? 'Guardando…' : 'Guardar'}
        </button>
      </div>
    </form>
  {/if}
</div>

<style>
  .modulos {
    display: flex;
    flex-direction: column;
    gap: 14px;
    max-width: 760px;
    padding-bottom: 32px;
  }
  .aviso {
    margin: 0;
    font-size: 13.5px;
    color: var(--v2-slate);
  }
  .lista {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .fila label {
    display: flex;
    align-items: flex-start;
    gap: 12px;
    padding: 12px 14px;
    cursor: pointer;
  }
  .fila input[type='checkbox'] {
    margin-top: 3px;
    width: 18px;
    height: 18px;
    flex: none;
  }
  .texto {
    display: flex;
    flex-direction: column;
    gap: 2px;
    flex: 1;
    min-width: 0;
  }
  .texto small {
    font-size: 12.5px;
    color: var(--v2-slate);
  }
  .nota {
    color: var(--v2-clay) !important;
  }
  .nota.usa {
    color: var(--v2-moss) !important;
  }
  .estado {
    font-size: 12px;
    font-weight: 600;
    color: var(--v2-slate);
    white-space: nowrap;
  }
  .acciones {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-top: 6px;
  }
  .error {
    margin: 0;
    color: var(--v2-rust);
    font-size: 13.5px;
  }
  .ok {
    margin: 0;
    color: var(--v2-moss);
    font-size: 13.5px;
  }
</style>
