# 音声対話（フロント雑談） 設計仕様 (2026-09-29)

## 背景・目的

`voice_ui` は現在、確信度を通過した発話に開始キーワード（既定「チェックイン」）が
含まれるときだけ `POST /api/voice/start` を呼び、キオスクを検索画面にする
（`2026-09-29-checkin-entry-design.md`）。それ以外の発話には反応しない。

来場者がホテルのフロントに話しかけるように、チェックイン以外の質問や
気軽な雑談にも音声で応じられるようにする。チェックインの意図が汲み取れた
ときは、キーワードを言わなくても今の開始動作につなぐ。

## 決定事項

- 対応する話題: ホテルに関する質問への回答と、フロントスタッフらしい気軽な雑談。
  - ホテルの事実はホテル情報ファイルに基づいて答える。ファイルにないホテルの
    事実（料金、空室など）は作らず「スタッフにお尋ねください」と返す。
  - 天気・挨拶などの一般的な雑談は LLM の知識で返してよい。
- 応答は音声だけ。キオスク画面は変えない（チェックインの意図のときだけ
  今と同じく検索画面へ）。会話の記録はデバッグ画面で見る。
- 返事をするかどうかは発話ごとに LLM が判定する（ロボットへの話しかけでなければ黙る）。
- ホテル情報はデモ用の架空ホテルとして用意し、リポジトリに置く。
- 対話は `voice_ui` の中で行う（アプリに対話APIは作らない）。
- 「チェックイン」を含む発話は LLM を通さず即開始する（今の速さを保つ）。
- LLM は Qwen3.6-35B-A3B pod（OpenAI互換、`vlm_server` と同じもの）を既定とする。

## 全体の流れ

```
マイク → VAD → Whisper → 確信度判定
  ├ 読み上げ中／読み上げ終了後 ECHO_GUARD_SECONDS 以内に重なった発話 → 破棄（self_echo）
  ├ 開始キーワードを含む → POST /api/voice/start（keyword_start）
  └ 含まない（DIALOGUE_ENABLED=1 のとき）→ LLM 判定
        ├ intent=checkin → POST /api/voice/start（checkin）
        ├ intent=chat    → reply を読み上げ（chat）
        └ intent=ignore  → 何もしない（ignore）
```

`DIALOGUE_ENABLED=0` のときは、キーワードを含まない発話は今と同じく無視する（no_keyword）。

`/api/voice/start` の結果（keyword_start / checkin 共通）:

| 結果 | voice_ui の動作 |
|---|---|
| accepted (202) | 何も言わない。入力案内は既存どおり SSE 経由で `ProgressAnnouncer` が読み上げる |
| not_available (409) | `BUSY_MESSAGE`「ただいま他のお客様をご案内しています。少々お待ちください」を読み上げる |
| rate_limited (429) / その他 | 何も言わない（ログのみ） |

## LLM とのやり取り

### 呼び出し

- OpenAI互換 `POST {DIALOGUE_LLM_URL}/chat/completions`
- `temperature=0.3`、`max_tokens=200`
- `response_format` に JSON schema を指定し、出力を次に固定する。

```json
{
  "type": "object",
  "properties": {
    "intent": {"type": "string", "enum": ["checkin", "chat", "ignore"]},
    "reply": {"type": "string"}
  },
  "required": ["intent", "reply"],
  "additionalProperties": false
}
```

- `reply` は `chat` のときだけ使う（他の intent では空でよい）。
- 時間切れ（`DIALOGUE_LLM_TIMEOUT_SECONDS`、既定8秒）、HTTPエラー、不正な出力は
  `ignore` として扱い、ログに残す。

### プロンプト

システムプロンプトに次を入れる。

- 役柄: 架空ホテル（ホテル情報ファイルの名前）のフロントスタッフのロボット。
  丁寧な日本語で、1〜2文・合計80文字程度までで答える。読み上げるので記号・
  箇条書き・絵文字を使わない。
- 判定の基準:
  - `checkin`: チェックインしたい・予約して来た・部屋に入りたい等、チェックイン手続きを
    求めている。
  - `chat`: ロボット（フロント）に向けた質問・挨拶・雑談。
  - `ignore`: ロボット宛てではない周囲の会話、独り言、意味をなさない断片。
    迷ったら `ignore`。
- 事実の扱い: ホテルの事実はホテル情報の範囲だけで答える。ない場合は
  「スタッフにお尋ねください」と答える。一般的な雑談は自由に答えてよい。
- ホテル情報ファイルの全文。

### 会話履歴

- 直近 `DIALOGUE_HISTORY_TURNS`（既定6）往復の `user` / `assistant` を保持し、
  毎回システムプロンプトの後に付ける。
- `assistant` に入れるのは `chat` の `reply` のみ。`ignore` の発話は履歴に残さない。
- 最後の発話から `DIALOGUE_IDLE_RESET_SECONDS`（既定60秒）たったら履歴を消す
  （次の来場者に前の会話を持ち込まない）。
- `checkin` と判定したら、その時点で履歴を消す（手続きに移るため）。

## ホテル情報

- `data/hotel_info.md`（日本語 Markdown、デモ用の架空ホテル）。
- 項目: ホテル名、チェックイン・チェックアウト時刻、朝食（時間・場所・料金の有無）、
  Wi-Fi、館内設備（大浴場・ジム・ランドリー等）、フロント営業時間、荷物預かり、
  周辺案内（駅・コンビニ等）、禁止事項。
- 起動時に一度だけ読み込む。パスは `HOTEL_INFO_FILE`（既定 `data/hotel_info.md`）。
  読み込めなければ起動時に例外で止める。

