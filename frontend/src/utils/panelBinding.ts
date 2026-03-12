import type { Panel } from '../types/panel'
import type { PanelEffectiveBinding, ScriptScopedOverride } from '../types/scriptAssets'
import type { PanelAssetBinding, PanelBindingSummary } from '../types/panelBinding'

export type PanelBindingTab = 'character' | 'location' | 'voice'

interface ResolvedPanelBindingState {
  assetOverrides?: ScriptScopedOverride[]
  effectiveBinding?: PanelEffectiveBinding | null
}

function uniqueIds(ids: Array<string | null | undefined>): string[] {
  return Array.from(new Set(ids.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)))
}

function sortOverridesByType(panel: Panel, assetType: PanelBindingTab): ScriptScopedOverride[] {
  return (panel.asset_overrides ?? [])
    .filter((item) => item.asset_type === assetType)
    .sort((a, b) => (a.is_primary ? 0 : 1) - (b.is_primary ? 0 : 1) || Number(a.priority ?? 0) - Number(b.priority ?? 0))
}

function pickPrimaryEffectiveItem(items: Array<Record<string, unknown>> | undefined): Record<string, unknown> | undefined {
  if (!items || items.length === 0) return undefined
  return items.find((item) => Boolean(item?.is_primary)) ?? items[0]
}

function readEffectiveAssetIds(items: Array<Record<string, unknown>> | undefined): string[] {
  if (!items || items.length === 0) return []
  return uniqueIds(items.map((item) => (typeof item.asset_id === 'string' ? item.asset_id : null)))
}

function readEffectiveVoice(effective: PanelEffectiveBinding | null): Record<string, unknown> | null {
  return effective?.effective_voice ?? null
}

function readEffectiveAssetNames(items: Array<Record<string, unknown>> | undefined): string[] {
  if (!items || items.length === 0) return []
  return uniqueIds(items.map((item) => (typeof item.asset_name === 'string' ? item.asset_name : null)))
}

export function getPanelBindingPrimaryAssetId(binding: PanelAssetBinding, tab: PanelBindingTab): string | null {
  if (tab === 'character') return binding.asset_character_id ?? null
  if (tab === 'location') return binding.asset_location_id ?? null
  return binding.asset_voice_id ?? null
}

export function getPanelBindingAssetIds(binding: PanelAssetBinding, tab: PanelBindingTab): string[] {
  const primaryId = getPanelBindingPrimaryAssetId(binding, tab)
  if (tab === 'character') return uniqueIds([...(binding.asset_character_ids ?? []), primaryId])
  if (tab === 'location') return uniqueIds([...(binding.asset_location_ids ?? []), primaryId])
  return uniqueIds([...(binding.asset_voice_ids ?? []), primaryId])
}

