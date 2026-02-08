import { env } from '$env/dynamic/public';

/**
 * Client-side signed URL helper for Supabase Storage photos.
 *
 * In cloud mode, photo paths in the database reference Supabase Storage objects.
 * These require time-limited signed URLs to access. This module handles:
 * - Batching sign requests (max 20 per call)
 * - Client-side caching with 5-minute safety margin
 * - Passthrough in local mode (paths used as-is)
 */

const BATCH_LIMIT = 20;

/** Safety margin: reuse cached URLs only if they expire more than 5 minutes from now. */
const SAFETY_MARGIN_MS = 5 * 60 * 1000;

interface CacheEntry {
	url: string;
	expiresAt: number;
}

/** In-memory cache: storage path -> { url, expiresAt } */
const cache = new Map<string, CacheEntry>();

/**
 * Check if a cached entry is still usable (expires more than 5 minutes from now).
 */
function isCacheValid(entry: CacheEntry): boolean {
	return entry.expiresAt - Date.now() > SAFETY_MARGIN_MS;
}

/**
 * Given an array of Supabase Storage paths, return a Map of path -> accessible URL.
 *
 * In local mode (PUBLIC_DASHBOARD_MODE !== 'cloud'), returns an identity map
 * where each path maps to itself -- local photos don't need signing.
 *
 * In cloud mode, fetches signed URLs from the server route POST /api/photos/sign,
 * batching requests in groups of 20 and caching results client-side.
 */
export async function batchSignUrls(paths: string[]): Promise<Map<string, string>> {
	const result = new Map<string, string>();

	// Local mode: no signing needed, return paths as-is
	if (env.PUBLIC_DASHBOARD_MODE !== 'cloud') {
		for (const p of paths) {
			result.set(p, p);
		}
		return result;
	}

	// Separate cached vs. uncached paths
	const needsSigning: string[] = [];

	for (const p of paths) {
		const cached = cache.get(p);
		if (cached && isCacheValid(cached)) {
			result.set(p, cached.url);
		} else {
			needsSigning.push(p);
		}
	}

	if (needsSigning.length === 0) {
		return result;
	}

	// Split into batches of BATCH_LIMIT
	const batches: string[][] = [];
	for (let i = 0; i < needsSigning.length; i += BATCH_LIMIT) {
		batches.push(needsSigning.slice(i, i + BATCH_LIMIT));
	}

	// Fetch all batches in parallel
	const responses = await Promise.all(
		batches.map(async (batch) => {
			const res = await fetch('/api/photos/sign', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ paths: batch }),
			});

			if (!res.ok) {
				const text = await res.text().catch(() => 'Unknown error');
				throw new Error(`Failed to sign URLs (${res.status}): ${text}`);
			}

			return res.json() as Promise<{ urls: Record<string, string> }>;
		}),
	);

	// Server returns 1-hour signed URLs; cache them with that expiry
	const expiresAt = Date.now() + 60 * 60 * 1000;

	for (const { urls } of responses) {
		for (const [path, signedUrl] of Object.entries(urls)) {
			cache.set(path, { url: signedUrl, expiresAt });
			result.set(path, signedUrl);
		}
	}

	return result;
}
