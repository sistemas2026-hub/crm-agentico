/**
 * EL RECINTO: suelo, muros, mobiliario y el mural de pantallas.
 *
 * No sabe nada de lo que pasa en la empresa. Recibe una lista de puestos con su
 * posición y devuelve un contenedor dibujado más un `animar(t, dt)` para lo que
 * se mueve por sí solo —las pantallas del mural, los testigos de los equipos,
 * la luz—. Quién ocupa cada puesto y qué está haciendo lo decide `adaptador.ts`;
 * acá no hay una sola palabra de negocio, y hay una prueba que lo comprueba.
 *
 * TODO ESTÁ DIBUJADO, NO IMPORTADO
 * No hay sprites ni atlas: cada volumen son tres caras —tapa iluminada, canto en
 * penumbra, lateral en sombra— derivadas del mismo color base con `tono()`. Es
 * la técnica que hace que una escena sin arte se lea como volumen y no como
 * recortes de papel, y tiene una ventaja que el arte no da: la luz entra SIEMPRE
 * del mismo lado, porque el signo está en una sola función.
 *
 * LO QUE NO ES, Y CONVIENE DECIRLO
 * Esto no es arte definitivo. Es una escena construida con geometría para fijar
 * la composición, la escala, la profundidad y el rendimiento. El día que haya
 * ilustración, lo que se reemplaza es el cuerpo de estas funciones: la rejilla,
 * el orden de pintado, la cámara y la frontera con los datos no se tocan. Ese
 * reparto es el verdadero entregable.
 *
 * EL ORDEN DE PINTADO ES UNA DECISIÓN, NO UN DESCUIDO
 * `sortableChildren` con `zIndex = profundidad(gx, gy)` para el mobiliario, y
 * dos valores fijos muy negativos para el suelo y los muros. Los muros están en
 * `gx = 0` y `gy = 0` y el mobiliario siempre en `gx >= 1, gy >= 1`, así que
 * ninguna pieza puede quedar DETRÁS de un muro por un empate de profundidad —
 * que es el defecto que aparece como un parpadeo entre fotogramas y se busca
 * durante una hora en el sitio equivocado.
 */

import { Container, Graphics, Sprite, Text, Polygon } from 'pixi.js';
import { ALTURA_UNIDAD, BALDOSA, aPantalla, profundidad, rombo, type Mundo } from './isometria';
import { PALETA, tono } from './paleta';
import type { Texturas } from './texturas';
import { construirNucleoAcristalado, construirPieza, type PiezaDeArquitectura } from './arquitectura';
import { aplanar, caja, panelEnX, panelEnY, panelMuroFondo, panelMuroLateral } from './volumen';

/**
 * UNA PLANTA ES UN DATO, NO CÓDIGO.
 *
 * Hasta acá el recinto estaba escrito a mano dentro de esta función: un mundo
 * de 14 × 10, un pasillo en una franja fija y una lista de muebles con sus
 * coordenadas. Servía para UNA sala, y la regla de esta casa es que dar de alta
 * una empresa nueva sea una fila en una tabla y un archivo en una carpeta, con
 * cero cambios en el motor. Una oficina virtual no es una excepción a eso.
 *
 * Así que la escena pasa a recibir la planta. Sabe dibujar TIPOS de mueble
 * —un armario, una mampara, una planta— y no sabe qué departamento está
 * construyendo. El día que una empresa quiera mover un escritorio, lo que
 * cambia es una fila, no este archivo.
 *
 * Lo que NO hace esto todavía: la planta vive en `plantas.js`, en el navegador.
 * Su sitio definitivo es la configuración del tenant, igual que los agentes.
 * Está dicho ahí.
 */
export interface Mueble2D {
  tipo: string;
  gx?: number;
  gy?: number;
  /** Parámetros propios del tipo: largo de una mampara, ancho de una zona… */
  [extra: string]: any;
}

export interface Planta {
  /**
   * Dónde empieza esta sala dentro del edificio, en celdas.
   *
   * Ausente o `{0,0}` para una sala sola. Cuando se montan varias a la vez, es
   * lo único que las separa: cada una sigue dibujándose en SUS coordenadas, y
   * el edificio la desplaza entera. Así una sala no necesita saber que hay
   * otras, que es lo que permitió montar las seis sin tocar nada de acá.
   */
  origen?: { gx: number; gy: number; gz?: number };
  mundo: Mundo;
  /**
   * Si la sala lleva sus dos muros.
   *
   * `false` para una franja de circulación: un suelo por el que se pasa no
   * tiene paredes, y ponérselas convertiría el edificio en un laberinto de
   * tabiques que tapa justamente lo que hay que ver.
   */
  muros?: boolean;
  /**
   * Si se dibuja el canto del forjado por debajo del suelo.
   *
   * Es lo que convierte un suelo en una PLANTA. Sin él, un nivel apilado se ve
   * como un tablero flotando a media altura — que es literalmente lo que la
   * vista plana de la empresa parecía, y el motivo por el que se construyó
   * esto.
   */
  losa?: boolean;
  /** Baranda en los bordes abiertos: un suelo que termina en el aire. */
  baranda?: boolean;
  /** El nombre escrito en el canto del forjado, para leerlo de lejos. */
  rotuloFrontal?: string;
  /** En qué nivel del edificio está. Lo pone quien compone el edificio. */
  nivel?: number;
  /** Qué papel cumple: una sala, la circulación, el núcleo o la envolvente. */
  papel?: 'sala' | 'circulacion' | 'nucleo' | 'arquitectura';
  /**
   * Una pieza del edificio que NO es una sala: basamento, fachada, extremo,
   * cubierta o remate del núcleo.
   *
   * Cuando viene, esta planta no tiene suelo, ni muros, ni puestos: es sólo esa
   * pieza, colocada por su origen. Se modeló así —una planta por pieza— y no
   * como una lista dentro de la sala, porque el orden de pintado entre niveles
   * lo decide el ORIGEN de la planta: la fachada tiene que ir detrás de las
   * salas y el extremo delante, y eso es imposible si comparten contenedor.
   */
  arquitectura?: PiezaDeArquitectura;
  /**
   * Si el cerramiento de esta planta es de vidrio en vez de muro.
   *
   * Lo usa el núcleo vertical, y sólo él. Es lo que lo vuelve reconocible como
   * ascensor a escala de conjunto, donde la escalera de dentro ya no se
   * distingue de un mueble.
   */
  vidrio?: boolean;
  /** El identificador de la sala de la organización, si es una sala. */
  sala?: string;
  /** El color propio del departamento. Tiñe la sala, nunca los estados. */
  acento?: number;
  /** La franja de suelo más clara que cruza el recinto. */
  pasillo: { desde: number; hasta: number } | null;
  /** Lo que se lee en el muro del fondo, y a qué altura del muro va. */
  cartel?: { rotulo: string; gx: number } | null;
  /** El mural de pantallas del muro de fondo, si lo hay. */
  mural?: { paneles: { gx: number; ancho: number }[] } | null;
  mobiliario: Mueble2D[];
  puestos: DefinicionDePuesto[];
}

/** El recinto del primer prototipo. Se conserva como respaldo. */
export const MUNDO: Mundo = { ancho: 14, fondo: 10, alto: 4 };

/**
 * El pasillo de la planta que se está dibujando.
 *
 * Es un módulo-global y es feo, y tiene un motivo: `construirSuelo` se llama
 * una vez por montaje y la alternativa era pasarlo por cuatro firmas. Se fija
 * al entrar en `construirOficina` y no se lee desde ningún otro sitio.
 */
let PASILLO: { desde: number; hasta: number } = { desde: 11, hasta: 14 };

/**
 * EL ACENTO DE LA SALA.
 *
 * Tiñe lo DECORATIVO —la luz de las pantallas, la banda del muro, el cartel,
 * el halo de un puesto tranquilo— para que ocho departamentos no se vean como
 * ocho recoloreados de la misma sala.
 *
 * Lo que NO tiñe son los estados. El rojo de un fallo y el gris de «no sé»
 * viven en `COLOR_DE_ANIMACION` y no se tocan: si el rojo cambiara de sala en
 * sala, quien mira dos pantallas aprendería que el color no quiere decir nada.
 *
 * Mismo patrón que `PASILLO`: se fija al entrar en `construirOficina` y no se
 * lee desde ningún otro sitio.
 */
let ACENTO = PALETA.ember;
let ACENTO_CLARO = PALETA.emberClaro;

/** Declaración de un puesto. Posición y a quién pertenece, nada más. */
export interface DefinicionDePuesto {
  id: string;
  /** El agente que lo ocupa, o `null` si está vacío. */
  agente: string | null;
  /**
   * La persona del equipo que lo ocupa, o `null`.
   *
   * Excluyente con `agente` —el esquema del motor rechaza un puesto con los
   * dos—, y la escena la dibuja igual que a un agente salvo en una cosa: sin
   * halo y sin estado. No hay flujo de eventos que represente a una persona, y
   * animarla sería inventar actividad.
   */
  persona?: string | null;
  /** Lo que se lee en la placa del puesto. */
  nombre: string;
  /** El área, para la placa. Dato de la empresa, no de la escena. */
  area: string;
  gx: number;
  gy: number;
  /** Un puesto principal es más grande y lleva tres monitores. */
  principal?: boolean;
}

export interface Puesto {
  def: DefinicionDePuesto;
  nodo: Container;
  /** Donde se monta el personaje. Vacío si el puesto no tiene agente. */
  ancla: Container;
  /** El halo de estado en el suelo. Se tiñe y se gradúa. */
  halo: Sprite;
  /**
   * Las piezas que emiten luz en el puesto, con la opacidad que les toca
   * cuando el brillo es 1. Se guardan en una lista en vez de aplicarle `alpha`
   * al contenedor: el marco del monitor no emite luz y bajarle la opacidad lo
   * volvería translúcido, con el escritorio visible a través.
   */
  brillos: { pieza: Container; base: number }[];
  /** El rótulo de la actividad bajo la placa. */
  rotulo: Text;
  /** El punto de color del estado en la placa. */
  testigo: Graphics;
  /**
   * El aviso de lo último que pasó, al lado de la placa.
   *
   * Es la segunda dimensión hecha visible: el cuerpo dice si TRABAJA y esto
   * dice QUÉ PASÓ. Antes un fallo reemplazaba la animación y el personaje
   * parecía detenerse; ahora sigue tecleando con el aviso al lado.
   */
  aviso: Container;
  /** El rótulo del puesto. Vive en la capa de arriba, no en el puesto. */
  placa: Container;
  /** El marco que aparece al seleccionar. */
  seleccion: Graphics;
  /** El paquete que sale del puesto cuando algo se despacha. */
  paquete: Container;
}

export interface Oficina {
  raiz: Container;
  mundo: Mundo;
  puestos: Puesto[];
  /**
   * Muebles que la planta pedía y esta escena no conoce.
   *
   * Se cuentan en vez de dibujarse «parecido». Una planta guardada puede venir
   * de una versión posterior de la interfaz; dibujar un sustituto haría que la
   * sala mostrara algo que nadie puso ahí.
   */
  sinTipo: number;
  /** Lo que se mueve por sí solo. `t` acumulado y `dt`, en segundos. */
  animar(t: number, dt: number): void;
  destruir(): void;
}

/* ════════════════════════════════════════════════════════════════════════════
   El recinto
   ════════════════════════════════════════════════════════════════════════════ */

function construirSuelo(mundo: Mundo): Container {
  const capa = new Container();
  const g = new Graphics();
  capa.addChild(g);

  for (let gx = 0; gx < mundo.ancho; gx++) {
    for (let gy = 0; gy < mundo.fondo; gy++) {
      const enPasillo = gx >= PASILLO.desde && gx < PASILLO.hasta;
      const base = enPasillo ? PALETA.pisoPasillo : (gx + gy) % 2 === 0 ? PALETA.pisoA : PALETA.pisoB;
      // Oscurecer al fondo: la perspectiva aérea aplicada al interior de una
      // sala. Es lo que da sensación de profundidad sin mover la cámara.
      const lejania = 1 - (gx + gy) / (mundo.ancho + mundo.fondo);
      g.poly(aplanar(rombo(gx, gy))).fill({ color: tono(base, -0.22 * lejania) });
    }
  }

  //  LA LUZ QUE ENTRA POR LA PUERTA.
  //
  //  Un trapecio que se abre desde el vano hacia dentro de la sala. Cuesta un
  //  polígono y hace dos cosas: dice que el hueco del muro es una puerta y no
  //  un trozo de pared que falta, y rompe la uniformidad del suelo, que es la
  //  queja concreta de «el edificio se ve oscuro y plano».
  //
  //  Va DESPUÉS de las baldosas y ANTES de las juntas, para que el enrejado
  //  siga leyéndose por encima: una mancha de luz que tapa las juntas se ve
  //  como una mancha, no como luz.
  if (mundo.puerta) {
    const [a, b] = mundo.puerta;
    const hasta = Math.min(mundo.fondo, 3.2);
    g.poly(aplanar([
      aPantalla(a, 0, 0.01),
      aPantalla(b, 0, 0.01),
      aPantalla(b + 0.9, hasta, 0.01),
      aPantalla(a - 0.9, hasta, 0.01)
    ])).fill({ color: PALETA.muroBanda, alpha: 0.16 });
  }

  // Las juntas, en una sola pasada y por líneas completas: 24 trazos en vez de
  // 140 rombos con borde. A ojo es idéntico.
  for (let gx = 0; gx <= mundo.ancho; gx++) {
    const a = aPantalla(gx, 0);
    const b = aPantalla(gx, mundo.fondo);
    g.moveTo(a.x, a.y).lineTo(b.x, b.y);
  }
  for (let gy = 0; gy <= mundo.fondo; gy++) {
    const a = aPantalla(0, gy);
    const b = aPantalla(mundo.ancho, gy);
    g.moveTo(a.x, a.y).lineTo(b.x, b.y);
  }
  g.stroke({ width: 1, color: PALETA.junta, alpha: 0.55 });

  // Marcas del pasillo: dos líneas continuas y trazos cortos entre ellas. Es lo
  // que convierte una franja de color en un paso.
  const marcas = new Graphics();
  for (const borde of [PASILLO.desde, PASILLO.hasta]) {
    const a = aPantalla(borde, 0);
    const b = aPantalla(borde, mundo.fondo);
    marcas.moveTo(a.x, a.y).lineTo(b.x, b.y);
  }
  marcas.stroke({ width: 2, color: PALETA.clayClaro, alpha: 0.22 });
  for (let gy = 0.4; gy < mundo.fondo; gy += 1.4) {
    const a = aPantalla((PASILLO.desde + PASILLO.hasta) / 2, gy);
    const b = aPantalla((PASILLO.desde + PASILLO.hasta) / 2, gy + 0.6);
    marcas.moveTo(a.x, a.y).lineTo(b.x, b.y);
  }
  marcas.stroke({ width: 2, color: PALETA.clayClaro, alpha: 0.16 });
  // Hermano, no hijo: un `Graphics` dentro de otro `Graphics` funciona y el
  // motor avisa por consola, con razón — son dos cosas distintas (una figura y
  // un contenedor) y mezclarlas hace que `clear()` del padre no haga lo que
  // parece. La capa cuesta un objeto y quita el aviso.
  capa.addChild(marcas);

  return capa;
}

