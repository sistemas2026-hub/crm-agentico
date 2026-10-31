import { describe, it, expect } from 'vitest';
import { comasALista, organizacionDelFormulario } from './organizacion-formulario.js';

/**
 * EL FORMULARIO → EL DOCUMENTO, Y NADA MÁS.
 *
 * Lo que esta capa hace es traducir: que los números sean números y que una
 * lista escrita con comas llegue como lista. Las reglas de una organización
 * coherente NO están acá —viven en el esquema del motor, que valida el
 * documento completo antes de escribir—, así que esto no las prueba: probarlas
 * en dos sitios es cómo se descubre, el día que se separen, que había dos
 * verdades.
 *
 * Lo que sí importa probar es el salto que §6 de CLAUDE.md describe como el que
 * más cuesta: el dato viaja bien desde el formulario y **la capa servidor lo
 * deja caer o lo renombra**. Ya pasó dos veces el 29/09/2026 con el backend en
 * verde.
 */

function formDe(pares) {
  const f = new FormData();
  for (const [k, v] of Object.entries(pares)) f.append(k, v);
  return f;
}

describe('una lista escrita con comas', () => {
  it('llega como lista, sin espacios ni vacíos', () => {
    expect(comasALista(' operativo , Operaciones ,, NOC y Redes ')).toEqual([
      'operativo', 'Operaciones', 'NOC y Redes'
    ]);
  });

  it('vacía es una lista vacía, no una lista con una cadena vacía', () => {
    // Una cadena vacía dentro del arreglo llegaría al motor como un área sin
    // nombre, y la rechazaría con un mensaje que no explica nada.
    expect(comasALista('')).toEqual([]);
    expect(comasALista(null)).toEqual([]);
    expect(comasALista('   ,  , ')).toEqual([]);
  });
});

