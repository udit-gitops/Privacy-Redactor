'use client';

import React, { useState, useEffect, useRef } from 'react';

// ── Types ─────────────────────────────────────────────────────────────────────
interface Entity { text: string; type: string; score: number; start: number; end: number; }

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';

// ── Demo samples for hero animation ──────────────────────────────────────────
const DEMO_SAMPLES = [
  "Udit Navariya (udit@company.com) earns $85,000 at Apple Inc. His Aadhaar is 1234 5678 9012.",
  "John Doe, card 4111 1111 1111 1111, lives at 221B Baker Street, Mumbai.",
  "Transfer Rs. 2,75,000 to HDFC account 1234567890 IFSC HDFC0001234 from udit@oksbi.",
];

// ── Redaction animation in hero ───────────────────────────────────────────────
function RedactionPreview() {
  const [step, setStep] = useState<'typing'|'redacting'|'done'>('typing');
  const [displayText, setDisplayText] = useState('');
  const [sampleIdx, setSampleIdx] = useState(0);
  const [redactedText, setRedactedText] = useState('');
  const timerRef = useRef<ReturnType<typeof setTimeout>|null>(null);
  const sample = DEMO_SAMPLES[sampleIdx];

  useEffect(() => {
    setStep('typing'); setDisplayText(''); setRedactedText('');
    let i = 0;
    const typeNext = () => {
      if (i < sample.length) {
        setDisplayText(sample.slice(0, i + 1)); i++;
        timerRef.current = setTimeout(typeNext, 18);
      } else {
        timerRef.current = setTimeout(() => {
          setStep('redacting');
          const redacted = sample
            .replace(/Udit Navariya|John Doe/g, '<PERSON>')
            .replace(/udit@company\.com|udit@oksbi/g, '<EMAIL_ADDRESS>')
            .replace(/\$[\d,]+|\bRs\.\s?[\d,]+/g, '<MONEY>')
            .replace(/Apple Inc\./g, '<ORGANIZATION>')
            .replace(/\b\d{4}\s\d{4}\s\d{4}\b/g, '<AADHAAR>')
            .replace(/4111 1111 1111 1111/g, '<CREDIT_CARD>')
            .replace(/1234567890/g, '<BANK_ACCOUNT>')
            .replace(/HDFC0001234/g, '<IFSC>')
            .replace(/221B Baker Street, Mumbai/g, '<ADDRESS>');
          timerRef.current = setTimeout(() => {
            setRedactedText(redacted); setStep('done');
            timerRef.current = setTimeout(() => setSampleIdx(p => (p+1) % DEMO_SAMPLES.length), 3200);
          }, 700);
        }, 500);
      }
    };
    timerRef.current = setTimeout(typeNext, 300);
    return () => { if (timerRef.current) clearTimeout(timerRef.current); };
  }, [sampleIdx]);

  const renderText = step === 'done' ? redactedText : displayText;
  const isRedacted = step === 'done';

  return (
    <div className="rounded-xl border border-slate-700/60 bg-slate-900/80 backdrop-blur-sm overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-700/60 bg-slate-800/50">
        <div className="h-3 w-3 rounded-full bg-red-500/80" />
        <div className="h-3 w-3 rounded-full bg-amber-400/80" />
        <div className="h-3 w-3 rounded-full bg-emerald-400/80" />
        <span className="ml-3 text-xs text-slate-500 font-mono">privacy-redact — live</span>
        <div className="ml-auto flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${step==='redacting'?'bg-amber-400 animate-pulse':step==='done'?'bg-emerald-400':'bg-slate-600'}`} />
          <span className="text-[10px] text-slate-500 font-mono">
            {step==='typing'?'input':step==='redacting'?'scanning...':'secured'}
          </span>
        </div>
      </div>
      <div className="p-5 min-h-[90px] font-mono text-sm leading-relaxed">
        {renderText.split(/(<[A-Z_]+>)/g).map((part, i) =>
          /^<[A-Z_]+>$/.test(part)
            ? <span key={i} className={`inline-block px-1.5 py-0.5 rounded text-xs font-bold mx-0.5 transition-all duration-500 ${isRedacted?'bg-indigo-500/20 text-indigo-300 border border-indigo-500/40':'bg-slate-700 text-slate-400'}`}>{part}</span>
            : <span key={i} className={isRedacted?'text-slate-300':'text-slate-200'}>{part}</span>
        )}
        <span className="inline-block w-0.5 h-4 bg-indigo-400 ml-0.5 animate-pulse align-middle" />
      </div>
    </div>
  );
}