/**
 * EL CANTO DEL FORJADO.
 *
 * Dos caras y nada mas: la del frente (gy = fondo) y la de la derecha
 * (gx = ancho), que son las dos que mira el espectador en esta proyeccion. Las
 * otras dos no se ven nunca, y dibujarlas seria pagar geometria por nada.
 *
 * POR QUE ESTO IMPORTA MAS DE LO QUE PARECE
 * Un suelo isometrico sin canto no tiene espesor, y sin espesor no se lee como
 * una planta de un edificio: se lee como una alfombra. Apilar tres alfombras no
 * da un edificio, da tres alfombras apiladas -- que es exactamente la critica
 * que trajo esta etapa. Son cuatro poligonos.
 */
function construirLosa(mundo: Mundo): Graphics {
  const g = new Graphics();
  const e = 0.6;

  //  Cara frontal, a lo largo de gy = fondo.
  g.poly(aplanar([
    aPantalla(0, mundo.fondo, 0),
    aPantalla(mundo.ancho, mundo.fondo, 0),
    aPantalla(mundo.ancho, mundo.fondo, -e),
    aPantalla(0, mundo.fondo, -e)
  ])).fill({ color: PALETA.muroRemate });

  //  UNA LINEA CLARA EN EL BORDE SUPERIOR DEL CANTO. Es lo que separa un nivel
  //  del siguiente cuando se miran los tres a la vez: sin ella los cantos y el
  //  fondo son el mismo tono oscuro y las losas se funden. Dos puntos y un
  //  trazo.
  {
    const a = aPantalla(0, mundo.fondo, 0);
    const b = aPantalla(mundo.ancho, mundo.fondo, 0);
    g.moveTo(a.x, a.y).lineTo(b.x, b.y)
     .stroke({ width: 1.5, color: PALETA.muroBanda, alpha: 0.7 });
  }

  //  Cara derecha, a lo largo de gx = ancho. Mas oscura: recibe menos luz, y
  //  pintar las dos iguales es lo que hace que la esquina desaparezca.
  g.poly(aplanar([
    aPantalla(mundo.ancho, 0, 0),
    aPantalla(mundo.ancho, mundo.fondo, 0),
    aPantalla(mundo.ancho, mundo.fondo, -e),
    aPantalla(mundo.ancho, 0, -e)
  ])).fill({ color: tono(PALETA.muroRemate, -0.3) });

  //  Una linea de luz en el borde superior del canto. Es el detalle que separa
  //  la losa del aire que hay debajo.
  for (const [a, b] of [
    [aPantalla(0, mundo.fondo, 0), aPantalla(mundo.ancho, mundo.fondo, 0)],
    [aPantalla(mundo.ancho, 0, 0), aPantalla(mundo.ancho, mundo.fondo, 0)]
  ]) {
    g.moveTo(a.x, a.y).lineTo(b.x, b.y);
  }
  g.stroke({ width: 2, color: ACENTO_CLARO, alpha: 0.35 });

  return g;
}

/**
 * La baranda de los bordes abiertos.
 *
 * Un pasamanos y sus montantes, en las dos caras que se ven. No es adorno: un
 * suelo que termina en el aire sin baranda se lee como un suelo CORTADO, y la
 * diferencia entre «esta planta sigue y no la dibujamos» y «esta planta termina
 * aqui» es justo lo que una seccion arquitectonica tiene que dejar claro.
 */
/**
 * EL CERRAMIENTO DE LOS DOS LADOS QUE MIRAN A LA CÁMARA.
 *
 * Una sala dibuja dos muros altos —el de fondo y el lateral— y deja los otros
 * dos abiertos. Mirada de lejos eso no se lee como un departamento sino como
 * dos tabiques sueltos, que es justo lo que se señaló al ver la planta
 * compacta: «algunas oficinas parecen espacios separados por paredes
 * parciales, no departamentos completos».
 *
 * POR QUÉ NO SE CIERRAN CON UN MURO ENTERO, con el número delante. En esta
 * isometría la `y` de pantalla crece hacia abajo y la altura se resta, así que
 * un muro en el borde de adelante tapa todo lo que tenga detrás y más bajo.
 * Medido, en celdas desde el borde:
 *
 *     altura   tapa escritorios   tapa personas
 *       1,2         0,7               0,0
 *       2,2         2,4               0,7
 *       4,0         5,3               3,7     <- un muro normal
 *
 * Una sala mide nueve o diez de fondo: un muro de 4 esconde media sala y a la
 * gente que trabaja en ella. Un antepecho de 1,2 cierra el recinto y **no tapa
 * a nadie**. Eso es lo que se dibuja: un peto a la altura de un escritorio,
 * con su remate, y el hueco de la puerta abierto donde corresponde.
 *
 * El vano es el MISMO dato que usa la rejilla de navegación. Una puerta que se
 * ve y por la que no se puede pasar, o al revés, es la clase de desacuerdo que
 * aparece cuando la geometría y las rutas se escriben dos veces.
 */
/**
 * Lo que sube el peto de cerramiento.
 *
 * 1,2 y no mas: a esa altura no tapa a NADIE -ver la tabla de arriba- y aun
 * asi dibuja el recinto entero. A 2,2 ya empieza a comerse escritorios.
 */
export const ALTURA_DE_ANTEPECHO = 1.2;

function construirAntepecho(mundo: Mundo): Graphics {
  const g = new Graphics();
  const h = ALTURA_DE_ANTEPECHO;
  const remate = 0.1;

  /** Un tramo del peto, con su remate más claro arriba. */
  const tramo = (
    pintar: (gg: Graphics, desde: number, largo: number, z0: number, z1: number, color: number, alpha?: number) => void,
    desde: number, hasta: number
  ) => {
    const largo = hasta - desde;
    if (largo <= 0.01) return;
    pintar(g, desde, largo, 0, h - remate, PALETA.muroLateral);
    pintar(g, desde, largo, h - remate, h, PALETA.muroRemate);
    //  La sombra de contacto al pie: sin ella el peto flota sobre el suelo.
    pintar(g, desde, largo, 0, 0.22, PALETA.pisoProfundo, 0.6);
  };

  /** El hueco de la puerta: jambas a los lados y umbral en el suelo. */
  const marcarVano = (
    pintar: (gg: Graphics, desde: number, largo: number, z0: number, z1: number, color: number, alpha?: number) => void,
    vano: [number, number],
    aSuelo: (u: number) => { x: number; y: number }
  ) => {
    pintar(g, vano[0] - 0.14, 0.14, 0, h, PALETA.muroRemate);
    pintar(g, vano[1], 0.14, 0, h, PALETA.muroRemate);
    const a = aSuelo(vano[0]);
    const b = aSuelo(vano[1]);
    g.moveTo(a.x, a.y).lineTo(b.x, b.y)
     .stroke({ color: PALETA.muroBanda, width: 2.5, alpha: 0.9 });
  };

  if (mundo.antepecho?.frente) {
    const pintar = (gg: Graphics, desde: number, largo: number, z0: number, z1: number, c: number, a = 1) =>
      panelEnY(gg, mundo.fondo, desde, largo, z0, z1, c, a);
    const v = mundo.puertaFrente;
    if (v) {
      tramo(pintar, 0, Math.max(0, v[0]));
      tramo(pintar, Math.min(mundo.ancho, v[1]), mundo.ancho);
      marcarVano(pintar, v, (u) => aPantalla(u, mundo.fondo, 0.02));
    } else {
      tramo(pintar, 0, mundo.ancho);
    }
  }

  if (mundo.antepecho?.derecha) {
    const pintar = (gg: Graphics, desde: number, largo: number, z0: number, z1: number, c: number, a = 1) =>
      panelEnX(gg, mundo.ancho, desde, largo, z0, z1, c, a);
    const v = mundo.puertaDerecha;
    if (v) {
      tramo(pintar, 0, Math.max(0, v[0]));
      tramo(pintar, Math.min(mundo.fondo, v[1]), mundo.fondo);
      marcarVano(pintar, v, (u) => aPantalla(mundo.ancho, u, 0.02));
    } else {
      tramo(pintar, 0, mundo.fondo);
    }
  }

  return g;
}

function construirBaranda(mundo: Mundo): Graphics {
  const g = new Graphics();
  const h = 0.8;

  //  Los montantes, cada dos celdas y medio.
  for (let gx = 0; gx <= mundo.ancho; gx += 2.5) {
    const a = aPantalla(gx, mundo.fondo, 0);
    const b = aPantalla(gx, mundo.fondo, h);
    g.moveTo(a.x, a.y).lineTo(b.x, b.y);
  }
  for (let gy = 0; gy <= mundo.fondo; gy += 2.5) {
    const a = aPantalla(mundo.ancho, gy, 0);
    const b = aPantalla(mundo.ancho, gy, h);
    g.moveTo(a.x, a.y).lineTo(b.x, b.y);
  }
  g.stroke({ width: 2, color: PALETA.metal, alpha: 0.5 });

  //  El pasamanos.
  const f0 = aPantalla(0, mundo.fondo, h);
  const f1 = aPantalla(mundo.ancho, mundo.fondo, h);
  const d1 = aPantalla(mundo.ancho, 0, h);
  g.moveTo(d1.x, d1.y).lineTo(f1.x, f1.y).lineTo(f0.x, f0.y);
  g.stroke({ width: 3, color: PALETA.metal, alpha: 0.75 });

  //  EL FILO DE LUZ DEL BORDE DE FORJADO.
  //
  //  Una linea azul a ras de suelo, siguiendo el mismo borde abierto. Es el
  //  acento tecnologico de la referencia, y a escala de edificio es lo que mas
  //  trabaja: recorre cada planta de punta a punta, asi que las tres se leen
  //  como tres lineas horizontales paralelas. Un detalle que solo se ve de
  //  cerca no sirve para una vista de conjunto.
  const s0 = aPantalla(0, mundo.fondo, 0.06);
  const s1 = aPantalla(mundo.ancho, mundo.fondo, 0.06);
  const s2 = aPantalla(mundo.ancho, 0, 0.06);
  g.moveTo(s2.x, s2.y).lineTo(s1.x, s1.y).lineTo(s0.x, s0.y);
  g.stroke({ width: 2.4, color: PALETA.azulTecno, alpha: 0.85 });

  return g;
}

/**
 * Un tramo de escalera: peldanos que suben de verdad.
 *
 * Suben en `gz` uno a uno en vez de dibujar una rampa con una textura de
 * rayas. Cuesta diez cajas y es la diferencia entre una escalera y un dibujo de
 * una escalera -- en isometria una rampa lisa no tiene forma de nada.
 */
/** El fondo de la caja del nucleo, en celdas. Lo usa el reparto de peldanos. */
const NUCLEO_FONDO = 4;

function construirEscalera(gx: number, gy: number, alto = 4, peldanos = 9,
                           desde = 0): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, gy) + 0.3;
  const g = new Graphics();
  const n = Math.max(2, Math.round(peldanos));
  //  La huella de cada peldano se reparte, no se fija: un tramo que sube
  //  quince unidades con peldanos de 0,3 saldria por fuera del nucleo.
  const huella = (NUCLEO_FONDO - 1) / n;
  for (let i = 0; i < n; i++) {
    const z = desde + (i * alto) / n;
    caja(g, gx, gy + i * huella, z, 1.7, huella * 1.05, alto / n, PALETA.muroRemate);
  }
  //  La zanca lateral, que es lo que le da el perfil inclinado.
  g.poly(aplanar([
    aPantalla(gx, gy, desde),
    aPantalla(gx, gy + n * huella, desde + alto),
    aPantalla(gx, gy + n * huella, desde + alto - 0.6),
    aPantalla(gx, gy, desde - 0.6)
  ])).fill({ color: tono(PALETA.muroRemate, -0.35) });
  nodo.addChild(g);
  return { nodo };
}

/**
 * El ascensor: una caja con su puerta iluminada.
 *
 * La puerta lleva el acento del nivel, no un color propio. Un ascensor que
 * brilla igual en los tres pisos deja de ser una referencia y pasa a ser un
 * mueble repetido.
 */
function construirAscensor(gx: number, gy: number, alto = 3.6): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, gy) + 0.3;
  const g = new Graphics();
  caja(g, gx, gy, 0, 1.7, 1.7, alto, PALETA.muroLateral);
  //  La puerta, en la cara que mira al espectador (+gy). Alta de 2,4 y no de
  //  la altura del hueco: una puerta de quince unidades es un porton.
  const h = Math.min(2.4, alto - 0.4);
  g.poly(aplanar([
    aPantalla(gx + 0.25, gy + 1.7, h),
    aPantalla(gx + 1.45, gy + 1.7, h),
    aPantalla(gx + 1.45, gy + 1.7, 0.15),
    aPantalla(gx + 0.25, gy + 1.7, 0.15)
  ])).fill({ color: tono(ACENTO, -0.45) });
  //  La junta central: el trazo que lo convierte en una puerta.
  const a = aPantalla(gx + 0.85, gy + 1.7, h);
  const b = aPantalla(gx + 0.85, gy + 1.7, 0.15);
  g.moveTo(a.x, a.y).lineTo(b.x, b.y);
  g.stroke({ width: 2, color: ACENTO_CLARO, alpha: 0.7 });
  nodo.addChild(g);
  return { nodo };
}

/** Una columna estructural. Es lo que hace que una losa parezca sostenida. */
function construirColumna(gx: number, gy: number, alto = 4.6): Mueble {
  const nodo = new Container();
  //  Por DETRAS de todo lo demas de su celda: una columna que tapa un
  //  escritorio es peor que ninguna columna.
  nodo.zIndex = profundidad(gx, gy) - 0.4;
  const g = new Graphics();
  caja(g, gx, gy, -0.6, 0.7, 0.7, alto + 0.6, PALETA.muroRemate);
  //  Una arista de luz: sin ella, a contraluz entre dos losas la columna se
  //  pierde contra el fondo y el nivel vuelve a parecer que flota.
  const a = aPantalla(gx + 0.7, gy + 0.7, -0.6);
  const b = aPantalla(gx + 0.7, gy + 0.7, alto);
  g.moveTo(a.x, a.y).lineTo(b.x, b.y);
  g.stroke({ width: 2, color: tono(PALETA.muroRemate, 0.35), alpha: 0.8 });
  nodo.addChild(g);
  return { nodo };
}

/**
 * El nombre de la sala, escrito en el canto del forjado.
 *
 * POR QUE AQUI Y NO EN EL MURO. El cartel del muro de fondo sigue existiendo y
 * se lee al mirar una sala sola. En el edificio no: con la separacion medida
 * entre niveles, el muro de fondo solo se ve hasta 2,7 de sus 4 unidades, y el
 * cartel vive a 3,63. Un nombre que a veces se ve no es un nombre.
 *
 * En el canto se lee de lejos, que es como se mira un edificio entero. Es el
 * directorio de la planta.
 */
function construirRotuloFrontal(rotulo: string, mundo: Mundo): Container {
  const nodo = new Container();
  const texto = new Text({
    text: rotulo.toUpperCase(),
    style: {
      fontFamily: 'ui-sans-serif, system-ui, sans-serif',
      fontSize: 13,
      fontWeight: '700',
      fill: ACENTO_CLARO,
      letterSpacing: 1.8
    },
    resolution: 2
  });
  texto.anchor.set(0.5, 0.5);
  const centro = aPantalla(mundo.ancho / 2, mundo.fondo, -0.3);
  texto.position.set(centro.x, centro.y);
  //  Acostado sobre el plano del canto, igual que el cartel sobre el muro: sin
  //  la inclinacion se ve pegado por delante, como una etiqueta de la interfaz
  //  y no como algo escrito en el edificio.
  texto.skew.y = -Math.atan2(BALDOSA.alto / 2, BALDOSA.ancho / 2);
  nodo.addChild(texto);
  return nodo;
}

