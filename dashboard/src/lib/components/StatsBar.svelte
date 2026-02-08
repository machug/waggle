<script lang="ts">
	interface Reading {
		weight_kg?: number;
		avg_weight_kg?: number;
		temp_c?: number;
		avg_temp_c?: number;
		humidity_pct?: number;
		avg_humidity_pct?: number;
		battery_v?: number;
		avg_battery_v?: number;
	}

	let { latest }: { latest: Reading | null } = $props();

	function fmt(val: number | undefined | null, decimals: number = 1): string {
		if (val == null) return '--';
		return val.toFixed(decimals);
	}

	const weight = $derived(fmt(latest?.weight_kg ?? latest?.avg_weight_kg));
	const temp = $derived(fmt(latest?.temp_c ?? latest?.avg_temp_c));
	const humidity = $derived(fmt(latest?.humidity_pct ?? latest?.avg_humidity_pct));
	const battery = $derived(fmt(latest?.battery_v ?? latest?.avg_battery_v, 2));

	const batteryLow = $derived(() => {
		const v = latest?.battery_v ?? latest?.avg_battery_v;
		return v != null && v < 3.3;
	});
</script>

<div class="grid grid-cols-2 md:grid-cols-4 gap-4">
	<!-- Weight -->
	<div class="bg-white rounded-lg shadow p-4 text-center">
		<div class="text-sm font-medium text-amber-800 mb-1">Weight</div>
		<div class="text-2xl font-bold text-amber-900">{weight}</div>
		<div class="text-xs text-amber-600">kg</div>
	</div>

	<!-- Temperature -->
	<div class="bg-white rounded-lg shadow p-4 text-center">
		<div class="text-sm font-medium text-amber-800 mb-1">Temperature</div>
		<div class="text-2xl font-bold text-amber-900">{temp}</div>
		<div class="text-xs text-amber-600">&deg;C</div>
	</div>

	<!-- Humidity -->
	<div class="bg-white rounded-lg shadow p-4 text-center">
		<div class="text-sm font-medium text-amber-800 mb-1">Humidity</div>
		<div class="text-2xl font-bold text-amber-900">{humidity}</div>
		<div class="text-xs text-amber-600">%</div>
	</div>

	<!-- Battery -->
	<div class="bg-white rounded-lg shadow p-4 text-center">
		<div class="text-sm font-medium text-amber-800 mb-1">Battery</div>
		<div class="text-2xl font-bold {batteryLow() ? 'text-red-600' : 'text-amber-900'}">
			{battery}
		</div>
		<div class="text-xs {batteryLow() ? 'text-red-500' : 'text-amber-600'}">V</div>
	</div>
</div>
