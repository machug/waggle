import type { WaggleClient } from './client';
import { getSupabase } from '$lib/supabase';

/**
 * Cloud mode API client.
 * Reads directly from Supabase using supabase-js.
 */
export class CloudClient implements WaggleClient {
	private get db() {
		return getSupabase();
	}

	async getHives(): Promise<any[]> {
		const { data, error } = await this.db.from('hives').select('*').order('id');
		if (error) throw error;
		return data || [];
	}

	async getHive(id: number): Promise<any> {
		const { data, error } = await this.db.from('hives').select('*').eq('id', id).single();
		if (error) throw error;
		return data;
	}

	async getReadings(hiveId: number, from?: string, to?: string): Promise<any> {
		let query = this.db.from('sensor_readings').select('*').eq('hive_id', hiveId);
		if (from) query = query.gte('observed_at', from);
		if (to) query = query.lte('observed_at', to);
		const { data, error } = await query.order('observed_at', { ascending: false }).limit(1000);
		if (error) throw error;
		return { items: data || [], total: data?.length || 0 };
	}

	async getAlerts(hiveId?: number, severity?: string): Promise<any> {
		let query = this.db.from('alerts').select('*');
		if (hiveId) query = query.eq('hive_id', hiveId);
		if (severity) query = query.eq('severity', severity);
		const { data, error } = await query.order('created_at', { ascending: false }).limit(100);
		if (error) throw error;
		return { items: data || [], total: data?.length || 0 };
	}

	async acknowledgeAlert(id: number, by?: string): Promise<void> {
		const { error } = await this.db
			.from('alerts')
			.update({
				acknowledged: true,
				acknowledged_at: new Date().toISOString(),
				acknowledged_by: by || 'dashboard',
				source: 'cloud',
			})
			.eq('id', id);
		if (error) throw error;
	}

	async getPhotos(hiveId: number, params?: Record<string, string>): Promise<any> {
		let query = this.db.from('photos').select('*').eq('hive_id', hiveId);
		if (params?.ml_status) query = query.eq('ml_status', params.ml_status);
		const { data, error } = await query.order('captured_at', { ascending: false }).limit(100);
		if (error) throw error;
		return { items: data || [], total: data?.length || 0 };
	}

	async getDetections(hiveId: number, params?: Record<string, string>): Promise<any> {
		let query = this.db.from('ml_detections').select('*').eq('hive_id', hiveId);
		if (params?.top_class) query = query.eq('top_class', params.top_class);
		const { data, error } = await query.order('detected_at', { ascending: false }).limit(100);
		if (error) throw error;
		return { items: data || [], total: data?.length || 0 };
	}

	async getVarroa(hiveId: number, params?: Record<string, string>): Promise<any> {
		// Compute varroa data from ml_detections
		const days = parseInt(params?.days || '7');
		const since = new Date(Date.now() - days * 24 * 60 * 60 * 1000).toISOString();
		const { data, error } = await this.db
			.from('ml_detections')
			.select('detected_at, varroa_count, bee_count')
			.eq('hive_id', hiveId)
			.gte('detected_at', since)
			.order('detected_at');
		if (error) throw error;
		return { items: data || [] };
	}

	async getVarroaOverview(): Promise<any> {
		// Get latest detection per hive
		const { data, error } = await this.db
			.from('ml_detections')
			.select('*')
			.order('detected_at', { ascending: false })
			.limit(100);
		if (error) throw error;
		return { items: data || [] };
	}

	async getInspections(hiveId: number): Promise<any> {
		const { data, error } = await this.db
			.from('inspections')
			.select('*')
			.eq('hive_id', hiveId)
			.order('inspected_at', { ascending: false });
		if (error) throw error;
		return { items: data || [], total: data?.length || 0 };
	}

	async createInspection(inspData: any): Promise<any> {
		const { data, error } = await this.db
			.from('inspections')
			.insert({
				...inspData,
				source: 'cloud',
			})
			.select()
			.single();
		if (error) throw error;
		return data;
	}

	async updateInspection(uuid: string, inspData: any): Promise<any> {
		const { data, error } = await this.db
			.from('inspections')
			.update({ ...inspData, source: 'cloud', updated_at: new Date().toISOString() })
			.eq('uuid', uuid)
			.select()
			.single();
		if (error) throw error;
		return data;
	}

	async getWeather(): Promise<any> {
		// In cloud mode, weather should be fetched via a SvelteKit server route
		// that calls the weather API directly (no Pi proxy needed)
		const res = await fetch('/api/weather/current');
		if (!res.ok) throw new Error(`Weather API error: ${res.status}`);
		return res.json();
	}

	async getHubStatus(): Promise<any> {
		// Hub status is Pi-only; in cloud mode return a stub
		return { api: 'cloud', version: '0.3.0', mode: 'cloud' };
	}

	async getSyncStatus(): Promise<any> {
		const { data, error } = await this.db.from('sync_state').select('*');
		if (error) throw error;
		return { items: data || [] };
	}

	async getTraffic(hiveId: number, params?: Record<string, string>): Promise<any> {
		let query = this.db.from('bee_counts').select('*').eq('hive_id', hiveId);
		if (params?.from) query = query.gte('observed_at', params.from);
		if (params?.to) query = query.lte('observed_at', params.to);
		const { data, error } = await query.order('observed_at', { ascending: false }).limit(1000);
		if (error) throw error;
		return { items: data || [], total: data?.length || 0 };
	}
}
