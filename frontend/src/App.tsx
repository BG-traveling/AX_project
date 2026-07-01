import { useState, useEffect, useRef } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import TyphoonMap from './components/Map/TyphoonMap'
import { postPredict, postPredictCompare } from './api/typhoonApi'
import type { PredictedPoint, AnalogTyphoon, CompareModelTrack } from './types/typhoon'
import { INTENSITY_COLOR } from './types/typhoon'
import { useYears, useTyphoonList, useTyphoonDetail } from './hooks/useTyphoonData'

type Phase = 'pick' | 'config' | 'result'

const DEFAULT_PRESSURE = 960
const DEFAULT_SST      = 29
const DEFAULT_DIAMETER = 400

function pressureToWind1min(p: number): number {
  if (p >= 1010) return 0
  return Math.round(Math.min(85, Math.pow(Math.max(0, 1010 - p), 0.644) * 3.92))
}

const METHOD_LABEL: Record<string, { label: string; color: string }> = {
  lstm:            { label: '🧠 LSTM 딥러닝',      color: '#dc2626' },
  ml:              { label: '🤖 GBM 머신러닝',      color: '#7c3aed' },
  analog_blending: { label: '📊 유사 태풍 블렌딩', color: '#0891b2' },
  physics:         { label: '⚙️ 물리 모델',         color: '#65a30d' },
}

