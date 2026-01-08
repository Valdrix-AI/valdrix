/**
 * Root Layout - Server Load
 * 
 * Runs on every page load (server-side).
 * Fetches session and makes it available to all pages.
 */

import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ locals }) => {
  const session = await locals.getSession();
  const user = await locals.getUser();
  
  return {
    session,
    user,
  };
};