function construirMuros(mundo: Mundo): Graphics {
  const g = new Graphics();
  const h = mundo.alto;

  // Muro de fondo (gy = 0) y muro lateral (gx = 0), cada uno con su propio tono:
  // el lateral recibe menos luz. Pintar los dos iguales es lo que hace que la
  // esquina desaparezca y la sala parezca un telón.
  //  EL MURO DE FONDO PUEDE TENER UN VANO: en el edificio es el que separa la
  //  sala de la franja de circulación, y una oficina a la que se entra
  //  atravesando la pared es un decorado. Se pinta en dos tramos, igual que
  //  una mampara con su vano, y el dintel lo cierra por arriba.
  //
  //  Sin `puerta` se pinta entero, que es lo que hacía antes: una sala mirada
  //  sola no da a ningún pasillo, así que abrirle un hueco al aire sería un
  //  agujero, no una puerta. Lo decide el compositor del edificio.
  const vano = mundo.puerta;
  if (vano) {
    panelMuroFondo(g, 0, Math.max(0, vano[0]), 0, h, PALETA.muroFondo);
    panelMuroFondo(g, Math.min(mundo.ancho, vano[1]), mundo.ancho, 0, h, PALETA.muroFondo);
    //  Dintel: el muro sigue por encima de la puerta.
    panelMuroFondo(g, vano[0], vano[1], 2.2, h, PALETA.muroFondo);
    //  Las jambas, un tono más claro: es lo que le da espesor al muro y hace
    //  que el hueco se lea como una puerta y no como pared que falta.
    panelMuroFondo(g, vano[0] - 0.12, vano[0], 0, 2.2, PALETA.muroRemate);
    panelMuroFondo(g, vano[1], vano[1] + 0.12, 0, 2.2, PALETA.muroRemate);
    //  El umbral en el suelo, que es lo que dice por dónde se entra.
    const a = aPantalla(vano[0], 0, 0.02);
    const b = aPantalla(vano[1], 0, 0.02);
    g.moveTo(a.x, a.y).lineTo(b.x, b.y)
     .stroke({ color: PALETA.muroBanda, width: 2, alpha: 0.8 });
  } else {
    panelMuroFondo(g, 0, mundo.ancho, 0, h, PALETA.muroFondo);
  }
  //  EL MURO LATERAL, con su propio vano. Mismo criterio que el de fondo: sin
  //  `puertaLateral` se pinta entero. Lo necesita la sede de una planta, donde
  //  una manzana entera tiene la circulación de este lado.
  const vanoLateral = mundo.puertaLateral;
  if (vanoLateral) {
    panelMuroLateral(g, 0, Math.max(0, vanoLateral[0]), 0, h, PALETA.muroLateral);
    panelMuroLateral(
      g, Math.min(mundo.fondo, vanoLateral[1]),
      Math.max(0, mundo.fondo - vanoLateral[1]), 0, h, PALETA.muroLateral);
    //  Dintel.
    panelMuroLateral(g, vanoLateral[0], vanoLateral[1] - vanoLateral[0], 2.2, h, PALETA.muroLateral);
    //  Jambas: es lo que le da espesor al muro y hace que el hueco se lea como
    //  una puerta y no como pared que falta.
    panelMuroLateral(g, vanoLateral[0] - 0.12, 0.12, 0, 2.2, PALETA.muroRemate);
    panelMuroLateral(g, vanoLateral[1], 0.12, 0, 2.2, PALETA.muroRemate);
    //  El umbral en el suelo, que es lo que dice por dónde se entra.
    const a = aPantalla(0, vanoLateral[0], 0.02);
    const b = aPantalla(0, vanoLateral[1], 0.02);
    g.moveTo(a.x, a.y).lineTo(b.x, b.y)
     .stroke({ color: PALETA.muroBanda, width: 2, alpha: 0.8 });
  } else {
    panelMuroLateral(g, 0, mundo.fondo, 0, h, PALETA.muroLateral);
  }

  // Sombra de contacto al pie de cada muro: sin esto los muros flotan y el
  // síntoma se describe como «la escena se ve plana».
  panelMuroFondo(g, 0, mundo.ancho, 0, 0.45, PALETA.pisoProfundo, 0.75);
  panelMuroLateral(g, 0, mundo.fondo, 0, 0.45, PALETA.pisoProfundo, 0.75);

  // Banda de luz indirecta a media altura. Es el detalle más rentable de toda
  // la escena: dos rectángulos y la pared deja de ser un plano de color.
  panelMuroFondo(g, 0, mundo.ancho, 1.02, 1.1, PALETA.muroBanda, 0.9);
  panelMuroLateral(g, 0, mundo.fondo, 1.02, 1.1, PALETA.muroBanda, 0.9);

  // Remate superior, con su canto: lo que le da espesor al muro.
  panelMuroFondo(g, 0, mundo.ancho, h - 0.12, h, PALETA.muroRemate);
  panelMuroLateral(g, 0, mundo.fondo, h - 0.12, h, PALETA.muroRemate);

  // Bandeja de cables bajo el remate, en el muro lateral. Son tres líneas y
  // dicen «esto es una sala técnica» más que cualquier otra cosa.
  for (let i = 0; i < 3; i++) {
    const z = h - 0.45 - i * 0.1;
    const a = aPantalla(0, 0.3, z);
    const b = aPantalla(0, mundo.fondo - 0.3, z);
    g.moveTo(a.x, a.y).lineTo(b.x, b.y);
  }
  g.stroke({ width: 2, color: PALETA.metal, alpha: 0.5 });

  return g;
}

/* ════════════════════════════════════════════════════════════════════════════
   El mural de pantallas
   ════════════════════════════════════════════════════════════════════════════ */

interface Mural {
  nodo: Container;
  animar(t: number, dt: number): void;
}

/**
 * Las tres pantallas grandes del muro de fondo.
 *
 * Cada una muestra una cosa distinta porque tres pantallas idénticas se leen
 * como un patrón decorativo. Y las tres se mueven: una pantalla quieta delata
 * que la escena está congelada, y es lo primero que alguien nota.
 *
 * NADA DE ESTO ES UN DATO. Es forma: barras, nodos, un barrido. No lleva cifras
 * ni nombres, y es a propósito — una pantalla de adorno con un número encima se
 * lee como una medición, y en cuanto alguien la cree, la escena está mintiendo.
 */
function construirMural(texturas: Texturas,
                        paneles: { gx: number; ancho: number }[]): Mural {
  const nodo = new Container();
  const anim: ((t: number, dt: number) => void)[] = [];

  const z0 = 1.45;
  const z1 = 3.35;

  paneles.forEach((p, indice) => {
    const marco = new Graphics();
    panelMuroFondo(marco, p.gx - 0.1, p.ancho + 0.2, z0 - 0.1, z1 + 0.1, PALETA.pantallaMarco);
    panelMuroFondo(marco, p.gx, p.ancho, z0, z1, tono(ACENTO, -0.78));
    nodo.addChild(marco);

    // La trama, recortada al panel. Le da estructura a un rectángulo brillante,
    // que es lo que lo hace leerse como monitor y no como un cartel.
    const esquina = aPantalla(p.gx, 0, z1);
    const trama = new Sprite(texturas.trama);
    trama.x = esquina.x;
    trama.y = esquina.y;
    trama.width = p.ancho * BALDOSA.ancho * 0.5;
    trama.height = (z1 - z0) * ALTURA_UNIDAD;
    trama.alpha = 0.5;
    // El muro de fondo se ve en diagonal: la trama tiene que seguir esa
    // inclinación o se nota pegada encima.
    trama.skew.y = Math.atan2(BALDOSA.alto / 2, BALDOSA.ancho / 2);
    nodo.addChild(trama);

    const contenido = new Container();
    nodo.addChild(contenido);

    if (indice === 0) anim.push(muralDeBarras(contenido, p.gx, p.ancho, z0, z1));
    else if (indice === 1) anim.push(muralDeEnlaces(contenido, p.gx, p.ancho, z0, z1));
    else anim.push(muralDeBarrido(contenido, p.gx, p.ancho, z0, z1, texturas));

    // El resplandor que la pantalla echa sobre el muro y el suelo. Es lo que
    // hace que la luz pertenezca a la escena en vez de estar dentro del marco.
    const luz = new Sprite(texturas.halo);
    luz.anchor.set(0.5);
    const centro = aPantalla(p.gx + p.ancho / 2, 0, (z0 + z1) / 2);
    luz.position.set(centro.x, centro.y);
    luz.width = p.ancho * BALDOSA.ancho * 1.5;
    luz.height = (z1 - z0) * ALTURA_UNIDAD * 3.2;
    luz.tint = ACENTO_CLARO;
    luz.blendMode = 'add';
    luz.alpha = 0.16;
    nodo.addChild(luz);
    anim.push((t) => {
      luz.alpha = 0.13 + Math.sin(t * 0.7 + indice) * 0.03;
    });
  });

  return {
    nodo,
    animar(t, dt) {
      for (const f of anim) f(t, dt);
    }
  };
}

/** Panel 1: barras verticales que suben y bajan. */
function muralDeBarras(padre: Container, gx: number, ancho: number, z0: number, z1: number) {
  const barras: { g: Graphics; fase: number; alto: number }[] = [];
  const n = 11;
  for (let i = 0; i < n; i++) {
    const bx = gx + 0.18 + (i * (ancho - 0.36)) / n;
    const bw = (ancho - 0.36) / n - 0.045;
    const g = new Graphics();
    panelMuroFondo(g, bx, bw, z0 + 0.18, z1 - 0.3, ACENTO_CLARO, 0.85);
    // El pivote de la escala está en la base de la barra, no en el origen del
    // panel: escalar desde el origen hunde las barras en el suelo.
    const base = aPantalla(bx, 0, z0 + 0.18);
    g.pivot.set(0, base.y);
    g.y = base.y;
    padre.addChild(g);
    barras.push({ g, fase: i * 0.7, alto: z1 - z0 });
  }
  return (t: number) => {
    for (const b of barras) {
      const v = 0.25 + (Math.sin(t * 1.1 + b.fase) * 0.5 + 0.5) * 0.7;
      b.g.scale.y = v;
      b.g.tint = v > 0.82 ? PALETA.clayClaro : 0xffffff;
    }
  };
}

/** Panel 2: nodos unidos por enlaces, con un pulso que viaja. */
function muralDeEnlaces(padre: Container, gx: number, ancho: number, z0: number, z1: number) {
  const nodos = [
    { x: 0.5, z: 0.5 },
    { x: 0.22, z: 0.75 },
    { x: 0.78, z: 0.74 },
    { x: 0.16, z: 0.3 },
    { x: 0.5, z: 0.2 },
    { x: 0.84, z: 0.32 },
    { x: 0.35, z: 0.52 },
    { x: 0.66, z: 0.5 }
  ];
  const enlaces: [number, number][] = [
    [0, 1],
    [0, 2],
    [0, 4],
    [0, 6],
    [0, 7],
    [1, 3],
    [2, 5],
    [4, 5],
    [3, 4],
    [6, 1],
    [7, 2]
  ];
  const punto = (n: { x: number; z: number }) =>
    aPantalla(gx + 0.2 + n.x * (ancho - 0.4), 0, z0 + 0.25 + n.z * (z1 - z0 - 0.5));

  const lineas = new Graphics();
  for (const [a, b] of enlaces) {
    const pa = punto(nodos[a]);
    const pb = punto(nodos[b]);
    lineas.moveTo(pa.x, pa.y).lineTo(pb.x, pb.y);
  }
  lineas.stroke({ width: 1.4, color: ACENTO_CLARO, alpha: 0.45 });
  padre.addChild(lineas);

  const puntos: Graphics[] = [];
  nodos.forEach((n, i) => {
    const p = punto(n);
    const g = new Graphics();
    g.circle(0, 0, i === 0 ? 4.2 : 2.6).fill({ color: i === 0 ? PALETA.clayClaro : ACENTO_CLARO });
    g.position.set(p.x, p.y);
    padre.addChild(g);
    puntos.push(g);
  });

  // El pulso: un punto que recorre un enlace y salta al siguiente. Es lo que
  // hace que un grafo quieto parezca una red con tráfico.
  const pulso = new Graphics();
  pulso.circle(0, 0, 2.2).fill({ color: 0xffffff });
  padre.addChild(pulso);

  return (t: number) => {
    const total = enlaces.length;
    const recorrido = (t * 0.55) % total;
    const indice = Math.floor(recorrido);
    const k = recorrido - indice;
    const [a, b] = enlaces[indice];
    const pa = punto(nodos[a]);
    const pb = punto(nodos[b]);
    pulso.position.set(pa.x + (pb.x - pa.x) * k, pa.y + (pb.y - pa.y) * k);
    pulso.alpha = 0.55 + Math.sin(k * Math.PI) * 0.45;
    puntos.forEach((g, i) => {
      g.scale.set(1 + Math.sin(t * 2.2 + i * 1.3) * 0.12);
      g.alpha = 0.7 + Math.sin(t * 1.7 + i) * 0.3;
    });
  };
}

/** Panel 3: una traza continua con un barrido que la recorre. */
function muralDeBarrido(
  padre: Container,
  gx: number,
  ancho: number,
  z0: number,
  z1: number,
  texturas: Texturas
) {
  const n = 46;
  const traza = new Graphics();
  padre.addChild(traza);

  const barrido = new Sprite(texturas.haz);
  barrido.anchor.set(0.5, 0);
  barrido.width = 18;
  barrido.height = (z1 - z0 - 0.3) * ALTURA_UNIDAD;
  barrido.tint = PALETA.mossClaro;
  barrido.blendMode = 'add';
  barrido.alpha = 0.5;
  barrido.skew.x = -Math.atan2(BALDOSA.alto / 2, BALDOSA.ancho / 2);
  padre.addChild(barrido);

  // La línea base: una referencia horizontal. Sin ella la traza no tiene
  // respecto a qué subir ni bajar, y se lee como un garabato.
  const base = new Graphics();
  panelMuroFondo(base, gx + 0.2, ancho - 0.4, z0 + 0.95, z0 + 0.97, PALETA.textoTenue, 0.3);
  padre.addChild(base);

  return (t: number) => {
    traza.clear();
    for (let i = 0; i < n; i++) {
      const px = gx + 0.2 + (i * (ancho - 0.4)) / (n - 1);
      const onda =
        Math.sin(i * 0.5 + t * 1.6) * 0.3 + Math.sin(i * 0.17 - t * 0.9) * 0.2 + Math.sin(i * 1.3 + t * 3) * 0.08;
      const pz = z0 + 0.95 + onda;
      const p = aPantalla(px, 0, pz);
      if (i === 0) traza.moveTo(p.x, p.y);
      else traza.lineTo(p.x, p.y);
    }
    traza.stroke({ width: 1.8, color: PALETA.mossClaro, alpha: 0.9 });

    const avance = (t * 0.22) % 1;
    const p = aPantalla(gx + 0.2 + avance * (ancho - 0.4), 0, z1 - 0.15);
    barrido.position.set(p.x, p.y);
  };
}

/* ════════════════════════════════════════════════════════════════════════════
   Mobiliario técnico
   ════════════════════════════════════════════════════════════════════════════ */

interface Mueble {
  nodo: Container;
  animar?(t: number, dt: number): void;
}

