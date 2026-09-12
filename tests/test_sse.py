from app.sse import EventBroadcaster


def test_subscriber_receives_published_snapshot():
    broadcaster = EventBroadcaster()
    q = broadcaster.subscribe()

    broadcaster.publish({"phase": "waiting"})

    assert q.get(timeout=1) == {"phase": "waiting"}


def test_multiple_subscribers_each_receive_the_snapshot():
    broadcaster = EventBroadcaster()
    q1 = broadcaster.subscribe()
    q2 = broadcaster.subscribe()

    broadcaster.publish({"phase": "active"})

    assert q1.get(timeout=1) == {"phase": "active"}
    assert q2.get(timeout=1) == {"phase": "active"}


def test_unsubscribed_queue_does_not_receive_future_snapshots():
    broadcaster = EventBroadcaster()
    q = broadcaster.subscribe()
    broadcaster.unsubscribe(q)

    broadcaster.publish({"phase": "error"})

    assert q.empty()