export default function App() {
  const [phase,            setPhase]            = useState<Phase>('pick')
  const [startPoint,       setStartPoint]       = useState<{ lat: number; lng: number } | null>(null)
  const [pressure,         setPressure]         = useState(DEFAULT_PRESSURE)
  const [sst,              setSst]              = useState(DEFAULT_SST)
  const [wind1min,         setWind1min]         = useState(pressureToWind1min(DEFAULT_PRESSURE))
  const [wind10min,        setWind10min]        = useState(Math.round(pressureToWind1min(DEFAULT_PRESSURE) * 0.88))
  const [diameter,         setDiameter]         = useState(DEFAULT_DIAMETER)
  const [loading,          setLoading]          = useState(false)
  const [predictedTrack,   setPredictedTrack]   = useState<PredictedPoint[]>([])
  const [analogs,          setAnalogs]          = useState<AnalogTyphoon[]>([])
  const [explanation,      setExplanation]      = useState('')
  const [predictionMethod, setPredictionMethod] = useState<string>('analog_blending')
  const [showAnalogs,      setShowAnalogs]      = useState(true)
  const [mobileOpen,       setMobileOpen]       = useState(false)

  // ── P2-1: 과거 태풍 검색 ───────────────────────────────
  const [selectedYear,     setSelectedYear]     = useState<number | null>(null)
  const [selectedTyphoon,  setSelectedTyphoon]  = useState<string | null>(null)
  const { years }                               = useYears()
  const { list: typhoonList }                   = useTyphoonList(selectedYear)
  const { detail: historicalDetail }            = useTyphoonDetail(selectedTyphoon)

  // ── P2-2: 다크모드 ────────────────────────────────────
  const [darkMode,         setDarkMode]         = useState(false)

  // ── P2-3: 모델 비교 ───────────────────────────────────
  const [compareMode,      setCompareMode]      = useState(false)
  const [compareTracks,    setCompareTracks]    = useState<CompareModelTrack[]>([])
  const [compareLoading,   setCompareLoading]   = useState(false)

  // ── P2-4: SST 히트맵 ──────────────────────────────────
  const [sstVisible,       setSstVisible]       = useState(false)

  // ── P1: 타임라인 슬라이더 상태 ─────────────────────────
  const [timelineIdx,  setTimelineIdx]  = useState(0)
  const [isPlaying,    setIsPlaying]    = useState(false)
  const [coneVisible,  setConeVisible]  = useState(true)
  const playIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // 예측 결과가 새로 오면 자동 재생 시작
  useEffect(() => {
    if (predictedTrack.length === 0) return
    setTimelineIdx(0)
    setIsPlaying(true)
  }, [predictedTrack])

  // 재생 중일 때 인터벌 실행
  useEffect(() => {
    if (playIntervalRef.current) clearInterval(playIntervalRef.current)
    if (!isPlaying || predictedTrack.length === 0) return

    playIntervalRef.current = setInterval(() => {
      setTimelineIdx(prev => {
        if (prev >= predictedTrack.length - 1) {
          setIsPlaying(false)
          clearInterval(playIntervalRef.current!)
          return prev
        }
        return prev + 1
      })
    }, 120)

    return () => { if (playIntervalRef.current) clearInterval(playIntervalRef.current) }
  }, [isPlaying, predictedTrack])

  useEffect(() => {
    const w1 = pressureToWind1min(pressure)
    setWind1min(w1)
    setWind10min(Math.round(w1 * 0.88))
  }, [pressure])

  // 모바일 패널 phase 자동 연동
  useEffect(() => {
    if (phase === 'config') setMobileOpen(true)   // 조건 설정 시 패널 열기
    if (phase === 'result') setMobileOpen(false)  // 결과 확인 시 지도 전체 표시
  }, [phase])

  function handleMapClick(lat: number, lng: number) {
    if (phase === 'pick') { setStartPoint({ lat, lng }); setPhase('config') }
  }

  function handleReset() {
    setPhase('pick'); setStartPoint(null)
    setPressure(DEFAULT_PRESSURE); setSst(DEFAULT_SST)
    setWind1min(pressureToWind1min(DEFAULT_PRESSURE))
    setWind10min(Math.round(pressureToWind1min(DEFAULT_PRESSURE) * 0.88))
    setDiameter(DEFAULT_DIAMETER)
    setPredictedTrack([]); setAnalogs([]); setExplanation('')
    setPredictionMethod('analog_blending')
    setTimelineIdx(0); setIsPlaying(false)
    setCompareMode(false); setCompareTracks([])
  }

  async function handleCompare() {
    if (!startPoint) return
    setCompareLoading(true)
    try {
      const month = new Date().getMonth() + 1
      const result = await postPredictCompare({
        start_lat: startPoint.lat, start_lng: startPoint.lng,
        pressure, sst, month,
        wind_1min_ms:  wind1min  > 0 ? wind1min  : undefined,
        wind_10min_ms: wind10min > 0 ? wind10min : undefined,
        diameter_km:   diameter  > 0 ? diameter  : undefined,
      })
      setCompareTracks(result.tracks)
      setCompareMode(true)
    } catch (e) {
      alert('비교 예측 실패: ' + (e as Error).message)
    } finally {
      setCompareLoading(false)
    }
  }

  async function handlePredict() {
    if (!startPoint) return
    setLoading(true)
    try {
      const month = new Date().getMonth() + 1
      const result = await postPredict({
        start_lat:     startPoint.lat,
        start_lng:     startPoint.lng,
        pressure, sst, month,
        wind_1min_ms:  wind1min  > 0 ? wind1min  : undefined,
        wind_10min_ms: wind10min > 0 ? wind10min : undefined,
        diameter_km:   diameter  > 0 ? diameter  : undefined,
      })
      setPredictedTrack(result.predicted_track)
      setAnalogs(result.analogs)
      setExplanation(result.ai_explanation)
      setPredictionMethod(result.prediction_method ?? 'analog_blending')
      setPhase('result')
    } catch (e) {
      alert('예측 실패: ' + (e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const lastPoint = predictedTrack[predictedTrack.length - 1]
  const peakPoint = predictedTrack.length
    ? predictedTrack.reduce((a, b) => b.wind_ms > a.wind_ms ? b : a, predictedTrack[0])
    : null
  const currentPoint = predictedTrack[timelineIdx]

  const intensityLabel: Record<string, string> = {
    TD: '열대저압부', TS: '열대폭풍', TY: '태풍', STY: '강한태풍',
  }
  function pressureToIntensity(p: number): 'TD' | 'TS' | 'TY' | 'STY' {
    if (p > 997) return 'TD'
    if (p > 979) return 'TS'
    if (p > 945) return 'TY'
    return 'STY'
  }

  const panelLabel = phase === 'result'
    ? '📊 결과 보기'
    : phase === 'config'
    ? '⚙️ 조건 설정'
    : '패널 열기'

  return (
    <div className={`app-root${darkMode ? ' dark' : ''}`}>

      {/* ── 사이드바 ── */}
      <aside className={`sidebar${mobileOpen ? '' : ' panel-collapsed'}`}>

        {/* 패널 헤더 — 로고 + 모바일 토글 버튼 (항상 노출) */}
        <div className="mobile-panel-header">
          <div style={logoStyle}>🌀 TyphoonPath</div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <button
              onClick={() => setDarkMode(d => !d)}
              style={{ background: 'none', border: 'none', fontSize: 16, cursor: 'pointer', padding: '2px 4px', lineHeight: 1 }}
              title={darkMode ? '라이트모드' : '다크모드'}
            >
              {darkMode ? '☀️' : '🌙'}
            </button>
            <button
              className="mobile-panel-toggle"
              onClick={() => setMobileOpen(o => !o)}
            >
              {mobileOpen ? '▼ 닫기' : `▲ ${panelLabel}`}
            </button>
          </div>
        </div>

        <StepIndicator phase={phase} />

        {/* STEP 1 */}
        <Section>
          <StepLabel step={1} label="시작점 설정" active={phase === 'pick'} done={phase !== 'pick'} />
          {phase === 'pick' ? (
            <div style={hintBox('#eff6ff', '#1d4ed8', '#bfdbfe')}>
              🗺️ 지도를 클릭해 태풍 발생 위치를 정해주세요
            </div>
          ) : (
            <div style={{ fontSize: 13, color: '#475569', background: '#f8fafc', borderRadius: 8, padding: '8px 10px' }}>
              📍 {startPoint?.lat.toFixed(2)}°N, {startPoint?.lng.toFixed(2)}°E
              {phase !== 'result' && (
                <button onClick={handleReset} style={{ marginLeft: 8, fontSize: 11, color: '#94a3b8', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}>
                  변경
                </button>
              )}
            </div>
          )}
        </Section>

        {/* STEP 2 */}
        <Section disabled={phase === 'pick'}>
          <StepLabel step={2} label="기상 조건 설정" active={phase === 'config'} done={phase === 'result'} />
          <div>
            <SliderRow label="중심기압" value={pressure} unit="hPa" min={850} max={1010} step={5}
              onChange={setPressure} disabled={phase !== 'config'}
              leftLabel="850 (강)" rightLabel="1010 (약)"
              valueColor={pressure < 920 ? '#ef4444' : pressure < 960 ? '#fb923c' : '#0ea5e9'} />
            <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2, marginBottom: 10 }}>
              예상 강도: <b style={{ color: INTENSITY_COLOR[pressureToIntensity(pressure)] }}>{intensityLabel[pressureToIntensity(pressure)]}</b>
            </div>
            <SliderRow label="해수면 온도" value={sst} unit="°C" min={20} max={35} step={1}
              onChange={setSst} disabled={phase !== 'config'}
              leftLabel="20°C (약화)" rightLabel="35°C (강화)"
              valueColor={sst >= 30 ? '#ef4444' : sst >= 27 ? '#fb923c' : '#0ea5e9'} />
            <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2, marginBottom: 10 }}>
              {sst >= 28 ? '⚡ 강화 가능 구역' : sst >= 26 ? '🔵 유지 구역' : '❄️ 약화 구역'}
            </div>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b', margin: '6px 0 4px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              상세 기상 조건 (선택)
            </div>
            <SliderRow label="1분 풍속" value={wind1min} unit="m/s" min={0} max={85} step={1}
              onChange={setWind1min} disabled={phase !== 'config'}
              leftLabel="0" rightLabel="85"
              valueColor={wind1min >= 50 ? '#ef4444' : wind1min >= 33 ? '#fb923c' : '#0ea5e9'} />
            <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2, marginBottom: 8 }}>미국 NHC 기준 · 기압에서 자동 추정</div>
            <SliderRow label="10분 풍속" value={wind10min} unit="m/s" min={0} max={75} step={1}
              onChange={setWind10min} disabled={phase !== 'config'}
              leftLabel="0" rightLabel="75"
              valueColor={wind10min >= 44 ? '#ef4444' : wind10min >= 29 ? '#fb923c' : '#0ea5e9'} />
            <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2, marginBottom: 8 }}>WMO·KMA 기준 · 1분 풍속의 약 88%</div>
            <SliderRow label="최대직경" value={diameter} unit="km" min={100} max={2000} step={50}
              onChange={setDiameter} disabled={phase !== 'config'}
              leftLabel="100" rightLabel="2000"
              valueColor={diameter >= 1200 ? '#ef4444' : diameter >= 600 ? '#fb923c' : '#0ea5e9'} />
            <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 2 }}>
              {diameter >= 1200 ? '🔴 초대형' : diameter >= 600 ? '🟠 대형' : diameter >= 300 ? '🔵 중형' : '⚪ 소형'} 태풍
            </div>
          </div>
          <button onClick={handlePredict} disabled={phase !== 'config' || loading}
            style={{ ...btnStyle, background: '#2563eb', color: '#fff', marginTop: 8 }}>
            {loading ? '🔄 경로 예측 중...' : '🌀 경로 예측하기'}
          </button>
        </Section>

        {/* STEP 3 결과 */}
        {phase === 'result' && lastPoint && peakPoint && (
          <Section>
            <StepLabel step={3} label="예측 결과" active={true} done={false} />
            {(() => {
              const m = METHOD_LABEL[predictionMethod] ?? METHOD_LABEL['analog_blending']
              return (
                <div style={{ fontSize: 11, fontWeight: 700, color: m.color, background: m.color + '18', borderRadius: 6, padding: '3px 8px', display: 'inline-block', marginBottom: 6 }}>
                  {m.label}
                </div>
              )
            })()}
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 8 }}>
              <Badge label="지속시간" value={`${lastPoint.hour}h (${(lastPoint.hour / 24).toFixed(1)}일)`} color="#8b5cf6" />
              <Badge label="최종강도" value={lastPoint.intensity} color={INTENSITY_COLOR[lastPoint.intensity]} />
              <Badge label="최종기압" value={`${lastPoint.pressure.toFixed(0)} hPa`} color="#475569" />
              <Badge label="최종풍속" value={`${lastPoint.wind_ms.toFixed(0)} m/s`} color="#0ea5e9" />
            </div>

            {/* 강도 타임라인 바 */}
            <div style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b', marginBottom: 4 }}>강도 변화 타임라인</div>
              <div style={{ display: 'flex', height: 18, borderRadius: 4, overflow: 'hidden', gap: 1 }}>
                {predictedTrack.filter((_, i) => i % 2 === 0).map((p, i) => (
                  <div key={i} title={`+${p.hour}h: ${p.intensity} ${p.wind_ms.toFixed(0)}m/s`}
                    style={{ flex: 1, background: INTENSITY_COLOR[p.intensity], minWidth: 2 }} />
                ))}
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#94a3b8', marginTop: 2 }}>
                <span>+0h</span><span>+{Math.round(lastPoint.hour / 2)}h</span><span>+{lastPoint.hour}h</span>
              </div>
            </div>

            {/* 최대 강도 */}
            <div style={{ background: '#fef3c7', border: '1px solid #fcd34d', borderRadius: 6, padding: '5px 8px', fontSize: 11, marginBottom: 8 }}>
              ⚡ 최대 강도: <b style={{ color: '#92400e' }}>+{peakPoint.hour}h</b>&nbsp;—&nbsp;
              <span style={{ color: INTENSITY_COLOR[peakPoint.intensity], fontWeight: 700 }}>{peakPoint.intensity}</span>&nbsp;
              {peakPoint.wind_ms.toFixed(0)} m/s / {peakPoint.pressure.toFixed(0)} hPa
            </div>

            {/* 원뿔 토글 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <input type="checkbox" id="showCone" checked={coneVisible} onChange={e => setConeVisible(e.target.checked)} />
              <label htmlFor="showCone" style={{ fontSize: 12, color: '#475569', cursor: 'pointer' }}>
                불확실성 원뿔 표시
              </label>
            </div>

            {/* 유사 태풍 토글 */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <input type="checkbox" id="showAnalogs" checked={showAnalogs} onChange={e => setShowAnalogs(e.target.checked)} />
              <label htmlFor="showAnalogs" style={{ fontSize: 12, color: '#475569', cursor: 'pointer' }}>
                유사 태풍 경로 표시 ({analogs.length}개)
              </label>
            </div>
            {showAnalogs && analogs.map((a, i) => (
              <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, marginBottom: 2 }}>
                <div style={{ width: 12, height: 3, background: ['#f59e0b', '#a855f7', '#06b6d4'][i], borderRadius: 2 }} />
                <span style={{ fontWeight: 600 }}>{a.name_en} ({a.year})</span>
                <span style={{ color: '#94a3b8' }}>유사도 {Math.round(a.similarity * 100)}%</span>
              </div>
            ))}

            <button onClick={handleReset} style={{ ...btnStyle, background: '#f1f5f9', color: '#475569', border: '1px solid #e2e8f0', marginTop: 8 }}>
              🔄 다시 예측하기
            </button>
          </Section>
        )}

        {/* ── P2-1: 과거 태풍 검색 ── */}
        <Section>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6, color: '#22c55e' }}>📚 과거 태풍 검색</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <select
              value={selectedYear ?? ''}
              onChange={e => { setSelectedYear(e.target.value ? Number(e.target.value) : null); setSelectedTyphoon(null) }}
              style={{ fontSize: 12, padding: '4px 6px', borderRadius: 6, border: '1px solid #e2e8f0', background: darkMode ? '#0f172a' : '#fff', color: darkMode ? '#e2e8f0' : '#1e293b' }}
            >
              <option value="">— 연도 선택 —</option>
              {[...years].sort((a, b) => b - a).map(y => (
                <option key={y} value={y}>{y}년</option>
              ))}
            </select>
            {selectedYear && (
              <select
                value={selectedTyphoon ?? ''}
                onChange={e => setSelectedTyphoon(e.target.value || null)}
                style={{ fontSize: 12, padding: '4px 6px', borderRadius: 6, border: '1px solid #e2e8f0', background: darkMode ? '#0f172a' : '#fff', color: darkMode ? '#e2e8f0' : '#1e293b' }}
              >
                <option value="">— 태풍 선택 —</option>
                {typhoonList.map(t => (
                  <option key={t.id} value={t.id}>{t.name_en} (No.{t.season_no})</option>
                ))}
              </select>
            )}
            {historicalDetail && (
              <div style={{ fontSize: 11, background: '#f0fdf4', border: '1px solid #86efac', borderRadius: 6, padding: '5px 8px', color: '#15803d' }}>
                📍 {historicalDetail.name_en} ({historicalDetail.year}) — 트랙 {historicalDetail.track.length}포인트
                <button
                  onClick={() => { setSelectedTyphoon(null); setSelectedYear(null) }}
                  style={{ marginLeft: 6, fontSize: 10, color: '#94a3b8', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline' }}
                >
                  제거
                </button>
              </div>
            )}
          </div>
        </Section>

        {/* ── P2-3/P2-4: 레이어 컨트롤 ── */}
        <Section>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6, color: '#7c3aed' }}>🗂️ 레이어 & 분석</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
            <input type="checkbox" id="sstToggle" checked={sstVisible} onChange={e => setSstVisible(e.target.checked)} />
            <label htmlFor="sstToggle" style={{ fontSize: 12, color: darkMode ? '#cbd5e1' : '#475569', cursor: 'pointer' }}>
              🌡️ SST 히트맵 (NASA GIBS)
            </label>
          </div>
          {phase === 'config' || phase === 'result' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <button
                onClick={handleCompare}
                disabled={!startPoint || compareLoading}
                style={{ ...btnStyle, background: compareMode ? '#7c3aed' : '#f3f0ff', color: compareMode ? '#fff' : '#7c3aed', border: '1px solid #a78bfa', fontSize: 12, padding: '7px 0' }}
              >
                {compareLoading ? '⏳ 비교 중...' : compareMode ? '📊 모델 비교 중 (켜짐)' : '📊 AI 모델 비교하기'}
              </button>
              {compareMode && (
                <>
                  {compareTracks.map(ct => {
                    const colors: Record<string, string> = { lstm: '#dc2626', ml: '#7c3aed', analog_blending: '#0891b2', physics: '#65a30d' }
                    const c = colors[ct.method] ?? '#6b7280'
                    return (
                      <div key={ct.method} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11 }}>
                        <div style={{ width: 20, height: 3, background: c, borderRadius: 2, flexShrink: 0 }} />
                        <span style={{ color: c, fontWeight: 700 }}>{ct.label}</span>
                        <span style={{ color: '#94a3b8' }}>{ct.track.length > 0 ? `${ct.track[ct.track.length-1].hour}h` : '—'}</span>
                      </div>
                    )
                  })}
                  <button
                    onClick={() => { setCompareMode(false); setCompareTracks([]) }}
                    style={{ fontSize: 11, color: '#94a3b8', background: 'none', border: 'none', cursor: 'pointer', textDecoration: 'underline', textAlign: 'left' }}
                  >
                    비교 모드 끄기
                  </button>
                </>
              )}
            </div>
          ) : (
            <div style={{ fontSize: 11, color: '#94a3b8' }}>시작점 설정 후 비교 가능합니다</div>
          )}
        </Section>

        {/* 강도 범례 */}
        <Section style={{ marginTop: 'auto' }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#94a3b8', textTransform: 'uppercase', marginBottom: 4 }}>강도 범례</div>
          {(['STY', 'TY', 'TS', 'TD'] as const).map(code => (
            <div key={code} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, marginBottom: 3 }}>
              <div style={{ width: 10, height: 10, borderRadius: '50%', background: INTENSITY_COLOR[code] }} />
              <span style={{ fontWeight: 600 }}>{code}</span>
              <span style={{ color: '#94a3b8' }}>{intensityLabel[code]}</span>
            </div>
          ))}
        </Section>
      </aside>

      {/* ── 메인 (지도 + 타임라인) ── */}
      <main className="main-area">
        <Banner phase={phase} loading={loading} />

        <div className="map-wrapper">
          <TyphoonMap
            startPoint={startPoint}
            predictedTrack={predictedTrack}
            analogs={analogs}
            isPickingStart={phase === 'pick'}
            onMapClick={handleMapClick}
            showAnalogs={showAnalogs}
            timelineIdx={timelineIdx}
            onTimelineIdxChange={setTimelineIdx}
            coneVisible={coneVisible}
            historicalTrack={historicalDetail?.track}
            darkMode={darkMode}
            compareTracks={compareMode ? compareTracks : []}
            sstVisible={sstVisible}
          />
          {/* 모바일: 패널 닫힌 상태에서 플로팅 버튼 */}
          {!mobileOpen && phase !== 'pick' && (
            <button
              className="mobile-fab"
              onClick={() => setMobileOpen(true)}
            >
              {phase === 'result' ? '📊 결과 보기' : '⚙️ 조건 설정'}
            </button>
          )}
        </div>

        {/* ── P1: 타임라인 슬라이더 (result 단계만 표시) ── */}
        {phase === 'result' && predictedTrack.length > 0 && (
          <div className="timeline-bar">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
              <button
                onClick={() => setIsPlaying(p => !p)}
                style={{
                  background: isPlaying ? '#ef4444' : '#2563eb',
                  color: '#fff', border: 'none', borderRadius: 6,
                  padding: '5px 14px', fontSize: 12, fontWeight: 700, cursor: 'pointer', flexShrink: 0,
                }}
              >
                   </button>

              {currentPoint && (
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  <span style={{ fontSize: 13, fontWeight: 800, color: '#1e293b' }}>
                    +{currentPoint.hour}h
                  </span>
                  <span style={{
                    fontSize: 11, fontWeight: 700, padding: '2px 7px', borderRadius: 5,
                    background: INTENSITY_COLOR[currentPoint.intensity] + '22',
                    color: INTENSITY_COLOR[currentPoint.intensity],
                  }}>
                    {currentPoint.intensity}
                  </span>
                  <span style={{ fontSize: 11, color: '#64748b' }}>
                    {currentPoint.pressure.toFixed(0)} hPa · {currentPoint.wind_ms.toFixed(0)} m/s
                  </span>
                  <span style={{ fontSize: 11, color: '#94a3b8' }}>
                    {currentPoint.lat.toFixed(2)}°N {currentPoint.lng.toFixed(2)}°E
                  </span>
                </div>
              )}

              <button
                onClick={() => { setTimelineIdx(predictedTrack.length - 1); setIsPlaying(false) }}
                style={{ marginLeft: 'auto', fontSize: 11, color: '#94a3b8', background: 'none', border: 'none', cursor: 'pointer', flexShrink: 0 }}
              >
                끝으로 ⏭
              </button>
            </div>

            <input
              type="range"
              min={0}
              max={predictedTrack.length - 1}
              value={timelineIdx}
              onChange={e => { setIsPlaying(false); setTimelineIdx(Number(e.target.value)) }}
              style={{ width: '100%', accentColor: '#2563eb', height: 4 }}
            />
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#94a3b8', marginTop: 2 }}>
              <span>+0h (현재)</span>
              <span>+{Math.round((predictedTrack[Math.floor(predictedTrack.length / 2)]?.hour ?? 0))}h</span>
              <span>+{lastPoint?.hour}h (종료)</span>
            </div>
          </div>
        )}

        {/* AI 해설 */}
        {explanation && (
          <div className="ai-panel">
            <div style={{ fontSize: 12, fontWeight: 700, color: '#0ea5e9', marginBottom: 6 }}>🤖 AI 기상 해설</div>
            <p style={{ fontSize: 13, color: '#334155', lineHeight: 1.7, margin: 0 }}>{explanation}</p>
          </div>
        )}
        {loading && (
          <div style={{ padding: '14px 20px', background: '#fff', borderTop: '1px solid #e2e8f0', color: '#94a3b8', fontSize: 13, textAlign: 'center' }}>
            🌀 경로 예측 중... 유사 태풍 탐색 중...
          </div>
        )}
      </main>
    </div>
  )
}

