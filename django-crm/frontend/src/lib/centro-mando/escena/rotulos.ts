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
