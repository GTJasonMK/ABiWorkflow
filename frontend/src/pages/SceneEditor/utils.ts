import type { Panel } from '../../types/panel'
import type { GlobalCharacterAsset, GlobalLocationAsset, GlobalVoice } from '../../types/assetHub'
import type {
  AssetSourceScope,
  AssetTabKey,
  CharacterApplyPlan,
  LocationApplyPlan,
  PanelAssetBinding,
  PromptApplyMode,
} from './types'

export function moveItem<T>(items: T[], from: number, to: number): T[] {
  const next = [...items]
  const [picked] = next.splice(from, 1)
  next.splice(to, 0, picked!)
  return next
}

export function normalizeText(value: string | null | undefined): string {
  return (value ?? '').trim()
}

function mergePromptSection(origin: string | null, sectionLabel: string, content: string | null | undefined): string | null {
  const base = normalizeText(origin)
  const chunk = normalizeText(content)
  if (!chunk) return base || null

  const candidate = `${sectionLabel}${chunk}`
  if (base.includes(chunk) || base.includes(candidate)) {
    return base || null
  }
  return base ? `${base}\n${candidate}` : candidate
}

function splitPromptLines(content: string | null | undefined): string[] {
  const text = normalizeText(content)
  if (!text) return []
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
}

export function collectAddedPromptLines(origin: string | null, nextPrompt: string | null): string[] {
  const originSet = new Set(splitPromptLines(origin))
  return splitPromptLines(nextPrompt).filter((line) => !originSet.has(line))
}

export function matchesFolderFilter(folderId: string | null | undefined, filterValue: string): boolean {
  if (filterValue === 'all') return true
  if (filterValue === '__none__') return !folderId
  return folderId === filterValue
}

export function assetTabLabel(tab: AssetTabKey): string {
  if (tab === 'character') return '角色'
  if (tab === 'location') return '地点'
  return '语音'
}

export function matchesSourceScope(
  assetProjectId: string | null | undefined,
  currentProjectId: string,
  scope: AssetSourceScope,
): boolean {
  if (scope === 'project') return assetProjectId === currentProjectId
  if (scope === 'global') return !assetProjectId
  return !assetProjectId || assetProjectId === currentProjectId
}

export function sourceScopeTag(assetProjectId: string | null | undefined, currentProjectId: string): string {
  if (!assetProjectId) return '全局'
  if (assetProjectId === currentProjectId) return '当前项目'
  return `项目:${assetProjectId.slice(0, 8)}`
}

export function buildPromptByMode(
  origin: string | null,
  chunks: Array<{ label: string; content: string | null | undefined }>,
  mode: PromptApplyMode,
): string | null {
  if (mode === 'replace') {
    const replaced = chunks
      .map(({ label, content }) => {
        const chunk = normalizeText(content)
        return chunk ? `${label}${chunk}` : null
      })
      .filter((item): item is string => Boolean(item))
      .join('\n')
      .trim()
    return replaced || normalizeText(origin) || null
  }
  return chunks.reduce<string | null>(
    (acc, { label, content }) => mergePromptSection(acc, label, content),
    origin,
  )
}

