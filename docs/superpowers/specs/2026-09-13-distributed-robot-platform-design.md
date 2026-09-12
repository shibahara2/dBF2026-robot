# 分散ロボ基盤 設計書

- 日付: 2026-09-13
- 参照元: `docs/state_machine.pdf`（分散ロボ基盤）, `docs/R2_Themis-Demo-Specification-v1.pdf`（R2/Themis API仕様）

## 1. 目的

dBF2026会場でのデモ「チェックイン → ロボットが飲み物を配達 → 完了」を実現する基盤を実装する。
基盤は AI管制PF・R2/Themis（ロボット）・会場UIの間を仲介するオーケストレーターであり、
実物のAI管制PF/R2/Themisがまだ用意できない開発期間中は自前のモックサーバで代替する。

## 2. システム構成

```
[会場ディスプレイのブラウザ]  (DGX Spark @dBF会場。マイク/スピーカーは将来の音声IF用、今回スコープ外)
     │ HTTP (POST /api/checkin, POST /api/reset) + SSE (GET /api/events)
     ▼
[大手町DC: Flask App]  (DGX Spark @大手町DC。単一プロセス・単一ワーカー)
 ├─ Web層（Flaskルート）: チェックインAPI、SSE配信
 ├─ StateMachine（バックグラウンドスレッド1本、プロセス起動時から常駐）
 └─ HTTPクライアント: 管制PF・R2/Themisへ発呼
     │                              │
     ▼                              ▼
[AI管制PF モック]               [R2/Themis モック]
(GET guide-robot/status,        (POST load-drink,
 POST drink/placed)              GET load-drink/status)
```

**ネットワーク前提**: 大手町DCと会場は同一L2/L3、NAT無しでインターネット経由ではない。
会場ブラウザは大手町DCのFlaskサーバへ直接HTTPでアクセスできる。

**役割分担の整理**（大手町Sparkが「サーバーかつクライアント」に見える点について）:
- 大手町Sparkは会場ブラウザに対しては**サーバー**、AI管制PF/R2に対しては**クライアント**であり、
  相手が異なるため矛盾ではない（一般的なbackend-for-frontend構成）。
- 業務ロジック（状態機械）は大手町DC側に集約し、会場側は「ブラウザ＋将来の音声入出力」のみの
  薄いクライアントに留める。会場側のネットワーク/機材トラブルが基盤のロジックに影響しないための判断。

## 3. プロセス・スレッドモデル

- **プロセス**: 1つ。Flaskは `threaded=True` の単一ワーカーで起動する（マルチワーカー禁止 — 状態が分裂するため）。
- **スレッド**:
  1. **状態機械スレッド（常時1本）**: プロセス起動時に開始し、待機とWAITING/ACTIVEの実行を繰り返す。
     チェックインごとにスレッドを作り直さない。
  2. **HTTPハンドリングスレッド（可変）**: Flaskがリクエスト/SSE接続ごとに使用。SSE接続は接続中ずっと
     1本を占有するため、他のAPI（checkin/reset）を同時に受けるにはマルチスレッド必須。

## 4. 状態機械

状態は `docs/state_machine.pdf` の WAITING / ACTIVE の2つに、例外系の ERROR を加えた3つのみ
（独自のIDLE等の状態は導入しない）。

```
[WAITING]
   0. チェックインボタン待ち（PF/R2への問い合わせはまだ発生しない。会場UIは開始/予約確認画面）
      - POST /api/checkin {name} を受けたら 1. へ
   1. while true; GET <AI管制PF>/guide-robot/status
      - status=Ready → break（2.へ）
      - status=Initializing → 2秒wait して continue
      - timeout / 422 → 2秒wait して continue
      - それ以外 → ERROR
   2. while true; GET <R2>/v1/commands/load-drink/status
      - status=completed → break（3.へ）
      - status=loading/returning → 2秒wait して continue
      - status=failed → ERROR
      - timeout → 2秒wait して continue
   3. request_id を生成（ISO8601タイムスタンプ、例 "2026-09-11T07:54:32.481Z"）
   4. POST <R2>/v1/commands/load-drink
      - 200 → break（ACTIVEへ）
      - 422/500 → ERROR
      - timeout → 同じ request_id で再送
   ▼
[ACTIVE]
   1. while true; GET <R2>/v1/commands/load-drink/status
      - response.request_id != 送信したrequest_id → ERROR
      - status=loading → 2秒wait して continue
      - status=returning/completed → break（2.へ）
      - status=failed → ERROR（人手で直す必要がある旨を表示）
      - timeout → 2秒wait して continue
   2. POST <AI管制PF>/drink/placed
      - accepted=true → break（WAITING step0 へ）
      - accepted=false またはHTTPエラー → ERROR（即時。リトライしない）
   ▼
[WAITING] step0 に戻る（会場UIも自動で開始画面に戻る）

[ERROR]（WAITING/ACTIVEのどのステップからも遷移しうる）
   - 会場UIはエラー画面＋エラー内容を表示
   - オペレーターが物理的にロボットを初期位置へ戻した後、UIの「リセット」ボタンを押す
   - POST /api/reset を受けたら WAITING step0 へ戻る
```

