<script>
  /**
   * Como cliente_final deriva una conversacion a un especialista
   * (facturacion_cliente, soporte_tecnico_cliente) y por que eso no es un
   * orquestador clasico -- ver nucleo/config/fusion.py, que documenta por
   * que SE DESCARTO esa alternativa, y nucleo/modelo/motor.py::
   * _ejecutar_derivacion, que es lo que reemplaza.
   *
   * Pagina puramente informativa (sin +page.server.js): no depende de que
   * este tenant tenga los roles nuevos configurados, es documentacion del
   * MECANISMO, igual que /agentes/asignaciones documenta el de fusion de
   * roles. Los mismos tonos que ya usan las etiquetas de conversaciones
   * (soporte_tecnico=clay, facturacion=moss, ver +layout.svelte) para que
   * el color se reconozca entre pantallas.
   */
  import PageHeader from '$lib/v2/components/PageHeader.svelte';
  import { enhance } from '$app/forms';
  import { Check, AlertTriangle } from '@lucide/svelte';

  /** @type {{ data: any, form: any }} */
  let { data, form } = $props();

  let flujo = $derived(data.flujo);
  let entradas = $derived(data.flujo?.entradas ?? []);
  let agentes = $derived(data.flujo?.agentes ?? []);
  // Candidatos a destino: todos los de cara al cliente menos la PUERTA DE
  // ENTRADA (a donde cae un mensaje nuevo). Ojo, no es "los que no derivan":
  // los especialistas tambien derivan, entre ellos, y aun asi son destinos
  // validos -- filtrar por eso dejaria la lista vacia.
  let candidatos = $derived(agentes.filter((/** @type {any} */ a) => !a.es_entrada));

  // Copia local editable. Se siembra una sola vez con lo que vino del motor;
  // despues manda lo que el usuario toco, hasta que recargue.
  let conectado = $state(
    Object.fromEntries(
      (data.flujo?.agentes ?? []).map((/** @type {any} */ a) => [a.nombre, a.es_destino])
    )
  );
  let atiende = $state(
    Object.fromEntries(
      (data.flujo?.agentes ?? []).map((/** @type {any} */ a) => [a.nombre, a.atiende ?? ''])
    )
  );

  // Conectado pero sin decir que atiende = enganchado e invisible: el router
  // no tiene con que decidir mandarle nada. Se avisa antes de guardar, no
  // despues de que alguien note que un agente nunca recibe conversaciones.
  let mudos = $derived(
    candidatos.filter((/** @type {any} */ a) => conectado[a.nombre] && !(atiende[a.nombre] || '').trim())
  );

  // 'update()' por defecto resetea el formulario a los valores del DOM al
  // cargar -- perderia lo recien escrito. Ver el mismo caso en la pantalla
  // del canal de WhatsApp.
  const guardando = () => {
    return async (/** @type {any} */ { update }) => {
      await update({ reset: false });
    };
  };
</script>

