"""Rest client stub."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Message:
    sid: str


class Messages:
    def create(self, body: str, from_: str, to: str) -> Message:  # type: ignore[override]
        return Message(sid="SM123")


class Client:
    def __init__(self, sid: str, token: str) -> None:
        self.messages = Messages()
