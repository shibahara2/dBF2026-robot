# R2 を WebSocket で直接操作する 設計仕様 (2026-10-03)

## 背景・目的

R2（THEMIS）に飲み物を積み込ませる操作は、これまで次の構成を前提にしていた。

- dBF-robot（このリポジトリ）が、`docs/R2_Demo_Specification-v1.pdf` の HTTP API
  （`POST /v1/commands/load-drink`、`GET /v1/commands/load-drink/status`）を呼ぶ。
- その HTTP API は R2 側が提供する。

実際に R2 を動かしているのは、ロボットのベンダーが作った操作パネル **UI-DRP**
（`~/Linux/DRP`、Bun 製の単一実行ファイル。ソースは `~/Linux/DRP-src`）だった。
UI-DRP には仕様書の `POST /v1/commands/load-drink` がない。R2 とのやり取りは
ブラウザで開いた画面が直接 WebSocket で行い、オペレーターのボタン操作で進める作り
だった。そのため、dBF-robot から HTTP で始めても R2 は動かず、`/debug` の
「POST load-drink をスキップ」で回避していた。

本仕様では、UI-DRP の画面がしていた R2 の操作を dBF-robot（Flask）のサーバー側に
移す。R2 の操作と表示は dBF-robot の `/debug` にまとめ、UI-DRP は使わない。

### 前提（ユーザー確認済み）

- 仕様書（`R2_Demo_Specification-v1.pdf`）とこのリポジトリはユーザーが作ったもの。
  UI-DRP だけがロボットのベンダー製で、**ロボットのベンダーの仕様に合っているのは
  UI-DRP**。ロボットに送るもの（メッセージ、順番、待ち時間）と、ロボットから受け取る
  ものの解釈は UI-DRP をそのまま写す。
- ロボット本体のプロセス（AOS、gamepad-server）は変えない。
- 仕様書の状態モデル（`completed` / `loading` / `returning` / `failed`）は、
  dBF-robot の中だけで使う。

## 構成

```
spark-3a50 (10.17.2.171)                 spark-60c9 (展示PC)              R2 (THEMIS)
┌─────────────────────────┐        ┌──────────────────────┐        ┌────────────────────┐
│ Flask :5100             │  ws    │ 有線 10.17.4.171     │  ws    │ gamepad-server     │
│  ├ ステートマシン        │───────▶│  :9002 を DNAT       │───────▶│ 192.168.0.11:9002  │
│  ├ R2 制御 (R2Controller)│        │  Wi-Fi THEMIS_5G     │        │  /realtime /zed2i  │
│  └ /debug               │        │  (192.168.0.112)     │        └────────────────────┘
└─────────────────────────┘        │ 音声 (voice_ui)      │
                                   └──────────────────────┘
```

- **spark-3a50**：Flask の中に R2 との WebSocket 接続と R2 の操作を持つ。
  ステートマシンと `/debug` もここ。
- **spark-60c9**：THEMIS_5G に**ふつうのクライアントとして**つながる。有線側
  （10.17.4.171）の 9002 番に来た通信を、R2 の `192.168.0.11:9002` へ転送する
  （DNAT ＋ MASQUERADE）。通すのは spark-3a50 からの通信だけ。音声（voice_ui）も
  ここで動かす。UI-DRP は使わない。
- ロボット側の設定は何も変えない。R2 の AP が Main PC でもロボット内のルーターでも、
  同じ方法で動く。
- L3 の転送なので、ロボット内の LCM（`ttl=1`）と ROS2/DDS のマルチキャストは
  10.17.x に出ない。
- 9002 番は `/zed2i`（VLM 用の映像）も同じなので、`THEMIS_WS_URL` も同じ転送で届く。

### 経路について（議論からの修正）

議論では「spark-3a50 に `192.168.0.0/24 via 10.17.4.171` の経路を足す」とした。
しかし spark-3a50（10.17.2.171）と spark-60c9（10.17.4.171）は同じセグメントに
いない（10.17.4.1 を経由して届く）ので、spark-3a50 から 10.17.4.171 を次の
転送先にはできない。そこで経路を足す代わりに、**spark-60c9 で 9002 番を DNAT する**。
spark-3a50 からは `ws://10.17.4.171:9002/realtime` につなぐ。spark-3a50 の
経路設定は不要になる。

spark-60c9 で行う設定（sudo が必要。README に手順を書く）：

