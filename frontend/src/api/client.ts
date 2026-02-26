import axios from 'axios'
import { getApiBaseUrl } from '../runtime'

const client = axios.create({
  timeout: 30000,
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
    console.error('[API 错误]', message)
    return Promise.reject(error)
  },
)

export default client
