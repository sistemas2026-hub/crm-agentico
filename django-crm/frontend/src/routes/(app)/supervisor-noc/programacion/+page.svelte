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

  // Los materiales de la orden abierta. Viven aparte de 'ficha' porque son otra
  // llamada: la ficha se ve enseguida y esto llega despues, en vez de retrasar
  // las dos cosas hasta que la mas lenta termine.
  let materiales = $state(/** @type {any} */ (null));
  let cargandoMateriales = $state(false);
  let errorMateriales = $state(/** @type {string|null} */ (null));
  //: El kit del dia es de la PERSONA, no del trabajo. Apagado por defecto y con
  //: su propio rotulo cuando se enciende.
  let verCustodia = $state(false);

  // La bitácora de la intervención. Otra llamada más, por el mismo motivo que los
  // materiales: la ficha se ve enseguida y esto llega después.
  let bitacora = $state(/** @type {any} */ (null));
  let cargandoBitacora = $state(false);
  let errorBitacora = $state(/** @type {string|null} */ (null));

  // El reporte que se está escribiendo. `momento` null = no hay formulario abierto.
  let momento = $state(/** @type {string|null} */ (null));
  let respuestas = $state(/** @type {Record<string, any>} */ ({}));
  let erroresCampo = $state(/** @type {Record<string, string>} */ ({}));
  let guardandoReporte = $state(false);
  let avisoReporte = $state(/** @type {string|null} */ (null));
  //: La clave de idempotencia se fija al ABRIR el formulario, no al enviarlo: una
  //: nueva por intento sería un identificador único, no una clave idempotente, y
  //: un doble clic dejaría dos AVANCE idénticos en la bitácora.
  let claveReporte = $state('');
  //: Las dos preguntas del bloqueo, separadas a proposito (ver el markup).
  let bloqueoRequiereNoc = $state(false);
  let bloqueoDetiene = $state(true);

  // Los bloqueos vivos de la empresa, para los filtros de la bandeja. Se piden una
  // vez y se cruzan por id: así no hay que tocar la API de la jornada.
  let bloqueos = $state(/** @type {any[]} */ ([]));
  //: `bloqueada` y `requiere NOC` son dos preguntas distintas, y por eso son dos
  //: filtros. Un trabajo detenido esperando al cliente está bloqueado y NO es
  //: cosa del NOC; juntarlos llenaría esa bandeja de lo que esa mesa no resuelve.
  let filtroTrabado = $state(/** @type {null | 'bloqueados' | 'noc'} */ (null));

  // Resolver un bloqueo, desde la ficha.
  let resolviendo = $state(false);
  let queSeHizo = $state('');
  let rolQueResolvio = $state('');
  let avisoResolver = $state(/** @type {string|null} */ (null));
  let claveResolver = $state('');

  /** Los roles que puede haber destrabado. Los mismos que `BloqueoDeTrabajo.QUIENES`. */
  const ROLES_RESOLUCION = [
    { valor: 'noc', texto: 'NOC' },
    { valor: 'coordinacion', texto: 'Coordinación' },
    { valor: 'bodega', texto: 'Bodega' },
    { valor: 'tecnico', texto: 'El técnico' },
    { valor: 'cliente', texto: 'El cliente' },
    { valor: 'tercero', texto: 'Un tercero' },
    { valor: 'otro', texto: 'Otro' }
  ];

  // La salud del seguimiento, calculada por el backend. Acá NO se reconstruye la
  // regla: la diferencia entre «no reportó» y «no sé si tiene señal» es una
  // acusación, no un detalle de formato.
  let salud = $state(/** @type {any} */ ({ por_orden: {}, conteo: {}, evalua_la_sincronizacion: false }));
  //: El tercer y cuarto filtro. Separados de «Bloqueados» y «Requiere NOC», que
  //: contestan otra pregunta.
  let filtroSalud = $state(/** @type {null | 'vencido' | 'sin_contacto_reciente'} */ (null));

  /** El veredicto de una fila, o null si no aplica. */
  const saludDe = (ordenId) => salud.por_orden?.[ordenId] ?? null;

  /** El color de cada situación. Los nombres los pone el backend. */
  const CLASE_SALUD = {
    al_dia: '',
    vencido: 'snoc-insignia-error',
    sin_contacto_reciente: 'snoc-insignia-neutra',
    pausado_noc: 'snoc-insignia-variante',
    no_aplica: ''
  };

  /** El bloqueo vivo de una orden de la tabla, si tiene. */
  const bloqueoDe = (ordenId) => bloqueos.find((b) => b.orden_id === ordenId) ?? null;

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
        (!fPrioridad || String(l.prioridad) === fPrioridad) &&
        // DOS FILTROS DISTINTOS, y los dos dicen la verdad:
        //   'bloqueados' -> el trabajo está detenido, sea por lo que sea;
        //   'noc'        -> hace falta que alguien de esa mesa haga algo.
        // Un trabajo esperando al cliente entra en el primero y no en el segundo.
        (filtroTrabado !== 'bloqueados' || !!bloqueoDe(l.orden)) &&
        (filtroTrabado !== 'noc' || bloqueoDe(l.orden)?.requiere_noc === true) &&
        // Y los dos del seguimiento, que contestan otra pregunta: no si está
        // detenido, sino si está reportando.
        (!filtroSalud || saludDe(l.orden)?.tipo === filtroSalud)
    )
  );

  /** Cuántos hay en cada uno. Se muestran para que el filtro no parezca roto cuando da cero. */
  const cuentaTrabados = $derived.by(() => {
    const ids = new Set(lineas.map((/** @type {any} */ l) => l.orden));
    const míos = bloqueos.filter((b) => ids.has(b.orden_id));
    return { bloqueados: míos.length, noc: míos.filter((b) => b.requiere_noc).length };
  });

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
    void cargarMateriales(ordenId);
    void cargarBitacora(ordenId);
    void cargarBloqueos();
    claveResolver = `crm-resolver-${ordenId}-${Date.now()}`;
  }

  /**
   * Que material toco esta orden.
   *
   * No suma ni calcula: el backend devuelve movimientos que YA existen,
   * agrupados por lo que significan. Un total en esta pantalla seria una segunda
   * contabilidad compitiendo con el libro.
   *
   * @param {string} ordenId
   */
  async function cargarMateriales(ordenId) {
    materiales = null;
    errorMateriales = null;
    cargandoMateriales = true;
    try {
      const q = verCustodia ? '?custodia=1' : '';
      const r = await fetch(`/api/supervisor-noc/ordenes/${ordenId}/materiales${q}`);
      const cuerpo = await r.json().catch(() => ({}));
      if (!r.ok) errorMateriales = cuerpo?.error ?? 'No fue posible consultar los materiales.';
      else materiales = cuerpo;
    } catch {
      errorMateriales = 'No fue posible consultar los materiales: el servicio no respondió.';
    } finally {
      cargandoMateriales = false;
    }
  }

  /**
   * La bitácora de la orden: la línea de tiempo y los formularios vigentes.
   *
   * @param {string} ordenId
   */
  async function cargarBitacora(ordenId) {
    bitacora = null;
    errorBitacora = null;
    cargandoBitacora = true;
    try {
      const r = await fetch(`/api/supervisor-noc/ordenes/${ordenId}/seguimiento`);
      const cuerpo = await r.json().catch(() => ({}));
      if (!r.ok) errorBitacora = cuerpo?.error ?? 'No fue posible consultar la bitácora.';
      else bitacora = cuerpo;
    } catch {
      errorBitacora = 'No fue posible consultar la bitácora: el servicio no respondió.';
    } finally {
      cargandoBitacora = false;
    }
  }

  /**
   * Abre el formulario de un momento. Los campos salen del tipo de trabajo, así
   * que esta pantalla no sabe cuáles son hasta que el backend los manda.
   *
   * @param {string} cual
   */
  function abrirReporte(cual) {
    momento = cual;
    respuestas = {};
    erroresCampo = {};
    avisoReporte = null;
    claveReporte = `crm-${bitacora?.orden_id ?? 'x'}-${cual}-${Date.now()}`;
    bloqueoRequiereNoc = false;
    bloqueoDetiene = true;
  }

  function cerrarReporte() {
    momento = null;
    respuestas = {};
    erroresCampo = {};
  }

  /** Manda el reporte. Un 422 vuelve con los errores POR CAMPO. */
  async function enviarReporte() {
    if (!momento || !bitacora?.orden_id) return;
    guardandoReporte = true;
    erroresCampo = {};
    avisoReporte = null;
    try {
      const r = await fetch(`/api/supervisor-noc/ordenes/${bitacora.orden_id}/seguimiento`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': claveReporte },
        body: JSON.stringify({
          momento,
          respuestas,
          // Solo significan algo en el bloqueo; el backend ignora el resto.
          ...(momento === 'bloqueo'
            ? { requiere_noc: bloqueoRequiereNoc, detener: bloqueoDetiene }
            : {})
        })
      });
      const cuerpo = await r.json().catch(() => ({}));
      if (!r.ok) {
        erroresCampo = cuerpo?.campos ?? {};
        avisoReporte = cuerpo?.error ?? 'El reporte no se pudo guardar.';
        return;
      }
      const ordenId = bitacora.orden_id;
      const eraBloqueo = momento === 'bloqueo';
      cerrarReporte();
      // Los bloqueos tambien: si no, alguien registra un bloqueo y los contadores
      // de SU PROPIA bandeja siguen en cero hasta recargar la pagina. Medido en el
      // laboratorio justo despues de escribir los filtros.
      //
      // Y si el bloqueo detuvo el trabajo, el estado operativo de la TABLA viene
      // del `load` del servidor: sin invalidar, la fila sigue mostrando el estado
      // anterior.
      await Promise.all([
        cargarBitacora(ordenId),
        cargarBloqueos(),
        cargarSalud(),
        ...(eraBloqueo ? [invalidateAll()] : [])
      ]);
    } catch {
      avisoReporte = 'El reporte no se pudo guardar: el servicio no respondió.';
    } finally {
      guardandoReporte = false;
    }
  }

  /** Los campos del momento abierto, tal como los declaró el tipo de trabajo. */
  const camposDelMomento = $derived.by(() => {
    if (!momento || !bitacora?.formularios) return [];
    return bitacora.formularios[momento]?.campos ?? [];
  });

  // La tabla necesita los bloqueos antes de que alguien abra una ficha: los
  // filtros y las marcas de fila se dibujan con esto.
  $effect(() => {
    void data.dia;
    void cargarBloqueos();
    void cargarSalud();
  });

  /** La salud del seguimiento de la jornada. Una llamada para toda la tabla. */
  async function cargarSalud() {
    try {
      const r = await fetch('/api/supervisor-noc/seguimiento-salud');
      const cuerpo = await r.json().catch(() => ({}));
      salud = r.ok
        ? cuerpo
        : { por_orden: {}, conteo: {}, evalua_la_sincronizacion: false };
    } catch {
      // La tabla se dibuja igual, sin la columna: es información adicional.
      salud = { por_orden: {}, conteo: {}, evalua_la_sincronizacion: false };
    }
  }

  /** Los bloqueos abiertos de la empresa. Una sola llamada para toda la tabla. */
  async function cargarBloqueos() {
    try {
      const r = await fetch('/api/supervisor-noc/bloqueos');
      const cuerpo = await r.json().catch(() => ({}));
      bloqueos = r.ok ? (cuerpo?.bloqueos ?? []) : [];
    } catch {
      // Sin esto la tabla se dibuja igual, solo sin las marcas de bloqueo: es
      // información adicional, no la razón por la que alguien abrió la pantalla.
      bloqueos = [];
    }
  }

  /** Destraba el trabajo. El estado al que vuelve lo decidió el bloqueo al abrirse. */
  async function resolverElBloqueo() {
    const ordenId = bitacora?.orden_id ?? ficha?.id;
    if (!ordenId) return;
    if (!queSeHizo.trim()) {
      avisoResolver = 'Decí qué se hizo para destrabarlo.';
      return;
    }
    resolviendo = true;
    avisoResolver = null;
    try {
      const r = await fetch(`/api/supervisor-noc/ordenes/${ordenId}/bloqueo/resolver`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': claveResolver },
        body: JSON.stringify({ que_se_hizo: queSeHizo, resuelto_por_rol: rolQueResolvio })
      });
      const cuerpo = await r.json().catch(() => ({}));
      if (!r.ok) {
        avisoResolver = cuerpo?.error ?? 'No se pudo resolver el bloqueo.';
        return;
      }
      queSeHizo = '';
      rolQueResolvio = '';
      // `invalidateAll` tambien: el estado operativo que muestra la TABLA viene
      // del `load` del servidor, y sin esto la fila sigue diciendo "bloqueada"
      // despues de destrabar. Medido en el laboratorio.
      await Promise.all([
        cargarBloqueos(),
        cargarBitacora(ordenId),
        cargarSalud(),
        invalidateAll()
      ]);
      // La ficha muestra el estado operativo: se vuelve a pedir para que no quede
      // diciendo «bloqueada» después de destrabar.
      void abrirOrden(ordenId);
    } catch {
      avisoResolver = 'No se pudo resolver el bloqueo: el servicio no respondió.';
    } finally {
      resolviendo = false;
    }
  }

  /** Enciende o apaga el kit del dia, y vuelve a pedirlo. */
  function alternarCustodia() {
    verCustodia = !verCustodia;
    const id = materiales?.orden_id ?? ficha?.id;
    if (id) void cargarMateriales(id);
  }

  /**
   * Los cuatro bloques, en el orden en que se leen. Cada uno dice de donde sale
   * su dato; el pie existe para que nadie tenga que adivinarlo.
   */
  const GRUPOS_MATERIAL = [
    {
      clave: 'comprometido',
      titulo: 'Comprometido para esta orden',
      pie: 'Reservado contra una bodega. Es lo unico que de verdad esta asignado a este trabajo.'
    },
    { clave: 'consumido', titulo: 'Consumido en esta orden', pie: '' },
    { clave: 'devuelto', titulo: 'Devuelto', pie: '' },
    {
      clave: 'otros',
      titulo: 'Otros movimientos de esta orden',
      pie: 'Ajustes, traslados y bajas que alguien ato a esta orden.'
    }
  ];

  /** Una cantidad legible, con la unidad del material. */
  function conUnidad(linea) {
    const n = Number(linea?.cantidad ?? 0);
    const texto = Number.isFinite(n)
      ? n.toLocaleString('es-CO', { maximumFractionDigits: 3 })
      : String(linea?.cantidad ?? '—');
    return `${texto} ${linea?.material?.unidad ?? ''}`.trim();
  }

  /** @param {string} profileId */
  async function abrirPersona(profileId) {
    drawer = 'persona';
    ficha = null;
    materiales = null;
    errorMateriales = null;
    bitacora = null;
    errorBitacora = null;
    momento = null;
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
          <a class="snoc-pildora" href="/supervisor-noc/cuadrillas">Cuadrillas</a>
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

                <!--
                  Los dos filtros de trabajos trabados. Van ACA, en la bandeja que
                  ya existe, y no en una pantalla nueva: dos lugares donde el NOC
                  mira trabajos es peor que uno incomodo. Si el volumen demuestra
                  que hace falta una cola dedicada, ahi se separa.
                -->
                <button
                  type="button"
                  class="snoc-pildora"
                  aria-pressed={filtroTrabado === 'bloqueados'}
                  style={filtroTrabado === 'bloqueados' ? 'font-weight:700;' : ''}
                  onclick={() =>
                    (filtroTrabado = filtroTrabado === 'bloqueados' ? null : 'bloqueados')}
                  title="Trabajos detenidos, por cualquier motivo"
                >
                  Bloqueados {cuentaTrabados.bloqueados}
                </button>
                <button
                  type="button"
                  class="snoc-pildora"
                  aria-pressed={filtroSalud === 'vencido'}
                  style={filtroSalud === 'vencido' ? 'font-weight:700;' : ''}
                  onclick={() => (filtroSalud = filtroSalud === 'vencido' ? null : 'vencido')}
                  title="Hay contacto reciente del dispositivo y no reportó. Eso sí es un atraso."
                >
                  Seguimiento vencido {salud.conteo?.vencido ?? 0}
                </button>
                <!--
                  Este filtro solo aparece si el sistema PUEDE contestar esa
                  pregunta. Mientras la app no tenga latido regular, la ausencia de
                  contacto no distingue "sin señal" de "app cerrada en el bolsillo",
                  y mostrar un filtro que nunca encuentra nada haria pensar que esta
                  roto. Se enciende con `minutos_contacto_reciente` en la config.
                -->
                {#if salud.evalua_la_sincronizacion}
                  <button
                    type="button"
                    class="snoc-pildora"
                    aria-pressed={filtroSalud === 'sin_contacto_reciente'}
                    style={filtroSalud === 'sin_contacto_reciente' ? 'font-weight:700;' : ''}
                    onclick={() =>
                      (filtroSalud =
                        filtroSalud === 'sin_contacto_reciente' ? null : 'sin_contacto_reciente')}
                    title="El dispositivo no aparece: no se puede saber si hay atraso de reporte."
                  >
                    Sin sincronización {salud.conteo?.sin_contacto_reciente ?? 0}
                  </button>
                {/if}
                <button
                  type="button"
                  class="snoc-pildora"
                  aria-pressed={filtroTrabado === 'noc'}
                  style={filtroTrabado === 'noc' ? 'font-weight:700;' : ''}
                  onclick={() => (filtroTrabado = filtroTrabado === 'noc' ? null : 'noc')}
                  title="Los que esperan una acción del NOC. No es lo mismo que estar bloqueado."
                >
                  Requiere NOC {cuentaTrabados.noc}
                </button>
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
                      <th>Seguimiento</th>
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
                        <td class="snoc-body-sm">
                          {l.estado_orden ?? '—'}
                          {#if bloqueoDe(l.orden)}
                            {@const b = bloqueoDe(l.orden)}
                            <!-- Detenido y «cosa del NOC» son dos marcas distintas
                                 porque son dos hechos distintos. -->
                            {#if b.detuvo_el_trabajo}
                              <span class="snoc-insignia snoc-insignia-error"
                                    title={`Detenido hace ${b.minutos_detenido} min. Vuelve a ${b.estado_operativo_anterior || '—'}.`}>
                                detenido
                              </span>
                            {:else}
                              <span class="snoc-insignia snoc-insignia-variante"
                                    title="Bloqueo reportado; el estado operativo no cambió.">
                                bloqueo reportado
                              </span>
                            {/if}
                            {#if b.requiere_noc}
                              <span class="snoc-insignia snoc-insignia-variante">NOC</span>
                            {/if}
                          {/if}
                        </td>
                        <td>
                          {#if saludDe(l.orden)}
                            {@const sa = saludDe(l.orden)}
                            <span class="snoc-insignia {CLASE_SALUD[sa.tipo] ?? ''}">
                              {sa.etiqueta}
                            </span>
                            {#if sa.tipo === 'vencido'}
                              <span class="snoc-mono-sm snoc-tenue">+{sa.minutos_vencido} min</span>
                            {:else if sa.minutos_desde_la_referencia != null}
                              <span class="snoc-mono-sm snoc-tenue">
                                {sa.minutos_desde_la_referencia} min
                              </span>
                            {/if}
                          {:else}
                            <span class="snoc-tenue">—</span>
                          {/if}
                        </td>
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

            <!--
              LA BITACORA DE LA INTERVENCION

              Una sola linea de tiempo: los cuatro momentos que reporta quien
              trabaja, mezclados con los eventos que el sistema ya escribia. Dos
              listas separadas obligarian a cruzarlas a mano para saber que paso
              antes, la devolucion del supervisor o el ultimo avance.

              Los campos de cada formulario los declara el TIPO DE TRABAJO y
              llegan del backend. Esta pantalla no sabe cuales son: por eso la
              empresa siguiente trae los suyos sin tocar codigo.
            -->
            <div class="snoc-pila-xs">
              <span class="snoc-label-sm snoc-tenue" style="text-transform:uppercase;">
                Seguimiento de la intervención
              </span>

              <!--
                LA SALUD DEL SEGUIMIENTO.

                Viene calculada del backend, etiqueta incluida. Aca no se decide
                nada: "no reporto" y "no se si tiene señal" son dos afirmaciones
                distintas y una de las dos acusa a una persona.
              -->
              {#if bitacora?.salud && bitacora.salud.tipo !== 'no_aplica'}
                {@const sa = bitacora.salud}
                <div class="snoc-analisis {sa.tipo === 'vencido' ? 'snoc-faltante' : 'snoc-observado'}">
                  <span class="snoc-insignia {CLASE_SALUD[sa.tipo] ?? ''}">{sa.etiqueta}</span>
                  {#if sa.tipo === 'vencido'}
                    <span class="snoc-mono-sm">hace {sa.minutos_vencido} min que venció</span>
                  {/if}
                  <p class="snoc-body" style="margin:0;">{sa.motivo}</p>
                  <div class="snoc-meta">
                    {#if sa.referencia}
                      <div>
                        <span>Última actualización:</span>
                        <span class="snoc-mono-sm">
                          {fecha(sa.referencia)} · hace {sa.minutos_desde_la_referencia} min
                        </span>
                      </div>
                    {/if}
                    {#if sa.vence_en}
                      <div>
                        <span>Debía actualizar antes de:</span>
                        <span class="snoc-mono-sm">{fecha(sa.vence_en)}</span>
                      </div>
                    {/if}
                    {#if sa.ultimo_contacto}
                      <div>
                        <span>Última sincronización conocida:</span>
                        <span class="snoc-mono-sm">
                          {fecha(sa.ultimo_contacto)} · hace {sa.minutos_desde_el_contacto} min
                        </span>
                      </div>
                    {/if}
                    <div>
                      <span>Ventana de la empresa:</span>
                      <span class="snoc-mono-sm">{sa.minutos_para_reportar} min</span>
                    </div>
                  </div>
                  {#if !sa.evalua_la_sincronizacion}
                    <span class="snoc-body-sm snoc-tenue">
                      La sincronización del dispositivo <strong>no se evalúa</strong>: la app de
                      campo no tiene un latido regular, así que la falta de contacto no distingue
                      «sin señal» de «app cerrada». Se enciende configurando los minutos de
                      contacto reciente.
                    </span>
                  {/if}
                </div>
              {/if}

              {#if cargandoBitacora}
                <p class="snoc-body-sm snoc-tenue" style="margin:0;">Leyendo la bitácora…</p>
              {:else if errorBitacora}
                <p class="snoc-body-sm snoc-error-txt" style="margin:0;">{errorBitacora}</p>
              {:else if bitacora}
                {#if bitacora.ultimo_reporte}
                  <div class="snoc-meta">
                    <div>
                      <span>Último reporte:</span>
                      <span class="snoc-insignia">{bitacora.ultimo_reporte.etiqueta}</span>
                    </div>
                    <div>
                      <span>Lo recibimos:</span>
                      <span class="snoc-mono-sm">
                        {fecha(bitacora.ultimo_reporte.recibido_en)}
                        {#if bitacora.ultimo_reporte.minutos_desde_que_lo_recibimos != null}
                          · hace {bitacora.ultimo_reporte.minutos_desde_que_lo_recibimos} min
                        {/if}
                      </span>
                    </div>
                    {#if bitacora.ultimo_reporte.capturado_en_dispositivo}
                      <div>
                        <span>Lo escribió en el teléfono:</span>
                        <span class="snoc-mono-sm">
                          {fecha(bitacora.ultimo_reporte.capturado_en_dispositivo)}
                        </span>
                      </div>
                    {/if}
                  </div>
                {:else}
                  <p class="snoc-body-sm snoc-tenue" style="margin:0;">
                    Todavía no hay ningún reporte de campo en esta orden.
                  </p>
                {/if}

                <!--
                  EL BLOQUEO VIVO, si hay.

                  Dice dos cosas que NO son lo mismo:
                    - si el trabajo esta DETENIDO (estado operativo `bloqueada`);
                    - si hace falta que alguien del NOC haga algo.
                  Un trabajo detenido esperando al cliente esta bloqueado y no es
                  cosa del NOC. Ver campo/bloqueos.py.
                -->
                {#if bitacora.bloqueo_abierto}
                  {@const bloq = bitacora.bloqueo_abierto}
                  <div class="snoc-analisis snoc-faltante">
                    <span class="snoc-insignia snoc-insignia-error">
                      {bloq.detuvo_el_trabajo ? 'Trabajo detenido' : 'Bloqueo reportado'}
                    </span>
                    {#if bloq.requiere_noc}
                      <span class="snoc-insignia snoc-insignia-variante">Requiere NOC</span>
                    {/if}

                    <div class="snoc-meta">
                      {#if bloq.detuvo_el_trabajo}
                        <div>
                          <span>Detenido desde:</span>
                          <span class="snoc-mono-sm">
                            {fecha(bloq.abierto_en)} · {bloq.minutos_detenido} min
                          </span>
                        </div>
                        <div>
                          <span>Vuelve a:</span>
                          <span class="snoc-insignia">{bloq.estado_operativo_anterior || '—'}</span>
                        </div>
                      {/if}
                      {#if bloq.categoria}
                        <div><span>Categoría:</span><span class="snoc-body-sm">{bloq.categoria}</span></div>
                      {/if}
                    </div>

                    {#if !bloq.detuvo_el_trabajo}
                      <p class="snoc-body" style="margin:0;">
                        <strong>El estado operativo no fue cambiado.</strong> Se reportó el bloqueo y
                        el trabajo sigue en <span class="snoc-insignia">{bitacora.estado_operativo}</span>:
                        son dos hechos distintos y acá solo pasó el primero.
                      </p>
                    {/if}
                    {#if bloq.motivo}
                      <p class="snoc-body" style="margin:0;">{bloq.motivo}</p>
                    {/if}
                    {#if bloq.necesita}
                      <p class="snoc-body-sm snoc-tenue" style="margin:0;">
                        Hace falta: {bloq.necesita}
                      </p>
                    {/if}

                    <!-- Destrabarlo. El estado al que vuelve ya lo decidio el
                         bloqueo cuando se abrio: esta pantalla no lo elige. -->
                    <div class="snoc-campo">
                      <label class="snoc-label-sm" for="bloq-que-se-hizo">
                        Qué se hizo para destrabarlo <span aria-hidden="true">*</span>
                      </label>
                      <textarea
                        id="bloq-que-se-hizo"
                        class="snoc-buscador-campo"
                        rows="2"
                        bind:value={queSeHizo}
                      ></textarea>
                    </div>
                    <div class="snoc-campo">
                      <label class="snoc-label-sm" for="bloq-rol">Quién lo resolvió</label>
                      <select id="bloq-rol" class="snoc-buscador-campo" bind:value={rolQueResolvio}>
                        <option value="">Sin especificar</option>
                        {#each ROLES_RESOLUCION as rol (rol.valor)}
                          <option value={rol.valor}>{rol.texto}</option>
                        {/each}
                      </select>
                    </div>
                    {#if avisoResolver}
                      <p class="snoc-body-sm snoc-error-txt" style="margin:0;">{avisoResolver}</p>
                    {/if}
                    <div class="snoc-acciones">
                      <button
                        type="button"
                        class="snoc-btn snoc-btn-primario"
                        disabled={resolviendo}
                        onclick={resolverElBloqueo}
                      >
                        {resolviendo ? 'Resolviendo…' : 'Resolver el bloqueo'}
                      </button>
                    </div>
                  </div>
                {/if}

                <!-- Lo que la bitacora tiene de raro. No bloquea nada: avisa. -->
                {#each bitacora.avisos ?? [] as aviso, i (i)}
                  <div class="snoc-analisis snoc-faltante">
                    <span class="snoc-insignia snoc-insignia-error">Falta parte de la historia</span>
                    <p class="snoc-body" style="margin:0;">{aviso}</p>
                  </div>
                {/each}

                <!-- Los cuatro momentos. INICIO solo aparece si no hubo uno. -->
                <div class="snoc-acciones">
                  {#if !(bitacora.momentos_registrados ?? []).includes('inicio_campo')}
                    <button type="button" class="snoc-btn snoc-btn-primario"
                            onclick={() => abrirReporte('inicio')}>
                      Registrar inicio
                    </button>
                  {/if}
                  <button type="button" class="snoc-btn" onclick={() => abrirReporte('avance')}>
                    Registrar avance
                  </button>
                  {#if !bitacora.bloqueo_abierto}
                    <button type="button" class="snoc-btn" onclick={() => abrirReporte('bloqueo')}>
                      Registrar bloqueo
                    </button>
                  {/if}
                  <button type="button" class="snoc-btn" onclick={() => abrirReporte('cierre')}>
                    Cerrar intervención
                  </button>
                </div>

                {#if momento}
                  <div class="snoc-analisis snoc-observado">
                    <span class="snoc-insignia snoc-insignia-variante">
                      {bitacora.formularios?.[momento]?.tipo_evento === 'cierre_campo'
                        ? 'Cierre de intervención'
                        : `Nuevo ${momento}`}
                    </span>

                    {#if bitacora.formularios?.[momento]?.declarado_por_el_tipo_de_trabajo === false}
                      <p class="snoc-body-sm snoc-tenue" style="margin:0;">
                        Este tipo de trabajo no declara campos propios para este momento, así que
                        se pide el mínimo. Los campos se configuran en el tipo de trabajo, no acá.
                      </p>
                    {/if}

                    {#each camposDelMomento as campo (campo.id)}
                      <div class="snoc-campo">
                        <label class="snoc-label-sm" for={`rep-${campo.id}`}>
                          {campo.titulo ?? campo.id}
                          {#if campo.reglas?.required}<span aria-hidden="true"> *</span>{/if}
                        </label>

                        {#if campo.tipo === 'booleano'}
                          <select
                            id={`rep-${campo.id}`}
                            class="snoc-buscador-campo"
                            bind:value={respuestas[campo.id]}
                          >
                            <option value={undefined}>Elegí una opción</option>
                            <option value={true}>Sí</option>
                            <option value={false}>No</option>
                          </select>
                        {:else if campo.tipo === 'seleccion'}
                          <select
                            id={`rep-${campo.id}`}
                            class="snoc-buscador-campo"
                            bind:value={respuestas[campo.id]}
                          >
                            <option value={undefined}>Elegí una opción</option>
                            {#each campo.reglas?.options ?? [] as opcion (opcion)}
                              <option value={opcion}>{opcion}</option>
                            {/each}
                          </select>
                        {:else if campo.tipo === 'entero' || campo.tipo === 'decimal'}
                          <!-- `step` sale del tipo: un decimal con step=1 hace que el
                               navegador rechace 37,5 con un mensaje que no explica nada. -->
                          <input
                            id={`rep-${campo.id}`}
                            class="snoc-buscador-campo"
                            type="number"
                            step={campo.tipo === 'entero' ? '1' : 'any'}
                            bind:value={respuestas[campo.id]}
                          />
                        {:else if campo.tipo === 'fecha'}
                          <input
                            id={`rep-${campo.id}`}
                            class="snoc-buscador-campo"
                            type="date"
                            bind:value={respuestas[campo.id]}
                          />
                        {:else}
                          <textarea
                            id={`rep-${campo.id}`}
                            class="snoc-buscador-campo"
                            rows="2"
                            bind:value={respuestas[campo.id]}
                          ></textarea>
                        {/if}

                        {#if campo.declaracion}
                          <span class="snoc-body-sm snoc-tenue">
                            Esto queda registrado como algo que <strong>vos afirmás</strong>, con
                            tu nombre y la hora. El sistema no puede comprobarlo.
                          </span>
                        {/if}
                        {#if erroresCampo[campo.id]}
                          <span class="snoc-body-sm snoc-error-txt">{erroresCampo[campo.id]}</span>
                        {/if}
                      </div>
                    {/each}

                    {#if avisoReporte}
                      <p class="snoc-body-sm snoc-error-txt" style="margin:0;">{avisoReporte}</p>
                    {/if}

                    <div class="snoc-acciones">
                      <button
                        type="button"
                        class="snoc-btn snoc-btn-primario"
                        disabled={guardandoReporte}
                        onclick={enviarReporte}
                      >
                        {guardandoReporte ? 'Guardando…' : 'Guardar el reporte'}
                      </button>
                      <button type="button" class="snoc-btn" onclick={cerrarReporte}>
                        Cancelar
                      </button>
                    </div>

                    {#if momento === 'bloqueo'}
                      <!--
                        Las dos casillas son las dos preguntas que no son la misma.
                        `requiere_noc` viaja aparte de las respuestas del formulario
                        a proposito: el campo del esquema lo nombra cada empresa
                        como quiere, y un filtro que dependa de ese nombre deja de
                        funcionar con la segunda.
                      -->
                      <div class="snoc-campo">
                        <label class="snoc-label-sm">
                          <input type="checkbox" bind:checked={bloqueoRequiereNoc} />
                          Hace falta que el NOC haga algo
                        </label>
                        <span class="snoc-body-sm snoc-tenue">
                          Esto lo pone en la bandeja «Requiere NOC». Un trabajo detenido esperando
                          al cliente o al material está bloqueado igual, pero no es de esa mesa.
                        </span>
                      </div>
                      <div class="snoc-campo">
                        <label class="snoc-label-sm">
                          <input type="checkbox" bind:checked={bloqueoDetiene} />
                          Detener el trabajo
                        </label>
                        <span class="snoc-body-sm snoc-tenue">
                          Si se destilda, el bloqueo queda anotado y el estado operativo
                          <strong>no cambia</strong>: algo demora pero se puede seguir.
                        </span>
                      </div>
                    {/if}
                  </div>
                {/if}

                <!-- La linea de tiempo. Los de seguimiento traen su detalle leido
                     con el esquema que tenian cuando se capturaron. -->
                {#if (bitacora.eventos ?? []).length}
                  <div class="snoc-historial">
                    {#each bitacora.eventos as ev (ev.id)}
                      <div class="snoc-pila-xs" style="padding-block:6px;">
                        <div>
                          <span class="snoc-mono-sm">{fecha(ev.recibido_en)}</span>
                          <span class="snoc-insignia {ev.es_seguimiento ? '' : 'snoc-insignia-variante'}">
                            {ev.etiqueta}
                          </span>
                          {#if ev.quien}
                            <span class="snoc-body-sm snoc-tenue">· {ev.quien}</span>
                          {/if}
                        </div>

                        {#if ev.es_seguimiento}
                          {#each ev.detalle ?? [] as d (d.id)}
                            <div class="snoc-body-sm">
                              <span class="snoc-tenue">{d.titulo}:</span>
                              <span>{d.valor === true ? 'Sí' : d.valor === false ? 'No' : d.valor}</span>
                              {#if ev.declaraciones?.[d.id]}
                                <span class="snoc-body-sm snoc-tenue">
                                  — lo afirmó {ev.declaraciones[d.id].declarado_por_nombre ?? 'una persona'}
                                </span>
                              {/if}
                            </div>
                          {/each}
                          {#if ev.capturado_en_dispositivo}
                            <span class="snoc-body-sm snoc-tenue">
                              Escrito en el teléfono a las {fecha(ev.capturado_en_dispositivo)}
                            </span>
                          {/if}
                        {:else}
                          <!--
                            Los hechos del sistema. `datos` trae SOLO las claves que
                            el backend decidio exponer para ese tipo: es una lista
                            blanca alla, no un volcado del JSON.
                          -->
                          {#if ev.datos?.que_se_hizo}
                            <div class="snoc-body-sm">
                              <span>{ev.datos.que_se_hizo}</span>
                              {#if ev.datos.resuelto_por_rol}
                                <span class="snoc-body-sm snoc-tenue">
                                  — lo resolvió {ev.datos.resuelto_por_rol}
                                </span>
                              {/if}
                            </div>
                          {/if}
                          {#if ev.datos?.minutos_detenido != null}
                            <span class="snoc-body-sm snoc-tenue">
                              Estuvo detenido {ev.datos.minutos_detenido} min
                              {#if ev.datos.volvio_a}· volvió a {ev.datos.volvio_a}{/if}
                            </span>
                          {/if}
                          {#if ev.estado_nuevo}
                            <span class="snoc-body-sm snoc-tenue">
                              {ev.estado_anterior ?? '—'} → {ev.estado_nuevo}
                            </span>
                          {/if}
                        {/if}
                      </div>
                    {/each}
                  </div>
                {/if}
              {/if}
            </div>

            <!--
              MATERIALES DE ESTA ORDEN

              Cada bloque dice de donde sale, porque los cuatro significan cosas
              distintas y mezclarlos es la forma de que alguien lea "150 m" como
              gastados en una casa cuando eran el kit de todo el dia.

              No hay totales a proposito: la existencia sale del libro
              --existencia(ubicacion, material)-- y una suma aca seria una segunda
              contabilidad.
            -->
            <div class="snoc-pila-xs">
              <span class="snoc-label-sm snoc-tenue" style="text-transform:uppercase;">
                Materiales de esta orden
              </span>

              {#if cargandoMateriales}
                <p class="snoc-body-sm snoc-tenue" style="margin:0;">Consultando movimientos…</p>
              {:else if errorMateriales}
                <p class="snoc-body-sm snoc-error-txt" style="margin:0;">{errorMateriales}</p>
              {:else if materiales}
                {#if materiales.con_novedad > 0}
                  <div class="snoc-analisis snoc-faltante">
                    <span class="snoc-insignia snoc-insignia-error">
                      {materiales.con_novedad} movimiento(s) con novedad
                    </span>
                    <p class="snoc-body" style="margin:0;">
                      Un <strong>descuadre</strong> o un <strong>conflicto</strong> quedó registrado
                      en esta orden. El hecho se respeta —no se corrige solo—: alguien de bodega
                      tiene que mirarlo.
                    </p>
                  </div>
                {/if}

                {#if !materiales.hay_algo}
                  <p class="snoc-body-sm snoc-tenue" style="margin:0;">
                    Esta orden todavía no tiene material reservado ni consumido.
                  </p>
                {/if}

                {#each GRUPOS_MATERIAL as grupo (grupo.clave)}
                  {#if (materiales[grupo.clave] ?? []).length}
                    <div class="snoc-pila-xs">
                      <span class="snoc-label-sm">{grupo.titulo}</span>
                      <div class="snoc-tabla-caja">
                        <table class="snoc-tabla">
                          <thead>
                            <tr>
                              <th scope="col">Material</th>
                              <th scope="col">Cantidad</th>
                              <th scope="col">Serie</th>
                              <th scope="col">Estado</th>
                            </tr>
                          </thead>
                          <tbody>
                            {#each materiales[grupo.clave] as linea (linea.id)}
                              <tr>
                                <td>
                                  <span class="snoc-mono-sm">{linea.material.codigo}</span>
                                  <span class="snoc-body-sm snoc-tenue">
                                    · {linea.material.nombre}
                                  </span>
                                </td>
                                <td class="snoc-mono-sm">{conUnidad(linea)}</td>
                                <td class="snoc-mono-sm">{linea.serie || '—'}</td>
                                <td>
                                  {#if grupo.clave === 'comprometido'}
                                    <span class="snoc-insignia">
                                      {linea.pendiente ? 'pendiente' : linea.desenlace || 'resuelta'}
                                    </span>
                                  {:else}
                                    <span
                                      class="snoc-insignia {linea.estado === 'aceptado'
                                        ? ''
                                        : 'snoc-insignia-error'}"
                                    >
                                      {linea.estado}
                                    </span>
                                    {#if linea.motivo}
                                      <span class="snoc-body-sm snoc-tenue"> {linea.motivo}</span>
                                    {/if}
                                  {/if}
                                </td>
                              </tr>
                            {/each}
                          </tbody>
                        </table>
                      </div>
                      {#if grupo.pie}
                        <span class="snoc-body-sm snoc-tenue">{grupo.pie}</span>
                      {/if}
                    </div>
                  {/if}
                {/each}

                <!--
                  El kit del dia, aparte y rotulado. 'EntregaDeKit' no tiene FK a
                  la orden: el despacho de la mañana es a la custodia del tecnico,
                  que con los mismos materiales hace cinco trabajos.
                -->
                <button type="button" class="snoc-btn" onclick={alternarCustodia}>
                  {verCustodia ? 'Ocultar' : 'Ver'} lo que el técnico lleva encima hoy
                </button>

                {#if verCustodia && materiales.custodia_del_tecnico}
                  <div class="snoc-analisis snoc-observado">
                    <span class="snoc-insignia snoc-insignia-variante">
                      Custodia del técnico — NO es material de esta orden
                    </span>
                    <p class="snoc-body" style="margin:0;">
                      Es el kit que
                      <strong>
                        {materiales.custodia_del_tecnico.tecnico?.nombre ?? 'el técnico'}
                      </strong>
                      tiene encima para toda la jornada{#if materiales.custodia_del_tecnico.acta}{' '}
                        (acta
                        <span class="snoc-mono-sm">{materiales.custodia_del_tecnico.acta}</span>){/if}.
                      Con esto atiende varias órdenes, así que no dice cuánto se usó acá.
                    </p>
                    {#if (materiales.custodia_del_tecnico.items ?? []).length}
                      <div class="snoc-mono-sm snoc-tenue snoc-pila-xs">
                        {#each materiales.custodia_del_tecnico.items as item, i (i)}
                          <span>{item.material.codigo} · {conUnidad(item)}</span>
                        {/each}
                      </div>
                    {:else}
                      <p class="snoc-body-sm snoc-tenue" style="margin:0;">
                        Sin kit vigente registrado.
                      </p>
                    {/if}
                  </div>
                {/if}
              {/if}
            </div>
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
