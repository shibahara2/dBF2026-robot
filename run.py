import os

from app import create_app

# run() below uses debug=True, so the reloader's parent process imports this
# module too. Only the child that serves requests may connect to R2; two
# connections from one host would both act on R2's /realtime.
app = create_app(start_r2=os.environ.get("WERKZEUG_RUN_MAIN") == "true")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5100, threaded=True, debug=True)
