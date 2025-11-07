import React from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import './App.css';

// Use relative path to leverage nginx proxy
const DEFAULT_API_URL = process.env.REACT_APP_API_URL || '/api';

const fetchJson = async (url, options) => {
  const response = await fetch(url, options);
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body.detail || JSON.stringify(body);
    } catch (error) {
      // ignore json parse errors
    }
    throw new Error(detail || `Request failed with status ${response.status}`);
  }
  return response.json();
};

const formatNumber = (value) => {
  if (value === undefined || value === null) return '0';
  return Number(value).toLocaleString();
};

const JobStatusPill = ({ status }) => {
  const normalized = (status || '').toLowerCase();
  return <span className={`status-pill status-${normalized}`}>{status}</span>;
};

const ProgressBar = ({ progress }) => {
  const value = Math.max(0, Math.min(1, progress || 0));
  return (
    <div className="job-progress">
      <div className="progress-bar" style={{ width: `${value * 100}%` }} />
    </div>
  );
};

function App({ apiBaseUrl = DEFAULT_API_URL }) {
  const [startUrl, setStartUrl] = React.useState('');
  const [maxDepth, setMaxDepth] = React.useState(3);

  const queryClient = useQueryClient();

  const {
    data: jobs = [],
    isLoading: jobsLoading,
    error: jobsError,
  } = useQuery({
    queryKey: ['jobs'],
    queryFn: () => fetchJson(`${apiBaseUrl}/jobs`),
    refetchInterval: 5000,
  });

  const {
    data: summary,
    isLoading: summaryLoading,
    error: summaryError,
  } = useQuery({
    queryKey: ['dataset-summary'],
    queryFn: () => fetchJson(`${apiBaseUrl}/dataset/summary`),
    refetchInterval: 15000,
  });

  const startCrawlMutation = useMutation({
    mutationFn: ({ url, depth }) =>
      fetchJson(`${apiBaseUrl}/crawl`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ start_url: url, max_depth: depth }),
      }),
    onSuccess: () => {
      setStartUrl('');
      queryClient.invalidateQueries({ queryKey: ['jobs'] });
      queryClient.invalidateQueries({ queryKey: ['dataset-summary'] });
    },
  });

  const handleStartCrawl = (event) => {
    event.preventDefault();
    if (!startUrl) return;
    startCrawlMutation.mutate({ url: startUrl, depth: maxDepth });
  };

  const renderJobs = () => {
    if (jobsLoading) {
      return <p className="empty-state">Loading jobs...</p>;
    }
    if (jobsError) {
      return <p className="empty-state error">Failed to load jobs: {jobsError.message}</p>;
    }
    if (!jobs.length) {
      return <p className="empty-state">No jobs yet. Start a crawl to begin!</p>;
    }
    return jobs.slice(0, 10).map((job) => (
      <div key={job.job_id} className={`job-item status-${job.status}`}>
        <div className="job-header">
          <span className="job-id">{job.job_id}</span>
          <JobStatusPill status={job.status} />
        </div>
        <div className="job-message">{job.message}</div>
        <ProgressBar progress={job.progress} />
        <div className="job-meta">
          <span>Created: {new Date(job.created_at).toLocaleString()}</span>
          <span>Updated: {new Date(job.updated_at).toLocaleString()}</span>
        </div>
      </div>
    ));
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Dataset Crawler</h1>
        <p>Professional Web Crawler for LLM Training Datasets</p>
      </header>

      <main className="App-main">
        <section className="card">
          <div className="card-header">
            <h2>Start New Crawl</h2>
            <span className="meta">Target API: {apiBaseUrl}</span>
          </div>
          <form onSubmit={handleStartCrawl} className="form-layout">
            <div className="form-group">
              <label htmlFor="start-url">Start URL</label>
              <input
                id="start-url"
                type="url"
                value={startUrl}
                onChange={(event) => setStartUrl(event.target.value)}
                placeholder="https://example.com/docs"
                required
              />
            </div>
            <div className="form-group">
              <label htmlFor="max-depth">Max Depth</label>
              <input
                id="max-depth"
                type="number"
                value={maxDepth}
                onChange={(event) => setMaxDepth(Number(event.target.value))}
                min={1}
                max={10}
              />
            </div>
            <div className="form-actions">
              <button
                type="submit"
                className="btn-primary"
                disabled={startCrawlMutation.isPending}
              >
                {startCrawlMutation.isPending ? 'Starting…' : 'Start Crawl'}
              </button>
            </div>
          </form>
          {startCrawlMutation.isError && (
            <div className="alert alert-error">
              Failed to start crawl: {startCrawlMutation.error.message}
            </div>
          )}
          {startCrawlMutation.isSuccess && (
            <div className="alert alert-success">
              Crawl started successfully!
            </div>
          )}
        </section>

        <section className="card">
          <h2>Dataset Summary</h2>
          {summaryLoading ? (
            <p className="empty-state">Loading dataset summary…</p>
          ) : summaryError ? (
            <p className="empty-state error">Failed to fetch summary: {summaryError.message}</p>
          ) : summary ? (
            <div className="stats-grid">
              <div className="stat">
                <div className="stat-label">Current Version</div>
                <div className="stat-value">{summary.current_version || 'N/A'}</div>
              </div>
              <div className="stat">
                <div className="stat-label">Total Versions</div>
                <div className="stat-value">{formatNumber(summary.total_versions)}</div>
              </div>
              <div className="stat">
                <div className="stat-label">Documents</div>
                <div className="stat-value">
                  {formatNumber(summary.current_statistics?.total_documents)}
                </div>
              </div>
              <div className="stat">
                <div className="stat-label">Total Tokens</div>
                <div className="stat-value">
                  {formatNumber(summary.current_statistics?.total_tokens)}
                </div>
              </div>
            </div>
          ) : (
            <p className="empty-state">No summary data available yet.</p>
          )}
        </section>

        <section className="card">
          <h2>Recent Jobs</h2>
          <div className="jobs-list">{renderJobs()}</div>
        </section>
      </main>
    </div>
  );
}

export default App;
