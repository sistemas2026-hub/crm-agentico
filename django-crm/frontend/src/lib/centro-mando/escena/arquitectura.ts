/**
 * LA SEDE: BASAMENTO, FACHADA, CUBIERTA Y EXTREMOS.
 *
 * Lo que convierte tres bandejas apiladas en un edificio. Nació el 31/10/2026,
 * con la primera referencia arquitectónica aprobada, y de una medición
 * incómoda: la escena cumplía 3 de los 8 criterios de esa referencia, y los
 * cuatro que fallaban —volumen, encuadre, núcleo legible, iluminación— no
 * fallaban por el motor gráfico. Fallaban porque **no había edificio**: había
 * salas, losas y columnas, y entre ellas, aire.
 *
 * QUÉ LLENA ESE AIRE, Y POR QUÉ ASÍ
 * ---------------------------------
 * La separación entre niveles es de quince unidades y no se puede bajar: la
 * desigualdad de oclusión de `edificio.js` la fija, y bajarla esconde
 * escritorios detrás de la losa de arriba. Así que las quince unidades se
 * quedan, y lo que cambia es QUÉ HAY en ellas. Una fachada continua de suelo a
 * suelo convierte ese hueco en la altura libre de una planta. Sin ella, las
 * mismas quince unidades son tres bandejas sobre pilotes.
 *
 * DÓNDE PUEDE IR UNA FACHADA EN UNA SECCIÓN ISOMÉTRICA
 * ----------------------------------------------------
 * En esta proyección el espectador mira desde `gx+gy` creciente, así que ve las
 * caras que miran a `+gx` y a `+gy`. Una fachada en el frente (`gy = fondo`)
 * taparía exactamente lo que hay que ver — es la razón por la que la franja de
 * circulación nunca tuvo muros.
 *
 * Por eso la envolvente de esta sede son tres piezas y no cuatro:
 *
 *   fondo    `gy = 0`        se ve su cara interior; es el telón de la sede
 *   extremo  `gx = ancho`    vidrio, se ve a través; cierra el volumen
 *   frente   `gy = fondo`    ABIERTO, a propósito: es el corte de la sección
 *
 * Y el corte se cuenta: en el frente quedan los retornos de fachada, dos
 * pedazos cortos de muro perpendicular. Sin ellos la planta no parece cortada,
 * parece que nunca tuvo fachada.
 *
 * NADA DE ACÁ SABE DE LA EMPRESA. Recibe celdas y colores. Quién trabaja en qué
 * piso lo decide `edificio.js`, que es quien pide estas piezas.
 */

import { Container, Graphics } from 'pixi.js';
import { aPantalla } from './isometria';
import { PALETA, tono } from './paleta';
import {
  caja,
  losaPlana,
  panelEnX,
  panelEnY,
  panelMuroFondo
} from './volumen';

/** Lo que `edificio.js` pide. Una pieza por planta, y la planta la coloca. */
export type PiezaDeArquitectura =
  | { tipo: 'basamento'; ancho: number; fondo: number; margen?: number }
  | {
      tipo: 'fachada';
      ancho: number;
      altura: number;
      /** Hasta qué `gx` hay otro nivel encima. Más allá, la fachada remata en
       *  peto de terraza en vez de subir hasta una losa que no existe. */
      sostenidaHasta?: number;
      acento?: number;
    }
  | { tipo: 'extremo'; fondo: number; altura: number; acento?: number }
  | { tipo: 'cubierta'; ancho: number; fondo: number; acento?: number }
  | { tipo: 'remate'; ancho: number; fondo: number; alto: number; acento?: number };

/** Altura del peto de una terraza o una cubierta, en celdas. */
const PETO = 1.1;

/** Cada cuántas celdas cae un machón de fachada. Coincide con las columnas. */
const PASO_MACHON = 6;

