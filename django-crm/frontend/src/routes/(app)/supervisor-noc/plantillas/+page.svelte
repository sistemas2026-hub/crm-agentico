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
   *
   * REDISEÑO DEL 21/11/2026 (maqueta aprobada):
   *   - Tres pestañas: las de la empresa, niveles de respuesta y catálogo. Antes
   *     iban apiladas, con Niveles en el medio.
   *   - El editor se abre en un panel ancho al costado, con el teléfono a la
   *     derecha; antes aparecía entre la lista y Niveles, sin moverse hasta él.
   *   - «+ Nueva plantilla» abre su formulario en otro panel.
   *   - Encender/apagar es un interruptor en la fila; el resultado de cada
   *     acción sale en un aviso a la vista, no arriba de todo.
   *   - Se avisa de cambios sin guardar al cerrar el editor, y se puede
   *     duplicar la plantilla abierta (usa la misma acción de crear).
   */
  import { enhance } from '$app/forms';
  import { goto } from '$app/navigation';
  import { page } from '$app/state';
  import { untrack } from 'svelte';
  import '../supervisor-noc.css';
  import NivelesDeRespuesta from './NivelesDeRespuesta.svelte';
  import Pestanas from '$lib/supervisor/ui/Pestanas.svelte';
  import PanelLateral from '$lib/supervisor/ui/PanelLateral.svelte';
  import { avisar } from '$lib/supervisor/ui/avisos.svelte.js';

  let { data, form } = $props();

  /** @param {any} x */
  const clonar = (x) => JSON.parse(JSON.stringify(x ?? null));

  //  Lo que se está editando. Arranca con lo que trajo el servidor —así la
  //  primera pintura ya muestra el editor y no «No se edita acá»— y se rehace
  //  cada vez que llega otra plantilla (el $effect de abajo).
  const inicial = untrack(() => data.edicion);
  let borrador = $state(/** @type {any} */ (inicial?.definicion ? clonar(inicial.definicion) : null));
  let nombre = $state(inicial?.nombre ?? '');
  let labor = $state(inicial?.labor ?? '');
  /** Uno por línea, como se escriben y se leen (19/10/2026). */
  let asuntos = $state((inicial?.asuntos ?? []).join('\n'));
  let plazoDias = $state(/** @type {number | null} */ (inicial?.plazo_dias ?? null));
  /** Lo que llegó del servidor, para saber si hay cambios sin guardar. */
  //  Vacío hasta que el efecto lo fija: mientras tanto no hay «cambios sin
  //  guardar» que decir (ni en el servidor ni antes de hidratar).
  let original = $state('');
  $effect(() => {
    const e = data.edicion;
    borrador = e?.definicion ? clonar(e.definicion) : null;
    nombre = e?.nombre ?? '';
    labor = e?.labor ?? '';
    asuntos = (e?.asuntos ?? []).join('\n');
    plazoDias = e?.plazo_dias ?? null;
    //  untrack: leer el borrador acá haría que cada edición volviera a
    //  correr este efecto y pisara lo escrito con lo del servidor.
    original = untrack(foto);
  });
  function foto() {
    return JSON.stringify([borrador, nombre, labor, asuntos, plazoDias]);
  }
  const sinGuardar = $derived(!!data.edicion && original !== '' && foto() !== original);

  let publicando = $state(false);

  /** @type {string} */
  let pestana = $state(page.url.searchParams.get('pestana') ?? 'propias');

  const nombreDeLabor = (/** @type {string} */ id) => (data.labores ?? []).find((/** @type {any} */ l) => l.id === id)?.texto ?? 'sin labor';
  const tipoTexto = (/** @type {string} */ id) => (data.tipos ?? []).find((/** @type {any} */ t) => t.id === id)?.texto ?? id;

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
    borrador.evidencias.push({
      titulo: '', obligatorio: true, paso: '', instrucciones: '',
      //  Sin marcar: una foto se toma. La captura es la excepción, y se dice.
      es_captura: false,
      //  Sin marcar: la foto viaja al ticket con las demás.
      solo_en_la_plataforma: false
    });
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

  //  LOS BOTONES DE CADA PASO (26/11/2026). En qué paso sale «Ver el
  //  contrato» y en cuál «Reportar». Si ningún paso los marca, la app los
  //  muestra al final de todos, como antes.
  const BOTONES_DE_PASO = [
    { id: 'contrato', texto: 'Ver el contrato' },
    { id: 'reportar', texto: 'Reportar' },
    //  El recuadro con la IP que asignó el sistema, para copiarla (26/11/2026).
    { id: 'ip', texto: 'IP asignada (para copiar)' },
    //  Activar la ONU en la red con el serial del paso (26/11/2026).
    { id: 'onu', texto: 'Activar la ONU' }
  ];
  /** Los pasos que tiene la plantilla, en el orden en que aparecen. */
  let pasosDeLaPlantilla = $derived.by(() => {
    if (!borrador) return [];
    const vistos = new Map();
    for (const x of [...(borrador.campos ?? []), ...(borrador.evidencias ?? [])]) {
      const p = (x.paso ?? '').trim();
      if (p && !vistos.has(p.toLowerCase())) vistos.set(p.toLowerCase(), p);
    }
    return [...vistos.values()];
  });
  /** @param {string} paso @param {string} boton */
  const tieneBoton = (paso, boton) =>
    (borrador?.botones_por_paso?.[paso] ?? []).includes(boton);
  /** @param {string} paso @param {string} boton @param {boolean} si */
  function ponerBoton(paso, boton, si) {
    borrador.botones_por_paso ??= {};
    const l = new Set(borrador.botones_por_paso[paso] ?? []);
    if (si) l.add(boton);
    else l.delete(boton);
    if (l.size) borrador.botones_por_paso[paso] = [...l];
    else delete borrador.botones_por_paso[paso];
  }
  /** Lo que se guarda: sin las marcas de un paso que ya no existe (se renombró
   *  o se borró), que el servidor rechazaría con razón. */
  function paraGuardar(/** @type {any} */ b) {
    if (!b?.botones_por_paso) return b;
    const existen = new Set(pasosDeLaPlantilla.map((p) => p.toLowerCase()));
    const botones = Object.fromEntries(
      Object.entries(b.botones_por_paso).filter(([p]) => existen.has(p.trim().toLowerCase()))
    );
    return { ...b, botones_por_paso: botones };
  }

  /** Las opciones de una selección se escriben una por renglón. */
  const opcionesTexto = (/** @type {any} */ c) => (c.opciones ?? []).join('\n');
  /** @param {any} c @param {string} texto */
  function ponerOpciones(c, texto) {
    c.opciones = texto.split('\n').map((s) => s.trim()).filter(Boolean);
  }

  /** Cómo lo ve el técnico: agrupado por paso, en el orden de la lista. */
  let vista = $derived.by(() => {
    if (!borrador) return [];
    const grupos = new Map();
    const de = (/** @type {string} */ paso) => {
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

  /** Tras adoptar, crear o duplicar, se abre en el editor. */
  const alCrear = () => {
    creandoAhora = true;
    return async (/** @type {any} */ { result, update }) => {
      await update();
      creandoAhora = false;
      if (result?.type === 'failure') avisar(result.data?.error ?? 'No se pudo crear.', { tono: 'error' });
      const id = result?.type === 'success' ? result.data?.abrir : null;
      if (id) {
        creando = false;
        if (result.data?.hecho) avisar(result.data.hecho);
        await goto(`?editar=${id}`, { invalidateAll: true });
      }
    };
  };

  //  EL MATERIAL QUE SE PRECARGA (26/11/2026). Se guarda aparte: es de la
  //  empresa para este tipo de trabajo, no de una versión de la plantilla.
  /** @typedef {{ codigo: string, cantidad: string, campo: string }} LineaDeMaterial */
  const comoLineas = (/** @type {any} */ e) =>
    /** @type {LineaDeMaterial[]} */ ((e?.material_habitual ?? []).map((/** @type {any} */ x) => ({
      codigo: x.codigo, cantidad: x.cantidad == null ? '' : String(x.cantidad), campo: x.campo ?? ''
    })));
  /** Los campos de número o de texto de la plantilla: de ahí puede salir la
   *  cantidad de un material (los metros de fibra) o la SERIE de un equipo (el
   *  serial de la ONU que el técnico escanea). */
  let camposDeNumero = $derived(
    (borrador?.campos ?? [])
      .filter((/** @type {any} */ c) => ['numero', 'texto'].includes(c.tipo) && (c.titulo ?? '').trim())
      .map((/** @type {any} */ c) => c.titulo.trim())
  );
  let materialHabitual = $state(comoLineas(untrack(() => data.edicion)));
  $effect(() => {
    materialHabitual = comoLineas(data.edicion);
  });
  let guardandoMaterial = $state(false);
  /** Los materiales activos del catálogo, por código, para el nombre y la unidad. */
  let materialPorCodigo = $derived(
    new Map((data.materiales ?? []).map((/** @type {any} */ m) => [m.codigo, m]))
  );

  //  LOS PUNTOS DE TV (26/11/2026).
  const tvDe = (/** @type {any} */ e) => {
    const t = e?.puntos_de_tv ?? {};
    return {
      activo: !!t.activo, conector: t.conector ?? '', por_punto: String(t.conectores_por_punto ?? 2),
      entrada: String(t.conectores_de_entrada ?? 2), maximo: String(t.maximo_de_puntos ?? 5),
      cable: t.cable ?? '',
      spliters: (t.spliters ?? []).map((/** @type {any} */ s) => ({ codigo: s.codigo, salidas: String(s.salidas) }))
    };
  };
  let tv = $state(tvDe(untrack(() => data.edicion)));
  $effect(() => {
    tv = tvDe(data.edicion);
  });
  let guardandoTv = $state(false);
  /** Lo que lleva cada cantidad de puntos, para que quien edita vea la cuenta. */
  let cuentaDeTv = $derived.by(() => {
    const pp = Number(tv.por_punto), en = Number(tv.entrada), max = Number(tv.maximo);
    if (![pp, en, max].every(Number.isFinite) || max < 1) return [];
    const salidas = tv.spliters.map((s) => Number(s.salidas)).filter(Number.isFinite).sort((a, b) => a - b);
    return Array.from({ length: Math.min(max, 10) }, (_, i) => {
      const n = i + 1;
      const spl = n >= 2 ? salidas.find((x) => x >= n) : null;
      return `${n}: ${pp * n + (n >= 2 ? en : 0)} conectores${n >= 2 ? (spl ? ` + spliter de ${spl}` : ' + spliter (ninguno alcanza)') : ''}`;
    });
  });

  /** @param {string} exito */
  const conAviso = (exito) => () => async (/** @type {any} */ { result, update }) => {
    await update({ reset: false });
    if (result?.type === 'success') avisar(result.data?.hecho ?? exito);
    else if (result?.type === 'failure') avisar(result.data?.error ?? 'No se pudo guardar.', { tono: 'error' });
  };

  /** Los asuntos de una plantilla, cortos para la lista. @param {string[]} a */
  const asuntosCortos = (a) =>
    a.length <= 3 ? a.join(' · ') : `${a.slice(0, 3).join(' · ')} y ${a.length - 3} más`;

  const definicionDeCero = $derived(
    (data.catalogo ?? []).find((/** @type {any} */ b) => b.codigo === 'trabajo_general')?.definicion ?? null
  );

  const editorAbierto = $derived(!!data.edicion || !!data.edicionError);
  function cerrarEditor() {
    if (sinGuardar && !confirm('Hay cambios sin guardar en esta plantilla. ¿Cerrar igual?')) return;
    goto('/supervisor-noc/plantillas', { keepFocus: true, noScroll: true });
  }

  const pestanas = $derived([
    { id: 'propias', texto: 'Las de la empresa', n: (data.propias ?? []).length },
    { id: 'niveles', texto: 'Niveles de respuesta', n: (data.niveles?.asuntos ?? []).length },
    { id: 'catalogo', texto: 'Catálogo para empezar', n: (data.catalogo ?? []).length }
  ]);
</script>

<svelte:head>
  <title>Plantillas de trabajo · Supervisor NOC</title>
</svelte:head>

<div class="snoc">
  <!-- v2-scroll: el UNICO contenedor que se desplaza. El marco de (app) es
       `overflow:hidden`; sin esto lo que no entra en la ventana queda
       recortado y no hay forma de llegar (ver supervisor-noc/+page.svelte). -->
  <div class="v2-scroll">
    <div class="snoc-lienzo">
      <header class="snoc-encabezado">
        <div class="snoc-encabezado-texto">
          <h1 class="snoc-h1">Plantillas de trabajo</h1>
          <p class="snoc-bajada">
            Qué anota y qué fotos saca el técnico en cada visita, y con qué labor sale la orden. Un
            cambio se publica como versión nueva: las órdenes ya creadas no cambian.
          </p>
        </div>
        {#if definicionDeCero && !data.error}
          <div class="snoc-encabezado-acciones">
            <button class="snoc-btn snoc-btn-primario" type="button" onclick={() => (creando = true)}>+ Nueva plantilla</button>
          </div>
        {/if}
      </header>

      {#if data.error}
        <p class="snoc-recuadro snoc-recuadro-error">
          No se pudieron leer las plantillas. Si otras pantallas tampoco cargan, es el backend.
        </p>
      {:else}
        <Pestanas {pestanas} bind:activa={pestana} etiqueta="Secciones de Plantillas" />

        {#if pestana === 'propias'}
          <section class="snoc-panel" style="padding:0;" aria-label="Las de la empresa">
            {#if !(data.propias ?? []).length}
              <p class="snoc-body-sm snoc-secundario" style="margin:0; padding:16px 18px;">
                Todavía no hay ninguna. Adoptá una del catálogo: queda lista para despachar y la podés ajustar.
              </p>
            {:else}
              <div class="snoc-tabla-caja">
                <table class="snoc-tabla">
                  <thead>
                    <tr><th>Plantilla</th><th>Labor</th><th>Pide</th><th>Asuntos que la eligen solos</th><th>En Despacho</th><th></th></tr>
                  </thead>
                  <tbody>
                    {#each data.propias as p (p.id)}
                      <tr>
                        <td>
                          <strong>{p.nombre}</strong>
                          {#if !p.editable}
                            <div class="snoc-body-sm" style="color:var(--snoc-alerta);">Armada a mano: se usa, pero no se edita acá</div>
                          {/if}
                        </td>
                        <td><span class="snoc-tag">{nombreDeLabor(p.labor)}</span></td>
                        <td class="snoc-body-sm">
                          {p.datos} {p.datos === 1 ? 'dato' : 'datos'} · {p.fotos} {p.fotos === 1 ? 'foto' : 'fotos'}
                          {#if p.version}<div class="snoc-secundario">versión {p.version}</div>{/if}
                        </td>
                        <td class="snoc-body-sm" style="max-width:340px;">
                          {#if (p.asuntos ?? []).length}
                            {asuntosCortos(p.asuntos)}
                          {:else}
                            <span style="color:var(--snoc-alerta);">Sin asuntos: Despacho no la elige sola por el asunto del ticket.</span>
                          {/if}
                        </td>
                        <td>
                          <form method="POST" action="?/activar" use:enhance={conAviso(p.activo ? 'Plantilla apagada.' : 'Plantilla encendida.')}>
                            <input type="hidden" name="id" value={p.id} />
                            <input type="hidden" name="activo" value={String(!p.activo)} />
                            <button
                              class="pl-sw"
                              class:pl-sw-on={p.activo}
                              type="submit"
                              role="switch"
                              aria-checked={p.activo}
                              aria-label="{p.activo ? 'Apagar' : 'Encender'} «{p.nombre}» en Despacho"
                            ></button>
                          </form>
                        </td>
                        <td><a class="snoc-btn" href="?editar={p.id}" data-sveltekit-noscroll>{p.editable ? 'Editar' : 'Ver'}</a></td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            {/if}
          </section>
        {:else if pestana === 'niveles'}
          <NivelesDeRespuesta {...data.niveles} />
        {:else}
          <p class="snoc-bajada">
            Plantillas de partida que trae la plataforma, armadas a partir de los trabajos que más
            visitas generan. Al adoptarla queda como propia y la ajustás a como trabaja tu equipo.
          </p>
          <div class="pl-catalogo">
            {#each data.catalogo as b (b.codigo)}
              <div class="snoc-panel pl-base">
                <div class="snoc-fila-sep"><strong>{b.nombre}</strong><span class="snoc-tag">{nombreDeLabor(b.labor)}</span></div>
                <span class="snoc-body-sm snoc-secundario">{b.descripcion}</span>
                <span class="snoc-body-sm snoc-secundario">{b.definicion.campos.length} datos · {b.definicion.evidencias.length} fotos</span>
                <div>
                  {#if b.adoptada}
                    <span class="snoc-insignia snoc-insignia-ok">Ya la tenés</span>
                  {:else}
                    <form method="POST" action="?/adoptar" use:enhance={alCrear}>
                      <input type="hidden" name="base" value={b.codigo} />
                      <button class="snoc-btn snoc-btn-primario" type="submit" disabled={creandoAhora}>Adoptar</button>
                    </form>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        {/if}
      {/if}
    </div>
  </div>
</div>

<!-- ============ NUEVA PLANTILLA (21/10/2026) ============
     Nace con el formulario de «Trabajo general» —el backend rechaza una
     plantilla que no pide nada— y se abre en el editor para ajustarlo. -->
<PanelLateral abierto={creando && !!definicionDeCero} antetitulo="Nueva plantilla" titulo="Empieza como «Trabajo general»" alCerrar={() => (creando = false)}>
  <form id="pl-crear" method="POST" action="?/crear" use:enhance={alCrear} class="snoc-pila" style="gap:14px;">
    <input type="hidden" name="definicion" value={JSON.stringify(definicionDeCero)} />
    <label class="snoc-campo-grupo">
      <span class="snoc-label">Nombre</span>
      <input class="snoc-campo" name="nombre" required maxlength="120" placeholder="Por ejemplo: Traslado de servicio" />
    </label>
    <div class="pl-par">
      <label class="snoc-campo-grupo">
        <span class="snoc-label">Labor</span>
        <select class="snoc-select" name="labor">
          <option value="">— sin labor (no se reparte) —</option>
          {#each data.labores ?? [] as l (l.id)}<option value={l.id}>{l.texto}</option>{/each}
        </select>
      </label>
      <label class="snoc-campo-grupo">
        <span class="snoc-label">Plazo para hacerlo (días)</span>
        <input class="snoc-campo" type="number" name="plazo_dias" min="0" max="60" placeholder="sin plazo" />
      </label>
    </div>
    <label class="snoc-campo-grupo">
      <span class="snoc-label">Asuntos de WispHub que se despachan con esta plantilla</span>
      <textarea class="snoc-campo" name="asuntos" rows="4" placeholder={'Uno por línea, como vienen en el ticket. Ej.:\nCambio De Domicilio'}></textarea>
      <span class="snoc-body-sm snoc-secundario">
        Al despachar un ticket con uno de estos asuntos, esta plantilla viene elegida. Un asunto va en
        una sola plantilla, y hace falta elegir la labor.
      </span>
    </label>
  </form>
  {#snippet pie()}
    <div class="snoc-fila-sep" style="flex-wrap:wrap;">
      <span class="snoc-body-sm snoc-secundario">Después se abre para ajustar qué anota y qué fotos saca el técnico.</span>
      <div class="snoc-fila">
        <button class="snoc-btn" type="button" onclick={() => (creando = false)}>Cancelar</button>
        <button class="snoc-btn snoc-btn-primario" type="submit" form="pl-crear" disabled={creandoAhora}>
          {creandoAhora ? 'Creando…' : 'Crear plantilla'}
        </button>
      </div>
    </div>
  {/snippet}
</PanelLateral>

<!-- ============ EL EDITOR ============ -->
<PanelLateral
  abierto={editorAbierto}
  ancho="muy-ancho"
  antetitulo={data.edicion ? (borrador ? 'Editar plantilla' : 'Ver plantilla') : 'Plantilla'}
  titulo={data.edicion?.nombre ?? 'No se pudo abrir'}
  alCerrar={cerrarEditor}
>
  {#snippet acciones()}
    {#if sinGuardar}<span class="snoc-insignia snoc-insignia-alerta">Cambios sin guardar</span>{/if}
  {/snippet}

  {#if data.edicionError}
    <p class="snoc-recuadro snoc-recuadro-error">{data.edicionError}</p>
  {:else if data.edicion && !borrador}
    <div class="snoc-recuadro snoc-recuadro-alerta snoc-pila-xs">
      <strong>No se edita acá</strong>
      <span>Esta plantilla se armó a mano y tiene cosas que el editor no maneja. Publicar encima las borraría, así que no se ofrece:</span>
      <ul class="snoc-body-sm" style="margin:0;">
        {#each data.edicion.por_que_no ?? [] as m}<li>{m}</li>{/each}
      </ul>
    </div>
  {:else if data.edicion}
    {#if data.edicion.ordenes_vivas}
      <p class="snoc-recuadro snoc-recuadro-alerta">
        {data.edicion.ordenes_vivas}
        {data.edicion.ordenes_vivas === 1 ? 'orden abierta usa' : 'órdenes abiertas usan'}
        esta plantilla. No cambian al publicar: conservan su versión.
      </p>
    {/if}

    <form
      id="pl-publicar"
      method="POST"
      action="?/publicar"
      class="pl-editor"
      use:enhance={() => {
        publicando = true;
        return async ({ result, update }) => {
          await update({ reset: false });
          publicando = false;
          if (result?.type === 'success') {
            original = foto();
            avisar(/** @type {any} */ (result).data?.hecho ?? 'Guardado.');
          } else if (result?.type === 'failure') {
            avisar(/** @type {any} */ (result).data?.error ?? 'No se pudo guardar.', { tono: 'error' });
          }
        };
      }}
    >
      <input type="hidden" name="id" value={data.edicion.id} />
      <input type="hidden" name="definicion" value={JSON.stringify(paraGuardar(borrador))} />

      <div class="pl-columna">
        <div class="pl-cabecera">
          <label class="snoc-campo-grupo">
            <span class="snoc-label">Nombre</span>
            <input class="snoc-campo" name="nombre" bind:value={nombre} required maxlength="120" />
          </label>
          <label class="snoc-campo-grupo">
            <span class="snoc-label">Labor</span>
            <select class="snoc-select" name="labor" bind:value={labor}>
              <option value="">— sin labor (no se reparte) —</option>
              {#each data.labores ?? [] as l (l.id)}<option value={l.id}>{l.texto}</option>{/each}
            </select>
          </label>
          <label class="snoc-campo-grupo">
            <span class="snoc-label">Duración estimada (minutos)</span>
            <input class="snoc-campo" type="number" min="1" max="1440" bind:value={borrador.duracion_estimada_minutos} />
            <span class="snoc-body-sm" style="color:var(--snoc-alerta);">Cambiarla saca versión nueva.</span>
          </label>
          <label class="snoc-campo-grupo">
            <span class="snoc-label">Plazo para hacerlo (días)</span>
            <input class="snoc-campo" type="number" name="plazo_dias" min="0" max="60" bind:value={plazoDias} placeholder="sin plazo" />
          </label>
        </div>

        <!-- LO QUE DESPACHO USA PARA LLENAR EL FORMULARIO SOLO (19/10/2026).
             El asunto del ticket elige esta plantilla; el plazo, contado desde
             que se creó el ticket, propone «para cuándo». -->
        <label class="snoc-campo-grupo">
          <span class="snoc-label">Asuntos de WispHub que se despachan con esta plantilla</span>
          <textarea class="snoc-campo" name="asuntos" rows="3" bind:value={asuntos} placeholder={'Uno por línea, como vienen en el ticket. Ej.:\nCambio De Domicilio'}></textarea>
          <span class="snoc-body-sm snoc-secundario">
            Al despachar un ticket con uno de estos asuntos, esta plantilla viene elegida, y «para cuándo»
            se propone como la fecha de creación del ticket más el plazo. Un asunto va en una sola plantilla.
          </span>
        </label>

        <div class="snoc-fila-sep">
          <h3 class="snoc-h3">Datos que anota <span class="snoc-cuenta">{borrador.campos.length}</span></h3>
          <button type="button" class="snoc-btn" onclick={agregarDato}>+ Agregar dato</button>
        </div>
        {#each borrador.campos as c, i (c)}
          <div class="snoc-recuadro pl-item">
            <div class="snoc-fila" style="flex-wrap:wrap;">
              <span class="snoc-mono snoc-secundario">{i + 1}</span>
              <input class="snoc-campo" style="flex:1; min-width:12rem;" placeholder="Qué se anota" bind:value={c.titulo} aria-label="Nombre del dato {i + 1}" maxlength="120" />
              <select class="snoc-select" bind:value={c.tipo} aria-label="Tipo del dato {i + 1}">
                {#each data.tipos ?? [] as t (t.id)}<option value={t.id}>{t.texto}</option>{/each}
              </select>
              <label class="snoc-body-sm"><input type="checkbox" bind:checked={c.obligatorio} /> obligatorio</label>
              <button type="button" class="snoc-btn" onclick={() => mover('campos', i, -1)} aria-label="Subir">↑</button>
              <button type="button" class="snoc-btn" onclick={() => mover('campos', i, 1)} aria-label="Bajar">↓</button>
              <button type="button" class="snoc-btn snoc-btn-error" onclick={() => borrador.campos.splice(i, 1)} aria-label="Quitar">✕</button>
            </div>
            <span class="snoc-body-sm snoc-secundario">{(data.tipos ?? []).find((/** @type {any} */ t) => t.id === c.tipo)?.ayuda}</span>
            {#if c.tipo === 'numero'}
              <div class="pl-cuatro">
                <label class="snoc-campo-grupo"><span class="snoc-label">Unidad</span><input class="snoc-campo" bind:value={c.unidad} maxlength="16" /></label>
                <label class="snoc-campo-grupo"><span class="snoc-label">Mínimo</span><input class="snoc-campo" type="number" step="any" bind:value={c.min} /></label>
                <label class="snoc-campo-grupo"><span class="snoc-label">Máximo</span><input class="snoc-campo" type="number" step="any" bind:value={c.max} /></label>
              </div>
              <!-- EL RANGO SANO, y por qué no es Mínimo/Máximo (07/11/2026).
                   Mínimo y Máximo limitan lo que el técnico PUEDE ESCRIBIR;
                   confundirlos con lo sano le impide reportar la señal rota que
                   fue a arreglar. Este rango dice qué está BIEN: el Supervisor
                   lo usa para devolver la orden cuando la medida de salida queda
                   afuera. Varía por empresa, así que va acá (CLAUDE.md §3.3). -->
              <div class="pl-cuatro">
                <label class="snoc-campo-grupo"><span class="snoc-label">Rango sano · bueno desde</span><input class="snoc-campo" type="number" step="any" bind:value={c.bueno_min} /></label>
                <label class="snoc-campo-grupo"><span class="snoc-label">Bueno hasta</span><input class="snoc-campo" type="number" step="any" bind:value={c.bueno_max} /></label>
              </div>
              <span class="snoc-body-sm" style="color:var(--snoc-primary);">Fuera del rango sano, el Supervisor devuelve la orden. Vacío: no juzga.</span>
            {:else if c.tipo === 'seleccion'}
              <label class="snoc-campo-grupo">
                <span class="snoc-label">Una opción por renglón</span>
                <textarea class="snoc-campo" rows="3" value={opcionesTexto(c)} oninput={(ev) => ponerOpciones(c, ev.currentTarget.value)}></textarea>
              </label>
              <!-- «Otro» con texto (18/10/2026): la opción la agrega la
                   plataforma; al elegirla, el técnico tiene que escribir qué fue. -->
              <label class="snoc-body-sm"><input type="checkbox" bind:checked={c.permite_otro} /> Permitir «Otro» con texto (el técnico escribe qué fue)</label>
            {/if}
            <div class="pl-par">
              <label class="snoc-campo-grupo"><span class="snoc-label">Ayuda para el técnico (opcional)</span><input class="snoc-campo" bind:value={c.ayuda} maxlength="400" /></label>
              <label class="snoc-campo-grupo"><span class="snoc-label">Paso (opcional)</span><input class="snoc-campo" bind:value={c.paso} maxlength="120" /></label>
            </div>
          </div>
        {/each}

        <div class="snoc-fila-sep">
          <h3 class="snoc-h3">Fotos que saca <span class="snoc-cuenta">{borrador.evidencias.length}</span></h3>
          <button type="button" class="snoc-btn" onclick={agregarFoto}>+ Agregar foto</button>
        </div>
        {#each borrador.evidencias as e, i (e)}
          <div class="snoc-recuadro pl-item">
            <div class="snoc-fila" style="flex-wrap:wrap;">
              <span class="snoc-mono snoc-secundario">{i + 1}</span>
              <input class="snoc-campo" style="flex:1; min-width:12rem;" placeholder="De qué es la foto" bind:value={e.titulo} aria-label="Nombre de la foto {i + 1}" maxlength="120" />
              <label class="snoc-body-sm"><input type="checkbox" bind:checked={e.obligatorio} /> obligatoria</label>
              <!-- ES UNA CAPTURA (06/11/2026). Marcada, el técnico la elige de la
                   galería en vez de abrir la cámara: la evidencia de un test de
                   velocidad ES una captura. Sin marcar sigue siendo cámara, y eso
                   es lo que hace que una foto valga como prueba de que alguien
                   estuvo ahí. -->
              <label class="snoc-body-sm"><input type="checkbox" bind:checked={e.es_captura} /> captura de pantalla</label>
              <button type="button" class="snoc-btn" onclick={() => mover('evidencias', i, -1)} aria-label="Subir">↑</button>
              <button type="button" class="snoc-btn" onclick={() => mover('evidencias', i, 1)} aria-label="Bajar">↓</button>
              <button type="button" class="snoc-btn snoc-btn-error" onclick={() => borrador.evidencias.splice(i, 1)} aria-label="Quitar">✕</button>
            </div>
            {#if e.es_captura}
              <span class="snoc-body-sm snoc-secundario">La elige de la galería (una captura de pantalla), en vez de tomarla con la cámara.</span>
            {/if}
            <!-- SOLO EN LA PLATAFORMA (25/11/2026): para los documentos del
                 cliente (cédula, recibo). Quedan en la orden y no viajan al
                 ticket del CRM ni al del proveedor. -->
            <label class="snoc-body-sm"><input type="checkbox" bind:checked={e.solo_en_la_plataforma} /> solo en la plataforma (no va al ticket)</label>
            {#if e.solo_en_la_plataforma}
              <span class="snoc-body-sm snoc-secundario">Queda guardada en la orden. No se adjunta al ticket: para documentos del cliente, como la cédula o un recibo.</span>
            {/if}
            <div class="pl-par">
              <label class="snoc-campo-grupo"><span class="snoc-label">Qué tiene que verse (opcional)</span><input class="snoc-campo" bind:value={e.instrucciones} maxlength="400" /></label>
              <label class="snoc-campo-grupo"><span class="snoc-label">Paso (opcional)</span><input class="snoc-campo" bind:value={e.paso} maxlength="120" /></label>
            </div>
          </div>
        {/each}

        {#if pasosDeLaPlantilla.length}
          <h3 class="snoc-h3">Botones de cada paso</h3>
          <p class="snoc-body-sm snoc-secundario" style="margin:0;">
            En qué paso le salen al técnico. Si no marcas ninguno, salen al final de todos los pasos.
          </p>
          <div class="pl-reportes">
            {#each pasosDeLaPlantilla as paso (paso)}
              <div class="snoc-recuadro pl-item">
                <span class="snoc-label">{paso}</span>
                {#each BOTONES_DE_PASO as b (b.id)}
                  <label class="snoc-body-sm" style="display:flex;gap:6px;align-items:center;">
                    <input type="checkbox" checked={tieneBoton(paso, b.id)}
                           onchange={(ev) => ponerBoton(paso, b.id, ev.currentTarget.checked)} />
                    {b.texto}
                  </label>
                {/each}
              </div>
            {/each}
          </div>
        {/if}

        <!-- LAS FOTOS DE CADA REPORTE. Son otra cosa que las de arriba: aquellas
             se exigen para cerrar; estas se ofrecen mientras el técnico reporta,
             y nunca retienen el reporte. -->
        {#if borrador.fotos_de_reportes}
          <h3 class="snoc-h3">Fotos en los reportes</h3>
          <p class="snoc-body-sm snoc-secundario" style="margin:0;">
            Las que el técnico puede adjuntar al reportar. Son opcionales: si no la saca, el reporte se guarda igual.
          </p>
          <div class="pl-reportes">
            {#each REPORTES as r (r.id)}
              <div class="snoc-recuadro pl-item">
                <span class="snoc-label">{r.texto}</span>
                {#each borrador.fotos_de_reportes[r.id] ?? [] as e, i (e)}
                  <div class="snoc-fila">
                    <input class="snoc-campo" style="flex:1; min-width:8rem;" placeholder="De qué es la foto" bind:value={e.titulo} aria-label="Foto {i + 1} del reporte {r.texto}" maxlength="120" />
                    <button type="button" class="snoc-btn snoc-btn-error" onclick={() => borrador.fotos_de_reportes[r.id].splice(i, 1)} aria-label="Quitar">✕</button>
                  </div>
                {:else}
                  <span class="snoc-body-sm snoc-secundario">Este reporte no pide foto.</span>
                {/each}
                {#if (borrador.fotos_de_reportes[r.id] ?? []).length < 5}
                  <button type="button" class="snoc-btn" style="align-self:flex-start;" onclick={() => agregarFotoDeReporte(r.id)}>+ Foto</button>
                {/if}
              </div>
            {/each}
          </div>
        {/if}
      </div>

      <!-- ---- cómo lo ve el técnico: como en un teléfono ---- -->
      <aside class="pl-telefono" aria-label="Así lo ve el técnico">
        <span class="snoc-label snoc-secundario">Así lo ve el técnico</span>
        <div class="pl-pantalla">
          {#each vista as g (g.paso)}
            {#if g.paso !== '—'}<span class="pl-paso">{g.paso}</span>{/if}
            {#each g.datos as c}
              <div class="pl-campo">
                {c.titulo || '(sin nombre)'}{c.obligatorio ? ' *' : ''}
                <span class="snoc-secundario">
                  · {tipoTexto(c.tipo)}{c.tipo === 'numero' && c.unidad ? ` en ${c.unidad}` : ''}
                  {#if c.tipo === 'checklist'}(Hecho / No aplica){/if}
                  {#if c.tipo === 'seleccion'}({(c.opciones ?? []).length} opciones{c.permite_otro ? ' + Otro' : ''}){/if}
                </span>
              </div>
            {/each}
            {#each g.fotos as e}
              <div class="pl-campo">Foto: {e.titulo || '(sin nombre)'}{e.obligatorio ? ' *' : ''}{e.es_captura ? ' · de la galería' : ''}{e.solo_en_la_plataforma ? ' · solo en la plataforma' : ''}</div>
            {/each}
          {/each}
          {#if borrador.fotos_de_reportes}
            <span class="pl-paso">Al reportar puede adjuntar</span>
            {#each REPORTES as r (r.id)}
              {#if (borrador.fotos_de_reportes[r.id] ?? []).length}
                <span class="snoc-body-sm">{r.texto}: <span class="snoc-secundario">{borrador.fotos_de_reportes[r.id].map((/** @type {any} */ e) => e.titulo || '(sin nombre)').join(', ')}</span></span>
              {/if}
            {/each}
          {/if}
          <span class="snoc-body-sm snoc-secundario">* obligatorio para cerrar la orden.</span>
        </div>
      </aside>
    </form>

    <!-- EL MATERIAL QUE SE PRECARGA (26/11/2026). Un formulario aparte: no va
         dentro del de publicar (no se anidan) y se guarda sin sacar versión. -->
    <form
      method="POST"
      action="?/materialHabitual"
      class="snoc-recuadro snoc-pila"
      style="gap:10px; margin-top:16px;"
      use:enhance={() => {
        guardandoMaterial = true;
        return async ({ result, update }) => {
          await update({ reset: false });
          guardandoMaterial = false;
          if (result?.type === 'success') avisar(/** @type {any} */ (result).data?.hecho ?? 'Guardado.');
          else if (result?.type === 'failure')
            avisar(/** @type {any} */ (result).data?.error ?? 'No se pudo guardar.', { tono: 'error' });
        };
      }}
    >
      <input type="hidden" name="id" value={data.edicion.id} />
      <h3 class="snoc-h3" style="margin:0;">Material que se precarga</h3>
      <p class="snoc-body-sm snoc-secundario" style="margin:0;">
        Le llega puesto al técnico en «Material utilizado», y él lo ajusta. Deja la cantidad vacía
        si cambia en cada trabajo (las grapas, la fibra): ese lo escribe él.
      </p>
      {#if (data.materiales ?? []).length === 0}
        <span class="snoc-body-sm snoc-secundario">No hay materiales en el catálogo de Inventario.</span>
      {/if}
      {#each materialHabitual as linea, i (i)}
        <div class="snoc-fila" style="gap:8px; align-items:flex-end; flex-wrap:wrap;">
          <label class="snoc-campo-grupo" style="flex:2 1 220px;">
            <span class="snoc-label">Material</span>
            <select class="snoc-campo" name={`material_codigo_${i}`} bind:value={linea.codigo}>
              <option value="">Elige…</option>
              {#each data.materiales ?? [] as m (m.codigo)}
                <option value={m.codigo}>{m.nombre} ({m.codigo})</option>
              {/each}
              {#if linea.codigo && !materialPorCodigo.has(linea.codigo)}
                <option value={linea.codigo}>{linea.codigo} (no está activo)</option>
              {/if}
            </select>
          </label>
          <label class="snoc-campo-grupo" style="flex:1 1 120px;">
            <span class="snoc-label">Cantidad {materialPorCodigo.get(linea.codigo)?.unidad ? `(${materialPorCodigo.get(linea.codigo).unidad})` : ''}</span>
            <input class="snoc-campo" name={`material_cantidad_${i}`} inputmode="decimal"
                   placeholder="La escribe el técnico" bind:value={linea.cantidad} />
          </label>
          <label class="snoc-campo-grupo" style="flex:2 1 200px;">
            <span class="snoc-label">O sale del campo (la cantidad; en un equipo, su serie)</span>
            <select class="snoc-campo" name={`material_campo_${i}`} bind:value={linea.campo}>
              <option value="">— ninguno —</option>
              {#each camposDeNumero as c (c)}
                <option value={c}>{c}</option>
              {/each}
              {#if linea.campo && !camposDeNumero.includes(linea.campo)}
                <option value={linea.campo}>{linea.campo} (no está en la plantilla)</option>
              {/if}
            </select>
          </label>
          <button class="snoc-btn" type="button" onclick={() => materialHabitual.splice(i, 1)}>Quitar</button>
        </div>
      {/each}
      <div class="snoc-fila" style="gap:8px;">
        <button class="snoc-btn" type="button"
                onclick={() => materialHabitual.push({ codigo: '', cantidad: '', campo: '' })}>+ Agregar material</button>
        <button class="snoc-btn snoc-btn-primario" type="submit" disabled={guardandoMaterial}>
          {guardandoMaterial ? 'Guardando…' : 'Guardar el material'}
        </button>
      </div>
    </form>

    <!-- LOS PUNTOS DE TV (26/11/2026). Aparte, como el material. -->
    <form
      method="POST"
      action="?/puntosDeTv"
      class="snoc-recuadro snoc-pila"
      style="gap:10px; margin-top:16px;"
      use:enhance={() => {
        guardandoTv = true;
        return async ({ result, update }) => {
          await update({ reset: false });
          guardandoTv = false;
          if (result?.type === 'success') avisar(/** @type {any} */ (result).data?.hecho ?? 'Guardado.');
          else if (result?.type === 'failure')
            avisar(/** @type {any} */ (result).data?.error ?? 'No se pudo guardar.', { tono: 'error' });
        };
      }}
    >
      <input type="hidden" name="id" value={data.edicion.id} />
      <h3 class="snoc-h3" style="margin:0;">Puntos de TV</h3>
      <p class="snoc-body-sm snoc-secundario" style="margin:0;">
        El técnico marca cuántos puntos instaló y la app pone el material: los conectores, el spliter más
        chico que alcance de los que él tiene, y el cable que diga que usó.
      </p>
      <label class="snoc-body-sm" style="display:flex;gap:6px;align-items:center;">
        <input type="checkbox" name="tv_activo" bind:checked={tv.activo} /> Este trabajo lleva puntos de TV
      </label>
      <div class="snoc-fila" style="gap:8px; flex-wrap:wrap; align-items:flex-end;">
        <label class="snoc-campo-grupo" style="flex:2 1 220px;">
          <span class="snoc-label">Conector coaxial</span>
          <select class="snoc-campo" name="tv_conector" bind:value={tv.conector}>
            <option value="">Elige…</option>
            {#each data.materiales ?? [] as m (m.codigo)}<option value={m.codigo}>{m.nombre} ({m.codigo})</option>{/each}
          </select>
        </label>
        <label class="snoc-campo-grupo" style="flex:1 1 100px;">
          <span class="snoc-label">Por punto</span>
          <input class="snoc-campo" name="tv_por_punto" inputmode="numeric" bind:value={tv.por_punto} />
        </label>
        <label class="snoc-campo-grupo" style="flex:1 1 100px;">
          <span class="snoc-label">De entrada (con spliter)</span>
          <input class="snoc-campo" name="tv_entrada" inputmode="numeric" bind:value={tv.entrada} />
        </label>
        <label class="snoc-campo-grupo" style="flex:1 1 100px;">
          <span class="snoc-label">Máximo de puntos</span>
          <input class="snoc-campo" name="tv_maximo" inputmode="numeric" bind:value={tv.maximo} />
        </label>
        <label class="snoc-campo-grupo" style="flex:2 1 220px;">
          <span class="snoc-label">Cable (se pregunta si lo usó y cuántos metros)</span>
          <select class="snoc-campo" name="tv_cable" bind:value={tv.cable}>
            <option value="">— no se pregunta —</option>
            {#each data.materiales ?? [] as m (m.codigo)}<option value={m.codigo}>{m.nombre} ({m.codigo})</option>{/each}
          </select>
        </label>
      </div>
      <span class="snoc-label">Spliters</span>
      {#each tv.spliters as s, i (i)}
        <div class="snoc-fila" style="gap:8px; align-items:flex-end; flex-wrap:wrap;">
          <label class="snoc-campo-grupo" style="flex:2 1 220px;">
            <span class="snoc-label">Material</span>
            <select class="snoc-campo" name={`tv_spliter_codigo_${i}`} bind:value={s.codigo}>
              <option value="">Elige…</option>
              {#each data.materiales ?? [] as m (m.codigo)}<option value={m.codigo}>{m.nombre} ({m.codigo})</option>{/each}
            </select>
          </label>
          <label class="snoc-campo-grupo" style="flex:1 1 100px;">
            <span class="snoc-label">Salidas</span>
            <input class="snoc-campo" name={`tv_spliter_salidas_${i}`} inputmode="numeric" bind:value={s.salidas} />
          </label>
          <button class="snoc-btn" type="button" onclick={() => tv.spliters.splice(i, 1)}>Quitar</button>
        </div>
      {/each}
      {#if cuentaDeTv.length}
        <p class="snoc-body-sm snoc-secundario" style="margin:0;">Así queda: {cuentaDeTv.join(' · ')}</p>
      {/if}
      <div class="snoc-fila" style="gap:8px;">
        <button class="snoc-btn" type="button" onclick={() => tv.spliters.push({ codigo: '', salidas: '' })}>+ Agregar spliter</button>
        <button class="snoc-btn snoc-btn-primario" type="submit" disabled={guardandoTv}>
          {guardandoTv ? 'Guardando…' : 'Guardar puntos de TV'}
        </button>
      </div>
    </form>

    <!-- DUPLICAR (21/11/2026): crea otra con este mismo formulario, por la
         misma acción que «+ Nueva plantilla». Sin asuntos: un asunto va en
         una sola plantilla, y copiarlos haría fallar el alta. -->
    <form id="pl-duplicar" method="POST" action="?/crear" use:enhance={alCrear} hidden>
      <input type="hidden" name="definicion" value={JSON.stringify(paraGuardar(borrador))} />
      <input type="hidden" name="nombre" value={`Copia de ${nombre}`.slice(0, 120)} />
      <input type="hidden" name="labor" value={labor} />
      <input type="hidden" name="plazo_dias" value={plazoDias ?? ''} />
    </form>
  {/if}

  {#snippet pie()}
    {#if data.edicion && borrador}
      <div class="snoc-fila-sep" style="flex-wrap:wrap;">
        <span class="snoc-body-sm snoc-secundario" style="max-width:520px;">
          Guarda nombre, labor, plazo y asuntos. Si cambiaste lo que anota el técnico, sale una versión
          nueva: las órdenes ya creadas no cambian.
        </span>
        <div class="snoc-fila">
          <button class="snoc-btn" type="submit" form="pl-duplicar" disabled={creandoAhora}>Duplicar</button>
          <button class="snoc-btn" type="button" onclick={cerrarEditor}>Cerrar</button>
          <button class="snoc-btn snoc-btn-primario" type="submit" form="pl-publicar" disabled={publicando}>
            {publicando ? 'Guardando…' : 'Guardar'}
          </button>
        </div>
      </div>
    {/if}
  {/snippet}
</PanelLateral>

<style>
  .pl-catalogo { display: grid; gap: 14px; grid-template-columns: repeat(auto-fill, minmax(min(100%, 300px), 1fr)); }
  .pl-base { gap: 6px; }
  .pl-par { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr)); }
  .pl-cuatro { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 130px), 1fr)); }
  .pl-editor { display: flex; flex-wrap: wrap; gap: 20px; align-items: flex-start; }
  .pl-columna { flex: 3 1 520px; min-width: 0; display: flex; flex-direction: column; gap: 14px; }
  .pl-cabecera { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 180px), 1fr)); }
  .pl-item { display: flex; flex-direction: column; gap: 8px; background: var(--v2-card); }
  .pl-reportes { display: grid; gap: 10px; grid-template-columns: repeat(auto-fit, minmax(min(100%, 200px), 1fr)); }
  .pl-telefono { flex: 1 1 280px; max-width: 340px; position: sticky; top: 0; display: grid; gap: 8px; }
  .pl-pantalla {
    border: 8px solid var(--v2-nav-bg); border-radius: 28px; padding: 16px 14px; min-height: 480px;
    background: var(--v2-card); display: flex; flex-direction: column; gap: 8px;
  }
  .pl-paso { font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--v2-slate); font-weight: 600; margin-top: 4px; }
  .pl-campo { font-size: 12.5px; padding: 8px 10px; border: 1px solid var(--v2-line); border-radius: 10px; background: var(--v2-paper); }
  .pl-sw { width: 40px; height: 24px; border-radius: 999px; border: 0; cursor: pointer; background: var(--v2-line-strong); position: relative; }
  .pl-sw::after { content: ''; position: absolute; top: 3px; left: 3px; width: 18px; height: 18px; border-radius: 999px; background: #fff; box-shadow: 0 1px 2px rgba(0, 0, 0, 0.25); transition: left 0.15s; }
  .pl-sw-on { background: var(--v2-sola-fuerte); }
  .pl-sw-on::after { left: 19px; }
  .pl-sw:focus-visible { outline: 2px solid var(--v2-ember); outline-offset: 2px; }
  @media (prefers-reduced-motion: reduce) { .pl-sw::after { transition: none; } }
</style>
