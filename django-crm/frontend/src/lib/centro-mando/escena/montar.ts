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

import { Application, Container, Graphics, Sprite, Text } from 'pixi.js';
import { Camara, LIMITES, gesto, type Toque } from './camara';
import { aPantalla, extensionDeVolumenes, extensionDelMundo, profundidad } from './isometria';
import { construirCaminante, type Caminante } from './caminante';
import { avanzar, poblar } from '../ambiente.js';
import { CELDA, camino, celdaDe, llegadaA } from '../navegacion.js';
import {
  avanzar as avanzarPaseo, crearPaseo, enPie, mezcla, puedeArrancar
} from '../paseo.js';
import { PALETA, coloresConAcento } from './paleta';
import { Transicion } from './pose';
import { construirOficina, type Planta, type Puesto } from './oficina';
import { construirPersonaje, type Personaje } from './personaje';
import { generarTexturas } from './texturas';
import { ANIMACION_POR_TIPO, type Acontecimiento, type EstadoDeAgente } from './adaptador';
import { separarRotulos, type CajaDeRotulo } from './rotulos';

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
   * La planta, o LAS plantas.
   *
   * Una sola dibuja una sala. Varias dibujan el edificio: cada una se construye
   * exactamente igual, en sus propias coordenadas, y se desplaza entera por su
   * `origen`. Ninguna sala sabe que hay otras — por eso montar las seis no
   * obligó a tocar nada de `oficina.ts`.
   */
  planta: Planta | Planta[];
  /**
   * Hasta dónde se puede alejar la cámara.
   *
   * El límite normal es 0,4 y su motivo sigue siendo bueno: por debajo, en una
   * SALA, el mobiliario es una mancha y el texto no se lee. Un edificio entero
   * es otro objeto — se midió: once salas en tres niveles ocupan 3.552 × 2.946
   * píxeles de mundo, y caben en una vista de 1.625 × 600 a escala **0,204**.
   * Con el límite de la sala, la vista de conjunto nace recortada y no hay
   * forma de ver el edificio completo.
   *
   * Así que quien monta decide. No se baja el límite para todos: en una sala
   * no hace falta y el motivo por el que existe no cambió.
   */
  escalaMinima?: number;
  /**
   * Letreros anclados a un punto del mundo y dibujados en espacio de PANTALLA.
   *
   * No escalan con la cámara, y ese es todo el punto. Se midió: la vista de
   * conjunto entra a escala 0,2, así que un rótulo de 13 píxeles mide 2,6 y no
   * se lee. Agrandar la fuente no sirve —en una sala quedaría gigante—; lo que
   * hace falta es texto que no participe del zoom.
   *
   * Van en el escenario y no en el mundo, igual que la viñeta, y no son
   * interactivos: si lo fueran se comerían los clics de los puestos que tienen
   * detrás.
   */
  /**
   * El mapa por el que se puede caminar, y a dónde se puede ir.
   *
   * Sin esto NADIE se levanta de su silla: un personaje que camine sin mapa
   * atraviesa las paredes, y eso es peor que un personaje quieto.
   */
  navegacion?: {
    rejilla: any;
    /** Dónde se puede ir a dar una vuelta, en unidades del plano. */
    paseos: { x: number; y: number; ancho: number; fondo: number }[];
  };

  letreros?: {
    texto: string; gx: number; gy: number; gz: number;
    /**
     * Hacia dónde crece el letrero desde su ancla. Los de piso van a la
     * izquierda —se anclan al borde del núcleo, que es la única franja del
     * encuadre sin edificio— y los de sala van a la derecha, sobre su propia
     * losa.
     */
    hacia?: 'izquierda' | 'derecha';
    /** Cuerpo de letra. Los de sala son menores que los de piso: hay once. */
    cuerpo?: number;
    /**
     * El acento del área, para que el rótulo diga de cuál es sin leerlo.
     *
     * De lejos el nombre no se lee pero el color sí, y eso es la mitad de la
     * legibilidad de una planta con once departamentos: mirada de conjunto,
     * la sede era una mancha gris uniforme.
     */
    color?: number;
  }[];
  /**
   * Las zonas de circulación por las que puede caminar gente de ambiente.
   *
   * Sin esto no hay nadie caminando, y esa es la omisión correcta: una sala
   * mirada sola no tiene por dónde cruzar, y una figura dando vueltas dentro
   * de un departamento estaría pisando puestos declarados.
   *
   * Lo que se dibuja acá NO es nadie de la empresa: no tiene nombre, no se
   * puede pulsar, no entra en ningún contador y no produce un acontecimiento.
   * Ver `ambiente.js`.
   */
  ambiente?: { x: number; y: number; ancho: number; fondo: number }[];
}

