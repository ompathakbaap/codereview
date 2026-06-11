import { create } from "zustand";
import { User, Review, Issue, Comment } from "@/types";
import api from "@/lib/api";

// ── Auth Store ────────────────────────────────────────────────────────────────

interface AuthState {
  user: User | null;
  token: string | null;
  setAuth: (token: string, user: User) => void;
  logout: () => void;
  hydrate: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  token: null,

  setAuth: (token, user) => {
    localStorage.setItem("token", token);
    localStorage.setItem("user", JSON.stringify(user));
    set({ token, user });
  },

  logout: () => {
    localStorage.removeItem("token");
    localStorage.removeItem("user");
    set({ token: null, user: null });
  },

  hydrate: () => {
    const token = localStorage.getItem("token");
    const raw = localStorage.getItem("user");
    if (token && raw) {
      try {
        set({ token, user: JSON.parse(raw) });
      } catch {}
    }
  },
}));

// ── Review Store ──────────────────────────────────────────────────────────────

interface ReviewState {
  reviews: Review[];
  activeReview: Review | null;
  issues: Issue[];
  comments: Comment[];
  activeUsers: string[];
  isLoading: boolean;

  // Actions
  fetchReviews: () => Promise<void>;
  fetchReview: (id: string) => Promise<void>;
  createReview: (data: { title: string; code: string; language: string }) => Promise<Review>;
  fetchComments: (reviewId: string) => Promise<void>;
  addComment: (reviewId: string, data: { content: string; issue_id?: string; line_number?: string }) => Promise<void>;

  // Real-time updates
  appendIssues: (issues: Issue[]) => void;
  setActiveUsers: (users: string[]) => void;
  addCommentLocal: (comment: Comment) => void;
  setReviewStatus: (status: Review["status"]) => void;
}

export const useReviewStore = create<ReviewState>((set, get) => ({
  reviews: [],
  activeReview: null,
  issues: [],
  comments: [],
  activeUsers: [],
  isLoading: false,

  fetchReviews: async () => {
    set({ isLoading: true });
    const { data } = await api.get<Review[]>("/api/reviews");
    set({ reviews: data, isLoading: false });
  },

  fetchReview: async (id) => {
    set({ isLoading: true });
    const { data } = await api.get<Review>(`/api/reviews/${id}`);
    set({ activeReview: data, issues: data.issues, isLoading: false });
  },

  createReview: async (body) => {
    const { data } = await api.post<Review>("/api/reviews", body);
    set((s) => ({ reviews: [data, ...s.reviews] }));
    return data;
  },

  fetchComments: async (reviewId) => {
    const { data } = await api.get<Comment[]>(`/api/reviews/${reviewId}/comments`);
    set({ comments: data });
  },

  addComment: async (reviewId, body) => {
    await api.post(`/api/reviews/${reviewId}/comments`, body);
    // Comment will arrive via WebSocket for real-time; also refresh
    await get().fetchComments(reviewId);
  },

  appendIssues: (issues) => set((s) => ({ issues: [...s.issues, ...issues] })),

  setActiveUsers: (users) => set({ activeUsers: users }),

  addCommentLocal: (comment) => set((s) => ({ comments: [...s.comments, comment] })),

  setReviewStatus: (status) =>
    set((s) => ({
      activeReview: s.activeReview ? { ...s.activeReview, status } : null,
    })),
}));