```
sudo sysctl -w net.ipv4.ip_forward=1
# 10.17.4.171:9002 に spark-3a50 から来た通信だけを R2 へ
sudo iptables -t nat -A PREROUTING -i <有線のインターフェース名（実機で確認）> -s 10.17.2.171 -p tcp --dport 9002 \
  -j DNAT --to-destination 192.168.0.11:9002
sudo iptables -t nat -A POSTROUTING -o wlP9s9 -d 192.168.0.11 -p tcp --dport 9002 -j MASQUERADE
sudo iptables -A FORWARD -s 10.17.2.171 -d 192.168.0.11 -p tcp --dport 9002 -j ACCEPT
sudo iptables -A FORWARD -s 192.168.0.11 -d 10.17.2.171 -m state --state ESTABLISHED,RELATED -j ACCEPT
```

ufw が有効なので、ufw の FORWARD ポリシーとの兼ね合いを実機で確認する。
永続化（再起動後も残す）の方法も README に書く。

### 運用上の注意

- `/realtime` には認証がなく、shutdown や関節の操作も受け付ける。転送で通す相手を
  spark-3a50 に絞る。
- ロボットの電源が切れると spark-60c9 の Wi-Fi が Robotbank に切り替わり、経路が
  消える。THEMIS_5G を優先して自動でつなぎ直すよう設定する。Flask 側は未接続を
  表示し、自動でつなぎ直す。
- status は dBF-robot の中にしかない（下記）。**R2 の動作中に Flask を再起動しない**。
  再起動すると status は `completed` に戻る。

## ロボットとのやり取り（UI-DRP をそのまま写す）

UI-DRP の画面（`dist/assets/index-*.js`）から読み取った内容。

### 接続

- `ws://<host>:9002/realtime`、`binaryType = arraybuffer`。接続のタイムアウトは
  5 秒（UI-DRP の `Dc=5e3`）。
- 受信：バイナリのフレームを MessagePack として読み解く。テキストのフレームは
  使わない（UI-DRP はバイナリだけをデコーダに渡している）。
- 送信：JSON 文字列。JavaScript の `JSON.stringify` と同じく、区切りに空白を
  入れない（Python では `json.dumps(obj, separators=(",", ":"))`）。

### 送るメッセージ

```
gamepad(button, combo) = {"type":"gamepad","data":{"button":<16要素>,"axis":[0,0,0,0,0,0],"combo":<5要素>}}
```

| 操作 | UI-DRP の関数 | 送るもの |
|---|---|---|
| ナビゲーションに入る | `enterNav` | `gamepad(button=[0]*16, combo=[0,0,1,0,0])` を1回。**dBF-robot は4回続けて送り、その後 `gamepad([0]*16, [0,0,0,0,0])` を1回送る**（下の注） |
| ナビゲーションを抜ける | `leaveNav` | `button[8]=button[9]=1`（他は0）、`combo=[1,0,0,0,0]` の gamepad を **4回**続けて送り、その後 `gamepad([0]*16, [0,0,0,0,0])` を1回 |
| 一連の動作を開始 | `playNavigation5(true)` | `enterNav` → **2秒待つ** → 接続が開いていれば `{"type":"play_navigation5","data":{"value":true}}` |
| 一連の動作を停止 | `playNavigation5(false)` | `leaveNav` → **2秒待つ** → 接続が開いていれば `{"type":"play_navigation5","data":{"value":false}}` |

`button` の並びは AOS の LCM `GamepadData` と同じと推定している
（`A,B,Y,X,LS,RS,LS2,RS2,BK,ST,LZ,RZ,U,D,L,R`。よって 8, 9 は BK と ST）。
`combo` は `STAND, WALK, NAVIGATION, MANIPULATION, (5番目)` と推定している。
`[0,0,1,0,0]` は NAVIGATION、`[1,0,0,0,0]` は STAND。ただし gamepad-server が JSON
をどう LCM に詰めているかは確認できていない。**意味の推定にかかわらず、UI-DRP と
同じ値をそのまま送る。**

**UI-DRP との違い（2026-10-05）**：2026-10-04 の実機では、UI-DRP どおり `enterNav` を
1回送っても、`play_navigation5` に `success:true` が返るだけでロボットが動かなかった
（UI-DRP でも同じ）。`leaveNav` は4回送って離す形で実機で効いたので、開始も同じ形にする
（`ENTER_NAV_REPEAT = 4`）。

`play_navigation5` は AOS v0.2.4 の gamepad-server には存在しない。ロボットでは
ベンダーがデモ用に足した新しい gamepad-server が動いていると推定している。
仕様書のシーケンスから、「A→B へ移動 → temi にボトルを載せる → B→A へ戻る」と
いう一連の動作だと推定している。

