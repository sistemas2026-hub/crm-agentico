/**
 * EL SPIKE DE THREE.JS: la misma empresa, con volúmenes de verdad.
 *
 * Esto NO reemplaza a PixiJS. Es el prototipo comparable que se pidió el
 * 01/11/2026 para decidir con evidencia, y vive aparte justamente para que la
 * comparación sea honesta: si tocara los archivos de la escena actual, la
 * medición compararía dos versiones del mismo código.
 *
 * QUÉ SE INTENTA DEMOSTRAR, Y QUÉ NO
 *
 * Se intenta demostrar una sola cosa: que con profundidad real se puede tener
 * una planta COMPACTA —varias filas de oficinas por piso— sin que un piso tape
 * al de abajo, porque la visibilidad se resuelve apagando o atravesando capas
 * en vez de separándolas. En 2.5D ordenado por el pintor eso obliga a quince
 * unidades de aire entre losas y de ahí sale la franja larga.
 *
 * No se intenta demostrar que Three.js dibuje más bonito. Un motor no dibuja
 * bonito: dibuja lo que se le modela. Lo que cambia es QUÉ SE PUEDE MODELAR.
 *
 * TRES MODOS DE VER, que son las tres salidas que existen al problema:
 *   · `seccion`   — la fachada que mira a la cámara no se dibuja. Se ve dentro
 *                   de cada piso como en una sección arquitectónica.
 *   · `rayosX`    — las losas de arriba se vuelven traslúcidas y se ven los
 *                   tres pisos a la vez.
 *   · aislamiento — un solo piso, con nada encima. Acá no hay oclusión posible
 *                   y por eso es donde se garantiza que ningún departamento
 *                   queda escondido.
 */
import * as THREE from 'three';
import { edificioCompacto, NUCLEO, ALTURA_DE_PISO, ALTURA_DE_MURO } from './distribucion.js';
import { separarRotulos } from '../escena/rotulos.js';

/** Una celda del mundo, en unidades de Three. Las mismas que en la planta. */
const CELDA = 1;

const COLOR = {
  noche: 0x070b1c,
  explanada: 0x101738,
  hormigon: 0x6f7590,
  hormigonOscuro: 0x474d66,
  losa: 0x8b90a8,
  piso: 0xb9b3c9,
  pisoPasillo: 0xd2ccdd,
  tabique: 0x9b95b0,
  vidrio: 0x7fb0e8,
  madera: 0x7a5a3c,
  escritorio: 0x8f88a6,
  metal: 0xa6a1b8,
  silla: 0x4f4a6e,
  pantalla: 0x6fd3ff,
  calido: 0xffcf96,
  azul: 0x3d9bff,
  agente: 0x8ab4ff,
  persona: 0xffd27a,
  libre: 0x5a5570
};

/**
 * Monta el prototipo sobre un contenedor del DOM.
 *
 * Devuelve los mismos cuatro verbos que la escena de PixiJS —`aplicar`,
 * `seleccionar`, `metricas`, `destruir`— a propósito: si los dos prototipos
 * exponen la misma puerta, cambiar de motor es cambiar un archivo y no
 * reescribir la pantalla. Eso es parte de lo que la comparación tiene que
 * medir, y se mide construyéndolo.
 *
 * @param {HTMLElement} contenedor
 * @param {{ pisos: any[], soloNivel?: number|null, modo?: string,
 *           alSeleccionar?: (id: string|null) => void }} opciones
 */
