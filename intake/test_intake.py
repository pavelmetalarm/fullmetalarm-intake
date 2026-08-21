import tempfile
import unittest
from unittest import mock
from pathlib import Path

from intake.poll import make_title, parse_message, run


class FakeTelegram:
    def __init__(self, updates):
        self.updates, self.events = updates, []

    def get_updates(self, offset):
        self.events.append(("get", offset))
        return self.updates

    def send_message(self, chat_id, text):
        self.events.append(("reply", text))


class FakeProject:
    def __init__(self, fail=False, events=None):
        self.fail, self.events = fail, events if events is not None else []

    def resolve_project(self):
        return "project"

    def resolve_fields(self, project_id):
        return {}

    def add_draft_issue(self, project_id, title, body):
        self.events.append(("create", title))
        if self.fail:
            raise RuntimeError("creation failed")
        return "item"

    def set_single_select(self, *args):
        self.events.append(("set",))


def update(update_id, sender=7, text="hello"):
    return {"update_id": update_id, "message": {"from": {"id": sender}, "chat": {"id": 42}, "text": text}}


class IntakeTests(unittest.TestCase):
    def test_command_parsing(self):
        self.assertEqual(parse_message("/bug broken"), ("bug", "broken"))
        self.assertEqual(parse_message("/idea future"), ("idea", "future"))
        self.assertEqual(parse_message("/note memo"), ("note", "memo"))
        self.assertEqual(parse_message("/bug@my_bot broken"), ("bug", "broken"))
        self.assertEqual(parse_message("ordinary text"), ("note", "ordinary text"))
        self.assertEqual(parse_message("  /idea indented"), ("idea", "indented"))

    def test_non_owner_creates_no_item(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "offset.json"
            project = FakeProject()
            project.add_draft_issue = mock.Mock(wraps=project.add_draft_issue)
            run(FakeTelegram([update(1, sender=99)]), project, 7, path)
            project.add_draft_issue.assert_not_called()

    def test_processed_update_creates_no_second_item(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "offset.json"
            path.write_text('{"offset": 1, "processed_update_ids": [1]}')
            project = FakeProject()
            run(FakeTelegram([update(1)]), project, 7, path)
            self.assertEqual(project.events, [])

    def test_creation_failure_does_not_advance_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "offset.json"
            path.write_text('{"offset": 0, "processed_update_ids": []}')
            with self.assertRaises(RuntimeError):
                run(FakeTelegram([update(5)]), FakeProject(fail=True), 7, path)
            self.assertEqual(path.read_text(), '{"offset":0,"processed_update_ids":[]}\n')

    def test_reply_follows_successful_item_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            events = []
            telegram = FakeTelegram([update(3)])
            project = FakeProject(events=events)
            run(telegram, project, 7, Path(directory) / "offset.json")
            self.assertEqual(events[0][0], "create")
            self.assertEqual(telegram.events[-1][0], "reply")

    def test_title_truncates_at_80_characters(self):
        title = make_title("x" * 81)
        self.assertEqual(len(title), 80)
        self.assertTrue(title.endswith("…"))


if __name__ == "__main__":
    unittest.main()
