import { useEffect, useRef, useState } from 'react'
import { createChart } from 'lightweight-charts'
import { Terminal, Activity, TrendingUp, AlertTriangle, Cpu } from 'lucide-react'
import './index.css'

const API_BASE = 'http://localhost:8000/api'

function App() {
  const [ticker, setTicker] = useState('PLTR')
  const [searchInput, setSearchInput] = useState('')
  const [marketData, setMarketData] = useState(null)
  const [newsData, setNewsData] = useState(null)
  const [tradeSignal, setTradeSignal] = useState(null)
  const [loadingChart, setLoadingChart] = useState(false)
  const chartContainerRef = useRef(null)
  const chartRef = useRef(null)

  // Fetch Fundamentals
  useEffect(() => {
    fetch(`${API_BASE}/market/${ticker}`)
      .then(res => res.json())
      .then(data => setMarketData(data))
      .catch(err => console.error("Error fetching market data", err))
  }, [ticker])

  // Fetch News & Macro
  useEffect(() => {
    fetch(`${API_BASE}/news`)
      .then(res => res.json())
      .then(data => setNewsData(data))
      .catch(err => console.error("Error fetching news", err))
  }, [])

  // Fetch Forecast & Render Chart
  useEffect(() => {
    if (!chartContainerRef.current) return

    setLoadingChart(true)

    // Cleanup previous chart
    if (chartRef.current) {
      chartRef.current.remove()
    }

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { type: 'solid', color: 'transparent' },
        textColor: '#94a3b8',
      },
      grid: {
        vertLines: { color: 'rgba(255, 255, 255, 0.05)' },
        horzLines: { color: 'rgba(255, 255, 255, 0.05)' },
      },
      crosshair: {
        mode: 1, // Normal crosshair
        vertLine: { color: '#8b5cf6', width: 1, style: 3 },
        horzLine: { color: '#8b5cf6', width: 1, style: 3 },
      },
      timeScale: {
        timeVisible: true,
        secondsVisible: false,
      },
    })
    chartRef.current = chart

    const historicalSeries = chart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444'
    })

    const predictionSeries = chart.addCandlestickSeries({
      upColor: 'rgba(16, 185, 129, 0.4)',
      downColor: 'rgba(239, 68, 68, 0.4)',
      borderVisible: true,
      borderColor: '#3b82f6',
      wickUpColor: 'rgba(16, 185, 129, 0.4)',
      wickDownColor: 'rgba(239, 68, 68, 0.4)'
    })

      fetch(`${API_BASE}/forecast/${ticker}`)
      .then(res => res.json())
      .then(data => {
        if (data.historical && data.prediction) {
          historicalSeries.setData(data.historical)
          predictionSeries.setData(data.prediction)
          chart.timeScale().fitContent()
        }
        if (data.signal) {
          setTradeSignal(data.signal)
        } else {
          setTradeSignal(null)
        }
      })
      .catch(err => console.error("Error fetching forecast", err))
      .finally(() => setLoadingChart(false))
      
    // Handle resize
    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth, height: chartContainerRef.current.clientHeight })
      }
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [ticker])

  const formatTime = (unixTime) => {
    return new Date(unixTime * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  return (
    <>
      <header className="dashboard-header">
        <div className="brand">
          <Terminal className="brand-icon" />
          KRONOS_TERMINAL
        </div>
        <div className="ticker-selector" style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          {['PLTR', 'MSFT', 'GC=F', 'QCOM', 'EURGBP=X'].map(sym => (
            <button 
              key={sym} 
              className={`ticker-btn ${ticker === sym ? 'active' : ''}`}
              onClick={() => setTicker(sym)}
            >
              {sym}
            </button>
          ))}
          <form onSubmit={(e) => {
            e.preventDefault()
            if (searchInput) setTicker(searchInput.toUpperCase())
          }}>
            <input 
              type="text" 
              className="search-input" 
              placeholder="Search ticker (e.g. AAPL)" 
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
            />
          </form>
        </div>
      </header>

      <main className="dashboard-grid">
        
        {/* LEFT COLUMN: Orchestrator Output & Fundamentals */}
        <aside style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          
          <div className="panel agent-output">
            <h2 className="panel-title" style={{ color: '#10b981' }}>
              <Cpu size={16} /> Orchestrator Output
            </h2>
            {newsData ? (
              <>
                <p className="agent-text">"{newsData.agent_analysis}"</p>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div className={`uncertainty-badge uncertainty-${newsData.uncertainty_level.toLowerCase().split('-')[0]}`}>
                    <AlertTriangle size={14} /> {newsData.uncertainty_level} Uncertainty
                  </div>
                  <div style={{ fontSize: '0.8rem', color: '#10b981' }}>
                    Sentiment: {newsData.sentiment_score}/100
                  </div>
                </div>
              </>
            ) : (
              <div className="loader-container"><div className="spinner" /></div>
            )}
          </div>

          <div className="panel">
            <h2 className="panel-title">Fundamentals</h2>
            {marketData ? (
              <div className="stats-grid">
                <div className="stat-card">
                  <div className="stat-label">Current Price</div>
                  <div className="stat-value">${Number(marketData.current_price).toFixed(2)}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Analyst Rating</div>
                  <div className="stat-value" style={{ 
                    color: marketData.analyst_rating?.includes('Buy') ? '#10b981' : 
                           marketData.analyst_rating?.includes('Sell') ? '#ef4444' : 
                           marketData.analyst_rating === 'N/A' ? '#94a3b8' : '#3b82f6' 
                  }}>
                    {marketData.analyst_rating || "N/A"}
                  </div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">P/E Ratio</div>
                  <div className="stat-value">{marketData.pe_ratio !== "N/A" ? Number(marketData.pe_ratio).toFixed(2) : "N/A"}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">30-Day Volatility</div>
                  <div className="stat-value text-red">{marketData.volatility}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Beta</div>
                  <div className="stat-value">{marketData.beta !== "N/A" ? Number(marketData.beta).toFixed(2) : "N/A"}</div>
                </div>
              </div>
            ) : (
              <div className="loader-container"><div className="spinner" /></div>
            )}
          </div>
        </aside>

        {/* CENTER COLUMN: Chart */}
        <div className="panel chart-container">
          <h2 className="panel-title" style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
            <span><TrendingUp size={16} /> {ticker} LIVE & KRONOS FORECAST</span>
          </h2>
          <div className="chart-wrapper" ref={chartContainerRef}>
            {loadingChart && (
              <div className="loader-container" style={{ position: 'absolute', inset: 0, zIndex: 10, background: 'rgba(11,15,25,0.7)' }}>
                <div className="spinner" /> Generating Forecast...
              </div>
            )}
          </div>
        </div>

        {/* RIGHT COLUMN: Macro Timeline & Trade Signal */}
        <aside style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxHeight: 'calc(100vh - 100px)' }}>
          <div className="panel" style={{ flexGrow: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
            <h2 className="panel-title">
              <Activity size={16} /> Live Macro Timeline
            </h2>
            <div className="timeline" style={{ flexGrow: 1 }}>
              {newsData ? (
                <>
                  {newsData.macro_events.map((evt, i) => (
                    <div key={`macro-${i}`} className="timeline-item macro">
                      <div className="timeline-bullet" />
                      <div className="timeline-time">{evt.time || 'Pending Event'}</div>
                      <div style={{ fontWeight: '600', marginBottom: '0.25rem' }}>
                        {evt.country} {evt.title}
                      </div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem', fontSize: '0.75rem', marginTop: '0.5rem', background: 'rgba(0,0,0,0.2)', padding: '0.5rem', borderRadius: '4px' }}>
                        <div>
                          <div style={{ color: '#94a3b8', fontSize: '0.65rem', textTransform: 'uppercase' }}>Actual</div>
                          <div style={{ color: evt.actual ? '#e2e8f0' : '#64748b' }}>{evt.actual || '--'}</div>
                        </div>
                        <div>
                          <div style={{ color: '#94a3b8', fontSize: '0.65rem', textTransform: 'uppercase' }}>Forecast</div>
                          <div style={{ color: '#e2e8f0' }}>{evt.forecast || '--'}</div>
                        </div>
                        <div>
                          <div style={{ color: '#94a3b8', fontSize: '0.65rem', textTransform: 'uppercase' }}>Previous</div>
                          <div style={{ color: '#e2e8f0' }}>{evt.previous || '--'}</div>
                        </div>
                      </div>
                    </div>
                  ))}
                  {newsData.headlines.map((headline, i) => (
                    <div key={`news-${i}`} className="timeline-item">
                      <div className="timeline-bullet" />
                      <div className="timeline-time">Today</div>
                      {headline}
                    </div>
                  ))}
                </>
              ) : (
                <div className="loader-container"><div className="spinner" /> Syncing...</div>
              )}
            </div>
          </div>

          {/* Simulated Portfolio Trade Signal */}
          {tradeSignal && (
            <div className="panel" style={{ borderLeft: `3px solid ${tradeSignal.type === 'LONG' ? '#10b981' : '#ef4444'}`, overflowY: 'auto' }}>
              <h2 className="panel-title" style={{ color: tradeSignal.type === 'LONG' ? '#10b981' : '#ef4444' }}>
                <TrendingUp size={16} /> £1000 Simulated Trade: {tradeSignal.type}
              </h2>
              <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', display: 'grid', marginBottom: '1rem' }}>
                <div className="stat-card">
                  <div className="stat-label">Entry ({formatTime(tradeSignal.entry_time)})</div>
                  <div className="stat-value" style={{ fontSize: '1rem' }}>${tradeSignal.entry_price.toFixed(2)}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Exit ({formatTime(tradeSignal.exit_time)})</div>
                  <div className="stat-value" style={{ fontSize: '1rem' }}>${tradeSignal.take_profit.toFixed(2)}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Target (TP)</div>
                  <div className="stat-value text-green" style={{ fontSize: '1rem' }}>+£{tradeSignal.portfolio_profit_gbp.toFixed(2)}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Stop Loss (SL @ ${tradeSignal.stop_loss.toFixed(2)})</div>
                  <div className="stat-value text-red" style={{ fontSize: '1rem' }}>-£{tradeSignal.portfolio_risk_gbp.toFixed(2)}</div>
                </div>
              </div>
              
              <div style={{ fontSize: '0.85rem', color: '#94a3b8' }}>
                <h4 style={{ color: '#e2e8f0', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Forecast Drivers</h4>
                <ul style={{ paddingLeft: '1.2rem', marginBottom: '1rem', listStyleType: 'circle' }}>
                  {tradeSignal.drivers?.map((d, i) => <li key={`driver-${i}`} style={{ marginBottom: '0.25rem' }}>{d}</li>)}
                </ul>
                <h4 style={{ color: '#e2e8f0', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Execution Risks</h4>
                <ul style={{ paddingLeft: '1.2rem', listStyleType: 'circle' }}>
                  {tradeSignal.risks?.map((r, i) => <li key={`risk-${i}`} style={{ marginBottom: '0.25rem' }}>{r}</li>)}
                </ul>
              </div>
            </div>
          )}
        </aside>

      </main>
    </>
  )
}

export default App
