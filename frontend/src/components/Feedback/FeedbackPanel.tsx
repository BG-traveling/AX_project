import type { FeedbackResponse } from '../../types/typhoon'

interface Props {
  feedback: FeedbackResponse | null
  isLoading: boolean
}

export default function FeedbackPanel({ feedback, isLoading }: Props) {
  if (isLoading) {
    return (
      <div style={containerStyle}>
        <div style={{ textAlign: 'center', color: '#94a3b8', padding: 20 }}>
          <div style={{ fontSize: 24, marginBottom: 8 }}>🌀</div>
          AI 피드백 생성 중...
        </div>
      </div>
    )
  }

  if (!feedback) return null

  const { avg_distance_km, direction_bias } = feedback.error_summary
  const accuracy = avg_distance_km < 100 ? '매우 정확' : avg_distance_km < 300 ? '양호' : '보통'

  return (
    <div style={containerStyle}>
      <h3 style={{ margin: '0 0 12px', fontSize: 15, color: '#1e293b' }}>🤖 AI 피드백</h3>

      {/* 오차 요약 */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
        <StatBadge label="평균 오차" value={`${avg_distance_km} km`} color="#0ea5e9" />
        <StatBadge label="방향 편향" value={direction_bias} color="#a855f7" />
        <StatBadge label="정확도" value={accuracy} color="#22c55e" />
      </div>

      {/* 피드백 텍스트 */}
      <div style={{
        background: '#f8fafc', borderRadius: 10, padding: '12px 14px',
        fontSize: 13, color: '#334155', lineHeight: 1.6,
      }}>
        {feedback.feedback}
      </div>
    </div>
  )
}

function StatBadge({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ flex: 1, background: '#f1f5f9', borderRadius: 8, padding: '8px 10px', textAlign: 'center' }}>
      <div style={{ fontSize: 11, color: '#94a3b8', marginBottom: 4 }}>{label}</div>
      <div style={{ fontSize: 13, fontWeight: 700, color }}>{value}</div>
    </div>
  )
}

const containerStyle: React.CSSProperties = {
  background: '#fff', borderRadius: 12, padding: 16,
  border: '1px solid #e2e8f0', boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
}
