<script>
  /**
   * Bandeja de solicitudes de instalación.
   *
   * Quien abre esta pantalla en 'Recibidas' tiene que responder UNA pregunta
   * por solicitud: ¿el servicio llega a esa dirección? Por eso la tarjeta
   * muestra primero la dirección, el mapa y el expediente, y nada más.
   *
   * Pero las otras pestañas son consulta, no decisión, y ahí hace falta otra
   * cosa: por qué se canceló, quién la aprobó, si el ticket del ISP salió.
   * Eso vive en 'Ver detalle', cerrado por defecto — volcarle veinte campos a
   * cada tarjeta la volvería ilegible justo para lo que se usa todos los días.
   *
   * Dos excepciones que van SIEMPRE visibles, sin un clic de por medio:
   * el motivo de cancelación (es LA razón por la que alguien abre esa
   * tarjeta) y lo que quedó pendiente con un sistema externo. Ese segundo se
   * guardaba desde siempre y no se mostraba en ninguna parte: el 09/09/2026
   * una cancelación dejó el ticket de WispHub abierto, el motivo estaba
   * anotado y el fallo también, y desde la pantalla parecía que el sistema no
   * había hecho nada.
   *
   * Las coordenadas se muestran con su precisión a la vista: un GPS de ±50 km
   * (pasa cuando el formulario se abre desde una computadora) no sirve para
   * decidir, y quien mira tiene que saberlo antes de confiar en el punto.
   */
  import { enhance } from '$app/forms';

  // 'Recibidas' es la vista por defecto (estado vacío = lo que espera una
  // decisión, que es para lo que se abre esta pantalla). Las otras cuatro son
  // consulta: lo ya resuelto, y lo que todavía no llegó.
  const PESTANAS = [
    { estado: '', texto: 'Recibidas' },
    { estado: 'nueva', texto: 'En proceso' },
    { estado: 'aprobada', texto: 'Aprobadas' },
    { estado: 'sin_factibilidad', texto: 'Sin factibilidad' },
    { estado: 'cancelada', texto: 'Canceladas' }
  ];
  import { CheckCircle2, AlertTriangle, MapPin, FileText, Inbox } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let abierta = $state('');
  let nota = $state('');
  let enviando = $state('');
  /**
   * Que tarjetas tienen el detalle desplegado.
   *
   * Cerrado por defecto y no abierto: la bandeja existe para decidir de un
   * vistazo, y volcarle veinte campos a cada tarjeta la vuelve ilegible justo
   * para lo que se usa todos los dias. El detalle es para cuando alguien
   * pregunta algo puntual -- por que se cancelo, si el ticket salio.
   */
  let detalles = $state(new Set());
  const alternarDetalle = (id) => {
    const proximo = new Set(detalles);
    proximo.has(id) ? proximo.delete(id) : proximo.add(id);
    detalles = proximo;
  };

  // Arriba de este valor, la ubicación no alcanza para decidir factibilidad:
  // son cuadras de diferencia. No se bloquea nada — se avisa, que es lo que
  // permite pedirle al cliente que la vuelva a tomar desde el celular.
  const PRECISION_DUDOSA_M = 200;

  const mapa = (g) => `https://www.google.com/maps?q=${g.lat},${g.lng}`;
  const fecha = (s) => (s ? new Date(s).toLocaleString('es-CO', { dateStyle: 'medium', timeStyle: 'short' }) : '—');
</script>

<svelte:head><title>Instalaciones</title></svelte:head>

