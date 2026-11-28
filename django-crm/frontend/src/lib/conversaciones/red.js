/**
 * Lo que se le hizo al equipo del cliente, contado en palabras (fase 1.8).
 *
 * La distinción que este archivo existe para sostener, y que es la más fácil
 * de arruinar en una pantalla:
 *
 *   ACCION_CONFIRMADA   el equipo hizo lo que se le pidió
 *   ≠
 *   el cliente tiene internet
 *
 * Confirmada significa que la acción produjo el efecto técnico que el sistema
 * PUEDE medir — en `reiniciar_ont`, que el equipo reinició y volvió. Que la
 * casa tenga servicio no lo dice ningún endpoint: lo sabe el cliente, y hay
 * que preguntárselo. Una UI que muestre «✓ Resuelto» ahí le está diciendo al
 * operador que puede cerrar el caso.
 *
 * Y la otra, que el motor ya separa y la pantalla no debe volver a juntar:
 *
 *   NO_VERIFICABLE ≠ ACCION_NO_CONFIRMADA
 *
 * La primera es «no se pudo medir» (el instrumento no respondió); la segunda
 * es «se midió y el efecto no está». Tratarlas igual convierte un fallo del
 * instrumento en un fallo del equipo del cliente.
 */

const ESTADOS = {
  ACCION_CONFIRMADA: {
    clave: 'confirmada',
    tono: 'ok',
    texto: 'El equipo hizo lo que se le pidió',
    // Deliberadamente explícito: es la lectura que se malinterpreta sola.
    matiz: 'No dice si el cliente ya tiene servicio: eso hay que preguntárselo.'
  },
  ACCION_NO_CONFIRMADA: {
    clave: 'no_confirmada',
    tono: 'mal',
    texto: 'Se midió y el efecto esperado no está',
    matiz: null
  },
  NO_VERIFICABLE: {
    clave: 'no_verificable',
    tono: 'aviso',
    // No es un fallo del equipo: es que no se pudo medir.
    texto: 'No se pudo comprobar: el instrumento no respondió',
    matiz: 'No significa que la acción haya fallado.'
  },
  VERIFICACION_PENDIENTE: {
    clave: 'pendiente',
    tono: 'neutro',
    texto: 'Esperando para comprobar',
    matiz: null
  }
};

const DESCONOCIDO = {
  clave: 'sin_registro',
  tono: 'neutro',
  texto: 'Estado no registrado',
  matiz: null
};

/** Nombres de herramienta en castellano. Una que no esté se muestra igual. */
const HERRAMIENTAS = {
  reiniciar_ont: 'Reinicio de la ONT',
  reiniciar_onu: 'Reinicio de la ONU'
};

export function nombreDeAccion(herramienta) {
  const h = (herramienta ?? '').toString();
  return HERRAMIENTAS[h] ?? (h ? h.replaceAll('_', ' ') : 'Acción sin nombre');
}

export function estadoDeAccion(a) {
  return ESTADOS[a?.estado] ?? DESCONOCIDO;
}

/**
 * Una acción, lista para dibujar.
 * `porQue` lo escribe Dexter (nunca la respuesta del sistema externo).
 */
export function lineaDeAccion(a) {
  const e = estadoDeAccion(a);
  return {
    nombre: nombreDeAccion(a?.herramienta),
    ...e,
    porQue: (a?.por_que ?? '').trim() || null,
    cuando: a?.ejecutada_en ?? null,
    // Sólo cuando aporta: «intento 2 de 3» explica una espera; «1 de 1» no.
    intentos:
      a?.intentos > 1 && a?.max_intentos > 1
        ? `intento ${a.intentos} de ${a.max_intentos}`
        : null
  };
}
