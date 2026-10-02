import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import '../../core/widgets/dexter_bloques.dart';
import '../ejecucion/campo_del_formulario.dart';
import '../ejecucion/widgets/formulario_de_campo.dart';

/// Lo que el técnico escribe cuando reporta un momento de la intervención.
///
/// NO HAY FORMULARIO NUEVO ACÁ
/// ---------------------------
/// Los campos los declara `WorkTypeVersion`, el backend los manda y los
/// interpreta `CampoDelFormulario.normalizar`, que es el mismo camino que usa la
/// pantalla de ejecución desde antes. Este archivo solo los pone en una hoja con
/// un botón.
///
/// Eso no es ahorro de código: es la decisión 1 del objetivo. Si acá se leyera el
/// esquema otra vez, habría **dos lecturas del mismo campo** — y ese defecto ya
/// ocurrió en esta aplicación: el widget aceptaba `clave` o `id` y la validación
/// de cierre solo `clave`, así que se podía terminar un trabajo con los
/// obligatorios vacíos.
///
/// LO QUE SÍ DECIDE ESTA HOJA
/// --------------------------
/// Nada del negocio. Junta lo que el técnico escribió y lo entrega; quien la usa
/// lo encola. Los obligatorios se marcan para que no mande algo que el servidor
/// va a rechazar, pero **la validación de verdad es la del servidor**: la de acá
/// es cortesía para no hacer viajar un reporte que ya se sabe incompleto.
class HojaDeReporte extends StatefulWidget {
  const HojaDeReporte({
    super.key,
    required this.momento,
    required this.titulo,
    required this.campos,
    required this.alGuardar,
    this.erroresDelServidor = const <String, String>{},
    this.guardando = false,
  });

  /// `inicio`, `avance`, `bloqueo` o `cierre`.
  final String momento;

  final String titulo;

  /// Los campos **crudos**, tal como los mandó el backend. Se normalizan acá con
  /// el mismo lector que el resto de la app.
  final List<Map<String, dynamic>> campos;

  /// Devuelve las respuestas y, cuando el momento es un bloqueo, sus dos datos
  /// de plataforma.
  final void Function(
    Map<String, dynamic> respuestas, {
    bool requiereNoc,
    bool detener,
  })
  alGuardar;

  /// Lo que el servidor rechazó, por campo. Se muestra donde corresponde en vez
  /// de un texto suelto arriba.
  final Map<String, String> erroresDelServidor;

  final bool guardando;

  @override
  State<HojaDeReporte> createState() => _HojaDeReporteState();
}

class _HojaDeReporteState extends State<HojaDeReporte> {
  final Map<String, dynamic> _valores = <String, dynamic>{};
  final Map<String, TextEditingController> _controladores =
      <String, TextEditingController>{};
  Map<String, String> _faltantes = <String, String>{};

  // Los dos datos del bloqueo. Separados a propósito: estar detenido y necesitar
  // al NOC son dos cosas distintas, y el CRM ya tomó esa decisión.
  bool _requiereNoc = false;
  bool _detener = true;

  @override
  void dispose() {
    for (final TextEditingController c in _controladores.values) {
      c.dispose();
    }
    super.dispose();
  }

  List<CampoDelFormulario> get _normalizados =>
      CampoDelFormulario.normalizar(widget.campos, _valores);

  void _alCambiar(String id, dynamic valor) {
    setState(() {
      _valores[id] = valor;
      // Si el técnico corrige el campo, el aviso se va: dejarlo encendido hace
      // que parezca que sigue mal.
      _faltantes = Map<String, String>.from(_faltantes)..remove(id);
    });
  }

  void _guardar() {
    final Map<String, String> faltan = <String, String>{};
    for (final CampoDelFormulario campo in _normalizados) {
      if (!campo.obligatorio) {
        continue;
      }
      final dynamic valor = _valores[campo.id];
      final bool vacio = valor == null || valor.toString().trim().isEmpty;
      if (vacio) {
        faltan[campo.id] = 'Este campo es requerido.';
      }
    }

    if (faltan.isNotEmpty) {
      setState(() => _faltantes = faltan);
      return;
    }

    widget.alGuardar(
      Map<String, dynamic>.from(_valores),
      requiereNoc: _requiereNoc,
      detener: _detener,
    );
  }

  @override
  Widget build(BuildContext context) {
    // Lo que falta localmente y lo que rechazó el servidor se muestran igual: al
    // técnico le da lo mismo quién lo dijo, lo que necesita es saber qué arreglar.
    final Map<String, String> errores = <String, String>{
      ...widget.erroresDelServidor,
      ..._faltantes,
    };

    return DexterBloque(
      titulo: widget.titulo,
      icono: Icons.edit_note,
      children: <Widget>[
        if (widget.campos.isEmpty)
          Text(
            'Este tipo de trabajo no declara campos para este momento. '
            'Se puede reportar igual.',
            style: AppTypography.cuerpoChico,
          )
        else
          FormularioDeCampo(
            campos: _normalizados,
            valores: _valores,
            controladores: _controladores,
            alCambiar: _alCambiar,
          ),

        for (final MapEntry<String, String> error in errores.entries)
          Padding(
            padding: const EdgeInsets.only(top: 4),
            child: Text(
              '${_tituloDe(error.key)}: ${error.value}',
              style: AppTypography.cuerpoChico.copyWith(color: AppColors.error),
            ),
          ),

        if (widget.momento == 'bloqueo') ...<Widget>[
          const SizedBox(height: AppSpacing.xs),
          _casilla(
            valor: _requiereNoc,
            titulo: 'Hace falta que el NOC haga algo',
            ayuda:
                'Esto lo pone en la bandeja «Requiere NOC». Un trabajo '
                'detenido esperando al cliente o al material está bloqueado '
                'igual, pero no es de esa mesa.',
            alCambiar: (bool v) => setState(() => _requiereNoc = v),
          ),
          _casilla(
            valor: _detener,
            titulo: 'Detener el trabajo',
            ayuda:
                'Si se destilda, el bloqueo queda anotado y el estado del '
                'trabajo no cambia: algo demora pero se puede seguir.',
            alCambiar: (bool v) => setState(() => _detener = v),
          ),
        ],

        const SizedBox(height: AppSpacing.sm),
        DexterAccionDominante(
          texto: widget.guardando ? 'Guardando…' : 'Guardar el reporte',
          icono: Icons.save_outlined,
          alTocar: widget.guardando ? null : _guardar,
        ),
        const SizedBox(height: AppSpacing.xs),
        Text(
          'Se guarda en el teléfono y sube cuando haya señal.',
          style: AppTypography.etiquetaChica,
        ),
      ],
    );
  }

  Widget _casilla({
    required bool valor,
    required String titulo,
    required String ayuda,
    required void Function(bool) alCambiar,
  }) {
    return Padding(
      padding: const EdgeInsets.only(top: AppSpacing.xs),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Row(
            children: <Widget>[
              Checkbox(
                value: valor,
                onChanged: (bool? v) => alCambiar(v ?? false),
              ),
              Expanded(child: Text(titulo, style: AppTypography.cuerpo)),
            ],
          ),
          Padding(
            padding: const EdgeInsets.only(left: 48),
            child: Text(ayuda, style: AppTypography.etiquetaChica),
          ),
        ],
      ),
    );
  }

  /// El título que declaró el esquema, para que el error diga de qué campo
  /// habla con las palabras que el técnico está viendo.
  String _tituloDe(String id) {
    for (final CampoDelFormulario campo in _normalizados) {
      if (campo.id == id) {
        return campo.titulo;
      }
    }
    return id;
  }
}
