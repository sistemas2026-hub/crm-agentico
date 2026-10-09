<script>
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import EmptyState from '$lib/v2/components/EmptyState.svelte';
  import NextAction from '$lib/v2/components/NextAction.svelte';
  import { Wrench, Receipt, Building2, Network, UserRound, PackageOpen } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  //  Los mismos seis que el motor acepta y que la cola de tickets sabe
  //  dibujar. Una lista cerrada en los dos lados: un icono que el motor
  //  aceptara y la pantalla no supiera dibujar degradaría a las iniciales,
  //  y la fila se vería distinta de las demás sin motivo visible.
  const ICONOS = {
    llave: Wrench,
    factura: Receipt,
    edificio: Building2,
    red: Network,
    persona: UserRound,
    caja: PackageOpen
  };
  const NOMBRES_ICONO = Object.keys(ICONOS);

  let editando = $state('');
  let creando = $state(false);
</script>

<div class="v2-page">
  <PageHeader title="Áreas de trabajo">
    {#snippet sub()}
      Un ticket no tiene área propia: hereda la de su responsable.
    {/snippet}
    {#snippet actions()}
      {#if !creando}
        <button class="v2-btn v2-btn-primary" onclick={() => (creando = true)}>
          + Nueva área
        </button>
      {/if}
    {/snippet}
  </PageHeader>

  {#if form?.crear?.ok}
    <NextAction
      label="Área creada"
      text={`"${form.crear.etiqueta}" quedó con el identificador interno «${form.crear.nombre}». Ese identificador no cambia aunque después le cambies el nombre visible. Todavía no recibe tickets: asignale gente desde Agentes.`}
      tone="mint" />
  {/if}
  {#if form?.borrar?.ok}
    <NextAction label="Área borrada" text="Ya no aparece en los tableros." tone="mint" />
  {/if}
  {#if form?.borrar?.error}
    <NextAction label="No se pudo borrar" text={form.borrar.error} tone="rust" />
  {/if}
  {#if form?.editar?.error}
    <NextAction label="No se pudo guardar" text={form.editar.error} tone="rust" />
  {/if}

  {#if creando}
    <form method="POST" action="?/crear" class="tarjeta">
      <h2 class="titulo-seccion">Nueva área</h2>
      <div class="campos">
        <label class="campo">
          <span class="etiqueta-campo">Nombre</span>
          <input class="entrada" name="etiqueta" placeholder="Cuadrilla Norte"
                 value={form?.crear?.etiqueta ?? ''} required />
        </label>
        <label class="campo campo-corto">
          <span class="etiqueta-campo">Color</span>
          <input class="entrada entrada-color" type="color" name="color" value="#64748b" />
        </label>
        <label class="campo">
          <span class="etiqueta-campo">Ícono</span>
          <select class="entrada" name="icono">
            {#each NOMBRES_ICONO as nombre}
              <option value={nombre}>{nombre}</option>
            {/each}
          </select>
        </label>
      </div>
      <p class="v2-sub nota">
        El nombre visible se puede cambiar después. El identificador interno que
        se genera a partir de él, no: es lo que queda guardado en cada persona.
      </p>
      {#if form?.crear?.error}
        <p class="error">{form.crear.error}</p>
      {/if}
      <div class="acciones">
        <button class="v2-btn v2-btn-primary" type="submit">Crear área</button>
        <button class="v2-btn" type="button" onclick={() => (creando = false)}>Cancelar</button>
      </div>
    </form>
  {/if}

  {#if !data.areas.length}
    <EmptyState
      title="Todavía no hay áreas"
      body="Un área agrupa a quienes atienden lo mismo. El área de un ticket sale de su responsable, así que sin áreas todos los tickets caen juntos." />
  {:else}
    <div class="lista">
      {#each data.areas as area (area.nombre)}
        {@const Icono = ICONOS[area.icono]}
        <div class="fila">
          {#if editando === area.nombre}
            <form method="POST" action="?/editar" class="fila-edicion">
              <input type="hidden" name="nombre" value={area.nombre} />
              <input class="entrada" name="etiqueta" value={area.etiqueta} required />
              <input class="entrada entrada-color" type="color" name="color"
                     value={area.color || '#64748b'} />
              <select class="entrada" name="icono">
                {#each NOMBRES_ICONO as n}
                  <option value={n} selected={n === area.icono}>{n}</option>
                {/each}
              </select>
              <button class="v2-btn v2-btn-sm v2-btn-primary" type="submit">Guardar</button>
              <button class="v2-btn v2-btn-sm" type="button"
                      onclick={() => (editando = '')}>Cancelar</button>
            </form>
          {:else}
            <span class="marca" style="--area-color: {area.color || '#64748b'}">
              {#if Icono}<Icono size={16} strokeWidth={1.9} />{/if}
            </span>
            <span class="nombre">{area.etiqueta}</span>
            <code class="interno">{area.nombre}</code>
            <span class="gente" class:vacia={area.personas === 0}>
              {#if area.personas === 0}
                sin gente · no recibe tickets
              {:else}
                {area.personas} {area.personas === 1 ? 'persona' : 'personas'}
              {/if}
            </span>
            <button class="v2-btn v2-btn-sm" onclick={() => (editando = area.nombre)}>
              Editar
            </button>
            <!-- El borrado solo se ofrece si está vacía. El motor lo rechaza
                 igual con 409 --esa es la garantía--, pero ofrecer un botón
                 que siempre falla enseña a ignorar los errores. -->
            {#if area.personas === 0}
              <form method="POST" action="?/borrar" class="en-linea">
                <input type="hidden" name="nombre" value={area.nombre} />
                <button class="v2-btn v2-btn-sm" type="submit">Borrar</button>
              </form>
            {/if}
          {/if}
        </div>
      {/each}
    </div>

    <p class="v2-sub pie">
      Un área sin gente no recibe tickets: el importador no crea un caso que no
      puede asignarle a nadie. Para que una empiece a recibir, asignale alguien
      desde <a href="/agentes">Agentes</a>.
    </p>
  {/if}
</div>

<style>
  .tarjeta {
    background: var(--v2-card);
    border: 1px solid var(--v2-line, #e7e5e4);
    border-radius: 10px;
    padding: 16px var(--v2-pad);
    margin: 0 var(--v2-pad) 18px;
  }
  .titulo-seccion {
    font-size: 15px;
    margin: 0 0 12px;
  }
  .campos {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    align-items: flex-end;
  }
  .campo {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 180px;
  }
  .campo-corto {
    min-width: 70px;
  }
  .etiqueta-campo {
    font-size: 12px;
    color: var(--v2-slate);
  }
  .entrada {
    padding: 6px 9px;
    font: inherit;
    font-size: 13.5px;
    color: var(--v2-ink);
    background: var(--v2-card);
    border: 1px solid var(--v2-line, #e7e5e4);
    border-radius: 6px;
  }
  .entrada-color {
    width: 46px;
    padding: 2px;
  }
  .nota {
    font-size: 12px;
    margin: 10px 0 0;
  }
  .error {
    color: var(--v2-rust, #b91c1c);
    font-size: 13px;
    margin: 10px 0 0;
  }
  .acciones {
    display: flex;
    gap: 8px;
    margin-top: 14px;
  }
  .lista {
    padding: 0 var(--v2-pad);
  }
  .fila {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 11px 0;
    border-bottom: 1px solid var(--v2-line, #e7e5e4);
  }
  .fila-edicion {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    width: 100%;
  }
  .marca {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 30px;
    height: 30px;
    border-radius: 7px;
    color: var(--area-color);
    background: color-mix(in srgb, var(--area-color) 12%, transparent);
  }
  .nombre {
    font-weight: 550;
  }
  /* El identificador interno a la vista, y en monoespaciada: es lo que queda
     escrito en cada persona, y verlo explica por qué renombrar no lo cambia. */
  .interno {
    font-family: var(--v2-mono);
    font-size: 12px;
    color: var(--v2-slate);
  }
  .gente {
    margin-left: auto;
    font-size: 12.5px;
    color: var(--v2-slate);
  }
  .gente.vacia {
    color: var(--v2-rust, #b45309);
  }
  .en-linea {
    display: inline;
  }
  .pie {
    padding: 14px var(--v2-pad) 24px;
    font-size: 12.5px;
  }
</style>
