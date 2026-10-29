# English Course Syllabus Assistant

A local Tkinter application that indexes one English syllabus PDF, answers
questions from its content, and lets you jump to and highlight retrieved
passages in the PDF preview.

## Features

- Upload a searchable English PDF.
- Split page-level text with LlamaIndex `SentenceSplitter`.
- Embed chunks with `sentence-transformers/all-MiniLM-L6-v2`.
- Answer questions locally with `Qwen/Qwen2.5-1.5B-Instruct`.
- Cite the PDF filename and page, and click a source button to highlight its
  matching passage in the viewer.
- Starter questions for course objectives, modules, grading, and materials.

## Setup

Use Python 3.11 or 3.12 with Tkinter available, then install the dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

On macOS, install the Python distribution that includes Tkinter if
`python -m tkinter` does not open a small test window.

## Run

```bash
python app.py
```

The embedding and chat models download when a PDF is uploaded. The input and
starter questions become available after both models finish loading. Both
models run locally after downloading; the first run needs an internet
connection and several gigabytes of free disk space and memory. PDFs
containing only scanned page images are not supported without OCR.
