import { useEffect, useRef, useState } from 'react'
import { createChart } from 'lightweight-charts'
import { Terminal, Activity, TrendingUp, AlertTriangle, Cpu, Briefcase, Newspaper, ShieldCheck, DollarSign, Globe, Layers } from 'lucide-react'
import './index.css'

const API_BASE = 'http://localhost:8000/api'

function App() {
  const [activeTab, setActiveTab] = useState('forecast') // 'forecast' | 'portfolio' | 'macro_ft'
  const [ticker, setTicker] = useState('PLTR')
  const [searchInput, setSearchInput] = useState('')
  const [marketData, setMarketData] = useState(null)
  const [newsData, setNewsData] = useState(null)
  const [tradeSignal, setTradeSignal] = useState(null)
  
  // Live Portfolio State
  const [portfolioData, setPortfolioData] = useState(null)
  const [loadingPortfolio, setLoadingPortfolio] = useState(false)

  // Financial Times Macro State
  const [ftData, setFtData] = useState(null)
  const [loadingFt, setLoadingFt] = useState(false)

  const [loadingChart, setLoadingChart] = useState(false)
  const chartContainerRef = useRef(null)
  const chartRef = useRef(null)

  // Fetch Fundamentals & News for Forecast Tab
  useEffect(() => {
    if (activeTab !== 'forecast') return
    fetch(`${API_BASE}/market/${ticker}`)
      .then(res => res.json())
      .then(data => setMarketData(data))
      .catch(err => console.error("Error fetching market data", err))
  }, [ticker, activeTab])

  useEffect(() => {
    if (activeTab !== 'forecast') return
    fetch(`${API_BASE}/news`)
      .then(res => res.json())
      .then(data => setNewsData(data))
      .catch(err => console.error("Error fetching news", err))
  }, [activeTab])

  // Fetch Forecast & Render Chart
  useEffect(() => {
    if (activeTab !== 'forecast' || !chartContainerRef.current) return

    setLoadingChart(true)
    if (chartRef.current) {
      chartRef.current.remove()
    }

    const chart = createChart(chartContainerRef.current, {
      layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#94a3b8' },
      grid: { vertLines: { color: 'rgba(255, 255, 255, 0.05)' }, horzLines: { color: 'rgba(255, 255, 255, 0.05)' } },
      crosshair: { mode: 1, vertLine: { color: '#8b5cf6', width: 1, style: 3 }, horzLine: { color: '#8b5cf6', width: 1, style: 3 } },
      timeScale: { timeVisible: true, secondsVisible: false },
    })
    chartRef.current = chart

    const historicalSeries = chart.addCandlestickSeries({
      upColor: '#10b981', downColor: '#ef4444', borderVisible: false, wickUpColor: '#10b981', wickDownColor: '#ef4444'
    })
    const predictionSeries = chart.addCandlestickSeries({
      upColor: 'rgba(16, 185, 129, 0.4)', downColor: 'rgba(239, 68, 68, 0.4)', borderVisible: true, borderColor: '#3b82f6', wickUpColor: 'rgba(16, 185, 129, 0.4)', wickDownColor: 'rgba(239, 68, 68, 0.4)'
    })

    fetch(`${API_BASE}/forecast/${ticker}`)
      .then(res => res.json())
      .then(data => {
        if (data.historical && data.prediction) {
          historicalSeries.setData(data.historical)
          predictionSeries.setData(data.prediction)
          chart.timeScale().fitContent()
        }
        setTradeSignal(data.signal || null)
      })
      .catch(err => console.error("Error fetching forecast", err))
      .finally(() => setLoadingChart(false))
      
    const handleResize = () => {
      if (chartContainerRef.current) chart.applyOptions({ width: chartContainerRef.current.clientWidth, height: chartContainerRef.current.clientHeight })
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [ticker, activeTab])

  // Fetch Live Portfolio when tab changes
  useEffect(() => {
    if (activeTab === 'portfolio') {
      setLoadingPortfolio(true)
      fetch(`${API_BASE}/live_trades`)
        .then(res => res.json())
        .then(data => setPortfolioData(data))
        .catch(err => console.error("Error fetching live trades", err))
        .finally(() => setLoadingPortfolio(false))
    }
  }, [activeTab])

  // Fetch Financial Times Macro when tab changes
  useEffect(() => {
    if (activeTab === 'macro_ft') {
      setLoadingFt(true)
      fetch(`${API_BASE}/macro_ft`)
        .then(res => res.json())
        .then(data => setFtData(data))
        .catch(err => console.error("Error fetching FT macro", err))
        .finally(() => setLoadingFt(false))
    }
  }, [activeTab])

  const formatTime = (unixTime) => {
    return new Date(unixTime * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }

  return (
    <>
      <header className="dashboard-header">
        <div className="brand">
          <Terminal className="brand-icon" />
          KRONOS_ALPHA_DESK
        </div>
        
        {/* Navigation Tabs */}
        <div className="nav-tabs">
          <button 
            className={`nav-tab-btn ${activeTab === 'forecast' ? 'active' : ''}`}
            onClick={() => setActiveTab('forecast')}
          >
            <TrendingUp size={16} /> Kronos AI Forecasts
          </button>
          <button 
            className={`nav-tab-btn ${activeTab === 'portfolio' ? 'active' : ''}`}
            onClick={() => setActiveTab('portfolio')}
          >
            <Briefcase size={16} /> Live Portfolio & Reasons
          </button>
          <button 
            className={`nav-tab-btn ${activeTab === 'macro_ft' ? 'active' : ''}`}
            onClick={() => setActiveTab('macro_ft')}
          >
            <Newspaper size={16} /> Financial Times Macro Desk
          </button>
        </div>

        {activeTab === 'forecast' && (
          <div className="ticker-selector" style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            {['PLTR', 'NVDA', 'TSLA', 'GLD', 'SOL-USD'].map(sym => (
              <button key={sym} className={`ticker-btn ${ticker === sym ? 'active' : ''}`} onClick={() => setTicker(sym)}>
                {sym}
              </button>
            ))}
            <form onSubmit={(e) => { e.preventDefault(); if (searchInput) setTicker(searchInput.toUpperCase()); }}>
              <input type="text" className="search-input" placeholder="Ticker (e.g. AAPL)" value={searchInput} onChange={(e) => setSearchInput(e.target.value)} />
            </form>
          </div>
        )}
      </header>

      {/* VIEW 1: KRONOS FORECAST & CHARTS */}
      {activeTab === 'forecast' && (
        <main className="dashboard-grid">
          <aside style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div className="panel agent-output">
              <h2 className="panel-title" style={{ color: '#10b981' }}><Cpu size={16} /> Orchestrator Output</h2>
              {newsData ? (
                <>
                  <p className="agent-text">"{newsData.agent_analysis}"</p>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div className={`uncertainty-badge uncertainty-${newsData.uncertainty_level.toLowerCase().split('-')[0]}`}>
                      <AlertTriangle size={14} /> {newsData.uncertainty_level} Uncertainty
                    </div>
                    <div style={{ fontSize: '0.8rem', color: '#10b981' }}>Sentiment: {newsData.sentiment_score}/100</div>
                  </div>
                </>
              ) : (<div className="loader-container"><div className="spinner" /></div>)}
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
                    <div className="stat-value" style={{ color: marketData.analyst_rating?.includes('Buy') ? '#10b981' : '#3b82f6' }}>{marketData.analyst_rating || "N/A"}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">30-Day Volatility</div>
                    <div className="stat-value text-red">{marketData.volatility}</div>
                  </div>
                </div>
              ) : (<div className="loader-container"><div className="spinner" /></div>)}
            </div>
          </aside>

          <div className="panel chart-container">
            <h2 className="panel-title" style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
              <span><TrendingUp size={16} /> {ticker} LIVE & KRONOS FORECAST</span>
            </h2>
            <div className="chart-wrapper" ref={chartContainerRef}>
              {loadingChart && (<div className="loader-container" style={{ position: 'absolute', inset: 0, zIndex: 10, background: 'rgba(11,15,25,0.7)' }}><div className="spinner" /> Generating Neural Forecast...</div>)}
            </div>
          </div>

          <aside style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', maxHeight: 'calc(100vh - 100px)' }}>
            <div className="panel" style={{ flexGrow: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <h2 className="panel-title"><Activity size={16} /> Live Macro Timeline</h2>
              <div className="timeline" style={{ flexGrow: 1 }}>
                {newsData ? (
                  newsData.macro_events.map((evt, i) => (
                    <div key={`macro-${i}`} className="timeline-item macro">
                      <div className="timeline-bullet" />
                      <div className="timeline-time">{evt.time}</div>
                      <div style={{ fontWeight: '600', marginBottom: '0.25rem' }}>{evt.country} {evt.title}</div>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem', fontSize: '0.75rem', background: 'rgba(0,0,0,0.2)', padding: '0.5rem', borderRadius: '4px' }}>
                        <div><div style={{ color: '#94a3b8', fontSize: '0.65rem' }}>ACTUAL</div><div style={{ color: '#e2e8f0' }}>{evt.actual || '--'}</div></div>
                        <div><div style={{ color: '#94a3b8', fontSize: '0.65rem' }}>FORECAST</div><div style={{ color: '#e2e8f0' }}>{evt.forecast || '--'}</div></div>
                        <div><div style={{ color: '#94a3b8', fontSize: '0.65rem' }}>PREVIOUS</div><div style={{ color: '#e2e8f0' }}>{evt.previous || '--'}</div></div>
                      </div>
                    </div>
                  ))
                ) : (<div className="loader-container"><div className="spinner" /> Syncing...</div>)}
              </div>
            </div>
          </aside>
        </main>
      )}

      {/* VIEW 2: LIVE PORTFOLIO & ALGORITHMIC TRADE RATIONALES */}
      {activeTab === 'portfolio' && (
        <div className="portfolio-container">
          {loadingPortfolio || !portfolioData ? (
            <div className="loader-container" style={{ minHeight: '400px' }}><div className="spinner" /> Querying Alpaca Brokerage Real-Time Book...</div>
          ) : (
            <>
              <div className="portfolio-overview">
                <div className="stat-card" style={{ background: 'rgba(16, 185, 129, 0.05)', border: '1px solid rgba(16, 185, 129, 0.2)' }}>
                  <div className="stat-label" style={{ color: '#10b981' }}><DollarSign size={14} style={{ display: 'inline' }} /> Total Account Equity</div>
                  <div className="stat-value">${portfolioData.account?.equity.toLocaleString() || '100,000'}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label"><ShieldCheck size={14} style={{ display: 'inline' }} /> Available Buying Power</div>
                  <div className="stat-value">${portfolioData.account?.buying_power.toLocaleString() || '--'}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Unencumbered Cash Reserves</div>
                  <div className="stat-value">${portfolioData.account?.cash.toLocaleString() || '--'}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Net Gain vs Baseline</div>
                  <div className="stat-value" style={{ color: (portfolioData.account?.day_change >= 0) ? '#10b981' : '#ef4444' }}>
                    {portfolioData.account?.day_change >= 0 ? '+' : ''}${portfolioData.account?.day_change || 0}
                  </div>
                </div>
              </div>

              <h2 className="panel-title" style={{ marginTop: '1rem' }}>
                <Layers size={18} style={{ display: 'inline' }} /> Active Positions & Institutional Algorithmic Rationale
              </h2>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {portfolioData.positions?.length === 0 ? (
                  <div className="panel" style={{ textAlign: 'center', padding: '3rem', color: '#94a3b8' }}>
                    No open positions right now. Kronos quantitative engines are scanning for high-conviction setups (Score &gt;= 2.0).
                  </div>
                ) : (
                  portfolioData.positions?.map((pos, idx) => (
                    <div key={idx} className={`trade-card ${pos.pnl_usd >= 0 ? 'win' : 'loss'}`}>
                      <div className="trade-header">
                        <div className="trade-title">
                          {pos.symbol} <span className="badge badge-blue">{pos.asset_class}</span>
                          <span className="badge badge-purple">{pos.status_badge}</span>
                        </div>
                        <div style={{ fontWeight: '700', fontSize: '1.25rem', color: pos.pnl_usd >= 0 ? '#10b981' : '#ef4444' }}>
                          {pos.pnl_usd >= 0 ? '+' : ''}${pos.pnl_usd} ({pos.pnl_pct >= 0 ? '+' : ''}{pos.pnl_pct}%)
                        </div>
                      </div>
                      
                      <div className="trade-metrics">
                        <div><div className="stat-label">Quantity Held</div><div style={{ fontWeight: '600' }}>{pos.qty}</div></div>
                        <div><div className="stat-label">Avg Entry Price</div><div style={{ fontWeight: '600' }}>${pos.entry_price}</div></div>
                        <div><div className="stat-label">Current Price</div><div style={{ fontWeight: '600' }}>${pos.current_price}</div></div>
                        <div><div className="stat-label">Market Valuation</div><div style={{ fontWeight: '600' }}>${pos.market_value}</div></div>
                        <div><div className="stat-label">Risk Management Level</div><div style={{ fontWeight: '600', color: '#06b6d4' }}>{pos.stop_tier}</div></div>
                      </div>

                      <div className="rationale-box">
                        <div className="rationale-title"><Cpu size={14} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '4px' }} /> Quantitative & Macro Entry Rationale</div>
                        <p style={{ fontSize: '0.9rem', color: '#cbd5e1', lineHeight: '1.5', margin: 0 }}>{pos.rationale}</p>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* VIEW 3: FINANCIAL TIMES (FT) INSTITUTIONAL MACRO RUNDOWN */}
      {activeTab === 'macro_ft' && (
        <div className="ft-container">
          {loadingFt || !ftData ? (
            <div className="loader-container" style={{ minHeight: '400px' }}><div className="spinner" /> Printing Financial Times Institutional Edition...</div>
          ) : (
            <>
              <div className="ft-masthead">
                <div className="ft-title">{ftData.masthead}</div>
                <div className="ft-date">Global Macro Economic Desk • {ftData.edition_date} • London & New York Edition</div>
              </div>

              {/* Lead Story */}
              <div className="ft-lead">
                <div className="ft-lead-text">
                  <h2>{ftData.lead_story?.headline}</h2>
                  <h3>{ftData.lead_story?.sub_headline}</h3>
                  <p>{ftData.lead_story?.article_p1}</p>
                  <p>{ftData.lead_story?.article_p2}</p>
                  <div style={{ fontStyle: 'italic', fontSize: '0.85rem', color: '#94a3b8', marginTop: '1rem' }}>{ftData.lead_story?.author}</div>
                </div>
                
                {/* Central Bank Policy Tracker */}
                <div className="panel" style={{ border: '1px solid rgba(253, 224, 71, 0.2)', background: 'rgba(0, 0, 0, 0.4)' }}>
                  <h3 style={{ color: '#fde047', borderBottom: '1px solid rgba(253, 224, 71, 0.2)', paddingBottom: '0.5rem', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <Globe size={18} /> Central Bank Policy Tracker
                  </h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                    <div>
                      <div style={{ fontWeight: '700', color: '#fff', display: 'flex', justifyContent: 'space-between' }}><span>Federal Reserve (USD)</span><span style={{ color: '#38bdf8' }}>{ftData.central_bank_tracker?.fed.rate}</span></div>
                      <div style={{ fontSize: '0.8rem', color: '#cbd5e1' }}>Outlook: {ftData.central_bank_tracker?.fed.outlook}</div>
                      <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Next FOMC: {ftData.central_bank_tracker?.fed.next_decision}</div>
                    </div>
                    <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '0.5rem' }}>
                      <div style={{ fontWeight: '700', color: '#fff', display: 'flex', justifyContent: 'space-between' }}><span>ECB Europe (EUR)</span><span style={{ color: '#38bdf8' }}>{ftData.central_bank_tracker?.ecb.rate}</span></div>
                      <div style={{ fontSize: '0.8rem', color: '#cbd5e1' }}>Outlook: {ftData.central_bank_tracker?.ecb.outlook}</div>
                      <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Next Decision: {ftData.central_bank_tracker?.ecb.next_decision}</div>
                    </div>
                    <div style={{ borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '0.5rem' }}>
                      <div style={{ fontWeight: '700', color: '#fff', display: 'flex', justifyContent: 'space-between' }}><span>Bank of England (GBP)</span><span style={{ color: '#38bdf8' }}>{ftData.central_bank_tracker?.boe.rate}</span></div>
                      <div style={{ fontSize: '0.8rem', color: '#cbd5e1' }}>Outlook: {ftData.central_bank_tracker?.boe.outlook}</div>
                      <div style={{ fontSize: '0.75rem', color: '#64748b' }}>Next Decision: {ftData.central_bank_tracker?.boe.next_decision}</div>
                    </div>
                  </div>
                </div>
              </div>

              {/* Sector columns */}
              <div className="ft-columns">
                {ftData.sector_columns?.map((col, i) => (
                  <div key={i} className="ft-col-card">
                    <div className="ft-col-title">{col.sector_name}</div>
                    <div className="ft-col-body">{col.summary}</div>
                  </div>
                ))}
              </div>

              {/* ForexFactory Calendar Grid */}
              <div>
                <h3 style={{ fontSize: '1.25rem', fontFamily: 'Georgia, serif', color: '#fde047', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '0.5rem', marginTop: '1rem' }}>
                  📅 This Week's Global High-Impact Economic Events (ForexFactory Archive)
                </h3>
                <div className="ft-calendar-grid">
                  {ftData.macro_calendar?.map((ev, i) => (
                    <div key={i} className="macro-card">
                      <div className="macro-card-top">
                        <span style={{ fontWeight: '700', color: ev.country === 'USD' ? '#38bdf8' : '#e879f9' }}>[{ev.country}] {ev.time}</span>
                        <span style={{ color: ev.impact === 'High' ? '#ef4444' : '#fbbf24', fontWeight: '600' }}>{ev.impact.toUpperCase()} IMPACT</span>
                      </div>
                      <div className="macro-card-title">{ev.title}</div>
                      <div className="macro-nums">
                        <div><div style={{ fontSize: '0.65rem', color: '#94a3b8' }}>ACTUAL</div><div style={{ fontWeight: '600', color: '#10b981' }}>{ev.actual}</div></div>
                        <div><div style={{ fontSize: '0.65rem', color: '#94a3b8' }}>FORECAST</div><div style={{ fontWeight: '600' }}>{ev.forecast}</div></div>
                        <div><div style={{ fontSize: '0.65rem', color: '#94a3b8' }}>PREV</div><div style={{ color: '#94a3b8' }}>{ev.previous}</div></div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </>
  )
}

export default App
