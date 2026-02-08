<script lang="ts">
	interface Hive {
		id: number;
		name: string;
	}

	interface Inspection {
		id?: string;
		hive_id?: number;
		inspected_at?: string;
		queen_seen?: boolean;
		brood_pattern?: string;
		treatment_type?: string;
		treatment_notes?: string;
		notes?: string;
	}

	let {
		hives = [],
		inspection,
		onsubmit
	}: {
		hives: Hive[];
		inspection?: Inspection;
		onsubmit?: () => void;
	} = $props();

	// Form state
	let hiveId = $state(inspection?.hive_id ?? (hives.length > 0 ? hives[0].id : 0));
	let inspectedAt = $state(
		inspection?.inspected_at
			? inspection.inspected_at.slice(0, 10)
			: new Date().toISOString().slice(0, 10)
	);
	let queenSeen = $state(inspection?.queen_seen ?? false);
	let broodPattern = $state(inspection?.brood_pattern ?? 'good');
	let treatmentType = $state(inspection?.treatment_type ?? '');
	let treatmentNotes = $state(inspection?.treatment_notes ?? '');
	let notes = $state(inspection?.notes ?? '');

	let submitting = $state(false);
	let error = $state('');
	let success = $state('');

	const broodOptions = [
		{ value: 'excellent', label: 'Excellent' },
		{ value: 'good', label: 'Good' },
		{ value: 'fair', label: 'Fair' },
		{ value: 'poor', label: 'Poor' },
		{ value: 'none', label: 'None' }
	];

	async function handleSubmit() {
		error = '';
		success = '';
		submitting = true;

		const body: Record<string, unknown> = {
			id: inspection?.id ?? crypto.randomUUID(),
			hive_id: hiveId,
			inspected_at: new Date(inspectedAt).toISOString(),
			queen_seen: queenSeen,
			brood_pattern: broodPattern
		};

		if (treatmentType.trim()) body.treatment_type = treatmentType.trim();
		if (treatmentNotes.trim()) body.treatment_notes = treatmentNotes.trim();
		if (notes.trim()) body.notes = notes.trim();

		try {
			const res = await fetch('/api/inspections', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify(body)
			});

			if (!res.ok) {
				const text = await res.text();
				throw new Error(`Failed to save inspection: ${res.status} ${text}`);
			}

			success = 'Inspection saved successfully.';

			// Reset form for next entry
			if (!inspection) {
				queenSeen = false;
				broodPattern = 'good';
				treatmentType = '';
				treatmentNotes = '';
				notes = '';
				inspectedAt = new Date().toISOString().slice(0, 10);
			}

			onsubmit?.();
		} catch (err) {
			error = err instanceof Error ? err.message : 'An unexpected error occurred.';
		} finally {
			submitting = false;
		}
	}
</script>

<form
	class="bg-white rounded-lg shadow-sm border border-amber-200 p-5"
	onsubmit={(e) => { e.preventDefault(); handleSubmit(); }}
