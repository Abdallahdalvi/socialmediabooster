import { useEffect, useState, useRef, useCallback } from "react";
import "@/App.css";
import axios from "axios";
import { motion, AnimatePresence } from "framer-motion";
import {
  Terminal,
  Activity,
  Globe,
  Shield,
  Cpu,
  Play,
  RefreshCcw,
  AlertTriangle,
  ChevronRight,
  Radio,
  Zap,
  Server,
  MapPin,
  Youtube,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// ---------- Small UI atoms ----------
const StatCard = ({ icon: Icon, label, value, testid }) => (
  <div
    data-testid={testid}
    className="border border-zinc-800 bg-[#0A0A0A] p-5 relative overflow-hidden group"
  >
    <div className="absolute inset-0 opacity-0 group-hover:opacity-10 bg-emerald-500 transition-opacity" />
    <div className="flex items-center gap-2 text-zinc-500 text-xs uppercase tracking-widest font-mono">
      <Icon size={14} />
      {label}
    </div>
    <div className="mt-3 text-3xl font-mono text-emerald-400 tabular-nums">
      {value}
    </div>
  </div>
);

const LogLine = ({ evt }) => {
  const color =
    {
      info: "text-zinc-300",
      tor: "text-cyan-400",
      ip: "text-emerald-400",
      play: "text-yellow-300",
      ok: "text-emerald-300",
      error: "text-red-400",
      warn: "text-orange-400",
      done: "text-emerald-400 font-bold",
      sys: "text-zinc-500 italic",
    }[evt.level] || "text-zinc-300";
  const prefix =
    {
      info: "[i]",
      tor: "[TOR]",
      ip: "[IP]",
      play: "[▶]",
      ok: "[✓]",
      error: "[✗]",
      warn: "[!]",
      done: "[✔ DONE]",
      sys: "[sys]",
    }[evt.level] || "[·]";
  return (
    <div className="flex gap-2 font-mono text-[13px] leading-relaxed">
      <span className="text-zinc-600 shrink-0">
        {evt.ts ? new Date(evt.ts).toLocaleTimeString() : ""}
      </span>
      <span className={`${color} shrink-0`}>{prefix}</span>
      <span className={color}>{evt.msg}</span>
    </div>
  );
};

// ---------- Job Submission Form ----------
const DURATION_OPTIONS = [
  { v: "short",  l: "Short",   r: "30 – 60 s"    },
  { v: "medium", l: "Medium",  r: "90 – 180 s"   },
  { v: "long",   l: "Long",    r: "240 – 420 s"  },
  { v: "xlong",  l: "X-Long",  r: "460 – 800 s"  },
  { v: "custom", l: "Custom",  r: "fixed"        },
];

const JobForm = ({ countries, onCreated }) => {
  const [urls, setUrls] = useState("");
  const [views, setViews] = useState(6);
  const [watchSec, setWatchSec] = useState(8);
  const [durationPreset, setDurationPreset] = useState("medium");
  const [mode, setMode] = useState("random");
  const [selectedCountries, setSelectedCountries] = useState(["us", "gb", "de"]);
  const [browserMode, setBrowserMode] = useState("playwright");
  const [submitting, setSubmitting] = useState(false);

  const toggleCountry = (code) => {
    setSelectedCountries((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]
    );
  };

  const submit = async () => {
    setSubmitting(true);
    try {
      const list = urls
        .split("\n")
        .map((s) => s.trim())
        .filter(Boolean);
      const res = await axios.post(`${API}/jobs`, {
        video_urls: list,
        views_per_video: parseInt(views) || 1,
        watch_seconds: parseInt(watchSec) || 5,
        duration_preset: durationPreset,
        location_mode: mode,
        countries: mode === "specific" ? selectedCountries : [],
        browser_mode: browserMode,
      });
      onCreated(res.data);
      setUrls("");
    } catch (e) {
      alert(e?.response?.data?.detail || "Failed to create job");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="border border-zinc-800 bg-[#0A0A0A] p-6">
      <div className="flex items-center gap-2 mb-6">
        <Youtube size={18} className="text-emerald-400" />
        <h3 className="font-mono text-lg tracking-wide">NEW BATCH JOB</h3>
      </div>

      <label className="block text-xs font-mono uppercase text-zinc-500 mb-2 tracking-widest">
        Video URLs <span className="text-zinc-600">(one per line)</span>
      </label>
      <textarea
        data-testid="video-urls-input"
        value={urls}
        onChange={(e) => setUrls(e.target.value)}
        placeholder="https://www.youtube.com/watch?v=dQw4w9WgXcQ&#10;https://youtu.be/xvFZjo5PgG0"
        rows={4}
        className="w-full bg-black border border-zinc-800 focus:border-emerald-500 outline-none px-3 py-2 font-mono text-sm text-zinc-100 rounded-none"
      />

      <div className="grid grid-cols-2 gap-4 mt-5">
        <div>
          <label className="block text-xs font-mono uppercase text-zinc-500 mb-2 tracking-widest">
            Views per video
          </label>
          <input
            data-testid="views-per-video-input"
            type="number"
            min={1}
            max={50}
            value={views}
            onChange={(e) => setViews(e.target.value)}
            className="w-full bg-black border border-zinc-800 focus:border-emerald-500 outline-none px-3 py-2 font-mono text-sm rounded-none"
          />
        </div>
        <div>
          <label className="block text-xs font-mono uppercase text-zinc-500 mb-2 tracking-widest">
            Watch (custom)
          </label>
          <input
            data-testid="watch-seconds-input"
            type="number"
            min={3}
            max={1200}
            value={watchSec}
            onChange={(e) => setWatchSec(e.target.value)}
            disabled={durationPreset !== "custom"}
            className={`w-full bg-black border outline-none px-3 py-2 font-mono text-sm rounded-none ${
              durationPreset === "custom"
                ? "border-zinc-800 focus:border-emerald-500 text-zinc-100"
                : "border-zinc-900 text-zinc-600"
            }`}
          />
        </div>
      </div>

      <div className="mt-5">
        <label className="block text-xs font-mono uppercase text-zinc-500 mb-2 tracking-widest">
          Watch Duration
        </label>
        <div className="grid grid-cols-5 gap-1.5">
          {DURATION_OPTIONS.map((opt) => (
            <button
              key={opt.v}
              data-testid={`duration-preset-${opt.v}`}
              onClick={() => setDurationPreset(opt.v)}
              className={`px-2 py-2 border font-mono text-[10px] uppercase tracking-wider transition-colors text-left ${
                durationPreset === opt.v
                  ? "border-emerald-500 bg-emerald-500/10 text-emerald-300"
                  : "border-zinc-800 bg-black text-zinc-500 hover:border-zinc-600"
              }`}
            >
              <div className="text-[11px]">{opt.l}</div>
              <div className="text-[9px] opacity-70">{opt.r}</div>
            </button>
          ))}
        </div>
        <p className="text-[10px] font-mono text-zinc-600 mt-1">
          {durationPreset !== "custom"
            ? "Each video watches a randomised duration in the selected range."
            : "All videos watch the exact 'Watch (custom)' seconds above."}
        </p>
      </div>

      <div className="mt-5">
        <label className="block text-xs font-mono uppercase text-zinc-500 mb-2 tracking-widest">
          Location Strategy
        </label>
        <div className="grid grid-cols-3 gap-2">
          {[
            { v: "random", l: "Random Worldwide" },
            { v: "specific", l: "Specific List" },
            { v: "auto", l: "Auto-match audience" },
          ].map((opt) => (
            <button
              data-testid={`location-mode-${opt.v}`}
              key={opt.v}
              onClick={() => setMode(opt.v)}
              className={`px-3 py-2 border font-mono text-xs uppercase tracking-wider transition-colors ${
                mode === opt.v
                  ? "border-emerald-500 bg-emerald-500/10 text-emerald-300"
                  : "border-zinc-800 bg-black text-zinc-500 hover:border-zinc-600"
              }`}
            >
              {opt.l}
            </button>
          ))}
        </div>
      </div>

      {mode === "specific" && (
        <div className="mt-4">
          <div className="text-xs font-mono uppercase text-zinc-500 mb-2 tracking-widest">
            Select exit countries
          </div>
          <div className="flex flex-wrap gap-1.5">
            {countries.map((c) => (
              <button
                key={c.code}
                data-testid={`country-chip-${c.code}`}
                onClick={() => toggleCountry(c.code)}
                className={`px-2.5 py-1 border font-mono text-[11px] uppercase ${
                  selectedCountries.includes(c.code)
                    ? "border-emerald-500 bg-emerald-500/10 text-emerald-300"
                    : "border-zinc-800 text-zinc-500 hover:border-zinc-600"
                }`}
              >
                {c.code} · {c.name}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="mt-5">
        <label className="block text-xs font-mono uppercase text-zinc-500 mb-2 tracking-widest">
          Browser Engine
        </label>
        <div className="grid grid-cols-2 gap-2">
          {[
            { v: "playwright", l: "Playwright (real Chromium)" },
            { v: "http", l: "HTTP (fast fallback)" },
          ].map((opt) => (
            <button
              data-testid={`browser-mode-${opt.v}`}
              key={opt.v}
              onClick={() => setBrowserMode(opt.v)}
              className={`px-3 py-2 border font-mono text-xs uppercase tracking-wider transition-colors ${
                browserMode === opt.v
                  ? "border-emerald-500 bg-emerald-500/10 text-emerald-300"
                  : "border-zinc-800 bg-black text-zinc-500 hover:border-zinc-600"
              }`}
            >
              {opt.l}
            </button>
          ))}
        </div>
      </div>

      <button
        data-testid="start-job-btn"
        onClick={submit}
        disabled={submitting || !urls.trim()}
        className="mt-6 w-full bg-emerald-500 hover:bg-emerald-400 disabled:bg-zinc-800 disabled:text-zinc-500 text-black font-mono text-sm uppercase tracking-widest py-3 flex items-center justify-center gap-2 transition-colors"
      >
        <Play size={16} />
        {submitting ? "Launching…" : "Launch Batch (rotate every 3)"}
      </button>
    </div>
  );
};

// ---------- Live Job Panel ----------
const LiveJobPanel = ({ job, logs }) => {
  const scrollRef = useRef(null);
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  const total = job?.total_videos || 0;
  const processed = job?.processed_videos || 0;
  const progress = total ? Math.round((processed / total) * 100) : 0;
  const nextRotIn = total ? 3 - (processed % 3 || 3) + (processed % 3 === 0 && processed > 0 ? 3 : 0) : 3;
  const nextRotationDisplay = total && processed < total ? (3 - (processed % 3)) % 3 || 3 : 0;

  return (
    <div className="border border-zinc-800 bg-[#0A0A0A]">
      <div className="border-b border-zinc-800 px-5 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2 font-mono text-sm">
          <Radio size={14} className={job?.status === "running" ? "text-emerald-400 animate-pulse" : "text-zinc-600"} />
          <span className="text-zinc-400 uppercase tracking-widest text-xs">Live Job</span>
          <span className="text-zinc-500 text-xs">·</span>
          <span className="text-emerald-400 text-xs">{job?.status || "idle"}</span>
        </div>
        <div className="font-mono text-[11px] text-zinc-500">{job?.id?.slice(0, 8) || "—"}</div>
      </div>

      <div className="grid grid-cols-4 divide-x divide-zinc-800 border-b border-zinc-800">
        <div className="p-4">
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-mono">Current IP</div>
          <div data-testid="current-ip" className="mt-1 font-mono text-emerald-400 text-sm tabular-nums">
            {job?.current_ip || "—"}
          </div>
        </div>
        <div className="p-4">
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-mono">Country</div>
          <div data-testid="current-country" className="mt-1 font-mono text-zinc-100 text-sm flex items-center gap-1">
            <MapPin size={12} className="text-emerald-500" />
            {job?.current_country || "—"}
            {job?.current_country_code ? (
              <span className="text-zinc-500 text-[10px] ml-1">
                [{job.current_country_code.toUpperCase()}]
              </span>
            ) : null}
          </div>
        </div>
        <div className="p-4">
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-mono">Progress</div>
          <div className="mt-1 font-mono text-zinc-100 text-sm">
            {processed}/{total} <span className="text-zinc-500">({progress}%)</span>
          </div>
        </div>
        <div className="p-4">
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-mono">Next rotation</div>
          <div className="mt-1 font-mono text-yellow-400 text-sm">
            {job?.status === "running" && processed < total ? `in ${nextRotationDisplay} video(s)` : "—"}
          </div>
        </div>
      </div>

      <div className="h-1 bg-zinc-900">
        <div
          className="h-full bg-emerald-500 transition-all"
          style={{ width: `${progress}%` }}
        />
      </div>

      <div
        ref={scrollRef}
        className="bg-black h-[380px] overflow-y-auto p-4 space-y-1 relative"
        style={{
          backgroundImage:
            "repeating-linear-gradient(0deg, rgba(255,255,255,0.02) 0px, rgba(255,255,255,0.02) 1px, transparent 1px, transparent 3px)",
        }}
      >
        {logs.length === 0 && (
          <div className="text-zinc-600 font-mono text-sm">Waiting for events…</div>
        )}
        {logs.map((e, i) => (
          <LogLine evt={e} key={i} />
        ))}
      </div>
    </div>
  );
};

// ---------- Job History ----------
const JobHistory = ({ jobs, onSelect, activeId }) => (
  <div className="border border-zinc-800 bg-[#0A0A0A]">
    <div className="px-5 py-3 border-b border-zinc-800 flex items-center gap-2 font-mono text-sm">
      <Server size={14} className="text-emerald-400" />
      <span className="uppercase tracking-widest text-xs text-zinc-400">Job History</span>
    </div>
    <div className="max-h-[340px] overflow-y-auto">
      {jobs.length === 0 && (
        <div className="p-5 font-mono text-zinc-600 text-sm">No jobs yet.</div>
      )}
      {jobs.map((j) => {
        const total = j.total_videos || j.video_urls.length * j.views_per_video;
        const pct = total ? Math.round((j.processed_videos / total) * 100) : 0;
        return (
          <button
            key={j.id}
            data-testid={`job-item-${j.id}`}
            onClick={() => onSelect(j.id)}
            className={`w-full text-left px-5 py-3 border-b border-zinc-900 hover:bg-zinc-900/40 transition-colors ${
              activeId === j.id ? "bg-zinc-900/60" : ""
            }`}
          >
            <div className="flex items-center justify-between font-mono text-xs">
              <span className="text-emerald-400">{j.id.slice(0, 8)}</span>
              <span
                className={
                  j.status === "completed"
                    ? "text-emerald-400"
                    : j.status === "running"
                    ? "text-yellow-400 animate-pulse"
                    : "text-zinc-500"
                }
              >
                {j.status}
              </span>
            </div>
            <div className="mt-1 text-[11px] text-zinc-500 font-mono truncate">
              {j.video_urls.length} URLs · {j.views_per_video} v/ea · mode: {j.location_mode}
            </div>
            <div className="mt-2 h-0.5 bg-zinc-900">
              <div className="h-full bg-emerald-500" style={{ width: `${pct}%` }} />
            </div>
          </button>
        );
      })}
    </div>
  </div>
);

// ---------- Educational Section ----------
const EduSection = () => (
  <section className="mt-24 border-t border-zinc-900 pt-16">
    <div className="grid grid-cols-1 md:grid-cols-3 gap-10">
      <div>
        <div className="text-emerald-400 font-mono text-xs uppercase tracking-widest mb-3">
          01 / What are YouTube Views?
        </div>
        <p className="text-zinc-400 text-sm leading-relaxed">
          A view is counted when a viewer intentionally initiates the playing of a
          video and watches for a meaningful duration. View counts influence
          discoverability, ranking, and recommendation weight inside YouTube&apos;s
          algorithmic surfaces.
        </p>
      </div>
      <div>
        <div className="text-emerald-400 font-mono text-xs uppercase tracking-widest mb-3">
          02 / Watch Hours
        </div>
        <p className="text-zinc-400 text-sm leading-relaxed">
          Watch time is the total minutes viewers spend watching. Channels need at
          least <span className="text-emerald-300">4,000 watch hours</span> in the last
          12 months and 1,000 subscribers to qualify for the YouTube Partner Program.
        </p>
      </div>
      <div>
        <div className="text-emerald-400 font-mono text-xs uppercase tracking-widest mb-3">
          03 / Why IP Rotation?
        </div>
        <p className="text-zinc-400 text-sm leading-relaxed">
          Automated traffic from a single IP is trivially fingerprinted. By routing
          each batch of <span className="text-emerald-300">3 videos</span> through a
          fresh Tor circuit — often exiting from a different country — traffic
          patterns look geographically distributed and organic in an educational
          test environment.
        </p>
      </div>
    </div>

    <div className="mt-16 grid grid-cols-1 md:grid-cols-2 gap-8">
      <div>
        <h3 className="font-mono text-2xl mb-4">Tips to Increase Views Organically</h3>
        <ul className="space-y-3 text-zinc-400 text-sm">
          {[
            "Design attention-grabbing thumbnails that honestly represent your video.",
            "Write specific, keyword-rich titles under 60 characters.",
            "Invest in the first 15 seconds — retention there dictates the algorithm's decision.",
            "Optimize descriptions with chapters, links, and keywords.",
            "Publish on a consistent schedule to build audience anticipation.",
            "Collaborate — you inherit each other's audience for free.",
          ].map((t, i) => (
            <li key={i} className="flex gap-3">
              <ChevronRight size={14} className="text-emerald-500 mt-1 shrink-0" />
              <span>{t}</span>
            </li>
          ))}
        </ul>
      </div>
      <div className="border border-zinc-800 bg-[#0A0A0A] p-6">
        <div className="flex items-center gap-2 font-mono text-sm text-yellow-400">
          <AlertTriangle size={16} />
          ETHICS & LEGAL DISCLAIMER
        </div>
        <p className="mt-4 text-zinc-400 text-sm leading-relaxed">
          This tool is provided <span className="text-emerald-300">strictly for
          educational and research purposes</span> — to study Tor circuit rotation,
          browser fingerprinting, and traffic distribution. Using automated tooling to
          inflate YouTube view counts violates YouTube&apos;s Terms of Service and can lead
          to permanent channel termination or worse.
        </p>
        <p className="mt-3 text-zinc-500 text-xs font-mono">
          You are responsible for how you use this software.
        </p>
      </div>
    </div>
  </section>
);

// ---------- Root App ----------
function App() {
  const [countries, setCountries] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [activeJobId, setActiveJobId] = useState(null);
  const [activeJob, setActiveJob] = useState(null);
  const [logs, setLogs] = useState([]);
  const [torStatus, setTorStatus] = useState({ ip: null, country: null });
  const [stats, setStats] = useState({
    total_jobs: 0,
    total_views_delivered: 0,
    unique_ips: 0,
    countries: 0,
  });

  const loadCountries = async () => {
    const r = await axios.get(`${API}/countries`);
    setCountries(r.data.list);
  };
  const loadJobs = useCallback(async () => {
    const r = await axios.get(`${API}/jobs`);
    setJobs(r.data);
    if (!activeJobId && r.data[0]) setActiveJobId(r.data[0].id);
  }, [activeJobId]);
  const loadStats = async () => {
    const r = await axios.get(`${API}/stats`);
    setStats(r.data);
  };
  const loadTor = async () => {
    try {
      const r = await axios.get(`${API}/tor/status`);
      setTorStatus(r.data);
    } catch {
      setTorStatus({ ip: null, country: "offline" });
    }
  };

  useEffect(() => {
    loadCountries();
    loadJobs();
    loadStats();
    loadTor();
    const t1 = setInterval(loadJobs, 4000);
    const t2 = setInterval(loadStats, 6000);
    return () => {
      clearInterval(t1);
      clearInterval(t2);
    };
  }, []);

  // Track active job details
  useEffect(() => {
    if (!activeJobId) return;
    const j = jobs.find((x) => x.id === activeJobId);
    if (j) setActiveJob(j);
  }, [jobs, activeJobId]);

  // SSE subscription for active job
  useEffect(() => {
    if (!activeJobId) return;
    setLogs([]);
    const es = new EventSource(`${API}/jobs/${activeJobId}/stream`);
    es.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data);
        setLogs((prev) => [...prev.slice(-300), data]);
      } catch {
        /* ignore malformed events */
      }
    };
    es.onerror = () => {
      es.close();
    };
    return () => es.close();
  }, [activeJobId]);

  return (
    <div className="min-h-screen bg-[#050505] text-zinc-100">
      {/* Top strip */}
      <div className="border-b border-zinc-900 bg-black">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between font-mono text-xs">
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-zinc-400">ytviews_lab</span>
            <span className="text-zinc-700">/</span>
            <span className="text-zinc-500">tor_rotation_engine</span>
          </div>
          <div className="hidden md:flex items-center gap-4 text-zinc-500">
            <span className="flex items-center gap-1">
              <Shield size={12} className="text-emerald-500" /> tor:{torStatus.ok ? "up" : "checking"}
            </span>
            <span data-testid="global-tor-ip">
              exit: <span className="text-emerald-400">{torStatus.ip || "…"}</span>
            </span>
            <span>country: <span className="text-emerald-400">{torStatus.country || "…"}</span></span>
          </div>
        </div>
      </div>

      {/* Hero */}
      <header className="max-w-7xl mx-auto px-6 pt-16 pb-10">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <div className="text-emerald-400 font-mono text-xs uppercase tracking-[0.3em] mb-4">
            &gt; educational / red-team research tool
          </div>
          <h1 className="font-mono text-4xl md:text-6xl leading-[1.05] tracking-tight max-w-4xl">
            YouTube Views Booster
            <br />
            <span className="text-emerald-400">with Tor IP Rotation</span>
          </h1>
          <p className="mt-6 text-zinc-400 max-w-2xl text-lg leading-relaxed">
            Simulate distributed traffic to any YouTube URL. Every{" "}
            <span className="text-emerald-300 font-mono">3 videos</span>, the engine
            builds a fresh Tor circuit and exits from a different geography — no fingerprint
            reuse, no single-IP anti-bot flags.
          </p>
        </motion.div>
      </header>

      {/* Stats */}
      <section className="max-w-7xl mx-auto px-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard testid="stat-total-views" icon={Activity} label="Views Delivered" value={stats.total_views_delivered} />
          <StatCard testid="stat-unique-ips" icon={Cpu} label="Unique Exit IPs" value={stats.unique_ips} />
          <StatCard testid="stat-countries" icon={Globe} label="Countries Covered" value={stats.countries} />
          <StatCard testid="stat-jobs" icon={Zap} label="Total Jobs" value={stats.total_jobs} />
        </div>
      </section>

      {/* Main */}
      <main className="max-w-7xl mx-auto px-6 mt-10 grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 space-y-6">
          <JobForm
            countries={countries}
            onCreated={(j) => {
              setActiveJobId(j.id);
              loadJobs();
            }}
          />
          <JobHistory jobs={jobs} activeId={activeJobId} onSelect={setActiveJobId} />
        </div>

        <div className="lg:col-span-2">
          <LiveJobPanel job={activeJob} logs={logs} />
          <div className="mt-4 border border-zinc-800 bg-[#0A0A0A] p-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Terminal size={14} className="text-emerald-400" />
              <span className="font-mono text-xs text-zinc-500 uppercase tracking-widest">
                Rotation policy
              </span>
              <span className="font-mono text-xs text-zinc-300">
                new tor circuit every{" "}
                <span className="text-emerald-400">3 videos</span>
              </span>
            </div>
            <button
              data-testid="manual-rotate-btn"
              onClick={async () => {
                await axios.post(`${API}/tor/rotate`, {});
                await loadTor();
              }}
              className="border border-zinc-800 hover:border-emerald-500 hover:text-emerald-400 px-3 py-1.5 text-xs font-mono uppercase tracking-widest flex items-center gap-2 transition-colors"
            >
              <RefreshCcw size={12} /> Force Rotate Now
            </button>
          </div>
        </div>
      </main>

      <div className="max-w-7xl mx-auto px-6 pb-24">
        <EduSection />
      </div>

      <footer className="border-t border-zinc-900 py-8">
        <div className="max-w-7xl mx-auto px-6 flex items-center justify-between font-mono text-xs text-zinc-600">
          <span>ytviews_lab © research</span>
          <span>engine: tor + playwright · rotation: every 3 videos</span>
        </div>
      </footer>
    </div>
  );
}

export default App;
