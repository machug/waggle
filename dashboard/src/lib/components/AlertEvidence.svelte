<script lang="ts">
	/**
	 * AlertEvidence — expandable detail showing evidence data for correlation alerts.
	 * Parses the alert message to extract key values and displays them in a compact format.
	 */

	interface AlertData {
		type: string;
		message: string;
		severity: string;
	}

	let { alert }: { alert: AlertData } = $props();

	// Only show for correlation alert types
	const isCorrelation = $derived(
		['POSSIBLE_SWARM', 'ABSCONDING', 'ROBBING', 'LOW_ACTIVITY'].includes(alert.type)
		&& alert.severity === 'critical' || alert.type === 'ROBBING' || alert.type === 'LOW_ACTIVITY'
	);

	let expanded = $state(false);

	// Extract numbers from message for display
	const evidence = $derived.by(() => {
		const msg = alert.message;
		const weightMatch = msg.match(/([\d.]+)\s*kg/i);
		const netOutMatch = msg.match(/net_out\s*([\d-]+)/i);
		const trafficMatch = msg.match(/traffic\s*([\d]+)/i);
		const readingsMatch = msg.match(/(\d+)\s*readings/i);

		return {
			weight: weightMatch ? weightMatch[1] : null,
			netOut: netOutMatch ? netOutMatch[1] : null,
			traffic: trafficMatch ? trafficMatch[1] : null,
			readings: readingsMatch ? readingsMatch[1] : null,
		};
	});

	function typeDescription(type: string): string {
		switch (type) {
			case 'POSSIBLE_SWARM': return 'Significant weight loss combined with high outward bee traffic suggests a swarm event.';
			case 'ABSCONDING': return 'Sustained weight loss and outward traffic over 2+ hours indicates colony absconding.';
			case 'ROBBING': return 'High total traffic with net inward movement and weight loss suggests robbing behavior.';
			case 'LOW_ACTIVITY': return "Today's traffic is significantly below the 7-day average.";
			default: return '';
		}
	}
</script>

{#if isCorrelation}
	<div class="mt-2">
		<button
			class="text-xs text-amber-600 hover:text-amber-800 font-medium transition-colors flex items-center gap-1"
			onclick={() => expanded = !expanded}
		>
			<svg class="w-3 h-3 transition-transform {expanded ? 'rotate-90' : ''}" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
			</svg>
			{expanded ? 'Hide evidence' : 'Show evidence'}
		</button>

		{#if expanded}
			<div class="mt-2 p-3 bg-amber-50 rounded-md border border-amber-200 text-sm">
				<p class="text-gray-600 mb-2">{typeDescription(alert.type)}</p>

				<div class="grid grid-cols-2 gap-2 text-xs">
					{#if evidence.weight}
						<div>
							<span class="text-gray-500">Weight change:</span>
							<span class="font-medium text-red-600">{evidence.weight} kg</span>
						</div>
					{/if}
					{#if evidence.netOut}
						<div>
							<span class="text-gray-500">Net out:</span>
							<span class="font-medium text-amber-700">{evidence.netOut}</span>
						</div>
					{/if}
					{#if evidence.traffic}
						<div>
							<span class="text-gray-500">Total traffic:</span>
							<span class="font-medium text-amber-700">{evidence.traffic}</span>
						</div>
					{/if}
					{#if evidence.readings}
						<div>
							<span class="text-gray-500">Readings:</span>
							<span class="font-medium text-gray-700">{evidence.readings}</span>
						</div>
					{/if}
				</div>
			</div>
		{/if}
	</div>
{/if}
