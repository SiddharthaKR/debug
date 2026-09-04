# Ask My FPGA — アプリケーション説明

> 🌐 言語: **日本語** · [English / 英語](APP_DESCRIPTION.en.md)
>
> 本アプリが何であり、各ツールが何をするかを正確に記述した公式リファレンス。
> `APP_DESCRIPTION.en.md` と章立てが一対一で対応します。

## 1. 概要
Ask My FPGA は、既存の **SharpRPL C# API** を呼び出して **Red Pitaya FPGA の状態確認
と設定**を行う自然言語エージェントです。ローカル LLM（gemma4、vLLM で配信）を
コーディングエージェントのハーネス（opencode、または任意の MCP クライアント）が駆動し、
小さな Python ツールを呼び出します。エージェントは FPGA を直接操作しません — 既存の
GUI と同様、C# API の HTTP クライアントです。英語でも日本語でも回答し、要求に応じて
ハードウェアを設定します。

## 2. アーキテクチャ
```
ユーザー（英語 / 日本語）
  -> ハーネス（opencode CLI、または MCP クライアント）が vLLM 経由で gemma4 を駆動
  -> Python ツール（tools/ = 読み取り、write_tools/ = 書き込み）+ fpga_common + topology
  -> SharpRPL C# API （HTTPS + x-device-token、deviceId ごと）
  -> Native-C 送信部（TCP）-> Red Pitaya FPGA（ADC -> DSP チェーン -> DAC / SCOPE）
```

## 3. 中核の規律: プロベナンス（出所）タグ
すべてのツール結果は `kind` タグを持ちます。エージェントはこれを保持し、あるレベルを
別のレベルに格上げしてはいけません:
- **fact** — ハードウェアからライブで読み取った値。
- **config** — レジスタカタログ、または文書化された固定配線由来の静的メタデータ。
- **measurement** — 取得した信号サンプルから計算した値。
- **unknown** — 解決・検証できなかったもの。推測せず、そのまま「不明」と述べる。

推論の原則: ハードウェアの**観測**（fact / measurement）と DSP の**解釈**を分けること。
原因を推測する場合（例:「なぜノイズが多いのか」）、いきなり断定せず、まず観測結果を
報告し、その後に考えられる原因を、不確実性を明示した解釈として提示する。

## 4. 安全モデル
- **読み取りは常に安全**（read-only、ハードウェアを変更しない）。
- **書き込みはゲートされる。** 各書き込みツールは既定で**ドライラン**を行い、どの
  レジスタがどう変わるか（現在値 -> 新しい値）を正確に表示する。エージェントが計画を
  提示し、人間が承認し、その後に初めて書き込みが実行される。各書き込みは
  **read-modify-write**（対象のビットフィールドのみ変更し、隣接ビットを保持）で、
  **読み戻し検証**される。
- MCP 版ではこれが 2 段階 `plan_* -> commit_write` になる。`plan_*` は差分 +
  `plan_token` を返し、`commit_write` はハードウェアを読み直し、**計画時から状態が
  変化していれば中止**、そうでなければ適用・検証する。

## 5. 信頼できる情報源（2 つのファイル）
エージェントは配線やレジスタを勝手に作りません。ハードウェアは次の 2 ファイルが定義:
- **settings.json**（`catalog_path`）— レジスタカタログ: エイリアス名 -> アドレス、
  および型（Q15.16 固定小数点 / float / uint32）。
- **topology.yaml**（`topology_path`）— データパス: 固定（ハードワイヤ）エッジ +
  セレクタ（mux、ライブレジスタ）。すべての配線は正確に 1 回だけ分類される。

## 6. 重要概念: モジュール vs ジェネレータ
- **モジュール**はレジスタカタログのブロック（BPF, SVF, MIX, LPF, PI, GAIN, SCOPE …）。
  `get_modules` はこれらを列挙する。
- **ジェネレータ（ASG0/ASG1）**は信号ジェネレータの**出力**で、C# の output API で
  駆動され、`config.asg_channel_map` に対応付けられる。これらはカタログモジュール
  **ではなく**、`get_modules` の `modules` には現れない（`generators` に現れる）。
  信号の生成・停止には `configure_asg` / `plan_configure_asg` を直接使う。ASG を
  `get_modules` や `get_parameter` で確認しようとしてはいけない。

