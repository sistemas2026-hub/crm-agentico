import { describe, expect, it } from 'vitest';
import { render } from 'svelte/server';

import OrdenDelDia from './OrdenDelDia.svelte';

/**
 * La tarjeta de una orden del día en Programación (29/10/2026). Pedido del
 * usuario: «añade el asunto» y «cada ticket en una tarjeta organizada, que no
 * salga la información revuelta». Se mide lo que se dibuja, con la forma que
 * devuelve `campo/dia_publicado.py`.
 */
const DIA = '2026-10-29';
const orden = {
  id: 'o-1',
  numero: 83,
  asunto: 'No Tiene Internet',
  tipo: 'Soporte',
  cliente: 'Beatriz Pinzón',
  barrio: 'VILLA ESTADIO',
  prioridad: 'alta',
  estado: 'asignada',
  estado_texto: 'Asignada',
  tecnicos: ['Jeider Amell'],
  asignada_por: 'supervisor',
  asignada_por_nombre: 'Supervisor',
  asignada_en: '2026-10-29T09:07:00-05:00',
  aviso: 'avisado',
  vence_en: '2026-10-28T23:59:59-05:00',
  orden_del_dia: 1,
  siguiente: true
};

function html(props) {
  return render(OrdenDelDia, { props: { dia: DIA, ...props } }).body;
}

describe('la tarjeta de una orden del día', () => {
  it('el asunto como título, y a quién, dónde, cuándo vence y su lugar del día', () => {
    const h = html({ orden, marca: 'Empieza por esta' });

    //  Svelte le agrega su sufijo a la clase: `od-asunto svelte-…`.
    expect(h).toMatch(/class="od-asunto[^"]*">No Tiene Internet<\/p>/);
    expect(h).toContain('Beatriz Pinzón');
    expect(h).toContain('VILLA ESTADIO');
    expect(h).toContain('OT 83');
    expect(h).toContain('Venció el 28/10');
    expect(h).toContain('class="od-lugar');
    expect(h).toContain('Supervisor · 09:07');
    expect(h).toContain('Jeider Amell');
  });

  it('la siguiente se marca, en su cabecera; las demás no', () => {
    expect(html({ orden, marca: 'Empieza por esta' })).toContain('Empieza por esta');
    expect(html({ orden, marca: 'Empieza por esta' })).toContain('od-siguiente');
    const otra = html({ orden: { ...orden, siguiente: false }, marca: 'Empieza por esta' });
    expect(otra).not.toContain('Empieza por esta');
    expect(otra).not.toContain('od-siguiente');
  });

  it('el color dice lo mismo que el texto: rojo lo vencido, ámbar lo de hoy', () => {
    expect(html({ orden })).toContain('od-vence-vencida');
    expect(html({ orden: { ...orden, vence_en: '2026-10-29T23:59:59-05:00' } })).toContain('od-vence-hoy');
    expect(html({ orden: { ...orden, prioridad: 'media' } })).toContain('od-prioridad-media');
  });

  it('sin asunto, el tipo de trabajo; sin lugar del día, sin número; lo terminado, atenuado', () => {
    const h = html({
      orden: { ...orden, asunto: '', orden_del_dia: null, estado: 'completada_campo', siguiente: false }
    });
    expect(h).toMatch(/class="od-asunto[^"]*">Soporte<\/p>/);
    expect(h).not.toContain('class="od-lugar');
    expect(h).toContain('od-terminada');
  });

  it('un aviso que no llegó se ve en rojo', () => {
    expect(html({ orden: { ...orden, aviso: 'no_llego' } })).toContain('od-aviso-mal');
    expect(html({ orden })).not.toContain('od-aviso-mal');
  });
});

