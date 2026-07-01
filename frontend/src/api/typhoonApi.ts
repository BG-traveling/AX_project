import type {
  TyphoonSummary, TyphoonDetail,
  FeedbackResponse, UserVariables,
  PredictResponse, PredictRequest,
} from '../types/typhoon'

// 개발: vite proxy(/api → localhost:8000)
// 프로덕션: VITE_API_BASE_URL=https://your-app.railway.app
const BASE = (import.meta.env.VITE_API_BASE_URL ?? '') + '/api'

export async function fetchYears(): Promise<number[]> {
  const res = await fetch(`${BASE}/typhoons/years`)
  if (!res.ok) throw new Error('연도 목록 조회 실패')
  return res.json()
}

export async function fetchTyphoons(year?: number, name?: string): Promise<TyphoonSummary[]> {
  const params = new URLSearchParams()
  if (year) params.set('year', String(year))
  if (name) params.set('name', name)
  const res = await fetch(`${BASE}/typhoons?${params}`)
  if (!res.ok) throw new Error('태풍 목록 조회 실패')
  return res.json()
}

export async function fetchTyphoonDetail(id: string): Promise<TyphoonDetail> {
  const res = await fetch(`${BASE}/typhoons/${encodeURIComponent(id)}`)
  if (!res.ok) throw new Error('태풍 상세 조회 실패')
  return res.json()
}

export async function postFeedback(
  typhoonId: string,
  userTrack: { lat: number; lng: number }[],
  userVariables: UserVariables,
): Promise<FeedbackResponse> {
  const res = await fetch(`${BASE}/feedback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      typhoon_id: typhoonId,
      user_track: userTrack,
      user_variables: userVariables,
    }),
  })
  if (!res.ok) throw new Error('피드백 생성 실패')
  return res.json()
}

export async function postPredict(req: PredictRequest): Promise<PredictResponse> {
  const body: Record<string, unknown> = {
    start_lat: req.start_lat,
    start_lng: req.start_lng,
    pressure:  req.pressure,
    sst:       req.sst,
    month:     req.month,
  }
  if (req.wind_1min_ms  != null && req.wind_1min_ms  > 0) body.wind_1min_ms  = req.wind_1min_ms
  if (req.wind_10min_ms != null && req.wind_10min_ms > 0) body.wind_10min_ms = req.wind_10min_ms
  if (req.diameter_km   != null && req.diameter_km   > 0) body.diameter_km   = req.diameter_km

  const res = await fetch(`${BASE}/predict`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error('예측 요청 실패')
  return res.json()
}
