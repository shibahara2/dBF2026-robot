import threading

from mocks.pf_mock import create_pf_mock_app
from mocks.r2_mock import create_r2_mock_app


def main():
    r2_app = create_r2_mock_app()
    pf_app = create_pf_mock_app()

    r2_thread = threading.Thread(
        target=lambda: r2_app.run(host="0.0.0.0", port=5001, threaded=True),
        daemon=True,
    )
    pf_thread = threading.Thread(
        target=lambda: pf_app.run(host="0.0.0.0", port=5002, threaded=True),
        daemon=True,
    )
    r2_thread.start()
    pf_thread.start()
    r2_thread.join()
    pf_thread.join()


if __name__ == "__main__":
    main()
