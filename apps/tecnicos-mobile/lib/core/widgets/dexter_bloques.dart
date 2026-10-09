import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Los bloques con los que están armadas las seis pantallas del diseño
/// "DEXTER CAMPO".
///
/// Se escriben una vez acá y no seis veces en cada pantalla. Las medidas no
/// son aproximaciones: salen de las clases de Tailwind de las maquetas
/// (`rounded-xl` = 12, `p-space-md` = 12, `h-14` = 56, `grid-cols-8
/// gap-1.5 h-3` para la barra segmentada), y cada componente dice de dónde
/// sale la suya.
///
/// Ninguno de estos widgets sabe qué significa lo que muestra. No hay un
/// umbral, un veredicto ni una regla de negocio en este archivo: quien los usa
/// le pasa el texto y el color ya decididos. Es la misma separación que ya
/// tenían [DexterCard] y [DexterMetricTile].

/// La tarjeta de sección: el contenedor blanco con el que el diseño separa un
/// tema de otro.
///
/// `bg-surface-container-lowest rounded-xl shadow-sm p-space-md`.
///
/// EL BORDE QUE EL DISEÑO NO DIBUJA
/// --------------------------------
/// La maqueta separa la tarjeta del lienzo solo con una sombra. Acá va además
/// una línea de un tono, y no es un descuido: quedó escrito al construir la
/// primera versión que bajo el sol una sombra difusa se lava y la tarjeta
/// pierde su límite. Esa decisión se tomó mirando el teléfono a la intemperie;
/// revertirla necesita una medición nueva, no una preferencia. La línea es
/// casi invisible en interiores, así que no pelea con el diseño.
class DexterBloque extends StatelessWidget {
  const DexterBloque({
    super.key,
    required this.children,
    this.titulo,
    this.icono,
    this.insignia,
    this.separacion = AppSpacing.md,
    this.padding = const EdgeInsets.all(AppSpacing.md),
    this.recortar = false,
  });

  /// El título de la sección, en `headline-md`, con su ícono azul a la
  /// izquierda.
  final String? titulo;
  final IconData? icono;

  /// Lo que va a la derecha del título: una pastilla, casi siempre.
  final Widget? insignia;

  final List<Widget> children;
  final double separacion;
  final EdgeInsetsGeometry padding;

  /// Para las tarjetas que llevan un mapa o una foto pegada al borde: el
  /// contenido se recorta contra el redondeo y el relleno lo pone cada hijo.
  final bool recortar;

  @override
  Widget build(BuildContext context) {
    final Widget contenido = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (titulo != null)
          Padding(
            padding: recortar
                ? const EdgeInsets.fromLTRB(
                    AppSpacing.md,
                    AppSpacing.md,
                    AppSpacing.md,
                    AppSpacing.sm,
                  )
                : EdgeInsets.zero,
            child: EncabezadoDeBloque(
              titulo: titulo!,
              icono: icono,
              insignia: insignia,
            ),
          ),
        for (int i = 0; i < children.length; i++) ...<Widget>[
          if (i > 0 || titulo != null) SizedBox(height: separacion),
          children[i],
        ],
      ],
    );

    return DecoratedBox(
      decoration: const BoxDecoration(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brCompleto,
        border: Border.fromBorderSide(
          BorderSide(color: AppColors.surfaceContainerHigh),
        ),
        boxShadow: AppTheme.sombraNivel1,
      ),
      child: recortar
          ? ClipRRect(borderRadius: AppRadius.brCompleto, child: contenido)
          : Padding(padding: padding, child: contenido),
    );
  }
}

/// Un tramo de la ficha: varias tarjetas que contestan la misma pregunta.
///
/// EL PROBLEMA QUE RESUELVE
/// ------------------------
/// Una ficha de trabajo apila una docena de `DexterBloque` con el mismo fondo,
/// el mismo borde y la misma sombra. Todas se leen como pares, así que al bajar
/// parece una sola sección larga: nada distingue lo que se **consulta** —la
/// telemetría, el triage, los datos técnicos— de lo que se **hace** —reportar,
/// anotar material—.
///
/// Esto no agrega una tarjeta más. Pone un rótulo **fuera** de las tarjetas,
/// sobre el fondo de la página, y separa los grupos más de lo que separa a sus
/// miembros. El ojo encuentra dónde empieza cada cosa sin leer un título.
///
/// La separación es la que hace el trabajo, no el rótulo: por eso [entre] es
/// menor que el espacio que cada pantalla deja entre un grupo y el siguiente.
class GrupoDeFicha extends StatelessWidget {
  const GrupoDeFicha({
    super.key,
    required this.titulo,
    required this.children,
    this.entre = AppSpacing.sm,
  });

