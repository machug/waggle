import { env } from '$env/dynamic/private';
import type { LayoutServerLoad } from './$types';

export const load: LayoutServerLoad = async ({ fetch }) => {
	try {
		const res = await fetch(`${env.WAGGLE_API_URL}/api/hub/status`);
		if (res.ok) {
			return { hubStatus: await res.json() };
		}
		return { hubStatus: null };
	} catch {
		return { hubStatus: null };
	}
};
