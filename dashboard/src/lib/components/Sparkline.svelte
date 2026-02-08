<script lang="ts">
	/**
	 * Sparkline — a minimal inline SVG line chart.
	 * Renders a small weight-trend line inside a fixed viewBox.
	 * When there are fewer than 2 data points, shows a "—" placeholder.
	 */

	let { values = [], width = 80, height = 28, color = '#d97706' }: {
		values?: number[];
		width?: number;
		height?: number;
		color?: string;
	} = $props();

	const padding = 2;

	const polylinePoints = $derived.by(() => {
		if (values.length < 2) return '';

		const min = Math.min(...values);
		const max = Math.max(...values);
		const range = max - min || 1; // avoid division by zero for flat data

		const usableWidth = width - padding * 2;
		const usableHeight = height - padding * 2;

		return values
			.map((v, i) => {
				const x = padding + (i / (values.length - 1)) * usableWidth;
				const y = padding + usableHeight - ((v - min) / range) * usableHeight;
				return `${x.toFixed(1)},${y.toFixed(1)}`;
			})
			.join(' ');
	});
</script>

{#if values.length < 2}
	<span class="text-gray-400 text-xs font-mono" aria-label="No trend data">&mdash;</span>
{:else}
	<svg
		{width}
		{height}
		viewBox="0 0 {width} {height}"
		class="inline-block"
		role="img"
		aria-label="Weight trend sparkline"
	>
		<polyline
			points={polylinePoints}
			fill="none"
			stroke={color}
			stroke-width="1.5"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
	</svg>
{/if}
