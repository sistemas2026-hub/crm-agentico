<script>
  /**
   * Pagos: con qué puede pagar un cliente.
   *
   * POR QUE ESTA PANTALLA EXISTE
   * ----------------------------
   * El link de pago y los puntos donde se paga (Efecty con su convenio, una
   * cuenta) cambian de una empresa a otra. Si solo se pudieran cargar por API,
   * serían justo lo que la regla multi-empresa del proyecto prohíbe: un dato que
   * "solo un desarrollador sabe editar". Acá cada empresa carga los suyos.
   *
   * DOS BLOQUES, UNA SOLA IDEA
   * --------------------------
   * "Pagar en línea" es una dirección; "Pagar en un punto" es una lista de textos
   * que escribe la empresa. Un punto físico identifica a la persona por su
   * cédula, así que el texto dice "di tu cédula" y no lleva ningún dato del
   * cliente: no hay nada que calcular por persona.
   *
   * QUE PASA CON ESTO
   * -----------------
   * No va en el prompt de ningún agente. El asistente lo recibe de dos herramientas:
   * la de cuenta (cuando la persona debe algo) y la de medios de pago (cuando
   * pregunta dónde o cómo pagar, deba o no). Las dos exigen que ya esté verificada,
   * y un valor mal escrito no se entrega. El panel de la derecha lo dice en la
   * pantalla para que nadie tenga que adivinarlo.
   *
   * VACIO NO ES UN ERROR
   * --------------------
   * Sin nada cargado el asistente dice cuánto se debe y no ofrece dónde pagar.
   * Es el estado por defecto, no una falla: no se marca como advertencia.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import SettingsCrumb from '$lib/v2/components/SettingsCrumb.svelte';
  import SettingsFormPanel from '$lib/v2/components/SettingsFormPanel.svelte';
  import Pill from '$lib/v2/components/Pill.svelte';

  // Los mismos topes que valida el servidor y el motor.
  const MAXIMO_MEDIOS = 10;
  const LARGO_MEDIO = 60;
  const LARGO_INSTRUCCION = 300;

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  /** Qué bloque se está editando: solo uno a la vez. @type {null | 'link' | 'medios'} */
  let editando = $state(null);

  /** Las filas del formulario de medios. Cada una con un id propio y estable:
   *  la clave del {#each} no puede ser el texto ni la posición. */
  let filas = $state(/** @type {{ id: number, nombre: string, instruccion: string }[]} */ ([]));
  let siguienteId = 0;

  let a = $derived(data.ajustes);
  const tieneLink = $derived(!!a && a.link !== '');
  const medios = $derived(/** @type {{ nombre: string, instruccion: string }[]} */ (a?.medios ?? []));
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

  function abrirMedios() {
    filas = medios.map((m) => ({ id: siguienteId++, nombre: m.nombre, instruccion: m.instruccion }));
    if (filas.length === 0) agregarFila();
    editando = 'medios';
  }
  function agregarFila() {
    if (filas.length >= MAXIMO_MEDIOS) return;
    filas.push({ id: siguienteId++, nombre: '', instruccion: '' });
  }
  /** @param {number} id */
  function quitarFila(id) {
    filas = filas.filter((f) => f.id !== id);
  }

  const resumen = $derived.by(() => {
    if (!a) return 'El asistente no respondió';
    const partes = [];
    partes.push(tieneLink ? `Link de pago · ${sitio}` : 'Sin link de pago');
    partes.push(
      medios.length === 0
        ? 'sin puntos de pago'
        : `${medios.length} ${medios.length === 1 ? 'punto de pago' : 'puntos de pago'}`
    );
    return partes.join(' · ');
  });
</script>

