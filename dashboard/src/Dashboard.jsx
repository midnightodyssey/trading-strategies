import { useState, useEffect, useCallback, useRef } from "react";

// â”€â”€â”€ IMMUTABLE CONSTANTS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const PHASES = [
  { id: "foundation", label: "Foundation",     icon: "â—ˆ", color: "#E8B96A", description: "Market structure, order flow, reading price" },
  { id: "framework",  label: "Code Framework", icon: "â¬¡", color: "#6DB8D8", description: "Python library, backtesting engine, indicators" },
  { id: "strategies", label: "Strategies",     icon: "â—‰", color: "#7DC87A", description: "Signal models, risk systems & optimisation" },
  { id: "mastery",    label: "Mastery",         icon: "âœ¦", color: "#B89FD8", description: "Prop firm challenge, live trading & edge refinement", locked: true },
];

const MODULES = {
  foundation: [
    { id: "structure", label: "Market Structure",     color: "#E8B96A", items: ["HH / HL / LH / LL Identification", "CHoCH & BOS Patterns", "Premium / Discount Zones", "Liquidity Pool Mapping"] },
    { id: "orderflow", label: "Order Flow Analysis",  color: "#E8B96A", items: ["Delta & Cumulative Delta (CVD)", "Footprint Chart Reading", "Volume Imbalances & Stacked Imbalances", "Absorption & Exhaustion Patterns"] },
    { id: "vwap",      label: "VWAP & Volume Profile", color: "#E8B96A", items: ["Anchored VWAP", "Value Area High / Low / POC", "High & Low Volume Nodes", "VWAP Standard Deviation Bands"] },
    { id: "psych_f",   label: "Trading Psychology",   color: "#E8B96A", items: ["Probabilistic Mindset (Douglas)", "Emotional Control Framework", "Pre-Trade Routine & Checklist", "Post-Trade Review Process"] },
  ],
  framework: [
    { id: "indicators", label: "Indicators",         color: "#6DB8D8", items: ["SMA", "EMA", "WMA", "RSI", "MACD", "Bollinger Bands", "ATR"] },
    { id: "backtest",   label: "Backtesting Engine", color: "#6DB8D8", items: ["Vectorised Engine Core", "BacktestResult Class", "Slippage & Commission Model", "Multi-Asset Portfolio", "Walk-Forward Validation"] },
    { id: "risk",       label: "Risk Models",        color: "#6DB8D8", items: ["Sharpe Ratio", "Sortino Ratio", "Max Drawdown", "Calmar Ratio", "VaR (Parametric)", "CVaR (Expected Shortfall)"] },
    { id: "data",       label: "Data Pipeline",      color: "#6DB8D8", items: ["Historical Data Acquisition (yfinance / Quandl)", "Real-Time Feed Integration", "Data Cleaning & Normalisation", "Feature Engineering Pipeline"] },
    { id: "execution",  label: "Execution Layer",    color: "#6DB8D8", items: ["Broker API Integration", "Order Management System", "Live P&L Tracking"] },
  ],
  strategies: [
    { id: "strat_class", label: "Strategy Classes",       color: "#7DC87A", items: ["Base Strategy Class", "SMA Crossover", "Mean Reversion", "Momentum (12/1)", "Breakout / Range Expansion"] },
    { id: "tech_strat",  label: "Technical Strategies",   color: "#7DC87A", items: ["EMA Trend Following", "RSI Mean Reversion", "MACD Divergence", "Multi-Timeframe Confluence"] },
    { id: "portfolio",   label: "Portfolio Construction", color: "#7DC87A", items: ["Mean-Variance Optimisation", "Risk Parity", "Kelly Criterion Sizing", "Correlation & Diversification"] },
    { id: "stat_edge",   label: "Statistical Edge",       color: "#7DC87A", items: ["Hypothesis Testing (T-Test, Permutation)", "Monte Carlo Simulation", "Market Regime Detection", "Factor Analysis"] },
  ],
  mastery: [
    { id: "live_exec",  label: "Prop Firm & Live",     color: "#B89FD8", items: ["Paper Trading â€” 30 Days (prop firm rules)", "Pass Challenge Phase", "Pass Verification Phase", "Funded Live Execution", "Real-Time Risk Monitoring"] },
    { id: "adv_models", label: "Advanced Models",      color: "#B89FD8", items: ["ML Signal Generation", "NLP Sentiment Analysis", "Options Pricing Models", "High-Frequency Considerations"] },
    { id: "edge",       label: "Edge Refinement",      color: "#B89FD8", items: ["Strategy Decay Detection", "Market Regime Adaptation", "Continuous Improvement Loop"] },
    { id: "pro",        label: "Professional Practice", color: "#B89FD8", items: ["Regulatory & Compliance Basics", "Fund Structure Understanding", "Performance Attribution", "Investor Reporting"] },
  ],
};

// base = institutional starting level (1â€“10); modules = which completions drive the bar
const SKILL_MODULE_MAP = [
  { name: "Technical Analysis",    color: "#E8B96A", base: 3, modules: ["structure", "orderflow", "vwap", "tech_strat"] },
  { name: "Quantitative & Coding", color: "#6DB8D8", base: 5, modules: ["indicators", "backtest", "data", "strat_class", "stat_edge"] },
  { name: "Risk Management",       color: "#7DC87A", base: 7, modules: ["risk", "portfolio"] },
  { name: "Trading Psychology",    color: "#E87A7A", base: 2, modules: ["psych_f"] },
  { name: "Market Knowledge",      color: "#B89FD8", base: 6, modules: ["structure", "orderflow", "vwap", "tech_strat", "portfolio"] },
  { name: "Execution & Process",   color: "#E8A86A", base: 4, modules: ["execution", "live_exec"] },
];

const ALL_MODULES = Object.values(MODULES).flat();

function computeSkillLevel(skill, completions) {
  const mods  = ALL_MODULES.filter(m => skill.modules.includes(m.id));
  const total = mods.reduce((s, m) => s + m.items.length, 0);
  const done  = mods.reduce((s, m) => s + (completions[m.id] || []).filter(Boolean).length, 0);
  const pct   = total > 0 ? done / total : 0;
  return Math.max(1, Math.round(skill.base + pct * (10 - skill.base)));
}

