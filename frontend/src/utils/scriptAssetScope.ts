import type { ScriptAssetBinding } from '../types/scriptAssets'

export function resolveBindingEpisodeId(binding: ScriptAssetBinding): string | null {
  const strategy = binding.strategy
  if (!strategy || typeof strategy !== 'object') return null
  const raw = (strategy as Record<string, unknown>).episode_id
  if (typeof raw !== 'string') return null
  const text = raw.trim()
  return text || null
}

export function bindingHasEpisodeScope(binding: ScriptAssetBinding): boolean {
  return resolveBindingEpisodeId(binding) !== null
}

export function bindingIsSharedDefault(binding: ScriptAssetBinding): boolean {
  return !bindingHasEpisodeScope(binding)
}

export function bindingMatchesEpisode(
  binding: ScriptAssetBinding,
  episodeId: string,
  options?: { includeSharedDefault?: boolean },
): boolean {
  const bindingEpisodeId = resolveBindingEpisodeId(binding)
  if (bindingEpisodeId === episodeId) return true
  return Boolean(options?.includeSharedDefault) && bindingEpisodeId === null
}

export function bindingBelongsToEpisodeScope(
  binding: ScriptAssetBinding,
  scopeEpisodeId?: string | null,
): boolean {
  if (!scopeEpisodeId) return true
  return resolveBindingEpisodeId(binding) === scopeEpisodeId
}

export function normalizeBindingForEpisodeScope(
  binding: ScriptAssetBinding,
  scopeEpisodeId?: string | null,
  source: string = 'asset_binding_page',
): ScriptAssetBinding {
  if (!scopeEpisodeId) return binding
  const strategyBase = binding.strategy && typeof binding.strategy === 'object'
    ? { ...(binding.strategy as Record<string, unknown>) }
    : {}
  return {
    ...binding,
    strategy: {
      ...strategyBase,
      source: strategyBase.source ?? source,
      episode_id: scopeEpisodeId,
    },
  }
}
