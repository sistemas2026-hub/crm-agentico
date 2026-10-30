/**
 * LA POSE DE UN PERSONAJE, COMO NÚMEROS.
 *
 * Acá vive toda la animación y no hay un solo gráfico: una pose es un puñado de
 * desplazamientos e intensidades, y `personaje.ts` se limita a aplicarlos a las
 * piezas que dibujó. Ese corte tiene un motivo práctico — en este repositorio
 * **no hay pruebas de interacción** (jsdom no arranca, medido el 07/10/2026),
 * así que todo lo que quede del lado gráfico solo se puede verificar mirando.
 * Lo que está acá se prueba en Node, con números.
 *
 * POR QUÉ LAS TRANSICIONES NO SE PROGRAMAN UNA POR UNA
 * Cinco estados dan veinte transiciones posibles. Escribirlas a mano es
 * garantizar que cuatro o cinco queden sin hacer, y las que faltan no fallan:
 * saltan. El personaje cambia de postura de golpe, parece un error de dibujo y
 * se busca en el sitio equivocado.
 *
 * Acá no se programa ninguna. Cada estado declara su pose y la transición es
 * **interpolar entre la pose actual y la nueva**, con una constante de tiempo.
 * Veinte transiciones naturales por el precio de una, y la suavidad se mide:
 * dos poses cualesquiera, un paso, y ninguna coordenada salta.
 *
 * LA QUIETUD TAMBIÉN SE ANIMA
 * Un personaje detenido del todo se lee como una imagen pegada, no como alguien
 * sentado. El reposo respira: el torso sube y baja ~1 px y la cabeza se mueve
 * menos todavía. Es el detalle más barato que separa «escena viva» de
 * «captura».
 */

/**
 * Los cinco estados visuales, y solo cinco.
 *
 * El diseño listaba siete animaciones; cuatro de ellas —esperando, levantarse,
 * caminar, sentarse— pertenecen a un personaje que se mueve por la oficina, y
 * eso todavía no tiene un hecho medido detrás que lo justifique. Siete
 * animaciones a medias se ven peor que cinco terminadas.
 *
 *   reposo      sentado, respirando, sin nada vigente
 *   teclear     trabajando contra el equipo
 *   alerta      algo falló: se incorpora, el puesto se tiñe
 *   despachar   suelta el teclado y entrega algo que sale del puesto
 *   incognito   NO SABEMOS. No es reposo y no se le parece
 */
export type Animacion = 'reposo' | 'teclear' | 'alerta' | 'despachar' | 'incognito';

export const ANIMACIONES: Animacion[] = ['reposo', 'teclear', 'alerta', 'despachar', 'incognito'];

/**
 * Una pose: desplazamientos en píxeles de mundo, giros en radianes,
 * intensidades de 0 a 1.
 *
 * Son todos números y es a propósito: interpolar números es trivial y correcto,
 * interpolar «estados» no se puede. En cuanto una pose llevara una bandera
 * booleana, la transición volvería a saltar en ese canal.
 */
export interface Pose {
  /** Sube o baja el cuerpo. Negativo es hacia arriba. */
  torsoY: number;
  /** Inclinación hacia el equipo. Positivo se echa adelante. */
  torsoInclina: number;
  /** Altura de la cabeza, aparte del torso. */
  cabezaY: number;
  /** Giro de la cabeza. Positivo mira hacia el pasillo. */
  cabezaGiro: number;
  /** Cabeza hacia abajo (mirando la pantalla) o arriba. */
  cabezaInclina: number;
  /** Altura de cada mano. El teclear alterna las dos. */
  manoIzqY: number;
  manoDerY: number;
  /** Cuánto se extiende el brazo hacia fuera del puesto. */
  alcance: number;
  /** Brillo de las pantallas del puesto. */
  brilloPantalla: number;
  /** Intensidad del halo del estado alrededor del puesto. */
  aura: number;
  /** Cuánto se apaga el personaje. 1 = sin color. */
  apagado: number;
  /** Visibilidad del signo de interrogación sobre la cabeza. */
  incertidumbre: number;
  /** Avance del paquete que sale del puesto, de 0 a 1. */
  despacho: number;
}

export const POSE_NEUTRA: Pose = {
  torsoY: 0,
  torsoInclina: 0,
  cabezaY: 0,
  cabezaGiro: 0,
  cabezaInclina: 0,
  manoIzqY: 0,
  manoDerY: 0,
  alcance: 0,
  brilloPantalla: 0.6,
  aura: 0,
  apagado: 0,
  incertidumbre: 0,
  despacho: 0
};

const CANALES = Object.keys(POSE_NEUTRA) as (keyof Pose)[];

/**
 * La pose de un estado en un instante dado. `t` en segundos, continuo.
 *
 * Las frecuencias no son redondas a propósito. Con 2 Hz y 4 Hz, la respiración
 * y el giro de cabeza se sincronizan cada medio segundo y el personaje parece
 * un mecanismo; con 1.7 y 0.43 nunca coinciden del todo y el movimiento se lee
 * como orgánico. Es el mismo truco de siempre y cuesta dos decimales.
 */
