"use client";
import { useEffect } from "react";
import { useAuthStore } from "@/store";

export default function AuthHydrator() {
  const hydrate = useAuthStore((s) => s.hydrate);
  useEffect(() => {
    hydrate();
  }, []);
  return null;
}