// ── Inline redaction tool (shown in modal) ────────────────────────────────────
function RedactionTool({ onClose }: { onClose: () => void }) {
  const [inputText, setInputText] = useState('');
  const [securedText, setSecuredText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [redactStyle, setRedactStyle] = useState('PLACEHOLDER');
  const [entities, setEntities] = useState<Entity[]>([]);
  const [copyState, setCopyState] = useState<'idle'|'copied'>('idle');
  const [selectedFile, setSelectedFile] = useState<File|null>(null);
  const [downloadDoc, setDownloadDoc] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleRedaction = async (file?: File, style?: string) => {
    const styleParam = style || redactStyle;
    if (!inputText.trim() && !file && !selectedFile) return;
    setIsLoading(true);
    try {
      let response: Response;
      const f = file || selectedFile;
      if (f) {
        const fd = new FormData();
        fd.append('file', f);
        fd.append('redact_style', styleParam);
        fd.append('return_redacted_document', downloadDoc ? 'true' : 'false');
        response = await fetch(`${API_BASE_URL}/api/v1/redact-file`, { method: 'POST', body: fd });
      } else {
        response = await fetch(`${API_BASE_URL}/api/v1/redact?redact_style=${styleParam}`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: inputText }),
        });
      }
      if (!response.ok) { const e = await response.json(); throw new Error(e.detail); }
      const ct = response.headers.get('content-type') || '';
      if (ct.includes('application/pdf') || ct.includes('image/') || ct.includes('text/plain')) {
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a'); a.href = url;
        const disp = response.headers.get('content-disposition') || '';
        const m = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(disp);
        a.download = m ? m[1].replace(/['"]/g,'') : `redacted_${f?.name??'file'}`;
        document.body.appendChild(a); a.click(); a.remove();
        window.URL.revokeObjectURL(url);
        setSecuredText(`✓ Downloaded: ${a.download}`);
      } else {
        const data = await response.json();
        const spaced = (data.secured_text as string).replace(/([^\s])(<)/g, '$1 $2');
        setSecuredText(spaced); setEntities(data.entities || []);
      }
    } catch (e: any) {
      setSecuredText(`Error: ${e.message}`);
    } finally { setIsLoading(false); }
  };

  const copy = () => {
    if (!securedText) return;
    navigator.clipboard.writeText(securedText).then(() => { setCopyState('copied'); setTimeout(()=>setCopyState('idle'),2000); });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" onClick={e => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" />
      <div className="relative w-full max-w-5xl max-h-[90vh] overflow-y-auto bg-[#111827] border border-slate-600 rounded-2xl shadow-2xl">
        {/* Modal header */}
        <div className="sticky top-0 z-10 flex items-center justify-between px-6 py-4 border-b border-slate-700 bg-[#111827]">
          <div className="flex items-center gap-2.5">
            <div className="h-7 w-7 rounded-lg bg-indigo-600 flex items-center justify-center">
              <svg className="h-3.5 w-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <span className="font-bold text-white">Privacy Redact</span>
            <span className="text-xs text-slate-500 ml-1">— redaction engine</span>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors p-1 rounded-lg hover:bg-slate-800">
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Tool body */}
        <div className="p-6 grid md:grid-cols-2 gap-6">
          {/* Input */}
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Input</label>
              {selectedFile && <button onClick={()=>{setSelectedFile(null);setInputText('');if(fileRef.current)fileRef.current.value='';}} className="text-xs text-red-400 hover:text-red-300">Clear file</button>}
            </div>
            <textarea
              className="w-full min-h-[200px] bg-slate-800 border border-slate-600 rounded-lg p-4 text-sm text-white placeholder-slate-500 focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500 focus:outline-none resize-none"
              placeholder="Paste text with sensitive data here..."
              value={inputText}
              onChange={e => { if(selectedFile)setSelectedFile(null); setInputText(e.target.value); }}
            />
            <div onClick={()=>fileRef.current?.click()}
              className={`border-2 border-dashed rounded-lg p-4 flex flex-col items-center justify-center cursor-pointer transition-all ${selectedFile?'border-indigo-500 bg-indigo-500/10':'border-slate-600 hover:border-slate-500 hover:bg-slate-700/40'}`}>
              <input type="file" ref={fileRef} className="hidden" accept=".pdf,.docx,.txt,.png,.jpg,.jpeg,.tiff"
                onChange={e => { const f=e.target.files?.[0]; if(f){setSelectedFile(f);setInputText(`File: ${f.name} (${Math.round(f.size/1024)}KB)`);handleRedaction(f);} }} />
              <svg className="h-5 w-5 text-slate-400 mb-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
              </svg>
              <p className="text-xs font-medium text-slate-300">{selectedFile ? `Attached: ${selectedFile.name}` : 'Drop a file or click to upload'}</p>
              <p className="text-[10px] text-slate-500 mt-0.5">PDF · DOCX · TXT · PNG · JPG · TIFF</p>
            </div>
            <div className="grid grid-cols-2 gap-3 bg-slate-800 border border-slate-600 rounded-lg p-3">
              <div>
                <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1">Style</label>
                <select value={redactStyle} onChange={e=>{setRedactStyle(e.target.value);if(inputText.trim()||selectedFile)handleRedaction(undefined,e.target.value);}}
                  className="w-full text-xs bg-slate-700 border border-slate-600 rounded-md p-2 text-white focus:ring-1 focus:ring-indigo-500 focus:outline-none">
                  <option value="PLACEHOLDER">Placeholder (&lt;PERSON&gt;)</option>
                  <option value="REDACTED">Tag ([REDACTED])</option>
                  <option value="MASK">Block mask (████)</option>
                  <option value="HIDDEN">Hidden tag</option>
                </select>
              </div>
              <div className="flex flex-col justify-center">
                <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-1.5">Output</label>
                <div className="flex items-center gap-2">
                  <input type="checkbox" id="dl" checked={downloadDoc} onChange={e=>setDownloadDoc(e.target.checked)} className="h-4 w-4 rounded border-slate-500 text-indigo-600 focus:ring-indigo-500" />
                  <label htmlFor="dl" className="text-xs text-slate-300 cursor-pointer select-none">Download redacted file</label>
                </div>
              </div>
            </div>
            <button onClick={()=>handleRedaction()} disabled={isLoading||(!inputText.trim()&&!selectedFile)}
              className="w-full bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 text-white text-sm font-semibold py-3 rounded-lg transition-all flex items-center justify-center gap-2">
              {isLoading ? (<><svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"/></svg>Scanning...</>) : 'Redact & Secure'}
            </button>
          </div>

          {/* Output */}
          <div className="flex flex-col gap-4">
            <div className="flex items-center justify-between">
              <label className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Secured Output</label>
              {securedText && !securedText.startsWith('Error:') && (
                <button onClick={copy} className={`text-xs font-semibold px-2.5 py-1 rounded-md transition-all ${copyState==='copied'?'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30':'text-indigo-400 hover:text-indigo-300 hover:bg-indigo-500/10'}`}>
                  {copyState==='copied'?'✓ Copied!':'Copy'}
                </button>
              )}
            </div>
            <div className="w-full min-h-[200px] flex-1 bg-slate-800 border border-slate-600 rounded-lg p-5 text-sm font-mono whitespace-pre-wrap overflow-y-auto text-white leading-relaxed">
              {securedText
                ? <span className={securedText.startsWith('Error:')?'text-red-400 font-sans':''}>{securedText}</span>
                : <span className="text-slate-500 font-sans italic">Redacted output will appear here...</span>
              }
            </div>
            {entities.length > 0 && (
              <div className="border border-slate-800 bg-slate-900/50 rounded-lg p-3 max-h-[120px] overflow-y-auto">
                <label className="block text-[10px] font-bold uppercase tracking-wider text-slate-600 mb-2">Detected</label>
                <div className="flex flex-wrap gap-1.5">
                  {entities.map((e,i) => (
                    <span key={i} className="text-[10px] bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 px-2 py-0.5 rounded-full flex items-center gap-1">
                      <span className="font-semibold">{e.text}</span>
                      <span className="opacity-40">·</span>
                      <span className="font-mono text-[9px] text-indigo-400">{e.type}</span>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Data ──────────────────────────────────────────────────────────────────────
const STATS = [
  { value: '25+', label: 'PII entity types' },
  { value: '3-layer', label: 'PDF extraction' },
  { value: 'Hindi + ENG', label: 'OCR support' },
  { value: 'DPDP ready', label: 'India compliance' },
];

const FEATURES = [
  {
    icon: <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" /></svg>,
    title: 'Indian PII Detection',
    desc: 'Aadhaar, PAN, Passport, GSTIN, UPI, IFSC, Voter ID, Driving License — all detected with high-confidence regex patterns built specifically for India.',
  },
  {
    icon: <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" /></svg>,
    title: 'Groq AI Context Layer',
    desc: 'LLaMA 3.1 resolves ambiguous words like "Apple" (fruit or company?) using surrounding context — fewer false positives, no missed detections.',
  },
  {
    icon: <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" /></svg>,
    title: '3-Layer PDF Processing',
    desc: 'Layout-aware text with PyMuPDF, table detection with pdfplumber, and Tesseract OCR fallback for scanned documents — all in one pipeline.',
  },
  {
    icon: <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" /><path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" /></svg>,
    title: 'Visual PDF Redaction',
    desc: 'Download a PDF with entities physically blacked out using annotation layers — not just text replacement. Original layout is fully preserved.',
  },
  {
    icon: <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M3.75 13.5l10.5-11.25L12 10.5h8.25L9.75 21.75 12 13.5H3.75z" /></svg>,
    title: '4 Redaction Styles',
    desc: 'Placeholder tags, [REDACTED] labels, █████ block masking, or hidden type labels. Configurable per request with instant re-processing.',
  },
  {
    icon: <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M7.5 14.25v2.25m3-4.5v4.5m3-6.75v6.75m3-9v9M6 20.25h12A2.25 2.25 0 0020.25 18V6A2.25 2.25 0 0018 3.75H6A2.25 2.25 0 003.75 6v12A2.25 2.25 0 006 20.25z" /></svg>,
    title: 'Audit Logging',
    desc: 'Every redaction event is logged to PostgreSQL with character count, entity count, and timestamps — full audit trail for compliance reporting.',
  },
];

const STEPS = [
  { step: '01', title: 'Upload or paste', desc: 'Drop a PDF, DOCX, image, or paste raw text directly into the input panel.' },
  { step: '02', title: 'Dual-engine scan', desc: 'Presidio NER runs pattern matching. Groq AI supplements with contextual entity detection.' },
  { step: '03', title: 'Conflict resolution', desc: 'Overlapping spans are merged by confidence score. Ambiguous entities go through AI tie-breaking.' },
  { step: '04', title: 'Redacted output', desc: 'Get clean text or download a physically redacted PDF with entities blacked out.' },
];

const TECH = [
  { name: 'Next.js 15', cat: 'Frontend' },
  { name: 'FastAPI', cat: 'Backend' },
  { name: 'Microsoft Presidio', cat: 'NER Engine' },
  { name: 'LLaMA 3.1 via Groq', cat: 'AI Layer' },
  { name: 'PyMuPDF', cat: 'PDF Processing' },
  { name: 'Tesseract OCR', cat: 'Image Processing' },
  { name: 'PostgreSQL', cat: 'Database' },
  { name: 'Docker', cat: 'Infrastructure' },
];

// ── Main landing page ─────────────────────────────────────────────────────────
export default function LandingPage() {
  const [menuOpen, setMenuOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const [showTool, setShowTool] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener('scroll', onScroll);
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  // Smooth scroll handler for nav links
  const scrollTo = (id: string) => {
    setMenuOpen(false);
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  // Lock body scroll when modal open
  useEffect(() => {
    document.body.style.overflow = showTool ? 'hidden' : '';
    return () => { document.body.style.overflow = ''; };
  }, [showTool]);

  return (
    <div className="min-h-screen bg-[#0A0F1E] text-slate-200 font-sans antialiased">

      {/* ── Modal tool ── */}
      {showTool && <RedactionTool onClose={() => setShowTool(false)} />}

      {/* ── Navbar ── */}
      <nav className={`fixed top-0 left-0 right-0 z-40 transition-all duration-300 ${scrolled?'bg-[#0A0F1E]/95 backdrop-blur-md border-b border-slate-800':'bg-transparent'}`}>
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="h-8 w-8 rounded-lg bg-indigo-600 flex items-center justify-center">
              <svg className="h-4 w-4 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <span className="font-bold text-white">Privacy Redact</span>
          </div>

          <div className="hidden md:flex items-center gap-8">
            {[['Features','features'],['How it works','how-it-works'],['Tech stack','tech-stack']].map(([label,id]) => (
              <button key={id} onClick={() => scrollTo(id)} className="text-sm text-slate-400 hover:text-white transition-colors">
                {label}
              </button>
            ))}
          </div>

          <div className="hidden md:flex items-center gap-3">
            <a href="https://github.com/udit-gitops/Privacy-Redactor" target="_blank" rel="noreferrer"
              className="text-sm text-slate-400 hover:text-white transition-colors flex items-center gap-1.5">
              <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24"><path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482C19.138 20.193 22 16.44 22 12.017 22 6.484 17.522 2 12 2z" /></svg>
              GitHub
            </a>
            <button onClick={() => setShowTool(true)}
              className="text-sm bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-lg font-medium transition-colors">
              Try it free →
            </button>
          </div>

          <button onClick={() => setMenuOpen(!menuOpen)} className="md:hidden text-slate-400 hover:text-white">
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d={menuOpen?"M6 18L18 6M6 6l12 12":"M4 6h16M4 12h16M4 18h16"} />
            </svg>
          </button>
        </div>

        {menuOpen && (
          <div className="md:hidden bg-[#0A0F1E]/98 border-b border-slate-800 px-6 py-4 flex flex-col gap-4">
            {[['Features','features'],['How it works','how-it-works'],['Tech stack','tech-stack']].map(([label,id]) => (
              <button key={id} onClick={() => scrollTo(id)} className="text-sm text-slate-400 hover:text-white text-left">{label}</button>
            ))}
            <button onClick={() => { setMenuOpen(false); setShowTool(true); }}
              className="text-sm bg-indigo-600 text-white px-4 py-2 rounded-lg font-medium text-center">
              Try it free →
            </button>
          </div>
        )}
      </nav>

      {/* ── Hero ── */}
      <section className="pt-32 pb-20 px-6 max-w-6xl mx-auto">
        <div className="grid lg:grid-cols-2 gap-12 items-center">
          <div>
            <div className="inline-flex items-center gap-2 bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 text-xs font-medium px-3 py-1.5 rounded-full mb-6">
              <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-pulse" />
              India's DPDP Act Compliant
            </div>
            <h1 className="text-4xl lg:text-5xl font-bold text-white leading-tight tracking-tight mb-5">
              Redact sensitive data{' '}
              <span className="text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-cyan-400">
                before it leaks.
              </span>
            </h1>
            <p className="text-slate-400 text-lg leading-relaxed mb-8">
              Enterprise-grade PII detection and redaction for Indian documents. Aadhaar, PAN, bank details, names — detected by AI, redacted instantly.
            </p>
            <div className="flex flex-wrap gap-3">
              <button onClick={() => setShowTool(true)}
                className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-6 py-3 rounded-lg transition-all hover:shadow-lg hover:shadow-indigo-500/25 active:scale-[0.98]">
                Try it free
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" /></svg>
              </button>
              <a href="https://github.com/udit-gitops/Privacy-Redactor" target="_blank" rel="noreferrer"
                className="inline-flex items-center gap-2 bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold px-6 py-3 rounded-lg border border-slate-700 transition-all">
                <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24"><path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482C19.138 20.193 22 16.44 22 12.017 22 6.484 17.522 2 12 2z" /></svg>
                View source
              </a>
            </div>
          </div>
          <div>
            <RedactionPreview />
          </div>
        </div>
      </section>

      {/* ── Stats ── */}
      <section className="border-y border-slate-800 bg-slate-900/40">
        <div className="max-w-6xl mx-auto px-6 py-10 grid grid-cols-2 md:grid-cols-4 gap-8">
          {STATS.map(s => (
            <div key={s.label} className="text-center">
              <div className="text-2xl font-bold text-white mb-1">{s.value}</div>
              <div className="text-xs text-slate-500 uppercase tracking-wider">{s.label}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Features ── */}
      <section id="features" className="py-24 px-6 max-w-6xl mx-auto scroll-mt-20">
        <div className="text-center mb-14">
          <p className="text-indigo-400 text-sm font-medium uppercase tracking-wider mb-3">Capabilities</p>
          <h2 className="text-3xl font-bold text-white mb-4">Everything you need for compliance</h2>
          <p className="text-slate-400 max-w-xl mx-auto">Built specifically for Indian data privacy requirements, with AI disambiguation on top.</p>
        </div>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURES.map(f => (
            <div key={f.title} className="bg-slate-900/60 border border-slate-800 rounded-xl p-6 hover:border-slate-700 transition-colors group">
              <div className="h-10 w-10 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 mb-4 group-hover:bg-indigo-500/20 transition-colors">
                {f.icon}
              </div>
              <h3 className="text-white font-semibold mb-2">{f.title}</h3>
              <p className="text-slate-400 text-sm leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── How it works ── */}
      <section id="how-it-works" className="py-24 px-6 bg-slate-900/30 border-y border-slate-800 scroll-mt-20">
        <div className="max-w-6xl mx-auto">
          <div className="text-center mb-14">
            <p className="text-indigo-400 text-sm font-medium uppercase tracking-wider mb-3">Pipeline</p>
            <h2 className="text-3xl font-bold text-white mb-4">How it works</h2>
            <p className="text-slate-400 max-w-xl mx-auto">A two-engine approach: deterministic pattern matching + AI context resolution.</p>
          </div>
          <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-6">
            {STEPS.map((s, i) => (
              <div key={s.step} className="relative">
                {i < STEPS.length - 1 && (
                  <div className="hidden lg:block absolute top-6 left-[calc(100%+0px)] w-full h-px bg-gradient-to-r from-slate-700 to-transparent z-0" />
                )}
                <div className="relative z-10 bg-slate-900 border border-slate-800 rounded-xl p-6">
                  <div className="text-indigo-400 font-mono text-xs font-bold mb-3">{s.step}</div>
                  <h3 className="text-white font-semibold mb-2">{s.title}</h3>
                  <p className="text-slate-400 text-sm leading-relaxed">{s.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Tech stack ── */}
      <section id="tech-stack" className="py-24 px-6 max-w-6xl mx-auto scroll-mt-20">
        <div className="text-center mb-14">
          <p className="text-indigo-400 text-sm font-medium uppercase tracking-wider mb-3">Stack</p>
          <h2 className="text-3xl font-bold text-white mb-4">Built on proven technology</h2>
          <p className="text-slate-400 max-w-xl mx-auto">No black boxes. Every component is open-source and production-tested.</p>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {TECH.map(t => (
            <div key={t.name} className="bg-slate-900/60 border border-slate-800 rounded-xl p-5 hover:border-indigo-500/30 transition-colors">
              <div className="text-[10px] text-indigo-400 font-medium uppercase tracking-wider mb-1.5">{t.cat}</div>
              <div className="text-white font-semibold text-sm">{t.name}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── CTA ── */}
      <section className="py-24 px-6">
        <div className="max-w-2xl mx-auto text-center">
          <div className="bg-gradient-to-br from-indigo-600/20 to-cyan-600/10 border border-indigo-500/20 rounded-2xl p-12">
            <h2 className="text-3xl font-bold text-white mb-4">Start redacting today</h2>
            <p className="text-slate-400 mb-8">No signup required. Paste your text or upload a document and see it work in seconds.</p>
            <button onClick={() => setShowTool(true)}
              className="inline-flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold px-8 py-4 rounded-xl text-lg transition-all hover:shadow-xl hover:shadow-indigo-500/30 active:scale-[0.98]">
              Launch the tool
              <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}><path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" /></svg>
            </button>
          </div>
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-slate-800 bg-slate-900/40">
        <div className="max-w-6xl mx-auto px-6 py-10">
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-8">
            <div>
              <div className="flex items-center gap-2 mb-4">
                <div className="h-7 w-7 rounded-lg bg-indigo-600 flex items-center justify-center">
                  <svg className="h-3.5 w-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" /></svg>
                </div>
                <span className="font-bold text-white">Privacy Redact</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {['Next.js 15','FastAPI','Presidio','LLaMA 3.1'].map(t => (
                  <span key={t} className="text-xs bg-slate-800 border border-slate-700 text-slate-400 px-2.5 py-1 rounded-full">{t}</span>
                ))}
              </div>
            </div>
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-600 mb-3">Contact</p>
              <p className="text-sm font-semibold text-white mb-3">Udit Navariya</p>
              <div className="flex items-center gap-5">
                <a href="https://github.com/udit-gitops" target="_blank" rel="noreferrer" title="GitHub"
                  className="flex items-center gap-1.5 text-slate-500 hover:text-white transition-colors text-xs">
                  <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24"><path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482C19.138 20.193 22 16.44 22 12.017 22 6.484 17.522 2 12 2z" /></svg>
                  GitHub
                </a>
                <a href="https://www.linkedin.com/in/udit-navariya/" target="_blank" rel="noreferrer" title="LinkedIn"
                  className="flex items-center gap-1.5 text-slate-500 hover:text-white transition-colors text-xs">
                  <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24"><path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z" /></svg>
                  LinkedIn
                </a>
                <a href="mailto:uditnavariya2005@gmail.com" title="uditnavariya2005@gmail.com"
                  className="flex items-center gap-1.5 text-slate-500 hover:text-white transition-colors text-xs">
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}><path strokeLinecap="round" strokeLinejoin="round" d="M21.75 6.75v10.5a2.25 2.25 0 01-2.25 2.25h-15a2.25 2.25 0 01-2.25-2.25V6.75m19.5 0A2.25 2.25 0 0019.5 4.5h-15a2.25 2.25 0 00-2.25 2.25m19.5 0v.243a2.25 2.25 0 01-1.07 1.916l-7.5 4.615a2.25 2.25 0 01-2.36 0L3.32 8.91a2.25 2.25 0 01-1.07-1.916V6.75" /></svg>
                  Email
                </a>
              </div>
            </div>
          </div>
          <div className="border-t border-slate-800 mt-8 pt-6 flex flex-col md:flex-row items-center justify-between gap-2 text-xs text-slate-600">
            <span>Built by Udit Navariya · Privacy Redact © 2026</span>
            <button onClick={() => setShowTool(true)} className="text-slate-500 hover:text-white transition-colors">
              Launch tool →
            </button>
          </div>
        </div>
      </footer>
    </div>
  );
}