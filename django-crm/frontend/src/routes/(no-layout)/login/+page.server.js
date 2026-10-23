/**
 * Login Page - Secure OAuth Implementation
 *
 * Security features:
 * - PKCE (Proof Key for Code Exchange) for authorization code protection
 * - Cryptographic state parameter for CSRF protection
 * - Server-side token exchange via Django backend (no client secret in frontend)
 * - Secure httpOnly cookies for sensitive data
 *
 * Django endpoint: POST /api/auth/google/callback/
 */

import axios from 'axios';
import { comoParametro, destinoSeguro } from '$lib/destino.js';
import { fail, redirect } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { generateCodeVerifier, generateCodeChallenge, generateState } from '$lib/utils/pkce.js';
import { describeError } from '$lib/server/log-safe.js';

const GOOGLE_AUTH_URL = 'https://accounts.google.com/o/oauth2/v2/auth';
const GOOGLE_SCOPES = ['openid', 'email', 'profile'].join(' ');

// Cookie configuration
const COOKIE_OPTIONS = {
  path: '/',
  httpOnly: true,
  sameSite: 'lax'
};

/**
 * Get secure cookie options based on environment
 * @param {number} maxAge - Cookie max age in seconds
 * @returns {object} Cookie options with secure flag for production
 */
function getCookieOptions(maxAge) {
  return {
    ...COOKIE_OPTIONS,
    secure: env.NODE_ENV === 'production',
    maxAge
  };
}

/** @type {import('@sveltejs/kit').ServerLoad} */
export async function load({ url, cookies }) {
  const code = url.searchParams.get('code');
  const returnedState = url.searchParams.get('state');
  const error = url.searchParams.get('error');
  const errorDescription = url.searchParams.get('error_description');

  // Handle OAuth error returned from Google
  if (error) {
    console.error('Google OAuth error:', error, errorDescription);
    return {
      google_url: null,
      error: errorDescription || `Error de OAuth: ${error}`
    };
  }

  // Handle OAuth callback with authorization code
  if (code) {
    return handleOAuthCallback(code, returnedState, cookies);
  }

  // Check if user is already authenticated
  const jwtAccess = cookies.get('jwt_access');
  if (jwtAccess) {
    // El destino se arrastra hasta /org: es la ultima parada antes de la app,
    // y es ahi donde se decide a donde entra la persona.
    throw redirect(307, `/org${comoParametro(url.searchParams.get('redirect'))}`);
  }

  // Generate OAuth parameters and return login URL
  return await generateOAuthUrl(
    cookies, destinoSeguro(url.searchParams.get('redirect'), ''));
}

/**
 * Handle the OAuth callback when Google redirects back with an authorization code
 * @param {string} code - Authorization code from Google
 * @param {string|null} returnedState - State parameter returned from Google
 * @param {import('@sveltejs/kit').Cookies} cookies - SvelteKit cookies
 */
async function handleOAuthCallback(code, returnedState, cookies) {
  // Retrieve and immediately clear OAuth cookies (one-time use)
  const savedState = cookies.get('oauth_state');
  const codeVerifier = cookies.get('oauth_code_verifier');

  // Clear OAuth cookies regardless of outcome
  cookies.delete('oauth_state', { path: '/' });
  cookies.delete('oauth_code_verifier', { path: '/' });
  const destinoOAuth = cookies.get('oauth_destino') || '';
  cookies.delete('oauth_destino', { path: '/' });

  // Validate state parameter (CSRF protection)
  if (!savedState || savedState !== returnedState) {
    console.error('OAuth state mismatch - possible CSRF attack');
    console.error('Expected:', savedState?.substring(0, 10) + '...');
    console.error('Received:', returnedState?.substring(0, 10) + '...');
    throw redirect(307, '/login?error=state_mismatch');
  }

  // Validate code verifier exists
  if (!codeVerifier) {
    console.error('Missing PKCE code verifier - session may have expired');
    throw redirect(307, '/login?error=session_expired');
  }

  const redirect_uri = env.GOOGLE_LOGIN_DOMAIN + '/login';

  try {
    // Exchange code for tokens via Django backend
    // The backend handles the actual token exchange with Google using the client secret.
    // PRIVATE_ (not PUBLIC_): this runs server-side, inside the frontend
    // container, so it must reach the backend by its compose service name.
    const apiUrl = env.PRIVATE_DJANGO_API_URL;
    console.log('Using API URL:', apiUrl);
    const response = await axios.post(
      `${apiUrl}/api/auth/google/callback/`,
      {
        code,
        code_verifier: codeVerifier,
        redirect_uri
      },
      {
        headers: { 'Content-Type': 'application/json' },
        timeout: 30000
      }
    );

    const { access_token, refresh_token, user } = response.data;

    // Store JWT tokens in secure httpOnly cookies
    cookies.set('jwt_access', access_token, getCookieOptions(60 * 60 * 24)); // 1 day
    cookies.set('jwt_refresh', refresh_token, getCookieOptions(60 * 60 * 24 * 365)); // 1 year
  } catch (error) {
    // Never log the raw error or the response body: the axios `config.data` for
    // this call is the authorization code plus the PKCE code_verifier, and a
    // token endpoint's response body can carry tokens.
    console.error('OAuth token exchange failed:', describeError(error));
    const errorMessage = error.response?.data?.error || error.message || 'Unknown error';

    // Provide user-friendly error messages
    let userError = 'auth_failed';
    const errStr = String(errorMessage);
    if (errStr.includes('code_verifier')) {
      userError = 'pkce_failed';
    } else if (errStr.includes('expired')) {
      userError = 'code_expired';
    }
    // Log the classification, not errorMessage: that string comes from the
    // token endpoint's response body, which does not belong in logs.
    console.error('OAuth failure classified as:', userError);

    throw redirect(307, `/login?error=${userError}`);
  }

  // Success - redirect to organization selection
  throw redirect(307, `/org${comoParametro(destinoOAuth)}`);
}

