<script lang="ts">
	import { Chart, registerables } from 'chart.js';
	import 'chartjs-adapter-date-fns';
	import { onMount, onDestroy } from 'svelte';

	Chart.register(...registerables);

	interface Reading {
		period_start?: string;
		observed_at?: string;
		avg_temp_c?: number;
		temp_c?: number;
		avg_humidity_pct?: number;
		humidity_pct?: number;
	}

	let { readings = [] }: { readings: Reading[] } = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart;

	function getTime(r: Reading): string {
		return r.period_start ?? r.observed_at ?? '';
	}

	onMount(() => {
		const labels = readings.map(getTime);
		const tempData = readings.map((r) => r.avg_temp_c ?? r.temp_c ?? null);
		const humidityData = readings.map((r) => r.avg_humidity_pct ?? r.humidity_pct ?? null);

		chart = new Chart(canvas, {
			type: 'line',
			data: {
				labels,
				datasets: [
					{
						label: 'Temperature (\u00B0C)',
						data: tempData,
						borderColor: '#dc2626',
						backgroundColor: 'rgba(220, 38, 38, 0.1)',
						fill: false,
						tension: 0.3,
						pointRadius: 0,
						pointHitRadius: 8,
						borderWidth: 2,
						yAxisID: 'y'
					},
					{
						label: 'Humidity (%)',
						data: humidityData,
						borderColor: '#2563eb',
						backgroundColor: 'rgba(37, 99, 235, 0.1)',
						fill: false,
						tension: 0.3,
						pointRadius: 0,
						pointHitRadius: 8,
						borderWidth: 2,
						yAxisID: 'y1'
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
						text: 'Environment',
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
						type: 'linear',
						position: 'left',
						title: {
							display: true,
							text: 'Temperature (\u00B0C)',
							color: '#dc2626'
						},
						ticks: { color: '#dc2626' },
						grid: { color: 'rgba(220, 38, 38, 0.08)' }
					},
					y1: {
						type: 'linear',
						position: 'right',
						title: {
							display: true,
							text: 'Humidity (%)',
							color: '#2563eb'
						},
						ticks: { color: '#2563eb' },
						grid: { drawOnChartArea: false }
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
