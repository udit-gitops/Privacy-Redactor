'use client';

import React, { useState, useRef } from 'react';

interface Entity {
  text: string;
  type: string;
  score: number;
  start: number;
  end: number;
}

const API_BASE_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000').replace(/\/$/, '');

export default function PrivacyDashboard() {
  const [inputText, setInputText]       = useState('');
  const [securedText, setSecuredText]   = useState('');
  const [isLoading, setIsLoading]       = useState(false);
  const [latency, setLatency]           = useState<number | null>(null);
  const [systemStatus, setSystemStatus] = useState<'connected' | 'error' | 'idle'>('idle');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [redactStyle, setRedactStyle]   = useState('PLACEHOLDER');
  const [downloadRedactedDoc, setDownloadRedactedDoc] = useState(false);
  const [detectedEntities, setDetectedEntities]       = useState<Entity[]>([]);
  const [copyState, setCopyState]       = useState<'idle' | 'copied'>('idle');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [metrics, setMetrics] = useState({
    charactersProcessed: 0,
    identitiesMasked: 0,
    complianceRating: 'COMPLIANT',
  });

  const handleRedaction = async (fileToProcess?: File, currentStyle?: string, forceDownload?: boolean) => {
    setIsLoading(true);
    setSystemStatus('idle');
    const startTime      = performance.now();
    const styleParam     = currentStyle || redactStyle;
    const shouldDownload = forceDownload !== undefined ? forceDownload : downloadRedactedDoc;

    try {
      let response: Response;
      const file = fileToProcess || selectedFile;

      if (file) {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('redact_style', styleParam);
        formData.append('return_redacted_document', shouldDownload ? 'true' : 'false');
        response = await fetch(`${API_BASE_URL}/api/v1/redact-file`, { method: 'POST', body: formData });
      } else {
        if (!inputText.trim()) { setIsLoading(false); return; }
        response = await fetch(`${API_BASE_URL}/api/v1/redact?redact_style=${styleParam}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: inputText }),
        });
      }

      if (!response.ok) {
        const err = await response.json();
        throw new Error(err.detail || 'Backend engine unreachable');
      }

      const contentType = response.headers.get('content-type') || '';

      // Binary file download
      if (contentType.includes('application/pdf') || contentType.includes('image/') || contentType.includes('text/plain')) {
        const blob = await response.blob();
        const url  = window.URL.createObjectURL(blob);
        const a    = document.createElement('a');
        a.href     = url;
        const disposition = response.headers.get('content-disposition') || '';
        const match = /filename[^;=\n]*=((['\"]).*?\2|[^;\n]*)/.exec(disposition);
        a.download  = match ? match[1].replace(/['\"]/g, '') : `redacted_${file?.name ?? 'file'}`;
        document.body.appendChild(a); a.click(); a.remove();
        window.URL.revokeObjectURL(url);
        setSecuredText(`[Success] Redacted file downloaded: ${a.download}`);
        setLatency(Math.round(performance.now() - startTime));
        setSystemStatus('connected');
        setMetrics({ charactersProcessed: file?.size ?? inputText.length, identitiesMasked: detectedEntities.length || 1, complianceRating: 'CLEANSED (FILE DOWNLOADED)' });
        setIsLoading(false);
        return;
      }

      // JSON result
      const data = await response.json();
      // Spacing fix: ensure space before every redacted tag like <PERSON>
      const spacedText = (data.secured_text as string).replace(/([^\s])(<)/g, '$1 $2');
      setSecuredText(spacedText);
      setDetectedEntities(data.entities || []);
      setLatency(Math.round(performance.now() - startTime));
      setSystemStatus('connected');
      setMetrics({
        charactersProcessed: data.metrics?.characters_processed ?? 0,
        identitiesMasked:    data.metrics?.identities_masked    ?? 0,
        complianceRating:    (data.metrics?.identities_masked ?? 0) > 3 ? 'CLEANSED (HIGH DENSITY)' : 'COMPLIANT',
      });
    } catch (error: any) {
      console.error(error);
      setSystemStatus('error');
      setSecuredText(`Error: ${error.message || 'Failed to reach the redaction engine.'}`);\n    } finally {
      setIsLoading(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setSelectedFile(file);
    setInputText(`File selected: ${file.name} (${Math.round(file.size / 1024)} KB)`);
    handleRedaction(file, redactStyle, downloadRedactedDoc);
  };

  const clearFile = () => {
    setSelectedFile(null); setInputText(''); setSecuredText('');
    setDetectedEntities([]); setLatency(null);
    setMetrics({ charactersProcessed: 0, identitiesMasked: 0, complianceRating: 'COMPLIANT' });
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const copyToClipboard = () => {
    if (!securedText) return;
    navigator.clipboard.writeText(securedText).then(() => {
      setCopyState('copied');
      setTimeout(() => setCopyState('idle'), 2000);
    });
  };

  return (
    <div className="min-h-screen bg-slate-100 text-slate-800 font-sans flex flex-col antialiased">

      {/* ── Header ── */}
      <header className="border-b border-slate-200 bg-white px-8 py-5 flex items-center justify-between shadow-sm">
        <div className="flex items-center space-x-3">
          <svg className="h-7 w-7 text-indigo-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-slate-900">Privacy Redaction Engine</h1>
            <p className="text-xs text-slate-500">Enterprise PII & Compliance Sanitizer</p>
          </div>
        </div>
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <span className={`h-2.5 w-2.5 rounded-full animate-pulse ${
              systemStatus === 'error' ? 'bg-red-500' : systemStatus === 'connected' ? 'bg-emerald-500' : 'bg-amber-400'
            }`} />
            <span className="text-xs font-medium text-slate-600">
              {systemStatus === 'error' ? 'Offline' : systemStatus === 'connected' ? 'Active' : 'Ready'}
            </span>
          </div>
          {latency !== null && (
            <span className="text-xs font-mono bg-slate-100 text-slate-600 px-2.5 py-1 rounded-md border border-slate-200">
              {latency}ms
            </span>
          )}
        </div>
      </header>

      {/* ── Main Workspace ── */}
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-8 p-8 max-w-7xl w-full mx-auto">

        {/* Input Panel */}
        <div className="bg-white border border-slate-200 rounded-xl p-6 flex flex-col gap-4 shadow-sm">
          <div className="flex items-center justify-between">
            <label className="text-xs font-bold uppercase tracking-wider text-slate-500">Input</label>
            {selectedFile && (
              <button onClick={clearFile} className="text-xs text-red-500 hover:text-red-700 font-medium transition-colors">
                Clear File
              </button>
            )}
          </div>

          <textarea
            className="w-full min-h-[220px] bg-white border border-slate-300 rounded-lg p-4 text-sm text-slate-800 placeholder-slate-400 focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500 focus:outline-none transition-all resize-none"
            placeholder="Paste raw email, corporate communication, or database logs here..."
            value={inputText}
            onChange={(e) => { if (selectedFile) setSelectedFile(null); setInputText(e.target.value); }}
          />

          {/* Upload zone */}
          <div
            onClick={() => fileInputRef.current?.click()}
            className={`border-2 border-dashed rounded-lg p-4 flex flex-col items-center justify-center cursor-pointer transition-all ${
              selectedFile ? 'border-indigo-500 bg-indigo-50' : 'border-slate-300 hover:border-slate-400 hover:bg-slate-50'
            }`}
          >
            <input type="file" ref={fileInputRef} onChange={handleFileChange} className="hidden" accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.tiff" />
            <svg className="h-6 w-6 text-slate-400 mb-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
            </svg>
            <p className="text-xs font-semibold text-slate-700">
              {selectedFile ? `Attached: ${selectedFile.name}` : 'Drop a file or click to upload'}
            </p>
            <p className="text-[10px] text-slate-400 mt-0.5">PDF · DOCX · TXT · PNG · JPG · TIFF</p>
          </div>

          {/* Controls */}
          <div className="grid grid-cols-2 gap-4 bg-slate-50 border border-slate-200 rounded-lg p-3">
            <div>
              <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1">Redaction Style</label>
              <select
                value={redactStyle}
                onChange={(e) => { setRedactStyle(e.target.value); if (selectedFile || inputText.trim()) handleRedaction(selectedFile || undefined, e.target.value); }}
                className="w-full text-xs bg-white border border-slate-300 rounded-md p-2 text-slate-700 focus:ring-1 focus:ring-indigo-500 focus:border-indigo-500 focus:outline-none"
              >
                <option value="PLACEHOLDER">Placeholder (&lt;PERSON&gt;)</option>
                <option value="REDACTED">Tag Replacement ([REDACTED])</option>
                <option value="MASK">Solid Box Mask (████████)</option>
                <option value="HIDDEN">Hidden tag (&lt;Name Hidden&gt;)</option>
              </select>
            </div>
            <div className="flex flex-col justify-center">
              <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1.5">Output Action</label>
              <div className="flex items-center space-x-2">
                <input type="checkbox" id="downloadDoc" checked={downloadRedactedDoc}
                  onChange={(e) => { setDownloadRedactedDoc(e.target.checked); if (selectedFile) handleRedaction(selectedFile, redactStyle, e.target.checked); }}
                  className="h-4 w-4 text-indigo-600 focus:ring-indigo-500 border-slate-300 rounded"
                />
                <label htmlFor="downloadDoc" className="text-xs text-slate-600 font-medium cursor-pointer select-none">
                  Download Redacted File
                </label>
              </div>
            </div>
          </div>

          <button
            onClick={() => handleRedaction()}
            disabled={isLoading || (!inputText.trim() && !selectedFile)}
            className="w-full bg-indigo-600 hover:bg-indigo-700 disabled:opacity-40 text-white text-sm font-semibold py-3.5 rounded-lg shadow-sm transition-all active:scale-[0.99] flex items-center justify-center gap-2"
          >
            {isLoading ? (
              <>
                <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <span>Analyzing & Anonymizing...</span>
              </>
            ) : <span>Redact & Secure Payload</span>}
          </button>
        </div>

        {/* Output Panel */}
        <div className="bg-white border border-slate-200 rounded-xl p-6 flex flex-col gap-4 shadow-sm">
          <div className="flex items-center justify-between">
            <label className="text-xs font-bold uppercase tracking-wider text-slate-500">Secured Output</label>
            {securedText && !securedText.startsWith('Error:') && (
              <button
                onClick={copyToClipboard}
                className={`text-xs font-semibold transition-all px-2.5 py-1 rounded-md ${
                  copyState === 'copied'
                    ? 'bg-emerald-100 text-emerald-700 border border-emerald-200'
                    : 'text-indigo-600 hover:text-indigo-800 hover:bg-indigo-50'
                }`}
              >
                {copyState === 'copied' ? '✓ Copied!' : 'Copy Output'}
              </button>
            )}
          </div>

          <div className="w-full min-h-[220px] flex-1 bg-white border border-slate-300 rounded-lg p-5 text-sm font-mono whitespace-pre-wrap overflow-y-auto text-slate-800 leading-relaxed">
            {securedText ? (
              <span className={securedText.startsWith('Error:') ? 'text-red-600 font-sans' : ''}>
                {securedText}
              </span>
            ) : (
              <span className="text-slate-400 font-sans italic">Awaiting input...</span>
            )}
          </div>

          {detectedEntities.length > 0 && (
            <div className="border border-slate-200 bg-slate-50 rounded-lg p-3 max-h-[140px] overflow-y-auto">
              <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-2">Detected Entities</label>
              <div className="flex flex-wrap gap-1.5">
                {detectedEntities.map((ent, idx) => (
                  <span key={idx} className="text-[10px] font-medium bg-indigo-50 text-indigo-800 border border-indigo-200 px-2 py-0.5 rounded-full flex items-center gap-1">
                    <span className="font-semibold">{ent.text}</span>
                    <span className="opacity-40">•</span>
                    <span className="font-mono text-[9px] bg-indigo-100 text-indigo-900 px-1 rounded">{ent.type}</span>
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </main>

      {/* ── Metrics ── */}
      <section className="bg-white border-t border-slate-200">
        <div className="max-w-7xl mx-auto px-8 py-6 grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-slate-50 border border-slate-200 p-5 rounded-xl">
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">Bytes Processed</p>
            <p className="text-3xl font-bold font-mono mt-1.5 text-slate-900">{metrics.charactersProcessed}</p>
          </div>
          <div className="bg-slate-50 border border-slate-200 p-5 rounded-xl">
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">Entities Scrubbed</p>
            <p className="text-3xl font-bold font-mono mt-1.5 text-slate-900">{metrics.identitiesMasked}</p>
          </div>
          <div className="bg-slate-50 border border-slate-200 p-5 rounded-xl flex flex-col justify-between">
            <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">Risk Evaluation</p>
            <span className={`self-start text-xs font-bold mt-2 px-3 py-1.5 rounded-lg border ${
              metrics.complianceRating.includes('COMPLIANT')
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                : 'bg-amber-50 text-amber-700 border-amber-200'
            }`}>
              {metrics.complianceRating}
            </span>
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="bg-white border-t border-slate-200">
        <div className="max-w-7xl mx-auto px-8 py-8 flex flex-col md:flex-row items-start md:items-center justify-between gap-8">

          {/* Left: Built with */}
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-3">Built with</p>
            <div className="flex flex-wrap gap-2">
              {['Next.js 15', 'FastAPI', 'Presidio', 'LLaMA 3.1'].map((tech) => (
                <span key={tech} className="text-xs bg-slate-100 border border-slate-200 text-slate-600 font-medium px-3 py-1 rounded-full">
                  {tech}
                </span>
              ))}
            </div>
          </div>

          {/* Divider on desktop */}
          <div className="hidden md:block w-px h-12 bg-slate-200" />

          {/* Right: Contact */}
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-3">Contact</p>
            <div className="flex flex-col gap-2.5">
              {/* Name */}
              <p className="text-sm font-semibold text-slate-800">Udit Navariya</p>

              <div className="flex items-center gap-4">
                {/* GitHub */}
                <a href="https://github.com/udit-gitops" target="_blank" rel="noreferrer"
                  title="GitHub"
                  className="flex items-center gap-1.5 text-slate-500 hover:text-slate-900 transition-colors">
                  <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
                    <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482C19.138 20.193 22 16.44 22 12.017 22 6.484 17.522 2 12 2z" />
                  </svg>
                  <span className="text-xs">GitHub</span>
                </a>

                {/* LinkedIn */}
                <a href="https://www.linkedin.com/in/udit-navariya/" target="_blank" rel="noreferrer"
                  title="LinkedIn"
                  className="flex items-center gap-1.5 text-slate-500 hover:text-slate-900 transition-colors">
                  <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z" />
                  </svg>
                  <span className="text-xs">LinkedIn</span>
                </a>

                {/* Email — icon + "Email" text, not full address */}
                <a href="mailto:uditnavariya2005@gmail.com"
                  title="uditnavariya2005@gmail.com"
                  className="flex items-center gap-1.5 text-slate-500 hover:text-slate-900 transition-colors">
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" />
                  </svg>
                  <span className="text-xs">Email</span>
                </a>
              </div>
            </div>
          </div>

        </div>
      </footer>
    </div>
  );
}
