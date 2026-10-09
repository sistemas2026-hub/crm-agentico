<script>
  /**
   * Credenciales: el inventario, no un segundo formulario.
   *
   * LA REGLA
   * Un secreto tiene UN SOLO lugar de edición. Si la integración tiene pantalla
   * propia, ahí se configura y acá sólo se informa el estado. Si no la tiene,
   * acá se edita.
   *
   * El motivo es concreto: SmartOLT no es una clave suelta, es subdominio +
   * clave + probar conexión. Dejar cambiarla desde el inventario permite
   * guardar sin haber probado nunca la combinación, y que todo PAREZCA bien
   * hasta que un cliente escribe y el asistente no puede consultar la ONU.
   *
   * LO QUE SÓLO PUEDE RESPONDER ESTA PANTALLA
   * «¿Qué le falta a esta empresa para que Dexter funcione completo?». Ni
   * SmartOLT ni WhatsApp por separado pueden contestarlo: cada una ve la suya.
   *
   * QUÉ ES DE ACÁ Y QUÉ DEL ASISTENTE
   * La lista de credenciales que hacen falta la arma el asistente con su propio
   * catálogo, así que el próximo ISP no necesita que nadie toque código. Lo que
   * vive del lado del frontend es a qué pantalla mandar cada una — eso es saber
   * qué pantallas existen en esta aplicación.
   *
   * EL VALOR NUNCA SALE
   * Ni al listar ni después de guardar: viajan el nombre, para qué sirve,
   * cuándo se cargó y los últimos caracteres. Una credencial que se puede
   * volver a leer desde una pantalla es una que se filtra con una captura.
   */
  import { enhance } from '$app/forms';

  import NextAction from '$lib/v2/components/NextAction.svelte';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';

  let { data, form } = $props();

  /** Cuál se está editando. Una por vez: pegar una clave es un acto deliberado. */
  let editando = $state('');
  let agregando = $state(false);
  let busy = $state(false);

  const credenciales = $derived(data.credenciales ?? []);
  const faltan = $derived(credenciales.filter((c) => c.declarado && !c.cargado));

  /**
   * Agrupadas por integración. Las que no tienen pantalla propia van juntas al
   * final: son exactamente las que sí se editan desde acá.
   */
  const grupos = $derived.by(() => {
    /** @type {Map<string, { integracion: string|null, href: string|null, items: any[] }>} */
    const m = new Map();
    for (const c of credenciales) {
      const clave = c.integracion ?? '';
      if (!m.has(clave)) {
        m.set(clave, { integracion: c.integracion ?? null, href: c.href ?? null, items: [] });
      }
      m.get(clave)?.items.push(c);
    }
    const propias = [...m.values()]
      .filter((g) => g.integracion)
      .sort((a, b) => (a.integracion ?? '').localeCompare(b.integracion ?? ''));
    const sueltas = m.get('');
    return sueltas ? [...propias, sueltas] : propias;
  });

  function cuando(iso) {
    if (!iso) return '';
    return new Date(iso).toLocaleDateString('es-CO', {
      day: 'numeric',
      month: 'short',
      year: 'numeric'
    });
  }
</script>

