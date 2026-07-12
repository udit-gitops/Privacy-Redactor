'use client';

import React, { useState, useRef } from 'react';

export default function PrivacyDashboard() {
  const [inputText, setInputText] = useState('');
  const [securedText, setSecuredText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [latency, setLatency] = useState<number | null>(null);
  const [systemStatus, setSystemStatus] = useState<'connected' | 'error' | 'idle'>('idle');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [metrics, setMetrics] = useState({
    charactersProcessed: 0,
    identitiesMasked: 0,
    complianceRating: 'COMPLIANT'
  });

  const handleRedaction = async (fileToProcess?: File) => {
    setIsLoading(true);
    setSystemStatus('idle');
    const startTime = performance.now();

    try {
      let response;
      if (fileToProcess || selectedFile) {
        const file = fileToProcess || selectedFile;
        const formData = new FormData();
        formData.append('file', file!);

        response = await fetch('http://127.0.0.1:8000/api/v1/redact-file', {
          method: 'POST',
          body: formData,
        });
      } else {
        if (!inputText.trim()) return;
        response = await fetch('http://127.0.0.1:8000/api/v1/redact', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: inputText }),
        });
      }

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Backend unreachable');
      }

      const data = await response.json();
      const endTime = performance.now();

      setSecuredText(data.secured_text);
      setLatency(Math.round(endTime - startTime));
      setSystemStatus('connected');
      setMetrics({
        charactersProcessed: data.metrics.characters_processed,
        identitiesMasked: data.metrics.identities_masked,
        complianceRating: data.metrics.identities_masked > 3 ? 'CLEANSED (HIGH DENSITY)' : 'COMPLIANT'
      });
    } catch (error: any) {
      console.error(error);
      setSystemStatus('error');
      setSecuredText(error.message || 'Error: Failed to communicate with the redact engine.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setSelectedFile(file);
      setInputText(`File selected: ${file.name} (${Math.round(file.size / 1024)} KB)`);
      handleRedaction(file);
    }
  };

  const triggerFileSelect = () => {
    fileInputRef.current?.click();
  };

  const clearFile = () => {
    setSelectedFile(null);
    setInputText('');
    setSecuredText('');
    setLatency(null);
    setMetrics({ charactersProcessed: 0, identitiesMasked: 0, complianceRating: 'COMPLIANT' });
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const copyToClipboard = () => {
    if (!securedText) return;
    navigator.clipboard.writeText(securedText);
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800 font-sans flex flex-col justify-between antialiased">
      {/* Header */}
      <header className="border-b border-slate-200 bg-white px-8 py-5 flex items-center justify-between shadow-xs">
        <div className="flex items-center space-x-3">
          {/* Shield Logo */}
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
            <span className={`h-2.5 w-2.5 rounded-full ${
              systemStatus === 'error' ? 'bg-red-500' : systemStatus === 'connected' ? 'bg-emerald-500' : 'bg-amber-400'
            } animate-pulse`} />
            <span className="text-xs font-medium text-slate-600">
              {systemStatus === 'error' ? 'System Offline' : systemStatus === 'connected' ? 'Active & Healthy' : 'Ready'}
            </span>
          </div>
          {latency !== null && (
            <span className="text-xs font-mono bg-slate-100 text-slate-600 px-2.5 py-1 rounded-md border border-slate-200">
              Speed: {latency}ms
            </span>
          )}
        </div>
      </header>

      {/* Main Workspace */}
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-2 gap-8 p-8 max-w-7xl w-full mx-auto">
        {/* Ingestion Panel */}
        <div className="bg-white border border-slate-200 rounded-xl p-6 flex flex-col justify-between shadow-xs space-y-4">
          <div className="flex flex-col flex-1 space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-xs font-bold uppercase tracking-wider text-slate-500">Data Input Stream</label>
              {selectedFile && (
                <button onClick={clearFile} className="text-xs text-red-500 hover:text-red-700 font-medium transition-colors">
                  Clear Uploaded File
                </button>
              )}
            </div>
            
            <textarea
              className="w-full flex-1 min-h-[300px] bg-slate-50 border border-slate-200 rounded-lg p-4 text-sm text-slate-800 placeholder-slate-400 focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-600 focus:outline-none transition-all resize-none"
              placeholder="Paste raw email, corporate communication, or database logs here..."
              value={inputText}
              onChange={(e) => {
                if (selectedFile) setSelectedFile(null); // Switch back to text mode
                setInputText(e.target.value);
              }}
            />
            
            {/* Document Upload Zone */}
            <div 
              onClick={triggerFileSelect}
              className={`border-2 border-dashed rounded-lg p-5 flex flex-col items-center justify-center cursor-pointer transition-all ${
                selectedFile 
                  ? 'border-indigo-500 bg-indigo-50/30' 
                  : 'border-slate-300 bg-slate-50/50 hover:bg-slate-50 hover:border-slate-400'
              }`}
            >
              <input 
                type="file" 
                ref={fileInputRef} 
                onChange={handleFileChange} 
                className="hidden" 
                accept=".pdf,.docx,.txt"
              />
              <svg className="h-8 w-8 text-slate-400 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              <p className="text-sm font-semibold text-slate-700">
                {selectedFile ? `Document Attached: ${selectedFile.name}` : 'Upload PDF, Word (DOCX), or Text document'}
              </p>
              <p className="text-xs text-slate-500 mt-1">Automatic ingestion and layout parsing</p>
            </div>
          </div>

          <button
            onClick={() => handleRedaction()}
            disabled={isLoading || (!inputText.trim() && !selectedFile)}
            className="w-full bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-40 text-sm font-semibold py-3.5 rounded-lg shadow-sm hover:shadow-md transition-all active:scale-[0.99] flex items-center justify-center space-x-2"
          >
            {isLoading ? (
              <>
                <svg className="animate-spin h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                <span>Analyzing and Anonymizing...</span>
              </>
            ) : (
              <span>Redact & Secure Payload</span>
            )}
          </button>
        </div>

        {/* Output Panel */}
        <div className="bg-white border border-slate-200 rounded-xl p-6 flex flex-col justify-between shadow-xs space-y-4">
          <div className="flex flex-col flex-1 space-y-3">
            <div className="flex items-center justify-between">
              <label className="text-xs font-bold uppercase tracking-wider text-slate-500">Secured Outputs</label>
              {securedText && !securedText.startsWith('Error:') && (
                <button onClick={copyToClipboard} className="text-xs text-indigo-600 hover:text-indigo-800 font-semibold transition-colors">
                  Copy Output Content
                </button>
              )}
            </div>
            
            <div className="w-full flex-1 min-h-[420px] bg-slate-50 border border-slate-200 rounded-lg p-5 text-sm font-mono whitespace-pre-wrap overflow-y-auto text-slate-700 leading-relaxed">
              {securedText ? (
                <span className={securedText.startsWith('Error:') ? 'text-red-500 font-sans' : ''}>
                  {securedText}
                </span>
              ) : (
                <span className="text-slate-400 font-sans italic">Awaiting document/text stream submission...</span>
              )}
            </div>
          </div>
        </div>
      </main>

      {/* Analytics & Footer */}
      <footer className="border-t border-slate-200 bg-white mt-auto">
        <div className="max-w-7xl mx-auto px-8 py-6">
          {/* Telemetry Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div className="bg-slate-50 border border-slate-200/80 p-5 rounded-xl shadow-xs">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">Telemetry: Bytes Masked</p>
              <p className="text-3xl font-bold font-mono mt-1.5 text-slate-900">{metrics.charactersProcessed}</p>
            </div>
            
            <div className="bg-slate-50 border border-slate-200/80 p-5 rounded-xl shadow-xs">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">Telemetry: Entities Scrubbed</p>
              <p className="text-3xl font-bold font-mono mt-1.5 text-slate-900">{metrics.identitiesMasked}</p>
            </div>

            <div className="bg-slate-50 border border-slate-200/80 p-5 rounded-xl shadow-xs flex flex-col justify-between">
              <p className="text-xs font-bold text-slate-400 uppercase tracking-wider">Risk Evaluation</p>
              <span className={`self-start text-xs font-bold mt-2 px-3 py-1.5 rounded-lg border ${
                metrics.complianceRating === 'COMPLIANT' 
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200' 
                  : 'bg-amber-50 text-amber-700 border-amber-200'
              }`}>
                {metrics.complianceRating}
              </span>
            </div>
          </div>

          {/* Contact Details & Repo Link */}
          <div className="flex flex-col md:flex-row items-center justify-between border-t border-slate-100 pt-6 text-sm text-slate-500">
            <div className="mb-4 md:mb-0 flex items-center space-x-2">
              <span className="font-semibold text-slate-800">Udit Navariya</span>
              <span>• Enterprise Dev Portfolio</span>
            </div>
            
            <div className="flex items-center space-x-6">
              {/* GitHub Link */}
              <a 
                href="https://github.com/udit-gitops/Privacy-Redactor" 
                target="_blank" 
                rel="noreferrer"
                className="flex items-center space-x-1.5 hover:text-slate-900 transition-colors"
                title="Visit Github Repository"
              >
                <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
                  <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482C19.138 20.193 22 16.44 22 12.017 22 6.484 17.522 2 12 2z" />
                </svg>
                <span className="text-xs font-medium">GitHub Project Code</span>
              </a>

              {/* LinkedIn Link */}
              <a 
                href="https://www.linkedin.com/in/udit-navariya/" 
                target="_blank" 
                rel="noreferrer"
                className="flex items-center space-x-1.5 hover:text-slate-900 transition-colors"
                title="LinkedIn Profile"
              >
                <svg className="h-5 w-5" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z" />
                </svg>
                <span className="text-xs font-medium">LinkedIn</span>
              </a>

              {/* Gmail mailto Link */}
              <a 
                href="mailto:uditnarururu@gmail.com" 
                className="flex items-center space-x-1.5 hover:text-slate-900 transition-colors"
                title="Send Email"
              >
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
                <span className="text-xs font-medium">Gmail Contact</span>
              </a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
}