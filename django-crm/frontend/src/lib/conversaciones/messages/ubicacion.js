/**
 * La ubicación que compartió el cliente, leída del texto que guarda el motor
 * (11/11/2026).
 *
 * El motor escribe «[El cliente compartio su ubicacion: … · coordenadas LAT,
 * LNG]» (nucleo/canales/whatsapp.py::texto_de_ubicacion): el modelo lo lee
 * así, y acá se reconoce ese mismo formato para ofrecer el mapa. Se exige el
 * prefijo entero y no solo «coordenadas»: un cliente que escribe «mis
 * coordenadas son…» no es una ubicación compartida, y un enlace armado con lo
 * que alguien tipeó sería un enlace que nadie verificó.
 */
const PATRON =
  /^\[El cliente compartio su ubicacion: (?:.* · )?coordenadas (-?\d{1,2}(?:\.\d+)?), (-?\d{1,3}(?:\.\d+)?)\]$/;

/**
 * @param {string | null | undefined} contenido
 * @returns {{ lat: number, lng: number, mapa: string } | null}
 */
export function ubicacionCompartida(contenido) {
  const m = PATRON.exec((contenido ?? '').trim());
  if (!m) return null;
  const lat = Number(m[1]);
  const lng = Number(m[2]);
  if (!Number.isFinite(lat) || !Number.isFinite(lng) || Math.abs(lat) > 90 || Math.abs(lng) > 180) {
    return null;
  }
  return { lat, lng, mapa: `https://www.google.com/maps?q=${lat},${lng}` };
}