<PageHeader title="Credenciales">
  {#snippet crumb()}<SettingsCrumb />{/snippet}
  {#snippet sub()}
    Qué claves necesita esta empresa y cuáles ya están. Se guardan cifradas y
    nunca se vuelven a mostrar.
  {/snippet}
</PageHeader>

<!-- El shell de la aplicacion tiene overflow:hidden, asi que el contenido tiene
     que vivir dentro de .v2-scroll o queda recortado sin barra. Mismo patron
     que /settings, /settings/api-tokens y las pantallas de canales. -->
<div class="v2-scroll">
  <div class="v2-pad" style="padding-top:24px;padding-bottom:48px;max-width:900px">
  {#if !data.disponible}
    <NextAction
      label="El asistente no respondió"
      text="No se pudo leer qué credenciales hacen falta. La lista sale del catálogo del asistente, así que hasta que responda esta pantalla queda vacía."
      tone="rust"
    />
  {:else}
    {#if form?.error}
      <NextAction label="Eso no funcionó" text={form.error} tone="rust" />
    {/if}
    {#if form?.guardado}
      <NextAction
        label="Guardada"
        text={`'${form.guardado}' quedó cifrada. El asistente la usa en la próxima consulta, sin reiniciar nada.`}
      />
    {/if}
    {#if form?.borrado}
      <NextAction
        label="Borrada"
        text={`'${form.borrado}' ya no está. Si existe una variable de entorno con ese nombre, el asistente vuelve a usarla.`}
      />
    {/if}

    {#if faltan.length}
      <NextAction
        label={faltan.length === 1 ? 'Falta una credencial' : `Faltan ${faltan.length} credenciales`}
        text={`El catálogo las pide y no están cargadas: ${faltan.map((c) => c.nombre).join(', ')}. Las herramientas que dependen de ellas van a fallar al usarse.`}
      />
    {/if}

    {#each grupos as g (g.integracion ?? '_sueltas')}
      <section class="grupo">
        <header class="titulo">
          <h2>{g.integracion ?? 'Sin pantalla propia'}</h2>
          {#if g.href}
            <a class="v2-btn v2-btn-sm" href={g.href}>Configurar en {g.integracion} →</a>
          {/if}
        </header>

        {#if g.href}
          <p class="regla">
            Se administran desde {g.integracion}, que además prueba la conexión
            antes de guardar. Acá sólo se ve el estado.
          </p>
        {/if}

        <ul class="lista">
          {#each g.items as c (c.nombre)}
            <li class="fila" class:falta={c.declarado && !c.cargado}>
              <div class="cabeza">
                <div>
                  <code class="nombre">{c.nombre}</code>
                  {#if c.cargado}
                    <Pill tone="moss">Configurada</Pill>
                  {:else}
                    <Pill tone="clay">Falta</Pill>
                  {/if}
                </div>
                {#if !c.href}
                  <button
                    class="v2-btn v2-btn-sm"
                    onclick={() => (editando = editando === c.nombre ? '' : c.nombre)}
                  >
                    {c.cargado ? 'Reemplazar' : 'Cargar'}
                  </button>
                {/if}
              </div>

              <p class="detalle">
                {#if c.declarado}
                  La usan <strong>{c.cantidad_herramientas}</strong>
                  {c.cantidad_herramientas === 1 ? 'herramienta' : 'herramientas'}:
                  <span class="herramientas">{c.herramientas.join(', ')}</span>{#if c.cantidad_herramientas > c.herramientas.length}…{/if}
                {:else if c.href}
                  La usa el canal de {c.integracion}, no el catálogo de herramientas.
                {:else}
                  Está cargada pero ninguna herramienta la pide. Puede ser de una
                  integración que se sacó y quedó la credencial viva.
                {/if}
              </p>

              {#if c.cargado}
                <p class="pista">
                  termina en <code>{c.pista}</code> · cargada el {cuando(c.actualizado_en)}
                  {#if c.descripcion}· {c.descripcion}{/if}
                </p>
              {/if}

              {#if !c.href && editando === c.nombre}
                <form
                  method="POST"
                  action="?/guardar"
                  class="editor"
                  use:enhance={() => {
                    busy = true;
                    return async ({ update }) => {
                      await update();
                      busy = false;
                      editando = '';
                    };
                  }}
                >
                  <input type="hidden" name="nombre" value={c.nombre} />
                  <label class="v2-label" for={`v-${c.nombre}`}>Valor</label>
                  <input
                    id={`v-${c.nombre}`}
                    name="valor"
                    type="password"
                    class="v2-input"
                    autocomplete="off"
                    spellcheck="false"
                    placeholder="Pegá la clave acá"
                    required
                  />
                  <label class="v2-label" for={`d-${c.nombre}`}>Para qué es (opcional)</label>
                  <input
                    id={`d-${c.nombre}`}
                    name="descripcion"
                    class="v2-input"
                    value={c.descripcion}
                  />
                  <p class="aviso">
                    Se guarda cifrada y no se puede volver a leer desde acá. Si
                    la perdés, se emite una nueva.
                  </p>
                  <div class="acciones">
                    <button class="v2-btn v2-btn-primary" disabled={busy}>Guardar</button>
                    <button type="button" class="v2-btn" onclick={() => (editando = '')}>
                      Cancelar
                    </button>
                    {#if c.cargado}
                      <button class="v2-btn v2-btn-sm borrar" formaction="?/borrar" disabled={busy}>
                        Borrar
                      </button>
                    {/if}
                  </div>
                </form>
              {/if}
            </li>
          {/each}
        </ul>
      </section>
    {/each}

    <div class="agregar">
      <button class="v2-btn" onclick={() => (agregando = !agregando)}>
        {agregando ? 'Cancelar' : 'Agregar otra credencial'}
      </button>
      <p class="regla" style="margin-top:6px">
        Para una clave que todavía no aparece arriba. Pasa cuando la herramienta
        que la va a usar aún no está en el catálogo del asistente: la credencial
        se puede cargar antes y queda esperándola.
      </p>

      {#if agregando}
        <form
          method="POST"
          action="?/guardar"
          class="editor"
          use:enhance={() => {
            busy = true;
            return async ({ update }) => {
              await update();
              busy = false;
              agregando = false;
            };
          }}
        >
          <label class="v2-label" for="nueva-nombre">Nombre</label>
          <input
            id="nueva-nombre"
            name="nombre"
            class="v2-input"
            placeholder="ej. IMPORTACION_API_TOKEN"
            autocomplete="off"
            spellcheck="false"
            required
          />
          <label class="v2-label" for="nueva-valor">Valor</label>
          <input
            id="nueva-valor"
            name="valor"
            type="password"
            class="v2-input"
            autocomplete="off"
            spellcheck="false"
            placeholder="Pegá la clave acá"
            required
          />
          <label class="v2-label" for="nueva-desc">Para qué es (opcional)</label>
          <input id="nueva-desc" name="descripcion" class="v2-input" />
          <p class="aviso">
            El nombre tiene que coincidir exactamente con el <code>auth_ref</code>
            que declara la herramienta, o va a seguir sin encontrarla.
          </p>
          <div class="acciones">
            <button class="v2-btn v2-btn-primary" disabled={busy}>Guardar</button>
          </div>
        </form>
      {/if}
    </div>
  {/if}
  </div>
</div>

<style>
  .grupo {
    margin-top: 26px;
  }
  .titulo {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 6px;
  }
  .titulo h2 {
    font-size: 13px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--v2-muted, #5c6672);
    margin: 0;
  }
  .lista {
    list-style: none;
    margin: 8px 0 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 1px;
    background: var(--v2-rule, #e4e7e9);
    border: 1px solid var(--v2-rule, #e4e7e9);
  }
  .fila {
    background: var(--v2-surface, #fff);
    padding: 14px 16px;
  }
  .fila.falta {
    border-left: 3px solid var(--v2-clay, #b5751f);
  }
  .cabeza {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
  }
  .cabeza > div {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .nombre {
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
    font-size: 13px;
  }
  .detalle,
  .pista,
  .regla {
    margin: 6px 0 0;
    font-size: 13px;
    color: var(--v2-muted, #5c6672);
  }
  .herramientas {
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
    font-size: 12px;
  }
  .pista code {
    font-size: 12px;
  }
  .editor {
    margin-top: 12px;
    padding-top: 12px;
    border-top: 1px solid var(--v2-rule, #e4e7e9);
    display: flex;
    flex-direction: column;
    gap: 4px;
    max-width: 520px;
  }
  .editor .v2-label {
    margin-top: 6px;
  }
  .aviso {
    margin: 8px 0 0;
    font-size: 12px;
    color: var(--v2-muted, #5c6672);
  }
  .acciones {
    display: flex;
    gap: 8px;
    margin-top: 12px;
    align-items: center;
  }
  .borrar {
    margin-left: auto;
    color: var(--v2-rust, #a3402f);
  }
  .agregar {
    margin-top: 28px;
    padding-top: 16px;
    border-top: 1px solid var(--v2-rule, #e4e7e9);
  }
</style>