interface Habitante {
  puesto: Puesto;
  /** Lo último que pasó en este puesto, si hay algo vigente. */
  acontecimiento: Acontecimiento | null;
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

  const plantas = Array.isArray(opciones.planta) ? opciones.planta : [opciones.planta];

  /* El mundo entero cuelga de un contenedor al que se le aplica la cámara. */
  const mundo = new Container();
  mundo.sortableChildren = true;
  app.stage.addChild(mundo);

  /*  Una sala por planta, cada una en su contenedor desplazado.
   *
   *  El orden entre salas lo da la profundidad de su origen: la de delante se
   *  dibuja después. Dentro de cada una el orden sigue siendo el suyo. Es una
   *  simplificación honesta y tiene un límite: si dos salas se SOLAPARAN en la
   *  rejilla, habría que intercalar sus objetos y esto no lo hace. Por eso el
   *  reparto deja pasillo entre ellas. */
  const salas = plantas.map((planta) => {
    const o = { gz: 0, ...(planta.origen ?? { gx: 0, gy: 0 }) };
    const oficina = construirOficina(planta, texturas);
    const caja = new Container();
    //  La altura entra en la posición, que es lo único que hace falta para
    //  apilar un nivel: en esta proyección `gz` se RESTA de la `y`.
    const p = aPantalla(o.gx, o.gy, o.gz);
    caja.position.set(p.x, p.y);
    //  EL ORDEN ENTRE NIVELES NO ES EL ORDEN DENTRO DE UN NIVEL, y mezclarlos
    //  es lo que rompe un edificio.
    //
    //  Dentro de un nivel manda la profundidad: lo de delante se dibuja
    //  después. Entre niveles manda la ALTURA: el piso de arriba se dibuja
    //  después del de abajo, porque su losa tapa el fondo del de abajo y eso
    //  es justamente lo que hace que se lea como un edificio y no como tres
    //  bandejas transparentes.
    //
    //  Por eso la altura multiplica: con `profundidad(gx, gy, gz)` —que pesa
    //  `gz` por 0,001— un nivel entero quedaría intercalado con el de abajo
    //  según su coordenada, y el resultado es un piso que asoma por dentro de
    //  otro. Se midió al construirlo.
    //  Una pieza larga de la envolvente fija la suya: ver `Planta.profundidad`.
    caja.zIndex = planta.profundidad ?? (o.gz * 1000 + profundidad(o.gx, o.gy));
    caja.addChild(oficina.raiz);
    mundo.addChild(caja);
    return { oficina, origen: o };
  });

  const oficina = {
    //  El recinto que la cámara encuadra: la unión de todas las salas.
    mundo: {
      ancho: Math.max(...salas.map((s) => s.origen.gx + s.oficina.mundo.ancho)),
      fondo: Math.max(...salas.map((s) => s.origen.gy + s.oficina.mundo.fondo)),
      //  La altura del edificio es la del nivel más alto MÁS su propio muro.
      //  Tomar sólo el alto de las salas dejaba los pisos de arriba fuera del
      //  encuadre: la cámara los limitaba contra un recinto de cuatro
      //  unidades y el tercer piso quedaba cortado por arriba.
      alto: Math.max(...salas.map((s) => s.origen.gz + s.oficina.mundo.alto))
    },
    puestos: salas.flatMap((s) => s.oficina.puestos),
    animar(t: number, dt: number) {
      for (const s of salas) s.oficina.animar(t, dt);
    },
    destruir() {
      for (const s of salas) s.oficina.destruir();
    }
  };

