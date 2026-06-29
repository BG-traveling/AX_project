import { useState, useEffect } from 'react'
import { fetchYears, fetchTyphoons, fetchTyphoonDetail } from '../api/typhoonApi'
import type { TyphoonSummary, TyphoonDetail } from '../types/typhoon'

export function useYears() {
  const [years, setYears] = useState<number[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchYears()
      .then(setYears)
      .finally(() => setLoading(false))
  }, [])

  return { years, loading }
}

export function useTyphoonList(year: number | null) {
  const [list, setList] = useState<TyphoonSummary[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!year) { setList([]); return }
    setLoading(true)
    fetchTyphoons(year)
      .then(setList)
      .finally(() => setLoading(false))
  }, [year])

  return { list, loading }
}

export function useTyphoonDetail(id: string | null) {
  const [detail, setDetail] = useState<TyphoonDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) { setDetail(null); return }
    setLoading(true)
    setError(null)
    fetchTyphoonDetail(id)
      .then(setDetail)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [id])

  return { detail, loading, error }
}
