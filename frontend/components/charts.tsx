"use client";

import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Analytics, Reading } from "@/lib/api";

const tooltipStyle = { background: "#fff", border: "1px solid #e1e8e3", borderRadius: 6, fontSize: 12 };

export function TrendChart({ readings, dataKey, color, unit }: { readings: Reading[]; dataKey: "energy" | "power" | "current" | "voltage"; color: string; unit: string }) {
  const data = [...readings].reverse().map((item) => ({
    time: new Date(item.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    [dataKey]: item[dataKey],
  }));
  return <div className="chart-canvas"><ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ top: 8, right: 10, bottom: 0, left: -15 }}>
    <CartesianGrid stroke="#edf1ed" vertical={false} />
    <XAxis dataKey="time" tickLine={false} axisLine={false} tick={{ fill: "#82908a", fontSize: 11 }} minTickGap={28} />
    <YAxis tickLine={false} axisLine={false} tick={{ fill: "#82908a", fontSize: 11 }} width={42} />
    <Tooltip contentStyle={tooltipStyle} formatter={(value) => [`${Number(value).toFixed(3)} ${unit}`, dataKey]} />
    <Line type="monotone" dataKey={dataKey} stroke={color} strokeWidth={2.2} dot={false} activeDot={{ r: 4 }} />
  </LineChart></ResponsiveContainer></div>;
}

export function ScoreThresholdChart({ readings }: { readings: Reading[] }) {
  const data = [...readings].reverse().map((item) => ({
    time: new Date(item.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    score: item.anomaly_score,
    threshold: item.threshold,
  }));
  return <div className="chart-canvas"><ResponsiveContainer width="100%" height="100%"><LineChart data={data} margin={{ top: 8, right: 10, bottom: 0, left: -15 }}>
    <CartesianGrid stroke="#edf1ed" vertical={false} />
    <XAxis dataKey="time" tickLine={false} axisLine={false} tick={{ fill: "#82908a", fontSize: 11 }} minTickGap={28} />
    <YAxis tickLine={false} axisLine={false} tick={{ fill: "#82908a", fontSize: 11 }} width={55} />
    <Tooltip contentStyle={tooltipStyle} formatter={(value, name) => [Number(value).toFixed(6), name === "score" ? "Anomaly score" : "Threshold"]} />
    <Line type="monotone" dataKey="score" name="Anomaly score" stroke="#bd493b" strokeWidth={2} dot={false} />
    <Line type="monotone" dataKey="threshold" name="Threshold" stroke="#d08a31" strokeWidth={1.5} strokeDasharray="5 4" dot={false} />
  </LineChart></ResponsiveContainer></div>;
}

export function DailyEnergyChart({ analytics, dataKey = "daily" }: { analytics: Analytics; dataKey?: "daily" | "weekly" | "monthly" }) {
  const data = analytics[dataKey].map((row) => ({
    label: "day" in row ? row.day.slice(5) : row.period,
    energy: row.energy,
  }));
  return <div className="chart-canvas"><ResponsiveContainer width="100%" height="100%"><BarChart data={data} margin={{ top: 10, right: 8, bottom: 4, left: -15 }}>
    <CartesianGrid stroke="#edf1ed" vertical={false} />
    <XAxis dataKey="label" tickLine={false} axisLine={false} tick={{ fill: "#82908a", fontSize: 11 }} />
    <YAxis tickLine={false} axisLine={false} tick={{ fill: "#82908a", fontSize: 11 }} width={42} />
    <Tooltip contentStyle={tooltipStyle} formatter={(value) => [`${Number(value).toFixed(5)} kWh`, "Energy"]} />
    <Bar dataKey="energy" fill="#167a67" radius={[3, 3, 0, 0]} maxBarSize={34} />
  </BarChart></ResponsiveContainer></div>;
}

export function StatusDonut({ normal, anomaly }: { normal: number; anomaly: number }) {
  const data = [{ name: "Normal", value: normal }, { name: "Anomaly", value: anomaly }];
  return <div className="donut-wrap"><ResponsiveContainer width="100%" height="100%"><PieChart>
    <Pie data={data} dataKey="value" nameKey="name" innerRadius={52} outerRadius={72} paddingAngle={3} stroke="none">
      <Cell fill="#167a67" /><Cell fill="#c04f3e" />
    </Pie><Tooltip contentStyle={tooltipStyle} />
  </PieChart></ResponsiveContainer><div className="donut-center"><strong>{normal + anomaly}</strong><small>READINGS</small></div></div>;
}