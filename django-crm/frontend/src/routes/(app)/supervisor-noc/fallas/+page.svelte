<script>
  /**
   * Fallas de red (30/10/2026, PRD §8.17, Ola 2).
   *
   * Las caídas de PON vivas y, para cada una, avisarle a sus clientes por
   * WhatsApp antes de que escriban. Dos pasos: «Preparar el aviso» muestra a
   * cuántos y quiénes quedan afuera; «Avisar a N clientes» manda, por lotes.
   * La lista la arma el motor: solo los equipos que se cayeron JUNTOS, de
   * clientes activos. Un corte de energía no se avisa.
   *
   * REDISEÑO DEL 21/11/2026 (maqueta aprobada):
   *   - Resumen arriba: activas, equipos afectados, avisos en curso, restablecidas.
   *   - Cada caída dice su estado, su tipo (LOS, LOS parcial, energía) y su
   *     riesgo, que el backend ya mandaba y no se usaban: antes todas tenían el
   *     mismo punto rojo.
   *   - Avisar pide confirmar con el resumen: un WhatsApp a N clientes no se
   *     retira, y era un solo clic.
   *   - Lo preparado de cada caída se recuerda: antes preparar una segunda
   *     borraba la primera.
   *   - Se refresca sola cada 20 s, no solo con un envío en curso: una caída
   *     nueva aparecía recién al recargar.
   */
  import { enhance } from '$app/forms';
  import { invalidateAll } from '$app/navigation';
  import '../supervisor-noc.css';
  import Confirmar from '$lib/supervisor/ui/Confirmar.svelte';
  import PanelLateral from '$lib/supervisor/ui/PanelLateral.svelte';
  import { avisar } from '$lib/supervisor/ui/avisos.svelte.js';
  import {
    avance,
    duracion,
    estadoDeLaCaida,
    motivosLegibles,
    NO_LISTO,
    POR_QUE_NO,
    resumenDeFallas,
    textoDeDetencion,
    TIPO_ALERTA
  } from '$lib/supervisor/fallas.js';

  let { data, form } = $props();

  const REFRESCO_MS = 20_000;

  const fallas = $derived(/** @type {any[]} */ (data.fallas ?? []));
  const resumen = $derived(resumenDeFallas(fallas));

  /** @type {'todas' | 'activa' | 'avisando' | 'resuelta'} */
  let filtro = $state('todas');
  /** @type {'equipos' | 'reciente'} */
  let orden = $state('equipos');

  const visibles = $derived(
    fallas
      .filter((f) => filtro === 'todas' || estadoDeLaCaida(f).grupo === filtro)
      .toSorted((a, b) =>
        orden === 'equipos'
          ? (Number(b.equipos) || 0) - (Number(a.equipos) || 0)
          : Date.parse(b.detectada_en ?? '') - Date.parse(a.detectada_en ?? '')
      )
  );
  const cuantas = $derived({
    todas: fallas.length,
    activa: fallas.filter((f) => estadoDeLaCaida(f).grupo === 'activa').length,
    avisando: resumen.avisando,
    resuelta: resumen.resueltas
  });

  /** Lo preparado de CADA caída, para que preparar otra no lo borre. */
  let preparadas = $state(/** @type {Record<string, any>} */ ({}));
  $effect(() => {
    if (form?.situacion && form?.preparada) preparadas[form.situacion] = form.preparada;
  });

  /** La que se está mandando, para no dejar apretar dos veces. */
  let enviando = $state(/** @type {string | null} */ (null));
  /** La que espera confirmación para avisar. */
  let porConfirmar = $state(/** @type {any | null} */ (null));

  /** @param {string} id @param {'preparar' | 'aprobar' | 'detener'} que */
  const alEnviar = (id, que) => {
    enviando = id;
    return async (/** @type {any} */ { result, update }) => {
      await update({ reset: false });
      enviando = null;
      if (que === 'aprobar' && result?.type === 'success') {
        delete preparadas[id];
        avisar('Aviso aprobado. Sale por WhatsApp en la próxima tanda.');
      }
      if (que === 'detener' && result?.type === 'success') {
        avisar('Envío detenido. No sale ninguna tanda más.');
      }
    };
  };

  /* -------------------------------------------------------------------------
     22/11/2026: DETENER EL ENVÍO, A QUIÉN LE LLEGA Y LOS TICKETS. Los tres
     estaban en la maqueta aprobada y esperaban al backend
     (operaciones/aviso_de_caida.py: detener, destinatarios, casos_de).
     ------------------------------------------------------------------------- */

  /** La caída cuyo envío se quiere detener. */
  let porDetener = $state(/** @type {any | null} */ (null));
  let motivoDetener = $state('');
  /** @param {string} id */
  function enviarDetencion(id) {
    porDetener = null;
    /** @type {HTMLFormElement | null} */ (document.getElementById(`detener-${id}`))?.requestSubmit();
  }

  /** La caída cuya lista de destinatarios está abierta, y lo que llegó. */
  let verDestinatarios = $state(/** @type {any | null} */ (null));
  let destinatarios = $state(/** @type {any | null} */ (null));
  let errorDestinatarios = $state('');
  let buscarDestinatario = $state('');
  /** @param {any} f */
  async function abrirDestinatarios(f) {
    verDestinatarios = f;
    destinatarios = null;
    errorDestinatarios = '';
    buscarDestinatario = '';
    try {
      const r = await fetch(`/supervisor-noc/fallas/${f.id}/destinatarios`, { headers: { accept: 'application/json' } });
      const d = await r.json().catch(() => ({}));
      if (verDestinatarios?.id !== f.id) return;
      if (!r.ok) throw new Error(d?.error || 'No se pudo leer la lista.');
      destinatarios = d;
    } catch (/** @type {any} */ e) {
      if (verDestinatarios?.id === f.id) errorDestinatarios = e?.message || 'No se pudo leer la lista.';
    }
  }
  const listaFiltrada = $derived.by(() => {
    const todos = /** @type {any[]} */ (destinatarios?.destinatarios ?? []);
    const q = buscarDestinatario.trim().toLowerCase();
    return q ? todos.filter((d) => d.servicio.includes(q) || String(d.cliente).toLowerCase().includes(q)) : todos;
  });
  const cuentaDestinatarios = $derived.by(() => {
    const todos = /** @type {any[]} */ (destinatarios?.destinatarios ?? []);
    const pendientes = todos.filter((d) => d.pendiente).length;
    return { pendientes, salieron: todos.length - pendientes };
  });

  let leidoEn = $state(Date.now());
  let ahora = $state(Date.now());
  async function actualizar() {
    await invalidateAll();
    leidoEn = Date.now();
  }
  $effect(() => {
    const t = setInterval(() => {
      ahora = Date.now();
      if (document.visibilityState === 'visible') actualizar();
    }, REFRESCO_MS);
    return () => clearInterval(t);
  });
  const haceCuanto = $derived(Math.max(0, Math.round((ahora - leidoEn) / 1000)));

  const ESTADO_AVISO = { en_curso: 'Enviando', terminado: 'Terminado', detenido: 'Detenido' };

  /** En el reloj de la empresa (la zona viene del servidor). @param {string | null} iso */
  const fecha = (iso) =>
    iso
      ? new Date(iso).toLocaleString('es-CO', {
          day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit',
          timeZone: data.zona || 'UTC'
        })
      : '';

  /** @param {string} id */
  function enviarAprobacion(id) {
    porConfirmar = null;
    /** @type {HTMLFormElement | null} */ (document.getElementById(`aprobar-${id}`))?.requestSubmit();
  }
