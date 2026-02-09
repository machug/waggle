import { apiGet } from '$lib/server/api';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	try {
		const [hives, criticalAlerts] = await Promise.all([
			apiGet<any>('/api/hives?limit=50'),
			// Fetch unacknowledged critical/high alerts for POSSIBLE_SWARM and ABSCONDING
			apiGet<any>('/api/alerts?acknowledged=0&limit=200').catch(() => ({ items: [] })),
		]);

		// Build set of hive IDs with critical alerts
		const criticalHiveIds = new Set<number>();
		for (const alert of (criticalAlerts.items ?? [])) {
			if (
				(alert.type === 'POSSIBLE_SWARM' || alert.type === 'ABSCONDING') &&
				(alert.severity === 'critical' || alert.severity === 'high')
			) {
				criticalHiveIds.add(alert.hive_id);
			}
		}

		return {
			hives: hives.items ?? [],
			criticalHiveIds: Array.from(criticalHiveIds),
		};
	} catch {
		return { hives: [], criticalHiveIds: [] };
	}
};
