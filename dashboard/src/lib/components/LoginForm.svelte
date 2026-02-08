<script lang="ts">
	/**
	 * LoginForm — Supabase Auth login form for cloud mode.
	 * Email + password with error display.
	 */
	import { goto } from '$app/navigation';
	import { getSupabase } from '$lib/supabase';

	let { onerror }: { onerror?: (msg: string) => void } = $props();

	let email = $state('');
	let password = $state('');
	let loading = $state(false);
	let errorMsg = $state('');

	async function handleSubmit() {
		errorMsg = '';
		if (!email || !password) {
			errorMsg = 'Email and password are required.';
			onerror?.(errorMsg);
			return;
		}

		loading = true;
		try {
			const { error } = await getSupabase().auth.signInWithPassword({
				email,
				password
			});

			if (error) {
				errorMsg = error.message;
				onerror?.(errorMsg);
			} else {
				await goto('/');
			}
		} catch (err) {
			errorMsg = err instanceof Error ? err.message : 'An unexpected error occurred.';
			onerror?.(errorMsg);
		} finally {
			loading = false;
		}
	}
</script>

<form
	class="space-y-5"
	onsubmit={(e: SubmitEvent) => { e.preventDefault(); handleSubmit(); }}
>
	<!-- Error message -->
	{#if errorMsg}
		<div
			class="rounded-md bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700"
			role="alert"
		>
			{errorMsg}
		</div>
	{/if}

	<!-- Email -->
	<div>
		<label for="email" class="block text-sm font-medium text-amber-900 mb-1">
			Email
		</label>
		<input
			id="email"
			type="email"
			autocomplete="email"
			required
			bind:value={email}
			disabled={loading}
			class="w-full rounded-lg border border-amber-300 bg-white px-3 py-2 text-sm
			       text-amber-900 placeholder-gray-400
			       focus:border-amber-500 focus:ring-2 focus:ring-amber-200 focus:outline-none
			       disabled:opacity-50 disabled:cursor-not-allowed"
			placeholder="you@example.com"
		/>
	</div>

	<!-- Password -->
	<div>
		<label for="password" class="block text-sm font-medium text-amber-900 mb-1">
			Password
		</label>
		<input
			id="password"
			type="password"
			autocomplete="current-password"
			required
			bind:value={password}
			disabled={loading}
			class="w-full rounded-lg border border-amber-300 bg-white px-3 py-2 text-sm
			       text-amber-900 placeholder-gray-400
			       focus:border-amber-500 focus:ring-2 focus:ring-amber-200 focus:outline-none
			       disabled:opacity-50 disabled:cursor-not-allowed"
			placeholder="Enter your password"
		/>
	</div>

	<!-- Submit button -->
	<button
		type="submit"
		disabled={loading}
		class="w-full rounded-lg bg-amber-600 px-4 py-2.5 text-sm font-semibold text-white
		       shadow-sm hover:bg-amber-700 focus:outline-none focus:ring-2
		       focus:ring-amber-400 focus:ring-offset-2 transition-colors
		       disabled:opacity-50 disabled:cursor-not-allowed"
	>
		{#if loading}
			<span class="inline-flex items-center gap-2">
				<svg class="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
					<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
					<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
				</svg>
				Signing in&hellip;
			</span>
		{:else}
			Sign In
		{/if}
	</button>
</form>
