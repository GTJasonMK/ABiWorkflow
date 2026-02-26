import client from './client'
import type { ApiResponse } from '../types/api'

export interface HealthPayload {
  status: string
  app: string
}

export interface RuntimeSummaryPayload {
  app_name: string
  debug: boolean
  llm_provider: string
  llm_model: string
  llm_key_configured: boolean
  video_provider: string
  redis_url: string
  celery_worker_online: boolean
  video_output_dir: string
  composition_output_dir: string
  app?: {
    name: string
    debug: boolean
    database_url: string
  }
  llm?: {
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
  queue?: {
    redis_url: string
    celery_broker_url: string
    celery_result_backend: string
    celery_worker_online: boolean
  }
  video?: {
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
  const appName = payload.app?.name ?? payload.app_name ?? 'AbiWorkflow'
  const debug = payload.app?.debug ?? payload.debug ?? false
  const llmSource = payload.llm
  const videoSource = payload.video
  const llmProvider = llmSource?.provider ?? payload.llm_provider ?? 'unknown'
  const llmModel = llmSource?.active_model ?? payload.llm_model ?? 'unknown'
  const llmKeyConfigured = llmSource?.any_key_configured ?? payload.llm_key_configured ?? false
  const videoProvider = videoSource?.provider ?? payload.video_provider ?? 'unknown'
  const redisUrl = payload.queue?.redis_url ?? payload.redis_url ?? 'unknown'
  const celeryWorkerOnline = payload.queue?.celery_worker_online ?? payload.celery_worker_online ?? false
  const videoOutputDir = videoSource?.output_dir ?? payload.video_output_dir ?? 'unknown'
  const compositionOutputDir = videoSource?.composition_output_dir ?? payload.composition_output_dir ?? 'unknown'

  return {
    ...payload,
    app_name: appName,
    debug,
    llm_provider: llmProvider,
    llm_model: llmModel,
    llm_key_configured: llmKeyConfigured,
    video_provider: videoProvider,
    redis_url: redisUrl,
    celery_worker_online: celeryWorkerOnline,
    video_output_dir: videoOutputDir,
    composition_output_dir: compositionOutputDir,
    app: payload.app ?? {
      name: appName,
      debug,
      database_url: 'unknown',
    },
    llm: {
      provider: llmProvider,
      active_model: llmModel,
      any_key_configured: llmKeyConfigured,
      openai: llmSource?.openai ?? {
        model: 'unknown',
        base_url: null,
        api_key_configured: false,
        api_key_preview: null,
      },
      anthropic: llmSource?.anthropic ?? {
        model: 'unknown',
        api_key_configured: false,
        api_key_preview: null,
      },
      deepseek: llmSource?.deepseek ?? {
        model: 'unknown',
        base_url: null,
        api_key_configured: false,
        api_key_preview: null,
      },
      ggk: llmSource?.ggk ?? {
        base_url: '',
        text_model: 'grok-3',
        api_key_configured: false,
        api_key_preview: null,
      },
    },
    queue: payload.queue ?? {
      redis_url: redisUrl,
      celery_broker_url: 'unknown',
      celery_result_backend: 'unknown',
      celery_worker_online: celeryWorkerOnline,
    },
    video: {
      provider: videoProvider,
      output_dir: videoOutputDir,
      composition_output_dir: compositionOutputDir,
      provider_max_duration_seconds: videoSource?.provider_max_duration_seconds ?? 0,
      poll_interval_seconds: videoSource?.poll_interval_seconds ?? 0,
      task_timeout_seconds: videoSource?.task_timeout_seconds ?? 0,
      tts_voice: videoSource?.tts_voice ?? 'unknown',
      http_provider: videoSource?.http_provider ?? {
        base_url: '',
        api_key_configured: false,
        api_key_preview: null,
        generate_path: '',
        status_path: '',
        task_id_path: '',
        status_value_path: '',
        progress_path: '',
        result_url_path: '',
        error_path: '',
        request_timeout_seconds: 0,
      },
      ggk_provider: videoSource?.ggk_provider ?? {
        video_model: 'grok-imagine-1.0-video',
        aspect_ratio: '16:9',
        resolution: 'SD',
        preset: 'normal',
        model_duration_profiles: '',
        request_timeout_seconds: 0,
      },
    },
  }
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
