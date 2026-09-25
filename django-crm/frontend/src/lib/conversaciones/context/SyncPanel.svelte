<script>
  /**
   * Qué quedó sin hacer afuera de Dexter (B4).
   *
   * Escalar produce un caso en el CRM y, cuando corresponde, un ticket en el
   * sistema del ISP. Si alguno falla, antes se perdía en el log: la
   * conversación quedaba escalada, visible en la bandeja, y sin caso — y nadie
   * se enteraba hasta que alguien lo buscaba a mano.
   *
   * ES UN PANEL APARTE, NO UNA LÍNEA EN ACTIVITY, a propósito: Activity es
   * historia —qué pasó— y esto es estado actual —qué falta—. Un pendiente de
   * revisión enterrado entre movimientos del relevo se lee como algo que ya
   * ocurrió y se cerró.
   *
   * SIN BOTÓN DE REINTENTAR, también a propósito. Lo que está `desconocida` no
   * se reintenta porque nadie puede saber si ya se hizo; un botón invitaría
   * exactamente al gesto que el gate Q2 prohíbe — y dos visitas técnicas al
   * mismo cliente no se deshacen.
   */
  import { TriangleAlert, CircleCheck, CircleX, Clock, CircleHelp } from '@lucide/svelte';
  import {
    lineaDeSincronizacion, loQueEsperaRevision, hayQueRevisar
  } from '$lib/conversaciones/sincronizacion.js';

  let { sincronizaciones = [] } = $props();

  // Lo ya hecho no se muestra: el panel dice qué FALTA. Si no falta nada, no
  // hay panel, y eso es información -- no un hueco.
  const faltan = $derived(loQueEsperaRevision(sincronizaciones));
  const lineas = $derived(faltan.map(lineaDeSincronizacion));
  const urgente = $derived(hayQueRevisar(sincronizaciones));

  function cuando(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return Number.isNaN(d.getTime())
      ? ''
      : d.toLocaleString('es-CO', {
          day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'
        });
  }
</script>

{#if lineas.length > 0}
  <section class="sync" class:sync-revisar={urgente}>
    <p class="panel-titulo">
      Sincronización externa
      {#if urgente}<span class="marca-revisar">· requiere revisión</span>{/if}
    </p>

    <ul class="efectos">
      {#each lineas as l, i (i)}
        <li class="efecto efecto-{l.tono}">
          <span class="icono" aria-hidden="true">
            {#if l.clave === 'hecha'}<CircleCheck size={14} />
            {:else if l.clave === 'fallida'}<CircleX size={14} />
            {:else if l.clave === 'desconocida'}<TriangleAlert size={14} />
            {:else if l.clave === 'pendiente' || l.clave === 'en_curso'}<Clock size={14} />
            {:else}<CircleHelp size={14} />{/if}
          </span>
          <div class="cuerpo">
            <p class="nombre">{l.nombre}</p>
            <p class="estado">{l.texto}</p>
            {#if l.detalle}<p class="detalle">{l.detalle}</p>{/if}
            <p class="cuando">
              <time datetime={l.cuando}>{cuando(l.cuando)}</time>{#if l.intentos}
                · {l.intentos}{/if}
            </p>
          </div>
        </li>
      {/each}
    </ul>

    <p class="panel-nota">
      Dexter reintenta solo lo que puede repetirse sin riesgo. Lo que quedó sin
      confirmar no se reintenta: hay que comprobarlo en el sistema externo antes
      de volver a hacerlo.
    </p>
  </section>
{/if}

<style>
  .sync {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--v2-line-soft);
  }

  .marca-revisar {
    color: var(--bandeja-aviso);
  }

  .efectos {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .efecto {
    display: flex;
    gap: 8px;
    padding: 8px 9px;
    border: 1px solid var(--bandeja-borde);
    border-radius: var(--bandeja-radio-sm);
  }
  .icono {
    flex: none;
    margin-top: 1px;
    color: var(--bandeja-texto-3);
  }
  .efecto-ok .icono {
    color: var(--bandeja-ok);
  }
  .efecto-mal .icono {
    color: var(--bandeja-error);
  }
  /* Ámbar y no rojo: «no sabemos» no es «falló». Pintarlo de rojo empujaría a
     rehacerlo, que es justo lo que no se puede. */
  .efecto-aviso {
    border-color: var(--bandeja-aviso-borde);
    background: var(--bandeja-aviso-fondo);
  }
  .efecto-aviso .icono {
    color: var(--bandeja-aviso);
  }

  .cuerpo {
    min-width: 0;
  }
  .nombre {
    margin: 0;
    font-size: 12.5px;
    font-weight: 600;
    color: var(--bandeja-texto);
  }
  .estado {
    margin: 2px 0 0;
    font-size: 12px;
    line-height: 1.4;
    color: var(--bandeja-texto);
  }
  .detalle {
    margin: 3px 0 0;
    font-size: 11px;
    line-height: 1.4;
    color: var(--bandeja-texto-2);
  }
  .cuando {
    margin: 3px 0 0;
    font-family: var(--bandeja-mono);
    font-size: 10px;
    color: var(--bandeja-texto-3);
  }
</style>
