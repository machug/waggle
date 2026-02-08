import { env } from '$env/dynamic/private';
import type { RequestHandler } from './$types';

const handler: RequestHandler = async ({ params, request }) => {
	const path = `/api/${params.path}`;
	const url = `${env.WAGGLE_API_URL}${path}`;

	const headers = new Headers();
	headers.set('X-API-Key', env.WAGGLE_API_KEY);

	// Only forward Content-Type when present on the incoming request (not for GET/HEAD)
	const contentType = request.headers.get('Content-Type');
	if (contentType) {
		headers.set('Content-Type', contentType);
	}

	const body =
		request.method !== 'GET' && request.method !== 'HEAD'
			? await request.text()
			: undefined;

	const response = await fetch(url, {
		method: request.method,
		headers,
		body
	});

	return new Response(response.body, {
		status: response.status,
		headers: {
			'Content-Type': response.headers.get('Content-Type') || 'application/json'
		}
	});
};

export const GET = handler;
export const POST = handler;
export const PATCH = handler;
export const PUT = handler;
export const DELETE = handler;
