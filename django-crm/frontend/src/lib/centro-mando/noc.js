/**
 * EL NOC DEL PROTOTIPO: cuántos puestos hay y dónde.
 *
 * DÓNDE VIVE ESTO DE VERDAD, Y POR QUÉ TODAVÍA NO
 * Qué departamentos tiene una empresa, cuántos puestos tiene cada uno y quién
 * los ocupa es **configuración por empresa**, no código: la regla de esta casa
 * es que dar de alta un ISP sea una fila en una tabla y un archivo en una
 * carpeta, con cero cambios en el motor. La planta de una oficina virtual no es
 * una excepción a eso.
 *
 * Lo que hay acá es la geometría de UNA sala, que es el alcance declarado de
 * este prototipo: una oficina y un personaje para fijar la calidad visual. Lo
 * que NO está acá —y es la mitad que importa— es **quién la ocupa**: el agente
 * llega como parámetro, desde el inventario que sirve el motor. Así que el dato
 * que varía por empresa ya viaja como dato; lo que queda fijo son las
 * coordenadas de un recinto de ejemplo.
 *
 * Cuando haya un segundo departamento, esto se convierte en una plantilla
 * guardada por empresa y esta función desaparece. Está escrito para que la
 * siguiente sesión no tenga que deducirlo.
 */

/**
 * El departamento, con su identificador histórico.
 *
 * `operativo` es el identificador que ya existe en la configuración y en los
 * datos; «NOC y Redes» es cómo se llama en la organización. No se renombra el
 * identificador: lo que se gana es un rótulo bonito y lo que se pierde es la
 * continuidad de todo lo registrado con el nombre viejo.
 */
export const DEPARTAMENTO_NOC = {
  id: 'operativo',
  rotulo: 'NOC y Redes',
  direccion: 'Dirección de Operaciones'
};

/**
 * @typedef {{ nombre: string, rotulo?: string, area?: string }} AgenteDelNoc
 */

/**
 * Los puestos de la sala.
 *
 * @param {AgenteDelNoc|null} agente el que ocupa el puesto de supervisión, o
 *        `null` si el inventario no devolvió ninguno. Un puesto vacío se dibuja
 *        vacío y lo dice: inventarle un ocupante para que la escena no se vea
 *        sosa es exactamente la clase de afirmación que esta pantalla no puede
 *        permitirse.
 */
export function puestosDelNoc(agente) {
  const supervision = {
    id: 'puesto-supervision',
    agente: agente?.nombre ?? null,
    nombre: agente?.rotulo || agente?.nombre || 'Puesto de supervisión',
    area: agente ? DEPARTAMENTO_NOC.rotulo : 'sin agente asignado',
    gx: 4.8,
    gy: 7.4,
    principal: true
  };

  // Tres estaciones de monitoreo en fila, de cara al mural. Están vacías y es
  // la verdad: hoy existe un solo agente ejecutable con puesto propio en esta
  // área. Dibujar tres ocupantes más haría una escena más vistosa y una
  // pantalla que miente sobre la plantilla.
  const estaciones = [
    { id: 'puesto-monitoreo-1', gx: 1.5, gy: 3.4 },
    { id: 'puesto-monitoreo-2', gx: 4.5, gy: 3.4 },
    { id: 'puesto-monitoreo-3', gx: 7.5, gy: 3.4 }
  ].map((p, i) => ({
    ...p,
    agente: null,
    nombre: `Monitoreo ${i + 1}`,
    area: 'puesto libre'
  }));

  return [supervision, ...estaciones];
}

/**
 * Normaliza un rótulo de área para compararlo.
 *
 * Hace falta porque **hay dos vocabularios de área y no coinciden**: la
 * configuración declara cinco identificadores (`operativo`, `soporte_tecnico`,
 * …) y el campo `area` de cada rol es texto libre con seis rótulos distintos. Lo
 * encontró el inventario de la Fase 0 y sigue abierto: la oficina virtual
 * agruparía por un vocabulario y el CRM por el otro.
 *
 * Lo que esta función hace es comparar sin acentos, sin mayúsculas y sin
 * separadores, que resuelve «NOC y Redes» ↔ `noc_y_redes`. Lo que NO hace es
 * adivinar: no acepta parecidos ni sinónimos. Aceptar «operaciones» como
 * `operativo` serviría hoy y el día que una empresa tenga las dos cosas
 * sentaría al agente equivocado en el puesto, sin un error que lo explique.
 */
function normalizar(texto) {
  return String(texto ?? '')
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

/**
 * Elige, del inventario del motor, el agente que ocupa el puesto de supervisión.
 *
 * Busca por área y no por nombre: el nombre del agente lo pone cada empresa en
 * su configuración y puede ser cualquiera, mientras el área es un vocabulario
 * acotado. Buscar `supervisor_noc` literal funcionaría hoy con Rapilink y
 * dejaría la sala vacía en la siguiente empresa, sin un error que lo explique.
 *
 * Devuelve `null` cuando no hay ninguno, y el puesto se dibuja vacío diciéndolo.
 * Esa es la respuesta correcta: sentar a un agente de otra área para que la sala
 * no se vea sosa es la clase de afirmación que esta pantalla no puede hacer.
 *
 * @param {any[]} agentes el inventario tal como lo sirve el motor
 */
export function supervisorDelNoc(agentes) {
  const lista = Array.isArray(agentes) ? agentes : [];
  const buscadas = new Set([normalizar(DEPARTAMENTO_NOC.id), normalizar(DEPARTAMENTO_NOC.rotulo)]);
  const delArea = lista.filter((a) => a && buscadas.has(normalizar(a.area)));
  // Si hay varios, el primero por nombre: un orden estable es lo que hace que
  // la sala se vea igual en dos cargas seguidas.
  const elegido = [...delArea].sort((a, b) => String(a.nombre).localeCompare(String(b.nombre)))[0];
  if (!elegido) return null;
  return {
    nombre: String(elegido.nombre),
    rotulo: elegido.cargo || String(elegido.nombre),
    area: DEPARTAMENTO_NOC.id
  };
}
