# 手動E2E確認手順

前提: `pip install -r requirements.txt` 済み。

1. ターミナル1: `R2_MOCK_LOADING_SECONDS=3 R2_MOCK_RETURNING_SECONDS=3 python run_mocks.py`（R2モックが:5001、PFモックが:5002で起動）
2. ターミナル2: `python run.py`（本体が:5000で起動）
3. ターミナル3で以下を順に実行し、状態がwaiting→active→waitingと遷移することを確認する:
   - `curl -N http://localhost:5000/api/events &`（SSEの生ログが流れ始める）
   - `curl -X POST http://localhost:5000/api/checkin -H "Content-Type: application/json" -d '{"name":"田中太郎"}'`
   - SSEログに `phase: "waiting"` → `phase: "active"` → 最終的に `phase: "waiting", step: "awaiting_checkin"` が流れることを確認する
4. 異常系確認: `PF_MOCK_ACCEPTED=false python -c "from mocks.pf_mock import create_pf_mock_app; create_pf_mock_app().run(port=5002)"` のようにPFモックを異常応答に切り替えて再度チェックインし、`phase: "error"` になることを確認する
5. `curl -X POST http://localhost:5000/api/reset` でERRORからWAITINGへ戻ることを確認する
