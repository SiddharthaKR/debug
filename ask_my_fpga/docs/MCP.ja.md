# Ask My FPGA — MCP サーバー

> 🌐 言語: **日本語** · [English / 英語](MCP.md)
>
> このガイドは `MCP.md` と章立てが一対一で対応しています。片方を編集したら、
> もう片方も同じように更新して同期を保ってください。

同じエンジニアリング操作を MCP レイヤーとして公開するオプション機能です。これにより
opencode の bash 許可リストに限らず、**MCP に対応した任意のクライアント**（opencode、
Claude Desktop、IDE）からツールを利用できます。`MCP` git ブランチ上にあり、`main` は
従来の CLI ツール構成をフォールバックとして残します。MCP サーバーは `tools/` と
`write_tools/` のスクリプトを**置き換えません** — それらのロジックを import して再利用
します。

## 公開するもの（レジスタではなくエンジニアリング操作）
読み取り（安全）: `get_status`、`get_modules`、`get_parameter`、`get_register_info`、
`get_fpga_state`、`get_output_status`、`get_sessions`、`get_signal_path`、
`get_affecting_parameters`、`get_reachable`、`capture_analyze_signal`。

書き込み（2段階）: `plan_set_parameters`、`plan_set_signal_path`、
`plan_configure_asg`、`plan_stop_asg`、`plan_configure_scope` — それぞれ
**plan_token** を返します — その後 `commit_write(plan_token)` 1つで適用します。

すべてのツールは名前付きパラメータ／エンジニアリング単位で動作します（例:
`plan_set_parameters({"PI0_SET_KP": 0.5})`、`get_signal_path("DAC0")`）。レジスタ
マップはカタログの背後に隠れたままで、生アドレスを扱うツールはありません。

## 安全モデル
- 読み取りとすべての `plan_*` は **read-only（読み取り専用）** としてマークされ、
  ハードウェアを一切変更しません。
- `commit_write` だけが **destructive（変更あり）** としてマークされます。
- 流れ: エージェントが `plan_*` を呼び、正確なレジスタ差分を提示 → あなたが承認 →
  エージェントが `commit_write` を呼ぶ。**確認は1回。**
- `commit_write` はまずハードウェアを読み直し、プラン作成時からレジスタが変化して
  いれば**何も書かずに中止**します。承認済みのプランが、変化したボードに気付かず
  適用されることを防ぎます。プランは5分で期限切れになります。
- `x-device-token` と `deviceId` は（`fpga_common` 経由で）`config.json` から取得され、
  モデルが見えるツールパラメータには**決してなりません**。

## インストールと実行
```
pip install -r mcp_server/requirements.txt      # mcp>=1.2,<2, numpy, websocket-client, PyYAML
python3 mcp_server/server.py                     # stdio で MCP を話す
```
設定は同じ `config.json`（または `FPGA_AGENT_CONFIG` で別ファイルを指定）を使います。
実機では `"mode": "live"` に設定してください — MCP サーバーは live 用途を想定しています。

## クライアントへの接続
- **opencode:** `mcp_server/opencode.mcp.example.json` をあなたの `opencode.json`
  にマージします。
- **Claude Desktop:** `mcp_server/claude_desktop.mcp.example.json`（絶対パスで）を
  `claude_desktop_config.json` に追加します。

plan/commit の分割が書き込み前の人間による確認をすでに強制しているため、MCP 経路では
bash 許可リストは不要です。クライアントがツール単位の承認に対応していれば、
`commit_write` をゲートすると二重の安全策になります。

## ハードウェア無しでのテスト
```
# config.json を "mode": "replay" にしてから:
python3 mcp_server/selftest.py
```
読み取りと plan→commit のフル動作（ドリフト中止チェックを含む）をフィクスチャに対して
実行し、終了後にフィクスチャを元に戻します。

## 構成
```
mcp_server/
  server.py        # MCP の薄い配線（FastMCP）: ツール登録 + アノテーション
  fpga_ops.py      # 操作 + plan/commit（fpga_common/topology/tools を import）
  selftest.py      # ハードウェア不要の plan/commit テスト（replay）
  requirements.txt
  opencode.mcp.example.json
  claude_desktop.mcp.example.json
```
