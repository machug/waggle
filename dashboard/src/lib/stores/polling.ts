/**
 * Client-side polling utility.
 * Creates an interval that calls invalidateAll() to re-run all load functions,
 * keeping dashboard data fresh without a full page reload.
 */
import { invalidateAll } from '$app/navigation';
import { onDestroy } from 'svelte';

export function startPolling(intervalMs: number = 60_000) {
	const timer = setInterval(() => {
		invalidateAll();
	}, intervalMs);

	onDestroy(() => clearInterval(timer));

	return {
		stop: () => clearInterval(timer)
	};
}
