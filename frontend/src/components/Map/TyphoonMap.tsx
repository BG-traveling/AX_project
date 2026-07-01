import { useEffect, useMemo } from 'react'
import { MapContainer, TileLayer, WMSTileLayer, Polyline, Polygon, CircleMarker, Tooltip, Marker, useMapEvents, Popup } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import type { PredictedPoint, AnalogTyphoon, TrackPoint, CompareModelTrack } from '../../types/typhoon'
import { INTENSITY_COLOR } from '../../types/typhoon'

// ── 아이콘 ──────────────────────────────────────────────────
const startIcon = L.divIcon({
  className: '',
  html: `<div style="
    width:36px;height:36px;background:#1d4ed8;border:3px solid #fff;
    border-radius:50%;box-shadow:0 0 0 3px #1d4ed8,0 3px 10px rgba(0,0,0,.4);
    display:flex;align-items:center;justify-content:center;font-size:16px;
  ">📍</div>`,
  iconSize: [36, 36], iconAnchor: [18, 18],
})

function makeTyphoonIcon(color: string) {
  return L.divIcon({
    className: '',
    html: `<div style="
      width:40px;height:40px;display:flex;align-items:center;justify-content:center;
      font-size:28px;
      filter:drop-shadow(0 0 6px ${color}) drop-shadow(0 0 12px ${color});
      animation:spin 2s linear infinite;
    ">🌀</div>
    <style>
      @keyframes spin { from{transform:rotate(0deg)} to{transform:rotate(360deg)} }
    </style>`,
    iconSize: [40, 40], iconAnchor: [20, 20],
  })
}

function makeTimeIcon(label: string, color: string) {
  return L.divIcon({
    className: '',
    html: `<div style="
      background:${color};color:#fff;border:2px solid #fff;border-radius:4px;
      padding:2px 5px;font-size:10px;font-weight:800;white-space:nowrap;
      box-shadow:0 1px 4px rgba(0,0,0,.3);transform:translate(-50%,-150%);
    ">${label}</div>`,
    iconSize: [0, 0], iconAnchor: [0, 0],
  })
}

const ANALOG_COLORS = ['#f59e0b', '#a855f7', '#06b6d4']

// ── 모델 비교 색상 ────────────────────────────────────────
const COMPARE_COLORS: Record<string, string> = {
  lstm:            '#dc2626',
  ml:              '#7c3aed',
  analog_blending: '#0891b2',
  physics:         '#65a30d',
}

// ── 불확실성 원뿔 계산 ────────────────────────────────────
function computeCone(track: PredictedPoint[]): [number, number][] {
  if (track.length < 2) return []

  const left: [number, number][] = []
  const right: [number, number][] = []

  track.forEach((p, i) => {
    const radiusKm = Math.max(30, 30 + (p.hour / 120) * 270)
    const cosLat = Math.cos((p.lat * Math.PI) / 180) || 0.01

    let dlat = 0, dlng = 0
    if (i < track.length - 1) {
      dlat = track[i + 1].lat - p.lat
      dlng = track[i + 1].lng - p.lng
    } else if (i > 0) {
      dlat = p.lat - track[i - 1].lat
      dlng = p.lng - track[i - 1].lng
    }
    const len = Math.sqrt(dlat * dlat + dlng * dlng) || 1

    const perpLat = -dlng / len
    const perpLng = dlat / len

    left.push([
      p.lat + perpLat * (radiusKm / 111.0),
      p.lng + perpLng * (radiusKm / (111.0 * cosLat)),
    ])
    right.push([
      p.lat - perpLat * (radiusKm / 111.0),
      p.lng - perpLng * (radiusKm / (111.0 * cosLat)),
    ])
  })

  return [...left, ...[...right].reverse()]
}

// ── Props ─────────────────────────────────────────────────
interface Props {
  startPoint: { lat: number; lng: number } | null
  predictedTrack: PredictedPoint[]
  analogs: AnalogTyphoon[]
  isPickingStart: boolean
  onMapClick: (lat: number, lng: number) => void
  showAnalogs: boolean
  timelineIdx: number
  onTimelineIdxChange: (idx: number) => void
  coneVisible: boolean
  // P2 features
  historicalTrack?: TrackPoint[]        // P2-1: 과거 태풍 경로
  darkMode?: boolean                     // P2-2: 다크모드 타일
  compareTracks?: CompareModelTrack[]    // P2-3: 모델 비교 경로
  sstVisible?: boolean                   // P2-4: SST 히트맵
}

function ClickHandler({ onMapClick, isPickingStart }: { onMapClick: Props['onMapClick']; isPickingStart: boolean }) {
  useMapEvents({ click(e) { if (isPickingStart) onMapClick(e.latlng.lat, e.latlng.lng) } })
  return null
}

