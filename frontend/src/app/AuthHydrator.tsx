hydrate: () => {
    const token = localStorage.getItem("token");
    const raw = localStorage.getItem("user");
    if (token && raw) {
      try {
        set({ token, user: JSON.parse(raw) });
      } catch {}
    }
    set({ isHydrated: true });
  },