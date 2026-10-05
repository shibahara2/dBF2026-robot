# 手動E2E確認手順

前提: `pip install -r requirements.txt` 済み。

1. ターミナル1: `R2_MOCK_STEP_SECONDS=3 python run_mocks.py`（PFモックが:5002、Themis WebSocketモック（R2 /realtime と映像）が:9002で起動）
2. ターミナル2: `python run.py`（本体が:5100で起動）
3. ターミナル3で以下を順に実行し、状態がwaiting→active→waitingと遷移することを確認する:
   - `curl -N http://localhost:5100/api/events &`（SSEの生ログが流れ始める）
   - `curl -X POST http://localhost:5100/api/checkin -H "Content-Type: application/json" -d '{"reservation_id":"RSV-0001"}'`
   - SSEログに `phase: "waiting"` → `phase: "active"` → 最終的に `phase: "waiting", step: "awaiting_checkin"` が流れることを確認する
4. 異常系確認: PFモックを異常応答（`accepted: false`）に切り替える。
   - ターミナル1で `Ctrl+C` を押し、`run_mocks.py`（PFモック:5002を含む）を停止する。
   - ターミナル1で改めて次を実行し、PFモックだけを異常応答で再起動する（Themis WebSocketモックも同じプロセスで一緒に起動し直す）:
     `PF_MOCK_ACCEPTED=false R2_MOCK_STEP_SECONDS=3 python run_mocks.py`
   - ターミナル3から手順3の `curl -X POST .../api/checkin` を再度実行し、`phase: "error"` になることを確認する。
5. `curl -X POST http://localhost:5100/api/reset` でERRORからWAITINGへ戻ることを確認する
6. R2 の異常系（ブラウザで `http://localhost:5100/debug` を開いておく）:
   - `R2_MOCK_START_REPLY=none python run_mocks.py` で起動し直してチェックインする。
     15秒後に `phase: "error"`、`step: "starting_r2"` になり、R2 パネルの failed の理由が
     `start_no_reply` になることを確認する。`under_mode` が `mock_m1` のまま
     「開始を再送」が押せることを確認する（モックは返事をしないので、再送もまた
     `start_no_reply` になる）。
   - `python run_mocks.py`（既定）で起動し直し、R2 パネルの「R2 を初期状態に戻す」→
     「ステートマシンをリセット」で戻す。チェックインし、`waiting_r2_placed` の間に
     「STOP」→「実行する」を押す。`phase: "error"`、failed の理由 `stopped` になることを
     確認し、「R2 を初期状態に戻す」→「ステートマシンをリセット」で戻ることを確認する。
   - R2 パネルの「切断」で「切断中（手動）」になり、自動でつなぎ直さないこと、
     「接続」で戻ることを確認する。

## 会場UI（ブラウザ）確認手順

前提: 手順1・2（モックと本体の起動）は上記と同じ。

1. ブラウザで `http://localhost:5100/` を開き、チェックインフォームが表示されることを確認する。
2. 名前を入力してチェックインすると、フォームが隠れて進行状況メッセージ（PF確認中→R2確認中→ドリンクセット中→お届け中→完了通知中）が順に表示され、最終的にフォームに戻ることを確認する。
3. 別のブラウザ（またはシークレットウィンドウ）で同時に `http://localhost:5100/` を開き、1人目が進行中の間は「他の方が対応中：〈ステップ〉」と表示され、フォームが使えないことを確認する。
4. `PF_MOCK_ACCEPTED=false` でモックを再起動し、チェックインしてエラー画面（`error_message`とリセットボタン）が表示されることを確認する。リセットボタンを押すとフォーム表示に戻ることを確認する。

## 音声IF（マイク・スピーカー）確認手順

前提: 手順1・2（モックと本体の起動）は上記と同じ。加えて以下が必要:

- VOICEVOXエンジンをホスト上で起動しておく。
- マイク・スピーカーが接続された端末で実行する。

1. ターミナル4: `python -m voice_ui.main`
   - 起動時にVOICEVOXへのプローブが成功し、openai-whisperモデル
     （既定`large-v3`、GPU/fp16）のロードが完了するまで待つ（初回はモデル
     ダウンロードが走るため数分かかることがある）。
2. 会場UI（ブラウザで`http://localhost:5100/`）が開始画面を表示している
   状態で、マイクに向かって「チェックインお願いします」のように話す。
   - ブラウザが検索画面に切り替わることを確認する。
   - スピーカーから「画面にお名前、予約番号、または電話番号を入力して
     ください」と読み上げられることを確認する。
   - 画面で予約を検索・選択・確定する。進行状況は読み上げられない。
3. 雑音対策の確認: 開始画面の表示中に、周囲の会話・BGMなど「チェックイン」
   を含まない音を意図的に聞かせ、誤って開始しない（検索画面に切り替わらない）
   ことを確認する。
   - 誤発火した場合は`voice_ui/main.py`のログ(`checkin pipeline outcome:
     rejected_low_confidence` 等)を見て、`STT_NO_SPEECH_PROB_MAX` /
     `STT_AVG_LOGPROB_MIN` / `VAD_TRAILING_SILENCE_MS`
     (`voice_ui/config.py`が読む環境変数)を調整する。
4. `PF_MOCK_FORCE_FAILURE=500`でモックを再起動しチェックインすると、
   スピーカーから`error_message`相当のエラー文言が読み上げられることを
   確認する。
