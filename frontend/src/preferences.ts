const DEFAULT_HOME_KEY = 'abi_default_home_path'
const DEFAULT_HOME = '/dashboard'
const SUPPORTED_HOME_PATHS = ['/dashboard', '/projects', '/tasks', '/operations', '/settings', '/guide']

export function listSupportedHomePaths(): string[] {
  return [...SUPPORTED_HOME_PATHS]
}

export function getDefaultHomePath(): string {
  if (typeof window === 'undefined') return DEFAULT_HOME
  try {
    const raw = window.localStorage.getItem(DEFAULT_HOME_KEY)?.trim()
    if (!raw) return DEFAULT_HOME
    return SUPPORTED_HOME_PATHS.includes(raw) ? raw : DEFAULT_HOME
  } catch {
    return DEFAULT_HOME
  }
}

export function setDefaultHomePath(path: string): void {
  if (typeof window === 'undefined') return
  if (!SUPPORTED_HOME_PATHS.includes(path)) return
  try {
    window.localStorage.setItem(DEFAULT_HOME_KEY, path)
  } catch {
    // ignore localStorage errors
  }
}
