/**
 * LA ÚNICA PUERTA DE LA ESCENA.
 *
 * Quien la usa ve cuatro verbos —`aplicar`, `seleccionar`, `metricas`,
 * `destruir`— y nada de PixiJS. Eso es lo que permite que la pantalla de Svelte
 * no importe el motor gráfico: el día que deje de ser PixiJS, cambia este
 * archivo y los de al lado, y la pantalla no se entera.
 *
 * TRES COSAS QUE ESTE ARCHIVO EXISTE PARA GARANTIZAR
 *
 * 1 · QUE SE PUEDA CERRAR. `destruir()` desmonta la aplicación, los oyentes del
 *     documento y las texturas. Sin eso, entrar y salir de la pantalla seis
 *     veces deja seis contextos de dibujo vivos; no falla, no avisa, solo va
 *     poniéndose lento hasta que el navegador tira el contexto más viejo y la
 *     escena se queda en negro sin un solo error en la consola.
 *
 * 2 · QUE EL CLIC LLEGUE. El arrastre captura el puntero —tiene que hacerlo, o
 *     se corta al salir del lienzo— y por eso el `click` del navegador no es
 *     fiable. La selección se decide con `gesto()` al soltar. Es el defecto que
 *     ya se pagó una vez en el plano anterior.
 *
 * 3 · QUE EL TIEMPO SEA REAL. Un contador de fotogramas como reloj hace que
 *     todo vaya más lento en una máquina lenta, incluida la respiración del
 *     personaje. Acá el tiempo son segundos de verdad, así que la escena se ve
 *     igual a 30 y a 144 cuadros por segundo — solo con menos pasos.
 */

import { Application, Container, Sprite } from 'pixi.js';
import { Camara, LIMITES, gesto, type Toque } from './camara';
import { aPantalla, extensionDelMundo } from './isometria';
import { COLOR_DE_ANIMACION, PALETA } from './paleta';
import { Transicion } from './pose';
import { construirOficina, type Planta, type Puesto } from './oficina';
import { construirPersonaje, type Personaje } from './personaje';
import { generarTexturas } from './texturas';
import type { EstadoDeAgente } from './adaptador';

export interface Metricas {
  /** Cuadros por segundo del último segundo. */
  fps: number;
  /** El peor segundo desde que se montó. Un promedio bueno esconde tirones. */
  fpsMinimo: number;
  /** Cuántos objetos hay en el árbol. La cuenta que importa al agregar salas. */
  objetos: number;
  /** Qué renderizador tocó: `webgl`, `webgpu`. */
  motor: string;
  escala: number;
}

export interface Escena {
  /** Lo que el adaptador decidió para cada agente. */
  aplicar(estados: EstadoDeAgente[]): void;
  /** Marca un puesto, o ninguno con `null`. No mueve la cámara. */
  seleccionar(idPuesto: string | null): void;
  /** Lleva la cámara a un puesto y lo marca. */
  enfocar(idPuesto: string): void;
  /** Vuelve a encuadrar el recinto completo. */
  encuadrar(): void;
  /** Se llama cuando alguien pulsa un puesto. `null` al pulsar el suelo. */
  alSeleccionar(f: (idPuesto: string | null) => void): void;
  metricas(): Metricas;
  /**
   * Coste REAL de dibujar un fotograma, en milisegundos.
   *
   * Existe porque los cuadros por segundo no se pueden medir en cualquier
   * sitio: un navegador sin ventana visible limita `requestAnimationFrame` a
   * su antojo —medido el 30/10/2026 en el banco de verificación: un contador
   * propio de rAF daba **1 por segundo** mientras la escena creía ir a 10—, y
   * entonces la cifra habla del navegador y no del dibujo.
   *
   * Esto dibuja N veces seguidas, sin esperar al refresco de pantalla, y
   * devuelve el promedio. Es la cifra que sí se puede comparar entre dos
   * versiones de la escena.
   */
  medirDibujo(cuadros?: number): { ms: number; cuadros: number };
  /**
   * Lo que un puesto está dibujando AHORA: su animación y la pose aplicada.
   *
   * Es el accesor que hace verificable la escena desde fuera. Sin él, la única
   * forma de comprobar que un cambio de estado llega al personaje es mirar una
   * captura — y mirar no sirve: el 30/10/2026 el personaje se veía igual en
   * «no sé» que en reposo porque el apagado se aplicaba a un contenedor, que en
   * PixiJS 8 no tiene tinte. La imagen era creíble y estaba mal.
   */
  estadoVisualDe(idPuesto: string): { animacion: string; pose: any } | null;
  destruir(): void;
}

