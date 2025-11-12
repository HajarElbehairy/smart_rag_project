import React from 'react';

function SourcesList({ sources }) {
  if (!sources || sources.length === 0) {
    return (
      <div className="empty-state">
        <p>No sources yet. Ask a question to see relevant documents.</p>
      </div>
    );
  }

  return (
    <div className="sources-list">
      {sources.map((source, index) => (
        <div key={index} className="source-item">
          <div className="source-header">
            <span className="source-number">{index + 1}</span>
            <h4 className="source-title">{source.title}</h4>
          </div>
          
          <a
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="source-link"
          >
            🔗 {source.url}
          </a>
          
          <p className="source-snippet">{source.snippet}</p>
          
          <div className="source-meta">
            <span>Distance: {source.distance.toFixed(4)}</span>
            <span>Pos: {source.position}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export default SourcesList;