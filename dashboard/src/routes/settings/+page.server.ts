import { apiGet } from '$lib/server/api';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	try {
		const [hives, status] = await Promise.all([
			apiGet<any>('/api/hives?limit=250'),
			apiGet<any>('/api/hub/status')
		]);
		return {
			hives: hives.items,
			hubStatus: status
		};
	} catch {
		return { hives: [], hubStatus: null };
	}
};