<PageHeader title="Flujo de derivación">
  {#snippet sub()}
    Cómo un mensaje de WhatsApp encuentra al especialista correcto, sin repetir la verificación de
    identidad ni sumar una llamada extra al modelo.
  {/snippet}
  {#snippet actions()}
    <a class="v2-btn v2-btn-sm" href="/agentes">Ver agentes</a>
  {/snippet}
</PageHeader>

<div class="v2-scroll">
  <div class="v2-pad" style="padding-top:16px;padding-bottom:40px;max-width:900px">

    <!-- ── conexiones, editable ──────────────────────────────────────────── -->
    <div class="v2-label" style="margin-bottom:10px">Quién atiende qué</div>
    {#if !flujo}
      <div class="v2-card" style="padding:20px 22px;margin-bottom:26px">
        <b style="font-size:13px">No se pudo leer el flujo</b>
        <p class="v2-sub" style="font-size:12.5px;margin:8px 0 0;line-height:1.5">
          El motor no está respondiendo. El diagrama de abajo explica igual el mecanismo.
        </p>
      </div>
    {:else if !flujo.herramienta_derivacion}
      <div class="v2-card" style="padding:20px 22px;margin-bottom:26px">
        <b style="font-size:13px">Este agente todavía no deriva a nadie</b>
        <p class="v2-sub" style="font-size:12.5px;margin:8px 0 0;line-height:1.5">
          Para conectar especialistas hace falta una herramienta de derivación en el catálogo del
          tenant. El diagrama de abajo explica cómo funcionaría.
        </p>
      </div>
    {:else}
      <form method="POST" action="?/guardar" use:enhance={guardando} style="margin-bottom:26px">
        <div class="v2-card" style="padding:16px">
          <p class="v2-sub" style="font-size:12px;margin:0 0 14px;line-height:1.5">
            {#if entradas.length}<b>{entradas.join(', ')}</b>{:else}El agente de entrada{/if}
            recibe todos los mensajes y decide a quién pasárselos, leyendo lo que cada agente dice
            que atiende. Escribilo como lo diría el cliente, no en jerga técnica.
          </p>

          {#each candidatos as a (a.nombre)}
            <div class="agente-fila">
              <label class="agente-check">
                <input type="checkbox" name="destinos" value={a.nombre}
                       bind:checked={conectado[a.nombre]} disabled={!data.can_edit} />
                <span>
                  <b style="font-size:13px">{a.area || a.nombre}</b>
                  <span class="v2-sub" style="font-size:11px"> · {a.n_herramientas} herramientas</span>
                </span>
              </label>

              {#if conectado[a.nombre]}
                <input class="v2-input agente-atiende" type="text" name={`atiende:${a.nombre}`}
                       placeholder="Ej: saldo, facturas, fecha de corte, un cobro que no entiende"
                       bind:value={atiende[a.nombre]} disabled={!data.can_edit} />
              {:else}
                <p class="v2-sub" style="font-size:11.5px;margin:0">
                  Desconectado: el agente existe, pero no le va a llegar ninguna conversación.
                </p>
              {/if}
            </div>
          {/each}

          {#if mudos.length}
            <p class="aviso-mudo">
              <AlertTriangle size={13} />
              {mudos.map((/** @type {any} */ a) => a.area || a.nombre).join(', ')}:
              está conectado pero sin describir qué atiende, así que el enrutador no va a tener con
              qué decidir mandarle nada.
            </p>
          {/if}

          {#if form?.error}<p class="v2-error" style="font-size:12px;margin:12px 0 0">{form.error}</p>{/if}
          {#if form?.guardado}<p class="ok-guardado"><Check size={13} /> Guardado</p>{/if}

          {#if data.can_edit}
            <button class="v2-btn v2-btn-primary v2-btn-sm" type="submit" style="margin-top:14px">
              Guardar flujo
            </button>
          {/if}
        </div>
      </form>
    {/if}

    <div class="v2-label" style="margin-bottom:10px">El mecanismo</div>
    <div class="v2-card diagrama-card">
      <svg class="diagrama" viewBox="0 0 900 700" role="img"
           aria-label="Un mensaje del cliente pasa primero por un chequeo de rol_efectivo: si la conversación ya fue derivada, entra directo al especialista guardado; si no, la atiende cliente_final, que puede derivar a facturación_cliente o a soporte_tecnico_cliente llamando a derivar_a_area en el mismo turno, sin una llamada aparte al modelo. Cualquiera de los dos especialistas puede escalar a un humano si no puede resolverlo solo.">

        <defs>
          <marker id="f-arrow" viewBox="0 0 10 10" refX="8" refY="5"
                   markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" fill="currentColor" />
          </marker>
          <marker id="f-arrow-moss" viewBox="0 0 10 10" refX="8" refY="5"
                   markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" style="fill:var(--v2-moss)" />
          </marker>
          <marker id="f-arrow-clay" viewBox="0 0 10 10" refX="8" refY="5"
                   markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" style="fill:var(--v2-clay)" />
          </marker>
          <marker id="f-arrow-rust" viewBox="0 0 10 10" refX="8" refY="5"
                   markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L10,5 L0,10 z" style="fill:var(--v2-rust)" />
          </marker>
        </defs>

        <rect x="365" y="14" width="170" height="46" rx="23"
              fill="none" stroke="currentColor" stroke-width="1.4" />
        <text x="450" y="42" text-anchor="middle" font-size="13" fill="currentColor">Cliente escribe</text>

        <line x1="450" y1="60" x2="450" y2="102" stroke="currentColor" stroke-width="1.4" marker-end="url(#f-arrow)" />

        <polygon points="450,108 562,172 450,236 338,172"
                 fill="var(--v2-line-soft)" stroke="currentColor" stroke-width="1.4" />
        <text x="450" y="164" text-anchor="middle" font-size="12" fill="currentColor">¿rol_efectivo ya</text>
        <text x="450" y="181" text-anchor="middle" font-size="12" fill="currentColor">apunta a un área?</text>

        <path d="M 366,196 C 320,225 290,240 280,278" fill="none"
              stroke="currentColor" stroke-width="1.4" marker-end="url(#f-arrow)" />
        <text x="255" y="240" text-anchor="middle" font-size="12" fill="currentColor" font-weight="700">no</text>

        <path d="M 534,196 C 660,250 780,300 800,360" fill="none"
              stroke="currentColor" stroke-width="1.4" stroke-dasharray="1 5"
              stroke-linecap="round" marker-end="url(#f-arrow)" />
        <text x="705" y="252" text-anchor="middle" font-size="12" fill="currentColor" font-weight="700">sí</text>
        <text x="742" y="332" text-anchor="middle" font-size="11.5" class="v2-sub">entra directo al área</text>
        <text x="742" y="347" text-anchor="middle" font-size="11.5" class="v2-sub">guardada, sin pasar por</text>
        <text x="742" y="362" text-anchor="middle" font-size="11.5" class="v2-sub">cliente_final de nuevo</text>

        <rect x="140" y="278" width="280" height="104" rx="10"
              fill="var(--v2-line-soft)" stroke="var(--v2-ink)" stroke-width="1.6" />
        <rect x="140" y="278" width="6" height="104" fill="var(--v2-ink)" />
        <text x="166" y="316" font-size="16" font-weight="700" style="fill:var(--v2-ink)">cliente_final</text>
        <text x="166" y="338" font-size="13.5" class="v2-sub">recepción — saluda y</text>
        <text x="166" y="356" font-size="13.5" class="v2-sub">verifica identidad</text>

        <path d="M 148,278 C 110,240 110,220 158,214" fill="none"
              class="v2-sub" stroke="currentColor" stroke-width="1.2" stroke-dasharray="3 4" marker-end="url(#f-arrow)" />
        <text x="60" y="238" font-size="11" class="v2-sub">tema aún</text>
        <text x="60" y="252" font-size="11" class="v2-sub">no claro</text>

        <path d="M 220,382 C 200,415 160,428 160,430" fill="none"
              style="stroke:var(--v2-moss)" stroke-width="1.6" marker-end="url(#f-arrow-moss)" />
        <text x="30" y="405" font-size="11.5" style="fill:var(--v2-moss)" font-weight="700">derivar_a_area(facturación)</text>
        <text x="30" y="420" font-size="11" class="v2-sub">misma llamada, sin turno extra</text>

        <path d="M 340,382 C 400,415 460,428 480,430" fill="none"
              style="stroke:var(--v2-clay)" stroke-width="1.6" marker-end="url(#f-arrow-clay)" />
        <text x="490" y="405" font-size="11.5" style="fill:var(--v2-clay)" font-weight="700">derivar_a_area(soporte)</text>
        <text x="490" y="420" font-size="11" class="v2-sub">misma llamada, sin turno extra</text>

        <rect x="20" y="432" width="300" height="106" rx="10"
              fill="color-mix(in srgb, var(--v2-moss) 10%, transparent)" stroke="var(--v2-moss)" stroke-width="1.6" />
        <rect x="20" y="432" width="6" height="106" fill="var(--v2-moss)" />
        <text x="46" y="470" font-size="15.5" font-weight="700" style="fill:var(--v2-moss)">facturacion_cliente</text>
        <text x="46" y="492" font-size="13.5" class="v2-sub">saldo · estado_facturas</text>
        <text x="46" y="510" font-size="13.5" class="v2-sub">fecha_corte — solo lectura</text>

        <rect x="480" y="432" width="320" height="106" rx="10"
              fill="color-mix(in srgb, var(--v2-clay) 10%, transparent)" stroke="var(--v2-clay)" stroke-width="1.6" />
        <rect x="480" y="432" width="6" height="106" fill="var(--v2-clay)" />
        <text x="506" y="470" font-size="15.5" font-weight="700" style="fill:var(--v2-clay)">soporte_tecnico_cliente</text>
        <text x="506" y="492" font-size="13.5" class="v2-sub">ping_cliente · manual (RAG)</text>
        <text x="506" y="510" font-size="13.5" class="v2-sub">checklist de diagnóstico</text>

        <path d="M 320,470 C 380,455 420,455 480,470" fill="none"
              class="v2-sub" stroke="currentColor" stroke-width="1.2" stroke-dasharray="3 4" marker-end="url(#f-arrow)" />
        <path d="M 480,490 C 420,505 380,505 320,490" fill="none"
              class="v2-sub" stroke="currentColor" stroke-width="1.2" stroke-dasharray="3 4" marker-end="url(#f-arrow)" />
        <text x="400" y="443" text-anchor="middle" font-size="11" class="v2-sub">cambia de tema</text>

        <path d="M 220,538 C 240,580 300,610 330,614" fill="none"
              style="stroke:var(--v2-rust)" stroke-width="1.4" stroke-dasharray="2 5" marker-end="url(#f-arrow-rust)" />
        <path d="M 620,538 C 590,580 500,610 470,614" fill="none"
              style="stroke:var(--v2-rust)" stroke-width="1.4" stroke-dasharray="2 5" marker-end="url(#f-arrow-rust)" />
        <text x="400" y="590" text-anchor="middle" font-size="11.5" style="fill:var(--v2-rust)">no se resuelve solo</text>

        <rect x="270" y="618" width="260" height="66" rx="10"
              fill="color-mix(in srgb, var(--v2-rust) 10%, transparent)" stroke="var(--v2-rust)" stroke-width="1.4"
              stroke-dasharray="4 3" />
        <text x="400" y="646" text-anchor="middle" font-size="14" font-weight="700" style="fill:var(--v2-rust)">Humano · BottleCRM</text>
        <text x="400" y="665" text-anchor="middle" font-size="12.5" class="v2-sub">escalamiento ya existente, sin cambios</text>

      </svg>
      <p class="v2-sub pie-figura">
        Enrutamiento de <b>cliente_final</b> hacia los especialistas, y de vuelta si el tema cambia o si
        ninguno puede resolverlo solo.
      </p>
    </div>

    <div class="v2-label" style="margin:22px 0 10px">Cómo leer los nodos</div>
    <div class="leyenda">
      <div class="leyenda-item">
        <span class="pastilla" style="background:var(--v2-ink)"></span>
        <div>
          <b>cliente_final</b>
          <span class="v2-sub"
            >Punto de entrada único. Saluda, verifica identidad, resuelve lo simple (saldo, estado) y
            decide cuándo derivar.</span
          >
        </div>
      </div>
      <div class="leyenda-item">
        <span class="pastilla" style="background:var(--v2-moss)"></span>
        <div>
          <b>facturacion_cliente</b>
          <span class="v2-sub"
            >Especialista de solo lectura. Ve el mismo servicio que cliente_final ya veía — nada nuevo
            que verificar.</span
          >
        </div>
      </div>
      <div class="leyenda-item">
        <span class="pastilla" style="background:var(--v2-clay)"></span>
        <div>
          <b>soporte_tecnico_cliente</b>
          <span class="v2-sub"
            >Sigue el checklist del manual (RAG) más a fondo que el chequeo rápido de cliente_final.</span
          >
        </div>
      </div>
      <div class="leyenda-item">
        <span class="pastilla" style="background:var(--v2-rust)"></span>
        <div>
          <b>Humano</b>
          <span class="v2-sub"
            >El camino de siempre (BottleCRM). No cambió — solo ahora hay menos casos que llegan hasta
            acá.</span
          >
        </div>
      </div>
    </div>

    <div class="v2-label" style="margin:22px 0 10px">Por qué no es un orquestador clásico</div>
    <div class="v2-card callout">
      <p class="veredicto">La derivación vive dentro del turno, no antes de él.</p>
      <p class="v2-sub">
        Un orquestador clásico clasifica el mensaje con un modelo aparte y recién después llama al
        especialista — dos llamadas en vez de una, en cada turno. Acá <code>derivar_a_area</code> es una
        herramienta más del tool-calling que <code>cliente_final</code> ya hacía: la decisión sale de la
        misma llamada, no de una extra.
      </p>
      <p class="v2-sub" style="margin-bottom:0">
        Y una vez derivada, la conversación no se reclasifica en cada mensaje —
        <code>rol_efectivo</code> queda escrito, así que el siguiente mensaje entra directo al especialista
        correcto.
      </p>
    </div>

    <div class="v2-label" style="margin:22px 0 10px">Verificado en vivo</div>
    <ul class="checks">
      <li>
        <span class="marca ok">✓</span>
        <span
          >Una pregunta simple de saldo la resuelve <code>cliente_final</code> mismo, sin derivar.
          <small class="v2-sub"
            >Confirma que no deriva de más — para lo simple, no vale la pena el salto.</small
          ></span
        >
      </li>
      <li>
        <span class="marca ok">✓</span>
        <span
          >Disputar un cobro deriva a <code>facturacion_cliente</code> con un aviso breve.
          <small class="v2-sub"
            >El cliente no vuelve a dar la cédula — la verificación viaja con la sesión, no con el rol.</small
          ></span
        >
      </li>
      <li>
        <span class="marca ok">✓</span>
        <span
          >Una falla que el chequeo básico no resuelve deriva a <code>soporte_tecnico_cliente</code>.
          <small class="v2-sub"
            >Sigue el checklist del manual con más profundidad que el primer chequeo de cliente_final.</small
          ></span
        >
      </li>
      <li>
        <span class="marca fix">!</span>
        <span
          >Reiniciar el motor a mitad de una conversación derivada podía confundir al especialista.
          <small class="v2-sub"
            >Sin historial en memoria, llegó a derivar mal una vez — corregido con una nota de continuidad
            que solo se agrega en ese caso puntual.</small
          ></span
        >
      </li>
    </ul>
  </div>
</div>

<style>
  .diagrama-card {
    padding: 24px 16px 14px;
    overflow-x: auto;
  }
  .diagrama {
    width: 100%;
    min-width: 640px;
    height: auto;
    display: block;
    color: var(--v2-ink);
  }
  .pie-figura {
    font-size: 12.5px;
    margin: 14px 0 0;
    padding-top: 12px;
    border-top: 1px dashed var(--v2-line);
    min-width: 640px;
  }

  .leyenda {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: 10px;
  }
  .leyenda-item {
    display: flex;
    gap: 12px;
    align-items: flex-start;
    background: var(--v2-line-soft);
    border: 1px solid var(--v2-line);
    border-radius: var(--v2-radius);
    padding: 14px 16px;
  }
  .pastilla {
    flex: none;
    width: 12px;
    height: 12px;
    border-radius: 3px;
    margin-top: 5px;
  }
  .leyenda-item b {
    display: block;
    font-size: 13.5px;
    margin-bottom: 3px;
  }
  .leyenda-item span {
    font-size: 13px;
    line-height: 1.45;
  }

  .callout {
    padding: 18px 22px;
    border-left: 3px solid var(--v2-ink);
    border-radius: 4px var(--v2-radius) var(--v2-radius) 4px;
  }
  .callout p {
    margin: 0 0 10px;
    font-size: 13.5px;
    line-height: 1.55;
  }
  .callout p:last-child {
    margin-bottom: 0;
  }
  .veredicto {
    font-weight: 700;
    font-size: 14.5px;
    color: var(--v2-ink);
    margin: 0 0 8px;
  }
  .callout code {
    font-size: 0.92em;
    background: var(--v2-line-soft);
    padding: 0.1em 0.4em;
    border-radius: 4px;
  }

  .checks {
    list-style: none;
    margin: 0;
    padding: 0;
    display: grid;
    gap: 10px;
  }
  .checks li {
    display: flex;
    gap: 12px;
    align-items: baseline;
    font-size: 14px;
  }
  .checks small {
    display: block;
    font-size: 12px;
    margin-top: 2px;
  }
  .marca {
    flex: none;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    font-size: 11.5px;
    font-weight: 700;
    transform: translateY(2px);
  }
  .marca.ok {
    background: color-mix(in srgb, var(--v2-moss) 15%, transparent);
    color: var(--v2-moss);
  }
  .marca.fix {
    background: color-mix(in srgb, var(--v2-rust) 15%, transparent);
    color: var(--v2-rust);
  }

/* El check y el texto de "que atiende" son una unidad: si estan sueltos,
     no se lee que el segundo solo tiene sentido cuando el primero esta
     marcado. */
  .agente-fila {
    display: flex;
    flex-direction: column;
    gap: 7px;
    padding: 12px 0;
  }
  .agente-fila + .agente-fila {
    border-top: 1px solid var(--v2-line-soft);
  }
  .agente-check {
    display: flex;
    align-items: center;
    gap: 9px;
    cursor: pointer;
  }
  .agente-check input {
    accent-color: var(--v2-ink);
  }
  /* Indentado bajo su check, para que se lea como dependiente de el. */
  .agente-atiende {
    margin-left: 25px;
    font-size: 12.5px;
  }
  .aviso-mudo {
    display: flex;
    align-items: flex-start;
    gap: 6px;
    margin: 12px 0 0;
    font-size: 11.5px;
    line-height: 1.5;
    color: var(--v2-clay);
  }
  .ok-guardado {
    display: flex;
    align-items: center;
    gap: 5px;
    margin: 12px 0 0;
    font-size: 12px;
    color: var(--v2-moss);
    font-weight: 550;
  }
</style>
