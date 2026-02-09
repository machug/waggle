import { createClient } from '@supabase/supabase-js';
import { env } from '$env/dynamic/public';

/**
 * Supabase client for cloud mode.
 * Only initialized when PUBLIC_DASHBOARD_MODE === 'cloud'.
 */
function createSupabaseClient() {
	const url = env.PUBLIC_SUPABASE_URL;
	const key = env.PUBLIC_SUPABASE_ANON_KEY;
	if (!url || !key) {
		throw new Error('SUPABASE_URL and SUPABASE_ANON_KEY are required in cloud mode');
	}
	return createClient(url, key);
}

let _client: ReturnType<typeof createSupabaseClient> | null = null;

export function getSupabase(): ReturnType<typeof createSupabaseClient> {
	if (!_client) {
		_client = createSupabaseClient();
	}
	return _client;
}