/** Un armario de equipos contra el muro lateral, con sus testigos. */
function construirArmario(gy: number, texturas: Texturas): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(0.4, gy);

  const g = new Graphics();
  caja(g, 0.1, gy, 0, 0.75, 1.5, 3.1, PALETA.rackCuerpo);
  // El frente, con sus bandejas. Las ranuras son lo que lo distingue de una
  // caja: sin ellas es un bloque.
  for (let i = 0; i < 9; i++) {
    const z = 0.22 + i * 0.32;
    panelMuroLateral(g, gy + 0.08, 1.34, z, z + 0.24, PALETA.rackFrente);
  }
  nodo.addChild(g);

  const testigos: Graphics[] = [];
  for (let i = 0; i < 9; i++) {
    for (let j = 0; j < 2; j++) {
      const p = aPantalla(0.1, gy + 0.22 + j * 0.22, 0.34 + i * 0.32);
      const led = new Graphics();
      led.circle(0, 0, 1.5).fill({ color: j === 0 ? PALETA.mossClaro : ACENTO_CLARO });
      led.position.set(p.x, p.y);
      nodo.addChild(led);
      testigos.push(led);
    }
  }

  const sombra = new Sprite(texturas.sombra);
  sombra.anchor.set(0.5);
  const pie = aPantalla(0.48, gy + 0.75, 0);
  sombra.position.set(pie.x, pie.y);
  sombra.width = 95;
  sombra.height = 48;
  sombra.alpha = 0.6;
  nodo.addChildAt(sombra, 0);

  return {
    nodo,
    animar(t) {
      // Los testigos no parpadean al unísono: eso se lee como una guirnalda.
      // Cada uno con su fase, y uno de cada siete se queda apagado un rato.
      for (let i = 0; i < testigos.length; i++) {
        const fase = i * 2.39;
        const v = Math.sin(t * (3 + (i % 5)) + fase);
        testigos[i].alpha = i % 7 === 3 ? 0.12 + Math.max(0, v) * 0.2 : 0.4 + Math.max(0, v) * 0.6;
      }
    }
  };
}

/** El panel de empalmes: una rejilla de bocas con hebras que salen de ellas. */
function construirPanelDeFibra(gy: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(0.3, gy);

  const g = new Graphics();
  panelMuroLateral(g, gy, 2.1, 1.35, 2.5, PALETA.pantallaMarco);
  panelMuroLateral(g, gy + 0.08, 1.94, 1.45, 2.4, tono(PALETA.rackFrente, 0.08));
  nodo.addChild(g);

  // Las bocas. 2 filas × 12: una rejilla regular es exactamente lo que es un
  // panel de empalmes, así que acá la regularidad sí corresponde.
  const bocas = new Graphics();
  for (let fila = 0; fila < 2; fila++) {
    for (let i = 0; i < 12; i++) {
      const p = aPantalla(0, gy + 0.2 + i * 0.15, 2.22 - fila * 0.38);
      bocas.circle(p.x, p.y, 1.7).fill({ color: PALETA.pisoProfundo });
      bocas.circle(p.x, p.y, 0.9).fill({ color: (i + fila) % 3 === 0 ? PALETA.clayClaro : PALETA.mossClaro });
    }
  }
  nodo.addChild(bocas);

  // Las hebras: curvas que caen del panel y entran en la bandeja. Dibujadas con
  // cuadráticas, que es lo que hace que un cable parezca colgar en vez de ser
  // una línea recta diagonal.
  const hebras = new Graphics();
  for (let i = 0; i < 7; i++) {
    const a = aPantalla(0, gy + 0.25 + i * 0.26, 1.45);
    const b = aPantalla(0, gy + 0.1 + i * 0.3, 0.55);
    hebras.moveTo(a.x, a.y).quadraticCurveTo(a.x - 10, a.y + 28, b.x, b.y);
  }
  hebras.stroke({ width: 1.3, color: ACENTO_CLARO, alpha: 0.4 });
  nodo.addChild(hebras);

  return { nodo };
}

/** Una luminaria de techo con su haz. Es la luz «de la sala». */
function construirLuminaria(gx: number, gy: number, texturas: Texturas): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, gy) - 0.5;

  const charco = new Sprite(texturas.halo);
  charco.anchor.set(0.5);
  const suelo = aPantalla(gx, gy, 0);
  charco.position.set(suelo.x, suelo.y);
  charco.width = 330;
  charco.height = 165;
  //  CALIDA, Y NO AZULADA. El tono anterior estaba afinado para un suelo
  //  oscuro: sobre el suelo claro de ahora, una luz fria aditiva no se ve. Y
  //  la referencia pide justo lo contrario del gris — oficinas CALIDAS vistas
  //  desde una noche azul. El contraste entre los dos es lo que hace que el
  //  edificio parezca encendido.
  charco.tint = PALETA.luzCalida;
  charco.blendMode = 'add';
  charco.alpha = 0.2;
  nodo.addChild(charco);

  const g = new Graphics();
  caja(g, gx - 0.6, gy - 0.25, 3.85, 1.2, 0.5, 0.12, PALETA.metal);
  nodo.addChild(g);

  return {
    nodo,
    animar(t) {
      // Una luminaria perfectamente estable es correcta y muerta. Un 2% de
      // variación lenta es lo que la vuelve luz.
      charco.alpha = 0.19 + Math.sin(t * 0.4 + gx) * 0.025;
    }
  };
}

/** Una planta. El detalle que más humaniza una sala técnica. */
function construirPlanta(gx: number, gy: number, texturas: Texturas): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, gy);

  const sombra = new Sprite(texturas.sombra);
  sombra.anchor.set(0.5);
  const suelo = aPantalla(gx + 0.3, gy + 0.3, 0);
  sombra.position.set(suelo.x, suelo.y);
  sombra.width = 62;
  sombra.height = 31;
  sombra.alpha = 0.55;
  nodo.addChild(sombra);

  const g = new Graphics();
  caja(g, gx + 0.08, gy + 0.08, 0, 0.45, 0.45, 0.42, PALETA.maceta);
  nodo.addChild(g);

  const hojas = new Container();
  const centro = aPantalla(gx + 0.3, gy + 0.3, 0.42);
  hojas.position.set(centro.x, centro.y);
  for (let i = 0; i < 9; i++) {
    const a = (i / 9) * Math.PI * 2 + 0.3;
    const largo = 20 + (i % 3) * 7;
    const hoja = new Graphics();
    hoja
      .moveTo(0, 0)
      .quadraticCurveTo(Math.cos(a) * largo * 0.5, -largo * 0.75, Math.cos(a) * largo, -largo * 0.5)
      .quadraticCurveTo(Math.cos(a) * largo * 0.45, -largo * 0.42, 0, 0)
      .fill({ color: i % 2 === 0 ? PALETA.planta : PALETA.plantaOscura });
    hojas.addChild(hoja);
  }
  nodo.addChild(hojas);

  return {
    nodo,
    animar(t) {
      // Las hojas se mecen muy poco. Mucho es una palmera en un huracán dentro
      // de una sala cerrada, y se nota como un error.
      hojas.skew.x = Math.sin(t * 0.6 + gx) * 0.02;
    }
  };
}

/** Un banco del pasillo. */
function construirBanco(gx: number, gy: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, gy);
  const g = new Graphics();
  caja(g, gx, gy + 0.1, 0.35, 2.2, 0.5, 0.1, PALETA.escritorioTapa);
  caja(g, gx + 0.1, gy + 0.18, 0, 0.14, 0.34, 0.35, PALETA.escritorioPata);
  caja(g, gx + 1.96, gy + 0.18, 0, 0.14, 0.34, 0.35, PALETA.escritorioPata);
  nodo.addChild(g);
  return { nodo };
}

/** Un dispensador de agua. */
function construirDispensador(gx: number, gy: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, gy);
  const g = new Graphics();
  caja(g, gx, gy, 0, 0.5, 0.5, 1.05, PALETA.escritorioCanto);
  caja(g, gx + 0.08, gy + 0.08, 1.05, 0.34, 0.34, 0.5, 0x6f86c9);
  nodo.addChild(g);
  return { nodo };
}

/**
 * La mampara que separa el pasillo de la sala, con su vano de paso.
 *
 * Nace de mirar la primera captura: la mitad derecha del recinto era suelo
 * vacío. Un pasillo sin nada que lo separe de la sala no se lee como pasillo,
 * se lee como «aquí no llegamos a poner nada». La mampara cuesta cuatro
 * rectángulos y convierte ese vacío en una decisión de planta.
 *
 * El vidrio va con opacidad baja y SIN sombra: una superficie transparente que
 * proyecta sombra es el detalle que hace que una escena parezca mal armada sin
 * que nadie sepa decir por qué.
 */
function construirMampara(gx: number, desde: number, hasta: number, vano: [number, number]): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, desde) + 0.4;
  const g = new Graphics();
  const alto = 2.3;

  const tramos: [number, number][] = [
    [desde, vano[0]],
    [vano[1], hasta]
  ];

  for (const [a, b] of tramos) {
    if (b <= a) continue;
    // El vidrio.
    const p = [
      aPantalla(gx, a, alto),
      aPantalla(gx, b, alto),
      aPantalla(gx, b, 0.12),
      aPantalla(gx, a, 0.12)
    ];
    g.poly(aplanar(p)).fill({ color: 0x8fa8d8, alpha: 0.1 });
    // Montantes cada metro y medio: lo que lo hace carpintería y no una mancha.
    for (let y = a; y <= b + 0.001; y += 1.5) {
      const arriba = aPantalla(gx, Math.min(y, b), alto);
      const abajo = aPantalla(gx, Math.min(y, b), 0);
      g.moveTo(arriba.x, arriba.y).lineTo(abajo.x, abajo.y);
    }
    // Travesaños: zócalo, media altura y remate.
    for (const z of [0.12, 1.15, alto]) {
      const i = aPantalla(gx, a, z);
      const f = aPantalla(gx, b, z);
      g.moveTo(i.x, i.y).lineTo(f.x, f.y);
    }
  }
  g.stroke({ width: 1.6, color: PALETA.metal, alpha: 0.75 });

  // El marco del vano, más grueso: señala por dónde se pasa.
  const jamba = (y: number) => {
    const arriba = aPantalla(gx, y, alto + 0.12);
    const abajo = aPantalla(gx, y, 0);
    g.moveTo(arriba.x, arriba.y).lineTo(abajo.x, abajo.y);
  };
  jamba(vano[0]);
  jamba(vano[1]);
  const dintelA = aPantalla(gx, vano[0], alto + 0.12);
  const dintelB = aPantalla(gx, vano[1], alto + 0.12);
  g.moveTo(dintelA.x, dintelA.y).lineTo(dintelB.x, dintelB.y);
  g.stroke({ width: 2.6, color: tono(PALETA.metal, 0.18), alpha: 0.9 });

  nodo.addChild(g);
  return { nodo };
}

/**
 * El cartel del departamento, en el muro del fondo.
 *
 * El texto llega como PARÁMETRO. Escribirlo acá pondría el nombre de un área
 * concreta dentro del motor gráfico, que es justo lo que la guarda de este
 * paquete impide: la escena tiene que servir igual para el departamento
 * siguiente sin tocar una línea.
 */
function construirCartel(rotulo: string, gx: number, texturas: Texturas): Mueble {
  const nodo = new Container();
  nodo.zIndex = -890;

  const texto = new Text({
    text: rotulo.toUpperCase(),
    style: {
      fontFamily: 'ui-sans-serif, system-ui, sans-serif',
      fontSize: 11,
      fontWeight: '700',
      fill: ACENTO_CLARO,
      letterSpacing: 2.2
    },
    resolution: 2
  });
  texto.anchor.set(0.5, 0.5);
  // En el friso, ENTRE el remate del muro y el borde superior del mural. A la
  // derecha del mural quedaba más espacio, y ahí el cartel se montaba encima
  // de la tercera pantalla: en la captura parecía parte de lo que esa pantalla
  // mostraba.
  const centro = aPantalla(gx, 0, 3.63);
  texto.position.set(centro.x, centro.y);
  // Acostado sobre el plano del muro: sin esta inclinación el cartel se ve
  // pegado por delante, como una etiqueta de la interfaz y no como algo que
  // está en la pared.
  texto.skew.y = Math.atan2(BALDOSA.alto / 2, BALDOSA.ancho / 2);
  nodo.addChild(texto);

  const halo = new Sprite(texturas.halo);
  halo.anchor.set(0.5);
  halo.position.set(centro.x, centro.y);
  halo.width = texto.width * 2.2;
  halo.height = 34;
  halo.tint = ACENTO_CLARO;
  halo.blendMode = 'add';
  halo.alpha = 0.12;
  nodo.addChildAt(halo, 0);

  return { nodo };
}

/**
 * La zona de supervisión: una alfombra técnica que ancla el puesto principal.
 *
 * El suelo del frente era una extensión vacía, y un personaje de pie sobre un
 * vacío no se lee como el protagonista de la sala: se lee como alguien a quien
 * le sobra sitio. La zona le pone límites a su espacio y, de paso, rompe la
 * repetición de las baldosas donde más se nota — adelante, que es donde la
 * cámara pasa más tiempo.
 *
 * Va casi sin color: una alfombra vistosa competiria con los monitores, que son
 * lo unico que tiene derecho a brillar en una sala oscura.
 */
function construirZona(gx: number, gy: number, ancho: number, fondo: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = -1500;
  const g = new Graphics();

  const contorno = [
    aPantalla(gx, gy + fondo),
    aPantalla(gx, gy),
    aPantalla(gx + ancho, gy),
    aPantalla(gx + ancho, gy + fondo)
  ];
  g.poly(aplanar(contorno)).fill({ color: tono(PALETA.pisoA, 0.1), alpha: 0.85 });
  g.poly(aplanar(contorno)).stroke({ width: 1.4, color: ACENTO_CLARO, alpha: 0.14 });

  // Una trama de lineas en una sola direccion: lo que distingue una alfombra
  // de un rectangulo pintado. En las dos direcciones pareceria una rejilla, y
  // una rejilla sobre un suelo que ya tiene juntas se ve como un error.
  for (let y = gy + 0.5; y < gy + fondo; y += 0.5) {
    const a = aPantalla(gx + 0.12, y);
    const b = aPantalla(gx + ancho - 0.12, y);
    g.moveTo(a.x, a.y).lineTo(b.x, b.y);
  }
  g.stroke({ width: 1, color: PALETA.junta, alpha: 0.5 });

  nodo.addChild(g);
  return { nodo };
}

/**
 * El tablero de planificación del muro lateral.
 *
 * Llena la mitad baja de ese muro, que estaba desnuda, y dice «oficina» sin una
 * palabra: columnas y tarjetas. No lleva texto NI cifras a proposito — un
 * tablero decorativo con numeros encima se lee como una medicion, y en cuanto
 * alguien lo crea la escena esta mintiendo. Es la misma regla que el mural.
 */
function construirTableroDePared(gy: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(0.2, gy);
  const g = new Graphics();

  const z0 = 1.3;
  const z1 = 2.75;
  panelMuroLateral(g, gy - 0.12, 2.74, z0 - 0.1, z1 + 0.1, PALETA.pantallaMarco);
  panelMuroLateral(g, gy, 2.5, z0, z1, tono(PALETA.muroLateral, 0.16));

  // Tres columnas de tarjetas. El reparto desigual --4, 2, 3-- es lo que lo
  // hace parecer un tablero en uso en vez de una plantilla vacia.
  const columnas = [4, 2, 3];
  columnas.forEach((cuantas, c) => {
    const base = gy + 0.18 + c * 0.82;
    // El encabezado de la columna.
    panelMuroLateral(g, base, 0.62, z1 - 0.22, z1 - 0.12, ACENTO_CLARO, 0.5);
    for (let i = 0; i < cuantas; i++) {
      const z = z1 - 0.42 - i * 0.26;
      if (z < z0 + 0.1) break;
      panelMuroLateral(g, base, 0.62, z - 0.18, z,
                       i === 0 && c === 2 ? PALETA.clayClaro : PALETA.textoTenue,
                       i === 0 && c === 2 ? 0.55 : 0.3);
    }
  });

  nodo.addChild(g);
  return { nodo };
}

