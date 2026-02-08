<script lang="ts">
	import WeightChart from '$lib/components/WeightChart.svelte';
	import EnvironmentChart from '$lib/components/EnvironmentChart.svelte';
	import BatteryChart from '$lib/components/BatteryChart.svelte';
	import StatsBar from '$lib/components/StatsBar.svelte';
	import AlertFeed from '$lib/components/AlertFeed.svelte';
	import TrafficChart from '$lib/components/TrafficChart.svelte';
	import DailySummaryChart from '$lib/components/DailySummaryChart.svelte';
	import ActivityHeatmap from '$lib/components/ActivityHeatmap.svelte';
	import PhotoFeed from '$lib/components/PhotoFeed.svelte';
	import { startPolling } from '$lib/stores/polling';
	import { page } from '$app/state';

	let { data } = $props();

	startPolling(60_000);

	const hive = $derived(data.hive);
	const readings = $derived(data.readings);
	const alerts = $derived(data.alerts);
	const currentRange = $derived(data.range);

	const trafficHourly = $derived(data.trafficHourly ?? []);
	const trafficHeatmap = $derived(data.trafficHeatmap ?? []);
	const trafficSummary = $derived(data.trafficSummary);
	const photos = $derived(data.photos ?? []);
	const photoDetections = $derived(data.photoDetections ?? []);

	// The most recent reading for stats display
	const latestReading = $derived(readings.length > 0 ? readings[readings.length - 1] : null);

	const ranges = ['24h', '7d', '30d', '90d'] as const;

	function formatLastSeen(iso: string | null | undefined): string {
		if (!iso) return 'Unknown';
		const d = new Date(iso);
		const now = new Date();
		const diffMs = now.getTime() - d.getTime();
		const diffMin = Math.floor(diffMs / 60_000);

		if (diffMin < 1) return 'Just now';
		if (diffMin < 60) return `${diffMin}m ago`;
		const diffHr = Math.floor(diffMin / 60);
		if (diffHr < 24) return `${diffHr}h ago`;
		const diffDays = Math.floor(diffHr / 24);
		return `${diffDays}d ago`;
	}
</script>

<svelte:head>
	<title>{hive?.name ?? 'Hive'} - Waggle</title>
</svelte:head>

<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
	<!-- Back link -->
	<a
		href="/"
		class="inline-flex items-center gap-1 text-sm text-amber-700 hover:text-amber-900 transition-colors mb-4"
	>
		<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
			<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
		</svg>
		Back to Apiary
	</a>

	<!-- Header -->
	<div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-6">
		<div>
			<h1 class="text-2xl font-bold text-amber-900">{hive?.name ?? 'Hive'}</h1>
			{#if hive?.location}
				<p class="text-sm text-amber-700 mt-0.5">{hive.location}</p>
			{/if}
			<p class="text-xs text-gray-500 mt-1">
				Last seen: {formatLastSeen(hive?.last_seen_at)}
			</p>
		</div>

		<!-- Time range selector -->
		<div class="flex gap-1 bg-white rounded-lg shadow p-1">
			{#each ranges as r}
				<a
					href="?range={r}"
					class="px-3 py-1.5 text-sm font-medium rounded transition-colors {currentRange === r
						? 'bg-amber-600 text-white'
						: 'text-amber-700 hover:bg-amber-100'}"
				>
					{r}
				</a>
			{/each}
		</div>
	</div>

	<!-- Stats bar -->
	<div class="mb-6">
		<StatsBar latest={latestReading} />
	</div>

	<!-- Charts -->
	{#if readings.length > 0}
		<!-- Weight: full width -->
		<div class="mb-6">
			<WeightChart {readings} />
		</div>

		<!-- Traffic section (Phase 2) -->
		{#if trafficHourly.length > 0}
			<div class="mb-6">
				<h2 class="text-lg font-semibold text-amber-900 mb-3">Bee Traffic</h2>

				<!-- Traffic summary stats -->
				{#if trafficSummary}
					<div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-4">
						<div class="bg-white rounded-lg shadow-sm p-3 text-center">
							<p class="text-xs text-gray-500">Today In</p>
							<p class="text-lg font-bold text-green-600">{trafficSummary.total_in.toLocaleString()}</p>
						</div>
						<div class="bg-white rounded-lg shadow-sm p-3 text-center">
							<p class="text-xs text-gray-500">Today Out</p>
							<p class="text-lg font-bold text-orange-600">{trafficSummary.total_out.toLocaleString()}</p>
						</div>
						<div class="bg-white rounded-lg shadow-sm p-3 text-center">
							<p class="text-xs text-gray-500">Net Out</p>
							<p class="text-lg font-bold text-amber-700">{trafficSummary.net_out.toLocaleString()}</p>
						</div>
						<div class="bg-white rounded-lg shadow-sm p-3 text-center">
							<p class="text-xs text-gray-500">Activity</p>
							<p class="text-lg font-bold text-amber-700">
								{trafficSummary.activity_score != null ? trafficSummary.activity_score + '%' : '--'}
							</p>
						</div>
					</div>
				{/if}

				<!-- Hourly traffic chart -->
				<TrafficChart data={trafficHourly} />
			</div>

			<!-- Activity heatmap -->
			{#if trafficHeatmap.length > 0}
				<div class="mb-6">
					<ActivityHeatmap data={trafficHeatmap} />
				</div>
			{/if}
		{:else}
			<div class="bg-white rounded-lg shadow p-6 text-center text-gray-400 text-sm mb-6">
				No traffic data available. Phase 2 sensor required.
			</div>
		{/if}

		<!-- Photos section (Phase 3) -->
		<div class="mb-6">
			<h2 class="text-lg font-semibold text-amber-900 mb-3">Photos</h2>
			<PhotoFeed {photos} detections={photoDetections} />
		</div>

		<!-- Environment + Battery: side by side -->
		<div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
			<EnvironmentChart {readings} />
			<BatteryChart {readings} />
		</div>
	{:else}
		<div class="bg-white rounded-lg shadow p-8 text-center text-gray-400 mb-6">
			No readings available for this time range.
		</div>
	{/if}

	<!-- Alert feed -->
	<AlertFeed {alerts} />
</div>
