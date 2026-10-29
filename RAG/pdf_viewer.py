"""A small Tkinter PDF viewer with page-level text highlighting."""

from __future__ import annotations

import re
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any

import fitz
from PIL import Image, ImageDraw, ImageTk


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class PDFViewer(ttk.Frame):
    """Render one PDF page at a time and highlight its best matching passage."""

    def __init__(
        self,
        parent: tk.Misc,
        pdf_path: str | Path,
        **kwargs: Any,
    ) -> None:
        super().__init__(parent, **kwargs)
        self.pdf_path = Path(pdf_path)
        self.pdf = fitz.open(self.pdf_path)
        self.page_number = 1
        self.highlight_text = ""
        self._photo: ImageTk.PhotoImage | None = None
        self._resize_job: str | None = None

        controls = ttk.Frame(self)
        controls.pack(fill="x", padx=8, pady=8)
        self.previous_button = ttk.Button(
            controls, text="◀ Previous", command=self.previous_page
        )
        self.previous_button.pack(side="left")
        self.page_label = ttk.Label(controls, anchor="center")
        self.page_label.pack(side="left", expand=True, fill="x", padx=8)
        self.next_button = ttk.Button(
            controls, text="Next ▶", command=self.next_page
        )
        self.next_button.pack(side="right")

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, background="#dce2e8", highlightthickness=0)
        vertical_scroll = ttk.Scrollbar(
            body, orient="vertical", command=self.canvas.yview
        )
        horizontal_scroll = ttk.Scrollbar(
            body, orient="horizontal", command=self.canvas.xview
        )
        self.canvas.configure(
            yscrollcommand=vertical_scroll.set,
            xscrollcommand=horizontal_scroll.set,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vertical_scroll.grid(row=0, column=1, sticky="ns")
        horizontal_scroll.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        self.canvas.bind("<Configure>", self._schedule_render)
        self.show_page(1)

    def show_page(self, page_number: int, highlight_text: str | None = None) -> None:
        self.page_number = min(max(page_number, 1), len(self.pdf))
        if highlight_text is not None:
            self.highlight_text = highlight_text
        self._render_page()

    def previous_page(self) -> None:
        self.show_page(self.page_number - 1, "")

    def next_page(self) -> None:
        self.show_page(self.page_number + 1, "")

    def _schedule_render(self, _event: tk.Event) -> None:
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(120, self._render_page)

    def _render_page(self) -> None:
        self._resize_job = None
        if not self.winfo_exists():
            return

        page = self.pdf[self.page_number - 1]
        canvas_width = max(self.canvas.winfo_width() - 24, 320)
        canvas_height = max(self.canvas.winfo_height() - 24, 400)
        scale = min(
            canvas_width / page.rect.width,
            canvas_height / page.rect.height,
            2.0,
        )
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        image = Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples)

        rectangles = self._matching_rectangles(page, self.highlight_text)
        if rectangles:
            draw = ImageDraw.Draw(image, "RGBA")
            for x0, y0, x1, y1 in rectangles:
                draw.rectangle(
                    (x0 * scale, y0 * scale, x1 * scale, y1 * scale),
                    fill=(255, 218, 74, 105),
                    outline=(225, 148, 0, 220),
                    width=2,
                )

        self._photo = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.create_image(12, 12, anchor="nw", image=self._photo)
        self.canvas.configure(
            scrollregion=(0, 0, image.width + 24, image.height + 24)
        )
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self.page_label.configure(
            text=f"Page {self.page_number} of {len(self.pdf)}"
        )
        self.previous_button.configure(
            state="normal" if self.page_number > 1 else "disabled"
        )
        self.next_button.configure(
            state="normal" if self.page_number < len(self.pdf) else "disabled"
        )

    @staticmethod
    def _matching_rectangles(
        page: fitz.Page, passage: str
    ) -> list[tuple[float, float, float, float]]:
        passage_tokens = _tokens(passage)
        if not passage_tokens:
            return []

        words = page.get_text("words", sort=True)
        page_tokens: list[str] = []
        token_rectangles: list[tuple[float, float, float, float]] = []
        for word in words:
            word_tokens = _tokens(str(word[4]))
            rect = (float(word[0]), float(word[1]), float(word[2]), float(word[3]))
            page_tokens.extend(word_tokens)
            token_rectangles.extend([rect] * len(word_tokens))

        previous = [0] * (len(passage_tokens) + 1)
        best_length = 0
        best_page_end = 0
        minimum_match = min(4, len(passage_tokens))

        for page_index, page_token in enumerate(page_tokens):
            current = [0] * (len(passage_tokens) + 1)
            for passage_index, passage_token in enumerate(passage_tokens, start=1):
                if page_token == passage_token:
                    current[passage_index] = previous[passage_index - 1] + 1
                    if current[passage_index] > best_length:
                        best_length = current[passage_index]
                        best_page_end = page_index + 1
            previous = current

        if best_length < minimum_match:
            return []
        return token_rectangles[best_page_end - best_length : best_page_end]

    def destroy(self) -> None:
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
            self._resize_job = None
        self.pdf.close()
        super().destroy()
