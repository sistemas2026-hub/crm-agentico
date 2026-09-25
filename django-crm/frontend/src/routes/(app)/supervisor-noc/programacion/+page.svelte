<script>
  import { enhance } from '$app/forms';
  import { invalidateAll, goto } from '$app/navigation';
  import '../supervisor-noc.css';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let trabajando = $state(false);
  let modalSecuenciar = $state(false);
  let seleccionada = $state(/** @type {any} */ (null));

  // Paneles laterales. Cada uno pide SU dato y muestra su propio cargando: la
  // pantalla entera no se recarga para abrir una ficha.
  let drawer = $state(/** @type {'orden'|'persona'|null} */ (null));
  let ficha = $state(/** @type {any} */ (null));
  let cargandoFicha = $state(false);
  let errorFicha = $state(/** @type {string|null} */ (null));

  // Formularios de escritura, cada uno detras de su confirmacion.
  let modalReprogramar = $state(/** @type {any} */ (null));
  let modalSecuencia = $state(/** @type {any} */ (null));
  let modalAnalizar = $state(false);
  let fCuando = $state('');
  let fCausa = $state('reprogramacion');
  let fMotivo = $state('');
  let fSecuencia = $state('');

  // Programar una OT sin plan. Los planes se piden al abrir el dialogo, no en
  // cada carga de la pagina: es una accion que casi nunca se usa.
  let modalProgramar = $state(/** @type {any} */ (null));
  let planes = $state(/** @type {any[]} */ ([]));
  let cargandoPlanes = $state(false);
  let errorPlanes = $state(/** @type {string|null} */ (null));
  let fPlan = $state('');

  // Los filtros son de CLIENTE: la jornada ya vino entera para ese dia.
  let fEstado = $state('');
  let fZona = $state('');
  let fPrioridad = $state('');

  const lineas = $derived(data.jornada?.lineas ?? []);

  const opciones = (/** @type {string} */ campo) =>
    [...new Set(lineas.map((/** @type {any} */ l) => l[campo]).filter(Boolean))].sort();

  const estados = $derived(opciones('estado'));
  const zonas = $derived(opciones('zona'));
  const prioridades = $derived(opciones('prioridad'));

  const visibles = $derived(
    lineas.filter(
      (/** @type {any} */ l) =>
        (!fEstado || l.estado === fEstado) &&
        (!fZona || l.zona === fZona) &&
        (!fPrioridad || String(l.prioridad) === fPrioridad)
    )
  );

  const hora = (/** @type {string|null} */ h) => (h ? String(h).slice(0, 5) : '—');
  const fecha = (/** @type {string|null} */ iso) =>
    iso
      ? new Date(iso).toLocaleString('es-CO', {
          day: '2-digit',
          month: 'short',
          hour: '2-digit',
          minute: '2-digit'
        })
      : '—';

  /** Minutos a "7h 30m", que es como se lee una jornada. */
  const dur = (/** @type {number|null} */ m) => {
    if (m == null) return '—';
    const h = Math.floor(m / 60);
    const r = m % 60;
    return h ? `${h}h ${r ? r + 'm' : ''}`.trim() : `${r}m`;
  };

  /**
   * El riesgo viene del backend y puede ser INDETERMINADO: si falta la
   * duracion de alguna orden, no se afirma "sin sobrecarga". Esa distincion
   * es el motivo por el que capacidad.py devuelve 'faltantes'.
   */
  const RIESGO = {
    SOBRECARGA: { texto: 'Sobrecarga', clase: 'snoc-insignia-error' },
    SIN_SOBRECARGA: { texto: 'Sin sobrecarga', clase: 'snoc-insignia-secundaria-suave' },
    INDETERMINADO: { texto: 'Indeterminado', clase: 'snoc-insignia-variante' }
  };
  const riesgoDe = (/** @type {any} */ r) => {
    const clave = typeof r === 'string' ? r : r?.estado;
    return RIESGO[/** @type {keyof typeof RIESGO} */ (clave)] ?? { texto: clave ?? '—', clase: 'snoc-insignia' };
  };

  const ocupacionDe = (/** @type {any} */ p) => {
    const j = p?.jornada?.minutos;
    const c = p?.carga?.minutos_conocidos;
    if (!j || c == null) return null;
    return Math.round((c / j) * 100);
  };

  /**
   * La ficha de una orden. El recorte de datos del cliente --sin telefono ni
   * GPS-- lo hace el servidor: aca llega ya recortada.
   *
   * @param {string} ordenId
   */
  async function abrirOrden(ordenId) {
    drawer = 'orden';
    ficha = null;
    errorFicha = null;
    cargandoFicha = true;
    try {
      const r = await fetch(`/api/supervisor-noc/ordenes/${ordenId}`);
      const cuerpo = await r.json().catch(() => ({}));
      if (!r.ok) errorFicha = cuerpo?.error ?? 'No fue posible consultar la orden.';
      else ficha = cuerpo;
    } catch {
      errorFicha = 'No fue posible consultar la orden: el servicio no respondió.';
    } finally {
      cargandoFicha = false;
    }
  }

  /** @param {string} profileId */
  async function abrirPersona(profileId) {
    drawer = 'persona';
    ficha = null;
    errorFicha = null;
    cargandoFicha = true;
    try {
      const r = await fetch(`/api/supervisor-noc/carga/${profileId}?dia=${data.dia}`);
      const cuerpo = await r.json().catch(() => ({}));
      if (!r.ok) errorFicha = cuerpo?.error ?? 'No fue posible consultar la carga.';
      else ficha = cuerpo;
    } catch {
      errorFicha = 'No fue posible consultar la carga: el servicio no respondió.';
    } finally {
      cargandoFicha = false;
    }
  }

  function cerrarDrawer() {
    drawer = null;
    ficha = null;
    errorFicha = null;
  }

  /**
   * Abre el dialogo de programar y pide los planes que admiten lineas.
   *
   * `propuesta` es una recomendacion del Supervisor con señal
   * 'orden_sin_programar': su 'origen_id' ES la orden. No se inventa otra
   * fuente -- el Supervisor ya detecta cuales estan sin programar, y la
   * jornada no puede traerlas porque solo devuelve las que YA estan en un
   * plan.
   *
   * @param {any} propuesta
   */
  async function pedirProgramar(propuesta) {
    modalProgramar = propuesta;
    fCuando = `${data.dia}T08:00`;
    fCausa = '';
    fMotivo = '';
    fPlan = '';
    planes = [];
    errorPlanes = null;
    cargandoPlanes = true;
    try {
      const r = await fetch('/api/supervisor-noc/planes');
      const cuerpo = await r.json().catch(() => ({}));
      if (!r.ok) errorPlanes = cuerpo?.error ?? 'No fue posible consultar los planes.';
      else planes = cuerpo?.planes ?? [];
    } catch {
      errorPlanes = 'No fue posible consultar los planes: el servicio no respondió.';
    } finally {
      cargandoPlanes = false;
    }
  }

  /**
   * Los planes cuya semana cubre el dia elegido.
   *
   * No es una regla nueva: 'programar_orden' exige que la linea caiga entre
   * 'semana_inicio' y 'semana_fin', y el backend expone 'semana_fin' justo
   * para que la pantalla no ofrezca lo que el servicio va a rechazar.
   */
  const planesCompatibles = $derived.by(() => {
    const dia = (fCuando || '').slice(0, 10);
    if (!dia) return planes;
    return planes.filter(
      (/** @type {any} */ p) =>
        !p.semana_inicio || !p.semana_fin || (p.semana_inicio <= dia && dia <= p.semana_fin)
    );
  });

  const semana = (/** @type {any} */ p) => {
    const f = (/** @type {string} */ d) =>
      new Date(`${d}T00:00`).toLocaleDateString('es-CO', { day: '2-digit', month: 'short' });
    return `${f(p.semana_inicio)} – ${f(p.semana_fin)}`;
  };

  /** Abre la confirmacion de reprogramar, con la fecha actual de la linea. */
  function pedirReprogramar(/** @type {any} */ linea) {
    fCuando = linea.programada_para ? String(linea.programada_para).slice(0, 16) : '';
    fCausa = 'reprogramacion';
    fMotivo = '';
    modalReprogramar = linea;
  }

  /** Abre la confirmacion de cambiar secuencia. */
  function pedirSecuencia(/** @type {any} */ linea) {
    fSecuencia = String(linea.secuencia ?? 0);
    fCausa = 'cambio_de_prioridad';
    fMotivo = '';
    modalSecuencia = linea;
  }

  /**
   * Un solo envio por clic: `trabajando` ya deshabilita los dos botones del
   * modal, asi que un doble clic no llega a producir un segundo POST. Al
   * terminar se vuelve a consultar el backend -- nunca se corrige la vista
   * suponiendo que la operacion salio bien.
   */
  const alTrabajar = () => {
    trabajando = true;
    return async (/** @type {any} */ { update }) => {
      trabajando = false;
      modalSecuenciar = false;
      modalReprogramar = null;
      modalSecuencia = null;
      modalAnalizar = false;
      modalProgramar = null;
      await update({ reset: false });
      await invalidateAll();
      // La ficha abierta quedo vieja: lo que muestra acaba de cambiar.
      if (drawer === 'orden' && ficha?.id) await abrirOrden(ficha.id);
    };
  };

  /** Cambiar de día recarga la jornada: el backend exige el filtro. */
  function cambiarDia(/** @type {Event} */ e) {
    const v = /** @type {HTMLInputElement} */ (e.currentTarget).value;
    if (/^\d{4}-\d{2}-\d{2}$/.test(v)) goto(`/supervisor-noc/programacion?dia=${v}`, { keepFocus: true });
  }
