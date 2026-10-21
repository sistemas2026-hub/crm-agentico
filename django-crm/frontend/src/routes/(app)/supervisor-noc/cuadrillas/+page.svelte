<script>
  /**
   * Cuadrillas — Supervisor NOC.
   *
   * DOS PREGUNTAS, DOS MITADES
   *   Arriba   el día: qué labor tiene cada cuadrilla y quién la integra HOY.
   *   Abajo    quiénes son: nombre, líder y vehículo. Cambia casi nunca.
   *
   * Esa es la razón de que sean dos tablas en el backend y de que acá estén
   * separadas: armar el día no es editar la cuadrilla. La cuadrilla sigue
   * siendo la misma; lo que cambia es su labor y su gente.
   *
   * POR QUÉ SE MANDA LA JORNADA ENTERA
   * El backend es idempotente por cuadrilla y fecha: reescribe todo con lo que
   * llega. Mandar sólo lo que cambió obligaría a decidir acá qué es un cambio,
   * que es justo lo que la idempotencia evita.
   */
  import { enhance } from '$app/forms';
  import { opcionesDeLider } from '$lib/supervisor/lider-de-cuadrilla.js';
  import '../supervisor-noc.css';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  /**
   * LAS DOS CASILLAS DEL CICLO, CON ESTADO PROPIO  --  19/10/2026
   *
   * Estaban escritas `checked={data.reparto_config.activo}`, de UNA VIA: la
   * fuente de verdad seguia siendo el servidor. Y esta pantalla tiene TRECE
   * formularios con `use:enhance` --mas del doble que cualquier otra del
   * sistema, la siguiente tiene cinco--, de los cuales seis usan el `enhance`
   * pelado y tres llaman `await update()`. Los nueve invalidan `data`.
   *
   * O sea: marcabas «Encendido», guardabas cualquier otra cosa de la misma
   * pantalla --una labor, una zona, una persona--, `data` se recargaba y la
   * casilla se DESMARCABA SOLA mientras vos creias que seguia marcada. Despues
   * le dabas a Guardar y se grababa `activo: false`. El sintoma es el peor de
   * todos: la pantalla dice una cosa y lo guardado es otra, sin error.
   *
   * Lo encontro el cliente: encendio el ciclo, volvio a entrar y decia APAGADO.
   *
   * POR QUE NO ALCANZA CON UN `$state` A SECAS: habria que resembrarlo cuando
   * el servidor cambia, y resembrar en cada recarga de `data` reproduce el
   * mismo bug. Por eso se compara contra lo ULTIMO QUE DIJO EL SERVIDOR: si
   * ese valor no cambio, la recarga no toca lo que la persona marco; si cambio
   * de verdad --otra sesion lo encendio-- se refleja.
   *
   * El patron `checked={}` de una via aparece 37 veces en el codigo y no es un
   * descuido: en una pantalla con uno o dos formularios es correcto. Lo que lo
   * rompe aca es la densidad.
   */
  //  Los cuatro `state_referenced_locally` que esto levanta son A PROPOSITO y
  //  por eso se silencian con su motivo, en vez de dejar avisos que enseñan a
  //  ignorar avisos. Svelte dice «esto solo captura el valor inicial»: eso es
  //  lo que se busca --la semilla-- y de los cambios posteriores se ocupa el
  //  `$effect` de abajo.
  //
  //  Y la semilla tiene que leer `data` AQUI, no dentro del efecto: un
  //  `$effect` no corre en el servidor, asi que sembrando solo ahi el HTML
  //  renderizado saldria siempre desmarcado y recien se corregiria al hidratar.
  /* svelte-ignore state_referenced_locally */
  let cicloActivo = $state(data.reparto_config?.activo ?? false);
  /* svelte-ignore state_referenced_locally */
  let cicloCopia = $state(data.reparto_config?.copia_la_jornada ?? true);
  /* svelte-ignore state_referenced_locally */
  let loUltimoDelServidor = $state({
    activo: data.reparto_config?.activo,
    copia: data.reparto_config?.copia_la_jornada
  });

  $effect(() => {
    const activo = data.reparto_config?.activo;
    const copia = data.reparto_config?.copia_la_jornada;
    if (activo !== loUltimoDelServidor.activo) {
      loUltimoDelServidor.activo = activo;
      cicloActivo = activo ?? false;
    }
    if (copia !== loUltimoDelServidor.copia) {
      loUltimoDelServidor.copia = copia;
      cicloCopia = copia ?? true;
    }
  });

  const LABORES_DE_FABRICA = [
    { id: 'instalacion', texto: 'Instalación' },
    { id: 'correctivo', texto: 'Correctivo' },
    { id: 'trabajos', texto: 'Trabajos' }
  ];
  /**
   * CON EL NOMBRE DE LA EMPRESA (20/10/2026). Se llaman como la empresa las
   * nombró en «Nombre de cada labor»; las que no cambió, como siempre. El id
   * es el interno y no cambia.
   */
  const LABORES = $derived(
    LABORES_DE_FABRICA.map((l) => ({
      ...l,
      texto: data.reparto_config?.nombres_de_labor?.[l.id] || l.texto
    }))
  );

  /**
   * LA VISTA PREVIA DEL ARMADO (21/10/2026). Pedido del usuario: ver ya lo
   * que armaría el Supervisor, sin esperar al día siguiente. Lee y no escribe.
   */
  let previa = $state(/** @type {any} */ (null));
  //  El dia ELEGIDO en la caja, no el cargado: el 21/10 se pidio el 22 y la
  //  vista previa calculo el 21 porque nadie habia tocado «Ver ese dia».
  /* svelte-ignore state_referenced_locally */
  let diaElegido = $state(data.dia ?? '');
  let cargandoPrevia = $state(false);
  let errorPrevia = $state('');
  async function verPrevia() {
    cargandoPrevia = true;
    errorPrevia = '';
    try {
      const r = await fetch(`/supervisor-noc/cuadrillas/vista-previa?fecha=${encodeURIComponent(diaElegido)}`);
      const d = await r.json();
      if (!r.ok) throw new Error(d?.error || 'No se pudo calcular.');
      previa = d;
    } catch (/** @type {any} */ e) {
      previa = null;
      errorPrevia = e?.message || 'No se pudo calcular.';
    } finally {
      cargandoPrevia = false;
    }
  }

  /** Los días del horario de las cuadrillas (21/10/2026), como los guarda el backend. */
  const DIAS_DEL_HORARIO = [
    { id: 'lunes', texto: 'Lunes' },
    { id: 'martes', texto: 'Martes' },
    { id: 'miercoles', texto: 'Miércoles' },
    { id: 'jueves', texto: 'Jueves' },
    { id: 'viernes', texto: 'Viernes' },
    { id: 'sabado', texto: 'Sábado' },
    { id: 'domingo', texto: 'Domingo' }
  ];
  /** Los feriados, uno por línea, como se escriben; el que se trabaja, con su horario. */
  const feriadosTexto = $derived(
    (data.horario?.feriados ?? [])
      .map((f) => `${f.fecha}${f.abre ? ` ${f.abre}-${f.cierra}` : ''} ${f.nombre}`)
      .join('\n')
  );

  const ROLES = [
    { id: 'tecnico_lider', texto: 'Técnico líder' },
    { id: 'tecnico', texto: 'Técnico' },
    { id: 'ayudante', texto: 'Ayudante' },
    { id: 'chofer', texto: 'Chofer' }
  ];

  /**
   * Los grupos de caso que pasan a Despacho (17/10/2026). De la labor de cada
   * uno sale la de una jornada armada sola: la de la mayoría de los casos de
   * sus zonas. Las claves son las de `paso_a_despacho.GRUPOS`, y el trabajo
   * pedido va partido en dos desde el 18/10/2026 (corrección 1 del usuario):
   * el de un cliente que ya existe y la instalación de uno nuevo
   * (`cuadrillas.INSTALACION_NUEVA`).
   */
  const GRUPOS_DE_CASO = [
    { id: 'falla_de_servicio', texto: 'Falla de servicio' },
    { id: 'trabajo_pedido', texto: 'Trabajo pedido (cliente que ya existe)' },
    { id: 'instalacion_nueva', texto: 'Instalación de un cliente nuevo' },
    { id: 'obra_de_red', texto: 'Obra de red' }
  ];

  /** Qué cuadrilla se está armando. `null` = ninguna. */
  let armando = $state(/** @type {any} */ (null));
  let labor = $state('instalacion');
  let lider = $state('');
  /** El líder que la jornada ya tiene (o el de la cuadrilla): se ofrece siempre. */
  let liderActual = $state(/** @type {any} */ (null));
  /**
   * Quiénes van en la jornada que se está armando.
   *
   * `persona` es el id de una PERSONA DE CAMPO, no de una cuenta: un auxiliar
   * sin celular no tiene `Profile` y aun así integra la cuadrilla.
   *
   * @type {{ persona: string, rol: string }[]}
   */
  let integrantes = $state([]);

  /** La ficha de cuadrilla abierta. `null` = ninguna. */
  let editando = $state(/** @type {any} */ (null));

  /** Las zonas que cubre la cuadrilla que se está armando. */
  let zonasDelDia = $state(/** @type {string[]} */ ([]));

  /** La zona cuyo mapeo de barrios está abierto. `null` = ninguno. */
  let mapeando = $state(/** @type {any} */ (null));
  let barriosElegidos = $state(/** @type {string[]} */ ([]));
  let buscaBarrio = $state('');

  /** En qué OTRA zona está cada barrio, para no ofrecerlo dos veces. */
  let barrioTomado = $derived.by(() => {
    /** @type {Record<string, string>} */
    const m = {};
    for (const z of data.zonas ?? []) {
      if (mapeando && z.id === mapeando.id) continue;
      for (const l of z.localidades ?? []) m[l] = z.nombre;
    }
    return m;
  });

  /** Los barrios que se ofrecen: los sincronizados, filtrados por el buscador. */
  let barriosOfrecidos = $derived(
    (data.localidades ?? [])
      .filter((l) =>
        !buscaBarrio ||
        String(l.localidad).toUpperCase().includes(buscaBarrio.toUpperCase())
      )
      // Los de más clientes primero: una zona se arma por peso, no por orden
      // alfabético.
      .slice()
      .sort((a, b) => (b.n_clientes ?? 0) - (a.n_clientes ?? 0))
  );

  function abrirMapeo(z) {
    mapeando = z;
    barriosElegidos = [...(z.localidades ?? [])];
    buscaBarrio = '';
  }

  function alternarBarrio(nombre) {
    barriosElegidos = barriosElegidos.includes(nombre)
      ? barriosElegidos.filter((x) => x !== nombre)
      : [...barriosElegidos, nombre];
  }

  /** La jornada ya armada de una cuadrilla, si la tiene. */
  function jornadaDe(cuadrillaId) {
    return (data.jornadas ?? []).find((j) => j.cuadrilla?.id === cuadrillaId) ?? null;
  }

  /**
   * Quién está ya en OTRA cuadrilla ese día.
   *
   * Se calcula acá para no ofrecer a alguien que el servidor va a rechazar:
   * la regla vive en el backend —y sigue viviendo ahí— pero mostrarla antes
   * evita el viaje de ida y vuelta para enterarse.
   */
  /**
   * Si esa persona ya está en otra cuadrilla hoy.
   *
   * Compara ids de PERSONA DE CAMPO, no de cuenta: desde que el integrante es
   * una persona, el aviso también alcanza a los auxiliares, que antes no
   * podían estar anotados en ningún lado.
   */
  function tomadaPorOtra(personaId, cuadrillaId) {
    for (const j of data.jornadas ?? []) {
      if (j.cuadrilla?.id === cuadrillaId) continue;
      if ((j.integrantes ?? []).some((i) => i.id === personaId)) {
        return j.cuadrilla?.nombre ?? 'otra cuadrilla';
      }
    }
    return '';
  }

  function armar(c) {
    const ya = jornadaDe(c.id);
    armando = c;
    labor = ya?.labor ?? 'instalacion';
    lider = ya?.lider?.id ?? c.lider?.id ?? '';
    liderActual = ya?.lider ?? c.lider ?? null;
    zonasDelDia = ya ? (ya.zonas ?? []).map((z) => z.id) : [];
    integrantes = ya
      ? ya.integrantes.map((i) => ({ persona: i.id, rol: i.rol }))
      : [];
    if (integrantes.length === 0) agregarIntegrante();
  }

  function agregarIntegrante() {
    //  El rol arranca VACÍO: así el backend usa el habitual de la persona
    //  que se elija, en vez de escribirle 'tecnico' encima.
    integrantes = [...integrantes, { persona: '', rol: '' }];
  }

  function quitarIntegrante(i) {
    integrantes = integrantes.filter((_, n) => n !== i);
    if (integrantes.length === 0) agregarIntegrante();
  }

  function abrirFicha(c) {
    editando = c
      ? {
          ...c,
          lider_id: c.lider?.id ?? '',
          vehiculo_id: c.vehiculo?.id ?? '',
          labor_habitual: c.labor_habitual || 'instalacion',
          zonas_habituales: (c.zonas_habituales ?? []).map((/** @type {any} */ z) => z.id)
        }
      : {
          id: '',
          nombre: '',
          lider_id: '',
          vehiculo_id: '',
          notas: '',
          labor_habitual: 'instalacion',
          zonas_habituales: []
        };
  }

  /**
   * Quiénes pueden ser LÍDER, en los dos selectores: la ficha de la cuadrilla
   * y «Líder de hoy». Ver `$lib/supervisor/lider-de-cuadrilla.js`: hasta el
   * 17/10/2026 se ofrecían solo las personas de campo con cuenta, la lista
   * salía vacía y guardar la ficha borraba al líder.
   */
  let lideresDeLaFicha = $derived(
    opcionesDeLider(data.personas, data.cuentasSinPersona, editando?.lider)
  );
  let lideresDeHoy = $derived(
    opcionesDeLider(data.personas, data.cuentasSinPersona, liderActual)
  );

  /** Cuántas personas trabajan hoy, sin contar a nadie dos veces. */
  let gentePorJornada = $derived(
    new Set(
      (data.jornadas ?? []).flatMap((j) => (j.integrantes ?? []).map((i) => i.id))
    ).size
  );

  // =====================================================================
  //  MOVER UNA ORDEN DE CUADRILLA ANTES DE PUBLICAR  --  13/10/2026
  // =====================================================================
  //  El reparto propone con un criterio declarado --lo que vence primero,
  //  despues lo mas viejo, respetando zonas-- y ese criterio es bueno. Pero
  //  quien conoce el terreno puede saber algo que el criterio no ve: que esa
  //  casa queda de paso, que ese cliente ya conoce a ese tecnico.
  //
  //  Hasta hoy la unica salida era publicar y reasignar despues, y eso deja al
  //  tecnico viendo en su telefono un trabajo que termina no siendo suyo.
  //
  //  NO SE TOCA EL REPARTO NI SE GUARDA NADA. Las mudanzas viven en la
  //  pantalla hasta que alguien publica; si se recarga, vuelve la propuesta
  //  del motor. Es coherente con lo que ya hacia: 'proponer()' no escribe.
  //
  //  Y el backend NO necesita nada nuevo: 'POST /campo/cuadrillas/reparto/'
  //  ya publica las asignaciones que le mandan, no las que el calculo dio.

  /** De qué jornada quedó cada orden movida. Vacío = como lo propuso el motor. */
  let mudanzas = $state(/** @type {Record<string, string>} */ ({}));

  /** Las órdenes que le tocan a una jornada, ya con las mudanzas aplicadas. */
  function repartoDe(jornada) {
    const p = data.reparto?.propuesta;
    if (!p) return [];
    const salida = [];
    for (const a of p.asignaciones ?? []) {
      for (const o of a.ordenes ?? []) {
        if ((mudanzas[o.id] ?? a.jornada) === jornada) salida.push(o);
      }
    }
    return salida;
  }

  function mover(ordenId, desde, hacia) {
    //  Volver a su jornada original BORRA la marca en vez de guardarla igual:
    //  así "no hay mudanzas" es un objeto vacío y no uno lleno de valores que
    //  no cambian nada.
    if (hacia === desde) delete mudanzas[ordenId];
    else mudanzas[ordenId] = hacia;
  }

  const hayMudanzas = $derived(Object.keys(mudanzas).length > 0);
