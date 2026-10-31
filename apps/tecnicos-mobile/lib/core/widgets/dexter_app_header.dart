import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Qué se sabe del enlace con el servidor.
enum EstadoConexion {
  /// El teléfono tiene una red disponible.
  conRed,

  /// El teléfono no tiene ninguna red: ni datos ni wifi.
  sinRed,

  /// Hay red, pero el último intento no llegó al servidor.
  sinServidor,

  /// Todavía no se pudo determinar.
  desconocido,

  /// Reservado: el servidor contestó recién. Nada lo devuelve todavía —
  /// hace falta una comprobación periódica contra el backend.
  enLinea,
}

/// El encabezado del diseño "DEXTER CAMPO", en su variante de raíz.
///
/// Tal como lo dibujan las pantallas de Stitch: a la izquierda el logo, la
/// marca en monoespaciada y, debajo, el nombre de la sección en grande; a la
/// derecha la pastilla de conexión y el avatar con su punto de estado.
///
/// LO QUE NO SE COPIÓ, Y POR QUÉ
/// -----------------------------
/// La pastilla del diseño dice siempre "ONLINE". Acá dice lo que de verdad se
/// puede afirmar —"CON RED", "SIN SERVIDOR"—, porque tener wifi no prueba que
/// el servidor conteste y el técnico decide si espera o sigue sin conexión
/// mirando justamente eso. La FORMA es la del diseño; la palabra, la medida.
class DexterAppHeader extends StatelessWidget {
  const DexterAppHeader({
    super.key,
    required this.empresa,
    required this.conexion,
    this.seccion,
    this.iniciales,
    this.notificacionesSinLeer = 0,
    this.onPerfil,
  });

  /// El tenant. El diseño no le reserva un lugar propio en el encabezado de
  /// raíz, así que viaja en la etiqueta accesible del avatar, que es de quien
  /// depende: el técnico pertenece a una empresa.
  final String empresa;

  final EstadoConexion conexion;

  /// En qué sección está parado el técnico. Es el título grande del diseño.
  final String? seccion;

  final String? iniciales;

  /// Sin uso en este diseño: esta familia de pantallas no tiene campana. Se
  /// conserva el parámetro para no romper a quien ya lo pasa.
  final int notificacionesSinLeer;

  final VoidCallback? onPerfil;

