/**
 * Lo que debe el cliente, del lado de la pantalla (10/11/2026).
 *
 * El cálculo lo hace el motor (`GET /conversaciones/<id>/cuenta`, la misma
 * herramienta que el agente de cobro). Acá sólo se decide QUÉ SE DICE con lo
 * que llegó, en un lugar que se puede probar sin montar el panel.
 *
 * LA REGLA QUE ESTE ARCHIVO SOSTIENE
 * ----------------------------------
 * «No se pudo calcular» y «no debe nada» nunca se dibujan igual. El motor los
 * separa (`disponible: false` contra `facturas_pendientes: 0`) y la pantalla
 * no puede juntarlos: un «al día» que en realidad era un sistema caído es
 * justo el error que el «saldo» de la ficha cometía (07/11/2026: saldo 0,00
 * con una factura pendiente y el servicio suspendido).
 */

/**
 * @typedef {{ tipo: 'consultando' }
 *   | { tipo: 'nada' }
 *   | { tipo: 'sin_identificar' }
 *   | { tipo: 'no_se_pudo', detalle: string | null }
 *   | { tipo: 'al_dia' }
 *   | { tipo: 'debe', pendientes: number, monto: string, vencidas: number,
 *       masAntigua: string | null, incluyeSaldo: boolean, parcial: boolean,
 *       link: string | null, otrosMedios: string[] }} ResumenDeCuenta
 */

/**
 * @param {any} cuenta  lo que contestó la ruta; `undefined` mientras viaja
 * @returns {ResumenDeCuenta}
 */
export function resumenDeCuenta(cuenta) {
  if (cuenta === undefined) return { tipo: 'consultando' };
  if (!cuenta || typeof cuenta !== 'object') return { tipo: 'nada' };

  if (cuenta.disponible === true) {
    const pendientes = Number(cuenta.facturas_pendientes);
    if (!Number.isFinite(pendientes)) return { tipo: 'no_se_pudo', detalle: null };
    if (pendientes === 0) return { tipo: 'al_dia' };
    return {
      tipo: 'debe',
      pendientes,
      monto: String(cuenta.monto_pendiente ?? ''),
      // Sólo viene cuando hay (el motor no manda un «0 vencidas»).
      vencidas: Number(cuenta.facturas_vencidas) || 0,
      masAntigua: cuenta.vencimiento_mas_antiguo ?? null,
      incluyeSaldo: cuenta.incluye_saldo_anterior === true,
      // El proveedor tenía más páginas: el total es de lo que se pudo leer.
      parcial: cuenta.completo === false,
      link: typeof cuenta.link_de_pago === 'string' ? cuenta.link_de_pago : null,
      otrosMedios: Array.isArray(cuenta.otros_medios_de_pago)
        ? cuenta.otros_medios_de_pago.filter((/** @type {any} */ m) => typeof m === 'string')
        : []
    };
  }

  switch (cuenta.motivo) {
    // La empresa no tiene configurado el cálculo: no hay nada que decir, y
    // decir «no se pudo» todos los días sería una alarma que se aprende a
    // ignorar.
    case 'sin_herramienta':
      return { tipo: 'nada' };
    case 'sin_identificar':
      return { tipo: 'sin_identificar' };
    default:
      return {
        tipo: 'no_se_pudo',
        detalle: cuenta.motivo === 'no_calculable' && typeof cuenta.detalle === 'string'
          ? cuenta.detalle
          : null
      };
  }
}
