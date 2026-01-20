/**
 * Server Hooks - Runs on every request
 * 
 * Purpose:
 * 1. Creates Supabase client for server-side use
 * 2. Validates and refreshes sessions
 * 3. Makes session available to routes via locals
 */

import { createServerClient } from '@supabase/ssr';
import { PUBLIC_SUPABASE_URL, PUBLIC_SUPABASE_ANON_KEY } from '$env/static/public';
import type { Handle } from '@sveltejs/kit';

export const handle: Handle = async ({ event, resolve }) => {
  // Create a Supabase client with cookie handling
  event.locals.supabase = createServerClient(
    PUBLIC_SUPABASE_URL,
    PUBLIC_SUPABASE_ANON_KEY,
    {
      cookies: {
        get: (key) => event.cookies.get(key),
        set: (key, value, options) => {
          event.cookies.set(key, value, { 
            path: '/', 
            httpOnly: true, 
            secure: true, 
            sameSite: 'strict',
            ...options 
          });
        },
        remove: (key, options) => {
          event.cookies.delete(key, { 
            path: '/', 
            httpOnly: true, 
            secure: true, 
            sameSite: 'strict',
            ...options 
          });
        },
      },
    }
  );

  event.locals.safeGetSession = async () => {
    const {
      data: { session },
    } = await event.locals.supabase.auth.getSession();
    if (!session) return { session: null, user: null };

    const {
      data: { user },
      error,
    } = await event.locals.supabase.auth.getUser();

    if (error || !user) {
      // validation failed
      return { session: null, user: null };
    }

    return { session, user };
  };

  // Auth Guard: Protect all routes starting with /dashboard
  // (Assuming dashboards are under /dashboard or we check for protected patterns)
  if (event.url.pathname.startsWith('/dashboard') || event.url.pathname.startsWith('/settings')) {
    const { session } = await event.locals.safeGetSession();
    if (!session) {
      return new Response(null, {
        status: 303,
        headers: { Location: '/login' }
      });
    }
  }


  return resolve(event, {
    // Filter out sensitive auth headers from responses
    filterSerializedResponseHeaders(name) {
      return name === 'content-range' || name === 'x-supabase-api-version';
    },
  });
};
