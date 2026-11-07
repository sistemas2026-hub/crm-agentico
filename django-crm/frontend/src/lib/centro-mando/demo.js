/**
 * ACTIVIDAD DE DEMOSTRACIÓN, MARCADA COMO TAL DESDE EL ORIGEN.
 *
 * Un prototipo visual que no se mueve no se puede evaluar: hay que ver las
 * cinco animaciones, la transición entre ellas y el paquete saliendo del puesto,
 * y eso no se consigue esperando a que la operación real haga justo eso mientras
 * alguien mira. Así que se generan eventos.
 *
 * LA REGLA, Y DÓNDE ESTÁ PUESTA
 * Estos eventos **nunca** pueden contarse como trabajo real. La protección no
 * vive acá: vive en que `proyectar()` recibe el lote entero con `simulado:
 * true` y les pone procedencia `simulado`, y en que `bitacora.js` tiene dos
 * arreglos separados por procedencia. Este archivo no podría colarlos aunque
 * quisiera — ni siquiera generando identificadores con la forma correcta, que es
 * justo lo que hace: los `id` son uuid de verdad, para que la separación no
 * dependa de que el dato de prueba «se vea falso».
 *
 * EL GUION ES UN GUION, NO AZAR
 * Los eventos salen en un orden fijo y con tiempos fijos. Un generador aleatorio
 * da una demostración distinta cada vez, y entonces «no vi la animación de
 * fallo» no se puede distinguir de «la animación de fallo no funciona». Con
 * guion, lo que se ve es siempre lo mismo y una ausencia es un defecto.
 */

/** Un uuid v4. Se usa `crypto.randomUUID` cuando existe. */
function uuid() {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === 'function') return c.randomUUID();
  // Respaldo para entornos sin `crypto` (una corrida de pruebas en Node viejo).
  // Mantiene la forma: el objetivo es que la validación de identidad del
  // proyector trate a lo simulado igual que a lo real.
  const h = () => Math.floor(Math.random() * 16).toString(16);
  const s = (n) => Array.from({ length: n }, h).join('');
  return `${s(8)}-${s(4)}-4${s(3)}-${['8', '9', 'a', 'b'][Math.floor(Math.random() * 4)]}${s(3)}-${s(12)}`;
}

/**
 * El guion. Cada paso dice cuánto esperar antes de emitirlo.
 *
 * El orden recorre las cinco animaciones y termina en una pausa larga, que es la
 * que deja ver el reposo. Sin esa pausa el personaje nunca para y no se puede
 * comprobar que vuelve solo a reposo al caducar la instrucción — que es la
 * garantía de que ningún estado queda indefinido.
 */
const GUION = [
  { espera: 1.2, tipo: 'consulta', nombre: 'consultar_estado_enlace' },
  { espera: 2.4, tipo: 'consulta', nombre: 'consultar_potencia_optica' },
  { espera: 2.0, tipo: 'accion', nombre: 'reiniciar_equipo_cliente' },
  { espera: 3.0, tipo: 'herramienta_fallida', nombre: 'consultar_inventario_puertos' },
  { espera: 2.6, tipo: 'derivacion', area: 'soporte_tecnico' },
  { espera: 3.2, tipo: 'escalada' },
  { espera: 6.0, tipo: 'consulta', nombre: 'consultar_alarmas_nodo' },
  { espera: 7.5, tipo: 'pausa' }
];

/**
 * @param {{ agente: string, areaDerivacion?: string }} opciones
 */
export function crearDemostracion(opciones) {
  const agente = opciones.agente;
  const areaDerivacion = opciones.areaDerivacion || null;
  let paso = 0;
  let acumulado = 0;
  let emitidos = 0;

  return {
    /**
     * Avanza el guion. `dt` en segundos.
     *
     * @returns {any[]} los eventos que toca emitir ahora, ya con forma de
     *          evento del flujo. Casi siempre vacío.
     */
    avanzar(dt) {
      acumulado += dt;
      const salida = [];
      // Un `while` y no un `if`: con la pestaña oculta el navegador entrega un
      // salto de varios segundos de golpe, y con un `if` el guion se quedaría
      // atascado emitiendo un paso cada fotograma durante un rato.
      while (acumulado >= GUION[paso % GUION.length].espera) {
        const actual = GUION[paso % GUION.length];
        acumulado -= actual.espera;
        paso++;
        if (actual.tipo === 'pausa') continue;

        const base = { id: uuid(), agente, en: new Date().toISOString() };
        if (actual.tipo === 'derivacion') {
          // Sin un área configurada no se inventa un destino: se salta el paso.
          // Dibujar una derivación hacia un área que la empresa no tiene sería
          // mostrar una ruta que no existe.
          if (!areaDerivacion) continue;
          salida.push({ ...base, tipo: 'consulta', datos: { area: areaDerivacion } });
        } else if (actual.tipo === 'escalada') {
          salida.push({ ...base, tipo: 'escalada' });
        } else {
          salida.push({
            ...base,
            tipo: actual.tipo,
            herramienta: actual.nombre,
            duracion_ms: 1200
          });
        }
        emitidos++;
      }
      return salida;
    },

    /** Vuelve al principio del guion. */
    reiniciar() {
      paso = 0;
      acumulado = 0;
    },

    get emitidos() {
      return emitidos;
    },

    /** Cuántos pasos tiene el guion completo, para decirlo en pantalla. */
    get pasos() {
      return GUION.length;
    }
  };
}
