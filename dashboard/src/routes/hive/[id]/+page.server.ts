import { error } from '@sveltejs/kit';
import { apiGet } from '$lib/server/api';
import type { PageServerLoad } from './$types';

/** Interval presets mapped to query parameters */
const INTERVAL_MAP: Record<string, { interval: string; limit: number }> = {
	'24h': { interval: 'hourly', limit: 24 },
	'7d': { interval: 'hourly', limit: 168 },
	'30d': { interval: 'hourly', limit: 720 },
	'90d': { interval: 'hourly', limit: 2160 }
};

export const load: PageServerLoad = async ({ params, url }) => {
	const hiveId = params.id;
	const range = url.searchParams.get('range') || '7d';
	const preset = INTERVAL_MAP[range] ?? INTERVAL_MAP['7d'];

	try {
		const [hive, readings, alerts, trafficHourly, trafficHeatmap, trafficSummary, photos, photoDetections] = await Promise.all([
			apiGet<any>(`/api/hives/${hiveId}`),
			apiGet<any>(
				`/api/hives/${hiveId}/readings?interval=${preset.interval}&limit=${preset.limit}`
			),
			apiGet<any>(`/api/alerts?hive_id=${hiveId}&limit=10`),
			// Traffic: hourly for last 24h
			apiGet<any>(`/api/hives/${hiveId}/traffic?interval=hourly&limit=24&order=asc`).catch(() => ({ items: [] })),
			// Traffic: hourly for last 7 days (for heatmap)
			apiGet<any>(`/api/hives/${hiveId}/traffic?interval=hourly&limit=168&order=asc`).catch(() => ({ items: [] })),
			// Traffic: daily summary
			apiGet<any>(`/api/hives/${hiveId}/traffic/summary`).catch(() => null),
			// Photos: recent photos for this hive
			apiGet<any>(`/api/hives/${hiveId}/photos?limit=30&order=desc`).catch(() => ({ items: [] })),
			// Detections: all detections for this hive's photos
			apiGet<any>(`/api/hives/${hiveId}/photos/detections?limit=500`).catch(() => ({ items: [] })),
		]);

		return {
			hive,
			readings: readings.items ?? [],
			readingsInterval: readings.interval,
			alerts: alerts.items ?? [],
			range,
			trafficHourly: trafficHourly.items ?? [],
			trafficHeatmap: trafficHeatmap.items ?? [],
			trafficSummary,
			photos: photos.items ?? [],
			photoDetections: photoDetections.items ?? [],
		};
	} catch (err: any) {
		if (err?.message?.includes('404')) {
			error(404, 'Hive not found');
		}
		// Re-throw other errors so SvelteKit handles them
		throw err;
	}
};
