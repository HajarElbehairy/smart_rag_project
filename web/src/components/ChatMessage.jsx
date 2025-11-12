import React from 'react';

function ChatMessage({ message }) {
  const { type, content, timestamp } = message;

  const formatTime = (date) => {
    return new Date(date).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  return (
    <div className={`message message-${type}`}>
      {type !== 'system' && (
        <div className="message-header">
          <span className="message-label">
            {type === 'user' ? '👤 You' : '🤖 Assistant'}
          </span>
          <span className="message-time">{formatTime(timestamp)}</span>
        </div>
      )}
      <div className="message-content">
        {content || <span className="typing-indicator">Thinking...</span>}
      </div>
    </div>
  );
}

export default ChatMessage;