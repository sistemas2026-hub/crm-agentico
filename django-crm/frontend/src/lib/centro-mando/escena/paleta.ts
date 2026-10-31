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

/*  EL GIRO DEL 31/10/2026: DENTRO SUBE, FUERA BAJA.
 *
 *  Esta tabla era una gama indigo oscura de arriba abajo, y tenia su motivo
 *  escrito: un centro de operaciones de red es un sitio oscuro. Lo sigue
 *  siendo —los racks no subieron— pero la referencia arquitectonica aprobada
 *  pide otra cosa del conjunto: **oficinas encendidas vistas desde una noche
 *  azul**. Un edificio con las luces apagadas no se lee como una empresa
 *  trabajando, se lee como una maqueta.
 *
 *  Lo que NO se hizo, porque es lo que aplana: subirle el brillo a todo. Los
 *  suelos, los muros y el mobiliario suben; el fondo BAJA, y la envolvente de
 *  `arquitectura.ts` es hormigon y vidrio frio. El contraste entre esas dos
 *  familias es lo que hace que el edificio se vea iluminado.
 *
 *  CONSECUENCIA QUE HAY QUE VIGILAR: el texto de la escena va en `textoClaro`
 *  y ahora el suelo es claro. Sigue siendo legible porque TODO texto de la
 *  escena va sobre su propia placa oscura —nunca sobre el suelo a pelo—, que
 *  era ya la regla de este archivo. Si alguien pone un texto sin placa, se
 *  volvera invisible, y ese es el precio de este cambio.
 */