  /* ── los letreros de pantalla ─────────────────────────────────────────── */
  const letreros = (opciones.letreros ?? []).map((l) => {
    const nodo = new Container();
    nodo.eventMode = 'none';
    const texto = new Text({
      text: l.texto,
      style: {
        fontFamily: 'ui-sans-serif, system-ui, sans-serif',
        fontSize: l.cuerpo ?? 13,
        fontWeight: '700',
        fill: 0xe8e7f5,
        letterSpacing: (l.cuerpo ?? 13) >= 13 ? 1.4 : 0.6
      },
      resolution: 2
    });
    const aLaDerecha = l.hacia === 'derecha';
    texto.anchor.set(aLaDerecha ? 0 : 1, 0.5);
    //  Una placa detrás del texto: sobre el suelo oscuro se lee, pero sobre
    //  una pantalla encendida o una losa clara se pierde. Cuesta un polígono.
    const placa = new Graphics();
    const alto = Math.round((l.cuerpo ?? 13) * 1.7);
    const izq = aLaDerecha ? -6 : -texto.width - 14;
    placa.roundRect(izq, -alto / 2, texto.width + 20, alto, 6)
      .fill({ color: 0x0b0a1c, alpha: 0.72 })
      .stroke({ width: 1, color: l.color ?? 0x2c2a52, alpha: l.color ? 0.95 : 0.9 });
    //  Y una pastilla del color del área pegada al borde. El contorno solo no
    //  alcanza: a tamaño de pantalla es una línea de un píxel y se pierde
    //  contra el fondo. La pastilla es lo que se ve desde lejos.
    if (l.color !== undefined) {
      placa.roundRect(izq + 3, -alto / 2 + 3, 3, alto - 6, 1.5)
        .fill({ color: l.color, alpha: 0.95 });
    }
    //  La guía que une la placa con su ancla cuando hubo que bajarla para que
    //  no se pisara con otra. Va PRIMERO para quedar detrás de la placa, y
    //  existe por una razón de verdad y no de adorno: un nombre corrido tres
    //  líneas hacia abajo señalaría la sala equivocada, y un rótulo que miente
    //  sobre a quién nombra es peor que dos rótulos encimados.
    const guia = new Graphics();
    nodo.addChildAt(guia, 0);
    nodo.addChild(placa);
    nodo.addChild(texto);
    app.stage.addChild(nodo);
    //  El punto del mundo al que queda atado, ya proyectado: no cambia nunca,
    //  así que se calcula una vez.
    const ancla = aPantalla(l.gx, l.gy, l.gz);
    return {
      nodo,
      ancla,
      guia,
      //  Lo que mide la placa, para la separación. El borde izquierdo depende
      //  de hacia dónde crece, igual que al dibujarla.
      izquierda: aLaDerecha ? -6 : -texto.width - 14,
      ancho: texto.width + 20,
      alto,
      //  Lo último que se dibujó en la guía, para no rehacerla cada fotograma.
      corrida: 0
    };
  });

  /* ── la viñeta ────────────────────────────────────────────────────────── */
  /* Va en el ESCENARIO y no en el mundo: oscurece las esquinas de la vista,
     que es lo que hace que la mirada caiga donde está la acción. Dentro del
     mundo se movería con la cámara y sería una mancha persiguiendo al suelo.
     No es interactiva: sin esto se come todos los clics del lienzo. */
  const vineta = new Sprite(texturas.vineta);
  vineta.eventMode = 'none';
  app.stage.addChild(vineta);

  //  LA CÁMARA ENCUADRA LO QUE HAY, NO EL CUBO QUE LO ENVUELVE.
  //
  //  Con una sola planta las dos cosas coinciden y se usa la de siempre. Con un
  //  edificio no: sus niveles están escalonados y la esquina alta del fondo es
  //  aire. Medirla estiraba la caja casi 900 píxeles hacia arriba y el encuadre
  //  terminaba ajustando por alto, con el edificio ocupando el 40% del ancho.
  const extension = salas.length > 1
    ? extensionDeVolumenes(salas.map((s) => ({ origen: s.origen, mundo: s.oficina.mundo })))
    : extensionDelMundo(oficina.mundo);
  const vista = () => ({
    ancho: contenedor.clientWidth || 960,
    alto: contenedor.clientHeight || 600
  });
  //  Los límites de ESTA escena. `escalaMinima` sólo afloja el piso del zoom;
  //  todo lo demás —el tope, el paso de la rueda, el margen— es igual, porque
  //  esos no dependen de qué se esté mirando.
  const limites = opciones.escalaMinima
    ? { ...LIMITES, escalaMin: Math.min(opciones.escalaMinima, LIMITES.escalaMin) }
    : LIMITES;
  const camara = new Camara(extension, vista(), limites);

