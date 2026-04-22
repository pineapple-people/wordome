from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from rich.tree import Tree


class RichTraceLogger:
    """
    Lightweight rich-backed tracer that renders nested steps as a tree.
    """

    def __init__(self, scope: str):
        self.scope = scope
        self.console = Console(stderr=True, highlight=False, soft_wrap=True)
        self._tree = Tree(Text(self.scope, style="dim"))
        self._stack: list[Tree] = [self._tree]
        self._live = Live(
            self._tree,
            console=self.console,
            transient=False,
            auto_refresh=True,
            refresh_per_second=20,
        )
        self._live_started = False

    def start(self) -> None:
        if self._live_started:
            return
        self._live.__enter__()
        self._live_started = True
        self._refresh()

    def stop(self) -> None:
        if not self._live_started:
            return
        self._refresh()
        self._live.__exit__(None, None, None)
        self._live_started = False

    def _refresh(self) -> None:
        if self._live_started:
            self._live.update(self._tree, refresh=True)

    def _current_node(self) -> Tree:
        return self._stack[-1]

    def _active_step_label(self, label: str):
        return Text(label, style="bold cyan")

    def _render(self, message: str, style: str, depth: int | None = None) -> None:
        if self._live_started:
            self._current_node().add(Text(message, style=style))
            self._refresh()
            return
        text = Text()
        text.append(self.scope, style="dim")
        text.append(" ", style="dim")
        if depth:
            text.append("│   " * (depth - 1) + "├── ", style="dim")
        text.append(message, style=style)
        self.console.print(text)

    def _style_for_level(self, level: str) -> str:
        styles = {
            "default": "white",
            "info": "cyan",
            "warn": "yellow",
            "error": "bold red",
        }
        return styles.get(level, level)

    def _render_callout(
        self,
        label: str,
        value: str,
        depth: int | None = None,
        label_style: str = "bold cyan",
        value_style: str = "bold #a855f7",
    ) -> None:
        if self._live_started:
            text = Text()
            text.append(label, style=label_style)
            text.append(": ", style="dim")
            text.append(value, style=value_style)
            self._current_node().add(text)
            self._refresh()
            return
        text = Text()
        text.append(self.scope, style="dim")
        text.append(" ", style="dim")
        if depth:
            text.append("│   " * (depth - 1) + "├── ", style="dim")
        text.append(label, style=label_style)
        text.append(": ", style="dim")
        text.append(value, style=value_style)
        self.console.print(text)

    def _render_status(
        self,
        label: str,
        status: str,
        status_style: str,
        depth: int | None = None,
        detail_label: str | None = None,
        detail_value: str | None = None,
        detail_label_style: str = "bold #ff8ad6",
        detail_value_style: str = "bold #ff8ad6",
    ) -> None:
        if self._live_started:
            text = Text()
            text.append(label, style="bold cyan")
            text.append("  ", style="dim")
            text.append(f"[{status}]", style=status_style)
            if detail_label and detail_value:
                text.append("  ", style="dim")
                text.append(f"[{detail_label}", style=detail_label_style)
                text.append(" ", style="dim")
                text.append(detail_value, style=detail_value_style)
                text.append("]", style=detail_label_style)
            self._current_node().label = text
            self._refresh()
            return
        text = Text()
        text.append(self.scope, style="dim")
        text.append(" ", style="dim")
        if depth:
            text.append("│   " * (depth - 1) + "├── ", style="dim")
        text.append(label, style="bold cyan")
        text.append("  ", style="dim")
        text.append(f"[{status}]", style=status_style)
        if detail_label and detail_value:
            text.append("  ", style="dim")
            text.append(f"[{detail_label}", style=detail_label_style)
            text.append(" ", style="dim")
            text.append(detail_value, style=detail_value_style)
            text.append("]", style=detail_label_style)
        self.console.print(text)

    def message(
        self,
        message: str,
        level: str = "default",
    ) -> None:
        self._render(message, self._style_for_level(level))

    def callout(
        self,
        label: str,
        value: str,
    ) -> None:
        self._render_callout(label, value)

    def render_result(self, result, preview_reviews: int = 3) -> None:
        reviews = list(getattr(result, "reviews", []) or [])
        domain_metadata = getattr(
            getattr(getattr(result, "metadata", None), "domain_metadata", None),
            "review_tabs",
            [],
        )
        rating_scales = {
            getattr(review, "rating_scale_max", None)
            for review in reviews
            if getattr(review, "rating_scale_max", None) is not None
        }
        rating_scale_display = "mixed"
        if len(rating_scales) == 1:
            rating_scale_display = str(next(iter(rating_scales)))
        elif not rating_scales:
            rating_scale_display = "unknown"

        summary = Table(
            show_header=False,
            box=None,
            padding=(0, 1),
        )
        summary.add_column("field", style="bold cyan", no_wrap=True)
        summary.add_column("value", style="white")
        summary.add_row("Product", getattr(result, "product_url", ""))
        review_page_url = getattr(result, "review_page_url", "") or ""
        if review_page_url and review_page_url != getattr(result, "product_url", ""):
            summary.add_row("Review URL", review_page_url)
        summary.add_row(
            "Reviews",
            str(getattr(result, "reviews_count", None) or len(reviews)),
        )
        summary.add_row("Scale", rating_scale_display)
        summary.add_row(
            "Regions",
            ", ".join(domain_metadata) if domain_metadata else "none",
        )

        renderables = [Panel(summary, title="Review Result", border_style="cyan")]

        if reviews:
            preview = Table(title=f"Sample ({min(preview_reviews, len(reviews))})")
            preview.add_column("Author", style="bold cyan", no_wrap=True)
            preview.add_column("Title", style="bold")
            preview.add_column("Rating", style="magenta", no_wrap=True)
            preview.add_column("Excerpt", style="white")
            for review in reviews[:preview_reviews]:
                body = getattr(review, "body", "") or ""
                excerpt = body.strip().replace("\n", " ")
                if len(excerpt) > 90:
                    excerpt = excerpt[:87].rstrip() + "..."
                rating_value = getattr(review, "rating", None)
                scale_max = getattr(review, "rating_scale_max", None)
                rating_display = "—"
                if rating_value is not None:
                    rating_display = (
                        f"{rating_value:g}/{scale_max}"
                        if scale_max is not None
                        else f"{rating_value:g}"
                    )

                preview.add_row(
                    getattr(review, "author", "") or "anonymous",
                    getattr(review, "title", "") or "",
                    rating_display,
                    excerpt,
                )
            renderables.append(preview)

        self.console.print(Group(*renderables))

    def _status(
        self,
        label: str,
        state: str,
        *,
        depth: int | None = None,
        detail_label: str | None = None,
        detail_value: str | None = None,
    ) -> None:
        self._render_status(
            label,
            state,
            "green"
            if state == "done"
            else "bold red"
            if state == "failed"
            else "white",
            depth=depth,
            detail_label=detail_label,
            detail_value=detail_value,
        )

    @contextmanager
    def step(self, label: str):
        start = perf_counter()
        if not self._live_started:
            self.start()
        branch = self._current_node().add(self._active_step_label(label))
        self._stack.append(branch)
        self._refresh()
        try:
            yield
        except Exception as exc:
            elapsed = perf_counter() - start
            branch.label = self._status_text(
                label,
                "failed",
                detail_label="after",
                detail_value=f"{elapsed:.2f}s: {exc}",
                status_style="bold red",
            )
            self._refresh()
            self._stack.pop()
            raise
        else:
            elapsed = perf_counter() - start
            branch.label = self._status_text(
                label,
                "done",
                detail_label="runtime:",
                detail_value=f"{elapsed:.2f}s",
                status_style="green",
            )
            self._refresh()
            self._stack.pop()

    def _status_text(
        self,
        label: str,
        state: str,
        *,
        status_style: str,
        detail_label: str | None = None,
        detail_value: str | None = None,
    ) -> Text:
        text = Text()
        text.append(label, style="bold cyan")
        text.append("  ", style="dim")
        text.append(f"[{state}]", style=status_style)
        if detail_label and detail_value:
            text.append("  ", style="dim")
            text.append(f"[{detail_label}", style="bold #ff8ad6")
            text.append(" ", style="dim")
            text.append(detail_value, style="bold #ff8ad6")
            text.append("]", style="bold #ff8ad6")
        return text


class RichLiveTraceLogger(RichTraceLogger):
    """
    Rich-backed tracer with a live spinner cue for the active step.
    """

    def _active_step_label(self, label: str):
        return Spinner("dots", text=label, style="cyan")


_TRACE_CONTEXT: ContextVar[RichTraceLogger | None] = ContextVar(
    "wordome_rich_trace",
    default=None,
)


def current_trace() -> RichTraceLogger | None:
    return _TRACE_CONTEXT.get()


@contextmanager
def use_trace(trace: RichTraceLogger):
    trace.start()
    token = _TRACE_CONTEXT.set(trace)
    try:
        yield trace
    finally:
        _TRACE_CONTEXT.reset(token)
        trace.stop()
