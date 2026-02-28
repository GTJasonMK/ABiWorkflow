export interface ProviderConfig {
  id: string
  provider_key: string
  provider_type: string
  name: string
  base_url: string
  submit_path: string
  status_path: string
  result_path: string
  auth_scheme: string
  api_key_configured: boolean
  api_key_preview: string | null
  api_key_header: string
  extra_headers: Record<string, unknown>
  request_template: Record<string, unknown>
  response_mapping: Record<string, unknown>
  status_mapping: Record<string, unknown>
  timeout_seconds: number
  enabled: boolean
  created_at: string | null
  updated_at: string | null
}

export interface ProviderUpsertPayload {
  provider_type: string
  name: string
  base_url: string
  submit_path: string
  status_path: string
  result_path: string
  auth_scheme: string
  api_key?: string
  api_key_header: string
  extra_headers: Record<string, unknown>
  request_template: Record<string, unknown>
  response_mapping: Record<string, unknown>
  status_mapping: Record<string, unknown>
  timeout_seconds: number
  enabled: boolean
}
