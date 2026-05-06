# Ingestion pipeline

Per-document arq job that runs five idempotent steps. Step state is gated by
`document.status` plus a `processing_steps` list in `meta_json` so re-runs
after a crash skip already-finished work.

```mermaid
flowchart LR
  upload["POST /documents"] --> store["S3/MinIO put"]
  store --> dbrow["INSERT document(status=pending)"]
  dbrow --> enqueue["arq.enqueue(ingest_document)"]
  enqueue --> step1["extract_text"]
  step1 --> step2["chunk"]
  step2 --> step3["embed"]
  step3 --> step4["extract_claims"]
  step4 --> step5["link_claims"]
  step5 --> ready["status=ready"]
```

## Per-kind extractors

| kind     | path                         | notes                                                                                    |
| -------- | ---------------------------- | ---------------------------------------------------------------------------------------- |
| pdf_text | `ingest/pdf.py`              | `pypdfium2` text per page; no LLM                                                        |
| pdf_scan | `ingest/pdf.py` + `image.py` | render pages, then Tesseract; vision-LLM fallback (cost-capped) for low-confidence pages |
| image    | `ingest/image.py`            | Tesseract; same fallback                                                                 |
| text     | `ingest/text.py`             | UTF-8 with chardet fallback                                                              |
| gedcom   | `ingest/gedcom.py`           | python-gedcom-style parsing; high-confidence direct claim emission                       |
| note     | `ingest/note.py`             | source kind `family_oral`; confidence floor                                              |

## Storage layout

```
tree/{tree_id}/originals/{sha256[0:2]}/{sha256}.{ext}
tree/{tree_id}/derived/{document_id}/page-{n:04d}.png
tree/{tree_id}/derived/{document_id}/text-{n:04d}.txt
tree/{tree_id}/derived/{document_id}/ocr-{n:04d}.json
tree/{tree_id}/exports/gedcom-{ts}.ged
```

## Idempotency

- Upload dedup: unique `(tree_id, sha256)`.
- Per-step gating: `meta_json.processing_steps` list.
- Embedding cache: `inference_cache` keyed on `(model, prompt_version, content_hash)`.
- Claim insert: partial unique `(source_id, chunk_id, predicate, md5(object_json::text))`.
