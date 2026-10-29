"""Tkinter interface for querying an English course syllabus PDF."""

from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from model import SyllabusRAG
from pdf_viewer import PDFViewer


QUICK_QUESTIONS = {
    "Course Objectives": "What are the course objectives?",
    "Modules": "What modules or topics does the course cover?",
    "Grading": "How is the course graded?",
    "Materials": "What textbooks and learning materials are listed?",
}

CHAT_BG = "#111827"
CHAT_PANEL_BG = "#1f2937"
CHAT_CARD_BG = "#273449"
CHAT_FG = "#f3f4f6"
CHAT_MUTED_FG = "#9ca3af"


class SyllabusApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("English Course Syllabus Assistant")
        self.root.geometry("560x330")
        self.root.minsize(480, 300)
        self.rag: SyllabusRAG | None = None
        self.preview_window: tk.Toplevel | None = None
        self.viewer: PDFViewer | None = None
        self.quick_buttons: list[tk.Button] = []
        self._chat_labels: list[tk.Label] = []
        self.busy = False
        self._load_generation = 0

        container = ttk.Frame(root, padding=28)
        container.pack(fill="both", expand=True)
        ttk.Label(
            container,
            text="Course Syllabus Assistant",
            font=("TkDefaultFont", 20, "bold"),
        ).pack(anchor="w", pady=(5, 8))
        ttk.Label(
            container,
            text=(
                "Upload one English course syllabus PDF to open the document "
                "viewer and grounded Q&A chat."
            ),
            wraplength=480,
        ).pack(anchor="w", pady=(0, 20))
        ttk.Button(
            container,
            text="Upload English syllabus PDF",
            command=self.upload_pdf,
        ).pack(anchor="w")
        self.upload_status = tk.StringVar(value="No syllabus loaded.")
        ttk.Label(
            container,
            textvariable=self.upload_status,
            wraplength=480,
        ).pack(anchor="w", pady=(14, 0))
        ttk.Label(
            container,
            text="The first run downloads the embedding model; the chat model "
            "downloads when you upload a syllabus PDF.",
            wraplength=480,
            foreground="#5c6773",
        ).pack(anchor="w", pady=(16, 0))

    def upload_pdf(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choose an English course syllabus",
            filetypes=[("PDF documents", "*.pdf")],
        )
        if not selected:
            return

        pdf_path = Path(selected)
        if pdf_path.suffix.lower() != ".pdf":
            messagebox.showerror("Invalid file", "Please select a PDF document.")
            return

        self._load_generation += 1
        generation = self._load_generation
        if self.preview_window is not None and self.preview_window.winfo_exists():
            self.preview_window.destroy()
        self.rag = None
        self.busy = False
        self.quick_buttons = []
        self._chat_labels = []
        self.upload_status.set(f"Preparing {pdf_path.name}…")

        window = tk.Toplevel(self.root)
        window.title(f"Syllabus Assistant — {pdf_path.name}")
        window.geometry("1320x850")
        window.minsize(980, 650)
        window.protocol("WM_DELETE_WINDOW", window.destroy)
        self.preview_window = window

        window.columnconfigure(0, weight=1, minsize=430)
        window.columnconfigure(1, weight=1, minsize=450)
        window.rowconfigure(0, weight=1)

        left = ttk.LabelFrame(window, text="Course syllabus PDF", padding=6)
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)
        try:
            self.viewer = PDFViewer(left, pdf_path)
        except Exception as exc:
            window.destroy()
            messagebox.showerror("Could not open PDF", str(exc))
            self.upload_status.set("The selected PDF could not be opened.")
            return
        self.viewer.grid(row=0, column=0, sticky="nsew")

        right = tk.Frame(
            window,
            background=CHAT_BG,
            padx=12,
            pady=12,
        )
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(4, weight=1)

        tk.Label(
            right,
            text="Ask about your syllabus",
            font=("TkDefaultFont", 17, "bold"),
            background=CHAT_BG,
            foreground=CHAT_FG,
        ).grid(row=0, column=0, sticky="w", pady=(2, 8))
        options = tk.Frame(right, background=CHAT_BG)
        options.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        for column in range(2):
            options.columnconfigure(column, weight=1)
        for index, (label, question) in enumerate(QUICK_QUESTIONS.items()):
            button = tk.Button(
                options,
                text=label,
                command=lambda prompt=question: self.submit_question(prompt),
                state="normal",
                relief="flat",
                borderwidth=0,
                padx=10,
                pady=8,
                cursor="hand2",
            )
            button.grid(
                row=index // 2,
                column=index % 2,
                sticky="ew",
                padx=(0, 5),
                pady=3,
            )
            self.quick_buttons.append(button)
        self._style_quick_buttons(ready=False)

        composer = tk.Frame(right, background=CHAT_BG)
        composer.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        composer.columnconfigure(0, weight=1)
        self.question = tk.StringVar()
        self.question_entry = tk.Entry(
            composer,
            textvariable=self.question,
            state="disabled",
            background=CHAT_PANEL_BG,
            foreground=CHAT_FG,
            insertbackground=CHAT_FG,
            disabledbackground=CHAT_PANEL_BG,
            disabledforeground="#ffffff",
            selectbackground="#2563eb",
            selectforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            highlightthickness=1,
            highlightbackground="#374151",
            highlightcolor="#60a5fa",
            insertwidth=2,
        )
        self.question_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.question_entry.bind("<Return>", lambda _event: self.submit_question())
        self.send_button = tk.Button(
            composer,
            text="Send",
            command=self.submit_question,
            state="disabled",
            background="#2563eb",
            foreground="#202735",
            activebackground="#1d4ed8",
            activeforeground="#202735",
            disabledforeground=CHAT_MUTED_FG,
            relief="flat",
            borderwidth=0,
            padx=14,
            pady=6,
            cursor="hand2",
        )
        self.send_button.grid(row=0, column=1)

        self.ready_message = tk.Label(
            right,
            text="You can now ask the chatbot about this syllabus.",
            background=CHAT_BG,
            foreground="#86efac",
        )
        self.ready_message.grid(row=3, column=0, sticky="w", pady=(0, 6))
        self.ready_message.grid_remove()

        conversation = tk.Frame(right, background=CHAT_BG)
        conversation.grid(row=4, column=0, sticky="nsew")
        conversation.rowconfigure(0, weight=1)
        conversation.columnconfigure(0, weight=1)
        self.chat_canvas = tk.Canvas(
            conversation,
            background=CHAT_BG,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        chat_scroll = tk.Scrollbar(
            conversation,
            orient="vertical",
            command=self.chat_canvas.yview,
            background=CHAT_PANEL_BG,
            activebackground="#374151",
            troughcolor=CHAT_BG,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
        )
        self.chat_canvas.configure(yscrollcommand=chat_scroll.set)
        self.chat_canvas.grid(row=0, column=0, sticky="nsew")
        chat_scroll.grid(row=0, column=1, sticky="ns")
        self.chat_messages = tk.Frame(
            self.chat_canvas,
            background=CHAT_BG,
        )
        self.chat_window = self.chat_canvas.create_window(
            (0, 0),
            window=self.chat_messages,
            anchor="nw",
        )
        self.chat_messages.bind("<Configure>", self._update_chat_scrollregion)
        self.chat_canvas.bind("<Configure>", self._resize_chat_messages)
        self._append_chat(
            "Assistant",
            "Your PDF is being prepared. The chat input will become available "
            "when the syllabus and chat model are ready.",
            "status",
        )

        self.source_buttons_frame = tk.Frame(
            right,
            background=CHAT_BG,
        )
        self.source_buttons_frame.grid(row=5, column=0, sticky="ew", pady=(6, 0))
        self.status = tk.StringVar(
            value="Indexing PDF, creating embeddings, and loading the chat model…"
        )
        tk.Label(
            right,
            textvariable=self.status,
            wraplength=550,
            background=CHAT_BG,
            foreground=CHAT_MUTED_FG,
        ).grid(row=6, column=0, sticky="w", pady=(5, 8))

        threading.Thread(
            target=self._build_index,
            args=(pdf_path, generation),
            daemon=True,
        ).start()

    def _build_index(self, pdf_path: Path, generation: int) -> None:
        try:
            rag = SyllabusRAG(pdf_path)
            rag.prepare_chat_model()
        except Exception as exc:
            self.root.after(
                0,
                lambda error=exc: self._index_failed(error, generation),
            )
            return
        self.root.after(
            0,
            lambda: self._index_ready(rag, pdf_path, generation),
        )

    def _index_failed(self, error: Exception, generation: int) -> None:
        if generation != self._load_generation or not self._preview_is_open():
            return
        self.status.set(f"Could not index PDF: {error}")
        self._append_chat(
            "Assistant",
            f"Indexing failed: {error}",
            "error",
        )
        self.upload_status.set("The PDF could not be indexed.")

    def _index_ready(
        self, rag: SyllabusRAG, pdf_path: Path, generation: int
    ) -> None:
        if generation != self._load_generation or not self._preview_is_open():
            return
        self.rag = rag
        self.status.set(
            f"Ready — indexed {len(rag.nodes)} passages from {pdf_path.name}."
        )
        self.ready_message.grid()
        self._append_chat(
            "Assistant",
            "The English syllabus is ready. You can now type a question or "
            "choose a starter question. Select a source below an answer to jump to and "
            "highlight its passage in the PDF.",
            "assistant",
        )
        self._style_quick_buttons(ready=True)
        self.question_entry.configure(state="normal")
        self.send_button.configure(state="normal")
        self.question_entry.focus_set()
        self.upload_status.set(f"Loaded {pdf_path.name}.")

    def submit_question(self, prompt: str | None = None) -> None:
        if self.rag is None or self.busy:
            return
        if prompt is not None:
            self.question.set(prompt)
        question = self.question.get().strip()
        if not question:
            return

        self.busy = True
        self.question_entry.configure(state="disabled")
        self.send_button.configure(state="disabled")
        self._append_chat("You", question, "user")
        self.question.set("")
        self.status.set("Searching the syllabus and generating an answer…")
        rag = self.rag

        threading.Thread(
            target=self._answer_question,
            args=(rag, question),
            daemon=True,
        ).start()

    def _answer_question(self, rag: SyllabusRAG, question: str) -> None:
        try:
            answer, sources = rag.ask(question)
        except Exception as exc:
            self.root.after(
                0, lambda error=exc: self._answer_failed(error, rag)
            )
            return
        self.root.after(
            0, lambda: self._answer_ready(answer, sources, rag)
        )

    def _answer_failed(self, error: Exception, rag: SyllabusRAG) -> None:
        if rag is not self.rag or not self._preview_is_open():
            return
        self._set_busy(False)
        self.status.set("The question could not be answered.")
        self._append_chat("Assistant", f"Error: {error}", "error")

    def _answer_ready(
        self,
        answer: str,
        sources: list[dict[str, Any]],
        rag: SyllabusRAG,
    ) -> None:
        if rag is not self.rag or not self._preview_is_open():
            return
        self._append_chat("Assistant", answer, "assistant")
        self._show_sources(sources)
        self.status.set("Answer ready. Click a source to highlight it in the PDF.")
        self._set_busy(False)

    def _show_sources(self, sources: list[dict[str, Any]]) -> None:
        for child in self.source_buttons_frame.winfo_children():
            child.destroy()
        if not sources:
            return
        tk.Label(
            self.source_buttons_frame,
            text="Jump to source:",
            background=CHAT_BG,
            foreground=CHAT_FG,
        ).pack(
            side="left",
            padx=(0, 6),
        )
        for index, source in enumerate(sources, start=1):
            label = f"{index}. p. {source['page']} ({source['score']:.2f})"
            tk.Button(
                self.source_buttons_frame,
                text=label,
                command=lambda item=source: self._show_source(item),
                background=CHAT_PANEL_BG,
                foreground="#202735",
                activebackground="#374151",
                activeforeground="#202735",
                relief="flat",
                borderwidth=0,
                padx=8,
                pady=4,
                cursor="hand2",
            ).pack(side="left", padx=3)

    def _show_source(self, source: dict[str, Any]) -> None:
        if self.viewer is not None and self.viewer.winfo_exists():
            self.viewer.show_page(source["page"], source["text"])

    def _resize_chat_messages(self, event: tk.Event) -> None:
        self._set_chat_width(event.width)

    def _set_chat_width(self, width: int) -> None:
        self.chat_canvas.itemconfigure(self.chat_window, width=width)
        wraplength = max(width - 64, 180)
        for label in self._chat_labels:
            label.configure(wraplength=wraplength)

    def _update_chat_scrollregion(self, _event: tk.Event) -> None:
        self.chat_canvas.configure(
            scrollregion=self.chat_canvas.bbox("all")
        )

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        enabled = "normal" if not busy and self.rag is not None else "disabled"
        self.question_entry.configure(state=enabled)
        self.send_button.configure(state=enabled)

    def _style_quick_buttons(self, ready: bool) -> None:
        background = CHAT_PANEL_BG if ready else "#202735"
        foreground = "#111827" if ready else "#475569"
        active_background = "#374151" if ready else "#202735"
        for button in self.quick_buttons:
            button.configure(
                state="normal",
                background=background,
                foreground=foreground,
                activebackground=active_background,
                activeforeground=foreground,
                cursor="hand2" if ready else "arrow",
            )

    def _preview_is_open(self) -> bool:
        return (
            self.preview_window is not None
            and self.preview_window.winfo_exists()
        )

    def _append_chat(self, speaker: str, text: str, tag: str) -> None:
        if not self._preview_is_open():
            return
        if speaker == "Assistant":
            border_color = "#56647a" if tag != "error" else "#8b3a46"
            card_color = CHAT_CARD_BG if tag != "error" else "#3b2028"
            card = tk.Frame(
                self.chat_messages,
                background=border_color,
                padx=1,
                pady=1,
            )
            card.pack(fill="x", padx=8, pady=6)
            content = tk.Frame(
                card,
                background=card_color,
                padx=14,
                pady=11,
            )
            content.pack(fill="x")
            text_color = "#fecaca" if tag == "error" else CHAT_FG
        else:
            card = tk.Frame(self.chat_messages, background=CHAT_BG)
            card.pack(fill="x", padx=8, pady=5)
            content = card
            text_color = "#dbeafe"

        header = tk.Label(
            content,
            text=speaker,
            anchor="w",
            background=content.cget("background"),
            foreground=text_color,
            font=("TkDefaultFont", 10, "bold"),
        )
        header.pack(fill="x", anchor="w")
        body = tk.Label(
            content,
            text=text,
            justify="left",
            anchor="w",
            background=content.cget("background"),
            foreground=text_color,
            font=("TkDefaultFont", 11),
        )
        body.pack(fill="x", anchor="w", pady=(4, 0))
        self._chat_labels.extend((header, body))
        self.chat_canvas.update_idletasks()
        width = self.chat_canvas.winfo_width()
        if width > 1:
            self._set_chat_width(width)
        self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all"))
        self.chat_canvas.yview_moveto(1.0)


def main() -> None:
    root = tk.Tk()
    SyllabusApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