/* ════════════════════════════════════════════════════════════════════════════
   Vidrio
   ════════════════════════════════════════════════════════════════════════════ */

/**
 * Un paño de vidrio en el plano `gy = 0`, con sus montantes.
 *
 * EL VIDRIO NO ES UN RECTÁNGULO AZUL TRANSPARENTE. Un paño sin montantes se lee
 * como un agujero: lo que dice «esto es vidrio» son las divisiones verticales y
 * el brillo del borde superior, no la transparencia. Se vio al construirlo —el
 * primer intento, un solo polígono con alfa, parecía que a la fachada le
 * faltaba un trozo.
 *
 * El alfa es bajo a propósito: detrás del telón de fondo está la noche, y lo
 * que tiene que leerse es que hay un cerramiento, no taparlo.
 */
function panoDeFondo(
  g: Graphics,
  gx: number,
  ancho: number,
  z0: number,
  z1: number,
  interior: number
) {
  //  El vidrio: la noche de fuera teñida por la luz de dentro.
  panelMuroFondo(g, gx, ancho, z0, z1, PALETA.vidrio, 0.82);
  //  La luz del interior lamiendo el vidrio desde abajo. Es lo que hace que una
  //  oficina encendida se note desde fuera.
  panelMuroFondo(g, gx, ancho, z0, z0 + (z1 - z0) * 0.45, interior, 0.46);
  //  Los montantes, cada dos celdas.
  for (let x = gx; x <= gx + ancho + 0.001; x += 2) {
    panelMuroFondo(g, Math.min(x, gx + ancho - 0.09), 0.09, z0, z1, PALETA.montante, 0.95);
  }
  //  El brillo del canto alto: el detalle que convierte el paño en cristal.
  panelMuroFondo(g, gx, ancho, z1 - 0.1, z1, PALETA.vidrioBrillo, 0.5);
}

/* ════════════════════════════════════════════════════════════════════════════
   Las piezas
   ════════════════════════════════════════════════════════════════════════════ */

/**
 * EL BASAMENTO: lo que apoya el edificio en el suelo.
 *
 * Sin esto, el nivel más bajo flota: su losa termina en el aire y debajo está
 * el color del lienzo. Es el mismo defecto que las bandejas, una planta más
 * abajo, y se nota más porque es donde el ojo busca el suelo.
 *
 * Lleva explanada, zócalo, escalinata de acceso y jardineras. Las jardineras no
 * son adorno: son lo único verde de la escena y es lo que fija la escala — un
 * seto dice cuánto mide una planta, y una caja gris no.
 */
