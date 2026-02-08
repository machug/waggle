<script lang="ts">
	import { Chart, registerables } from 'chart.js';
	import 'chartjs-adapter-date-fns';
	import { onMount, onDestroy } from 'svelte';

	Chart.register(...registerables);

	interface DailySummary {
		date: string;
		total_in: number;
		total_out: number;
		net_out: number;
		total_traffic: number;
		activity_score: number | null;
	}

	let { data = [] }: { data: DailySummary[] } = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart;

	onMount(() => {
		const labels = data.map((d) => d.date);

		chart = new Chart(canvas, {
			type: 'line',
			data: {
				labels,
				datasets: [
					{
						label: 'Total In',
						data: data.map((d) => d.total_in),
						borderColor: '#22c55e',
						backgroundColor: 'rgba(34, 197, 94, 0.1)',
						fill: false,
						tension: 0.3,
						pointRadius: 3,
						pointHitRadius: 8,
						borderWidth: 2
					},
					{
						label: 'Total Out',
						data: data.map((d) => d.total_out),
						borderColor: '#f97316',
						backgroundColor: 'rgba(249, 115, 22, 0.1)',
						fill: false,
						tension: 0.3,
						pointRadius: 3,
						pointHitRadius: 8,
						borderWidth: 2
					},
					{
						label: 'Net Out',
						data: data.map((d) => d.net_out),
						borderColor: '#d97706',
						backgroundColor: 'transparent',
						fill: false,
						tension: 0.3,
						pointRadius: 3,
						pointHitRadius: 8,
						borderWidth: 2,
						borderDash: [6, 3]
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				plugins: {
					legend: {
						display: true,
						labels: { color: '#78350f' }
					},
					title: {
						display: true,
						text: 'Daily Traffic Summary',
						font: { size: 14, weight: 'bold' },
						color: '#78350f'
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
