import 'package:flutter/material.dart';

import '../../../demo/field_mock_data.dart';
import '../../../core/theme/app_theme.dart';
import '../estado_trabajo.dart';
import '../trabajo_vista.dart';

/// Un trabajo en la lista, con las variantes del diseño de Stitch.
///
/// La forma cambia según en qué anda el trabajo, igual que en las maquetas:
///
/// * **en curso** — cinta de estado, telemetría y el botón grande de continuar;
/// * **pendiente** — etiquetas del plan y dos acciones, detalles y llegada;
/// * **incidencia** — prioridad, nodo y el diagnóstico previo;
/// * **terminado** — marca de guardado y acceso a la ficha.
///
/// Los datos reales van siempre. Los que el backend todavía no entrega —SLA,
/// zona, distancia, telemetría, plan contratado— solo aparecen con el modo
/// demostración encendido, y cada uno lleva su `CAMPO-DATA-XXX`.
class TarjetaTrabajo extends StatefulWidget {
  const TarjetaTrabajo({
    super.key,
    required this.trabajo,
    this.onTap,
    this.mostrarDatosFuturos = FieldMockData.modoDemo,
  });

  final TrabajoVista trabajo;
  final VoidCallback? onTap;
  final bool mostrarDatosFuturos;

  @override
  State<TarjetaTrabajo> createState() => _TarjetaTrabajoState();
}

class _TarjetaTrabajoState extends State<TarjetaTrabajo> {
  /// Los datos de abajo empiezan plegados a propósito: la lista es para
  /// decidir a cuál orden ir, no para leerla entera. Lo que hace falta para
  /// esa decisión va arriba; el resto se pide.
  bool _desplegado = false;

  TrabajoVista get trabajo => widget.trabajo;
  VoidCallback? get onTap => widget.onTap;
  bool get mostrarDatosFuturos => widget.mostrarDatosFuturos;