export function poseDe(animacion: Animacion, t: number): Pose {
  const respira = Math.sin(t * 1.7);
  const mira = Math.sin(t * 0.43);

  switch (animacion) {
    case 'teclear': {
      // Las manos alternan en contrafase: si subieran juntas sería un aplauso.
      const tecleo = Math.sin(t * 13);
      return {
        ...POSE_NEUTRA,
        torsoY: respira * 0.5 - 1,
        torsoInclina: 0.06,
        cabezaY: -0.5,
        cabezaGiro: mira * 0.6,
        cabezaInclina: 0.16,
        manoIzqY: tecleo * 1.6,
        manoDerY: -tecleo * 1.6,
        // El brillo late con el tecleo, apenas: una pantalla que no cambia
        // nunca delata que la escena está congelada.
        brilloPantalla: 0.92 + Math.sin(t * 7) * 0.05,
        aura: 0.55
      };
    }

    case 'alerta': {
      // Se incorpora y mira la pantalla de frente. El pulso es rápido y
      // pequeño: temblar mucho se lee como un error de dibujo, no como alarma.
      const pulso = Math.sin(t * 5.3);
      return {
        ...POSE_NEUTRA,
        torsoY: -2.5 + pulso * 0.6,
        torsoInclina: 0.12,
        cabezaY: -1.5,
        cabezaGiro: 0,
        cabezaInclina: -0.05,
        manoIzqY: -2,
        manoDerY: -3,
        alcance: 2,
        brilloPantalla: 1,
        aura: 0.85 + pulso * 0.15
      };
    }

    case 'despachar': {
      // Suelta el teclado, gira hacia el pasillo y acompaña al paquete. El
      // avance va de 0 a 1 y vuelve a 0: el paquete sale y la mano regresa.
      const ciclo = (t * 0.8) % 1;
      return {
        ...POSE_NEUTRA,
        torsoY: respira * 0.4 - 0.5,
        torsoInclina: 0.02,
        cabezaY: -0.5,
        cabezaGiro: 2.2,
        cabezaInclina: 0.02,
        manoIzqY: 0,
        manoDerY: -3.5,
        alcance: 5 + Math.sin(ciclo * Math.PI) * 3,
        brilloPantalla: 0.7,
        aura: 0.5,
        despacho: ciclo
      };
    }

    case 'incognito': {
      // Lo que se dibuja acá es una AUSENCIA, y tiene que verse como tal: el
      // personaje se apaga, las pantallas bajan a un resto de luz y aparece el
      // signo de interrogación. Si en vez de eso se quedara sentado y quieto
      // sería indistinguible del reposo, que es justo la confusión que esta
      // pantalla existe para romper.
      return {
        ...POSE_NEUTRA,
        torsoY: respira * 0.25,
        torsoInclina: 0.01,
        cabezaY: 0.5,
        cabezaGiro: mira * 0.3,
        cabezaInclina: 0.04,
        brilloPantalla: 0.1,
        aura: 0.3,
        apagado: 0.82,
        incertidumbre: 0.75 + Math.sin(t * 2.1) * 0.25
      };
    }

    case 'reposo':
    default:
      return {
        ...POSE_NEUTRA,
        torsoY: respira * 0.9,
        torsoInclina: 0.01,
        cabezaY: respira * 0.35,
        cabezaGiro: mira * 2.4,
        cabezaInclina: 0.03,
        manoIzqY: respira * 0.3,
        manoDerY: respira * 0.3,
        brilloPantalla: 0.55,
        aura: 0.12
      };
  }
}

/** Interpola dos poses. `k` de 0 (la primera) a 1 (la segunda). */
export function mezclar(a: Pose, b: Pose, k: number): Pose {
  const f = Math.min(1, Math.max(0, k));
  const salida = {} as Pose;
  for (const canal of CANALES) salida[canal] = a[canal] + (b[canal] - a[canal]) * f;
  return salida;
}

/**
 * La pose que se dibuja, suavizando hacia el estado vigente.
 *
 * `tau` es la constante de tiempo: a los ~3·tau la transición está hecha. 0.18 s
 * da un cambio que se percibe sin esperarlo, y no es un número elegido mirando
 * una sola máquina — la mezcla usa el tiempo transcurrido, así que dura lo mismo
 * a 30 que a 144 fotogramas por segundo.
 */
export class Transicion {
  private pose: Pose;
  private animacion: Animacion;
  private tau: number;

  constructor(animacion: Animacion = 'reposo', tau = 0.18) {
    this.animacion = animacion;
    this.tau = tau;
    this.pose = poseDe(animacion, 0);
  }

  /** Cambia el estado objetivo. Repetir el mismo no reinicia nada. */
  hacia(animacion: Animacion) {
    this.animacion = animacion;
  }

  /** @returns la pose a dibujar. `dt` y `t` en segundos. */
  avanzar(dt: number, t: number): Pose {
    const objetivo = poseDe(this.animacion, t);
    const k = this.tau <= 0 ? 1 : 1 - Math.exp(-Math.max(0, dt) / this.tau);
    this.pose = mezclar(this.pose, objetivo, k);
    return this.pose;
  }

  /** El estado objetivo actual. Para las pruebas y el panel. */
  get destino(): Animacion {
    return this.animacion;
  }

  /** La última pose calculada, sin avanzar el tiempo. */
  get actual(): Pose {
    return this.pose;
  }
}
