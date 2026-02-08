<script lang="ts">
	interface HourlyData {
		period_start: string;
		sum_total_traffic?: number;
		total_traffic?: number;
	}

	let { data = [] }: { data: HourlyData[] } = $props();

	interface DayRow {
		date: string;
		label: string;
	}

	// Build a map of "YYYY-MM-DD|hour" -> traffic value
	const trafficMap = $derived.by(() => {
		const map = new Map<string, number>();
		for (const d of data) {
			const dt = new Date(d.period_start);
			const dateStr = dt.toISOString().slice(0, 10);
			const hour = dt.getUTCHours();
			const val = d.sum_total_traffic ?? d.total_traffic ?? 0;
			const key = `${dateStr}|${hour}`;
			map.set(key, (map.get(key) ?? 0) + val);
		}
		return map;
	});

	// Determine the 7 most recent days from the data
	const days: DayRow[] = $derived.by(() => {
		const dateSet = new Set<string>();
		for (const d of data) {
			const dt = new Date(d.period_start);
			dateSet.add(dt.toISOString().slice(0, 10));
		}
		const sorted = [...dateSet].sort().slice(-7);
		return sorted.map((dateStr) => {
			const dt = new Date(dateStr + 'T00:00:00Z');
			const label = dt.toLocaleDateString('en-US', {
				weekday: 'short',
				month: 'short',
				day: 'numeric',
				timeZone: 'UTC'
			});
			return { date: dateStr, label };
		});
	});

	const maxVal = $derived.by(() => {
		let max = 0;
		for (const val of trafficMap.values()) {
			if (val > max) max = val;
		}
		return max;
	});

	function getVal(date: string, hour: number): number {
		return trafficMap.get(`${date}|${hour}`) ?? 0;
	}

	function intensityColor(val: number): string {
		if (maxVal === 0 || val === 0) return '#fefce8';
		const ratio = Math.min(val / maxVal, 1);
		const r = Math.round(254 - ratio * (254 - 245));
		const g = Math.round(243 - ratio * (243 - 158));
		const b = Math.round(199 - ratio * (199 - 11));
		return `rgb(${r}, ${g}, ${b})`;
	}
</script>

<div class="bg-white rounded-lg shadow p-4">
	<h3 class="text-sm font-semibold text-amber-900 mb-3">Activity Heatmap (7 Days)</h3>
	<div class="grid gap-px" style="grid-template-columns: 80px repeat(24, 1fr)">
		<!-- Header row -->
		<div></div>
		{#each Array(24) as _, h}
			<div class="text-[10px] text-center text-gray-400">{h}</div>
		{/each}
		<!-- Data rows -->
		{#each days as day}
			<div class="text-xs text-gray-500 pr-2 flex items-center">{day.label}</div>
			{#each Array(24) as _, h}
				{@const val = getVal(day.date, h)}
				<div
					class="aspect-square rounded-sm cursor-default"
					style="background-color: {intensityColor(val)}"
					title="{day.label} {h}:00 — {val} bees"
				></div>
			{/each}
		{/each}
	</div>
</div>
