---
name: generate-recommendation-report
description: Use when a user wants to convert a candidate resume PDF into a CONNECTUS candidate recommendation report, reuse the approved Chinese Word format, migrate resume wording verbatim, or generate a standardized 候选人推荐报告 DOCX.
---

# 推荐报告生成

## 核心原则

把 PDF 作为内容权威，把 `assets/reference.docx` 作为格式权威。不得改写简历原文，不得沿用母版中的旧候选人或示例内容。

**REQUIRED SUB-SKILLS:** Use `pdf:pdf` to read and render the resume PDF. Use `documents:documents` to render and verify the DOCX.

开始前完整读取 `references/report-rules.md`。不得修改 `assets/reference.docx`。

## 输入

要求用户提供一份候选人简历 PDF。客户、推荐职位、顾问信息、指定城市和附加章节均为可选项；未提供时按规则留空或采用明确的默认值。母版已经内置，不要求用户重新上传。

## 工作流

1. 提取 PDF 全文并渲染每一页，核对跨页断句、日期、公司、职位和地点。
2. 按 `references/report-rules.md` 整理 JSON。不得猜测婚姻状态、客户、顾问信息或求职动机；当前城市或推荐职位存在多个合理答案时，先询问用户。
3. 将 JSON 保存到任务的 `work/` 目录。运行：

   默认将最终 DOCX 输出到 `C:\Users\shawnxu\Desktop\工作文件\简历推荐\<候选人姓名>-候选人推荐报告.docx`。生成前创建该目录；只有用户明确指定其他交付目录时才覆盖此默认值。JSON、渲染 PDF 和逐页 PNG 等中间文件仍保存在任务的 `work/` 目录。

   `python scripts/build_report.py INPUT.json "C:\Users\shawnxu\Desktop\工作文件\简历推荐\<候选人姓名>-候选人推荐报告.docx"`

   第三个参数可选，仅用于显式指定其他母版；默认使用内置母版。
4. 运行：

   `python scripts/verify_report.py INPUT.json "C:\Users\shawnxu\Desktop\工作文件\简历推荐\<候选人姓名>-候选人推荐报告.docx"`

   任何 FAIL 都必须修正后重跑。
5. 在 Windows 上优先使用 Microsoft Word 原生打开并导出 PDF；确认一节、首页设计、第二页从学历开始、后续页眉页脚、分页和文字无裁切。
6. 查看每一页渲染图。只有内容验证和视觉验证同时通过，才交付 DOCX。

## JSON 契约

```json
{
  "candidate": {
    "name": "姓名",
    "gender": "男/女/空",
    "age": "29岁/空",
    "marital_status": "已婚/未婚/空",
    "current_city": "城市/空",
    "client": "客户/空",
    "recommended_position": "职位/空",
    "consultant": {"name": "", "mobile": "", "phone": "", "email": ""}
  },
  "recommendation_reasons": ["优势亮点原文"],
  "motivation": "求职动机原文或空",
  "education": [
    {"date": "2014.09–2018.06", "school": "学校", "degree": "本科", "major": "专业"}
  ],
  "work_experience": [
    {
      "date": "2024.05 – 至今",
      "company": "公司",
      "title": "职位",
      "location": "城市",
      "items": [{"heading": "小标题或 null", "body": "工作原文"}]
    }
  ],
  "additional_sections": []
}
```

`additional_sections` 默认留空。用户明确要求保留附加信息时，可加入 `{ "title": "证书", "lines": ["原文"] }`。

## 停止条件

- PDF 无法可靠读取且 OCR 仍失败。
- 推荐职位或当前工作城市无法可靠确定。
- 母版结构或哈希不匹配。
- Word 无法原生打开、渲染失败或页面出现裁切。
- 原文覆盖、模板残留、项目符号或段落属性验证失败。

遇到停止条件时说明具体问题；不得用未验证文件替代最终结果。
