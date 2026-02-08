<script lang="ts">
	import { onMount, onDestroy } from 'svelte';

	interface Photo {
		id: number;
		hive_id: number;
		file_path: string;
		captured_at: string;
		ml_status: string;
		signed_url?: string;
		image_width?: number;
		image_height?: number;
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

	let { photo, detections = [], onclose }: {
		photo: Photo;
		detections: Detection[];
		onclose: () => void;
	} = $props();

	let imageContainer = $state<HTMLDivElement | null>(null);
	let imageEl = $state<HTMLImageElement | null>(null);
	let imageLoaded = $state(false);
	let naturalWidth = $state(0);
	let naturalHeight = $state(0);

	function getPhotoUrl(p: Photo): string {
		if (p.signed_url) {
			return p.signed_url;
		}
		return `/api/hives/${p.hive_id}/photos/${p.id}/image`;
	}

	function classColor(className: string): string {
		const lower = className.toLowerCase();
		if (lower.includes('bee') && !lower.includes('wasp')) return '#22c55e'; // green
		if (lower.includes('varroa')) return '#ef4444'; // red
		if (lower.includes('wasp') || lower.includes('hornet')) return '#f97316'; // orange
		return '#3b82f6'; // blue for other classes
	}

	function formatTime(iso: string): string {
		const d = new Date(iso);
		return d.toLocaleString(undefined, {
			year: 'numeric',
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit',
			second: '2-digit'
		});
	}

	function handleImageLoad(event: Event) {
		const img = event.target as HTMLImageElement;
		naturalWidth = img.naturalWidth;
		naturalHeight = img.naturalHeight;
		imageLoaded = true;
	}

	function handleBackdropClick(event: MouseEvent) {
		if (event.target === event.currentTarget) {
			onclose();
		}
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			onclose();
		}
	}

	onMount(() => {
		document.addEventListener('keydown', handleKeydown);
		// Prevent body scroll while overlay is open
		document.body.style.overflow = 'hidden';
	});

	onDestroy(() => {
		document.removeEventListener('keydown', handleKeydown);
		document.body.style.overflow = '';
	});
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	class="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4"
	onclick={handleBackdropClick}
>
	<div class="bg-white rounded-xl shadow-2xl max-w-4xl w-full max-h-[90vh] overflow-y-auto relative">
		<!-- Close button -->
		<button
			onclick={onclose}
			class="absolute top-3 right-3 z-10 w-8 h-8 flex items-center justify-center rounded-full bg-white/90 hover:bg-white shadow text-gray-600 hover:text-gray-900 transition-colors cursor-pointer"
			aria-label="Close"
		>
			<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
			</svg>
		</button>

		<!-- Photo with detection overlay -->
		<div class="relative bg-gray-900" bind:this={imageContainer}>
			<img
				bind:this={imageEl}
				src={getPhotoUrl(photo)}
				alt="Hive photo {photo.id}"
				class="w-full h-auto block"
				onload={handleImageLoad}
			/>

			<!-- SVG overlay for bounding boxes -->
			{#if imageLoaded && detections.length > 0 && naturalWidth > 0 && naturalHeight > 0}
				<svg
					class="absolute inset-0 w-full h-full pointer-events-none"
					viewBox="0 0 {naturalWidth} {naturalHeight}"
					preserveAspectRatio="xMidYMid meet"
				>
					{#each detections as det (det.id)}
						{@const color = classColor(det.class_name)}
						<!-- Bounding box -->
						<rect
							x={det.bbox_x}
							y={det.bbox_y}
							width={det.bbox_w}
							height={det.bbox_h}
							fill="none"
							stroke={color}
							stroke-width="3"
							rx="2"
						/>
						<!-- Label background -->
						<rect
							x={det.bbox_x}
							y={det.bbox_y - 24}
							width={Math.max(det.class_name.length * 9 + 60, 80)}
							height="24"
							fill={color}
							rx="2"
						/>
						<!-- Label text -->
						<text
							x={det.bbox_x + 4}
							y={det.bbox_y - 7}
							fill="white"
							font-size="14"
							font-weight="600"
							font-family="system-ui, sans-serif"
						>
							{det.class_name} {(det.confidence * 100).toFixed(0)}%
						</text>
					{/each}
				</svg>
			{/if}
		</div>

		<!-- Photo info -->
		<div class="px-5 py-4 border-b border-gray-100">
			<div class="flex items-center gap-3 flex-wrap">
				<p class="text-sm text-gray-500">{formatTime(photo.captured_at)}</p>
				<span
					class="px-2 py-0.5 rounded text-xs font-semibold {photo.ml_status === 'completed'
						? 'bg-green-100 text-green-800'
						: photo.ml_status === 'failed'
							? 'bg-red-100 text-red-800'
							: photo.ml_status === 'processing'
								? 'bg-blue-100 text-blue-800'
								: 'bg-gray-100 text-gray-600'}"
				>
					{photo.ml_status}
				</span>
				{#if detections.length > 0}
					<span class="text-sm text-amber-800 font-medium">
						{detections.length} detection{detections.length !== 1 ? 's' : ''}
					</span>
				{/if}
			</div>
		</div>

		<!-- Detection list -->
		{#if detections.length > 0}
			<div class="px-5 py-3">
				<h4 class="text-xs font-bold text-amber-900 uppercase tracking-wide mb-2">Detections</h4>
				<ul class="divide-y divide-gray-100">
					{#each detections as det (det.id)}
						{@const color = classColor(det.class_name)}
						<li class="py-2 flex items-center gap-3">
							<!-- Color swatch -->
							<span
								class="w-3 h-3 rounded-sm shrink-0"
								style="background-color: {color};"
							></span>
							<!-- Class name -->
							<span class="text-sm font-medium text-gray-800 capitalize">{det.class_name}</span>
							<!-- Confidence -->
							<span class="text-xs text-gray-500">
								{(det.confidence * 100).toFixed(1)}%
							</span>
							<!-- Bounding box coordinates -->
							<span class="text-xs text-gray-400 ml-auto">
								({Math.round(det.bbox_x)}, {Math.round(det.bbox_y)}) {Math.round(det.bbox_w)}x{Math.round(det.bbox_h)}
							</span>
						</li>
					{/each}
				</ul>
			</div>
		{:else if photo.ml_status === 'completed'}
			<div class="px-5 py-4 text-sm text-gray-400 text-center">
				No detections found in this photo.
			</div>
		{/if}
	</div>
</div>
