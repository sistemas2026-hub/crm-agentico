<script>
  /**
   * Avisos de campo.
   *
   * QUÉ DECIDE ESTA PANTALLA Y QUÉ NO
   * ---------------------------------
   * No decide nada del negocio. Los tipos de canal los dice el backend —el día
   * que se agregue uno aparece solo— y el permiso también: `puedeConfigurar`
   * llega resuelto y acá solo se dibuja o no.
   *
   * Lo único propio es la ayuda: qué pegar y dónde encontrarlo. Eso es lo que
   * convierte «una fila que carga un programador» en «configuración que hace la
   * empresa», que era el punto.
   */
  import { enhance } from '$app/forms';

  let { data, form } = $props();

  /** El tipo elegido en el formulario de alta. Cambia la ayuda y el placeholder. */
  let tipo = $state('google_chat');

  const esCorreo = $derived(tipo === 'correo');

  /** Dónde se consigue cada cosa. Sin esto, «pegá el webhook» no ayuda a nadie. */
  const AYUDA = {
    google_chat:
      'En el espacio de Chat: flecha junto al nombre → Apps e integraciones → Webhooks → Agregar webhook. Después, tres puntos → Copiar vínculo.',
    slack:
      'En api.slack.com/apps → tu app → Incoming Webhooks → Add New Webhook to Workspace.',
    teams:
      'En el canal de Teams: … → Workflows → «Publicar en un canal cuando se reciba una solicitud de webhook». Copiá la URL que genera.',
    discord: 'En el canal: Editar canal → Integraciones → Webhooks → Nuevo webhook.',
    webhook: 'Cualquier URL que acepte un POST con un JSON de la forma {"text": "…"}.',
    correo: 'La dirección a la que querés que llegue el aviso.'
  };
</script>

<svelte:head><title>Avisos de campo · Dexter</title></svelte:head>

