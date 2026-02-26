import { useEffect, useRef, useState } from 'react'

export interface FrameData {
  time: number
  dataUrl: string
}

interface UseFrameExtractorOptions {
  src: string | null
  thumbnailHeight?: number
  containerWidth: number
}

interface UseFrameExtractorReturn {
  frames: FrameData[]
  loading: boolean
  progress: number
}

/**
 * 从视频中提取帧缩略图，用于胶片条时间线显示。
 * 使用离屏 <video> + Canvas drawImage 逐帧捕获 JPEG 缩略图。
 */
export function useFrameExtractor({
  src,
  thumbnailHeight = 56,
  containerWidth,
}: UseFrameExtractorOptions): UseFrameExtractorReturn {
  const [frames, setFrames] = useState<FrameData[]>([])
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const abortRef = useRef(false)

  useEffect(() => {
    abortRef.current = false
    setFrames([])
    setProgress(0)

    if (!src || containerWidth <= 0) {
      setLoading(false)
      return
    }

    setLoading(true)

    const video = document.createElement('video')
    video.crossOrigin = 'anonymous'
    video.muted = true
    video.preload = 'auto'
    video.src = src

    const canvas = document.createElement('canvas')
    const ctx = canvas.getContext('2d')!

    const extractFrames = async () => {
      // 等待视频元数据加载完成
      await new Promise<void>((resolve, reject) => {
        video.onloadedmetadata = () => resolve()
        video.onerror = () => reject(new Error('视频加载失败'))
      })

      const duration = video.duration
      if (!duration || duration <= 0) {
        setLoading(false)
        return
      }

      // 计算缩略图宽度（假设 16:9 宽高比）和帧数
      const thumbWidth = Math.round(thumbnailHeight * (16 / 9))
      const frameCount = Math.max(8, Math.min(120, Math.round(containerWidth / thumbWidth)))

      canvas.width = thumbWidth
      canvas.height = thumbnailHeight

      const extracted: FrameData[] = []

      for (let i = 0; i < frameCount; i++) {
        if (abortRef.current) break

        const time = (i / frameCount) * duration

        // seek 到目标时间并等待 seeked 事件
        await new Promise<void>((resolve) => {
          const onSeeked = () => {
            video.removeEventListener('seeked', onSeeked)
            resolve()
          }
          video.addEventListener('seeked', onSeeked)
          video.currentTime = time
        })

        if (abortRef.current) break

        ctx.drawImage(video, 0, 0, canvas.width, canvas.height)
        const dataUrl = canvas.toDataURL('image/jpeg', 0.6)

        extracted.push({ time, dataUrl })
        // 渐进式更新：每帧提取后立即反映到 UI
        setFrames([...extracted])
        setProgress((i + 1) / frameCount)
      }

      setLoading(false)
    }

    extractFrames().catch(() => {
      if (!abortRef.current) {
        setLoading(false)
      }
    })

    return () => {
      abortRef.current = true
      video.src = ''
      video.load()
    }
  }, [src, containerWidth, thumbnailHeight])

  return { frames, loading, progress }
}
