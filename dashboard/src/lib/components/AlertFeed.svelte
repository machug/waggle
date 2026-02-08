<script lang="ts">
	interface Alert {
		id: number;
		hive_id: number;
		alert_type: string;
		severity: string;
		message: string;
		created_at: string;
		acknowledged_at: string | null;
	}

	let { alerts = [] }: { alerts: Alert[] } = $props();
	let acknowledging = $state<Set<number>>(new Set());

	function severityColor(severity: string): string {
		switch (severity) {
			case 'high':
			case 'critical':
				return 'bg-red-100 text-red-800 border-red-200';
			case 'medium':
				return 'bg-amber-100 text-amber-800 border-amber-200';
			case 'low':
			case 'info':
				return 'bg-blue-100 text-blue-800 border-blue-200';
			default:
				return 'bg-gray-100 text-gray-800 border-gray-200';
		}
	}

	function severityBadge(severity: string): string {
		switch (severity) {
			case 'high':
			case 'critical':
				return 'bg-red-600 text-white';
			case 'medium':
				return 'bg-amber-500 text-white';
			case 'low':
			case 'info':
				return 'bg-blue-500 text-white';
			default:
				return 'bg-gray-500 text-white';
		}
	}

	function formatTime(iso: string): string {
		const d = new Date(iso);
		return d.toLocaleString(undefined, {
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	async function acknowledge(alertId: number) {
		acknowledging.add(alertId);
		acknowledging = new Set(acknowledging);

		try {
			const res = await fetch(`/api/alerts/${alertId}/acknowledge`, {
				method: 'PATCH'
			});
			if (!res.ok) {
				console.error('Failed to acknowledge alert:', res.status);
			}
			// Update the alert in the local list
			const idx = alerts.findIndex((a) => a.id === alertId);
			if (idx !== -1) {
				alerts[idx] = { ...alerts[idx], acknowledged_at: new Date().toISOString() };
				alerts = [...alerts];
			}
		} catch (err) {
			console.error('Failed to acknowledge alert:', err);
		} finally {
			acknowledging.delete(alertId);
			acknowledging = new Set(acknowledging);
		}
	}
</script>

<div class="bg-white rounded-lg shadow">
	<div class="px-4 py-3 border-b border-amber-100">
		<h3 class="text-sm font-bold text-amber-900 uppercase tracking-wide">Recent Alerts</h3>
	</div>

	{#if alerts.length === 0}
		<div class="px-4 py-8 text-center text-gray-400 text-sm">
			No recent alerts for this hive.
		</div>
	{:else}
		<ul class="divide-y divide-gray-100">
			{#each alerts as alert (alert.id)}
				<li class="px-4 py-3 flex items-start gap-3 {alert.acknowledged_at ? 'opacity-60' : ''}">
					<!-- Severity badge -->
					<span
						class="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold shrink-0 mt-0.5 {severityBadge(alert.severity)}"
					>
						{alert.severity}
					</span>

					<!-- Alert content -->
					<div class="flex-1 min-w-0">
						<div class="flex items-center gap-2 mb-0.5">
							<span class="text-xs font-medium text-gray-500 uppercase">{alert.alert_type}</span>
							<span class="text-xs text-gray-400">{formatTime(alert.created_at)}</span>
						</div>
						<p class="text-sm text-gray-700 leading-snug">{alert.message}</p>
						{#if alert.acknowledged_at}
							<span class="text-xs text-green-600 mt-1 inline-block">
								Acknowledged {formatTime(alert.acknowledged_at)}
							</span>
						{/if}
					</div>

					<!-- Acknowledge button -->
					{#if !alert.acknowledged_at}
						<button
							onclick={() => acknowledge(alert.id)}
							disabled={acknowledging.has(alert.id)}
							class="shrink-0 px-3 py-1 text-xs font-medium rounded border border-amber-300 text-amber-700 hover:bg-amber-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
						>
							{acknowledging.has(alert.id) ? 'Ack...' : 'Ack'}
						</button>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</div>
