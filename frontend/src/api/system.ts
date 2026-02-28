import client from './client'
import type { ApiResponse } from '../types/api'

export interface HealthPayload {
  status: string
  app: string
}

export interface RuntimeSummaryPayload {
  app: {
    name: string
    debug: boolean
    database_url: string
  }
  llm: {
    provider: string
    active_model: string
    any_key_configured: boolean
    openai: {
      model: string
      base_url: string | null
      api_key_configured: boolean
      api_key_preview: string | null
    }
    anthropic: {
      model: string
      api_key_configured: boolean
      api_key_preview: string | null
    }
    deepseek: {
      model: string
      base_url: string | null
      api_key_configured: boolean
      api_key_preview: string | null
    }
    ggk: {
      base_url: string
      text_model: string
      api_key_configured: boolean
      api_key_preview: string | null
    }
  }
  queue: {
    redis_url: string
    celery_broker_url: string
    celery_result_backend: string
    celery_worker_online: boolean
  }
  video: {
    provider: string
    output_dir: string
    composition_output_dir: string
    provider_max_duration_seconds: number
    poll_interval_seconds: number
    task_timeout_seconds: number
    tts_voice: string
    http_provider: {
      base_url: string
      api_key_configured: boolean
      api_key_preview: string | null
      generate_path: string
      status_path: string
      task_id_path: string
      status_value_path: string
      progress_path: string
      result_url_path: string
      error_path: string
      request_timeout_seconds: number
    }
    ggk_provider: {
      video_model: string
      aspect_ratio: string
      resolution: string
      preset: string
      model_duration_profiles: string
      request_timeout_seconds: number
    }
  }
}

export interface RuntimeSettingsUpdatePayload {
  app_name?: string
  debug?: boolean
  database_url?: string
  llm_provider?: 'openai' | 'anthropic' | 'deepseek' | 'ggk'
  openai_api_key?: string
  openai_model?: string
  openai_base_url?: string
  anthropic_api_key?: string
  anthropic_model?: string
  deepseek_api_key?: string
  deepseek_base_url?: string
  deepseek_model?: string
  ggk_base_url?: string
  ggk_api_key?: string
  ggk_text_model?: string
  redis_url?: string
  celery_broker_url?: string
  celery_result_backend?: string
  video_provider?: string
  video_output_dir?: string
  composition_output_dir?: string
  video_provider_max_duration_seconds?: number
  video_poll_interval_seconds?: number
  video_task_timeout_seconds?: number
  video_http_base_url?: string
  video_http_api_key?: string
  video_http_generate_path?: string
  video_http_status_path?: string
  video_http_task_id_path?: string
  video_http_status_value_path?: string
  video_http_progress_path?: string
  video_http_result_url_path?: string
  video_http_error_path?: string
  video_http_request_timeout_seconds?: number
  ggk_video_model?: string
  ggk_video_aspect_ratio?: string
  ggk_video_resolution?: string
  ggk_video_preset?: string
  ggk_video_model_duration_profiles?: string
  ggk_request_timeout_seconds?: number
  tts_voice?: string
}

export interface GgkImportRequestPayload {
  project_path?: string
  base_url?: string
  prefer_internal_key?: boolean
  auto_switch_provider?: boolean
}

export interface GgkImportResultPayload {
  imported: boolean
  source: {
    project_path: string
    env_path: string
    db_path: string
    api_key_source: string
    base_url_reachable: boolean
  }
  runtime: RuntimeSummaryPayload
}

let runtimeRequest: Promise<RuntimeSummaryPayload> | null = null

function extractWrappedData<T>(payload: unknown): T | null {
  if (payload && typeof payload === 'object' && 'data' in payload) {
    return (payload as { data?: T | null }).data ?? null
  }
  return null
}

function normalizeRuntimeSummary(payload: RuntimeSummaryPayload): RuntimeSummaryPayload {
  const { app, llm, queue, video } = payload
  if (!app || !llm || !queue || !video) {
    throw new Error('获取运行配置失败：响应字段缺失')
  }
  return payload
}

/** 获取后端健康状态 */
export async function getHealthStatus(): Promise<HealthPayload> {
  const resp = await client.get<ApiResponse<HealthPayload> | HealthPayload>('/health')
  const wrapped = extractWrappedData<HealthPayload>(resp.data)
  if (wrapped) return wrapped

  const direct = resp.data as Partial<HealthPayload>
  if (typeof direct?.status === 'string' && typeof direct?.app === 'string') {
    return { status: direct.status, app: direct.app }
  }

  throw new Error('健康检查失败：响应格式非法')
}

/** 获取运行配置摘要 */
export async function getRuntimeSummary(): Promise<RuntimeSummaryPayload> {
  if (runtimeRequest) return runtimeRequest

  runtimeRequest = (async () => {
    const resp = await client.get<ApiResponse<RuntimeSummaryPayload>>('/system/runtime')
    const wrapped = extractWrappedData<RuntimeSummaryPayload>(resp.data)
    if (!wrapped) {
      throw new Error('获取运行配置失败：响应格式非法')
    }
    return normalizeRuntimeSummary(wrapped)
  })()

  try {
    return await runtimeRequest
  } finally {
    runtimeRequest = null
  }
}

/** 更新后端运行配置 */
export async function updateRuntimeSettings(payload: RuntimeSettingsUpdatePayload): Promise<RuntimeSummaryPayload> {
  const resp = await client.put<ApiResponse<RuntimeSummaryPayload>>('/system/runtime', payload)
  const wrapped = extractWrappedData<RuntimeSummaryPayload>(resp.data)
  if (wrapped) {
    return normalizeRuntimeSummary(wrapped)
  }

  throw new Error('保存系统配置失败：响应格式非法')
}

/** 从本地 GGK 项目导入配置 */
export async function importRuntimeFromGgk(payload: GgkImportRequestPayload = {}): Promise<GgkImportResultPayload> {
  const resp = await client.post<ApiResponse<GgkImportResultPayload>>('/system/ggk/import', payload)
  const wrapped = extractWrappedData<GgkImportResultPayload>(resp.data)
  if (wrapped) {
    return {
      ...wrapped,
      runtime: normalizeRuntimeSummary(wrapped.runtime),
    }
  }

  throw new Error('导入 GGK 配置失败：响应格式非法')
}
