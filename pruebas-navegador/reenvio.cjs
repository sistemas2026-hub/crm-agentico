/**
 * Un reenvío TCP de `127.0.0.1:<puerto>` a `<destino>:<puerto>`.
 *
 * Existe para que el navegador de las pruebas vea el laboratorio como
 * `localhost`. Ver el porqué completo en `dentro.sh`: resumido, la cookie que
 * recuerda qué empresa se eligió sale `Secure` en cualquier host que no sea
 * localhost, y sobre `http://` el navegador la descarta sin decir nada.
 *
 * Ocho líneas y ninguna dependencia, a propósito: una herramienta de más en la
 * imagen es una herramienta que el día que no esté deja la suite sin explicar
 * por qué.
 *
 * Es `.cjs` y no `.js` porque el `package.json` de este directorio declara
 * `"type": "module"`: con extensión `.js`, `require` no existe y el reenvío
 * muere al arrancar — y el síntoma es `ERR_CONNECTION_REFUSED` en la primera
 * navegación, que señala al servidor y no al reenvío.
 */
const net = require('net');

const [, , puerto, destino] = process.argv;

net
  .createServer((cliente) => {
    const arriba = net.connect(Number(puerto), destino);
    cliente.pipe(arriba);
    arriba.pipe(cliente);
    //  Si un lado se cae, el otro se cierra. Sin esto quedan sockets a medias
    //  y la corrida termina colgada en vez de fallar.
    cliente.on('error', () => arriba.destroy());
    arriba.on('error', () => cliente.destroy());
  })
  .listen(Number(puerto), '127.0.0.1');
