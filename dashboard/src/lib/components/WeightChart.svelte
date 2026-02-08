<script lang="ts">
	import { Chart, registerables } from 'chart.js';
	import 'chartjs-adapter-date-fns';
	import { onMount, onDestroy } from 'svelte';

	Chart.register(...registerables);

	interface Reading {
		period_start?: string;
		observed_at?: string;
		avg_weight_kg?: number;
		weight_kg?: number;
		min_weight_kg?: number;
		max_weight_kg?: number;
	}

	let { readings = [] }: { readings: Reading[] } = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart;

	function getTime(r: Reading): string {
		return r.period_start ?? r.observed_at ?? '';
	}

	function getWeight(r: Reading): number | null {
		return r.avg_weight_kg ?? r.weight_kg ?? null;
	}

	onMount(() => {
		const labels = readings.map(getTime);
		const data = readings.map(getWeight);

		chart = new Chart(canvas, {
			type: 'line',
			data: {
				labels,
				datasets: [
					{
						label: 'Weight (kg)',
						data,
						borderColor: '#d97706',
						backgroundColor: 'rgba(217, 119, 6, 0.1)',
						fill: true,
						tension: 0.3,
						pointRadius: 0,
						pointHitRadius: 8,
						borderWidth: 2
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				plugins: {
					legend: { display: false },
					title: {
						display: true,
						text: 'Weight (kg)',
						font: { size: 14, weight: 'bold' },
						color: '#78350f'
					}
				},
				scales: {
					x: {
						type: 'time',
						time: { tooltipFormat: 'MMM d, HH:mm' },
						ticks: { maxTicksLimit: 8, color: '#92400e' },
						grid: { display: false }
					},
					y: {
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
	});

	onDestroy(() => chart?.destroy());
</script>

<div class="bg-white rounded-lg shadow p-4">
	<div class="h-64">
		<canvas bind:this={canvas}></canvas>
	</div>
</div>
