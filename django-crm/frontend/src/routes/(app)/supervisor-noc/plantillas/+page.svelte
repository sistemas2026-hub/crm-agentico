<script>
  /**
   * Plantillas de trabajo.
   *
   * Qué anota y qué fotos saca el técnico en cada visita, y con qué labor sale
   * la orden. Se adoptan del catálogo de la plataforma y se ajustan, o se
   * arman desde cero, sin escribir JSON: el esquema lo arma el backend.
   *
   * LA LISTA DE TIPOS ES CERRADA A PROPÓSITO. Ver `campo/plantillas.py`: la
   * app y el servidor entienden distinto un booleano obligatorio, un texto con
   * mínimo, un entero o una firma, y en todos esos casos la orden queda
   * cerrada en el teléfono y trabada en el servidor. Acá se ofrece solo lo que
   * los dos lados hacen igual.
   */
  import { enhance } from '$app/forms';
  import PestanasNoc from '$lib/supervisor/PestanasNoc.svelte';
  import { goto } from '$app/navigation';
  import '../supervisor-noc.css';
  import NivelesDeRespuesta from './NivelesDeRespuesta.svelte';

  let { data, form } = $props();

  /** @param {any} x */
  const clonar = (x) => JSON.parse(JSON.stringify(x ?? null));

  /** Lo que se está editando. Se rehace cada vez que llega otra plantilla. */
  let borrador = $state(/** @type {any} */ (null));
  let nombre = $state('');
  let labor = $state('');
  /** Uno por línea, como se escriben y se leen (19/10/2026). */
  let asuntos = $state('');
  let plazoDias = $state(/** @type {number | null} */ (null));
  $effect(() => {
    const e = data.edicion;
    borrador = e?.definicion ? clonar(e.definicion) : null;
    nombre = e?.nombre ?? '';
    labor = e?.labor ?? '';
    asuntos = (e?.asuntos ?? []).join('\n');
    plazoDias = e?.plazo_dias ?? null;
  });

  let publicando = $state(false);

  const nombreDeLabor = (id) =>
    (data.labores ?? []).find((l) => l.id === id)?.texto ?? 'sin labor';
  const tipoTexto = (id) => (data.tipos ?? []).find((t) => t.id === id)?.texto ?? id;

  /** @param {'campos'|'evidencias'} lista @param {number} i @param {number} d */
  function mover(lista, i, d) {
    const arr = borrador[lista];
    const j = i + d;
    if (j < 0 || j >= arr.length) return;
    [arr[i], arr[j]] = [arr[j], arr[i]];
  }

  function agregarDato() {
    borrador.campos.push({ titulo: '', tipo: 'texto', obligatorio: true, paso: '' });
  }
  function agregarFoto() {
    borrador.evidencias.push({ titulo: '', obligatorio: true, paso: '', instrucciones: '' });
  }

  /** Los cuatro reportes que el técnico manda mientras trabaja. */
  const REPORTES = [
    { id: 'inicio', texto: 'Al llegar' },
    { id: 'avance', texto: 'Avance' },
    { id: 'bloqueo', texto: 'Bloqueo' },
    { id: 'cierre', texto: 'Cierre' }
  ];
  /** @param {string} momento */
  function agregarFotoDeReporte(momento) {
    borrador.fotos_de_reportes ??= {};
    (borrador.fotos_de_reportes[momento] ??= []).push({ titulo: '' });
  }

  /** Las opciones de una selección se escriben una por renglón. */
  const opcionesTexto = (c) => (c.opciones ?? []).join('\n');
  function ponerOpciones(c, texto) {
    c.opciones = texto.split('\n').map((s) => s.trim()).filter(Boolean);
  }

  /** Cómo lo ve el técnico: agrupado por paso, en el orden de la lista. */
  let vista = $derived.by(() => {
    if (!borrador) return [];
    const grupos = new Map();
    const de = (paso) => {
      const k = (paso ?? '').trim() || '—';
      if (!grupos.has(k)) grupos.set(k, { paso: k, datos: [], fotos: [] });
      return grupos.get(k);
    };
    for (const c of borrador.campos) de(c.paso).datos.push(c);
    for (const e of borrador.evidencias) de(e.paso).fotos.push(e);
    return [...grupos.values()];
  });

  /** El formulario de «+ Nueva plantilla» abierto (21/10/2026). */
  let creando = $state(false);
  let creandoAhora = $state(false);

  /** Tras adoptar o crear, se abre en el editor. */
  const alCrear = () => {
    creandoAhora = true;
    return async ({ result, update }) => {
      await update();
      creandoAhora = false;
      const id = result?.type === 'success' ? result.data?.abrir : null;
      if (id) {
        creando = false;
        await goto(`?editar=${id}`, { invalidateAll: true });
      }
    };
  };

  /** Los asuntos de una plantilla, cortos para la lista. @param {string[]} a */
  const asuntosCortos = (a) =>
    a.length <= 3 ? a.join(' · ') : `${a.slice(0, 3).join(' · ')} y ${a.length - 3} más`;

  const definicionDeCero = $derived(
    (data.catalogo ?? []).find((b) => b.codigo === 'trabajo_general')?.definicion ?? null
  );