/**
 * Generate Google OAuth URL with PKCE parameters
 * @param {import('@sveltejs/kit').Cookies} cookies - SvelteKit cookies
 * @returns {Promise<object>} Object containing the Google OAuth URL
 */
async function generateOAuthUrl(cookies, destino) {
  // Sin GOOGLE_CLIENT_ID no hay a donde mandar a nadie. Hasta el 23/10/2026 se
  // armaba igual la URL con client_id=undefined (medido en produccion: 9
  // caracteres, la palabra "undefined"), y el boton principal del login
  // llevaba a una pagina de error de Google. Sin la variable, la pantalla no
  // ofrece Google y no se dejan cookies de PKCE que nadie va a usar.
  if (!env.GOOGLE_CLIENT_ID) {
    return { google_url: null };
  }

  // Generate PKCE parameters
  const codeVerifier = generateCodeVerifier();
  const codeChallenge = await generateCodeChallenge(codeVerifier);

  // Generate cryptographically random state for CSRF protection
  const state = generateState();

  // Store PKCE verifier and state in secure httpOnly cookies
  // These expire in 10 minutes - should be plenty for OAuth flow
  const oauthCookieMaxAge = 60 * 10; // 10 minutes

  cookies.set('oauth_code_verifier', codeVerifier, getCookieOptions(oauthCookieMaxAge));
  cookies.set('oauth_state', state, getCookieOptions(oauthCookieMaxAge));
  // A donde queria ir quien fue rebotado hasta aca. Viaja en una cookie y no
  // en el 'state' de OAuth porque el state es el anti-CSRF: mezclarle un dato
  // de navegacion obliga a parsearlo para compararlo, y esa comparacion es lo
  // unico que protege el intercambio. Se guarda ya validado (destinoSeguro).
  if (destino) {
    cookies.set('oauth_destino', destino, getCookieOptions(oauthCookieMaxAge));
  } else {
    cookies.delete('oauth_destino', { path: '/' });
  }

  // Build Google OAuth URL with all required parameters
  const redirect_uri = env.GOOGLE_LOGIN_DOMAIN + '/login';

  const params = new URLSearchParams({
    client_id: env.GOOGLE_CLIENT_ID,
    redirect_uri,
    response_type: 'code',
    scope: GOOGLE_SCOPES,
    state,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
    access_type: 'offline', // Request refresh token
    prompt: 'consent' // Always show consent screen (required for refresh token)
  });

  const google_login_url = `${GOOGLE_AUTH_URL}?${params.toString()}`;

  return { google_url: google_login_url };
}

/** @type {import('@sveltejs/kit').Actions} */
export const actions = {
  // Aca vivia la accion `magicLink` (pedir un enlace de acceso por correo). Se
  // quito el 23/10/2026 junto con su formulario: ese camino creaba cuentas con
  // cualquier correo, y el registro ahora esta cerrado (backend:
  // PERMITIR_AUTORREGISTRO). Queda una sola accion, con nombre por si vuelve
  // otra: SvelteKit no deja mezclar `default` con acciones con nombre.

  // Email+password sign-in. A failure HAS to reach the user -- there is no
  // "always say success" cover here, since a wrong password needs to be told
  // apart from a wrong email so someone can tell what to fix.
  password: async ({ request, cookies, url }) => {
    const formData = await request.formData();
    const email = formData.get('email');
    const password = formData.get('password');

    if (!email || !password) {
      return fail(400, { error: 'El correo y la contraseña son obligatorios' });
    }

    try {
      const apiUrl = env.PRIVATE_DJANGO_API_URL;
      const response = await axios.post(
        `${apiUrl}/api/auth/login/`,
        { email, password },
        { headers: { 'Content-Type': 'application/json' }, timeout: 10000 }
      );

      const { access_token, refresh_token } = response.data;
      const secure = env.NODE_ENV === 'production';
      cookies.set('jwt_access', access_token, {
        path: '/',
        httpOnly: true,
        sameSite: 'lax',
        secure,
        maxAge: 60 * 60 * 24 // 1 day
      });
      cookies.set('jwt_refresh', refresh_token, {
        path: '/',
        httpOnly: true,
        sameSite: 'lax',
        secure,
        maxAge: 60 * 60 * 24 * 365 // 1 year
      });
    } catch (/** @type {any} */ error) {
      const errorMessage = error.response?.data?.error || 'Correo o contraseña incorrectos';
      return fail(error.response?.status === 401 ? 401 : 400, { error: errorMessage });
    }

    throw redirect(307, `/org${comoParametro(url.searchParams.get('redirect'))}`);
  }
};
