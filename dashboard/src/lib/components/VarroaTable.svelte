<script lang="ts">
	interface HiveVarroa {
		hive_id: number;
		hive_name: string;
		latest_mites_per_100_bees: number;
		trend: string;
		last_updated: string;
	}

	let { hives = [] }: { hives: HiveVarroa[] } = $props();

	let sortAsc = $state(false);

	const sorted = $derived(
		[...hives].sort((a, b) =>
			sortAsc
				? a.latest_mites_per_100_bees - b.latest_mites_per_100_bees
				: b.latest_mites_per_100_bees - a.latest_mites_per_100_bees
		)
	);

	function severityClass(mites: number): string {
		if (mites >= 3) return 'text-red-700 bg-red-50';
		if (mites >= 1) return 'text-amber-700 bg-amber-50';
		return 'text-green-700 bg-green-50';
	}

	function severityBadge(mites: number): string {
		if (mites >= 3) return 'bg-red-100 text-red-800 border-red-300';
		if (mites >= 1) return 'bg-amber-100 text-amber-800 border-amber-300';
		return 'bg-green-100 text-green-800 border-green-300';
	}

	function severityLabel(mites: number): string {
		if (mites >= 3) return 'High';
		if (mites >= 1) return 'Moderate';
		return 'Low';
	}

	function trendArrow(trend: string): string {
		switch (trend) {
			case 'up':
				return 'M5 15l7-7 7 7';
			case 'down':
				return 'M19 9l-7 7-7-7';
			default:
				return 'M5 12h14';
		}
	}

	function trendColor(trend: string): string {
		switch (trend) {
			case 'up':
				return 'text-red-500';
			case 'down':
				return 'text-green-500';
			default:
				return 'text-gray-400';
		}
	}

	function trendLabel(trend: string): string {
		switch (trend) {
			case 'up':
				return 'Increasing';
			case 'down':
				return 'Decreasing';
			default:
				return 'Stable';
		}
	}

	function timeAgo(dateStr: string): string {
		const date = new Date(dateStr);
		const now = new Date();
		const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

		if (seconds < 60) return 'just now';
		const minutes = Math.floor(seconds / 60);
		if (minutes < 60) return `${minutes}m ago`;
		const hours = Math.floor(minutes / 60);
		if (hours < 24) return `${hours}h ago`;
		const days = Math.floor(hours / 24);
		if (days < 30) return `${days}d ago`;
		const months = Math.floor(days / 30);
		return `${months}mo ago`;
	}
</script>

<div class="bg-white rounded-lg shadow overflow-hidden">
	<!-- Table for larger screens -->
	<div class="hidden sm:block">
		<table class="w-full">
			<thead>
				<tr class="border-b border-amber-200 bg-amber-50/50">
					<th class="px-4 py-3 text-left text-xs font-semibold text-amber-800 uppercase tracking-wider">
						Hive
					</th>
					<th class="px-4 py-3 text-left text-xs font-semibold text-amber-800 uppercase tracking-wider">
						<button
							class="inline-flex items-center gap-1 hover:text-amber-900 transition-colors"
							onclick={() => (sortAsc = !sortAsc)}
						>
							Mites / 100 Bees
							<svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								{#if sortAsc}
									<path stroke-linecap="round" stroke-linejoin="round" d="M5 15l7-7 7 7" />
								{:else}
									<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
								{/if}
							</svg>
						</button>
					</th>
					<th class="px-4 py-3 text-left text-xs font-semibold text-amber-800 uppercase tracking-wider">
						Severity
					</th>
					<th class="px-4 py-3 text-left text-xs font-semibold text-amber-800 uppercase tracking-wider">
						Trend
					</th>
					<th class="px-4 py-3 text-left text-xs font-semibold text-amber-800 uppercase tracking-wider">
						Last Updated
					</th>
				</tr>
			</thead>
			<tbody class="divide-y divide-amber-100">
				{#each sorted as hive (hive.hive_id)}
					<tr
						class="hover:bg-amber-50/50 cursor-pointer transition-colors"
						onclick={() => {
							window.location.href = `/hive/${hive.hive_id}`;
						}}
					>
						<td class="px-4 py-3">
							<span class="text-sm font-medium text-amber-900">{hive.hive_name}</span>
						</td>
						<td class="px-4 py-3">
							<span class="text-sm font-bold {severityClass(hive.latest_mites_per_100_bees)} px-2 py-0.5 rounded">
								{hive.latest_mites_per_100_bees.toFixed(1)}
							</span>
						</td>
						<td class="px-4 py-3">
							<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border {severityBadge(hive.latest_mites_per_100_bees)}">
								{severityLabel(hive.latest_mites_per_100_bees)}
							</span>
						</td>
						<td class="px-4 py-3">
							<span class="inline-flex items-center gap-1 text-sm {trendColor(hive.trend)}" title={trendLabel(hive.trend)}>
								<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
									<path stroke-linecap="round" stroke-linejoin="round" d={trendArrow(hive.trend)} />
								</svg>
								{trendLabel(hive.trend)}
							</span>
						</td>
						<td class="px-4 py-3">
							<span class="text-xs text-gray-500" title={new Date(hive.last_updated).toLocaleString()}>
								{timeAgo(hive.last_updated)}
							</span>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>

	<!-- Card layout for mobile -->
	<div class="sm:hidden divide-y divide-amber-100">
		{#each sorted as hive (hive.hive_id)}
			<a
				href="/hive/{hive.hive_id}"
				class="block p-4 hover:bg-amber-50/50 transition-colors"
			>
				<div class="flex items-center justify-between mb-2">
					<span class="text-sm font-medium text-amber-900">{hive.hive_name}</span>
					<span class="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border {severityBadge(hive.latest_mites_per_100_bees)}">
						{severityLabel(hive.latest_mites_per_100_bees)}
					</span>
				</div>
				<div class="flex items-center justify-between">
					<div class="flex items-center gap-3">
						<span class="text-lg font-bold {severityClass(hive.latest_mites_per_100_bees)} px-2 py-0.5 rounded">
							{hive.latest_mites_per_100_bees.toFixed(1)}
						</span>
						<span class="inline-flex items-center gap-1 text-sm {trendColor(hive.trend)}">
							<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2.5">
								<path stroke-linecap="round" stroke-linejoin="round" d={trendArrow(hive.trend)} />
							</svg>
						</span>
					</div>
					<span class="text-xs text-gray-500">{timeAgo(hive.last_updated)}</span>
				</div>
			</a>
		{/each}
	</div>

	{#if hives.length === 0}
		<div class="p-12 text-center">
			<svg class="w-12 h-12 text-amber-300 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
				<path stroke-linecap="round" stroke-linejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
			</svg>
			<p class="text-gray-500 text-sm">No varroa data available yet.</p>
			<p class="text-gray-400 text-xs mt-1">Data will appear once varroa analysis has been run.</p>
		</div>
	{/if}
</div>
