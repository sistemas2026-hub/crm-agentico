<script>
  /**
   * El formulario de contratación.
   *
   * Lo llena una persona desde el celular, saliendo de una conversación de
   * WhatsApp, y le pedimos 20 campos, tres fotos y una firma. Todo acá está
   * pensado alrededor de eso:
   *
   *  - Lo que ya nos dijo por chat viene prellenado. No se le pregunta dos
   *    veces.
   *  - Los requisitos se dicen ARRIBA, antes de que empiece: descubrir en el
   *    paso 4 que hace falta una foto del recibo es cuando la gente abandona.
   *  - El GPS y la firma se piden con el pulgar, no con el teclado.
   *  - Si algo falla al enviar, no se pierde nada de lo escrito.
   */
  import { enhance } from '$app/forms';
  import { untrack } from 'svelte';
  import PortalShell from '$lib/v2/components/PortalShell.svelte';
  import { CheckCircle2, Clock, MapPin, Camera, PenLine, AlertTriangle } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  // 'untrack' porque esto siembra los campos UNA vez y después son de quien
  // escribe: sin esto, un re-render del loader le pisaría lo que ya tipeó.
  // Mismo criterio que la página de CSAT.
  const p = untrack(() => data.prellenado ?? {});
  // Los planes que se ofrecen en su zona (los resuelve el motor desde el
  // catalogo curado). Vacio = el motor no respondio, y el campo cae a texto.
  const planes = untrack(() => data.planesDisponibles ?? []);

  // Ubicación: se guarda en estado porque la da el navegador, no el teclado.
  let gps = $state({ lat: p.gps_lat ?? '', lng: p.gps_lng ?? '', precision: p.gps_precision_m ?? '' });
  let gpsEstado = $state(untrack(() => (gps.lat ? 'listo' : 'sin_pedir')));
  let gpsError = $state('');

  let enviando = $state(false);
  let lienzo = $state(null);
  let firmado = $state(false);

  const TEXTO_AUTORIZACIONES = [
    'Autorización Centrales de Riesgo (Ley 1266 de 2008): autorizo a Rapilink SAS a consultar, ' +
      'reportar y actualizar mi información en las bases de datos de centrales de riesgo crediticio.',
    'Habeas Data (Ley 1581 de 2012): autorizo el tratamiento de mis datos personales por parte de ' +
      'Rapilink SAS para las finalidades descritas en su Política de Privacidad, incluyendo la ' +
      'prestación del servicio y el envío de comunicaciones relacionadas.'
  ].join('\n\n');

  function pedirUbicacion() {
    if (!navigator.geolocation) {
      gpsError = 'Tu navegador no puede compartir la ubicación. Probá desde el celular.';
      return;
    }
    gpsEstado = 'pidiendo';
    gpsError = '';
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        gps = {
          lat: String(pos.coords.latitude),
          lng: String(pos.coords.longitude),
          precision: String(Math.round(pos.coords.accuracy))
        };
        gpsEstado = 'listo';
      },
      (err) => {
        gpsEstado = 'sin_pedir';
        // Cada motivo tiene una salida distinta; un "no se pudo" genérico deja
        // a la persona sin saber qué hacer.
        gpsError =
          err.code === err.PERMISSION_DENIED
            ? 'Nos negaste el permiso de ubicación. Activalo en el candado de la barra de direcciones y volvé a tocar el botón.'
            : err.code === err.TIMEOUT
              ? 'Tardó demasiado. Salí al patio o a la calle y probá de nuevo: adentro la señal del GPS es peor.'
              : 'No se pudo obtener la ubicación. Probá de nuevo en unos segundos.';
      },
      { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
    );
  }

  // --- firma ---------------------------------------------------------------
  // Un lienzo y no un campo de texto: es lo que la persona espera al firmar, y
  // lo que después se ve en el expediente que abre el técnico.
  let dibujando = false;

  function pos(e) {
    const r = lienzo.getBoundingClientRect();
    const t = e.touches?.[0] ?? e;
    return { x: t.clientX - r.left, y: t.clientY - r.top };
  }
  function empezar(e) {
    e.preventDefault();
    dibujando = true;
    const ctx = lienzo.getContext('2d');
    const { x, y } = pos(e);
    ctx.beginPath();
    ctx.moveTo(x, y);
  }
  function trazar(e) {
    if (!dibujando) return;
    e.preventDefault();
    const ctx = lienzo.getContext('2d');
    ctx.lineWidth = 2.2;
    ctx.lineCap = 'round';
    ctx.strokeStyle = '#17202b';
    const { x, y } = pos(e);
    ctx.lineTo(x, y);
    ctx.stroke();
    firmado = true;
  }
  function terminar() {
    dibujando = false;
  }
  function borrarFirma() {
    lienzo.getContext('2d').clearRect(0, 0, lienzo.width, lienzo.height);
    firmado = false;
  }

  // La firma es un lienzo, no un archivo: se convierte a PNG justo antes de
  // enviar y se agrega al FormData como un archivo más.
  function alEnviar({ formData, cancel }) {
    if (!firmado) {
      cancel();
      alert('Falta tu firma.');
      return;
    }
    enviando = true;
    formData.set('texto_autorizaciones', TEXTO_AUTORIZACIONES);
    formData.set('gps_lat', gps.lat);
    formData.set('gps_lng', gps.lng);
    formData.set('gps_precision_m', gps.precision);

    return new Promise((resolver) => {
      lienzo.toBlob((blob) => {
        formData.set('firma', blob, 'firma.png');
        resolver(async ({ update }) => {
          await update({ reset: false });   // no se borra lo escrito si falla
          enviando = false;
        });
      }, 'image/png');
    });
  }
