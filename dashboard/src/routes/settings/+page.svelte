<script lang="ts">
	import { invalidateAll } from '$app/navigation';

	let { data } = $props();

	// --- Hive CRUD state ---
	let showAddForm = $state(false);
	let editingHiveId = $state<number | null>(null);
	let error = $state('');
	let success = $state('');
	let loading = $state(false);

	// Add form fields
	let addId = $state(1);
	let addName = $state('');
	let addLocation = $state('');
	let addMac = $state('');

	// Edit form fields
	let editName = $state('');
	let editLocation = $state('');

	// Auto-clear success messages
	function flashSuccess(msg: string) {
		success = msg;
		error = '';
		setTimeout(() => {
			success = '';
		}, 3000);
	}

	function resetAddForm() {
		addId = 1;
		addName = '';
		addLocation = '';
		addMac = '';
		showAddForm = false;
		error = '';
	}

	function validateAddForm(): string | null {
		if (addId < 1 || addId > 250) return 'Hive ID must be between 1 and 250.';
		if (!addName.trim()) return 'Hive name is required.';
		if (addMac.trim() && !/^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$/.test(addMac.trim())) {
			return 'MAC address must be in format AA:BB:CC:DD:EE:FF.';
		}
		return null;
	}

	async function createHive() {
		const validationError = validateAddForm();
		if (validationError) {
			error = validationError;
			return;
		}

		loading = true;
		error = '';

		const body: any = { id: addId, name: addName.trim() };
		if (addLocation.trim()) body.location = addLocation.trim();
		if (addMac.trim()) body.sender_mac = addMac.trim().toUpperCase();

		try {
			const res = await fetch('/api/hives', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body)
			});

			if (!res.ok) {
				const errBody = await res.json().catch(() => null);
				error = errBody?.detail || `Failed to create hive (${res.status})`;
				return;
			}

			resetAddForm();
			flashSuccess('Hive created successfully.');
			await invalidateAll();
		} catch (e) {
			error = 'Network error creating hive.';
		} finally {
			loading = false;
		}
	}

	function startEdit(hive: any) {
		editingHiveId = hive.id;
		editName = hive.name ?? '';
		editLocation = hive.location ?? '';
		error = '';
	}

	function cancelEdit() {
		editingHiveId = null;
		error = '';
	}

	async function updateHive(id: number) {
		if (!editName.trim()) {
			error = 'Hive name is required.';
			return;
		}

		loading = true;
		error = '';

		try {
			const res = await fetch(`/api/hives/${id}`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					name: editName.trim(),
					location: editLocation.trim() || null
				})
			});

			if (!res.ok) {
				const errBody = await res.json().catch(() => null);
				error = errBody?.detail || `Failed to update hive (${res.status})`;
				return;
			}

			editingHiveId = null;
			flashSuccess('Hive updated successfully.');
			await invalidateAll();
		} catch (e) {
			error = 'Network error updating hive.';
		} finally {
			loading = false;
		}
	}

	async function deleteHive(hive: any) {
		if (!confirm(`Delete hive "${hive.name}" (ID ${hive.id})? This cannot be undone.`)) return;

		loading = true;
		error = '';

		try {
			const res = await fetch(`/api/hives/${hive.id}`, { method: 'DELETE' });

			if (!res.ok) {
				const errBody = await res.json().catch(() => null);
				error = errBody?.detail || `Failed to delete hive (${res.status})`;
				return;
			}

			flashSuccess('Hive deleted successfully.');
			await invalidateAll();
		} catch (e) {
			error = 'Network error deleting hive.';
		} finally {
			loading = false;
		}
	}

	// --- Hub status helpers ---
	const hubStatus = $derived(data.hubStatus);
	const hives = $derived(data.hives ?? []);

	function formatUptime(seconds: number | null | undefined): string {
		if (seconds == null) return '--';
		const d = Math.floor(seconds / 86400);
		const h = Math.floor((seconds % 86400) / 3600);
		const m = Math.floor((seconds % 3600) / 60);
		if (d > 0) return `${d}d ${h}h ${m}m`;
		if (h > 0) return `${h}h ${m}m`;
		return `${m}m`;
	}

	function formatDiskFree(mb: number | null | undefined): string {
		if (mb == null) return '--';
		if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
		return `${Math.round(mb)} MB`;
	}

	function formatLastSeen(ts: string | null | undefined): string {
		if (!ts) return 'Never';
		const d = new Date(ts);
		const now = new Date();
		const diffMs = now.getTime() - d.getTime();
		const diffMin = Math.floor(diffMs / 60000);
		if (diffMin < 1) return 'Just now';
		if (diffMin < 60) return `${diffMin}m ago`;
		const diffH = Math.floor(diffMin / 60);
		if (diffH < 24) return `${diffH}h ago`;
		const diffD = Math.floor(diffH / 24);
		return `${diffD}d ago`;
	}

	type ServiceKey = 'bridge' | 'worker' | 'mqtt' | 'api';
	const serviceLabels: Record<ServiceKey, string> = {
		bridge: 'ESP-NOW Bridge',
		worker: 'Worker',
		mqtt: 'MQTT Broker',
		api: 'API Server'
	};