/**
 * El ducto de suelo que va de los armarios a los puestos.
 *
 * Dos lineas y unas tapas. Hace dos cosas: dice que la sala es tecnica, y le da
 * al suelo una DIRECCION -- sin algo que lo cruce, un piso isometrico grande se
 * lee como un tablero de ajedrez y la mirada no sabe hacia donde ir.
 */
function construirDucto(gy: number, desde: number, hasta: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = -1400;
  const g = new Graphics();

  const ancho = 0.34;
  const contorno = [
    aPantalla(desde, gy + ancho),
    aPantalla(desde, gy),
    aPantalla(hasta, gy),
    aPantalla(hasta, gy + ancho)
  ];
  g.poly(aplanar(contorno)).fill({ color: tono(PALETA.metal, -0.45) });
  g.poly(aplanar(contorno)).stroke({ width: 1, color: PALETA.metal, alpha: 0.5 });

  // Las juntas entre tapas, cada metro.
  for (let x = desde + 1; x < hasta; x += 1) {
    const a = aPantalla(x, gy);
    const b = aPantalla(x, gy + ancho);
    g.moveTo(a.x, a.y).lineTo(b.x, b.y);
  }
  g.stroke({ width: 1, color: PALETA.pisoProfundo, alpha: 0.8 });

  nodo.addChild(g);
  return { nodo };
}

/**
 * Un mostrador de atención: la pieza que una sala de recepción tiene y un
 * centro de operaciones no.
 *
 * Es un volumen en L —tablero alto y encimera— porque un mostrador recto se lee
 * como otro escritorio. Lo que lo distingue a esta escala es el peto: la cara
 * que mira al visitante, más alta que la mesa de trabajo de detrás.
 */
function construirMostrador(gx: number, gy: number, largo: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, gy);
  const g = new Graphics();
  //  El cuerpo, alto: es lo que separa a quien atiende de quien espera.
  caja(g, gx, gy, 0, largo, 0.7, 1.05, PALETA.escritorioCanto);
  //  La encimera, sobresaliendo hacia el visitante.
  caja(g, gx - 0.08, gy - 0.12, 1.05, largo + 0.16, 0.95, 0.08, PALETA.escritorioTapa);
  //  Una franja de luz en el frente: el detalle que lo vuelve un mostrador de
  //  oficina y no una barra.
  caja(g, gx + 0.1, gy + 0.72, 0.28, largo - 0.2, 0.04, 0.45, ACENTO_CLARO);
  nodo.addChild(g);
  return { nodo };
}

/**
 * Una mesa de reunión con sus sillas alrededor.
 *
 * La mesa es ovalada —dos elipses— porque una rectangular en isometría es
 * indistinguible de un escritorio grande. Las sillas van sin respaldo: a esta
 * escala el respaldo solo agrega ruido.
 */
function construirMesa(gx: number, gy: number, texturas: Texturas): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, gy);

  const sombra = new Sprite(texturas.sombra);
  sombra.anchor.set(0.5);
  const centro = aPantalla(gx, gy, 0);
  sombra.position.set(centro.x, centro.y + 4);
  sombra.width = 150;
  sombra.height = 75;
  sombra.alpha = 0.55;
  nodo.addChild(sombra);

  const g = new Graphics();
  //  Las sillas primero: las de atrás quedan detrás de la mesa.
  for (let i = 0; i < 6; i++) {
    const a = (i / 6) * Math.PI * 2;
    const p = aPantalla(gx + Math.cos(a) * 1.25, gy + Math.sin(a) * 1.25, 0);
    g.ellipse(p.x, p.y - 11, 8, 4).fill({ color: PALETA.sillaTela });
    g.rect(p.x - 1.5, p.y - 11, 3, 11).fill({ color: PALETA.sillaBase });
  }
  //  El tablero y su canto.
  const tapa = aPantalla(gx, gy, 0.74);
  g.ellipse(tapa.x, tapa.y + 3, 44, 22).fill({ color: PALETA.escritorioCanto });
  g.ellipse(tapa.x, tapa.y, 44, 22).fill({ color: PALETA.escritorioTapa });
  //  La columna central.
  const pie = aPantalla(gx, gy, 0);
  g.moveTo(pie.x - 5, pie.y).lineTo(pie.x - 3, tapa.y)
    .lineTo(pie.x + 3, tapa.y).lineTo(pie.x + 5, pie.y)
    .fill({ color: PALETA.escritorioPata });
  nodo.addChild(g);
  return { nodo };
}

/**
 * Una estantería contra el muro lateral, con carpetas.
 *
 * Las carpetas son tiras verticales de alturas desiguales. La desigualdad es lo
 * que importa: una fila regular se lee como una textura repetida, y una
 * estantería real nunca lo está.
 */
function construirEstanteria(gy: number, largo: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(0.25, gy);
  const g = new Graphics();

  caja(g, 0.1, gy, 0, 0.5, largo, 2.4, PALETA.escritorioPata);
  //  Cuatro baldas.
  for (let i = 0; i < 4; i++) {
    const z = 0.35 + i * 0.52;
    panelMuroLateral(g, gy + 0.06, largo - 0.12, z, z + 0.06, PALETA.escritorioTapa);
    //  Las carpetas, apoyadas sobre cada balda.
    let y = gy + 0.14;
    let k = i * 3;
    while (y < gy + largo - 0.2) {
      const ancho = 0.07 + ((k * 7) % 5) * 0.012;
      const alto = 0.3 + ((k * 13) % 7) * 0.025;
      const color = [PALETA.clayClaro, PALETA.textoTenue, ACENTO_CLARO,
                     PALETA.mossClaro][k % 4];
      panelMuroLateral(g, y, ancho, z + 0.06, z + 0.06 + alto, color, 0.55);
      y += ancho + 0.015;
      k++;
    }
  }
  nodo.addChild(g);
  return { nodo };
}

/* ════════════════════════════════════════════════════════════════════════════
   El puesto de trabajo
   ════════════════════════════════════════════════════════════════════════════ */

function construirPuesto(def: DefinicionDePuesto, texturas: Texturas): Puesto {
  const nodo = new Container();
  nodo.zIndex = profundidad(def.gx, def.gy);
  nodo.sortableChildren = true;

  const ancho = def.principal ? 3.2 : 2.3;
  const monitores = def.principal ? 3 : 2;
  const brillos: { pieza: Container; base: number }[] = [];

  /* El halo del estado, debajo de todo: es luz en el suelo. */
  const halo = new Sprite(texturas.halo);
  halo.anchor.set(0.5);
  const pieHalo = aPantalla(def.gx + ancho / 2, def.gy + 0.4, 0);
  halo.position.set(pieHalo.x, pieHalo.y);
  halo.width = def.principal ? 340 : 250;
  halo.height = def.principal ? 170 : 125;
  halo.blendMode = 'add';
  halo.alpha = 0;
  halo.zIndex = -10;
  nodo.addChild(halo);

  const sombra = new Sprite(texturas.sombra);
  sombra.anchor.set(0.5);
  sombra.position.set(pieHalo.x, pieHalo.y + 6);
  sombra.width = ancho * 52;
  sombra.height = ancho * 26;
  sombra.alpha = 0.5;
  sombra.zIndex = -5;
  nodo.addChild(sombra);

  /* El escritorio. */
  const mueble = new Graphics();
  mueble.zIndex = 0;
  caja(mueble, def.gx, def.gy, 0.72, ancho, 1.0, 0.09, PALETA.escritorioTapa);
  // Las patas: dos bloques en los extremos, no cuatro palos. A esta escala
  // cuatro palos se pierden y cuestan lo mismo.
  caja(mueble, def.gx + 0.08, def.gy + 0.1, 0, 0.16, 0.8, 0.72, PALETA.escritorioPata);
  caja(mueble, def.gx + ancho - 0.24, def.gy + 0.1, 0, 0.16, 0.8, 0.72, PALETA.escritorioPata);
  // El faldón frontal: lo que cierra el hueco bajo la tapa y hace que el
  // escritorio no parezca una tabla flotando sobre dos tacos.
  caja(mueble, def.gx + 0.24, def.gy + 0.86, 0.18, ancho - 0.48, 0.08, 0.54, PALETA.escritorioCanto);
  nodo.addChild(mueble);

  /* El reflejo de las pantallas sobre la tapa. Es el detalle que delata que la
     luz de la escena viene de los monitores y no de ninguna parte. */
  const reflejo = new Sprite(texturas.haz);
  reflejo.anchor.set(0.5, 0);
  const tapa = aPantalla(def.gx + ancho / 2, def.gy + 0.45, 0.82);
  reflejo.position.set(tapa.x, tapa.y - 4);
  reflejo.width = ancho * 44;
  reflejo.height = 26;
  reflejo.tint = ACENTO_CLARO;
  reflejo.blendMode = 'add';
  reflejo.alpha = 0.2;
  reflejo.zIndex = 1;
  nodo.addChild(reflejo);
  brillos.push({ pieza: reflejo, base: 0.26 });

  /* Los monitores. Perfil bajo a propósito: el personaje se sienta DETRÁS, y
     una pantalla alta le taparía la cabeza. Esa restricción decidió la
     composición entera de la sala. */
  const pantallas = new Container();
  pantallas.zIndex = 2;
  for (let i = 0; i < monitores; i++) {
    const mx = def.gx + 0.35 + i * ((ancho - 0.7) / monitores);
    const mw = (ancho - 0.7) / monitores - 0.12;

    const marco = new Graphics();
    caja(marco, mx, def.gy + 0.2, 0.81, mw, 0.1, 0.78, PALETA.pantallaMarco);
    caja(marco, mx + mw / 2 - 0.07, def.gy + 0.22, 0.81, 0.14, 0.06, 0.12, PALETA.metal);
    pantallas.addChild(marco);

    // La cara que se ve es la de atrás (el personaje mira la otra). El vidrio
    // se insinúa por el borde superior, que es lo que se ve desde acá.
    const vidrio = new Graphics();
    const z0 = 0.95;
    const z1 = 1.59;
    const p = [
      aPantalla(mx + 0.01, def.gy + 0.2, z1),
      aPantalla(mx + mw - 0.01, def.gy + 0.2, z1),
      aPantalla(mx + mw - 0.01, def.gy + 0.2, z0),
      aPantalla(mx + 0.01, def.gy + 0.2, z0)
    ];
    vidrio.poly(aplanar(p)).fill({ color: ACENTO_CLARO });
    vidrio.blendMode = 'add';
    vidrio.alpha = 0.3;
    pantallas.addChild(vidrio);
    brillos.push({ pieza: vidrio, base: 0.52 });

    // El canto encendido del borde superior. Un monitor visto de espaldas se
    // reconoce por esa línea de luz; sin ella es un bloque oscuro sobre la
    // mesa, que es como se veía en la primera captura.
    const canto = new Graphics();
    const a = aPantalla(mx + 0.01, def.gy + 0.2, z1);
    const b = aPantalla(mx + mw - 0.01, def.gy + 0.2, z1);
    canto.moveTo(a.x, a.y).lineTo(b.x, b.y).stroke({ width: 1.6, color: 0xffffff, alpha: 0.9 });
    canto.blendMode = 'add';
    pantallas.addChild(canto);
    brillos.push({ pieza: canto, base: 0.85 });

    // El derrame por el borde superior: la luz que sale del vidrio hacia el
    // espectador. Un monitor visto de espaldas sin derrame se ve apagado.
    const derrame = new Sprite(texturas.halo);
    derrame.anchor.set(0.5);
    const borde = aPantalla(mx + mw / 2, def.gy + 0.2, z1);
    derrame.position.set(borde.x, borde.y);
    derrame.width = mw * 95;
    derrame.height = 56;
    derrame.tint = ACENTO_CLARO;
    derrame.blendMode = 'add';
    derrame.alpha = 0.35;
    pantallas.addChild(derrame);
    brillos.push({ pieza: derrame, base: 0.42 });
  }
  nodo.addChild(pantallas);

  /* El teclado y la taza. Dos piezas minúsculas que cambian mucho: un
     escritorio vacío se lee como mobiliario de catálogo. */
  const sobremesa = new Graphics();
  sobremesa.zIndex = 3;
  caja(sobremesa, def.gx + ancho / 2 - 0.55, def.gy + 0.56, 0.81, 1.1, 0.26, 0.03, tono(PALETA.escritorioCanto, 0.1));
  caja(sobremesa, def.gx + ancho / 2 + 0.62, def.gy + 0.6, 0.81, 0.18, 0.18, 0.16, PALETA.textoTenue);
  nodo.addChild(sobremesa);

  /* El paquete que sale del puesto al despachar algo. Oculto por defecto. */
  const paquete = new Container();
  paquete.zIndex = 20;
  const pg = new Graphics();
  caja(pg, 0, 0, 0, 0.34, 0.34, 0.22, PALETA.clayClaro);
  paquete.addChild(pg);
  const brilloPaquete = new Sprite(texturas.halo);
  brilloPaquete.anchor.set(0.5);
  brilloPaquete.width = 70;
  brilloPaquete.height = 50;
  brilloPaquete.tint = PALETA.clayClaro;
  brilloPaquete.blendMode = 'add';
  brilloPaquete.alpha = 0.5;
  paquete.addChildAt(brilloPaquete, 0);
  paquete.visible = false;
  nodo.addChild(paquete);

  /* El ancla del personaje: una celda detrás del escritorio. */
  const ancla = new Container();
  const puntoAncla = aPantalla(def.gx + ancho / 2, def.gy - 0.15, 0);
  ancla.position.set(puntoAncla.x, puntoAncla.y);
  // DETRÁS del escritorio, no delante. El personaje está más lejos de la
  // cámara, así que los monitores le tapan el tronco y se le ven la cabeza y
  // los hombros por encima. Esa oclusión no es un defecto: es la que decidió
  // toda la composición de la sala, y dibujarlo delante lo dejaría flotando
  // sobre su propia mesa.
  ancla.zIndex = -2;
  nodo.addChild(ancla);

  /* La placa con el nombre. Va SOBRE una placa opaca y no sobre el suelo: el
     contraste de un texto claro sobre un piso oscuro cambia según la baldosa, y
     eso es justo lo que la paleta del tablero ya tuvo que corregir una vez. */
  const placa = new Container();
  placa.zIndex = 30;
  //  LA PLACA LEJANA VA MÁS ALTA QUE LA CERCANA.
  //
  //  En isometría dos puestos caen en la misma columna de pantalla cuando
  //  `gx - gy` coincide, por lejos que estén en la sala. Cuando eso pasa, el
  //  puesto de delante se dibuja después y su placa TAPA la de atrás: el
  //  nombre del agente del fondo queda cortado a media palabra.
  //
  //  Resolverlo moviendo muebles hasta que encajen no es resolverlo: la
  //  siguiente planta que alguien escriba vuelve a chocar, y el síntoma —un
  //  nombre cortado— no señala a la geometría. Separarlas en ALTURA funciona
  //  para cualquier reparto, y además es lo natural: lo que está más lejos se
  //  rotula más arriba.
  const alturaPlaca = def.principal ? 2.9 : 3.65;
  const puntoPlaca = aPantalla(def.gx + ancho / 2, def.gy - 0.4, alturaPlaca);
  placa.position.set(puntoPlaca.x, puntoPlaca.y);

  // UNA PLACA VACÍA NO PUEDE GRITAR IGUAL QUE UNA OCUPADA.
  // En la primera versión las cuatro pesaban lo mismo y las tres estaciones
  // libres se comían la atención del único puesto que tiene a alguien. El dato
  // es el mismo; lo que cambia es cuánto reclama.
  //  OCUPADO ES OCUPADO, LO OCUPE QUIEN LO OCUPE. Un escritorio con una
  //  persona del equipo pesa lo mismo que uno con un agente: los dos tienen a
  //  alguien, y rotular mas tenue al humano diria que cuenta menos.
  const ocupado = !!(def.agente || def.persona);

  const titulo = new Text({
    text: def.nombre,
    style: {
      fontFamily: 'ui-sans-serif, system-ui, sans-serif',
      fontSize: ocupado ? 12 : 10,
      fontWeight: ocupado ? '600' : '400',
      fill: ocupado ? PALETA.textoClaro : PALETA.textoTenue,
      letterSpacing: 0.2
    },
    resolution: 2
  });
  titulo.anchor.set(0.5, 1);
  const subtitulo = new Text({
    text: def.area,
    style: {
      fontFamily: 'ui-sans-serif, system-ui, sans-serif',
      fontSize: ocupado ? 9.5 : 8.5,
      fill: ocupado ? PALETA.textoTenue : 0x6b6a85,
      letterSpacing: 0.6
    },
    resolution: 2
  });
  subtitulo.anchor.set(0.5, 0);
  subtitulo.y = 2;

  const rotulo = new Text({
    text: '',
    style: {
      fontFamily: 'ui-monospace, SFMono-Regular, monospace',
      fontSize: 9.5,
      fill: PALETA.textoClaro,
      letterSpacing: 0.3
    },
    resolution: 2
  });
  rotulo.anchor.set(0.5, 0);
  rotulo.y = 16;
  rotulo.visible = false;

  //  El margen es 36 y no 26 porque el caso peor es un título corto con un
  //  rótulo de área largo —«Gestión» bajo «Administración»— y ahí el subtítulo
  //  se salía de su propia placa. Se vio en una captura, no en una prueba: el
  //  ancho se mide al crear el texto, y lo que falla es el margen, no la
  //  medida. Diez píxeles cuestan nada y cubren el caso.
  const anchoPlaca = Math.max(titulo.width, subtitulo.width) + 36;
  const fondoPlaca = new Graphics();
  fondoPlaca
    .roundRect(-anchoPlaca / 2, -titulo.height - 5, anchoPlaca, titulo.height + subtitulo.height + 11, 4)
    .fill({ color: PALETA.placa, alpha: ocupado ? 0.88 : 0.5 })
    .stroke({ width: 1, color: 0xffffff, alpha: ocupado ? 0.1 : 0.04 });

  const testigo = new Graphics();
  testigo.circle(0, 0, 3).fill({ color: ACENTO });
  testigo.position.set(-anchoPlaca / 2 + 9, -titulo.height / 2 - 1);
  // El punto de estado solo donde hay un estado que contar.
  testigo.visible = ocupado;
  placa.alpha = ocupado ? 1 : 0.72;

  /* El aviso: un punto con halo, a la derecha de la placa. Va DENTRO de la
     placa para heredar la capa de rótulos — un acontecimiento tampoco puede
     quedar tapado por un mueble cercano. */
  const aviso = new Container();
  const avisoHalo = new Sprite(texturas.halo);
  avisoHalo.anchor.set(0.5);
  avisoHalo.width = 34;
  avisoHalo.height = 34;
  avisoHalo.blendMode = 'add';
  avisoHalo.alpha = 0.55;
  const avisoPunto = new Graphics();
  avisoPunto.circle(0, 0, 4.4).fill({ color: 0xffffff });
  avisoPunto.circle(0, 0, 6.6).stroke({ width: 1.4, color: 0xffffff, alpha: 0.5 });
  aviso.addChild(avisoHalo, avisoPunto);
  aviso.x = anchoPlaca / 2 + 11;
  aviso.y = -titulo.height / 2 - 1;
  aviso.visible = false;

  placa.addChild(fondoPlaca, testigo, titulo, subtitulo, rotulo, aviso);
  //  LA PLACA NO CUELGA DEL PUESTO: va a una capa propia, encima de todo.
  //
  //  Colgaba de él, y una luminaria de techo le pasaba por delante: la
  //  luminaria está más cerca de la cámara que un escritorio del fondo, así
  //  que se dibuja después, y su carcasa tapaba media placa. En la captura se
  //  leía «ministración» y parecía que la placa era demasiado estrecha — no lo
  //  era, tenía 18 px de margen a cada lado.
  //
  //  Un rótulo no compite por profundidad con el mobiliario: es información
  //  sobre la sala, no un objeto dentro de ella. Quien monta el recinto lo
  //  recoge y lo pone en la capa de arriba.

  /* El marco de selección. Un rombo en el suelo, no un recuadro: un recuadro
     recto sobre una escena isométrica se lee como parte de la interfaz, no de
     la sala. */
  const seleccion = new Graphics();
  seleccion.zIndex = -8;
  const contorno = [
    aPantalla(def.gx - 0.2, def.gy + 1.3),
    aPantalla(def.gx - 0.2, def.gy - 1.2),
    aPantalla(def.gx + ancho + 0.2, def.gy - 1.2),
    aPantalla(def.gx + ancho + 0.2, def.gy + 1.3)
  ];
  seleccion
    .poly(aplanar(contorno))
    .stroke({ width: 2, color: PALETA.textoClaro, alpha: 0.85 });
  seleccion.visible = false;
  nodo.addChild(seleccion);

  /* La zona sensible. Cubre el escritorio y el espacio del personaje: pulsar
     «el puesto» tiene que funcionar también pulsando al lado de la silla, que
     es donde la gente pulsa. */
  nodo.eventMode = 'static';
  nodo.cursor = 'pointer';
  // La silueta de un prisma isométrico es un HEXÁGONO convexo: la cara superior
  // más las dos laterales que miran a la cámara. El primer intento encadenó seis
  // puntos mezclando alturas sin ese orden y salió un polígono que se cruza a sí
  // mismo; el recuento de cruces de un polígono así deja AGUJEROS, y pulsar en
  // medio del puesto no seleccionaba nada. Se vio en el navegador, no acá: es
  // justo el hueco que la escena deja sin cubrir.
  const x0 = def.gx - 0.2;
  const x1 = def.gx + ancho + 0.2;
  const y0 = def.gy - 1.3;
  const y1 = def.gy + 1.3;
  const alto = 2.6;
  nodo.hitArea = new Polygon(
    aplanar([
      aPantalla(x0, y0, alto),
      aPantalla(x1, y0, alto),
      aPantalla(x1, y0, 0),
      aPantalla(x1, y1, 0),
      aPantalla(x0, y1, 0),
      aPantalla(x0, y1, alto)
    ])
  );

  return { def, nodo, placa, ancla, halo, brillos, rotulo, testigo, aviso,
           seleccion, paquete };
}

