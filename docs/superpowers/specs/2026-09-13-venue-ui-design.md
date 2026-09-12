# 会場UI 設計仕様 (2026-09-13)

## 背景・目的

既存のFlaskバックエンド (`app/`) は check-in → guide-robot-ready → drink-load →
drink-delivered のサイクルを状態機械で管理し、`/api/checkin`・`/api/reset`・
SSEの`/api/events`を提供しているが、現状フロントエンドが一切存在しない。

会場UIは、来場者が自分で名前を入力してチェックインし、その場でAI管制PF
(案内ロボット)とR2/Themis(ドリンク配送ロボット)の進行状況を見守るための
セルフサービス画面として新設する。

## スコープ

- 対象: 来場者が使う1画面のキオスクUI（チェックイン操作＋進行状況表示）。
- 既存バックエンド（`app/state_machine.py`, `app/routes/checkin.py`,
  `app/routes/events.py`, clients等）は変更しない。R2/PFの「お届け完了」を
  新たに判定するロジックは追加しない — 既存のHTTPステータス
  (`phase`/`step`/`guest_name`/`request_id`/`error_message`) をそのまま
  表示するだけで十分とする。
- ビルドツール・フロントエンドフレームワークは導入しない
  (Flaskテンプレート + バニラJS + バニラCSSのみ)。

## アーキテクチャ

単一ページを、`/api/events` から届くsnapshotだけで駆動する「純粋なレンダラー」
として実装する。ポーリングやページ遷移は使わない。

### 新規ファイル

- `app/routes/ui.py` — `GET /` で `templates/index.html` を返すBlueprint。
- `app/templates/index.html` — 画面の骨格。名前入力フォーム／進行状況表示／
  エラー表示の3ブロックをJSで出し分ける。
- `app/static/app.js` — `EventSource('/api/events')` を購読しDOMを更新。
  `fetch`で`/api/checkin`・`/api/reset`を呼ぶ。
- `app/static/style.css` — キオスク向けの最小限のスタイル（大きめの文字・
  ボタン）。

`app/__init__.py` に `ui_bp` を登録する1行を追加するのみ。

## 状態遷移とUX

自分のチェックイン名は `sessionStorage` の `myGuestName` に保存し、SSEの
`snapshot.guest_name` と比較して「自分の進行」か「他の人の進行」かを
判定する（バックエンドにguest単位のセッション概念はないため、この判定は
ブラウザローカルの補助情報として扱う）。

`snapshot.phase` / `snapshot.step` / `snapshot.guest_name` から以下の4つの
表示パターンを導出する。

1. **入力フォーム** — `phase=waiting` かつ `step=awaiting_checkin` →
   名前入力＋チェックインボタンを表示。
2. **自分の進行中** — `guest_name === myGuestName` → ステップに応じた
   日本語メッセージを表示:
   - `polling_pf_ready` → 「AI管制PF(案内ロボット)の状態を確認しています」
   - `polling_r2_ready` → 「ドリンク準備ロボットの状態を確認しています」
   - `sending_load_drink` → 「ドリンクをセットしています」
   - `polling_r2_active`（`phase=active`） → 「ドリンクをお届け中です」
   - `notifying_pf_placed` → 「お届け完了を通知しています」
   - バックエンドが `awaiting_checkin` に戻したら、そのままフォーム表示に
     切り替える。完了を独自に検出するロジックや完了トースト等は実装しない。
3. **他の人の進行中** — `guest_name` があり `myGuestName` と不一致 →
   名前は出さず「他の方が対応中：〈同ステップ表示〉」とだけ表示し、
   フォームを無効化する（待機列の可視化）。
4. **エラー** — `phase=error` → `error_message` をそのまま表示し、
   「リセット」ボタンを誰でも押せる状態で表示する（成功すれば1に戻る）。

### チェックイン送信時の409対応

通常はSSEで事前にフォームが無効化されているはずだが、競合で409が返った
場合は、エラー表示は出さず次のSSEスナップショットの反映を静かに待つ。

## エラーハンドリング

- `/api/checkin`・`/api/reset`のHTTPエラー（409, 422等）はUI上で目立つ
  エラー表示にはしない（上記の通り、次のSSE更新を待てば整合するため）。
- `EventSource`の接続切れは、ブラウザの自動再接続に任せる（追加のリトライ
  ロジックは実装しない）。

## テスト方針

**バックエンド (pytest)**:
- `tests/test_routes_ui.py` を追加。`GET /` が200を返し、テンプレートが
  正しくレンダリングされること（キー要素の存在）を、既存の
  `test_routes_checkin.py` と同じFlaskテストクライアントパターンで確認する。

**フロントエンドJS**:
- リポジトリにNode/JSテストツールチェーンが無いため、新規導入しない
  (YAGNI)。`app.js`はsnapshot→表示の単純なマッピングに留め、ロジックを
  薄く保つ。
- 動作確認は `docs/superpowers/plans/manual-e2e-check.md` の手動E2E手順を
  拡張し、モックサーバー (`PF_MOCK_FORCE_FAILURE`/`R2_MOCK_FORCE_FAILURE`等)
  を使って以下を目視確認する項目を追加する:
  - フォーム表示 → チェックイン → 各ステップ表示の切り替わり
  - 別タブ/別ブラウザで2人目がアクセスした際の「他の方が対応中」表示
  - `PF_MOCK_FORCE_FAILURE=500` 等でエラー画面＋リセットボタンの動作
