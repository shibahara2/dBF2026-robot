import json

import responses

from tools.vlm_eval import FIXTURE_DIR, collect_cases, main


ENDPOINT = "http://vlm.example/analyze"


def _make_dataset(tmp_path):
    for label, names in {"yes": ["a.jpg"], "no": ["b.png", "c.jpg"]}.items():
        (tmp_path / label).mkdir()
        for name in names:
            (tmp_path / label / name).write_bytes(b"\xff\xd8\xffimg")
    (tmp_path / "no" / "notes.txt").write_text("ignored")
    return tmp_path


def _reply(*decisions):
    answers = iter(decisions)

    def callback(_request):
        answer = next(answers)
        return 200, {}, json.dumps(
            {"speaking_to_themis": answer == "yes", "answer": answer, "latency_ms": 5}
        )

    return callback


def test_collect_cases_uses_directory_as_label(tmp_path):
    cases = collect_cases(_make_dataset(tmp_path))

    assert [(c.expected, c.path.name) for c in cases] == [
        ("no", "b.png"),
        ("no", "c.jpg"),
        ("yes", "a.jpg"),
    ]


def test_repository_fixtures_have_both_labels():
    labels = {case.expected for case in collect_cases(FIXTURE_DIR)}

    assert labels == {"yes", "no"}


@responses.activate
def test_all_correct_exits_zero(tmp_path, capsys):
    responses.add_callback(responses.POST, ENDPOINT, callback=_reply("no", "no", "yes"))

    code = main(["--endpoint", ENDPOINT, "--dataset", str(_make_dataset(tmp_path))])

    out = capsys.readouterr().out
    assert code == 0
    assert "accuracy 3/3 (100.0%)" in out


@responses.activate
def test_mismatch_is_reported_and_fails_min_accuracy(tmp_path, capsys):
    responses.add_callback(responses.POST, ENDPOINT, callback=_reply("yes", "no", "yes"))

    code = main(
        [
            "--endpoint", ENDPOINT,
            "--dataset", str(_make_dataset(tmp_path)),
            "--min-accuracy", "1.0",
        ]
    )

    out = capsys.readouterr().out
    assert code == 1
    assert "NG" in out and "b.png" in out
    assert "accuracy 2/3 (66.7%)" in out
    assert "false_positive=1" in out


@responses.activate
def test_request_error_counts_as_failure(tmp_path, capsys):
    responses.add(responses.POST, ENDPOINT, status=502)

    code = main(["--endpoint", ENDPOINT, "--dataset", str(_make_dataset(tmp_path))])

    out = capsys.readouterr().out
    assert code == 1
    assert "errors=3" in out
