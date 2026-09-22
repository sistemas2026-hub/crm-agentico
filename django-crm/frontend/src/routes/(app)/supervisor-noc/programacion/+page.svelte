<script>
  import { enhance } from '$app/forms';
  import { invalidateAll, goto } from '$app/navigation';
  import '../supervisor-noc.css';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let trabajando = $state(false);
  let modalSecuenciar = $state(false);
  let seleccionada = $state(/** @type {any} */ (null));

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
      await update({ reset: false });
      await invalidateAll();
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
          <a class="snoc-pildora" href="/supervisor-noc">Hallazgos y propuestas</a>
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
                      <th class="snoc-derecha">Plan</th>
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
                          <span class="snoc-mono-sm snoc-tenue">{l.plan_estado ?? '—'}</span>
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
                      <a class="snoc-pildora" href="/supervisor-noc">Revisar</a>
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
</div>
