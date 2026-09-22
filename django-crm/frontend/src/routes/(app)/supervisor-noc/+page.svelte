<script>
  import { enhance } from '$app/forms';
  import { invalidateAll } from '$app/navigation';
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

  /** El filtro se aplica en el navegador: el GET ya trajo el conjunto entero. */
  const visibles = $derived(
    filtro ? propuestas.filter((/** @type {any} */ p) => p.tipo_senal === filtro) : propuestas
  );

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

  const alDecidir = () => async (/** @type {any} */ { update }) => {
    revisando = null;
    comentario = '';
    await update({ reset: false });
    await invalidateAll();
    // La ficha abierta quedo vieja: su estado acaba de cambiar.
    if (abierta) await abrirDetalle(abierta);
  };
</script>

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
              <h1 class="snoc-h1">SUPERVISOR NOC IA</h1>
              <span class="snoc-insignia snoc-insignia-neutra snoc-primario">Shadow Mode</span>
            </div>
            <p class="snoc-body snoc-secundario">
              Observa la operación, la analiza y propone. La decisión es humana.
            </p>
          </div>
        </div>

        <div class="snoc-envuelve snoc-pestanas" style="width:100%; order:3;">
          <a class="snoc-pildora snoc-pildora-activa" href="/supervisor-noc">Hallazgos y propuestas</a>
          <a class="snoc-pildora" href="/supervisor-noc/programacion">Programación</a>
        </div>

        <div class="snoc-fila snoc-chip-modo">
          <div class="snoc-chip-icono"><span class="snoc-icono" style="font-size:22px;">visibility</span></div>
          <div class="snoc-pila-xs">
            <div class="snoc-fila" style="gap:var(--snoc-xs);">
              <span class="snoc-punto snoc-punto-primario"></span>
              <span class="snoc-label" style="text-transform:uppercase; letter-spacing:0.08em;">Modo observación</span>
            </div>
            <span class="snoc-mono-sm snoc-secundario">Solo análisis y propuestas · Sin ejecución</span>
          </div>
          <span class="snoc-icono snoc-tenue" style="font-size:18px;">verified_user</span>
        </div>
      </header>

      <!-- ============ SEGURIDAD Y AUTONOMÍA ============ -->
      <section class="snoc-pila">
        <div class="snoc-rejilla snoc-rejilla-2 snoc-rejilla-4">
          <div class="snoc-tarjeta">
            <div
              class="snoc-filo {data.autonomia.permitido === false
                ? 'snoc-filo-error'
                : data.autonomia.estado == null
                  ? 'snoc-filo-neutro'
                  : 'snoc-filo-primario'}"
            ></div>
            <div class="snoc-fila-sep">
              <span class="snoc-label-sm snoc-secundario" style="text-transform:uppercase;">Estado de autonomía</span>
              <span class="snoc-icono" style="font-size:18px;">stop_circle</span>
            </div>
            <div style="margin:var(--snoc-xs) 0;">
              {#if data.autonomia.estado == null}
                <span class="snoc-insignia snoc-insignia-variante">No se pudo leer</span>
              {:else}
                <span
                  class="snoc-insignia {data.autonomia.permitido
                    ? 'snoc-insignia-secundaria-suave'
                    : 'snoc-insignia-error'}"
                >
                  <span
                    class="snoc-punto {data.autonomia.permitido ? 'snoc-punto-secundario' : 'snoc-punto-error'}"
                  ></span>
                  {data.autonomia.estado}
                </span>
              {/if}
            </div>
            <span class="snoc-body-sm snoc-tenue">
              {data.autonomia.motivo || 'Interruptor del motor · solo lectura'}
            </span>
          </div>

          <div class="snoc-tarjeta">
            <div class="snoc-filo snoc-filo-secundario"></div>
            <div class="snoc-fila-sep">
              <span class="snoc-label-sm snoc-secundario" style="text-transform:uppercase;">Techo de autonomía</span>
              <span class="snoc-icono" style="font-size:18px;">shield</span>
            </div>
            <div style="margin:var(--snoc-xs) 0;">
              <span class="snoc-insignia snoc-insignia-variante">Sin configurar</span>
            </div>
            <span class="snoc-body-sm snoc-tenue">
              {fueraDeAlcance} propuesta{fueraDeAlcance === 1 ? '' : 's'} por encima del alcance de esta etapa
            </span>
          </div>

          <div class="snoc-tarjeta">
            <div class="snoc-filo snoc-filo-primario"></div>
            <div class="snoc-fila-sep">
              <span class="snoc-label-sm snoc-secundario" style="text-transform:uppercase;">Acciones ejecutadas</span>
              <span class="snoc-icono snoc-primario" style="font-size:18px;">analytics</span>
            </div>
            <div style="margin:var(--snoc-xs) 0;"><span class="snoc-cifra">0</span></div>
            <span class="snoc-body-sm snoc-tenue">No existe estado «ejecutada» en esta etapa</span>
          </div>

          <div class="snoc-tarjeta">
            <div class="snoc-filo snoc-filo-neutro"></div>
            <div class="snoc-fila-sep">
              <span class="snoc-label-sm snoc-secundario" style="text-transform:uppercase;">
                Última propuesta registrada
              </span>
              <span class="snoc-icono snoc-tenue" style="font-size:18px;">update</span>
            </div>
            <div
              style="margin:var(--snoc-xs) 0;"
              title="Derivado de la propuesta más reciente: el backend no registra cuándo corrió el ciclo."
            >
              <span class="snoc-mono snoc-secundario">
                {ultimaPropuesta ? fecha(ultimaPropuesta) : 'Ninguna todavía'}
              </span>
            </div>
            <div class="snoc-fila-sep">
              <span class="snoc-body-sm snoc-tenue">Ciclo listo</span>
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
          </div>
        </div>

        <div class="snoc-aviso">
          <span class="snoc-icono snoc-primario" style="font-size:20px;">info</span>
          <p class="snoc-body" style="margin:0;">
            El <strong>Supervisor NOC IA</strong> está en modo observación. Analiza la operación, detecta situaciones y
            genera propuestas, <strong class="snoc-error-txt">pero no ejecuta acciones autónomas</strong>.
          </p>
          <span class="snoc-insignia" style="margin-left:auto;">Revisión humana requerida</span>
        </div>

        <div class="snoc-tarjeta" style="padding:var(--snoc-sm);">
          <div class="snoc-fila-sep" style="flex-wrap:wrap;">
            <div class="snoc-fila" style="gap:var(--snoc-xs);">
              <span class="snoc-icono snoc-primario" style="font-size:16px;">security</span>
              <span class="snoc-label-sm snoc-secundario" style="text-transform:uppercase;">
                Controles de seguridad:
              </span>
            </div>
            <div class="snoc-envuelve">
              <span class="snoc-insignia snoc-insignia-neutra">
                <span class="snoc-icono snoc-primario" style="font-size:13px;">check_circle</span>Revisión humana requerida
              </span>
              <span class="snoc-insignia snoc-insignia-neutra">
                <span class="snoc-icono snoc-primario" style="font-size:13px;">check_circle</span>Sin camino de ejecución
              </span>
              <span class="snoc-insignia">
                <span class="snoc-icono snoc-tenue" style="font-size:13px;">lock</span>Aceptar ≠ ejecutar
              </span>
              <span class="snoc-insignia snoc-insignia-secundaria-suave">Acciones ejecutadas: 0</span>
            </div>
          </div>
        </div>
      </section>

      <!-- ============ RESUMEN OPERATIVO ============ -->
      <section class="snoc-pila">
        <div class="snoc-fila-sep">
          <div class="snoc-fila" style="gap:var(--snoc-xs);">
            <h2 class="snoc-h3">Resumen operativo</h2>
            <span class="snoc-mono-sm snoc-secundario">(Corte en tiempo real)</span>
          </div>
          <span class="snoc-mono-sm snoc-tenue">Derivado en la consulta · no hay KPI guardado</span>
        </div>

        {#if data.errorIndicadores}
          <div class="snoc-aviso">
            <span class="snoc-icono snoc-error-txt" style="font-size:20px;">error</span>
            <p class="snoc-body" style="margin:0;">{data.errorIndicadores.mensaje}</p>
          </div>
        {/if}

        <div class="snoc-rejilla snoc-rejilla-2 snoc-rejilla-5">
          {#each data.resumen as k (k.clave)}
            <div class="snoc-tarjeta">
              <div class="snoc-fila-sep">
                <span class="snoc-label-sm snoc-secundario" style="text-transform:uppercase;">{k.titulo}</span>
                <span
                  class="snoc-insignia {k.tono === 'error'
                    ? 'snoc-insignia-error'
                    : k.tono === 'variante'
                      ? 'snoc-insignia-variante'
                      : k.tono === 'secundario'
                        ? 'snoc-insignia-secundaria-suave'
                        : ''}">{k.etiqueta}</span
                >
              </div>
              <div class="snoc-kpi-cifra">
                {#if k.dato.estado === 'SIN_DATO'}
                  <span class="snoc-sin-dato">Sin datos</span>
                {:else}
                  <span class="snoc-cifra">{k.dato.valor ?? '—'}</span>
                  <span class="snoc-mono-sm {k.dato.estado === 'VALIDO' ? 'snoc-tenue' : 'snoc-error-txt'}">
                    {k.dato.estado === 'VALIDO'
                      ? 'completo'
                      : k.dato.estado === 'NO_APLICA'
                        ? 'no aplica'
                        : 'parcial'}
                  </span>
                {/if}
              </div>
              <span class="snoc-body-sm snoc-tenue" title={k.dato.motivo || ''}>{leyendaIndicador(k.dato)}</span>
            </div>
          {/each}
        </div>
      </section>

      <!-- ============ TALLER ============ -->
      <div class="snoc-taller">
        <div class="snoc-col-8">
          <!-- --- HALLAZGOS --- -->
          <section class="snoc-panel">
            <div class="snoc-fila-sep" style="flex-wrap:wrap;">
              <div class="snoc-fila" style="gap:var(--snoc-xs);">
                <h3 class="snoc-h3">Hallazgos del Supervisor</h3>
                {#if data.hallazgos.error}
                  <span class="snoc-insignia snoc-insignia-error">sin datos</span>
                {:else}
                  <span class="snoc-insignia snoc-insignia-neutra">{data.hallazgos.count} registrados</span>
                {/if}
              </div>
              <span class="snoc-mono-sm snoc-tenue">Cada fila es una propuesta con su evidencia</span>
            </div>

            {#if !data.hallazgos.error && propuestas.length > 0}
              <div class="snoc-envuelve" style="padding-bottom:var(--snoc-xs);">
                <button
                  class="snoc-pildora {filtro ? '' : 'snoc-pildora-activa'}"
                  type="button"
                  onclick={() => (filtro = null)}
                >
                  Todos ({propuestas.length})
                </button>
                {#each porSenal as [clave, info] (clave)}
                  <button
                    class="snoc-pildora {filtro === clave ? 'snoc-pildora-activa' : ''}"
                    type="button"
                    onclick={() => (filtro = clave)}
                    title={clave}
                  >
                    {info.etiqueta} ({info.n})
                  </button>
                {/each}
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
            {:else if visibles.length === 0}
              <p class="snoc-body snoc-secundario">
                Ninguna propuesta de ese tipo.
                <button class="snoc-enlace" type="button" onclick={() => (filtro = null)}>Ver todas</button>
              </p>
            {:else}
              <div class="snoc-tabla-caja">
                <table class="snoc-tabla">
                  <thead>
                    <tr>
                      <th>Prioridad</th><th>Tipo</th><th>Origen</th><th>Acción propuesta</th>
                      <th>Estado</th><th>Nivel</th><th>Expira</th><th class="snoc-derecha">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {#each visibles as p (p.id)}
                      <tr class={abierta === p.id ? 'snoc-fila-activa' : ''}>
                        <td><span class="snoc-insignia {tonoPrioridad(p.prioridad)}">{p.prioridad}</span></td>
                        <td class="snoc-label">{p.tipo_senal_display}</td>
                        <td>
                          <span class="snoc-id">{p.origen_tipo}</span>
                          <div class="snoc-mono-sm snoc-tenue" title={p.origen_id}>
                            {String(p.origen_id).slice(0, 12)}
                          </div>
                        </td>
                        <td class="snoc-body-sm snoc-recorte" title={p.accion_propuesta}>{p.accion_propuesta}</td>
                        <td><span class="snoc-insignia {estadoDe(p.estado).clase}">{estadoDe(p.estado).texto}</span></td>
                        <td>
                          <span class="snoc-mono-sm" title={NIVELES[p.nivel_autonomia_requerido] ?? ''}>
                            {p.nivel_autonomia_requerido} · {NIVELES[p.nivel_autonomia_requerido] ?? '—'}
                          </span>
                          {#if p.dentro_del_alcance === false}
                            <span class="snoc-insignia snoc-insignia-error" title="Por encima del alcance de la etapa">
                              fuera
                            </span>
                          {/if}
                        </td>
                        <td class="snoc-mono-sm snoc-tenue">{fechaCorta(p.expira_en)}</td>
                        <td class="snoc-derecha">
                          <button
                            class="snoc-pildora {abierta === p.id ? 'snoc-pildora-activa' : ''}"
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
            {/if}
          </section>

          <!-- --- PENDIENTES DE REVISIÓN --- -->
          <section class="snoc-panel">
            <div class="snoc-pila-xs">
              <div class="snoc-fila-sep">
                <div class="snoc-fila" style="gap:var(--snoc-xs);">
                  <span class="snoc-icono snoc-primario" style="font-size:22px;">assignment_turned_in</span>
                  <h3 class="snoc-h3">Pendientes de revisión</h3>
                </div>
                <span class="snoc-insignia snoc-insignia-neutra">{pendientes.length} pendientes</span>
              </div>
              <div class="snoc-nota">
                <span class="snoc-icono snoc-tenue" style="font-size:16px;">verified</span>
                <span class="snoc-body-sm snoc-secundario">
                  Una propuesta <strong>NO</strong> significa que la acción se haya ejecutado. Aceptar registra que estás
                  de acuerdo, nada más: en esta etapa no hay camino de ejecución.
                </span>
              </div>
            </div>

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

            {#if pendientes.length === 0}
              <p class="snoc-body snoc-secundario">No hay propuestas esperando revisión.</p>
            {:else}
              <div class="snoc-tabla-caja">
                <table class="snoc-tabla">
                  <thead>
                    <tr>
                      <th>Origen</th><th>Tipo</th><th>Acción propuesta</th><th>Prioridad</th><th>Creada</th>
                      <th class="snoc-derecha">Decisión</th>
                    </tr>
                  </thead>
                  <tbody>
                    {#each pendientes as p (p.id)}
                      <tr>
                        <td><span class="snoc-id">{p.origen_tipo}</span></td>
                        <td class="snoc-label">{p.tipo_senal_display}</td>
                        <td class="snoc-body-sm" style="max-width:260px;">{p.accion_propuesta}</td>
                        <td><span class="snoc-insignia {tonoPrioridad(p.prioridad)}">{p.prioridad}</span></td>
                        <td class="snoc-mono-sm snoc-secundario">{fechaCorta(p.created_at)}</td>
                        <td class="snoc-derecha">
                          {#if revisando === p.id}
                            <div class="snoc-pila-xs" style="align-items:stretch; min-width:300px;">
                              <input
                                class="snoc-campo"
                                bind:value={comentario}
                                placeholder="Motivo (obligatorio para rechazar o cancelar)"
                              />
                              <div class="snoc-envuelve" style="justify-content:flex-end;">
                                <form method="POST" action="?/revisar" use:enhance={alDecidir} style="display:contents;">
                                  <input type="hidden" name="id" value={p.id} />
                                  <input type="hidden" name="comentario" value={comentario} />
                                  <button class="snoc-btn snoc-btn-primario" name="decision" value="aceptada" type="submit">
                                    Aceptar
                                  </button>
                                  <button class="snoc-btn snoc-btn-error" name="decision" value="rechazada" type="submit">
                                    Rechazar
                                  </button>
                                </form>
                                <form method="POST" action="?/cancelar" use:enhance={alDecidir} style="display:contents;">
                                  <input type="hidden" name="id" value={p.id} />
                                  <input type="hidden" name="motivo" value={comentario} />
                                  <button
                                    class="snoc-btn"
                                    type="submit"
                                    title="La condición ya no aplica: nadie opinó sobre el fondo"
                                  >
                                    Cancelar propuesta
                                  </button>
                                </form>
                                <button class="snoc-btn" type="button" onclick={() => (revisando = null)}>Cerrar</button>
                              </div>
                            </div>
                          {:else}
                            <div class="snoc-envuelve" style="justify-content:flex-end;">
                              <button class="snoc-pildora" type="button" onclick={() => abrirDetalle(p.id)}>
                                Ver contexto
                              </button>
                              <button
                                class="snoc-btn snoc-btn-primario"
                                type="button"
                                onclick={() => {
                                  revisando = p.id;
                                  comentario = '';
                                }}
                              >
                                Revisar propuesta
                              </button>
                            </div>
                          {/if}
                        </td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            {/if}
          </section>
        </div>

        <!-- ============ PANEL DERECHO ============ -->
        <div class="snoc-col-4">
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
        </div>
      </div>
    {/if}
  </div>

  <!-- ============ PANEL LATERAL DE DETALLE ============ -->
  {#if abierta}
    <div
      class="snoc-velo"
      role="presentation"
      onclick={(e) => {
        if (e.target === e.currentTarget) cerrarDetalle();
      }}
    >
      <aside class="snoc-drawer" aria-label="Detalle de la propuesta">
        <div class="snoc-drawer-cabecera">
          <div class="snoc-pila-xs">
            <span class="snoc-label-sm snoc-tenue" style="text-transform:uppercase;">Detalle del hallazgo</span>
            <h3 class="snoc-h4">{detalle?.tipo_senal_display ?? 'Cargando…'}</h3>
          </div>
          <button class="snoc-btn" type="button" onclick={cerrarDetalle} aria-label="Cerrar">
            <span class="snoc-icono" style="font-size:18px;">close</span>
          </button>
        </div>

        <div class="snoc-drawer-cuerpo">
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
            <div class="snoc-pila-xs">
              <span class="snoc-label-sm snoc-tenue" style="text-transform:uppercase;">Identificación</span>
              <div class="snoc-meta">
                <div><span>ID de propuesta:</span><span class="snoc-mono-sm">{detalle.id}</span></div>
                <div><span>Tipo de señal:</span><span class="snoc-body-sm">{detalle.tipo_senal_display}</span></div>
                <div><span>Clave técnica:</span><span class="snoc-mono-sm">{detalle.tipo_senal}</span></div>
                <div>
                  <span>Estado:</span>
                  <span class="snoc-insignia {estadoDe(detalle.estado).clase}">{estadoDe(detalle.estado).texto}</span>
                </div>
                <div><span>Prioridad:</span><span class="snoc-body-sm" style="font-weight:600;">{detalle.prioridad}</span></div>
                <div>
                  <span>Nivel de autonomía:</span>
                  <span class="snoc-mono-sm">
                    {detalle.nivel_autonomia_requerido} · {NIVELES[detalle.nivel_autonomia_requerido] ?? '—'}
                  </span>
                </div>
                <div><span>Creada:</span><span class="snoc-mono-sm">{fecha(detalle.created_at)}</span></div>
                <div><span>Expira:</span><span class="snoc-mono-sm">{fecha(detalle.expira_en)}</span></div>
                <div>
                  <span>Alcance de la etapa:</span>
                  <span class="snoc-body-sm">
                    {detalle.dentro_del_alcance === false ? 'Fuera del alcance vigente' : 'Dentro del alcance'}
                  </span>
                </div>
              </div>
            </div>

            <div class="snoc-pila-xs">
              <span class="snoc-label-sm snoc-tenue" style="text-transform:uppercase;">Origen</span>
              <div class="snoc-meta">
                <div><span>Tipo de origen:</span><span class="snoc-body-sm">{detalle.origen_tipo}</span></div>
                <div><span>ID de origen:</span><span class="snoc-mono-sm">{detalle.origen_id}</span></div>
                <div><span>Organización:</span><span class="snoc-body-sm">{data.org ?? '—'}</span></div>
              </div>
            </div>

            <div class="snoc-generado">
              <span class="snoc-icono snoc-primario" style="font-size:18px;">psychology</span>
              <div class="snoc-pila-xs">
                <span class="snoc-label-sm" style="text-transform:uppercase;">Generado por</span>
                <span class="snoc-body-sm"><strong>Supervisor NOC IA</strong> · detección automática</span>
                <span class="snoc-mono-sm snoc-tenue">
                  Ninguna persona propuso esto. La auditoría del registro no lleva usuario, y así se reconoce el origen
                  IA.
                </span>
              </div>
            </div>

            <div class="snoc-pila-xs">
              <span class="snoc-label-sm snoc-tenue" style="text-transform:uppercase;">Acción propuesta</span>
              <p class="snoc-body-lg snoc-accion">{detalle.accion_propuesta}</p>
            </div>

            <div class="snoc-pila-xs">
              <span class="snoc-label-sm snoc-tenue" style="text-transform:uppercase;">Análisis del Supervisor</span>

              <div class="snoc-analisis snoc-observado">
                <div class="snoc-fila" style="gap:var(--snoc-xs);">
                  <span class="snoc-insignia snoc-insignia-variante">Observado</span>
                  <span class="snoc-mono-sm snoc-secundario">
                    {(detalle.evidencia ?? []).length} observación{(detalle.evidencia ?? []).length === 1 ? '' : 'es'}
                  </span>
                </div>
                {#if Array.isArray(detalle.evidencia) && detalle.evidencia.length}
                  <ul class="snoc-evidencia">
                    {#each detalle.evidencia as e, i (i)}
                      <li>
                        <span class="snoc-body">{e.dato}</span>
                        <div class="snoc-mono-sm snoc-tenue">
                          <span title="De dónde salió el dato">{e.fuente ?? 'sin fuente'}</span>
                          {#if e.id}<span> · id {e.id}</span>{/if}
                          {#if e.observado_en}
                            <span title="Cuándo se LEYÓ el dato, no cuándo ocurrió el hecho">
                              · leído {fecha(e.observado_en)}
                            </span>
                          {/if}
                        </div>
                      </li>
                    {/each}
                  </ul>
                {:else}
                  <p class="snoc-body snoc-secundario" style="margin:0;">Sin observaciones registradas.</p>
                {/if}
              </div>

              <div class="snoc-analisis snoc-inferido">
                <div class="snoc-fila" style="gap:var(--snoc-xs);">
                  <span class="snoc-insignia snoc-insignia-primaria">Motivo</span>
                  <span class="snoc-mono-sm snoc-secundario">Regla de análisis, calculada en código</span>
                </div>
                <p class="snoc-body" style="margin:0;">{detalle.motivo || 'Sin motivo registrado.'}</p>
              </div>

              {#if detalle.impacto}
                <div class="snoc-analisis snoc-faltante">
                  <div class="snoc-fila" style="gap:var(--snoc-xs);">
                    <span class="snoc-insignia">Impacto</span>
                  </div>
                  <p class="snoc-body" style="margin:0;">{detalle.impacto}</p>
                </div>
              {/if}

              {#if detalle.tipo_senal === 'dato_incompleto'}
                <div class="snoc-analisis snoc-faltante">
                  <div class="snoc-fila" style="gap:var(--snoc-xs);">
                    <span class="snoc-insignia snoc-insignia-error">Datos faltantes</span>
                    <span class="snoc-mono-sm snoc-error-txt">Brecha de información operacional</span>
                  </div>
                  <p class="snoc-body" style="margin:0;">
                    Esta señal nombra objetos concretos a los que les falta un campo concreto. No es un comodín: se
                    emite solo cuando el dato ausente se puede nombrar.
                  </p>
                </div>
              {/if}

              <div class="snoc-fila" style="gap:var(--snoc-xs);">
                <span class="snoc-icono snoc-primario" style="font-size:15px;">balance</span>
                <span class="snoc-mono-sm snoc-secundario">
                  <strong>Nota de integridad:</strong> nunca se presenta una inferencia como hecho consumado.
                </span>
              </div>
            </div>

            <div class="snoc-pila-xs">
              <span class="snoc-label-sm snoc-tenue" style="text-transform:uppercase;">Trazabilidad</span>
              <div class="snoc-meta">
                <div>
                  <span>Revisada por:</span>
                  <span class="snoc-body-sm">{detalle.revisado_por_email ?? 'Todavía nadie'}</span>
                </div>
                <div><span>Fecha de revisión:</span><span class="snoc-mono-sm">{fecha(detalle.revisado_en)}</span></div>
                <div>
                  <span>Responsable sugerido:</span>
                  <span class="snoc-body-sm">{detalle.responsable_sugerido_email ?? '—'}</span>
                </div>
                <div><span>Resultado:</span><span class="snoc-body-sm">{detalle.resultado || '—'}</span></div>
                <div>
                  <span>Versión de conocimiento:</span>
                  <span class="snoc-mono-sm">{detalle.conocimiento_version || '—'}</span>
                </div>
              </div>

              {#if detalle.observaciones}
                <div class="snoc-nota">
                  <span class="snoc-body-sm"><strong>Observaciones del revisor:</strong> {detalle.observaciones}</span>
                </div>
              {/if}

              {#if detalle.propuesta_original}
                <details class="snoc-detalles">
                  <summary class="snoc-label-sm">Propuesta original (antes de modificarla)</summary>
                  <pre class="snoc-pre">{JSON.stringify(detalle.propuesta_original, null, 2)}</pre>
                </details>
              {/if}

              {#if Array.isArray(detalle.historial) && detalle.historial.length}
                <div class="snoc-pila-xs">
                  <span class="snoc-label-sm snoc-tenue" style="text-transform:uppercase;">Historial de auditoría</span>
                  {#each detalle.historial as h, i (i)}
                    <div class="snoc-historial">
                      <span class="snoc-body-sm"><strong>{h.accion}</strong> · {h.descripcion}</span>
                      <span class="snoc-mono-sm snoc-tenue">
                        {h.quien === 'Supervisor NOC IA'
                          ? 'Generado por Supervisor NOC IA'
                          : `Ejecutado por usuario: ${h.quien}`}
                        · {fecha(h.cuando)}
                      </span>
                    </div>
                  {/each}
                </div>
              {/if}
            </div>
          {/if}
        </div>
      </aside>
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
