import asyncio
import threading

from mocks.pf_mock import create_pf_mock_app
from mocks.r2_realtime_mock import R2RealtimeMock
from mocks.themis_video_mock import serve_mock


def main():
    pf_app = create_pf_mock_app()

    pf_thread = threading.Thread(
        target=lambda: pf_app.run(host="0.0.0.0", port=5002, threaded=True),
        daemon=True,
    )
    # R2 (/realtime) and Themis video (/zed2i) share :9002, like the real robot.
    themis_thread = threading.Thread(
        target=lambda: asyncio.run(
            serve_mock("127.0.0.1", 9002, realtime=R2RealtimeMock.from_env())
        ),
        daemon=True,
    )
    pf_thread.start()
    themis_thread.start()
    pf_thread.join()
    themis_thread.join()


if __name__ == "__main__":
    main()