/* ════════════════════════════════════════════════════════════════════════════
   La biblioteca de las piezas de red
   ────────────────────────────────────────────────────────────────────────────
   Hasta acá el catálogo era de oficina genérica: escritorios, estanterías,
   macetas. Con eso, once departamentos se distinguían por el color del rótulo
   y nada más — medido: la maceta aparecía en las 19 plantillas y era la pieza
   más numerosa de la escena, con 39 unidades.

   Estas piezas existen para que un área se reconozca SIN leer el letrero. No
   son adornos: cada una es lo que de verdad hay en ese sitio. Y son módulos
   del mismo registro `TIPOS` que el resto, así que una sala las pide con una
   fila de datos.

   OJO AL ESCRIBIR ACÁ: `guardas.test.js` prohíbe el vocabulario del negocio
   en esta carpeta, comentarios incluidos, y me frenó con dos palabras en el
   primer intento. La escena dibuja TIPOS y no sabe de qué empresa son.
   ════════════════════════════════════════════════════════════════════════════ */

/**
 * EL VIDEOWALL del NOC: la pieza protagonista de la sala de supervisión.
 *
 * Tres por dos paneles con marco común, topología de red en el central y
 * gráficas en los demás. Es lo primero que se ve de un NOC y lo que ninguna
 * otra área tiene.
 *
 * Va en el muro de FONDO y no en el lateral: un videowall se mira de frente
 * desde los puestos, y los puestos miran hacia el fondo.
 *
 * @param gx dónde empieza, en celdas del muro de fondo
 * @param ancho cuánto ocupa
 */
function construirVideowall(gx: number, ancho: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, 0.2);
  const g = new Graphics();

  const z0 = 1.15;
  const z1 = 3.3;
  //  El bastidor, un poco más grande que los paneles: es lo que los une en una
  //  sola pieza en vez de seis pantallas sueltas colgadas.
  panelMuroFondo(g, gx - 0.12, ancho + 0.24, z0 - 0.12, z1 + 0.12, PALETA.pantallaMarco);

  const cols = 3;
  const filas = 2;
  const anchoPanel = (ancho - 0.1 * (cols - 1)) / cols;
  const altoPanel = (z1 - z0 - 0.1 * (filas - 1)) / filas;
  for (let c = 0; c < cols; c++) {
    for (let f = 0; f < filas; f++) {
      const x = gx + c * (anchoPanel + 0.1);
      const zb = z0 + f * (altoPanel + 0.1);
      panelMuroFondo(g, x, anchoPanel, zb, zb + altoPanel, PALETA.noche);
      panelMuroFondo(g, x, anchoPanel, zb, zb + altoPanel, PALETA.azulTecno, 0.22);
    }
  }
  nodo.addChild(g);

  //  LA TOPOLOGÍA, en el panel central de arriba. Nodos unidos por enlaces: es
  //  el dibujo que dice «esto vigila una red» y no «esto es una pantalla».
  const red = new Graphics();
  const cx = gx + anchoPanel + 0.05;
  const zTop = z0 + altoPanel + 0.1;
  const nodos: { x: number; y: number }[] = [];
  for (let i = 0; i < 7; i++) {
    //  Repartidos con `sin`, no al azar: la escena tiene que verse igual en dos
    //  cargas seguidas para poder comparar capturas.
    const u = 0.18 + ((Math.sin(i * 2.3) + 1) / 2) * (anchoPanel - 0.36);
    const v = 0.22 + ((Math.sin(i * 5.1) + 1) / 2) * (altoPanel - 0.44);
    nodos.push(aPantalla(cx + u, 0, zTop + v));
  }
  for (let i = 1; i < nodos.length; i++) {
    red.moveTo(nodos[0].x, nodos[0].y).lineTo(nodos[i].x, nodos[i].y);
  }
  red.stroke({ width: 1, color: PALETA.azulTecnoTenue, alpha: 0.7 });
  for (let i = 0; i < nodos.length; i++) {
    red.circle(nodos[i].x, nodos[i].y, i === 0 ? 3 : 1.9)
       .fill({ color: i === 0 ? ACENTO_CLARO : PALETA.mossClaro, alpha: 0.95 });
  }
  nodo.addChild(red);

  //  Barras y trazas en los demás paneles. Dos lenguajes distintos para que no
  //  parezcan la misma pantalla repetida seis veces.
  const datos = new Graphics();
  for (const [c, f] of [[0, 1], [2, 1], [0, 0], [1, 0], [2, 0]] as const) {
    const x0 = gx + c * (anchoPanel + 0.1);
    const zb = z0 + f * (altoPanel + 0.1);
    if ((c + f) % 2 === 0) {
      for (let i = 0; i < 9; i++) {
        const h = (0.2 + ((Math.sin(i * 3.7 + c) + 1) / 2) * 0.55) * altoPanel;
        panelMuroFondo(datos, x0 + 0.14 + i * (anchoPanel - 0.28) / 9,
                       (anchoPanel - 0.28) / 11, zb + 0.16, zb + 0.16 + h,
                       i % 4 === 0 ? PALETA.clayClaro : PALETA.mossClaro, 0.75);
      }
    } else {
      const pts = [];
      for (let i = 0; i <= 12; i++) {
        const u = 0.14 + (i / 12) * (anchoPanel - 0.28);
        const v = 0.2 + ((Math.sin(i * 1.4 + f * 2) + 1) / 2) * (altoPanel - 0.4);
        pts.push(aPantalla(x0 + u, 0, zb + v));
      }
      datos.moveTo(pts[0].x, pts[0].y);
      for (const p of pts.slice(1)) datos.lineTo(p.x, p.y);
      datos.stroke({ width: 1.4, color: ACENTO_CLARO, alpha: 0.8 });
    }
  }
  nodo.addChild(datos);

  return { nodo };
}

/**
 * UN RACK de red: el armario de equipos con sus testigos.
 *
 * Es un volumen en el suelo y no un panel de pared, porque un rack se rodea:
 * en el NOC van en fila contra un costado y se ve que son cuerpos.
 *
 * @param gx @param gy la esquina
 * @param unidades cuántos equipos lleva montados
 */
function construirRack(gx: number, gy: number, unidades: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, gy);
  const g = new Graphics();

  const alto = 2.6;
  caja(g, gx, gy, 0, 0.8, 1.1, alto, PALETA.rackCuerpo);
  //  El frente, un tono más claro: sin esto el rack es una caja negra y no se
  //  distingue de un armario.
  caja(g, gx, gy + 0.02, 0.06, 0.03, 1.06, alto - 0.12, PALETA.rackFrente);
  nodo.addChild(g);

  //  Los equipos montados, cada uno con su franja de testigos. La altura
  //  desigual es lo que lo hace un rack en uso y no un mueble vacío.
  const equipos = new Graphics();
  const cuantos = Math.max(2, Math.min(9, Math.trunc(unidades) || 5));
  for (let i = 0; i < cuantos; i++) {
    const z = 0.22 + i * ((alto - 0.5) / cuantos);
    const h = ((alto - 0.5) / cuantos) * 0.72;
    caja(equipos, gx - 0.01, gy + 0.08, z, 0.04, 0.94, h, tono(PALETA.rackFrente, 0.12));
    //  Los LED. Verde casi siempre y ámbar de vez en cuando: un rack con todas
    //  las luces de alarma diría que la red está caída, y eso es una afirmación
    //  sobre la operación que ningún adorno puede hacer.
    for (let k = 0; k < 6; k++) {
      const p = aPantalla(gx - 0.02, gy + 0.18 + k * 0.14, z + h * 0.5);
      equipos.circle(p.x, p.y, 1.1)
             .fill({ color: (i * 7 + k) % 11 === 0 ? PALETA.clayClaro : PALETA.mossClaro,
                     alpha: 0.9 });
    }
  }
  nodo.addChild(equipos);
  return { nodo };
}

/**
 * UNA BOBINA de cable drop, de pie sobre su eje.
 *
 * La pieza más inequívoca de todo el catálogo: una bobina de dos mil metros de
 * cable de acometida solo la tiene quien tiende fibra.
 */
function construirBobina(gx: number, gy: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, gy);
  const g = new Graphics();

  //  Las dos tapas y el cable enrollado entre ellas. Se dibuja como tres cajas
  //  y no como cilindros: en isometría a esta escala un cilindro y un prisma
  //  chato se ven igual, y el prisma cuesta un cuarto.
  caja(g, gx, gy, 0, 0.12, 1.3, 1.3, PALETA.madera);
  caja(g, gx + 0.12, gy + 0.12, 0.16, 0.5, 1.06, 1.0, tono(PALETA.noche, 0.22));
  //  Las vueltas del cable: líneas horizontales sobre el carrete.
  const vueltas = new Graphics();
  for (let i = 0; i < 7; i++) {
    const z = 0.26 + i * 0.12;
    const a = aPantalla(gx + 0.14, gy + 0.14, z);
    const b = aPantalla(gx + 0.6, gy + 0.14, z);
    vueltas.moveTo(a.x, a.y).lineTo(b.x, b.y);
  }
  vueltas.stroke({ width: 1, color: PALETA.textoTenue, alpha: 0.45 });
  caja(g, gx + 0.62, gy, 0, 0.12, 1.3, 1.3, PALETA.maderaClara);
  nodo.addChild(g);
  nodo.addChild(vueltas);
  return { nodo };
}

