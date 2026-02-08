<script lang="ts">
	/**
	 * TrafficIndicator — mini in/out bar sparkline for hive cards.
	 * Shows the last N periods as tiny stacked bars.
	 */
	interface TrafficPoint {
		bees_in: number;
		bees_out: number;
	}

	let { data = [], width = 80, height = 24 }: {
		data?: TrafficPoint[];
		width?: number;
		height?: number;
	} = $props();

	const maxVal = $derived(Math.max(1, ...data.map(d => Math.max(d.bees_in, d.bees_out))));
	const barWidth = $derived(data.length > 0 ? Math.max(2, (width - (data.length - 1) * 2) / data.length) : 0);
</script>

{#if data.length < 2}
	<span class="text-gray-400 text-xs font-mono" aria-label="No traffic data">&mdash;</span>
{:else}
	<svg {width} {height} viewBox="0 0 {width} {height}" class="inline-block" role="img" aria-label="Traffic sparkline">
		{#each data as point, i}
			{@const x = i * (barWidth + 2)}
			{@const inH = (point.bees_in / maxVal) * (height / 2)}
			{@const outH = (point.bees_out / maxVal) * (height / 2)}
			<!-- In bar (green, top half, grows down from center) -->
			<rect x={x} y={height / 2 - inH} width={barWidth} height={inH} fill="#22c55e" rx="1" />
			<!-- Out bar (orange, bottom half, grows down from center) -->
			<rect x={x} y={height / 2} width={barWidth} height={outH} fill="#f97316" rx="1" />
		{/each}
	</svg>
{/if}
