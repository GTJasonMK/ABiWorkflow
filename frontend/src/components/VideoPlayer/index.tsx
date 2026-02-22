export default function VideoPlayer({ src }: { src: string | null }) {
  if (!src) {
    return (
      <div className="np-video-box">
        暂无视频
      </div>
    )
  }

  return (
    <video
      src={src}
      controls
      className="np-video-player"
    />
  )
}