function construirBasamento(p: Extract<PiezaDeArquitectura, { tipo: 'basamento' }>): Container {
  const nodo = new Container();
  const g = new Graphics();
  //  Coordenadas LOCALES desde cero, y el compositor coloca la pieza en la
  //  esquina de afuera. Hacerlo con coordenadas negativas —el edificio en el
  //  cero y el zócalo asomando hacia atrás— deja el origen de la planta dentro
  //  de la pieza, y el orden de pintado se decide por ese origen: el basamento
  //  terminaba dibujándose DESPUÉS del núcleo y se lo comía.
  const { ancho, fondo } = p;
  const SUELO = -2.4;

  //  1 · La explanada. Va por debajo de todo y se extiende más allá del zócalo:
  //      un edificio sin suelo alrededor parece recortado y pegado encima.
  losaPlana(g, -5, -5, ancho + 10, fondo + 10, SUELO, PALETA.explanada);
  //  Juntas del pavimento, sólo en una dirección: en las dos, la explanada se
  //  convierte en papel milimetrado y le gana protagonismo al edificio.
  for (let x = -5; x < ancho + 10; x += 6) {
    const a = aPantalla(x, -5, SUELO);
    const b = aPantalla(x, fondo + 5, SUELO);
    g.moveTo(a.x, a.y).lineTo(b.x, b.y).stroke({ color: tono(PALETA.explanada, 0.3), width: 1 });
  }

  //  2 · El zócalo: la caja que levanta el edificio del suelo.
  caja(g, 0, 0, SUELO, ancho, fondo, -SUELO, PALETA.hormigon);
  //  Un filo claro en el borde superior. Es la línea que separa el edificio del
  //  suelo, y sin ella el zócalo y la losa del primer piso son una mancha.
  panelEnY(g, fondo, 0, ancho, -0.16, 0, PALETA.hormigonFilo, 0.85);
  panelEnX(g, ancho, 0, fondo, -0.16, 0, PALETA.hormigonFilo, 0.7);

  nodo.addChild(g);

  //  3 · La escalinata de acceso, al pie del núcleo. Tres peldaños anchos.
  const esc = new Graphics();
  for (let i = 0; i < 3; i++) {
    caja(esc, 2.5, fondo + 0.2 + i * 1.0, SUELO + i * 0.8,
         6, 1.0, 0.8, tono(PALETA.hormigon, 0.12 + i * 0.07));
  }
  nodo.addChild(esc);

  //  4 · Jardineras y balizas a lo largo del frente.
  const verde = new Graphics();
  for (let x = 11; x < ancho - 3.2; x += 4.6) {
    caja(verde, x, fondo - 2.2, 0, 2.8, 1.5, 0.5, PALETA.hormigonClaro);
    caja(verde, x + 0.2, fondo - 2.0, 0.5, 2.4, 1.1, 0.7, PALETA.seto);
    caja(verde, x + 0.6, fondo - 1.8, 1.2, 1.4, 0.6, 0.3, PALETA.setoClaro);
    //  La baliza: un punto de luz cálida a ras de suelo. Son las que dicen que
    //  el edificio está vivo de noche.
    const b = aPantalla(x + 3.6, fondo - 1.4, 0.4);
    verde.circle(b.x, b.y, 2.4).fill({ color: PALETA.luzCalida, alpha: 0.9 });
    verde.circle(b.x, b.y, 8).fill({ color: PALETA.luzCalida, alpha: 0.13 });
  }
  nodo.addChild(verde);
  return nodo;
}

/**
 * LA FACHADA DE FONDO: el telón de la sede, de suelo a suelo.
 *
 * Es la pieza que más cambia la lectura del edificio, y la razón está en la
 * aritmética: entre la losa de un nivel y la del siguiente hay quince unidades
 * y los muros de una sala miden cuatro. Once unidades de aire por planta, tres
 * plantas: treinta y tres unidades de nada, que en pantalla son casi novecientos
 * píxeles. Eso era lo que se leía como «bandejas flotando», y no se arregla
 * acercando los pisos —la oclusión lo prohíbe— sino poniendo edificio ahí.
 *
 * ARRIBA DE DONDE HAY OTRO NIVEL, la fachada sube hasta su losa. **Más allá, no:**
 * remata en peto de terraza. Una fachada que sube quince unidades hasta una losa
 * que no existe es un muro colgado en el aire, que es el mismo error que ya se
 * había cometido con las columnas y se vio en el navegador.
 */
