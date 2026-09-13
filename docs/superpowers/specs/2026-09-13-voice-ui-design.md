# 音声IF 設計仕様 (2026-09-13)

## 背景・目的

`state_machine.pdf` の「システム構成」に「DGX Spark @dBF会場」の一項目として
「マイク・スピーカーを繋げて音声IF」が挙げられている。会場UI (`app/`,
`docs/superpowers/specs/2026-09-13-venue-ui-design.md`) はブラウザのフォーム
入力＋画面表示のみを実装しており、マイク・スピーカーは未対応。

本仕様は、来場者が名前を声で伝えてチェックインでき、チェックイン後の進行
状況を音声で読み上げる「音声IF」を新設するための設計を定める。

社内の別プロジェクト `../dimos` に、mic → VAD/正規化 → Whisper(STT) →
テキスト → TTS → speaker という音声パイプラインの実装例と、実際にdBF会場の
ような雑音の多い環境でVAD代わりの振幅閾値検出が誤爆した経験がある。本設計
はその反省を踏まえる（[dimosとの比較](#dimosの実装との比較)参照）。

## スコープ

- 対象: チェックイン画面と同じ会場端末で動く、名前の音声入力＋進行状況の
  音声読み上げ。
- 既存バックエンド（`app/state_machine.py`, `app/routes/checkin.py`,
  `app/routes/events.py`, clients等）は変更しない。既存の
  `POST /api/checkin` と `GET /api/events` (SSE) をそのまま利用する。
- 新規プロセス `voice_ui/` として実装し、Flaskアプリ (`run.py`) とは別プロ
  セスで動かす。両者はHTTP/SSE経由でのみやり取りし、Pythonレベルの相互
  importは行わない。
- **今回のスコープ外（将来のサブタスク）**: `phase=waiting` /
  `step=awaiting_checkin` のときだけマイクを有効化する状態連動ゲーティング。
  今回はマイクは常時有効のまま、VAD＋Whisper確信度の二重フィルタのみで
  雑音対策を行う。チェックインサイクル進行中に誤って`/api/checkin`が呼ばれ
  ても、既存の状態機械が409を返して弾くため実害はない。
- 音声コマンドは「名前を話す→チェックイン」の1種類のみ。リセット等その他
  の音声コマンドは対象外。
- ビルドツール等の新規フロントエンド資産は追加しない（`voice_ui/`は純粋な
  Pythonプロセス）。

## アーキテクチャ

`voice_ui/` を新設し、以下の小さなコンポーネントに分割する。dimosの
`Observable`ベースのノード連結フレームワークは導入しない — 本IFは分岐の
無い一本のパイプライン2系統（入力系・出力系）であり、reactivexの配線機構は
過剰。各コンポーネントは単一責務・独立してユニットテスト可能な形にする。

### 新規ファイル

- `voice_ui/mic.py` — `SounddeviceMicSource`。`sounddevice.InputStream`の
  コールバックでfloat32フレームをキューに積む。
- `voice_ui/vad_segmenter.py` — Silero VAD (ONNX runtime版、torch不要) を
  使い、フレーム列から1発話分の音声（`np.ndarray` + サンプルレート）を
  区切って返す。トレイリングサイレンス検出で発話終端を確定する。
- `voice_ui/stt.py` — `WhisperTranscriber`。faster-whisper
  (`language="ja"`) で発話を文字起こしし、`(text, no_speech_prob,
  avg_logprob)`を返す。純粋関数 `is_confident(no_speech_prob, avg_logprob,
  thresholds) -> bool` を同モジュールに持ち、閾値判定をI/Oから分離する。
- `voice_ui/name_extract.py` — 純粋関数 `extract_name(text: str) -> str`。
  「名前は」「です」「と申します」等の定型パターンを除去し、それ以外は
  トリムした生テキストをそのまま名前として扱う。
- `voice_ui/checkin_client.py` — `CheckinClient.checkin(name: str)`。
  `POST {FLASK_BASE_URL}/api/checkin` を呼ぶ薄いHTTPクライアント
  （既存の`app/clients/`と同じ形）。
- `voice_ui/tts.py` — `VoicevoxSpeaker`。VOICEVOXエンジンHTTP API
  (`/audio_query` → `/synthesis`) でWAVを合成し、スピーカー出力キューに渡す。
  起動時に`/version`をプローブし、失敗時はリトライ後に例外送出（dimosの
  `VoicevoxTTSNode`と同じfail-fast方針）。
- `voice_ui/speaker.py` — `SounddeviceSpeakerSink`。合成済みWAVを
  `sounddevice.OutputStream`に書き込む。
- `voice_ui/progress_announcer.py` — `GET /api/events` (SSE) を購読し、
  スナップショットの`step`変化 / `phase=error`を検知して読み上げ対象の
  テキストをキューに積む。読み上げ文言は `STEP_MESSAGES`
  （`app/static/app.js`の同名定数と同一内容。JS/Pythonでソース共有できない
  ため値を複製するが、キー（step名）は`app/state_machine.py`の定数と一致
  させる）。
- `voice_ui/main.py` — エントリポイント。以下2系統を配線する。
  - 入力系: mic → vad_segmenter → stt(+is_confident) → name_extract →
    checkin_client
  - 出力系: progress_announcer(SSE) → tts → speaker
- `voice_ui/config.py` — 環境変数読み込み（`FLASK_BASE_URL`,
  `VOICEVOX_URL`, Whisperモデルサイズ, VAD/確信度の各閾値など。
  `app/config.py`の既存パターンに合わせる）。

### 環境変数（案）

| 変数 | デフォルト | 用途 |
|---|---|---|
| `FLASK_BASE_URL` | `http://localhost:5000` | チェックインAPI/SSEの接続先 |
| `VOICEVOX_URL` | `http://127.0.0.1:50021` | VOICEVOXエンジン |
| `WHISPER_MODEL` | `base` | faster-whisperのモデルサイズ |
| `STT_NO_SPEECH_PROB_MAX` | `0.6` | この値を超えたら破棄 |
| `STT_AVG_LOGPROB_MIN` | `-1.0` | この値を下回ったら破棄 |
| `VAD_TRAILING_SILENCE_MS` | `500` | 発話終端とみなす無音長 |

## データフロー

**入力側（チェックイン）**

1. `mic.py`がマイクからフレームを連続的にキューへ積む。
2. `vad_segmenter.py`がSilero VADの音声確率を見て発話区間をバッファし、
   トレイリングサイレンスを検知した時点で1発話分を確定・emitする。
3. `stt.py`がfaster-whisperで文字起こしし、`(text, no_speech_prob,
   avg_logprob)`を得る。
4. `is_confident(...)`がfalseなら破棄してログのみ、次の発話待ちに戻る
   （音声IFとしては無反応。UI側の状態は変えない）。
5. 確信度を通過したら`name_extract.extract_name(text)`で名前を抽出。
6. `checkin_client.checkin(name)`が`POST /api/checkin`を呼ぶ。
   - `200`: ログ出力のみ（画面はSSE経由で自動的に進捗表示へ切り替わる）。
   - `409`（サイクル進行中）: 想定内。警告ログのみで無視する。
   - その他エラー: 警告ログを残し、プロセスは継続する。

**出力側（進捗読み上げ）**

1. `progress_announcer.py`が`GET /api/events`のSSEを購読し続ける。
2. 直前のスナップショットと比較し、`step`が変化していれば
   `STEP_MESSAGES[step]`を、`phase == "error"`なら`error_message`を、
   読み上げキューに積む。
3. `tts.py`がキューを順にVOICEVOXへ渡し、WAVを`speaker.py`へ渡す。
4. スピーカー出力とマイク入力は独立コンポーネントであり、読み上げ中も
   マイクは拾い続ける（エコー/ハウリング対策や「読み上げ中はマイクを
   一時停止する」といったゲーティングは今回のスコープ外。将来の
   状態連動ゲーティング実装時にあわせて検討する）。

## エラーハンドリング

- **VOICEVOXエンジン未起動**: 起動時プローブが既定回数失敗したら例外を
  投げてプロセスを終了する（無音のまま動き続けさせない）。
- **マイクデバイスが無い**: `mic.py`は起動失敗をログに残しプロセスを終了
  する（音声入力がこのプロセスの主目的であるため、フォールバック動作は
  設けない。TTS専用に切り出して動かしたい場合は別プロセスとして起動する
  想定）。
- **faster-whisperモデルロード失敗**: 起動時に一度ロードを試み、失敗したら
  即終了する。
- **低確信度の発話**: `is_confident()`で破棄し、デバッグ用に
  `text/no_speech_prob/avg_logprob`をログへ残す（閾値チューニング用）。
- **`name_extract`が想定外の文字列を作る**: 既存のテキスト入力フォームも
  任意文字列を許容しているため、バックエンド側追加バリデーションは行わない。
- **Flaskアプリに接続できない（ネットワーク/起動順序）**: `checkin_client`
  はリクエスト例外を警告ログに残し、プロセス自体は継続する。
- **SSE切断**: `progress_announcer.py`は接続断を検知したら指数バックオフで
  再接続する。

## テスト方針

既存リポジトリのテストスタイル（pytest + `responses`、`app/clients/`と
同じ依存注入パターン）に合わせる。

- **純粋関数のユニットテスト**（音声・ネットワーク不要、最優先）:
  - `is_confident()`: 閾値の境界ケース（ちょうど閾値、閾値超え/未満）
  - `extract_name()`: 「田中太郎です」「名前は田中太郎」「田中太郎」
    「田中太郎と申します」等のパターン
  - `STEP_MESSAGES`: `app/state_machine.py`の全STEP定数に対応する文言が
    存在することを検証するテスト（`app/static/app.js`とのキー一致も
    合わせて確認し、2箇所の定義が乖離したら検知できるようにする）
- **`checkin_client`**: `responses`で`/api/checkin`をモックし、200/409/422/
  接続エラーそれぞれのハンドリングを検証。
- **VAD/Whisper/VOICEVOXの実モデル自体はユニットテスト対象外**
  （重い・非決定的なため）。各クラスはコンストラクタでクライアント/
  モデルを差し替え可能にし（既存の`r2_client`/`pf_client`と同じDI
  パターン）、`main.py`の配線ロジック（mic→VAD→STT→confidence gate→
  name_extract→checkinが正しい順で呼ばれるか、破棄時に後続を呼ばないか）
  をフェイクで検証する。
- **手動E2E**: `docs/superpowers/plans/manual-e2e-check.md`に倣い、実機
  （VOICEVOXエンジン起動＋マイク/スピーカー接続）での確認手順を追記する。
  最低限、以下を含める:
  - 雑音（BGM・人の会話等）の中で無関係な発話をしてもチェックインが
    誤発火しないこと
  - 静かな環境で「田中太郎です」等と発話するとチェックインが実行され、
    画面（会場UI）とスピーカーの両方に進捗が反映されること
  - `PF_MOCK_FORCE_FAILURE`等でエラー状態にした際、`error_message`が
    読み上げられること

## dimosの実装との比較

| 観点 | dimos | 本設計 | 差分の理由 |
|---|---|---|---|
| マイク取得 | `node_microphone.py`: `SounddeviceAudioSource`、`reactivex.Observable`で`AudioEvent`をemit | `mic.py`: 同じsounddeviceコールバックだが、キューに積むだけでreactivex無し | dimosの`Observable`/`AbstractAudioEmitter`は多数のノードを動的に繋ぎ替える汎用エージェント基盤のためのもの。本IFは分岐の無い固定1系統パイプラインであり、reactivexの配線コストが見合わない。 |
| 発話区切り | 振幅閾値: `AudioNormalizer`（ゲイン/ピーク追跡）＋`VolumeMonitorNode`、または手動`KeyRecorder`（PTT） | `vad_segmenter.py`: Silero VAD（音声らしさをモデルで判定） | dBF会場で振幅閾値が雑音に誤反応した実体験そのものへの対策。dimosにはVADモデルが無く、「十分大きい音」か「人間がキーを押している間」のどちらかしかなかった。 |
| STT | `stt/node_whisper.py`: `WhisperNode`、確信度による棄却なし（PTTで「これは発話である」ことが人手で保証されている前提） | `stt.py`: faster-whisperに加え`is_confident()`で`no_speech_prob`/`avg_logprob`による二段フィルタ | VADによる区切りは確率的でPTTのような人手保証が無いため、本設計で新たに追加した防御層。 |
| テキスト→アクション | `agents/whisper_human_input_ja.py`: 文字起こしを`/human_input`トピックへ publish し、汎用LLMエージェントが解釈 | `name_extract.py`＋`checkin_client.py`: ルールベースの名前抽出＋固定エンドポイントへの直接POST | dimos側は任意の発話・任意の意図に対応する会話エージェントが前提。本IFは「名前を言う」の1意図のみのため、LLMエージェントを挟まず単純関数で十分（レイテンシ・コストの節約にもなる）。 |
| TTS | `tts/node_voicevox.py`: `VoicevoxTTSNode`、HTTP経由でVOICEVOXエンジンを叩き、起動時プローブ＋キュー処理スレッド | `tts.py`: ほぼ同一のHTTP呼び出し・起動時プローブ方針をreactivexの`Subject`無しで踏襲 | この部分のdimos実装はそのまま本用途に合っていたため、配線機構だけ外して流用。 |
| 音声出力 | `node_output.py`: `SounddeviceAudioOutput`、出力デバイスが無くてもログを出して音声を捨てるだけで継続動作 | `speaker.py`で同様の degrade-gracefully 方針を踏襲 | キオスク会場側の機材構成が予告なく変わりうるため、この耐性はそのまま維持する価値がある。 |
| 全体方針 | 小さな単機能ノードを`Observable`で繋ぐ汎用フレームワーク | 同じ「小さな単機能・独立してテスト可能」という設計原則は継承しつつ、reactivex層は導入しない | 固定1系統パイプラインにはプレーンな関数/クラスの方が読みやすく、テストしやすく、本リポジトリに`reactivex`/`AbstractAudio*`依存を新規追加せずに済む。 |
