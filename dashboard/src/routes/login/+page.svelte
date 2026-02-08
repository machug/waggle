<script lang="ts">
	import { env } from '$env/dynamic/public';
	import LoginForm from '$lib/components/LoginForm.svelte';

	const isCloudMode = $derived(env.PUBLIC_DASHBOARD_MODE === 'cloud');
</script>

<svelte:head>
	<title>Sign In — Waggle</title>
</svelte:head>

<div class="min-h-[calc(100vh-3.5rem)] flex items-center justify-center px-4 py-12">
	<div class="w-full max-w-sm">
		<!-- Card -->
		<div class="rounded-xl border border-amber-200 bg-white shadow-md p-6 sm:p-8">
			<!-- Logo / heading -->
			<div class="text-center mb-6">
				<svg
					class="w-10 h-10 text-amber-600 mx-auto mb-3"
					viewBox="0 0 24 24"
					fill="currentColor"
					aria-hidden="true"
				>
					<path d="M12 2L9.19 8.63 2 9.24l5.46 4.73L5.82 21 12 17.27 18.18 21l-1.64-7.03L22 9.24l-7.19-.61z"/>
				</svg>
				<h1 class="text-xl font-bold text-amber-900">Sign In</h1>
				<p class="text-sm text-gray-500 mt-1">Welcome back to Waggle</p>
			</div>

			{#if isCloudMode}
				<LoginForm />
			{:else}
				<div
					class="rounded-md bg-amber-50 border border-amber-200 px-4 py-3 text-sm text-amber-800 text-center"
				>
					Login is only available in cloud mode
				</div>
			{/if}
		</div>
	</div>
</div>