function construirFachada(p: Extract<PiezaDeArquitectura, { tipo: 'fachada' }>): Container {
  const nodo = new Container();
  const g = new Graphics();
  const acento = p.acento ?? PALETA.azulTecno;
  const sostenida = Math.max(0, Math.min(p.ancho, p.sostenidaHasta ?? 0));

  /** La altura de la fachada en una `gx`: hasta la losa, o peto de terraza. */
  const alturaEn = (gx: number) => (gx < sostenida - 0.01 ? p.altura : PETO + 3.2);

  //  Se recorre en tramos entre machones, porque la altura cambia donde
  //  termina el nivel de arriba y un solo paño no puede tener dos alturas.
  const cortes: number[] = [0];
  for (let x = PASO_MACHON; x < p.ancho; x += PASO_MACHON) cortes.push(x);
  if (sostenida > 0.2 && sostenida < p.ancho - 0.2) cortes.push(sostenida);
  cortes.push(p.ancho);
  cortes.sort((a, b) => a - b);

  for (let i = 0; i < cortes.length - 1; i++) {
    const x0 = cortes[i];
    const x1 = cortes[i + 1];
    const w = x1 - x0;
    if (w < 0.12) continue;
    const h = alturaEn((x0 + x1) / 2);

    //  El antepecho, opaco: es lo que impide que las sillas se vean «a través»
    //  del suelo contra la noche.
    panelMuroFondo(g, x0, w, 0, 1.0, PALETA.hormigon);
    //  El revestimiento de madera a la altura de la vista. Es el único material
    //  templado del exterior y lo que evita que la sede sea vidrio y hormigón.
    panelMuroFondo(g, x0, w, 1.0, 1.35, PALETA.maderaClara, 0.9);
    //  El paño principal, a la altura de la gente.
    panoDeFondo(g, x0, w, 1.35, 4.1, PALETA.luzCalida);
    //  El dintel de madera que separa la planta de su doble altura.
    panelMuroFondo(g, x0, w, 4.1, 4.75, PALETA.madera);
    if (h > 5.4) {
      //  LA DOBLE ALTURA, Y LO QUE SE APRENDIÓ MIRÁNDOLA.
      //
      //  Entre el techo de una planta y la losa de la siguiente hay once
      //  unidades que la oclusión obliga a dejar. El primer intento las pintó
      //  como vidrio apagado —«ahí arriba no trabaja nadie»— y en el navegador
      //  eso fue exactamente lo que se vio: una banda muerta por planta, tres
      //  bandas muertas apiladas, y el edificio volviendo a parecer bandejas
      //  separadas por nada.
      //
      //  Lo que esas once unidades son de verdad es un ATRIO, y un atrio de
      //  noche se ve encendido. Se pinta brillante a propósito: el hueco que
      //  la geometría impone se convierte en lo que mejor dice «edificio de
      //  oficinas» desde lejos.
      panoDeFondo(g, x0, w, 4.75, h - 1.25, PALETA.luzCalida);
      //  Los forjados intermedios del atrio: dos líneas horizontales que le
      //  dan escala. Sin ellas el paño alto es un rectángulo y no se sabe si
      //  mide tres metros o diez.
      for (let z = 6.6; z < h - 1.9; z += 3.1) {
        panelMuroFondo(g, x0, w, z, z + 0.22, PALETA.hormigonClaro, 0.75);
        panelMuroFondo(g, x0, w, z + 0.22, z + 0.3, PALETA.luzCalida, 0.5);
      }
      //  El canto de la losa de arriba, visto desde dentro.
      panelMuroFondo(g, x0, w, h - 1.25, h, PALETA.hormigon);
      panelMuroFondo(g, x0, w, h - 0.16, h, PALETA.hormigonFilo, 0.55);
    } else {
      //  Tramo sin nivel encima: peto de terraza y se acabó.
      panelMuroFondo(g, x0, w, 4.75, h, PALETA.hormigon);
      panelMuroFondo(g, x0, w, h - 0.14, h, PALETA.hormigonFilo, 0.8);
    }
  }

  //  Los machones, por delante del cerramiento: la estructura que se ve.
  for (let x = 0; x <= p.ancho - 0.6; x += PASO_MACHON) {
    const h = alturaEn(x + 0.3);
    caja(g, x, -0.5, 0, 0.62, 0.5, h, tono(PALETA.hormigon, -0.1));
  }

  //  La franja de acento a la altura del forjado: es la línea horizontal que
  //  ata toda la fachada y la que le da el aire tecnológico de la referencia.
  panelMuroFondo(g, 0, p.ancho, 4.78, 4.92, acento, 0.75);

  nodo.addChild(g);
  return nodo;
}