export function parsePanelBinding(panel: Panel | null): PanelAssetBinding {
  if (!panel) return {}

  const effective = panel.effective_binding ?? null
  const characterOverrides = sortOverridesByType(panel, 'character')
  const locationOverrides = sortOverridesByType(panel, 'location')
  const voiceOverrides = sortOverridesByType(panel, 'voice')

  const effectivePrimaryCharacter = pickPrimaryEffectiveItem(effective?.characters)
  const effectivePrimaryLocation = pickPrimaryEffectiveItem(effective?.locations)
  const effectiveVoice = readEffectiveVoice(effective)

  const characterIds = readEffectiveAssetIds(effective?.characters)
  const locationIds = readEffectiveAssetIds(effective?.locations)
  const voiceIds = typeof effectiveVoice?.voice_id === 'string'
    ? [effectiveVoice.voice_id]
    : uniqueIds(voiceOverrides.map((item) => item.asset_id as string | null))

  const fallbackCharacter = characterOverrides[0]
  const fallbackLocation = locationOverrides[0]
  const fallbackVoice = voiceOverrides[0]

  return {
    asset_character_ids: characterIds.length > 0
      ? characterIds
      : uniqueIds(characterOverrides.map((item) => item.asset_id as string | null)),
    asset_character_id: typeof effectivePrimaryCharacter?.asset_id === 'string'
      ? effectivePrimaryCharacter.asset_id
      : typeof fallbackCharacter?.asset_id === 'string'
        ? fallbackCharacter.asset_id
        : undefined,
    asset_character_name: typeof effectivePrimaryCharacter?.asset_name === 'string'
      ? effectivePrimaryCharacter.asset_name
      : (typeof fallbackCharacter?.asset_name === 'string' ? fallbackCharacter.asset_name : undefined),
    asset_location_ids: locationIds.length > 0
      ? locationIds
      : uniqueIds(locationOverrides.map((item) => item.asset_id as string | null)),
    asset_location_id: typeof effectivePrimaryLocation?.asset_id === 'string'
      ? effectivePrimaryLocation.asset_id
      : typeof fallbackLocation?.asset_id === 'string'
        ? fallbackLocation.asset_id
        : undefined,
    asset_location_name: typeof effectivePrimaryLocation?.asset_name === 'string'
      ? effectivePrimaryLocation.asset_name
      : (typeof fallbackLocation?.asset_name === 'string' ? fallbackLocation.asset_name : undefined),
    asset_voice_ids: voiceIds,
    asset_voice_id: typeof effectiveVoice?.voice_id === 'string'
      ? effectiveVoice.voice_id
      : typeof fallbackVoice?.asset_id === 'string'
        ? fallbackVoice.asset_id
        : undefined,
    asset_voice_name: typeof effectiveVoice?.voice_name === 'string'
      ? effectiveVoice.voice_name
      : (typeof fallbackVoice?.asset_name === 'string' ? fallbackVoice.asset_name : undefined),
  }
}

export function buildResolvedPanelBindingState(
  panel: Panel,
  nextState: ResolvedPanelBindingState = {},
): Panel {
  const resolvedPanel: Panel = {
    ...panel,
    asset_overrides: nextState.assetOverrides ?? panel.asset_overrides,
    effective_binding: Object.prototype.hasOwnProperty.call(nextState, 'effectiveBinding')
      ? (nextState.effectiveBinding ?? null)
      : panel.effective_binding,
  }

  return {
    ...resolvedPanel,
    voice_id: getPanelBindingPrimaryAssetId(parsePanelBinding(resolvedPanel), 'voice'),
  }
}

export function summarizePanelBinding(panel: Panel): PanelBindingSummary {
  const effective = panel.effective_binding
  if (!effective) {
    const fallback = parsePanelBinding(panel)
    return {
      characterNames: fallback.asset_character_name ? [fallback.asset_character_name] : [],
      locationNames: fallback.asset_location_name ? [fallback.asset_location_name] : [],
      voiceName: fallback.asset_voice_name,
      voiceId: fallback.asset_voice_id,
      effectivePrompt: panel.visual_prompt ?? panel.script_text ?? undefined,
      effectiveReferenceImageUrl: panel.reference_image_url ?? undefined,
      compiled: false,
    }
  }

  const binding = parsePanelBinding(panel)
  const effectiveCharacterNames = readEffectiveAssetNames(effective.characters)
  const effectiveLocationNames = readEffectiveAssetNames(effective.locations)
  return {
    characterNames: effectiveCharacterNames.length > 0
      ? effectiveCharacterNames
      : (binding.asset_character_name ? [binding.asset_character_name] : []),
    locationNames: effectiveLocationNames.length > 0
      ? effectiveLocationNames
      : (binding.asset_location_name ? [binding.asset_location_name] : []),
    voiceName: binding.asset_voice_name,
    voiceId: binding.asset_voice_id,
    effectivePrompt: effective.effective_visual_prompt ?? panel.visual_prompt ?? panel.script_text ?? undefined,
    effectiveReferenceImageUrl: effective.effective_reference_image_url ?? panel.reference_image_url ?? undefined,
    compiled: true,
  }
}
