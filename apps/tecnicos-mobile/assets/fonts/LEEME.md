# Fuentes de Dexter Campo

Las dos familias del sistema visual de Stitch ("Dexter Campo  App") van
empaquetadas en la
aplicación. No se descargan en tiempo de ejecución: el técnico trabaja sin
conexión, y una fuente que no llega deja la pantalla con otra tipografía.

| Familia | Uso | Origen | Versión | Licencia |
|---|---|---|---|---|
| Inter | Texto de interfaz | <https://github.com/rsms/inter> (release oficial) | v4.1 | SIL Open Font License 1.1 — `OFL-Inter.txt` |
| JetBrains Mono | Datos técnicos: mediciones, seriales, códigos, identificadores | <https://github.com/JetBrains/JetBrainsMono> (release oficial) | v2.304 | SIL Open Font License 1.1 — `OFL-JetBrainsMono.txt` |

La OFL permite empaquetar y redistribuir las fuentes dentro de una aplicación,
incluso comercial, mientras se conserve el aviso de copyright y la licencia
—por eso los dos `OFL-*.txt` viven acá al lado y no se borran—, y siempre que
no se vendan las fuentes por separado.

## Pesos incluidos, y por qué solo esos

Se incluyen únicamente los que la escala tipográfica usa. Cada peso de más son
unos 410 KB (Inter) o 270 KB (JetBrains Mono) dentro del instalador, sin que
nada los muestre.

| Archivo | Peso | Dónde se usa |
|---|---|---|
| `Inter-Regular.ttf` | 400 | Cuerpo y texto chico |
| `Inter-Medium.ttf` | 500 | Etiquetas medianas |
| `Inter-SemiBold.ttf` | 600 | Títulos, botones y etiquetas chicas |
| `Inter-Bold.ttf` | 700 | Título grande |
| `JetBrainsMono-Medium.ttf` | 500 | Datos en una fila (`data-mono-sm`, `data-mono-md`) |
| `JetBrainsMono-SemiBold.ttf` | 600 | Mediciones dentro de una tarjeta |
| `JetBrainsMono-Bold.ttf` | 700 | Mediciones (potencia, metraje, conteos) |

No se incluye ninguna cursiva: el diseño no usa ninguna.

## Cómo se nombran en el código

Los nombres de las familias viven **solo** en `lib/core/theme/app_typography.dart`
(`AppTypography.familiaTexto` y `AppTypography.familiaMono`). Ningún widget
escribe `'Geist'` ni `'JetBrainsMono'` directamente, así que cambiar de
tipografía es tocar un archivo.

## Al actualizar una versión

Bajar el `.zip` del release oficial del repositorio de arriba, copiar solo los
pesos de la tabla, reemplazar también el `OFL-*.txt` que venga en ese release y
actualizar la versión en esta tabla.

## Cambio de familia de interfaz (22/09/2026)

El sistema visual pasó del proyecto "Dexter Campo Mobile App" (Geist) al
proyecto "Dexter Campo  App" (Inter), que es el que manda. Geist salió del
paquete: mantenerla sumaba medio mega al instalador sin que nada la usara.
Si alguna vez se vuelve atrás, está en su release oficial, con la misma
licencia.
