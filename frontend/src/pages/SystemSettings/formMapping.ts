import type { RuntimeSettingsUpdatePayload, RuntimeSummaryPayload } from '../../api/system'
import type { BackendSettingsFormValues } from './types'

function normalizeInput(value: string | undefined | null): string {
  return (value ?? '').trim()
}

function assignIfNonEmpty<T extends keyof RuntimeSettingsUpdatePayload>(
  payload: RuntimeSettingsUpdatePayload,
  key: T,
  value: string,
): void {
  const normalized = normalizeInput(value)
  if (normalized) {
    payload[key] = normalized as RuntimeSettingsUpdatePayload[T]
  }
}

export function buildUpdatePayload(values: BackendSettingsFormValues): RuntimeSettingsUpdatePayload {
  const payload: RuntimeSettingsUpdatePayload = {
    app_name: normalizeInput(values.app_name),
    debug: values.debug,
    llm_provider: values.llm_provider,
    openai_model: normalizeInput(values.openai_model),
    anthropic_model: normalizeInput(values.anthropic_model),
    deepseek_model: normalizeInput(values.deepseek_model),
    ggk_text_model: normalizeInput(values.ggk_text_model),
    video_provider: normalizeInput(values.video_provider),
    video_output_dir: normalizeInput(values.video_output_dir),
    composition_output_dir: normalizeInput(values.composition_output_dir),
    video_provider_max_duration_seconds: values.video_provider_max_duration_seconds,
    video_poll_interval_seconds: values.video_poll_interval_seconds,
    video_task_timeout_seconds: values.video_task_timeout_seconds,
    ggk_video_model: normalizeInput(values.ggk_video_model),
    ggk_video_aspect_ratio: normalizeInput(values.ggk_video_aspect_ratio),
    ggk_video_resolution: normalizeInput(values.ggk_video_resolution),
    ggk_video_preset: normalizeInput(values.ggk_video_preset),
    ggk_video_model_duration_profiles: normalizeInput(values.ggk_video_model_duration_profiles),
    ggk_request_timeout_seconds: values.ggk_request_timeout_seconds,
    tts_voice: normalizeInput(values.tts_voice),
    video_http_generate_path: normalizeInput(values.video_http_generate_path),
    video_http_status_path: normalizeInput(values.video_http_status_path),
    video_http_task_id_path: normalizeInput(values.video_http_task_id_path),
    video_http_status_value_path: normalizeInput(values.video_http_status_value_path),
    video_http_progress_path: normalizeInput(values.video_http_progress_path),
    video_http_result_url_path: normalizeInput(values.video_http_result_url_path),
    video_http_error_path: normalizeInput(values.video_http_error_path),
    video_http_request_timeout_seconds: values.video_http_request_timeout_seconds,
  }

  // URL 与连接类字段：留空表示不修改已有值，避免空值覆盖 .env 中已有配置。
  assignIfNonEmpty(payload, 'openai_base_url', values.openai_base_url)
  assignIfNonEmpty(payload, 'deepseek_base_url', values.deepseek_base_url)
  assignIfNonEmpty(payload, 'ggk_base_url', values.ggk_base_url)
  assignIfNonEmpty(payload, 'video_http_base_url', values.video_http_base_url)

  // 密钥：留空表示不修改已有值。
  assignIfNonEmpty(payload, 'openai_api_key', values.openai_api_key)
  assignIfNonEmpty(payload, 'anthropic_api_key', values.anthropic_api_key)
  assignIfNonEmpty(payload, 'deepseek_api_key', values.deepseek_api_key)
  assignIfNonEmpty(payload, 'ggk_api_key', values.ggk_api_key)
  assignIfNonEmpty(payload, 'video_http_api_key', values.video_http_api_key)

  // 连接串：留空表示不修改已有值。
  assignIfNonEmpty(payload, 'database_url', values.database_url)
  assignIfNonEmpty(payload, 'redis_url', values.redis_url)
  assignIfNonEmpty(payload, 'celery_broker_url', values.celery_broker_url)
  assignIfNonEmpty(payload, 'celery_result_backend', values.celery_result_backend)

  return payload
}

