import responses

from tools.vlm_client import main


@responses.activate
def test_cli_prints_decision_per_image(tmp_path, capsys):
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"\xff\xd8\xffjpeg")
    responses.add(
        responses.POST,
        "http://vlm.example/analyze",
        json={"speaking_to_themis": True, "answer": "yes", "latency_ms": 12},
    )

    exit_code = main(["--endpoint", "http://vlm.example/analyze", str(image)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "frame.jpg" in out and "yes" in out


@responses.activate
def test_cli_health_returns_nonzero_when_unhealthy(capsys):
    responses.add(responses.GET, "http://vlm.example/health", status=503)

    assert main(["--endpoint", "http://vlm.example/analyze", "--health"]) == 1


@responses.activate
def test_cli_reports_request_failure(tmp_path, capsys):
    image = tmp_path / "frame.png"
    image.write_bytes(b"png")
    responses.add(responses.POST, "http://vlm.example/analyze", status=422)

    assert main(["--endpoint", "http://vlm.example/analyze", str(image)]) == 1
    assert "error" in capsys.readouterr().out
