/**
 * LOS MÓDULOS HEREDADOS QUE UNA EMPRESA PUEDE SACAR DE SU MENÚ  --  12/11/2026
 *
 * Auditoría del menú (SPEC/AUDITORIA_MENU_2026-11-12.md §1.5): un tercio del
 * menú es herencia de BottleCRM sin alimentación propia. Que se vea o no es un
 * dato de cada empresa (CLAUDE.md §3.3): vive en `Org.modulos_ocultos` del
 * backend, lo cambia su ADMIN en /settings/modulos, y viaja en la MISMA
 * respuesta de `/org/settings/` que el cascarón ya pide en cada navegación
 * (`getOrgShell`): leerlo no cuesta un viaje más.
 *
 * OCULTAR NO ES UN PERMISO. La ruta sigue existiendo con sus propias reglas; el
 * menú solo deja de dibujar la entrada. Por eso esto vive en `lib/v2` y no en
 * ningún `+page.server.js`.
 *
 * Las claves son las mismas, en el mismo orden, que `common/modulos.py`; la
 * prueba de cada lado fija las nueve.
 */

/**
 * @typedef {{ clave: string, href: string, nombre: string, para: string,
 *             dexter: 'no_usa' | 'usa', nota?: string }} Modulo
 */

/** @type {Modulo[]} */
export const MODULOS_OCULTABLES = [
  {
    clave: 'accounts',
    href: '/accounts',
    nombre: 'Cuentas',
    para: 'Fichas de empresas clientes del CRM: rubro, empleados, ingresos.',
    dexter: 'no_usa',
    nota: 'No se relacionan con el cliente de WispHub ni con WhatsApp: el motor nunca crea una.'
  },
  {
    clave: 'contacts',
    href: '/contacts',
    nombre: 'Contactos',
    para: 'Personas de contacto de esas cuentas.',
    dexter: 'no_usa',
    nota: 'El cliente que escribe por WhatsApp no queda acá: queda en Conversaciones.'
  },
  {
    clave: 'solutions',
    href: '/solutions',
    nombre: 'Base de conocimiento',
    para: 'Artículos con flujo borrador → revisado → aprobado.',
    dexter: 'no_usa',
    nota: 'Los agentes no la leen: lo que responde Dexter sale de Documentos.'
  },
  {
    clave: 'documents',
    href: '/documents',
    nombre: 'Documentos',
    para: 'Archivos de la empresa. Los marcados «usar en el asistente» alimentan las respuestas.',
    dexter: 'usa',
    nota: 'Dexter sí lo usa: ocultarlo del menú no apaga lo que ya está cargado, pero nadie va a encontrar dónde cargar uno nuevo.'
  },
  {
    clave: 'tasks',
    href: '/tasks',
    nombre: 'Tareas',
    para: 'Lista de tareas manual del equipo.',
    dexter: 'no_usa',
    nota: 'El seguimiento real está en Instalaciones, el Supervisor NOC y las órdenes de campo.'
  },
  {
    clave: 'pipeline',
    href: '/pipeline',
    nombre: 'Negociaciones',
    para: 'Embudo de ventas del CRM por etapas.',
    dexter: 'no_usa',
    nota: 'La venta de un ISP la sigue el Embudo (/ventas), que sale de las solicitudes.'
  },
  {
    clave: 'goals',
    href: '/goals',
    nombre: 'Metas',
    para: 'Objetivos sobre negociaciones ganadas.',
    dexter: 'no_usa',
    nota: 'Cuenta negociaciones del CRM: en un ISP suele quedar en cero.'
  },
  {
    clave: 'invoices',
    href: '/invoices',
    nombre: 'Facturas',
    para: 'Facturación propia del CRM.',
    dexter: 'no_usa',
    nota: 'La factura del cliente está en WispHub y el asistente la consulta allá, no acá.'
  },
  {
    clave: 'timesheet',
    href: '/timesheet',
    nombre: 'Registro de horas',
    para: 'Horas trabajadas por caso, para cobrar por hora.',
    dexter: 'no_usa',
    nota: 'Sin uso con tarifa plana.'
  }
];

const CLAVES = new Set(MODULOS_OCULTABLES.map((m) => m.clave));

/**
 * Las claves conocidas de lo que llegó del backend. Cualquier otra cosa (null,
 * un texto, una clave que este frontend no conoce) se descarta: ante la duda
 * se MUESTRA, porque esconder del menú algo que no se sabe si estaba oculto
 * deja a una persona sin camino a su pantalla, y no protege nada.
 *
 * @param {unknown} valor
 * @returns {Set<string>}
 */
export function ocultosConocidos(valor) {
  if (!Array.isArray(valor)) return new Set();
  return new Set(valor.filter((v) => typeof v === 'string' && CLAVES.has(v)));
}

/**
 * Los grupos del menú sin los módulos que esta empresa ocultó, y sin los
 * grupos que quedaron vacíos. Una entrada sin `modulo` no se puede ocultar.
 *
 * @template {{ modulo?: string }} I
 * @template {{ items: I[] }} G
 * @param {G[]} grupos
 * @param {unknown} ocultos
 * @returns {G[]}
 */
export function sinModulosOcultos(grupos, ocultos) {
  const fuera = ocultosConocidos(ocultos);
  if (!fuera.size) return grupos;
  return grupos
    .map((g) => ({ ...g, items: g.items.filter((i) => !i.modulo || !fuera.has(i.modulo)) }))
    .filter((g) => g.items.length > 0);
}
