/**
 * LA ORGANIZACIÓN DE LA EMPRESA, LEÍDA DE SU CONFIGURACIÓN.
 *
 * QUÉ CAMBIÓ EL 31/10/2026, Y POR QUÉ NO ERA UN DETALLE
 * ------------------------------------------------------
 * Este archivo tenía SEIS departamentos escritos dentro. Se midió de dónde
 * habían salido: de agrupar el campo `area` de los roles configurados. Así que
 * la oficina virtual no mostraba la organización de la empresa — mostraba los
 * GRUPOS DE SUS AGENTES, que es otra cosa, y tres consecuencias lo prueban:
 *
 *   · Un departamento sin ningún agente no existía. Recursos Humanos y
 *     Auditoría son departamentos reales de un proveedor de internet y no hay
 *     un agente que los represente; deducidos de los agentes, desaparecen. Una
 *     empresa que mira su propia oficina y no ve a Recursos Humanos no está
 *     viendo su empresa.
 *   · Dos etiquetas de rol que son UN departamento salían como dos salas.
 *     «Soporte Técnico» y «Atención al Cliente» son dos áreas en el vocabulario
 *     de los roles y una sola puerta de servicio en la empresa.
 *   · La siguiente empresa necesitaba una sesión de código. El ISP chico tiene
 *     cuatro departamentos en una planta; el grande, quince en cinco niveles.
 *
 * Ahora la estructura llega del motor (`TenantConfig.organizacion`) y este
 * archivo no sabe cuántos departamentos hay ni cómo se llaman. Lo que hace es
 * casar esa declaración con dos cosas: el catálogo de salas (`plantillas.js`) y
 * el inventario de agentes que el motor sirve.
 *
 * LO QUE SIGUE SIENDO CÓDIGO, Y ES CORRECTO QUE LO SEA
 * La geometría. Ver el encabezado de `plantillas.js`: describir una sala
 * isométrica son cuarenta números y equivocarse en uno no da error. La empresa
 * elige una plantilla; no la describe.
 *
 * NADA DE AQUÍ INVENTA
 * Un puesto sin agente declarado queda vacío. Un agente declarado que el
 * inventario no trae deja el puesto vacío Y DICE POR QUÉ. Una plantilla que el
 * catálogo no tiene cae en una sala sosa y marcada. Las tres son informaciones
 * verdaderas, y las tres se ven distintas entre sí — que es el punto.
 */

import { plantillaDe } from './plantillas.js';

/**
 * @typedef {{ id: string, rotulo: string, direccion: string, piso: number,
 *             tipo: 'departamento'|'espacio', areas: string[],
 *             capacidades: string[], plantilla: string,
 *             plantillaFaltante: string|null, puestosDesconocidos: string[],
 *             planta: any }} Sala
 */

/**
 * `#rrggbb` -> número, que es lo que la escena entiende.
 *
 * La configuración guarda el color como texto porque es lo que se escribe en un
 * formulario y lo que ya hace `AreaDeTrabajo.color`; la escena lo quiere como
 * entero. Un valor que no sea exactamente `#rrggbb` se descarta en vez de
 * interpretarse: el motor ya lo valida, y adivinar acá taparía el día que deje
 * de validarlo.
 *
 * @param {string|undefined|null} texto
 */
