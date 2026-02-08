import { apiGet } from '$lib/server/api';
import type { PageServerLoad } from './$types';

interface HiveVarroa {
	hive_id: number;
	hive_name: string;
	latest_mites_per_100_bees: number;
	trend: string;
	last_updated: string;
}

interface VarroaOverviewResponse {
	items: HiveVarroa[];
}

export const load: PageServerLoad = async () => {
	try {
		const overview = await apiGet<VarroaOverviewResponse>('/api/varroa/overview');
		return {
			hives: overview.items ?? []
		};
	} catch {
		return { hives: [] };
	}
};
