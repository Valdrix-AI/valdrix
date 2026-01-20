import { PUBLIC_API_URL } from '$env/static/public';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, parent, url }) => {
  const { session, user } = await parent();
  
  const startDate = url.searchParams.get('start_date');
  const endDate = url.searchParams.get('end_date');
  const provider = url.searchParams.get('provider') || '';

  if (!user || !startDate || !endDate) {
    return {
      costs: null,
      carbon: null,
      zombies: null,
      analysis: null,
      allocation: null,
      freshness: null,
      startDate,
      endDate,
      provider
    };
  }

  const headers = {
    'Authorization': `Bearer ${session?.access_token}`,
  };

  const providerQuery = provider ? `&provider=${provider}` : '';

  try {
    const [costsRes, carbonRes, zombiesRes, analyzeRes, allocationRes, freshnessRes] = await Promise.all([
      fetch(`${PUBLIC_API_URL}/costs?start_date=${startDate}&end_date=${endDate}${providerQuery}`, { headers }),
      fetch(`${PUBLIC_API_URL}/carbon?start_date=${startDate}&end_date=${endDate}${providerQuery}`, { headers }),
      fetch(`${PUBLIC_API_URL}/zombies?analyze=true${providerQuery}`, { headers }),
      fetch(`${PUBLIC_API_URL}/costs/analyze?start_date=${startDate}&end_date=${endDate}${providerQuery}`, { headers }),
      // New: Attribution allocation summary
      fetch(`${PUBLIC_API_URL}/costs/attribution/summary?start_date=${startDate}&end_date=${endDate}`, { headers }),
      // New: Data freshness indicator
      fetch(`${PUBLIC_API_URL}/costs/freshness?start_date=${startDate}&end_date=${endDate}`, { headers }),
    ]);

    const costs = costsRes.ok ? await costsRes.json() : null;
    const carbon = carbonRes.ok ? await carbonRes.json() : null;
    const zombies = zombiesRes.ok ? await zombiesRes.json() : null;
    const analysis = analyzeRes.ok ? await analyzeRes.json() : { analysis: 'Analysis unavailable.' };
    const allocation = allocationRes.ok ? await allocationRes.json() : null;
    const freshness = freshnessRes.ok ? await freshnessRes.json() : null;

    return {
      costs,
      carbon,
      zombies,
      analysis,
      allocation,
      freshness,
      startDate,
      endDate,
      provider
    };
  } catch (err: any) {
    return {
      costs: null,
      carbon: null,
      zombies: null,
      analysis: null,
      allocation: null,
      freshness: null,
      startDate,
      endDate,
      error: err.message
    };
  }
};
