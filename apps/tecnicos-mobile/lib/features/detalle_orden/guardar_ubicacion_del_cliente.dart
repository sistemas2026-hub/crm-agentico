import 'package:campo/core/storage/ubicacion_de_captura.dart';

/// Dejar escrita la ubicacion de la casa del cliente, desde la puerta.
///
/// POR QUE EXISTE  --  10/11/2026. Medido contra la instancia real del ISP:
/// de 5.186 equipos, **10** tienen coordenada (0,19 %). El dato lo tiene el
/// tecnico, parado ahi, y hasta hoy la app solo sabia dibujar un boton
/// apagado que decia «Sin ubicacion».
///
/// SOLO SE OFRECE CUANDO NO HAY UNA COORDENADA UTILIZABLE --decision del
/// usuario--: la que ya esta cargada y se puede leer no se pisa nunca. Esa
/// regla vive en quien dibuja el boton; aca se asume tomada.
///
/// NO ESCRIBE UNA CUARTA LECTURA DE GPS: usa `UbicacionDeCaptura.tomar()`,
/// que ya resuelve el plazo, el permiso, los tres motivos de fallo y el
/// `isMocked`, y que tiene su propia costura de prueba.
enum EstadoDeGuardado {
  guardada,

  /// Quedo en un sistema y en el otro no. No se deshace --no hay con que-- y
  /// volver a tocar el boton reintenta SOLO el que falta.
  parcial,

  /// El telefono no pudo decir donde esta.
  sinUbicacion,

  /// La tiene, pero tan imprecisa que escribirla seria peor que no tenerla.
  demasiadoImprecisa,

  /// El servidor la rechazo, o no contesto.
  rechazada,
}

class ResultadoDeGuardado {
  const ResultadoDeGuardado(this.estado, this.mensaje);

  final EstadoDeGuardado estado;

  /// Lo que se le dice al tecnico. Siempre dice QUE PASO y, cuando se puede,
  /// que hacer: «activa la ubicacion» sirve, «error 502» no.
  final String mensaje;

  bool get algoQuedoEscrito =>
      estado == EstadoDeGuardado.guardada ||
      estado == EstadoDeGuardado.parcial;
}

/// Cuantos metros de error se aceptan.
///
/// NO ES UN NUMERO AL AZAR, y la guarda importa: una posicion tomada de la
/// antena de celular puede venir con cientos o miles de metros de error, y
/// escribirla pondria la casa a varias cuadras. Peor que no tenerla, porque
/// el que la lea despues la va a creer. Cien metros es la cuadra de la zona:
/// alcanza para encontrar la casa preguntando, y descarta lo que vino de la
/// antena.
const double metrosDeErrorAceptados = 100.0;

class GuardarUbicacionDelCliente {
  const GuardarUbicacionDelCliente({
    required this.enviar,
    this.tomarUbicacion,
  });

  /// Manda la ubicacion al servidor. Responde el codigo HTTP y el cuerpo.
  final Future<({int codigo, Map<String, dynamic> cuerpo})> Function(
      double latitud, double longitud) enviar;

  /// De donde sale la posicion. Por omision, el GPS del telefono.
  final Future<Map<String, dynamic>> Function()? tomarUbicacion;

