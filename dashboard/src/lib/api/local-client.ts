import type { WaggleClient } from './client';

/**
 * Local mode API client.
 * Talks to the SvelteKit server API routes, which proxy to the Pi's FastAPI backend.
 * The API key is injected server-side and never exposed to the browser.
 */
export class LocalClient implements WaggleClient {
	private async fetchJson<T>(path: string): Promise<T> {
		const res = await fetch(path);
		if (!res.ok) {
			throw new Error(`API error: ${res.status} ${res.statusText}`);
		}
		return res.json() as Promise<T>;
	}

	private async mutate(path: string, method: string, body?: unknown): Promise<Response> {
		return fetch(path, {
			method,
			headers: { 'Content-Type': 'application/json' },
			body: body ? JSON.stringify(body) : undefined,
		});
	}

	async getHives(): Promise<any[]> {
		const data = await this.fetchJson<{ items: any[] }>('/api/hives');
		return data.items;
	}

	async getHive(id: number): Promise<any> {
		return this.fetchJson(`/api/hives/${id}`);
	}

	async getReadings(hiveId: number, from?: string, to?: string): Promise<any> {
		const params = new URLSearchParams();
		if (from) params.set('from', from);
		if (to) params.set('to', to);
		return this.fetchJson(`/api/hives/${hiveId}/readings?${params}`);
	}

	async getAlerts(hiveId?: number, severity?: string): Promise<any> {
		const params = new URLSearchParams();
		if (severity) params.set('severity', severity);
		const path = hiveId ? `/api/hives/${hiveId}/alerts` : '/api/alerts';
		return this.fetchJson(`${path}?${params}`);
	}

	async acknowledgeAlert(id: number, by?: string): Promise<void> {
		await this.mutate(`/api/alerts/${id}/acknowledge`, 'POST', by ? { acknowledged_by: by } : {});
	}

	async getPhotos(hiveId: number, params?: Record<string, string>): Promise<any> {
		const searchParams = new URLSearchParams(params);
		return this.fetchJson(`/api/hives/${hiveId}/photos?${searchParams}`);
	}

	async getDetections(hiveId: number, params?: Record<string, string>): Promise<any> {
		const searchParams = new URLSearchParams(params);
		return this.fetchJson(`/api/hives/${hiveId}/detections?${searchParams}`);
	}

	async getVarroa(hiveId: number, params?: Record<string, string>): Promise<any> {
		const searchParams = new URLSearchParams(params);
		return this.fetchJson(`/api/hives/${hiveId}/varroa?${searchParams}`);
	}

	async getVarroaOverview(): Promise<any> {
		return this.fetchJson('/api/varroa/overview');
	}

	async getInspections(hiveId: number): Promise<any> {
		return this.fetchJson(`/api/hives/${hiveId}/inspections`);
	}

	async createInspection(data: any): Promise<any> {
		const res = await this.mutate('/api/inspections', 'POST', data);
		return res.json();
	}

	async updateInspection(uuid: string, data: any): Promise<any> {
		const res = await this.mutate(`/api/inspections/${uuid}`, 'PUT', data);
		return res.json();
	}

	async getWeather(): Promise<any> {
		return this.fetchJson('/api/weather/current');
	}

	async getHubStatus(): Promise<any> {
		return this.fetchJson('/api/status');
	}

	async getSyncStatus(): Promise<any> {
		return this.fetchJson('/api/sync/status');
	}

	async getTraffic(hiveId: number, params?: Record<string, string>): Promise<any> {
		const searchParams = new URLSearchParams(params);
		return this.fetchJson(`/api/hives/${hiveId}/traffic?${searchParams}`);
	}
}