export default function TyphoonMap({
  startPoint, predictedTrack, analogs, isPickingStart, onMapClick,
  showAnalogs, timelineIdx, onTimelineIdxChange, coneVisible,
  historicalTrack = [], darkMode = false, compareTracks = [], sstVisible = false,
}: Props) {
  useEffect(() => {
    if (predictedTrack.length > 0) onTimelineIdxChange(0)
  }, [predictedTrack])

  // P2-4: SST date (7일 전 — GIBS 데이터 지연 고려)
  const sstDate = useMemo(() => {
    const d = new Date()
    d.setDate(d.getDate() - 7)
    return d.toISOString().slice(0, 10)
  }, [])

  const visibleTrack = predictedTrack.slice(0, timelineIdx + 1)
  const isAnimating  = timelineIdx < predictedTrack.length - 1 && predictedTrack.length > 0
  const currentPoint = visibleTrack[visibleTrack.length - 1]

  // 강도별 구간
  const segments: { positions: [number, number][]; color: string }[] = []
  for (let i = 0; i < visibleTrack.length - 1; i++) {
    const p = visibleTrack[i]
    segments.push({
      positions: [[p.lat, p.lng], [visibleTrack[i + 1].lat, visibleTrack[i + 1].lng]],
      color: INTENSITY_COLOR[p.intensity],
    })
  }

  // 불확실성 원뿔
  const conePositions = coneVisible ? computeCone(visibleTrack) : []

  // P2-1: 과거 태풍 — 강도별 세그먼트
  const historicalSegments: { positions: [number, number][]; color: string }[] = []
  for (let i = 0; i < historicalTrack.length - 1; i++) {
    const p = historicalTrack[i]
    historicalSegments.push({
      positions: [[p.lat, p.lng], [historicalTrack[i + 1].lat, historicalTrack[i + 1].lng]],
      color: INTENSITY_COLOR[p.intensity as keyof typeof INTENSITY_COLOR] ?? '#94a3b8',
    })
  }

  // P2-2: 타일 레이어 URL
  const tileUrl = darkMode
    ? 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png'
    : 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
  const tileAttr = darkMode
    ? '&copy; <a href="https://carto.com/">CARTO</a>'
    : '&copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a>'

  return (
    <MapContainer
      center={[22, 135]}
      zoom={4}
      style={{ width: '100%', height: '100%', cursor: isPickingStart ? 'crosshair' : 'grab' }}
    >
      {/* P2-2: 다크/라이트 타일 전환 */}
      <TileLayer key={darkMode ? 'dark' : 'light'} url={tileUrl} attribution={tileAttr} />

      {/* P2-4: SST 히트맵 WMS 레이어 */}
      {sstVisible && (
        <WMSTileLayer
          key={`sst-${sstDate}`}
          url="https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi"
          layers="GHRSST_L4_MUR_Sea_Surface_Temperature"
          format="image/png"
          transparent={true}
          opacity={0.65}
          version="1.1.1"
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          params={{ TIME: sstDate } as any}
          attribution="NASA GIBS"
        />
      )}

      <ClickHandler onMapClick={onMapClick} isPickingStart={isPickingStart} />

      {/* ── P2-1: 과거 태풍 경로 (강도별 색상) ── */}
      {historicalSegments.map((seg, i) => (
        <Polyline
          key={`hist-seg-${i}`}
          positions={seg.positions}
          color={seg.color}
          weight={3}
          opacity={0.75}
          dashArray="8 4"
        />
      ))}
      {historicalTrack.length > 0 && historicalTrack.map((p, i) => {
        const isFirst = i === 0
        const isLast  = i === historicalTrack.length - 1
        const isDay   = i > 0 && i % 4 === 0   // 매 4포인트 = 약 24h (6h 간격 가정)
        if (!isFirst && !isLast && !isDay) return null
        return (
          <CircleMarker
            key={`hist-pt-${i}`}
            center={[p.lat, p.lng]}
            radius={isFirst || isLast ? 7 : 5}
            fillColor={INTENSITY_COLOR[p.intensity as keyof typeof INTENSITY_COLOR] ?? '#94a3b8'}
            color="#fff"
            weight={2}
            fillOpacity={0.9}
          >
            <Popup>
              <div style={{ fontSize: 12, lineHeight: 1.6 }}>
                <b>{isFirst ? '🌀 시작' : isLast ? '⭕ 소멸' : `⏱ ${p.dt?.slice(0, 16) ?? ''}`}</b><br />
                강도: <b style={{ color: INTENSITY_COLOR[p.intensity as keyof typeof INTENSITY_COLOR] }}>{p.intensity}</b><br />
                기압: {p.pressure ? `${p.pressure} hPa` : '—'}<br />
                풍속: {p.wind_ms?.toFixed(0)} m/s
              </div>
            </Popup>
          </CircleMarker>
        )
      })}

      {/* ── P2-3: 모델 비교 경로 ── */}
      {compareTracks.map((ct) => {
        const color = COMPARE_COLORS[ct.method] ?? '#6b7280'
        const positions: [number, number][] = ct.track.map(p => [p.lat, p.lng])
        return (
          <Polyline key={`cmp-${ct.method}`} positions={positions} color={color} weight={3} opacity={0.8} dashArray="10 4">
            <Tooltip sticky>
              <span style={{ fontSize: 12 }}>
                <b style={{ color }}>{ct.label}</b><br />
                포인트 {ct.track.length}개 / {ct.track[ct.track.length - 1]?.hour ?? 0}h
              </span>
            </Tooltip>
          </Polyline>
        )
      })}

      {/* ── 불확실성 원뿔 (Cone of Uncertainty) ── */}
      {conePositions.length >= 3 && (
        <Polygon
          positions={conePositions}
          pathOptions={{
            color: '#3b82f6',
            fillColor: '#3b82f6',
            fillOpacity: 0.12,
            weight: 1.5,
            opacity: 0.4,
            dashArray: '4 4',
          }}
        />
      )}

      {/* ── 유사 태풍 경로 ── */}
      {showAnalogs && analogs.map((analog, idx) => (
        <Polyline
          key={analog.id}
          positions={analog.track.map(p => [p.lat, p.lng])}
          color={ANALOG_COLORS[idx % ANALOG_COLORS.length]}
          weight={2} opacity={0.4} dashArray="6 4"
        >
          <Tooltip sticky>
            <span style={{ fontSize: 12 }}>
              <b>{analog.name_en} ({analog.year})</b><br />
              유사도 {Math.round(analog.similarity * 100)}%
            </span>
          </Tooltip>
        </Polyline>
      ))}

      {/* ── 예측 경로 — 강도별 색상 구간 ── */}
      {segments.map((seg, i) => (
        <Polyline key={`seg-${i}`} positions={seg.positions} color={seg.color} weight={4} opacity={0.9} />
      ))}

      {/* ── 경로 포인트 마커 ── */}
      {visibleTrack.map((p, i) => {
        if (isAnimating && i === visibleTrack.length - 1) return null
        const isDay   = p.hour % 24 === 0 && p.hour > 0
        const isFirst = i === 0
        const isLast  = !isAnimating && i === predictedTrack.length - 1
        const showLabel = isDay || isLast

        return (
          <CircleMarker
            key={`pred-${i}`}
            center={[p.lat, p.lng]}
            radius={isFirst ? 10 : isLast ? 8 : isDay ? 6 : 4}
            fillColor={INTENSITY_COLOR[p.intensity]}
            color="#fff"
            weight={isFirst || isLast || isDay ? 2 : 1}
            fillOpacity={1}
          >
            {showLabel && (
              <Tooltip permanent direction="top" offset={[0, -8]}>
                <span style={{ fontSize: 10, fontWeight: 700, color: INTENSITY_COLOR[p.intensity] }}>
                  {isLast ? `종료 ${p.hour}h` : `+${p.hour}h`}
                </span>
              </Tooltip>
            )}
            <Popup>
              <div style={{ fontSize: 12, lineHeight: 1.7, minWidth: 150 }}>
                <div style={{ fontWeight: 800, color: '#1e293b', marginBottom: 4 }}>
                  {isFirst ? '🌀 예측 시작' : isLast ? '⭕ 소멸' : `⏱ +${p.hour}시간`}
                </div>
                <table style={{ borderCollapse: 'collapse', width: '100%' }}>
                  <tbody>
                    <tr><td style={{ color: '#64748b', paddingRight: 8 }}>강도</td><td style={{ fontWeight: 700, color: INTENSITY_COLOR[p.intensity] }}>{p.intensity}</td></tr>
                    <tr><td style={{ color: '#64748b' }}>기압</td><td><b>{p.pressure.toFixed(0)}</b> hPa</td></tr>
                    <tr><td style={{ color: '#64748b' }}>풍속</td><td><b>{p.wind_ms.toFixed(1)}</b> m/s</td></tr>
                    <tr><td style={{ color: '#64748b' }}>위치</td><td>{p.lat.toFixed(2)}°N {p.lng.toFixed(2)}°E</td></tr>
                  </tbody>
                </table>
              </div>
            </Popup>
          </CircleMarker>
        )
      })}

      {/* ── 24h 시간 레이블 ── */}
      {visibleTrack
        .filter((p, i) => p.hour % 24 === 0 && p.hour > 0 && i < visibleTrack.length - 1)
        .map(p => (
          <Marker
            key={`lbl-${p.hour}`}
            position={[p.lat, p.lng]}
            icon={makeTimeIcon(`+${p.hour / 24}일`, INTENSITY_COLOR[p.intensity])}
            interactive={false}
          />
        ))}

      {/* ── 움직이는 태풍 아이콘 ── */}
      {isAnimating && currentPoint && (
        <Marker
          key={`typhoon-moving-${timelineIdx}`}
          position={[currentPoint.lat, currentPoint.lng]}
          icon={makeTyphoonIcon(INTENSITY_COLOR[currentPoint.intensity])}
          interactive={false}
          zIndexOffset={1000}
        />
      )}

      {/* ── 시작점 마커 ── */}
      {startPoint && (
        <Marker position={[startPoint.lat, startPoint.lng]} icon={startIcon}>
          <Tooltip permanent direction="top" offset={[0, -20]}>
            <span style={{ fontSize: 11, fontWeight: 700, color: '#1d4ed8' }}>
              시작점 {startPoint.lat.toFixed(1)}°N {startPoint.lng.toFixed(1)}°E
            </span>
          </Tooltip>
        </Marker>
      )}
    </MapContainer>
  )
}
