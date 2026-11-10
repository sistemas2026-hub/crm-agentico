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

/// LAS DOS, EN UN SOLO BOTÓN (09/11/2026)
/// ---------------------------------------
/// El mismo usuario, probándolo: «en test de velocidad solo sale para elegir
/// captura, deben ser ambos pero en un solo botón».
///
/// Y es cierto: un requisito marcado como captura abría SOLO la galería, así
/// que quien quisiera fotografiar la pantalla de otro aparato --que pasa-- se
/// quedaba sin cámara. Al revés también: una foto del daño que el técnico ya
/// había sacado cinco minutos antes no se podía usar.
///
/// Ahora el botón ofrece las dos y el técnico elige. Lo que la plantilla
/// decide ya no es SI se puede usar la galería, sino CUÁL se ofrece primero.
///
/// LO QUE NO SE AFLOJA. Una foto sacada en el momento prueba que alguien
/// estuvo ahí; una elegida de la galería puede ser de otro día o de otra casa.
/// Eso no cambia porque ahora se pueda elegir: lo que cambia es que la app
/// GUARDA DE DÓNDE SALIÓ --ver [esDeGaleria]--, así que quien revisa el cierre
/// decide con el dato a la vista en vez de suponer que toda foto es de campo.
/// Antes esa distinción se defendía prohibiendo la galería, y el precio lo
/// pagaba el técnico cuando la cámara no servía para ese requisito.

/// Cuál de las dos se ofrece PRIMERO en la hoja de elección.
///
/// No es la única disponible --las dos están siempre-- sino la que el técnico
/// va a querer nueve de cada diez veces para ese requisito.
ImageSource fuenteDeLaEvidencia(Map<String, dynamic>? requisito) =>
    esUnaCaptura(requisito) ? ImageSource.gallery : ImageSource.camera;

/// La otra, la que va segunda.
ImageSource laOtraFuente(ImageSource primera) =>
    primera == ImageSource.camera ? ImageSource.gallery : ImageSource.camera;

/// Si la imagen NO se tomó en el momento.
///
/// Es lo que se guarda con la evidencia para que la revisión del cierre sepa
/// qué está mirando. En una captura de pantalla no dice nada raro --sale de la
/// galería por definición--; en una foto de daño, sí.
bool esDeGaleria(ImageSource fuente) => fuente == ImageSource.gallery;

/// Lo que dice el botón, para que no prometa algo que no va a pasar.
///
/// Ya no nombra una sola fuente: «TOMAR FOTOGRAFÍA» con la galería detrás
/// dejaba al técnico esperando una cámara que no se abre. Ahora el botón abre
/// una elección, y lo dice.
String textoDelBoton({required bool yaHayFoto, required bool esCaptura}) {
  if (yaHayFoto) return 'CAMBIAR LA IMAGEN';
  return esCaptura ? 'AGREGAR LA CAPTURA' : 'AGREGAR LA FOTO';
}

/// Cómo se llama cada opción dentro de la hoja.
///
/// Dicen el gesto, no el aparato: «Tomar una foto ahora» contra «Elegir una
/// que ya tengo» es la diferencia que importa, y es justo la que queda
/// registrada en la evidencia.
String textoDeLaOpcion(ImageSource fuente) => fuente == ImageSource.camera
    ? 'Tomar una foto ahora'
    : 'Elegir una que ya tengo';
