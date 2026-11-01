<script>
  /**
   * LA OFICINA VIRTUAL — PROTOTIPO DEL NOC.
   *
   * Ruta aparte, `/centro-mando/v2`. El centro de mando que está en producción
   * no se toca: comparte los módulos de datos (`proyeccion`, `frescura`) y nada
   * más. Si esto se cae, aquello sigue.
   *
   * CÓMO SE COMPONE, DE FUERA HACIA DENTRO
   *
   *   flujo.js        pide eventos con cursor y MIDE si se puede confiar
   *   proyeccion.js   evento -> instrucción visual, con procedencia
   *   frescura.js     las cuatro señales -> un veredicto
   *   adaptador.ts    instrucción + veredicto -> animación
   *   montar.ts       la única puerta de la escena
   *
   * Esta pantalla no sabe qué es un sprite ni cómo se dibuja un suelo
   * isométrico, y la escena no sabe qué es un evento. Ese corte es el
   * entregable de verdad: cuando haya ocho departamentos, lo que se repite es
   * la escena, no esta cadena.
   *
   * EL BUCLE DE AQUÍ NO ES EL DE LA ESCENA
   * La escena tiene su propio reloj a la velocidad de la pantalla (respiración,
   * pantallas, cámara). Acá hay un reloj LENTO, de 150 ms, que hace tres cosas
   * que no necesitan 60 veces por segundo: avanzar el guion de demostración,
   * caducar las instrucciones vencidas y —esto es lo importante— recalcular la
   * frescura. Lo último tiene que pasar SIN respuestas del motor: si el silencio
   * solo se evaluara al recibir algo, un motor caído nunca dispararía el aviso.
   */

  import { onDestroy } from 'svelte';
  import { crearFlujo } from '$lib/centro-mando/flujo.js';
  import { crearBitacora } from '$lib/centro-mando/bitacora.js';
  import { crearDemostracion } from '$lib/centro-mando/demo.js';
  import { proyectar, vigentes } from '$lib/centro-mando/proyeccion.js';
  import { frescura } from '$lib/centro-mando/frescura.js';
  import { ocupacionesSinSilla, pisosDe, plantaDe, salaPorId, salasDe }
    from '$lib/centro-mando/departamentos.js';
  import { edificioDe } from '$lib/centro-mando/edificio.js';
  import { edificioCompactoPixi } from '$lib/centro-mando/edificio-compacto.js';
  import { page } from '$app/state';
  import FichaDePuesto from '$lib/components/centro-mando/FichaDePuesto.svelte';

  let { data } = $props();

  /**
   * LAS SALAS SALEN DE LA CONFIGURACIÓN DE LA EMPRESA, no de este archivo.
   *
   * Hasta el 31/10/2026 había seis departamentos escritos en el frontend, y se
   * midió de dónde habían salido: de agrupar el campo `area` de los roles. O
   * sea que esta pantalla mostraba los GRUPOS DE LOS AGENTES y los presentaba
   * como el organigrama. Un departamento sin ningún agente no existía.
   *
   * Se lee una vez, al montar. Es estructura, no estado: cambia cuando alguien
   * reorganiza la empresa, y entonces hay que remontar — que es lo que pasa al
   * navegar.
   */
  const SALAS = salasDe(data.organizacion);
  const PISOS = pisosDe(data.organizacion, SALAS);
  /**
   * De dónde salió la estructura, y por qué se muestra.
   *
   * `por_defecto` significa que la empresa no declaró su organización y se está
   * viendo la estructura genérica del producto. Las dos se dibujan igual, así
   * que sin decirlo una empresa creería que configuró algo que no configuró.
   */
  const ORIGEN = data.organizacion?.origen ?? null;

  /**
   * QUÉ SE ESTÁ MIRANDO. Tres cosas distintas, no una con variantes:
   *
   *   edificio   los niveles apilados, con su núcleo y su estructura
   *   piso       un nivel aislado, bajado al suelo
   *   sala       una sala sola, como estaba antes de que hubiera niveles
   *
   * Cambiarlo DESMONTA y vuelve a montar la escena. No es pereza: entre una
   * sala y el edificio cambia el recinto, el mobiliario, el número de plantas y
   * hasta el límite del zoom. Reconstruirlo en caliente sería mantener dos
   * caminos para el mismo resultado, y el segundo nunca se prueba.
   */
  let vista = $state(
    /** @type {{ tipo: 'edificio' } | { tipo: 'piso', nivel: number } | { tipo: 'sala', id: string }} */
    (SALAS.length === 0 ? { tipo: 'edificio' } : { tipo: 'edificio' })
  );
  /**
   * ENLACE DIRECTO A UNA SALA O A UN PUESTO.
   *
   * `?sala=cartera` abre esa sala; `?sala=cartera&puesto=cartera:p1` abre
   * además su ficha; `?piso=2` abre ese nivel. Sin parámetros, el edificio.
   *
   * Hace falta por dos motivos distintos y los dos valen. Uno: una oficina sin
   * enlaces no se puede mandar — «mirá el puesto de facturación» obliga a
   * explicar cuatro clics. Dos: es la única forma de que una prueba de
   * navegador llegue a un puesto sin adivinar en qué píxel del lienzo cayó,
   * que es justo la clase de prueba que falla por lo que no importa.
   *
   * Se lee UNA vez, del `location` del navegador, y no se escribe de vuelta:
   * sincronizar la URL con cada clic convertiría el historial del navegador en
   * un registro de la cámara.
   */
  const DESDE_LA_URL = (() => {
    if (typeof location === 'undefined' || SALAS.length === 0) return {};
    const q = new URLSearchParams(location.search);
    const pedida = q.get('sala');
    const piso = Number(q.get('piso'));
    //  UNA SALA QUE NO EXISTE SE IGNORA, y se comprueba con una busqueda
    //  EXACTA y no con `salaPorId`: esa funcion cae a la primera sala cuando
    //  no encuentra el id, que es lo correcto para el selector -lo que se
    //  selecciona siempre existe- y es justo lo que no se puede hacer con un
    //  enlace. Medido: `?sala=departamento-que-no-existe` abria NOC y Redes
    //  en silencio, asi que un enlace viejo a Cartera te mostraba otro
    //  departamento y nada decia que no era el que pediste.
    if (pedida && SALAS.some((s) => s.id === pedida)) {
      return { vista: { tipo: 'sala', id: pedida }, puesto: q.get('puesto') };
    }
    if (Number.isFinite(piso) && PISOS.some((x) => x.nivel === piso)) {
      return { vista: { tipo: 'piso', nivel: piso } };
    }
    return {};
  })();
  if (DESDE_LA_URL.vista) vista = DESDE_LA_URL.vista;

  let sala = $derived(vista.tipo === 'sala' ? salaPorId(SALAS, vista.id) : null);
  let pisoVisto = $derived(
    vista.tipo === 'piso' ? (PISOS.find((p) => p.nivel === vista.nivel) ?? null) : null
  );

  /**
   * El inventario se lee UNA vez, al montar. El compilador avisa de que esto
   * captura el valor inicial; ese es exactamente el valor que queremos: si el
   * inventario cambiara habría que remontar, que es lo que pasa al navegar.
   */
  const inventario = data.agentes;

  /**
   * El edificio, cuando lo que se mira es un edificio.
   *
   * `soloNivel` es lo único que cambia entre la vista de conjunto y un nivel
   * aislado: el compositor ya sabe bajar el nivel al suelo y recalcular el
   * recinto. Tener dos funciones —una para el edificio y otra para un piso—
   * sería tener dos geometrías que se van separando sin que nadie lo note.
   */
  /**
   * LA OPCION B DE LA COMPARACION DE MOTORES, detras de `?planta=compacta`.
   *
   * Sin el parametro esta pantalla es la de siempre, byte por byte: es la
   * forma de comparar las dos distribuciones con la MISMA escena, los mismos
   * personajes y la misma ficha de puesto, sin duplicar 877 lineas que se
   * irian separando. Con el parametro se dibuja la planta en rejilla, y lo
   * que mide es `edificio-compacto.test.js`.
   *
   * Es temporal y se va con la decision de motor: lo dice el propio nombre
   * del parametro, que no es una preferencia del usuario ni se persiste.
   */
  const plantaCompacta = $derived(page.url.searchParams.get('planta') === 'compacta');

  let edificio = $derived(
    SALAS.length === 0 || vista.tipo === 'sala'
      ? null
      : (plantaCompacta ? edificioCompactoPixi : edificioDe)(
          SALAS, inventario, PISOS,
          { soloNivel: vista.tipo === 'piso' ? vista.nivel : null })
  );

  let planta = $derived(
    SALAS.length === 0
      ? null
      : vista.tipo === 'sala'
        ? plantaDe(sala ?? SALAS[0], inventario)
        : (edificio?.plantas?.length ? edificio.plantas : null)
  );

  /**
   * Hasta dónde se puede alejar la cámara en lo que se está mirando.
   *
   * Medido: once salas en tres niveles ocupan 3.552 × 2.946 píxeles de mundo y
   * caben en una vista de 1.625 × 600 a escala 0,204. Con el límite de una sala
   * —0,4— la vista de conjunto nace recortada. Un nivel aislado entra a 0,42 y
   * no necesita nada.
   *
   * No se baja para todos: en una sala el límite existe porque por debajo el
   * mobiliario es una mancha, y eso no cambió.
   */
  let escalaMinima = $derived(vista.tipo === 'edificio' ? 0.16 : undefined);

  /**
   * El nombre de cada nivel, atado al edificio y dibujado a tamaño de pantalla.
   *
   * Medido: la vista de conjunto entra a escala 0,2, así que el nombre que va
   * escrito en el canto de la losa —13 px— mide 2,6 y no se lee. Agrandarlo no
   * sirve: en una sala quedaría gigante. Lo que hace falta es texto que no
   * participe del zoom, y eso es lo que la escena sabe hacer con `letreros`.
   *
   * Se ancla al borde izquierdo del núcleo de cada nivel y se dibuja hacia la
   * izquierda, que es la única franja del encuadre donde no hay edificio.
   */
  let letreros = $derived(
    vista.tipo === 'sala' || !edificio
      ? []
      : [
          ...edificio.niveles.map((n) => ({
            texto: n.rotulo ? `P${n.nivel} · ${n.rotulo}` : `Piso ${n.nivel}`,
            //  FUERA DE LA HUELLA DEL EDIFICIO, no pegado a su borde.
            //
            //  Con `gx: 0` el ancla cae sobre el núcleo, y el rótulo del piso
            //  se cruzaba con el de la primera sala de ese nivel: en la
            //  captura del 31/10/2026 se leía «P2 · Operación y cliente.»
            //  porque «NOC y Redes» se le montaba encima. Dos textos que se
            //  pisan no es un detalle estético: es un nombre que deja de
            //  decir lo que dice.
            //
            //  `-6` lo saca por delante del basamento, que llega a -3,2.
            gx: -6,
            gy: 9,
            gz: n.gz,
            hacia: /** @type {const} */ ('izquierda')
          })),
          //  EL NOMBRE DE CADA SALA, TAMBIEN A TAMAÑO DE PANTALLA.
          //
          //  Ya va escrito en el canto de su losa, y medido en el navegador no
          //  se lee: la vista de conjunto entra a escala 0,2 y un texto de
          //  13 px mide 2,6. Agrandarlo no sirve —en una sala quedaria
          //  gigante— y es el mismo motivo por el que los pisos pasaron a ser
          //  letreros. Lo que cambia es que hay once y no tres, asi que van
          //  mas chicos y hacia la derecha, sobre su propia losa.
          ...edificio.plantas
            .filter((p) => p.papel === 'sala')
            .map((p) => ({
              texto: p.cartel?.rotulo ?? p.sala,
              gx: p.origen.gx + 0.4,
              gy: p.origen.gy + p.mundo.fondo + 0.6,
              gz: p.origen.gz,
              hacia: /** @type {const} */ ('derecha'),
              cuerpo: 10
            }))
        ]
  );

  /** Cómo se llama lo que se está mirando. */
  let titulo = $derived(
    SALAS.length === 0
      ? 'Sin estructura'
      : vista.tipo === 'edificio'
        ? 'El edificio'
        : vista.tipo === 'piso'
          ? (pisoVisto?.rotulo || `Piso ${vista.nivel}`)
          : (sala?.rotulo ?? 'Sala desconocida')
  );
  let subtitulo = $derived(
    vista.tipo === 'edificio'
      ? `${SALAS.filter((s) => s.tipo === 'departamento').length} departamentos · ${PISOS.length} piso(s)`
      : vista.tipo === 'piso'
        ? `Piso ${vista.nivel} · ${pisoVisto?.salas?.length ?? 0} sala(s)`
        : (sala?.direccion || (sala?.tipo === 'espacio' ? 'Espacio complementario' : ''))
  );

  /** Los puestos de lo que se esté mirando: una sala, un nivel o el edificio. */
  let puestosVisibles = $derived(
    planta === null ? [] : Array.isArray(planta) ? planta.flatMap((p) => p.puestos) : planta.puestos
  );
  let agentesConPuesto = $derived(puestosVisibles.map((p) => p.agente).filter(Boolean));
  /**
   * Las personas del equipo sentadas en lo que se esta mirando.
   *
   * Van APARTE de `agentesConPuesto` y no sumadas a la misma lista: ese arreglo
   * alimenta el adaptador de actividad, y meter ahi a alguien que el motor no
   * representa haria que la escena buscara eventos de una persona.
   *
   * Pero SI cuentan como puesto ocupado. Sin esto el pie decia «1 de 4 puestos
   * ocupados» con tres personas dibujadas en la sala: la oficina se
   * contradecia a si misma, y el numero es justo lo que alguien lee para saber
   * cuanta gente hay.
   */
  let personasConPuesto = $derived(puestosVisibles.map((p) => p.persona).filter(Boolean));

  /**
   * Las ocupaciones que la sala vista no puede dibujar. El cálculo vive en
   * `departamentos.js` porque acá no se puede probar: el harness de vitest no
   * resuelve `$app/*`, y esto se rompe en silencio.
   */
  let sinSilla = $derived(
    ocupacionesSinSilla(
      vista.tipo === 'sala'
        ? (sala ? [sala] : [])
        : vista.tipo === 'piso'
          ? (pisoVisto?.salas ?? [])
          : SALAS
    )
  );

  /** @type {HTMLElement|null} */
  let lienzo = $state(null);
  /** @type {any} */
  let escena = null;
  let montando = $state(true);
  /** @type {string|null} */
  let errorDeEscena = $state(null);

  /** Instrucciones acumuladas, reales y simuladas por separado. */
  let instruccionesReales = $state([]);
  let instruccionesSimuladas = $state([]);
  const bitacora = crearBitacora();
  /**
   * Copias reactivas de los dos historiales.
   *
   * `bitacora` es un objeto corriente con dos captadores: leerlo dentro de un
   * `$derived` NO crea dependencia, así que la ficha se habría quedado con el
   * historial del instante en que se abrió y nadie lo habría notado —se ve
   * igual que «todavía no llegó nada»—. Es el salto que §6 de CLAUDE.md
   * describe: el dato llega bien y la capa de pantalla lo deja caer.
   *
   * Siguen siendo DOS, nunca uno: la separación entre lo real y lo simulado es
   * estructural y no sobrevive a juntarlos «para la vista».
   */
  let historialReal = $state([]);
  let historialSimulado = $state([]);

  let demostracion = $state(false);
  /** @type {any} */
  let guion = null;

  /** @type {any} */
  let veredicto = $state(frescura({ ultimaRespuestaOk: null }));
  /** @type {any[]} */
  let estados = $state([]);
  /** @type {any} */
  let diagnostico = $state(null);
  /** @type {any} */
  let metricas = $state(null);
  let sinRepresentacion = $state(0);

  /** @type {string|null} */
  let seleccionado = $state(DESDE_LA_URL.puesto ?? null);

  //  El flujo pide TODOS los agentes de la empresa, no los de la sala que se
  //  está mirando: si filtrara por departamento, cambiar de sala tiraría el
  //  cursor y se perderían los eventos de los demás mientras tanto.
  const flujo = crearFlujo({
    agentes: (data.agentes || []).map((a) => a.nombre).filter(Boolean),
    areas: data.areas || [],
    // Un agente sin puesto no se proyecta, y sin agentes con puesto no se filtra
    // por agente: así el prototipo se puede mirar aunque el inventario venga
    // vacío, en vez de quedarse en una sala muda sin decir por qué.
    limite: 120
  });

  flujo.alLote((lote) => {
    instruccionesReales = [...instruccionesReales, ...lote.instrucciones];
    bitacora.anotar(lote.instrucciones);
    historialReal = bitacora.real;
  });

  /** El puesto que está seleccionado, con su definición. */
  let puestoSeleccionado = $derived(puestosVisibles.find((p) => p.id === seleccionado) ?? null);

  /**
   * Que puede hacer HOY el agente de ese puesto.
   *
   * `null` -no se pudo leer- y `[]` -se leyo y no tiene ninguna- son cosas
   * distintas y la ficha las muestra distinto, asi que no se colapsan aca: un
   * agente sin entrada en el mapa es un agente del que no sabemos, no uno que
   * no puede hacer nada.
   */
  let accionesDelPuesto = $derived(
    !data.acciones || !puestoSeleccionado?.agente
      ? null
      : (data.acciones.acciones?.[puestoSeleccionado.agente] ?? null)
  );
  let estadoSeleccionado = $derived(
    puestoSeleccionado?.agente
      ? (estados.find((e) => e.agente === puestoSeleccionado.agente) ?? null)
      : null
  );
  /**
   * Las capacidades del departamento al que pertenece el puesto abierto.
   *
   * En la vista de empresa hay varias plantas, así que se busca la que
   * contiene este puesto en vez de asumir la vigente.
   */
  /**
   * La sala a la que pertenece el puesto abierto.
   *
   * Sale del propio identificador del puesto, que se compone como
   * `<sala>:<puesto>` justamente para que esto no necesite plumbing: en la
   * vista de empresa hay once plantas y buscar «la vigente» no significa nada.
   */
  let salaDelPuesto = $derived(
    puestoSeleccionado
      ? (SALAS.find((s) => s.id === String(puestoSeleccionado.id).split(':')[0]) ?? null)
      : null
  );

  let capacidadesDelPuesto = $derived.by(() => {
    if (!puestoSeleccionado || planta === null) return [];
    const plantas = Array.isArray(planta) ? planta : [planta];
    const suya = plantas.find((p) => p.puestos.some((q) => q.id === puestoSeleccionado.id));
    return suya?.capacidades ?? [];
  });

  let historialSeleccionado = $derived(
    puestoSeleccionado?.agente
      ? (demostracion ? historialSimulado : historialReal).filter(
          (a) => a.agente === puestoSeleccionado.agente
        )
      : []
  );

  /** La frase del indicador de frescura, arriba del lienzo. */
  const PALABRAS = {
    sin_lectura: 'Esperando la primera lectura',
    silencio: 'Sin información · el motor no responde',
    pausado: 'Sin información · la pestaña estuvo oculta',
    error: 'Sin información · la última lectura falló',
    retraso: 'Sin información · el flujo viene atrasado',
    al_dia: 'Actualizado'
  };
  let frase = $derived(PALABRAS[veredicto?.motivo] ?? 'Sin información');

  /* ── el reloj lento ─────────────────────────────────────────────────────── */
  let ultimoTic = 0;

  function tic() {
    const ahora = Date.now();
    const dt = ultimoTic ? Math.min(0.5, (ahora - ultimoTic) / 1000) : 0;
    ultimoTic = ahora;

    if (demostracion && guion) {
      const eventos = guion.avanzar(dt);
      if (eventos.length) {
        // EL LOTE ENTERO SE MARCA COMO SIMULADO. No evento por evento: si
        // dependiera de cada fila, bastaría con olvidarse de una para que un
        // movimiento de prueba entrara como actividad real.
        const p = proyectar(eventos, {
          agentes: agentesConPuesto,
          areas: data.areas || [],
          ahora,
          simulado: true
        });
        instruccionesSimuladas = [...instruccionesSimuladas, ...p.instrucciones];
        bitacora.anotar(p.instrucciones);
        historialSimulado = bitacora.simulado;
      }
    }

    // Caducar. Sin esto, un agente que consultó una vez se quedaría
    // «consultando» para siempre, que es justo la mentira que esta cadena evita.
    instruccionesReales = vigentes(instruccionesReales, ahora);
    instruccionesSimuladas = vigentes(instruccionesSimuladas, ahora);

    // La frescura se recalcula SIEMPRE, con o sin respuestas. Es el único modo
    // de que el silencio se note: un motor caído no manda un aviso de que está
    // caído.
    veredicto = frescura(flujo.senales());
    diagnostico = flujo.diagnostico();

    // Durante la demostración el veredicto del flujo real no puede apagar la
    // escena: lo que se está mirando no viene de ahí. Se mantiene al día a
    // propósito, y el cartel de «demostración» lo dice en todas las vistas.
    const veredictoDeEscena = demostracion
      ? { confiable: true, motivo: 'al_dia', detalle: null, silencio_s: 0 }
      : veredicto;

    //  Durante la demostración no se mezclan los turnos reales en curso: lo
    //  que se está mirando es un guion, y pintar encima una ejecución de
    //  verdad haría que una parte de la escena fuera real y otra inventada sin
    //  que se pueda distinguir cuál es cuál.
    const visual = visualizarAhora(
      demostracion ? instruccionesSimuladas : instruccionesReales,
      veredictoDeEscena,
      ahora,
      demostracion ? [] : flujo.activas()
    );
    estados = visual.estados;
    sinRepresentacion = visual.sinRepresentacion;
    escena?.aplicar(estados);
    metricas = escena?.metricas() ?? null;
  }

  /** @type {any} */
  let visualizar = null;
  function visualizarAhora(instrucciones, v, ahora, activas) {
    if (!visualizar) return { estados: [], sinRepresentacion: 0 };
    return visualizar(instrucciones, agentesConPuesto, v, ahora, activas);
  }

  /* ── montaje ────────────────────────────────────────────────────────────── */
  $effect(() => {
    if (!lienzo) return;
    //  Leer `planta` acá es lo que hace que cambiar de sala vuelva a ejecutar
    //  este efecto: la escena se destruye y se monta de nuevo.
    const laPlanta = planta;
    const elZoom = escalaMinima;
    const losLetreros = letreros;
    //  Sin estructura no se monta nada, y NO se cae a una inventada: dibujar
    //  un edificio que nadie declaró sería afirmar cómo es una empresa que no
    //  se pudo consultar. El aviso lo da el pie.
    if (laPlanta === null) {
      montando = false;
      return;
    }
    let vivo = true;
    /** @type {any} */
    let reloj = null;

    (async () => {
      try {
        // Carga diferida: el motor gráfico son cientos de kilobytes y no tiene
        // nada que hacer en el servidor. Importarlo arriba lo metería en el
        // paquete de todas las pantallas.
        const [{ montarEscena }, adaptador] = await Promise.all([
          import('$lib/centro-mando/escena/montar'),
          import('$lib/centro-mando/escena/adaptador')
        ]);
        if (!vivo) return;
        visualizar = adaptador.visualizar;
        escena = await montarEscena({ contenedor: lienzo, planta: laPlanta,
                                      escalaMinima: elZoom, letreros: losLetreros });
        if (!vivo) {
          escena.destruir();
          escena = null;
          return;
        }
        escena.alSeleccionar((id) => {
          seleccionado = id;
        });
        montando = false;
        flujo.arrancar();
        reloj = setInterval(tic, 150);
        tic();
      } catch (/** @type {any} */ e) {
        errorDeEscena = e?.message || 'No se pudo iniciar la escena';
        montando = false;
      }
    })();

    return () => {
      vivo = false;
      if (reloj) clearInterval(reloj);
      escena?.destruir();
      escena = null;
    };
  });

  onDestroy(() => {
    flujo.detener();
  });

  function alternarDemostracion() {
    demostracion = !demostracion;
    if (demostracion) {
      guion = guion || crearDemostracion({ agente: agentesConPuesto[0] || 'sin_agente', areaDerivacion: (data.areas || [])[0] ?? null });
      guion.reiniciar();
    } else {
      // Lo simulado se olvida al apagar. Dejarlo ahí haría que la próxima
      // mirada a la ficha encontrara un historial de demostración sin el cartel
      // que lo explica.
      instruccionesSimuladas = [];
      bitacora.olvidarSimulado();
      historialSimulado = [];
    }
  }
