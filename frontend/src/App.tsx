import React, { useState, useEffect, useRef } from 'react';
import {
  sendChatMessage,
  fetchCacheStats,
  clearCache,
  fetchDocumentPage,
  updateApiKey,
  checkHealth,
  Citation,
  CacheStats,
  DocumentPageResponse
} from './services/api';
import {
  ArrowUp,
  Settings,
  Plus,
  X,
  ExternalLink,
  Zap,
  Sparkles,
  Building,
  Trash2,
  Volume2,
  HardHat,
  FileText,
  RotateCcw,
  PanelLeftClose,
  PanelLeft,
  MessageSquare
} from 'lucide-react';

interface Message {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  citations?: Citation[];
  is_supported?: boolean;
  cache_status?: 'HIT' | 'MISS';
  latency_ms?: number;
}

interface ChatSession {
  id: string;
  title: string;
  timestamp: number;
  messages: Message[];
}

const STORAGE_KEY = 'cedarhaven_chat_sessions';

export default function App() {
  const [sessions, setSessions] = useState<ChatSession[]>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved ? JSON.parse(saved) : [];
    } catch {
      return [];
    }
  });

  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const [cacheStats, setCacheStats] = useState<CacheStats | null>(null);
  const [health, setHealth] = useState<{ status: string; gemini_configured: boolean; model: string } | null>(null);

  // Citation Inspector Drawer
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedPage, setSelectedPage] = useState<DocumentPageResponse | null>(null);
  const [loadingPage, setLoadingPage] = useState(false);

  // Settings Modal
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [settingsMsg, setSettingsMsg] = useState('');

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Persist sessions to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
    } catch (e) {
      console.warn('Failed to save sessions to localStorage:', e);
    }
  }, [sessions]);

  useEffect(() => {
    refreshMeta();
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  const refreshMeta = async () => {
    try {
      const [h, s] = await Promise.all([checkHealth(), fetchCacheStats()]);
      setHealth(h);
      setCacheStats(s);
    } catch (e) {
      console.warn('Failed to fetch status:', e);
    }
  };

  const startNewChat = () => {
    setCurrentSessionId(null);
    setMessages([]);
    setInput('');
  };

  const selectSession = (session: ChatSession) => {
    setCurrentSessionId(session.id);
    setMessages(session.messages);
  };

  const deleteSession = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    setSessions(prev => prev.filter(s => s.id !== sessionId));
    if (currentSessionId === sessionId) {
      startNewChat();
    }
  };

  const handleSend = async (queryText?: string) => {
    const textToSend = queryText || input;
    if (!textToSend.trim() || loading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      sender: 'user',
      text: textToSend.trim(),
    };

    const newMessages = [...messages, userMessage];
    setMessages(newMessages);
    if (!queryText) setInput('');
    setLoading(true);

    try {
      const res = await sendChatMessage(textToSend, true);
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        sender: 'assistant',
        text: res.answer,
        citations: res.citations,
        is_supported: res.is_supported ?? true,
        cache_status: res.cache_status,
        latency_ms: res.latency_ms,
      };

      const finalMessages = [...newMessages, assistantMessage];
      setMessages(finalMessages);

      // Save or update session in Recent Chats
      setSessions(prev => {
        if (currentSessionId) {
          return prev.map(s => s.id === currentSessionId ? { ...s, messages: finalMessages } : s);
        } else {
          const newId = Date.now().toString();
          setCurrentSessionId(newId);
          const newSession: ChatSession = {
            id: newId,
            title: textToSend.trim().length > 38 ? textToSend.trim().substring(0, 36) + '...' : textToSend.trim(),
            timestamp: Date.now(),
            messages: finalMessages,
          };
          return [newSession, ...prev];
        }
      });

      refreshMeta();
    } catch (err: any) {
      setMessages(prev => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          sender: 'assistant',
          text: `⚠️ **Service Notice:** ${err.message || 'Unable to retrieve answer. Please try again.'}`,
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenCitation = async (citation: Citation) => {
    setLoadingPage(true);
    setDrawerOpen(true);
    try {
      const data = await fetchDocumentPage(citation.doc_id, citation.page_number);
      setSelectedPage(data);
    } catch (e) {
      console.error('Failed to load page text', e);
    } finally {
      setLoadingPage(false);
    }
  };

  const handlePurgeCache = async () => {
    try {
      await clearCache();
      await refreshMeta();
      setSettingsMsg('Cache cleared successfully.');
      setTimeout(() => setSettingsMsg(''), 2500);
    } catch (e) {
      setSettingsMsg('Error clearing cache.');
    }
  };

  const handleSaveApiKey = async () => {
    if (!apiKeyInput.trim()) return;
    try {
      await updateApiKey(apiKeyInput);
      setSettingsMsg('API Key updated successfully.');
      setApiKeyInput('');
      refreshMeta();
      setTimeout(() => setSettingsMsg(''), 2500);
    } catch (e: any) {
      setSettingsMsg(`Error: ${e.message}`);
    }
  };

  const suggestions = [
    {
      icon: <Trash2 size={15} color="#09090b" />,
      title: 'Waste Collection Rules',
      query: 'What time must curbside waste bins be placed out on collection day?'
    },
    {
      icon: <Volume2 size={15} color="#09090b" />,
      title: 'Weekend Construction Noise',
      query: 'Can a contractor use a power saw at 8 a.m. on Saturday?'
    },
    {
      icon: <HardHat size={15} color="#09090b" />,
      title: 'Sidewalk Obstruction',
      query: 'A contractor is blocking my sidewalk with renovation materials. Who handles this and how fast?'
    },
    {
      icon: <FileText size={15} color="#09090b" />,
      title: 'Shed & Deck Permits',
      query: 'What is the maximum size for a storage shed that is exempt from a building permit?'
    }
  ];

  return (
    <div className="app-layout">
      {/* Top Navbar */}
      <header className="top-nav">
        <div className="brand-group">
          <button
            className="btn-icon-label"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            title={sidebarOpen ? "Hide Recent Chats" : "Show Recent Chats"}
            style={{ padding: '6px' }}
          >
            {sidebarOpen ? <PanelLeftClose size={15} /> : <PanelLeft size={15} />}
          </button>

          <div className="brand-icon">
            <Building size={15} />
          </div>
          <div className="brand-title">
            <span className="brand-name">Cedarhaven AI</span>
            <span className="status-badge">
              <span className="status-dot"></span>
              Policy Grounded
            </span>
          </div>
        </div>

        <div className="nav-actions">
          <button
            className="btn-icon-label"
            onClick={startNewChat}
            title="Start a new query"
          >
            <Plus size={13} />
            <span>New Query</span>
          </button>

          <button
            className="btn-icon-label"
            onClick={() => setSettingsOpen(true)}
            title="Settings & Cache Stats"
          >
            <Settings size={13} />
            <span>Settings</span>
          </button>
        </div>
      </header>

      {/* Main Body: Recent Chats Sidebar + Chat Canvas */}
      <div className="app-body">
        {/* Recent Chats Sidebar */}
        <aside className={`recent-sidebar ${sidebarOpen ? '' : 'closed'}`}>
          <div className="sidebar-top">
            <button className="btn-new-chat" onClick={startNewChat}>
              <Plus size={14} />
              <span>New Conversation</span>
            </button>
          </div>

          <div className="sidebar-section-title">Recent Chats</div>

          <div className="recent-chats-scroll">
            {sessions.length === 0 ? (
              <div className="empty-recent-notice">
                No previous conversations yet. Ask a question to start.
              </div>
            ) : (
              sessions.map(s => (
                <div
                  key={s.id}
                  className={`recent-chat-item ${currentSessionId === s.id ? 'active' : ''}`}
                  onClick={() => selectSession(s)}
                >
                  <MessageSquare size={13} style={{ flexShrink: 0, marginRight: '6px', opacity: 0.6 }} />
                  <span className="recent-chat-title">{s.title}</span>
                  <button
                    className="btn-delete-session"
                    onClick={(e) => deleteSession(e, s.id)}
                    title="Delete chat"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              ))
            )}
          </div>
        </aside>

        {/* Chat Canvas */}
        <main className="chat-container">
          <div className="chat-inner">
            {messages.length === 0 ? (
              <div className="welcome-hero">
                <div className="hero-pill-badge">
                  <Sparkles size={11} />
                  <span>Municipal Policy Engine · Powered by Gemini</span>
                </div>
                <h1 className="hero-title">What would you like to know?</h1>
                <p className="hero-subtitle">
                  Search across Town of Cedarhaven 311 services, municipal bylaws, and building permits.
                  All responses are strictly grounded in official policy.
                </p>

                <div className="suggestion-grid">
                  {suggestions.map((s, idx) => (
                    <button
                      key={idx}
                      className="suggestion-card"
                      onClick={() => handleSend(s.query)}
                    >
                      <div className="card-label">
                        {s.icon}
                        <span>{s.title}</span>
                      </div>
                      <div className="card-desc">{s.query}</div>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m) => {
                // Ensure distinct, non-duplicate citations per message
                const uniqueCitations = (m.citations || []).filter((c, idx, arr) =>
                  arr.findIndex(item => item.doc_id === c.doc_id && item.page_number === c.page_number) === idx
                );

                return (
                  <div key={m.id} className={`message-row ${m.sender}`}>
                    {m.sender === 'assistant' && (
                      <div className={`message-avatar assistant ${m.is_supported === false ? 'avatar-subtle' : ''}`}>
                        CH
                      </div>
                    )}
                    <div className={`message-content ${m.is_supported === false ? 'unsupported-notice' : ''}`}>
                      <div className={`message-body-text ${m.is_supported === false ? 'text-subtle' : ''}`}>
                        {m.text}
                      </div>

                      {/* Grounded Evidence Citations (Deduplicated) */}
                      {m.is_supported !== false && uniqueCitations.length > 0 && (
                        <div className="citations-container">
                          <div className="citations-header">Sources</div>
                          <div className="citations-chips">
                            {uniqueCitations.map((c, i) => (
                              <button
                                key={i}
                                className="citation-chip"
                                onClick={() => handleOpenCitation(c)}
                                title={`Inspect ${c.doc_title} page ${c.page_number}`}
                              >
                                <span className="citation-chip-badge">{i + 1}</span>
                                <span>{c.doc_id} · p. {c.page_number} ({c.section})</span>
                                <ExternalLink size={10} color="#a1a1aa" />
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Discreet Performance Info */}
                      {m.sender === 'assistant' && m.cache_status && (
                        <div className="message-footer">
                          <span className={`cache-indicator ${m.cache_status === 'HIT' ? 'hit' : 'miss'}`}>
                            {m.cache_status === 'HIT' ? (
                              <>
                                <Zap size={10} /> {m.latency_ms}ms · Cached
                              </>
                            ) : (
                              <>
                                {(m.latency_ms! / 1000).toFixed(1)}s · Gemini
                              </>
                            )}
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                );
              })
            )}

            {loading && (
              <div className="message-row assistant">
                <div className="message-avatar assistant">CH</div>
                <div className="message-content" style={{ color: '#71717a', fontSize: '0.88rem' }}>
                  Searching Cedarhaven policies and formulating response...
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </main>

        {/* Floating Bottom Input Dock */}
        <div className="bottom-dock">
          <form
            className="input-box"
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
          >
            <input
              type="text"
              className="text-field"
              placeholder="Ask about bylaws, permits, waste, road repairs, noise..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={loading}
            />
            <button
              type="submit"
              className="btn-send"
              disabled={loading || !input.trim()}
              title="Submit question"
            >
              <ArrowUp size={15} />
            </button>
          </form>
          <div className="dock-disclaimer">
            Town of Cedarhaven · Grounded in official municipal policy documents
          </div>
        </div>

        {/* Citation Inspector Side Drawer */}
        <aside className={`inspector-drawer ${drawerOpen ? 'open' : ''}`}>
          <div className="drawer-top">
            <div className="drawer-title-group">
              <h3>Citation Source Inspector</h3>
              {selectedPage && (
                <div className="drawer-subtitle">
                  {selectedPage.doc_title} · Page {selectedPage.page_number}
                </div>
              )}
            </div>
            <button className="drawer-close" onClick={() => setDrawerOpen(false)}>
              <X size={16} />
            </button>
          </div>

          <div className="drawer-content">
            {loadingPage ? (
              <div>Loading verified page from source PDF...</div>
            ) : selectedPage ? (
              <div>{selectedPage.content}</div>
            ) : (
              <div>Click any citation pill to view the source page.</div>
            )}
          </div>
        </aside>
      </div>

      {/* Minimal Settings Modal */}
      {settingsOpen && (
        <div className="simple-modal-backdrop" onClick={() => setSettingsOpen(false)}>
          <div className="simple-modal" onClick={(e) => e.stopPropagation()}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h3 style={{ fontSize: '0.95rem', fontWeight: 600 }}>System Settings</h3>
              <button className="drawer-close" onClick={() => setSettingsOpen(false)}>
                <X size={15} />
              </button>
            </div>

            {/* Cache Overview */}
            <div style={{ background: '#fbfbfb', border: '1px solid #eaeaea', borderRadius: '10px', padding: '14px', marginBottom: '16px', fontSize: '0.82rem' }}>
              <div style={{ fontWeight: 600, color: '#09090b', marginBottom: '8px' }}>Cache Telemetry</div>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: '#71717a', marginBottom: '4px' }}>
                <span>Hits:</span>
                <strong style={{ color: '#09090b' }}>{cacheStats?.cache_hits ?? 0} / {cacheStats?.total_queries ?? 0} ({cacheStats?.hit_ratio_percent ?? 0}%)</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', color: '#71717a', marginBottom: '10px' }}>
                <span>Saved Latency:</span>
                <strong style={{ color: '#09090b' }}>{cacheStats?.total_latency_saved_ms ? (cacheStats.total_latency_saved_ms / 1000).toFixed(1) : 0}s</strong>
              </div>
              <button
                className="btn-icon-label"
                onClick={handlePurgeCache}
                style={{ width: '100%', justifyContent: 'center' }}
              >
                <RotateCcw size={12} />
                <span>Purge Cache</span>
              </button>
            </div>

            {/* API Key Form */}
            <div style={{ fontSize: '0.82rem', marginBottom: '16px' }}>
              <label style={{ display: 'block', fontWeight: 600, color: '#09090b', marginBottom: '6px' }}>
                Gemini API Key
              </label>
              <input
                type="password"
                className="text-field"
                style={{ border: '1px solid #e4e4e7', borderRadius: '8px', padding: '8px 12px', width: '100%', marginBottom: '8px', fontSize: '0.82rem' }}
                placeholder="Update API key"
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
              />
              <button
                className="btn-icon-label"
                onClick={handleSaveApiKey}
                style={{ width: '100%', justifyContent: 'center', background: '#09090b', color: '#ffffff', border: 'none' }}
              >
                Update Key
              </button>
            </div>

            {settingsMsg && (
              <div style={{ fontSize: '0.78rem', textAlign: 'center', color: settingsMsg.includes('Error') ? '#dc2626' : '#16a34a' }}>
                {settingsMsg}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
