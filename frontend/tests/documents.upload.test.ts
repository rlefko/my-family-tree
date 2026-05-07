/**
 * Tests for the document upload mutation. Verifies the FormData builder
 * produces the right shape, and that uploadDocumentRequest sends the right
 * URL and FormData via XHR.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { buildUploadFormData, uploadDocumentRequest } from "@/api/endpoints/documents";

describe("buildUploadFormData", () => {
  it("includes file and tree_id and omits kind by default", () => {
    const file = new File(["abc"], "evidence.pdf", { type: "application/pdf" });
    const fd = buildUploadFormData({ file, treeId: "tree-1" });
    expect(fd.get("tree_id")).toBe("tree-1");
    const got = fd.get("file");
    expect(got).toBeInstanceOf(File);
    expect((got as File).name).toBe("evidence.pdf");
    expect(fd.get("kind")).toBeNull();
  });

  it("appends kind when provided", () => {
    const file = new File(["abc"], "evidence.pdf", { type: "application/pdf" });
    const fd = buildUploadFormData({ file, treeId: "tree-1", kind: "pdf_text" });
    expect(fd.get("kind")).toBe("pdf_text");
  });
});

describe("uploadDocumentRequest", () => {
  let originalXHR: typeof XMLHttpRequest;
  const tracker: { last: FakeXHR | null } = { last: null };

  class FakeXHRUpload {
    listeners: Record<string, Array<(e: ProgressEvent) => void>> = {};
    addEventListener(event: string, fn: (e: ProgressEvent) => void) {
      (this.listeners[event] ??= []).push(fn);
    }
    fire(event: string, e: ProgressEvent) {
      (this.listeners[event] ?? []).forEach((fn) => fn(e));
    }
  }

  class FakeXHR {
    upload = new FakeXHRUpload();
    status = 0;
    statusText = "";
    responseText = "";
    requestHeaders: Record<string, string> = {};
    sentBody: FormData | null = null;
    method = "";
    url = "";
    listeners: Record<string, Array<(e: ProgressEvent) => void>> = {};
    open(method: string, url: string) {
      this.method = method;
      this.url = url;
    }
    setRequestHeader(name: string, value: string) {
      this.requestHeaders[name] = value;
    }
    addEventListener(event: string, fn: (e: ProgressEvent) => void) {
      (this.listeners[event] ??= []).push(fn);
    }
    send(body: FormData) {
      this.sentBody = body;
      tracker.last = this;
    }
    abort() {
      this.fire("abort", new ProgressEvent("abort"));
    }
    fire(event: string, e: ProgressEvent) {
      (this.listeners[event] ?? []).forEach((fn) => fn(e));
    }
  }

  beforeEach(() => {
    originalXHR = globalThis.XMLHttpRequest;
    tracker.last = null;
    vi.stubGlobal("XMLHttpRequest", FakeXHR as unknown as typeof XMLHttpRequest);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    globalThis.XMLHttpRequest = originalXHR;
  });

  it("posts to the documents endpoint with the FormData", async () => {
    const file = new File(["x".repeat(10)], "scan.pdf", { type: "application/pdf" });
    const promise = uploadDocumentRequest({ file, treeId: "tree-7" });
    const xhr = tracker.last;
    if (!xhr) throw new Error("XHR not constructed");
    expect(xhr.method).toBe("POST");
    expect(xhr.url).toMatch(/\/api\/v1\/documents$/);
    expect(xhr.requestHeaders["X-Request-ID"]).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/,
    );
    expect(xhr.sentBody).toBeInstanceOf(FormData);
    expect(xhr.sentBody?.get("tree_id")).toBe("tree-7");
    xhr.status = 201;
    xhr.responseText = JSON.stringify({
      id: "doc-1",
      kind: "pdf_text",
      mime_type: "application/pdf",
      byte_size: 10,
      sha256: "abc",
      original_filename: "scan.pdf",
      status: "pending",
      attempts: 0,
      imported_at: new Date().toISOString(),
      text_count: 0,
      chunk_count: 0,
      vision_calls: [],
    });
    xhr.fire("load", new ProgressEvent("load"));
    const result = await promise;
    expect(result.id).toBe("doc-1");
  });

  it("rejects with parsed error code on failure", async () => {
    const file = new File(["x"], "scan.pdf", { type: "application/pdf" });
    const promise = uploadDocumentRequest({ file, treeId: "tree-7" });
    const xhr = tracker.last;
    if (!xhr) throw new Error("XHR not constructed");
    xhr.status = 413;
    xhr.responseText = JSON.stringify({ error: { code: "request_too_large", message: "too big" } });
    xhr.fire("load", new ProgressEvent("load"));
    await expect(promise).rejects.toMatchObject({ status: 413, code: "request_too_large" });
  });
});
