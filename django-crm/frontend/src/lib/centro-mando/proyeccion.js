/**
 * EL PROYECTOR: de eventos reales a instrucciones visuales.
 *
 * Es el puente entre lo que el motor registró y lo que la oficina dibuja. No
 * sabe qué es PixiJS, ni un sprite, ni un escritorio: produce un contrato de
 * datos que cualquier escena puede consumir, y por eso se puede cambiar el
 * motor gráfico sin tocar una línea de acá.
 *
 * LA REGLA QUE GOBIERNA TODO ESTE ARCHIVO
 * ---------------------------------------
 * **Una llamada terminada no prueba que el agente siga trabajando.**
 * `tool_calls` se escribe cuando la llamada TERMINA, con su duración: no
 * existe la fila «en vuelo». El motor ya se niega por eso a emitir el estado
 * `waiting_tool` — «una herramienta lenta y una recién terminada se ven
 * igual».
 *
 * Así que un evento produce una animación BREVE Y ACOTADA que representa
 * *algo que pasó*, nunca un estado permanente que afirme *algo que sigue
 * pasando*. Toda instrucción caduca.
 *
 * LAS TRES CATEGORÍAS, Y POR QUÉ NO SE MEZCLAN
 *
 *   evento      algo que ocurrió y está registrado   -> procedencia evento:<uuid>
 *   ambiental   relleno visual, no significa nada    -> procedencia 'ambiente'
 *   desconocido no se sabe                           -> NO se proyecta
 *
 * Lo tercero es lo que más cuesta respetar: ante un evento raro la tentación
 * es dibujar algo genérico. Eso es inventar actividad. Si no se entiende, no
 * se proyecta, y `descartados` lo cuenta para que la pantalla pueda decirlo.
 */

/** Cuánto dura en pantalla cada tipo, cuando el evento no dice su duración. */
const DURACION = {
  consulta: 900,
  accion: 1300,
  falla: 1600,
  expediente: 2200,
  escalada: 1800
};

/** Techo absoluto. Una herramienta que tardó 40 s no deja al personaje 40 s
 *  moviéndose: la animación cuenta QUE pasó, no cuánto duró. */
const DURACION_MAXIMA = 2500;
const DURACION_MINIMA = 600;

/**
 * Instrucciones visuales para un lote de eventos.
 *
 * @param {any[]} eventos   los del flujo incremental, ya aislados por empresa
 * @param {{agentes?: string[], areas?: string[], ahora?: number}} ctx
 *        `agentes` son los que EXISTEN como instancia ejecutable y tienen
 *        personaje. Un evento de un rol que no está acá no se proyecta: sería
 *        dibujar un empleado que no existe como proceso.
 */
export function proyectar(eventos, ctx = {}) {
  const conPersonaje = new Set(ctx.agentes || []);
  const areasValidas = new Set(ctx.areas || []);
  const ahora = ctx.ahora ?? Date.now();

  const instrucciones = [];
  const vistos = new Set();
  const descartados = { sin_evento: 0, agente_desconocido: 0, tipo_desconocido: 0, repetido: 0 };

  for (const ev of eventos || []) {
    // 1 · SIN IDENTIDAD NO HAY INSTRUCCIÓN. El id del evento es lo que hace
    //     verificable la animación: sin él no se puede rastrear hasta el
    //     hecho que la causó, y entonces es decoración disfrazada de dato.
    if (!ev || !ev.id) { descartados.sin_evento++; continue; }

    // 2 · DUPLICADOS. El flujo puede entregar el mismo evento dos veces —es
    //     el precio de no perder ninguno en la transición foto→cursor— y
    //     animarlo dos veces contaría una actividad que ocurrió una.
    if (vistos.has(ev.id)) { descartados.repetido++; continue; }
    vistos.add(ev.id);

    // 3 · EL AGENTE TIENE QUE EXISTIR como instancia ejecutable. El rol por sí
    //     solo no basta: `soporte`, `facturacion` y `administracion` son
    //     CAPACIDADES asignadas a personas, no empleados virtuales, y pintarles
    //     un escritorio sería inventar tres empleados.
    const agente = typeof ev.agente === 'string' ? ev.agente : null;
    if (!agente || (conPersonaje.size > 0 && !conPersonaje.has(agente))) {
      descartados.agente_desconocido++;
      continue;
    }

    const forma = formaDe(ev, areasValidas);
    if (!forma) { descartados.tipo_desconocido++; continue; }

    const duracion = Math.max(
      DURACION_MINIMA,
      Math.min(forma.duracion ?? DURACION[forma.tipo] ?? 900, DURACION_MAXIMA)
    );

    instrucciones.push({
      // Identidad y procedencia: lo que hace auditable cada animación.
      id: ev.id,
      procedencia: `evento:${ev.id}`,
      agente,
      tipo: forma.tipo,
      // Referencia temporal: cuándo PASÓ, no cuándo se dibuja.
      en: ev.en ?? null,
      // Y hasta cuándo se muestra. Nada queda indefinido.
      duracion_ms: duracion,
      caduca_en: ahora + duracion,
      // Qué se lee en pantalla. Nunca un dato de cliente: el nombre de una
      // herramienta y el de un área son del catálogo de la empresa.
      etiqueta: forma.etiqueta,
      ...(forma.destino ? { destino: forma.destino } : {})
    });
  }

  return { instrucciones, descartados };
}

