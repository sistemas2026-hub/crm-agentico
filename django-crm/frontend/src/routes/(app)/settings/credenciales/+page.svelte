<script>
  /**
   * Credenciales del asistente.
   *
   * POR QUÉ EXISTE
   * Hasta ahora cargar una credencial nueva obligaba a entrar al contenedor.
   * El endpoint del asistente siempre fue genérico, pero las únicas pantallas
   * que lo llamaban estaban cableadas a WhatsApp y a SmartOLT. Dar de alta una
   * empresa no puede depender de una sesión de consola: esto es SaaS y el
   * próximo ISP trae sus propias claves.
   *
   * LA LISTA NO ESTÁ ESCRITA ACÁ
   * La arma el asistente leyendo los `auth_ref` que declara el catálogo de
   * herramientas del tenant. Si mañana una empresa declara
   * `OTRO_PROVEEDOR_API_KEY`, aparece sola y esta pantalla no cambia.
   *
   * LO QUE NUNCA SE MUESTRA
   * El valor. Ni al listar ni después de guardar: el asistente devuelve el
   * nombre, para qué sirve, cuándo se cargó y una pista de los últimos
   * caracteres. Una credencial que se puede volver a leer desde una pantalla
   * es una credencial que se filtra con una captura de pantalla.
   */
  import { enhance } from '$app/forms';

  import NextAction from '$lib/v2/components/NextAction.svelte';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';

  let { data, form } = $props();

  /** Cuál se está editando. Una por vez: pegar una clave es un acto deliberado. */
  let editando = $state('');
  let busy = $state(false);

  const credenciales = $derived(data.credenciales ?? []);
  const faltan = $derived(credenciales.filter((c) => c.declarado && !c.cargado));
  const huerfanas = $derived(credenciales.filter((c) => !c.declarado && c.cargado));

  function cuando(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleDateString('es-CO', { day: 'numeric', month: 'short', year: 'numeric' });
  }
</script>

<PageHeader title="Credenciales">
  {#snippet crumb()}<SettingsCrumb />{/snippet}
  {#snippet sub()}
    Las claves que el asistente necesita para hablar con los sistemas de la
    empresa. Se guardan cifradas y nunca se vuelven a mostrar.
  {/snippet}
</PageHeader>

<div class="v2-pad" style="padding-top:24px;max-width:900px">
  {#if !data.disponible}
    <NextAction
      label="El asistente no respondió"
      text="No se pudo leer qué credenciales hacen falta. La lista sale del catálogo de herramientas del asistente, así que hasta que responda esta pantalla queda vacía."
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
        tone="moss"
      />
    {/if}
    {#if form?.borrado}
      <NextAction
        label="Borrada"
        text={`'${form.borrado}' ya no está. Si existe una variable de entorno con ese nombre, el asistente vuelve a usarla.`}
        tone="clay"
      />
    {/if}

    {#if faltan.length}
      <NextAction
        label={faltan.length === 1 ? 'Falta una credencial' : `Faltan ${faltan.length} credenciales`}
        text={`El catálogo las pide y no están cargadas: ${faltan.map((c) => c.nombre).join(', ')}. Las herramientas que dependen de ellas van a fallar al usarse.`}
        tone="clay"
      />
    {/if}

    {#if !credenciales.length}
      <p class="vacio">Este asistente no declara ninguna credencial todavía.</p>
    {/if}

    <ul class="lista">
      {#each credenciales as c (c.nombre)}
        <li class="fila" class:falta={c.declarado && !c.cargado}>
          <div class="cabeza">
            <div>
              <code class="nombre">{c.nombre}</code>
              {#if c.cargado}
                <Pill label="Cargada" tone="moss" />
              {:else}
                <Pill label="Falta" tone="clay" />
              {/if}
              {#if !c.declarado}
                <Pill label="Sin usar" tone="slate" />
              {/if}
            </div>
            <button
              class="v2-btn v2-btn-sm"
              onclick={() => (editando = editando === c.nombre ? '' : c.nombre)}
            >
              {c.cargado ? 'Reemplazar' : 'Cargar'}
            </button>
          </div>

          <p class="detalle">
            {#if c.declarado}
              La usan <strong>{c.cantidad_herramientas}</strong>
              {c.cantidad_herramientas === 1 ? 'herramienta' : 'herramientas'}:
              <span class="herramientas">{c.herramientas.join(', ')}</span>{#if c.cantidad_herramientas > c.herramientas.length}…{/if}
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

          {#if editando === c.nombre}
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
                placeholder="ej. PAT de importación WispHub → Dexter"
              />
              <p class="aviso">
                Se guarda cifrada y no se puede volver a leer desde acá. Si la
                perdés, se emite una nueva.
              </p>
              <div class="acciones">
                <button class="v2-btn v2-btn-primary" disabled={busy}>Guardar</button>
                <button type="button" class="v2-btn" onclick={() => (editando = '')}>
                  Cancelar
                </button>
                {#if c.cargado}
                  <button
                    class="v2-btn v2-btn-sm borrar"
                    formaction="?/borrar"
                    disabled={busy}
                  >
                    Borrar
                  </button>
                {/if}
              </div>
            </form>
          {/if}
        </li>
      {/each}
    </ul>

    {#if huerfanas.length}
      <p class="nota">
        {huerfanas.length}
        {huerfanas.length === 1 ? 'credencial cargada no la pide' : 'credenciales cargadas no las pide'}
        ninguna herramienta. Borrarlas no rompe nada, y una clave viva que
        nadie usa es una que nadie va a rotar.
      </p>
    {/if}
  {/if}
</div>

<style>
  .lista {
    list-style: none;
    margin: 20px 0 0;
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
  .nota,
  .vacio {
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
  .nota {
    margin-top: 16px;
  }
</style>
