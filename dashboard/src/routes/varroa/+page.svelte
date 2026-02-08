<script lang="ts">
	import VarroaTable from '$lib/components/VarroaTable.svelte';

	let { data } = $props();

	const hives = $derived(data.hives ?? []);

	const criticalCount = $derived(hives.filter((h: any) => h.latest_mites_per_100_bees >= 3).length);
	const moderateCount = $derived(
		hives.filter(
			(h: any) => h.latest_mites_per_100_bees >= 1 && h.latest_mites_per_100_bees < 3
		).length
	);
	const lowCount = $derived(hives.filter((h: any) => h.latest_mites_per_100_bees < 1).length);
</script>

<svelte:head>
	<title>Varroa Tracker - Waggle</title>
</svelte:head>

<div class="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
	<!-- Header -->
	<div class="mb-6">
		<h1 class="text-2xl font-bold text-amber-900">Varroa Tracker</h1>
		<p class="text-sm text-amber-700 mt-1">
			Cross-hive varroa mite load overview
		</p>
	</div>

	<!-- Summary cards -->
	{#if hives.length > 0}
		<div class="grid grid-cols-3 gap-3 mb-6">
			<div class="bg-white rounded-lg shadow-sm border-l-4 border-l-red-500 p-4 text-center">
				<p class="text-xs text-gray-500 uppercase tracking-wider">High Risk</p>
				<p class="text-2xl font-bold text-red-700">{criticalCount}</p>
				<p class="text-xs text-gray-400">hive{criticalCount !== 1 ? 's' : ''}</p>
			</div>
			<div class="bg-white rounded-lg shadow-sm border-l-4 border-l-amber-500 p-4 text-center">
				<p class="text-xs text-gray-500 uppercase tracking-wider">Moderate</p>
				<p class="text-2xl font-bold text-amber-700">{moderateCount}</p>
				<p class="text-xs text-gray-400">hive{moderateCount !== 1 ? 's' : ''}</p>
			</div>
			<div class="bg-white rounded-lg shadow-sm border-l-4 border-l-green-500 p-4 text-center">
				<p class="text-xs text-gray-500 uppercase tracking-wider">Low Risk</p>
				<p class="text-2xl font-bold text-green-700">{lowCount}</p>
				<p class="text-xs text-gray-400">hive{lowCount !== 1 ? 's' : ''}</p>
			</div>
		</div>
	{/if}

	<!-- Varroa table -->
	<VarroaTable {hives} />
</div>
