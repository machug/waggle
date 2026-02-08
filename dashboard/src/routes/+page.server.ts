import { apiGet } from '$lib/server/api';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	try {
		const hives = await apiGet<any>('/api/hives?limit=50');
		return { hives: hives.items };
	} catch {
		return { hives: [] };
	}
};