export function montarThree(contenedor, opciones) {
  const pisos = opciones.pisos ?? [];
  let soloNivel = opciones.soloNivel ?? null;
  let modo = opciones.modo ?? 'corte';

  const renderizador = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  //  EL RECORTE POR PLANOS, que es la capacidad que el prototipo de PixiJS no
  //  tiene. Quita la esquina del edificio que mira a la camara y deja ver el
  //  interior de los tres pisos a la vez, como la seccion abierta de la
  //  referencia aprobada. En 2.5D habria que recortar cada sprite a mano.
  renderizador.localClippingEnabled = true;
  renderizador.setPixelRatio(Math.min(2, globalThis.devicePixelRatio || 1));
  renderizador.setSize(contenedor.clientWidth || 800, contenedor.clientHeight || 600);
  renderizador.shadowMap.enabled = true;
  //  `PCFSoftShadowMap` ya no existe en three 0.187: avisa y cae a este.
  renderizador.shadowMap.type = THREE.PCFShadowMap;
  renderizador.setClearColor(COLOR.noche, 1);
  contenedor.appendChild(renderizador.domElement);

  const escena = new THREE.Scene();
  //  SIN NIEBLA, y es una leccion y no una preferencia: la camara ortografica
  //  se coloca a 300 unidades para que el volumen de vista cubra el edificio,
  //  asi que una niebla pensada para distancias de escena -120 a 340- deja el
  //  edificio entero dentro del tramo opaco. La primera captura salio negra y
  //  parecia un problema de luz. La profundidad en ortografica se da con el
  //  contraste entre caras, no con la distancia.

  /* ── la cámara ortográfica isométrica ─────────────────────────────────── */
  //  Ortográfica y no en perspectiva: es lo que mantiene la lectura de plano
  //  —dos salas del mismo tamaño se ven del mismo tamaño estén donde estén— y
  //  es lo que hace que esto sea comparable con la isometría de PixiJS en vez
  //  de ser otra cosa.
  const camara = new THREE.OrthographicCamera(-50, 50, 30, -30, -400, 800);
  //  El ángulo isométrico clásico: igual distancia en los tres ejes.
  const DIRECCION = new THREE.Vector3(1, 0.88, 1).normalize();
  const objetivo = new THREE.Vector3(0, 0, 0);
  let zoom = 1;

  /* ── luz ───────────────────────────────────────────────────────────────── */
  //  Tres fuentes y ninguna más, por el mismo criterio que en PixiJS: subir el
  //  brillo general aplana todo. Lo que da volumen es que una cara reciba luz
  //  y la de al lado no.
  escena.add(new THREE.HemisphereLight(0x9db2dd, 0x11162e, 0.78));
  const sol = new THREE.DirectionalLight(0xdce7ff, 1.5);
  sol.position.set(60, 90, 40);
  sol.castShadow = true;
  sol.shadow.mapSize.set(1024, 1024);
  sol.shadow.camera.left = -90;
  sol.shadow.camera.right = 90;
  sol.shadow.camera.top = 90;
  sol.shadow.camera.bottom = -90;
  sol.shadow.camera.far = 400;
  sol.shadow.bias = -0.0012;
  escena.add(sol);
  const relleno = new THREE.DirectionalLight(0x7e95d8, 0.42);
  relleno.position.set(-50, 30, -40);
  escena.add(relleno);

  /* ── materiales compartidos ───────────────────────────────────────────── */
  //  Compartidos para que el número de llamadas de dibujo no crezca con el
  //  número de escritorios. Los que cambian por piso —las losas, que se
  //  vuelven traslúcidas en rayos X— se clonan por nivel.
  const mat = {
    losa: new THREE.MeshStandardMaterial({ color: COLOR.losa, roughness: 0.92 }),
    piso: new THREE.MeshStandardMaterial({ color: COLOR.piso, roughness: 0.95 }),
    pasillo: new THREE.MeshStandardMaterial({ color: COLOR.pisoPasillo, roughness: 0.95 }),
    tabique: new THREE.MeshStandardMaterial({ color: COLOR.tabique, roughness: 0.9 }),
    hormigon: new THREE.MeshStandardMaterial({ color: COLOR.hormigon, roughness: 0.95 }),
    hormigonOscuro: new THREE.MeshStandardMaterial({ color: COLOR.hormigonOscuro, roughness: 1 }),
    vidrio: new THREE.MeshPhysicalMaterial({
      color: COLOR.vidrio, roughness: 0.08, metalness: 0,
      transparent: true, opacity: 0.22, side: THREE.DoubleSide
    }),
    escritorio: new THREE.MeshStandardMaterial({ color: COLOR.escritorio, roughness: 0.75 }),
    madera: new THREE.MeshStandardMaterial({ color: COLOR.madera, roughness: 0.85 }),
    metal: new THREE.MeshStandardMaterial({ color: COLOR.metal, roughness: 0.4, metalness: 0.6 }),
    silla: new THREE.MeshStandardMaterial({ color: COLOR.silla, roughness: 0.8 }),
    pantalla: new THREE.MeshStandardMaterial({
      color: 0x0d1830, emissive: COLOR.pantalla, emissiveIntensity: 1.1, roughness: 0.3
    }),
    calido: new THREE.MeshBasicMaterial({
      color: COLOR.calido, transparent: true, opacity: 0.14,
      blending: THREE.AdditiveBlending, depthWrite: false
    }),
    agente: new THREE.MeshStandardMaterial({ color: COLOR.agente, roughness: 0.65 }),
    persona: new THREE.MeshStandardMaterial({ color: COLOR.persona, roughness: 0.65 }),
    libre: new THREE.MeshStandardMaterial({ color: COLOR.libre, roughness: 0.8 })
  };

  /* ── geometrías compartidas ───────────────────────────────────────────── */
  const geo = {
    caja: new THREE.BoxGeometry(1, 1, 1),
    cilindro: new THREE.CylinderGeometry(0.5, 0.5, 1, 10),
    esfera: new THREE.SphereGeometry(0.5, 12, 10),
    plano: new THREE.PlaneGeometry(1, 1)
  };

  /** Una caja con origen en su esquina mínima: así se piensa igual que la planta. */
  function caja(material, x, y, z, ancho, alto, fondo, padre) {
    const m = new THREE.Mesh(geo.caja, material);
    m.scale.set(ancho, alto, fondo);
    m.position.set(x + ancho / 2, y + alto / 2, z + fondo / 2);
    m.castShadow = true;
    m.receiveShadow = true;
    padre.add(m);
    return m;
  }

  const raiz = new THREE.Group();
  escena.add(raiz);

  /* ── los rótulos ──────────────────────────────────────────────────────── */
  //  En HTML y no en la escena, a propósito: un texto modelado en 3D encoge
  //  con el zoom y a escala de edificio no se lee —es el mismo problema que
  //  en PixiJS obligó a sacar los rótulos del mundo—. Y se reutiliza
  //  `separarRotulos`, que es el módulo del otro prototipo: la separación de
  //  nombres es un problema de pantalla y no depende del motor. Que se pueda
  //  compartir es, en sí mismo, un dato para la comparación.
  if (getComputedStyle(contenedor).position === 'static') contenedor.style.position = 'relative';
  const capaRotulos = document.createElement('div');
  capaRotulos.style.cssText =
    'position:absolute;inset:0;pointer-events:none;overflow:hidden;font:600 11px ui-sans-serif,system-ui,sans-serif';
  contenedor.appendChild(capaRotulos);
  /** @type {{nodo: HTMLElement, mundo: THREE.Vector3, ancho: number}[]} */
  let rotulos = [];

  /** Lo que se puede señalar con el puntero: cada sala por su identificador. */
  const seleccionables = [];
  /** Los grupos por nivel, para aislar y para los rayos X. */
  const porNivel = new Map();

  let edificio = edificioCompacto(pisos, { soloNivel });

  /* ── el suelo ─────────────────────────────────────────────────────────── */
  function construirSuelo(huella) {
    const g = new THREE.Group();
    const margen = 14;
    const explanada = new THREE.Mesh(
      geo.plano,
      new THREE.MeshStandardMaterial({ color: COLOR.explanada, roughness: 1 })
    );
    explanada.rotation.x = -Math.PI / 2;
    explanada.scale.set(huella.ancho + margen * 2, huella.fondo + margen * 2, 1);
    explanada.position.set(huella.ancho / 2, -0.6, huella.fondo / 2);
    explanada.receiveShadow = true;
    explanada.userData.esSuelo = true;
    g.add(explanada);
    //  El basamento: el edificio apoya en algo, no flota.
    const base = caja(mat.hormigonOscuro, -3, -0.6, -3, huella.ancho + 6, 0.6, huella.fondo + 6, g);
    base.userData.esSuelo = true;
    return g;
  }

  /* ── una sala ─────────────────────────────────────────────────────────── */
  function construirSala(puesta, y) {
    const g = new THREE.Group();
    const { sala, x, z, ancho, fondo } = puesta;

    //  El suelo de la sala, con el color de acento del departamento. Es lo que
    //  hace que dos departamentos se distingan desde arriba sin leer el rótulo.
    //  El acento del departamento, ACLARADO. El color que la empresa elige
    //  está pensado para un rótulo sobre fondo oscuro; como suelo, a plena
    //  saturación, convierte la planta en un tablero de parchís. Mezclado con
    //  el gris del piso conserva la identificación y deja que la luz mande.
    const acento = new THREE.MeshStandardMaterial({
      color: new THREE.Color(sala?.planta?.acento ?? COLOR.piso).lerp(
        new THREE.Color(COLOR.piso), 0.62
      ),
      roughness: 0.95
    });
    const suelo = caja(acento, x, y, z, ancho, 0.12, fondo, g);
    suelo.castShadow = false;
    suelo.userData.salaId = sala?.id ?? null;
    seleccionables.push(suelo);

    //  Tabiques bajos: altos cerrarían la sala y no se vería nada desde fuera;
    //  ausentes, el piso sería una explanada y no una oficina. A 2,2 se lee la
    //  división y se mira por encima.
    const h = 2.2;
    caja(mat.tabique, x, y, z, ancho, h, 0.25, g);
    caja(mat.tabique, x, y, z, 0.25, h, fondo, g);
    //  Los otros dos, más bajos: cerrar la sala por los cuatro lados a la
    //  misma altura la convierte en una caja y tapa lo de dentro desde la
    //  cámara. A 0,8 la planta se lee cerrada y se sigue viendo quién trabaja.
    const bajo = caja(mat.tabique, x, y, z + fondo - 0.25, ancho, 0.8, 0.25, g);
    const bajo2 = caja(mat.tabique, x + ancho - 0.25, y, z, 0.25, 0.8, fondo, g);
    bajo.castShadow = false;
    bajo2.castShadow = false;

    //  La luz cálida de la sala: un plano aditivo sobre el suelo. Ilumina ESTA
    //  sala y no sube el brillo de la escena, que es la diferencia entre
    //  «iluminado» y «lavado».
    const charco = new THREE.Mesh(geo.plano, mat.calido);
    charco.rotation.x = -Math.PI / 2;
    charco.scale.set(ancho - 1, fondo - 1, 1);
    charco.position.set(x + ancho / 2, y + 0.14, z + fondo / 2);
    g.add(charco);

    //  Los puestos, con el mismo origen que usa la plantilla.
    for (const p of sala?.planta?.puestos ?? []) {
      const px = x + (p.gx ?? 0) * CELDA;
      const pz = z + (p.gy ?? 0) * CELDA;
      construirPuesto(g, px, y + 0.12, pz, p);
    }
    return g;
  }

  /** Un escritorio con su silla, su pantalla y quien lo ocupa, si lo ocupa. */
  function construirPuesto(padre, x, y, z, p) {
    caja(mat.escritorio, x, y + 0.75, z, 2.2, 0.12, 1.2, padre);
    caja(mat.metal, x + 0.1, y, z + 0.1, 0.12, 0.75, 0.12, padre);
    caja(mat.metal, x + 2.0, y, z + 0.1, 0.12, 0.75, 0.12, padre);
    //  La pantalla, emisiva: es la fuente de luz que hace que un escritorio
    //  ocupado se lea distinto de uno vacío sin escribir «ocupado».
    const pantalla = caja(mat.pantalla, x + 0.6, y + 0.87, z + 0.15, 1.0, 0.6, 0.06, padre);
    pantalla.castShadow = false;

    const quien = p.agente ? mat.agente : p.persona ? mat.persona : null;
    if (!quien) return;

    //  Una figura sentada, deliberadamente simple: este prototipo compara
    //  arquitectura, no personajes. Lo que tiene que demostrar es que a esta
    //  escala una persona se distingue y da escala al edificio.
    const silla = caja(mat.silla, x + 0.65, y, z + 1.5, 0.9, 0.45, 0.9, padre);
    silla.castShadow = false;
    const torso = new THREE.Mesh(geo.cilindro, quien);
    torso.scale.set(0.62, 0.85, 0.5);
    torso.position.set(x + 1.1, y + 0.9, z + 1.95);
    torso.castShadow = true;
    padre.add(torso);
    const cabeza = new THREE.Mesh(geo.esfera, quien);
    cabeza.scale.setScalar(0.48);
    cabeza.position.set(x + 1.1, y + 1.45, z + 1.95);
    cabeza.castShadow = true;
    padre.add(cabeza);
  }

  /* ── el núcleo vertical ───────────────────────────────────────────────── */
  function construirNucleo(alto) {
    const g = new THREE.Group();
    //  La caja de escaleras, maciza, y el hueco del ascensor a su lado.
    caja(mat.hormigon, 0, 0, 0, NUCLEO.ancho * 0.55, alto, NUCLEO.fondo, g);
    const hueco = caja(
      mat.metal, NUCLEO.ancho * 0.6, 0, NUCLEO.fondo * 0.15,
      NUCLEO.ancho * 0.4, alto, NUCLEO.fondo * 0.7, g
    );
    hueco.material = mat.hormigonOscuro;

    //  Los peldaños, visibles: un núcleo liso es una columna, y lo que lo
    //  convierte en circulación es que se vea por dónde se sube.
    const peldanos = Math.floor(alto / 0.5);
    for (let i = 0; i < peldanos; i++) {
      const y = i * 0.5;
      const ida = Math.floor(y / (ALTURA_DE_PISO / 2)) % 2 === 0;
      const z = ida ? 0.6 + (i % 7) * 0.9 : NUCLEO.fondo - 1.5 - (i % 7) * 0.9;
      const p = caja(mat.hormigonOscuro, 0.4, y, z, NUCLEO.ancho * 0.4, 0.12, 0.8, g);
      p.castShadow = false;
    }

    //  La piel de vidrio, por fuera de todo y dibujada al final: es lo que lo
    //  hace torre y no muro. En PixiJS esto costó una pasada entera, porque
    //  una caja sin su cara frontal es un hueco entre dos muros; acá el buffer
    //  de profundidad lo resuelve solo, y esa diferencia es parte de lo que la
    //  comparación tiene que registrar.
    const piel = caja(mat.vidrio, -0.15, 0, -0.15, NUCLEO.ancho + 0.3, alto, NUCLEO.fondo + 0.3, g);
    piel.castShadow = false;
    piel.receiveShadow = false;
    //  La franja azul por planta: marca dónde para el ascensor.
    for (let n = 0; n * ALTURA_DE_PISO < alto; n++) {
      const banda = caja(
        new THREE.MeshBasicMaterial({ color: COLOR.azul, transparent: true, opacity: 0.55 }),
        -0.2, n * ALTURA_DE_PISO + ALTURA_DE_MURO - 0.6, -0.2,
        NUCLEO.ancho + 0.4, 0.18, NUCLEO.fondo + 0.4, g
      );
      banda.castShadow = false;
    }
    return g;
  }

  /* ── el edificio ──────────────────────────────────────────────────────── */
  function construir() {
    //  Vaciar lo anterior sin dejar geometría colgando: lo que no se libera no
    //  da error, solo se va poniendo lento hasta que el navegador tira el
    //  contexto. Es el mismo defecto que la escena de PixiJS documenta.
    raiz.clear();
    seleccionables.length = 0;
    porNivel.clear();
    capaRotulos.replaceChildren();
    rotulos = [];

    const { niveles, huella, alto } = edificio;
    if (niveles.length === 0) return;

    raiz.add(construirSuelo(huella));

    for (const nivel of niveles) {
      const g = new THREE.Group();
      g.userData.nivel = nivel.nivel;
      const y = nivel.gz;

      //  La losa del piso, que es el techo del de abajo. Material propio por
      //  nivel: en rayos X este es el que se vuelve traslúcido.
      const losa = caja(mat.losa.clone(), -1, y - 0.45, -1, huella.ancho + 2, 0.45, huella.fondo + 2, g);
      losa.userData.esLosa = true;
      g.userData.losa = losa;

      //  El suelo de circulación entre salas.
      const circulacion = caja(mat.pasillo, 0, y, 0, huella.ancho, 0.1, huella.fondo, g);
      circulacion.castShadow = false;

      //  LA LUZ DE DENTRO, una por piso y no una general.
      //
      //  Dos fuentes puntuales cálidas a media altura de la planta. Es la
      //  diferencia entre un edificio iluminado y uno aclarado: subir la luz
      //  ambiente hace que el interior y la fachada suban juntos y la escena
      //  se aplana. Lo que hace que un piso se vea habitado es que su interior
      //  esté más cálido que su envolvente.
      for (const f of [0.22, 0.5, 0.78]) {
        //  La intensidad va en cientos y no es un número grande por gusto:
        //  con `decay = 2` la luz cae con el cuadrado de la distancia, así que
        //  a diez unidades del foco 46 se convierte en 0,46 y no ilumina
        //  nada. La primera versión tenía las lámparas puestas y el interior
        //  seguía oscuro: el mecanismo estaba, el efecto no.
        const lampara = new THREE.PointLight(0xffc98a, 230, huella.ancho * 1.3, 2);
        lampara.position.set(huella.ancho * f, y + ALTURA_DE_PISO * 0.95, huella.fondo * (0.3 + (f % 0.5)));
        g.add(lampara);
      }

      for (const puesta of nivel.salas) {
        g.add(construirSala({ ...puesta, z: puesta.y }, y + 0.1));
        const nodo = document.createElement('div');
        nodo.textContent = puesta.sala?.rotulo ?? puesta.sala?.id ?? '';
        nodo.style.cssText =
          'position:absolute;transform:translate(-50%,-50%);white-space:nowrap;' +
          'background:#0b0a1ccc;color:#e8e7f5;border:1px solid #2c2a52;' +
          'border-radius:5px;padding:1px 5px;font-size:10px;';
        capaRotulos.appendChild(nodo);
        rotulos.push({
          nodo,
          //  Anclado al CENTRO de la sala y a la altura del tabique: sobre el
          //  suelo lo tapan los escritorios, y sobre el techo señalaría al
          //  piso de arriba.
          mundo: new THREE.Vector3(
            puesta.x + puesta.ancho / 2,
            y + 2.4,
            puesta.y + puesta.fondo / 2
          ),
          ancho: 0,
          visible: true
        });
      }

      //  Las dos fachadas QUE NO MIRAN A LA CÁMARA. Las otras dos se dejan
      //  abiertas: eso es la sección arquitectónica de la referencia, y es lo
      //  que permite ver dentro sin apagar nada.
      const h = ALTURA_DE_PISO - 0.45;
      caja(mat.vidrio, -1, y, -1, huella.ancho + 2, h, 0.3, g);
      caja(mat.vidrio, -1, y, -1, 0.3, h, huella.fondo + 2, g);
      //  Los montantes, cada cuatro celdas: sin ellos el vidrio es una lámina
      //  azul y no una fachada.
      for (let x = 0; x < huella.ancho + 2; x += 4) {
        const m = caja(mat.hormigon, x - 1, y, -1.1, 0.22, h, 0.3, g);
        m.castShadow = false;
      }
      for (let z = 0; z < huella.fondo + 2; z += 4) {
        const m = caja(mat.hormigon, -1.1, y, z - 1, 0.3, h, 0.22, g);
        m.castShadow = false;
      }

      raiz.add(g);
      porNivel.set(nivel.nivel, g);
    }

    //  El núcleo atraviesa todos los niveles: es una sola pieza, y eso es lo
    //  que lo hace circulación vertical y no tres rellanos sueltos.
    const alturaNucleo = soloNivel !== null ? ALTURA_DE_PISO : alto;
    raiz.add(construirNucleo(alturaNucleo));

    //  La cubierta y su remate, sólo en la vista de conjunto: aislado, un
    //  techo encima es exactamente lo que no se quiere mirar.
    if (soloNivel === null) {
      const { huella: hu } = edificio;
      //  La cubierta se marca para que «rayos X» la alcance. Sin esto el modo
      //  volvía traslúcidas las losas intermedias y dejaba la tapa opaca
      //  encima: se veía exactamente igual que antes, que es la peor forma de
      //  que un modo falle — el botón responde y no cambia nada.
      const antesDeLaCubierta = raiz.children.length;
      caja(mat.hormigon, -1, alto - 0.45, -1, hu.ancho + 2, 0.5, hu.fondo + 2, raiz);
      //  Las juntas del pavimento de cubierta. Sin ellas, cuarenta unidades de
      //  losa lisa se leen como una tapa puesta encima y no como un techo.
      for (let x = 4; x < hu.ancho; x += 6) {
        const j = caja(mat.hormigonOscuro, x, alto + 0.04, -1, 0.14, 0.04, hu.fondo + 2, raiz);
        j.castShadow = false;
      }
      for (let z = 4; z < hu.fondo; z += 6) {
        const j = caja(mat.hormigonOscuro, -1, alto + 0.04, z, hu.ancho + 2, 0.04, 0.14, raiz);
        j.castShadow = false;
      }
      caja(mat.hormigon, -1, alto, -1, hu.ancho + 2, 0.7, 0.3, raiz);
      caja(mat.hormigon, -1, alto, -1, 0.3, 0.7, hu.fondo + 2, raiz);
      //  Las máquinas de cubierta: lo que hace que un techo se lea como techo.
      caja(mat.metal, hu.ancho * 0.3, alto, hu.fondo * 0.3, 5, 1.6, 4, raiz);
      caja(mat.metal, hu.ancho * 0.6, alto, hu.fondo * 0.5, 3.4, 1.1, 3, raiz);
      for (let i = antesDeLaCubierta; i < raiz.children.length; i++) {
        raiz.children[i].userData.esCubierta = true;
      }
    }

    aplicarModo();
  }

  /**
   * Los planos que quitan la esquina del edificio que mira a la cámara.
   *
   * Dos planos y `clipIntersection = true`: con eso el material se conserva
   * donde se cumple UNO U OTRO —a la izquierda del corte O por detrás de él—,
   * que es justo el complemento de la esquina. Con la unión al revés, el valor
   * por defecto, se conservaría sólo la intersección y el edificio se quedaría
   * en una esquina sola.
   */
  const planosDeCorte = [
    new THREE.Plane(new THREE.Vector3(-1, 0, 0), 0),
    new THREE.Plane(new THREE.Vector3(0, 0, -1), 0)
  ];

  function colocarCorte() {
    const { huella } = edificio;
    //  El corte se lleva algo más de un tercio del frente: lo suficiente para
    //  ver dentro de los tres pisos y poco como para que el edificio siga
    //  leyéndose como un volumen cerrado y no como media maqueta.
    planosDeCorte[0].constant = huella.ancho * 0.62;
    planosDeCorte[1].constant = huella.fondo * 0.62;
  }

  /** Cómo se ve lo que hay encima del piso que se mira. */
  function aplicarModo() {
    //  En rayos X la cubierta se APAGA. Volverla traslúcida sobre tres losas
    //  también traslúcidas apila cuatro capas de transparencia y el resultado
    //  es una niebla lechosa donde no se distingue ningún piso.
    for (const hijo of raiz.children) {
      if (hijo.userData.esCubierta) hijo.visible = modo !== 'rayosX';
    }

    //  El recorte se aplica a TODOS los materiales: un muro recortado junto a
    //  un escritorio entero deja un escritorio flotando en el aire.
    colocarCorte();
    const recorta = modo === 'corte' && soloNivel === null;
    escena.traverse((o) => {
      if (!o.isMesh) return;
      const materiales = Array.isArray(o.material) ? o.material : [o.material];
      for (const m of materiales) {
        if (!m) continue;
        m.clippingPlanes = recorta ? planosDeCorte : null;
        m.clipIntersection = true;
        m.needsUpdate = true;
      }
    });

    for (const [nivel, g] of porNivel) {
      const losa = g.userData.losa;
      if (!losa) continue;
      const esElDeAbajo = nivel === Math.min(...porNivel.keys());
      if (modo === 'rayosX' && !esElDeAbajo) {
        losa.material.transparent = true;
        losa.material.opacity = 0.18;
        losa.material.depthWrite = false;
        losa.castShadow = false;
      } else {
        losa.material.transparent = false;
        losa.material.opacity = 1;
        losa.material.depthWrite = true;
        losa.castShadow = true;
      }
      losa.material.needsUpdate = true;
    }
  }

  construir();

  /* ── encuadre ─────────────────────────────────────────────────────────── */
  function encuadrar() {
    //  Mide el EDIFICIO y no la escena. La explanada se extiende catorce
    //  unidades más allá de la huella por cada lado, así que encuadrando
    //  `raiz` entera el edificio entraba ocupando un tercio de la pantalla y
    //  parecía una maqueta sobre una mesa vacía. Se marcó el suelo al
    //  construirlo y acá se salta: es el mismo error que «aprovechar el
    //  viewport» nombra en los criterios.
    const caja3 = new THREE.Box3();
    raiz.traverse((o) => {
      if (o.isMesh && !o.userData.esSuelo) caja3.expandByObject(o);
    });
    if (caja3.isEmpty()) return;
    caja3.getCenter(objetivo);
    const esfera = caja3.getBoundingSphere(new THREE.Sphere());
    const w = contenedor.clientWidth || 800;
    const h = contenedor.clientHeight || 600;
    const aspecto = w / h;
    //  El radio de la esfera envolvente garantiza que entra MIRE DESDE DONDE
    //  MIRE: con la caja proyectada habría que rehacer la cuenta en cada giro,
    //  y una vista que se recorta al girar es justo lo que se está evitando.
    const alto = esfera.radius * 1.08;
    camara.top = alto;
    camara.bottom = -alto;
    camara.left = -alto * aspecto;
    camara.right = alto * aspecto;
    zoom = 1;
    camara.zoom = zoom;
    camara.updateProjectionMatrix();
  }

  function colocarCamara() {
    const d = 300;
    camara.position.copy(objetivo).addScaledVector(DIRECCION, d);
    camara.lookAt(objetivo);
  }

  encuadrar();
  colocarCamara();

  /* ── el puntero: arrastrar mueve, la rueda acerca, soltar selecciona ───── */
  const rayo = new THREE.Raycaster();
  const puntero = new THREE.Vector2();
  let arrastrando = false;
  let movido = 0;
  let ultimo = { x: 0, y: 0 };

  const lienzo = renderizador.domElement;
  function alBajar(e) {
    arrastrando = true;
    movido = 0;
    ultimo = { x: e.clientX, y: e.clientY };
    lienzo.setPointerCapture?.(e.pointerId);
  }
  function alMover(e) {
    if (!arrastrando) return;
    const dx = e.clientX - ultimo.x;
    const dy = e.clientY - ultimo.y;
    movido += Math.abs(dx) + Math.abs(dy);
    ultimo = { x: e.clientX, y: e.clientY };
    //  Mover en el plano de la pantalla, no en el del mundo: arrastrar tiene
    //  que llevar el edificio adonde apunta el dedo.
    const derecha = new THREE.Vector3().crossVectors(camara.up, DIRECCION).normalize();
    const arriba = new THREE.Vector3().crossVectors(DIRECCION, derecha).normalize();
    const escala = (camara.top - camara.bottom) / (contenedor.clientHeight || 600) / camara.zoom;
    objetivo.addScaledVector(derecha, dx * escala);
    objetivo.addScaledVector(arriba, -dy * escala);
  }
  function alSubir(e) {
    if (!arrastrando) return;
    arrastrando = false;
    lienzo.releasePointerCapture?.(e.pointerId);
    //  Un arrastre no es un clic. Es el mismo defecto que ya se pagó en la
    //  escena de PixiJS: el `click` del navegador llega igual tras capturar el
    //  puntero, y seleccionaba al soltar en cualquier parte.
    if (movido > 6) return;
    const r = lienzo.getBoundingClientRect();
    puntero.x = ((e.clientX - r.left) / r.width) * 2 - 1;
    puntero.y = -((e.clientY - r.top) / r.height) * 2 + 1;
    rayo.setFromCamera(puntero, camara);
    const tocados = rayo.intersectObjects(seleccionables, false);
    opciones.alSeleccionar?.(tocados[0]?.object?.userData?.salaId ?? null);
  }
  function alRodar(e) {
    e.preventDefault();
    zoom = Math.min(6, Math.max(0.35, zoom * (e.deltaY > 0 ? 0.9 : 1.1)));
    camara.zoom = zoom;
    camara.updateProjectionMatrix();
  }
  lienzo.addEventListener('pointerdown', alBajar);
  lienzo.addEventListener('pointermove', alMover);
  lienzo.addEventListener('pointerup', alSubir);
  lienzo.addEventListener('wheel', alRodar, { passive: false });

  /* ── redimensionar ────────────────────────────────────────────────────── */
  function alRedimensionar() {
    const w = contenedor.clientWidth || 800;
    const h = contenedor.clientHeight || 600;
    renderizador.setSize(w, h);
    const alto = (camara.top - camara.bottom) / 2;
    camara.left = -alto * (w / h);
    camara.right = alto * (w / h);
    camara.updateProjectionMatrix();
  }
  const observador =
    typeof ResizeObserver !== 'undefined' ? new ResizeObserver(alRedimensionar) : null;
  observador?.observe(contenedor);

  /**
   * ¿Se ve la sala a la que apunta este rótulo, o la tapa algo?
   *
   * Se lanza un rayo desde la cámara hacia el ancla y se mira qué toca
   * primero. Si lo primero que encuentra está claramente más cerca que el
   * ancla, hay algo delante: la cubierta, la losa de arriba, otro muro.
   *
   * Existe porque sin esto el edificio mostraba «NOC y Redes» escrito sobre la
   * cubierta, señalando una sala que está dos plantas más abajo y que no se ve
   * desde ahí. Un rótulo que nombra lo que no está a la vista no informa:
   * desinforma, y es el mismo criterio por el que los rótulos se separan.
   */
  const rayoDeRotulo = new THREE.Raycaster();
  const origenAuxiliar = new THREE.Vector3();
  const direccionAuxiliar = new THREE.Vector3();

  /** ¿Este punto cae en la esquina que el corte se llevó? */
  function enLaEsquinaCortada(p) {
    return (
      modo === 'corte' &&
      soloNivel === null &&
      p.x > planosDeCorte[0].constant &&
      p.z > planosDeCorte[1].constant
    );
  }

  function salaVisible(mundo) {
    //  DOS COSAS QUE SE APRENDIERON MIDIENDO, las dos con el mismo síntoma:
    //  todos los rótulos desaparecían a la vez.
    //
    //  1. En cámara ORTOGRÁFICA los rayos son PARALELOS. Lanzarlo desde
    //     `camara.position` hacia el ancla es un rayo de perspectiva, que no
    //     es el que dibuja la pantalla. El rayo correcto sale de detrás del
    //     ancla, en la dirección de la cámara.
    //  2. El trazador de rayos NO CONOCE los planos de recorte. La esquina
    //     que el corte se llevó sigue ahí para él, así que todos los rayos
    //     chocaban con geometría invisible y no se veía nada.
    origenAuxiliar.copy(mundo).addScaledVector(DIRECCION, 500);
    direccionAuxiliar.copy(DIRECCION).negate();
    rayoDeRotulo.set(origenAuxiliar, direccionAuxiliar);
    const tocados = rayoDeRotulo.intersectObject(raiz, true);
    const distanciaAlAncla = 500;
    for (const t of tocados) {
      if (enLaEsquinaCortada(t.point)) continue;
      //  Medio metro de margen: el suelo de la propia sala está justo debajo
      //  del ancla y se tocaría a sí misma.
      return t.distance > distanciaAlAncla - 2.6;
    }
    return true;
  }

  //  El rayo no se lanza en cada fotograma: once rayos contra toda la escena,
  //  144 veces por segundo, es trabajo que nadie ve. Cada seis basta.
  let cuadrosDesdeLaPrueba = 0;

  /** Proyecta cada rótulo a la pantalla y los separa para que no se pisen. */
  function situarRotulos() {
    if (rotulos.length === 0) return;
    const probar = cuadrosDesdeLaPrueba++ % 6 === 0;
    const w = contenedor.clientWidth || 1;
    const h = contenedor.clientHeight || 1;
    const v = new THREE.Vector3();
    const cajas = rotulos.map((r) => {
      v.copy(r.mundo).project(camara);
      if (!r.ancho) r.ancho = r.nodo.offsetWidth || 80;
      return {
        x: ((v.x + 1) / 2) * w - r.ancho / 2,
        y: ((1 - v.y) / 2) * h,
        ancho: r.ancho,
        alto: 18
      };
    });
    if (probar) for (const r of rotulos) r.visible = salaVisible(r.mundo);
    const ys = separarRotulos(cajas);
    rotulos.forEach((r, i) => {
      r.nodo.style.display = r.visible === false ? 'none' : '';
      r.nodo.style.left = `${cajas[i].x + r.ancho / 2}px`;
      r.nodo.style.top = `${ys[i]}px`;
    });
  }

  /* ── el bucle ─────────────────────────────────────────────────────────── */
  let vivo = true;
  let fps = 60;
  let fpsMinimo = Infinity;
  let cuadros = 0;
  let acumulado = 0;
  let t = 0;
  let ultimoInstante = performance.now();

  function cuadro() {
    if (!vivo) return;
    const ahora = performance.now();
    const dt = Math.min(0.1, (ahora - ultimoInstante) / 1000);
    ultimoInstante = ahora;
    t += dt;

    colocarCamara();
    renderizador.render(escena, camara);
    situarRotulos();

    acumulado += dt;
    cuadros++;
    if (acumulado >= 1) {
      fps = cuadros / acumulado;
      //  Igual que en PixiJS: el primer segundo incluye el montaje y contarlo
      //  como peor caso diría 12 fps en una máquina que va a 60.
      if (t > 2) fpsMinimo = Math.min(fpsMinimo, fps);
      acumulado = 0;
      cuadros = 0;
    }
    requestAnimationFrame(cuadro);
  }
  requestAnimationFrame(cuadro);

  return {
    /** Cambiar qué piso se mira, o cómo. */
    aplicar(cambios = {}) {
      let rehacer = false;
      if ('soloNivel' in cambios && cambios.soloNivel !== soloNivel) {
        soloNivel = cambios.soloNivel;
        edificio = edificioCompacto(pisos, { soloNivel });
        rehacer = true;
      }
      if ('modo' in cambios && cambios.modo !== modo) {
        modo = cambios.modo;
        if (!rehacer) aplicarModo();
      }
      if (rehacer) {
        construir();
        encuadrar();
      }
    },
    encuadrar,
    metricas() {
      if (!vivo) return { fps: 0, fpsMinimo: 0, objetos: 0, motor: 'destruida' };
      let objetos = 0;
      escena.traverse(() => objetos++);
      return {
        fps: Math.round(fps),
        fpsMinimo: Number.isFinite(fpsMinimo) ? Math.round(fpsMinimo) : Math.round(fps),
        objetos,
        motor: 'three/webgl',
        llamadas: renderizador.info.render.calls,
        triangulos: renderizador.info.render.triangles
      };
    },
    destruir() {
      vivo = false;
      observador?.disconnect();
      lienzo.removeEventListener('pointerdown', alBajar);
      lienzo.removeEventListener('pointermove', alMover);
      lienzo.removeEventListener('pointerup', alSubir);
      lienzo.removeEventListener('wheel', alRodar);
      //  Liberar de verdad: en WebGL lo que no se libera no da error, se queda
      //  ocupando memoria de la tarjeta hasta que el navegador tira el
      //  contexto más viejo y la pantalla se va a negro sin un solo mensaje.
      escena.traverse((o) => {
        if (o.isMesh) {
          o.geometry?.dispose?.();
          if (Array.isArray(o.material)) o.material.forEach((m) => m.dispose?.());
          else o.material?.dispose?.();
        }
      });
      Object.values(geo).forEach((g) => g.dispose?.());
      Object.values(mat).forEach((m) => m.dispose?.());
      renderizador.dispose();
      lienzo.remove();
      capaRotulos.remove();
    }
  };
}
