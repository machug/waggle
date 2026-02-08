<script lang="ts">
	import '../app.css';
	import favicon from '$lib/assets/favicon.svg';
	import { page } from '$app/state';

	let { children, data } = $props();
	let menuOpen = $state(false);

	const navLinks = [
		{ href: '/', label: 'Apiary' },
		{ href: '/varroa', label: 'Varroa' },
		{ href: '/inspections', label: 'Inspections' },
		{ href: '/alerts', label: 'Alerts' },
		{ href: '/settings', label: 'Settings' }
	];

	const isActive = (href: string): boolean => {
		if (href === '/') return page.url.pathname === '/';
		return page.url.pathname.startsWith(href);
	};

	const hubOnline = $derived(data.hubStatus !== null);
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<!-- Hub offline banner -->
{#if !hubOnline}
	<div class="bg-red-600 text-white text-center text-sm py-1.5 px-4 font-medium">
		Hub Offline — sensor data may be stale
	</div>
{/if}

<!-- Navigation bar -->
<nav class="bg-amber-700 shadow-md">
	<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
		<div class="flex items-center justify-between h-14">
			<!-- Brand -->
			<a href="/" class="flex items-center gap-2 text-white font-bold text-lg tracking-tight">
				<svg class="w-7 h-7" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
					<path d="M12 2L9.19 8.63 2 9.24l5.46 4.73L5.82 21 12 17.27 18.18 21l-1.64-7.03L22 9.24l-7.19-.61z"/>
				</svg>
				Waggle
			</a>

			<!-- Desktop nav links -->
			<div class="hidden sm:flex sm:items-center sm:gap-1">
				{#each navLinks as link}
					<a
						href={link.href}
						class="px-3 py-2 rounded-md text-sm font-medium transition-colors {isActive(link.href)
							? 'bg-amber-800 text-white'
							: 'text-amber-100 hover:bg-amber-600 hover:text-white'}"
					>
						{link.label}
					</a>
				{/each}
			</div>

			<!-- Connection status badge (desktop) -->
			<div class="hidden sm:flex items-center">
				{#if hubOnline}
					<span class="inline-flex items-center gap-1.5 text-xs font-medium text-amber-100">
						<span class="w-2 h-2 rounded-full bg-green-400"></span>
						Hub Online
					</span>
				{:else}
					<span class="inline-flex items-center gap-1.5 text-xs font-medium text-red-200">
						<span class="w-2 h-2 rounded-full bg-red-400"></span>
						Hub Offline
					</span>
				{/if}
			</div>

			<!-- Mobile hamburger button -->
			<button
				class="sm:hidden inline-flex items-center justify-center p-2 rounded-md text-amber-100 hover:text-white hover:bg-amber-600 transition-colors"
				onclick={() => (menuOpen = !menuOpen)}
				aria-expanded={menuOpen}
				aria-label="Toggle navigation menu"
			>
				{#if menuOpen}
					<!-- X icon -->
					<svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
					</svg>
				{:else}
					<!-- Hamburger icon -->
					<svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16" />
					</svg>
				{/if}
			</button>
		</div>
	</div>

	<!-- Mobile menu -->
	{#if menuOpen}
		<div class="sm:hidden border-t border-amber-600">
			<div class="px-2 pt-2 pb-3 space-y-1">
				{#each navLinks as link}
					<a
						href={link.href}
						onclick={() => (menuOpen = false)}
						class="block px-3 py-2 rounded-md text-base font-medium transition-colors {isActive(link.href)
							? 'bg-amber-800 text-white'
							: 'text-amber-100 hover:bg-amber-600 hover:text-white'}"
					>
						{link.label}
					</a>
				{/each}
			</div>
			<!-- Connection status (mobile) -->
			<div class="px-4 pb-3 border-t border-amber-600 pt-3">
				{#if hubOnline}
					<span class="inline-flex items-center gap-1.5 text-xs font-medium text-amber-100">
						<span class="w-2 h-2 rounded-full bg-green-400"></span>
						Hub Online
					</span>
				{:else}
					<span class="inline-flex items-center gap-1.5 text-xs font-medium text-red-200">
						<span class="w-2 h-2 rounded-full bg-red-400"></span>
						Hub Offline
					</span>
				{/if}
			</div>
		</div>
	{/if}
</nav>

<!-- Main content -->
<main class="min-h-screen bg-amber-50">
	{@render children()}
</main>