const BOOK_DEFS = [
  { title: "Market Wizards",                              author: "Jack Schwager",          category: "Psychology" },
  { title: "Trading in the Zone",                         author: "Mark Douglas",           category: "Psychology" },
  { title: "Reminiscences of a Stock Operator",           author: "Edwin LefÃ¨vre",          category: "Psychology" },
  { title: "Technical Analysis of the Financial Markets", author: "John J. Murphy",         category: "Technical"  },
  { title: "Algorithmic Trading",                         author: "Ernest Chan",            category: "Quant"      },
  { title: "Advances in Financial Machine Learning",      author: "Marcos Lopez de Prado",  category: "Quant"      },
  { title: "Quantitative Trading",                        author: "Ernest Chan",            category: "Quant"      },
  { title: "The Man Who Solved the Market",               author: "Gregory Zuckerman",      category: "Psychology" },
  { title: "Evidence-Based Technical Analysis",           author: "David Aronson",          category: "Technical"  },
  { title: "Options, Futures & Other Derivatives",        author: "John C. Hull",           category: "Technical"  },
];

const VIDEO_CAT_DEFS = [
  { label: "Order Flow & Price Action", color: "#E8B96A" },
  { label: "Quant / Systematic",        color: "#6DB8D8" },
  { label: "Risk & Portfolio",          color: "#7DC87A" },
  { label: "Market Microstructure",     color: "#B89FD8" },
  { label: "Psychology & Process",      color: "#E8876A" },
];

const TARGET_DEFS = [
  { metric: "Sharpe Ratio",      target: 1.5,  unit: "",    higher: true  },
  { metric: "Max Drawdown",      target: 10,   unit: "%",   higher: false },
  { metric: "Win Rate",          target: 55,   unit: "%",   higher: true  },
  { metric: "Avg Risk / Reward", target: 2.0,  unit: "x",   higher: true  },
  { metric: "Backtest History",  target: 10,   unit: " yr", higher: true  },
];

const MILESTONE_DEFS = [
  { label: "Indicators Library Complete",            color: "#7DC87A" },
  { label: "Risk Model Suite Complete",              color: "#7DC87A" },
  { label: "Backtesting Engine v1",                  color: "#6DB8D8" },
  { label: "First Strategy Backtest (10-yr data)",   color: "#6DB8D8" },
  { label: "Paper Trading â€” 30-Day Structured Trial", color: "#E8B96A" },
  { label: "Pass Prop Firm Challenge Phase",         color: "#B89FD8" },
  { label: "Pass Prop Firm Verification",            color: "#B89FD8" },
  { label: "First Funded Payout",                    color: "#B89FD8" },
];

const NEXT_ACTIONS = [
  { priority: "HIGH", text: "Build walk-forward validation â€” your risk/stats background makes this achievable now" },
  { priority: "HIGH", text: "Codify your institutional edge: translate put-spread hedging logic into a systematic options screener" },
  { priority: "HIGH", text: "Paper trade with prop firm rules (1% risk/trade, 4% daily DD, 10% max DD) â€” apply the same discipline you used on the PM desk" },
  { priority: "MED",  text: "Read Trading in the Zone ch. 4â€“8 â€” psychology is your lowest-rated skill and the hardest to develop" },
  { priority: "MED",  text: "Implement Greeks (Delta, Gamma, Vega, Theta) in Python â€” you know the theory, now automate it" },
  { priority: "MED",  text: "Research prop firm evaluations that suit systematic/quant traders (FTMO, Topstep, Apex Trader)" },
  { priority: "LOW",  text: "Build a market regime detector â€” leverage your multi-asset PM exposure to identify trend vs. mean-reversion environments" },
];

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

// â”€â”€â”€ MARKDOWN RENDERER â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const DOC_CATEGORY_COLOR = {
  Framework:  "#6DB8D8",   // blue   - core engine (backtest, data, indicators)
  Strategies: "#7DC87A",   // green  - strategy implementations
  Risk:       "#E87A7A",   // red    - risk metrics & position sizing
  Execution:  "#B89FD8",   // purple - OMS, broker, live trading
  Analysis:   "#E8A86A",   // orange - stat edge, portfolio tools
  Automation: "#5FC9A6",   // teal   - job orchestration, scheduling, operations
  Reference:  "#8896A8",   // grey   - uncategorised
};

const DOC_CATEGORY_ORDER = ["Framework", "Strategies", "Risk", "Execution", "Analysis", "Automation", "Reference"];

function MarkdownDoc({ content }) {
  const lines = content.split("\n");
  const els = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    // fenced code block
    if (line.startsWith("```")) {
      const lang = line.slice(3).trim();
      const codeLines = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      els.push(
        <pre key={i} style={{ background: "#060A12", border: "1px solid #1E2535", borderRadius: 6,
          padding: "10px 14px", margin: "8px 0 14px", overflowX: "auto",
          fontFamily: "monospace", fontSize: 11, color: "#7DC87A", lineHeight: 1.6 }}>
          {lang && <div style={{ fontSize: 9, color: "#3A4A5A", letterSpacing: "0.12em", marginBottom: 6 }}>{lang.toUpperCase()}</div>}
          {codeLines.join("\n")}
        </pre>
      );
      i++; continue;
    }
    // h1
    if (line.startsWith("# ")) {
      els.push(<h1 key={i} style={{ fontFamily: "'Playfair Display', serif", fontSize: 20, color: "#F0F2F8",
        fontWeight: 600, margin: "0 0 4px" }}>{line.slice(2)}</h1>);
      i++; continue;
    }
    // h2
    if (line.startsWith("## ")) {
      els.push(<h2 key={i} style={{ fontSize: 14, color: "#E8B96A", fontWeight: 700,
        margin: "18px 0 8px", letterSpacing: "0.04em" }}>{line.slice(3)}</h2>);
      i++; continue;
    }
    // h3
    if (line.startsWith("### ")) {
      els.push(<h3 key={i} style={{ fontSize: 12, color: "#A0AABA", fontWeight: 700,
        margin: "12px 0 6px", letterSpacing: "0.03em" }}>{line.slice(4)}</h3>);
      i++; continue;
    }
    // hr
    if (line.startsWith("---")) {
      els.push(<hr key={i} style={{ border: "none", borderTop: "1px solid #1E2535", margin: "16px 0" }} />);
      i++; continue;
    }
    // bullet list item
    if (line.startsWith("- ")) {
      const items = [];
      while (i < lines.length && lines[i].startsWith("- ")) {
        items.push(lines[i].slice(2));
        i++;
      }
      els.push(
        <ul key={i} style={{ margin: "4px 0 10px", paddingLeft: 18, listStyle: "none" }}>
          {items.map((item, j) => (
            <li key={j} style={{ fontSize: 12, color: "#8896A8", lineHeight: 1.6, marginBottom: 3,
              display: "flex", gap: 8, alignItems: "flex-start" }}>
              <span style={{ color: "#3A4A5A", flexShrink: 0 }}>â€º</span>
              <InlineMarkdown text={item} />
            </li>
          ))}
        </ul>
      );
      continue;
    }
    // blank line
    if (line.trim() === "") { i++; continue; }
    // italic metadata line (*Source: ...*)
    if (line.startsWith("*") && line.endsWith("*")) {
      els.push(<div key={i} style={{ fontSize: 10, color: "#3A4A5A", fontStyle: "italic",
        marginBottom: 3 }}>{line.slice(1, -1)}</div>);
      i++; continue;
    }
    // paragraph
    els.push(<p key={i} style={{ fontSize: 12, color: "#8896A8", lineHeight: 1.7, margin: "0 0 8px" }}>
      <InlineMarkdown text={line} />
    </p>);
    i++;
  }
  return <div>{els}</div>;
}

