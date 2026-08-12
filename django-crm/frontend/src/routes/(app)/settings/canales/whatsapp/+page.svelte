<script>
  /**
   * WhatsApp: las credenciales que hacen falta para prender el canal.
   *
   * NUNCA se ve un valor GUARDADO. Esta pantalla solo sabe si algo esta
   * cargado (una pista de 4 caracteres y cuando) -- los valores reales viven
   * cifrados en la base y ni siquiera salen de ella (ver
   * nucleo/seguridad/secretos.py::listar). La unica excepcion es el
   * verify_token recien generado: ese SI se muestra una vez, porque hay que
   * copiarlo a Meta, y despues de esa carga se pierde igual que los demas.
   *
   * El ojo de cada campo es OTRA cosa y no contradice lo anterior: muestra lo
   * que la persona acaba de escribir o pegar, que ya esta en su navegador.
   * Existe porque con cinco campos de puntitos identicos no hay forma de
   * notar que el token se pego en la casilla del App Secret -- y ese error no
   * se descubre hasta que Meta rechaza el webhook, con un mensaje que no
   * menciona cual credencial esta cruzada.
   *
   * El toggle "Activar" queda deshabilitado hasta que las cuatro credenciales
   * indispensables tengan valor. Es una ayuda de la interfaz, no la
   * proteccion real: aunque alguien la saltee escribiendo directo al motor,
   * este sigue fallando cerrado en cada llamada (nucleo/canales/whatsapp.py).
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import { shortAge } from '$lib/v2/format.js';
  import { enhance } from '$app/forms';
  import { Copy, Check, ExternalLink, Eye, EyeOff } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let canal = $derived(data.canal);
  let secretos = $derived(data.secretos ?? []);

  // Las cinco credenciales de Meta. 'clave' es la que usa canal.refs para dar
  // el NOMBRE real del secreto (ej. 'WHATSAPP_TOKEN') -- este archivo no
  // hardcodea esos nombres, los lee de la configuracion del tenant.
  const CREDENCIALES = [
    {
      clave: 'phone_number_id',
      etiqueta: 'ID del número emisor',
      ayuda: 'WhatsApp → API Setup, en Meta for Developers. No es el teléfono: es su ID numérico.',
      indispensable: true
    },
    {
      clave: 'token',
      etiqueta: 'Token de acceso',
      ayuda:
        'System User → token permanente. El token de prueba de la consola dura 24 h y deja de servir sin aviso — no sirve acá.',
      indispensable: true
    },
    {
      clave: 'app_secret',
      etiqueta: 'App Secret',
      ayuda:
        'App → Settings → Basic. Con esto se confirma que cada mensaje entrante viene de verdad de Meta.',
      indispensable: true
    },
    {
      clave: 'verify_token',
      etiqueta: 'Verify token',
      ayuda:
        'No lo pide Meta: lo elegís vos. Se usa una sola vez, al dar de alta el webhook — mejor generarlo que inventar uno.',
      indispensable: true,
      generable: true
    },
    {
      clave: 'waba_id',
      etiqueta: 'ID de la cuenta de negocio (WABA)',
      ayuda: 'Solo hace falta para mandar avisos por plantilla (mora, corte). Se puede cargar después.',
      indispensable: false
    }
  ];

  function refDe(/** @type {string} */ clave) {
    return canal?.refs?.[clave] ?? null;
  }

  function secretoDe(/** @type {string} */ clave) {
    const nombre = refDe(clave);
    return nombre ? secretos.find((s) => s.nombre === nombre) : undefined;
  }

  let todosLosIndispensables = $derived(
    CREDENCIALES.filter((c) => c.indispensable).every((c) => !!secretoDe(c.clave))
  );

  let activoChecked = $state(!!canal?.activo);
  let numeroVisible = $state(canal?.numero_visible ?? '');

  // El dominio no se guarda en ningun lado: es solo para armar el texto que
  // hay que copiar en Meta. Cada quien pone el suyo (ver DESPLIEGUE.md §4.c).
  let dominio = $state('');
  let urlWebhook = $derived(
    dominio.trim()
      ? `https://${dominio.trim().replace(/^https?:\/\//, '').replace(/\/$/, '')}/canales/whatsapp/${canal?.tenant_slug ?? ''}`
      : ''
  );
  let copiadoUrl = $state(false);
  let copiadoToken = $state(false);

  // Por credencial: si se está viendo lo tecleado, y qué se tecleó. Los dos
  // son por clave y no un booleano suelto porque hay cinco campos y mostrar
  // uno no puede destapar los otros cuatro.
  //
  // Esto NO revela lo guardado -- el valor cifrado nunca sale de la base (ver
  // secretos.listar()). Revela lo que la persona acaba de escribir o pegar,
  // que ya está en su navegador. Existe porque con cinco campos de puntitos
  // idénticos no hay forma de notar que el token se pegó en la casilla del
  // App Secret, y ese error se descubre recién cuando Meta rechaza el webhook.
  let aLaVista = $state(/** @type {Record<string, boolean>} */ ({}));
  let pegado = $state(/** @type {Record<string, string>} */ ({}));

  /** @param {string} texto @param {() => void} marcar */
  async function copiar(texto, marcar) {
    try {
      await navigator.clipboard.writeText(texto);
      marcar();
    } catch {
      // Portapapeles bloqueado. El texto esta a la vista para seleccionarlo
      // a mano; no hay nada mas que hacer.
    }
  }

  const enviando = () => {
    return async (/** @type {any} */ { update }) => {
      await update();
    };
  };

  // 'update()' por defecto RESETEA el formulario a sus valores por defecto
  // (comportamiento nativo de use:enhance) -- bien para el campo de
  // credencial, que conviene vaciar despues de guardar un secreto. Mal para
  // este: el checkbox y el numero visible volverian a lo que HABIA antes de
  // tocar nada, y como aca no habia numero cargado, "antes" es vacio -- se
  // ve como si el campo se hubiera borrado solo, aunque el guardado si
  // funciono.
  const guardandoCanal = () => {
    return async (/** @type {any} */ { update }) => {
      await update({ reset: false });
    };
  };

  /**
   * Tras guardar una credencial: vaciar el campo y volver a ocultarlo. El
   * reset del formulario limpia el DOM, pero el valor vive en 'pegado' y el
   * bind lo volveria a poner -- y dejar el secreto a la vista despues de
   * guardarlo es justo lo que no se quiere.
   * @param {string} clave
   */
  function guardandoCredencial(clave) {
    return () => async (/** @type {any} */ { update, result }) => {
      await update();
      if (result?.type === 'success') {
        pegado[clave] = '';
        aLaVista[clave] = false;
      }
    };
  }
