import { useEffect, useMemo, useState } from 'react'
import CharacterCard from './components/CharacterCard'
import EndingScreen from './components/EndingScreen'
import LivingRoom from './components/LivingRoom'
import ResultStory from './components/ResultStory'
import type { StoryResult } from './components/ResultStory'
import SetupScreen from './components/SetupScreen'
import { DISASTERS } from './data/gameData'
import { advanceDay, applyStrategy, chooseFarmEvent, createGame, getHint, resolveChoice, safetyGrade, useMedkit } from './game/engine'
import type { Choice, DisasterId, FamilyId, GameState, StrategyId } from './types/game'

export default function App() {
  const [selected, setSelected] = useState<FamilyId[]>([])
  const [disaster, setDisaster] = useState<DisasterId>()
  const [game, setGame] = useState<GameState>()
  const [message, setMessage] = useState('')

  function toggleFamily(id: FamilyId) {
    setSelected((current) => {
      if (current.includes(id)) {
        setMessage('')
        return current.filter((item) => item !== id)
      }
      if (current.length >= 3) {
        setMessage('가족은 최대 3명까지 선택할 수 있어요.')
        return current
      }
      setMessage('')
      return [...current, id]
    })
  }

  function startGame() {
    if (!disaster || selected.length === 0) return
    setGame(createGame(selected, disaster))
  }

  function restart() {
    setSelected([])
    setDisaster(undefined)
    setGame(undefined)
    setMessage('')
  }

  if (!game) {
    return <SetupScreen selected={selected} disaster={disaster} message={message} onToggle={toggleFamily} onDisaster={setDisaster} onStart={startGame} />
  }
  if (game.phase === 'ending') return <EndingScreen game={game} onRestart={restart} />
  return <GameScreen game={game} onGame={setGame} onRestart={restart} />
}

