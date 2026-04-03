"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import { getDocumentFileBlob, type DocumentItem } from "@/lib/api";

// Configure PDF.js worker — use unpkg CDN with exact version matching react-pdf's pdfjs
pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

interface Citation {
  text: string;
  page: number;
}

interface DocumentViewerProps {
  doc: DocumentItem;
  loanId: string;
  onClose: () => void;
  onConfirm?: () => void;
  onReupload?: () => void;
}

function normalize(s: string): string {
  return s.toLowerCase().replace(/[,$%]/g, "").replace(/\s+/g, " ").trim();
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

export default function DocumentViewer({
  doc,
  loanId,
  onClose,
  onConfirm,
  onReupload,
}: DocumentViewerProps) {
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [fileLoading, setFileLoading] = useState(true);
  const [fileError, setFileError] = useState(false);
  const [pdfError, setPdfError] = useState(false);
  const [rawText, setRawText] = useState<string | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [scale, setScale] = useState(1.0);
  const [highlightField, setHighlightField] = useState<string | null>(null);
  const viewerRef = useRef<HTMLDivElement>(null);
  const highlightTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const extractedData = doc.extracted_data || {};
  const citations: Record<string, Citation> =
    (extractedData._citations as Record<string, Citation>) || {};
  const displayFields = Object.entries(extractedData).filter(
    ([key]) => !key.startsWith("_")
  );

  const ext = (doc.file_name || "").toLowerCase().split(".").pop() || "";
  const isPdf = ext === "pdf";
  const isImage = ["jpg", "jpeg", "png", "gif", "webp", "tiff", "bmp"].includes(ext);

  // Fetch file as blob (authenticated)
  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;

    async function load() {
      try {
        const blob = await getDocumentFileBlob(loanId, doc.id);
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setFileUrl(objectUrl);
        // For text fallback: try to read the blob as text
        try {
          const textContent = await blob.text();
          const printable = [...textContent.slice(0, 500)].filter(
            (c) => c.charCodeAt(0) >= 32 || "\n\r\t".includes(c)
          ).length;
          if (printable / Math.max(textContent.slice(0, 500).length, 1) > 0.85) {
            setRawText(textContent);
          }
        } catch { /* ignore */ }
      } catch {
        if (!cancelled) setFileError(true);
      } finally {
        if (!cancelled) setFileLoading(false);
      }
    }

    load();
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [loanId, doc.id]);

  // Fallback timer: if PDF hasn't loaded after 5 seconds, assume it failed
  useEffect(() => {
    if (!isPdf || !fileUrl || pdfError || numPages > 0) return;
    const timer = setTimeout(() => {
      setPdfError(true);
    }, 5000);
    return () => clearTimeout(timer);
  }, [isPdf, fileUrl, pdfError, numPages]);

  // Close on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  // Apply text highlights in PDF text layer
  const applyHighlight = useCallback(
    (fieldKey: string | null) => {
      if (!viewerRef.current) return;

      // Clear existing highlights
      viewerRef.current
        .querySelectorAll(".citation-hl")
        .forEach((el) => {
          const htmlEl = el as HTMLElement;
          htmlEl.style.backgroundColor = "";
          htmlEl.style.outline = "";
          htmlEl.style.borderRadius = "";
          el.classList.remove("citation-hl");
        });

      if (!fieldKey) return;

      const citation = citations[fieldKey];
      const value = extractedData[fieldKey];

      // Build search terms (raw, not normalized — we normalize during comparison)
      const terms: string[] = [];
      if (citation?.text) terms.push(citation.text);
      if (typeof value === "string" && value.length > 2) terms.push(value);
      if (typeof value === "number") {
        terms.push(String(value));
        terms.push(value.toLocaleString());
      }

      if (terms.length === 0) return;

      // Collect text layer spans
      const spans = viewerRef.current.querySelectorAll(
        ".react-pdf__Page__textContent span"
      );
      const allItems: { text: string; norm: string; span: Element }[] = [];
      spans.forEach((span) => {
        const text = span.textContent || "";
        if (text.trim()) allItems.push({ text, norm: normalize(text), span });
      });

      if (allItems.length === 0) return;

      const hlStyle = (el: HTMLElement) => {
        el.style.backgroundColor = "rgba(250, 204, 21, 0.5)";
        el.style.outline = "2px solid rgba(234, 179, 8, 0.7)";
        el.style.borderRadius = "2px";
        el.classList.add("citation-hl");
      };

      let foundMatch = false;

      for (const term of terms) {
        const normTerm = normalize(term);
        if (normTerm.length < 2) continue;

        // Strategy 1: sliding window over consecutive spans
        // Build normalized text with span index boundaries
        // so we can correctly map back from normalized positions to spans
        const spanBounds: { spanIdx: number; normStart: number; normEnd: number }[] = [];
        let normPos = 0;
        for (let i = 0; i < allItems.length; i++) {
          const n = allItems[i].norm;
          if (normPos > 0) normPos += 1; // account for join space
          spanBounds.push({ spanIdx: i, normStart: normPos, normEnd: normPos + n.length });
          normPos += n.length;
        }

        // Build full normalized text using same spacing
        const fullNorm = allItems.map((t) => t.norm).join(" ");
        const idx = fullNorm.indexOf(normTerm);

        if (idx !== -1) {
          const matchEnd = idx + normTerm.length;
          let firstHighlighted = true;
          for (const { spanIdx, normStart, normEnd } of spanBounds) {
            if (normEnd > idx && normStart < matchEnd) {
              const htmlEl = allItems[spanIdx].span as HTMLElement;
              hlStyle(htmlEl);
              if (firstHighlighted) {
                allItems[spanIdx].span.scrollIntoView({ behavior: "smooth", block: "center" });
                firstHighlighted = false;
              }
            }
          }
          foundMatch = true;
          break;
        }

        // Strategy 2: single-span match for short values
        if (!foundMatch) {
          for (const item of allItems) {
            if (item.norm.includes(normTerm) || normTerm.includes(item.norm)) {
              if (item.norm.length >= 2) {
                hlStyle(item.span as HTMLElement);
                item.span.scrollIntoView({ behavior: "smooth", block: "center" });
                foundMatch = true;
                break;
              }
            }
          }
        }

        if (foundMatch) break;
      }
    },
    [citations, extractedData]
  );

  function handleFieldEnter(fieldKey: string) {
    const citation = citations[fieldKey];
    if (citation?.page && citation.page !== currentPage) {
      setCurrentPage(citation.page);
    }
    setHighlightField(fieldKey);

    // Small delay to let page render before searching text layer
    if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current);
    highlightTimerRef.current = setTimeout(
      () => applyHighlight(fieldKey),
      200
    );
  }

  function handleFieldLeave() {
    setHighlightField(null);
    if (highlightTimerRef.current) clearTimeout(highlightTimerRef.current);
    applyHighlight(null);
  }

  function onDocumentLoadSuccess({ numPages: n }: { numPages: number }) {
    setNumPages(n);
  }

  function formatValue(key: string, value: unknown): string {
    if (value === null || value === undefined) return "\u2014";
    if (Array.isArray(value)) {
      return value
        .map((v, i) => {
          if (typeof v === "object" && v !== null) {
            return `(${i + 1}) ${Object.entries(
              v as Record<string, unknown>
            )
              .map(([k, val]) => `${k}: ${val}`)
              .join(", ")}`;
          }
          return String(v);
        })
        .join("; ");
    }
    if (typeof value === "object") return JSON.stringify(value);
    if (typeof value === "number") {
      const isCurrency =
        !key.match(/year|last4|page|count|zip|ssn|ein/i) && value >= 1000;
      return isCurrency ? `$${value.toLocaleString()}` : String(value);
    }
    return String(value);
  }

  function highlightTextContent(text: string, fieldKey: string): string {
    const escaped = escapeHtml(text);
    const citation = citations[fieldKey];
    const value = extractedData[fieldKey];

    // Build search terms in priority order
    const terms: string[] = [];
    if (citation?.text) terms.push(citation.text);
    if (typeof value === "string" && value.length > 2) terms.push(value);
    if (typeof value === "number") {
      terms.push(String(value));
      terms.push(value.toLocaleString());
    }

    if (terms.length === 0) return escaped;

    for (const term of terms) {
      if (term.length < 2) continue;
      const escapedTerm = escapeHtml(term);
      // Case-insensitive search in the escaped HTML
      const idx = escaped.toLowerCase().indexOf(escapedTerm.toLowerCase());
      if (idx !== -1) {
        const before = escaped.slice(0, idx);
        const match = escaped.slice(idx, idx + escapedTerm.length);
        const after = escaped.slice(idx + escapedTerm.length);
        return `${before}<mark style="background-color: rgba(250, 204, 21, 0.5); outline: 2px solid rgba(234, 179, 8, 0.7); border-radius: 2px; padding: 0 2px;">${match}</mark>${after}`;
      }
    }

    return escaped;
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex" onClick={onClose}>
      <div
        className="flex flex-col w-full h-full bg-white"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header bar */}
        <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-200 bg-gray-50 flex-shrink-0">
          <div className="flex items-center gap-3 min-w-0">
            <button
              onClick={onClose}
              className="text-sm text-gray-500 hover:text-gray-800 flex items-center gap-1 flex-shrink-0"
            >
              <span className="text-lg">&larr;</span> Back
            </button>
            <div className="h-5 w-px bg-gray-300" />
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-gray-900 truncate">
                {doc.title || doc.file_name}
              </h2>
              <div className="flex items-center gap-2 text-xs text-gray-500">
                {doc.document_type && (
                  <span className="capitalize">
                    {doc.document_type.replace(/_/g, " ")}
                  </span>
                )}
                {doc.classification_confidence != null && (
                  <span>
                    &bull;{" "}
                    {(doc.classification_confidence * 100).toFixed(0)}%
                    confidence
                  </span>
                )}
                <span>&bull; {doc.file_name}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            {isPdf && (
              <>
                <button
                  onClick={() => setScale((s) => Math.max(0.5, s - 0.15))}
                  className="w-7 h-7 flex items-center justify-center text-sm border border-gray-300 rounded hover:bg-gray-100"
                >
                  -
                </button>
                <span className="text-xs text-gray-500 min-w-[3rem] text-center">
                  {Math.round(scale * 100)}%
                </span>
                <button
                  onClick={() => setScale((s) => Math.min(3, s + 0.15))}
                  className="w-7 h-7 flex items-center justify-center text-sm border border-gray-300 rounded hover:bg-gray-100"
                >
                  +
                </button>
                <div className="h-5 w-px bg-gray-300 mx-1" />
              </>
            )}
            <button
              onClick={onClose}
              className="w-7 h-7 flex items-center justify-center text-gray-400 hover:text-gray-700 border border-gray-300 rounded hover:bg-gray-100"
            >
              &times;
            </button>
          </div>
        </div>

        {/* Main split pane */}
        <div className="flex flex-1 overflow-hidden">
          {/* Left: Document viewer */}
          <div
            ref={viewerRef}
            className="flex-1 overflow-auto bg-gray-100 flex flex-col items-center p-4"
            style={{ minWidth: 0 }}
          >
            {fileLoading && (
              <div className="flex items-center justify-center h-full gap-2 text-gray-500">
                <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                <span className="text-sm">Loading document...</span>
              </div>
            )}

            {fileError && (
              <div className="flex items-center justify-center h-full text-gray-500">
                <div className="text-center">
                  <div className="text-4xl mb-2">&#128196;</div>
                  <p className="text-sm">
                    Unable to load document preview.
                  </p>
                  <p className="text-xs text-gray-400 mt-1">
                    The file may not be available in storage.
                  </p>
                </div>
              </div>
            )}

            {fileUrl && isPdf && !pdfError && (
              <>
                <Document
                  file={fileUrl}
                  onLoadSuccess={onDocumentLoadSuccess}
                  onLoadError={() => setPdfError(true)}
                  error={
                    <div className="flex items-center justify-center py-20 text-gray-500">
                      <div className="text-center">
                        <div className="text-4xl mb-2">&#128196;</div>
                        <p className="text-sm">Could not render PDF.</p>
                        <p className="text-xs text-gray-400 mt-1">Switching to text view...</p>
                      </div>
                    </div>
                  }
                  loading={
                    <div className="flex items-center gap-2 text-gray-500 py-20">
                      <div className="w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
                      <span className="text-sm">Rendering PDF...</span>
                    </div>
                  }
                >
                  <Page
                    pageNumber={currentPage}
                    scale={scale}
                    renderTextLayer={true}
                    renderAnnotationLayer={false}
                    className="shadow-lg"
                  />
                </Document>

                {numPages > 1 && (
                  <div className="flex items-center gap-3 mt-4 bg-white rounded-lg shadow-sm border px-4 py-2 sticky bottom-4">
                    <button
                      onClick={() =>
                        setCurrentPage((p) => Math.max(1, p - 1))
                      }
                      disabled={currentPage <= 1}
                      className="text-sm font-medium text-gray-600 hover:text-gray-900 disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                      &larr; Prev
                    </button>
                    <div className="flex items-center gap-1">
                      <input
                        type="number"
                        min={1}
                        max={numPages}
                        value={currentPage}
                        onChange={(e) => {
                          const val = parseInt(e.target.value);
                          if (val >= 1 && val <= numPages)
                            setCurrentPage(val);
                        }}
                        className="w-10 text-center text-sm border border-gray-300 rounded py-0.5"
                      />
                      <span className="text-sm text-gray-500">
                        of {numPages}
                      </span>
                    </div>
                    <button
                      onClick={() =>
                        setCurrentPage((p) =>
                          Math.min(numPages, p + 1)
                        )
                      }
                      disabled={currentPage >= numPages}
                      className="text-sm font-medium text-gray-600 hover:text-gray-900 disabled:opacity-30 disabled:cursor-not-allowed"
                    >
                      Next &rarr;
                    </button>
                  </div>
                )}
              </>
            )}

            {fileUrl && isImage && (
              <img
                src={fileUrl}
                alt={doc.file_name}
                className="max-w-full max-h-full object-contain shadow-lg rounded"
              />
            )}

            {/* Text fallback — for text files or PDFs that failed to parse */}
            {((fileUrl && !isPdf && !isImage) || pdfError) && rawText && (
              <div className="w-full max-w-3xl bg-white rounded-lg shadow-lg border overflow-hidden">
                <div className="px-4 py-2 bg-gray-50 border-b border-gray-200 text-xs text-gray-500 font-medium">
                  {doc.file_name} — Document Text
                </div>
                <pre
                  className="p-4 text-sm font-mono text-gray-800 whitespace-pre-wrap leading-relaxed overflow-auto max-h-[calc(100vh-160px)]"
                  dangerouslySetInnerHTML={{
                    __html: highlightField
                      ? highlightTextContent(rawText, highlightField)
                      : escapeHtml(rawText),
                  }}
                />
              </div>
            )}

            {/* No preview fallback — unsupported file type or PDF error with no text */}
            {((fileUrl && !isPdf && !isImage && !rawText) || (pdfError && !rawText)) && (
              <div className="flex items-center justify-center h-full text-gray-500">
                <div className="text-center">
                  <div className="text-4xl mb-2">&#128196;</div>
                  <p className="text-sm font-medium">{doc.file_name}</p>
                  <p className="text-xs text-gray-400 mt-1">
                    {pdfError
                      ? "This file could not be rendered as PDF. View extracted fields on the right."
                      : "Preview not available for this file type"}
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Right: Extracted fields panel */}
          <div className="w-[420px] flex-shrink-0 border-l border-gray-200 bg-white flex flex-col overflow-hidden">
            {/* Panel header */}
            <div className="px-4 py-3 border-b border-gray-200 bg-gradient-to-r from-indigo-50 to-white">
              <div className="flex items-center gap-2">
                <div className="w-6 h-6 rounded bg-indigo-100 flex items-center justify-center">
                  <span className="text-xs">&#128269;</span>
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-gray-900">
                    Extracted Fields
                  </h3>
                  <p className="text-[10px] text-gray-500">
                    Hover a field to highlight its source in the document
                  </p>
                </div>
              </div>
              {Object.keys(citations).length > 0 && (
                <div className="mt-2 flex items-center gap-1.5">
                  <span className="inline-block w-3 h-3 rounded-sm bg-yellow-300 border border-yellow-400" />
                  <span className="text-[10px] text-gray-500">
                    = source location in document
                  </span>
                </div>
              )}
            </div>

            {/* Fields list */}
            <div className="flex-1 overflow-y-auto p-3">
              {displayFields.length > 0 ? (
                <div className="space-y-1.5">
                  {displayFields.map(([key, value]) => {
                    if (
                      value === null ||
                      value === undefined ||
                      value === ""
                    )
                      return null;
                    const hasCitation = !!citations[key];
                    const isActive = highlightField === key;

                    return (
                      <div
                        key={key}
                        onMouseEnter={() => handleFieldEnter(key)}
                        onMouseLeave={handleFieldLeave}
                        className={`rounded-lg border px-3 py-2 transition-all duration-150 ${
                          isActive
                            ? "border-yellow-400 bg-yellow-50 shadow-md ring-2 ring-yellow-200"
                            : hasCitation
                            ? "border-gray-200 bg-white hover:border-indigo-300 hover:bg-indigo-50/30 cursor-pointer"
                            : "border-gray-100 bg-gray-50/50"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-0.5">
                          <span className="text-[10px] text-gray-500 uppercase tracking-wider font-medium">
                            {key.replace(/_/g, " ")}
                          </span>
                          {hasCitation && (
                            <span
                              className={`text-[9px] px-1.5 py-0.5 rounded-full font-medium ${
                                isActive
                                  ? "bg-yellow-200 text-yellow-800"
                                  : "bg-indigo-100 text-indigo-600"
                              }`}
                            >
                              p.{citations[key].page}
                            </span>
                          )}
                        </div>
                        <div className="text-sm font-semibold text-gray-900 break-words leading-snug">
                          {formatValue(key, value)}
                        </div>
                        {isActive && hasCitation && (
                          <div className="mt-1.5 text-[10px] text-gray-500 italic border-t border-yellow-200 pt-1 leading-relaxed">
                            <span className="font-medium text-yellow-700 not-italic">
                              Source:
                            </span>{" "}
                            &ldquo;
                            {citations[key].text.length > 100
                              ? citations[key].text.slice(0, 100) + "..."
                              : citations[key].text}
                            &rdquo;
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="text-sm text-gray-400 text-center py-12">
                  <div className="text-3xl mb-2">&#128203;</div>
                  No extracted data available
                </div>
              )}
            </div>

            {/* Action buttons */}
            {(onConfirm || onReupload) && (
              <div className="px-4 py-3 border-t border-gray-200 bg-gray-50 flex items-center gap-2">
                {onConfirm && (
                  <button
                    onClick={onConfirm}
                    className="flex-1 px-4 py-2.5 text-sm font-semibold text-white bg-green-600 rounded-lg hover:bg-green-700 transition-colors shadow-sm"
                  >
                    Approve Extraction
                  </button>
                )}
                {onReupload && (
                  <button
                    onClick={onReupload}
                    className="px-4 py-2.5 text-sm font-medium text-gray-700 border border-gray-300 rounded-lg hover:bg-gray-100 transition-colors"
                  >
                    Re-upload
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
