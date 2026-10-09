// See https://svelte.dev/docs/kit/types#app.d.ts
// for information about these interfaces
declare global {
  namespace App {
    // interface Error {}
    interface Locals {
      user?: any; // You might want to replace 'any' with a more specific type for user
      org?: any; // You might want to replace 'any' with a more specific type for org
      org_name?: string;
      org_settings?: {
        default_currency?: string;
        currency_symbol?: string;
        default_country?: string | null;
      };
      profile?: {
        role?: string;
        is_organization_admin?: boolean;
      };
      /**
       * De que empresa son los datos que puede pedir quien inicio sesion.
       *
       * Lo resuelve `lib/server/v2/tenant.js::tenantDeLaSesion` una vez por
       * peticion y lo deja aca para que las siguientes lecturas no vuelvan a
       * preguntarle al motor. Es cache de request, no una fuente: quien lo
       * necesita llama a `tenantDeLaSesion`, nunca lee este campo directo.
       */
      tenant?: string;
    }
    // interface PageData {}
    // interface PageState {}
    // interface Platform {}
  }
}

export {};
