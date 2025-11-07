import React from 'react';
import ReactDOM from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from './App';
import './index.css';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 1000 * 5,
    },
  },
});

const apiBaseUrl = window.__DATASET_API_BASE_URL__ || process.env.REACT_APP_API_URL || 'http://localhost:18000';

const rootElement = document.getElementById('root');

if (!rootElement) {
  throw new Error('Root element with id "root" was not found.');
}

const root = ReactDOM.createRoot(rootElement);

root.render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App apiBaseUrl={apiBaseUrl} />
    </QueryClientProvider>
  </React.StrictMode>
);