</script>

<svelte:head>
  <title>Cuadrillas · Supervisor NOC</title>
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
          <h1 class="snoc-h1">CUADRILLAS</h1>
          <p class="snoc-body snoc-secundario">
            Quiénes son, y qué hace cada una el día que elijas. La cuadrilla sigue siendo la
            misma mañana; lo que cambia es su labor y su gente.
          </p>
        </div>
        <div class="snoc-fila" style="gap:var(--snoc-sm);">
          <a class="snoc-pildora" href="/supervisor-noc">Pendientes por revisión</a>
          <a class="snoc-pildora" href="/supervisor-noc/programacion">Programación</a>
          <a class="snoc-pildora snoc-pildora-activa" href="/supervisor-noc/cuadrillas">
            Cuadrillas
          </a>
          <a class="snoc-pildora" href="/supervisor-noc/despacho">Despacho</a>
          <a class="snoc-pildora" href="/supervisor-noc/plantillas">Plantillas</a>
        </div>
      </div>

      {#if data.error}
        <p class="snoc-aviso snoc-error-txt">
          No se pudieron leer todos los datos. Lo que falta no está vacío: no se sabe.
        </p>
      {/if}
      {#if form?.error}
        <p class="snoc-aviso snoc-error-txt">{form.error}</p>
      {/if}
      {#if form?.hecho}
        <p class="snoc-aviso">{form.hecho}</p>
      {/if}
    </section>

    <!-- ============ EL DÍA ============ -->
    <section class="snoc-panel" style="gap:var(--snoc-sm);">
      <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
        <div class="snoc-pila-xs">
          <h2 class="snoc-h2">El día</h2>
          <p class="snoc-body-sm snoc-secundario">
            {gentePorJornada}
            {gentePorJornada === 1 ? 'persona' : 'personas'} con trabajo asignado.
          </p>
        </div>
        <!-- La fecha va en la URL: así un día se puede compartir por enlace. -->
        <form method="GET" class="snoc-fila" style="gap:var(--snoc-xs);">
          <input class="snoc-campo" type="date" name="dia" bind:value={diaElegido} />
          <button class="snoc-btn" type="submit">Ver ese día</button>
          <button class="snoc-btn" type="button" onclick={verPrevia} disabled={cargandoPrevia}>
            {cargandoPrevia ? 'Calculando…' : 'Ver qué armaría el Supervisor'}
          </button>
        </form>
      </div>

      {#if errorPrevia}
        <p class="snoc-aviso snoc-error-txt">{errorPrevia}</p>
      {/if}
      {#if previa}
        <div class="snoc-tarjeta snoc-pila" style="gap:var(--snoc-sm);">
          <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
            <strong class="snoc-body">Lo que armaría el Supervisor el {previa.fecha}</strong>
            <button class="snoc-btn" type="button" onclick={() => (previa = null)}>Cerrar</button>
          </div>
          <span class="snoc-body-sm snoc-secundario">
            Vista previa: no se guardó nada. Para que lo arme, pedíselo en su chat
            («armá la jornada del día de cada cuadrilla»).
          </span>
          {#if !previa.trabaja}
            <p class="snoc-aviso">{previa.porque}</p>
          {:else}
            <span class="snoc-body-sm">Horario de ese día: {previa.apertura} a {previa.cierre}.</span>
            <table class="snoc-tabla">
              <thead>
                <tr><th>Cuadrilla</th><th>Qué haría</th><th>Labor</th><th>Zonas</th><th>Quiénes</th></tr>
              </thead>
              <tbody>
                {#each previa.cuadrillas as c (c.cuadrilla)}
                  <tr>
                    <td>{c.cuadrilla}</td>
                    <td>{c.que_haria}</td>
                    <td>{c.labor_antes && c.labor_antes !== c.labor ? `${c.labor_antes} → ` : ''}{c.labor || '—'}</td>
                    <td>{c.zonas.join(', ') || '—'}</td>
                    <td>{[c.lider, ...c.gente.map((g) => g.nombre)].filter(Boolean).join(', ') || '—'}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
            <span class="snoc-body-sm snoc-secundario">
              Casos en Despacho que cuentan para la labor: {previa.demanda.contados ?? 0}
              · sin barrio todavía: {previa.demanda.sin_barrio ?? 0}
              · barrio sin zona: {previa.demanda.sin_zona ?? 0}
              · sin labor: {previa.demanda.sin_labor ?? 0}
              · ya despachados: {previa.demanda.ya_despachados ?? 0}.
            </span>
            {#if (previa.barrios_sin_zona ?? []).length}
              <p class="snoc-aviso">
                Barrios sin zona: sus casos no le llegan a ninguna cuadrilla. Cargalos en
                Zonas operativas → Elegir barrios:
                {previa.barrios_sin_zona.map((b) => `${b.barrio} (${b.casos})`).join(', ')}.
              </p>
            {/if}
            {#each previa.por_zona as z (z.zona)}
              <span class="snoc-body-sm">
                {z.zona}: {z.labores.map((l) => `${l.casos} de ${l.labor}`).join(', ')}
              </span>
            {/each}
          {/if}
        </div>
      {/if}

      {#if (data.cuadrillas ?? []).length === 0}
        <p class="snoc-body snoc-secundario">
          Todavía no hay ninguna cuadrilla. Hasta que exista una no se le puede asignar
          trabajo a nadie: el reparto elige de acá.
        </p>
      {:else}
        <table class="snoc-tabla">
          <thead>
            <tr>
              <th>Cuadrilla</th>
              <th>Labor de hoy</th>
              <th>Quiénes</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {#each data.cuadrillas as c (c.id)}
              {@const j = jornadaDe(c.id)}
              <tr>
                <td>
                  <strong>{c.nombre}</strong>
                  {#if c.lider}
                    <span class="snoc-body-sm snoc-secundario" style="display:block;">
                      Líder: {c.lider.nombre}
                    </span>
                  {/if}
                  {#if c.vehiculo}
                    <span class="snoc-body-sm snoc-secundario" style="display:block;">
                      {c.vehiculo.nombre}
                    </span>
                  {/if}
                </td>
                <td>
                  {#if j}
                    <span class="snoc-insignia snoc-insignia-primaria">{j.labor_nombre}</span>
                    <!-- QUIÉN LA ARMÓ (17/10/2026). La que se armó sola —el
                         Supervisor o el ciclo de la madrugada— se reajusta de
                         labor mientras no tenga órdenes; corregirla a mano la
                         vuelve de una persona y ya no la toca. -->
                    {#if j.armada_por === 'automatica'}
                      <span class="snoc-tag">Armada sola</span>
                    {/if}
                    {#if j.zonas?.length}
                      {#each j.zonas as z (z.id)}
                        <span class="snoc-tag">{z.nombre}</span>
                      {/each}
                    {:else}
                      <span class="snoc-sin-dato" style="display:block;">sin zona</span>
                    {/if}
                  {:else}
                    <!-- SIN JORNADA NO ES «NO TRABAJA»: es que nadie se lo asignó
                         todavía. Decirlo distinto que «descansa» importa a las 6 am. -->
                    <span class="snoc-sin-dato">Sin armar</span>
                  {/if}
                </td>
                <td>
                  {#if j && j.integrantes.length}
                    {#each j.integrantes as i (i.id)}
                      <span class="snoc-tag">{i.nombre} · {i.rol.replace('_', ' ')}</span>
                    {/each}
                  {:else}
                    <span class="snoc-sin-dato">—</span>
                  {/if}
                </td>
                <td class="snoc-derecha">
                  <button class="snoc-pildora" type="button" onclick={() => armar(c)}>
                    {j ? 'Cambiar el día' : 'Armar el día'}
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </section>

    <!-- ============ ARMAR EL DÍA DE UNA CUADRILLA ============ -->
    {#if armando}
      <section class="snoc-panel" style="gap:var(--snoc-sm);">
        <h2 class="snoc-h2">{armando.nombre} · {data.dia}</h2>

        <form method="POST" action="?/jornada" use:enhance={() => {
          return async ({ result, update }) => {
            await update();
            if (result.type === 'success') armando = null;
          };
        }} class="snoc-pila">
          <input type="hidden" name="cuadrilla" value={armando.id} />
          <input type="hidden" name="fecha" value={data.dia} />

          <div class="snoc-fila" style="gap:var(--snoc-md); flex-wrap:wrap;">
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Labor</span>
              <select class="snoc-select" name="labor" bind:value={labor}>
                {#each LABORES as l (l.id)}
                  <option value={l.id}>{l.texto}</option>
                {/each}
              </select>
            </label>

            <label class="snoc-campo-grupo">
              <span class="snoc-label">Líder de hoy</span>
              <select class="snoc-select" name="lider" bind:value={lider}>
                <option value="">— el de la cuadrilla —</option>
                {#if lideresDeHoy.actual}
                  <option value={lideresDeHoy.actual.profile}>{lideresDeHoy.actual.nombre}</option>
                {/if}
                {#if lideresDeHoy.deCampo.length}
                  <optgroup label="Personas de campo">
                    {#each lideresDeHoy.deCampo as p (p.profile)}
                      <option value={p.profile}>{p.nombre}</option>
                    {/each}
                  </optgroup>
                {/if}
                {#if lideresDeHoy.cuentas.length}
                  <optgroup label="Otras cuentas del equipo">
                    {#each lideresDeHoy.cuentas as p (p.profile)}
                      <option value={p.profile}>{p.nombre}</option>
                    {/each}
                  </optgroup>
                {/if}
              </select>
            </label>
          </div>

          <div class="snoc-pila-xs">
            <span class="snoc-label">Zonas que cubre hoy</span>
            {#if (data.zonas ?? []).length === 0}
              <p class="snoc-body-sm snoc-secundario">
                Todavía no hay zonas. Se arman más abajo; sin ellas la cuadrilla queda sin
                zona, que no es lo mismo que cubrir todas.
              </p>
            {:else}
              <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
                {#each data.zonas as z (z.id)}
                  <label class="snoc-pildora" style="cursor:pointer;">
                    <input
                      type="checkbox"
                      name="zona"
                      value={z.id}
                      checked={zonasDelDia.includes(z.id)}
                      onchange={(e) => {
                        zonasDelDia = e.currentTarget.checked
                          ? [...zonasDelDia, z.id]
                          : zonasDelDia.filter((x) => x !== z.id);
                      }}
                    />
                    {z.nombre}
                  </label>
                {/each}
              </div>
              {#if zonasDelDia.length === 0}
                <!-- Vacío NO es «cubre todas», y hay que decirlo: con zona dura
                     una cuadrilla sin zona no recibe trabajo por zona. -->
                <p class="snoc-body-sm snoc-secundario">
                  Sin zona asignada. No significa que cubra todas: significa que no va a
                  recibir trabajo por zona.
                </p>
              {/if}
            {/if}
          </div>

          <p class="snoc-body-sm snoc-secundario">
            El líder del día puede no ser el de la cuadrilla: si está de vacaciones, alguien
            la lleva igual, y quién respondía ese día no puede depender de quién la lidera
            hoy.
          </p>

          <div class="snoc-pila-xs">
            <span class="snoc-label">Quiénes van</span>
            {#each integrantes as ig, i (i)}
              {@const ocupada = ig.persona ? tomadaPorOtra(ig.persona, armando.id) : ''}
              <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
                <select class="snoc-select" name="integrante_persona" bind:value={ig.persona}>
                  <option value="">— elegí a alguien —</option>
                  {#each data.personas as p (p.id)}
                    <option value={p.id}>
                      {p.nombre}{p.tiene_cuenta ? '' : ' · sin celular'}
                    </option>
                  {/each}
                </select>
                <select class="snoc-select" name="integrante_rol" bind:value={ig.rol}>
                  {#each ROLES as r (r.id)}
                    <option value={r.id}>{r.texto}</option>
                  {/each}
                </select>
                <button class="snoc-pildora" type="button" onclick={() => quitarIntegrante(i)}>
                  Quitar
                </button>
                {#if ocupada}
                  <!-- Se avisa ANTES de enviar. La regla vive en el backend y
                       sigue viviendo ahí; esto evita el viaje para enterarse. -->
                  <span class="snoc-error-txt snoc-body-sm">
                    Ya está en {ocupada} hoy
                  </span>
                {/if}
              </div>
            {/each}
            <button class="snoc-pildora" type="button" onclick={agregarIntegrante}>
              Agregar a alguien
            </button>
          </div>

          <div class="snoc-fila" style="gap:var(--snoc-sm);">
            <button class="snoc-btn snoc-btn-primario" type="submit">Guardar el día</button>
            <button class="snoc-pildora" type="button" onclick={() => (armando = null)}>
              Cancelar
            </button>
          </div>
        </form>
      </section>
    {/if}

    <!-- ============ EL REPARTO ============ -->
    <section class="snoc-panel" style="gap:var(--snoc-sm);">
      <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
        <div class="snoc-pila-xs">
          <h2 class="snoc-h2">Armar la jornada</h2>
          <p class="snoc-body-sm snoc-secundario">
            Ordena lo pendiente por SLA y antigüedad, y lo reparte entre las cuadrillas que
            trabajan el {data.dia}, respetando sus zonas. <strong>Propone: no asigna nada
            hasta que vos publiques.</strong>
          </p>
        </div>
        <a class="snoc-btn" href="?dia={data.dia}&reparto=1">Ver la propuesta</a>
      </div>

      {#if data.reparto.error}
        <p class="snoc-aviso snoc-error-txt">
          {data.reparto.motivo || 'No se pudo calcular la propuesta.'}
        </p>
      {:else if data.reparto.pedido && data.reparto.propuesta}
        {@const p = data.reparto.propuesta}
        {@const conOrdenes = p.asignaciones.filter((a) => a.ordenes.length)}

        {#if conOrdenes.length === 0}
          <p class="snoc-body snoc-secundario">
            No hay nada para repartir. Puede ser que no queden órdenes pendientes, o que
            ninguna caiga en las zonas que se cubren hoy — abajo se dice cuál de las dos.
          </p>
        {:else}
          <form method="POST" action="?/publicar" use:enhance class="snoc-pila">
            {#each conOrdenes as a (a.jornada)}
              <!-- Se manda lo que se está MIRANDO, no la fecha: entre ver y
                   publicar pueden entrar órdenes nuevas.
                   Y se manda lo que quedó después de los cambios: 'repartoDe'
                   devuelve la propuesta con las mudanzas aplicadas. -->
              <input
                type="hidden"
                name="asignacion"
                value={[a.jornada, ...repartoDe(a.jornada).map((o) => o.id)].join('|')}
              />
              <div class="snoc-tarjeta">
                <div class="snoc-fila-sep" style="flex-wrap:wrap;">
                  <strong>{a.cuadrilla.nombre}</strong>
                  <span class="snoc-body-sm snoc-secundario">
                    {a.ordenes.length}
                    {a.ordenes.length === 1 ? 'orden' : 'órdenes'} ·
                    {a.integrantes}
                    {a.integrantes === 1 ? 'persona' : 'personas'}
                    {#if a.zonas.length}· {a.zonas.join(', ')}{/if}
                  </span>
                </div>
                {#each repartoDe(a.jornada) as o (o.id)}
                  <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
                    <span class="snoc-mono">#{o.numero}</span>
                    <span>{o.cliente || '—'}</span>
                    <span class="snoc-body-sm snoc-secundario">{o.direccion}</span>
                    {#if o.zona}<span class="snoc-tag">{o.zona}</span>{/if}
                    <!--
                      MOVERLA ANTES DE PUBLICAR  --  13/10/2026
                      El reparto propone con un criterio declarado, pero quien
                      conoce el terreno puede saber algo que el criterio no
                      ve: que esa casa queda de paso, que ese cliente ya
                      conoce a ese técnico. Hasta hoy la única salida era
                      publicar y reasignar después, que deja al técnico viendo
                      en su teléfono un trabajo que no era suyo.
                      Es un <select> y no arrastrar: funciona con teclado, en
                      un teléfono, y no hay forma de soltar una orden en el
                      vacío.
                    -->
                    <select
                      class="snoc-campo"
                      style="margin-left:auto; max-width:14rem;"
                      aria-label="Mover la orden {o.numero} a otra cuadrilla"
                      onchange={(e) => mover(o.id, a.jornada, e.currentTarget.value)}
                    >
                      {#each conOrdenes as destino (destino.jornada)}
                        <option value={destino.jornada} selected={destino.jornada === a.jornada}>
                          {destino.cuadrilla.nombre}
                        </option>
                      {/each}
                    </select>
                  </div>
                {/each}
              </div>
            {/each}

            {#if hayMudanzas}
              <!--
                SE DICE QUE LA PROPUESTA YA NO ES LA DEL MOTOR. Publicar una
                jornada creyendo que es la calculada cuando tiene cambios a
                mano haría que, el día que algo salga mal, se revisara el
                criterio en vez de la decisión.
              -->
              <p class="snoc-body-sm">
                Moviste {Object.keys(mudanzas).length}
                {Object.keys(mudanzas).length === 1 ? 'orden' : 'órdenes'}.
                Se publica como quedó acá, no como lo propuso el reparto.
                <button class="snoc-enlace" type="button" onclick={() => (mudanzas = {})}>
                  Volver a la propuesta
                </button>
              </p>
            {/if}
            <button class="snoc-btn snoc-btn-primario" type="submit">
              Publicar esta jornada
            </button>
            <p class="snoc-body-sm snoc-secundario">
              Recién ahí el técnico la ve en su teléfono. Una orden que alguien ya asignó a
              mano no se pisa: esa decisión la tomó una persona mirando el caso.
            </p>
          </form>
        {/if}

        <!--
          LOS TRES MOTIVOS, POR SEPARADO. Se arreglan distinto: una necesita
          que alguien mapee su barrio, otra que alguien cubra esa zona hoy, y
          la tercera que haya más gente o menos tope.
        -->
        {#each [['sin_zona', 'Sin zona: su barrio no está mapeado a ninguna zona'], ['sin_cuadrilla', 'Nadie cubre su zona hoy'], ['sobrantes', 'No entraron por el tope de la cuadrilla']] as [clave, titulo] (clave)}
          {#if p[clave]?.length}
            <div class="snoc-pila-xs">
              <span class="snoc-label">{titulo} ({p[clave].length})</span>
              {#each p[clave] as o (o.id)}
                <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
                  <span class="snoc-mono">#{o.numero}</span>
                  <span>{o.cliente || '—'}</span>
                  {#if o.zona}<span class="snoc-tag">{o.zona}</span>{/if}
                  <!-- ¿UNA LETRA DE MÁS O DE MENOS? (13/10/2026). Si el barrio
                       se parece a uno ya mapeado, se SUGIERE: decide una
                       persona. Aceptar agrega lo escrito como un alias más de
                       esa zona, así que arregla esta orden y las que lleguen
                       escritas igual. No se corrige solo: dos barrios reales
                       pueden diferir en una letra. -->
                  {#if clave === 'sin_zona' && o.parecida && o.zona}
                    {@const zona = (data.zonas ?? []).find((z) => z.id === o.parecida.zona_id)}
                    <span class="snoc-body-sm snoc-secundario">
                      ¿Es <strong>{o.parecida.localidad}</strong> ({o.parecida.zona})?
                    </span>
                    {#if zona}
                      <form method="POST" action="?/mapeo" use:enhance>
                        <input type="hidden" name="zona_id" value={zona.id} />
                        {#each zona.localidades as l (l)}
                          <input type="hidden" name="localidad" value={l} />
                        {/each}
                        <input type="hidden" name="localidad" value={o.zona} />
                        <button class="snoc-btn" type="submit">
                          Sí: «{o.zona}» es de {zona.nombre}
                        </button>
                      </form>
                    {/if}
                  {/if}
                </div>
              {/each}
            </div>
          {/if}
        {/each}
      {:else}
        <p class="snoc-body-sm snoc-secundario">
          No se calcula sola: mirar esta pantalla no puede disparar un recorrido de todas
          las órdenes pendientes.
        </p>
      {/if}
    </section>

    <!-- ============ EL HORARIO DE LAS CUADRILLAS (21/10/2026) ============
         Pedido del usuario: el horario por defecto de la empresa es el de
         atención al cliente. El Supervisor arma y despacha con ESTE, y sin
         este no lo hace solo. -->
    <section class="snoc-panel" style="gap:var(--snoc-sm);">
      <div class="snoc-pila-xs">
        <h2 class="snoc-h2">Horario de las cuadrillas</h2>
        <p class="snoc-body-sm snoc-secundario">
          Cuándo trabajan las cuadrillas. Es aparte del horario de atención al cliente: el
          Supervisor arma la jornada y despacha solo dentro de este horario.
        </p>
      </div>
      {#if data.horarioError}
        <p class="snoc-aviso snoc-error-txt">No se pudo leer el horario de las cuadrillas.</p>
      {:else}
        {#if !data.horario?.configurado}
          <p class="snoc-aviso">
            Todavía no está cargado: hasta que lo guardes, el Supervisor no arma ni despacha solo.
          </p>
        {:else if data.horario.zona_horaria !== data.horario.zona_de_la_empresa}
          <p class="snoc-aviso">
            La empresa está en {data.horario.zona_de_la_empresa} y este horario en
            {data.horario.zona_horaria}: revisá cuál es la de la operación.
          </p>
        {/if}
        <form method="POST" action="?/horario" use:enhance class="snoc-pila"
              style="gap:var(--snoc-md);">
          <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap; align-items:end;">
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Zona horaria</span>
              <input class="snoc-campo" name="zona_horaria" list="zonas-horarias" required
                     value={data.horario?.zona_horaria || 'America/Bogota'} />
              <datalist id="zonas-horarias">
                <option value="America/Bogota"></option>
                <option value="America/Lima"></option>
                <option value="America/Guayaquil"></option>
                <option value="America/Caracas"></option>
                <option value="America/Mexico_City"></option>
              </datalist>
            </label>
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Hora de corte</span>
              <input class="snoc-campo" type="time" name="hora_de_corte"
                     value={data.horario?.hora_de_corte ?? ''} style="width:auto;" />
            </label>
          </div>
          <span class="snoc-body-sm snoc-secundario">
            Hora de corte: lo que entra a Despacho antes sale hoy; lo que entra después, mañana
            a primera hora. Vacía, el Supervisor no crea órdenes solo.
          </span>
          <div class="snoc-pila-xs">
            {#each DIAS_DEL_HORARIO as d (d.id)}
              {@const v = data.horario?.dias?.[d.id]}
              <div class="snoc-fila" style="gap:var(--snoc-sm); align-items:center; flex-wrap:wrap;">
                <label class="snoc-fila" style="gap:var(--snoc-xs); min-width:120px;">
                  <input type="checkbox" name={`trabaja_${d.id}`} value="1" checked={!!v} />
                  <span class="snoc-body">{d.texto}</span>
                </label>
                <input class="snoc-campo" type="time" name={`abre_${d.id}`} style="width:auto;"
                       value={v?.abre ?? '07:00'} aria-label={`${d.texto}: abre`} />
                <span class="snoc-body-sm">a</span>
                <input class="snoc-campo" type="time" name={`cierra_${d.id}`} style="width:auto;"
                       value={v?.cierra ?? '17:00'} aria-label={`${d.texto}: cierra`} />
              </div>
            {/each}
          </div>
          <label class="snoc-campo-grupo">
            <span class="snoc-label">Feriados</span>
            <textarea class="snoc-campo" name="feriados" rows="4" value={feriadosTexto}
                      placeholder={'Uno por línea: AAAA-MM-DD Nombre\n2026-12-08 Inmaculada Concepción'}></textarea>
            <span class="snoc-body-sm snoc-secundario">
              Un feriado queda cerrado. Si se trabaja, poné el horario después de la fecha:
              2026-11-16 07:00-12:00 Independencia de Cartagena. El día hábil anterior, el
              Supervisor propone si conviene trabajarlo, según la cola.
            </span>
          </label>
          <div>
            <button class="snoc-btn snoc-btn-primario" type="submit">Guardar horario</button>
          </div>
        </form>
      {/if}
    </section>

    <!-- ============ EL CICLO DE LA MADRUGADA ============ -->
    <!--
      Deja armada la jornada de cada cuadrilla y avisa qué hay que mirar. NO
      publica: `reparto.proponer()` no escribe nada y se recalcula al abrir
      esta pantalla, así que guardar una propuesta de las 3 de la mañana solo
      lograría servirla vieja a las 7. Una persona sigue publicando.

      Viene APAGADO de fábrica: encender un proceso que corre todas las noches
      es una decisión de operación, no algo que pase porque alguien desplegó
      una versión. Mismo criterio que `RELOJ_HABILITADO` en el motor.
    -->
    <section class="snoc-panel" style="gap:var(--snoc-sm);">
      <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
        <div class="snoc-pila-xs">
          <h2 class="snoc-h2">El ciclo de la madrugada</h2>
          <p class="snoc-body-sm snoc-secundario">
            Cada día, a la hora que elijas, deja armada la jornada de cada cuadrilla
            —su pareja de siempre, en sus zonas habituales— y te avisa qué quedó sin
            resolver. El reparto lo seguís publicando vos.
          </p>
        </div>
        {#if data.reparto_config}
          <span class="snoc-tag">
            {data.reparto_config.activo ? 'Encendido' : 'Apagado'}
          </span>
        {/if}
      </div>

      {#if data.repartoConfigError}
        <p class="snoc-aviso snoc-error-txt">
          No se pudo leer la configuración del ciclo.
        </p>
      {:else if data.reparto_config}
        <form method="POST" action="?/reparto_config" use:enhance
              class="snoc-pila-xs">
          <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap; align-items:flex-end;">
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Hora</span>
              <select class="snoc-select" name="hora_local">
                {#each Array.from({ length: 24 }, (_, h) => h) as h (h)}
                  <option value={h} selected={h === data.reparto_config.hora_local}>
                    {String(h).padStart(2, '0')}:00
                  </option>
                {/each}
              </select>
            </label>
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Órdenes por cuadrilla</span>
              <input
                class="snoc-campo"
                type="number"
                name="tope_por_cuadrilla"
                min="1"
                max="99"
                value={data.reparto_config.tope_por_cuadrilla}
                style="width:90px"
              />
            </label>
            <!-- EL CORTE DE RED (19/10/2026, caso 4 de las correcciones): desde
                 cuántos equipos del mismo puerto en LOS a la vez un caso pasa a
                 Despacho marcado como corte de red, un solo trabajo. -->
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Corte de red desde (equipos del puerto en LOS)</span>
              <input
                class="snoc-campo"
                type="number"
                name="onus_para_corte_de_red"
                min="2"
                max="64"
                value={data.reparto_config.onus_para_corte_de_red ?? 2}
                style="width:90px"
              />
            </label>
          </div>

          <!-- La hora es LOCAL de la empresa, no la del servidor: el servidor
               corre en UTC y una hora suelta no dice de dónde es. -->
          <p class="snoc-body-sm snoc-secundario">
            Hora de <strong>{data.reparto_config.zona_horaria}</strong>.
            {#if data.reparto_config.ultima_corrida}
              Última corrida: {data.reparto_config.ultima_corrida}.
            {:else}
              Todavía no corrió ninguna vez.
            {/if}
          </p>

          <label class="snoc-fila" style="gap:var(--snoc-xs); align-items:center;">
            <input type="checkbox" name="copia_la_jornada" value="1"
                   bind:checked={cicloCopia} />
            <span class="snoc-body-sm">
              Armar la jornada de cada cuadrilla: su pareja de siempre, en sus zonas
              habituales
            </span>
          </label>

          <label class="snoc-fila" style="gap:var(--snoc-xs); align-items:center;">
            <input type="checkbox" name="activo" value="1"
                   bind:checked={cicloActivo} />
            <span class="snoc-body-sm">
              <strong>Encendido</strong> — corre solo todas las noches
            </span>
          </label>

          <!-- CÓMO SE LLAMA CADA LABOR (20/10/2026). Pedido del usuario: los
               traslados los hace la cuadrilla de correctivo, «pero un cambio
               de domicilio no es un correctivo». Cambia el nombre que se ve en
               todas las pantallas; qué cuadrilla recibe qué no cambia. Vacío =
               el de siempre. -->
          <div class="snoc-pila-xs">
            <span class="snoc-label">Nombre de cada labor</span>
            <p class="snoc-body-sm snoc-secundario">
              Cambia solo cómo se llama en Plantillas, Despacho y Cuadrillas. Qué
              cuadrilla recibe cada trabajo sigue igual.
            </p>
            <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap;">
              {#each LABORES_DE_FABRICA as l (l.id)}
                <label class="snoc-campo-grupo">
                  <span class="snoc-label">{l.texto}</span>
                  <input class="snoc-campo" name={`nombre_labor_${l.id}`} maxlength="40"
                         value={data.reparto_config.nombres_de_labor?.[l.id] ?? ''}
                         placeholder={l.texto} />
                </label>
              {/each}
            </div>
          </div>

          <!-- DE QUÉ LABOR ES CADA CASO (17/10/2026). Por empresa y no en
               código: en otro ISP un trabajo pedido puede ir a otra labor. -->
          <div class="snoc-pila-xs">
            <span class="snoc-label">De qué labor es cada caso de Despacho</span>
            <p class="snoc-body-sm snoc-secundario">
              Una jornada armada sola sale con la labor de la mayoría de los casos de
              sus zonas. «No cuenta» deja ese tipo de caso afuera de la cuenta.
            </p>
            <div class="snoc-fila" style="gap:var(--snoc-sm); flex-wrap:wrap;">
              {#each GRUPOS_DE_CASO as g (g.id)}
                <label class="snoc-campo-grupo">
                  <span class="snoc-label">{g.texto}</span>
                  <select class="snoc-select" name={`labor_de_${g.id}`}>
                    <option value="" selected={!data.reparto_config.labor_por_grupo?.[g.id]}>
                      — no cuenta —
                    </option>
                    {#each LABORES as l (l.id)}
                      <option value={l.id}
                              selected={data.reparto_config.labor_por_grupo?.[g.id] === l.id}>
                        {l.texto}
                      </option>
                    {/each}
                  </select>
                </label>
              {/each}
            </div>
          </div>

          <p class="snoc-body-sm snoc-secundario">
            El tope no es capacidad calculada: es un freno para que no le caigan treinta
            órdenes a la primera cuadrilla. Una cuadrilla puede tener el suyo propio, y
            ese le gana a este. Con tantos equipos del mismo puerto sin señal (LOS) a la
            vez, cada caso pasa a Despacho marcado como corte de red: un solo trabajo
            para todos, no una visita por cliente.
          </p>

          <div>
            <!-- Sin `disabled`: el permiso lo exige el backend
                 (`_exigir_gestion`), y esta pantalla no recibe el rol. Un
                 `disabled` por una variable que no existe se evalua como
                 "deshabilitado siempre" y nadie podria guardar. -->
            <button class="snoc-btn" type="submit">Guardar</button>
          </div>
        </form>

      <!-- LOS TIPOS DE TRABAJO Y SU LABOR.
           Una cuadrilla puesta en correctivo no puede recibir instalaciones, y
           ningún código ('ftth', 'soporte') dice a cuál pertenece: cada empresa
           nombra los suyos. Lo que no está clasificado NO se reparte, así que
           esto no es cosmético. -->
      <div style="margin-top:14px;border-top:1px solid var(--snoc-borde,#e5e7eb);padding-top:14px">
        <div class="snoc-pila-xs">
          <strong class="snoc-body-sm">Qué labor tiene cada tipo de trabajo</strong>
          <p class="snoc-body-sm snoc-secundario">
            Define qué cuadrillas pueden tomarlo. Lo que quede sin clasificar no se
            reparte: aparece aparte, nombrado, en vez de ir a parar a cualquier cuadrilla.
          </p>
        </div>

        {#if (data.tipos ?? []).length === 0}
          <p class="snoc-body-sm snoc-secundario" style="margin-top:8px">
            Todavía no hay tipos de trabajo cargados.
          </p>
        {:else}
          {#if data.tiposSinClasificar}
            <p class="snoc-aviso" style="margin-top:8px">
              {data.tiposSinClasificar}
              {data.tiposSinClasificar === 1 ? 'tipo sin clasificar' : 'tipos sin clasificar'}.
              Sus órdenes no se están repartiendo.
            </p>
          {/if}

          <div class="snoc-pila-xs" style="margin-top:8px">
            {#each data.tipos as t (t.id)}
              <form method="POST" action="?/tipo_labor" use:enhance
                    class="snoc-fila-sep" style="gap:var(--snoc-xs); flex-wrap:wrap;">
                <input type="hidden" name="id" value={t.id} />
                <div class="snoc-pila-xs" style="min-width:0">
                  <span class="snoc-body-sm">{t.nombre}</span>
                  <span class="snoc-body-sm snoc-secundario snoc-mono">{t.codigo}</span>
                </div>
                <div class="snoc-fila" style="gap:var(--snoc-xs)">
                  <select class="snoc-select" name="labor">
                    <option value="" selected={!t.labor}>— sin clasificar —</option>
                    {#each LABORES as l (l.id)}
                      <option value={l.id} selected={l.id === t.labor}>{l.texto}</option>
                    {/each}
                  </select>
                  <button class="snoc-pildora" type="submit">Guardar</button>
                </div>
              </form>
            {/each}
          </div>
        {/if}
      </div>

        {#if form?.error}
          <p class="snoc-aviso snoc-error-txt">{form.error}</p>
        {/if}
        {#if form?.hecho}
          <p class="snoc-aviso">{form.hecho}</p>
        {/if}
      {/if}
    </section>

    <!-- ============ QUIÉNES TRABAJAN EN CAMPO ============ -->
    <!--
      Dos preguntas distintas que antes eran la misma:

        quién ENTRA al sistema    una cuenta, con correo y contraseña
        quién TRABAJÓ             con cuenta o sin ella

      Los auxiliares no tienen celular asignado, así que no tienen cuenta — y
      mientras el integrante de una jornada fue un `Profile`, anotarlos
      obligaba a inventarles una que nadie iba a usar. Ver
      `campo.cuadrillas.PersonaDeCampo`.
    -->
    <section class="snoc-panel" style="gap:var(--snoc-sm);">
      <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
        <div class="snoc-pila-xs">
          <h2 class="snoc-h2">Quiénes trabajan en campo</h2>
          <p class="snoc-body-sm snoc-secundario">
            Incluye a quienes no tienen celular asignado: también integran la cuadrilla, y
            así queda escrito quién estuvo cada día. Lo que no reciben es el trabajo en un
            teléfono.
          </p>
        </div>
      </div>

      <form method="POST" action="?/persona_alta" use:enhance class="snoc-fila"
            style="gap:var(--snoc-xs); flex-wrap:wrap; align-items:flex-end;">
        <label class="snoc-campo-grupo" style="flex:1 1 180px; min-width:0;">
          <span class="snoc-label">Nombre y apellido</span>
          <input class="snoc-campo" name="nombre" placeholder="Pedro Ayudante" required />
        </label>
        <label class="snoc-campo-grupo">
          <span class="snoc-label">Rol habitual</span>
          <select class="snoc-select" name="rol_habitual">
            {#each ROLES as r (r.id)}
              <option value={r.id} selected={r.id === 'ayudante'}>{r.texto}</option>
            {/each}
          </select>
        </label>
        <button class="snoc-btn" type="submit">Dar de alta</button>
      </form>

      {#if (data.cuentasSinPersona ?? []).length}
        <!-- El equipo que ya tiene cuenta se da de alta en un clic, en vez de
             teclear el nombre de alguien que el sistema ya conoce. -->
        <div class="snoc-pila-xs">
          <span class="snoc-label">Del equipo, todavía sin dar de alta</span>
          <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
            {#each data.cuentasSinPersona as c (c.profile)}
              <form method="POST" action="?/persona_alta" use:enhance>
                <input type="hidden" name="profile" value={c.profile} />
                <input type="hidden" name="rol_habitual" value="tecnico" />
                <button class="snoc-pildora" type="submit">+ {c.nombre}</button>
              </form>
            {/each}
          </div>
        </div>
      {/if}

      {#if (data.personas ?? []).length === 0}
        <p class="snoc-body-sm snoc-secundario">
          Todavía no hay nadie cargado. Sin esto no se puede armar una cuadrilla.
        </p>
      {:else}
        <div class="snoc-pila-xs">
          {#each data.personas as p (p.id)}
            <div class="snoc-tarjeta snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-xs);">
              <div class="snoc-pila-xs" style="min-width:0;">
                <span class="snoc-body">{p.nombre}</span>
                <span class="snoc-body-sm snoc-secundario">
                  {ROLES.find((r) => r.id === p.rol_habitual)?.texto ?? p.rol_habitual}
                  {#if p.tiene_cuenta}
                    · entra al sistema
                  {:else}
                    · sin celular asignado
                  {/if}
                  {#if !p.activa} · dado de baja{/if}
                </span>
              </div>
              <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
                {#if !p.tiene_cuenta && (data.cuentasSinPersona ?? []).length}
                  <!-- EL AUXILIAR AL QUE LE ASIGNAN CELULAR: se le engancha la
                       cuenta a ESTA persona, así su historial sigue siendo uno
                       en vez de empezar de cero. -->
                  <form method="POST" action="?/persona_editar" use:enhance
                        class="snoc-fila" style="gap:var(--snoc-xs);">
                    <input type="hidden" name="id" value={p.id} />
                    <select class="snoc-select" name="profile">
                      <option value="">— enlazar una cuenta —</option>
                      {#each data.cuentasSinPersona as c (c.profile)}
                        <option value={c.profile}>{c.nombre}</option>
                      {/each}
                    </select>
                    <button class="snoc-pildora" type="submit">Enlazar</button>
                  </form>
                {/if}
                <form method="POST" action="?/persona_editar" use:enhance>
                  <input type="hidden" name="id" value={p.id} />
                  <input type="hidden" name="activa" value={p.activa ? '0' : '1'} />
                  <button class="snoc-pildora" type="submit">
                    {p.activa ? 'Dar de baja' : 'Reactivar'}
                  </button>
                </form>
              </div>
            </div>
          {/each}
        </div>
        <p class="snoc-body-sm snoc-secundario">
          Dar de baja no borra nada: sus jornadas siguen explicando quién estuvo cada día.
        </p>
      {/if}
    </section>

    <!-- ============ LAS ZONAS ============ -->
    <section class="snoc-panel" style="gap:var(--snoc-sm);">
      <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
        <div class="snoc-pila-xs">
          <h2 class="snoc-h2">Zonas operativas</h2>
          <p class="snoc-body-sm snoc-secundario">
            Cómo divide la empresa su territorio. No son las zonas del proveedor —ésas son
            de corte de facturación— y por eso se declaran acá.
          </p>
        </div>
        <form method="POST" action="?/zona" use:enhance class="snoc-fila"
              style="gap:var(--snoc-xs);">
          <input class="snoc-campo" name="nombre" required placeholder="Norte" />
          <button class="snoc-btn" type="submit">Crear zona</button>
        </form>
      </div>

      {#if (data.zonas ?? []).length === 0}
        <p class="snoc-body snoc-secundario">
          Todavía no hay ninguna. Sin zonas, una cuadrilla no puede recibir trabajo por
          zona.
        </p>
      {:else}
        <table class="snoc-tabla">
          <thead>
            <tr>
              <th>Zona</th>
              <th>Barrios</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {#each data.zonas as z (z.id)}
              <tr>
                <td><strong>{z.nombre}</strong></td>
                <td>
                  {#if z.localidades?.length}
                    {#each z.localidades as l (l)}
                      <span class="snoc-tag">{l}</span>
                    {/each}
                  {:else}
                    <span class="snoc-sin-dato">sin barrios asignados</span>
                  {/if}
                </td>
                <td class="snoc-derecha">
                  <button class="snoc-pildora" type="button" onclick={() => abrirMapeo(z)}>
                    Elegir barrios
                  </button>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}

      {#if mapeando}
        <div class="snoc-pila" style="gap:var(--snoc-sm);">
          <h3 class="snoc-h2">Barrios de {mapeando.nombre}</h3>
          <!--
            LOS BARRIOS SE ELIGEN, NO SE ESCRIBEN. La lista la arma el motor
            recorriendo el catálogo del proveedor —«nunca la escribe una
            persona»— y ya resolvió las variantes: un intento de «mejorar» el
            nombre colapsando SOLEDAD ATLANTICO devolvió SOLEDA, un typo de
            tres clientes. Teclearlos acá repetiría ese error.
          -->
          {#if data.localidadesError}
            <p class="snoc-aviso snoc-error-txt">
              No se pudieron leer las localidades. Sin ellas no se puede mapear: no están
              vacías, no se saben.
            </p>
          {:else}
            <p class="snoc-body-sm snoc-secundario">
              {data.localidades.length} barrios sincronizados, con sus clientes.
              {#if data.localidadesActualizadoEn}
                Última sincronización: {data.localidadesActualizadoEn}.
              {/if}
              Se actualizan desde Configuración · Planes de venta.
            </p>

            <form method="POST" action="?/mapeo" use:enhance={() => {
              return async ({ result, update }) => {
                await update();
                if (result.type === 'success') mapeando = null;
              };
            }} class="snoc-pila" style="gap:var(--snoc-sm);">
              <input type="hidden" name="zona_id" value={mapeando.id} />

              <input
                class="snoc-campo"
                bind:value={buscaBarrio}
                placeholder="Buscar un barrio…"
              />

              <div style="max-height:320px; overflow:auto;" class="snoc-pila-xs">
                {#each barriosOfrecidos as l (l.localidad)}
                  {@const tomado = barrioTomado[l.localidad]}
                  <label
                    class="snoc-fila"
                    style="gap:var(--snoc-xs); cursor:{tomado ? 'not-allowed' : 'pointer'};"
                  >
                    <input
                      type="checkbox"
                      name="localidad"
                      value={l.localidad}
                      checked={barriosElegidos.includes(l.localidad)}
                      disabled={Boolean(tomado)}
                      onchange={() => alternarBarrio(l.localidad)}
                    />
                    <span class={tomado ? 'snoc-secundario' : ''}>{l.localidad}</span>
                    <span class="snoc-body-sm snoc-secundario">
                      {l.n_clientes}
                      {l.n_clientes === 1 ? 'cliente' : 'clientes'}
                    </span>
                    {#if tomado}
                      <!-- Se dice EN CUÁL está: el servidor lo rechazaría igual,
                           pero sin el nombre hay que salir a buscarlo. -->
                      <span class="snoc-body-sm snoc-secundario">· ya está en {tomado}</span>
                    {/if}
                  </label>
                {:else}
                  <p class="snoc-body-sm snoc-secundario">
                    Ningún barrio coincide con la búsqueda.
                  </p>
                {/each}
              </div>

              <div class="snoc-fila" style="gap:var(--snoc-sm);">
                <button class="snoc-btn snoc-btn-primario" type="submit">
                  Guardar {barriosElegidos.length}
                  {barriosElegidos.length === 1 ? 'barrio' : 'barrios'}
                </button>
                <button class="snoc-pildora" type="button" onclick={() => (mapeando = null)}>
                  Cancelar
                </button>
              </div>
            </form>
          {/if}
        </div>
      {/if}
    </section>

    <!-- ============ EL HISTORIAL ============ -->
    <section class="snoc-panel" style="gap:var(--snoc-sm);">
      <div class="snoc-pila-xs">
        <h2 class="snoc-h2">Quién estuvo con quién</h2>
        <p class="snoc-body-sm snoc-secundario">
          El dato siempre estuvo completo —una fila por persona y por día—; esto lo lee
          junto en vez de ir cambiando la fecha de a uno.
        </p>
      </div>

      <!-- Va por GET: así un historial se comparte por enlace, igual que el día. -->
      <form method="GET" class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
        <input type="hidden" name="dia" value={data.dia} />
        <label class="snoc-campo-grupo">
          <span class="snoc-label">Desde</span>
          <input class="snoc-campo" type="date" name="desde" value={data.historial.desde} />
        </label>
        <label class="snoc-campo-grupo">
          <span class="snoc-label">Hasta</span>
          <input class="snoc-campo" type="date" name="hasta" value={data.historial.hasta} />
        </label>
        <label class="snoc-campo-grupo">
          <span class="snoc-label">De una cuadrilla</span>
          <select class="snoc-select" name="cual" value={data.historial.cual}>
            <option value="">— todas —</option>
            {#each data.cuadrillas as c (c.id)}
              <option value={c.id}>{c.nombre}</option>
            {/each}
          </select>
        </label>
        <label class="snoc-campo-grupo">
          <span class="snoc-label">O de una persona</span>
          <select class="snoc-select" name="quien" value={data.historial.quien}>
            <option value="">— nadie en particular —</option>
            {#each data.personas as p (p.id)}
              <option value={p.id}>
                {p.nombre}{p.tiene_cuenta ? '' : ' · sin celular'}
              </option>
            {/each}
          </select>
        </label>
        <button class="snoc-btn" type="submit">Ver</button>
      </form>

      {#if data.historial.error}
        <p class="snoc-aviso snoc-error-txt">
          {data.historial.motivo || 'No se pudo leer el historial.'}
        </p>
      {:else if !data.historial.pedido}
        <p class="snoc-body-sm snoc-secundario">
          Elegí un rango y una cuadrilla o una persona. No se trae solo: es una consulta de
          hasta tres meses y esta pantalla se abre casi siempre para asignar, no para mirar
          atrás.
        </p>
      {:else if data.historial.jornadas.length === 0}
        <p class="snoc-body-sm snoc-secundario">
          No hay ninguna jornada en ese rango. Que no haya no es lo mismo que no haber
          podido leerlas: esto es una respuesta, no un error.
        </p>
      {:else}
        <table class="snoc-tabla">
          <thead>
            <tr>
              <th>Día</th>
              <th>Cuadrilla</th>
              <th>Labor</th>
              <th>Quiénes</th>
            </tr>
          </thead>
          <tbody>
            {#each data.historial.jornadas as j (j.id)}
              <tr>
                <td class="snoc-mono">{j.fecha}</td>
                <td>{j.cuadrilla?.nombre ?? '—'}</td>
                <td>
                  <span class="snoc-insignia snoc-insignia-neutra">{j.labor_nombre}</span>
                </td>
                <td>
                  {#each j.integrantes as i (i.id)}
                    <!-- La persona consultada se destaca: en una fila de cinco,
                         encontrarla a ojo es justo lo que uno vino a evitar. -->
                    <span
                      class="snoc-tag"
                      class:snoc-insignia-primaria={i.id === data.historial.quien}
                    >
                      {i.nombre} · {i.rol.replace('_', ' ')}
                    </span>
                  {:else}
                    <span class="snoc-sin-dato">—</span>
                  {/each}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </section>

    <!-- ============ QUIÉNES SON ============ -->
    <section class="snoc-panel" style="gap:var(--snoc-sm);">
      <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
        <div class="snoc-pila-xs">
          <h2 class="snoc-h2">Las cuadrillas</h2>
          <p class="snoc-body-sm snoc-secundario">
            Una cuadrilla no se borra: se da de baja. Sus jornadas la referencian y son las
            que explican quién hizo qué.
          </p>
        </div>
        <div class="snoc-fila" style="gap:var(--snoc-xs);">
          <a
            class="snoc-pildora"
            href="?dia={data.dia}&bajas={data.verBajas ? '0' : '1'}"
          >
            {data.verBajas ? 'Ocultar las dadas de baja' : 'Ver las dadas de baja'}
          </a>
          <button class="snoc-pildora" type="button" onclick={() => abrirFicha(null)}>
            Cuadrilla nueva
          </button>
        </div>
      </div>

      {#if editando}
        <form method="POST" action="?/cuadrilla" use:enhance={() => {
          return async ({ result, update }) => {
            await update();
            if (result.type === 'success') editando = null;
          };
        }} class="snoc-pila">
          <input type="hidden" name="cuadrilla_id" value={editando.id} />
          <div class="snoc-fila" style="gap:var(--snoc-md); flex-wrap:wrap;">
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Nombre</span>
              <input
                class="snoc-campo"
                name="nombre"
                required
                bind:value={editando.nombre}
                placeholder="Cuadrilla 1"
              />
            </label>
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Líder</span>
              <select class="snoc-select" name="lider" bind:value={editando.lider_id}>
                <option value="">— sin líder —</option>
                {#if lideresDeLaFicha.actual}
                  <option value={lideresDeLaFicha.actual.profile}>{lideresDeLaFicha.actual.nombre}</option>
                {/if}
                {#if lideresDeLaFicha.deCampo.length}
                  <optgroup label="Personas de campo">
                    {#each lideresDeLaFicha.deCampo as p (p.profile)}
                      <option value={p.profile}>{p.nombre}</option>
                    {/each}
                  </optgroup>
                {/if}
                {#if lideresDeLaFicha.cuentas.length}
                  <optgroup label="Otras cuentas del equipo">
                    {#each lideresDeLaFicha.cuentas as p (p.profile)}
                      <option value={p.profile}>{p.nombre}</option>
                    {/each}
                  </optgroup>
                {/if}
              </select>
              <!-- Lo que ya tenía, para que guardar mande solo lo que la
                   persona cambió (`cambioDe` en +page.server.js). -->
              <input type="hidden" name="lider_antes" value={editando.lider?.id ?? ''} />
            </label>
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Vehículo</span>
              <select class="snoc-select" name="vehiculo" bind:value={editando.vehiculo_id}>
                <option value="">— sin vehículo —</option>
                {#each data.vehiculos as v (v.id)}
                  <option value={v.id}>{v.nombre}</option>
                {/each}
              </select>
              <input type="hidden" name="vehiculo_antes" value={editando.vehiculo?.id ?? ''} />
            </label>
          </div>
          <p class="snoc-body-sm snoc-secundario">
            El vehículo es una ubicación de inventario: en una cuadrilla el material vive en
            la camioneta y no en la mochila de una persona, y eso cambia a quién se le pide
            cuenta.
          </p>

          <!-- LO HABITUAL (17/10/2026). De acá arma el Supervisor la jornada de
               cada día: las zonas adónde va la cuadrilla y la labor cuando no
               hay casos que digan otra. Una cuadrilla sin zona no recibe
               trabajo del reparto. -->
          <div class="snoc-fila" style="gap:var(--snoc-md); flex-wrap:wrap; align-items:flex-start;">
            <label class="snoc-campo-grupo">
              <span class="snoc-label">Labor habitual</span>
              <select class="snoc-select" name="labor_habitual" bind:value={editando.labor_habitual}>
                {#each LABORES as l (l.id)}
                  <option value={l.id}>{l.texto}</option>
                {/each}
              </select>
            </label>
            <div class="snoc-pila-xs">
              <span class="snoc-label">Zonas habituales</span>
              {#if (data.zonas ?? []).filter((z) => z.activa !== false).length === 0}
                <p class="snoc-body-sm snoc-secundario">
                  Todavía no hay zonas: se arman más abajo, en «Zonas operativas».
                </p>
              {:else}
                <div class="snoc-fila" style="gap:var(--snoc-xs); flex-wrap:wrap;">
                  {#each (data.zonas ?? []).filter((z) => z.activa !== false) as z (z.id)}
                    <label class="snoc-pildora" style="cursor:pointer;">
                      <input
                        type="checkbox"
                        name="zona_habitual"
                        value={z.id}
                        checked={editando.zonas_habituales.includes(z.id)}
                        onchange={(e) => {
                          editando.zonas_habituales = e.currentTarget.checked
                            ? [...editando.zonas_habituales, z.id]
                            : editando.zonas_habituales.filter((/** @type {string} */ x) => x !== z.id);
                        }}
                      />
                      {z.nombre}
                    </label>
                  {/each}
                </div>
              {/if}
            </div>
          </div>
          <p class="snoc-body-sm snoc-secundario">
            De acá arma el Supervisor la jornada de cada día: las zonas adónde va y la labor
            cuando no hay casos que digan otra. Sin zonas, la cuadrilla no recibe trabajo.
          </p>
          <div class="snoc-fila" style="gap:var(--snoc-sm);">
            <button class="snoc-btn snoc-btn-primario" type="submit">Guardar</button>
            <button class="snoc-pildora" type="button" onclick={() => (editando = null)}>
              Cancelar
            </button>
          </div>
        </form>
      {/if}

      {#if (data.cuadrillas ?? []).length === 0}
        <p class="snoc-body snoc-secundario">Todavía no hay ninguna.</p>
      {:else}
        <table class="snoc-tabla">
          <thead>
            <tr>
              <th>Nombre</th>
              <th>Líder</th>
              <th>Vehículo</th>
              <th>Labor habitual</th>
              <th>Zonas habituales</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {#each data.cuadrillas as c (c.id)}
              <tr>
                <td>
                  <strong>{c.nombre}</strong>
                  {#if !c.activa}
                    <span class="snoc-insignia snoc-insignia-neutra">Dada de baja</span>
                  {/if}
                </td>
                <td>{c.lider?.nombre ?? '—'}</td>
                <td>{c.vehiculo?.nombre ?? '—'}</td>
                <td>{LABORES.find((l) => l.id === c.labor_habitual)?.texto ?? '—'}</td>
                <td>
                  {#if (c.zonas_habituales ?? []).length}
                    {c.zonas_habituales.map((/** @type {any} */ z) => z.nombre).join(', ')}
                  {:else}
                    <span class="snoc-insignia snoc-insignia-neutra">Sin zona</span>
                  {/if}
                </td>
                <td class="snoc-derecha">
                  <div class="snoc-fila" style="gap:var(--snoc-xs); justify-content:flex-end;">
                    <button class="snoc-pildora" type="button" onclick={() => abrirFicha(c)}>
                      Editar
                    </button>
                    <form method="POST" action="?/baja" use:enhance>
                      <input type="hidden" name="cuadrilla_id" value={c.id} />
                      <input type="hidden" name="activa" value={c.activa ? '0' : '1'} />
                      <button class="snoc-pildora" type="submit">
                        {c.activa ? 'Dar de baja' : 'Reactivar'}
                      </button>
                    </form>
                  </div>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </section>
    </div>
  </div>
</div>
