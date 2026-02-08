<script lang="ts">
	/**
	 * WeatherOverlay — compact widget showing current weather conditions.
	 * Designed to sit in the hive detail page header area.
	 */

	interface Weather {
		temp_c: number;
		humidity_pct: number;
		conditions: string;
		icon?: string;
	}

	let { weather = null }: { weather?: Weather | null } = $props();

	/** Map common conditions text to a simple SVG weather icon path. */
	const iconPath = $derived.by(() => {
		if (weather?.icon) return null; // use external icon URL instead
		const c = weather?.conditions?.toLowerCase() ?? '';
		if (c.includes('clear') || c.includes('sunny'))
			return 'M12 2v2m0 16v2M4.93 4.93l1.41 1.41m11.32 11.32l1.41 1.41M2 12h2m16 0h2M6.34 17.66l-1.41 1.41m12.73-12.73l1.41-1.41M12 6a6 6 0 100 12 6 6 0 000-12z';
		if (c.includes('cloud'))
			return 'M6.5 19a4.5 4.5 0 01-.42-8.98A7 7 0 0119.5 12.5 3.5 3.5 0 0118 19H6.5z';
		if (c.includes('rain') || c.includes('drizzle'))
			return 'M6.5 14a4.5 4.5 0 01-.42-8.98A7 7 0 0119.5 7.5 3.5 3.5 0 0118 14H6.5zM8 17v2m4-2v2m4-2v2';
		if (c.includes('snow'))
			return 'M6.5 14a4.5 4.5 0 01-.42-8.98A7 7 0 0119.5 7.5 3.5 3.5 0 0118 14H6.5zM9 17l.5 1m5-1l.5 1m-3.5-1v1.5';
		if (c.includes('storm') || c.includes('thunder'))
			return 'M6.5 14a4.5 4.5 0 01-.42-8.98A7 7 0 0119.5 7.5 3.5 3.5 0 0118 14H6.5zM13 14l-2 4h3l-2 4';
		// default: partly cloudy
		return 'M12 3v1m4.22 1.78l.71-.71M20 12h1M17.66 17.66l.71.71M12 20v1m-4.22-1.78l-.71.71M3 12H2m3.34-5.66l-.71-.71M15.91 8.81A4 4 0 0110 13H7a3 3 0 110-6h.1';
	});
</script>

{#if weather}
	<div
		class="inline-flex items-center gap-2.5 rounded-lg bg-white/80 backdrop-blur
		       border border-amber-200 px-3 py-1.5 text-sm shadow-sm"
	>
		<!-- Weather icon -->
		{#if weather.icon}
			<img
				src={weather.icon}
				alt={weather.conditions}
				class="w-6 h-6"
			/>
		{:else if iconPath}
			<svg
				class="w-5 h-5 text-amber-600 shrink-0"
				fill="none"
				viewBox="0 0 24 24"
				stroke="currentColor"
				stroke-width="1.5"
				aria-hidden="true"
			>
				<path stroke-linecap="round" stroke-linejoin="round" d={iconPath} />
			</svg>
		{/if}

		<!-- Temperature -->
		<span class="font-semibold text-amber-900">
			{weather.temp_c.toFixed(1)}&deg;C
		</span>

		<!-- Humidity -->
		<span class="text-gray-500">
			{weather.humidity_pct.toFixed(0)}%
		</span>

		<!-- Conditions -->
		<span class="text-gray-600 hidden sm:inline">
			{weather.conditions}
		</span>
	</div>
{:else}
	<!-- Loading / no data state -->
	<div
		class="inline-flex items-center gap-2 rounded-lg bg-white/60 border border-amber-100
		       px-3 py-1.5 text-sm text-gray-400"
	>
		<svg
			class="w-4 h-4 animate-spin"
			fill="none"
			viewBox="0 0 24 24"
			aria-hidden="true"
		>
			<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
			<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
		</svg>
		Weather loading&hellip;
	</div>
{/if}