export function mapRuntimeToFormValues(runtime: RuntimeSummaryPayload): BackendSettingsFormValues {
  return {
    app_name: runtime.app.name || 'AbiWorkflow',
    debug: Boolean(runtime.app.debug),
    llm_provider: (runtime.llm.provider || 'openai') as 'openai' | 'anthropic' | 'deepseek' | 'ggk',
    openai_model: runtime.llm.openai.model || 'gpt-4o',
    openai_base_url: runtime.llm.openai.base_url ?? '',
    openai_api_key: '',
    anthropic_model: runtime.llm.anthropic.model || 'claude-sonnet-4-20250514',
    anthropic_api_key: '',
    deepseek_model: runtime.llm.deepseek.model || 'deepseek-chat',
    deepseek_base_url: runtime.llm.deepseek.base_url || 'https://api.deepseek.com/v1',
    deepseek_api_key: '',
    ggk_base_url: runtime.llm.ggk.base_url ?? '',
    ggk_text_model: runtime.llm.ggk.text_model || 'grok-3',
    ggk_api_key: '',
    video_provider: runtime.video.provider || 'mock',
    video_output_dir: runtime.video.output_dir || './outputs/videos',
    composition_output_dir: runtime.video.composition_output_dir || './outputs/compositions',
    video_provider_max_duration_seconds: runtime.video.provider_max_duration_seconds ?? 6,
    video_poll_interval_seconds: runtime.video.poll_interval_seconds ?? 1,
    video_task_timeout_seconds: runtime.video.task_timeout_seconds ?? 300,
    ggk_video_model: runtime.video.ggk_provider.video_model || 'grok-imagine-1.0-video',
    ggk_video_aspect_ratio: runtime.video.ggk_provider.aspect_ratio || '16:9',
    ggk_video_resolution: runtime.video.ggk_provider.resolution || 'SD',
    ggk_video_preset: runtime.video.ggk_provider.preset || 'normal',
    ggk_video_model_duration_profiles: runtime.video.ggk_provider.model_duration_profiles ?? '',
    ggk_request_timeout_seconds: runtime.video.ggk_provider.request_timeout_seconds ?? 300,
    tts_voice: runtime.video.tts_voice || 'zh-CN-XiaoxiaoNeural',
    video_http_base_url: runtime.video.http_provider.base_url ?? '',
    video_http_api_key: '',
    video_http_generate_path: runtime.video.http_provider.generate_path || '/v1/video/generations',
    video_http_status_path: runtime.video.http_provider.status_path || '/v1/video/generations/{task_id}',
    video_http_task_id_path: runtime.video.http_provider.task_id_path || 'task_id',
    video_http_status_value_path: runtime.video.http_provider.status_value_path || 'status',
    video_http_progress_path: runtime.video.http_provider.progress_path || 'progress_percent',
    video_http_result_url_path: runtime.video.http_provider.result_url_path || 'result_url',
    video_http_error_path: runtime.video.http_provider.error_path || 'error_message',
    video_http_request_timeout_seconds: runtime.video.http_provider.request_timeout_seconds ?? 60,
    // 连接串默认留空，避免覆盖为脱敏值；输入新值才会更新。
    database_url: '',
    redis_url: '',
    celery_broker_url: '',
    celery_result_backend: '',
  }
}

export function resetSensitiveFields(): Partial<BackendSettingsFormValues> {
  return {
    openai_api_key: '',
    anthropic_api_key: '',
    deepseek_api_key: '',
    ggk_api_key: '',
    video_http_api_key: '',
    database_url: '',
    redis_url: '',
    celery_broker_url: '',
    celery_result_backend: '',
  }
}