</script>

<svelte:head>
	<title>Settings | Waggle</title>
</svelte:head>

<div class="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-8">
	<h1 class="text-2xl font-bold text-amber-900">Settings</h1>

	<!-- Feedback messages -->
	{#if error}
		<div class="bg-red-50 border border-red-200 text-red-700 px-4 py-3 rounded-lg text-sm">
			{error}
		</div>
	{/if}
	{#if success}
		<div class="bg-green-50 border border-green-200 text-green-700 px-4 py-3 rounded-lg text-sm">
			{success}
		</div>
	{/if}

	<!-- ==================== Hub Status ==================== -->
	<section>
		<h2 class="text-lg font-semibold text-amber-800 mb-3">Hub Status</h2>

		{#if hubStatus}
			<div class="bg-white rounded-lg shadow p-5 space-y-5">
				<!-- Overview stats -->
				<div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
					<div class="text-center">
						<p class="text-xs text-gray-500 uppercase tracking-wide">Uptime</p>
						<p class="text-lg font-semibold text-amber-900 mt-1">
							{formatUptime(hubStatus.uptime_seconds)}
						</p>
					</div>
					<div class="text-center">
						<p class="text-xs text-gray-500 uppercase tracking-wide">Disk Free</p>
						<p class="text-lg font-semibold text-amber-900 mt-1">
							{formatDiskFree(hubStatus.disk_free_mb)}
						</p>
					</div>
					<div class="text-center">
						<p class="text-xs text-gray-500 uppercase tracking-wide">Hives</p>
						<p class="text-lg font-semibold text-amber-900 mt-1">
							{hubStatus.hive_count ?? '--'}
						</p>
					</div>
					<div class="text-center">
						<p class="text-xs text-gray-500 uppercase tracking-wide">Readings</p>
						<p class="text-lg font-semibold text-amber-900 mt-1">
							{hubStatus.reading_count?.toLocaleString() ?? '--'}
						</p>
					</div>
				</div>

				<!-- Service health -->
				<div>
					<h3 class="text-sm font-medium text-gray-600 mb-2">Services</h3>
					<div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
						{#each Object.entries(serviceLabels) as [key, label]}
							{@const status = hubStatus.services?.[key]}
							{@const isUp = status === 'running' || status === 'ok' || status === true}
							<div
								class="flex items-center gap-2 bg-gray-50 rounded-md px-3 py-2"
							>
								<span
									class="w-2.5 h-2.5 rounded-full shrink-0 {isUp
										? 'bg-green-500'
										: 'bg-red-500'}"
								></span>
								<span class="text-sm text-gray-700">{label}</span>
							</div>
						{/each}
					</div>
				</div>
			</div>
		{:else}
			<div class="bg-white rounded-lg shadow p-5 text-center text-gray-400">
				Hub status unavailable.
			</div>
		{/if}
	</section>

	<!-- ==================== Hive Management ==================== -->
	<section>
		<div class="flex items-center justify-between mb-3">
			<h2 class="text-lg font-semibold text-amber-800">Hive Management</h2>
			{#if !showAddForm}
				<button
					onclick={() => {
						showAddForm = true;
						error = '';
					}}
					class="inline-flex items-center gap-1.5 bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors cursor-pointer"
				>
					<svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
					</svg>
					Add Hive
				</button>
			{/if}
		</div>

		<!-- Add hive form -->
		{#if showAddForm}
			<div class="bg-white rounded-lg shadow p-5 mb-4">
				<h3 class="text-sm font-semibold text-amber-800 mb-4">New Hive</h3>
				<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
					<div>
						<label for="add-id" class="block text-xs font-medium text-gray-600 mb-1">
							ID <span class="text-red-500">*</span>
						</label>
						<input
							id="add-id"
							type="number"
							min="1"
							max="250"
							bind:value={addId}
							class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
							placeholder="1-250"
						/>
					</div>
					<div>
						<label for="add-name" class="block text-xs font-medium text-gray-600 mb-1">
							Name <span class="text-red-500">*</span>
						</label>
						<input
							id="add-name"
							type="text"
							bind:value={addName}
							class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
							placeholder="Hive name"
						/>
					</div>
					<div>
						<label for="add-location" class="block text-xs font-medium text-gray-600 mb-1">Location</label>
						<input
							id="add-location"
							type="text"
							bind:value={addLocation}
							class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
							placeholder="Optional"
						/>
					</div>
					<div>
						<label for="add-mac" class="block text-xs font-medium text-gray-600 mb-1">MAC Address</label>
						<input
							id="add-mac"
							type="text"
							bind:value={addMac}
							class="w-full border border-gray-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-amber-500"
							placeholder="AA:BB:CC:DD:EE:FF"
						/>
					</div>
				</div>
				<div class="flex items-center gap-3 mt-4">
					<button
						onclick={createHive}
						disabled={loading}
						class="bg-amber-600 hover:bg-amber-700 disabled:bg-amber-400 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors cursor-pointer"
					>
						{loading ? 'Creating...' : 'Create Hive'}
					</button>
					<button
						onclick={resetAddForm}
						class="text-gray-500 hover:text-gray-700 text-sm font-medium px-3 py-2 cursor-pointer"
					>
						Cancel
					</button>
				</div>
			</div>
		{/if}

		<!-- Hive table (desktop) -->
		{#if hives.length > 0}
			<div class="bg-white rounded-lg shadow overflow-hidden">
				<!-- Desktop table -->
				<div class="hidden sm:block overflow-x-auto">
					<table class="w-full text-sm">
						<thead>
							<tr class="bg-amber-50 text-left text-xs font-medium text-amber-800 uppercase tracking-wider">
								<th class="px-4 py-3">ID</th>
								<th class="px-4 py-3">Name</th>
								<th class="px-4 py-3">Location</th>
								<th class="px-4 py-3">MAC</th>
								<th class="px-4 py-3">Last Seen</th>
								<th class="px-4 py-3 text-right">Actions</th>
							</tr>
						</thead>
						<tbody class="divide-y divide-gray-100">
							{#each hives as hive (hive.id)}
								{#if editingHiveId === hive.id}
									<!-- Editing row -->
									<tr class="bg-amber-50/50">
										<td class="px-4 py-3 font-mono text-gray-500">{hive.id}</td>
										<td class="px-4 py-3">
											<input
												type="text"
												bind:value={editName}
												class="w-full border border-gray-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
											/>
										</td>
										<td class="px-4 py-3">
											<input
												type="text"
												bind:value={editLocation}
												class="w-full border border-gray-300 rounded px-2 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
												placeholder="Optional"
											/>
										</td>
										<td class="px-4 py-3 font-mono text-xs text-gray-400">
											{hive.sender_mac ?? '--'}
										</td>
										<td class="px-4 py-3 text-gray-400 text-xs">
											{formatLastSeen(hive.last_seen_at)}
										</td>
										<td class="px-4 py-3 text-right space-x-2">
											<button
												onclick={() => updateHive(hive.id)}
												disabled={loading}
												class="text-green-600 hover:text-green-800 font-medium text-xs cursor-pointer"
											>
												Save
											</button>
											<button
												onclick={cancelEdit}
												class="text-gray-400 hover:text-gray-600 text-xs cursor-pointer"
											>
												Cancel
											</button>
										</td>
									</tr>
								{:else}
									<!-- Display row -->
									<tr class="hover:bg-amber-50/30 transition-colors">
										<td class="px-4 py-3 font-mono text-gray-500">{hive.id}</td>
										<td class="px-4 py-3 font-medium text-gray-800">{hive.name}</td>
										<td class="px-4 py-3 text-gray-500">{hive.location ?? '--'}</td>
										<td class="px-4 py-3 font-mono text-xs text-gray-400">
											{hive.sender_mac ?? '--'}
										</td>
										<td class="px-4 py-3 text-gray-400 text-xs">
											{formatLastSeen(hive.last_seen_at)}
										</td>
										<td class="px-4 py-3 text-right space-x-2">
											<button
												onclick={() => startEdit(hive)}
												class="text-amber-600 hover:text-amber-800 font-medium text-xs cursor-pointer"
											>
												Edit
											</button>
											<button
												onclick={() => deleteHive(hive)}
												class="text-red-500 hover:text-red-700 font-medium text-xs cursor-pointer"
											>
												Delete
											</button>
										</td>
									</tr>
								{/if}
							{/each}
						</tbody>
					</table>
				</div>

				<!-- Mobile cards -->
				<div class="sm:hidden divide-y divide-gray-100">
					{#each hives as hive (hive.id)}
						{#if editingHiveId === hive.id}
							<div class="p-4 bg-amber-50/50 space-y-3">
								<div class="flex items-center justify-between">
									<span class="font-mono text-xs text-gray-400">ID {hive.id}</span>
									<span class="font-mono text-xs text-gray-400">{hive.sender_mac ?? '--'}</span>
								</div>
								<div>
									<label for="edit-name-mobile" class="block text-xs text-gray-500 mb-1">Name</label>
									<input
										id="edit-name-mobile"
										type="text"
										bind:value={editName}
										class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
									/>
								</div>
								<div>
									<label for="edit-location-mobile" class="block text-xs text-gray-500 mb-1">Location</label>
									<input
										id="edit-location-mobile"
										type="text"
										bind:value={editLocation}
										class="w-full border border-gray-300 rounded px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500"
										placeholder="Optional"
									/>
								</div>
								<div class="flex gap-3">
									<button
										onclick={() => updateHive(hive.id)}
										disabled={loading}
										class="bg-green-600 hover:bg-green-700 text-white text-sm font-medium px-3 py-1.5 rounded transition-colors cursor-pointer"
									>
										Save
									</button>
									<button
										onclick={cancelEdit}
										class="text-gray-500 hover:text-gray-700 text-sm px-3 py-1.5 cursor-pointer"
									>
										Cancel
									</button>
								</div>
							</div>
						{:else}
							<div class="p-4 space-y-2">
								<div class="flex items-center justify-between">
									<div>
										<span class="font-medium text-gray-800">{hive.name}</span>
										<span class="ml-2 font-mono text-xs text-gray-400">#{hive.id}</span>
									</div>
									<span class="text-xs text-gray-400">{formatLastSeen(hive.last_seen_at)}</span>
								</div>
								<div class="flex items-center justify-between text-xs text-gray-500">
									<span>{hive.location ?? 'No location'}</span>
									<span class="font-mono">{hive.sender_mac ?? '--'}</span>
								</div>
								<div class="flex gap-3 pt-1">
									<button
										onclick={() => startEdit(hive)}
										class="text-amber-600 hover:text-amber-800 font-medium text-xs cursor-pointer"
									>
										Edit
									</button>
									<button
										onclick={() => deleteHive(hive)}
										class="text-red-500 hover:text-red-700 font-medium text-xs cursor-pointer"
									>
										Delete
									</button>
								</div>
							</div>
						{/if}
					{/each}
				</div>
			</div>
		{:else}
			<div class="bg-white rounded-lg shadow p-8 text-center text-gray-400">
				No hives registered. Click "Add Hive" to get started.
			</div>
		{/if}
	</section>
</div>
