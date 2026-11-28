/**
 * PRUEBA DE CARGA DE DEXTER  --  24/11/2026
 *
 * Simula a la gente que usa Dexter a la vez, haciendo lo MISMO que hace su
 * navegador o su teléfono, con la misma frecuencia. Los intervalos salen del
 * código, no de una suposición:
 *
 *   Oficina (Bandeja)   lista de chats cada 8 s   conversaciones/+layout.svelte
 *                       chat abierto cada 5 s      conversaciones/[id]/+page.svelte
 *   Supervisor NOC      Programación cada 15 s     supervisor-noc/programacion/+page.svelte
 *                       Pulso cada 60 s            lib/supervisor/ui/PulsoDelNoc.svelte
 *   Técnico (app)       ubicación cada 90 s        core/ubicacion/compartir_ubicacion.dart
 *                       sincroniza cada 2 min      core/sync/envio_automatico.dart
 *
 * Cómo se corre y cómo se lee: pruebas-carga/LEEME.md.
 *
 * LO QUE NO SIMULA: mensajes de WhatsApp entrando al motor. Cada uno llama a
 * OpenAI (cuesta) y el motor le CONTESTA al número por Meta: contra un motor
 * real, una prueba así le escribe a teléfonos de verdad. Va aparte, y solo
 * contra un motor con Meta y el modelo simulados.
 */

import http from 'k6/http';
import { check, sleep, fail } from 'k6';
import exec from 'k6/execution';
import { Counter } from 'k6/metrics';

// ---------------------------------------------------------------------------
// CONFIGURACIÓN (todo por variables: -e NOMBRE=valor)
// ---------------------------------------------------------------------------
const FRONT = (__ENV.FRONT || '').replace(/\/+$/, '');
const API = (__ENV.API || '').replace(/\/+$/, '');
const PERFIL = __ENV.PERFIL || 'humo';
const ESCRIBE = __ENV.CARGA_ESCRIBE === 'si';
const SESION_S = num(__ENV.SESION_S, 300);
//  La Bandeja no recarga la página entera: invalida 'app:conversaciones', y
//  SvelteKit pide solo ese nodo (root, (app), conversaciones, página).
const BANDEJA_INVALIDA = __ENV.BANDEJA_INVALIDA || '0010';

/** Cuánta gente hay HOY a la vez. El perfil la multiplica. */
const BASE = {
  oficina: num(__ENV.OFICINA, 6),
  supervisor: num(__ENV.SUPERVISORES, 2),
  tecnico: num(__ENV.TECNICOS, 10)
};

/** Los dominios de producción. Agregar los de Dexter con -e HOSTS_PRODUCCION=a,b */
const HOSTS_PRODUCCION = [
  'agent.rapilinksas.co',
  'agent-api.rapilinksas.co',
  'motor.rapilinksas.co',
  ...(__ENV.HOSTS_PRODUCCION || '').split(',').map((h) => h.trim()).filter(Boolean)
];

if (!FRONT || !API) {
  throw new Error('Faltan FRONT y API: -e FRONT=https://app... -e API=https://api...');
}