/**
 * EL EXTREMO: la cara de vidrio que cierra el volumen por su lado largo.
 *
 * Va en `gx = 0` de su propio contenedor, y el compositor lo coloca en el
 * `gx` donde termina el nivel. Se dibuja DESPUÉS de las salas —su origen tiene
 * la profundidad más alta del nivel— y por eso puede ser transparente sin que
 * el orden de pintado lo mande detrás.
 *
 * ALFA ALTO Y NO OPACO: un extremo opaco taparía la última sala entera, que es
 * justo lo que una sección abierta no hace. Lo que tiene que decir es «acá
 * termina el edificio», y para eso alcanza el marco y un velo.
 */
function construirExtremo(p: Extract<PiezaDeArquitectura, { tipo: 'extremo' }>): Container {
  const nodo = new Container();
  const g = new Graphics();
  const acento = p.acento ?? PALETA.azulTecno;

  //  El velo de vidrio, de suelo a losa.
  panelEnX(g, 0, 0, p.fondo, 0, p.altura, PALETA.vidrio, 0.26);
  //  Los montantes verticales, cada dos celdas y medio.
  for (let y = 0; y <= p.fondo - 0.1; y += 2.5) {
    panelEnX(g, 0, y, 0.1, 0, p.altura, PALETA.montante, 0.8);
  }
  //  Los travesaños a la altura de cada forjado.
  for (const z of [1.1, 4.3, p.altura - 1.2]) {
    if (z > 0 && z < p.altura) {
      panelEnX(g, 0, 0, p.fondo, z, z + 0.12, PALETA.montante, 0.85);
    }
  }
  //  El pilar de esquina, opaco: es lo que hace que el vidrio tenga un borde en
  //  vez de desvanecerse.
  caja(g, -0.55, 0, 0, 0.55, 0.62, p.altura, PALETA.hormigonClaro);
  caja(g, -0.55, p.fondo - 0.62, 0, 0.55, 0.62, p.altura, PALETA.hormigonClaro);
  //  El filo de acento del canto superior.
  panelEnX(g, 0, 0, p.fondo, p.altura - 0.16, p.altura, acento, 0.5);

  nodo.addChild(g);
  return nodo;
}

/**
 * LA CUBIERTA: lo que remata el edificio por arriba.
 *
 * Sin ella el nivel más alto se lee como una planta más a la que le cortaron el
 * techo, y el edificio no termina: se interrumpe. Lleva losa, peto, equipos de
 * clima y jardineras, que son los cuatro objetos que dicen «azotea» sin que
 * haga falta explicarlo.
 */
