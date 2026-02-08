<script lang="ts">
	import { goto, invalidateAll } from '$app/navigation';
	import { page } from '$app/state';
	import AlertEvidence from '$lib/components/AlertEvidence.svelte';

	let { data } = $props();

	// Current filter values derived from URL
	let hiveFilter = $derived(page.url.searchParams.get('hive_id') ?? '');
	let severityFilter = $derived(page.url.searchParams.get('severity') ?? '');
	let typeFilter = $derived(page.url.searchParams.get('type') ?? '');
	let statusFilter = $derived(page.url.searchParams.get('acknowledged') ?? '');

	// Track which alerts are being acknowledged
	let acknowledging = $state<Set<number>>(new Set());

	const alertTypes = [
		{ value: '', label: 'All Types' },
		{ value: 'POSSIBLE_SWARM', label: 'Possible Swarm' },
		{ value: 'ABSCONDING', label: 'Absconding' },
		{ value: 'ROBBING', label: 'Robbing' },
		{ value: 'LOW_ACTIVITY', label: 'Low Activity' },
		{ value: 'HIGH_TEMP', label: 'High Temp' },
		{ value: 'LOW_TEMP', label: 'Low Temp' },
		{ value: 'LOW_BATTERY', label: 'Low Battery' },
		{ value: 'NO_DATA', label: 'No Data' }
	];

	const severities = [
		{ value: '', label: 'All Severities' },
		{ value: 'critical', label: 'Critical' },
		{ value: 'high', label: 'High' },
		{ value: 'medium', label: 'Medium' },
		{ value: 'low', label: 'Low' }
	];

	const statuses = [
		{ value: '', label: 'All Status' },
		{ value: 'false', label: 'Unacknowledged' },
		{ value: 'true', label: 'Acknowledged' }
	];

	function applyFilters(key: string, value: string) {
		const params = new URLSearchParams(page.url.searchParams);
		if (value) {
			params.set(key, value);
		} else {
			params.delete(key);
		}
		const query = params.toString();
		goto(`/alerts${query ? `?${query}` : ''}`, { keepFocus: true });
	}

	async function acknowledgeAlert(alertId: number) {
		acknowledging.add(alertId);
		acknowledging = new Set(acknowledging);
		try {
			const res = await fetch(`/api/alerts/${alertId}/acknowledge`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ acknowledged_by: 'dashboard' })
			});
			if (res.ok) {
				await invalidateAll();
			}
		} finally {
			acknowledging.delete(alertId);
			acknowledging = new Set(acknowledging);
		}
	}

	function severityColor(severity: string): string {
		switch (severity) {
			case 'critical':
				return 'bg-red-200 text-red-800 border-red-400';
			case 'high':
				return 'bg-red-100 text-red-700 border-red-300';
			case 'medium':
				return 'bg-amber-100 text-amber-700 border-amber-300';
			case 'low':
				return 'bg-blue-100 text-blue-700 border-blue-300';
			default:
				return 'bg-gray-100 text-gray-700 border-gray-300';
		}
	}

	function severityDot(severity: string): string {
		switch (severity) {
			case 'critical':
				return 'bg-red-600';
			case 'high':
				return 'bg-red-500';
			case 'medium':
				return 'bg-amber-500';
			case 'low':
				return 'bg-blue-500';
			default:
				return 'bg-gray-500';
		}
	}

	function cardBorder(severity: string): string {
		switch (severity) {
			case 'critical':
				return 'border-l-red-600';
			case 'high':
				return 'border-l-red-500';
			case 'medium':
				return 'border-l-amber-500';
			case 'low':
				return 'border-l-blue-500';
			default:
				return 'border-l-gray-400';
		}
	}

	function alertIcon(type: string): string {
		switch (type) {
			case 'HIGH_TEMP':
				return 'M15.362 5.214A8.252 8.252 0 0112 21 8.25 8.25 0 016.038 7.047 8.287 8.287 0 009 9.601a8.983 8.983 0 013.361-6.867 8.21 8.21 0 003 2.48z'; // fire
			case 'LOW_TEMP':
				return 'M12 3v2.25m6.364.386l-1.591 1.591M21 12h-2.25m-.386 6.364l-1.591-1.591M12 18.75V21m-4.773-4.227l-1.591 1.591M5.25 12H3m4.227-4.773L5.636 5.636M15.75 12a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0z'; // sun/cold
			case 'LOW_BATTERY':
				return 'M21 10.5h.375c.621 0 1.125.504 1.125 1.125v2.25c0 .621-.504 1.125-1.125 1.125H21M3.75 18h15A2.25 2.25 0 0021 15.75v-6a2.25 2.25 0 00-2.25-2.25h-15A2.25 2.25 0 001.5 9.75v6A2.25 2.25 0 003.75 18z'; // battery
			case 'NO_DATA':
				return 'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z'; // warning triangle
			case 'POSSIBLE_SWARM':
				return 'M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z'; // clock/swarm
			case 'ABSCONDING':
				return 'M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15m3 0l3-3m0 0l-3-3m3 3H9'; // arrow-right-on-rect
			case 'ROBBING':
				return 'M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z'; // warning
			case 'LOW_ACTIVITY':
				return 'M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75z'; // chart-bar (low)
			default:
				return 'M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0'; // bell
		}
	}

	function alertTypeLabel(type: string): string {
		switch (type) {
			case 'HIGH_TEMP':
				return 'High Temp';
			case 'LOW_TEMP':
				return 'Low Temp';
			case 'LOW_BATTERY':
				return 'Low Battery';
			case 'NO_DATA':
				return 'No Data';
			case 'POSSIBLE_SWARM':
				return 'Possible Swarm';
			case 'ABSCONDING':
				return 'Absconding';
			case 'ROBBING':
				return 'Robbing';
			case 'LOW_ACTIVITY':
				return 'Low Activity';
			default:
				return type;
		}
	}

	function hiveName(hiveId: number): string {
		const hive = data.hives.find((h: any) => h.id === hiveId);
		return hive ? hive.name : `Hive #${hiveId}`;
	}

	function timeAgo(dateStr: string): string {
		const date = new Date(dateStr);
		const now = new Date();
		const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

		if (seconds < 60) return 'just now';
		const minutes = Math.floor(seconds / 60);
		if (minutes < 60) return `${minutes}m ago`;
		const hours = Math.floor(minutes / 60);
		if (hours < 24) return `${hours}h ago`;
		const days = Math.floor(hours / 24);
		if (days < 30) return `${days}d ago`;
		const months = Math.floor(days / 30);
		return `${months}mo ago`;
	}

	function formatDate(dateStr: string): string {
		return new Date(dateStr).toLocaleString();
	}

	let hasActiveFilters = $derived(
		hiveFilter !== '' || severityFilter !== '' || typeFilter !== '' || statusFilter !== ''
	);