describe('mover la orden a otro técnico (14/11/2026)', () => {
  const OTROS = [
    { profile: 'p-aa', nombre: 'Jeider Amell · Cuadrilla #1' },
    { profile: 'p-bb', nombre: 'Nicolás Mora · Cuadrilla #2' }
  ];

  //  LA GUARDA AFIRMA EL `value`, NO QUE LA OPCIÓN EXISTA. El selector dibuja
  //  el nombre y manda el id, y son dos cosas distintas: un `value` con el
  //  nombre adentro renderiza igual de bien y el POST vuelve 404 «No existe
  //  esa persona». Esa es la mutación que esto tiene que matar.
  it('cada opción manda el id de la persona, no su nombre', () => {
    const h = html({ orden, aQuienMover: OTROS });

    expect(h).toMatch(/<option value="p-aa"[^>]*>Jeider Amell · Cuadrilla #1<\/option>/);
    expect(h).toMatch(/<option value="p-bb"[^>]*>Nicolás Mora · Cuadrilla #2<\/option>/);
  });

  it('el formulario dice qué orden mueve, y pide el motivo', () => {
    const h = html({ orden, aQuienMover: OTROS });

    expect(h).toContain('action="?/mover"');
    expect(h).toMatch(/name="orden"[^>]*value="o-1"/);
    //  El backend acepta el motivo vacío; la pantalla no. Sin él, el evento
    //  `reasignacion` queda sin la única línea que después explica por qué
    //  un trabajo cambió de manos.
    expect(h).toMatch(/name="motivo"[^>]*required/);
  });

  //  SIN A QUIÉN MOVERLA NO HAY CONTROL. Un selector vacío es un botón que no
  //  hace nada, y en esta pantalla eso pasa seguido: un día con una sola
  //  cuadrilla de una persona.
  it('sin nadie más en el día, el control no se dibuja', () => {
    const h = html({ orden, aQuienMover: [] });

    expect(h).not.toContain('action="?/mover"');
  });

  //  NO SE MUEVE LO TERMINADO: el servidor lo rechaza, y ofrecer un botón que
  //  va a ser negado es peor que no ofrecerlo.
  it('una orden cerrada no se puede mover', () => {
    const h = html({ orden: { ...orden, estado: 'cerrada', estado_texto: 'Cerrada' },
                     aQuienMover: OTROS });

    expect(h).not.toContain('action="?/mover"');
  });

  //  NI LO YA HECHO: el trabajo lo completó alguien y espera revisión.
  //  Moverla se lo atribuye a quien no lo hizo — la revisión del cierre, la
  //  devolución al ticket y la marca de agua de las fotos nombran al
  //  responsable.
  it('una orden ya completada en campo tampoco', () => {
    const h = html({ orden: { ...orden, estado: 'completada_campo',
                              estado_texto: 'Completada en campo' },
                     aQuienMover: OTROS });

    expect(h).not.toContain('action="?/mover"');
  });

  //  EL CONTROL SALIÓ SIN DÓNDE REPORTAR (14/11/2026). La página recargaba y
  //  no decía nada: ni el éxito ni el error. Y el error estaba — el servidor
  //  rechazaba al líder del día. Ninguna de las guardas anteriores lo vio,
  //  porque todas miraban que el formulario se dibujara, no que contestara.
  it('el resultado de mover se ve en la tarjeta de esa orden', () => {
    const h = html({ orden, aQuienMover: OTROS,
                     form: { de: 'mover', orden: 'o-1', error: 'No se pudo mover.' } });

    expect(h).toContain('No se pudo mover.');
    expect(h).toContain('snoc-error-txt');
  });

  //  Y NO EN LAS OTRAS: `form` es de la página entera y hay una tarjeta por
  //  orden. Sin comparar el id, el mismo mensaje sale en las treinta.
  it('el resultado de otra orden no aparece en esta', () => {
    const h = html({ orden, aQuienMover: OTROS,
                     form: { de: 'mover', orden: 'OTRA', hecho: 'Movida.' } });

    expect(h).not.toContain('Movida.');
  });

  //  PERO UNA EN CAMINO SÍ: es el caso que pidió el control.
  it('una en camino sí se puede mover', () => {
    const h = html({ orden: { ...orden, estado: 'en_camino',
                              estado_texto: 'En camino' },
                     aQuienMover: OTROS });

    expect(h).toContain('action="?/mover"');
  });
});


/**
 * DETENIDA POR EL TÉCNICO (20/11/2026, OT #328). El técnico bloqueó la orden
 * y en esta pantalla no se veía ni se podía sacar: la barra dibuja `bloqueada`
 * en el casillero de «En sitio», y el botón que la destrababa vivía en otra
 * pantalla. Se mide lo que se dibuja, con la forma de `campo/dia_publicado.py`.
 */
describe('la tarjeta de una orden detenida', () => {
  const detenida = {
    ...orden,
    estado: 'bloqueada',
    estado_texto: 'Bloqueada',
    bloqueo: {
      quien: 'Mario Vásquez',
      desde: '14/11 14:40',
      categoria: 'acceso',
      motivo: 'No hay quien abra',
      necesita: 'Llamar al cliente'
    }
  };

  it('dice que está detenida, quién la paró, desde cuándo y por qué', () => {
    const h = html({ orden: detenida });

    expect(h).toContain('Detenida por Mario Vásquez · 14/11 14:40');
    expect(h).toContain('No hay quien abra');
    expect(h).toContain('acceso');
    expect(h).toContain('Necesita: Llamar al cliente');
  });

  it('ofrece devolverla, con la aclaración obligatoria y el id de la orden', () => {
    const h = html({ orden: detenida });

    expect(h).toContain('action="?/destrabar"');
    expect(h).toMatch(/<textarea[^>]*name="aclaracion"[^>]*required/);
    expect(h).toMatch(/<input[^>]*name="orden"[^>]*value="o-1"/);
    expect(h).toContain('Devolver al técnico');
  });

  //  LA QUE NO ESTÁ DETENIDA NO LO OFRECE: un botón que el servidor va a
  //  negar (409, sin bloqueo abierto) es peor que no tenerlo.
  it('una orden sin bloqueo no dibuja nada de esto', () => {
    const h = html({ orden });

    expect(h).not.toContain('action="?/destrabar"');
    expect(h).not.toContain('Detenida');
  });

  //  MANDA EL BLOQUEO, NO EL ESTADO. El servidor solo manda `bloqueo` cuando
  //  hay uno abierto que detuvo el trabajo; una orden que figura `bloqueada`
  //  sin esa fila no tiene qué devolver (el servidor contestaría 409), y la
  //  tarjeta no puede romperse leyendo un motivo que no llegó.
  it('bloqueada pero sin bloqueo abierto: se dibuja, y sin el botón', () => {
    const h = html({ orden: { ...orden, estado: 'bloqueada', estado_texto: 'Bloqueada' } });

    expect(h).toContain('OT 83');
    expect(h).not.toContain('action="?/destrabar"');
  });

  //  POR QUÉ SE DEVOLVIÓ  --  21/11/2026, OT #281. «Corrección requerida»
  //  no decía qué se pidió rehacer ni por qué.
  describe('la orden devuelta dice por qué', () => {
    const devuelta = {
      ...orden,
      estado: 'correccion_requerida',
      estado_texto: 'Corrección requerida',
      devolucion: {
        quien: 'el Supervisor',
        cuando: '21/11 09:14',
        rehacer: ['Medición al salir', 'Daño encontrado'],
        motivo: 'La foto del medidor al salir no deja leer ningún número.'
      }
    };

    it('quién la devolvió, cuándo, qué tiene que rehacer y el motivo', () => {
      const h = html({ orden: devuelta });

      expect(h).toContain('Devuelta por el Supervisor · 21/11 09:14');
      expect(h).toContain('Medición al salir, Daño encontrado');
      expect(h).toContain('no deja leer ningún número');
    });

    it('cada punto del motivo va en su renglón, sin la barra', () => {
      const h = html({ orden: { ...devuelta, devolucion: { ...devuelta.devolucion,
        motivo: 'Revisá las fotos: 1 es una imagen de producto. | No se pudo comparar el reporte con el ticket.' } } });

      //  Dos del motivo y uno de «Tiene que rehacer».
      expect(h.split('od-devuelta-texto').length - 1).toBe(3);
      expect(h).not.toContain(' | ');
      expect(h).toContain('No se pudo comparar el reporte con el ticket.');
    });

    it('sin motivo escrito igual dice qué rehacer', () => {
      const h = html({ orden: { ...devuelta,
        devolucion: { ...devuelta.devolucion, motivo: '' } } });

      expect(h).toContain('Tiene que rehacer:');
      expect(h.split('od-devuelta-texto').length - 1).toBe(1);
    });

    it('la que no está devuelta no dibuja nada', () => {
      expect(html({ orden })).not.toContain('od-devuelta');
      expect(html({ orden: { ...orden, devolucion: null } })).not.toContain('Devuelta por');
    });
  });

  //  LOS RECORDATORIOS SE PLIEGAN  --  20/11/2026, OT #328. El Supervisor
  //  recuerda cada 15 minutos: una orden parada días dibujaba decenas de
  //  renglones iguales. Se mide el efecto: cuántas veces sale la frase.
  describe('los recordatorios del Supervisor', () => {
    const FRASE = 'El Supervisor le recordó reportar';
    const veces = (/** @type {string} */ h) => h.split(FRASE).length - 1;
    const r = (/** @type {string} */ cuando, llego = true) => ({ cuando, llego });

    it('uno solo se ve entero, sin plegar', () => {
      const h = html({ orden: { ...orden, recordatorios: [r('14:55')] } });

      expect(veces(h)).toBe(1);
      expect(h).toContain('14:55');
      expect(h).not.toContain('<details class="od-recordatorios');
    });

    it('varios quedan en UN renglón, con cuántos y cuándo el último', () => {
      const h = html({ orden: { ...orden, recordatorios: [
        r('14/11 14:55'), r('14/11 15:10'), r('14/11 15:25')] } });

      expect(veces(h)).toBe(1);
      expect(h).toContain('3 veces');
      expect(h).toContain('último 14/11 15:25');
      expect(h).toContain('<details class="od-recordatorios');
      //  Cerrado al nacer: abierto no pliega nada. Con regex, porque Svelte
      //  le agrega su clase de alcance al atributo.
      expect(h).not.toMatch(/<details[^>]*od-recordatorios[^>]*\sopen/);
    });

    it('la lista completa sigue adentro, para quien la abra', () => {
      const h = html({ orden: { ...orden, recordatorios: [
        r('14/11 14:55'), r('14/11 15:10'), r('14/11 15:25')] } });

      expect(h.split('od-recordatorio-fila').length - 1).toBe(3);
      expect(h).toContain('14/11 14:55');
      expect(h).toContain('14/11 15:10');
    });

    it('plegado no esconde los que no llegaron al teléfono', () => {
      const dos = html({ orden: { ...orden, recordatorios: [
        r('14:55', false), r('15:10'), r('15:25', false)] } });
      const uno = html({ orden: { ...orden, recordatorios: [
        r('14:55', false), r('15:10')] } });
      const bien = html({ orden: { ...orden, recordatorios: [r('14:55'), r('15:10')] } });

      expect(dos).toContain('(2 no llegaron al teléfono)');
      expect(uno).toContain('(1 no llegó al teléfono)');
      expect(dos).toMatch(/<summary class="[^"]*od-recordatorio-mal/);
      expect(bien).not.toContain('no lleg');
      expect(bien).not.toContain('od-recordatorio-mal');
    });

    it('sin recordatorios no se dibuja nada', () => {
      expect(veces(html({ orden }))).toBe(0);
      expect(html({ orden })).not.toContain('od-recordatorios');
    });
  });

  //  EL RESULTADO SE VE AUNQUE EL BLOQUE YA NO ESTÉ: cuando sale bien, la
  //  orden recarga sin bloqueo. Si el mensaje viviera adentro del bloque, el
  //  éxito no se mostraría nunca.
  it('el resultado se muestra en la orden que ya no está detenida', () => {
    const h = html({ orden, form: { de: 'destrabar', orden: 'o-1',
                                    hecho: 'Devuelta al técnico.' } });

    expect(h).toContain('Devuelta al técnico.');
  });

  it('el error se muestra, y solo en su orden', () => {
    const mia = html({ orden: detenida, form: { de: 'destrabar', orden: 'o-1',
                                                error: 'No se pudo devolver.' } });
    const otra = html({ orden: detenida, form: { de: 'destrabar', orden: 'OTRA',
                                                 error: 'No se pudo devolver.' } });

    expect(mia).toContain('No se pudo devolver.');
    expect(mia).toContain('snoc-error-txt');
    expect(otra).not.toContain('No se pudo devolver.');
  });
});
