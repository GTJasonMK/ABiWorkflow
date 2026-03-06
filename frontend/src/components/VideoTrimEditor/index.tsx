import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Button, Space, App as AntdApp } from 'antd'
import { CaretRightOutlined, PauseOutlined, UndoOutlined, ScissorOutlined } from '@ant-design/icons'
import { useFrameExtractor } from '../../hooks/useFrameExtractor'
import { trimComposition } from '../../api/composition'
import { getApiErrorMessage } from '../../utils/error'

/** 分镜在时间线上的段落信息 */
interface SceneSegment {
  id: string
  title: string
  duration: number
  startTime: number
}

export interface TimelineSegment {
  id: string
  title: string
  duration_seconds: number
}

interface VideoTrimEditorProps {
  src: string | null
  compositionId: string | null
  duration: number
  segments?: TimelineSegment[]
  onTrimApplied?: (newCompositionId: string, newDuration: number, newMediaUrl: string | null) => void
}

/** 时间线缩放：每秒对应像素宽度（用于让不同时长体现真实长度差异） */
const TIMELINE_PX_PER_SEC = 18
/** 短视频下限，避免时间线过短导致手柄难以操作 */
const MIN_TIMELINE_WIDTH = 240
/** 超长视频上限，避免极端宽度导致渲染性能抖动 */
const MAX_TIMELINE_WIDTH = 12000

