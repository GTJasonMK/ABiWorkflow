import type { ProviderConfig } from '../types/provider'

export function extractAllowedVideoLengths(
  template: Record<string, unknown> | null | undefined,
): number[] {
  if (!template || typeof template !== 'object') return []
  const raw = (template as { _allowed_video_lengths?: unknown })._allowed_video_lengths
  if (!Array.isArray(raw)) return []

  const lengths = raw
    .map((value) => {
      if (typeof value === 'number') return Math.trunc(value)
      const parsed = Number.parseInt(String(value), 10)
      return Number.isFinite(parsed) ? parsed : NaN
    })
    .filter((value): value is number => Number.isFinite(value) && value > 0)

  return [...new Set(lengths)].sort((a, b) => a - b)
}

export function resolveVideoProviderAllowedLengths(
  configs: ProviderConfig[],
  providerKey: string | null | undefined,
): number[] {
  const key = (providerKey ?? '').trim()
  if (!key) return []
  const matched = configs.find((item) => item.provider_type === 'video' && item.provider_key === key)
  return extractAllowedVideoLengths(matched?.request_template)
}

