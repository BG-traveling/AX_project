import { useYears, useTyphoonList } from '../../hooks/useTyphoonData'

interface Props {
  selectedYear: number | null
  selectedId: string | null
  onYearChange: (year: number | null) => void
  onSelectTyphoon: (id: string) => void
}

export default function TyphoonSelector({ selectedYear, selectedId, onYearChange, onSelectTyphoon }: Props) {
  const { years, loading: yearsLoading } = useYears()
  const { list, loading: listLoading } = useTyphoonList(selectedYear)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <label style={{ fontSize: 13, fontWeight: 600, color: '#475569' }}>연도</label>
      <select
        value={selectedYear ?? ''}
        onChange={e => onYearChange(e.target.value ? Number(e.target.value) : null)}
        disabled={yearsLoading}
        style={selectStyle}
      >
        <option value="">연도 선택</option>
        {years.map(y => <option key={y} value={y}>{y}년</option>)}
      </select>

      <label style={{ fontSize: 13, fontWeight: 600, color: '#475569', marginTop: 8 }}>태풍</label>
      <select
        value={selectedId ?? ''}
        onChange={e => e.target.value && onSelectTyphoon(e.target.value)}
        disabled={!selectedYear || listLoading}
        style={selectStyle}
      >
        <option value="">{listLoading ? '불러오는 중...' : '태풍 선택'}</option>
        {list.map(t => (
          <option key={t.id} value={t.id}>
            {t.name_en} ({t.track_count}개 관측)
          </option>
        ))}
      </select>
    </div>
  )
}

const selectStyle: React.CSSProperties = {
  padding: '8px 10px',
  borderRadius: 8,
  border: '1px solid #e2e8f0',
  fontSize: 14,
  background: '#fff',
  cursor: 'pointer',
  width: '100%',
}
