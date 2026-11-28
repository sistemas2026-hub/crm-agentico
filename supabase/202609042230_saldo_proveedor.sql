-- =============================================================================
--  SALDO DEL PROVEEDOR -- para auditar lo que calculamos contra lo que cobran
-- =============================================================================
--  Contamos el gasto por tokens (asistente.usage_daily) y ese conteo decide si
--  el asistente se frena. Pero es un CALCULO nuestro: depende de que la tarifa
--  cargada sea la vigente, de que el desglose de cache sea correcto y de que
--  las ventanas de horario pico esten bien.
--
--  Cualquiera de las tres puede quedar desactualizada sin aviso. Paso el
--  17/08/2026: DeepSeek subio precios y nadie se entero -- el nivel de $0.28
--  por millon simplemente dejo de aplicarse, y solo se vio mirando la
--  facturacion real semanas despues.
--
--  El saldo del proveedor es la unica cifra que no discute nadie. Lo que baja
--  de un dia al otro ES lo que se gasto. Guardarlo permite comparar:
--
--      saldo de ayer - saldo de hoy   ->  gasto real
--      suma de costo_usd de hoy       ->  gasto calculado
--
--  Si se separan, algo cambio: la tarifa, la mezcla de cache, o las ventanas.
--  Es una alarma sobre nuestro propio calculo, no sobre el consumo.
--
--  NO REEMPLAZA EL CONTEO. El saldo no dice por dia ni por tipo de token, y
--  llega tarde para frenar nada. Se sigue contando por tokens porque es lo
--  unico que permite avisar a tiempo; esto audita ese conteo.

alter table asistente.usage_daily
  add column if not exists saldo_proveedor_usd numeric(12,4);

comment on column asistente.usage_daily.saldo_proveedor_usd is
  'Saldo que reportaba el proveedor del modelo al cerrar este dia. La RESTA '
  'entre dos dias consecutivos es el gasto real, y se compara contra costo_usd '
  '-- que es lo que calculamos nosotros. Nulo si el proveedor no expone saldo '
  'o si ese dia no se pudo consultar.';
