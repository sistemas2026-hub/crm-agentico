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

  // QUIÉN DECIDE (12/11/2026). Las áreas se ELIGEN de las que la empresa
  // declaró en el motor: el nombre interno no lo conoce nadie, y uno escrito a
  // mano que no coincida dejaría al área afuera sin que nada lo avise.
  const d = untrack(() => data.decision ?? {});
  let elegidas = $state(new Set(d.areas_que_deciden ?? []));
  const alternarArea = (nombre) => {
    const proximo = new Set(elegidas);
    proximo.has(nombre) ? proximo.delete(nombre) : proximo.add(nombre);
    elegidas = proximo;
  };
  // Una elegida que el motor ya no declara (se borró el área) se muestra igual:
  // sigue guardada y sigue valiendo, y esconderla la haría imposible de quitar.
  const opcionesDeArea = $derived.by(() => {
    const disponibles = data.decision?.areas_disponibles ?? [];
    const nombres = new Set(disponibles.map((a) => a.nombre));
    const huerfanas = [...(d.areas_que_deciden ?? [])]
      .filter((n) => !nombres.has(n))
      .map((n) => ({ nombre: n, etiqueta: `${n} (ya no existe en la empresa)` }));
    return [...disponibles, ...huerfanas];
  });
  let guardandoDecision = $state(false);
</script>

<svelte:head><title>Instalaciones · Ajustes</title></svelte:head>

<!-- Scroll propio: el contenedor de la app corta lo que se sale (.v2-main,
     overflow hidden). Sin esto la pantalla no bajaba (02/11/2026). -->
<div class="v2-scroll">
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
  {#if form?.error && form?.de !== 'decision'}
    <div class="alerta"><AlertTriangle size={16} /><span>{form.error}</span></div>
  {/if}
  {#if form?.guardado && form?.de !== 'decision'}
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

  <!-- QUIÉN DECIDE LA FACTIBILIDAD (12/11/2026). Hasta ese día la bandeja, la
       decisión y el expediente con la cédula los veía cualquier rol. -->
  <form method="POST" action="?/decision" id="quien-decide" use:enhance={() => {
    guardandoDecision = true;
    return async ({ update }) => { await update({ reset: false }); guardandoDecision = false; };
  }}>
    <fieldset class="tarjeta" disabled={!data.can_edit || guardandoDecision}>
      <legend>Quién decide la factibilidad</legend>
      <p class="ayuda">
        Las personas de estas áreas ven la bandeja de Instalaciones, deciden si el servicio
        llega a la dirección y abren el expediente (con la foto del documento, el recibo y
        la firma). Administración, supervisión y operaciones pueden siempre.
        <strong>Sin ningún área elegida, solo ellos.</strong>
      </p>
      {#if data.decision?.error}
        <div class="alerta"><AlertTriangle size={16} /><span>{data.decision.error}</span></div>
      {/if}
      {#if data.decision?.error_areas}
        <div class="alerta"><AlertTriangle size={16} /><span>{data.decision.error_areas}</span></div>
      {/if}
      {#if opcionesDeArea.length}
        <div class="areas">
          {#each opcionesDeArea as area (area.nombre)}
            <label class="area">
              <input type="checkbox" name="areas_que_deciden" value={area.nombre}
                     checked={elegidas.has(area.nombre)}
                     onchange={() => alternarArea(area.nombre)} />
              <span>{area.etiqueta}</span>
            </label>
          {/each}
        </div>
      {:else if !data.decision?.error_areas}
        <p class="nota">La empresa todavía no tiene áreas. Se crean en Ajustes → Áreas (/settings/areas).</p>
      {/if}
      {#if !elegidas.size}
        <p class="aviso-vacio">
          <AlertTriangle size={14} />
          Ningún área elegida: solo administración, supervisión y operaciones ven la bandeja.
        </p>
      {/if}
    </fieldset>
    {#if form?.de === 'decision' && form?.error}
      <div class="alerta"><AlertTriangle size={16} /><span>{form.error}</span></div>
    {/if}
    {#if form?.de === 'decision' && form?.guardado}
      <div class="ok"><CheckCircle2 size={16} /><span>Guardado.</span></div>
    {/if}
    {#if data.can_edit}
      <button type="submit" class="guardar" disabled={guardandoDecision}>
        {guardandoDecision ? 'Guardando…' : 'Guardar quién decide'}
      </button>
    {/if}
  </form>
</div>
</div>

<style>
  .hoja { max-width: 640px; padding: 24px 20px 60px; display: flex; flex-direction: column; gap: 16px; }
  h1 { font-size: 1.6rem; margin: 0 0 4px; letter-spacing: -.02em; }
  .bajada { color: var(--v2-slate); margin: 0; }

  .tarjeta {
    background: var(--v2-card); border: 1px solid var(--v2-line); border-radius: 10px;
    padding: 16px; display: flex; flex-direction: column; gap: 8px;
  }
  .tarjeta[disabled] { opacity: .65; }
  legend { font-weight: 650; padding: 0 4px; }
  .ayuda { margin: 0; font-size: .88rem; color: var(--v2-slate); line-height: 1.5; }

  select, input {
    font: inherit; padding: 10px 12px; border: 1px solid var(--v2-line-strong);
    border-radius: 8px; background: var(--v2-paper); width: 100%;
  }
  select:focus-visible, input:focus-visible, button:focus-visible {
    outline: 2px solid var(--v2-ember); outline-offset: 2px;
  }

  /* El paso entre los dos equipos, dibujado: sin esto son dos campos sueltos
     y no se ve que uno viene después del otro. */
  .flecha {
    display: flex; align-items: center; gap: 8px; justify-content: center;
    color: var(--v2-slate); font-size: .84rem; margin: -6px 0;
  }

  .guardar {
    align-self: flex-start; font: inherit; font-weight: 650; color: var(--v2-on-ember);
    background: var(--v2-ember); border: none; border-radius: 8px;
    padding: 11px 20px; cursor: pointer;
  }
  .guardar:disabled { background: color-mix(in srgb, var(--v2-ember) 45%, var(--v2-card)); cursor: default; }
  .nota { color: var(--v2-slate); font-size: .86rem; margin: 0; }
  form { display: flex; flex-direction: column; gap: 12px; }
  .areas { display: flex; flex-direction: column; gap: 6px; }
  .area { display: flex; align-items: center; gap: 9px; font-size: .92rem; cursor: pointer; }
  .area input { width: auto; }
  .aviso-vacio { display: flex; gap: 7px; align-items: center; margin: 0; font-size: .84rem; color: var(--v2-clay); }

  .alerta, .ok {
    display: flex; gap: 9px; align-items: center; border-radius: 8px;
    padding: 11px 13px; font-size: .9rem;
  }
  .alerta { background: color-mix(in srgb, var(--v2-rust) 10%, var(--v2-card)); border: 1px solid color-mix(in srgb, var(--v2-rust) 32%, var(--v2-card)); color: var(--v2-rust); }
  .ok { background: color-mix(in srgb, var(--v2-moss) 10%, var(--v2-card)); border: 1px solid color-mix(in srgb, var(--v2-moss) 32%, var(--v2-card)); color: var(--v2-moss); }
</style>
