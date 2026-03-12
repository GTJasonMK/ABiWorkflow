import type { Panel } from '../../types/panel'
import type { GlobalCharacterAsset, GlobalLocationAsset } from '../../types/assetHub'
import type {
  AssetApplyPlan,
  AssetSourceScope,
  AssetTabKey,
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

function pickReferenceImageUrl(...candidates: Array<string | null | undefined>): string | null {
  for (const candidate of candidates) {
    const normalized = normalizeText(candidate)
    if (normalized) return normalized
  }
  return null
}

export function buildCharacterApplyPlan(
  panel: Panel,
  character: GlobalCharacterAsset,
  mode: PromptApplyMode,
): AssetApplyPlan {
  const nextPrompt = buildPromptByMode(
    panel.visual_prompt,
    [
      { label: '角色设定：', content: character.prompt_template },
      { label: '角色补充：', content: character.description },
    ],
    mode,
  )

  return {
    nextPrompt,
    nextReferenceImageUrl: pickReferenceImageUrl(panel.reference_image_url, character.reference_image_url),
  }
}

export function buildLocationApplyPlan(
  panel: Panel,
  location: GlobalLocationAsset,
  mode: PromptApplyMode,
): AssetApplyPlan {
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
    nextReferenceImageUrl: pickReferenceImageUrl(panel.reference_image_url, location.reference_image_url),
  }
}
