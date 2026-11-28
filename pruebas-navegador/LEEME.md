# Pruebas de navegador de la oficina virtual

Lo que ninguna prueba de este repositorio podía ver hasta ahora: que la cadena
**entera** funcione en un navegador de verdad. `vitest` prueba módulos y
componentes sueltos, y los dos defectos más caros del 29/09/2026 vivían
justamente en los saltos que ninguna de esas pruebas atraviesa —`requiere_noc`
viajaba bien desde el backend y la capa servidor lo dejaba caer, con su prueba
en verde—.

## Por qué vive acá y no en `django-crm/frontend/`

Para no tocar su `package.json`. Esas dependencias entran en la imagen que se
despliega, y una suite de navegador no tiene nada que hacer en producción. Acá
tiene las suyas, y el frontend no se entera.

## Cómo se corre

Hace falta el laboratorio levantado (`oficinalab-*`) y nada más. El navegador
corre dentro del contenedor oficial de Playwright, así que **no se instala nada
en Windows** — que es la lección de `pnpm check`, que rompe el frontend por
truncamiento de rutas.

```
cd pruebas-navegador
./correr.sh
```

La primera vez baja la imagen e instala `@playwright/test` en `node_modules/`
(queda cacheado en el disco, fuera del repositorio por `.gitignore`).

Variables, con sus valores por defecto:

| Variable | Por defecto | Qué es |
|---|---|---|
| `BASE` | `http://host.docker.internal:55600` | el frontend del laboratorio |
| `USUARIO` | `admin@localhost` | la cuenta del laboratorio |
| `CLAVE` | `lab12345` | su contraseña |
| `ORG_CON` | `MicroPyramid` | la organización que SÍ tiene asistente |
| `ORG_SIN` | `Plumeline Media` | la que NO lo tiene |

**Ninguna de esas credenciales es de producción**, y la suite no sabe hablar
con producción: `BASE` apunta a un puerto local y el contenedor no tiene ruta a
otra cosa.

## Qué comprueba, y qué NO

Comprueba el camino completo: entrar, elegir empresa, que la oficina cargue,
navegar edificio → piso → sala, abrir la ficha de un puesto, que los estados de
«no hay información» se digan en vez de callarse, que editar la organización
conserve lo que no se editó, y que una organización sin asistente **falle
cerrada**.

**No** comprueba que la escena se vea bien. Un lienzo de PixiJS es un bitmap:
afirmar sobre píxeles da una prueba que se rompe cada vez que alguien mueve una
planta dos celdas, y que no se rompe cuando el defecto importa. Lo que sí se
puede afirmar de la escena es **cuántos objetos tiene y a cuántos fotogramas
va**, que es lo que la cabecera publica, y eso sí está acá.

## La trampa de medir fotogramas

Medido el 31/10/2026: **el número de fps de la cabecera sólo vale con la
ventana del navegador en primer plano.** Con la ventana tapada por otra, Chrome
estrangula `requestAnimationFrame` a **1 Hz**, y el contador de la escena baja
con él.

Se comprobó así, y el resultado no deja lugar a dudas:

```
pantalla CON lienzo,  ventana tapada     mediana 1004 ms por fotograma → 1 fps
pantalla SIN lienzo,  ventana tapada     mediana 1003 ms por fotograma → 1 fps
pantalla SIN lienzo,  ventana al frente  mediana    7 ms por fotograma → 145 fps
```

Una pantalla sin lienzo yendo a 1 Hz prueba que lo estrangulado es la ventana y
no la escena. Y `document.visibilityState` decía `visible` y `hasFocus()` decía
`true`: la señal de la API de visibilidad **no** lo delata, porque es oclusión
de ventana y no una pestaña en segundo plano.

Consecuencia para esta suite: corre **headless** dentro del contenedor, donde no
hay ventana que ocluir, así que la afirmación sobre fps es válida ahí. Si
alguien la corre en modo visible y la ventana queda detrás, va a fallar por lo
que no importa.

Y consecuencia para cualquier comparación de rendimiento: **dos medidas tomadas
sin controlar el foco de la ventana no se pueden comparar.**

## Un laboratorio recién reiniciado hay que calentarlo

Vite compila bajo demanda. La primera petición a cada ruta después de reiniciar
el contenedor tarda decenas de segundos, y la preparación de sesión muere con
`Target page, context or browser has been closed` —que no se parece en nada a
«el servidor todavía está compilando»—.

Antes de la primera corrida tras un reinicio:

```
for r in /login /org /centro-mando/v2 /settings/organizacion /; do
  curl -s -o /dev/null -w "$r %{http_code}\n" -m 120 "http://localhost:55600$r"
done
```

Con eso, la suite entera corre en unos 6 minutos.

## Lo que esta suite encontró la primera vez que corrió

Dos defectos que ninguna prueba de módulo podía ver, y los dos del tipo que
esta cadena existe para cazar — la pantalla decía algo que no era cierto:

1. **Un enlace a una sala que no existe abría otra sala.**
   `salaPorId` cae a la primera sala cuando no encuentra el id, que es correcto
   para el selector y es justo lo que no se puede hacer con un enlace: un
   enlace viejo a Cartera mostraba NOC y Redes sin decir que no era lo pedido.

2. **La oficina de una empresa sin asistente culpaba al despliegue.**
   Decía «falta PRIVATE_ASISTENTE_URL o la empresa de la sesión»: le nombraba a
   quien mira una variable de entorno que no puede tocar, y presentaba como
   error de configuración lo que es un hecho del producto —esa empresa todavía
   no tiene asistente—. Es exactamente el mensaje que el 31/10/2026 mandó a
   buscar el problema al sitio equivocado.
