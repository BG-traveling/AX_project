export type Intensity = 'TD' | 'TS' | 'TY' | 'STY'

export interface TrackPoint {
  dt: string
  lat: number
  lng: number
  wind_ms: number
  pressure: number | null
  intensity: Intensity
}

export interface TyphoonSummary {
  id: string
  name_en: string
  year: number
  season_no: number
  track_count: number
}

export interface TyphoonDetail extends TyphoonSummary {
  track: TrackPoint[]
}

export interface UserVariables {
  pressure: number
  temperature: number
}

export interface FeedbackResponse {
  actual_track: { lat: number; lng: number }[]
  feedback: string
  error_summary: {
    avg_distance_km: number
    direction_bias: string
  }
}

// 강도별 색상
export const INTENSITY_COLOR: Record<Intensity, string> = {
  TD:  '#94a3b8',
  TS:  '#34d399',
  TY:  '#fb923c',
  STY: '#ef4444',
}

// ── 예측 관련 타입 ──────────────────────────────
export interface PredictedPoint {
  lat: number
  lng: number
  pressure: number
  wind_ms: number
  intensity: Intensity
  hour: number
}

export interface AnalogTyphoon {
  id: string
  name_en: string
  year: number
  similarity: number
  track: { lat: number; lng: number }[]
}

export interface PredictRequest {
  start_lat: number
  start_lng: number
  pressure: number
  sst: number
  month: number
  wind_1min_ms?: number
  wind_10min_ms?: number
  diameter_km?: number
}

export interface PredictResponse {
  predicted_track: PredictedPoint[]
  analogs: AnalogTyphoon[]
  ai_explanation: string
  prediction_method: 'ml' | 'analog_blending' | 'physics'
}
