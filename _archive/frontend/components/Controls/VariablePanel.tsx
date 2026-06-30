import type { UserVariables } from '../../types/typhoon'

interface Props {
  variables: UserVariables
  onChange: (v: UserVariables) => void
  onReset: () => void
}

export const DEFAULT_VARIABLES: UserVariables = { pressure: 980, temperature: 29 }

export default function VariablePanel({ variables, onChange, onReset }: Props) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
          <label style={labelStyle}>중심기압</label>
          <span style={valueStyle}>{variables.pressure} hPa</span>
        </div>
        <input
          type="range" min={850} max={1010} step={5}
          value={variables.pressure}
          onChange={e => onChange({ ...variables, pressure: Number(e.target.value) })}
          style={{ width: '100%' }}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#94a3b8' }}>
          <span>850 hPa (강)</span><span>1010 hPa (약)</span>
        </div>
      </div>

      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
          <label style={labelStyle}>해수면 온도</label>
          <span style={valueStyle}>{variables.temperature} °C</span>
        </div>
        <input
          type="range" min={20} max={35} step={1}
          value={variables.temperature}
          onChange={e => onChange({ ...variables, temperature: Number(e.target.value) })}
          style={{ width: '100%' }}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#94a3b8' }}>
          <span>20°C (약화)</span><span>35°C (강화)</span>
        </div>
      </div>

      <button onClick={onReset} style={resetBtnStyle}>변수 초기화</button>
    </div>
  )
}

const labelStyle: React.CSSProperties = { fontSize: 13, fontWeight: 600, color: '#475569' }
const valueStyle: React.CSSProperties = { fontSize: 14, fontWeight: 700, color: '#0ea5e9' }
const resetBtnStyle: React.CSSProperties = {
  padding: '6px 0', borderRadius: 8, border: '1px solid #e2e8f0',
  background: '#f8fafc', cursor: 'pointer', fontSize: 13, color: '#64748b',
}