<div class="flex flex-col gap-space-lg max-w-3xl">
  <header class="flex flex-col gap-space-xs">
    <h1 class="font-headline-lg text-headline-lg text-on-surface">Avisos de campo</h1>
    <p class="font-body-md text-body-md text-on-surface-variant">
      Dónde quiere tu empresa que le avisemos cuando un supervisor devuelve un
      trabajo. El técnico se entera en el momento y no cuando vuelve a abrir la app.
    </p>
  </header>

  {#if data.error}
    <div class="bg-error-container p-space-md rounded font-body-sm text-body-sm text-on-error-container">
      No se pudo leer la configuración. Lo que ves abajo puede estar incompleto.
    </div>
  {/if}

  {#if form?.error}
    <div class="bg-error-container p-space-md rounded font-body-sm text-body-sm text-on-error-container">
      {form.error}
    </div>
  {/if}
  {#if form?.probado}
    <div class="bg-primary-fixed/40 p-space-md rounded font-body-sm text-body-sm text-on-surface">
      ✅ {form.probado}
    </div>
  {/if}
  {#if form?.probado_mal}
    <!-- NO es un error de la página: es el resultado de la prueba, que es
         justamente lo que se quería averiguar. -->
    <div class="bg-error-container p-space-md rounded font-body-sm text-body-sm text-on-error-container">
      No llegó: {form.probado_mal} Revisá que la URL siga siendo válida.
    </div>
  {/if}

  <!-- ------------------------------------------------------------------ -->
  <!-- Los canales cargados                                                -->
  <!-- ------------------------------------------------------------------ -->
  <section class="flex flex-col gap-space-sm">
    <h2 class="font-title-md text-title-md text-on-surface">Canales</h2>

    {#if data.canales.length === 0}
      <p class="font-body-sm text-body-sm text-on-surface-variant">
        Todavía no hay ninguno. Mientras tanto nadie recibe avisos — y eso es un
        estado válido, no un error.
      </p>
    {:else}
      <ul class="flex flex-col gap-space-sm">
        {#each data.canales as c (c.id)}
          <li class="bg-surface-container-lowest p-space-md rounded shadow-sm flex flex-col gap-space-xs">
            <div class="flex items-center gap-space-sm flex-wrap">
              <span class="font-title-sm text-title-sm text-on-surface">{c.tipo_nombre}</span>
              {#if c.nombre}
                <span class="font-body-sm text-body-sm text-on-surface-variant">· {c.nombre}</span>
              {/if}
              {#if !c.activo}
                <span class="font-label-badge text-label-badge px-2 py-0.5 rounded bg-surface-container-high text-on-surface-variant">
                  APAGADO
                </span>
              {/if}
            </div>

            <!-- La pista y no el valor: en un webhook esa URL es la credencial. -->
            <code class="font-label-code text-label-code text-on-surface-variant">{c.pista}</code>

            {#if c.probado_en}
              <span class="font-body-sm text-body-sm text-on-surface-variant">
                {c.ultimo_error
                  ? `Última prueba: no llegó — ${c.ultimo_error}`
                  : 'Última prueba: llegó bien'}
              </span>
            {:else}
              <span class="font-body-sm text-body-sm text-secondary">
                Sin probar. Probalo ahora y sabés si sirve, en vez de enterarte
                el día que haya una devolución.
              </span>
            {/if}

            {#if data.puedeConfigurar}
              <div class="flex gap-space-sm flex-wrap pt-space-xs">
                <form method="POST" action="?/probar" use:enhance>
                  <input type="hidden" name="id" value={c.id} />
                  <button class="h-9 px-3 rounded bg-secondary text-on-secondary font-body-sm text-body-sm">
                    Probar
                  </button>
                </form>
                <form method="POST" action="?/apagar" use:enhance>
                  <input type="hidden" name="id" value={c.id} />
                  <input type="hidden" name="activo" value={(!c.activo).toString()} />
                  <button class="h-9 px-3 rounded bg-surface-container-high text-on-surface font-body-sm text-body-sm">
                    {c.activo ? 'Apagar' : 'Encender'}
                  </button>
                </form>
                <form method="POST" action="?/borrar" use:enhance>
                  <input type="hidden" name="id" value={c.id} />
                  <button class="h-9 px-3 rounded text-error font-body-sm text-body-sm">
                    Borrar
                  </button>
                </form>
              </div>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
  </section>

  <!-- ------------------------------------------------------------------ -->
  <!-- Agregar uno                                                         -->
  <!-- ------------------------------------------------------------------ -->
  {#if data.puedeConfigurar}
    <section class="flex flex-col gap-space-sm">
      <h2 class="font-title-md text-title-md text-on-surface">Agregar un canal</h2>

      <form method="POST" action="?/agregar" use:enhance class="flex flex-col gap-space-md bg-surface-container-lowest p-space-md rounded shadow-sm">
        <div class="flex flex-col gap-space-xs">
          <label for="tipo" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
            Por dónde
          </label>
          <select
            id="tipo"
            name="tipo"
            bind:value={tipo}
            class="w-full h-10 px-3 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm"
          >
            <!-- Los tipos los dice el BACKEND. Si mañana se agrega uno, aparece
                 acá sin tocar este archivo. -->
            {#each data.tipos as t (t.valor)}
              <option value={t.valor}>{t.nombre}</option>
            {/each}
          </select>
          <span class="font-body-sm text-body-sm text-secondary">{AYUDA[tipo]}</span>
        </div>

        <div class="flex flex-col gap-space-xs">
          <label for="destino" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
            {esCorreo ? 'Dirección de correo' : 'URL del webhook'}
            <span class="text-error">*</span>
          </label>
          <input
            id="destino"
            name="destino"
            required
            placeholder={esCorreo ? 'coordinacion@empresa.co' : 'https://…'}
            class="w-full h-10 px-3 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm"
          />
          {#if !esCorreo}
            <span class="font-body-sm text-body-sm text-secondary">
              Tratala como una contraseña: cualquiera con esa URL puede publicar
              en el espacio. Una vez guardada no se vuelve a mostrar.
            </span>
          {/if}
        </div>

        <div class="flex flex-col gap-space-xs">
          <label for="nombre" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
            Cómo lo llamás <span class="text-secondary font-normal opacity-75">(opcional)</span>
          </label>
          <input
            id="nombre"
            name="nombre"
            placeholder="Cuadrilla norte"
            class="w-full h-10 px-3 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm"
          />
        </div>

        <button class="h-10 px-4 rounded bg-primary text-on-primary font-body-md text-body-md self-start">
          Agregar
        </button>
      </form>
    </section>

    <!-- ---------------------------------------------------------------- -->
    <!-- El dominio de los enlaces                                         -->
    <!-- ---------------------------------------------------------------- -->
    <section class="flex flex-col gap-space-sm">
      <h2 class="font-title-md text-title-md text-on-surface">Enlaces</h2>
      <p class="font-body-sm text-body-sm text-on-surface-variant">
        De dónde cuelgan los enlaces que van en el aviso. Es de la empresa y no
        de un canal: si lo dejás vacío el aviso sale igual, sin enlace.
      </p>

      <form method="POST" action="?/dominio" use:enhance class="flex gap-space-sm items-end bg-surface-container-lowest p-space-md rounded shadow-sm">
        <div class="flex flex-col gap-space-xs flex-1">
          <label for="dominio" class="font-table-header text-table-header text-on-surface-variant uppercase tracking-wider">
            Dominio
          </label>
          <input
            id="dominio"
            name="url_base_app"
            value={data.urlBaseApp}
            placeholder="https://crm.empresa.co"
            class="w-full h-10 px-3 bg-surface-container-lowest text-on-surface font-body-md text-body-md rounded shadow-sm"
          />
        </div>
        <button class="h-10 px-4 rounded bg-primary text-on-primary font-body-md text-body-md">
          Guardar
        </button>
      </form>
    </section>
  {:else}
    <p class="font-body-sm text-body-sm text-on-surface-variant">
      Solo gestión puede cambiar esto. Lo de arriba es para consulta.
    </p>
  {/if}
</div>
