import { env } from '$env/dynamic/private';

/**
 * Server-side API helper for making authenticated requests to the Waggle backend.
 * The API key is injected server-side and never exposed to the browser.
 */
export async function apiRequest(path: string, options: RequestInit = {}): Promise<Response> {
	const url = `${env.WAGGLE_API_URL}${path}`;
	const headers = new Headers(options.headers);
	headers.set('X-API-Key', env.WAGGLE_API_KEY);
	headers.set('Content-Type', 'application/json');

	return fetch(url, {
		...options,
		headers
	});
}

/** Typed helper for GET requests. Throws on non-2xx responses. */
export async function apiGet<T>(path: string): Promise<T> {
	const res = await apiRequest(path);
	if (!res.ok) {
		throw new Error(`API error: ${res.status} ${res.statusText}`);
	}
	return res.json() as Promise<T>;
}

/** Helper for mutations (POST, PATCH, PUT, DELETE). */
export async function apiMutate(
	path: string,
	method: string,
	body?: unknown
): Promise<Response> {
	return apiRequest(path, {
		method,
		body: body ? JSON.stringify(body) : undefined
	});
}
