<script>
  /**
   * Ajustes → Instalaciones.
   *
   * Dos equipos, y el orden en que aparecen ES el flujo: primero quien recibe
   * y valida, después quien ejecuta. Se explica para qué sirve cada uno, no
   * sólo cómo se llama el campo: quien configura esto en otra empresa no
   * conoce el proceso de Rapilink.
   */
  import { enhance } from '$app/forms';
  import { untrack } from 'svelte';
  import { CheckCircle2, AlertTriangle, ArrowDown } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  // 'untrack': siembra los campos UNA vez y despues son de quien edita.
  const a = untrack(() => data.ajustes ?? {});
  let guardando = $state(false);

  // Elegir el técnico completa su correo solo: son dos datos del mismo
  // equipo, y pedirlos por separado es una forma de que queden desparejos.
  let solicitudes = $state(a.tecnico_solicitudes ?? '');
  let aprobadas = $state(a.tecnico_aprobadas ?? '');

  const correoDe = (id) => data.tecnicos?.find((t) => t.id === id)?.email ?? '';
</script>

<svelte:head><title>Instalaciones · Ajustes</title></svelte:head>

<div class="hoja">
  <header>
    <h1>Instalaciones</h1>
    <p class="bajada">
      Qué equipo de WispHub recibe cada etapa de una solicitud de servicio nueva.
    </p>
  </header>

  {#if data.ajustes?.error}
    <div class="alerta"><AlertTriangle size={16} /><span>{data.ajustes.error}</span></div>
  {/if}
  {#if form?.error}
    <div class="alerta"><AlertTriangle size={16} /><span>{form.error}</span></div>
  {/if}
  {#if form?.guardado}
    <div class="ok"><CheckCircle2 size={16} /><span>Guardado.</span></div>
  {/if}

  {#if !data.tecnicos?.length}
    <div class="alerta">
      <AlertTriangle size={16} />
      <span>
        No se pudo leer el personal de WispHub, así que hay que escribir los IDs a mano.
        Revisá que la clave de WispHub esté cargada.
      </span>
    </div>
  {/if}

  <form method="POST" action="?/guardar" use:enhance={() => {
    guardando = true;
    return async ({ update }) => { await update({ reset: false }); guardando = false; };
  }}>
    <fieldset class="tarjeta" disabled={!data.can_edit || guardando}>
      <legend>1 · Recibe las solicitudes nuevas</legend>
      <p class="ayuda">
        A este equipo le llega el ticket apenas alguien envía el formulario. Es quien
        verifica si el servicio puede llegar a esa dirección, antes de que nadie salga a
        instalar.
      </p>
      {#if data.tecnicos?.length}
        <select name="tecnico_solicitudes" bind:value={solicitudes}>
          <option value="">Elegí un equipo…</option>
          {#each data.tecnicos as t}
            <option value={t.id}>{t.nombre}{t.email ? ` — ${t.email}` : ''}</option>
          {/each}
        </select>
      {:else}
        <input name="tecnico_solicitudes" bind:value={solicitudes} placeholder="ID en WispHub" />
      {/if}
      <input type="hidden" name="email_solicitudes"
             value={correoDe(solicitudes) || a.email_solicitudes || ''} />
    </fieldset>

    <div class="flecha"><ArrowDown size={18} /><span>cuando se confirma la factibilidad</span></div>

    <fieldset class="tarjeta" disabled={!data.can_edit || guardando}>
      <legend>2 · Ejecuta las instalaciones</legend>
      <p class="ayuda">
        Cuando alguien aprueba una solicitud desde la bandeja, el ticket pasa a este
        equipo. Todo lo que llega acá ya tiene la factibilidad confirmada.
      </p>
      {#if data.tecnicos?.length}
        <select name="tecnico_aprobadas" bind:value={aprobadas}>
          <option value="">Elegí un equipo…</option>
          {#each data.tecnicos as t}
            <option value={t.id}>{t.nombre}{t.email ? ` — ${t.email}` : ''}</option>
          {/each}
        </select>
      {:else}
        <input name="tecnico_aprobadas" bind:value={aprobadas} placeholder="ID en WispHub" />
      {/if}
      <input type="hidden" name="email_aprobadas"
             value={correoDe(aprobadas) || a.email_aprobadas || ''} />
    </fieldset>

    {#if data.can_edit}
      <button type="submit" class="guardar" disabled={guardando}>
        {guardando ? 'Guardando…' : 'Guardar'}
      </button>
    {:else}
      <p class="nota">Solo un administrador puede cambiar esto.</p>
    {/if}
  </form>
</div>

<style>
  .hoja { max-width: 640px; padding: 24px 20px 60px; display: flex; flex-direction: column; gap: 16px; }
  h1 { font-size: 1.6rem; margin: 0 0 4px; letter-spacing: -.02em; }
  .bajada { color: #5a6672; margin: 0; }

  .tarjeta {
    background: #fff; border: 1px solid #d3dae1; border-radius: 10px;
    padding: 16px; display: flex; flex-direction: column; gap: 8px;
  }
  .tarjeta[disabled] { opacity: .65; }
  legend { font-weight: 650; padding: 0 4px; }
  .ayuda { margin: 0; font-size: .88rem; color: #5a6672; line-height: 1.5; }

  select, input {
    font: inherit; padding: 10px 12px; border: 1px solid #cbd4dd;
    border-radius: 8px; background: #fafbfc; width: 100%;
  }
  select:focus-visible, input:focus-visible, button:focus-visible {
    outline: 2px solid #1668c1; outline-offset: 2px;
  }

  /* El paso entre los dos equipos, dibujado: sin esto son dos campos sueltos
     y no se ve que uno viene después del otro. */
  .flecha {
    display: flex; align-items: center; gap: 8px; justify-content: center;
    color: #7b8794; font-size: .84rem; margin: -6px 0;
  }

  .guardar {
    align-self: flex-start; font: inherit; font-weight: 650; color: #fff;
    background: #1668c1; border: none; border-radius: 8px;
    padding: 11px 20px; cursor: pointer;
  }
  .guardar:disabled { background: #8fb4d9; cursor: default; }
  .nota { color: #7b8794; font-size: .86rem; margin: 0; }

  .alerta, .ok {
    display: flex; gap: 9px; align-items: center; border-radius: 8px;
    padding: 11px 13px; font-size: .9rem;
  }
  .alerta { background: #fdecea; border: 1px solid #f0b8b2; color: #8a2a20; }
  .ok { background: #f4fbf6; border: 1px solid #b9dfc6; color: #1d7a45; }
</style>
