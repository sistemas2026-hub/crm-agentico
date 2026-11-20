/// QUÉ SELECTOR DE FOTOS ABRE LA APP (09/11/2026).
///
/// EL PEDIDO, DE QUIEN LO SUFRE
/// ----------------------------
/// El usuario, probando el botón nuevo de la evidencia: «solo salen las
/// imágenes de Google Fotos, no está mostrando las fotos de la galería
/// reciente».
///
/// QUÉ PASABA
/// ----------
/// `image_picker`, en Android, abre por omisión el selector viejo
/// (`ACTION_GET_CONTENT`), que delega en la aplicación que el teléfono tenga
/// como predeterminada para imágenes. En un teléfono con Google Fotos, eso es
/// Google Fotos: muestra lo que esa aplicación tiene sincronizado y **no la
/// carpeta de cámara del aparato**. Una captura de pantalla recién tomada
/// --que es justo lo que pide un test de velocidad-- puede no aparecer ahí
/// nunca, o tardar en subir.
///
/// Android 13 trae un selector propio del sistema --el Photo Picker-- que
/// muestra TODAS las imágenes del teléfono, incluidas las de hace un minuto,
/// sin depender de qué aplicación esté instalada. El plugin lo sabe usar, pero
/// hay que pedírselo.
///
/// POR QUÉ ESTO VIVE EN SU PROPIO ARCHIVO
/// ---------------------------------------
/// Porque es una línea que no se entiende sola. Sin este texto, el día que
/// alguien la borre «porque no hace nada», la app vuelve a mostrar Google
/// Fotos y el técnico vuelve a no encontrar su captura -- y eso no falla, no
/// avisa y no se ve en ninguna prueba: se ve parado en la casa del cliente.
///
/// En un teléfono viejo, sin Photo Picker del sistema, el plugin cae solo al
/// selector de antes. No hay nada que comprobar ni que elegir.
library;

import 'package:image_picker_android/image_picker_android.dart';
import 'package:image_picker_platform_interface/image_picker_platform_interface.dart';

/// Hace que la galería la muestre el sistema, no la aplicación de fotos que
/// esté instalada. Se llama una vez, al arrancar.
///
/// No lanza nunca: en iOS, en una prueba o en cualquier plataforma donde la
/// implementación no sea la de Android, `instance` no es `ImagePickerAndroid`
/// y no hay nada que hacer. Que la app no abra por un selector sería peor que
/// el selector equivocado.
void usarElSelectorDelSistema() {
  final ImagePickerPlatform actual = ImagePickerPlatform.instance;
  if (actual is ImagePickerAndroid) {
    actual.useAndroidPhotoPicker = true;
  }
}
