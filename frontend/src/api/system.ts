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
    model: string
    base_url: string | null
    api_key_configured: boolean
    api_key_preview: string | null
  }
  queue: {
    redis_url: string
    celery_broker_url: string
    celery_result_backend: string
    celery_worker_online: boolean
    queue_mode: 'redis' | 'sqlite'
    redis_available: boolean
    fallback_active: boolean
    fallback_reason: string | null
  }
  video: {
    provider: string
    output_dir: string
    composition_output_dir: string
    provider_max_duration_seconds: number
    poll_interval_seconds: number
    task_timeout_seconds: number
    project_asset_publish_global_default: boolean
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
      base_url: string
      api_key_configured: boolean
      api_key_preview: string | null
      video_model: string
      aspect_ratio: string
      resolution: string
      preset: string
      model_duration_profiles: string
      request_timeout_seconds: number
    }
    portrait: {
      api_base_url: string
      api_key_configured: boolean
      api_key_preview: string | null
      image_model: string
    }
  }
  models: {
    default_bindings: Record<string, unknown>
    capability_profiles: Record<string, unknown>
  }
}

export interface RuntimeSettingsUpdatePayload {
  app_name?: string
  debug?: boolean
  database_url?: string
  llm_api_key?: string
  llm_model?: string
  llm_base_url?: string
  ggk_base_url?: string
  ggk_api_key?: string
  redis_url?: string
  celery_broker_url?: string
  celery_result_backend?: string
  video_provider?: string
  video_output_dir?: string
  composition_output_dir?: string
  video_provider_max_duration_seconds?: number
  video_poll_interval_seconds?: number
  video_task_timeout_seconds?: number
  project_asset_publish_global_default?: boolean
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
  portrait_api_base_url?: string
  portrait_api_key?: string
  portrait_image_model?: string
  default_model_bindings?: string
  model_capability_profiles?: string
}

let runtimeRequest: Promise<RuntimeSummaryPayload> | null = null

function extractWrappedData<T>(payload: unknown): T | null {
  if (payload && typeof payload === 'object' && 'data' in payload) {
    return (payload as { data?: T | null }).data ?? null
  }
  return null
}

function normalizeRuntimeSummary(payload: RuntimeSummaryPayload): RuntimeSummaryPayload {
  const { app, llm, queue, video, models } = payload
  if (!app || !llm || !queue || !video || !models) {
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
