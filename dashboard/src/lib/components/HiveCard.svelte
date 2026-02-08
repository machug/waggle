<script lang="ts">
	/**
	 * HiveCard — displays a single hive's status at a glance.
	 * Shows name, location, last-seen time, latest sensor readings,
	 * battery level with colour coding, and an optional weight sparkline.
	 */
	import Sparkline from './Sparkline.svelte';
	import TrafficIndicator from './TrafficIndicator.svelte';
	import ActivityBadge from './ActivityBadge.svelte';

	interface Reading {
		weight_kg: number;
		temp_c: number;
		humidity_pct: number;
		pressure_hpa: number;
		battery_v: number;
		observed_at: string;
		flags: number;
	}

	interface LatestTraffic {
		observed_at: string;
		bees_in: number;
		bees_out: number;
		net_out: number;
		total_traffic: number;
	}

	interface Hive {
		id: number;
		name: string;
		location: string | null;
		notes: string | null;
		sender_mac: string;
		last_seen_at: string | null;
		created_at: string;
		latest_reading: Reading | null;
		latest_traffic: LatestTraffic | null;
		activity_score_today: number | null;
	}

	let { hive, weightHistory = [], trafficHistory = [], hasCriticalAlert = false }: {
		hive: Hive;
		weightHistory?: number[];
		trafficHistory?: { bees_in: number; bees_out: number }[];
		hasCriticalAlert?: boolean;
	} = $props();

	// ---- battery helpers ----
	const batteryColor = $derived.by(() => {
		const v = hive.latest_reading?.battery_v;
		if (v == null) return 'text-gray-400';
		if (v >= 3.5) return 'text-green-500';
		if (v >= 3.3) return 'text-yellow-500';
		return 'text-red-500';
	});

	const batteryLabel = $derived.by(() => {
		const v = hive.latest_reading?.battery_v;
		if (v == null) return 'Unknown';
		if (v >= 3.5) return 'Good';
		if (v >= 3.3) return 'Low';
		return 'Critical';
	});

	// ---- time formatting ----
	function relativeTime(iso: string): string {
		const diff = Date.now() - new Date(iso).getTime();
		const mins = Math.floor(diff / 60_000);
		if (mins < 1) return 'just now';
		if (mins < 60) return `${mins}m ago`;
		const hrs = Math.floor(mins / 60);
		if (hrs < 24) return `${hrs}h ago`;
		const days = Math.floor(hrs / 24);
		return `${days}d ago`;
	}

	const lastSeen = $derived(
		hive.last_seen_at ? relativeTime(hive.last_seen_at) : 'never'
	);
</script>

<a
	href="/hive/{hive.id}"
	class="block rounded-xl border bg-white shadow-sm hover:shadow-md
	       transition-shadow p-5 group
	       {hasCriticalAlert ? 'border-red-400 animate-pulse' : 'border-amber-200'}"
>
	<!-- Header row -->
	<div class="flex items-start justify-between gap-2 mb-3">
		<div class="min-w-0">
			<h3
				class="text-lg font-semibold text-amber-900 truncate group-hover:text-amber-700 transition-colors"
			>
				{hive.name}
			</h3>
			{#if hive.location}
				<p class="text-sm text-gray-500 truncate">{hive.location}</p>
			{/if}
		</div>

		<!-- Battery icon -->
		<div class="flex flex-col items-center shrink-0" title="Battery: {batteryLabel}">
			<svg
				class="w-5 h-5 {batteryColor}"
				fill="currentColor"
				viewBox="0 0 24 24"
				aria-hidden="true"
			>
				<path d="M17 4h-3V2h-4v2H7a2 2 0 00-2 2v14a2 2 0 002 2h10a2 2 0 002-2V6a2 2 0 00-2-2z" />
			</svg>
			{#if hive.latest_reading}
				<span class="text-[10px] font-medium {batteryColor}">
					{hive.latest_reading.battery_v.toFixed(2)}V
				</span>
			{/if}
		</div>

		{#if hive.activity_score_today != null || hive.latest_traffic}
			<ActivityBadge score={hive.activity_score_today} />
		{/if}
	</div>

	{#if hive.latest_reading}
		<!-- Readings grid -->
		<div class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm mb-3">
			<div>
				<span class="text-gray-500">Weight</span>
				<span class="ml-1 font-medium text-amber-900">
					{hive.latest_reading.weight_kg.toFixed(1)} kg
				</span>
			</div>
			<div>
				<span class="text-gray-500">Temp</span>
				<span class="ml-1 font-medium text-amber-900">
					{hive.latest_reading.temp_c.toFixed(1)}&deg;C
				</span>
			</div>
			<div>
				<span class="text-gray-500">Humidity</span>
				<span class="ml-1 font-medium text-amber-900">
					{hive.latest_reading.humidity_pct.toFixed(0)}%
				</span>
			</div>
			<div>
				<span class="text-gray-500">Pressure</span>
				<span class="ml-1 font-medium text-amber-900">
					{hive.latest_reading.pressure_hpa.toFixed(0)} hPa
				</span>
			</div>

			{#if hive.latest_traffic}
				<div class="col-span-2 flex items-center gap-2 pt-1 border-t border-amber-50">
					<span class="text-gray-500 text-sm">Traffic</span>
					<span class="font-medium text-green-600 text-sm">{hive.latest_traffic.bees_in} in</span>
					<span class="font-medium text-orange-600 text-sm">{hive.latest_traffic.bees_out} out</span>
				</div>
			{/if}
		</div>

		<!-- Sparkline + last seen -->
		<div class="flex items-center justify-between pt-2 border-t border-amber-100">
			<div class="flex items-center gap-2">
				<Sparkline values={weightHistory} />
				{#if trafficHistory.length > 1}
					<TrafficIndicator data={trafficHistory} />
				{/if}
			</div>
			<span class="text-xs text-gray-400">
				{lastSeen}
			</span>
		</div>
	{:else}
		<!-- No data state -->
		<div class="flex items-center justify-center py-6 text-gray-400 text-sm">
			No data yet
		</div>
	{/if}
</a>
