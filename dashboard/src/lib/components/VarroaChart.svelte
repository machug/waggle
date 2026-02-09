<script lang="ts">
	import {
		Chart,
		LineController,
		LineElement,
		PointElement,
		LinearScale,
		TimeScale,
		Filler,
		Legend,
		Title,
		Tooltip
	} from 'chart.js';
	import 'chartjs-adapter-date-fns';

	Chart.register(
		LineController,
		LineElement,
		PointElement,
		LinearScale,
		TimeScale,
		Filler,
		Legend,
		Title,
		Tooltip
	);

	interface VarroaDataPoint {
		date: string;
		mites_per_100_bees: number;
	}

	let { data = [], hiveName = '' }: { data: VarroaDataPoint[]; hiveName?: string } = $props();

	let canvas: HTMLCanvasElement = $state()!;
	let chart: Chart | null = null;
	let selectedDays = $state(30);

	const filteredData = $derived(() => {
		if (!data.length) return [];
		const cutoff = new Date();
		cutoff.setDate(cutoff.getDate() - selectedDays);
		return data.filter((d) => new Date(d.date) >= cutoff);
	});

	const TREATMENT_THRESHOLD = 3.0;

	/** Chart.js annotation plugin alternative: use a horizontal line dataset */
	function buildChart(points: VarroaDataPoint[]): Chart {
		const labels = points.map((d) => d.date);
		const values = points.map((d) => d.mites_per_100_bees);

		// Determine Y max for background bands
		const maxVal = Math.max(...values, TREATMENT_THRESHOLD + 1);
		const yMax = Math.ceil(maxVal + 0.5);

		return new Chart(canvas, {
			type: 'line',
			data: {
				labels,
				datasets: [
					// Green zone (0-1): rendered as a stacked area
					{
						label: 'Low Risk (0-1)',
						data: labels.map(() => 1),
						backgroundColor: 'rgba(34, 197, 94, 0.10)',
						borderColor: 'transparent',
						fill: 'origin',
						pointRadius: 0,
						pointHitRadius: 0,
						order: 3
					},
					// Amber zone (1-3)
					{
						label: 'Moderate Risk (1-3)',
						data: labels.map(() => TREATMENT_THRESHOLD),
						backgroundColor: 'rgba(245, 158, 11, 0.10)',
						borderColor: 'transparent',
						fill: '-1',
						pointRadius: 0,
						pointHitRadius: 0,
						order: 3
					},
					// Red zone (3+)
					{
						label: 'High Risk (3+)',
						data: labels.map(() => yMax),
						backgroundColor: 'rgba(239, 68, 68, 0.08)',
						borderColor: 'transparent',
						fill: '-1',
						pointRadius: 0,
						pointHitRadius: 0,
						order: 3
					},
					// Treatment threshold line
					{
						label: 'Treatment Threshold (3.0)',
						data: labels.map(() => TREATMENT_THRESHOLD),
						borderColor: '#ef4444',
						borderDash: [6, 4],
						borderWidth: 2,
						backgroundColor: 'transparent',
						fill: false,
						pointRadius: 0,
						pointHitRadius: 0,
						order: 2
					},
					// Actual mite data
					{
						label: hiveName ? `${hiveName} - Mites/100 Bees` : 'Mites per 100 Bees',
						data: values,
						borderColor: '#d97706',
						backgroundColor: 'rgba(217, 119, 6, 0.15)',
						fill: false,
						tension: 0.3,
						pointRadius: 3,
						pointHitRadius: 8,
						pointBackgroundColor: values.map((v) =>
							v >= TREATMENT_THRESHOLD ? '#ef4444' : v >= 1 ? '#f59e0b' : '#22c55e'
						),
						pointBorderColor: values.map((v) =>
							v >= TREATMENT_THRESHOLD ? '#ef4444' : v >= 1 ? '#f59e0b' : '#22c55e'
						),
						borderWidth: 2,
						order: 1
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				plugins: {
					legend: {
						display: false
					},
					title: {
						display: true,
						text: hiveName ? `Varroa Load - ${hiveName}` : 'Varroa Mite Load',
						font: { size: 14, weight: 'bold' },
						color: '#78350f'
					},
					tooltip: {
						filter: (tooltipItem) => {
							// Only show tooltip for the actual data line
							return tooltipItem.datasetIndex === 4;
						},
						callbacks: {
							label: (ctx) => `${ctx.parsed?.y?.toFixed(1) ?? '0.0'} mites/100 bees`
						}
					}
				},
				scales: {
					x: {
						type: 'time',
						time: {
							unit: 'day',
							tooltipFormat: 'MMM d, yyyy'
						},
						ticks: { maxTicksLimit: 10, color: '#92400e' },
						grid: { display: false }
					},
					y: {
						min: 0,
						max: yMax,
						title: {
							display: true,
							text: 'Mites / 100 Bees',
							color: '#92400e'
						},
						ticks: { color: '#92400e' },
						grid: { color: 'rgba(217, 119, 6, 0.1)' }
					}
				},
				interaction: {
					intersect: false,
					mode: 'index'
				}
			}
		});
	}

	$effect(() => {
		const points = filteredData();
		if (chart) chart.destroy();
		if (canvas && points.length > 0) {
			chart = buildChart(points);
		}
		return () => {
			chart?.destroy();
			chart = null;
		};
	});
</script>

<div class="bg-white rounded-lg shadow p-4">
	<!-- Time range selector -->
	<div class="flex items-center justify-end gap-1 mb-3">
		{#each [30, 60, 90] as days}
			<button
				class="px-3 py-1 text-sm font-medium rounded transition-colors {selectedDays === days
					? 'bg-amber-600 text-white'
					: 'text-amber-700 hover:bg-amber-100 bg-amber-50'}"
				onclick={() => (selectedDays = days)}
			>
				{days}d
			</button>
		{/each}
	</div>

	<!-- Chart area -->
	<div class="h-72">
		{#if data.length === 0}
			<div class="flex items-center justify-center h-full text-gray-400 text-sm">
				No varroa data available.
			</div>
		{:else}
			<canvas bind:this={canvas}></canvas>
		{/if}
	</div>

	<!-- Legend -->
	<div class="flex flex-wrap items-center justify-center gap-4 mt-3 text-xs text-gray-600">
		<span class="inline-flex items-center gap-1.5">
			<span class="w-3 h-3 rounded-sm bg-green-500/20 border border-green-500/40"></span>
			Low (0-1)
		</span>
		<span class="inline-flex items-center gap-1.5">
			<span class="w-3 h-3 rounded-sm bg-amber-500/20 border border-amber-500/40"></span>
			Moderate (1-3)
		</span>
		<span class="inline-flex items-center gap-1.5">
			<span class="w-3 h-3 rounded-sm bg-red-500/20 border border-red-500/40"></span>
			High (3+)
		</span>
		<span class="inline-flex items-center gap-1.5">
			<span class="w-6 border-t-2 border-dashed border-red-500"></span>
			Treatment Threshold
		</span>
	</div>
</div>
