"""PDF syllabus retrieval and local answer generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import fitz
import numpy as np
from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter
from sentence_transformers import SentenceTransformer


EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
LLM_MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
CHUNK_SIZE = 180
CHUNK_OVERLAP = 40
TOP_K = 3


class SyllabusRAG:
    """Build and query an English-only index for one syllabus PDF."""

    def __init__(
        self,
        pdf_path: str | Path,
        embedding_model_name: str = EMBEDDING_MODEL,
        llm_model_name: str = LLM_MODEL,
    ) -> None:
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.is_file() or self.pdf_path.suffix.lower() != ".pdf":
            raise ValueError("Select an existing PDF syllabus file.")

        self.embedding_model_name = embedding_model_name
        self.llm_model_name = llm_model_name
        self._tokenizer: Any = None
        self._llm: Any = None
        self._torch: Any = None
        self._llm_device: str | None = None

        documents = self._extract_pages()
        if not documents:
            raise ValueError(
                "No selectable text was found in this PDF. "
                "Scanned PDFs need OCR before they can be used."
            )

        splitter = SentenceSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
        )
        self.nodes = splitter.get_nodes_from_documents(documents)
        if not self.nodes:
            raise ValueError("The PDF did not contain text that could be indexed.")

        self.embedding_model = SentenceTransformer(self.embedding_model_name)
        self.embeddings = np.asarray(
            self.embedding_model.encode(
                [node.text for node in self.nodes],
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            ),
            dtype=np.float32,
        )

    def _extract_pages(self) -> list[Document]:
        documents: list[Document] = []
        with fitz.open(self.pdf_path) as pdf:
            for page_number, page in enumerate(pdf, start=1):
                text = page.get_text("text").strip()
                if text:
                    documents.append(
                        Document(
                            text=text,
                            metadata={
                                "source": self.pdf_path.name,
                                "page": page_number,
                            },
                        )
                    )
        return documents

    def retrieve(self, question: str, top_k: int = TOP_K) -> list[dict[str, Any]]:
        """Return the most similar source passages and their PDF page numbers."""
        question = question.strip()
        if not question:
            return []

        query_embedding = np.asarray(
            self.embedding_model.encode(
                [question],
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )[0],
            dtype=np.float32,
        )
        scores = self.embeddings @ query_embedding
        count = min(max(top_k, 1), len(self.nodes))
        best_indices = np.argsort(scores)[::-1][:count]

        results: list[dict[str, Any]] = []
        for index in best_indices:
            node = self.nodes[int(index)]
            results.append(
                {
                    "text": node.text,
                    "source": str(node.metadata["source"]),
                    "page": int(node.metadata["page"]),
                    "score": float(scores[index]),
                }
            )
        return results

    def prepare_chat_model(self) -> None:
        """Load the local generation model before enabling the chat controls."""
        self._load_llm()

    def ask(
        self, question: str, top_k: int = TOP_K
    ) -> tuple[str, list[dict[str, Any]]]:
        question = question.strip()
        if not question:
            raise ValueError("Enter a question before sending it.")

        sources = self.retrieve(question, top_k=top_k)
        if not sources:
            return "I could not find relevant information in the syllabus.", []

        answer = self._generate_answer(question, sources)
        citations = sorted(
            {(item["source"], item["page"]) for item in sources},
            key=lambda citation: citation[1],
        )
        citation_text = "; ".join(
            f"{source} (PDF p. {page})" for source, page in citations
        )
        return f"{answer}\n\nSources: {citation_text}", sources

    def _load_llm(self) -> None:
        if self._llm is not None:
            return

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError(
                "The local language model requires PyTorch and Transformers. "
                "Install the dependencies from requirements.txt."
            ) from exc

        if torch.cuda.is_available():
            device = "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"

        dtype = torch.float16 if device in {"cuda", "mps"} else torch.float32
        self._tokenizer = AutoTokenizer.from_pretrained(self.llm_model_name)
        self._llm = AutoModelForCausalLM.from_pretrained(
            self.llm_model_name,
            torch_dtype=dtype,
        )
        self._llm.to(device)
        self._llm.eval()
        self._torch = torch
        self._llm_device = device

    def _generate_answer(
        self, question: str, sources: list[dict[str, Any]]
    ) -> str:
        self._load_llm()

        context = "\n\n".join(
            f"[Source: {item['source']}, PDF page {item['page']}]\n{item['text']}"
            for item in sources
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "You are an English-language course syllabus assistant. "
                    "Answer only in English and use only the syllabus context "
                    "provided. Do not invent dates, requirements, policies, "
                    "or grades. If the context does not answer the question, "
                    "say that the syllabus does not provide enough information. "
                    "Be concise and cite the relevant PDF page number."
                ),
            },
            {
                "role": "user",
                "content": f"Syllabus context:\n{context}\n\nQuestion: {question}",
            },
        ]
        prompt = self._tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = self._tokenizer(
            prompt,
            return_tensors="pt",
            truncation=True,
            max_length=4096,
        ).to(self._llm_device)

        with self._torch.inference_mode():
            output = self._llm.generate(
                **inputs,
                max_new_tokens=220,
                do_sample=False,
                pad_token_id=self._tokenizer.eos_token_id,
            )

        prompt_length = inputs["input_ids"].shape[1]
        answer = self._tokenizer.decode(
            output[0][prompt_length:],
            skip_special_tokens=True,
        ).strip()
        if not answer:
            raise RuntimeError("The language model returned an empty answer.")
        return answer
