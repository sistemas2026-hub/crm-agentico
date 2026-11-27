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
  // 'Aprobadas por Dexter' (12/11/2026): las que aprobó sola la
  // pre-factibilidad, con su motivo, para revisarlas juntas.
  const PESTANAS = [
    { estado: '', texto: 'Recibidas' },
    { estado: 'nueva', texto: 'En proceso' },
    { estado: 'aprobada', texto: 'Aprobadas' },
    { estado: 'aprobada', automatica: true, texto: 'Aprobadas por Dexter' },
    { estado: 'sin_factibilidad', texto: 'Sin factibilidad' },
    { estado: 'cancelada', texto: 'Canceladas' }
  ];
  const hrefDe = (p) =>
    p.estado ? `?estado=${p.estado}${p.automatica ? '&automatica=1' : ''}` : '/instalaciones';
  const esActiva = (p) =>
    data.vista !== 'por_activar' &&
    (data.estado || '') === p.estado && Boolean(data.automatica) === Boolean(p.automatica);
  import { CheckCircle2, AlertTriangle, MapPin, FileText, Inbox, BadgeCheck } from '@lucide/svelte';

  //  POR ACTIVAR (26/11/2026): cual tarjeta tiene abierto el «Devolver».
  let devolviendo = $state('');
  const MARCA = /** @type {Record<string, string>} */ ({ true: '✔', false: '✖', null: '?' });
  /** @param {any} i */
  const queEspera = (i) =>
    i.espera === 'entrega_del_tecnico'
      ? 'Aprobada y activa: espera que el técnico valide el servicio y la entregue.'
      : i.contrato?.instalacion?.activacion === 'pedida' || i.contrato?.instalacion?.activacion === 'en_curso'
        ? 'Activándose en el proveedor…'
        : i.contrato?.estado === 'instalacion'
          ? 'Instalación creada en el proveedor. Revísala y apruébala para activarla.'
          : i.contrato?.alta?.estado === 'pedida' || i.contrato?.alta?.estado === 'en_curso'
            ? 'Creando la instalación en el proveedor…'
            : 'La instalación todavía no está en el proveedor.';

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

  // Lo pendiente lo calcula el backend (decision.pendientes); acá solo se
  // nombra (12/11/2026).
  const QUE_FALTA = {
    reasignacion: 'mover el ticket al equipo que instala',
    cierre: 'cerrar el ticket del ISP',
    aviso: 'avisarle al cliente'
  };
  /** El estado del WhatsApp al cliente al rechazar, dicho para una persona. */
  const textoAviso = (a) => {
    if (!a?.estado) return '';
    if (a.estado === 'enviado') return 'Se le avisó al cliente por WhatsApp.';
    if (a.estado === 'esperando') return 'El aviso al cliente sale cuando abra el horario de avisos de la empresa.';
    if (a.estado === 'pendiente') return 'El aviso al cliente todavía no salió.';
    if (a.estado === 'no_aplica') return 'Rechazada antes de que existiera el aviso al cliente: no se le escribió.';
    return `No se pudo avisar al cliente: ${a.texto || a.motivo || 'motivo desconocido'}.`;
  };
  let reintentando = $state('');
  //  El contrato cuya alta en el proveedor se está volviendo a pedir.
  let pidiendoAlta = $state('');
  // Qué tarjeta tiene abierta la advertencia del mapa (ver «Ver en el mapa…»).
  let mapaAbierto = $state('');
  const fecha = (s) => (s ? new Date(s).toLocaleString('es-CO', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'America/Bogota' }) : '—');
</script>

<svelte:head><title>Instalaciones</title></svelte:head>

<!-- Scroll propio: el contenedor de la app corta lo que se sale (.v2-main,
     overflow hidden). Sin esto la pantalla no bajaba (02/11/2026). -->
