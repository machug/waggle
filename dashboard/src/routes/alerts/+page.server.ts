import { apiGet } from '$lib/server/api';
import type { PageServerLoad } from './$types';

interface Alert {
	id: number;
	hive_id: number;
	reading_id: number | null;
	type: string;
	severity: string;
	message: string;
	acknowledged: boolean;
	acknowledged_at: string | null;
	acknowledged_by: string | null;
	created_at: string;
}

interface AlertsResponse {
	items: Alert[];
	total: number;
	limit: number;
	offset: number;
}

interface Hive {
	id: number;
	name: string;
}

interface HivesResponse {
	items: Hive[];
	total: number;
}

export const load: PageServerLoad = async ({ url }) => {
	const params = new URLSearchParams();

	// Forward filter params from URL
	const hiveId = url.searchParams.get('hive_id');
	const severity = url.searchParams.get('severity');
	const type = url.searchParams.get('type');
	const acknowledged = url.searchParams.get('acknowledged');

	if (hiveId) params.set('hive_id', hiveId);
	if (severity) params.set('severity', severity);
	if (type) params.set('type', type);
	if (acknowledged) params.set('acknowledged', acknowledged);

	params.set('limit', '50');

	try {
		const [alerts, hives] = await Promise.all([
			apiGet<AlertsResponse>(`/api/alerts?${params.toString()}`),
			apiGet<HivesResponse>('/api/hives?limit=250')
		]);
		return {
			alerts: alerts.items,
			total: alerts.total,
			hives: hives.items
		};
	} catch {
		return { alerts: [], total: 0, hives: [] };
	}
};