function construirCubierta(p: Extract<PiezaDeArquitectura, { tipo: 'cubierta' }>): Container {
  const nodo = new Container();
  const g = new Graphics();
  const acento = p.acento ?? PALETA.azulTecno;

  //  1 · La losa, con su espesor.
  caja(g, 0, 0, -0.75, p.ancho, p.fondo, 0.75, tono(PALETA.hormigon, -0.34));
  //  Las juntas del pavimento de la azotea. Son lo único que le da textura a
  //  un plano que, por tamaño, es la superficie más grande de la escena.
  for (let x = 3; x < p.ancho; x += 3) {
    const a = aPantalla(x, 0.5, 0);
    const b2 = aPantalla(x, p.fondo - 0.5, 0);
    g.moveTo(a.x, a.y).lineTo(b2.x, b2.y)
     .stroke({ color: tono(PALETA.hormigon, -0.14), width: 1, alpha: 0.6 });
  }
  //  El filo iluminado del canto, en los dos bordes que se ven.
  panelEnY(g, p.fondo, 0, p.ancho, -0.16, 0, PALETA.hormigonFilo, 0.8);
  panelEnX(g, p.ancho, 0, p.fondo, -0.16, 0, PALETA.hormigonFilo, 0.65);

  //  2 · El peto, en los cuatro bordes. Los dos del fondo se ven por dentro y
  //      son los que dan el espesor de la azotea; los dos del frente la cierran.
  caja(g, 0, 0, 0, p.ancho, 0.42, PETO, PALETA.hormigonClaro);
  caja(g, 0, 0, 0, 0.42, p.fondo, PETO, PALETA.hormigonClaro);
  caja(g, 0, p.fondo - 0.42, 0, p.ancho, 0.42, PETO, PALETA.hormigonClaro);
  caja(g, p.ancho - 0.42, 0, 0, 0.42, p.fondo, PETO, PALETA.hormigonClaro);
  //  Una línea de acento corrida por el remate: es el perfil nocturno del
  //  edificio, lo que lo dibuja contra el cielo.
  panelEnY(g, p.fondo, 0, p.ancho, PETO - 0.13, PETO, acento, 0.6);
  panelEnX(g, p.ancho, 0, p.fondo, PETO - 0.13, PETO, acento, 0.45);

  nodo.addChild(g);

  //  3 · Los equipos: tres cajas de clima sobre sus bancadas, y conductos.
  const eq = new Graphics();
  for (let i = 0; i < 3; i++) {
    const x = 3.5 + i * 5.2;
    if (x + 3 > p.ancho - 1) break;
    caja(eq, x, 1.4, 0, 3, 2.1, 0.22, tono(PALETA.hormigon, -0.1));
    caja(eq, x + 0.25, 1.65, 0.22, 2.5, 1.6, 1.15, PALETA.metal);
    //  La rejilla, que es lo que distingue una máquina de una caja.
    for (let r = 0; r < 4; r++) {
      panelEnY(eq, 1.65 + 1.6, x + 0.35, 2.3,
               0.45 + r * 0.17, 0.55 + r * 0.17, tono(PALETA.metal, -0.3), 0.9);
    }
  }
  nodo.addChild(eq);

  //  4 · LOS LUCERNARIOS, que son lo que salva la azotea.
  //
  //      Medido mirando la captura: la cubierta ocupa una cuarta parte de la
  //      imagen y estaba vacía. Un plano oscuro enorme no es neutro — le quita
  //      el peso al edificio iluminado que tiene debajo, que es justo lo que
  //      hay que mirar. Un lucernario corrido devuelve esa superficie a la
  //      escena: es luz que sale del propio edificio, no brillo añadido.
  const luz = new Graphics();
  for (let x = 2.4; x < p.ancho - 3.4; x += 7.4) {
    const w = Math.min(4.6, p.ancho - 3.4 - x);
    if (w < 1.4) break;
    //  El cércol: un lucernario sin marco es una mancha clara en el suelo.
    caja(luz, x, p.fondo - 6.2, 0, w, 3.2, 0.26, PALETA.hormigonClaro);
    losaPlana(luz, x + 0.3, p.fondo - 5.9, w - 0.6, 2.6, 0.3, PALETA.luzCalida, 0.72);
    losaPlana(luz, x + 0.3, p.fondo - 5.9, w - 0.6, 2.6, 0.32, PALETA.vidrioBrillo, 0.22);
    //  Los montantes del vidrio, en el eje largo.
    for (let k = 1; k < 3; k++) {
      losaPlana(luz, x + 0.3 + (w - 0.6) * k / 3, p.fondo - 5.9, 0.1, 2.6, 0.33,
                PALETA.montante, 0.8);
    }
  }
  nodo.addChild(luz);

  //  5 · Jardineras de azotea, pegadas al peto del frente.
  const verde = new Graphics();
  for (let x = 2.2; x < p.ancho - 3; x += 4.6) {
    caja(verde, x, p.fondo - 2.0, 0, 2.6, 1.2, 0.42, PALETA.hormigonClaro);
    caja(verde, x + 0.2, p.fondo - 1.85, 0.42, 2.2, 0.9, 0.6, PALETA.seto);
  }
  nodo.addChild(verde);
  return nodo;
}

