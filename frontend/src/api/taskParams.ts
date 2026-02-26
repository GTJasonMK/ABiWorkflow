export interface StartTaskOptions {
  forceRecover?: boolean
  forceRegenerate?: boolean
}

export function buildAsyncTaskQuery(options: StartTaskOptions = {}): string {
  const query = new URLSearchParams({ async_mode: 'true' })
  if (options.forceRecover) {
    query.set('force_recover', 'true')
  }
  if (options.forceRegenerate) {
    query.set('force_regenerate', 'true')
  }
  return query.toString()
}
