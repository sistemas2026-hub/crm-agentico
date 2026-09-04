<script>
  /**
   * Bandeja de solicitudes de instalación.
   *
   * Quien abre esta pantalla tiene que responder UNA pregunta por solicitud:
   * ¿el servicio llega a esa dirección? Todo lo que está en la tarjeta existe
   * para contestarla — la dirección, el mapa, el expediente — y nada más.
   *
   * Las coordenadas se muestran con su precisión a la vista: un GPS de ±50 km
   * (pasa cuando el formulario se abre desde una computadora) no sirve para
   * decidir, y quien mira tiene que saberlo antes de confiar en el punto.
   */
  import { enhance } from '$app/forms';
  import { CheckCircle2, AlertTriangle, MapPin, FileText, Inbox } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let abierta = $state('');
  let nota = $state('');
  let enviando = $state('');

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
        {#if s.pdf}
          <a class="chip" href={s.pdf} target="_blank" rel="noopener">
            <FileText size={14} /> Expediente
          </a>
        {/if}
        {#if s.ticket_wisphub}
          <span class="chip tenue">Ticket {s.ticket_wisphub}</span>
        {/if}
      </div>

      {#if s.fallo_integracion}
        <p class="fallo"><AlertTriangle size={14} /> {s.fallo_integracion}</p>
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

  .fallo { display: flex; gap: 7px; align-items: center; margin: 0; font-size: .83rem; color: #8a2a20; }

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
