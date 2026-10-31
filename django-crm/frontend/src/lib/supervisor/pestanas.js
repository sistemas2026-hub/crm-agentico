/**
 * Las pestañas de Supervisor NOC, en UN solo lugar (28/10/2026).
 *
 * Estaban copiadas a mano en cada pantalla y ya no coincidían: unas tenían
 * «Ajustes», otras no tenían «Plantillas». El orden sigue el flujo del día: lo
 * que hay que revisar, las cuadrillas, lo que falta despachar, lo que quedó
 * publicado, y la configuración. Programación va después de Despacho a pedido
 * del usuario: Despacho es lo que falta, Programación lo que quedó.
 */
export const PESTANAS_NOC = [
  { id: 'pendientes', href: '/supervisor-noc', texto: 'Pendientes por revisión' },
  { id: 'cuadrillas', href: '/supervisor-noc/cuadrillas', texto: 'Cuadrillas' },
  { id: 'despacho', href: '/supervisor-noc/despacho', texto: 'Despacho' },
  { id: 'programacion', href: '/supervisor-noc/programacion', texto: 'Programación' },
  { id: 'plantillas', href: '/supervisor-noc/plantillas', texto: 'Plantillas' },
  { id: 'ajustes', href: '/supervisor-noc/ajustes', texto: 'Ajustes' }
];
