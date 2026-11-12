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

/*
 * EN ESPAÑOL  --  12/11/2026
 * --------------------------
 * El backend corre con LANGUAGE_CODE por defecto (inglés): los mensajes de DRF
 * y de Django llegaban tal cual a la pantalla («This field is required.»). Se
 * traducen ACÁ, en el único lugar por el que pasan los errores de formulario,
 * y no cambiando el idioma del backend: eso cambiaría también los textos de la
 * API que leen otros clientes (el motor, la app de campo) y las pruebas que los
 * afirman.
 *
 * La lista sale de lo que el backend emite DE VERDAD: los mensajes por defecto
 * de los campos y validadores de DRF/Django que usan los serializers, más los
 * propios del backend que se repiten (buscados con grep el 12/11/2026:
 * «You don't have permission to perform this action.» aparece 13 veces,
 * «Organization context required» 10, «Email already exists»…). Un mensaje
 * que no esté acá sigue pasando en inglés: no se inventa una traducción
 * genérica que esconda el motivo.
 */

/** @type {Array<[RegExp, string | ((...g: string[]) => string)]>} */
const TRADUCCIONES = [
  [/^This field is required\.?$/i, 'Este campo es obligatorio.'],
  [/^This field may not be blank\.?$/i, 'Este campo no puede quedar vacío.'],
  [/^This field may not be null\.?$/i, 'Este campo no puede quedar vacío.'],
  [/^This list may not be empty\.?$/i, 'Elegí al menos uno.'],
  [/^This field must be unique\.?$/i, 'Ya existe otro con este valor.'],
  [/^Enter a valid email address\.?$/i, 'Escribí un correo válido.'],
  [/^Enter a valid URL\.?$/i, 'Escribí una dirección web válida.'],
  [/^Enter a valid phone number\.?$/i, 'Escribí un teléfono válido.'],
  [/^A valid integer is required\.?$/i, 'Tiene que ser un número entero.'],
  [/^A valid number is required\.?$/i, 'Tiene que ser un número.'],
  [/^Must be a valid boolean\.?$/i, 'Tiene que ser sí o no.'],
  [/^Not a valid string\.?$/i, 'Tiene que ser un texto.'],
  [/^Must be a valid UUID\.?$/i, 'El identificador no es válido.'],
  [/^Ensure this field has no more than (\d+) characters\.?$/i, (n) => `Máximo ${n} caracteres.`],
  [/^Ensure this field has at least (\d+) characters\.?$/i, (n) => `Mínimo ${n} caracteres.`],
  [/^Ensure this value is less than or equal to (-?\d+(?:\.\d+)?)\.?$/i, (n) => `Tiene que ser como mucho ${n}.`],
  [/^Ensure this value is greater than or equal to (-?\d+(?:\.\d+)?)\.?$/i, (n) => `Tiene que ser al menos ${n}.`],
  [/^Ensure that there are no more than (\d+) digits in total\.?$/i, (n) => `Máximo ${n} dígitos en total.`],
  [/^Ensure that there are no more than (\d+) decimal places\.?$/i, (n) => `Máximo ${n} decimales.`],
  [/^"?(.*?)"? is not a valid choice\.?$/i, (v) => `«${v}» no es una opción válida.`],
  [/^Invalid pk "?(.*?)"? - object does not exist\.?$/i, () => 'Lo que elegiste ya no existe. Recargá la página.'],
  [/^Incorrect type\. Expected pk value, received .*$/i, () => 'Lo que elegiste no es válido. Recargá la página.'],
  [/^Date has wrong format\..*$/i, () => 'La fecha no tiene un formato válido.'],
  [/^Datetime has wrong format\..*$/i, () => 'La fecha y hora no tienen un formato válido.'],
  [/^Time has wrong format\..*$/i, () => 'La hora no tiene un formato válido.'],
  [/^Expected a list of items but got type .*$/i, () => 'Se esperaba una lista.'],
  [/^(.+) with this (.+) already exists\.?$/i, () => 'Ya existe un registro con ese valor.'],
  [/^The fields (.+) must make a unique set\.?$/i, () => 'Ya existe un registro con esa combinación.'],
  [/^You do(?:n't| not) have permission to perform this action\.?$/i, 'No tenés permiso para hacer esto.'],
  [/^You do not have permission\.?$/i, 'No tenés permiso para hacer esto.'],
  [/^You must be an organization administrator to perform this action\.?$/i, 'Solo un administrador de la organización puede hacer esto.'],
  [/^Authentication credentials were not provided\.?$/i, 'Tu sesión venció. Volvé a iniciar sesión.'],
  [/^Given token not valid for any token type$/i, 'Tu sesión venció. Volvé a iniciar sesión.'],
  [/^Not found\.?$/i, 'No se encontró.'],
  [/^No .+ matches the given query\.?$/i, 'No se encontró.'],
  [/^Organization context (?:is )?required.*$/i, 'Falta la organización de la sesión. Volvé a iniciar sesión.'],
  [/^(?:Given )?Email(?: id)? already exists\.?$/i, 'Ya hay una persona con ese correo.'],
  [/^(?:Account|Team) already exists with this name\.?$/i, 'Ya existe uno con ese nombre.'],
  [/^Name is required\.?$/i, 'Falta el nombre.']
];

/**
 * Un mensaje del backend en español, si es uno de los conocidos; si no, tal
 * cual. Traduce también dentro de «campo: mensaje; campo: mensaje», que es como
 * `apiRequest` aplana los errores por campo.
 * @param {string} texto
 * @returns {string}
 */
export function enEspanol(texto) {
  return String(texto ?? '')
    .split('; ')
    .map((parte) => {
      const corte = parte.indexOf(': ');
      const campo = corte > 0 && !/\s/.test(parte.slice(0, corte)) ? parte.slice(0, corte) : '';
      const resto = campo ? parte.slice(corte + 2) : parte;
      //  Entero primero: un mensaje puede llevar comas propias («Use one of
      //  these formats instead: YYYY-MM-DD, …»). Si no se reconoce entero, es
      //  una lista unida con ', ' (así une `apiRequest` varios del mismo campo).
      const entero = traducirUno(resto);
      const traducido =
        entero !== resto ? entero : resto.split(', ').map((m) => traducirUno(m)).join(', ');
      return campo ? `${campo}: ${traducido}` : traducido;
    })
    .join('; ');
}

/** @param {string} mensaje */
function traducirUno(mensaje) {
  const limpio = mensaje.trim();
  for (const [patron, destino] of TRADUCCIONES) {
    const m = limpio.match(patron);
    if (m) return typeof destino === 'string' ? destino : destino(...m.slice(1));
  }
  return mensaje;
}

/**
 * @param {any} err the error thrown by `apiRequest`
 * @param {string} fallback what to say when the response explained nothing
 * @returns {string} a message worth putting in front of somebody
 */
export function readableError(err, fallback) {
  return enEspanol(legible(err, fallback));
}

/**
 * @param {any} err
 * @param {string} fallback
 * @returns {string}
 */
function legible(err, fallback) {
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
