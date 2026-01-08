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
          event.cookies.set(key, value, { path: '/', ...options });
        },
        remove: (key, options) => {
          event.cookies.delete(key, { path: '/', ...options });
        },
      },
    }
  );

  /**
   * Get session and user - validates with Supabase
   * 
   * IMPORTANT: We use getUser() instead of getSession() for security.
   * getSession() reads from cookies (client-controlled, could be tampered).
   * getUser() verifies with Supabase servers (trusted source of truth).
   */
  event.locals.getSession = async () => {
    const { data: { session } } = await event.locals.supabase.auth.getSession();
    return session;
  };

  event.locals.getUser = async () => {
    const { data: { user } } = await event.locals.supabase.auth.getUser();
    return user;
  };

  return resolve(event, {
    // Filter out sensitive auth headers from responses
    filterSerializedResponseHeaders(name) {
      return name === 'content-range' || name === 'x-supabase-api-version';
    },
  });
};