</script>

<svelte:head>
  <title>Plantillas de trabajo · Supervisor NOC</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="" />
  <link
    href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;700&family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap"
    rel="stylesheet"
  />
</svelte:head>

<div class="snoc">
  <!-- v2-scroll: el UNICO contenedor que se desplaza. El marco de (app) es
       `overflow:hidden`; sin esto lo que no entra en la ventana queda
       recortado y no hay forma de llegar (ver supervisor-noc/+page.svelte). -->
  <div class="v2-scroll">
    <div class="snoc-lienzo">
    <!-- ============ CABECERA ============ -->
    <section class="snoc-panel" style="gap:var(--snoc-md);">
      <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-md);">
        <div class="snoc-pila-xs">
          <h1 class="snoc-h1">PLANTILLAS DE TRABAJO</h1>
          <p class="snoc-body snoc-secundario">
            Qué anota y qué fotos saca el técnico en cada visita, y con qué labor sale la
            orden. Un cambio se publica como versión nueva: las órdenes ya creadas no cambian.
          </p>
        </div>
        <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap;">
          <PestanasNoc activa="plantillas" />
        </div>
      </div>
      {#if form?.error}
        <p class="snoc-aviso snoc-error-txt" role="alert">{form.error}</p>
      {/if}
      {#if form?.hecho}
        <p class="snoc-aviso" role="status">{form.hecho}</p>
      {/if}
    </section>

    {#if data.error}
      <section class="snoc-panel">
        <p class="snoc-aviso snoc-error-txt">
          No se pudieron leer las plantillas. Si otras pantallas tampoco cargan, es el backend.
        </p>
      </section>
    {:else}
      <!-- ============ LAS DE LA EMPRESA ============ -->
      <section class="snoc-panel" style="gap:var(--snoc-sm);">
        <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
          <h2 class="snoc-h2">Las de la empresa</h2>
          {#if definicionDeCero && !creando}
            <button class="snoc-btn snoc-btn-primario" type="button" onclick={() => (creando = true)}>
              + Nueva plantilla
            </button>
          {/if}
        </div>

        <!-- ============ NUEVA PLANTILLA (21/10/2026) ============
             Pedido del usuario: un botón que cree la plantilla con sus asuntos.
             Nace con el formulario de «Trabajo general» —el backend rechaza una
             plantilla que no pide nada— y se abre en el editor para ajustarlo. -->
        {#if creando && definicionDeCero}
          <form method="POST" action="?/crear" use:enhance={alCrear}
                class="snoc-tarjeta snoc-pila" style="gap:var(--snoc-md);">
            <input type="hidden" name="definicion" value={JSON.stringify(definicionDeCero)} />
            <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap; align-items:end;">
              <label class="snoc-campo-grupo">
                <span class="snoc-label">Nombre</span>
                <input class="snoc-campo" name="nombre" required maxlength="120"
                       placeholder="Por ejemplo: Traslado de servicio" />
              </label>
              <label class="snoc-campo-grupo">
                <span class="snoc-label">Labor</span>
                <select class="snoc-select" name="labor">
                  <option value="">— sin labor —</option>
                  {#each data.labores as l (l.id)}<option value={l.id}>{l.texto}</option>{/each}
                </select>
              </label>
              <label class="snoc-campo-grupo">
                <span class="snoc-label">Plazo para hacerlo (días)</span>
                <input class="snoc-campo" type="number" name="plazo_dias" min="0" max="60"
                       placeholder="sin plazo" />
              </label>
            </div>
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Asuntos de WispHub que se despachan con esta plantilla</span>
              <textarea class="snoc-campo" name="asuntos" rows="4"
                        placeholder={'Uno por línea, como vienen en el ticket. Ej.:\nCambio De Domicilio'}></textarea>
              <span class="snoc-body-sm snoc-secundario">
                Al despachar un ticket con uno de estos asuntos, esta plantilla viene elegida.
                Un asunto va en una sola plantilla, y hace falta elegir la labor.
              </span>
            </label>
            <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap;">
              <button class="snoc-btn snoc-btn-primario" type="submit" disabled={creandoAhora}>
                {creandoAhora ? 'Creando…' : 'Crear plantilla'}
              </button>
              <button class="snoc-btn" type="button" onclick={() => (creando = false)}>Cancelar</button>
              <span class="snoc-body-sm snoc-secundario">
                Después se abre para ajustar qué anota y qué fotos saca el técnico.
              </span>
            </div>
          </form>
        {/if}

        {#if !(data.propias ?? []).length}
          <p class="snoc-body-sm snoc-secundario">
            Todavía no hay ninguna. Adoptá una del catálogo de abajo: queda lista para
            despachar y la podés ajustar.
          </p>
        {:else}
          <div class="snoc-pila" style="gap:var(--snoc-xs);">
            {#each data.propias as p (p.id)}
              <div class="snoc-tarjeta snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
                <div class="snoc-pila-xs" style="min-width:0;">
                  <span class="snoc-body">
                    <strong>{p.nombre}</strong>
                    {#if !p.activo}<span class="snoc-insignia snoc-insignia-neutra">apagada</span>{/if}
                  </span>
                  <span class="snoc-body-sm snoc-secundario">
                    {nombreDeLabor(p.labor)} ·
                    {p.datos} {p.datos === 1 ? 'dato' : 'datos'} ·
                    {p.fotos} {p.fotos === 1 ? 'foto' : 'fotos'}
                    {#if p.version} · versión {p.version}{/if}
                  </span>
                  <span class="snoc-body-sm snoc-secundario">
                    {#if (p.asuntos ?? []).length}
                      Asuntos: {asuntosCortos(p.asuntos)}
                    {:else}
                      Sin asuntos: Despacho no la elige sola por el asunto del ticket.
                    {/if}
                  </span>
                  {#if !p.editable}
                    <span class="snoc-body-sm snoc-secundario">
                      Armada a mano con cosas que el editor no maneja: se puede seguir usando,
                      pero no se edita acá.
                    </span>
                  {/if}
                </div>
                <div class="snoc-fila" style="gap:var(--snoc-xs);">
                  <a class="snoc-btn" href="?editar={p.id}">{p.editable ? 'Editar' : 'Ver'}</a>
                  <form method="POST" action="?/activar" use:enhance>
                    <input type="hidden" name="id" value={p.id} />
                    <input type="hidden" name="activo" value={String(!p.activo)} />
                    <button class="snoc-btn" type="submit">
                      {p.activo ? 'Apagar' : 'Encender'}
                    </button>
                  </form>
                </div>
              </div>
            {/each}
          </div>
        {/if}
      </section>

      <!-- ============ EL EDITOR ============ -->
      {#if data.edicionError}
        <section class="snoc-panel">
          <p class="snoc-aviso snoc-error-txt">{data.edicionError}</p>
        </section>
      {:else if data.edicion}
        <section class="snoc-panel" style="gap:var(--snoc-md);">
          <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
            <h2 class="snoc-h2">{data.edicion.nombre}</h2>
            <a class="snoc-btn" href="/supervisor-noc/plantillas">Cerrar</a>
          </div>

          {#if !borrador}
            <div class="snoc-hueco">
              <span class="snoc-hueco-rotulo">No se edita acá</span>
              <p class="snoc-hueco-motivo">
                Esta plantilla se armó a mano y tiene cosas que el editor no maneja.
                Publicar encima las borraría, así que no se ofrece:
              </p>
              <ul class="snoc-body-sm">
                {#each data.edicion.por_que_no ?? [] as m}<li>{m}</li>{/each}
              </ul>
            </div>
          {:else}
            {#if data.edicion.ordenes_vivas}
              <p class="snoc-aviso">
                {data.edicion.ordenes_vivas}
                {data.edicion.ordenes_vivas === 1 ? 'orden abierta usa' : 'órdenes abiertas usan'}
                esta plantilla. No cambian al publicar: conservan su versión.
              </p>
            {/if}

            <form method="POST" action="?/publicar" class="snoc-pila" style="gap:var(--snoc-md);"
                  use:enhance={() => {
                    publicando = true;
                    return async ({ update }) => { await update({ reset: false }); publicando = false; };
                  }}>
              <input type="hidden" name="id" value={data.edicion.id} />
              <input type="hidden" name="definicion" value={JSON.stringify(borrador)} />

              <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap;">
                <label class="snoc-campo-grupo">
                  <span class="snoc-label">Nombre</span>
                  <input class="snoc-campo" name="nombre" bind:value={nombre} required maxlength="120" />
                </label>
                <label class="snoc-campo-grupo">
                  <span class="snoc-label">Labor</span>
                  <select class="snoc-select" name="labor" bind:value={labor}>
                    <option value="">— sin labor (no se reparte) —</option>
                    {#each data.labores as l (l.id)}<option value={l.id}>{l.texto}</option>{/each}
                  </select>
                </label>
                <label class="snoc-campo-grupo">
                  <span class="snoc-label">Duración estimada (minutos)</span>
                  <input class="snoc-campo" type="number" min="1" max="1440"
                         bind:value={borrador.duracion_estimada_minutos} />
                </label>
                <label class="snoc-campo-grupo">
                  <span class="snoc-label">Plazo para hacerlo (días)</span>
                  <input class="snoc-campo" type="number" name="plazo_dias" min="0" max="60"
                         bind:value={plazoDias} placeholder="sin plazo" />
                </label>
              </div>

              <!-- LO QUE DESPACHO USA PARA LLENAR EL FORMULARIO SOLO (19/10/2026).
                   El asunto del ticket elige esta plantilla; el plazo, contado
                   desde que se creó el ticket, propone «para cuándo». -->
              <label class="snoc-campo-grupo">
                <span class="snoc-label">Asuntos de WispHub que se despachan con esta plantilla</span>
                <textarea class="snoc-campo" name="asuntos" rows="3" bind:value={asuntos}
                          placeholder={'Uno por línea, como vienen en el ticket. Ej.:\nCambio De Domicilio'}></textarea>
                <span class="snoc-body-sm snoc-secundario">
                  Al despachar un ticket con uno de estos asuntos, esta plantilla viene elegida, y
                  «para cuándo» se propone como la fecha de creación del ticket más el plazo.
                  Un asunto va en una sola plantilla.
                </span>
              </label>

              <div class="snoc-dos-columnas" style="gap:var(--snoc-md); align-items:start;">
                <!-- ---- lo que se edita ---- -->
                <div class="snoc-pila" style="gap:var(--snoc-md);">
                  <div class="snoc-pila" style="gap:var(--snoc-xs);">
                    <h3 class="snoc-h3">Datos que anota</h3>
                    {#each borrador.campos as c, i (c)}
                      <div class="snoc-tarjeta snoc-pila" style="gap:var(--snoc-xs);">
                        <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
                          <input class="snoc-campo" style="flex:1; min-width:12rem;"
                                 placeholder="Qué se anota" bind:value={c.titulo}
                                 aria-label="Nombre del dato {i + 1}" maxlength="120" />
                          <select class="snoc-select" bind:value={c.tipo} aria-label="Tipo del dato {i + 1}">
                            {#each data.tipos as t (t.id)}<option value={t.id}>{t.texto}</option>{/each}
                          </select>
                          <label class="snoc-body-sm">
                            <input type="checkbox" bind:checked={c.obligatorio} /> obligatorio
                          </label>
                          <button type="button" class="snoc-btn" onclick={() => mover('campos', i, -1)}
                                  aria-label="Subir">↑</button>
                          <button type="button" class="snoc-btn" onclick={() => mover('campos', i, 1)}
                                  aria-label="Bajar">↓</button>
                          <button type="button" class="snoc-btn snoc-btn-error"
                                  onclick={() => borrador.campos.splice(i, 1)} aria-label="Quitar">✕</button>
                        </div>
                        <span class="snoc-body-sm snoc-secundario">
                          {(data.tipos ?? []).find((t) => t.id === c.tipo)?.ayuda}
                        </span>
                        {#if c.tipo === 'numero'}
                          <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
                            <input class="snoc-campo" style="width:6rem;" placeholder="Unidad"
                                   bind:value={c.unidad} maxlength="16" aria-label="Unidad" />
                            <input class="snoc-campo" style="width:7rem;" type="number" step="any"
                                   placeholder="Mínimo" bind:value={c.min} aria-label="Mínimo" />
                            <input class="snoc-campo" style="width:7rem;" type="number" step="any"
                                   placeholder="Máximo" bind:value={c.max} aria-label="Máximo" />
                          </div>
                        {:else if c.tipo === 'seleccion'}
                          <textarea class="snoc-campo" rows="3" placeholder="Una opción por renglón"
                                    aria-label="Opciones"
                                    value={opcionesTexto(c)}
                                    oninput={(ev) => ponerOpciones(c, ev.currentTarget.value)}></textarea>
                          <!-- «Otro» con texto (18/10/2026): la opción la agrega la
                               plataforma; al elegirla, el técnico tiene que
                               escribir qué fue. -->
                          <label class="snoc-body-sm">
                            <input type="checkbox" bind:checked={c.permite_otro} />
                            Permitir «Otro» con texto (el técnico escribe qué fue)
                          </label>
                        {/if}
                        <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
                          <input class="snoc-campo" style="flex:1; min-width:10rem;"
                                 placeholder="Ayuda para el técnico (opcional)" bind:value={c.ayuda}
                                 aria-label="Ayuda" maxlength="400" />
                          <input class="snoc-campo" style="width:11rem;" placeholder="Paso (opcional)"
                                 bind:value={c.paso} aria-label="Paso" maxlength="120" />
                        </div>
                      </div>
                    {/each}
                    <button type="button" class="snoc-btn" onclick={agregarDato}>+ Agregar dato</button>
                  </div>

                  <div class="snoc-pila" style="gap:var(--snoc-xs);">
                    <h3 class="snoc-h3">Fotos que saca</h3>
                    {#each borrador.evidencias as e, i (e)}
                      <div class="snoc-tarjeta snoc-pila" style="gap:var(--snoc-xs);">
                        <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
                          <input class="snoc-campo" style="flex:1; min-width:12rem;"
                                 placeholder="De qué es la foto" bind:value={e.titulo}
                                 aria-label="Nombre de la foto {i + 1}" maxlength="120" />
                          <label class="snoc-body-sm">
                            <input type="checkbox" bind:checked={e.obligatorio} /> obligatoria
                          </label>
                          <button type="button" class="snoc-btn" onclick={() => mover('evidencias', i, -1)}
                                  aria-label="Subir">↑</button>
                          <button type="button" class="snoc-btn" onclick={() => mover('evidencias', i, 1)}
                                  aria-label="Bajar">↓</button>
                          <button type="button" class="snoc-btn snoc-btn-error"
                                  onclick={() => borrador.evidencias.splice(i, 1)} aria-label="Quitar">✕</button>
                        </div>
                        <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
                          <input class="snoc-campo" style="flex:1; min-width:10rem;"
                                 placeholder="Qué tiene que verse (opcional)" bind:value={e.instrucciones}
                                 aria-label="Instrucciones" maxlength="400" />
                          <input class="snoc-campo" style="width:11rem;" placeholder="Paso (opcional)"
                                 bind:value={e.paso} aria-label="Paso" maxlength="120" />
                        </div>
                      </div>
                    {/each}
                    <button type="button" class="snoc-btn" onclick={agregarFoto}>+ Agregar foto</button>
                  </div>

                  <!-- LAS FOTOS DE CADA REPORTE. Son otra cosa que las de arriba:
                       aquellas se exigen para cerrar; estas se ofrecen mientras
                       el técnico reporta, y nunca retienen el reporte. -->
                  {#if borrador.fotos_de_reportes}
                    <div class="snoc-pila" style="gap:var(--snoc-xs);">
                      <h3 class="snoc-h3">Fotos en los reportes</h3>
                      <p class="snoc-body-sm snoc-secundario">
                        Las que el técnico puede adjuntar al reportar. Son opcionales: si
                        no la saca, el reporte se guarda igual.
                      </p>
                      {#each REPORTES as r (r.id)}
                        <div class="snoc-tarjeta snoc-pila" style="gap:var(--snoc-xs);">
                          <span class="snoc-label">{r.texto}</span>
                          {#each borrador.fotos_de_reportes[r.id] ?? [] as e, i (e)}
                            <div class="snoc-fila" style="gap:var(--snoc-xs);">
                              <input class="snoc-campo" style="flex:1; min-width:12rem;"
                                     placeholder="De qué es la foto" bind:value={e.titulo}
                                     aria-label="Foto {i + 1} del reporte {r.texto}" maxlength="120" />
                              <button type="button" class="snoc-btn snoc-btn-error"
                                      onclick={() => borrador.fotos_de_reportes[r.id].splice(i, 1)}
                                      aria-label="Quitar">✕</button>
                            </div>
                          {:else}
                            <span class="snoc-body-sm snoc-secundario">Este reporte no pide foto.</span>
                          {/each}
                          {#if (borrador.fotos_de_reportes[r.id] ?? []).length < 5}
                            <button type="button" class="snoc-btn" style="align-self:flex-start;"
                                    onclick={() => agregarFotoDeReporte(r.id)}>+ Foto</button>
                          {/if}
                        </div>
                      {/each}
                    </div>
                  {/if}
                </div>

                <!-- ---- cómo lo ve el técnico ---- -->
                <aside class="snoc-tarjeta snoc-pila" style="gap:var(--snoc-sm);">
                  <h3 class="snoc-h3">Así lo ve el técnico</h3>
                  {#each vista as g (g.paso)}
                    <div class="snoc-pila-xs">
                      {#if g.paso !== '—'}<span class="snoc-label">{g.paso}</span>{/if}
                      {#each g.datos as c}
                        <span class="snoc-body-sm">
                          {c.titulo || '(sin nombre)'}{c.obligatorio ? ' *' : ''}
                          <span class="snoc-secundario">
                            · {tipoTexto(c.tipo)}{c.tipo === 'numero' && c.unidad ? ` en ${c.unidad}` : ''}
                            {#if c.tipo === 'checklist'}(Hecho / No aplica){/if}
                            {#if c.tipo === 'seleccion'}({(c.opciones ?? []).length} opciones{c.permite_otro ? ' + Otro' : ''}){/if}
                          </span>
                        </span>
                      {/each}
                      {#each g.fotos as e}
                        <span class="snoc-body-sm">
                          📷 {e.titulo || '(sin nombre)'}{e.obligatorio ? ' *' : ''}
                        </span>
                      {/each}
                    </div>
                  {/each}
                  {#if borrador.fotos_de_reportes}
                    <div class="snoc-pila-xs">
                      <span class="snoc-label">Al reportar puede adjuntar</span>
                      {#each REPORTES as r (r.id)}
                        {#if (borrador.fotos_de_reportes[r.id] ?? []).length}
                          <span class="snoc-body-sm">
                            {r.texto}:
                            <span class="snoc-secundario">
                              {borrador.fotos_de_reportes[r.id].map((e) => e.titulo || '(sin nombre)').join(', ')}
                            </span>
                          </span>
                        {/if}
                      {/each}
                    </div>
                  {/if}
                  <span class="snoc-body-sm snoc-secundario">* obligatorio para cerrar la orden.</span>
                </aside>
              </div>

              <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap;">
                <button class="snoc-btn snoc-btn-primario" type="submit" disabled={publicando}>
                  {publicando ? 'Guardando…' : 'Guardar'}
                </button>
                <span class="snoc-body-sm snoc-secundario">
                  Guarda nombre, labor, plazo y asuntos. Si cambiaste lo que anota el técnico, sale
                  una versión nueva: las órdenes ya creadas no cambian.
                </span>
              </div>
            </form>
          {/if}
        </section>
      {/if}

      <!-- ============ NIVELES DE RESPUESTA (24/10/2026) ============ -->
      <NivelesDeRespuesta {...data.niveles} />

      <!-- ============ EL CATÁLOGO ============ -->
      <section class="snoc-panel" style="gap:var(--snoc-sm);">
        <div class="snoc-pila-xs">
          <h2 class="snoc-h2">Catálogo para empezar</h2>
          <p class="snoc-body-sm snoc-secundario">
            Plantillas de partida que trae la plataforma, armadas a partir de los trabajos que
            más visitas generan. Al adoptarla queda como propia y la ajustás a como trabaja tu
            equipo.
          </p>
        </div>
        <div class="snoc-pila" style="gap:var(--snoc-xs);">
          {#each data.catalogo as b (b.codigo)}
            <div class="snoc-tarjeta snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
              <div class="snoc-pila-xs" style="min-width:0;">
                <span class="snoc-body"><strong>{b.nombre}</strong></span>
                <span class="snoc-body-sm snoc-secundario">
                  {nombreDeLabor(b.labor)} · {b.descripcion}
                </span>
                <span class="snoc-body-sm snoc-secundario">
                  {b.definicion.campos.length} datos · {b.definicion.evidencias.length} fotos
                </span>
              </div>
              {#if b.adoptada}
                <span class="snoc-insignia snoc-insignia-neutra">ya la tenés</span>
              {:else}
                <form method="POST" action="?/adoptar" use:enhance={alCrear}>
                  <input type="hidden" name="base" value={b.codigo} />
                  <button class="snoc-btn" type="submit">Adoptar</button>
                </form>
              {/if}
            </div>
          {/each}
        </div>

        <!-- Crear desde cero vive arriba, en «+ Nueva plantilla» (21/10/2026):
             aca abajo, debajo del catalogo, nadie lo encontraba. -->
      </section>
    {/if}
    </div>
  </div>
</div>