>
	<h3 class="text-sm font-bold text-amber-900 uppercase tracking-wide mb-4">
		{inspection ? 'Edit Inspection' : 'New Inspection'}
	</h3>

	<!-- Hive selector -->
	<div class="mb-4">
		<label for="insp-hive" class="block text-xs font-medium text-amber-800 mb-1">Hive</label>
		<select
			id="insp-hive"
			class="w-full rounded-md border border-amber-300 bg-white px-3 py-2 text-sm text-gray-800 shadow-sm focus:border-amber-500 focus:ring-1 focus:ring-amber-500 focus:outline-none"
			bind:value={hiveId}
		>
			{#each hives as hive}
				<option value={hive.id}>{hive.name}</option>
			{/each}
		</select>
	</div>

	<!-- Date -->
	<div class="mb-4">
		<label for="insp-date" class="block text-xs font-medium text-amber-800 mb-1">Date</label>
		<input
			id="insp-date"
			type="date"
			class="w-full rounded-md border border-amber-300 bg-white px-3 py-2 text-sm text-gray-800 shadow-sm focus:border-amber-500 focus:ring-1 focus:ring-amber-500 focus:outline-none"
			bind:value={inspectedAt}
		/>
	</div>

	<!-- Queen seen -->
	<div class="mb-4 flex items-center gap-2">
		<input
			id="insp-queen"
			type="checkbox"
			class="rounded border-amber-300 text-amber-600 focus:ring-amber-500"
			bind:checked={queenSeen}
		/>
		<label for="insp-queen" class="text-sm font-medium text-amber-800">Queen seen</label>
	</div>

	<!-- Brood pattern -->
	<div class="mb-4">
		<label for="insp-brood" class="block text-xs font-medium text-amber-800 mb-1">
			Brood Pattern
		</label>
		<select
			id="insp-brood"
			class="w-full rounded-md border border-amber-300 bg-white px-3 py-2 text-sm text-gray-800 shadow-sm focus:border-amber-500 focus:ring-1 focus:ring-amber-500 focus:outline-none"
			bind:value={broodPattern}
		>
			{#each broodOptions as opt}
				<option value={opt.value}>{opt.label}</option>
			{/each}
		</select>
	</div>

	<!-- Treatment type -->
	<div class="mb-4">
		<label for="insp-treatment" class="block text-xs font-medium text-amber-800 mb-1">
			Treatment Type <span class="text-gray-400 font-normal">(optional)</span>
		</label>
		<input
			id="insp-treatment"
			type="text"
			placeholder="e.g. Oxalic acid, Apivar strip"
			class="w-full rounded-md border border-amber-300 bg-white px-3 py-2 text-sm text-gray-800 shadow-sm focus:border-amber-500 focus:ring-1 focus:ring-amber-500 focus:outline-none placeholder:text-gray-400"
			bind:value={treatmentType}
		/>
	</div>

	<!-- Treatment notes -->
	<div class="mb-4">
		<label for="insp-treatment-notes" class="block text-xs font-medium text-amber-800 mb-1">
			Treatment Notes <span class="text-gray-400 font-normal">(optional)</span>
		</label>
		<textarea
			id="insp-treatment-notes"
			rows="2"
			placeholder="Dosage, application method, duration..."
			class="w-full rounded-md border border-amber-300 bg-white px-3 py-2 text-sm text-gray-800 shadow-sm focus:border-amber-500 focus:ring-1 focus:ring-amber-500 focus:outline-none placeholder:text-gray-400 resize-y"
			bind:value={treatmentNotes}
		></textarea>
	</div>

	<!-- Notes -->
	<div class="mb-5">
		<label for="insp-notes" class="block text-xs font-medium text-amber-800 mb-1">
			Notes <span class="text-gray-400 font-normal">(optional)</span>
		</label>
		<textarea
			id="insp-notes"
			rows="3"
			placeholder="General observations, hive condition, temperament..."
			class="w-full rounded-md border border-amber-300 bg-white px-3 py-2 text-sm text-gray-800 shadow-sm focus:border-amber-500 focus:ring-1 focus:ring-amber-500 focus:outline-none placeholder:text-gray-400 resize-y"
			bind:value={notes}
		></textarea>
	</div>

	<!-- Error / Success messages -->
	{#if error}
		<div class="mb-4 rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700">
			{error}
		</div>
	{/if}
	{#if success}
		<div class="mb-4 rounded-md bg-green-50 border border-green-200 px-3 py-2 text-sm text-green-700">
			{success}
		</div>
	{/if}

	<!-- Submit -->
	<button
		type="submit"
		disabled={submitting || hives.length === 0}
		class="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-md text-sm font-medium bg-amber-600 text-white hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-sm"
	>
		{#if submitting}
			<svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
				<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
				<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"></path>
			</svg>
			Saving...
		{:else}
			{inspection ? 'Update Inspection' : 'Save Inspection'}
		{/if}
	</button>
</form>
