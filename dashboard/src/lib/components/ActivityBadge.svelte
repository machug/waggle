<script lang="ts">
	/**
	 * ActivityBadge — shows hive activity level based on activity_score_today.
	 * < 20 or null: Grey "Quiet"
	 * 20-80: Green "Active"
	 * > 80: Orange "Busy"
	 */
	let { score = null }: { score?: number | null } = $props();

	const label = $derived(
		score == null || score < 20 ? 'Quiet' :
		score <= 80 ? 'Active' : 'Busy'
	);

	const classes = $derived(
		score == null || score < 20
			? 'bg-gray-100 text-gray-500 border-gray-200'
			: score <= 80
				? 'bg-green-50 text-green-700 border-green-200'
				: 'bg-orange-50 text-orange-700 border-orange-200'
	);
</script>

<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border {classes}">
	{label}
</span>
