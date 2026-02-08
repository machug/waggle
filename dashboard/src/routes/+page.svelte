<script lang="ts">
	import HiveCard from '$lib/components/HiveCard.svelte';
	import { startPolling } from '$lib/stores/polling';

	let { data } = $props();

	// Auto-refresh every 60 seconds
	startPolling(60_000);

	const hives = $derived(data.hives ?? []);
	const criticalHiveIds = $derived(new Set(data.criticalHiveIds ?? []));
</script>

<svelte:head>
	<title>Apiary Overview | Waggle</title>
</svelte:head>

<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
	<!-- Page header -->
	<div class="mb-6">
		<h1 class="text-2xl font-bold text-amber-900">Apiary Overview</h1>
		<p class="text-sm text-gray-500 mt-1">
			{hives.length === 1 ? '1 hive' : `${hives.length} hives`} registered
		</p>
	</div>

	{#if hives.length === 0}
		<!-- Empty state -->
		<div
			class="flex flex-col items-center justify-center rounded-xl border-2 border-dashed
			       border-amber-200 bg-white py-16 px-6 text-center"
		>
			<svg
				class="w-12 h-12 text-amber-300 mb-4"
				fill="none"
				viewBox="0 0 24 24"
				stroke="currentColor"
				stroke-width="1.5"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					d="M12 9v6m3-3H9m12 0a9 9 0 11-18 0 9 9 0 0118 0z"
				/>
			</svg>
			<p class="text-gray-600 text-lg font-medium mb-1">No hives registered yet</p>
			<p class="text-gray-400 text-sm">
				Go to <a href="/settings" class="text-amber-600 hover:underline font-medium">Settings</a> to
				add your first hive.
			</p>
		</div>
	{:else}
		<!-- Hive card grid: 1 col mobile, 2 cols tablet, 3 cols desktop -->
		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
			{#each hives as hive (hive.id)}
				<HiveCard
					{hive}
					hasCriticalAlert={criticalHiveIds.has(hive.id)}
				/>
			{/each}
		</div>
	{/if}
</div>
