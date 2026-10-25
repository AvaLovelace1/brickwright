"""The conversation transcript: the live message list, mirrored to a log file."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Self


class Transcript:
    """The conversation, written to ``path`` one JSON message per line.

    ``messages`` is the live list passed to the completion call; :meth:`append`
    adds to it and writes the message to disk, flushing immediately for
    durability. Base64 image payloads are elided from the log copy only.

    On :meth:`close` an indented, human-readable ``<name>.pretty.json`` copy is also
    written alongside the ``.jsonl`` log -- the same elided messages as one JSON
    array, including the full multi-round history across any :meth:`reset`.
    """

    def __init__(self, path: Path) -> None:
        self.messages: list[dict[str, Any]] = []
        self._path = Path(path)
        # Everything written, for the pretty copy.
        self._logged: list[dict[str, Any]] = []
        self._file = self._path.open("w")

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def append(self, message: dict[str, Any]) -> None:
        """Append ``message`` to the conversation and log it durably."""
        self.messages.append(message)
        self._log(_loggable(message))

    def reset(self, seed_messages: list[dict[str, Any]]) -> None:
        """Start a new conversation in place, continuing the same log.

        Clears the live ``messages`` list and appends ``seed_messages`` so the next
        completion sees a fresh conversation. A marker is logged first, so the full
        multi-round history stays on disk and readable.
        """
        self.messages = []
        self._log({"role": "_meta", "event": "conversation_reset"})
        for message in seed_messages:
            self.append(message)

    def close(self) -> None:
        """Close the log file and write the indented copy. Safe to call repeatedly."""
        if self._file.closed:
            return
        self._file.close()
        pretty_path = self._path.with_name(self._path.stem + ".pretty.json")
        pretty_path.write_text(
            json.dumps(self._logged, indent=2, ensure_ascii=False) + "\n"
        )

    def _log(self, entry: dict[str, Any]) -> None:
        """Write one log entry as a JSON line and keep it for the pretty copy."""
        self._logged.append(entry)
        json.dump(entry, self._file)
        self._file.write("\n")
        self._file.flush()


def _loggable(message: dict[str, Any]) -> dict[str, Any]:
    """A copy of ``message`` safe to log: base64 image data replaced by a marker.

    The full image is sent to the model and saved in the record already; the log
    keeps everything else verbatim but swaps the data URL for ``<image: <mime>
    elided>`` so the file stays small and readable.
    """
    content = message.get("content")
    if not isinstance(content, list):
        return message
    out = copy.deepcopy(message)
    for part in out["content"]:
        url = _image_data_url(part)
        if url is not None:
            part["image_url"]["url"] = f"<image: {_mime_of(url)} elided>"
    return out


def _image_data_url(part: Any) -> str | None:
    """The ``data:`` image URL carried by a content ``part``, or None."""
    if not isinstance(part, dict) or part.get("type") != "image_url":
        return None
    url = part.get("image_url", {}).get("url", "")
    return url if isinstance(url, str) and url.startswith("data:") else None


def _mime_of(data_url: str) -> str:
    """The media type of a ``data:<mime>;...`` URL (``image`` if unparseable)."""
    return data_url[len("data:") :].split(";", 1)[0] or "image"