/**
 * CAJAS DE MATERIAL apiladas: el stock que sale a la calle.
 *
 * Van en Operaciones de Campo, donde se alista lo que se lleva la cuadrilla.
 * El apilado desigual es a propósito: tres cajas perfectamente alineadas se
 * leen como un mueble, y esto es material en movimiento.
 */
function construirCajasDeMaterial(gx: number, gy: number, cuantas: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, gy);
  const g = new Graphics();

  const n = Math.max(1, Math.min(5, Math.trunc(cuantas) || 3));
  let z = 0;
  for (let i = 0; i < n; i++) {
    const lado = 0.78 - i * 0.05;
    //  Cada caja corrida un poco respecto de la de abajo.
    const dx = ((i * 7) % 3 - 1) * 0.07;
    const dy = ((i * 5) % 3 - 1) * 0.07;
    const color = i % 2 === 0 ? PALETA.clay : PALETA.rust;
    caja(g, gx + dx, gy + dy, z, lado, lado, 0.52, color);
    //  La cinta de la tapa, que es lo que la hace una caja y no un cubo.
    caja(g, gx + dx + lado * 0.42, gy + dy, z + 0.52, lado * 0.16, lado,
         0.012, tono(color, 0.3));
    z += 0.52;
  }
  nodo.addChild(g);
  return { nodo };
}

/**
 * EL BANCO DE PREPARACIÓN: la mesa de trabajo donde se alista y se prueba.
 *
 * No es `mesa` —esa es redonda, de reunión— ni `mostrador` —ese atiende a
 * alguien—. Esto es un tablón con instrumental encima y cajones debajo.
 */
function construirBancoDePreparacion(gx: number, gy: number, largo: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, gy);
  const g = new Graphics();

  const L = Math.max(1.4, largo || 2.6);
  caja(g, gx, gy, 0.72, 0.9, L, 0.08, PALETA.maderaClara);
  caja(g, gx + 0.04, gy + 0.04, 0, 0.82, 0.5, 0.72, PALETA.escritorioPata);
  caja(g, gx + 0.04, gy + L - 0.54, 0, 0.82, 0.5, 0.72, PALETA.escritorioPata);
  //  Los cajones del módulo izquierdo.
  for (let i = 0; i < 3; i++) {
    caja(g, gx + 0.02, gy + 0.08, 0.1 + i * 0.2, 0.02, 0.42, 0.16,
         tono(PALETA.escritorioPata, 0.18));
  }
  nodo.addChild(g);

  //  El instrumental sobre el tablón: un medidor, un par de carretes chicos y
  //  una bandeja de conectores. Son tres volúmenes y dicen «acá se trabaja con
  //  las manos».
  const util = new Graphics();
  caja(util, gx + 0.18, gy + 0.3, 0.8, 0.34, 0.5, 0.14, PALETA.rackFrente);
  const p = aPantalla(gx + 0.35, gy + 0.55, 0.95);
  util.circle(p.x, p.y, 2.4).fill({ color: PALETA.mossClaro, alpha: 0.9 });
  caja(util, gx + 0.2, gy + L - 0.9, 0.8, 0.5, 0.6, 0.1, PALETA.metal);
  for (let i = 0; i < 4; i++) {
    caja(util, gx + 0.26 + i * 0.1, gy + L - 0.84, 0.9, 0.06, 0.48, 0.05,
         i % 2 === 0 ? PALETA.emberClaro : PALETA.azulTecnoTenue);
  }
  nodo.addChild(util);
  return { nodo };
}

/**
 * UNA PIZARRA de ideas, con su bandeja de marcadores y trazos a mano.
 *
 * Se distingue de `tablero` a propósito: el tablero es una pantalla de datos
 * con tarjetas ordenadas, la pizarra es blanca y lo que tiene está escrito.
 * Comercial y Reuniones piensan en una pizarra; el NOC mira un tablero.
 */
function construirPizarra(gy: number, largo: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(0.2, gy);
  const g = new Graphics();

  const L = Math.max(1.6, largo || 2.4);
  const z0 = 1.35;
  const z1 = 2.7;
  panelMuroLateral(g, gy - 0.1, L + 0.2, z0 - 0.08, z1 + 0.08, PALETA.metal);
  panelMuroLateral(g, gy, L, z0, z1, PALETA.textoClaro, 0.88);
  //  La bandeja de marcadores.
  panelMuroLateral(g, gy, L, z0 - 0.1, z0 - 0.02, PALETA.muroRemate);
  for (let i = 0; i < 3; i++) {
    panelMuroLateral(g, gy + 0.2 + i * 0.22, 0.14, z0 - 0.08, z0 - 0.03,
                     [PALETA.ember, PALETA.moss, PALETA.azulTecno][i], 0.9);
  }
  nodo.addChild(g);

  //  Lo escrito: dos recuadros unidos por una flecha y unas líneas de texto
  //  fingido. Trazos, no tarjetas — es lo que la separa del tablero.
  const trazo = new Graphics();
  const rect = (y: number, w: number, z: number, h: number) => {
    const a = aPantalla(0, gy + y, z + h);
    const b = aPantalla(0, gy + y + w, z + h);
    const c = aPantalla(0, gy + y + w, z);
    const d = aPantalla(0, gy + y, z);
    trazo.poly([a.x, a.y, b.x, b.y, c.x, c.y, d.x, d.y].slice(0)).stroke(
      { width: 1.4, color: PALETA.azulTecno, alpha: 0.8 });
  };
  rect(0.25, 0.6, z1 - 0.65, 0.4);
  rect(L - 0.85, 0.6, z1 - 0.65, 0.4);
  const a = aPantalla(0, gy + 0.9, z1 - 0.45);
  const b = aPantalla(0, gy + L - 0.9, z1 - 0.45);
  trazo.moveTo(a.x, a.y).lineTo(b.x, b.y)
       .stroke({ width: 1.4, color: PALETA.ember, alpha: 0.8 });
  for (let i = 0; i < 4; i++) {
    const p = aPantalla(0, gy + 0.3, z0 + 0.5 - i * 0.14);
    const q = aPantalla(0, gy + 0.3 + (L - 0.8) * (0.5 + 0.12 * ((i * 3) % 4)), z0 + 0.5 - i * 0.14);
    trazo.moveTo(p.x, p.y).lineTo(q.x, q.y);
  }
  trazo.stroke({ width: 1, color: PALETA.textoTenue, alpha: 0.6 });
  nodo.addChild(trazo);
  return { nodo };
}

/**
 * UNA IMPRESORA multifunción con su pila de papel.
 *
 * Administración es el área que imprime, sella y despacha, y una multifunción
 * es lo que la distingue de una oficina cualquiera.
 */
function construirImpresora(gx: number, gy: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, gy);
  const g = new Graphics();

  caja(g, gx, gy, 0, 0.9, 1.0, 0.62, tono(PALETA.escritorioPata, 0.1));
  caja(g, gx + 0.05, gy + 0.05, 0.62, 0.8, 0.9, 0.34, PALETA.muroRemate);
  //  La bandeja de salida: la ranura con el papel asomando.
  caja(g, gx - 0.01, gy + 0.12, 0.5, 0.04, 0.72, 0.06, PALETA.pisoProfundo);
  caja(g, gx - 0.06, gy + 0.16, 0.52, 0.1, 0.62, 0.02, PALETA.textoClaro);
  //  El panel de control, inclinado hacia quien lo usa.
  caja(g, gx + 0.1, gy + 0.1, 0.97, 0.3, 0.34, 0.03, PALETA.pantallaMarco);
  const p = aPantalla(gx + 0.25, gy + 0.27, 1.0);
  g.circle(p.x, p.y, 2.6).fill({ color: PALETA.azulTecnoTenue, alpha: 0.85 });
  nodo.addChild(g);
  return { nodo };
}

/**
 * UNA CAJA FUERTE empotrada en su módulo, con su dial y su manija.
 *
 * La pieza de la sala que maneja dinero. No la tiene nadie más, y a diferencia
 * de un armario —que es un mueble— esto se lee como un bloque macizo.
 */
function construirCajaFuerte(gx: number, gy: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, gy);
  const g = new Graphics();

  //  El módulo que la sostiene, y la caja encima: una caja fuerte a ras del
  //  suelo se lee como un cubo de basura.
  caja(g, gx, gy, 0, 0.8, 0.9, 0.55, PALETA.escritorioPata);
  caja(g, gx + 0.04, gy + 0.04, 0.55, 0.72, 0.82, 0.78, tono(PALETA.rackCuerpo, 0.1));
  //  La puerta, un plano hundido respecto del marco.
  caja(g, gx + 0.02, gy + 0.12, 0.64, 0.03, 0.66, 0.6, tono(PALETA.metal, -0.32));
  nodo.addChild(g);

  const herraje = new Graphics();
  //  El dial y la manija, lo único que la identifica a esta escala.
  const d = aPantalla(gx + 0.01, gy + 0.36, 0.98);
  herraje.circle(d.x, d.y, 4.2).fill({ color: PALETA.metal })
         .circle(d.x, d.y, 2.4).fill({ color: tono(PALETA.metal, -0.3) });
  for (let i = 0; i < 8; i++) {
    const a = (i / 8) * Math.PI * 2;
    herraje.circle(d.x + Math.cos(a) * 5.6, d.y + Math.sin(a) * 2.8, 0.6)
           .fill({ color: PALETA.textoTenue, alpha: 0.8 });
  }
  const m = aPantalla(gx + 0.01, gy + 0.62, 0.94);
  herraje.rect(m.x - 1, m.y - 7, 2, 14).fill({ color: PALETA.metal });
  nodo.addChild(herraje);
  return { nodo };
}

/**
 * UNA BIBLIOTECA de pared: estantes altos con libros de lomo ancho.
 *
 * Se distingue de `estanteria` a propósito. Aquélla son cuatro baldas de
 * CARPETAS de archivo, delgadas y todas iguales, y dice «acá se guardan
 * expedientes». Ésta tiene libros de distinto grosor y alguno tumbado, y dice
 * «acá se consulta». Es el mueble de un despacho, no el de un archivo.
 */
function construirBiblioteca(gy: number, largo: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(0.25, gy);
  const g = new Graphics();

  const L = Math.max(1.6, largo || 2.6);
  caja(g, 0.1, gy, 0, 0.44, L, 3.0, PALETA.madera);
  //  Cinco baldas, más separadas que las de la estantería: caben libros de pie.
  for (let i = 0; i < 5; i++) {
    const z = 0.3 + i * 0.56;
    panelMuroLateral(g, gy + 0.05, L - 0.1, z, z + 0.055, PALETA.maderaClara);
    let y = gy + 0.14;
    let k = i * 5;
    while (y < gy + L - 0.25) {
      const ancho = 0.08 + ((k * 11) % 7) * 0.02;
      const alto = 0.34 + ((k * 17) % 5) * 0.03;
      //  Uno de cada siete, tumbado sobre los demás: es lo que separa una
      //  biblioteca en uso de una fila de lomos iguales.
      const tumbado = k % 7 === 3;
      const color = [PALETA.rust, PALETA.moss, PALETA.clay, PALETA.azulTecno,
                     PALETA.maderaClara][k % 5];
      if (tumbado) {
        panelMuroLateral(g, y, ancho * 2.4, z + 0.055, z + 0.055 + 0.09, color, 0.8);
        y += ancho * 2.4 + 0.02;
      } else {
        panelMuroLateral(g, y, ancho, z + 0.055, z + 0.055 + alto, color, 0.8);
        y += ancho + 0.012;
      }
      k++;
    }
  }
  nodo.addChild(g);
  return { nodo };
}

/**
 * LA PANTALLA DE VIDEOCONFERENCIA, con su barra de cámara encima.
 *
 * La pieza protagonista de una sala de reuniones. Se distingue del `tablero`
 * —que es una pantalla de datos llena de tarjetas— y de la `pizarra` —blanca y
 * escrita a mano— porque lo que muestra son personas: dos recuadros con una
 * silueta cada uno.
 *
 * Las siluetas son genéricas a propósito: dibujar caras reconocibles sería
 * inventar gente en una reunión que nadie convocó.
 */
function construirVideoconferencia(gy: number, largo: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(0.22, gy);
  const g = new Graphics();

  const L = Math.max(2.0, largo || 2.8);
  const z0 = 1.5;
  const z1 = 2.85;
  panelMuroLateral(g, gy - 0.1, L + 0.2, z0 - 0.1, z1 + 0.1, PALETA.pantallaMarco);
  panelMuroLateral(g, gy, L, z0, z1, PALETA.noche);
  //  La barra de la cámara, encima del marco, con su ojo.
  panelMuroLateral(g, gy + L * 0.3, L * 0.4, z1 + 0.12, z1 + 0.2, PALETA.rackCuerpo);
  const ojo = aPantalla(0, gy + L * 0.5, z1 + 0.16);
  g.circle(ojo.x, ojo.y, 2).fill({ color: PALETA.pisoProfundo })
   .circle(ojo.x, ojo.y, 1).fill({ color: PALETA.azulTecnoTenue, alpha: 0.9 });
  nodo.addChild(g);

  //  Los dos recuadros de participante, con hombros y cabeza.
  const gente = new Graphics();
  for (let i = 0; i < 2; i++) {
    const y0 = gy + 0.14 + i * (L - 0.28) / 2;
    const w = (L - 0.28) / 2 - 0.1;
    panelMuroLateral(gente, y0, w, z0 + 0.14, z1 - 0.14, tono(PALETA.azulTecno, -0.25));
    //  La cabeza.
    const c = aPantalla(0, y0 + w / 2, z1 - 0.52);
    gente.circle(c.x, c.y, 4.6).fill({ color: PALETA.piel, alpha: 0.85 });
    //  Los hombros, un trapecio bajo la cabeza.
    panelMuroLateral(gente, y0 + w * 0.2, w * 0.6, z0 + 0.2, z1 - 0.62,
                     PALETA.camisa, 0.85);
  }
  nodo.addChild(gente);
  return { nodo };
}

/**
 * BANDEJAS DE DOCUMENTOS apiladas sobre un módulo bajo.
 *
 * La pieza de Finanzas y Auditoría: donde entra, espera y sale el papel. Se
 * distingue de la estantería —que guarda lo ya archivado— porque esto es lo
 * que está EN TRÁMITE, y por eso las bandejas van abiertas y con hojas
 * asomando.
 */
function construirBandejas(gx: number, gy: number, cuantas: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, gy);
  const g = new Graphics();

  //  El módulo bajo que las sostiene.
  caja(g, gx, gy, 0, 0.7, 1.0, 0.68, PALETA.escritorioPata);
  caja(g, gx - 0.02, gy - 0.02, 0.68, 0.74, 1.04, 0.05, PALETA.escritorioTapa);

  const n = Math.max(2, Math.min(5, Math.trunc(cuantas) || 3));
  for (let i = 0; i < n; i++) {
    const z = 0.73 + i * 0.17;
    //  La bandeja: un marco con su suelo, separada de la de abajo por cuatro
    //  patas cortas. Es ese aire entre bandeja y bandeja lo que las hace una
    //  pila de bandejas y no un bloque.
    caja(g, gx + 0.08, gy + 0.1, z, 0.54, 0.8, 0.03, PALETA.metal);
    caja(g, gx + 0.08, gy + 0.1, z + 0.03, 0.54, 0.03, 0.08, PALETA.metal);
    caja(g, gx + 0.08, gy + 0.87, z + 0.03, 0.54, 0.03, 0.08, PALETA.metal);
    //  Las hojas, sobresaliendo un poco: nunca las mismas en cada bandeja.
    if (i % 3 !== 2) {
      caja(g, gx + 0.1 + (i % 2) * 0.03, gy + 0.14, z + 0.03,
           0.5, 0.72, 0.035 + (i % 2) * 0.02, PALETA.textoClaro, 0.92);
    }
  }
  nodo.addChild(g);
  return { nodo };
}

