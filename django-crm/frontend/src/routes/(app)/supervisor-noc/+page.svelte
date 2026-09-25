<script>
  import { enhance } from '$app/forms';
  import { invalidateAll } from '$app/navigation';
  import {
    comunDeEvidencia,
    fuentesDeEvidencia,
    baseDePrioridad,
    contrasteDeEstados,
    haceCuanto,
    expiraEn,
    antiguedadDelCaso,
    lecturaExterna,
    CONTEXTO_AUSENTE,
    pasosDelCiclo
  } from '$lib/v2/supervisor-noc-detalle.js';
  import {
    kpisDelTablero,
    hallazgosPorTipo,
    estadoDeCasos,
    ordenesDeTrabajo,
    cargaPorTecnico,
    ticketsPorOrigen,
    bandejaDeRevision,
    rotuloDeHallazgo,
    actividadReciente,
    celdaDeSla,
    BLOQUES_SIN_DATO
  } from '$lib/v2/supervisor-noc-tablero.js';
  import './supervisor-noc.css';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  // ---------------------------------------------------------------------
  //  ESTADO LOCAL
  //  Nada de esto decide permisos ni protege nada: el backend es la
  //  autoridad y vuelve a comprobarlo en cada llamada. Aca solo vive lo que
  //  la pantalla necesita para no parpadear.
  // ---------------------------------------------------------------------
  let modalCiclo = $state(false);
  let corriendo = $state(false);
  let asistenteCorriendo = $state(/** @type {string | null} */ (null));
  let filtro = $state(/** @type {string | null} */ (null));

  // Los filtros de la bandeja. Se aplican en el navegador: el GET ya trajo el
  // conjunto entero (el backend corta en 200 y hoy hay 93), asi que una
  // vuelta al servidor por pastilla seria reordenar datos que ya estan en
  // pantalla.
  //
  // Abre en 'pendientes' y no en 'todas' a proposito: la bandeja se llama
  // asi porque lo que muestra es lo que espera una decision. Lo ya decidido
  // esta a una pastilla de distancia, no escondido.
  let filtroEstado = $state('pendientes');
  let filtroNivel = $state(/** @type {string | null} */ (null));
  let filtroPropuesta = $state('');

  const NIVELES_VISIBLES = ['Alta', 'Media', 'Baja'];

  /**
   * El KPI de pendientes lleva a la bandeja Y la deja filtrada en pendientes.
   * Sin lo segundo, el numero del KPI y el de la tabla se contradicen cuando
   * alguien habia dejado el filtro en 'todas'.
   */
  function irAPendientes() {
    filtroEstado = 'pendientes';
    filtroNivel = null;
    filtroPropuesta = '';
    filtro = null;
  }

  function limpiarFiltros() {
    filtro = null;
    filtroNivel = null;
    filtroPropuesta = '';
    filtroEstado = '';
  }

  let revisando = $state(/** @type {string | null} */ (null));
  let comentario = $state('');

  // El panel lateral. `detalle` se pide por id y trae su propio cargando:
  // antes esto recargaba la pagina entera -- las 92 propuestas, los
  // indicadores y el estado del motor -- para mostrar una ficha.
  let abierta = $state(/** @type {string | null} */ (null));
  let detalle = $state(/** @type {any} */ (null));
  let cargandoDetalle = $state(false);
  let errorDetalle = $state(/** @type {string | null} */ (null));

  /** @type {Record<number, string>} */
  const NIVELES = {
    0: 'Observar',
    1: 'Recomendar',
    2: 'Coordinar',
    3: 'Ejecutar acciones reversibles autorizadas',
    4: 'Acción crítica con autorización humana'
  };

  /** Los estados del modelo. No hay ninguno mas, y 'ejecutada' no existe. */
  const ESTADOS = {
    propuesta: { texto: 'Propuesta', clase: 'snoc-insignia' },
    aceptada: { texto: 'Aceptada', clase: 'snoc-insignia-secundaria-suave' },
    modificada: { texto: 'Modificada', clase: 'snoc-insignia-secundaria-suave' },
    rechazada: { texto: 'Rechazada', clase: 'snoc-insignia-error' },
    cancelada: { texto: 'Cancelada', clase: 'snoc-insignia-variante' },
    expirada: { texto: 'Expirada', clase: 'snoc-insignia-variante' }
  };
  const estadoDe = (/** @type {string} */ e) =>
    ESTADOS[/** @type {keyof typeof ESTADOS} */ (e)] ?? { texto: e, clase: 'snoc-insignia' };

  const PRIORIDAD = { alta: 'snoc-insignia-error-solida', media: 'snoc-insignia-secundaria' };
  const tonoPrioridad = (/** @type {any} */ p) =>
    PRIORIDAD[/** @type {keyof typeof PRIORIDAD} */ (String(p).toLowerCase())] ?? 'snoc-insignia';

  const propuestas = $derived(data.hallazgos?.resultados ?? []);

  // ---------------------------------------------------------------------
  //  EL TABLERO
  //  Las derivaciones viven en $lib/v2/supervisor-noc-tablero.js, probadas
  //  aparte: la regla que mas facil se rompe aqui -- un `?? 0` de mas y un
  //  indicador caido se muestra como "todo en orden" -- no se puede ejercitar
  //  sin montar el componente.
  // ---------------------------------------------------------------------
  const leidas = $derived(data.hallazgos?.error ? null : (data.hallazgos?.resultados ?? null));
  const kpis = $derived(kpisDelTablero(data.indicadores, leidas));
  const donut = $derived(hallazgosPorTipo(leidas));
  const barras = $derived(estadoDeCasos(data.indicadores));
  const ordenes = $derived(ordenesDeTrabajo(data.indicadores));
  const tecnicos = $derived(cargaPorTecnico(data.capacidad?.personas));
  const origen = $derived(ticketsPorOrigen(data.indicadores));
  const actividad = $derived(actividadReciente(data.actividad?.eventos));

  /**
   * La bandeja: filtrada, ordenada y numerada. La logica vive en
   * $lib/v2/supervisor-noc-tablero.js y esta probada aparte -- el orden y la
   * numeracion tienen casos borde (prioridad ausente, sin fecha de origen)
   * que dentro del .svelte no se pueden ejercitar sin montarlo.
   */
  const bandeja = $derived(
    bandejaDeRevision(propuestas, {
      estado: filtroEstado,
      nivel: filtroNivel,
      tipo: filtro,
      conPropuesta: filtroPropuesta
    })
  );

  /** Cuantas hay en cada estado, para que la pastilla no mienta. */
  const conteoPorEstado = $derived.by(() => {
    const pend = bandejaDeRevision(propuestas, { estado: 'pendientes' }).length;
    return { pendientes: pend, decididas: propuestas.length - pend, '': propuestas.length };
  });

  /**
   * Cuantas hay en cada nivel DENTRO del estado elegido.
   *
   * Cuenta sobre el mismo subconjunto que la tabla muestra, no sobre el total:
   * si la bandeja esta en 'pendientes', una pastilla que diga 'Alta (80)'
   * contando tambien las ya decididas filtra a un numero distinto del que
   * anuncia.
   */
  const conteoPorNivel = $derived.by(() => {
    const base = bandejaDeRevision(propuestas, { estado: filtroEstado });
    /** @type {Record<string, number>} */
    const cuenta = {};
    for (const p of base) cuenta[p.nivel.texto] = (cuenta[p.nivel.texto] ?? 0) + 1;
    return cuenta;
  });
  const SIN_DATO = BLOQUES_SIN_DATO;

  /**
   * Cuantas filas se ven antes de tener que desplazar, en las dos tablas.
   *
   * Con las 93 propuestas de hoy las dos tablas median ~9.900px juntas: unas
   * once pantallas solo de tablas, y todo lo de abajo --los tecnicos, las
   * ordenes, la actividad-- quedaba a un viaje de distancia. El numero no
   * esconde nada: la insignia dice cuantas se ven y el pie cuantas quedan.
   *
   * Vive aca y no en el CSS porque los dos textos lo necesitan: un alto fijo
   * en la hoja y un "se ven 5" escrito a mano se desincronizan en cuanto
   * alguien toca uno de los dos.
   */
  const FILAS_A_LA_VISTA = 5;

  /** El icono de cada KPI. Decora; el numero y su rotulo dicen todo lo demas. */
  const ICONO_KPI = {
    hallazgos: 'radar',
    propuestas: 'assignment_turned_in',
    sla: 'schedule',
    sin_programar: 'event_busy',
    bloqueados: 'block',
    desinc: 'sync_problem'
  };

  /**
   * Los tipos de señal presentes, para las pildoras. Se derivan de lo que el
   * backend devolvio: una pildora fija que filtra a cero es peor que no
   * estar. El `tipo_senal` viaja tal cual -- el rotulo es el
   * `tipo_senal_display` que manda el backend, no una traduccion propia.
   */
  const porSenal = $derived.by(() => {
    /** @type {Map<string, {etiqueta: string, n: number}>} */
    const cuenta = new Map();
    for (const p of propuestas) {
      const previo = cuenta.get(p.tipo_senal);
      cuenta.set(p.tipo_senal, { etiqueta: p.tipo_senal_display, n: (previo?.n ?? 0) + 1 });
    }
    return [...cuenta.entries()].sort((a, b) => b[1].n - a[1].n);
  });



  const pendientes = $derived(propuestas.filter((/** @type {any} */ p) => p.estado === 'propuesta'));
  const fueraDeAlcance = $derived(
    propuestas.filter((/** @type {any} */ p) => p.dentro_del_alcance === false).length
  );

  const ultimaPropuesta = $derived(
    propuestas
      .map((/** @type {any} */ p) => p.created_at)
      .filter(Boolean)
      .sort()
      .at(-1) ?? null
  );

  const fecha = (/** @type {string|null} */ iso) =>
    iso
      ? new Date(iso).toLocaleString('es-CO', {
          day: '2-digit',
          month: 'short',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit'
        })
      : '—';
  const hora = (/** @type {string|null} */ iso) =>
    iso ? new Date(iso).toLocaleTimeString('es-CO', { hour: '2-digit', minute: '2-digit' }) : '—';
  const fechaCorta = (/** @type {string|null} */ iso) =>
    iso
      ? new Date(iso).toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' })
      : '—';

  /** El sobre del indicador dice cuanto confiar en el numero. */
  function leyendaIndicador(/** @type {any} */ d) {
    if (!d || d.estado === 'SIN_DATO') return 'El backend no entregó este indicador';
    if (d.estado === 'VALIDO') return 'Dato completo';
    if (d.estado === 'NO_APLICA') return 'No aplica en el período';
    const pct = d.cobertura != null ? ` (${Math.round(d.cobertura * 100)}% de cobertura)` : '';
    return `Datos insuficientes${pct}`;
  }

  /**
   * Abre el panel lateral y pide la ficha. Una sola peticion por apertura; si
   * falla, el panel lo dice y no deja un cargando colgado.
   *
   * @param {string} id
   */
  async function abrirDetalle(id) {
    abierta = id;
    detalle = null;
    errorDetalle = null;
    cargandoDetalle = true;
    try {
      const r = await fetch(`/api/supervisor-noc/propuestas/${id}`);
      const cuerpo = await r.json().catch(() => ({}));
      if (!r.ok) {
        errorDetalle = cuerpo?.error ?? 'No fue posible consultar esta propuesta.';
      } else {
        detalle = cuerpo;
      }
    } catch {
      errorDetalle = 'No fue posible consultar esta propuesta: el servicio no respondió.';
    } finally {
      cargandoDetalle = false;
    }
  }

  /** Escape cierra el panel. Con media pantalla, llegar a la X es un viaje. */
  function alTeclado(/** @type {KeyboardEvent} */ e) {
    if (e.key === 'Escape' && abierta) cerrarDetalle();
  }

  function cerrarDetalle() {
    abierta = null;
    detalle = null;
    errorDetalle = null;
  }

  // ---------------------------------------------------------------------
  //  ENVIOS
  //  Todos refrescan desde el backend al terminar (`invalidateAll`). Nunca
  //  se corrige el estado local suponiendo que la operacion salio bien: si
  //  el backend la rechazo, la pantalla tiene que mostrar lo que el backend
  //  dice, no lo que la pantalla esperaba.
  // ---------------------------------------------------------------------
  const alCorrerCiclo = () => {
    corriendo = true;
    return async (/** @type {any} */ { update }) => {
      corriendo = false;
      modalCiclo = false;
      await update({ reset: false });
      await invalidateAll();
    };
  };

  const alCorrerAsistente = (/** @type {string} */ dominio) => () => {
    asistenteCorriendo = dominio;
    return async (/** @type {any} */ { update }) => {
      asistenteCorriendo = null;
      await update({ reset: false });
      await invalidateAll();
    };
  };


  /** Donde esta la propuesta abierta dentro de la lista visible. */
  const posicion = $derived.by(() => {
    const indice = bandeja.findIndex((/** @type {any} */ p) => p.id === abierta);
    return { indice, total: bandeja.length };
  });

  /** Salta a la anterior o la siguiente sin cerrar el panel. */
  function irA(/** @type {number} */ paso) {
    const destino = bandeja[posicion.indice + paso];
    if (destino) abrirDetalle(destino.id);
  }

  // Las derivaciones de la ficha viven en $lib/v2/supervisor-noc-detalle.js:
  // son reglas de presentacion con casos borde, y probarlas exige poder
  // llamarlas sin montar el componente.
  const comun = $derived(comunDeEvidencia(detalle?.evidencia));
  const fuentes = $derived(fuentesDeEvidencia(detalle?.evidencia));
  const basePrioridad = $derived(baseDePrioridad(detalle?.evidencia));
  const contraste = $derived(contrasteDeEstados(detalle?.evidencia));
  const antiguedad = $derived(antiguedadDelCaso(detalle?.evidencia));
  const lectura = $derived(lecturaExterna(detalle?.evidencia));

  const alDecidir = () => async (/** @type {any} */ { update }) => {
    revisando = null;
    comentario = '';
    await update({ reset: false });
    await invalidateAll();
    // La ficha abierta quedo vieja: su estado acaba de cambiar.
    if (abierta) await abrirDetalle(abierta);
  };
