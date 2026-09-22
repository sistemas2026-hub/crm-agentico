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
class TarjetaTrabajo extends StatelessWidget {
  const TarjetaTrabajo({
    super.key,
    required this.trabajo,
    this.onTap,
    this.mostrarDatosFuturos = FieldMockData.modoDemo,
  });

  final TrabajoVista trabajo;
  final VoidCallback? onTap;
  final bool mostrarDatosFuturos;

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
              ? 'Derivado de ${trabajo.futuro.ticketOrigen} '
                  '(${trabajo.futuro.motivoTicket})'
              : 'Derivado de ${trabajo.origen!.etiqueta}'
                  '${mostrarDatosFuturos ? ' (${trabajo.futuro.motivoTicket})' : ''}',
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
              '${trabajo.futuro.distanciaKm.toStringAsFixed(1)} km de tu posición',
              style: AppTypography.etiquetaChica.copyWith(color: AppColors.secondary),
            ),
            const SizedBox(width: 6),
            Text('•', style: AppTypography.etiquetaChica),
            const SizedBox(width: 6),
            Text(
              'Est. arribo: ${trabajo.futuro.minutosDeViaje} min',
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
      Text(
        trabajo.tipoNombre,
        style: AppTypography.tituloChico.copyWith(fontWeight: FontWeight.w700),
      ),
      const SizedBox(height: AppSpacing.xs),
      Row(
        children: <Widget>[
          const Icon(Icons.hub, size: 16, color: AppColors.onSurfaceVariant),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              trabajo.direccion,
              style: AppTypography.cuerpo,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
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
    ];
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
      !_enCurso && !_terminado && mostrarDatosFuturos && trabajo.futuro.requiereAlturas;

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
    if (trabajo.prioridad.isEmpty) return trabajo.futuro.prioridad;
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
