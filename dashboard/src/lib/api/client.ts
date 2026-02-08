/**
 * Unified API client interface for Waggle dashboard.
 *
 * Selects between local (Pi proxy) and cloud (Supabase) clients
 * based on the PUBLIC_DASHBOARD_MODE environment variable.
 */

export interface WaggleClient {
	getHives(): Promise<any[]>;
	getHive(id: number): Promise<any>;
	getReadings(hiveId: number, from?: string, to?: string): Promise<any>;
	getAlerts(hiveId?: number, severity?: string): Promise<any>;
	acknowledgeAlert(id: number, by?: string): Promise<void>;
	getPhotos(hiveId: number, params?: Record<string, string>): Promise<any>;
	getDetections(hiveId: number, params?: Record<string, string>): Promise<any>;
	getVarroa(hiveId: number, params?: Record<string, string>): Promise<any>;
	getVarroaOverview(): Promise<any>;
	getInspections(hiveId: number): Promise<any>;
	createInspection(data: any): Promise<any>;
	updateInspection(uuid: string, data: any): Promise<any>;
	getWeather(): Promise<any>;
	getHubStatus(): Promise<any>;
	getSyncStatus(): Promise<any>;
	getTraffic(hiveId: number, params?: Record<string, string>): Promise<any>;
}

/**
 * Get the appropriate client based on dashboard mode.
 * Import dynamically to avoid bundling both clients.
 */
export async function getClient(): Promise<WaggleClient> {
	// This will be resolved at build time by SvelteKit
	const mode =
		typeof window !== 'undefined'
			? ((window as any).__WAGGLE_MODE__ || 'local')
			: 'local';

	if (mode === 'cloud') {
		const { CloudClient } = await import('./cloud-client');
		return new CloudClient();
	}

	const { LocalClient } = await import('./local-client');
	return new LocalClient();
}