function InlineMarkdown({ text }) {
  // handle **bold**, `code`, and plain text
  const parts = text.split(/(\[[^\]]+\]\([^\)]+\)|`[^`]+`|\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((part, i) => {
        if (part.startsWith("**") && part.endsWith("**"))
          return <strong key={i} style={{ color: "#CDD5E0", fontWeight: 700 }}>{part.slice(2, -2)}</strong>;
        if (part.startsWith("`") && part.endsWith("`"))
          return <code key={i} style={{ background: "#060A12", color: "#7DC87A", fontFamily: "monospace",
            fontSize: 11, padding: "1px 5px", borderRadius: 3 }}>{part.slice(1, -1)}</code>;
        const linkMatch = part.match(/^\[([^\]]+)\]\(([^\)]+)\)$/);
        if (linkMatch) {
          const label = linkMatch[1];
          const href = linkMatch[2];
          return <a key={i} href={href} target="_blank" rel="noreferrer" style={{ color: "#6DB8D8", textDecoration: "underline" }}>{label}</a>;
        }
        return part;
      })}
    </>
  );
}

// â”€â”€â”€ DEFAULT STATE â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

const DEFAULT_STATE = {
  completions: {
    // â”€â”€ Post-quiz calibration (Mar 2026) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    // All items reflect actual tested knowledge â€” institutional background
    // provides context and accelerates learning, but does not substitute
    // for systematic study of each framework item below.
    structure:   [false, false, false, false],   // Q1â€“Q4: HH/HL, CHoCH/BOS, Premium/Discount, Liquidity Pools â€” all incomplete
    orderflow:   [false, false, false, false],   // Q5â€“Q8: CVD, Footprint, Imbalances, Absorption â€” all incomplete
    vwap:        [false, false, false, false],   // Q9â€“Q12: Anchored VWAP, VAH/VAL/POC, Nodes, SD Bands â€” all incomplete
    psych_f:     [false, false, false, false],   // Q13â€“Q16: Douglas mindset, Emotional control, Routine, Review â€” all incomplete
    indicators:  [false, false, false, false, false, false, false],  // Q17â€“Q23: SMA/EMA/WMA/RSI/MACD/BB/ATR â€” all incomplete
    backtest:    [false, false, false, false, false],  // Q24â€“Q28: Engine, Result class, Slippage, Multi-asset, Walk-forward â€” incomplete
    risk:        [false, false, false, false, false, false],   // Q29â€“Q34: Sharpe/Sortino/MDD/Calmar/VaR/CVaR â€” all incomplete
    data:        [false, false, false, false],   // Q35â€“Q38: Acquisition, Real-time, Cleaning, Feature engineering â€” incomplete
    execution:   [false, false, false],          // Q39â€“Q41: Broker API, OMS, Live P&L â€” all incomplete
    strat_class: [false, false, false, false, false],  // Q42â€“Q46: Base class, SMA cross, Mean rev, Momentum, Breakout â€” incomplete
    tech_strat:  [false, false, false, false],   // Q47â€“Q50: EMA trend, RSI MR, MACD div, MTF confluence â€” incomplete
    portfolio:   [false, false, false, false],   // Q51â€“Q54: MVO, Risk Parity, Kelly, Correlation â€” incomplete
    stat_edge:   [false, false, false, false],   // Q55â€“Q58: Hypothesis test, Monte Carlo, Regime, Factor analysis â€” incomplete
    // Mastery â€” not started
    live_exec:   [false, false, false, false, false],
    adv_models:  [false, false, false, false],
    edge:        [false, false, false],
    pro:         [false, false, false, false],
  },
  skills: {
    // Recalibrated: 3yr institutional background (options desk, multi-asset PM, equities financing)
    "Technical Analysis":    5,   // Research desk exposure; not systematic TA, but not a beginner
    "Quantitative & Coding": 6,   // Intermediate Python â€” correct
    "Risk Management":       8,   // Ran hedge book & exposure mgmt for pension fund clients
    "Trading Psychology":    2,   // Self-rated weakest â€” correct
    "Market Knowledge":      8,   // Multi-asset: equities, options, FX, futures, credit, equities financing
    "Execution & Process":   5,   // Supported real institutional execution; understands OMS/process
  },
  books: {
    "Market Wizards":                              "reading",
    "Trading in the Zone":                         "reading",
    "Reminiscences of a Stock Operator":           "unread",
    "Technical Analysis of the Financial Markets": "unread",
    "Algorithmic Trading":                         "read",
    "Advances in Financial Machine Learning":      "reading",
    "Quantitative Trading":                        "read",
    "The Man Who Solved the Market":               "unread",
    "Evidence-Based Technical Analysis":           "unread",
    "Options, Futures & Other Derivatives":        "read",   // Worked with put spreads on options desk
  },
  activity:   { Mon: 3, Tue: 7, Wed: 5, Thu: 9, Fri: 4, Sat: 8, Sun: 6 },
  targets:    { "Sharpe Ratio": 0.8, "Max Drawdown": 22, "Win Rate": 48, "Avg Risk / Reward": 1.4, "Backtest History": 3 },
  videos:     { "Order Flow & Price Action": 8, "Quant / Systematic": 7, "Risk & Portfolio": 5, "Market Microstructure": 4, "Psychology & Process": 3 },
  milestones: [true, true, false, false, false, false, false, false],
};

function loadState() {
  try {
    const raw = localStorage.getItem("trading-career-v4");
    if (!raw) return DEFAULT_STATE;
    const saved = JSON.parse(raw);
    return {
      ...DEFAULT_STATE,
      ...saved,
      completions: { ...DEFAULT_STATE.completions, ...saved.completions },
      skills:      { ...DEFAULT_STATE.skills,      ...saved.skills      },
      books:       { ...DEFAULT_STATE.books,        ...saved.books       },
      activity:    { ...DEFAULT_STATE.activity,     ...saved.activity    },
      targets:     { ...DEFAULT_STATE.targets,      ...saved.targets     },
      videos:      { ...DEFAULT_STATE.videos,        ...saved.videos      },
    };
  } catch { return DEFAULT_STATE; }
}

// â”€â”€â”€ SMALL COMPONENTS â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

function Ring({ pct, color, size = 52, stroke = 4 }) {
  const r    = (size - stroke * 2) / 2;
  const circ = 2 * Math.PI * r;
  const dash = (pct / 100) * circ;
  return (
    <svg width={size} height={size} style={{ transform: "rotate(-90deg)", display: "block" }}>
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="#252D3D" strokeWidth={stroke} />
      <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth={stroke}
        strokeDasharray={`${dash} ${circ}`} strokeLinecap="round"
        style={{ transition: "stroke-dasharray 1.2s ease" }} />
    </svg>
  );
}

function PhaseCard({ phase, active, progress, onClick }) {
  return (
    <div onClick={!phase.locked ? onClick : undefined} style={{
      background: active ? "#1A2235" : "#111827",
      border: `2px solid ${active ? phase.color : phase.locked ? "#1E2535" : "#2A3347"}`,
      borderRadius: 12, padding: "14px 16px",
      display: "flex", alignItems: "center", gap: 12,
      opacity: phase.locked ? 0.4 : 1,
      cursor: phase.locked ? "default" : "pointer",
      transition: "all 0.25s", position: "relative", overflow: "hidden",
    }}>
      {active && !phase.locked && (
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 2,
          background: `linear-gradient(90deg, transparent, ${phase.color}, transparent)` }} />
      )}
      <div style={{ position: "relative", flexShrink: 0 }}>
        <Ring pct={progress} color={phase.color} size={48} stroke={4} />
        <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center",
          justifyContent: "center", fontSize: 14, color: phase.color }}>{phase.icon}</div>
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 4 }}>
          <span style={{ fontFamily: "'Playfair Display', serif", fontSize: 15, color: "#F0F2F8", fontWeight: 600 }}>{phase.label}</span>
          <span style={{ fontSize: 12, color: phase.color, fontFamily: "monospace", fontWeight: 700 }}>{progress}%</span>
        </div>
        <div style={{ fontSize: 11, color: "#8896A8", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{phase.description}</div>
      </div>
    </div>
  );
}

function ModuleBar({ mod, completions, onToggle }) {
  const done  = completions.filter(Boolean).length;
  const total = mod.items.length;
  const pct   = total ? Math.round((done / total) * 100) : 0;
  const [open, setOpen] = useState(false);
  return (
    <div style={{ marginBottom: 10 }}>
      <div onClick={() => setOpen(o => !o)} style={{
        background: "#0F1520", border: `1px solid ${open ? mod.color + "60" : "#252D3D"}`,
        borderRadius: open ? "8px 8px 0 0" : 8, padding: "12px 14px",
        cursor: "pointer", transition: "border-color 0.2s",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 7 }}>
              <span style={{ fontSize: 13, color: "#CDD5E0", fontWeight: 600 }}>{mod.label}</span>
              <span style={{ fontSize: 12, color: mod.color, fontFamily: "monospace", fontWeight: 700 }}>{done}/{total}</span>
            </div>
            <div style={{ height: 5, background: "#252D3D", borderRadius: 4, overflow: "hidden" }}>
              <div style={{ height: "100%", width: `${pct}%`, background: mod.color,
                borderRadius: 4, transition: "width 0.5s ease", boxShadow: `0 0 6px ${mod.color}80` }} />
            </div>
          </div>
          <span style={{ fontSize: 10, color: "#4A5568", transform: open ? "rotate(180deg)" : "none",
            transition: "transform 0.2s", marginLeft: 4 }}>â–¼</span>
        </div>
      </div>
      {open && (
        <div style={{ padding: "8px 14px 10px", background: "#080C14",
          border: `1px solid ${mod.color}60`, borderTop: "none", borderRadius: "0 0 8px 8px" }}>
          {mod.items.map((item, i) => (
            <div key={i} onClick={e => { e.stopPropagation(); onToggle(i); }}
              style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 4px",
                cursor: "pointer", borderRadius: 5, transition: "background 0.1s" }}
              onMouseEnter={e => e.currentTarget.style.background = "rgba(255,255,255,0.03)"}
              onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
              <div style={{ width: 15, height: 15, borderRadius: 3, flexShrink: 0,
                border: `1.5px solid ${completions[i] ? mod.color : "#3A4A5A"}`,
                background: completions[i] ? mod.color + "33" : "transparent",
                display: "flex", alignItems: "center", justifyContent: "center", transition: "all 0.15s" }}>
                {completions[i] && <span style={{ fontSize: 8, color: mod.color, fontWeight: 700 }}>âœ“</span>}
              </div>
              <span style={{ fontSize: 12, color: completions[i] ? mod.color : "#5A6A7A",
                transition: "color 0.15s" }}>{item}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SkillRow({ skill, level, base, mounted }) {
  const earned = level - base;
  return (
    <div style={{ marginBottom: 11 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 5 }}>
        <span style={{ fontSize: 12, color: "#A0AABA", fontWeight: 500 }}>{skill.name}</span>
        <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
          {earned > 0 && (
            <span style={{ fontSize: 9, color: "#4A6A4A", fontFamily: "monospace" }}>+{earned}</span>
          )}
          <span style={{ fontSize: 12, color: skill.color, fontFamily: "monospace", fontWeight: 700 }}>{level}/10</span>
        </div>
      </div>
      <div style={{ height: 5, background: "#1E2535", borderRadius: 4, overflow: "hidden", position: "relative" }}>
        {/* base level marker */}
        <div style={{ position: "absolute", top: 0, bottom: 0, left: 0,
          width: `${base * 10}%`, background: skill.color + "40", borderRadius: 4 }} />
        {/* earned from completions */}
        <div style={{ height: "100%", borderRadius: 4,
          width: mounted ? `${level * 10}%` : `${base * 10}%`,
          background: skill.color, transition: "width 0.6s ease",
          boxShadow: `0 0 6px ${skill.color}60` }} />
      </div>
    </div>
  );
}

const SectionLabel = ({ children }) => (
  <div style={{ fontSize: 10, letterSpacing: "0.2em", color: "#5A6A80", textTransform: "uppercase",
    marginBottom: 12, fontWeight: 600 }}>{children}</div>
);

const Hint = ({ children }) => (
  <div style={{ fontSize: 9, color: "#2A3A4A", letterSpacing: "0.08em", marginBottom: 10 }}>{children}</div>
);

const MiniBtn = ({ onClick, children }) => (
  <button onClick={onClick} style={{
    width: 16, height: 16, borderRadius: 3, border: "1px solid #2A3A4A",
    background: "transparent", color: "#5A6A7A", fontSize: 11, cursor: "pointer",
    display: "flex", alignItems: "center", justifyContent: "center", lineHeight: 1,
  }}>{children}</button>
);

// â”€â”€â”€ DASHBOARD â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

export default function Dashboard() {
  const [activePhase, setActivePhase]       = useState("framework");
  const [mounted, setMounted]               = useState(false);
  const [state, setState]                   = useState(loadState);
  const [editTarget, setEditTarget]         = useState(null);
  const [editTargetVal, setEditTargetVal]   = useState("");
  const [activeTab, setActiveTab]           = useState("overview");
  const [docs, setDocs]                     = useState([]);
  const [selectedDoc, setSelectedDoc]       = useState(null);
  const modalRef                            = useRef(null);

  useEffect(() => { setTimeout(() => setMounted(true), 100); }, []);
  useEffect(() => { localStorage.setItem("trading-career-v4", JSON.stringify(state)); }, [state]);

  // fetch docs â€” re-fetches on each panel open so new files are picked up automatically
  useEffect(() => {
    const loadDocs = async () => {
      try {
        const api = await fetch("/api/docs");
        if (api.ok) {
          const data = await api.json();
          if (Array.isArray(data)) {
            setDocs(data);
            return;
          }
        }
      } catch (_) {}

      try {
        const staticDocs = await fetch("/docs_index.json");
        if (!staticDocs.ok) return;
        const data = await staticDocs.json();
        if (Array.isArray(data)) setDocs(data);
      } catch (_) {}
    };

    loadDocs();
  }, []);

  // close modal on Escape
  useEffect(() => {
    if (!selectedDoc) return;
    const handler = (e) => { if (e.key === "Escape") setSelectedDoc(null); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selectedDoc]);

  // â”€â”€ computed â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const calcProgress = useCallback((phaseId) => {
    const mods = MODULES[phaseId] || [];
    if (!mods.length) return 0;
    const sum = mods.reduce((acc, mod) => {
      const c = state.completions[mod.id] || [];
      return acc + c.filter(Boolean).length / mod.items.length;
    }, 0);
    return Math.round((sum / mods.length) * 100);
  }, [state.completions]);

  const overallPct = Math.round(
    PHASES.filter(p => !p.locked).reduce((s, p) => s + calcProgress(p.id), 0) /
    PHASES.filter(p => !p.locked).length
  );

  // â”€â”€ state updaters â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const toggleItem = useCallback((modId, idx) => {
    setState(s => {
      const arr = [...(s.completions[modId] || [])];
      arr[idx] = !arr[idx];
      return { ...s, completions: { ...s.completions, [modId]: arr } };
    });
  }, []);


  const cycleBook = useCallback((title) => {
    const next = { unread: "reading", reading: "read", read: "unread" };
    setState(s => ({ ...s, books: { ...s.books, [title]: next[s.books[title] || "unread"] } }));
  }, []);

  const adjustActivity = useCallback((day, delta) => {
    setState(s => ({ ...s, activity: { ...s.activity, [day]: Math.min(10, Math.max(0, (s.activity[day] || 0) + delta)) } }));
  }, []);

  const adjustVideo = useCallback((label, delta) => {
    setState(s => ({ ...s, videos: { ...s.videos, [label]: Math.max(0, (s.videos[label] || 0) + delta) } }));
  }, []);

  const toggleMilestone = useCallback((i) => {
    setState(s => {
      const m = [...(s.milestones || DEFAULT_STATE.milestones)];
      m[i] = !m[i];
      return { ...s, milestones: m };
    });
  }, []);

  const commitTarget = useCallback((metric) => {
    const val = parseFloat(editTargetVal);
    if (!isNaN(val)) setState(s => ({ ...s, targets: { ...s.targets, [metric]: val } }));
    setEditTarget(null);
    setEditTargetVal("");
  }, [editTargetVal]);

  // â”€â”€ derived values â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  const filteredMods    = MODULES[activePhase] || [];
  const activePhaseData = PHASES.find(p => p.id === activePhase);
  const booksRead       = BOOK_DEFS.filter(b => state.books[b.title] === "read").length;
  const booksReading    = BOOK_DEFS.filter(b => state.books[b.title] === "reading").length;
  const totalVideos     = VIDEO_CAT_DEFS.reduce((s, c) => s + (state.videos[c.label] || 0), 0);
  const maxVideo        = Math.max(...VIDEO_CAT_DEFS.map(c => state.videos[c.label] || 0), 1);
  const maxActivity     = Math.max(...DAYS.map(d => state.activity[d] || 0), 1);
  const milestones      = state.milestones || DEFAULT_STATE.milestones;
  const priorityColor   = { HIGH: "#E87A7A", MED: "#E8B96A", LOW: "#4A5A70" };

  const TABS = [
    { id: "overview",     label: "Overview"    },
    { id: "curriculum",   label: "Curriculum"  },
    { id: "resources",    label: "Resources"   },
    { id: "performance",  label: "Performance" },
  ];

  return (
    <div style={{ minHeight: "100vh", background: "#080C14", fontFamily: "'Inter', sans-serif", color: "#8896A8" }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600&family=Inter:wght@400;500;600&display=swap');
        * { box-sizing: border-box; margin: 0; padding: 0; }
        ::-webkit-scrollbar { width: 4px; }
        ::-webkit-scrollbar-track { background: #080C14; }
        ::-webkit-scrollbar-thumb { background: #252D3D; border-radius: 4px; }
        button { transition: opacity 0.15s; } button:hover { opacity: 0.7; }
      `}</style>

      {/* â”€â”€ HEADER â”€â”€ */}
      <div style={{ borderBottom: "1px solid #1E2535", padding: "20px 28px 0" }}>
        <div style={{ maxWidth: 1100, margin: "0 auto" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18 }}>
            <div>
              <div style={{ fontSize: 11, letterSpacing: "0.15em", color: "#5A6A80", textTransform: "uppercase", marginBottom: 5, fontWeight: 600 }}>
                Harrison Seaborn Â· Goal: Prop Firm Funded Trader
              </div>
              <h1 style={{ fontFamily: "'Playfair Display', serif", fontSize: 26, color: "#F0F2F8", fontWeight: 600 }}>
                Career Progression Dashboard
              </h1>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 11, color: "#5A6A80", marginBottom: 3, letterSpacing: "0.1em", textTransform: "uppercase", fontWeight: 600 }}>Overall Progress</div>
              <div style={{ fontFamily: "monospace", fontSize: 34, color: "#E8B96A", lineHeight: 1, fontWeight: 700 }}>
                {overallPct}<span style={{ fontSize: 16 }}>%</span>
              </div>
            </div>
          </div>

          {/* â”€â”€ TAB NAV â”€â”€ */}
          <div style={{ display: "flex", gap: 0 }}>
            {TABS.map(tab => {
              const active = activeTab === tab.id;
              return (
                <button key={tab.id} onClick={() => setActiveTab(tab.id)} style={{
                  background: "transparent", border: "none", cursor: "pointer",
                  padding: "10px 22px", fontSize: 13, fontWeight: 600,
                  color: active ? "#F0F2F8" : "#4A5A70",
                  borderBottom: `2px solid ${active ? "#E8B96A" : "transparent"}`,
                  letterSpacing: "0.03em", transition: "color 0.2s, border-color 0.2s",
                  marginBottom: -1,
                }}>
                  {tab.label}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      <div style={{ maxWidth: 1100, margin: "0 auto", padding: "28px 28px" }}>

        {/* â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
            TAB: OVERVIEW
        â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â• */}
        {activeTab === "overview" && (
          <div>
            {/* Phase summary cards â€” clicking also switches to Curriculum */}
            <div style={{ marginBottom: 28 }}>
              <SectionLabel>Learning Phases</SectionLabel>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
                {PHASES.map(p => (
                  <PhaseCard key={p.id} phase={p} active={false}
                    progress={calcProgress(p.id)}
                    onClick={() => { setActivePhase(p.id); setActiveTab("curriculum"); }} />
                ))}
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>
              {/* Priority Actions */}
              <div style={{ background: "#0D1321", border: "1px solid #1E2535", borderRadius: 14, padding: "20px 18px" }}>
                <SectionLabel>Priority Actions</SectionLabel>
                {NEXT_ACTIONS.map((action, i) => (
                  <div key={i} style={{ display: "flex", alignItems: "flex-start", gap: 8, marginBottom: 9,
                    padding: "9px 12px", background: "#080C14", borderRadius: 8,
                    borderLeft: `2px solid ${priorityColor[action.priority]}` }}>
                    <span style={{ fontSize: 8, fontWeight: 700, color: priorityColor[action.priority],
                      letterSpacing: "0.08em", paddingTop: 2, minWidth: 26 }}>{action.priority}</span>
                    <span style={{ fontSize: 12, color: "#8896A8", lineHeight: 1.5 }}>{action.text}</span>
                  </div>
                ))}
              </div>

              {/* Career Milestones */}
              <div style={{ background: "#0D1321", border: "1px solid #1E2535", borderRadius: 14, padding: "20px 18px" }}>
                <SectionLabel>Career Milestones</SectionLabel>
                <Hint>CLICK TO TOGGLE COMPLETE</Hint>
                {MILESTONE_DEFS.map((m, i) => {
                  const done = milestones[i];
                  return (
                    <div key={i} onClick={() => toggleMilestone(i)}
                      style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 11,
                        cursor: "pointer", borderRadius: 6, padding: "3px 4px", transition: "background 0.1s" }}
                      onMouseEnter={e => e.currentTarget.style.background = "rgba(255,255,255,0.02)"}
                      onMouseLeave={e => e.currentTarget.style.background = "transparent"}>
                      <div style={{ width: 16, height: 16, borderRadius: "50%", flexShrink: 0,
                        border: `1.5px solid ${done ? m.color : "#2A3A4A"}`,
                        background: done ? m.color + "33" : "transparent",
                        display: "flex", alignItems: "center", justifyContent: "center", transition: "all 0.2s" }}>
                        {done && <span style={{ fontSize: 8, color: m.color }}>âœ“</span>}
                      </div>
                      <span style={{ fontSize: 12, lineHeight: 1.3,
                        color: done ? "#5A7A5A" : "#6A7A8A",
                        textDecoration: done ? "line-through" : "none",
                        transition: "all 0.2s" }}>{m.label}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
            TAB: CURRICULUM
        â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â• */}
        {activeTab === "curriculum" && (
          <div>
            {/* Phase selector */}
            <div style={{ marginBottom: 24 }}>
              <SectionLabel>Learning Phases â€” click to switch</SectionLabel>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}>
                {PHASES.map(p => (
                  <PhaseCard key={p.id} phase={p} active={activePhase === p.id}
                    progress={calcProgress(p.id)} onClick={() => setActivePhase(p.id)} />
                ))}
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1.3fr 1fr", gap: 18 }}>
              {/* Modules */}
              <div style={{ background: "#0D1321", border: "1px solid #1E2535", borderRadius: 14, padding: "20px 18px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <SectionLabel>{activePhaseData?.label} Â· Modules</SectionLabel>
                  <div style={{ fontSize: 12, color: activePhaseData?.color, fontWeight: 700 }}>
                    {filteredMods.reduce((s, m) => s + (state.completions[m.id] || []).filter(Boolean).length, 0)} /
                    {filteredMods.reduce((s, m) => s + m.items.length, 0)} complete
                  </div>
                </div>
                <Hint>EXPAND A MODULE Â· CLICK ITEMS TO MARK COMPLETE</Hint>
                {filteredMods.map(m => (
                  <ModuleBar key={m.id} mod={m}
                    completions={state.completions[m.id] || m.items.map(() => false)}
                    onToggle={idx => toggleItem(m.id, idx)} />
                ))}
              </div>

              {/* Skill Proficiency */}
              <div style={{ background: "#0D1321", border: "1px solid #1E2535", borderRadius: 14, padding: "20px 18px" }}>
                <SectionLabel>Skill Proficiency</SectionLabel>
                <Hint>DERIVED FROM MODULE COMPLETION Â· BASE FROM INSTITUTIONAL BACKGROUND</Hint>
                {SKILL_MODULE_MAP.map(skill => (
                  <SkillRow key={skill.name} skill={skill}
                    level={computeSkillLevel(skill, state.completions)}
                    base={skill.base} mounted={mounted} />
                ))}
              </div>
            </div>
          </div>
        )}

        {/* â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
            TAB: RESOURCES
        â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â• */}
        {activeTab === "resources" && (
          <div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18, marginBottom: 18 }}>
              {/* Essential Reading */}
              <div style={{ background: "#0D1321", border: "1px solid #1E2535", borderRadius: 14, padding: "20px 18px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <SectionLabel>Essential Reading</SectionLabel>
                  <div style={{ display: "flex", gap: 10, fontSize: 10 }}>
                    <span style={{ color: "#7DC87A" }}>â— {booksRead} read</span>
                    <span style={{ color: "#E8B96A" }}>â— {booksReading} reading</span>
                    <span style={{ color: "#3A4A5A" }}>â— {BOOK_DEFS.length - booksRead - booksReading} queued</span>
                  </div>
                </div>
                <Hint>CLICK DOT TO CYCLE: QUEUED â†’ READING â†’ READ</Hint>
                {BOOK_DEFS.map((book, i) => {
                  const status   = state.books[book.title] || "unread";
                  const dotColor = status === "read" ? "#7DC87A" : status === "reading" ? "#E8B96A" : "#252D3D";
                  return (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "7px 0",
                      borderBottom: i < BOOK_DEFS.length - 1 ? "1px solid #131B28" : "none" }}>
                      <div onClick={() => cycleBook(book.title)} style={{ width: 8, height: 8, borderRadius: "50%",
                        flexShrink: 0, background: dotColor, cursor: "pointer", transition: "background 0.2s",
                        border: status === "unread" ? "1px solid #3A4A5A" : "none" }} />
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <span style={{ fontSize: 12, color: status === "read" ? "#5A7A5A" : "#A0AABA" }}>{book.title}</span>
                        <span style={{ fontSize: 10, color: "#3A4A5A", marginLeft: 6 }}>{book.author}</span>
                      </div>
                      <span style={{ fontSize: 9, color: "#3A4A5A", background: "#131B28",
                        padding: "2px 6px", borderRadius: 4, flexShrink: 0 }}>{book.category}</span>
                    </div>
                  );
                })}
              </div>

              {/* Video Library */}
              <div style={{ background: "#0D1321", border: "1px solid #1E2535", borderRadius: 14, padding: "20px 18px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  <SectionLabel>Video Library</SectionLabel>
                  <div style={{ fontSize: 12, color: "#E8B96A", fontFamily: "monospace", fontWeight: 700 }}>{totalVideos} saved</div>
                </div>
                <Hint>USE + / âˆ’ TO UPDATE COUNTS</Hint>
                {VIDEO_CAT_DEFS.map(cat => {
                  const count = state.videos[cat.label] || 0;
                  return (
                    <div key={cat.label} style={{ marginBottom: 14 }}>
                      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 5 }}>
                        <span style={{ fontSize: 12, color: "#A0AABA" }}>{cat.label}</span>
                        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
                          <MiniBtn onClick={() => adjustVideo(cat.label, -1)}>âˆ’</MiniBtn>
                          <span style={{ fontSize: 12, color: cat.color, fontFamily: "monospace",
                            fontWeight: 700, minWidth: 22, textAlign: "center" }}>{count}</span>
                          <MiniBtn onClick={() => adjustVideo(cat.label, 1)}>+</MiniBtn>
                        </div>
                      </div>
                      <div style={{ height: 4, background: "#1E2535", borderRadius: 4, overflow: "hidden" }}>
                        <div style={{ height: "100%", borderRadius: 4,
                          width: mounted ? `${(count / maxVideo) * 100}%` : "0%",
                          background: cat.color, transition: "width 0.4s ease",
                          boxShadow: `0 0 6px ${cat.color}60` }} />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Reference Docs â€” grouped by category */}
            {docs.length > 0 && (() => {
              const grouped = DOC_CATEGORY_ORDER.reduce((acc, cat) => {
                const catDocs = docs.filter(d => d.category === cat);
                if (catDocs.length > 0) acc.push({ cat, docs: catDocs });
                return acc;
              }, []);
              return (
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
                    <SectionLabel>Reference Docs</SectionLabel>
                    <span style={{ fontSize: 10, color: "#3A4A5A", fontFamily: "monospace" }}>
                      {docs.length} docs Â· {grouped.length} categories Â· auto-synced
                    </span>
                  </div>
                  <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                    {grouped.map(({ cat, docs: catDocs }) => {
                      const color = DOC_CATEGORY_COLOR[cat] || "#8896A8";
                      return (
                        <div key={cat}>
                          {/* Category header */}
                          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
                            <div style={{ width: 10, height: 10, borderRadius: "50%", background: color, flexShrink: 0 }} />
                            <span style={{ fontSize: 11, color: color, fontWeight: 700, letterSpacing: "0.12em",
                              textTransform: "uppercase" }}>{cat}</span>
                            <div style={{ flex: 1, height: 1, background: `linear-gradient(90deg, ${color}30, transparent)` }} />
                            <span style={{ fontSize: 10, color: "#3A4A5A" }}>{catDocs.length} doc{catDocs.length > 1 ? "s" : ""}</span>
                          </div>
                          {/* Doc cards */}
                          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: 10 }}>
                            {catDocs.map((doc, i) => (
                              <div key={i} onClick={() => setSelectedDoc(doc)}
                                style={{ background: "#080C14", border: `1px solid ${color}25`,
                                  borderRadius: 10, padding: "12px 14px", cursor: "pointer",
                                  borderLeft: `3px solid ${color}`,
                                  transition: "background 0.15s, border-color 0.15s" }}
                                onMouseEnter={e => { e.currentTarget.style.background = "#0D1625"; e.currentTarget.style.borderColor = color + "70"; }}
                                onMouseLeave={e => { e.currentTarget.style.background = "#080C14"; e.currentTarget.style.borderColor = color + "25"; }}>
                                <div style={{ fontSize: 12, color: "#CDD5E0", fontWeight: 600,
                                  lineHeight: 1.35, marginBottom: 6 }}>{doc.title}</div>
                                <div style={{ fontSize: 10, color: "#3A4A5A" }}>
                                  {doc.content.split("\n").filter(l => l.trim()).length} lines Â· click to read
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })()}
          </div>
        )}

        {/* â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
            TAB: PERFORMANCE
        â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â• */}
        {activeTab === "performance" && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }}>

            {/* Strategy Targets */}
            <div style={{ background: "#0D1321", border: "1px solid #1E2535", borderRadius: 14, padding: "20px 18px" }}>
              <SectionLabel>Strategy Performance Targets</SectionLabel>
              <Hint>CLICK CURRENT VALUE TO EDIT</Hint>
              {TARGET_DEFS.map(item => {
                const current  = state.targets[item.metric] ?? 0;
                const progress = item.higher
                  ? Math.min(100, (current / item.target) * 100)
                  : current === 0 ? 0 : Math.min(100, (item.target / current) * 100);
                const met       = item.higher ? current >= item.target : current <= item.target;
                const isEditing = editTarget === item.metric;
                return (
                  <div key={item.metric} style={{ marginBottom: 14 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                      <span style={{ fontSize: 13, color: "#8896A8" }}>{item.metric}</span>
                      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                        {isEditing ? (
                          <input autoFocus value={editTargetVal}
                            onChange={e => setEditTargetVal(e.target.value)}
                            onBlur={() => commitTarget(item.metric)}
                            onKeyDown={e => e.key === "Enter" && commitTarget(item.metric)}
                            style={{ width: 60, background: "#131B28",
                              border: `1px solid ${met ? "#7DC87A" : "#E87A7A"}`,
                              borderRadius: 4, color: met ? "#7DC87A" : "#E87A7A",
                              fontFamily: "monospace", fontSize: 13, fontWeight: 700,
                              padding: "2px 6px", outline: "none", textAlign: "right" }} />
                        ) : (
                          <span onClick={() => { setEditTarget(item.metric); setEditTargetVal(String(current)); }}
                            style={{ fontSize: 13, color: met ? "#7DC87A" : "#E87A7A", fontFamily: "monospace",
                              fontWeight: 700, cursor: "pointer",
                              borderBottom: "1px dashed", borderColor: "currentColor" }}>
                            {current}{item.unit}
                          </span>
                        )}
                        <span style={{ fontSize: 11, color: "#3A4A5A" }}>â†’ {item.target}{item.unit}</span>
                      </div>
                    </div>
                    <div style={{ height: 5, background: "#1E2535", borderRadius: 4, overflow: "hidden" }}>
                      <div style={{ height: "100%", width: mounted ? `${progress}%` : "0%",
                        background: met ? "#7DC87A" : "linear-gradient(90deg, #E87A7A, #E8B96A)",
                        borderRadius: 4, transition: "width 0.5s ease",
                        boxShadow: met ? "0 0 6px #7DC87A60" : "none" }} />
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Weekly Activity */}
            <div style={{ background: "#0D1321", border: "1px solid #1E2535", borderRadius: 14, padding: "20px 18px" }}>
              <SectionLabel>Weekly Activity</SectionLabel>
              <Hint>CLICK BAR +1 Â· RIGHT-CLICK âˆ’1</Hint>
              <div style={{ display: "flex", alignItems: "flex-end", gap: 8, height: 120, marginTop: 12 }}>
                {DAYS.map(day => {
                  const val  = state.activity[day] || 0;
                  const peak = val === maxActivity && val > 0;
                  return (
                    <div key={day} style={{ flex: 1, display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}
                      onContextMenu={e => { e.preventDefault(); adjustActivity(day, -1); }}>
                      <div onClick={() => adjustActivity(day, 1)}
                        title={`${val} sessions â€” click +1, right-click âˆ’1`}
                        style={{ width: "100%", borderRadius: 4,
                          height: `${(val / 10) * 90}px`, minHeight: 4,
                          background: peak ? "#E8B96A" : "#1E2A3D",
                          boxShadow: peak ? "0 0 12px #E8B96A60" : "none",
                          transition: "height 0.3s ease, background 0.3s ease",
                          cursor: "pointer", alignSelf: "flex-end" }} />
                      <span style={{ fontSize: 10, color: "#4A5A70", fontWeight: 600, letterSpacing: "0.05em" }}>{day}</span>
                    </div>
                  );
                })}
              </div>
            </div>

          </div>
        )}

        <div style={{ marginTop: 32, textAlign: "center", fontSize: 10, color: "#1E2535", letterSpacing: "0.15em", fontWeight: 600 }}>
          MIDNIGHTODYSSEY Â· QUANT FRAMEWORK v0.1 Â· CAREER PROGRESSION TRACKER
        </div>
      </div>

      {/* â”€â”€ DOC READER MODAL â”€â”€ */}
      {selectedDoc && (
        <div onClick={e => e.target === e.currentTarget && setSelectedDoc(null)}
          style={{ position: "fixed", inset: 0, background: "rgba(4,8,16,0.88)",
            display: "flex", alignItems: "flex-start", justifyContent: "center",
            zIndex: 1000, padding: "40px 24px", overflowY: "auto" }}>
          <div ref={modalRef} style={{ background: "#0D1321", border: "1px solid #252D3D",
            borderRadius: 14, width: "100%", maxWidth: 720,
            padding: "28px 32px", position: "relative" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
              <div>
                <div style={{ fontSize: 9, color: DOC_CATEGORY_COLOR[selectedDoc.category] || "#B89FD8",
                  letterSpacing: "0.15em", textTransform: "uppercase", fontWeight: 700, marginBottom: 6 }}>
                  {selectedDoc.category}
                </div>
                <div style={{ fontFamily: "'Playfair Display', serif", fontSize: 18, color: "#F0F2F8",
                  fontWeight: 600 }}>{selectedDoc.title}</div>
                <div style={{ fontSize: 10, color: "#3A4A5A", marginTop: 4 }}>{selectedDoc.filename}</div>
              </div>
              <button onClick={() => setSelectedDoc(null)}
                style={{ background: "#1E2535", border: "none", borderRadius: 6, color: "#5A6A7A",
                  width: 28, height: 28, fontSize: 16, cursor: "pointer", flexShrink: 0,
                  display: "flex", alignItems: "center", justifyContent: "center" }}>Ã—</button>
            </div>
            <div style={{ borderTop: "1px solid #1E2535", paddingTop: 20 }}>
              <MarkdownDoc content={selectedDoc.content} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

