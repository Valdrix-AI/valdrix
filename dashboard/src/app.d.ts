/**
 * TypeScript Declarations for App
 * 
 * Extends SvelteKit's types with our Supabase integration.
 */

import type { SupabaseClient, Session, User } from '@supabase/supabase-js';

declare global {
  namespace App {
    interface Locals {
      supabase: SupabaseClient;
      getSession: () => Promise<Session | null>;
      getUser: () => Promise<User | null>;
    }
    interface PageData {
      session: Session | null;
      user: User | null;
    }
    // interface Error {}
    // interface Platform {}
  }
}

export {};
