import { useEffect, useState, useRef, useCallback } from "react";
import "@/App.css";
import axios from "axios";
import { motion } from "framer-motion";
import {
  Terminal,
  Activity,
  Globe,
  Shield,
  Cpu,
  Play,
  AlertTriangle,
  ChevronRight,
  Radio,
  Zap,
  Server,
  MapPin,
  Youtube,
  Maximize2,
} from "lucide-react";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
const API = `${BACKEND_URL}/api`;

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

const DURATION_OPTIONS = [
  { v: "short", l: "Short", r: "30–60 s" },
  { v: "medium", l: "Medium", r: "90–180 s" },
  { v: "long", l: "Long", r: "240–420 s" },
  { v: "xlong", l: "X-Long", r: "460–800 s" },
];

const JobForm = ({ onCreated }) => {
  const [urls, setUrls] = useState("");
  const [views, setViews] = useState(3);
  const [durationPreset, setDurationPreset] = useState("medium");
  const [maxWindows, setMaxWindows] = useState(3);
  const [submitting, setSubmitting] = useState(false);

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
        duration_preset: durationPreset,
        max_visible_windows: parseInt(maxWindows) || 3,
        browser_mode: "visible",
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
        <Maximize2 size={18} className="text-emerald-400" />
        <h3 className="font-mono text-lg tracking-wide">VISIBLE BROWSERS</h3>
      </div>

      <label className="block text-xs font-mono uppercase text-zinc-500 mb-2 tracking-widest">
        YouTube URLs <span className="text-zinc-600">(one per line)</span>
      </label>
      <textarea
        value={urls}
        onChange={(e) => setUrls(e.target.value)}
        placeholder="https://www.youtube.com/watch?v=dQw4w9WgXcQ&#10;https://youtu.be/xvFZjo5PgG0"
        rows={4}
        className="w-full bg-black border border-zinc-800 focus:border-emerald-500 outline-none px-3 py-2 font-mono text-sm text-zinc-100 rounded-none"
      />

      <div className="grid grid-cols-2 gap-4 mt-5">
        <div>
          <label className="block text-xs font-mono uppercase text-zinc-500 mb-2 tracking-widest">
            Views per Video
          </label>
          <input
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
            Visible Windows (1-5)
          </label>
          <input
            type="number"
            min={1}
            max={5}
            value={maxWindows}
            onChange={(e) => setMaxWindows(e.target.value)}
            className="w-full bg-black border border-zinc-800 focus:border-emerald-500 outline-none px-3 py-2 font-mono text-sm rounded-none"
          />
        </div>
      </div>

      <div className="mt-5">
        <label className="block text-xs font-mono uppercase text-zinc-500 mb-2 tracking-widest">
          Watch Duration per Video
        </label>
        <div className="grid grid-cols-4 gap-1.5">
          {DURATION_OPTIONS.map((opt) => (
            <button
              key={opt.v}
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
      </div>

      <div className="mt-5 p-3 border border-cyan-900 bg-cyan-950/30 rounded text-xs text-cyan-300 font-mono">
        ✓ Each window opens visibly, rotates Tor IP, watches video
        <br />
        ✓ You can see & interact with browsers
        <br />
        ✓ Moves between windows automatically
        <br />
        ✓ Like YTMonster/YTViews.webappbazaar.com
      </div>

      <button
        onClick={submit}
        disabled={submitting || !urls.trim()}
        className="mt-6 w-full bg-emerald-500 hover:bg-emerald-400 disabled:bg-zinc-800 disabled:text-zinc-500 text-black font-mono text-sm uppercase tracking-widest py-3 flex items-center justify-center gap-2"
      >
        <Play size={16} />
        {submitting ? "Starting..." : "Launch Visible Browsers"}
      </button>
    </div>
  );
};

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

  return (
    <div className="border border-zinc-800 bg-[#0A0A0A]">
      <div className="border-b border-zinc-800 px-5 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2 font-mono text-sm">
          <Radio
            size={14}
            className={job?.status === "running" ? "text-emerald-400 animate-pulse" : "text-zinc-600"}
          />
          <span className="text-zinc-400 uppercase tracking-widest text-xs">Live Status</span>
          <span className="text-zinc-500 text-xs">·</span>
          <span className="text-emerald-400 text-xs">{job?.status || "idle"}</span>
        </div>
        <div className="font-mono text-[11px] text-zinc-500">{job?.id?.slice(0, 8) || "—"}</div>
      </div>

      <div className="grid grid-cols-5 divide-x divide-zinc-800 border-b border-zinc-800">
        <div className="p-4">
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-mono">Progress</div>
          <div className="mt-1 font-mono text-emerald-400 text-sm">{progress}%</div>
        </div>
        <div className="p-4">
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-mono">Watched</div>
          <div className="mt-1 font-mono text-zinc-100 text-sm">{processed}/{total}</div>
        </div>
        <div className="p-4">
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-mono">Delivered</div>
          <div className="mt-1 font-mono text-emerald-300 text-sm">{job?.total_views_delivered || 0}</div>
        </div>
        <div className="p-4">
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-mono">Failed</div>
          <div className="mt-1 font-mono text-red-400 text-sm">{job?.failures || 0}</div>
        </div>
        <div className="p-4">
          <div className="text-[10px] uppercase tracking-widest text-zinc-500 font-mono">Unique IPs</div>
          <div className="mt-1 font-mono text-cyan-400 text-sm">{(job?.unique_ips || []).length}</div>
        </div>
      </div>

      <div className="h-1 bg-zinc-900">
        <div className="h-full bg-emerald-500 transition-all" style={{ width: `${progress}%` }} />
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

function App() {
  const [jobs, setJobs] = useState([]);
  const [activeJobId, setActiveJobId] = useState(null);
  const [activeJob, setActiveJob] = useState(null);
  const [logs, setLogs] = useState([]);
  const [stats, setStats] = useState({
    total_jobs: 0,
    total_views_delivered: 0,
    unique_ips: 0,
    countries: 0,
  });

  const loadJobs = useCallback(async () => {
    try {
      const r = await axios.get(`${API}/jobs`);
      setJobs(r.data);
      if (!activeJobId && r.data[0]) setActiveJobId(r.data[0].id);
    } catch (e) {
      console.error("Failed to load jobs", e);
    }
  }, [activeJobId]);

  const loadStats = async () => {
    try {
      const r = await axios.get(`${API}/stats`);
      setStats(r.data);
    } catch (e) {
      console.error("Failed to load stats", e);
    }
  };

  useEffect(() => {
    loadJobs();
    loadStats();
    const t1 = setInterval(loadJobs, 2000);
    const t2 = setInterval(loadStats, 4000);
    return () => {
      clearInterval(t1);
      clearInterval(t2);
    };
  }, [loadJobs]);

  useEffect(() => {
    if (!activeJobId) return;
    const j = jobs.find((x) => x.id === activeJobId);
    if (j) setActiveJob(j);
  }, [jobs, activeJobId]);

  useEffect(() => {
    if (!activeJobId) return;
    setLogs([]);
    const es = new EventSource(`${API}/jobs/${activeJobId}/stream`);
    es.onmessage = (msg) => {
      try {
        const data = JSON.parse(msg.data);
        setLogs((prev) => [...prev.slice(-300), data]);
      } catch {
        /* ignore */
      }
    };
    es.onerror = () => es.close();
    return () => es.close();
  }, [activeJobId]);

  return (
    <div className="min-h-screen bg-[#050505] text-zinc-100">
      <div className="border-b border-zinc-900 bg-black">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between font-mono text-xs">
          <div className="flex items-center gap-3">
            <div className="w-2 h-2 rounded-full bg-cyan-500 animate-pulse" />
            <span className="text-zinc-400">ytviews</span>
            <span className="text-zinc-700">/</span>
            <span className="text-zinc-500">visible_browsers_v2</span>
          </div>
        </div>
      </div>

      <header className="max-w-7xl mx-auto px-6 pt-16 pb-10">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <h1 className="font-mono text-4xl md:text-6xl leading-[1.05] tracking-tight max-w-4xl">
            YT Views Booster
            <br />
            <span className="text-cyan-400">Visible Browsers Edition</span>
          </h1>
          <p className="mt-6 text-zinc-400 max-w-2xl text-sm leading-relaxed">
            Opens real, visible Chromium windows. Each rotates Tor IP, watches your video,
            then closes. Repeat N times with different IPs. Just like YTMonster.
          </p>
        </motion.div>
      </header>

      <section className="max-w-7xl mx-auto px-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard icon={Activity} label="Total Viewed" value={stats.total_views_delivered} />
          <StatCard icon={Cpu} label="Unique IPs" value={stats.unique_ips} />
          <StatCard icon={Globe} label="Countries" value={stats.countries} />
          <StatCard icon={Zap} label="Jobs" value={stats.total_jobs} />
        </div>
      </section>

      <main className="max-w-7xl mx-auto px-6 mt-10 grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1 space-y-6">
          <JobForm
            onCreated={(j) => {
              setActiveJobId(j.id);
              loadJobs();
            }}
          />
        </div>

        <div className="lg:col-span-2">
          <LiveJobPanel job={activeJob} logs={logs} />
        </div>
      </main>
    </div>
  );
}

export default App;