### 受け取るメッセージ

MessagePack を読み解いた結果の `type` で分ける。

| `type` | 中身 | 使い方 |
|---|---|---|
| `robot_aggregator` | `data.under_mode.data.data`（文字列 `<何か>_m<番号>`） | 進み具合。下の「`under_mode` の解釈」 |
| `play_navigation5_rp` | `data.success`（bool） | 開始・停止への返事 |

`robot_aggregator` には `walk_state`、`base_state`、`thread_state`、`battery_state`、
`bear_state` なども入っている（AOS v0.2.4 で確認）。今回は使わない。

### `under_mode` の解釈

- `_m` の後ろの番号を取り出す（UI-DRP の `split("_m")[1]`）。
- **前回の値から変わったときだけ**判断する。
  - `5` になり、status が `loading` → `returning`（UI-DRP のログ「placement completed」）
  - `1` になり、status が `returning` → `completed`（UI-DRP のログ「returned to A」）
- 値が空、または `under_mode` が含まれないメッセージは無視し、前回の値は
  空でない最後の値のままにする。
  - **UI-DRP との違い**：UI-DRP は aggregator を丸ごと置き換えるので、
    `under_mode` が一度空になってから同じ値に戻ると、もう一度「変わった」と判断する。
    今回はこれを変化とみなさない。値が届き続けるふだんの動きでは、結果は同じ。
- 意味がわかっているのは `_m5` と `_m1` だけ。他の値（`_m2`〜`_m4` があるか、
  待機中の値）は不明。**値が変わるたびに生の値をログに残し、`/debug` にも出す。**

## R2 の status（dBF-robot が持つ）

R2 は `loading` などの status を持っていない。R2 にあるのは `under_mode` と
`play_navigation5_rp` だけで、status は dBF-robot が自分の送った命令と
`under_mode` の変化から組み立てる（UI-DRP もブラウザの中で同じ4つを持っていた）。
status は、`under_mode` の変化をどう解釈するかと、ステートマシンが先へ進むかの
判断に必要。

| status | 意味 |
|---|---|
| `completed` | A で待機中。次の動作を始めてよい（初期値） |
| `loading` | 動作中で、まだ置き終わっていない |
| `returning` | 置き終わって、A へ戻っている途中 |
| `failed` | 続けられない。人が確認して直す必要がある |

`failed` には理由を付ける：`start_no_reply`（開始の返事が15秒来ない）、
`start_rejected`（返事が `success:false`）、`start_disconnected`（返事待ちの
あいだに切断）、`disconnected`（`loading`/`returning` 中に切断）、`stopped`（STOP）、
`manual`（手動で `failed` にした）。

request_id は作らない（照合する相手がいない）。

### 遷移

```
                     start() 成功（_rp success:true）
     completed ─────────────────────────────▶ loading
        ▲  ▲                                      │ under_mode → _m5、または手動
        │  │ under_mode → _m1、または手動          ▼
        │  └──────────────────────────────── returning
        │
        │ 「R2 を初期状態に戻す」（failed のときだけ）
        │
      failed ◀── start() 失敗（返事なし15秒 / success:false / 返事待ちに切断）
             ◀── loading / returning 中の切断
             ◀── STOP（いつでも）
             ◀── 手動で failed（loading / returning のとき）
```

開始の返事を待っているあいだ（`enterNav` → 2秒 → `play_navigation5` → 返事まで）は、
status は `completed` のままにする。「開始中」はステートマシンの段階（step）で表す。

## 部品

### `app/clients/r2_link.py`：`R2Link`（WebSocket の接続）

- `websocket-client` で接続し、受信用のスレッドで読み続ける
  （`themis_video/client.py` と同じ書き方。`websocket_factory` を差し替えてテストする）。
- **自動接続**：`start()` で接続を始め、切れたら `reconnect_delay` 後につなぎ直す。
- **手動切断**：`disconnect()` で切り、自動でつなぎ直さない。`connect()` で再開する。
- 接続状態：`connecting` / `connected` / `disconnected`（つなぎ直し待ち）/
  `stopped`（手動で切断）。最後に状態が変わった時刻も持つ。
- `send_json(obj)`：空白なしの JSON で送る。未接続なら `False` を返す。
- 受信したバイナリを `msgpack` で読み解き、`on_message(dict)` を呼ぶ。読み解けない
  ものはログに残して捨てる。
