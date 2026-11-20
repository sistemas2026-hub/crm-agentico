/**
 * De donde vino un ticket: una conversacion de WhatsApp escalada por Dexter,
 * el sistema del ISP (WispHub), o alguien que lo cargo a mano en el CRM.
 *
 * EL CASO NO TIENE UN CAMPO DE ORIGEN (23/10/2026), asi que se deduce de lo que
 * si trae, en este orden:
 *   1. `external_ticket_id` / `provider`  -> vino del sistema del ISP.
 *   2. el nombre termina en " · #xxxx"    -> lo creo Dexter al escalar (ver
 *      nucleo/seguimiento/nombres.py, que arma "Asunto · Cliente · #id8"); o
 *      el formato viejo "WhatsApp <numero> - <id8>".
 *   3. lo demas                           -> creado a mano.
 * Es la misma regla que ya usaban la lista y el detalle por separado; vive aca
 * para que sea UNA. Cuando el caso tenga su origen guardado (tanda B), esta
 * funcion lee ese campo primero y el resto queda de respaldo.
 *
 * @param {{ name?: string, external_ticket_id?: string|null, provider?: string|null }} t
 * @returns {{ clave: 'whatsapp'|'wisphub'|'manual', etiqueta: string }}
 */
export function origenDelTicket(t) {
  if (t?.external_ticket_id || t?.provider) {
    const sistema = t.provider ? t.provider.charAt(0).toUpperCase() + t.provider.slice(1) : 'WispHub';
    return { clave: 'wisphub', etiqueta: sistema === 'Wisphub' ? 'WispHub' : sistema };
  }
  const nombre = (t?.name ?? '').trim();
  const tramos = nombre.split(' · ');
  if ((tramos.length > 1 && tramos[tramos.length - 1].startsWith('#')) || /^WhatsApp\s+\S+\s+-\s+\S+$/.test(nombre)) {
    return { clave: 'whatsapp', etiqueta: 'WhatsApp · Dexter' };
  }
  return { clave: 'manual', etiqueta: 'Creado a mano' };
}
