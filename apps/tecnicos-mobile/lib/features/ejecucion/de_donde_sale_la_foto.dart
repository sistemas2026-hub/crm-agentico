import 'package:image_picker/image_picker.dart';

/// DE DÓNDE SALE LA IMAGEN DE UN REQUISITO DE EVIDENCIA (06/11/2026).
///
/// EL PEDIDO, DE QUIEN LO SUFRE
/// ----------------------------
/// «La foto de test de velocidad solo direcciona a la cámara y no deja ver
/// los capture ni nada.»
///
/// Tenía razón y el caso es claro: la evidencia de un test de velocidad **es**
/// una captura de pantalla. La app abría `ImageSource.camera` y nada más, así
/// que el técnico tenía que fotografiar la pantalla de otro teléfono -- o no
/// podía cumplir el requisito.
///
/// POR QUÉ NO SE PERMITE EN TODAS, QUE FUE LA DECISIÓN
/// ---------------------------------------------------
/// Una foto sacada en el momento prueba que alguien estuvo ahí. Una elegida
/// de la galería puede ser de otro día o de otra casa, y la orden la guardaría
/// igual, con la misma cara de evidencia. La revisión del cierre no podría
/// distinguirlas.
///
/// Así que lo decide la PLANTILLA, no el técnico y no la app: quien la arma
/// sabe si ese requisito es una captura o es el daño en la pared. Se marca
/// con una casilla al lado de «obligatoria».
///
/// EL VALOR POR OMISIÓN ES EL QUE NO AFLOJA NADA. Sin la marca --y una
/// plantilla vieja no la trae-- es cámara. Una plantilla que todavía no se
/// editó no puede empezar a aceptar imágenes de la galería por su cuenta.

/// `true` solo cuando la plantilla lo dice explícitamente.
///
/// Se compara contra `true` y no se usa el valor como booleano: de la API
/// llega JSON, y `"si"`, `1` o `"true"` NO son la marca. Cualquier cosa que no
/// sea el booleano verdadero cae a cámara, que es el lado seguro.
bool esUnaCaptura(Map<String, dynamic>? requisito) =>
    requisito != null && requisito['es_captura'] == true;

/// La fuente que hay que abrirle al técnico para ese requisito.
ImageSource fuenteDeLaEvidencia(Map<String, dynamic>? requisito) =>
    esUnaCaptura(requisito) ? ImageSource.gallery : ImageSource.camera;

/// Lo que dice el botón, para que no prometa algo que no va a pasar.
///
/// «Tomar fotografía» abriendo la galería deja al técnico esperando una cámara
/// que no se abre, y eso se lee como que la app falló.
String textoDelBoton({required bool yaHayFoto, required bool esCaptura}) {
  if (yaHayFoto) return esCaptura ? 'ELEGIR OTRA' : 'VOLVER A TOMAR';
  return esCaptura ? 'ELEGIR LA CAPTURA' : 'TOMAR FOTOGRAFÍA';
}