<PageHeader title="Pagos">
  {#snippet crumb()}<SettingsCrumb />{/snippet}
  {#snippet sub()}{resumen}{/snippet}
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
          Lo que el cliente puede usar para pagar vive en la configuración del
          asistente, que es otro servicio. No se pudo leer: o no está desplegado, o
          no está respondiendo. Lo que ya tenga cargado sigue vigente — esta pantalla
          no lo borró.
        </p>
      </div>
    </div>
  </div>
{:else}
  <div class="v2-scroll">
    <div class="v2-pad pg-pad">
      <div class="pg-grid">
        <div class="pg-main">
          <!-- ───────── Pagar en línea ───────── -->
          {#if editando === 'link'}
            <SettingsFormPanel
              title="Link de pago"
              action="?/guardar"
              error={form?.guardar?.error}
              submitLabel="Guardar"
              oncancel={() => (editando = null)}
              ondone={() => (editando = null)}
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
                    Tiene que empezar con https://. Dejalo vacío para quitarlo.
                  </p>
                </div>
              {/snippet}
            </SettingsFormPanel>
          {:else}
            <section class="v2-card pg-bloque" aria-labelledby="pg-linea">
              <header class="pg-head">
                <h2 id="pg-linea" class="pg-titulo">Pagar en línea</h2>
                {#if data.can_edit}
                  <button class="v2-btn v2-btn-sm" onclick={() => (editando = 'link')}>
                    {tieneLink ? 'Cambiar el link' : 'Cargar el link'}
                  </button>
                {/if}
              </header>
              {#if tieneLink}
                <p class="pg-sitio">{sitio}</p>
                <p class="v2-hint pg-nota">El asistente se lo ofrece a quien debe una factura.</p>
              {:else}
                <p class="pg-vacio">Sin link de pago</p>
                <p class="v2-hint pg-nota">
                  El asistente dice cuánto se debe, sin ofrecer dónde pagar en línea.
                </p>
              {/if}
              {#if form?.guardado && !editando}
                <p class="v2-hint pg-ok" role="status">Guardado.</p>
              {/if}
            </section>
          {/if}

          <!-- ───────── Pagar en un punto ───────── -->
          {#if editando === 'medios'}
            <SettingsFormPanel
              title="Pagar en un punto"
              action="?/guardar_medios"
              error={form?.guardar_medios?.error}
              submitLabel="Guardar"
              oncancel={() => (editando = null)}
              ondone={() => (editando = null)}
            >
              {#snippet fields()}
                <div class="pg-form">
                <p class="v2-hint" style="margin:0">
                  Un punto donde el cliente puede pagar en persona, o una cuenta.
                  Escribí lo que el cliente tiene que hacer: si el punto lo identifica
                  por su cédula, decíselo ("di tu cédula"). Hasta {MAXIMO_MEDIOS} medios.
                </p>

                {#each filas as fila, i (fila.id)}
                  <div class="pg-fila">
                    <div class="v2-field pg-campo-nombre">
                      <label for="m-nombre-{fila.id}">Nombre</label>
                      <input
                        id="m-nombre-{fila.id}"
                        class="v2-input"
                        name="medio_nombre"
                        placeholder="Efecty"
                        maxlength={LARGO_MEDIO}
                        bind:value={fila.nombre}
                      />
                    </div>
                    <div class="v2-field pg-campo-texto">
                      <label for="m-texto-{fila.id}">Cómo se paga</label>
                      <textarea
                        id="m-texto-{fila.id}"
                        class="v2-input pg-texto"
                        name="medio_instruccion"
                        rows="2"
                        placeholder="Convenio 12345. Di tu cédula en caja."
                        maxlength={LARGO_INSTRUCCION}
                        bind:value={fila.instruccion}
                      ></textarea>
                      <span class="pg-contador" class:pg-contador-alto={fila.instruccion.length > LARGO_INSTRUCCION - 40}>
                        {fila.instruccion.length}/{LARGO_INSTRUCCION}
                      </span>
                    </div>
                    <button
                      class="v2-btn v2-btn-quiet v2-btn-sm pg-quitar"
                      type="button"
                      aria-label="Quitar el medio {fila.nombre || i + 1}"
                      onclick={() => quitarFila(fila.id)}
                    >
                      Quitar
                    </button>
                  </div>
                {:else}
                  <p class="v2-hint" style="margin:0">
                    No queda ningún medio: al guardar se quitan todos.
                  </p>
                {/each}

                <div>
                  <button
                    class="v2-btn v2-btn-sm"
                    type="button"
                    disabled={filas.length >= MAXIMO_MEDIOS}
                    onclick={agregarFila}
                  >
                    Agregar otro medio
                  </button>
                </div>
                </div>
              {/snippet}
            </SettingsFormPanel>
          {:else}
            <section class="v2-card pg-bloque" aria-labelledby="pg-punto">
              <header class="pg-head">
                <h2 id="pg-punto" class="pg-titulo">Pagar en un punto</h2>
                {#if data.can_edit}
                  <button class="v2-btn v2-btn-sm" onclick={abrirMedios}>
                    {medios.length === 0 ? 'Agregar un medio' : 'Editar los medios'}
                  </button>
                {/if}
              </header>

              {#if a.medios_ilegibles}
                <p class="v2-error pg-nota" role="alert">
                  Lo que había guardado no se pudo leer, así que el asistente no
                  ofrece ningún medio. Cargalos de nuevo desde acá.
                </p>
              {/if}

              {#if medios.length > 0}
                <ul class="pg-lista">
                  {#each medios as m, i (i)}
                    <li>
                      <span class="pg-medio">{m.nombre}</span>
                      <span class="pg-instruccion">{m.instruccion}</span>
                    </li>
                  {/each}
                </ul>
              {:else if !a.medios_ilegibles}
                <p class="pg-vacio">Sin puntos de pago</p>
                <p class="v2-hint pg-nota">
                  Si la empresa recibe pagos en Efecty u otra entidad, cargalos acá con
                  su convenio: por ejemplo «Efecty» — «Convenio 12345. Di tu cédula en
                  caja».
                </p>
              {/if}
              {#if form?.guardado_medios && !editando}
                <p class="v2-hint pg-ok" role="status">Guardado.</p>
              {/if}
            </section>
          {/if}
        </div>

        <!-- ───────── Qué ve el asistente ───────── -->
        <aside class="v2-card pg-aside" aria-labelledby="pg-aside-t">
          <h2 id="pg-aside-t" class="pg-titulo">Qué hace el asistente con esto</h2>
          <dl class="pg-reglas">
            <div>
              <dt>Quién lo recibe</dt>
              <dd>
                Un cliente ya verificado. Si tiene una factura pendiente, el asistente se
                lo ofrece al decirle cuánto debe. Si pregunta dónde o cómo pagar, se lo da,
                deba algo o no.
              </dd>
            </div>
            <div>
              <dt>Quién no</dt>
              <dd>Quien no se pudo verificar como cliente.</dd>
            </div>
            <div>
              <dt>Cómo lo dice</dt>
              <dd>
                Los datos tal cual están escritos acá. No cambia ni inventa ningún número
                de convenio ni de cuenta.
              </dd>
            </div>
            <div>
              <dt>Dónde queda escrito</dt>
              <dd>En ningún mensaje de un agente. Se cambia o se quita acá, sin tocar nada más.</dd>
            </div>
          </dl>
          <div class="pg-estado">
            <Pill tone={tieneLink ? 'moss' : 'slate'}>Link {tieneLink ? 'cargado' : 'sin cargar'}</Pill>
            <Pill tone={medios.length > 0 ? 'moss' : 'slate'}>
              {medios.length === 0
                ? 'Sin puntos de pago'
                : `${medios.length} ${medios.length === 1 ? 'punto de pago' : 'puntos de pago'}`}
            </Pill>
          </div>
        </aside>
      </div>
    </div>
  </div>
{/if}

<style>
  .pg-pad {
    padding-top: 16px;
    padding-bottom: 32px;
  }
  /* Dos columnas: lo que se edita, y al lado lo que el asistente hace con eso. */
  .pg-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 320px;
    gap: 16px;
    align-items: start;
  }
  .pg-main {
    display: flex;
    flex-direction: column;
    gap: 16px;
    min-width: 0;
  }
  @media (max-width: 920px) {
    .pg-grid {
      grid-template-columns: minmax(0, 1fr);
    }
  }

  .pg-bloque,
  .pg-aside {
    padding: 16px 18px;
  }
  .pg-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 10px;
  }
  .pg-titulo {
    margin: 0;
    font-size: 13px;
    font-weight: 600;
  }
  .pg-aside .pg-titulo {
    margin-bottom: 12px;
  }

  /* El sitio es la cifra de este bloque: grande, tabular y en la fuente de datos. */
  .pg-sitio {
    margin: 0 0 4px;
    font-family: var(--v2-mono);
    font-size: 22px;
    font-weight: 600;
    line-height: 1.25;
    overflow-wrap: anywhere;
    color: var(--v2-ink);
  }
  .pg-vacio {
    margin: 0 0 4px;
    font-size: 15px;
    font-weight: 600;
    color: var(--v2-slate);
  }
  .pg-nota {
    margin: 0;
  }
  .pg-ok {
    margin: 12px 0 0;
  }

  /* La lista de medios: nombre a la izquierda, lo que hay que hacer a la derecha. */
  .pg-lista {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .pg-lista li {
    display: grid;
    grid-template-columns: 160px minmax(0, 1fr);
    gap: 4px 16px;
    padding: 10px 0;
    border-top: 1px solid var(--v2-line-soft);
  }
  .pg-lista li:first-child {
    border-top: 0;
    padding-top: 2px;
  }
  .pg-medio {
    font-weight: 600;
    overflow-wrap: anywhere;
  }
  .pg-instruccion {
    overflow-wrap: anywhere;
  }
  @media (max-width: 560px) {
    .pg-lista li {
      grid-template-columns: minmax(0, 1fr);
    }
  }

  /* SettingsFormPanel reparte sus campos en una grilla: todo lo mio va en UN
     contenedor que ocupa el ancho entero. */
  .pg-form {
    grid-column: 1 / -1;
    display: flex;
    flex-direction: column;
    gap: 12px;
    min-width: 0;
  }
  .pg-texto {
    resize: vertical;
    min-height: 54px;
    line-height: 1.4;
    font-family: inherit;
  }

  /* El formulario de medios: una fila por medio. */
  .pg-fila {
    display: grid;
    grid-template-columns: 170px minmax(0, 1fr) auto;
    gap: 10px;
    align-items: start;
    padding-top: 12px;
    border-top: 1px solid var(--v2-line-soft);
  }
  .pg-campo-texto {
    position: relative;
  }
  .pg-contador {
    display: block;
    margin-top: 3px;
    text-align: right;
    font-size: 11px;
    font-variant-numeric: tabular-nums;
    color: var(--v2-slate);
  }
  .pg-contador-alto {
    color: var(--v2-clay);
  }
  .pg-quitar {
    margin-top: 22px;
  }
  @media (max-width: 640px) {
    .pg-fila {
      grid-template-columns: minmax(0, 1fr);
    }
    .pg-quitar {
      margin-top: 0;
      justify-self: start;
    }
  }

  /* El panel de reglas: se lee de corrido, sin tarjetas dentro de la tarjeta. */
  .pg-reglas {
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .pg-reglas dt {
    font-size: 12px;
    font-weight: 600;
    color: var(--v2-slate);
  }
  .pg-reglas dd {
    margin: 2px 0 0;
    font-size: 13px;
    line-height: 1.45;
  }
  .pg-estado {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 16px;
    padding-top: 14px;
    border-top: 1px solid var(--v2-line-soft);
  }
</style>
