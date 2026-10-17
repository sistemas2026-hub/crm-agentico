/**
 * LA LOGICA DE LA BURBUJA DEL SUPERVISOR, SIN SVELTE Y SIN RED
 * =============================================================
 *
 * Esta separado del componente a proposito: lo que decide --que sesion es,
 * que mensaje es un duplicado, como se lee un hilo que vino del motor-- se
 * puede probar sin montar un componente ni levantar un servidor. Un panel
 * que "se ve bien" no dice nada sobre si recupera la conversacion correcta.
 */

/**
 * El prefijo que separa la conversacion del Supervisor de la del asistente
 * general.
 *
 * POR QUE NO SE REUSA `user.id` A SECAS
 * -------------------------------------
 * `/api/asistente` ya manda `identificador_sesion: locals.user.id`, y el
 * motor guarda por (organizacion, canal, usuario_externo). Si esta burbuja
 * mandara lo mismo, las dos pantallas escribirian en EL MISMO hilo: una
 * pregunta sobre una factura hecha en el asistente general aparecria dentro
 * del chat del Supervisor, y al reves. Son dos conversaciones distintas del
 * mismo usuario y necesitan dos claves distintas.
 *
 * El tenant NO entra en la clave: el aislamiento por empresa ya lo da el
 * motor, que resuelve `organization_id` del tenant y filtra por el. Meterlo
 * aca seria un segundo mecanismo para lo mismo, y dos mecanismos para un
 * aislamiento es como terminan los huecos.
 */
export const PREFIJO_SESION = 'snoc:';

/**
 * La clave de conversacion de esta persona en el Supervisor.
 *
 * Devuelve '' si no hay usuario: quien llama tiene que tratar eso como "no
 * hay sesion", nunca inventar una. Una clave vacia o por defecto haria que
 * dos personas distintas compartieran hilo.
 *
 * @param {{ id?: string | number } | null | undefined} usuario
 * @returns {string}
 */
export function claveDeSesion(usuario) {
  const id = usuario?.id;
  if (id === undefined || id === null || id === '') return '';
  return `${PREFIJO_SESION}${id}`;
}

/**
 * Pasa el hilo que devuelve el motor a lo que pinta la burbuja.
 *
 * El motor habla en los roles de OpenAI ('user' / 'assistant'); la pantalla
 * habla de quien escribio. La traduccion vive aca y no en el marcado para
 * que se pueda afirmar sobre ella.
 *
 * Se descarta lo que no sea de esos dos roles --'system', 'tool'-- porque no
 * se le escribio a nadie: son andamiaje del turno. Mostrarlos confundiria
 * una nota interna con un mensaje.
 *
 * @param {Array<{id?: string, rol?: string, contenido?: string, creado_en?: string|null}>} mensajes
 * @returns {Array<{id: string, rol: 'usuario'|'supervisor', texto: string, cuando: string|null}>}
 */
export function aBurbujas(mensajes) {
  if (!Array.isArray(mensajes)) return [];
  const salida = [];
  for (const m of mensajes) {
    const rol = m?.rol === 'user' ? 'usuario' : m?.rol === 'assistant' ? 'supervisor' : null;
    if (!rol) continue;
    const texto = (m?.contenido ?? '').trim();
    //  Un turno puede quedar con la respuesta vacia (una escalada, una pausa).
    //  Pintar una burbuja en blanco parece un error de la pantalla.
    if (!texto) continue;
    salida.push({
      id: String(m.id ?? `${rol}-${salida.length}`),
      rol,
      texto,
      cuando: m?.creado_en ?? null
    });
  }
  return salida;
}

/**
 * Si este texto es el mismo que ya se esta enviando o se acaba de enviar.
 *
 * EL DUPLICADO QUE IMPORTA NO ES EL DEL USUARIO
 * ----------------------------------------------
 * Una persona puede preguntar dos veces lo mismo a proposito, y eso es
 * legitimo. Lo que esto evita es el doble envio ACCIDENTAL: Enter dos veces,
 * un clic repetido mientras la primera peticion todavia no volvio. Por eso
 * mira solo el ULTIMO mensaje del usuario y solo mientras hay un envio en
 * curso -- pasado eso, repetir es una decision suya.
 *
 * @param {string} texto
 * @param {Array<{rol: string, texto: string}>} burbujas
 * @param {boolean} enviando
 * @returns {boolean}
 */
export function esDuplicado(texto, burbujas, enviando) {
  if (!enviando) return false;
  const limpio = (texto ?? '').trim();
  if (!limpio) return true;
  for (let i = burbujas.length - 1; i >= 0; i--) {
    if (burbujas[i].rol === 'usuario') return burbujas[i].texto === limpio;
  }
  return false;
}

/**
 * El bloque de estado operativo que viaja con la pregunta.
 *
 * POR QUE EXISTE, Y QUE NO ES
 * ---------------------------
 * Quien responde es Dexter, que sabe de WispHub y SmartOLT por su catalogo
 * de herramientas pero NO ve el estado del Supervisor: sus propuestas, sus
 * indicadores. Sin esto, preguntarle "¿que deberia revisar primero?" dentro
 * del Supervisor devolveria una respuesta generica, porque la pregunta llega
 * sin lo unico que esta pantalla sabe.
 *
 * NO es un prompt ni una persona. Son CIFRAS que ya estan en la pantalla,
 * escritas en texto plano. No se le dice al modelo como contestar: se le da
 * lo que le falta. Si manana el Supervisor tiene su propio agente en la
 * configuracion del tenant, esto se reemplaza por ese rol y el bloque sobra.
 *
 * Sin datos devuelve '' -- antes mandaba un encabezado con ceros, que le
 * afirma al modelo que no hay nada pendiente cuando lo que pasa es que no se
 * pudo leer. Un dato ausente y un cero son cosas distintas.
 *
 * @param {{abiertas?: number, criticas?: number, indicadores?: Record<string, any>} | null} estado
 * @returns {string}
 */
export function bloqueDeContexto(estado) {
  if (!estado) return '';
  const lineas = [];
  if (typeof estado.abiertas === 'number') {
    lineas.push(`- propuestas del Supervisor sin revisar: ${estado.abiertas}`);
  }
  if (typeof estado.criticas === 'number') {
    lineas.push(`- de esas, de prioridad alta: ${estado.criticas}`);
  }
  for (const [clave, valor] of Object.entries(estado.indicadores ?? {})) {
    if (typeof valor === 'number' || typeof valor === 'string') {
      lineas.push(`- ${clave}: ${valor}`);
    }
  }
  if (!lineas.length) return '';
  return [
    '[Estado del Supervisor NOC en este momento, leido del CRM]',
    ...lineas,
    '[Fin del estado. Lo de abajo lo escribio el responsable de operaciones.]'
  ].join('\n');
}

/**
 * Arma lo que se le manda al motor: contexto y pregunta, en ese orden.
 *
 * Sin contexto manda la pregunta tal cual, sin envoltorio. Un encabezado
 * vacio es ruido que el modelo igual tiene que leer.
 *
 * @param {string} pregunta
 * @param {string} contexto
 * @returns {string}
 */
export function mensajeParaElMotor(pregunta, contexto) {
  const limpia = (pregunta ?? '').trim();
  return contexto ? `${contexto}\n\n${limpia}` : limpia;
}
