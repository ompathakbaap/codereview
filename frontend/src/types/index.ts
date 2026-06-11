export interface User {
  id: string;
  email: string;
  username: string;
  created_at: string;
}

export interface AuthToken {
  access_token: string;
  token_type: string;
  user: User;
}

export type Severity = "critical" | "high" | "medium" | "low" | "info";
export type Category = "bug" | "security" | "style" | "performance";
export type ReviewStatus = "pending" | "running" | "complete" | "error";

export interface Issue {
  id: string;
  category: Category;
  severity: Severity;
  line_start: string | null;
  line_end: string | null;
  title: string;
  description: string;
  suggestion: string | null;
  code_snippet: string | null;
  created_at: string;
}

export interface Review {
  id: string;
  title: string;
  code: string;
  language: string;
  status: ReviewStatus;
  owner_id: string;
  created_at: string;
  updated_at: string;
  issues: Issue[];
}

export interface Comment {
  id: string;
  review_id: string;
  user_id: string;
  issue_id: string | null;
  content: string;
  line_number: string | null;
  created_at: string;
  username: string | null;
}

// WebSocket events
export type WSEvent =
  | { type: "user_joined"; user_id: string; username: string; active_users: string[] }
  | { type: "user_left"; user_id: string; username: string; active_users: string[] }
  | { type: "review_complete"; review_id: string; summary: string; issue_count: number; issues: Issue[] }
  | { type: "review_error"; review_id: string; error: string }
  | { type: "new_comment"; comment_id: string; user_id: string; username: string; content: string; issue_id: string | null; line_number: string | null }
  | { type: "cursor_move"; user_id: string; username: string; line: number }
  | { type: "pong" };

// SSE streaming events
export type SSEEvent =
  | { type: "node_start"; node: string; label: string }
  | { type: "token"; node: string; text: string }
  | { type: "node_done"; node: string; issue_count: number; issues: Issue[]; summary?: string }
  | { type: "complete"; issue_count: number; issues: Issue[] }
  | { type: "error"; message: string };

// Stats
export interface ReviewStats {
  total_reviews: number;
  total_issues: number;
  issues_by_category: Record<string, number>;
  issues_by_severity: Record<string, number>;
  top_languages: { language: string; count: number }[];
  recent_reviews: { date: string; status: string }[];
}
