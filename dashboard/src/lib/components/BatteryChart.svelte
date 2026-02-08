<script lang="ts">
	import { Chart, registerables } from 'chart.js';
	import 'chartjs-adapter-date-fns';
	import { onMount, onDestroy } from 'svelte';

	Chart.register(...registerables);

	interface Reading {
		period_start?: string;
		observed_at?: string;
		avg_battery_v?: number;
		battery_v?: number;
	}

	let { readings = [] }: { readings: Reading[] } = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart;

	function getTime(r: Reading): string {
		return r.period_start ?? r.observed_at ?? '';
	}

	onMount(() => {
		const labels = readings.map(getTime);
		const data = readings.map((r) => r.avg_battery_v ?? r.battery_v ?? null);

		// Threshold line at 3.3V
		const thresholdData = labels.map(() => 3.3);

		chart = new Chart(canvas, {
			type: 'line',
			data: {
				labels,
				datasets: [
					{
						label: 'Battery (V)',
						data,
						borderColor: '#16a34a',
						backgroundColor: 'rgba(22, 163, 74, 0.1)',
						fill: true,
						tension: 0.3,
						pointRadius: 0,
						pointHitRadius: 8,
						borderWidth: 2
					},
					{
						label: 'Low threshold (3.3V)',
						data: thresholdData,
						borderColor: '#dc2626',
						borderDash: [6, 4],
						borderWidth: 1.5,
						pointRadius: 0,
						pointHitRadius: 0,
						fill: false
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				plugins: {
					legend: {
						display: true,
						position: 'top',
						labels: { usePointStyle: true, pointStyle: 'line', color: '#78350f' }
					},
					title: {
						display: true,
						text: 'Battery (V)',
						font: { size: 14, weight: 'bold' },
						color: '#78350f'
					}
				},
				scales: {
					x: {
						type: 'time',
						time: { tooltipFormat: 'MMM d, HH:mm' },
						ticks: { maxTicksLimit: 6, color: '#92400e' },
						grid: { display: false }
					},
					y: {
						suggestedMin: 3.0,
						suggestedMax: 4.2,
						ticks: { color: '#92400e' },
						grid: { color: 'rgba(22, 163, 74, 0.1)' }
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