  /// Dos o tres palabras, en mayúsculas. Nombra el MOMENTO del trabajo, no la
  /// categoría del dato: «para llegar» le dice al técnico cuándo mirar esto;
  /// «información del cliente» no.
  final String titulo;

  /// Las tarjetas. `null` significa «esta no va», y es distinto de una tarjeta
  /// que se dibuja vacía: ver el filtro de abajo.
  final List<Widget?> children;

  /// Lo que separa a las tarjetas DE ESTE grupo entre sí.
  final double entre;

  @override
  Widget build(BuildContext context) {
    // AUSENTE NO ES LO MISMO QUE VACIA, Y ACA SE PAGA LA DIFERENCIA
    // -------------------------------------------------------------
    // Una sección que no tiene nada que decir devolvía `SizedBox.shrink()`: un
    // widget que existe y no ocupa nada. Para este grupo eso era una tarjeta
    // más, así que el rótulo se dibujaba igual y además quedaba un espacio
    // fantasma entre hermanas.
    //
    // Medido en el emulador el 02/10/2026: «PARA ENTENDER LA FALLA» apareció
    // con NADA debajo, en una orden sin telemetría ni datos técnicos. La prueba
    // de la lista vacía pasaba —la lista no estaba vacía— mientras el síntoma
    // estaba a la vista.
    //
    // Por eso lo ausente se dice con `null`, que sí se puede contar.
    final List<Widget> visibles = children.whereType<Widget>().toList();

    // Un grupo cuyas tarjetas son todas condicionales puede quedar sin ninguna.
    // Dibujar el rótulo solo sería anunciar una sección vacía, que es peor que
    // no anunciarla: el técnico baja buscando algo que no está.
    if (visibles.isEmpty) {
      return const SizedBox.shrink();
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.only(
            left: AppSpacing.xs,
            bottom: AppSpacing.xs,
          ),
          child: Text(
            titulo.toUpperCase(),
            style: AppTypography.labelCaption.copyWith(
              letterSpacing: 1.1,
              color: AppColors.onSurfaceVariant,
            ),
          ),
        ),
        for (int i = 0; i < visibles.length; i++) ...<Widget>[
          if (i > 0) SizedBox(height: entre),
          visibles[i],
        ],
      ],
    );
  }
}

/// La fila de título de una sección: ícono azul, título y, a la derecha, una
/// pastilla.
class EncabezadoDeBloque extends StatelessWidget {
  const EncabezadoDeBloque({
    super.key,
    required this.titulo,
    this.icono,
    this.insignia,
  });

  final String titulo;
  final IconData? icono;
  final Widget? insignia;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: <Widget>[
        if (icono != null) ...<Widget>[
          Icon(icono, size: 22, color: AppColors.secondary),
          const SizedBox(width: AppSpacing.xs),
        ],
        Expanded(
          child: Text(
            titulo,
            style: AppTypography.headlineMd,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        if (insignia != null) ...<Widget>[
          const SizedBox(width: AppSpacing.sm),
          insignia!,
        ],
      ],
    );
  }
}

/// La pastilla cuadrada del diseño: `px-2 py-0.5 rounded` con el texto en
/// `label-badge`, o sea en monoespaciada.
///
/// No decide su color: lo elige quien sabe qué significa. Los combinados que
/// usa el diseño están en los constructores nombrados.
class DexterPastilla extends StatelessWidget {
  const DexterPastilla({
    super.key,
    required this.texto,
    required this.color,
    required this.fondo,
    this.icono,
    this.descripcionAccesible,
  });

  /// Rojo pleno: lo que está mal y no admite matices.
  const DexterPastilla.critica({
    Key? key,
    required String texto,
    IconData? icono,
  }) : this(
         key: key,
         texto: texto,
         color: AppColors.onError,
         fondo: AppColors.error,
         icono: icono,
       );

