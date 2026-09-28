from tools.check_themis_video import probe


class FakeClient:
    def __init__(self, on_frame):
        self.on_frame = on_frame
        self.stopped = False

    def start(self):
        self.on_frame(b"first")
        self.on_frame(b"second-frame")

    def stop(self):
        self.stopped = True


def test_probe_reports_frame_sizes_and_intervals():
    output = []

    samples = probe(
        "ws://themis:9002/zed2i",
        duration_seconds=0,
        client_factory=lambda url, on_frame: FakeClient(on_frame),
        output=output.append,
    )

    assert [sample.size for sample in samples] == [5, 12]
    assert output[0].startswith("frame=1 size=5")
    assert output[1].startswith("frame=2 size=12")


def test_probe_can_save_first_raw_frame_for_decoder_analysis(tmp_path):
    path = tmp_path / "themis-frame.bin"

    probe(
        "ws://themis:9002/zed2i",
        duration_seconds=0,
        client_factory=lambda url, on_frame: FakeClient(on_frame),
        output=lambda message: None,
        save_first_frame=path,
    )

    assert path.read_bytes() == b"first"