  @override
  Widget build(BuildContext context) {
    return _MarcoDeEncabezado(
      child: Row(
        children: <Widget>[
          Image.asset(
            'assets/images/logo_dexter_campo.png',
            width: 32,
            height: 32,
            filterQuality: FilterQuality.medium,
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.center,
              children: <Widget>[
                Text(
                  'DEXTER CAMPO',
                  style: AppTypography.labelBadge.copyWith(
                    color: AppColors.primary,
                    letterSpacing: 0.8,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                if (seccion != null)
                  Text(
                    seccion!,
                    // `leading-none` del diseño: el título se apoya en la
                    // marca sin aire de por medio.
                    style: AppTypography.headlineMd.copyWith(height: 1.05),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
              ],
            ),
          ),
          const SizedBox(width: AppSpacing.sm),
          PastillaDeConexion(estado: conexion),
          const SizedBox(width: AppSpacing.sm),
          AvatarDeTecnico(
            iniciales: iniciales,
            empresa: empresa,
            conexion: conexion,
            onTap: onPerfil,
          ),
        ],
      ),
    );
  }
}

/// El encabezado de un paso dentro de una orden.
///
/// La segunda variante del diseño: flecha de volver, logo, el título del
/// flujo con el paso debajo, la pastilla de la herramienta activa, el avatar,
/// y una barra de avance de 4 px pegada al borde inferior.
///
/// EL PASO SE CALCULA, NO SE COPIA
/// -------------------------------
/// Las cuatro pantallas de paso del diseño dicen todas "PASO 2 DE 5" y pintan
/// la barra al 2/5: Stitch generó el mismo encabezado cuatro veces sin variar
/// el número. Copiar ese 2 sería copiar un artefacto de la generación, así que
/// acá el paso entra por parámetro y la barra sale de él.
class DexterStepHeader extends StatelessWidget {
  const DexterStepHeader({
    super.key,
    required this.titulo,
    required this.paso,
    required this.deTotal,
    this.herramienta,
    this.iconoHerramienta,
    this.pastilla,
    this.iniciales,
    this.empresa = '',
    this.onVolver,
    this.onPerfil,
  });

  final String titulo;

  /// En qué paso está, empezando en 1.
  final int paso;
  final int deTotal;

  /// La pastilla de la derecha: qué está activo ahora mismo.
  final String? herramienta;
  final IconData? iconoHerramienta;

  /// Ocupa el mismo lugar que [herramienta], para cuando lo que va ahí ya es
  /// un widget con su propia lógica —el estado de la cola, por ejemplo— en
  /// vez de una palabra.
  final Widget? pastilla;

  final String? iniciales;
  final String empresa;
  final VoidCallback? onVolver;
  final VoidCallback? onPerfil;

  double get _avance {
    if (deTotal <= 0) return 0;
    return (paso.clamp(0, deTotal)) / deTotal;
  }

  @override
  Widget build(BuildContext context) {
    return _MarcoDeEncabezado(
      barraDeAvance: _avance,
      child: Row(
        children: <Widget>[
          Semantics(
            button: true,
            label: 'Volver',
            excludeSemantics: true,
            child: InkWell(
              onTap: onVolver ?? () => Navigator.of(context).maybePop(),
              borderRadius: AppRadius.brTarjeta,
              child: const SizedBox(
                width: AppSpacing.objetivoTactil,
                height: AppSpacing.objetivoTactil,
                child: Icon(Icons.arrow_back, size: 24, color: AppColors.onSurface),
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.xs),
          Image.asset(
            'assets/images/logo_dexter_campo.png',
            width: 28,
            height: 28,
            filterQuality: FilterQuality.medium,
          ),
          const SizedBox(width: AppSpacing.xs),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisAlignment: MainAxisAlignment.center,
              children: <Widget>[
                Text(
                  titulo,
                  style: AppTypography.headlineMd.copyWith(height: 1.15),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                Text(
                  'PASO $paso DE $deTotal',
                  style: AppTypography.labelBadge
                      .copyWith(color: AppColors.secondary),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
          if (pastilla != null) ...<Widget>[
            const SizedBox(width: AppSpacing.sm),
            // CON TECHO, Y NO ES UN DETALLE
            // -----------------------------
            // Sin el, la chapa del estado de la cola medía 357 px dentro de
            // un encabezado de 600: al titulo le quedaban 50, y ahi "PASO 1
            // DE 5" se partia en CUATRO renglones y desbordaba la barra. Lo
            // que ocupa la derecha no puede decidir cuanto lugar le queda a
            // lo que identifica el trabajo.
            ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 150),
              child: pastilla!,
            ),
          ] else if (herramienta != null) ...<Widget>[
            const SizedBox(width: AppSpacing.sm),
            _PastillaChica(
              texto: herramienta!,
              icono: iconoHerramienta ?? Icons.bolt,
            ),
          ],
          const SizedBox(width: AppSpacing.sm),
          AvatarDeTecnico(
            iniciales: iniciales,
            empresa: empresa,
            onTap: onPerfil,
          ),
        ],
      ),
    );
  }
}

/// La caja común de las dos variantes: alto fijo, canal lateral, la sombra
/// casi imperceptible del diseño y, si corresponde, la barra de avance.
/// En cuántas partes se reparte la barra de avance. Mil alcanza para que un
/// paso de cualquier flujo caiga en su lugar sin que se note el redondeo.
const int _escala = 1000;

int _tramo(double parte) => (parte.clamp(0.0, 1.0) * _escala).round();

class _MarcoDeEncabezado extends StatelessWidget {
  const _MarcoDeEncabezado({required this.child, this.barraDeAvance});

  final Widget child;
  final double? barraDeAvance;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppColors.surface,
      child: DecoratedBox(
        decoration: const BoxDecoration(
          color: AppColors.surface,
          boxShadow: <BoxShadow>[
            // `shadow-[0_1px_8px_rgba(0,0,0,0.04)]`, tal cual.
            BoxShadow(color: Color(0x0A000000), blurRadius: 8, offset: Offset(0, 1)),
          ],
        ),
        child: SafeArea(
          bottom: false,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              SizedBox(
                height: AppSpacing.encabezado,
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.margen,
                  ),
                  child: child,
                ),
              ),
              if (barraDeAvance != null)
                SizedBox(
                  height: 4,
                  // DOS TRAMOS PROPORCIONALES, NO UN STACK
                  // --------------------------------------
                  // La primera version apilaba un FractionallySizedBox sobre
                  // la pista. Medido: el tramo azul salia de 160x0 px --alto
                  // CERO, porque con restricciones flojas se ajusta a un hijo
                  // sin tamaño-- y ademas aparecia a 320 px del borde, o sea
                  // flotando en el medio del encabezado. Se lee como un
                  // cargador a medio andar y no como "vas por el primero de
                  // cinco". Con dos Expanded no hay nada que interpretar.
                  child: Row(
                    children: <Widget>[
                      if (_tramo(barraDeAvance!) > 0)
                        Expanded(
                          flex: _tramo(barraDeAvance!),
                          child: const ColoredBox(color: AppColors.secondary),
                        ),
                      if (_tramo(barraDeAvance!) < _escala)
                        Expanded(
                          flex: _escala - _tramo(barraDeAvance!),
                          child: const ColoredBox(
                              color: AppColors.surfaceContainerHigh),
                        ),
                    ],
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

/// La pastilla redonda de estado del encabezado de raíz.
class PastillaDeConexion extends StatelessWidget {
  const PastillaDeConexion({super.key, required this.estado});

  final EstadoConexion estado;

  @override
  Widget build(BuildContext context) {
    final (String texto, Color puntoYTexto, Color fondo) = switch (estado) {
      EstadoConexion.enLinea => (
          'EN LÍNEA',
          AppColors.onTertiaryContainer,
          AppColors.surfaceContainerHigh,
        ),
      EstadoConexion.conRed => (
          'CON RED',
          AppColors.onTertiaryContainer,
          AppColors.surfaceContainerHigh,
        ),
      EstadoConexion.sinRed => (
          'SIN RED',
          AppColors.onErrorContainer,
          AppColors.errorContainer,
        ),
      EstadoConexion.sinServidor => (
          'SIN SERVIDOR',
          AppColors.onErrorContainer,
          AppColors.errorContainer,
        ),
      EstadoConexion.desconocido => (
          'BUSCANDO',
          AppColors.onSurfaceVariant,
          AppColors.surfaceContainerHigh,
        ),
    };

    // El texto de la pastilla va en el azul oscuro del diseño cuando el fondo
    // es la superficie elevada; cuando el fondo es el rojo claro, en su
    // propio tono. El punto conserva siempre el color del estado.
    final Color colorTexto = fondo == AppColors.errorContainer
        ? AppColors.onErrorContainer
        : AppColors.onPrimaryFixed;

    return Semantics(
      label: 'Conexión: $texto',
      excludeSemantics: true,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
        decoration: BoxDecoration(
          color: fondo,
          borderRadius: BorderRadius.circular(AppRadius.circulo),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            _PuntoLatiendo(color: puntoYTexto),
            const SizedBox(width: 6),
            Text(texto, style: AppTypography.labelBadge.copyWith(color: colorTexto)),
          ],
        ),
      ),
    );
  }
}

/// La pastilla cuadrada y chica del encabezado de paso (ícono + palabra).
class _PastillaChica extends StatelessWidget {
  const _PastillaChica({required this.texto, required this.icono});

  final String texto;
  final IconData icono;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: const BoxDecoration(
        color: AppColors.surfaceContainerHigh,
        borderRadius: AppRadius.brChico,
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(icono, size: 16, color: AppColors.secondary),
          const SizedBox(width: 4),
          Text(
            texto,
            style: AppTypography.labelBadge
                .copyWith(color: AppColors.onPrimaryFixed),
          ),
        ],
      ),
    );
  }
}

/// El punto del estado.
///
/// QUÉ SE COPIÓ DEL DISEÑO, Y QUÉ NO
/// ---------------------------------
/// El diseño le pone `animate-pulse`, que en la web late para siempre. Acá
/// late en una RÁFAGA de tres pulsos y se queda encendido, y vuelve a latir
/// cada vez que el estado cambia. El motivo no es estético:
///
///   * una animación que no termina nunca mantiene el repintado vivo todo el
///     día en un teléfono que el técnico lleva en la mano desde la mañana, y
///   * cuelga a `pumpAndSettle` en cualquier prueba que monte el encabezado
///     — son 592 en esta aplicación, y el armazón aparece en casi todas.
///
/// Lo que el latido comunica —"esto se acaba de mover"— se conserva entero:
/// es justo cuando el estado cambia que hay algo nuevo que mirar.
///
/// Y si el sistema tiene activado "reducir movimiento", no late nada. No se
/// pierde información: el estado está escrito al lado, en palabras.
class _PuntoLatiendo extends StatefulWidget {
  const _PuntoLatiendo({required this.color});

  final Color color;

  /// El `w-2 h-2` del diseño.
  static const double tamano = 8;

  /// Tres pulsos. Alcanzan para que el ojo lo cace sin quedarse mirando.
  static const int pulsos = 3;
  static const Duration duracionDeUnPulso = Duration(milliseconds: 700);

  @override
  State<_PuntoLatiendo> createState() => _PuntoLatiendoState();
}

class _PuntoLatiendoState extends State<_PuntoLatiendo>
    with SingleTickerProviderStateMixin {
  late final AnimationController _control = AnimationController(
    vsync: this,
    duration: _PuntoLatiendo.duracionDeUnPulso * _PuntoLatiendo.pulsos,
  );

  late final Animation<double> _opacidad = TweenSequence<double>(
    <TweenSequenceItem<double>>[
      for (int i = 0; i < _PuntoLatiendo.pulsos; i++) ...<TweenSequenceItem<double>>[
        TweenSequenceItem<double>(
          tween: Tween<double>(begin: 1, end: 0.35)
              .chain(CurveTween(curve: Curves.easeInOut)),
          weight: 1,
        ),
        TweenSequenceItem<double>(
          tween: Tween<double>(begin: 0.35, end: 1)
              .chain(CurveTween(curve: Curves.easeInOut)),
          weight: 1,
        ),
      ],
    ],
  ).animate(_control);

  bool _movimientoPermitido = true;

  /// Solo late lo que está vivo: el verde del sistema. Un punto que parpadea
  /// sobre "SIN RED" sugiere actividad donde no la hay.
  bool get _puedeLatir =>
      _movimientoPermitido && widget.color == AppColors.onTertiaryContainer;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final bool permitido =
        !(MediaQuery.maybeOf(context)?.disableAnimations ?? false);
    final bool cambio = permitido != _movimientoPermitido;
    _movimientoPermitido = permitido;
    if (cambio || _control.status == AnimationStatus.dismissed) _latir();
  }

  @override
  void didUpdateWidget(covariant _PuntoLatiendo anterior) {
    super.didUpdateWidget(anterior);
    // El estado cambió: se vuelve a llamar la atención sobre el punto.
    if (anterior.color != widget.color) _latir();
  }

  void _latir() {
    if (_puedeLatir) {
      _control.forward(from: 0);
    } else {
      _control.stop();
      _control.value = _control.upperBound;
    }
  }

  @override
  void dispose() {
    _control.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final Widget punto = Container(
      width: _PuntoLatiendo.tamano,
      height: _PuntoLatiendo.tamano,
      decoration: BoxDecoration(color: widget.color, shape: BoxShape.circle),
    );
    if (!_puedeLatir) return punto;
    return FadeTransition(opacity: _opacidad, child: punto);
  }
}

/// El avatar del técnico con el punto de estado abajo a la derecha.
class AvatarDeTecnico extends StatelessWidget {
  const AvatarDeTecnico({
    super.key,
    required this.iniciales,
    this.empresa = '',
    this.conexion,
    this.onTap,
  });

  final String? iniciales;
  final String empresa;

  /// Si se pasa, el punto toma el color del estado. Si no, va en el azul de
  /// acción, como en el encabezado de paso del diseño.
  final EstadoConexion? conexion;

  final VoidCallback? onTap;

  Color get _colorDelPunto {
    return switch (conexion) {
      EstadoConexion.sinRed || EstadoConexion.sinServidor => AppColors.error,
      EstadoConexion.desconocido => AppColors.outline,
      _ => AppColors.secondary,
    };
  }

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: onTap != null,
      label: empresa.isEmpty ? 'Perfil y sesión' : 'Perfil y sesión · $empresa',
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppRadius.circulo),
        child: SizedBox(
          width: AppSpacing.objetivoTactil,
          height: AppSpacing.objetivoTactil,
          child: Center(
            child: SizedBox(
              width: 34,
              height: 34,
              child: Stack(
                children: <Widget>[
                  Center(
                    child: Container(
                      width: 32,
                      height: 32,
                      decoration: const BoxDecoration(
                        color: AppColors.primaryContainer,
                        shape: BoxShape.circle,
                      ),
                      alignment: Alignment.center,
                      child: iniciales == null || iniciales!.isEmpty
                          ? const Icon(Icons.person,
                              size: 18, color: AppColors.onPrimary)
                          : Text(
                              iniciales!,
                              style: AppTypography.labelBadge
                                  .copyWith(color: AppColors.onPrimary),
                            ),
                    ),
                  ),
                  Positioned(
                    right: 0,
                    bottom: 0,
                    child: Container(
                      width: 10,
                      height: 10,
                      decoration: BoxDecoration(
                        color: _colorDelPunto,
                        shape: BoxShape.circle,
                        // `ring-2 ring-surface`: el punto se recorta contra el
                        // avatar con un anillo del color del lienzo.
                        border: Border.all(color: AppColors.surface, width: 2),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