- 接続状態が変わったら `on_state_change(state)` を呼ぶ。

### `app/clients/r2_controller.py`：`R2Controller`（R2 の操作と status）

`R2Link` を使って、UI-DRP の手順と status を持つ。テストのため `sleep` と `now` と
`monotonic` を差し替えられるようにする。

- `snapshot()`：接続状態、status、失敗の理由、各時刻、`under_mode`（生の値と時刻）、
  最後の `_rp`（中身と時刻、送ってから届くまでの秒数）を返す。
- `start_load_drink()`：返事が来るまで待つ（同期）。
  - status が `completed` で接続中のときだけ開始する。そうでなければ開始せずに
    失敗を返す。
  - `enterNav` → 2秒 → `play_navigation5(true)` → `_rp` を最大
    `start_reply_timeout`（既定15秒）待つ。
  - `success:true` → `loading` にして成功を返す。
  - `success:false` / 時間切れ / 返事待ちのあいだに切断 → `failed`（理由付き）にして
    失敗を返す。
  - 時間切れの後に遅れて届いた `_rp` は、status を変えずにログに残す。
- `resend_start()`：開始の再送。status が `failed` で理由が `start_no_reply` /
  `start_rejected` / `start_disconnected` のどれかで、`under_mode` の番号が `1` の
  ときだけ。内部では status を `completed` に戻してから `start_load_drink()` と同じ
  手順を行う。
- `stop()`：接続中のとき、`playNavigation5(false)` の手順を送り、`failed`（`stopped`）
  にする。停止への `_rp` はログに残すだけ（UI-DRP も待たない）。
- `mark(status)`：手動での状態変更。
  - `returning`：`loading` のときだけ
  - `completed`：`returning` のときだけ
  - `failed`：`loading` か `returning` のとき（理由 `manual`）
- `reset()`：「R2 を初期状態に戻す」。`failed` のときだけ `completed` に戻す。
  ロボットには何も送らない。
- `connect()` / `disconnect()`：`R2Link` へ渡す。`loading` / `returning` 中に切断
  （手動、自動どちらでも）したら `failed`（`disconnected`）。
- 状態が変わるたびに、登録されたリスナーを呼ぶ（ステートマシンと SSE 用）。
- 条件に合わない操作は、理由の文字列を付けて失敗を返す（`/debug` が 409 で返す）。
- 内部の状態は1つのロックで守る。`start_load_drink()` の返事待ちは
  `threading.Condition` で待つ。

### ステートマシン（`app/state_machine.py`）の R2 部分

AI 管制PF の部分はポーリングのまま変えない。R2 の部分だけ、`R2Controller` の
状態変化を待つ形（イベント駆動）にする。

ステートマシンの状態は phase と step の組み合わせ。phase は今のまま
（`waiting` / `active` / `error`）。`error` のときの step は、エラーが起きた
段階のまま残る。step は次のとおり（3〜5 は名前を変える。ユーザー確認済み）。

| 順番 | step | phase | 何をしているか |
|---|---|---|---|
| 1 | `awaiting_checkin` | waiting | チェックイン待ち |
| 2 | `polling_pf_ready` | waiting | AI 管制PF の `Ready` を待つ（ポーリング） |
| 3 | `waiting_r2_ready`（旧 `polling_r2_ready`） | waiting | R2 が接続中かつ `completed` になるのを待つ |
| 4 | `starting_r2`（旧 `sending_load_drink`） | waiting | NAVIGATION → `play_navigation5(true)` → 返事 |
| 5 | `waiting_r2_placed`（旧 `polling_r2_active`） | active | `returning`（`under_mode` の `_m5`）を待つ |
| 6 | `notifying_pf_placed` | active | AI 管制PF に `drink/placed` を送る。終わったら 1 に戻る |

| step（新） | 旧 | 何をするか | 次へ進む条件 / エラー |
|---|---|---|---|
| `waiting_r2_ready` | `polling_r2_ready` | 接続中かつ `completed` になるまで待つ。未接続のあいだも待ち続ける | 条件を満たしたら次へ。`failed` ならエラー |
| `starting_r2` | `sending_load_drink` | `start_load_drink()` を呼ぶ | 成功なら次へ。失敗ならエラー（理由を表示） |
| `waiting_r2_placed` | `polling_r2_active` | `returning` になるまで待つ | `returning` なら次へ（`drink/placed`）。`failed` ならエラー |