function GameScreen({ game, onGame, onRestart }: { game: GameState; onGame: (game: GameState) => void; onRestart: () => void }) {
  const disaster = DISASTERS.find((item) => item.id === game.disaster)!
  const hint = useMemo(() => getHint(game), [game])
  const isFarm = game.currentEvent.id.startsWith('farm-')
  const [secondsLeft, setSecondsLeft] = useState(180)
  const [story, setStory] = useState<StoryResult>()

  useEffect(() => {
    setSecondsLeft(180)
  }, [game.day])

  useEffect(() => {
    if (story) return
    const timer = window.setInterval(() => setSecondsLeft((seconds) => Math.max(0, seconds - 1)), 1000)
    return () => window.clearInterval(timer)
  }, [game.day, story])

  function handleChoice(choice: Choice, index: number) {
    const after = resolveChoice(game, choice, (game.day + index) % game.family.length)
    const hasDamage = choice.effects.some((effect) => (effect.amount ?? 0) < 0 || (effect.risk ?? 0) > 5)
    const hasCare = choice.effects.some((effect) => (effect.amount ?? 0) > 0)
    const action: StoryResult['action'] = isFarm ? 'explore' : hasDamage ? 'caution' : hasCare ? 'care' : 'prepare'
    setStory({ before: game, after, choice, action })
  }

  function continueStory(strategy: StrategyId) {
    if (!story) return
    onGame(advanceDay(applyStrategy(story.after, strategy)))
    setStory(undefined)
  }

  const minutes = Math.floor(secondsLeft / 60)
  const seconds = String(secondsLeft % 60).padStart(2, '0')

  return (
    <main className="game-shell">
      <header className="topbar">
        <div className="brand"><span>🛟</span><div><b>우리 가족 안전 30일</b><small>함께 배우는 재난 대비</small></div></div>
        <div className="day-chip"><span>오늘은</span><strong>{game.day}일차</strong><i>/ 30일</i></div>
        <div className={`timer-chip ${secondsLeft <= 30 ? 'timer-warning' : ''}`} aria-label={`오늘의 남은 시간 ${minutes}분 ${seconds}초`}>
          <span>⏱️ 오늘의 남은 시간</span>
          <strong>{minutes}:{seconds}</strong>
          <i>{secondsLeft === 0 ? '천천히 선택해도 괜찮아요' : '시간이 끝나도 자동 진행되지 않아요'}</i>
        </div>
        <div className="disaster-chip"><span>{disaster.icon}</span><div><small>현재 재난</small><b>{disaster.name}</b></div></div>
        <button className="text-button" onClick={onRestart}>처음으로</button>
      </header>

      <div className="game-grid">
        <aside className="family-sidebar panel">
          <div className="panel-title"><span>우리 가족</span><small>{game.family.filter((item) => !item.unableToAct).length}명 활동 중</small></div>
          <div className="character-list">
            {game.family.map((member) => (
              <CharacterCard
                key={member.id}
                member={member}
                compact
                onHeal={game.resources.medkit > 0 ? () => onGame(useMedkit(game, member.id)) : undefined}
              />
            ))}
          </div>
          <div className="safety-note"><span>💡</span><p><b>{disaster.name} 안전 수칙</b>{disaster.safety}</p></div>
        </aside>

        <section className="scene-column">
          <LivingRoom disaster={game.disaster} risk={game.risk} family={game.family} action={story?.action} />
          <div className="event-card panel">
            <div className="event-title">
              <span>{game.currentEvent.icon}</span>
              <div><small>{isFarm ? '오늘의 안전 탐색' : '오늘의 상황'}</small><h2>{game.currentEvent.title}</h2></div>
            </div>
            <p className="event-description">{game.currentEvent.description}</p>
            {hint && <div className="hint">{hint}</div>}
            <div className="choices">
              {game.currentEvent.choices.map((choice, index) => (
                <button key={choice.id} onClick={() => handleChoice(choice, index)}>
                  <i>{index + 1}</i><span>{choice.label}</span><b>선택</b>
                </button>
              ))}
            </div>
            {!isFarm && (
              <button className="farm-button" onClick={() => onGame(chooseFarmEvent(game))}>
                <span>🎒</span><div><b>물품이 부족한가요?</b><small>오늘은 밖의 안전을 확인하고 물품을 탐색해요.</small></div><i>파밍하기 →</i>
              </button>
            )}
          </div>
        </section>

        <aside className="resource-sidebar">
          <section className="panel inventory">
            <div className="panel-title"><span>비상 물품</span><small>매일 인원만큼 사용</small></div>
            <Resource icon="🍞" label="빵" value={game.resources.bread} color="#e59b43" />
            <Resource icon="💧" label="물" value={game.resources.water} color="#4da7e8" />
            <Resource icon="🩹" label="구급상자" value={game.resources.medkit} color="#ef6b6b" />
          </section>
          <section className="panel score-panel">
            <div className="panel-title"><span>안전 성장</span><small>{safetyGrade(game.level)}</small></div>
            <div className="level-card">
              <div><span>⭐</span><b>Lv.{game.level}</b><small>{game.xp} XP</small></div>
              <div className="xp-track"><i style={{ width: `${game.xp % 100}%` }} /></div>
              <p>🔥 현재 {game.combo}콤보 · 최고 {game.bestCombo}콤보</p>
            </div>
            {!!game.badges.length && <div className="mini-badges" aria-label="획득한 배지">{game.badges.map((badge) => <span title={badge.description} key={badge.id}>{badge.icon}<i>{badge.name}</i></span>)}</div>}
            <Score label="재난 대비" value={game.preparedness} icon="🛡️" />
            <Score label="구조 연결" value={game.rescue} icon="📡" />
            <Score label="현재 위험" value={game.risk} icon="⚠️" danger />
          </section>
          <section className="panel logs">
            <div className="panel-title"><span>가족 안전 일지</span></div>
            {game.logs.map((log, index) => (
              <div className={`log ${log.tone}`} key={`${log.day}-${index}`}><b>{log.day}일</b><p>{log.text}</p></div>
            ))}
          </section>
        </aside>
      </div>
      {story && <ResultStory story={story} onContinue={continueStory} />}
    </main>
  )
}

function Resource({ icon, label, value, color }: { icon: string; label: string; value: number; color: string }) {
  return <div className="resource"><span style={{ background: `${color}22` }}>{icon}</span><div><small>{label}</small><b>{value}<i>개</i></b></div></div>
}

function Score({ label, value, icon, danger = false }: { label: string; value: number; icon: string; danger?: boolean }) {
  return <div className="score"><span>{icon}</span><div><small>{label}</small><div><i style={{ width: `${value}%` }} className={danger ? 'danger' : ''} /></div></div><b>{value}</b></div>
}