  Future<ResultadoDeGuardado> ejecutar() async {
    final Map<String, dynamic> lectura = await (tomarUbicacion != null
        ? tomarUbicacion!()
        //  TREINTA SEGUNDOS, Y NO LOS CINCO DE UNA FOTO (10/11/2026).
        //
        //  El plazo de `UbicacionDeCaptura` esta pensado para acompanar
        //  una captura: ahi el GPS ya viene caliente porque la camara lo
        //  estaba usando, y esperar mas «compra desconfianza». Aca es al
        //  reves: el tecnico abrio la ficha y toco un boton, el GPS puede
        //  estar arrancando de cero, y eso tarda entre treinta segundos y
        //  un minuto ESTE DONDE ESTE -- medido el 10/11/2026 en la
        //  primera prueba real: a cielo abierto y sin techo, los cinco
        //  segundos se agotaban igual y el mensaje mandaba a salir
        //  afuera a alguien que ya estaba afuera.
        //
        //  Treinta es lo que tarda un arranque frio tipico. Mas seria
        //  dejar al tecnico mirando un boton sin saber si pasa algo; por
        //  eso el boton muestra «Buscando señal…» mientras tanto.
        : UbicacionDeCaptura.tomar(plazo: const Duration(seconds: 30)));

    final double? lat = (lectura['lat'] as num?)?.toDouble();
    final double? lng = (lectura['lng'] as num?)?.toDouble();
    if (lat == null || lng == null) {
      //  EL MOTIVO, NO «no se pudo». Los tres que distingue la captura llevan
      //  a acciones distintas: prender el GPS, dar el permiso, o salir a
      //  cielo abierto.
      final String motivo = (lectura['ubicacion_motivo'] ?? '').toString();
      return ResultadoDeGuardado(
        EstadoDeGuardado.sinUbicacion,
        switch (motivo) {
          'servicio_apagado' =>
            'La ubicación del teléfono está apagada. Activala y volvé a tocar.',
          'permiso_denegado' =>
            'La app no tiene permiso para usar la ubicación. Dáselo en los '
                'ajustes del teléfono.',
          'sin_senal_gps' =>
            'El GPS no encontró señal. Probá afuera, con el cielo despejado.',
          _ => 'El teléfono no pudo decir dónde está.',
        },
      );
    }

    //  UNA POSICION SIMULADA NO SE ESCRIBE. Queda en el sistema del ISP como
    //  si fuera la casa, y nadie que la lea despues va a saber que era falsa.
    if (lectura['ubicacion_simulada'] == true) {
      return const ResultadoDeGuardado(
        EstadoDeGuardado.demasiadoImprecisa,
        'El teléfono está usando una ubicación simulada. No se guarda.',
      );
    }

    final double? precision = (lectura['precision_m'] as num?)?.toDouble();
    if (precision != null && precision > metrosDeErrorAceptados) {
      return ResultadoDeGuardado(
        EstadoDeGuardado.demasiadoImprecisa,
        'La señal del GPS da un error de ${precision.round()} metros. '
            'Esperá unos segundos o salí a cielo abierto.',
      );
    }

    final ({int codigo, Map<String, dynamic> cuerpo}) r;
    try {
      r = await enviar(lat, lng);
    } catch (_) {
      //  Sin red, el servidor caido, un plazo vencido: para el tecnico es el
      //  mismo caso, y ninguno deja la ubicacion escrita.
      return const ResultadoDeGuardado(
        EstadoDeGuardado.rechazada,
        'No se pudo guardar: el servidor no respondió. Probá de nuevo.',
      );
    }

    final String estado = (r.cuerpo['codigo'] ?? '').toString();
    if (r.codigo == 200 && estado == 'parcial') {
      return const ResultadoDeGuardado(
        EstadoDeGuardado.parcial,
        //  NO DICE «no se repite lo que ya salio», y se quito a
        //  proposito (10/11/2026). Con el MISMO punto es verdad --la
        //  clave es la misma y el que ya salio vuelve como repetida--,
        //  pero el boton re-lee el GPS en cada toque: si el tecnico se
        //  movio, el punto nuevo se escribe en los DOS lados. Eso es lo
        //  que corresponde --quiere ESE punto-- y no lo que la frase
        //  prometia.
        'Quedó guardada en un sistema y en el otro no. Volvé a tocar para '
            'completar.',
      );
    }
    if (r.codigo == 200) {
      return const ResultadoDeGuardado(
        EstadoDeGuardado.guardada, 'Ubicación guardada.');
    }
    return ResultadoDeGuardado(
      EstadoDeGuardado.rechazada,
      switch (estado) {
        'bloqueado_por_interruptor' =>
          'Las escrituras están detenidas desde la oficina.',
        'sin_herramienta' =>
          'Esta empresa todavía no tiene configurado dónde guardar la '
              'ubicación.',
        'coordenada_invalida' => 'La ubicación que tomó el teléfono no sirve.',
        'sin_identificador' =>
          'Esta orden no trae con qué identificar al cliente en el sistema '
              'del ISP.',
        _ => 'No se pudo guardar. Probá de nuevo en un momento.',
      },
    );
  }
}
