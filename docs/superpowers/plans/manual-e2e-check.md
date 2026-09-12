# 手動E2E確認手順

前提: `pip install -r requirements.txt` 済み。

1. ターミナル1: `R2_MOCK_LOADING_SECONDS=3 R2_MOCK_RETURNING_SECONDS=3 python run_mocks.py`（R2モックが:5001、PFモックが:5002で起動）
2. ターミナル2: `python run.py`（本体が:5000で起動）
3. ターミナル3で以下を順に実行し、状態がwaiting→active→waitingと遷移することを確認する:
   - `curl -N http://localhost:5000/api/events &`（SSEの生ログが流れ始める）
   - `curl -X POST http://localhost:5000/api/checkin -H "Content-Type: application/json" -d '{"name":"田中太郎"}'`
   - SSEログに `phase: "waiting"` → `phase: "active"` → 最終的に `phase: "waiting", step: "awaiting_checkin"` が流れることを確認する
4. 異常系確認: PFモックを異常応答（`accepted: false`）に切り替える。
   - ターミナル1で `Ctrl+C` を押し、`run_mocks.py`（PFモック:5002を含む）を停止する。
   - ターミナル1で改めて次を実行し、PFモックだけを異常応答で再起動する（R2モックも同じプロセスで一緒に起動し直す）:
     `PF_MOCK_ACCEPTED=false R2_MOCK_LOADING_SECONDS=3 R2_MOCK_RETURNING_SECONDS=3 python run_mocks.py`
   - ターミナル3から手順3の `curl -X POST .../api/checkin` を再度実行し、`phase: "error"` になることを確認する。
5. `curl -X POST http://localhost:5000/api/reset` でERRORからWAITINGへ戻ることを確認する

## 会場UI（ブラウザ）確認手順

前提: 手順1・2（モックと本体の起動）は上記と同じ。

1. ブラウザで `http://localhost:5000/` を開き、チェックインフォームが表示されることを確認する。
2. 名前を入力してチェックインすると、フォームが隠れて進行状況メッセージ（PF確認中→R2確認中→ドリンクセット中→お届け中→完了通知中）が順に表示され、最終的にフォームに戻ることを確認する。
3. 別のブラウザ（またはシークレットウィンドウ）で同時に `http://localhost:5000/` を開き、1人目が進行中の間は「他の方が対応中：〈ステップ〉」と表示され、フォームが使えないことを確認する。
4. `PF_MOCK_ACCEPTED=false` でモックを再起動し、チェックインしてエラー画面（`error_message`とリセットボタン）が表示されることを確認する。リセットボタンを押すとフォーム表示に戻ることを確認する。