  /* ── los habitantes ───────────────────────────────────────────────────── */
  const habitantes: Habitante[] = oficina.puestos.map((puesto, asiento) => {
    let personaje: Personaje | null = null;
    //  UNA PERSONA DEL EQUIPO TAMBIEN SE DIBUJA, y su aspecto sale de su
    //  nombre igual que el de un agente. Lo que NO tiene es halo ni estado: no
    //  hay un flujo de eventos que la represente, y animarla seria inventar
    //  actividad. Ver el bucle de abajo.
    const quien = puesto.def.agente || puesto.def.persona;
    if (quien) {
      //  El nombre del agente decide su aspecto: ropa, pelo y piel. Sin esto
      //  ocho departamentos son la misma persona clonada cuarenta veces, que
      //  es lo primero que delata que la oficina es un fondo repetido.
      personaje = construirPersonaje(texturas, quien, asiento);
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
      //  EL RELOJ DE ESTA PERSONA. Derivado del asiento y no aleatorio: dos
      //  cargas seguidas tienen que dar la misma escena, o una captura deja de
      //  poder compararse con la anterior.
      //
      //  1,37 y 0,37 no son redondos a propósito — con un paso entero los
      //  desfases se repiten cada pocos asientos y vuelven a aparecer filas
      //  enteras sincronizadas, que es el defecto que esto arregla.
      transicion: new Transicion(
        personaje ? 'reposo' : 'incognito',
        0.18,
        asiento * 1.37,
        1 + (((asiento * 0.37) % 1) - 0.5) * 0.16
      ),
      acontecimiento: null,
      recorrido: { desde, hasta }
    };
  });

  /* ── los marcadores de presencia ──────────────────────────────────────── */

  /**
   * UN PUNTO DE PANTALLA POR PUESTO OCUPADO, SÓLO CUANDO SE MIRA DE LEJOS.
   *
   * EL PROBLEMA, medido el 31/10/2026 contra la referencia: la vista de
   * conjunto entra a escala 0,2, y una persona sentada —que ya se dibuja un 18%
   * más grande que su medida estricta— mide ahí diez píxeles. El edificio se
   * lee, los departamentos se leen, y **la gente no**. Una sede donde no se ve
   * a nadie no parece una empresa trabajando: parece una maqueta.
   *
   * Agrandar el personaje no sirve: a escala de sala quedaría gigante, que es
   * la misma razón por la que los nombres de piso pasaron a ser letreros.
   *
   * Lo que NO es: un adorno ni una animación de ambiente. Cada punto marca una
   * ocupación DECLARADA —el mismo dato que el pie cuenta— y toma el color del
   * estado que ya tiene el halo de ese puesto. No inventa actividad: cuando el
   * agente está en reposo, el punto está en reposo.
   *
   * Y desaparece al acercarse. A partir de cierto zoom el personaje ya se ve,
   * y dejar el punto encima sería tapar justo lo que se vino a mirar.
   */
  const UMBRAL_PRESENCIA = 0.45;
  const presencias = new Container();
  presencias.eventMode = 'none';
  app.stage.addChild(presencias);

  const marcadores = new Map<string, { nodo: Graphics; ancla: { x: number; y: number } }>();
  for (const s of salas) {
    for (const p of s.oficina.puestos) {
      if (!p.def.agente && !p.def.persona) continue;
      const g = new Graphics();
      //  Un punto con anillo: el anillo es lo que lo separa del fondo claro de
      //  una oficina iluminada. Sin él, sobre el suelo nuevo, desaparecía.
      g.circle(0, 0, 4.6).fill({ color: PALETA.placa, alpha: 0.72 });
      g.circle(0, 0, 2.8).fill({ color: 0xffffff });
      marcadores.set(p.def.id, {
        nodo: g,
        ancla: aPantalla(
          s.origen.gx + p.def.gx + 1,
          s.origen.gy + p.def.gy + 0.4,
          (s.origen.gz ?? 0) + 2.9
        )
      });
      presencias.addChild(g);
    }
  }