/**
 * Qué forma visual le toca a un evento, o `null` si no se entiende.
 *
 * Devolver `null` es una decisión, no un olvido: un tipo que esta versión no
 * conoce NO se dibuja. Pintar algo genérico ante lo desconocido es exactamente
 * cómo una pantalla empieza a afirmar cosas que nadie midió.
 */
function formaDe(ev, areasValidas) {
  // La DERIVACIÓN es la única que viaja entre departamentos, y se representa
  // como un expediente que se mueve — no como el personaje abandonando su
  // escritorio. Si los agentes caminaran en cada transferencia, la oficina
  // sería gente yendo y viniendo todo el día.
  const area = ev?.datos?.area;
  if (area) {
    // Un área que la empresa no tiene configurada NO se dibuja. El destino
    // sale del evento real; inventarlo sería mostrar una ruta que no existe.
    if (areasValidas.size > 0 && !areasValidas.has(area)) return null;
    return { tipo: 'expediente', destino: area, etiqueta: `→ ${area}` };
  }

  switch (ev.tipo) {
    case 'consulta':
      return { tipo: 'consulta', etiqueta: ev.herramienta || 'consulta',
               duracion: ev.duracion_ms };
    case 'accion':
      return { tipo: 'accion', etiqueta: ev.herramienta || 'acción',
               duracion: ev.duracion_ms };
    case 'herramienta_fallida':
      return { tipo: 'falla', etiqueta: ev.herramienta || 'error',
               duracion: ev.duracion_ms };
    case 'escalada':
      // Lo único que de verdad SALE de la oficina: el caso pasa a una persona.
      return { tipo: 'escalada', etiqueta: 'a una persona' };
    default:
      return null;
  }
}

/**
 * Las instrucciones que siguen vigentes en un instante dado.
 *
 * Existe para que ningún estado quede indefinido: el personaje vuelve a reposo
 * solo, sin que nadie tenga que acordarse de apagarlo. Si esta función no
 * existiera, un agente que consultó una vez se quedaría «consultando» para
 * siempre — que es justo la mentira que este módulo evita.
 */
export function vigentes(instrucciones, ahora = Date.now()) {
  return (instrucciones || []).filter((i) => i && i.caduca_en > ahora);
}

/**
 * El estado visible de cada agente: lo que está haciendo, o reposo.
 *
 * Reposo NO es «no hace nada»: es «no hay ningún evento que respalde una
 * actividad». La diferencia importa cuando alguien pregunta por qué un
 * personaje está quieto.
 */
export function estadoDeAgentes(instrucciones, agentes, ahora = Date.now()) {
  const vivos = vigentes(instrucciones, ahora);
  const porAgente = new Map();
  for (const i of vivos) {
    // La más reciente gana: si llegaron dos, se muestra la última.
    const previa = porAgente.get(i.agente);
    if (!previa || i.caduca_en >= previa.caduca_en) porAgente.set(i.agente, i);
  }
  return (agentes || []).map((a) => {
    const act = porAgente.get(a);
    return act
      ? { agente: a, tipo: act.tipo, etiqueta: act.etiqueta,
          procedencia: act.procedencia, caduca_en: act.caduca_en }
      // Procedencia 'ambiente': el reposo no es una actividad operativa y
      // NUNCA puede aparecer en el historial como si lo fuera.
      : { agente: a, tipo: 'reposo', etiqueta: null, procedencia: 'ambiente' };
  });
}
