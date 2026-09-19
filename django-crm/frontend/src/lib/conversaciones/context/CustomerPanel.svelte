<script>
  /**
   * Quién es el cliente, con lo que Dexter efectivamente sabe.
   *
   * LO QUE NO ESTÁ, Y POR QUÉ. La referencia de diseño muestra también
   * dirección, plan, velocidades, saldo y últimas facturas — y marca casi
   * todos esos campos como MOCK. No están acá porque Dexter **no los guarda**:
   * las respuestas de la API del ISP no se persisten (PRD RNF-01; traen
   * contraseñas, GPS y cédula). Traerlos en vivo al abrir la pantalla
   * convertiría a este panel en una segunda fuente de verdad y metería PII del
   * cliente donde hoy no la hay. Es una decisión, no una omisión: se dice en
   * pantalla en vez de dejar cuatro secciones vacías.
   *
   * Lo que sí consta viene de la verificación de identidad, dentro de esta
   * conversación:
   *
   *   nombre_cliente · id_cliente   la persona, si se verificó
   *   equipo                        identificadores TÉCNICOS de su equipo
   *                                 (Sesion.CAMPOS_PERSISTIBLES), filtrados
   *                                 por el motor
   *
   * `id_cliente` es además la señal de que hubo verificación: los campos
   * técnicos sólo se escriben al verificar, y verificar exige id_cliente.
   */
  import { ShieldCheck, ShieldQuestion } from '@lucide/svelte';

  let { conversacion } = $props();

  const ROTULO_EQUIPO = {
    sn_onu: 'Serial de la ONU',
    interfaz_lan: 'Interfaz'
  };

  const verificado = $derived(!!conversacion?.id_cliente);
  const equipo = $derived(Object.entries(conversacion?.equipo ?? {}).filter(([, v]) => v));

  // Mismo criterio que el encabezado: diez dígitos seguidos no se leen.
  function telefono(v) {
    const crudo = (v ?? '').toString();
    const d = crudo.replace(/\D/g, '');
    if (/^\+?\d[\d\s-]{5,}$/.test(crudo) && d.length === 10) {
      return `${d.slice(0, 3)} ${d.slice(3, 6)} ${d.slice(6)}`;
    }
    return crudo;
  }
  // Un BSUID de WhatsApp no es un teléfono y no hay que mostrarlo como tal.
  const esIdOpaco = $derived(
    !!conversacion?.usuario_externo && !/^\+?\d[\d\s-]{5,}$/.test(conversacion.usuario_externo)
  );
</script>

<section class="cliente">
  <p class="bloque-titulo">Cliente</p>

  <p class="verificacion" class:v-si={verificado} class:v-no={!verificado}>
    {#if verificado}
      <ShieldCheck size={13} />
      <span>Identidad verificada en esta conversación</span>
    {:else}
      <ShieldQuestion size={13} />
      <!-- No es una falta: la mayoría de las consultas no necesitan
           verificar. Lo que no se puede es tratar los datos como confirmados. -->
      <span>Sin verificar — nada de lo de abajo está confirmado</span>
    {/if}
  </p>

  {#if conversacion?.nombre_cliente}
    <div class="campo">
      <span class="v2-sub">Nombre</span>
      <span class="dato">{conversacion.nombre_cliente}</span>
    </div>
  {/if}

  <div class="campo">
    <span class="v2-sub">{esIdOpaco ? 'Identificador del canal' : 'Teléfono'}</span>
    {#if conversacion?.usuario_externo}
      <span class="dato mono">{telefono(conversacion.usuario_externo)}</span>
    {:else}
      <span class="v2-muted">Sin identificar</span>
    {/if}
  </div>

  {#if conversacion?.id_cliente}
    <div class="campo">
      <span class="v2-sub">Cliente en el ISP</span>
      <span class="dato mono">{conversacion.id_cliente}</span>
    </div>
  {/if}

  {#if equipo.length > 0}
    <p class="bloque-titulo separado">Equipo</p>
    {#each equipo as [clave, valor] (clave)}
      <div class="campo">
        <!-- Si el tenant captura un campo nuevo, aparece con su clave cruda en
             vez de no aparecer: el motor ya lo manda, y esconderlo sería
             perder un dato que alguien fue a buscar. -->
        <span class="v2-sub">{ROTULO_EQUIPO[clave] ?? clave.replaceAll('_', ' ')}</span>
        <span class="dato mono">{valor}</span>
      </div>
    {/each}
  {/if}

  <p class="nota-fuente">
    Dexter guarda de cada cliente lo que hizo falta para atenderlo: su identidad
    y los identificadores de su equipo. El plan, la dirección, el saldo y las
    facturas viven en el sistema del ISP y no se traen acá.
  </p>
</section>

<style>
  .cliente {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding-bottom: 16px;
    border-bottom: 1px solid var(--v2-line-soft);
  }

  .bloque-titulo {
    margin: 0;
    font-family: var(--bandeja-mono);
    font-size: 9.5px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--bandeja-texto-2);
  }
  .separado {
    margin-top: 4px;
    padding-top: 12px;
    border-top: 1px solid var(--bandeja-borde);
  }

  .verificacion {
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 0;
    padding: 5px 8px;
    border: 1px solid;
    border-radius: var(--bandeja-radio-sm);
    font-size: 11.5px;
    line-height: 1.35;
  }
  .verificacion :global(svg) {
    flex: none;
  }
  .v-si {
    color: var(--bandeja-ok);
    background: color-mix(in srgb, var(--bandeja-ok) 8%, transparent);
    border-color: color-mix(in srgb, var(--bandeja-ok) 30%, transparent);
  }
  /* Ámbar y no rojo: no verificar no es un error ni una falta del operador.
     La mayoría de las consultas no lo necesitan. */
  .v-no {
    color: var(--bandeja-aviso);
    background: var(--bandeja-aviso-fondo);
    border-color: var(--bandeja-aviso-borde);
  }

  .campo {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 3px;
  }
  .campo > .v2-sub {
    font-size: 11.5px;
  }

  .dato {
    font-size: 13px;
    color: var(--bandeja-texto);
    max-width: 100%;
    overflow-wrap: anywhere;
  }
  /* Los identificadores técnicos en mono y con cifras tabulares: se comparan
     contra otro sistema carácter por carácter. */
  .mono {
    font-family: var(--bandeja-mono);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
  }

  .nota-fuente {
    margin: 2px 0 0;
    font-size: 11px;
    line-height: 1.45;
    color: var(--bandeja-texto-2);
  }
</style>