</script>

<svelte:window onkeydown={alTeclado} />

<svelte:head>
  <title>Supervisor NOC IA · {data.org ?? 'Operaciones'}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin="" />
  <link
    href="https://fonts.googleapis.com/css2?family=Hanken+Grotesk:wght@600;700&family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;700&family=Material+Symbols+Outlined:opsz,wght,FILL,GRAD@20..48,100..700,0..1,-50..200&display=swap"
    rel="stylesheet"
  />
</svelte:head>

<div class="snoc">
  <!--
    v2-scroll NO ES DECORACION: es el unico contenedor que hace scroll.

    El shell de (app) es `height:100vh; overflow:hidden` y `.v2-main`
    tambien recorta (lib/v2/styles/v2.css). Sin esta envoltura la pantalla
    se ve entera solo si cabe: todo lo que pasa del alto de la ventana
    queda recortado y no hay forma de llegar a lo de abajo.

    Es el mismo fallo que settings/guias-tv dejo escrito el 10/09/2026, y
    volvio a pasar por la misma razon: la pantalla trae su propio CSS y se
    ve completa sin el mientras el contenido quepa. Los dos modales quedan
    FUERA -- son position:fixed y cubren la ventana, no el contenido
    desplazado.
  -->
  <div class="v2-scroll">
    <div class="snoc-lienzo">
      {#if !data.puedeVer}
        <section class="snoc-panel">
          <div class="snoc-fila">
            <span class="snoc-icono snoc-error-txt" style="font-size:28px;">lock</span>
            <div class="snoc-pila-xs">
              <h1 class="snoc-h2">Supervisor NOC IA</h1>
              <p class="snoc-body snoc-secundario">
                Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede ver y revisar las propuestas. Tu rol es
                <strong class="snoc-mono">{data.rol ?? 'sin rol'}</strong>.
              </p>
            </div>
          </div>
        </section>
      {:else}
        <!-- ============ CABECERA ============ -->
        <header class="snoc-fila-sep" style="flex-wrap:wrap; padding-bottom:var(--snoc-sm);">
          <div class="snoc-fila">
            <div class="snoc-marca-grande">
              <span class="snoc-icono" style="font-size:28px;">psychology</span>
            </div>
            <div class="snoc-pila-xs">
              <div class="snoc-fila">
                <h1 class="snoc-h1">Supervisor NOC IA</h1>
                <span class="snoc-insignia snoc-insignia-neutra snoc-primario">Shadow Mode</span>
              </div>
              <p class="snoc-body snoc-secundario">
                Observa la operación, la analiza y propone. La decisión es humana.
              </p>
            </div>
          </div>

          <div class="snoc-fila" style="gap:var(--snoc-sm);">
            <span
              class="snoc-mono-sm snoc-tenue"
              title="Derivado de la propuesta más reciente: el backend no registra cuándo corrió el ciclo."
            >
              Última propuesta: {ultimaPropuesta ? fecha(ultimaPropuesta) : 'ninguna todavía'}
            </span>
            <button
              class="snoc-btn snoc-btn-primario"
              type="button"
              onclick={() => (modalCiclo = true)}
              disabled={corriendo}
            >
              <span class="snoc-icono" style="font-size:14px;">refresh</span>
              <span>{corriendo ? 'Analizando…' : 'Ejecutar ciclo'}</span>
            </button>
          </div>

          <div class="snoc-envuelve snoc-pestanas" style="width:100%; order:3;">
            <a class="snoc-pildora snoc-pildora-activa" href="/supervisor-noc">Pendientes por revisión</a>
            <a class="snoc-pildora" href="/supervisor-noc/programacion">Programación</a>
          </div>
        </header>

        <!--
          ============ ESTADO DEL MOTOR ============
          Una sola línea. Antes esto eran cuatro tarjetas, un banner y una barra
          de controles diciendo lo mismo: «la IA no ejecuta» aparecía cuatro
          veces antes del primer dato. La garantía nunca fue el mensaje repetido
          -- es que en este archivo no existe ninguna acción que ejecute algo.
        -->
        <section class="snoc-tarjeta" style="padding:var(--snoc-sm) var(--snoc-md);">
          <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-sm);">
            <div class="snoc-fila" style="gap:var(--snoc-xs);">
              <span class="snoc-icono snoc-primario" style="font-size:18px;">visibility</span>
              <span class="snoc-body-sm">Modo observación · <strong>analiza y propone, no ejecuta</strong></span>
            </div>
            <div class="snoc-envuelve">
              <span class="snoc-insignia snoc-insignia-neutra" title="Interruptor del motor, en solo lectura">
                Autonomía:
                {#if data.autonomia.estado == null}
                  <span class="snoc-tenue">no se pudo leer</span>
                {:else}
                  <span
                    class="snoc-punto {data.autonomia.permitido ? 'snoc-punto-secundario' : 'snoc-punto-error'}"
                  ></span>
                  {data.autonomia.estado}
                {/if}
              </span>
              <span class="snoc-insignia snoc-insignia-neutra">Acciones ejecutadas: 0</span>
              {#if fueraDeAlcance > 0}
                <span class="snoc-insignia snoc-insignia-error" title="Por encima del alcance de esta etapa">
                  {fueraDeAlcance} fuera de alcance
                </span>
              {/if}
            </div>
          </div>
        </section>


        <!--
          ============ PENDIENTES POR REVISIÓN ============
          Va ARRIBA, antes de los indicadores, porque es lo único de esta
          pantalla que pide una decisión de una persona. Un KPI se mira; esto
          se atiende.

          Antes eran DOS tablas con las mismas filas: «Hallazgos recientes»
          aquí y «Pendientes de revisión» al final, y como las 93 propuestas
          estaban en estado `propuesta`, coincidían fila por fila. Leerlas dos
          veces no era redundancia inofensiva -- hacía dudar de si eran dos
          cosas distintas que casualmente coincidían.

          Los botones de decisión no están en la fila: viven en «Ver detalle»,
          junto a la evidencia. Decidir sobre una fila de tabla es decidir sin
          mirar por qué.
        -->
        <section class="snoc-panel" id="pendientes">
          <div class="snoc-fila-sep" style="flex-wrap:wrap;">
            <div class="snoc-fila" style="gap:var(--snoc-xs);">
              <span class="snoc-icono snoc-primario" style="font-size:20px;">rule</span>
              <h2 class="snoc-h3">Pendientes por revisión</h2>
              {#if data.hallazgos.error}
                <span class="snoc-insignia snoc-insignia-error">sin datos</span>
              {:else}
                <span class="snoc-insignia snoc-insignia-neutra">
                  {bandeja.length}
                  {filtroEstado === 'pendientes' ? 'esperando decisión' : 'en la lista'}
                </span>
                {#if bandeja.length > FILAS_A_LA_VISTA}
                  <span class="snoc-insignia" title="Las demás están abajo, desplazando dentro de la tabla">
                    se ven {FILAS_A_LA_VISTA}
                  </span>
                {/if}
              {/if}
            </div>
            <span class="snoc-mono-sm snoc-tenue">
              Aceptar registra que estás de acuerdo · no ejecuta nada
            </span>
          </div>

          {#if !data.hallazgos.error && propuestas.length > 0}
            <!-- Los filtros se aplican en el navegador: el GET ya trajo el
                 conjunto entero, así que una vuelta al servidor por pastilla
                 sería reordenar datos que ya están en pantalla. -->
            <div class="snoc-pila-xs">
              <div class="snoc-envuelve">
                <span class="snoc-label-sm snoc-secundario" style="text-transform:uppercase; align-self:center;">
                  Revisión
                </span>
                {#each [{ v: 'pendientes', t: 'Pendientes' }, { v: 'decididas', t: 'Ya decididas' }, { v: '', t: 'Todas' }] as o (o.v)}
                  <button
                    class="snoc-pildora {filtroEstado === o.v ? 'snoc-pildora-activa' : ''}"
                    type="button"
                    onclick={() => (filtroEstado = o.v)}
                  >
                    {o.t} ({conteoPorEstado[o.v] ?? 0})
                  </button>
                {/each}
              </div>

              <div class="snoc-envuelve">
                <span class="snoc-label-sm snoc-secundario" style="text-transform:uppercase; align-self:center;">
                  Prioridad
                </span>
                <button
                  class="snoc-pildora {filtroNivel ? '' : 'snoc-pildora-activa'}"
                  type="button"
                  onclick={() => (filtroNivel = null)}
                >
                  Todas
                </button>
                {#each NIVELES_VISIBLES as nv (nv)}
                  <button
                    class="snoc-pildora {filtroNivel === nv ? 'snoc-pildora-activa' : ''}"
                    type="button"
                    onclick={() => (filtroNivel = nv)}
                    disabled={(conteoPorNivel[nv] ?? 0) === 0}
                    title="Prioridad {nv}"
                  >
                    {nv} ({conteoPorNivel[nv] ?? 0})
                  </button>
                {/each}
                <button
                  class="snoc-pildora {filtroPropuesta === 'si' ? 'snoc-pildora-activa' : ''}"
                  type="button"
                  onclick={() => (filtroPropuesta = filtroPropuesta === 'si' ? '' : 'si')}
                  title="Las que traen una acción recomendada escrita"
                >
                  Con propuesta
                </button>
                <button
                  class="snoc-pildora {filtroPropuesta === 'no' ? 'snoc-pildora-activa' : ''}"
                  type="button"
                  onclick={() => (filtroPropuesta = filtroPropuesta === 'no' ? '' : 'no')}
                  title="Detectadas, sin acción recomendada"
                >
                  Sin propuesta
                </button>
              </div>

              <div class="snoc-envuelve">
                <span class="snoc-label-sm snoc-secundario" style="text-transform:uppercase; align-self:center;">
                  Tipo
                </span>
                <button
                  class="snoc-pildora {filtro ? '' : 'snoc-pildora-activa'}"
                  type="button"
                  onclick={() => (filtro = null)}
                >
                  Todos
                </button>
                <!-- Las pastillas de tipo se derivan de lo que el backend
                     devolvió: una fija que filtra a cero es peor que no
                     estar. -->
                {#each porSenal as [clave, info] (clave)}
                  <button
                    class="snoc-pildora {filtro === clave ? 'snoc-pildora-activa' : ''}"
                    type="button"
                    onclick={() => (filtro = clave)}
                    title={clave}
                  >
                    {rotuloDeHallazgo(clave, info.etiqueta)} ({info.n})
                  </button>
                {/each}
              </div>
            </div>
          {/if}

          {#if form?.error}
            <div class="snoc-aviso">
              <span class="snoc-icono snoc-error-txt" style="font-size:18px;">error</span>
              <span class="snoc-body">{form.error}</span>
            </div>
          {:else if form?.ok && form.tipo === 'revision'}
            <div class="snoc-aviso">
              <span class="snoc-icono snoc-primario" style="font-size:18px;">check_circle</span>
              <span class="snoc-body">
                Revisión registrada: <strong>{form.decision}</strong>.
                {form.aviso ?? 'Ninguna acción se ejecutó.'}
              </span>
            </div>
          {:else if form?.ok && form.tipo === 'cancelacion'}
            <div class="snoc-aviso">
              <span class="snoc-icono snoc-primario" style="font-size:18px;">check_circle</span>
              <span class="snoc-body">Propuesta cancelada. Ninguna acción se ejecutó.</span>
            </div>
          {/if}

          {#if data.hallazgos.error}
            <div class="snoc-aviso">
              <span class="snoc-icono snoc-error-txt" style="font-size:18px;">error</span>
              <span class="snoc-body">{data.hallazgos.error.mensaje}</span>
            </div>
          {:else if propuestas.length === 0}
            <p class="snoc-body snoc-secundario">
              No hay propuestas registradas. Corré un ciclo de análisis para que el Supervisor revise la operación.
            </p>
          {:else if bandeja.length === 0}
            <p class="snoc-body snoc-secundario">
              Ninguna propuesta con esos filtros.
              <button class="snoc-enlace" type="button" onclick={limpiarFiltros}>Ver todas</button>
            </p>
          {:else}
            <div class="snoc-tabla-caja snoc-tabla-alta">
              <table class="snoc-tabla">
                <thead>
                  <tr>
                    <th style="width:2.5rem;">N.º</th>
                    <th>Prioridad</th>
                    <th>Tipo de hallazgo</th>
                    <th>Cliente</th>
                    <th>Caso / OT</th>
                    <th>Asunto del ticket</th>
                    <th>Antigüedad</th>
                    <th>Propuesta</th>
                    <th class="snoc-derecha">Acción</th>
                  </tr>
                </thead>
                <tbody>
                  {#each bandeja as p (p.id)}
                    <tr class={abierta === p.id ? 'snoc-fila-activa' : ''}>
                      <!-- La posición en lo que se está viendo, no el id: con
                           un filtro puesto, numerar por id dejaría huecos. -->
                      <td class="snoc-mono-sm snoc-tenue">{p.n}</td>
                      <td>
                        <span
                          class="snoc-insignia snoc-sla-{p.nivel.tono}"
                          title="Prioridad {p.prioridad} en la escala del Supervisor (0-99, menor es más urgente)"
                        >
                          {p.nivel.texto}
                        </span>
                        {#if !p.revision.pendiente}
                          <div>
                            <span class="snoc-insignia snoc-insignia-variante" title="Ya pasó por una persona">
                              {p.revision.texto}
                            </span>
                          </div>
                        {/if}
                      </td>
                      <td class="snoc-label">{p.rotulo}</td>
                      <td class="snoc-body-sm">
                        {#if p.cliente}
                          {p.cliente}
                        {:else}
                          <span class="snoc-celda-ausente">No disponible en la fuente</span>
                        {/if}
                      </td>
                      <td>
                        {#if p.orden_numero != null}
                          <span class="snoc-id">OT-{p.orden_numero}</span>
                        {:else if p.ticket_externo}
                          <span class="snoc-id">{p.ticket_externo}</span>
                          {#if p.proveedor_externo}
                            <div class="snoc-mono-sm snoc-tenue">{p.proveedor_externo}</div>
                          {/if}
                        {:else}
                          <span class="snoc-mono-sm snoc-tenue" title={p.origen_id}>
                            {String(p.origen_id).slice(0, 8)}
                          </span>
                        {/if}
                      </td>
                      <td class="snoc-body-sm snoc-recorte" title={p.asunto}>
                        {#if p.asunto}
                          {p.asunto}
                        {:else}
                          <span class="snoc-celda-ausente">No disponible en la fuente</span>
                        {/if}
                      </td>
                      <td class="snoc-mono-sm snoc-tenue">
                        {#if p.edad.texto}
                          {p.edad.texto}
                        {:else}
                          <span class="snoc-celda-ausente">—</span>
                        {/if}
                      </td>
                      <td class="snoc-body-sm snoc-recorte" title={p.accion_propuesta}>
                        {#if p.tienePropuesta}
                          {p.accion_propuesta}
                        {:else}
                          <span class="snoc-celda-ausente">Sin acción recomendada</span>
                        {/if}
                      </td>
                      <td class="snoc-derecha">
                        <button
                          class="snoc-btn {abierta === p.id ? 'snoc-btn-primario' : ''}"
                          type="button"
                          onclick={() => abrirDetalle(p.id)}
                        >
                          Ver detalle
                        </button>
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
            <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-xs);">
              <span class="snoc-mono-sm snoc-tenue">
                Se revisa desde «Ver detalle», junto a la evidencia.
              </span>
              {#if bandeja.length > FILAS_A_LA_VISTA}
                <span class="snoc-mono-sm snoc-tenue">
                  Se desplaza dentro de la tabla · quedan {bandeja.length - FILAS_A_LA_VISTA} más abajo
                </span>
              {/if}
            </div>
          {/if}
        </section>

        <!-- ============ LOS SEIS KPI ============ -->
        {#if data.errorIndicadores}
          <div class="snoc-aviso">
            <span class="snoc-icono snoc-error-txt" style="font-size:20px;">error</span>
            <p class="snoc-body" style="margin:0;">{data.errorIndicadores.mensaje}</p>
          </div>
        {/if}

        <section class="snoc-rejilla snoc-rejilla-2 snoc-rejilla-6">
          {#each kpis as k (k.clave)}
            {#if k.clave === 'propuestas'}
              <!--
                El unico KPI que lleva a algun lado, porque es el unico que
                tiene un destino: la bandeja de arriba. Es un <a> de verdad y
                no un div con onclick -- el teclado llega a uno y no al otro.
              -->
              <a class="snoc-kpi snoc-kpi-enlace snoc-tono-{k.tono}" href="#pendientes" onclick={irAPendientes}>
                <div class="snoc-kpi-icono">
                  <span class="snoc-icono" style="font-size:15px;">{ICONO_KPI[k.clave]}</span>
                </div>
                {#if k.n == null}
                  <span class="snoc-kpi-n snoc-sin-dato" style="font-size:1rem;">Sin dato</span>
                {:else}
                  <span class="snoc-kpi-n">{k.n}</span>
                {/if}
                <span class="snoc-kpi-titulo">{k.titulo}</span>
                <span class="snoc-kpi-sub">{k.sub}</span>
              </a>
            {:else}
              <div class="snoc-kpi snoc-tono-{k.tono}">
                <div class="snoc-kpi-icono">
                  <span class="snoc-icono" style="font-size:15px;">{ICONO_KPI[k.clave]}</span>
                </div>
                {#if k.n == null}
                  <!--
                    Un hueco, no un cero: el backend no entregó el indicador, y
                    escribir «0» aquí afirmaría que no hay ninguno.
                  -->
                  <span class="snoc-kpi-n snoc-sin-dato" style="font-size:1rem;">Sin dato</span>
                {:else}
                  <span class="snoc-kpi-n">{k.n}</span>
                {/if}
                <span class="snoc-kpi-titulo">{k.titulo}</span>
                <span class="snoc-kpi-sub">{k.sub}</span>
              </div>
            {/if}
          {/each}
        </section>

        <!-- ============ LOS CUATRO GRÁFICOS ============ -->
        <section class="snoc-rejilla snoc-rejilla-2 snoc-rejilla-4">
          <!-- 1 · Hallazgos por tipo -->
          <div class="snoc-grafico">
            <h2 class="snoc-grafico-titulo">
              <span class="snoc-icono snoc-primario" style="font-size:15px;">donut_small</span>
              Hallazgos por tipo
            </h2>
            {#if donut.disponible}
              <div class="snoc-grafico-cuerpo">
                <div class="snoc-donut-centro">
                  <svg
                    class="snoc-donut"
                    viewBox="0 0 40 40"
                    width="110"
                    height="110"
                    role="img"
                    aria-label="Reparto de las {donut.total} propuestas por tipo de señal"
                  >
                    {#each donut.tramos as t (t.clave)}
                      <circle
                        cx="20"
                        cy="20"
                        r="15.9155"
                        fill="none"
                        stroke={t.color}
                        stroke-width="5"
                        stroke-dasharray={t.dash}
                        stroke-dashoffset={t.offset}
                      ></circle>
                    {/each}
                  </svg>
                  <span class="snoc-donut-cifra">{donut.total}</span>
                </div>
                <div class="snoc-leyenda">
                  {#each donut.tramos as t (t.clave)}
                    <div class="snoc-leyenda-fila" title="{t.etiqueta}: {t.n}">
                      <span class="snoc-leyenda-punto" style="background:{t.color};"></span>
                      <span class="snoc-leyenda-txt">{t.etiqueta}</span>
                      <span class="snoc-leyenda-n">{t.n}</span>
                    </div>
                  {/each}
                </div>
              </div>
            {:else}
              <div class="snoc-hueco">
                {#if data.hallazgos.error}
                  <span class="snoc-hueco-rotulo">Sin dato</span>
                  <p class="snoc-hueco-motivo">{data.hallazgos.error.mensaje}</p>
                {:else}
                  <span class="snoc-hueco-rotulo">Sin propuestas</span>
                  <p class="snoc-hueco-motivo">
                    Corré un ciclo de análisis para que el Supervisor revise la operación.
                  </p>
                {/if}
              </div>
            {/if}
          </div>

          <!-- 2 · Estado de casos técnicos -->
          <div class="snoc-grafico">
            <h2 class="snoc-grafico-titulo">
              <span class="snoc-icono snoc-primario" style="font-size:15px;">bar_chart</span>
              Estado de casos técnicos
            </h2>
            {#if barras.disponible}
              <div class="snoc-barras">
                {#each barras.barras as b (b.estado)}
                  <div class="snoc-barra-col" title="{b.estado}: {b.n}">
                    <span class="snoc-barra-n">{b.n}</span>
                    <div class="snoc-barra" style="height:{b.alto}%;"></div>
                    <span class="snoc-barra-txt">{b.estado}</span>
                  </div>
                {/each}
              </div>
            {:else}
              <div class="snoc-hueco">
                <span class="snoc-hueco-rotulo">Sin dato</span>
                <p class="snoc-hueco-motivo">El reparto de casos por estado no llegó en esta consulta.</p>
              </div>
            {/if}
          </div>

          <!--
            3 · Tickets por origen
            Sale de `casos.por_origen`, que agrupa por `Case.external_provider`:
            'wisphub' cuando el caso espeja un ticket del proveedor, 'dexter'
            cuando nació en el CRM. Son las dos categorías que el campo
            distingue; no se derivan otras.
          -->
          <div class="snoc-grafico">
            <h2 class="snoc-grafico-titulo">
              <span class="snoc-icono snoc-primario" style="font-size:15px;">hub</span>
              Tickets por origen
            </h2>
            {#if origen.disponible}
              <div class="snoc-grafico-cuerpo">
                <div class="snoc-donut-centro">
                  <svg
                    class="snoc-donut"
                    viewBox="0 0 40 40"
                    width="110"
                    height="110"
                    role="img"
                    aria-label="Reparto de los {origen.total} casos por sistema de origen"
                  >
                    {#each origen.tramos as t (t.clave)}
                      <circle
                        cx="20"
                        cy="20"
                        r="15.9155"
                        fill="none"
                        stroke={t.color}
                        stroke-width="5"
                        stroke-dasharray={t.dash}
                        stroke-dashoffset={t.offset}
                      ></circle>
                    {/each}
                  </svg>
                  <span class="snoc-donut-cifra">{origen.total}</span>
                </div>
                <div class="snoc-leyenda">
                  {#each origen.tramos as t (t.clave)}
                    <div class="snoc-leyenda-fila" title="{t.etiqueta}: {t.n}">
                      <span class="snoc-leyenda-punto" style="background:{t.color};"></span>
                      <span class="snoc-leyenda-txt">{t.etiqueta}</span>
                      <span class="snoc-leyenda-n">{t.n}</span>
                      <span class="snoc-tenue">{t.pct}%</span>
                    </div>
                  {/each}
                </div>
              </div>
            {:else}
              <div class="snoc-hueco">
                <span class="snoc-hueco-rotulo">Sin dato</span>
                <p class="snoc-hueco-motivo">
                  Ningún caso trae sistema de origen en esta consulta.
                </p>
              </div>
            {/if}
          </div>

          <!-- 4 · Mapa de operación · LAS COORDENADAS ESTAN EN LA ORDEN, NO EN LA PROPUESTA -->
          <div class="snoc-grafico">
            <h2 class="snoc-grafico-titulo">
              <span class="snoc-icono snoc-tenue" style="font-size:15px;">map</span>
              {SIN_DATO.mapa.titulo}
            </h2>
            <div class="snoc-hueco">
              <span class="snoc-hueco-rotulo">Falta en el backend</span>
              <p class="snoc-hueco-motivo">{SIN_DATO.mapa.motivo}</p>
            </div>
          </div>
        </section>

        <!-- ============ LOS TRES BLOQUES DE ABAJO ============ -->
        <section class="snoc-rejilla snoc-rejilla-2 snoc-rejilla-3">
          <!-- Técnicos · carga operativa -->
          <div class="snoc-grafico" id="tecnicos">
            <div class="snoc-fila-sep">
              <h2 class="snoc-grafico-titulo">
                <span class="snoc-icono snoc-primario" style="font-size:15px;">engineering</span>
                Técnicos · carga operativa
              </h2>
              <a class="snoc-pildora" href="/supervisor-noc/programacion">Ver todos</a>
            </div>
            {#if data.capacidad.error}
              <div class="snoc-hueco">
                <span class="snoc-hueco-rotulo">Sin dato</span>
                <p class="snoc-hueco-motivo">{data.capacidad.error.mensaje}</p>
              </div>
            {:else if !tecnicos.disponible}
              <div class="snoc-hueco">
                <span class="snoc-hueco-rotulo">Nadie con jornada</span>
                <p class="snoc-hueco-motivo">
                  Ninguna persona tiene jornada registrada para el {fechaCorta(data.dia)}.
                </p>
              </div>
            {:else}
              <div class="snoc-desplazable">
                {#each tecnicos.filas as t (t.id)}
                  <div class="snoc-tecnico">
                    <div class="snoc-tecnico-cabeza">
                      <span class="snoc-tecnico-nombre">{t.nombre}</span>
                      <span class="snoc-mono-sm {t.tono === 'critico' ? 'snoc-error-txt' : 'snoc-tenue'}">
                        {t.pct == null ? t.estado : `${t.pct}% · ${t.estado}`}
                      </span>
                    </div>
                    <div class="snoc-riel">
                      <div class="snoc-riel-relleno snoc-riel-{t.tono}" style="width:{t.ancho}%;"></div>
                    </div>
                    {#if t.faltantes > 0}
                      <span class="snoc-mono-sm snoc-tenue">
                        {t.faltantes} orden{t.faltantes === 1 ? '' : 'es'} sin duración: la carga real puede ser mayor
                      </span>
                    {/if}
                  </div>
                {/each}
              </div>
            {/if}
          </div>

          <!-- Órdenes de trabajo -->
          <div class="snoc-grafico" id="programacion">
            <div class="snoc-fila-sep">
              <h2 class="snoc-grafico-titulo">
                <span class="snoc-icono snoc-primario" style="font-size:15px;">assignment</span>
                Órdenes de trabajo
              </h2>
              <a class="snoc-pildora" href="/supervisor-noc/programacion">Ver programación</a>
            </div>
            {#if ordenes.disponible}
              <div class="snoc-desplazable">
                {#each ordenes.filas as f (f.clave)}
                  <div class="snoc-fila-orden">
                    <span>{f.texto}</span>
                    <span class="snoc-fila-orden-n {f.tono === 'alerta' ? 'snoc-error-txt' : ''}">{f.n}</span>
                  </div>
                {/each}
              </div>
            {:else}
              <div class="snoc-hueco">
                <span class="snoc-hueco-rotulo">Sin dato</span>
                <p class="snoc-hueco-motivo">Los indicadores de programación no llegaron en esta consulta.</p>
              </div>
            {/if}
          </div>

          <!--
            Actividad reciente del Supervisor
            De `common.Activity`, acotada a las entidades de este módulo. Un
            renglón sin usuario lo escribió la IA, y el backend lo marca con
            `es_ia`: no se deduce del texto.
          -->
          <div class="snoc-grafico">
            <h2 class="snoc-grafico-titulo">
              <span class="snoc-icono snoc-primario" style="font-size:15px;">history</span>
              Actividad reciente del Supervisor
            </h2>
            {#if data.actividad.error}
              <div class="snoc-hueco">
                <span class="snoc-hueco-rotulo">Sin dato</span>
                <p class="snoc-hueco-motivo">{data.actividad.error.mensaje}</p>
              </div>
            {:else if !actividad.disponible}
              <div class="snoc-hueco">
                <span class="snoc-hueco-rotulo">Sin actividad</span>
                <p class="snoc-hueco-motivo">
                  Todavía no hay hechos registrados en este módulo.
                </p>
              </div>
            {:else}
              <div class="snoc-tabla-caja snoc-desplazable">
                <table class="snoc-tabla">
                  <thead>
                    <tr><th>Hora</th><th>Evento</th><th>Detalle</th></tr>
                  </thead>
                  <tbody>
                    {#each actividad.filas as f (f.id)}
                      <tr>
                        <td class="snoc-mono-sm snoc-tenue" title={fecha(f.cuando)}>{hora(f.cuando)}</td>
                        <td class="snoc-body-sm">
                          {f.evento}
                          {#if f.esIa}
                            <span class="snoc-insignia snoc-insignia-neutra" title="Lo escribió el Supervisor, no una persona">IA</span>
                          {/if}
                        </td>
                        <td class="snoc-body-sm snoc-recorte" title="{f.detalle} · {f.quien}">{f.detalle}</td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            {/if}
          </div>
        </section>

        <!-- ============ ASISTENTES OPERATIVOS ============ -->
        <div class="snoc-panel" style="gap:var(--snoc-sm);">
          <div class="snoc-fila-sep">
            <div class="snoc-fila">
              <div class="snoc-chip-icono snoc-chip-icono-solido">
                <span class="snoc-icono" style="font-size:18px;">smart_toy</span>
              </div>
              <div class="snoc-pila-xs">
                <h3 class="snoc-h4">Asistentes operativos</h3>
                <span class="snoc-body-sm snoc-secundario">Analizan su dominio y proponen</span>
              </div>
            </div>
          </div>

          <div class="snoc-pila-xs">
            {#each [{ id: 'programacion', rotulo: 'Programación', desc: 'Órdenes sin programar, planes sin publicar, riesgo de plazo' }, { id: 'compromiso', rotulo: 'Compromisos', desc: 'Compromisos por vencer y dependencias pendientes' }] as a (a.id)}
              <form method="POST" action="?/asistente" use:enhance={alCorrerAsistente(a.id)}>
                <input type="hidden" name="dominio" value={a.id} />
                <div class="snoc-caja-asistente">
                  <div class="snoc-fila-sep">
                    <span class="snoc-label">{a.rotulo}</span>
                    <button class="snoc-btn snoc-btn-primario" type="submit" disabled={asistenteCorriendo !== null}>
                      <span class="snoc-icono" style="font-size:14px;">play_arrow</span>
                      {asistenteCorriendo === a.id ? 'Analizando…' : 'Analizar'}
                    </button>
                  </div>
                  <p class="snoc-body-sm snoc-secundario" style="margin:var(--snoc-xs) 0 0;">{a.desc}</p>
                </div>
              </form>
            {/each}
          </div>

          {#if form?.ok && form.tipo === 'asistente'}
            <div class="snoc-resultado">
              <span class="snoc-label-sm" style="text-transform:uppercase;">Resultado · {form.dominio}</span>
              {#each form.asistente?.recomendaciones ?? [] as r, i (i)}
                <div class="snoc-resultado-fila">
                  <span class="snoc-body-sm">{r.recomendacion ?? r.accion_propuesta ?? r.tipo_senal}</span>
                  <span class="snoc-mono-sm snoc-tenue">{r.resultado ?? ''}</span>
                </div>
              {:else}
                <span class="snoc-body-sm snoc-secundario">El asistente no encontró señales de su dominio.</span>
              {/each}
            </div>
          {:else if form?.ok && form.tipo === 'ciclo'}
            <div class="snoc-resultado">
              <span class="snoc-label-sm" style="text-transform:uppercase;">Último ciclo</span>
              <div class="snoc-mono-sm snoc-pila-xs">
                <span>Señales detectadas: <strong>{form.resumen?.senales ?? 0}</strong></span>
                <span>Propuestas nuevas: <strong>{form.resumen?.propuestas ?? 0}</strong></span>
                <span>Repetidas: <strong>{form.resumen?.repetidas ?? 0}</strong></span>
                <span>Datos insuficientes: <strong>{form.resumen?.datos_insuficientes ?? 0}</strong></span>
                <span>Expiradas: <strong>{form.resumen?.expiradas ?? 0}</strong></span>
              </div>
              <span class="snoc-mono-sm snoc-tenue">Acciones ejecutadas: {form.acciones_ejecutadas ?? 0}</span>
            </div>
          {/if}

          <div class="snoc-fila" style="gap:var(--snoc-xs); padding-top:var(--snoc-xs);">
            <span class="snoc-icono snoc-primario" style="font-size:13px;">gavel</span>
            <span class="snoc-mono-sm snoc-tenue">
              Los asistentes solo leen y proponen. No programan, no asignan y no llaman a ningún sistema externo.
            </span>
          </div>
        </div>
      {/if}
    </div>
  </div>

  <!-- ============ MODAL DE DETALLE DEL HALLAZGO ============ -->
  {#if abierta}
    <div
      class="snoc-velo snoc-velo-centrado"
      role="presentation"
      onclick={(e) => {
        if (e.target === e.currentTarget) cerrarDetalle();
      }}
    >
      <div class="snoc-modal-hallazgo" role="dialog" aria-modal="true" aria-labelledby="snoc-hallazgo-titulo">
        <!-- CABECERA: navegación entre hallazgos -->
        <div class="snoc-modal-cabecera">
          <div class="snoc-fila" style="gap:var(--snoc-xs);">
            {#if posicion.total > 1}
              <button
                class="snoc-btn"
                type="button"
                onclick={() => irA(-1)}
                disabled={posicion.indice <= 0 || cargandoDetalle}
              >
                <span class="snoc-icono" style="font-size:16px;">chevron_left</span> Anterior
              </button>
              <span class="snoc-mono-sm snoc-contador">{posicion.indice + 1} de {posicion.total}</span>
              <button
                class="snoc-btn"
                type="button"
                onclick={() => irA(1)}
                disabled={posicion.indice >= posicion.total - 1 || cargandoDetalle}
              >
                Siguiente <span class="snoc-icono" style="font-size:16px;">chevron_right</span>
              </button>
            {/if}
          </div>
          <div class="snoc-fila" style="gap:var(--snoc-sm);">
            <span class="snoc-insignia snoc-insignia-neutra">
              <span class="snoc-punto snoc-punto-primario"></span> Observación · sin ejecución
            </span>
            <button class="snoc-btn" type="button" onclick={cerrarDetalle} aria-label="Cerrar">
              <span class="snoc-icono" style="font-size:18px;">close</span>
            </button>
          </div>
        </div>

        <div class="snoc-modal-cuerpo">
          {#if cargandoDetalle}
            <div class="snoc-cargando">
              <span class="snoc-icono snoc-girando" style="font-size:22px;">progress_activity</span>
              <span class="snoc-body snoc-secundario">Consultando la propuesta…</span>
            </div>
          {:else if errorDetalle}
            <div class="snoc-aviso">
              <span class="snoc-icono snoc-error-txt" style="font-size:18px;">error</span>
              <span class="snoc-body">{errorDetalle}</span>
            </div>
          {:else if detalle}
            <div class="snoc-fila-sep" style="flex-wrap:wrap;">
              <h3 class="snoc-h2" id="snoc-hallazgo-titulo">DETALLE DEL HALLAZGO</h3>
              <span class="snoc-mono-sm snoc-tenue">Leído {haceCuanto(comun?.leido ?? detalle.created_at)}</span>
            </div>

            <!-- LA DISCREPANCIA -->
            <div class="snoc-hallazgo">
              <div class="snoc-fila-sep" style="flex-wrap:wrap;">
                <div class="snoc-fila" style="gap:var(--snoc-xs);">
                  <span class="snoc-icono" style="font-size:18px;">warning</span>
                  <span class="snoc-hallazgo-titulo">{detalle.tipo_senal_display}</span>
                </div>
                <span class="snoc-mono-sm">{detalle.origen_tipo} · {String(detalle.origen_id).slice(0, 8)}</span>
              </div>

              {#if contraste}
                <div class="snoc-mismatch">
                  <div class="snoc-mismatch-lado">
                    <span class="snoc-label-sm" style="text-transform:uppercase;">En el CRM</span>
                    <span class="snoc-h4">{contraste.crm}</span>
                  </div>
                  <span class="snoc-mismatch-vs">≠</span>
                  <div class="snoc-mismatch-lado">
                    <span class="snoc-label-sm" style="text-transform:uppercase;">En el proveedor</span>
                    <span class="snoc-h4">{contraste.proveedor}</span>
                  </div>
                </div>
              {:else}
                <p class="snoc-body" style="margin:0;">{detalle.motivo || 'Sin motivo registrado.'}</p>
              {/if}
            </div>

            <!-- TIRA DE CINCO -->
            <div class="snoc-tira">
              <span class="snoc-tira-item">
                <span class="snoc-label-sm snoc-tenue">Estado</span>
                <span class="snoc-insignia {estadoDe(detalle.estado).clase}">{estadoDe(detalle.estado).texto}</span>
              </span>
              <span class="snoc-tira-item">
                <span class="snoc-label-sm snoc-tenue">Prioridad</span>
                <span class="snoc-mono">
                  {detalle.prioridad}{#if basePrioridad}<span class="snoc-tenue"> · {basePrioridad}</span>{/if}
                </span>
              </span>
              <span class="snoc-tira-item">
                <span class="snoc-label-sm snoc-tenue">Autonomía</span>
                <span class="snoc-mono">
                  {detalle.nivel_autonomia_requerido} · {NIVELES[detalle.nivel_autonomia_requerido] ?? '—'}
                </span>
              </span>
              <span class="snoc-tira-item">
                <span class="snoc-label-sm snoc-tenue">Detección</span>
                <span class="snoc-mono">{haceCuanto(detalle.created_at)}</span>
              </span>
              <span class="snoc-tira-item">
                <span class="snoc-label-sm snoc-tenue">Expira</span>
                <span class="snoc-mono">{expiraEn(detalle.expira_en)}</span>
              </span>
            </div>

            <!-- DOS COLUMNAS: identificación y contexto -->
            <div class="snoc-dos-columnas">
              <section class="snoc-columna">
                <div class="snoc-columna-titulo">
                  <span class="snoc-icono snoc-primario" style="font-size:16px;">fingerprint</span>
                  <span class="snoc-label" style="text-transform:uppercase; letter-spacing:0.06em;">
                    Identificación de la señal
                  </span>
                </div>
                <dl class="snoc-lista-datos">
                  <div><dt>Tipo de señal</dt><dd>{detalle.tipo_senal_display}</dd></div>
                  <div><dt>Clave técnica</dt><dd class="snoc-mono-sm">{detalle.tipo_senal}</dd></div>
                  <div><dt>Estado actual</dt><dd>{estadoDe(detalle.estado).texto}</dd></div>
                  <div>
                    <dt>Nivel de autonomía</dt>
                    <dd>{detalle.nivel_autonomia_requerido} · {NIVELES[detalle.nivel_autonomia_requerido] ?? '—'}</dd>
                  </div>
                  <div><dt>Fecha de creación</dt><dd class="snoc-mono-sm">{fecha(detalle.created_at)}</dd></div>
                  <div><dt>Fecha de expiración</dt><dd class="snoc-mono-sm">{fecha(detalle.expira_en)}</dd></div>
                  <div><dt>Tipo de origen</dt><dd>{detalle.origen_tipo}</dd></div>
                  <div><dt>Organización</dt><dd>{data.org ?? '—'}</dd></div>
                  <div>
                    <dt>Alcance de la etapa</dt>
                    <dd>{detalle.dentro_del_alcance === false ? 'Fuera del alcance vigente' : 'Dentro del alcance'}</dd>
                  </div>
                </dl>
              </section>

              <section class="snoc-columna">
                <div class="snoc-columna-titulo">
                  <span class="snoc-icono snoc-primario" style="font-size:16px;">dvr</span>
                  <span class="snoc-label" style="text-transform:uppercase; letter-spacing:0.06em;">
                    Contexto operativo
                  </span>
                </div>
                <dl class="snoc-lista-datos">
                  {#if antiguedad}
                    <div>
                      <dt>Antigüedad del caso</dt>
                      <dd>
                        {antiguedad.dias != null ? `${antiguedad.dias} días` : '—'}
                        <span class="snoc-mono-sm snoc-tenue">· desde {antiguedad.desde}</span>
                      </dd>
                    </div>
                  {/if}
                  <div>
                    <dt>Caso / orden relacionada</dt>
                    <dd>
                      <span class="snoc-mono-sm">{String(detalle.origen_id).slice(0, 8)}</span>
                      {#if detalle.origen_tipo === 'case'}
                        <a class="snoc-enlace-externo" href="/tickets/{detalle.origen_id}">
                          Ver en el CRM <span class="snoc-icono" style="font-size:13px;">open_in_new</span>
                        </a>
                      {/if}
                    </dd>
                  </div>
                  <div>
                    <dt>Responsable sugerido</dt>
                    <dd>
                      {detalle.responsable_sugerido_email ?? 'Ninguno'}
                      <span class="snoc-mono-sm snoc-tenue">· sugerido, no asignado</span>
                    </dd>
                  </div>
                  {#if detalle.impacto}
                    <div><dt>Afectación operativa</dt><dd>{detalle.impacto}</dd></div>
                  {/if}
                  {#if lectura}
                    <div><dt>Última verificación externa</dt><dd class="snoc-mono-sm">{lectura}</dd></div>
                  {/if}
                  {#if detalle.conocimiento_version}
                    <div><dt>Versión de conocimiento</dt><dd class="snoc-mono-sm">{detalle.conocimiento_version}</dd></div>
                  {/if}
                </dl>
                <div class="snoc-ausente">
                  <span class="snoc-icono snoc-tenue" style="font-size:14px;">info</span>
                  <span class="snoc-mono-sm snoc-tenue">
                    No llegan en esta respuesta: {CONTEXTO_AUSENTE.join(' · ')}.
                  </span>
                </div>
              </section>
            </div>

            <!-- ANÁLISIS -->
            <section class="snoc-analisis-caja">
              <div class="snoc-fila-sep" style="flex-wrap:wrap;">
                <div class="snoc-fila" style="gap:var(--snoc-xs);">
                  <span class="snoc-icono snoc-primario" style="font-size:18px;">psychology</span>
                  <span class="snoc-label" style="text-transform:uppercase; letter-spacing:0.06em;">
                    Análisis del Supervisor NOC IA
                  </span>
                </div>
                <span class="snoc-mono-sm snoc-tenue">calculado en código, no por un modelo</span>
              </div>

              <div class="snoc-pila-xs">
                <span class="snoc-label-sm snoc-tenue" style="text-transform:uppercase;">Situación identificada</span>
                <p class="snoc-body" style="margin:0;">{detalle.tipo_senal_display}</p>
              </div>

              <div class="snoc-pila-xs">
                <span class="snoc-label-sm snoc-tenue" style="text-transform:uppercase;">Evaluación</span>
                <p class="snoc-body" style="margin:0;">{detalle.motivo || 'Sin motivo registrado.'}</p>
              </div>

              <div class="snoc-pila-xs">
                <span class="snoc-label-sm snoc-tenue" style="text-transform:uppercase;">Recomendación sugerida</span>
                <p class="snoc-body-lg snoc-accion" style="margin:0;">{detalle.accion_propuesta}</p>
                <span class="snoc-mono-sm snoc-tenue">No invasiva · requiere confirmación humana</span>
              </div>

              {#if fuentes.length}
                <div class="snoc-pila-xs">
                  <span class="snoc-label-sm snoc-tenue" style="text-transform:uppercase;">Datos auditados</span>
                  <div class="snoc-envuelve">
                    {#each fuentes as f (f)}
                      <span class="snoc-insignia snoc-insignia-neutra">{f}</span>
                    {/each}
                  </div>
                </div>
              {/if}
            </section>

            <!-- EVIDENCIA COMO TABLA -->
            <details class="snoc-detalles">
              <summary class="snoc-label-sm">
                Ver análisis técnico completo ({(detalle.evidencia ?? []).length} observaciones registradas)
              </summary>
              <div style="padding-top:var(--snoc-sm);">
                {#if Array.isArray(detalle.evidencia) && detalle.evidencia.length}
                  <div class="snoc-tabla-caja">
                    <table class="snoc-tabla">
                      <thead>
                        <tr><th>Fuente</th><th>Observación</th><th>Referencia</th><th>Leído</th></tr>
                      </thead>
                      <tbody>
                        {#each detalle.evidencia as e, i (i)}
                          <tr>
                            <td class="snoc-mono-sm">{e.fuente ?? '—'}</td>
                            <td class="snoc-body-sm">{e.dato}</td>
                            <td class="snoc-mono-sm snoc-tenue">{e.id ?? '—'}</td>
                            <td class="snoc-mono-sm snoc-tenue">{fecha(e.observado_en)}</td>
                          </tr>
                        {/each}
                      </tbody>
                    </table>
                  </div>
                {:else}
                  <span class="snoc-body snoc-secundario">Sin observaciones registradas.</span>
                {/if}
              </div>
            </details>

            <!-- INFORMACIÓN TÉCNICA -->
            <details class="snoc-detalles">
              <summary class="snoc-label-sm">Información técnica</summary>
              <div class="snoc-meta" style="margin-top:var(--snoc-sm);">
                <div style="grid-column:1 / -1;">
                  <span>ID de propuesta:</span><span class="snoc-mono-sm snoc-copiable">{detalle.id}</span>
                </div>
                <div style="grid-column:1 / -1;">
                  <span>ID de origen:</span><span class="snoc-mono-sm snoc-copiable">{detalle.origen_id}</span>
                </div>
                <div><span>Clave técnica:</span><span class="snoc-mono-sm">{detalle.tipo_senal}</span></div>
                <div><span>Actualizada:</span><span class="snoc-mono-sm">{fecha(detalle.updated_at)}</span></div>
              </div>
              {#if detalle.propuesta_original}
                <pre class="snoc-pre">{JSON.stringify(detalle.propuesta_original, null, 2)}</pre>
              {/if}
            </details>

            <!-- CICLO: revisión humana ➔ ejecución -->
            <section class="snoc-ciclo">
              <div class="snoc-fila-sep" style="flex-wrap:wrap;">
                <span class="snoc-label" style="text-transform:uppercase; letter-spacing:0.06em;">
                  Ciclo de ejecución
                </span>
                <span class="snoc-mono-sm snoc-tenue">Revisión humana ➔ Ejecución</span>
              </div>
              <ol class="snoc-pasos">
                {#each pasosDelCiclo(detalle.estado) as p (p.clave)}
                  <li class="snoc-paso {p.estado}">
                    <span class="snoc-paso-punto"></span>
                    <span class="snoc-paso-texto">{p.texto}</span>
                  </li>
                {/each}
              </ol>
              <span class="snoc-mono-sm snoc-tenue">
                Las tres últimas etapas <strong>no existen en esta etapa del producto</strong>: no hay camino de
                ejecución, y el estado «ejecutada» no está en el modelo. Se muestran para que se vea dónde termina
                lo que esta pantalla puede hacer.
              </span>
            </section>

            {#if Array.isArray(detalle.historial) && detalle.historial.length}
              <details class="snoc-detalles">
                <summary class="snoc-label-sm">Trazabilidad ({detalle.historial.length})</summary>
                <div class="snoc-pila-xs" style="padding-top:var(--snoc-sm);">
                  {#each detalle.historial as h, i (i)}
                    <div class="snoc-historial">
                      <span class="snoc-body-sm"><strong>{h.accion}</strong> · {h.descripcion}</span>
                      <span class="snoc-mono-sm snoc-tenue">
                        {h.quien === 'Supervisor NOC IA'
                          ? 'Generado por Supervisor NOC IA'
                          : `Ejecutado por usuario: ${h.quien}`} · {fecha(h.cuando)}
                      </span>
                    </div>
                  {/each}
                </div>
              </details>
            {/if}
          {/if}
        </div>

        <!-- PIE FIJO: la decisión -->
        {#if detalle && !cargandoDetalle && !errorDetalle}
          <div class="snoc-modal-pie">
            <div class="snoc-fila" style="gap:var(--snoc-xs); min-width:0;">
              <span class="snoc-icono snoc-primario" style="font-size:16px;">verified_user</span>
              <span class="snoc-body-sm snoc-secundario">
                La IA observa y propone. <strong>La decisión es tuya</strong>: aceptar no ejecuta nada.
              </span>
            </div>
            {#if detalle.estado === 'propuesta'}
              <div class="snoc-pie-acciones">
                <input class="snoc-campo" bind:value={comentario} placeholder="Motivo (para rechazar o cancelar)" />
                <form method="POST" action="?/cancelar" use:enhance={alDecidir} style="display:contents;">
                  <input type="hidden" name="id" value={detalle.id} />
                  <input type="hidden" name="motivo" value={comentario} />
                  <button class="snoc-btn" type="submit">Cancelar</button>
                </form>
                <form method="POST" action="?/revisar" use:enhance={alDecidir} style="display:contents;">
                  <input type="hidden" name="id" value={detalle.id} />
                  <input type="hidden" name="comentario" value={comentario} />
                  <button class="snoc-btn snoc-btn-error" name="decision" value="rechazada" type="submit">
                    Rechazar
                  </button>
                  <button class="snoc-btn snoc-btn-primario" name="decision" value="aceptada" type="submit">
                    Aceptar propuesta
                  </button>
                </form>
              </div>
            {:else}
              <div class="snoc-fila" style="gap:var(--snoc-sm);">
                <span class="snoc-body-sm snoc-secundario">
                  Ya revisada: <strong>{estadoDe(detalle.estado).texto}</strong>
                </span>
                <button class="snoc-btn" type="button" onclick={cerrarDetalle}>Cerrar</button>
              </div>
            {/if}
          </div>
        {/if}
      </div>
    </div>
  {/if}


  <!-- ============ MODAL DEL CICLO ============ -->
  {#if modalCiclo}
    <div
      class="snoc-velo"
      role="presentation"
      onclick={(e) => {
        if (e.target === e.currentTarget) modalCiclo = false;
      }}
    >
      <div class="snoc-modal" role="dialog" aria-modal="true" aria-labelledby="snoc-modal-titulo">
        <div class="snoc-fila snoc-primario">
          <span class="snoc-icono" style="font-size:28px;">lock_clock</span>
          <h4 class="snoc-h3" id="snoc-modal-titulo">Ejecutar ciclo de observación</h4>
        </div>
        <p class="snoc-body snoc-secundario" style="margin:0;">
          El Supervisor NOC IA analizará nuevamente la operación y podrá generar nuevas propuestas. En esta etapa
          <strong style="color:var(--snoc-on-surface);">no ejecutará acciones autónomas</strong>.
        </p>
        <div class="snoc-mono-sm snoc-caja-datos">
          <div>• Lo único que escribe: propuestas y su auditoría</div>
          <div>• Un ciclo a la vez por organización</div>
          <div>• Todo o nada: si falla a la mitad, no quedan propuestas parciales</div>
        </div>
        <form method="POST" action="?/ciclo" use:enhance={alCorrerCiclo}>
          <div class="snoc-fila" style="justify-content:flex-end; padding-top:var(--snoc-xs);">
            <button class="snoc-btn" type="button" onclick={() => (modalCiclo = false)} disabled={corriendo}>
              Cancelar
            </button>
            <button class="snoc-btn snoc-btn-primario" type="submit" disabled={corriendo}>
              {corriendo ? 'Analizando operación…' : 'Ejecutar ciclo'}
            </button>
          </div>
        </form>
      </div>
    </div>
  {/if}
</div>
