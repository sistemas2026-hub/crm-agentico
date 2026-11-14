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
