import { useState, useEffect, useCallback } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

// ─── Palette: Broadsheet Editorial ───────────────────────────────────────────
const T = {
  ink:      "#1a1208",
  paper:    "#f4efe4",
  paperDk:  "#ede7d6",
  cream:    "#faf7f0",
  rule:     "#c8bfa8",
  ruleDk:   "#8a7f6a",
  red:      "#c0392b",
  redDk:    "#922b21",
  gold:     "#b5860d",
  goldLt:   "#fdf3dc",
  blue:     "#1a3a5c",
  blueLt:   "#e8f0f8",
  green:    "#1c4d35",
  greenLt:  "#e8f5ee",
  muted:    "#6b6252",
  faint:    "#a89f8c",
};

function useApi(endpoint, params = {}) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(true);
  const stableParams = JSON.stringify(params);

  const run = useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams(
        Object.entries(params).filter(([, v]) => v !== "" && v != null && v !== 0)
      ).toString();
      const res = await fetch(`${API_BASE}${endpoint}${qs ? "?" + qs : ""}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  }, [endpoint, stableParams]); // eslint-disable-line

  useEffect(() => { run(); }, [run]);
  return { data, loading, refetch: run };
}

function Rule({ my = 16, weight = 1, color = T.rule }) {
  return <div style={{ borderTop: `${weight}px solid ${color}`, margin: `${my}px 0` }} />;
}
function DoubleRule({ my = 16 }) {
  return (
    <div style={{ margin: `${my}px 0` }}>
      <div style={{ borderTop: `3px solid ${T.ink}` }} />
      <div style={{ borderTop: `1px solid ${T.ink}`, marginTop: "3px" }} />
    </div>
  );
}

const CAT_ICON = {
  "Product/Tool": "◈", "AI Model": "◉", "Research Paper": "◎",
  "Industry News": "◆", "Tutorial/Guide": "▶", "Platform/Infrastructure": "▣",
};
const SRC_STYLE = {
  "Hacker News":             { bg: "#c0392b", label: "HN" },
  "arXiv":                   { bg: "#1a3a5c", label: "arXiv" },
  "Medium":                  { bg: "#1a1208", label: "Medium" },
  "NewsAPI":                 { bg: "#b5860d", label: "News" },
  "platformengineering.org": { bg: "#1c4d35", label: "PE.org" },
  "Platform Weekly":         { bg: "#1c4d35", label: "PW" },
};
function srcFor(s) {
  const k = Object.keys(SRC_STYLE).find(k => s?.includes(k)) || "NewsAPI";
  return SRC_STYLE[k];
}

function Stamp({ children, bg = T.ink, color = T.paper }) {
  return (
    <span style={{
      display: "inline-block", padding: "1px 7px 2px",
      background: bg, color,
      fontSize: "9.5px", fontWeight: 700,
      letterSpacing: "0.14em", textTransform: "uppercase",
      fontFamily: "'Barlow Condensed', sans-serif",
    }}>{children}</span>
  );
}

function Stars({ score }) {
  const full  = Math.round((score || 0) / 2);
  const color = score >= 7 ? T.green : score >= 5 ? T.gold : T.muted;
  return (
    <span style={{ fontFamily: "Georgia, serif", fontSize: "13px", color, letterSpacing: "2px" }}>
      {"●".repeat(full)}{"○".repeat(5 - full)}
    </span>
  );
}

function CompetitorBlock({ competitors, advantage, productName }) {
  if (!competitors?.length) return null;
  return (
    <div style={{ marginTop: "18px", border: `1px solid ${T.rule}`, borderLeft: `4px solid ${T.red}` }}>
      <div style={{ padding: "7px 14px", background: T.ink, display: "flex", alignItems: "center" }}>
        <span style={{ color: T.paper, fontSize: "10px", fontWeight: 700, letterSpacing: "0.15em", textTransform: "uppercase", fontFamily: "'Barlow Condensed', sans-serif" }}>
          COMPETITIVE LANDSCAPE — {productName || "This Product"}
        </span>
      </div>
      <table style={{ width: "100%", borderCollapse: "collapse", background: T.cream }}>
        <thead>
          <tr style={{ borderBottom: `2px solid ${T.ink}` }}>
            {["Rival", "What they do", "How this differs"].map(h => (
              <th key={h} style={{ padding: "7px 12px", textAlign: "left", fontSize: "9px", fontWeight: 700, color: T.muted, letterSpacing: "0.12em", textTransform: "uppercase", fontFamily: "'Barlow Condensed', sans-serif" }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {competitors.map((c, i) => (
            <tr key={i} style={{ borderBottom: `1px solid ${T.rule}`, background: i % 2 === 0 ? T.cream : T.paper }}>
              <td style={{ padding: "9px 12px", fontWeight: 700, fontSize: "12px", color: T.ink, whiteSpace: "nowrap" }}>{c.name}</td>
              <td style={{ padding: "9px 12px", fontSize: "12px", color: T.muted, lineHeight: 1.5 }}>{c.description}</td>
              <td style={{ padding: "9px 12px", fontSize: "12px", color: T.green, lineHeight: 1.5 }}>{c.comparison}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {advantage && (
        <div style={{ padding: "10px 14px", background: T.greenLt, borderTop: `1px solid ${T.rule}`, fontSize: "12px", color: T.green, lineHeight: 1.6 }}>
          <strong style={{ fontFamily: "'Barlow Condensed', sans-serif", letterSpacing: "0.1em", textTransform: "uppercase", fontSize: "10px" }}>KEY ADVANTAGE — </strong>
          {advantage}
        </div>
      )}
    </div>
  );
}

function ArticleCard({ article, expanded, onToggle, isLead }) {
  const [showSummary, setShowSummary] = useState(false);
  const src  = srcFor(article.source);
  const icon = CAT_ICON[article.category] || "◆";
  const hasSummary = article.summary && article.summary.length > 20;
  const hasRivals  = article.is_product_or_tool && article.competitors?.length > 0;

  return (
    <article
      style={{ paddingBottom: "18px", marginBottom: "18px", borderBottom: `1px solid ${T.rule}` }}
    >
      {/* Source / category / badges row */}
      <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "7px", flexWrap: "wrap" }}>
        <Stamp bg={src.bg}>{src.label}</Stamp>
        <span style={{ fontSize: "9.5px", color: T.muted, textTransform: "uppercase", letterSpacing: "0.12em", fontFamily: "'Barlow Condensed', sans-serif" }}>
          {icon} {article.category}
        </span>
        <span style={{ marginLeft: "auto" }}><Stars score={article.relevance_score} /></span>
      </div>

      {/* Headline */}
      <h2 style={{
        margin: "0 0 10px",
        fontFamily: "'Playfair Display', Georgia, serif",
        fontSize: isLead ? "clamp(20px,3.5vw,28px)" : "16px",
        fontWeight: 700, lineHeight: 1.28,
        color: T.ink, letterSpacing: "-0.2px",
      }}>
        <a href={article.url} target="_blank" rel="noopener noreferrer"
          style={{ color: "inherit", textDecoration: "none" }}
          onMouseEnter={e => e.currentTarget.style.borderBottom = `2px solid ${T.ink}`}
          onMouseLeave={e => e.currentTarget.style.borderBottom = "2px solid transparent"}>
          {article.title}
        </a>
      </h2>

      {/* Inline action links — Summary + Rivals */}
      <div style={{ display: "flex", gap: "14px", alignItems: "center", marginBottom: "8px", flexWrap: "wrap" }}>
        {hasSummary && (
          <button
            onClick={() => setShowSummary(s => !s)}
            style={{
              background: "none", border: "none", padding: 0, cursor: "pointer",
              fontSize: "10px", fontWeight: 700,
              color: showSummary ? T.ink : T.muted,
              fontFamily: "'Barlow Condensed', sans-serif",
              letterSpacing: "0.12em", textTransform: "uppercase",
              borderBottom: `1px solid ${showSummary ? T.ink : T.rule}`,
            }}>
            {showSummary ? "▲ SUMMARY" : "▼ SUMMARY"}
          </button>
        )}
        {hasRivals && (
          <button
            onClick={onToggle}
            style={{
              background: "none", border: "none", padding: 0, cursor: "pointer",
              fontSize: "10px", fontWeight: 700,
              color: expanded ? T.red : T.muted,
              fontFamily: "'Barlow Condensed', sans-serif",
              letterSpacing: "0.12em", textTransform: "uppercase",
              borderBottom: `1px solid ${expanded ? T.red : T.rule}`,
            }}>
            {expanded ? "▲ RIVALS" : "⚔ RIVALS"}
          </button>
        )}

        {/* Tags + author on the right */}
        <div style={{ marginLeft: "auto", display: "flex", gap: "8px", alignItems: "center", flexWrap: "wrap" }}>
          {(article.tags || []).slice(0, 3).map(t => (
            <span key={t} style={{ fontSize: "10px", color: T.faint, fontFamily: "'Barlow Condensed', sans-serif" }}>#{t}</span>
          ))}
          {article.author && (
            <span style={{ fontSize: "10px", color: T.faint, fontStyle: "italic" }}>
              {article.author.slice(0, 28)}{article.author.length > 28 ? "…" : ""}
            </span>
          )}
        </div>
      </div>

      {/* Collapsible summary */}
      {showSummary && hasSummary && (
        <div style={{
          margin: "0 0 10px",
          padding: "12px 14px",
          background: T.paperDk,
          borderLeft: `3px solid ${T.gold}`,
          fontSize: isLead ? "14px" : "12.5px",
          color: T.muted, lineHeight: 1.7,
          fontFamily: "'Source Serif 4', Georgia, serif",
        }}>
          {article.summary}
        </div>
      )}

      {/* Collapsible competitor analysis */}
      {expanded && hasRivals && (
        <CompetitorBlock
          competitors={article.competitors}
          advantage={article.competitive_advantage}
          productName={article.product_name}
        />
      )}
    </article>
  );
}

function SubscribeDrawer({ onClose, onSuccess }) {
  const [form, setForm]     = useState({ email: "", name: "", min_relevance: 6, categories: [] });
  const [loading, setLoading] = useState(false);
  const cats = ["Product/Tool", "AI Model", "Research Paper", "Industry News", "Tutorial/Guide", "Platform/Infrastructure"];
  const toggle = c => setForm(f => ({ ...f, categories: f.categories.includes(c) ? f.categories.filter(x => x !== c) : [...f.categories, c] }));

  const submit = async () => {
    if (!form.email) return;
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/users`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form),
      });
      if (res.ok) onSuccess(); else throw new Error(await res.text());
    } catch (e) { alert(e.message); }
    finally { setLoading(false); }
  };

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 200, display: "flex", alignItems: "flex-end", justifyContent: "flex-end" }}>
      <div onClick={onClose} style={{ position: "absolute", inset: 0, background: "rgba(26,18,8,0.55)", backdropFilter: "blur(2px)" }} />
      <div style={{
        position: "relative", zIndex: 1,
        width: "420px", maxWidth: "100vw", height: "100vh",
        background: T.cream, borderLeft: `4px solid ${T.ink}`,
        padding: "36px 28px", overflowY: "auto",
      }}>
        <button onClick={onClose} style={{ position: "absolute", top: "18px", right: "18px", background: "none", border: "none", cursor: "pointer", fontSize: "22px", color: T.muted }}>×</button>
        <DoubleRule my={0} />
        <h2 style={{ fontFamily: "'Playfair Display', serif", fontSize: "24px", fontWeight: 700, margin: "18px 0 6px", color: T.ink }}>Subscribe to the Digest</h2>
        <p style={{ margin: "0 0 22px", color: T.muted, fontSize: "13px", lineHeight: 1.6, fontFamily: "'Source Serif 4', serif" }}>
          One curated briefing per day at 08:00 UTC. Summaries, competitive intelligence, and relevance scores.
        </p>
        <Rule />

        {[{ key: "email", label: "Email address", type: "email", ph: "you@company.com" }, { key: "name", label: "Your name", type: "text", ph: "First name" }].map(f => (
          <div key={f.key} style={{ marginBottom: "16px" }}>
            <label style={{ display: "block", marginBottom: "5px", fontSize: "9.5px", fontWeight: 700, letterSpacing: "0.15em", textTransform: "uppercase", color: T.muted, fontFamily: "'Barlow Condensed', sans-serif" }}>{f.label}</label>
            <input type={f.type} placeholder={f.ph} value={form[f.key]}
              onChange={e => setForm(p => ({ ...p, [f.key]: e.target.value }))}
              style={{ width: "100%", padding: "9px 11px", border: "none", borderBottom: `2px solid ${T.ink}`, background: "transparent", color: T.ink, fontSize: "14px", outline: "none", fontFamily: "Georgia, serif", boxSizing: "border-box" }} />
          </div>
        ))}

        <div style={{ marginBottom: "20px" }}>
          <label style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px", fontSize: "9.5px", fontWeight: 700, letterSpacing: "0.15em", textTransform: "uppercase", color: T.muted, fontFamily: "'Barlow Condensed', sans-serif" }}>
            <span>Min relevance score</span><span style={{ color: T.red }}>{form.min_relevance} / 10</span>
          </label>
          <input type="range" min={1} max={10} value={form.min_relevance}
            onChange={e => setForm(f => ({ ...f, min_relevance: +e.target.value }))}
            style={{ width: "100%", accentColor: T.ink }} />
        </div>

        <div style={{ marginBottom: "24px" }}>
          <label style={{ display: "block", marginBottom: "10px", fontSize: "9.5px", fontWeight: 700, letterSpacing: "0.15em", textTransform: "uppercase", color: T.muted, fontFamily: "'Barlow Condensed', sans-serif" }}>Sections (blank = all)</label>
          {cats.map(c => {
            const on = form.categories.includes(c);
            return (
              <label key={c} onClick={() => toggle(c)} style={{ display: "flex", alignItems: "center", gap: "10px", cursor: "pointer", fontSize: "13px", color: on ? T.ink : T.muted, marginBottom: "9px", fontFamily: "'Source Serif 4', serif" }}>
                <span style={{ width: "14px", height: "14px", border: `2px solid ${on ? T.ink : T.rule}`, background: on ? T.ink : "transparent", display: "inline-flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>
                  {on && <span style={{ color: T.paper, fontSize: "9px", fontWeight: 900 }}>✓</span>}
                </span>
                {CAT_ICON[c]} {c}
              </label>
            );
          })}
        </div>

        <Rule />
        <div style={{ display: "flex", gap: "10px" }}>
          <button onClick={onClose} style={{ flex: 1, padding: "11px", border: `1px solid ${T.rule}`, background: "transparent", color: T.muted, cursor: "pointer", fontSize: "12px", fontFamily: "'Barlow Condensed', sans-serif", letterSpacing: "0.1em", textTransform: "uppercase" }}>Cancel</button>
          <button onClick={submit} disabled={loading || !form.email} style={{ flex: 2, padding: "11px", border: "none", background: form.email && !loading ? T.ink : T.rule, color: T.paper, cursor: "pointer", fontSize: "12px", fontWeight: 700, fontFamily: "'Barlow Condensed', sans-serif", letterSpacing: "0.1em", textTransform: "uppercase" }}>
            {loading ? "Processing…" : "SUBSCRIBE →"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────
export default function App() {
  const today = new Date().toLocaleDateString("en-GB", { weekday: "long", year: "numeric", month: "long", day: "numeric" });

  const [filters, setFilters]             = useState({ category: "", source: "", min_relevance: 0, search: "" });
  const [expandedId, setExpandedId]       = useState(null);
  const [showSub, setShowSub]             = useState(false);
  const [subOk, setSubOk]                 = useState(false);
  const [refreshing, setRefreshing]       = useState(false);
  const [activeTab, setActiveTab]         = useState("feed");

  const { data: news, loading, refetch } = useApi("/api/news", { limit: 40, ...filters });
  const { data: stats }                  = useApi("/api/news/stats");
  const { data: usersData }              = useApi("/api/users");
  const { data: cfg }                    = useApi("/api/config");

  const articles  = news?.articles || [];
  const lead      = articles[0];
  const mainCol   = articles.slice(1, 11);
  const sideCol   = articles.slice(11);

  const doRefresh = async () => {
    setRefreshing(true);
    await fetch(`${API_BASE}/api/trigger-refresh`, { method: "POST" });
    setTimeout(() => { setRefreshing(false); refetch(); }, 4000);
  };

  const configured = cfg ? [cfg.anthropic_configured && "Claude AI", cfg.resend_configured && "Email", cfg.news_api_configured && "NewsAPI"].filter(Boolean) : [];

  return (
    <div style={{ background: T.paper, minHeight: "100vh", color: T.ink }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,700;0,900;1,700&family=Source+Serif+4:ital,wght@0,400;0,600;1,400&family=Barlow+Condensed:wght@400;600;700&display=swap');
        *, *::before, *::after { box-sizing: border-box; }
        body { margin: 0; background: ${T.paper}; }
        ::selection { background: ${T.ink}; color: ${T.paper}; }
        body { -webkit-font-smoothing: antialiased; }
      `}</style>

      {/* ── MASTHEAD ─────────────────────────────────────────────────────────── */}
      <header style={{ background: T.paper, padding: "0 32px" }}>
        {/* Ticker */}
        <div style={{ borderBottom: `1px solid ${T.rule}`, padding: "7px 0", display: "flex", justifyContent: "space-between", alignItems: "center", fontSize: "10px", color: T.muted, fontFamily: "'Barlow Condensed', sans-serif", letterSpacing: "0.1em", flexWrap: "wrap", gap: "8px" }}>
          <div style={{ display: "flex", gap: "18px" }}>
            {configured.map(s => <span key={s} style={{ color: T.green }}>● {s.toUpperCase()}</span>)}
            {configured.length === 0 && <span style={{ color: T.red }}>● CONFIGURE API KEYS IN .ENV</span>}
          </div>
          <div style={{ display: "flex", gap: "14px" }}>
            <span>1-HOUR REFRESH</span><span style={{ color: T.rule }}>|</span>
            <span>DIGEST AT 08:00 UTC</span><span style={{ color: T.rule }}>|</span>
            <span>{stats?.total_articles || "—"} ARTICLES INDEXED</span>
          </div>
        </div>

        {/* Title block */}
        <div style={{ textAlign: "center", padding: "28px 0 16px" }}>
          <div style={{ fontFamily: "'Barlow Condensed', sans-serif", fontSize: "10px", fontWeight: 700, letterSpacing: "0.42em", color: T.muted, textTransform: "uppercase", marginBottom: "10px" }}>
            The Intelligence Briefing for AI Engineers
          </div>
          <h1 style={{ fontFamily: "'Playfair Display', Georgia, serif", fontSize: "clamp(44px, 9vw, 88px)", fontWeight: 900, margin: 0, lineHeight: 1, color: T.ink, letterSpacing: "-2px" }}>
            AI SIGNAL
          </h1>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: "14px", marginTop: "12px" }}>
            <div style={{ flex: 1, height: "1px", background: T.rule }} />
            <span style={{ fontSize: "10px", color: T.muted, fontFamily: "'Barlow Condensed', sans-serif", letterSpacing: "0.15em", whiteSpace: "nowrap" }}>{today}</span>
            <div style={{ flex: 1, height: "1px", background: T.rule }} />
          </div>
        </div>

        {/* Nav */}
        <div style={{ borderTop: `3px solid ${T.ink}`, borderBottom: `1px solid ${T.ink}`, display: "flex", justifyContent: "space-between", alignItems: "stretch" }}>
          <div style={{ display: "flex" }}>
            {[{ id: "feed", label: "FEED" }, { id: "subscribers", label: "SUBSCRIBERS" }].map(tab => (
              <button key={tab.id} onClick={() => setActiveTab(tab.id)} style={{ padding: "10px 18px", border: "none", borderRight: `1px solid ${T.rule}`, background: activeTab === tab.id ? T.ink : "transparent", color: activeTab === tab.id ? T.paper : T.muted, cursor: "pointer", fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700, fontSize: "11px", letterSpacing: "0.15em" }}>
                {tab.label}
              </button>
            ))}
          </div>
          <div style={{ display: "flex" }}>
            <button onClick={doRefresh} disabled={refreshing} style={{ padding: "10px 16px", border: "none", borderLeft: `1px solid ${T.rule}`, background: "transparent", color: refreshing ? T.faint : T.muted, cursor: "pointer", fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700, fontSize: "11px", letterSpacing: "0.1em" }}>
              {refreshing ? "⟳ REFRESHING…" : "⟳ REFRESH"}
            </button>
            <button onClick={() => setShowSub(true)} style={{ padding: "10px 20px", border: "none", background: T.red, color: T.paper, cursor: "pointer", fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700, fontSize: "11px", letterSpacing: "0.15em" }}>
              SUBSCRIBE →
            </button>
          </div>
        </div>
      </header>

      <main style={{ maxWidth: "1200px", margin: "0 auto", padding: "0 32px 80px" }}>

        {/* ── FEED ───────────────────────────────────────────────────────── */}
        {activeTab === "feed" && (
          <>
            {/* Filter strip */}
            <div style={{ display: "flex", gap: "14px", padding: "14px 0", borderBottom: `1px solid ${T.rule}`, flexWrap: "wrap", alignItems: "center" }}>
              <input placeholder="Search headlines…" value={filters.search}
                onChange={e => setFilters(f => ({ ...f, search: e.target.value }))}
                style={{ flex: "1 1 180px", padding: "7px 0", border: "none", borderBottom: `2px solid ${T.ink}`, background: "transparent", color: T.ink, fontSize: "13px", outline: "none", fontFamily: "Georgia, serif" }} />
              {[
                { k: "category", opts: ["Product/Tool","AI Model","Research Paper","Industry News","Tutorial/Guide","Platform/Infrastructure"], ph: "All sections" },
                { k: "source",   opts: ["Hacker News","arXiv","Medium","NewsAPI"], ph: "All sources" },
              ].map(({ k, opts, ph }) => (
                <select key={k} value={filters[k]} onChange={e => setFilters(f => ({ ...f, [k]: e.target.value }))}
                  style={{ padding: "7px 4px", border: "none", borderBottom: `2px solid ${filters[k] ? T.ink : T.rule}`, background: "transparent", color: filters[k] ? T.ink : T.muted, fontSize: "12px", cursor: "pointer", outline: "none", fontFamily: "'Barlow Condensed', sans-serif", letterSpacing: "0.06em" }}>
                  <option value="">{ph}</option>
                  {opts.map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              ))}
              <label style={{ display: "flex", alignItems: "center", gap: "8px", fontSize: "11px", color: T.muted, fontFamily: "'Barlow Condensed', sans-serif", letterSpacing: "0.08em", whiteSpace: "nowrap" }}>
                MIN RELEVANCE {filters.min_relevance || "ANY"}
                <input type="range" min={0} max={9} value={filters.min_relevance}
                  onChange={e => setFilters(f => ({ ...f, min_relevance: +e.target.value }))}
                  style={{ width: "70px", accentColor: T.ink }} />
              </label>
              <span style={{ marginLeft: "auto", fontSize: "11px", color: T.faint, fontFamily: "'Barlow Condensed', sans-serif" }}>{articles.length} STORIES</span>
            </div>

            {loading ? (
              <div style={{ padding: "80px", textAlign: "center" }}>
                <p style={{ fontFamily: "'Playfair Display', serif", fontSize: "20px", color: T.muted, fontStyle: "italic" }}>Gathering intelligence…</p>
              </div>
            ) : articles.length === 0 ? (
              <div style={{ padding: "80px", textAlign: "center" }}>
                <p style={{ fontFamily: "'Playfair Display', serif", fontSize: "20px", color: T.muted, fontStyle: "italic" }}>No stories match your filters.</p>
              </div>
            ) : (
              <>
                {/* Stats row */}
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", borderBottom: `1px solid ${T.rule}`, margin: "0 0 28px" }}>
                  {[
                    { label: "Articles Indexed",  val: stats?.total_articles || 0 },
                    { label: "Products & Tools",   val: stats?.product_articles || 0 },
                    { label: "Sources Active",     val: 4 },
                    { label: "Subscribers",        val: usersData?.users?.length || 0 },
                  ].map(({ label, val }) => (
                    <div key={label} style={{ padding: "18px 0 16px", borderRight: `1px solid ${T.rule}`, textAlign: "center" }}>
                      <div style={{ fontFamily: "'Playfair Display', serif", fontSize: "36px", fontWeight: 900, lineHeight: 1, color: T.ink }}>{val}</div>
                      <div style={{ fontSize: "9.5px", color: T.muted, marginTop: "5px", fontFamily: "'Barlow Condensed', sans-serif", letterSpacing: "0.12em", textTransform: "uppercase" }}>{label}</div>
                    </div>
                  ))}
                </div>

                {/* Lead story */}
                {lead && (
                  <>
                    <div style={{ marginBottom: "6px" }}><Stamp bg={T.red}>Lead Story</Stamp></div>
                    <ArticleCard article={lead} expanded={expandedId === lead.id} onToggle={() => setExpandedId(expandedId === lead.id ? null : lead.id)} isLead />
                  </>
                )}

                {/* Two-column grid */}
                <div style={{ display: "grid", gridTemplateColumns: "minmax(0,2fr) minmax(0,1fr)", gap: "0 36px" }}>
                  <div style={{ borderRight: `1px solid ${T.rule}`, paddingRight: "36px" }}>
                    <div style={{ padding: "10px 0 12px" }}><Stamp>Platform &amp; Tooling</Stamp></div>
                    <Rule my={8} />
                    {mainCol.map(a => (
                      <ArticleCard key={a.id} article={a} expanded={expandedId === a.id} onToggle={() => setExpandedId(expandedId === a.id ? null : a.id)} />
                    ))}
                  </div>

                  <div>
                    <div style={{ padding: "10px 0 12px" }}><Stamp bg={T.blue}>Research &amp; Models</Stamp></div>
                    <Rule my={8} />
                    {sideCol.map(a => (
                      <ArticleCard key={a.id} article={a} expanded={expandedId === a.id} onToggle={() => setExpandedId(expandedId === a.id ? null : a.id)} />
                    ))}

                    {/* Legend box */}
                    <div style={{ marginTop: "24px", padding: "16px", background: T.paperDk, border: `1px solid ${T.rule}` }}>
                      <p style={{ margin: "0 0 10px", fontSize: "9.5px", fontWeight: 700, color: T.muted, letterSpacing: "0.15em", textTransform: "uppercase", fontFamily: "'Barlow Condensed', sans-serif" }}>Sources</p>
                      {Object.entries(SRC_STYLE).map(([name, { bg }]) => (
                        <div key={name} style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "7px" }}>
                          <span style={{ width: "10px", height: "10px", background: bg, display: "inline-block", flexShrink: 0 }} />
                          <span style={{ fontSize: "11px", color: T.muted, fontFamily: "'Barlow Condensed', sans-serif" }}>{name}</span>
                        </div>
                      ))}
                      <Rule my={10} />
                      <p style={{ margin: 0, fontSize: "11px", color: T.faint, lineHeight: 1.6, fontFamily: "Georgia, serif", fontStyle: "italic" }}>
                        Click any headline to expand competitor intelligence. Stars rate platform engineering relevance (1–10).
                      </p>
                    </div>
                  </div>
                </div>
              </>
            )}
          </>
        )}

        {/* ── SUBSCRIBERS ─────────────────────────────────────────────────── */}
        {activeTab === "subscribers" && (
          <div style={{ maxWidth: "700px", paddingTop: "28px" }}>
            <DoubleRule my={0} />
            <h2 style={{ fontFamily: "'Playfair Display', serif", fontSize: "28px", margin: "18px 0 4px" }}>Subscriber Registry</h2>
            <p style={{ color: T.muted, fontSize: "13px", margin: "0 0 20px", fontFamily: "Georgia, serif" }}>Daily digest sent at 08:00 UTC. Capacity: 20 subscribers.</p>
            <Rule />
            {(usersData?.users || []).length === 0 ? (
              <p style={{ color: T.muted, fontFamily: "Georgia, serif", fontStyle: "italic" }}>No subscribers yet.</p>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    {["Name", "Email", "Min Relevance", "Sections"].map(h => (
                      <th key={h} style={{ padding: "8px 10px", textAlign: "left", fontSize: "9px", color: T.muted, letterSpacing: "0.15em", textTransform: "uppercase", borderBottom: `2px solid ${T.ink}`, fontFamily: "'Barlow Condensed', sans-serif" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(usersData?.users || []).map((u, i) => (
                    <tr key={u.email} style={{ borderBottom: `1px solid ${T.rule}`, background: i % 2 === 0 ? T.cream : T.paper }}>
                      <td style={{ padding: "10px", fontSize: "13px", fontWeight: 600 }}>{u.name}</td>
                      <td style={{ padding: "10px", fontSize: "12px", color: T.muted }}>{u.email}</td>
                      <td style={{ padding: "10px" }}><Stars score={u.min_relevance} /></td>
                      <td style={{ padding: "10px", fontSize: "11px", color: T.muted }}>{u.categories?.join(", ") || "All"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <div style={{ marginTop: "20px" }}>
              <button onClick={() => setShowSub(true)} style={{ padding: "11px 22px", border: "none", background: T.ink, color: T.paper, cursor: "pointer", fontWeight: 700, fontFamily: "'Barlow Condensed', sans-serif", letterSpacing: "0.12em", textTransform: "uppercase" }}>
                + ADD SUBSCRIBER
              </button>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer style={{ borderTop: `3px solid ${T.ink}`, padding: "20px 32px", background: T.ink, color: T.paper, display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "12px" }}>
        <span style={{ fontFamily: "'Playfair Display', serif", fontSize: "22px", fontWeight: 900 }}>AI SIGNAL</span>
        <span style={{ fontSize: "11px", color: T.faint, fontFamily: "'Barlow Condensed', sans-serif", letterSpacing: "0.1em" }}>CLAUDE HAIKU · HACKER NEWS · ARXIV · NEWSAPI · MEDIUM</span>
        <a href={`${API_BASE}/docs`} target="_blank" rel="noopener noreferrer" style={{ fontSize: "11px", color: T.faint, fontFamily: "'Barlow Condensed', sans-serif", letterSpacing: "0.1em", textDecoration: "none", borderBottom: `1px solid ${T.faint}` }}>API DOCS →</a>
      </footer>

      {showSub && <SubscribeDrawer onClose={() => setShowSub(false)} onSuccess={() => { setShowSub(false); setSubOk(true); setTimeout(() => setSubOk(false), 5000); }} />}

      {subOk && (
        <div style={{ position: "fixed", bottom: "24px", left: "50%", transform: "translateX(-50%)", background: T.ink, color: T.paper, padding: "14px 24px", fontFamily: "'Barlow Condensed', sans-serif", fontWeight: 700, fontSize: "13px", letterSpacing: "0.1em", zIndex: 300, borderLeft: `4px solid ${T.green}`, boxShadow: "0 8px 32px rgba(0,0,0,0.25)" }}>
          ✓ SUBSCRIBED — FIRST DIGEST ARRIVES TOMORROW AT 08:00 UTC
        </div>
      )}
    </div>
  );
}
