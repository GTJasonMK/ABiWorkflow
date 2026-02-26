type ErrorWithResponse = {
  response?: {
    data?: {
      detail?: string
      message?: string
    }
  }
  message?: string
}

export function getApiErrorMessage(error: unknown, fallback: string): string {
  const err = error as ErrorWithResponse
  return err?.response?.data?.detail ?? err?.response?.data?.message ?? err?.message ?? fallback
}

