<script>
  /**
   * Que vende la empresa, y que canales trae la television.
   *
   * Existe por una falla medida el 08/09/2026 en el simulador: un prospecto
   * pidio telefonia fija y el agente contesto tres veces seguidas "solo
   * tenemos internet residencial y combos con television" -- sin llamar a
   * ninguna herramienta, porque no habia ninguna que se lo dijera. La
   * respuesta era correcta y no tenia fuente. Acerto porque un ISP vende
   * internet; con otro servicio, o en otro tenant, la misma frase le niega
   * al cliente algo que la empresa si vende.
   *
   * Los servicios se editan a mano (son pocos y cambian poco). La parrilla
   * se sube por Excel: son cientos de canales y nadie los va a tipear.
   *
   * Un servicio se APAGA, no se borra: vuelve, y borrarlo pierde la
   * descripcion que alguien redacto.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';
  import { enhance } from '$app/forms';
  import { Plus, Trash2, Upload, Check } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  /** @type {{ nombre: string, activo: boolean, descripcion: string }[]} */
  let servicios = $state(
    (data.servicios ?? []).map((/** @type {any} */ s) => ({
      nombre: s.nombre ?? '',
      activo: s.activo !== false,
      descripcion: s.descripcion ?? ''
    }))
  );

  let guardando = $state(false);
  let subiendo = $state(false);
  /** @type {File | null} */
  let archivo = $state(null);

  let activos = $derived(servicios.filter((s) => s.activo && s.nombre.trim()).length);

  function agregar() {
    servicios = [...servicios, { nombre: '', activo: true, descripcion: '' }];
  }

  /** @param {number} i */
  function quitar(i) {
    servicios = servicios.filter((_, j) => j !== i);
  }

  const guardandoAction = () => {
    guardando = true;
    return async (/** @type {any} */ { update }) => {
      await update({ reset: false });
      guardando = false;
    };
  };

  const subiendoAction = () => {
    subiendo = true;
    return async (/** @type {any} */ { update }) => {
      await update({ reset: false });
      subiendo = false;
    };
  };

  /** @param {Event} e */
  function elegirArchivo(e) {
    const input = /** @type {HTMLInputElement} */ (e.target);
    archivo = input.files?.[0] ?? null;
  }
</script>

