<script>
  /**
   * Centro de mando: la operacion de los agentes, vista como una sala.
   *
   * Cada agente configurado en el tenant tiene una estacion; su color dice en
   * que anda (procesando / atendiendo / disponible / error) y su placa, que
   * trae entre manos. Todo sale de /centro-mando en el motor, que cuenta
   * filas -- no hay ni un dato simulado en esta pantalla. Si el motor no
   * responde, se dice; no se rellena con nada.
   *
   * Por que una sala y no una tabla: la pregunta que responde esto no es
   * "cuantas conversaciones hubo" (para eso esta /consumo y la bandeja) sino
   * "quien esta haciendo que ahora", y eso se lee de un vistazo por posicion
   * y color mucho antes que leyendo filas.
   *
   * La escena se dibuja sobre un lienzo fijo de 1600x1020 y se escala al
   * espacio disponible: asi las posiciones son aritmetica simple y no
   * dependen del tamano de la ventana.
   */
  import { onMount } from 'svelte';
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import { Button } from '$lib/components/ui/button/index.js';
  import { AlertTriangle, RefreshCw, Users } from '@lucide/svelte';

  /** @type {{ data: any }} */
  let { data } = $props();

  let panorama = $state(data.panorama);
  let error = $state(data.error || '');
  let refrescando = $state(false);
  let ultimoRefresco = $state(/** @type {string|null} */ (null));
  let seleccionado = $state(/** @type {any} */ (null));
  let escala = $state(1);

  const ANCHO = 1600, ALTO = 1020;
  const CX = ANCHO / 2, CY = 530, RX = 570, RY = 315;

  /* ---------------------------------------------------------------------
   * Imagenes. El motor no sabe (ni debe saber) con que dibujo se representa
   * cada rol: manda nombre, area y cargo. La correspondencia es de
   * presentacion y vive aqui, por palabras clave, con un respaldo generico
   * para el rol que no encaje en ninguna -- que es lo que pasa siempre que
   * una empresa nueva llama a sus areas de otra manera.
   * ------------------------------------------------------------------- */
  const PISTAS_ESTACION = [
    [/vent|comercial/, 'ventas'],
    [/factur|cartera|pago|cobr/, 'facturacion'],
    [/fibra|ftth|red|olt/, 'soporte-fibra'],
    [/tecnic|soporte/, 'soporte'],
    [/campo|instal|visita|cuadrilla/, 'campo'],
    [/supervis|administra|analista|gerencia/, 'supervisor'],
    [/escala/, 'escalamiento'],
    [/espera|cola/, 'espera'],
    [/cliente|recepcion|router|chat|guiad|config/, 'chat']
  ];
  const PISTAS_AVATAR = [
    [/vent|comercial/, 'ventas'],
    [/factur|cartera|pago|cobr/, 'facturacion'],
    [/fibra|ftth|red|olt|tecnic/, 'soporte'],
    [/campo|instal|visita/, 'campo'],
    [/supervis|administra|analista/, 'supervisor'],
    [/identidad|verific/, 'identidad'],
    [/dato|analit|informe/, 'datos'],
    [/cliente|recepcion|router|chat|guiad|config/, 'router']
  ];

  function porPistas(/** @type {any[][]} */ pistas, /** @type {any} */ agente, /** @type {string} */ respaldo) {
    const texto = `${agente.nombre} ${agente.area || ''} ${agente.cargo || ''}`.toLowerCase();
    for (const [patron, archivo] of pistas) {
      if (patron.test(texto)) return archivo;
    }
    return respaldo;
  }

  const estacionDe = (/** @type {any} */ a) => `/centro-mando/estaciones/${porPistas(PISTAS_ESTACION, a, 'generica')}.webp`;
  const avatarDe = (/** @type {any} */ a) => `/centro-mando/avatares/${porPistas(PISTAS_AVATAR, a, 'router')}.webp`;

  /* --------------------------------------------------------------------- */
  const COLORES = {
    procesando: '#06B6D4',
    atendiendo: '#2563EB',
    disponible: '#22C55E',
    error: '#EF4444'
  };
  const ROTULO = {
    procesando: 'PROCESANDO',
    atendiendo: 'ATENDIENDO',
    disponible: 'DISPONIBLE',
    error: 'CON ERRORES'
  };
  const colorDe = (/** @type {any} */ a) => COLORES[/** @type {keyof typeof COLORES} */ (a.estado)] || '#8AA2C0';

  const agentes = $derived(panorama?.agentes || []);
  const totales = $derived(panorama?.totales || {});
  const eventos = $derived(panorama?.eventos || []);
  const servicios = $derived(panorama?.servicios || []);

  /* El pod se encoge cuando hay muchos agentes: lo que manda es el arco que
     le toca a cada uno sobre el anillo. Con seis caben holgados; un tenant
     con diez los tendria encimados si el ancho fuera fijo. */
  const anchoEstacion = $derived(Math.max(
    170, Math.min(320, (Math.PI * (RX + RY) / Math.max(agentes.length, 1)) * 0.74)));


  /** Reparte los agentes en un anillo: dos, seis u once caben igual. */
  function posicion(/** @type {number} */ i, /** @type {number} */ n) {
    // Se arranca arriba (-90) para que el primero quede al fondo y no tapado
    // por las placas de los de adelante.
    const ang = (-90 + (360 / Math.max(n, 1)) * i) * Math.PI / 180;
    return { x: CX + RX * Math.cos(ang), y: CY + RY * Math.sin(ang) };
  }

  const hora = (/** @type {string|null} */ iso) =>
    iso ? new Date(iso).toLocaleTimeString('es-CO',
      { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'America/Bogota' }) : '—';

  const ms = (/** @type {number|null} */ v) => (v == null ? '—' : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${v} ms`);

  function textoEvento(/** @type {any} */ e) {
    if (e.tipo === 'escalada') return `Conversación escalada${e.motivo ? `: ${e.motivo}` : ''}`;
    if (e.tipo === 'herramienta_fallida') return `${e.herramienta} falló`;
    if (e.tipo === 'accion') return `${e.herramienta} ejecutada`;
    return `${e.herramienta} · ${ms(e.duracion_ms)}`;
  }

  async function refrescar() {
    if (refrescando) return;
    refrescando = true;
    try {
      const r = await fetch('/api/centro-mando?ventana=10');
      const d = await r.json();
      if (r.ok) {
        panorama = d;
        error = '';
        ultimoRefresco = new Date().toISOString();
        if (seleccionado) {
          seleccionado = d.agentes.find((/** @type {any} */ a) => a.nombre === seleccionado.nombre) || null;
        }
      } else {
        error = d.error || 'No se pudo actualizar';
      }
    } catch (/** @type {any} */ e) {
      error = e?.message || 'No se pudo contactar al asistente';
    } finally {
      refrescando = false;
    }
  }

  function ajustar() {
    const caja = document.getElementById('escena');
    if (!caja) return;
    escala = Math.min(caja.clientWidth / ANCHO, caja.clientHeight / ALTO);
  }

  onMount(() => {
    ajustar();
    window.addEventListener('resize', ajustar);
    // Cada 12 s, y solo con la pestana a la vista: refrescar en segundo plano
    // es pegarle a la base cada 12 s por cada pestana olvidada abierta.
    const t = setInterval(() => { if (!document.hidden) refrescar(); }, 12000);
    return () => {
      clearInterval(t);
      window.removeEventListener('resize', ajustar);
    };
  });
</script>

<PageHeader title="Centro de mando" subtitle="Qué está haciendo cada agente ahora mismo">
  {#snippet actions()}
    <Button variant="outline" size="sm" onclick={refrescar} disabled={refrescando}>
      <RefreshCw class="mr-2 size-4 {refrescando ? 'animate-spin' : ''}" />
      Actualizar
    </Button>
  {/snippet}
</PageHeader>

{#if error}
  <div class="mb-4 flex items-start gap-3 rounded-lg border border-amber-500/40 bg-amber-500/10 p-4">
    <AlertTriangle class="mt-0.5 size-5 shrink-0 text-amber-500" />
    <div>
      <p class="font-medium">No se pudo leer la operación</p>
      <p class="text-muted-foreground text-sm">{error}</p>
    </div>
  </div>
{/if}

{#if panorama}
  <div class="sala">
    <!-- barra de identidad: de quien es esta operacion y de cuando es el dato -->
    <div class="identidad">
      <span class="marca"><i></i>DEXTER <b>· CENTRO DE MANDO</b></span>
      <span class="tenant">{panorama.tenant}</span>
      <span class="sep"></span>
      <span class="dato">{agentes.length} agentes configurados</span>
      {#if totales.abiertas_total}
        <span class="dato">{totales.abiertas_total} abiertas sin cerrar</span>
      {/if}
      {#if totales.fallos_hoy}
        <span class="dato rojo">{totales.fallos_hoy} fallos hoy</span>
      {/if}
      <span class="reloj">{hora(ultimoRefresco || panorama.generado_en)} <em>(Bogotá)</em></span>
    </div>

    <!-- franja de cifras -->
    <div class="cifras">
      {#each [
        ['Activas (24 h)', totales.conversaciones_activas, ''],
        ['Agentes con trabajo', totales.agentes_activos, ''],
        ['Conversaciones hoy', totales.atendidas_hoy, ''],
        ['Herramientas hoy', totales.herramientas_hoy, ''],
        ['Herramienta promedio', ms(totales.duracion_media_ms), ''],
        ['Esperan a una persona', totales.esperando_humano, 'ambar']
      ] as [rotulo, valor, tono]}
        <div class="cifra {tono}">
          <div class="v">{valor ?? '—'}</div>
          <div class="k">{rotulo}</div>
        </div>
      {/each}
    </div>

    <div class="cuerpo">
      <div class="escena" id="escena">
        <div class="lienzo" style="width:{ANCHO}px; height:{ALTO}px; transform:translate(-50%,-50%) scale({escala})">
          <!-- radios del nucleo a cada estacion -->
          <svg class="piso" viewBox="0 0 {ANCHO} {ALTO}" preserveAspectRatio="none">
            {#each agentes as a, i}
              {@const p = posicion(i, agentes.length)}
              <line x1={CX} y1={CY} x2={p.x} y2={p.y} stroke={colorDe(a)}
                    stroke-width="1.5" stroke-dasharray="5 9" opacity="0.45" />
            {/each}
            <ellipse cx={CX} cy={CY} rx={RX} ry={RY} fill="none"
                     stroke="rgba(0,229,255,.10)" stroke-width="1" />
          </svg>

          <!-- nucleo -->
          <div class="nucleo" style="left:{CX}px; top:{CY}px">
            <div class="anillo"></div>
            <div class="rot">EN CURSO AHORA</div>
            <div class="n">{totales.conversaciones_activas ?? 0}</div>
            <div class="sub">activas (24 h)</div>
            {#if totales.esperando_humano}
              <div class="humano">{totales.esperando_humano} esperan a una persona</div>
            {/if}
          </div>

          <!-- servicios externos usados hoy, anclados al borde -->
          {#each servicios as s, i}
            <div class="servicio" class:fallando={s.fallos > 0}
                 style="left:{i < 3 ? 24 : ANCHO - 236}px; top:{120 + (i % 3) * 84}px">
              <div class="t">{s.herramienta}</div>
              <div class="d">{s.usos} usos · {ms(s.duracion_media_ms)}{s.fallos ? ` · ${s.fallos} fallos` : ''}</div>
            </div>
          {/each}

          <!-- estaciones -->
          {#each agentes as a, i}
            {@const p = posicion(i, agentes.length)}
            <div class="estacion" style="--c:{colorDe(a)}; left:{p.x}px; top:{p.y}px; width:{anchoEstacion}px">
              <img class="pod" src={estacionDe(a)} alt="" />
              <div class="tinte" style="-webkit-mask-image:url({estacionDe(a)}); mask-image:url({estacionDe(a)})"></div>
            </div>
          {/each}

          <!-- agentes y placas -->
          {#each agentes as a, i}
            {@const p = posicion(i, agentes.length)}
            <button class="agente" style="--c:{colorDe(a)}; left:{p.x}px; top:{p.y}px"
                    onclick={() => (seleccionado = a)}
                    aria-label="Ver detalle de {a.nombre}">
              <img src={avatarDe(a)} alt="" class:trabaja={a.estado === 'procesando'} />
            </button>

            <div class="placa" style="--c:{colorDe(a)}; width:{Math.max(168, anchoEstacion * 0.78)}px; left:{p.x}px; top:{p.y + anchoEstacion * 0.26}px">
              <div class="fila1">
                <span class="nombre">{a.nombre.replaceAll('_', ' ')}</span>
                <span class="chip"><i class:vivo={a.estado === 'procesando'}></i>{ROTULO[a.estado] || a.estado}</span>
              </div>
              <div class="area">{a.cargo || a.area || ''}</div>
              {#if a.haciendo}<div class="haciendo">{a.haciendo}</div>{/if}
              <div class="datos">
                <span>Conv <b>{a.conversaciones}</b></span>
                {#if a.esperando_humano}<span class="ambar">Humano <b>{a.esperando_humano}</b></span>{/if}
                {#if a.ultima_herramienta}<span class="tool">{a.ultima_herramienta}</span>{/if}
              </div>
            </div>
          {/each}
        </div>
      </div>

      <!-- eventos -->
      <aside class="eventos">
        <header>
          <span>Actividad reciente</span>
          <span class="sello">{ultimoRefresco ? hora(ultimoRefresco) : hora(panorama.generado_en)}</span>
        </header>
        <div class="lista">
          {#each eventos as e}
            <div class="evento {e.tipo}">
              <div class="h">{hora(e.en)}</div>
              <div class="q">{e.agente.replaceAll('_', ' ')}</div>
              <div class="d">{textoEvento(e)}</div>
            </div>
          {:else}
            <p class="vacio">Sin actividad registrada en las últimas 6 horas.</p>
          {/each}
        </div>
      </aside>
    </div>
  </div>

  <!-- detalle -->
  {#if seleccionado}
    <button class="telon" onclick={() => (seleccionado = null)} aria-label="Cerrar detalle"></button>
    <aside class="detalle" style="--c:{colorDe(seleccionado)}">
      <header>
        <img src={avatarDe(seleccionado)} alt="" />
        <div>
          <h2>{seleccionado.nombre.replaceAll('_', ' ')}</h2>
          <p>{seleccionado.cargo || ''}{seleccionado.area ? ` · ${seleccionado.area}` : ''}</p>
          <span class="chip"><i></i>{ROTULO[seleccionado.estado] || seleccionado.estado}</span>
        </div>
        <button class="cerrar" onclick={() => (seleccionado = null)} aria-label="Cerrar">✕</button>
      </header>

      <div class="rejilla">
        <div><b>{seleccionado.conversaciones}</b><span>Activas (24 h)</span></div>
        <div><b>{seleccionado.abiertas_total}</b><span>Abiertas sin cerrar</span></div>
        <div><b>{seleccionado.esperando_humano}</b><span>Esperan a una persona</span></div>
        <div><b>{seleccionado.recibidas_hoy}</b><span>Recibidas hoy</span></div>
        <div><b>{seleccionado.llamadas_ventana}</b><span>Herramientas ({panorama.ventana_min} min)</span></div>
        <div><b>{ms(seleccionado.duracion_media_ms)}</b><span>Duración media</span></div>
        <div class:rojo={seleccionado.fallos_ventana > 0}><b>{seleccionado.fallos_ventana}</b><span>Fallos recientes</span></div>
      </div>

      <div class="bloque">
        <h3>Descripción</h3>
        <p>{seleccionado.descripcion || 'Sin descripción configurada.'}</p>
      </div>

      <div class="bloque">
        <h3>Última señal</h3>
        <p>
          {#if seleccionado.ultima_herramienta}
            Última herramienta: <code>{seleccionado.ultima_herramienta}</code><br />
          {/if}
          Última actividad: {hora(seleccionado.ultima_actividad)}
          {#if seleccionado.ultima_actividad}<span class="tz"> (Bogotá)</span>{/if}
        </p>
      </div>

      <footer>
        <Button href="/agentes" variant="outline" size="sm">Ver configuración</Button>
        <Button href="/conversaciones" size="sm">
          <Users class="mr-2 size-4" />Abrir bandeja
        </Button>
      </footer>
    </aside>
  {/if}
{/if}

<style>
  .sala {
    --fondo: #050b18; --panel: #0f172a; --borde: rgba(0,229,255,.14);
    --texto: #e6f1ff; --texto2: #8aa2c0; --texto3: #47607f;
    /* El color va aparte del degradado a proposito: el degradado arranca casi
       transparente y, sin un fondo opaco debajo, en el CRM (que es claro) se
       veia la pagina blanca a traves del centro de la sala. */
    background-color: var(--fondo);
    background-image: radial-gradient(ellipse at 50% 0%, rgba(0,229,255,.16), transparent 62%);
    color: var(--texto);
    border: 1px solid var(--borde); border-radius: 14px; overflow: hidden;
    display: flex; flex-direction: column; height: calc(100vh - 190px); min-height: 560px;
  }
  /* auto-fit y no un numero fijo de columnas: son ocho cifras y el ancho
     disponible depende del menu lateral. Con un numero fijo, la ultima se
     caia a una segunda fila y quedaba fuera del marco de la sala. */
  .cifras { display: grid; grid-template-columns: repeat(auto-fit, minmax(146px, 1fr)); border-bottom: 1px solid var(--borde); }
  .cifra { padding: 12px 16px; border-right: 1px solid var(--borde); }
  .cifra:last-child { border-right: 0; }
  .cifra .v { font-family: ui-monospace, monospace; font-size: 22px; font-weight: 700; line-height: 1; }
  .cifra .k { font-size: 10px; letter-spacing: .1em; color: var(--texto2); text-transform: uppercase; margin-top: 6px; }
  .cifra.ambar .v { color: #f59e0b; }
  .cifra.rojo .v { color: #ef4444; }

  .cuerpo { flex: 1; display: flex; min-height: 0; }
  .escena { flex: 1; position: relative; overflow: hidden; }
  .lienzo { position: absolute; left: 50%; top: 50%; transform-origin: center; }
  .piso { position: absolute; inset: 0; width: 100%; height: 100%; }

  .estacion { position: absolute; transform: translate(-50%, -42%); pointer-events: none; }
  .estacion .pod { width: 100%; display: block; }
  .estacion .tinte {
    position: absolute; inset: 0; background: var(--c); opacity: .3; mix-blend-mode: color;
    -webkit-mask-size: 100% 100%; mask-size: 100% 100%; transition: background .4s;
  }

  .agente {
    position: absolute; transform: translate(-50%, -50%); background: none; border: 0; padding: 0;
    cursor: pointer; z-index: 2;
  }
  .agente img {
    width: 92px; height: 92px; border-radius: 50%; object-fit: cover; display: block;
    border: 2px solid var(--c); box-shadow: 0 0 20px var(--c), 0 10px 18px rgba(0,0,0,.6);
    transition: box-shadow .3s;
  }
  .agente img.trabaja { animation: latir 2.2s ease-in-out infinite; }
  .agente:hover img { box-shadow: 0 0 30px var(--c); }

  .placa {
    position: absolute; transform: translateX(-50%); z-index: 3;
    background: rgba(15,23,42,.95); border: 1px solid var(--c); border-radius: 10px;
    padding: 8px 10px; backdrop-filter: blur(6px);
  }
  .placa .fila1 { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
  .placa .nombre { font-size: 11.5px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; line-height: 1.25; }
  .placa .area { font-size: 9.5px; color: var(--texto2); margin-top: 2px; }
  .placa .datos { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 6px; font-family: ui-monospace, monospace; font-size: 9.5px; color: var(--texto2); }
  .placa .datos b { color: var(--texto); }
  .placa .datos .ambar { color: #f59e0b; }
  .placa .datos .tool { color: var(--c); }

  .chip {
    font-family: ui-monospace, monospace; font-size: 8.5px; letter-spacing: .08em; font-weight: 700;
    padding: 2px 6px; border-radius: 5px; white-space: nowrap; color: var(--c);
    border: 1px solid var(--c); background: color-mix(in srgb, var(--c) 14%, transparent);
    display: inline-flex; align-items: center; gap: 5px;
  }
  .chip i { width: 6px; height: 6px; border-radius: 50%; background: var(--c); display: inline-block; }
  .chip i.vivo { animation: latir 1.6s infinite; }

  .nucleo {
    position: absolute; transform: translate(-50%, -50%); width: 190px; height: 190px; border-radius: 50%;
    background: rgba(3,10,23,.9); border: 1px solid rgba(0,229,255,.4);
    box-shadow: 0 0 40px rgba(0,229,255,.28), inset 0 0 26px rgba(0,229,255,.12);
    display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center;
  }
  .nucleo .anillo { position: absolute; inset: -8px; border-radius: 50%; border: 1px solid rgba(0,229,255,.2); border-top-color: #00e5ff; animation: girar 9s linear infinite; }
  .nucleo .rot { font-family: ui-monospace, monospace; font-size: 8px; letter-spacing: .2em; color: #00e5ff; }
  .nucleo .n { font-family: ui-monospace, monospace; font-size: 38px; font-weight: 700; line-height: 1.1; }
  .nucleo .sub { font-size: 9px; letter-spacing: .12em; color: var(--texto2); text-transform: uppercase; }
  .nucleo .humano { font-family: ui-monospace, monospace; font-size: 8.5px; color: #f59e0b; margin-top: 6px; }

  .eventos { flex: 0 0 320px; background: var(--panel); border-left: 1px solid var(--borde); display: flex; flex-direction: column; min-height: 0; }
  .eventos header { padding: 12px 16px; border-bottom: 1px solid var(--borde); display: flex; justify-content: space-between; align-items: center; font-size: 11.5px; letter-spacing: .12em; text-transform: uppercase; }
  .eventos .sello { font-family: ui-monospace, monospace; font-size: 10px; color: var(--texto3); letter-spacing: 0; }
  .eventos .lista { flex: 1; overflow-y: auto; padding: 10px 14px; }
  .evento { padding: 8px 0 8px 14px; border-left: 1px solid var(--borde); position: relative; }
  .evento::before { content: ''; position: absolute; left: -4px; top: 13px; width: 7px; height: 7px; border-radius: 50%; background: #06b6d4; }
  .evento.escalada::before { background: #8b5cf6; }
  .evento.accion::before { background: #f59e0b; }
  .evento.herramienta_fallida::before { background: #ef4444; }
  .evento .h { font-family: ui-monospace, monospace; font-size: 10px; color: var(--texto2); }
  .evento .q { font-size: 10.5px; font-weight: 600; letter-spacing: .05em; text-transform: uppercase; margin-top: 1px; }
  .evento .d { font-size: 11px; color: var(--texto2); margin-top: 2px; }
  .eventos .vacio { font-size: 11.5px; color: var(--texto3); padding: 8px 0; }

  .telon { position: fixed; inset: 0; background: rgba(2,6,18,.6); backdrop-filter: blur(3px); border: 0; z-index: 40; }
  .detalle {
    position: fixed; top: 0; right: 0; height: 100%; width: 440px; z-index: 41;
    background: #0f172a; color: #e6f1ff; border-left: 1px solid var(--c);
    box-shadow: -24px 0 56px rgba(0,0,0,.8); display: flex; flex-direction: column; overflow-y: auto;
  }
  .detalle header { display: flex; gap: 14px; align-items: center; padding: 18px 16px; border-bottom: 1px solid rgba(0,229,255,.14); position: relative; }
  .detalle header img { width: 84px; height: 84px; border-radius: 12px; object-fit: cover; border: 2px solid var(--c); }
  .detalle header h2 { font-size: 18px; margin: 0 0 3px; text-transform: capitalize; }
  .detalle header p { font-size: 11.5px; color: #8aa2c0; margin: 0 0 8px; }
  .detalle .cerrar { position: absolute; top: 12px; right: 12px; width: 28px; height: 28px; border-radius: 8px; border: 1px solid rgba(0,229,255,.14); background: #16233a; color: #8aa2c0; cursor: pointer; }
  .detalle .rejilla { display: grid; grid-template-columns: repeat(3, 1fr); }
  .detalle .rejilla div { padding: 12px 8px; text-align: center; border-right: 1px solid rgba(0,229,255,.1); border-bottom: 1px solid rgba(0,229,255,.1); }
  .detalle .rejilla b { display: block; font-family: ui-monospace, monospace; font-size: 17px; }
  .detalle .rejilla span { font-size: 8.5px; letter-spacing: .08em; color: #8aa2c0; text-transform: uppercase; }
  .detalle .rejilla .rojo b { color: #ef4444; }
  .detalle .bloque { padding: 14px 16px; border-bottom: 1px solid rgba(0,229,255,.1); }
  .detalle .bloque h3 { font-family: ui-monospace, monospace; font-size: 10px; letter-spacing: .14em; color: #8aa2c0; text-transform: uppercase; margin: 0 0 8px; }
  .detalle .bloque p { font-size: 12.5px; line-height: 1.55; margin: 0; color: #cfe0f5; }
  .detalle .bloque code { font-family: ui-monospace, monospace; font-size: 11.5px; color: var(--c); }
  .detalle .tz { color: #47607f; }
  .detalle footer { margin-top: auto; padding: 14px 16px; display: flex; gap: 10px; }


  .identidad {
    display: flex; align-items: center; gap: 14px; padding: 9px 16px;
    border-bottom: 1px solid var(--borde); font-size: 11px; color: var(--texto2);
  }
  .identidad .marca { font-weight: 700; letter-spacing: .16em; color: var(--texto); display: flex; align-items: center; gap: 8px; }
  .identidad .marca b { font-weight: 500; letter-spacing: .18em; color: var(--texto2); }
  .identidad .marca i { width: 7px; height: 7px; border-radius: 50%; background: #00e5ff; box-shadow: 0 0 9px #00e5ff; }
  .identidad .tenant { font-family: ui-monospace, monospace; letter-spacing: .08em; padding: 3px 9px; border: 1px solid var(--borde); border-radius: 6px; text-transform: uppercase; }
  .identidad .sep { flex: 1; }
  .identidad .dato { font-family: ui-monospace, monospace; font-size: 10.5px; }
  .identidad .dato.rojo { color: #ef4444; }
  .identidad .reloj { font-family: ui-monospace, monospace; font-size: 11px; color: var(--texto); }
  .identidad .reloj em { color: var(--texto3); font-style: normal; }

  .placa .haciendo {
    font-size: 10px; color: var(--c); margin-top: 4px; line-height: 1.35;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }

  /* Un servicio externo con lo que se le pidio hoy. Anclado al borde y nunca
     sobre una estacion: es contexto, no protagonista. */
  .servicio {
    position: absolute; z-index: 2; width: 212px; padding: 7px 10px; border-radius: 9px;
    background: rgba(4,21,37,.92); border: 1px solid rgba(0,229,255,.3);
    font-family: ui-monospace, monospace; line-height: 1.45;
  }
  .servicio .t { font-size: 10px; color: #00e5ff; font-weight: 700; letter-spacing: .06em; }
  .servicio .d { font-size: 9px; color: var(--texto2); }
  .servicio.fallando { border-color: rgba(239,68,68,.55); }
  .servicio.fallando .t { color: #ef4444; }

  @keyframes latir { 0%, 100% { opacity: 1 } 50% { opacity: .55 } }
  @keyframes girar { to { transform: rotate(360deg) } }
  @media (prefers-reduced-motion: reduce) { * { animation: none !important } }
</style>
