import React, { useEffect } from 'react';

function ErrorBanner({ message, onClose }) {
  useEffect(() => {
    if (message) {
      const timer = setTimeout(onClose, 7000);
      return () => clearTimeout(timer);
    }
  }, [message, onClose]);

  if (!message) return null;

  return (
    <div className="error-banner">
      <span>{message}</span>
      <button onClick={onClose} className="close-btn">✕</button>
    </div>
  );
}

export default ErrorBanner;