  /* Un puesto vacío no tiene estado que mostrar: su placa lo dice y su halo se
     queda apagado. Dejarlo en `incognito` con el signo de interrogación sería
     afirmar que no sabemos algo que sí sabemos — que ahí no hay nadie. */
  for (const h of habitantes) {
    if (!h.puesto.def.agente) {
      h.puesto.testigo.tint = PALETA.incognito;
      h.puesto.halo.alpha = 0;
      //  UNA PERSONA DEL EQUIPO NO ENTRA AQUI EN `incognito`, y no hace falta
      //  corregirlo: arriba ya quedo en `reposo` porque tiene personaje. El
      //  signo de interrogacion dice «no se que pasa ahi»; de una persona se
      //  sabe perfectamente -- esta sentada y el motor no la representa. Lo
      //  que si se apaga es el halo, que es lo correcto: no hay flujo de
      //  eventos que la anime, y animarla seria inventar actividad.
    }
  }

  /*  Los colores de estado con el acento de esta sala. Los de alarma NO
      cambian: un rojo tiene que ser el mismo rojo en las ocho. */
  //  Con varias salas el acento de los estados es el de la primera: los
  //  colores de alarma no cambian nunca y el de «normal» tiene que ser uno
  //  solo cuando se ven todas a la vez, o el mismo estado se vería de seis
  //  colores distintos en la misma pantalla.
  const colores = coloresConAcento(plantas[0]?.acento);

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
    //  LA RUEDA DESPLAZA; EL ZOOM PIDE CTRL. Es como se mueve un lienzo en
    //  Canva o en Figma, y es lo que la revisión pidió por su nombre. De
    //  regalo, el pellizco de un panel táctil llega como una rueda con
    //  `ctrlKey`, así que el zoom de dos dedos funciona sin nada más.
    if (e.ctrlKey || e.metaKey) {
      camara.rueda(e.deltaY, enVista(e));
      return;
    }
    //  Con mayúsculas, la rueda vertical desplaza en horizontal: es la
    //  convención de todos los lienzos y la única forma de recorrer una
    //  planta ancha con un ratón de una sola rueda.
    const dx = e.shiftKey ? -e.deltaY : -e.deltaX;
    const dy = e.shiftKey ? 0 : -e.deltaY;
    camara.arrastrar(dx, dy);
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

  /* ── la gente que cruza ───────────────────────────────────────────────── */
  /* Van al MUNDO y no a una sala: su `zIndex` se recalcula cada fotograma con
     la misma `profundidad` que ordena todo lo demás, así que Pixi las intercala
     sola entre las manzanas. Es lo que hace barato que caminen —no hay que
     reordenar nada a mano— y también por qué sólo pueden ir por la circulación:
     a nivel de mundo una figura se pinta entera delante o detrás de una sala,
     nunca entre sus muebles. */
  let gente = poblar(opciones.ambiente ?? []);
  const caminantes: Caminante[] = gente.map((f: any) => {
    const c = construirCaminante(f.oficio);
    c.nodo.eventMode = 'none';
    mundo.addChild(c.nodo);
    return c;
  });

  /* ── el paseo: alguien se levanta, camina y vuelve ─────────────────────
     El cuerpo que camina NO es el personaje sentado: `personaje.ts` dibuja a
     alguien en su silla y estirarle las piernas se ve como lo que es. Se usa
     el mismo `caminante.ts` del ambiente, y durante el medio segundo de
     levantarse los dos se cruzan en opacidad sobre el mismo punto — que es lo
     que evita el salto.

     SOLO SE LEVANTAN LOS PUESTOS OCUPADOS. Una silla vacía que se pone de pie
     y camina sería una persona inventada. */
  const navegable = opciones.navegacion ?? null;
  const paseantes = navegable
    ? habitantes
        .filter((h) => h.personaje && (h.puesto.def.agente || h.puesto.def.persona))
        .map((h, i) => ({
          habitante: h,
          paseo: crearPaseo(h.puesto.def.id, i * 17 + 5),
          cuerpo: null as Caminante | null
        }))
    : [];

