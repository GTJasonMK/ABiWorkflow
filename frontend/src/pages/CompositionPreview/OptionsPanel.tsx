import { Form, Select, Switch, InputNumber } from 'antd'

type TransitionType = 'none' | 'crossfade' | 'fade_black'

export interface CompositionOptions {
  transition_type: TransitionType
  transition_duration: number
  include_subtitles: boolean
  include_tts: boolean
}

interface Props {
  options: CompositionOptions
  onChange: (opts: CompositionOptions) => void
}

export default function OptionsPanel({ options, onChange }: Props) {
  return (
    <Form layout="vertical" size="small">
      <Form.Item label="转场效果">
        <Select
          value={options.transition_type}
          onChange={(val) => onChange({ ...options, transition_type: val })}
          options={[
            { value: 'none', label: '无转场' },
            { value: 'crossfade', label: '交叉溶解' },
            { value: 'fade_black', label: '淡入黑场' },
          ]}
        />
      </Form.Item>
      <Form.Item label="转场时长（秒）">
        <InputNumber
          min={0}
          max={2.0}
          step={0.1}
          value={options.transition_duration}
          onChange={(val) => onChange({ ...options, transition_duration: val ?? 0.5 })}
          style={{ width: '100%' }}
        />
      </Form.Item>
      <Form.Item label="包含字幕">
        <Switch
          checked={options.include_subtitles}
          onChange={(val) => onChange({ ...options, include_subtitles: val })}
        />
      </Form.Item>
      <Form.Item label="包含配音">
        <Switch
          checked={options.include_tts}
          onChange={(val) => onChange({ ...options, include_tts: val })}
        />
      </Form.Item>
    </Form>
  )
}
