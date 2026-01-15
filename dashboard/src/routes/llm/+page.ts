import { PUBLIC_API_URL } from '$env/static/public';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, parent }) => {
  const { session } = await parent();
  
  if (!session?.access_token) {
    return {
      usage: [],
      summary: {
        total_cost: 0,
        total_tokens: 0,
        by_model: {},
      },
    };
  }

  const res = await fetch(`${PUBLIC_API_URL}/llm/usage`, {
    headers: {
      'Authorization': `Bearer ${session.access_token}`,
    },
  });

  if (!res.ok) {
    return {
      usage: [],
      summary: {
        total_cost: 0,
        total_tokens: 0,
        by_model: {},
      },
      error: `API error: ${res.status}`,
    };
  }

  const result = await res.json();
  const usage = result.usage || [];
  
  let total_cost = 0;
  let total_tokens = 0;
  const by_model: Record<string, { tokens: number, cost: number, calls: number }> = {};

  for (const record of usage) {
    total_cost += record.cost_usd || 0;
    total_tokens += record.total_tokens || 0;
    
    const model = record.model || 'unknown';
    if (!by_model[model]) {
      by_model[model] = { tokens: 0, cost: 0, calls: 0 };
    }
    by_model[model].tokens += record.total_tokens || 0;
    by_model[model].cost += record.cost_usd || 0;
    by_model[model].calls += 1;
  }

  return {
    usage,
    summary: {
      total_cost,
      total_tokens,
      by_model,
    },
  };
};