<PageHeader title="Servicios y canales">
  {#snippet crumb()}<SettingsCrumb />{/snippet}
  {#snippet sub()}
    {#if data.huboRespuesta}
      {activos} servicio{activos === 1 ? '' : 's'} ofrecido{activos === 1 ? '' : 's'} ·
      {data.canales.length} canal{data.canales.length === 1 ? '' : 'es'} en la parrilla
    {:else}
      El asistente no responde
    {/if}
  {/snippet}
</PageHeader>

<div class="v2-page">
  {#if !data.huboRespuesta}
    <p class="aviso aviso-error">
      No se pudo leer la configuración del asistente. Puede estar reiniciándose por una
      actualización: probá de nuevo en un momento.
    </p>
  {/if}

  {#if form?.error}
    <p class="aviso aviso-error">{form.error}</p>
  {/if}

  <!-- ============================ SERVICIOS ============================ -->
  <section class="bloque">
    <header>
      <h2>Servicios que ofrece la empresa</h2>
      <p class="ayuda">
        El agente consulta esta lista antes de decir que algo se ofrece o que no. Si está
        vacía no adivina: avisa que va a confirmar y escala. Un servicio que dejás de
        vender <strong>apagalo</strong> en vez de borrarlo — si vuelve, conservás su
        descripción.
      </p>
    </header>

    {#if form?.guardado}
      <p class="aviso aviso-ok"><Check size={14} /> Servicios guardados.</p>
    {/if}

    <table class="tabla">
      <thead>
        <tr>
          <th class="col-activo">Se ofrece</th>
          <th>Servicio</th>
          <th>Detalle (opcional)</th>
          <th class="col-accion"></th>
        </tr>
      </thead>
      <tbody>
        {#each servicios as s, i}
          <tr class:apagado={!s.activo}>
            <td class="col-activo">
              <input
                type="checkbox"
                bind:checked={s.activo}
                disabled={!data.can_edit}
                aria-label="Se ofrece {s.nombre || 'este servicio'}"
              />
            </td>
            <td>
              <input
                class="campo"
                type="text"
                bind:value={s.nombre}
                disabled={!data.can_edit}
                placeholder="Internet residencial"
              />
            </td>
            <td>
              <input
                class="campo"
                type="text"
                bind:value={s.descripcion}
                disabled={!data.can_edit}
                placeholder="Planes de fibra óptica para el hogar"
              />
            </td>
            <td class="col-accion">
              {#if data.can_edit}
                <button
                  type="button"
                  class="v2-btn v2-btn-sm"
                  onclick={() => quitar(i)}
                  aria-label="Quitar {s.nombre || 'servicio'}"
                >
                  <Trash2 size={14} />
                </button>
              {/if}
            </td>
          </tr>
        {/each}
        {#if servicios.length === 0}
          <tr>
            <td colspan="4" class="vacio">
              Todavía no hay servicios cargados. Mientras esta lista esté vacía, el agente
              no va a afirmar qué se vende: lo va a escalar.
            </td>
          </tr>
        {/if}
      </tbody>
    </table>

    {#if data.can_edit}
      <div class="acciones">
        <button type="button" class="v2-btn v2-btn-sm" onclick={agregar}>
          <Plus size={14} /> Agregar servicio
        </button>

        <form method="POST" action="?/guardarServicios" use:enhance={guardandoAction}>
          <input type="hidden" name="datos" value={JSON.stringify(servicios)} />
          <button type="submit" class="v2-btn v2-btn-primary v2-btn-sm" disabled={guardando}>
            {guardando ? 'Guardando…' : 'Guardar servicios'}
          </button>
        </form>
      </div>
    {/if}
  </section>

  <!-- ============================ PARRILLA ============================ -->
  <section class="bloque">
    <header>
      <h2>Parrilla de canales</h2>
      <p class="ayuda">
        Una sola parrilla para todos los planes con televisión. Subí un Excel
        (<code>.xlsx</code>) con <strong>un canal por fila en la primera columna</strong> —
        sin encabezado ni nombre de hoja especial. Reemplaza la parrilla entera: es lo que
        diga el archivo. El agente reconoce lo que escribe el cliente aunque venga en
        minúsculas, sin tildes o incompleto («discovery» encuentra «DISCOVERY H&amp;H»).
      </p>
    </header>

    {#if form?.subido}
      <p class="aviso aviso-ok">
        <Check size={14} />
        Se cargaron {form.total} canal{form.total === 1 ? '' : 'es'}.
        {#if form.descartados?.length}
          Se descartaron {form.descartados.length} por estar repetidos:
          <span class="descartados">{form.descartados.join(', ')}</span>
        {/if}
      </p>
    {/if}

    {#if data.can_edit}
      <form
        method="POST"
        action="?/subirParrilla"
        enctype="multipart/form-data"
        use:enhance={subiendoAction}
        class="subida"
      >
        <input
          type="file"
          name="archivo"
          accept=".xlsx"
          onchange={elegirArchivo}
          aria-label="Archivo Excel con la parrilla"
        />
        <button
          type="submit"
          class="v2-btn v2-btn-primary v2-btn-sm"
          disabled={subiendo || !archivo}
        >
          <Upload size={14} />
          {subiendo ? 'Cargando…' : 'Cargar parrilla'}
        </button>
      </form>
    {/if}

    <h3 class="sub">
      {#if data.canales.length}
        Canales cargados ({data.canales.length})
      {:else}
        Todavía no hay parrilla cargada
      {/if}
    </h3>

    {#if data.canales.length}
      <ul class="canales">
        {#each data.canales as c}
          <li>{c}</li>
        {/each}
      </ul>
    {:else}
      <p class="vacio">
        Sin parrilla, el agente no responde por canales: dice que va a confirmar y escala.
        Es a propósito — inventar el nombre de un canal es mucho más fácil de creer que
        inventar un servicio entero.
      </p>
    {/if}
  </section>
</div>

<style>
  .v2-page {
    display: flex;
    flex-direction: column;
    gap: 24px;
    padding: 20px 24px 48px;
    max-width: 980px;
  }
  .bloque {
    display: flex;
    flex-direction: column;
    gap: 14px;
    padding: 20px;
    border: 1px solid var(--v2-border, #e3e6e4);
    border-radius: 8px;
    background: var(--v2-surface, #fff);
  }
  .bloque header {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  h2 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
  }
  h3.sub {
    margin: 6px 0 0;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--v2-text-muted, #6b7671);
  }
  .ayuda {
    margin: 0;
    font-size: 13px;
    line-height: 1.55;
    color: var(--v2-text-muted, #6b7671);
    max-width: 72ch;
  }
  code {
    font-family: ui-monospace, monospace;
    font-size: 0.92em;
    background: var(--v2-surface-2, #f1f3f2);
    padding: 1px 4px;
    border-radius: 3px;
  }
  .tabla {
    width: 100%;
    border-collapse: collapse;
    font-size: 13.5px;
  }
  .tabla th {
    text-align: left;
    font-size: 11px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    color: var(--v2-text-muted, #6b7671);
    font-weight: 600;
    padding: 8px 10px;
    border-bottom: 1px solid var(--v2-border, #e3e6e4);
  }
  .tabla td {
    padding: 7px 10px;
    border-bottom: 1px solid var(--v2-border-soft, #eff1f0);
    vertical-align: middle;
  }
  .tabla tr.apagado .campo {
    opacity: 0.55;
  }
  .col-activo {
    width: 82px;
  }
  .col-accion {
    width: 48px;
    text-align: right;
  }
  .campo {
    width: 100%;
    padding: 6px 8px;
    border: 1px solid var(--v2-border, #e3e6e4);
    border-radius: 5px;
    font: inherit;
    background: var(--v2-surface, #fff);
    color: inherit;
  }
  .campo:disabled {
    background: var(--v2-surface-2, #f1f3f2);
  }
  .acciones {
    display: flex;
    gap: 10px;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
  }
  .subida {
    display: flex;
    gap: 10px;
    align-items: center;
    flex-wrap: wrap;
  }
  .canales {
    margin: 0;
    padding: 0;
    list-style: none;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(190px, 1fr));
    gap: 4px 14px;
    font-size: 13px;
  }
  .canales li {
    padding: 3px 0;
    border-bottom: 1px solid var(--v2-border-soft, #eff1f0);
  }
  .vacio {
    margin: 0;
    font-size: 13px;
    color: var(--v2-text-muted, #6b7671);
    max-width: 72ch;
    line-height: 1.55;
  }
  .aviso {
    margin: 0;
    padding: 9px 12px;
    border-radius: 6px;
    font-size: 13px;
    display: flex;
    align-items: center;
    gap: 7px;
    flex-wrap: wrap;
  }
  .aviso-ok {
    background: var(--v2-ok-soft, #e4f0e9);
    color: var(--v2-ok, #2c6e49);
  }
  .aviso-error {
    background: var(--v2-danger-soft, #f7e2de);
    color: var(--v2-danger, #a03323);
  }
  .descartados {
    font-family: ui-monospace, monospace;
    font-size: 0.92em;
  }
</style>