## 7. 読み取りツール（tools/、常に安全）
| ツール | 機能 | 入力 | kind |
|---|---|---|---|
| `get_status` | サーバ到達性 + ステータス。解決された `config_file`, `device_id`, `mode` も報告 | — | fact/unknown |
| `get_modules` | レジスタカタログのモジュール + ジェネレータ（ASG0/ASG1）を列挙 | — | config |
| `get_register_info` | 1 レジスタのカタログメタデータ（型・format・既定値・アドレス・共有エイリアス） | NAME | config/unknown |
| `get_parameter` | 1 つの名前付きパラメータをライブ読み取りし、工学単位にデコード | NAME | fact/unknown |
| `get_fpga_state` | モジュール別のライブ値スナップショット（デコード済み） | [--modules PI,MIX] | fact |
| `get_output_status` | アクティブデバイスのライブなジェネレータ/出力ステータス | — | fact |
| `get_sessions` | 登録済みデバイスセッション + アクティブデバイス | — | fact |
| `get_signal_path` | ノードの上流のライブ信号経路をトレース。固定ホップ = config、ライブ mux セレクタ = fact、各 mux の alternatives も。「Xへの経路」「Xに影響するモジュール」に回答 | TARGET（例: DAC0, SCOPE0） | fact/config |
| `get_affecting_parameters` | ノードの上流パス上の全モジュールの構成レジスタ | TARGET | config |
| `get_reachable` | 実現可能性（トポロジのみ）: どのソースがノードへ経路可能か。ソース指定時は正確なセレクタ書き込み | TARGET [--source SRC] | config |
| `capture_analyze_signal` | /ws/wave からキャプチャし、スカラー要約のみ返す（RMS, 平均/DC, ピーク, 最小, 最大, 主要周波数, 上位 FFT ピーク, クリッピング）。生サンプルは返さない | [LABEL] [--channel N] [--nsamples K] | measurement/unknown |

## 8. 書き込みツール（write_tools/、ドライラン -> 承認 -> 適用）
| ツール | 機能 | 入力 |
|---|---|---|
| `set_parameter` | 1 つ以上のモジュールレジスタを工学単位で設定（ゲイン・係数・設定値・オフセット）。バッチ可。ビットパック/共有アドレスのレジスタは拒否 | NAME=VALUE ... [--apply] |
| `set_signal_path` | トポロジを反転して mux セレクタ書き込みに変換し、信号を経路設定 | SRC ... SINK [--apply] |
| `configure_asg` | ASG ジェネレータ出力を設定または停止（波形・周波数・振幅・オフセット） | ASG0\|ASG1 --waveform --freq --amp --offset [--disable] [--stop] [--apply] |
| `configure_scope` | スコープのタップ（SCOPE_SEL）や取得デシメーションの設定、開始/停止 | SCOPE0\|SCOPE1 [--source SIG] [--decimation N] [--start\|--stop] [--apply] |

## 9. MCP ツール（mcp_server/、同じ操作を MCP 経由で）
読み取り: 上記と同じ `get_*`。書き込みは 2 段階: `plan_set_parameters`,
`plan_set_signal_path`, `plan_configure_asg`, `plan_stop_asg`,
`plan_configure_scope`（それぞれ `plan_token` を返す）、その後 `commit_write(plan_token)`
が人間の承認後に計画と照合しつつ適用する。秘密情報（`x-device-token`, `deviceId`）は
設定ファイルに保持され、ツールパラメータにはならない。

## 10. よくある質問への回答方法（質問 -> ツール）
- 「サーバに繋がる? / どの config? / live か?」-> `get_status`
- 「どんなモジュールがある?」-> `get_modules`
- 「<PARAM> は?」（例: PI0_SET_KP）-> `get_parameter`
- 「DAC0 への信号経路は?」-> `get_signal_path DAC0`
- 「DAC0 に影響するモジュールは?」-> `get_signal_path DAC0`（その upstream_nodes）— `get_modules` ではない
- 「DAC0 に影響するパラメータは?」-> `get_affecting_parameters DAC0`
- 「ASG1 を DAC0 に経路できる?」-> `get_reachable DAC0 --source ASG1`
- 「なぜ DAC0/SCOPE0 はノイズっぽい?」-> `get_signal_path` + モジュール状態 + `capture_analyze_signal`。まず観測を報告し、原因は解釈として提示
- 「ASG1 で正弦波を生成」-> `configure_asg ASG1 --waveform SINE --freq 1000 --amp 0.2`（ドライラン -> 承認 -> 適用）
- 「PI0_SET_KP を 0.5 に設定」-> `set_parameter PI0_SET_KP=0.5`（ドライラン -> 承認 -> 適用）
- 「ASG1 をチェーン経由で DAC0 へ」-> `get_reachable` の後 `set_signal_path`
- 「DAC0 を SCOPE0 で見る」-> `configure_scope SCOPE0 --source DAC0`

## 11. 設定の要点（config.json）
- `device_id` — 対象の Red Pitaya（null は GUI の activeDeviceId に追従）。
- `device_token` — `x-device-token` ヘッダとして送信。live モードで必須。
- `mode` — `live`（実機と通信）または `replay`（フィクスチャ、ハードウェア不要）。
- `base_url` — SharpRPL サーバ。`asg_channel_map` — ASG 名 -> 出力チャンネル。
1 セッションは 1 台を対象。`FPGA_AGENT_CONFIG=config.rpN.json` でボードを選択。

## 12. 必要ライブラリ
- CLI（非 MCP）経路: PyYAML（トポロジ系ツール）。numpy + websocket-client は
  `capture_analyze_signal` のみ（websocket-client はライブキャプチャ用）。`mcp` は不要。
- MCP 経路: 追加で `mcp` パッケージ（`mcp>=1.2,<2`）。
