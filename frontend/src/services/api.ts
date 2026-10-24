export interface Citation {
  doc_id: string;
  doc_title: string;
  doc_label?: string;
  page_number: number;
  section: string;
  quote?: string;
}

export interface RetrievedChunk {
  chunk_id: string;
  doc_id: string;
  doc_title: string;
  page_number: number;
  section: string;
  text: string;
  score: number;
}

export interface ActionCard {
  is_actionable: boolean;
  case_type?: string;
  priority_level?: string;
  target_sla?: string;
  required_evidence?: string[];
  draft_ticket?: string;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  retrieved_chunks: RetrievedChunk[];
  is_supported?: boolean;
  action_card?: ActionCard | null;
  cache_status: 'HIT' | 'MISS';
  cached_at?: number;
  hit_count?: number;
  latency_ms: number;
  saved_latency_ms: number;
}

export interface CacheStats {
  total_queries: number;
  cache_hits: number;
  cache_misses: number;
  hit_ratio_percent: number;
  cached_entries_count: number;
  total_latency_saved_ms: number;
  estimated_tokens_saved: number;
}

export interface DocumentPageResponse {
  doc_id: string;
  doc_title: string;
  doc_label: string;
  page_number: number;
  content: string;
}

const API_BASE = '/api';

export async function sendChatMessage(message: string, useCache: boolean = true): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, use_cache: useCache }),
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to send message.');
  }
  return res.json();
}

export async function fetchCacheStats(): Promise<CacheStats> {
  const res = await fetch(`${API_BASE}/cache/stats`);
  if (!res.ok) throw new Error('Failed to fetch cache stats');
  return res.json();
}

export async function clearCache(): Promise<void> {
  const res = await fetch(`${API_BASE}/cache/clear`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to clear cache');
}

export async function fetchDocumentPage(docId: string, pageNum: number): Promise<DocumentPageResponse> {
  const res = await fetch(`${API_BASE}/documents/${docId}/page/${pageNum}`);
  if (!res.ok) throw new Error('Failed to fetch document page');
  return res.json();
}

export async function updateApiKey(apiKey: string): Promise<void> {
  const res = await fetch(`${API_BASE}/config/key`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey }),
  });
  if (!res.ok) throw new Error('Failed to update API key');
}

export async function checkHealth(): Promise<{ status: string; gemini_configured: boolean; model: string }> {
  const res = await fetch(`${API_BASE}/health`);
  if (!res.ok) throw new Error('Failed to check health');
  return res.json();
}
