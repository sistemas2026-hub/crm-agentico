/**
 * Los efectos externos de una conversación, contados en palabras (B4).
 *
 * Escalar produce dos cosas afuera: un caso en el CRM y, cuando corresponde, un
 * ticket en el sistema del ISP. Este panel dice cuáles quedaron sin hacer.
 *
 * La distinción que sostiene, y que viene del gate Q2:
 *
 *   fallida_definitiva   se intentó, no se pudo, y no va a poder solo
 *   desconocida          el pedido PUDO haber llegado. Nadie sabe si se hizo,
 *                        y NO se va a reintentar: reintentar un ticket que
 *                        quizá ya existe manda dos visitas técnicas al mismo
 *                        cliente
 *
 * Las dos esperan a una persona, pero por motivos opuestos, y mostrarlas igual
 * borraría justamente el motivo por el que una no se reintenta.
 */

const TIPOS = {
  crear_caso: 'Crear el caso en el CRM',
  crear_ticket: 'Crear el ticket de la operación',
  cerrar_caso: 'Cerrar el caso en el CRM',
  cerrar_ticket: 'Cerrar el ticket de la operación'
};

const ESTADOS = {
  pendiente: {
    clave: 'pendiente',
    tono: 'neutro',
    texto: 'En cola, se reintenta solo',
    revisar: false
  },
  en_curso: {
    clave: 'en_curso',
    tono: 'neutro',
    texto: 'Intentándolo ahora',
    revisar: false
  },
  hecha: {
    clave: 'hecha',
    tono: 'ok',
    texto: 'Hecho',
    revisar: false
  },
  fallida_definitiva: {
    clave: 'fallida',
    tono: 'mal',
    texto: 'No se pudo, y ya no se reintenta',
    revisar: true
  },
  desconocida: {
    clave: 'desconocida',
    tono: 'aviso',
    // Deliberadamente no dice «falló»: pudo haberse hecho.
    texto: 'No sabemos si llegó a hacerse',
    detalle:
      'No se reintenta solo: si ya se hizo, repetirlo duplicaría el trabajo. ' +
      'Hay que comprobarlo a mano.',
    revisar: true
  }
};

const DESCONOCIDO = { clave: 'sin_registro', tono: 'neutro', texto: 'Estado no registrado', revisar: false };

export function nombreDeEfecto(tipo) {
  const t = (tipo ?? '').toString();
  return TIPOS[t] ?? (t ? t.replaceAll('_', ' ') : 'Efecto sin nombre');
}

export function estadoDeSincronizacion(s) {
  return ESTADOS[s?.estado] ?? DESCONOCIDO;
}

/** Una línea lista para dibujar. */
export function lineaDeSincronizacion(s) {
  const e = estadoDeSincronizacion(s);
  return {
    nombre: nombreDeEfecto(s?.tipo),
    ...e,
    detalle: e.detalle ?? null,
    // Sólo cuando aporta: «intento 3 de 4» explica una espera; el primero no.
    intentos: s?.intentos > 1 ? `intento ${s.intentos}` : null,
    cuando: s?.actualizado_en ?? s?.creado_en ?? null
  };
}

/**
 * Lo que una persona tiene que mirar.
 *
 * Lo ya hecho no se muestra: el panel dice qué FALTA. Si todo salió bien, no
 * hay panel — y eso es información, no un hueco.
 */
export function loQueEsperaRevision(sincronizaciones = []) {
  return sincronizaciones.filter((s) => s?.estado !== 'hecha');
}

/** Si algo de esto necesita intervención humana, para destacar el panel. */
export function hayQueRevisar(sincronizaciones = []) {
  return sincronizaciones.some((s) => estadoDeSincronizacion(s).revisar);
}
