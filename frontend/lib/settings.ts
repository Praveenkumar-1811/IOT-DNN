"use client";

import { useSyncExternalStore } from "react";

const STORAGE_KEY = "poll_interval_seconds";

function subscribe(callback: () => void) {
  window.addEventListener("storage", callback);
  window.addEventListener("energy-settings-change", callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener("energy-settings-change", callback);
  };
}

function readInterval() {
  const value = Number(window.localStorage.getItem(STORAGE_KEY));
  return [1, 2, 5, 10].includes(value) ? value : 1;
}

export function usePollingInterval() {
  return useSyncExternalStore(subscribe, readInterval, () => 1);
}

export function savePollingInterval(value: number) {
  window.localStorage.setItem(STORAGE_KEY, String(value));
  window.dispatchEvent(new Event("energy-settings-change"));
}