  /** Una vuelta por el pasillo desde el puesto, o `null` si no hay camino. */
  const planearPaseo = (idPuesto: string) => {
    if (!navegable) return null;
    const silla = llegadaA(navegable.rejilla, idPuesto);
    if (!silla) return null;
    const zonas = navegable.paseos ?? [];
    if (zonas.length === 0) return null;
    //  Un punto del pasillo, elegido de forma estable por el identificador:
    //  dos cargas seguidas tienen que dar el mismo paseo.
    let suma = 0;
    for (let k = 0; k < idPuesto.length; k++) suma += idPuesto.charCodeAt(k);
    const z = zonas[suma % zonas.length];
    const destino = celdaDe(
      z.x + z.ancho * (0.3 + ((suma % 7) / 7) * 0.4),
      z.y + z.fondo * (0.2 + ((suma % 11) / 11) * 0.6));
    const ida = camino(navegable.rejilla, silla, destino);
    if (!ida || ida.length < 3) return null;
    //  UNA VUELTA CORTA, NO UNA EXCURSIÓN. Medido en el navegador: con la ruta
    //  entera hasta el punto elegido, el cuerpo estaba fuera de su silla unos
    //  40 segundos de cada 70 —el contador de objetos lo mostraba subido más
    //  de la mitad del tiempo—. Eso no se lee como «alguien se levantó un
    //  momento» sino como que la oficina está medio vacía.
    //
    //  Se corta la ida a 24 celdas: doce unidades de ida y doce de vuelta, que
    //  a 1,5 por segundo son unos dieciséis segundos de paseo.
    const corta = ida.slice(0, Math.min(ida.length, 24));
    if (corta.length < 3) return null;
    return { ida: corta, vuelta: [...corta].reverse() };
  };