describe('el formulario se convierte en una organización', () => {
  it('arma los pisos, los departamentos y los espacios', () => {
    const org = organizacionDelFormulario(formDe({
      'piso:0:nivel': '3', 'piso:0:rotulo': 'Tecnología',
      'piso:1:nivel': '1', 'piso:1:rotulo': '',
      'dep:0:id': 'operativo', 'dep:0:rotulo': 'NOC y Redes', 'dep:0:piso': '3',
      'dep:0:plantilla': 'operaciones', 'dep:0:areas': 'operativo, Operaciones',
      'dep:0:capacidades': '', 'dep:0:agente': 'supervisor_noc', 'dep:0:acento': '#4f46e5',
      'esp:0:id': 'recepcion', 'esp:0:rotulo': 'Recepción', 'esp:0:piso': '1',
      'esp:0:plantilla': 'atencion'
    }));

    expect(org.pisos).toEqual([{ nivel: 3, rotulo: 'Tecnología' }, { nivel: 1, rotulo: '' }]);
    expect(org.departamentos.length).toBe(1);
    expect(org.departamentos[0]).toMatchObject({
      id: 'operativo', rotulo: 'NOC y Redes', piso: 3, plantilla: 'operaciones',
      areas: ['operativo', 'Operaciones'], capacidades: [], acento: '#4f46e5'
    });
    expect(org.espacios).toEqual([
      { id: 'recepcion', rotulo: 'Recepción', piso: 1, plantilla: 'atencion', acento: '' }
    ]);
  });

  it('el agente elegido se guarda como una ocupación del puesto principal', () => {
    // Quien organiza la empresa elige una persona, no una silla. La silla la
    // pone la plantilla, y por eso el formulario no pregunta por ella.
    const org = organizacionDelFormulario(formDe({
      'dep:0:id': 'x', 'dep:0:plantilla': 'tecnica', 'dep:0:agente': 'ventas'
    }));
    expect(org.departamentos[0].ocupaciones).toEqual([
      { puesto: 'principal', agente: 'ventas' }
    ]);
  });

  it('NO borra las ocupaciones que la pantalla no edita', () => {
    // El defecto, encontrado en el navegador el 31/10/2026: al agregar un
    // departamento desde la pantalla, Atención al Cliente perdió a su segundo
    // agente y el pie pasó de «6 de 37 puestos ocupados» a «5 de 40». Sin
    // error y sin aviso: sólo visible contando.
    const org = organizacionDelFormulario(formDe({
      'dep:0:id': 'atencion_cliente', 'dep:0:plantilla': 'atencion',
      'dep:0:agente': 'cliente_final',
      'dep:0:otras': JSON.stringify([
        { puesto: 'p1', agente: 'soporte_tecnico_cliente', nombre: 'Diagnóstico' }
      ])
    }));
    expect(org.departamentos[0].ocupaciones).toEqual([
      { puesto: 'principal', agente: 'cliente_final' },
      { puesto: 'p1', agente: 'soporte_tecnico_cliente', nombre: 'Diagnóstico' }
    ]);
  });

  it('y un campo oculto roto no arrastra medio documento', () => {
    // Lo que llega mal es un campo que el navegador reescribió. Guardar media
    // lista sería peor que guardar ninguna.
    for (const basura of ['{', 'null', '"texto"', '42', '[1,2]']) {
      const org = organizacionDelFormulario(formDe({
        'dep:0:id': 'x', 'dep:0:plantilla': 'tecnica', 'dep:0:agente': 'ventas',
        'dep:0:otras': basura
      }));
      expect(org.departamentos[0].ocupaciones, basura).toEqual([
        { puesto: 'principal', agente: 'ventas' }
      ]);
    }
  });

  it('un principal repetido en el campo oculto no se cuela', () => {
    // Dos ocupaciones del mismo puesto son un documento que el esquema del
    // motor rechaza, con razón. Lo que no puede pasar es que lo arme esta capa.
    const org = organizacionDelFormulario(formDe({
      'dep:0:id': 'x', 'dep:0:plantilla': 'tecnica', 'dep:0:agente': 'ventas',
      'dep:0:otras': JSON.stringify([{ puesto: 'principal', agente: 'otro' }])
    }));
    expect(org.departamentos[0].ocupaciones).toEqual([
      { puesto: 'principal', agente: 'ventas' }
    ]);
  });

  it('sin agente, el departamento queda SIN ocupaciones', () => {
    // Un departamento sin nadie es el caso que la estructura deducida de los
    // agentes no podía representar. Mandar `[{puesto:'principal', agente:''}]`
    // lo haría parecer ocupado por alguien sin nombre.
    const org = organizacionDelFormulario(formDe({
      'dep:0:id': 'recursos_humanos', 'dep:0:plantilla': 'expedientes'
    }));
    expect(org.departamentos[0].ocupaciones).toEqual([]);
  });

  it('una fila sin identificador se descarta: es como se borra', () => {
    const org = organizacionDelFormulario(formDe({
      'dep:0:id': 'uno', 'dep:0:plantilla': 'tecnica',
      'dep:1:id': '', 'dep:1:rotulo': 'a medio escribir', 'dep:1:plantilla': 'tecnica',
      'esp:0:id': '', 'esp:0:rotulo': 'fantasma'
    }));
    expect(org.departamentos.map((d) => d.id)).toEqual(['uno']);
    expect(org.espacios).toEqual([]);
  });

  it('los índices del formulario no se guardan, y pueden tener huecos', () => {
    // Quitar una fila del medio deja `dep:0` y `dep:2`. Si el orden dependiera
    // del índice, la lista saldría desordenada o con un agujero.
    const org = organizacionDelFormulario(formDe({
      'dep:0:id': 'a', 'dep:0:plantilla': 'tecnica',
      'dep:2:id': 'b', 'dep:2:plantilla': 'tecnica'
    }));
    expect(org.departamentos.map((d) => d.id)).toEqual(['a', 'b']);
  });

  it('los números del formulario llegan como números', () => {
    // Un `piso: "3"` de texto pasa la validación del esquema por coerción y
    // después no empareja con `nivel: 3` al agrupar: el departamento
    // desaparecería del edificio sin un error que lo explique.
    const org = organizacionDelFormulario(formDe({
      'piso:0:nivel': '2',
      'dep:0:id': 'a', 'dep:0:plantilla': 'tecnica', 'dep:0:piso': '2'
    }));
    expect(org.pisos[0].nivel).toBe(2);
    expect(org.departamentos[0].piso).toBe(2);
  });

  it('un formulario vacío da una organización vacía, no basura', () => {
    // Vacía significa «la empresa deja de declarar la suya» y vuelve a la
    // estructura por defecto. Hay que poder deshacer.
    expect(organizacionDelFormulario(formDe({}))).toEqual({
      pisos: [], departamentos: [], espacios: []
    });
  });

  it('campos de otro formulario no se cuelan', () => {
    // El `FormData` trae todo lo que el navegador mande. Sin el filtro por
    // prefijo, un campo ajeno entraría como una fila.
    const org = organizacionDelFormulario(formDe({
      csrfmiddlewaretoken: 'x', 'otro:0:id': 'y',
      'dep:0:id': 'a', 'dep:0:plantilla': 'tecnica'
    }));
    expect(org.departamentos.map((d) => d.id)).toEqual(['a']);
  });
});
