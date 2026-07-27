import { useEffect, useRef, useState } from 'react'
import { createChart } from 'lightweight-charts'
import { Terminal, Activity, TrendingUp, AlertTriangle, Cpu, Briefcase, Newspaper, ShieldCheck, DollarSign, Globe, Layers, BarChart3, Search, FileText, CheckCircle2, XCircle, Info, X, ExternalLink } from 'lucide-react'
import './index.css'

const API_BASE = 'http://localhost:8000/api'

function App() {
  const [activeTab, setActiveTab] = useState('forecast') // 'forecast' | 'portfolio' | 'macro_ft' | 'earnings'
  const [ticker, setTicker] = useState('PLTR')
  const [searchInput, setSearchInput] = useState('')
  
  // Forecast Tab State
  const [marketData, setMarketData] = useState(null)
  const [orchestratorData, setOrchestratorData] = useState(null)
  const [tradeSignal, setTradeSignal] = useState(null)
  const [loadingChart, setLoadingChart] = useState(false)
  
  // Live Portfolio State
  const [portfolioData, setPortfolioData] = useState(null)
  const [loadingPortfolio, setLoadingPortfolio] = useState(false)

  // Financial Times Macro State
  const [ftData, setFtData] = useState(null)
  const [loadingFt, setLoadingFt] = useState(false)

  // Earnings & Fundamental Hub State
  const [portfolioEarnings, setPortfolioEarnings] = useState(null)
  const [loadingPortEarnings, setLoadingPortEarnings] = useState(false)
  const [earningsSearchTicker, setEarningsSearchTicker] = useState('NVDA')
  const [tickerEarningsData, setTickerEarningsData] = useState(null)
  const [loadingTickerEarnings, setLoadingTickerEarnings] = useState(false)

  // Interactive Stock Summary Modal State
  const [selectedModalTicker, setSelectedModalTicker] = useState(null)
  const [modalData, setModalData] = useState(null)
  const [loadingModal, setLoadingModal] = useState(false)

  const chartContainerRef = useRef(null)
  const chartRef = useRef(null)

  // Open interactive summary modal
  const openTickerModal = (sym) => {
    const cleanSym = (sym.includes("USD") && !sym.includes("-") && sym !== "USD") ? sym.replace("USD", "-USD") : sym
    setSelectedModalTicker(cleanSym)
    setLoadingModal(true)
    fetch(`${API_BASE}/earnings/${cleanSym}`)
      .then(res => res.json())
      .then(data => setModalData(data))
      .catch(err => console.error("Error fetching modal summary", err))
      .finally(() => setLoadingModal(false))
  }

  const closeTickerModal = () => {
    setSelectedModalTicker(null)
    setModalData(null)
  }

  // Fetch Market Data & Orchestrator Intelligence for Forecast Tab
  useEffect(() => {
    if (activeTab !== 'forecast') return
    fetch(`${API_BASE}/market/${ticker}`)
      .then(res => res.json())
      .then(data => setMarketData(data))
      .catch(err => console.error("Error fetching market data", err))

    fetch(`${API_BASE}/orchestrator/${ticker}`)
      .then(res => res.json())
      .then(data => setOrchestratorData(data))
      .catch(err => console.error("Error fetching orchestrator data", err))
  }, [ticker, activeTab])

  // Fetch Forecast & Render Chart
  useEffect(() => {
    if (activeTab !== 'forecast' || !chartContainerRef.current) return

    setLoadingChart(true)
    if (chartRef.current) {
      chartRef.current.remove()
    }

    const chart = createChart(chartContainerRef.current, {
      layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#8b95a5' },
      grid: { vertLines: { color: 'rgba(255, 255, 255, 0.04)' }, horzLines: { color: 'rgba(255, 255, 255, 0.04)' } },
      crosshair: { mode: 1, vertLine: { color: '#d97706', width: 1, style: 3 }, horzLine: { color: '#d97706', width: 1, style: 3 } },
      timeScale: { timeVisible: true, secondsVisible: false },
    })
    chartRef.current = chart

    const historicalSeries = chart.addCandlestickSeries({
      upColor: '#059669', downColor: '#dc2626', borderVisible: false, wickUpColor: '#059669', wickDownColor: '#dc2626'
    })
    const predictionSeries = chart.addCandlestickSeries({
      upColor: 'rgba(5, 150, 105, 0.4)', downColor: 'rgba(220, 38, 38, 0.4)', borderVisible: true, borderColor: '#2563eb', wickUpColor: 'rgba(5, 150, 105, 0.4)', wickDownColor: 'rgba(220, 38, 38, 0.4)'
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

  // Fetch Earnings & Fundamental Data when tab changes
  useEffect(() => {
    if (activeTab === 'earnings') {
      setLoadingPortEarnings(true)
      fetch(`${API_BASE}/portfolio_earnings`)
        .then(res => res.json())
        .then(data => setPortfolioEarnings(data))
        .catch(err => console.error("Error fetching portfolio earnings", err))
        .finally(() => setLoadingPortEarnings(false))

      fetchTickerEarnings(earningsSearchTicker)
    }
  }, [activeTab])

  const fetchTickerEarnings = (sym) => {
    setLoadingTickerEarnings(true)
    fetch(`${API_BASE}/earnings/${sym}`)
      .then(res => res.json())
      .then(data => setTickerEarningsData(data))
      .catch(err => console.error("Error fetching ticker earnings", err))
      .finally(() => setLoadingTickerEarnings(false))
  }

  return (
    <>
      {/* INTERACTIVE INSTITUTIONAL BUSINESS & EXPANSION MODAL */}
      {selectedModalTicker && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 1000, background: 'rgba(5, 6, 8, 0.85)', backdropFilter: 'blur(5px)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1.5rem' }} onClick={closeTickerModal}>
          <div style={{ background: '#101319', border: '1px solid #2e3543', borderRadius: '6px', width: '100%', maxWidth: '820px', maxHeight: '90vh', overflowY: 'auto', padding: '2rem', position: 'relative', boxShadow: '0 20px 50px rgba(0,0,0,0.8)' }} onClick={e => e.stopPropagation()}>
            <button onClick={closeTickerModal} style={{ position: 'absolute', top: '1.5rem', right: '1.5rem', background: 'transparent', border: 'none', color: '#8b95a5', cursor: 'pointer' }}><X size={22} /></button>
            
            {loadingModal || !modalData ? (
              <div className="loader-container" style={{ minHeight: '300px' }}><div className="spinner" /> Accessing SEC & Aladdin Financial Archives for {selectedModalTicker}...</div>
            ) : (
              <div>
                <div style={{ borderBottom: '2px solid #d97706', paddingBottom: '1rem', marginBottom: '1.5rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <h2 style={{ fontSize: '1.75rem', fontWeight: '800', color: '#fff', fontFamily: 'JetBrains Mono, monospace', display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                      {modalData.name} ({modalData.symbol})
                      <span className="badge badge-purple" style={{ fontSize: '0.75rem' }}>{modalData.sector}</span>
                    </h2>
                    <div style={{ fontSize: '0.85rem', color: '#8b95a5', marginTop: '0.2rem' }}>Industry Classification: {modalData.industry}</div>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1.25rem', marginBottom: '1.5rem' }}>
                  <div style={{ background: '#090b0e', border: '1px solid #1f2532', padding: '1.25rem', borderRadius: '4px' }}>
                    <div style={{ fontSize: '0.75rem', fontWeight: '700', color: '#34d399', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.65rem' }}>🏢 Core Business & Monetized Revenue Products</div>
                    <p style={{ fontSize: '0.88rem', color: '#e2e8f0', lineHeight: '1.6', margin: 0 }}>{modalData.core_business_products}</p>
                  </div>
                  <div style={{ background: '#090b0e', border: '1px solid #1f2532', padding: '1.25rem', borderRadius: '4px' }}>
                    <div style={{ fontSize: '0.75rem', fontWeight: '700', color: '#fbbf24', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.65rem' }}>🚀 Capital Expenditures, R&D & Strategic Expansion</div>
                    <p style={{ fontSize: '0.88rem', color: '#e2e8f0', lineHeight: '1.6', margin: 0 }}>{modalData.expansion_spending}</p>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.85rem', marginBottom: '1.5rem' }}>
                  <div className="stat-card"><div className="stat-label">Trailing P/E</div><div className="stat-value" style={{ fontSize: '1.1rem' }}>{modalData.pe_ratio_trailing !== "N/A" ? `${modalData.pe_ratio_trailing}x` : "N/A"}</div></div>
                  <div className="stat-card"><div className="stat-label">Forward P/E</div><div className="stat-value" style={{ fontSize: '1.1rem', color: '#60a5fa' }}>{modalData.pe_ratio_forward !== "N/A" ? `${modalData.pe_ratio_forward}x` : "N/A"}</div></div>
                  <div className="stat-card"><div className="stat-label">Revenue Growth YoY</div><div className="stat-value" style={{ fontSize: '1.1rem', color: '#10b981' }}>{modalData.revenue_growth_yoy}</div></div>
                  <div className="stat-card"><div className="stat-label">Free Cash Flow</div><div className="stat-value" style={{ fontSize: '1.1rem', color: '#34d399' }}>{modalData.free_cash_flow}</div></div>
                </div>

                <div style={{ background: '#0e1117', borderLeft: '4px solid #2563eb', padding: '1.25rem', borderRadius: '3px' }}>
                  <div style={{ fontSize: '0.75rem', fontWeight: '700', color: '#60a5fa', textTransform: 'uppercase', marginBottom: '0.5rem' }}>📑 Executive Institutional Profile & SEC Summary</div>
                  <p style={{ fontSize: '0.85rem', color: '#cbd5e1', lineHeight: '1.7', margin: 0, maxHeight: '200px', overflowY: 'auto' }}>
                    {modalData.business_summary}
                  </p>
                </div>

                <div style={{ marginTop: '1.5rem', display: 'flex', justifyContent: 'flex-end' }}>
                  <button onClick={closeTickerModal} className="ticker-btn active" style={{ padding: '0.6rem 1.5rem' }}>Close Intelligence Desk</button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      <header className="dashboard-header">
        <div className="brand">
          <Terminal className="brand-icon" />
          BLACKROCK_ALADDIN // KRONOS DESK
        </div>
        
        {/* Institutional Navigation Tabs */}
        <div className="nav-tabs">
          <button className={`nav-tab-btn ${activeTab === 'forecast' ? 'active' : ''}`} onClick={() => setActiveTab('forecast')}>
            <TrendingUp size={15} /> Quant Forecasts & Drivers
          </button>
          <button className={`nav-tab-btn ${activeTab === 'portfolio' ? 'active' : ''}`} onClick={() => setActiveTab('portfolio')}>
            <Briefcase size={15} /> Live Book & Rationale
          </button>
          <button className={`nav-tab-btn ${activeTab === 'earnings' ? 'active' : ''}`} onClick={() => setActiveTab('earnings')}>
            <BarChart3 size={15} /> Earnings & Holdings Intelligence
          </button>
          <button className={`nav-tab-btn ${activeTab === 'macro_ft' ? 'active' : ''}`} onClick={() => setActiveTab('macro_ft')}>
            <Newspaper size={15} /> FT Institutional Macro Desk
          </button>
        </div>

        {activeTab === 'forecast' && (
          <div className="ticker-selector">
            {['PLTR', 'NVDA', 'TSLA', 'GLD', 'SLV', 'SOL-USD'].map(sym => (
              <div key={sym} style={{ display: 'inline-flex', alignItems: 'center', gap: '2px' }}>
                <button className={`ticker-btn ${ticker === sym ? 'active' : ''}`} onClick={() => setTicker(sym)}>
                  {sym}
                </button>
                <button 
                  title="Click to view core business, revenues & CapEx expansion"
                  onClick={() => openTickerModal(sym)} 
                  style={{ background: '#181b22', border: '1px solid #2a313d', borderRadius: '3px', padding: '0.35rem 0.5rem', color: '#fbbf24', cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
                  <Info size={13} />
                </button>
              </div>
            ))}
            <form onSubmit={(e) => { e.preventDefault(); if (searchInput) setTicker(searchInput.toUpperCase()); }}>
              <input type="text" className="search-input" placeholder="Search Symbol..." value={searchInput} onChange={(e) => setSearchInput(e.target.value)} />
            </form>
          </div>
        )}
      </header>

      {/* VIEW 1: QUANT FORECAST & DYNAMIC ORCHESTRATOR OUTPUT */}
      {activeTab === 'forecast' && (
        <main className="dashboard-grid">
          <aside style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', overflowY: 'auto', maxHeight: 'calc(100vh - 90px)' }}>
            <div className="panel">
              <h2 className="panel-title" style={{ color: '#fbbf24', display: 'flex', justifyContent: 'space-between' }}>
                <span><Cpu size={15} /> Aladdin Quant Orchestrator</span>
                <span onClick={() => openTickerModal(ticker)} style={{ cursor: 'pointer', color: '#60a5fa', textTransform: 'none', fontSize: '0.75rem', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                  View Business & CapEx <ExternalLink size={12} />
                </span>
              </h2>
              {orchestratorData ? (
                <>
                  <div className="agent-text">"{orchestratorData.agent_analysis}"</div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                    <div className={`uncertainty-badge uncertainty-${orchestratorData.uncertainty_level.toLowerCase().split('-')[0]}`}>
                      <AlertTriangle size={13} /> {orchestratorData.uncertainty_level} Risk Tier
                    </div>
                    <div style={{ fontSize: '0.75rem', color: '#10b981', fontWeight: '700' }}>Conviction Score: {orchestratorData.sentiment_score}/100</div>
                  </div>

                  <div style={{ marginBottom: '0.85rem' }}>
                    <div style={{ fontSize: '0.75rem', fontWeight: '700', color: '#10b981', textTransform: 'uppercase', marginBottom: '0.4rem' }}>📈 Key Upside Drivers</div>
                    <ul style={{ paddingLeft: '1.1rem', fontSize: '0.8rem', color: '#cbd5e1', lineHeight: '1.5', listStyleType: 'square' }}>
                      {orchestratorData.key_drivers?.map((d, idx) => <li key={idx} style={{ marginBottom: '0.3rem' }}>{d}</li>)}
                    </ul>
                  </div>

                  <div style={{ marginBottom: '0.85rem' }}>
                    <div style={{ fontSize: '0.75rem', fontWeight: '700', color: '#ef4444', textTransform: 'uppercase', marginBottom: '0.4rem' }}>⚠️ Structural & Macro Risks</div>
                    <ul style={{ paddingLeft: '1.1rem', fontSize: '0.8rem', color: '#cbd5e1', lineHeight: '1.5', listStyleType: 'square' }}>
                      {orchestratorData.key_risks?.map((r, idx) => <li key={idx} style={{ marginBottom: '0.3rem' }}>{r}</li>)}
                    </ul>
                  </div>

                  <div style={{ background: '#0a0c0f', padding: '0.75rem', border: '1px solid #22262e', borderRadius: '4px', fontSize: '0.78rem', color: '#94a3b8', cursor: 'pointer' }} onClick={() => openTickerModal(ticker)}>
                    <strong style={{ color: '#fbbf24', display: 'block', marginBottom: '0.25rem', textTransform: 'uppercase', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <span>🏢 Earnings & Corporate Guidance</span>
                      <span style={{ fontSize: '0.65rem', color: '#60a5fa' }}>[Click for Revenues & CapEx Details]</span>
                    </strong>
                    {orchestratorData.earnings_summary}
                  </div>
                </>
              ) : (<div className="loader-container"><div className="spinner" /> Synthesizing Intelligence...</div>)}
            </div>

            <div className="panel">
              <h2 className="panel-title">Institutional Financial Metrics</h2>
              {marketData ? (
                <div className="stats-grid" style={{ gridTemplateColumns: 'repeat(2, 1fr)', display: 'grid' }}>
                  <div className="stat-card">
                    <div className="stat-label">Current Valuation</div>
                    <div className="stat-value">${Number(marketData.current_price).toFixed(2)}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Wall St Consensus</div>
                    <div className="stat-value" style={{ fontSize: '1rem', color: '#10b981' }}>{marketData.analyst_rating}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Trailing P/E Ratio</div>
                    <div className="stat-value" style={{ fontSize: '1.1rem' }}>{marketData.pe_ratio !== "N/A" ? `${marketData.pe_ratio}x` : "N/A"}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Forward P/E Multiple</div>
                    <div className="stat-value" style={{ fontSize: '1.1rem', color: '#60a5fa' }}>{marketData.forward_pe !== "N/A" ? `${marketData.forward_pe}x` : "N/A"}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Free Cash Flow</div>
                    <div className="stat-value" style={{ fontSize: '1.1rem', color: '#34d399' }}>{marketData.free_cash_flow}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Operating Cash Flow</div>
                    <div className="stat-value" style={{ fontSize: '1.1rem' }}>{marketData.operating_cash_flow}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">Revenue YoY Growth</div>
                    <div className="stat-value" style={{ fontSize: '1.1rem', color: '#fbbf24' }}>{marketData.revenue_growth}</div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">EBITDA Reserves</div>
                    <div className="stat-value" style={{ fontSize: '1.1rem' }}>{marketData.ebitda}</div>
                  </div>
                </div>
              ) : (<div className="loader-container"><div className="spinner" /></div>)}
            </div>
          </aside>

          <div className="panel chart-container">
            <h2 className="panel-title" style={{ display: 'flex', justifyContent: 'space-between', width: '100%' }}>
              <span><TrendingUp size={15} /> {ticker} LIVE PRICE ACTION & KRONOS NEURAL FORECAST</span>
            </h2>
            <div className="chart-wrapper" ref={chartContainerRef}>
              {loadingChart && (<div className="loader-container" style={{ position: 'absolute', inset: 0, zIndex: 10, background: 'rgba(10,11,14,0.8)' }}><div className="spinner" /> Running Quantitative Forecast...</div>)}
            </div>
          </div>

          <aside style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', maxHeight: 'calc(100vh - 90px)' }}>
            <div className="panel" style={{ flexGrow: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <h2 className="panel-title"><Activity size={15} /> {ticker} Associated Live News Wire</h2>
              <div className="timeline" style={{ flexGrow: 1 }}>
                {orchestratorData ? (
                  orchestratorData.headlines.map((item, idx) => (
                    <div key={idx} className="timeline-item">
                      <div className="timeline-time">[{item.publisher.toUpperCase()}] • TODAY</div>
                      <div style={{ fontWeight: '600', color: '#e2e8f0' }}>{item.title}</div>
                    </div>
                  ))
                ) : (<div className="loader-container"><div className="spinner" /> Fetching Live Wire...</div>)}
              </div>
            </div>

            {tradeSignal && (
              <div className="panel" style={{ borderLeft: `4px solid ${tradeSignal.type === 'LONG' ? '#059669' : '#dc2626'}` }}>
                <h2 className="panel-title" style={{ color: tradeSignal.type === 'LONG' ? '#10b981' : '#ef4444' }}>
                  <TrendingUp size={15} /> Simulated Institutional Position: {tradeSignal.type}
                </h2>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '0.5rem', fontSize: '0.8rem', marginBottom: '0.5rem' }}>
                  <div className="stat-card"><div className="stat-label">Entry Level</div><div className="stat-value" style={{ fontSize: '1rem' }}>${tradeSignal.entry_price.toFixed(2)}</div></div>
                  <div className="stat-card"><div className="stat-label">Target (TP)</div><div className="stat-value" style={{ fontSize: '1rem', color: '#10b981' }}>${tradeSignal.take_profit.toFixed(2)}</div></div>
                  <div className="stat-card"><div className="stat-label">Protective Floor</div><div className="stat-value" style={{ fontSize: '1rem', color: '#ef4444' }}>${tradeSignal.stop_loss.toFixed(2)}</div></div>
                  <div className="stat-card"><div className="stat-label">Expected Swing</div><div className="stat-value" style={{ fontSize: '1rem', color: '#fbbf24' }}>+{tradeSignal.expected_profit_pct.toFixed(2)}%</div></div>
                </div>
              </div>
            )}
          </aside>
        </main>
      )}

      {/* VIEW 2: LIVE PORTFOLIO & ALGORITHMIC TRADE RATIONALES */}
      {activeTab === 'portfolio' && (
        <div className="portfolio-container">
          {loadingPortfolio || !portfolioData ? (
            <div className="loader-container" style={{ minHeight: '400px' }}><div className="spinner" /> Interrogating Alpaca Real-Time Ledger...</div>
          ) : (
            <>
              <div className="portfolio-overview">
                <div className="stat-card" style={{ borderLeft: '3px solid #059669' }}>
                  <div className="stat-label"><DollarSign size={13} style={{ display: 'inline' }} /> Total Account Equity</div>
                  <div className="stat-value">${portfolioData.account?.equity.toLocaleString() || '100,000'}</div>
                </div>
                <div className="stat-card" style={{ borderLeft: '3px solid #2563eb' }}>
                  <div className="stat-label"><ShieldCheck size={13} style={{ display: 'inline' }} /> Available Buying Power</div>
                  <div className="stat-value">${portfolioData.account?.buying_power.toLocaleString() || '--'}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Unencumbered Cash Reserves</div>
                  <div className="stat-value">${portfolioData.account?.cash.toLocaleString() || '--'}</div>
                </div>
                <div className="stat-card">
                  <div className="stat-label">Net Gain vs Initial Baseline</div>
                  <div className="stat-value" style={{ color: (portfolioData.account?.day_change >= 0) ? '#10b981' : '#ef4444' }}>
                    {portfolioData.account?.day_change >= 0 ? '+' : ''}${portfolioData.account?.day_change || 0}
                  </div>
                </div>
              </div>

              <h2 className="panel-title" style={{ marginTop: '0.5rem' }}>
                <Layers size={16} style={{ display: 'inline' }} /> Active Holdings & Algorithmic Rationale (Click Symbol for Business & Revenue Desk)
              </h2>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {portfolioData.positions?.length === 0 ? (
                  <div className="panel" style={{ textAlign: 'center', padding: '3rem', color: '#8b95a5' }}>
                    No open positions at this instant. Kronos quantitative engines are awaiting macro conviction clearance (Score &gt;= 2.0).
                  </div>
                ) : (
                  portfolioData.positions?.map((pos, idx) => (
                    <div key={idx} className={`trade-card ${pos.pnl_usd >= 0 ? 'win' : 'loss'}`}>
                      <div className="trade-header">
                        <div className="trade-title">
                          <span onClick={() => openTickerModal(pos.symbol)} style={{ cursor: 'pointer', textDecoration: 'underline', color: '#fbbf24' }} title="Click for Business & CapEx Report">
                            {pos.symbol}
                          </span>
                          <span className="badge badge-blue">{pos.asset_class}</span>
                          <span className="badge badge-purple">{pos.status_badge}</span>
                        </div>
                        <div style={{ fontWeight: '700', fontSize: '1.15rem', color: pos.pnl_usd >= 0 ? '#10b981' : '#ef4444', fontFamily: 'JetBrains Mono, monospace' }}>
                          {pos.pnl_usd >= 0 ? '+' : ''}${pos.pnl_usd} ({pos.pnl_pct >= 0 ? '+' : ''}{pos.pnl_pct}%)
                        </div>
                      </div>
                      
                      <div className="trade-metrics">
                        <div><div className="stat-label">Quantity Held</div><div style={{ fontWeight: '600', color: '#fff', fontFamily: 'monospace' }}>{pos.qty}</div></div>
                        <div><div className="stat-label">Avg Entry Price</div><div style={{ fontWeight: '600', color: '#fff', fontFamily: 'monospace' }}>${pos.entry_price}</div></div>
                        <div><div className="stat-label">Current Valuation</div><div style={{ fontWeight: '600', color: '#fff', fontFamily: 'monospace' }}>${pos.current_price}</div></div>
                        <div><div className="stat-label">Position Notional</div><div style={{ fontWeight: '600', color: '#fff', fontFamily: 'monospace' }}>${pos.market_value}</div></div>
                        <div><div className="stat-label">Active Stop Protection</div><div style={{ fontWeight: '700', color: '#fbbf24' }}>{pos.stop_tier}</div></div>
                      </div>

                      <div className="rationale-box">
                        <div className="rationale-title"><Cpu size={13} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '5px' }} /> Quantitative & Macro Entry Rationale</div>
                        <p style={{ fontSize: '0.85rem', color: '#cbd5e1', lineHeight: '1.6', margin: 0 }}>{pos.rationale}</p>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* VIEW 3: EARNINGS & FUNDAMENTALS INTELLIGENCE DESK */}
      {activeTab === 'earnings' && (
        <div className="portfolio-container">
          {/* Universal Earnings Ticker Search Box */}
          <div className="panel" style={{ borderTop: '3px solid #2563eb' }}>
            <h2 className="panel-title" style={{ color: '#60a5fa' }}><Search size={16} /> Global Universal Ticker Earnings & Financial Guidance Desk</h2>
            <form onSubmit={(e) => { e.preventDefault(); if (earningsSearchTicker) fetchTickerEarnings(earningsSearchTicker.toUpperCase()); }} style={{ display: 'flex', gap: '1rem', alignItems: 'center', marginBottom: '1.25rem' }}>
              <input 
                type="text" 
                className="search-input" 
                style={{ width: '320px', padding: '0.6rem 1rem', fontSize: '0.9rem' }}
                placeholder="Enter Ticker (e.g. NVDA, TSLA, AAPL, PLTR)..." 
                value={earningsSearchTicker} 
                onChange={(e) => setEarningsSearchTicker(e.target.value)} 
              />
              <button type="submit" className="ticker-btn active" style={{ padding: '0.6rem 1.5rem', fontSize: '0.9rem' }}>Query Aladdin Engine</button>
              {tickerEarningsData && (
                <button type="button" onClick={() => openTickerModal(earningsSearchTicker)} className="ticker-btn" style={{ padding: '0.6rem 1.2rem', borderColor: '#fbbf24', color: '#fbbf24' }}>
                  📑 Open Full Business & Expansion Modal
                </button>
              )}
            </form>

            {loadingTickerEarnings || !tickerEarningsData ? (
              <div className="loader-container" style={{ minHeight: '200px' }}><div className="spinner" /> Extracting SEC & Wall Street Earnings Consensus...</div>
            ) : (
              <div style={{ background: '#0d0f13', padding: '1.5rem', border: '1px solid #22262e', borderRadius: '4px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid #22262e', paddingBottom: '1rem', marginBottom: '1.25rem' }}>
                  <div>
                    <h3 onClick={() => openTickerModal(tickerEarningsData.symbol)} style={{ fontSize: '1.4rem', fontWeight: '800', color: '#fff', cursor: 'pointer', textDecoration: 'underline' }} title="Click to launch Business & CapEx desk">
                      {tickerEarningsData.name} ({tickerEarningsData.symbol}) <ExternalLink size={15} style={{ display: 'inline', color: '#fbbf24' }} />
                    </h3>
                    <div style={{ fontSize: '0.8rem', color: '#fbbf24', fontWeight: '600', marginTop: '0.2rem' }}>{tickerEarningsData.sector} | {tickerEarningsData.industry}</div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div className="stat-label">Next Scheduled Earnings Call</div>
                    <div style={{ fontSize: '1.1rem', fontWeight: '700', color: '#10b981', fontFamily: 'monospace' }}>📅 {tickerEarningsData.next_earnings_date}</div>
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1.25rem', marginBottom: '1.5rem' }}>
                  <div className="stat-card"><div className="stat-label">Trailing P/E Ratio</div><div className="stat-value" style={{ fontSize: '1.2rem' }}>{tickerEarningsData.pe_ratio_trailing !== "N/A" ? `${tickerEarningsData.pe_ratio_trailing}x` : "N/A"}</div></div>
                  <div className="stat-card"><div className="stat-label">Forward P/E Multiple</div><div className="stat-value" style={{ fontSize: '1.2rem', color: '#60a5fa' }}>{tickerEarningsData.pe_ratio_forward !== "N/A" ? `${tickerEarningsData.pe_ratio_forward}x` : "N/A"}</div></div>
                  <div className="stat-card"><div className="stat-label">Revenue Growth YoY</div><div className="stat-value" style={{ fontSize: '1.2rem', color: '#10b981' }}>{tickerEarningsData.revenue_growth_yoy}</div></div>
                  <div className="stat-card"><div className="stat-label">Analyst Rating Consensus</div><div className="stat-value" style={{ fontSize: '1.2rem', color: '#fbbf24' }}>{tickerEarningsData.analyst_consensus_rating}</div></div>
                  <div className="stat-card"><div className="stat-label">Operating Cash Flow</div><div className="stat-value" style={{ fontSize: '1.1rem' }}>{tickerEarningsData.operating_cash_flow}</div></div>
                  <div className="stat-card"><div className="stat-label">Free Cash Flow</div><div className="stat-value" style={{ fontSize: '1.1rem', color: '#34d399' }}>{tickerEarningsData.free_cash_flow}</div></div>
                  <div className="stat-card"><div className="stat-label">Gross Profit Margin</div><div className="stat-value" style={{ fontSize: '1.1rem' }}>{tickerEarningsData.gross_margin}</div></div>
                  <div className="stat-card"><div className="stat-label">Net Profit Margin</div><div className="stat-value" style={{ fontSize: '1.1rem' }}>{tickerEarningsData.profit_margin}</div></div>
                </div>

                <div style={{ fontSize: '0.85rem', color: '#cbd5e1', lineHeight: '1.6', borderTop: '1px solid #22262e', paddingTop: '1rem' }}>
                  <div style={{ fontWeight: '700', color: '#fbbf24', textTransform: 'uppercase', marginBottom: '0.5rem', fontSize: '0.75rem' }}>📑 Institutional Business & Earnings Summary</div>
                  {tickerEarningsData.business_summary}
                </div>
              </div>
            )}
          </div>

          {/* Active Portfolio Holdings Earnings & Guidance Section */}
          <div className="panel" style={{ borderTop: '3px solid #059669' }}>
            <h2 className="panel-title" style={{ color: '#34d399' }}><FileText size={16} /> My Active Portfolio Holdings: Earnings Reports & Financial Intelligence (Click Symbol for Business & Revenue Desk)</h2>
            
            {loadingPortEarnings || !portfolioEarnings ? (
              <div className="loader-container" style={{ minHeight: '200px' }}><div className="spinner" /> Pulling Live Alpaca Book Earnings Profiles...</div>
            ) : portfolioEarnings.holdings?.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '2rem', color: '#8b95a5', fontSize: '0.9rem' }}>
                No active stock holdings in live book right now. As orders execute, their detailed earnings schedules, guidance, and valuations appear here automatically.
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1.25rem', marginTop: '0.5rem' }}>
                {portfolioEarnings.holdings.map((h, idx) => (
                  <div key={idx} className="trade-card" style={{ borderLeftColor: '#059669', background: '#0e1015' }}>
                    <div className="trade-header">
                      <div onClick={() => openTickerModal(h.symbol)} style={{ fontWeight: '800', fontSize: '1.15rem', color: '#fbbf24', fontFamily: 'JetBrains Mono, monospace', cursor: 'pointer', textDecoration: 'underline' }} title="Click for Business & CapEx Report">
                        {h.symbol} <span style={{ fontSize: '0.85rem', color: '#94a3b8', fontWeight: '600' }}>({h.name})</span>
                      </div>
                      <span className="badge badge-green">{h.sector}</span>
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '0.5rem', fontSize: '0.8rem', background: '#13161d', padding: '0.75rem', borderRadius: '4px', fontFamily: 'monospace' }}>
                      <div><div className="stat-label">Next Earnings</div><div style={{ fontWeight: '700', color: '#fbbf24' }}>{h.next_earnings_date}</div></div>
                      <div><div className="stat-label">Forward P/E</div><div style={{ fontWeight: '700', color: '#60a5fa' }}>{h.forward_pe !== "N/A" ? `${h.forward_pe}x` : "N/A"}</div></div>
                      <div><div className="stat-label">Rev Growth YoY</div><div style={{ fontWeight: '700', color: '#34d399' }}>{h.revenue_growth_yoy}</div></div>
                    </div>

                    <div style={{ fontSize: '0.82rem', color: '#cbd5e1', lineHeight: '1.5', background: '#090a0d', padding: '0.8rem', border: '1px solid #1e222b', borderRadius: '3px', cursor: 'pointer' }} onClick={() => openTickerModal(h.symbol)}>
                      <strong style={{ color: '#06b6d4', display: 'block', marginBottom: '0.2rem', textTransform: 'uppercase', fontSize: '0.7rem', display: 'flex', justifyContent: 'space-between' }}>
                        <span>Aladdin Holding Synthesis</span>
                        <span style={{ color: '#fbbf24' }}>[Click for Core Business & Revenues]</span>
                      </strong>
                      {h.earnings_synthesis}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* VIEW 4: FINANCIAL TIMES (FT) INSTITUTIONAL MACRO RUNDOWN */}
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

              <div className="ft-lead">
                <div className="ft-lead-text">
                  <h2>{ftData.lead_story?.headline}</h2>
                  <h3>{ftData.lead_story?.sub_headline}</h3>
                  <p>{ftData.lead_story?.article_p1}</p>
                  <p>{ftData.lead_story?.article_p2}</p>
                  <div style={{ fontStyle: 'italic', fontSize: '0.85rem', color: '#8b95a5', marginTop: '1rem' }}>{ftData.lead_story?.author}</div>
                </div>
                
                <div className="panel" style={{ border: '1px solid #d97706', background: '#0e1117' }}>
                  <h3 style={{ color: '#fbbf24', borderBottom: '1px solid #282e3a', paddingBottom: '0.6rem', marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.95rem', textTransform: 'uppercase' }}>
                    <Globe size={16} /> Central Bank Policy Tracker
                  </h3>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', fontSize: '0.85rem' }}>
                    <div>
                      <div style={{ fontWeight: '700', color: '#fff', display: 'flex', justifyContent: 'space-between' }}><span>Federal Reserve (USD)</span><span style={{ color: '#60a5fa', fontFamily: 'monospace' }}>{ftData.central_bank_tracker?.fed.rate}</span></div>
                      <div style={{ color: '#cbd5e1' }}>Outlook: {ftData.central_bank_tracker?.fed.outlook}</div>
                      <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.2rem' }}>Next FOMC: {ftData.central_bank_tracker?.fed.next_decision}</div>
                    </div>
                    <div style={{ borderTop: '1px solid #22262e', paddingTop: '0.75rem' }}>
                      <div style={{ fontWeight: '700', color: '#fff', display: 'flex', justifyContent: 'space-between' }}><span>ECB Europe (EUR)</span><span style={{ color: '#60a5fa', fontFamily: 'monospace' }}>{ftData.central_bank_tracker?.ecb.rate}</span></div>
                      <div style={{ color: '#cbd5e1' }}>Outlook: {ftData.central_bank_tracker?.ecb.outlook}</div>
                      <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.2rem' }}>Next Decision: {ftData.central_bank_tracker?.ecb.next_decision}</div>
                    </div>
                    <div style={{ borderTop: '1px solid #22262e', paddingTop: '0.75rem' }}>
                      <div style={{ fontWeight: '700', color: '#fff', display: 'flex', justifyContent: 'space-between' }}><span>Bank of England (GBP)</span><span style={{ color: '#60a5fa', fontFamily: 'monospace' }}>{ftData.central_bank_tracker?.boe.rate}</span></div>
                      <div style={{ color: '#cbd5e1' }}>Outlook: {ftData.central_bank_tracker?.boe.outlook}</div>
                      <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '0.2rem' }}>Next Decision: {ftData.central_bank_tracker?.boe.next_decision}</div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="ft-columns">
                {ftData.sector_columns?.map((col, i) => (
                  <div key={i} className="ft-col-card">
                    <div className="ft-col-title">{col.sector_name}</div>
                    <div className="ft-col-body">{col.summary}</div>
                  </div>
                ))}
              </div>

              <div>
                <h3 style={{ fontSize: '1.15rem', fontFamily: 'Georgia, serif', color: '#fbbf24', borderBottom: '1px solid #22262e', paddingBottom: '0.6rem', marginTop: '0.5rem' }}>
                  📅 Global High-Impact Economic Events (ForexFactory Institutional Ledger)
                </h3>
                <div className="ft-calendar-grid">
                  {ftData.macro_calendar?.map((ev, i) => (
                    <div key={i} className="macro-card">
                      <div className="macro-card-top">
                        <span style={{ fontWeight: '700', color: ev.country === 'USD' ? '#38bdf8' : '#e879f9' }}>[{ev.country}] {ev.time}</span>
                        <span style={{ color: ev.impact === 'High' ? '#ef4444' : '#fbbf24', fontWeight: '700' }}>{ev.impact.toUpperCase()} IMPACT</span>
                      </div>
                      <div className="macro-card-title">{ev.title}</div>
                      <div className="macro-nums">
                        <div><div style={{ fontSize: '0.65rem', color: '#8b95a5' }}>ACTUAL</div><div style={{ fontWeight: '700', color: '#10b981' }}>{ev.actual}</div></div>
                        <div><div style={{ fontSize: '0.65rem', color: '#8b95a5' }}>FORECAST</div><div style={{ fontWeight: '700', color: '#fff' }}>{ev.forecast}</div></div>
                        <div><div style={{ fontSize: '0.65rem', color: '#8b95a5' }}>PREVIOUS</div><div style={{ color: '#cbd5e1' }}>{ev.previous}</div></div>
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
