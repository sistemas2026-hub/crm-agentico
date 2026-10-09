-- =============================================================================
-- D28: EL ASIGNADO DEL CASO EN EL CRM  (contrato D28, §3.6)
-- =============================================================================
-- Cuando un operador toma una conversacion, el caso del CRM deberia mostrar que
-- esa persona lo esta atendiendo. Hoy eso se sincroniza desde el proxy, en el
-- momento de tomar, y solo entonces: una reasignacion posterior deja el CRM con
-- el dueño anterior, y soltar no lo toca. Asi que las dos vistas divergen y
-- nadie se entera.
--
-- LA AUTORIDAD NO CAMBIA: Dexter decide quien atiende. Lo que se agrega es la
-- via para que el CRM lo REFLEJE, de forma durable y reintentable, en vez de
-- depender de que una peticion HTTP suelta haya salido bien.
--
-- POR QUE 'asignar_caso' Y NO 'sincronizar_asignados'
-- ---------------------------------------------------
-- El efecto es aditivo y de una sola persona: poner a ESTE operador en el
-- conjunto. No es "dejar el conjunto como Dexter dice" -- eso borraria a los
-- colaboradores que alguien sumo en el CRM, y el CRM no guarda quien agrego a
-- quien, asi que no hay forma de distinguir una asignacion automatica vieja de
-- una colaboracion armada a mano. El nombre dice lo que hace.
--
-- NO HAY 'desasignar_caso'. Misma razon, y es una decision: quitar a alguien
-- sin saber quien lo puso borra trabajo que no se recupera. Soltar una
-- conversacion deja divergencia VISIBLE, no una limpieza a ciegas.

alter table asistente.sincronizaciones_externas
  drop constraint if exists sincronizaciones_tipo_check;
alter table asistente.sincronizaciones_externas
  add constraint sincronizaciones_tipo_check
  check (tipo in ('crear_caso', 'crear_ticket', 'cerrar_caso', 'cerrar_ticket',
                  'asignar_caso'));