  bool get _enCurso => trabajo.estado.enMarcha;
  bool get _terminado => trabajo.estado.terminada;
  bool get _incidencia => trabajo.familia == FamiliaTrabajo.incidencia;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Container(
        decoration: BoxDecoration(
          color: AppColors.surfaceContainerLowest,
          borderRadius: AppRadius.brTarjeta,
          boxShadow: _enCurso ? AppTheme.sombraNivel2 : AppTheme.sombraNivel1,
        ),
        clipBehavior: Clip.antiAlias,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            _cintaSuperior(),
            Padding(
              padding: const EdgeInsets.all(AppSpacing.md),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  if (_incidencia) ..._cuerpoIncidencia() else ..._cuerpoTrabajo(),
                  const SizedBox(height: AppSpacing.md),
                  _acciones(),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  // --- Cinta superior ------------------------------------------------------

  Widget _cintaSuperior() {
    final (IconData icono, String titulo) = switch (trabajo.familia) {
      FamiliaTrabajo.instalacion => (
          Icons.add_circle,
          'INSTALACIÓN${trabajo.numero == null ? '' : ' #${trabajo.numero}'}'
        ),
      FamiliaTrabajo.incidencia => (
          Icons.confirmation_number,
          'TICKET${trabajo.numero == null ? '' : ' #${trabajo.numero}'} · INCIDENCIA NOC'
        ),
      FamiliaTrabajo.mantenimiento => (
          Icons.build_circle,
          'OT${trabajo.numero == null ? '' : ' #${trabajo.numero}'} · MANTENIMIENTO'
        ),
      FamiliaTrabajo.otro => (
          _terminado ? Icons.cloud_done : Icons.build,
          'OT${trabajo.numero == null ? '' : ' #${trabajo.numero}'}'
              '${trabajo.tipoNombre.isEmpty ? '' : ' · ${trabajo.tipoNombre.toUpperCase()}'}'
        ),
    };

    final Color colorTexto = _enCurso ? AppColors.onPrimary : _colorFamilia;

    return Container(
      color: _enCurso ? AppColors.primary : AppColors.surfaceContainerLowest,
      padding: EdgeInsets.fromLTRB(
        AppSpacing.md,
        AppSpacing.sm,
        AppSpacing.md,
        _enCurso ? AppSpacing.sm : 0,
      ),
      child: Row(
        children: <Widget>[
          Icon(icono, size: 16, color: colorTexto),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              titulo,
              style: AppTypography.etiquetaChica.copyWith(
                color: colorTexto,
                fontWeight: FontWeight.w700,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          if (!_enCurso) ...<Widget>[
            _pastillaOffline(),
            const SizedBox(width: 6),
          ],
          _pastillaEstado(),
        ],
      ),
    );
  }

  /// La ficha ya está en el teléfono. No es un dato de ejemplo: todo lo que se
  /// lista salió de la base local, así que se puede abrir sin señal.
  Widget _pastillaOffline() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm, vertical: 4),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainer,
        borderRadius: BorderRadius.circular(AppRadius.circulo),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          const Icon(Icons.offline_pin, size: 12, color: AppColors.onSurfaceVariant),
          const SizedBox(width: 4),
          Text(
            'Cacheada',
            style: AppTypography.etiquetaChica.copyWith(
              color: AppColors.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }

  Color get _colorFamilia => switch (trabajo.familia) {
        FamiliaTrabajo.instalacion => AppColors.primary,
        FamiliaTrabajo.incidencia => AppColors.error,
        FamiliaTrabajo.mantenimiento => AppColors.onSurfaceVariant,
        FamiliaTrabajo.otro => AppColors.primary,
      };

  Widget _pastillaEstado() {
    final (Color fondo, Color texto) = switch (trabajo.estado) {
      EstadoTrabajo.enCamino || EstadoTrabajo.enSitio => (
          AppColors.surfaceBright,
          AppColors.onSurface
        ),
      EstadoTrabajo.completadaCampo ||
      EstadoTrabajo.completadaSinEnviar ||
      EstadoTrabajo.cerrada =>
        (AppColors.exito, AppColors.exito),
      EstadoTrabajo.correccionRequerida || EstadoTrabajo.cancelada => (
          AppColors.errorContainer,
          AppColors.onErrorContainer
        ),
      _ => (AppColors.surfaceContainerHighest, AppColors.onSurfaceVariant),
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm, vertical: 4),
      decoration: BoxDecoration(
        color: fondo,
        borderRadius: BorderRadius.circular(AppRadius.circulo),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (_enCurso) ...<Widget>[
            Container(
              width: 8,
              height: 8,
              decoration: const BoxDecoration(
                color: AppColors.secondaryContainer,
                shape: BoxShape.circle,
              ),
            ),
            const SizedBox(width: 6),
          ],
          Text(
            trabajo.estado.etiqueta,
            style: AppTypography.etiquetaChica.copyWith(color: texto),
          ),
        ],
      ),
    );
  }

  // --- Cuerpo de un trabajo normal ----------------------------------------

  List<Widget> _cuerpoTrabajo() {
    return <Widget>[
      // De qué ticket nació esta orden. El backend lo entrega desde el
      // 22/09/2026 (`origen`); el motivo todavía no existe, así que solo se
      // agrega en la demostración (CAMPO-DATA-029).
      if (_enCurso && (trabajo.origen != null || mostrarDatosFuturos)) ...<Widget>[
        const SizedBox(height: AppSpacing.sm),
        _aviso(
          icono: Icons.alt_route,
          texto: trabajo.origen == null
              ? 'Derivado de ${_ejemplo.ticketOrigen} '
                  '(${_ejemplo.motivoTicket})'
              : 'Derivado de ${trabajo.origen!.etiqueta}'
                  '${mostrarDatosFuturos ? ' (${_ejemplo.motivoTicket})' : ''}',
          color: AppColors.onSurfaceVariant,
          fondo: AppColors.surfaceContainer,
        ),
      ],
      const SizedBox(height: AppSpacing.sm),
      Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Expanded(
            child: Text(
              trabajo.clienteNombre,
              style: AppTypography.tituloChico.copyWith(fontWeight: FontWeight.w700),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          if (trabajo.compromiso != null || mostrarDatosFuturos)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 3),
              decoration: const BoxDecoration(
                color: AppColors.surfaceContainerHigh,
                borderRadius: AppRadius.brChico,
              ),
              child: Text(
                'Ventana: ${_ventana(trabajo)}',
                style: AppTypography.etiquetaChica,
              ),
            ),
        ],
      ),
      const SizedBox(height: AppSpacing.xs),
      Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Icon(Icons.pin_drop, size: 16, color: AppColors.onSurfaceVariant),
          const SizedBox(width: 6),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  trabajo.direccion,
                  style: AppTypography.cuerpo,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
                // Cómo se entra al inmueble. Real cuando el despacho lo
                // cargó; de ejemplo solo en la demostración (CAMPO-DATA-041).
                if (trabajo.detalleAcceso.isNotEmpty || mostrarDatosFuturos)
                  Text(
                    'Detalle acceso: '
                    '${trabajo.detalleAcceso.isEmpty ? FieldMockData.detalleAcceso : trabajo.detalleAcceso}',
                    style: AppTypography.etiquetaChica,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
              ],
            ),
          ),
        ],
      ),
      if (trabajo.tipoNombre.isNotEmpty) ...<Widget>[
        const SizedBox(height: AppSpacing.xs),
        Text(
          trabajo.tipoNombre,
          style: AppTypography.cuerpoChico,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
      ],
      if (trabajo.requiereActualizacion) ...<Widget>[
        const SizedBox(height: AppSpacing.sm),
        _aviso(
          icono: Icons.system_update,
          texto: trabajo.versionEsquemaConocida
              ? 'Necesita una versión más nueva de la aplicación'
              : 'Todavía no sabemos qué versión necesita: falta bajar el detalle',
          color: AppColors.onErrorContainer,
          fondo: AppColors.errorContainer,
        ),
      ],
      if (mostrarDatosFuturos) ...<Widget>[
        const SizedBox(height: AppSpacing.sm),
        // CAMPO-DATA-005
        Row(
          children: <Widget>[
            const Icon(Icons.navigation, size: 14, color: AppColors.secondary),
            const SizedBox(width: 6),
            Text(
              '${_ejemplo.distanciaKm.toStringAsFixed(1)} km de tu posición',
              style: AppTypography.etiquetaChica.copyWith(color: AppColors.secondary),
            ),
            const SizedBox(width: 6),
            Text('•', style: AppTypography.etiquetaChica),
            const SizedBox(width: 6),
            Text(
              'Est. arribo: ${_ejemplo.minutosDeViaje} min',
              style: AppTypography.etiquetaChica,
            ),
          ],
        ),
        if (_enCurso) ...<Widget>[
          const SizedBox(height: AppSpacing.sm),
          _cajaTelemetria(),
        ],
        if (!_enCurso && !_terminado) ...<Widget>[
          const SizedBox(height: AppSpacing.sm),
          _etiquetasDelPlan(),
        ],
      ],
      // CAMPO-DATA-045 · Lo que hay que llevar puesto para poder hacerlo.
      if (_pideAlturas) ...<Widget>[
        const SizedBox(height: AppSpacing.sm),
        _avisoSeguridad(),
      ],
      // CAMPO-DATA-046 · Cómo cerró el trabajo.
      if (_terminado && mostrarDatosFuturos) ...<Widget>[
        const SizedBox(height: AppSpacing.sm),
        _aviso(
          icono: Icons.verified,
          texto: '${FieldMockData.actaEstado} · Potencia final '
              '${FieldMockData.actaPotenciaFinal}',
          color: AppColors.exitoTexto,
          fondo: AppColors.exitoFondo,
        ),
      ],
      if (_terminado && mostrarDatosFuturos) ...<Widget>[
        const SizedBox(height: AppSpacing.sm),
        _aviso(
          icono: Icons.cloud_done,
          texto: 'Sincronizado con Dexter Server',
          color: AppColors.onSurfaceVariant,
          fondo: AppColors.surfaceContainer,
        ),
      ],
    ];
  }

  // --- Cuerpo de una incidencia -------------------------------------------

  List<Widget> _cuerpoIncidencia() {
    return <Widget>[
      const SizedBox(height: AppSpacing.sm),

      // 1 · RAZON DE FALLA. Es el asunto del ticket (`resumen`), no el tipo de
      //     trabajo: "No Tiene Internet" dice por que lo llamaron; "Reparacion
      //     de Senal (FTTH)" dice que plantilla se usa. Si el asunto no llego,
      //     el tipo es lo mejor que hay.
      Text(
        trabajo.resumen.isNotEmpty ? trabajo.resumen : trabajo.tipoNombre,
        style: AppTypography.tituloChico.copyWith(fontWeight: FontWeight.w700),
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
      ),

      // 2 · PRIORIDAD. Dos, y no una: la que calcula Dexter va con peso, la
      //     del proveedor al lado y en chico. Mezclarlas haria que la pantalla
      //     afirme un analisis que hoy no ocurre.
      const SizedBox(height: AppSpacing.sm),
      _prioridades(),

      // 2b · POR QUE esa prioridad. Sin motivos la etiqueta es un adorno, asi
      //      que cuando los haya van pegados a ella y no escondidos abajo.
      if (trabajo.motivosPrioridad.isNotEmpty) ...<Widget>[
        const SizedBox(height: AppSpacing.xs),
        Text(
          trabajo.motivosPrioridad.join(' · '),
          style: AppTypography.etiquetaChica.copyWith(
            color: AppColors.onSurfaceVariant,
          ),
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
      ],

      // 3 · CLIENTE.
      const SizedBox(height: AppSpacing.sm),
      _dato(
        icono: Icons.person_outline,
        valor: trabajo.clienteNombre,
        vacio: 'Cliente no identificado',
        fuerte: true,
      ),

      // 4 · DIRECCION.
      const SizedBox(height: AppSpacing.xs),
      _dato(
        icono: Icons.pin_drop,
        valor: trabajo.direccion,
        vacio: 'Sin direccion',
      ),
      // El diagnóstico sí es real: lo manda el backend.
      if (trabajo.diagnosticoPrevio.isNotEmpty) ...<Widget>[
        const SizedBox(height: AppSpacing.sm),
        Container(
          padding: const EdgeInsets.all(AppSpacing.sm),
          decoration: BoxDecoration(
            color: AppColors.surfaceContainerLow,
            borderRadius: AppRadius.brCampo,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Row(
                children: <Widget>[
                  const Icon(Icons.query_stats, size: 14, color: AppColors.secondary),
                  const SizedBox(width: 6),
                  Text(
                    'DIAGNÓSTICO DEXTER INTELIGENTE',
                    style: AppTypography.etiquetaChica.copyWith(
                      color: AppColors.secondary,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 4),
              Text(trabajo.diagnosticoPrevio, style: AppTypography.cuerpoChico),
            ],
          ),
        ),
      ],

      // 5 · El resto, plegado.
      const SizedBox(height: AppSpacing.sm),
      _botonDesplegar(),
      if (_desplegado) ...<Widget>[
        const SizedBox(height: AppSpacing.sm),
        _masDatos(),
      ],
    ];
  }

  // --- Las dos prioridades -------------------------------------------------

  /// La de Dexter con peso, la del proveedor en chico.
  ///
  /// Hoy Dexter **no calcula** prioridad: el campo lo pone quien despacha y su
  /// default es 'media'. Mostrar eso como juicio seria presentar una copia
  /// disfrazada de analisis, que es contra lo que advierte el importador del
  /// motor. Hasta que calcule, dice 'sin evaluar'.
  Widget _prioridades() {
    final bool evaluada = trabajo.prioridadEvaluadaPorDexter;
    final (Color fondo, Color color, String texto) = evaluada
        ? _pintaPrioridad(trabajo.prioridad)
        : (AppColors.surfaceContainer, AppColors.onSurfaceVariant, 'Sin evaluar');

    return Row(
      children: <Widget>[
        Container(
          padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.sm, vertical: 6),
          decoration: BoxDecoration(color: fondo, borderRadius: AppRadius.brCampo),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(evaluada ? Icons.priority_high : Icons.help_outline,
                  size: 15, color: color),
              const SizedBox(width: 6),
              Text(
                texto.toUpperCase(),
                style: AppTypography.etiqueta.copyWith(
                  color: color,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
        ),
        if (trabajo.prioridadProveedor.isNotEmpty) ...<Widget>[
          const SizedBox(width: AppSpacing.sm),
          Flexible(
            child: Text(
              'WispHub: ${trabajo.prioridadProveedor}',
              style: AppTypography.etiquetaChica.copyWith(
                color: AppColors.onSurfaceVariant,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ],
    );
  }

  (Color, Color, String) _pintaPrioridad(String p) => switch (p) {
        'muy_alta' => (AppColors.errorContainer, AppColors.error, 'Muy alta'),
        'alta' => (AppColors.errorContainer, AppColors.onErrorContainer, 'Alta'),
        'baja' => (AppColors.surfaceContainer, AppColors.onSurfaceVariant, 'Baja'),
        _ => (AppColors.surfaceContainerHigh, AppColors.onSurface, 'Media'),
      };

  // --- Un dato, o por que no esta ------------------------------------------

  /// Un dato que puede no venir. El vacio se dibuja distinto del valor, no se
  /// esconde: que falte es el caso NORMAL —medido por el motor: 45 de 85
  /// conversaciones con cliente identificado— y una tarjeta que solo se ve
  /// bien llena esta a medio hacer.
  Widget _dato({
    required IconData icono,
    required String valor,
    required String vacio,
    bool fuerte = false,
  }) {
    final bool hay = valor.trim().isNotEmpty;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Icon(icono,
            size: 16,
            color: hay ? AppColors.onSurfaceVariant : AppColors.outline),
        const SizedBox(width: 6),
        Expanded(
          child: Text(
            hay ? valor : vacio,
            style: (fuerte ? AppTypography.cuerpo : AppTypography.cuerpoChico)
                .copyWith(
              color: hay ? AppColors.onSurface : AppColors.outline,
              fontWeight: hay && fuerte ? FontWeight.w600 : FontWeight.w400,
              fontStyle: hay ? FontStyle.normal : FontStyle.italic,
            ),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ],
    );
  }

  // --- El desplegable ------------------------------------------------------

  Widget _botonDesplegar() {
    return InkWell(
      onTap: () => setState(() => _desplegado = !_desplegado),
      borderRadius: AppRadius.brCampo,
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 6),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            Text(
              _desplegado ? 'Menos datos' : 'Mas datos',
              style: AppTypography.etiqueta.copyWith(
                color: AppColors.primary,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(width: 4),
            Icon(_desplegado ? Icons.expand_less : Icons.expand_more,
                size: 18, color: AppColors.primary),
          ],
        ),
      ),
    );
  }

  Widget _masDatos() {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.sm),
      decoration: BoxDecoration(
        color: AppColors.surfaceContainerLow,
        borderRadius: AppRadius.brCampo,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          // Cuando no hay ficha, decir POR QUE. 'No se pudo preguntar' y 'se
          // pregunto y no se pudo identificar al cliente' se arreglan distinto:
          // una se reintenta, la otra se resuelve hablando con la persona.
          if (!trabajo.contextoDisponible) ...<Widget>[
            _aviso(
              icono: trabajo.motorAlcanzado ? Icons.person_off : Icons.cloud_off,
              texto: trabajo.motorAlcanzado
                  ? 'Sin ficha: no se pudo identificar al cliente'
                  : 'Sin ficha: no se pudo consultar. Se reintenta al sincronizar',
              color: AppColors.onSurfaceVariant,
              fondo: AppColors.surfaceContainer,
            ),
            const SizedBox(height: AppSpacing.sm),
          ],
          _dato(icono: Icons.router, valor: trabajo.ipCliente, vacio: 'IP no disponible'),
          const SizedBox(height: AppSpacing.xs),
          _dato(
            icono: Icons.account_circle_outlined,
            valor: trabajo.estadoCuenta,
            vacio: 'Estado de cuenta no disponible',
          ),
          const SizedBox(height: AppSpacing.xs),
          _dato(icono: Icons.call, valor: trabajo.telefono, vacio: 'Sin telefono'),
          const SizedBox(height: AppSpacing.xs),
          _dato(
            icono: Icons.map_outlined,
            valor: trabajo.localidadCliente,
            vacio: 'Localidad no disponible',
          ),
        ],
      ),
    );
  }

  // --- Piezas --------------------------------------------------------------

  /// CAMPO-DATA-001 y CAMPO-DATA-011: la topología y la señal del cliente.
  Widget _cajaTelemetria() {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.sm),
      decoration: BoxDecoration(
        color: AppColors.errorContainer.withValues(alpha: 0.45),
        borderRadius: AppRadius.brTarjeta,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Text(
                'Telemetría Dexter OLT',
                style: AppTypography.etiquetaChica.copyWith(
                  color: AppColors.onErrorContainer,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const Spacer(),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: AppColors.error,
                  borderRadius: BorderRadius.circular(AppRadius.circulo),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    const Icon(Icons.error_outline, size: 11, color: AppColors.onError),
                    const SizedBox(width: 3),
                    Text(
                      'Alerta Dexter',
                      style: AppTypography.etiquetaChica.copyWith(
                        color: AppColors.onError,
                        fontSize: 10,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          Row(
            children: <Widget>[
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      FieldMockData.cto,
                      style: AppTypography.etiqueta.copyWith(
                        color: AppColors.onSurface,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    Text('Splitter 1:8 Libre (Port 3)', style: AppTypography.etiquetaChica),
                  ],
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.sm,
                  vertical: 6,
                ),
                decoration: const BoxDecoration(
                  color: AppColors.surfaceContainerLowest,
                  borderRadius: AppRadius.brCampo,
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: <Widget>[
                    Text('RX: ', style: AppTypography.etiquetaChica),
                    Text(
                      '${FieldMockData.potenciaRxPrevia.toStringAsFixed(1)} dBm',
                      style: AppTypography.etiquetaGrande.copyWith(
                        color: AppColors.error,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  /// CAMPO-DATA-023: plan contratado y materiales previstos de la instalación.
  Widget _etiquetasDelPlan() {
    return Wrap(
      spacing: AppSpacing.xs,
      runSpacing: AppSpacing.xs,
      children: <Widget>[
        _Etiqueta(
          icono: Icons.speed,
          texto: 'Fibra 500 Mbps + TV',
          fondo: AppColors.surfaceContainer,
          color: AppColors.primary,
        ),
        const _Etiqueta(
          texto: 'ONT + 80m Drop',
          fondo: AppColors.surfaceVariant,
          color: AppColors.onSurface,
        ),
        // CAMPO-DATA-004: la prioridad, que el diseño usa como "cliente esperando".
        _Etiqueta(
          icono: Icons.person_outline,
          texto: 'Prioridad ${_prioridad(trabajo)}',
          fondo: AppColors.exito,
          color: AppColors.exito,
        ),
      ],
    );
  }

  /// Los valores de ejemplo de este trabajo.
  ///
  /// Se piden acá, no dentro de `TrabajoVista`: un modelo que trae adentro un
  /// dato inventado se lo entrega a cualquiera que lo lea, y encima arrastra
  /// al núcleo a depender de la demostración. Cada uso de esto vive dentro de
  /// un bloque con la bandera; la guarda de `guarda_demo_test.dart` lo mide.
  TrabajoFuturoMock get _ejemplo => FieldMockData.trabajoFuturo(trabajo.id);

  Widget _aviso({
    required IconData icono,
    required String texto,
    required Color color,
    required Color fondo,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: 6,
      ),
      decoration: BoxDecoration(color: fondo, borderRadius: AppRadius.brCampo),
      child: Row(
        children: <Widget>[
          Icon(icono, size: 14, color: color),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              texto,
              style: AppTypography.etiquetaChica.copyWith(color: color),
            ),
          ),
        ],
      ),
    );
  }

  // --- Acciones ------------------------------------------------------------

  /// El aviso de seguridad del diseño: qué certificación pide el trabajo y si
  /// el técnico la tiene. Las dos cosas son de ejemplo (CAMPO-DATA-045): la
  /// orden no trae requisitos y el perfil no trae certificaciones, así que
  /// esto **no habilita ni bloquea** nada.
  Widget _avisoSeguridad() {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.sm),
      decoration: const BoxDecoration(
        color: AppColors.errorContainer,
        borderRadius: AppRadius.brCampo,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          const Icon(Icons.health_and_safety, size: 16, color: AppColors.onErrorContainer),
          const SizedBox(width: 6),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  FieldMockData.requisitoSeguridad,
                  style: AppTypography.etiquetaChica.copyWith(
                    color: AppColors.onErrorContainer,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                Text(
                  FieldMockData.aptitudTecnico,
                  style: AppTypography.etiquetaChica.copyWith(
                    color: AppColors.onErrorContainer,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// Solo los trabajos que exigen trabajar en altura muestran el aviso y sus
  /// acciones (CAMPO-DATA-045). Marcarlos todos sería ruido, y el ruido en un
  /// aviso de seguridad se deja de mirar.
  bool get _pideAlturas =>
      !_enCurso && !_terminado && mostrarDatosFuturos && _ejemplo.requiereAlturas;

  /// Las dos acciones del aviso de seguridad. Todavía no hay módulo de EPP ni
  /// preparación de OT, así que abren la ficha del trabajo, que es lo que la
  /// aplicación sí sabe hacer.
  Widget _accionesDeSeguridad() {
    return Row(
      children: <Widget>[
        Expanded(
          child: _BotonAccion(
            texto: 'Consultar EPP & Permisos',
            icono: Icons.shield_outlined,
            fondo: AppColors.surfaceContainer,
            color: AppColors.primary,
            onTap: onTap,
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: _BotonAccion(
            texto: 'Preparar OT',
            icono: Icons.checklist,
            fondo: AppColors.secondary,
            color: AppColors.onSecondary,
            onTap: onTap,
          ),
        ),
      ],
    );
  }

  Widget _acciones() {
    // CAMPO-DATA-045 · Cuando el trabajo anuncia un requisito de seguridad, el
    // diseño cambia las acciones por las suyas.
    if (_pideAlturas && !_incidencia) return _accionesDeSeguridad();

    if (_enCurso) {
      return Row(
        children: <Widget>[
          Expanded(
            child: _BotonAccion(
              texto: 'Continuar ejecución',
              icono: Icons.play_arrow,
              fondo: AppColors.primary,
              color: AppColors.onPrimary,
              onTap: onTap,
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          _BotonIcono(icono: Icons.near_me, activo: trabajo.latitud != null),
          const SizedBox(width: AppSpacing.sm),
          _BotonIcono(icono: Icons.call, activo: trabajo.telefono.isNotEmpty),
        ],
      );
    }

    if (_incidencia) {
      return _BotonAccion(
        texto: 'EVALUAR EN CAMPO',
        icono: Icons.assignment_add,
        fondo: AppColors.surfaceContainer,
        color: AppColors.primary,
        onTap: onTap,
      );
    }

    if (_terminado) {
      return _BotonAccion(
        texto: 'Ver Acta Digital',
        icono: Icons.description_outlined,
        fondo: AppColors.surfaceContainerHigh,
        color: AppColors.onSurface,
        onTap: onTap,
      );
    }

    return Row(
      children: <Widget>[
        Expanded(
          child: _BotonAccion(
            texto: 'Detalles',
            icono: Icons.info_outline,
            fondo: AppColors.surfaceContainerHigh,
            color: AppColors.onSurface,
            onTap: onTap,
          ),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(
          child: _BotonAccion(
            texto: 'Iniciar ruta de viaje',
            icono: Icons.navigation,
            fondo: AppColors.secondary,
            color: AppColors.onSecondary,
            onTap: onTap,
          ),
        ),
      ],
    );
  }

  /// La prioridad que decidió la oficina; si no la dijo, la de ejemplo.
  String _prioridad(TrabajoVista trabajo) {
    if (trabajo.prioridad.isEmpty) return _ejemplo.prioridad;
    return trabajo.prioridad[0].toUpperCase() + trabajo.prioridad.substring(1);
  }

  /// Qué franja se muestra, en orden de certeza: la que el servidor prometió
  /// al cliente, la hora agendada, y recién al final el ejemplo.
  String _ventana(TrabajoVista trabajo) {
    if (trabajo.ventanaTexto.isNotEmpty) return trabajo.ventanaTexto;
    if (trabajo.compromiso != null) return _ventanaReal(trabajo.compromiso!);
    return FieldMockData.ventanaHoraria;
  }

  static String _ventanaReal(DateTime fecha) {
    String dosDigitos(int n) => n.toString().padLeft(2, '0');
    final fin = fecha.add(const Duration(hours: 2));
    return '${dosDigitos(fecha.hour)}:${dosDigitos(fecha.minute)} - '
        '${dosDigitos(fin.hour)}:${dosDigitos(fin.minute)}';
  }
}

class _Etiqueta extends StatelessWidget {
  const _Etiqueta({
    required this.texto,
    required this.fondo,
    required this.color,
    this.icono,
  });

  final String texto;
  final Color fondo;
  final Color color;
  final IconData? icono;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm, vertical: 4),
      decoration: BoxDecoration(color: fondo, borderRadius: AppRadius.brCampo),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          if (icono != null) ...<Widget>[
            Icon(icono, size: 13, color: color),
            const SizedBox(width: 4),
          ],
          Text(texto, style: AppTypography.etiquetaChica.copyWith(color: color)),
        ],
      ),
    );
  }
}

class _BotonAccion extends StatelessWidget {
  const _BotonAccion({
    required this.texto,
    required this.icono,
    required this.fondo,
    required this.color,
    required this.onTap,
  });

  final String texto;
  final IconData icono;
  final Color fondo;
  final Color color;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: AppRadius.brTarjeta,
      child: Container(
        height: 52,
        alignment: Alignment.center,
        decoration: BoxDecoration(color: fondo, borderRadius: AppRadius.brTarjeta),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: <Widget>[
            Icon(icono, size: 18, color: color),
            const SizedBox(width: 6),
            Flexible(
              child: Text(
                texto,
                style: AppTypography.etiqueta.copyWith(
                  color: color,
                  fontWeight: FontWeight.w700,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Los dos botones cuadrados del pie: navegar y llamar. Todavía no abren nada
/// —falta decidir la dependencia— y se ven apagados si el dato no existe.
class _BotonIcono extends StatelessWidget {
  const _BotonIcono({required this.icono, required this.activo});

  final IconData icono;
  final bool activo;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 52,
      height: 52,
      decoration: const BoxDecoration(
        color: AppColors.surfaceContainer,
        borderRadius: AppRadius.brTarjeta,
      ),
      child: Icon(
        icono,
        size: 20,
        color: activo ? AppColors.primary : AppColors.outline,
      ),
    );
  }
}