</script>

<PageHeader title="WhatsApp">
  {#snippet crumb()}<SettingsCrumb />{/snippet}
  {#snippet sub()}
    {#if !canal}
      El asistente no responde
    {:else if canal.activo}
      Activo{#if canal.numero_visible} · {canal.numero_visible}{/if}
    {:else if todosLosIndispensables}
      Las credenciales están cargadas, falta activarlo
    {:else}
      Faltan credenciales para poder activarlo
    {/if}
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <div class="v2-pad" style="padding-top:16px;padding-bottom:32px;max-width:760px">
    {#if !canal}
      <div class="v2-card" style="padding:20px 22px">
        <b style="font-size:13px">No se pudo leer la configuración del canal</b>
        <p class="v2-sub" style="font-size:12.5px;margin:8px 0 0;line-height:1.5">
          El motor no está respondiendo. Los mismos ajustes se ven en
          <a href="/settings/asistente" style="color:inherit">Personalidad del asistente</a>; si esa
          pantalla tampoco carga, es el motor.
        </p>
      </div>
    {:else}
      {#if form?.generado?.valor}
        <div
          class="v2-card"
          style="padding:15px 16px;margin-bottom:18px;border-color:color-mix(in srgb, var(--v2-moss) 40%, var(--v2-line))"
        >
          <div style="font-weight:650;font-size:13px">Verify token generado, copialo ahora</div>
          <p class="v2-sub" style="font-size:12px;margin:4px 0 10px">
            Esta es la única vez que se muestra. Pegalo en Meta → WhatsApp → Configuration → Verify
            token, en el mismo paso en que pegás la URL del webhook.
          </p>
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
            <code
              class="v2-num"
              style="flex:1;min-width:220px;background:var(--v2-line-soft);border:1px solid var(--v2-line);border-radius:var(--v2-radius);padding:9px 11px;font-size:12.5px;word-break:break-all"
            >{form.generado.valor}</code>
            <button
              class="v2-btn v2-btn-sm"
              type="button"
              onclick={() => copiar(form.generado.valor, () => {
                copiadoToken = true;
                setTimeout(() => (copiadoToken = false), 1600);
              })}
            >
              {#if copiadoToken}<Check size={13} />Copiado{:else}<Copy size={13} />Copiar{/if}
            </button>
          </div>
        </div>
      {/if}

      <!-- ── estado del canal ────────────────────────────────────────────── -->
      <div class="v2-label" style="margin-bottom:10px">Estado del canal</div>
      <div class="v2-card" style="padding:16px">
        <form
          method="POST"
          action="?/guardarCanal"
          use:enhance={guardandoCanal}
          style="display:flex;flex-direction:column;gap:14px"
        >
          <input type="hidden" name="activo" value={activoChecked} />

          <div style="display:flex;align-items:center;gap:10px">
            <label class="canal-switch">
              <input
                type="checkbox"
                bind:checked={activoChecked}
                disabled={!data.can_edit || (!activoChecked && !todosLosIndispensables)}
              />
              <span>Canal activo</span>
            </label>
            <Pill tone={canal.activo ? 'moss' : 'slate'} dot>
              {canal.activo ? 'Recibiendo mensajes' : 'Apagado'}
            </Pill>
          </div>

          {#if !todosLosIndispensables}
            <p class="v2-sub" style="font-size:11.5px;margin:0">
              Faltan credenciales indispensables para poder activarlo — completá la lista de abajo.
            </p>
          {/if}

          <div class="v2-field" style="margin:0">
            <label for="f-numero" style="font-size:11.5px">Número visible</label>
            <input
              id="f-numero"
              class="v2-input"
              type="text"
              name="numero_visible"
              placeholder="300 000 0000"
              bind:value={numeroVisible}
              disabled={!data.can_edit}
            />
            <p class="v2-hint">
              Solo para mostrarlo acá y en la lista de conversaciones. No participa de ninguna
              llamada a Meta.
            </p>
          </div>

          {#if form?.canalError}<p class="v2-error" style="font-size:12px">{form.canalError}</p>{/if}

          {#if data.can_edit}
            <button class="v2-btn v2-btn-primary" type="submit" style="align-self:flex-start">
              Guardar
            </button>
          {/if}
        </form>
      </div>

      <!-- ── URL del webhook ─────────────────────────────────────────────── -->
      <div class="v2-label" style="margin:22px 0 10px">URL para pegar en Meta</div>
      <div class="v2-card" style="padding:16px">
        <div class="v2-field" style="margin:0">
          <label for="f-dominio" style="font-size:11.5px">Tu dominio</label>
          <input
            id="f-dominio"
            class="v2-input"
            type="text"
            placeholder="wa.tuempresa.co"
            bind:value={dominio}
          />
          <p class="v2-hint">
            No se guarda en ningún lado — es solo para armar el texto de abajo. Tiene que apuntar
            por DNS al servidor antes de darlo de alta en Meta (ver DESPLIEGUE.md §4.c).
          </p>
        </div>

        {#if urlWebhook}
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:12px">
            <code
              class="v2-num"
              style="flex:1;min-width:220px;background:var(--v2-line-soft);border:1px solid var(--v2-line);border-radius:var(--v2-radius);padding:9px 11px;font-size:12px;word-break:break-all"
            >{urlWebhook}</code>
            <button
              class="v2-btn v2-btn-sm"
              type="button"
              onclick={() => copiar(urlWebhook, () => {
                copiadoUrl = true;
                setTimeout(() => (copiadoUrl = false), 1600);
              })}
            >
              {#if copiadoUrl}<Check size={13} />Copiado{:else}<Copy size={13} />Copiar{/if}
            </button>
          </div>
          <p class="v2-sub" style="font-size:11px;margin:8px 0 0">
            Pegala en Meta → tu App → WhatsApp → Configuration → Callback URL, junto con el verify
            token de abajo.
          </p>
        {/if}
      </div>

      <!-- ── credenciales ────────────────────────────────────────────────── -->
      <div class="v2-label" style="margin:22px 0 10px">Credenciales</div>
      <div class="v2-card" style="overflow:hidden">
        {#each CREDENCIALES as c, i (c.clave)}
          {@const refName = refDe(c.clave)}
          {@const secreto = secretoDe(c.clave)}
          <div class="cred-fila" class:cred-borde={i > 0}>
            <div class="cred-info">
              <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                <b style="font-size:13px">{c.etiqueta}</b>
                {#if !c.indispensable}
                  <Pill tone="slate">Opcional</Pill>
                {/if}
                {#if secreto}
                  <Pill tone="moss" dot>Cargado</Pill>
                {:else if c.indispensable}
                  <Pill tone="clay">Sin cargar</Pill>
                {:else}
                  <Pill tone="slate">Sin cargar</Pill>
                {/if}
              </div>
              <p class="v2-sub" style="font-size:11.5px;margin:5px 0 0;line-height:1.5">{c.ayuda}</p>
              {#if secreto}
                <p class="v2-sub" style="font-size:11px;margin:5px 0 0">
                  Termina en <span class="v2-num">…{secreto.pista}</span> · actualizado
                  {shortAge(secreto.actualizado_en)}
                </p>
              {/if}
              {#if form?.campo === refName && form?.error}
                <p class="v2-error" style="font-size:11.5px;margin:6px 0 0">{form.error}</p>
              {/if}
            </div>

            {#if data.can_edit}
              <div class="cred-accion">
                <form
                  method="POST"
                  action="?/guardarCredencial"
                  use:enhance={guardandoCredencial(c.clave)}
                  class="cred-form"
                >
                  <input type="hidden" name="nombre" value={refName} />
                  <input type="hidden" name="descripcion" value={c.etiqueta} />
                  <div class="cred-campo">
                    <input
                      class="v2-input"
                      type={aLaVista[c.clave] ? 'text' : 'password'}
                      name="valor"
                      autocomplete="off"
                      placeholder={secreto ? 'Reemplazar…' : 'Pegar valor…'}
                      required
                      bind:value={pegado[c.clave]}
                    />
                    <!-- Muestra lo que ACABÁS de pegar, no lo que está
                         guardado: ese valor ya está en tu navegador, así que
                         verlo no expone nada nuevo. Sirve para lo único que
                         hace falta acá — confirmar que el valor cayó en la
                         casilla correcta, con cinco campos que si no se ven
                         idénticos. -->
                    <button
                      type="button"
                      class="cred-ojo"
                      onclick={() => (aLaVista[c.clave] = !aLaVista[c.clave])}
                      aria-label={aLaVista[c.clave] ? 'Ocultar' : 'Mostrar lo que pegaste'}
                      title={aLaVista[c.clave] ? 'Ocultar' : 'Mostrar lo que pegaste'}
                    >
                      {#if aLaVista[c.clave]}<EyeOff size={14} />{:else}<Eye size={14} />{/if}
                    </button>
                  </div>
                  <button class="v2-btn v2-btn-sm" type="submit">
                    {secreto ? 'Actualizar' : 'Guardar'}
                  </button>
                </form>

                <!-- El campo se vacía al guardar (no se deja un secreto en el
                     formulario), y ese vaciado es la señal más fuerte de la
                     pantalla: sin esto se lee como "se perdió" en vez de
                     "listo". La confirmación tiene que estar donde estaba el
                     valor, no solo en la pista de la izquierda. -->
                {#if form?.guardado === refName}
                  <p class="cred-ok"><Check size={12} /> Guardado</p>
                {/if}

                <div style="display:flex;gap:6px">
                  {#if c.generable}
                    <form method="POST" action="?/generarVerifyToken" use:enhance={enviando}>
                      <button class="v2-btn v2-btn-sm v2-btn-quiet" type="submit">Generar</button>
                    </form>
                  {/if}
                  {#if secreto}
                    <form method="POST" action="?/borrarCredencial" use:enhance={enviando}>
                      <input type="hidden" name="nombre" value={refName} />
                      <button class="v2-btn v2-btn-sm v2-btn-quiet" type="submit">Borrar</button>
                    </form>
                  {/if}
                </div>
              </div>
            {/if}
          </div>
        {/each}
      </div>

      <p class="v2-sub" style="font-size:11.5px;margin-top:14px;display:flex;gap:6px;align-items:center">
        <ExternalLink size={12} />
        Permisos que necesita el System User en Meta: <span class="v2-num">whatsapp_business_messaging</span>
        y <span class="v2-num">whatsapp_business_management</span>.
      </p>
    {/if}
  </div>
</div>

<style>
  .canal-switch {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
  }
  .canal-switch input {
    accent-color: var(--v2-ink);
  }
  .cred-fila {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 20px;
    padding: 16px;
    flex-wrap: wrap;
  }
  .cred-borde {
    border-top: 1px solid var(--v2-line-soft);
  }
  .cred-info {
    flex: 1;
    min-width: 260px;
  }
  .cred-accion {
    display: flex;
    flex-direction: column;
    gap: 6px;
    flex: none;
    width: 260px;
  }
  .cred-form {
    display: flex;
    gap: 6px;
  }
  /* El campo y su ojo son una sola pieza: el boton va DENTRO del recuadro,
     no al lado, para que no se lea como una accion sobre la credencial
     (guardar, borrar) sino como parte de escribir en el campo. */
  .cred-campo {
    position: relative;
    flex: 1;
    min-width: 0;
    display: flex;
  }
  .cred-campo input {
    flex: 1;
    min-width: 0;
    font-size: 12.5px;
    padding-right: 30px;
  }
  .cred-ojo {
    position: absolute;
    right: 1px;
    top: 1px;
    bottom: 1px;
    width: 28px;
    display: grid;
    place-items: center;
    border: 0;
    background: none;
    color: var(--v2-slate);
    cursor: pointer;
    border-radius: 0 7px 7px 0;
  }
  .cred-ojo:hover {
    color: var(--v2-ink);
  }
  .cred-ok {
    display: flex;
    align-items: center;
    gap: 4px;
    margin: 2px 0 0;
    font-size: 11.5px;
    color: var(--v2-moss);
    font-weight: 550;
  }

  @media (max-width: 640px) {
    .cred-accion {
      width: 100%;
    }
  }
</style>