// ── 스타일 상수 ──────────────────────────────────────────
const logoStyle: CSSProperties = {
  fontSize: 18, fontWeight: 800, color: '#1e293b',
  letterSpacing: '-0.02em',
}
const btnStyle: CSSProperties = {
  width: '100%', padding: '10px 0', border: 'none',
  borderRadius: 8, fontWeight: 700, fontSize: 14, cursor: 'pointer',
}
function hintBox(bg: string, text: string, border: string): CSSProperties {
  return { background: bg, border: `1px solid ${border}`, borderRadius: 8, padding: '8px 10px', fontSize: 12, color: text, lineHeight: 1.5 }
}

// ── 서브 컴포넌트 ─────────────────────────────────────────
function StepIndicator({ phase }: { phase: Phase }) {
  const steps = ['pick', 'config', 'result']
  const idx   = steps.indexOf(phase)
  return (
    <div style={{ display: 'flex', alignItems: 'center', margin: '4px 0 10px' }}>
      {steps.map((s, i) => (
        <div key={s} style={{ display: 'flex', alignItems: 'center', flex: 1 }}>
          <div style={{
            width: 24, height: 24, borderRadius: '50%', flexShrink: 0,
            background: i < idx ? '#22c55e' : i === idx ? '#2563eb' : '#e2e8f0',
            color: i <= idx ? '#fff' : '#94a3b8',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 11, fontWeight: 700,
          }}>
            {i < idx ? '✓' : i + 1}
          </div>
          {i < steps.length - 1 && (
            <div style={{ flex: 1, height: 2, background: i < idx ? '#22c55e' : '#e2e8f0' }} />
          )}
        </div>
      ))}
    </div>
  )
}

