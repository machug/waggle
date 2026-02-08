import { json, error } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';
import { createClient } from '@supabase/supabase-js';
import type { RequestHandler } from './$types';

const BATCH_LIMIT = 20;
const SIGNED_URL_EXPIRY_SECONDS = 3600; // 1 hour

/**
 * Lazily-initialized server-side Supabase client using the service role key.
 * This grants full storage access for generating signed URLs without RLS restrictions.
 */
let _serviceClient: ReturnType<typeof createClient> | null = null;

function getServiceClient() {
	if (!_serviceClient) {
		const url = env.SUPABASE_URL;
		const key = env.SUPABASE_SERVICE_KEY;
		if (!url || !key) {
			throw new Error('SUPABASE_URL and SUPABASE_SERVICE_KEY must be set for photo signing');
		}
		_serviceClient = createClient(url, key);
	}
	return _serviceClient;
}

/**
 * POST /api/photos/sign
 *
 * Accepts { paths: string[] } and returns { urls: Record<string, string> }
 * where each key is the original storage path and each value is a signed URL
 * valid for 1 hour.
 */
export const POST: RequestHandler = async ({ request }) => {
	let body: unknown;
	try {
		body = await request.json();
	} catch {
		error(400, 'Invalid JSON body');
	}

	// Validate shape
	if (
		!body ||
		typeof body !== 'object' ||
		!('paths' in body) ||
		!Array.isArray((body as any).paths)
	) {
		error(400, 'Request body must contain a "paths" array');
	}

	const paths: string[] = (body as any).paths;

	if (paths.length === 0) {
		error(400, 'Paths array must not be empty');
	}

	if (paths.length > BATCH_LIMIT) {
		error(400, `Maximum ${BATCH_LIMIT} paths per request`);
	}

	// Validate each path is a non-empty string
	for (const p of paths) {
		if (typeof p !== 'string' || p.trim().length === 0) {
			error(400, 'Each path must be a non-empty string');
		}
	}

	try {
		const supabase = getServiceClient();

		const { data, error: storageError } = await supabase.storage
			.from('photos')
			.createSignedUrls(paths, SIGNED_URL_EXPIRY_SECONDS);

		if (storageError) {
			console.error('Supabase storage error:', storageError);
			error(500, `Storage error: ${storageError.message}`);
		}

		if (!data) {
			error(500, 'No data returned from Supabase storage');
		}

		// Build path -> signedUrl map from the response
		const urls: Record<string, string> = {};
		for (const entry of data) {
			if (entry.error) {
				console.error(`Failed to sign path "${entry.path}":`, entry.error);
				// Skip failed paths rather than failing the entire batch
				continue;
			}
			if (entry.path && entry.signedUrl) {
				urls[entry.path] = entry.signedUrl;
			}
		}

		return json({ urls });
	} catch (err) {
		// Re-throw SvelteKit HttpErrors (from error() calls above)
		if (err && typeof err === 'object' && 'status' in err) {
			throw err;
		}
		console.error('Unexpected error signing URLs:', err);
		error(500, 'Internal server error while signing photo URLs');
	}
};