/**
 * EL REMATE DEL NÚCLEO: la caja que sobresale de la cubierta.
 *
 * Un ascensor necesita recorrido por encima de la última parada, y esa caja es
 * lo que de verdad hace que un volumen se lea como edificio de oficinas y no
 * como un bloque. En la referencia es la pieza más alta de la sede.
 */
function construirRemate(p: Extract<PiezaDeArquitectura, { tipo: 'remate' }>): Container {
  const nodo = new Container();
  const g = new Graphics();
  const acento = p.acento ?? PALETA.azulTecno;

  caja(g, 0, 0, 0, p.ancho, p.fondo, p.alto, PALETA.hormigonClaro);
  //  Las dos caras vistas, acristaladas: el hueco del ascensor se ve iluminado
  //  desde abajo, que es lo que lo ata a los tres pisos.
  panelEnY(g, p.fondo, 0.4, p.ancho - 0.8, 0.5, p.alto - 0.6, PALETA.vidrio, 0.85);
  panelEnY(g, p.fondo, 0.4, p.ancho - 0.8, 0.5, 1.9, acento, 0.35);
  panelEnX(g, p.ancho, 0.4, p.fondo - 0.8, 0.5, p.alto - 0.6, PALETA.vidrio, 0.7);
  //  La cornisa.
  caja(g, -0.3, -0.3, p.alto, p.ancho + 0.6, p.fondo + 0.6, 0.3, PALETA.hormigon);
  //  El testigo del remate: el punto rojo que corona cualquier edificio alto.
  const c = aPantalla(p.ancho / 2, p.fondo / 2, p.alto + 0.6);
  g.circle(c.x, c.y, 2.2).fill({ color: PALETA.rustClaro, alpha: 0.95 });
  g.circle(c.x, c.y, 6).fill({ color: PALETA.rustClaro, alpha: 0.16 });

  nodo.addChild(g);
  return nodo;
}

/**
 * EL NÚCLEO VERTICAL, ACRISTALADO.
 *
 * Es el criterio 5 de la referencia: *«debe existir un núcleo vertical de
 * circulación»*, y la medición del 31/10/2026 lo dejó en «existe, pero no se
 * lee». Existía —escaleras, ascensor, rellano, apilados en la misma huella— y
 * estaba pintado con los mismos dos tonos que los muros de cualquier sala. Un
 * elemento que es igual a todo lo demás no comunica nada: hay que buscarlo
 * sabiendo que está.
 *
 * Lo que lo vuelve reconocible no es el color, es el MATERIAL. Una torre de
 * vidrio con sus montantes y una línea de luz por planta se lee como el
 * ascensor de un edificio incluso a escala de conjunto, cuando las escaleras de
 * dentro ya no se distinguen. Y al apilarse en la misma huella, las líneas de
 * cada planta quedan alineadas: eso es lo que dice que los tres pisos son el
 * mismo edificio.
 *
 * Reemplaza a `construirMuros` para esta planta, no se suma: dos cerramientos
 * en el mismo plano producen un vidrio que no es transparente.
 */
