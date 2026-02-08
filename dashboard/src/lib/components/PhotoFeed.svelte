<script lang="ts">
	import PhotoDetail from './PhotoDetail.svelte';

	interface Photo {
		id: number;
		hive_id: number;
		file_path: string;
		captured_at: string;
		ml_status: 'pending' | 'processing' | 'completed' | 'failed';
		signed_url?: string;
	}

	interface Detection {
		id: number;
		photo_id: number;
		class_name: string;
		confidence: number;
		bbox_x: number;
		bbox_y: number;
		bbox_w: number;
		bbox_h: number;
	}

	let { photos = [], detections = [], mode = 'local' }: {
		photos: Photo[];
		detections: Detection[];
		mode?: 'local' | 'cloud';
	} = $props();

	let filter = $state<'all' | 'detections' | 'pending'>('all');
	let selectedPhoto = $state<Photo | null>(null);

	const photoDetectionMap = $derived(() => {
		const map = new Map<number, Detection[]>();
		for (const d of detections) {
			const list = map.get(d.photo_id) ?? [];
			list.push(d);
			map.set(d.photo_id, list);
		}
		return map;
	});

	const filteredPhotos = $derived(() => {
		const map = photoDetectionMap();
		switch (filter) {
			case 'detections':
				return photos.filter((p) => (map.get(p.id)?.length ?? 0) > 0);
			case 'pending':
				return photos.filter((p) => p.ml_status === 'pending' || p.ml_status === 'processing');
			default:
				return photos;
		}
	});

	const selectedDetections = $derived(() => {
		if (!selectedPhoto) return [];
		return photoDetectionMap().get(selectedPhoto.id) ?? [];
	});

	function getPhotoUrl(photo: Photo): string {
		if (mode === 'cloud' && photo.signed_url) {
			return photo.signed_url;
		}
		return `/api/hives/${photo.hive_id}/photos/${photo.id}/image`;
	}

	function statusBadgeClass(status: string): string {
		switch (status) {
			case 'completed':
				return 'bg-green-100 text-green-800';
			case 'processing':
				return 'bg-blue-100 text-blue-800';
			case 'pending':
				return 'bg-gray-100 text-gray-600';
			case 'failed':
				return 'bg-red-100 text-red-800';
			default:
				return 'bg-gray-100 text-gray-600';
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

	function getDetectionSummary(photo: Photo): { count: number; topClass: string } | null {
		const dets = photoDetectionMap().get(photo.id);
		if (!dets || dets.length === 0) return null;

		// Find the most common class
		const classCounts = new Map<string, number>();
		for (const d of dets) {
			classCounts.set(d.class_name, (classCounts.get(d.class_name) ?? 0) + 1);
		}
		let topClass = '';
		let topCount = 0;
		for (const [cls, count] of classCounts) {
			if (count > topCount) {
				topClass = cls;
				topCount = count;
			}
		}

		return { count: dets.length, topClass };
	}

	function openDetail(photo: Photo) {
		selectedPhoto = photo;
	}

	function closeDetail() {
		selectedPhoto = null;
	}
</script>

<div class="bg-white rounded-lg shadow">
	<div class="px-4 py-3 border-b border-amber-100 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
		<h3 class="text-sm font-bold text-amber-900 uppercase tracking-wide">Photos</h3>

		<!-- Filter buttons -->
		<div class="flex gap-1">
			<button
				onclick={() => (filter = 'all')}
				class="px-3 py-1 text-xs font-medium rounded transition-colors {filter === 'all'
					? 'bg-amber-600 text-white'
					: 'text-amber-700 hover:bg-amber-100 border border-amber-200'}"
			>
				All
			</button>
			<button
				onclick={() => (filter = 'detections')}
				class="px-3 py-1 text-xs font-medium rounded transition-colors {filter === 'detections'
					? 'bg-amber-600 text-white'
					: 'text-amber-700 hover:bg-amber-100 border border-amber-200'}"
			>
				With Detections
			</button>
			<button
				onclick={() => (filter = 'pending')}
				class="px-3 py-1 text-xs font-medium rounded transition-colors {filter === 'pending'
					? 'bg-amber-600 text-white'
					: 'text-amber-700 hover:bg-amber-100 border border-amber-200'}"
			>
				Pending
			</button>
		</div>
	</div>

	{#if filteredPhotos().length === 0}
		<div class="px-4 py-8 text-center text-gray-400 text-sm">
			{#if photos.length === 0}
				No photos available. Phase 3 camera required.
			{:else}
				No photos match the current filter.
			{/if}
		</div>
	{:else}
		<div class="p-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 max-h-[600px] overflow-y-auto">
			{#each filteredPhotos() as photo (photo.id)}
				<button
					class="group bg-gray-50 rounded-lg overflow-hidden border border-gray-200 hover:border-amber-400 hover:shadow-md transition-all text-left cursor-pointer"
					onclick={() => openDetail(photo)}
				>
					<!-- Thumbnail -->
					<div class="relative aspect-video bg-gray-200 overflow-hidden">
						<img
							src={getPhotoUrl(photo)}
							alt="Hive photo {photo.id}"
							class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
							loading="lazy"
						/>
						<!-- ML status badge -->
						<span
							class="absolute top-2 right-2 px-2 py-0.5 rounded text-xs font-semibold {statusBadgeClass(photo.ml_status)}"
						>
							{photo.ml_status}
						</span>
					</div>

					<!-- Info -->
					<div class="px-3 py-2">
						<p class="text-xs text-gray-500">{formatTime(photo.captured_at)}</p>
						{#if photo.ml_status === 'completed'}
							{@const summary = getDetectionSummary(photo)}
							{#if summary}
								<p class="text-sm font-medium text-amber-800 mt-0.5">
									{summary.count} detection{summary.count !== 1 ? 's' : ''}
									<span class="text-gray-500 font-normal">- {summary.topClass}</span>
								</p>
							{:else}
								<p class="text-sm text-gray-400 mt-0.5">No detections</p>
							{/if}
						{/if}
					</div>
				</button>
			{/each}
		</div>
	{/if}
</div>

{#if selectedPhoto}
	<PhotoDetail
		photo={selectedPhoto}
		detections={selectedDetections()}
		onclose={closeDetail}
	/>
{/if}