<div class="v2-scroll">
<div class="hoja" data-privado>
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
        href={hrefDe(p)}
        class="pestana"
        class:activa={esActiva(p)}
        aria-current={esActiva(p) ? 'page' : undefined}
      >{p.texto}</a>
    {/each}
    <a href="?vista=por_activar" class="pestana" class:activa={data.vista === 'por_activar'}
       aria-current={data.vista === 'por_activar' ? 'page' : undefined}>Por activar</a>
  </nav>

  {#if data.sinPermiso}
    <!-- 12/11/2026: la bandeja (y el expediente con la cédula) es de las
         áreas que la empresa eligió en Ajustes → Instalaciones. El servidor
         lo decide; acá solo se dice por qué no se ve nada. -->
    <section class="vacio" role="status">
      <AlertTriangle size={26} />
      <h2>Esta bandeja no está habilitada para tu área</h2>
      <p>{data.error}</p>
    </section>
  {:else if data.error}
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
        {#if form.pendientes?.length && form.fallo}
          Quedó pendiente con el ISP: {form.fallo}
        {/if}
        {#if form.estado === 'sin_factibilidad' && form.aviso}
          {textoAviso(form.aviso)}
        {/if}
      </span>
    </div>
  {/if}
  {#if form?.altaResuelta}
    <div class="ok">
      <CheckCircle2 size={16} />
      <span>
        {form.estado === 'en_el_isp'
          ? 'Guardado: el contrato quedó con el número del cliente en el proveedor.'
          : 'Guardado: el cliente no quedó creado. Ya se puede volver a intentar o anular el contrato.'}
      </span>
    </div>
  {/if}
  {#if form?.altaPedida}
    <div class="ok">
      <CheckCircle2 size={16} />
      <span>
        {form.estado === 'en_el_isp'
          ? 'El cliente ya está creado en el proveedor.'
          : 'Pedido. El cliente se está creando en el proveedor: recarga en un momento para ver cómo quedó.'}
      </span>
    </div>
  {/if}
  {#if form?.reintentado}
    <div class="ok" class:alerta={form.pendientes?.length}>
      <CheckCircle2 size={16} />
      <span>
        {form.pendientes?.length
          ? `Sigue pendiente: ${form.pendientes.map((p) => QUE_FALTA[p] ?? p).join(', ')}.`
          : 'Listo: no queda nada pendiente con el ISP ni con el aviso al cliente.'}
        {#if form.aviso?.estado === 'no_enviado'}{textoAviso(form.aviso)}{/if}
      </span>
    </div>
  {/if}

  {#if data.vista === 'por_activar'}
    <!-- LA INSTALACIÓN QUE VALIDA UNA PERSONA (26/11/2026). El técnico finalizó;
         aquí se revisa lo que dejó y se aprueba —eso la activa en el proveedor—
         o se devuelve. Lo que se puede hacer lo decide el servidor
         (`se_puede_activar`); la pantalla solo lo muestra. -->
    {#if form?.de === 'instalacion' && form?.hecho}
      <div class="ok"><CheckCircle2 size={16} /><span>{form.hecho}</span></div>
    {/if}
    {#if form?.de === 'instalacion' && form?.error}
      <div class="alerta"><AlertTriangle size={16} /><span>{form.error}</span></div>
    {/if}
    {#if !data.error && !(data.instalaciones ?? []).length}
      <section class="vacio">
        <BadgeCheck size={26} />
        <h2>No hay instalaciones esperando validación</h2>
        <p>Cuando un técnico finalice una instalación, aparece aquí para revisarla y activarla.</p>
      </section>
    {/if}
    {#each data.instalaciones ?? [] as i (i.orden_id)}
      {@const c = i.contrato}
      {@const r = i.revision}
      <article class="tarjeta">
        <div class="encabezado">
          <div>
            <h2>OT-{i.numero} · {i.cliente}</h2>
            <p class="meta">
              Contrato {c?.numero ?? '—'}{#if c?.servicio_isp}{' · '}N.º en el proveedor {c.servicio_isp}{/if}
            </p>
          </div>
          <span class="cuando">{fecha(i.finalizada_en)}</span>
        </div>
        <p class="origen"><span>{queEspera(i)}</span></p>
        {#if c?.instalacion?.detalle}
          <p class="fallo"><AlertTriangle size={14} /><span>{c.instalacion.detalle}</span></p>
        {/if}
        {#if c?.alta?.estado === 'fallida' || c?.alta?.por_revisar}
          <p class="fallo"><AlertTriangle size={14} /><span>La instalación no quedó creada en el proveedor. {c.alta.detalle ?? ''}</span></p>
        {/if}

        {#if r}
          <div class="revision">
            <div class="grupo-titulo">Lo que revisó Dexter</div>
            <ul class="puntos">
              {#each r.puntos ?? [] as pt (pt.clave)}
                <li class:mal={pt.ok === false} class:duda={pt.ok === null}>
                  <span class="marca" aria-hidden="true">{MARCA[String(pt.ok)]}</span>
                  <span>{pt.texto}</span>
                </li>
              {/each}
            </ul>
            {#if (r.evidencias ?? []).length}
              <div class="fotos">
                {#each r.evidencias as e (e.id)}
                  <figure class:falta={!e.evidencia_id}>
                    {#if e.evidencia_id}
                      <a href={`/api/supervisor-noc/evidencias/${e.evidencia_id}/archivo`} target="_blank" rel="noopener" title="Abrir la foto">
                        <img src={`/api/supervisor-noc/evidencias/${e.evidencia_id}/archivo`} alt={e.titulo} loading="lazy" />
                      </a>
                    {:else}
                      <span class="sin-foto" aria-hidden="true">—</span>
                    {/if}
                    <figcaption>{e.titulo}{#if e.pide_atencion}{' · '}<b>mirar</b>{/if}</figcaption>
                  </figure>
                {/each}
              </div>
            {/if}
          </div>
        {:else}
          <p class="origen"><span class="tenue">La revisión automática no se pudo calcular: revisa las fotos en la orden.</span></p>
        {/if}

        {#if i.espera === 'validacion'}
          <div class="botones">
            <form method="POST" action="?/aprobarInstalacion" use:enhance={() => {
              enviando = i.orden_id;
              return async ({ update }) => { await update({ reset: false }); enviando = ''; };
            }}>
              <input type="hidden" name="orden" value={i.orden_id} />
              <button type="submit" class="aprobar" disabled={!c?.instalacion?.se_puede_activar || enviando === i.orden_id}
                      title={c?.instalacion?.se_puede_activar ? '' : 'Primero tiene que estar creada la instalación en el proveedor'}>
                {enviando === i.orden_id ? 'Aprobando…' : 'Aprobar y activar'}
              </button>
            </form>
            <button type="button" class="cancelar" onclick={() => (devolviendo = devolviendo === i.orden_id ? '' : i.orden_id)}>
              Devolver al técnico
            </button>
          </div>
          {#if devolviendo === i.orden_id}
            <form method="POST" action="?/devolverInstalacion" class="decision" use:enhance={() => {
              enviando = i.orden_id;
              return async ({ update }) => { await update({ reset: false }); enviando = ''; devolviendo = ''; };
            }}>
              <input type="hidden" name="orden" value={i.orden_id} />
              <input type="hidden" name="vuelta" value={i.vuelta ?? 1} />
              <fieldset class="rehacer">
                <legend>Qué tiene que volver a tomar</legend>
                {#each r?.evidencias ?? [] as e (e.id)}
                  <label><input type="checkbox" name="requisito" value={e.id} /> {e.titulo}</label>
                {:else}
                  <p class="tenue">Esta plantilla no pide fotos.</p>
                {/each}
              </fieldset>
              <label class="nota">Por qué
                <textarea name="observacion" rows="2" placeholder="Lo lee el técnico tal cual."></textarea>
              </label>
              <div class="botones">
                <button type="submit" class="rechazar" disabled={enviando === i.orden_id}>Devolver</button>
              </div>
            </form>
          {/if}
        {/if}
      </article>
    {/each}
  {/if}

  {#if data.vista !== 'por_activar' && !data.solicitudes?.length && !data.sinPermiso}
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
          <!-- EL GPS DE LA VIVIENDA NO SALE SIN QUE ALGUIEN LO DECIDA
               (12/11/2026). Era un enlace que mandaba las coordenadas exactas
               a Google en la URL con un clic distraído. Ahora el primer clic
               solo explica; el segundo, explícito, abre el servicio externo
               sin 'Referer'. -->
          {#if mapaAbierto === s.id}
            <span class="aviso-mapa" role="status">
              Esto abre Google Maps y le manda a Google la ubicación exacta de la vivienda.
              <a class="chip" href={mapa(s.gps)} target="_blank" rel="noopener noreferrer"
                 referrerpolicy="no-referrer" onclick={() => (mapaAbierto = '')}>
                <MapPin size={14} /> Abrir en Google Maps
              </a>
              <button type="button" class="chip" onclick={() => (mapaAbierto = '')}>No abrir</button>
            </span>
          {:else}
            <button type="button" class="chip" onclick={() => (mapaAbierto = s.id)}>
              <MapPin size={14} /> Ver en el mapa…
            </button>
          {/if}
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

      {#if s.prefactibilidad_motivo}
        <!-- Por qué Dexter la aprobó sola, o por qué la dejó para una persona
             («fuera de zona», «GPS dudoso»). Lo escribe el backend. -->
        <p class="prefact" class:auto={s.decision_automatica}>
          <strong>{s.decision_automatica ? 'Aprobada por Dexter:' : 'Pre-factibilidad:'}</strong>
          {s.prefactibilidad_motivo}
        </p>
      {/if}

      {#if s.estado === 'sin_factibilidad' && s.aviso_cliente?.estado}
        <p class="aviso-cliente" class:fallo={s.aviso_cliente.estado === 'no_enviado'}>
          {textoAviso(s.aviso_cliente)}
        </p>
      {/if}

      {#if s.pendientes?.length}
        <!-- LO PENDIENTE, CON SU BOTÓN (12/11/2026). Antes la pantalla decía
             «se puede reintentar» y no había cómo: el backend devolvía 409 a
             todo lo que no estuviera enviada. -->
        <div class="pendiente">
          <p class="fallo">
            <AlertTriangle size={14} />
            <span>
              <strong>Falta:</strong> {s.pendientes.map((p) => QUE_FALTA[p] ?? p).join(', ')}.
              {#if s.fallo_integracion}<span class="tenue">Último error: {s.fallo_integracion}</span>{/if}
            </span>
          </p>
          <form method="POST" action="?/reintentar" use:enhance={() => {
            reintentando = s.id;
            return async ({ update }) => { await update({ reset: false }); reintentando = ''; };
          }}>
            <input type="hidden" name="id" value={s.id} />
            <button type="submit" class="decidir" disabled={reintentando === s.id}>
              {reintentando === s.id ? 'Reintentando…' : 'Reintentar'}
            </button>
          </form>
        </div>
      {:else if s.fallo_integracion}
        <!-- Esto es lo que quedo a medias con un sistema externo (el ticket
             del ISP, el correo). Antes se guardaba y no se mostraba en
             ninguna parte: el 09/09/2026 una cancelacion dejo el ticket
             abierto y desde la pantalla parecia que no habia pasado nada.
             Sin pendientes, es historia: lo que fallo ya se resolvio o no se
             reintenta desde aca (el correo, la creacion del ticket). -->
        <p class="fallo">
          <AlertTriangle size={14} />
          <span><strong>Lo que falló con un sistema externo:</strong> {s.fallo_integracion}</span>
        </p>
      {/if}

      <!-- SI EL CLIENTE QUEDÓ CREADO EN EL PROVEEDOR (25/11/2026). Lo dice
           el backend (`contrato.alta`); aquí solo se dibuja. Es el único
           lugar donde hoy se ve un alta que FALLÓ: la app instalada no lo
           muestra, y un cliente sin crear que nadie ve es un fallo en
           silencio. -->
      {#if s.contrato?.estado === 'en_el_isp'}
        <p class="origen">
          <span>Contrato {s.contrato.numero} · cliente creado en el proveedor{#if s.contrato.servicio_isp}{' '}(N.º {s.contrato.servicio_isp}){/if}.</span>
        </p>
      {:else if s.contrato?.alta?.por_revisar}
        <!-- NADIE SABE SI QUEDÓ CREADO. No es un fallo, y no se ofrece
             reintentar ni anular: eso, con el cliente quizá ya creado, es
             crear dos. Lo resuelve una persona mirando en el proveedor. -->
        <div class="pendiente">
          <p class="fallo">
            <AlertTriangle size={14} />
            <span>
              <strong>No se sabe si el cliente quedó creado en el proveedor</strong> (contrato {s.contrato.numero}).
              {s.contrato.alta.detalle ?? ''}
              Búscalo en el proveedor y di qué encontraste.
            </span>
          </p>
          <form method="POST" action="?/resolverAlta" use:enhance={() => {
            pidiendoAlta = s.contrato.id;
            return async ({ update }) => { await update({ reset: false }); pidiendoAlta = ''; };
          }}>
            <input type="hidden" name="id" value={s.id} />
            <input type="hidden" name="contrato" value={s.contrato.id} />
            <input class="v2-input" name="id_cliente" inputmode="numeric" maxlength="64"
                   placeholder="N.º del cliente en el proveedor"
                   aria-label="Número del cliente en el proveedor" />
            <button type="submit" name="quedo" value="si" class="decidir"
                    disabled={pidiendoAlta === s.contrato.id}>Sí quedó: es este número</button>
            <button type="submit" name="quedo" value="no" class="decidir"
                    disabled={pidiendoAlta === s.contrato.id}>No quedó creado</button>
          </form>
        </div>
      {:else if s.contrato?.alta?.estado === 'fallida'}
        <div class="pendiente">
          <p class="fallo">
            <AlertTriangle size={14} />
            <span>
              <strong>El cliente NO quedó creado en el proveedor</strong> (contrato {s.contrato.numero}).
              {s.contrato.alta.detalle ?? ''}
            </span>
          </p>
          {#if s.contrato.alta.se_puede_pedir}
            <form method="POST" action="?/crearEnElIsp" use:enhance={() => {
              pidiendoAlta = s.contrato.id;
              return async ({ update }) => { await update({ reset: false }); pidiendoAlta = ''; };
            }}>
              <input type="hidden" name="id" value={s.id} />
              <input type="hidden" name="contrato" value={s.contrato.id} />
              <button type="submit" class="decidir" disabled={pidiendoAlta === s.contrato.id}>
                {pidiendoAlta === s.contrato.id ? 'Pidiendo…' : 'Volver a intentar'}
              </button>
            </form>
          {/if}
        </div>
      {:else if s.contrato?.alta?.estado}
        <p class="origen"><span>Contrato {s.contrato.numero} · creando al cliente en el proveedor…</span></p>
      {:else if s.contrato}
        <p class="origen"><span>Contrato {s.contrato.numero} firmado.</span></p>
      {/if}
      {#each s.contrato?.alta?.avisos ?? [] as aviso}
        <p class="origen"><span>Aviso del alta: {aviso}</span></p>
      {/each}

      <!-- A NOMBRE DE OTRA PERSONA (26/11/2026). Los datos de arriba son de
           quien hizo la solicitud; el contrato puede haber quedado a nombre de
           otra persona, y con ESE nombre se crea el cliente en el proveedor.
           Lo decide el backend (`contrato.otro_titular`); aquí solo se dibuja. -->
      {#if s.contrato?.otro_titular && s.contrato.titular}
        <div class="motivo titular">
          <div class="motivo-rotulo">El contrato quedó a nombre de otra persona</div>
          <p class="motivo-texto">
            <strong>{s.contrato.titular.nombre}</strong>{#if s.contrato.titular.documento}{' · '}{s.contrato.titular.documento}{/if}
          </p>
          <div class="motivo-cuando">Aceptó el tratamiento de sus datos al firmar. Los demás datos son los de la solicitud.</div>
        </div>
      {:else if s.contrato?.documento_cambiado}
        <p class="origen"><span>El técnico cambió el número de documento en sitio: el del contrato no es el de la solicitud.</span></p>
      {/if}

      <!-- DE DÓNDE VINO (12/11/2026): el prospecto se abre en Prospectos; la
           conversación no, porque la solicitud no la guarda (el asistente no
           la anota al crearla). Se dice en vez de inventar un enlace. -->
      <p class="origen">
        {#if s.lead_id}
          <a href="/leads/{s.lead_id}">Ver el prospecto</a>
        {:else}
          <span>Sin prospecto asociado (llegó por fuera del chat).</span>
        {/if}
        <span class="tenue">· La conversación de origen no queda guardada en la solicitud; se encuentra por el teléfono {s.telefono || ''} en Conversaciones.</span>
      </p>

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

      <!-- DECIDIR SOLO SOBRE LO QUE ESPERA UNA DECISION.
           Una solicitud cancelada, aprobada o sin factibilidad ya se resolvio.
           El backend lo rechaza ("Esta solicitud ya esta en estado '...'"), asi
           que no habia riesgo de pisar nada -- pero la pantalla ofrecia el
           boton igual en las cinco pestañas: se escribia la nota, se hacia clic
           y salia un error. Ofrecer un camino que siempre falla es peor que no
           ofrecerlo. Visto el 10/09/2026 en una tarjeta ya cancelada. -->
      {#if s.estado && s.estado !== 'enviada'}
        <!-- nada que decidir -->
      {:else if abierta === s.id}
        <form method="POST" action="?/decidir" class="decision" use:enhance={() => {
          enviando = s.id;
          return async ({ update }) => { await update({ reset: false }); enviando = ''; abierta = ''; nota = ''; };
        }}>
          <input type="hidden" name="id" value={s.id} />
          <label class="nota">
            Nota
            <textarea name="nota" bind:value={nota} rows="2"
              placeholder="Obligatoria si rechazás: se le manda al cliente por WhatsApp, tal cual. Escribila para él."></textarea>
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
</div>

<style>
  .pestanas {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
    border-bottom: 1px solid var(--v2-line);
    margin-bottom: 4px;
  }
  .pestana {
    padding: 8px 14px;
    font-size: 13.5px;
    color: var(--v2-slate);
    text-decoration: none;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
  }
  .pestana:hover { color: var(--v2-ink); }
  .pestana.activa {
    color: var(--v2-ink);
    font-weight: 600;
    border-bottom-color: var(--v2-ember);
  }

  .hoja { max-width: 820px; padding: 24px 20px 60px; display: flex; flex-direction: column; gap: 14px; }
  h1 { font-size: 1.6rem; margin: 0 0 4px; letter-spacing: -.02em; }
  .bajada { color: var(--v2-slate); margin: 0; max-width: 62ch; }

  .tarjeta {
    background: var(--v2-card); border: 1px solid var(--v2-line); border-radius: 10px;
    padding: 16px; display: flex; flex-direction: column; gap: 11px;
  }
  .encabezado { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
  .encabezado h2 { font-size: 1.05rem; margin: 0; }
  .meta { margin: 2px 0 0; font-size: .86rem; color: var(--v2-slate); }
  .cuando { font-size: .8rem; color: var(--v2-slate); white-space: nowrap; }

  .donde { background: var(--v2-paper); border: 1px solid var(--v2-line); border-radius: 8px; padding: 10px 12px; }
  .dir { font-weight: 650; }
  .sub { font-size: .86rem; color: var(--v2-slate); margin-top: 2px; }

  .acciones-datos { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip {
    display: inline-flex; align-items: center; gap: 6px; font-size: .83rem;
    border: 1px solid var(--v2-line-strong); border-radius: 999px; padding: 5px 11px;
    color: var(--v2-ink); text-decoration: none; background: var(--v2-paper);
  }
  .chip.tenue { color: var(--v2-slate); }
  button.chip { font: inherit; font-size: .83rem; cursor: pointer; }
  .aviso-mapa {
    display: inline-flex; flex-wrap: wrap; align-items: center; gap: 8px;
    font-size: .83rem; color: var(--v2-ink); background: var(--v2-paper);
    border: 1px dashed var(--v2-line-strong); border-radius: 8px; padding: 6px 10px;
  }
  .chip.dudoso {
    background: color-mix(in srgb, var(--v2-clay) 10%, var(--v2-card));
    border-color: color-mix(in srgb, var(--v2-clay) 35%, var(--v2-card));
    color: var(--v2-clay);
  }

  .fallo { display: flex; gap: 7px; align-items: flex-start; margin: 0; font-size: .83rem; color: var(--v2-rust); }
  .pendiente { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between; }
  .aviso-cliente { margin: 0; font-size: .85rem; color: var(--v2-slate); }
  .prefact { margin: 0; font-size: .85rem; color: var(--v2-clay); }
  .prefact.auto { color: var(--v2-moss); }
  .origen { margin: 0; font-size: .82rem; display: flex; flex-wrap: wrap; gap: 6px; }
  .origen a { color: var(--v2-ember-text); }
  .tenue { color: var(--v2-slate); }

  /* POR ACTIVAR (26/11/2026) */
  .revision { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px; border: 1px solid var(--v2-line); border-radius: 8px; background: var(--v2-paper); }
  .puntos { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 3px; font-size: .85rem; }
  .puntos li { display: flex; gap: 8px; align-items: flex-start; color: var(--v2-ink); }
  .puntos .marca { width: 1.1em; flex: none; font-weight: 700; color: var(--v2-moss); }
  .puntos li.mal .marca, .puntos li.mal { color: var(--v2-rust); }
  .puntos li.duda .marca { color: var(--v2-clay); }
  .fotos { display: grid; grid-template-columns: repeat(auto-fill, minmax(96px, 1fr)); gap: 8px; }
  .fotos figure { margin: 0; display: flex; flex-direction: column; gap: 3px; }
  .fotos img { width: 100%; aspect-ratio: 1; object-fit: cover; border-radius: 6px; border: 1px solid var(--v2-line); }
  .fotos .sin-foto { display: grid; place-items: center; aspect-ratio: 1; border-radius: 6px; border: 1px dashed var(--v2-line-strong); color: var(--v2-slate); }
  .fotos figcaption { font-size: .74rem; color: var(--v2-slate); line-height: 1.25; }
  .fotos figure.falta figcaption { color: var(--v2-rust); }
  .rehacer { border: 1px solid var(--v2-line); border-radius: 8px; padding: 8px 10px; display: flex; flex-direction: column; gap: 4px; font-size: .86rem; }
  .rehacer legend { font-weight: 600; padding: 0 4px; }

  /* El motivo de cancelacion se lee como una cita, porque lo es: son las
     palabras del cliente sin resumir ni corregir (ver CancelarSolicitudView). */
  .motivo {
    border-left: 3px solid var(--v2-clay); background: color-mix(in srgb, var(--v2-clay) 10%, var(--v2-card));
    border-radius: 0 8px 8px 0; padding: 9px 12px;
  }
  .motivo.revision { border-left-color: var(--v2-origen-ink); background: var(--v2-origen); }
  .motivo.titular { border-left-color: var(--v2-moss); background: color-mix(in srgb, var(--v2-moss) 9%, var(--v2-card)); }
  .motivo-rotulo {
    font-size: .72rem; text-transform: uppercase; letter-spacing: .05em;
    color: var(--v2-slate); margin-bottom: 4px;
  }
  .motivo-texto { margin: 0; font-size: .93rem; line-height: 1.45; color: var(--v2-ink); }
  .motivo-cuando { margin-top: 5px; font-size: .78rem; color: var(--v2-slate); }

  .ver-detalle {
    align-self: flex-start; font: inherit; font-size: .82rem; font-weight: 600;
    background: none; border: 0; padding: 2px 0; cursor: pointer;
    color: var(--v2-ember-text); text-decoration: underline;
  }
  .detalle {
    display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
    gap: 14px; padding: 12px; border: 1px solid var(--v2-line); border-radius: 8px;
    background: var(--v2-paper);
  }
  .grupo-titulo {
    font-size: .72rem; text-transform: uppercase; letter-spacing: .05em;
    color: var(--v2-slate); margin-bottom: 6px;
  }
  /* Rotulo y valor en dos columnas: leer 'Ticket del ISP  92151' de un
     vistazo es lo que hace util esta tabla. */
  .detalle dl {
    margin: 0; display: grid; grid-template-columns: auto 1fr;
    gap: 3px 10px; font-size: .83rem;
  }
  .detalle dt { color: var(--v2-slate); }
  .detalle dd { margin: 0; color: var(--v2-ink); font-weight: 600; word-break: break-word; }
  .detalle dd.si { color: var(--v2-moss); }

  .decidir, .cancelar {
    align-self: flex-start; font: inherit; font-weight: 600; background: var(--v2-card);
    border: 1px solid var(--v2-line-strong); border-radius: 8px; padding: 9px 16px; cursor: pointer;
  }
  .decision { display: flex; flex-direction: column; gap: 9px; }
  .nota { display: flex; flex-direction: column; gap: 5px; font-size: .86rem; font-weight: 600; color: var(--v2-ink); }
  textarea {
    font: inherit; font-weight: 400; padding: 9px 11px; border: 1px solid var(--v2-line-strong);
    border-radius: 8px; background: var(--v2-card); resize: vertical;
  }
  .botones { display: flex; flex-wrap: wrap; gap: 8px; }
  .aprobar, .rechazar {
    font: inherit; font-weight: 650; border-radius: 8px; padding: 9px 16px;
    cursor: pointer; border: 1px solid transparent;
  }
  .aprobar { background: var(--v2-moss); color: #fff; }
  .rechazar { background: var(--v2-card); color: var(--v2-rust); border-color: color-mix(in srgb, var(--v2-rust) 35%, var(--v2-card)); }
  button:disabled { opacity: .6; cursor: default; }
  textarea:focus-visible, button:focus-visible, a:focus-visible {
    outline: 2px solid var(--v2-ember); outline-offset: 2px;
  }

  .vacio {
    text-align: center; color: var(--v2-slate); background: var(--v2-card); border: 1px solid var(--v2-line);
    border-radius: 10px; padding: 40px 24px; display: flex; flex-direction: column;
    align-items: center; gap: 8px;
  }
  .vacio h2 { margin: 0; font-size: 1.05rem; color: var(--v2-ink); }
  .vacio p { margin: 0; max-width: 46ch; font-size: .9rem; }

  .alerta, .ok { display: flex; gap: 9px; align-items: center; border-radius: 8px; padding: 11px 13px; font-size: .9rem; }
  .alerta {
    background: color-mix(in srgb, var(--v2-rust) 10%, var(--v2-card));
    border: 1px solid color-mix(in srgb, var(--v2-rust) 35%, var(--v2-card));
    color: var(--v2-rust);
  }
  .ok {
    background: color-mix(in srgb, var(--v2-moss) 10%, var(--v2-card));
    border: 1px solid color-mix(in srgb, var(--v2-moss) 35%, var(--v2-card));
    color: var(--v2-moss);
  }
</style>