export const PALETA = {
  /* ── el recinto ──────────────────────────────────────────────────────── */
  /** Fondo del lienzo, más oscuro que el suelo para que el recinto flote. */
  fondo: 0x060a1a,
  /** Suelo: dos tonos que alternan, muy cerca uno del otro. Un tablero de
   *  ajedrez marcado convierte el piso en el protagonista. */
  pisoA: 0xbfb9cf,
  pisoB: 0xc9c3d8,
  /** Suelo del pasillo: un paso más claro, es lo que lo hace legible como paso
   *  y no como una franja pintada. */
  pisoPasillo: 0xdcd6e6,
  /** La línea entre baldosas. Casi igual al piso: un enrejado visible hace que
   *  la escena parezca papel milimetrado. */
  junta: 0xa8a2ba,
  /** Zócalo y oscurecimiento al pie de los muros (la sombra de contacto que
   *  hace que una pared se apoye en el piso en vez de flotar sobre él). */
  pisoProfundo: 0x3a3652,

  /* ── los muros ───────────────────────────────────────────────────────── */
  muroFondo: 0x8a84a0,
  muroLateral: 0x767090,
  muroRemate: 0xb4aec6,
  /** Banda de luz indirecta a media altura: el detalle que más aporta a que un
   *  muro plano se lea como una pared de verdad. */
  muroBanda: 0xe0c89c,

  /* ── mobiliario ──────────────────────────────────────────────────────── */
  escritorioTapa: 0x9d96b4,
  escritorioCanto: 0x7d7696,
  escritorioPata: 0x5a5474,
  sillaTela: 0x5f5a80,
  sillaBase: 0x474263,
  rackCuerpo: 0x2b2840,
  rackFrente: 0x3a3754,
  pantallaMarco: 0x15142a,
  pantallaApagada: 0x101026,
  planta: 0x2b6e46,
  plantaOscura: 0x1d4d31,
  maceta: 0x6e5443,
  metal: 0x9a95b0,

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
  auricular: 0x15142a,

  /* ── la sede: exterior de noche, interiores encendidos ───────────────────
   *
   *  ESTOS COLORES NO SIGUEN LA REGLA DE LOS DE ARRIBA, Y ES DELIBERADO.
   *
   *  Todo lo anterior es una gama índigo oscura, de un centro de operaciones
   *  visto por dentro. La referencia arquitectónica aprobada el 31/10/2026 pide
   *  otra cosa: **exterior azul de noche, interiores cálidos y encendidos**, con
   *  la estructura en tonos claros y grafito. El contraste entre los dos es lo
   *  que hace que un edificio se lea como un edificio iluminado y no como una
   *  maqueta gris.
   *
   *  Por eso no se sube el brillo de todo —eso aplana— sino que se separan dos
   *  familias: lo que está fuera baja, lo que está dentro sube. */

  /** La noche alrededor del edificio. Más azul y más profundo que `fondo`. */
  noche: 0x060a1a,
  /** El suelo urbano sobre el que se apoya la sede. */
  explanada: 0x0e1430,
  /** Hormigón visto: losas, petos, basamento. La estructura. */
  hormigon: 0x4a5068,
  hormigonClaro: 0x79819e,
  /** El canto iluminado de una losa, lo que separa un nivel del de abajo. */
  hormigonFilo: 0xa8b0c8,
  /** Vidrio de fachada: azul frío, siempre con alfa. */
  vidrio: 0x2b4a7a,
  /** El reflejo en el vidrio, y los montantes que lo dividen. */
  vidrioBrillo: 0x8fc2ff,
  montante: 0x2a3048,
  /** Luz de interior de oficina. Es el color que vuelve cálido lo de dentro. */
  luzCalida: 0xffd9a8,
  luzCalidaTenue: 0xc79a5e,
  /** Madera del revestimiento del fondo: el único material templado del
   *  exterior, y lo que impide que la fachada sea sólo vidrio y hormigón. */
  madera: 0x5d4330,
  maderaClara: 0x8a6442,
  /** El acento tecnológico: la franja del ascensor, los testigos del núcleo. */
  azulTecno: 0x3d9bff,
  azulTecnoTenue: 0x1d5a9e,
  /** Vegetación de las jardineras del basamento y las terrazas. */
  seto: 0x2f6b47,
  setoClaro: 0x55a371
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
 * EL ASPECTO DE UNA PERSONA, Y POR QUÉ NO SIGNIFICA NADA.
 *
 * Hasta acá todos los agentes eran la misma figura con la misma ropa: ocho
 * departamentos habrían sido la misma persona clonada cuarenta veces, que es lo
 * primero que se nota y lo que delata que la oficina es un fondo repetido.
 *
 * El aspecto se deriva del NOMBRE del agente con un reparto opaco. Dos cosas
 * que eso garantiza: que el mismo agente se vea igual en dos cargas seguidas
 * —si fuera azar, cambiaría de cara cada vez que alguien recarga— y que no
 * haya que guardar ni editar nada para que la sala se vea poblada.
 *
 * **El reparto es ARBITRARIO y no quiere decir nada.** No codifica rol, ni
 * antigüedad, ni nada que alguien pueda leer. Existe para que dos puestos no se
 * vean como la misma persona, y para nada más; si algún día un color tuviera
 * que significar algo, se pasaría como dato y no saldría de un hash.
 */
export const ROPA = [0x4f46e5, 0x2b6e46, 0x9a5b00, 0x3e5c8a, 0x6d3f78, 0x1f6f7a];
export const PELO = [0x2b2238, 0x4a3326, 0x1a1a22, 0x6b4a2f, 0x3d2b45];
export const PIEL = [0xd8a375, 0xa9754f, 0xeec4a0, 0x7d5338, 0xc08f63];

export interface Aspecto {
  camisa: number;
  camisaSombra: number;
  pelo: number;
  piel: number;
}

/**
 * Un entero estable a partir de un texto.
 *
 * No es criptográfico y no pretende serlo: lo único que tiene que cumplir es
 * dar siempre el mismo número para el mismo nombre, y repartir razonablemente
 * nombres parecidos — `atencion_1` y `atencion_2` no pueden caer en el mismo
 * sitio o la sala vuelve a verse clonada justo donde más se nota.
 */
function sembrar(texto: string): number {
  let h = 2166136261;
  for (let i = 0; i < texto.length; i++) {
    h ^= texto.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return Math.abs(h);
}

/**
 * El aspecto de un agente: la camisa la decide el ASIENTO, el pelo y la piel la
 * PERSONA.
 *
 * Esa división no es estética, es lo que da la garantía: dos compañeros de sala
 * ocupan asientos distintos, así que **nunca llevan la misma camisa**. Y el
 * pelo y la piel salen del nombre, así que la misma persona se ve igual en dos
 * cargas seguidas y mover a alguien de puesto no le cambia la cara.
 *
 * SE INTENTÓ CON EL NOMBRE SOLO, Y SU PROPIA PRUEBA LO CAZÓ. De cuatro puestos
 * salían tres aspectos: dos agentes sentados en la misma sala eran la misma
 * persona. Con 6 × 5 × 5 = 150 combinaciones, cuatro nombres chocan el 4% de
 * las veces — una prueba que dependiera de eso pasaría casi siempre y fallaría
 * sin motivo aparente el día que alguien renombrara un agente.
 *
 * El segundo intento —desplazar el hash del nombre por el asiento— tampoco
 * servía, y por una razón que conviene dejar escrita: desplazar DOS valores
 * distintos por cantidades distintas no los separa. La garantía solo aparece
 * cuando el canal depende únicamente del asiento.
 *
 * **El reparto es ARBITRARIO y no quiere decir nada.** No codifica rol, ni
 * antigüedad, ni nada que alguien pueda leer; existe para que dos puestos no se
 * vean como la misma persona. Si algún día un color tuviera que significar
 * algo, se pasaría como dato y no saldría de acá.
 *
 * El límite, dicho: pasados `ROPA.length` asientos las camisas se repiten. El
 * pelo y la piel siguen separándolos, pero la garantía fuerte cubre hasta seis
 * por sala.
 */
export function aspectoDe(nombre: string, asiento = 0): Aspecto {
  const texto = String(nombre ?? '');
  const camisa = ROPA[Math.max(0, Math.floor(asiento)) % ROPA.length];
  return {
    camisa,
    //  La sombra se DERIVA de la camisa y no se elige aparte: elegirlas por
    //  separado deja a alguien con el costado iluminado al revés.
    camisaSombra: tono(camisa, -0.3),
    //  Una semilla por canal. Dividir UNA semilla entre dos números
    //  correlaciona los dos: nombres cercanos caían juntos en más de un canal.
    pelo: PELO[sembrar(texto + '|pelo') % PELO.length],
    piel: PIEL[sembrar(texto + '|piel') % PIEL.length]
  };
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

/**
 * Los colores de estado con el acento de un departamento.
 *
 * **El acento tiñe la SALA, no los ESTADOS.** `alerta`, `despachar` e
 * `incognito` no se tocan: un rojo tiene que ser el mismo rojo en las ocho
 * salas, o quien mira dos pantallas aprende que el color no quiere decir nada.
 * Lo que cambia es el tono de «normal» y «trabajando», que es decoración.
 */
export function coloresConAcento(acento?: number): Record<string, number> {
  if (!acento) return COLOR_DE_ANIMACION;
  return {
    ...COLOR_DE_ANIMACION,
    reposo: acento,
    teclear: tono(acento, 0.28)
  };
}
