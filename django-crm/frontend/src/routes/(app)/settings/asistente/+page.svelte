<script>
  /**
   * Como se presenta y como escribe el asistente.
   *
   * Es la primera parte de la configuracion del asistente que el cliente
   * maneja solo, y esta separada de /agentes a proposito: ahi se decide QUE
   * DATOS ve cada rol, que es superficie de seguridad y se revisa; aca no se
   * puede tocar ni un permiso. Lo peor que puede pasar es que el asistente
   * hable raro.
   *
   * El panel de la derecha dice justamente eso. Una pantalla de configuracion
   * que no aclara su alcance hace que la gente no toque nada por miedo, o que
   * toque creyendo que cambia mas de lo que cambia.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import SettingsFormPanel from '$lib/v2/components/SettingsFormPanel.svelte';
  import { MessageSquare, ShieldCheck } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let editing = $state(false);
  let editingEmpresa = $state(false);
  let editingPlazo = $state(false);

  let p = $derived(data.config?.persona);
  let identidad = $derived(data.config?.identidad);
  let plazoVisitaTecnica = $derived(data.config?.plazo_visita_tecnica);

  const TONOS = [
    ['cercano', 'Cercano', 'Trata de usted pero sin formalismos. El que viene por defecto.'],
    ['formal', 'Formal', 'Mas distante y cuidado. Para un cliente que espera trato institucional.'],
    ['tecnico', 'Tecnico', 'Directo y sin rodeos. Pensado para personal de campo.']
  ];

  const LARGOS = [
    ['breve', 'Breve', 'Dos o tres frases. Es lo que funciona por WhatsApp.'],
    ['media', 'Media', 'Un parrafo, con algo de contexto.'],
    ['extensa', 'Extensa', 'Explica el porque. Cuesta mas de leer en el celular.']
  ];

  let tonoLabel = $derived(TONOS.find((t) => t[0] === p?.tono)?.[1] ?? p?.tono);
  let largoLabel = $derived(
    LARGOS.find((l) => l[0] === p?.longitud_respuesta)?.[1] ?? p?.longitud_respuesta
  );
</script>

<PageHeader title="Personalidad del asistente">
  {#snippet crumb()}<SettingsCrumb />{/snippet}
  {#snippet sub()}
    {#if p}
      Se llama {p.nombre_asistente} · habla en tono {tonoLabel?.toLowerCase()} · respuestas
      {largoLabel?.toLowerCase()}
    {:else}
      El asistente no responde
    {/if}
  {/snippet}
  {#snippet actions()}
    {#if p && data.can_edit && !editing}
      <button class="v2-btn v2-btn-primary" onclick={() => (editing = true)}>
        Editar personalidad
      </button>
    {/if}
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <div class="v2-pad" style="padding-top:16px;padding-bottom:32px">
    {#if !p}
      <!--
        Ni un formulario vacio ni una pantalla en blanco. Si el motor no
        contesta no hay valores que mostrar, y ofrecer campos para llenar
        terminaria en un guardado que falla despues de escribir todo.
      -->
      <div class="v2-card" style="padding:20px 22px;max-width:60ch">
        <b style="font-size:13px">No se pudo leer la configuracion del asistente</b>
        <p class="v2-sub" style="font-size:12.5px;margin:8px 0 0;line-height:1.5">
          O no hay un asistente desplegado para esta organizacion, o el motor no esta respondiendo.
          Los agentes y sus permisos se ven en
          <a href="/agentes" style="color:inherit">Agentes</a>; si esa pantalla tampoco carga, es el
          motor.
        </p>
      </div>
    {:else}
      {#if editing}
        <SettingsFormPanel
          title="Personalidad del asistente"
          action="?/update"
          error={form?.update?.error}
          submitLabel="Guardar personalidad"
          oncancel={() => (editing = false)}
          ondone={() => (editing = false)}
        >
          {#snippet fields()}
            <div class="v2-field">
              <label for="f-nombre">Como se llama</label>
              <input
                id="f-nombre"
                class="v2-input"
                type="text"
                name="nombre_asistente"
                maxlength="60"
                required
                value={p.nombre_asistente}
              />
              <p class="v2-hint">Con este nombre se presenta al abrir una conversacion.</p>
            </div>

            <div class="v2-field">
              <label for="f-tono">Tono</label>
              <select id="f-tono" class="v2-input" name="tono">
                {#each TONOS as [valor, etiqueta] (valor)}
                  <option value={valor} selected={valor === p.tono}>{etiqueta}</option>
                {/each}
              </select>
              <p class="v2-hint">{TONOS.find((t) => t[0] === p.tono)?.[2]}</p>
            </div>

            <div class="v2-field">
              <label for="f-largo">Largo de las respuestas</label>
              <select id="f-largo" class="v2-input" name="longitud_respuesta">
                {#each LARGOS as [valor, etiqueta] (valor)}
                  <option value={valor} selected={valor === p.longitud_respuesta}>{etiqueta}</option
                  >
                {/each}
              </select>
              <p class="v2-hint">{LARGOS.find((l) => l[0] === p.longitud_respuesta)?.[2]}</p>
            </div>

            <div class="v2-field v2-sfp-wide">
              <label for="f-instrucciones">Instrucciones adicionales</label>
              <textarea
                id="f-instrucciones"
                class="v2-input"
                name="instrucciones_adicionales"
                rows="5"
                maxlength="2000">{p.instrucciones_adicionales}</textarea
              >
              <p class="v2-hint">
                Se le anteponen a cada pregunta, asi que conviene que sean pocas y concretas. Maximo
                2.000 caracteres: mas largo que eso empieza a comerse el espacio que el modelo
                necesita para la consulta, y las respuestas empeoran sin dar ningun error.
              </p>
            </div>
          {/snippet}
        </SettingsFormPanel>
      {/if}

      {#if editingEmpresa}
        <SettingsFormPanel
          title="Qué ofrece la empresa"
          action="?/updateEmpresa"
          error={form?.updateEmpresa?.error}
          submitLabel="Guardar"
          oncancel={() => (editingEmpresa = false)}
          ondone={() => (editingEmpresa = false)}
        >
          {#snippet fields()}
            <div class="v2-field v2-sfp-wide">
              <label for="f-descripcion-empresa">Servicios y planes que ofrece la empresa</label>
              <textarea
                id="f-descripcion-empresa"
                class="v2-input"
                name="descripcion"
                rows="5"
                maxlength="2000"
                placeholder="Ej: Rapilink ofrece planes de internet residencial, y combos de internet + TV. No ofrece telefonía."
              >{identidad?.descripcion}</textarea>
              <p class="v2-hint">
                Esto se le pasa SIEMPRE al agente, en cualquier conversación — a diferencia de los
                documentos del corpus, que solo se traen si la pregunta coincide. Sirve para que el
                agente sepa qué existe y qué no, en vez de adivinar cuando le preguntan algo (ej. si
                vendemos TV o no).
              </p>
            </div>
          {/snippet}
        </SettingsFormPanel>
      {/if}

      {#if editingPlazo}
        <SettingsFormPanel
          title="Plazos de tickets"
          action="?/updatePlazo"
          error={form?.updatePlazo?.error}
          submitLabel="Guardar"
          oncancel={() => (editingPlazo = false)}
          ondone={() => (editingPlazo = false)}
        >
          {#snippet fields()}
            <div class="v2-field">
              <label for="f-plazo-tv">Días para resolver una visita técnica de TV</label>
              <input
                id="f-plazo-tv"
                class="v2-input"
                type="number"
                name="dias"
                min="1"
                max="30"
                required
                value={plazoVisitaTecnica}
              />
              <p class="v2-hint">
                Cuando el agente agenda una visita técnica, este es el plazo que se promete para
                resolverla — se calcula desde el momento en que se crea el ticket, no una fecha fija.
                Hoy se cuenta en días corridos, no hábiles.
              </p>
            </div>
          {/snippet}
        </SettingsFormPanel>
      {/if}

      <div class="v2-split">
        <div>
          <div class="v2-label" style="margin-bottom:10px">Como se presenta</div>
          <div class="v2-card" style="overflow:hidden">
            <div class="v2-setting">
              <div class="v2-setting-body">
                <b>Nombre</b>
                <span class="v2-sub" style="font-size:11.5px">
                  Con este nombre se presenta al abrir una conversacion.
                </span>
              </div>
              <Pill tone="ink">{p.nombre_asistente}</Pill>
            </div>
            <div class="v2-setting">
              <div class="v2-setting-body">
                <b>Tono</b>
                <span class="v2-sub" style="font-size:11.5px">
                  {TONOS.find((t) => t[0] === p.tono)?.[2]}
                </span>
              </div>
              <Pill tone="slate">{tonoLabel}</Pill>
            </div>
            <div class="v2-setting">
              <div class="v2-setting-body">
                <b>Largo de las respuestas</b>
                <span class="v2-sub" style="font-size:11.5px">
                  {LARGOS.find((l) => l[0] === p.longitud_respuesta)?.[2]}
                </span>
              </div>
              <Pill tone="slate">{largoLabel}</Pill>
            </div>
          </div>

          <div class="v2-label" style="margin:22px 0 10px">Instrucciones adicionales</div>
          <div class="v2-card" style="padding:15px 16px">
            {#if p.instrucciones_adicionales}
              <p style="font-size:12.5px;margin:0;line-height:1.6;white-space:pre-wrap">
                {p.instrucciones_adicionales}
              </p>
              <p class="v2-sub" style="font-size:11.5px;margin:10px 0 0">
                <span class="v2-num">{p.instrucciones_adicionales.length}</span> de 2.000 caracteres
              </p>
            {:else}
              <p class="v2-sub" style="font-size:12.5px;margin:0">
                Ninguna. El asistente se comporta segun el tono y el largo de arriba.
              </p>
            {/if}
          </div>
        </div>

        <div>
          <div class="v2-label" style="margin-bottom:10px">Que cambia esto</div>
          <div class="v2-card" style="padding:15px 16px">
            <div style="display:flex;gap:10px;align-items:flex-start">
              <MessageSquare size={16} style="color:var(--v2-slate);flex:none;margin-top:2px" />
              <p class="v2-sub" style="font-size:12.5px;margin:0;line-height:1.5">
                Solo la forma de las respuestas. El cambio se aplica en la conversacion siguiente,
                sin reiniciar nada.
              </p>
            </div>
          </div>

          <div class="v2-card" style="padding:15px 16px;margin-top:12px">
            <div style="display:flex;gap:10px;align-items:flex-start">
              <ShieldCheck size={16} style="color:var(--v2-moss);flex:none;margin-top:2px" />
              <div>
                <div style="font-weight:600;font-size:13px">Nada de esto abre datos</div>
                <p class="v2-sub" style="font-size:12.5px;margin:5px 0 0;line-height:1.5">
                  Que puede consultar cada agente, y que campos le devuelve cada consulta, se decide
                  en <a href="/agentes" style="color:inherit">Agentes</a> y no cambia desde aca. Aunque
                  las instrucciones dijeran lo contrario: los limites se aplican en el codigo del motor,
                  no en el texto que lee el modelo.
                </p>
              </div>
            </div>
          </div>

          {#if data.config?.modelo}
            <p class="v2-sub" style="font-size:11.5px;margin-top:14px">
              Responde con <b style="font-weight:600;color:var(--v2-ink)">{data.config.modelo}</b>
              sobre <span class="v2-num">{data.config.roles.length}</span> agentes. El modelo no se elige
              desde la interfaz.
            </p>
          {/if}
        </div>
      </div>

      <div style="display:flex;align-items:center;justify-content:space-between;margin:22px 0 10px">
        <div class="v2-label" style="margin:0">Qué ofrece la empresa</div>
        {#if data.can_edit && !editingEmpresa}
          <button class="v2-btn v2-btn-sm" onclick={() => (editingEmpresa = true)}>Editar</button>
        {/if}
      </div>
      <div class="v2-card" style="padding:15px 16px">
        {#if identidad?.descripcion}
          <p style="font-size:12.5px;margin:0;line-height:1.6;white-space:pre-wrap">
            {identidad.descripcion}
          </p>
        {:else}
          <p class="v2-sub" style="font-size:12.5px;margin:0">
            Todavía no se describió qué servicios y planes ofrece la empresa. Sin esto, el agente no
            tiene forma de saber si un servicio que le preguntan existe o no.
          </p>
        {/if}
      </div>

      {#if plazoVisitaTecnica != null}
        <div style="display:flex;align-items:center;justify-content:space-between;margin:22px 0 10px">
          <div class="v2-label" style="margin:0">Plazos de tickets</div>
          {#if data.can_edit && !editingPlazo}
            <button class="v2-btn v2-btn-sm" onclick={() => (editingPlazo = true)}>Editar</button>
          {/if}
        </div>
        <div class="v2-card" style="padding:15px 16px">
          <div class="v2-setting" style="padding:0">
            <div class="v2-setting-body">
              <b>Visita técnica de TV</b>
              <span class="v2-sub" style="font-size:11.5px">
                Plazo que se promete al agendar una visita, desde el momento en que se crea el ticket.
              </span>
            </div>
            <Pill tone="slate">{plazoVisitaTecnica} día{plazoVisitaTecnica === 1 ? '' : 's'}</Pill>
          </div>
        </div>
      {/if}
    {/if}
  </div>
</div>
