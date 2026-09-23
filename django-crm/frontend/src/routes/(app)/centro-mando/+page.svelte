<script>
  /**
   * Centro de mando: que esta haciendo ahora cada agente del tenant.
   *
   * Todo sale de /centro-mando en el motor, que cuenta filas -- no hay ni un
   * dato simulado. Si el motor no responde, se dice; no se rellena con nada.
   *
   * POR QUE UNA REJILLA Y NO UNA SALA EN ANILLO
   * Hasta el 23/09/2026 los agentes se dibujaban en un anillo sobre un lienzo
   * escalado, con cada tarjeta colocada por coordenadas. Se veia mejor con
   * cuatro o cinco agentes y se rompia con ocho: las placas invadian el pod
   * del vecino y el texto largo se cortaba (una herramienta se llama
   * 'verificar_identidad_por_cedula'). Cada arreglo de radio movia el
   * problema a otro punto, porque cuantos agentes hay lo decide cada empresa
   * y no hay radio que sirva para todas.
   *
   * Con una rejilla, la clase entera de errores desaparece: no hay posiciones
   * que calcular ni solapes posibles, y cuatro agentes o doce se ven igual de
   * bien. Se pierde la metafora de la sala; se gana que siempre se lea.
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
  const ORDEN = { error: 0, procesando: 1, atendiendo: 2, disponible: 3 };
  const colorDe = (/** @type {any} */ a) => COLORES[/** @type {keyof typeof COLORES} */ (a.estado)] || '#8AA2C0';

  const totales = $derived(panorama?.totales || {});
  const eventos = $derived(panorama?.eventos || []);
  const servicios = $derived(panorama?.servicios || []);

  /* Primero quien tiene problemas, despues quien trabaja, al final quien esta
     libre: si hay algo que mirar, esta arriba a la izquierda. */
  const agentes = $derived(
    [...(panorama?.agentes || [])].sort((a, b) =>
      (ORDEN[/** @type {keyof typeof ORDEN} */ (a.estado)] ?? 9) -
      (ORDEN[/** @type {keyof typeof ORDEN} */ (b.estado)] ?? 9) ||
      (b.conversaciones || 0) - (a.conversaciones || 0))
  );

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

  /* Que el bloque llegue al fondo de la ventana sin recortar nada. Va como
     alto MINIMO y medido: si se fija el alto, un dia el contenido no cabe y
     se corta; y si se resta una constante a 100vh, el encabezado de la
     pagina cambia de alto con el ancho y queda hueco o sobra scroll. */
  function estirar() {
    const sala = document.querySelector('.sala');
    if (!sala) return;
    const arriba = sala.getBoundingClientRect().top + window.scrollY;
    sala.style.minHeight = Math.max(560, window.innerHeight - arriba - 14) + 'px';
  }

  onMount(() => {
    estirar();
    window.addEventListener('resize', estirar);
    // Cada 12 s, y solo con la pestana a la vista: refrescar en segundo plano
    // es pegarle a la base cada 12 s por cada pestana olvidada abierta.
    const t = setInterval(() => { if (!document.hidden) refrescar(); }, 12000);
    return () => {
      clearInterval(t);
      window.removeEventListener('resize', estirar);
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
      <div class="rejilla-envoltura">
        {#if servicios.length}
          <div class="servicios">
            <span class="et">Servicios usados hoy</span>
            {#each servicios as s}
              <span class="chip-servicio" class:fallando={s.fallos > 0}>
                <b>{s.herramienta}</b>
                {s.usos} usos · {ms(s.duracion_media_ms)}{s.fallos ? ` · ${s.fallos} fallos` : ''}
              </span>
            {/each}
          </div>
        {/if}

        <div class="rejilla">
          {#each agentes as a (a.nombre)}
            <button class="agente" style="--c:{colorDe(a)}" onclick={() => (seleccionado = a)}>
              <div class="pod">
                <img class="fondo" src={estacionDe(a)} alt="" />
                <div class="tinte" style="-webkit-mask-image:url({estacionDe(a)}); mask-image:url({estacionDe(a)})"></div>
                <img class="cara" src={avatarDe(a)} alt="" />
              </div>
              <div class="ficha">
                <div class="fila1">
                  <span class="nombre">{a.nombre.replaceAll('_', ' ')}</span>
                  <span class="chip"><i class:vivo={a.estado === 'procesando'}></i>{ROTULO[a.estado] || a.estado}</span>
                </div>
                <div class="cargo">{a.cargo || a.area || ''}</div>
                <div class="haciendo">{a.haciendo || ''}</div>
                <div class="datos">
                  <span>Conv <b>{a.conversaciones}</b></span>
                  {#if a.esperando_humano}<span class="ambar">Humano <b>{a.esperando_humano}</b></span>{/if}
                  {#if a.duracion_media_ms}<span>{ms(a.duracion_media_ms)}</span>{/if}
                </div>
              </div>
            </button>
          {/each}
        </div>
      </div>

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

      <div class="rejilla-cifras">
        <div><b>{seleccionado.conversaciones}</b><span>Activas (24 h)</span></div>
        <div><b>{seleccionado.abiertas_total}</b><span>Abiertas sin cerrar</span></div>
        <div><b>{seleccionado.esperando_humano}</b><span>Esperan persona</span></div>
        <div><b>{seleccionado.recibidas_hoy}</b><span>Recibidas hoy</span></div>
        <div><b>{seleccionado.llamadas_ventana}</b><span>Herramientas ({panorama.ventana_min} min)</span></div>
        <div class:rojo={seleccionado.fallos_ventana > 0}><b>{seleccionado.fallos_ventana}</b><span>Fallos recientes</span></div>
      </div>

      <div class="bloque">
        <h3>Ahora mismo</h3>
        <p>{seleccionado.haciendo || 'Sin actividad.'}</p>
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
    background-color: var(--fondo);
    background-image: radial-gradient(ellipse at 50% 0%, rgba(0,229,255,.16), transparent 60%);
    color: var(--texto);
    border: 1px solid var(--borde); border-radius: 14px; overflow: hidden;
    display: flex; flex-direction: column;
  }

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

  .cifras { display: grid; grid-template-columns: repeat(auto-fit, minmax(146px, 1fr)); border-bottom: 1px solid var(--borde); }
  .cifra { padding: 12px 16px; border-right: 1px solid var(--borde); }
  .cifra:last-child { border-right: 0; }
  .cifra .v { font-family: ui-monospace, monospace; font-size: 22px; font-weight: 700; line-height: 1; }
  .cifra .k { font-size: 10px; letter-spacing: .1em; color: var(--texto2); text-transform: uppercase; margin-top: 6px; }
  .cifra.ambar .v { color: #f59e0b; }

  .cuerpo { flex: 1; display: flex; min-height: 0; }
  .rejilla-envoltura { flex: 1; min-width: 0; display: flex; flex-direction: column; overflow-y: auto; padding: 14px; gap: 14px; }

  .servicios { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .servicios .et { font-size: 10px; letter-spacing: .12em; text-transform: uppercase; color: var(--texto2); margin-right: 4px; }
  .chip-servicio {
    font-family: ui-monospace, monospace; font-size: 10px; color: var(--texto2);
    border: 1px solid rgba(0,229,255,.28); border-radius: 8px; padding: 4px 9px;
    background: rgba(4,21,37,.6); white-space: nowrap;
  }
  .chip-servicio b { color: #00e5ff; font-weight: 700; margin-right: 6px; }
  .chip-servicio.fallando { border-color: rgba(239,68,68,.5); }
  .chip-servicio.fallando b { color: #ef4444; }

  /* auto-fill y no un numero fijo de columnas: cuantos agentes hay lo decide
     cada empresa, y el ancho disponible cambia con el menu lateral. */
  .rejilla { display: grid; grid-template-columns: repeat(auto-fill, minmax(236px, 1fr)); gap: 14px; align-content: start; }

  .agente {
    text-align: left; padding: 0; cursor: pointer; overflow: hidden;
    background: var(--panel); border: 1px solid var(--c); border-radius: 12px;
    transition: transform .15s, box-shadow .15s;
    display: flex; flex-direction: column;
  }
  .agente:hover { transform: translateY(-2px); box-shadow: 0 0 22px color-mix(in srgb, var(--c) 40%, transparent); }

  .pod { position: relative; height: 128px; overflow: hidden; background: #030a17; }
  .pod .fondo { position: absolute; left: 50%; top: 52%; width: 235px; transform: translate(-50%, -50%); }
  .pod .tinte {
    position: absolute; left: 50%; top: 52%; width: 235px; height: 235px; transform: translate(-50%, -50%);
    background: var(--c); opacity: .32; mix-blend-mode: color;
    -webkit-mask-size: 100% 100%; mask-size: 100% 100%;
  }
  .pod .cara {
    position: absolute; left: 50%; top: 46%; transform: translate(-50%, -50%);
    width: 62px; height: 62px; border-radius: 50%; object-fit: cover;
    border: 2px solid var(--c); box-shadow: 0 0 16px var(--c);
  }

  .ficha { padding: 10px 12px 12px; display: flex; flex-direction: column; gap: 3px; }
  .fila1 { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
  .nombre { font-size: 12.5px; font-weight: 700; letter-spacing: .05em; text-transform: uppercase; line-height: 1.25; }
  .cargo { font-size: 10.5px; color: var(--texto2); }
  .haciendo { font-size: 11px; color: var(--c); line-height: 1.35; margin-top: 3px; min-height: 30px; overflow-wrap: anywhere; }
  .datos { display: flex; gap: 10px; flex-wrap: wrap; font-family: ui-monospace, monospace; font-size: 10.5px; color: var(--texto2); margin-top: 2px; }
  .datos b { color: var(--texto); }
  .datos .ambar { color: #f59e0b; }

  .chip {
    font-family: ui-monospace, monospace; font-size: 8.5px; letter-spacing: .08em; font-weight: 700;
    padding: 2px 6px; border-radius: 5px; white-space: nowrap; color: var(--c);
    border: 1px solid var(--c); background: color-mix(in srgb, var(--c) 14%, transparent);
    display: inline-flex; align-items: center; gap: 5px; flex-shrink: 0;
  }
  .chip i { width: 6px; height: 6px; border-radius: 50%; background: var(--c); display: inline-block; }
  .chip i.vivo { animation: latir 1.6s infinite; }

  .eventos { flex: 0 0 318px; background: var(--panel); border-left: 1px solid var(--borde); display: flex; flex-direction: column; min-height: 0; }
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
  .evento .d { font-size: 11px; color: var(--texto2); margin-top: 2px; overflow-wrap: anywhere; }
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
  .detalle .rejilla-cifras { display: grid; grid-template-columns: repeat(3, 1fr); }
  .detalle .rejilla-cifras div { padding: 12px 8px; text-align: center; border-right: 1px solid rgba(0,229,255,.1); border-bottom: 1px solid rgba(0,229,255,.1); }
  .detalle .rejilla-cifras b { display: block; font-family: ui-monospace, monospace; font-size: 17px; }
  .detalle .rejilla-cifras span { font-size: 8.5px; letter-spacing: .08em; color: #8aa2c0; text-transform: uppercase; }
  .detalle .rejilla-cifras .rojo b { color: #ef4444; }
  .detalle .bloque { padding: 14px 16px; border-bottom: 1px solid rgba(0,229,255,.1); }
  .detalle .bloque h3 { font-family: ui-monospace, monospace; font-size: 10px; letter-spacing: .14em; color: #8aa2c0; text-transform: uppercase; margin: 0 0 8px; }
  .detalle .bloque p { font-size: 12.5px; line-height: 1.55; margin: 0; color: #cfe0f5; }
  .detalle .bloque code { font-family: ui-monospace, monospace; font-size: 11.5px; color: var(--c); }
  .detalle .tz { color: #47607f; }
  .detalle footer { margin-top: auto; padding: 14px 16px; display: flex; gap: 10px; }

  @keyframes latir { 0%, 100% { opacity: 1 } 50% { opacity: .55 } }
  @media (prefers-reduced-motion: reduce) { * { animation: none !important } }
</style>