function StepLabel({ step, label, active, done }: { step: number; label: string; active: boolean; done: boolean }) {
  return (
    <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6, color: active ? '#2563eb' : done ? '#22c55e' : '#94a3b8', display: 'flex', alignItems: 'center', gap: 4 }}>
      {done ? '✅' : active ? '▶' : '○'} STEP {step}: {label}
    </div>
  )
}

function SliderRow({ label, value, unit, min, max, step, onChange, disabled, leftLabel, rightLabel, valueColor }: {
  label: string; value: number; unit: string
  min: number; max: number; step: number
  onChange: (v: number) => void; disabled?: boolean
  leftLabel?: string; rightLabel?: string; valueColor?: string
}) {
  return (
    <div style={{ marginBottom: 4 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 }}>
        <span style={{ fontSize: 12, fontWeight: 600, color: '#475569' }}>{label}</span>
        <span style={{ fontSize: 14, fontWeight: 800, color: valueColor || '#1e293b' }}>
          {value} <span style={{ fontSize: 10, fontWeight: 400 }}>{unit}</span>
        </span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(Number(e.target.value))} disabled={disabled}
        style={{ width: '100%', accentColor: valueColor || '#2563eb' }} />
      {(leftLabel || rightLabel) && (
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, color: '#cbd5e1', marginTop: 1 }}>
          <span>{leftLabel}</span><span>{rightLabel}</span>
        </div>
      )}
    </div>
  )
}

