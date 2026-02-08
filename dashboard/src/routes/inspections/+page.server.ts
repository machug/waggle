import { apiGet } from '$lib/server/api';
import type { PageServerLoad } from './$types';

interface Hive {
	id: number;
	name: string;
}

interface HivesResponse {
	items: Hive[];
	total: number;
}

interface Inspection {
	id: string;
	hive_id: number;
	inspected_at: string;
	queen_seen: boolean;
	brood_pattern: string;
	treatment_type?: string | null;
	treatment_notes?: string | null;
	notes?: string | null;
	source?: string | null;
}

interface InspectionsResponse {
	items: Inspection[];
}

export const load: PageServerLoad = async ({ url }) => {
	const hiveId = url.searchParams.get('hive_id');

	try {
		const [hivesData, inspectionsData] = await Promise.all([
			apiGet<HivesResponse>('/api/hives?limit=250'),
			hiveId
				? apiGet<InspectionsResponse>(`/api/hives/${hiveId}/inspections`)
				: Promise.resolve({ items: [] })
		]);

		return {
			hives: hivesData.items ?? [],
			inspections: inspectionsData.items ?? [],
			selectedHiveId: hiveId ? parseInt(hiveId) : null
		};
	} catch {
		return {
			hives: [],
			inspections: [],
			selectedHiveId: hiveId ? parseInt(hiveId) : null
		};
	}
};
