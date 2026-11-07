<script>
  /**
   * Pagos: el link con el que un cliente puede pagar.
   *
   * POR QUE ESTA PANTALLA EXISTE
   * ----------------------------
   * El link de pago cambia de una empresa a otra. Si solo se pudiera cargar por
   * API, sería justo lo que la regla multi-empresa del proyecto prohíbe: un
   * dato que "solo un desarrollador sabe editar". Acá cada empresa pega el suyo.
   *
   * QUE PASA CON EL LINK
   * --------------------
   * No va en el prompt de ningún agente. El asistente lo recibe de la
   * herramienta de cuenta, y solo si la persona ya está verificada y tiene algo
   * por pagar: a quien no debe nada no se le da, y un valor mal escrito tampoco.
   *
   * VACIO NO ES UN ERROR
   * --------------------
   * Sin link cargado el asistente dice cuánto se debe y no ofrece dónde pagar.
   * Es el estado por defecto, no una falla: no se marca como advertencia.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';
  import StatCard from '$lib/v2/components/StatCard.svelte';
  import SettingsFormPanel from '$lib/v2/components/SettingsFormPanel.svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let editando = $state(false);

  let a = $derived(data.ajustes);
  const tieneLink = $derived(!!a && a.link !== '');
  /* El sitio, sin el camino: lo que se muestra en la tarjeta. El link completo
     puede llevar parámetros y no cabe; el campo de edición lo enseña entero. */
  const sitio = $derived.by(() => {
    if (!a || !a.link) return '';
    try {
      return new URL(a.link).hostname;
    } catch {
      return a.link;
    }
  });
</script>

<PageHeader title="Pagos">
  {#snippet crumb()}<SettingsCrumb />{/snippet}
  {#snippet sub()}
    {#if !a}
      El asistente no respondió
    {:else if tieneLink}
      Link de pago cargado · {sitio}
    {:else}
      Sin link de pago
    {/if}
  {/snippet}
  {#snippet actions()}
    {#if data.can_edit && a && !editando}
      <button class="v2-btn v2-btn-primary" onclick={() => (editando = true)}>
        {tieneLink ? 'Cambiar el link' : 'Cargar el link'}
      </button>
    {/if}
  {/snippet}
</PageHeader>

{#if !a}
  <!-- El motor es otro servicio: que no conteste no lo arregla el operador desde
       acá, así que se dice qué pasa y no se ofrece un formulario que no podría
       guardar nada. -->
  <div class="v2-scroll">
    <div class="v2-pad" style="padding-top:16px">
      <div class="v2-card" style="padding:16px">
        <p class="v2-sub" style="margin:0 0 6px">Sin conexión con el asistente</p>
        <p class="v2-hint" style="margin:0">
          El link de pago vive en la configuración del asistente, que es otro
          servicio. No se pudo leer: o no está desplegado, o no está respondiendo.
          Lo que ya tenga cargado sigue vigente — esta pantalla no lo borró.
        </p>
      </div>
    </div>
  </div>
{:else}
  <div class="v2-pad" style="padding-top:16px;flex:none">
    <div class="v2-stats">
      <StatCard
        label="Link de pago"
        value={tieneLink ? sitio : 'Sin cargar'}
        tone={tieneLink ? 'ink' : 'slate'}
        detail={tieneLink
          ? 'El asistente se lo ofrece a quien debe una factura'
          : 'El asistente dice cuánto se debe, sin ofrecer dónde pagar'}
      />
    </div>
  </div>

  <div class="v2-scroll">
    <div class="v2-pad" style="padding-bottom:32px">
      {#if form?.guardado && !editando}
        <p class="v2-hint" role="status" style="margin:0 0 12px">Guardado.</p>
      {/if}

      {#if editando}
        <SettingsFormPanel
          title="Link de pago"
          action="?/guardar"
          error={form?.guardar?.error}
          submitLabel="Guardar"
          oncancel={() => (editando = false)}
          ondone={() => (editando = false)}
        >
          {#snippet fields()}
            <div class="v2-field">
              <label for="f-link">Dirección donde el cliente puede pagar</label>
              <input
                id="f-link"
                class="v2-input"
                type="url"
                name="link_de_pago"
                placeholder="https://pagos.miempresa.co"
                maxlength="500"
                value={a.link}
              />
              <p class="v2-hint">
                Tiene que empezar con https://. El asistente se lo da solo a un
                cliente ya verificado que tenga una factura pendiente. Dejalo
                vacío para quitarlo.
              </p>
            </div>
          {/snippet}
        </SettingsFormPanel>
      {:else}
        <div class="v2-card" style="padding:16px">
          <p class="v2-sub" style="margin:0 0 6px">Cómo lo usa el asistente</p>
          <p class="v2-hint" style="margin:0">
            Cuando un cliente verificado pregunta cuánto debe y tiene facturas
            pendientes, el asistente le dice el monto y, si hay un link cargado,
            se lo ofrece para pagar. A quien no debe nada no se le da. El link no
            está escrito en ningún mensaje del agente: se puede cambiar o quitar
            acá, sin tocar nada más.
          </p>
        </div>
      {/if}
    </div>
  </div>
{/if}
