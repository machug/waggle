<script lang="ts">
	interface Hive {
		id: number;
		name: string;
	}

	interface Inspection {
		id: string;
		hive_id: number;
		inspected_at: string;
		queen_seen: boolean;
		brood_pattern: string;
		treatment_type?: string | null;
		treatment_notes?: string | null;
		notes?: string | null;
		source?: string | null;
	}

	let {
		inspections = [],
		hives = []
	}: {
		inspections: Inspection[];
		hives: Hive[];
	} = $props();

	let expandedId = $state<string | null>(null);

	function toggle(id: string) {
		expandedId = expandedId === id ? null : id;
	}

	function hiveName(hiveId: number): string {
		const hive = hives.find((h) => h.id === hiveId);
		return hive ? hive.name : `Hive #${hiveId}`;
	}

	function formatDate(iso: string): string {
		const d = new Date(iso);
		return d.toLocaleDateString(undefined, {
			weekday: 'short',
			year: 'numeric',
			month: 'short',
			day: 'numeric'
		});
	}

	function broodColor(pattern: string): string {
		switch (pattern) {
			case 'excellent':
				return 'bg-green-100 text-green-800 border-green-200';
			case 'good':
				return 'bg-emerald-100 text-emerald-800 border-emerald-200';
			case 'fair':
				return 'bg-amber-100 text-amber-800 border-amber-200';
			case 'poor':
				return 'bg-red-100 text-red-800 border-red-200';
			case 'none':
				return 'bg-gray-100 text-gray-600 border-gray-200';
			default:
				return 'bg-gray-100 text-gray-600 border-gray-200';
		}
	}

	function sourceColor(source: string | null | undefined): string {
		if (source === 'cloud') return 'bg-purple-100 text-purple-700 border-purple-200';
		return 'bg-blue-100 text-blue-700 border-blue-200';
	}

	function sourceLabel(source: string | null | undefined): string {
		if (source === 'cloud') return 'cloud';
		return 'local';
	}

	function truncate(text: string, maxLen: number): string {
		if (text.length <= maxLen) return text;
		return text.slice(0, maxLen) + '...';
	}

	const sorted = $derived(
		[...inspections].sort(
			(a, b) => new Date(b.inspected_at).getTime() - new Date(a.inspected_at).getTime()
		)
	);
</script>

