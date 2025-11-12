import React, { useState, useRef, useEffect } from 'react';
import './App.css';
import ChatMessage from './components/ChatMessage';
import SourcesList from './components/SourcesList';
import ErrorBanner from './components/ErrorBanner';

const API_URL = 'http://localhost:8000';

function App() {
  const [messages, setMessages] = useState([
    {
      id: 1,
      type: 'system',
      content: '👋 Hi! Ask me anything about the documentation.',
      timestamp: new Date()
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [sources, setSources] = useState([]);
  const [error, setError] = useState('');
  const [health, setHealth] = useState(null);
  
  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    checkHealth();
  }, []);

  const checkHealth = async () => {
    try {
      const res = await fetch(`${API_URL}/health`);
      const data = await res.json();
      setHealth(data);
      if (!data.faiss_index_exists || !data.metadata_exists) {
        setError('⚠️ Index files not found. Run indexing first.');
      }
    } catch (err) {
      setError('❌ Backend not connected. Start: python backend/app.py');
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const query = input.trim();
    if (!query || isLoading) return;

    const userMsg = {
      id: Date.now(),
      type: 'user',
      content: query,
      timestamp: new Date()
    };
    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setIsLoading(true);
    setError('');

    const assistantId = Date.now() + 1;
    setMessages(prev => [...prev, {
      id: assistantId,
      type: 'assistant',
      content: '',
      timestamp: new Date()
    }]);

    try {
      const response = await fetch(`${API_URL}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, top_k: 5 })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.substring(6));
              
              if (data.type === 'sources') {
                setSources(data.sources);
              } else if (data.type === 'token') {
                setMessages(prev => prev.map(msg =>
                  msg.id === assistantId
                    ? { ...msg, content: msg.content + data.content }
                    : msg
                ));
              } else if (data.type === 'error') {
                setError(data.message);
                setMessages(prev => prev.filter(m => m.id !== assistantId));
              }
            } catch (e) {
              console.error('Parse error:', e);
            }
          }
        }
      }
    } catch (err) {
      setError(`Error: ${err.message}`);
      setMessages(prev => prev.filter(m => m.id !== assistantId));
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <div className="header-content">
          <div>
            <h1>🤖 RAG Assistant</h1>
            <p>Ask questions about indexed documentation</p>
          </div>
          {health && (
            <span className={health.status === 'ok' ? 'status-ok' : 'status-error'}>
              ● {health.status.toUpperCase()}
            </span>
          )}
        </div>
        <ErrorBanner message={error} onClose={() => setError('')} />
      </header>

      <div className="main-content">
        <div className="chat-container">
          <div className="chat-messages">
            {messages.map(msg => (
              <ChatMessage key={msg.id} message={msg} />
            ))}
            {isLoading && (
              <div className="loading-indicator">
                <span className="loading-dots">●●●</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <form onSubmit={handleSubmit} className="input-form">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Type your question... (Enter to send, Shift+Enter for new line)"
              rows="2"
              disabled={isLoading}
              className="input-textarea"
            />
            <button type="submit" disabled={isLoading || !input.trim()} className="send-button">
              {isLoading ? '⏳' : '📤'} Send
            </button>
          </form>
        </div>

        <aside className="sources-sidebar">
          <h3>📚 Sources</h3>
          <SourcesList sources={sources} />
        </aside>
      </div>
    </div>
  );
}

export default App;