</script>

<svelte:head><title>Oficina virtual · {titulo}</title></svelte:head>

<div class="pantalla">
  <header class="barra">
    <div class="donde">
      <h1>{titulo}</h1>
      <p>
        {subtitulo}
        {#if ORIGEN === 'por_defecto'}
          · <span class="procedencia" data-prueba="origen-organizacion">estructura por defecto del producto</span>
        {:else if ORIGEN === 'declarada'}
          · <span data-prueba="origen-organizacion">organización declarada por la empresa</span>
        {/if}
      </p>
    </div>

    <!-- El selector de sala. Cambiarlo remonta la escena entera: es otra
         planta, no el mismo recinto con otros muebles. -->
    <!-- Tres niveles de acercamiento, y el orden importa: se entra por el
         edificio, se elige un piso y se entra a una sala. Es el recorrido que
         una persona hace al buscar algo, y el botón del edificio es siempre la
         vuelta atrás. -->
    <nav class="salas" aria-label="Qué se mira">
      <button
        type="button"
        class:activa={vista.tipo === 'edificio'}
        aria-pressed={vista.tipo === 'edificio'}
        onclick={() => { vista = { tipo: 'edificio' }; seleccionado = null; }}
      >El edificio</button>
      <!-- De arriba hacia abajo, que es como se lee un edificio. El piso es un
           dato de la organización: el botón aísla ese nivel y lo baja al suelo,
           porque un piso flotando a dos pisos de altura no dice nada. -->
      {#each PISOS as piso (piso.nivel)}
        <button
          type="button"
          class="nivel"
          class:activa={vista.tipo === 'piso' && vista.nivel === piso.nivel}
          aria-pressed={vista.tipo === 'piso' && vista.nivel === piso.nivel}
          title={piso.rotulo || `Piso ${piso.nivel}`}
          onclick={() => { vista = { tipo: 'piso', nivel: piso.nivel }; seleccionado = null; }}
        >P{piso.nivel}{#if !piso.declarado}<em title="Ningún piso declarado con este nivel">?</em>{/if}</button>
        {#each piso.salas as s (s.id)}
          <button
            type="button"
            class:activa={vista.tipo === 'sala' && vista.id === s.id}
            class:espacio={s.tipo === 'espacio'}
            aria-pressed={vista.tipo === 'sala' && vista.id === s.id}
            onclick={() => { vista = { tipo: 'sala', id: s.id }; seleccionado = null; }}
          >{s.rotulo}</button>
        {/each}
      {/each}
    </nav>

    <!-- El indicador de frescura, siempre a la vista y no escondido en la
         ficha: es la diferencia entre «este agente no tiene trabajo» y «no
         tengo ni idea de lo que hace», y eso no puede depender de que alguien
         abra un panel. -->
    <div class="frescura" class:mal={!veredicto?.confiable} data-prueba="frescura">
      <span class="punto"></span>
      <span>{frase}</span>
      {#if veredicto?.silencio_s != null && !veredicto.confiable}
        <span class="desde">{veredicto.silencio_s} s</span>
      {/if}
    </div>

    <div class="mandos">
      {#if demostracion}
        <span class="sello">DEMOSTRACIÓN</span>
      {/if}
      <button type="button" onclick={alternarDemostracion}>
        {demostracion ? 'Detener demostración' : 'Demostración'}
      </button>
      <button type="button" onclick={() => escena?.encuadrar()}>Encuadrar</button>
      {#if metricas}
        <span class="metricas" data-prueba="metricas">
          {metricas.fps} fps · mín {metricas.fpsMinimo} · {metricas.objetos} obj · {metricas.motor}
        </span>
      {/if}
    </div>
  </header>

  <div class="cuerpo">
    <div class="escenario" bind:this={lienzo} data-prueba="escenario">
      {#if montando}
        <p class="cargando">Montando la oficina…</p>
      {/if}
      {#if errorDeEscena}
        <p class="roto">
          No se pudo iniciar la escena: {errorDeEscena}
          <small>El resto del centro de mando no depende de esta pantalla.</small>
        </p>
      {/if}
    </div>

    {#if puestoSeleccionado}
      <FichaDePuesto
        puesto={puestoSeleccionado}
        estado={estadoSeleccionado}
        veredicto={demostracion ? { confiable: true, motivo: 'al_dia', detalle: 'Guion de demostración en curso.' } : veredicto}
        historial={historialSeleccionado}
        capacidades={capacidadesDelPuesto}
        sala={salaDelPuesto}
        acciones={accionesDelPuesto}
        autonomia={data.acciones?.autonomia ?? null}
        simulado={demostracion}
        {diagnostico}
        alCerrar={() => {
          seleccionado = null;
          escena?.seleccionar(null);
        }}
      />
    {/if}
  </div>

  <footer class="pie">
    {#if data.error}
      <span class="alarma">Inventario de agentes: {data.error}</span>
    {:else if SALAS.length === 0}
      <span class="alarma">
        No se pudo leer la estructura de la empresa: no se dibuja ningún edificio
        a propósito, porque inventarlo afirmaría cómo es una empresa que no se
        pudo consultar.
      </span>
    {:else if agentesConPuesto.length === 0 && personasConPuesto.length === 0}
      <span class="alarma">
        Ningún puesto de «{titulo}» tiene un agente del inventario ni una
        persona del equipo: se dibujan vacíos a propósito.
      </span>
    {:else}
      <span>
        {agentesConPuesto.length + personasConPuesto.length}
        de {puestosVisibles.length} puestos ocupados{#if agentesConPuesto.length > 0}:
          <code>{agentesConPuesto.join(', ')}</code>{/if}{#if personasConPuesto.length > 0}
          <!-- Se nombran aparte porque son otra cosa: un agente lo ejecuta el
               motor y una persona no, y mezclarlos en una lista haría que
               quien la lea no pueda distinguirlos. -->
          · {personasConPuesto.length} persona(s) del equipo{/if}
      </span>
    {/if}
    {#if sinSilla.length > 0}
      <span class="alarma">
        {sinSilla.length} ocupación(es) declarada(s) en un puesto que su sala no
        tiene, así que no se dibujan: <code>{sinSilla.join(', ')}</code>. Elegir
        una sala más grande las devuelve.
      </span>
    {/if}
    {#if sinRepresentacion > 0}
      <span class="alarma">
        {sinRepresentacion} hecho(s) registrado(s) que la escena no sabe dibujar.
      </span>
    {/if}
    <span class="nota">
      Arrastrar mueve la cámara · la rueda hace zoom · pulsar un puesto abre su ficha
    </span>
  </footer>
</div>

<style>
  .pantalla {
    display: flex;
    flex-direction: column;
    height: calc(100vh - 56px);
    min-height: 520px;
    background: #0b0a1c;
    color: #e8e7f5;
  }

  /*  Un espacio complementario se ve distinto de un departamento porque NO es
      uno: no agrupa areas ni agentes, y a una recepcion no se le asignan
      responsabilidades. */
  .salas button.espacio {
    border-style: dashed;
    opacity: 0.85;
  }
  .procedencia {
    color: #ffd79a;
  }

  .barra {
    display: flex;
    align-items: center;
    gap: 18px;
    padding: 10px 16px;
    border-bottom: 1px solid rgba(255, 255, 255, 0.08);
    flex-wrap: wrap;
  }
  .donde h1 {
    margin: 0;
    font-size: 15px;
    font-weight: 600;
  }
  .donde p {
    margin: 1px 0 0;
    color: #9a98bd;
    font-size: 11.5px;
  }

  .frescura {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-left: auto;
    padding: 5px 11px;
    border-radius: 999px;
    background: rgba(123, 203, 138, 0.12);
    border: 1px solid rgba(123, 203, 138, 0.35);
    font-size: 11.5px;
  }
  .frescura.mal {
    background: rgba(154, 152, 189, 0.14);
    border-color: rgba(154, 152, 189, 0.45);
  }
  .punto {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: #7bcb8a;
  }
  .frescura.mal .punto {
    background: #9a98bd;
  }
  .desde {
    color: #9a98bd;
    font-variant-numeric: tabular-nums;
  }

  .salas {
    display: flex;
    gap: 6px;
  }
  .salas button {
    padding: 5px 11px;
    border: 1px solid rgba(255, 255, 255, 0.14);
    border-radius: 6px;
    background: transparent;
    color: #9a98bd;
    font-size: 11.5px;
    cursor: pointer;
  }
  .salas button.activa {
    border-color: #8b84f5;
    color: #e8e7f5;
    background: rgba(139, 132, 245, 0.12);
  }

  .mandos {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 11.5px;
  }
  .mandos button {
    padding: 5px 11px;
    border: 1px solid rgba(255, 255, 255, 0.16);
    border-radius: 6px;
    background: transparent;
    color: #e8e7f5;
    font-size: 11.5px;
    cursor: pointer;
  }
  .mandos button:hover {
    border-color: rgba(255, 255, 255, 0.4);
  }
  .sello {
    padding: 3px 8px;
    border-radius: 4px;
    background: rgba(224, 166, 83, 0.18);
    border: 1px solid rgba(224, 166, 83, 0.5);
    color: #e0a653;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
  }
  .metricas {
    color: #6b6a85;
    font-variant-numeric: tabular-nums;
  }

  .cuerpo {
    display: flex;
    flex: 1;
    min-height: 0;
  }
  .escenario {
    position: relative;
    flex: 1;
    min-width: 0;
    overflow: hidden;
  }
  .cargando,
  .roto {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
    align-items: center;
    justify-content: center;
    margin: 0;
    color: #9a98bd;
    font-size: 12.5px;
    text-align: center;
  }
  .roto {
    color: #ff7b6b;
  }
  .roto small {
    color: #9a98bd;
  }

  .pie {
    display: flex;
    gap: 16px;
    align-items: center;
    padding: 7px 16px;
    border-top: 1px solid rgba(255, 255, 255, 0.08);
    color: #9a98bd;
    font-size: 11px;
    flex-wrap: wrap;
  }
  .pie code {
    color: #e8e7f5;
  }
  .alarma {
    color: #e0a653;
  }
  .nota {
    margin-left: auto;
    color: #6b6a85;
  }
</style>