</script>

<svelte:head>
  <title>Fallas de red · Supervisor NOC</title>
</svelte:head>

<div class="snoc">
  <div class="v2-scroll">
    <div class="snoc-lienzo">
      <header class="snoc-encabezado">
        <div class="snoc-encabezado-texto">
          <h1 class="snoc-h1">Fallas de red</h1>
          <p class="snoc-bajada">
            Caídas de un puerto PON. Avisarles a sus clientes antes de que escriban evita que todos
            pregunten a la vez: <strong>lo aprueba una persona</strong> y sale por WhatsApp, por tandas.
          </p>
        </div>
        {#if data.puedeVer}
          <div class="snoc-encabezado-acciones">
            <span class="snoc-body-sm snoc-secundario" aria-live="polite">
              Actualizado hace {haceCuanto} s · se refresca solo cada 20 s
            </span>
            <button type="button" class="snoc-btn" onclick={actualizar}>Actualizar ahora</button>
          </div>
        {/if}
      </header>

      {#if form?.error && !form?.situacion}
        <p class="snoc-recuadro snoc-recuadro-error" role="alert">{form.error}</p>
      {/if}

      {#if !data.puedeVer}
        <p class="snoc-recuadro">
          Solo el Jefe de Operaciones (o un ADMIN/SUPERVISOR) puede ver las fallas de red y avisar a
          los clientes.
        </p>
      {:else if data.error}
        <p class="snoc-recuadro snoc-recuadro-error">{data.error}</p>
      {:else}
        <div class="snoc-indicadores">
          <div class="snoc-indicador {resumen.activas ? 'snoc-indicador-critico' : 'snoc-indicador-ok'}">
            <span class="snoc-indicador-valor">{resumen.activas}</span>
            <span class="snoc-indicador-rotulo">{resumen.activas === 1 ? 'Caída activa' : 'Caídas activas'}</span>
          </div>
          <div class="snoc-indicador">
            <span class="snoc-indicador-valor">{resumen.equipos}</span>
            <span class="snoc-indicador-rotulo">Equipos afectados según SmartOLT</span>
          </div>
          <div class="snoc-indicador {resumen.avisando ? 'snoc-indicador-accion' : ''}">
            <span class="snoc-indicador-valor">{resumen.avisando}</span>
            <span class="snoc-indicador-rotulo">
              {resumen.avisando ? `Aviso enviándose · ${resumen.avisados} de ${resumen.aprobados}` : 'Avisos enviándose'}
            </span>
          </div>
          <div class="snoc-indicador {resumen.resueltas ? 'snoc-indicador-ok' : ''}">
            <span class="snoc-indicador-valor">{resumen.resueltas}</span>
            <span class="snoc-indicador-rotulo">Restablecidas en las últimas 24 h</span>
          </div>
        </div>

        {#if !fallas.length}
          <p class="snoc-recuadro">
            <strong>No hay caídas de PON activas.</strong> La pantalla se refresca sola: una caída
            nueva aparece acá sin recargar.
          </p>
        {:else}
          <div class="snoc-fila-sep" style="flex-wrap:wrap;">
            <div class="snoc-segmentado" role="group" aria-label="Qué caídas ver">
              {#each [['todas', 'Todas'], ['activa', 'Activas'], ['avisando', 'Avisando'], ['resuelta', 'Restablecidas 24 h']] as [clave, texto] (clave)}
                <button
                  type="button"
                  aria-pressed={filtro === clave}
                  onclick={() => (filtro = /** @type {any} */ (clave))}
                >
                  {texto} <span class="snoc-cuenta">{cuantas[/** @type {keyof typeof cuantas} */ (clave)]}</span>
                </button>
              {/each}
            </div>
            <label class="snoc-fila snoc-body-sm">
              <span class="snoc-secundario">Ordenar</span>
              <select class="snoc-select" bind:value={orden}>
                <option value="equipos">Más equipos primero</option>
                <option value="reciente">Más reciente primero</option>
              </select>
            </label>
          </div>

          {#if !visibles.length}
            <p class="snoc-recuadro">Ninguna caída en esta vista.</p>
          {/if}

          {#each visibles as f (f.id)}
            {@const est = estadoDeLaCaida(f)}
            {@const mia = form?.situacion === f.id}
            {@const previa = preparadas[f.id] ?? null}
            <article class="snoc-panel fl-caida" aria-labelledby="falla-{f.id}">
              <div class="snoc-tarjeta-cabeza">
                <div class="snoc-fila" style="flex-wrap:wrap;">
                  <span class="snoc-insignia {est.tono === 'critico' ? 'snoc-insignia-error' : est.tono === 'alerta' ? 'snoc-insignia-alerta' : est.tono === 'ok' ? 'snoc-insignia-ok' : 'snoc-insignia-secundaria-suave'}">
                    {est.texto}
                  </span>
                  {#if f.aviso && f.aviso.estado !== 'en_curso'}
                    <span class="snoc-insignia">Aviso: {ESTADO_AVISO[/** @type {keyof typeof ESTADO_AVISO} */ (f.aviso.estado)] ?? f.aviso.estado}</span>
                  {/if}
                  <h2 class="snoc-h3" id="falla-{f.id}">{f.codigo} · {f.titulo}</h2>
                </div>
                <div class="snoc-fila">
                  {#if f.tipo_alerta}<span class="snoc-tag">{TIPO_ALERTA[f.tipo_alerta] ?? f.tipo_alerta}</span>{/if}
                  {#if f.riesgo}<span class="snoc-tag">Riesgo {f.riesgo}</span>{/if}
                </div>
              </div>

              <dl class="snoc-datos">
                <div><dt>Puerto</dt><dd class="snoc-mono">{f.puerto || '—'}</dd></div>
                {#if f.caja}<div><dt>Caja</dt><dd class="snoc-mono">{f.caja}</dd></div>{/if}
                <div><dt>Equipos</dt><dd>{f.equipos ?? '—'}</dd></div>
                <div>
                  <dt>Detectada</dt>
                  <dd>
                    {fecha(f.detectada_en)}
                    {#if est.grupo !== 'resuelta'}<span class="snoc-secundario" style="font-weight:400;"> · hace {duracion(f.detectada_en, ahora)}</span>{/if}
                  </dd>
                </div>
              </dl>

              {#if f.aviso}
                {@const pct = avance(f.aviso)}
                <div class="snoc-pila-xs">
                  <div class="snoc-fila-sep snoc-body-sm">
                    <span>
                      <strong>{f.aviso.enviados}</strong> avisados de {f.aviso.clientes} aprobados
                      {#if f.aviso.descartados}· {f.aviso.descartados} ya habían vuelto{/if}
                      {#if f.aviso.pendientes}· faltan {f.aviso.pendientes}{/if}
                    </span>
                    <strong>{pct} %</strong>
                  </div>
                  <div class="snoc-avance" role="progressbar" aria-label="Avance del aviso" aria-valuenow={pct} aria-valuemin="0" aria-valuemax="100">
                    <span style="width:{pct}%"></span>
                  </div>
                  {#if f.aviso.fase === 'restablecido' || f.aviso.restablecidos}
                    <p class="snoc-body-sm" style="margin:0;">
                      Ya volvió: <strong>{f.aviso.restablecidos}</strong> avisados de que quedó restablecido
                      {#if f.aviso.fase === 'restablecido' && f.aviso.estado === 'en_curso' && f.aviso.pendientes}
                        · {f.aviso.pendientes} esperando a que vuelva su equipo
                      {/if}
                    </p>
                  {/if}
                  {#if f.aviso.motivo_detencion}
                    <p class="snoc-recuadro snoc-recuadro-error">{textoDeDetencion(f.aviso.motivo_detencion)}</p>
                  {/if}
                  {#each motivosLegibles(f.aviso.motivos) as m, i (i)}
                    <p class="snoc-body-sm snoc-secundario" style="margin:0;">No salió: {m}</p>
                  {/each}
                  <p class="snoc-body-sm snoc-secundario" style="margin:0;">
                    Aprobado por {f.aviso.aprobado_por || 'una persona'} el {fecha(f.aviso.aprobado_en)}
                    {#if f.aviso.detenido_por}· lo detuvo {f.aviso.detenido_por}{/if}
                    {#if f.aviso.terminado_en} · terminó el {fecha(f.aviso.terminado_en)}{/if}
                  </p>
                  <div class="snoc-fila" style="flex-wrap:wrap;">
                    <button type="button" class="snoc-btn" onclick={() => abrirDestinatarios(f)}>
                      Ver a quién le llega
                    </button>
                    {#if f.aviso.estado === 'en_curso'}
                      <form id="detener-{f.id}" method="POST" action="?/detener" use:enhance={() => alEnviar(f.id, 'detener')}>
                        <input type="hidden" name="situacion" value={f.id} />
                        <input type="hidden" name="motivo" value={motivoDetener} />
                        <button
                          type="button"
                          class="snoc-btn snoc-btn-error"
                          disabled={enviando === f.id}
                          onclick={() => { motivoDetener = ''; porDetener = f; }}
                        >
                          {enviando === f.id ? 'Deteniendo…' : 'Detener el envío'}
                        </button>
                      </form>
                    {/if}
                  </div>
                </div>
              {:else if f.por_que_no}
                <!-- Antes era texto gris: para quien opera es lo que decide. -->
                <p class="snoc-recuadro snoc-recuadro-alerta">{POR_QUE_NO[f.por_que_no] ?? f.por_que_no}</p>
              {:else if previa}
                <div class="snoc-pila" role="status">
                  {#if previa.cargando}
                    <p class="snoc-recuadro">
                      Dexter está armando la lista de clientes del ISP. Probá de nuevo en un momento.
                    </p>
                    <form method="POST" action="?/preparar" use:enhance={() => alEnviar(f.id, 'preparar')}>
                      <input type="hidden" name="situacion" value={f.id} />
                      <button class="snoc-btn" disabled={enviando === f.id}>
                        {enviando === f.id ? 'Preparando…' : 'Probar de nuevo'}
                      </button>
                    </form>
                  {:else}
                    <div class="snoc-recuadro {previa.no_listo ? 'snoc-recuadro-error' : 'snoc-recuadro-ok'} snoc-pila-xs">
                      <span>
                        Se les avisaría a <strong>{previa.clientes}</strong> clientes que se cayeron juntos.
                        {#if previa.sin_cliente || previa.fuera_de_estado}
                          Quedan afuera {previa.sin_cliente} equipos sin cliente y {previa.fuera_de_estado}
                          de clientes que no están activos.
                        {/if}
                      </span>
                      <span class="snoc-secundario">
                        Cuando la falla se resuelva, Dexter les avisa que quedó restablecido a los que
                        recibieron este aviso y cuyo equipo ya volvió.
                      </span>
                      {#if previa.modo_prueba}
                        <span style="color:var(--snoc-alerta);">
                          El aviso está en modo prueba: solo les llega a los números de prueba.
                        </span>
                      {/if}
                      {#if previa.no_listo}
                        <span class="snoc-error-txt">
                          {NO_LISTO[previa.no_listo] ?? previa.no_listo} Se cambia en Ajustes → WhatsApp →
                          Mensajes automáticos.
                        </span>
                      {/if}
                    </div>
                    {#if !previa.no_listo && previa.clientes}
                      <form id="aprobar-{f.id}" method="POST" action="?/aprobar" use:enhance={() => alEnviar(f.id, 'aprobar')}>
                        <input type="hidden" name="situacion" value={f.id} />
                        <div class="snoc-fila">
                          <button
                            type="button"
                            class="snoc-btn snoc-btn-primario"
                            disabled={enviando === f.id}
                            onclick={() => (porConfirmar = { ...f, clientes: previa.clientes, modo_prueba: previa.modo_prueba })}
                          >
                            {enviando === f.id ? 'Aprobando…' : `Avisar a ${previa.clientes} clientes`}
                          </button>
                          <button type="button" class="snoc-btn" onclick={() => delete preparadas[f.id]}>Descartar</button>
                        </div>
                      </form>
                    {/if}
                  {/if}
                </div>
              {:else}
                <form class="snoc-fila" style="flex-wrap:wrap;" method="POST" action="?/preparar" use:enhance={() => alEnviar(f.id, 'preparar')}>
                  <input type="hidden" name="situacion" value={f.id} />
                  <button class="snoc-btn snoc-btn-primario" disabled={enviando === f.id}>
                    {enviando === f.id ? 'Preparando…' : 'Preparar el aviso a los clientes'}
                  </button>
                  <span class="snoc-body-sm snoc-secundario">
                    No le envía nada a nadie: arma la lista y revisa que WhatsApp esté listo.
                  </span>
                </form>
              {/if}

              {#if f.casos?.length}
                <!-- LOS TICKETS DE LA CAÍDA (22/11/2026): los casos que Dexter ligó a
                     este puerto. Los abiertos primero. -->
                <details class="fl-casos">
                  <summary class="snoc-body-sm">
                    <strong>{f.casos_total}</strong> {f.casos_total === 1 ? 'ticket ligado' : 'tickets ligados'} a esta caída
                    {#if f.casos.some((/** @type {any} */ c) => c.abierto)}· {f.casos.filter((/** @type {any} */ c) => c.abierto).length} abiertos{/if}
                  </summary>
                  <ul class="fl-lista">
                    {#each f.casos as c (c.id)}
                      <li>
                        <a href="/tickets/{c.id}">{c.ticket ? `#${c.ticket}` : 'Ticket'}{c.cliente ? ` · ${c.cliente}` : ''}</a>
                        <span class="snoc-tag {c.abierto ? '' : 'fl-cerrado'}">{c.abierto ? 'Abierto' : 'Cerrado'}</span>
                        {#if c.servicio}<a class="snoc-body-sm" href="/clientes/{encodeURIComponent(c.servicio)}">ficha del cliente</a>{/if}
                      </li>
                    {/each}
                  </ul>
                  {#if f.casos_total > f.casos.length}
                    <p class="snoc-body-sm snoc-secundario" style="margin:0;">Se muestran {f.casos.length} de {f.casos_total}.</p>
                  {/if}
                </details>
              {/if}

              {#if mia && form?.error}
                <p class="snoc-recuadro snoc-recuadro-error" role="alert">{form.error}</p>
              {/if}
            </article>
          {/each}
        {/if}
      {/if}
    </div>
  </div>
</div>

<Confirmar
  abierto={!!porConfirmar}
  titulo="¿Avisar a {porConfirmar?.clientes ?? 0} clientes por WhatsApp?"
  confirmar="Sí, avisar a {porConfirmar?.clientes ?? 0}"
  alCancelar={() => (porConfirmar = null)}
  alConfirmar={() => enviarAprobacion(porConfirmar.id)}
>
  <p style="margin:0;">
    Caída del puerto <strong class="snoc-mono">{porConfirmar?.puerto}</strong>{#if porConfirmar?.caja}{' '}({porConfirmar.caja}){/if}.
    Sale por tandas. <strong>Un aviso enviado no se retira.</strong>
  </p>
  {#if porConfirmar?.modo_prueba}
    <p class="snoc-recuadro snoc-recuadro-alerta">Modo prueba: solo les llega a los números de prueba.</p>
  {/if}
  <p class="snoc-body-sm snoc-secundario" style="margin:0;">
    Cuando el servicio vuelva, Dexter les avisa que quedó restablecido.
  </p>
</Confirmar>

<Confirmar
  abierto={!!porDetener}
  titulo="¿Detener el envío del aviso?"
  confirmar="Sí, detener"
  tono="peligro"
  alCancelar={() => (porDetener = null)}
  alConfirmar={() => enviarDetencion(porDetener.id)}
>
  <p style="margin:0;">
    Caída del puerto <strong class="snoc-mono">{porDetener?.puerto}</strong>. Quedan
    <strong>{porDetener?.aviso?.pendientes ?? 0}</strong> por avisar.
  </p>
  <p class="snoc-body-sm snoc-secundario" style="margin:0;">
    La tanda que ya está saliendo termina. No sale ninguna más, <strong>tampoco el «ya volvió»</strong>,
    y no se puede volver a aprobar para esta caída.
  </p>
  <label class="snoc-pila-xs snoc-body-sm">
    <span>Por qué (opcional, queda en la historia de la caída)</span>
    <input class="snoc-campo" maxlength="200" bind:value={motivoDetener} placeholder="ej: falsa alarma, el mensaje no corresponde" />
  </label>
</Confirmar>

<PanelLateral
  abierto={!!verDestinatarios}
  antetitulo="Aviso de la caída · {verDestinatarios?.puerto ?? ''}"
  titulo="A quién le llega"
  alCerrar={() => (verDestinatarios = null)}
>
  {#if errorDestinatarios}
    <p class="snoc-recuadro snoc-recuadro-error" role="alert">{errorDestinatarios}</p>
  {:else if !destinatarios}
    <p class="snoc-body-sm snoc-secundario">Leyendo la lista…</p>
  {:else}
    <div class="snoc-pila">
      <p class="snoc-body-sm" style="margin:0;">
        <strong>{destinatarios.total}</strong> servicios aprobados ·
        {destinatarios.fase === 'restablecido' ? 'aviso de «ya volvió»' : 'aviso de la caída'} ·
        {cuentaDestinatarios.salieron} con su tanda ya enviada · {cuentaDestinatarios.pendientes} pendientes
      </p>
      <p class="snoc-body-sm snoc-secundario" style="margin:0;">
        «Tanda enviada» no dice que le llegó: los que no recibieron el aviso y por qué se cuentan en la
        tarjeta de la caída. El nombre sale del último ticket de ese servicio; sin ticket, se ve el número.
      </p>
      {#if destinatarios.recortada}
        <p class="snoc-recuadro snoc-recuadro-alerta">Se muestran los primeros {destinatarios.destinatarios.length}.</p>
      {/if}
      <input class="snoc-campo" type="search" placeholder="Buscar por servicio o nombre" bind:value={buscarDestinatario} aria-label="Buscar destinatario" />
      <ul class="fl-lista fl-destinatarios">
        {#each listaFiltrada as d (d.servicio)}
          <li>
            <a href="/clientes/{encodeURIComponent(d.servicio)}">
              {d.cliente || 'Sin nombre en el CRM'} <span class="snoc-mono snoc-secundario">· {d.servicio}</span>
            </a>
            <span class="snoc-tag {d.pendiente ? 'fl-pendiente' : ''}">{d.pendiente ? 'Pendiente' : 'Tanda enviada'}</span>
          </li>
        {:else}
          <li class="snoc-secundario">Nadie coincide con la búsqueda.</li>
        {/each}
      </ul>
    </div>
  {/if}
</PanelLateral>

<style>
  .fl-caida { gap: 12px; }
  .fl-casos summary { cursor: pointer; }
  .fl-lista { list-style: none; margin: 8px 0 0; padding: 0; display: flex; flex-direction: column; }
  .fl-lista li {
    display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap;
    padding: 8px 0; border-top: 1px solid var(--v2-line);
  }
  .fl-lista li:first-child { border-top: 0; }
  .fl-lista a { color: var(--v2-ember-text); text-decoration: none; font-weight: 600; }
  .fl-lista a:hover { text-decoration: underline; }
  .fl-cerrado { opacity: 0.7; }
  .fl-pendiente { background: var(--v2-ember-soft); color: var(--v2-ember-text); }
</style>
