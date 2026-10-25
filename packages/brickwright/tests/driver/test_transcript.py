"""Tests for the conversation transcript: the live message list and its log."""

import json

import pytest

from brickwright.driver.transcript import Transcript


class TestTranscript:
    def test_messages_holds_appended_messages_in_order(self, tmp_path):
        transcript = Transcript(tmp_path / "messages.jsonl")
        transcript.append({"role": "system", "content": "sys"})
        transcript.append({"role": "user", "content": "hi"})
        assert transcript.messages == [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]

    def test_append_writes_one_json_line_per_message(self, tmp_path):
        path = tmp_path / "messages.jsonl"
        transcript = Transcript(path)
        transcript.append({"role": "system", "content": "sys"})
        transcript.append({"role": "user", "content": "hi"})
        transcript.close()

        lines = path.read_text().splitlines()
        assert [json.loads(line) for line in lines] == [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]

    def test_is_a_context_manager_that_persists_its_messages(self, tmp_path):
        path = tmp_path / "messages.jsonl"
        with Transcript(path) as transcript:
            transcript.append({"role": "system", "content": "sys"})
        assert [json.loads(line) for line in path.read_text().splitlines()] == [
            {"role": "system", "content": "sys"}
        ]

    def test_closes_the_log_on_context_exit(self, tmp_path):
        with Transcript(tmp_path / "messages.jsonl") as transcript:
            transcript.append({"role": "system", "content": "sys"})
        # Writing to the closed file is an error -- the handle was released.
        with pytest.raises(ValueError):
            transcript.append({"role": "user", "content": "late"})

    def test_each_message_is_flushed_before_close(self, tmp_path):
        # Durability: a message is on disk the instant it is appended, so an
        # interrupt before close() still leaves everything written so far.
        path = tmp_path / "messages.jsonl"
        transcript = Transcript(path)
        transcript.append({"role": "system", "content": "sys"})
        lines = path.read_text().splitlines()
        assert [json.loads(line) for line in lines] == [
            {"role": "system", "content": "sys"}
        ]

    def test_close_writes_an_indented_pretty_json_copy(self, tmp_path):
        path = tmp_path / "messages.jsonl"
        with Transcript(path) as transcript:
            transcript.append({"role": "system", "content": "sys"})
            transcript.append({"role": "user", "content": "hi"})

        pretty = tmp_path / "messages.pretty.json"
        assert pretty.is_file()
        text = pretty.read_text()
        # A single indented JSON array of the same messages, in order.
        assert json.loads(text) == [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hi"},
        ]
        assert "\n  " in text  # actually indented, not a single line

    def test_pretty_copy_keeps_full_history_across_a_reset(self, tmp_path):
        path = tmp_path / "messages.jsonl"
        with Transcript(path) as transcript:
            transcript.append({"role": "system", "content": "sys-1"})
            transcript.append({"role": "user", "content": "round 1"})
            transcript.reset([{"role": "system", "content": "sys-2"}])
            transcript.append({"role": "user", "content": "round 2"})

        # The live conversation only holds the latest round...
        assert transcript.messages == [
            {"role": "system", "content": "sys-2"},
            {"role": "user", "content": "round 2"},
        ]
        # ...but the pretty copy preserves the whole multi-round history, including
        # the reset marker -- matching the .jsonl log.
        pretty = json.loads((tmp_path / "messages.pretty.json").read_text())
        assert pretty == [
            {"role": "system", "content": "sys-1"},
            {"role": "user", "content": "round 1"},
            {"role": "_meta", "event": "conversation_reset"},
            {"role": "system", "content": "sys-2"},
            {"role": "user", "content": "round 2"},
        ]

    def test_pretty_copy_also_elides_base64_images(self, tmp_path):
        path = tmp_path / "messages.jsonl"
        with Transcript(path) as transcript:
            transcript.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "build this"},
                        {
                            "type": "image_url",
                            "image_url": {"url": "data:image/png;base64,QUJDREVG"},
                        },
                    ],
                }
            )
        pretty_text = (tmp_path / "messages.pretty.json").read_text()
        assert "QUJDREVG" not in pretty_text
        assert "<image: image/png elided>" in pretty_text

    def test_base64_image_is_elided_in_the_log_only(self, tmp_path):
        path = tmp_path / "messages.jsonl"
        transcript = Transcript(path)
        message = {
            "role": "user",
            "content": [
                {"type": "text", "text": "build this"},
                {
                    "type": "image_url",
                    "image_url": {"url": "data:image/png;base64,QUJDREVG"},
                },
            ],
        }
        transcript.append(message)
        transcript.close()

        # The live conversation keeps the full data URL (it is sent to the model).
        assert transcript.messages[0]["content"][1]["image_url"]["url"].startswith(
            "data:image/png;base64,QUJDREVG"
        )
        # The logged copy elides the base64 payload but keeps the text.
        logged = json.loads(path.read_text())
        assert logged["content"][0] == {"type": "text", "text": "build this"}
        assert "QUJDREVG" not in path.read_text()
        assert logged["content"][1]["image_url"]["url"] == "<image: image/png elided>"
