-- =============================================================================
--  LOS ROLES DEL SCHEDULER, CONCEDIDOS AL USUARIO QUE CORRE EL RELOJ
-- =============================================================================
--  EL PROBLEMA QUE CIERRA
--  ----------------------
--  Los tres roles del scheduler existen desde 202609141200 y NO estaban
--  concedidos a ningun usuario. Medido en produccion el 08/10/2026:
--
--    usuario: motor_user
--    roles del scheduler que existen: scheduler_coordinator, job_executor,
--                                     monitor_ro
--    roles que puede asumir: app_backend
--
--  Consecuencia: el reloj llevaba encendido desde el 22/09 --'RELOJ_HABILITADO
--  = 1' en 'motor-reloj'-- sin poder tocar una sola de sus propias tablas. Cada
--  intento de reclamar un turno moria con 'InsufficientPrivilege'. El scheduler
--  estaba construido, cableado, encendido, y la cadena nunca se cerro.
--
--  Es "codigo construido no es codigo que corre" en su version mas completa:
--  cada pieza existia y estaba probada por separado.
--
--  POR QUE A 'motor_user' Y NO A UN USUARIO PROPIO
--  -----------------------------------------------
--  Porque 'motor-reloj' se conecta con 'motor_user': comparte la credencial
--  con el motor, y eso es como esta hecho el despliegue hoy. Darle un usuario
--  propio seria mas limpio --el reloj es lo unico que deberia poder reclamar
--  turnos-- pero es un cambio de infraestructura, con su secreto nuevo que
--  rotar, y no se toma dentro de esta migracion.
--
--  LO QUE CONTIENE EL RIESGO MIENTRAS TANTO, y no es una promesa: la guarda
--  'tests/test_p2_inerte.py' comprueba sobre el grafo de imports que NINGUN
--  entrypoint --ni el motor, ni Django, ni un CMD de Dockerfile-- alcanza
--  'nucleo/programador'. El motor tendra el permiso y no tiene por donde
--  usarlo, y si alguien abriera ese camino la guarda se pone en rojo.
--
--  'monitor_ro' NO SE CONCEDE AQUI, a proposito. Es el rol del termometro
--  ('cli/salud_scheduler.py'), que esta pensado para correr desde afuera con su
--  propia credencial de solo lectura. Darselo al motor seria ampliar lo que
--  esta migracion necesita para funcionar, y una migracion que concede de mas
--  es la que nadie revisa dos veces.
--
--  QUE NO HACE ESTA MIGRACION
--  --------------------------
--  No enciende ningun trabajo. El catalogo sigue vacio y lo seguira: ninguna
--  migracion siembra un job --lo afirma 'test_p2_inerte' como uno de sus cinco
--  puntos-- y encenderlo es un gesto de operacion aparte, con
--  'cli/programar_job.py', que exige actor y motivo.
--
--  Conceder el permiso y encender el trabajo son dos decisiones distintas, y
--  esta migracion toma solo la primera.
--
--  DEPENDE DE 202609141200 (los roles) y es IDEMPOTENTE: 'grant' sobre un rol
--  ya concedido no falla ni duplica nada.
-- =============================================================================

do $$
begin
  --  Se comprueba que existan antes de conceder. Un 'grant' sobre un rol
  --  inexistente aborta la migracion entera, y el mensaje de Postgres no dice
  --  cual de los dos falto.
  if not exists (select 1 from pg_roles where rolname = 'scheduler_coordinator') then
    raise exception 'falta el rol scheduler_coordinator: aplicar antes 202609141200';
  end if;
  if not exists (select 1 from pg_roles where rolname = 'job_executor') then
    raise exception 'falta el rol job_executor: aplicar antes 202609141200';
  end if;
  if not exists (select 1 from pg_roles where rolname = 'motor_user') then
    raise exception 'falta el usuario motor_user: es con el que se conecta el reloj';
  end if;

  --  EL COORDINADOR mira el catalogo, reclama turnos y los agenda.
  execute 'grant scheduler_coordinator to motor_user';
  --  EL EJECUTOR corre el turno reclamado y lo finaliza.
  execute 'grant job_executor to motor_user';
end
$$;

-- =============================================================================
--  COMPROBACION  --  la migracion afirma su propio efecto
-- =============================================================================
--  No alcanza con que el 'grant' no haya fallado: se comprueba que el usuario
--  pueda ASUMIR los dos roles, que es lo que de verdad hacia falta. Un grant
--  que no produce esa pertenencia dejaria el mismo 'InsufficientPrivilege' que
--  esta migracion viene a cerrar, y nadie lo notaria hasta el proximo tick.
do $$
declare
  faltan text;
begin
  select string_agg(r.rolname, ', ')
    into faltan
    from (values ('scheduler_coordinator'), ('job_executor')) as r(rolname)
   where not exists (
     select 1
       from pg_auth_members m
       join pg_roles rr on rr.oid = m.roleid
       join pg_roles uu on uu.oid = m.member
      where uu.rolname = 'motor_user' and rr.rolname = r.rolname);

  if faltan is not null then
    raise exception 'motor_user sigue sin poder asumir: %', faltan;
  end if;
end
$$;