<div class="hoja">
  <header>
    <h1>Solicitudes de instalación</h1>
    <p class="bajada">
      Esperando que alguien confirme si el servicio llega a la dirección. Al aprobar, el
      ticket pasa al equipo que instala.
    </p>
  </header>

  <!-- El estado viaja en la URL y no en un estado local: así una pestaña se
       puede compartir por chat, y volver atrás en el navegador hace lo que
       uno espera. La carga la resuelve el servidor con ?estado=. -->
  <nav class="pestanas" aria-label="Filtrar por estado">
    {#each PESTANAS as p}
      <a
        href={p.estado ? `?estado=${p.estado}` : '/instalaciones'}
        class="pestana"
        class:activa={(data.estado || '') === p.estado}
        aria-current={(data.estado || '') === p.estado ? 'page' : undefined}
      >{p.texto}</a>
    {/each}
  </nav>

  {#if data.error}
    <div class="alerta"><AlertTriangle size={16} /><span>{data.error}</span></div>
  {/if}
  {#if form?.error}
    <div class="alerta"><AlertTriangle size={16} /><span>{form.error}</span></div>
  {/if}
  {#if form?.decidido}
    <div class="ok">
      <CheckCircle2 size={16} />
      <span>
        Solicitud {form.estado === 'aprobada' ? 'aprobada' : 'rechazada'}.
        {#if form.fallo}
          El ticket de WispHub no se pudo mover: {form.fallo}
        {/if}
      </span>
    </div>
  {/if}

  {#if !data.solicitudes?.length}
    <section class="vacio">
      <Inbox size={26} />
      <h2>No hay solicitudes esperando</h2>
      <p>
        Acá aparecen las solicitudes apenas alguien completa el formulario que le pasa el
        asistente por WhatsApp.
      </p>
    </section>
  {/if}

  {#each data.solicitudes as s (s.id)}
    <article class="tarjeta">
      <div class="encabezado">
        <div>
          <h2>{s.nombre || s.telefono}</h2>
          <p class="meta">{s.documento} · {s.telefono}{s.correo ? ` · ${s.correo}` : ''}</p>
        </div>
        <span class="cuando">{fecha(s.enviada_en)}</span>
      </div>

      <!-- La dirección primero y grande: es el dato sobre el que se decide. -->
      <div class="donde">
        <div class="dir">{s.direccion || '(sin dirección)'}</div>
        <div class="sub">Barrio {s.barrio || '—'} · Plan {s.plan || '—'}</div>
      </div>

      <div class="acciones-datos">
        {#if s.gps}
          <a class="chip" href={mapa(s.gps)} target="_blank" rel="noopener">
            <MapPin size={14} /> Ver en el mapa
          </a>
          {#if Number(s.gps.precision_m) > PRECISION_DUDOSA_M}
            <span class="chip dudoso">
              <AlertTriangle size={14} />
              Ubicación aproximada (±{Math.round(Number(s.gps.precision_m) / 1000) || 1} km) — pedile que la tome desde el celular
            </span>
          {/if}
        {:else}
          <span class="chip dudoso"><AlertTriangle size={14} /> Sin coordenadas</span>
        {/if}
        {#if s.tiene_pdf}
          <a class="chip" href="/api/solicitudes/{s.id}/expediente" target="_blank" rel="noopener">
            <FileText size={14} /> Expediente
          </a>
        {/if}
        {#if s.ticket_wisphub}
          <span class="chip tenue">Ticket {s.ticket_wisphub}</span>
        {/if}
      </div>

      <!-- EL MOTIVO DE CANCELACION VA SIEMPRE VISIBLE, no dentro del
           detalle: en la pestaña 'Canceladas' es LA razon por la que alguien
           abre esa tarjeta. Esconderlo detras de un clic seria pedirle un
           clic para lo unico que vino a ver. -->
      {#if s.estado === 'cancelada' && s.motivo_cancelacion}
        <div class="motivo">
          <div class="motivo-rotulo">Motivo de la cancelación, en palabras del cliente</div>
          <p class="motivo-texto">“{s.motivo_cancelacion}”</p>
          {#if s.cancelada_en}<div class="motivo-cuando">Cancelada el {fecha(s.cancelada_en)}</div>{/if}
        </div>
      {/if}

      {#if s.nota_revision}
        <div class="motivo revision">
          <div class="motivo-rotulo">
            Nota de quien revisó{s.revisada_por ? ` — ${s.revisada_por}` : ''}
          </div>
          <p class="motivo-texto">{s.nota_revision}</p>
        </div>
      {/if}

      {#if s.fallo_integracion}
        <!-- Esto es lo que quedo a medias con un sistema externo (el ticket
             del ISP, el correo). Antes se guardaba y no se mostraba en
             ninguna parte: el 09/09/2026 una cancelacion dejo el ticket
             abierto y desde la pantalla parecia que no habia pasado nada. -->
        <p class="fallo">
          <AlertTriangle size={14} />
          <span><strong>Quedó pendiente con un sistema externo:</strong> {s.fallo_integracion}</span>
        </p>
      {/if}

      <button type="button" class="ver-detalle" onclick={() => alternarDetalle(s.id)}
              aria-expanded={detalles.has(s.id)}>
        {detalles.has(s.id) ? 'Ocultar detalle' : 'Ver detalle'}
      </button>

      {#if detalles.has(s.id)}
        <div class="detalle">
          <div class="grupo">
            <div class="grupo-titulo">Estado del trámite</div>
            <dl>
              <dt>Estado</dt><dd>{s.estado || 'enviada'}</dd>
              <dt>Enviada</dt><dd>{fecha(s.enviada_en)}</dd>
              {#if s.revisada_en}<dt>Revisada</dt><dd>{fecha(s.revisada_en)}</dd>{/if}
              {#if s.cancelada_en}<dt>Cancelada</dt><dd>{fecha(s.cancelada_en)}</dd>{/if}
              <dt>Ticket del ISP</dt>
              <dd>{s.ticket_wisphub || 'sin ticket'}</dd>
              <dt>Correo al equipo</dt>
              <dd>{s.correo_enviado_en ? fecha(s.correo_enviado_en) : 'no se envió'}</dd>
            </dl>
          </div>

          <div class="grupo">
            <div class="grupo-titulo">Lo que contó el cliente</div>
            <dl>
              {#if s.tipo_solicitud}<dt>Tipo</dt><dd>{s.tipo_solicitud}</dd>{/if}
              {#if s.edad}<dt>Edad</dt><dd>{s.edad}</dd>{/if}
              {#if s.fecha_corte}<dt>Fecha de corte</dt><dd>{s.fecha_corte}</dd>{/if}
              {#if s.como_se_entero}<dt>Cómo nos conoció</dt><dd>{s.como_se_entero}</dd>{/if}
              {#if s.gps}<dt>Coordenadas</dt><dd>{s.gps.lat}, {s.gps.lng}</dd>{/if}
            </dl>
          </div>

          <!-- Las autorizaciones vivian solo dentro del expediente en PDF:
               para comprobar que estaban habia que abrir el documento entero,
               con la cedula adentro. Aca se ven sin exponer nada de eso. -->
          <div class="grupo">
            <div class="grupo-titulo">Autorizaciones</div>
            <dl>
              <dt>Habeas data</dt>
              <dd class:si={s.autoriza_habeas_data}>
                {s.autoriza_habeas_data ? 'Autorizó' : 'No autorizó'}
              </dd>
              <dt>Centrales de riesgo</dt>
              <dd class:si={s.autoriza_centrales_riesgo}>
                {s.autoriza_centrales_riesgo ? 'Autorizó' : 'No autorizó'}
              </dd>
              {#if s.autorizaciones_en}
                <dt>Firmadas</dt><dd>{fecha(s.autorizaciones_en)}</dd>
              {/if}
              {#if s.ip_autorizaciones}
                <dt>Desde la IP</dt><dd>{s.ip_autorizaciones}</dd>
              {/if}
            </dl>
          </div>
        </div>
      {/if}

      {#if abierta === s.id}
        <form method="POST" action="?/decidir" class="decision" use:enhance={() => {
          enviando = s.id;
          return async ({ update }) => { await update({ reset: false }); enviando = ''; abierta = ''; nota = ''; };
        }}>
          <input type="hidden" name="id" value={s.id} />
          <label class="nota">
            Nota
            <textarea name="nota" bind:value={nota} rows="2"
              placeholder="Obligatoria si rechazás: el cliente va a preguntar por qué."></textarea>
          </label>
          <div class="botones">
            <button type="submit" name="aprueba" value="true" class="aprobar" disabled={enviando === s.id}>
              {enviando === s.id ? 'Guardando…' : 'Hay factibilidad'}
            </button>
            <button type="submit" name="aprueba" value="false" class="rechazar" disabled={enviando === s.id}>
              No hay factibilidad
            </button>
            <button type="button" class="cancelar" onclick={() => { abierta = ''; nota = ''; }}>
              Cancelar
            </button>
          </div>
        </form>
      {:else}
        <button type="button" class="decidir" onclick={() => { abierta = s.id; nota = ''; }}>
          Decidir
        </button>
      {/if}
    </article>
  {/each}
</div>

<style>
  .pestanas {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
    border-bottom: 1px solid var(--v2-border, #e3e6e4);
    margin-bottom: 4px;
  }
  .pestana {
    padding: 8px 14px;
    font-size: 13.5px;
    color: var(--v2-text-muted, #6b7671);
    text-decoration: none;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
  }
  .pestana:hover { color: var(--v2-text, #16211f); }
  .pestana.activa {
    color: var(--v2-text, #16211f);
    font-weight: 600;
    border-bottom-color: var(--v2-accent, #0f6e6a);
  }

  .hoja { max-width: 820px; padding: 24px 20px 60px; display: flex; flex-direction: column; gap: 14px; }
  h1 { font-size: 1.6rem; margin: 0 0 4px; letter-spacing: -.02em; }
  .bajada { color: #5a6672; margin: 0; max-width: 62ch; }

  .tarjeta {
    background: #fff; border: 1px solid #d3dae1; border-radius: 10px;
    padding: 16px; display: flex; flex-direction: column; gap: 11px;
  }
  .encabezado { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
  .encabezado h2 { font-size: 1.05rem; margin: 0; }
  .meta { margin: 2px 0 0; font-size: .86rem; color: #5a6672; }
  .cuando { font-size: .8rem; color: #7b8794; white-space: nowrap; }

  .donde { background: #f2f6fa; border: 1px solid #d3dae1; border-radius: 8px; padding: 10px 12px; }
  .dir { font-weight: 650; }
  .sub { font-size: .86rem; color: #5a6672; margin-top: 2px; }

  .acciones-datos { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip {
    display: inline-flex; align-items: center; gap: 6px; font-size: .83rem;
    border: 1px solid #cbd4dd; border-radius: 999px; padding: 5px 11px;
    color: #35404b; text-decoration: none; background: #fafbfc;
  }
  .chip.tenue { color: #7b8794; }
  .chip.dudoso { background: #fdf6e3; border-color: #e6d9ae; color: #6b5a2b; }

  .fallo { display: flex; gap: 7px; align-items: flex-start; margin: 0; font-size: .83rem; color: #8a2a20; }

  /* El motivo de cancelacion se lee como una cita, porque lo es: son las
     palabras del cliente sin resumir ni corregir (ver CancelarSolicitudView). */
  .motivo {
    border-left: 3px solid #b45309; background: #fffbeb;
    border-radius: 0 8px 8px 0; padding: 9px 12px;
  }
  .motivo.revision { border-left-color: #1668c1; background: #f2f7fd; }
  .motivo-rotulo {
    font-size: .72rem; text-transform: uppercase; letter-spacing: .05em;
    color: #6b7280; margin-bottom: 4px;
  }
  .motivo-texto { margin: 0; font-size: .93rem; line-height: 1.45; color: #35404b; }
  .motivo-cuando { margin-top: 5px; font-size: .78rem; color: #6b7280; }

  .ver-detalle {
    align-self: flex-start; font: inherit; font-size: .82rem; font-weight: 600;
    background: none; border: 0; padding: 2px 0; cursor: pointer;
    color: #1668c1; text-decoration: underline;
  }
  .detalle {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: 14px; padding: 12px; border: 1px solid #e3e8ee; border-radius: 8px;
    background: #fbfcfd;
  }
  .grupo-titulo {
    font-size: .72rem; text-transform: uppercase; letter-spacing: .05em;
    color: #6b7280; margin-bottom: 6px;
  }
  /* Rotulo y valor en dos columnas: leer 'Ticket del ISP  92151' de un
     vistazo es lo que hace util esta tabla. */
  .detalle dl {
    margin: 0; display: grid; grid-template-columns: auto 1fr;
    gap: 3px 10px; font-size: .83rem;
  }
  .detalle dt { color: #6b7280; }
  .detalle dd { margin: 0; color: #23303c; font-weight: 600; word-break: break-word; }
  .detalle dd.si { color: #1f7a4d; }

  .decidir, .cancelar {
    align-self: flex-start; font: inherit; font-weight: 600; background: #fff;
    border: 1px solid #cbd4dd; border-radius: 8px; padding: 9px 16px; cursor: pointer;
  }
  .decision { display: flex; flex-direction: column; gap: 9px; }
  .nota { display: flex; flex-direction: column; gap: 5px; font-size: .86rem; font-weight: 600; color: #35404b; }
  textarea {
    font: inherit; font-weight: 400; padding: 9px 11px; border: 1px solid #cbd4dd;
    border-radius: 8px; background: #fafbfc; resize: vertical;
  }
  .botones { display: flex; flex-wrap: wrap; gap: 8px; }
  .aprobar, .rechazar {
    font: inherit; font-weight: 650; border-radius: 8px; padding: 9px 16px;
    cursor: pointer; border: 1px solid transparent;
  }
  .aprobar { background: #1d7a45; color: #fff; }
  .rechazar { background: #fff; color: #8a2a20; border-color: #f0b8b2; }
  button:disabled { opacity: .6; cursor: default; }
  textarea:focus-visible, button:focus-visible, a:focus-visible {
    outline: 2px solid #1668c1; outline-offset: 2px;
  }

  .vacio {
    text-align: center; color: #5a6672; background: #fff; border: 1px solid #d3dae1;
    border-radius: 10px; padding: 40px 24px; display: flex; flex-direction: column;
    align-items: center; gap: 8px;
  }
  .vacio h2 { margin: 0; font-size: 1.05rem; color: #17202b; }
  .vacio p { margin: 0; max-width: 46ch; font-size: .9rem; }

  .alerta, .ok { display: flex; gap: 9px; align-items: center; border-radius: 8px; padding: 11px 13px; font-size: .9rem; }
  .alerta { background: #fdecea; border: 1px solid #f0b8b2; color: #8a2a20; }
  .ok { background: #f4fbf6; border: 1px solid #b9dfc6; color: #1d7a45; }
</style>
