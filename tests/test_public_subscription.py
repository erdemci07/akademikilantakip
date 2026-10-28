from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


class FakeSubscribers:
    def __init__(self):
        self.enabled: set[int] = set()
        self.seen: set[int] = set()
        self.deleted: set[int] = set()

    def subscribe(self, chat_id: int) -> bool:
        first = chat_id not in self.seen
        self.seen.add(chat_id)
        self.enabled.add(chat_id)
        return first

    def unsubscribe(self, chat_id: int) -> None:
        self.enabled.discard(chat_id)

    def forget(self, chat_id: int) -> None:
        self.enabled.discard(chat_id)
        self.seen.discard(chat_id)
        self.deleted.add(chat_id)


@pytest.fixture
def command_runner():
    path = Path(__file__).resolve().parents[1] / "functions" / "subscription_logic.py"
    spec = importlib.util.spec_from_file_location("public_subscription_logic", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.process_update


def message(text: str, chat_id: int = 101, chat_type: str = "private") -> dict:
    return {"message": {"chat": {"type": chat_type, "id": chat_id}, "text": text}}


@pytest.mark.parametrize("command", ["/start", "/devam", "/start@AkademikBot"])
def test_start_adds_private_chat(command_runner, command):
    store = FakeSubscribers()
    replies = []
    assert command_runner(message(command), store, lambda chat_id, text: replies.append((chat_id, text)))
    assert store.enabled == {101}
    assert replies[0][0] == 101
    assert "aktif" in replies[0][1]


def test_stop_and_resume(command_runner):
    store = FakeSubscribers()
    def send(chat_id, text):
        return None
    command_runner(message("/start"), store, send)
    command_runner(message("/dur"), store, send)
    assert store.enabled == set()
    command_runner(message("/devam"), store, send)
    assert store.enabled == {101}


def test_delete_record(command_runner):
    store = FakeSubscribers()
    command_runner(message("/start"), store, lambda chat_id, text: None)
    command_runner(message("/sil"), store, lambda chat_id, text: None)
    assert store.deleted == {101}


def test_ignore_group_commands(command_runner):
    store = FakeSubscribers()
    assert not command_runner(message("/start", -100, "supergroup"), store, lambda *_: None)
    assert store.enabled == set()


def test_ignore_non_command_and_invalid_id(command_runner):
    store = FakeSubscribers()
    assert not command_runner(message("Merhaba"), store, lambda *_: None)
    assert not command_runner(message("/start", True), store, lambda *_: None)
    assert store.enabled == set()


def test_status_without_record(command_runner):
    responses = []
    store = FakeSubscribers()
    assert command_runner(message("/durum"), store, lambda _, text: responses.append(text))
    assert "Henüz" in responses[0]


def test_unknown_command_not_handled(command_runner):
    assert not command_runner(message("/random"), FakeSubscribers(), lambda *_: None)


class SampleHistory:
    def __init__(self):
        self.reads = 0

    def initial_history_summary(self) -> str:
        self.reads += 1
        return "📚 Geçmişten 8 ilan: https://uni.edu.tr/ilan"


def test_first_start_delivers_history_once(command_runner):
    store = FakeSubscribers()
    history = SampleHistory()
    replies = []

    def reply(chat_id, text):
        replies.append((chat_id, text))

    assert command_runner(message("/start"), store, reply, history)
    assert len(replies) == 2
    assert "aktif" in replies[0][1]
    assert "Geçmişten" in replies[1][1]
    assert history.reads == 1

    assert command_runner(message("/start"), store, reply, history)
    assert command_runner(message("/devam"), store, reply, history)
    assert len(replies) == 4
    assert history.reads == 1


def test_reactivation_does_not_repeat_history(command_runner):
    store = FakeSubscribers()
    history = SampleHistory()
    replies = []

    def reply(chat_id, text):
        replies.append(text)

    command_runner(message("/start"), store, reply, history)
    command_runner(message("/dur"), store, reply, history)
    command_runner(message("/start"), store, reply, history)
    assert history.reads == 1


def test_history_failure_does_not_cancel_subscription(command_runner):
    store = FakeSubscribers()

    class Unavailable:
        def initial_history_summary(self):
            raise RuntimeError("Firestore unavailable")

    replies = []
    assert command_runner(message("/start"), store, lambda _chat, value: replies.append(value), Unavailable())
    assert store.enabled == {101}
    assert len(replies) == 2
    assert "görüntülenemedi" in replies[1]