</script>

<svelte:head><title>Solicitud de servicio · Rapilink</title></svelte:head>

<PortalShell>
  <div class="hoja">
    {#if data.vencida || data.invalida}
      <section class="tarjeta centro">
        <Clock size={22} />
        <h1>Este enlace ya no sirve</h1>
        <p>
          Los enlaces de solicitud quedan abiertos un tiempo limitado. Escribinos por WhatsApp
          y te pasamos uno nuevo en el momento.
        </p>
      </section>
    {:else if data.error}
      <section class="tarjeta centro">
        <AlertTriangle size={22} />
        <h1>No pudimos abrir tu solicitud</h1>
        <p>{data.error}. Probá de nuevo en unos minutos.</p>
      </section>
    {:else if data.yaEnviada || form?.enviada}
      <section class="tarjeta centro exito">
        <CheckCircle2 size={26} />
        <h1>Recibimos tu solicitud</h1>
        <p>{form?.mensaje ?? 'Te contactamos para coordinar la instalación.'}</p>
      </section>
    {:else}
      <header class="encabezado">
        <h1>Solicitud de servicio</h1>
        <p class="bajada">Completá el formulario para solicitar tu conexión de fibra óptica + TV.</p>
      </header>

      <!-- Los requisitos, ANTES de empezar. Descubrir en el paso 4 que hace
           falta una foto del recibo es exactamente donde la gente abandona. -->
      <aside class="requisitos">
        <strong>Antes de empezar, tené a mano:</strong>
        <ul>
          <li>Tu cédula (para fotografiarla)</li>
          <li>Un recibo de agua o luz</li>
          <li>Estar en la dirección donde querés el servicio, para compartir la ubicación</li>
        </ul>
        <span class="minuto">Toma unos 5 minutos.</span>
      </aside>

      {#if form?.error}
        <div class="alerta" role="alert">
          <AlertTriangle size={16} />
          <span>{form.error}</span>
        </div>
      {/if}

      <form method="POST" action="?/enviar" enctype="multipart/form-data" use:enhance={alEnviar}>
        <fieldset class="tarjeta" disabled={enviando}>
          <legend><span class="n">1</span> Datos personales</legend>
          <div class="grilla">
            <label>Nombre <span class="req">*</span>
              <input name="nombre" value={p.nombre ?? ''} required placeholder="Ej. María" />
            </label>
            <label>Apellido <span class="req">*</span>
              <input name="apellido" value={p.apellido ?? ''} required placeholder="Ej. González" />
            </label>
            <label>Edad
              <input name="edad" value={p.edad ?? ''} inputmode="numeric" placeholder="Mínimo 18 años" />
            </label>
            <label>Correo electrónico
              <input name="correo" type="email" value={p.correo ?? ''} placeholder="ejemplo@correo.com" />
            </label>
            <label>Teléfono / Celular <span class="req">*</span>
              <input name="telefono" value={p.telefono ?? ''} required inputmode="tel" placeholder="Ej. 3001234567" />
            </label>
            <label>Tipo de documento
              <select name="tipo_documento" value={p.tipo_documento ?? ''}>
                <option value="">Seleccioná una opción</option>
                <option>Cédula de ciudadanía</option>
                <option>Cédula de extranjería</option>
                <option>Pasaporte</option>
                <option>NIT</option>
              </select>
            </label>
            <label class="ancho">Número de documento <span class="req">*</span>
              <input name="numero_documento" value={p.numero_documento ?? ''} required inputmode="numeric" placeholder="Ej. 1234567890" />
            </label>
          </div>
        </fieldset>

        <fieldset class="tarjeta" disabled={enviando}>
          <legend><span class="n">2</span> Información del servicio</legend>
          <div class="grilla">
            <label>Tipo de solicitud
              <select name="tipo_solicitud" value={p.tipo_solicitud ?? ''}>
                <option value="">Seleccioná una opción</option>
                <option>Instalación nueva</option>
                <option>Traslado de servicio</option>
                <option>Servicio adicional</option>
              </select>
            </label>
            <!-- Los planes de SU zona, no un campo libre: escribir el nombre
                 a mano deja pedir un plan que ahi no se ofrece, y eso lo
                 descubre alguien recien al ir a instalar. Viene preseleccionado
                 con el que eligió en la conversación, y puede cambiarlo por
                 otro de la misma lista si cambió de idea.

                 Si la lista viene vacía (el motor no respondió) se cae a texto
                 libre: una solicitud que se puede enviar vale más que una
                 lista perfecta. -->
            <label>Plan de interés
              {#if planes.length}
                <select name="plan_interesado" value={p.plan_interesado ?? ''}>
                  {#each planes as plan}
                    <option value={plan}>{plan}</option>
                  {/each}
                  {#if p.plan_interesado && !planes.includes(p.plan_interesado)}
                    <!-- El plan que eligió ya no figura en su zona. Se deja
                         igual, seleccionado: quitárselo sin avisar sería
                         cambiarle la solicitud por atrás. -->
                    <option value={p.plan_interesado}>{p.plan_interesado} (a confirmar)</option>
                  {/if}
                </select>
              {:else}
                <input name="plan_interesado" value={p.plan_interesado ?? ''} placeholder="Ej. FAMILIA — 200 MB + TV" />
              {/if}
            </label>
            <label>Fecha de corte de facturación
              <select name="fecha_corte" value={p.fecha_corte ?? ''}>
                <option value="">Seleccioná una opción</option>
                <option>15</option>
                <option>30</option>
              </select>
            </label>
            <label>¿Cómo se enteró del servicio?
              <select name="como_se_entero" value={p.como_se_entero ?? ''}>
                <option value="">Seleccioná una opción</option>
                <option>WhatsApp</option>
                <option>Recomendación de un conocido</option>
                <option>Redes sociales</option>
                <option>Publicidad en la calle</option>
                <option>Otro</option>
              </select>
            </label>
          </div>
        </fieldset>

        <fieldset class="tarjeta" disabled={enviando}>
          <legend><span class="n">3</span> Ubicación</legend>
          <div class="grilla">
            <label class="ancho">Dirección completa <span class="req">*</span>
              <input name="direccion" value={p.direccion ?? ''} required placeholder="Ej. Calle 45 # 23-10, Casa 3" />
            </label>
            <label>Barrio <span class="req">*</span>
              <input name="barrio" value={p.barrio ?? ''} required placeholder="Ej. Zarabanda" />
            </label>
            <div class="campo">
              <span class="rotulo">Coordenadas GPS <span class="req">*</span></span>
              {#if gpsEstado === 'listo'}
                <p class="gps-ok"><MapPin size={15} /> Ubicación tomada (±{gps.precision} m)</p>
                <button type="button" class="secundario" onclick={pedirUbicacion}>Volver a tomarla</button>
              {:else}
                <button type="button" class="principal" onclick={pedirUbicacion} disabled={gpsEstado === 'pidiendo'}>
                  <MapPin size={16} />
                  {gpsEstado === 'pidiendo' ? 'Obteniendo…' : 'Obtener mi ubicación'}
                </button>
              {/if}
              {#if gpsError}<p class="error-campo">{gpsError}</p>{/if}
            </div>
          </div>
          <p class="aviso">
            <AlertTriangle size={15} />
            <span>
              <strong>La ubicación es lo que decide si podemos llegar.</strong> Con ella verificamos
              si hay red disponible en tu dirección — sin coordenadas precisas no podemos confirmarlo.
              Tomala parada donde querés el servicio.
            </span>
          </p>
        </fieldset>

        <fieldset class="tarjeta" disabled={enviando}>
          <legend><span class="n">4</span> Documentos</legend>
          <div class="fotos">
            {#each [['foto_cedula', 'Foto de la cédula'], ['foto_recibo', 'Foto del recibo de agua o luz'], ['foto_solicitante', 'Foto tuya']] as [campo, rotulo]}
              <label class="foto">
                <Camera size={18} />
                <span class="rot">{rotulo} <span class="req">*</span></span>
                <!-- capture: en el celular abre la cámara directo, que es de
                     donde sale la foto en la práctica. -->
                <input type="file" name={campo} accept="image/*" capture="environment" required />
                <span class="peso">Máx. 5 MB</span>
              </label>
            {/each}
          </div>
        </fieldset>

        <fieldset class="tarjeta" disabled={enviando}>
          <legend><span class="n">5</span> Firma</legend>
          <canvas
            bind:this={lienzo} width="600" height="200" class="lienzo"
            onmousedown={empezar} onmousemove={trazar} onmouseup={terminar} onmouseleave={terminar}
            ontouchstart={empezar} ontouchmove={trazar} ontouchend={terminar}
          ></canvas>
          <div class="bajo-lienzo">
            <span><PenLine size={14} /> Firmá con el dedo dentro del recuadro</span>
            <button type="button" class="secundario" onclick={borrarFirma}>Borrar</button>
          </div>
        </fieldset>

        <fieldset class="tarjeta" disabled={enviando}>
          <legend><span class="n">6</span> Autorizaciones</legend>
          <label class="check">
            <input type="checkbox" name="autoriza_centrales_riesgo" value="true" />
            <span>
              <strong>Centrales de riesgo (Ley 1266 de 2008).</strong> Autorizo a Rapilink SAS a
              consultar, reportar y actualizar mi información en las bases de datos de centrales
              de riesgo crediticio.
            </span>
          </label>
          <label class="check">
            <input type="checkbox" name="autoriza_habeas_data" value="true" required />
            <span>
              <strong>Habeas Data (Ley 1581 de 2012). <span class="req">*</span></strong> Autorizo el
              tratamiento de mis datos personales por parte de Rapilink SAS para las finalidades
              descritas en su Política de Privacidad, incluyendo la prestación del servicio y el
              envío de comunicaciones relacionadas.
            </span>
          </label>
        </fieldset>

        <button type="submit" class="enviar" disabled={enviando}>
          {enviando ? 'Enviando…' : 'Enviar mi solicitud'}
        </button>
        <p class="pie">Tu información está protegida bajo la Ley 1581 de 2012.</p>
      </form>
    {/if}
  </div>
</PortalShell>

<style>
  .hoja { max-width: 760px; margin: 0 auto; padding: 20px 16px 64px; }

  .encabezado { text-align: center; margin-bottom: 18px; }
  h1 { font-size: clamp(1.6rem, 5vw, 2.1rem); margin: 0 0 6px; letter-spacing: -.02em; }
  .bajada { color: #5a6672; margin: 0; }

  .requisitos {
    background: #f2f6fa; border: 1px solid #d3dae1; border-radius: 10px;
    padding: 14px 16px; margin-bottom: 18px; font-size: .93rem;
  }
  .requisitos ul { margin: 8px 0 6px; padding-left: 1.1rem; display: flex; flex-direction: column; gap: 4px; }
  .minuto { color: #5a6672; font-size: .86rem; }

  .tarjeta {
    background: #fff; border: 1px solid #d3dae1; border-radius: 10px;
    padding: 18px 16px; margin-bottom: 14px;
  }
  .tarjeta[disabled] { opacity: .6; }
  .centro { text-align: center; display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 40px 20px; }
  .exito { border-color: #b9dfc6; background: #f4fbf6; }

  legend { font-weight: 650; font-size: 1.02rem; display: flex; align-items: center; gap: 9px; padding: 0 4px; }
  .n {
    background: #1668c1; color: #fff; width: 24px; height: 24px; border-radius: 50%;
    display: inline-flex; align-items: center; justify-content: center; font-size: .82rem;
  }

  .grilla { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; margin-top: 12px; }
  .ancho { grid-column: 1 / -1; }
  label, .campo { display: flex; flex-direction: column; gap: 5px; font-size: .88rem; font-weight: 600; color: #35404b; }
  .rotulo { font-size: .88rem; font-weight: 600; }
  .req { color: #c0392b; }

  /* Los campos de texto van sin 'type' y con 'inputmode' (numeric/tel): el
     teclado del celular cambia igual y no se hereda la validacion rara de
     type=tel. Por eso aca no hay selectores por type salvo email. */
  input:not([type]), input[type='email'], select {
    font: inherit; font-weight: 400; padding: 10px 12px;
    border: 1px solid #cbd4dd; border-radius: 8px; background: #fafbfc; width: 100%;
  }
  input:focus-visible, select:focus-visible, button:focus-visible, canvas:focus-visible {
    outline: 2px solid #1668c1; outline-offset: 2px;
  }

  .principal, .secundario {
    font: inherit; font-weight: 600; border-radius: 8px; padding: 10px 14px; cursor: pointer;
    display: inline-flex; align-items: center; justify-content: center; gap: 7px;
  }
  .principal { background: #1668c1; color: #fff; border: 1px solid #1668c1; }
  .secundario { background: #fff; color: #35404b; border: 1px solid #cbd4dd; }
  .gps-ok { margin: 0; color: #1d7a45; font-weight: 600; display: flex; align-items: center; gap: 6px; }
  .error-campo { color: #c0392b; font-weight: 400; font-size: .85rem; margin: 4px 0 0; }

  .aviso {
    display: flex; gap: 9px; align-items: flex-start; margin: 14px 0 0;
    background: #fdf6e3; border: 1px solid #e6d9ae; border-radius: 8px;
    padding: 11px 13px; font-size: .87rem; font-weight: 400; color: #6b5a2b;
  }

  .fotos { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; margin-top: 12px; }
  .foto {
    border: 1px dashed #cbd4dd; border-radius: 8px; padding: 14px; gap: 7px;
    align-items: flex-start; background: #fafbfc;
  }
  .foto .rot { font-size: .86rem; }
  .foto .peso { font-weight: 400; font-size: .78rem; color: #7b8794; }
  .foto input[type='file'] { font: inherit; font-weight: 400; font-size: .82rem; width: 100%; }

  .lienzo {
    width: 100%; height: 190px; margin-top: 12px; background: #fafbfc;
    border: 1px dashed #cbd4dd; border-radius: 8px; touch-action: none; cursor: crosshair;
  }
  .bajo-lienzo {
    display: flex; justify-content: space-between; align-items: center;
    margin-top: 8px; font-size: .83rem; color: #7b8794;
  }
  .bajo-lienzo span { display: inline-flex; align-items: center; gap: 6px; }

  .check {
    flex-direction: row; align-items: flex-start; gap: 10px;
    font-weight: 400; font-size: .88rem; line-height: 1.5; margin-top: 12px;
  }
  .check input { margin-top: 3px; flex: none; width: 17px; height: 17px; }

  .enviar {
    width: 100%; font: inherit; font-size: 1.02rem; font-weight: 650; color: #fff;
    background: #1668c1; border: none; border-radius: 10px; padding: 15px; cursor: pointer;
  }
  .enviar:disabled { background: #8fb4d9; cursor: default; }
  .pie { text-align: center; color: #7b8794; font-size: .82rem; margin: 10px 0 0; }

  .alerta {
    display: flex; gap: 9px; align-items: center; background: #fdecea;
    border: 1px solid #f0b8b2; color: #8a2a20; border-radius: 8px;
    padding: 11px 13px; margin-bottom: 14px; font-size: .9rem;
  }
</style>
