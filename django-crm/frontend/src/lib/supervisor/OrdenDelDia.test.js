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
