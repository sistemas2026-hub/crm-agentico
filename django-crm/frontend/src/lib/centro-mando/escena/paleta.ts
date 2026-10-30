/**
 * LOS COLORES DE LA ESCENA.
 *
 * Salen de la paleta «Fibra» del producto (`lib/v2/styles/v2.css`) y no de un
 * gusto: el índigo de la tinta, el índigo de la acción, el óxido del error, el
 * musgo de lo que está bien, la arcilla de lo que está por vencer. La escena es
 * oscura porque un centro de operaciones de red lo es —las pantallas son la luz
 * del sitio— pero los acentos son los mismos que el resto del CRM, así que un
 * rojo acá significa lo mismo que un rojo en la cola de casos.
 *
 * ESTÁN EN NÚMERO, NO EN `var(--token)`
 * PixiJS necesita un entero. Resolver variables CSS en tiempo de dibujo
 * obligaría a leer el `computedStyle` en cada fotograma, y además el lienzo no
 * hereda el tema: es su propio mundo. Lo que se pierde es seguir el modo oscuro
 * del CRM automáticamente; lo que se gana es que la escena se vea igual en los
 * dos, que para un recinto oscuro es lo correcto.
 *
 * EL CONTRASTE SE MIDE, TAMBIÉN ACÁ
 * El texto de la escena (el nombre del puesto, el rótulo de la actividad) va en
 * `textoClaro` sobre `pisoProfundo` o sobre su propia placa, y no sobre el suelo
 * a pelo: la lección de los tonos neón del primer tablero —3.68 de contraste
 * donde hacían falta 4.5— se pagó una vez.
 */

export const PALETA = {
  /* ── el recinto ──────────────────────────────────────────────────────── */
  /** Fondo del lienzo, más oscuro que el suelo para que el recinto flote. */
  fondo: 0x0b0a1c,
  /** Suelo: dos tonos que alternan, muy cerca uno del otro. Un tablero de
   *  ajedrez marcado convierte el piso en el protagonista. */
  pisoA: 0x1b1a33,
  pisoB: 0x1f1e3a,
  /** Suelo del pasillo: un paso más claro, es lo que lo hace legible como paso
   *  y no como una franja pintada. */
  pisoPasillo: 0x272645,
  /** La línea entre baldosas. Casi igual al piso: un enrejado visible hace que
   *  la escena parezca papel milimetrado. */
  junta: 0x16152b,
  /** Zócalo y oscurecimiento al pie de los muros (la sombra de contacto que
   *  hace que una pared se apoye en el piso en vez de flotar sobre él). */
  pisoProfundo: 0x121124,

  /* ── los muros ───────────────────────────────────────────────────────── */
  muroFondo: 0x232245,
  muroLateral: 0x1c1b38,
  muroRemate: 0x343358,
  /** Banda de luz indirecta a media altura: el detalle que más aporta a que un
   *  muro plano se lea como una pared de verdad. */
  muroBanda: 0x3a3870,

  /* ── mobiliario ──────────────────────────────────────────────────────── */
  escritorioTapa: 0x3b3a5e,
  escritorioCanto: 0x2a2947,
  escritorioPata: 0x1e1d36,
  sillaTela: 0x2f2e52,
  sillaBase: 0x191830,
  rackCuerpo: 0x1a192f,
  rackFrente: 0x24233f,
  pantallaMarco: 0x15142a,
  pantallaApagada: 0x101026,
  planta: 0x2b6e46,
  plantaOscura: 0x1d4d31,
  maceta: 0x4a3a2e,
  metal: 0x4d4c6e,

  /* ── luz y estado ────────────────────────────────────────────────────── */
  /** Acción: el índigo del producto. Es la luz «todo normal» de las pantallas. */
  ember: 0x4f46e5,
  emberClaro: 0x8b84f5,
  /** Error. */
  rust: 0xb42318,
  rustClaro: 0xff7b6b,
  /** Está bien, resuelto. */
  moss: 0x2b6e46,
  mossClaro: 0x7bcb8a,
  /** Por vencer, atención. */
  clay: 0x9a5b00,
  clayClaro: 0xe0a653,
  /** Lo que no sabemos. Gris, deliberadamente sin color: el no saber no es una
   *  alarma y no puede competir con el rojo del error. */
  incognito: 0x6b6a85,

  /* ── texto ───────────────────────────────────────────────────────────── */
  textoClaro: 0xe8e7f5,
  textoTenue: 0x9a98bd,
  placa: 0x100f22,

  /* ── el personaje ────────────────────────────────────────────────────── */
  piel: 0xd8a375,
  pelo: 0x2b2238,
  camisa: 0x4f46e5,
  camisaSombra: 0x3730a3,
  pantalon: 0x272644,
  auricular: 0x15142a
} as const;

/**
 * Oscurece o aclara un color entero. `k` negativo oscurece.
 *
 * La escena necesita una cara iluminada y otra en sombra de cada volumen, y
 * declarar los dos tonos a mano para cada pieza lleva a que una quede con la
 * luz al revés. Derivarla garantiza que todas reciban la luz del mismo lado.
 */
export function tono(color: number, k: number): number {
  const r = (color >> 16) & 0xff;
  const g = (color >> 8) & 0xff;
  const b = color & 0xff;
  const ajustar = (c: number) =>
    Math.max(0, Math.min(255, Math.round(k >= 0 ? c + (255 - c) * k : c * (1 + k))));
  return (ajustar(r) << 16) | (ajustar(g) << 8) | ajustar(b);
}

/** Mezcla dos colores. `k` de 0 (el primero) a 1 (el segundo). */
export function mezclarColor(a: number, b: number, k: number): number {
  const f = Math.min(1, Math.max(0, k));
  const canal = (desp: number) => {
    const ca = (a >> desp) & 0xff;
    const cb = (b >> desp) & 0xff;
    return Math.round(ca + (cb - ca) * f) & 0xff;
  };
  return (canal(16) << 16) | (canal(8) << 8) | canal(0);
}

/**
 * El color de un estado visual.
 *
 * Centralizado para que el halo del puesto, el borde de la placa y el punto de
 * la ficha no puedan discrepar: tres sitios que dicen el estado con colores
 * distintos es peor que no decirlo.
 */
export const COLOR_DE_ANIMACION: Record<string, number> = {
  reposo: PALETA.ember,
  teclear: PALETA.emberClaro,
  alerta: PALETA.rustClaro,
  despachar: PALETA.clayClaro,
  incognito: PALETA.incognito
};