状態機械が保持するデータ: `phase`（waiting/active/error）, `step`（現在の詳細ステップ、UI表示用メッセージ）,
`guest_name`, `request_id`, `error_message`。状態が変化するたびにSSE配信キューへスナップショットをpublishする。

**1回に1組客のみ**: ロボットが物理的に1台のため、WAITING step0以外（つまり手順が進行中）に
`POST /api/checkin` が来た場合は 409 を返す。

## 5. 基盤が公開するAPI（会場UI向け）

| Method/Path | 用途 |
|---|---|
| `POST /api/checkin` | body `{name}`。WAITING step0のときのみ受理し手順を開始。それ以外は409 |
| `POST /api/reset` | ERROR状態のときのみ受理しWAITING step0へ戻す。それ以外は409 |
| `GET /api/events` | SSE。状態変化のたびに `{phase, step, guest_name, request_id, error_message}` をpush |

## 6. モックサーバ（開発期間中の代替）

- `mocks/r2_mock.py`: `R2_Themis-Demo-Specification-v1.pdf` 記載の
  `POST /v1/commands/load-drink` / `GET /v1/commands/load-drink/status` を実装。
  内部でタイマーにより `none→loading→returning→completed` を数秒かけて遷移させ、実機の動きに近づける。
  冪等性ルール（同一request_idの再送は200、status=completed以外での新規コマンドは500）も再現する。
- `mocks/pf_mock.py`: `GET /api/v1/guide-robot/status`（Ready/Initializing切り替え）、
  `POST /api/v1/drink/placed`（`{accepted: true}` 固定、環境変数等でfalse/エラーへ切替可）を実装。
- どちらも異常系（422/500/timeout/failed/accepted=false）を意図的に発生させるフラグを持たせ、
  基盤側のERROR経路を機械的にテストできるようにする。
- 実機に切り替える際は `R2_BASE_URL` / `PF_BASE_URL` 環境変数を実機のURLに変更するだけで済むようにする。

## 7. エラーハンドリング

- WAITING/ACTIVEの各ステップでdocs記載の異常系（timeout/422/500/failed/request_id不一致/
  accepted=false）を検知したら即座に `phase=error` へ遷移し、以後の自動処理を停止する。
- ERRORからの復帰は「オペレーターがロボットを手動で初期位置へ戻す」ことが前提（仕様上、ロボット側の
  自動復帰手段がないため）。基盤側はUIの手動リセットボタンでのみWAITING step0へ戻る。

## 8. テスト方針

- `state_machine.py`: R2/PFクライアントをモック化した単体テストで、正常系（WAITING→ACTIVE→WAITING）と
  各異常系がERRORに落ちることを検証。
- `clients/`: `responses` 等でHTTPレイヤーのみテスト（タイムアウト・再送・レスポンス解釈）。
- `mocks/`: 仕様書通りの入出力を返すことを軽い統合テストで確認。
- `routes/`: Flaskの `test_client()` で checkin/reset のAPI契約（409条件含む）をテスト。

## 9. スコープ外（将来拡張）

- 会場側の音声IF（マイク・スピーカー）: docsに記載はあるが今回の実装スコープには含めない。
  将来追加する際は会場Spark側にWebRTC等での音声入出力クライアントを追加する想定。
- 複数ロボット・複数会場対応: 今回は単一プロセス・単一状態機械が前提。スケールする場合は
  別途アーキテクチャ再検討が必要。