## 自分の声への対策（エコーガード）

- `VoicevoxSpeaker` は「再生中、または最後の再生終了から `ECHO_GUARD_SECONDS`
  （既定0.5秒）以内か」を返す `is_busy()` を持つ。
- パイプラインは、発話区間が確定した時点で `is_busy()` が真なら、その発話を
  LLM にもキーワード判定にも回さず破棄する（outcome `self_echo`）。
- 読み上げ途中の割り込み（バージイン）はしない。

## 返事の読み上げ

- `reply` を「。」「！」「？」（全角・半角）で文に区切り、1文ずつ `speak` する。
- `VoicevoxSpeaker` は合成スレッドと再生スレッドに分ける。合成済みの音声を
  キューに積み、1文目の再生中に2文目を合成する。順序は投入順を保つ。
- 事前合成（`preload`）の対象は `VOICE_START_GUIDANCE` と `BUSY_MESSAGE`。

## 会話ログ（デバッグ画面）

### voice_ui → アプリ

発話ごと（`no_utterance` 以外）に `POST /api/voice/turns` を送る。失敗しても処理は続ける。

```json
{
  "text": "朝ごはんは何時からですか",
  "no_speech_prob": 0.12,
  "avg_logprob": -0.31,
  "outcome": "chat",
  "reply": "朝食は6時半から10時まで、1階のレストランでご用意しております。",
  "stt_ms": 840,
  "llm_ms": 1100
}
```

`outcome` は `rejected_low_confidence` / `self_echo` / `keyword_start` /
`checkin` / `chat` / `ignore` / `no_keyword` のいずれか。`llm_ms` は LLM を
呼ばなかったとき `null`。

### アプリ

- `POST /api/voice/turns`: 本文を検証し（`text` は文字列、`outcome` は上記のいずれか）、
  受信時刻 `at`（UTC、`YYYY-MM-DDTHH:MM:SSZ`）を付けて直近20件をメモリに保持する。
  SSE に `{"type": "voice_turn", ...}` として配信する。202。不正なら422。
- `GET /api/voice/turns`: 保持している直近20件を新しい順で返す。
- キオスク・`ProgressAnnouncer` は `type` 付きイベントを無視する（既存）。

### デバッグ画面

- 「音声対話ログ」欄を追加し、新しい順に表で表示する:
  時刻、書き起こし、判定、返事、no_speech_prob、avg_logprob、STT(ms)、LLM(ms)。
- ページを開いたときに `GET /api/voice/turns` で読み込み、以後は SSE の
  `voice_turn` を先頭に追加する（最大20行）。

## 設定（環境変数、`voice_ui/config.py`）

| 変数 | 既定値 |
|---|---|
| `DIALOGUE_ENABLED` | `1` |
| `DIALOGUE_LLM_URL` | `http://10.43.10.179:8000/v1`（`one-box-rag-chat` の ClusterIP） |
| `DIALOGUE_LLM_MODEL` | `qwen3.6-35b-a3b` |
| `DIALOGUE_LLM_API_KEY` | 空 |
| `DIALOGUE_LLM_TIMEOUT_SECONDS` | `8` |
| `DIALOGUE_HISTORY_TURNS` | `6` |
| `DIALOGUE_IDLE_RESET_SECONDS` | `60` |
| `HOTEL_INFO_FILE` | `data/hotel_info.md` |
| `ECHO_GUARD_SECONDS` | `0.5` |

## エラーハンドリング

| 状況 | 振る舞い |
|---|---|
| LLM 時間切れ・HTTPエラー・不正出力 | `ignore` 扱い、警告ログ。キーワード開始は影響なし |
| `/api/voice/turns` 送信失敗 | 無視（デバッグ用のため） |
| 1文の合成失敗 | 警告ログ、次の文へ |
| ホテル情報ファイルが読めない | 起動時に例外で停止 |

## テスト方針

- 対話（`voice_ui/dialogue.py`）: フェイク LLM で、intent ごとの結果、履歴の上限、
  60秒での消去、checkin での消去、時間切れ・不正出力の ignore 扱い、
  システムプロンプトにホテル情報が入ること。
- LLM クライアント: `responses` で、JSON schema 付きリクエスト、応答の解釈、エラー時。
- パイプライン: キーワードなら LLM を呼ばない、checkin/chat/ignore の振り分け、
  409 で `BUSY_MESSAGE`、エコーガードでの破棄、`DIALOGUE_ENABLED=0`、
  ターン送信の内容。
- スピーカー: 文の区切り、合成と再生の順序、`is_busy()` の時間判定（時計を注入）。
- アプリ: `/api/voice/turns` の検証・保持件数・SSE 配信・GET の順序。
- デバッグ画面: 「音声対話ログ」欄の要素と `debug.js` が `voice_turn` を扱うこと。
- 判定精度の評価: `tools/dialogue_eval.py` と `tests/fixtures/dialogue/cases.json`
  （checkin / chat（ホテル質問・雑談）/ ignore のラベル付き発話 16件程度）。
  pod に投げて intent の正答率を出す（手動実行、CI 対象外）。
- 実機: マイクで話して確認する。

## 運用上の推奨（README に記載）

雑談の返事はその場で合成するため、VOICEVOX（CPU版）は性能コアに固定して
起動することを推奨する（`--cpuset-cpus=5-9,15-19` と `--cpu_num_threads 10`、
GB10 の場合）。固定しないと1文の合成が2〜9秒ぶれることを計測で確認している。

## 対象外

- キオスク画面への字幕表示
- 読み上げ中の割り込み（バージイン）
- 音声での予約検索・確定
- VOICEVOX の GPU 化、Whisper の変更
