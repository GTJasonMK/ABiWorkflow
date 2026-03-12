import axios from 'axios'
import { getApiBaseUrl } from '../runtime'

export const DEFAULT_API_TIMEOUT_MS = 60_000

declare module 'axios' {
  interface AxiosRequestConfig {
    suppressErrorLog?: boolean
  }

  interface InternalAxiosRequestConfig {
    suppressErrorLog?: boolean
  }
}

const client = axios.create({
  timeout: DEFAULT_API_TIMEOUT_MS,
})

client.interceptors.request.use((config) => {
  // API 地址支持运行时切换（系统设置修改后当前会话立即生效）。
  if (!config.baseURL) {
    config.baseURL = getApiBaseUrl()
  }
  return config
})

client.interceptors.response.use(
  (response) => response,
  (error) => {
    const message = error.response?.data?.detail ?? error.message ?? '请求失败'
    if (!error.config?.suppressErrorLog) {
      console.error('[API 错误]', message)
    }
    return Promise.reject(error)
  },
)

export default client
