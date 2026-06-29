import { MapContainer, TileLayer, Polyline, CircleMarker, Tooltip, Marker, useMapEvents, Popup } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import type { PredictedPoint, AnalogTyphoon } from '../../types/typhoon'
import { INTENSITY_COLOR } from '../../types/typhoon'

// 시작점 마커 아이콘
const startIcon = L.divIcon({
  className: '',
  html: `<div style="
    width: 36px; height: 36px;
    background: #1d4ed8;
    border: 3px solid #fff;
    border-radius: 50%;
    box-shadow: 0 0 0 3px #1d4ed8, 0 3px 10px rgba(0,0,0,0.4);
    display: flex; align-items: center; justify-content: center;
    font-size: 16px;
  ">📍</div>`,
  iconSize: [36, 36],
  iconAnchor: [18, 18],
})

// 24h 타임 레이블 아이콘 생성
function makeTimeIcon(label: string, color: string) {
  return L.divIcon({
    className: '',
    html: `<div style="
      background: ${color};
      color: #fff;
      border: 2px solid #fff;
      border-radius: 4px;
      padding: 2px 5px;
      font-size: 10px;
      font-weight: 800;
      white-space: nowrap;
      box-shadow: 0 1px 4px rgba(0,0,0,0.3);
      transform: translate(-50%, -150%);
    ">${label}</div>`,
    iconSize: [0, 0],
    iconAnchor: [0, 0],
  })
}

const ANALOG_COLORS = ['#f59e0b', '#a855f7', '#06b6d4']

interface Props {
  startPoint: { lat: number; lng: number } | null
  predictedTrack: PredictedPoint[]
  analogs: AnalogTyphoon[]
  isPickingStart: boolean
  onMapClick: (lat: number, lng: number) => void
  showAnalogs: boolean
}

function ClickHandler({ onMapClick, isPickingStart }: { onMapClick: Props['onMapClick']; isPickingStart: boolean }) {
  useMapEvents({
    click(e) {
      if (isPickingStart) onMapClick(e.latlng.lat, e.latlng.lng)
    },
  })
  return null
}

export default function TyphoonMap({
  startPoint, predictedTrack, analogs, isPickingStart, onMapClick, showAnalogs,
}: Props) {
  // 강도별 구간으로 경로를 분리
  const segments: { positions: [number, number][]; color: string }[] = []
  for (let i = 0; i < predictedTrack.length - 1; i++) {
    const p = predictedTrack[i]
    segments.push({
      positions: [[p.lat, p.lng], [predictedTrack[i + 1].lat, predictedTrack[i + 1].lng]],
      color: INTENSITY_COLOR[p.intensity],
    })
  }

  return (
    <MapContainer
      center={[22, 135]}
      zoom={4}
      style={{ width: '100%', height: '100%', cursor: isPickingStart ? 'crosshair' : 'grab' }}
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/">OpenStreetMap</a>'
      />
      <ClickHandler onMapClick={onMapClick} isPickingStart={isPickingStart} />

      {/* ── 유사 태풍 경로 ── */}
      {showAnalogs && analogs.map((analog, idx) => (
        <Polyline
          key={analog.id}
          positions={analog.track.map(p => [p.lat, p.lng])}
          color={ANALOG_COLORS[idx % ANALOG_COLORS.length]}
          weight={2}
          opacity={0.4}
          dashArray="6 4"
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
        <Polyline
          key={`seg-${i}`}
          positions={seg.positions}
          color={seg.color}
          weight={4}
          opacity={0.9}
        />
      ))}

      {/* ── 예측 포인트 마커 ── */}
      {predictedTrack.map((p, i) => {
        const isDay = p.hour % 24 === 0 && p.hour > 0   // 24h 단위 레이블
        const isFirst = i === 0
        const isLast = i === predictedTrack.length - 1
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
                    <tr>
                      <td style={{ color: '#64748b', paddingRight: 8 }}>강도</td>
                      <td style={{ fontWeight: 700, color: INTENSITY_COLOR[p.intensity] }}>{p.intensity}</td>
                    </tr>
                    <tr>
                      <td style={{ color: '#64748b' }}>기압</td>
                      <td><b>{p.pressure.toFixed(0)}</b> hPa</td>
                    </tr>
                    <tr>
                      <td style={{ color: '#64748b' }}>풍속</td>
                      <td><b>{p.wind_ms.toFixed(1)}</b> m/s</td>
                    </tr>
                    <tr>
                      <td style={{ color: '#64748b' }}>위치</td>
                      <td>{p.lat.toFixed(2)}°N {p.lng.toFixed(2)}°E</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </Popup>
          </CircleMarker>
        )
      })}

      {/* ── 24h 시간 레이블 마커 ── */}
      {predictedTrack
        .filter((p, i) => p.hour % 24 === 0 && p.hour > 0 && i !== predictedTrack.length - 1)
        .map(p => (
          <Marker
            key={`lbl-${p.hour}`}
            position={[p.lat, p.lng]}
            icon={makeTimeIcon(`+${p.hour / 24}일`, INTENSITY_COLOR[p.intensity])}
            interactive={false}
          />
        ))}

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
