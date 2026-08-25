/**
 * Turning a DRF rejection back into a sentence.
 *
 * The API answers a bad save with `{"error": true, "errors": {"field":
 * ["message"]}}`, and `apiRequest` flattens that into an Error whose message
 * carries the JSON. Showing "Request failed" over the top of it throws away the
 * one useful thing in the response: the API already said exactly what was wrong
 * with which field.
 *
 * This lived twice in the accounts routes and was about to live twice more in
 * contacts. Two copies of a function is how the backend ended up with five
 * different opinions about who may open a record.
 */

/**
 * @param {any} err the error thrown by `apiRequest`
 * @param {string} fallback what to say when the response explained nothing
 * @returns {string} a message worth putting in front of somebody
 */
export function readableError(err, fallback) {
  const message = String(err?.message ?? '');
  const start = message.indexOf('{');
  if (start === -1) return message || fallback;
  try {
    const parsed = JSON.parse(message.slice(start));
    const errors = parsed.errors ?? parsed;
    if (typeof errors === 'string') return errors;
    // Se BAJA hasta el mensaje, no se lee el primer nivel y ya.
    //
    // Algunas respuestas anidan dos veces: crear una persona contesta
    // {errors: {user_errors: {email: ["..."]}}}, y quedarse en el primer par
    // dejaba 'detail' como objeto -- String() sobre eso imprime
    // "[object Object]" y el motivo real, que la API ya dijo, se pierde justo
    // cuando alguien lo necesita. Visto el 25/08/2026 al dar de alta a un
    // colaborador: la pantalla decia "user_errors: [object Object]".
    const bajar = (nodo, camino) => {
      if (nodo === null || nodo === undefined) return null;
      if (typeof nodo === 'string') return { camino, texto: nodo };
      if (Array.isArray(nodo)) return nodo.length ? bajar(nodo[0], camino) : null;
      if (typeof nodo === 'object') {
        const par = Object.entries(nodo)[0];
        if (!par) return null;
        const [clave, valor] = par;
        // Los envoltorios ('user_errors', 'profile_errors') no le dicen nada
        // a quien lee: lo util es el campo y el motivo.
        const nuevo = clave.endsWith('_errors') || clave === 'non_field_errors' ? camino : clave;
        return bajar(valor, nuevo);
      }
      return { camino, texto: String(nodo) };
    };

    const hallado = bajar(errors, '');
    if (!hallado) return fallback;
    return hallado.camino ? `${hallado.camino}: ${hallado.texto}` : String(hallado.texto);
  } catch {
    return message;
  }
}
