import { PUBLIC_API_URL } from '$env/static/public';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ fetch, parent, url }) => {
  const { session, user } = await parent();
  
  const startDate = url.searchParams.get('start_date');
  const endDate = url.searchParams.get('end_date');

  if (!user || !startDate || !endDate) {
    return {
      costs: null,
      carbon: null,
      zombies: null,
      analysis: null,
      startDate,
      endDate
    };
  }

  const headers = {
    'Authorization': `Bearer ${session?.access_token}`,
  };

  try {
    const [costsRes, carbonRes, zombiesRes, analyzeRes] = await Promise.all([
      fetch(`${PUBLIC_API_URL}/costs?start_date=${startDate}&end_date=${endDate}`, { headers }),
      fetch(`${PUBLIC_API_URL}/carbon?start_date=${startDate}&end_date=${endDate}`, { headers }),
      fetch(`${PUBLIC_API_URL}/zombies?analyze=true`, { headers }),
      fetch(`${PUBLIC_API_URL}/analyze?start_date=${startDate}&end_date=${endDate}`, { headers }),
    ]);

    const costs = costsRes.ok ? await costsRes.json() : null;
    const carbon = carbonRes.ok ? await carbonRes.json() : null;
    const zombies = zombiesRes.ok ? await zombiesRes.json() : null;
    const analysis = analyzeRes.ok ? await analyzeRes.json() : { analysis: 'Analysis unavailable.' };

    return {
      costs,
      carbon,
      zombies,
      analysis,
      startDate,
      endDate
    };
  } catch (err: any) {
    return {
      costs: null,
      carbon: null,
      zombies: null,
      analysis: null,
      startDate,
      endDate,
      error: err.message
    };
  }
};
