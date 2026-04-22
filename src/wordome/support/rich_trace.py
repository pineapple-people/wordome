from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter

from rich.console import Console
from rich.text import Text


class RichTraceLogger:
    """
    Lightweight rich-backed tracer that renders nested steps as a tree.
    """

    def __init__(self, scope: str):
        self.scope = scope
        self.console = Console(stderr=True, highlight=False, soft_wrap=True)
        self._depth = 0

    def _indent(self, depth: int | None = None) -> str:
        depth = self._depth if depth is None else depth
        if depth <= 0:
            return ""
        return "│   " * (depth - 1) + "├── "

    def _render(self, message: str, style: str, depth: int | None = None) -> None:
        text = Text()
        text.append(self.scope, style="dim")
        text.append(" ", style="dim")
        text.append(self._indent(depth), style="dim")
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
        text = Text()
        text.append(self.scope, style="dim")
        text.append(" ", style="dim")
        text.append(self._indent(depth), style="dim")
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
        text = Text()
        text.append(self.scope, style="dim")
        text.append(" ", style="dim")
        text.append(self._indent(depth), style="dim")
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
        depth = self._depth
        self._render(label, "bold cyan", depth=depth)
        self._depth += 1
        try:
            yield
        except Exception as exc:
            elapsed = perf_counter() - start
            self._depth -= 1
            self._status(
                label,
                "failed",
                depth=depth,
                detail_label="after",
                detail_value=f"{elapsed:.2f}s: {exc}",
            )
            raise
        else:
            elapsed = perf_counter() - start
            self._depth -= 1
            self._status(
                label,
                "done",
                depth=depth,
                detail_label="runtime:",
                detail_value=f"{elapsed:.2f}s",
            )


_TRACE_CONTEXT: ContextVar[RichTraceLogger | None] = ContextVar(
    "wordome_rich_trace",
    default=None,
)


def current_trace() -> RichTraceLogger | None:
    return _TRACE_CONTEXT.get()


@contextmanager
def use_trace(trace: RichTraceLogger):
    token = _TRACE_CONTEXT.set(trace)
    try:
        yield trace
    finally:
        _TRACE_CONTEXT.reset(token)
