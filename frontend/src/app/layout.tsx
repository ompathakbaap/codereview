"use client";
import type { Metadata } from "next";
import "./globals.css";
import { Toaster } from "react-hot-toast";
import { useEffect } from "react";
import { useAuthStore } from "@/store/index";

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const hydrate = useAuthStore((s) => s.hydrate);

  useEffect(() => {
    hydrate();
  }, []);

  return (
    <html lang="en">
      <body>
        {children}
        <Toaster
          position="bottom-right"
          toastOptions={{
            style: {
              background: "#13161e",
              color: "#e8eaf0",
              border: "1px solid #1e2330",
              fontFamily: "'DM Sans', sans-serif",
            },
          }}
        />
      </body>
    </html>
  );
}