</script>

<svelte:head>
	<title>Alerts - Waggle</title>
</svelte:head>

<div class="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
	<!-- Header -->
	<div class="mb-6">
		<h1 class="text-2xl font-bold text-amber-900">Alerts</h1>
		<p class="text-sm text-amber-700 mt-1">
			{#if data.total === 0}
				No alerts found
			{:else}
				Showing {data.alerts.length} of {data.total} alert{data.total !== 1 ? 's' : ''}
			{/if}
		</p>
	</div>

	<!-- Filter bar -->
	<div class="bg-white rounded-lg shadow-sm border border-amber-200 p-4 mb-6">
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
			<!-- Hive filter -->
			<div>
				<label for="filter-hive" class="block text-xs font-medium text-amber-800 mb-1">Hive</label>
				<select
					id="filter-hive"
					class="w-full rounded-md border border-amber-300 bg-white px-3 py-2 text-sm text-gray-800 shadow-sm focus:border-amber-500 focus:ring-1 focus:ring-amber-500 focus:outline-none"
					value={hiveFilter}
					onchange={(e) => applyFilters('hive_id', e.currentTarget.value)}
				>
					<option value="">All Hives</option>
					{#each data.hives as hive}
						<option value={String(hive.id)}>{hive.name}</option>
					{/each}
				</select>
			</div>

			<!-- Severity filter -->
			<div>
				<label for="filter-severity" class="block text-xs font-medium text-amber-800 mb-1">Severity</label>
				<select
					id="filter-severity"
					class="w-full rounded-md border border-amber-300 bg-white px-3 py-2 text-sm text-gray-800 shadow-sm focus:border-amber-500 focus:ring-1 focus:ring-amber-500 focus:outline-none"
					value={severityFilter}
					onchange={(e) => applyFilters('severity', e.currentTarget.value)}
				>
					{#each severities as s}
						<option value={s.value}>{s.label}</option>
					{/each}
				</select>
			</div>

			<!-- Type filter -->
			<div>
				<label for="filter-type" class="block text-xs font-medium text-amber-800 mb-1">Type</label>
				<select
					id="filter-type"
					class="w-full rounded-md border border-amber-300 bg-white px-3 py-2 text-sm text-gray-800 shadow-sm focus:border-amber-500 focus:ring-1 focus:ring-amber-500 focus:outline-none"
					value={typeFilter}
					onchange={(e) => applyFilters('type', e.currentTarget.value)}
				>
					{#each alertTypes as t}
						<option value={t.value}>{t.label}</option>
					{/each}
				</select>
			</div>

			<!-- Status filter -->
			<div>
				<label for="filter-status" class="block text-xs font-medium text-amber-800 mb-1">Status</label>
				<select
					id="filter-status"
					class="w-full rounded-md border border-amber-300 bg-white px-3 py-2 text-sm text-gray-800 shadow-sm focus:border-amber-500 focus:ring-1 focus:ring-amber-500 focus:outline-none"
					value={statusFilter}
					onchange={(e) => applyFilters('acknowledged', e.currentTarget.value)}
				>
					{#each statuses as s}
						<option value={s.value}>{s.label}</option>
					{/each}
				</select>
			</div>
		</div>

		{#if hasActiveFilters}
			<div class="mt-3 pt-3 border-t border-amber-100">
				<button
					class="text-xs text-amber-600 hover:text-amber-800 font-medium transition-colors"
					onclick={() => goto('/alerts')}
				>
					Clear all filters
				</button>
			</div>
		{/if}
	</div>

	<!-- Alert list -->
	{#if data.alerts.length === 0}
		<div class="bg-white rounded-lg shadow-sm border border-amber-200 p-12 text-center">
			<svg class="w-12 h-12 text-amber-300 mx-auto mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
				<path stroke-linecap="round" stroke-linejoin="round" d="M14.857 17.082a23.848 23.848 0 005.454-1.31A8.967 8.967 0 0118 9.75v-.7V9A6 6 0 006 9v.75a8.967 8.967 0 01-2.312 6.022c1.733.64 3.56 1.085 5.455 1.31m5.714 0a24.255 24.255 0 01-5.714 0m5.714 0a3 3 0 11-5.714 0" />
			</svg>
			<p class="text-gray-500 text-sm">No alerts matching your filters.</p>
		</div>
	{:else}
		<div class="space-y-3">
			{#each data.alerts as alert (alert.id)}
				<div class="bg-white rounded-lg shadow-sm border border-amber-200 border-l-4 {cardBorder(alert.severity)} overflow-hidden transition-shadow hover:shadow-md">
					<div class="p-4">
						<!-- Top row: type badge, severity badge, timestamp -->
						<div class="flex flex-wrap items-center gap-2 mb-2">
							<!-- Alert type with icon -->
							<span class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-amber-50 text-amber-800 border border-amber-200">
								<svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d={alertIcon(alert.type)} />
								</svg>
								{alertTypeLabel(alert.type)}
							</span>

							<!-- Severity badge -->
							<span class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-semibold border {severityColor(alert.severity)}">
								<span class="w-1.5 h-1.5 rounded-full {severityDot(alert.severity)}"></span>
								{alert.severity}
							</span>

							<!-- Timestamp -->
							<span class="text-xs text-gray-400 ml-auto" title={formatDate(alert.created_at)}>
								{timeAgo(alert.created_at)}
							</span>
						</div>

						<!-- Hive link -->
						<div class="mb-1">
							<a
								href="/hives/{alert.hive_id}"
								class="text-sm font-medium text-amber-700 hover:text-amber-900 hover:underline transition-colors"
							>
								{hiveName(alert.hive_id)}
							</a>
						</div>

						<!-- Message -->
						<p class="text-sm text-gray-700 mb-3">{alert.message}</p>

						<!-- Alert Evidence (correlation alerts) -->
						<AlertEvidence {alert} />

						<!-- Action row -->
						<div class="flex items-center justify-between">
							{#if alert.acknowledged}
								<span class="text-xs text-gray-400 italic">
									Acknowledged by {alert.acknowledged_by ?? 'unknown'}
									{#if alert.acknowledged_at}
										at {formatDate(alert.acknowledged_at)}
									{/if}
								</span>
							{:else}
								<button
									class="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
									onclick={() => acknowledgeAlert(alert.id)}
									disabled={acknowledging.has(alert.id)}
								>
									{#if acknowledging.has(alert.id)}
										<svg class="w-3.5 h-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
											<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
											<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
										</svg>
										Acknowledging...
									{:else}
										<svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
											<path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5" />
										</svg>
										Acknowledge
									{/if}
								</button>
							{/if}

							<!-- Full timestamp on right -->
							<span class="text-xs text-gray-400 hidden sm:inline">
								{formatDate(alert.created_at)}
							</span>
						</div>
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>