export function construirNucleoAcristalado(mundo: {
  ancho: number;
  fondo: number;
  alto: number;
}): Container {
  const nodo = new Container();
  const g = new Graphics();
  const h = mundo.alto;

  //  El zócalo opaco: el canto del forjado del que arranca la torre.
  panelMuroFondo(g, 0, mundo.ancho, 0, 0.55, PALETA.hormigon);
  panelEnX(g, 0, 0, mundo.fondo, 0, 0.55, tono(PALETA.hormigon, -0.14));

  //  Los dos paños de vidrio. Alfa bajo: lo que importa es que se vea la
  //  escalera por dentro, que es lo que prueba que es un núcleo y no un pilar.
  panelMuroFondo(g, 0, mundo.ancho, 0.55, h, PALETA.vidrio, 0.5);
  panelEnX(g, 0, 0, mundo.fondo, 0.55, h, PALETA.vidrio, 0.62);
  //  LA LUZ DE DENTRO. Un hueco de ascensor de noche está iluminado, y es lo
  //  único que hace que la torre se distinga del cielo a escala de edificio:
  //  medido contra la referencia, con el vidrio solo seguía sin leerse.
  panelMuroFondo(g, 0.3, mundo.ancho - 0.6, 0.7, h - 0.5, PALETA.luzCalida, 0.3);
  panelEnX(g, 0, 0.3, mundo.fondo - 0.6, 0.7, h - 0.5, PALETA.luzCalidaTenue, 0.34);

  //  Los montantes. Cada celda y media, que es más tupido que en la fachada:
  //  una caja de ascensor tiene la carpintería más densa, y a escala de
  //  conjunto es la textura que la distingue de un paño de fachada.
  for (let x = 0; x <= mundo.ancho + 0.01; x += 1.5) {
    panelMuroFondo(g, Math.min(x, mundo.ancho - 0.1), 0.1, 0.55, h, PALETA.montante, 0.9);
  }
  for (let y = 0; y <= mundo.fondo + 0.01; y += 1.5) {
    panelEnX(g, 0, Math.min(y, mundo.fondo - 0.1), 0.1, 0.55, h, PALETA.montante, 0.9);
  }

  //  LA LÍNEA DE PLANTA. Una franja de luz azul en el arranque y otra en el
  //  remate: apiladas, son las que atan los niveles a la vista.
  for (const z of [0.62, h - 0.42]) {
    panelMuroFondo(g, 0, mundo.ancho, z, z + 0.18, PALETA.azulTecno, 0.85);
    panelEnX(g, 0, 0, mundo.fondo, z, z + 0.18, PALETA.azulTecnoTenue, 0.9);
  }

  //  La franja vertical del hueco del ascensor, de suelo a techo. Es lo que
  //  dice «por acá se sube» cuando la cabina ya no se distingue.
  panelMuroFondo(g, mundo.ancho - 2.2, 1.6, 0.8, h - 0.5, PALETA.azulTecno, 0.3);
  panelMuroFondo(g, mundo.ancho - 2.25, 0.09, 0.8, h - 0.5, PALETA.vidrioBrillo, 0.75);
  panelMuroFondo(g, mundo.ancho - 0.65, 0.09, 0.8, h - 0.5, PALETA.vidrioBrillo, 0.75);

  //  Las esquinas opacas: sin ellas el vidrio se desvanece y la torre pierde
  //  el canto, que es justo lo que la hace legible a lo lejos.
  caja(g, -0.42, -0.42, 0, 0.42, mundo.fondo + 0.42, h, PALETA.hormigonClaro);
  caja(g, mundo.ancho, -0.42, 0, 0.42, 0.42, h, PALETA.hormigonClaro);

  nodo.addChild(g);
  return nodo;
}

/* ════════════════════════════════════════════════════════════════════════════
   La puerta del módulo
   ════════════════════════════════════════════════════════════════════════════ */

/**
 * Construye una pieza de arquitectura.
 *
 * Devuelve `null` para un tipo que no conoce, igual que el mobiliario: una
 * pieza desconocida no puede tirar la escena entera, y el contador de la
 * cabecera es el que delata que algo no se dibujó.
 */
export function construirPieza(pieza: PiezaDeArquitectura): Container | null {
  switch (pieza?.tipo) {
    case 'basamento':
      return construirBasamento(pieza);
    case 'fachada':
      return construirFachada(pieza);
    case 'extremo':
      return construirExtremo(pieza);
    case 'cubierta':
      return construirCubierta(pieza);
    case 'remate':
      return construirRemate(pieza);
    default:
      return null;
  }
}
