# GPUデフォルト／no-GPU音声環境設計

## 目的

GPUを利用できる環境では音声IFを標準機能として利用し、GPUを利用できない環境では音声依存をインストールせず、Flask本体・会場UI・モック・コアテストだけを動かせるようにする。

## 決定事項

- GPU構成をデフォルトとする。
- GPUなし構成は `requirements-no-gpu.txt` で明示する。
- GPUなし構成では音声IFをインストールしない。CPU版Whisperへのフォールバックは実装しない。
- 音声IFは本体プロセスに組み込まず、`python -m voice_ui.main` で別プロセスとして明示的に起動する。
- 既存の `requirements-core.txt` は共通依存の内部構成として維持する。
- 既存の `requirements-voice-gpu.txt` はGPU専用依存として維持する。

## 依存関係

```text
requirements.txt
├── requirements-core.txt
└── requirements-voice-gpu.txt

requirements-no-gpu.txt
└── requirements-core.txt
```

### GPU環境

`requirements.txt` をインストールする。これによりFlask本体、テスト、音声UI、CUDA版torch/torchaudioが利用可能になる。

### GPUなし環境

`requirements-no-gpu.txt` をインストールする。音声UIの依存関係は含めず、`python run.py` によるコアアプリだけを利用する。

## 起動方法

GPU環境では次の2プロセスを起動する。

```bash
python run.py
python -m voice_ui.main
```

GPUなし環境ではFlask本体だけを起動する。

```bash
python run.py
```

音声IFは自動起動しない。これにより、GPUなし環境で音声依存やデバイス初期化が原因となって本体UIが起動できなくなることを防ぐ。

## 設定と実行時の扱い

GPU版の音声設定は既存どおり `WHISPER_DEVICE=cuda` と `WHISPER_FP16=1` をデフォルトとする。GPU環境でCUDAが使えない場合は、音声プロセスの起動失敗として扱い、Flask本体の起動可否には影響させない。

GPUなし環境で `voice_ui.main` を実行することはサポート対象外とする。READMEと起動手順で、GPUなし環境では音声プロセスを起動しないことを明記する。

## テスト方針

- GPU環境では既存の全テストを実行する。
- GPUなし環境では、音声ハードウェア・GPU・音声依存を必要とするテストと、音声依存を読み込む統合テストを除外する。
- GPUなし向けのテストコマンドをREADMEに固定し、コア機能の回帰を検証できるようにする。
- `requirements-no-gpu.txt` のインストール後に、Flask本体とモックが起動できることを確認する。

## READMEへの反映

READMEに次を記載する。

- GPU構成がデフォルトであること
- GPU環境では `requirements.txt` を使うこと
- GPUなし環境では `requirements-no-gpu.txt` を使うこと
- GPUなし環境では音声IFを利用できないこと
- GPU環境でのFlask本体・モック・音声IFの起動方法
- GPUあり／GPUなしのテストコマンド

## 受け入れ条件

1. `requirements.txt` からGPU版の依存関係をインストールできる。
2. `requirements-no-gpu.txt` からコア依存だけをインストールできる。
3. GPUなし環境で `python run.py` が起動できる。
4. GPUなし環境の手順に音声プロセスの起動が含まれていない。
5. GPU環境では既存の音声IF起動手順を継続利用できる。
6. READMEの依存関係、起動方法、テスト方法が実際のファイル構成と一致する。

## 対象外

- CPU版Whisperへのフォールバック
- GPUの自動検出による依存関係インストールやプロセス起動
- Docker/ComposeによるGPU切り替え
- 音声IF自体の認識精度や会話フローの変更
