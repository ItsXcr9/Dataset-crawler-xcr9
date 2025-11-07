import React, { useState, useEffect } from 'react';
import './App.css';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:18000';

function App() {
  const [jobs, setJobs] = useState([]);
  const [summary, setSummary] = useState(null);
  const [startUrl, setStartUrl] = useState('');
  const [maxDepth, setMaxDepth] = useState(3);

  useEffect(() => {
    fetchJobs();
    fetchSummary();
    const interval = setInterval(() => {
      fetchJobs();
      fetchSummary();
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchJobs = async () => {
    try {
      const response = await fetch(`${API_URL}/jobs`);
      const data = await response.json();
      setJobs(data);
    } catch (error) {
      console.error('Error fetching jobs:', error);
    }
  };

  const fetchSummary = async () => {
    try {
      const response = await fetch(`${API_URL}/dataset/summary`);
      const data = await response.json();
      setSummary(data);
    } catch (error) {
      console.error('Error fetching summary:', error);
    }
  };

  const startCrawl = async (e) => {
    e.preventDefault();
    try {
      const response = await fetch(`${API_URL}/crawl`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ start_url: startUrl, max_depth: maxDepth })
      });
      const data = await response.json();
      alert(`Crawl started: ${data.job_id}`);
      setStartUrl('');
      fetchJobs();
    } catch (error) {
      alert('Error starting crawl: ' + error.message);
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Dataset Crawler</h1>
        <p>Professional Web Crawler for LLM Training Datasets</p>
      </header>

      <main className="App-main">
        <section className="card">
          <h2>Start New Crawl</h2>
          <form onSubmit={startCrawl}>
            <div className="form-group">
              <label>Start URL:</label>
              <input
                type="url"
                value={startUrl}
                onChange={(e) => setStartUrl(e.target.value)}
                placeholder="https://example.com"
                required
              />
            </div>
            <div className="form-group">
              <label>Max Depth:</label>
              <input
                type="number"
                value={maxDepth}
                onChange={(e) => setMaxDepth(parseInt(e.target.value))}
                min="1"
                max="10"
              />
            </div>
            <button type="submit" className="btn-primary">Start Crawl</button>
          </form>
        </section>

        {summary && (
          <section className="card">
            <h2>Dataset Summary</h2>
            <div className="stats-grid">
              <div className="stat">
                <div className="stat-label">Current Version</div>
                <div className="stat-value">{summary.current_version || 'N/A'}</div>
              </div>
              <div className="stat">
                <div className="stat-label">Total Versions</div>
                <div className="stat-value">{summary.total_versions || 0}</div>
              </div>
              <div className="stat">
                <div className="stat-label">Documents</div>
                <div className="stat-value">
                  {summary.current_statistics?.total_documents || 0}
                </div>
              </div>
              <div className="stat">
                <div className="stat-label">Total Tokens</div>
                <div className="stat-value">
                  {(summary.current_statistics?.total_tokens || 0).toLocaleString()}
                </div>
              </div>
            </div>
          </section>
        )}

        <section className="card">
          <h2>Recent Jobs</h2>
          <div className="jobs-list">
            {jobs.length === 0 ? (
              <p className="empty-state">No jobs yet. Start a crawl to begin!</p>
            ) : (
              jobs.slice(0, 10).map((job) => (
                <div key={job.job_id} className={`job-item status-${job.status}`}>
                  <div className="job-header">
                    <span className="job-id">{job.job_id}</span>
                    <span className={`job-status ${job.status}`}>{job.status}</span>
                  </div>
                  <div className="job-message">{job.message}</div>
                  <div className="job-progress">
                    <div
                      className="progress-bar"
                      style={{ width: `${job.progress * 100}%` }}
                    ></div>
                  </div>
                </div>
              ))
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;

