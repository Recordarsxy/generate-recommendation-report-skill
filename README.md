# generate-recommendation-report Skill 基线备份

这是 `generate-recommendation-report` 的当前可用版本快照，冻结日期为 2026-08-12。

## 用途

- 为后续网站化开发保留一个可以随时恢复的稳定基线。
- 防止后续修改 Skill、脚本、规则或 Word 母版时丢失当前可用版本。
- 可将完整目录或 ZIP 上传到另一个 Codex 项目中分析。

## 完整 Skill

Skill 位于 `generate-recommendation-report/`，包含：

- `SKILL.md`：Skill 主说明与工作流。
- `agents/openai.yaml`：界面配置。
- `assets/reference.docx`：CONNECTUS 候选人推荐报告母版。
- `assets/preview.png`：母版预览图。
- `references/report-rules.md`：固定内容与版式规则。
- `scripts/build_report.py`：报告生成脚本。
- `scripts/verify_report.py`：报告验证脚本。

`scripts/__pycache__/` 未纳入备份，因为它只包含 Python 自动生成的缓存，不属于功能源文件。

## 完整性验证

`CHECKSUMS.sha256` 保存了所有 Skill 文件的 SHA-256 校验值。备份时，7 个文件均已与本机当前可用 Skill 逐一比对，结果全部一致。

## 恢复方法

将 `generate-recommendation-report/` 整个目录复制回 Codex 的个人 Skills 目录即可。不要只复制 `SKILL.md`，Word 母版、规则文件和两个脚本都是生成质量的一部分。

## 隐私

该备份含公司报告母版与内部规则，GitHub 仓库应保持为 Private。
