<script>
  import { enhance } from '$app/forms';
  import './supervisor-noc.css';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let modalAbierto = $state(false);
  let revisando = $state(/** @type {string | null} */ (null));
  let comentario = $state('');
  let corriendo = $state(false);

  /**
   * Los tipos de senal con al menos una propuesta, para las pildoras de
   * filtro. Se derivan de lo que realmente hay -- la maqueta traia siete
   * categorias fijas con sus conteos escritos a mano, y una pildora que
   * filtra a cero es peor que no estar.
   */
  const porSenal = $derived.by(() => {
    const cuenta = new Map();
    for (const p of data.hallazgos?.resultados ?? []) {
      const clave = p.tipo_senal;
      cuenta.set(clave, { etiqueta: p.tipo_senal_display, n: (cuenta.get(clave)?.n ?? 0) + 1 });
    }
    return [...cuenta.entries()].sort((a, b) => b[1].n - a[1].n);
  });

  const PRIORIDAD = { alta: 'snoc-insignia-error-solida', media: 'snoc-insignia-secundaria' };
  const tonoPrioridad = (p) => PRIORIDAD[String(p).toLowerCase()] ?? 'snoc-insignia';

  /** El sobre del indicador dice cuanto confiar en el numero. */
  function leyendaIndicador(d) {
    if (!d) return 'Sin dato';
    if (d.estado === 'VALIDO') return 'Dato completo';
    if (d.estado === 'NO_APLICA') return 'No aplica en el período';
    const pct = d.cobertura != null ? ` (${Math.round(d.cobertura * 100)}% de cobertura)` : '';
    return `Datos insuficientes${pct}`;
  }

  const fecha = (iso) =>
    iso ? new Date(iso).toLocaleString('es-CO', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
  const fechaCorta = (iso) =>
    iso ? new Date(iso).toLocaleDateString('es-CO', { day: '2-digit', month: 'short', year: 'numeric' }) : '—';

  /**
   * La ultima pasada se DERIVA de la propuesta mas reciente: no hay columna
   * que registre cuando corrio el ciclo. Es una aproximacion y el titulo lo
   * dice, en vez de presentarla como un sello de ejecucion.
   */
  const ultimaPropuesta = $derived(
    (data.hallazgos?.resultados ?? [])
      .map((p) => p.created_at)
      .filter(Boolean)
      .sort()
      .at(-1) ?? null
  );

  /**
   * Los tres callbacks de `use:enhance`, aca y no en el marcado: una arrow que
   * devuelve otra arrow dentro de un atributo {...} se lee mal y es facil de
   * romper al editarla.
   */
  const alRevisar = () => async ({ update }) => {
    revisando = null;
    comentario = '';
    await update();
  };
  const alCorrer = () => {
    corriendo = true;
    return async ({ update }) => {
      corriendo = false;
      await update();
    };
  };
  const alCorrerCiclo = () => {
    corriendo = true;
    return async ({ update }) => {
      corriendo = false;
      modalAbierto = false;
      await update();
    };
  };

  const NAV = [
    { rotulo: 'Inicio', icono: 'home', href: '/' },
    { rotulo: 'Dashboard', icono: 'dashboard', href: '/pipeline' },
    { rotulo: 'Clientes', icono: 'group', href: '/accounts' },
    { rotulo: 'Casos / Solicitudes', icono: 'inbox', href: '/tickets' },
    { rotulo: 'Operaciones', icono: 'pulse_alert', href: '/tasks' },
    { rotulo: 'Trabajos de campo', icono: 'build', href: '/instalaciones' },
    { rotulo: 'SLA', icono: 'timelapse', href: '/goals' },
    { rotulo: 'Incidencias', icono: 'warning', href: '/conversaciones' },
    { rotulo: 'Reportes', icono: 'monitoring', href: '/consumo' }
  ];
  const NAV_FINAL = [
    { rotulo: 'Agentes', icono: 'how_to_reg', href: '/agentes' },
    { rotulo: 'Asistente', icono: 'smart_toy', href: '/asistente' },
    { rotulo: 'Configuración', icono: 'settings', href: '/settings' }
  ];
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
  <aside class="snoc-aside">
    <div style="display:flex; flex-direction:column; flex:1; overflow-y:auto;">
      <div class="snoc-marca">
        <div class="snoc-marca-icono"><span class="snoc-icono" style="font-size:20px;">hub</span></div>
        <div class="snoc-pila-xs">
          <span class="snoc-h4" style="text-transform:uppercase; color:var(--snoc-on-primary);">{data.org ?? 'Organización'}</span>
          <span class="snoc-tag" style="color:var(--snoc-surface-variant);">ISP Core Platform</span>
        </div>
      </div>
      <nav class="snoc-nav">
        {#each NAV as item}
          <a href={item.href}><span class="snoc-icono" style="font-size:18px;">{item.icono}</span><span>{item.rotulo}</span></a>
        {/each}
        <a href="/supervisor-noc" aria-current="page">
          <span class="snoc-nav-activo-izq">
            <span class="snoc-icono" style="font-size:18px;">psychology</span>
            <span>SUPERVISOR NOC IA</span>
          </span>
          <span class="snoc-latido"><span></span><span></span></span>
        </a>
        {#each NAV_FINAL as item}
          <a href={item.href}><span class="snoc-icono" style="font-size:18px;">{item.icono}</span><span>{item.rotulo}</span></a>
        {/each}
      </nav>
    </div>
    <div class="snoc-pie">
      <div class="snoc-fila" style="padding-top:var(--snoc-xs);">
        <div style="width:1.75rem; height:1.75rem; border-radius:9999px; background:var(--snoc-secondary); color:var(--snoc-on-secondary); display:flex; align-items:center; justify-content:center;">
          <span class="snoc-icono" style="font-size:14px;">admin_panel_settings</span>
        </div>
        <div class="snoc-pila-xs">
          <span class="snoc-label-sm" style="color:var(--snoc-inverse-on-surface);">{data.usuario ?? 'Sin sesión'}</span>
          <span class="snoc-mono-sm" style="color:var(--snoc-outline-variant);">{data.rol ?? '—'}</span>
        </div>
      </div>
    </div>
  </aside>

  <div class="snoc-cuerpo">
    <header class="snoc-header">
      <div class="snoc-miga snoc-label-sm">
        <span>Operaciones</span><span class="snoc-tenue">/</span>
        <span>Inteligencia Artificial</span><span class="snoc-tenue">/</span>
        <span class="snoc-label snoc-primario">Supervisor NOC IA</span>
      </div>
      <div class="snoc-fila">
        <a class="snoc-btn" href="/">Volver al CRM</a>
      </div>
    </header>

    <main class="snoc-main">
      <div class="snoc-lienzo">
        {#if !data.puedeVer}
          <!-- El 403 se explica en vez de mostrarse como una pantalla rota. -->
          <section class="snoc-panel">
            <div class="snoc-fila">
              <span class="snoc-icono snoc-error-txt" style="font-size:28px;">lock</span>
              <div class="snoc-pila-xs">
                <h1 class="snoc-h2">Supervisor NOC IA</h1>
                <p class="snoc-body snoc-secundario">
                  Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede ver y revisar las propuestas.
                  Tu rol es <strong class="snoc-mono">{data.rol ?? 'sin rol'}</strong>.
                </p>
              </div>
            </div>
          </section>
        {:else}
          <!-- ============ CABECERA ============ -->
          <header class="snoc-fila-sep" style="flex-wrap:wrap; padding-bottom:var(--snoc-sm);">
            <div class="snoc-fila">
              <div style="width:3rem; height:3rem; border-radius:var(--snoc-r-xl); background:var(--snoc-primary); color:var(--snoc-on-primary); display:flex; align-items:center; justify-content:center; box-shadow:var(--snoc-sombra);">
                <span class="snoc-icono" style="font-size:28px;">psychology</span>
              </div>
              <div class="snoc-pila-xs">
                <div class="snoc-fila">
                  <h1 class="snoc-h1">SUPERVISOR NOC IA</h1>
                  <span class="snoc-insignia snoc-insignia-neutra snoc-primario">Shadow Mode</span>
                </div>
                <p class="snoc-body snoc-secundario">Monitorea, analiza y propone acciones para una operación más eficiente.</p>
              </div>
            </div>

            <div class="snoc-fila" style="background:var(--snoc-surface-container-low); padding:var(--snoc-sm) var(--snoc-md); border-radius:var(--snoc-r-xl); box-shadow:var(--snoc-sombra);">
              <div style="width:2.25rem; height:2.25rem; border-radius:var(--snoc-r-lg); background:var(--snoc-surface-container-high); color:var(--snoc-primary); display:flex; align-items:center; justify-content:center;">
                <span class="snoc-icono" style="font-size:22px;">visibility</span>
              </div>
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
              <!-- 1. Interruptor de autonomía: del MOTOR, no de tenant_config. -->
              <div class="snoc-tarjeta">
                <div class="snoc-filo {data.autonomia.permitido === false ? 'snoc-filo-error' : data.autonomia.estado == null ? 'snoc-filo-neutro' : 'snoc-filo-primario'}"></div>
                <div class="snoc-fila-sep">
                  <span class="snoc-label-sm snoc-secundario" style="text-transform:uppercase;">Estado de autonomía</span>
                  <span class="snoc-icono" style="font-size:18px;">stop_circle</span>
                </div>
                <div style="margin:var(--snoc-xs) 0;">
                  {#if data.autonomia.estado == null}
                    <span class="snoc-insignia snoc-insignia-variante">No se pudo leer</span>
                  {:else}
                    <span class="snoc-insignia {data.autonomia.permitido ? 'snoc-insignia-secundaria-suave' : 'snoc-insignia-error'}">
                      <span class="snoc-punto {data.autonomia.permitido ? 'snoc-punto-secundario' : 'snoc-punto-error'}"></span>
                      {data.autonomia.estado}
                    </span>
                  {/if}
                </div>
                <span class="snoc-body-sm snoc-tenue">{data.autonomia.motivo || 'Interruptor del motor'}</span>
              </div>

              <!-- 2. Alcance de la etapa, medido sobre las propuestas reales. -->
              <div class="snoc-tarjeta">
                <div class="snoc-filo snoc-filo-secundario"></div>
                <div class="snoc-fila-sep">
                  <span class="snoc-label-sm snoc-secundario" style="text-transform:uppercase;">Fuera del alcance vigente</span>
                  <span class="snoc-icono" style="font-size:18px;">shield</span>
                </div>
                <div style="margin:var(--snoc-xs) 0;">
                  <span class="snoc-cifra">{(data.hallazgos?.resultados ?? []).filter((p) => p.dentro_del_alcance === false).length}</span>
                </div>
                <span class="snoc-body-sm snoc-tenue">Propuestas por encima del techo de esta etapa</span>
              </div>

              <!-- 3. El cero que sí es comprobable: 'ejecutada' no es un estado posible. -->
              <div class="snoc-tarjeta">
                <div class="snoc-filo snoc-filo-primario"></div>
                <div class="snoc-fila-sep">
                  <span class="snoc-label-sm snoc-secundario" style="text-transform:uppercase;">Acciones ejecutadas</span>
                  <span class="snoc-icono snoc-primario" style="font-size:18px;">analytics</span>
                </div>
                <div style="margin:var(--snoc-xs) 0;"><span class="snoc-cifra">0</span></div>
                <span class="snoc-body-sm snoc-tenue">No existe estado «ejecutada» en esta etapa</span>
              </div>

              <!-- 4. Última pasada + la acción. -->
              <div class="snoc-tarjeta">
                <div class="snoc-filo snoc-filo-neutro"></div>
                <div class="snoc-fila-sep">
                  <span class="snoc-label-sm snoc-secundario" style="text-transform:uppercase;">Última propuesta registrada</span>
                  <span class="snoc-icono snoc-tenue" style="font-size:18px;">update</span>
                </div>
                <div style="margin:var(--snoc-xs) 0;" title="Derivado de la propuesta más reciente: no hay registro del momento del ciclo.">
                  <span class="snoc-mono snoc-secundario">{ultimaPropuesta ? fecha(ultimaPropuesta) : 'Ninguna todavía'}</span>
                </div>
                <div class="snoc-fila-sep">
                  <span class="snoc-body-sm snoc-tenue">Ciclo listo</span>
                  <button class="snoc-btn snoc-btn-primario" type="button" onclick={() => (modalAbierto = true)}>
                    <span class="snoc-icono" style="font-size:14px;">refresh</span>
                    <span>Ejecutar ciclo</span>
                  </button>
                </div>
              </div>
            </div>

            <div class="snoc-aviso">
              <span class="snoc-icono snoc-primario" style="font-size:20px;">info</span>
              <p class="snoc-body" style="margin:0;">
                El <strong>Supervisor NOC IA</strong> se encuentra en modo observación. Analiza la operación, detecta
                situaciones y genera propuestas, <strong class="snoc-error-txt">pero no ejecuta acciones autónomas</strong>.
              </p>
              <span class="snoc-insignia" style="margin-left:auto;">Requiere autorización humana</span>
            </div>

            <div class="snoc-tarjeta" style="padding:var(--snoc-sm);">
              <div class="snoc-fila-sep" style="flex-wrap:wrap;">
                <div class="snoc-fila" style="gap:var(--snoc-xs);">
                  <span class="snoc-icono snoc-primario" style="font-size:16px;">security</span>
                  <span class="snoc-label-sm snoc-secundario" style="text-transform:uppercase;">Controles de seguridad:</span>
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
              <div class="snoc-fila" style="gap:var(--snoc-xs);">
                <span class="snoc-mono-sm snoc-tenue">Derivado en la consulta · no hay KPI guardado</span>
              </div>
            </div>

            {#if data.errorIndicadores}
              <div class="snoc-aviso">
                <span class="snoc-icono snoc-error-txt" style="font-size:20px;">error</span>
                <p class="snoc-body" style="margin:0;">
                  {data.errorIndicadores === 'SIN_PERMISO'
                    ? 'Tu rol no alcanza para ver los indicadores operativos.'
                    : 'No se pudieron leer los indicadores operativos.'}
                </p>
              </div>
            {:else}
              <div class="snoc-rejilla snoc-rejilla-2 snoc-rejilla-5">
                {#each data.resumen as k}
                  <div class="snoc-tarjeta">
                    <div class="snoc-fila-sep">
                      <span class="snoc-label-sm snoc-secundario" style="text-transform:uppercase;">{k.titulo}</span>
                      <span class="snoc-insignia {k.tono === 'error' ? 'snoc-insignia-error' : k.tono === 'variante' ? 'snoc-insignia-variante' : k.tono === 'secundario' ? 'snoc-insignia-secundaria-suave' : ''}">{k.etiqueta}</span>
                    </div>
                    <div style="margin:var(--snoc-sm) 0; display:flex; align-items:baseline; justify-content:space-between; gap:var(--snoc-sm);">
                      <span class="snoc-cifra">{k.dato.valor ?? '—'}</span>
                      <span class="snoc-mono-sm {k.dato.estado === 'VALIDO' ? 'snoc-tenue' : 'snoc-error-txt'}">
                        {k.dato.estado === 'VALIDO' ? 'completo' : k.dato.estado === 'NO_APLICA' ? 'no aplica' : 'parcial'}
                      </span>
                    </div>
                    <span class="snoc-body-sm snoc-tenue" title={k.dato.motivo || ''}>{leyendaIndicador(k.dato)}</span>
                  </div>
                {/each}
              </div>
            {/if}
          </section>

          <!-- ============ TALLER ============ -->
          <div class="snoc-taller">
            <div class="snoc-col-8">
              <!-- --- HALLAZGOS --- -->
              <section class="snoc-panel">
                <div class="snoc-fila-sep" style="flex-wrap:wrap;">
                  <div class="snoc-fila" style="gap:var(--snoc-xs);">
                    <h3 class="snoc-h3">Hallazgos del Supervisor</h3>
                    <span class="snoc-insignia snoc-insignia-neutra">{data.hallazgos.count} registrados</span>
                  </div>
                  <span class="snoc-mono-sm snoc-tenue">Cada fila es una propuesta con su evidencia</span>
                </div>

                <div class="snoc-envuelve" style="padding-bottom:var(--snoc-xs);">
                  <a class="snoc-pildora {data.filtroSenal ? '' : 'snoc-pildora-activa'}" href="/supervisor-noc">
                    Todos ({data.hallazgos.count})
                  </a>
                  {#each porSenal as [clave, info]}
                    <a class="snoc-pildora {data.filtroSenal === clave ? 'snoc-pildora-activa' : ''}" href="/supervisor-noc?senal={clave}">
                      {info.etiqueta} ({info.n})
                    </a>
                  {/each}
                </div>

                {#if data.hallazgos.error}
                  <p class="snoc-body snoc-error-txt">
                    {data.hallazgos.error === 'SIN_PERMISO' ? 'Sin permiso para listar propuestas.' : 'No se pudieron leer las propuestas.'}
                  </p>
                {:else if data.hallazgos.resultados.length === 0}
                  <p class="snoc-body snoc-secundario">
                    No hay hallazgos registrados{data.filtroSenal ? ' para esta señal' : ''}. Corré un ciclo de análisis para
                    que el Supervisor revise la operación.
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
                        {#each data.hallazgos.resultados as p}
                          <tr class={data.seleccionada === p.id ? 'snoc-fila-activa' : ''}>
                            <td><span class="snoc-insignia {tonoPrioridad(p.prioridad)}">{p.prioridad}</span></td>
                            <td class="snoc-label">{p.tipo_senal_display}</td>
                            <td>
                              <span class="snoc-id">{p.origen_tipo}</span>
                              <div class="snoc-mono-sm snoc-tenue">{String(p.origen_id).slice(0, 12)}</div>
                            </td>
                            <td class="snoc-body-sm snoc-recorte" title={p.accion_propuesta}>{p.accion_propuesta}</td>
                            <td><span class="snoc-insignia">{p.estado}</span></td>
                            <td>
                              <span class="snoc-mono-sm">{p.nivel_autonomia_requerido}</span>
                              {#if p.dentro_del_alcance === false}
                                <span class="snoc-insignia snoc-insignia-error" title="Por encima del techo de la etapa">fuera</span>
                              {/if}
                            </td>
                            <td class="snoc-mono-sm snoc-tenue">{fechaCorta(p.expira_en)}</td>
                            <td class="snoc-derecha">
                              <a class="snoc-pildora {data.seleccionada === p.id ? 'snoc-pildora-activa' : ''}" href="/supervisor-noc?propuesta={p.id}{data.filtroSenal ? `&senal=${data.filtroSenal}` : ''}">
                                {data.seleccionada === p.id ? 'Seleccionado' : 'Ver detalle'}
                              </a>
                            </td>
                          </tr>
                        {/each}
                      </tbody>
                    </table>
                  </div>
                {/if}
              </section>

              <!-- --- DETALLE --- -->
              <section class="snoc-panel">
                {#if !data.seleccionada}
                  <div class="snoc-fila">
                    <span class="snoc-icono snoc-tenue" style="font-size:18px;">frame_inspect</span>
                    <p class="snoc-body snoc-secundario" style="margin:0;">
                      Elegí un hallazgo de la tabla para inspeccionar su evidencia, su análisis y su historial de auditoría.
                    </p>
                  </div>
                {:else if data.errorDetalle}
                  <p class="snoc-body snoc-error-txt">
                    {data.errorDetalle === 'NO_ENCONTRADA' ? 'Esa propuesta no existe o no es de tu organización.' : 'No se pudo leer el detalle.'}
                  </p>
                {:else if data.detalle}
                  {@const d = data.detalle}
                  <div class="snoc-fila-sep" style="flex-wrap:wrap; padding-bottom:var(--snoc-xs);">
                    <div class="snoc-fila">
                      <div style="width:2rem; height:2rem; border-radius:var(--snoc-r-lg); background:var(--snoc-error-container); color:var(--snoc-on-error-container); display:flex; align-items:center; justify-content:center;">
                        <span class="snoc-icono" style="font-size:18px;">emergency</span>
                      </div>
                      <div>
                        <h4 class="snoc-h4">Detalle del Hallazgo: {d.tipo_senal_display}</h4>
                        <span class="snoc-mono-sm snoc-secundario">{d.origen_tipo} · {d.origen_id}</span>
                      </div>
                    </div>
                    <span class="snoc-insignia">Modo inspección</span>
                  </div>

                  <div class="snoc-meta">
                    <div><span>Acción propuesta:</span><span class="snoc-body-sm" style="font-weight:600;">{d.accion_propuesta}</span></div>
                    <div><span>Prioridad:</span><span class="snoc-body-sm snoc-error-txt" style="font-weight:600;">{d.prioridad}</span></div>
                    <div><span>Estado:</span><span class="snoc-insignia">{d.estado}</span></div>
                    <div><span>Nivel requerido:</span><span class="snoc-mono">{d.nivel_autonomia_requerido} {d.dentro_del_alcance === false ? '· fuera de alcance' : ''}</span></div>
                    <div><span>Impacto:</span><span class="snoc-body-sm">{d.impacto ?? '—'}</span></div>
                    <div><span>Creada:</span><span class="snoc-mono">{fecha(d.created_at)}</span></div>
                    <div><span>Expira:</span><span class="snoc-mono">{fecha(d.expira_en)}</span></div>
                    <div><span>Revisada por:</span><span class="snoc-body-sm">{d.revisado_por_email ?? '—'}</span></div>
                    <div><span>Responsable sugerido:</span><span class="snoc-body-sm">{d.responsable_sugerido_email ?? '—'}</span></div>
                  </div>

                  <div class="snoc-pila" style="padding-top:var(--snoc-xs);">
                    <div class="snoc-fila" style="gap:var(--snoc-xs);">
                      <span class="snoc-icono snoc-primario" style="font-size:18px;">model_training</span>
                      <h5 class="snoc-label" style="text-transform:uppercase; letter-spacing:0.08em; margin:0;">Análisis del Supervisor</h5>
                    </div>

                    <!-- OBSERVADO: la evidencia, con su fuente. -->
                    <div class="snoc-analisis snoc-observado">
                      <div class="snoc-fila" style="gap:var(--snoc-xs);">
                        <span class="snoc-insignia snoc-insignia-variante">Observado</span>
                        <span class="snoc-mono-sm snoc-secundario">Evidencia registrada con la propuesta</span>
                      </div>
                      {#if Array.isArray(d.evidencia) && d.evidencia.length}
                        <ul style="margin:0; padding-left:1.1rem;">
                          {#each d.evidencia as e}
                            <li class="snoc-body">
                              <span class="snoc-mono-sm snoc-tenue">{e.fuente ?? 'sin fuente'}</span> — {e.dato ?? JSON.stringify(e)}
                            </li>
                          {/each}
                        </ul>
                      {:else}
                        <p class="snoc-body snoc-secundario" style="margin:0;">Sin observaciones registradas.</p>
                      {/if}
                    </div>

                    <!-- INFERIDO: el motivo. Nunca se presenta como hecho. -->
                    <div class="snoc-analisis snoc-inferido">
                      <div class="snoc-fila" style="gap:var(--snoc-xs);">
                        <span class="snoc-insignia" style="background:var(--snoc-primary); color:var(--snoc-on-primary);">Inferido</span>
                        <span class="snoc-mono-sm snoc-secundario">Regla de análisis, calculada en código</span>
                      </div>
                      <p class="snoc-body" style="margin:0;">{d.motivo || 'Sin motivo registrado.'}</p>
                    </div>

                    <!-- DATOS FALTANTES: solo si la señal misma lo declara. -->
                    {#if d.tipo_senal === 'dato_incompleto'}
                      <div class="snoc-analisis snoc-faltante">
                        <div class="snoc-fila" style="gap:var(--snoc-xs);">
                          <span class="snoc-insignia snoc-insignia-error">Datos faltantes</span>
                          <span class="snoc-mono-sm snoc-error-txt">Brecha de información operacional</span>
                        </div>
                        <p class="snoc-body" style="margin:0;">
                          Esta señal nombra objetos concretos a los que les falta un campo concreto. No es un comodín:
                          se emite solo cuando el dato ausente se puede nombrar.
                        </p>
                      </div>
                    {/if}

                    <div class="snoc-fila" style="gap:var(--snoc-xs); padding:var(--snoc-xs) 0;">
                      <span class="snoc-icono snoc-primario" style="font-size:15px;">balance</span>
                      <span class="snoc-mono-sm snoc-secundario">
                        <strong>Nota de integridad:</strong> nunca se presenta una inferencia como hecho consumado.
                      </span>
                    </div>
                  </div>

                  {#if Array.isArray(d.historial) && d.historial.length}
                    <div class="snoc-pila-xs">
                      <span class="snoc-label-sm snoc-tenue" style="text-transform:uppercase;">Historial de auditoría</span>
                      {#each d.historial as h}
                        <div class="snoc-fila-sep" style="background:var(--snoc-surface-container-low); padding:var(--snoc-xs) var(--snoc-sm); border-radius:var(--snoc-r-lg);">
                          <span class="snoc-body-sm"><strong>{h.accion}</strong> · {h.descripcion}</span>
                          <span class="snoc-mono-sm snoc-tenue">{h.quien} · {fecha(h.cuando)}</span>
                        </div>
                      {/each}
                    </div>
                  {/if}
                {/if}
              </section>

              <!-- --- PROPUESTAS PENDIENTES --- -->
              <section class="snoc-panel">
                <div class="snoc-pila-xs">
                  <div class="snoc-fila-sep">
                    <div class="snoc-fila" style="gap:var(--snoc-xs);">
                      <span class="snoc-icono snoc-primario" style="font-size:22px;">assignment_turned_in</span>
                      <h3 class="snoc-h3">Propuestas generadas por el Supervisor NOC IA</h3>
                    </div>
                    <span class="snoc-insignia snoc-insignia-neutra">{data.pendientes.count} pendientes</span>
                  </div>
                  <div class="snoc-fila" style="gap:var(--snoc-xs); background:var(--snoc-surface-container-low); padding:var(--snoc-xs) var(--snoc-sm); border-radius:var(--snoc-r-lg);">
                    <span class="snoc-icono snoc-tenue" style="font-size:16px;">verified</span>
                    <span class="snoc-body-sm snoc-secundario">
                      Una propuesta <strong>NO</strong> significa que la acción se haya ejecutado. Aceptar registra que estás
                      de acuerdo, nada más: no hay camino de ejecución en esta etapa.
                    </span>
                  </div>
                </div>

                {#if form?.error}
                  <div class="snoc-aviso"><span class="snoc-icono snoc-error-txt" style="font-size:18px;">error</span><span class="snoc-body">{form.error}</span></div>
                {:else if form?.ok && form.tipo === 'revision'}
                  <div class="snoc-aviso"><span class="snoc-icono snoc-primario" style="font-size:18px;">check_circle</span><span class="snoc-body">Revisión registrada: <strong>{form.decision}</strong>. No se ejecutó ninguna acción.</span></div>
                {/if}

                {#if data.pendientes.resultados.length === 0}
                  <p class="snoc-body snoc-secundario">No hay propuestas esperando revisión.</p>
                {:else}
                  <div class="snoc-tabla-caja">
                    <table class="snoc-tabla">
                      <thead>
                        <tr><th>Origen</th><th>Tipo</th><th>Descripción</th><th>Prioridad</th><th>Creada</th><th class="snoc-derecha">Decisión</th></tr>
                      </thead>
                      <tbody>
                        {#each data.pendientes.resultados as p}
                          <tr>
                            <td><span class="snoc-id">{p.origen_tipo}</span></td>
                            <td class="snoc-label">{p.tipo_senal_display}</td>
                            <td class="snoc-body-sm" style="max-width:260px;">{p.accion_propuesta}</td>
                            <td><span class="snoc-insignia {tonoPrioridad(p.prioridad)}">{p.prioridad}</span></td>
                            <td class="snoc-mono-sm snoc-secundario">{fechaCorta(p.created_at)}</td>
                            <td class="snoc-derecha">
                              {#if revisando === p.id}
                                <form method="POST" action="?/revisar" use:enhance={alRevisar}>
                                  <input type="hidden" name="id" value={p.id} />
                                  <div class="snoc-pila-xs" style="align-items:flex-end;">
                                    <input
                                      class="snoc-body-sm"
                                      style="width:100%; padding:4px var(--snoc-sm); border:1px solid var(--snoc-outline-variant); border-radius:var(--snoc-r-lg);"
                                      name="comentario"
                                      bind:value={comentario}
                                      placeholder="Motivo (obligatorio si rechazás o modificás)"
                                    />
                                    <div class="snoc-envuelve" style="justify-content:flex-end;">
                                      <button class="snoc-btn snoc-btn-primario" name="decision" value="aceptada" type="submit">Aceptar</button>
                                      <button class="snoc-btn snoc-btn-error" name="decision" value="rechazada" type="submit">Rechazar</button>
                                      <button class="snoc-btn" type="button" onclick={() => (revisando = null)}>Cancelar</button>
                                    </div>
                                  </div>
                                </form>
                              {:else}
                                <div class="snoc-envuelve" style="justify-content:flex-end;">
                                  <a class="snoc-pildora" href="/supervisor-noc?propuesta={p.id}">Ver contexto</a>
                                  <button class="snoc-btn snoc-btn-primario" type="button" onclick={() => { revisando = p.id; comentario = ''; }}>Revisar propuesta</button>
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
              <!--
                En la maqueta este panel era un chat con el Supervisor. No se
                cableó como chat porque no existe ese endpoint: el módulo de
                operaciones expone los DOS asistentes de dominio, que leen sus
                señales y escriben propuestas en la misma cola. Se conserva el
                lugar y la forma del panel; lo que cambia es que cada botón
                hace algo real en vez de simularlo.
              -->
              <div class="snoc-panel" style="gap:var(--snoc-sm);">
                <div class="snoc-fila-sep">
                  <div class="snoc-fila">
                    <div style="width:2rem; height:2rem; border-radius:var(--snoc-r-lg); background:var(--snoc-primary); color:var(--snoc-on-primary); display:flex; align-items:center; justify-content:center;">
                      <span class="snoc-icono" style="font-size:18px;">smart_toy</span>
                    </div>
                    <div class="snoc-pila-xs">
                      <h3 class="snoc-h4">Asistentes operativos</h3>
                      <span class="snoc-body-sm snoc-secundario">Analizan su dominio y proponen</span>
                    </div>
                  </div>
                  <span class="snoc-latido"><span></span><span></span></span>
                </div>

                <div class="snoc-fila-sep snoc-mono-sm" style="padding-top:var(--snoc-xs);">
                  <span class="snoc-primario"><span class="snoc-punto snoc-punto-primario"></span> En línea · Modo observación</span>
                  <span class="snoc-tenue">{data.org ?? ''}</span>
                </div>

                <div class="snoc-pila-xs">
                  {#each [{ id: 'programacion', rotulo: 'Programación', desc: 'Órdenes sin programar, planes sin publicar, riesgo de plazo' }, { id: 'compromiso', rotulo: 'Compromisos', desc: 'Compromisos por vencer y dependencias pendientes' }] as a}
                    <form method="POST" action="?/asistente" use:enhance={alCorrer}>
                      <input type="hidden" name="dominio" value={a.id} />
                      <div style="background:var(--snoc-surface-container-low); padding:var(--snoc-sm); border-radius:var(--snoc-r-lg);">
                        <div class="snoc-fila-sep">
                          <span class="snoc-label">{a.rotulo}</span>
                          <button class="snoc-btn snoc-btn-primario" type="submit" disabled={corriendo}>
                            <span class="snoc-icono" style="font-size:14px;">play_arrow</span> Analizar
                          </button>
                        </div>
                        <p class="snoc-body-sm snoc-secundario" style="margin:var(--snoc-xs) 0 0;">{a.desc}</p>
                      </div>
                    </form>
                  {/each}
                </div>

                {#if form?.ok && form.tipo === 'asistente'}
                  <div class="snoc-pila-xs" style="background:var(--snoc-surface-container); padding:var(--snoc-sm); border-radius:var(--snoc-r-lg); max-height:22rem; overflow-y:auto;">
                    <span class="snoc-label-sm" style="text-transform:uppercase;">Resultado · {form.dominio}</span>
                    {#each form.asistente?.recomendaciones ?? [] as r}
                      <div class="snoc-pila-xs" style="background:var(--snoc-surface-container-lowest); padding:var(--snoc-xs) var(--snoc-sm); border-radius:var(--snoc-r-lg);">
                        <span class="snoc-body-sm">{r.recomendacion ?? r.accion_propuesta ?? r.tipo_senal}</span>
                        <span class="snoc-mono-sm snoc-tenue">{r.resultado ?? ''}</span>
                      </div>
                    {:else}
                      <span class="snoc-body-sm snoc-secundario">El asistente no encontró señales de su dominio.</span>
                    {/each}
                  </div>
                {:else if form?.ok && form.tipo === 'ciclo'}
                  <div class="snoc-pila-xs" style="background:var(--snoc-surface-container); padding:var(--snoc-sm); border-radius:var(--snoc-r-lg);">
                    <span class="snoc-label-sm" style="text-transform:uppercase;">Último ciclo</span>
                    <span class="snoc-mono-sm">
                      {form.resumen?.senales ?? 0} señales · {form.resumen?.propuestas ?? 0} propuestas nuevas ·
                      {form.resumen?.repetidas ?? 0} repetidas · {form.resumen?.expiradas ?? 0} expiradas
                    </span>
                    <span class="snoc-mono-sm snoc-tenue">Acciones ejecutadas: 0</span>
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
    </main>
  </div>

  <!-- ============ MODAL DEL CICLO ============ -->
  {#if modalAbierto}
    <div class="snoc-velo" role="presentation" onclick={(e) => { if (e.target === e.currentTarget) modalAbierto = false; }}>
      <div class="snoc-modal" role="dialog" aria-modal="true" aria-labelledby="snoc-modal-titulo">
        <div class="snoc-fila snoc-primario">
          <span class="snoc-icono" style="font-size:28px;">lock_clock</span>
          <h4 class="snoc-h3" id="snoc-modal-titulo">Confirmar ciclo de análisis</h4>
        </div>
        <p class="snoc-body snoc-secundario" style="margin:0;">
          El ciclo lee la operación y registra propuestas. <strong style="color:var(--snoc-on-surface);">No altera ninguna
          orden, no programa, no asigna y no llama a ningún sistema externo</strong>.
        </p>
        <div class="snoc-mono-sm" style="background:var(--snoc-surface-container-low); padding:var(--snoc-sm); border-radius:var(--snoc-r-lg);">
          <div>• Lo único que escribe: propuestas y su auditoría</div>
          <div>• Un ciclo a la vez por organización</div>
          <div>• Todo o nada: si falla a la mitad, no quedan propuestas parciales</div>
        </div>
        <form method="POST" action="?/ciclo" use:enhance={alCorrerCiclo}>
          <div class="snoc-fila" style="justify-content:flex-end; padding-top:var(--snoc-xs);">
            <button class="snoc-btn" type="button" onclick={() => (modalAbierto = false)}>Cancelar</button>
            <button class="snoc-btn snoc-btn-primario" type="submit" disabled={corriendo}>
              {corriendo ? 'Analizando…' : 'Iniciar lectura'}
            </button>
          </div>
        </form>
      </div>
    </div>
  {/if}
</div>