- 待つ処理は `R2Controller` の状態変化の通知で起きる。
- **再送からの再開**：`starting_r2` でエラーになった後、`/debug` の再送が成功したら、
  エラーを解除して `waiting_r2_placed` から続ける（今の「スキップ」で再開する仕組み
  `SKIP_RESUME` と同じ形）。
- **なくすもの**：request_id とその一致チェック、`timeout` / `validation_error` の
  結果、同じ request_id での再送、`try_skip_load_drink` と
  `/api/debug/skip-load-drink`。
- スナップショットから `request_id`、`r2_status`、`r2_status_at` を外す。R2 の状態は
  別のイベント `r2_state` で流す。
- `docs/state_machine.pdf` の WAITING 2〜4 と ACTIVE 1 の R2 部分は、本仕様の流れに
  置き換わる。

### `/debug`

画面は実装してから見て調整する（ユーザー判断）。最初の実装は次のとおり。

- **接続先**：R2 の行を `R2_WS_URL` にする。
- **R2 パネル**（今の「手動操作」を置き換え）
  - 接続状態（接続中 / 接続試行中 / 未接続 / 切断中（手動））を色付きで先頭に出し、
    いつからかも出す。[切断] / [接続] ボタン。未接続のときはパネルの枠を赤くする。
  - status と変わった時刻、`failed` の理由。
  - `under_mode` の生の値と変わった時刻。
  - 最後の開始の返事（生の中身、時刻、送ってから届くまでの秒数）。
  - ボタン：[STOP] [開始を再送] [returning にする] [completed にする]
    [failed にする] [R2 を初期状態に戻す]。押せないときは灰色にし、理由を近くに出す。
  - 確認が要るボタン：STOP、returning にする（「AI管制PFに drink/placed を送り、
    temi が出発します」）、R2 を初期状態に戻す（「R2 が A にいることを確認しましたか」）。
    画面の中に「実行する / やめる」を出す（ブラウザのダイアログは使わない）。
- **ステートマシンのリセット**ボタンをエラー表示の近くに足す（今の `/api/reset`）。
- 「GETステータス最新取得」から R2 の行を消す（PF の行は残す）。
- **シーケンス図**の R2 の矢印を描き直す。
  - `waiting_r2_ready`：接続中 かつ status = completed
  - `starting_r2`：gamepad NAVIGATION ＋ `play_navigation5(true)` → `play_navigation5_rp` success
  - `waiting_r2_placed`：`robot_aggregator` の `under_mode` が `_m5` → returning
- キオスク画面（`app.js`）の step と文言の対応表は、名前だけ新しい step に合わせる。
  表示する文言は変えない。

### `/debug` 用の API（`app/routes/r2_debug.py`）

| メソッド | パス | 内容 |
|---|---|---|
| GET | `/api/debug/r2` | `R2Controller.snapshot()` |
| POST | `/api/debug/r2/connect` | 接続 |
| POST | `/api/debug/r2/disconnect` | 切断 |
| POST | `/api/debug/r2/stop` | STOP |
| POST | `/api/debug/r2/resend` | 開始の再送（成功したらステートマシンを再開） |
| POST | `/api/debug/r2/mark` | `{"status": "returning" \| "completed" \| "failed"}` |
| POST | `/api/debug/r2/reset` | R2 を初期状態に戻す |

条件に合わないときは 409 と `{"message": <理由>}` を返す。

R2 の状態が変わるたびに、SSE（`/api/events`）で種類付きのイベント
`{"type": "r2_state", ...snapshot}` を流す。キオスク画面と voice_ui は種類付きの
イベントを無視する（`10fd042`、`eb9a475`）。

### 設定（`app/config.py`、`.env.example`）

| 変数 | 既定 | 内容 |
|---|---|---|
| `R2_WS_URL` | `ws://127.0.0.1:9002/realtime` | R2 の gamepad-server |
| `R2_START_REPLY_TIMEOUT_SECONDS` | `15` | 開始の返事を待つ秒数 |
| `R2_WS_RECONNECT_DELAY_SECONDS` | `1` | つなぎ直すまでの秒数 |
| `R2_WS_CONNECT_TIMEOUT_SECONDS` | `5` | 接続のタイムアウト |

`R2_BASE_URL`、`DRINK_TYPE`、`TARGET_ROBOT_ID` は消す。

### Flask のリローダーへの対応

`run.py` は `debug=True` で動いていて、リローダーの親プロセスでも `create_app()` が
呼ばれる。そのままだと親と子の両方が R2 に WebSocket でつなぐ。リローダーの親
（`debug=True` で `WERKZEUG_RUN_MAIN` が `"true"` でないとき）では `R2Link` を
起動しない。