<div class="bg-white rounded-lg shadow-sm border border-amber-200">
	<div class="px-4 py-3 border-b border-amber-100">
		<h3 class="text-sm font-bold text-amber-900 uppercase tracking-wide">Inspection Timeline</h3>
	</div>

	{#if sorted.length === 0}
		<div class="px-4 py-12 text-center">
			<svg class="w-10 h-10 text-amber-300 mx-auto mb-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
				<path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
			</svg>
			<p class="text-sm text-gray-400">No inspections recorded yet.</p>
			<p class="text-xs text-gray-400 mt-1">Select a hive and log your first inspection.</p>
		</div>
	{:else}
		<ul class="divide-y divide-gray-100">
			{#each sorted as insp (insp.id)}
				<li>
					<button
						class="w-full text-left px-4 py-3 hover:bg-amber-50/50 transition-colors"
						onclick={() => toggle(insp.id)}
					>
						<!-- Summary row -->
						<div class="flex items-start gap-3">
							<!-- Date column -->
							<div class="shrink-0 w-24">
								<span class="text-sm font-medium text-amber-900">
									{formatDate(insp.inspected_at)}
								</span>
							</div>

							<!-- Details column -->
							<div class="flex-1 min-w-0">
								<div class="flex flex-wrap items-center gap-1.5 mb-1">
									<!-- Hive name -->
									<span class="text-sm font-medium text-gray-700">
										{hiveName(insp.hive_id)}
									</span>

									<!-- Queen seen icon -->
									{#if insp.queen_seen}
										<span
											class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-xs font-medium bg-yellow-100 text-yellow-800 border border-yellow-200"
											title="Queen seen"
										>
											<svg class="w-3 h-3" viewBox="0 0 24 24" fill="currentColor">
												<path d="M12 2l2.09 6.26L21 9.27l-5 3.64L17.18 20 12 16.77 6.82 20 8 12.91l-5-3.64 6.91-1.01z"/>
											</svg>
											Queen
										</span>
									{/if}

									<!-- Brood pattern badge -->
									<span class="inline-flex px-1.5 py-0.5 rounded text-xs font-medium border {broodColor(insp.brood_pattern)}">
										{insp.brood_pattern}
									</span>

									<!-- Treatment indicator -->
									{#if insp.treatment_type}
										<span class="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-xs font-medium bg-teal-100 text-teal-800 border border-teal-200">
											<svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
												<path stroke-linecap="round" stroke-linejoin="round" d="M9.75 3.104v5.714a2.25 2.25 0 01-.659 1.591L5 14.5M9.75 3.104c-.251.023-.501.05-.75.082m.75-.082a24.301 24.301 0 014.5 0m0 0v5.714c0 .597.237 1.17.659 1.591L19.8 15.3M14.25 3.104c.251.023.501.05.75.082M19.8 15.3l-1.57.393A9.065 9.065 0 0112 15a9.065 9.065 0 00-6.23.693L5 14.5m14.8.8l1.402 1.402c1.232 1.232.65 3.318-1.067 3.611A48.309 48.309 0 0112 21c-2.773 0-5.491-.235-8.135-.687-1.718-.293-2.3-2.379-1.067-3.61L5 14.5" />
											</svg>
											{insp.treatment_type}
										</span>
									{/if}

									<!-- Source badge -->
									<span class="inline-flex px-1.5 py-0.5 rounded-full text-xs font-medium border {sourceColor(insp.source)}">
										{sourceLabel(insp.source)}
									</span>
								</div>

								<!-- Notes excerpt (collapsed view) -->
								{#if insp.notes && expandedId !== insp.id}
									<p class="text-xs text-gray-500 leading-snug">
										{truncate(insp.notes, 100)}
									</p>
								{/if}
							</div>

							<!-- Expand chevron -->
							<div class="shrink-0 mt-1">
								<svg
									class="w-4 h-4 text-gray-400 transition-transform {expandedId === insp.id ? 'rotate-180' : ''}"
									fill="none"
									viewBox="0 0 24 24"
									stroke="currentColor"
									stroke-width="2"
								>
									<path stroke-linecap="round" stroke-linejoin="round" d="M19.5 8.25l-7.5 7.5-7.5-7.5" />
								</svg>
							</div>
						</div>
					</button>

					<!-- Expanded details -->
					{#if expandedId === insp.id}
						<div class="px-4 pb-4 pt-1 ml-27 border-t border-dashed border-amber-100">
							<dl class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
								<div>
									<dt class="text-xs text-gray-500">Queen Seen</dt>
									<dd class="font-medium text-gray-800">
										{insp.queen_seen ? 'Yes' : 'No'}
									</dd>
								</div>
								<div>
									<dt class="text-xs text-gray-500">Brood Pattern</dt>
									<dd class="font-medium text-gray-800 capitalize">{insp.brood_pattern}</dd>
								</div>
								{#if insp.treatment_type}
									<div>
										<dt class="text-xs text-gray-500">Treatment</dt>
										<dd class="font-medium text-gray-800">{insp.treatment_type}</dd>
									</div>
								{/if}
								{#if insp.treatment_notes}
									<div class="col-span-2">
										<dt class="text-xs text-gray-500">Treatment Notes</dt>
										<dd class="font-medium text-gray-800">{insp.treatment_notes}</dd>
									</div>
								{/if}
							</dl>
							{#if insp.notes}
								<div class="mt-3 pt-3 border-t border-gray-100">
									<p class="text-xs text-gray-500 mb-1">Notes</p>
									<p class="text-sm text-gray-700 whitespace-pre-line">{insp.notes}</p>
								</div>
							{/if}
						</div>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</div>