// ---------------------------------------------------------------------------
// GUARDAS: lo que esta prueba se niega a hacer
// ---------------------------------------------------------------------------
const host = (u) => u.replace(/^https?:\/\//, '').split(/[/:]/)[0].toLowerCase();
const esProduccion = [FRONT, API].some((u) => HOSTS_PRODUCCION.includes(host(u)));

if (esProduccion) {
  if (__ENV.CONTRA_PRODUCCION !== 'si-entiendo') {
    throw new Error(
      `${host(FRONT)} es PRODUCCIÓN. Una prueba de carga ahí la sienten los clientes. ` +
        'Si es a propósito (fuera de horario, con alguien mirando): -e CONTRA_PRODUCCION=si-entiendo'
    );
  }
  //  Las posiciones falsas aparecerían en el mapa del Supervisor como si
  //  fueran de los técnicos de verdad.
  if (ESCRIBE) throw new Error('En producción la prueba no escribe: quitá CARGA_ESCRIBE.');
  //  El perfil de estrés está hecho para encontrar dónde se quiebra.
  if (PERFIL === 'estres') throw new Error('El perfil estres no corre contra producción: usá staging.');
}

// ---------------------------------------------------------------------------
// PERFILES
// ---------------------------------------------------------------------------
const n = (quien, x) => Math.max(1, Math.round(BASE[quien] * x));

/** @param {string} quien @param {string} funcion */
function escenario(quien, funcion) {
  const sube = (x, dur) => ({ duration: dur, target: n(quien, x) });
  const perfiles = {
    //  Una persona de cada una, un minuto: ¿funciona el script contra este servidor?
    humo: { executor: 'constant-vus', vus: 1, duration: '1m' },
    //  La gente de hoy, diez minutos.
    normal: { executor: 'ramping-vus', startVUs: 0, stages: [sube(1, '1m'), sube(1, '10m'), sube(0, '30s')] },
    //  El doble: la tesis de vender a un ISP con el doble de clientes.
    doble: { executor: 'ramping-vus', startVUs: 0, stages: [sube(1, '1m'), sube(2, '2m'), sube(2, '10m'), sube(0, '30s')] },
    //  Sube por escalones hasta 10 veces, para ver DÓNDE se quiebra. Cada
    //  escalón dura lo suficiente para que se note si se estabiliza o no.
    estres: {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [1, 2, 3, 5, 7, 10].flatMap((x) => [sube(x, '1m'), sube(x, '3m')]).concat([sube(0, '1m')])
    }
  };
  const p = perfiles[PERFIL];
  if (!p) throw new Error(`PERFIL desconocido: ${PERFIL}. Son: ${Object.keys(perfiles).join(', ')}`);
  const rampa = p.executor === 'ramping-vus' ? { gracefulRampDown: '20s' } : {};
  return { ...p, ...rampa, exec: funcion, tags: { quien } };
}

/** Las pantallas, para que el resumen las muestre una por una. */
const PANTALLAS = ['bandeja', 'chat', 'bandeja-cola', 'chat-nuevos', 'programacion',
  'programacion-vivo', 'pulso', 'campo-mi-dia', 'campo-trabajos', 'campo-notificaciones', 'campo-ubicacion'];

export const options = {
  //  Un grupo en cero (-e TECNICOS=0) no se simula.
  scenarios: Object.fromEntries(
    ['oficina', 'supervisor', 'tecnico'].filter((q) => BASE[q] > 0).map((q) => [q, escenario(q, q)])
  ),
  //  Las metas. Una que no se cumple deja el resultado en rojo; la de errores
  //  además CORTA la prueba: seguir golpeando un servidor caído no mide nada.
  thresholds: {
    'http_req_failed{fase:uso}': [{ threshold: 'rate<0.01', abortOnFail: false }, { threshold: 'rate<0.10', abortOnFail: true, delayAbortEval: '30s' }],
    'http_req_duration{tipo:sondeo}': ['p(95)<1500'],
    'http_req_duration{tipo:pagina}': ['p(95)<3000'],
    'http_req_duration{tipo:app}': ['p(95)<2000'],
    checks: ['rate>0.99'],
    //  Sin meta, k6 no guarda la métrica de cada pantalla: esta siempre se cumple.
    ...Object.fromEntries(PANTALLAS.map((p) => [`http_req_duration{name:${p}}`, ['max>=0']]))
  },
  setupTimeout: '5m',
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max']
};

const sesionVencida = new Counter('sesion_vencida');

// ---------------------------------------------------------------------------
// CUENTAS: de un archivo que NO va al repositorio (ver cuentas.ejemplo.json)
// ---------------------------------------------------------------------------
const CUENTAS = JSON.parse(open(__ENV.CUENTAS || './cuentas.json'));

/** Entra como lo hace la app: login, empresa, y los tokens con la empresa adentro. */
function entrar(cuenta, quien) {
  const json = { headers: { 'Content-Type': 'application/json' }, tags: { fase: 'entrada' }, timeout: '60s' };
  const r = http.post(`${API}/api/auth/login/`, JSON.stringify({ email: cuenta.email, password: cuenta.password }), json);
  if (r.status !== 200) fail(`${quien} ${cuenta.email}: el login devolvió ${r.status}. ¿La contraseña es la de este servidor?`);
  const access = r.json('access_token');

  let org = cuenta.org_id || CUENTAS.org_id;
  if (!org) {
    const me = http.get(`${API}/api/auth/me/`, { headers: { Authorization: `Bearer ${access}` }, tags: { fase: 'entrada' } });
    org = (me.json('organizations') || [])[0]?.id;
    if (!org) fail(`${cuenta.email} no pertenece a ninguna empresa.`);
  }
  const s = http.post(`${API}/api/auth/switch-org/`, JSON.stringify({ org_id: org }), {
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${access}` },
    tags: { fase: 'entrada' },
    timeout: '60s'
  });
  if (s.status !== 200) fail(`${cuenta.email}: elegir la empresa devolvió ${s.status}.`);
  return { email: cuenta.email, access: s.json('access_token'), refresh: s.json('refresh_token'), org };
}

/** Hoy en Bogotá, AAAA-MM-DD: es el día que pide Programación. */
function hoyEnBogota() {
  return new Date(Date.now() - 5 * 3600 * 1000).toISOString().slice(0, 10);
}

export function setup() {
  const grupo = (quien) => {
    const lista = CUENTAS[quien] || [];
    if (!lista.length && BASE[quien] > 0) fail(`cuentas.json no trae cuentas de "${quien}".`);
    return lista.map((c) => entrar(c, quien));
  };
  const datos = { oficina: grupo('oficina'), supervisor: grupo('supervisor'), tecnico: grupo('tecnico'), dia: hoyEnBogota() };

  //  Chats reales para tener uno abierto: los ids salen de la misma lista que
  //  ve la Bandeja, y se queda con los que se pueden leer.
  datos.conversaciones = [];
  if (datos.oficina.length) {
    const s = datos.oficina[0];
    const r = http.get(`${FRONT}/conversaciones/__data.json`, { ...frontParams(s, 'entrada', 'bandeja'), tags: { fase: 'entrada' } });
    const ids = [...new Set((r.body || '').match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/g) || [])];
    for (const id of ids) {
      if (datos.conversaciones.length >= 20) break;
      const h = http.get(`${FRONT}/api/conversaciones/${id}/hilo?limite=1`, { ...frontParams(s, 'entrada', 'hilo'), tags: { fase: 'entrada' } });
      if (h.status === 200) datos.conversaciones.push(id);
    }
  }
  console.log(
    `Listo: ${datos.oficina.length} de oficina, ${datos.supervisor.length} supervisores, ${datos.tecnico.length} técnicos, ` +
      `${datos.conversaciones.length} chats para abrir. Perfil ${PERFIL}${esProduccion ? ' — PRODUCCIÓN' : ''}.`
  );
  return datos;
}

// ---------------------------------------------------------------------------
// PEDIDOS
// ---------------------------------------------------------------------------
function frontParams(s, tipo, nombre) {
  return {
    cookies: {
      jwt_access: { value: s.access, replace: true },
      jwt_refresh: { value: s.refresh, replace: true },
      org: { value: s.org, replace: true }
    },
    redirects: 0,
    tags: { tipo, name: nombre, fase: 'uso' },
    timeout: '30s'
  };
}

function apiParams(s, tipo, nombre) {
  return {
    headers: { Authorization: `Bearer ${s.access}`, 'Content-Type': 'application/json' },
    redirects: 0,
    tags: { tipo, name: nombre, fase: 'uso' },
    timeout: '30s'
  };
}

/** Un 30x a /login es una sesión caída, no una página servida: se cuenta aparte. */
function revisar(r, nombre) {
  if (r.status >= 300 && r.status < 400 && String(r.headers.Location || '').includes('/login')) sesionVencida.add(1);
  check(r, { [`${nombre}: responde bien`]: (x) => x.status === 200 || x.status === 201 });
  if (r.status !== 200 && r.status !== 201 && __ENV.CARGA_DETALLE === 'si') {
    console.warn(`${nombre}: ${r.status} ${String(r.body || '').slice(0, 200)}`);
  }
}

const pagina = (s, ruta, nombre) => revisar(http.get(`${FRONT}${ruta}`, frontParams(s, 'pagina', nombre)), nombre);
const sondeo = (s, ruta, nombre) => revisar(http.get(`${FRONT}${ruta}`, frontParams(s, 'sondeo', nombre)), nombre);
const app = (s, ruta, nombre) => revisar(http.get(`${API}${ruta}`, apiParams(s, 'app', nombre)), nombre);

/**
 * Corre las tareas cada una a su ritmo durante la sesión, como los
 * `setInterval` del navegador. Arranca cada una en un momento al azar dentro
 * de su intervalo: cien navegadores no se abren todos en el mismo segundo.
 */
function durante(segundos, tareas) {
  const fin = Date.now() + segundos * 1000;
  const prox = tareas.map((t) => Date.now() + Math.random() * t.cada * 1000);
  while (Date.now() < fin) {
    const ahora = Date.now();
    tareas.forEach((t, i) => {
      if (ahora >= prox[i]) {
        t.hacer();
        prox[i] = ahora + t.cada * 1000;
      }
    });
    const espera = Math.min(...prox, fin) - Date.now();
    if (espera > 0) sleep(espera / 1000);
  }
}

const deTurno = (lista) => lista[(exec.vu.idInTest - 1) % lista.length];

// ---------------------------------------------------------------------------
// LAS TRES PERSONAS
// ---------------------------------------------------------------------------
export function oficina(d) {
  const s = deTurno(d.oficina);
  const chat = d.conversaciones.length ? deTurno(d.conversaciones) : null;
  pagina(s, '/conversaciones', 'bandeja');
  if (chat) pagina(s, `/conversaciones/${chat}`, 'chat');
  durante(SESION_S, [
    { cada: 8, hacer: () => sondeo(s, `/conversaciones/__data.json?x-sveltekit-invalidated=${BANDEJA_INVALIDA}`, 'bandeja-cola') },
    ...(chat ? [{ cada: 5, hacer: () => sondeo(s, `/api/conversaciones/${chat}/hilo?limite=1`, 'chat-nuevos') }] : [])
    //  Sin sondeo de notificaciones: el contador de la campana lo calcula el
    //  servidor al abrir cada página. lib/stores/notifications.svelte.js (que
    //  sondeaba cada 45 s) solo lo usa AppShell, que ya no monta ninguna pantalla.
  ]);
}

export function supervisor(d) {
  const s = deTurno(d.supervisor);
  pagina(s, '/supervisor-noc/programacion', 'programacion');
  durante(SESION_S, [
    { cada: 15, hacer: () => sondeo(s, `/supervisor-noc/programacion/vivo?dia=${d.dia}`, 'programacion-vivo') },
    { cada: 60, hacer: () => sondeo(s, '/supervisor-noc/pulso', 'pulso') }
  ]);
}

export function tecnico(d) {
  const s = deTurno(d.tecnico);
  app(s, '/api/campo/mi-dia/', 'campo-mi-dia');
  durante(SESION_S, [
    { cada: 120, hacer: () => app(s, '/api/campo/trabajos/', 'campo-trabajos') },
    { cada: 120, hacer: () => app(s, '/api/notifications/', 'campo-notificaciones') },
    ...(ESCRIBE
      ? [{
          cada: 90,
          hacer: () => {
            //  Alrededor de Soledad (Atlántico), corrido un poco por técnico.
            const r = http.post(
              `${API}/api/campo/ubicacion/`,
              JSON.stringify({
                latitud: 10.91 + exec.vu.idInTest * 0.001,
                longitud: -74.77 - Math.random() * 0.01,
                medida_en: new Date().toISOString(),
                precision_m: 15,
                bateria: 80
              }),
              apiParams(s, 'app', 'campo-ubicacion')
            );
            revisar(r, 'campo-ubicacion');
          }
        }]
      : [])
  ]);
}

// ---------------------------------------------------------------------------
// EL RESUMEN, en castellano y guardado en un archivo
// ---------------------------------------------------------------------------
export function handleSummary(datos) {
  const m = datos.metrics;
  const ms = (x) => (x == null ? '—' : `${Math.round(x)} ms`);
  const lineas = [];
  lineas.push(`PRUEBA DE CARGA · perfil ${PERFIL} · ${FRONT}`);
  lineas.push(`Pedidos: ${m.http_reqs?.values.count ?? 0} (${(m.http_reqs?.values.rate ?? 0).toFixed(1)} por segundo)`);
  lineas.push(`Con error: ${((m['http_req_failed{fase:uso}']?.values.rate ?? 0) * 100).toFixed(2)} %`);
  lineas.push(`Sesiones caídas (rebote a /login): ${m.sesion_vencida?.values.count ?? 0}`);
  lineas.push(`Gente simulada a la vez, máximo: ${m.vus_max?.values.max ?? '—'}`);
  lineas.push('');
  lineas.push('Tiempo de respuesta (p95 = el 95 % tardó menos que esto):');
  for (const [tipo, meta] of [['sondeo', 1500], ['pagina', 3000], ['app', 2000]]) {
    const t = m[`http_req_duration{tipo:${tipo}}`]?.values;
    if (!t) continue;
    lineas.push(`  ${tipo.padEnd(7)} mediana ${ms(t.med).padStart(8)}  p95 ${ms(t['p(95)']).padStart(8)}  máx ${ms(t.max).padStart(9)}  meta p95 < ${meta} ms  ${t['p(95)'] < meta ? 'OK' : 'NO CUMPLE'}`);
  }
  lineas.push('');
  lineas.push('Por pantalla:');
  for (const [nombre, valor] of Object.entries(m)) {
    const g = nombre.match(/^http_req_duration\{name:(.+)\}$/);
    if (!g) continue;
    const v = valor.values;
    if (!v.max) continue; //  sin pedidos en esta corrida
    lineas.push(`  ${g[1].padEnd(22)} mediana ${ms(v.med).padStart(8)}  p95 ${ms(v['p(95)']).padStart(8)}  máx ${ms(v.max).padStart(9)}`);
  }
  const fallidas = Object.values(datos.root_group?.checks ?? {}).filter((c) => c.fails > 0);
  if (fallidas.length) {
    lineas.push('');
    lineas.push('Comprobaciones que fallaron:');
    for (const c of fallidas) lineas.push(`  ${c.name}: ${c.fails} de ${c.passes + c.fails}`);
  }
  const texto = lineas.join('\n') + '\n';
  const sello = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  return {
    stdout: texto,
    [`resultados/${PERFIL}-${sello}.txt`]: texto,
    [`resultados/${PERFIL}-${sello}.json`]: JSON.stringify(datos, null, 1)
  };
}

function num(v, porDefecto) {
  const x = Number(v);
  return Number.isFinite(x) && v !== undefined && v !== '' ? x : porDefecto;
}