### 消すもの

- `app/clients/r2_client.py`、`mocks/r2_mock.py`、`tests/test_r2_client.py`、
  `tests/test_r2_mock.py`
- `/api/debug/skip-load-drink` と、`/debug` のスキップボタン
- 過去の spec / plan（`docs/superpowers/*/2026-09-13-*` など）は記録として残す。

### モック（ローカル開発用）

- `mocks/r2_realtime_mock.py`：`/realtime` をまねる。
  - gamepad と `play_navigation5` を受け、送られてきた JSON を記録する。
  - `play_navigation5(true)` に `{"type":"play_navigation5_rp","data":{"success":true}}`
    を MessagePack で返す。その後、`under_mode` を `mock_m1` → `mock_m3` →
    `mock_m5` → `mock_m3` → `mock_m1` と、`robot_aggregator` で一定間隔ごとに送る。
  - 環境変数：`R2_MOCK_STEP_SECONDS`（各段階の秒数、既定3）、
    `R2_MOCK_START_REPLY`（`success` / `fail` / `none`。既定 `success`）。
  - `play_navigation5(false)` には `success:true` を返し、`under_mode` の進行を止める。
- `mocks/themis_video_mock.py` のサーバーをパスで分け、`/realtime` は上のモック、
  それ以外は今の映像に応える。実機と同じく1つのポート（9002）で両方に応える。
- `run_mocks.py`：AI 管制PF のモック（:5002）と、このサーバー（:9002）を起動する。
  映像のモックを別に起動していた手順（README）は、`run_mocks.py` に一本化する。

### 依存

- `msgpack` を `requirements-core.txt` に足す。

## テスト

- **`R2Link`**（`websocket_factory` を偽物にする）：自動接続、切断からのつなぎ直し、
  手動切断ではつなぎ直さないこと、MessagePack の読み解き、読み解けないフレームを
  捨てること、空白なしの JSON で送ること、状態変化の通知。
- **`R2Controller`**（偽の `R2Link`、偽の `sleep`/時計）
  - 開始と STOP で送るメッセージが、**UI-DRP と1文字単位で同じ**であること
    （期待値は UI-DRP の `JSON.stringify` の出力を写した文字列で書く）。
    送る順番と2秒の待ちも確かめる。
  - 返事が `success:true` / `success:false` / 来ない / 返事待ちに切断、の各場合。
  - `under_mode` の変化：`loading` 中の `_m5`、`returning` 中の `_m1`、それ以外の
    状態での `_m5`/`_m1` を無視すること、同じ値が続くときは無視すること、空の値。
  - 手動の操作それぞれの、押せる条件と押せない条件。
  - 再送の条件（理由と `_m1`）。
  - `loading`/`returning` 中の切断で `failed` になること。
  - リスナーが呼ばれること。
- **ステートマシン**（偽の R2 制御）：R2 部分を新しい流れで書き直す。待機の確認
  （未接続でも待つ、`failed` でエラー）、開始の失敗、再送からの再開、
  `returning` で `drink/placed` に進むこと、`waiting_r2_placed` 中の `failed`。
  AI 管制PF 部分のテストは変えない。
- **`/debug` の API**：各操作の 200 / 409、`GET /api/debug/r2`、SSE に `r2_state` が
  流れること。
- **結合テスト**（`tests/test_integration_mocks.py` の R2 部分を置き換え）：本物の
  `R2Link` と `R2Controller` を、本物の WebSocket モックに実際のソケットでつなぎ、
  開始 → `loading` → `returning` → `completed` を一周させる。
- **モック**：`/realtime` と映像のパスの振り分け、各環境変数での動き。
- **手動確認**（`docs/superpowers/plans/manual-e2e-check.md` を更新）：モックで一周、
  開始の返事なし → 再送、STOP → 初期状態に戻す → リセット。

### 実機で確かめること

- spark-3a50 から `ws://10.17.4.171:9002/realtime` につながるか（DNAT と ufw）。
- 開始の返事が届くまでの秒数（15秒が妥当か）。
- `under_mode` の値の一覧（待機中、移動中、`_m5`、`_m1` 以外の値があるか）。
- STOP の後のロボットの様子と、A に戻す方法（ベンダーに確認）。
- `/realtime` に UI-DRP と dBF-robot が同時につないだときの動き（同時につながない
  運用にするが、念のため）。