</script>

<svelte:head>
  <title>Programación · Supervisor NOC IA</title>
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
            <h1 class="snoc-h2">Programación · Supervisor NOC IA</h1>
            <p class="snoc-body snoc-secundario">
              Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede ver la programación. Tu rol es
              <strong class="snoc-mono">{data.rol ?? 'sin rol'}</strong>.
            </p>
          </div>
        </div>
      </section>
    {:else}
      <!-- ============ CABECERA Y GUARDARRAÍLES ============ -->
      <section class="snoc-panel" style="gap:var(--snoc-md);">
        <div class="snoc-fila-sep" style="flex-wrap:wrap; gap:var(--snoc-md);">
          <div class="snoc-pila-xs">
            <div class="snoc-fila">
              <h1 class="snoc-h1">PROGRAMACIÓN</h1>
              <span class="snoc-insignia snoc-insignia-neutra snoc-primario">Shadow Mode</span>
            </div>
            <p class="snoc-body snoc-secundario">
              Órdenes de trabajo, carga por persona y orden propuesto de la jornada.
            </p>
          </div>

          <div class="snoc-envuelve snoc-guardarrailes">
            <span class="snoc-guardarrail">
              <span class="snoc-punto snoc-punto-primario"></span>
              <span class="snoc-label-sm snoc-secundario">MODO:</span>
              <span class="snoc-insignia snoc-insignia-neutra snoc-primario">Observación</span>
            </span>
            <span class="snoc-guardarrail">
              <span class="snoc-label-sm snoc-secundario">AUTONOMÍA:</span>
              {#if data.autonomia.estado == null}
                <span class="snoc-insignia snoc-insignia-variante">No se pudo leer</span>
              {:else}
                <span
                  class="snoc-insignia {data.autonomia.permitido
                    ? 'snoc-insignia-secundaria-suave'
                    : 'snoc-insignia-error'}">{data.autonomia.estado}</span
                >
              {/if}
            </span>
            <span class="snoc-guardarrail">
              <span class="snoc-label-sm snoc-secundario">TECHO:</span>
              <span class="snoc-insignia snoc-insignia-variante">Sin configurar</span>
            </span>
            <span class="snoc-guardarrail">
              <span class="snoc-label-sm snoc-secundario">ACCIONES:</span>
              <span class="snoc-mono" style="font-weight:700;">0</span>
            </span>
          </div>
        </div>

        <!-- Pestañas: las dos vistas del mismo módulo, alcanzables entre sí -->
        <div class="snoc-envuelve snoc-pestanas">
          <a class="snoc-pildora" href="/supervisor-noc">Pendientes por revisión</a>
          <a class="snoc-pildora snoc-pildora-activa" href="/supervisor-noc/programacion">Programación</a>
        </div>
      </section>

      <!-- ============ FILTROS ============ -->
      <section class="snoc-panel" style="gap:var(--snoc-sm);">
        <div class="snoc-filtros">
          <div class="snoc-campo-grupo">
            <label class="snoc-label-sm snoc-secundario" for="f-dia">Día de la jornada</label>
            <input id="f-dia" class="snoc-campo" type="date" value={data.dia} onchange={cambiarDia} />
          </div>
          <div class="snoc-campo-grupo">
            <label class="snoc-label-sm snoc-secundario" for="f-estado">Estado de la línea</label>
            <select id="f-estado" class="snoc-campo" bind:value={fEstado}>
              <option value="">Todos</option>
              {#each estados as e (e)}<option value={e}>{e}</option>{/each}
            </select>
          </div>
          <div class="snoc-campo-grupo">
            <label class="snoc-label-sm snoc-secundario" for="f-zona">Zona</label>
            <select id="f-zona" class="snoc-campo" bind:value={fZona}>
              <option value="">Todas</option>
              {#each zonas as z (z)}<option value={z}>{z}</option>{/each}
            </select>
          </div>
          <div class="snoc-campo-grupo">
            <label class="snoc-label-sm snoc-secundario" for="f-prio">Prioridad</label>
            <select id="f-prio" class="snoc-campo" bind:value={fPrioridad}>
              <option value="">Todas</option>
              {#each prioridades as p (p)}<option value={String(p)}>{p}</option>{/each}
            </select>
          </div>
          <div class="snoc-campo-grupo" style="justify-content:flex-end;">
            <span class="snoc-mono-sm snoc-tenue">
              {visibles.length} de {lineas.length} líneas
            </span>
          </div>
        </div>

        {#if data.diaInvalido}
          <div class="snoc-aviso">
            <span class="snoc-icono snoc-error-txt" style="font-size:18px;">warning</span>
            <span class="snoc-body">La fecha pedida no tenía formato válido. Se muestra la jornada de hoy.</span>
          </div>
        {/if}
        <span class="snoc-mono-sm snoc-tenue">
          La prioridad se muestra porque el backend la expone, pero <strong>no ordena</strong>: el orden lo da la
          secuencia.
        </span>
      </section>

      <!-- ============ RESUMEN ============ -->
      <div class="snoc-rejilla snoc-rejilla-2 snoc-rejilla-5">
        {#each data.resumen as k (k.clave)}
          <div class="snoc-tarjeta">
            <span class="snoc-label-sm snoc-secundario" style="text-transform:uppercase;">{k.titulo}</span>
            <div class="snoc-kpi-cifra">
              {#if k.dato.estado === 'SIN_DATO'}
                <span class="snoc-sin-dato">Sin datos</span>
              {:else}
                <span class="snoc-cifra">{k.dato.valor}{k.sufijo ?? ''}</span>
                {#if k.dato.estado !== 'VALIDO'}
                  <span class="snoc-mono-sm snoc-error-txt">parcial</span>
                {/if}
              {/if}
            </div>
            <span class="snoc-body-sm snoc-tenue">{k.dato.motivo || ' '}</span>
          </div>
        {/each}
      </div>

      {#if form?.error}
        <div class="snoc-aviso">
          <span class="snoc-icono snoc-error-txt" style="font-size:18px;">error</span>
          <span class="snoc-body">{form.error}</span>
        </div>
      {:else if form?.ok}
        <div class="snoc-aviso">
          <span class="snoc-icono snoc-primario" style="font-size:18px;">check_circle</span>
          <span class="snoc-body">
            {form.tipo === 'secuenciar'
              ? 'Orden propuesto actualizado. No se reprogramó ninguna orden ni se cambió ninguna asignación.'
              : 'Plan publicado. No se ejecutó ninguna programación.'}
          </span>
        </div>
      {/if}

      <div class="snoc-taller">
        <div class="snoc-col-8">
          <!-- ============ PROGRAMACIÓN OPERATIVA ============ -->
          <section class="snoc-panel">
            <div class="snoc-fila-sep" style="flex-wrap:wrap;">
              <div class="snoc-fila" style="gap:var(--snoc-xs);">
                <h3 class="snoc-h3">Programación operativa</h3>
                {#if data.jornada.error}
                  <span class="snoc-insignia snoc-insignia-error">sin datos</span>
                {:else}
                  <span class="snoc-insignia snoc-insignia-neutra">{data.jornada.count} líneas</span>
                {/if}
              </div>
              <!--
                Abre la confirmacion; el POST vive en el modal. Es la unica
                escritura de esta pantalla con efecto visible en la operacion:
                no reprograma ni reasigna, pero el orden nuevo queda registrado
                y alguien lo va a leer para trabajar.
              -->
              <div class="snoc-envuelve" style="justify-content:flex-end;">
              <button
                class="snoc-btn"
                type="button"
                onclick={() => (modalAnalizar = true)}
                disabled={trabajando}
                title="Corre el asistente de programación: lee sus señales y escribe propuestas. No programa ni asigna."
              >
                <span class="snoc-icono" style="font-size:14px;">neurology</span>
                Analizar programación
              </button>
              <button
                class="snoc-btn snoc-btn-primario"
                type="button"
                onclick={() => (modalSecuenciar = true)}
                disabled={trabajando || !!data.jornada.error || lineas.length === 0}
                title="Reordena el orden propuesto. No reprograma ninguna orden ni cambia asignaciones."
              >
                <span class="snoc-icono" style="font-size:14px;">low_priority</span>
                {trabajando ? 'Secuenciando…' : 'Secuenciar jornada'}
              </button>
              </div>
            </div>

            {#if data.jornada.error}
              <div class="snoc-aviso">
                <span class="snoc-icono snoc-error-txt" style="font-size:18px;">error</span>
                <span class="snoc-body">{data.jornada.error.mensaje}</span>
              </div>
            {:else if lineas.length === 0}
              <p class="snoc-body snoc-secundario">
                No hay ninguna orden programada para el {data.dia}. Probá con otra fecha.
              </p>
            {:else if visibles.length === 0}
              <p class="snoc-body snoc-secundario">Ninguna línea cumple esos filtros.</p>
            {:else}
              <div class="snoc-tabla-caja">
                <table class="snoc-tabla">
                  <thead>
                    <tr>
                      <th>Sec.</th><th>OT</th><th>Cliente</th><th>Horario</th>
                      <th>Zona</th><th>Prioridad</th><th>Estado línea</th><th>Estado OT</th>
                      <th class="snoc-derecha">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {#each visibles as l (l.id)}
                      <tr
                        class={seleccionada?.id === l.id ? 'snoc-fila-activa' : ''}
                        onclick={() => (seleccionada = l)}
                      >
                        <td>
                          {#if (l.secuencia ?? 0) === 0}
                            <span class="snoc-insignia snoc-insignia-variante" title="secuencia = 0 significa SIN SECUENCIAR">
                              sin sec.
                            </span>
                          {:else}
                            <span class="snoc-mono" style="font-weight:700;">{l.secuencia}</span>
                          {/if}
                        </td>
                        <td><span class="snoc-id">#{l.numero ?? '—'}</span></td>
                        <td class="snoc-body-sm snoc-recorte" title={l.cliente}>{l.cliente ?? '—'}</td>
                        <td class="snoc-mono-sm">{hora(l.hora_inicio)} – {hora(l.hora_fin)}</td>
                        <td class="snoc-body-sm">{l.zona || '—'}</td>
                        <td class="snoc-mono-sm snoc-tenue" title="Expuesta pero no ordena">{l.prioridad ?? '—'}</td>
                        <td><span class="snoc-insignia">{l.estado ?? '—'}</span></td>
                        <td class="snoc-body-sm">{l.estado_orden ?? '—'}</td>
                        <td class="snoc-derecha">
                          <div class="snoc-envuelve" style="justify-content:flex-end;">
                            <button class="snoc-pildora" type="button" onclick={() => abrirOrden(l.orden)}>
                              Ver OT
                            </button>
                            <button class="snoc-pildora" type="button" onclick={() => pedirSecuencia(l)}>
                              Secuencia
                            </button>
                            {#if l.programacion}
                              <button class="snoc-pildora" type="button" onclick={() => pedirReprogramar(l)}>
                                Reprogramar
                              </button>
                            {:else}
                              <!--
                                Sin plan no se puede reprogramar y no se
                                disimula: elegir plan exige listarlos, y no
                                hay ninguna ruta que lo haga.
                              -->
                              <button
                                class="snoc-pildora"
                                type="button"
                                disabled
                                title="Esta orden no está en ningún plan. Reprogramar exige elegir plan, y el backend todavía no expone un listado de planes semanales."
                              >
                                Reprogramar
                              </button>
                            {/if}
                          </div>
                        </td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>

              {#if data.jornada.resumen}
                <div class="snoc-nota">
                  <span class="snoc-icono snoc-tenue" style="font-size:16px;">info</span>
                  <span class="snoc-body-sm snoc-secundario">
                    {data.jornada.resumen.secuencia_cero} sin secuenciar ·
                    {data.jornada.resumen.secuencias_empatadas} secuencia(s) empatada(s), que afectan a
                    {data.jornada.resumen.lineas_en_empate} línea(s). Los empates se <strong>cuentan</strong>, no se
                    resuelven: qué hacer con ellos sigue siendo una decisión abierta del backend.
                  </span>
                </div>
              {/if}
            {/if}
          </section>

          <!-- ============ DETALLE DE LA LÍNEA ============ -->
          <section class="snoc-panel">
            {#if !seleccionada}
              <div class="snoc-fila">
                <span class="snoc-icono snoc-tenue" style="font-size:18px;">frame_inspect</span>
                <p class="snoc-body snoc-secundario" style="margin:0;">
                  Elegí una línea de la tabla para ver su ficha.
                </p>
              </div>
            {:else}
              <div class="snoc-fila-sep" style="flex-wrap:wrap;">
                <h4 class="snoc-h4">Orden #{seleccionada.numero ?? '—'} · {seleccionada.cliente ?? 'Sin cliente'}</h4>
                <span class="snoc-insignia">{seleccionada.estado ?? '—'}</span>
              </div>
              <div class="snoc-meta">
                <div><span>Secuencia:</span><span class="snoc-mono-sm">{(seleccionada.secuencia ?? 0) === 0 ? 'sin secuenciar' : seleccionada.secuencia}</span></div>
                <div><span>Día:</span><span class="snoc-mono-sm">{seleccionada.dia ?? '—'}</span></div>
                <div><span>Horario:</span><span class="snoc-mono-sm">{hora(seleccionada.hora_inicio)} – {hora(seleccionada.hora_fin)}</span></div>
                <div><span>Zona:</span><span class="snoc-body-sm">{seleccionada.zona || '—'}</span></div>
                <div><span>Prioridad:</span><span class="snoc-mono-sm">{seleccionada.prioridad ?? '—'}</span></div>
                <div><span>Estado de la OT:</span><span class="snoc-body-sm">{seleccionada.estado_orden ?? '—'}</span></div>
                <div><span>Programada para:</span><span class="snoc-mono-sm">{fecha(seleccionada.programada_para)}</span></div>
                <div><span>Semana del plan:</span><span class="snoc-mono-sm">{seleccionada.plan_semana ?? '—'}</span></div>
                <div><span>Estado del plan:</span><span class="snoc-body-sm">{seleccionada.plan_estado ?? '—'}</span></div>
              </div>

              {#if seleccionada.plan_estado === 'borrador' && seleccionada.programacion}
                <form method="POST" action="?/publicar" use:enhance={alTrabajar}>
                  <input type="hidden" name="programacion" value={seleccionada.programacion} />
                  <div class="snoc-fila-sep">
                    <span class="snoc-body-sm snoc-secundario">
                      El plan de esta semana está en borrador. Publicarlo solo cambia su estado.
                    </span>
                    <button class="snoc-btn snoc-btn-primario" type="submit" disabled={trabajando}>
                      {trabajando ? 'Publicando…' : 'Publicar plan'}
                    </button>
                  </div>
                </form>
              {/if}
            {/if}
          </section>

          <!-- ============ RECOMENDACIONES ============ -->
          <section class="snoc-panel">
            <div class="snoc-fila-sep">
              <div class="snoc-fila" style="gap:var(--snoc-xs);">
                <span class="snoc-icono snoc-primario" style="font-size:22px;">assignment_turned_in</span>
                <h3 class="snoc-h3">Recomendaciones del Supervisor</h3>
              </div>
              <span class="snoc-insignia snoc-insignia-neutra">{data.recomendaciones.length}</span>
            </div>
            <div class="snoc-nota">
              <span class="snoc-icono snoc-tenue" style="font-size:16px;">verified</span>
              <span class="snoc-body-sm snoc-secundario">
                Son las propuestas del dominio de programación, de la misma cola que la otra vista. Se revisan allí:
                esta pantalla no decide.
              </span>
            </div>

            {#if data.errorPropuestas}
              <div class="snoc-aviso">
                <span class="snoc-icono snoc-error-txt" style="font-size:18px;">error</span>
                <span class="snoc-body">{data.errorPropuestas.mensaje}</span>
              </div>
            {:else if data.recomendaciones.length === 0}
              <p class="snoc-body snoc-secundario">
                Ninguna propuesta abierta sobre programación.
              </p>
            {:else}
              <div class="snoc-rejilla snoc-rejilla-2">
                {#each data.recomendaciones.slice(0, 6) as p (p.id)}
                  <div class="snoc-tarjeta">
                    <div class="snoc-fila-sep">
                      <span class="snoc-label">{p.tipo_senal_display}</span>
                      <span class="snoc-insignia {p.prioridad === 'alta' ? 'snoc-insignia-error-solida' : 'snoc-insignia'}">
                        {p.prioridad}
                      </span>
                    </div>
                    <p class="snoc-body-sm" style="margin:var(--snoc-xs) 0;">{p.accion_propuesta}</p>
                    <div class="snoc-fila-sep">
                      <span class="snoc-mono-sm snoc-tenue">{p.origen_tipo}</span>
                      <div class="snoc-envuelve" style="justify-content:flex-end;">
                        {#if p.tipo_senal === 'orden_sin_programar' && p.estado === 'propuesta'}
                          <button class="snoc-btn snoc-btn-primario" type="button" onclick={() => pedirProgramar(p)}>
                            <span class="snoc-icono" style="font-size:14px;">event_available</span>
                            Programar
                          </button>
                        {/if}
                        <a class="snoc-pildora" href="/supervisor-noc">Revisar</a>
                      </div>
                    </div>
                  </div>
                {/each}
              </div>
            {/if}
          </section>
        </div>

        <!-- ============ CARGA POR PERSONA ============ -->
        <div class="snoc-col-4">
          <div class="snoc-panel" style="gap:var(--snoc-sm);">
            <div class="snoc-fila-sep">
              <h3 class="snoc-h4">Carga por persona</h3>
              <span class="snoc-insignia snoc-insignia-neutra">{data.capacidad.personas.length}</span>
            </div>
            <div class="snoc-nota">
              <span class="snoc-icono snoc-tenue" style="font-size:16px;">groups</span>
              <span class="snoc-body-sm snoc-secundario">
                El sistema no modela cuadrillas con nombre: asigna <strong>personas</strong> a cada orden, y la
                capacidad se calcula por persona.
              </span>
            </div>

            {#if data.capacidad.error}
              <div class="snoc-aviso">
                <span class="snoc-icono snoc-error-txt" style="font-size:18px;">error</span>
                <span class="snoc-body">{data.capacidad.error.mensaje}</span>
              </div>
            {:else if data.capacidad.personas.length === 0}
              <p class="snoc-body snoc-secundario">Nadie tiene trabajo programado ese día.</p>
            {:else}
              {#each data.capacidad.personas as p, i (p.profile?.id ?? i)}
                {@const pct = ocupacionDe(p)}
                <div class="snoc-tarjeta" style="gap:var(--snoc-xs);">
                  <div class="snoc-fila-sep">
                    <span class="snoc-label" style="text-transform:uppercase;">
                      {p.profile?.nombre ?? p.profile?.email ?? 'Sin nombre'}
                    </span>
                    <span class="snoc-insignia {riesgoDe(p.riesgo).clase}">{riesgoDe(p.riesgo).texto}</span>
                  </div>
                  {#if p.profile?.id}
                    <button class="snoc-pildora" type="button" onclick={() => abrirPersona(p.profile.id)}>
                      Ver carga del día
                    </button>
                  {/if}

                  {#if pct != null}
                    <div class="snoc-barra" title="{pct}% de la jornada comprometida">
                      <div class="snoc-barra-relleno {pct > 100 ? 'snoc-barra-exceso' : ''}" style="width:{Math.min(pct, 100)}%"></div>
                    </div>
                    <span class="snoc-cifra" style="font-size:22px; line-height:28px;">{pct}%</span>
                  {:else}
                    <span class="snoc-sin-dato">Sin datos de ocupación</span>
                  {/if}

                  <div class="snoc-mono-sm snoc-tenue snoc-pila-xs">
                    <span>jornada {dur(p.jornada?.minutos)}</span>
                    <span>carga {dur(p.carga?.minutos_conocidos)}</span>
                    <span>resto {dur(p.carga?.minutos_restantes ?? p.carga?.resto)}</span>
                  </div>

                  {#if (p.faltantes ?? []).length}
                    <div class="snoc-analisis snoc-faltante" style="padding:var(--snoc-xs) var(--snoc-sm);">
                      <span class="snoc-mono-sm snoc-error-txt">
                        {p.faltantes.length} orden(es) sin duración declarada: el porcentaje se calculó sobre lo
                        conocido, no se imputó nada.
                      </span>
                    </div>
                  {/if}
                </div>
              {/each}
            {/if}
          </div>
        </div>
      </div>
    {/if}
  </div>

  <!-- ============ CONFIRMACIÓN DE SECUENCIACIÓN ============ -->
  {#if modalSecuenciar}
    <div
      class="snoc-velo"
      role="presentation"
      onclick={(e) => {
        if (e.target === e.currentTarget && !trabajando) modalSecuenciar = false;
      }}
    >
      <div class="snoc-modal" role="dialog" aria-modal="true" aria-labelledby="snoc-sec-titulo">
        <div class="snoc-fila snoc-primario">
          <span class="snoc-icono" style="font-size:28px;">low_priority</span>
          <h4 class="snoc-h3" id="snoc-sec-titulo">¿Confirmar secuenciación de jornada?</h4>
        </div>
        <p class="snoc-body snoc-secundario" style="margin:0;">
          Esta acción modificará el orden propuesto de las órdenes para la jornada seleccionada. No reprograma ni
          reasigna técnicos, pero el nuevo orden quedará registrado y podrá ser utilizado por la operación.
        </p>
        <div class="snoc-mono-sm snoc-caja-datos">
          <div>• Jornada: {data.dia}</div>
          <div>• Líneas afectadas: {lineas.length}</div>
          <div>• Se aplica en una sola transacción</div>
        </div>
        <form method="POST" action="?/secuenciar" use:enhance={alTrabajar}>
          <input type="hidden" name="dia" value={data.dia} />
          <div class="snoc-fila" style="justify-content:flex-end; padding-top:var(--snoc-xs);">
            <button
              class="snoc-btn"
              type="button"
              onclick={() => (modalSecuenciar = false)}
              disabled={trabajando}
            >
              Cancelar
            </button>
            <button class="snoc-btn snoc-btn-primario" type="submit" disabled={trabajando}>
              {trabajando ? 'Secuenciando jornada…' : 'Confirmar secuenciación'}
            </button>
          </div>
        </form>
      </div>
    </div>
  {/if}

  <!-- ============ PANEL LATERAL: ORDEN O PERSONA ============ -->
  {#if drawer}
    <div
      class="snoc-velo"
      role="presentation"
      onclick={(e) => {
        if (e.target === e.currentTarget) cerrarDrawer();
      }}
    >
      <aside class="snoc-drawer" aria-label="Detalle">
        <div class="snoc-drawer-cabecera">
          <div class="snoc-pila-xs">
            <span class="snoc-label-sm snoc-tenue" style="text-transform:uppercase;">
              {drawer === 'orden' ? 'Orden de trabajo' : 'Carga del día'}
            </span>
            <h3 class="snoc-h4">
              {#if cargandoFicha}
                Cargando…
              {:else if drawer === 'orden'}
                Orden #{ficha?.numero ?? '—'}
              {:else}
                {ficha?.profile?.nombre ?? ficha?.profile?.email ?? 'Persona'}
              {/if}
            </h3>
          </div>
          <button class="snoc-btn" type="button" onclick={cerrarDrawer} aria-label="Cerrar">
            <span class="snoc-icono" style="font-size:18px;">close</span>
          </button>
        </div>

        <div class="snoc-drawer-cuerpo">
          {#if cargandoFicha}
            <div class="snoc-cargando">
              <span class="snoc-icono snoc-girando" style="font-size:22px;">progress_activity</span>
              <span class="snoc-body snoc-secundario">Consultando…</span>
            </div>
          {:else if errorFicha}
            <div class="snoc-aviso">
              <span class="snoc-icono snoc-error-txt" style="font-size:18px;">error</span>
              <span class="snoc-body">{errorFicha}</span>
            </div>
          {:else if ficha && drawer === 'orden'}
            <div class="snoc-pila-xs">
              <span class="snoc-label-sm snoc-tenue" style="text-transform:uppercase;">Cliente</span>
              <div class="snoc-meta">
                <div><span>Nombre:</span><span class="snoc-body-sm">{ficha.cliente?.nombre ?? '—'}</span></div>
                <div><span>Dirección:</span><span class="snoc-body-sm">{ficha.cliente?.direccion ?? '—'}</span></div>
              </div>
              <span class="snoc-mono-sm snoc-tenue">
                El teléfono y las coordenadas del cliente no se traen a esta pantalla: para programar una visita no
                hacen falta.
              </span>
            </div>

            <div class="snoc-pila-xs">
              <span class="snoc-label-sm snoc-tenue" style="text-transform:uppercase;">Orden</span>
              <div class="snoc-meta">
                <div><span>Número:</span><span class="snoc-mono-sm">#{ficha.numero ?? '—'}</span></div>
                <div><span>Revisión:</span><span class="snoc-mono-sm">{ficha.revision ?? '—'}</span></div>
                <div>
                  <span>Tipo:</span>
                  <span class="snoc-body-sm">{ficha.tipo?.nombre ?? ficha.tipo?.codigo ?? '—'}</span>
                </div>
                <div>
                  <span>Estado operativo:</span>
                  <span class="snoc-insignia">{ficha.estado_operativo ?? '—'}</span>
                </div>
                <div>
                  <span>Estado de validación:</span>
                  <span class="snoc-body-sm">{ficha.estado_validacion ?? '—'}</span>
                </div>
                <div><span>Programada para:</span><span class="snoc-mono-sm">{fecha(ficha.programada_para)}</span></div>
                <div><span>Iniciada:</span><span class="snoc-mono-sm">{fecha(ficha.iniciada_en)}</span></div>
                <div>
                  <span>Completada en campo:</span>
                  <span class="snoc-mono-sm">{fecha(ficha.completada_campo_en)}</span>
                </div>
                <div><span>Evidencias:</span><span class="snoc-mono-sm">{ficha.n_evidencias ?? '—'}</span></div>
              </div>
            </div>

            <div class="snoc-pila-xs">
              <span class="snoc-label-sm snoc-tenue" style="text-transform:uppercase;">Quién la trabaja</span>
              <div class="snoc-meta">
                <div>
                  <span>Técnico principal:</span>
                  <span class="snoc-body-sm">
                    {ficha.tecnico_principal?.nombre ?? ficha.tecnico_principal?.email ?? 'Sin asignar'}
                  </span>
                </div>
                <div><span>Integrantes:</span><span class="snoc-body-sm">{(ficha.cuadrilla ?? []).length}</span></div>
              </div>
            </div>

            {#if ficha.diagnostico_previo}
              <div class="snoc-analisis snoc-observado">
                <span class="snoc-insignia snoc-insignia-variante">Diagnóstico previo</span>
                <p class="snoc-body" style="margin:0;">{ficha.diagnostico_previo}</p>
              </div>
            {/if}
          {:else if ficha && drawer === 'persona'}
            <div class="snoc-pila-xs">
              <span class="snoc-label-sm snoc-tenue" style="text-transform:uppercase;">Capacidad del {data.dia}</span>
              <div class="snoc-meta">
                <div><span>Jornada:</span><span class="snoc-mono-sm">{dur(ficha.jornada?.minutos)}</span></div>
                <div>
                  <span>Carga conocida:</span>
                  <span class="snoc-mono-sm">{dur(ficha.carga?.minutos_conocidos)}</span>
                </div>
                <div>
                  <span>Riesgo:</span>
                  <span class="snoc-insignia {riesgoDe(ficha.riesgo).clase}">{riesgoDe(ficha.riesgo).texto}</span>
                </div>
              </div>
            </div>

            {#if (ficha.faltantes ?? []).length}
              <div class="snoc-analisis snoc-faltante">
                <span class="snoc-insignia snoc-insignia-error">Datos faltantes</span>
                <p class="snoc-body" style="margin:0;">
                  {ficha.faltantes.length} orden(es) no declaran duración. El riesgo responde
                  <strong>INDETERMINADO</strong> en vez de «sin sobrecarga»: un dato que falta no vale cero.
                </p>
              </div>
            {/if}

            <details class="snoc-detalles">
              <summary class="snoc-label-sm">Respuesta completa del backend</summary>
              <pre class="snoc-pre">{JSON.stringify(ficha, null, 2)}</pre>
            </details>
          {/if}
        </div>
      </aside>
    </div>
  {/if}

  <!-- ============ CONFIRMAR REPROGRAMACIÓN ============ -->
  {#if modalReprogramar}
    <div
      class="snoc-velo"
      role="presentation"
      onclick={(e) => {
        if (e.target === e.currentTarget && !trabajando) modalReprogramar = null;
      }}
    >
      <div class="snoc-modal" role="dialog" aria-modal="true" aria-labelledby="snoc-repro-titulo">
        <div class="snoc-fila snoc-primario">
          <span class="snoc-icono" style="font-size:28px;">edit_calendar</span>
          <h4 class="snoc-h3" id="snoc-repro-titulo">¿Reprogramar esta orden?</h4>
        </div>
        <p class="snoc-body snoc-secundario" style="margin:0;">
          Cambia la fecha y hora de la orden <strong>#{modalReprogramar.numero}</strong> dentro de su plan. Queda
          registrada como novedad operativa con la causa que declares.
        </p>
        <form method="POST" action="?/reprogramar" use:enhance={alTrabajar}>
          <input type="hidden" name="orden" value={modalReprogramar.orden} />
          <input type="hidden" name="plan" value={modalReprogramar.programacion} />
          <div class="snoc-pila-xs">
            <label class="snoc-label-sm snoc-secundario" for="r-cuando">Nueva fecha y hora</label>
            <input
              id="r-cuando"
              class="snoc-campo"
              type="datetime-local"
              name="programada_para"
              bind:value={fCuando}
              required
            />

            <label class="snoc-label-sm snoc-secundario" for="r-causa">Causa</label>
            <select id="r-causa" class="snoc-campo" name="causa" bind:value={fCausa}>
              {#each data.causas as c (c.valor)}<option value={c.valor}>{c.texto}</option>{/each}
            </select>

            <label class="snoc-label-sm snoc-secundario" for="r-motivo">Motivo (opcional)</label>
            <input id="r-motivo" class="snoc-campo" name="motivo" bind:value={fMotivo} maxlength="255" />
          </div>
          <div class="snoc-fila" style="justify-content:flex-end; padding-top:var(--snoc-md);">
            <button class="snoc-btn" type="button" onclick={() => (modalReprogramar = null)} disabled={trabajando}>
              Cancelar
            </button>
            <button class="snoc-btn snoc-btn-primario" type="submit" disabled={trabajando}>
              {trabajando ? 'Reprogramando…' : 'Confirmar reprogramación'}
            </button>
          </div>
        </form>
      </div>
    </div>
  {/if}

  <!-- ============ CONFIRMAR CAMBIO DE SECUENCIA ============ -->
  {#if modalSecuencia}
    <div
      class="snoc-velo"
      role="presentation"
      onclick={(e) => {
        if (e.target === e.currentTarget && !trabajando) modalSecuencia = null;
      }}
    >
      <div class="snoc-modal" role="dialog" aria-modal="true" aria-labelledby="snoc-sec1-titulo">
        <div class="snoc-fila snoc-primario">
          <span class="snoc-icono" style="font-size:28px;">swap_vert</span>
          <h4 class="snoc-h3" id="snoc-sec1-titulo">¿Cambiar la secuencia de esta línea?</h4>
        </div>
        <p class="snoc-body snoc-secundario" style="margin:0;">
          Cambia el orden propuesto de la orden <strong>#{modalSecuencia.numero}</strong>.
          <strong style="color:var(--snoc-on-surface);">Cambiar la secuencia no es reprogramar</strong>: no toca la
          fecha, ni el plan, ni la asignación, ni ninguna otra línea.
        </p>
        <form method="POST" action="?/secuencia" use:enhance={alTrabajar}>
          <input type="hidden" name="linea" value={modalSecuencia.id} />
          <div class="snoc-pila-xs">
            <label class="snoc-label-sm snoc-secundario" for="s-num">Secuencia (0 significa sin secuenciar)</label>
            <input
              id="s-num"
              class="snoc-campo"
              type="number"
              name="secuencia"
              min="0"
              bind:value={fSecuencia}
              required
            />

            <label class="snoc-label-sm snoc-secundario" for="s-causa">Causa</label>
            <select id="s-causa" class="snoc-campo" name="causa" bind:value={fCausa}>
              {#each data.causas as c (c.valor)}<option value={c.valor}>{c.texto}</option>{/each}
            </select>

            <label class="snoc-label-sm snoc-secundario" for="s-motivo">Motivo (opcional)</label>
            <input id="s-motivo" class="snoc-campo" name="motivo" bind:value={fMotivo} maxlength="255" />
          </div>
          <div class="snoc-fila" style="justify-content:flex-end; padding-top:var(--snoc-md);">
            <button class="snoc-btn" type="button" onclick={() => (modalSecuencia = null)} disabled={trabajando}>
              Cancelar
            </button>
            <button class="snoc-btn snoc-btn-primario" type="submit" disabled={trabajando}>
              {trabajando ? 'Guardando…' : 'Confirmar secuencia'}
            </button>
          </div>
        </form>
      </div>
    </div>
  {/if}

  <!-- ============ CONFIRMAR ANÁLISIS ============ -->
  {#if modalAnalizar}
    <div
      class="snoc-velo"
      role="presentation"
      onclick={(e) => {
        if (e.target === e.currentTarget && !trabajando) modalAnalizar = false;
      }}
    >
      <div class="snoc-modal" role="dialog" aria-modal="true" aria-labelledby="snoc-ana-titulo">
        <div class="snoc-fila snoc-primario">
          <span class="snoc-icono" style="font-size:28px;">neurology</span>
          <h4 class="snoc-h3" id="snoc-ana-titulo">¿Analizar la programación?</h4>
        </div>
        <p class="snoc-body snoc-secundario" style="margin:0;">
          El asistente lee las señales de programación y podrá registrar propuestas nuevas en la cola de revisión.
          <strong style="color:var(--snoc-on-surface);">No programa, no asigna y no ejecuta ninguna acción</strong>:
          cada recomendación la decide una persona.
        </p>
        <form method="POST" action="?/analizar" use:enhance={alTrabajar}>
          <div class="snoc-fila" style="justify-content:flex-end; padding-top:var(--snoc-xs);">
            <button class="snoc-btn" type="button" onclick={() => (modalAnalizar = false)} disabled={trabajando}>
              Cancelar
            </button>
            <button class="snoc-btn snoc-btn-primario" type="submit" disabled={trabajando}>
              {trabajando ? 'Analizando…' : 'Confirmar análisis'}
            </button>
          </div>
        </form>
      </div>
    </div>
  {/if}

  <!-- ============ PROGRAMAR UNA OT SIN PLAN ============ -->
  {#if modalProgramar}
    <div
      class="snoc-velo"
      role="presentation"
      onclick={(e) => {
        if (e.target === e.currentTarget && !trabajando) modalProgramar = null;
      }}
    >
      <div class="snoc-modal" role="dialog" aria-modal="true" aria-labelledby="snoc-prog-titulo">
        <div class="snoc-fila snoc-primario">
          <span class="snoc-icono" style="font-size:28px;">event_available</span>
          <h4 class="snoc-h3" id="snoc-prog-titulo">¿Programar esta orden?</h4>
        </div>
        <p class="snoc-body snoc-secundario" style="margin:0;">
          {modalProgramar.accion_propuesta}
        </p>

        {#if cargandoPlanes}
          <div class="snoc-cargando">
            <span class="snoc-icono snoc-girando" style="font-size:22px;">progress_activity</span>
            <span class="snoc-body snoc-secundario">Consultando planes semanales…</span>
          </div>
        {:else if errorPlanes}
          <div class="snoc-aviso">
            <span class="snoc-icono snoc-error-txt" style="font-size:18px;">error</span>
            <span class="snoc-body">{errorPlanes}</span>
          </div>
          <div class="snoc-fila" style="justify-content:flex-end;">
            <button class="snoc-btn" type="button" onclick={() => (modalProgramar = null)}>Cerrar</button>
          </div>
        {:else if planes.length === 0}
          <div class="snoc-aviso">
            <span class="snoc-icono snoc-tenue" style="font-size:18px;">info</span>
            <span class="snoc-body">No hay planes disponibles para programar esta orden.</span>
          </div>
          <span class="snoc-mono-sm snoc-tenue">
            Un plan cerrado no admite órdenes nuevas. Hace falta un plan en borrador o publicado.
          </span>
          <div class="snoc-fila" style="justify-content:flex-end;">
            <button class="snoc-btn" type="button" onclick={() => (modalProgramar = null)}>Cerrar</button>
          </div>
        {:else}
          <form method="POST" action="?/programar" use:enhance={alTrabajar}>
            <input type="hidden" name="orden" value={modalProgramar.origen_id} />
            <div class="snoc-pila-xs">
              <label class="snoc-label-sm snoc-secundario" for="p-cuando">Fecha y hora</label>
              <input
                id="p-cuando"
                class="snoc-campo"
                type="datetime-local"
                name="programada_para"
                bind:value={fCuando}
                required
              />

              <label class="snoc-label-sm snoc-secundario" for="p-plan">Plan semanal</label>
              {#if planesCompatibles.length === 0}
                <div class="snoc-aviso">
                  <span class="snoc-icono snoc-error-txt" style="font-size:18px;">warning</span>
                  <span class="snoc-body">
                    Ningún plan cubre esa fecha. Una orden tiene que caer dentro de la semana de su plan.
                  </span>
                </div>
              {:else}
                <select id="p-plan" class="snoc-campo" name="plan" bind:value={fPlan} required>
                  <option value="" disabled>Elegí un plan…</option>
                  {#each planesCompatibles as p (p.id)}
                    <option value={p.id}>
                      Semana {semana(p)} · {p.estado_display ?? p.estado}{p.admite_lineas ? ' · admite órdenes' : ''}
                    </option>
                  {/each}
                </select>
                <span class="snoc-mono-sm snoc-tenue">
                  {planesCompatibles.length} de {planes.length} plan(es) cubren esa fecha.
                </span>
              {/if}

              <label class="snoc-label-sm snoc-secundario" for="p-causa">Causa</label>
              <select id="p-causa" class="snoc-campo" name="causa" bind:value={fCausa}>
                <option value="">Sin causa (solo para planes en borrador)</option>
                {#each data.causas as c (c.valor)}<option value={c.valor}>{c.texto}</option>{/each}
              </select>
              <span class="snoc-mono-sm snoc-tenue">
                Agregar una orden a un plan <strong>ya publicado</strong> es una adición formal y el backend exige
                causa. Sobre un borrador es opcional.
              </span>

              <label class="snoc-label-sm snoc-secundario" for="p-motivo">Motivo (opcional)</label>
              <input id="p-motivo" class="snoc-campo" name="motivo" bind:value={fMotivo} maxlength="255" />
            </div>

            <div class="snoc-fila" style="justify-content:flex-end; padding-top:var(--snoc-md);">
              <button class="snoc-btn" type="button" onclick={() => (modalProgramar = null)} disabled={trabajando}>
                Cancelar
              </button>
              <button
                class="snoc-btn snoc-btn-primario"
                type="submit"
                disabled={trabajando || !fPlan || planesCompatibles.length === 0}
              >
                {trabajando ? 'Programando…' : 'Confirmar programación'}
              </button>
            </div>
          </form>
        {/if}
      </div>
    </div>
  {/if}
</div>