  app.ticker.add((tick) => {
    // `deltaMS` es el tiempo real del fotograma. Se acota a 100 ms porque al
    // volver de una pestaña oculta el navegador entrega un salto enorme, y sin
    // tope la respiración del personaje da un brinco y la cámara se dispara.
    const dt = Math.min(0.1, tick.deltaMS / 1000);
    t += dt;

    if (caminantes.length > 0) {
      gente = gente.map((f: any) => avanzar(f, dt, opciones.ambiente ?? []));
      for (let i = 0; i < caminantes.length; i++) {
        const f: any = gente[i];
        const p = aPantalla(f.x, f.y, 0);
        caminantes[i].nodo.position.set(p.x, p.y);
        caminantes[i].nodo.zIndex = profundidad(f.x, f.y);
        caminantes[i].paso(t, f.andando === true);
      }
    }

    //  EL PASEO. Se avanza el estado de cada uno y se mueve su cuerpo.
    for (const p of paseantes) {
      const antes = p.paseo;
      //  `puedeArrancar` mira a los demás: como mucho uno fuera de su silla.
      const puede = antes.estado !== 'sentado'
        || puedeArrancar(paseantes.map((q) => q.paseo));
      p.paseo = puede
        ? avanzarPaseo(antes, dt, { celda: CELDA, planear: () => planearPaseo(p.paseo.puesto) })
        : { ...antes, espera: Math.max(antes.espera, 2) };

      const m = mezcla(p.paseo);
      //  La silla se vacía a la vez que aparece el cuerpo de pie: los dos
      //  extremos de la misma transición, no un corte.
      if (p.habitante.personaje) p.habitante.personaje.nodo.alpha = 1 - m;

      if (enPie(p.paseo) && p.paseo.donde) {
        if (!p.cuerpo) {
          p.cuerpo = construirCaminante('visita');
          p.cuerpo.nodo.eventMode = 'none';
          mundo.addChild(p.cuerpo.nodo);
        }
        const q = aPantalla(p.paseo.donde.gx, p.paseo.donde.gy, 0);
        p.cuerpo.nodo.position.set(q.x, q.y);
        p.cuerpo.nodo.zIndex = profundidad(p.paseo.donde.gx, p.paseo.donde.gy);
        p.cuerpo.nodo.alpha = m;
        p.cuerpo.paso(t, p.paseo.estado === 'yendo' || p.paseo.estado === 'volviendo');
      } else if (p.cuerpo) {
        p.cuerpo.destruir();
        p.cuerpo = null;
        if (p.habitante.personaje) p.habitante.personaje.nodo.alpha = 1;
      }
    }

    camara.avanzar(dt);
    const tr = camara.transformacion();
    mundo.position.set(tr.x, tr.y);
    mundo.scale.set(tr.escala);

    //  Los letreros siguen a su punto del mundo SIN escalar: se aplica la
    //  misma transformación al ancla y se deja el texto a tamaño de pantalla.
    //
    //  Y ahí está el problema que resuelve `separarRotulos`: las anclas sí
    //  encogen con la cámara, el texto no. En la vista de conjunto once anclas
    //  separadas por cuatro celdas caen a doce píxeles y los nombres se montan.
    //  La separación se recalcula cada fotograma porque depende de la cámara:
    //  no hay una colocación fija que sirva a todas las escalas.
    const cajas: CajaDeRotulo[] = letreros.map((l) => ({
      x: l.ancla.x * tr.escala + tr.x + l.izquierda,
      y: l.ancla.y * tr.escala + tr.y,
      ancho: l.ancho,
      alto: l.alto
    }));
    const ys = separarRotulos(cajas);
    for (let i = 0; i < letreros.length; i++) {
      const l = letreros[i];
      l.nodo.position.set(l.ancla.x * tr.escala + tr.x, ys[i]);
      const corrida = ys[i] - cajas[i].y;
      //  Redibujar la guía sólo cuando cambió de verdad: a 144 cuadros por
      //  segundo, once `clear()` por fotograma se notan y no hacen falta.
      if (Math.abs(corrida - l.corrida) > 0.5) {
        l.corrida = corrida;
        l.guia.clear();
        //  Nace en el BORDE de la placa y no en su centro: dibujada desde el
        //  centro queda tapada por la placa misma y no se ve nunca —así nació,
        //  y así era código que no dibujaba nada—. Y sólo cuando el tirón
        //  saca el ancla fuera de la placa: por debajo de eso el rótulo sigue
        //  tocando su sala y una línea sobraría.
        const borde = l.alto / 2 + 1;
        if (corrida > borde + 2) {
          l.guia
            .moveTo(0, -corrida)
            .lineTo(0, -borde)
            .stroke({ width: 1, color: 0x6f6ba6, alpha: 0.75 })
            .circle(0, -corrida, 1.8)
            .fill({ color: 0x8f8bc6, alpha: 0.9 });
        }
      }
    }

    //  Los marcadores de presencia, con la misma transformación y el mismo
    //  motivo: lo que tiene que leerse de lejos no puede encoger con el zoom.
    presencias.visible = tr.escala < UMBRAL_PRESENCIA;
    if (presencias.visible) {
      for (const m of marcadores.values()) {
        m.nodo.position.set(m.ancla.x * tr.escala + tr.x, m.ancla.y * tr.escala + tr.y);
      }
    }

    oficina.animar(t, dt);

    for (const h of habitantes) {
      const pose = h.transicion.avanzar(dt, t);
      h.personaje?.aplicar(pose);

      const color = colores[h.transicion.destino] ?? PALETA.ember;
      //  EL MARCADOR TOMA EL ESTADO QUE YA TIENE EL HALO, no uno propio. Dos
      //  sitios que deciden el color del mismo puesto es la forma más segura
      //  de que un día digan cosas distintas, y el de lejos es el que se cree.
      const marca = marcadores.get(h.puesto.def.id);
      if (marca) marca.nodo.tint = h.puesto.def.agente ? color : PALETA.luzCalida;
      h.puesto.halo.tint = color;
      h.puesto.halo.alpha = h.puesto.def.agente ? pose.aura * 0.42 : 0;
      h.puesto.testigo.tint = color;

      for (const b of h.puesto.brillos) b.pieza.alpha = b.base * pose.brilloPantalla;

      //  EL AVISO: lo último que pasó, al lado de la placa y al margen de si
      //  el personaje sigue trabajando. Las dos señales conviven; una no
      //  reemplaza a la otra.
      const suceso = h.acontecimiento;
      const vivo = suceso && (suceso.hasta == null || suceso.hasta > Date.now());
      h.puesto.aviso.visible = !!vivo;
      if (vivo) {
        const tono = colores[ANIMACION_POR_TIPO[suceso.tipo] ?? 'reposo'] ?? PALETA.ember;
        for (const hijo of h.puesto.aviso.children) (hijo as any).tint = tono;
        //  Late despacio: un aviso fijo se confunde con un adorno de la placa.
        h.puesto.aviso.alpha = 0.72 + Math.sin(t * 3.4) * 0.28;
      }

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
        h.acontecimiento = e.acontecimiento ?? null;
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
      //  Las figuras de ambiente primero: son hijas del mundo y `app.destroy`
      //  se las lleva, pero liberarlas a mano deja claro que son nuestras y no
      //  de la escena.
      for (const c of caminantes) c.destruir();
      caminantes.length = 0;
      //  Los cuerpos de los paseos tambien: si no, salir y entrar de la
      //  pantalla deja figuras sueltas en memoria de la tarjeta.
      for (const p of paseantes) { p.cuerpo?.destruir(); p.cuerpo = null; }
      paseantes.length = 0;
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