function colorDe(texto) {
  const t = String(texto ?? '').trim();
  if (!/^#[0-9a-fA-F]{6}$/.test(t)) return null;
  return parseInt(t.slice(1), 16);
}

/**
 * Una sala lista para dibujar: lo que la empresa declaró + la geometría elegida.
 *
 * @param {any} decl la declaración de la configuración
 * @param {'departamento'|'espacio'} tipo
 * @returns {Sala}
 */
function componer(decl, tipo) {
  const { plantilla, faltante } = plantillaDe(decl?.plantilla);
  const ocupaciones = new Map(
    (Array.isArray(decl?.ocupaciones) ? decl.ocupaciones : [])
      .filter((o) => o && o.puesto)
      .map((o) => [String(o.puesto), o])
  );

  const id = String(decl?.id ?? '');
  const puestos = plantilla.puestos.map((p) => {
    const o = ocupaciones.get(p.id);
    return {
      ...p,
      //  El identificador global se compone acá y no en la plantilla: dos
      //  departamentos con la misma plantilla tienen los mismos puestos
      //  locales, y sin el prefijo seleccionar uno seleccionaría el otro.
      id: `${id}:${p.id}`,
      local: p.id,
      nombre: (o && o.nombre) || p.nombre,
      agente: (o && o.agente) || null,
      //  UNA PERSONA DEL EQUIPO. Sin esto, un escritorio donde trabaja alguien
      //  se dibujaba EXACTAMENTE IGUAL que uno libre, y mirar la oficina decia
      //  que media empresa no existe.
      persona: (o && o.persona) || null
    };
  });

  //  Puestos que la configuración declara y la plantilla NO tiene. Es el caso
  //  en que un agente declarado desaparecería sin que nadie lo notara: la
  //  empresa escribió que alguien se sienta y no hay silla. Se reporta en vez
  //  de ignorarse.
  const locales = new Set(plantilla.puestos.map((p) => p.id));
  const puestosDesconocidos = [...ocupaciones.keys()].filter((k) => !locales.has(k));

  return {
    id,
    rotulo: String(decl?.rotulo ?? id),
    direccion: String(decl?.direccion ?? ''),
    piso: Number.isFinite(decl?.piso) ? Number(decl.piso) : 1,
    tipo,
    areas: Array.isArray(decl?.areas) ? decl.areas.map(String) : [],
    capacidades: Array.isArray(decl?.capacidades) ? decl.capacidades.map(String) : [],
    plantilla: String(decl?.plantilla ?? ''),
    plantillaFaltante: faltante,
    puestosDesconocidos,
    planta: {
      ...plantilla,
      acento: colorDe(decl?.acento) ?? plantilla.acento,
      puestos
    }
  };
}

/**
 * Todas las salas de la empresa: sus departamentos y sus espacios.
 *
 * Los espacios —recepción, dirección, una sala de reuniones— van en la misma
 * lista porque son salas del mismo edificio, y llevan `tipo` porque no son
 * departamentos: no agrupan áreas ni agentes, y a una recepción no se le
 * asignan responsabilidades.
 *
 * Una organización vacía devuelve una lista vacía. NO cae a nada: inventar una
 * estructura es exactamente lo que este archivo dejó de hacer, y quien la
 * muestre tiene que poder decir que no la tiene.
 *
 * @param {any} organizacion el documento que sirve el motor
 * @returns {Sala[]}
 */
export function salasDe(organizacion) {
  const org = organizacion ?? {};
  const deps = Array.isArray(org.departamentos) ? org.departamentos : [];
  const esps = Array.isArray(org.espacios) ? org.espacios : [];
  return [
    ...deps.filter((d) => d && d.id).map((d) => componer(d, 'departamento')),
    ...esps.filter((e) => e && e.id).map((e) => componer(e, 'espacio'))
  ];
}

/**
 * Los pisos del edificio con sus salas, del más alto al más bajo.
 *
 * De arriba hacia abajo porque es como se lee un edificio, y porque es el orden
 * en el que la sección arquitectónica de la etapa siguiente los va a apilar.
 *
 * UN PISO DECLARADO Y VACÍO SIGUE APARECIENDO. Una empresa que declara cuatro
 * niveles y solo ocupa tres tiene un piso libre, y eso es un dato de su
 * edificio, no un error que haya que esconder.
 *
 * Y una sala en un piso que nadie declaró TAMBIÉN aparece, en un piso extra
 * marcado. El motor lo rechaza al validar, así que llegar hasta acá significa
 * que entró por otro camino; perderla en silencio dejaría a un departamento
 * fuera del edificio sin que nadie pudiera explicar por qué.
 *
 * @param {any} organizacion
 * @param {Sala[]} [salas] las ya compuestas, para no componerlas dos veces
 */
export function pisosDe(organizacion, salas) {
  const lista = salas ?? salasDe(organizacion);
  const declarados = Array.isArray(organizacion?.pisos) ? organizacion.pisos : [];
  const porNivel = new Map();
  for (const p of declarados) {
    if (!p || !Number.isFinite(p.nivel)) continue;
    porNivel.set(Number(p.nivel), {
      nivel: Number(p.nivel),
      rotulo: String(p.rotulo ?? ''),
      declarado: true,
      salas: []
    });
  }
  for (const s of lista) {
    if (!porNivel.has(s.piso)) {
      porNivel.set(s.piso, { nivel: s.piso, rotulo: '', declarado: false, salas: [] });
    }
    porNivel.get(s.piso).salas.push(s);
  }
  return [...porNivel.values()].sort((a, b) => b.nivel - a.nivel);
}

/** @param {Sala[]} salas @param {string|null} id */
export function salaPorId(salas, id) {
  return salas.find((s) => s.id === id) ?? salas[0] ?? null;
}

/**
 * Compara rótulos de área sin acentos, mayúsculas ni separadores.
 *
 * Hace falta porque **hay dos vocabularios de área y no coinciden**: la
 * configuración declara identificadores (`operativo`, `soporte_tecnico`) y el
 * campo `area` de cada rol es texto libre («Operaciones»). Por eso cada
 * departamento declara TODAS las escrituras que reclama.
 *
 * Lo que NO hace es adivinar: no acepta parecidos ni sinónimos. Aceptar
 * «operaciones» como `operativo` serviría hoy y el día que una empresa tenga
 * las dos cosas sentaría al agente equivocado en el puesto, sin un error que lo
 * explique.
 *
 * Se EXPORTA porque la pantalla que organiza la empresa propone ocupantes
 * casando las mismas areas, y dos normalizaciones distintas casarian distinto:
 * una propondria a alguien que la oficina despues no agrupa en esa sala.
 *
 * @param {string} texto
 */
export function normalizar(texto) {
  return String(texto ?? '')
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

/**
 * SENTADOS EN UNA SILLA QUE NO EXISTE.
 *
 * Las ocupaciones que la configuración declara en un puesto que la plantilla
 * elegida NO tiene. Devuelve `sala/puesto` para que se pueda nombrar sin
 * ambigüedad: el mismo `p3` existe en cinco salas distintas.
 *
 * PASA, Y AHORA ES FACIL QUE PASE. Alguien cambia la sala de un departamento
 * por una más chica desde `/settings/organizacion` y el agente que estaba en
 * `p3` se queda sin dónde sentarse. La ocupación NO se borra -- se conserva a
 * propósito, para que volver a la sala grande lo devuelva a su puesto --, pero
 * mientras tanto el agente es invisible.
 *
 * Y eso, sin decirlo, es la falla de siempre: el pie decía «5 de 38 puestos
 * ocupados» y la diferencia con el documento guardado no la veía nadie. Un
 * agente que la empresa cree sentado y la oficina no dibuja tiene que aparecer
 * como lo que es.
 *
 * Vive acá y no en la pantalla porque una pantalla de SvelteKit no se puede
 * probar en este repositorio -- el harness no resuelve `$app/*` --, y esto es
 * exactamente la clase de cálculo que se rompe en silencio.
 *
 * @param {Sala[]} salas las que se estén mirando: una, un piso o el edificio
 * @returns {string[]}
 */
export function ocupacionesSinSilla(salas) {
  return (Array.isArray(salas) ? salas : [])
    .filter(Boolean)
    .flatMap((s) => (s.puestosDesconocidos ?? []).map((p) => `${s.rotulo}/${p}`));
}

/**
 * Los agentes cuya área cae en esta sala, en orden estable.
 *
 * NO decide quién se sienta —eso se declara, ver `plantaDe`—. Sirve para
 * responder la otra pregunta, la que la ficha necesita: qué roles pertenecen a
 * este departamento. Un rol que pertenece y no tiene puesto no es un error; es
 * una capacidad, o alguien a quien todavía nadie le asignó sitio.
 *
 * Un orden estable es lo que hace que la sala se vea igual en dos cargas
 * seguidas. Y no muta el arreglo que recibe: `sort` lo haría, y el resto de la
 * pantalla vería los agentes en otro orden sin motivo.
 *
 * @param {any[]} agentes el inventario tal como lo sirve el motor
 * @param {Sala} sala
 */
export function agentesDe(agentes, sala) {
  const lista = Array.isArray(agentes) ? agentes : [];
  const buscadas = new Set((sala?.areas ?? []).map(normalizar));
  if (buscadas.size === 0) return [];
  return [...lista]
    .filter((a) => a && buscadas.has(normalizar(a.area)))
    .sort((a, b) => String(a.nombre).localeCompare(String(b.nombre)))
    .map((a) => ({
      nombre: String(a.nombre),
      rotulo: a.cargo || String(a.nombre),
      area: sala.id
    }));
}

/**
 * La planta lista para dibujar: geometría de la sala + quién la ocupa.
 *
 * QUIÉN SE SIENTA SE DECLARA, NO SE DEDUCE (30/10/2026)
 * ----------------------------------------------------
 * Antes esta función sentaba a TODOS los agentes del área, en orden, hasta
 * llenar los puestos. Eso dibujaba nueve empleados donde hay seis: tres de los
 * nueve roles —`soporte`, `facturacion`, `administracion`— **no son empleados
 * virtuales**, son capacidades que se le asignan a una persona real del CRM.
 *
 * EL CAMPO QUE PARECÍA RESOLVERLO NO RESUELVE NADA. `orientado_a` viaja desde
 * el motor, y se midió contra el YAML del tenant: su valor por defecto en el
 * esquema es `colaborador`, así que los TRES que no lo declaran salen idénticos
 * a los DOS que sí lo declaran y sí tienen puerta propia. Separa 4 de 5, no
 * 4-2-3. Deducir la ocupación de ahí habría cambiado una invención por otra.
 *
 * Y se VALIDA contra el inventario: un agente declarado que el motor no sirve
 * deja el puesto vacío **y dice por qué**. Dibujarlo igual sería volver a
 * inventar un empleado; callarlo sería un hueco que nadie puede explicar.
 *
 * @param {Sala} sala
 * @param {any[]} agentes inventario del motor
 */
export function plantaDe(sala, agentes) {
  const inventario = new Map(
    (Array.isArray(agentes) ? agentes : [])
      .filter((a) => a && a.nombre)
      .map((a) => [String(a.nombre), a])
  );

  const puestos = sala.planta.puestos.map((p) => {
    //  UNA PERSONA VA PRIMERO. No se resuelve contra el inventario de agentes
    //  --no esta ahi ni tiene por que estarlo-- y por eso tampoco puede estar
    //  «ausente»: lo que la empresa escribio es lo que hay. El esquema del
    //  motor ya garantiza que un puesto no tenga agente Y persona.
    if (p.persona) {
      return { ...p, agente: null, persona: p.persona, nombre: p.persona,
               area: 'persona del equipo', motivo: null };
    }
    if (!p.agente) {
      return { ...p, agente: null, persona: null, nombre: p.nombre || 'Puesto',
               area: 'puesto libre', motivo: 'sin agente asignado' };
    }
    const real = inventario.get(p.agente);
    if (!real) {
      //  Declarado y ausente del inventario. No es lo mismo que un puesto
      //  libre, y la ficha lo dice con esas palabras.
      return { ...p, agente: null, persona: null, nombre: p.nombre || 'Puesto',
               area: 'agente no encontrado',
               motivo: `la configuración declara «${p.agente}» y el inventario no lo trae` };
    }
    return {
      ...p,
      agente: p.agente,
      persona: null,
      nombre: real.cargo || p.nombre || p.agente,
      area: sala.rotulo,
      //  A quién atiende. Es información real y se muestra en la ficha; NO se
      //  usa para decidir quién se sienta.
      orientado_a: real.orientado_a ?? null,
      motivo: null
    };
  });

  return {
    ...sala.planta,
    cartel: { ...sala.planta.cartel, rotulo: sala.rotulo },
    puestos,
    /**
     * Roles del departamento que existen y NO tienen puesto propio.
     *
     * Se resuelven contra el inventario y se muestran en la ficha. Que no
     * tengan escritorio no los hace invisibles: existen, y lo que la oficina no
     * puede hacer es dibujarlos como si fueran alguien sentado.
     */
    capacidades: (sala.capacidades ?? [])
      .map((n) => inventario.get(n) ?? { nombre: n, cargo: null, ausente: true })
      .map((a) => ({ nombre: String(a.nombre), cargo: a.cargo ?? null,
                     ausente: a.ausente === true }))
  };
}
