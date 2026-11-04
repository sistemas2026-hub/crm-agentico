/**
 * Separar rótulos que se pisan, en espacio de PANTALLA.
 *
 * Los rótulos no participan del zoom —ese es su motivo de existir: un texto de
 * 13 px a escala 0,2 mide 2,6 y no se lee—, pero sus anclas sí. Al alejarse
 * para ver el edificio entero, once anclas que en el mundo están a cuatro
 * celdas una de otra caen a doce píxeles de distancia y los nombres se montan.
 *
 * Dos nombres montados no son un defecto estético: en la captura del
 * 31/10/2026 «Dirección» tapaba «Operaciones de Campo» y el segundo dejaba de
 * decir lo que dice. Por eso esto vive en código y no en un ajuste de posición
 * a ojo: la distancia entre dos anclas depende de la cámara, así que no hay
 * una colocación fija que sirva para todas las escalas.
 */

export interface CajaDeRotulo {
  /** Borde izquierdo de la placa, en píxeles de pantalla. */
  x: number;
  /** CENTRO vertical de la placa: es a lo que está anclado el texto. */
  y: number;
  ancho: number;
  alto: number;
}

/** ¿Las dos placas comparten alguna columna de pantalla? */
function seCruzanEnX(a: CajaDeRotulo, b: CajaDeRotulo): boolean {
  return a.x < b.x + b.ancho && b.x < a.x + a.ancho;
}

/**
 * Devuelve el centro vertical que le toca a cada caja, en el MISMO orden en
 * que entraron, de forma que ninguna se cruce con otra.
 *
 * Se empuja hacia ABAJO y nunca hacia arriba, a propósito: la banda del
 * edificio cae hacia abajo y a la derecha, así que bajar un nombre lo mantiene
 * del lado de su propia sala. Subirlo lo acercaría a la sala de encima, que es
 * exactamente el error que se está corrigiendo.
 *
 * Es determinista —mismo orden de entrada, mismo resultado— porque el desempate
 * es el índice: sin eso, dos rótulos a la misma altura intercambiarían lugar
 * entre fotograma y fotograma y la pantalla temblaría.
 */
export function separarRotulos(cajas: CajaDeRotulo[], holgura = 2): number[] {
  const ys = cajas.map((c) => c.y);
  const orden = cajas
    .map((_, i) => i)
    .sort((a, b) => cajas[a].y - cajas[b].y || a - b);

  const yaPuestos: number[] = [];
  for (const i of orden) {
    const caja = cajas[i];
    let y = caja.y;
    //  Se repite hasta despejar: bajar para esquivar una placa puede meter la
    //  caja debajo de otra que antes no la tocaba.
    for (let vuelta = 0; vuelta < cajas.length; vuelta++) {
      let movida = false;
      for (const j of yaPuestos) {
        const otra = cajas[j];
        if (!seCruzanEnX(caja, otra)) continue;
        const piso = ys[j] + otra.alto / 2 + holgura + caja.alto / 2;
        if (y < piso) {
          y = piso;
          movida = true;
        }
      }
      if (!movida) break;
    }
    ys[i] = y;
    yaPuestos.push(i);
  }
  return ys;
}

/**
 * DÓNDE ANCLAR EL NOMBRE DE UNA SALA PARA QUE NO LO TAPE UNA PLACA DE PUESTO.
 *
 * `separarRotulos` resuelve que dos NOMBRES DE SALA no se monten, y eso hace
 * bien. Lo que no mira —ni puede, porque no las recibe— son las placas que
 * cuelgan sobre cada escritorio, que viven en el mundo y se dibujan aparte.
 *
 * Medido sobre la sede del piloto: **6 de los 11 nombres de sala** caían
 * encima de una placa de puesto. «Agente de Soporte Técnico» sobre
 * «Operaciones de Campo», «Recepcionista Virtual» sobre «Atención al Cliente».
 * Y mi propia prueba de solapes decía cero, porque comparaba nombres de sala
 * contra nombres de sala: medí el par que se me ocurrió y no el que estaba
 * roto.
 *
 * La solución es correr el ancla a lo largo del frente de la sala, que es
 * suelo libre, hasta el punto más lejano de cualquier puesto. No se mueve el
 * puesto ni se achica el nombre: se busca el hueco que ya existe.
 *
 * Se trabaja en PANTALLA y no en celdas porque en isometría dos puntos
 * separados en el mundo pueden caer juntos: `(gx+1, gy+1)` queda a cero
 * píxeles en horizontal de `(gx, gy)`.
 *
 * @param ancho el ancho de la sala, en celdas
 * @param fondo su fondo
 * @param puestos los escritorios, en celdas locales de la sala
 * @returns el desplazamiento `gx` desde la esquina, en celdas
 */
export function anclaDelNombre(
  ancho: number,
  fondo: number,
  puestos: { gx?: number; gy?: number }[],
  //  A QUE PROFUNDIDAD SE ANCLA, en celdas de la propia sala.
  //
  //  Por omision 0,6 POR DELANTE del frente, que es como nacio y como se
  //  sigue usando fuera de la sede. En la sede de una planta no sirve: ese
  //  punto cae ya en la franja de circulacion, y justo ahi empieza la PUERTA
  //  de la sala siguiente -su vano arranca a 0,6 de su propio origen-. Medido
  //  el 04/11/2026 en el navegador: cuatro letreros tapaban un 28% del vano
  //  del vecino, uno detras de otro por toda la columna.
  gyAncla = fondo + 0.6
): number {
  //  El frente de la sala, muestreado. Diez puntos alcanzan: la placa mide
  //  unos 120 px y el frente entero de una sala de 13 celdas mide 416.
  const CANDIDATOS = 10;

  //  La placa de un puesto cuelga por encima del escritorio.
  const GZ_PLACA = 2.6;

  const aPantallaX = (gx: number, gy: number) => (gx - gy) * 32;
  const aPantallaY = (gx: number, gy: number, gz = 0) => (gx + gy) * 16 - gz * 26;

  const placas = (puestos ?? []).map((p) => ({
    x: aPantallaX(p.gx ?? 0, p.gy ?? 0),
    y: aPantallaY(p.gx ?? 0, p.gy ?? 0, GZ_PLACA)
  }));
  if (placas.length === 0) return 0.4;

  let mejor = 0.4;
  let mejorHolgura = -Infinity;
  for (let i = 0; i < CANDIDATOS; i++) {
    //  Entre 0,4 y el ancho menos un margen: pegado al borde derecho el
    //  nombre se sale de su propia sala.
    const gx = 0.4 + (i / (CANDIDATOS - 1)) * Math.max(0, ancho - 2.8);
    const x = aPantallaX(gx, gyAncla);
    const y = aPantallaY(gx, gyAncla);
    //  La holgura de este candidato es la distancia a la placa MÁS CERCANA.
    //  Se pondera la vertical porque una placa justo encima o justo debajo
    //  tapa, y una al lado a la misma altura no.
    let holgura = Infinity;
    for (const p of placas) {
      holgura = Math.min(holgura, Math.hypot((x - p.x) * 0.55, y - p.y));
    }
    if (holgura > mejorHolgura) {
      mejorHolgura = holgura;
      mejor = gx;
    }
  }
  return Number(mejor.toFixed(2));
}