function Badge({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div style={{ background: color + '1a', border: `1px solid ${color}44`, borderRadius: 6, padding: '3px 8px', fontSize: 11 }}>
      <span style={{ color: '#64748b' }}>{label} </span>
      <span style={{ fontWeight: 700, color }}>{value}</span>
    </div>
  )
}

function Banner({ phase, loading }: { phase: Phase; loading: boolean }) {
  const messages: Record<Phase, string> = {
    pick:   '🗺️ 지도에서 태풍 발생 위치를 클릭하세요',
    config: '⚙️ 기상 조건을 설정하고 경로를 예측하세요',
    result: '🌀 예측 완료! 타임라인으로 경로를 탐색하거나 포인트를 클릭하세요',
  }
  return (
    <div style={{
      padding: '10px 20px',
      background: phase === 'result' ? '#f0fdf4' : phase === 'config' ? '#eff6ff' : '#f8fafc',
      borderBottom: '1px solid #e2e8f0', fontSize: 13, fontWeight: 600,
      color: phase === 'result' ? '#15803d' : phase === 'config' ? '#1d4ed8' : '#64748b',
    }}>
      {loading ? '⏳ 예측 계산 중...' : messages[phase]}
    </div>
  )
}

function Section({ children, disabled, style }: { children: ReactNode; disabled?: boolean; style?: CSSProperties }) {
  return (
    <div style={{ padding: '8px 0', borderTop: '1px solid #f1f5f9', opacity: disabled ? 0.45 : 1, pointerEvents: disabled ? 'none' : undefined, ...style }}>
      {children}
    </div>
  )
}
