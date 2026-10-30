/**
 * LA FRONTERA.
 *
 * De un lado, el contrato de datos: instrucciones con su procedencia y un
 * veredicto sobre si los datos son de fiar. Del otro, cinco animaciones y un
 * puñado de números. Este archivo es el único que conoce las dos cosas.
 *
 * Lo que eso compra: `oficina.ts`, `personaje.ts` y `camara.ts` no saben de
 * dónde salen los datos ni qué significan, y `proyeccion.js` y `frescura.js` no
 * saben que existe un motor gráfico. Cambiar PixiJS por otra cosa es reescribir
 * `escena/*`, no esto; cambiar de dónde vienen los eventos es reescribir
 * aquello, no esto.
 *
 * LA REGLA QUE NO SE NEGOCIA
 * **No saber gana siempre.** Si el veredicto de frescura dice que los datos no
 * son de fiar, todos los personajes pasan a `incognito`, incluso los que
 * tuvieran una actividad vigente. Mostrar una actividad vieja como si fuera
 * actual es peor que no mostrar nada: lo segundo se nota y lo primero no.
 *
 * Esa decisión NO se vuelve a tomar acá: la toma `estadoVisible()` de
 * `frescura.js`, que ya está probada y tiene su prueba de mutación. Este archivo
 * la USA. Reimplementarla sería tener dos sitios donde cambiar la regla y uno
 * donde olvidarse.
 */

import { estadoDeAgentes } from '../proyeccion.js';
import { estadoVisible } from '../frescura.js';
import type { Animacion } from './pose';

/**
 * De tipo de instrucción a animación.
 *
 * Cinco tipos, cuatro animaciones: `expediente` y `escalada` comparten
 * `despachar` porque **son lo mismo visto desde el puesto** — algo sale de acá y
 * sigue su camino en otra parte. Inventarles dos animaciones distintas no
 * agregaría información: agregaría una diferencia que el dato no sostiene. Lo
 * que las distingue se lee en el rótulo y en la ficha, donde sí cabe.
 */
export const ANIMACION_POR_TIPO: Record<string, Animacion> = {
  consulta: 'teclear',
  accion: 'teclear',
  falla: 'alerta',
  expediente: 'despachar',
  escalada: 'despachar'
};

export interface EstadoDeAgente {
  agente: string;
  animacion: Animacion;
  /** Lo que se lee en el puesto. Sale del dato, nunca se inventa. */
  rotulo: string | null;
  /** `evento:<uuid>` · `simulado` · `ambiente`. Lo que hace auditable la escena. */
  procedencia: string;
  confiable: boolean;
  /** Clave del motivo. La redacción la pone la pantalla, no este archivo. */
  motivo: string | null;
  detalle: string | null;
  /** Hasta cuándo vale la actividad. `null` si no hay ninguna. */
  hasta: number | null;
}

export interface Visualizacion {
  estados: EstadoDeAgente[];
  /**
   * Instrucciones vigentes que ninguna animación sabe representar.
   *
   * Se CUENTAN en vez de dibujarse de cualquier manera. Pintar algo genérico
   * ante lo desconocido es exactamente cómo una pantalla empieza a afirmar
   * cosas que nadie midió; contarlas deja que la ficha lo diga.
   */
  sinRepresentacion: number;
}

/**
 * El estado visual de cada personaje.
 *
 * @param instrucciones las que devolvió `proyectar()`, vigentes o no — acá se
 *        filtran por caducidad, que es lo que hace que un personaje vuelva solo
 *        a reposo sin que nadie tenga que acordarse de apagarlo.
 * @param agentes los que tienen puesto en la escena. Un agente que no está en
 *        esta lista no se dibuja: sería un empleado que no existe.
 * @param veredicto el de `frescura()`. Si falta, se asume lo peor — no saber si
 *        los datos son de fiar es un caso de no saber.
 */
export function visualizar(
  instrucciones: any[],
  agentes: string[],
  veredicto: any,
  ahora: number = Date.now()
): Visualizacion {
  const crudos = estadoDeAgentes(instrucciones, agentes, ahora);
  let sinRepresentacion = 0;

  const estados = crudos.map((crudo: any) => {
    // `estadoVisible` espera `null` cuando no hay actividad y la instrucción
    // cuando sí. `estadoDeAgentes` ya usa el tipo 'reposo' para la ausencia.
    const actividad = crudo.tipo && crudo.tipo !== 'reposo' ? crudo : null;
    const visible = estadoVisible(actividad, veredicto);

    if (visible.estado === 'sin_informacion') {
      return {
        agente: crudo.agente,
        animacion: 'incognito' as Animacion,
        // El rótulo de la actividad NO viaja: con los datos en duda, repetir en
        // qué andaba hace media hora es afirmar que sigue en eso.
        rotulo: null,
        procedencia: visible.procedencia,
        confiable: false,
        motivo: visible.motivo ?? null,
        detalle: visible.detalle ?? null,
        hasta: null
      };
    }

    if (visible.estado === 'reposo') {
      return {
        agente: crudo.agente,
        animacion: 'reposo' as Animacion,
        rotulo: null,
        procedencia: visible.procedencia,
        confiable: true,
        motivo: visible.motivo ?? 'sin_actividad_vigente',
        detalle: null,
        hasta: null
      };
    }

    const animacion = ANIMACION_POR_TIPO[crudo.tipo];
    if (!animacion) {
      // Hay un hecho registrado y no hay forma honesta de dibujarlo. Se cuenta
      // y el personaje queda en `incognito`, que es la verdad: sabemos que pasó
      // algo y no sabemos mostrarlo. Lo que NO se hace es elegir una animación
      // cualquiera para que la escena no se quede quieta.
      sinRepresentacion++;
      return {
        agente: crudo.agente,
        animacion: 'incognito' as Animacion,
        rotulo: crudo.etiqueta ?? null,
        procedencia: crudo.procedencia,
        confiable: true,
        motivo: 'sin_representacion',
        detalle: null,
        hasta: crudo.caduca_en ?? null
      };
    }

    return {
      agente: crudo.agente,
      animacion,
      rotulo: crudo.etiqueta ?? null,
      procedencia: visible.procedencia,
      confiable: true,
      motivo: null,
      detalle: null,
      hasta: crudo.caduca_en ?? null
    };
  });

  return { estados, sinRepresentacion };
}

/**
 * ¿Esta procedencia es de un hecho real y registrado?
 *
 * La usa la escena para marcar lo simulado en pantalla y la ficha para no
 * mezclarlo con el historial. Es una sola línea y tiene nombre propio porque el
 * día que se escriba `p.startsWith('evento')` en dos sitios, uno de los dos se
 * va a quedar viejo.
 */
export function esReal(procedencia: string | null | undefined): boolean {
  return typeof procedencia === 'string' && procedencia.startsWith('evento:');
}

/** ¿Viene de un lote de demostración? */
export function esSimulado(procedencia: string | null | undefined): boolean {
  return procedencia === 'simulado';
}