/**
 * EL TURNERO: la columna con el número de atención, en la sala de espera.
 *
 * Es la pieza que dice «acá se hace fila» y no la tiene nadie más en la sede.
 * Un pedestal con una pantalla de siete segmentos arriba y la ranura de los
 * tiquetes debajo.
 *
 * El número que muestra es FIJO y decorativo: un turnero que contara algo
 * estaría afirmando cuánta gente espera, y eso es una métrica que ninguna
 * medición respalda. Es la misma regla que el videowall del NOC.
 */
function construirTurnero(gx: number, gy: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, gy);
  const g = new Graphics();

  //  El pedestal, angosto y alto: se ve de lejos sin ocupar sitio de paso.
  caja(g, gx, gy, 0, 0.34, 0.42, 1.25, tono(PALETA.escritorioPata, 0.06));
  caja(g, gx - 0.02, gy - 0.02, 0, 0.38, 0.46, 0.06, PALETA.muroRemate);
  //  La cabeza con la pantalla, inclinada hacia la sala.
  caja(g, gx - 0.04, gy - 0.04, 1.25, 0.42, 0.5, 0.46, PALETA.pantallaMarco);
  caja(g, gx - 0.06, gy + 0.02, 1.32, 0.03, 0.38, 0.32, PALETA.noche);
  nodo.addChild(g);

  //  Los dos dígitos, dibujados como barras: a esta escala un texto no se lee
  //  y una forma de siete segmentos sí se reconoce.
  const digitos = new Graphics();
  for (const [d, patron] of [[0, [1, 1, 1, 0, 1, 1, 1]], [1, [1, 0, 1, 1, 1, 0, 1]]] as const) {
    const base = gy + 0.1 + d * 0.16;
    //  arriba, sup-izq, medio, inf-der... siete tramos sobre una retícula.
    const tramos: [number, number, number][] = [
      [0.0, 0.11, 1.52], [0.0, 0.0, 1.44], [0.0, 0.11, 1.44],
      [0.1, 0.0, 1.44], [0.0, 0.11, 1.36], [0.1, 0.0, 1.36], [0.0, 0.11, 1.36]
    ];
    patron.forEach((on, i) => {
      if (!on) return;
      const [dy, w, z] = tramos[i];
      caja(digitos, gx - 0.07, base + dy, z, 0.02, Math.max(w, 0.03), w > 0 ? 0.022 : 0.075,
           ACENTO_CLARO, 0.9);
    });
  }
  nodo.addChild(digitos);

  //  La ranura de los tiquetes.
  const ranura = new Graphics();
  caja(ranura, gx - 0.03, gy + 0.1, 0.78, 0.02, 0.2, 0.03, PALETA.pisoProfundo);
  nodo.addChild(ranura);
  return { nodo };
}

/**
 * UNA MESA DE REVISIÓN: tablero rectangular con dos sillas enfrentadas.
 *
 * Auditoría y Recursos Humanos se sientan con alguien enfrente — a revisar un
 * expediente o a entrevistar—, y eso es distinto de la mesa redonda de reunión
 * informal que tiene media sede.
 */
function construirMesaDeRevision(gx: number, gy: number, largo: number): Mueble {
  const nodo = new Container();
  nodo.zIndex = profundidad(gx, gy);
  const g = new Graphics();

  const L = Math.max(1.6, largo || 2.2);
  caja(g, gx, gy, 0.7, 1.1, L, 0.07, PALETA.maderaClara);
  for (const [dx, dy] of [[0.08, 0.1], [0.08, L - 0.26], [0.94, 0.1], [0.94, L - 0.26]]) {
    caja(g, gx + dx, gy + dy, 0, 0.08, 0.16, 0.7, PALETA.escritorioPata);
  }
  //  Las dos sillas, enfrentadas a lo ancho: es la pose de una revisión.
  for (const dx of [-0.52, 1.24]) {
    caja(g, gx + dx, gy + L / 2 - 0.26, 0.42, 0.44, 0.52, 0.06, PALETA.sillaTela);
    caja(g, gx + dx + (dx < 0 ? 0 : 0.38), gy + L / 2 - 0.26, 0.48, 0.06, 0.52, 0.5,
         PALETA.sillaTela);
    caja(g, gx + dx + 0.18, gy + L / 2 - 0.08, 0, 0.08, 0.14, 0.42, PALETA.sillaBase);
  }
  //  El expediente abierto sobre la mesa, con su pila al lado.
  caja(g, gx + 0.3, gy + L / 2 - 0.3, 0.77, 0.44, 0.6, 0.01, PALETA.textoClaro);
  caja(g, gx + 0.32, gy + 0.22, 0.77, 0.38, 0.4, 0.08, PALETA.clayClaro);
  nodo.addChild(g);
  return { nodo };
}

/* ════════════════════════════════════════════════════════════════════════════
   El montaje del recinto
   ════════════════════════════════════════════════════════════════════════════ */

/**
 * De qué sabe dibujar la escena.
 *
 * Un registro por TIPO, no una lista de llamadas. Es lo que permite que la
 * planta sea un dato: agregar un mueble a una sala es una fila más, y agregar
 * un TIPO nuevo de mueble es una entrada acá. Un tipo que no está se ignora y
 * se cuenta — no se dibuja «algo parecido», que es como una escena empieza a
 * mostrar lo que nadie pidió.
 */
const TIPOS: Record<string, (m: Mueble2D, tx: Texturas) => Mueble> = {
  mampara: (m) => construirMampara(m.gx ?? 0, m.desde ?? 0, m.hasta ?? 0, m.vano ?? [0, 0]),
  zona: (m) => construirZona(m.gx ?? 0, m.gy ?? 0, m.ancho ?? 1, m.fondo ?? 1),
  ducto: (m) => construirDucto(m.gy ?? 0, m.desde ?? 0, m.hasta ?? 0),
  tablero: (m) => construirTableroDePared(m.gy ?? 0),
  armario: (m, tx) => construirArmario(m.gy ?? 0, tx),
  panel_fibra: (m) => construirPanelDeFibra(m.gy ?? 0),
  luminaria: (m, tx) => construirLuminaria(m.gx ?? 0, m.gy ?? 0, tx),
  planta: (m, tx) => construirPlanta(m.gx ?? 0, m.gy ?? 0, tx),
  banco: (m) => construirBanco(m.gx ?? 0, m.gy ?? 0),
  dispensador: (m) => construirDispensador(m.gx ?? 0, m.gy ?? 0),
  mostrador: (m) => construirMostrador(m.gx ?? 0, m.gy ?? 0, m.largo ?? 2),
  mesa: (m, tx) => construirMesa(m.gx ?? 0, m.gy ?? 0, tx),
  estanteria: (m) => construirEstanteria(m.gy ?? 0, m.largo ?? 2),
  //  La biblioteca de las piezas de red. Son las que hacen reconocible un area
  //  sin leer el letrero.
  videowall: (m) => construirVideowall(m.gx ?? 0, m.ancho ?? 4),
  rack: (m) => construirRack(m.gx ?? 0, m.gy ?? 0, m.unidades ?? 5),
  bobina: (m) => construirBobina(m.gx ?? 0, m.gy ?? 0),
  cajas: (m) => construirCajasDeMaterial(m.gx ?? 0, m.gy ?? 0, m.cuantas ?? 3),
  banco_trabajo: (m) => construirBancoDePreparacion(m.gx ?? 0, m.gy ?? 0, m.largo ?? 2.6),
  pizarra: (m) => construirPizarra(m.gy ?? 0, m.largo ?? 2.4),
  impresora: (m) => construirImpresora(m.gx ?? 0, m.gy ?? 0),
  turnero: (m) => construirTurnero(m.gx ?? 0, m.gy ?? 0),
  bandejas: (m) => construirBandejas(m.gx ?? 0, m.gy ?? 0, m.cuantas ?? 3),
  videoconferencia: (m) => construirVideoconferencia(m.gy ?? 0, m.largo ?? 2.8),
  caja_fuerte: (m) => construirCajaFuerte(m.gx ?? 0, m.gy ?? 0),
  biblioteca: (m) => construirBiblioteca(m.gy ?? 0, m.largo ?? 2.6),
  mesa_revision: (m) => construirMesaDeRevision(m.gx ?? 0, m.gy ?? 0, m.largo ?? 2.2),
  //  Los tres del nucleo vertical. Entran al catalogo como cualquier otro: la
  //  escena sabe dibujar TIPOS y no sabe que esto es un nucleo.
  escalera: (m) => construirEscalera(m.gx ?? 0, m.gy ?? 0, m.alto ?? 4,
                                     m.peldanos ?? 9, m.desde ?? 0),
  ascensor: (m) => construirAscensor(m.gx ?? 0, m.gy ?? 0, m.alto ?? 3.6),
  columna: (m) => construirColumna(m.gx ?? 0, m.gy ?? 0, m.alto ?? 4.6)
};

/** Los tipos de mueble que una planta puede pedir. Para probarlo desde fuera. */
export const TIPOS_DE_MUEBLE = Object.keys(TIPOS);

export function construirOficina(planta: Planta, texturas: Texturas): Oficina {
  const raiz = new Container();
  raiz.sortableChildren = true;

  const mundo = planta.mundo;

  //  UNA PIEZA DE EDIFICIO NO ES UNA SALA, y sale por acá antes de tocar nada.
  //
  //  Sin esta salida temprana habría que apagar a mano el suelo, los muros, la
  //  losa, la baranda, el pasillo y los puestos para cada pieza, y el día que
  //  alguien agregue un elemento nuevo a `construirOficina` se le colará a la
  //  fachada. Una fachada con baldosas no da error: se ve rarísimo y no se
  //  sabe de dónde salió.
  if (planta.arquitectura) {
    const pieza = construirPieza(planta.arquitectura);
    if (pieza) raiz.addChild(pieza);
    return {
      raiz,
      mundo,
      puestos: [],
      sinTipo: pieza ? 0 : 1,
      animar() {},
      destruir() {
        raiz.destroy({ children: true });
      }
    };
  }

  ACENTO = planta.acento ?? PALETA.ember;
  ACENTO_CLARO = tono(ACENTO, 0.28);
  //  Sin pasillo se fija una franja vacía en vez de un `if` repartido por el
  //  dibujo del suelo: una sala sin pasillo es una sala con un pasillo de
  //  ancho cero, y así hay un solo camino de código.
  PASILLO = planta.pasillo ?? { desde: 0, hasta: 0 };

  //  La losa va DEBAJO del suelo, y por eso su zIndex es el mas bajo de la
  //  sala. Puesta por encima, el canto se dibuja sobre las baldosas y la
  //  planta parece tener un reborde en vez de un espesor.
  if (planta.losa) {
    const losa = construirLosa(mundo);
    losa.zIndex = -2500;
    raiz.addChild(losa);
  }

  const suelo = construirSuelo(mundo);
  suelo.zIndex = -2000;
  raiz.addChild(suelo);

  //  Por defecto SI lleva muros: una sala sola es lo que habia antes de que
  //  existieran los niveles, y tiene que seguir viendose igual.
  if (planta.muros !== false) {
    //  El núcleo no lleva muros opacos: lleva vidrio. Es un REEMPLAZO y no un
    //  añadido — dos cerramientos en el mismo plano dan un vidrio que no es
    //  transparente, y entonces no se ve la escalera que justifica la pieza.
    if (planta.vidrio) {
      const { interior, piel } = construirNucleoAcristalado(mundo);
      interior.zIndex = -1000;
      raiz.addChild(interior);
      //  LA PIEL VA POR DELANTE DE TODO LO DEL NÚCLEO, y por eso no puede ir
      //  en el mismo nodo: un vidrio que se dibuja detrás de la escalera no es
      //  un cerramiento, es un fondo. 900 lo deja sobre el mobiliario y bajo
      //  la capa de rótulos, que es donde tiene que estar.
      piel.zIndex = 900;
      piel.eventMode = 'none';
      raiz.addChild(piel);
    } else {
      const muros = construirMuros(mundo);
      muros.zIndex = -1000;
      raiz.addChild(muros);
    }
  }

  if (planta.rotuloFrontal) {
    const rot = construirRotuloFrontal(planta.rotuloFrontal, mundo);
    //  En la capa de rotulos no: esa va por encima de TODO, y el nombre de una
    //  sala del fondo taparia el personaje de una sala de delante. Esto va
    //  pegado a su propia losa, que es donde esta escrito.
    rot.zIndex = -2400;
    rot.eventMode = 'none';
    raiz.addChild(rot);
  }

  //  EL CERRAMIENTO de los dos lados que miran a la camara. Ver
  //  `construirAntepecho`: si lleva puerta, el hueco se abre y se marca.
  if (mundo.antepecho?.frente || mundo.antepecho?.derecha) {
    const cierre = construirAntepecho(mundo);
    //  Al mismo nivel que la baranda: por encima del suelo y por debajo del
    //  mobiliario, que si no un antepecho tacharia el escritorio de delante.
    cierre.zIndex = -1500;
    raiz.addChild(cierre);
  }

  if (planta.baranda) {
    const baranda = construirBaranda(mundo);
    //  Por encima del suelo y por debajo del mobiliario: una baranda delante
    //  de un escritorio lo tacharia.
    baranda.zIndex = -1500;
    raiz.addChild(baranda);
  }

  const animables: ((t: number, dt: number) => void)[] = [];

  if (planta.mural && planta.mural.paneles.length) {
    const mural = construirMural(texturas, planta.mural.paneles);
    mural.nodo.zIndex = -900;
    raiz.addChild(mural.nodo);
    animables.push(mural.animar);
  }

  const muebles: Mueble[] = [];
  let sinTipo = 0;
  for (const m of planta.mobiliario || []) {
    const hacer = TIPOS[m?.tipo];
    if (!hacer) {
      sinTipo++;
      continue;
    }
    muebles.push(hacer(m, texturas));
  }
  if (planta.cartel?.rotulo) {
    muebles.push(construirCartel(planta.cartel.rotulo, planta.cartel.gx, texturas));
  }
  for (const m of muebles) {
    raiz.addChild(m.nodo);
    if (m.animar) animables.push(m.animar);
  }

  //  La capa de rótulos, por encima de todo el mobiliario. Es lo que impide
  //  que un objeto cercano tape el nombre de un puesto lejano.
  const capaRotulos = new Container();
  capaRotulos.zIndex = 5000;
  capaRotulos.eventMode = 'none';
  raiz.addChild(capaRotulos);

  const puestos = (planta.puestos || []).map((def) => {
    const p = construirPuesto(def, texturas);
    raiz.addChild(p.nodo);
    capaRotulos.addChild(p.placa);
    return p;
  });

  return {
    raiz,
    mundo,
    puestos,
    /** Cuántos muebles pedía la planta que esta escena no sabe dibujar. */
    sinTipo,
    animar(t, dt) {
      for (const f of animables) f(t, dt);
    },
    destruir() {
      // `children: true` destruye el árbol completo. Las texturas se destruyen
      // aparte, porque son compartidas y las crea quien monta la escena: que
      // este método se las llevara rompería un segundo montaje en la misma
      // página, y el síntoma sería una escena en negro sin ningún error.
      raiz.destroy({ children: true });
    }
  };
}