export function parsePanelBinding(panel: Panel | null): PanelAssetBinding {
  if (!panel) return {}
  const effective = panel.effective_binding && typeof panel.effective_binding === 'object'
    ? panel.effective_binding
    : null
  const overrides = panel.asset_overrides ?? []
  const characterOverrides = overrides
    .filter((item) => item.asset_type === 'character')
    .sort((a, b) => (a.is_primary ? 0 : 1) - (b.is_primary ? 0 : 1) || Number(a.priority ?? 0) - Number(b.priority ?? 0))
  const locationOverrides = overrides
    .filter((item) => item.asset_type === 'location')
    .sort((a, b) => (a.is_primary ? 0 : 1) - (b.is_primary ? 0 : 1) || Number(a.priority ?? 0) - Number(b.priority ?? 0))
  const voiceOverrides = overrides
    .filter((item) => item.asset_type === 'voice')
    .sort((a, b) => (a.is_primary ? 0 : 1) - (b.is_primary ? 0 : 1) || Number(a.priority ?? 0) - Number(b.priority ?? 0))

  const effectiveCharacters = Array.isArray(effective?.characters) ? effective.characters : []
  const effectiveLocations = Array.isArray(effective?.locations) ? effective.locations : []
  const effectiveVoice = (effective?.effective_voice && typeof effective.effective_voice === 'object')
    ? (effective.effective_voice as Record<string, unknown>)
    : null

  const effectivePrimaryCharacter = (effectiveCharacters.find((item) => {
    if (!item || typeof item !== 'object') return false
    return Boolean((item as Record<string, unknown>).is_primary)
  }) ?? effectiveCharacters[0]) as Record<string, unknown> | undefined
  const effectivePrimaryLocation = (effectiveLocations.find((item) => {
    if (!item || typeof item !== 'object') return false
    return Boolean((item as Record<string, unknown>).is_primary)
  }) ?? effectiveLocations[0]) as Record<string, unknown> | undefined

  const characterIds = effectiveCharacters
    .map((item) => (item && typeof item === 'object' ? (item as Record<string, unknown>).asset_id : null))
    .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
  const locationIds = effectiveLocations
    .map((item) => (item && typeof item === 'object' ? (item as Record<string, unknown>).asset_id : null))
    .filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
  const voiceIds = (effectiveVoice && typeof effectiveVoice.voice_id === 'string')
    ? [effectiveVoice.voice_id]
    : voiceOverrides.map((item) => item.asset_id)

  const fallbackCharacter = characterOverrides[0]
  const fallbackLocation = locationOverrides[0]
  const fallbackVoice = voiceOverrides[0]

  return {
    asset_character_ids: characterIds.length > 0
      ? characterIds
      : characterOverrides.length > 0
        ? characterOverrides.map((item) => item.asset_id)
        : [],
    asset_character_id: typeof effectivePrimaryCharacter?.asset_id === 'string'
      ? effectivePrimaryCharacter.asset_id
      : fallbackCharacter?.asset_id,
    asset_character_name: typeof effectivePrimaryCharacter?.asset_name === 'string'
      ? effectivePrimaryCharacter.asset_name
      : (fallbackCharacter?.asset_name || undefined),
    asset_location_ids: locationIds.length > 0
      ? locationIds
      : locationOverrides.length > 0
        ? locationOverrides.map((item) => item.asset_id)
        : [],
    asset_location_id: typeof effectivePrimaryLocation?.asset_id === 'string'
      ? effectivePrimaryLocation.asset_id
      : fallbackLocation?.asset_id,
    asset_location_name: typeof effectivePrimaryLocation?.asset_name === 'string'
      ? effectivePrimaryLocation.asset_name
      : (fallbackLocation?.asset_name || undefined),
    asset_voice_ids: voiceIds,
    asset_voice_id: typeof effectiveVoice?.voice_id === 'string'
      ? effectiveVoice.voice_id
      : fallbackVoice?.asset_id,
    asset_voice_name: typeof effectiveVoice?.voice_name === 'string'
      ? effectiveVoice.voice_name
      : (fallbackVoice?.asset_name || undefined),
  }
}

export function buildCharacterApplyPlan(
  panel: Panel,
  character: GlobalCharacterAsset,
  mode: PromptApplyMode,
  voices: GlobalVoice[],
): CharacterApplyPlan {
  const nextPrompt = buildPromptByMode(
    panel.visual_prompt,
    [
      { label: '角色设定：', content: character.prompt_template },
      { label: '角色补充：', content: character.description },
    ],
    mode,
  )
  const currentBinding = parsePanelBinding(panel)
  const fallbackVoiceId = currentBinding.asset_voice_id || character.default_voice_id || null
  const fallbackVoiceName = character.default_voice_id
    ? voices.find((item) => item.id === character.default_voice_id)?.name
    : undefined

  return {
    nextPrompt,
    nextReferenceImageUrl: panel.reference_image_url || character.reference_image_url || null,
    fallbackVoiceId,
    fallbackVoiceName,
  }
}

export function buildLocationApplyPlan(
  panel: Panel,
  location: GlobalLocationAsset,
  mode: PromptApplyMode,
): LocationApplyPlan {
  const nextPrompt = buildPromptByMode(
    panel.visual_prompt,
    [
      { label: '地点设定：', content: location.prompt_template },
      { label: '地点补充：', content: location.description },
    ],
    mode,
  )
  return {
    nextPrompt,
    nextReferenceImageUrl: panel.reference_image_url || location.reference_image_url || null,
  }
}