function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${String(m).padStart(2, '0')}:${s.toFixed(1).padStart(4, '0')}`
}

export default function VideoTrimEditor({ src, compositionId, duration, segments, onTrimApplied }: VideoTrimEditorProps) {
  const videoRef = useRef<HTMLVideoElement>(null)
  const wrapperRef = useRef<HTMLDivElement>(null)
  const timelineRef = useRef<HTMLDivElement>(null)
  const [playing, setPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [videoDuration, setVideoDuration] = useState(duration)
  const [trimStart, setTrimStart] = useState(0)
  const [trimEnd, setTrimEnd] = useState(0)
  const [trimming, setTrimming] = useState(false)
  const [wrapperWidth, setWrapperWidth] = useState(0)
  const { message } = AntdApp.useApp()

  const dragRef = useRef<'left' | 'right' | 'playhead' | null>(null)

  const effectiveDuration = videoDuration || duration || 0

  // 计算时间线内容宽度：按时长线性映射像素宽度，超出容器时出现横向滚动条
  const timelineWidth = useMemo(() => {
    if (effectiveDuration <= 0) {
      return MIN_TIMELINE_WIDTH
    }
    const naturalWidth = Math.ceil(effectiveDuration * TIMELINE_PX_PER_SEC)
    return Math.min(MAX_TIMELINE_WIDTH, Math.max(MIN_TIMELINE_WIDTH, naturalWidth))
  }, [effectiveDuration])

  const isScrollable = timelineWidth > wrapperWidth

  // 分镜段落计算
  const sceneSegments = useMemo<SceneSegment[]>(() => {
    if (!segments || segments.length === 0 || effectiveDuration <= 0) return []
    const timelineSegments: SceneSegment[] = []
    let cursor = 0
    for (const segment of segments) {
      const durationSeconds = Math.max(0, Number(segment.duration_seconds ?? 0))
      if (durationSeconds <= 0) continue
      timelineSegments.push({
        id: segment.id,
        title: segment.title,
        duration: durationSeconds,
        startTime: cursor,
      })
      cursor += durationSeconds
    }
    return timelineSegments
  }, [segments, effectiveDuration])

  const resetTrim = useCallback(() => {
    setTrimStart(0)
    setTrimEnd(effectiveDuration)
  }, [effectiveDuration])

  useEffect(() => {
    if (effectiveDuration > 0) {
      setTrimStart(0)
      setTrimEnd(effectiveDuration)
    }
  }, [effectiveDuration])

  // 监听外层可滚动容器宽度
  useEffect(() => {
    const el = wrapperRef.current
    if (!el) return
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setWrapperWidth(entry.contentRect.width)
      }
    })
    observer.observe(el)
    return () => observer.disconnect()
  }, [])

  // 帧提取使用实际时间线宽度（含溢出），确保长视频帧密度足够
  const { frames, loading: framesLoading } = useFrameExtractor({
    src,
    thumbnailHeight: 56,
    containerWidth: timelineWidth,
  })

  const handleLoadedMetadata = useCallback(() => {
    const video = videoRef.current
    if (video && video.duration && isFinite(video.duration)) {
      setVideoDuration(video.duration)
    }
  }, [])

  const handleTimeUpdate = useCallback(() => {
    const video = videoRef.current
    if (!video) return
    setCurrentTime(video.currentTime)
    if (video.currentTime >= trimEnd && !video.paused) {
      video.pause()
      setPlaying(false)
    }
  }, [trimEnd])

  const handleEnded = useCallback(() => {
    setPlaying(false)
  }, [])

  const togglePlay = useCallback(() => {
    const video = videoRef.current
    if (!video) return
    if (video.paused) {
      if (video.currentTime < trimStart || video.currentTime >= trimEnd) {
        video.currentTime = trimStart
      }
      video.play()
      setPlaying(true)
    } else {
      video.pause()
      setPlaying(false)
    }
  }, [trimStart, trimEnd])

  // 百分比定位（相对于内层时间线宽度）
  const timeToPercent = useCallback((time: number) => {
    if (effectiveDuration <= 0) return 0
    return (time / effectiveDuration) * 100
  }, [effectiveDuration])

  // 鼠标 clientX → 时间（getBoundingClientRect 已考虑滚动偏移）
  const pixelToTime = useCallback((clientX: number) => {
    const el = timelineRef.current
    if (!el || effectiveDuration <= 0) return 0
    const rect = el.getBoundingClientRect()
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width))
    return ratio * effectiveDuration
  }, [effectiveDuration])

  // 播放时自动滚动，保持播放头可见
  useEffect(() => {
    if (!playing || !isScrollable) return
    const wrapper = wrapperRef.current
    if (!wrapper || effectiveDuration <= 0) return
    const playheadPx = (currentTime / effectiveDuration) * timelineWidth
    const scrollLeft = wrapper.scrollLeft
    const visibleRight = scrollLeft + wrapperWidth
    const margin = 60
    if (playheadPx > visibleRight - margin) {
      wrapper.scrollLeft = playheadPx - margin
    } else if (playheadPx < scrollLeft + margin) {
      wrapper.scrollLeft = Math.max(0, playheadPx - wrapperWidth + margin)
    }
  }, [currentTime, playing, isScrollable, timelineWidth, wrapperWidth, effectiveDuration])

  // 拖拽手柄/播放头
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!dragRef.current) return
      e.preventDefault()
      const time = pixelToTime(e.clientX)

      if (dragRef.current === 'left') {
        const newStart = Math.max(0, Math.min(time, trimEnd - 0.5))
        setTrimStart(newStart)
        if (videoRef.current) videoRef.current.currentTime = newStart
      } else if (dragRef.current === 'right') {
        const newEnd = Math.min(effectiveDuration, Math.max(time, trimStart + 0.5))
        setTrimEnd(newEnd)
        if (videoRef.current) videoRef.current.currentTime = newEnd
      } else if (dragRef.current === 'playhead') {
        const clampedTime = Math.max(trimStart, Math.min(trimEnd, time))
        if (videoRef.current) videoRef.current.currentTime = clampedTime
        setCurrentTime(clampedTime)
      }
    }

    const handleMouseUp = () => {
      dragRef.current = null
    }

    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseup', handleMouseUp)
    return () => {
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseup', handleMouseUp)
    }
  }, [trimStart, trimEnd, effectiveDuration, pixelToTime])

  const handleHandleMouseDown = useCallback((type: 'left' | 'right') => (e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dragRef.current = type
  }, [])

  const handleTimelineClick = useCallback((e: React.MouseEvent) => {
    if (dragRef.current) return
    const time = pixelToTime(e.clientX)
    const clampedTime = Math.max(trimStart, Math.min(trimEnd, time))
    if (videoRef.current) videoRef.current.currentTime = clampedTime
    setCurrentTime(clampedTime)
  }, [pixelToTime, trimStart, trimEnd])

  const handleTimelineMouseDown = useCallback((e: React.MouseEvent) => {
    const time = pixelToTime(e.clientX)
    if (time >= trimStart && time <= trimEnd) {
      dragRef.current = 'playhead'
      const clampedTime = Math.max(trimStart, Math.min(trimEnd, time))
      if (videoRef.current) videoRef.current.currentTime = clampedTime
      setCurrentTime(clampedTime)
    }
  }, [pixelToTime, trimStart, trimEnd])

  const handleApplyTrim = useCallback(async () => {
    if (!compositionId) return
    if (Math.abs(trimStart) < 0.01 && Math.abs(trimEnd - effectiveDuration) < 0.01) {
      message.info('选区为全长，无需裁剪')
      return
    }
    setTrimming(true)
    try {
      const result = await trimComposition(compositionId, trimStart, trimEnd)
      message.success('裁剪完成')
      onTrimApplied?.(result.composition_id, result.duration_seconds, result.media_url)
    } catch (error) {
      message.error(getApiErrorMessage(error, '裁剪失败'))
    } finally {
      setTrimming(false)
    }
  }, [compositionId, trimStart, trimEnd, effectiveDuration, message, onTrimApplied])

  const selectionDuration = useMemo(() => Math.max(0, trimEnd - trimStart), [trimStart, trimEnd])
  const isTrimmed = Math.abs(trimStart) >= 0.01 || Math.abs(trimEnd - effectiveDuration) >= 0.01

  if (!src) {
    return (
      <div className="np-trim-editor">
        <div className="np-trim-editor__preview">
          <div className="np-trim-editor__preview-empty">暂无视频</div>
        </div>
      </div>
    )
  }

  return (
    <div className="np-trim-editor">
      {/* 视频预览区 */}
      <div className="np-trim-editor__preview">
        <video
          ref={videoRef}
          src={src}
          onLoadedMetadata={handleLoadedMetadata}
          onTimeUpdate={handleTimeUpdate}
          onEnded={handleEnded}
          style={{ width: '100%', maxHeight: 480, display: 'block' }}
        />
      </div>

      {/* 播放控件栏 */}
      <div className="np-trim-editor__controls">
        <button
          className="np-trim-editor__play-btn"
          onClick={togglePlay}
          type="button"
        >
          {playing ? <PauseOutlined /> : <CaretRightOutlined />}
        </button>
        <span className="np-time-display">
          {formatTime(currentTime)} / {formatTime(effectiveDuration)}
          {isTrimmed && (
            <span className="np-time-display__selection">
              选区 {formatTime(selectionDuration)}
            </span>
          )}
        </span>
      </div>

      {/* 可滚动的时间线外层容器 */}
      <div ref={wrapperRef} className="np-trim-editor__timeline-wrapper">
        {/* 内层时间线（宽度随视频时长伸展） */}
        <div
          ref={timelineRef}
          className="np-trim-editor__timeline"
          style={{ width: `${timelineWidth}px` }}
          onClick={handleTimelineClick}
          onMouseDown={handleTimelineMouseDown}
        >
          {/* 帧缩略图 */}
          <div className="np-film-strip">
            {framesLoading && frames.length === 0
              ? Array.from({ length: 20 }).map((_, i) => (
                  <div key={i} className="np-film-strip__placeholder" />
                ))
              : frames.map((frame, i) => (
                  <img
                    key={i}
                    src={frame.dataUrl}
                    className="np-film-strip__frame"
                    alt=""
                    draggable={false}
                  />
                ))}
          </div>

          {/* 裁剪遮罩 + 选区 + 手柄 */}
          {effectiveDuration > 0 && (
            <div className="np-trim-overlay">
              <div
                className="np-trim-overlay__mask-left"
                style={{ width: `${timeToPercent(trimStart)}%` }}
              />
              <div
                className="np-trim-overlay__mask-right"
                style={{ width: `${100 - timeToPercent(trimEnd)}%` }}
              />
              <div
                className="np-trim-selection"
                style={{
                  left: `calc(${timeToPercent(trimStart)}% + 16px)`,
                  right: `calc(${100 - timeToPercent(trimEnd)}% + 16px)`,
                }}
              />
              <div
                className="np-trim-handle np-trim-handle--left"
                style={{ left: `${timeToPercent(trimStart)}%` }}
                onMouseDown={handleHandleMouseDown('left')}
              />
              <div
                className="np-trim-handle np-trim-handle--right"
                style={{ right: `${100 - timeToPercent(trimEnd)}%` }}
                onMouseDown={handleHandleMouseDown('right')}
              />
            </div>
          )}

          {/* 分镜边界标记 */}
          {effectiveDuration > 0 && sceneSegments.length > 1 && sceneSegments.map((segment, idx) => (
            <div key={segment.id} className="np-scene-marker">
              {idx > 0 && (
                <div
                  className="np-scene-marker__divider"
                  style={{ left: `${timeToPercent(segment.startTime)}%` }}
                />
              )}
              <div
                className="np-scene-marker__label"
                style={{
                  left: `${timeToPercent(segment.startTime)}%`,
                  width: `${timeToPercent(segment.duration)}%`,
                }}
                title={`${idx + 1}. ${segment.title} (${segment.duration.toFixed(1)}s)`}
              >
                <span className="np-scene-marker__text">
                  {idx + 1}. {segment.title}
                </span>
              </div>
            </div>
          ))}

          {/* 播放头 */}
          {effectiveDuration > 0 && (
            <div
              className="np-playhead"
              style={{ left: `${timeToPercent(currentTime)}%` }}
            />
          )}
        </div>
      </div>

      {/* 操作栏 */}
      <div className="np-trim-editor__actions">
        <Space>
          <Button
            icon={<UndoOutlined />}
            onClick={resetTrim}
            disabled={!isTrimmed || trimming}
          >
            重置
          </Button>
          <Button
            type="primary"
            icon={<ScissorOutlined />}
            onClick={handleApplyTrim}
            loading={trimming}
            disabled={!isTrimmed || !compositionId || trimming}
          >
            应用裁剪
          </Button>
        </Space>
      </div>
    </div>
  )
}