  /// Rojo claro: una advertencia, o una prioridad alta.
  const DexterPastilla.alerta({
    Key? key,
    required String texto,
    IconData? icono,
  }) : this(
         key: key,
         texto: texto,
         color: AppColors.onErrorContainer,
         fondo: AppColors.errorContainer,
         icono: icono,
       );

  /// Verde sobre superficie elevada: lo que está en regla. En esta paleta el
  /// chip verde no tiene fondo verde — lleva el texto en verde.
  const DexterPastilla.enRegla({
    Key? key,
    required String texto,
    IconData? icono,
  }) : this(
         key: key,
         texto: texto,
         color: AppColors.onTertiaryContainer,
         fondo: AppColors.surfaceContainerHigh,
         icono: icono,
       );

  /// El tono por omisión del diseño: azul oscuro sobre superficie elevada.
  const DexterPastilla.neutra({
    Key? key,
    required String texto,
    IconData? icono,
  }) : this(
         key: key,
         texto: texto,
         color: AppColors.onPrimaryFixed,
         fondo: AppColors.surfaceContainerHigh,
         icono: icono,
       );

  final String texto;
  final Color color;
  final Color fondo;
  final IconData? icono;
  final String? descripcionAccesible;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: descripcionAccesible ?? texto,
      excludeSemantics: true,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
        decoration: BoxDecoration(
          color: fondo,
          borderRadius: AppRadius.brChico,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            if (icono != null) ...<Widget>[
              Icon(icono, size: 14, color: color),
              const SizedBox(width: 4),
            ],
            Flexible(
              child: Text(
                texto.toUpperCase(),
                style: AppTypography.labelBadge.copyWith(color: color),
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

/// La pastilla redonda con punto: `rounded-full px-2.5 py-1` con un punto de
/// color a la izquierda. El diseño la usa para el estado en vivo ("En Sitio",
/// "ONLINE").
class DexterPastillaConPunto extends StatelessWidget {
  const DexterPastillaConPunto({
    super.key,
    required this.texto,
    required this.colorDelPunto,
    this.fondo = AppColors.surfaceContainerHigh,
    this.color = AppColors.onPrimaryFixed,
  });

  final String texto;
  final Color colorDelPunto;
  final Color fondo;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: fondo,
        borderRadius: BorderRadius.circular(AppRadius.circulo),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(
              color: colorDelPunto,
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 6),
          Flexible(
            child: Text(
              texto.toUpperCase(),
              style: AppTypography.labelBadge.copyWith(color: color),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}

/// El bloque hundido de adentro de una tarjeta: `rounded-lg
/// bg-surface-container-low p-space-sm`. Sirve para separar un dato del resto
/// sin abrir otra tarjeta.
class DexterHundido extends StatelessWidget {
  const DexterHundido({
    super.key,
    required this.child,
    this.color = AppColors.surfaceContainerLow,
    this.padding = const EdgeInsets.all(AppSpacing.sm),
  });

  final Widget child;
  final Color color;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: color,
        borderRadius: AppRadius.brTarjeta,
      ),
      child: child,
    );
  }
}

/// La baldosa de media fila: rótulo arriba, valor abajo. El diseño las pone de
/// a dos (`grid-cols-2 gap-space-sm`) sobre `bg-surface-container`.
class DexterBaldosa extends StatelessWidget {
  const DexterBaldosa({
    super.key,
    required this.rotulo,
    required this.children,
    this.nota,
    this.fondo = AppColors.surfaceContainer,
  });

  /// El rótulo gris en mayúsculas.
  final String rotulo;

  /// El cuerpo de la baldosa, ya compuesto por quien la usa.
  final List<Widget> children;

  /// La línea chica de abajo.
  final String? nota;

  final Color fondo;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.sm),
      decoration: BoxDecoration(
        color: fondo,
        borderRadius: AppRadius.brTarjeta,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Text(
            rotulo.toUpperCase(),
            style: AppTypography.labelCaption.copyWith(
              color: AppColors.outline,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          const SizedBox(height: AppSpacing.xs),
          ...children,
          if (nota != null) ...<Widget>[
            const SizedBox(height: AppSpacing.xs),
            Text(
              nota!,
              style: AppTypography.labelCaption,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ],
      ),
    );
  }
}

/// La baldosa con el ícono en su caja blanca a la izquierda:
/// `bg-surface-container-high` + `w-10 h-10 rounded-lg
/// bg-surface-container-lowest`.
class DexterBaldosaConIcono extends StatelessWidget {
  const DexterBaldosaConIcono({
    super.key,
    required this.icono,
    required this.rotulo,
    required this.valor,
    this.colorDelIcono = AppColors.secondary,
    this.colorDelValor = AppColors.onSurface,
  });

  final IconData icono;
  final String rotulo;
  final String valor;
  final Color colorDelIcono;
  final Color colorDelValor;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      label: '$rotulo: $valor',
      excludeSemantics: true,
      child: Container(
        padding: const EdgeInsets.all(AppSpacing.sm),
        decoration: const BoxDecoration(
          color: AppColors.surfaceContainerHigh,
          borderRadius: AppRadius.brTarjeta,
        ),
        child: Row(
          children: <Widget>[
            Container(
              width: 40,
              height: 40,
              alignment: Alignment.center,
              decoration: const BoxDecoration(
                color: AppColors.surfaceContainerLowest,
                borderRadius: AppRadius.brTarjeta,
              ),
              child: Icon(icono, size: 20, color: colorDelIcono),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  Text(
                    rotulo.toUpperCase(),
                    style: AppTypography.labelCaption.copyWith(
                      color: AppColors.outline,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  Text(
                    valor,
                    style: AppTypography.labelTelemetry.copyWith(
                      color: colorDelValor,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// La fila de dato del diseño: ícono chico azul, y el texto al lado.
class DexterFilaDeDato extends StatelessWidget {
  const DexterFilaDeDato({
    super.key,
    required this.icono,
    required this.texto,
    this.estilo,
    this.colorDelIcono = AppColors.secondary,
    this.alFinal,
  });

  final IconData icono;
  final String texto;
  final TextStyle? estilo;
  final Color colorDelIcono;
  final Widget? alFinal;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Padding(
          padding: const EdgeInsets.only(top: 2),
          child: Icon(icono, size: 18, color: colorDelIcono),
        ),
        const SizedBox(width: AppSpacing.sm),
        Expanded(child: Text(texto, style: estilo ?? AppTypography.bodySm)),
        if (alFinal != null) ...<Widget>[
          const SizedBox(width: AppSpacing.sm),
          alFinal!,
        ],
      ],
    );
  }
}

/// La barra segmentada con la que el diseño dibuja una lectura óptica:
/// `grid-cols-8 gap-1.5 h-3`, ocho celdas de 12 px de alto y 2 px de radio.
///
/// NO SABE QUÉ ES UNA SEÑAL BUENA
/// ------------------------------
/// Recibe los colores de las ocho celdas ya decididos y el texto de las tres
/// referencias de abajo. El umbral vive donde tiene que vivir —en quien
/// calcula el veredicto—, nunca en un widget de dibujo: si estuviera acá,
/// habría dos reglas distintas en el sistema y la de la pantalla no sería la
/// que manda.
class DexterBarraSegmentada extends StatelessWidget {
  const DexterBarraSegmentada({
    super.key,
    required this.celdas,
    this.izquierda,
    this.centro,
    this.derecha,
    this.colorDelCentro,
    this.descripcionAccesible,
  });

  /// El color de cada celda, de izquierda a derecha.
  final List<Color> celdas;

  final String? izquierda;
  final String? centro;
  final String? derecha;
  final Color? colorDelCentro;

  final String? descripcionAccesible;

  @override
  Widget build(BuildContext context) {
    final bool hayPie = izquierda != null || centro != null || derecha != null;

    return Semantics(
      label: descripcionAccesible,
      excludeSemantics: descripcionAccesible != null,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          SizedBox(
            height: 12,
            child: Row(
              children: <Widget>[
                for (int i = 0; i < celdas.length; i++) ...<Widget>[
                  if (i > 0) const SizedBox(width: 6),
                  Expanded(
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        color: celdas[i],
                        borderRadius: const BorderRadius.all(
                          Radius.circular(2),
                        ),
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
          if (hayPie) ...<Widget>[
            const SizedBox(height: 6),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Expanded(
                  child: Text(
                    izquierda ?? '',
                    style: AppTypography.labelBadge.copyWith(
                      color: AppColors.outline,
                    ),
                  ),
                ),
                if (centro != null)
                  Expanded(
                    flex: 2,
                    child: Text(
                      centro!,
                      textAlign: TextAlign.center,
                      style: AppTypography.labelBadge.copyWith(
                        color: colorDelCentro ?? AppColors.onSurface,
                      ),
                    ),
                  ),
                Expanded(
                  child: Text(
                    derecha ?? '',
                    textAlign: TextAlign.end,
                    style: AppTypography.labelBadge.copyWith(
                      color: AppColors.outline,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

/// Botón secundario del diseño: `h-14 rounded-lg bg-surface-container-lowest
/// shadow-sm`, ícono azul y texto en `body-sm` semibold.
///
/// Los 56 px no son estéticos: la aplicación se usa con guantes.
class DexterAccionRapida extends StatelessWidget {
  const DexterAccionRapida({
    super.key,
    required this.icono,
    required this.texto,
    this.alTocar,
  });

  final IconData icono;
  final String texto;
  final VoidCallback? alTocar;

  @override
  Widget build(BuildContext context) {
    final bool activa = alTocar != null;
    final Color tinta = activa ? AppColors.onSurface : AppColors.inactivo;

    return Semantics(
      button: true,
      enabled: activa,
      label: texto,
      excludeSemantics: true,
      child: Material(
        color: AppColors.surfaceContainerLowest,
        borderRadius: AppRadius.brTarjeta,
        elevation: 0,
        child: InkWell(
          onTap: alTocar,
          borderRadius: AppRadius.brTarjeta,
          // Sin borde, como el diseño: acá la separacion del lienzo la da la
          // sombra y no una linea, y sumarla correria el alto a 58 -- los 56
          // son el objetivo tactil con guantes, no un numero cualquiera.
          child: Ink(
            decoration: BoxDecoration(
              borderRadius: AppRadius.brTarjeta,
              boxShadow: activa ? AppTheme.sombraNivel1 : null,
            ),
            child: SizedBox(
              height: AppSpacing.objetivoTactilAmplio,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: <Widget>[
                  Icon(
                    icono,
                    size: 22,
                    color: activa ? AppColors.secondary : AppColors.inactivo,
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Flexible(
                    child: Text(
                      texto,
                      style: AppTypography.etiquetaGrande.copyWith(
                        color: tinta,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
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

/// El botón dominante: el único relleno de azul saturado de la pantalla.
/// `w-full h-14 rounded-lg bg-secondary-container text-on-secondary shadow-md`
/// con el texto en `body-lg` bold y en mayúsculas.
class DexterAccionDominante extends StatelessWidget {
  const DexterAccionDominante({
    super.key,
    required this.texto,
    this.icono,
    this.alTocar,
    this.fondo = AppColors.secondaryContainer,
    this.tinta = AppColors.onSecondary,
    this.trabajando = false,
  });

  final String texto;
  final IconData? icono;
  final VoidCallback? alTocar;
  final Color fondo;
  final Color tinta;

  /// Mientras la acción está en curso: el botón no se puede volver a tocar y
  /// lo dice.
  final bool trabajando;

  @override
  Widget build(BuildContext context) {
    final bool activa = alTocar != null && !trabajando;

    return Semantics(
      button: true,
      enabled: activa,
      label: texto,
      excludeSemantics: true,
      child: Material(
        color: activa ? fondo : AppColors.surfaceContainerHigh,
        borderRadius: AppRadius.brTarjeta,
        elevation: 0,
        child: InkWell(
          onTap: activa ? alTocar : null,
          borderRadius: AppRadius.brTarjeta,
          child: SizedBox(
            height: AppSpacing.objetivoTactilAmplio,
            width: double.infinity,
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: <Widget>[
                if (trabajando)
                  SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(
                      strokeWidth: 2,
                      valueColor: AlwaysStoppedAnimation<Color>(
                        activa ? tinta : AppColors.inactivo,
                      ),
                    ),
                  )
                else if (icono != null)
                  Icon(
                    icono,
                    size: 24,
                    color: activa ? tinta : AppColors.inactivo,
                  ),
                if (trabajando || icono != null)
                  const SizedBox(width: AppSpacing.sm),
                Flexible(
                  child: Text(
                    texto.toUpperCase(),
                    style: AppTypography.bodyLg.copyWith(
                      color: activa ? tinta : AppColors.inactivo,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0.5,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
