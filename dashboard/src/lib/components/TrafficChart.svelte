<script lang="ts">
	import { Chart, registerables } from 'chart.js';
	import 'chartjs-adapter-date-fns';
	import { onMount, onDestroy } from 'svelte';

	Chart.register(...registerables);

	interface TrafficData {
		period_start?: string;
		observed_at?: string;
		sum_bees_in?: number;
		bees_in?: number;
		sum_bees_out?: number;
		bees_out?: number;
		sum_net_out?: number;
		net_out?: number;
	}

	let { data = [] }: { data: TrafficData[] } = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart;

	function getTime(d: TrafficData): string {
		return d.period_start ?? d.observed_at ?? '';
	}

	function getIn(d: TrafficData): number | null {
		return d.sum_bees_in ?? d.bees_in ?? null;
	}

	function getOut(d: TrafficData): number | null {
		const val = d.sum_bees_out ?? d.bees_out ?? null;
		return val !== null ? -val : null;
	}

	function getNet(d: TrafficData): number | null {
		return d.sum_net_out ?? d.net_out ?? null;
	}

	onMount(() => {
		const labels = data.map(getTime);

		chart = new Chart(canvas, {
			type: 'bar',
			data: {
				labels,
				datasets: [
					{
						label: 'Bees In',
						data: data.map(getIn),
						backgroundColor: '#22c55e',
						stack: 'traffic',
						order: 2
					},
					{
						label: 'Bees Out',
						data: data.map(getOut),
						backgroundColor: '#f97316',
						stack: 'traffic',
						order: 2
					},
					{
						type: 'line',
						label: 'Net Out',
						data: data.map(getNet),
						borderColor: '#d97706',
						backgroundColor: 'transparent',
						fill: false,
						tension: 0.3,
						pointRadius: 0,
						pointHitRadius: 8,
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
						display: true,
						labels: { color: '#78350f' }
					},
					title: {
						display: true,
						text: 'Bee Traffic (In/Out)',
						font: { size: 14, weight: 'bold' },
						color: '#78350f'
					}
				},
				scales: {
					x: {
						type: 'time',
						time: { tooltipFormat: 'MMM d, HH:mm' },
						ticks: { maxTicksLimit: 8, color: '#92400e' },
						grid: { display: false },
						stacked: true
					},
					y: {
						title: {
							display: true,
							text: 'Bees',
							color: '#92400e'
						},
						ticks: { color: '#92400e' },
						grid: { color: 'rgba(217, 119, 6, 0.1)' },
						stacked: true
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
