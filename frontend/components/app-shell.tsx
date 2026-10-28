"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, AlertTriangle, BarChart3, Bolt, Cpu, Database, History, Radio, Settings2, Wifi } from "lucide-react";
import { useEffect, useState } from "react";
import { API_URL, api } from "@/lib/api";

const navigation = [
  { href: "/", label: "Dashboard", icon: Activity },
  { href: "/live", label: "Live monitoring", icon: Radio },
  { href: "/anomalies", label: "Anomalies", icon: AlertTriangle },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/history", label: "Reading history", icon: History },
  { href: "/datasets", label: "Datasets", icon: Database },
  { href: "/model", label: "Model", icon: Cpu },
  { href: "/settings", label: "Settings", icon: Settings2 },
  { href: "/system", label: "System status", icon: Wifi },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [modelReady, setModelReady] = useState(false);

  useEffect(() => {
    let active = true;
    const check = async () => {
      try {
        const health = await api.health();
        if (active) {
          setApiOnline(health.database);
          setModelReady(health.model);
        }
      } catch {
        if (active) setApiOnline(false);
      }
    };
    void check();
    const timer = window.setInterval(check, 10000);
    return () => { active = false; window.clearInterval(timer); };
  }, []);

  return (
    <div className="app-frame">
      <aside className="sidebar">
        <Link className="brand" href="/">
          <span className="brand-mark"><Bolt size={20} strokeWidth={2.4} /></span>
          <span><strong>GRID / ROOM</strong><small>BUILDING ENERGY INTELLIGENCE</small></span>
        </Link>
        <div className="nav-caption">WORKSPACE</div>
        <nav className="nav-list" aria-label="Main navigation">
          {navigation.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return <Link className={`nav-link${active ? " active" : ""}`} href={href} key={href} aria-current={active ? "page" : undefined}>
              <Icon size={17} strokeWidth={1.8} /><span>{label}</span>{label === "Anomalies" && <span className="nav-indicator" />}
            </Link>;
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className={`system-status ${apiOnline === false ? "offline" : ""}`}>
            <span className="status-dot" />
            <span><strong>{apiOnline === null ? "CONNECTING" : apiOnline ? "SYSTEM ONLINE" : "API UNAVAILABLE"}</strong><small>FastAPI · SQLite</small></span>
          </div>
          <div className="model-status"><Cpu size={15} /><span>Autoencoder</span><b>{modelReady ? "READY" : "SETUP"}</b></div>
        </div>
      </aside>
      <main className="main-column">
        <header className="topbar">
          <div className="topbar-path"><span className="topbar-mobile-mark"><Bolt size={16} /></span>ENERGY MONITORING <span>/</span> {navigation.find((item) => item.href === pathname)?.label.toUpperCase() ?? "WORKSPACE"}</div>
          <div className="topbar-right"><span className="live-badge"><span />{apiOnline ? "API ONLINE" : apiOnline === false ? "API OFFLINE" : "CONNECTING"}</span><span className="api-address"><Wifi size={14} />{API_URL}</span></div>
        </header>
        <div className="page-content">{children}</div>
      </main>
    </div>
  );
}