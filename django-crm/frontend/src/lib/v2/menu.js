/**
 * EL ÁRBOL DEL MENÚ, SIN SVELTE  --  12/11/2026
 *
 * Vivía dentro de `Sidebar.svelte`, donde nada lo podía probar: qué entradas ve
 * cada rol, qué se relabela con la terminología de la empresa y, desde hoy,
 * qué módulos heredados sacó la empresa de su menú (`lib/v2/modulos.js`). Acá
 * es una función pura; el componente solo pone el ícono (`icono` es el nombre,
 * el mapa a componentes está en Sidebar) y dibuja.
 *
 * Grupos por TRABAJO, del más urgente al menos (22/10/2026). `role` sale del
 * JWT en el servidor y solo decide qué se MUESTRA: cada destino oculto lo sigue
 * exigiendo su backend, así que esto es experiencia, no control de acceso.
 *
 *   admin    solo ADMIN: un miembro solo llegaría para que lo rebote un aviso.
 *   roles    el conjunto exacto que deja pasar la pantalla en su servidor.
 *   termKey  la entrada que un paquete vertical puede renombrar.
 *   count    la clave de su insignia en `counts` (lo arma el layout).
 *   modulo   la clave con que la empresa la puede ocultar (common/modulos.py).
 */
import { t } from '$lib/terminology.js';
import { sinModulosOcultos } from './modulos.js';

/** El mismo conjunto que campo/permissions.py::ROLES_GESTION y que el
 *  servidor de /supervisor-noc. */
export const ROLES_GESTION = ['ADMIN', 'SUPERVISOR', 'OPERACIONES'];

/**
 * @typedef {{ href: string, label: string, icono: string, exact?: boolean,
 *             admin?: boolean, roles?: string[], termKey?: string,
 *             count?: string, modulo?: string }} Entrada
 * @typedef {{ label: string, items: Entrada[] }} Grupo
 */

/** @type {Grupo[]} */
export const GRUPOS = [
  {
    label: 'Operación en vivo',
    items: [
      { href: '/', label: 'Hoy', icono: 'Sun', exact: true },
      // Insignia: chats que piden una persona (la misma cuenta que Hoy).
      { href: '/conversaciones', label: 'Conversaciones', icono: 'MessageCircle', count: 'conversaciones' },
      // Hasta el 12/11/2026 lo veía todo rol y un USER rebotaba en un candado
      // (auditoría del menú, Supervisor NOC). Insignia: órdenes detenidas que
      // esperan al NOC.
      {
        href: '/supervisor-noc',
        label: 'Supervisor NOC IA',
        icono: 'Activity',
        roles: ROLES_GESTION,
        count: 'supervisor'
      },
      // Que hace cada agente AHORA. /agentes dice como esta configurado
      // cada uno; esto, en que anda en este momento.
      { href: '/centro-mando', label: 'Centro de mando', icono: 'Radar' },
      { href: '/asistente', label: 'Asistente', icono: 'Sparkles' }
    ]
  },
  {
    label: 'Campo',
    items: [
      // Insignia: solicitudes que esperan la decisión de factibilidad.
      { href: '/instalaciones', label: 'Instalaciones', icono: 'ClipboardCheck', count: 'instalaciones' },
      { href: '/inventario', label: 'Inventario', icono: 'Boxes' }
    ]
  },
  {
    label: 'Clientes',
    items: [
      { href: '/tickets', label: 'Tickets', icono: 'LifeBuoy', count: 'tickets' },
      { href: '/tasks', label: 'Tareas', icono: 'CircleCheck', count: 'tasks', modulo: 'tasks' },
      { href: '/accounts', label: 'Cuentas', icono: 'Building2', termKey: 'account.plural', modulo: 'accounts' },
      { href: '/contacts', label: 'Contactos', icono: 'Users', termKey: 'contact.plural', modulo: 'contacts' },
      { href: '/solutions', label: 'Base de conocimiento', icono: 'BookOpen', modulo: 'solutions' },
      { href: '/documents', label: 'Documentos', icono: 'FileText', modulo: 'documents' }
    ]
  },
  {
    label: 'Ventas',
    items: [
      // El embudo del ISP (12/11/2026): chats de venta → enlaces → enviadas →
      // aprobadas → instaladas → activas. Primero porque es el que existe para
      // un ISP; Negociaciones es la herencia del CRM.
      { href: '/ventas', label: 'Embudo', icono: 'Funnel' },
      {
        href: '/pipeline',
        label: 'Negociaciones',
        icono: 'Columns3',
        count: 'pipeline',
        termKey: 'opportunity.plural',
        modulo: 'pipeline'
      },
      { href: '/leads', label: 'Prospectos', icono: 'Target', count: 'leads', termKey: 'lead.plural' },
      { href: '/goals', label: 'Metas', icono: 'Trophy', modulo: 'goals' }
    ]
  },
  {
    label: 'Facturación',
    items: [
      {
        href: '/invoices',
        label: 'Facturas',
        icono: 'Receipt',
        count: 'invoices',
        termKey: 'invoice.plural',
        modulo: 'invoices'
      },
      { href: '/timesheet', label: 'Registro de horas', icono: 'Clock', modulo: 'timesheet' }
    ]
  },
  {
    // Lo que se ajusta de la IA: quien atiende, que sigue al pie de la
    // letra, de que ejemplos aprende, y donde se la prueba sin un cliente.
    label: 'Dexter',
    items: [
      { href: '/agentes', label: 'Agentes', icono: 'Bot' },
      { href: '/habilidades', label: 'Habilidades', icono: 'GraduationCap', admin: true },
      { href: '/manual', label: 'Manual', icono: 'BookMarked' },
      { href: '/simulador-whatsapp', label: 'Simulador WhatsApp', icono: 'Smartphone' }
    ]
  },
  {
    // Administración, aparte del trabajo.
    label: 'Administrar',
    items: [
      { href: '/team', label: 'Equipo y accesos', icono: 'UserCog', admin: true },
      { href: '/settings', label: 'Configuración', icono: 'SlidersHorizontal' },
      { href: '/conectores', label: 'Conectar sistema', icono: 'PlugZap', admin: true },
      { href: '/configuracion-guiada', label: 'Conectar API nueva', icono: 'Cable', admin: true },
      { href: '/consumo', label: 'Consumo', icono: 'Gauge', admin: true },
      { href: '/capacidad', label: 'Capacidad', icono: 'TrendingUp', admin: true }
    ]
  }
];

/**
 * Lo que dibuja el menú para esta persona en esta empresa.
 *
 * @param {{ role?: string, terminology?: Record<string, string> | null,
 *           ocultos?: unknown }} contexto
 * @returns {Grupo[]}
 */
export function gruposDelMenu({ role = 'USER', terminology = undefined, ocultos = [] } = {}) {
  const porRol = GRUPOS.map((g) => ({
    ...g,
    items: g.items
      .filter((i) => (i.admin ? role === 'ADMIN' : true))
      .filter((i) => (i.roles ? i.roles.includes(role) : true))
      .map((i) => (i.termKey ? { ...i, label: t(terminology, i.termKey, i.label) } : i))
  })).filter((g) => g.items.length > 0);
  return sinModulosOcultos(porRol, ocultos);
}
