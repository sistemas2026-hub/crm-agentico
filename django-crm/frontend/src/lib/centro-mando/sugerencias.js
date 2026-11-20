/**
 * PROPONER QUIÉN SE SIENTA. NO DECIDIRLO.
 *
 * Este archivo existe por una tensión real y vieja de la oficina virtual:
 * sentar a los agentes AUTOMÁTICAMENTE dibujaba empleados que no existen, y
 * sentarlos UNO A UNO obliga a quien organiza la empresa a repetir a mano algo
 * que el sistema ya sabe.
 *
 * La salida de esa tensión no es elegir un extremo: es separar el GESTO del
 * DATO. El sistema propone —de una vez, para todo el departamento— y una
 * persona confirma apretando Guardar. Lo que queda escrito en la configuración
 * sigue siendo una declaración explícita, exactamente igual que si se hubiera
 * tipeado silla por silla. Nada de acá escribe nada: devuelve una propuesta.
 *
 * LAS TRES COSAS QUE NO PROPONE, Y POR QUÉ CADA UNA
 *
 *   · UNA CAPACIDAD NO SE SIENTA. `soporte`, `facturacion` y `administracion`
 *     no son empleados virtuales: son capacidades que se le asignan a una
 *     persona real del CRM. Sentarlas es justo el error que dibujaba nueve
 *     empleados donde hay seis, y el que hizo falta eliminar la deducción
 *     automática el 30/10/2026. Si el departamento las declara en
 *     `capacidades`, quedan fuera de la propuesta.
 *
 *   · NADIE SE SIENTA DOS VECES. El esquema del motor rechaza un agente
 *     sentado en dos sitios, así que proponerlo produciría un error al guardar
 *     que nadie podría explicar —el otro puesto puede estar en otro piso—. Se
 *     filtra acá, antes, y se dice.
 *
 *   · NO PISA LO QUE ALGUIEN ELIGIÓ. Un puesto que ya tiene agente se respeta.
 *     Una propuesta que sobreescribe deja de ser una propuesta.
 *
 * Y LO QUE SOBRA SE DICE. Si pertenecen cinco al departamento y hay tres
 * sillas, los dos que quedan afuera se devuelven por nombre. Callarlos haría
 * que la propuesta pareciera completa cuando no lo es, y quien organiza la
 * empresa tiene que poder enterarse de que necesita una sala más grande.
 */
import { normalizar } from './departamentos.js';

/**
 * @typedef {{ areas?: string[], capacidades?: string[],
 *             ocupaciones?: {puesto: string, agente?: string}[] }} Departamento
 * @typedef {{ nombre: string, cargo?: string|null, area?: string|null }} Agente
 * @typedef {{ id: string }} Puesto
 */

/**
 * Qué ocupaciones propondría el sistema para este departamento.
 *
 * @param {Departamento} dep lo que el formulario tiene en pantalla
 * @param {Agente[]} agentes el inventario que sirve el motor
 * @param {Puesto[]} puestos los puestos de la plantilla elegida, en su orden
 * @param {string[]} [sentadosEnOtras] agentes ya sentados en OTROS
 *   departamentos. El llamador los conoce; este módulo no ve la empresa entera.
 * @returns {{ ocupaciones: {puesto: string, agente: string}[],
 *             sentados: string[], sinSilla: string[], ocupadoEnOtra: string[] }}
 */
export function sugerirOcupantes(dep, agentes, puestos, sentadosEnOtras = []) {
  const areas = new Set((dep?.areas ?? []).map(normalizar));
  const capacidades = new Set((dep?.capacidades ?? []).map(String));
  const enOtras = new Set((sentadosEnOtras ?? []).map(String));

  //  Lo que ya está declarado, por puesto. Un `agente` vacío es un puesto
  //  libre: el formulario escribe cadena vacía cuando alguien elige «ninguno».
  const porPuesto = new Map(
    (dep?.ocupaciones ?? [])
      .filter((o) => o && o.puesto)
      .map((o) => [String(o.puesto), { ...o }])
  );
  //  UNA SILLA CON UNA PERSONA NO ESTÁ LIBRE. Mirar sólo `agente` la daba por
  //  vacía y la propuesta sentaba un agente encima de alguien del equipo: el
  //  documento resultante declara las dos cosas en el mismo puesto y el motor
  //  lo rechaza, así que el síntoma habría sido un error al guardar que no
  //  nombra la silla que lo causó.
  const libre = (id) => {
    const o = porPuesto.get(id);
    return !o || (!o.agente && !o.persona);
  };
  const yaSentadosAcá = new Set(
    [...porPuesto.values()].map((o) => o.agente).filter(Boolean)
  );

  const pertenecen = (Array.isArray(agentes) ? agentes : [])
    .filter((a) => a && a.nombre && areas.has(normalizar(a.area)))
    .filter((a) => !capacidades.has(String(a.nombre)))
    //  Mismo orden que `agentesDe`: la propuesta tiene que salir igual en dos
    //  cargas seguidas, o cada «sugerir» sentaría a gente distinta.
    .sort((a, b) => String(a.cargo || a.nombre).localeCompare(String(b.cargo || b.nombre)));

  const ocupadoEnOtra = pertenecen
    .filter((a) => enOtras.has(String(a.nombre)))
    .map((a) => String(a.nombre));

  const candidatos = pertenecen
    .map((a) => String(a.nombre))
    .filter((n) => !enOtras.has(n) && !yaSentadosAcá.has(n));

  const libres = (Array.isArray(puestos) ? puestos : [])
    .map((p) => String(p?.id ?? ''))
    .filter((id) => id && libre(id));

  const sentados = [];
  for (const id of libres) {
    const quien = candidatos.shift();
    if (!quien) break;
    porPuesto.set(id, { puesto: id, agente: quien });
    sentados.push(quien);
  }

  return {
    //  Se devuelve la lista ENTERA, no sólo lo agregado: es la que el
    //  formulario va a mandar, y armarla a medias es como se perdió un agente
    //  de verdad el 31/10/2026.
    //  Se devuelven ENTERAS y tal como venían: una ocupación de persona
    //  conserva su `persona`, y una de agente su `agente`. Reconstruirlas a
    //  mano fue como se perdió un agente de verdad el 31/10/2026.
    ocupaciones: [...porPuesto.values()].filter((o) => o.agente || o.persona),
    sentados,
    sinSilla: candidatos,
    ocupadoEnOtra
  };
}

/**
 * Todos los agentes sentados en la empresa menos los de un departamento.
 *
 * Lo necesita `sugerirOcupantes` para no proponer a alguien que ya tiene silla
 * en otro piso. Se excluye el propio departamento porque sus ocupaciones ya
 * viajan dentro de `dep` y contarlas dos veces las volvería inamovibles.
 *
 * @param {Departamento[]} departamentos
 * @param {number} exceptoIndice
 */
export function sentadosEnOtrosDepartamentos(departamentos, exceptoIndice) {
  const salida = [];
  (Array.isArray(departamentos) ? departamentos : []).forEach((d, i) => {
    if (i === exceptoIndice) return;
    for (const o of d?.ocupaciones ?? []) {
      if (o && o.agente) salida.push(String(o.agente));
    }
  });
  return salida;
}
