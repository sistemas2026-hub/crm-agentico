/**
 * Las pestañas de Supervisor NOC, en UN solo lugar (28/10/2026).
 *
 * Estaban copiadas a mano en cada pantalla y ya no coincidían: unas tenían
 * «Ajustes», otras no tenían «Plantillas». El orden sigue el flujo del día: lo
 * que hay que revisar, las cuadrillas, lo que falta despachar, lo que quedó
 * publicado, y la configuración. Programación va después de Despacho a pedido
 * del usuario: Despacho es lo que falta, Programación lo que quedó.
 *
 * DESDE EL 13/11/2026 SE DIBUJAN EN EL MENÚ LATERAL, no dentro de cada pantalla.
 * Pedido del usuario: al tocar «Supervisor» en el menú se despliegan sus
 * subpantallas y se pueden contraer. Antes tocar «Supervisor» abría directo
 * Pendientes —la pantalla más pesada— aunque uno fuera a Despacho. La fila de
 * píldoras de cada encabezado se quitó: dos navegaciones iguales sobraban.
 *
 *   menu     el nombre en el menú, si el de la pantalla no cabe en la barra.
 *   exacta   solo se marca activa en su ruta exacta (las demás son prefijo, y
 *            '/supervisor-noc' es prefijo de todas).
 *   incluye  otras rutas que son parte de esta subpantalla.
 *   count    la insignia del menú que le corresponde (ver lib/v2/menu.js).
 */
export const PESTANAS_NOC = [
  {
    id: 'pendientes',
    href: '/supervisor-noc',
    texto: 'Pendientes por revisión',
    menu: 'Pendientes',
    exacta: true,
    count: 'supervisor'
  },
  //  30/10/2026: las caídas de PON activas y el aviso a sus clientes.
  { id: 'fallas', href: '/supervisor-noc/fallas', texto: 'Fallas de red' },
  { id: 'cuadrillas', href: '/supervisor-noc/cuadrillas', texto: 'Cuadrillas' },
  { id: 'despacho', href: '/supervisor-noc/despacho', texto: 'Despacho' },
  //  Los planes semanales se abren desde Programación y son parte de ella.
  {
    id: 'programacion',
    href: '/supervisor-noc/programacion',
    texto: 'Programación',
    incluye: ['/supervisor-noc/planes-semanales']
  },
  { id: 'plantillas', href: '/supervisor-noc/plantillas', texto: 'Plantillas' },
  { id: 'ajustes', href: '/supervisor-noc/ajustes', texto: 'Ajustes' }
];
