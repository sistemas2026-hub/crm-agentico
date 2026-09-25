<script>
  /**
   * Cómo se sintoniza cada televisor.
   *
   * Desde el 10/09/2026 este catálogo es la FUENTE OFICIAL de esas
   * instrucciones. Antes el paso a paso vivía en el prompt del rol de soporte
   * y, copiado, en dos descripciones de herramienta — para algo que cambia por
   * marca de televisor y que nadie podía corregir sin un desarrollador.
   *
   * LAS DOS CONEXIONES REALES, que es lo que decide la guía:
   *
   *   directo   fibra → ONU → CATV → coaxial → entrada del TV.
   *             La señal es digital y la sintonía depende de la MARCA.
   *
   *   TDT       fibra → ONU → CATV → coaxial → TDT → HDMI o AV.
   *             El coaxial no llega al televisor. Quien sintoniza es la
   *             cajita, así que la marca del TV no cambia nada — por eso hay
   *             UNA sola guía de TDT y el schema no deja crear otras.
   *
   * ESTA PANTALLA NO VALIDA LAS REGLAS. Las hace cumplir el motor al guardar
   * (`GuiaTV` y `TenantConfig` en `nucleo/config/schema.py`), y reescribirlas
   * en JavaScript daría dos lugares donde corregirlas y uno donde olvidarse.
   *
   * Lo único que hace acá es volver INALCANZABLE el error más fácil de
   * cometer: con TDT el campo de marca se deshabilita y se limpia. Eso no es
   * una validación duplicada — es no ofrecer el error. Los otros dos casos los
   * frena el motor, y su mensaje explica además por qué la regla existe.
   *
   * Una guía se APAGA, no se borra: una que se retira porque quedó vieja
   * vuelve corregida, y borrarla pierde el texto que alguien redactó.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';
  import { enhance } from '$app/forms';
  import { Plus, Trash2, AlertTriangle, Tv, Box } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  /** @type {{ marca: string, tipo_conexion: string, instrucciones: string, url_video: string, activa: boolean, observaciones: string }[]} */
  let guias = $state(
    (data.guias ?? []).map((/** @type {any} */ g) => ({
      marca: g.marca ?? '',
      tipo_conexion: g.tipo_conexion ?? 'directo',
      instrucciones: g.instrucciones ?? '',
      url_video: g.url_video ?? '',
      activa: g.activa !== false,
      observaciones: g.observaciones ?? ''
    }))
  );

  let guardando = $state(false);
  let filtro = $state('');

  const llano = (/** @type {string} */ t) =>
    (t ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();

  let visibles = $derived(
    guias
      .map((g, i) => ({ g, i }))
      .filter(({ g }) => !filtro.trim() || llano(g.marca).includes(llano(filtro)))
  );

  // Las dos guías que el flujo siempre busca como respaldo. Se muestran arriba
  // y con nombre propio: sin ellas, una marca sin guía específica deja al
  // agente sin nada que entregar.
  let general = $derived(
    guias.find((g) => g.tipo_conexion === 'directo' && !g.marca.trim() && g.activa)
  );
  let tdt = $derived(guias.find((g) => g.tipo_conexion === 'tdt' && g.activa));
  let activas = $derived(guias.filter((g) => g.activa).length);

  // NO SE VALIDAN LAS REGLAS ACA, A PROPOSITO.
  //
  // «TDT sin marca», «activa con instrucciones» y «una sola activa por marca»
  // viven en `GuiaTV` y `TenantConfig` (nucleo/config/schema.py). Reescribirlas
  // en JavaScript daria dos lugares donde corregirlas y uno donde olvidarse —
  // y la copia del navegador se queda vieja sin que nada falle.
  //
  // Lo que si hace esta pantalla es volver INALCANZABLE el caso invalido más
  // fácil de cometer: con TDT el campo de marca se deshabilita y se limpia.
  // Eso no es una validación duplicada, es no ofrecer el error.
  //
  // Los otros dos los frena el motor al guardar, y su mensaje explica además
  // por qué existe la regla. Ese texto se muestra tal cual.

  function agregar() {
    guias = [
      ...guias,
      { marca: '', tipo_conexion: 'directo', instrucciones: '', url_video: '', activa: true, observaciones: '' }
    ];
  }

  /** @param {number} i */
  function quitar(i) {
    guias = guias.filter((_, n) => n !== i);
  }

  /** @param {number} i */
  function cambioTipo(i) {
    // Con TDT la marca no interviene: se limpia para que no quede escrita y
    // el guardado falle por algo que la persona ya no ve en pantalla.
    if (guias[i].tipo_conexion === 'tdt') guias[i].marca = '';
  }

  const guardandoAction = () => {
    guardando = true;
    return async (/** @type {any} */ { update }) => {
      await update({ reset: false });
      guardando = false;
    };
  };
</script>

<PageHeader title="Guías de sintonización">
  {#snippet crumb()}<SettingsCrumb />{/snippet}
  {#snippet sub()}
    {#if data.huboRespuesta}
      {activas} guía{activas === 1 ? '' : 's'} activa{activas === 1 ? '' : 's'} ·
      {general ? 'con' : 'SIN'} guía general · {tdt ? 'con' : 'SIN'} guía de TDT
    {:else}
      El asistente no responde
    {/if}
  {/snippet}
</PageHeader>

<!--
  'v2-scroll' NO ES DECORACION: es el unico contenedor que hace scroll.

  El shell es 'height:100vh; overflow:hidden' y '.v2-main' tambien recorta
  (lib/v2/styles/v2.css). Quien scrollea es '.v2-scroll' -- 'flex:1;
  min-height:0; overflow-y:auto' -- y lo usan las 16 pantallas de /settings.

  Esta usaba 'v2-page', una clase que NO existe globalmente: solo esta
  definida DENTRO de settings/oferta, y Svelte aisla los estilos por
  componente, asi que aca no aplicaba nada. Con el catalogo vacio no se
  notaba; con las 19 guias cargadas, todo lo que pasaba del alto de la
  pantalla quedaba recortado y no habia forma de llegar a las de abajo.
  Reportado el 10/09/2026, apenas se cargaron las guias.
-->
<div class="v2-scroll">
  <div class="v2-pad" style="padding-top:16px;padding-bottom:48px;max-width:980px">
  {#if !data.huboRespuesta}
    <p class="aviso aviso-error">
      No se pudo leer la configuración del asistente. Puede estar reiniciándose por una
      actualización: probá de nuevo en un momento.
    </p>
  {/if}

  <p class="intro">
    Lo que el agente le dice al cliente para sintonizar. Si una marca no tiene guía
    propia, usa la <strong>general</strong>. Si el cable pasa por una cajita TDT, usa
    siempre la <strong>de TDT</strong> — la marca del televisor no interviene ahí.
  </p>

  <!-- Las dos de respaldo, primero: son las que sostienen todo lo demás. -->
  <div class="respaldo">
    <div class="pieza" class:falta={!general}>
      <Tv size={16} />
      <div>
        <div class="rotulo">Guía general — TV directo</div>
        <div class="valor">
          {general ? 'Cargada' : 'Falta: sin ella, una marca sin guía propia deja al agente sin nada que entregar'}
        </div>
      </div>
    </div>
    <div class="pieza" class:falta={!tdt}>
      <Box size={16} />
      <div>
        <div class="rotulo">Guía de TDT — única</div>
        <div class="valor">
          {tdt ? 'Cargada' : 'Falta: sin ella, el agente no puede orientar a quien tiene cajita'}
        </div>
      </div>
    </div>
  </div>

  {#if form?.error}
    <p class="aviso aviso-error"><AlertTriangle size={15} /> {form.error}</p>
  {:else if form?.guardado}
    <p class="aviso aviso-ok">Guías guardadas.</p>
  {/if}

  <div class="barra">
    <input class="v2-input" placeholder="Filtrar por marca…" bind:value={filtro} />
    {#if data.can_edit}
      <button type="button" class="v2-btn v2-btn-sm" onclick={agregar}>
        <Plus size={14} /> Agregar guía
      </button>
    {/if}
  </div>

  <form method="POST" action="?/guardar" use:enhance={guardandoAction}>
    <input type="hidden" name="datos" value={JSON.stringify(guias)} />

    {#if guias.length === 0}
      <p class="vacio">Todavía no hay ninguna guía cargada.</p>
    {/if}

    {#each visibles as { g, i } (i)}
      <div class="guia" class:apagada={!g.activa}>
        <div class="fila">
          <label class="campo tipo">
            Conexión
            <select class="v2-input" bind:value={g.tipo_conexion}
                    onchange={() => cambioTipo(i)} disabled={!data.can_edit}>
              {#each data.tipos as t}
                <option value={t}>{t === 'tdt' ? 'TV + TDT' : 'TV directo'}</option>
              {/each}
            </select>
          </label>

          <label class="campo marca">
            Marca
            <input class="v2-input" bind:value={g.marca} disabled={!data.can_edit || g.tipo_conexion === 'tdt'}
                   placeholder={g.tipo_conexion === 'tdt' ? 'La de TDT no lleva marca' : 'Vacío = guía general'} />
          </label>

          <label class="campo activa">
            <input type="checkbox" bind:checked={g.activa} disabled={!data.can_edit} />
            Activa
          </label>

          {#if data.can_edit}
            <button type="button" class="quitar" onclick={() => quitar(i)} aria-label="Quitar guía">
              <Trash2 size={15} />
            </button>
          {/if}
        </div>

        <label class="campo">
          Instrucciones — se le leen al cliente tal cual
          <textarea class="v2-input" rows="3" bind:value={g.instrucciones} disabled={!data.can_edit}
                    placeholder="Ej: Entra a Menú, Canales, Búsqueda automática, y elige ANTENA."></textarea>
        </label>

        <div class="fila">
          <label class="campo">
            URL del video (opcional)
            <input class="v2-input" bind:value={g.url_video} disabled={!data.can_edit}
                   placeholder="https://…" />
          </label>
          <label class="campo">
            Observaciones — internas, no se le dicen al cliente
            <input class="v2-input" bind:value={g.observaciones} disabled={!data.can_edit}
                   placeholder="Ej: confirmado con el técnico" />
          </label>
        </div>
      </div>
    {/each}

    {#if data.can_edit}
      <button type="submit" class="v2-btn v2-btn-primary" disabled={guardando}>
        {guardando ? 'Guardando…' : 'Guardar guías'}
      </button>
    {/if}
    </form>
  </div>
</div>

<style>
  .intro { color: #5a6473; font-size: .9rem; max-width: 62ch; line-height: 1.5; }

  .respaldo { display: flex; gap: 12px; flex-wrap: wrap; margin: 14px 0; }
  .pieza {
    display: flex; gap: 9px; align-items: flex-start; flex: 1 1 260px;
    border: 1px solid #cfd6e0; border-radius: 8px; padding: 10px 12px; background: #fbfcfd;
  }
  .pieza.falta { border-color: #b45309; background: #fffbeb; }
  .rotulo { font-size: .72rem; text-transform: uppercase; letter-spacing: .05em; color: #6b7280; }
  .valor { font-size: .88rem; color: #23303c; }

  .barra { display: flex; gap: 9px; align-items: center; margin: 14px 0; }
  .barra :global(input) { max-width: 260px; }

  .guia {
    display: flex; flex-direction: column; gap: 10px;
    border: 1px solid #e3e8ee; border-radius: 9px; padding: 12px; margin-bottom: 11px;
  }
  .guia.apagada { opacity: .62; background: #fafbfc; }
  .fila { display: flex; gap: 11px; flex-wrap: wrap; align-items: flex-end; }
  .campo { display: flex; flex-direction: column; gap: 4px; flex: 1 1 190px;
           font-size: .78rem; color: #5a6473; }
  .campo.tipo { flex: 0 0 150px; }
  .campo.marca { flex: 1 1 200px; }
  .campo.activa { flex: 0 0 auto; flex-direction: row; align-items: center; gap: 6px;
                  font-size: .85rem; padding-bottom: 7px; }
  .quitar { background: none; border: 0; cursor: pointer; color: #8a2a20; padding: 6px; }

  .aviso { display: flex; gap: 8px; align-items: flex-start; font-size: .86rem;
           padding: 9px 12px; border-radius: 8px; margin: 11px 0; }
  .aviso-error { background: #fdf2f0; color: #8a2a20; border-left: 3px solid #8a2a20; }
  .aviso-ok { background: #f0f9f4; color: #1f7a4d; border-left: 3px solid #1f7a4d; }
  .aviso ul { margin: 6px 0 0; padding-left: 18px; }
  .vacio { color: #6b7280; font-size: .88rem; }
</style>
