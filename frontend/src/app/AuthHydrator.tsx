"use client";
import { useEffect } from "react";
import { useAuthStore } from "@/store/index";

export default function AuthHydrator() {
  const hydrate = useAuthStore((s) => s.hydrate);
  useEffect(() => { hydrate(); }, []);
  return null;
}