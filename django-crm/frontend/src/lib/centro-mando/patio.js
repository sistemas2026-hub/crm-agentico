/**
 * EL PATIO, AMUEBLADO: lo que hace que el centro sea un patio y no un hueco.
 *
 * Reducir el suelo vacío fue la mitad del arreglo —`anillo.js` lo bajó de 644
 * a 180— y la otra mitad es esta: **un rectángulo de suelo liso en el medio de
 * la empresa se lee como un descampado por grande o chico que sea**. Lo que lo
 * convierte en patio no es el tamaño, es que tenga para qué estar.
 *
 * TRES FRANJAS, Y NINGUNA EN EL MEDIO
 * -----------------------------------
 * Todo el mobiliario va contra los dos bordes largos y en la franja de la
 * entrada. El centro queda libre, y no por estética: **por ahí caminan las
 * figuras de ambiente**. `ambiente.js` las mantiene a 1,2 de los bordes de la
 * circulación, así que un banco a 0,9 del borde queda por fuera de donde ellas
 * pisan. Si el mobiliario invadiera el centro, se verían atravesando un banco
 * —y arreglar eso del otro lado exigiría darle al caminante un mapa de
 * obstáculos, que es el sistema de navegación que todavía no se construyó—.
 *
 * QUÉ LLEVA Y POR QUÉ ESO
 * -----------------------
 * - **Mostrador en la entrada**, mirando hacia afuera: es lo primero que se ve
 *   al entrar, y hoy la recepción de la empresa del piloto queda enterrada
 *   dentro de una manzana. Esto NO la reemplaza —la recepción es una sala
 *   declarada y sigue donde la pone el reparto— sino que marca el acceso.
 * - **Bancos y maceteros** alternados contra los bordes: el punto de descanso.
 * - **Un dispensador** cerca de la entrada: el punto de café.
 * - **Una mesa** a media profundidad: el punto de encuentro.
 * - **Luminarias** por el eje: van en el techo, así que no estorban a nadie.
 *
 * Todo sale del TAMAÑO del patio, nunca de cuántos agentes o departamentos
 * tiene la empresa. Un patio dice algo del edificio; si dijera algo de la
 * operación estaría afirmando con adornos lo que ninguna herramienta midió.
 */

/** Cada cuánto se repite una pieza a lo largo de un borde. */
export const PASO = 5.5;

/** A qué distancia del borde se apoya el mobiliario. */
export const ORILLA = 0.9;

/**
 * Lo que las figuras de ambiente dejan libre en cada borde.
 *
 * Es el mismo número que `ambiente.puntoEn` usa como margen. Está acá otra vez
 * a propósito y con esta nota: son dos módulos que no se importan entre sí, y
 * la prueba de este archivo comprueba que el mobiliario cae **fuera** de la
 * banda por donde ellas caminan. Si alguien cambia uno, la guarda cae.
 */
export const MARGEN_DE_PASO = 1.2;

/** Un patio por debajo de esto no se amuebla: no entra nada sin estorbar. */
export const MINIMO = { ancho: 8, fondo: 8 };

/**
 * El mobiliario de un patio, en coordenadas locales de su losa.
 *
 * @param {{ancho: number, fondo: number}} patio
 * @returns {{tipo: string, gx: number, gy: number, largo?: number}[]}
 */
export function mobiliarioDePatio(patio) {
  const ancho = Number(patio?.ancho) || 0;
  const fondo = Number(patio?.fondo) || 0;
  if (ancho < MINIMO.ancho || fondo < MINIMO.fondo) return [];

  const izquierda = ORILLA;
  const derecha = Number((ancho - ORILLA).toFixed(2));
  const redondo = (v) => Number(v.toFixed(2));

  //  LOS DOS PUNTOS CON NOMBRE VAN PRIMERO, y los bordes se acomodan a ellos.
  //
  //  Al revés —bordes primero y estos encima— la mesa caía sobre un banco: lo
  //  cazó la guarda de este archivo en un patio de 20 × 28, a 1,13 de
  //  distancia. Quien manda es la pieza que tiene una razón de estar en ese
  //  sitio exacto; los bancos se pueden correr.
  const fijas = [
    //  EL PUNTO DE ENCUENTRO, a media profundidad. Contra el borde y no en el
    //  centro del patio, que sería lo natural y es justo lo que no se puede:
    //  por el centro cruzan las figuras.
    { tipo: 'mesa', gx: izquierda, gy: redondo(fondo / 2) },
    //  EL PUNTO DE CAFÉ, del lado de la entrada, que es por donde se llega.
    { tipo: 'dispensador', gx: derecha, gy: redondo(Math.max(1, fondo - 1.6)) }
  ];

  //  Los dos bordes largos, alternando banco y macetero. Se arranca a medio
  //  paso del fondo para no apoyar nada contra la esquina, donde se cruzan los
  //  dos bordes y dos piezas quedarían encimadas.
  const bordes = [];
  let turno = 0;
  for (let gy = PASO / 2; gy <= fondo - PASO / 2; gy += PASO) {
    const tipo = turno % 2 === 0 ? 'banco' : 'planta';
    bordes.push({ tipo, gx: izquierda, gy: redondo(gy) });
    bordes.push({ tipo: turno % 2 === 0 ? 'planta' : 'banco', gx: derecha, gy: redondo(gy) });
    turno += 1;
  }

  const piezas = [
    ...fijas,
    ...bordes.filter((b) => !fijas.some(
      (f) => Math.hypot(f.gx - b.gx, f.gy - b.gy) < PASO / 2))
  ];

  //  Las luminarias van en el TECHO: son las únicas que pueden ir por el eje
  //  sin que nadie las atraviese caminando.
  for (let gy = PASO; gy < fondo; gy += PASO * 1.6) {
    piezas.push({ tipo: 'luminaria', gx: Number((ancho / 2).toFixed(2)), gy: Number(gy.toFixed(2)) });
  }

  return piezas;
}

/**
 * El mobiliario de la franja de entrada: el mostrador que marca el acceso.
 *
 * Va contra el borde de ADENTRO —el que da al patio— y no contra el frente: en
 * esta isometría el frente queda entre la cámara y la oficina, así que una
 * pieza apoyada ahí tapa lo que viene detrás. Es la misma razón por la que la
 * sede no lleva muro frontal.
 *
 * @param {{ancho: number, fondo: number}} entrada
 */
export function mobiliarioDeEntrada(entrada) {
  const ancho = Number(entrada?.ancho) || 0;
  const fondo = Number(entrada?.fondo) || 0;
  if (ancho < MINIMO.ancho || fondo < 3) return [];

  const largo = Math.max(2, Math.min(4, Math.round(ancho * 0.3)));
  return [
    { tipo: 'mostrador', gx: Number((ancho / 2).toFixed(2)), gy: ORILLA, largo },
    { tipo: 'planta', gx: ORILLA, gy: Number((fondo - ORILLA).toFixed(2)) },
    { tipo: 'planta', gx: Number((ancho - ORILLA).toFixed(2)), gy: Number((fondo - ORILLA).toFixed(2)) }
  ];
}
