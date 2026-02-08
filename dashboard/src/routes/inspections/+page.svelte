<script lang="ts">
	import { goto, invalidateAll } from '$app/navigation';
	import { page } from '$app/state';
	import InspectionForm from '$lib/components/InspectionForm.svelte';
	import InspectionTimeline from '$lib/components/InspectionTimeline.svelte';

	let { data } = $props();

	let hiveFilter = $derived(page.url.searchParams.get('hive_id') ?? '');

	function applyHiveFilter(value: string) {
		const params = new URLSearchParams(page.url.searchParams);
		if (value) {
			params.set('hive_id', value);
		} else {
			params.delete('hive_id');
		}
		const query = params.toString();
		goto(`/inspections${query ? `?${query}` : ''}`, { keepFocus: true });
	}

	async function handleSubmitted() {
		await invalidateAll();
	}
</script>

<svelte:head>
	<title>Inspection Log - Waggle</title>
</svelte:head>

<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
	<!-- Header -->
	<div class="mb-6">
		<h1 class="text-2xl font-bold text-amber-900">Inspection Log</h1>
		<p class="text-sm text-amber-700 mt-1">
			Record hive inspections and track colony health over time.
		</p>
	</div>

	<!-- Hive filter -->
	<div class="bg-white rounded-lg shadow-sm border border-amber-200 p-4 mb-6">
		<div class="flex items-center gap-3">
			<label for="filter-hive" class="text-xs font-medium text-amber-800 shrink-0">
				Filter by Hive
			</label>
			<select
				id="filter-hive"
				class="w-full max-w-xs rounded-md border border-amber-300 bg-white px-3 py-2 text-sm text-gray-800 shadow-sm focus:border-amber-500 focus:ring-1 focus:ring-amber-500 focus:outline-none"
				value={hiveFilter}
				onchange={(e) => applyHiveFilter(e.currentTarget.value)}
			>
				<option value="">All Hives</option>
				{#each data.hives as hive}
					<option value={String(hive.id)}>{hive.name}</option>
				{/each}
			</select>
			{#if hiveFilter}
				<button
					class="text-xs text-amber-600 hover:text-amber-800 font-medium transition-colors"
					onclick={() => applyHiveFilter('')}
				>
					Clear
				</button>
			{/if}
		</div>
	</div>

	<!-- Two-column layout: form + timeline -->
	<div class="grid grid-cols-1 lg:grid-cols-12 gap-6">
		<!-- Form column -->
		<div class="lg:col-span-5">
			<InspectionForm
				hives={data.hives}
				onsubmit={handleSubmitted}
			/>
		</div>

		<!-- Timeline column -->
		<div class="lg:col-span-7">
			<InspectionTimeline
				inspections={data.inspections}
				hives={data.hives}
			/>
		</div>
	</div>
</div>