export interface OpcionesDeEscena {
  /** El elemento que contiene el lienzo. Se mide para encuadrar. */
  contenedor: HTMLElement;
  /**
   * La planta completa: mundo, pasillo, mobiliario, puestos y cartel.
   *
   * Entra como DATO. La escena sabe dibujar tipos de mueble y no sabe qué
   * departamento está construyendo, que es lo que permite que la segunda sala
   * no cueste lo que costó la primera.
   */
  planta: Planta;
}

interface Habitante {
  puesto: Puesto;
  personaje: Personaje | null;
  transicion: Transicion;
  /** Inicio y fin del recorrido del paquete, en coordenadas del puesto. */
  recorrido: { desde: { x: number; y: number }; hasta: { x: number; y: number } };
}

export async function montarEscena(opciones: OpcionesDeEscena): Promise<Escena> {
  const { contenedor } = opciones;

  const app = new Application();
  await app.init({
    background: PALETA.fondo,
    antialias: true,
    // `autoDensity` + la densidad real de la pantalla: sin esto, en un portátil
    // con pantalla de alta densidad el texto de las placas sale borroso y
    // parece un problema de la fuente.
    resolution: Math.min(2, globalThis.devicePixelRatio || 1),
    autoDensity: true,
    resizeTo: contenedor,
    // WebGL y no WebGPU: WebGPU no está en todos los navegadores de escritorio
    // ni en los headless con los que se verifica esto, y una escena que no se
    // puede verificar es una escena que nadie sabe si funciona.
    preference: 'webgl'
  });
  contenedor.appendChild(app.canvas);
  app.canvas.style.display = 'block';
  // El navegador trata el lienzo como texto seleccionable y arrastrar deja la
  // página con todo en azul. Se ve feo y encima dispara el menú de arrastre.
  app.canvas.style.touchAction = 'none';
  (app.canvas.style as any).userSelect = 'none';

  const texturas = generarTexturas();
  const oficina = construirOficina(opciones.planta, texturas);

  /* El mundo entero cuelga de un contenedor al que se le aplica la cámara. */
  const mundo = new Container();
  mundo.addChild(oficina.raiz);
  app.stage.addChild(mundo);

  /* ── la viñeta ────────────────────────────────────────────────────────── */
  /* Va en el ESCENARIO y no en el mundo: oscurece las esquinas de la vista,
     que es lo que hace que la mirada caiga donde está la acción. Dentro del
     mundo se movería con la cámara y sería una mancha persiguiendo al suelo.
     No es interactiva: sin esto se come todos los clics del lienzo. */
  const vineta = new Sprite(texturas.vineta);
  vineta.eventMode = 'none';
  app.stage.addChild(vineta);

  const extension = extensionDelMundo(oficina.mundo);
  const vista = () => ({
    ancho: contenedor.clientWidth || 960,
    alto: contenedor.clientHeight || 600
  });
  const camara = new Camara(extension, vista(), LIMITES);

  /* ── los habitantes ───────────────────────────────────────────────────── */
  const habitantes: Habitante[] = oficina.puestos.map((puesto) => {
    let personaje: Personaje | null = null;
    if (puesto.def.agente) {
      personaje = construirPersonaje(texturas);
      // Un 18% más grande que las medidas de `personaje.ts`. En la primera
      // captura la figura era correcta y se perdía: la sala es de 14 × 10
      // celdas y una persona sentada a escala estricta ocupa 50 px de 1900. El
      // protagonista de la escena tiene que leerse sin acercar la cámara, y
      // esta es la exageración mínima que lo consigue sin que parezca un
      // gigante detrás de su mesa.
      personaje.nodo.scale.set(1.18);
      puesto.ancla.addChild(personaje.nodo);
    }
    // El paquete sale del escritorio hacia el pasillo, en línea recta sobre el
    // suelo. El destino es el pasillo del recinto y no «hacia la derecha»: así
    // el movimiento pertenece a la sala.
    const desde = aPantalla(puesto.def.gx + 1, puesto.def.gy + 0.4, 0.9);
    const hasta = aPantalla(12.5, puesto.def.gy + 0.4, 0.3);
    return {
      puesto,
      personaje,
      transicion: new Transicion(personaje ? 'reposo' : 'incognito'),
      recorrido: { desde, hasta }
    };
  });

  /* Un puesto vacío no tiene estado que mostrar: su placa lo dice y su halo se
     queda apagado. Dejarlo en `incognito` con el signo de interrogación sería
     afirmar que no sabemos algo que sí sabemos — que ahí no hay nadie. */
  for (const h of habitantes) {
    if (!h.puesto.def.agente) {
      h.puesto.testigo.tint = PALETA.incognito;
      h.puesto.halo.alpha = 0;
    }
  }

  /* ── selección ────────────────────────────────────────────────────────── */
  /* Qué puesto estaba bajo el puntero al pulsar. Lo escribe el sistema de
     eventos del motor gráfico y lo lee el oyente del lienzo al soltar: es el
     dato que hace que la decisión «clic o arrastre» pueda tomarse una sola vez
     y en un sitio. */
  let puestoPulsado: string | null = null;
  let seleccionado: string | null = null;
  const oyentes = new Set<(id: string | null) => void>();

  function marcar(id: string | null) {
    seleccionado = id;
    for (const h of habitantes) h.puesto.seleccion.visible = h.puesto.def.id === id;
  }

  for (const h of habitantes) {
    // `pointertap` de PixiJS no sirve acá por lo mismo que no sirve `click`: el
    // arrastre se queda con el puntero. Se guarda cuál es el puesto bajo el
    // puntero al pulsar, y al soltar se decide.
    h.puesto.nodo.on('pointerdown', () => {
      puestoPulsado = h.puesto.def.id;
    });
    h.puesto.nodo.on('pointerover', () => {
      h.puesto.seleccion.visible = true;
      h.puesto.seleccion.alpha = h.puesto.def.id === seleccionado ? 1 : 0.35;
    });
    h.puesto.nodo.on('pointerout', () => {
      h.puesto.seleccion.alpha = 1;
      h.puesto.seleccion.visible = h.puesto.def.id === seleccionado;
    });
  }

  /* ── cámara: rueda y arrastre ─────────────────────────────────────────── */
  let inicio: Toque | null = null;
  let ultimo: { x: number; y: number } | null = null;
  let arrastrando = false;

  const enVista = (e: PointerEvent | WheelEvent) => {
    const caja = app.canvas.getBoundingClientRect();
    return { x: e.clientX - caja.left, y: e.clientY - caja.top };
  };

  const alBajar = (e: PointerEvent) => {
    const p = enVista(e);
    inicio = { ...p, t: performance.now() };
    ultimo = p;
    arrastrando = false;
    // Capturar el puntero es necesario: sin esto, arrastrar y salir del lienzo
    // deja la escena pegada al puntero para siempre.
    try {
      app.canvas.setPointerCapture(e.pointerId);
    } catch {
      // Un navegador que no lo soporte pierde el arrastre fuera del lienzo y
      // nada más. No es motivo para no montar la escena.
    }
  };

  const alMover = (e: PointerEvent) => {
    if (!inicio || !ultimo) return;
    const p = enVista(e);
    if (!arrastrando && gesto(inicio, { ...p, t: performance.now() }) === 'arrastre') {
      arrastrando = true;
      app.canvas.style.cursor = 'grabbing';
    }
    if (arrastrando) camara.arrastrar(p.x - ultimo.x, p.y - ultimo.y);
    ultimo = p;
  };

  const alSubir = (e: PointerEvent) => {
    if (!inicio) return;
    const p = enVista(e);
    const cual = gesto(inicio, { ...p, t: performance.now() });
    app.canvas.style.cursor = '';
    try {
      app.canvas.releasePointerCapture(e.pointerId);
    } catch {
      /* ya liberado */
    }
    if (cual === 'clic') {
      // Pulsar el suelo deselecciona, y es deliberado: sin salida, el panel se
      // queda abierto y no hay forma de volver a ver la sala entera.
      marcar(puestoPulsado);
      for (const f of oyentes) f(puestoPulsado);
    }
    inicio = null;
    ultimo = null;
    arrastrando = false;
    puestoPulsado = null;
  };

  const alRodar = (e: WheelEvent) => {
    // Sin esto la rueda hace rodar la página además de la escena, y se pierde
    // la pantalla de vista mientras se intenta hacer zoom.
    e.preventDefault();
    camara.rueda(e.deltaY, enVista(e));
  };

  app.canvas.addEventListener('pointerdown', alBajar);
  app.canvas.addEventListener('pointermove', alMover);
  app.canvas.addEventListener('pointerup', alSubir);
  app.canvas.addEventListener('pointercancel', alSubir);
  app.canvas.addEventListener('wheel', alRodar, { passive: false });

  const ajustarVineta = () => {
    const v = vista();
    vineta.width = v.ancho;
    vineta.height = v.alto;
  };
  ajustarVineta();

  const alRedimensionar = () => {
    camara.redimensionar(vista());
    ajustarVineta();
  };
  const observador =
    typeof ResizeObserver !== 'undefined' ? new ResizeObserver(alRedimensionar) : null;
  observador?.observe(contenedor);

  /* ── el bucle ─────────────────────────────────────────────────────────── */
  let t = 0;
  let fps = 60;
  let fpsMinimo = Infinity;
  let acumulado = 0;
  let cuadros = 0;

  app.ticker.add((tick) => {
    // `deltaMS` es el tiempo real del fotograma. Se acota a 100 ms porque al
    // volver de una pestaña oculta el navegador entrega un salto enorme, y sin
    // tope la respiración del personaje da un brinco y la cámara se dispara.
    const dt = Math.min(0.1, tick.deltaMS / 1000);
    t += dt;

    camara.avanzar(dt);
    const tr = camara.transformacion();
    mundo.position.set(tr.x, tr.y);
    mundo.scale.set(tr.escala);

    oficina.animar(t, dt);

    for (const h of habitantes) {
      const pose = h.transicion.avanzar(dt, t);
      h.personaje?.aplicar(pose);

      const color = COLOR_DE_ANIMACION[h.transicion.destino] ?? PALETA.ember;
      h.puesto.halo.tint = color;
      h.puesto.halo.alpha = h.puesto.def.agente ? pose.aura * 0.42 : 0;
      h.puesto.testigo.tint = color;

      for (const b of h.puesto.brillos) b.pieza.alpha = b.base * pose.brilloPantalla;

      // El paquete: visible solo mientras hay despacho, recorriendo la recta
      // hacia el pasillo. Fuera de eso se oculta, no se deja quieto en el
      // camino: un paquete parado a mitad del pasillo parece un objeto olvidado.
      const visible = pose.despacho > 0.01 && pose.despacho < 0.99;
      h.puesto.paquete.visible = visible;
      if (visible) {
        const k = pose.despacho;
        h.puesto.paquete.position.set(
          h.recorrido.desde.x + (h.recorrido.hasta.x - h.recorrido.desde.x) * k,
          // Un arco, no una recta: el paquete se eleva y baja. Es lo que lo
          // hace parecer entregado en vez de deslizado por el suelo.
          h.recorrido.desde.y + (h.recorrido.hasta.y - h.recorrido.desde.y) * k - Math.sin(k * Math.PI) * 16
        );
        h.puesto.paquete.alpha = Math.min(1, Math.sin(k * Math.PI) * 2.2);
      }
    }

    acumulado += dt;
    cuadros++;
    if (acumulado >= 1) {
      fps = cuadros / acumulado;
      // El primer segundo incluye el montaje y siempre es malo: contarlo como
      // peor caso haría que la medición dijera 12 fps en una máquina que corre
      // a 60. Se empieza a medir el mínimo a partir del segundo segundo.
      if (t > 2) fpsMinimo = Math.min(fpsMinimo, fps);
      acumulado = 0;
      cuadros = 0;
    }
  });

  /**
   * ¿La escena sigue viva?
   *
   * Hace falta porque `destruir()` no es el final de las llamadas: el bucle de
   * quien la usa puede tener un fotograma en vuelo, y al cambiar de sala se
   * destruye una escena y se monta otra en el mismo gesto. Sin esta bandera,
   * `metricas()` entra a un `app.stage` que ya es `null` y revienta — y no
   * revienta sola: se lleva por delante el bucle entero, así que la escena
   * nueva se queda quieta sin un solo mensaje que lo explique.
   *
   * Encontrado el 30/10/2026 al construir el segundo departamento. Ninguna
   * prueba podía verlo: hasta ese día nunca se había desmontado una escena con
   * otra arrancando detrás.
   */
  let vivo = true;

  function contar(c: Container): number {
    let n = 1;
    for (const h of c.children) n += contar(h as Container);
    return n;
  }

  return {
    aplicar(estados) {
      if (!vivo) return;
      for (const e of estados || []) {
        const h = habitantes.find((x) => x.puesto.def.agente === e.agente);
        if (!h) continue;
        h.transicion.hacia(e.animacion);
        const texto = e.rotulo ?? '';
        if (h.puesto.rotulo.text !== texto) h.puesto.rotulo.text = texto;
        h.puesto.rotulo.visible = texto.length > 0;
      }
    },

    seleccionar(id) {
      if (!vivo) return;
      marcar(id);
    },

    enfocar(id) {
      if (!vivo) return;
      const h = habitantes.find((x) => x.puesto.def.id === id);
      if (!h) return;
      marcar(id);
      camara.mirarA(aPantalla(h.puesto.def.gx + 1, h.puesto.def.gy, 1));
    },

    encuadrar() {
      if (!vivo) return;
      camara.encuadrar();
    },

    alSeleccionar(f) {
      oyentes.add(f);
    },

    estadoVisualDe(idPuesto) {
      if (!vivo) return null;
      const h = habitantes.find((x) => x.puesto.def.id === idPuesto);
      if (!h) return null;
      return { animacion: h.transicion.destino, pose: { ...h.transicion.actual } };
    },

    medirDibujo(cuadros = 120) {
      if (!vivo) return { ms: 0, cuadros: 0 };
      const t0 = performance.now();
      for (let i = 0; i < cuadros; i++) app.renderer.render(app.stage);
      return { ms: Number(((performance.now() - t0) / cuadros).toFixed(3)), cuadros };
    },

    metricas() {
      if (!vivo) {
        return { fps: 0, fpsMinimo: 0, objetos: 0, motor: 'destruida', escala: 0 };
      }
      return {
        fps: Math.round(fps),
        fpsMinimo: Number.isFinite(fpsMinimo) ? Math.round(fpsMinimo) : Math.round(fps),
        objetos: contar(app.stage),
        motor: (app.renderer as any)?.name ?? (app.renderer as any)?.type ?? 'desconocido',
        escala: Number(camara.estado().actual.escala.toFixed(2))
      };
    },

    destruir() {
      //  Idempotente: destruir dos veces no puede explotar. Al cambiar de sala
      //  hay un desmontaje y un montaje en el mismo gesto, y basta con que el
      //  efecto de limpieza corra dos veces.
      if (!vivo) return;
      vivo = false;
      app.canvas.removeEventListener('pointerdown', alBajar);
      app.canvas.removeEventListener('pointermove', alMover);
      app.canvas.removeEventListener('pointerup', alSubir);
      app.canvas.removeEventListener('pointercancel', alSubir);
      app.canvas.removeEventListener('wheel', alRodar);
      observador?.disconnect();
      oyentes.clear();
      // El orden importa: primero la aplicación (que se lleva el árbol y el
      // contexto), después las texturas. Al revés, el renderizador intenta
      // liberar texturas ya liberadas y avisa por consola en cada salida.
      app.destroy(true, { children: true, texture: false });
      texturas.destruir();
    }
  };
}
